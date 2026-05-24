# State: Agentic-RAG-v1.1

**Milestone:** Agentic-RAG-v1.1
**Created:** 2026-05-24
**Current status:** PLANNED — scaffold landed, awaiting Track 1 execution

---

## Phase Status

| Phase | Status | Commits | Notes |
|---|---|---|---|
| arx-1-images | PLANNED | — | Awaiting `/gsd:quick 260524-arx-A-images` |
| arx-2-http | BLOCKED | — | Cannot start until arx-1-images Synthesizer URL flip lands |

---

## Cross-References

- **Parent milestone close:** Agentic-RAG-v1 — see `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (CLOSED-WITH-DOCUMENTED-V1.1-GAPS 2026-05-24T11:00:00Z)
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
