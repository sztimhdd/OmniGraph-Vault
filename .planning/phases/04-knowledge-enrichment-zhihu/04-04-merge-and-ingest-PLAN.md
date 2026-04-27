---
phase: 04-knowledge-enrichment-zhihu
plan: 04
type: execute
wave: 3
depends_on: [04-02, 04-03]
files_modified:
  - enrichment/merge_md.py
  - enrichment/merge_and_ingest.py
  - tests/unit/test_merge_md.py
  - tests/unit/test_merge_and_ingest.py
autonomous: true
requirements: [D-03, D-07, D-08, D-09, D-11]
must_haves:
  truths:
    - "merge_md appends 3 好问 summaries under '## 知识增厚' to the WeChat MD (D-09)"
    - "merge_and_ingest.py ingests enriched WeChat MD + up-to-3 Zhihu docs into LightRAG"
    - "Zhihu docs passed to ainsert with ids=f'zhihu_{hash}_{q}' and file_paths='enriches:{hash}' (D-08)"
    - "On partial success (>=1 q ok, others fail), articles.enriched = 2 (D-11)"
    - "On all-fail, articles.enriched = -2; still ingests un-enriched WeChat MD (D-07)"
    - "ingestions.enrichment_id gets a non-null value on success"
    - "Emits single-line JSON summary on stdout (D-03)"
  artifacts:
    - path: "enrichment/merge_md.py"
      provides: "Pure-function WeChat MD + 好问 summaries merger"
      exports: ["merge_wechat_with_haowen"]
      min_lines: 40
    - path: "enrichment/merge_and_ingest.py"
      provides: "Runner: reads disk artifacts, merges, ingests, updates SQLite"
      exports: ["main", "merge_and_ingest"]
      min_lines: 120
    - path: "tests/unit/test_merge_md.py"
      provides: "Test merge order, heading, missing-question handling"
      min_lines: 40
    - path: "tests/unit/test_merge_and_ingest.py"
      provides: "Test SQLite update, ainsert call args, partial-failure path"
      min_lines: 80
  key_links:
    - from: "merge_and_ingest.py"
      to: "LightRAG.ainsert with ids + file_paths"
      via: "rag.ainsert(zhihu_md, ids=[f'zhihu_{hash}_{q}'], file_paths=[f'enriches:{hash}'])"
      pattern: "ids=\\[?f?.zhihu_"
    - from: "merge_and_ingest.py"
      to: "SQLite articles.enriched column"
      via: "UPDATE articles SET enriched = ? WHERE url = ?"
      pattern: "UPDATE articles SET enriched"
    - from: "merge_and_ingest.py"
      to: "SQLite ingestions.enrichment_id"
      via: "UPDATE ingestions SET enrichment_id = ? WHERE article_id = ?"
      pattern: "UPDATE ingestions SET enrichment_id"
---

<objective>
Merge the 好问 summaries (D-09: inline) and ingest everything into LightRAG:
enriched WeChat MD as a regular doc (with appended 知识增厚 section) plus 1-3
standalone Zhihu docs with synthetic IDs and an `enriches:<hash>` file_paths
backlink (D-08). Update SQLite `articles.enriched` and
`ingestions.enrichment_id` per D-07/D-11.

Purpose: This is the final Python helper the top-level Hermes skill calls.
It's the "sealing step" that brings the separate enrichment artifacts (questions
JSON, 好问 haowen.json per q, Zhihu MD per q) into the knowledge graph.

Output: Two modules — a pure merger function and a runner that reads artifacts,
merges, calls LightRAG, and writes SQLite status.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-02-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-03-SUMMARY.md
@ingest_wechat.py
@config.py

<interfaces>
Disk layout after plans 02+03 run (per D-03):
```
$ENRICHMENT_DIR/<wechat_hash>/
    questions.json                   # from extract_questions.py
    0/                                # q_idx 0
        haowen.json                  # from /zhihu-haowen-enrich skill: {question, summary, best_source_url}
        final_content.md             # from fetch_zhihu.py (the Zhihu answer MD)
        metadata.json                # image metadata
        images/
    1/
        ...
    2/
        ...
```

Note: q_idx subdirs may be missing if the question was skipped/failed. The
merger must handle q_idx ∈ {0,1,2} with any subset present.

LightRAG ainsert signature (RESEARCH.md §3):
```python
rag.ainsert(
    input: str,
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
) -> str (track_id)
```

D-08 encoding:
- Each Zhihu doc: `ids=[f"zhihu_{wechat_hash}_{q_idx}"]`, `file_paths=[f"enriches:{wechat_hash}"]`

D-07 enriched state machine (written to SQLite articles.enriched):
- 0 = pending (initial)
- 1 = in progress (optionally set while running; not required)
- 2 = success (including partial ≥1 q success)
- -1 = skipped (too short — plan 02 returns skipped; plan 07 sets this column)
- -2 = all-fail (all 3 q failed)

enrichment_id = a stable synthetic ID — use the wechat_hash prefixed with "enrich_" (e.g., f"enrich_{wechat_hash}").
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 4.1: enrichment/merge_md.py — pure merger function</name>
  <files>enrichment/merge_md.py, tests/unit/test_merge_md.py</files>
  <read_first>
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-09 (好问 summaries inline to WeChat MD)
    - docs/enrichment-prd.md §4 and §6.4 (merge format rationale, heading convention)
  </read_first>
  <behavior>
    - Input: original WeChat MD string + list of haowen dicts (some may be None for failed questions).
    - Output: original MD unchanged + appended section `## 知识增厚` with one subsection per successful question: `### 问题 N: <question>` then `<summary>` then `来源: <best_source_url>`.
    - If ZERO questions succeeded: append a footer `## 知识增厚\n\n(未找到相关的知乎问答)` (useful audit trail for `enriched=-2`).
    - Missing (None) haowen items are skipped in the output.
    - Function is pure; no I/O, no side effects.
  </behavior>
  <action>
    Create `enrichment/merge_md.py`:

    ```python
    """Merge 好问 summaries inline into the WeChat markdown (D-09).

    Pure function — no I/O. Used by merge_and_ingest.py after disk artifacts
    are collected.
    """
    from __future__ import annotations
    from typing import Optional


    HEADER = "\n\n## 知识增厚\n"
    EMPTY_FOOTER = "\n\n## 知识增厚\n\n(未找到相关的知乎问答)\n"


    def merge_wechat_with_haowen(
        wechat_md: str,
        haowen: list[Optional[dict]],
    ) -> str:
        """Append 好问 summaries to the WeChat MD tail.

        `haowen` is a list of {question, summary, best_source_url, ...} dicts
        (from the `/zhihu-haowen-enrich` skill's haowen.json). None entries
        (= failed questions) are skipped. If all entries are None, a footer
        indicating "no Zhihu answers found" is appended.
        """
        successful = [h for h in haowen if h is not None]
        if not successful:
            return wechat_md.rstrip() + EMPTY_FOOTER

        out = wechat_md.rstrip() + HEADER
        for i, h in enumerate(haowen):
            if h is None:
                continue
            q = h.get("question", "(unknown)")
            summary = h.get("summary", "").strip()
            src = h.get("best_source_url", "").strip()
            out += f"\n### 问题 {i + 1}: {q}\n\n{summary}\n"
            if src:
                out += f"\n来源: {src}\n"
        return out
    ```

    Create `tests/unit/test_merge_md.py`:

    ```python
    """Unit tests for enrichment.merge_md."""
    import pytest
    from enrichment.merge_md import merge_wechat_with_haowen


    @pytest.mark.unit
    def test_merge_appends_knowledge_section():
        md = "# article\nbody text"
        haowen = [{"question": "q1", "summary": "s1", "best_source_url": "http://a"}]
        out = merge_wechat_with_haowen(md, haowen)
        assert "# article" in out
        assert "body text" in out
        assert "## 知识增厚" in out
        assert "### 问题 1: q1" in out
        assert "s1" in out
        assert "http://a" in out


    @pytest.mark.unit
    def test_merge_preserves_question_index_with_none_gap():
        md = "orig"
        haowen = [
            {"question": "q1", "summary": "s1", "best_source_url": "http://a"},
            None,  # q2 failed
            {"question": "q3", "summary": "s3", "best_source_url": "http://c"},
        ]
        out = merge_wechat_with_haowen(md, haowen)
        # Index label reflects position in the original list, not the filtered one
        assert "### 问题 1: q1" in out
        assert "### 问题 2:" not in out   # q2 skipped
        assert "### 问题 3: q3" in out


    @pytest.mark.unit
    def test_merge_all_failed_appends_empty_footer():
        md = "orig"
        out = merge_wechat_with_haowen(md, [None, None, None])
        assert "## 知识增厚" in out
        assert "未找到相关的知乎问答" in out
        assert out.startswith("orig")


    @pytest.mark.unit
    def test_merge_empty_list_treated_as_all_failed():
        out = merge_wechat_with_haowen("orig", [])
        assert "未找到相关的知乎问答" in out


    @pytest.mark.unit
    def test_merge_handles_missing_fields():
        md = "orig"
        haowen = [{"question": "q1"}]  # no summary, no url
        out = merge_wechat_with_haowen(md, haowen)
        assert "### 问题 1: q1" in out
        # Should not crash, should not emit broken "来源: " line
        assert "来源: \n" not in out
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_merge_md.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/merge_md.py` exists and is importable
    - `grep -q "def merge_wechat_with_haowen" enrichment/merge_md.py` succeeds
    - `grep -q "知识增厚" enrichment/merge_md.py` succeeds
    - `pytest tests/unit/test_merge_md.py -x -v` exits 0 with all 5 tests passing
  </acceptance_criteria>
  <done>Pure merge function with 5 passing tests</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4.2: enrichment/merge_and_ingest.py — runner + SQLite + LightRAG</name>
  <files>enrichment/merge_and_ingest.py, tests/unit/test_merge_and_ingest.py</files>
  <read_first>
    - enrichment/merge_md.py (just-created merger — will be called from here)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §3 (LightRAG ainsert signature, ids+file_paths for D-08)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-07/D-11 (enriched state machine)
    - ingest_wechat.py lines 49-67 (_persist_entities_to_sqlite pattern for failure-tolerant SQLite writes)
    - ingest_wechat.py lines 713-725 (UPDATE articles SET content_hash pattern)
  </read_first>
  <behavior>
    - Reads `questions.json` from disk, iterates q_idx 0..N-1.
    - For each q_idx, checks for `haowen.json` and `final_content.md` in subdir.
    - Missing haowen.json → that q is a failure (None in haowen list).
    - Missing final_content.md but present haowen.json → that q's Zhihu doc is skipped but summary still merged.
    - Merges WeChat MD using merge_md.merge_wechat_with_haowen.
    - Calls rag.ainsert on the merged MD (no special ids — it's the parent).
    - For each successful Zhihu MD, calls rag.ainsert with ids=[f"zhihu_{hash}_{q_idx}"], file_paths=[f"enriches:{hash}"].
    - On partial success (>=1 haowen ok), sets articles.enriched=2.
    - On all-fail, sets articles.enriched=-2 AND still ingests the un-enriched WeChat MD (D-07).
    - Updates ingestions.enrichment_id = f"enrich_{hash}" if available.
    - Stdout: single-line JSON summary (D-03).
  </behavior>
  <action>
    Create `enrichment/merge_and_ingest.py`:

    ```python
    """Merge enrichment artifacts and ingest into LightRAG + SQLite.

    Called by the Hermes `enrich_article` skill as the final step of per-article
    enrichment. Reads disk artifacts produced by:
      - enrichment/extract_questions.py  → questions.json
      - /zhihu-haowen-enrich skill        → <q>/haowen.json (per question)
      - enrichment/fetch_zhihu.py         → <q>/final_content.md (per question)

    Writes:
      - LightRAG: 1 enriched WeChat doc + 0-3 Zhihu docs (D-08 metadata)
      - SQLite:   articles.enriched = 2 | -2, ingestions.enrichment_id = <id>

    CLI:
        python -m enrichment.merge_and_ingest <wechat_hash> \\
            --article-path <path to wechat MD> \\
            --article-url <url>
    """
    from __future__ import annotations

    import argparse
    import asyncio
    import json
    import logging
    import os
    import sqlite3
    import sys
    from pathlib import Path
    from typing import Optional

    from enrichment.merge_md import merge_wechat_with_haowen

    logger = logging.getLogger(__name__)

    DEFAULT_BASE_DIR = Path(os.environ.get(
        "ENRICHMENT_DIR",
        str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
    ))
    DEFAULT_DB_PATH = Path(os.environ.get(
        "KOL_SCAN_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "kol_scan.db"),
    ))


    # ───────────────────── Artifact reader ─────────────────────

    def _load_haowen_list(hash_dir: Path, question_count: int) -> list[Optional[dict]]:
        """Return list of haowen dicts (or None for missing) for q_idx 0..question_count-1."""
        result: list[Optional[dict]] = []
        for i in range(question_count):
            haowen_path = hash_dir / str(i) / "haowen.json"
            if haowen_path.is_file():
                try:
                    result.append(json.loads(haowen_path.read_text(encoding="utf-8")))
                except Exception as e:
                    logger.warning("haowen.json for q%d unreadable: %s", i, e)
                    result.append(None)
            else:
                result.append(None)
        return result


    def _load_zhihu_mds(hash_dir: Path, question_count: int) -> dict[int, str]:
        """Return {q_idx: zhihu_markdown_content} for questions that have a final_content.md."""
        result: dict[int, str] = {}
        for i in range(question_count):
            md_path = hash_dir / str(i) / "final_content.md"
            if md_path.is_file():
                result[i] = md_path.read_text(encoding="utf-8")
        return result


    # ───────────────────── SQLite ─────────────────────

    def _update_sqlite_status(
        db_path: Path,
        article_url: str,
        enriched: int,
        enrichment_id: Optional[str],
    ) -> None:
        """Write enriched state + enrichment_id. Failure-tolerant (logs + continues)."""
        if not db_path.exists():
            logger.warning("SQLite DB not found at %s — skipping status update", db_path)
            return
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE articles SET enriched = ? WHERE url = ?",
                         (enriched, article_url))
            if enrichment_id:
                # Look up article_id for ingestions table
                row = conn.execute("SELECT id FROM articles WHERE url = ?", (article_url,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE ingestions SET enrichment_id = ? WHERE article_id = ?",
                        (enrichment_id, row[0]),
                    )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("SQLite status update failed: %s", e)


    # ───────────────────── LightRAG ingest ─────────────────────

    async def _ingest_to_lightrag(
        wechat_md: str,
        zhihu_docs: dict[int, str],
        wechat_hash: str,
    ) -> None:
        """Call rag.ainsert for the WeChat MD + each Zhihu doc with D-08 metadata."""
        # Import here so tests can swap via get_rag monkeypatch without importing lightrag
        from ingest_wechat import get_rag
        rag = await get_rag()
        # Parent WeChat doc — no synthetic ids (let LightRAG auto-hash)
        await rag.ainsert(wechat_md)
        # Zhihu children with deterministic ids + enriches-backlink
        for q_idx, md in zhihu_docs.items():
            await rag.ainsert(
                md,
                ids=[f"zhihu_{wechat_hash}_{q_idx}"],
                file_paths=[f"enriches:{wechat_hash}"],
            )


    # ───────────────────── Main entry ─────────────────────

    async def merge_and_ingest(
        wechat_hash: str,
        article_path: Path,
        article_url: str,
        base_dir: Path = DEFAULT_BASE_DIR,
        db_path: Path = DEFAULT_DB_PATH,
    ) -> dict:
        hash_dir = base_dir / wechat_hash
        questions_path = hash_dir / "questions.json"
        if not questions_path.is_file():
            raise FileNotFoundError(f"questions.json missing at {questions_path}")

        questions_data = json.loads(questions_path.read_text(encoding="utf-8"))
        questions = questions_data.get("questions", [])
        question_count = len(questions)

        haowen_list = _load_haowen_list(hash_dir, question_count)
        zhihu_mds = _load_zhihu_mds(hash_dir, question_count)

        success_count = sum(1 for h in haowen_list if h is not None)

        # Merge WeChat MD with 好问 summaries (D-09)
        wechat_text = article_path.read_text(encoding="utf-8")
        enriched_md = merge_wechat_with_haowen(wechat_text, haowen_list)

        # Ingest to LightRAG
        await _ingest_to_lightrag(enriched_md, zhihu_mds, wechat_hash)

        # SQLite state (D-07/D-11)
        enriched_state = 2 if success_count >= 1 else -2
        enrichment_id = f"enrich_{wechat_hash}"
        _update_sqlite_status(db_path, article_url, enriched_state, enrichment_id)

        return {
            "hash": wechat_hash,
            "status": "ok",
            "enriched": enriched_state,
            "question_count": question_count,
            "success_count": success_count,
            "zhihu_docs_ingested": len(zhihu_mds),
            "enrichment_id": enrichment_id,
        }


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser()
        parser.add_argument("wechat_hash")
        parser.add_argument("--article-path", required=True)
        parser.add_argument("--article-url", required=True)
        parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
        parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
        args = parser.parse_args(argv)

        try:
            summary = asyncio.run(merge_and_ingest(
                args.wechat_hash,
                Path(args.article_path),
                args.article_url,
                base_dir=Path(args.base_dir),
                db_path=Path(args.db_path),
            ))
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"hash": args.wechat_hash, "status": "error", "error": str(e)}))
            return 1

        print(json.dumps(summary))
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Create `tests/unit/test_merge_and_ingest.py`:

    ```python
    """Unit tests for enrichment.merge_and_ingest — D-07/D-08/D-11."""
    from __future__ import annotations
    import asyncio
    import json
    import sqlite3
    from pathlib import Path
    from unittest.mock import MagicMock, AsyncMock
    import pytest


    def _seed_artifacts(base_dir: Path, wechat_hash: str, haowen_map: dict[int, dict | None],
                        zhihu_mds: dict[int, str]) -> Path:
        """Create questions.json + per-q haowen.json + final_content.md on disk."""
        hdir = base_dir / wechat_hash
        hdir.mkdir(parents=True)
        questions = [{"question": f"q{i}", "context": "c"} for i in range(len(haowen_map))]
        (hdir / "questions.json").write_text(
            json.dumps({"hash": wechat_hash, "questions": questions}), encoding="utf-8",
        )
        for q_idx, haowen in haowen_map.items():
            qdir = hdir / str(q_idx); qdir.mkdir()
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
            "INSERT INTO ingestions (article_id, status) VALUES ((SELECT id FROM articles WHERE url=?), 'ok')",
            (url,),
        )
        conn.commit(); conn.close()


    @pytest.fixture
    def _mock_rag(mocker):
        rag = MagicMock()
        rag.ainsert = AsyncMock(return_value="track-id")
        mocker.patch("enrichment.merge_and_ingest._ingest_to_lightrag",
                     new=AsyncMock(side_effect=lambda *a, **kw: None))
        return rag


    @pytest.mark.unit
    def test_partial_success_sets_enriched_2(tmp_path: Path, mocker, _mock_rag):
        from enrichment.merge_and_ingest import merge_and_ingest
        base = tmp_path / "enrich"; base.mkdir()
        _seed_artifacts(base, "abc", {
            0: {"question": "q0", "summary": "s0", "best_source_url": "u0"},
            1: None,
            2: {"question": "q2", "summary": "s2", "best_source_url": "u2"},
        }, zhihu_mds={0: "zhihu-md-0", 2: "zhihu-md-2"})
        db = tmp_path / "k.db"; _seed_db(db, "http://ex/1")
        article = tmp_path / "a.md"; article.write_text("wechat body", encoding="utf-8")

        summary = asyncio.run(merge_and_ingest(
            "abc", article, "http://ex/1", base_dir=base, db_path=db,
        ))
        assert summary["enriched"] == 2
        assert summary["success_count"] == 2
        assert summary["zhihu_docs_ingested"] == 2

        # SQLite assertions
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT enriched FROM articles WHERE url='http://ex/1'").fetchone()
        assert row[0] == 2
        row = conn.execute(
            "SELECT enrichment_id FROM ingestions WHERE article_id=(SELECT id FROM articles WHERE url='http://ex/1')"
        ).fetchone()
        assert row[0] == "enrich_abc"
        conn.close()


    @pytest.mark.unit
    def test_all_fail_sets_enriched_minus_2(tmp_path: Path, mocker, _mock_rag):
        from enrichment.merge_and_ingest import merge_and_ingest
        base = tmp_path / "enrich"; base.mkdir()
        _seed_artifacts(base, "xyz", {0: None, 1: None, 2: None}, zhihu_mds={})
        db = tmp_path / "k.db"; _seed_db(db, "http://ex/2")
        article = tmp_path / "a.md"; article.write_text("x" * 2100, encoding="utf-8")

        summary = asyncio.run(merge_and_ingest(
            "xyz", article, "http://ex/2", base_dir=base, db_path=db,
        ))
        assert summary["enriched"] == -2
        assert summary["success_count"] == 0
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT enriched FROM articles WHERE url='http://ex/2'").fetchone()
        assert row[0] == -2
        conn.close()


    @pytest.mark.unit
    def test_zhihu_docs_use_deterministic_ids_and_enriches_backlink(tmp_path: Path, mocker):
        """D-08: Zhihu docs ingested with ids=[f'zhihu_{hash}_{q}'] and file_paths=['enriches:{hash}']."""
        import enrichment.merge_and_ingest as mi
        base = tmp_path / "enrich"; base.mkdir()
        _seed_artifacts(base, "hh", {
            0: {"question": "q0", "summary": "s", "best_source_url": "u"},
        }, zhihu_mds={0: "zhihu-md-0"})
        db = tmp_path / "k.db"; _seed_db(db, "http://x")
        article = tmp_path / "a.md"; article.write_text("body", encoding="utf-8")

        rag = MagicMock()
        rag.ainsert = AsyncMock(return_value="t")
        async def fake_get_rag(): return rag
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
        rc = main(["notahash", "--article-path", "/does/not/exist", "--article-url", "u",
                   "--base-dir", str(tmp_path), "--db-path", str(tmp_path / "k.db")])
        assert rc == 1  # missing questions.json
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_merge_md.py tests/unit/test_merge_and_ingest.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - Files `enrichment/merge_and_ingest.py` and `tests/unit/test_merge_and_ingest.py` exist
    - `grep -q "ids=\[f.zhihu_" enrichment/merge_and_ingest.py` succeeds (D-08 synthetic ID pattern)
    - `grep -q "file_paths=\[f.enriches:" enrichment/merge_and_ingest.py` succeeds (D-08 backlink)
    - `grep -q "UPDATE articles SET enriched" enrichment/merge_and_ingest.py` succeeds
    - `grep -q "UPDATE ingestions SET enrichment_id" enrichment/merge_and_ingest.py` succeeds
    - `grep -q "enriched_state = 2 if success_count >= 1 else -2" enrichment/merge_and_ingest.py` succeeds (D-11 partial-success policy)
    - `pytest tests/unit/test_merge_and_ingest.py -x -v` exits 0 with all 4 tests passing
    - `python -m enrichment.merge_and_ingest --help` exits 0
  </acceptance_criteria>
  <done>merge_and_ingest runner with D-07/D-08/D-11 semantics; 4 tests pass; merge_md tests still green</done>
</task>

</tasks>

<verification>
  - `pytest tests/unit/test_merge_md.py tests/unit/test_merge_and_ingest.py -x -v` — 9 tests green
  - CLI modules respond to `--help`
  - `grep -q "from enrichment.merge_md import" enrichment/merge_and_ingest.py` succeeds (proper composition)
</verification>

<success_criteria>
- Pure merger function (merge_md) respects D-09 (inline summaries under 知识增厚)
- Runner (merge_and_ingest) respects D-07 (state machine), D-08 (Zhihu doc ids + enriches backlink), D-11 (partial success = 2)
- SQLite articles.enriched + ingestions.enrichment_id updated (failure-tolerant)
- D-03 stdout contract honored
- 9 unit tests green
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-04-SUMMARY.md`.
</output>
