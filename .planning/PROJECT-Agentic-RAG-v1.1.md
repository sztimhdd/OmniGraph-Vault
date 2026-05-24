# OmniGraph-Vault — Parallel Milestone: Agentic-RAG-v1.1

> Sibling milestone to Agentic-RAG-v1 (CLOSED-WITH-DOCUMENTED-V1.1-GAPS 2026-05-24).
> Closes two functional gaps from v1 audit dim 5 and adds first HTTP integration.
> Phase directories use the `arx-N-*` prefix to avoid collision with `ar-N` (v1).

## What This Milestone Is

Two surgical tracks closing the v1.0 → v1.1 gap:

1. **Track 1 (v1.1-A) — Images:** Retriever currently single-chunk-wraps the LightRAG synthesized response, so `ARTICLE_HASH_RE` rarely matches and `image_candidates` stays empty. TEST-05 condition (a) fails (0 images instead of ≥3). Fix: chunk-by-chunk decomposition with hash extraction per chunk, image globbing per match. Synthesizer URL pattern flips from `http://localhost:8765/...` to `/static/img/...` so kb/api `/static/img` mount serves directly.

2. **Track 2 (v1.1-B) — HTTP API + Databricks deployment:** Wrap `lib/research/orchestrator.research_stream()` in an SSE FastAPI endpoint at `POST /api/research`. First Databricks Apps deployment of the agentic-RAG pipeline — primary serving target. Local UAT via `scripts/smoke_databricks_serving_local.py` + `scripts/run_local_uvicorn.py` + Playwright MCP (main session only). Triple verification (Network + Log + Content) before deploy gate.

**Out of scope (deferred to v1.2 or operator-side):**
- v1.1-C (Native function-calling adapter, Option B) — Option A JSON-mode shim from v1 keeps working
- v1.1-D (Per-tool-call telemetry) — current stage-level telemetry sufficient
- v1.1-E (LightRAG cache write-perms) — operator-side, not lib work
- Inline citations in Synthesizer body — explicitly dropped per user direction 2026-05-24

## Goal

After v1.1:
- `omnigraph_research` skill returns markdown with ≥3 images on TEST-05 query (was 0)
- `kb/api` exposes `POST /api/research` SSE endpoint locally + on Databricks Apps
- Same skill / CLI / HTTP three-surfaces backed by single `lib/research/orchestrator.research()` — no fork

## Locked Architectural Choices (do NOT re-discuss)

Inherits from Agentic-RAG-v1 PROJECT.md unchanged:
- 5-stage pipeline + 7 frozen `@dataclass(frozen=True)` types in `lib/research/types.py` (LOCKED)
- Best-effort failure (Axis 3); Synthesizer terminal-stage no-status rule (Axis 8)
- Cap = budget (cap-hit returns ok); LLM provider env-only via `OMNIGRAPH_LLM_PROVIDER`
- Pattern A: `_run_pipeline` async generator shared by `research()` + `research_stream()`
- Three providers: DeepSeek (Aliyun), Mosaic AI (Databricks), Vertex Gemini

**New for v1.1:**
- Track 2 prioritizes Databricks Apps as primary HTTP serving target (not Aliyun, not Hermes)
- HTTP endpoint streaming format: `text/event-stream` with one event per stage + terminal `done` event
- Image URL pattern flips lib-wide: `http://localhost:8765/{parent}/{name}` → `/static/img/{parent}/{name}`

## Cross-Milestone Contract

Same single dependency on KG side:
```python
async def search(query_text: str, mode: str = "hybrid") -> str: ...
```

**New constraint Track 1 introduces:** Retriever needs raw chunk list, not only synthesized response. If LightRAG raw-chunk access is not exposed, Track 1 falls back to splitting synthesized text on paragraph boundaries + grepping hash refs across all paragraphs (degraded but still better than current single-wrap).

## Cadence

Hybrid:
- Plan scaffold (this 4-file set) — manual write
- Track 1 — single `/gsd:quick 260524-arx-A-images` invocation
- Track 2 — `/gsd:quick 260524-arx-B-http-databricks` (may split into 2 commits: API endpoint, then Databricks deploy)
- Milestone close — manual audit + STATE update + `MILESTONE_Agentic-RAG-v1.1_AUDIT.md`

Two Tracks **strictly serial**: Track 2 cannot start until Synthesizer URL flip from Track 1 lands; otherwise Databricks deploy serves images via dead localhost URLs.

## Deploy Gate (Track 2)

Local 5-step UAT (smoke → uvicorn → curl → Playwright MCP → triple verification) MUST pass before `databricks sync + apps deploy`.

**First-deploy human-in-the-loop checkpoint:** after local UAT passes, agent posts a deploy preflight (workspace path, app name, env block diff, expected synced file count) and waits for explicit "go" from user before triggering sync/deploy. This overrides the autonomous-deploy memory `claude_databricks_deployment_autonomous.md` for the FIRST deploy only — subsequent redeploys of the same app name run autonomously.

**Post-deploy UAT failure:** agent fix-redeploys autonomously, no second checkpoint.
