---
quick_id: 260520-sho
user_label: 260520-a0g
slug: aim-0-plan-robustness
description: aim-0 plan robustness — verification + fallbacks + env-inventory
mode: quick
created: 2026-05-20
---

# Quick 260520-a0g — aim-0 PLAN robustness

Doc-only fix. 4 surgical edits to 2 PLAN files. No code change, no Skill, no exploration.

## Files touched

- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-01-spec-rtt-mem-dryrun-PLAN.md`
- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-02-smoke-ingest-scratch-PLAN.md`

## Edits (verbatim from operator brief)

| GAP | File | Edit |
|---|---|---|
| GAP-B + GAP-C | `aim-0-02-PLAN.md` | Delete two `sqlite3 ... FROM ingestions` SELECT blocks (`ingest_wechat.py` never writes that table); replace with entity_buffer check; rewrite "What to report" list, Pass predicate, Verification table accordingly. |
| GAP-E | both PLANs | Add Hermes-SSH-unreachable fallback URL (`Y_uRMYBmdLWUPnz_ac7jWA`, validated as `ingest_wechat.py:1647` default). |
| GAP-F | both PLANs | Add `/etc/omnigraph/.env` key inventory pre-flight grep before env-export blocks. |
| GAP-G | `aim-0-01-PLAN.md` | Fix Vision cascade comment to mention OpenRouter (real cascade is SiliconFlow → OpenRouter → Gemini Vision, not the 2-tier description in the plan). |

## Constraints (user's mandate)

- Surgical only — 4 edit regions, no other changes
- 1 atomic commit + push (`docs(aim-0): plan robustness — verification + fallbacks + env-inventory (260520-a0g)`)
- No Skill calls, no code changes
- No agent spawning — directly executed

## Out of scope

- GAP-A (Aliyun SSH reachability) — operator-side, unrelated to plan docs
- GAP-D (`config.py ENV_PATH` hardcoded) — deferred to aim-1
