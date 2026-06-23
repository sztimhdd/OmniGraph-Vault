# State: Agentic-RAG-v1.1

**Milestone:** Agentic-RAG-v1.1
**Created:** 2026-05-24
**Current status:** ✅ COMPLETE — arx-1-images CLOSED PASS, arx-2 (http + finish) CLOSED PASS 2026-06-23 (Databricks full @ iterations=1; Aliyun full; deep-iteration deferred to async-job follow-up #63)

---

## Phase Status

| Phase | Status | Commits | Notes |
|---|---|---|---|
| arx-1-images | ✅ CLOSED PASS (2026-05-25) | `39c8f43` | TEST-05 (a) 0 → 10 images on Hermes real-KG. See `.planning/quick/260524-arx-A-images/VERIFICATION-1.1-A.md` |
| arx-2-http | ✅ CLOSED PASS (2026-05-25) | `38a7286` | SSE endpoint + 5-stage orchestrator (transport layer). |
| arx-2-finish | ✅ CLOSED PASS (2026-06-23) | `f02440e` `2a67a73` `b7f0645` `f746a7c` `8d98f61` | Deep Research usable in KB UI on BOTH envs. Real LLM synthesis (GAP A), full frontend /research/ (GAP B), Aliyun E2E Branch A + Databricks E2E Branch A (deployed `01f16f2a`, 11 sources, [1]-[11] cites). **Databricks limited to iterations=1** (300s HTTP-cap; deep-iteration → async-job follow-up #63). See `.planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md`. |

---

## Cross-References

- **Parent milestone close:** Agentic-RAG-v1 — see `.planning/archive/closed-milestones/MILESTONE_Agentic-RAG-v1_AUDIT.md` (CLOSED-WITH-DOCUMENTED-V1.1-GAPS 2026-05-24T11:00:00Z)
- **Source of v1.1-A scope:** v1 audit dim 5 (image-rich answer gap; TEST-05 condition a 0 vs ≥3 target)
- **Source of v1.1-B scope:** v1 audit dim 5 + user direction 2026-05-24 ("HTTP API for KB web, Databricks first")
- **Explicitly dropped:** Inline citations (originally v1.1-B in audit, renumbered out per user "3去掉" 2026-05-24)
- **Deferred to v1.2:** v1.1-C (Native function-calling Option B), v1.1-D (per-tool-call telemetry), v1.1-E (LightRAG cache write-perms — operator-side)

---

## Decisions Locked This Milestone

1. **Track ordering:** Strictly serial Wave 1 → Wave 2. Synthesizer URL flip is hard precondition for Databricks deployment. (User confirmation 2026-05-24)
2. **First-deploy human-in-the-loop checkpoint:** First Databricks Apps deploy of v1.1 endpoint pauses for user "go" after local UAT passes. Subsequent redeploys autonomous per `claude_databricks_deployment_autonomous.md`. (User confirmation 2026-05-24)
3. **Image URL pattern:** Lib-wide flip `http://localhost:8765/...` → `/static/img/...`. Affects Synthesizer only; kb/api `/static/img` mount serves the same filesystem layout.
4. **Phase prefix:** `arx-N` (not `ar1.1-N`, not `arr-N`) — short, doesn't collide with v1 `ar-N`.
5. **Inline citations: dropped.** Not coming back in v1.1; revisit in v1.2 if user requests.

---

## Open Questions

None at scaffold time. All resolved in PROJECT-Agentic-RAG-v1.1.md and user 2026-05-24 拍板.

---

## Audit Trail

- 2026-05-24 — Scaffold landed (this file + PROJECT/REQUIREMENTS/ROADMAP-Agentic-RAG-v1.1.md). Awaiting Track 1 quick.
- 2026-05-25 — arx-1-images closed PASS. Option A fix (`only_context` additive param at sole CONTRACT-01 entry) unstarved retriever's hash-grep. Hermes real-KG: `STATUS: ok / CHUNKS: 9 / IMAGES: 10` (v1 baseline 0). Commit `39c8f43`. VERIFICATION at `.planning/quick/260524-arx-A-images/VERIFICATION-1.1-A.md`.
- 2026-06-23 — **arx-2-finish CLOSED PASS. Milestone Agentic-RAG-v1.1 COMPLETE.** Turned the shipped-but-unusable `/api/research` SSE endpoint into a real user-facing Deep Research feature on BOTH serving targets. GAP A (real LLM synthesis), GAP B (full /research/ frontend — 5-stage stepper, fetch+ReadableStream SSE, bilingual, SSG-registered), GAP D/E (E2E proof each env). **Aliyun**: Branch A full (chunks=9, real prose, 03-VERIFICATION 2026-06-13); the #44 sources=0 degrade cleared 2026-06-23 (`260623-g6e`, long_form sources=13) so Aliyun is no longer degraded. **Databricks**: Branch A full at iterations=1 — human UAT (Entra-SSO blocks Playwright) query "what is a harness for agent" → 5 stages green, 11 sources, [1]-[11] inline cites, embedded images, ~9000-word report; backend log `POST /api/research 200`, graphml 30833 nodes/44371 edges @ dim 3072. 6 bugs fixed en route (stale GEMINI guard, verifier await-list, deploy.sh omnigraph_search staging, SSE heartbeat, 300s-cap iteration caps, Tavily secret wiring). 4 known-limitations filed NON-blocking (#63 iterations=1/async-job, #64 vector-chunk-resync, #65 rerank-inactive, #66 img-404). Commits `f02440e` `2a67a73` `b7f0645` `f746a7c` `8d98f61`. VERIFICATION: `.planning/phases/arx-2-finish/arx-2-finish-04-VERIFICATION.md`.
