---
phase: 05-pipeline-automation
plan: 03b
subsystem: rss-ingest
tags: [wave1, rss, ingest, deepseek, translate, d-07-revised, d-19, anti-ghost]
status: complete
created: 2026-05-02
completed: 2026-05-02
---

# Plan 05-03b SUMMARY — RSS ingest (direct translate → ainsert, D-19 hook)

**Status:** Complete (local; real-article smoke deferred to Hermes)
**Wave:** 1
**Depends on:** 05-03 (classifications populate `depth_score >= 2`)

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 3b.1 | `enrichment/run_enrich_for_id.py` (KOL bridge + RSS guarded no-op) | 5 unit tests pass |
| 3b.2 | `enrichment/rss_ingest.py` (DeepSeek translate + Task 4.2 PROCESSED gate) | 8 unit tests pass |

## 2. Behaviors verified

### 3b.1 — `run_enrich_for_id.py` (5 tests)

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_kol_path_invokes_skill_with_env_vars` | subprocess called with `["hermes","skill","run","enrich_article"]` + ARTICLE_PATH/URL/HASH env keys set |
| 2 | `test_rss_guarded_noop_does_not_invoke_skill` | `--source rss` exits 0, **subprocess.run NOT called**, stdout contains "RSS excluded per D-07 REVISED" |
| 3 | `test_kol_missing_article_exits_nonzero` | unknown `--article-id` → rc=2, subprocess NOT called |
| 4 | `test_subprocess_args_use_env_not_cli_flags` | no `--article-id`/`--source` in the skill invocation — regression guard against SKILL.md contract breakage |
| 5 | `test_invalid_source_argparse_errors` | argparse `choices=['kol','rss']` enforced (SystemExit rc=2) |

### 3b.2 — `rss_ingest.py` (8 tests)

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_english_article_triggers_translate` | English body → `_translate_to_chinese` called once; Chinese written |
| 2 | `test_chinese_article_skips_translation` | langdetect 'zh-cn' → 0 translate calls; body passes through |
| 3 | `test_original_md_written_before_final` | both `original.md` (English source) and `final_content.md` (Chinese) exist |
| 4 | `test_atomic_write_uses_os_replace` | every `os.replace` call has a `.tmp` source path |
| 5 | `test_enriched_set_to_2_on_processed` | happy path: `_ingest_lightrag → True` → `UPDATE rss_articles SET enriched=2` |
| 6 | `test_non_processed_leaves_enriched_unchanged` | **D-19 anti-ghost gate**: `_ingest_lightrag → False` → `enriched` stays at 0, NOT set to 2, NOT set to -2 |
| 7 | `test_subprocess_never_invoked` | **D-07 REVISED hard guard**: `subprocess.run` + `subprocess.Popen` patched; call counts both 0 |
| 8 | `test_dry_run_no_writes_no_translate` | `--dry-run` writes nothing, does not resolve API key, does not translate |

## 3. D-07 REVISED compliance (RSS excluded from enrichment)

| Check | Result |
|-------|--------|
| `rss_ingest.py` imports `subprocess`? | No (static grep `subprocess.py:0`) |
| `rss_ingest.py` mentions `run_enrich_for_id`? | No (grep `0`) |
| `rss_ingest.py` ever calls `subprocess.run`/`Popen`? | No (runtime check via Test 7) |
| `run_enrich_for_id.py --source rss` short-circuits before DB+subprocess? | Yes (Test 2 — stdout marker + `mock_run.assert_not_called`) |
| Print marker "RSS excluded per D-07 REVISED"? | Yes (audited grep: `1`) |

## 4. D-19 anti-ghost verification hook

```python
# rss_ingest.py::_ingest_lightrag (excerpt, final block)
statuses = await rag.aget_docs_by_ids([doc_id])
entry = (statuses or {}).get(doc_id)
status_val = getattr(entry, "status", None) or (entry.get("status") if isinstance(entry, dict) else None)
if str(status_val).upper() != PROCESSED_STATUS:
    logger.warning(
        "rss_id=%s post-ingest status=%r (expected %s) — leaving rss_articles.enriched unchanged",
        rss_article_id, status_val, PROCESSED_STATUS,
    )
    return False
return True
```

This matches `ingest_wechat.py:1086-1120` (Task 0.8 pattern, commit
`585aa3b`). The `enriched=2` write is gated on the True return. On
False, the caller's `stats["errors"]` increments but the row retains
its prior value (default 0) so the next batch retries naturally.

## 5. Phase 7 D-09 supersession compliance (LLM → DeepSeek)

| Check | Result |
|-------|--------|
| `api.deepseek.com` present | Yes |
| `from batch_classify_kol import get_deepseek_api_key` | Yes (reuses production key resolver) |
| `google.genai` import | No |
| `from google import genai` | No |
| `GEMINI_API_KEY` reference | No |
| Translation prompt is Chinese-output | Yes (`_TRANSLATE_PROMPT` instructs Chinese Markdown with preserved code/URLs) |

## 6. State-machine simplification

Per D-19, `rss_articles.enriched` has **only two terminal states** in the
RSS path:

| Value | Meaning |
|-------|---------|
| 0     | pending (default; also the retry state after a failed PROCESSED gate) |
| 2     | ainsert + PROCESSED confirmed |

The `-2` "enrichment failed" Phase 4 state is **not used** by the RSS
path — enrichment is not attempted, and failed ingests stay at 0 for
natural retry. Static audit: `grep -c "enriched = -2" → 0`.

## 7. Dependencies on v3.1 / v3.2 infrastructure

- **`lib.lightrag_embedding.embedding_func`** — 3072-dim Vertex AI path,
  already adopted by Wave 0.
- **`lib.deepseek_model_complete`** — DeepSeek LightRAG LLM wrapper.
- **`config.BASE_DIR` / `config.RAG_WORKING_DIR`** — both monkeypatched
  in tests so no runtime dependency on `~/.hermes/omonigraph-vault/`.
- **`LightRAG.aget_docs_by_ids`** — D-19 contract; runtime gate mocked
  via `_ingest_lightrag` patching in unit tests. Real-batch verification
  is Hermes-side (below).
- **Checkpoint guards (v3.2 Phase 12)** — intentionally NOT wired into
  `rss_ingest.py` for this plan. The text-only RSS path (summary →
  translate → ainsert) has a single I/O stage; checkpoint per-article
  would add state-file churn without benefit. 05-04 step_7 inherits
  checkpointing via `batch_ingest_from_spider.py` for KOL articles
  anyway. If operational data shows RSS-side resume is needed, wire
  checkpoints then.

## 8. Known caveats

- **`_resolve_rss` helper retained** in `run_enrich_for_id.py` but not
  called by `main()`. It preserves path-derivation parity with
  `_resolve_kol` in case a future decision re-enables RSS enrichment.
  Reviewer may delete; non-load-bearing.
- **Single-process batch**: `rss_ingest.py` processes articles
  sequentially. With translation at ~10s/article + LightRAG ingest at
  ~30s/article, expect ~40s/article × N. Real-batch capacity decision
  deferred to 05-06 cron tuning.
- **Body source**: `rss_ingest.py` uses `rss_articles.summary` (the
  feedparser summary) as the ingest body. Some RSS 2.0 feeds put the
  full content in `<content:encoded>` instead; `rss_fetch._content_text`
  already picks the largest body but stores it in `summary`. If a feed
  is observed to store content only in `content` → investigate
  `rss_fetch.py` separately; no change here.

## 9. Hermes-side verification (operator to run)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/python -m pytest \
  tests/unit/test_rss_schema.py \
  tests/unit/test_rss_fetch.py \
  tests/unit/test_rss_classify.py \
  tests/unit/test_rss_ingest.py \
  tests/unit/test_run_enrich_for_id.py -v

# Dry-run smoke (no API call, no DB write)
venv/bin/python enrichment/rss_ingest.py --dry-run

# Real smoke on a single article
venv/bin/python enrichment/rss_ingest.py --article-id 1

sqlite3 data/kol_scan.db "SELECT id, enriched FROM rss_articles WHERE id=1"
# Expected: 1 | 2   (on success, verified by aget_docs_by_ids==PROCESSED)
# On failure:  1 | 0   (retry next batch)

ls ~/.hermes/omonigraph-vault/rss_content/*/final_content.md
# Expected: at least one Chinese final_content.md

# Confirm D-07 REVISED on the bridge too
venv/bin/python enrichment/run_enrich_for_id.py --source rss --article-id 1
# Expected stdout: "RSS excluded per D-07 REVISED 2026-05-02 + D-19 — ..."
# rc 0; no hermes skill run invoked
```

## 10. Commits (pending push)

1. `feat(05-03b): run_enrich_for_id.py KOL bridge + RSS guarded no-op`
2. `feat(05-03b): rss_ingest.py with DeepSeek translate + D-19 PROCESSED gate`
3. `docs(05-03b): SUMMARY + close Plan 05-03b`

## 11. Hand-off

Plan 05-03b complete. Wave 1 (plans 05-01/02/03/03b) **CLOSED** locally.
Remaining: update `.planning/STATE.md` Wave-1-closed entry + annotate
`.planning/ROADMAP.md` with `Wave 1 closed 2026-05-02 @ <hash>`.

Next waves are out of scope for this autonomous run:
- 05-04 orchestrate
- 05-05 daily digest
- 05-06 cron + observation

Await user review before proceeding.
