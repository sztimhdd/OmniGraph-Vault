---
phase: kdb-2.5
plan_id: kdb-2.5-01
slug: job-script-and-smallbatch-validation
wave: 1
depends_on: []
estimated_time: 1d
requirements:
  - SEED-DBX-02
skills:
  - databricks-patterns
  - python-patterns
  - writing-tests
  - search-first
files_modified:
  - databricks-deploy/jobs/__init__.py
  - databricks-deploy/jobs/reindex_lightrag.py
  - databricks-deploy/jobs/reindex_lightrag.yml
  - databricks-deploy/jobs/tests/__init__.py
  - databricks-deploy/jobs/tests/conftest.py
  - databricks-deploy/jobs/tests/test_reindex_unit.py
  - databricks-deploy/jobs/tests/test_reindex_integration.py
  - databricks-deploy/jobs/tests/fixtures/kol_scan_fixture.db
  - .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-SMALLBATCH-FINDINGS.md
autonomous: false

must_haves:
  truths:
    - "Job script loads ~170 filtered candidates from Volume DB (DATA-07 strict filter)"
    - "Empty-target check blocks Step 1 on non-empty lightrag_storage/ without --force-overwrite"
    - "_ingest_one returns IngestResult(status='failed') on exception — never propagates"
    - "_ingest_one cross-checks doc_status post-ainsert (D-05: try/except alone is insufficient)"
    - "ainsert called with ids=[content_hash] for idempotency (D-06)"
    - "Step 1 smallbatch produces kdb-2.5-smallbatch-stats.json on Volume"
    - "Unit tests green before Step 1 trigger; cost gate decision explicit in SMALLBATCH-FINDINGS"
  artifacts:
    - path: "databricks-deploy/jobs/reindex_lightrag.py"
      provides: "Multi-mode Job script (smallbatch / fullreindex / postcheck)"
      min_lines: 350
    - path: "databricks-deploy/jobs/reindex_lightrag.yml"
      provides: "Three Bundle Jobs (smallbatch / fullrun / postcheck) — no --force-overwrite in defaults"
    - path: "databricks-deploy/jobs/tests/test_reindex_unit.py"
      provides: "6 unit tests covering DATA-07 filter, stratified sample, empty-target safety, per-article isolation, resume, FAILURES.csv schema"
    - path: ".planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-SMALLBATCH-FINDINGS.md"
      provides: "Step 1 evidence: per-article token counts, wallclock, cost extrapolation, gate decision"
  key_links:
    - from: "reindex_lightrag.py:_load_candidates"
      to: "kol_scan.db WHERE layer1_verdict='candidate' AND ..."
      via: "sqlite3 URI mode (file:?mode=ro)"
      pattern: "layer1_verdict.*candidate"
    - from: "reindex_lightrag.py:_ingest_one"
      to: "rag.doc_status.get_docs_by_ids"
      via: "post-ainsert doc_status check (D-05)"
      pattern: "get_docs_by_ids"
    - from: "reindex_lightrag.py:_instantiate_lightrag"
      to: "lightrag_databricks_provider.make_llm_func / make_embedding_func"
      via: "sys.path.insert + bare import (Pitfall 6)"
      pattern: "from lightrag_databricks_provider import"
---

<objective>
Author the kdb-2.5 Databricks Job script, Bundle YAML, unit test suite, and run Step 1
(50-article stratified smallbatch) against the prod Volume. Produce
`kdb-2.5-SMALLBATCH-FINDINGS.md` with measured per-article cost, wallclock, 429 rate,
and the explicit gate decision: cost_extrap < $200 AND wallclock_extrap < 30h AND
failure_rate < 5%. If gate FAILS → STOP; do NOT proceed to Plan 02.

Purpose: Validate the re-index Job at small scale before committing to the hours-long /
$17-100 Step 2. The gate decision is the primary deliverable of this plan.

Output:
- `databricks-deploy/jobs/reindex_lightrag.py` (~400 LOC)
- `databricks-deploy/jobs/reindex_lightrag.yml`
- 6 unit tests + 1 integration test + fixture DB + conftest
- `kdb-2.5-SMALLBATCH-FINDINGS.md` (Step 1 evidence + gate decision)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-RESEARCH.md
@.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-CONTEXT.md
@.planning/REQUIREMENTS-kb-databricks-v1.md
@.planning/ROADMAP-kb-databricks-v1.md
@.planning/STATE-kb-databricks-v1.md

<interfaces>
<!-- Key contracts the executor must use. Extracted from kdb-1.5 frozen files. DO NOT MODIFY. -->

From databricks-deploy/lightrag_databricks_provider.py (kdb-1.5 FROZEN):
```python
KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
KB_EMBEDDING_MODEL = os.environ.get("KB_EMBEDDING_MODEL", "databricks-qwen3-embedding-0-6b")
EMBEDDING_DIM = 1024  # locked per REQUIREMENTS rev 3

def make_llm_func() -> async callable   # wraps WorkspaceClient.serving_endpoints.query
def make_embedding_func() -> EmbeddingFunc  # @wrap_embedding_func_with_attrs(dim=1024)
```

From kb/data/article_query.py lines 71-85 (DATA-07 filter — Job WHERE must match):
```python
_DATA07_BARE = (
    "body IS NOT NULL AND body != '' "
    "AND layer1_verdict = 'candidate' "
    "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
)
# Job also requires: AND content_hash IS NOT NULL
# kol_scan.db has tables: articles (KOL) and rss_articles (RSS)
# Both have columns: content_hash TEXT, title TEXT, body TEXT, lang TEXT,
#                    layer1_verdict TEXT, layer2_verdict TEXT
```

From venv/Lib/site-packages/lightrag/lightrag.py v1.4.15:
```python
async def ainsert(
    self,
    input: str | list[str],
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
    track_id: str | None = None,
) -> str:  # returns track_id — NOT a success indicator

# doc_status check (required per D-05):
status_records = await rag.doc_status.get_docs_by_ids([f"doc-{content_hash}"])
doc_status = status_records[0].status.value  # "PROCESSED" | "FAILED" | "PENDING"
```

Volume layout (locked per STATE rev 3):
```
/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/
  data/kol_scan.db          # source DB (READ_VOLUME)
  lightrag_storage/          # re-index output (WRITE_VOLUME — D-03)
  output/kdb-2.5-progress.csv
  output/kdb-2.5-FAILURES.csv
  output/kdb-2.5-smallbatch-stats.json
```
</interfaces>
</context>

<tasks>

<!-- ================================================================
Task 1.1 — Job script reindex_lightrag.py
~2-3h; creates the main deliverable.
================================================================ -->
<task type="auto" tdd="true">
<name>Task 1.1: Author databricks-deploy/jobs/reindex_lightrag.py</name>
<files>
databricks-deploy/jobs/__init__.py
databricks-deploy/jobs/reindex_lightrag.py
</files>
<behavior>
  - test_load_candidates_strict_filter: given a fixture DB with 3 candidate + 2 reject rows, returns exactly 3 rows with expected content_hashes
  - test_stratified_sample_distribution: given 100 rows spanning 5 body-length groups, sample_n=50 returns 10 per group (±1 rounding)
  - test_empty_target_safety_blocks: given non-empty tmp dir without force flag, _verify_target_empty raises RuntimeError containing mtime strings
  - test_empty_target_safety_passes_on_force: same tmp dir with force_overwrite=True passes without raising
  - test_ingest_one_isolates_failures: given mock rag.ainsert raising RuntimeError, _ingest_one returns IngestResult(status='failed') and does not re-raise
  - test_ingest_one_checks_doc_status: given mock rag.ainsert succeeding but doc_status returning 'FAILED', _ingest_one returns status='failed' (D-05)
  - test_resume_skips_already_ok: given a progress CSV with hash 'abc' status='ok', _load_progress_hashes returns {'abc'}; fullreindex filters that hash out
  - test_failures_csv_schema_no_path_leak: given IngestResult with error containing a file path, _append_failures_csv writes truncated 200-char error; error contains no '/' or '\' chars (path leak check)
</behavior>
<action>
Skill(skill="python-patterns", args="Idiomatic frozen dataclass pattern for CandidateRow + IngestResult. asyncio.run() wrapping. sqlite3 URI mode (file:?mode=ro). Stratified ntile sampling with random.seed(42). pathlib.Path for all file ops. Typed Literal for status field.")

Skill(skill="databricks-patterns", args="sys.path.insert pattern for hyphenated databricks-deploy/ directory import. LightRAG factory consumption (make_llm_func + make_embedding_func). WRITE_VOLUME FUSE access pattern for lightrag_storage/. asyncio.run() entry point for spark_python_task.")

Create `databricks-deploy/jobs/__init__.py` as empty file (package marker).

Create `databricks-deploy/jobs/reindex_lightrag.py` implementing the full Q4 sketch from RESEARCH.md. Key implementation rules:

**Imports + path setup (Pitfall 6):**
```python
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # databricks-deploy/
from lightrag_databricks_provider import (
    EMBEDDING_DIM, KB_LLM_MODEL, make_embedding_func, make_llm_func,
)
```

**VOLUME_ROOT and paths:**
```python
VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
DB_PATH     = f"{VOLUME_ROOT}/data/kol_scan.db"
LIGHTRAG_DIR = f"{VOLUME_ROOT}/lightrag_storage"
PROGRESS_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-progress.csv"
FAILURES_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-FAILURES.csv"
```

**CandidateRow and IngestResult:** frozen dataclasses exactly as in RESEARCH Q4.
- CandidateRow: source_table, content_hash, title, body, lang
- IngestResult: content_hash, source_table, status: Literal["ok","failed","skipped"], elapsed_s, error_truncated, track_id

**_load_candidates(db_path, *, filter_mode="strict", sample_n=None):**
- filter_mode MUST be "strict" (per D-01: hardcoded scope, --filter-mode flag preserved for testing but defaulted to strict)
- SQL: UNION ALL of articles + rss_articles with WHERE: body IS NOT NULL AND body != '' AND content_hash IS NOT NULL AND DATA-07 filter
- ORDER BY content_hash for deterministic ordering
- Stratified sampling: sort by len(body), 5 ntiles, sample_n//5 per bucket, random.seed(42)

**_verify_target_empty(*, lightrag_dir, force_overwrite) (D-07):**
- On non-empty + not force_overwrite: raise RuntimeError listing up to 10 artifacts with mtime strings
- On force_overwrite: logger.warning listing count of existing artifacts
- On empty or missing dir: return silently
- DO NOT include --force-overwrite in the default YAML parameters (Pitfall 7)

**_ingest_one(rag, row) → IngestResult (D-05 + D-06):**
- `await rag.ainsert(row.body, ids=[row.content_hash], file_paths=[f"{row.source_table}/{row.content_hash}"])`
- Post-ainsert: `await rag.doc_status.get_docs_by_ids([f"doc-{row.content_hash}"])`
- Only status=="PROCESSED" → ok; "FAILED" or unknown → failed
- Broad `except Exception as e` → IngestResult(status='failed', error_truncated=repr(e)[:200])
- error_truncated MUST be 200-char trimmed repr(e) — no file paths, no hostnames

**_run_smallbatch(args):**
- Load candidates with sample_n=args.max_articles (default 50), filter_mode=args.filter_mode
- _verify_target_empty before first ainsert
- Sequential loop: await _ingest_one per article, _append_progress after each
- Compute: n_ok, n_failed, n_skipped, avg_wallclock_per_ok
- Call _write_smallbatch_findings at end
- Return 0 if failure_rate <= 0.05 else 2

**_run_fullreindex(args):**
- Load all candidates (no sample_n)
- _verify_target_empty before first ainsert
- Resume: _load_progress_hashes(status_filter={'ok'}) → filter candidates
- Sequential loop with progress append + failures CSV append
- Burn-rate alert every 25 articles: if _compute_burn_rate_ratio > 1.5 → logger.warning
- Return 0 if failure_rate <= 0.05 else 2

**_run_postcheck(args):**
- Read vdb_entities.json → verify embedding_dim == 1024
- Sample up to 200 entity names → count zh chars (一-鿿) vs non-zh; warn if either < 10
- Two aquery calls: zh "LangGraph 与 CrewAI 的对比" + en "compare LangGraph and CrewAI frameworks", both mode="hybrid"
- Verify each response len >= 50; return 1 on any check failure
- _write_postcheck_findings with embedding_dim, n_zh, n_en, first-400-char excerpts

**_instantiate_lightrag(working_dir):**
- LightRAG(working_dir=..., llm_model_func=make_llm_func(), embedding_func=make_embedding_func())
- if hasattr(rag, "initialize_storages"): await rag.initialize_storages()

**main():** argparse with --mode {smallbatch,fullreindex,postcheck}, --db-path, --lightrag-dir, --filter-mode, --max-articles (default 50), --force-overwrite (store_true), --shutdown-lightrag (store_true).

NO --init-empty flag in argparse — use _verify_target_empty(force_overwrite=False) as the default behavior (safe by default; fail loudly on non-empty). The RESEARCH uses --init-empty in discussion but --force-overwrite is the actual runtime flag.
</action>
<verify>
  <automated>cd C:\Users\huxxha\Desktop\OmniGraph-Vault && .venv/Scripts/python -c "import ast, pathlib; ast.parse(pathlib.Path('databricks-deploy/jobs/reindex_lightrag.py').read_text())" && echo SYNTAX_OK</automated>
</verify>
<done>
- databricks-deploy/jobs/reindex_lightrag.py exists with >= 350 lines
- Passes ast.parse (syntax valid)
- Contains: _load_candidates, _verify_target_empty, _ingest_one, _run_smallbatch, _run_fullreindex, _run_postcheck, _instantiate_lightrag, main
- _ingest_one contains "get_docs_by_ids" (D-05 doc-status check)
- _ingest_one contains "ids=[row.content_hash]" (D-06 idempotency)
- _verify_target_empty raises RuntimeError with mtime strings on non-empty without force
- databricks-deploy/jobs/__init__.py exists (empty)
</done>
</task>

<!-- ================================================================
Task 1.2 — Unit tests + fixture DB
~1-1.5h
================================================================ -->
<task type="auto" tdd="true">
<name>Task 1.2: Unit tests, integration test, fixture DB, conftest</name>
<files>
databricks-deploy/jobs/tests/__init__.py
databricks-deploy/jobs/tests/conftest.py
databricks-deploy/jobs/tests/test_reindex_unit.py
databricks-deploy/jobs/tests/test_reindex_integration.py
databricks-deploy/jobs/tests/fixtures/kol_scan_fixture.db
</files>
<behavior>
  Unit tests (all mock — no network):
  - test_load_candidates_strict_filter: fixture DB with 5 articles (3 candidate+body, 1 reject, 1 candidate+null-body); strict filter returns 3
  - test_stratified_sample_distribution: 50-row fixture with bodies of len 100, 500, 1000, 5000, 50000 (10 per bucket); sample_n=50 returns exactly 50 with all buckets represented
  - test_empty_target_safety_blocks: tmp_path with 2 dummy files; force_overwrite=False → RuntimeError with filename substrings in message
  - test_empty_target_safety_passes_on_force: same tmp_path; force_overwrite=True → no raise
  - test_ingest_one_isolates_failures: mock rag.ainsert raising RuntimeError("boom"); _ingest_one returns status='failed', error_truncated contains "boom"[:200]
  - test_ingest_one_checks_doc_status: mock rag.ainsert OK but doc_status returns FAILED; _ingest_one returns status='failed' with error containing "doc_status=FAILED"
  - test_resume_skips_already_ok: write progress CSV with 2 ok + 1 failed; _load_progress_hashes returns 2-element set; fullreindex candidate list shrinks by 2
  - test_failures_csv_schema_no_path_leak: simulate failure with error repr containing a path; _append_failures_csv writes 200-char truncated error; error string contains no '/' and no '\\'

  Integration test (requires Model Serving auth — mark with @pytest.mark.dryrun):
  - test_smallbatch_against_fixture_db: run asyncio.run(_run_smallbatch(args)) with fixture DB (5 articles), tmp lightrag_dir; expect return 0 or 2, NEVER unhandled exception; check smallbatch-stats.json exists on tmp dir output path
</behavior>
<action>
Skill(skill="writing-tests", args="pytest fixtures with tmp_path and monkeypatch. sqlite3.connect(':memory:') or tmp .db creation for fixture DB. AsyncMock for rag.ainsert and rag.doc_status.get_docs_by_ids. @pytest.mark.dryrun marker for integration test gated behind Model Serving auth. conftest.py shared fixtures for tmp_working_dir and mock_rag_factory.")

Skill(skill="search-first", args="Before writing conftest, verify pytest-asyncio version in databricks-deploy/requirements.txt (>=0.23.0) and confirm asyncio_mode=auto is set in pytest.ini — reuse existing config from kdb-1.5, do not duplicate.")

**conftest.py:**
- `@pytest.fixture` `tmp_working_dir(tmp_path)` → creates `tmp_path/lightrag_storage/` and `tmp_path/output/` dirs; returns tmp_path
- `@pytest.fixture` `fixture_db_path(tmp_path)` → creates a SQLite DB at `tmp_path/kol_scan_fixture.db` with articles + rss_articles tables containing 5 rows (3 candidate+body, 1 reject, 1 null-body) matching the production schema (content_hash, title, body, lang, layer1_verdict, layer2_verdict)
- `@pytest.fixture` `mock_rag` → MagicMock with async .ainsert returning "track-123" and async .doc_status.get_docs_by_ids returning [MagicMock(status=MagicMock(value="PROCESSED"))]
- Patch PROGRESS_CSV and FAILURES_CSV to tmp_path in session-scoped monkeypatch

**test_reindex_unit.py:** import only from `databricks.jobs.reindex_lightrag` (adjust sys.path as needed). All 8 unit tests described in behavior. No network calls.

**test_reindex_integration.py:** single test `test_smallbatch_against_fixture_db` marked `@pytest.mark.dryrun`. Creates tiny 5-article fixture DB (bodies 100-5000 chars). Calls `asyncio.run(_run_smallbatch(args))` with `--lightrag-dir` pointing to tmp path. Verifies:
- Return value is 0 or 2 (never unhandled exception)
- `tmp_lightrag_dir/output/kdb-2.5-smallbatch-stats.json` created (path adjusted per PROGRESS_CSV constant overriding in conftest)

**kol_scan_fixture.db:** Pre-built SQLite fixture file with 5 articles:
- 2 articles table rows: (hash 'aaaa...', 'candidate', None, body='short article body ~100 chars') + (hash 'bbbb...', 'candidate', None, body='medium body' × 500 chars)
- 1 articles reject row: (hash 'cccc...', 'reject', None, body='rejected')
- 2 rss_articles rows: (hash 'dddd...', 'candidate', None, body='rss article' × 200 chars) + (hash 'eeee...', 'candidate', 'reject', body='rss reject')

Build via conftest fixture or ship as binary created by a helper script. Prefer building it in conftest so the fixture is always current.
</action>
<verify>
  <automated>cd C:\Users\huxxha\Desktop\OmniGraph-Vault && .venv/Scripts/pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v -m "not dryrun" 2>&amp;1 | tail -30</automated>
</verify>
<done>
- All 8 unit tests PASS (no network calls needed)
- test_reindex_integration.py exists with @pytest.mark.dryrun test
- kol_scan_fixture.db exists under tests/fixtures/
- `pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v -m "not dryrun"` exits 0 with 8 passed
</done>
</task>

<!-- ================================================================
Task 1.3 — Bundle YAML
~0.5h
================================================================ -->
<task type="auto">
<name>Task 1.3: Author databricks-deploy/jobs/reindex_lightrag.yml Bundle resource</name>
<files>
databricks-deploy/jobs/reindex_lightrag.yml
</files>
<action>
Skill(skill="databricks-patterns", args="Bundle Job resource shape: spark_python_task + serverless environments: with environment_version '2' + dependencies list. max_concurrent_runs: 1 for single-writer safety. Three separate Jobs for distinct timeouts. YAML include path relative to bundle root. databricks bundle deploy -t dev + bundle run syntax.")

Skill(skill="search-first", args="Verify current databricks bundle CLI version (0.260+) spark_python_task shape — python_file path resolution relative to YAML location. Confirm environment_version '2' is the current serverless compute generation.")

Create `databricks-deploy/jobs/reindex_lightrag.yml` with three Job resources:

**kdb_2_5_reindex_smallbatch:**
- name: "[kdb-2.5] Re-index LightRAG — Step 1 smallbatch (50 articles)"
- queue.enabled: true; max_concurrent_runs: 1
- timeout_seconds: 7200 (2h ceiling for Step 1)
- spark_python_task.python_file: path resolving to reindex_lightrag.py relative to bundle root (verify at deploy time: if YAML is in `databricks-deploy/jobs/`, use `./reindex_lightrag.py`; if bundle root is `databricks-deploy/`, use `jobs/reindex_lightrag.py`)
- parameters: ["--mode", "smallbatch", "--max-articles", "50", "--filter-mode", "strict"]
- NO --force-overwrite in parameters (Pitfall 7, D-07)
- environment_key: default with environment_version: "2" + dependencies: ["lightrag-hku==1.4.15", "databricks-sdk>=0.30.0", "numpy>=1.26.0"]

**kdb_2_5_reindex_fullrun:**
- name: "[kdb-2.5] Re-index LightRAG — Step 2 fullreindex (all candidates)"
- timeout_seconds: 108000 (30h ceiling matching ROADMAP cost gate)
- parameters: ["--mode", "fullreindex", "--filter-mode", "strict"]
- NO --force-overwrite (operator passes via `databricks bundle run ... --params` at runtime per D-07)
- Same environment block

**kdb_2_5_reindex_postcheck:**
- name: "[kdb-2.5] Re-index LightRAG — Step 3 postcheck"
- timeout_seconds: 1800 (30min ceiling)
- parameters: ["--mode", "postcheck"]
- Same environment block

Add header comment explaining:
- Phase: kdb-2.5 / Requirements: SEED-DBX-02, SEED-DBX-03
- Deploy: databricks bundle deploy -t dev
- Run Step 1: databricks bundle run kdb_2_5_reindex_smallbatch -t dev
- Run Step 2 (ONLY after Step 1 gate PASS): databricks bundle run kdb_2_5_reindex_fullrun -t dev
- Run Step 2 retry with resume: same command (progress CSV handles resume per D-06)
- Run Step 2 with force-overwrite (explicit operator intent): databricks bundle run kdb_2_5_reindex_fullrun -t dev --params force-overwrite=true
- Run Step 3: databricks bundle run kdb_2_5_reindex_postcheck -t dev

Include note: "This file must be referenced via include: in the parent databricks.yml bundle config."
</action>
<verify>
  <automated>cd C:\Users\huxxha\Desktop\OmniGraph-Vault && databricks bundle validate -t dev 2>&amp;1 | head -20</automated>
</verify>
<done>
- reindex_lightrag.yml exists
- Three Jobs defined: kdb_2_5_reindex_smallbatch, kdb_2_5_reindex_fullrun, kdb_2_5_reindex_postcheck
- Neither smallbatch nor fullrun default parameters include --force-overwrite
- timeout_seconds: 7200, 108000, 1800 respectively
- `databricks bundle validate -t dev` returns no errors (or only warns about unset email_notifications)
</done>
</task>

<!-- ================================================================
Task 1.4 — Deploy bundle + trigger Step 1 + cost gate decision
~0.5-1h active + ~30min Job run
TYPE: checkpoint:human-verify because Step 1 run requires the executor to
wait for the Job, read billing data, and write the findings doc — then the
user must review the cost gate before Plan 02 is allowed to proceed.
================================================================ -->
<task type="checkpoint:human-verify" gate="blocking">
<name>Task 1.4: Deploy bundle, run Step 1, verify cost gate, write SMALLBATCH-FINDINGS</name>
<what-built>
Job script (reindex_lightrag.py) + Bundle YAML (reindex_lightrag.yml) authored and unit-tested.
Now deploy the bundle to dev workspace and execute Step 1 (50-article stratified smallbatch).
Produce kdb-2.5-SMALLBATCH-FINDINGS.md with the explicit cost gate decision.

**CRITICAL — Cost gate decision MUST appear explicitly at the end of SMALLBATCH-FINDINGS:**
```
Gate decisions:
  cost_extrap < $200: YES/NO  → $X (extrapolated)
  wallclock_extrap < 30h: YES/NO  → Xh (extrapolated)
  failure_rate < 5%: YES/NO  → X% (N_failed / 50)

GATE: PASS → proceed to Plan 02
  OR: BLOCKED — cost gate failed; escalate to user; do NOT trigger Step 2
```

If BLOCKED → STOP PLAN 01 HERE. Do NOT execute Plan 02.
</what-built>
<how-to-verify>
**Step A — Bundle deploy:**
```bash
cd /path/to/OmniGraph-Vault
databricks bundle deploy -t dev 2>&1 | tail -30
# Expected: "Bundle deployed successfully" or "Updated existing bundle"
```

**Step B — Confirm YAML includes reindex_lightrag.yml:**
Check that `databricks-deploy/databricks.yml` has `include: [jobs/reindex_lightrag.yml]` or
an equivalent path. If not, add the include entry (this is a one-line addition to the bundle
root config, NOT a kdb-1.5 frozen file modification).

**Step C — Trigger Step 1:**
```bash
databricks bundle run kdb_2_5_reindex_smallbatch -t dev
# Streams logs. Wait for completion (~30 min).
# Job should end with exit code 0 (SUCCEEDED) or 2 (SUCCEEDED_WITH_FAILURES if >5% of 50)
```

**Step D — Pull smallbatch stats from Volume:**
```bash
databricks fs cat dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-smallbatch-stats.json
```
Verify JSON contains: n_results, n_ok, n_failed, elapsed_total_s, avg_wallclock_per_ok.

**Step E — Pull billing data:**
In Databricks workspace UI: Settings → Billing → Model Serving usage for the Job run window.
Note: Sonnet 4.6 input tokens, output tokens; Qwen3-Embedding input tokens. Divide by 50.

**Step F — Write SMALLBATCH-FINDINGS.md:**
Author `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-SMALLBATCH-FINDINGS.md`
using the RESEARCH Q8 template. Include:
- 50-article run-id from `databricks jobs runs list` or output of `bundle run`
- Per-article measurements from billing dashboard
- Extrapolation formula with actual numbers
- 3-line gate decision (cost / time / failure rate)
- Longest-article wallclock + body-length (from progress CSV)

**Step G — Verify gate:**
If all 3 gate criteria PASS:
- Type "gate PASS — proceed to Plan 02"

If any gate criterion FAILS:
- Type "gate BLOCKED: [criterion that failed] = [actual value]"
- Do NOT proceed to Plan 02 until user reviews and approves scope adjustment
</how-to-verify>
<resume-signal>
Type "gate PASS — proceed to Plan 02" OR "gate BLOCKED: [reason]"
</resume-signal>
</task>

</tasks>

<verification>
## Phase kdb-2.5-01 verification

All must-haves for Plan 01 are verified by this sequence:

```bash
# 1. Syntax check
cd C:\Users\huxxha\Desktop\OmniGraph-Vault
.venv/Scripts/python -c "import ast, pathlib; ast.parse(pathlib.Path('databricks-deploy/jobs/reindex_lightrag.py').read_text())"

# 2. Unit tests (no network)
.venv/Scripts/pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v -m "not dryrun"
# Expected: 8 passed

# 3. D-05 doc-status check present
grep -n "get_docs_by_ids" databricks-deploy/jobs/reindex_lightrag.py
# Expected: at least 1 match in _ingest_one

# 4. D-06 idempotency present
grep -n "ids=\[row.content_hash\]" databricks-deploy/jobs/reindex_lightrag.py
# Expected: match in _ingest_one

# 5. D-07 empty-target safety in YAML (no --force-overwrite in defaults)
grep -A5 "parameters:" databricks-deploy/jobs/reindex_lightrag.yml | grep "force-overwrite"
# Expected: NO MATCH

# 6. DATA-07 filter present
grep -n "layer1_verdict.*candidate" databricks-deploy/jobs/reindex_lightrag.py
# Expected: match in _load_candidates

# 7. SMALLBATCH-FINDINGS.md cost gate line present
grep "GATE:" .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-SMALLBATCH-FINDINGS.md
# Expected: "GATE: PASS" or "GATE: BLOCKED"
```

CONFIG-DBX-01 check (zero kb/ / lib/ / top-level *.py modifications):
```bash
git diff --name-only HEAD | grep -E "^kb/|^lib/|^[^/]+\.py$"
# Expected: empty
```
</verification>

<success_criteria>
Plan 01 is complete when ALL of the following are true:

1. `databricks-deploy/jobs/reindex_lightrag.py` exists with >= 350 lines; contains _load_candidates, _verify_target_empty, _ingest_one (with get_docs_by_ids + ids=[content_hash]), _run_smallbatch, _run_fullreindex, _run_postcheck
2. `databricks-deploy/jobs/reindex_lightrag.yml` exists with 3 Jobs; no --force-overwrite in default parameters
3. `pytest databricks-deploy/jobs/tests/test_reindex_unit.py -v -m "not dryrun"` → 8 PASSED, 0 failures
4. `databricks bundle deploy -t dev` SUCCEEDED
5. `databricks bundle run kdb_2_5_reindex_smallbatch -t dev` completed (SUCCEEDED or SUCCEEDED_WITH_FAILURES)
6. `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-SMALLBATCH-FINDINGS.md` exists with explicit gate decision
7. Gate decision = PASS (cost < $200, wallclock < 30h, failure rate < 5%)
8. Zero modifications to: kdb-1.5 frozen files, CONFIG-EXEMPTIONS.md, kb/, lib/, top-level *.py
</success_criteria>

<hard_constraints>
D-01: filter_mode='strict' is hardcoded default in _load_candidates; DATA-07 filter matches kb/data/article_query.py.
D-02: This plan is Plan 01; Plan 02 is a separate wave — do not conflate.
D-03: Job runs as hhu@edc.ca; no --as flag needed for dev deploy; verify WRITE_VOLUME at Plan 02 pre-flight.
D-04: NO ThreadPoolExecutor; single LightRAG instance; single thread. LightRAG internals provide concurrency.
D-05: _ingest_one MUST call get_docs_by_ids post-ainsert; try/except alone is insufficient.
D-06: ainsert called with ids=[row.content_hash] — explicit ID for idempotency.
D-07: _verify_target_empty raises on non-empty without force; YAML default parameters MUST NOT include --force-overwrite.
ROADMAP gate (line 162): cost_extrap > $200 OR wallclock_extrap > 30h → STOP; do not trigger Plan 02.
CONFIG-DBX-01: ZERO modifications to kb/, lib/, top-level *.py, kdb-1.5 frozen files, CONFIG-EXEMPTIONS.md.
Concurrent safety: git add explicit files only (no -A); forward-only commits (no --amend, no git reset).
</hard_constraints>

<anti_patterns>
- DO NOT add ThreadPoolExecutor for "parallelism" (Pitfall 2: corrupts shared lightrag_storage/).
- DO NOT add --force-overwrite to YAML default parameters (Pitfall 7: silently overwrite good state).
- DO NOT treat ainsert return value (track_id) as success indicator (Pitfall 1: it's unconditional).
- DO NOT use git add -A (concurrent quick safety: explicit file paths only).
- DO NOT use hardcoded article count 2598 or 2000; _load_candidates is the source of truth (~170 filtered).
- DO NOT call `from databricks-deploy.lightrag_databricks_provider import` (Pitfall 6: hyphenated dir is not a package; use sys.path.insert).
- DO NOT modify lightrag_databricks_provider.py or startup_adapter.py (kdb-1.5 frozen).
- DO NOT extend CONFIG-EXEMPTIONS.md (kdb-2 frozen).
- DO NOT reference tests/integration/kb/ (kdb-2 / KB-v2 territory).
</anti_patterns>

<output>
After completion, create `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-01-SUMMARY.md`
containing:
- Summary of what was built (script, YAML, tests)
- Step 1 run-id and smallbatch results (n_ok, n_failed, avg_wallclock)
- Cost gate verdict (PASS / BLOCKED)
- Explicit Skill invocations used: Skill(skill="databricks-patterns"), Skill(skill="python-patterns"), Skill(skill="writing-tests"), Skill(skill="search-first")
- Commit hashes (forward-only, no --amend)
- Any deviations from plan with rationale
</output>
