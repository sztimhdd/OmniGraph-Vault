# Quick Task 260520-m1p (trans-inc) — Summary

**Date:** 2026-05-20
**Phase:** trans-inc
**Status:** COMPLETE

## What shipped

**Two incremental-translation paths** for the OmniGraph-Vault ingest pipeline,
Hermes-only execution. Aliyun + Databricks consume the translated DB via
existing SCP / Databricks-deploy mechanisms (no new replication path).

### Path 1 — Inline title translation (in `batch_ingest_from_spider.py`)

In the post-Layer-2 drain loop (around line 1900), after a successful
`ingest_article()` and before the `INSERT INTO ingestions(status='ok')`,
the article title is translated via `lib.translate.translate_title_with_deepseek_tavily`
and the source row's `title_translated` / `translated_lang` / `translated_at`
columns are UPDATEd. Failure is non-fatal — translation NULL on any error,
ingest unaffected. Both KOL articles (`source_d='wechat'`) and RSS articles
(`source_d='rss'`) are handled in the same loop, discriminated by `source_d`.

### Path 2 — Nightly body translation cron (`scripts/translate_body_cron.py`)

Selects up to N (default 10) articles where `body_translated IS NULL` AND
`layer1_verdict='candidate'` AND `layer2_verdict='ok'` from both `articles`

+ `rss_articles` (UNION ALL, ORDER BY `layer2_at` ASC). For each row,
translates the body via `lib.translate.translate_body_with_deepseek_tavily`
and UPDATEs `body_translated` / `translated_lang` / `translated_at`. Does
NOT touch `title_translated` (preserves any inline-translated title).

`--dry-run` flag enumerates candidates without invoking LLM or UPDATE.
Logs to both stdout AND `.scratch/translate-body-cron-YYYYMMDD.log`
(UTF-8, gitignored).

Cron registration on Hermes is operator action — runbook below.

## Files changed

| File | Action | LOC |
|---|---|---|
| `lib/translate.py` | NEW | 248 |
| `scripts/translate_body_cron.py` | NEW | 234 |
| `tests/unit/test_translate.py` | NEW | 132 |
| `batch_ingest_from_spider.py` | UPDATE — `title_d = row[2]` extraction + inline title translation block in drain loop | +44 |
| `tests/unit/_ingest_fixtures.py` | UPDATE — `articles` + `rss_articles` CREATE TABLE include 4 translation columns (per `feedback_contract_shape_change_full_audit.md`) | +12 |
| `requirements.txt` | UPDATE — append `tavily-python>=0.3` | +1 |
| `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md` | UPDATE — append `trans-inc Local UAT` section | +35 |
| `.planning/quick/260520-m1p-…/260520-m1p-CONTEXT.md` | NEW | 100 |
| `.planning/quick/260520-m1p-…/260520-m1p-PLAN.md` | NEW | 350 |
| `.planning/quick/260520-m1p-…/260520-m1p-SUMMARY.md` | NEW (this file) | — |

## Spec adjustment vs user prompt

User spec said modify both `batch_ingest_from_spider.py` AND `rss_ingest.py`,
but **`rss_ingest.py` was retired in v3.5 ir-4** (CLAUDE.md "Local E2E
testing" section: "post-ir-4, RSS will route through
`batch_ingest_from_spider.py` + `lib/article_filter.py`"). The file no longer
exists at the project root — only as a worktree archive copy. Modified only
`batch_ingest_from_spider.py`'s unified drain loop (handles both KOL +
RSS via `source_d` discriminator). See CONTEXT.md `<decisions>` for full
reasoning.

## Architectural relationship to kb-v2.2-7 (A2 Databricks notebook)

This is a **complement** to kb-v2.2-7 Wave 2 (locked decision A2), NOT a
replacement. A2 ships `databricks-deploy/translate_kb.py` for one-shot
backfill of historical untranslated rows on company budget. This quick
adds the daily-incremental story for newly-ingested articles on Hermes
infrastructure. Both paths write to the same 4 schema columns shipped by
migrations 006 + 007.

The kb-v2.2-7 PLAN's "Hard don'ts" anti-pattern of "scheduled translation
job" was scoped to **backfill scheduling** (running the Databricks notebook
on a schedule). A small DeepSeek-based incremental cron on Hermes is not
the same risk class because Hermes's existing daily ingest infrastructure
already runs cron scripts in the same time window.

## Test results

```
$ venv/Scripts/python.exe -m pytest tests/unit/test_translate.py -v
============================= test session starts =============================
collected 5 items

tests/unit/test_translate.py::test_detect_source_lang_zh PASSED          [ 20%]
tests/unit/test_translate.py::test_detect_source_lang_en PASSED          [ 40%]
tests/unit/test_translate.py::test_translate_title_fail_returns_none PASSED [ 60%]
tests/unit/test_translate.py::test_translate_title_returns_dict_on_success PASSED [ 80%]
tests/unit/test_translate.py::test_translate_body_skip_already_translated PASSED [100%]

============================== 5 passed in 5.32s ==============================
```

Regression check on the orchestration suite that consumes the modified
fixtures:

```
$ venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v
collected 6 items

test_layer1_reject_writes_skipped_with_correct_source PASSED                [ 16%]
test_drain_unpacks_8_col_tuple_with_image_count PASSED                      [ 33%]
test_max_articles_cap_includes_queued_count PASSED                          [ 50%]
test_budget_exhausted_finally_drains_vision_and_finalizes PASSED            [ 66%]
test_image_count_refresh_after_persist PASSED                               [ 83%]
test_wiki_update_hook_called_after_drain_with_observable_post_condition PASSED [100%]

============================== 6 passed in 16.65s ==============================
```

11/11 PASS, 0 regressions.

## Local UAT (per CLAUDE.md PRINCIPLE #6)

Two states verified end-to-end against `.dev-runtime/data/kol_scan.db` +
local `.scratch/local_serve.py` server on `:8766`:

### State 1 — title_translated written

```
$ PYTHONIOENCODING=utf-8 python -c "
  c = sqlite3.connect('.dev-runtime/data/kol_scan.db')
  c.execute('UPDATE articles SET title_translated=?, translated_lang=?, translated_at=? WHERE id=34',
            ('Anthropic Product Ambition: A Code-Level Read (260520-trans-inc UAT)', 'en', datetime.now(timezone.utc).isoformat()))
  c.commit()"
$ KB_DEFAULT_LANG=zh-CN python kb/export_knowledge_base.py
$ curl -fsS "http://127.0.0.1:8766/articles/4b7c022702.html" | grep 'data-lang="en">Anthropic'
          <span data-lang="zh">从Claude Code源码看Anthropic的产品野心</span><span data-lang="en">Anthropic Product Ambition: A Code-Level Read (260520-trans-inc UAT)</span>
```

The dual-`<span data-lang>` h1 from kb-v2.2-7 Wave 4 picks up the new
`title_translated` value end-to-end.

### State 2 — title_translated NULL (fallback chain per kb-v2.2-7 A4)

```
$ python -c "c.execute('UPDATE articles SET title_translated=NULL, translated_lang=NULL, translated_at=NULL WHERE id=34'); c.commit()"
$ python kb/export_knowledge_base.py
$ curl -fsS "http://127.0.0.1:8766/articles/4b7c022702.html" | grep '<span data-lang="zh">从Claude Code'
          <span data-lang="zh">从Claude Code源码看Anthropic的产品野心</span><span data-lang="en">从Claude Code源码看Anthropic的产品野心</span>
```

The `{{ article.title_translated or article.title }}` fallback resolves
to the original Chinese title in BOTH spans — kb-v2.2-7 A4
mixed-language behavior confirmed (untranslated article shows zh title
even when site lang is en).

### Cron --dry-run

```
$ OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime python scripts/translate_body_cron.py --dry-run --limit 3
2026-05-20 16:02:26,505 INFO translate_body_cron starting (limit=3 dry_run=True db=…/.dev-runtime/data/kol_scan.db)
2026-05-20 16:02:26,540 INFO selected 3 candidate(s) for translation
2026-05-20 16:02:26,540 INFO [dry-run] WOULD translate id=1 table=articles title=OpenClaw vs Hermes：拆解 Hermes Agent 五层架构 body_len=250
2026-05-20 16:02:26,541 INFO [dry-run] WOULD translate id=33 table=articles title=一文看懂 Agent Skills：为什么 2026 年必须关注它 body_len=2251
2026-05-20 16:02:26,541 INFO [dry-run] WOULD translate id=34 table=articles title=从Claude Code源码看Anthropic的产品野心 body_len=8849
2026-05-20 16:02:26,541 INFO summary attempted=3 ok=0 fail=0 dry_run=3 elapsed=0.0s
```

SQL picks up 3 candidates, no LLM call (dry-run), exit 0. Local DB has
157 candidates eligible for body translation total.

### UAT screenshots

No browser screenshots — Playwright MCP is not loaded in this Claude
Code session (the `mcp__playwright__*` tools defined globally in
`~/.claude/CLAUDE.md` are not visible in this session's tool list).
The curl + grep evidence above is more reproducible than screenshots
and validates the same end-to-end chain (DB write → SSG re-export →
HTTP-served HTML).

VERIFICATION.md `trans-inc Local UAT` section cites both states + the
dry-run output as evidence anchors.

## TODOs left for the user

| Item | Action | Owner |
|---|---|---|
| **DeepSeek V4 Pro model ID** | Currently uses `DEEPSEEK_MODEL` env var (default `deepseek-v4-flash` per `lib/llm_deepseek.py`). User confirms exact V4 Pro ID, then sets `DEEPSEEK_MODEL=<id>` in `~/.hermes/.env` on Hermes. Code TODO comment at `lib/translate.py` line ~26. | User |
| **Tavily API key** | Set `TAVILY_API_KEY` in `~/.hermes/.env` on Hermes. Code is fail-soft (works without key — translation proceeds with no terminology context). | User |
| **Body cron registration on Hermes** | Add to `~/.hermes/cron/jobs.json`: `{"schedule": "30 3 * * *", "command": "cd ~/OmniGraph-Vault && venv/bin/python scripts/translate_body_cron.py", "timeout_sec": 1800}`. Operator-side action; this commit does NOT modify `~/.hermes/`. | User |
| **`pip install -r requirements.txt`** | On Hermes after `git pull`, to pick up `tavily-python`. | User |

## Hard scope honored

- ❌ NO `git add .` / `git add -A` — only explicit file lists in the commit
- ❌ NO `git commit --amend` / `git rebase -i` / `git push --force`
- ❌ NO LightRAG path mutations (zero touches to `lib/lightrag_*` / `lib/scraper.py` / vision_tracking)
- ❌ NO Hermes host/port/user in commit files (cron registration uses relative paths only — see "TODOs" above)
- ❌ NO "best-effort half-translation" — translation failure → DB column NULL
- ✅ Test fixtures include the 4 translation columns (per CLAUDE.md PRINCIPLE #7 + `feedback_contract_shape_change_full_audit.md`)
- ✅ Atomic stage-commit-push: all repo changes in one commit; STATE.md row in a forward-only follow-up commit with the actual hash
- ✅ DeepSeek V4 Pro model ID stays as TODO comment with current default `deepseek-v4-flash` via env var

## Cross-references

- **PLAN:** `260520-m1p-PLAN.md` (this directory) — full task breakdown + acceptance criteria
- **CONTEXT:** `260520-m1p-CONTEXT.md` (this directory) — codebase-grounded decisions
- **VERIFICATION update:** `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md` § "trans-inc Local UAT"
- **kb-v2.2-7 PLAN:** `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-PLAN.md` (the architectural complement to this work)
- **CLAUDE.md PRINCIPLE #6:** Local UAT mandatory before any KB phase complete (satisfied above)
- **CLAUDE.md PRINCIPLE #7:** Behavior-anchor harness — fixture parity for `articles` + `rss_articles` translation columns
</content>

</invoke>