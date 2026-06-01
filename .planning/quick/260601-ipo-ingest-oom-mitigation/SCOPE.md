# 260601-ipo — Aliyun ingest OOM mitigation

**Started:** 2026-06-01 12:05 ADT (15:05 UTC)
**Tier:** `/gsd:quick` (~50-80 LoC, 2 commits, < 1h end-to-end)
**Goal:** stop Aliyun ingest services from OOM-killing the host (4 OOM-kills / 24h, anon-rss peak 11 GB on 15 GB ECS).

## Diagnostic findings (Phase 0)

OOM frequency (last 24h, all `omnigraph-*-ingest.service`):

| Time (CST) | Service | anon-rss peak |
|---|---|---|
| 06-01 06:52 | evening-ingest | 11.05 GB |
| 06-01 08:21 | daily-ingest | 10.91 GB |
| 06-01 14:31 | afternoon-ingest | 11.00 GB |
| 06-01 20:39 | daily-ingest | 10.99 GB |

Root causes:

1. **No systemd memory cap** — all 3 services have `MemoryMax=infinity MemoryHigh=infinity OOMScoreAdjust=0 Restart=no`.
2. **No mutual exclusion** — 3 ingest services run on overlapping windows (UTC 00:00 / 06:00 / 12:00); when a long article keeps `daily-ingest` running ~19h, it overlaps with `evening-ingest` next cron → 2× RAM = OOM.
3. **LightRAG worker over-concurrency** — `ingest_wechat.py:401-404` sets `llm_model_max_async=4 / embedding_func_max_async=4 / max_parallel_insert=3`; each worker holds vdb context (~1-2 GB each for 31776×3072-dim entities + relationships + chunks).
4. **No mid-batch GC** — Python doesn't reclaim freed vdb pages between articles.
5. **Aliyun is all-in-one** — 15 GB ECS hosts vitaclaw-stack (15+ bun procs, postgres, docker), kb-api, ingest. Ingest peak crowds everything else.

Note: `OMNIGRAPH_BATCH_TIMEOUT_SEC` + per-article `asyncio.wait_for` (Phase 17 BTIMEOUT, shipped 2026-05-17) are **already wired** — `_SINGLE_CHUNK_FLOOR_S=1200s` floor + chunk + image budget. ISSUES.md #4 ("8h+ no upper bound") is **stale** and gets closed by this quick.

## Out of scope

- LightRAG → Qdrant migration (separate path, doc in flight by user)
- Per-article ainsert timeout addition (already shipped Phase 17)
- ARAG / wiki / kb-api work (separate sessions)

## Plan

### (a) systemd hardening — 3 unit files

For each of `omnigraph-{daily,afternoon,evening}-ingest.service`:

```
[Service]
MemoryMax=4G                    # SIGKILL hard ceiling
MemoryHigh=3G                   # soft pressure → kernel reclaim before kill
OOMScoreAdjust=500              # ingest dies first if global OOM hits
Restart=on-failure              # auto-recover next checkpoint resume
RestartSec=10min                # cool-down before retry
[Unit]
Conflicts=omnigraph-afternoon-ingest.service omnigraph-evening-ingest.service   # adjust per service
```

`Conflicts=` ensures only ONE ingest runs at a time. If two timers fire close together, the later activation kills the earlier — but at the per-article boundary the running batch finishes its current article via checkpoint, then the new batch picks up resume.

### (b) LightRAG RAM-mitigation — `ingest_wechat.py`

```python
embedding_func_max_async=4 → 2     # halve embedding worker fanout
llm_model_max_async=4 → 2          # halve LLM extraction fanout
max_parallel_insert=3 → 2          # halve insert fanout
```

Plus, at end of `ingest_article()` in `batch_ingest_from_spider.py` (per-article boundary):

```python
import gc
gc.collect()                       # force reclaim of vdb / chunk / entity dicts
```

Estimated peak RAM reduction: 11 GB → 5-6 GB per active ingest. With (a) MemoryMax=4G on top, services SIGKILL themselves at 4G before crowding kb-api / vitaclaw stack.

### (c) ISSUES.md cleanup

- Close #4 (`260530-ainsert-budget-timeout`) — already shipped Phase 17 BTIMEOUT.
- Add new row for residual: "Aliyun all-in-one + LightRAG nano-vectordb full-load, structural fix is Qdrant migration".

## Success criteria

1. 3 systemd unit files have `MemoryMax=4G` + `Conflicts=` and `daemon-reload` succeeds.
2. `ingest_wechat.py` LightRAG max_async = 2; `gc.collect()` called at end of `ingest_article`.
3. Next cron (Tue 2026-06-02 06:00 UTC `afternoon-ingest`) completes WITHOUT `oom-kill` log; OR if it OOMs, only ingest service dies (kb-api stays up; verify `curl 127.0.0.1:8766/health` after).
4. Commit + push (no force, explicit git add).
5. `journalctl -u omnigraph-afternoon-ingest --since=cron-time` shows `Restart=on-failure` recovery if it fails once.

## Constraints honoured

- PRINCIPLE #5: SSH self-run, never outsource to user.
- PRINCIPLE #7: Aliyun systemd / code edits go through git, not direct prod hand-edit.
- PRINCIPLE #9: no `kb/static/` or `kb/templates/` touched.
- No conflict with P2-3-perf-fix-B (other session) — B touches `lib/llm_rerank.py` + `lib/vertex_gemini_rerank.py` + kb-api.service, this quick touches `ingest_wechat.py` + `omnigraph-*-ingest.service`.
- Hermes RO until 2026-06-22 — only Aliyun touched.
- No `git commit --amend`, no `--force`, no `git add -A`.
