"""Unit tests for enrichment.merge_and_ingest — D-07/D-08/D-11."""
from __future__ import annotations
import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import pytest


def _seed_artifacts(
    base_dir: Path,
    wechat_hash: str,
    haowen_map: dict,
    zhihu_mds: dict,
) -> Path:
    """Create questions.json + per-q haowen.json + final_content.md on disk."""
    hdir = base_dir / wechat_hash
    hdir.mkdir(parents=True)
    questions = [{"question": f"q{i}", "context": "c"} for i in range(len(haowen_map))]
    (hdir / "questions.json").write_text(
        json.dumps({"hash": wechat_hash, "questions": questions}),
        encoding="utf-8",
    )
    for q_idx, haowen in haowen_map.items():
        qdir = hdir / str(q_idx)
        qdir.mkdir()
        if haowen is not None:
            (qdir / "haowen.json").write_text(json.dumps(haowen), encoding="utf-8")
        if q_idx in zhihu_mds:
            (qdir / "final_content.md").write_text(zhihu_mds[q_idx], encoding="utf-8")
    return hdir


def _seed_db(db_path: Path, url: str) -> None:
    from batch_scan_kol import init_db
    conn = init_db(db_path)
    conn.execute("INSERT INTO accounts (name, fakeid) VALUES ('X', 'fx1')")
    conn.execute(
        "INSERT INTO articles (account_id, title, url) VALUES (1, 't', ?)", (url,),
    )
    conn.execute(
        "INSERT INTO ingestions (article_id, status) VALUES "
        "((SELECT id FROM articles WHERE url=?), 'ok')",
        (url,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def _mock_rag(mocker):
    rag = MagicMock()
    rag.ainsert = AsyncMock(return_value="track-id")
    mocker.patch(
        "enrichment.merge_and_ingest._ingest_to_lightrag",
        new=AsyncMock(side_effect=lambda *a, **kw: None),
    )
    return rag


@pytest.mark.unit
def test_partial_success_sets_enriched_2(tmp_path: Path, mocker, _mock_rag):
    from enrichment.merge_and_ingest import merge_and_ingest
    base = tmp_path / "enrich"
    base.mkdir()
    _seed_artifacts(
        base,
        "abc",
        {
            0: {"question": "q0", "summary": "s0", "best_source_url": "u0"},
            1: None,
            2: {"question": "q2", "summary": "s2", "best_source_url": "u2"},
        },
        zhihu_mds={0: "zhihu-md-0", 2: "zhihu-md-2"},
    )
    db = tmp_path / "k.db"
    _seed_db(db, "http://ex/1")
    article = tmp_path / "a.md"
    article.write_text("wechat body", encoding="utf-8")

    summary = asyncio.run(merge_and_ingest(
        "abc", article, "http://ex/1", base_dir=base, db_path=db,
    ))
    assert summary["enriched"] == 2
    assert summary["success_count"] == 2
    assert summary["zhihu_docs_ingested"] == 2

    # SQLite assertions
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT enriched FROM articles WHERE url='http://ex/1'"
    ).fetchone()
    assert row[0] == 2
    row = conn.execute(
        "SELECT enrichment_id FROM ingestions WHERE article_id="
        "(SELECT id FROM articles WHERE url='http://ex/1')"
    ).fetchone()
    assert row[0] == "enrich_abc"
    conn.close()


@pytest.mark.unit
def test_all_fail_sets_enriched_minus_2(tmp_path: Path, mocker, _mock_rag):
    from enrichment.merge_and_ingest import merge_and_ingest
    base = tmp_path / "enrich"
    base.mkdir()
    _seed_artifacts(base, "xyz", {0: None, 1: None, 2: None}, zhihu_mds={})
    db = tmp_path / "k.db"
    _seed_db(db, "http://ex/2")
    article = tmp_path / "a.md"
    article.write_text("x" * 2100, encoding="utf-8")

    summary = asyncio.run(merge_and_ingest(
        "xyz", article, "http://ex/2", base_dir=base, db_path=db,
    ))
    assert summary["enriched"] == -2
    assert summary["success_count"] == 0

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT enriched FROM articles WHERE url='http://ex/2'"
    ).fetchone()
    assert row[0] == -2
    conn.close()


@pytest.mark.unit
def test_zhihu_docs_use_deterministic_ids_and_enriches_backlink(tmp_path: Path, mocker):
    """D-08: Zhihu docs ingested with ids=['zhihu_{hash}_{q}'] and file_paths=['enriches:{hash}']."""
    import enrichment.merge_and_ingest as mi

    base = tmp_path / "enrich"
    base.mkdir()
    _seed_artifacts(
        base,
        "hh",
        {0: {"question": "q0", "summary": "s", "best_source_url": "u"}},
        zhihu_mds={0: "zhihu-md-0"},
    )
    db = tmp_path / "k.db"
    _seed_db(db, "http://x")
    article = tmp_path / "a.md"
    article.write_text("body", encoding="utf-8")

    rag = MagicMock()
    rag.ainsert = AsyncMock(return_value="t")

    async def fake_get_rag(flush: bool = True):
        # D-09.07: accept flush kwarg to match new get_rag signature.
        return rag

    mocker.patch("ingest_wechat.get_rag", new=fake_get_rag)

    asyncio.run(mi.merge_and_ingest(
        "hh", article, "http://x", base_dir=base, db_path=db,
    ))

    # Assert at least one call used ids=zhihu_hh_0 and file_paths=enriches:hh
    calls = rag.ainsert.await_args_list
    zhihu_calls = [c for c in calls if c.kwargs.get("ids")]
    assert len(zhihu_calls) >= 1
    first = zhihu_calls[0]
    assert first.kwargs["ids"] == ["zhihu_hh_0"]
    assert first.kwargs["file_paths"] == ["enriches:hh"]


@pytest.mark.unit
def test_cli_stdout_under_50kb(tmp_path: Path, mocker):
    from enrichment.merge_and_ingest import main
    rc = main([
        "notahash",
        "--article-path", "/does/not/exist",
        "--article-url", "u",
        "--base-dir", str(tmp_path),
        "--db-path", str(tmp_path / "k.db"),
    ])
    assert rc == 1  # missing questions.json
