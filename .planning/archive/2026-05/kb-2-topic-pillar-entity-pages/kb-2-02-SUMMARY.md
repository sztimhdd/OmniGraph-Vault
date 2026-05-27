---
phase: kb-2-topic-pillar-entity-pages
plan: 02
type: execute
wave: 1
depends_on: []
files_modified: [kb/locale/zh-CN.json, kb/locale/en.json]
requirements: [TOPIC-03, ENTITY-03, LINK-03]
---

# kb-2-02 — Locale Keys Plan Summary

## Objective
Ship 26 new bilingual i18n keys per UI-SPEC §5 verbatim table. Pure additive change.

## Tasks
1 task — JSON merge.

## Dependency graph
- **Depends on:** none (Wave 1, parallel with plans 01 + 03)
- **Consumed by:** plans 06 (topic.html + entity.html), 07 (index.html + article.html extensions)

## Tech-stack notes
- No code, no test, no Skill invocation. Localization data only.
- Keys are dot-strings (kb-1 i18n convention) — flat object structure preserved.
- Existing `validate_key_parity()` from kb-1's `kb/i18n.py` enforces zh ↔ en parity at SSG build time (already wired into export driver Task 2 of kb-1-09).

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
None — text values originate from kb-2-UI-SPEC.md §5 which was authored by ui-ux-pro-max + frontend-design Skills at UI-SPEC time. Mechanically copying values verbatim does NOT need a fresh invocation.

## Acceptance signal
`validate_key_parity()` exits 0 + all 26 keys present in both locales with verbatim values.

---

## Execution Record (appended 2026-05-13)

**Status:** COMPLETE — Wave 1 ready.

### What was done

Single Task 1 — added 26 new kb-2 i18n keys to both `kb/locale/zh-CN.json` and `kb/locale/en.json`, copied verbatim from `kb-2-UI-SPEC.md §5`. Pure additive change; existing kb-1 keys untouched.

| Locale | Keys before | Keys after | Delta |
|---|---|---|---|
| zh-CN.json | 97 | 123 | +26 |
| en.json | 97 | 123 | +26 |

### Verification (all PASS)

- `validate_key_parity()` returns `True` — both locales have IDENTICAL key sets.
- `tests/unit/kb/test_i18n.py` — 8/8 PASS in 0.18s.
- JSON files parse cleanly via `json.load()`.
- Verbatim spot-check (10 representative keys × 2 locales) all match UI-SPEC §5 table.
- Regression guard: `site.brand` (kb-1 key) still `企小勤` / `VitaClaw` — confirms surgical-changes principle held (no file regenerated).
- All 5 topic slugs present in both locales: `agent`, `cv`, `llm`, `nlp`, `rag` (each with `.name` + `.desc`).

### New keys (full list, 26)

`breadcrumb.topics`, `breadcrumb.entities`, `topic.agent.name`, `topic.agent.desc`, `topic.cv.name`, `topic.cv.desc`, `topic.llm.name`, `topic.llm.desc`, `topic.nlp.name`, `topic.nlp.desc`, `topic.rag.name`, `topic.rag.desc`, `topic.article_count_label`, `topic.cooccurring_entities_title`, `topic.empty_title`, `topic.empty_hint`, `entity.article_count_label`, `entity.lang_distribution_aria`, `entity.empty_title`, `entity.empty_hint`, `home.section.topics_title`, `home.section.entities_title`, `home.topic.browse`, `article.related_aria`, `article.related_entities`, `article.related_topics`.

### Reconciling "28 vs 26"

The plan + UI-SPEC §5 footer mention "28 new keys" but the §5 verbatim table enumerates 26 distinct keys. Per the plan's explicit instruction ("Following the verbatim table is canonical; the literal output is 26 new keys"), 26 is the ship count. The "28" is a pre-publication arithmetic artifact (5 topics × 2 attributes counted twice). Plans 06 + 07 templates only reference the 26 keys present.

### Foundation enabled

- **TOPIC-03**: topic page header can render `{{ 'topic.{slug}.name' | t(lang) }}` + `{{ 'topic.{slug}.desc' | t(lang) }}` for all 5 topics.
- **ENTITY-03**: entity page header can render `{{ 'entity.lang_distribution_aria' | t(lang) }}` aria-label.
- **LINK-03**: homepage section headers can render `{{ 'home.section.topics_title' | t(lang) }}` + `{{ 'home.section.entities_title' | t(lang) }}`.
- **LINK-01/02** (article aside extensions): `article.related_aria`, `article.related_entities`, `article.related_topics` ready for plan 07 article.html extensions.

### Deviations from plan

None. Plan executed exactly as written.

### Self-Check: PASSED

- File `kb/locale/zh-CN.json` exists, parses, contains all 26 new keys verbatim.
- File `kb/locale/en.json` exists, parses, contains all 26 new keys verbatim.
- `validate_key_parity()` succeeds (no AssertionError).
- 8/8 kb-1 i18n unit tests still pass.
