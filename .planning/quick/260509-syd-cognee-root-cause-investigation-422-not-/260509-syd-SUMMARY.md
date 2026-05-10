---
type: quick
id: 260509-syd
title: Cognee root-cause investigation — 422 NOT_FOUND
status: complete
investigation_only: true
requirements: [COG-01, COG-02, COG-03]
recommended_fix_path: B
date_completed: 2026-05-09
---

# Quick 260509-syd Summary — Cognee 422 NOT_FOUND root-cause

## One-liner

Root cause is **mis-routed Cognee embeddings** (configured for AI Studio
`gemini/gemini-embedding-2` but the model is Vertex-exclusive AND the
production GEMINI_API_KEY is an OAuth-format token AI Studio rejects with 401);
recommended fix is **Path B — switch Cognee to Vertex (~5 LOC)**, locally
verified to return a 3072-dim vector in 0.47 s.

## Recommended fix: Path B (switch Cognee to Vertex)

**Reasoning** (1 paragraph, copied from INVESTIGATION.md § Recommended path):

Path B is the right answer because it (1) is **proven working** in this
investigation (Vertex SA + `vertex_ai/gemini-embedding-2` returns a 3072-dim
vector in 0.47 s on Hermes-equivalent corp network), (2) is the **smallest
change** that actually fixes the root cause (5 LOC in one file vs Path C's
210 LOC vs Path A's hidden deploy-side AI-Studio-key dependency that's
already been a source of pain twice), (3) **aligns with production** —
LightRAG already uses Vertex `gemini-embedding-2` for embeddings, so picking
Vertex for Cognee gives both consumers the same routing and quota profile,
and (4) **future-proofs** the v3.3 quota-isolation migration. Path A keeps
an AI-Studio dependency we know is brittle (preview-tier model, shared
quota, format-mismatched key in `.env`). Path C is over-engineered.

### Concrete change for the follow-up fix quick

`cognee_wrapper.py:47-51` (~5 LOC):

```python
os.environ["LLM_PROVIDER"] = "vertex_ai"
os.environ["LLM_MODEL"] = f"vertex_ai/{INGESTION_LLM}"
os.environ["EMBEDDING_PROVIDER"] = "vertex_ai"
os.environ["EMBEDDING_MODEL"] = "vertex_ai/gemini-embedding-2"
```

Plus a smoke test that reproduces this investigation's Vertex-success path
(the fix quick should add it to `scripts/local_e2e.sh` or a new pytest
fixture so this regression cannot happen silently again).

## Pointer to full investigation

See [INVESTIGATION.md](./INVESTIGATION.md) for:
- Routing trace (14 numbered steps, file:line citations)
- Evidence ledger (8 numbered facts, each with verbatim log excerpts)
- All three fix paths with t-shirt estimates and counted LOC
- Open questions for the fix quick

## Log files (raw evidence)

All logs under `.scratch/` (gitignored — INVESTIGATION.md pastes verbatim
excerpts so the doc is self-contained):

- `.scratch/cognee-diag-inspect-20260509-210650.log` — env / config / registry snapshot
- `.scratch/cognee-diag-inline-20260509-210718.log` — `cognee.remember()` 60 s hang reproduction
- `.scratch/cognee-diag-litellm-20260509-210844.log` — first LiteLLM probe (captured AI Studio URL form)
- `.scratch/cognee-diag-litellm-20260509-211126.log` — full LiteLLM probe (Vertex success + AI Studio + Vertex-preview failures)

## Open questions for the fix quick

1. Does Cognee 1.0's `LiteLLMEmbeddingEngine` honor `GOOGLE_APPLICATION_CREDENTIALS`
   without explicit `vertex_credentials=` kwarg? (Verified: LiteLLM main.py
   reads `VERTEXAI_CREDENTIALS`/`VERTEX_CREDENTIALS` from env at L5223-L5228;
   the fix quick should add a probe-with-Cognee-engine smoke that proves the
   chain works end-to-end without explicit kwargs.)

2. Does `vertex_ai/gemini-2.5-flash` work for the LLM side (Cognee's
   classify_documents / extract_graph_from_data)? Worth a one-line probe in
   `probe_litellm_direct.py` before fix.

3. Is `~/.hermes/.env` `GEMINI_API_KEY=AQ.A…` (OAuth-format) intentional? It
   is unusable for AI Studio and will expire (1 h OAuth lifetime). The fix
   should either remove it (Vertex uses SA) or document the format mismatch.

4. Are the 4 `os.environ[…] = _initial_key` lines in `cognee_wrapper.py:41-44`
   needed under Path B? They become Vertex-mode no-ops; rotation logic in
   `lib/api_keys.py` still relies on the env seed. The fix quick should
   decide: remove or annotate.

5. Add an automated regression test that imports `cognee_wrapper` + calls
   `cognee.remember(...)` + asserts a vector is returned in <10 s. Without
   it, the next config drift will rebreak this path silently.

## Files added by this quick

| Path | Purpose |
| ---- | ---- |
| `scripts/cognee_diag/inspect_cognee_routing.py` | env + LLMConfig + EmbeddingConfig + LiteLLM registry probe |
| `scripts/cognee_diag/probe_cognee_inline_baseline.py` | reproduces 60 s hang of `cognee.remember()` |
| `scripts/cognee_diag/probe_litellm_direct.py` | bypasses Cognee, probes each candidate model string against AI Studio + Vertex |
| `scripts/cognee_diag/README.md` | what each probe proves / does not prove |
| `.planning/quick/260509-syd-…/260509-syd-PLAN.md` | task plan |
| `.planning/quick/260509-syd-…/INVESTIGATION.md` | full root-cause analysis with evidence ledger |
| `.planning/quick/260509-syd-…/260509-syd-SUMMARY.md` | this file |

## Stop-gate verification

Before commit, confirmed via:

```bash
git status --short
# (only paths under scripts/cognee_diag/ + .planning/quick/260509-syd-*/ allowed)
```

No edits to `cognee_wrapper.py`, `cognee_batch_processor.py`, `ingest_wechat.py`,
`lib/api_keys.py`, `kg_synthesize.py`, `CLAUDE.md`, `.planning/STATE.md`,
`.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`.

## Final commit SHA

(filled in after commit)
