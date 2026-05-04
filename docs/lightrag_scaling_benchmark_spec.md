# LightRAG Scaling Benchmark — Design Spec

**Status:** draft
**Author:** spec-only (no implementation)
**Audience:** engineer tasked with implementing and running the benchmark
**Date:** 2026-05-04
**Target graph:** `.dev-runtime/lightrag_storage/` (Windows local dev box, isolated from Hermes)

---

## 1. Goal & Success Criteria

**Goal.** Determine the asymptotic scaling order `k` of LightRAG ingest latency
as a function of graph size `N` (nodes), and attribute the slope to one (or
several) of four candidate root-cause hypotheses. The benchmark must produce
**actionable numbers** — not just a suspicion.

**Why this matters.** Empirical observation: single-merge latency grows from
~5 min at 3 articles to 40+ min at 6 articles; Hermes stalled entirely at 562
nodes. The shape (super-linear? quadratic? exponential above a threshold?)
determines whether the fix is "tune config + parallelize embeddings" or
"change graph backend / shard by topic" — two very different scopes.

**Done when all four hold.**

1. A `time_per_article = f(N_nodes)` curve, fitted to a power law
   `t ≈ a · N^k`, is produced for **each** of the three configuration states
   (§3). 3 × `k` values in hand.
2. A per-stage time breakdown (extract / merge / vdb_upsert / graphml_save /
   summary_LLM) is produced for **State 2** (post-refactor), showing which
   stage dominates at large `N`.
3. Hypothesis attribution percentages (§5) are computed from the numbers
   above, not hand-waved.
4. The Go/No-Go decision (§7) maps cleanly onto one of three follow-up
   paths: config-only, structural (vdb/graph backend), or stack-level
   reconsider.

**Confidence target.** `k` must be fitted with R² ≥ 0.9 on ≥8 sample points
per state. That's the minimum to distinguish `k=1.2` from `k=1.7`. Fewer
samples = the entire decision collapses to "feels slow."

---

## 2. Environment

**Location.** `.dev-runtime/` on the local Windows dev box. All three states
run here. Hermes is untouched (Day-1 cron tmux `pid 636368` must remain
undisturbed; see memory `hermes_agent_cron_timeout.md`).

**Article pool.** `.dev-runtime/data/kol_scan.db` (scp'd from Hermes,
2026-05-04; 563 articles / 734 classifications / 81 ingestions / 53 accounts).
Select a **fixed, shared sequence** of 20 articles by `articles.id ASC` with
`topic_filter IN ('openclaw','hermes','agent','harness')` AND
`min_depth >= 2`. The *same* 20 articles, *same* order, for every state —
otherwise cross-state comparability breaks.

**Reset to empty graph.** Before each state's run:

```
rm -rf .dev-runtime/lightrag_storage/*
rm -rf .dev-runtime/images/*
rm -rf .dev-runtime/checkpoints/*
```

No flags, no partial resets. Every state starts from `N_nodes=0`.

**Run depth.** 20 articles per state. Based on current data (100 nodes after
2 articles → ~50 nodes/article locally), 20 articles gets us to ~1000 nodes —
well past where Hermes stalled (562). If the curve is already flat by
article 10, we can stop early and save wall-clock; the spec must not
**require** all 20.

**Stopping rules.** Stop a state's run when **any** of these fire:

- 20 articles complete
- **S1 / S2** single-article wall-clock exceeds **45 min** (hard ceiling;
  bigger than that means LightRAG has effectively stopped making progress)
- **S0** single-article wall-clock exceeds **90 min** (soft ceiling —
  doubled from S1/S2 because S0 is known-slow and will plausibly hit
  40min+/article by article 6-7; capping at 45min would starve S0 of enough
  samples to plot at all). S0 runs may produce as few as **5** samples —
  that's acceptable because S0 is a sanity-check curve, not the
  decision-driving one (see §7).
- Disk usage on `.dev-runtime/lightrag_storage/` exceeds 2 GB (tells us
  storage blowup is the real issue; switch to disk-only diagnostics)

**What's frozen.**

- **Active env:** `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`,
  `OMNIGRAPH_BASE_DIR=c:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime`,
  `KOL_SCAN_DB_PATH=.dev-runtime/data/kol_scan.db`,
  `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow` — all loaded by
  `.dev-runtime/.env` (Quick 260504-g7a / 260504-lt2 gates already landed on
  `origin/main` through commit `d8c02c3`).
- **LLM:** Vertex Gemini (`gemini-3.1-flash-lite-preview`) — SA auth, no
  Cisco Umbrella breakage.
- **Embedding:** `gemini-embedding-2` @ 3072 dim, global endpoint, SA auth.
- **Vision cascade:** OpenRouter → Gemini (SiliconFlow skipped).
- **LightRAG version:** `lightrag-hku==1.4.15` pinned in `requirements.txt`.
  DO NOT upgrade during the benchmark window — staged-timing instrumentation
  requires monkey-patch hooks that bind to internal LightRAG function names,
  and those names may change across versions. Upgrade is a post-benchmark
  task.
- Keep 2 known-but-non-blocking issues visible so the engineer doesn't chase
  them: (a) async-drain hang after `batch_ingest` finishes (pre-existing
  D-10.09 — benchmark timer must stop **before** the hang, at "last article
  ingested" event); (b) OpenRouter vision `desc_chars=0` but cascade marks
  success (reporting quirk in `image_pipeline`, unrelated to scaling).

**Expected wall-clock budget.** This is overnight work, not a session task.

| State | Article count | Est. per-article | State total |
|-------|---------------|------------------|-------------|
| S0 — baseline, serial loop, current config | ≤ 20 (may stop at 5-10) | Starts ~5 min, reaches 40+ min by art. 6-7 (per Hermes observation at 562 nodes) | **10-15 h** |
| S1 — config-only (parallelized throttle, still serial embed) | ≤ 20 | 1.5-3× faster than S0's constant | **5-8 h** |
| S2 — config + batch-API refactor (serial loop removed) | ≤ 20 | Another 10-20× faster on embed stage | **2-4 h** |
| **Total** | 60 runs | — | **15-30 h wall-clock** |

Plan an overnight run (S0) + next-day run (S1 + S2 back-to-back). Don't try
to land all three in one working day — the hard ceilings exist specifically
because we expect S0 to be painful. Budget separately for 1-2 h of pilot
work (see below) before the real runs start.

---

## 3. Three-State Configuration Comparison

The central design decision: we run the **same** benchmark three times, with
increasingly aggressive config/code, to separate "constant" from "order."

| State | Config | Serial embed loop? | Purpose |
|-------|--------|--------------------|---------|
| **S0 Baseline** | `embedding_func_max_async=1`, `embedding_batch_num=20`, `llm_model_max_async=2` (current `ingest_wechat.py:216-218`) | **Yes** (unchanged) | Reproduces the observed regression. Fix point for all comparisons. |
| **S1 Config-only** | `embedding_func_max_async=4`, `embedding_batch_num=64`, `llm_model_max_async=4` | **Yes** (unchanged) | Tests whether Hermes's low-risk config alone is enough. Serial loop still present. |
| **S2 Config + Batch** | Same as S1, PLUS `lib/lightrag_embedding.py:207` rewritten: `for text in texts` → `asyncio.gather(_embed_once(t) ...)` OR a Vertex native batch-embed call (one API call, N texts). | **No** (refactored) | Tests whether serial embed was the remaining bottleneck. |

**Predictions (useful as a sanity check, not as a result).**

- S0 → S1: constant speedup ~1.5–3× from parallelism alone.
- S1 → S2: constant speedup another 10–20× on the embed stage (single API
  call per batch vs. 20 serial).
- **`k` should be approximately the same across all three states.** Config
  changes the constant; they do **not** change the underlying super-linear
  driver. If `k` moves meaningfully between states, the experiment has
  told us something surprising — re-audit hypotheses A/B/C because one of
  them is sensitive to concurrency in a way we didn't predict.

**What S2's batch-API refactor looks like, at spec level** (no code here — the
engineer writes it):

- Collapse `lib/lightrag_embedding.py:206-244` — the `for text in texts:`
  loop + per-text rotation — into a single batched path.
- Vertex `google.genai` SDK supports passing a list of `Content` objects per
  call; prefer that over `asyncio.gather` of N singletons if the SDK can do
  it in one HTTP round-trip.
- 429 behavior must be preserved: on batch 429 → back off + retry whole
  batch. Per-text rotation is no longer meaningful with SA auth (pool size
  1 in Vertex mode — already documented in `lib/lightrag_embedding.py:201-204`).
- **Out of scope for the spec itself** — the refactor is a separate Quick
  task post-benchmark. The spec only needs to **describe** what S2 looks
  like so the engineer knows what to build.

### Pilot run (mandatory before the real benchmark)

The "~50 nodes/article" expectation in §2 is extrapolated from 2 articles
(100 nodes total) on this local graph. Hermes observed ~90 nodes/article at
its scale — a 2× discrepancy. Article richness, chunking, and the
extract-LLM's verbosity all shift the real nodes/article constant, and it
matters: if the constant is lower than assumed, 20 articles may not even
reach 562 nodes (Hermes's stall point), and the benchmark ends before it
can tell us anything about the regime we care about.

**Procedure.**

1. Run S2 only (cheapest config) for **5 articles**, NO graph reset
   between them.
2. Record `N_nodes_after` at each step → compute avg nodes/article for
   this local corpus.
3. Extrapolate linearly to 20 articles. If the forecast is **< 600 nodes**,
   expand the benchmark to 25-30 articles (still enforce §2 stopping rules
   per state).
4. Write a 1-page report to
   `docs/benchmarks/lightrag_scaling_pilot_<YYYYMMDD>.md` containing:
   the 5 per-article node counts, the fitted constant, the recommended
   article count for the real run, and a one-line GO signal. Keep the
   pilot graph state; **do not commit it** to the real benchmark — reset
   before S0.

The pilot's own data does **not** go into the headline §6 plots. It
calibrates the sample size, nothing more. Pilot wall-clock budget: 1-2 h.

---

## 4. Measurement Methodology

Per article, emit **one structured log row** (JSONL is fine) with all fields
below. Record at "article N complete" event. Rows accumulate to a single
`benchmark_<state>_<timestamp>.jsonl` file.

### Required metrics (every article, every state)

| Category | Field | Source |
|---------|-------|--------|
| **Size** | `article_idx` (1..20), `N_nodes_before`, `N_nodes_after`, `N_edges_before`, `N_edges_after` | count from `graph_chunk_entity_relation.graphml` pre/post |
| **Timing (wall)** | `total_ingest_sec` | `time.perf_counter()` around the whole `rag.ainsert` |
| **Timing (staged)** | `extract_sec`, `merge_sec`, `vdb_upsert_sec`, `graphml_save_sec`, `summary_llm_sec` | Instrument LightRAG's internal phase boundaries (may require monkey-patch hooks since LightRAG doesn't emit these natively — document this in the implementation). |
| **LLM calls** | `llm_extract_count`, `llm_merge_summary_count`, `llm_chunk_summary_count` | Wrap the dispatched LLM func to count by call-site tag |
| **Embedding** | `embed_api_call_count`, `embed_text_count`, `embed_avg_batch_size`, `embed_total_tokens` | Wrap `embedding_func` |
| **Disk I/O** | `vdb_entities_bytes_before/after`, `vdb_relationships_bytes_before/after`, `graphml_bytes_before/after` | `os.stat` pre/post |

### Sampling cadence

- **Every article** produces one JSONL row (not every 2). 20 articles × 3 states = 60 rows — easy to plot, easy to fit.
- **Every 5 articles** snapshot the three storage files (`cp` to
  `benchmark_snapshots/state_<X>_art_<N>/`) so we can re-inspect disk growth
  post-hoc without re-running.

### Non-metrics (deliberately excluded to keep noise out)

- No CPU / memory profiling. Ingest is I/O + API bound; CPU is not the
  bottleneck hypothesis. Adds noise to wall-clock.
- No GPU metrics (no local GPU used).
- No network-level packet capture.

---

## 5. Hypothesis Attribution Method

We have four candidates. Each leaves a distinct fingerprint.

| Hypothesis | Fingerprint that confirms it | Fingerprint that rules it out |
|-----------|-------------------------------|-------------------------------|
| **S** — serial embed loop (`lib/lightrag_embedding.py:207`) | **S0 vs S1 vs S2** total-time curves separate by ≥10× at large N; S2 curve is much flatter in absolute terms. | If S2's curve is still steep (same `k`), S was never the main driver — only a constant. |
| **A** — nano-vectordb JSON full rewrite | `vdb_upsert_sec` > 30% of `total_ingest_sec` at N=1000, growing linearly with `vdb_entities_bytes_after`. | If `vdb_upsert_sec` stays ~constant or grows sub-linearly: A is not the driver. |
| **B** — NetworkX `.graphml` full serialization | `graphml_save_sec` grows with `graphml_bytes_after` (linear in node count) AND becomes >20% of `total_ingest_sec` at large N. | If `graphml_save_sec` stays tiny (<5% of total) throughout: B is not the driver. |
| **C** — `description_list` + `FORCE_LLM_SUMMARY_ON_MERGE=8` | `llm_merge_summary_count` per article **grows with N** (not constant). `extract_count` stays roughly flat. | If summary calls stay proportional to new entities per article (constant slope, not rising): C is not the driver. |

### Attribution procedure (once numbers are in)

1. Use **S2** (noise floor; serial-loop constant removed) as the clean
   substrate for A/B/C analysis.
2. Compute `k` via log-log regression of `total_ingest_sec` vs `N_nodes_after`
   for S2. That's the structural order.
3. Per-stage shares: average `stage_sec / total_ingest_sec` over the last 5
   articles (when N is largest, hypothesis differences are loudest).
4. Express as an attribution table:

```
S state 2 — after serial-loop fix applied
───────────────────────────────────────────
Stage                  Share at N≈1000   Scaling order (log-log k)
extract_sec               X.X%              k≈...
merge_sec                 X.X%              k≈...
vdb_upsert_sec            X.X%              k≈...
graphml_save_sec          X.X%              k≈...
summary_llm_sec           X.X%              k≈...
```

The stage with the highest `k` **AND** highest share at N≈1000 is the
dominant structural driver. If two stages are close, report both — no
arbitrary single-winner pick.

---

## 6. Data Products

**D1 — Three-state scaling overlay.** Single PNG:
- X-axis: `N_nodes_after` (log)
- Y-axis: `total_ingest_sec` (log)
- Three lines (S0, S1, S2), each with fitted power-law + its `k` value in
  legend.
- **This is the headline chart.** It answers "is k the same across states?"
  at a glance.

**D2 — Stage breakdown stacked area chart (S2 only).** X-axis: article index
1..20 (ordinal), Y-axis: seconds, stacks: extract / merge / vdb_upsert /
graphml_save / summary_llm. Use S2 because the serial-embed noise is gone
and the real growing stages surface cleanly.

**D3 — Attribution table** (format shown in §5). One table per state; S2's is
the one that drives the decision.

**D4 — Disk growth supplementary plot.** X-axis: articles, Y-axis: bytes, two
lines: `vdb_entities` + `graphml`. Used to corroborate hypotheses A and B.

All four products + the raw JSONL go into
`docs/benchmarks/lightrag_scaling_<YYYYMMDD>/` — committed to git (JSONL is
small, graph state snapshots go to `.gitignore`).

---

## 7. Go / No-Go Thresholds

**Decision is driven by `k` from State 2** — that's the "serial embed fixed"
baseline. S0/S1 `k` values are sanity checks; don't make the call on them.

| S2 `k` | Decision | Action |
|-------|---------|--------|
| **≤ 1.1** | **GREEN** — near-linear after serial fix | Land the S2 refactor + the S1 config bumps as production defaults. v3.4 milestone can open on top of this. No structural rework needed. |
| **1.1 – 1.5** | **YELLOW** — super-linear but not catastrophic | Ship S2 anyway (it's a free win), but start a parallel track: (a) per-topic sharding (split graph by article topic → keep per-shard N small) OR (b) swap nano-vectordb for LanceDB (direct fix for hypothesis A). Attribution table tells us which of the two to pick. |
| **≥ 1.5** | **RED** — structural blowup | Don't patch; reconsider. Candidates: swap NetworkX→Neo4j/Postgres graph backend (fixes B), or re-evaluate whether LightRAG itself is the right KG engine at this scale. This is a v3.5+ conversation, not a v3.4 hotfix. |

**Why `k ≤ 1.1` for GREEN (not 1.2 or 1.0).** LightRAG advertises
"incremental update without full reprocessing." A system that actually
delivers that should land at `k ≈ 1.0`. Setting GREEN at `1.2` means
accepting a 16× slowdown at 10× nodes (100 → 1000), which directly
contradicts the incremental claim; `1.1` is 12.6× at 10×, still
super-linear but small enough to credibly match the marketing. `k = 1.0`
exactly is likely unachievable given nano-vectordb + NetworkX graphml
full-rewrite semantics, so we give a small slack band [1.0, 1.1] rather
than demanding a flat line.

**Edge cases.**

- **Decision only reads S2 `k`.** S0 / S1 `k` values exist only to confirm
  the "constant vs. order" story (same `k` across states ⇒ config doesn't
  alter structural scaling). S0's coarser fit (as few as 5 samples per §2)
  does not invalidate the Go/No-Go call.
- If **S2's** fit has R² < 0.9, **do not** report `k`. The curve is too
  noisy; more samples needed, or graph is showing threshold behavior (e.g.
  fine until N=500, then cliff). Switch to qualitative reporting + flag the
  cliff. S0/S1 R² < 0.9 is tolerable — treat those fits as qualitative.
- If S2 ran to the 45-min/article hard stop before N=500, that's itself a
  **RED** outcome regardless of `k` — we never got clean data because the
  degradation is worse than assumed.

---

## Appendix A — Explicitly OUT of scope for this spec

- Benchmark implementation (Python code). This is a spec. Implementation is
  a separate Quick task.
- Any code change to `lib/lightrag_embedding.py`, `ingest_wechat.py`, or the
  LightRAG library itself. State 2's batch refactor is **described** here
  (§3), not done.
- SSH to Hermes. Hermes is untouched.
- `run_uat_ingest.py:13` / `scripts/seed_rss_feeds.py:21` hardcoded-path
  cleanup (deferred from Quick 260504-lt2; unrelated to benchmark).

## Appendix B — Claims deliberately NOT used

To avoid baking disputed remote reports into the spec:

- "Hermes ingested 1000 docs in 11 min" — not used.
- "16,860 LLM calls observed" — not used.
- "`FORCE_LLM_SUMMARY_ON_MERGE` defaults to 1" — not used.

The spec uses **only** the locally verified facts (`lib/lightrag_embedding.py:207`
serial loop, current `.dev-runtime/lightrag_storage/` file sizes, 2 articles
→ 100 nodes local baseline).

---

*End of spec.*
