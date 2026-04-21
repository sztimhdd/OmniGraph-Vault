# Phase 1: Bug Fixes + Gate 6 Validation - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix all known bugs blocking Gate 6, then prove cross-article synthesis works on this machine using two-layer validation: manual script run (confirms execution) + skill_runner.py (confirms routing).

New capabilities (shell wrappers, full skill packaging, Phase 2 SKILL.md) are out of scope for this phase.

</domain>

<decisions>
## Implementation Decisions

### Path Constants (INFRA-01)

- **D-01:** Add `ENTITY_BUFFER_DIR = BASE_DIR / "entity_buffer"` to `config.py` — under `~/.hermes/omonigraph-vault/`, consistent with the existing `BASE_DIR` pattern.
- **D-02:** Add `CANONICAL_MAP_FILE = BASE_DIR / "canonical_map.json"` to `config.py` — same dir, not project root.
- **D-03:** All scripts that reference entity_buffer or canonical_map.json must import and use these constants from `config.py`.

### Fix Scope

- **D-04:** Fix all 7 items from `.planning/codebase/CONCERNS.md`:
  - INFRA-01: Add `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE` to `config.py`
  - INFRA-02: Replace all hardcoded `/home/sztimhdd/` paths across all affected files
  - INFRA-03: Add `import json` to `kg_synthesize.py`
  - INFRA-04: Change default mode from `"naive"` to `"hybrid"` in `kg_synthesize.py`
  - Adjacent: Replace bare `except:` clauses with `except Exception as e:` + logging in `cognee_wrapper.py` (line 94) and `ingest_wechat.py` (line 158)
  - Adjacent: Fix undefined variable references in `ingest_pdf()` — replace `url` with `file_path`, `full_content` with `full_text`; compute `article_hash` from `file_hash`; create entity buffer dir before writing
  - Adjacent: Add image download success/failure counter in `ingest_wechat.py`; log warning if success rate < 50%

### Gate 6 Validation (Two-Layer)

- **D-05:** Validation = manual script run (confirms no crash, exit 0) + skill_runner.py (confirms routing). Both layers required. No separate `verify_gate_6.py`.
- **D-06:** Manual run: ingest 3 WeChat articles with shared named entities → run `cognee_batch_processor.py` → run `kg_synthesize.py "<cross-article query>"`. Verify synthesis response references entities from ≥2 articles.
- **D-07:** skill_runner test: Use full TEST-01 suite — trigger phrase matching, missing key guard, non-WeChat URL guard, wrong-skill redirect. Existing file `tests/skills/test_omnigraph_ingest.json` has 8 cases; add the non-WeChat URL guard case before running.

### skill_runner Test File

- **D-08:** The non-WeChat URL guard case is the only gap in the existing test file. Decision on SKILL.md behavior for non-WeChat URLs: guard/reject them (Phase 2 will formalize; for Phase 1 add the test case and update SKILL.md Case 5 to match).

### Claude's Discretion

- Exact log message wording for the image download counter warning (e.g., "Warning: X/Y images failed")
- Whether `ingest_pdf()` fix is a minimal variable-name repair or a broader async consistency fix — keep it minimal (don't fix the async consistency issue; that's Phase 2 scope)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and Roadmap
- `.planning/REQUIREMENTS.md` — all Phase 1 requirements (INFRA-01..04, GATE6-01..05) with acceptance criteria
- `.planning/ROADMAP.md` — Phase 1 success criteria (5 criteria including manual run + skill_runner)

### Bug Locations and Fix Approaches
- `.planning/codebase/CONCERNS.md` — confirmed bug locations with file:line evidence and fix approaches for all 7 items in scope

### Code Files to Modify
- `config.py` — add `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE` constants here; existing pattern: `BASE_DIR = Path.home() / ".hermes" / "omonigraph-vault"`
- `kg_synthesize.py` — line 44 (`mode: str = "naive"` → `"hybrid"`), line 50 (hardcoded canonical_map path), missing `import json`
- `ingest_wechat.py` — lines 279, 280, 368 (hardcoded paths); line 158 (bare except); image download loop error counter
- `cognee_batch_processor.py` — lines 9, 30, 35, 36 (hardcoded paths)
- `cognee_wrapper.py` — line 8 (hardcoded path), line 94 (bare except)
- `init_cognee.py` — lines 5, 23 (hardcoded paths)
- `list_entities.py` — line 5 (hardcoded path)
- `query_lightrag.py` — line 12 (hardcoded path)
- `tests/verify_gate_a.py` — lines 6, 7 (hardcoded paths)
- `tests/verify_gate_b.py` — line 6 (hardcoded path)
- `tests/verify_gate_c.py` — line 33 (hardcoded path)
- `setup_cognee.py` — line 23 (hardcoded path)

### skill_runner Test Assets
- `skills/omnigraph_ingest/SKILL.md` — existing skill; Case 5 needs update to reject non-WeChat URLs (add guard)
- `tests/skills/test_omnigraph_ingest.json` — existing 8-case test file; add non-WeChat URL guard case

</canonical_refs>

<deferred>
## Deferred Ideas

None raised during discussion.

</deferred>
