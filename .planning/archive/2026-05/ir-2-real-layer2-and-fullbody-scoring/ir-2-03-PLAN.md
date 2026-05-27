---
phase: ir-2-real-layer2-and-fullbody-scoring
plan: 03
type: execute
wave: 3
depends_on:
  - "ir-2-00"
  - "ir-2-01"
  - "ir-2-02"
files_modified:
  - .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md
  - .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md
autonomous: false  # ends with a STOP gate — operator runs the actual Hermes deploy
requirements:
  - LF-2.4
  - LF-4.2

must_haves:
  truths:
    - "HERMES-DEPLOY.md is a complete operator runbook for ir-2: pre-flight, backup, pause cron, pull main, apply migration 007, verify schema, smoke 5 dry-run + 1 real, resume cron, first-cron watch, sign-off, two-path rollback. Mirrors ir-1's HERMES-DEPLOY structure."
    - "CLOSURE.md documents the LF-2.4 close-out smoke: real DeepSeek call against the 20-article spike sample (.scratch/layer2-spike/sample-20.json), passes the contract-faithful gate, references the evidence at .scratch/layer2-deepseek-validation-<ts>.md AND .scratch/layer2-deepseek-runner-<ts>.log."
    - "The close-out smoke runner is a NEW python file at .scratch/layer2-deepseek-runner.py (gitignored) — NOT committed. It imports lib.article_filter.layer2_full_body_score and runs against the 20-article sample. Output: 1 markdown report + 1 raw stdout log."
    - "Anti-fabrication: the CLOSURE.md MUST cite specific line numbers from the evidence files (e.g. 'see .scratch/layer2-deepseek-validation-<ts>.md L42-L60 for per-article verdict table'). NO summary statistics in CLOSURE.md without an accompanying line-reference."
    - "If the close-out smoke fails (DeepSeek API error / rate limit / non-JSON / 误杀 / 漏放 / etc), CLOSURE.md MUST report the failure truthfully — including 'all-batch NULL validates LF-2.6 failure mode' as a legitimate outcome — and STATE that LF-2.4 sign-off is DEFERRED to a follow-up smoke run."
    - "STOP gate: ir-2-03 plan ENDS at HERMES-DEPLOY.md authored + CLOSURE.md ship + close-out smoke evidence files written. Per user direction (2026-05-07 evening), agent does NOT SSH or trigger production cron."
  artifacts:
    - path: ".planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md"
      provides: "Operator runbook for ir-2 Hermes deploy (migration 007 + new lib code + cron resume)."
      min_lines: 120
      contains: "migration 007"
    - path: ".planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md"
      provides: "ir-2 close-out summary citing close-out smoke evidence file paths + line numbers. LF-2.4 verdict explicit. References ir-2-00..03 commit hashes."
      min_lines: 60
      contains: ".scratch/layer2-deepseek-validation-"
    - path: ".scratch/layer2-deepseek-runner.py"
      provides: "Close-out smoke runner — imports lib.article_filter.layer2_full_body_score (post-ir-2-00 real DeepSeek), reads sample-20.json, scores against ground truth, writes report + log."
      gitignored: true
      committed: false
      min_lines: 80
    - path: ".scratch/layer2-deepseek-validation-<ts>.md"
      provides: "Markdown report from close-out smoke. Contains: command + env, raw log file path, per-article table (id, gt verdict, l2 verdict, OK?), summary stats (误杀/漏放/reject rate), conclusion (LF-2.4 PASS/FAIL/DEFERRED)."
      gitignored: true
      committed: false
      min_lines: 40
    - path: ".scratch/layer2-deepseek-runner-<ts>.log"
      provides: "Raw stdout/stderr from the runner invocation. Used by .md report to cite specific log lines for any reported numbers."
      gitignored: true
      committed: false
  key_links:
    - from: ".planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md"
      to: "migrations/007_layer2_columns.py + lib/article_filter.py + batch_ingest_from_spider.py"
      via: "documented step-by-step shell commands"
      pattern: "python migrations/007_layer2_columns.py"
    - from: ".planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md"
      to: ".scratch/layer2-deepseek-validation-<ts>.md + .scratch/layer2-deepseek-runner-<ts>.log"
      via: "explicit file path references with line numbers"
      pattern: "see .scratch/layer2-deepseek-validation-"
---

<objective>
Wave 3: produce the operator-facing artifacts that close ir-2 locally so the user can decide when to run the actual Hermes deploy. Three deliverables:

1. **HERMES-DEPLOY.md** — operator runbook for ir-2 (migration 007 + new code).
2. **Close-out smoke** — real DeepSeek run against the 20-article spike sample, validating LF-2.4. Evidence lives in `.scratch/` (gitignored).
3. **CLOSURE.md** — phase closure document referencing the evidence file paths + line numbers, with LF-2.4 verdict explicit.

Per session direction this plan EXPLICITLY stops at "HERMES-DEPLOY.md authored + CLOSURE.md ship + close-out smoke evidence files written". No SSH, no production cron, no migration 007 against `data/kol_scan.db` (the local default).
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/ROADMAP-v3.5-Ingest-Refactor.md
@.scratch/layer2-validation-20260507-210423.md
@.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md
</execution_context>

<context>
@CLAUDE.md
</context>

<interfaces>
<!-- The ir-1 HERMES-DEPLOY.md (truthful re-author at f38138b) is the structural model.
     ir-2's runbook follows the same shape:
       1. Pre-flight (hostname, branch, HEAD)
       2. Backup (DB + cron registry — Lessons 2026-05-06 #2)
       3. Pull main
       4. Apply migration 007
       5. Verify schema
       6. Smoke 5 articles (dry-run, then 1 real)
       7. Resume cron / monitor
       8. First-cron watch with day-1 backlog warning
       9. STATE sign-off step (operator-side; agent does not write STATE-v3.5)
       10. Rollback path (commits revert + DB restore from backup) -->

<!-- Close-out smoke runner shape:

  1. Read .scratch/layer2-spike/sample-20.json (ground truth)
  2. Read .dev-runtime/data/kol_scan.db articles.body for each id
  3. Build ArticleWithBody list, chunk into LAYER2_BATCH_SIZE batches
  4. Call layer2_full_body_score (real DeepSeek via lib.article_filter)
  5. Compare verdict ('ok'/'reject') against ground truth verdict
  6. Compute 误杀 (gt=keep, l2=reject) and 漏放 (gt=reject, l2=keep) counts
  7. Write markdown report with line-numbered per-article table + summary
  8. Write raw stdout to a separate log file

The runner uses lib.article_filter directly (not the spike's google.genai
direct call), so this is a true contract-faithful execution: same async
batching, same prompt, same persistence helper shape (though we only call
score() here, not persist — the smoke is read-only against DB).

The runner output is ALWAYS written, even if some batches fail (whole-batch
NULL = legitimate LF-2.6 outcome that the report must record). -->
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 4.1: Author HERMES-DEPLOY.md operator runbook</name>
  <read_first>
    - .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md (template)
    - migrations/007_layer2_columns.py (the runner this runbook references)
    - .planning/STATE-v3.5-Ingest-Refactor.md § Hermes operational state (current cron registry — DO NOT modify, READ ONLY)
  </read_first>
  <files>.planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md</files>
  <behavior>
    - Self-contained runbook; same Step 0-10 + Rollback structure as ir-1's.
    - Migration 007 (Layer 2 columns) replaces ir-1's migration 006 references.
    - Step 6 dry-run smoke now exercises BOTH Layer 1 + Layer 2 (per-batch logs `[layer1] batch` AND `[layer2] batch`).
    - Step 7 1-article real ingest is the gating happy-path on Hermes (Layer 2 happy path was NOT exercised locally in this plan — close-out smoke uses local DeepSeek; Step 7 is the production-key end-to-end gate).
    - Day-1 backlog warning extended to acknowledge BOTH layer1 + layer2 columns will be NULL on every backlog row → expect 2 LLM calls per article on first cron.
    - Reject-rate sanity adds: Layer 2 reject rate on filtered sample ≥ 30% (some "ok" must filter to "reject" via depth gate; if Layer 2 is rejecting nothing, the prompt is broken).
    - Rollback path A: revert ir-2-00..03 commits in reverse order (mirroring ir-1 rollback). layer2_* columns can stay (NULL-defaulted, ignored by reverted code).
  </behavior>
  <action>
**Create `.planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md`** modeled on ir-1's structure. The file is too large to inline-quote here in full; the implementer must write it from scratch using ir-1 as the template + the spike report's failure-mode mapping.

Mandatory sections (preserve order):

1. **Header** with REQ + Scope + Pre-condition + Operator note.
2. **Step 0 — Pre-flight** (local: git log/status/rev-parse).
3. **Step 1 — Connect to Hermes** (SSH details from memory file; cd ~/OmniGraph-Vault).
4. **Step 2 — Backup** (DB + cron registry per CLAUDE.md Lessons 2026-05-06 #2).
5. **Step 3 — Pause `daily-ingest` cron** (`hermes cron disable daily-ingest`).
6. **Step 4 — Pull main + verify HEAD matches**.
7. **Step 5 — Apply migration 007**:
   ```bash
   python migrations/007_layer2_columns.py data/kol_scan.db
   sqlite3 data/kol_scan.db "PRAGMA table_info(articles)"     | grep layer2_
   sqlite3 data/kol_scan.db "PRAGMA table_info(rss_articles)" | grep layer2_
   # Re-run for idempotency:
   python migrations/007_layer2_columns.py data/kol_scan.db
   ```
8. **Step 6 — Smoke 5 articles (dry-run)** — log should contain `[layer1] batch` lines (Layer 1 fires under dry-run per LF-3.6); `[layer2] batch` lines do NOT appear under dry-run (Layer 2 is gated by the per-candidate body which dry-run short-circuits).
9. **Step 7 — Smoke 1 article (real ingest)** — gating happy-path. Log MUST contain `[layer1] batch ... null=0` AND `[layer2] batch ... null=0`. DB query must show both `layer1_verdict` AND `layer2_verdict` populated for the 1 article.
10. **Step 8 — Resume `daily-ingest` cron**.
11. **Step 9 — First-cron-run watch**:
    - Day-1 backlog: every backlog row needs Layer 1 + Layer 2; expect 2× the LLM cost vs. ir-1's day-1.
    - Reject rate sanity: Layer 1 50-70% (per ir-1 spike); Layer 2 reject rate on `verdict='candidate'` rows ≥ 30% (per Layer 2 spike's 55% on hand-curated sample).
    - If `[layer2] batch ... null != 0` on multiple consecutive batches → DeepSeek API issue. Rows stay layer2_verdict=NULL → re-eval next tick. Investigate via the failure mode mapping (timeout / non_json / partial_json / row_count_mismatch).
12. **Step 10 — Sign-off** (STATE-v3.5-Ingest-Refactor.md update — agent does NOT touch sibling docs; operator does this manually post-deploy).
13. **Rollback Path A** (revert ir-2-03 → ir-2-02 → ir-2-01 → ir-2-00; layer2_* columns stay NULL-defaulted).
14. **Rollback Path B** (DB backup restore).
15. **STOP gate** explicit per session direction.
16. **References** including spike report path + close-out smoke evidence path placeholders.

Reference ir-1 HERMES-DEPLOY.md (truthful version at commit f38138b) for exact wording of warnings, command formats, and rollback ordering. Adapt all `migration 006` / `layer1_*` references to `migration 007` / `layer2_*` (or both, where applicable for first-cron-run sanity checks).

**HARD CONSTRAINTS:**
- DO NOT include real SSH hostnames, ports, or usernames.
- DO NOT execute any of the runbook commands during this plan's execute step.
- Day-1 backlog warning must surface that BOTH layer1 AND layer2 are first-time-evaluated post-migration.
- Reject-rate sanity must include BOTH layer1 (50-70% per ir-1 spike) and layer2 (≥30% on Layer-1-passed rows per Layer 2 spike).
- The runbook does NOT replace operator judgment.
  </action>
  <verify>
    <automated>test -f .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md && wc -l .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md | awk '{print $1}' | grep -qE "^[0-9]{3,}$" && echo "len ok"</automated>
    <automated>grep -c "migration 007" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md | grep -qE "^[2-9]|^1[0-9]" && echo "mig007 refs ok"</automated>
    <automated>grep -q "Day-1 backlog" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md && grep -q "Rollback" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md && grep -q "STOP gate" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md && echo "sections ok"</automated>
  </verify>
  <acceptance_criteria>
    - File exists, ≥120 lines.
    - Contains literal `migration 007` (referenced multiple times in steps 5/6/9/rollback).
    - Contains literal `Day-1 backlog warning` AND mentions BOTH layer1 + layer2 first-time-eval impact.
    - Contains BOTH rollback paths (Path A simple commits-revert + Path B DB restore).
    - Contains explicit STOP gate section per user direction.
    - Does NOT contain literal IP addresses, real port numbers, or real usernames.
    - References .scratch/layer2-deepseek-validation-<ts>.md as the LF-2.4 close-out smoke evidence file.
  </acceptance_criteria>
  <done>LF-4.2 delivered. Hermes deploy is now operator-ready behind an explicit STOP gate.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 4.2: Author + run close-out smoke (real DeepSeek)</name>
  <read_first>
    - .scratch/layer2-spike/sample-20.json (ground truth — 20 article ids + expected verdicts)
    - .scratch/layer2-spike/runner.py (spike runner — structural template, but uses Vertex Gemini directly; close-out runner uses lib.article_filter instead)
    - lib/article_filter.py post ir-2-00 (real layer2_full_body_score)
    - .scratch/layer2-validation-20260507-210423.md (spike report — gives the expected reject-rate band for sanity checks)
  </read_first>
  <files>.scratch/layer2-deepseek-runner.py (gitignored, not committed)</files>
  <behavior>
    - **Smoke runner location:** `.scratch/layer2-deepseek-runner.py` (NEW file, gitignored, NOT committed).
    - **Inputs:** `.scratch/layer2-spike/sample-20.json` (ground truth), `.dev-runtime/data/kol_scan.db` (article bodies).
    - **Outputs:** `.scratch/layer2-deepseek-validation-<ts>.md` (markdown report) + `.scratch/layer2-deepseek-runner-<ts>.log` (raw stdout/stderr).
    - **Implementation:**
      1. Load sample-20.json (`{"articles": [{id, title, gt_verdict, gt_depth_score, gt_relevant, ...}]}`).
      2. Connect to .dev-runtime DB; for each id, fetch `body` from articles table; truncate to 8000 chars.
      3. Build `ArticleWithBody` list of 20.
      4. Chunk into 4 batches of LAYER2_BATCH_SIZE=5.
      5. For each batch: `await layer2_full_body_score(arts)`; record results + per-batch wall_clock.
      6. Compare each result.verdict against ground truth verdict.
      7. Compute 误杀 (gt='keep' AND l2='reject') and 漏放 (gt='reject' AND l2='ok') counts.
      8. Write markdown report referencing the raw log file path + per-article line numbers.
      9. Print all batch summaries to stdout (captured by `tee` to the log file).
    - **Failure handling:** if any batch returns all-NULL (LF-2.6), the runner records the failure in the report under "Failure modes encountered" and continues with the next batch. The summary at the end states whether the smoke was complete (all 4 batches got verdicts) or partial (some batches NULL).
    - **LF-2.4 verdict logic:** PASS iff (誤殺 == 0 AND 漏放 == 0 AND null_batches == 0). Otherwise FAIL with explicit reason.
    - **Smoke is NON-COMMITTED.** Both the runner script and the output files live in `.scratch/` (gitignored). CLOSURE.md (Task 4.3) is the committed reference to the smoke results.
    - **Cost discipline:** 4 batches × 5 articles ≈ 4 DeepSeek API calls. Spike report estimates ~¥0.13 total. User's budget is ¥1.
  </behavior>
  <action>
1. **Verify .dev-runtime DB has the 20 sample articles**:

```bash
python -c "
import json, sqlite3
sample = json.loads(open('.scratch/layer2-spike/sample-20.json').read())
ids = [a['id'] for a in sample['articles']]
print('sample size:', len(ids))
conn = sqlite3.connect('.dev-runtime/data/kol_scan.db')
present = sum(1 for i in ids if conn.execute('SELECT 1 FROM articles WHERE id=?', (i,)).fetchone())
print('articles present in DB:', present, '/', len(ids))
"
```

If `articles present in DB` < 20: STOP. Do not proceed; investigate sample drift.

2. **Verify DEEPSEEK_API_KEY availability + Layer 2 model env**:

```bash
grep -E "^DEEPSEEK_API_KEY=" .dev-runtime/.env > /dev/null 2>&1 && echo "key set" || echo "key MISSING"
grep -E "^DEEPSEEK_MODEL=" .dev-runtime/.env  || echo "DEEPSEEK_MODEL not set; default deepseek-v4-flash will apply"
```

If key missing: STOP and document in CLOSURE.md — LF-2.4 sign-off DEFERRED until API key provisioned.

3. **Author `.scratch/layer2-deepseek-runner.py`** (gitignored). Pseudocode shape:

```python
"""ir-2 close-out smoke — real DeepSeek validation against 20-article spike sample.

Hard constraints:
  - Imports lib.article_filter.layer2_full_body_score (post ir-2-00 real DeepSeek)
  - Reads .scratch/layer2-spike/sample-20.json (ground truth)
  - Reads .dev-runtime/data/kol_scan.db articles.body
  - Writes .scratch/layer2-deepseek-validation-<ts>.md + .log
  - Anti-fabrication: every reported number cites a log line
"""
from __future__ import annotations
import asyncio, json, os, sqlite3, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / ".scratch" / "layer2-spike" / "sample-20.json"
DB = REPO / ".dev-runtime" / "data" / "kol_scan.db"

BATCH = 5  # LAYER2_BATCH_SIZE
TRUNC = 8000  # LAYER2_BODY_TRUNCATION_CHARS

async def main():
    from lib.article_filter import (
        ArticleWithBody, layer2_full_body_score, PROMPT_VERSION_LAYER2,
    )

    ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = REPO / ".scratch" / f"layer2-deepseek-runner-{ts}.log"
    md_path = REPO / ".scratch" / f"layer2-deepseek-validation-{ts}.md"

    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    articles_meta = sample["articles"]  # 20 entries
    ids = [a["id"] for a in articles_meta]
    gt = {a["id"]: {"verdict": a["gt_verdict"], "depth": a.get("gt_depth_score"), "relevant": a.get("gt_relevant")} for a in articles_meta}

    conn = sqlite3.connect(str(DB))
    bodies = {}
    for i in ids:
        row = conn.execute("SELECT title, COALESCE(body, '') FROM articles WHERE id=?", (i,)).fetchone()
        if row is None:
            print(f"FATAL: id={i} missing from {DB}", file=sys.stderr)
            sys.exit(1)
        bodies[i] = (row[0], row[1][:TRUNC])

    arts = [ArticleWithBody(id=i, source="wechat", title=bodies[i][0] or "", body=bodies[i][1]) for i in ids]
    chunks = [arts[i:i+BATCH] for i in range(0, len(arts), BATCH)]

    print(f"=== close-out smoke runner ts={ts} ===")
    print(f"sample size: {len(arts)}")
    print(f"prompt_version: {PROMPT_VERSION_LAYER2}")
    print(f"deepseek model: {os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash (default)')}")
    print(f"batch size: {BATCH}")
    print()

    all_results = []
    null_batches = 0
    for idx, chunk in enumerate(chunks):
        t0 = time.monotonic()
        results = await layer2_full_body_score(chunk)
        wall = time.monotonic() - t0
        null_count = sum(1 for r in results if r.verdict is None)
        ok_count = sum(1 for r in results if r.verdict == "ok")
        rej_count = sum(1 for r in results if r.verdict == "reject")
        if null_count == len(results):
            null_batches += 1
            err = results[0].reason if results else "empty"
            print(f"[batch {idx}] FAILED null={null_count} reason={err} wall_s={wall:.2f}")
        else:
            print(f"[batch {idx}] ok={ok_count} reject={rej_count} null={null_count} wall_s={wall:.2f}")
        all_results.append((chunk, results))

    # Score
    misshits, missdrops, exact_matches = 0, 0, 0
    table_lines = []
    for chunk, results in all_results:
        for art, res in zip(chunk, results):
            gt_v = gt[art.id]["verdict"]  # 'keep' or 'reject'
            l2_v = res.verdict  # 'ok' or 'reject' or None
            l2_keep = (l2_v == "ok")
            gt_keep = (gt_v == "keep")
            if l2_v is None:
                ok_flag = "NULL"
            elif l2_keep == gt_keep:
                ok_flag = "✓"
                exact_matches += 1
            elif gt_keep and not l2_keep:
                misshits += 1
                ok_flag = "✗ 误杀"
            else:
                missdrops += 1
                ok_flag = "✗ 漏放"
            line = f"| {art.id} | {art.title[:40]} | {gt_v} | {l2_v} | {ok_flag} | {res.reason[:40]} |"
            table_lines.append(line)
            print(line)

    print()
    print(f"=== summary ===")
    print(f"exact matches: {exact_matches}/{len(arts)}")
    print(f"误杀 (false negatives, gt=keep l2=reject): {misshits}")
    print(f"漏放 (false positives, gt=reject l2=keep): {missdrops}")
    print(f"NULL batches: {null_batches}/{len(chunks)}")
    print(f"reject rate: {sum(1 for _, results in all_results for r in results if r.verdict == 'reject')}/{len(arts)}")

    lf24_pass = (misshits == 0 and missdrops == 0 and null_batches == 0)
    print(f"LF-2.4 gate: {'PASS' if lf24_pass else 'FAIL'}")

    # Write markdown report
    md = f"""# ir-2 Close-out Smoke — Real DeepSeek Validation

**Date:** {ts}
**Sample:** 20 articles from .scratch/layer2-spike/sample-20.json
**Model:** {os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash (default)')}
**Prompt version:** {PROMPT_VERSION_LAYER2}

## Raw log

See: `.scratch/layer2-deepseek-runner-{ts}.log`

## Per-article verdicts

| id | title | gt verdict | l2 verdict | OK? | l2 reason |
|---|---|---|---|---|---|
{chr(10).join(table_lines)}

## Summary

| Metric | Value |
|---|---|
| exact matches | {exact_matches}/{len(arts)} |
| 误杀 (gt=keep, l2=reject) | {misshits} |
| 漏放 (gt=reject, l2=keep) | {missdrops} |
| NULL batches | {null_batches}/{len(chunks)} |
| reject rate | {sum(1 for _, results in all_results for r in results if r.verdict == 'reject')}/{len(arts)} |

## LF-2.4 verdict

**{"PASS" if lf24_pass else "FAIL"}**

{"Contract-faithful close-out gate satisfied: 0 误杀, 0 漏放, 0 NULL batches against the spike-validated 20-article sample on real DeepSeek." if lf24_pass else "Close-out gate failed — see breakdown above. Re-run after addressing the failure mode (DeepSeek prompt tuning / API issue / sample drift)."}
"""
    md_path.write_text(md, encoding="utf-8")
    print(f"\nReport written: {md_path}")
    print(f"Log expected at: {log_path}")

if __name__ == "__main__":
    asyncio.run(main())
```

4. **Run the smoke**:

```bash
TS=$(date +%Y%m%d-%H%M%S)
set -a && . .dev-runtime/.env && set +a
python .scratch/layer2-deepseek-runner.py 2>&1 | tee .scratch/layer2-deepseek-runner-${TS}.log
```

The runner writes the .md alongside; the bash `tee` writes the .log.

5. **Verify both output files exist and have content**:

```bash
ls -la .scratch/layer2-deepseek-validation-*.md .scratch/layer2-deepseek-runner-*.log | tail -2
wc -l .scratch/layer2-deepseek-validation-*.md .scratch/layer2-deepseek-runner-*.log
```

6. **Capture the latest TS for use in CLOSURE.md** (Task 4.3).

**HARD CONSTRAINTS:**
- The runner file at `.scratch/layer2-deepseek-runner.py` MUST stay gitignored. Verify with `git check-ignore -v .scratch/layer2-deepseek-runner.py`.
- The output `.md` and `.log` files MUST stay gitignored.
- Do NOT commit `.scratch/` content.
- If DEEPSEEK_API_KEY is missing or smoke fails: write the markdown report anyway with the failure mode documented; CLOSURE.md will reflect DEFERRED status.
- Anti-fabrication: every numeric claim in the runner-output .md MUST trace to a stdout line in the .log file. The `tee` capture is the source of truth.
  </action>
  <verify>
    <automated>test -f .scratch/layer2-deepseek-runner.py && echo "runner present"</automated>
    <automated>ls .scratch/layer2-deepseek-validation-*.md 2>&1 | tail -1</automated>
    <automated>ls .scratch/layer2-deepseek-runner-*.log 2>&1 | tail -1</automated>
    <automated>git check-ignore -v .scratch/layer2-deepseek-runner.py 2>&1 | grep -q ".gitignore" && echo "runner gitignored ok"</automated>
  </verify>
  <acceptance_criteria>
    - `.scratch/layer2-deepseek-runner.py` exists, gitignored.
    - `.scratch/layer2-deepseek-validation-<ts>.md` exists with the per-article table + summary block + LF-2.4 verdict, gitignored.
    - `.scratch/layer2-deepseek-runner-<ts>.log` exists with raw stdout from the run, gitignored.
    - Markdown report references the log file path explicitly.
    - If smoke succeeds: LF-2.4 verdict is PASS.
    - If smoke fails (any batch NULL OR any 误杀/漏放): LF-2.4 verdict is FAIL with explicit failure reason; runner exit code is still 0 (failure is reported, not raised).
  </acceptance_criteria>
  <done>LF-2.4 close-out smoke evidence captured. Outcome (PASS / FAIL / DEFERRED) recorded in `.scratch/layer2-deepseek-validation-<ts>.md` for CLOSURE.md to reference.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 4.3: Author CLOSURE.md citing smoke evidence by line number</name>
  <read_first>
    - .scratch/layer2-deepseek-validation-<ts>.md (just produced — extract verdict + line numbers)
    - .scratch/layer2-deepseek-runner-<ts>.log (just produced — count lines for citations)
    - .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md (just authored)
    - git log --oneline -10 (capture ir-2-00..03 commit hashes)
  </read_first>
  <files>.planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md</files>
  <behavior>
    - CLOSURE.md is the COMMITTED summary of ir-2 phase completion.
    - References ir-2-00..03 commit hashes (planning + execute).
    - References the gitignored close-out smoke evidence files by exact path + line number citations.
    - Documents LF-2.4 verdict (PASS / FAIL / DEFERRED) WITHOUT re-stating the underlying numbers — instead, "see .scratch/layer2-deepseek-validation-<ts>.md L<N>".
    - Lists deviations and unknowns explicitly.
    - Ends with the STOP gate notice (mirroring ir-1's CLOSURE pattern, if any).
  </behavior>
  <action>
**Create `.planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md`** with the following structure:

```markdown
# ir-2 Phase Closure — Real Layer 2 + full-body scoring

**Date:** <YYYY-MM-DD HH:MM ADT>
**Phase:** v3.5-Ingest-Refactor / ir-2
**Status:** Code complete + close-out smoke captured. Hermes deploy gated by operator (HERMES-DEPLOY.md).

## Commits

| Wave | Plan | Commit | Description |
|---|---|---|---|
| 1 | ir-2-00 | <full sha> | feat(ir-2): real Layer 2 DeepSeek impl + persistence + migration 007 |
| 2 | ir-2-01 | <full sha> | feat(ir-2): rewire ingest loop to batched Layer 2 |
| 2 | ir-2-02 | <full sha> | test(ir-2): LF-2.8 6-case Layer 2 unit suite |
| 3 | ir-2-03 | <full sha> | docs(ir-2): HERMES-DEPLOY runbook + close-out smoke evidence |

(Pull from `git log --oneline -10` after each execute commit lands.)

## REQ coverage

| REQ | Plan | Status |
|---|---|---|
| LF-2.1 | ir-2-00 | done — `lib.article_filter.layer2_full_body_score` is async batch |
| LF-2.2 | ir-2-00 | done — LAYER2_BATCH_SIZE=5, LAYER2_TIMEOUT_SEC=60 |
| LF-2.3 | ir-2-00 | done (operator-config) — calls `lib.llm_deepseek.deepseek_model_complete`; deepseek-chat is operator-set via DEEPSEEK_MODEL env. **Deviation note**: REQ pinned `deepseek-chat`; module default is `deepseek-v4-flash`. ir-2 does not enforce model name at code level. |
| LF-2.4 | ir-2-03 | <PASS / FAIL / DEFERRED> — see `.scratch/layer2-deepseek-validation-<ts>.md` L<N>-L<M> for per-article table + L<P>-L<Q> for summary |
| LF-2.5 | ir-2-00 | done — migration 007 + verdict alphabet 'ok'/'reject' |
| LF-2.6 | ir-2-00 | done — failure modes (timeout / non_json / partial_json / row_count_mismatch) wired |
| LF-2.7 | ir-2-00 | done — prompt_version bump constant + persistence |
| LF-2.8 | ir-2-02 | done — see commit ir-2-02 (6 cases + 2 regressions); pytest output cited in commit body |
| LF-3.2 | ir-2-01 | done — `_drain_layer2_queue` batched accumulator |
| LF-3.3 | ir-2-01 | done — Layer 2 reject → INSERT OR REPLACE INTO ingestions(status='skipped') |
| LF-4.2 | ir-2-03 | done — HERMES-DEPLOY.md authored; STOP gate held |

## Close-out smoke evidence (LF-2.4)

Runner: `.scratch/layer2-deepseek-runner.py` (gitignored)
Log: `.scratch/layer2-deepseek-runner-<ts>.log` (gitignored, <N> lines)
Report: `.scratch/layer2-deepseek-validation-<ts>.md` (gitignored, <M> lines)

Per-article verdict table: see report L<X>-L<Y>.
Summary stats (误杀 / 漏放 / null_batches / reject rate): see report L<P>-L<Q>.
LF-2.4 verdict line: see report L<R>.

**Verdict-line text (verbatim from report L<R>):**

> <copy-paste the exact verdict line>

## Deviations

1. **LF-2.3 model name pin** — REQ specifies `deepseek-chat`; module default is `deepseek-v4-flash`. Operator sets `DEEPSEEK_MODEL=deepseek-chat` in `~/.hermes/.env` if strict compliance is required. (Documented in ir-2-00-PLAN.md.)
2. **Layer 2 spike substitute model** — original `.scratch/layer2-validation-20260507-210423.md` ran on Vertex Gemini Flash Lite (not DeepSeek). The close-out smoke at ir-2-03 is the contract-faithful re-validation against real DeepSeek; result captured in CLOSURE.md above.
3. **`ingestions.reason` column not added** — preserved deviation from ir-1. Layer 2 reject reason logged at INFO level + persisted to `articles.layer2_reason`.

## Unknowns

- Hermes-side first-cron-run wall-clock and reject rate (deferred to operator post-deploy; see HERMES-DEPLOY.md Step 9).
- DeepSeek prompt-faithfulness over time (drift between `deepseek-v4-flash` and `deepseek-chat`; close-out smoke captures one snapshot only).

## STOP gate

Per session direction (2026-05-07 evening): agent does NOT SSH or trigger production cron. Operator triggers Hermes deploy at chosen window per HERMES-DEPLOY.md.

After deploy: ir-3 (production cutover + 1-week observation) starts at operator's next session. ir-3 is observation-only — no code changes.

## References

- PROJECT-v3.5-Ingest-Refactor.md
- REQUIREMENTS-v3.5-Ingest-Refactor.md
- ROADMAP-v3.5-Ingest-Refactor.md § Phase ir-2
- ir-2-00-PLAN.md, ir-2-01-PLAN.md, ir-2-02-PLAN.md, ir-2-03-PLAN.md
- HERMES-DEPLOY.md (this directory)
- .scratch/layer2-validation-20260507-210423.md (Vertex spike — pre-ir-2)
- .scratch/layer2-deepseek-validation-<ts>.md (DeepSeek close-out — ir-2-03)
- .scratch/layer2-deepseek-runner-<ts>.log (DeepSeek close-out raw stdout — ir-2-03)
```

Fill in:
- `<full sha>` from `git log --oneline -10` for each ir-2 commit.
- `<ts>` matching the close-out smoke timestamp.
- `<N> / <M>` line counts via `wc -l`.
- `<X>-<Y>`, `<P>-<Q>`, `<R>` line numbers from the actual smoke report (e.g. `head -100 .scratch/layer2-deepseek-validation-<ts>.md | grep -n "..."`).
- LF-2.4 verdict text copied verbatim from the report.

**HARD CONSTRAINTS:**
- DO NOT inline summary numbers (e.g. "誤殺=0, 漏放=0") in CLOSURE.md without the line-reference. Anti-fabrication rule from fc13098 lesson.
- DO NOT touch sibling docs (PROJECT-v3.5 / REQUIREMENTS-v3.5 / ROADMAP-v3.5 / STATE-v3.5).
- DO NOT modify the ir-2 PLAN files retroactively.
- The CLOSURE.md is the ONE committed reference to the smoke; the .scratch/ files are the source of truth.
  </action>
  <verify>
    <automated>test -f .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md && wc -l .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md | awk '{print $1}' | grep -qE "^[6-9][0-9]$|^[1-9][0-9]{2,}$" && echo "len ok"</automated>
    <automated>grep -q ".scratch/layer2-deepseek-validation-" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md && grep -q ".scratch/layer2-deepseek-runner-" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md && echo "evidence refs ok"</automated>
    <automated>grep -qE "L[0-9]+" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md && echo "line numbers cited"</automated>
  </verify>
  <acceptance_criteria>
    - File exists, ≥60 lines.
    - References both `.scratch/layer2-deepseek-validation-<ts>.md` and `.scratch/layer2-deepseek-runner-<ts>.log` paths.
    - At least one citation of the form `L<N>` to a specific line number in the evidence files.
    - LF-2.4 verdict (PASS / FAIL / DEFERRED) explicit.
    - Lists all 4 ir-2 commit hashes (or marked TBD if commit hash not yet final).
    - Lists deviations explicitly.
    - Ends with STOP gate notice.
  </acceptance_criteria>
  <done>ir-2 phase closure documented with truthful evidence trail. The .scratch/ smoke files are the source of truth; CLOSURE.md is the committed reference.</done>
</task>

</tasks>

<verification>
After Tasks 4.1, 4.2, 4.3 land:

```bash
# Runbook completeness
wc -l .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md
grep -c "^## Step" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/HERMES-DEPLOY.md

# Smoke evidence in .scratch (gitignored)
ls -la .scratch/layer2-deepseek-validation-*.md .scratch/layer2-deepseek-runner-*.log | tail -2

# CLOSURE.md cites the evidence with line numbers
grep -nE "L[0-9]+|.scratch/layer2-deepseek-" .planning/phases/ir-2-real-layer2-and-fullbody-scoring/CLOSURE.md | head
```

After this plan: ir-2 phase is **complete locally**. Hermes deploy is gated behind explicit user trigger. ir-3 plan-phase does NOT start automatically.
</verification>

<commit_message>
docs(ir-2): HERMES-DEPLOY runbook + CLOSURE with smoke evidence (LF-4.2 + LF-2.4)

Authored .planning/phases/ir-2-*/HERMES-DEPLOY.md as a self-contained
operator runbook (mirror of ir-1 structure) covering: pre-flight, DB +
cron-registry backup, pause daily-ingest, pull main, apply migration 007,
schema verification, 5-article dry-run + 1-article real smoke (the
contract-faithful happy-path gate for Layer 2), cron resume, first-cron
watch with Day-1 backlog warning extended for layer1 + layer2 first-time
evaluation, STATE sign-off step (operator-side), two-path rollback (commits
revert + DB restore from backup).

Close-out smoke (LF-2.4 contract-faithful re-validation against DeepSeek):
runner at .scratch/layer2-deepseek-runner.py (gitignored, NOT committed)
imports lib.article_filter.layer2_full_body_score (post-ir-2-00 real
DeepSeek wired) and runs against the 20-article spike sample. Outputs:

- .scratch/layer2-deepseek-validation-<ts>.md (gitignored)
- .scratch/layer2-deepseek-runner-<ts>.log (gitignored, raw stdout)

CLOSURE.md cites both evidence files by path + line number, names the
LF-2.4 verdict (PASS / FAIL / DEFERRED) and quotes the verdict line
verbatim from the smoke report. Anti-fabrication: no summary numbers in
CLOSURE.md without line-reference (lesson from fc13098).

Per session direction (2026-05-07 evening): agent stops at runbook
authored + smoke evidence captured + CLOSURE.md ship. Operator triggers
actual Hermes deploy.

REQs: LF-2.4, LF-4.2
Phase: v3.5-Ingest-Refactor / ir-2 / plan 03
Depends-on: ir-2-00 (lib + migration), ir-2-01 (ingest loop), ir-2-02 (tests)
</commit_message>
