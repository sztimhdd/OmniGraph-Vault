# OmniGraph Wiki v2 — W5A Unified Patch Compiler Core

**Date:** 2026-08-11  
**Status:** AUTHORITATIVE DESIGN CONTRACT — implementation not started  
**Depends on:** W5-0 `W5-0 CLOSURE RESULT: PASS` at/through `3f0680cd`  
**Next phase after W5A:** W5B Safe Autonomous Wiki Evolution  

---

## 1. Purpose

W5-0 made the existing Wiki machinery trustworthy enough to build on:

- W3 ingest hook is live and production-proven;
- canonical article identity is 10-char MD5;
- production entity-buffer path is resolved correctly;
- rich W1 pages are protected from W3 placeholder overwrite;
- Wiki health, deterministic index rebuild, Error Book lifecycle, and a rerunnable retrieval baseline exist.

W5A now solves the next architectural problem: **W1 batch generation and W3 incremental updates still create Wiki content through separate compiler paths with separate assumptions.**

Current split:

```text
W1 batch
scripts/wiki_generate_pages.py
  -> LightRAG + Tavily + builtin knowledge
  -> Opus full-page synthesis
  -> W1-specific validation
  -> direct atomic page write

W3 incremental
batch_ingest_from_spider.py
  -> kb/wiki_update.py
  -> entity buffers + article hashes
  -> placeholder full-page generation
  -> W3-specific lint
  -> direct page write OR _suggestions/ for rich pages
```

This is not yet a compiler architecture. It is two generators that happen to target the same directory.

**W5A goal:** establish one shared, typed, deterministic seam:

```text
EvidencePack
    -> Patch Proposal
    -> Patch Validation
    -> Candidate Page Assembly
    -> Health/Lint Validation
    -> Policy Decision
    -> Atomic Apply OR Structured Suggestion
```

W5A is deliberately **not** the semantic/evaluation wave. It builds the safe compiler core that W5B will later make autonomous and query-feedback-driven.

---

## 2. Non-goals

W5A MUST NOT implement:

- runtime Wiki navigation graph;
- `wiki_search` / `wiki_read` MCP tools;
- automatic N-hop traversal;
- weighted Wiki/graph/vector retrieval fusion;
- query-feedback-driven patch acceptance;
- affected-query / guard-query evaluation as a production gate;
- concepts/domains aggregation;
- Wiki-first Web UI;
- answer caching into `queries/`;
- bulk conversion of all existing Wiki pages to a new citation format;
- a new paid provider or a new production service.

Those belong to W5B/W6/W7/W8.

---

## 3. Design alternatives considered

### Approach A — Rewrite W1 and W3 around a brand-new compiler

Replace both current paths immediately and make all callers use a new compiler end-to-end.

**Pros:** cleanest final architecture.  
**Cons:** high blast radius; combines source retrieval, LLM behavior, schema migration, W3 production behavior, and apply semantics in one change. Hard to diagnose and rollback. Rejected for W5A.

### Approach B — Shared Patch Core + adapters (SELECTED)

Introduce a stable internal patch model and apply engine. Adapt W1 and W3 to feed that core while preserving their existing source-acquisition behavior and W3 no-fail ingest contract.

**Pros:** real convergence at the safety-critical seam; bounded change; preserves known-good source acquisition; W5B can replace proposal quality later without changing apply semantics.  
**Cons:** W1/W3 still have different evidence-collection adapters in W5A. This is intentional.

### Approach C — Thin compatibility wrapper only

Keep both current generators intact and merely wrap their final strings in a common `apply()` call.

**Pros:** smallest patch.  
**Cons:** does not create a real compiler contract; full-page overwrite semantics remain hidden inside callers; cannot support later semantic patch evaluation cleanly. Rejected.

**Decision:** Approach B.

---

## 4. Core principles

### 4.1 Markdown/frontmatter remains Wiki source of truth

The compiler does not create a second knowledge store. Applied Wiki pages remain the source of truth. Git remains the durable audit/rollback mechanism.

Structured unapplied patch proposals under `_suggestions/` are workflow artifacts, not knowledge truth.

### 4.2 Patches, not page replacement, are the unit of change

For an existing page, the compiler MUST represent intended changes explicitly rather than silently replacing the entire Markdown document.

W5A does not expose a generic delete operation.

### 4.3 Evidence identity is independent from rendering style

Internal compiler objects use a normalized source representation. Rendering to Markdown may preserve an existing page's legacy citation style or use the canonical current schema for new pages.

### 4.4 Existing pages are preserved by default

No update may remove an existing section, source, paragraph, image, or cross-reference unless a future phase explicitly authorizes destructive semantics. W5A is additive/upsert-only for existing pages.

### 4.5 Application is optimistic-concurrency-safe

Every update patch targeting an existing page carries the base page digest seen when the patch was proposed. Apply MUST fail safely if the page changed before apply.

### 4.6 W3 remains non-blocking to ingestion

W5A MUST NOT add network LLM/Tavily/Databricks calls to the production ingest hook. W3 must remain bounded and failure-isolated. Semantic enrichment belongs to W5B or an out-of-band worker.

---

## 5. Canonical internal data model

Exact Python class names may differ, but the observable contract MUST be equivalent.

### 5.1 `EvidenceRef`

Normalized source identity:

```text
EvidenceRef
- evidence_id: stable string within the pack
- type: article | web | builtin
- ref: article hash | URL | null
- title: human-readable title
- provenance: caller/source adapter identifier
- metadata: optional non-secret structured metadata
```

Rules:

- `article.ref` MUST be canonical 10-char lowercase hex and must resolve in the article store before apply;
- `web.ref` MUST be a URL when present;
- `builtin.ref` is null;
- evidence IDs are compiler-local identifiers, not Markdown footnote numbers.

### 5.2 `EvidencePack`

The input to patch proposal:

```text
EvidencePack
- pack_id
- subject_slug
- subject_title
- trigger: w1_batch | w3_incremental | manual_test
- article_hashes[]
- evidence[]: EvidenceRef
- context_blocks[]
- existing_page_path | null
- existing_page_digest | null
- created_at
- compiler_version
```

`context_blocks` may contain LightRAG context, entity-buffer facts, or other caller-provided material. W5A does not require all callers to populate the same richness of context.

### 5.3 `WikiPatch`

Versioned machine-readable proposal:

```text
WikiPatch
- patch_schema_version: 1
- patch_id
- target_slug
- target_path
- target_kind: entity | concept | comparison | query
- base_digest | null
- trigger
- evidence_pack_id
- operations[]
- evidence[]
- policy_hint: auto_apply | suggestion_only
- reason
- created_at
- compiler_version
```

Allowed W5A operation vocabulary:

```text
CREATE_PAGE
UPSERT_SECTION
MERGE_SOURCES
SET_METADATA
```

No generic `DELETE_SECTION`, `DELETE_SOURCE`, or whole-page `REPLACE_PAGE` operation is allowed for an existing page in W5A.

`CREATE_PAGE` is valid only when the target does not exist.

`UPSERT_SECTION` targets one H2 section by normalized heading. If the heading exists, its content may be replaced only inside that section; all other sections remain byte-preserved except formatting changes strictly required by the renderer. If the heading does not exist, it is appended according to the page-section ordering policy.

`MERGE_SOURCES` is union/dedup, never subtractive.

`SET_METADATA` in W5A may change only compiler-approved fields such as `last_updated`, `confidence_level`, and fields required for schema normalization. It MUST NOT silently replace `created`.

### 5.4 Structured suggestions

New W5A suggestion source of truth:

```text
kb/wiki/_suggestions/<slug>-<patch-id>.json
```

It contains the serialized `WikiPatch` plus validation/policy outcome.

Legacy `.md` suggestions remain readable and are not bulk-migrated. New W5A code should not create a second Markdown duplicate unless existing project UX requires it.

---

## 6. Citation/schema strategy

Current repository truth is split:

- `kb/wiki/SCHEMA.md` defines GFM `[^N]` + typed `sources[]` dictionaries as canonical for newly authored pages;
- legacy `^[article:<10-char>]` remains lint-supported;
- current W1 generation still explicitly emits the legacy format.

W5A resolves this without a bulk migration.

### 6.1 New pages

All **new pages created through the W5A compiler** MUST emit the current canonical `SCHEMA.md` format:

- typed `sources[]` entries;
- GFM `[^N]` body citations;
- article/web/builtin source types supported.

### 6.2 Existing pages

Existing pages MUST NOT be mass-converted merely because W5A touches the compiler.

The page renderer must determine the existing page's citation/frontmatter style and preserve it by default during W5A updates.

A patch's internal evidence model is canonical regardless of rendered page style.

If an existing legacy page cannot safely represent a proposed non-article citation without format migration, the patch MUST become `suggestion_only` rather than silently losing provenance or converting the full page.

### 6.3 Validation

Both legacy and canonical page forms continue to lint-pass. New-page tests MUST assert canonical emission. Existing-page tests MUST assert style preservation and no unrelated content loss.

---

## 7. Shared compiler modules and boundaries

Hermes may choose exact filenames after repository review, but responsibilities MUST remain separated.

Recommended shape:

```text
kb/wiki_compiler/
  models.py       # EvidenceRef/EvidencePack/WikiPatch + serialization
  patch.py        # candidate assembly / section/source merge
  validate.py     # deterministic patch + candidate-page validation
  apply.py        # base-digest guard, policy, atomic apply/suggestion
  adapters/
    w1.py
    w3.py
```

The implementation may use fewer files if that better matches repository conventions, but one file must not become a new monolith containing source retrieval, LLM calls, patching, validation, and filesystem application together.

### 7.1 Pure patch engine

Given:

```text
existing page or null
+ WikiPatch
```

produce:

```text
candidate Markdown page
+ deterministic diagnostics
```

This layer MUST be pure with respect to network calls and production services.

### 7.2 Validator

Validation order:

1. patch schema/type validation;
2. target path/kind validation;
3. base digest / existence precondition;
4. evidence identity validation;
5. operation safety validation;
6. candidate page parse/schema validation;
7. citation integrity;
8. wikilink/backlink validity using existing project policy;
9. `wiki_health`-compatible page integrity checks;
10. contradiction/staleness checks where meaningful.

Blocking failures do not apply the patch and are recorded in the Error Book with patch ID/provenance.

### 7.3 Apply engine

Required behavior:

```text
validate
  -> acquire narrow per-page apply guard
  -> re-check base digest/existence
  -> assemble candidate
  -> validate candidate again if state changed
  -> atomic tempfile + replace
  -> release guard
```

The exact locking primitive may be chosen during implementation. Observable requirement: two concurrent patches based on the same old page MUST NOT silently overwrite one another.

---

## 8. W1 adapter contract

W1 keeps its existing source acquisition in W5A:

```text
LightRAG context
+ Tavily
+ builtin/Opus
```

W5A SHOULD NOT redesign retrieval quality or provider choice.

The change is at the output seam:

```text
W1 evidence/source catalog
      -> normalized EvidencePack
      -> candidate synthesis
      -> WikiPatch
      -> shared validator/apply engine
```

W1 must no longer directly `_atomic_write()` a generated page as its authoritative apply path.

For a brand-new page, W1 may emit `CREATE_PAGE`.

For an existing page, W1 must convert the intended change to non-destructive patch operations. A full generated candidate may be used internally to compute a section-level patch, but the applied artifact MUST respect the operation restrictions above.

`--dry-run`, cost-gate behavior, and `--skip-existing` semantics should remain compatible unless repository truth requires a narrowly documented adjustment.

---

## 9. W3 adapter contract

W3 keeps production-safe evidence acquisition:

```text
article hashes
+ entity buffers
+ current Wiki page state
```

No new external LLM/web call in the ingest hook.

W3 output changes from an opaque full-page `content` blob to a structured `EvidencePack` + `WikiPatch` proposal.

Policy in W5A:

### Existing rich page

Always `suggestion_only` unless the patch is a trivially safe metadata/source merge that the shared policy explicitly allows.

At minimum, the current safety behavior remains:

```text
rich existing page
-> no placeholder overwrite
-> structured patch stored under _suggestions/
```

### New page

W3 may auto-apply a low-confidence canonical `CREATE_PAGE` only when all of these are true:

- entity frequency threshold is met;
- all article hashes resolve;
- canonical schema/citations validate;
- full Wiki health validation for the candidate passes;
- target does not exist at final apply check.

Otherwise it becomes a structured suggestion.

### Failure isolation

Any W3 compiler failure returns a bounded failure result to `_wiki_update_check`; ingestion remains successful and the error is recorded. Existing W3 runtime budget/timeout behavior must not regress.

---

## 10. Policy layer in W5A

W5A needs only a small deterministic policy matrix. Do not build a generalized rule engine.

```text
W1 create + valid candidate                 -> auto_apply
W1 update + safe non-destructive patch      -> auto_apply only if all deterministic gates pass
W3 new page + threshold + all gates pass    -> auto_apply
W3 rich-page substantive update             -> suggestion_only
stale base digest                           -> reject/suggestion, never overwrite
missing/invalid evidence                    -> reject
candidate health/lint ERROR                 -> reject
candidate WARN only                         -> caller/policy decides; default conservative
```

W5B will add semantic utility, affected-query evaluation, guard queries, and richer risk levels. Do not pre-build those systems in W5A.

---

## 11. Error handling and Error Book integration

Every rejected patch that represents a real compiler integrity problem should be recordable with:

```text
patch_id
page/path
check/type
message/evidence
trigger (w1/w3)
compiler_version
status lifecycle
```

Use the existing Error Book lifecycle. Do not create a second error database.

Expected non-errors such as `suggestion_only` policy outcomes are workflow states, not lint failures.

A stale base digest is a concurrency conflict. It should be observable and retryable, not logged as a corrupted Wiki page.

---

## 12. Compatibility and migration

W5A is an incremental migration.

### Must preserve

- all existing Wiki pages;
- current legacy citation parsing/lint support;
- current production ingest success/failure semantics;
- W3 bounded hook behavior;
- deterministic health/index tooling;
- Error Book;
- W5-0 baseline artifacts;
- Git as final rollback/audit source.

### May change

- W1 internal output path: direct page write -> patch core;
- W3 suggestion artifact: opaque Markdown -> structured patch JSON;
- new-page renderer: legacy -> current canonical SCHEMA;
- shared helpers duplicated between W1/W3 may move into compiler modules.

### Must not do

- mass rewrite all 19 pages;
- bulk citation migration;
- delete legacy suggestion artifacts merely for cleanliness.

---

## 13. Testing strategy

W5A acceptance depends on behavior-anchor tests, not implementation-shape tests.

Minimum test matrix:

### Patch model / serialization

- round-trip `WikiPatch` JSON;
- unknown schema version rejected;
- invalid operation rejected;
- invalid target path rejected.

### Create

- new page `CREATE_PAGE` emits canonical typed sources + GFM citations;
- invalid/missing article evidence blocks apply;
- create fails safely if target appears before final apply.

### Existing-page update

- one H2 section can be added without changing unrelated sections;
- one H2 section can be updated without removing other content;
- existing `created` preserved;
- source merge deduplicates and never subtracts;
- legacy page keeps legacy rendering unless explicit safe upgrade exists;
- canonical page remains canonical;
- images/cross-links outside target section survive byte-for-byte where practical.

### Concurrency

- stale base digest cannot overwrite a newer page;
- two patches from the same base cannot both silently win.

### Validation / health

- bad citation rejected;
- bad YAML/frontmatter rejected;
- broken target/path rejected;
- health ERROR blocks apply;
- Error Book records true integrity failures without duplicate explosion.

### W1 adapter

- W1 new page goes through shared validate/apply seam;
- W1 update no longer uses authoritative direct full-page overwrite;
- cost gate/dry-run remain intact.

### W3 adapter

- W3 hook still invoked exactly once after relevant ingest batch;
- W3 failure does not abort successful article ingest;
- rich page update becomes structured suggestion and does not overwrite;
- new valid low-risk page may apply through shared core;
- entity-buffer canonical path remains first.

### Regression

Run all existing W5-0 Wiki tests plus directly affected ingest/generator tests.

---

## 14. Production UAT

Because W3 runtime code will likely change, Mode A production verification is required.

Minimum controlled production UAT:

1. deploy only the verified W5A runtime files using current authoritative mechanism;
2. confirm ingest service healthy before/after;
3. run or observe one bounded W3 update cycle using real production entity buffers;
4. prove W3 emits a structured patch/suggestion through the shared compiler seam;
5. prove one existing rich page is not overwritten;
6. if a safe new-page candidate is available, prove create through shared core; otherwise use a controlled non-destructive fixture/UAT path and do not manufacture production knowledge;
7. run `wiki_health` on production Wiki state;
8. verify index consistency;
9. rollback immediately if ingest or Wiki health regresses.

W1 is primarily an offline/batch path; production deployment is needed only for code actually consumed by current production jobs.

---

## 15. Acceptance gates

### Gate A — Shared typed compiler contract exists

`EvidenceRef`, `EvidencePack`, `WikiPatch` (or equivalent) are versioned, serializable, tested, and used by both W1/W3 adapters.

### Gate B — Non-destructive patch engine exists

Existing-page application is operation-based, not whole-page blind replacement. Unsupported/destructive ops fail closed.

### Gate C — Concurrency-safe atomic apply

Base digest/existence preconditions and atomic write prevent silent lost updates.

### Gate D — Canonical new-page schema

New W5A-created pages emit current `SCHEMA.md` canonical typed sources + GFM citations. Existing legacy pages remain compatible and are not bulk migrated.

### Gate E — W1 converges on shared seam

W1 no longer authoritatively direct-writes generated pages outside the shared patch validation/apply path.

### Gate F — W3 converges on shared seam

W3 generates structured patches/suggestions, preserves non-blocking ingest semantics, does not add external network/LLM work to the hook, and cannot overwrite a rich page with a placeholder.

### Gate G — Deterministic validation + Error Book integration

Invalid evidence/schema/citation/health candidates fail closed with durable diagnostics where appropriate.

### Gate H — Regression and production UAT

Relevant tests pass; controlled production W3 UAT proves shared-core behavior; Wiki health/index remain acceptable; production ingest remains healthy.

### Gate I — Independent adversarial verification + closeout

An independent reviewer checks actual diff/evidence against Gates A-H and confirms no W5B/W6/W7/W8 scope creep. Planning/ISSUES/SUMMARY/VERIFICATION artifacts are reconciled and pushed.

---

## 16. Autonomous execution discipline for the later Hermes `/goal`

After this design is approved and converted into an implementation plan, Hermes may run Mode A autonomously with the established loop:

```text
DISCOVER
-> PLAN
-> ADVERSARIAL PLAN REVIEW
-> RED / REPRODUCE
-> MINIMUM BUILD
-> TEST
-> ADVERSARIAL DIFF REVIEW
-> VERIFY GATES
-> DEPLOY / PROD UAT where applicable
-> DIAGNOSE / REVISE until pass
```

Hermes must rediscover current repo/live truth before implementation and must not weaken these gates to obtain PASS.

Production safety boundaries remain the same as W5-0: no destructive corpus/DB/Qdrant operation, no secret rotation, no force push, no new paid service, no security-control bypass, and automatic rollback on runtime regression.

---

## 17. W5A exit state

W5A is complete when OmniGraph can truthfully be described as:

```text
W1 rich batch evidence ---------\
                                 -> Shared Patch Compiler
W3 incremental evidence --------/       |
                                         +-> validated atomic apply
                                         +-> structured suggestion
                                         +-> Error Book on integrity failure
```

At that point W5B can focus only on **semantic quality and autonomous evolution**:

```text
propose patch
-> source-grounded semantic check
-> affected-query eval
-> guard-query eval
-> risk policy
-> auto-apply / hold
```

W5B must not need to redesign page mutation, concurrency, provenance, or apply semantics again.
