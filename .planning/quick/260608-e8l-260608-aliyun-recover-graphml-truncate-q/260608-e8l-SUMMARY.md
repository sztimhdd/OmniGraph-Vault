# Quick Task 260608-e8l — Aliyun Recovery — SUMMARY

**Date:** 2026-06-08
**Quick ID:** 260608-e8l
**Recovery path:** Step 3 (Hermes transplant fallback) — Step 2 (kb-api in-memory dump) abandoned
**Total wall-clock:** ~3.5h (Step 0 → final timer enable)

## Outcome

Aliyun OmniGraph stack restored to operational state after 35h compound outage:

- ✅ graphml truncate corruption fixed (Hermes RO byte-identical 27654/39604 transplanted, then ingest grew it to 27683/39655)
- ✅ Qdrant container restored with `--restart=unless-stopped` policy (3 collections healthy: 3467 chunks / 54225 ents / 75441 rels)
- ✅ Atomic write patch shipped to BOTH venvs (`venv-aim1` py3.11 + `venv` py3.10) — `.tmp` + `os.replace()` — production verified during smoke ingest
- ✅ Cron resumed with safer config (`--max-articles 10→5`, `MemoryHigh 3G→10G`, `MemoryMax 4G→12G`); `Conflicts=` already existed
- ✅ kb-api restarted, `/health` 200, search FTS now returns results (was 0 pre-restart)

## Step-by-step results

| # | Step | Status | Wall_s | Evidence |
|---|------|--------|--------|----------|
| 0 | Forensic snapshot | ✅ | 5s | corrupt graphml backed up `.corrupt-20260607-0840` sha256 `ac3ed62f93e8c3a3154e8ebc4efb71ee34ac13bea65d38b644707faf0ce7b354` |
| 1 | Stop crash-loop | ✅ | 8s | 3 timers `disabled`, 3 services `inactive` |
| 2 | kb-api dump | ⏭ ABANDONED | 5min | kb-api openapi has no `/admin/dump`; PID 3409419 has 0 graphml fds (closed at hydrate); no `py-spy` / `gdb` installed for runtime attach. Decision: skip to Step 3 within budget. |
| 3 | Hermes transplant | ✅ | 4min | `scp -P 49221 sztimhdd@<host>:graphml → /tmp → aliyun-vitaclaw:/tmp`. sha256 `938c99bf66a5ad41dce10f7b363e64171da4a2bf33c24d7844e96af5ffa26499` matched all 3 hops. NetworkX parsed cleanly: 27654 nodes / 39604 edges (matches `project_aim2_closed_260524.md` baseline) |
| 4 | Atomic write patch | ✅ | 4min | `.bak-pre-atomic-20260608` snapshots taken; `nx.write_graphml(graph, file_name)` → `tmp_path = file_name + ".tmp"` + `nx.write_graphml(graph, tmp_path)` + `os.fsync` + `os.replace(tmp_path, file_name)` in BOTH venvs. AST syntax check passed. |
| 5 | Qdrant restart | ✅ | 1min | `docker update --restart=unless-stopped qdrant`, `docker start qdrant`, healthz `healthz check passed` after ~30s, all 3 collections present |
| 6 | kb-api restart | ✅ | 90s | systemctl restart, `/health` 200 after ~50s hydrate. **Search FTS smoke: items=20 total=20 (was 0 pre-restart)** — kb-api restart cured the search bug. Long_form synthesize returns `status=done confidence=kg` but `sources=0 markdown=empty` — surfaced as known divergence (see "Known divergence" below) |
| 7 | Cron resume + smoke | ✅ | 3.4h (mostly ingest) | service-file edits applied, `daemon-reload` ok. Manual fire 22:04:50 CST → 5/5 articles processed in 1899s (31.6 min). **Atomic write VERIFIED in production: graphml grew 32006816→32053702 bytes (+47KB), 27654→27683 nodes (+29), 39604→39655 edges (+51), no `.tmp` orphan, ownership flipped uid 1000→root.** Service hung post-completion (~50min idle in `S` state, asyncio loop not exiting cleanly — separate pre-existing issue, see Issues). Killed via `systemctl stop`, graphml integrity intact post-stop. Re-enabled 3 timers — next fires 06-09 08:00 CST. |
| 8 | Final verification | ✅ | 1min | All 4 substrates green: graphml 27683/39655 parses, Qdrant healthz + 3 collections + restart policy, kb-api `/health` 200 + search 20 items, 3 ingest timers active with patched configs |

## Atomic write fix — production proof

```
Pre-ingest:   graphml 32006816 bytes, 27654 nodes / 39604 edges, mtime 21:35, owner uid 1000
Post-ingest:  graphml 32053702 bytes, 27683 nodes / 39655 edges, mtime 22:35, owner root
Delta:        +46886 bytes, +29 nodes, +51 edges
.tmp orphan:  NONE — os.replace() succeeded atomically
```

This is the single most important outcome: **6/7 graphml-corruption-class incident cannot recur** because any future SIGTERM mid-write now leaves the live `.graphml` untouched and only orphans the `.tmp`.

## Known divergence (post-Hermes-transplant 14-day data loss bound)

**Step 3 fallback trade-off documented per orchestrator:** Hermes RO baseline = 5/24 cutover, byte-identical at 27654 ents / 39604 rels. Aliyun Qdrant accepted writes 5/24→6/7 (now 54225 ents / 75441 rels), but those 14 days of graphml writes were never persisted to disk on Hermes (frozen RO until 2026-06-22) and were destroyed by the 6/7 truncation. Net delta: **graphml is now ~26.5k entities / ~35.8k relationships smaller than Qdrant has**.

**Visible symptom:** `POST /api/synthesize {mode: long_form}` returns `status=done confidence=kg` but `sources=0 markdown=empty`. LightRAG hybrid retrieval finds chunks in Qdrant but the corresponding entity/relationship nodes don't exist in graphml, so the KG join produces 0 sources.

**This is NOT a new bug** — it's the documented data-loss bound of the Step 3 path. New Step 7 ingests will incrementally rewrite graphml (atomic-safe now) and gradually catch up. Long_form RAG quality is degraded until the catch-up completes.

**Follow-up scope (user decision):**
- Path X — Aliyun cron slow rebuild: 1-2 weeks of normal cron (5 articles/run × 3 runs/day × 14 days = 210 article ingests). Free, automatic, no operator work; long_form quality degraded throughout.
- Path Y — Hermes batch ingest 7-10h: Hermes is on home network (no corp Umbrella TLS interception), DeepSeek reachable for provider parity, ~8-25× faster. Operator-driven 1-night job. Restores parity in one window.

Decision deferred to user — not started in this quick.

## SiliconFlow vision provider note

Step 7 manual ingest exhibited **16.7% Gemini fallback** during vision cascade for the 5-article smoke (`provider_mix: {siliconflow: 9, gemini: 1}`). LDEV-06 also dropped `openrouter` provider per env (`OMNIGRAPH_VISION_SKIP_PROVIDERS=openrouter`).

Orchestrator probed SiliconFlow API directly: `balance=0 chargeBalance=-57.3247`. Per memory `aliyun_qdrant_collection_naming` (note: actual reference is the broader SiliconFlow API field-meaning bug noted prior), the API field semantics are unreliable; the user panel is authoritative (last verified ~¥15).

**Recommendation:** verify SiliconFlow balance via user panel before next cron fire (06-09 08:00 CST). If balance truly depleted and OpenRouter is also disabled, **all** vision will fall through to Gemini, which is capped at 500 RPD on the free tier — a single batch of image-rich articles can exhaust it.

## Cross-references

- Workflow result: `C:/Users/huxxha/AppData/Local/Temp/claude/.../tasks/wad5a5ysc.output`
- aim-2 cutover memory: `project_aim2_closed_260524.md` (Hermes byte-identical baseline 27654/39604)
- LightRAG networkx storage: `lightrag/kg/networkx_impl.py` (write_nx_graph atomic patch in BOTH venvs)
- Backup files preserved on Aliyun:
  - `graph_chunk_entity_relation.graphml.corrupt-20260607-0840` (pre-recovery forensic)
  - `networkx_impl.py.bak-pre-atomic-20260608` (×2, both venvs)
  - `omnigraph-{daily,afternoon,evening}-ingest.service.bak-pre-recovery-20260608` (×3)

## NOT done (intentionally)

- ❌ Hermes write — read-only `scp` pull only; Hermes RO until 2026-06-22 honored
- ❌ qdrant-snapshot.timer — kept disabled (still awaiting #41 streaming-write fix)
- ❌ A3 BACKOFF=10 changes — workflow verdict ruled out A3 as cause; left in place
- ❌ Long_form synthesize bug fix — deferred to user-decided follow-up (Path X / Path Y)
- ❌ Service post-completion-hang root-cause — separate pre-existing issue, surfaced in ISSUES.md

## Surfaced issues (added to .planning/ISSUES.md)

1. **Aliyun graphml ↔ Qdrant divergence after 6/7 incident** — long_form synthesize returns 0 sources; needs Path X / Y replay
2. **Ingest service hangs post-completion** — `Done — N candidates processed` + `Successfully finalized 12 storages` log lines emit, but python process stays in `S` (sleep) state for 50+ min (some asyncio task / connection pool not closing). `Restart=on-failure` doesn't fire because no failure; `TimeoutStopSec` would, but daily-ingest doesn't set one. Pre-existing — observed in workflow finding 4 already.
3. **SiliconFlow API balance field semantics** — user panel is authoritative; API balance/chargeBalance values cannot be trusted for budget governor decisions
4. **LightRAG vendored atomic-write patch is fragile** — `pip install --force-reinstall lightrag` will overwrite. Track as P2 tech debt: vendor patch upstream OR move to a sitecustomize hook.

## Single forward-only commit (post-recovery)

- Commit subject: `fix(aliyun-recover): graphml truncate + Qdrant restart + atomic write structural fix`
- Files staged: `.planning/quick/260608-e8l-...-q/{260608-e8l-PLAN.md, 260608-e8l-SUMMARY.md}` + `.planning/STATE.md` + `.planning/ISSUES.md`
- All structural fixes committed live on Aliyun side; repo commit captures planning + lessons only (atomic-write patch is in vendored site-packages, not in repo).

## Final state snapshot (2026-06-08 22:35 CST)

```
graphml:  27683 nodes / 39655 edges, parses cleanly, 32053702 bytes
Qdrant:   3467 chunks / 54225 entities / 75441 relationships, restart=unless-stopped, healthz OK
kb-api:   active, /health 200, search FTS returns 20 items
Cron:     3 timers active, --max-articles 5, MemoryHigh=10G/12G, Conflicts= already-existed
Atomic write patch: ✅ both venvs, production-verified
```
