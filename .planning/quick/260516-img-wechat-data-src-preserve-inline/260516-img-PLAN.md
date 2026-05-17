# 260516-img — kb-v2.1-8-quick PLAN

**Author:** orchestrator (forwarded by user)
**Date:** 2026-05-16
**Branch:** main
**Mission:** Fix `ingest_wechat.py:process_content()` so WeChat lazy-load images
(`<img data-src="https://mmbiz.qpic.cn/..." src="data:image/svg+xml,...placeholder">`)
produce inline `![](real-url)` markdown — preserving inline image position in
the article body for new ingests.

## Root cause

Pre-fix `process_content(html)` collected image URLs via BeautifulSoup
(`img.get('data-src') or img.get('src')`) but then passed the **original raw
html string** to `html2text.handle()`. WeChat lazy-load pattern means the
original `src` is a `data:image/svg+xml,...placeholder`, so html2text emitted
unusable `![](data:...)` markdown — losing the real URL **and** its inline
position. Subsequent `image_pipeline.localize_markdown(remote→local)` was a
no-op because `remote_url` never appeared in the markdown.

Result on prod: only the Phase 5-00 retrieval-binding end-of-doc text refs
(`Image N from article 'X': URL`, line 1303) survived — which kb-v2.1-6 then
correctly rendered as `<img>` tags clustered at end-of-article.

## Fix (single function, surgical)

In `process_content()` (now `process_content(html: str) -> tuple[str, list[str]]`):

1. In the BeautifulSoup loop over `img` tags, **mutate** `img['src'] = data_src`
   when (a) `data-src` exists, AND (b) current `src` is missing OR starts with
   `'data:'` (data-URI placeholder). Do NOT overwrite a valid `http(s)` src.
2. Pass `str(soup)` (the mutated soup) to `html2text.handle()` — NOT the original
   `html` string.
3. Idempotent: running on already-fixed HTML produces identical output (valid
   `http(s)` src preserved unchanged).

Phase 5-00 retrieval-binding line 1303 (`Image N from article 'X': URL`) and
`image_pipeline.localize_markdown` are **untouched** — they serve different
concerns (LightRAG aquery binding, URL→local-path rewrite) and stay correct.

## Skills invoked

- `Skill(skill="python-patterns", args="...")` — BeautifulSoup mutation pattern,
  idiomatic helper, type hints, docstring with WeChat lazy-load + Phase 5-00
  context.
- `Skill(skill="writing-tests", args="...")` — Testing Trophy: unit > integration
  here (pure function, synthetic HTML fixtures, no network).

## Tests (NEW: `tests/unit/test_process_content_wechat_data_src.py`, 7 cases)

1. `test_data_src_promoted_when_src_is_data_uri_placeholder` — happy path
2. `test_data_src_used_when_src_missing` — no-src case
3. `test_valid_src_preserved_unchanged_no_data_src` — regression guard
4. `test_valid_src_not_overwritten_by_data_src` — regression guard
5. `test_multi_image_article_inline_positions_preserved` — 3 imgs, position +
   ordered output
6. `test_idempotent_on_already_fixed_html` — re-run identical
7. `test_relative_src_not_collected_in_images_list` — http*-only collection

## Hard gate (per user instruction)

Full pytest suite MUST PASS locally before push to origin/main.

If any test fails → STOP, do NOT push, escalate.

## Anti-patterns

- ❌ Don't modify `ingest_wechat.py:1303` Phase 5-00 retrieval-binding line.
- ❌ Don't modify `image_pipeline.localize_markdown` (already correct).
- ❌ Don't regenerate historical `final_content.md` files.
- ❌ Don't touch Aliyun production (Hermes is deploy target).
- ❌ Don't touch `kb/` (this is ingest-side fix, not export-side).
- ❌ Don't touch `databricks-deploy/` (kdb-1.5 / kdb-2 territory).
- ❌ Don't `git add -A` / `--amend` / `git reset --hard` / `git rebase -i` /
  `git push --force` (concurrent-quick safety).
