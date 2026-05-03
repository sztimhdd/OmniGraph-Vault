---
phase: 05-pipeline-automation
plan: 03
subsystem: rss-classify
tags: [wave1, rss, classify, deepseek, d-08, d-09-supersession]
status: complete
created: 2026-05-02
completed: 2026-05-02
---

# Plan 05-03 SUMMARY — RSS classifier (DeepSeek, bilingual prompt)

**Status:** Complete (local; live classify smoke deferred to Hermes)
**Wave:** 1
**Depends on:** 05-01, 05-02

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 3.1  | `enrichment/rss_classify.py` (228 lines) | — |
| 3.1  | `tests/unit/test_rss_classify.py` (6 tests) | 6/6 pass |
| 3.1  | `tests/conftest.py` — inject `DEEPSEEK_API_KEY=dummy-for-tests` via `os.environ.setdefault` at module top | unblocks any test that imports `lib` transitively |

## 2. Behaviors verified

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_writes_classification_row_with_chinese_reason` | happy path: one row per (article, topic), Chinese `reason`, depth ∈ {1,2,3} |
| 2 | `test_reclassify_is_noop_via_unique_constraint` | UNIQUE(article_id, topic) + silent `IntegrityError` handling = 1 row after 2 runs |
| 3 | `test_malformed_llm_response_is_skipped` | exception from `_call_deepseek` → `stats["failed"]` increments, no partial row |
| 4 | `test_dry_run_does_not_write` | `--dry-run` skips LLM call, skips DB write, never resolves API key |
| 5 | `test_max_articles_limits_batch` | `--max-articles 2` classifies exactly 2 articles even with 3 eligible |
| 6 | `test_uses_deepseek_endpoint_not_gemini` | static audit: `api.deepseek.com` present, `google.genai`/`GEMINI_API_KEY` absent, `get_deepseek_api_key` imported |

## 3. LLM routing — Phase 7 D-09 supersession compliance

- **Endpoint:** `https://api.deepseek.com/v1/chat/completions` (raw HTTP `requests.post`).
- **Model:** `deepseek-chat` (env-overridable via `CLASSIFIER_MODEL`).
- **Key resolver:** `from batch_classify_kol import get_deepseek_api_key`
  (production pattern: env var → `~/.hermes/.env` → `~/.hermes/config.yaml`).
- **Gemini absent:** `google.genai`, `from google import genai`, and
  `GEMINI_API_KEY` are all confirmed absent from `enrichment/rss_classify.py`
  by the static test (gate per 05-00-SUMMARY §D).

## 4. D-08 EN→CN — prompt encodes the rule

```
**规则**:
- 必须用中文回答 reason(无论原文语言)。
- depth_score: 1=资讯/快讯, 2=技术教程/分析, 3=深度研究/架构拆解。
- relevant: 0 或 1(是否与主题相关)。
- excluded: 0 或 1(是否应被剔除,例如广告/招聘/纯转载)。
- 只输出 JSON,不要任何其他文字。不要代码块围栏,不要解释。
```

The classifier does not run a separate EN→CN translate step. The LLM
receives (possibly-English) title + content, and the prompt constrains
`reason` to Chinese output. Happy-path test 1 asserts the returned
`reason` contains at least one CJK character.

## 5. Topic taxonomy

Shared with KOL per PRD §3.1.5 "分类 topic 与 KOL 共用同一套标签体系":

```python
DEFAULT_TOPICS: tuple[str, ...] = ("Agent", "LLM", "RAG", "NLP", "CV")
```

CLI: `--topic Agent --topic LLM` overrides for a narrower sweep.

## 6. Eligible-article SQL (anti-reclassification)

```sql
SELECT a.id, a.title, COALESCE(a.summary, '')
FROM rss_articles a
WHERE (SELECT COUNT(*) FROM rss_classifications c
       WHERE c.article_id = a.id AND c.topic IN (?, ?, ?, ?, ?)) < ?
ORDER BY a.fetched_at DESC
LIMIT ?
```

Returns articles that have fewer than `len(topics)` classifications
across the requested topic set. So an article already classified for
{Agent, LLM} but not for {RAG, NLP, CV} is still picked up.

## 7. Known caveats

- **Fence-stripping** only triggers when response content starts with
  ```` ``` ```` . If DeepSeek occasionally emits a single-line response
  with a trailing fence and nothing else, `json.loads` will raise and the
  pair is counted as failed — matches intended behaviour (no partial
  writes).
- **`depth_score` bounds check** is explicit (`if not 1 <= depth <= 3`).
  LLM outputs outside range are treated as failures.
- **Throttle** is 0.3s between LLM calls. For ~300 articles × 5 topics =
  1500 calls this is ~7.5 min of sleep overhead — acceptable for daily
  batch, consistent with `batch_classify_kol.py` cadence.

## 8. Hermes-side verification (operator to run)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/python -m pytest tests/unit/test_rss_classify.py -v

# Dry-run smoke — no API calls, no DB writes
venv/bin/python enrichment/rss_classify.py --max-articles 2 --dry-run

# Real run against today's fetched rss_articles
venv/bin/python enrichment/rss_classify.py --max-articles 5

sqlite3 data/kol_scan.db "SELECT topic, depth_score, COUNT(*) FROM rss_classifications GROUP BY topic, depth_score ORDER BY 1, 2;"
```

## 9. Commits

1. (pending) — `feat(05-03): rss_classify.py + conftest DEEPSEEK_API_KEY guard`

## 10. Hand-off

Plan 05-03 complete. Plan 05-03b (`enrichment/rss_ingest.py` + the
`run_enrich_for_id.py` guard) unblocked — articles now have a
`depth_score` column to filter on (`>=2`) for the translate-and-ainsert
path.
