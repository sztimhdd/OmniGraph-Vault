# arx-4 — Next-Phase Focus Triage + Research

**Phase slug:** `arx-4-databricks-kg-retrieval`
**Authored:** 2026-06-24
**Mode:** Triage-first (ISSUES labels are unreliable — verify, don't trust). Reading-heavy.
**Scope discipline:** Fix known-unfixed / finish known-undone ONLY. Zero new features, zero capability expansion.

---

## 0. Method

Per `feedback_parallel_track_gates_manual_run` + the command mandate, this project has repeatedly burned cycles on stale tracker state. So **every** open-row classification below is backed by a code grep, a git fact, or a read-only prod probe (`aliyun-vitaclaw` SSH + Databricks deploy artifacts), not by reading the ISSUES prose.

**Live prod probes run 2026-06-24 (this session):**

| Probe | Result |
|---|---|
| Aliyun `aliyun-vitaclaw` SSH | reachable (`iZj1imk39yc55iZ`, CST clock OK) |
| Aliyun graphml | `graph_chunk_entity_relation.graphml` = **32056 nodes / 46605 edges**, 38 MB, mtime 2026-06-24 20:21 (above 27654 Hermes 5/24 baseline → Path X cron rebuild **confirmed active**) |
| Aliyun Qdrant | 3 collections live: chunks=**3851**, entities=**59191**, relationships=**82582** (3072-dim suffix) |
| Aliyun kb-api | `systemctl is-active` = **active**, listening :8766 |
| Aliyun timers | all firing on schedule: 3× ingest (daily/afternoon/evening), translate, rss-fetch/rescrape/layer2, **kol-scan + kol-refresh + kol-zombie-cleanup** (cookie self-heal chain LIVE) |
| Aliyun disk `/dev/vda3` | **85%** (80G/99G, 15G free) — up from 84% (g6e), `/var/lib/containerd` = 23G orphan (#61) |
| Databricks app | `app_entry:app` = `kb.api:app` + SSG static mount; hydrates UC-Volume `lightrag_storage` → `/tmp/omnigraph_vault` (`startup_adapter.py`) |
| `ingest_wechat.py:429-430` | `default_embedding_timeout`/`default_llm_timeout` kwargs **present** (confirms #31 shipped) |
| `databricks-deploy/jobs/reindex_lightrag.py` | **exists + kdb-2.5-validated** (Run 4: ok=75 failed=0 0.00%) — serverless reindex Job |
| `requirements.txt:30-31` + `databricks-deploy/requirements.txt:42-43` | `sentence-transformers` + `torch` still present (confirms #23 open) |
| `.planning/ROADMAP.md` | absent (confirms #54 false-negative is real) |

---

## 1. Triage table — every open row

Status legend: **(a)** actually-resolved-but-mislabeled · **(b)** stale/self-healed · **(c)** superseded/folded · **(d)** genuinely-open + worth-doing · **(e)** genuinely-open but park.

| # | labeled | verified | evidence | true-sev |
|---|---|---|---|---|
| 1 | P0→P1 | **(b)** self-healed | Row itself notes 12→1 stuck (2026-06-02). Sole remaining row; cron re-scrape path active. Symptom near-gone. | P3 / near-resolved |
| 2 | P0 | **(e)** park | Vertex 429 burst; row says "daily-ingest auto-retries next cron". No 3-day chronic accumulation reported since. Passive self-heal by design. | P3 watch |
| 40 | P0 | **(c)** superseded — CLOSED BLOCKED | Row VERDICT FINAL 2026-06-12: native list-ainsert 1.27x < 1.4x; all gather paths BLOCKED. v1.2 concurrent-ingest thread CLOSED. **Hard-constraint: do NOT re-attempt.** | — (closed research) |
| 44 | P0 | **(b)** self-healed (Aliyun) / **(d)** open (Databricks) | Aliyun symptom CLEARED — live probe: graphml 32056 nodes (>baseline), Qdrant aligned, arx-2 close measured long_form sources=13 on 2026-06-23. Databricks residue = #64. | P1 (Aliyun); Databricks split → #64 |
| 41 | P0 | **(e)** park / partially moot | `qdrant_to_nanovdb.py` OOM converter. This was the Qdrant→NanoVDB bridge for the **old** Databricks sync path. The kdb-2.5 reindex Job (serverless, no OOM) is a **superior alternate** path that sidesteps the converter entirely. Timer already disabled. | P2 (moot if reindex-Job path adopted) |
| 58 | P0-sec | **(a)** mislabeled-resolved (partial) | Row text: "⚠️ PARTIAL 2026-06-23 … literal redacted from repo + env wired (commit `9fc5dcf`)". Password ROTATION = **user-only** (excluded by command). Code half is done. | Doc / user-only — EXCLUDE |
| 51 | P1 | **(e)** park (omnigraph-adjacent) | Disk 85% (live). Real but slow burn (~1pp/3d). Bundle w/ #61 containerd reclaim. Diagnostic-only, no code. NOTE: command says "#51 is vitaclaw docker garbage, exclude" — but the ISSUES #51 row is the omnigraph disk-trend; the **containerd** garbage is #61. Treat disk as ops-park. | P2 ops-park — EXCLUDE from focus |
| 3 | P1 | **(e)** park (decision-gated) | Wiki body single-language. Needs user decision (path A/B/C). Not a fix — a product decision. | P2 decision-gated |
| 5 | P1 | **(e)** park (decision-gated) | `_suggestions/` no review queue. Needs user decision (keep/retire/build UI) = new feature → out of scope. | P3 |
| 6 | P1 | **(e)** park | `test_css_budget_within_2100` — style.css 2172 vs 2150. Cosmetic test gate. Command explicitly names as park. | P3 cosmetic |
| 36 | P1 | **(c)** superseded | Single-article 48min wall on Aliyun (cross-border Vertex physics). Real fix candidates all = new infra (Hermes-fresh-ingest / regional endpoint). #40 sibling. Path X cron already absorbs the throughput need (graphml IS rebuilding). | P2 (no viable in-scope fix) |
| 38 | P1 | **(c)** folded into #40 | Wrapper-cap cumulative wall. Row says "Folded into #40 for fix path". #40 BLOCKED. | — (folded, dead) |
| 39 | P1 | **(b)** mitigated | PROCESSED-gate 150s. A3 (`b6f4a23` backoff 10.0→300s budget) + Aliyun .env override applied 2026-06-07. MERGE candidate w/ #32. Mitigation shipped. | P2 watch |
| 42 | P1 | **(c)** folded into #41 | Snapshot SLB throttle. Row: "(folded into #41)". Timer disabled → trigger gone. | — (folded) |
| 28 | P1→P2 | **(e)** park (needs measurement) | DeepSeek image-emit rate < Claude, "NOT zero". Needs N≥10 sample before any change. Not a clear defect. | P2 measure-first |
| 29-orig | P1 | **(a)** resolved | Historical row; resolved via R32 (`8f5d147` server-side `_normalize_citations`). Already in Resolved. Marker row only. | — (resolved R32) |
| 32 | P1 | **(b)** mitigated / MERGE #39 | PROCESSED-gate 60s. Same knob as #39, mitigated by same commits. | P2 (merge #39) |
| 33 | P1 | **(e)** park (by-design) | Wrapper 1200s cap on image-heavy KOL. Row: "NOT a bug — wrapper design"; cache heals next pass. P3. | P3 by-design |
| 31 | P1 | **(a)** mislabeled-resolved | **VERIFIED shipped**: `ingest_wechat.py:429-430` has `default_embedding_timeout`/`default_llm_timeout` kwargs. Row says "Fix shipped 2026-06-03". Still in Open table. | — move to Resolved |
| 26 | P1 | **(a)** mislabeled-resolved | Folded into #25; #25 resolved R24, #26 resolved R25 (qdrant-migration). Row still in Open P1 table with "(folded into #25)". | — move to Resolved (R25) |
| 43 | P1 | **(a)** mislabeled-resolved | Row text: "**RESOLVED 2026-06-07 00:37 UTC**" + "Move to Resolved (recent) on next ISSUES update". Never moved. | — move to Resolved |
| 45-orig / 45-orig-3 | P1 | **(a)** resolved | Historical diff-archaeology rows; resolved R29 (`352dd01` os._exit). Marker rows. | — (resolved R29) |
| 48-orig | P1 | **(a)** resolved | Historical row; resolved R31 (`dd845c9`+`a9c4f44`). Marker row. | — (resolved R31) |
| 56 | P1 | **(a)** mislabeled-resolved | **Row literally starts "✅ RESOLVED 2026-06-23 … R33"**. Still in Open P1 table. Live probe confirms: kol-scan/refresh/zombie timers all firing; MAX(scanned_at) recovered per R33. | — move to Resolved (R33) |
| 60 | P1 | **(d)** open (ops-hardening) | Incident resolved (g6e); row tracks the **preventive rebuild-checklist**. Real undone work, but it's a script/doc artifact (no user-facing correctness). Plausible-again (host expiry). | P1 ops — candidate but not user-facing |
| 63 | P2 | **(d) but OUT OF SCOPE** | Databricks iterations=1 cap. Real undone work, BUT the fix = **async-job + polling rearchitecture** = build something new (per `databricks-apps-sse-300s-cap`). Hard-constraint: new-build → excluded. | P2 — EXCLUDE (new-build) |
| 64 | P2 | **(d)** GENUINELY OPEN — top candidate | Live Databricks log (arx-2 UAT#3): `0 vector chunks` every query → WEIGHT fallback. UC-Volume snapshot has graphml↔vdb-chunk misalignment. **Fix = re-sync an aligned snapshot** (finish-existing: Aliyun storage is now aligned + a reindex Job exists). User-facing retrieval-quality. | **P2→P1 correctness** |
| 65 | P2 | **(d)** GENUINELY OPEN — bundles w/ #64 | `kb/api.py:_build_llm_rerank` inits OK (:72) + passes `rerank_model_func` to LightRAG (:100), but every query logs "Rerank is enabled but no rerank model is configured". Init-vs-query disagree. Small wiring fix (~10-40 LoC) or set `enable_rerank=False`. | P2 |
| 46 | P2 | **(e)** park | SiliconFlow balance field unreliable → panel-verify checklist. Operational/doc. | P2 doc |
| 47-orig | P2 | **(a)** resolved | Historical; resolved R30 (`62e49a3` sitecustomize). Marker row. | — (resolved R30) |
| 11 | P2 | **(e)** park | STATE.md table style drift. Cosmetic doc. | P3 doc |
| 23 | P2 | **(d)** open but gated | `sentence-transformers`+`torch` trim. **VERIFIED present** (requirements.txt:30-31 + databricks-deploy:42-43). Gated on "after perf-fix-B rollback no longer needed". ~1.2GB deploy saving. Cleanup, low-risk. | P2 cleanup |
| 35 | P2 | **(b)** self-heal expected | 4 absent article hashes; cron re-attempt. Tracking only. | P3 |
| 49 | P2 | **(e)** park | `_dedupe_reference_sections` ZH-header gap (bare `## 参考`). Real headers covered; low impact. ~3 LoC. Bundle w/ next synthesize-touch. | P2 trivial |
| 37 | P2 | **(e)** park | 21 Qdrant orphan articles (no rels). Zero functional impact; cleanup when #40 lands (#40 BLOCKED → indefinite park). | P3 |
| 53 | P2 | **(d)** open trivial | translate `id=1258` returns None every cron. Single stuck job blocking 100% coverage (96.5% otherwise). Skip-list or root-cause. ~few LoC. | P2 trivial |
| 61 | P2 | **(d)** open ops | `/var/lib/containerd` 23G orphan layers. Reclaimable but outside docker prune. Careful `crictl rmi --prune`. Bundle w/ #51 disk window. | P2 ops |
| 66 | P3 | **(e)** park | One Databricks image 404 (`f31803442a/4.jpg`). Cosmetic. | P3 cosmetic |
| 13 | P3 | **(e)** park v1.2 | P1 K2 citation revisit, PARKED v1.2. Overtaken by qa.js + #29 server-side. | P3 parked |
| 14 | P3 | **(e)** park | P4.0/P4.1 ARAG audit. Wave-3 blocked. (Note: arx-2 Deep Research effectively shipped this capability — may be stale.) | P3 |
| 15 | P3 | **(e)** park | P6.1 fixture drift audit. Housekeeping. | P3 |
| 17 | P3 | **(e)** park | wiki-bilingual SSG bake = Issue #3 path B = new feature. | P3 |
| 18 | P3 | **(e)** park (user) | Databricks PAT rotation. User convenience. | P3 user |
| 34 | P3 | **(c)** postmortem-only | Hermes detour postmortem. Doc only, no fix. | — (doc) |
| 57 | Doc | **(a)** mislabeled-resolved | **Row starts "✅ RESOLVED 2026-06-23 … commit `338dd90`"**. Still in Open Doc table. | — move to Resolved |
| 59 | Doc | **(e)** park | Level-C QR-binding hardening note. Rare unattended path. Robustness note. | Doc |
| 54 | Doc | **(d)** open trivial | `init` reports `roadmap_exists:false`. **VERIFIED**: no bare `.planning/ROADMAP.md` (archived by 260611-lct). Re-confirmed 2× (dv7, g6e). Fix = stub pointer file (1 file). | Doc trivial |
| 62 | Doc | **(a)** resolved inline | docker-compose-plugin conflict; resolved inline in g6e. Recorded for future. | — (informational) |

**Triage summary counts:**
- **(a) mislabeled-resolved, still in Open tables:** #56, #57, #31, #43, #26 (+ marker rows #29-orig/#45/#47/#48/#62 already tracked) → **5 rows the orchestrator must move post-plan.**
- **(b) self-healed / mitigated:** #1, #44(Aliyun), #39, #32, #35 → downgrade.
- **(c) superseded / folded / closed-blocked:** #40, #38, #42, #36 → no in-scope fix.
- **(d) genuinely open + worth doing:** #64, #65, #60, #23, #53, #61, #54 (+ #63 open but new-build → excluded).
- **(e) park:** the long P2/P3/Doc tail.

---

## 2. Cluster analysis — the genuinely-open (d) rows

### Cluster A — Databricks KG-retrieval quality  ★ recommended
**Rows:** #64 (UC-Volume vector-chunk misalignment / WEIGHT fallback), #65 (rerank configured-but-inactive). #44's Databricks residue is the same root.
**Combined severity:** correctness/quality — affects every deployed `/api/research` + `/api/synthesize` query.
**User-facing impact:** HIGH-but-currently-masked. Reports still render (WEIGHT fallback recovers 11-12 chunks → sources>0), so it's not a hard outage, but the **vector-similarity retrieval path is 100% starved** (`0 vector chunks` on every query) and rerank is inert — the two mechanisms most responsible for retrieval *quality* are both off on the deployed env.
**Effort:** MEDIUM. #64 = re-sync an aligned snapshot into UC Volume + re-hydrate (no new code — the alignment fix is data, and the tooling exists). #65 = small wiring fix in `kb/api.py` (~10-40 LoC) or `enable_rerank=False`.
**Is the real fix viable? YES — and it's finish-existing, not new-build:**
- The canonical Aliyun `lightrag_storage` is now **internally chunk-aligned** (live probe: graphml 32056 nodes, Qdrant aligned, long_form sources=13). app.yaml:51 already declares the Databricks app expects **3072-dim** embeddings (matching Aliyun's `gemini-embedding-2`), so a snapshot synced FROM Aliyun is dim-compatible with the deployed provider.
- A Databricks-native serverless reindex Job (`reindex_lightrag.py --mode fullreindex`) exists and was **kdb-2.5-validated** (Run 4: ok=75 / 0% failure). It builds a fresh, chunk-aligned snapshot **by construction**, on serverless (no OOM #41, no cross-border physics #36). ⚠️ kdb-2.5 ran at dim=1024 (`EMBEDDING_DIM=1024` in `lightrag_databricks_provider.py:48`) — so the Job is one viable path but needs a dim/provider reconciliation; the **lower-risk path is sync-from-aligned-Aliyun** (already 3072-dim, already aligned, no re-extraction cost).
- This is the **single highest value/viable-fix ratio** cluster: it directly restores the retrieval substrate (per `lightrag_is_core_asset_no_bypass` — fix the infra, don't skip it), closes 2 open rows + clears #44's last residue, and every path is "finish work already proven," not "invent something."

### Cluster B — Ingest throughput
**Rows:** #36 (48min/article), #38 (wrapper cumulative cap), #39 (PROCESSED-gate), #32/#33 (gate/cap), #40 (concurrency).
**Verdict: NO in-scope phase.** The cluster's real fix — in-process concurrency (#40) — is **research-CLOSED BLOCKED** (1.27x < 1.4x; pipeline_status singleton; Aliyun 2-core/14G OOM ceiling). #38/#42 fold into #40. #36's fix candidates are all new infra (Hermes-fresh-ingest, regional endpoint). #39/#32 are already mitigated (backoff→300s). **The throughput need is already being met passively** — live probe shows Path X cron is rebuilding the graphml (32056 > 27654 baseline). Remaining options are all either dead (#40), new-build (#36), or zero-code ops cadence (more systemd timers). **Park the whole cluster.**

### Cluster C — Deep Research depth (#63)
**Verdict: OUT OF SCOPE.** Real undone work, but the only fix is an **async-job + client-polling rearchitecture** (the SSE arch cannot defeat the Databricks ~300s duration cap — `databricks-apps-sse-300s-cap`). That is building a new serving architecture = capability expansion. Excluded by hard constraint. Deep Research is fully usable at iterations=1 (the default, UAT#3 PASS). Aliyun (no cap) already runs higher iterations. Leave as the natural arx-3 follow-up.

### Cluster D — Ops hardening + small cleanups
**Rows:** #60 (rebuild checklist), #61 (containerd reclaim), #51 (disk), #54 (roadmap stub), #23 (deps trim), #53 (translate 1258), #49 (ZH dedupe).
**Verdict: real but low-coupling, individually tiny, mostly ops/doc.** #60 is the most valuable (prevents a repeat of the 7-day silent KG halt) but it's a preventive script, not a user-facing correctness fix. The rest are 1-file / few-LoC cleanups best handled as `/gsd:quick`s when their natural touch-window opens, NOT bundled into a phase (bundling unrelated tiny fixes violates atomic-commit discipline + PRINCIPLE #8 right-sizing). **Park as a quick-backlog; do not phase.**

---

## 3. RECOMMENDED NEXT-PHASE FOCUS

### → **Databricks KG-retrieval quality restoration (#64 + #65)**

**Rationale (3 sentences):** Of all genuinely-open work, only Cluster A combines real user-facing impact (the deployed Databricks app's vector-similarity retrieval is 100% starved and rerank is inert — the two highest-leverage quality mechanisms both off) with a *viable, finish-existing* fix path (re-sync the now-aligned 3072-dim Aliyun snapshot into the UC Volume + a small `kb/api.py` rerank-wiring fix), versus Cluster B (real fix proven dead), Cluster C (only fix is new-build, excluded), and Cluster D (tiny ops/doc quicks, not phase-worthy). It honors `lightrag_is_core_asset_no_bypass` by repairing the retrieval substrate rather than masking it with the WEIGHT fallback. Every step is "run a validated Job / sync aligned data / fix a known wiring bug" — zero new features.

**Issue rows this phase closes:** **#64** (UC-Volume vector-chunk re-sync → restore vector-similarity retrieval) and **#65** (rerank init-vs-query reconcile). Clears the last **#44** residue on the Databricks env (Aliyun half already self-healed).

**Phase boundary (what this phase IS):**
1. Re-sync / regenerate an internally chunk-aligned `lightrag_storage` snapshot into the UC Volume so `chunks_vdb` vector similarity stops returning `0 vector chunks` (decision: sync-from-aligned-Aliyun vs run the kdb-2.5 reindex Job — to be locked in CONTEXT, default = sync-from-Aliyun as lower-risk + dim-matched).
2. Re-hydrate the deployed app + verify the WEIGHT-fallback WARNING is gone and `Raw search results` shows `>0 vector chunks`.
3. Reconcile #65: trace `rerank_model_func` from `kb/api.py:_build_llm_rerank` (:72 init / :100 pass) through to the LightRAG query path; either wire it so rerank actually applies, or set `enable_rerank=False` to drop the misleading warning — whichever the trace proves correct.
4. Re-run the arx-2 Deep Research UAT on Databricks at iterations=1 to confirm vector-path retrieval + (if wired) rerank are now active, sources still >0, report still cited.

### What this phase does NOT touch (explicit out-of-scope)
- **Ingest throughput** (#36/#38/#39/#32/#33/#40) — #40 BLOCKED, rest folded/mitigated/new-infra. Park.
- **Deep Research iterations≥2 / async-job rearchitecture** (#63) — new-build, excluded by hard constraint. Natural arx-3.
- **Aliyun #44** — already self-healed (live-verified); this phase only addresses the Databricks residue.
- **Ops/cleanup quicks** (#60 rebuild checklist, #61 containerd, #51 disk, #54 roadmap stub, #23 deps trim, #53 translate-1258, #49 ZH-dedupe) — handle as `/gsd:quick`s in their own windows, not this phase.
- **Decision-gated / measurement-first** (#3 wiki-bilingual, #5 suggestions queue, #28 image-emit rate) — need user decision or data, not a fix.
- **#58 password rotation** (user-only) + **#18 PAT rotation** (user) — excluded.
- **New-build of anything.** If a step turns out to require building new infra, halt and re-scope.

---

## 3.5. ⚠️ CRITICAL CORRECTION — sync-from-Aliyun premise FALSIFIED (probed 2026-06-24, post-recommendation)

After the focus was confirmed, a deeper probe **invalidated the "sync-from-aligned-Aliyun is the low-risk path" assumption** in §3. The naive sync would *reproduce* #64, not fix it. Evidence chain (all live-probed this session):

| Fact | Evidence |
|---|---|
| Databricks app reads **on-disk nanovectordb** `vdb_*.json` | `app.yaml`/`config.py`/`startup_adapter.py` have ZERO Qdrant refs → defaults to `nanovectordb` per `kb/api.py:92`. Databricks stands up no Qdrant. |
| `sync_to_databricks.sh` Step 3 copies Aliyun **on-disk** `vdb_*.json` | script lines 113-132 tar the on-disk dir, not Qdrant. |
| Aliyun on-disk `vdb_chunks.json` is **STALE** | live: mtime **2026-06-06**, `embedding_dim=3072`, `data_len=3294` (vs graphml today 32056 nodes / Qdrant chunks 3851). |
| Aliyun on-disk `vdb_relationships.json` is an **EMPTY 49-byte placeholder** | live: `ls` shows 49 bytes — the #41 converter OOM victim never wrote it. |
| Aliyun runtime freshness lives in **Qdrant**, which does NOT sync to Databricks | `OMNIGRAPH_VECTOR_STORAGE=qdrant` in Aliyun `.env` + kb-api override; Aliyun queries Qdrant, not on-disk vdb. |
| The converter that refreshes on-disk vdb from Qdrant is **dead** | `qdrant-snapshot.timer` = **disabled** (live); blocked by #41 OOM since 2026-06-05. |

**Consequence:** Aliyun's *queryable* storage (Qdrant) is aligned, but its *syncable* storage (on-disk nanovectordb) is stale-and-broken. Syncing it to Databricks transplants `graphml(32056 fresh)` + `vdb_chunks(3294 stale, June 6)` + `vdb_relationships(empty)` = the exact #44/#64 misalignment, just relocated. **The chosen path is blocked by the dead #41 converter.**

**Revised viable fix paths for #64 (both real, neither is the clean "sync aligned data" originally framed):**

- **Path B — serverless reindex Job (`reindex_lightrag.py --mode fullreindex`):** regenerates on-disk graphml + vdb **aligned-by-construction** on Databricks serverless (no OOM, no cross-border). Validated in kdb-2.5 (Run 4: ok=75/0%). **Blocker:** the job's provider is `EMBEDDING_DIM=1024` (`lightrag_databricks_provider.py:48`) but the deployed app expects **3072** (`app.yaml:51`, arx-2). Needs EITHER (a) re-point the job's embedding to the 3072 Vertex SA provider, OR (b) flip the whole Databricks app back to 1024 (undoes an arx-2 decision). Plus LLM re-extraction cost (~$17-40 at 75-article scale; larger for the full corpus).
- **Path A+ — fix #41 first, THEN sync:** fix the converter streaming-write (#41, ~50-100 LoC), regenerate Aliyun's on-disk vdb from its fresh Qdrant (now aligned to the fresh graphml), THEN `sync_to_databricks.sh`. Keeps 3072-dim, no re-extraction cost, but **pulls #41 into this phase's scope** (the phase becomes #64+#65+#41).

**This re-opens the fix-path decision** (the user's "sync-from-Aliyun" choice was made on the now-falsified premise). Re-posed below before CONTEXT is written.

---

## 4. Open questions for CONTEXT / planning
1. **#64 fix path:** sync-from-aligned-Aliyun snapshot (lower-risk, 3072-dim matched, no re-extraction cost) **vs** run `reindex_lightrag.py --mode fullreindex` on serverless (clean-build but dim=1024 in current provider → needs dim reconciliation + LLM re-extraction cost ~$17-40). Default recommendation: **sync-from-Aliyun**. Lock in CONTEXT.
2. **Sync mechanism:** which transport pushes Aliyun `lightrag_storage` → UC Volume? (`scripts/sync_to_databricks.sh` exists; verify it carries the vdb_chunks alignment, not just a stale archive.) The #44 root was a *stale* snapshot — the sync must capture the *current* aligned state.
3. **#65 root:** is `rerank_model_func` genuinely not reaching LightRAG's query path, or is `enable_rerank` unset at query time? The trace decides wire-it vs disable-it. Read `kb/api.py:_build_llm_rerank` + how LightRAG consumes `rerank_model_func` at aquery time.
4. **UAT acceptance:** what's the pass bar? Proposed: deployed backend log shows `Raw search results: >0 vector chunks` (no WEIGHT-fallback WARNING) AND (rerank wired → no "no rerank model configured" WARNING; OR disabled → warning gone) AND Deep Research iterations=1 still returns sources>0 + cited report.

---

## RESEARCH COMPLETE
