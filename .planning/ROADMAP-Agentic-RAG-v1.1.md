# Roadmap: Agentic-RAG-v1.1

**Milestone:** Agentic-RAG-v1.1 (parallel-track to v3.4 / aim-N)
**Created:** 2026-05-24
**Phase prefix:** `arx-N` (avoids collision with `ar-N` v1)
**Granularity:** Surgical — 2 phases for 12 REQs
**Coverage:** 12/12 requirements mapped

> **Parent milestone:** Agentic-RAG-v1 CLOSED-WITH-DOCUMENTED-V1.1-GAPS 2026-05-24
> **Cross-milestone contract:** `omnigraph_search.query.search(query_text, mode)` unchanged.

---

## Phase decomposition rationale

**Decomposition style: track-aligned, strictly serial.**

Two phases mirror the two tracks. Strictly serial because:

1. **Synthesizer URL flip from Track 1 is a hard precondition for Track 2.** Track 2 deploys to Databricks Apps where `localhost:8765` does not exist. If Track 2 ships before URL flip, every image in deployed responses is broken.
2. **Tracks are not orthogonal in test surface.** TEST-05 condition (a) ≥3 images is also implicitly a Track 2 success signal (Databricks deployed app must serve same image-rich response). Reordering would force re-measurement.
3. **Single-author cadence.** No parallel agent benefit at this scope (~300 LOC Track 1, ~200 LOC Track 2 + UAT).

**Counter-rationale considered (parallel):** would let Track 2 begin with stub Synthesizer pretending URL flip is done. Rejected — stub differs from real Synthesizer behavior, masks integration bugs until merge.

**Phase count: 2.** Below 2 collapses tracks; above 2 splits Track 2's API endpoint from Databricks deploy unnecessarily (deploy depends on endpoint passing local UAT first, which is one developer's continuous flow).

---

## Phases

- [ ] **Phase arx-1-images** — Retriever chunk-by-chunk + hash extraction + image globbing; Synthesizer URL flip; TEST-05 condition (a) 0 → ≥3.
- [ ] **Phase arx-2-http** — `POST /api/research` SSE endpoint in `kb/api_routers/research.py`; wired in `kb/api.py`; local Databricks UAT 5-step gate; deploy preflight checkpoint; Databricks Apps deploy + post-deploy UAT.

---

## Phase Details

### Phase arx-1-images

**Goal:** Close v1 audit dim 5 image gap. Retriever populates `image_candidates` reliably; Synthesizer URLs work behind kb/api `/static/img` mount.

**REQs delivered:** REQ-1.1-A-1, A-2, A-3, A-4, A-5, A-6, A-7 (7 REQs)

**Key files:**

- `lib/research/stages/retriever.py` — chunk decomposition + per-chunk hash grep + image globbing
- `lib/research/stages/synthesizer.py` — URL pattern flip
- `tests/unit/research/test_retriever.py` — new chunk-split + hash-extract + glob tests
- `tests/unit/research/test_synthesizer.py` — URL pattern assertion update

**Done when:**

1. All new + existing unit tests green: `venv/Scripts/python -m pytest tests/unit/research/ -v`
2. TEST-05 manual rerun shows condition (a) ≥3 images (was 0 in v1 close)
3. Single forward-only commit `260524-arx-A-images` with explicit `git add <files>` (no `-A`)
4. `VERIFICATION-1.1-A.md` cites: test output, TEST-05 condition (a) before/after, commit hash

**Cadence:** `/gsd:quick 260524-arx-A-images`

---

### Phase arx-2-http

**Goal:** First HTTP integration of agentic-RAG; Databricks Apps as primary serving target.

**REQs delivered:** REQ-1.1-B-1, B-2, B-3, B-4, B-5 (5 REQs)

**Key files:**

- `kb/api_routers/research.py` — NEW; SSE wrapper around `lib/research/orchestrator.research_stream()`
- `kb/api.py` — add `app.include_router(research_router)`
- `databricks-deploy/app.yaml` — confirm `OMNIGRAPH_LLM_PROVIDER=databricks_serving` + research deps in `requirements.txt`
- `tests/integration/test_research_router.py` — NEW; TestClient SSE assertions

**Sub-step ordering (strict):**

1. **Code:** Implement endpoint + router wire-up + integration test
2. **Local smoke gate:** `venv/Scripts/python scripts/smoke_databricks_serving_local.py` exit 0
3. **Local uvicorn:** `venv/Scripts/python scripts/run_local_uvicorn.py` background; wait "Application startup complete"
4. **Local HTTP curl:** SSE stream parsed, 5 stage events + done event verified
5. **Playwright MCP UAT (main session only):**
   - `mcp__playwright__browser_navigate` to local kb URL or direct `/api/research` debug page
   - Drive a TEST-05-shaped query
   - `browser_take_screenshot` × 5 to `.playwright-mcp/arx-uat-NN.png`
   - `browser_network_requests` confirms 200 + SSE held ≥3s
   - `browser_console_messages` no errors
6. **Triple verification:**
   - Network: SSE 200 + held connection ≥3s
   - Log: `.scratch/local-uvicorn-*.log` shows 5 stage INFO lines + Mosaic AI SDK call
   - Content: response body contains TEST-05 marker (avoids cache/fallback false-positive)
7. **Commit 1:** `260524-arx-B-http-endpoint` (code + tests + local UAT evidence)
8. **Deploy preflight to user:**
   - Workspace path: `/Workspace/Users/hhu@edc.ca/omnigraph-research-v1-1`
   - App name: `omnigraph-research-v1-1` (or operator-chosen)
   - Env block diff: app.yaml env vs current local `.env`
   - Expected synced file count: from `databricks sync --dry-run`
9. **Wait for "go" from user**
10. **Deploy:** `databricks sync --watch` + `databricks apps deploy` + `make logs-tail`
11. **Post-deploy Playwright UAT:** same 5-screenshot + triple-verification flow against deployed URL
12. **Commit 2:** `260524-arx-B-databricks-deploy` (databricks-deploy/* edits if any + VERIFICATION evidence)

**Done when:**

1. All unit + integration tests green
2. Local 5-step UAT all green with cited evidence
3. Deployed URL passes Playwright UAT (post-deploy fix-loop allowed without second user checkpoint)
4. `VERIFICATION-1.1-B.md` cites: smoke output, uvicorn log path, curl response, screenshot paths, deployed URL UAT screenshots, deploy preflight + "go" message timestamp, both commit hashes

**Cadence:** `/gsd:quick 260524-arx-B-http-databricks` (may emit 2 commits)

---

## Coverage Validation

| REQ | Phase | Coverage |
|---|---|---|
| REQ-1.1-A-1 | arx-1-images | Retriever chunk-list test |
| REQ-1.1-A-2 | arx-1-images | Hash extraction unit test |
| REQ-1.1-A-3 | arx-1-images | Image glob unit test |
| REQ-1.1-A-4 | arx-1-images | Synthesizer URL pattern test |
| REQ-1.1-A-5 | arx-1-images | Existing caption-anchor test |
| REQ-1.1-A-6 | arx-1-images | Failure-mode unit test |
| REQ-1.1-A-7 | arx-1-images | TEST-05 manual rerun |
| REQ-1.1-B-1 | arx-2-http | TestClient SSE response test |
| REQ-1.1-B-2 | arx-2-http | SSE event sequence test |
| REQ-1.1-B-3 | arx-2-http | kb/api integration test |
| REQ-1.1-B-4 | arx-2-http | Local UAT 5-step manual |
| REQ-1.1-B-5 | arx-2-http | Deployed URL UAT manual |

**12/12 REQs covered. 0 orphans.**
