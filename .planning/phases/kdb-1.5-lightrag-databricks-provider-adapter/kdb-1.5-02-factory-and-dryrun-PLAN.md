---
phase: kdb-1.5-lightrag-databricks-provider-adapter
plan: 02
type: execute
wave: 2
depends_on:
  - "01"
files_modified:
  - databricks-deploy/lightrag_databricks_provider.py
  - databricks-deploy/tests/test_provider_dryrun.py
  - databricks-deploy/tests/fixtures/article_zh_1.txt
  - databricks-deploy/tests/fixtures/article_zh_2.txt
  - databricks-deploy/tests/fixtures/article_en_1.txt
  - databricks-deploy/tests/fixtures/article_en_2.txt
  - databricks-deploy/tests/fixtures/article_en_3.txt
  - databricks-deploy/pytest.ini
  - databricks-deploy/requirements.txt
autonomous: true
requirements:
  - LLM-DBX-03
priority: P0
estimated_loc: 320
estimated_time: 2.5h
skills_required:
  - databricks-patterns
  - search-first

must_haves:
  truths:
    - "make_llm_func() returns a LightRAG-compatible callable that wraps databricks-claude-sonnet-4-6 via WorkspaceClient"
    - "make_embedding_func() returns an EmbeddingFunc (dim=1024, max_token_size=8192) that wraps databricks-qwen3-embedding-0-6b"
    - "Synchronous SDK calls are wrapped in loop.run_in_executor to preserve async event-loop"
    - "Dry-run e2e test produces graphml + vector json files under /tmp/lightrag_storage_dryrun_<ts>/"
    - "At least one vdb_*.json file written by LightRAG has a vector entry of length 1024"
    - "Test teardown cleans up /tmp/lightrag_storage_dryrun_*/"
  artifacts:
    - path: "databricks-deploy/lightrag_databricks_provider.py"
      provides: "make_llm_func() + make_embedding_func() factories — LLM-DBX-03 deliverable"
      exports: ["make_llm_func", "make_embedding_func", "KB_LLM_MODEL", "KB_EMBEDDING_MODEL", "EMBEDDING_DIM"]
      min_lines: 100
    - path: "databricks-deploy/tests/test_provider_dryrun.py"
      provides: "4 tests: LLM smoke, embedding smoke, e2e roundtrip, bilingual sanity"
      min_lines: 150
    - path: "databricks-deploy/tests/fixtures/"
      provides: "5 short fixture articles (2 zh + 3 en) for dry-run"
  key_links:
    - from: "databricks-deploy/lightrag_databricks_provider.py"
      to: "databricks.sdk.WorkspaceClient.serving_endpoints.query"
      via: "loop.run_in_executor + ChatMessage list"
      pattern: "serving_endpoints\\.query"
    - from: "databricks-deploy/lightrag_databricks_provider.py"
      to: "lightrag.utils.wrap_embedding_func_with_attrs"
      via: "decorator on _embed (embedding_dim=1024, max_token_size=8192)"
      pattern: "wrap_embedding_func_with_attrs|EmbeddingFunc"
    - from: "databricks-deploy/tests/test_provider_dryrun.py"
      to: "lightrag.LightRAG"
      via: "real ainsert + aquery against real MosaicAI endpoints"
      pattern: "from lightrag import LightRAG|LightRAG\\("
---

<objective>
Implement `databricks-deploy/lightrag_databricks_provider.py` — the LLM-DBX-03 factory file that exports `make_llm_func()` and `make_embedding_func()`, wrapping MosaicAI Model Serving (`databricks-claude-sonnet-4-6` + `databricks-qwen3-embedding-0-6b` dim=1024) for LightRAG instantiation.

This phase IS the dry-run venue for LLM-DBX-03. The companion test `test_provider_dryrun.py` runs as a standalone pytest on the local dev box with user OAuth (per `~/.databrickscfg` `[dev]` profile), instantiating REAL LightRAG against REAL Model Serving endpoints with a synthetic 5-article fixture in `/tmp/lightrag_storage_dryrun_<ts>/`.

**Wave 2 dependency:** This plan depends on plan 01 (Wave 1) having created `databricks-deploy/requirements.txt` (which pins databricks-sdk + lightrag-hku + pytest-asyncio). Plan 02 appends `pytest-asyncio>=0.23.0` to that file ONLY IF plan 01 did not already include it — the verification command checks for its presence first.

## Provider primary path: SDK (WorkspaceClient) — REQ-overrides-RESEARCH rationale

**Decision: SDK-primary (`WorkspaceClient.serving_endpoints.query`), OpenAI-compat fallback.** This contradicts RESEARCH.md Q5 verdict + Summary line 13 which suggest OpenAI-compat-primary. The reconciliation rule:

1. **REQ takes precedence over RESEARCH simplification suggestions.** REQUIREMENTS-kb-databricks-v1.md LLM-DBX-03 (lines 40-44) explicitly lists `WorkspaceClient().serving_endpoints.query(name=KB_LLM_MODEL, ...)` as the implementation shape — this is the binding contract. RESEARCH Q5's "zero-new-HTTP-plumbing" framing is a *simplicity* argument, not a contract argument; REQ wins.
2. **App SP auto-injection in production.** kdb-2 first deploy uses Apps SP credentials auto-injected by the runtime (`DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET`). `WorkspaceClient()` consumes these zero-config. The OpenAI-compat path needs a manually-fetched bearer token at runtime — adds a moving part to kdb-2 production deploy.
3. **Discoverability + debuggability.** SDK shape is more discoverable (typed objects vs raw HTTP/JSON), and SDK errors carry richer context than raw HTTPError responses.
4. **RESEARCH Decision 3 (line 384) is internally consistent with SDK-primary.** RESEARCH.md itself contradicts: Q5 summary says OpenAI-compat-primary, but Decision 3 says SDK-primary citing "milestone-locked auth pattern" + "verbatim REQ shape" — Decision 3 is the authored decision, Q5 is exploratory analysis. We follow Decision 3.

**Acknowledgement:** RESEARCH Q5 summary suggests OpenAI-compat primary; we follow REQ LLM-DBX-03's `WorkspaceClient` pattern per the REQ-overrides-RESEARCH precedence rule. OpenAI-compat is retained ONLY as a fallback if the SDK `input=...` kwarg shape misbehaves at dry-run time (Decision 3 escape hatch in RESEARCH.md).

Purpose:
- Validate the LightRAG ↔ Databricks SDK adapter shape BEFORE kdb-2.5 burns $20–100 on a full re-index
- Surface Risk #2 (SDK shape mismatch) and Risk #3 (Qwen3-0.6B bilingual quality) early
- Lock in the embedding_dim=1024 contract that kdb-2.5 + kdb-2 inherit

Output:
- `databricks-deploy/lightrag_databricks_provider.py` (factory functions, sync→async via run_in_executor, env-var-overridable model names)
- `databricks-deploy/tests/test_provider_dryrun.py` (4 tests; ~10 min wallclock; ~$0.20–$0.80 cost)
- `databricks-deploy/tests/fixtures/article_*.txt` (5 short fixture articles — 2 zh, 3 en; ~200–500 chars each)
- `databricks-deploy/pytest.ini` (registers `dryrun` marker + asyncio_mode auto)
- `databricks-deploy/requirements.txt` (append pytest-asyncio if plan 01 omitted it)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-kb-databricks-v1.md
@.planning/REQUIREMENTS-kb-databricks-v1.md
@.planning/ROADMAP-kb-databricks-v1.md
@.planning/STATE-kb-databricks-v1.md
@.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md
@.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md
@.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-01-SUMMARY.md

<interfaces>
<!-- Concrete contracts. Verbatim from RESEARCH.md Q5 sketch + Decision 3 + REQUIREMENTS LLM-DBX-03 (lines 40-44). -->

Module-level constants (env-var overridable):
  KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
  KB_EMBEDDING_MODEL = os.environ.get("KB_EMBEDDING_MODEL", "databricks-qwen3-embedding-0-6b")
  EMBEDDING_DIM = 1024  # Qwen3-0.6B locked

LightRAG signatures the factories must match (verified in venv/Lib/site-packages/lightrag/):
  llm_model_func(prompt: str, system_prompt: str | None = None,
                 history_messages: list[dict] | None = None,
                 **kwargs) -> Awaitable[str]

  EmbeddingFunc:
    decorated via @wrap_embedding_func_with_attrs(embedding_dim=1024, max_token_size=8192)
    inner async signature: async def _embed(texts: list[str], **_kwargs) -> np.ndarray of shape (N, 1024) dtype=float32

WorkspaceClient.serving_endpoints.query() shape (verified via PREFLIGHT-FINDINGS sub-tests 1.2/1.3):
  LLM call:
    w.serving_endpoints.query(name=KB_LLM_MODEL, messages=[ChatMessage(role=ChatMessageRole.USER, content="...")])
    Returns response with .choices[0].message.content (string)
  Embedding call:
    w.serving_endpoints.query(name=KB_EMBEDDING_MODEL, input=["text1", "text2", ...])
    Returns response with .data: list of objects each with .embedding: list[float]
    NOTE: Q5 caveat #1 — verify the Python SDK kwarg name (input=...) in dry-run test 2.
    If SDK rejects input=... kwarg, fall back to OpenAI-compat shape via lightrag.llm.openai.openai_embed
    with base_url pointed at https://<host>/serving-endpoints (research Decision 3 escape hatch).
    Time-box for this fallback: 30 minutes — if not working in 30 min, escalate.

Dry-run auth path (verified in PREFLIGHT-DBX-01):
  WorkspaceClient() reads ~/.databrickscfg [dev] profile → user OAuth → routes to MosaicAI endpoints.
  No service principal needed for dry-run; that comes in kdb-2 first deploy.

From plan 01 (Wave 1, must be merged first):
  - databricks-deploy/requirements.txt EXISTS with: databricks-sdk>=0.30.0, lightrag-hku==1.4.15, numpy, fastapi, uvicorn, jinja2, markdown, pygments
  - databricks-deploy/CONFIG-EXEMPTIONS.md EXISTS (initial-empty ledger)
  - databricks-deploy/startup_adapter.py EXISTS (adapter for STORAGE-DBX-05)
  - databricks-deploy/tests/__init__.py + conftest.py EXIST

Fixture articles (5 short test docs, ~200–500 chars each):
  - article_zh_1.txt: "LangGraph 是 LangChain 推出的多 Agent 编排框架..."
  - article_zh_2.txt: "CrewAI 是另一个流行的多 Agent 框架,与 LangGraph 不同..."
  - article_en_1.txt: "LangGraph from LangChain is a stateful multi-agent orchestration framework..."
  - article_en_2.txt: "CrewAI is another multi-agent framework that takes a different approach..."
  - article_en_3.txt: "AutoGen by Microsoft is a third multi-agent framework..."

Cross-lingual query test:
  query = "compare LangGraph and CrewAI" (en)
  expect retrieval to surface BOTH zh and en articles (proves bilingual embedding works)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 2.1: Invoke databricks-patterns + search-first Skills for factory design</name>
  <read_first>
    - .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md (Q5 lines 200-317, Decision 3 lines 384-391, Pitfall 4 lines 507-513, Pitfall 5 lines 515-523)
    - C:\Users\huxxha\.claude\skills\databricks-patterns\SKILL.md
    - C:\Users\huxxha\.claude\skills\search-first\SKILL.md
    - .planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md (sub-tests 1.2 + 1.3 — exact CLI invocation that proved both endpoints reachable)
  </read_first>
  <action>
    Invoke TWO Skills explicitly (both must produce literal tool calls):

    Skill 1 — databricks-patterns:

    Skill(skill="databricks-patterns", args="Design databricks-deploy/lightrag_databricks_provider.py wrapping MosaicAI Model Serving for LightRAG. Constraints: (1) Synthesis endpoint=databricks-claude-sonnet-4-6 (env var KB_LLM_MODEL override). (2) Embedding endpoint=databricks-qwen3-embedding-0-6b dim=1024 (env var KB_EMBEDDING_MODEL override). (3) Auth: WorkspaceClient() with no args — reads ~/.databrickscfg [dev] for local dry-run, reads Apps SP injection for kdb-2 deploy. (4) SDK call shape per PREFLIGHT-FINDINGS sub-test 1.2: w.serving_endpoints.query(name=KB_LLM_MODEL, messages=[ChatMessage(role=ChatMessageRole.USER, content=...)]) returning .choices[0].message.content. (5) Embedding call shape per PREFLIGHT sub-test 1.3: w.serving_endpoints.query(name=KB_EMBEDDING_MODEL, input=[...]) returning .data: list[{embedding: list[float]}]. (6) The SDK is synchronous — must wrap in asyncio.get_running_loop().run_in_executor(None, lambda: w.serving_endpoints.query(...)) to preserve LightRAG's async contract (Pitfall 4 in RESEARCH.md). Show me the exact SDK kwarg name for the embedding endpoint — does it accept input=[...] directly, or does it need a different keyword name? If unsure, show me how to defensively branch.")

    Skill 2 — search-first:

    Skill(skill="search-first", args="Before writing custom HTTP wrapper, search lightrag.llm.openai for existing OpenAI-compat shape that can target Databricks serving endpoints with base_url=https://<host>/serving-endpoints + Bearer token. Specifically look at venv/Lib/site-packages/lightrag/llm/openai.py for openai_complete_if_cache and openai_embed signatures. Confirm whether they accept base_url + api_key kwargs that we can populate from databricks auth token. This is the documented fallback in RESEARCH.md Decision 3 if the WorkspaceClient SDK shape misbehaves on the embedding kwarg. Report: (a) exact callable signatures, (b) whether base_url is a kwarg or env var, (c) whether the api_key kwarg accepts a fresh OAuth bearer or only a static API key.")

    Both Skill outputs MUST appear referenced verbatim in eventual SUMMARY.md (literal substrings `Skill(skill="databricks-patterns")` AND `Skill(skill="search-first")`).
  </action>
  <verify>
    <automated>grep -c 'Skill(skill="databricks-patterns")' .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-02-SUMMARY.md && grep -c 'Skill(skill="search-first")' .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-02-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - Both Skills literally invoked as tool calls (not just listed in <read_first>)
    - Outputs captured and inform Task 2.2 implementation choices (especially the `input=...` kwarg disambiguation)
    - Both Skill literal substrings appear in SUMMARY.md (verified at commit time)
  </acceptance_criteria>
  <done>2 Skills invoked; design choices locked for Task 2.2.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.2: Write lightrag_databricks_provider.py + 5 fixture articles + ensure pytest-asyncio installed</name>
  <read_first>
    - .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md (Q5 sketch lines 219-272, Pitfall 4 + Pitfall 5)
    - venv/Lib/site-packages/lightrag/utils.py (lines 421-457 — EmbeddingFunc class definition + double-wrapping warning at line 437)
    - venv/Lib/site-packages/lightrag/llm/openai.py (line 206 — openai_complete_if_cache + openai_embed shapes for fallback context)
    - databricks-deploy/requirements.txt (created in plan 01 — confirm contents before appending)
  </read_first>
  <behavior>
    The file MUST export:
      - make_llm_func() -> async callable matching LightRAG's llm_model_func signature
      - make_embedding_func() -> EmbeddingFunc instance with embedding_dim=1024 attr accessible

    Behavioral contract:
      - LLM call latency < 10s for short prompt (per PREFLIGHT 2.65s baseline + slack)
      - Embedding call returns np.ndarray shape (N, 1024) dtype float32
      - SDK calls wrapped in run_in_executor (NOT direct call from async context)
      - Module-level constants env-var-overridable: KB_LLM_MODEL, KB_EMBEDDING_MODEL

    Anti-pattern: DO NOT instantiate WorkspaceClient at module-import time (lazy-construct inside the factory closure so import doesn't fail in environments without auth).
  </behavior>
  <action>
    Step 1: Confirm `databricks-deploy/requirements.txt` exists (created by plan 01). Read it. If `pytest-asyncio` is not present, append:

    ```
    pytest>=7.4.0
    pytest-asyncio>=0.23.0
    ```

    (Use file-append, NOT overwrite. Plan 01 owns the canonical pin set.)

    Step 2: Install dependencies in the project venv:
      `pip install -r databricks-deploy/requirements.txt`

    (If pip install fails on corp network for any package, confirm `databricks-sdk` and `pytest-asyncio` specifically are installable.)

    Step 3: Write `databricks-deploy/lightrag_databricks_provider.py` with this concrete shape:

    ```python
    """LightRAG ↔ Databricks Model Serving factory.

    Provides make_llm_func() + make_embedding_func() that wrap MosaicAI Model
    Serving endpoints for LightRAG instantiation. Consumed by kdb-2 App startup
    (post LLM-DBX-01 dispatcher integration) and kdb-2.5 re-index Job.

    Auth:
      - Locally: WorkspaceClient() reads ~/.databrickscfg [dev] profile (user OAuth)
      - In Apps:  WorkspaceClient() reads DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET
                  injected automatically by the Apps runtime

    See .planning/phases/kdb-1.5-.../kdb-1.5-RESEARCH.md Q5 + Decision 3.
    """
    from __future__ import annotations

    import asyncio
    import logging
    import os
    from typing import Any

    import numpy as np

    from lightrag.utils import EmbeddingFunc, wrap_embedding_func_with_attrs

    logger = logging.getLogger(__name__)

    KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
    KB_EMBEDDING_MODEL = os.environ.get(
        "KB_EMBEDDING_MODEL", "databricks-qwen3-embedding-0-6b"
    )
    EMBEDDING_DIM = 1024  # Qwen3-0.6B output dim — locked per REQUIREMENTS rev 3
    EMBEDDING_MAX_TOKEN_SIZE = 8192


    def make_llm_func():
        """Return a LightRAG-compatible llm_model_func wrapping MosaicAI sonnet-4-6.

        Lazy-imports databricks-sdk to keep import-time clean.
        Wraps the synchronous SDK call in run_in_executor to preserve
        LightRAG's async event-loop semantics (Pitfall 4 in RESEARCH.md).
        """
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        w = WorkspaceClient()  # closure captures the client

        async def llm_func(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> str:
            history_messages = history_messages or []
            messages: list[ChatMessage] = []
            if system_prompt:
                messages.append(
                    ChatMessage(role=ChatMessageRole.SYSTEM, content=system_prompt)
                )
            for m in history_messages:
                role_str = m.get("role", "user").upper()
                messages.append(
                    ChatMessage(role=ChatMessageRole(role_str), content=m["content"])
                )
            messages.append(ChatMessage(role=ChatMessageRole.USER, content=prompt))

            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: w.serving_endpoints.query(
                    name=KB_LLM_MODEL, messages=messages
                ),
            )
            return resp.choices[0].message.content

        return llm_func


    @wrap_embedding_func_with_attrs(
        embedding_dim=EMBEDDING_DIM,
        max_token_size=EMBEDDING_MAX_TOKEN_SIZE,
    )
    async def _embed(texts: list[str], **_kwargs: Any) -> np.ndarray:
        """Internal embedding callable. Wrapped via decorator with dim metadata."""
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: w.serving_endpoints.query(
                name=KB_EMBEDDING_MODEL, input=texts
            ),
        )
        # SDK returns .data: list[{embedding: list[float]}]
        # If the response shape diverges (e.g., older SDK uses a different key),
        # fall through to a defensive .embeddings attribute check before raising.
        try:
            vectors = [d.embedding for d in resp.data]
        except AttributeError:
            # Fallback shape: response.embeddings or response['data'][i]['embedding']
            data = getattr(resp, "embeddings", None) or resp.data
            vectors = [d["embedding"] if isinstance(d, dict) else d.embedding for d in data]
        return np.array(vectors, dtype=np.float32)


    def make_embedding_func() -> EmbeddingFunc:
        """Return EmbeddingFunc instance wrapping MosaicAI Qwen3-embedding-0-6b.

        DO NOT re-wrap with EmbeddingFunc — _embed is already wrapped via the
        decorator (Pitfall 5 in RESEARCH.md).
        """
        return _embed  # type: ignore[return-value]
    ```

    Step 4: Create 5 fixture article files at `databricks-deploy/tests/fixtures/`. Each ~200–500 chars. Suggested content:

    `article_zh_1.txt`:
    ```
    LangGraph 是 LangChain 团队推出的多 Agent 编排框架,基于状态图(StateGraph)的概念,让开发者可以显式定义多个 Agent 之间的协作流程。核心抽象包括 nodes、edges 和 state,适合需要精细控制 Agent 间消息传递的复杂工作流场景。
    ```

    `article_zh_2.txt`:
    ```
    CrewAI 是另一个流行的多 Agent 框架,与 LangGraph 不同的是,它采用角色驱动(role-based)的设计:每个 Agent 有明确的角色、目标和工具。Crew 概念将多个 Agent 组合成一个团队,适合需要快速搭建多 Agent 协作系统的场景。
    ```

    `article_en_1.txt`:
    ```
    LangGraph from LangChain is a stateful multi-agent orchestration framework built around the StateGraph abstraction. Developers explicitly define nodes, edges, and shared state to create deterministic agent workflows. It excels at complex flows requiring fine-grained control over message passing.
    ```

    `article_en_2.txt`:
    ```
    CrewAI takes a different approach from LangGraph: it is role-based. Each agent has a defined role, goal, and toolset, and multiple agents are grouped into a Crew. This makes CrewAI quick to set up for collaborative agent systems where the structure matches a team metaphor.
    ```

    `article_en_3.txt`:
    ```
    AutoGen by Microsoft is a third multi-agent framework focusing on conversation-driven agent collaboration. Agents communicate via natural-language messages and can be configured with custom code execution capabilities. AutoGen targets research and prototyping more than production deployment.
    ```

    Step 5: Run a quick import check: `python -c "import sys; sys.path.insert(0, 'databricks-deploy'); from lightrag_databricks_provider import make_llm_func, make_embedding_func, EMBEDDING_DIM; print(EMBEDDING_DIM)"` — must print `1024` without raising.
  </action>
  <verify>
    <automated>python -c "import sys; sys.path.insert(0, 'databricks-deploy'); from lightrag_databricks_provider import make_llm_func, make_embedding_func, EMBEDDING_DIM, KB_LLM_MODEL, KB_EMBEDDING_MODEL; assert EMBEDDING_DIM == 1024; assert KB_LLM_MODEL == 'databricks-claude-sonnet-4-6'; assert KB_EMBEDDING_MODEL == 'databricks-qwen3-embedding-0-6b'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - File `databricks-deploy/lightrag_databricks_provider.py` exists, importable
    - Exports `make_llm_func`, `make_embedding_func`, `KB_LLM_MODEL`, `KB_EMBEDDING_MODEL`, `EMBEDDING_DIM`
    - `EMBEDDING_DIM == 1024` (literal int, not env-overridable — locked per REQ rev 3)
    - `KB_LLM_MODEL` default == "databricks-claude-sonnet-4-6"
    - `KB_EMBEDDING_MODEL` default == "databricks-qwen3-embedding-0-6b"
    - File contains literal substring `loop.run_in_executor` (Pitfall 4 mitigation)
    - File contains literal substring `@wrap_embedding_func_with_attrs(` (Pitfall 5 correct usage)
    - File contains literal substring `embedding_dim=EMBEDDING_DIM` OR `embedding_dim=1024`
    - 5 fixture files exist at `databricks-deploy/tests/fixtures/article_{zh_1,zh_2,en_1,en_2,en_3}.txt`
    - Each fixture is non-empty (`test -s ...` succeeds)
    - WorkspaceClient is NOT imported at module top (lazy import only): `head -25 databricks-deploy/lightrag_databricks_provider.py | grep -c "from databricks.sdk"` returns 0
    - `databricks-deploy/requirements.txt` contains `pytest-asyncio>=0.23.0` (either from plan 01 or appended here)
  </acceptance_criteria>
  <done>Factory file + 5 fixtures shipped; pytest-asyncio installed; module imports cleanly without WorkspaceClient instantiation at import time.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.3: Write dry-run e2e test_provider_dryrun.py + run against REAL Model Serving</name>
  <read_first>
    - .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md (Q5 dry-run e2e test structure lines 282-313, Time-box line 314, Risks 1-3 lines 397-424)
    - .planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-PREFLIGHT-FINDINGS.md (sub-tests 1.2 + 1.3 — proves auth path works)
    - venv/Lib/site-packages/lightrag/__init__.py (top of file — verify LightRAG, QueryParam imports)
    - venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py (vdb_*.json on-disk shape — for Test 3 assertion key naming)
  </read_first>
  <behavior>
    Test 1 — `test_llm_factory_smoke` (~5s, ~$0.01):
      - llm = make_llm_func()
      - response = await llm("Reply with exactly the word: pong", system_prompt="You are a test bot.")
      - assert isinstance(response, str)
      - assert len(response) > 0
      - assert latency < 10s (use time.time() bracket)

    Test 2 — `test_embedding_factory_smoke` (~3s, ~$0.001):
      - emb = make_embedding_func()
      - vec = await emb(["hello world"])
      - assert vec.shape == (1, 1024)
      - assert vec.dtype == np.float32
      - assert emb.embedding_dim == 1024
      - assert emb.max_token_size == 8192

    Test 3 — `test_lightrag_e2e_roundtrip` (~5 min, ~$0.20–$0.80):
      - tmp_dir = tempfile.mkdtemp(prefix="lightrag_storage_dryrun_")
      - rag = LightRAG(working_dir=tmp_dir, llm_model_func=make_llm_func(), embedding_func=make_embedding_func())
      - await rag.initialize_storages()
      - For each fixture article: await rag.ainsert(article_text)
      - response = await rag.aquery("What multi-agent frameworks are mentioned?", QueryParam(mode="hybrid"))
      - assert isinstance(response, str) and len(response) > 50
      - assert os.path.exists(tmp_dir / "graph_chunk_entity_relation.graphml")
      - assert any vdb_*.json file exists in tmp_dir
      - **Key-name-agnostic dim check** (per NIT 6 / RESEARCH.md vdb shape uncertainty): load any vdb_*.json successfully, walk its structure, find at least one float-list entry, assert its length == 1024. This avoids hard-coding a specific JSON key name (`embedding_dim` vs `dim` vs nested under `data[i].embedding`) which varies between nano-vectordb on-disk schema versions.
      - Cleanup: shutil.rmtree(tmp_dir)

    Test 4 — `test_dryrun_bilingual` (~3 min, ~$0.10–$0.30):
      - Reuse a fresh LightRAG instance with all 5 fixture articles ingested
      - response_zh = await rag.aquery("LangGraph 与 CrewAI 的对比", QueryParam(mode="hybrid"))
      - response_en = await rag.aquery("compare LangGraph and CrewAI frameworks", QueryParam(mode="hybrid"))
      - assert both non-empty (>50 chars)
      - Print response_zh and response_en to stdout for human review (logged for post-test inspection — Risk #3 early warning)
  </behavior>
  <action>
    Step 1: Write `databricks-deploy/tests/test_provider_dryrun.py`. Concrete shape:

    ```python
    """Dry-run e2e test for the LightRAG-Databricks provider factory.

    Runs against REAL Model Serving endpoints (not mocked). Auth via user OAuth
    from ~/.databrickscfg [dev] profile. Cost: ~$0.20–$0.80 per full run.
    Time: ~10 min wallclock.

    Skip in CI by default (use `pytest -m dryrun` to opt in). For local
    pre-deploy validation only.
    """
    from __future__ import annotations

    import asyncio
    import json
    import os
    import shutil
    import sys
    import tempfile
    import time
    from pathlib import Path

    import numpy as np
    import pytest

    # Make databricks-deploy importable in test context
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from lightrag_databricks_provider import (
        EMBEDDING_DIM,
        KB_EMBEDDING_MODEL,
        KB_LLM_MODEL,
        make_embedding_func,
        make_llm_func,
    )

    pytestmark = pytest.mark.dryrun

    FIXTURES_DIR = Path(__file__).parent / "fixtures"


    def _load_fixtures() -> list[str]:
        articles = []
        for name in sorted(FIXTURES_DIR.glob("article_*.txt")):
            articles.append(name.read_text(encoding="utf-8"))
        return articles


    def _find_vector_of_dim(obj, expected_dim: int) -> bool:
        """Walk a nested JSON-decoded object; return True iff at least one
        list of floats with length == expected_dim is found.

        Key-name-agnostic: avoids hard-coding `embedding_dim` vs `dim` vs
        nested `data[i].embedding` shape that varies across nano-vectordb
        on-disk schema versions.
        """
        if isinstance(obj, list):
            if obj and all(isinstance(x, (int, float)) for x in obj) and len(obj) == expected_dim:
                return True
            return any(_find_vector_of_dim(item, expected_dim) for item in obj)
        if isinstance(obj, dict):
            return any(_find_vector_of_dim(v, expected_dim) for v in obj.values())
        return False


    @pytest.mark.asyncio
    async def test_llm_factory_smoke():
        llm = make_llm_func()
        t0 = time.time()
        response = await llm(
            "Reply with exactly the word: pong",
            system_prompt="You are a test bot.",
        )
        elapsed = time.time() - t0
        assert isinstance(response, str)
        assert len(response) > 0
        assert elapsed < 10.0, f"LLM call took {elapsed:.2f}s (expected <10s)"


    @pytest.mark.asyncio
    async def test_embedding_factory_smoke():
        emb = make_embedding_func()
        vec = await emb(["hello world"])
        assert vec.shape == (1, EMBEDDING_DIM)
        assert vec.dtype == np.float32
        assert emb.embedding_dim == EMBEDDING_DIM
        assert emb.max_token_size == 8192


    @pytest.mark.asyncio
    async def test_lightrag_e2e_roundtrip(tmp_path):
        from lightrag import LightRAG, QueryParam

        tmp_dir = tmp_path / f"lightrag_storage_dryrun_{int(time.time())}"
        tmp_dir.mkdir()
        try:
            rag = LightRAG(
                working_dir=str(tmp_dir),
                llm_model_func=make_llm_func(),
                embedding_func=make_embedding_func(),
            )
            await rag.initialize_storages()

            for art in _load_fixtures():
                await rag.ainsert(art)

            response = await rag.aquery(
                "What multi-agent frameworks are mentioned?",
                QueryParam(mode="hybrid"),
            )
            assert isinstance(response, str)
            assert len(response) > 50, f"Got short response: {response!r}"

            graphml = tmp_dir / "graph_chunk_entity_relation.graphml"
            assert graphml.exists(), f"Expected {graphml} to exist"

            vdb_files = list(tmp_dir.glob("vdb_*.json"))
            assert vdb_files, "No vdb_*.json files emitted"

            # Key-name-agnostic dim verification: walk the JSON and find at least
            # one float-list of length EMBEDDING_DIM. Avoids hard-coding the JSON
            # key name (embedding_dim / dim / nested data[i].embedding) which
            # varies across nano-vectordb schema versions.
            with open(vdb_files[0]) as f:
                vdb_data = json.load(f)
            assert _find_vector_of_dim(vdb_data, EMBEDDING_DIM), (
                f"vdb {vdb_files[0].name} contains no length-{EMBEDDING_DIM} "
                f"float vector — embedding dim contract not verified end-to-end"
            )
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)


    @pytest.mark.asyncio
    async def test_dryrun_bilingual(tmp_path, capsys):
        """Risk #3 early warning: surface Qwen3-0.6B Chinese retrieval quality."""
        from lightrag import LightRAG, QueryParam

        tmp_dir = tmp_path / f"lightrag_bilingual_{int(time.time())}"
        tmp_dir.mkdir()
        try:
            rag = LightRAG(
                working_dir=str(tmp_dir),
                llm_model_func=make_llm_func(),
                embedding_func=make_embedding_func(),
            )
            await rag.initialize_storages()
            for art in _load_fixtures():
                await rag.ainsert(art)

            resp_zh = await rag.aquery(
                "LangGraph 与 CrewAI 的对比",
                QueryParam(mode="hybrid"),
            )
            resp_en = await rag.aquery(
                "compare LangGraph and CrewAI frameworks",
                QueryParam(mode="hybrid"),
            )
            assert len(resp_zh) > 50, f"Chinese query returned short response: {resp_zh!r}"
            assert len(resp_en) > 50, f"English query returned short response: {resp_en!r}"
            print("\n--- BILINGUAL DRY-RUN ---")
            print("ZH query response:", resp_zh[:400])
            print("EN query response:", resp_en[:400])
            print("--- END ---")
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
    ```

    Step 2: Create `databricks-deploy/pytest.ini` registering the `dryrun` marker + asyncio_mode:

    ```ini
    [pytest]
    asyncio_mode = auto
    markers =
        dryrun: requires real Databricks Model Serving access (~$0.20-$0.80 per run)
    ```

    Step 3: Run the dry-run against REAL Model Serving endpoints:

    ```bash
    pytest databricks-deploy/tests/test_provider_dryrun.py -v -m dryrun --tb=short -s
    ```

    All 4 tests must PASS.

    **Fallback handling — TIME-BOXED 30 MIN MAX:** if test 2 fails because the SDK rejects the `input=...` kwarg for the embedding endpoint, fall back to OpenAI-compat shape (Decision 3 escape hatch in RESEARCH.md): swap the `_embed()` body to use `lightrag.llm.openai.openai_embed(texts, model=KB_EMBEDDING_MODEL, base_url=f"{w.config.host}/serving-endpoints", api_key=w.config.token)`. Document the fallback decision in the SUMMARY.md.

    **If the fallback path is also not working after 30 minutes** (e.g., auth header shape diverges, base_url path wrong, openai_embed signature mismatch): STOP and escalate — do NOT keep iterating. Capture the exact error in `.scratch/kdb-1.5-02-fallback-blocked-<ts>.log`, update SUMMARY.md with status=BLOCKED, and surface to user with the 2-3 most likely root causes. The 30-min budget assumes the fallback is a 5-line swap; longer iteration indicates a deeper REQ-vs-SDK contract mismatch that needs design-level resolution, not more code attempts.

    Step 4: Capture key output for SUMMARY.md:
      - Test latencies (test 1 LLM smoke time, test 2 embedding smoke time)
      - Test 3 wallclock + bytes emitted under tmp_dir
      - Test 4 zh + en response excerpts (first 400 chars each) — qualitative read for Risk #3
      - Total cost estimate (sum of token counts × MosaicAI pricing if surfaced; otherwise note "trivial, <$1")
  </action>
  <verify>
    <automated>pytest databricks-deploy/tests/test_provider_dryrun.py -v -m dryrun --tb=short -s</automated>
  </verify>
  <acceptance_criteria>
    - File `databricks-deploy/tests/test_provider_dryrun.py` exists
    - Contains 4 test functions: `test_llm_factory_smoke`, `test_embedding_factory_smoke`, `test_lightrag_e2e_roundtrip`, `test_dryrun_bilingual`
    - All 4 tests PASS when run with `-m dryrun` against REAL Model Serving
    - Test 3 produces graphml + vdb_*.json under a tmp working_dir; vdb_*.json contains at least one length-1024 float vector (key-name-agnostic check via `_find_vector_of_dim` helper)
    - Test 4 surfaces zh + en query response excerpts to stdout via `print(...)` + `-s` flag (Risk #3 evidence captured)
    - `databricks-deploy/pytest.ini` exists with `dryrun` marker registered
    - tmp_dir cleanup succeeds: after test run, `ls /tmp/ | grep lightrag_storage_dryrun` returns nothing (or only artifacts from currently-running tests)
  </acceptance_criteria>
  <done>4-test dry-run e2e green against REAL MosaicAI endpoints; embedding_dim=1024 contract verified end-to-end via key-name-agnostic walk; bilingual qualitative output captured for SUMMARY.md.</done>
</task>

</tasks>

<verification>
Phase-level verification anchors (this plan's contribution):

1. `databricks-deploy/lightrag_databricks_provider.py` exists with `make_llm_func` + `make_embedding_func` + EMBEDDING_DIM=1024 exports
2. `databricks-deploy/tests/test_provider_dryrun.py` 4 tests PASS against REAL Model Serving
3. `databricks-deploy/tests/fixtures/` contains 5 short fixture articles
4. Embedding contract end-to-end: at least one `vdb_*.json` file emitted by LightRAG contains a length-1024 float vector (verified via key-name-agnostic walk)
5. Risk #3 (Qwen3 bilingual) qualitative evidence captured in stdout (zh + en query excerpts)
6. CONFIG-DBX-01 verification: `git log cfe47b4..HEAD --name-only -- kb/ lib/` returns empty for this plan's commits
7. Skill discipline: `Skill(skill="databricks-patterns")` AND `Skill(skill="search-first")` literal substrings in SUMMARY.md (matches trimmed `skills_required: [databricks-patterns, search-first]` in frontmatter)
8. No regressions in existing project test suite — this plan only adds NEW files under `databricks-deploy/`
</verification>

<success_criteria>
- All 4 dry-run tests pass: `pytest databricks-deploy/tests/test_provider_dryrun.py -v -m dryrun` → `4 passed`
- Plan 01 unit tests still pass (Wave 1 should already be merged before this Wave 2 plan starts): `pytest databricks-deploy/tests/test_startup_adapter.py -v` → `5 passed`
- Combined test count: 9 tests green across both plans
- Skill discipline: 2 literal Skill invocations in SUMMARY.md (`databricks-patterns` + `search-first`) — matches trimmed frontmatter
- No `databricks.sdk` import at module-top of provider file (lazy import only)
- Cost spent on dry-run: < $2 (extrapolated from PREFLIGHT measured latencies)
- Total elapsed: < 2.5h (Skill invocation 15min + factory write 30min + fixtures 10min + test write 30min + dry-run execution 10min + SUMMARY 30min + slack)
- Forward-only commit (no `--amend`, no `--reset`, no `git add -A`)
</success_criteria>

<output>
After completion, create `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-02-SUMMARY.md` containing:
- What shipped (factory file + 4 dry-run tests + 5 fixtures + pytest.ini + requirements.txt addition)
- Test counts (4/4 dry-run green; combined 9/9 across plans 01+02)
- Skill invocations made: literal `Skill(skill="databricks-patterns")` + `Skill(skill="search-first")` substrings (matches trimmed `skills_required: [databricks-patterns, search-first]` in frontmatter — `python-patterns` + `writing-tests` invoked in plan 01 SUMMARY only)
- Dry-run measurements: LLM latency, embedding latency, e2e wallclock, total cost estimate
- Bilingual qualitative read: zh + en query response excerpts (first ~400 chars each); subjective verdict on Qwen3 retrieval quality (PASS / NEEDS-INVESTIGATION / FAIL → escalate before kdb-2.5)
- SDK kwarg verification: confirm `input=...` works for embedding endpoint, OR document fallback to OpenAI-compat shape (or BLOCKED status if 30-min fallback budget hit)
- Phase kdb-1.5 verification status: STORAGE-DBX-05 (alt path) ✅ via plan 01; LLM-DBX-03 ✅ via plan 02 → kdb-1.5 phase complete (with ROADMAP success criterion #4 `app.yaml` wiring deferred to kdb-2 DEPLOY-DBX-04, recorded in plan 01's VERIFICATION.md)
- 2-forward-commit STATE.md backfill: list both commit hashes from plan 01 + plan 02; suggest exec write a follow-up commit updating STATE.md "Last activity" line with these hashes (forward-only, NO --amend)
</output>
</output>
