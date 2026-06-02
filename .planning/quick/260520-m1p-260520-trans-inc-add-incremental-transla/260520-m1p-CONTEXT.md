# Quick Task 260520-m1p (trans-inc): Incremental translation in ingest pipeline — Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Task Boundary

Add incremental translation to the OmniGraph-Vault ingest pipeline so daily ingest cron auto-fills `title_translated` (inline, in-pipeline) and a separate nightly cron auto-fills `body_translated` (~10 articles/day). Translations target the 4 schema columns shipped by migrations 006 (articles) + 007 (rss_articles): `title_translated`, `body_translated`, `translated_lang`, `translated_at`.

Use DeepSeek (existing infra; LF-2.3 Layer-2 client) for the LLM, Tavily for terminology context lookup. Hermes-only — Aliyun / Databricks pull translated DB via existing SCP / Databricks-deploy mechanisms.

Scope is INCREMENTAL only — backfill of existing untranslated articles is out-of-scope (handled by `databricks-deploy/translate_kb.py` per kb-v2.2-7 Wave 2 A2).
</domain>

<decisions>
## Implementation Decisions (locked)

### Inline title translation — single insertion point in `batch_ingest_from_spider.py` only

User spec said "modify `batch_ingest_from_spider.py` 和 `rss_ingest.py`" but **`rss_ingest.py` was retired in v3.5 ir-4** (CLAUDE.md "Local E2E testing" section: "post-ir-4, RSS will route through `batch_ingest_from_spider.py` + `lib/article_filter.py`"). The file no longer exists at the project root — only in a worktree archive.

**Decision:** modify only `batch_ingest_from_spider.py` at the unified post-Layer-2 drain loop (lines 1810-1920). Both KOL articles (`source_d == 'wechat'`) and RSS articles (`source_d == 'rss'`) flow through this loop, discriminated by `source_d` from the 8-tuple `candidate_rows`. The right insertion point is **after line 1913** (the `if wall >= effective_timeout` block, end of status-determination) **before line 1915** (the `INSERT OR REPLACE INTO ingestions` call that marks the article complete).

Variables in scope at the insertion point: `art_id_d` (row[0]), `source_d` (row[1]), `url_d` (row[3]), `body`, `status`. We need to add `title_d = row[2]` near line 1836 alongside the existing `art_id_d`/`source_d`/`url_d` extraction.

### Why NOT modify the line 938 path (older per-account `'wechat'`-hardcoded fetch path)

That path doesn't write `status='ok'` to the `ingestions` table at the same point — it appends to an in-memory `summary` list (line 947). It also predates the Layer 2 verdict gate that the user's spec requires (`layer1_verdict='candidate' AND layer2_verdict='ok'`). Touching it adds risk without spec benefit.

### Tavily integration — required dep, fail-soft behavior

Tavily is not currently in `requirements.txt`. Add it as a required pip dep (`tavily-python`).

Behavior: if `TAVILY_API_KEY` is missing OR the Tavily API call fails / times out, log a warning and proceed without web context. The DeepSeek translation continues with empty `context_snippets`. The user's "翻译失败 → NULL,不'best-effort 写半句中文'" rule applies to LLM failure (which makes the entire translation NULL), NOT to Tavily augmentation failure (which only degrades terminology quality).

Domain restriction (per user spec "*.org / *.gov / 维基 / 大厂官网"): pass `include_domains=["wikipedia.org", "*.gov", "*.org", "github.com", "openai.com", "anthropic.com", "google.com", "microsoft.com", "huggingface.co"]` to Tavily client.

### DeepSeek model ID — TODO placeholder, default to env-var-controlled model

User spec says "DeepSeek V4 Pro" but the exact model ID is not yet known. The existing `lib/llm_deepseek.py` reads `DEEPSEEK_MODEL` env var (default `deepseek-v4-flash`). The translate helper will:

- Use the existing `deepseek_model_complete` wrapper (no new wrapper needed — it already has 300s timeout, lazy client, error handling).
- Add a code comment: `# TODO(user): DeepSeek V4 Pro model ID confirmed by user — currently uses DEEPSEEK_MODEL env var (default deepseek-v4-flash). Override via env: DEEPSEEK_MODEL=<v4-pro-id>`

Per-call timeout is enforced via `asyncio.wait_for`: 15s for title (cheap), 60s for body (longer text). These wrap `deepseek_model_complete` which has its own 300s ceiling.

### Schema state — migrations 006 + 007 exist; test fixtures need 4 new columns

`kb/data/migrations/006_add_translation_columns.sql` exists (kb-v2.2-2 ship); columns added to `articles`.
`kb/data/migrations/007_add_translation_columns_rss.sql` exists (kb-v2.2-7 Wave 1 ship); columns added to `rss_articles`.

**Test fixture `tests/unit/_ingest_fixtures.py` does NOT have those 4 columns** in the `articles` and `rss_articles` CREATE TABLE clauses. Per `feedback_contract_shape_change_full_audit.md` and 2026-05-15 lesson #2, fixture drift silently masks downstream bugs. **Mandatory:** extend `articles` and `rss_articles` CREATE TABLE in `_ingest_fixtures.py` with `body_translated TEXT, title_translated TEXT, translated_lang VARCHAR(5), translated_at DATETIME`.

### Body cron — overwrite `translated_at` on body update, but NOT `title_translated`

When the nightly body cron runs, an article may already have `title_translated` set by the inline path. The body cron must:

- UPDATE `body_translated`, `translated_lang`, `translated_at` (most-recent translation timestamp wins)
- Do NOT touch `title_translated` (preserve the inline-translated title)

SQL: `UPDATE {table} SET body_translated = ?, translated_lang = ?, translated_at = ? WHERE id = ?` — explicitly exclude `title_translated`.

### Cron registration — to `~/.hermes/cron/jobs.json`, NOT in this commit

Spec requires registering the body cron at 03:30 ADT in Hermes's `~/.hermes/cron/jobs.json`. **This is a Hermes-side ops change, not in repo scope.** The PLAN/SUMMARY documents the registration command for the user to run on Hermes; we do NOT modify any file under `~/.hermes/` from local Claude Code.

The repo deliverable is the script `scripts/translate_body_cron.py` and a runbook line in SUMMARY.md telling the user how to register the cron.

### kb-v2.2-7 PLAN A2 architectural relationship — complement, not pivot

kb-v2.2-7 Wave 2 (locked decision A2) ships translation production via `databricks-deploy/translate_kb.py` (manual Databricks notebook, paid budget, "Run all" trigger). The PLAN's "Hard don'ts" forbid scheduled translation jobs and bundle yaml.

This trans-inc quick adds **incremental** translation on Hermes for new articles (~10/day cron + inline). It does NOT remove or replace the Databricks notebook. Functions:

- **Databricks notebook (kb-v2.2-7 A2):** one-shot backfill of historical untranslated rows, paid LLM
- **Hermes inline + cron (this quick):** ongoing daily translation of newly-ingested articles, DeepSeek

The user described this as "kb-v2.2-7 计划里说好的但漏了" but technically it's a deliberate complement to A2 — A2 was scoped to backfill-only, with no incremental story documented. This quick fills that gap.

The kb-v2.2-7 PLAN's "Hard don'ts" anti-pattern of "scheduled translation job" was scoped to **backfill scheduling** (i.e., running the Databricks notebook on a schedule) — adding a small DeepSeek-based incremental cron is not the same risk because Hermes can run it cheaply within the existing daily ingest infrastructure.

### Claude's Discretion

Areas not explicitly directed by user spec that I'll decide during execution:

- Exact DeepSeek prompt wording for title vs body (mirror kb-v2.2-7 Wave 2's image-position-preserving discipline for body; minimal terminology-focused for title)
- Logging structure: per-row log line in `.scratch/translate-body-cron-<YYYYMMDD>.log` for body cron; reuse standard `logger` for inline path
- Test mock structure: use `unittest.mock.AsyncMock` for `deepseek_model_complete` and `_tavily_search`; pinned-DB-row tests use a tmp_path SQLite + the existing `_ingest_fixtures` schema (extended)
- `--dry-run` semantics: log SELECT row IDs + LLM call shape (prompt length + model name), do not invoke LLM, do not UPDATE
</decisions>

<specifics>
## Specific Files + Line Anchors

| File | Action | Anchor |
|---|---|---|
| `lib/translate.py` | NEW | — |
| `scripts/translate_body_cron.py` | NEW | — |
| `tests/unit/test_translate.py` | NEW | — |
| `batch_ingest_from_spider.py` | UPDATE | line 1836 add `title_d = row[2]`; lines 1913→1915 insert title-translation block |
| `tests/unit/_ingest_fixtures.py` | UPDATE | lines 83-101 (articles CREATE TABLE) + 106-122 (rss_articles CREATE TABLE) — add 4 translation columns each |
| `requirements.txt` | UPDATE | append `tavily-python>=0.3` |
| `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md` | UPDATE | append `## trans-inc Local UAT` section |
| `.planning/STATE.md` (NOT STATE-KB-v2.md — quick task table lives in main STATE) | UPDATE | append "Quick Tasks Completed" row |

**Translation columns to add (already in migrations 006 + 007 — fixture parity needed):**

```sql
body_translated TEXT,
title_translated TEXT,
translated_lang VARCHAR(5),
translated_at DATETIME
```

</specifics>

<canonical_refs>

## Canonical References

- `kb/data/migrations/006_add_translation_columns.sql` — schema for `articles` translation columns (already shipped kb-v2.2-2)
- `kb/data/migrations/007_add_translation_columns_rss.sql` — schema for `rss_articles` translation columns (already shipped kb-v2.2-7 Wave 1)
- `lib/llm_deepseek.py` — existing DeepSeek async client (`deepseek_model_complete(prompt, system_prompt, history_messages, **kwargs) -> str`, default model `deepseek-v4-flash`, env-overridable via `DEEPSEEK_MODEL`)
- `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-PLAN.md` Wave 2 — image-position-preserving prompt discipline (bullet-list of explicit clauses to mirror in the body cron prompt)
- `.scratch/B-followup-kb-default-lang-260520.md` — KB bilingual fallback chain context
- `tests/unit/_ingest_fixtures.py` — production-shape behavior-anchor harness fixtures
- CLAUDE.md PRINCIPLE #7 (behavior-anchor harness) — applies to fixture drift
- Memory `feedback_contract_shape_change_full_audit.md` — fixture-drift discipline
- Memory `feedback_no_amend_in_concurrent_quicks.md` — forward-only commits
- Memory `feedback_git_add_explicit_in_parallel_quicks.md` — explicit `git add <files>`
- Memory `feedback_kb_local_uat_mandatory.md` — Local UAT discipline (PRINCIPLE #6)
</canonical_refs>
</content>

</invoke>