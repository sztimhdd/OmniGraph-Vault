# PLAN (FINAL, post-review) — Increase Aliyun ingest cron frequency to drain backlog

**Drafted:** 2026-06-24 ~21:50 CST · **Revised:** 2026-06-24 ~22:10 CST after adversarial subagent review
**Author:** orchestrator (Aliyun operator, Principle #5) · **Reviewer:** code-reviewer subagent (live-verified against box)
**Status:** FINAL → awaiting user go/no-go
**Type:** prod-ops, Aliyun systemd timer/service change. ZERO repo code edits (config-only). Forward-only.
**Review verdict:** APPROVE-WITH-CHANGES — all 6 revisions folded in below. 2 material factual errors in the draft were corrected (see "Corrections from review").

---

## Problem (evidence-based)

- 3 ingest services (`omnigraph-{daily,afternoon,evening}-ingest`) are the **same job** (byte-identical `ExecStart … --max-articles 5`; verified identical except `Description=` and the self-excluding `Conflicts=` list; the `override.conf` drop-in is the same 694-byte file on all three), fired 8h apart, mutually `Conflicts=`-exclusive.
- **Throughput < inflow → backlog grows.** Cron lands ~9-12 articles/day; KOL scan adds ~103/week ≈ 15/day. Backlog = 191 `layer2='ok'` not-yet-ingested, slowly rising.
- **Each run is bounded by `--max-articles 5` (an attempt cap)** — NOT the 8h budget (never used) and NOT landed-count. metrics show `not_started: 180-285` every run. Of 5 attempts, 1-4 land (scrape hit-rate ~1-5%: UA mostly fails on WeChat JS-render; Apify ~30% verification page; MCP tunnel fallback recovers a fraction).
- Scrape failures are **per-attempt random** → more frequent rounds = more independent retries on the same flaky pool = higher cumulative hit-rate. This is the lever frequency gives that a bigger batch cannot.

## Measured timing (last 24h, live)

| run (CST) | work elapsed | landed | note |
|---|---|---|---|
| 06-24 20:00 | 1274s (21m) | 2 | |
| 06-24 14:00 | 20s | 0 | empty |
| 06-24 08:00 | 26s | 1 | |
| 06-24 06:22 | 858s (15m) | 3 | this was a `Restart=on-failure` recovery of the killed 03:12 run — completed clean, no cascade |
| 06-24 03:12 | 34m work, **then hung 2h25m** | 2 | `Successfully finalized 12 storages` at 03:47, then silent hang until `RuntimeMaxSec=3h` SIGKILL at 06:12 |
| 06-23 23:29 | 1352s (23m) | 4 | |

- Worst **work** time: 34 min. **Worst service occupancy: up to the RuntimeMaxSec ceiling** because of the post-completion asyncio hang (memory `ingest_service_post_completion_asyncio_hang`) — which **fired once in the last 24h** (03:12 run), force-killed by the existing 3h ceiling.
- 8h batch budget never touched.

## Corrections from review (draft was wrong on these — do not regress)

1. **`RuntimeMaxSec` already exists live** at `10800` (3h) in `/etc/systemd/system/omnigraph-daily-ingest.service.d/override.conf` (resolved `RuntimeMaxUSec=3h`). The draft wrongly treated it as new. → We EDIT the existing value, not add a second.
2. **The asyncio hang DID occur in the last 24h** (03:12 run). The draft said "not seen in 24h." → occupancy sizing must assume the hang.
3. **Corruption-safety is real and verified:** the hang begins *after* `Successfully finalized 12 storages` — graphml is fully flushed before the hang/kill window. The patched `write_nx_graph` (`.tmp` → `fsync` → `os.replace`, verified in venv-aim1) makes the live `graph_chunk_entity_relation.graphml` atomically all-old-or-all-new under any SIGTERM/SIGKILL. Live graphml healthy (32056 nodes / 46605 edges, no stray `.tmp`). **A RuntimeMaxSec kill does NOT reintroduce the 6/7 corruption class.**
4. **Real re-entry vector is `Restart=on-failure`+`RestartSec=10min`, not the timer.** A RuntimeMaxSec kill → `Failed (timeout)` → one restart 10min later (verified 06:12 kill → 06:22 clean recovery). Single-instance-safe. Keep `Restart=on-failure`.

## Safety constraints (LOCKED — preserve)

1. **No concurrent ingest** (6/7 graphml corruption was schedule overlap). Guaranteed by CONSOLIDATING to one unit: a unit cannot conflict with itself, and `Type=simple` holds exactly one instance — a timer firing on an already-active unit is a verified no-op (systemd 249, `replace` start job satisfied without a 2nd instance). Invariant `RuntimeMaxSec (1h) < interval (2h)` guarantees a hung run is force-killed ~1h before the next fire.
2. **Atomic-write patch present** in venv-aim1 lightrag networkx_impl.py — keep untouched.
3. **Cost/quota tri-governor** (`MAX_ARTICLES`): keep per-round batch SMALL (5), raise frequency instead. Embedding uses dedicated Gemini keys (1000 RPD each, separate GCP projects) — isolated from vision quota. Small frequent bursts gentler on Vertex RPM than few large ones.

## Proposed change

**Frequency 3×/day → every 2h (12×/day). Keep `--max-articles 5`. Tighten the existing RuntimeMaxSec 3h→1h to bound the hang below the interval. Consolidate the 3 duplicate units into ONE timer+service.**

### Steps (all on Aliyun via `aliyun-vitaclaw`, read/verify then mutate)

**Step 0 — pre-flight snapshot (read-only):**
- Record chunks/ent/rel counts, `systemctl list-timers omnigraph-*`, and `systemctl show omnigraph-daily-ingest.service -p RuntimeMaxUSec -p Restart -p RestartUSec`.
- Copy the 3 `.service` + 3 `.timer` files AND the `override.conf` drop-in to `*.bak-pre-freq-260624` so rollback restores the exact 3h/on-failure/10min config.

**Step 1 — retime + tighten ceiling on the sole runner (`omnigraph-daily-ingest`):**
- `omnigraph-daily-ingest.timer`: set `OnCalendar=*-*-* 00/2:00:00 UTC` (every 2h), keep `Persistent=true`.
- In `omnigraph-daily-ingest.service.d/override.conf`: **change the existing `RuntimeMaxSec=10800` → `RuntimeMaxSec=3600`** (60min; > 34min worst work, < 2h interval). Keep `TimeoutStopSec=300` and the Qdrant env lines unchanged. Do NOT add a second RuntimeMaxSec line.
- Leave `Conflicts=`, `TimeoutStartSec=300`, `Restart=on-failure`, `RestartSec=10min`, `ExecStartPre` cleanup, `--max-articles 5` all unchanged.

**Step 2 — disable the two redundant timers (consolidate):**
- `systemctl disable --now omnigraph-afternoon-ingest.timer omnigraph-evening-ingest.timer`
- Leave their `.service`+`.bak` files on disk (rollback). They cannot fire without a timer.

**Step 3 — daemon-reload + enable:**
- `systemctl daemon-reload; systemctl enable --now omnigraph-daily-ingest.timer`
- `systemctl list-timers omnigraph-*` → confirm ONLY the 2h timer scheduled, next fire ≤ 2h.
- `systemctl show omnigraph-daily-ingest.service -p RuntimeMaxUSec` → confirm resolves to `1h` and is strictly < the 2h interval.

**Step 4 — verify (Principle #6, observe ≥2 real fires over ~4-5h):**
- Each fire `Deactivated successfully` (or `Failed (timeout)` → exactly ONE `Restart=on-failure` recovery that then completes clean).
- **Corruption guard:** after any RuntimeMaxSec kill, graphml node/edge count is non-decreasing and there is NO stray `*.graphml.tmp` sibling.
- **No overlap:** never two ingest instances `active` at once (`systemctl show -p ActiveState` sampled across a fire boundary).
- No `Connection refused`; chunks count rising.
- After ~24h: landed/day ~24-36 (vs ~9-12), backlog trending DOWN.

**Step 5 — version-control:**
- Copy final `omnigraph-daily-ingest.{timer,service}` + `override.conf` to repo `deploy/aliyun/systemd/`, commit forward-only.

## Expected outcome

- 12 rounds/day × ~2-3 landed ≈ **24-36 articles/day** > 15/day inflow → 191 backlog drains in ~1 week, then stays caught up. (On hang days, a RuntimeMaxSec kill + 1 restart ≈ 13-14 effective runs — still bounded.)
- Cost worst-case 12×5×¥0.04 ≈ ¥2.4/day (~¥72/mo) vision; realistic ~¥1-1.5/day. ~2.4× current Apify spend. Embedding RPM safer than larger batches. Gemini-fallback rate scales ~4× but stays far under 500 RPD at observed volumes.

## Rollback

`*.bak-pre-freq-260624` (units + override.conf) restore 3×/day + 3h ceiling; `daemon-reload` + re-enable the 3 timers. Fully reversible, no data touched.

## Reviewer's note worth surfacing to user

The post-completion asyncio hang is itself the biggest throughput/cost waster: today a 34min job holds the slot ~3h (the old ceiling). **Tightening RuntimeMaxSec 3h→1h alone recovers most of the wasted wall-clock even without raising frequency.** Frequency-up + tighter-ceiling together is the stronger play (this plan), but if you want the most conservative first step, the ceiling tighten alone is a cheaper lever. (Recommendation: do both, as planned.)

## Out-of-scope issue surfaced by review (file to ISSUES.md, not this change)

`vitaclaw-site.service` is crash-looping (restartCount≈397, `Failed (exit-code)` every ~5s) — flooding journald + restart churn. Unrelated to ingest. Should be filed as a separate P-row. **RESOLVED 2026-06-24 (ISSUES #67, user-authorized disable).**

---

## EXECUTION RESULT — 2026-06-24 ~22:15 CST (DONE)

All 5 steps executed by orchestrator (Aliyun operator, read→verify→mutate). Forward-only.

- **Step 0:** baseline chunks=3851/ent=59191/rel=82582; confirmed live `RuntimeMaxUSec=3h` (reviewer was right); daily-ingest inactive; 7 `.bak-pre-freq-260624` backups taken.
- **Step 1:** daily.timer `OnCalendar=*-*-* 00/2:00:00 UTC` (every 2h); override.conf `RuntimeMaxSec=10800→3600`. **Deviation:** an annotation `sed` was malformed and prepended garbage to every override.conf line — caught immediately, **restored from the `.bak` backup**, redid the value edit cleanly (python, not sed). Net result correct. (Lesson: the backup-first discipline paid off.)
- **Step 2:** `disable --now` afternoon + evening timers → both inactive. Consolidated to one runner.
- **Step 3:** daemon-reload + enable daily.timer. **Invariant confirmed: `RuntimeMaxUSec=1h` < 2h interval.** NEXT fire = Thu 00:00 CST. `enable --now` triggered one immediate Persistent catch-up run (completed 5s).
- **Step 4 corruption guard PASS:** graphml intact (32056 nodes / 46605 edges, well-formed `</graphml>` tail), **no stray `.tmp`**. The immediate run was Layer-1-only, never touched graphml.
- **Step 5:** repo copies updated (`omnigraph-daily-ingest.timer` — also dropped a stale `Requires=` line that the live unit doesn't have, per memory `aliyun_drift_recovery_260528_lessons`; new `omnigraph-daily-ingest.service.d/override.conf`).

### ⚠️ BLOCKER surfaced by the immediate run (NOT caused by this change) → ISSUES #68

The immediate fire's Layer-1 classify failed **every batch** with `403 PERMISSION_DENIED: billing to be enabled` on GCP `project-df08084f-6db8-4f04-be8` → `no candidates after batch filtering` → 0 ingestable. This is **intermittent**: the 20:00 run (pre-change) classified fine (`candidate=30...`) and landed 3 articles; chunks rose +28 over 24h, so some runs work. The Layer-1 classify path uses the single `OMNIGRAPH_GEMINI_KEY` whose project has billing disabled; when a run happens onto a billing-enabled path it works. **Implication: raising frequency multiplies a partially-failing classify.** The frequency change is correct and safe, but its throughput benefit is capped until the billing 403 is fixed (re-enable billing on that project, OR rotate the classify key to a billing-enabled project, OR add `OMNIGRAPH_GEMINI_KEYS` multi-key rotation for the classify path like embedding already has). Filed ISSUES #68 (P1).

### Verification status
- Config change: VERIFIED (timer 2h, ceiling 1h<2h, single runner, graphml safe, backups exist).
- Throughput outcome: PENDING — cannot confirm "24-36 articles/day" until #68 (billing 403) is resolved; the every-2h cadence will then deliver it. Will observe ≥2 real fires after billing fix.
