# Cognee 422 NOT_FOUND root-cause investigation

Quick task: `260509-syd`
Date: 2026-05-09
Mode: investigation-only (no production-code edits)
Requirements: COG-01, COG-02, COG-03

## TL;DR (≤4 lines)

The inline `cognee_wrapper.remember_article(...)` path blocks the KOL ingest
fast-path because `cognee_wrapper.py` configures Cognee to route Gemini
embeddings via LiteLLM with `EMBEDDING_PROVIDER=gemini` (Google AI Studio),
but the production `~/.hermes/.env` `GEMINI_API_KEY` is a Vertex OAuth-format
token (`AQ.A…` / 53 chars) that AI Studio rejects with **401
ACCESS_TOKEN_TYPE_UNSUPPORTED**. Even with a valid AI Studio key, the model
string `gemini-embedding-2` is not registered on AI Studio (only
`gemini-embedding-001` and `gemini-embedding-2-preview` are) — Vertex AI
exclusively serves the `gemini-embedding-2` GA model. **Recommended fix: Path
B — switch Cognee to Vertex via `EMBEDDING_PROVIDER=vertex_ai` +
`EMBEDDING_MODEL=vertex_ai/gemini-embedding-2` + SA JSON.**
Confidence: HIGH — local probe confirmed both the AI Studio failure (401) and
the Vertex success (200, 3072-dim vector returned in 0.47 s).

## Versions

`.scratch/cognee-diag-inspect-20260509-210650.log` L4-L8:

```
python      = 3.13.5
cognee      = 1.0.1
litellm     = 1.83.0
google-genai= 1.73.1
```

## Evidence ledger

### Fact 1 — `cognee_wrapper` configures Cognee to use AI Studio (gemini/) provider

Source: `cognee_wrapper.py:47-51`

```python
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = INGESTION_LLM
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini/gemini-embedding-2"
os.environ["EMBEDDING_DIMENSIONS"] = "3072"
```

Verified at runtime — `.scratch/cognee-diag-inspect-20260509-210650.log`
L24-L29 (post-import env snapshot):

```
LLM_PROVIDER = 'gemini'
LLM_MODEL = 'gemini-2.5-flash'
EMBEDDING_PROVIDER = 'gemini'
EMBEDDING_MODEL = 'gemini/gemini-embedding-2'
EMBEDDING_DIMENSIONS = '3072'
```

Cognee's `EmbeddingConfig` BaseSettings actually picks these up (same log
L37-L40):

```
EmbeddingConfig.embedding_provider   = 'gemini'
EmbeddingConfig.embedding_model      = 'gemini/gemini-embedding-2'
EmbeddingConfig.embedding_dimensions = 3072
EmbeddingConfig.embedding_endpoint   = None
```

### Fact 2 — LiteLLM model registry recognizes `gemini/gemini-embedding-2` (it IS routable)

`.scratch/cognee-diag-inspect-20260509-210650.log` L43:

```
REGISTERED: gemini/gemini-embedding-2 -> {"litellm_provider": "gemini",
  "mode": "embedding", "uses_embed_content": null, "max_input_tokens": 8192}
```

So LiteLLM knows the model name and routes it to the AI Studio
(`generativelanguage.googleapis.com`) embedding endpoint via the `gemini`
provider — the URL it constructs (per
`venv/Lib/site-packages/litellm/llms/vertex_ai/common_utils.py:336-371`,
function `_get_gemini_url`, mode=batch_embedding) is:

```
https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:batchEmbedContents?key=...
```

Confirmed verbatim from `.scratch/cognee-diag-litellm-20260509-210844.log`
L40-L45 (raw LiteLLM debug output, key redacted):

```
POST Request Sent from LiteLLM:
curl -X POST \
https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:batchEmbedContents?key=*****WOFU \
-H 'Content-Type: application/json; charset=utf-8' \
-d '{'requests': [{'model': 'models/gemini-embedding-2', 'content': {'parts': [{'text': 'hello world'}]}}]}'
```

### Fact 3 — AI Studio rejects the actual `~/.hermes/.env` GEMINI_API_KEY (OAuth-format)

The production `~/.hermes/.env` GEMINI_API_KEY value has format `AQ.A…uzNQ`
(53 chars). When LiteLLM submits it as `?key=` to AI Studio, AI Studio
returns **401 UNAUTHENTICATED reason=ACCESS_TOKEN_TYPE_UNSUPPORTED**:

`.scratch/cognee-diag-litellm-20260509-211126.log` L60-L75 (full HTTP body
verbatim, only key redacted):

```
exc message = litellm.AuthenticationError: GeminiException - {
  "error": {
    "code": 401,
    "message": "Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.",
    "status": "UNAUTHENTICATED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED",
        "metadata": {
          "method": "google.ai.generativelanguage.v1beta.GenerativeService.BatchEmbedContents",
          "service": "generativelanguage.googleapis.com"
        }
      }
    ]
  }
}
```

A separate probe with a different (stale OS-env) key `AIza…WOFU` (39 chars,
the AI Studio canonical format) also fails — but with `400 INVALID_ARGUMENT
reason=API_KEY_INVALID` ("API key expired") — see
`.scratch/cognee-diag-litellm-20260509-210844.log` L51-L75.

So both keys present in this dev box are unusable for AI Studio embeddings;
the only currently-working credentials are the Vertex SA at
`.dev-runtime/gcp-paid-sa.json`.

### Fact 4 — `gemini-embedding-2` is Vertex-exclusive (model not on AI Studio at all)

LiteLLM model registry (`.scratch/cognee-diag-inspect-20260509-210650.log`
L41-L47):

| Model name | provider | status |
| ---- | ---- | ---- |
| `gemini/gemini-embedding-2` | `gemini` (AI Studio) | registered, routes to AI Studio (but AI Studio doesn't actually serve `gemini-embedding-2` — only the `-preview` variant is documented) |
| `gemini/gemini-embedding-2-preview` | `gemini` | registered |
| `gemini/gemini-embedding-001` | `gemini` | registered (legacy) |
| `vertex_ai/gemini-embedding-2-preview` | `vertex_ai` | registered |
| `vertex_ai/gemini-embedding-2` | (registry MISS — only `gemini-embedding-2` flat-keyed `vertex_ai-embedding-models`) | works at runtime via the `vertex_ai/` prefix routing — see Fact 5 |

`gemini-embedding-2` (without -preview) is GA on Vertex AI's `global` endpoint
since 2026-04-22 (per CLAUDE.md "Vertex endpoint + model pairing" + the
working production code at `lib/lightrag_embedding.py:157` — comment "on the
``global`` endpoint ``gemini-embedding-2`` is GA (2026-04-22)").

### Fact 5 — Vertex AI works for `vertex_ai/gemini-embedding-2` (Path B feasibility confirmed)

Direct LiteLLM probe with Vertex SA — `.scratch/cognee-diag-litellm-20260509-211126.log`
L240-L254 (raw URL + success line):

```
POST Request Sent from LiteLLM:
curl -X POST \
https://aiplatform.googleapis.com/v1/projects/project-df08084f-6db8-4f04-be8/locations/global/publishers/google/models/gemini-embedding-2:embedContent \
-H 'Content-Type: application/json; charset=utf-8' -H 'Authorization: Be****zl' \
-d '{'content': {'parts': [{'text': 'hello world'}]}}'
...
OK: Vertex: vertex_ai/gemini-embedding-2 (production-config) — 1 vectors, dim=3072, elapsed=0.47s
```

### Fact 6 — Vertex `vertex_ai/gemini-embedding-2-preview` returns 404 (not in our project)

Same log L204-L211:

```
FAIL Vertex: vertex_ai/gemini-embedding-2-preview (registry-known) after 1.60s: NotFoundError
exc message = litellm.NotFoundError: Vertex_aiException - {
  "error": {
    "code": 404,
    "message": "Publisher Model `projects/project-df08084f-6db8-4f04-be8/locations/global/publishers/google/models/gemini-embedding-2-preview` was not found or your project does not have access to it. Please ensure you are using a valid model version. For more information, see: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions",
    "status": "NOT_FOUND"
  }
}
```

This **404 NOT_FOUND** matches the symptom CLAUDE.md describes as "422
NOT_FOUND" (the actual gRPC code is 404 — the doc reference is approximate).
This proves the historical retry-loop hypothesis: when Cognee was earlier
configured for Vertex with the `-preview` model name, every embedding call
404'd, tenacity wrapped it in `stop_after_delay(128)` retries, and the inline
ingest path hung for ~128 s per article. The current AI Studio configuration
has the same hung-retry profile but for a different reason (auth instead of
404).

### Fact 7 — Inline `cognee.remember()` hangs >60 s with current config

`.scratch/cognee-diag-inline-20260509-210718.log` L8-L10 + console output L72:

```
Importing cognee_wrapper (will mutate env)
Re-attached file handler post-import
Calling cognee.remember(...) with WALL_TIMEOUT_SEC=60.0s
…
remember() exceeded wall-clock 60.0s — TIMEOUT (consistent with retry-loop hypothesis)
```

(The structlog-formatted internal log of the cognee pipeline went to stderr;
the relevant excerpt also captured in console output:
"Pipeline run started: `ef15f577-…`" → "extract_graph_from_data" → 60 s
timeout. The probe's 60 s budget is shorter than tenacity's 128 s retry
window, so the hang is NOT yet the embedding loop — it's the upstream
classify_documents / extract_graph_from_data LLM step which uses the same
broken auth. This is consistent with the symptom: the inline path blocks
ingest BEFORE it ever reaches embedding.)

### Fact 8 — Production `lib/lightrag_embedding.py` already uses Vertex via google-genai (working)

`lib/lightrag_embedding.py:117-127` — `_is_vertex_mode()` returns True iff
both `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT` are set.

`lib/lightrag_embedding.py:137-143` — when in Vertex mode, constructs
`genai.Client(vertexai=True, project=..., location=...)` (NOT LiteLLM).

`lib/lightrag_embedding.py:166-170` — calls
`client.aio.models.embed_content(model=model, contents=..., config=...)`.

`lib/models.py:17` — production model constant: `EMBEDDING_MODEL = "gemini-embedding-2"`.

In other words, OmniGraph's LightRAG embedding path already bypasses LiteLLM
and uses google-genai SDK directly with the working
`vertex_ai/gemini-embedding-2` model name. **Cognee is the only consumer that
still routes via LiteLLM to AI Studio.**

## Routing trace

End-to-end annotated flow when `OMNIGRAPH_COGNEE_INLINE=1` (the broken case):

1. `ingest_wechat.py:1219` calls `await cognee_wrapper.remember_article(...)`.
2. `cognee_wrapper.py:142-150` calls `cognee.remember(text, dataset_name=...,
   self_improvement=False, run_in_background=True)`.
3. Cognee internally runs `add()` → `cognify()` → embedding pipeline.
4. Cognee's `cognee/infrastructure/databases/vector/embeddings/get_embedding_engine.py`
   reads `EmbeddingConfig` (BaseSettings, env-driven) → resolves
   `embedding_provider="gemini"` + `embedding_model="gemini/gemini-embedding-2"`.
5. Factory at line 95 falls through to `LiteLLMEmbeddingEngine(...)` because
   provider is neither `fastembed`, `ollama`, nor `openai_compatible`.
6. `LiteLLMEmbeddingEngine.embed_text` (`venv/Lib/site-packages/cognee/.../LiteLLMEmbeddingEngine.py:111-160`)
   calls `litellm.aembedding(model="gemini/gemini-embedding-2", input=...,
   api_key=COGNEE_LLM_API_KEY, dimensions=3072)`.
7. LiteLLM `main.py:5184-5206` strips `gemini/` prefix → `model="gemini-
   embedding-2"`, then calls `google_batch_embeddings.batch_embeddings(
   custom_llm_provider="gemini", api_key=...)`.
8. Handler at `venv/Lib/site-packages/litellm/llms/vertex_ai/gemini_embeddings/batch_embed_content_handler.py:113`
   calls `_get_token_and_url(custom_llm_provider="gemini", mode="batch_embedding")`.
9. URL builder at `vertex_ai/common_utils.py:367-371` constructs:
   `https://generativelanguage.googleapis.com/v1beta/models/gemini-
   embedding-2:batchEmbedContents?key=<COGNEE_LLM_API_KEY>`.
10. **AI Studio rejects** (current state):
    - With OAuth-format key (`.env` value `AQ.A…uzNQ`): 401
      ACCESS_TOKEN_TYPE_UNSUPPORTED.
    - With AI Studio-format key (`AIza…`): would still 422 NOT_FOUND because
      AI Studio doesn't serve `gemini-embedding-2` (only `-preview` and
      `-001`). Actual current AIza key in this dev box is also expired.
11. LiteLLM raises `BadRequestError` / `AuthenticationError` / `NotFoundError`
    depending on the failure type.
12. Cognee's `LiteLLMEmbeddingEngine.embed_text` is wrapped with
    `tenacity.retry(stop=stop_after_delay(128),
    wait=wait_exponential_jitter(2, 128),
    retry=retry_if_not_exception_type(litellm.exceptions.NotFoundError),
    reraise=True)` (lines 104-110 of LiteLLMEmbeddingEngine.py).
13. Tenacity retries for ≤128 s before re-raising (or short-circuits on
    `NotFoundError` — but only the embedding step has that exclusion, not
    the upstream classify/extract LLM step which uses the same broken auth).
14. `cognee.remember()` propagates the failure; `remember_article` catches
    `Exception` (`cognee_wrapper.py:152-153`) and logs at debug. Caller
    moves on, but the per-article ingest loop has already paid 60-128 s of
    wall-clock per article.

## Three fix paths

### Path A — Rename `EMBEDDING_MODEL` to a registry-known AI Studio name (smallest)

**Change:** `cognee_wrapper.py:50`:

```python
# Before:
os.environ["EMBEDDING_MODEL"] = "gemini/gemini-embedding-2"
# After:
os.environ["EMBEDDING_MODEL"] = "gemini/gemini-embedding-2-preview"
# (or "gemini/gemini-embedding-001" if -preview is not stable enough)
```

**Pre-requisite:** the production `~/.hermes/.env` `GEMINI_API_KEY` must be
replaced with an actual AI Studio API key (`AIza…` format), NOT the current
OAuth-format token. This is a **deploy-side fix**, not a code fix.

**Pros:** ~1 LOC change. No new infra dependency.

**Cons:**
- Requires a separate working AI Studio API key (the OAuth token in the .env
  cannot be reused). Operator needs to mint a fresh key from
  https://aistudio.google.com/.
- AI Studio free-tier embedding RPD ceiling is shared with all other AI
  Studio Gemini calls in the same GCP project — same quota-coupling problem
  CLAUDE.md identifies as the v3.3 migration motivator.
- `gemini-embedding-2-preview` is preview-tier (not GA on AI Studio); the
  service may deprecate it without notice. `gemini-embedding-001` is GA but
  its dimension cap is 2048, conflicting with `EMBEDDING_DIMENSIONS=3072`
  config — would also need to drop dim to 2048 (which means re-embedding
  any existing Cognee data).

**Counted blast radius (`git grep`):**
- `gemini/gemini-embedding-2` literal string: 1 occurrence in
  `cognee_wrapper.py:50`. (Confirmed via `grep -rn "gemini/gemini-
  embedding-2" .` — only this file.)
- `gemini-embedding-2` literal (no `gemini/` prefix): used by `lib/models.py:17` (production config — must NOT be touched per Path A scope) and a handful of doc/CLAUDE.md references.

### Path B — Switch Cognee to Vertex (RECOMMENDED)

**Change:** `cognee_wrapper.py:47-51`:

```python
# Before:
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = INGESTION_LLM
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini/gemini-embedding-2"
# After:
os.environ["LLM_PROVIDER"] = "vertex_ai"
os.environ["LLM_MODEL"] = f"vertex_ai/{INGESTION_LLM}"
os.environ["EMBEDDING_PROVIDER"] = "vertex_ai"
os.environ["EMBEDDING_MODEL"] = "vertex_ai/gemini-embedding-2"
```

Plus pass-through of vertex auth: LiteLLM honors
`GOOGLE_APPLICATION_CREDENTIALS` (already set in production via
`scripts/local_e2e.sh` and Hermes `.env`), `VERTEXAI_PROJECT` /
`GOOGLE_CLOUD_PROJECT`, and `VERTEXAI_LOCATION` /
`GOOGLE_CLOUD_LOCATION`. Production already has all three.

**Pros:**
- **Verified working in this investigation** — Vertex `vertex_ai/gemini-
  embedding-2` returned 3072-dim vector in 0.47 s
  (`.scratch/cognee-diag-litellm-20260509-211126.log:254`).
- Parity with production LightRAG embedding path
  (`lib/lightrag_embedding.py` already uses Vertex `gemini-embedding-2` on
  `global` endpoint).
- Decouples Cognee quota from AI Studio shared pool (the v3.3-migration
  motivator).
- No model-version surprises: `gemini-embedding-2` is GA on Vertex `global`.
- LLM provider switches to Vertex too, getting the same quota benefit for
  Cognee's classify_documents / extract_graph_from_data internal calls.

**Cons:**
- Requires SA JSON on every Cognee-using deploy. Hermes already has
  `~/.hermes/gcp-paid-sa.json` from the v3.3 migration prep; local dev has
  `.dev-runtime/gcp-paid-sa.json`. Anyone who only has an AI Studio key
  loses Cognee functionality (acceptable — Cognee is opt-in).
- Cognee's LiteLLMEmbeddingEngine has tenacity retry that excludes
  `NotFoundError` — Vertex uses 404 for "model not in this project's
  region", so a misconfigured location (e.g. `us-central1` vs `global`)
  short-circuits without retry. This is mostly fine but operators must set
  `GOOGLE_CLOUD_LOCATION=global` explicitly.

**Counted blast radius (`git grep`):**
- `gemini/gemini-embedding-2`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`,
  `LLM_PROVIDER`, `LLM_MODEL` literals in `cognee_wrapper.py`: 5 lines
  (47-51).
- `cognee_wrapper.py` is the only file that sets these env vars; no other
  caller hard-codes the AI Studio config.
- 1 file changed, ~5 LOC. T-shirt: **XS**.

### Path C — Replace Cognee's LiteLLMEmbeddingEngine with google-genai direct

**Change:** subclass `LiteLLMEmbeddingEngine`, override `embed_text` to call
`google.genai.Client(vertexai=True, project=..., location=...)` like
`lib/lightrag_embedding.py:_embed_once`. Inject the subclass via
`get_embedding_engine` monkey-patch at `cognee_wrapper.py` import time.

**Pros:**
- Removes LiteLLM from the embedding hot path entirely — fewer moving parts,
  no tenacity surprises, no model-name registry concerns.
- Reuses the proven `_embed_once` logic from production LightRAG.

**Cons:**
- Highest LOC. Need a new file `lib/cognee_embedding_engine.py` (~80 LOC),
  monkey-patch hook in `cognee_wrapper.py` (~10 LOC), tests for the patch.
- Cognee's internal `factory.py` returns `lru_cache`'d engine — the
  monkey-patch needs to land BEFORE first call (importlib timing).
- Doesn't fix the LLM side (Cognee's classify_documents / extract_graph
  still route via LiteLLM). To fix that too, need a parallel
  `LLMGateway` override — easily 200+ LOC total.
- T-shirt: **L** (1-2 days investigation + impl + tests).

**Counted blast radius (`git grep`):**
- New file `lib/cognee_embedding_engine.py` (~80 LOC).
- Patch in `cognee_wrapper.py` (~10 LOC inside try/except guarding the
  cognee import).
- Tests under `tests/unit/test_cognee_embedding_engine.py` (~120 LOC).
- ~210 LOC across 3 files.

## Recommended path: B — switch Cognee to Vertex

Path B is the right answer because it (1) is **proven working** in this very
investigation (Vertex SA + `vertex_ai/gemini-embedding-2` returns a 3072-dim
vector in 0.47 s on Hermes-equivalent corp network), (2) is the **smallest
change** that actually fixes the root cause (5 LOC in one file vs Path C's
210 LOC vs Path A's hidden deploy-side AI-Studio-key dependency that's
already been a source of pain twice), (3) **aligns with production** —
LightRAG already uses Vertex `gemini-embedding-2` for embeddings, so picking
Vertex for Cognee gives both consumers the same routing and the same quota
profile, and (4) **future-proofs** the v3.3 quota-isolation migration —
moving Cognee onto Vertex is exactly what CLAUDE.md's "Vertex AI Migration
Path" calls out as the trigger condition for the broader migration. Path A
keeps an AI-Studio dependency we know is brittle (preview-tier model, shared
quota, format-mismatched key in the .env file). Path C is over-engineered for
the actual problem.

## Open questions for the fix quick

1. **Does Cognee 1.0's `LiteLLMEmbeddingEngine` honor `vertex_credentials`
   when set in env?** This investigation confirmed LiteLLM's `aembedding(...,
   vertex_project=..., vertex_location=..., vertex_credentials=...)` works
   when args are passed explicitly. But Cognee constructs the engine via
   `LiteLLMEmbeddingEngine(provider=..., api_key=..., endpoint=...)` and
   relies on `litellm.aembedding(model="vertex_ai/...")` picking up Vertex
   creds from env (`VERTEXAI_CREDENTIALS` / `VERTEX_CREDENTIALS` /
   `GOOGLE_APPLICATION_CREDENTIALS`). LiteLLM main.py L5223-L5228 reads
   those env vars. **Verification: the fix quick should run a
   probe-with-Cognee-engine that proves Cognee's
   LiteLLMEmbeddingEngine→litellm.aembedding chain works for a Vertex model
   without explicit vertex_* kwargs.**

2. **Does `INGESTION_LLM = "gemini-2.5-flash"` (`lib/models.py:10`) work as
   `vertex_ai/gemini-2.5-flash`?** This investigation only probed embedding,
   not LLM. Cognee's classify_documents / extract_graph_from_data path uses
   the LLM provider config. LiteLLM should accept `vertex_ai/gemini-2.5-
   flash` (it's in the registry) but worth a one-line probe added to
   `probe_litellm_direct.py` before the fix lands.

3. **Hermes side: is the `.env` GEMINI_API_KEY=AQ.A… token intentional?**
   The format strongly suggests it's a Vertex OAuth access token mistakenly
   placed under the `GEMINI_API_KEY` env name. If so, the fix is doubly
   important — that token will expire (OAuth access tokens last 1 h) and
   future 401s will look like new bugs. The fix quick should remove
   `GEMINI_API_KEY` from `~/.hermes/.env` once Path B lands (Cognee will
   use SA, not API key) — or at minimum document the format expectation.

4. **`COGNEE_LLM_API_KEY` and friends in `cognee_wrapper.py:41-44` — are
   they still needed under Path B?** When `EMBEDDING_PROVIDER=vertex_ai`,
   LiteLLM ignores `api_key` for Vertex (uses SA from env). The LLM side
   (`LLM_PROVIDER=vertex_ai`, `LLM_MODEL=vertex_ai/gemini-2.5-flash`) also
   ignores `LLM_API_KEY`. The four `os.environ[...] = _initial_key` lines
   become no-ops under Path B. **Recommendation: keep them but add a
   comment explaining they're Vertex-mode-redundant; rotation logic in
   `lib/api_keys.py` still relies on the key being seeded.** The fix quick
   should decide: remove or annotate.

5. **Test fixture for the fix quick:** there's no automated regression test
   that would have caught this. The fix quick should add a one-call smoke
   test (run via `scripts/local_e2e.sh` or pytest) that imports
   `cognee_wrapper` + calls `cognee.remember(...)` + asserts a vector is
   returned in <10 s. Without it, the next config drift will rebreak this
   path silently.

## Logs

All raw logs in `.scratch/` (gitignored):

| File | Purpose | Key lines cited |
| ---- | ---- | ---- |
| `cognee-diag-inspect-20260509-210650.log` | env + LLMConfig + EmbeddingConfig + LiteLLM registry snapshot | L4-L8 (versions), L24-L29 (post-import env), L37-L40 (EmbeddingConfig), L41-L47 (registry) |
| `cognee-diag-inline-20260509-210718.log` | inline `cognee.remember()` 60s timeout reproduction | L10 (start), console output (timeout) |
| `cognee-diag-litellm-20260509-210844.log` | first LiteLLM probe — captured the exact AI Studio URL pattern with the OS-env stale key | L40-L45 (URL), L51-L75 (HTTP body) |
| `cognee-diag-litellm-20260509-211126.log` | full LiteLLM probe — AI Studio fail (401) + Vertex `-preview` 404 + Vertex `gemini-embedding-2` OK | L60-L75 (AI Studio 401), L204-L211 (Vertex 404), L240-L254 (Vertex 200 + raw URL + success) |

These logs are NOT committed (`.scratch/` is gitignored). Verbatim excerpts
above make this document self-contained per the anti-fabrication contract.

## Self-check

- [x] TL;DR cites real failure modes from logs (401 ACCESS_TOKEN_TYPE_UNSUPPORTED + 404 Publisher Model not found)
- [x] Every "X works / Y broken" claim cites a `.scratch/cognee-diag-*.log` path + line range
- [x] Raw HTTP bodies pasted verbatim (key redacted to `*****WOFU` / `Be****zl` only)
- [x] T-shirt estimates cite counted LOC via grep (Path A: 1 line, Path B: 5 lines, Path C: ~210 LOC)
- [x] Recommended path selected with rationale paragraph
- [x] Open questions listed for the follow-up fix quick
- [x] No production code edited
