# 260710-health-audit SUMMARY

**Quick ID:** 260710-u67 · **Date:** 2026-07-11 · **Mode:** read-only investigation (no planner/executor spawn — goal prompt was the plan; Principle #8 right-sizing)

## What was done

Independent verification of user's claim "ingestion pipeline restored after manual Aliyun ops". Four-layer read-only audit over SSH `aliyun-vitaclaw`:

- **L1 drift:** 38 live systemd units diffed vs `deploy/aliyun/systemd/` — 33 identical; mcp-tunnel gained 9222/58932 forwards (Jul 10 21:22, the user's ops); daily-digest ExecStart repurposed to vitaclaw agent-news (old drift); translate units + 2 ingest overrides live-only; `vertex-proxy-env.conf` orphan; Aliyun git carries cb42271 as uncommitted hot-patch (byte-identical to GitHub) with stale origin ref.
- **L2 deps:** WG fresh handshake + Google 404@0.23s via tunnel + EMBED OK dim=3072 + DeepSeek ok + Qdrant up (unless-stopped). FAIL: SiliconFlow balance **-58.37 CNY**; qdrant-snapshot timer **dead since Jun 17 rebuild** (last run Jun 6, Path X self-heal offline). WARN: mcp-tunnel Mac-side flap (85–1346 restarts/day); Vertex 429 storms (retry-recoverable); disk 84%.
- **L3 data:** layer1 NULL 194→44 (all Apr/May fossils); 402-storm layer2 NULLs cleared (33 = 25 fossils + 8 in-flight today); ingest ok 7/11=5 (first post-fix run, cut by 1h RuntimeMaxSec by design); graphml 39,909n/58,634e growing; "backlog 267" is accounting artifact — 198 are `skipped_ingested` (already in KG), real backlog ~60-70, ~2-3 days to drain; translate 97% coverage healthy; rewrite 54% with **no automation hook**; WeChat session ret=0 after 06:19 cookie refresh.
- **L4 verdict:** **claim substantiated** — root causes were WeChat session expiry (Jul 10) + Vertex gemini-3.1-flash-lite-preview 404 killing Layer1 (fixed by DeepSeek switch cb42271, verified live 08:00 CST run: 219 candidates, 0 nulls, 5 ingested).

## Deliverables

- `REPORT.md` (this dir) — full evidence, PASS/WARN/FAIL per layer, 2🔴+4🟡+2🔵 findings, 5 rows drafted for ISSUES.md transcription
- Raw dumps: `.scratch/260710-health-audit/{live-units-dump.txt,unit-diff-report.txt}` (untracked)

## Discipline

Zero writes on Aliyun; zero systemctl mutations; sqlite `mode=ro`; git pull-only. ISSUES.md rows drafted, NOT edited (orchestrator transcription pending user ack).
