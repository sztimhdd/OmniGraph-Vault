# Cold-run New Config — Single Article Measurement

**Date:** 2026-05-04 (run 23:14 ADT)
**Config commit:** `e833206` (`perf(ingest): tune LightRAG concurrency knobs — 5-knob config`)
**Config values:** `embedding_func_max_async=4`, `embedding_batch_num=64`, `llm_model_max_async=4`, `max_parallel_insert=3`, `addon_params={"insert_batch_size":100}` (`ingest_wechat.py:218-222`)
**Command:** `venv\Scripts\python .dev-runtime\run_local.py batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2 --max-articles 1`
**Article picked by pipeline:** `article_id=337` — *"我用 Tabbit 浏览器搭了一套内容创作全自动流水线，太香了！"*
*(IDs 334/335/336 were re-classified as failing the topic/depth filter and skipped; 337 was the first match.)*

## Measurement

| metric | value |
|---|---|
| wall-clock total (process start → exit) | **493.242 s** |
| `batch_timeout_metrics.total_elapsed_sec` (internal) | 476.28 s |
| status | `ok` (`ingestions.id=209`) |
| article body length | 10,312 chars |
| chunks extracted | 6 (main doc) + 1 (spider sub-doc) |
| graph nodes after | 38 |
| graph edges after | 44 |
| `vdb_entities.json` | 906 KB |
| `vdb_relationships.json` | 1049 KB |
| `graphml` | 35 KB |
| entities merged | 35 (main) + 4 (sub) |
| relations merged | 41 (main) + 3 (sub) |

## Comparison to old-config baselines

| run | art_id | body | config | wall-clock | speedup vs g7a |
|---|---:|---:|---|---:|---:|
| Quick 260504-g7a smoke | 332 | 10,303 | old | 382 s | 1.00× (ref) |
| Quick 260504-lt2 smoke | 333 | 18,380 | old | ~393 s¹ | 0.97× |
| **this run** | **337** | **10,312** | **new** | **493 s** | **0.77×** |

¹ derived from `data/batch_timeout_metrics_20260504_155512.json` `total_elapsed_sec=393.11` (lt2 internal metric, ≈ wall-clock).

**Article 337 is body-length-matched to article 332 (10,312 vs 10,303 chars)** — the cleanest like-for-like.

## Caveats

- Only 1 data point per config — not statistically significant.
- Three different articles, similar but not identical content shape. Chunk count for the baselines is unrecorded.
- Network conditions differ (g7a/lt2 ran 15:55–16:00 ADT; this run 23:14 ADT). MCP fallback retried twice this run with `0 chars` returns before falling back to attempt 2 — added some seconds.
- Spider phase (downstream URL discovery + 2nd ingest) is included in all three measurements equally; not isolated.
- Serial embed loop (`lib/lightrag_embedding.py:207`) NOT touched per HARD NO — that's the S2-refactor lever, deliberately out of scope.
- Hermes 50.5× number deliberately excluded (cache+pollution confounded).

## Why "speedup" is the wrong question for this test

The 5 new knobs all target **multi-article batch concurrency**:

| knob | activates when… | this run had… |
|---|---|---|
| `embedding_func_max_async=4` | concurrent embedding requests across docs | 1 doc, sequential per-text (serial loop unchanged) |
| `embedding_batch_num=64` | LightRAG hands ≥64 texts at once | 6 chunks → ≪64 |
| `llm_model_max_async=4` | concurrent LLM calls (extract/merge) | 6 sequential extracts (1 doc) |
| `max_parallel_insert=3` | ≥3 docs in flight | 1 doc |
| `insert_batch_size=100` | per-batch chunk count > 100 | 6 chunks |

**None of the five knobs meaningfully activate for `--max-articles 1`.** The 0.77× ratio is best read as "config has small dormant overhead at N=1," not "new config is slower."

## Conclusion (one sentence)

**Inconclusive.** Single-article cold-run is structurally not where this config can show its strengths; the right next experiment is a multi-article batch (e.g., `--max-articles 5` or `--max-articles 10`) on a fresh empty graph, where the concurrency knobs have something to chew on. **Do not rollback `e833206` based on this number alone** — the per-knob activation table above shows why a single article can't validate or invalidate the change.

## Reproducibility pointers

- raw log: `.dev-runtime/logs/coldrun-new-config.log` (gitignored)
- elapsed timings: `.dev-runtime/logs/coldrun-elapsed.txt` (gitignored)
- internal metrics file: `data/batch_timeout_metrics_20260504_231429.json` (gitignored)
- old-config comparator: `data/batch_timeout_metrics_20260504_155512.json` (gitignored)
- pre-run reset: `rm -rf .dev-runtime/{lightrag_storage,checkpoints,images}/*`
- DB row inserted: `ingestions.id=209 article_id=337 status=ok ingested_at='2026-05-04 23:20:25'`
