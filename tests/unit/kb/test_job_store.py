"""Unit tests for kb/services/job_store.py — in-memory async-job dict.

Coverage matrix (kb-3-06 PLAN Task 1 behavior #7):
    1. new_job returns 12-char hex id with initial status='running' / result=None
    2. update_job mutates fields; get_job returns the merged record
    3. get_job for unknown id returns None
    4. concurrent update_job calls do not lose updates (threading.Lock works)

Skill(skill="writing-tests", args="Real concurrent.futures.ThreadPoolExecutor — multiple workers calling update_job with different keys; final dict must reflect every update. No mocks.")
"""
from __future__ import annotations

import importlib
import re
from concurrent.futures import ThreadPoolExecutor

import pytest


def _reload_job_store():
    import kb.services.job_store as js

    importlib.reload(js)
    return js


def test_new_job_returns_12_char_hex_with_running_status() -> None:
    js = _reload_job_store()
    jid = js.new_job()
    assert isinstance(jid, str)
    assert len(jid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", jid)
    rec = js.get_job(jid)
    assert rec is not None
    assert rec["status"] == "running"
    assert rec["result"] is None
    assert rec["error"] is None


def test_update_job_merges_fields() -> None:
    js = _reload_job_store()
    jid = js.new_job()
    js.update_job(jid, status="done", result="hello")
    rec = js.get_job(jid)
    assert rec is not None
    assert rec["status"] == "done"
    assert rec["result"] == "hello"
    # Non-updated fields remain.
    assert rec["error"] is None


def test_get_job_unknown_returns_none() -> None:
    js = _reload_job_store()
    assert js.get_job("does_not_exist") is None


def test_concurrent_update_job_thread_safe() -> None:
    js = _reload_job_store()
    jid = js.new_job()

    def writer(key: str) -> None:
        # Each worker writes a unique key so we can detect lost updates.
        js.update_job(jid, **{key: True})

    keys = [f"flag_{i}" for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(writer, keys))
    rec = js.get_job(jid)
    assert rec is not None
    for k in keys:
        assert rec.get(k) is True
