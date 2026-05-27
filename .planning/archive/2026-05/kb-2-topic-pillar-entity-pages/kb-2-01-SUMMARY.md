---
phase: kb-2-topic-pillar-entity-pages
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/kb/conftest.py
  - tests/integration/kb/test_export.py
requirements: [TOPIC-02, ENTITY-01, ENTITY-03, LINK-01, LINK-02]
---

# kb-2-01 — Fixture Extension Plan Summary

## Objective
Build shared `fixture_db` (Hermes-prod-shape SQLite) consumed by every kb-2 query / integration test.

## Tasks
1 task — purely additive test infra. No production code modified.

## Dependency graph
- **Depends on:** none (Wave 1 root, parallel with plans 02 + 03)
- **Consumed by:** plans 04 (query function unit tests), 09 (integration test)

## Tech-stack notes
- Pure pytest fixture extension. No new deps.
- Mirrors Hermes prod schema verified via SSH 2026-05-13: classifications has 3945 rows / 5 topics; extracted_entities has 5257 rows / 91 entities at ≥5-article freq.
- Fixture downscale: 8 articles + 22 entity rows (6 above + 2 below threshold). Exercises every code path without prod-volume bloat.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
None — pure test data, no UI surface, no business logic. The `python-patterns` rule applies (PEP 8 + type hints + dataclass-like constants), but the rule is loaded automatically — no `Skill()` invocation required for non-UI test infra.

## Acceptance signal
`pytest tests/integration/kb/test_export.py -v` returns 6/6 PASS after fixture refactor (kb-1 baseline preserved via assertion-number bumps only — no test logic change).

---

## Execution Results (2026-05-13)

**Status:** Complete. 1/1 task. Commit `5830639`.

### Verified data shape

| Metric | Target | Actual |
| --- | --- | --- |
| KOL articles | 5 | 5 (ids 1-5) |
| RSS articles | 3 | 3 (ids 10-12) |
| Topics in `classifications.topic` | 5 distinct | 5: Agent / CV / LLM / NLP / RAG |
| `classifications` rows | ~20 | 16 (depth_score >= 2 throughout) |
| Entities ≥ 5-article freq (ENTITY-01 above) | ≥ 6 | 6: OpenAI, LangChain, LightRAG, Anthropic, AutoGen, MCP (each freq=5) |
| Entities < 5-article freq (negative coverage) | ≥ 2 | 2: ObscureLib (freq=2), OneOffMention (freq=3) |
| `extracted_entities` rows total | n/a | 35 |
| Articles passing TOPIC-02 cohort gate | 8/8 | 8/8 (all have `layer1='candidate'` OR `layer2='ok'`) |

### kb-1 baseline preservation

```text
$ pytest tests/integration/kb/test_export.py -q
......                                                                   [100%]
6 passed in 3.16s
```

Three mechanical assertion bumps in `test_export.py::test_export_produces_expected_output_tree`:

- `len(detail_files) == 3` → `== 8` (5 KOL + 3 RSS)
- `sitemap.count("<url>") == 6` → `== 11` (3 index + 8 articles)
- `len(url_index) == 3` → `== 8`

No test-logic changes. Body constants (`_BODY_WITH_LOCALHOST` / `_BODY_SHORT_FOR_OG_FALLBACK` / `_BODY_EN_PLAIN`) moved to conftest; `test_export.py` imports `_BODY_SHORT_FOR_OG_FALLBACK` (only one still referenced inside the test file itself for the og:description fallback hash recompute).

### Files modified

| File | Change |
| --- | --- |
| `tests/integration/kb/conftest.py` | Created (197 lines) — `build_kb2_fixture_db()` + `fixture_db` pytest fixture + `_BODY_*` constants |
| `tests/integration/kb/test_export.py` | Refactored — removed local `fixture_db` def + `_BODY_*` constants (now imported from conftest), bumped 3 assertion numbers |

### Commit

`5830639 test(kb-2-01): extend kb fixture with classifications + entities + layer verdicts`

### Deviations

**[Rule 3 — Blocking, externally-caused] Parallel-agent staging-area pollution**

The git index already contained two pre-staged files from a sibling kb-2 agent's worktree session (`kb-2-03-SUMMARY.md` + `kb/templates/_icons.html`). Per CLAUDE.md 2026-05-11 lesson, `git add <explicit-files>` was used — but `git commit` always commits everything in the index, not only what was just added. The two sibling files therefore got swept into commit `5830639` under the kb-2-01 message. Per CLAUDE.md 2026-05-06 lesson (rjs/STK-02/03 incident), forward-only repair was chosen: the file *contents* in HEAD are byte-identical to the sibling's spec, only the commit attribution is wrong. The sibling kb-2-03 agent will see those files already in HEAD and can either accept the mis-attribution or follow up with a forward-only re-attribution commit. Did NOT use `git reset` or `git commit --amend` (forbidden on shared worktrees).

No CLAUDE.md violations. No code-quality issues. No new tokens. No production-code changes.

### Foundation for downstream plans

- **Plan 04** (`kb/data/article_query.py` query functions) can now TDD against `fixture_db`:
  - `list_topic_cohort(topic, cohort_filter)` — exercises `classifications` + cohort gate
  - `list_articles_by_entity(entity_name)` — exercises `extracted_entities`
  - `list_topics_with_counts()` — 5 distinct topics ready
  - `list_entities_above_threshold(min_freq=5)` — 6 above-threshold + 2 below for negative tests
- **Plan 09** (integration test) consumes the same fixture for end-to-end SSG-output assertions on topic + entity pages.

### Self-Check: PASSED

- `tests/integration/kb/conftest.py` — exists in HEAD `5830639`
- `tests/integration/kb/test_export.py` — modified in HEAD `5830639`
- Commit `5830639` — found via `git log --oneline -1`
- pytest 6/6 PASS — verified post-commit
