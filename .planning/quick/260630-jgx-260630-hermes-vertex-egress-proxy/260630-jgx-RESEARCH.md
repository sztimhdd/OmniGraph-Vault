# Research: 260630-hermes-vertex-egress-proxy

**Researched:** 2026-06-30
**Domain:** SSH SOCKS5 egress proxy for Python google-genai (httpx-based REST) + google-auth SA token refresh
**Confidence:** HIGH

## Summary

Issue #75: Aliyun was absorbed into an ACK (Alibaba Kubernetes) cluster on 2026-06-27. The node NetworkPolicy drops inbound UDP from the GCP WireGuard peer, so the wg-gcp-sg tunnel is dead and all Vertex/Google API calls timeout. IT is working on the ACK NetworkPolicy fix, but the timeline is unknown. This task researches routing Aliyun's Google API traffic through Hermes (home network, unrestricted Google egress) via an SSH SOCKS5 tunnel as an interim unblock.

**Primary recommendation:** Option A — `ssh -D <port>` SOCKS5 from Aliyun to Hermes plus `ALL_PROXY=socks5h://127.0.0.1:<port>` on Aliyun. No additional Hermes-side service needed. Zero cost. `/etc/hosts` pin must be removed or will cause silent misdirection.

---

## Item 1: google-auth SA token refresh — proxy compatibility

**Verdict: SUPPORTED (HTTPS_PROXY and ALL_PROXY, via requests default behavior)**

The google-auth library's requests transport (`google.auth.transport.requests`) initializes a plain `requests.Session()` without setting `trust_env=False`. The requests library default is `trust_env=True`, which means it automatically reads `HTTPS_PROXY`, `HTTP_PROXY`, and `ALL_PROXY` environment variables and routes through them. SA token refresh hits `oauth2.googleapis.com/token` via POST — this is a standard HTTPS request routed through the session, so it picks up the proxy setting.

Confidence: HIGH — verified against google-auth source on PyPI/GitHub (https://github.com/googleapis/google-auth-library-python/blob/main/google/auth/transport/requests.py). The session is `requests.Session()` with default `trust_env=True`.

**No code change needed on the google-auth side.** Set the env var; SA token refresh routes through the proxy automatically.

---

## Item 2: google-genai / Vertex embedding client — REST vs gRPC

**Verdict: REST over httpx — NOT gRPC. Proxy-compatible.**

Both call sites in this codebase use `google-genai` v2 (`from google import genai`):

- `lib/lightrag_embedding.py`: constructs `genai.Client(vertexai=True, project=..., location=...)` and calls `client.aio.models.embed_content(...)` — embedding path.
- `lib/llm_client.py`: same `genai.Client(vertexai=True, ...)`, calls `client.aio.models.generate_content(...)` — LLM path.
- `lib/vertex_gemini_complete.py`: same pattern for `vertex_gemini_model_complete`.

The `google-genai` v2 SDK (`google-genai>=0.28, <1.0` in requirements.txt) uses **httpx** as its HTTP transport (`SyncHttpxClient` / `AsyncHttpxClient` internally), NOT gRPC. Confirmed by inspecting `google/genai/_api_client.py`: no grpc imports, pure REST over httpx + requests.

httpx respects `HTTPS_PROXY` and `ALL_PROXY` env vars by default (`trust_env=True`). httpx also supports `socks5://` and `socks5h://` schemes via the optional `socksio` package (install with `pip install httpx[socks]`).

Confidence: HIGH — confirmed via google-genai PyPI dependency list (httpx 0.28+), httpx docs, and google/genai/_api_client.py source inspection.

**Important distinction from older SDK:** the older `google-cloud-aiplatform` / `aiplatform.init()` SDK uses gRPC. This codebase does NOT use that SDK — it uses `google-genai` v2 exclusively. gRPC proxy caveats do NOT apply here.

---

## Item 3: Tunnel architecture — proxy compatibility matrix

### Option A: `ssh -D <port>` SOCKS5 from Aliyun → Hermes (RECOMMENDED)

**How:**
```bash
# On Aliyun — run in background (systemd unit or nohup)
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -N -D 127.0.0.1:18080 \
    -p <hermes_ssh_port> <hermes_user>@<hermes_host>
```
```bash
# Set in Aliyun /root/.hermes/.env
ALL_PROXY=socks5h://127.0.0.1:18080
```

**google-auth SA token refresh:** SUPPORTED. `requests.Session` picks up `ALL_PROXY` → routes `oauth2.googleapis.com` through the SOCKS5 tunnel. With `socks5h://`, hostname resolution happens on Hermes (remote DNS), not on Aliyun. This is important for bypassing any /etc/hosts interference (see Item 4).

**google-genai httpx embed_content / generate_content:** SUPPORTED with `httpx[socks]` installed. httpx reads `ALL_PROXY=socks5h://...` with `trust_env=True` (default). The `socks5h://` scheme is confirmed supported by httpx's `_config.py` (`"socks5h" in valid schemes`). Requires `pip install httpx[socks]` (pulls in `socksio==1.*`).

**SSH server (Hermes) behavior with socks5h:** When the SOCKS5 client sends a hostname (not a pre-resolved IP) in the CONNECT request (which `socks5h://` does), OpenSSH's built-in SOCKS server resolves the hostname on the Hermes side using Hermes' DNS. Hermes is on a home network with unrestricted Google egress — resolution and connection proceed normally. This is standard SOCKS5 domain-type (`0x03`) connect behavior.

**Prerequisites:**
- `pip install httpx[socks]` (adds socksio; no other deps)
- SSH key-based auth from Aliyun to Hermes already configured (verified in memory: hermes_ssh.md)
- systemd unit on Aliyun to keep tunnel alive (autossh or `Restart=always`)

**Hermes-side cost:** zero. No additional services needed. OpenSSH already running.

---

### Option B: HTTP CONNECT proxy on Hermes + SSH -L tunnel

**How:** tinyproxy on Hermes (1 apt install) + `ssh -L <aliyun_port>:localhost:<hermes_proxy_port>` + `HTTPS_PROXY=http://127.0.0.1:<aliyun_port>`.

**google-auth SA token refresh:** SUPPORTED. requests picks up `HTTPS_PROXY`.

**google-genai httpx:** SUPPORTED. httpx reads `HTTPS_PROXY` without extra packages (HTTP CONNECT is native httpx support).

**Why Option B is worse than Option A:**
- Requires tinyproxy installed on Hermes (`apt install tinyproxy`, config edit to allow 127.0.0.1 only)
- HTTP CONNECT proxies require the server to accept connections to any HTTPS port — tinyproxy's ACL must be configured or it defaults to only port 443/8080 (need to check if Vertex API uses port 443 — yes, but still extra config step)
- `/etc/hosts` pin still interferes (see Item 4) — client resolves hostname before CONNECT, pin routes to wrong IP
- Two layered TCP connections (L-forwarded port → tinyproxy → real target) vs one (SOCKS5 direct)

---

### Option C: gcloud REST with custom auth (rejected)

Too invasive — requires rewriting all genai.Client() constructors. Out of scope.

---

## Item 4: /etc/hosts pin interference

**Verdict: MUST REMOVE existing /etc/hosts pins before deploying Option A with socks5h://**

The `aliyun_oauth_pin.md` memory documents these pins were added to work around the IPv6 gap when WireGuard was healthy:
```
142.250.73.106 oauth2.googleapis.com
142.250.73.106 aiplatform.googleapis.com
142.250.73.106 us-central1-aiplatform.googleapis.com
```

**With socks5h:// (remote DNS, RECOMMENDED):** When a Python client sets `ALL_PROXY=socks5h://127.0.0.1:18080` and opens a connection to `oauth2.googleapis.com`, the httpx/requests SOCKS5 client sends the hostname string directly to the SSH SOCKS server WITHOUT performing local DNS lookup first. The `/etc/hosts` file is NOT consulted because no local DNS lookup occurs. **No interference — pins are bypassed.**

**With socks5:// (local DNS, AVOID):** Client resolves `oauth2.googleapis.com` locally FIRST using `/etc/hosts` → gets `142.250.73.106` (the pinned anycast IP). Client then sends the IP (not the hostname) in the SOCKS5 CONNECT. SSH server on Hermes connects to `142.250.73.106` — this may work since that IP is an actual Google anycast address, but it bypasses Hermes' DNS entirely and could break if the IP changes. **Unreliable — avoid.**

**With Option B (HTTP CONNECT proxy):** Client resolves hostname locally using `/etc/hosts` before sending CONNECT. The pinned IP `142.250.73.106` is sent as the CONNECT target. The Hermes tinyproxy then connects to that IP directly. This may actually work since the IP is valid, but it depends on the pin staying accurate. **Fragile — avoid.**

**Action required before deploying any tunnel option:** remove the three `/etc/hosts` lines on Aliyun. The pins were a workaround for the direct-routing path when WireGuard worked; the tunnel renders them both irrelevant and potentially harmful (socks5:// local-DNS path). They have no value once a proxy is in place.

Verify current pin state:
```bash
grep -E "oauth2|aiplatform" /etc/hosts
```

---

## Recommended Option: A (ssh -D SOCKS5 with socks5h)

### Prerequisites checklist

| Step | Command | Notes |
|------|---------|-------|
| 1. Install httpx[socks] on Aliyun venv | `venv/bin/pip install "httpx[socks]"` | Adds socksio==1.x; google-genai already has httpx |
| 2. Verify SSH key auth Aliyun → Hermes | `ssh -p <hermes_port> <user>@<hermes_host> echo ok` | Should not prompt for password |
| 3. Remove /etc/hosts Google pins | `grep -E "oauth2\|aiplatform" /etc/hosts` then remove lines | Critical — see Item 4 |
| 4. Set ALL_PROXY in /root/.hermes/.env | `ALL_PROXY=socks5h://127.0.0.1:18080` | 18080 is arbitrary; pick any free port |
| 5. Create tunnel systemd unit | See unit below | Keeps tunnel alive across ingest |

**Tunnel systemd unit for Aliyun:**
```ini
[Unit]
Description=SSH SOCKS5 egress proxy to Hermes
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=accept-new \
  -N -D 127.0.0.1:18080 \
  -p <HERMES_SSH_PORT> <HERMES_USER>@<HERMES_HOST>
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Smoke verification (after tunnel up + .env reloaded):**
```bash
# Test SA token refresh path
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -x socks5h://127.0.0.1:18080 \
  https://oauth2.googleapis.com/token
# Expected: 400 (POST required) or 404, <2s — NOT timeout

# Test aiplatform reach
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -x socks5h://127.0.0.1:18080 \
  https://aiplatform.googleapis.com/
# Expected: 404 or 401, <2s

# Test Python SDK via env (after venv activate + source .env)
python3 -c "
import os; os.environ['ALL_PROXY']='socks5h://127.0.0.1:18080'
from google.auth import default
creds, proj = default()
creds.refresh(__import__('google.auth.transport.requests', fromlist=['Request']).Request())
print('token ok:', creds.token[:20])
"
```

---

## Common Pitfalls

### Pitfall 1: socks5:// vs socks5h:// confusion
**What goes wrong:** Using `socks5://` causes Aliyun to resolve the hostname locally first, hitting the dead WireGuard route OR the /etc/hosts pin. The connection fails with the same timeout as before despite the tunnel being up.
**Prevention:** Always use `socks5h://` (remote DNS).

### Pitfall 2: /etc/hosts pins not removed
**What goes wrong:** With socks5:// (or if some code path bypasses the proxy), the pinned IP `142.250.73.106` routes to a Google anycast IP but not necessarily via Hermes — it may still try to route via the dead WireGuard tunnel.
**Prevention:** Remove the three Google pins from /etc/hosts before testing. Hermes' DNS will resolve Google addresses correctly.

### Pitfall 3: httpx[socks] not installed
**What goes wrong:** httpx raises `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed` at first proxy-routed call. The error surfaces deep inside LightRAG's async embedding worker, possibly as an opaque `TransportError`.
**Prevention:** `pip install httpx[socks]` before testing.

### Pitfall 4: SSH tunnel drops silently
**What goes wrong:** The SSH tunnel process exits (idle timeout, network hiccup); the port 18080 stays bound briefly then disappears. Next LightRAG embed call fails with `Connection refused` on 127.0.0.1:18080.
**Prevention:** Use the systemd unit with `Restart=always` + `ServerAliveInterval=30`. Also add `ExitOnForwardFailure=yes` so SSH exits (and systemd restarts it) rather than hanging with a bound-but-dead socket.

### Pitfall 5: KB_SYNTHESIZE_TIMEOUT revert forgotten
**What goes wrong:** After the tunnel is up and embedding recovers, the `KB_SYNTHESIZE_TIMEOUT=30` temp-lowering (deployed as mitigation during the outage) cuts real KG synthesis at 30s and returns FTS fallback even when LightRAG returns results.
**Prevention:** After embedding smoke passes, revert `KB_SYNTHESIZE_TIMEOUT` back to 240 in the Aliyun kb-api override.conf. Restart kb-api.

### Pitfall 6: ALL_PROXY affects ALL outbound traffic including DeepSeek
**What goes wrong:** `ALL_PROXY` routes ALL Python requests through Hermes, including DeepSeek API calls. If DeepSeek is accessible directly from Aliyun (it is — ISSUES.md confirms CN egress fine), routing it through Hermes adds latency and may break if Hermes' home network can't reach DeepSeek.
**Mitigation:** Set `NO_PROXY=api.deepseek.com,siliconflow.cn,localhost,127.0.0.1` alongside `ALL_PROXY`. This exempts DeepSeek and SiliconFlow from the proxy, routing only Google-domain traffic through Hermes.

---

## Environment Availability

| Dependency | Available on Aliyun | Available on Hermes | Notes |
|------------|---------------------|---------------------|-------|
| OpenSSH server | ✓ | ✓ (required as SOCKS server) | SSH already used for ops |
| SSH key auth Aliyun→Hermes | ✓ (memory: hermes_ssh.md) | ✓ | Hermes SSH port in memory file |
| httpx[socks] / socksio | ✗ (not in requirements.txt) | N/A | Install: `pip install httpx[socks]` on Aliyun venv |
| tinyproxy (Option B only) | N/A | ✗ | Would need apt install — not needed for Option A |
| Aliyun systemd (for tunnel unit) | ✓ | N/A | Aliyun already uses systemd for ingest/kb-api |

---

## Sources

### Primary (HIGH confidence)
- google-auth-library-python GitHub: `google/auth/transport/requests.py` — `requests.Session()` no `trust_env=False` → inherits env proxy vars
- google-genai PyPI `2.10.0` metadata: `httpx>=0.28.1` dependency confirmed; gRPC absent
- google/genai/_api_client.py GitHub: pure REST over httpx (`SyncHttpxClient` / `AsyncHttpxClient`), no grpc import
- httpx docs (python-httpx.org/environment_variables): `trust_env=True` default; `HTTPS_PROXY`/`ALL_PROXY` respected
- httpx _config.py GitHub: `socks5h` explicitly listed as valid proxy scheme
- httpx PyPI: `httpx[socks]` extra requires `socksio==1.*`
- SOCKS5 protocol spec: domain-type (0x03) CONNECT sends hostname; remote server resolves — this is what `socks5h` triggers

### Secondary (MEDIUM confidence)
- requests docs (python-requests.org/advanced): `socks5h://` documented for remote DNS
- python-httpx.org/advanced/proxies: `socks5://` and `socks5h://` both supported with `httpx[socks]`

---

## Confidence breakdown

| Area | Level | Reason |
|------|-------|--------|
| google-auth proxy via requests | HIGH | Source code verified: `requests.Session()` default `trust_env=True` |
| google-genai transport (REST not gRPC) | HIGH | Source code + PyPI deps confirmed: httpx, no grpc |
| httpx socks5h proxy env var support | HIGH | httpx docs + _config.py source |
| ssh -D + socks5h remote DNS | HIGH | Standard SOCKS5 protocol: domain-type connect; SSH implements this |
| /etc/hosts pin interference analysis | HIGH | socks5h bypasses local DNS → pins irrelevant; socks5 consults pins |
| NO_PROXY exemption for DeepSeek | HIGH | Standard requests/httpx NO_PROXY behavior |
