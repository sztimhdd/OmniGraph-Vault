"""T4 pacing tests: consecutive DeepSeek batches in run()'s loop wait ~2 s.

Perf plan task T4 (perf(classify)): the real DeepSeek batch loop in
``batch_classify_kol.run()`` fired consecutive batches back-to-back with no
gap.  Contract under test:

  - classifier="deepseek" with N batches: a fixed ~2 s pause
    (DEEPSEEK_BATCH_PACE) precedes every batch AFTER the first, so the
    inter-batch gap is never zero.
  - No sleep before the first batch and none after the last (a single-batch
    topic pays zero pacing cost).
  - A failed batch aborts the topic without an orphan trailing sleep.
  - classifier="gemini" semantics are untouched: its existing
    GEMINI_CLASSIFY_SLEEP still fires once before the loop, not per batch.

Sleeps are asserted via monkeypatched ``time.sleep`` (same seam as
test_image_pipeline / test_rss_fetch) — never a real 2 s wall-clock wait.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Defuse import-time API-key coupling BEFORE importing the module — same
# pattern as test_classify_batch_truncation.py / test_classify_multitopic_argparse.py.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

import batch_classify_kol  # noqa: E402  (import after env seed is intentional)

# ---------------------------------------------------------------------------
# Schema — mirrors batch_classify_kol.init_db() PLUS the two columns the
# topic-v2 bridge (2026-08-11) UPDATEs at the end of run(): layer1_verdict /
# layer1_prompt_version.  Fresh init_db() DDL predates that migration, so
# dry_run=False against a bare init_db copy crashes on the bridge UPDATE.
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
    scanned_at TEXT DEFAULT (datetime('now', 'localtime')),
    layer1_verdict TEXT,
    layer1_prompt_version TEXT
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


def _seed_db(db_file: Path, n: int) -> None:
    """Seed a tmp DB with one account and n unclassified articles."""
    conn = sqlite3.connect(str(db_file))
    conn.executescript(_SCHEMA_DDL)
    conn.execute("INSERT INTO accounts (name, fakeid) VALUES ('TestAccount', 'fake001')")
    for i in range(n):
        conn.execute(
            "INSERT INTO articles (account_id, title, url, digest) VALUES (1, ?, ?, ?)",
            (f"Article {i}", f"http://example.com/{i}", f"digest {i}"),
        )
    conn.commit()
    conn.close()


def _drive_run(monkeypatch, tmp_path, n: int, batch_size: str, classifier: str):
    """Run run() against n seeded articles with the classify LLM faked.

    Records an ordered event log: ("classify", abs_offset) whenever the
    classify seam is invoked and ("sleep", seconds) whenever time.sleep is
    called inside batch_classify_kol.  Returns the event log.
    """
    db_file = tmp_path / "kol_scan_pace.db"
    _seed_db(db_file, n)

    monkeypatch.setattr(batch_classify_kol, "DB_PATH", db_file)
    monkeypatch.setattr(
        batch_classify_kol, "init_db", lambda: sqlite3.connect(str(db_file))
    )
    monkeypatch.setattr(batch_classify_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_classify_kol, "get_deepseek_api_key", lambda: "dummy-key")
    monkeypatch.setenv("KOL_CLASSIFY_BATCH_SIZE", batch_size)

    events: list[tuple] = []

    def fake_classify_batch(titles, digests, topic, min_depth, api_key, abs_offset):
        events.append(("classify", abs_offset))
        return [
            {"index": abs_offset + i, "depth_score": 2, "relevant": True, "reason": "ok"}
            for i in range(len(titles))
        ]

    def fake_gemini(prompt):
        events.append(("classify", 0))
        # Legacy gemini branch never re-bases indices; one item is enough for
        # run()'s cls_by_idx lookups to stay collision-free across batches.
        return [{"index": 0, "depth_score": 2, "relevant": True, "reason": "ok"}]

    monkeypatch.setattr(batch_classify_kol, "_classify_batch", fake_classify_batch)
    monkeypatch.setattr(batch_classify_kol, "_call_gemini", fake_gemini)
    monkeypatch.setattr(
        batch_classify_kol.time, "sleep", lambda seconds: events.append(("sleep", seconds))
    )

    batch_classify_kol.run(topic="NLP", min_depth=2, classifier=classifier, dry_run=False)
    return events


# ---------------------------------------------------------------------------
# Test 1 — decisive: consecutive DeepSeek batches are paced ~2 s apart
# ---------------------------------------------------------------------------

def test_consecutive_deepseek_batches_wait_about_2s(monkeypatch, tmp_path) -> None:
    """250 articles @ batch 100 → 3 DeepSeek batches with two pacing sleeps.

    Event order must be classify(0) → sleep → classify(100) → sleep →
    classify(200): the pause sits between batches, never before the first and
    never as an orphan after the last.
    """
    assert batch_classify_kol.DEEPSEEK_BATCH_PACE == 2.0, (
        "T4 pins a fixed ~2 s inter-batch pace; got "
        f"{batch_classify_kol.DEEPSEEK_BATCH_PACE!r}"
    )

    events = _drive_run(monkeypatch, tmp_path, n=250, batch_size="100", classifier="deepseek")

    assert events == [
        ("classify", 0),
        ("sleep", batch_classify_kol.DEEPSEEK_BATCH_PACE),
        ("classify", 100),
        ("sleep", batch_classify_kol.DEEPSEEK_BATCH_PACE),
        ("classify", 200),
    ], f"expected classify/sleep/classify/sleep/classify pacing; got {events}"


# ---------------------------------------------------------------------------
# Test 2 — single-batch topic pays zero pacing cost
# ---------------------------------------------------------------------------

def test_single_deepseek_batch_has_no_pacing_sleep(monkeypatch, tmp_path) -> None:
    """50 articles @ batch 100 → exactly one DeepSeek batch, zero sleeps."""
    events = _drive_run(monkeypatch, tmp_path, n=50, batch_size="100", classifier="deepseek")

    assert events == [("classify", 0)], (
        f"a single-batch topic must not sleep at all; got {events}"
    )


# ---------------------------------------------------------------------------
# Test 3 — failed batch aborts without an orphan trailing sleep
# ---------------------------------------------------------------------------

def test_failed_deepseek_batch_no_orphan_sleep(monkeypatch, tmp_path) -> None:
    """Batch 2 returns None → run() aborts the topic; no sleep after the failure."""
    events: list[tuple] = []

    db_file = tmp_path / "kol_scan_pace.db"
    _seed_db(db_file, 150)  # 2 batches @ 100

    monkeypatch.setattr(batch_classify_kol, "DB_PATH", db_file)
    monkeypatch.setattr(
        batch_classify_kol, "init_db", lambda: sqlite3.connect(str(db_file))
    )
    monkeypatch.setattr(batch_classify_kol, "load_env", lambda: None)
    monkeypatch.setattr(batch_classify_kol, "get_deepseek_api_key", lambda: "dummy-key")
    monkeypatch.setenv("KOL_CLASSIFY_BATCH_SIZE", "100")

    call_no = [0]

    def fake_classify_batch(titles, digests, topic, min_depth, api_key, abs_offset):
        call_no[0] += 1
        events.append(("classify", abs_offset))
        if call_no[0] == 2:
            return None  # second batch fails → run() aborts the topic
        return [
            {"index": abs_offset + i, "depth_score": 2, "relevant": True, "reason": "ok"}
            for i in range(len(titles))
        ]

    monkeypatch.setattr(batch_classify_kol, "_classify_batch", fake_classify_batch)
    monkeypatch.setattr(
        batch_classify_kol.time, "sleep", lambda seconds: events.append(("sleep", seconds))
    )

    batch_classify_kol.run(topic="NLP", min_depth=2, classifier="deepseek", dry_run=False)

    assert events == [
        ("classify", 0),
        ("sleep", batch_classify_kol.DEEPSEEK_BATCH_PACE),
        ("classify", 100),
    ], f"no sleep may follow the failed batch; got {events}"


# ---------------------------------------------------------------------------
# Test 4 — Gemini semantics unchanged (one 5 s sleep before the loop only)
# ---------------------------------------------------------------------------

def test_gemini_classifier_keeps_single_preloop_sleep(monkeypatch, tmp_path) -> None:
    """classifier=gemini: GEMINI_CLASSIFY_SLEEP once, before the loop — not per batch."""
    events = _drive_run(monkeypatch, tmp_path, n=50, batch_size="100", classifier="gemini")

    assert events == [("sleep", batch_classify_kol.GEMINI_CLASSIFY_SLEEP), ("classify", 0)], (
        f"gemini must keep exactly one pre-loop sleep and no inter-batch pacing; got {events}"
    )
