# Quick 260529-hlu — Summary

**Status:** Complete (commit pending push, held by orchestrator)
**Date:** 2026-05-29
**Description:** wiki SSG bake parity for SCHEMA-2026-05-20 multi-type sources + GFM `[^N]` footnote

## Outcome

`kb/export_knowledge_base.py:_convert_wiki_citations` now supports both
citation forms (legacy `^[article:<hash>]` AND new GFM `[^N]`) and multi-type
frontmatter sources (article / web / builtin). `wiki_entity.html` sources
section conditionally renders by source type. 11 new unit tests pin both
formats.

## Files changed

| File | Change |
|---|---|
| `kb/export_knowledge_base.py` | +110 / -22 — added `FOOTNOTE_CITATION_RE`, `_normalize_frontmatter_sources`, `_build_source_url`; refactored `_convert_wiki_citations` to dual-format; updated `_render_wiki_pages` call site to pass `frontmatter_sources` + `page_slug` |
| `kb/templates/wiki_entity.html` | line 65 hard-coded article markup -> if/elif by `src.type` (article / web / builtin / fallback) |
| `tests/unit/kb/test_export_wiki_citations.py` | new file, 11 tests |

## Verification

```text
pytest tests/unit/kb/test_export_wiki_citations.py -v        -> 11/11 PASS
pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py     -> 5/5 PASS  (regression)

Dry-run bake (.scratch/bake_wiki_only.py):
  19 wiki pages rendered to .scratch/wiki-test-output/wiki/
  copilot-studio.html  : 21 sources (web + builtin types render correctly,
                                       42 <sup class="wiki-cite">, 0 literal [^N])
  claude-code.html     : 20 sources (legacy article rendering byte-identical,
                                       32 <sup class="wiki-cite">, 0 literal ^[article:)
```

## Risk / next steps

- This commit fixes the bake, but the 5 Copilot Studio wiki pages on local
  main still need a full Makefile bake + browser UAT on Databricks before
  push. Push held by orchestrator (target = 9 commits batched: 5 wiki entity
  pages + 1 cross-link + SCHEMA-EXTENSION-PROPOSAL + DEPLOY-PLAN + this fix).
- No `_ssg/` changes were made (Principle #9): full Makefile pipeline
  (Pass 0 SSG bake) is required when this commit + the 5 wiki pages get
  deployed to Databricks.

## Constraints honored

- A. No push origin main
- B. No SCHEMA.md changes
- C. No kb/wiki_lint.py changes
- D. No kb/wiki_update.py / kb/services/wiki_inject.py changes
- E. Legacy `^[article:hash]` continues to render byte-identical (verified in
  `.scratch/wiki-test-output/wiki/claude-code.html` etc, all 12 legacy pages)
- F. No other wiki file changes
- G. No `_ssg/` changes
- H. Atomic commit, not pushed
