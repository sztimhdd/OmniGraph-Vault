# Model-adapter seam: source-only intake

**Scope:** local source plus the 2026-09-09 redacted production comparison. No provider call, credential read, agent invocation, or paid model request was made.

## Decision

[KNOWN/HIGH] The smallest reusable text-completion seam is `lib.llm_complete.get_llm_func()`. It returns an async callable compatible with LightRAG: prompt, optional system prompt, optional history, extra kwargs, and a plain string result. The registered values are `deepseek`, `vertex_gemini`, `databricks_serving`, `bailian`, and `router`.

[KNOWN/HIGH] A Hermes subscription is not an available Python provider in this tree. The only Hermes bridge found is `skills/hermes_claude_code_bridge`, which shells out to a Claude ACP agent for interactive implementation delegation. It is not a request/response LLM endpoint and cannot meet the LightRAG completion contract. No source evidence shows a stable Hermes gateway inference API, authentication contract, streaming contract, or rate-limit/error mapping. A `hermes_subscription` provider is **UNKNOWN** pending a separately authorized, non-paid capability probe.

## Minimum adapter boundary

After the transport contract is known, add a provider module and select it in `get_llm_func()`:

```python
async def hermes_subscription_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    model: str | None = None,
    **kwargs,
) -> str: ...
```

It must fail explicitly when its route is absent; it must not silently fall back to another provider. One bounded timeout, response-to-string validation, and error propagation that preserves current caller retry/rollback behavior are required. This is a seam description, not an implementation authorization.

## Reuse classification

| Use | Current call path | Reuse status |
| --- | --- | --- |
| LightRAG entity extraction / relationships | `ingest_wechat.get_rag()` → `get_llm_func()` | Directly reusable once dispatch is extended. |
| Full-body Layer-2 classification | `batch_ingest_from_spider._classify_full_body()` uses its provider branch | Requires implementation-time verification that it calls the dispatcher. |
| Batch KOL classification | `batch_classify_kol.py` provider branch | Separate deliberate adapter decision. |
| KB synthesis | `kb/services/synthesize.py` / Databricks factory | Separate error contract; do not couple by default. |
| Vision | `lib/vision_cascade.py` uses multimodal OpenAI-compatible HTTP | Not reusable: image-content contract. |
| Embedding | `lib/lightrag_embedding.py` uses local BGE-M3 HTTP or Vertex SDK | Not reusable: vector/batch contract. |

## Production drift relevant to this decision

[KNOWN/HIGH] Old pipeline differs from main in `lib/llm_router.py`, `lib/llm_client.py`, `lib/models.py`, `lib/lightrag_embedding.py`, `lib/vision_cascade.py`, and `lib/llm_bailian.py`. Fresh selected-file hashes confirm those differences. `batch_ingest_from_spider.py` and `ingest_wechat.py` match old pipeline byte-for-byte, so the top-level ingest binding is stable.

[KNOWN/HIGH] `lib/llm_router.py` is documented disabled for entity extraction; do not start a Hermes adaptation from `router`. `lib/llm_deepseek.py` is OpenAI-compatible but hardcodes the DeepSeek base URL, so it is behavioral reference rather than generic transport seam.

## Python dependency inventory

| Need | Existing declaration / import | Adapter relevance |
| --- | --- | --- |
| Async OpenAI-compatible client | `openai>=1.50.0`; `lib.llm_deepseek` | Reuse only if the Hermes route supports this protocol. |
| HTTP client | `requests`; `httpx` already imported for local embeddings | Sufficient for a documented HTTP route. |
| Retry | `tenacity` in `lib.llm_client` | Reuse only after retryable errors are specified. |
| Gemini / Vertex | `google-genai` | Existing alternative, not required for Hermes text route. |
| LightRAG | existing callback consumer | Consumer contract, not adapter transport dependency. |

## Evidence

- [dispatcher](../../../lib/llm_complete.py:30)
- [DeepSeek callback reference](../../../lib/llm_deepseek.py:78)
- [ingest binding](../../../ingest_wechat.py:247)
- [deprecated router](../../../lib/llm_router.py:1)
- [vision boundary](../../../lib/vision_cascade.py:340)
- [embedding boundary](../../../lib/lightrag_embedding.py:222)
- [production comparison](../2026-09-09/code-comparison.json)

