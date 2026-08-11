# W5A Independent Verification — Final Verdict

- **Verifier:** independent final verifier (not involved in W5A implementation)
- **Date:** 2026-08-11 (verification run)
- **Repo:** `/home/sztimhdd/OmniGraph-Vault`, branch `main`
- **Local HEAD:** `507396fdca791d8e7473cd3e7e246aba95fe275f` (`docs(wiki-v2-w5a): add production UAT evidence report`)
- **origin/main:** `c8ec5227` (local is 1 docs-only commit ahead — see §11)
- **Implementation range reviewed:** `bc9fcce5..HEAD` (commits `64298303`, `8150e928`, `df573e1c`, `e8bdc664`, `ec787b3e`, `cbec5264`, `f40bfa34`, `c8ec5227`, `507396fd`; unrelated vision commits `ec3e7349`/`3bfe098f` ride in the range but touch no W5A files)
- **Method:** full read of design spec + plan + adversarial review + production UAT; full read of `kb/wiki_compiler/{models,assembler,engine}.py`, `kb/wiki_compiler/adapters/w3.py`, `kb/wiki_update.py`, `scripts/wiki_generate_pages.py`; targeted reads of tests; empirical runs (repair tests, full suite, standalone health, AST import-closure, greps, git diffs). Read-only except this report.
- **Worktree state:** clean (`git status` empty), no repo files modified by this verification.

---

## 1. Design compliance — 19 non-negotiable properties

The design doc (`docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5a-patch-compiler-design.md`) does not number a list of 19 properties; the enumeration below derives from its non-negotiable contract sections (§2 non-goals, §4 core principles, §5 model rules, §6 citation/schema, §7 engine, §8/§9 adapter policy, §10 policy matrix, §11 Error Book, §12 compatibility, §15 gates). Every property was checked against current code, not commit messages.

| # | Property (design ref) | Verdict | Evidence |
|---|---|---|---|
| 1 | **Markdown/frontmatter remains the Wiki source of truth**; `_suggestions/` = workflow artifacts only (§4.1) | **PASS** | All applied pages are `.md` under `kb/wiki/`; suggestions are JSON under `kb/wiki/_suggestions/` (`engine.py:467-493`); git untouched for page content (see §6). |
| 2 | **WikiPatch is the sole mutation unit** — no caller authoritatively replaces a whole existing page outside the shared compiler (§4.2, Gates B/E) | **PASS** | Both adapters build `WikiPatch` and route through `engine.apply_patch` (`wiki_update.py:167`, `wiki_generate_pages.py:1163-1167`). No `REPLACE_PAGE` op exists. Remaining direct writes are non-target artifacts only (see §5). |
| 3 | **Evidence normalized independently of Markdown style** — one normalized model, rendering preserves legacy or emits canonical (§4.3) | **PASS** | `EvidenceRef/EvidencePack/WikiPatch` (`models.py`) used by both W1 (`wiki_generate_pages.py:1139-1154`) and W3 (`w3.py:100-147`); engine detects legacy vs canonical (`engine.py:225-230`) and preserves style on merge. |
| 4 | **Substantive existing-page body mutation is suggestion-only in W5A** (§4.4, Gate B) | **PASS** | `classify_patch` returns `suggestion_only` whenever any op is `UPSERT_SECTION` (`engine.py:178-181`); CREATE on existing page also `suggestion_only` (`engine.py:174-176`). Existing-page patches from both adapters carry `UPSERT_SECTION` → never auto-apply. |
| 5 | **Narrow auto-apply only**: deterministic source merge / metadata update that preserves all body content (§4.4) | **PASS** | `MERGE_SOURCES` auto-applies only when the merge is frontmatter-only (`_merge_sources` never touches body; `engine.py:559-658`); `SET_METADATA` auto-applies only when keys ⊆ `{last_updated}` (`engine.py:192-198`). Legacy page + web/builtin evidence → `suggestion_only` (`engine.py:186-189`). |
| 6 | **Never auto-deletes/replaces** paragraph, section, image, or cross-reference (§4.4) | **PASS** | No `DELETE_*` op in the model (`models.py:21-23`); `classify_patch` rejects `DELETE_PAGE` outright (`engine.py:169-170, 292-297`); assembler never emits `UPSERT_SECTION` when there is no new content (`assembler.py:394-404`), so empty sections cannot be used to delete. |
| 7 | **Optimistic concurrency mandatory** — every update patch carries base digest; stale → conflict, never overwrite (§4.5, Gate C) | **PASS** | Model enforces non-CREATE patches require `base_digest` (`models.py:255-260`); engine re-checks digest under lock → `conflict` on mismatch/existence-change (`engine.py:328-352`); same-base concurrency test proves exactly one winner (`test_concurrent_same_base_at_most_one_applied`, passed; prod UAT C `['applied','conflict']`). |
| 8 | **W3 stays non-blocking** — no new network/LLM/Tavily/Databricks work in the ingest hook (§4.6, Gate F) | **PASS** | AST import closure of `wiki_update.py` + `wiki_compiler/*` + `kb/error_book.py` = stdlib + `kb` only; network/LLM import scan = NONE (see §7). Hook remains wrapped in the existing try/except + 120s outer timeout (unchanged caller `batch_ingest_from_spider.py:1592-1609`); prod UAT D confirmed service active + hook accounting format unchanged. |
| 9 | **Evidence identity rules**: article refs canonical 10-char lowercase hex resolved before apply; web = URL; builtin = null; `evidence_id` ≠ footnote number (§5.1) | **PASS** | `ARTICLE_REF_PATTERN = ^[a-f0-9]{10}$` enforced in `EvidenceRef.__post_init__` + `validate_evidence` (`models.py:94-103`, `engine.py:132-137`). Resolution happens in adapters before apply: W3 filters hashes through DB (`w3.py:173-177`), W1 validates refs ⊆ catalog (`wiki_generate_pages.py:838-844`). Footnote numbers are positional catalog positions, distinct from `evidence_id` (`assembler.py:25-30`). |
| 10 | **Operation allowlist**: only `CREATE_PAGE`/`UPSERT_SECTION`/`MERGE_SOURCES`/`SET_METADATA`; no generic replace/delete ops (§5.3) | **PASS** | `VALID_OPERATIONS` (`models.py:21-23`); `PatchOperation.__post_init__` and `WikiPatch.__post_init__` reject anything else; DELETE explicitly rejected in policy (`engine.py:169-170`). |
| 11 | **`CREATE_PAGE` valid only when target does not exist** (§5.3) | **PASS** | Model: CREATE requires `base_digest=None` (`models.py:248-254`); engine: create-target already exists → `conflict`, never overwrite (`engine.py:328-335`; test `test_apply_patch_conflict_when_create_target_exists` passed). |
| 12 | **`UPSERT_SECTION` targets exactly one H2**; `MERGE_SOURCES` union/dedup never subtractive; `SET_METADATA` only approved fields, preserves `created` (§5.3) | **PASS** (one residual note) | `_upsert_section` replaces exactly one `##` heading (`engine.py:534-556`); `_merge_sources` dedups by `(type, ref)`/`(type,title)` and only appends (`engine.py:579-601`); assembler `SET_METADATA` emits only `last_updated`/`confidence_level` (`assembler.py:405-415`), `created` never rewritten. Residual: `classify_patch`'s MERGE branch does not re-check sibling `SET_METADATA` keys, and `_set_metadata` has no allowlist of its own — a hand-crafted `(MERGE_SOURCES, SET_METADATA{created})` patch would auto-apply and rewrite `created` (adversarial MINOR-5). Unreachable from both adapters; documented residual for W5B (see §10). |
| 13 | **Structured suggestions** — `kb/wiki/_suggestions/<slug>-<patch-id>.json`, deterministic path, no timestamp duplicates (§5.4) | **PASS** (one deviation note) | Filename is `<slug>-<patch_id>.json` with no timestamp (`engine.py:491`); same patch → same path (test `test_suggestion_filename_deterministic_no_duplicates` passed; prod UAT A: exactly 1 file on re-apply). Deviation: payload is `{patch_id, target_slug, policy_hint, reason, operations, evidence, suggested_content}` — not the full serialized `WikiPatch` + outcome record of §5.4, and persisted suggestions are review-only (re-apply hits legacy-rebuild branch → `KeyError`). Adversarial MINOR-6, explicitly deferred to W5B; does not affect the authoritative apply path. |
| 14 | **New pages emit canonical SCHEMA.md representation** — typed `sources[]` + GFM `[^N]` citations (Gate D, §6) | **PASS** | Assembler renders `- id: N` positional first key + typed entries + `[^N]` body + `## References` (`assembler.py:433-452, 234-244`); W1 prompt + validator enforce the same (`wiki_generate_pages.py:438-457, 803-892`); `lint_citation_integrity` passes on rendered pages (test `test_rendered_page_passes_lint_citation_integrity` passed; prod UAT B lint `[]`). |
| 15 | **No bulk migration** — existing pages preserved, legacy citation style remains lint-supported (§6, §12) | **PASS** | `git diff bc9fcce5..HEAD -- kb/wiki/` = **0 lines** (see §6); `kb/wiki_lint.py` unchanged (legacy `^[article:...]` still lint-supported — health run flags them as *unresolved* only without DB corpus, never as format errors); legacy pages keep legacy rendering (`engine.py:613-616, 627-629, 641-643`). |
| 16 | **Apply engine sequence**: validate → per-page lock → recheck existence/digest → assemble → validate → atomic tempfile+replace; two same-base patches never both win (§7, Gate C) | **PASS** | `apply_patch` order verified: evidence validate (283) → classify (291) → lock acquire (313) → re-read (317-319) → digest/existence check (328-352) → render (356) → `_atomic_write` via `tempfile.mkstemp` + `os.replace` (362, 429-460) → unlock in `finally` (364-365). Concurrency test passed; prod UAT C confirmed exactly one winner + no stray temp files. |
| 17 | **Deterministic policy matrix** (§10): W1 new CREATE→auto_apply; W1 existing substantive→suggestion_only; W3 new+threshold+gates→auto_apply; W3 existing substantive→suggestion_only; stale digest→conflict/retry, never overwrite; missing/invalid evidence→reject; candidate lint ERROR→reject; WARN→no silent promotion | **PASS** (one residual note) | All rows verified in `classify_patch` + `apply_patch` (`engine.py:155-201, 282-352`) and adapter behavior (assembler hints `assembler.py:378, 420`; W3 frequency threshold `w3.py:189-192`; UAT E: 127/127 applied new pages, existing pages → suggestion). Residual: the shared engine itself runs evidence/schema-level validation only — the design §7 order 6–10 lint steps (citation/backlink/staleness/contradiction/health) run in W1's validator and are satisfied by construction for W3 (assembler-generated content; UAT B lint+health PASS). Adversarial MINOR-4; W5B must not assume the engine validates candidates. |
| 18 | **Error Book integration** — true integrity failures recorded with patch provenance; no new error DB; `suggestion_only`/`conflict` never logged as errors (§11) | **PASS** | Uses existing `kb.error_book.log_lint_failure` (`engine.py:820-859`); payload keys `lint_name=wiki_compiler:*`, `patch_id`, `trigger`, `compiler_version`; suggestion (299-308) and conflict (328-352) paths never log. `kb/error_book.py` untouched in range (no schema change). Residual: category hardcoded to `evidence_validation` for render/IO failures and policy-rejected not logged (adversarial MINOR-7) — non-blocking. |
| 19 | **Scope: no W5B/W6/W7/W8 features** — no runtime graph, `wiki_search`/`wiki_read`, N-hop, fusion, query-feedback, aggregation, frontend, answer caching, bulk citation migration, new paid service (§2, Gate I) | **PASS** | See §8. W5A commits touch only `kb/wiki_compiler/*`, `kb/wiki_update.py`, `scripts/wiki_generate_pages.py`, tests, `.gitignore`, `skills/omnigraph_ingest/SKILL.md`, review docs. No MCP tool surface, graph runtime, LLM provider, or service changes. |

**Design compliance result: 19/19 PASS** (three documented non-blocking residuals carried from the adversarial review: MINOR-4 engine lint depth, MINOR-5 SET_METADATA allowlist edge, MINOR-6 suggestion JSON completeness — all unreachable from production adapters, all deferred to W5B).

---

## 2. Repair verification (adversarial BLOCKER + 2 MAJOR, claimed fixed in `c8ec5227`)

### (a) W1 seam — BLOCKER (dead seam: TypeError + result-shape/status mismatch)

Verified in code at HEAD (`scripts/wiki_generate_pages.py`):
- `_compiler_engine()` returns `kb.wiki_compiler.engine.apply_patch` directly (line 954-965) — the plan-era `kb.wiki_compiler.apply` module no longer referenced.
- Seam call: `apply_fn(patch, wiki_root=output_dir.parent)` — **no `known_article_hashes` kwarg** (lines 1163-1167).
- Result read as plain **dict**: `apply_result.get("status", "rejected")` (line 1182).
- Status mapping: `applied`→`ok`; `suggestion`→`suggested` (with suggestion_path); `conflict`→`failed` (+"conflict" error); else→`failed` (lines 1187-1198).
- **Unstubbed guard test exists and passes** — `test_one_entity_real_engine_writes_page` monkeypatches ONLY `fetch_lightrag_context`/`fetch_tavily_results`/`call_opus`, never `_compiler_engine` (test source lines 211-242), and asserts a real page lands with status ok.

Command + output:
```
$ venv/bin/python -m pytest tests/integration/test_wiki_generate.py -v
4 passed in 0.13s
  test_one_entity_full PASSED
  test_one_entity_real_engine_writes_page PASSED   ← REAL engine, unstubbed
  test_dry_run_skips_llm PASSED
  test_validation_rejects_uncited_response PASSED
```
**REPAIR CONFIRMED.**

### (b) Merge — MAJOR (`_merge_sources` corrupts multi-line canonical blocks)

Verified in code: the insertion scan now advances past the list item AND deeper-indented continuation lines, stopping at the next column-0 key or block end (`engine.py:620-639`); new canonical entries are emitted id-first with `- id: len(existing)+i` (`engine.py:645-653`).

Command + output:
```
$ venv/bin/python -m pytest tests/unit/test_wiki_compiler_engine.py -v -k "merge"
5 passed, 24 deselected in 0.08s
  test_classify_merge_sources_legacy_incompatible_suggestion_only PASSED
  test_classify_merge_sources_canonical_auto_apply PASSED
  test_apply_patch_merge_sources_preserves_multi_entry_blocks PASSED   ← real apply path, 2-entry fixture
  test_merge_sources_suggestion_render_preserves_multi_entry_blocks PASSED
  test_apply_patch_merge_sources_canonical PASSED
```
**REPAIR CONFIRMED** (multi-entry fixtures re-parsed with `frontmatter`; every original entry keeps id/ref/title/provenance; new entry appended last).

### (c) id emission — MAJOR (canonical output omitted SCHEMA.md `id`)

Verified in code: assembler `_render_yaml` emits `- id: N` as the list marker with 4-space continuations (`assembler.py:443-449`); W1 `_typed_sources_yaml` renders `- id:` first (`wiki_generate_pages.py:447`); prompt instructs positional `id` as FIRST key (`wiki_generate_pages.py:562-563`); W1 validator rejects missing/misnumbered ids (`wiki_generate_pages.py:822-826`); `kb/wiki_lint.py` `lint_citation_integrity` (unchanged) resolves `[^N]` via `sources[].id`.

Command + output:
```
$ venv/bin/python -m pytest tests/unit/test_wiki_compiler_assembler.py tests/unit/test_wiki_compiler_w1_adapter.py -v
35 passed in 0.20s
  test_sources_entries_emit_positional_id PASSED
  test_rendered_page_passes_lint_citation_integrity PASSED
  test_validator_requires_positional_source_id PASSED
  test_prompt_instructs_positional_source_id PASSED
  ... (all 35)
```
**REPAIR CONFIRMED.** Independent corroboration: prod UAT B (deployed `c8ec5227`) produced `sources[]` with `id: 1,2,3` and `lint_citation_integrity → []`.

---

## 3. Full regression suite

Exact command:
```
venv/bin/python -m pytest tests/unit/test_wiki_compiler_models.py tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_compiler_engine.py tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_wiki_compiler_w1_adapter.py tests/unit/test_wiki_w5_0.py tests/integration/test_wiki_hook.py \
  tests/integration/test_wiki_generate.py tests/unit/test_wiki_lint.py tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_centrality.py tests/unit/test_baseline_bench.py -v
```

**Result: 147 passed, 0 failed, 0 skipped — 1.89s** (Python 3.12.3, pytest 9.0.3).
Coverage includes: W5-0 behavior anchors (`test_wiki_w5_0.py`), W3 hook integration (`test_wiki_hook.py`), W1 integration incl. unstubbed seam test, lint/citation/centrality/baseline regressions.

---

## 4. Standalone Wiki health (read-only, real `kb/wiki/`)

`scripts/wiki_health.py --help` confirms flags: `--json`, `--wiki-root`, `--db-path`, `--max-stale-days`, `--rebuild-index` (no index rebuild used).

Run A — without DB (as in the task's exact command):
```
$ venv/bin/python scripts/wiki_health.py --wiki-root kb/wiki --json
summary: pages_checked 19, errors 376, warns 185, db_hashes_loaded 0   (exit 1)
```
The 376 errors are all `unresolved legacy citation ^[article:<hex>]` on the 19 pre-existing legacy entity pages — the checker had **no DB corpus** (`db_hashes_loaded: 0`) to resolve legacy hashes against. No canonical/citation-format errors.

Run B — with the real corpus (production-equivalent):
```
$ venv/bin/python scripts/wiki_health.py --wiki-root kb/wiki --db-path data/kol_scan.db --json
summary: pages_checked 19, errors 0, warns 185, db_hashes_loaded 298   (exit 0)
```
- **0 errors** with DB-backed legacy-hash resolution. 185 warnings = broken wikilinks (`[[target]]` with no page) — pre-existing W1-era page content.
- **W5A cannot have changed health status:** `kb/wiki/` content is byte-identical to pre-W5A (`git diff bc9fcce5..HEAD -- kb/wiki/` = 0 lines) and `scripts/wiki_health.py` + `kb/wiki_lint.py` are unmodified in the range → identical input + identical checker ⇒ identical output.
- Independent corroboration: prod UAT B health on a canonical W5A-generated page: only expected `index.md missing` warning for an isolated root.

---

## 5. Zero-bypass audit (final)

`scripts/wiki_generate_pages.py`:
- Sole authoritative entity write path: `apply_fn(patch, wiki_root=output_dir.parent)` at line 1164 → `engine.apply_patch`. 
- `_atomic_write` (line 96) used only for `kb/wiki/index.md` (line 1247) — allowed non-target artifact.
- `write_text` only for `kb/wiki/_debug/<slug>-opus.md` and `_debug/<slug>-prompt.txt` (lines 1075, 1091) — allowed debug artifacts.
- `open(...,"a")` only for `kb/wiki/log.md` append (line 1203) — allowed log artifact.
- No `open(...,'w')` / `write_text` / `os.replace` targets any `kb/wiki/<kind>/<slug>.md`.

`kb/wiki_update.py`:
- **No** `_build_page`, **no** local `_atomic_write`, **no** timestamp `.md` suggestions — the only mentions are the module docstring describing their removal (lines 6-8).
- Sole write path: `_apply_suggestion_engine` → `engine.apply_patch` (line 167). Suggestion JSON written by the engine (`_write_suggestion`), never `.md`.

**RESULT: zero bypass — no authoritative target-page write exists outside the shared engine.**

---

## 6. No-bulk-modification evidence

```
$ git diff bc9fcce5..HEAD -- kb/wiki/ | wc -l        → 0
$ git diff bc9fcce5..HEAD --name-only -- kb/wiki/     → (empty)
```
- **0 lines changed** across all 19 entity pages, `index.md`, `SCHEMA.md`, `_suggestions/` in the entire W5A range. No page rewritten, no citation bulk-migrated, no legacy suggestion deleted.
- **Contract stability:** `kb/wiki_lint.py` — **unmodified** in range; `kb/wiki/SCHEMA.md` — **unmodified** in range (the plan's Task 5 "update SCHEMA.md for truth alignment" step was evidently not needed / not applied; the existing SCHEMA already matches emitted output, which is why the id-repair aligns to it). Both remain exactly as W5-0 left them.
- Local wiki = 19 entity pages; production remote = 26 (remote tree is dirty with uncommitted W3-created pages — environment divergence, not a W5A repo change; UAT E zero-write proof: 26→26, `_suggestions/` 5→5).

---

## 7. W3 network audit

AST import-closure analysis over `kb/wiki_update.py` + `kb/wiki_compiler/{models,assembler,engine}.py` + `kb/wiki_compiler/adapters/w3.py` + transitively imported `kb/error_book.py`:

```
IMPORT CLOSURE FILES: 6 (all kb/* or kb/wiki_compiler/*)
NON-kb/stdlib IMPORTS: __future__, dataclasses, datetime, fcntl, hashlib, json, os, pathlib,
                       re, sqlite3, tempfile, time, typing
NETWORK/LLM IMPORTS: NONE
```
Grep for `requests|httpx|aiohttp|openai|genai|tavily|databricks|subprocess|urllib` over the W3 path source files: **zero matches** (only a compiled `__pycache__` artifact matched; source is clean; the string `tavily-web` appears solely as a provenance label in `assembler.py`). W1's own acquisition (requests/Databricks/Tavily/LightRAG) is unchanged and permitted by design §8 — it is not in the W3 path. `sqlite3` is the DB read for hash filtering (`w3.py:174`), not network.

**RESULT: zero network/LLM imports in the W3 path.**

---

## 8. Scope compliance (no W5B/W6/W7/W8)

- Per-commit file inventory: the 9 W5A commits touch only `kb/wiki_compiler/*`, `kb/wiki_update.py`, `scripts/wiki_generate_pages.py`, `tests/*wiki*`, `.gitignore`, `skills/omnigraph_ingest/SKILL.md`, `docs/superpowers/reviews/*`. The range also carries two unrelated vision commits (`ec3e7349`, `3bfe098f` → `image_pipeline.py`, `lib/vision_cascade.py`, vision tests, `.env.*`) which touch no W5A files and are excluded from W5A scope.
- Grep of the W5A diff for `wiki_search|wiki_read|n_hop|hop traversal|score fusion|retrieval fusion|query.feedback|guard.query|affected.query|aggregation layer|answer cach|frontend|bulk migrat|citation migrat`: **no matches**.
- No MCP tool surface changes (diff name-list contains no `mcp/`/`server/`/`tool` files).
- No runtime graph, no N-hop traversal, no retrieval fusion, no query-feedback loop, no aggregation layer, no frontend, no answer caching, no bulk citation migration, no new paid provider/service.
- Legacy citations were deliberately **kept** lint-supported (`kb/wiki_lint.py` untouched), matching §6/§12.

**RESULT: W5A stays strictly within compiler-core scope.**

---

## 9. Overall verdict

# **PASS**

Justification:
- **19/19 design properties verified PASS** against current code (three documented non-blocking residuals, all pre-approved as MINOR by the adversarial review and unreachable from production adapters).
- **All 3 adversarial findings (1 BLOCKER + 2 MAJOR) are genuinely repaired** in `c8ec5227` and proven by tests that exercise the REAL engine path — not just claimed: the unstubbed W1 seam test would fail with the original TypeError if the seam regressed; the multi-entry merge tests re-parse frontmatter and would fail on the old splice corruption; the id-emission tests tie prompt → validator → assembler → surviving lint together.
- **147/147 regression tests pass**; standalone health = **0 errors** with DB-backed resolution on the real wiki, and health status is provably unchanged from pre-W5A (0-byte page diff + unmodified checker).
- Zero-bypass, zero-bulk-mod, zero W3 network, zero scope creep — all independently confirmed.
- Production UAT (A/B/C/D/E, deployed `c8ec5227` on 47.117.244.253) independently corroborates: structured suggestion with unchanged digest, canonical create with lint/health PASS, exactly-one-winner concurrency, service healthy, 127/127 isolated creates with zero production writes.

---

## 10. Residual risks / deferred items (non-blocking, W5B notes)

1. **MINOR-4 — engine lint depth:** the shared engine validates evidence/schema/candidate structure but not the full design §7 order 6–10 (backlink/staleness/contradiction/health). W1 pre-validates; W3 content is assembler-generated (UAT B lint+health clean). **W5B must not assume the engine validates candidates.**
2. **MINOR-5 — SET_METADATA allowlist edge:** a hand-crafted `(MERGE_SOURCES, SET_METADATA{created})` patch auto-applies (MERGE branch doesn't re-check sibling keys; `_set_metadata` has no internal allowlist). Unreachable from both adapters; add the allowlist inside `_set_metadata` as defense-in-depth before W5B exposes arbitrary patch ingestion.
3. **MINOR-6 — suggestion JSON completeness (§5.4):** persisted suggestions are deterministic but not a full serialized `WikiPatch` + outcome record, and are review-only (cannot be re-applied). Deferred to W5B explicitly.
4. **MINOR-7 — Error Book category** hardcoded to `evidence_validation` for all failure stages; policy-rejected (DELETE) not logged. Non-blocking.
5. **MINOR-8 — `_resolve_target`** falls back to `root.parent/target_path` when the direct parent doesn't exist (no containment assert). Model + adapters prevent reachability today; assert containment when the engine becomes a public surface.
6. **Buffer ⊋ DB drift** observed in UAT B (875 buffer files vs 234 DB∩buffer hashes) — production is safe (DB-first filter); future reconciliation task.
7. **Closeout:** local `main` is 1 commit ahead of `origin/main` (`507396fd`, docs-only UAT report). Completion contract item 11 requires the verified commits be pushed without force — this push appears pending.
8. **`kb/wiki/_debug/`** (W1 prompt/opus dumps) is not gitignored (NIT-10) — harmless but noisy; ignore or clean in a future pass.

---

## 11. Verification artifacts

- This report: `docs/superpowers/reviews/w5a-independent-verification.md`
- Prior reviews read: `docs/superpowers/reviews/w5a-adversarial-review.md` (13/15 PASS + BLOCKER + 2 MAJOR @ 3bfe098f), `docs/superpowers/reviews/w5a-production-uat.md` (A/B/C/D/E PASS @ c8ec5227)
- No repo files modified by this verification; worktree clean before and after.
