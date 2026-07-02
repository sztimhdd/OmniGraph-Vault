# 260702-ep6 SUMMARY — Switch vertex-proxy exit: Hermes → GCP Singapore VM

**Status:** CLOSED  
**Date:** 2026-07-02  
**Commits:** `679b67d` (proxy target switch), `7178fd1` (ops hardening + dependency wiring)

---

## What Changed

### Root trigger
`omnigraph-vertex-proxy.service` had been tunneling through `ohca.ddns.net:49221` (Hermes). Hermes went down 2026-07-01 ~08:52. The proxy unit entered a restart storm: 10149 restarts over ~24h due to `StartLimitIntervalSec=0` misplaced in `[Service]` (no rate limiting). The service was manually stopped.

### Solution
Switched SSH tunnel exit from Hermes to the GCP Singapore VM (`35.198.243.36`, user `huhai_orion`), which is the WireGuard peer already in the topology. TCP:22 to this host is reachable from Aliyun even under the ACK NetworkPolicy that blocks WireGuard UDP + TCP:443.

### Files modified
| File | Change |
|------|--------|
| `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` | ExecStart target: `hermes` → `huhai_orion@35.198.243.36 -i /root/.ssh/id_ed25519`; `StartLimitIntervalSec=0` moved from `[Service]` to `[Unit]`; `RestartSec=10→30`; Description de-TEMPORARY'd |
| `deploy/aliyun/systemd/omnigraph-daily-ingest.service` | Added `After=+Wants=omnigraph-vertex-proxy.service` |
| `deploy/aliyun/systemd/omnigraph-afternoon-ingest.service` | Same |
| `deploy/aliyun/systemd/omnigraph-evening-ingest.service` | Same |
| `deploy/aliyun/systemd/omnigraph-kol-classify.service` | Same |
| `deploy/aliyun/systemd/omnigraph-rss-layer2-classify.service` | Same |

### Dependency ordering rationale
`Wants=` (not `Requires=`) — proxy is preferred but ingest is not blocked if proxy briefly reconnects. `After=` ensures systemd starts the proxy first. This is belt-and-suspenders only; the embedding code already handles `OMNIGRAPH_EMBED_PROXY` absent or unreachable via httpx fallback.

---

## Verification (Aliyun live)

```
=== proxy ===
active (running)
LISTEN 0 128  127.0.0.1:18080  0.0.0.0:*  users:(("ssh",pid=2435167,fd=4))

=== embed smoke ===
EMBED OK dim=3072

=== dependency check ===
omnigraph-daily-ingest After=... omnigraph-vertex-proxy.service ✓
omnigraph-kol-classify After=omnigraph-vertex-proxy.service ✓
```

---

## Key decisions

| Decision | Why |
|----------|-----|
| GCP VM (35.198.243.36) not Hermes | TCP:22 reachable through ACK NetworkPolicy; GCP Singapore → Google global endpoint is near-zero latency; no dependency on home network |
| `Wants=` not `Requires=` | Proxy restart ~30s; don't block 3-hour ingest over a 30s gap |
| `StartLimitIntervalSec=0` to `[Unit]` | `[Service]` placement was silently no-op AND was the root cause of the Hermes-down 10149-restart storm |
| B-mitigation is now PERMANENT DEFAULT | IT fixing ACK NetworkPolicy is still pending but deprioritized; GCP-VM path has no Hermes-availability dependency |

---

## Out-of-scope / open issues

- **#75 ACK NetworkPolicy** — IT still handling the root fix. When fixed, rollback procedure in `260630-jgx-DECISION.md` + #76. Updated #75 row to reflect GCP-VM as exit point.
- **#76 rollback trigger** — unchanged (same trigger: `wg show wg-gcp-sg latest-handshake < 30s AND curl oauth2 returns 400`). Rollback steps updated to include disabling proxy unit.
- **Layer1 NULL backlog** (~194 articles as of 2026-07-01) — will drain automatically on next cron run now that proxy is live.
