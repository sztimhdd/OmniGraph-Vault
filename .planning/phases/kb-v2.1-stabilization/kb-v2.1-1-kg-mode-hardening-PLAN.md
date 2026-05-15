---
phase: kb-v2.1-1-kg-mode-hardening
requirements: [REQ-5]
priority: P0
skills_required: [security-reviewer, python-patterns, writing-tests]
wave: 1
depends_on: []
estimated_loc: 100-200
estimated_time: 1d
---

# Phase kb-v2.1-1 — KG Mode Production Hardening

## Goal

Make `/kb/api/search?mode=kg` and KG-backed synthesis paths production-safe:
no hardcoded developer credential paths, no OOM kills, no Caddy 502, no
indefinite hangs, no secret leakage in logs. Either the KG mode WORKS reliably
under resource limits, OR it returns a controlled "kg_unavailable" degraded
response while FTS5 + happy-path /api/synthesize continue to work.

## Why this is P0

Aliyun production observation 2026-05-14:
- KG search triggered LightRAG embedding work
- Logged error for missing local credential path: `/home/sztimhdd/.hermes/gcp-paid-sa.json`
- One KG search caused `kb-api.service` OOM kill (auto-restart by systemd)

Production is currently fragile to KG-mode requests. This phase closes that.

## Files affected

| File | Action |
|---|---|
| `kb/services/synthesize.py` | MODIFY — credential discovery, memory bounds, error handling |
| `kb/api.py` | MODIFY — `/api/search?mode=kg` route handler hardening + `kg_unavailable` controlled response |
| `kb/config.py` | MODIFY — env var for GCP credential path; remove any hardcoded developer paths |
| `lib/llm_complete.py` (or wherever LightRAG embedding init lives) | INVESTIGATE — find all credential reads; route through kb/config.py env var |
| `kb/deploy/kb-api.service` (NEW or symbolic update) | NEW reference template — `MemoryMax=2G`, `MemoryHigh=1.5G`, `CPUQuota=200%` |
| `kb-deploy-runbook.md` (or part of phase output) | NEW — Aliyun operator instructions for systemd unit refresh |
| `tests/integration/kb/test_kg_mode_hardening.py` | NEW — credential env var honored, memory-bound smoke, controlled-degraded response shape |

## Read first (mandatory)

1. `kb/docs/10-DESIGN-DISCIPLINE.md` — especially Rule 3 (local UAT mandatory)
2. `kb/services/synthesize.py` — full file
3. `kb/api.py` — `/api/search` route + `/api/synthesize` route
4. `lib/llm_complete.py` — all credential reads
5. `lib/lightrag_embedding.py` — Vertex/Gemini path divergence
6. `~/.hermes/.env` reference (production env vars list, no values)
7. Aliyun journalctl output for `kb-api.service` (request from operator if needed)

## Action

### Task 1 — Credential discovery + env-driven config

Invoke `Skill(skill="security-reviewer", args="Audit kb/services/synthesize.py + lib/llm_complete.py + lib/lightrag_embedding.py for hardcoded credential paths or paths that resolve to developer-specific home directories. Surface every literal '/home/...', '~/.hermes/...gcp-paid-sa.json', and similar. Recommend env var names + safe-default behavior when env unset (fail-closed with controlled error, NOT 500). Output checklist for executor.")`.

Then:

1. Find every credential file path read. Common suspects:
   - `OMNIGRAPH_GCP_SA_KEY_PATH` / `GOOGLE_APPLICATION_CREDENTIALS`
   - DeepSeek + Gemini API key reads (less risky — env var already)
2. Add `KB_KG_GCP_SA_KEY_PATH` (or reuse existing) to `kb/config.py` mirroring `KB_DB_PATH` pattern.
3. Replace hardcoded path reads with `config.KB_KG_GCP_SA_KEY_PATH` (or equivalent).
4. If env var unset OR file at path doesn't exist OR can't read:
   - Set in-module flag `KG_MODE_AVAILABLE = False`
   - Log WARNING once at module import (no traceback, no path leak)
   - Subsequent KG-mode requests return controlled degraded response (see Task 3)

### Task 2 — Memory bound on systemd unit

Document a systemd unit template (or extend existing `/etc/systemd/system/kb-api.service`) with:

```ini
[Service]
MemoryMax=2G
MemoryHigh=1.5G
CPUQuota=200%
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
```

Rationale:
- `MemoryHigh=1.5G` triggers throttling before OOM
- `MemoryMax=2G` is hard cap (kernel kills process; systemd restarts)
- Aliyun ECS has 3.4Gi RAM total; vitaclaw-site Node uses ~500MB; 2G cap leaves headroom
- `StartLimitBurst=5 / IntervalSec=60` prevents OOM-restart-OOM-restart loops from monopolizing

Output: a reference systemd unit at `kb/deploy/kb-api.service` (NOT auto-installed; operator copies). Document expected memory profile in the unit's comments.

Invoke `Skill(skill="python-patterns", args="Review credential env-var pattern + KG_MODE_AVAILABLE module flag — Pythonic, fail-closed, no global mutable state for production safety.")`.

### Task 3 — Controlled-degraded response shape

When `KG_MODE_AVAILABLE = False`:

`GET /api/search?mode=kg`:
```json
{
  "items": [],
  "total": 0,
  "mode": "kg",
  "kg_unavailable": true,
  "reason": "kg_credentials_missing" | "kg_disabled" | "kg_resource_exhausted",
  "fallback_suggestion": "Use mode=fts for keyword search or /api/synthesize for Q&A."
}
```

HTTP status: 200 (NOT 500/502).

`POST /api/synthesize` with KG path failure: existing `fts5_fallback` path already covers this; verify no regression.

### Task 4 — Tests

Invoke `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + real FastAPI TestClient. Test: env var unset → KG_MODE_AVAILABLE=False → /api/search?mode=kg returns kg_unavailable=true with HTTP 200. Test: env var pointing to non-existent file → same behavior. Test: KG-mode request when KG_MODE_AVAILABLE=True does NOT 500. Test: rapid 10x KG-mode requests don't crash service (smoke).")`.

`tests/integration/kb/test_kg_mode_hardening.py`:
- `test_kg_mode_unavailable_when_env_unset`
- `test_kg_mode_unavailable_when_credential_file_missing`
- `test_kg_mode_response_shape_includes_kg_unavailable_field`
- `test_kg_mode_response_status_200_not_500_when_unavailable`
- `test_search_mode_fts_unaffected_by_kg_mode_disable`
- `test_synthesize_falls_back_to_fts5_when_kg_path_fails` (regression of existing kb-3-09)

### Task 5 — Local UAT (Rule 3 mandatory)

Run `.scratch/local_serve.py` against `.dev-runtime/`. Exercise:

```bash
# 1. KG mode with credential set (should work or controlled fail)
KB_KG_GCP_SA_KEY_PATH=/path/to/dummy.json venv/Scripts/python.exe .scratch/local_serve.py &
curl -sS "http://127.0.0.1:8766/api/search?q=AI%20Agent&mode=kg" | head

# 2. KG mode with credential UNSET (must return kg_unavailable, not 500)
unset KB_KG_GCP_SA_KEY_PATH
venv/Scripts/python.exe .scratch/local_serve.py &
curl -sS "http://127.0.0.1:8766/api/search?q=AI%20Agent&mode=kg"
# expect: {"items":[],"total":0,"mode":"kg","kg_unavailable":true,...}
# expect: HTTP 200

# 3. FTS mode unaffected
curl -sS "http://127.0.0.1:8766/api/search?q=langchain&mode=fts" | head
# expect: regular response

# 4. Synthesize fts5_fallback path
curl -X POST -H "content-type: application/json" -d '{"question":"test","lang":"zh"}' \
  http://127.0.0.1:8766/api/synthesize
# expect: 202 + job_id; polling eventually returns confidence="fts5_fallback" (KG unavailable)
```

Capture screenshots: `.playwright-mcp/kb-v2.1-1-kg-disabled-{uat-step}.png`.

## Acceptance criteria (grep-verifiable)

- [ ] No hardcoded developer paths: `grep -rE "/home/sztimhdd|/Users/[a-z]+/" kb/ lib/ | grep -v test` returns 0 matches
- [ ] `kb/config.py` has new env var for KG credential path
- [ ] `kb/services/synthesize.py` has `KG_MODE_AVAILABLE` module flag
- [ ] `kb/deploy/kb-api.service` reference unit has `MemoryMax=2G`, `MemoryHigh=1.5G`
- [ ] `tests/integration/kb/test_kg_mode_hardening.py` exists with ≥6 test cases, all PASS
- [ ] Existing kb-3-09 fts5_fallback tests still PASS (regression)
- [ ] Local UAT scenarios 1-4 (above) all behave as documented
- [ ] No regression in full pytest run
- [ ] kb-deploy-runbook for Aliyun operator: how to apply the memory limits + verify

## Skill discipline (regex check)

After execution, SUMMARY.md MUST contain:
- `Skill(skill="security-reviewer"` — credential audit
- `Skill(skill="python-patterns"` — env var + flag pattern
- `Skill(skill="writing-tests"` — test suite

## Anti-patterns

- ❌ DO NOT 500/502 on KG mode unavailable — controlled-degraded only
- ❌ DO NOT log credential path values in error messages
- ❌ DO NOT swallow exceptions silently — surface as `kg_unavailable=true` with `reason` field
- ❌ DO NOT change C1 contract (kg_synthesize.synthesize_response signature read-only)
- ❌ DO NOT use `git add -A`
- ❌ DO NOT modify Aliyun production directly — phase output is reference systemd unit + RUNBOOK; operator applies
- ❌ DO NOT introduce hard auto-disable (e.g., disable KG mode permanently in main); MUST be env-driven so dev environments with proper creds still test KG path

## Return signal

```
## kb-v2.1-1 KG MODE HARDENING COMPLETE
- credential audit: <N> hardcoded paths found, <N> remediated
- KG_MODE_AVAILABLE flag pattern shipped
- systemd unit reference at kb/deploy/kb-api.service (MemoryMax=2G)
- tests/integration/kb/test_kg_mode_hardening.py: <X>/<X> PASS
- Local UAT: <pass>/<total>
- Skill regex: security-reviewer / python-patterns / writing-tests all in SUMMARY
- no regression: pytest <X>/<X>
- RUNBOOK for Aliyun operator: included
```
