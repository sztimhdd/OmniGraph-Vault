"""The existing public build/promotion path owns inline citation closure."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from vitax.knowledge import KnowledgeError, KnowledgeReader, build
from vitax.production import merge_accepted_articles
from scripts.refresh_vitax_local import promote_release


A='evidence-'+'a'*20
B='evidence-'+'b'*20
UNKNOWN='evidence-ee30a0a92978511ce97a'


def projection():
    return {'schema_version':1,'release_id':'release-test','published_at':'2026-10-04T20:00:00Z',
            'documents':[{'revision_id':'rev-a','doc_id':'doc-a','title':'Source A',
                          'source_url':'https://example.test/a','source_published_at':None,
                          'fetched_at':None,'visibility':'public'}],
            'evidence':[{'evidence_id':i,'revision_id':'rev-a','locator':'paragraph:1',
                         'quote':'Exact approved quote '+i,'visibility':'public'} for i in (A,B)],
            'knowledge':[{'knowledge_id':'wiki-test','kind':'wiki','title':'Wiki',
                          'body':'合法旧引用（'+A+'）。','evidence_ids':[A],'visibility':'public'}],
            'entities':[],'relations':[]}


def package(root, data, *, mutate=None):
    root.mkdir()
    build(data,root/'public.sqlite')
    if mutate is not None:
        with sqlite3.connect(root/'public.sqlite') as c:mutate(c)
    (root/'site').mkdir();(root/'site/index.html').write_text('offline synthetic site')
    entries=[{'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
             for name in ('public.sqlite','site/index.html')]
    (root/'manifest.json').write_text(json.dumps({'schema_version':1,'release_id':data['release_id'],'files':entries}))


def test_unknown_inline_id_blocks_build_without_creating_a_database(tmp_path):
    p=projection();p['knowledge'][0]['body']='中文引用'+UNKNOWN+'。'
    with pytest.raises(KnowledgeError,match=UNKNOWN):build(p,tmp_path/'bad.sqlite')
    assert not (tmp_path/'bad.sqlite').exists()


def test_known_inline_id_reaches_panel_without_changing_body_input_or_old_links(tmp_path):
    p=projection();p['knowledge'][0]['body']+='中文'+B+'，再引用（'+B+'）。'
    extras=['evidence-'+c*20 for c in ('c','d','e')]
    for eid in extras:
        p['evidence'].append({'evidence_id':eid,'revision_id':'rev-a','locator':'paragraph:1',
                             'quote':'Already public '+eid,'visibility':'public'})
        p['knowledge'][0]['body']+='（'+eid+'）。'
    original=deepcopy(p);build(p,tmp_path/'known.sqlite')
    assert p==original
    with KnowledgeReader(tmp_path/'known.sqlite') as reader:
        item=reader.read_knowledge('wiki-test')['knowledge']
        assert item['body']==original['knowledge'][0]['body']
        assert item['evidence_ids']==[A,B,*extras]
        assert reader.read_evidence(B)['evidence']['quote']=='Exact approved quote '+B


def test_inline_reference_cannot_make_private_evidence_public(tmp_path):
    p=projection();p['evidence'][1]['visibility']='private';p['knowledge'][0]['body']+='（'+B+'）。'
    with pytest.raises(KnowledgeError,match=B):build(p,tmp_path/'private.sqlite')
    assert p['evidence'][1]['visibility']=='private'


def test_reference_uses_full_approved_merged_projection_not_only_wiki_citations(tmp_path):
    wiki=projection();wiki['evidence']=wiki['evidence'][:1];wiki['knowledge'][0]['body']+='（'+B+'）。'
    article=projection();article['evidence']=article['evidence'][1:]
    article['knowledge']=[{'knowledge_id':'article-test','kind':'article','title':'Article',
                           'body':'已获准文章','evidence_ids':[B],'visibility':'public'}]
    merged=merge_accepted_articles({'projection':wiki},[{'projection':article}])['projection']
    build(merged,tmp_path/'merged.sqlite')
    with KnowledgeReader(tmp_path/'merged.sqlite') as reader:
        assert reader.read_knowledge('wiki-test')['knowledge']['evidence_ids']==[A,B]


def test_unknown_inline_id_in_old_shaped_package_blocks_promotion_and_keeps_current(tmp_path):
    p=projection();prior=tmp_path/'prior';package(prior,p);current=tmp_path/'current';promote_release(prior,current)
    candidate=tmp_path/'candidate';bad=projection();bad['release_id']='release-bad'
    package(candidate,bad,mutate=lambda c:c.execute('UPDATE knowledge SET body=?',('引用'+UNKNOWN,)))
    with pytest.raises(KnowledgeError,match=UNKNOWN):promote_release(candidate,current)
    assert current.resolve()==prior.resolve()


def test_valid_inline_id_without_persisted_panel_link_blocks_promotion(tmp_path):
    p=projection();prior=tmp_path/'prior';package(prior,p);current=tmp_path/'current';promote_release(prior,current)
    p['release_id']='release-unlinked';p['knowledge'][0]['body']+='（'+B+'）。'
    candidate=tmp_path/'unlinked'
    package(candidate,p,mutate=lambda c:c.execute('DELETE FROM knowledge_evidence WHERE evidence_id=?',(B,)))
    with pytest.raises(KnowledgeError,match='panel'):promote_release(candidate,current)
    assert current.resolve()==prior.resolve()


def test_public_builder_rejects_unknown_before_any_site_build(tmp_path,monkeypatch):
    from scripts.build_vitax_release import build_release,ReleaseError
    import scripts.build_vitax_release as builder
    def forbidden(*args,**kwargs):raise AssertionError('inline validation must run before site build')
    monkeypatch.setattr(builder,'_build_site',forbidden)
    p=projection();p['knowledge'][0]['body']+='（'+UNKNOWN+'）。';source=tmp_path/'source.json'
    source.write_text(json.dumps(p))
    with pytest.raises((KnowledgeError,ReleaseError),match=UNKNOWN):
        build_release(source,tmp_path/'candidate')
