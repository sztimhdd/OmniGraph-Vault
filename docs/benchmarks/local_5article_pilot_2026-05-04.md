# Local 5-Article Pilot — New LightRAG Config (2026-05-04 / 05)

**Setting:** `.dev-runtime/` empty graph start, `batch_ingest_from_spider.py --max-articles 5`
**Config:** `embedding_func_max_async=4`, `embedding_batch_num=64`, `llm_model_max_async=4`, `max_parallel_insert=3`, `addon_params={"insert_batch_size":100}` (commit `e833206`, present at `ingest_wechat.py:218-222`)
**Goal:** Clean cold-graph multi-article data point. Complement to the single-article cold-run (`b47c29c`, article 337) where none of the 5 knobs activated, and to Hermes hot-graph batch run (independent context, not measured here).
**Run window:** 2026-05-04 23:59:54 → 2026-05-05 00:39:48 ADT (work-complete by last log line; process subsequently hung in D-10.09 async-drain and was manually killed).

## Result Summary

| metric | value |
|---|---|
| process wall-clock to last log line (work-complete) | **2394 s (~39.9 min)** |
| `batch_timeout_metrics.total_elapsed_sec` (internal self-report) | 2377.29 s |
| `avg_article_time_sec` (internal, 5 ok articles) | 222.43 s |
| `timeout_histogram` (5 ok articles bucketed) | 1× 0-60s, 3× 60-300s, 1× 300-900s, 0× 900s+ |
| articles `ok` / `skipped` / `failed` | 5 / 23 / 0 |
| candidates iterated through | 28 (to reach 5 ok) |
| graph nodes (start → end) | 0 → **253** |
| graph edges (start → end) | 0 → **309** |
| `vdb_entities.json` | 0 → **6,034 KB** (6,183,310 B) |
| `vdb_relationships.json` | 0 → **7,371 KB** (7,548,186 B) |
| `graph_chunk_entity_relation.graphml` | 0 → **245 KB** (250,374 B) |

## Per-Article Timing

5 articles ingested successfully. Per-article processing time as bucketed by the pipeline's internal `timeout_histogram` (authoritative; mapped from per-article timers, not from inter-ingest DB gaps).

| # | DB id | article_id | body chars | title (truncated) | DB `ingested_at` | Δ since start | Δ since prev ok |
|---|---|---|---:|---|---|---:|---:|
| 1 | 212 | 340 | 10,377 | 开源「洁癖.skill」，让你的Agent越用越聪明。 | 00:05:53 | 359 s | — |
| 2 | 222 | 358 |  4,626 | JoyInside 创新大赛现场，我看到 AI 硬件长出了灵魂 | 00:11:37 | 703 s | 344 s |
| 3 | 226 | 365 | 12,200 | 小米白送了我 16 亿 tokens！... | 00:25:15 | 1521 s | 818 s |
| 4 | 227 | 366 |  4,707 | 红杉 AI 大会2026：工作方式，彻底变了 | 00:27:42 | 1668 s | 147 s |
| 5 | 237 | 376 |  4,431 | 2026年AI最火的三个技术方向 | 00:37:38 | 2264 s | 596 s |

**Caveats on the gap columns:** "Δ since prev ok" includes the wall-clock spent on every `skipped` candidate the pipeline had to iterate through before the next successful scrape. It is **not** equivalent to "time to ingest this article alone." For per-article ingest cost in isolation, see the histogram (1× <60s, 3× 60-300s, 1× 300-900s) — that's the pipeline's own timer over `ainsert` per article, with no skip overhead included.

## Per-Article Trend

5 ok articles is too few to fit a curve, and gross body-length is the strongest variable in our sample (range 4,431 – 12,200 chars, 2.75× spread). The histogram bucketing is consistent with body-length being the dominant per-article variable: only the 12,200-char article fell in the 300-900s bucket, the smallest (~4,431 char) is plausibly in the 0-60s bucket. **At N=5, no observable trend of per-article time rising with graph size N.** This dataset cannot resolve scaling order — that is the v3.4 benchmark's job (see `docs/lightrag_scaling_benchmark_spec.md`).

## Anomalies / Observations

- **Apify scrape success rate 5/28 (~18%)** for this candidate slice. The other 23 candidates all hit the same path: Apify Actor returned HTTP 200 / `Status: SUCCEEDED`, but content-extraction layers all returned None ("`scraper: all 4 wechat layers returned None`") → classified `skipped` per D-10.04 (no fail-open). This is unrelated to LightRAG config — it is an upstream WeChat / Apify content-availability signal at this point in time.
- **0 timeouts, 0 fail-opens, 0 RuntimeError, 0 actual 429** events. Two regex hits on "429" are both false positives (one ms timestamp ending `.429Z`, one hex hash containing `429`).
- **OpenRouter Vision returns `desc_chars=0` on 24 / 67 image_processed events (~36%)**. Cascade still marks `outcome=success` and continues — the pre-existing image_pipeline reporting quirk noted in `CLAUDE.md`. Not blocking, not config-related.
- **D-10.09 async-drain hang at end-of-batch.** "Vision drain timeout — 0/10 task(s) still pending (cancelling)" fired at 00:39:33; "Metrics written" at 00:39:48; process did not exit on its own and was killed manually after 22 minutes of no log activity. This is a pre-existing known issue (CLAUDE.md "Known but non-blocking") and inflates raw process-exit wall-clock; the work-complete wall-clock (2394 s) is the honest measurement.
- **Pre-scrape guard hits: 0** (all skips were from D-10.04 post-scrape "no content" path, not from the `OMNIGRAPH_PRE_SCRAPE_SKIP*` guard).

## Comparison Anchors

Old-config single-article cold-run baselines (already on file):

| run | art_id | body | config | wall-clock | source |
|---|---:|---:|---|---:|---|
| Quick 260504-g7a smoke | 332 | 10,303 | old | 382 s | (committed in g7a SUMMARY) |
| Quick 260504-lt2 smoke | 333 | 18,380 | old | ~393 s | (lt2 internal metric) |
| Quick 260504-x9b cold-run | 337 | 10,312 | new | 493 s | `b47c29c` cold_run report |
| **this pilot, 1st article (340)** | **340** | **10,377** | **new** | **359 s** (Δ since start) | this report |
| **this pilot, 5 ok total** | — | — | new | 2394 s wall-clock / 222.43 s avg-per-article | this report |

The 1st-article number (359 s for article 340 at 10,377 chars) is the closest single-article anchor in this pilot to the prior 1-article cold-run measurements, and it includes some scrape-skip overhead (2 skips before article 340 was reached). Single-article-in-batch is not the same shape as standalone single-article cold-run — interpretation is for the user.

**No "X× faster / X× slower" claim is being made.** The 5 new-config knobs target multi-article concurrency (`max_parallel_insert=3`, `embedding_batch_num=64`, etc.); whether they activated meaningfully here depends on intra-batch parallelism the histogram alone cannot reveal.

## Per-Article File Size Growth (NOT measured)

The task brief asked for per-article snapshots of `vdb_entities.json` / `graphml` after each article. **This pilot did not instrument per-article snapshots** — only end-state file sizes are captured (table above). Per-article growth curves are an instrumentation gap and would require either (a) checkpoint-based copying mid-run, or (b) modifying `batch_ingest_from_spider.py` (out of scope per HARD NOs). Recorded as a known instrumentation gap.

## Reproducibility Pointers

- **Raw log:** `.dev-runtime/logs/pilot-5art-20260504-2359.log` (251 KB, 3086 lines, gitignored)
- **Pipeline-internal metrics:** `data/batch_timeout_metrics_20260505_000001.json` (gitignored)
- **DB rows (since reset, `ingestions.id > 209`):** 28 rows (5 ok / 23 skipped) — preserved in `.dev-runtime/data/kol_scan.db`
- **Pre-run reset:** `rm -rf .dev-runtime/{lightrag_storage,checkpoints,images}/*` (DB preserved)
- **Run command:** `venv\Scripts\python .dev-runtime\run_local.py batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2 --max-articles 5`
- **Config commit:** `e833206 perf(ingest): tune LightRAG concurrency knobs — 5-knob config` (verified in `ingest_wechat.py:218-222` before run)
- **Active env vars:** `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`, `OMNIGRAPH_BASE_DIR=.dev-runtime`, `KOL_SCAN_DB_PATH=.dev-runtime/data/kol_scan.db`, `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow` (loaded by `.dev-runtime/.env` via `.dev-runtime/run_local.py`)

## Conclusion (one sentence)

**Inconclusive on whether the 5 new-config knobs delivered meaningful multi-article speedup;** dataset gives a clean 5-article cold-graph data point (2394 s end-to-end / 222.43 s avg-per-article / 253 nodes / 309 edges) for use as a comparison baseline once Hermes hot-graph numbers land or once the v3.4 scaling benchmark (per `docs/lightrag_scaling_benchmark_spec.md`) instruments per-stage timing.
