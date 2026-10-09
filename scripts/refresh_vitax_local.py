"""One bounded local snapshot, knowledge and release refresh; no source scanning."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.build_vitax_release import build_release, _export_public_dto
from scripts.build_vitax_source_packet import build_source_packet
from scripts.export_vitax_library import promote_library
from vitax.knowledge import KnowledgeReader, KnowledgeError, _validate_projection
from vitax.production import ProductionError, _canonical_json, _prompt, merge_accepted_articles, run, standardize_documents
from vitax.backfill_budget import BackfillBudget, BudgetError


# ponytail: 50 is the queue size, not a prompt size. One Wiki per content theme,
# bounded themes/inputs per batch; add real clustering only if themes stay wrong.
DEFAULT_QUEUE = 50
WIKI_GROUPS = 3
WIKI_SOURCES = 2          # align with the source-packet cap of one or two records
CHUNK_CHARS = 24000
SOURCE_DATABASE = '/root/OmniGraph-Vault/data/kol_scan.db'
SOURCE_HOST = 'ack-node-2'
# The collector owns the producer code, credentials and ledger. When this
# process already runs there, the same program must run locally instead of
# opening an SSH/scp round trip back to itself.
PRODUCER_HOSTNAME = 'iZj1imk39yc55iZ'
PRODUCER_PYTHON = '/root/OmniGraph-Vault/venv-aim1/bin/python'
_TITLE_TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9+#.-]{1,30}|[\u3400-\u9fff]{2,8}')
_CJK_LANGS = {'zh','zh-cn','zh-hans','zh-hant','zh-tw','zh-hk','zh-sg'}

# The production mirror must define every field the reader needs, including the
# display rewrite field. Shared verbatim with the remote export program so the
# compatibility behaviour can be tested offline. Owner: this module (not the export).
EXPORT_FIELDS = ('id','title','url','body','title_translated','body_translated','translated_lang','lang','layer1_verdict','layer2_verdict','body_rewritten')
_REMOTE_FIELD_SHIM = r'''
database=out/'articles.sqlite'
changed=False
con=sqlite3.connect(database)
for table in ('articles','rss_articles'):
 columns={row[1] for row in con.execute('PRAGMA table_info('+table+')')}
 for field in fields:
  if field not in columns:con.execute('ALTER TABLE '+table+' ADD COLUMN '+field+' TEXT');changed=True
con.commit();con.close()
if changed:
 with open(database,'rb') as stream:x['sqlite_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
 (out/'receipt.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
'''


def promote_release(directory, current):
    directory = Path(directory).resolve(strict=True)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest.get('schema_version') != 1 or not manifest.get('files'):
        raise ValueError('invalid release manifest')
    paths = [entry['path'] for entry in manifest['files']]
    actual = {'public.sqlite', *[str(p.relative_to(directory)) for p in (directory/'site').rglob('*') if p.is_file()]}
    if 'site/index.html' not in actual or len(paths) != len(set(paths)) or set(paths) != actual:
        raise ValueError('release manifest does not cover the complete package')
    for entry in manifest['files']:
        path = (directory/entry['path']).resolve(strict=True)
        path.relative_to(directory)
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != entry['sha256']:
                raise ValueError('release hash mismatch')
    with KnowledgeReader(directory/'public.sqlite') as reader:
        if reader.release_id != manifest['release_id']:
            raise ValueError('release identity mismatch')
    projection = _export_public_dto(directory/'public.sqlite')
    validated = _validate_projection(projection)
    for item in projection['knowledge']:
        if item['evidence_ids'] != validated['knowledge'][item['knowledge_id']]['evidence_ids']:
            raise KnowledgeError('inline evidence is absent from the persisted knowledge panel')
    if not (directory/'site/index.html').is_file():
        raise ValueError('release site missing')
    current = Path(current).absolute()
    if os.path.lexists(current) and not current.is_symlink():
        raise ValueError('current must be a managed symlink')
    current.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    staging = current.with_name(current.name+'.'+uuid.uuid4().hex)
    staging.symlink_to(directory,target_is_directory=True)
    staging.replace(current)


def on_producer_host():
    """True when this process already runs on the collector that owns the producer.

    There the same stdlib program runs in the local production interpreter;
    anywhere else (the Mac) it keeps the existing SSH producer entry.
    """
    return socket.gethostname() == PRODUCER_HOSTNAME


def ssh_python(host, program, timeout=300):
    # Helpers use stdlib only; the paid runner execs the full venv separately.
    command = [PRODUCER_PYTHON,'-S','-'] if on_producer_host() else ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,'python3 -']
    result = subprocess.run(command,input=program,text=True,capture_output=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{host} operation failed (exit {result.returncode})')
    return json.loads(result.stdout)


def refresh_library(root):
    files = ['scripts/export_vitax_library.py','vitax/__init__.py','vitax/local_articles.py','vitax/knowledge.py']
    payload = {p:base64.b64encode((REPO/p).read_bytes()).decode() for p in files}
    nonce = uuid.uuid4().hex
    program = 'payload='+repr(payload)+'\nnonce='+repr(nonce)+'\nfields='+repr(list(EXPORT_FIELDS))+'\n'+r'''
import socket,pathlib,base64,subprocess,json,hashlib,sqlite3
assert socket.gethostname()=='iZj1imk39yc55iZ'
r=pathlib.Path('/root/.vitax-local-automation/runtime');r.mkdir(mode=0o700,parents=True,exist_ok=True)
for name,data in payload.items():
 p=r/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);raw=base64.b64decode(data);compile(raw,name,'exec');p.write_bytes(raw);p.chmod(0o600)
out=pathlib.Path('/root/.vitax-local-automation/exports')/nonce
python='/root/OmniGraph-Vault/venv-aim1/bin/python'
bootstrap='import sys,runpy;sys.path.insert(0,sys.argv.pop(1));sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name="__main__")'
site=str(pathlib.Path(python).parent.parent/'lib'/('python'+str(__import__('sys').version_info.major)+'.'+str(__import__('sys').version_info.minor))/'site-packages')
p=subprocess.run([python,'-S','-c',bootstrap,site,str(r/'scripts/export_vitax_library.py'),'--source','/root/OmniGraph-Vault/data/kol_scan.db','--output',str(out)],capture_output=True,text=True,timeout=60)
assert p.returncode==0,'source export failed'
x=json.loads(p.stdout)
''' + _REMOTE_FIELD_SHIM + r'''
x['remote_dir']=str(out);print(json.dumps(x))
'''
    receipt = ssh_python(SOURCE_HOST,program,timeout=90)
    target = root/'library/snapshots'/receipt['snapshot_id']
    target.mkdir(parents=True,mode=0o700)
    local = on_producer_host()
    for name in ('articles.sqlite','receipt.json'):
        source = Path(receipt['remote_dir'])/name
        if local:
            if not source.is_file():
                raise RuntimeError('snapshot transfer failed; previous current retained')
            (target/name).write_bytes(source.read_bytes())
        else:
            copy = subprocess.run(['scp','-C','-q','-o','ConnectTimeout=10',SOURCE_HOST+':'+receipt['remote_dir']+'/'+name,str(target/name)],capture_output=True,text=True,timeout=240)
            if copy.returncode:
                raise RuntimeError('snapshot transfer failed; previous current retained')
        (target/name).chmod(0o600)
    promote_library(target,root/'library/current')
    return receipt


def read_native_result(tag, prompt_digest):
    """Read the original producer cache only; never submit another request."""
    program = 'tag='+repr(tag)+'\ndigest='+repr(prompt_digest)+'\n'+r'''
import socket,pathlib,json
assert socket.gethostname()=='iZj1imk39yc55iZ'
r=pathlib.Path('/root/.vitax-local-automation/deepseek-turns')/tag
f=r/'result.json';saved=r/'prompt.sha256'
if f.exists():
 assert saved.is_file() and saved.read_text()==digest,'stale remote output'
 print(f.read_text())
else:
 print('null')
'''
    return ssh_python(SOURCE_HOST,program,timeout=30)


def _prompt_content(prompt):
    """Ignore only source-packet capture time; keep task, recipe and source content exact."""
    first, separator, suffix = prompt.partition('\n')
    try:
        payload = json.loads(first)
    except json.JSONDecodeError:
        return prompt
    if not isinstance(payload, dict):
        return prompt
    for document in payload.get('sources', []):
        if isinstance(document, dict):
            document.pop('representation_saved_at', None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True) + separator + suffix


def native_turn(prompt, directory, *, budget=None, identity=None, task=None):
    """Run direct DeepSeek on the existing credential-owning producer host."""
    directory.mkdir(parents=True,mode=0o700,exist_ok=True)
    cached = directory/'native-result.json'
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    key = budget.call_key(identity,prompt) if budget is not None else None
    if budget is not None and not cached.exists() and not budget.pending(key):
        historical = read_native_result(directory.name,digest)
        if historical is not None:
            (directory/'prompt.sha256').write_text(digest)
            cached.write_text(json.dumps(historical,ensure_ascii=False,indent=2)+'\n')
    if cached.exists():
        result = json.loads(cached.read_text())
        if (directory/'prompt.sha256').read_text() != digest:
            saved_prompt = directory/'prompt.txt'
            if not saved_prompt.is_file():
                raise ValueError('refusing stale native output')
            original = saved_prompt.read_text()
            if hashlib.sha256(original.encode()).hexdigest() != (directory/'prompt.sha256').read_text() or _prompt_content(original) != _prompt_content(prompt):
                raise ValueError('refusing stale native output')
            prompt = original
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            key = budget.call_key(identity,prompt) if budget is not None else None
        if result.get('ok') is False and budget is None:
            retry = directory.with_name(directory.name+'-retry-'+datetime.now(ZoneInfo('America/Halifax')).date().isoformat())
            if '-retry-' not in directory.name:
                return native_turn(prompt,retry,task=task)
    elif budget is not None and budget.pending(key):
        result = read_native_result(directory.name,digest)
        if result is None:
            raise BudgetError('backfill outcome unknown; reservation retained, no request sent')
        cached.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        (directory/'prompt.sha256').write_text(digest)
    else:
        if budget is not None:
            budget.reserve(key,identity,prompt,directory)
        payload = base64.b64encode(prompt.encode()).decode()
        client = base64.b64encode((REPO/'lib/llm_deepseek.py').read_bytes()).decode()
        program = 'payload='+repr(payload)+'\nclient='+repr(client)+'\ntag='+repr(directory.name)+'\nmodel='+repr('deepseek-v4-flash' if budget is not None else None)+'\ntask='+repr(task)+'\n'+r'''
import socket,pathlib,json,base64,sys,importlib.util,asyncio
assert socket.gethostname()=='iZj1imk39yc55iZ'
sys.path.insert(0,'/root/OmniGraph-Vault')
r=pathlib.Path('/root/.vitax-local-automation/deepseek-turns')/tag
r.mkdir(mode=0o700,parents=True,exist_ok=True)
prompt=base64.b64decode(payload).decode()
import hashlib
digest=hashlib.sha256(prompt.encode()).hexdigest();saved=r/'prompt.sha256';f=r/'result.json'
if saved.exists():assert saved.read_text()==digest,'stale remote output'
if f.exists():
 print(f.read_text());sys.exit(0)
saved.write_text(digest);saved.chmod(0o600)
p=r/'client.py';raw=base64.b64decode(client);compile(raw,str(p),'exec');p.write_bytes(raw);p.chmod(0o600)
spec=importlib.util.spec_from_file_location('vitax_deepseek_client',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:
 result=asyncio.run(m.deepseek_complete_with_receipt(prompt,model=model,task=task));result['ok']=True
except Exception as e:
 import traceback
 error=r/'error.log';error.write_text(traceback.format_exc());error.chmod(0o600)
 result={'ok':False,'error_class':type(e).__name__,'text':getattr(e,'text',''),'usage':getattr(e,'usage',None)}
f=r/'result.json';f.write_text(json.dumps(result,ensure_ascii=False));f.chmod(0o600)
print(f.read_text())
'''
        # Use the installed producer environment, not an alternate provider.
        program = "import os,pathlib\np=pathlib.Path('/root/.vitax-local-automation/deepseek-runner-"+uuid.uuid4().hex+".py');p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_text("+repr(program)+");p.chmod(0o600)\nos.execv('/root/OmniGraph-Vault/venv-aim1/bin/python',['/root/OmniGraph-Vault/venv-aim1/bin/python',str(p)])\n"
        result = ssh_python(SOURCE_HOST,program,timeout=330)
        cached.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        (directory/'prompt.sha256').write_text(digest)
    (directory/'prompt.txt').write_text(prompt,encoding='utf-8')
    if budget is not None and budget.pending(key):
        budget.settle(key,result)
    if result.get('ok') is False:
        raise RuntimeError('DeepSeek completion failed: '+result['error_class'])
    from lib.llm_deepseek import validate_completion_receipt
    validate_completion_receipt(result['usage'], result['text'])
    output, usage = directory/'model-output.json', directory/'usage.json'
    output.write_text(result['text'],encoding='utf-8')
    usage.write_text(json.dumps(result['usage'],indent=2)+'\n')
    return output,usage


def merge_wiki_update(result, base, wiki_id):
    """Replace one explicitly selected Wiki while retaining its old evidence."""
    projection = json.loads(json.dumps(result['projection']))
    wiki = [k for k in projection['knowledge'] if k['kind']=='wiki']
    if len(wiki) != 1 or wiki[0]['knowledge_id'] != wiki_id:
        raise ValueError('generated Wiki does not match the explicit target')
    prior = next((k for k in base['knowledge'] if k['knowledge_id']==wiki_id), None)
    if prior:
        if prior['kind'] != 'wiki':
            raise ValueError('Wiki target must be an existing Wiki')
        wiki[0]['evidence_ids'] = list(dict.fromkeys(prior['evidence_ids'] + wiki[0]['evidence_ids']))
    retained = dict(base, knowledge=[k for k in base['knowledge'] if k['knowledge_id'] != wiki_id])
    return merge_accepted_articles({'projection':projection},[{'projection':retained}])['projection']


def _is_chinese(text, lang=None):
    """Prefer the recorded language; fall back to the main script, never one character."""
    if isinstance(lang, str) and lang.strip():
        return lang.strip().lower() in _CJK_LANGS
    text = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`", " ", text)
    text = re.sub(r"<(script|style|pre|code)\b[^>]*>[\s\S]*?</\1\s*>", " ", text, flags=re.I)
    text = re.sub(r"https?://[^\s<>]+|www\.[^\s<>]+|<[^>]+>", " ", text)
    cjk = sum(1 for character in text if '\u3400' <= character <= '\u9fff')
    words = len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", text))
    return cjk > words


def _article_task(body, lang=None):
    """Faithful translation for a foreign original; Chinese interpretation otherwise."""
    return 'article' if _is_chinese(body, lang) else 'translate'


def _slug(value):
    slug = re.sub(r'[^a-z0-9]+','-',str(value).lower()).strip('-')[:60]
    return slug or 'theme'


def _theme_id(cue):
    """Stable Wiki id; a digest keeps pure-CJK cues from collapsing to 'theme'."""
    slug = _slug(cue)
    return 'wiki-'+slug if slug != 'theme' else 'wiki-'+hashlib.sha256(cue.encode()).hexdigest()[:16]


def _theme_cues(article):
    """Existing content cues for one accepted article: entity names, then title keywords."""
    projection = article.get('projection', {})
    cues = {str(item['name']).lower() for item in projection.get('entities', []) if isinstance(item, dict) and item.get('name')}
    for item in projection.get('knowledge', []):
        if isinstance(item, dict):
            cues.update(token.lower() for token in _TITLE_TOKEN.findall(str(item.get('title', ''))))
    return cues


def theme_groups(articles, limit=WIKI_GROUPS, known=frozenset()):
    """Group accepted articles by the content cues they actually share.

    Deterministic: existing themes first, then by coverage. One source may start
    a useful theme page; no fixed topic and no arbitrary pairing.
    """
    cues = [_theme_cues(article) for article in articles]
    counts = {}
    for article_cues in cues:
        for cue in article_cues:
            counts[cue] = counts.get(cue, 0) + 1
    groups, used = [], set()
    for cue in sorted(counts, key=lambda name: (name not in known, -counts[name], name)):
        if len(groups) >= limit:
            break
        members = [index for index, article_cues in enumerate(cues) if cue in article_cues and index not in used]
        if not members:
            continue
        used.update(members)
        groups.append((cue, [articles[index] for index in members]))
    return groups


def _turn_identity(lane, revision, task, *, chunk=False):
    """Budget/cache identity is task-specific; a chunked translation is never the article."""
    return {'lane':lane,'source_revisions':[revision],'stage':'translate' if task == 'translate' else 'article',
            'recipe':'deepseek-v6-chunk' if chunk else 'deepseek-v6'}


def _knowledge_id(task, doc):
    """Knowledge id is task-specific: a translation never collides with an old interpretation."""
    suffix = doc['revision_id'][-12:]
    return f"{doc['doc_id']}-{suffix}-translation" if task == 'translate' else f"article-{doc['doc_id']}-{suffix}"


def _article_prompt(doc, task):
    payload = json.loads(_prompt({'schema_version':1,'documents':[doc]}))
    knowledge_id = _knowledge_id(task, doc)
    payload['output_schema']['knowledge'][0].update(knowledge_id=knowledge_id,kind='article',image_ids=[])
    if task == 'translate':
        payload['task'] += " Return exactly ONE faithful Chinese translation as the knowledge body. Use the exact knowledge_id in output_schema. Return image_ids:[] and empty entities and relations lists."
    else:
        payload['task'] += f" Return exactly ONE article interpretation. Use the exact knowledge_id in output_schema. Prefix entity/relation IDs with {doc['doc_id']}-{doc['revision_id'][-12:]}-. images is empty for this stored original. Return image_ids:[] in every knowledge item. Markdown images are not registered captures."
    return json.dumps(payload,ensure_ascii=False),knowledge_id


def _translate_document(doc, *, root, tag, budget, lane):
    """Chunk one original only when it exceeds a single request's text capacity."""
    from lib.llm_deepseek import assemble_chunks, chunk_text
    text = '\n\n'.join(paragraph['text'] for paragraph in doc['paragraphs'])
    chunks = chunk_text(text,max_chars=CHUNK_CHARS)
    identity = _turn_identity(lane, doc['revision_id'], 'translate', chunk=True) if budget is not None else None
    parts = []
    for index, chunk in enumerate(chunks, 1):
        prompt = json.dumps({'task':'Translate this part of the article into Chinese. Output only the translation text.','source':chunk},ensure_ascii=False)
        output, _ = native_turn(prompt,root/'native'/(tag+'-chunk-'+str(index)),budget=budget,identity=identity,task='translate_chunk')
        parts.append(output.read_text(encoding='utf-8'))
    return assemble_chunks(parts)


def _source_language(root, selection):
    """Recorded language and existing Chinese draft for one mirror record."""
    source, record = selection
    table = 'articles' if source == 'wechat' else 'rss_articles'
    with sqlite3.connect((root/'library/current/articles.sqlite').as_uri()+'?mode=ro',uri=True) as connection:
        row = connection.execute(f'SELECT lang,body_translated FROM {table} WHERE id=?',(record,)).fetchone()
    return (row[0],row[1]) if row else (None,None)


def _article_tag(task, doc):
    """Cache/tag key includes the task: an interpretation is never reused as a translation."""
    return 'deepseek-v6-'+task+'-'+doc['doc_id']+'-'+doc['revision_id'][-12:]


def produce(root, selection, *, budget=None, backfill_lane='K'):
    """One source packet, one independently publishable article."""
    root = Path(root)
    packet_dir = root/'packets'/uuid.uuid4().hex
    packet = build_source_packet(root/'library/current/articles.sqlite',[selection],packet_dir,source_receipt_path=root/'library/current/receipt.json')
    standardized = standardize_documents(json.loads(packet.read_text()),capture_root=packet_dir)
    doc = standardized['documents'][0]
    body = '\n\n'.join(paragraph['text'] for paragraph in doc['paragraphs'])
    lang, translated = _source_language(root, selection)
    task = _article_task(body, lang)
    tag = _article_tag(task, doc)
    path = root/'accepted'/tag
    cached = (path/'accepted.json').exists()
    if not cached:
        identity = _turn_identity(backfill_lane, doc['revision_id'], task) if budget is not None else None
        try:
            if task == 'translate' and _is_chinese(translated or ''):
                raw = json.dumps({'knowledge':[{'knowledge_id':_knowledge_id(task,doc),'kind':'article','language':'zh','title':doc['title'],'body':translated}],'entities':[],'relations':[]},ensure_ascii=False)
                output = root/'native'/tag/'reused.json';output.parent.mkdir(parents=True,mode=0o700,exist_ok=True);output.write_text(raw,encoding='utf-8')
                usage = None
                cached = True
            elif task == 'translate' and len(body) > CHUNK_CHARS:
                chinese = _translate_document(doc,root=root,tag=tag,budget=budget,lane=backfill_lane)
                raw = json.dumps({'knowledge':[{'knowledge_id':_knowledge_id(task,doc),'kind':'article','language':'zh','title':doc['title'],'body':chinese}],'entities':[],'relations':[]},ensure_ascii=False)
                output = root/'native'/tag/'assembled.json';output.parent.mkdir(parents=True,mode=0o700,exist_ok=True);output.write_text(raw,encoding='utf-8')
                usage = None
            else:
                prompt, _ = _article_prompt(doc, task)
                output, usage = native_turn(prompt,root/'native'/tag,budget=budget,identity=identity,task=task)
            if path.exists():
                path.rename(path.with_name(path.name+'-failed-'+uuid.uuid4().hex[:8]))
            run(packet,path,capture_root=packet_dir,model_output=output,model_receipt=usage,run_hermes=False,manual=None,sqlite_path=None,stage='article',source_id=doc['doc_id'])
        except ProductionError as exc:
            exc.source_revision = doc['revision_id']
            exc.source_task = task
            raise
    return path/'accepted.json', cached, task


def produce_wiki(root, selections, accepted_paths, base, wiki_id, topic, *, budget=None, backfill_lane='K'):
    """One theme Wiki update; a failed theme never blocks the articles."""
    root = Path(root)
    prior = next((k for k in base['knowledge'] if k['knowledge_id'] == wiki_id), None)
    if prior and prior['kind'] != 'wiki':
        raise ValueError('Wiki target must be an existing Wiki')
    packet_dir = root/'packets'/uuid.uuid4().hex
    packet = build_source_packet(root/'library/current/articles.sqlite',selections,packet_dir,source_receipt_path=root/'library/current/receipt.json')
    standardized = standardize_documents(json.loads(packet.read_text()),capture_root=packet_dir)
    fingerprints = [hashlib.sha256(p.read_bytes()).hexdigest() for p in accepted_paths]
    tag = 'deepseek-v6-wiki-'+hashlib.sha256((''.join(fingerprints)+wiki_id+json.dumps(prior,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()[:20]
    path = root/'accepted'/tag
    if not (path/'accepted.json').exists():
        context = [json.loads(p.read_text()) for p in accepted_paths]
        brief = [{'knowledge':x['projection']['knowledge'],'evidence':x['projection']['evidence']} for x in context]
        prompt = _prompt(standardized,brief)+f'\nUse knowledge_id {wiki_id}. The explicit topic is {topic}. Return one coherent cross-source Wiki, entities:[], relations:[].'
        if prior:
            prompt += '\nUpdate this existing Wiki. Preserve its useful content and add the new evidence. Prior Wiki: '+json.dumps({'title':prior['title'],'body':prior['body']},ensure_ascii=False)
        if budget is None:
            output,usage = native_turn(prompt,root/'native'/tag,task='wiki')
        else:
            identity = {'lane':backfill_lane,'source_revisions':[d['revision_id'] for d in standardized['documents']],'stage':'wiki','recipe':'deepseek-v6'}
            output,usage = native_turn(prompt,root/'native'/tag,budget=budget,identity=identity,task='wiki')
        if path.exists():
            path.rename(path.with_name(path.name+'-failed-'+uuid.uuid4().hex[:8]))
        run(packet,path,capture_root=packet_dir,model_output=output,model_receipt=usage,run_hermes=False,manual=None,sqlite_path=None,stage='wiki',accepted_articles=accepted_paths)
    return json.loads((path/'accepted.json').read_text())


def gap_queue(root, base, failed, limit=None):
    """Select by missing task, not by the row: a registered interpretation never masks a translation."""
    known = {document['revision_id'] for document in base['documents']}
    with sqlite3.connect((root/'library/current/articles.sqlite').as_uri()+'?mode=ro',uri=True) as connection:
        rows = connection.execute("""SELECT source,id,body,body_translated,lang FROM (
            SELECT 'wechat' AS source,id,body,body_translated,lang,layer2_verdict FROM articles
            UNION ALL SELECT 'rss' AS source,id,body,body_translated,lang,layer2_verdict FROM rss_articles
        ) WHERE layer2_verdict='ok' AND length(trim(coalesce(body,'')))>0
        ORDER BY row_number() OVER (PARTITION BY source ORDER BY id DESC),source DESC""").fetchall()
    selections = []
    for source, record, body, translated, lang in rows:
        task = _article_task(body, lang)
        revision = stored_revision(source, record, body)
        if task == 'article':
            if revision in known:            # this revision already has an interpretation
                continue
        elif _is_chinese(translated or ''):  # the mirror already carries a real Chinese translation
            continue
        if failed.get(revision+':deepseek-v6:'+task, 0) >= 2:
            continue
        selections.append((source, record))
        if limit is not None and len(selections) >= limit:
            break
    return selections


def stored_revision(source, record, body):
    content_hash = hashlib.sha256(_canonical_json([{'locator':'paragraph:1','text':body}])).hexdigest()
    return 'rev-'+hashlib.sha256(f'{source}-{record}:{content_hash}'.encode()).hexdigest()[:20]


def write_back_translation(selection, *, revision_id, body, database=SOURCE_DATABASE, host=SOURCE_HOST, history_dir="/root/.vitax-local-automation/deepseek-turns/writeback-history"):
    """Push a finished translation into the original DB field on the producer host.

    Reuses the existing SSH producer entry. The remote side recomputes the
    original-body revision and only writes when it still matches ``revision_id``,
    so a changed original is never overwritten by a stale result. Free of model
    cost; it shares the caller's refresh lock and 100-yuan ledger, no new budget.
    """
    source, record = selection
    table = 'articles' if source == 'wechat' else 'rss_articles'
    import inspect
    classifier = inspect.getsource(_is_chinese)
    program = ('import re\n_CJK_LANGS='+repr(_CJK_LANGS)+'\n'+classifier+'\nhistory_dir='+repr(str(history_dir))+'\n'+'database='+repr(str(database))+'\norigin='+repr(source)+'\ntable='+repr(table)+'\nrecord='+repr(int(record))+'\nexpected='+repr(str(revision_id))+'\nbody='+repr(body)+'\n'+r'''
import json,hashlib,sqlite3,pathlib
def content_hash(text): return hashlib.sha256(json.dumps([{'locator':'paragraph:1','text':text}],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
def revision(text): return 'rev-'+hashlib.sha256((origin+'-'+str(record)+':'+content_hash(text)).encode()).hexdigest()[:20]
con=sqlite3.connect(database);con.execute('PRAGMA busy_timeout=5000')
try:
 row=con.execute('SELECT body,body_translated,translated_lang FROM '+table+' WHERE id=?',(record,)).fetchone()
 if row is None or not isinstance(row[0],str) or not row[0].strip():
  print(json.dumps({'written':False,'reason':'no-original-body'}))
 elif revision(row[0])!=expected:
  print(json.dumps({'written':False,'reason':'original-changed'}))
 elif _is_chinese(row[1] or '',row[2]):
  print(json.dumps({'written':False,'reason':'existing-translation'}))
 else:
  if row[1]:
   old={'source':origin,'record_id':record,'revision_id':expected,'body_translated':row[1],'translated_lang':row[2]}
   raw=json.dumps(old,ensure_ascii=False,sort_keys=True).encode('utf-8')
   directory=pathlib.Path(history_dir);directory.mkdir(parents=True,mode=0o700,exist_ok=True)
   saved=directory/(origin+'-'+str(record)+'-'+hashlib.sha256(raw).hexdigest()+'.json')
   if not saved.exists():
    with saved.open('xb') as stream: stream.write(raw)
    saved.chmod(0o600)
  cursor=con.execute('UPDATE '+table+' SET body_translated=?,translated_lang=? WHERE id=? AND body=? AND body_translated IS ? AND translated_lang IS ?',(body,'zh',record,row[0],row[1],row[2]))
  written=cursor.rowcount
  con.commit()
  if written!=1: print(json.dumps({'written':False,'reason':'original-changed'}))
  else: print(json.dumps({'written':True,'field':'body_translated'}))
finally: con.close()
''')
    return ssh_python(host, program, timeout=30)


def refresh(root, base_database, *, selections=None, mirror_only=False, use_existing_snapshot=False, wiki_id="wiki-harness", backfill=False, backfill_lane='K', queue=DEFAULT_QUEUE):
    if backfill and (mirror_only or backfill_lane not in ('K','D')):
        raise BudgetError('backfill requires lane K or D and no mirror-only run')
    root = Path(root).absolute();root.mkdir(parents=True,mode=0o700,exist_ok=True)
    # ponytail: one updater lock; parallel producers need separate source leases first.
    with (root/'refresh.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # The normal paid entry shares the same ledger and UNKNOWN recovery as backfill.
        budget = None if mirror_only else BackfillBudget(root,lock)
        started = datetime.now(ZoneInfo('America/Halifax'))
        if not use_existing_snapshot:
            refresh_library(root)
        today = started.date().isoformat()
        marker = root/'production-day.json'
        failed_file = root/'production-failures.json'
        failed = json.loads(failed_file.read_text()) if failed_file.exists() else {}
        current = root/'public/current'
        base = _export_public_dto(current/'public.sqlite' if current.exists() else Path(base_database))
        pending_file = root/'pending-wikis.json'
        pending = json.loads(pending_file.read_text()) if pending_file.exists() else {}
        batch, abort = None, None
        if not mirror_only and (pending or backfill or not marker.exists() or json.loads(marker.read_text()).get('day') != today):
            remaining = 0
            if not selections:
                candidates = gap_queue(root, base, failed)
                selections = candidates[:queue]
                remaining = len(candidates) - len(selections)
            if selections or pending:
                # Count an attempted day before any model turn; failures never cause hourly rebilling.
                if not backfill:
                    marker.write_text(json.dumps({'day':today,'status':'attempting','selections':[list(s) for s in selections]})+'\n')
                accepted, errors, first_error, reused = [], [], None, 0
                pushed = {'pushed':0,'skipped':0,'failed':0}
                for selection in selections:
                    try:
                        path, cached, task = produce(root, selection, budget=budget, backfill_lane=backfill_lane)
                    except ProductionError as exc:
                        # A bad article never blocks the rest; only a provider or budget abort stops the batch.
                        revision = getattr(exc,'source_revision',None)
                        if revision:
                            key = revision+':deepseek-v6:'+getattr(exc,'source_task','article')
                            failed[key] = failed.get(key,0)+1
                            failed_file.write_text(json.dumps(failed,indent=2)+'\n')
                        errors.append({'selection':list(selection),'error_class':type(exc).__name__})
                        if first_error is None:
                            first_error = exc
                        continue
                    except Exception as exc:
                        # Provider/budget abort: stop paying, but keep every already-accepted article.
                        abort = exc
                        break
                    accepted.append((selection, path))
                    reused += int(cached)
                    if task == 'translate':
                        try:
                            article = json.loads(path.read_text())
                            chinese = next((item['body'] for item in article['projection']['knowledge'] if item['kind'] == 'article'), None)
                            if chinese:
                                result = write_back_translation(selection, revision_id=article['projection']['documents'][0]['revision_id'], body=chinese)
                                pushed['pushed' if result.get('written') else 'skipped'] += 1
                        except Exception:
                            pushed['failed'] += 1
                wiki_error, themes, release_id = None, 0, None
                try:
                    if accepted or pending:
                        projection = merge_accepted_articles({'projection':json.loads(json.dumps(base))},[{'projection':json.loads(p.read_text())['projection']} for _,p in accepted])['projection']
                        articles = [json.loads(path.read_text()) for _, path in accepted]
                        for topic, members in theme_groups(articles):
                            theme_id = _theme_id(topic)
                            entry = pending.setdefault(theme_id, {'topic':topic, 'members':[]})
                            for member in members:
                                selection, path = accepted[articles.index(member)]
                                saved = {'selection':list(selection), 'accepted':str(path)}
                                if saved not in entry['members']:
                                    entry['members'].append(saved)
                        pending_file.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n')
                        completed = []
                        if abort is None:
                            for theme_id, entry in list(pending.items())[:WIKI_GROUPS]:
                                group = entry['members'][:WIKI_SOURCES]
                                paths = [Path(member['accepted']) for member in group]
                                try:
                                    wiki = produce_wiki(root,[tuple(member['selection']) for member in group],paths,projection,theme_id,entry['topic'],budget=budget,backfill_lane=backfill_lane)
                                    projection = merge_wiki_update(wiki,projection,theme_id)
                                    completed.append((theme_id, group))
                                    themes += 1
                                except (BudgetError, RuntimeError) as exc:
                                    wiki_error = type(exc).__name__
                                    abort = exc
                                    break
                                except (ProductionError, ValueError) as exc:
                                    wiki_error = type(exc).__name__
                        release_id = 'release-local-'+uuid.uuid4().hex[:16]
                        projection['release_id'] = release_id
                        projection['published_at'] = datetime.now(ZoneInfo('America/Halifax')).isoformat()
                        output = root/'public/releases'/release_id;output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        source = root/'public'/('projection-'+release_id+'.json')
                        source.write_text(json.dumps(projection,ensure_ascii=False,indent=2)+'\n')
                        build_release(source,output)
                        promote_release(output,current)
                        for theme_id, group in completed:
                            pending[theme_id]['members'] = [member for member in pending[theme_id]['members'] if member not in group]
                            if not pending[theme_id]['members']:
                                del pending[theme_id]
                        pending_file.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n')
                except Exception as exc:
                    if not backfill:
                        marker.write_text(json.dumps({'day':today,'status':'failed','selections':[list(s) for s in selections],'error_class':type(exc).__name__})+'\n')
                    raise
                if (accepted or themes or not selections) and abort is None:
                    if not backfill:
                        marker.write_text(json.dumps({'day':today,'status':'published','release_id':release_id,'provider':'deepseek','wiki_themes':themes,'wiki_error':wiki_error,'selections':[list(s) for s,_ in accepted]})+'\n')
                else:
                    if abort is None:
                        abort = first_error or ProductionError('no article accepted')
                    # The day is counted and the partial result is kept; the raise happens after status.json.
                    if not backfill:
                        marker.write_text(json.dumps({'day':today,'status':'failed','release_id':release_id,'selections':[list(s) for s,_ in accepted] or [list(s) for s in selections],'error_class':type(abort).__name__})+'\n')
                batch = {'input':len(selections),'reused':reused,'accepted':len(accepted),'failed':len(errors),'remaining':remaining,
                         'wiki_themes':themes,'wiki_pending':sum(len(entry['members']) for entry in pending.values()),'wiki_error':wiki_error,'write_back':pushed,'aborted':type(abort).__name__ if abort else None,'errors':errors}
                batch['elapsed_seconds'] = (datetime.now(ZoneInfo('America/Halifax'))-started).total_seconds()
        state = {'checked_at':datetime.now(ZoneInfo('America/Halifax')).isoformat(),'library':str(root/'library/current'),'public':str(current),'production':json.loads(marker.read_text()) if marker.exists() else None}
        if budget is not None:
            state['backfill_budget'] = budget.summary()
        if batch is not None:
            state['batch'] = batch
        (root/'status.json').write_text(json.dumps(state,indent=2)+'\n')
        if abort is not None:
            raise abort
        return state


def recover_projection(root, candidate, output):
    """Repair inline closure from saved source banks; never select, generate or write back."""
    from vitax.production import _citations
    from vitax.knowledge import body_evidence_ids
    root = Path(root)
    projection = json.loads(Path(candidate).read_text())
    evidence = {item['evidence_id']:item for item in projection['evidence']}
    artifacts = {}
    for path in (root/'accepted').glob('*/accepted.json'):
        saved = json.loads(path.read_text())
        for item in saved['projection']['knowledge']:
            artifacts.setdefault(item['knowledge_id'], path.parent)
    retained, failures = [], []
    for item in projection['knowledge']:
        missing = [key for key in body_evidence_ids(item['body']) if key not in evidence]
        try:
            extra = []
            if missing:
                directory = artifacts.get(item['knowledge_id'])
                if directory is None:
                    raise ProductionError('saved source bank missing')
                standardized = json.loads((directory/'standardized.json').read_text())
                locators = {(doc['revision_id'], paragraph['locator']):paragraph['text'] for doc in standardized['documents'] for paragraph in doc['paragraphs']}
                _, extra, _ = _citations([{'citation_id':key} for key in missing], locators)
            for entry in extra:
                evidence[entry['evidence_id']] = entry
            item['evidence_ids'] = list(dict.fromkeys(item['evidence_ids'] + body_evidence_ids(item['body'])))
            retained.append(item)
        except ProductionError as exc:
            failures.append({'knowledge_id':item['knowledge_id'], 'error':str(exc)})
    projection['knowledge'] = retained
    projection['evidence'] = list(evidence.values())
    _validate_projection(projection)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(projection,ensure_ascii=False,indent=2)+'\n')
    return {'candidate':str(candidate), 'output':str(output), 'knowledge':len(retained), 'failures':failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--base-database')
    parser.add_argument('--recover-projection')
    parser.add_argument('--recovery-output')
    parser.add_argument('--select',action='append')
    parser.add_argument('--wiki-id',default='wiki-harness')
    parser.add_argument('--mirror-only',action='store_true')
    parser.add_argument('--use-existing-snapshot',action='store_true')
    parser.add_argument('--backfill',action='store_true')
    parser.add_argument('--backfill-lane',choices=('K','D'),default='K')
    parser.add_argument('--queue',type=int,default=DEFAULT_QUEUE,help='gap-queue size; 50 is the batch default')
    args = parser.parse_args()
    if args.recover_projection:
        if not args.recovery_output:
            parser.error('--recovery-output is required for recovery')
        with (Path(args.root)/'refresh.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            print(json.dumps(recover_projection(args.root,args.recover_projection,args.recovery_output)))
        return
    if not args.base_database:
        parser.error('--base-database is required for refresh')
    selections = [(p.split(':',1)[0],int(p.split(':',1)[1])) for p in args.select] if args.select else None
    print(json.dumps(refresh(args.root,args.base_database,selections=selections,mirror_only=args.mirror_only,use_existing_snapshot=args.use_existing_snapshot,wiki_id=args.wiki_id,backfill=args.backfill,backfill_lane=args.backfill_lane,queue=args.queue)))


if __name__=='__main__':
    main()
