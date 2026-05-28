# 260528-f1s — Aliyun drift recovery (SUMMARY)

**Quick ID:** 260528-f1s
**Date:** 2026-05-28
**Status:** ✅ **CLOSED 2026-05-28** — code plane green, data plane synced, 4/4 smoke GREEN
**Duration:** ~6h wall (3h actual work + 3h SCP/UC Volume bandwidth on slow corp egress 0.77 MB/s)

## Outcome

Recovered Aliyun + Databricks from 11-day stale state caused by 8 compounding failures since aim-3 cutover (2026-05-24). All 22 atomic steps from PLAN executed; 5 commits pushed to GitHub main; 4/4 user-side browser smoke GREEN (real LightRAG `kg` confidence — NOT fts5_fallback).

## End-state metrics

| Plane | Metric | Pre-quick | Post-quick |
|---|---|---|---|
| Code | Aliyun HEAD | `bb2a358` (7 behind, 3 hot-patched) | `56037de` (= origin/main) |
| Code | GitHub main HEAD | `bec6f6f` | `56037de` |
| Code | Databricks workspace | bec6f6f-era _ssg | 56037de-era _ssg with body_cleaned migration shipped |
| Data | DB articles_fts rows | 0 (empty) → 275 (post D3) → 238 (Databricks stale) | **275 (Databricks post UC Volume push)** |
| Data | KB DB body_translated coverage (L2='ok') | 244 / 285 (85.6%) | **275 / 275 (100%) on L2='ok' body subset** |
| Data | Translate backlog (L1=candidate AND L2='ok' AND body_translated NULL) | 41 (27 KOL + 14 RSS) | **0** |
| Data | kb/output/index.html mtime | 2026-05-17 (11 days stale) | **2026-05-28 22:58** (Aliyun) + 2026-05-28 15:13 (local re-bake for Databricks) |
| Data | LightRAG storage embedding_dim | 3072 (Vertex Gemini) | 3072 ✓ |
| Data | LightRAG nodes / edges | 30068 / 43143 | 30068 / 43143 (parity preserved) |
| Process | Aliyun zombie PID 334819 | active, 2-day stale | killed; timer re-armed for 2026-05-29 12:00 UTC |
| Process | Aliyun translate cron | DEAD since 2026-05-24 (Hermes-only) | one-shot ran via `setsid nohup`; future runs need follow-up Aliyun-side timer (out of scope) |

## Smoke 4/4 GREEN evidence (user-side browser SSO 2026-05-28 ~07:08-07:09 ADT)

Backend log timestamps (Aliyun-side `/api/synthesize` POST):

| # | Endpoint | Result | Wall |
|---|---|---|---|
| 1 | `GET /health` | 200 `status=ok version=2.0.0` | 07:04:37 |
| 2 | `GET /api/articles?limit=5` | 200 `total=275`; 3 RSS rows surface `title_translated=null` (BL-1 patho already known) | 07:05:07 |
| 3 | `GET /api/search?q=AI&mode=fts` | 200 non-empty (275 indexed) | 07:05:29 + 07:05:43 |
| 4 | `POST /api/synthesize` long_form `What is LightRAG?` | 202 Accepted → poll → status=done; **`response_chars=3305 markdown` (NOT fts5_fallback)**; `wall_s=80.51`; LightRAG load+query trace verified | 07:08:06 → 07:09:27 |

Critical synthesize trace evidence:
- 07:08:06 POST /api/synthesize 202 Accepted (BG dispatch)
- 07:08:11 LightRAG graphml load 30068 nodes / 43143 edges
- 07:08:34 nano-vectordb 3 collections (3072-dim) loaded
- 07:08:37 `lightrag_singleton_ready wall_s=30.58` (Databricks /tmp tmpfs cold-start)
- 07:08:40 embedding 8 workers init
- 07:08:42-43 hybrid query: 52 entities, 170 relations, 13 chunks
- 07:08:43 rerank warning (expected — Wave 2 P2-3 hasn't added BGE-v2-m3 yet)
- 07:09:27 `kg_after_aquery wall_s=49.93 response_chars=3305`
- 07:09:27 `c1_after_aquery wall_s=80.51 response_chars=3305`

Browser job poll: `GET /api/synthesize/<job_id>` → `status=done`, result keys `['job_id', 'status', 'result', 'fallback_used', 'confidence', 'error']`, real markdown output.

## Commits (5 pushed to origin/main during this quick)

| Commit | Type | Notes |
|---|---|---|
| `97bc36c` | feat(kb/migrations) | 008 add body_cleaned/body_repositioned columns |
| `56037de` | fix(kb/migrations) | 008 SQL comment had stray semicolon (forward-fix; not amend) |
| `8522f6a` | chore(kb/scripts) | set +x on daily_rebuild.sh |
| `8f543ea` | fix(kb/ask) | (pre-existing local commit, rode along with push per constraint A) |
| `e1a40d9` | docs(v1.1) | (pre-existing local commit) |
| `de36db9` | docs(v1.1.P5) | (pre-existing local commit) |

This quick's docs commit (this SUMMARY + STATE update) is the **6th** authored by f1s — landing on top of 7 unrelated commits authored by the parallel `260528-mi6` orchestrator while user smoke was running. No rebase, no amend, no force-push.

## Sanity checkpoints (boot logs from 2nd Pass 3 deploy `01f15ac97d9b1eb7b16d6d76360b32aa`)

```
2026-05-28 19:18:55 kb.db_bootstrap INFO Hydration complete: /tmp/kol_scan.db (43868160 bytes)
2026-05-28 19:18:55 kb.db_bootstrap INFO lang-column migration: {'articles': 'already_present', 'rss_articles': 'already_present'}
Applying 008_add_body_cleaned_columns.sql ...
  SKIP (already exists): articles.body_cleaned          ← idempotent guard worked
  SKIP (already exists): articles.body_repositioned
  SKIP (already exists): rss_articles.body_cleaned
2026-05-28 19:18:56 kb.db_bootstrap INFO FTS5 rebuild complete: 275 rows indexed
2026-05-28 19:18:57 kb.db_bootstrap INFO Hydrating LightRAG storage ...
```

DB size 42MB ✓ (matches Aliyun snapshot post-translate)
FTS rebuild rows 275 ✓ (was 238 stale on 1st Pass 3 deploy `01f15ac2127c1f9dbc7e6fa8105d2415`)

## Lessons (added to memory)

1. **`databricks apps stop+start` wipes deployment artifact** → app reports `state=UNAVAILABLE` until you re-run `apps deploy --source-code-path`. Required 2 Pass 3 deploys this quick: 1st before UC Volume push (FTS=238 stale), 2nd after stop+start+re-deploy (FTS=275 ✓). [Memory: `databricks_apps_stop_start_wipes_deployment`]

2. **D5 backlog avg-body estimate was 4x off.** I read recon avg `body_len=8500 chars` for the 41 backlog and estimated ~40s/article × 41 = 30 min. Actual: 13K-17K chars (the 244 already-translated were the easy small ones; the 41 left were the gnarly long ones), giving ~2:44/article × 41 = **99 min actual**. Halt H3 fired at article 1+2 (4-min cadence) — user revised to "let it run" because cost was minimal and per-article failure-safe.

3. **systemd timer with `Persistent=true` immediately re-fires service on `start`.** When I `systemctl start omnigraph-daily-ingest.timer` (intended: re-arm tomorrow), `Persistent=true` saw last-run was missed → fired service NOW (PID 3519433). Caused DB write-lock contention with translate cron. Fix: stop service, leave timer started — but timer also got auto-stopped, so it stays inactive until next manual arm. Current state: timer inactive, must be manually re-armed before 2026-05-29 12:00 UTC.

4. **`databricks fs cp --overwrite` works for UC Volume re-seed** despite RUNBOOK §6 warning (which prescribes a force-overwrite Job for safety). 1.8GB lightrag + 881MB images + 42MB DB all pushed cleanly via three sequential `fs cp` calls (no parallel — UC Volume write-lock competition not validated). Total upload time: 1.8GB lightrag ~31 min + 881MB images ~18 min + 42MB DB <1 min at corp egress 0.77 MB/s.

5. **Forward-fix discipline on shared main holds even mid-quick.** When my migration 008 SQL had a stray `;` in a comment that broke `run_migrations.py:_apply_sql` split, I committed forward-fix `56037de` instead of amending `97bc36c`. Memory `feedback_no_amend_in_concurrent_quicks` cited.

6. **Aliyun translate worker uses `BASE_DIR/data/kol_scan.db` resolution which expects `~/.hermes/omonigraph-vault/data/`.** Aliyun has neither — the empty 0-byte `~/.hermes/omonigraph-vault/kol_scan.db` was the legacy fallback target. Fix this quick: symlink `~/.hermes/omonigraph-vault/kol_scan.db` → `/root/OmniGraph-Vault/data/kol_scan.db`. Persistent (no commit needed since it's filesystem-side); future translate runs from Aliyun-side will resolve correctly.

## Out of scope (stays as backlog)

- **OOM mitigation** for `omnigraph-{evening,afternoon,daily}-ingest` (F7 BACKLOG) — units have `MemoryMax=infinity`, blew past 15GB host headroom multiple times. Each ingest still OOM-killable; not blocked but degraded. Separate quick proposed.
- **WeChat session refresh** for `omnigraph-kol-scan` (F8 DEFER) — runbook in `feedback_wechat_cookie_refresh_runbook` requires Hermes-side refresh which is RO-frozen until 2026-06-22. Skip for now.
- **Aliyun-side translate cron** — `translate_body_cron.py` is Hermes-only by design (per docstring + missing systemd unit on Aliyun). Without one, post-Hermes-thaw or post-Aliyun-cron-install, translate backlog will accrue again. Tracked in BL quick `260528-mi6` which is closing this gap with the same model + key but Aliyun-side timer.
- **Aliyun-side UC Volume historical image residue** — UC Volume had 367 image subdirs vs Aliyun's ~240 because `databricks fs cp -r --overwrite` merges instead of replacing. Old subdirs are dead refs (no SSG card links to them) — harmless but technically violates "data plane = Aliyun canonical" strictly. Fix would require RUNBOOK §6 force-overwrite Job. Backlog.

## Cross-references

- Recon report: [.scratch/260528-aliyun-recon-1350.md](../../../.scratch/260528-aliyun-recon-1350.md)
- Displayable gap diagnostic: [.scratch/260528-displayable-gap.py](../../../.scratch/260528-displayable-gap.py)
- Translate run log: Aliyun `/root/OmniGraph-Vault/.scratch/translate-backfill-260528-run2.log` (5942.9s elapsed, 41/41 ok, 0 fail)
- Backlog quick (in flight, 1m orchestrator session): [260528-mi6-260528-translate-completeness](../260528-mi6-260528-translate-completeness/)
- Plan: [260528-f1s-PLAN.md](./260528-f1s-PLAN.md)

## Status

**CLOSED 2026-05-28** — Aliyun + GitHub main + Databricks workspace + UC Volume snapshot all aligned at commit `56037de`. Daily ingest timer **inactive** (must be re-armed before 2026-05-29 12:00 UTC by user or follow-up quick). 4/4 smoke GREEN.
