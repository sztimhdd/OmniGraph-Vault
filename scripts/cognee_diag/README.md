# cognee_diag — root-cause probes for the Cognee 422 NOT_FOUND issue

These scripts were added by quick task `260509-syd`
(`.planning/quick/260509-syd-cognee-root-cause-investigation-422-not-/`) to
isolate why the inline `cognee_wrapper.remember_article(...)` call
(`ingest_wechat.py:1219-1228`, gated by `OMNIGRAPH_COGNEE_INLINE`) blocks the
KOL ingest fast-path with a 422 NOT_FOUND retry loop.

**Read-only investigation tooling.** None of these scripts touch production
code. None of them need to run on Hermes — they all run locally against the
.venv, the operator's `~/.hermes/.env`, and (if available) the dev Vertex SA at
`.dev-runtime/gcp-paid-sa.json`.

## Scripts

### `inspect_cognee_routing.py` — pure-import probe

What it proves:

- The exact `os.environ` mutations `cognee_wrapper` applies at import time
- The values Cognee 1.0 actually resolves to in its `LLMConfig` +
  `EmbeddingConfig` (BaseSettings singletons read from env)
- Whether LiteLLM's model registry (`litellm.model_cost`) recognises each
  candidate model string (`gemini/gemini-embedding-2`,
  `gemini/gemini-embedding-2-preview`, `vertex_ai/gemini-embedding-2-preview`,
  etc.)

What it does NOT prove:

- What live AI Studio / Vertex returns for those model strings (see
  `probe_litellm_direct.py`)

Run:

```bash
.venv/Scripts/python scripts/cognee_diag/inspect_cognee_routing.py
```

Output: `.scratch/cognee-diag-inspect-<YYYYMMDD-HHMMSS>.log`

### `probe_cognee_inline_baseline.py` — failing-path reproducer

What it proves:

- Whether `cognee.remember(...)` configured via `cognee_wrapper` can complete a
  single round-trip in <60s
- The exact exception / stack trace surface when it fails (likely a tenacity
  retry chain wrapping a LiteLLM `BadRequestError` / `NotFoundError`)
- Wall-clock duration — if the call hangs past `WALL_TIMEOUT_SEC`, that itself
  is consistent with the retry-loop hypothesis (LiteLLM's
  `LiteLLMEmbeddingEngine` has `stop_after_delay(128)`)

What it does NOT prove:

- Which specific step (entity-extraction LLM vs embedding) fails first.
  `litellm.set_verbose = True` + DEBUG logging on `litellm` + `httpx` makes this
  visible in the log.

Run:

```bash
.venv/Scripts/python scripts/cognee_diag/probe_cognee_inline_baseline.py
```

Output: `.scratch/cognee-diag-inline-<YYYYMMDD-HHMMSS>.log`

### `probe_litellm_direct.py` — bypass-Cognee model-name probe

What it proves:

- Whether the 422 originates from AI Studio (model string unknown) or from
  LiteLLM routing logic (registry miss / wrong URL). Drives `litellm.aembedding`
  directly with each candidate model string:
  - `gemini/gemini-embedding-2` (cognee_wrapper config)
  - `gemini/gemini-embedding-2-preview` (registry-known AI Studio name)
  - `gemini/gemini-embedding-001` (legacy AI Studio name)
  - `vertex_ai/gemini-embedding-2-preview` (registry-known Vertex name)
  - `vertex_ai/gemini-embedding-2` (production-config Vertex name)
- Path B feasibility: whether Vertex SA from `.dev-runtime/gcp-paid-sa.json`
  can serve embeddings via LiteLLM (vs the production google-genai-direct path
  in `lib/lightrag_embedding.py`)

What it does NOT prove:

- Whether AI Studio's `gemini-embedding-2` (without `-preview`) silently routes
  to `-preview` server-side (the model registry suggests no, but only an HTTP
  call settles it — that's exactly what this script does)

Run:

```bash
.venv/Scripts/python scripts/cognee_diag/probe_litellm_direct.py
```

Output: `.scratch/cognee-diag-litellm-<YYYYMMDD-HHMMSS>.log`

## Notes

- All three scripts set `DEEPSEEK_API_KEY=dummy` to defuse the Phase 5
  cross-coupling import-time check at `lib/__init__.py:35`.
- `probe_cognee_inline_baseline.py` sets `OMNIGRAPH_COGNEE_INLINE=1` so the
  inline path is exercised (the production default is `0` since 2026-05-04).
- All API keys / SA contents are redacted in logs (only first/last 4 chars +
  length appear).
- Logs go to `.scratch/` which is gitignored — they are evidence-by-reference;
  the INVESTIGATION.md sibling doc pastes verbatim excerpts so the analysis is
  self-contained.

## When to delete these scripts

After the follow-up fix quick lands and the inline `remember_article` path is
re-enabled (or replaced), this directory can be deleted. Until then, keep them
as a regression probe — re-running `inspect_cognee_routing.py` is the cheapest
way to verify a routing change actually took effect.
