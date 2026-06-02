# Quick 260529-hlu — wiki SSG bake parity for SCHEMA-2026-05-20

**Mode:** quick
**Created:** 2026-05-29

## Goal

SSG bake path (`kb/export_knowledge_base.py`) only supports the legacy
`^[article:<hash>]` citation form. SCHEMA-2026-05-20 added GFM `[^N]`
footnote citations + multi-type frontmatter `sources` (article / web / builtin),
already implemented by `kb/wiki_lint.py` (W3) but not by the bake. The 5 new
Copilot Studio entity pages render with `· 0` pill, literal `[^N]` in body,
and missing sources section.

Add bake parity with the W3 contract. Legacy entity pages must continue to
render byte-identical (12 existing pages).

## Decisions (all recommended A/A/A)

1. **Sources data structure:** flat list of dicts, each with `type` field —
   template renders by type via if/elif (article = internal link, web =
   external link with target=_blank, builtin = label only).
2. **Body rewrite order:** `[^N]` first, then legacy `^[article:hash]` — both
   forms supported; non-overlapping tokens; same numbering space (legacy hash
   matching a frontmatter type=article ref reuses that id).
3. **Failure handling:** unknown `[^N]` id -> `logger.warning` + leave literal
   token in body. Do NOT raise / do NOT silently drop.

## Tasks

### Task 1 — refactor `_convert_wiki_citations` + template + tests

- `kb/export_knowledge_base.py`
  - Add `FOOTNOTE_CITATION_RE = re.compile(r"\[\^(\d+)\]")`
  - Add `_normalize_frontmatter_sources(raw)` — accept legacy string list
    OR new dict list; normalize to flat dict list with `type`/`ref`.
  - Add `_build_source_url(src, base_path)` — article -> internal,
    web -> ref, builtin -> "".
  - Refactor `_convert_wiki_citations` signature:
    `(body_md, base_path, frontmatter_sources=None, *, page_slug="")`
  - Process [^N] first, then legacy ^[article:hash]; merge into single
    sources list with shared n numbering; back-compat `hash` field on
    type=article entries.
- `kb/templates/wiki_entity.html`
  - Replace hard-coded `<a href="{{ src.url }}">article:{{ src.hash }}</a>`
    with if/elif by `src.type` (article / web / builtin / fallback).
- `tests/unit/kb/test_export_wiki_citations.py` (new file)
  - 11 tests covering: normalize legacy/dict/empty, legacy-only render,
    legacy-no-frontmatter, new-format multi-type, mixed format, unknown
    [^N] warning, source count (legacy + new), template per-type markup.

**Verify:**

- `pytest tests/unit/kb/test_export_wiki_citations.py -v` — 11/11 pass
- Wiki-only dry-run bake (`.scratch/bake_wiki_only.py`):
  - All 19 entity pages render
  - copilot-studio.html: 21 sources, web/builtin types render, body has
    42 `<sup class="wiki-cite">`, 0 literal `[^N]`
  - claude-code.html: legacy article-only sources render with
    `article:<hash>` label, 32 `<sup>`, 0 literal `^[article:`

**Files:**

- `kb/export_knowledge_base.py` (modified)
- `kb/templates/wiki_entity.html` (modified)
- `tests/unit/kb/test_export_wiki_citations.py` (new)

**Done:** atomic commit with all 3 files; no `_ssg/` changes; no SCHEMA /
wiki_lint / wiki_inject changes.

## Constraints

- A. No push origin main
- B. No SCHEMA.md changes
- C. No kb/wiki_lint.py changes
- D. No kb/wiki_update.py / kb/services/wiki_inject.py changes
- E. Legacy `^[article:hash]` must continue to render byte-identical
- F. No other wiki file changes (Surgical)
- G. No `_ssg/` modifications
- H. Atomic commit, no push
