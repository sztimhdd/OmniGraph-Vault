# Quick Task 260707-k6f — SUMMARY

**Status:** CLOSED (Phase 1 of conservative phased rollback)
**Date:** 2026-07-07 (Aliyun clock 2026-07-08 CST; ~11h ahead of dev ADT)
**Goal:** Retire the #75 SOCKS5 vertex-proxy B-mitigation at the runtime/ops layer now that WG `wg-gcp-sg` is empirically confirmed repaired (#76 trigger met). Leave code + systemd `Wants=` in place for a 1-week observation window.

---

## What actually happened (differs from the pre-written plan — read this)

Before mutating anything I inspected live Aliyun state. Two of the planned steps were **already done by a prior session** and one was **intentionally skipped** as surgical:

| Planned step | Reality found | Action taken |
|---|---|---|
| Backup `.env` | — | ✅ `cp -p` → `/root/.hermes/.env.bak-pre-rollback-260707` (2754 B, byte-identical) |
| Remove `OMNIGRAPH_EMBED_PROXY` from `.env` | **Already ABSENT** — grep + diff vs `.env.bak-pre-socks5-260630` show it's in neither file. `.env` mtime = 2026-07-07 21:44 CST (~4h before this quick); DeepSeek key also rotated (`sk-06d8…`→`sk-a8b6…`) — matches prior session's "新Key请替换" + proxy-var cleanup. | ✅ No-op (verified absent). `NO_PROXY` kept (harmless DeepSeek/SiliconFlow bypass). |
| `disable --now omnigraph-vertex-proxy.service` | Service was `active` but already `enabled=disabled`; resurrected 22:00 CST by a timer-ingest `Wants=`. | ✅ `disable --now` → `active=inactive`, `enabled=disabled`, port 18080 unbound, **unit file preserved** on disk. |
| Restart 5 ingest/classify services | All 5 `inactive` (timer-triggered oneshots, not long-running). The **00:00 CST cron already ran direct with no proxy** and succeeded. | ⏭️ **Intentionally skipped** — restarting a timer oneshot = an unscheduled ingest run (unwanted side effect + WeChat throttle cost). They already read clean env. Plan pre-authorized this hedge. |

### Production already proved direct-WG works (stronger than a smoke probe)

The `omnigraph-daily-ingest` cron at **00:00 CST 2026-07-08 ran a full clean cycle with NO proxy**:
- layer1 batches 1-9 all `null=0` (one transient `ClientError` batch 8, self-recovered next batch)
- layer2 `ok=5`
- graphml grew to **38545 nodes / 56314 edges**, vdb flushed
- zero `ConnectTimeout` / `TransportError oauth2`

### Post-rollback verification (proxy fully DOWN)

With `omnigraph-vertex-proxy.service` stopped + port 18080 unbound + `OMNIGRAPH_EMBED_PROXY` sourced as empty:
```
OMNIGRAPH_EMBED_PROXY sourced as: [<empty/unset>]
EMBED OK dim=3072
18080 still unbound ✓
```
→ Embedding is unambiguously going direct via the WG tunnel; the proxy is no longer a dependency.

---

## WG repair evidence (the #76 trigger, gathered earlier this session, read-only)

| Criterion | Evidence |
|---|---|
| WG handshake < 30s | `wg show wg-gcp-sg` → `latest handshake: 10s ago` after forced tunnel traffic; transfer 857 KiB recv / 1.44 MiB sent, growing |
| TCP:443 direct non-timeout | `curl -4 https://oauth2.googleapis.com/token` → `404 0.57s remote=74.125.20.95` |
| Google IP routes THROUGH tunnel | `ip route get 74.125.195.95` → `dev wg-gcp-sg src 10.0.0.2` |

**IPv6 trap excluded:** oauth2/aiplatform resolve to IPv6 by default but host has NO IPv6 egress (`curl -6` → `000`). Bare `curl` 404 was IPv4 happy-eyeballs fallback — always force `curl -4` + check `ip route`. Recorded in memory `wg_gcp_sg_repaired_260707`.

---

## Deferred to a follow-up quick (after ~1 week sustained stability)

1. Delete `_make_client()` proxy-injection code in `lib/lightrag_embedding.py` + `lib/vertex_gemini_complete.py` (auto-no-ops while `OMNIGRAPH_EMBED_PROXY` unset — safe to leave now).
2. Remove `Wants=/After=omnigraph-vertex-proxy.service` from the 5 unit files (`daily-ingest`, `afternoon-ingest`, `evening-ingest`, `kol-classify`, `rss-layer2-classify`) — this is what resurrects the disabled service at each timer fire.
3. Optionally delete `/etc/systemd/system/omnigraph-vertex-proxy.service`.

**Why deferred:** conservative observation window (user-approved 2026-07-07). Proxy unit preserved so re-enable is a one-liner if WG destabilizes.

## Rollback-the-rollback (unused — Task 2 passed)

`ssh aliyun-vitaclaw 'cp /root/.hermes/.env.bak-pre-rollback-260707 /root/.hermes/.env && systemctl enable --now omnigraph-vertex-proxy.service'`

---

## Files/commits

- No code changed (Phase 1 is ops + docs only).
- Docs: `.planning/ISSUES.md` (#76 Phase-1 done + cleanup deferred; #75 WG repaired), `.planning/STATE.md` (Quick Tasks row).
- Aliyun state: proxy disabled+stopped, unit preserved, `.env` backup `/root/.hermes/.env.bak-pre-rollback-260707`.
