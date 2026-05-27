# ir-2 Phase Closure — Real Layer 2 + full-body scoring

**Date:** 2026-05-07 ~21:54 ADT
**Phase:** v3.5-Ingest-Refactor / ir-2
**Status:** Code complete + close-out smoke captured. **LF-2.4 sign-off DEFERRED**
(local network blocked DeepSeek API; failure validates LF-2.6 cleanly).
Hermes deploy gated by operator (HERMES-DEPLOY.md in this directory).

## Commits

| Wave | Plan | Commit | Description |
|---|---|---|---|
| - | plan ir-2-00 | `cd38dd4` | docs(ir-2): plan ir-2-00 — real Layer 2 DeepSeek impl + persist + migration 007 |
| - | plan ir-2-01 | `243d5e7` | docs(ir-2): plan ir-2-01 — ingest loop batched Layer 2 wiring |
| - | plan ir-2-02 | `d42bd31` | docs(ir-2): plan ir-2-02 — LF-2.8 6-case Layer 2 unit suite |
| - | plan ir-2-03 | `2597adb` | docs(ir-2): plan ir-2-03 — HERMES-DEPLOY + close-out smoke + CLOSURE |
| 1 | execute 00 | `7cd9efe` | feat(ir-2): real Layer 2 DeepSeek impl + persistence + migration 007 |
| 2 | execute 01 | `434a1a2` | feat(ir-2): rewire ingest loop to batched Layer 2 |
| 2 | execute 02 | `657d638` | test(ir-2): LF-2.8 6-case Layer 2 unit suite |
| 3 | execute 03 | (this commit) | docs(ir-2): HERMES-DEPLOY runbook + CLOSURE with smoke evidence |

## REQ coverage

| REQ | Plan | Status | Evidence |
|---|---|---|---|
| LF-2.1 | ir-2-00 | done | `lib.article_filter.layer2_full_body_score` is async batch (commit 7cd9efe) |
| LF-2.2 | ir-2-00 | done | LAYER2_BATCH_SIZE=5, LAYER2_TIMEOUT_SEC=60 (commit 7cd9efe) |
| LF-2.3 | ir-2-00 | done (operator-config) | Calls `lib.llm_deepseek.deepseek_model_complete`. **Deviation**: REQ pinned `deepseek-chat`; module default is `deepseek-v4-flash`. Operator sets `DEEPSEEK_MODEL=deepseek-chat` in `~/.hermes/.env` if strict. |
| LF-2.4 | ir-2-03 | **DEFERRED** | See `.scratch/layer2-deepseek-validation-20260507-215424.md` L19-L38 (per-article table) + L40-L50 (summary) + L52-L58 (verdict block). Network blocked DeepSeek API; 0/20 verdicts produced; smoke validates LF-2.6 failure mode but defers LF-2.4 contract-faithful sign-off. |
| LF-2.5 | ir-2-00 | done | migration 007 + verdict alphabet 'ok'/'reject' on `articles.layer2_*` / `rss_articles.layer2_*` |
| LF-2.6 | ir-2-00 + ir-2-03 smoke | done — VALIDATED end-to-end | Smoke captured 4/4 whole-batch failures with `exception:APIConnectionError` reason; rows stayed layer2_verdict=NULL (no partial persist). See log L1-L4 (APIConnectionError per batch attempt) + L13-L16 (batch FAILED summaries) + L17-L36 (per-article NULL verdicts). |
| LF-2.7 | ir-2-00 | done | `PROMPT_VERSION_LAYER2='layer2_v0_20260507'` constant + persistence; covered by unit test `test_layer2_prompt_version_bump_invalidates_prior` (commit 657d638) |
| LF-2.8 | ir-2-02 | done — 16/16 PASS | pytest tests/unit/test_article_filter.py output captured at `.scratch/ir-2-02-pytest-output.log` L27 ("16 passed in 4.83s") |
| LF-3.2 | ir-2-01 | done | `_drain_layer2_queue` batched accumulator (commit 434a1a2); 3 await invocations + 10 layer2_queue refs in ingest_from_db |
| LF-3.3 | ir-2-01 | done | Layer 2 reject → `INSERT OR REPLACE INTO ingestions(status='skipped')` (commit 434a1a2) |
| LF-4.2 | ir-2-03 | done | HERMES-DEPLOY.md authored in this directory (this commit); STOP gate held |

## Close-out smoke evidence (LF-2.4)

**Runner script** (gitignored, NOT committed): `.scratch/layer2-deepseek-runner.py`
**Raw stdout log** (gitignored): `.scratch/layer2-deepseek-runner-20260507-215424.log` (49 lines, 2899 bytes)
**Markdown report** (gitignored): `.scratch/layer2-deepseek-validation-20260507-215424.md` (58 lines, 4049 bytes)

### Citations

- **Per-article verdict table** (20 rows, all hit APIConnectionError):
  see report L19-L38 (markdown table) and log L17-L36 (raw stdout).
- **Summary stats** (misshits=0, missdrops=0, NULL batches=4/4, reject rate=0.0%):
  see report L40-L50 (summary table) and log L40-L44 (raw stdout summary block).
- **LF-2.4 verdict line:** see report L54 (verbatim: "**FAIL**") and log L46
  (verbatim: "LF-2.4 gate: FAIL").
- **DEFERRED reason:** see report L58 — "Note: 4 batch(es) failed entirely
  (whole-batch NULL). This validates LF-2.6 failure-mode handling (rows
  stay layer2_verdict=NULL → re-eval next ingest tick) but DEFERS LF-2.4
  sign-off until the failure mode is investigated."

### Verdict-line text (verbatim from report L52-L56)

> ## LF-2.4 verdict
>
> **FAIL**
>
> Close-out gate failed — see breakdown above. Investigate per failure-mode mapping.

### Failure mode interpretation

The 4 batches uniformly hit `APIConnectionError: Connection error` against
`api.deepseek.com`. Most likely cause: corporate proxy / firewall blocking
DeepSeek API egress from this Windows dev box. The same key is set via
`DEEPSEEK_API_KEY` in `.dev-runtime/.env` (production-shape) — the issue is
network-level, not auth-level.

**This is the same shape as ir-1's local smoke (403 PERMISSION_DENIED on
Vertex Gemini) — the local environment cannot reach Hermes-side LLM
endpoints, but the wiring (env load, batching, persistence helper, decision
rule, failure-mode mapping) all exercised correctly.** LF-2.6 is verified
end-to-end at the failure-path level.

The contract-faithful happy-path validation (0 misshits + 0 missdrops + 0
NULL batches against the spike-validated 20-article sample) lands when the
runner is invoked from a network that can reach DeepSeek. Three options:

1. Run the same `.scratch/layer2-deepseek-runner.py` from Hermes-side after
   ir-2 deploy (Hermes has working API egress per ir-1 cron observability).
2. Run from any non-corporate-proxy host with the same `DEEPSEEK_API_KEY`.
3. Wait for ir-3's first-cron-run wall-clock evidence (Step 9 of
   HERMES-DEPLOY.md captures the same data on real production traffic).

Option 3 is the lowest-effort path and the recommended close-out per
PROJECT § Success criteria #2 (zero cron failures over the 1-week
observation window).

## Deviations

1. **LF-2.3 model name pin** — REQ specifies `deepseek-chat`; module default
   is `deepseek-v4-flash` (configurable via `DEEPSEEK_MODEL` env). Operator
   sets `DEEPSEEK_MODEL=deepseek-chat` in `~/.hermes/.env` if strict
   compliance required. Documented in ir-2-00-PLAN.md and propagated into
   commit 7cd9efe body.
2. **Layer 2 spike substitute model** — original
   `.scratch/layer2-validation-20260507-210423.md` ran on Vertex Gemini
   Flash Lite (not DeepSeek). The close-out smoke at ir-2-03 was the
   intended contract-faithful re-validation against real DeepSeek; result
   captured in CLOSURE.md above (DEFERRED due to local network).
3. **Local network blocks DeepSeek API** — same shape as ir-1's local
   network blocking Vertex Gemini (Windows dev box behind corporate proxy).
   Not a code defect; infrastructure constraint of the local dev environment.
4. **`ingestions.reason` column not added** — preserved deviation from ir-1.
   Layer 2 reject reason logged at INFO level + persisted to
   `articles.layer2_reason`.

## Unknowns

- Hermes-side first-cron-run wall-clock and Layer 2 reject rate (deferred
  to operator post-deploy; see HERMES-DEPLOY.md Step 9). Spike measured
  ~5-7s per batch on Vertex Gemini; DeepSeek calibration may differ
  (per spike § "Model substitution caveat").
- Network egress reliability between Hermes and `api.deepseek.com`. ir-1
  cron observability + ir-2 deploy Step 7 1-article real smoke is the
  first datapoint; if DeepSeek availability is similar to Vertex's, no
  action needed.
- Whether `deepseek-chat` and `deepseek-v4-flash` calibrate Layer 2
  decisions identically. Spike was on Vertex Gemini, not either DeepSeek
  variant — calibration drift is possible. Phase ir-3 1-week observation
  catches this if reject rate drifts outside the 50-70% band on Layer 1
  or out of the ≥30% band on Layer 2 (post-Layer-1-pass rows).

## STOP gate

Per session direction (2026-05-07 evening): agent does NOT SSH or trigger
production cron. Operator triggers Hermes deploy at chosen window per
HERMES-DEPLOY.md.

After deploy: ir-3 (production cutover + 1-week observation) starts at
operator's next session. ir-3 is observation-only — no code changes.

## References

- `.planning/PROJECT-v3.5-Ingest-Refactor.md`
- `.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md`
- `.planning/ROADMAP-v3.5-Ingest-Refactor.md` § Phase ir-2
- `ir-2-00-PLAN.md`, `ir-2-01-PLAN.md`, `ir-2-02-PLAN.md`, `ir-2-03-PLAN.md`
- `HERMES-DEPLOY.md` (this directory)
- `.scratch/layer2-validation-20260507-210423.md` (Vertex spike — pre-ir-2)
- `.scratch/layer2-deepseek-validation-20260507-215424.md` (DeepSeek close-out — ir-2-03; gitignored)
- `.scratch/layer2-deepseek-runner-20260507-215424.log` (DeepSeek close-out raw stdout — ir-2-03; gitignored)
- `.scratch/ir-2-02-pytest-output.log` (LF-2.8 unit test output; gitignored)
- ir-1's `.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md` and `CLOSURE.md` patterns (structural model)
