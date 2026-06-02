---
phase: ar-4-telemetry-streaming-smoke
plan: 02
status: CLOSED-WITH-DOCUMENTED-V1.1-GAPS — Tasks 1+2+3+4 shipped
last_updated: "2026-05-24"
commits:
  - 9cf40f6  # feat(ar-4-02): scripts/smoke_milestone.py — TEST-05 milestone-close driver
  - 4df3949  # fix(ar-4-02): smoke_milestone.py — prepend repo root to sys.path
  - e628bea  # fix(ar-4-02): JSON-mode LLM-decision adapter (Option A) — closes Reasoner+Verifier real-LLM gap
  - 440dc0f  # fix(ar-4-02): calibrate TEST-05 condition (c) — 120s → 240s, safety net 180s → 300s
  - 0fc543e  # fix(ar-4-02): _DecisionPayload — add confidence + discrepancies for Verifier path
requirements_status:
  TEST-05: PASS-WITH-DOCUMENTED-GAP — 4/5 conditions (b/c/d/e) PASS on Hermes iter-5 smoke; condition (a) zero-images deferred to v1.1 (Retriever↔KG plumbing gap, NOT architecture issue)
  TEST-06: PASS-WITH-DOCUMENTED-GAPS — 3/5 audit dimensions (1/2/3) PASS; 4 (attribution) + 5 (image relevance) deferred to v1.1
---

# ar-4-02 — Wave 2 close

## Outcome

Wave 2 ships the **TEST-05 milestone-close smoke driver**, the **Option A JSON-mode LLM-decision adapter** (Reasoner + Verifier real-LLM enablement — surfaced as a milestone-blocking architectural gap during iter-3 SSH-run that ar-2/ar-3 deferred under the "real provider integration is an ar-3+ refinement" mock-only contract), the **condition-(c) calibration** (120s → 240s; pre-empirical estimate vs measured DeepSeek latency), and the **TEST-06 manual audit** (`.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`).

5 forward-only commits across 5 iterations of the Wave 2 Task 2 SSH-run sub-cycle. **No `--amend`. No `git reset`. Explicit `git add <files>` only** throughout.

## Iteration narrative (Wave 2 Task 2 SSH-run sub-cycle)

The PLAN budgeted "max 3 smoke iterations + 1 audit re-run before user escalation" assuming prompt-tweak-class issues. What happened: each iteration surfaced a structurally-different blocker, the user was engaged at every escalation, and explicit user directives at iter-2 (perms restore) + iter-3 (Option A adapter) + iter-4 (calibration) + iter-5 (Verifier-fields) drove the loop to closure across 5 total iterations.

| Iter | Trigger | Outcome | Commit |
|---|---|---|---|
| 1 | First SSH-run | `ModuleNotFoundError: omnigraph` — Hermes venv lacked editable install. SSH-ran `pip install -e .` (one-shot setup); driver-side forward-fix prepending repo root to `sys.path` | `4df3949` |
| 2 | Post editable-install | `[Errno 13] Permission denied: kv_store_llm_response_cache.json` — aim-2 KG migration locked `lightrag_storage/` read-only. User directive: restore owner-write temporarily (recoverable, aim-2 migration was post-completion). Smoke ran end-to-end for the first time at 62s | (no commit — perms-only) |
| 3 | First real-LLM run | Reasoner + Verifier crashed at iter 1: `'str' object has no attribute 'is_final'`. ar-2/ar-3 mock-only LLM-decision contract surfaced — the loops dispatch `(prompt, tools) → _LLMDecision` but `cfg.llm_complete` is bound to LightRAG-compatible `(prompt) → str`. User directive: **Option A JSON-mode shim** | `e628bea` |
| 4 | Post Option-A adapter | Pipeline progressed but hit 180s safety net at 164.7s mid-Reasoner (default-cap loops × 25-30s/LLM-call). User directive: relax condition (c) 120s→240s, safety net 180s→300s | `440dc0f` |
| 5 | Post calibration | Reasoner OK; Verifier failed: `'_DecisionPayload' object has no attribute 'confidence'`. Verifier's `_LLMDecision` declares `confidence: float` + `discrepancies: tuple[str,...]` beyond Reasoner's. Forward-fix: extend `_DecisionPayload` with both fields (defaults preserve Reasoner path) | `0fc543e` |
| 5 (re-run) | Post Verifier-fields fix | **4/5 conditions PASS**: b=100, c=124s, d=[], e=0.593. Only (a)=0 fails (Retriever upstream gap). User directive: accept 4/5 + close with (a) deferred to v1.1 | (no new commit — re-run only) |

## TEST-05 verdict (iter-5 re-run, current state on Hermes commit `0fc543e`)

```json
{
  "query": "Hermes Harness 深度解析",
  "telemetry_path": ".scratch/smoke-telemetry-1779638012.jsonl",
  "markdown_archive_path": "/home/sztimhdd/.hermes/omonigraph-vault/synthesis_archive/1779638012_Hermes_Harness_深度解析.md",
  "markdown_chars": 2195,
  "a_image_count": 0,        "a_pass": false,
  "b_confidence": 100.0,     "b_pass": true,
  "c_elapsed_s": 124.2,      "c_pass": true,
  "d_failed_stages": [],     "d_pass": true,
  "e_cjk_ratio": 0.593,      "e_pass": true,
  "all_pass": false
}
```

Per-stage telemetry from iter-5 telemetry JSONL:

| Stage | Status | Duration | Extras |
|---|---|---|---|
| web_baseline | ok | 1.35s | 10 snippets (Tavily live) |
| retriever | ok | 31.7s | 1 chunk, 0 image_candidates (kg_text no hashes) |
| reasoner | ok | 113.1s | iter_count=5 (cap), 0 images analyzed (none upstream) |
| verifier | ok | (TBD — must re-check telemetry) | confidence=100.0, external_citations |
| synthesizer | (terminal) | <1ms | 0 images embedded, note_lines, confidence=0.5 |

## TEST-06 audit verdict

`.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (NEW, this Wave 2 deliverable).

| Dimension | Score | Threshold | Verdict |
|---|---|---|---|
| 1. Coverage breadth | 3/5 | ≥3 | ✓ |
| 2. Technical depth | 3/5 | ≥3 | ✓ |
| 3. Philosophical framing | 4/5 | ≥3 | ✓ |
| 4. Source attribution | **2/5** | ≥3 | ✗ (v1.1-B deferred) |
| 5. Image relevance | **1/5** | ≥3 | ✗ (v1.1-A deferred) |

Strict interpretation: 3/5 dimensions PASS, 2/5 FAIL. Per user directive: **PASS-WITH-DOCUMENTED-V1.1-GAPS** — milestone closure validates the agentic-RAG-v1 pipeline architecture end-to-end against real LLM + real web tools + real KG; content-quality refinements (dim 4 + dim 5) map to v1.1 work items.

## Deviations vs PLAN (all user-directed, all forward-only)

1. **Wave 2 Task 2 SSH-run iter count: 5 (PLAN budget: 3)** — every iteration surfaced a structurally-different blocker, user was engaged at each escalation, explicit directives drove forward each time. Honest framing: the 3-iter budget assumed prompt-tweak-class issues; the real iter sequence covered (a) infra setup [editable install + perms], (b) architectural gap [LLM adapter], (c) calibration [condition c], (d) field-shape gap [Verifier confidence/discrepancies], (e) close. None of these were in scope for "remediation" as the PLAN imagined.

2. **Option A JSON-mode shim shipped inside ar-4-02 scope** — user initially answered "Open ar-5 phase for LLM-adapter" then refined to "Option A inline (~50 LOC, 1 day)" with full analysis. Adapter is provider-agnostic: same wrap works for DeepSeek (Aliyun env), Databricks Mosaic AI, Vertex Gemini. 30 unit tests + 0 regressions across the full research suite.

3. **TEST-05 condition (c) calibrated 120s → 240s** — pre-empirical estimate against measured DeepSeek latency on Hermes path (default-cap loops × ~25-30s/LLM-call ≈ 200-280s realistic). Updated in scripts/smoke_milestone.py + ar-4-CONTEXT.md + ar-4-02-PLAN.md + ROADMAP-Agentic-RAG-v1.md (single forward commit `440dc0f`).

4. **`_DecisionPayload` extended with Verifier-only fields after iter-4** — original Option A design was Reasoner-only. iter-5 forward-fix added `confidence: float = 0.0` + `discrepancies: tuple[str, ...] = ()` with Reasoner-path defaults that preserve the original behavior.

5. **Audit verdict acknowledges 2/5 dimensions FAIL strictly** — honest framing per Audit Doc § "PASS-WITH-DOCUMENTED-V1.1-GAPS". User explicitly accepted this milestone-close path.

## Files modified across Wave 2

NEW:

- `scripts/smoke_milestone.py` — TEST-05 driver (141 LOC + 7 LOC sys.path fix)
- `lib/research/llm_adapter.py` — Option A JSON-mode shim (~210 LOC)
- `tests/unit/research/test_llm_adapter.py` — 30 unit tests
- `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` — TEST-06 audit doc
- `.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-02-SUMMARY.md` — this file

MODIFIED:

- `lib/research/config.py` — `from_env()` wraps underlying provider in adapter
- `.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-CONTEXT.md` — TEST-05 condition (c) calibration
- `.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-02-smoke-audit-PLAN.md` — condition (c) literal updates (~7 lines via `sed -i` batch)
- `.planning/ROADMAP-Agentic-RAG-v1.md` — ar-4 § Success Criteria #3 condition (c) calibration

NOT modified:

- `lib/research/stages/{reasoner,verifier,synthesizer,web_baseline,retriever}.py` — locked, no cross-phase touches needed; the adapter at `from_env()` boundary is the only change
- `lib/research/types.py` — locked across ar-N

## v1.1 follow-up work items (extracted from audit)

| Item | Source | Effort |
|---|---|---|
| V1.1-A: Retriever chunk-by-chunk extraction with hash refs | ar-2 unfulfilled aspiration; fixes TEST-05 (a) + audit dim 5 | 1-2 days |
| V1.1-B: Synthesizer prompt threading inline citations | audit dim 4 root cause | 0.5-1 day |
| V1.1-C: Native function-calling adapter (Option B from 2026-05-24 escalation) | replaces Option A JSON-mode shim; lower latency + higher reliability | 2-3 days |
| V1.1-D: Per-tool-call telemetry events | ar-4 CONTEXT § Out of scope | 0.5 day |
| V1.1-E: LightRAG cache write-perms reconciliation with aim-2 read-only protection | cross-milestone | 1 day |

## Hermes operator-side state (cleaned up)

- `pip install -e .` on Hermes venv — persistent (post-`pip uninstall` would reverse), required for all `python scripts/smoke_milestone.py` + `python -m omnigraph.research` invocations going forward. Left in place.
- `chmod -R u+w` on `~/.hermes/omonigraph-vault/lightrag_storage/` — temporary write-restore for each smoke iter. Restored to read-only via `chmod -R a-w` after each iteration. Final state: `dr-xr-xr-x` (matches aim-2 baseline). Net delta across 5 iters: `kv_store_llm_response_cache.json` grew ~14 KB (cache writes during real-LLM iterations 3+4+5).

## Forward-only commit chain (Wave 2 final)

5 wave-2 commits + 1 milestone-close commit (this SUMMARY + STATE + ROADMAP + audit doc). Zero `--amend`, zero `git reset`, all `git add <files>` explicit.

## Wave 2 status: CLOSED-WITH-DOCUMENTED-V1.1-GAPS — Agentic-RAG-v1 milestone CLOSED
