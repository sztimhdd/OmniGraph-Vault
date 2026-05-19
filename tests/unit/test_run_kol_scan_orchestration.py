"""Behavior-anchor regression tests for batch_ingest_from_spider.run().

Companion to T1-T5 in test_ingest_from_db_orchestration.py. ``run()`` is the
sister orchestrator that handles KOL scan -> classify -> ingest at
batch_ingest_from_spider.py L793-L1014 (~220 LOC). It meets the same three
in-scope signals as ``ingest_from_db`` (CLAUDE.md PRINCIPLE #7):

  (a) >300 LOC of nested batches (Phase 1 scan + Phase 2 filter + Phase 3 ingest)
  (b) silent broad ``except Exception`` handlers around external calls
      (per-account list_articles try/except continues with next account)
  (c) cost-or-correctness consequences (paid Apify spend, ghost successes,
      candidate-pool poisoning)

Anchor IDs:
    R1 - unknown account_filter early-return (no list_articles, no
         ingest_article, no summary/metrics file written)
    R2 - checkpoint-skip path: has_stage('text_ingest')=True writes
         status='skipped_ingested' and never calls ingest_article
    R3 - dry_run=True suppresses LightRAG init (get_rag never called)
         and stamps every summary entry with status='dry_run'
    R4 - finally block ALWAYS writes batch_timeout_metrics_*.json under
         PROJECT_ROOT/data even when the per-article loop raises

Style mirror: tests/unit/test_ingest_from_db_orchestration.py (same
monkeypatch pattern, same caplog basicConfig defence, same fixture reuse).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# Phase 5 cross-coupling defence -- set BEFORE any lib.* import chain pulls
# in lib.llm_deepseek (raises at import if DEEPSEEK_API_KEY unset).
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import pytest

import batch_ingest_from_spider as bi

from tests.unit._ingest_fixtures import mock_rag


# ---------------------------------------------------------------------------
# Shared run() patch stack
# ---------------------------------------------------------------------------


def _patch_run_env(
    monkeypatch,
    tmp_path: Path,
    *,
    fakeids: dict[str, str] | None = None,
    articles: list[dict] | None = None,
    has_stage_returns: bool = False,
    ingest_outcome: tuple[bool, float, bool] | Exception = (True, 1.0, True),
    rag: MagicMock | None = None,
) -> dict[str, object]:
    """Apply the standard run() mock stack and return the installed handles.

    Patches (all via monkeypatch so pytest auto-undoes after test):
        * batch_ingest_from_spider.kol_config              -> SimpleNamespace
        * batch_ingest_from_spider._load_hermes_env        -> no-op
        * batch_ingest_from_spider.PROJECT_ROOT            -> tmp_path
        * batch_ingest_from_spider.list_articles           -> MagicMock(articles)
        * batch_ingest_from_spider.has_stage               -> returns bool
        * batch_ingest_from_spider.get_article_hash        -> returns "hash-<url>"
        * batch_ingest_from_spider.ingest_article          -> AsyncMock
        * batch_ingest_from_spider.SLEEP_BETWEEN_ARTICLES  -> 0
        * batch_ingest_from_spider.RATE_LIMIT_SLEEP_ACCOUNTS -> 0
        * sys.modules["ingest_wechat"].get_rag             -> AsyncMock(rag)
        * logging.basicConfig                              -> no-op (caplog defence)

    Returns dict whose keys are: list_articles, ingest_article,
    get_rag, rag -- for .assert_called* introspection in tests.
    """
    fake_cfg = SimpleNamespace(
        FAKEIDS=dict(fakeids or {"AccountA": "fake123"}),
        TOKEN="t",
        COOKIE="c",
    )
    monkeypatch.setattr(bi, "kol_config", fake_cfg)
    monkeypatch.setattr(bi, "_load_hermes_env", lambda: None)
    monkeypatch.setattr(bi, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(bi, "SLEEP_BETWEEN_ARTICLES", 0)
    monkeypatch.setattr(bi, "RATE_LIMIT_SLEEP_ACCOUNTS", 0)

    list_mock = MagicMock(return_value=list(articles or []))
    monkeypatch.setattr(bi, "list_articles", list_mock)

    monkeypatch.setattr(bi, "has_stage", lambda h, s: has_stage_returns)
    monkeypatch.setattr(bi, "get_article_hash", lambda url: f"hash-{url}")

    if isinstance(ingest_outcome, Exception):
        ingest_mock = AsyncMock(side_effect=ingest_outcome)
    else:
        ingest_mock = AsyncMock(return_value=tuple(ingest_outcome))
    monkeypatch.setattr(bi, "ingest_article", ingest_mock)

    fake_rag = rag if rag is not None else mock_rag()
    fake_iw = MagicMock()
    fake_iw.get_rag = AsyncMock(return_value=fake_rag)
    monkeypatch.setitem(sys.modules, "ingest_wechat", fake_iw)

    # caplog defence: production calls logging.basicConfig(force=True) which
    # would remove pytest's caplog handler. No-op patch keeps caplog intact.
    monkeypatch.setattr(logging, "basicConfig", lambda *a, **kw: None)

    return {
        "list_articles": list_mock,
        "ingest_article": ingest_mock,
        "get_rag": fake_iw.get_rag,
        "rag": fake_rag,
    }


def _read_coldstart_summary(tmp_path: Path) -> list[dict]:
    """Read the single coldstart_run_*.json file written under tmp_path/data."""
    matches = list((tmp_path / "data").glob("coldstart_run_*.json"))
    assert len(matches) == 1, (
        f"expected exactly 1 coldstart_run_*.json under {tmp_path / 'data'}; "
        f"got {matches!r}"
    )
    return json.loads(matches[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# R1 - unknown account_filter early-return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_account_filter_early_returns(monkeypatch, tmp_path: Path):
    """Anchor R1: unknown account_filter triggers logger.error + early return.

    Production L808-L812: if account_filter is set and not present in
    kol_config.FAKEIDS, the function logs and returns BEFORE the scan loop,
    BEFORE any LightRAG init, and BEFORE the try/finally that writes the
    metrics + summary files. The contract is "no observable side effects":
    no list_articles call, no ingest_article call, no files written under
    PROJECT_ROOT/data.
    """
    handles = _patch_run_env(
        monkeypatch,
        tmp_path,
        fakeids={"TestAccount": "fake123"},
    )

    await bi.run(
        days_back=7,
        max_articles=5,
        dry_run=True,
        account_filter="DoesNotExist",
    )

    handles["list_articles"].assert_not_called()
    handles["ingest_article"].assert_not_called()
    handles["get_rag"].assert_not_called()

    data_dir = tmp_path / "data"
    if data_dir.exists():
        coldstart = list(data_dir.glob("coldstart_run_*.json"))
        metrics = list(data_dir.glob("batch_timeout_metrics_*.json"))
        assert coldstart == [], (
            f"early-return must not write coldstart_run_*.json; got {coldstart!r}"
        )
        assert metrics == [], (
            f"early-return must not write batch_timeout_metrics_*.json; got {metrics!r}"
        )


# ---------------------------------------------------------------------------
# R2 - checkpoint-skip writes 'skipped_ingested' without calling ingest_article
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_skip_writes_skipped_ingested(monkeypatch, tmp_path: Path):
    """Anchor R2: has_stage('text_ingest')=True short-circuits to summary.

    Production L907-L916: per-article loop computes ckpt_hash and checks
    has_stage. When the marker exists, the article gets a summary row with
    status='skipped_ingested' and the loop ``continue``s -- ingest_article
    must NOT be called for that article. Pins the cost-saving CKPT-03 path
    (re-running ingest after checkpoint set would waste vision $ and
    embedding quota).
    """
    handles = _patch_run_env(
        monkeypatch,
        tmp_path,
        fakeids={"AccountA": "fake123"},
        articles=[
            {
                "title": "T",
                "url": "https://mp.weixin.qq.com/s/test",
            },
        ],
        has_stage_returns=True,
    )

    await bi.run(
        days_back=7,
        max_articles=5,
        dry_run=True,
    )

    handles["ingest_article"].assert_not_called()

    summary = _read_coldstart_summary(tmp_path)
    skipped = [r for r in summary if r.get("status") == "skipped_ingested"]
    assert len(skipped) == 1, (
        f"expected exactly 1 status='skipped_ingested' row; got summary={summary!r}"
    )
    assert skipped[0]["url"] == "https://mp.weixin.qq.com/s/test"


# ---------------------------------------------------------------------------
# R3 - dry_run=True suppresses get_rag and stamps status='dry_run'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_skips_rag_init_and_stamps_dry_run(monkeypatch, tmp_path: Path):
    """Anchor R3: dry_run=True path must not initialize LightRAG.

    Production L867-L873: ``rag`` stays None when ``dry_run`` is True. The
    ``from ingest_wechat import get_rag`` line is inside the guarded block,
    so the import never runs and get_rag is never called. The per-article
    loop still calls ingest_article (which short-circuits on dry_run inside
    its own body), and every summary row is stamped status='dry_run'.

    Without topic_filter / exclude_topics, scanning_active=False so all
    listed articles pass through to the ingest loop unfiltered (L860-L862).
    """
    handles = _patch_run_env(
        monkeypatch,
        tmp_path,
        articles=[
            {"title": "T1", "url": "https://mp.weixin.qq.com/s/test1"},
            {"title": "T2", "url": "https://mp.weixin.qq.com/s/test2"},
        ],
        has_stage_returns=False,
    )

    await bi.run(
        days_back=7,
        max_articles=5,
        dry_run=True,
    )

    handles["get_rag"].assert_not_called()

    summary = _read_coldstart_summary(tmp_path)
    dry_run_rows = [r for r in summary if r.get("status") == "dry_run"]
    assert len(dry_run_rows) == 2, (
        f"expected 2 status='dry_run' rows; got summary={summary!r}"
    )
    urls = {r["url"] for r in dry_run_rows}
    assert urls == {
        "https://mp.weixin.qq.com/s/test1",
        "https://mp.weixin.qq.com/s/test2",
    }, f"unexpected urls in summary; got {urls!r}"


# ---------------------------------------------------------------------------
# R4 - finally always writes batch_timeout_metrics JSON, even on exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finally_writes_metrics_on_exception(monkeypatch, tmp_path: Path):
    """Anchor R4: finally block runs the BTIMEOUT-04 metrics emit even when
    the per-article loop raises.

    Production L967-L992: the try/finally wraps the entire ingest phase. The
    metrics emit at L975-L992 lives in the finally branch and writes
    batch_timeout_metrics_*.json under PROJECT_ROOT/data unconditionally.
    Pins the invariant that operator-visible metrics survive any in-loop
    exception -- regression of this contract would leave silent failures
    with no metrics artifact for forensic analysis.

    The test drives ingest_article to raise RuntimeError. The exception
    propagates past the finally (caught by pytest.raises) but the metrics
    file MUST still be on disk.
    """
    rag = mock_rag()
    handles = _patch_run_env(
        monkeypatch,
        tmp_path,
        articles=[
            {"title": "Boom", "url": "https://mp.weixin.qq.com/s/boom"},
        ],
        has_stage_returns=False,
        ingest_outcome=RuntimeError("mock failure"),
        rag=rag,
    )

    with pytest.raises(RuntimeError, match="mock failure"):
        await bi.run(
            days_back=7,
            max_articles=5,
            dry_run=False,
        )

    metrics_files = list((tmp_path / "data").glob("batch_timeout_metrics_*.json"))
    assert len(metrics_files) == 1, (
        f"finally block must write exactly 1 batch_timeout_metrics_*.json "
        f"under {tmp_path / 'data'}; got {metrics_files!r} -- regression "
        f"of BTIMEOUT-04 invariant"
    )

    # Sanity-check: the rag finalize_storages call also belongs to the
    # finally invariant (D-10.09 vision drain + flush).
    rag.finalize_storages.assert_called_once()
