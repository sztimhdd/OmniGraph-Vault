# W5A Wiki Compiler — Adversarial Full-Diff Review

**Reviewer:** fresh adversarial reviewer (not the implementer)
**Date:** 2026-08-11
**Branch:** `main` @ `3bfe098f` (origin/main synced; worktree clean)
**Commits reviewed (full chain `bc9fcce5..HEAD`):** `64298303`, `8150e928`, `df573e1c`, `e8bdc664`, `ec787b3e`, `cbec5264`, `f40bfa34` (the diff also carries two unrelated vision commits `ec3e7349`, `3bfe098f` — excluded from review scope; `kb/wiki/` page content itself is untouched by the whole range, see item 12).
**Method:** full read of `models.py`, `assembler.py`, `engine.py`, `adapters/w3.py`, `kb/wiki_update.py`, `scripts/wiki_generate_pages.py`, `SCHEMA.md`, design spec; AST import-closure analysis; empirical probes of pure functions (`_merge_sources`, `classify_patch`); full W5A test suite run at HEAD in an isolated `git worktree` (`101 passed`). No state-mutating tests in the repo; no files modified except this report.

---

## Summary table

| # | Attack item | Verdict | Severity |
|---|---|---|---|
| 1 | W1 zero-bypass | **PASS** (no direct entity writes; but the shared seam is broken — see BLOCKER-1) | BLOCKER (cross-ref) |
| 2 | W3 zero-bypass | **PASS** | — |
| 3 | UPSERT_SECTION never auto-applies on existing pages | **PASS** | — |
| 4 | MERGE_SOURCES never subtractive / merge safety | **FINDING** — merge never removes sources, but corrupts canonical multi-line frontmatter blocks | **MAJOR** |
| 5 | Legacy provenance preserved | **PASS** | — |
| 6 | Canonical citations are `[^N]` with matching defs | **PASS** (with two MINOR notes) | MINOR |
| 7 | TOCTOU — digest check under lock | **PASS** | — |
| 8 | Per-page lock scope + gitignore | **PASS** (one NIT: `kb/wiki/_debug/` unignored) | NIT |
| 9 | Deterministic patch IDs / filenames | **PASS** (W1 id changes with date — documented, content legitimately changes) | — |
| 10 | Validation failure ≠ suggestion outcome; Error Book split | **PASS** (one NIT: policy-rejected not logged) | NIT |
| 11 | No network/LLM in W3 path | **PASS** (AST import closure: stdlib + `kb` only) | — |
| 12 | No bulk modification of existing wiki pages | **PASS** (`git diff bc9fcce5..HEAD -- kb/wiki/` = 0 lines) | — |
| 13 | Prompt / validator / SCHEMA agreement | **FINDING** — prompt+validator+assembler agree with each other but all contradict SCHEMA.md `id` requirement and the surviving W3 lint | **MAJOR** |
| 14 | Error Book categories, no schema change | **PASS** (one MINOR: single hardcoded category for all failure stages) | MINOR |
| 15 | `_wiki_update_check` call-site compatibility | **PASS** | — |

**BLOCKER/MAJOR findings:** 1 BLOCKER (W1 seam), 2 MAJOR (merge corruption, `id` contract conflict). Minimal repairs proposed in §3 — **not implemented** (reviewer role).

---

## 1. BLOCKER — W1 → shared engine seam is dead on arrival (TypeError + result-shape/status mismatch)

**Item 1 cross-ref; Gate E (W1 convergence) fails in production.** No test catches it because every test stubs the seam with the *plan-named* API.

**Evidence A — the call cannot bind.** `scripts/wiki_generate_pages.py:941-955`:

```python
def _compiler_engine():
    try:
        from kb.wiki_compiler.apply import apply_patch_atomic  # type: ignore[import-not-found]
        return apply_patch_atomic
    except ImportError:
        from kb.wiki_compiler.engine import apply_patch  # type: ignore[import-not-found]
        return apply_patch
```

`kb/wiki_compiler/apply.py` **does not exist** (verified: `ls kb/wiki_compiler/` → `__init__.py adapters assembler.py engine.py models.py`; `import kb.wiki_compiler.apply` → `ModuleNotFoundError`). The fallback is `engine.apply_patch`, whose signature is `engine.py:241-246`:

```python
def apply_patch(
    patch: WikiPatch,
    wiki_root: Path,
    wiki_update: Optional[Callable[[dict], None]] = None,
    error_book: Optional[Callable[[dict], None]] = None,
) -> dict:
```

The seam call site `wiki_generate_pages.py:1153-1158`:

```python
apply_fn = _compiler_engine()
apply_result = apply_fn(
    patch,
    wiki_root=output_dir.parent,
    known_article_hashes=set(article_hashes),   # ← not in apply_patch signature
)
```

→ `TypeError: apply_patch() got an unexpected keyword argument 'known_article_hashes'` → caught at `:1159` → every W1 run returns `status="failed"`, `errors=["compiler apply raised: TypeError: ..."]`. **No page, no suggestion, no Error Book entry — W1 cannot write anything at HEAD.**

**Evidence B — even with the kwarg fixed, result reading is wrong.** `wiki_generate_pages.py:1170-1186`:

```python
status = getattr(apply_result, "status", "rejected")        # dict has no .status attr → always "rejected"
...
elif status == "suggested":                                  # engine emits "suggestion" (engine.py:307)
```

`engine.apply_patch` returns a plain `dict` (`engine.py:275-280`), and `getattr(dict, "status", "rejected")` returns the default `"rejected"`; the engine's suggestion status is `"suggestion"` (`engine.py:253, 307`), never `"suggested"`. So every apply would read as `failed` even after fixing Evidence A.

**Evidence C — tests hide both.** `tests/unit/test_wiki_compiler_w1_adapter.py:150-165` (fake matches the *plan's* `apply_patch_atomic(patch, *, wiki_root, known_article_hashes) -> ApplyResult` contract, returns `SimpleNamespace(status=..., ...)`), patched at `:201`, `:424`, `:480`; `tests/integration/test_wiki_generate.py:154` `monkeypatch.setattr(wgp, "_compiler_engine", lambda: fake_apply)`. The adapter test even asserts the plan vocabulary: `apply_status="suggested"` at `:511`. Full suite at HEAD in a fresh worktree: **101 passed** — green despite the dead seam.

**Minimal repair (do not implement now):** make the W1 seam speak the engine's real contract — (a) call `apply_patch(patch, wiki_root=output_dir.parent)` without `known_article_hashes` (or add a thin `kb/wiki_compiler/apply.apply_patch_atomic(patch, *, wiki_root, known_article_hashes)` adapter that wraps `engine.apply_patch` and returns a result object, and point `_compiler_engine` at it); (b) read results as dicts: `result["status"]`, map `"suggestion"`; (c) add at least one test that does **not** stub `_compiler_engine` and asserts a real page lands on `status == "ok"`.

---

## 2. MAJOR — `_merge_sources` corrupts canonical multi-line frontmatter (item 4)

**Item 4 verdict is FINDING (MAJOR).** Merging is never *subtractive* (union/dedup only — `engine.py:579-601`), so the "remove an existing source" attack fails — but the insertion-point scan breaks on canonical block-style entries, mangling the existing `sources:` list.

**Evidence — the scan stops at the first continuation line.** `engine.py:617-641`:

```python
insert_at = src_idx + 1
while insert_at < len(lines) and (
    lines[insert_at].startswith(indent + "- ")
    or (indent and lines[insert_at].startswith("  - "))
):
    insert_at += 1
```

Both clauses are identical when `indent == "  "`, and canonical continuation lines (`    ref: …`, `    title: …`) do **not** start with `"  - "`, so `insert_at` lands right after the *first* `- type:` line — mid-entry. Empirical probe (pure function, run at HEAD):

```python
out = _merge_sources(page_with_2_canonical_entries, [web EvidenceRef])
```

produced:

```yaml
sources:
  - type: article
  - type: web
    ref: "https://new.example.com"
    title: "New web"
    provenance: tavily-web
    ref: "0123456789"          # ← old entry 1's continuation absorbed into new entry
    title: "Corpus article"
    provenance: lightrag-corpus
  - type: web
    ref: "https://example.com"
    title: "Example"
    provenance: tavily-web
```

The old first entry loses `ref`/`title`/`provenance` (bare `- type: article`); the new entry inherits duplicate keys (PyYAML last-wins on reparse). Reachability:
- **Auto-apply:** `classify_patch` returns `auto_apply` for MERGE_SOURCES on any canonical existing page (`engine.py:183-190`) — reachable by any patch with a MERGE op (assembler doesn't emit standalone MERGE today, but the engine advertises this as a safe auto-apply primitive, and design §4.4 explicitly permits auto-applied source merges).
- **Suggestions:** every W3/W1 existing-page suggestion renders through `_render_candidate` → `_merge_sources` (`engine.py:489`, `527-528`), so **every structured suggestion for an existing canonical page embeds corrupted frontmatter** in `suggested_content`.

**Why tests are green:** `test_apply_patch_success_no_conflict` (`tests/unit/test_wiki_compiler_engine.py:388-425`) merges into `_EXISTING_PAGE` which has **one** source entry, and asserts only `'ref: "0123456789"' in after` — the corruption inserts that string *somewhere*, so the assertion passes.

**Minimal repair:** skip the whole sources block when scanning (advance while the line is a list item or is indented deeper than the list — i.e. stop at the next column-0 key or the closing `---`), then insert after the last entry; add a merge test with ≥2 multi-line canonical entries that re-parses the result with `frontmatter` and asserts every entry keeps its keys and the new entry is last.

---

## 3. MAJOR — canonical output omits SCHEMA.md `id`; surviving W3 lint enforces it (item 13)

**Item 13 verdict is FINDING (MAJOR).** The prompt, W1 validator, and assembler are mutually consistent — all emit/expect typed `sources[]` dicts with `type`/`ref`/`title`/`provenance` and **no `id`**. But SCHEMA.md (the contract the design says W5A must emit) requires `id`, and the surviving lint rejects id-less pages.

**Evidence A — SCHEMA.md requires `id`.** `kb/wiki/SCHEMA.md:44-47`:

```text
- `sources` — ordered list of all sources used. Each item:
  - `id` — integer ≥1, unique within the page; referenced inline as `[^id]`
```

**Evidence B — W5A output deliberately omits it.** `assembler.py:438-448` (`_render_yaml` renders only `type`/`ref`/`title`/`provenance`); `wiki_generate_pages.py:441-442`:

```python
# Omits SCHEMA.md's ``id`` field — footnote numbering is positional and
# 1-based, matching the compiler assembler's canonical rendering.
```

**Evidence C — the surviving lint requires it.** `kb/wiki_lint.py:42-66` (module untouched by W5A):

```python
source_by_id: dict[str, dict] = {}
for s in sources_list:
    if isinstance(s, dict) and "id" in s:
        source_by_id[str(s["id"])] = s
for m in FOOTNOTE_CITATION_RE.finditer(text):
    sid = m.group(1)
    src = source_by_id.get(sid)
    if src is None:
        failures.append(f"[^{sid}]: id not in frontmatter sources[]")
```

For any id-less page `source_by_id` is empty → **every `[^N]` citation fails lint**. SCHEMA.md:3 says "Lint (W3) enforces it" and design §6/Gate D say new W5A pages "MUST emit the current canonical SCHEMA.md representation". Today a W5A-generated page fails the repository's own citation lint. (No current W3 path calls `kb/wiki_lint.py` anymore — see MINOR-4 — so this is latent, but it breaks the documented contract and any future lint pass, e.g. `kb/services/wiki_inject.py`, which still imports `lint_citation_integrity`.)

**Minimal repair (choose one, then make prompt/validator/assembler/lint agree):**
1. Emit `id: N` (positional, 1-based) in `assembler._render_yaml` + `_typed_sources_yaml` + prompt template, and have the W1 validator verify it — aligns with SCHEMA.md and lint; or
2. Formally amend SCHEMA.md §1 and `kb/wiki_lint.py` to positional numbering (documented spec change).

---

## 4. MINOR findings

**MINOR-4 — shared engine does not implement design §7 validation order 6–10; W3 no longer lints before apply/suggest.**
`apply_patch` runs only `validate_evidence` (`engine.py:283`), policy, digest, and structural render checks (`WikiValidationError`). No citation-integrity, backlink, staleness, contradiction, or Wiki-health check exists in the apply path. The old W3 hook's lint gates were deleted with the rewrite (`git diff bc9fcce5..HEAD -- kb/wiki_update.py` removes `from kb.wiki_lint import (lint_backlink_validity, lint_citation_integrity, lint_contradicts_existing, lint_staleness, ...)` and the `lint_citation_integrity`/`lint_backlink_validity`/`lint_contradicts_existing`/`lint_staleness` check loop); the new path (`wiki_update.py:141-167`) applies/persists with no lint. Impact is currently bounded: W3 CREATE_PAGE content is assembler-generated (citations valid by construction) and W1 pre-validates citations itself (`validate_and_parse`). Design Gate G ("invalid evidence/schema/citation/health fails closed") is therefore only partially implemented in the *shared* core. Severity: MINOR (no current exploit path) — but W5B must not assume the engine validates candidates.

**MINOR-5 — SET_METADATA allowlist bypassed when MERGE_SOURCES is present.**
`classify_patch` (`engine.py:183-190`) returns `auto_apply` for any MERGE_SOURCES patch on a canonical page without inspecting sibling SET_METADATA keys, and `_set_metadata` (`engine.py:644-666`) rewrites **any** scalar frontmatter key it finds, with no allowlist of its own. Empirical probe at HEAD: ops `(MERGE_SOURCES, SET_METADATA{created: "1999-01-01"})` on an existing canonical page → `classify_patch` = `auto_apply`; `_set_metadata` would rewrite `created`. Violates design §5.3 ("SET_METADATA … must preserve `created`") and the engine's own docstring ("any critical key -> suggestion_only"). Not reachable from the assembler (only emits `last_updated`/`confidence_level`). Repair: in the MERGE branch, also require SET_METADATA keys ⊆ `{last_updated, confidence_level}` before auto-apply, and add the allowlist inside `_set_metadata` as defense in depth.

**MINOR-6 — suggestion JSON is not the design's "serialized WikiPatch plus outcome" (§5.4), and persisted suggestions are not re-appliable.**
`_write_suggestion` payload (`engine.py:482-493`) contains `patch_id, target_slug, policy_hint, reason, operations, evidence, suggested_content` — missing `patch_schema_version, target_path, target_kind, base_digest, trigger, evidence_pack_id, created_at, compiler_version`, and no validation/policy outcome record. A consumer cannot reconstruct the `WikiPatch` (no `target_path` at all). Additionally, `apply_suggestion_atomic` on a persisted JSON hits the legacy-rebuild branch and raises `KeyError("page_path")` (`wiki_update.py:153-155`) → rejected + Error Book — i.e. persisted suggestions are never re-appliable. Repair: store `patch.to_dict()` plus the outcome dict in the JSON.

**MINOR-7 — Error Book category granularity (item 14).**
`_report_error_book` (`engine.py:803-836`) hardcodes `lint_name="wiki_compiler:evidence_validation"` for **all** failures — evidence, render (`engine.py:358`), and disk I/O (`engine.py:321-322`) — so render/IO failures are mislabeled as evidence validation. Also, the policy-rejected (DELETE_PAGE) path (`engine.py:292-297`) returns without any Error Book write, contradicting the engine docstring ("rejected … logged to the Error Book"). No schema change: `kb/error_book.py` is untouched in the W5A diff, and the payload keys (`lint_name`, `page_path`, `failures`, `suggestion_excerpt`, `ts`) match `log_lint_failure` (`kb/error_book.py:101-128`). Repair: derive the category from the failure stage; log policy rejections.

**MINOR-8 — `_resolve_target` lacks containment.**
`engine.py:794-800` falls back to `root.parent / target_path` when the direct path's parent doesn't exist, so a malformed patch (e.g. `target_path="kb/other/x.md"` with `wiki_root=kb/wiki`) resolves outside the wiki dir. Model checks ban `..` and absolute paths (`models.py:216-223`) and the assembler/adapters only generate `kb/wiki/<kind>/<slug>.md` / `entities/<slug>.md`, so no production path hits this — but the engine is the shared authoritative apply path and should assert containment (resolved target under the wiki dir).

**MINOR-9 — W1 citation-order not verified (item 6).**
The W1 validator checks `[^N]` numbers are in range and refs ⊆ catalog (`wiki_generate_pages.py:847-868`) but never verifies that frontmatter position N equals catalog position N, nor that `[^N]:` definition content matches `sources[N]` — a reordering Opus could produce a page whose footnote numbers and definitions disagree with the typed list. The prompt instructs order preservation (`:557-559`); enforcement is absent. Also a NIT edge: a zero-article, `confidence_level: low` page with plain `[N]` citations and no defs passes (the no-citation check is skipped at `:855-859`).

**NIT-10 — `kb/wiki/_debug/` not gitignored.** W1 writes `kb/wiki/_debug/<slug>-opus.md` and `<slug>-prompt.txt` (`wiki_generate_pages.py:1063-1065, 1081`); `.gitignore:119-120` covers only `.locks/`, `_suggestions/*.json`, `error_book.db`.

**NIT-11 — W1 retains `_atomic_write` for `index.md`.** `wiki_generate_pages.py:1235` writes `kb/wiki/index.md` directly. Not a `<kind>/<slug>` target page (allowed by the item-1 carve-out), but the helper remains a footgun for future edits.

---

## Per-item verdicts with evidence (the 15 checklist items)

1. **W1 zero-bypass — PASS (structurally) / BLOCKER (seam).** All entity-page writes flow exclusively through the seam `apply_fn(patch, wiki_root=…)` (`wiki_generate_pages.py:1153-1158`); remaining direct writes are non-target artifacts: `_atomic_write` only for `kb/wiki/index.md` (`:1235`), `_debug/*` (`:1065,1081`), `log.md` append (`:1191`). No `open(...,'w')`/`Path.write_text`/`os.replace` targets `entities/`. The seam itself is broken — see BLOCKER-1.
2. **W3 zero-bypass — PASS.** `grep _atomic_write|_build_page|write_text|os.replace kb/wiki_update.py` → only docstring mentions; legacy `_atomic_write`, `_build_page`, `_page_is_w1_rich` deleted (diff confirms removal). Sole write path: `_apply_suggestion_engine` → `engine.apply_patch` (`wiki_update.py:167`); only production caller `batch_ingest_from_spider.py:1592-1597` uses the preserved `generate_wiki_suggestions`/`apply_suggestion_atomic` surface.
3. **UPSERT_SECTION auto-apply — PASS.** `classify_patch` returns `suggestion_only` unconditionally when any op is `UPSERT_SECTION` (`engine.py:178-181`); CREATE_PAGE+UPSERT mixtures classify by CREATE but `_render_candidate` uses only `ops[0]` and the assembler never emits the mix; an existing-page UPSERT can never auto-apply. The SET_METADATA carve-out is narrow: `auto_apply` only when ops are all SET_METADATA and keys ⊆ `{last_updated}` (`engine.py:192-198`).
4. **MERGE_SOURCES — FINDING (MAJOR).** Never subtractive (dedup union, `engine.py:579-601`; legacy web/builtin guarded to suggestion_only at `:186-189` and defensively no-op at `:613-616`) — but insertion corrupts canonical blocks (MAJOR-2).
5. **Legacy provenance — PASS.** Legacy pages detected (`engine.py:225-230`); web/builtin evidence on legacy → suggestion_only (`:186-189`); article-only merges append `- article:<hex>` strings preserving legacy style (`:627-629`); existing entries never rewritten; legacy string ↔ evidence dedup keys align (`("article", hex)`).
6. **Citation validity — PASS (MINOR-9).** Canonical output is `[^N]` (caret) with `[^N]:` definitions in `## References` (`assembler.py:203-241`); W1 prompt mandates caret form and forbids the legacy literal (`wiki_generate_pages.py:548-564`); the validator regex is `\[\^(\d+)\](?!:)` (`:77`) so plain `[N]` cannot pass when articles exist (`:855-857`); frontmatter order = catalog order = footnote positions in assembler output. See MINOR-9 for the W1 positional-order gap.
7. **TOCTOU — PASS.** In `apply_patch` the lock is acquired **before** the read/digest/write sequence and released in `finally`: lock `engine.py:313`, read `:317-319`, digest compare `:344-352`, `os.replace` `:362`, release `:364-365`. A stale-base patch can never overwrite a newer page (mismatch → `conflict`, `:345-352`; create-vs-existing → `conflict`, `:328-335`). `classify_patch` reads state pre-lock but only shapes policy, not write safety.
8. **Lock scope + gitignore — PASS (NIT-10).** Per-page lock name `<slug>.md.lock` under `kb/wiki/.locks/` (`engine.py:380-382, 312`); `.gitignore:119-120` adds `kb/wiki/.locks/` and `kb/wiki/_suggestions/*.json`; `kb/wiki/error_book.db` already ignored (`:116`); `git status --short` clean; `git ls-files kb/wiki/` shows no lock/suggestion/DB artifacts (only `_suggestions/.gitkeep`).
9. **Deterministic IDs — PASS.** `stable_patch_id` hashes slug+pack_id+operations with sorted canonical JSON (`models.py:40-58`) — no timestamp/random; suggestion filename `<slug>-<patch_id>.json` (`engine.py:491`). W3 `pack_id="w3-<slug>-<hashes>"` deterministic (`w3.py:133`). W1 `pack_id="w1-<slug>-<today>"` (`wiki_generate_pages.py:1130`) is stable within a day and legitimately changes with `last_updated` (documented in `wiki_update.py:56-61`).
10. **Validation vs suggestion — PASS (NIT).** Evidence failures → `_report_error_book` + `rejected` (`engine.py:283-288`); `suggestion_only` → JSON persisted, no Error Book (`:299-308`); `conflict` → no Error Book (`:330-352`); only suggestion-render WikiValidationError also logs (`:302-306`). Matches design §11. NIT: policy-rejected not logged; category hardcoded (MINOR-7).
11. **No network in W3 — PASS.** AST import closure of `wiki_update.py`, `adapters/w3.py`, `engine.py`, `assembler.py`, `models.py` = stdlib (`fcntl, json, os, re, tempfile, time, dataclasses, datetime, pathlib, typing, hashlib`) + internal `kb` only — no `requests/httpx/aiohttp/openai/genai/databricks/tavily/subprocess` anywhere in the closure. W1 keeps its own acquisition (`requests` for Tavily/Opus, LightRAG) — permitted by design §8.
12. **No bulk modification — PASS.** `git diff bc9fcce5..HEAD -- kb/wiki/` = 0 lines; `git ls-files` shows no page rewrites.
13. **Prompt/validator/SCHEMA — FINDING (MAJOR).** Prompt (`wiki_generate_pages.py:523-588`) ↔ validator (`:797-879`) ↔ assembler are consistent (typed `type/ref/title/provenance`, `[^N]`, `## References`, no `id`); both contradict SCHEMA.md §1 (`id` required) and `kb/wiki_lint.py:42-66` (enforces `id`) — MAJOR-3.
14. **Error Book — PASS (MINOR-7).** Uses existing `kb.error_book.log_lint_failure` (`engine.py:839-842`); payload keys match the API (`lint_name, page_path, failures, suggestion_excerpt, patch_id, trigger, compiler_version, ts`); `kb/error_book.py` unchanged in the diff → no schema change; dedup/lifecycle intact.
15. **`batch_ingest_from_spider` compat — PASS.** `_wiki_update_check` (`batch_ingest_from_spider.py:1579-1609`) calls `generate_wiki_suggestions(article_hashes, wiki_root, db_conn)` → list, and `apply_suggestion_atomic(s, db_conn, wiki_root=wiki_root)` → bool — both signatures preserved (`wiki_update.py:94-100, 170-180`); whole hook wrapped in try/except → exceptions swallowed; lock TimeoutError (5 s) would surface through `_apply_suggestion_engine` but is caught by the hook's `except Exception` and the 120 s outer `asyncio.wait_for` — bounded, non-blocking, failure-isolated.

---

## Gate mapping

| Gate | Status | Note |
|---|---|---|
| A — shared typed contract | PASS | models used by both adapters; W1 seam broken (BLOCKER-1) prevents actual use in production |
| B — operation-based, no blind replace | PASS | no REPLACE_PAGE; UPDATE → scoped ops; substantive existing-page mutations suggestion-only |
| C — concurrency-safe atomic apply | PASS | lock/digest/atomic replace verified (item 7) |
| D — canonical new-page schema | **FAIL** | id-less output contradicts SCHEMA.md + lint (MAJOR-3); `[^N]` format itself correct |
| E — W1 convergence | **FAIL** | seam TypeError → W1 cannot write (BLOCKER-1) |
| F — W3 convergence | PASS | structured patches/suggestions, non-blocking, no network, no placeholder overwrite |
| G — deterministic validation + Error Book | PASS (partial) | evidence/candidate-structure fail closed; design §7 order 6–10 not in shared engine (MINOR-4) |
| H — regression + UAT | PASS (tests) / **FAIL (UAT)** | 101/101 tests green; Mode A production UAT required by design §14 not evidenced in this range |
| I — independent verification | this review | scope creep check: vision commits (`ec3e7349`, `3bfe098f`) ride in the same range but are not W5A files; W5A diff touches only compiler/wiki files, tests, `.gitignore`, `skills/omnigraph_ingest/SKILL.md`, `.env.*` — no W5B/W6+ features implemented |

---

## Bottom line

The W3 side of W5A is genuinely converged and safe (items 2, 3, 5, 7, 8, 10, 11, 15 pass with hard evidence). The W1 side is converged **on paper only**: the production seam throws a TypeError on every call and the status vocabulary doesn't match — no W1 page has been writable since `e8bdc664`, and the green suite is an artifact of stubbing. Two further defects would bite W5B: `_merge_sources` mangles canonical frontmatter (already visible in every existing-page suggestion JSON), and the emitted "canonical" pages contradict SCHEMA.md/`kb/wiki_lint.py` on the `id` field. Recommend: fix BLOCKER-1 + MAJOR-2 + MAJOR-3, add an unstubbed W1 seam test and a multi-entry merge test, then re-run Gate D/E/H and the design §14 production UAT.
