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

## Self-Check: PASS

Branch A FULL: one successful real-synthesis Deep Research UI run on live Aliyun (5-stage
stepper + 4630-char cited report + 14 sources + 6 images). #44 NOT a blocker (WEIGHT fallback).
Deploy = deliberate op, zero Aliyun git ops, user-approved.
