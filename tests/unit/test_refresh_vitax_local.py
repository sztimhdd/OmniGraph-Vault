"""Only a complete verified release can replace the local reader."""
import hashlib
import json
import subprocess
import types

import pytest
from fastapi.testclient import TestClient
from tests.unit.test_vitax_api import _projection
from vitax.api import create_app
from vitax.knowledge import build


def test_local_collector_runs_the_producer_program_without_ssh(monkeypatch):
    """On the collector the same program runs in the local production interpreter."""
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job, 'on_producer_host', lambda: True)
    seen = {}
    def run(command, **kwargs):
        seen['command'] = command
        seen['input'] = kwargs.get('input')
        return subprocess.CompletedProcess(command, 0, '{"ok": true}', '')
    monkeypatch.setattr(job, 'subprocess', types.SimpleNamespace(run=run, CompletedProcess=subprocess.CompletedProcess))
    assert job.ssh_python('ack-node-2', 'print(1)') == {'ok': True}
    assert seen['command'] == [job.PRODUCER_PYTHON, '-S', '-']
    assert seen['input'] == 'print(1)'


def test_mac_default_keeps_the_ssh_producer_entry(monkeypatch):
    """Anywhere else the existing ssh producer entry is unchanged."""
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job, 'on_producer_host', lambda: False)
    seen = {}
    def run(command, **kwargs):
        seen['command'] = command
        return subprocess.CompletedProcess(command, 0, '{"ok": true}', '')
    monkeypatch.setattr(job, 'subprocess', types.SimpleNamespace(run=run, CompletedProcess=subprocess.CompletedProcess))
    assert job.ssh_python('ack-node-2', 'print(1)') == {'ok': True}
    assert seen['command'] == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'ack-node-2', 'python3 -']


def test_refresh_library_imports_the_local_snapshot_without_scp(tmp_path, monkeypatch):
    """A local collector export is copied into the snapshot; no scp round trip."""
    from scripts import refresh_vitax_local as job
    remote = tmp_path / 'remote'; remote.mkdir()
    (remote / 'articles.sqlite').write_bytes(b'LOCAL_SQLITE')
    (remote / 'receipt.json').write_text('{"snapshot_id": "s1"}')
    monkeypatch.setattr(job, 'on_producer_host', lambda: True)
    monkeypatch.setattr(job, 'ssh_python', lambda host, program, timeout=90: {'snapshot_id': 's1', 'remote_dir': str(remote)})
    scp_calls = []
    monkeypatch.setattr(job, 'subprocess', types.SimpleNamespace(run=lambda *a, **k: scp_calls.append(a) or subprocess.CompletedProcess(a[0], 0, '', ''), CompletedProcess=subprocess.CompletedProcess))
    promoted = []
    monkeypatch.setattr(job, 'promote_library', lambda snapshot, current: promoted.append((snapshot, current)))
    receipt = job.refresh_library(tmp_path / 'library-root')
    assert receipt['snapshot_id'] == 's1'
    snapshot = tmp_path / 'library-root/library/snapshots/s1'
    assert (snapshot / 'articles.sqlite').read_bytes() == b'LOCAL_SQLITE'
    assert (snapshot / 'receipt.json').read_text() == '{"snapshot_id": "s1"}'
    assert scp_calls == [] and len(promoted) == 1


def package(path, release_id):
    path.mkdir()
    data = _projection();data['release_id'] = release_id
    build(data, path/'public.sqlite')
    (path/'site').mkdir();(path/'site/index.html').write_text(release_id)
    entries=[{'path':str(p.relative_to(path)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [path/'public.sqlite',path/'site/index.html']]
    (path/'manifest.json').write_text(json.dumps({'schema_version':1,'release_id':release_id,'files':entries}))


def test_verified_release_promotes_without_restart_and_bad_package_keeps_old(tmp_path):
    from scripts.refresh_vitax_local import promote_release
    first=tmp_path/'one';second=tmp_path/'two'
    package(first,'first');package(second,'second')
    current=tmp_path/'current'
    promote_release(first,current)
    with TestClient(create_app(current/'public.sqlite', site_dir=current/'site')) as client:
        assert client.get('/api/release').json()['release_id']=='first'
        promote_release(second,current)
        assert client.get('/api/release').json()['release_id']=='second'
        assert client.get('/').text=='second'
        metadata=json.loads((first/'manifest.json').read_text())
        metadata['files']=[f for f in metadata['files'] if f['path']!='site/index.html']
        (first/'manifest.json').write_text(json.dumps(metadata))
        (first/'site/index.html').write_text('unverified replacement')
        with pytest.raises(ValueError):promote_release(first,current)
        assert client.get('/api/release').json()['release_id']=='second'
        (first/'public.sqlite').write_bytes(b'broken')
        with pytest.raises(ValueError):promote_release(first,current)
        assert client.get('/api/release').json()['release_id']=='second'


def test_provider_failure_marks_the_day_and_never_quarantines_a_source(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    import sqlite3
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):
            c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.executemany('INSERT INTO rss_articles(id,body,layer2_verdict) VALUES(?,?,?)',[(i,'synthetic article '+('a'*1800),'ok') for i in (1,2,3,4)])
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[]})
    attempted=[]
    def fail(*args,**kwargs):attempted.append(args[1]);raise RuntimeError('synthetic provider failure')
    monkeypatch.setattr(job,'produce',fail)
    with pytest.raises(RuntimeError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert json.loads((root/'production-day.json').read_text())['status']=='failed'
    (root/'production-day.json').write_text(json.dumps({'day':'2000-01-01','status':'failed'}))
    with pytest.raises(RuntimeError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert attempted==[('rss',4),('rss',4)]
    assert not (root/'failed-sources.json').exists()


def test_gap_queue_drops_the_harness_and_length_gates(tmp_path):
    from scripts.refresh_vitax_local import gap_queue
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):
            c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        # Below the old 1600-char floor and without the old 'harness' keyword.
        c.execute('INSERT INTO articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('短文没有 harness 关键词','zh','ok'))
        # Above the old 25000-byte ceiling.
        c.execute('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('x'*90000,'en','ok'))
    assert gap_queue(root,{'documents':[]},{},50)==[('wechat',1),('rss',1)]


def test_gap_queue_reuses_an_existing_chinese_draft(tmp_path):
    from scripts.refresh_vitax_local import gap_queue
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):
            c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO rss_articles(id,body,body_translated,lang,layer2_verdict) VALUES(1,?,?,?,?)',('English original','已有译稿','en','ok'))
        c.execute('INSERT INTO rss_articles(id,body,body_translated,lang,layer2_verdict) VALUES(2,?,?,?,?)',('English original two',None,'en','ok'))
    assert gap_queue(root,{'documents':[]},{},50)==[('rss',2)]


def test_gap_queue_keeps_translating_a_revision_that_already_has_an_interpretation(tmp_path):
    from scripts.refresh_vitax_local import gap_queue
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    body='English original'
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):
            c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',(body,'en','ok'))
    from scripts.refresh_vitax_local import stored_revision
    base={'documents':[{'doc_id':'rss-1','revision_id':stored_revision('rss',1,body)}]}   # interpretation already published
    assert gap_queue(root,base,{},50)==[('rss',1)]                                        # translation still missing


def test_explicit_wiki_update_keeps_old_citations_and_other_knowledge():
    from scripts.refresh_vitax_local import merge_wiki_update
    from copy import deepcopy
    base = _projection()
    prior = next(k for k in base['knowledge'] if k['kind']=='wiki')
    original = deepcopy(base)
    update = deepcopy(base)
    target = next(k for k in update['knowledge'] if k['knowledge_id']==prior['knowledge_id'])
    target['body'] += '\n新的依据更新。'
    target['evidence_ids'] = target['evidence_ids'][-1:]
    merged = merge_wiki_update({'projection':update},base,prior['knowledge_id'])
    changed = next(k for k in merged['knowledge'] if k['knowledge_id']==prior['knowledge_id'])
    assert changed['evidence_ids'] == prior['evidence_ids']
    assert changed['body'] != prior['body']
    assert len(merged['knowledge']) == len(base['knowledge'])
    assert base == original
    with pytest.raises(ValueError, match='explicit target'):
        merge_wiki_update({'projection':update},base,'unrelated-wiki')


def test_changed_body_requeues_and_known_revision_is_skipped(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    body='中文正文'+('测'*1800)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):
            c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
            c.execute(f'INSERT INTO {table}(id,body,layer2_verdict) VALUES(1,?,?)',(body,'ok'))
    revision=job.stored_revision('wechat',1,body)
    base={'documents':[{'doc_id':'wechat-1','revision_id':revision}]}
    monkeypatch.setattr(job,'_export_public_dto',lambda _: base)
    attempts=[]
    def capture(root_,selection,**kwargs):attempts.append(selection);raise ValueError('stop before model')
    monkeypatch.setattr(job,'produce',capture)
    with pytest.raises(ValueError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert attempts==[('rss',1)]
    (root/'production-day.json').write_text(json.dumps({'day':'2000-01-01','status':'failed'}))
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        c.execute('UPDATE articles SET body=?',(body+' changed',))
    with pytest.raises(ValueError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert attempts==[('rss',1),('wechat',1)]
    assert base['documents'][0]['revision_id']==revision


def test_auto_selection_revision_matches_real_standardization(tmp_path):
    from scripts.refresh_vitax_local import stored_revision
    from vitax.production import standardize_documents
    body='原文 synthetic harness\n\n```python\nprint(1)\n```\n'
    saved=tmp_path/'original.md';saved.write_text(body)
    source={'documents':[dict(source_id='wechat-42',source_url='https://example.test/a',title='synthetic',
        capture_format='stored-markdown',markdown_path=str(saved),raw_markdown_sha256=hashlib.sha256(body.encode()).hexdigest(),
        source_record_ref={'source':'wechat','record_id':42},source_snapshot_id='synthetic',representation_saved_at='2026-10-03T00:00:00Z',fetched_at=None)]}
    doc=standardize_documents(source,capture_root=tmp_path)['documents'][0]
    assert stored_revision('wechat',42,body)==doc['revision_id']
    assert doc['paragraphs'][0]['text']==body


def test_only_a_twice_failed_revision_leaves_the_queue(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    from scripts.refresh_vitax_local import gap_queue
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    body='synthetic article '+('a'*1800)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.executemany('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(?,?,?,?)',[(i,body,'en','ok') for i in (1,2,3,4)])
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[]})
    attempted=[]
    def fail(root_,selection,**kwargs):
        attempted.append(selection)
        source,record=selection
        error=job.ProductionError('synthetic acceptance failure')
        error.source_revision=job.stored_revision(source,record,body);error.source_task='translate'
        raise error
    monkeypatch.setattr(job,'produce',fail)
    for _ in range(2):
        with pytest.raises(job.ProductionError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
        (root/'production-day.json').write_text(json.dumps({'day':'2000-01-01','status':'failed'}))
    assert attempted==[('rss',4),('rss',3),('rss',2),('rss',1)]*2
    failures=json.loads((root/'production-failures.json').read_text())
    assert failures[job.stored_revision('rss',4,body)+':deepseek-v6:translate']==2
    assert gap_queue(root,{'documents':[]},failures,50)==[]


def test_gap_queue_skips_a_twice_failed_revision(tmp_path):
    from scripts.refresh_vitax_local import gap_queue
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.executemany('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(?,?,?,?)',[(i,'synthetic article','en','ok') for i in (1,2)])
    body='synthetic article'
    from scripts.refresh_vitax_local import stored_revision
    failed={stored_revision('rss',2,body)+':deepseek-v6:translate':2}
    assert gap_queue(root,{'documents':[]},failed,50)==[('rss',1)]


def test_one_bad_article_does_not_block_a_good_one(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    good='synthetic article '+('a'*1800);bad='synthetic article '+('b'*1800)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO articles(id,body,layer2_verdict) VALUES(1,?,?)',(good,'ok'))
        c.execute('INSERT INTO rss_articles(id,body,layer2_verdict) VALUES(1,?,?)',(bad,'ok'))
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[],'evidence':[],'knowledge':[{'knowledge_id':'wiki-mcp','kind':'wiki','title':'MCP','body':'旧主题'}],'entities':[],'relations':[]})
    published=[]
    def produce(root_,selection,**kwargs):
        if selection==('rss',1):
            error=job.ProductionError('bad article');error.source_revision=job.stored_revision('rss',1,bad);raise error
        path=root_/'accepted'/('ok-'+selection[0]);path.mkdir(parents=True)
        article={'projection':{'documents':[],'evidence':[],'knowledge':[{'knowledge_id':'article-wechat-1','kind':'article','title':'MCP 主题','body':'中文'}],'entities':[{'entity_id':'mcp','name':'MCP'}],'relations':[]}}
        (path/'accepted.json').write_text(json.dumps(article))
        return (path/'accepted.json',False,'article')
    monkeypatch.setattr(job,'produce',produce)
    monkeypatch.setattr(job,'write_back_translation',lambda *a,**k:{'written':True})
    def no_wiki(*args,**kwargs):raise job.ProductionError('wiki down')
    monkeypatch.setattr(job,'produce_wiki',no_wiki)
    monkeypatch.setattr(job,'build_release',lambda source,directory:(directory.mkdir(parents=True),(directory/'index.html').write_text('x')))
    monkeypatch.setattr(job,'promote_release',lambda directory,current:published.append(True))
    state=job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert published==[True]
    assert state['batch']['accepted']==1 and state['batch']['failed']==1
    assert state['batch']['wiki_error']=='ProductionError'
    assert json.loads((root/'production-day.json').read_text())['status']=='published'


def test_long_foreign_body_is_chunked_without_loss(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job,'CHUNK_CHARS',400)
    text='\n'.join('English sentence number %d.'%i for i in range(80))
    prompts=[]
    def turn(prompt,directory,**kwargs):
        prompts.append(json.loads(prompt));directory.mkdir(parents=True,exist_ok=True)
        output=directory/'model-output.json';output.write_text('译文%d'%len(prompts),encoding='utf-8')
        return output,directory/'usage.json'
    monkeypatch.setattr(job,'native_turn',turn)
    doc={'doc_id':'x-1','revision_id':'rev-'+'a'*20,'title':'T','paragraphs':[{'locator':'paragraph:1','text':text}]}
    assert job._article_task(text)=='translate'
    assembled=job._translate_document(doc,root=tmp_path,tag='t',budget=None,lane='K')
    assert assembled==''.join('译文%d'%n for n in range(1,len(prompts)+1))
    assert len(prompts)>1 and ''.join(p['source'] for p in prompts)==text


def test_write_back_translation_is_wired_to_the_ssh_producer_entry(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import subprocess,sys
    import sqlite3
    database=tmp_path/'original.sqlite'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE articles(id INTEGER,body TEXT,body_translated TEXT,translated_lang TEXT)')
        c.execute('INSERT INTO articles VALUES(1,?,NULL,NULL)',('原始正文',))
    revision=job.stored_revision('wechat',1,'原始正文')
    calls=[]
    def fake_ssh(host,program,timeout=30):
        calls.append((host,program))
        return json.loads(subprocess.run([sys.executable,'-c',program],capture_output=True,text=True,check=True).stdout)
    monkeypatch.setattr(job,'ssh_python',fake_ssh)
    assert job.write_back_translation(('wechat',1),revision_id=revision,body='译文',database=str(database),history_dir=tmp_path/'history')=={'written':True,'field':'body_translated'}
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT body_translated,translated_lang FROM articles WHERE id=1').fetchone()==('译文','zh')
    # A valid translation already in the source DB is preferred over a rewrite.
    assert job.write_back_translation(('wechat',1),revision_id=revision,body='另一版本',database=str(database),history_dir=tmp_path/'history')=={'written':False,'reason':'existing-translation'}
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT body_translated FROM articles WHERE id=1').fetchone()[0]=='译文'
        c.execute('UPDATE articles SET body=?,body_translated=NULL WHERE id=1',('被改写的正文',))
    assert job.write_back_translation(('wechat',1),revision_id=revision,body='陈旧译文',database=str(database),history_dir=tmp_path/'history')=={'written':False,'reason':'original-changed'}
    assert calls and calls[0][0]=='ack-node-2' and 'body_translated' in calls[0][1]
    assert 'AND body=?' in calls[0][1] and 'rowcount' in calls[0][1]      # atomic UPDATE, no read-then-write drift


def test_refresh_pushes_a_translation_to_the_source_database(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    body='English original '+('a'*1800)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO rss_articles(id,body,layer2_verdict) VALUES(1,?,?)',(body,'ok'))
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[],'evidence':[],'knowledge':[],'entities':[],'relations':[]})
    revision=job.stored_revision('rss',1,body)
    def produce(root_,selection,**kwargs):
        path=root_/'accepted'/'ok';path.mkdir(parents=True)
        (path/'accepted.json').write_text(json.dumps({'projection':{'documents':[{'revision_id':revision}],'evidence':[],'knowledge':[{'knowledge_id':'article-rss-1','kind':'article','body':'译文正文'}],'entities':[],'relations':[]}}))
        return (path/'accepted.json',False,'translate')
    monkeypatch.setattr(job,'produce',produce)
    monkeypatch.setattr(job,'produce_wiki',lambda *a,**k:(_ for _ in ()).throw(job.ProductionError('no wiki')))
    monkeypatch.setattr(job,'build_release',lambda source,directory:(directory.mkdir(parents=True),(directory/'index.html').write_text('x')))
    monkeypatch.setattr(job,'promote_release',lambda directory,current:None)
    pushes=[]
    monkeypatch.setattr(job,'write_back_translation',lambda selection,**kw:pushes.append((selection,kw)) or {'written':True})
    state=job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert pushes==[(('rss',1),{'revision_id':revision,'body':'译文正文'})]
    assert state['batch']['write_back']=={'pushed':1,'skipped':0,'failed':0}


def test_refresh_library_owns_the_export_field_contract(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import hashlib,sqlite3
    # The exact shim the remote export program runs, executed offline.
    out=tmp_path/'out';out.mkdir()
    database=out/'articles.sqlite'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE articles(id INTEGER,body TEXT,layer1_verdict TEXT)')
        c.execute('CREATE TABLE rss_articles(id INTEGER,body TEXT,layer1_verdict TEXT)')
    receipt=out/'receipt.json';receipt.write_text(json.dumps({'schema_version':1,'snapshot_id':'s','sqlite_sha256':'stale'}))
    x={'schema_version':1,'snapshot_id':'s','sqlite_sha256':'stale'}
    exec(job._REMOTE_FIELD_SHIM,{'out':out,'fields':job.EXPORT_FIELDS,'x':x,'json':json,'hashlib':hashlib,'sqlite3':sqlite3})
    with sqlite3.connect(database) as c:
        columns={row[1] for row in c.execute('PRAGMA table_info(articles)')}
    assert 'body_rewritten' in job.EXPORT_FIELDS and 'body_rewritten' in columns
    assert json.loads(receipt.read_text())['sqlite_sha256']==hashlib.file_digest(database.open('rb'),'sha256').hexdigest()
    captured=[]
    monkeypatch.setattr(job,'ssh_python',lambda host,program,timeout=90:captured.append(program) or (_ for _ in ()).throw(RuntimeError('stop before transfer')))
    with pytest.raises(RuntimeError):job.refresh_library(tmp_path/'library-root')
    assert 'body_rewritten' in captured[0] and 'ALTER TABLE' in captured[0]


def test_theme_groups_uses_content_cues_not_a_fixed_topic():
    from scripts.refresh_vitax_local import _theme_id, theme_groups
    one={'projection':{'entities':[{'name':'MCP'}],'knowledge':[{'title':'无状态 MCP'}]}}
    two={'projection':{'entities':[{'name':'MCP'}],'knowledge':[{'title':'datasette-mcp'}]}}
    three={'projection':{'entities':[],'knowledge':[{'title':'编译器优化'}]}}
    groups=theme_groups([one,two,three])
    assert groups[0][0]=='mcp' and len(groups[0][1])==2
    assert all(topic!='agent harness engineering' for topic,_ in groups)
    assert theme_groups([three])                                # one source may start a useful theme
    assert _theme_id('MCP')=='wiki-mcp'
    assert _theme_id('编译器')!='wiki-theme' and _theme_id('编译器')!=_theme_id('另一个中文主题')


def test_translation_chunk_identity_is_not_the_article_identity():
    from scripts.refresh_vitax_local import _turn_identity
    article=_turn_identity('K','rev-1','article')
    chunk=_turn_identity('K','rev-1','translate',chunk=True)
    assert article['stage']=='article' and article['recipe']=='deepseek-v6'
    assert chunk['stage']=='translate' and chunk['recipe']=='deepseek-v6-chunk'
    assert (chunk['stage'],chunk['recipe'])!=(article['stage'],article['recipe'])


def test_cache_tag_separates_translation_from_an_older_interpretation():
    from scripts.refresh_vitax_local import _article_tag, _knowledge_id, WIKI_SOURCES
    doc={'doc_id':'rss-196907','revision_id':'rev-'+'b'*20}
    assert _article_tag('article',doc)=='deepseek-v6-article-rss-196907-'+'b'*12   # legacy cache still hits
    assert _article_tag('translate',doc)=='deepseek-v6-translate-rss-196907-'+'b'*12
    assert _article_tag('translate',doc)!=_article_tag('article',doc)
    assert _knowledge_id('translate',doc)!=_knowledge_id('article',doc)             # no merge collision with the old draft
    assert WIKI_SOURCES==2                                                          # aligned with the packet cap


def test_language_prefers_recorded_lang_then_main_script():
    from scripts.refresh_vitax_local import _article_task, _is_chinese
    assert _is_chinese('这是一段很长的中文正文内容', 'zh') is True
    assert _is_chinese('This is a long English body', 'en') is False
    assert _is_chinese('这段正文混了一个 x 字母', None) is True   # main script wins, not one character
    assert _is_chinese('plain ascii body only', None) is False
    assert _article_task('这段正文混了一个 x 字母')=='article'
    assert _article_task('plain ascii body only')=='translate'


def test_wiki_provider_abort_stops_paid_wiki_but_publishes_articles(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('中文正文','zh','ok'))
        c.execute('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('中文正文二','zh','ok'))
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[],'evidence':[],'knowledge':[{'knowledge_id':'wiki-mcp','kind':'wiki','title':'MCP','body':'旧主题'}],'entities':[],'relations':[]})
    def produce(root_,selection,**kwargs):
        path=root_/'accepted'/(selection[0]+'-'+str(selection[1]));path.mkdir(parents=True)
        article={'projection':{'documents':[{'revision_id':'rev-'+str(selection[1])}],'evidence':[],'knowledge':[{'knowledge_id':'article-'+str(selection[1]),'kind':'article','title':'MCP 主题','body':'中文'}],'entities':[{'entity_id':'mcp','name':'MCP'}],'relations':[]}}
        (path/'accepted.json').write_text(json.dumps(article))
        return (path/'accepted.json',False,'article')
    monkeypatch.setattr(job,'produce',produce)
    wiki_calls=[]
    def wiki(*args,**kwargs):
        wiki_calls.append(args);raise RuntimeError('provider down during wiki')
    monkeypatch.setattr(job,'produce_wiki',wiki)
    published=[]
    monkeypatch.setattr(job,'build_release',lambda source,directory:(directory.mkdir(parents=True),(directory/'index.html').write_text('x')))
    monkeypatch.setattr(job,'promote_release',lambda directory,current:published.append(True))
    with pytest.raises(RuntimeError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert published==[True] and len(wiki_calls)==1          # articles published, paid Wiki stopped after the abort
    state=json.loads((root/'status.json').read_text())
    assert state['batch']['accepted']==2 and state['batch']['aborted']=='RuntimeError'
    assert state['batch']['wiki_error']=='RuntimeError' and state['batch']['wiki_themes']==0


def test_normal_entry_shares_the_shared_ledger(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO rss_articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('synthetic article','en','ok'))
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[]})
    monkeypatch.setattr(job,'produce',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('provider down')))
    with pytest.raises(RuntimeError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert (root/'backfill-budget.json').exists()            # non-backfill paid entry shares the ledger


def test_wiki_merge_takes_the_accepted_object_directly(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.execute('INSERT INTO articles(id,body,lang,layer2_verdict) VALUES(1,?,?,?)',('中文正文','zh','ok'))
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[],'evidence':[],'knowledge':[],'entities':[],'relations':[]})
    def produce(root_,selection,**kwargs):
        path=root_/'accepted'/'a';path.mkdir(parents=True)
        (path/'accepted.json').write_text(json.dumps({'projection':{'documents':[{'revision_id':'rev-1'}],'evidence':[],'knowledge':[{'knowledge_id':'article-1','kind':'article','title':'MCP 主题','body':'中文'}],'entities':[{'entity_id':'mcp','name':'MCP'}],'relations':[]}}))
        return (path/'accepted.json',False,'article')
    monkeypatch.setattr(job,'produce',produce)
    wiki={'schema_version':1,'usage':None,'selected_images':[],'projection':{'documents':[{'revision_id':'rev-1'}],'evidence':[{'evidence_id':'e1','revision_id':'rev-1','locator':'paragraph:1','quote':'原文'}],'knowledge':[{'knowledge_id':'wiki-mcp','kind':'wiki','title':'MCP','body':'主题正文','evidence_ids':['e1']}],'entities':[],'relations':[]}}
    monkeypatch.setattr(job,'produce_wiki',lambda *a,**k:wiki)
    seen={}
    def build(source,directory):
        seen['projection']=json.loads(source.read_text());directory.mkdir(parents=True);(directory/'index.html').write_text('x')
    monkeypatch.setattr(job,'build_release',build)
    monkeypatch.setattr(job,'promote_release',lambda directory,current:None)
    state=job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    ids=[item['knowledge_id'] for item in seen['projection']['knowledge']]
    assert 'wiki-mcp' in ids and 'article-1' in ids and state['batch']['wiki_themes']==1


def test_provider_abort_publishes_already_accepted_articles(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3
    root=tmp_path/'runtime';(root/'library/current').mkdir(parents=True)
    with sqlite3.connect(root/'library/current/articles.sqlite') as c:
        for table in ('articles','rss_articles'):c.execute(f'CREATE TABLE {table}(id INTEGER,body TEXT,body_translated TEXT,lang TEXT,layer2_verdict TEXT)')
        c.executemany('INSERT INTO rss_articles(id,body,layer2_verdict) VALUES(?,?,?)',[(i,'synthetic article','ok') for i in (1,2)])
    monkeypatch.setattr(job,'_export_public_dto',lambda _: {'documents':[],'evidence':[],'knowledge':[],'entities':[],'relations':[]})
    def produce(root_,selection,**kwargs):
        if selection==('rss',2):
            path=root_/'accepted'/'one';path.mkdir(parents=True)
            (path/'accepted.json').write_text(json.dumps({'projection':{'documents':[],'evidence':[],'knowledge':[],'entities':[],'relations':[]}}))
            return (path/'accepted.json',False,'article')
        raise RuntimeError('provider down after the first article')
    monkeypatch.setattr(job,'produce',produce)
    monkeypatch.setattr(job,'produce_wiki',lambda *a,**k:(_ for _ in ()).throw(job.ProductionError('no wiki')))
    published=[]
    monkeypatch.setattr(job,'build_release',lambda source,directory:(directory.mkdir(parents=True),(directory/'index.html').write_text('x')))
    monkeypatch.setattr(job,'promote_release',lambda directory,current:published.append(True))
    with pytest.raises(RuntimeError):job.refresh(root,tmp_path/'unused',use_existing_snapshot=True)
    assert published==[True]                                  # prior success saved before the abort
    state=json.loads((root/'status.json').read_text())
    assert state['batch']['accepted']==1 and state['batch']['aborted']=='RuntimeError'
    assert json.loads((root/'production-day.json').read_text())['status']=='failed'


def test_explicit_produce_reuses_existing_translation_without_buying(tmp_path, monkeypatch):
    from scripts import refresh_vitax_local as job
    from tests.unit.test_vitax_local_articles import mirror
    root = tmp_path/'runtime'; (root/'library').mkdir(parents=True)
    mirror(root/'library/current')
    monkeypatch.setattr(job, 'native_turn', lambda *a, **k: pytest.fail('must reuse existing translation'))
    path, reused, task = job.produce(root, ('wechat', 1))
    assert reused and task == 'translate'
    assert json.loads(path.read_text())['projection']['knowledge'][0]['body'] == '已有译文'


def _pending_wiki_setup(tmp_path, monkeypatch, count):
    from scripts import refresh_vitax_local as job
    root = tmp_path/'runtime'; root.mkdir()
    empty = {'documents':[], 'evidence':[], 'knowledge':[], 'entities':[], 'relations':[]}
    members = []
    for i in range(count):
        path = root/'accepted'/str(i)/'accepted.json'; path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'projection':empty}))
        members.append({'selection':['rss',i+1], 'accepted':str(path)})
    (root/'pending-wikis.json').write_text(json.dumps({'wiki-mcp':{'topic':'MCP','members':members}}))
    monkeypatch.setattr(job, '_export_public_dto', lambda _: empty)
    monkeypatch.setattr(job, 'gap_queue', lambda *a: [])
    monkeypatch.setattr(job, 'produce', lambda *a, **k: pytest.fail('pending Wiki must reuse accepted articles'))
    monkeypatch.setattr(job, 'build_release', lambda *a: None)
    monkeypatch.setattr(job, 'promote_release', lambda *a: None)
    return job, root, members


def test_failed_wiki_resumes_from_pending_without_new_articles(tmp_path, monkeypatch):
    job, root, members = _pending_wiki_setup(tmp_path, monkeypatch, 1)
    calls = []
    def wiki(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == 1:
            raise job.ProductionError('invalid Wiki')
        return {'projection':{'knowledge':[{'knowledge_id':'wiki-mcp','kind':'wiki'}]}}
    monkeypatch.setattr(job, 'produce_wiki', wiki)
    monkeypatch.setattr(job, 'merge_wiki_update', lambda wiki, base, key: base)
    job.refresh(root, tmp_path/'unused', use_existing_snapshot=True, backfill=True)
    assert json.loads((root/'pending-wikis.json').read_text())['wiki-mcp']['members'] == members
    state = job.refresh(root, tmp_path/'unused', use_existing_snapshot=True, backfill=True)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert state['batch']['input'] == 0 and state['batch']['wiki_themes'] == 1
    assert json.loads((root/'pending-wikis.json').read_text()) == {}


def test_wiki_overflow_preserves_uncovered_members_for_next_queue(tmp_path, monkeypatch):
    job, root, members = _pending_wiki_setup(tmp_path, monkeypatch, 3)
    calls = []
    monkeypatch.setattr(job, 'produce_wiki', lambda *a, **k: calls.append(a[1]) or {'projection':{}})
    monkeypatch.setattr(job, 'merge_wiki_update', lambda wiki, base, key: base)
    job.refresh(root, tmp_path/'unused', use_existing_snapshot=True, backfill=True)
    assert calls == [[('rss',1),('rss',2)]]
    assert json.loads((root/'pending-wikis.json').read_text())['wiki-mcp']['members'] == members[2:]
    job.refresh(root, tmp_path/'unused', use_existing_snapshot=True, backfill=True)
    assert calls[-1] == [('rss',3)]
    assert json.loads((root/'pending-wikis.json').read_text()) == {}





def test_unknown_language_ignores_technical_noise_and_preserves_replaced_draft(tmp_path, monkeypatch):
    from scripts import refresh_vitax_local as job
    import sqlite3, subprocess, sys
    prose = '这篇文章介绍工具配置和实际操作，保留技术名称并说明使用方法。' * 40
    chinese = '<article data-route="' + 'x'*1367 + '">' + prose + '</article>'
    chinese += '\nhttps://example.test/' + 'a'*4000 + '\n```python\n' + 'print(value)\n'*300 + '```'
    english = '中文注释句' + ('English technical documentation describes practical configuration. ' * 350)
    assert job._article_task(chinese, None) == 'article'
    assert job._article_task(english, None) == 'translate'
    assert job._article_task(chinese, 'en') == 'translate'
    assert job._article_task(english, 'zh') == 'article'
    database = tmp_path/'source.sqlite'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE articles(id INTEGER,body TEXT,body_translated TEXT,translated_lang TEXT)')
        c.execute('INSERT INTO articles VALUES(1,?,?,?)', ('English original', english, 'en'))
    def offline(host, program, timeout=30):
        return json.loads(subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, check=True).stdout)
    monkeypatch.setattr(job, 'ssh_python', offline)
    result = job.write_back_translation(('wechat',1), revision_id=job.stored_revision('wechat',1,'English original'), body=prose, database=database, history_dir=tmp_path/'history')
    assert result['written'] is True
    saved = list((tmp_path/'history').glob('*.json'))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())['body_translated'] == english
    assert json.loads(saved[0].read_text())['translated_lang'] == 'en'
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT body_translated FROM articles').fetchone()[0] == prose


def test_paid_cache_ignores_only_packet_time_with_verified_original_prompt(tmp_path, monkeypatch):
    from scripts import refresh_vitax_local as job
    from tests.unit.test_backfill_budget import result
    directory = tmp_path/'native'/'wiki'; directory.mkdir(parents=True)
    prompt = json.dumps({'task':'wiki','sources':[{'revision_id':'rev-1','text':'original','representation_saved_at':'old'}]})
    (directory/'native-result.json').write_text(json.dumps(result()))
    (directory/'prompt.sha256').write_text(hashlib.sha256(prompt.encode()).hexdigest())
    (directory/'prompt.txt').write_text(prompt)
    monkeypatch.setattr(job, 'ssh_python', lambda *a, **k: pytest.fail('paid cache must stay offline'))
    changed = prompt.replace('old','new')
    assert job.native_turn(changed, directory)[0].is_file()
    with pytest.raises(ValueError, match='stale'):
        job.native_turn(changed.replace('original','different'), directory)


def test_recover_projection_isolates_unknown_inline_and_never_generates(tmp_path, monkeypatch):
    from scripts import refresh_vitax_local as job
    from tests.unit.test_citation_contract import projection
    data = projection()
    bad = dict(data['knowledge'][0], knowledge_id='bad', body='未知 evidence-'+'0'*20)
    data['knowledge'].append(bad)
    candidate = tmp_path/'candidate.json'; candidate.write_text(json.dumps(data))
    monkeypatch.setattr(job,'native_turn',lambda *a,**k:pytest.fail('recovery must not buy'))
    result = job.recover_projection(tmp_path,candidate,tmp_path/'recovered.json')
    assert result['knowledge'] == 1 and result['failures'][0]['knowledge_id'] == 'bad'
    assert len(json.loads((tmp_path/'recovered.json').read_text())['knowledge']) == 1



def test_local_stdlib_helper_skips_site_startup(monkeypatch):
    import sys
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job, 'on_producer_host', lambda: True)
    monkeypatch.setattr(job, 'PRODUCER_PYTHON', sys.executable)
    result = job.ssh_python('collector', 'import json,sys,sqlite3; c=sqlite3.connect(":memory:"); print(json.dumps({"site_loaded":"site" in sys.modules,"sqlite":c.execute("select 7").fetchone()[0]}))')
    assert result == {'site_loaded': False, 'sqlite': 7}


def test_export_bootstrap_preserves_cli_args_without_site(tmp_path, monkeypatch):
    import ast, sys, sysconfig
    from scripts import refresh_vitax_local as job
    captured = {}
    def capture(host, program, **kwargs):
        captured['program'] = program
        raise RuntimeError('captured')
    monkeypatch.setattr(job, 'ssh_python', capture)
    with pytest.raises(RuntimeError, match='captured'):
        job.refresh_library(tmp_path)
    node = next(n for n in ast.parse(captured['program']).body if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'bootstrap' for t in n.targets))
    bootstrap = ast.literal_eval(node.value)
    script = tmp_path / 'export.py'
    script.write_text('import sys,json,markdown;print(json.dumps({"args":sys.argv[1:],"site":"site" in sys.modules,"markdown":bool(markdown.markdown("x"))}))')
    result = subprocess.run([sys.executable, '-S', '-c', bootstrap, sysconfig.get_path('purelib'), str(script), '--source', 'input'], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {'args':['--source','input'],'site':False,'markdown':True}
