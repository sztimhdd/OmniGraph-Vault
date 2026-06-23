---
phase: arx-2-finish
plan: 04
wave: 5
status: passed
requirement: REQ-1.1-B-5
verified: 2026-06-23
method: human-performed UAT (deployed env requires Entra ID SSO — blocks Playwright/automation)
deployment_id: 01f16f2a4ae112109eb1a48c52bfcd34
---

# arx-2-finish Wave 5 (Databricks E2E) — VERIFICATION

## Result: ✅ PASS — Databricks full-functionality (Branch A) PROVEN at iterations=1

REQ-1.1-B-5 (deployed-URL Deep Research returns a real cited report) is **met** on the
live Databricks App. This is the "Databricks full" half of the arx-2 split-reality decision.

## UAT evidence (human-performed, 2026-06-23)

Deployed env requires Microsoft Entra ID SSO, which blocks Playwright/automation (CLAUDE.md
Principle #6 — UAT performed manually by the user against the live deployed URL
`https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/research/`).

**Query:** "what is a harness for agent" · **iterations = 1**

**Frontend (UAT#3):**
- All 5 stages ran green in order: `web_baseline → retriever → reasoner → verifier → synthesizer → done`.
- Real ~9000-word LLM-synthesized report (NOT the old stub, NOT chunks[0] verbatim).
- Inline `[1]`–`[11]` citations threaded into the prose.
- **sources = 11** (omnigraph_search KG hits).
- Embedded images rendered (`/static/img/<hash>/0-12.jpg`).
- Bilingual chrome (zh-CN / en) rendered.

**Backend confirmation (deployed app log):**
- `POST /api/research HTTP/1.1 200 OK` — full 5-stage pipeline ran server-side.
- KG hydrated: `graphml 30833 nodes / 44371 edges`, all vdb at `embedding_dim 3072`
  (entities 30832, chunks 2025) — healthy UC-Volume snapshot.
- 12 images served (one 404, see KL-4); `llm_rerank_init_ok provider=databricks_serving`.

## REQ coverage

| REQ | Status | Evidence |
|-----|--------|----------|
| REQ-1.1-B-1 (POST /api/research → SSE) | ✅ | `POST /api/research 200`, text/event-stream |
| REQ-1.1-B-2 (5 stage events + done) | ✅ | web_baseline→retriever→reasoner→verifier→synthesizer→done |
| REQ-1.1-B-3 (kb/api integration) | ✅ | deployed app serves via `from kb.api import app` |
| REQ-1.1-B-4 (UI + local UAT) | ✅ | Wave 3 local UAT (02-SUMMARY) + Aliyun Branch A (03) |
| REQ-1.1-B-5 (deployed-URL real cited report) | ✅ | this UAT — 11 sources, real prose, deployed Databricks |

## Bugs fixed en route to this pass (all committed + deployed)

1. `query.py` stale GEMINI_API_KEY guard (blocked retriever+reasoner on Vertex-SA env) — `f02440e`
2. `verifier.py` `await` on sync web_search stub (`object list can't be used in 'await'`) — `f02440e`
3. `deploy.sh` never staged `omnigraph_search/` (stale workspace copy) — `2a67a73`
4. SSE heartbeat (`: keepalive` 15s) for HTTP/2 idle-reset — `b7f0645`
5. Reasoner+verifier iteration cap + default 1 + anti-buffering headers (300s-cap) — `f746a7c`
6. Tavily secret: scope + SP READ + app.yaml valueFrom + app-level resource registration; key
   re-stored cleanly (stdin store had mangled it → 401) — `8d98f61` + `apps update`

---

## ⚠️ KNOWN LIMITATIONS (documented, NON-blocking — none prevent a real cited report)

### KL-1 (P2) — iterations=1 only on Databricks (300s HTTP-cap)
Databricks Apps HTTP/2 gateway enforces a **hard ~300s total-duration cap**. At iterations≥2
the reasoner agent-loop (cross-border LLM calls) exceeds 300s → stream killed mid-reasoner
(`ERR_HTTP2_PROTOCOL_ERROR`, reproduced twice at iterations=3 on 2026-06-23). The SSE heartbeat
(commit `b7f0645`) correctly prevents IDLE-timeout death but **cannot defeat the total-DURATION
cap** — different gateway limits. **Deep multi-round research (iterations 2–10) on Databricks
requires an async-job + polling architecture** (like `/ask/` Quick-answer), NOT long-lived SSE.
Mitigation shipped: UI iterations default is now **1** (backend `Field(1)` + html input value=1 +
both JS fallbacks=1, this commit). Follow-up: ISSUES **#63** (`arx-3-async-job-architecture-for-deep-iterations`).

### KL-2 (P2) — Databricks retrieval runs on WEIGHT fallback, not vector similarity
Every query logs `WARNING: No entity-related chunks selected by vector similarity, falling
back to WEIGHT method` + `Raw search results: 0 vector chunks`. Same #44-class graphml↔vdb-chunk
misalignment, surviving in the Databricks UC-Volume snapshot. Retrieval still returns 11–12
chunks via WEIGHT fallback (sources>0, report is good) but the vector path is starved.
Follow-up: ISSUES **#64** (`arx-vector-chunk-resync`) — UC-Volume lightrag_storage snapshot needs
a vector-chunk rebuild/re-sync.

### KL-3 (P2) — Rerank configured-but-inactive
`llm_rerank_init_ok provider=databricks_serving` at startup, BUT every query logs
`WARNING: Rerank is enabled but no rerank model is configured`. Init and query-time rerank-model
lookup disagree. Follow-up: ISSUES **#65** — verify whether rerank applies; if not, wire it or
set `enable_rerank=False` to drop the warning.

### KL-4 (P3) — One image 404
`GET /static/img/f31803442a/4.jpg 404` (other images 200). One article's image missing from the
UC-Volume image hydration (5747 files / 1.29GB hydrated). Cosmetic. Follow-up: ISSUES **#66**.

---

## Split-reality status (both halves now resolved)

- **Databricks: FULL** (Branch A) at iterations=1 — this VERIFICATION.
- **Aliyun: FULL** (Branch A) — 03-VERIFICATION (chunks=9, real prose, 2026-06-13). The earlier
  #44 sources=0 degrade **cleared 2026-06-23** (`260623-g6e`: long_form sources=13, real KG hit).
  Aliyun is no longer degraded.

## Self-Check: PASS
Deployed Databricks Deep Research delivers a real LLM-synthesized cited report (11 sources, [1]-[11]
inline citations, embedded images, bilingual) at iterations=1. Backend log confirms full 5-stage
200 + healthy 30833-node 3072-dim KG. 4 known-limitations documented + filed as P2/P3 follow-ups,
none blocking. REQ-1.1-B-5 met.
