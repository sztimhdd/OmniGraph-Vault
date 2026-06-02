---
phase: kdb-2.5
plan_id: kdb-2.5-02
slug: fullreindex-and-postcheck
wave: 2
depends_on:
  - kdb-2.5-01
estimated_time: 1d
requirements:
  - SEED-DBX-02
  - SEED-DBX-03
skills:
  - databricks-patterns
  - writing-tests
files_modified:
  - .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-FAILURES.csv
  - .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-VERIFICATION.md
  - .planning/STATE-kb-databricks-v1.md
autonomous: false

must_haves:
  truths:
    - "lightrag_storage/ target is verified empty before Step 2 trigger (D-07)"
    - "WRITE_VOLUME grant for hhu@edc.ca verified before triggering Step 2 (D-03)"
    - "Step 2 Job completes with final state SUCCEEDED or SUCCEEDED_WITH_FAILURES"
    - "Failure rate <= 5% of ~170 candidates (per ROADMAP rev 3 line 163)"
    - "kdb-2.5-FAILURES.csv copied to phase dir with content_hash + source_table + error_truncated"
    - "vdb_entities.json embedding_dim == 1024 (Qwen3-0.6B locked per REQUIREMENTS rev 3)"
    - "Bilingual entity coverage: >= 10 zh + >= 10 en in 200-entity sample (SEED-DBX-03)"
    - "2 round-trip aquery responses (1 zh + 1 en), each >= 50 chars (SEED-DBX-03)"
    - "kdb-2.5-VERIFICATION.md authored with all 5 ROADMAP success criteria assessed"
  artifacts:
    - path: ".planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-FAILURES.csv"
      provides: "Failed article hashes for selective retry"
    - path: ".planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-VERIFICATION.md"
      provides: "Phase verification with ROADMAP success criteria 1-5 assessed"
    - path: ".planning/STATE-kb-databricks-v1.md"
      provides: "Current Position updated + Last activity backfilled (2-forward-commit pattern)"
  key_links:
    - from: "kdb-2.5-VERIFICATION.md"
      to: "/Volumes/.../lightrag_storage/vdb_entities.json"
      via: "embedding_dim field check (SEED-DBX-03)"
      pattern: "embedding_dim.*1024"
    - from: "kdb-2.5-VERIFICATION.md"
      to: "databricks jobs runs get <run-id>"
      via: "Job final state citation"
      pattern: "run-id"
    - from: "kdb-2.5-FAILURES.csv"
      to: "kdb-2.5-VERIFICATION.md"
      via: "failure rate calculation (n_failed / n_total)"
      pattern: "failure_rate"
---

<objective>
Execute Step 2 (full re-index of ~170 DATA-07 candidates) and Step 3 (post-check sanity)
for phase kdb-2.5, then author the VERIFICATION document. This plan is GATED on Plan 01's
cost gate PASS — do not begin until kdb-2.5-SMALLBATCH-FINDINGS.md shows GATE: PASS.

Purpose: Complete the LightRAG knowledge-graph build on Databricks, producing the
`lightrag_storage/` artifacts that enable kdb-3 Smoke 3 KG-mode RAG round-trips.

Output:

- `/Volumes/.../lightrag_storage/` populated (vdb_*.json + graph_*.graphml + kv_store_*.json)
- `/Volumes/.../output/kdb-2.5-FAILURES.csv` (failed hashes, if any)
- `/Volumes/.../output/kdb-2.5-postcheck-stats.json` (Step 3 evidence)
- `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-FAILURES.csv` (local copy)
- `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-VERIFICATION.md`
- STATE-kb-databricks-v1.md "Current Position" + "Last activity" updated
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-RESEARCH.md
@.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-CONTEXT.md
@.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-01-SUMMARY.md
@.planning/REQUIREMENTS-kb-databricks-v1.md
@.planning/ROADMAP-kb-databricks-v1.md
@.planning/STATE-kb-databricks-v1.md

<interfaces>
<!-- Key artifacts produced by Plan 01 that this plan consumes. -->

From kdb-2.5-SMALLBATCH-FINDINGS.md (Plan 01 output):

- Step 1 avg_wallclock_per_ok: used for Step 2 burn-rate alert baseline
- Step 1 cost per article: used for Step 2 real-time cost monitoring
- Gate decision: MUST be PASS before this plan executes

From kdb-2.5-progress.csv (written by Step 1 run):

- OK content_hashes from Step 1: Step 2 resumes by skipping these (D-06 idempotency)

Volume paths (locked per STATE rev 3):

```
/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/
  lightrag_storage/              # must be EMPTY at Step 2 start (D-07)
  output/kdb-2.5-progress.csv   # Step 1 wrote these; Step 2 appends
  output/kdb-2.5-FAILURES.csv   # Step 2 writes failed hashes
  output/kdb-2.5-postcheck-stats.json  # Step 3 writes
```

Step 3 verification check shape (from RESEARCH Q4 _run_postcheck):

```python
# Verify in vdb_entities.json:
data["embedding_dim"] == 1024
# Sample entity names (up to 200):
n_zh = count(any char in '一'-'鿿')  # >= 10 expected
n_en = count(no CJK chars)           # >= 10 expected
# Round-trip queries:
resp_zh = await rag.aquery("LangGraph 与 CrewAI 的对比", QueryParam(mode="hybrid"))
resp_en = await rag.aquery("compare LangGraph and CrewAI frameworks", QueryParam(mode="hybrid"))
# Both len() >= 50
```

</interfaces>
</context>

<tasks>

<!-- ================================================================
Task 2.1 — WRITE_VOLUME pre-flight + empty-target verification
~0.5h; CRITICAL gate — BLOCKED if not satisfied
================================================================ -->
<task type="checkpoint:human-verify" gate="blocking">
<name>Task 2.1: WRITE_VOLUME pre-flight + empty-target verification (D-03 + D-07)</name>
<what-built>
Prerequisite checks before triggering Step 2. Two hard gates:
1. WRITE_VOLUME grant verified for hhu@edc.ca on the target Volume (D-03)
2. lightrag_storage/ is empty on the Volume (D-07 — Job must NOT silently overwrite)

These checks CANNOT be automated because the WRITE_VOLUME grant requires a SQL query
against the workspace and the Volume listing requires dbutils.fs or Databricks CLI with
filesystem access. The executor performs both checks and reports results.
</what-built>
<how-to-verify>
**Check 1 — WRITE_VOLUME grant:**

Run via Databricks MCP execute_sql (warehouse eaa098820703bf5f):

```sql
SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault
```

Expected: row with `grantee = 'hhu@edc.ca'` and `action_type = 'WRITE_VOLUME'`
(or 'ALL PRIVILEGES').

If not present, user must run:

```sql
GRANT WRITE_VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO `hhu@edc.ca`
```

Then re-verify before proceeding.

**Check 2 — Empty target:**

```bash
databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/ 2>&1
```

Expected for first run: "Error: Path does not exist" OR an empty listing.
If non-empty: STOP. Do not proceed. Ask user for explicit --force-overwrite intent.

**If both checks pass:**

- Type "pre-flight PASS — WRITE_VOLUME granted, lightrag_storage/ empty"

**If either check fails:**

- Type "pre-flight BLOCKED: [which check failed] — [details]"
- Do NOT proceed to Task 2.2 until resolved
</how-to-verify>

<resume-signal>
Type "pre-flight PASS — WRITE_VOLUME granted, lightrag_storage/ empty"
OR "pre-flight BLOCKED: [reason]"
</resume-signal>
</task>

<!-- ================================================================
Task 2.2 — Trigger Step 2 fullreindex + monitor + collect FAILURES.csv
~0.5h active + 1-8h Job run (async wait)
================================================================ -->
<task type="checkpoint:human-verify" gate="blocking">
<name>Task 2.2: Trigger Step 2 fullreindex, monitor burn-rate, collect FAILURES.csv</name>
<what-built>
Step 2 full re-index of all ~170 DATA-07 candidates. The Job runs for ~1-8 hours
(~30s/article × 170 at 1× concurrency per RESEARCH Q3). Executor triggers the Job,
monitors burn-rate vs Step 1 extrapolation, and collects FAILURES.csv when done.

BURN-RATE ALERT (ROADMAP rev 3 line 171): if Step 2 cost-rate exceeds Step 1
extrapolation × 1.5 by the 25-article mark → the Job logs a WARNING. If the executor
observes this warning in the streaming logs, STOP and escalate before proceeding.
</what-built>
<how-to-verify>
**Step A — Trigger Step 2:**

```bash
databricks bundle run kdb_2_5_reindex_fullrun -t dev
# Streams logs. Note the run-id from output.
```

Note: if lightrag_storage/ is non-empty from a previous attempt, operator must pass
`--params force-overwrite=true` explicitly (D-07 requirement). The YAML default does
NOT include this flag.

**Step B — Monitor progress (while Job runs):**
Every 30 min, check:

```bash
# Count OK rows in progress CSV:
databricks fs cat dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-progress.csv | grep ",ok," | wc -l

# Check for BURN-RATE WARNING in logs:
databricks jobs runs get-output <run-id> 2>&1 | grep "BURN-RATE alert"
```

If BURN-RATE alert appears AND cost looks like it will exceed $200: manually cancel + escalate.

**Step C — Wait for Job completion:**

```bash
databricks jobs runs get <run-id>
# Wait until state.life_cycle_state = "TERMINATED"
# Check state.result_state: "SUCCESS" or "SUCCESS" (exit code 0) or check for exit code 2 (>5% failures)
```

**Step D — Pull FAILURES.csv if any:**

```bash
databricks fs cp dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-FAILURES.csv \
  .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-FAILURES.csv
```

If file does not exist on Volume (zero failures): create an empty CSV with header row only:
`content_hash,source_table,error_truncated`

**Step E — Assess failure rate:**

```bash
# Count failed rows in progress CSV:
databricks fs cat dbfs:/Volumes/.../output/kdb-2.5-progress.csv | grep ",failed," | wc -l
# Failure rate = failed / (ok + failed + skipped)
```

If failure_rate > 5% (> 9 of ~170): PHASE REOPENED — type "Step 2 REOPENED: failure_rate = X%"
If failure_rate <= 5%: type "Step 2 PASS: ok=X failed=Y failure_rate=Z%"

**If >50% of FAILURES.csv rows contain "429" or "rate_limit_exceeded":**
This is rate-limit collapse, NOT corpus quality failure. Reduce MAX_ASYNC=2 and re-run.
Type "Step 2 REOPENED: 429 storm — reduce MAX_ASYNC to 2 and retry"

**On PASS:** provide run-id, n_ok, n_failed, failure_rate for Task 2.3.
</how-to-verify>
<resume-signal>
Type "Step 2 PASS: run-id=XXXX ok=X failed=Y failure_rate=Z%"
OR "Step 2 REOPENED: [reason]"
OR "Step 2 BURN-RATE ALERT: cost_rate=Xx extrapolation — escalating"
</resume-signal>
</task>

<!-- ================================================================
Task 2.3 — Step 3 postcheck + VERIFICATION authoring
~0.5-1h; fully automated except for VERIFICATION doc authoring
================================================================ -->
<task type="auto">
<name>Task 2.3: Step 3 postcheck + author kdb-2.5-VERIFICATION.md</name>
<files>
.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-VERIFICATION.md
.planning/STATE-kb-databricks-v1.md
</files>
<action>
Skill(skill="databricks-patterns", args="databricks bundle run kdb_2_5_reindex_postcheck -t dev. databricks jobs runs get for final state. databricks fs cat to read postcheck-stats.json from Volume. Structured log parsing for embedding_dim + bilingual coverage + round-trip query excerpts.")

Skill(skill="writing-tests", args="Assert embedding_dim == 1024 from postcheck-stats.json. Assert n_zh >= 10 and n_en >= 10 from bilingual sample. Assert len(zh_response) >= 50 and len(en_response) >= 50 from round-trip excerpts. These are SEED-DBX-03 acceptance criteria.")

**Step A — Trigger Step 3:**

```bash
databricks bundle run kdb_2_5_reindex_postcheck -t dev
# Note run-id, wait for completion (~30 min)
```

**Step B — Pull postcheck stats:**

```bash
databricks fs cat dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-postcheck-stats.json
```

Parse JSON: embedding_dim, bilingual_zh_count_in_sample, bilingual_en_count_in_sample,
zh_response_excerpt, en_response_excerpt.

**Step C — Verify SEED-DBX-03 criteria:**
Assert programmatically (can be a one-off Python snippet run locally):

```python
import json
data = json.loads(open(".../kdb-2.5-postcheck-stats.json").read())
assert data["embedding_dim"] == 1024, f"Expected 1024, got {data['embedding_dim']}"
assert data["bilingual_zh_count_in_sample"] >= 10, "zh coverage < 10"
assert data["bilingual_en_count_in_sample"] >= 10, "en coverage < 10"
assert len(data["zh_response_excerpt"]) >= 50, "zh round-trip too short"
assert len(data["en_response_excerpt"]) >= 50, "en round-trip too short"
print("SEED-DBX-03 PASS")
```

If any assertion fails: postcheck FAILED — phase REOPENED.

**Step D — Author kdb-2.5-VERIFICATION.md:**
Use the RESEARCH Q8 template. Populate all sections with real measured values:

- Phase ROADMAP success criteria table (5 rows: Job state, Volume populated, failure rate <= 5%, post-check, cost recorded)
- Step 1 small-batch findings (from SMALLBATCH-FINDINGS.md values)
- Step 2 full re-index (run-id, start/end time, wallclock, ok/failed counts, total cost from billing)
- Step 3 post-check (embedding_dim, n_zh, n_en, zh/en response excerpts)
- **NEW: kb-v2.2 F12 sync baseline measurements (nice-to-have, NOT a hard acceptance gate per orchestrator request 2026-05-17):**
  - **vdb file sizes** — `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` final byte sizes (use `find /Volumes/.../lightrag_storage/ -name 'vdb_*.json' -exec ls -la {} \;` to capture). Format as a small table with file + bytes + MB.
  - **Total LLM cost (Step 2 only)** — actual $ from Databricks billing dashboard or DBU/Model-Serving line items. Compare to v1.0.x reconcile_ingestions ghost-reduction cost baseline (Hermes; ~$X/day historical) — note absolute $ + ratio.
  - **Per-article entity extraction density** — distribution stats: avg / p50 / p90 entities per article (parse `vdb_entities.json` and group by source_id ↔ content_hash). Compare to Hermes current Vertex/DeepSeek pairing if a baseline number is available in CLAUDE.md or a recent quick. Flag if density differs by > 30% (could indicate prompt drift or chunk_token_size config diff).
  - **Coverage** — articles_processed / DATA-07_candidate_total (e.g., 165/170 = 97%). Cross-reference to FAILURES.csv count. Document any coverage delta from raw-row count (~2598) → DATA-07-filter (~170) → actually-processed.
  - **F12 sync baseline conclusion** — one-paragraph note: "Databricks-built KG vdb sizes are [comparable / N% larger / N% smaller] than Hermes current KG (~789 articles). F12 sync memory budget can use [baseline figure]. Investigate [factor] if delta > 30%."
- Files emitted list
- Skill discipline: Skill(skill="databricks-patterns"), Skill(skill="writing-tests")
- Commit ledger (forward-only hashes)
- Status: PASSED (if all criteria met) or REOPENED (if any failed)

**Step E — Update STATE-kb-databricks-v1.md:**
Update "Current Position" section:

```
- **Phase:** kdb-2.5 — Re-index LightRAG Storage (COMPLETE)
- **Status:** kdb-2.5 complete. SEED-DBX-02 (Step 1 + Step 2) + SEED-DBX-03 (Step 3) PASS.
  Job final state SUCCEEDED. Failure rate: X%. Post-check: dim=1024, bilingual zh=N en=N.
  Total cost: $X. Ready for kdb-3 (Smoke + UAT close).
- **Last activity:** <date> — kdb-2.5 fullreindex + postcheck shipped.
  Run-id: <run-id>. Commit hashes (forward-only): <hash> (VERIFICATION + STATE backfill).
```

This is the "2-forward-commit pattern" from STATE rev 3. Do NOT amend previous commits.

Commit order:

1. `docs(kdb-2.5-02): VERIFICATION + FAILURES.csv` — stages VERIFICATION.md + FAILURES.csv
2. `docs(kdb-2.5): backfill STATE-kb-databricks-v1.md phase complete` — stages STATE file only
Both commits explicit file paths; no git add -A.
</action>

<verify>
  <automated>
    cd C:\Users\huxxha\Desktop\OmniGraph-Vault && .venv/Scripts/python -c "
import json, pathlib, sys
stats_path = pathlib.Path('.planning/phases/kdb-2.5-reindex-lightrag-storage')
# Check VERIFICATION.md exists
v = stats_path / 'kdb-2.5-VERIFICATION.md'
assert v.exists(), 'VERIFICATION.md missing'
content = v.read_text(encoding='utf-8')
# Check ROADMAP criteria present
assert 'SEED-DBX-03' in content or 'embedding_dim' in content, 'VERIFICATION missing post-check evidence'
assert 'PASS' in content or 'REOPENED' in content, 'VERIFICATION missing status'
print('VERIFICATION checks PASS')
"
  </automated>
</verify>
<done>
- `databricks bundle run kdb_2_5_reindex_postcheck -t dev` completed successfully
- postcheck-stats.json: embedding_dim == 1024 (SEED-DBX-03)
- postcheck-stats.json: bilingual_zh_count_in_sample >= 10 AND bilingual_en_count_in_sample >= 10
- postcheck-stats.json: len(zh_response_excerpt) >= 50 AND len(en_response_excerpt) >= 50
- kdb-2.5-FAILURES.csv exists in phase dir (empty CSV if zero failures)
- kdb-2.5-VERIFICATION.md exists with all 5 ROADMAP success criteria assessed
- kdb-2.5-VERIFICATION.md contains "status: passed" (or "reopened" with explanation)
- STATE-kb-databricks-v1.md "Current Position" updated to kdb-2.5 COMPLETE
- Both artifacts committed with forward-only commits (no --amend, explicit file paths)
</done>
</task>

</tasks>

<verification>
## Phase kdb-2.5-02 verification

```bash
# 1. WRITE_VOLUME grant verified (done in Task 2.1 pre-flight)
# Recheck:
# databricks-mcp-server execute_sql: SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault

# 2. Volume lightrag_storage/ populated
databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage/ 2>&1 | head -20
# Expected: vdb_entities.json, vdb_chunks.json, vdb_relationships.json,
#           graph_chunk_entity_relation.graphml, kv_store_*.json (12 files total)

# 3. Failure rate check
databricks fs cat dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-progress.csv \
  | awk -F, 'NR>1{t++; if($3=="ok") ok++; if($3=="failed") f++} END{print "ok=" ok " failed=" f " total=" t " rate=" f/t}'
# Expected: rate <= 0.05

# 4. SEED-DBX-03 embedding dim
databricks fs cat dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-postcheck-stats.json \
  | python -c "import json,sys; d=json.load(sys.stdin); print('dim:', d['embedding_dim'])"
# Expected: dim: 1024

# 5. SEED-DBX-03 bilingual coverage
databricks fs cat dbfs:/Volumes/.../output/kdb-2.5-postcheck-stats.json \
  | python -c "import json,sys; d=json.load(sys.stdin); print('zh:', d['bilingual_zh_count_in_sample'], 'en:', d['bilingual_en_count_in_sample'])"
# Expected: both >= 10

# 6. SEED-DBX-03 round-trip response lengths
databricks fs cat dbfs:/Volumes/.../output/kdb-2.5-postcheck-stats.json \
  | python -c "import json,sys; d=json.load(sys.stdin); print('zh_len:', len(d['zh_response_excerpt']), 'en_len:', len(d['en_response_excerpt']))"
# Expected: both >= 50

# 7. VERIFICATION.md complete
grep "status:" .planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-VERIFICATION.md
# Expected: "status: passed"

# 8. CONFIG-DBX-01 check
git log cfe47b4..HEAD --grep '(kdb-' --name-only -- kb/ lib/ \
  | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' | sort -u
# Expected: empty output
```

</verification>

<success_criteria>
Plan 02 is complete when ALL of the following are true:

1. Task 2.1 pre-flight PASSED: WRITE_VOLUME grant confirmed for hhu@edc.ca; lightrag_storage/ empty before Step 2
2. Step 2 Job final state = SUCCEEDED or SUCCEEDED_WITH_FAILURES; failure rate <= 5%
3. 12 expected files present in `/Volumes/.../lightrag_storage/` (vdb_*.json + graph_*.graphml + kv_store_*.json)
4. kdb-2.5-FAILURES.csv exists in phase dir (may be header-only if zero failures)
5. Step 3 postcheck: embedding_dim == 1024 in vdb_entities.json
6. Step 3 postcheck: bilingual_zh_count_in_sample >= 10 AND bilingual_en_count_in_sample >= 10
7. Step 3 postcheck: zh and en round-trip responses each >= 50 chars
8. kdb-2.5-VERIFICATION.md exists with status: passed; all 5 ROADMAP criteria assessed
9. STATE-kb-databricks-v1.md "Current Position" updated to kdb-2.5 COMPLETE
10. All commits forward-only (no --amend, no git add -A, no git reset)
11. Zero modifications to: kdb-1.5 frozen files, CONFIG-EXEMPTIONS.md, kb/, lib/, top-level *.py

**If Step 2 failure rate > 5% → phase REOPENED:** Do NOT mark VERIFICATION.md as passed.
Analyze FAILURES.csv: if >50% are "429" → reduce MAX_ASYNC=2, retry. If corpus quality →
review failure hashes against kol_scan.db, selectively fix + retry with progress CSV resume.

**If Step 3 postcheck fails → phase REOPENED:** Likely kdb-1.5 factory bug or wrong endpoint.
Diagnostic: check lightrag_databricks_provider.py EMBEDDING_DIM constant (must be 1024).
Check that make_embedding_func() was not accidentally replaced. Roll back lightrag_storage/
artifacts on Volume (`databricks fs rm -r dbfs:/Volumes/.../lightrag_storage/`), fix factory,
re-run Step 1 + Step 2 from scratch with --force-overwrite.
</success_criteria>

<hard_constraints>
D-01: Job reads strict DATA-07 candidates; filter is hardcoded in Plan 01 script — no changes here.
D-02: This plan is Plan 02 (wave 2); Plan 01 must be PASS before this plan starts.
D-03: Job runs as hhu@edc.ca; WRITE_VOLUME pre-flight MUST pass before Task 2.2.
D-04: No ThreadPoolExecutor; single LightRAG instance (enforced in Plan 01 script).
D-05: Doc-status post-check is baked into _ingest_one (Plan 01 script); no changes here.
D-06: Idempotency via ids=[content_hash] (Plan 01 script); resume from progress CSV on retry.
D-07 CRITICAL: lightrag_storage/ MUST be verified empty before Task 2.2. If non-empty AND neither --init-empty nor --force-overwrite intent confirmed → BLOCKED. Operator must explicitly pass --params force-overwrite=true to databricks bundle run on retry.
ROADMAP gate (line 163): failure_rate > 5% → phase REOPENED; do NOT mark VERIFICATION as passed.
ROADMAP gate (line 165): Step 3 sanity fail → phase REOPENED.
CONFIG-DBX-01: ZERO modifications to kb/, lib/, top-level *.py, kdb-1.5 frozen files, CONFIG-EXEMPTIONS.md.
Concurrent safety: git add explicit files only; forward-only commits.
</hard_constraints>

<anti_patterns>

- DO NOT trigger Step 2 before WRITE_VOLUME pre-flight PASS (Task 2.1).
- DO NOT skip the empty-target check — the first Step 2 run is the ONLY run that starts on a clean Volume. Retries resume via progress CSV.
- DO NOT mark VERIFICATION as passed if failure_rate > 5% or any SEED-DBX-03 criterion fails.
- DO NOT modify lightrag_databricks_provider.py if postcheck fails — escalate to user first.
- DO NOT use git add -A (concurrent quick safety).
- DO NOT git commit --amend (2-forward-commit pattern: forward-only commits only).
- DO NOT classify 429-storm failures as "corpus quality" — different root cause, different fix.
- DO NOT skip updating STATE-kb-databricks-v1.md (2-forward-commit pattern required by milestone state machine).
</anti_patterns>

<output>
After completion, create `.planning/phases/kdb-2.5-reindex-lightrag-storage/kdb-2.5-02-SUMMARY.md`
containing:
- Step 2 run-id, total articles processed (ok/failed/skipped), wallclock, total cost
- Step 3 postcheck results (embedding_dim, n_zh, n_en, response lengths)
- Failure analysis if any failures (failure category distribution from FAILURES.csv)
- VERIFICATION status (passed / reopened)
- Explicit Skill invocations: Skill(skill="databricks-patterns"), Skill(skill="writing-tests"), Skill(skill="systematic-debugging")
- Commit hashes (forward-only)
- Any deviations from plan with rationale
</output>
