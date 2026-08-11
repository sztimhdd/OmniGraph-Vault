# OmniGraph Wiki v2 W5A Unified Patch Compiler Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge W1 batch Wiki generation and W3 incremental Wiki updates onto one typed, deterministic, concurrency-safe patch/validation/apply core without adding semantic auto-acceptance, runtime navigation, or new network work to the ingest hook.

**Architecture:** Preserve W1 and W3 evidence acquisition, but normalize both into `EvidencePack` and `WikiPatch`. A pure patch assembler renders candidate Markdown, a deterministic validator checks evidence/schema/lint/health constraints, and one apply engine enforces optimistic concurrency, per-page locking, policy, atomic writes, and structured JSON suggestions. Existing-page substantive body mutations remain suggestion-only in W5A; new pages use the canonical `SCHEMA.md` typed-sources + GFM-footnote format.

**Tech Stack:** Python 3, stdlib dataclasses/json/hashlib/fcntl/tempfile/pathlib, python-frontmatter, existing `kb.wiki_lint`, existing `scripts/wiki_health.py`, pytest, SQLite Error Book, systemd/Aliyun production UAT.

## Global Constraints

- Authoritative design contract: `docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5a-patch-compiler-design.md` at commit `8f4c809080b80c76c37784325ee9302a8daa6ed8`.
- W5-0 is a fixed prerequisite and must not be weakened or reworked.
- Markdown/frontmatter remains Wiki source of truth; `_suggestions/` contains workflow artifacts only.
- No runtime graph, `wiki_search`/`wiki_read`, N-hop traversal, retrieval fusion, query-feedback acceptance, concepts/domains UI, answer caching, new paid provider, or new production service.
- No bulk rewrite or citation migration of existing Wiki pages.
- Existing-page substantive body changes are suggestion-only in W5A; no automatic paragraph/section/image/cross-reference deletion or replacement.
- New pages created by the W5A compiler must use canonical typed `sources[]` + GFM `[^N]` citations from `kb/wiki/SCHEMA.md`.
- Existing legacy pages remain lint-supported and preserve rendering style by default.
- W3 ingest hook gains no Tavily/Databricks/LLM/network work and must remain bounded/failure-isolated under the existing 120s outer timeout.
- Article evidence uses canonical lowercase MD5(url)[:10] identity and must resolve before apply.
- Git is the durable audit/rollback source; no uncommitted production-only final state.
- No force push; preserve unrelated/concurrent work; use an isolated worktree during execution if the main worktree is dirty or concurrent work is detected.

---

## File Map

Create:

- `kb/wiki_compiler/__init__.py` — public compiler exports only.
- `kb/wiki_compiler/models.py` — typed models, enum validation, serialization, stable IDs/digests.
- `kb/wiki_compiler/patch.py` — pure candidate-page assembly, canonical new-page rendering, legacy/canonical source merge, H2 section parsing.
- `kb/wiki_compiler/validate.py` — deterministic patch/evidence/candidate validation using existing Wiki lint/health primitives.
- `kb/wiki_compiler/apply.py` — deterministic policy, page lock, optimistic concurrency, structured suggestion persistence, atomic apply, Error Book logging.
- `kb/wiki_compiler/adapters/__init__.py` — adapter package.
- `kb/wiki_compiler/adapters/w1.py` — W1 source-catalog/candidate → normalized EvidencePack/WikiPatch.
- `kb/wiki_compiler/adapters/w3.py` — article hashes/entity buffers → normalized EvidencePack/WikiPatch.
- `tests/unit/test_wiki_compiler_models.py`
- `tests/unit/test_wiki_compiler_patch.py`
- `tests/unit/test_wiki_compiler_apply.py`
- `tests/unit/test_wiki_compiler_w1_adapter.py`
- `tests/unit/test_wiki_compiler_w3_adapter.py`

Modify:

- `scripts/wiki_generate_pages.py` — keep retrieval/Opus acquisition, switch authoritative write path to W1 adapter + shared compiler; update prompt/validation to canonical new-page schema.
- `kb/wiki_update.py` — preserve compatibility entry points while delegating W3 proposal/apply to shared compiler.
- `kb/wiki/SCHEMA.md` — document W5A compiler behavior and remove stale ambiguity about canonical generation.
- `tests/unit/test_wiki_w5_0.py` — keep W5-0 behavior anchors; update only assertions whose public representation intentionally changes from Markdown suggestion to structured JSON.
- `tests/unit/test_error_book.py` only if the compiler needs a backward-compatible payload assertion; do not redesign Error Book schema in W5A.
- `.planning/ISSUES.md` — orchestration closeout only, after verified implementation.

Do not modify retrieval runtime, MCP tool surfaces, graph storage, frontend, or LightRAG/Qdrant schema.

---

### Task 1: Typed compiler models and stable identity

**Files:**
- Create: `kb/wiki_compiler/__init__.py`
- Create: `kb/wiki_compiler/models.py`
- Create: `tests/unit/test_wiki_compiler_models.py`

**Interfaces:**
- Produces:
  - `EvidenceRef(evidence_id: str, type: str, ref: str | None, title: str, provenance: str, metadata: dict[str, object])`
  - `EvidencePack(pack_id: str, subject_slug: str, subject_title: str, trigger: str, article_hashes: tuple[str, ...], evidence: tuple[EvidenceRef, ...], context_blocks: tuple[str, ...], existing_page_path: str | None, existing_page_digest: str | None, created_at: str, compiler_version: str)`
  - `PatchOperation(op: str, section: str | None = None, content: str | None = None, metadata: dict[str, object] | None = None)`
  - `WikiPatch(patch_schema_version: int, patch_id: str, target_slug: str, target_path: str, target_kind: str, base_digest: str | None, trigger: str, evidence_pack_id: str, operations: tuple[PatchOperation, ...], evidence: tuple[EvidenceRef, ...], policy_hint: str, reason: str, created_at: str, compiler_version: str)`
  - `page_digest(text: str) -> str` using SHA-256 over UTF-8 bytes.
  - `WikiPatch.to_dict() / from_dict()` and JSON round-trip.
- Consumes: no network, no repository state except path validation rules.

- [ ] **Step 1: Write failing model round-trip and validation tests**

Add tests that assert:

```python
from kb.wiki_compiler.models import EvidenceRef, PatchOperation, WikiPatch


def test_wikipatch_json_round_trip():
    src = EvidenceRef("a1", "article", "0123456789", "Article", "w3", {})
    patch = WikiPatch(
        patch_schema_version=1,
        patch_id="patch-abc",
        target_slug="openclaw",
        target_path="entities/openclaw.md",
        target_kind="entity",
        base_digest="deadbeef",
        trigger="w3_incremental",
        evidence_pack_id="pack-abc",
        operations=(PatchOperation("MERGE_SOURCES"),),
        evidence=(src,),
        policy_hint="suggestion_only",
        reason="new source evidence",
        created_at="2026-08-11T00:00:00+00:00",
        compiler_version="w5a-v1",
    )
    assert WikiPatch.from_dict(patch.to_dict()) == patch
```

Also assert rejection of:

- `patch_schema_version != 1`;
- target path escaping `kb/wiki` semantics (`../`, absolute paths, non-`.md` targets);
- target kind outside `entity|concept|comparison|query`;
- operation outside `CREATE_PAGE|UPSERT_SECTION|MERGE_SOURCES|SET_METADATA`;
- article evidence not matching `[a-f0-9]{10}`;
- `CREATE_PAGE` mixed with a non-null `base_digest`;
- update patch with null `base_digest`.

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_models.py -v
```

Expected: import/module failure.

- [ ] **Step 3: Implement immutable dataclasses and explicit validation**

Use frozen dataclasses. Validate in `__post_init__`; do not depend on Pydantic or add a dependency. Generate helper IDs only when adapters ask for them; constructors used in tests must remain deterministic.

Required helpers:

```python
def page_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_patch_id(*, target_slug: str, evidence_pack_id: str, operations: tuple[PatchOperation, ...]) -> str:
    # canonical-json SHA256[:16], prefixed `wpatch-`
```

Canonical JSON must use sorted keys and compact separators so the same logical proposal gets the same deterministic ID.

- [ ] **Step 4: Run model tests GREEN**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_models.py -v
```

- [ ] **Step 5: Commit Task 1**

```bash
git add kb/wiki_compiler/__init__.py kb/wiki_compiler/models.py tests/unit/test_wiki_compiler_models.py
git commit -m "feat(wiki-v2-w5a): add typed patch compiler models"
```

---

### Task 2: Pure patch assembler and canonical renderer

**Files:**
- Create: `kb/wiki_compiler/patch.py`
- Create: `tests/unit/test_wiki_compiler_patch.py`

**Interfaces:**
- Consumes: `WikiPatch`, optional existing Markdown text.
- Produces:
  - `detect_page_style(markdown: str) -> Literal["canonical", "legacy"]`
  - `parse_h2_sections(markdown_body: str) -> list[tuple[str, str]]`
  - `assemble_candidate(existing_text: str | None, patch: WikiPatch) -> str`
  - `render_canonical_new_page(patch: WikiPatch) -> str`
- No filesystem writes, DB access, network, Error Book, or locking.

- [ ] **Step 1: Write failing canonical-create tests**

Create a `CREATE_PAGE` patch with two article sources and one web source. Assert output:

```yaml
sources:
  - id: 1
    type: article
    ref: 0123456789
    title: Article A
  - id: 2
    type: article
    ref: abcdef0123
    title: Article B
  - id: 3
    type: web
    ref: https://example.com/source
    title: Web Source
```

and a body that uses `[^1]`, `[^2]`, `[^3]` only when supplied by the patch body. Assert no `^[article:...]` is generated for new pages.

`CREATE_PAGE` operation contract in W5A:

```python
PatchOperation(
    op="CREATE_PAGE",
    content="# Title\n\nObserved evidence paragraph [^1][^2].\n",
    metadata={
        "title": "Title",
        "created": "2026-08-11",
        "last_updated": "2026-08-11",
        "confidence_level": "low",
    },
)
```

The renderer owns `sources`; callers must not inject raw source YAML.

- [ ] **Step 2: Write failing existing-page preservation tests**

Fixture a legacy page containing:

- legacy string `sources`;
- three H2 sections;
- an image in section A;
- a `[[cross-link]]` in section C;
- fixed `created` date.

Apply only `MERGE_SOURCES` + `SET_METADATA(last_updated=...)` and assert body bytes are unchanged and `created` is unchanged.

Create a second patch with `UPSERT_SECTION(section="Architecture", content="...")` and assert only that section changes in the candidate; unrelated section/image/cross-link text remains unchanged. This test proves patch assembly capability, not auto-apply policy.

- [ ] **Step 3: Run patch tests RED**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_patch.py -v
```

- [ ] **Step 4: Implement section parser and renderer**

Requirements:

- Parse YAML with `frontmatter`, but preserve existing body text for metadata/source-only changes.
- H2 recognition is line-based `^##\s+(.+?)\s*$`; do not treat fenced-code headings as sections.
- `MERGE_SOURCES` is union/dedup and never subtractive.
- Canonical sources dedup key: `(type, ref, title)`; legacy source strings dedup by exact normalized string.
- Legacy existing page + article-only evidence: merge as legacy `article:<hash>` strings.
- Legacy existing page + new web/builtin evidence: assembly may produce a candidate for review, but validator/policy must prevent auto-apply; do not silently drop the evidence.
- `SET_METADATA` allowlist in W5A: `last_updated`, `confidence_level`. Reject `created`, `title`, `sources`, and arbitrary fields through this operation.
- `UPSERT_SECTION` may replace only the named H2 section in a candidate. It must not be able to target the H1/frontmatter.

- [ ] **Step 5: Run patch tests GREEN**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_patch.py -v
```

- [ ] **Step 6: Commit Task 2**

```bash
git add kb/wiki_compiler/patch.py tests/unit/test_wiki_compiler_patch.py
git commit -m "feat(wiki-v2-w5a): add pure patch assembler"
```

---

### Task 3: Deterministic validation, policy, optimistic concurrency, and apply

**Files:**
- Create: `kb/wiki_compiler/validate.py`
- Create: `kb/wiki_compiler/apply.py`
- Create: `tests/unit/test_wiki_compiler_apply.py`
- Modify only if needed for payload compatibility: `kb/error_book.py`

**Interfaces:**
- Consumes: `WikiPatch`, article-hash resolver set/callable, `wiki_root: Path`.
- Produces:
  - `ValidationIssue(code: str, message: str, blocking: bool)`
  - `validate_patch(patch, *, wiki_root, known_article_hashes) -> tuple[ValidationIssue, ...]`
  - `validate_candidate(candidate_text, patch, *, wiki_root, known_article_hashes) -> tuple[ValidationIssue, ...]`
  - `decide_policy(patch, candidate_text, existing_text) -> Literal["auto_apply", "suggestion_only", "reject"]`
  - `ApplyResult(status: str, patch_id: str, target_path: str, suggestion_path: str | None, issues: tuple[str, ...])`
  - `apply_patch_atomic(patch, *, wiki_root, known_article_hashes) -> ApplyResult`

- [ ] **Step 1: Write failing policy tests**

Required decisions:

```text
W1 CREATE_PAGE + valid candidate                    -> auto_apply
W3 CREATE_PAGE + valid evidence/candidate           -> auto_apply
existing page + UPSERT_SECTION                      -> suggestion_only
existing legacy page + new web/builtin evidence     -> suggestion_only
existing page + MERGE_SOURCES(article only)         -> auto_apply only if body unchanged
existing page + SET_METADATA(last_updated/confidence)-> auto_apply only if body unchanged
invalid evidence / lint ERROR                       -> reject
stale base digest                                   -> conflict, never overwrite
```

- [ ] **Step 2: Write failing optimistic-concurrency tests**

Test sequence:

1. Read existing text and compute `base_digest`.
2. Build patch.
3. Mutate target before apply.
4. Assert `ApplyResult.status == "conflict"` and target content stays at the externally-mutated version.

Also create two concurrent workers with the same base digest; at most one may return `applied`. The other must return `conflict`/`suggested`, never overwrite the winner.

- [ ] **Step 3: Write failing structured-suggestion tests**

A substantive update must create:

```text
kb/wiki/_suggestions/<slug>-<patch-id>.json
```

with top-level fields:

```json
{
  "patch": {"patch_schema_version": 1},
  "decision": "suggestion_only",
  "validation": [],
  "created_at": "..."
}
```

Writing the same deterministic patch twice must not create timestamp duplicates; it must address the same `<slug>-<patch-id>.json` path atomically.

- [ ] **Step 4: Run tests RED**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_apply.py -v
```

- [ ] **Step 5: Implement validation**

Use existing primitives rather than reimplementing them:

- `kb.wiki_lint.lint_citation_integrity`
- `kb.wiki_lint.lint_backlink_validity`
- `kb.wiki_lint.lint_contradicts_existing`
- `kb.wiki_lint.lint_staleness`

For candidate-page lint, write only to a temporary file under the target directory or a temporary Wiki fixture, then remove it. Do not let lint temp files appear in `index.md` or `_suggestions/`.

Candidate canonical schema checks must explicitly verify:

- required frontmatter fields;
- typed source IDs unique positive integers;
- every `[^N]` resolves;
- article refs resolve in `known_article_hashes`;
- no unknown source type;
- target slug/path is consistent.

- [ ] **Step 6: Implement per-page lock and atomic apply**

Use stdlib `fcntl.flock` on a deterministic lock file under:

```text
kb/wiki/.locks/<sha256(relative-target)[:16]>.lock
```

Lock files are runtime artifacts and must not be Git-tracked; add the directory to `.gitignore` if necessary.

Critical section:

```text
LOCK_EX
-> reread target
-> recheck existence/base_digest
-> assemble candidate
-> validate candidate
-> decide policy
-> tempfile in target directory
-> os.replace
-> unlock
```

No waiting loop beyond the kernel lock is required; do not create a lock service.

- [ ] **Step 7: Integrate Error Book for true compiler integrity rejection**

On `reject` due to validation integrity, call existing `log_lint_failure()` with compatible keys and include extra fields in payload:

```python
{
    "lint_name": f"wiki_compiler:{issue.code}",
    "page_path": str(target),
    "failures": [issue.message],
    "suggestion_excerpt": patch.patch_id,
    "patch_id": patch.patch_id,
    "trigger": patch.trigger,
    "compiler_version": patch.compiler_version,
}
```

Do **not** log normal `suggestion_only` policy outcomes as errors. Do not log digest conflicts as corrupted-page errors.

- [ ] **Step 8: Run Task 3 tests GREEN plus W5-0 regressions**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_apply.py \
  tests/unit/test_error_book.py \
  tests/unit/test_wiki_w5_0.py -v
```

- [ ] **Step 9: Commit Task 3**

```bash
git add kb/wiki_compiler/validate.py kb/wiki_compiler/apply.py tests/unit/test_wiki_compiler_apply.py kb/error_book.py .gitignore
git commit -m "feat(wiki-v2-w5a): add validated atomic patch apply"
```

Only stage files actually changed.

---

### Task 4: W3 adapter and production-hook convergence

**Files:**
- Create: `kb/wiki_compiler/adapters/__init__.py`
- Create: `kb/wiki_compiler/adapters/w3.py`
- Create: `tests/unit/test_wiki_compiler_w3_adapter.py`
- Modify: `kb/wiki_update.py`
- Modify behavior-anchor assertions as needed: `tests/unit/test_wiki_w5_0.py`
- Read-only unless a call signature truly requires it: `batch_ingest_from_spider.py`

**Interfaces:**
- Consumes: article hashes, DB connection, entity buffer dirs, Wiki root.
- Produces:
  - `build_w3_evidence_packs(article_hashes, *, db_conn, wiki_root, entity_buffer_dirs, min_frequency=2) -> list[EvidencePack]`
  - `propose_w3_patch(pack: EvidencePack, *, wiki_root) -> WikiPatch`
  - compatibility `generate_wiki_suggestions(...) -> list[dict]` may remain, but each dict must contain/derive from a serialized `WikiPatch`, not an opaque authoritative full-page replacement.
  - compatibility `apply_suggestion_atomic(...)` delegates to shared `apply_patch_atomic`.

- [ ] **Step 1: Write failing W3 evidence tests**

Use a temp SQLite `articles(content_hash)` and entity-buffer fixtures. Assert:

- unknown article hashes are ignored;
- canonical buffer search order behavior remains intact;
- entity frequency threshold still uses distinct article hashes;
- existing page path/digest is captured in the `EvidencePack`;
- article `EvidenceRef` objects use 10-char hash identity.

- [ ] **Step 2: Write failing W3 new-page canonical patch test**

For a new entity found in two real fixture hashes, assert `propose_w3_patch` emits:

- `CREATE_PAGE`;
- `trigger="w3_incremental"`;
- `policy_hint="auto_apply"`;
- canonical low-confidence body with claims cited using GFM footnotes generated from the evidence list;
- no legacy `^[article:hash]` output.

The body can remain intentionally minimal in W5A; do not add an LLM call. Example semantics:

```markdown
# Test Entity

Observed in 2 newly ingested OmniGraph source articles.[^1][^2]
```

- [ ] **Step 3: Write failing rich-existing-page structured suggestion test**

Given a W1-rich existing page, assert W3 produces a patch that references the existing digest and that shared apply yields `suggestion_only` with JSON artifact; the original page hash/content remains unchanged.

- [ ] **Step 4: Run W3 tests RED**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_w3_adapter.py tests/unit/test_wiki_w5_0.py -v
```

- [ ] **Step 5: Implement W3 adapter and compatibility bridge**

Move only normalization/proposal responsibilities. Keep entity-buffer discovery behavior and W5-0 canonical path fix intact. Remove `_build_page()` as an authoritative update mechanism; it may remain temporarily only if a legacy compatibility test proves an external caller still requires it, and must not be called by the new W3 production path.

`batch_ingest_from_spider._wiki_update_check` must continue to receive the same high-level success/failure stats shape expected by logs/tests. If no call signature change is required, do not touch `batch_ingest_from_spider.py`.

- [ ] **Step 6: Run W3 + ingest orchestration regressions GREEN**

At minimum:

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_w3_adapter.py \
  tests/unit/test_wiki_w5_0.py \
  tests/unit/test_batch_ingest_hash.py -v
```

Then locate and run the existing test covering `_wiki_update_check`/`ingest_from_db` orchestration if its filename differs. Do not guess a test name; inspect current repository.

- [ ] **Step 7: Commit Task 4**

```bash
git add kb/wiki_compiler/adapters kb/wiki_update.py tests/unit/test_wiki_compiler_w3_adapter.py tests/unit/test_wiki_w5_0.py batch_ingest_from_spider.py
git commit -m "refactor(wiki-v2-w5a): route W3 through patch compiler"
```

Only stage `batch_ingest_from_spider.py` if actually changed.

---

### Task 5: W1 adapter, canonical generation, and no-direct-write convergence

**Files:**
- Create: `kb/wiki_compiler/adapters/w1.py`
- Create: `tests/unit/test_wiki_compiler_w1_adapter.py`
- Modify: `scripts/wiki_generate_pages.py`
- Modify: `kb/wiki/SCHEMA.md`

**Interfaces:**
- Consumes: existing W1 source catalog, validated Opus output, current target page if any.
- Produces:
  - `build_w1_evidence_pack(entity_name, catalog, *, target_path, existing_text=None, context_blocks=()) -> EvidencePack`
  - `candidate_to_w1_patch(candidate_markdown: str, pack: EvidencePack, *, wiki_root) -> WikiPatch`
  - new page → `CREATE_PAGE` patch;
  - existing page → section/source/metadata patch, `suggestion_only` when any body section differs.

- [ ] **Step 1: Write failing catalog normalization tests**

Given W1 catalog entries for article/web/builtin, assert exact `EvidenceRef` mapping and dedup. Article refs must remain 10-char hashes; web URL and builtin null-ref provenance must survive.

- [ ] **Step 2: Write failing canonical Opus-output validation test**

Update W1 expected output contract to match current `SCHEMA.md`:

- typed `sources[]` dictionaries;
- body GFM `[^N]` citations;
- all article refs must be in the trusted source catalog;
- web refs must be catalog URLs;
- builtin source may have no `ref`;
- no legacy string-only source list is emitted for new pages.

Legacy page parsing remains accepted for existing pages; this step does not bulk migrate them.

- [ ] **Step 3: Write failing existing-page diff-to-patch test**

Fixture existing page and a newly synthesized candidate with one changed H2 plus one new source. Assert `candidate_to_w1_patch` emits `UPSERT_SECTION` + `MERGE_SOURCES` + allowed metadata update, carries the original `base_digest`, and policy resolves to `suggestion_only` in W5A.

- [ ] **Step 4: Run W1 tests RED**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_w1_adapter.py -v
```

- [ ] **Step 5: Update W1 synthesis prompt and validator to canonical schema**

In `scripts/wiki_generate_pages.py`:

- keep LightRAG/Tavily/Databricks acquisition unchanged;
- change `build_opus_prompt()` from explicit legacy citation instructions to canonical typed-source/GFM instructions consistent with `SCHEMA.md`;
- update `validate_and_parse()` to validate the canonical format for newly synthesized pages;
- do not remove legacy lint support from `kb/wiki_lint.py`;
- preserve image instructions and source-grounding restrictions.

Do not change provider, model endpoint, Tavily depth, LightRAG mode, or cost gate in W5A.

- [ ] **Step 6: Replace direct W1 authoritative page write**

In `generate_one_entity()` after synthesis validation:

```text
normalized catalog -> EvidencePack
validated candidate -> WikiPatch
shared apply_patch_atomic(...)
```

Remove `_atomic_write(out_path, page_text)` as the authoritative page-apply path. Debug prompt/Opus artifacts may keep their existing debug writes.

Required result mapping:

```text
applied       -> status=ok, path=target
suggested     -> status=suggested, path=structured suggestion path
rejected      -> status=failed with validation issues
conflict      -> status=failed/conflict, never overwrite
```

`--dry-run`, cost gate, and `--skip-existing` remain compatible. Existing-page runs without `--skip-existing` must never auto-apply substantive body replacement in W5A.

- [ ] **Step 7: Update `SCHEMA.md` only for truth alignment**

Document:

- W5A new-page compiler emits canonical typed `sources[]` + GFM;
- existing legacy pages remain accepted/preserved;
- structured patch JSON is the new automatic suggestion format;
- Error Book path/lifecycle is current (remove any stale statement that all lint failures only append the old JSONL file).

Do not rewrite unrelated schema sections.

- [ ] **Step 8: Run W1 tests plus current Wiki lint/health tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_w1_adapter.py \
  tests/unit/test_wiki_compiler_models.py \
  tests/unit/test_wiki_compiler_patch.py \
  tests/unit/test_wiki_compiler_apply.py \
  tests/unit/test_wiki_compiler_w3_adapter.py \
  tests/unit/test_wiki_w5_0.py \
  tests/unit/test_error_book.py -v
```

Also run any pre-existing tests specifically importing `scripts/wiki_generate_pages.py` discovered from repository search.

- [ ] **Step 9: W1 smoke without production write**

Use existing `--dry-run` plus a temp output directory or mocked source acquisition to prove CLI compatibility. If credentials are already available and a real Opus smoke is cheap/approved by the existing cost gate, one real entity smoke may be run into a temp Wiki root, never directly over an existing production Wiki page.

- [ ] **Step 10: Commit Task 5**

```bash
git add kb/wiki_compiler/adapters/w1.py scripts/wiki_generate_pages.py kb/wiki/SCHEMA.md tests/unit/test_wiki_compiler_w1_adapter.py
git commit -m "refactor(wiki-v2-w5a): route W1 through canonical patch compiler"
```

---

### Task 6: Full regression, adversarial review, and scope audit

**Files:**
- No planned production-code creation; modify only to fix review findings within W5A scope.
- Create execution evidence under existing phase conventions, e.g. `.planning/phases/wiki-v2-w5a/VERIFICATION.md` and `SUMMARY.md` if that matches current project practice.

**Interfaces:**
- Consumes: completed Tasks 1–5.
- Produces: independently reviewable proof that W1/W3 share the compiler seam and W5-0 behavior did not regress.

- [ ] **Step 1: Run focused compiler suite**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_models.py \
  tests/unit/test_wiki_compiler_patch.py \
  tests/unit/test_wiki_compiler_apply.py \
  tests/unit/test_wiki_compiler_w1_adapter.py \
  tests/unit/test_wiki_compiler_w3_adapter.py -v
```

- [ ] **Step 2: Run all Wiki-related tests discovered from repository**

Use repository search/listing rather than a guessed subset. Record exact command, test count, passes/failures, and any pre-existing unrelated failure.

- [ ] **Step 3: Run standalone health checker on real repository Wiki**

```bash
venv/bin/python scripts/wiki_health.py
```

Record exit code and findings. Do not use `--rebuild-index` merely to make a failure disappear; diagnose first.

- [ ] **Step 4: Prove no direct authoritative W1/W3 full-page write remains**

Review call sites. Required evidence:

- W1 generated target pages route through `apply_patch_atomic`;
- W3 generated pages/suggestions route through shared compiler;
- remaining `_atomic_write` helpers are debug/index/shared apply only, not bypasses for authoritative existing-page writes;
- no caller can auto-apply `UPSERT_SECTION` in W5A.

- [ ] **Step 5: Independent adversarial diff review**

Fresh reviewer must actively try to reject for:

- accidental legacy bulk migration;
- direct-write bypass;
- W3 network/LLM work;
- auto-applied substantive existing-page body changes;
- source/citation provenance loss;
- TOCTOU/concurrency overwrite;
- `_suggestions/` timestamp duplication instead of deterministic patch ID;
- Error Book misuse for normal suggestion state;
- W6/W7/W8 scope creep.

Resolve every blocking finding and rerun affected tests.

- [ ] **Step 6: Commit review fixes atomically**

Use a precise commit message matching the finding; do not squash unrelated task history merely for aesthetics.

---

### Task 7: Production deploy and controlled W5A UAT

**Files/Systems:**
- Current authoritative Aliyun production environment discovered at execution time.
- Relevant deployed W3/compiler Python files only.
- Planning verification artifacts.
- `.planning/ISSUES.md` after successful verification.

**Interfaces:**
- Consumes: verified Git commits.
- Produces: live evidence that W3 still works through the shared compiler without degrading Wiki/ingest health.

- [ ] **Step 1: Re-discover current production truth before mutation**

Confirm current host, deploy mechanism, service/timer, repo/runtime path, Python venv, `OMNIGRAPH_BASE_DIR`, DB path, entity-buffer path, and current service health. Do not blindly reuse August 11 addresses/paths if live evidence differs.

- [ ] **Step 2: Capture rollback state**

Record current Git SHAs and make narrow backups of files to be replaced. Do not back up or copy DB/Qdrant/LightRAG corpora unnecessarily.

- [ ] **Step 3: Deploy only verified W5A runtime files**

Use the current established deploy mechanism (Git pull if healthy; surgical SCP/rsync if that remains the production convention). Preserve env/secrets. Restart only the service needed for new Python code to be loaded.

- [ ] **Step 4: Health/readiness check immediately after deploy**

Verify relevant systemd service status, KB health endpoint if applicable, and no new traceback/import error in journal.

If health regresses: rollback immediately before further diagnosis.

- [ ] **Step 5: Controlled W3 production UAT — existing rich page path**

Choose a small set of known production article hashes whose entity buffers map to existing rich Wiki pages. Invoke the current W3 check through its real production-callable function/path.

Required evidence:

```text
entity buffers discovered
-> EvidencePack/WikiPatch created
-> substantive rich-page update classified suggestion_only
-> deterministic <slug>-<patch-id>.json created
-> existing target page digest unchanged
-> no legacy timestamp Markdown overwrite artifact created by the new path
```

Do not ask the user for approval for this non-destructive UAT.

- [ ] **Step 6: Controlled CREATE_PAGE UAT in isolated Wiki root using production evidence**

Use real production DB/entity buffers but a temp Wiki root, e.g. `/tmp/omnigraph-w5a-uat/wiki`, to prove:

```text
new entity
-> canonical CREATE_PAGE
-> typed sources[]
-> GFM citations
-> health/lint pass
-> atomic apply
```

This proves creation semantics without introducing a junk production Wiki page.

- [ ] **Step 7: Concurrency UAT in temp Wiki root**

Run two same-base patches against one temp target using the production Python environment. Require one winner and one conflict/suggestion; never silent overwrite.

- [ ] **Step 8: Confirm ingest non-blocking contract**

Run or inspect a real bounded W3 invocation and confirm failure isolation remains. No new network calls may appear inside W3 compiler path. If a natural cron fires during the window, capture `W3 wiki hook` journal evidence; otherwise a controlled direct invocation is sufficient.

- [ ] **Step 9: Final health + Wiki integrity**

Run production/repo-equivalent health checker and compare selected rich-page digests before/after. Confirm service active, no new Error Book flood, no accidental mass page diff.

- [ ] **Step 10: Independent production verifier**

Fresh verifier checks the original W5A design, implementation plan, task commits, tests, and production evidence. It must explicitly answer PASS/FAIL for:

1. both W1 and W3 route through shared compiler seam;
2. new pages canonical;
3. existing substantive body updates suggestion-only;
4. optimistic concurrency proven;
5. W3 no-network/non-blocking preserved;
6. structured suggestions deterministic;
7. Wiki health and production service healthy;
8. no W6/W7/W8 scope creep.

- [ ] **Step 11: Closeout docs and issue provenance**

Create/update `.planning/phases/wiki-v2-w5a/{RESEARCH,PLAN,VERIFICATION,SUMMARY}.md` according to current project convention, referencing this superpowers plan rather than duplicating it. Update `.planning/ISSUES.md` only for genuinely resolved/new out-of-scope issues.

- [ ] **Step 12: Final integration/push**

Refresh `origin/main`. If main advanced, reconcile without history rewrite and rerun affected verification. Push verified commits without force.

Final executor report must end exactly:

```text
W5A RESULT: PASS
```

If a contract blocker prevents safe completion, restore production health and end exactly:

```text
W5A RESULT: BLOCKED
```

with the precise blocker and current production state.

---

## Completion Contract

W5A is complete only when all of the following are simultaneously true:

1. Typed `EvidenceRef`, `EvidencePack`, `WikiPatch`, operations, deterministic patch IDs, and JSON round-trip exist with behavior-anchor tests.
2. One pure patch assembler can canonical-create new pages and preserve existing-page content outside scoped operations.
3. One shared validator/policy/apply engine provides evidence validation, canonical/legacy lint compatibility, deterministic structured suggestions, atomic writes, Error Book integration for true failures, per-page locking, and optimistic digest conflict protection.
4. W3 produces normalized evidence/patches and delegates apply/suggestion to the shared compiler with no new network/LLM work and no regression of the 120s failure-isolation contract.
5. W1 preserves current source acquisition but no longer directly writes authoritative generated pages; new generation is canonical typed-source/GFM; existing substantive changes are structured suggestions.
6. No bulk existing-page citation/schema migration occurs.
7. Focused compiler tests, all Wiki-related regressions, and standalone Wiki health pass or any unrelated pre-existing failures are explicitly evidenced and excluded by independent review.
8. Production W3 controlled UAT proves structured rich-page suggestion with unchanged page digest; isolated real-evidence CREATE_PAGE UAT proves canonical output; concurrency UAT proves no lost update.
9. Relevant production service is healthy after deployment and rollback state is documented.
10. Independent final verifier reports no blocking issue against the original W5A design contract.
11. Verified commits are pushed to `origin/main` without force and closeout provenance is reconciled.
12. Final executor line is exactly `W5A RESULT: PASS`.

## Self-Review Result

- Spec coverage: all design sections are mapped to Tasks 1–7, including schema compatibility, concurrency, structured suggestions, W1/W3 adapters, Error Book, non-blocking W3, production UAT, and scope boundaries.
- Placeholder scan: no TBD/TODO/"implement later" execution placeholders remain; repository-discovery steps are explicit where exact current production/test names must be discovered rather than guessed.
- Type consistency: `EvidenceRef`, `EvidencePack`, `PatchOperation`, `WikiPatch`, `ValidationIssue`, `ApplyResult`, `assemble_candidate`, `validate_patch`, `validate_candidate`, `decide_policy`, and `apply_patch_atomic` names are consistent across tasks.
- Scope check: W5A remains one coherent subsystem — compiler mechanics/convergence. Semantic utility evaluation stays in W5B; navigation stays in W6; hybrid feedback stays in W7; UI stays in W8.
