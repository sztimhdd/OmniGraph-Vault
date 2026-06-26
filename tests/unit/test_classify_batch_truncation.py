"""Regression tests for the #70 DeepSeek finish_reason=length truncation bug.

Root cause (quick 260625-jv2 postmortem):
    batch_size=200 overflows DeepSeek max_tokens ceiling for dense topics
    (NLP 200-row response ~28000 chars).  The response comes back with
    ``finish_reason=length`` and JSON cut mid-stream.  The pre-fix
    fence-strip at batch_classify_kol:185-189 leaves the raw ``` prefix,
    causing ``json.loads`` to raise ``Expecting value: line 1 column 1``.
    ``_call_deepseek`` returns ``None``, and ``run()`` aborts the WHOLE
    topic — deterministic starvation on every cron fire.

Fix under test (quick 260626-fp5):
    1. ``_call_deepseek`` now returns the sentinel string ``"TRUNCATED"``
       on ``finish_reason=length`` instead of ``None``.
    2. New ``_classify_batch`` wraps ``_call_deepseek`` with adaptive halving:
       truncated slices are split in half recursively until success or
       len(titles) < MIN_BATCH.
    3. Each result dict's ``index`` is re-based to ``abs_offset + batch_index``
       so the pre-existing ``cls_by_idx`` consumer in ``run()`` is correct
       across split batches without any change.

These tests pin three observable contracts (NOT internal implementation shape):
  Test 1 — _call_deepseek returns "TRUNCATED" on finish_reason=length
  Test 2 — _classify_batch splits and yields abs-indexed flat results
  Test 3 (decisive regression) — run() writes ALL N rows to classifications
                                   even when the first batch truncates
"""
from __future__ import annotations

import os
import sqlite3
import unittest.mock as mock
from pathlib import Path

# Defuse import-time DEEPSEEK_API_KEY / GEMINI_API_KEY coupling BEFORE
# importing the module — same pattern as test_classify_multitopic_argparse.py.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

import batch_classify_kol  # noqa: E402  (import after env seed is intentional)

# ---------------------------------------------------------------------------
# DDL — copied verbatim from batch_classify_kol.init_db() so the tests run
# without hitting DB_PATH / init_db() directly (avoids filesystem coupling).
# Must stay in sync with the production schema; any new column addition to
# init_db() that run() touches must also appear here.
# ---------------------------------------------------------------------------
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    wechat_id TEXT,
    fakeid TEXT NOT NULL UNIQUE,
    tags TEXT,
    source TEXT,
    category TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    digest TEXT,
    update_time INTEGER,
    scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    topic TEXT NOT NULL,
    depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
    relevant INTEGER DEFAULT 0,
    excluded INTEGER DEFAULT 0,
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id, topic)
);
"""


def _make_deepseek_response(finish_reason: str, content: str = "") -> mock.MagicMock:
    """Build a mock requests.Response whose .json() matches DeepSeek's shape.

    Both ``choices[0]["finish_reason"]`` and ``choices[0]["message"]["content"]``
    are always present so the ``try`` branch in ``_call_deepseek`` never falls
    into the ``except`` path — the sentinel / parse-result logic is exercised.
    """
    resp = mock.MagicMock()
    resp.json.return_value = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": content},
            }
        ]
    }
    resp.raise_for_status.return_value = None
    return resp


def _make_valid_json_content(n: int, start_index: int = 0) -> str:
    """Return a JSON string representing n classification results starting at start_index."""
    import json
    items = [
        {"index": start_index + i, "depth_score": 2, "relevant": True, "reason": "test"}
        for i in range(n)
    ]
    return json.dumps(items)


# ---------------------------------------------------------------------------
# Test 1 — _call_deepseek returns "TRUNCATED" sentinel on finish_reason=length
# ---------------------------------------------------------------------------

def test_call_deepseek_returns_truncated_sentinel(monkeypatch) -> None:
    """finish_reason=length must return the string "TRUNCATED", not None.

    This pins the boundary between the network layer and the split logic —
    the sentinel drives _classify_batch's adaptive halving; returning None
    would abort the topic (the pre-fix bug behaviour).
    """
    truncated_resp = _make_deepseek_response(finish_reason="length", content='[{"index":0,')

    with mock.patch.object(batch_classify_kol.requests, "post", return_value=truncated_resp):
        result = batch_classify_kol._call_deepseek("any prompt", "dummy-key")

    assert result == "TRUNCATED", (
        f"_call_deepseek must return the string 'TRUNCATED' on finish_reason=length; "
        f"got {result!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — _classify_batch splits a truncated 50-title slice into 25+25
# ---------------------------------------------------------------------------

def test_classify_batch_splits_on_truncation(monkeypatch) -> None:
    """_classify_batch with 50 titles: first call (50) truncates → splits → 25+25 succeed.

    Verifies:
    - Total result length == 50 (all titles classified, no abort)
    - Indices are re-based correctly (first half 0..24, second half 25..49)
    - No index collision or gap
    """
    n = 50
    titles = [f"Title {i}" for i in range(n)]
    digests = ["" for _ in range(n)]

    call_count = [0]

    def fake_call_deepseek(prompt: str, api_key: str):
        call_count[0] += 1
        # First call is for all 50 — simulate truncation.
        if call_count[0] == 1:
            return "TRUNCATED"
        # Second call: first 25 — valid results with 0-based indices within the slice.
        if call_count[0] == 2:
            import json
            return json.loads(_make_valid_json_content(25, start_index=0))
        # Third call: second 25 — valid results with 0-based indices within the slice.
        if call_count[0] == 3:
            import json
            return json.loads(_make_valid_json_content(25, start_index=0))
        raise AssertionError(f"Unexpected call #{call_count[0]} to _call_deepseek")

    monkeypatch.setattr(batch_classify_kol, "_call_deepseek", fake_call_deepseek)

    result = batch_classify_kol._classify_batch(
        titles, digests, topic="NLP", min_depth=2, api_key="dummy-key", abs_offset=0
    )

    assert result is not None, "_classify_batch must not return None when split succeeds"
    assert len(result) == n, (
        f"_classify_batch must return {n} items after a successful 25+25 split; "
        f"got {len(result)}"
    )

    returned_indices = sorted(item["index"] for item in result)
    assert returned_indices == list(range(n)), (
        f"indices must be 0..{n-1} after re-basing; got {returned_indices}"
    )


# ---------------------------------------------------------------------------
# Test 3 — decisive regression: run() writes ALL N rows even when first batch
#           truncates (previously aborted the whole topic, leaving 0 rows)
# ---------------------------------------------------------------------------

def test_run_classifies_all_articles_on_truncation(monkeypatch, tmp_path) -> None:
    """run() with N=50 articles, batch_size=50: first DeepSeek call truncates,
    split into 25+25 succeeds → COUNT(*) of classifications for topic == 50.

    This is the decisive regression gate for #70: before the fix, run() called
    _call_deepseek directly; on TRUNCATED (then None) it hit the
    ``if result is None: ... return`` branch and wrote ZERO rows.  After the fix,
    the split path in _classify_batch recovers all 50 rows.
    """
    n = 50
    topic = "NLP"

    # --- Set up a real SQLite DB in tmp_path ---
    db_file = tmp_path / "kol_scan_test.db"
    conn_setup = sqlite3.connect(str(db_file))
    conn_setup.executescript(_SCHEMA_DDL)
    conn_setup.execute(
        "INSERT INTO accounts (name, fakeid) VALUES ('TestAccount', 'fake001')"
    )
    for i in range(n):
        conn_setup.execute(
            "INSERT INTO articles (account_id, title, url, digest) VALUES (1, ?, ?, ?)",
            (f"Article title {i}", f"http://example.com/{i}", f"digest {i}"),
        )
    conn_setup.commit()
    conn_setup.close()

    # --- Patch DB_PATH so init_db() / run() connect to our temp DB ---
    fake_db_path = mock.MagicMock()
    fake_db_path.exists.return_value = True
    fake_db_path.__str__ = mock.Mock(return_value=str(db_file))
    monkeypatch.setattr(batch_classify_kol, "DB_PATH", fake_db_path)

    # --- Patch env-overridable batch_size to 50 (one batch for 50 articles) ---
    monkeypatch.setenv("KOL_CLASSIFY_BATCH_SIZE", "50")

    # --- Patch load_env and get_deepseek_api_key so no file I/O ---
    monkeypatch.setattr(batch_classify_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_classify_kol, "get_deepseek_api_key", lambda: "dummy-key")

    # --- Patch _call_deepseek: first call (50 titles) → TRUNCATED;
    #     second (25) + third (25) calls → valid 0-based JSON results ---
    call_count = [0]

    def fake_call_deepseek(prompt: str, api_key: str):
        import json
        call_count[0] += 1
        if call_count[0] == 1:
            return "TRUNCATED"
        # Each half returns 25 items with 0-based indices (re-basing is done by
        # _classify_batch, not here).
        return json.loads(_make_valid_json_content(25, start_index=0))

    monkeypatch.setattr(batch_classify_kol, "_call_deepseek", fake_call_deepseek)

    # --- Run ---
    batch_classify_kol.run(topic=topic, min_depth=2, classifier="deepseek", dry_run=False)

    # --- Verify: ALL N articles must have a classification row ---
    conn_verify = sqlite3.connect(str(db_file))
    count = conn_verify.execute(
        "SELECT COUNT(*) FROM classifications WHERE topic=?", (topic,)
    ).fetchone()[0]
    conn_verify.close()

    assert count == n, (
        f"run() must write {n} classification rows for topic='{topic}' "
        f"even when the first 50-title batch returns finish_reason=length; "
        f"got {count} rows.  Pre-fix behaviour: 0 rows (whole topic aborted)."
    )
