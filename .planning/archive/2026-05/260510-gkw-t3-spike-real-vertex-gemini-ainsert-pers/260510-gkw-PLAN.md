---
phase_id: quick-260510-gkw
description: T3 spike — real Vertex Gemini ainsert persistence contract investigation (multi-snapshot, single-doc + sequential 5-doc)
status: ready
type: quick
mode: quick
created: 2026-05-10
predecessor: quick-260509-t4i
---

# Quick Task 260510-gkw — T3 Real-Vertex `ainsert` Persistence Contract Spike

## Goal

Add `test_t3a_real_vertex_post_await_vs_post_finalize` and
`test_t3b_sequential_5_real_vertex_per_article_status` to the existing
`tests/unit/test_ainsert_persistence_contract.py`, run them against real
Vertex Gemini + real embedding, capture raw evidence to a `.scratch/`
log, and write a 6-section `T3-INVESTIGATION.md` isolating the production
bug surface.

**No fix.** This quick is investigative only — fix selection is the
user's call after reading the investigation.

## Background — Why This Spike Now

### Predecessor result (quick `260509-t4i`)

- T1 (single-doc, mock LLM/embed) — **PASSED**
- T2 (sequential 7-doc, mock LLM/embed) — **PASSED**
- T3 stub (`test_t3_real_vertex_gemini_single_doc`, line 187 of the test
  file) — **SKIPPED** by design (default skipif on SA file + env var).

T1+T2 GREEN with mocks rules out LightRAG single-doc and sequential-flush
breakage at the framework level. The bug lives in the **real
LLM / real embed / real network / real timing** layer — exactly what
T3a + T3b exercise.

### 2026-05-10 09:00 ADT cron forensic (Hermes)

- `ingestions` table: `status='ok' AND source='wechat' AND date=2026-05-10`
  → **4 rows**.
- LightRAG `kv_store_doc_status.json` today: **1 processed + 1 processing
  + 7 pending = 9 doc entries** (only 1-2 actually completed).
- `graph_chunk_entity_relation.graphml` mtime: **09:12 ADT**.
- `finalize_storages` log line: **09:33 ADT** — a **21-minute gap** between
  the last graphml write and finalize. The finalize phase did not actually
  flip pending docs to processed within the cron window.

### Hypothesis under test

> `await rag.ainsert(...)` returns ⇒ application marks `ingestions=ok`
> at the call-site, but LightRAG's `kv_store_doc_status` for that
> `doc_id` is **NOT yet `'processed'`** at that moment. The `'processed'`
> transition happens later — during a subsequent `finalize_storages()`
> call OR an async background merge — which the production cron path
> does not reliably await before exiting.

T3a probes a single doc with status snapshots at **post-await** and
**post-finalize** boundaries. T3b stresses the same path across 5
sequential docs to surface accumulation effects (per-article snapshots
+ a final post-finalize snapshot).

## Constraints

### Allowed file changes

- `tests/unit/test_ainsert_persistence_contract.py` — **APPEND ONLY**
  (T3a + T3b functions added after the existing T3). Do NOT touch T1,
  T2, or the existing `test_t3_real_vertex_gemini_single_doc`.
- `.planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/`
  — planning artifacts (this PLAN, the SUMMARY, T3-INVESTIGATION.md).
- `.scratch/ainsert-t3-vertex-<ts>.log` — gitignored evidence log;
  capture but do NOT `git add`.
- `.planning/STATE.md` — append a single row under
  `Last activity` (Task 3 only).

### Hard-forbidden file changes (executor MUST refuse)

- `lib/lightrag_embedding.py`, `lib/vertex_gemini_complete.py`,
  `lib/llm_complete.py` — no source change of any kind.
- `batch_ingest_from_spider.py`, `ingest_wechat.py` — production code
  untouched.
- Any other file under `tests/unit/` — only the named file may be edited.
- `requirements.txt`, `pyproject.toml`, `pytest.ini` — config untouched.
- The existing T1, T2, and T3 (`test_t3_real_vertex_gemini_single_doc`,
  line 187) — assertions and bodies must remain byte-identical.

### STOP gates (do NOT cross)

- NO production code change.
- NO SSH to Hermes.
- NO trigger of production cron / cleanup script.
- NO follow-up fix quick — INVESTIGATION ends with "fix is user's
  call, post-decision".
- After INVESTIGATION written and committed + pushed, executor STOPS.

### Anti-fabrication rules (ENFORCE)

- Honest pass/fail. RED is the **high-value** outcome (bug reproduces
  locally). Do NOT tweak assertions to coerce GREEN.
- T3a main assertion: `assert post_await_status == 'processed'` —
  literal string `==`, not set membership / `in {...}`.
- T3b main assertion: `assert not not_processed` where
  `not_processed = [(d, s) for d, s in snapshots if s != 'processed']`.
- INVESTIGATION must cite the exact `.scratch/ainsert-t3-vertex-<ts>.log`
  path and reference the 2026-05-10 09:00 ADT production evidence.
- NO promotional words ("verified working", "confirmed fixed",
  "all green"). State the actual outcome verbatim.
- Commit message body fills outcome placeholders with what actually
  happened — including HANG / asyncio.TimeoutError if that occurs.

---

## Tasks

### Task 1: Append T3a + T3b to `tests/unit/test_ainsert_persistence_contract.py`

**Files:** `tests/unit/test_ainsert_persistence_contract.py` (modify
— append-only after the existing T3 at line ~229).

**Action:**

Append two new async test functions following the design in
**APPENDIX A** (verbatim user spec). Both must:

1. Use `@pytest.mark.slow` + the same `@pytest.mark.skipif` pattern as
   the existing T3 (skip when SA JSON missing or
   `GOOGLE_CLOUD_PROJECT` empty).
2. Use `pytest.importorskip("lib.vertex_gemini_complete")` and
   `pytest.importorskip("lib.lightrag_embedding")` to discover real
   public names — same pattern as existing T3 (line 203-215).
3. Build `LightRAG(working_dir=str(tmp_path), llm_model_func=...,
   embedding_func=...)` and `await rag.initialize_storages()` before
   any ainsert call. Do NOT pass `embedding_dim=3072` — production
   `embedding_func` already wears `EmbeddingFunc` attrs via
   `wrap_embedding_func_with_attrs`.
4. Wrap each `ainsert` call in `asyncio.wait_for(..., timeout=300)`.
5. Read `tmp_path / "kv_store_doc_status.json"` directly via
   `json.loads(path.read_text(encoding="utf-8"))` — do NOT call any
   LightRAG public API for status. The bug surface is the file.
6. Use `time.monotonic()` for elapsed timing, `print(..., flush=True)`
   for status dumps so `--capture=no` shows them in real time.

**T3a — `test_t3a_real_vertex_post_await_vs_post_finalize(tmp_path)`:**

- One doc, content `"x" * 5000` (>= 1 chunk at default
  `chunk_token_size=1200`).
- `doc_id = "doc-t3a-real-001"`, pass `ids=[doc_id]` positionally.
- Capture three snapshots:
  - `post_await_status`: read `kv_store_doc_status.json[doc_id]['status']`
    immediately after `await asyncio.wait_for(rag.ainsert(...), 300)`
    returns. **Print** with `[T3a status] post-await: <status>`.
  - `post_await_elapsed`: `time.monotonic()` delta from before-ainsert
    to after-ainsert.
  - `post_finalize_status`: after `await rag.finalize_storages()`,
    re-read the same key. Print `[T3a status] post-finalize: <status>`.
  - `post_finalize_elapsed`: total `time.monotonic()` delta from
    before-ainsert through post-finalize.
- Print verdict line: `[T3a verdict] post-await={post_await_status}
  post-finalize={post_finalize_status} dt_await={post_await_elapsed:.1f}s
  dt_total={post_finalize_elapsed:.1f}s`.
- **Main assertion (literal):**
  `assert post_await_status == 'processed', f"contract violation:
  post-await status={post_await_status!r}, expected 'processed'"`.
- File-existence guards: if `kv_store_doc_status.json` missing at the
  post-await snapshot, raise AssertionError with "ainsert returned but
  status file does not exist".

**T3b — `test_t3b_sequential_5_real_vertex_per_article_status(tmp_path)`:**

- Build ONE rag instance shared across 5 sequential ainsert calls.
- For `i in range(5)`:
  - `doc_id = f"doc-t3b-{i:03d}"`
  - `content` ≈ 3KB unique per doc — recommended construction:
    `f"article-{i}-prefix " + ("lorem ipsum " * 200) + ("中文样本 " * 100)`
    (mixed ASCII + CJK, ~3KB ≥ chunk threshold). The point is unique
    content per doc so chunk-cache cannot mask state leak.
  - `await asyncio.wait_for(rag.ainsert(content, ids=[doc_id]), 300)`.
  - Snapshot per article: read the status JSON, capture
    `(doc_id, current_status)`, print `[T3b iter {i}] doc={doc_id}
    status={current_status} dt={iter_elapsed:.1f}s`.
- After loop: `await rag.finalize_storages()`, then re-read
  `kv_store_doc_status.json` and snapshot final statuses for all 5
  doc_ids.
- Compute `not_processed = [(d, s) for d, s in snapshots if s !=
  'processed']` for the **post-await** snapshot list (one per iter)
  AND a separate `not_processed_final` for the post-finalize list.
- Print verdict lines:
  - `[T3b verdict] post-await processed: {5 - len(not_processed)}/5`
  - `[T3b verdict] post-finalize processed: {5 - len(not_processed_final)}/5`
- **Main assertion (literal):** `assert not not_processed, f"contract
  violation: {len(not_processed)}/5 docs not 'processed' at post-await:
  {not_processed!r}"`.
- Do NOT short-circuit the loop on first failure — run all 5 iters so
  the X/5 ratio is observable in the log even if the first iter
  violates.

**Implementation hints (carry into executor task):**

- Helper `_read_doc_status(tmp_path: Path, doc_id: str) -> str | None`:
  returns `store[doc_id]['status']` if present, else `None`. File-not-
  found returns `None` (don't raise). Use this in both T3a and T3b
  snapshot points.
- Use `from __future__ import annotations` already at the top of the
  file — no import changes needed beyond `import time` if not present.
  (Verify: t4i version imports asyncio, json, os, Path, Any, np,
  pytest, LightRAG, EmbeddingFunc — `time` may need adding.)
- `pytestmark` style: do NOT add file-level pytestmark; T3a + T3b carry
  their own decorators (consistent with existing T3).
- Both functions named with `t3a_` / `t3b_` prefix so pytest-asyncio
  collects them under the same module.

**Verify:**

```bash
venv/Scripts/python -c "import ast; \
    ast.parse(open('tests/unit/test_ainsert_persistence_contract.py').read()); \
    print('SYNTAX OK')"
venv/Scripts/python -m pytest tests/unit/test_ainsert_persistence_contract.py \
    --collect-only -q
# Expect: 5 tests collected (t1, t2, original t3, t3a, t3b).
# All 3 slow tests show as deselected/skipped without -m slow + env vars.
```

Also confirm via grep that exactly **5** test functions exist:

```bash
grep -nE "^async def test_" tests/unit/test_ainsert_persistence_contract.py
# Expect 5 hits: t1, t2, t3, t3a, t3b.
```

And confirm T1, T2, original T3 bodies untouched:

```bash
git diff tests/unit/test_ainsert_persistence_contract.py | head -60
# Expect: only additions (lines starting with `+`) below the existing T3.
# Zero `-` lines (deletions) inside the existing T1/T2/T3 bodies.
```

**Done:** File parses, collects 5 test items, existing T1+T2+T3
untouched (zero `-` lines in their bodies), T3a + T3b decorated with
`@pytest.mark.slow` + `skipif`.

---

### Task 2: Run T3a + T3b under real Vertex Gemini, capture `.scratch` log

**Files:** `.scratch/ainsert-t3-vertex-<UTC-ts>.log` (new, gitignored).

**Action:**

Export the real-Vertex env block (executor must run these literally;
do NOT skip):

```bash
export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/.dev-runtime/gcp-paid-sa.json
export GOOGLE_CLOUD_PROJECT=$(python -c "import json; \
    print(json.load(open('.dev-runtime/gcp-paid-sa.json'))['project_id'])")
export GOOGLE_CLOUD_LOCATION=global
export OMNIGRAPH_LLM_PROVIDER=vertex_gemini
export OMNIGRAPH_LLM_MODEL=gemini-3.1-flash-lite-preview
export OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime
export DEEPSEEK_API_KEY=dummy   # defends against lib/__init__.py:35 import-time crash
```

Then run the slow suite:

```bash
mkdir -p .scratch
TS=$(date -u +%Y%m%dT%H%M%SZ)
venv/Scripts/python -m pytest \
    tests/unit/test_ainsert_persistence_contract.py \
    -v -m slow --capture=no 2>&1 \
    | tee .scratch/ainsert-t3-vertex-${TS}.log
echo "Exit: ${PIPESTATUS[0]}" >> .scratch/ainsert-t3-vertex-${TS}.log
```

`--capture=no` is mandatory — it ensures the `[T3a status]`,
`[T3a verdict]`, `[T3b iter ...]`, `[T3b verdict]` print lines flush
to stdout in real time and end up in the tee log.

Expected wall time: T3a ~3-5min; T3b ~15-25min (5 docs × ~5min/doc
real Vertex). Total **~30 min**. Do NOT abort early — let
`asyncio.wait_for(..., timeout=300)` decide if a single doc hangs.

**Verify:**

- Log file exists at `.scratch/ainsert-t3-vertex-<ts>.log`.
- Log contains the literal markers `[T3a verdict]` and either
  `[T3b verdict]` (loop completed) OR a `FAILED` line for T3a (loop
  never started). One of the two must appear.
- Capture (write down for Task 3 commit message):
  - T3a outcome: `PASSED`, `FAILED`, or `TIMEOUT (asyncio.TimeoutError)`.
  - T3b outcome: `PASSED`, `FAILED at iter X`, or `TIMEOUT at iter X`.
  - For each: the relevant log line range (e.g. "log L42-L78").
  - The `dt_await` and `dt_total` values from T3a verdict line.
  - The `X/5 post-await` and `Y/5 post-finalize` values from T3b
    verdict lines.

**Done:** Log captured. T3a and T3b outcomes observed and recorded.
**GREEN, RED, or HANG all acceptable** — RED / HANG are the
high-value outcomes for the investigation.

**Outcome interpretations (carry into INVESTIGATION):**

- **T3a PASSED + T3b PASSED 5/5:** Contract holds at single-article
  real-Vertex level. Bug is concurrent / batch / accumulation —
  reproduces only at >5 docs or under cron-loaded conditions.
- **T3a FAILED:** Contract violation reproduced locally at single-doc.
  Capture raw `post_await_status` string and the `dt_await` /
  `dt_total` diff. **HIGH-VALUE outcome** — bug surface narrowed to
  a deterministic single-doc reproducer.
- **T3a TIMEOUT (300s):** Reproduces production hang at single-article
  level. Capture stack trace from the `.scratch` log. Treat as
  contract violation (the contract requires `ainsert` to terminate;
  300s + non-termination is a violation).
- **T3a PASSED + T3b FAILED at iter N:** State leak reproduces at
  N-doc accumulation. Capture which iteration first violated and the
  observed status string.
- **T3b PASSED 5/5 post-await + post-finalize differs:** The
  finalize-phase write-back is the lifecycle step the production cron
  is missing — name this in INVESTIGATION § 5 next-quick recommendation.

---

### Task 3: Write `T3-INVESTIGATION.md`, write `260510-gkw-SUMMARY.md`, update `STATE.md`, atomic commit + push

**Files staged:**

- `tests/unit/test_ainsert_persistence_contract.py` (T3a + T3b appended)
- `.planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/260510-gkw-PLAN.md`
- `.planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/T3-INVESTIGATION.md` (new)
- `.planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/260510-gkw-SUMMARY.md` (new)
- `.planning/STATE.md` (single Last activity row appended; do not
  rewrite the whole file)

**Files NOT staged (verify with `git status` before commit):**

- `.scratch/ainsert-t3-vertex-<ts>.log` — gitignored. Confirm `git
  status` shows it under "Untracked files" but NOT under "Changes to
  be committed".
- Any file under `lib/` — confirm `git diff --cached lib/` is empty.
- Any file under root that was not listed above.

**Action — `T3-INVESTIGATION.md` structure (6 sections, mandatory):**

```markdown
# T3-INVESTIGATION — Real Vertex Gemini `ainsert` Persistence Contract

## 1. TL;DR (3 lines)

- T3a result: <PASSED | FAILED | TIMEOUT>
- T3b result: <X/5 post-await processed, Y/5 post-finalize processed>
- Root-cause inference (one sentence): <e.g. "post-await status is
  routinely 'processing', not 'processed'; the 'processed' flip
  happens during finalize_storages — production cron does not await
  finalize before marking ingestions=ok">

## 2. Test results (raw)

Cite `.scratch/ainsert-t3-vertex-<ts>.log` exact path. Inline the
relevant pytest -v stanzas (one for T3a, one for T3b) and the
`[T3a status]`, `[T3a verdict]`, `[T3b iter ...]`, `[T3b verdict]`
print lines verbatim. Use fenced code blocks; do not paraphrase.

## 3. Timing data

- T3a `dt_await`: <Xs>
- T3a `dt_total` (post-finalize): <Ys>
- T3a finalize-phase delta (`dt_total - dt_await`): <Zs>
- T3b per-iter `dt`: <list of 5 values>
- T3b total wall-clock: <sum + finalize>
- Sync-vs-async inference: state which timings are consistent with
  ainsert returning before persistence is complete (e.g. dt_await
  ≪ dt_total; or dt_finalize > 0 with status flipping during it).

## 4. Reproduces production bug?

Compare local results to 2026-05-10 09:00 ADT cron forensic:

- Production: 4 ingestions ok, 1-2 LightRAG processed, 21min
  graphml-vs-finalize gap.
- Local T3a: <does post-await status differ from post-finalize? If
  yes — same shape as production. If no — bug needs concurrency or
  batch volume to surface, T3b/larger-N spike needed>.
- Local T3b: <if not_processed > 0 at post-await, this matches the
  pending-status accumulation seen in production>.

State plainly: "REPRODUCES at single-doc level" / "REPRODUCES at
5-doc accumulation level" / "DOES NOT REPRODUCE locally — production
bug requires >5 docs or cron-loaded concurrency".

## 5. Next quick (fix range — NOT IN THIS QUICK)

This is NOT a fix proposal — it is a fix-options enumeration for the
user's decision.

Possible approaches (executor lists 2-4 options based on the
observed evidence):

1. **Add `await rag.finalize_storages()` after every `ainsert` in
   `ingest_wechat.py`.** LOC estimate: ~3 lines. Risk: per-article
   finalize may serialize batch throughput — measure on Hermes.
2. **Move the `ingestions=ok` write to AFTER a single
   `finalize_storages()` at end-of-batch in
   `batch_ingest_from_spider.py`.** LOC: ~10 lines. Risk: failure of
   one article's persistence would block the whole batch's
   ingestions ledger update.
3. **Poll `kv_store_doc_status.json[doc_id]['status'] == 'processed'`
   with a bounded wait after `await rag.ainsert`.** LOC: ~15 lines
   (helper + integration). Risk: bounded wait may exceed cron timeout
   on slow articles.
4. **<other option suggested by raw evidence>**

Recommend ONE as the lowest-risk first attempt, but explicitly state
"fix is the user's call, post-decision".

## 6. Open questions

List 2-5 questions raised by the evidence that this spike could not
answer (e.g. "Does `finalize_storages` itself await all background
tasks, or only flush in-memory caches?", "What is the actual
concurrency level of the production cron loop — N=1 sequential, or
N>1 via asyncio?"). These shape the next investigation if the chosen
fix doesn't hold.
```

**Action — `260510-gkw-SUMMARY.md`:**

Mirror the t4i SUMMARY format (predecessor). Sections: Outcome (T3a +
T3b verdicts), What Was Built (T3a + T3b function names + line ranges),
Local result (one-line summary), Log path (cite the exact `.scratch`
filename), What Was NOT Touched (surgical-change verification list —
match the t4i pattern), STOP gate (this quick is investigative; fix
deferred per user decision).

**Action — `STATE.md` update:**

Append a single line under the existing "Last activity" entry. Do NOT
rewrite the file. Example:

```
Last activity: 2026-05-10 - Completed quick task 260510-gkw: T3a + T3b real-Vertex ainsert contract spike — <T3a outcome>, <T3b X/5 ratio>; investigation at .planning/quick/260510-gkw-*/T3-INVESTIGATION.md, raw log at .scratch/ainsert-t3-vertex-<ts>.log; fix deferred per STOP gate
```

**Action — atomic commit + push:**

```bash
# Pull first — parallel quicks (Cognee retire / 09:00 forensic) may
# have pushed.
git pull --ff-only origin main

# Stage exactly the allowed files.
git add tests/unit/test_ainsert_persistence_contract.py
git add .planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/
git add .planning/STATE.md

# Confirm staging matches the allowed list.
git status --short
git diff --cached --stat

# Commit with full HEREDOC body (fill outcome placeholders honestly).
git commit -m "$(cat <<'EOF'
test(lightrag): T3 real Vertex contract spike — multi-snapshot ainsert persistence

Quick task 260510-gkw. Builds on 260509-t4i (T1+T2 mock PASSED).
T3a + T3b snapshot kv_store_doc_status.json at post-await and
post-finalize boundaries to isolate production bug surface.

2026-05-10 09:00 ADT cron evidence:
- ingestions ok wechat: 4
- LightRAG processed today: 1-2
- 21min finalize gap (graphml mtime 09:12 → 09:33)

T3a (single-doc multi-snapshot) result: <fill: PASSED|FAILED|HANG>
T3b (sequential 5-doc) result: <fill: X/5 post-await processed>

Investigation: .planning/quick/260510-gkw-t3-spike-real-vertex-gemini-ainsert-pers/T3-INVESTIGATION.md
Raw log: .scratch/ainsert-t3-vertex-<actual-ts>.log

No source code changed. Fix deferred per STOP gate.
EOF
)"

git log -1 --stat
git push origin main
```

**Verify:**

- `git status` clean post-commit (no unstaged changes to listed paths;
  `.scratch/...log` shown as untracked is expected).
- `git log -1 --stat` shows ONLY: `tests/unit/test_ainsert_persistence_contract.py`,
  the four planning files, `.planning/STATE.md`. NO `lib/`, NO root
  `*.py`, NO config files.
- Commit body has placeholders filled with the actual T3a / T3b
  outcomes from Task 2 and the actual `.scratch` filename.
- `git push` succeeds (clean fast-forward; no merge conflict).
- `git log origin/main -1` on the local copy matches the new HEAD.

**Done:** Single atomic commit pushed to `origin/main`. STATE.md row
visible. INVESTIGATION.md complete with all 6 sections. SUMMARY.md
mirrors outcome.

**STOP after Task 3.** Do NOT open a follow-up fix quick — fix
selection is the user's call after reading INVESTIGATION § 5.

---

## APPENDIX A — User-Supplied Design (Verbatim)

### Test function shapes

> **T3a — `test_t3a_real_vertex_post_await_vs_post_finalize`**
> Single doc, real Vertex Gemini LLM + real `embedding_func`. Capture
> status snapshots at:
> 1. **post-await** — immediately after
>    `await asyncio.wait_for(rag.ainsert(content, ids=[doc_id]), 300)`
>    returns. Read `kv_store_doc_status.json[doc_id]['status']`
>    directly off disk.
> 2. **post-finalize** — after `await rag.finalize_storages()`. Re-read
>    same key.
>
> Print verdict line including both statuses + elapsed timings.
> Main assertion: `post_await_status == 'processed'` (literal `==`).
>
> **T3b — `test_t3b_sequential_5_real_vertex_per_article_status`**
> Five sequential docs, ONE shared `LightRAG` instance, real Vertex
> stack. After each `ainsert`, snapshot per-article status. After loop,
> call `finalize_storages()` once and snapshot final per-article
> statuses.
>
> Main assertion: `not not_processed` where `not_processed` = list of
> `(doc_id, status)` tuples with `status != 'processed'` from the
> post-await snapshot list.
>
> Print verdict lines:
> - `[T3b verdict] post-await processed: X/5`
> - `[T3b verdict] post-finalize processed: Y/5`

### Env block (real Vertex)

```bash
export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/.dev-runtime/gcp-paid-sa.json
export GOOGLE_CLOUD_PROJECT=$(python -c "import json; print(json.load(open('.dev-runtime/gcp-paid-sa.json'))['project_id'])")
export GOOGLE_CLOUD_LOCATION=global
export OMNIGRAPH_LLM_PROVIDER=vertex_gemini
export OMNIGRAPH_LLM_MODEL=gemini-3.1-flash-lite-preview
export OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime
export DEEPSEEK_API_KEY=dummy
```

### Pytest invocation

```bash
venv/Scripts/python -m pytest tests/unit/test_ainsert_persistence_contract.py \
    -v -m slow --capture=no 2>&1 \
    | tee .scratch/ainsert-t3-vertex-$(date +%Y%m%d-%H%M%S).log
```

### `T3-INVESTIGATION.md` 6-section spec

1. **TL;DR** — 3 lines: T3a outcome, T3b X/5, root-cause inference.
2. **Test results raw** — pytest -v chunks + relevant `[T3 status]`
   print lines, cite `.scratch/...log` path.
3. **Timing data** — post-await elapsed, post-finalize elapsed,
   sync-vs-async inference.
4. **Reproduces production bug?** — compare to 09:00 ADT cron
   (4 ok / 1-2 processed).
5. **Next quick (fix range — NOT IN THIS QUICK)** — recommend
   approach (e.g. add finalize call after every ainsert, OR change
   ingestions=ok marker timing, OR add explicit doc_status='processed'
   wait), with LOC estimate + risk. Explicitly state "fix is user's
   call, post-decision".
6. **Open questions** — 2-5 questions the spike raised but could not
   answer.

### Anti-fabrication rules (verbatim)

- Honest pass/fail. RED is high-value. Do not tweak assertions to coerce GREEN.
- `post_await_status` is literal string compare — `==`, not `in {'processed', 'processing'}`.
- INVESTIGATION must cite `.scratch/ainsert-t3-vertex-<ts>.log` exact path.
- NO promotional words ("verified working", "confirmed fixed").

### STOP gates (verbatim)

- NO production code change (`lib/`, root `*.py`).
- NO SSH Hermes.
- NO trigger production cron / cleanup script.
- NO follow-up fix quick — INVESTIGATION ends with "fix is user's call, post-decision".
- After INVESTIGATION written, executor commits + pushes (this quick wraps up cleanly).

### Outcome interpretation table (verbatim)

| Outcome | Inference |
|---------|-----------|
| T3a PASSED + T3b 5/5 | Contract holds at single-doc real Vertex; bug is concurrent / batch / accumulation. |
| T3a FAILED | Contract violation reproduced at single-doc real Vertex. Capture raw post_await_status + timing diff. **HIGH-VALUE.** |
| T3a HANG (300s) | Reproduces production hang at single-doc level. Capture stack trace. |
| T3b post-await < 5/5 but post-finalize == 5/5 | Finalize-phase write-back is the missing lifecycle step in production cron. |
