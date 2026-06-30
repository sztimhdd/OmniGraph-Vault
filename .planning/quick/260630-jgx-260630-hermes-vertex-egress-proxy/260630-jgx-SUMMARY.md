---
phase: 260630-jgx
plan: 01
subsystem: ingest/embedding/proxy
tags: [vertex-ai, socks5, proxy, hermes, embedding, issue-75, lightrag]
dependency_graph:
  requires: [omnigraph-vertex-proxy.service, hermes-ssh-access]
  provides: [vertex-embedding-restored, ingest-pipeline-unblocked]
  affects: [batch_ingest_from_spider, lib/lightrag_embedding, kb-api]
tech_stack:
  added: [socksio-1.0.0, PySocks-1.7.1, aiohttp-socks-0.11.0]
  patterns: [httpx SOCKS5 proxy injection via HttpOptions, google.auth Request monkeypatch]
key_files:
  created:
    - deploy/aliyun/systemd/omnigraph-vertex-proxy.service
    - .planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md
  modified:
    - lib/lightrag_embedding.py (_make_client: httpx proxy + google.auth monkeypatch)
    - /root/.hermes/.env (Aliyun, not repo: added OMNIGRAPH_EMBED_PROXY + NO_PROXY)
    - /etc/systemd/system/kb-api.service.d/override.conf (Aliyun: KB_SYNTHESIZE_TIMEOUT 30→240)
    - /etc/hosts (Aliyun: removed 3 Google IP pins)
decisions:
  - "Use OMNIGRAPH_EMBED_PROXY (not ALL_PROXY) — custom var prevents unintended proxy routing by requests/PySocks for non-Google traffic"
  - "Monkeypatch google.auth.transport.requests.Request in _make_client to inject proxied session for SA token refresh"
  - "Force httpx transport via HttpOptions(httpx_async_client=httpx.AsyncClient(proxy=...)) to bypass aiohttp lack of SOCKS5 support"
metrics:
  duration: 47 minutes
  completed_date: "2026-06-30"
  tasks_completed: 2
  files_modified: 2
---

# Phase 260630-jgx Plan 01: Hermes Vertex Egress Proxy Summary

**One-liner:** SOCKS5 egress proxy via Hermes SSH tunnel restores Aliyun→Vertex AI embedding path while IT fixes ACK NetworkPolicy (#75); requires httpx injection + google.auth monkeypatch to bypass aiohttp's SOCKS5 limitation.

## What Was Done

Deployed a temporary SOCKS5 egress proxy to unblock Aliyun's broken Vertex/Google API path
caused by the ACK NetworkPolicy issue (#75 — wg-gcp-sg WireGuard peer down).

336 articles were stuck (173 with `layer1_verdict=NULL`, ingest cron dying with
`TransportError oauth2.googleapis.com ConnectTimeout`). This mitigation restores
embedding + classify within hours.

### Architecture

```
Aliyun Python process
  → OMNIGRAPH_EMBED_PROXY=socks5h://127.0.0.1:18080
  → httpx.AsyncClient(proxy=...) [injected via _make_client()]
  → 127.0.0.1:18080 [omnigraph-vertex-proxy.service SSH -D SOCKS5 listener]
  → SSH tunnel to Hermes (hermes alias in ~/.ssh/config)
  → Hermes internet → Google APIs / Vertex AI
```

## Tasks Completed

### Task 1: SPIKE (PASS)

Proved SOCKS5 proxy works end-to-end before committing persistent changes.

- Installed: socksio, PySocks, aiohttp-socks in venv-aim1
- Removed `/etc/hosts` Google IP pins (3 entries for oauth2 + aiplatform)
- Opened temp tunnel: `ssh -fN -D 127.0.0.1:18080 -p 49221 <user>@<hermes>`
- SA token curl probe: `404 1.9s` via SOCKS5 — Google OAuth reachable
- Python embedding probe (final): `EMBED OK dim=3072` via httpx injection
- Tunnel killed: port 18080 unbound confirmed

### Task 2: IMPLEMENT (PASS)

- Wrote `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` (uses `hermes` alias)
- SCPd unit to Aliyun `/etc/systemd/system/`, enabled + started
- Backed up `.env` to `.env.bak-pre-socks5-260630`
- Added `OMNIGRAPH_EMBED_PROXY=socks5h://127.0.0.1:18080` + `NO_PROXY=...` to `.env`
- Reverted `KB_SYNTHESIZE_TIMEOUT` 30→240 in kb-api override.conf
- Restarted kb-api (also installed PySocks in `venv/` to fix kb-api startup crash)
- E2E smoke: `EMBED OK dim=3072` via systemd tunnel + patched code
- E2E ingest: 2 articles scraped + LightRAG embedding running without ConnectTimeout
- Committed: `13e6566`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `ALL_PROXY` env var causes cascading failures — switched to custom var**
- **Found during:** Task 2 Step C/D (implementing .env changes)
- **Issue:** Setting `ALL_PROXY=socks5h://...` in `.env` causes `requests`+PySocks to route ALL HTTPS traffic through SOCKS5, including tiktoken BPE downloads (kb-api startup), DeepSeek API, SiliconFlow. This caused `TLS/SSL connection has been closed (EOF)` errors and kb-api crash loop.
- **Root cause:** PySocks intercepts `requests` sessions globally when `ALL_PROXY` is set; `socks5h://` scheme is not properly supported by urllib3/PySocks leading to TLS EOF.
- **Fix:** Use `OMNIGRAPH_EMBED_PROXY` (custom var) instead of `ALL_PROXY`. Only `_make_client()` reads this var — no other code affected.
- **Files modified:** `lib/lightrag_embedding.py`, `/root/.hermes/.env` (Aliyun)
- **Commit:** `13e6566`

**2. [Rule 1 - Bug] google-genai uses aiohttp (no SOCKS5) — httpx injection required**
- **Found during:** Task 1 Step D (initial embedding probe)
- **Issue:** `ALL_PROXY` not honored by google-genai's aiohttp transport. `HTTPS_PROXY` makes aiohttp attempt HTTP CONNECT to SOCKS5 port → `ServerDisconnectedError`. Direct TCP connections to Google IPs observed (bypassing SOCKS5).
- **Root cause:** google-genai v1.75.0 uses aiohttp for async Vertex API calls. aiohttp has no native SOCKS5 support and treats `HTTPS_PROXY` as HTTP CONNECT proxy.
- **Fix:** Inject `httpx.AsyncClient(proxy=proxy_url)` via `HttpOptions(httpx_async_client=...)`, forcing the SDK to use httpx (which supports SOCKS5 natively via socksio).
- **Files modified:** `lib/lightrag_embedding.py`
- **Commit:** `13e6566`

**3. [Rule 2 - Missing functionality] google-auth SA token refresh uses requests (separate from httpx path)**
- **Found during:** Task 2 Step E (end-to-end smoke after systemd deploy)
- **Issue:** Even with httpx injection for the API call, the SA token refresh path in google-genai uses `google.auth.transport.requests.Request()` (blocking `requests` + urllib3 + PySocks). This path gets TLS EOF when PySocks routes through the SOCKS5 tunnel.
- **Root cause:** Two distinct HTTP transport paths — httpx for the API call, requests for token auth. The requests SOCKS5 path fails at TLS layer (TLS EOF from SOCKS5 tunnel, specific to this server/client combination).
- **Fix:** Monkeypatch `google.auth.transport.requests.Request.__init__` to inject a `requests.Session` with `proxies={'https': proxy_url}` when `OMNIGRAPH_EMBED_PROXY` is set. This routes the token refresh through the same SOCKS5 tunnel but via the requests+PySocks path.
- **Files modified:** `lib/lightrag_embedding.py`
- **Commit:** `13e6566`

**4. [Rule 2 - Missing functionality] PySocks needed in venv/ (kb-api venv), not just venv-aim1/**
- **Found during:** Task 2 Step D (kb-api restart after .env change)
- **Issue:** kb-api reads `EnvironmentFile=/root/.hermes/.env`. With `ALL_PROXY` set (before we switched to custom var), kb-api's Python process tried SOCKS5 for tiktoken BPE download at startup, but `venv/` lacked PySocks → `InvalidSchema: Missing dependencies for SOCKS support` crash loop.
- **Fix:** Installed PySocks in `venv/` (`/root/OmniGraph-Vault/venv/bin/pip install PySocks`). Also switched to `OMNIGRAPH_EMBED_PROXY` (custom var) which kb-api never reads, permanently preventing this issue.
- **Files modified:** `venv/` packages on Aliyun (not repo)

**5. [Rule 1 - Bug] Systemd tunnel stale state after spike test kill**
- **Found during:** Task 2 Step E (post-systemd-deploy smoke test)
- **Issue:** After the spike `pkill` killed the temporary nohup tunnel, the systemd service restarted but curl through port 18080 returned `SSL EOF`. Subsequent httpx probes also failed. 
- **Root cause:** Suspected stale SOCKS5 multiplexer state in SSH after previous concurrent connection attempts during the spike were abruptly killed.
- **Fix:** `systemctl restart omnigraph-vertex-proxy.service` — fresh SSH connection, all subsequent tests passed.
- **Not a code change** — operational note for future reference.

## Known Stubs

None. All Aliyun-side changes are live. The `OMNIGRAPH_EMBED_PROXY` env var is the activation flag — removing it from `.env` deactivates the proxy path cleanly.

## #75 Status Update

**B-mitigation DEPLOYED** — proxy active, embedding recovering.

- `omnigraph-vertex-proxy.service` is enabled and active (survives reboot via `WantedBy=multi-user.target`)
- Next ingest cron (omnigraph-daily-ingest.timer) will process 173 NULL layer1_verdict articles
- `KB_SYNTHESIZE_TIMEOUT=240` restored — synthesis should recover

## Newly Surfaced Issues for Orchestrator

1. **Rollback tracking needed:** When IT confirms ACK NetworkPolicy fix, this proxy mitigation needs rollback. Full procedure is in `260630-jgx-DECISION.md`. Suggest adding a reminder in ISSUES.md.

2. **Systemd service `StartLimitIntervalSec` in [Service] section:** Warning in journal: `Unknown key name 'StartLimitIntervalSec' in section 'Service'`. Should be in `[Unit]` section in the next Makefile deploy cycle. Low priority — service still functions correctly.

## Self-Check

Files created:
- `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` ✓
- `.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md` ✓
- `.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-SUMMARY.md` ✓

Commit: `13e6566` ✓

Aliyun state verified:
- `systemctl is-active omnigraph-vertex-proxy.service` → active ✓
- `ss -tlnp | grep 18080` → LISTEN ✓
- `grep OMNIGRAPH_EMBED_PROXY /root/.hermes/.env` → set ✓
- `grep KB_SYNTHESIZE_TIMEOUT ...override.conf` → 240 ✓
- `systemctl is-active kb-api.service` → active ✓
- Embedding smoke: `EMBED OK dim=3072` ✓
- E2E ingest: articles processing without ConnectTimeout ✓

## Self-Check: PASSED
