# W5A Gap-Closure Verification — cbf3b77f + 7c1c57cc

**Verifier:** Fresh independent reviewer (not the implementer)
**Date:** 2026-08-11
**HEAD verified:** `7c1c57cc87b71ee1b9ade670f44bdf2a45ce2538` (branch `main`, origin/main synced, tree clean)
**Commits under review:**
- `cbf3b77f` — GAP 2 (SET_METADATA allowlist in `classify_patch`) + GAP 3 (full WikiPatch serialization in suggestions)
- `7c1c57cc` — GAP 1 (final candidate validation gates in shared apply path)

**Authoritative design:** `docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5a-patch-compiler-design.md` §5.3 (SET_METADATA), §5.4 (structured suggestions), §7 (module boundaries / validation order / apply flow), §9-§10 (W3 contract / policy matrix).

Method: commit messages were NOT trusted. Every item was verified against current code at HEAD, with evidence cited as `file:line`. Full suite run with `venv/bin/python -m pytest`.

---

## Overall verdict: **PASS** (18/18 checklist items)

---

## GAP 1 — §7 final candidate validation in shared apply path (7c1c57cc)

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Candidate validation runs on the assembled candidate BEFORE `_atomic_write` | **PASS** | `kb/wiki_compiler/engine.py:417-443` — `_render_candidate` at :418, `_validate_candidate` at :430-432, blocking check at :433-440, `_atomic_write` at :443. All inside the flock (:375 acquire, :445-446 release). Matches design §7 apply flow "assemble candidate → final validation → atomic tempfile + replace". |
| 2 | Reuses `kb.wiki_lint` primitives — no second lint implementation | **PASS** | `engine.py:117` imports `lint_backlink_validity, lint_citation_integrity` from `kb.wiki_lint`; used at :834 and :843. Frontmatter parse reuses the shared `frontmatter` lib (:825). No new lint logic written in the gates. |
| 3 | Frontmatter parse failure → rejected, no write | **PASS** | `engine.py:824-828` — `frontmatter.load` exception → blocking list → :433-440 rejected before write. Mirrors wiki_health `check_yaml_validity` ERROR (`scripts/wiki_health.py:45-46`). Minor coverage note: no dedicated test anchor with malformed YAML (only docstring mention in `test_wiki_compiler_candidate_gates.py:10`); the code path is identical to the tested citation-blocking path. |
| 4 | Citation integrity failure → rejected, no write, Error Book with patch provenance | **PASS** | `engine.py:833-837` (lint failures → blocking), :433-440 (`_report_error_book` with `lint_name="wiki_compiler:candidate_integrity"` then `rejected`, return before write). Provenance payload at :1041-1050: `lint_name`, `page_path`, `failures`, `patch_id`, `trigger`, `compiler_version`. Covers `[^N]` id not in `sources[]`, unknown type, article ref not in known corpus (all handled inside `lint_citation_integrity`). |
| 5 | Wikilink handling matches current policy (WARN, documented, non-blocking) | **PASS** | `engine.py:839-846` — broken backlinks appended to `warnings`, never blocking. Policy cited in module docstring :63-69 and `_validate_candidate` docstring :799-804. Repo policy verified: `scripts/wiki_health.py:98-114` `check_wikilinks` appends to `findings["warns"]`. §10 "candidate WARN only → conservative policy; no silent promotion" = apply proceeds with warning recorded. Deviation from master-review phrasing is documented in the test docstring (`test_wiki_compiler_candidate_gates.py:19-30`). |
| 6 | `suggestion_only` path unchanged — never mutates target page | **PASS** | `engine.py:361-370` — suggestion path returns before lock acquisition; only `_write_suggestion` runs (JSON under `_suggestions/`). Gates exist solely inside the auto_apply branch (:372+). |
| 7 | No network calls in new validation code | **PASS** | `engine.py` imports are stdlib + `frontmatter` + `kb.wiki_compiler.{assembler,models}` + `kb.wiki_lint` (no requests/urllib/httpx/aiohttp/socket — grep 0 matches). `kb/wiki_lint.py` also has zero network imports. New code uses only `tempfile`/`shutil`/`pathlib`/`frontmatter`. |
| 8 | 6 gate tests all pass, mapped to requirements | **PASS** | All 6 pass (see mapping below). |

### GAP-1 test mappings (`tests/unit/test_wiki_compiler_candidate_gates.py`, 6/6 passed)

| Test | Requirement mapped |
|---|---|
| `test_create_page_unresolved_article_citation_rejected` (:191) | unresolved citation (`[^1]` ref not in evidence-known hashes) → `rejected`, target absent (no apply) |
| `test_create_page_broken_wikilink_warn_policy_applies` (:215) | broken `[[wikilink]]` → current-policy behavior: applies + `warnings` records "broken wikilink [[no-such-entity]]" (deviation documented in docstring) |
| `test_create_page_valid_canonical_still_applies` (:252) | valid canonical CREATE_PAGE → `applied`, `warnings == []`, exact content written |
| `test_blocking_failure_leaves_no_target_or_temp_leftovers` (:276) | failure precedes write: no target, no `.tmp`, no `.candidate-check-*` leftovers; only the by-design persistent `.md.lock` remains |
| `test_error_book_records_candidate_integrity_failure` (:309) | Error Book receives failure: exactly 1 call, `lint_name == "wiki_compiler:candidate_integrity"`, `patch_id`/`page_path`/`failures` present |
| `test_uat_good_engine_fixture_shape_still_applies` (:338) | UAT-good canonical candidate (id-carrying sources) still passes gates and applies |

---

## GAP 2 — §5.3 SET_METADATA allowlist (cbf3b77f)

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 9 | `classify_patch` rejects/defers SET_METADATA with keys outside `NON_CRITICAL_METADATA_KEYS = {last_updated, confidence_level}` | **PASS** | `engine.py:123` (`NON_CRITICAL_METADATA_KEYS = frozenset({"last_updated", "confidence_level"})`); :220-227 collects metadata keys from EVERY op and returns `suggestion_only` when any key is outside the allowlist. |
| 10 | `created` can never be mutated on existing pages (MERGE_SOURCES + SET_METADATA{created} can NEVER auto-apply) | **PASS** | Two independent layers: (a) `classify_patch` allowlist check :220-227 runs BEFORE the MERGE_SOURCES branch :240-247 — a critical key forces `suggestion_only` before any merge can classify; (b) defense-in-depth: `_set_metadata` :754-757 filters to allowlisted keys only, so the candidate renderer never rewrites `created` even in suggestion mode. |
| 11 | Regression test exists and passes: MERGE_SOURCES + SET_METADATA(created=…) on existing page → never auto-applies → created unchanged | **PASS** | `tests/unit/test_wiki_compiler_engine.py:500` `test_apply_patch_merge_plus_critical_metadata_suggestion_only` — end-to-end: status `suggestion`, page byte-identical to before, `created: '2026-05-20'` preserved and `created: '1999-01-01'` absent from `suggested_content`. Plus `test_classify_merge_plus_critical_set_metadata_suggestion_only` (:352) and render guard `test_set_metadata_render_skips_critical_keys` (:537). All pass. |
| 12 | Allowlist enforced at the SHARED engine boundary, not adapters/assembler | **PASS** | Enforcement lives in `kb/wiki_compiler/engine.py` (`classify_patch` :220-227, `_set_metadata` :754-757) — the single shared apply path used by both W1 (`scripts/wiki_generate_pages.py`) and W3 (`kb/wiki_update.py`) adapters. No adapter/assembler copies exist. |

---

## GAP 3 — §5.4 structured suggestions (cbf3b77f)

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 13 | Suggestion JSON contains full serialized WikiPatch; `payload["patch"]` round-trips via `WikiPatch.from_dict` | **PASS** | `engine.py:567` `"patch": patch.to_dict()` (all 15 fields). Round-trip asserted in `test_suggestion_payload_contains_full_serialized_wikipatch` (`test_wiki_compiler_engine.py:747-794`): every field present, `WikiPatch.from_dict(serialized) == original` (accounting for documented `metadata=None → {}` normalization in `models.from_dict` for CREATE_PAGE/UPSERT_SECTION ops). Passes. |
| 14 | Policy/classification outcome + validation diagnostics present in JSON | **PASS** | `engine.py:568-569` — `policy_hint: "suggestion_only"`, `reason: patch.reason`. Asserted at `test_wiki_compiler_engine.py:740-741, 797-801`. |
| 15 | `suggested_content` present | **PASS** | `engine.py:570` — `_render_candidate(patch, current_text)`; asserted (`"Suggested body [^1]" in payload["suggested_content"]`, :744/:801). |
| 16 | Deterministic filename semantics unchanged — same logical patch → same path, no duplicates | **PASS** | `engine.py:577` — `_suggestions/<slug>-<patch-id>.json`, no timestamps. Guarded by `test_suggestion_filename_deterministic_no_duplicates` (:804) — same patch twice → same path, exactly one file. Passes. |
| 17 | No new database; no bulk migration; legacy suggestion files untouched | **PASS** | Both commits touch only `kb/wiki_compiler/engine.py` + the two test files (verified via `git show --stat`). No DB, no migration code. Engine writes only `.json` suggestions; no code reads/deletes/rewrites legacy `.md` suggestions (grep of `kb/` for `_suggestions`: engine write path + docs only). |
| 18 | Round-trip test passes: `WikiPatch.from_dict(payload["patch"]) == original_patch` | **PASS** | `test_wiki_compiler_engine.py:784-794` (see item 13). Passes in the suite run. |

---

## Full suite

Specified 13-file set (`models/assembler/engine/w3_convergence/w1_adapter/candidate_gates/w5_0 + hook/generate + wiki_lint/citations/centrality/baseline_bench`), HEAD `7c1c57cc`, `venv/bin/python -m pytest`:

**158 passed, 0 failed, 0 skipped** (1.91s)

| File | Tests |
|---|---|
| test_wiki_compiler_models.py | 29 |
| test_wiki_compiler_assembler.py | 19 |
| test_wiki_compiler_engine.py | 34 |
| test_wiki_compiler_w3_convergence.py | 11 |
| test_wiki_compiler_w1_adapter.py | 16 |
| test_wiki_compiler_candidate_gates.py | 6 |
| test_wiki_w5_0.py | 10 |
| integration/test_wiki_hook.py | 2 |
| integration/test_wiki_generate.py | 4 |
| test_wiki_lint.py | 7 |
| test_wiki_citations.py | 2 |
| test_wiki_centrality.py | 3 |
| test_baseline_bench.py | 15 |

**Count reconciliation (the "expect 164" figure):** the expected 164 = the 13-file set (158) + `tests/unit/test_ingest_from_db_orchestration.py` (6 tests — W3 `_wiki_update_check` hook-orchestration anchors, T6). That file was run separately: **6 passed** (14.36s) → 164 total across both sets. Both numbers verified; no tests missing, skipped, or deselected (no `addopts`/marker deselect in `pyproject.toml`).

---

## Residual notes (true W5B items only — NOT the three gaps)

1. **§7 order 9-10 (contradiction/staleness) intentionally not run** on auto-apply candidates — candidate is fresh by construction (`last_updated` written now); LLM-semantic contradiction review is W5B scope. Documented at `engine.py:70-73` and `_validate_candidate` docstring :802-804. Design-compliant, not a gap.
2. **Re-apply of persisted suggestion JSON is W5B work** — the embedded `payload["patch"]` is consumable, but `apply_suggestion_atomic` re-application awaits W5B by design (engine currently writes suggestions; consumption is W5B's autonomous-evolution path).
3. **wiki_health corpus severity differs from the candidate gate by design**: `check_citations` treats "article ref not in DB corpus" as WARN, while the gate blocks. This is the documented conservative reading of §7 order 7 + §10 ("candidate health/lint ERROR → reject"), recorded in the gate reference and module docstring — stricter than health, deliberately.
4. **Minor coverage gap (not a closure defect):** no dedicated malformed-YAML test anchor for the frontmatter-parse gate (item 3). The code path is real and correct; the 6 behavior anchors cover the citation-blocking path, which shares the identical reject/Error-Book/no-write machinery.
5. No new files created outside the report; no repo files modified by this verification.

---

*Report written by fresh independent verifier; all verdicts derived from code at HEAD `7c1c57cc`, not from commit messages or prior review documents.*
