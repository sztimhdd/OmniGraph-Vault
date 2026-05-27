---
phase: 18-daily-ops-hygiene
plan: 00
subsystem: vertex-live-probe
tags: [wave1, vertex, embedding, probe, telegram, cron, hyg-01]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 18-00 SUMMARY — Vertex AI embedding model-name live probe

**Status:** Complete (local ship; Hermes-side cron registration pending operator run)
**Wave:** 1
**Requirements:** HYG-01
**Depends on:** —

---

## 1. What shipped

| Artifact | Lines | Purpose |
|---|---|---|
| `scripts/vertex_live_probe.py` | 112 | Probes 3 candidate Vertex embedding model names; exits 0 if any green, 1 + Telegram on all-red |
| `scripts/register_vertex_probe_cron.sh` | 39 | Idempotent Hermes cron registrar (monthly, day 1 @ 08:00) |
| `tests/unit/test_vertex_live_probe.py` | 170 | 6 mocked tests (all-green / all-404 / partial / no-telegram / JSON schema / missing-env) |

Tests: **6/6 pass** on Windows (`venv/Scripts/python -m pytest tests/unit/test_vertex_live_probe.py -v`). No live network, no live Vertex, no live Telegram.

---

## 2. Design decisions

### Probe design

- **Candidate list** is pinned to 3 names in preference order: `gemini-embedding-2` → `gemini-embedding-2-preview` → `gemini-embedding-001`. The first two are the two names that have been authoritative in the Vertex catalog within the last 7 days (per `memory/vertex_ai_smoke_validated.md`). The third is a safety net.
- **"ANY green = pass" semantic**: the probe's job is to tell us whether the Vertex catalog still has *some* usable embedding model for us, not which specific name. If all 3 go red simultaneously, something larger is broken (Vertex outage, project credential expiry, region issue) — the Telegram message is operator-actionable either way.
- **Serial probing** (not parallel): 3 calls over 3s is cheap and keeps error messages per-candidate clean. Parallel `asyncio.gather` would muddy rate-limit error attribution if we ever hit one.

### Cron design

- **Monthly (day 1 @ 08:00)** is the minimum useful cadence. The 2026-05-02 → 2026-05-03 flip observed in Wave 0 was actually *within* 24h — monthly probe alone would have caught the second flip on day-1-next-month, not before. Weekly or daily is arguably better, but monthly is the floor; operators can manually run the probe any time via the same script before any `_resolve_model()` change (hard prerequisite from `memory/vertex_ai_smoke_validated.md`).
- **Natural-language prompt** per D-16 "Hermes drives" — the Hermes skill system translates the prompt into the Python subprocess. Consistent with `scripts/register_phase5_cron.sh`.

### Telegram delivery

- Reuses the Phase 5 Wave 2 plumbing (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from `~/.hermes/.env`). No new bot, no new chat id.
- Emoji prefix `🔴` for critical per D-18-03.
- Silent degradation when creds missing (`[no-telegram-creds]` to stderr) — probe still exits with the right code.

---

## 3. Acceptance criteria reconciliation

| Criterion | Status |
|---|---|
| `scripts/vertex_live_probe.py` ≥ 80 lines | ✅ 112 lines |
| `grep -q "gemini-embedding-2"` | ✅ 2 occurrences (constant + tests) |
| `grep -q "vertexai=True"` | ✅ 1 occurrence |
| `grep -q "sendMessage"` in probe | ✅ 1 occurrence |
| `! grep -q "api_key="` (no api-key mode) | ✅ absent |
| 5+ pytest tests pass | ✅ 6/6 pass |
| `scripts/register_vertex_probe_cron.sh` ≥ 30 lines | ✅ 39 lines |
| `bash -n` syntax valid | ✅ OK |
| `grep -q "hermes cron add"` | ✅ 1 occurrence |
| `grep -q "0 8 1 \* \*"` monthly schedule | ✅ present |
| `grep -q "SKIP"` idempotency branch | ✅ 2 occurrences |

---

## 4. Hermes-side verification (operator to run)

```bash
# 1. Pull + register cron
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_vertex_probe_cron.sh"

# 2. Manual trigger — should return exit 0 (gemini-embedding-2 is authoritative 2026-05-03)
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && venv/bin/python scripts/vertex_live_probe.py"

# 3. Confirm cron appears in list
ssh -p 49221 sztimhdd@ohca.ddns.net "hermes cron list | grep vertex-probe-monthly"

# 4. Re-run registrar — should print SKIP
ssh -p 49221 sztimhdd@ohca.ddns.net "bash ~/OmniGraph-Vault/scripts/register_vertex_probe_cron.sh"
```

Expected: step 2 prints `✅ dims=3072  gemini-embedding-2` and `[OK] 1 / 3 candidate(s) green`. Exit 0. No Telegram.

If step 2 reports **all 3 candidates red**, this is the third Vertex catalog flip in a week — **do NOT auto-patch**; ping the user immediately.

---

## 5. Commits

1. `docs(18): plan Milestone v3.3 Daily-Ops Hygiene` — planning docs (before this plan started)
2. (this plan) — `feat(18-00): vertex live-probe + monthly Hermes cron (HYG-01)`

---

## 6. Hand-off

Plan 18-00 static-code portion complete. Plan 18-01 (118-image cap) is unblocked and starts next.

Monitoring: operator should watch the first month's cron fire (2026-06-01 @ 08:00 local) and confirm no false-positive alerts. If a real alert fires, the operational lesson from 05-00-SUMMARY § C applies — investigate empirically before patching code.
