---
phase: 05-pipeline-automation
plan: 00c
type: execute
wave: 0
depends_on: []
files_modified:
  - lightrag_llm.py
  - lightrag_embedding.py
  - ingest_wechat.py
  - ingest_github.py
  - query_lightrag.py
  - multimodal_ingest.py
  - omnigraph_search/query.py
  - batch_classify_kol.py
  - batchkol_topic.py
  - _reclassify.py
  - enrichment/extract_questions.py
  - batch_ingest_from_spider.py
  - cognee_wrapper.py
  - tests/unit/test_lightrag_llm.py
  - tests/unit/test_lightrag_embedding_rotation.py
  - .planning/phases/05-pipeline-automation/05-00c-audit.md
  - .planning/phases/05-pipeline-automation/05-00c-SUMMARY.md
autonomous: true
requirements: [D-01, D-02, D-03, D-15, D-16]
user_setup:
  - service: deepseek
    why: "All LightRAG LLM calls (entity extraction, relationships, summarization) route to Deepseek to release Gemini's generate_content pool for other uses; Gemini keys reserved for embedding-only"
    env_vars:
      - name: DEEPSEEK_API_KEY
        source: "~/.hermes/.env — already set; remote probe confirmed reachable and returned models [deepseek-v4-flash, deepseek-v4-pro]"
  - service: gemini
    why: "Embedding calls rotate across GEMINI_API_KEY and GEMINI_API_KEY_BACKUP to double daily budget (IF keys are on different GCP projects; free-tier quota is per-project-per-model)"
    env_vars:
      - name: GEMINI_API_KEY
        source: "~/.hermes/.env — primary embedding key"
      - name: GEMINI_API_KEY_BACKUP
        source: "~/.hermes/.env — backup embedding key used by rotation on 429"
must_haves:
  truths:
    - "A shared module `lightrag_llm.py` at repo root exports `deepseek_model_complete` matching LightRAG's `llm_model_func` contract (async, text-only, supports system_prompt/history_messages/keyword_extraction kwargs)"
    - "`deepseek_model_complete` uses OpenAI-compatible SDK against `https://api.deepseek.com/v1` with `deepseek-v4-flash` default (overridable via DEEPSEEK_MODEL env var)"
    - "`lightrag_embedding.py` rotates across `GEMINI_API_KEY` and `GEMINI_API_KEY_BACKUP` per-call round-robin with automatic failover on 429 (`RESOURCE_EXHAUSTED`) — if one key exhausts, the next call uses the other; if both 429, propagate exception"
    - "All 5 LightRAG `llm_model_func` production sites (ingest_wechat, ingest_github, query_lightrag, multimodal_ingest, omnigraph_search/query) import and use `deepseek_model_complete` — no direct Gemini LLM calls remain in LightRAG-driven paths"
    - "Classification + enrichment scripts (batch_classify_kol, batchkol_topic, _reclassify, enrichment/extract_questions) route to Deepseek via the same shared wrapper"
    - "Vision calls (multimodal_ingest image description, any Gemini Vision usage) remain on Gemini — the swap is LLM-only, not multimodal"
    - "`tests/unit/test_lightrag_llm.py` passes 100% mocked, no live Deepseek calls"
    - "`tests/unit/test_lightrag_embedding_rotation.py` verifies round-robin selection, 429 failover, and both-keys-429 exception propagation"
    - "A remote smoke test ingests 1 small doc end-to-end and confirms: (1) Deepseek invoked (evidence in logs); (2) both Gemini keys rotated (evidence in rotation telemetry)"
    - "Cognee binding decision is documented: EITHER Cognee stays on Gemini (justified) OR Cognee is also swapped to Deepseek (justified + env vars changed)"
  artifacts:
    - path: "lightrag_llm.py"
      provides: "Shared Deepseek LLM wrapper matching LightRAG llm_model_func signature; single source of truth for LLM completion across the pipeline"
      contains: "def deepseek_model_complete"
      min_lines: 80
    - path: "lightrag_embedding.py"
      provides: "Multi-key rotation + 429 failover on top of Task 05-00's in-band multimodal handling at 3072 dim"
      contains: "_KEY_POOL"
    - path: "tests/unit/test_lightrag_llm.py"
      provides: "Contract tests for Deepseek wrapper — signature compat, env handling, error propagation, system_prompt+history_messages shape"
      min_lines: 60
    - path: "tests/unit/test_lightrag_embedding_rotation.py"
      provides: "Unit tests for key pool: round-robin, 429 failover, both-keys-429 exception, single-key fallback (empty BACKUP)"
      min_lines: 80
    - path: ".planning/phases/05-pipeline-automation/05-00c-audit.md"
      provides: "Task 0c.0 research findings — whether to extend lib/ or create fresh lightrag_llm.py; LLM call-site inventory with decisions per site"
      contains: "Decision:"
    - path: ".planning/phases/05-pipeline-automation/05-00c-SUMMARY.md"
      provides: "Plan SUMMARY with files changed, tests added, smoke-test result, Cognee decision, and Wave 0 runtime unblock status"
  key_links:
    - from: "ingest_wechat.py, ingest_github.py, query_lightrag.py, multimodal_ingest.py, omnigraph_search/query.py"
      to: "lightrag_llm.py"
      via: "from lightrag_llm import deepseek_model_complete"
      pattern: "from lightrag_llm import deepseek_model_complete"
    - from: "lightrag_llm.deepseek_model_complete"
      to: "Deepseek OpenAI-compat endpoint"
      via: "openai.AsyncOpenAI(base_url='https://api.deepseek.com/v1') or litellm acompletion"
      pattern: "api.deepseek.com"
    - from: "lightrag_embedding._KEY_POOL"
      to: "os.environ GEMINI_API_KEY + GEMINI_API_KEY_BACKUP"
      via: "module-init reads both, per-call picks via round-robin counter"
      pattern: "GEMINI_API_KEY_BACKUP"
    - from: "batch_classify_kol.py, batchkol_topic.py, _reclassify.py, enrichment/extract_questions.py"
      to: "lightrag_llm.deepseek_model_complete"
      via: "shared wrapper used by LightRAG AND standalone LLM callers"
      pattern: "deepseek_model_complete"
---

<objective>
Unblock Plan 05-00's Wave 0 runtime (currently stuck at Case C zero-progress after 5 attempts) by eliminating the Gemini generate_content + embedding quota coupling: all LLM calls route to Deepseek (releases Gemini generate_content pool), embedding calls rotate across 2 Gemini keys (effectively doubles daily embed budget when keys are on separate GCP projects).

Purpose: Phase 5's daily-pipeline goal (unattended cron) is incompatible with single-free-tier-key Gemini because LightRAG's entity extraction consumes both LLM quota (generate_content) and embedding quota (embed_content) from the same project. Separating them gives two independent failure axes: LLM can only be throttled by Deepseek side, embeddings can only be throttled by Gemini side, and embedding itself is spread across 2 keys.

Scope: FULL pipeline per user decision — all 7 production `llm_model_func` call sites + classification scripts + enrichment. Vision and embedding stay on Gemini (embedding now rotation-enabled). Cognee binding is audited and decided per-case.

Output: `lightrag_llm.py` as single source of truth for LLM completion; `lightrag_embedding.py` with key rotation on top of Task 05-00's 3072-dim native multimodal base; all in-scope files rewired; two unit test suites; audit doc + plan SUMMARY.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
@$HOME/.claude/get-shit-done/references/checkpoints.md
@$HOME/.claude/get-shit-done/references/tdd.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-00-embedding-migration-and-consolidation-PLAN.md
@.planning/phases/05-pipeline-automation/05-00-SUMMARY.md
@CLAUDE.md
@lightrag_embedding.py
@ingest_wechat.py
@ingest_github.py
@query_lightrag.py
@multimodal_ingest.py
@cognee_wrapper.py

<interfaces>
From LightRAG (`venv/Lib/site-packages/lightrag/lightrag.py:400`):

```python
# llm_model_func is called with:
# (prompt: str, system_prompt: str | None = None, history_messages: list[dict] = [], **kwargs) -> str
# kwargs may include: keyword_extraction (bool), stream (bool), hashing_kv (obj for caching)
# MUST return a plain string (the model's text response), NOT a streaming iterator
```

Existing call sites follow the pattern:
```python
async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    # ... construct messages ...
    response = await client.generate_content(...)
    return response.text
```

Deepseek OpenAI-compat target signature:
```python
from openai import AsyncOpenAI

_client = AsyncOpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com/v1",
)

async def deepseek_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    **kwargs,
) -> str:
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    resp = await _client.chat.completions.create(
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        messages=messages,
        stream=False,
    )
    return resp.choices[0].message.content
```

Key rotation target for `lightrag_embedding.py`:
```python
_KEY_POOL = [
    os.environ.get("GEMINI_API_KEY"),
    os.environ.get("GEMINI_API_KEY_BACKUP"),
]
_KEY_POOL = [k for k in _KEY_POOL if k]  # drop None/empty
if not _KEY_POOL:
    raise RuntimeError("No Gemini keys available (need GEMINI_API_KEY)")

_rotation_index = itertools.cycle(range(len(_KEY_POOL)))

async def _embed_with_rotation(contents):
    tried: set[int] = set()
    while len(tried) < len(_KEY_POOL):
        idx = next(_rotation_index)
        if idx in tried:
            continue
        tried.add(idx)
        key = _KEY_POOL[idx]
        try:
            client = genai.Client(api_key=key)
            return await client.aio.models.embed_content(...)
        except ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                continue  # try next key
            raise
    raise RuntimeError("All Gemini keys exhausted (429)")
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0c.0: Audit existing LLM abstractions in lib/ and call-site inventory</name>
  <files>.planning/phases/05-pipeline-automation/05-00c-audit.md</files>
  <read_first>
    - lib/models.py
    - lib/llm_client.py
    - lib/__init__.py
    - tests/unit/test_models.py
    - tests/unit/test_llm_client.py
    - cognee_wrapper.py lines 1-60
    - cognee_batch_processor.py
    - All 7 production call sites noted in frontmatter
  </read_first>
  <action>
    Produce `.planning/phases/05-pipeline-automation/05-00c-audit.md` with:

    **Section 1 — lib/ inventory.** What does `lib/models.py` + `lib/llm_client.py` already abstract? If there's a multi-provider pattern we can extend, document it and choose: extend lib/ vs create fresh `lightrag_llm.py`. Default recommendation: fresh `lightrag_llm.py` adjacent to `lightrag_embedding.py` for consistency, UNLESS lib/ already has a fully functional Deepseek path we just need to wire.

    **Section 2 — call-site inventory.** For each of the 7 production sites + 4 classification/enrichment sites, document:
    - Current LLM vendor + model (e.g., gemini-2.5-flash, gemini-2.5-flash-lite)
    - Current call pattern (direct SDK vs wrapper)
    - Swap complexity (trivial import change vs contract mismatch)
    - Any site-specific risks (grounding, tool-use, streaming)

    **Section 3 — Cognee decision.** Read `cognee_wrapper.py` lines 25-60 for current binding. Choose:
    - **Keep on Gemini** if: Cognee is already async-decoupled from fast path AND its LLM volume is small AND env-var swap would cascade into Cognee internal model registry changes
    - **Swap to Deepseek** if: Cognee's LLM volume is meaningful AND env-var-only swap suffices (e.g., `LLM_PROVIDER=openai` + `OPENAI_API_BASE=https://api.deepseek.com/v1`)

    Document decision + justification in a few sentences. Whichever path chosen, surface this to subsequent tasks — if "swap", a later task must actually implement it; if "keep", Task 0c.4 skips Cognee.

    **Section 4 — final plan of attack.** 2-3 bullets mapping each remaining task to concrete file-level changes, referencing Section 2's inventory.
  </action>
  <verify>
    <automated>test -f .planning/phases/05-pipeline-automation/05-00c-audit.md &amp;&amp; grep -q "Decision:" .planning/phases/05-pipeline-automation/05-00c-audit.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists and is ≥ 40 lines.
    - Contains explicit "Decision:" lines for (a) lib/ extend vs fresh, (b) Cognee keep vs swap.
    - Lists all 11 call sites with current model and swap complexity per site.
  </acceptance_criteria>
  <done>Audit committed; subsequent tasks reference it for implementation choices.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 0c.1: Shared `lightrag_llm.py` with Deepseek wrapper + unit tests</name>
  <files>lightrag_llm.py, tests/unit/test_lightrag_llm.py</files>
  <behavior>
    - Test 1: `deepseek_model_complete("hi")` constructs a single-message `user` role call to Deepseek chat completions; verify via mock of `AsyncOpenAI.chat.completions.create` that `model=deepseek-v4-flash` and messages is `[{"role":"user","content":"hi"}]`.
    - Test 2: With `system_prompt="sys"`, messages become `[{"role":"system","content":"sys"},{"role":"user","content":"hi"}]`.
    - Test 3: With `history_messages=[{"role":"user","content":"prev"},{"role":"assistant","content":"prev-reply"}]`, messages are ordered `[system?, prev, prev-reply, user-current]`.
    - Test 4: Response extraction returns `response.choices[0].message.content` as a plain string.
    - Test 5: `DEEPSEEK_MODEL` env var overrides model ("deepseek-v4-pro" test).
    - Test 6: Missing `DEEPSEEK_API_KEY` at import time raises `RuntimeError` with clear message.
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-00c-audit.md (Section 1 — extend-vs-fresh decision)
    - lightrag_embedding.py (naming + structural convention to match)
    - CLAUDE.md (simplicity first — one function, not a provider registry)
    - Any existing `lib/llm_client.py` if audit says to extend
  </read_first>
  <action>
    Create `lightrag_llm.py` at repo root (per audit decision; if audit chose extend-lib/, adapt accordingly). The module:

    - Single public async function: `deepseek_model_complete`
    - Signature exactly matches LightRAG's `llm_model_func` expectations (prompt: str, system_prompt: str|None=None, history_messages: list|None=None, **kwargs) -> str
    - Uses `openai.AsyncOpenAI` with `base_url="https://api.deepseek.com/v1"`
    - Reads `DEEPSEEK_API_KEY` at module init; raises at init if missing
    - Reads `DEEPSEEK_MODEL` env var with default `"deepseek-v4-flash"`
    - Handles `keyword_extraction` kwarg gracefully (LightRAG passes it for some calls; Deepseek ignores it, we just don't forward it)
    - Returns plain string (no streaming)
    - Module-level `_client` singleton (don't create client per call)

    Unit tests in `tests/unit/test_lightrag_llm.py` use `pytest.mark.asyncio` and `unittest.mock.AsyncMock` for `AsyncOpenAI.chat.completions.create`. NO live API calls.

    If the audit recommends extending `lib/llm_client.py` instead, put the function there and re-export from `lightrag_llm.py` (so the import pattern `from lightrag_llm import deepseek_model_complete` is stable regardless).
  </action>
  <verify>
    <automated>ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; source venv/bin/activate &amp;&amp; python -m pytest tests/unit/test_lightrag_llm.py -v"</automated>
  </verify>
  <acceptance_criteria>
    - `lightrag_llm.py` exists; contains `async def deepseek_model_complete` and module-level `_client` singleton.
    - `grep -q "api.deepseek.com" lightrag_llm.py` returns 0.
    - `grep -q "deepseek-v4-flash" lightrag_llm.py` returns 0.
    - `grep -q "DEEPSEEK_API_KEY" lightrag_llm.py` returns 0.
    - 6 unit tests pass (mocked, no live API).
    - Module import on remote succeeds: `python -c "from lightrag_llm import deepseek_model_complete; print(deepseek_model_complete)"` — prints function repr.
  </acceptance_criteria>
  <done>Deepseek wrapper ready for import across the 5+ call sites.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 0c.2: Key rotation in `lightrag_embedding.py` + unit tests</name>
  <files>lightrag_embedding.py, tests/unit/test_lightrag_embedding_rotation.py</files>
  <behavior>
    - Test 1 (single-key fallback): `GEMINI_API_KEY_BACKUP` unset → pool has 1 key → every call uses it.
    - Test 2 (round-robin): 2 keys configured → 4 successive calls use keys in order `[A, B, A, B]`.
    - Test 3 (429 failover): 2 keys, key A returns 429 on first call → rotation falls through to key B within the same call → test sees key B's mocked response.
    - Test 4 (both 429): Both keys return 429 → raise `RuntimeError("All Gemini keys exhausted")`.
    - Test 5 (non-429 error passes through): Key A raises a 500/network error → does NOT rotate, propagates exception to caller.
    - Test 6 (empty BACKUP line): `GEMINI_API_KEY_BACKUP=""` → treated as no-backup (pool size 1).
  </behavior>
  <read_first>
    - lightrag_embedding.py current state (post Task 05-00 0.2 — at 3072 dim)
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md Pitfall 5 (`_priority` forwarding)
    - CLAUDE.md (Surgical Changes — keep the Task 05-00 in-band multimodal and `_priority` handling intact)
  </read_first>
  <action>
    Extend `lightrag_embedding.py` WITHOUT breaking its existing contract (same decorator, same signature, same output shape at 3072 dim). Changes:

    1. Replace single-key `os.environ["GEMINI_API_KEY"]` read inside `embedding_func` with a module-level `_KEY_POOL` built at import time from `GEMINI_API_KEY` + `GEMINI_API_KEY_BACKUP`.
    2. Add a module-level `_rotation_index = itertools.cycle(range(len(_KEY_POOL)))` for round-robin.
    3. Wrap the actual Gemini call (currently a single `client.aio.models.embed_content(...)`) in a per-call retry loop:
        - Pick next key from rotation
        - Attempt the call
        - On `google.genai.errors.ClientError` where `error.code == 429` OR "RESOURCE_EXHAUSTED" in message: record this key as failed for THIS call, try next
        - If all keys fail with 429: raise `RuntimeError("All Gemini keys exhausted (429)")`
        - Any other exception: raise immediately (don't rotate on 5xx / network errors)
    4. Preserve the existing L2-normalization, task-prefix routing, `_priority` popping, and in-band multimodal handling.

    Unit tests use `monkeypatch` to set env vars per test + mock `genai.Client` at the `google.genai` module level.

    **Keep the change SURGICAL.** Do NOT refactor the decorator, do NOT rename `embedding_func`, do NOT touch the L2 norm block or the multimodal `_build_contents` helper. Only add the key-pool init + rotation loop around the actual `embed_content` call.
  </action>
  <verify>
    <automated>ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; source venv/bin/activate &amp;&amp; python -m pytest tests/unit/test_lightrag_embedding_rotation.py tests/unit/test_lightrag_embedding.py -v"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "_KEY_POOL" lightrag_embedding.py` returns 0.
    - `grep -q "GEMINI_API_KEY_BACKUP" lightrag_embedding.py` returns 0.
    - `grep -q "RESOURCE_EXHAUSTED\|429" lightrag_embedding.py` returns 0 (failover logic is present).
    - 6 new rotation tests pass.
    - Original 5 `test_lightrag_embedding.py` tests STILL pass (the `_priority` pop, multimodal, L2 norm, 3072 shape, prefix routing) — regression guard.
  </acceptance_criteria>
  <done>Embedding module now supports multi-key rotation with 429 failover; 3072-dim + multimodal contract preserved.</done>
</task>

<task type="auto">
  <name>Task 0c.3: Swap LightRAG `llm_model_func` across 5 production sites</name>
  <files>ingest_wechat.py, ingest_github.py, query_lightrag.py, multimodal_ingest.py, omnigraph_search/query.py</files>
  <read_first>
    - lightrag_llm.py (Task 0c.1 output)
    - Each of the 5 files' current `llm_model_func` definition + LightRAG construction block
    - .planning/phases/05-pipeline-automation/05-00c-audit.md Section 2 (per-site swap complexity + risks)
    - CLAUDE.md (Surgical Changes — touch only the `llm_model_func` + its single caller line)
  </read_first>
  <action>
    For each of the 5 files:

    1. Remove the local `async def llm_model_func(...)` definition.
    2. Add near the other third-party imports: `from lightrag_llm import deepseek_model_complete`.
    3. Change the `LightRAG(..., llm_model_func=llm_model_func, ...)` line to `LightRAG(..., llm_model_func=deepseek_model_complete, ...)`.
    4. Update `llm_model_name="gemini-2.5-flash"` (if present) to `llm_model_name="deepseek-v4-flash"` (LightRAG uses this for internal logging/caching).
    5. Clean up any now-orphaned imports that only the deleted `llm_model_func` needed (e.g., `from lightrag.llm.gemini import gemini_model_complete`).

    DO NOT touch:
    - Vision calls (`multimodal_ingest.py` may have a separate image-description path using Gemini Vision — leave it)
    - `embedding_func` imports and usage (already handled by Task 0c.2)
    - Any non-LightRAG code paths (CDP scraping, file I/O, etc.)

    Remote smoke-import check after each file: `python -c "import <module>"` must succeed.
  </action>
  <verify>
    <automated>ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; grep -c '^from lightrag_llm import deepseek_model_complete' ingest_wechat.py ingest_github.py query_lightrag.py multimodal_ingest.py omnigraph_search/query.py | awk -F: '{s+=\$2} END {exit !(s==5)}'" &amp;&amp; ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; source venv/bin/activate &amp;&amp; python -c 'import ingest_wechat, ingest_github, query_lightrag, multimodal_ingest; import omnigraph_search.query'"</automated>
  </verify>
  <acceptance_criteria>
    - Exactly 5 files contain exactly one `from lightrag_llm import deepseek_model_complete` line.
    - `grep -l "llm_model_func=deepseek_model_complete" ingest_wechat.py ingest_github.py query_lightrag.py multimodal_ingest.py omnigraph_search/query.py` returns all 5.
    - Zero files retain a `from lightrag.llm.gemini import gemini_model_complete` import — `grep -l "from lightrag.llm.gemini import gemini_model_complete" *.py omnigraph_search/*.py` returns empty.
    - All 5 modules import cleanly on remote.
  </acceptance_criteria>
  <done>LightRAG ingestion/query paths all route LLM to Deepseek.</done>
</task>

<task type="auto">
  <name>Task 0c.4: Swap LLM in classification + enrichment scripts</name>
  <files>batch_classify_kol.py, batchkol_topic.py, _reclassify.py, enrichment/extract_questions.py, batch_ingest_from_spider.py</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-00c-audit.md Section 2 (current LLM model per file)
    - Each file's current LLM call pattern (direct SDK call? helper function?)
    - CLAUDE.md
  </read_first>
  <action>
    For each script, audit its LLM call shape and swap to Deepseek via `lightrag_llm.deepseek_model_complete`. Because classification is typically structured-JSON output, the swap may require:

    - Replace direct `google.genai` / `gemini_2.5_flash` calls with `await deepseek_model_complete(prompt, system_prompt=...)`
    - Adjust any response-parsing (Deepseek chat completions return OpenAI-format; Gemini returned `.text`)
    - Preserve the existing prompt text EXACTLY (per Phase 4 D-12 — same prompt shape produces same extraction quality)

    If any script uses LLM for vision or a Deepseek-incompatible feature (e.g., grounding), document the exception in audit (and optionally route that narrow path to Gemini, but default is full swap).

    For `batch_ingest_from_spider.py`: it depends on the LightRAG ingest path; if it calls `ingest_wechat.py` as a subprocess it already picks up Task 0c.3's swap. If it has its OWN `llm_model_func` definition, swap it too. Verify before editing.

    Scope discipline: only the LLM calls change. Do NOT refactor prompt templates, JSON parsing utilities, or batch orchestration logic.
  </action>
  <verify>
    <automated>ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; source venv/bin/activate &amp;&amp; python -c 'import batch_classify_kol, batchkol_topic, _reclassify, batch_ingest_from_spider' &amp;&amp; python -c 'from enrichment import extract_questions'"</automated>
  </verify>
  <acceptance_criteria>
    - All 5 scripts import cleanly on remote.
    - `grep -l "from lightrag_llm import\|from lightrag_llm\." batch_classify_kol.py batchkol_topic.py _reclassify.py enrichment/extract_questions.py` returns at least 4 files (batch_ingest_from_spider may legitimately stay untouched if it only shells out to ingest_wechat).
    - No file retains a hardcoded `"gemini-2.5-flash"` or `"gemini-2.5-flash-lite"` model name for LLM completion (Vision model names MAY stay — audit documents the distinction).
  </acceptance_criteria>
  <done>Classification/enrichment paths no longer consume Gemini generate_content quota.</done>
</task>

<task type="auto">
  <name>Task 0c.5: Cognee binding decision — keep or swap</name>
  <files>cognee_wrapper.py, cognee_batch_processor.py (only if swap chosen)</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-00c-audit.md Section 3 (Cognee decision)
    - cognee_wrapper.py lines 1-60 (env-var setup)
    - Cognee docs for `LLM_PROVIDER` + `LLM_MODEL` config values
  </read_first>
  <action>
    **If audit chose "keep on Gemini":** No code change. Document in SUMMARY that Cognee continues to use Gemini (acceptable because it's async-decoupled + low volume). Task becomes a no-op.

    **If audit chose "swap to Deepseek":** Change the env-var assignments in `cognee_wrapper.py` (and `cognee_batch_processor.py` if separately configured):
    - `LLM_PROVIDER=openai` (or whatever Cognee uses for OpenAI-compat endpoints)
    - Set `OPENAI_API_BASE` or equivalent to `https://api.deepseek.com/v1`
    - Set `OPENAI_API_KEY=${DEEPSEEK_API_KEY}` (or use a Cognee-specific env var)
    - Embeddings side: decide whether to also move Cognee's embedding backend or keep Gemini — document both decisions

    Smoke test after change: `python cognee_batch_processor.py --once` (or equivalent dry-run) must complete without raising.
  </action>
  <verify>
    <automated>ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault &amp;&amp; source venv/bin/activate &amp;&amp; python -c 'import cognee_wrapper'"</automated>
  </verify>
  <acceptance_criteria>
    - Module imports cleanly regardless of decision.
    - If "swap": `grep -q 'api.deepseek.com\|deepseek' cognee_wrapper.py` returns 0.
    - If "keep": audit doc + SUMMARY both explicitly state "Cognee remains on Gemini" with justification.
  </acceptance_criteria>
  <done>Cognee binding is either intentionally preserved or cleanly swapped per audit.</done>
</task>

<task type="auto">
  <name>Task 0c.6: Remote integration smoke test — 1 doc end-to-end</name>
  <files>docs/spikes/wave0c_smoke_log.md</files>
  <read_first>
    - All prior tasks' output
    - scripts/wave0_reembed.py (for reference on how LightRAG construction works post-rewire)
  </read_first>
  <action>
    On remote WSL, perform an end-to-end smoke test that exercises:
    1. Deepseek LLM wrapper (entity extraction)
    2. Both Gemini keys (rotation telemetry)
    3. 3072-dim embedding storage
    4. LightRAG `ainsert` of ONE small doc

    Approach: pick one doc from `kv_store_full_docs.json.bak` (smallest is fine), wipe the 3 `vdb_*.json` files + `kv_store_*.json` + graphml (per Task 05-00 Task 0.4 wipe list), then run a minimal Python script:

    ```python
    # scripts/wave0c_smoke.py (temporary — do NOT commit)
    import asyncio, json, os
    from pathlib import Path
    from config import RAG_WORKING_DIR
    from lightrag_embedding import embedding_func
    from lightrag_llm import deepseek_model_complete
    from lightrag import LightRAG

    async def main():
        # pick smallest doc from the backup
        backup = json.loads((Path(RAG_WORKING_DIR) / "kv_store_full_docs.json.bak").read_text())
        doc_id, doc = min(backup.items(), key=lambda kv: len(kv[1].get("content","")))
        print(f"smoke doc: {doc_id} ({len(doc['content'])} chars)")

        rag = LightRAG(
            working_dir=RAG_WORKING_DIR,
            llm_model_func=deepseek_model_complete,
            embedding_func=embedding_func,
            llm_model_name="deepseek-v4-flash",
            embedding_func_max_async=1,
            embedding_batch_num=20,
            llm_model_max_async=2,
        )
        await rag.initialize_storages()
        await rag.ainsert(doc["content"])
        print("OK ingested")

    asyncio.run(main())
    ```

    After run:
    - Verify `vdb_chunks.json` `embedding_dim: 3072` (post-run)
    - Verify logs show Deepseek URL (`api.deepseek.com`) and NO `generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent` for LLM calls
    - Verify rotation telemetry (add lightweight `_ROTATION_HITS: dict[str, int]` counter in lightrag_embedding.py during Task 0c.2; smoke assert both keys hit ≥1)

    Write findings to `docs/spikes/wave0c_smoke_log.md`:
    ```
    # Plan 05-00c Smoke Test Log
    date: YYYY-MM-DD
    doc_id: <id>
    doc_size_chars: <N>
    embed_calls: <N>
    llm_calls: <N>
    deepseek_invoked: true|false
    gemini_llm_invoked: true|false (must be false)
    key_rotation_hits: {key_A: N, key_B: M}
    final_vdb_embedding_dim: 3072
    result: pass|fail
    notes: ...
    ```

    If smoke FAILS (e.g., Deepseek 4xx, rotation broken, dim mismatch): return a checkpoint with the log. Do NOT force-pass.

    If keys are both 429 at smoke time (quota exhausted): document that the code-level swap succeeded but live validation is blocked on API budget. Still OK to mark plan complete IF unit tests pass AND the code-level acceptance criteria all pass — log a follow-up "smoke test pending API budget reset" item.
  </action>
  <verify>
    <automated>test -f docs/spikes/wave0c_smoke_log.md &amp;&amp; grep -E "^(deepseek_invoked|gemini_llm_invoked|result):" docs/spikes/wave0c_smoke_log.md | wc -l | grep -q "^3$"</automated>
  </verify>
  <acceptance_criteria>
    - `docs/spikes/wave0c_smoke_log.md` exists with all required keys.
    - `deepseek_invoked: true`.
    - `gemini_llm_invoked: false` (LLM side fully swapped).
    - `final_vdb_embedding_dim: 3072` (OR `result: pending_api_budget` if keys drained).
    - If result is `pass`: the one test doc is in the graph (vdb rows > 0, doc_status=processed).
  </acceptance_criteria>
  <done>End-to-end pipeline validated with Deepseek + rotation; Wave 0 runtime retry can then proceed.</done>
</task>

</tasks>

<verification>
- `lightrag_llm.py` exists with `deepseek_model_complete`; 6 unit tests pass.
- `lightrag_embedding.py` supports key rotation + 429 failover; existing tests still pass; 6 new rotation tests pass.
- 5 production `llm_model_func` sites use Deepseek import.
- 4+ classification/enrichment scripts swapped.
- Cognee binding documented (keep or swap).
- Smoke test on remote produces `wave0c_smoke_log.md` with `deepseek_invoked: true` and `gemini_llm_invoked: false` (and result=pass OR pending_api_budget with justification).
</verification>

<success_criteria>
- All 6 tasks executed and committed atomically (--no-verify).
- Unit test count added: 12 (6 Deepseek + 6 rotation) — all passing.
- Zero Gemini LLM calls in LightRAG-driven paths (grep audit confirms).
- Smoke test output committed at `docs/spikes/wave0c_smoke_log.md`.
- Per-plan ROADMAP update via `roadmap update-plan-progress 05 00c complete`.
- STATE.md advanced per-plan (do NOT call phase complete — 05-00 runtime still pending).
- SUMMARY at `.planning/phases/05-pipeline-automation/05-00c-SUMMARY.md` with: audit decision, files changed per task, test pass counts, Cognee decision, smoke test result, and an explicit "Wave 0 runtime unblocker status" section noting that Plan 05-00 runtime should now be retryable.
</success_criteria>

<output>
`.planning/phases/05-pipeline-automation/05-00c-SUMMARY.md` with the sections listed in success_criteria.

The SUMMARY must include a **"Hand-off to Plan 05-00 runtime"** section listing the exact command to retry Wave 0 after this plan merges:
```
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python scripts/wave0_reembed.py --i-understand"
```
and noting that with 2-key rotation + Deepseek-only LLM, the 22-doc re-embed should succeed in a single pass (~1200 embed calls spread across 2 key buckets + 0 generate_content calls).
</output>
