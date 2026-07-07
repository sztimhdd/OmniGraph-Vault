# Quick Task 260707-l9g — SUMMARY

**Status:** CLOSED
**Date:** 2026-07-07 (Aliyun clock 2026-07-08 CST)
**Commit:** `5cf19c8` (code+units, pushed origin/main) + docs commit (this close)
**Verified by:** adversarial workflow `wf_67c73b79-5e3` (3 skeptics + synthesizer, 451k tokens)
**Follows:** 260707-k6f (Phase-1 rollback — proxy already disabled+stopped)

Phase-2 of the #75 SOCKS5 vertex-proxy retirement + P2 mcp-tunnel restart-storm fix. User overrode the 1-week observation window ("直接在本session跑").

---

## The workflow caught 3 things the naive plan got wrong

1. **The ep6 #75 systemd fix was BACKWARDS.** `StartLimitIntervalSec=0` DISABLES the rate limiter (retry forever) and is a `[Unit]` directive (silently ignored in `[Service]`, systemd ≥v230) — independently confirmed vs systemd docs. So "move 0 to [Unit] to stop a storm" is self-contradictory. The ep6 storm actually ended when Hermes became reachable, not the directive move. → P2 correct fix = keep limiter OFF (self-heals) + `RestartSec=300` (30× flood cut). Rejected Option A (`StartLimitBurst`) — its sticky `failed` state would leave the WeChat-scrape #3 fallback silently dead.
2. **B1 — repo systemd units are DRIFTED from Aliyun live** (#68 every-2h consolidation, live-only `override.conf` with `RuntimeMaxSec` guarding the #45 asyncio-hang). `cp repo→/etc` FORBIDDEN → edited live files in-place + enumerated via `grep -l`.
3. **Preserve `network-online.target`** when stripping — a whole-line `sed` delete would drop it → cold-boot ingest before network → ConnectTimeout.

## P1 — proxy code deletion (VERDICT: SAFE, zero runtime delta — confirmed in prod)

- `lib/lightrag_embedding.py` `_make_client()`: deleted `proxy_url=...` + `if proxy_url:` block + 260630-jgx docstring paragraph. Final = `http_options = None` → `genai.Client(..., http_options=None)`.
- `lib/vertex_gemini_complete.py` `_make_client()`: same.
- `lib/vertex_gemini_rerank.py`: untouched (separate proxy-free `_make_client`).
- **Local:** 36 embedding/vertex tests green (== baseline), rerank 6 green, imports OK.
- **Aliyun (SCP'd — git fetch 443-blocked):** proxy refs = 0 0; `git diff --stat` = only 2 files, 71 deletions; `import lib.lightrag_embedding, lib.vertex_gemini_complete` OK on venv-aim1; **post-deploy `EMBED OK dim=3072`** with the code deleted → the deletion is a proven no-op (prod `.env` had no `OMNIGRAPH_EMBED_PROXY`, so the block was already dead).

## P1 — systemd units

- 5 live units (`daily/afternoon/evening-ingest`, `kol-classify`, `rss-layer2-classify`) — stripped ` omnigraph-vertex-proxy.service` from `After=`/`Wants=` in-place (backups `.bak-pre-l9g-260707`), preserving `network-online.target`.
- `/etc/systemd/system/omnigraph-vertex-proxy.service` — backed up to `/root/omnigraph-vertex-proxy.service.bak-pre-l9g-260707`, then `rm`'d. `git rm` in repo.
- Verified: `systemctl show <ingest> -p After/Wants` → no vertex-proxy, network-online present. `systemctl status omnigraph-vertex-proxy` → `not-found` (no dangling deps).

## P2 — mcp-tunnel restart storm (NRestarts was 5087, journal 3.8G, disk 84%)

- Root: `ExecStart` tunnels to `hermes` (→ `localhost:49221`); Hermes down since ~07-01 → ssh exits 255; `RestartSec=10` + no effective limiter = ~8640 restarts/day flooding journal.
- Fix (live unit overwritten, backup `.bak-pre-l9g-260707`): moved `StartLimitIntervalSec=0` `[Service]`→`[Unit]` (correct section) + `RestartSec` 10→300.
- Verified: `StartLimitIntervalUSec=0`, `RestartUSec=300000000` (5min), `NRestarts=0`, state `activating/auto-restart` — ONE attempt at 02:29:54 then waiting 300s (vs ~18 in the same window before). Self-heals within 5 min when Hermes returns (no sticky failed-state). Flood stopped.

## Deploy discipline honored

- B1: live units edited in-place, enumerated via `grep -l`, NEVER `cp repo→/etc`.
- B2: lib files deployed via SCP (git fetch cross-border 443-blocked, per R38-R40), never bare `git pull`.
- B3: ONLY mcp-tunnel restarted; NO ingest unit restart (mid-batch SIGTERM = graphml corruption per `systemd_schedule_overlap_sigterm_corruption`; they adopt edits on next timer fire); NO kb-api restart (#27 hydrate-throttle risk).
- Git: encountered real branch divergence (origin +6 commits from Mac/Aliyun sync, 07-05/06). **Zero file overlap** with my 11 local commits → clean `git rebase origin/main` (14/14, no conflicts), re-verified P1 edits survived, pushed `6a16e56..5cf19c8`. No force-push, no `--amend`.

## Backups / rollback

- Aliyun: 5× `/etc/systemd/system/<unit>.service.bak-pre-l9g-260707`, mcp-tunnel `.bak-pre-l9g-260707`, proxy unit `/root/omnigraph-vertex-proxy.service.bak-pre-l9g-260707`, `.env` backup from k6f still present.
- Repo: `git revert 5cf19c8` restores proxy code + unit if WG ever destabilizes.

## Issue tracker

- **#76 CLOSED** (rollback complete: Phase-1 k6f + Phase-2 l9g).
- **#75 downgraded** (WG repaired + B-mitigation fully retired; code+units+unit-file all gone).
- **New mcp-tunnel row** filed + RESOLVED (restart-storm fix; same StartLimitIntervalSec-family as #75).
