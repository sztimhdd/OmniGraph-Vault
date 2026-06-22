---
quick_id: 260520-sho
user_label: 260520-a0g
slug: aim-0-plan-robustness
description: aim-0 plan robustness — verification + fallbacks + env-inventory
mode: quick
created: 2026-05-20
completed: 2026-05-20
---

# Quick 260520-a0g — SUMMARY

Doc-only fix to 2 PLAN files in the aim-0 phase directory. 4 surgical edit blocks, no code change, no Skill invocation, no exploration outside the 2 files.

## What changed

| GAP | File | Change | Verified by |
|---|---|---|---|
| GAP-B + GAP-C | `aim-0-02-smoke-ingest-scratch-PLAN.md` | Replaced single `sqlite3 ... FROM ingestions` SELECT block (line 147-152 of pre-edit file) with `entity_buffer/*.json` existence check; rewrote "What to report back" to 5-item list anchored on `Exit code: 0`; updated Pass predicate + Verification table to match | `grep "FROM ingestions"` returns 0 matches |
| GAP-E | both PLANs | Added Hermes-SSH-unreachable fallback URL `https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA` (validated as `ingest_wechat.py:1647` default) | `grep "Y_uRMYBmdLWUPnz_ac7jWA"` returns 2 matches (one per PLAN) |
| GAP-F | both PLANs | Added `grep -oE '^[A-Z_][A-Z_0-9]*=' /etc/omnigraph/.env \| sort -u` pre-flight before env-export blocks (Step 3.5 in plan-01, before "Set environment" block in plan-02) | `grep "grep -oE"` returns 2 matches |
| GAP-G | `aim-0-01-spec-rtt-mem-dryrun-PLAN.md` | Replaced 2-tier Vision cascade comment ("Vision falls to Vertex if absent") with 3-tier (SiliconFlow → OpenRouter → Gemini Vision); added rationale line about Vertex 500 RPD ceiling | `grep "OpenRouter"` returns 1+ match |

## Why these 4 gaps mattered

- **GAP-B + GAP-C — `ingestions` SELECT was a false-FAIL trap**: `ingest_wechat.py` direct CLI never writes the `ingestions` table (7 INSERTs all in `batch_ingest_from_spider.py`, zero in `ingest_wechat.py`). The original SELECT would have returned 0 rows on a successful smoke ingest, leading the operator to (incorrectly) report READY-04 FAIL. Path `/tmp/aliyun-readiness/data/kol_scan.db` was also wrong (default DB lives under `repo/data/`).
- **GAP-E — Hermes-as-SPOF for candidate selection**: Step 1 of plan-02 (and the article-URL selection comment in plan-03 of plan-01) assumed Hermes SSH is always reachable. If Hermes is down at READY-04 time, the operator has no fallback. `ingest_wechat.py:1647` already encodes a verified-working KOL URL as its default — ideal known-good fallback.
- **GAP-F — `/etc/omnigraph/.env` key inventory**: The READY-03 / READY-04 operator prompts assume `GEMINI_API_KEY` / `GOOGLE_APPLICATION_CREDENTIALS` / `SILICONFLOW_API_KEY` are present in `/etc/omnigraph/.env`, but never verify. If a key is missing, failure surfaces ~10 min into the scratch venv install — wasted time. Pre-flight grep is cheap and surfaces the gap before commitment.
- **GAP-G — Vision cascade documentation drift**: Plan-01 Step 3 comment said "Vision falls to Vertex if absent" — but the actual cascade is 3-tier (SiliconFlow → OpenRouter → Gemini Vision), and aim-1 will need to make a SiliconFlow deployment decision based on accurate cascade understanding.

## Out of scope (per user mandate)

- GAP-A (Aliyun SSH reachability) — operator-side, unrelated to plan docs
- GAP-D (`config.py ENV_PATH` hardcoded) — deferred to aim-1
- Any code changes
- Any Skill calls

## Constraints honored

- Surgical only — only the 4 specified edit regions touched
- No `git add -A` / `git add .` / `git commit --amend` / `git reset` / `git push --force` (atomic forward-only commit)
- Read-first scope limited to the 2 PLAN files (no codebase exploration / git history)
- No fabricated test data — verification by grep counts only

## Verification commands run

```bash
grep -n "FROM ingestions" .planning/phases/aim-0-readiness-aliyun-ecs/aim-0-02-smoke-ingest-scratch-PLAN.md
# → 0 matches (expected: 0)

grep -n "Y_uRMYBmdLWUPnz_ac7jWA" .planning/phases/aim-0-readiness-aliyun-ecs/
# → 2 matches (expected: ≥ 2)

grep -n "grep -oE" .planning/phases/aim-0-readiness-aliyun-ecs/
# → 2 matches (expected: ≥ 2)

grep -n "OpenRouter" .planning/phases/aim-0-readiness-aliyun-ecs/aim-0-01-spec-rtt-mem-dryrun-PLAN.md
# → 1 match (expected: ≥ 1)
```

All 4 verifications PASS.

## Files modified

- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-01-spec-rtt-mem-dryrun-PLAN.md`
- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-02-smoke-ingest-scratch-PLAN.md`
- `.planning/quick/260520-sho-260520-a0g-aim-0-plan-robustness-verific/260520-sho-PLAN.md` (created)
- `.planning/quick/260520-sho-260520-a0g-aim-0-plan-robustness-verific/260520-sho-SUMMARY.md` (this file)
- `.planning/STATE.md` (quick task row appended)

## Commit

`docs(aim-0): plan robustness — verification + fallbacks + env-inventory (260520-a0g)`
