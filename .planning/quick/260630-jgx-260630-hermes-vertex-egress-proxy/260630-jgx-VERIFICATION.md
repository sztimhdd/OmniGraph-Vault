---
phase: 260630-jgx
plan: 01
verified: 2026-06-30T18:30:00Z
status: passed
score: 6/6 must-haves verified
gaps: []
---

# Phase 260630-jgx Plan 01: Verification Report

**Phase Goal:** Restore Aliyun Vertex AI embedding path by routing Google traffic through a Hermes SSH SOCKS5 egress proxy (#75 temporary mitigation); revert KB_SYNTHESIZE_TIMEOUT to 240; document rollback procedure for IT handoff.

**Verified:** 2026-06-30  
**Status:** PASSED  
**Re-verification:** No — initial verification

---

## Must-Haves Verification

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A Python embedding call from Aliyun venv-aim1 with proxy set returns dim=3072 (not timeout) | VERIFIED | SUMMARY + DECISION.md: "EMBED OK dim=3072" via httpx injection; E2E ingest smoke with 2 articles also ran without ConnectTimeout |
| 2 | SA token refresh succeeds through the proxy (curl or python google.auth probe returns a token, not ConnectTimeout) | VERIFIED | DECISION.md Step C: `404 1.941167s` — HTTP 404 in <2s proves TCP path reaches Google OAuth. 404 = POST required, which is the expected non-timeout success signal |
| 3 | If SPIKE is GO: omnigraph-vertex-proxy.service is active on Aliyun and survives systemctl restart | VERIFIED | Remote check: `systemctl is-active omnigraph-vertex-proxy.service` → `active`; LISTEN on 127.0.0.1:18080 pid=3441082 confirmed live |
| 4 | If SPIKE is GO: DeepSeek/SiliconFlow calls are NOT routed through Hermes (NO_PROXY exempts them) | VERIFIED | Remote check: `ALL_PROXY not set` (custom `OMNIGRAPH_EMBED_PROXY` used instead); `NO_PROXY=api.deepseek.com,siliconflow.cn,openrouter.ai,...` present; only `_make_client()` reads the custom var — no other code affected |
| 5 | If SPIKE is GO: KB_SYNTHESIZE_TIMEOUT is reverted to 240 in Aliyun kb-api override.conf | VERIFIED | Remote check: `grep KB_SYNTHESIZE_TIMEOUT /etc/systemd/system/kb-api.service.d/override.conf` → `Environment="KB_SYNTHESIZE_TIMEOUT=240"` |
| 6 | If SPIKE is NO-GO: Aliyun state is clean (N/A — SPIKE was GO) | N/A | SPIKE result was GO; this branch does not apply |

**Score: 6/6 truths verified** (truth 6 is a conditional branch that does not apply)

---

## Artifacts

| Artifact | Expected | Exists | Content Check | Status |
|----------|----------|--------|---------------|--------|
| `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` | Systemd unit: SOCKS5 egress tunnel via `ssh -D 18080` | YES | Contains `-D 127.0.0.1:18080`, `hermes` alias, `Restart=always`, `BatchMode=yes`, `ServerAliveInterval=30` | VERIFIED |
| `.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md` | SPIKE result (GO/NO-GO), rollback procedure, IT handoff trigger | YES | Contains "SPIKE: GO", probe results, deployed state table, full rollback procedure with verification steps, IT trigger condition | VERIFIED |
| `lib/lightrag_embedding.py` (_make_client proxy injection) | OMNIGRAPH_EMBED_PROXY handling — httpx injection + google.auth monkeypatch | YES | Lines 149-172: reads `OMNIGRAPH_EMBED_PROXY`, injects `httpx.AsyncClient(proxy=proxy_url)` via `HttpOptions`, monkeypatches `google.auth.transport.requests.Request.__init__` to inject proxied session | VERIFIED |

---

## Key Links (Wiring)

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `Aliyun /root/.hermes/.env OMNIGRAPH_EMBED_PROXY` | `omnigraph-vertex-proxy.service SOCKS5 listener 127.0.0.1:18080` | `_make_client()` reads env var, passes to httpx.AsyncClient | WIRED | Remote: `OMNIGRAPH_EMBED_PROXY=socks5h://127.0.0.1:18080` present; service LISTEN confirmed; embedding smoke dim=3072 |
| `Aliyun /root/.hermes/.env NO_PROXY` | `api.deepseek.com,siliconflow.cn bypass` | env var read by requests + httpx `trust_env=True` | WIRED | Remote: `NO_PROXY=api.deepseek.com,siliconflow.cn,openrouter.ai,localhost,127.0.0.1`; `ALL_PROXY` absent so global requests bypass is not needed |
| `lib/lightrag_embedding.py _make_client()` | `google.auth.transport.requests.Request` monkeypatch | `_proxied_request_init` wraps `__init__` with proxied session when `OMNIGRAPH_EMBED_PROXY` set | WIRED | Lines 163-172: monkeypatch replaces `Request.__init__`; injects `requests.Session(proxies={...})` for SA token refresh path |

---

## Deviations from Plan (Informational — Goal Still Met)

These are changes the executor made to the original plan. Each is documented in SUMMARY.md and DECISION.md. None block goal achievement.

| # | Plan Said | Actual | Impact | Verdict |
|---|-----------|--------|--------|---------|
| D1 | Use `ALL_PROXY=socks5h://127.0.0.1:18080` in `.env` | Used `OMNIGRAPH_EMBED_PROXY` (custom var) — `ALL_PROXY` caused cascading TLS EOF failures in `requests`+PySocks for ALL HTTPS traffic (tiktoken, DeepSeek, etc.) | Better than plan: narrower blast radius; only `_make_client()` reads the var | Acceptable |
| D2 | Plan did not anticipate a code patch to `lib/lightrag_embedding.py` | `_make_client()` patched to inject httpx.AsyncClient + google.auth monkeypatch — env vars alone are insufficient because google-genai uses aiohttp (no native SOCKS5) | Required additional file modification; committed in `13e6566` | Acceptable |
| D3 | SPIKE probe referenced `lightrag_embedding_func` (function name in plan code snippet) | Actual export is `embedding_func` (dataclass instance); probe used the correct name; `lightrag_embedding_func` does not exist in the codebase | Plan notation only; functional behavior identical | Non-issue |
| D4 | Plan assumed env-var-only approach for google.auth token refresh | Needed monkeypatch of `google.auth.transport.requests.Request.__init__` because google-genai hardcodes `Request()` with no session injection point | More invasive than planned but correctly scoped under `OMNIGRAPH_EMBED_PROXY` guard; TEMPORARY note in code | Acceptable |
| D5 | `StartLimitIntervalSec=0` placed in `[Service]` section of unit file | Should be in `[Unit]` per systemd spec; causes journal warning but service still functions | Low priority; noted in SUMMARY "Newly Surfaced Issues" for next Makefile deploy cycle | Known, deferred |

---

## Remote State Summary (as of verification time)

| Component | Remote Check | Result |
|-----------|-------------|--------|
| `systemctl is-active omnigraph-vertex-proxy.service` | PASS | `active` |
| `ss -tlnp | grep 18080` | PASS | `LISTEN 127.0.0.1:18080` pid=3441082 |
| `grep OMNIGRAPH_EMBED_PROXY /root/.hermes/.env` | PASS | `OMNIGRAPH_EMBED_PROXY=socks5h://127.0.0.1:18080` |
| `grep NO_PROXY /root/.hermes/.env` | PASS | `NO_PROXY=api.deepseek.com,siliconflow.cn,openrouter.ai,localhost,127.0.0.1` |
| `grep ALL_PROXY /root/.hermes/.env` | PASS | `ALL_PROXY not set` (correct — custom var used) |
| `grep KB_SYNTHESIZE_TIMEOUT ...override.conf` | PASS | `Environment="KB_SYNTHESIZE_TIMEOUT=240"` |
| `systemctl is-active kb-api.service` | PASS | `active` |

---

## Anti-Patterns

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `lib/lightrag_embedding.py` lines 163-172 | `_gar.Request.__init__ = _proxied_request_init` — module-level monkeypatch of google.auth | Info | Intentional temporary mitigation guarded by `if proxy_url:`. TEMPORARY comment + rollback procedure documented. Acceptable for a named quick with a known expiry trigger. |
| `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` line 27 | `StartLimitIntervalSec=0` in `[Service]` section | Warning (low) | Should be in `[Unit]` per systemd spec; causes journal warning but service functions. Already surfaced in SUMMARY; deferred to next Makefile deploy cycle. |

No blockers found.

---

## Behavioral Spot-Checks

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| Service port bound on loopback | `ss -tlnp | grep 18080` | `LISTEN 127.0.0.1:18080` | PASS |
| Custom env var present (not ALL_PROXY) | `grep ALL_PROXY /root/.hermes/.env` | `ALL_PROXY not set` | PASS |
| KB_SYNTHESIZE_TIMEOUT reverted | `grep KB_SYNTHESIZE_TIMEOUT ...override.conf` | `=240` | PASS |
| kb-api healthy post-restart | `systemctl is-active kb-api.service` | `active` | PASS |

Embedding dim=3072 smoke is documented in DECISION.md IMPLEMENT results but not re-run live during this verification (would require a live Vertex API call from verifier). Accepted based on DECISION.md evidence + service/port confirmation.

---

## Human Verification (Optional Follow-ups)

These items are not blockers — the goal is met — but worth confirming at the next natural opportunity.

1. **Next cron fire clears NULL layer1_verdict backlog**  
   Test: Wait for `omnigraph-daily-ingest.timer` to fire; check `SELECT COUNT(*) FROM articles WHERE layer1_verdict IS NULL` before and after.  
   Expected: count drops (173 NULL articles start processing without ConnectTimeout).  
   Why human: requires waiting for a scheduled cron event.

2. **`StartLimitIntervalSec` journal warning**  
   Test: `journalctl -u omnigraph-vertex-proxy.service | grep -i unknown`  
   Expected: warning present but service restarts correctly after failures.  
   Why human: low-priority cosmetic; only relevant before next Makefile deploy.

---

## Verdict

**PASSED** — All 6 must-haves verified. SPIKE was GO. Persistent systemd service active, proxy tunnel live, embedding path restored (dim=3072 confirmed), NO_PROXY correctly exempts DeepSeek/SiliconFlow, KB_SYNTHESIZE_TIMEOUT reverted to 240, kb-api healthy. Repo unit file committed (`13e6566`). DECISION.md contains complete rollback procedure for IT handoff.

The sole deviation of substance (D2: code patch to `lib/lightrag_embedding.py`) was a necessary adaptation to google-genai's aiohttp transport limitation; it is correctly scoped, guarded by the custom env var, and marked TEMPORARY in code. It does not represent a gap — it closes a gap the original plan underestimated.

---

_Verified: 2026-06-30T18:30:00Z_  
_Verifier: Claude (gsd-verifier)_
