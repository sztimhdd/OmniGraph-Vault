---
status: passed
phase: arx-2-finish
plan: 03
wave: 4
requirement: REQ-1.1-B-4 (Aliyun-equivalent E2E)
branch: A (FULL — chunks > 0)
verified: 2026-06-15
---

# Wave 4 (plan 03) — Aliyun E2E VERIFICATION — Branch A (FULL)

## Acceptance branch chosen: **Branch A — FULL E2E acceptance**

Trigger value: `retrieved.status=ok`, **`retrieved.chunks=9`** (> 0). The #44 vector-chunk
starvation IS real on Aliyun (logs: `Raw search results: 25 entities, 69 relations, 0 vector
chunks` from `chunks_vdb`), BUT LightRAG's **WEIGHT fallback recovers** (`No entity-related
chunks selected by vector similarity, falling back to WEIGHT method` → `Selecting 33 from 33
entity-related chunks by weighted polling` → `Final context: 25 entities, 69 relations, 20
chunks`). So the research retriever path returns real chunks even though the parallel
`/api/synthesize long_form` path returns 0 (different code path). Branch A applies.

## Deviation from plan (recorded — user-approved)

Plan 03's interface said "GAP-D already live, read+UAT only, DO NOT re-pull/restart." The
read-only Task-1 re-probe revealed two things the plan did not anticipate: Aliyun HEAD
`ba1121c` is **pre-Wave-1 (GAP-A) and pre-Wave-3 (frontend)** — so (a) the live endpoint ran
the OLD ar-1 stub synthesizer, and (b) there was **no `/research/` page** in `/var/www/kb/`.
A user on Aliyun literally could not use Deep Research. Per the phase goal ("user CAN use Deep
Research on Aliyun") + user decision 2026-06-15 (**Full deploy**), a surgical deploy was
performed — a deliberate deploy op with **zero git ops on Aliyun** (rsync + restart only):

1. backed up + rsync'd `lib/research/stages/synthesizer.py` (GAP-A) → `/root/OmniGraph-Vault/...`
2. baked `research.html` with `KB_BASE_PATH=/kb` → rsync'd to `/var/www/kb/research/index.html`
   + `research.js` + `style.css` → `/var/www/kb/static/`
3. `systemctl restart kb-api` (picks up the new synthesizer)

No daily KB-bake timer exists on Aliyun (only ingest 20:00 + digest 20:30 CST), so the rsync'd
page will NOT be clobbered.

## Task 1 — retriever re-probe (read-only SSH, Principle #5)

Command (env sourced per memory `aliyun_ssh_manual_trigger_env`):
```
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault; set -a; source /root/.hermes/.env; set +a; \
  timeout 600 venv/bin/python -m lib.research "What is an AI agent?" \
    --max-iter-reasoner 1 --max-iter-verifier 1 --dump-state /tmp/arx-aliyun-dumpstate.json'
```
CST start: 2026-06-13 02:01:48 CST. Completed clean (no OOM — short loops avoided the 580s
wall the original probe hit). dump-state retrieved block:
- `retrieved.status = ok`, `retrieved.chunks = 9`, `retrieved.image_candidates = 10`

## Task 1b — post-deploy real-prose CLI proof (GAP-A synthesizer)

After deploying the GAP-A synthesizer + kb-api restart, re-ran the CLI (CST 2026-06-15 13:45):
- `retriever.chunks = 9`, `synth.sources = 10`, `embedded_images = 5`, `confidence = 0.5`, `note_lines = []`
- **`IS_OLD_STUB = False`**, `markdown_len = 3900` (vs old-stub 324)
- markdown head: `好的，以下是根据您提供的检索资料撰写的详细研究报告。\n\n## 研究报告：什么是AI Agent？\n\n### 一、核心定义...[2][10]...` — a real, structured, **cited** Chinese report (NOT chunks[0] verbatim).

## Task 2 — live browser UI UAT (Playwright MCP, main session)

Live Aliyun deploy: **`http://101.133.154.49/kb/research/`** (Caddy `:80`, `/kb/` strip-prefix).
Run executed THROUGH the corporate Menlo Security remote-browser isolation (the CSP/COOP console
errors + screenshot timeouts are Menlo proxy artifacts — the server returns clean HTML with NO CSP;
`curl -D -` from inside the box confirms `200 OK text/html`, no security headers).

**Deploy verification (curl, public path):**
- `GET /kb/research/` → **HTTP 200** (page deployed)
- `GET /kb/static/research.js` → **HTTP 200**
- page content markers: `research-stepper`, `深度研究`, `/kb/static/research.js` present
- kb-api restart log: `lightrag_singleton_ready wall_s=11.71` → `Application startup complete` → `Uvicorn running on http://127.0.0.1:8766`, `llm_rerank_init_ok provider=vertex_gemini`

**Live UI run (max_iterations=1, query "What is an AI agent?"):**
- Stepper streamed real stage transitions (observed mid-stream: `web_baseline=done, retriever=done,
  reasoner=running, verifier=pending, synthesizer=pending`).
- Final state: `data-research-state=done`; **all 5 steps `done`** (web_baseline/retriever/reasoner/
  verifier/synthesizer); error banner hidden.
- Rendered report: **answerLen=4630**, **14 source chips**, **6 images rendered** (woven
  `/static/img/072048ac90/*.jpg` + `ef5aa6387b/1.jpg` — all 200 via Menlo image-proxy). The report
  is a real 6-section Chinese research report (核心定义 / 核心架构：模型与Harness / 记忆系统 / 工作循环 /
  外部化 / 应用与发展) with inline `[10][11][12]` citations, bold terms, nested lists.
- Network: `GET /kb/research/ => 200` + all 6 `/static/img/*` => 200 (POST /api/research proxied via
  Menlo's xhr channel; the rendered 4630-char report is conclusive proof it returned the done event).

**Screenshots** (`.playwright-mcp/`):
- `arx-aliyun-uat-01-page-render.png` — idle page (nav 深度研究, hero, query + max_iterations + submit)
- `arx-aliyun-uat-02-stepper-streaming.png` — 5-stage stepper mid-stream
- `arx-aliyun-uat-03-final-report.png` — 5 steps lit green + rendered cited report (深度研究 visible)

## REQ coverage

| REQ | Status | Evidence |
|-----|--------|----------|
| REQ-1.1-B-4 (Aliyun-equiv E2E) | ✅ PASS (Branch A FULL) | Live UI run: stepper 5/5 done + real 4630-char cited report + 14 sources + 6 images on live Aliyun deploy |

## #44 note (out of scope, NOT a blocker)

ISSUE #44 (graphml↔Qdrant divergence → `0 vector chunks` from chunks_vdb) IS reproducing on
Aliyun, but does NOT block Deep Research: the WEIGHT-method fallback recovers 9 chunks → real
cited report. #44's graphml-rebuild (Path X/Y) remains out of this phase's scope. Aliyun
achieved FULL acceptance, not the degraded Branch B the plan hedged for.

## Wave 03 Fresh Re-probe (2026-06-15 UTC, orchestrator re-verification)

Command:
```
ssh aliyun-vitaclaw 'cd ~/OmniGraph-Vault; set -a; source /root/.hermes/.env; set +a; \
  timeout 900 venv/bin/python -m lib.research "What is LightRAG?" \
    --max-iter-reasoner 1 --max-iter-verifier 1 \
    --dump-state /tmp/arx-aliyun-dumpstate.jsonl 2>&1 | tail -40'
```

**Result:** CONFIRMED
- `retrieved.status = ok`
- `retrieved.chunks = 9` (Branch A condition met: chunks > 0)
- `image_candidates = 10`
- Wall time: ~580s (resource OK, within timeout 900)
- Real synthesis: markdown prose with structured ## sections, Chinese text, inline [n] citations, embedded images

**Logs show full pipeline:**
- `Raw search results: 20 entities, 64 relations, 0 vector chunks`
- `No entity-related chunks selected by vector similarity, falling back to WEIGHT method`
- `Selecting 20 from 20 entity-related chunks by weighted polling`
- `Final context: 20 entities, 64 relations, 19 chunks`
- Real LLM synthesis with images: `/static/img/10f661a3e3/2.jpg`, etc.

ISSUE #44 (vector starvation: 0 from chunks_vdb) confirmed, but fallback works — 9 chunks recovered via WEIGHT method.

## Self-Check: PASS

At least one successful Deep Research execution demonstrated on the LIVE Aliyun deploy (Branch A
FULL): real LLM prose + 9 chunks (via WEIGHT fallback despite #44 vector starvation) + inline
citations + 5-stage pipeline completing. All SSH run by the orchestrator (Principle #5), 
env-sourced per aliyun_ssh_manual_trigger_env memory. Deploy pre-existing (user-approved prior
session); re-probe confirms continuation of working state.
