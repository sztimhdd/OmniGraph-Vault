"""Shared K/D budget reserves before transport and retains unknown outcomes."""
from contextlib import contextmanager
import fcntl
import hashlib
import json

import pytest


@pytest.fixture(autouse=True)
def no_real_remote_cache_reads(monkeypatch):
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job,'read_native_result',lambda *a,**kw:None)


@contextmanager
def held(root):
    from vitax.backfill_budget import BackfillBudget
    root.mkdir(parents=True, exist_ok=True)
    with (root/'refresh.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield BackfillBudget(root, lock)


def identity(lane='K', revision='revision-1', stage='article'):
    return {'lane':lane,'source_revisions':[revision],'recipe':'deepseek-v6','stage':stage}


def result(request='request-1', prompt=100000, output=1000, *, split=True, ok=True):
    usage = {'receipt_type':'deepseek-chat.v1','provider':'deepseek','model':'deepseek-flash',
             'requested_model':'deepseek-v4-flash','request_id':request,'api_calls':1,
             'failed':False,'finish_reason':'stop','prompt_tokens':prompt,
             'completion_tokens':output,'total_tokens':prompt+output,
             'output_sha256':hashlib.sha256(b'result').hexdigest()}
    if split:
        usage.update(prompt_cache_hit_tokens=prompt//2, prompt_cache_miss_tokens=prompt-prompt//2)
    return {'ok':ok,'text':'result','usage':usage}


def test_peak_reservation_actual_usage_settlement_and_shared_k_d_restart(tmp_path):
    with held(tmp_path) as budget:
        key=budget.call_key(identity(),'prompt')
        budget.reserve(key, identity(), 'prompt', tmp_path/'native'/'one')
        assert budget.summary()['reserved_fen']==220
        budget.settle(key,result())
        # 50000 hit * 0.04 + 50000 miss * 2 + 1000 output * 8 = ¥0.110.
        assert budget.summary()['settled_upper_bound_fen']==11
        assert budget.summary()['available_fen']==9989
        assert key==budget.call_key(identity('D'),'prompt')
    with held(tmp_path) as restarted:
        assert restarted.summary()['settled_upper_bound_fen']==11
        assert restarted.pending(key)


def test_duplicate_request_id_is_settled_once_and_unknown_cannot_reserve_twice(tmp_path):
    from vitax.backfill_budget import BudgetError
    with held(tmp_path) as budget:
        for n in (1,2):
            i=identity(revision=str(n));key=budget.call_key(i,str(n))
            budget.reserve(key,i,str(n),tmp_path/'native'/str(n));budget.settle(key,result())
        assert budget.summary()['settled_upper_bound_fen']==11
        key=budget.call_key(identity(),'unknown');budget.reserve(key,identity(),'unknown',tmp_path/'native'/'unknown')
    with held(tmp_path) as restarted:
        assert restarted.summary()['reserved_fen']==220
        with pytest.raises(BudgetError):restarted.reserve(key,identity(),'unknown',tmp_path/'native'/'unknown')
        with pytest.raises(BudgetError):restarted.settle(key,{'ok':False,'usage':None,'text':''})
        assert restarted.summary()['reserved_fen']==220


def test_missing_cache_breakdown_uses_uncached_upper_bound_and_binds_request(tmp_path):
    from vitax.backfill_budget import BudgetError
    with held(tmp_path) as budget:
        key=budget.call_key(identity(),'x');budget.reserve(key,identity(),'x',tmp_path/'native'/'x')
        budget.settle(key,result(split=False))
        assert budget.summary()['settled_upper_bound_fen']==21
        other=budget.call_key(identity(),'y');budget.reserve(other,identity(),'y',tmp_path/'native'/'y')
        with pytest.raises(BudgetError):budget.settle(other,result(prompt=200000))
        assert budget.summary()['reserved_fen']==220


def test_real_native_entry_insufficient_balance_and_historical_cache_make_zero_requests(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    from vitax.backfill_budget import BudgetError
    calls=[]
    monkeypatch.setattr(job,'ssh_python',lambda *a,**kw:calls.append(a) or result())
    with held(tmp_path) as budget:
        for n in range(45):
            i=identity(revision=str(n));key=budget.call_key(i,str(n));budget.reserve(key,i,str(n),tmp_path/'native'/str(n))
            budget.settle(key,result(request=str(n),prompt=1048576,output=12000,split=False))
        assert budget.summary()['available_fen']==100
        with pytest.raises(BudgetError):job.native_turn('new',tmp_path/'native'/'new',budget=budget,identity=identity())
        cached=tmp_path/'native'/'cached';cached.mkdir()
        (cached/'native-result.json').write_text(json.dumps(result(request='historical')))
        (cached/'prompt.sha256').write_text(hashlib.sha256(b'cached').hexdigest())
        assert job.native_turn('cached',cached,budget=budget,identity=identity())[0].is_file()
        assert budget.summary()['settled_upper_bound_fen']==9900
    assert calls==[]


def test_unknown_native_result_restart_reads_cache_without_second_generation(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    from vitax.backfill_budget import BudgetError
    calls=[]
    def transport(*args,**kwargs):
        calls.append(args)
        raise RuntimeError('synthetic disconnect after request dispatch')
    monkeypatch.setattr(job,'ssh_python',transport)
    directory=tmp_path/'native'/'one'
    with held(tmp_path) as budget:
        with pytest.raises(RuntimeError):job.native_turn('prompt',directory,budget=budget,identity=identity())
        assert budget.summary()['reserved_fen']==220
    reads=[]
    def missing(*args,**kwargs):reads.append(args);return None
    monkeypatch.setattr(job,'read_native_result',missing)
    with held(tmp_path) as budget:
        with pytest.raises(BudgetError):job.native_turn('prompt',directory,budget=budget,identity=identity('D'))
        assert budget.summary()['reserved_fen']==220
    monkeypatch.setattr(job,'read_native_result',lambda *a,**kw:result())
    with held(tmp_path) as budget:
        assert job.native_turn('prompt',directory,budget=budget,identity=identity('D'))[0].is_file()
        assert budget.summary()['reserved_fen']==0
        assert budget.summary()['settled_upper_bound_fen']==11
    assert len(calls)==1 and len(reads)==1


def test_successful_generation_stays_charged_when_product_acceptance_fails(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job,'ssh_python',lambda *a,**kw:result())
    with held(tmp_path) as budget:
        output,_=job.native_turn('prompt',tmp_path/'native'/'one',budget=budget,identity=identity())
        assert output.read_text()=='result'
        with pytest.raises(job.ProductionError):raise job.ProductionError('synthetic invalid model product')
        assert budget.summary()['settled_upper_bound_fen']==11


def test_real_refresh_backfill_charges_before_product_error_and_leaves_daily_owner_marker(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    from tests.unit.test_vitax_local_articles import mirror
    from tests.unit.test_vitax_api import _projection
    from vitax.knowledge import build
    root=tmp_path/'runtime';(root/'library').mkdir(parents=True)
    mirror(root/'library/current')
    base=tmp_path/'base.sqlite';build(_projection(),base)
    marker=root/'production-day.json';marker.write_text(json.dumps({'day':'2000-01-01','status':'published','selections':[['wechat',9],['rss',8]]}))
    before=marker.read_bytes();calls=[]
    def transport(*args,**kwargs):calls.append(args);return result()
    monkeypatch.setattr(job,'ssh_python',transport)
    # Real packet -> prompt -> native budget -> real product JSON validation.
    with pytest.raises(job.ProductionError):
        job.refresh(root,base,selections=[('wechat',1)],use_existing_snapshot=True,backfill=True)
    assert marker.read_bytes()==before
    with held(root) as budget:
        assert budget.summary()['settled_upper_bound_fen']==11
        assert budget.summary()['reserved_fen']==0
    assert len(calls)==1
    daily=tmp_path/'daily';(daily/'library').mkdir(parents=True);mirror(daily/'library/current')
    job.refresh(daily,base,use_existing_snapshot=True,mirror_only=True)
    assert not (daily/'backfill-budget.json').exists()


def test_known_truncated_generation_is_charged_without_retrying_failed_cache(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    failed=result(ok=False);failed['usage']['finish_reason']='length';failed['error_class']='ValueError'
    calls=[]
    monkeypatch.setattr(job,'ssh_python',lambda *a,**kw:calls.append(a) or failed)
    with held(tmp_path) as budget:
        for _ in range(2):
            with pytest.raises(RuntimeError):
                job.native_turn('prompt',tmp_path/'native'/'one',budget=budget,identity=identity())
        assert budget.summary()['settled_upper_bound_fen']==11
        assert budget.summary()['reserved_fen']==0
    assert len(calls)==1


def test_unknown_stage_cannot_be_resubmitted_with_a_changed_prompt(tmp_path):
    from vitax.backfill_budget import BudgetError
    with held(tmp_path) as budget:
        first=identity();first['source_revisions']=['revision-1','revision-2']
        other=identity('D');other['source_revisions']=['revision-2','revision-1']
        original=budget.call_key(first,'original')
        budget.reserve(original,first,'original',tmp_path/'native'/'original')
        changed=budget.call_key(other,'changed')
        with pytest.raises(BudgetError):
            budget.reserve(changed,other,'changed',tmp_path/'native'/'changed')
        assert budget.summary()['reserved_fen']==220


def test_remote_historical_cache_without_local_copy_is_free(tmp_path,monkeypatch):
    from scripts import refresh_vitax_local as job
    monkeypatch.setattr(job,'read_native_result',lambda *a,**kw:result(request='historical-remote'))
    def forbidden(*args,**kwargs):raise AssertionError('must not submit generation for remote cache')
    monkeypatch.setattr(job,'ssh_python',forbidden)
    with held(tmp_path) as budget:
        assert job.native_turn('prompt',tmp_path/'native'/'remote',budget=budget,identity=identity())[0].is_file()
        assert budget.summary()['settled_upper_bound_fen']==0
        assert budget.summary()['reserved_fen']==0
