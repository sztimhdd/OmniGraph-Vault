---
phase: 05-pipeline-automation
plan: 05
subsystem: daily-digest
tags: [wave2, digest, telegram, asymmetric-union, d-07-revised, d-19]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 05-05 SUMMARY — daily_digest.py (TOP-N KOL + RSS Markdown digest)

**Status:** Complete (local; Telegram delivery smoke deferred to Hermes)
**Wave:** 2
**Depends on:** 05-04 (orchestrator provides step_8 call site)

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 5.1 | `enrichment/daily_digest.py` (251 lines) | — |
| 5.1 | `tests/unit/test_daily_digest.py` (9 tests) | 9/9 pass |

## 2. Asymmetric UNION ALL (D-07 REVISED + D-19)

```sql
-- KOL branch: REQUIRES enriched=2 (Phase 4 contract)
SELECT 'kol' AS src, a.id, a.title, a.url, acc.name AS source,
       COALESCE(a.digest, '') AS body, c.topic, c.depth_score, c.classified_at,
       a.scanned_at AS fetched_at,
       LENGTH(COALESCE(a.digest, '')) AS content_length
FROM articles a
JOIN classifications c ON c.article_id = a.id
JOIN accounts acc ON acc.id = a.account_id
WHERE date(a.scanned_at) = ? AND c.depth_score >= 2 AND a.enriched = 2
UNION ALL
-- RSS branch: NO enriched filter (RSS never enriched per D-07 REVISED)
SELECT 'rss' AS src, a.id, a.title, a.url, f.name AS source,
       COALESCE(a.summary, '') AS body, c.topic, c.depth_score, c.classified_at,
       a.fetched_at, a.content_length
FROM rss_articles a
JOIN rss_classifications c ON c.article_id = a.id
JOIN rss_feeds f ON f.id = a.feed_id
WHERE date(a.fetched_at) = ? AND c.depth_score >= 2
ORDER BY depth_score DESC, content_length DESC, classified_at DESC
LIMIT ?
```

Asymmetry verified by Test 7 (`test_asymmetric_enriched_filter`):
- KOL `enriched=0` + RSS `enriched=0` → ONLY RSS rows appear (KOL excluded).
- KOL `enriched=2` + RSS `enriched=0` → BOTH appear (Test 8).

## 3. Schema-reality adaptations (from plan sample SQL)

Plan's interfaces sample used columns that don't exist on the current
`articles` table. Corrected in the shipped SQL:

| Plan sample | Actual on `articles` | Adaptation |
|-------------|----------------------|------------|
| `a.fetched_at` | `a.scanned_at` | `a.scanned_at AS fetched_at` aliased for KOL branch |
| `a.content_length` | (not present) | `LENGTH(COALESCE(a.digest,'')) AS content_length` computed for KOL |
| `a.author` | (not present) | JOIN to `accounts.name AS source` for KOL |
| `a.content` | `a.digest` (short WeChat digest) | `COALESCE(a.digest,'') AS body` |

RSS branch uses native column names (`fetched_at`, `content_length`,
`summary`) — those are present from Plan 05-01's schema.

## 4. Markdown shape (PRD §3.3.2)

```markdown
# OmniGraph-Vault today's quality picks — 2026-05-03

**1. [Agent] KOL Title 0** [[KOL]]
- 来源: TestKOL · WeChat
- 摘要: KOL digest body 0 KOL digest body 0 KOL digest body 0 ...
- [阅读原文](https://mp.weixin.qq.com/s/kol0)

**2. [LLM] RSS Title 0** [[RSS]]
- 来源: Feed A · RSS
- 摘要: RSS summary body 0 RSS summary body 0 ...
- [阅读原文](https://a.example/p/rss0)

---
Scanned today: 4 KOL + 3 RSS | Deep: 7 | Ingested: 4
```

Source tag (`[KOL]` / `[RSS]`) + channel label (`WeChat` / `RSS`) makes
provenance immediately visible to the reader per 05-05 objective §3.

## 5. Empty-state policy

Per CONTEXT Claude's Discretion §4: zero candidates → log
"no candidates for <date>" + return rc=0 + **skip** Telegram delivery +
**skip** archive file write. Verified by Test 3.

## 6. Telegram delivery contract

- Endpoint: `https://api.telegram.org/bot{token}/sendMessage`
- Timeout: 15s
- `parse_mode=Markdown`, `disable_web_page_preview=True`
- Missing `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: log `delivery_error`,
  return False. run() still writes the archive (durable record), and
  returns `rc=1` so cron can alert.
- Non-2xx response: log `delivery_error: status=<N> body=<snippet>`,
  return False. Archive still written.

Verified by Test 9 (`test_missing_telegram_creds_returns_rc1`): missing
creds → `rc=1` but `{digest_dir}/{today}.md` exists.

## 7. Atomic archive write

`archive(date, markdown, digest_dir)`:
1. `target_dir.mkdir(parents=True, exist_ok=True)`
2. Write to `{date}.md.tmp`
3. `os.replace(tmp, target)` (atomic on POSIX + NTFS)

Path: `BASE_DIR / "digests" / {YYYY-MM-DD}.md` — typo'd `omonigraph-vault`
preserved via `config.BASE_DIR` (Test 6 asserts `omonigraph-vault` in the
resolved path).

## 8. Unit test summary (9 tests)

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_top_n_sorting` | 7 inserted → top 5 returned, depth DESC sort holds |
| 2 | `test_render_markdown_shape` | Markdown contains `[topic]`, `· WeChat/RSS`, `阅读原文`, http URL, `[KOL]`/`[RSS]` tag |
| 3 | `test_empty_state_skips_telegram_and_archive` | 0 rows → no Telegram call, no archive file |
| 4 | `test_dry_run_no_network_no_write` | `--dry-run` prints Markdown, no Telegram, no archive |
| 5 | `test_archive_uses_os_replace` | archive path uses `.tmp` source + `os.replace` |
| 6 | `test_archive_path_preserves_typo` | resolved archive path contains `omonigraph-vault` |
| 7 | `test_asymmetric_enriched_filter` | KOL(enriched=0) excluded; RSS(enriched=0) included |
| 8 | `test_mixed_enriched_both_appear` | KOL(enriched=2) + RSS(enriched=0) both appear |
| 9 | `test_missing_telegram_creds_returns_rc1` | No creds → `rc=1` but archive still written |

## 9. No LLM synthesis pass — intentional

Per 05-05 plan §50 + user's Wave 2 prompt item #1: daily_digest.py is
**SQL + Markdown templating only**. No DeepSeek, no Gemini, no LightRAG
aquery, no synthesis. Prompt-dependent image rendering caveat (Wave 0
Addendum §C) doesn't apply — digest doesn't go through a prompt.

If future work adds an LLM summarization layer (e.g., per-cluster theme
sentence), route via DeepSeek per CLAUDE.md rule; that's a new plan, not
an edit to this module.

## 10. Hermes-side verification (operator to run)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/python -m pytest tests/unit/test_daily_digest.py -v   # expect 9/9

# Dry-run smoke — prints Markdown for today (might be empty)
venv/bin/python enrichment/daily_digest.py --dry-run

# Date-specific dry-run (feed a date with KOL+RSS content from Wave 1 smoke)
venv/bin/python enrichment/daily_digest.py --date 2026-05-03 --dry-run

# Real delivery (requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in ~/.hermes/.env)
venv/bin/python enrichment/daily_digest.py
ls -la ~/.hermes/omonigraph-vault/digests/
```

## 11. Commits

1. (pending) — `feat(05-05): daily_digest.py asymmetric UNION + Telegram + atomic archive`

## 12. Hand-off

Plan 05-05 complete. Plan 05-06 Task 6.1 (cron registration) is the next
autonomous step. Task 6.2 (3-day observation) is a user checkpoint —
the autonomous run stops there.
