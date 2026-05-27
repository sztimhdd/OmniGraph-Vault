---
phase: 05-pipeline-automation
plan: 00b
type: execute
wave: 0
depends_on: [05-00]
files_modified:
  - batch_ingest_from_spider.py
  - scripts/wave0b_submit_batch.py
  - scripts/wave0b_poll_and_ingest.py
  - tests/verify_wave0b_filter.py
autonomous: true
requirements: [D-06, D-10, D-11, D-12, D-13, D-14, D-15]
must_haves:
  truths:
    - "All 302 existing KOL articles are classified — `classifications` table is no longer empty"
    - "`batch_ingest_from_spider.py` accepts multiple keyword filters via `--topic-filter` (comma-separated OR multi-flag)"
    - "Filter `(keyword in {openclaw,hermes,agent,harness}) AND depth_score>=2` produces a non-empty subset"
    - "Submission uses Gemini Batch API if spike report says `batch_api_available: true`, else chunked sync fallback with RPM throttle"
    - "Filtered articles are ingested into LightRAG; existing dedup prevents re-ingest"
    - "Wave 0b is re-runnable as keyword scope grows (new keyword list + `--from-db` produces additional ingests, no collisions)"
    - "Wave 0b and Wave 0's 18-doc re-embed target DISJOINT article sets (see dedup_isolation note below); no collisions"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Multi-keyword `--topic-filter` support"
      contains: "comma"
    - path: "scripts/wave0b_submit_batch.py"
      provides: "Batch API submission (or sync fallback) for filtered subset"
      min_lines: 60
    - path: "scripts/wave0b_poll_and_ingest.py"
      provides: "Batch result polling + LightRAG ingest of classified articles"
      min_lines: 60
    - path: "tests/verify_wave0b_filter.py"
      provides: "SQL assertion: filtered subset count > 0 and matches keyword+depth predicate"
      contains: "depth_score >= 2"
  key_links:
    - from: "batch_classify_kol.py"
      to: "classifications table (previously empty)"
      via: "Gemini classifier with all 5 topic flags"
      pattern: "--topic Agent --topic LLM --topic RAG --topic NLP --topic CV"
    - from: "batch_ingest_from_spider.py"
      to: "LightRAG ainsert for filtered subset"
      via: "--from-db --topic-filter <keywords> --min-depth 2"
      pattern: "--topic-filter"
---

<objective>
Populate the empty `classifications` table over all 302 existing KOL articles, then ingest the keyword+depth-filtered subset into LightRAG using the new `gemini-embedding-2` base from Plan 05-00. Extend `batch_ingest_from_spider.py` to accept multiple keywords so re-running with new scope stays a one-command operation.

Purpose: D-12 + D-10 + D-11 — give Wave 1+ daily digests a non-empty, depth-filtered graph floor from day 1. Cost-optimize with Batch API if spike showed it available.

Output: populated `classifications` table, extended CLI, batch submission + poll scripts, and filtered ingests completed.

**Dedup isolation note (addresses checker BLOCKER 4):** The 18 docs re-embedded by Plan 05-00's `scripts/wave0_reembed.py` bypass `batch_ingest_from_spider.py`'s dedup layer — they go through LightRAG's `adelete_by_doc_id` + `ainsert` directly. Wave 0b's filtered subset is a DISJOINT set of KOL historical catch-up articles, not those 18 Phase 4 seed docs. Therefore Wave 0b's use of `batch_ingest_from_spider.py --from-db` cannot collide with Wave 0's re-embed (no article_id overlap; dedup table `ingestions` is consulted by Wave 0b only).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-00-embedding-migration-and-consolidation-PLAN.md
@docs/spikes/embedding-002-contract.md
@batch_classify_kol.py
@batch_ingest_from_spider.py
@lightrag_embedding.py

<interfaces>
Existing CLI in `batch_ingest_from_spider.py` (per code_context of CONTEXT.md):

```python
# Current: single topic
parser.add_argument("--topic-filter", type=str, default=None, help="Required topic to include (e.g. 'AI agents')")
parser.add_argument("--from-db", action="store_true", help="Ingest articles already classified in kol_scan.db (requires --topic-filter)")
parser.add_argument("--min-depth", type=int, default=2)
```

Target shape (chosen: comma-separated for composability with cron args):
```python
# --topic-filter "openclaw,hermes,agent,harness"
# parses to list: ["openclaw", "hermes", "agent", "harness"]
```

Existing dedup (per RESEARCH.md Pitfall 4):
```sql
-- batch_ingest_from_spider.py:562
excludes article_id IN (SELECT article_id FROM ingestions WHERE status = 'ok')
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0b.1: Classify all 302 existing KOL articles (populate `classifications` table)</name>
  <files>batch_classify_kol.py</files>
  <read_first>
    - batch_classify_kol.py (existing CLI — confirm `--topic`, `--min-depth`, `--days-back` flags)
    - .planning/STATE.md (blocker: `classifications` table currently empty)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (D-12)
    - .planning/phases/05-pipeline-automation/05-PRD.md §9 quick-start command
  </read_first>
  <action>
    Inspect `batch_classify_kol.py` and confirm whether it supports a mode that processes ALL unclassified articles (not just the last 7 days). If not, add a new flag `--classify-all` that sets `days_back = 99999` (or equivalent: SELECT articles where article_id NOT IN classifications regardless of date).

    The flag implementation is minimal:
    ```python
    parser.add_argument("--classify-all", action="store_true",
                        help="Classify every article not already in classifications table, regardless of age")
    # When args.classify_all is True, the SQL query selecting articles to classify
    # must drop the days_back filter:
    if args.classify_all:
        where_clauses.remove("date(a.fetched_at) >= date('now', ?)")  # or equivalent
    ```

    Keep all other CLI behavior unchanged. Preserve existing `--topic`, `--min-depth`, `--classifier` flags (surgical change per CLAUDE.md §3).

    After the code change, execute on remote:
    ```
    ssh remote "cd ~/OmniGraph-Vault && venv/bin/python batch_classify_kol.py \
      --topic Agent --topic LLM --topic RAG --topic NLP --topic CV \
      --min-depth 2 --classify-all --classifier gemini"
    ```

    Throttle consideration: `batch_classify_kol.py` uses the LLM classifier with its own rate limiting; `--classifier gemini` is preferred (free-tier 250 RPD, plenty for 302 articles over one run). DeepSeek works too if the user's account has quota; note `--classifier deepseek` is the default per existing code.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; sqlite3 data/kol_scan.db 'SELECT COUNT(*) FROM classifications'" | awk '{if(\$1 &gt; 100) exit 0; else exit 1}'</automated>
  </verify>
  <acceptance_criteria>
    - File `batch_classify_kol.py` contains `--classify-all` flag OR an equivalent mechanism to classify all unclassified articles.
    - `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM classifications"` returns ≥ 100 (expected: ~302 × number-of-topics, capped by unique (article_id, topic) constraint).
    - `sqlite3 data/kol_scan.db "SELECT COUNT(DISTINCT article_id) FROM classifications"` returns ≥ 250 (the vast majority of 302 articles now have at least one classification row).
  </acceptance_criteria>
  <done>`classifications` table populated; D-12 satisfied; ready for Task 0b.2 filter.</done>
</task>

<task type="auto">
  <name>Task 0b.2: Extend `batch_ingest_from_spider.py` to accept multi-keyword `--topic-filter`</name>
  <files>batch_ingest_from_spider.py, tests/verify_wave0b_filter.py</files>
  <read_first>
    - batch_ingest_from_spider.py lines 598-616 (current argparse block + `--topic-filter` usage)
    - batch_ingest_from_spider.py `ingest_from_db` function (search for `def ingest_from_db`) — where the topic filter is applied in the SQL query
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (D-11 re-runnable pattern)
  </read_first>
  <action>
    In `batch_ingest_from_spider.py`:

    **1. Change `--topic-filter` to accept comma-separated values.**
    Replace the existing argparse line (lines ~602-603):
    ```python
    parser.add_argument("--topic-filter", type=str, default=None,
                        help="Required topic to include (e.g. 'AI agents')")
    ```
    with:
    ```python
    parser.add_argument("--topic-filter", type=str, default=None,
                        help="Required topic(s) to include, comma-separated "
                             "(e.g. 'openclaw,hermes,agent,harness'). "
                             "Case-insensitive. Matches title OR classification topic OR content.")
    ```

    **2. Change `ingest_from_db` and `main()` to parse+pass the list.**
    In `main()`:
    ```python
    if args.from_db:
        if not args.topic_filter:
            logger.error("--topic-filter is required with --from-db")
            sys.exit(1)
        topic_list = [t.strip().lower() for t in args.topic_filter.split(",") if t.strip()]
        ingest_from_db(topic_list, args.min_depth, args.dry_run)
    ```

    **3. Update `ingest_from_db` signature and SQL.**
    Change `def ingest_from_db(topic_filter: str, ...)` to `def ingest_from_db(topic_filters: list[str], ...)`.

    In the SQL `WHERE` clause, replace the single-topic filter with:
    ```python
    # Build a case-insensitive OR condition over the keyword list.
    # Match title, content_snippet, or classification topic.
    placeholders = ",".join("?" for _ in topic_filters)
    where_topic = f"""(
        LOWER(a.title) GLOB {" OR LOWER(a.title) GLOB ".join(["?"] * len(topic_filters))}
        OR LOWER(IFNULL(a.content, '')) GLOB {" OR LOWER(IFNULL(a.content, '')) GLOB ".join(["?"] * len(topic_filters))}
        OR LOWER(c.topic) IN ({placeholders})
    )"""
    # Params: [f"*{t}*" for t in topic_filters] * 2 + topic_filters
    ```
    (Planner's exact SQL is fine; the acceptance criterion is that ALL keywords are matched and case-insensitive.)

    **4. Create `tests/verify_wave0b_filter.py`:**
    ```python
    """Verify keyword+depth filter produces a non-empty, correct subset."""
    import sqlite3
    from pathlib import Path
    import sys

    DB = Path("data/kol_scan.db")
    KEYWORDS = ["openclaw", "hermes", "agent", "harness"]

    conn = sqlite3.connect(DB)
    # Count matching rows
    conds = " OR ".join(
        f"LOWER(a.title) LIKE '%{k}%' OR LOWER(IFNULL(a.content, '')) LIKE '%{k}%' OR LOWER(c.topic) = '{k}'"
        for k in KEYWORDS
    )
    sql = f"""
        SELECT COUNT(DISTINCT a.id)
        FROM articles a
        JOIN classifications c ON c.article_id = a.id
        WHERE c.depth_score >= 2 AND ({conds})
    """
    (n,) = conn.execute(sql).fetchone()
    print(f"filtered_count: {n}")
    assert n > 0, f"Expected >0 matching articles, got {n}"
    sys.exit(0)
    ```
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter 'openclaw,hermes,agent,harness' --min-depth 2 --dry-run 2&gt;&amp;1" | grep -E "^(Would ingest|Article|Dry-run|Topic filter)" &amp;&amp; ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python tests/verify_wave0b_filter.py"</automated>
  </verify>
  <acceptance_criteria>
    - `batch_ingest_from_spider.py --topic-filter` help text mentions "comma-separated".
    - Running `batch_ingest_from_spider.py --from-db --topic-filter 'openclaw,hermes,agent,harness' --min-depth 2 --dry-run` does NOT error with "topic-filter required" and prints a list of candidate articles OR an empty-but-clean summary.
    - `tests/verify_wave0b_filter.py` exits 0 (SQL confirms the filter matches at least one article).
    - No regressions: running with a single keyword `--topic-filter openclaw` still works (backward-compat: list of length 1).
  </acceptance_criteria>
  <done>Multi-keyword CLI ready; D-11 re-runnable pattern established.</done>
</task>

<task type="auto">
  <name>Task 0b.3: Submit Batch API (or sync fallback) and ingest filtered subset</name>
  <files>scripts/wave0b_submit_batch.py, scripts/wave0b_poll_and_ingest.py</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md Pattern 2 (full Batch API shape) + Pitfall 2 (paid tier warning)
    - docs/spikes/embedding-002-contract.md (Plan 05-00 output — check `batch_api_available` field)
    - batch_ingest_from_spider.py (Task 0b.2 output — uses filtered list)
    - lightrag_embedding.py (for sync fallback path)
  </read_first>
  <action>
    This task has two paths depending on the spike report's `batch_api_available` value. Both scripts MUST be created; the operator picks which to run based on the spike output.

    **Path A — Batch API available (spike says `batch_api_available: true`):**

    `scripts/wave0b_submit_batch.py` MUST include a full argparse block with `--dry-run`, `--topic-filter`, and `--min-depth` (BLOCKER 4 fix — the previous pseudocode stub had no argparse, making the acceptance criterion unverifiable):

    ```python
    """Submit a single Gemini Batch embedding job for the Wave 0b filtered subset.

    Requires docs/spikes/embedding-002-contract.md with batch_api_available: true.
    Alternative when false: run `batch_ingest_from_spider.py` directly with the
    sync embedding_func from Plan 05-00.

    Usage:
        venv/bin/python scripts/wave0b_submit_batch.py --dry-run
        venv/bin/python scripts/wave0b_submit_batch.py \\
            --topic-filter "openclaw,hermes,agent,harness" --min-depth 2
    """
    from __future__ import annotations

    import argparse
    import json
    import os
    import sqlite3
    import sys
    from pathlib import Path

    from google import genai
    from google.genai import types

    DB = Path("data/kol_scan.db")

    def _eligible_articles(topic_filters: list[str], min_depth: int) -> list[dict]:
        conn = sqlite3.connect(DB)
        try:
            kws = [f"%{k.lower()}%" for k in topic_filters]
            placeholders = " OR ".join(["LOWER(c.topic) = ?" for _ in topic_filters])
            title_conds = " OR ".join(["LOWER(a.title) LIKE ?" for _ in topic_filters])
            sql = f"""
                SELECT DISTINCT a.id, a.title, a.content
                FROM articles a
                JOIN classifications c ON c.article_id = a.id
                WHERE c.depth_score >= ?
                  AND (({title_conds}) OR ({placeholders}))
                  AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
            """
            rows = conn.execute(sql, (min_depth, *kws, *[k.lower() for k in topic_filters])).fetchall()
            return [{"id": r[0], "title": r[1], "content": r[2]} for r in rows]
        finally:
            conn.close()

    def main() -> int:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true",
                            help="Print planned actions, skip Batch API calls")
        parser.add_argument("--topic-filter", default="openclaw,hermes,agent,harness",
                            help="Comma-separated keyword filter (case-insensitive)")
        parser.add_argument("--min-depth", type=int, default=2,
                            help="Minimum depth_score (default: 2)")
        args = parser.parse_args()

        topic_filters = [t.strip() for t in args.topic_filter.split(",") if t.strip()]
        rows = _eligible_articles(topic_filters, args.min_depth)
        print(f"eligible_count: {len(rows)}")

        if args.dry_run:
            for r in rows[:20]:
                print(f"  DRY: id={r['id']} title={r['title'][:80]}")
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more")
            return 0

        # Live path — construct Batch job
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        # 1. Build JSONL upload file with one line per article chunk
        # 2. Upload via client.files.upload(...)
        # 3. Submit via client.batches.create_embeddings(
        #      model="gemini-embedding-2",
        #      src=types.EmbeddingsBatchJobSource(file_name=uploaded.name),
        #      config=types.CreateEmbeddingsBatchJobConfig(display_name="wave0b-kol-catchup"),
        #    )
        # 4. Write batch_job_name to data/wave0b_batch.json for the poller
        print("TODO: implement live batch submission (commented out until spike confirms availability)")
        return 0

    if __name__ == "__main__":
        sys.exit(main())
    ```

    `scripts/wave0b_poll_and_ingest.py` (also MUST have argparse + `--dry-run`):
    ```python
    """Poll the Batch job until complete, download results, and pass the filtered
    subset to batch_ingest_from_spider.py for LightRAG ingest.

    Usage:
        venv/bin/python scripts/wave0b_poll_and_ingest.py --dry-run
        venv/bin/python scripts/wave0b_poll_and_ingest.py
    """
    from __future__ import annotations

    import argparse
    import json
    import subprocess
    import sys
    import time
    from pathlib import Path

    BATCH_STATE = Path("data/wave0b_batch.json")

    def main() -> int:
        p = argparse.ArgumentParser()
        p.add_argument("--dry-run", action="store_true",
                       help="Preview poll/ingest plan without API calls")
        args = p.parse_args()

        if not BATCH_STATE.exists():
            print(f"ERROR: {BATCH_STATE} not found; run wave0b_submit_batch.py first", file=sys.stderr)
            return 2

        job_name = json.loads(BATCH_STATE.read_text())["batch_job_name"]
        if args.dry_run:
            print(f"DRY: would poll batch_job_name={job_name} every 60s then subprocess ingest")
            return 0

        # 1. Poll client.batches.get(name=job_name) every 60s until state in (SUCCEEDED,FAILED,CANCELLED)
        # 2. On SUCCEEDED: download result file via client.files.download(file=job.dest.file_name)
        # 3. Invoke batch_ingest_from_spider as subprocess (uses NEW embedding_func via lightrag_embedding):
        subprocess.run(
            ["venv/bin/python", "batch_ingest_from_spider.py", "--from-db",
             "--topic-filter", "openclaw,hermes,agent,harness", "--min-depth", "2"],
            check=True,
        )
        return 0

    if __name__ == "__main__":
        sys.exit(main())
    ```

    Rationale: The Batch API optimizes the 302-classification/pre-embed step, not the actual LightRAG ingest (which is sync and per-doc). The poll-and-ingest script bridges the two. If Batch API is unavailable, skip the Batch submission entirely and just run the `batch_ingest_from_spider.py` sync command — the embedding_func from Plan 05-00 already respects the 60-RPM throttle via Task 0.4's rpm_ceiling-adapted config.

    **Path B — Batch API unavailable (spike says `batch_api_available: false`):**

    Document in the plan SUMMARY that Path A scripts are skeleton-only, and the actual Wave 0b execution is:
    ```
    # Pre-flight: clean zombie docs (prevents resume poison from prior runs)
    ssh remote "cd ~/OmniGraph-Vault && venv/bin/python scripts/clean_lightrag_zombies.py"

    # Actual ingest — v3.2 checkpoint/resume + try/finally _clear_pending_doc_id protect per-article
    ssh remote "cd ~/OmniGraph-Vault && venv/bin/python batch_ingest_from_spider.py \
      --from-db --topic-filter 'openclaw,hermes,agent,harness' --min-depth 2"
    ```
    This uses the new sync `embedding_func` with the existing 60-RPM throttle. Ingestion dedup (Pitfall 4) prevents re-ingest of the 18 original docs — but note those 18 ARE NOT in the Wave 0b filtered subset anyway (Plan 05-00 re-embeds them via `adelete_by_doc_id` + `ainsert`, which bypasses the `ingestions` dedup table used by `batch_ingest_from_spider.py`). See objective's dedup isolation note.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; grep -q 'batch_api_available' docs/spikes/embedding-002-contract.md &amp;&amp; BAA=\$(grep 'batch_api_available:' docs/spikes/embedding-002-contract.md | awk '{print \$2}') &amp;&amp; if [ \"\$BAA\" = 'true' ]; then venv/bin/python scripts/wave0b_submit_batch.py --dry-run; else venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter 'openclaw,hermes,agent,harness' --min-depth 2 --dry-run; fi"</automated>
  </verify>
  <acceptance_criteria>
    - Files `scripts/wave0b_submit_batch.py` AND `scripts/wave0b_poll_and_ingest.py` exist (both, regardless of path chosen — Path B just doesn't execute them).
    - Each file is a self-contained module with a `__main__` block and `--dry-run` flag.
    - `grep -q "argparse" scripts/wave0b_submit_batch.py` returns 0.
    - `grep -q 'add_argument("--dry-run"' scripts/wave0b_submit_batch.py` returns 0.
    - `grep -q "argparse" scripts/wave0b_poll_and_ingest.py` returns 0.
    - `grep -q 'add_argument("--dry-run"' scripts/wave0b_poll_and_ingest.py` returns 0.
    - `venv/bin/python scripts/wave0b_submit_batch.py --dry-run` exits 0 and prints `eligible_count: <N>`.
    - After execution of the chosen path, `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM ingestions WHERE status='ok'"` has increased by ≥ the filtered subset count (new ingests added).
    - LightRAG entity count post-Wave-0b > post-Wave-0 count (new docs add entities).
  </acceptance_criteria>
  <done>Filtered KOL historical articles ingested; daily digest in Wave 2 has a non-empty graph floor.</done>
</task>

</tasks>

<verification>
- `classifications` table populated (≥ 250 distinct article_ids).
- `batch_ingest_from_spider.py --topic-filter` accepts comma-separated values.
- Either Batch API submission succeeded OR sync fallback completed; filtered subset ingested; LightRAG entity count grew.
- `tests/verify_wave0b_filter.py` exits 0.
- Both wave0b scripts have real argparse blocks with `--dry-run`.
</verification>

<success_criteria>
- D-12 satisfied: all 302 articles classified.
- D-10 + D-11 satisfied: keyword+depth filter produces a non-empty subset; CLI is re-runnable with new keywords.
- D-14 satisfied: single Batch submission (if available) OR sync fallback completed.
- LightRAG graph grew by the filtered subset count.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-00b-SUMMARY.md` with: classified count, filtered subset count, Batch-vs-sync path taken, LightRAG entity count delta, and any articles that failed ingest with reason.
</output>
