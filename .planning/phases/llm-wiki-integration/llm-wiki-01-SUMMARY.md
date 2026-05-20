# W0 Scaffold — SUMMARY

**Phase:** llm-wiki-integration
**Plan:** 01 (W0 scaffold)
**Wave:** 0
**Status:** Complete (autonomous)
**Date:** 2026-05-19

## Files Created

### Wiki scaffold (`kb/wiki/`)
- `kb/wiki/SCHEMA.md` — formal contract (frontmatter + citation + cross-ref + lint)
- `kb/wiki/index.md` — directory listing (entities/openclaw bullet seeded)
- `kb/wiki/log.md` — operation log (W0 entry seeded)
- `kb/wiki/README.md` — human-readable scaffold doc + sync mechanism + rollback
- `kb/wiki/entities/openclaw.md` — placeholder with frontmatter + `^[article:0000000000]` citation; W1 will overwrite with real LightRAG synthesis
- `kb/wiki/{entities,concepts,comparisons,queries,_suggestions}/.gitkeep` — empty subdir markers

### Hermes operator prompt
- `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` — two-section operator prompt (Section 1 read-only export, Section 2 production symlink) per CLAUDE.md Rule 5 (no SSH outsourcing)

### Test stubs (`@pytest.mark.skip`)
- `tests/unit/test_wiki_lint.py` (4 stubs: test_unresolved_citation, test_contradicts_existing, test_backlink_validity, test_staleness_check)
- `tests/unit/test_wiki_centrality.py` (test_centrality_ranking)
- `tests/unit/test_wiki_citations.py` (test_all_pages_cited)
- `tests/integration/test_wiki_hook.py` (test_end_of_cron_fires)
- `tests/integration/test_wiki_generate.py` (test_one_entity_full)
- `tests/integration/kb/test_synthesize_wiki_inject.py` (test_wiki_context_injected_into_prompt)
- `tests/unit/kb/test_synthesize_wiki_fallthrough.py` (test_falls_through_when_wiki_missing)

## Verification

- All 4 wiki docs + entities/openclaw.md grep-pass for required markers (frontmatter, citation, symlink, rollback)
- pytest --collect-only on the 7 stub files: **10 tests collected** (matches expected — test_wiki_lint has 4, others have 1 each)
- pytest run: **10 skipped, 0 failed, 0 errored**
- No `ssh` invocation issued during W0 (per Rule 5 + plan acceptance criterion)

## Hermes Operator Prompt — Forwarding Guidance

- **Section 1** (read-only export): forward to Hermes any time the user wants to compare existing `~/wiki-omnigraph/` content against repo state. Safe.
- **Section 2** (production symlink): **DO NOT forward until W1 has replaced the placeholder `kb/wiki/entities/openclaw.md` with real generated content.** The file currently contains a placeholder that would be served live to Hermes if symlinked early.

## Notes

- `kb/wiki/entities/openclaw.md` is a W0 placeholder (frontmatter shape correct, body marked TODO with placeholder hash `0000000000`). W1 generates real content using `scripts/rank_wiki_entities.py` + LightRAG hybrid query.
- No KB runtime code touched — no Local UAT required this wave per CLAUDE.md Rule 6 (W3/W4 trigger Local UAT).
- Stop checkpoints respected: no Section 2 forwarded; no real LLM/embedding cost incurred.
