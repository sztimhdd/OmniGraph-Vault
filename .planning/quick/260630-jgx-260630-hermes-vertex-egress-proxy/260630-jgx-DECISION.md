# 260630-jgx SPIKE DECISION

**Date:** 2026-06-30T17:37:47Z
**SPIKE: GO**

## Summary

The SOCKS5 egress proxy via Hermes successfully routes Vertex AI embedding calls from
Aliyun through Hermes' internet connection, restoring the broken Google/Vertex API path.

**Deviation from plan:** The implementation requires a code patch in `lib/lightrag_embedding.py`
in addition to env var changes. `ALL_PROXY`/`HTTPS_PROXY` alone are insufficient because:
- The `google-auth` SA token refresh path uses `requests` library (needs PySocks) 
- The `google-genai` SDK async embedding path uses `aiohttp`, which does NOT support SOCKS5 natively
- Fix: inject an `httpx.AsyncClient(proxy=...)` into `genai.Client` via `HttpOptions(httpx_async_client=...)`,
  which forces the SDK to use httpx (SOCKS5-capable via socksio) instead of aiohttp

## Step-by-step probe results

### Step A: Prerequisites
- `httpx[socks]` / `socksio-1.0.0`: installed ✓
- `PySocks-1.7.1`: installed ✓  
- `aiohttp-socks-0.11.0`: installed (not used in final solution, but installed) ✓
- `/etc/hosts` Google pins (`oauth2.googleapis.com`, `aiplatform.googleapis.com`,
  `us-central1-aiplatform.googleapis.com` → `142.250.73.106`): REMOVED ✓
  (were present; removed so socks5h resolution is unambiguous)

### Step B: Temporary tunnel
- Opened: `ssh -fN -D 127.0.0.1:18080 -p 49221 <user>@<host>` on Aliyun
- Port check: `LISTEN 127.0.0.1:18080` ✓

### Step C: SA token refresh probe (curl)
```
404 1.941167s
```
HTTP 404 in 1.9s — TCP path via Hermes reaches Google OAuth ✓
(404 = POST required; non-timeout = success)

### Step D: Python embedding probe
**First attempt (env var only):** FAIL
- `ALL_PROXY` not honored by aiohttp (google-genai async transport)
- `HTTPS_PROXY` causes aiohttp to attempt HTTP CONNECT to SOCKS5 port → `ServerDisconnectedError`
- Direct connections to Google IPs (not via proxy) observed via `ss -tp`

**Diagnosis:** google-genai v1.75.0 uses aiohttp for Vertex async calls. aiohttp does NOT
support SOCKS5 via env vars. Fix: inject `httpx.AsyncClient(proxy="socks5h://...")` via
`HttpOptions(httpx_async_client=async_client)` to force httpx transport.

**Second attempt (httpx injection):** PASS
```
Vertex mode: True project='banded-totality-485901'
EMBED OK dim=3072
```
Traffic confirmed via `ss -tp`: python process connected to `127.0.0.1:18080` (SOCKS5 tunnel) ✓

### Step E: Tunnel killed
- `pkill -f "ssh.*-D.*18080"` executed ✓
- Port check: `PORT 18080 NOT BOUND` ✓

## /etc/hosts status
- Modified in Step A: YES — 3 Google IP pins removed
- Current state: no Google pins in /etc/hosts

## KB_SYNTHESIZE_TIMEOUT status
- Currently: 30 (lowered as #75 mitigation on 2026-06-29)
- Will be reverted to 240 in Task 2 Step D

---

## IMPLEMENT Results (Task 2 — COMPLETED 2026-06-30T18:10:00Z)

### Deviations from original plan

**Original plan:** set `ALL_PROXY=socks5h://127.0.0.1:18080` in `.env`
**Actual implementation:** use `OMNIGRAPH_EMBED_PROXY=socks5h://127.0.0.1:18080` (custom var)

Reason: `ALL_PROXY` in `.env` caused `requests`+PySocks to try routing ALL HTTPS traffic
through SOCKS5 (including tiktoken BPE downloads, DeepSeek API, etc.), causing cascading
TLS EOF failures (`SSLZeroReturnError`) and kb-api startup crashes. Using a custom env var
that only the embedding code reads prevents unintended proxy routing.

**Additional code changes:**
- `lib/lightrag_embedding.py` `_make_client()`: patched to inject httpx.AsyncClient proxy
  AND monkeypatch google.auth.transport.requests.Request with proxied session when
  `OMNIGRAPH_EMBED_PROXY` is set
- venv/ also needs PySocks (kb-api uses venv/, not venv-aim1/; PySocks installed in both)

### Final deployed state on Aliyun

| Component | Status | Value |
|-----------|--------|-------|
| `omnigraph-vertex-proxy.service` | active | LISTEN 127.0.0.1:18080 (pid 3441082 → hermes:49221) |
| `/root/.hermes/.env` OMNIGRAPH_EMBED_PROXY | set | `socks5h://127.0.0.1:18080` |
| `/root/.hermes/.env` NO_PROXY | set | `api.deepseek.com,siliconflow.cn,...` |
| `/root/.hermes/.env` ALL_PROXY | **not set** | n/a |
| KB_SYNTHESIZE_TIMEOUT | 240 | reverted from 30 |
| kb-api.service | active | status=ok |
| Embedding smoke | PASS | `EMBED OK dim=3072` |
| E2E ingest | PASS | 2 articles scraped+embedded, no ConnectTimeout |
| Backup | created | `/root/.hermes/.env.bak-pre-socks5-260630` |
| PySocks in venv/ | installed | 1.7.1 |
| PySocks in venv-aim1/ | installed | 1.7.1 |

### Commit hash
`13e6566` — feat(260630-jgx): SOCKS5 egress proxy via Hermes to unblock Vertex/Google API (#75 temp mitigation)

---

## Rollback procedure (for IT handoff — self-contained)

**Trigger condition:** IT confirms ACK NetworkPolicy fix for wg-gcp-sg wireguard peering.

**Verification before rollback:**
```bash
ssh aliyun-vitaclaw 'wg show wg-gcp-sg | grep latest-handshake'
# → must show timestamp within last 30s

ssh aliyun-vitaclaw 'curl -sS -o /dev/null -w "%{http_code}\n" https://oauth2.googleapis.com/token'
# → expect 400 within 2s (not timeout) — means direct Google egress works
```

**Rollback steps:**
```bash
# 1. Remove proxy vars from .env
ssh aliyun-vitaclaw 'sed -i "/^OMNIGRAPH_EMBED_PROXY=/d; /^NO_PROXY=/d" /root/.hermes/.env'

# 2. Stop and disable the tunnel service
ssh aliyun-vitaclaw 'systemctl disable --now omnigraph-vertex-proxy.service'

# 3. Remove code patch: set OMNIGRAPH_EMBED_PROXY to empty string (code skips proxy injection)
#    OR deploy a git reverted version of lib/lightrag_embedding.py from commit before 13e6566

# 4. Restart ingest services so they pick up the clean env
ssh aliyun-vitaclaw 'systemctl restart omnigraph-daily-ingest.service omnigraph-evening-ingest.service'

# 5. Verify embedding still works directly (should now use direct WireGuard path)
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && set -a && source /root/.hermes/.env && set +a &&
  /root/OmniGraph-Vault/venv-aim1/bin/python3 -c "
import asyncio
from lib.lightrag_embedding import embedding_func
import numpy as np
async def probe():
    r = await embedding_func([\"rollback verify\"])
    print(f\"EMBED OK dim={r.shape[-1]}\") if isinstance(r, np.ndarray) else print(\"EMBED FAIL\")
asyncio.run(probe())"'
# → expect EMBED OK dim=3072
```

---

## #75 status update

**B-mitigation DEPLOYED (proxy active, embedding recovering)**

Root cause (#75): ACK cluster ingestion broke WireGuard peering to GCP (wg-gcp-sg).
Direct Google/Vertex API calls from Aliyun time out. IT is fixing.

This proxy workaround routes Vertex embedding calls: Aliyun → SOCKS5(18080) → Hermes → Google.
DeepSeek/SiliconFlow NOT proxied (ALL_PROXY not set; custom OMNIGRAPH_EMBED_PROXY used).
KB_SYNTHESIZE_TIMEOUT reverted to 240 — synthesis should recover with embedding.

**Next scheduled cron:** omnigraph-daily-ingest.timer will pick up 173 NULL layer1_verdict articles.
