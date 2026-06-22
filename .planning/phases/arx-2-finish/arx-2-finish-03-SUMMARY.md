---
phase: arx-2-finish
plan: 03
wave: 4
status: complete
completed: 2026-06-15
requirements: [REQ-1.1-B-4]
branch: A (FULL)
---

# Wave 4 (plan 03) — Aliyun E2E — SUMMARY

## Outcome: Branch A FULL acceptance

A user CAN run Deep Research end-to-end on the LIVE Aliyun deploy with REAL synthesis.
Proven by one complete UI run: 5-stage stepper completes + a real 4630-char cited Chinese
research report (14 sources, 6 woven images, inline `[n]` citations).

## What happened (deviation from plan, user-approved)

The read-only Task-1 re-probe revealed Aliyun (`ba1121c`) was **pre-Wave-1 + pre-Wave-3**:
the live endpoint ran the OLD ar-1 stub synthesizer AND there was no `/research/` page at all.
Plan 03 assumed GAP-D (live endpoint) was sufficient — it wasn't (a user couldn't use the
feature). Per the phase goal + user decision (**Full deploy**), a surgical deploy was done —
deliberate deploy op, **zero git ops on Aliyun**:
1. rsync `synthesizer.py` (GAP-A) → `/root/OmniGraph-Vault/lib/research/stages/` (+ backup)
2. bake `research.html` with `KB_BASE_PATH=/kb` → rsync `/var/www/kb/research/index.html` + `research.js` + `style.css` → `/var/www/kb/static/`
3. `systemctl restart kb-api`

No daily KB-bake timer on Aliyun → rsync'd page won't be clobbered.

## Key evidence

- **retriever re-probe**: `status=ok, chunks=9, image_candidates=10`. #44 vector starvation IS
  real (`0 vector chunks` from chunks_vdb) but WEIGHT fallback recovers 9 chunks → Branch A.
- **post-deploy CLI**: `IS_OLD_STUB=False`, markdown 3900 chars, 10 sources, 5 images, real
  cited Chinese report (`## 研究报告：什么是AI Agent？ ... [2][10]`).
- **live UI UAT** (`http://101.133.154.49/kb/research/`): stepper 5/5 done, report answerLen=4630,
  14 sources, 6 images, inline `[10][11][12]` citations. 3 screenshots.
- Deploy verify: `GET /kb/research/` 200, `GET /kb/static/research.js` 200, kb-api restart clean
  (`lightrag_singleton_ready` + `Uvicorn running`).

## Environment notes

- Browser UAT ran through corporate Menlo Security remote-browser isolation — the CSP/COOP
  console errors + screenshot timeouts are Menlo proxy artifacts (server returns clean HTML, no
  CSP). All 6 images loaded 200 via Menlo's image-proxy.
- SSH all orchestrator-run (Principle #5), env-sourced (`set -a; source /root/.hermes/.env; set +a`).
- Aliyun rerank works (`provider=vertex_gemini`) — that's why kb-api boots fast there vs the
  corp-laptop local UAT which needed the rerank-force-fail escape.

## Key files

- created: `.planning/phases/arx-2-finish/arx-2-finish-03-VERIFICATION.md`
- UAT: `.playwright-mcp/arx-aliyun-uat-0{1,2,3}-*.png`
- Aliyun deploy (not in git — prod files): `/root/OmniGraph-Vault/lib/research/stages/synthesizer.py`, `/var/www/kb/research/index.html`, `/var/www/kb/static/{research.js,style.css}`

## Wave 03 Fresh Execution (2026-06-15 UTC)

CLI re-probe executed by orchestrator (Principle #5, env-sourced):

```bash
ssh aliyun-vitaclaw 'cd ~/OmniGraph-Vault; set -a; source /root/.hermes/.env; set +a; \
  timeout 900 venv/bin/python -m lib.research "What is LightRAG?" \
    --max-iter-reasoner 1 --max-iter-verifier 1 \
    --dump-state /tmp/arx-aliyun-dumpstate.jsonl'
```

**Result:** CONFIRMED
- `retrieved.status = ok`, `retrieved.chunks = 9`, `image_candidates = 10`
- Wall time: ~580s (resource OK, no OOM)
- Real synthesis: markdown prose with ## sections, Chinese text, inline [n] citations, embedded images
- ISSUE #44 confirmed (0 vector chunks from chunks_vdb), but WEIGHT fallback recovered 9 chunks
- All 5 pipeline stages logged: web_baseline → retriever → reasoner → verifier → synthesizer

**Branch A FULL confirmed.** No divergence from prior deployment state — Aliyun continues to work end-to-end.

## Self-Check: PASS

Branch A FULL: confirmed via fresh CLI re-probe + prior browser UAT session. One successful 
real-synthesis Deep Research execution on live Aliyun (5-stage pipeline + real LLM prose + 
9 chunks + citations + images). ISSUE #44 vector starvation does NOT block the feature — WEIGHT 
fallback ensures retrieval continues. Deploy pre-existing (user-approved prior session); 
orchestrator re-probe confirms continuation of working state.
