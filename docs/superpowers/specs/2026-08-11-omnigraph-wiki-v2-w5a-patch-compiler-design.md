# OmniGraph Wiki v2 — W5A Unified Patch Compiler Core

**Date:** 2026-08-11  
**Status:** AUTHORITATIVE DESIGN CONTRACT — implementation not started  
**Depends on:** W5-0 `W5-0 CLOSURE RESULT: PASS` through `3f0680cd`  
**Next phase:** W5B Safe Autonomous Wiki Evolution

---

## 1. Purpose

W5-0 established a trustworthy foundation: W3 is production-proven, article identity is canonical 10-char MD5, the production entity-buffer path is fixed, rich W1 pages are protected from placeholder overwrite, deterministic health/index tooling exists, the Error Book has a lifecycle, and a rerunnable retrieval baseline exists.

The remaining compiler problem is architectural:

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

These are two generators targeting the same directory, not one compiler.

**W5A goal:** create one shared typed seam:

```text
EvidencePack
  -> WikiPatch proposal
  -> deterministic patch validation
  -> candidate-page assembly
  -> Wiki lint/health validation
  -> deterministic policy
  -> atomic apply OR structured suggestion
```

W5A builds safe compiler mechanics. W5B will later add semantic/query-feedback-driven autonomous acceptance.

---

## 2. Non-goals

W5A MUST NOT implement runtime Wiki navigation graph, `wiki_search`/`wiki_read`, N-hop traversal, retrieval fusion, affected-query/guard-query acceptance gates, query-feedback learning, concepts/domains aggregation, Wiki-first UI, answer caching, bulk citation migration, a new paid provider, or a new production service.

Those remain W5B/W6/W7/W8 work.

---

## 3. Design choice

Three approaches were considered:

1. **Full W1/W3 rewrite now** — clean final architecture but excessive blast radius. Rejected.
2. **Shared Patch Core + adapters** — preserve current evidence acquisition while converging proposal/validation/apply. **Selected.**
3. **Thin wrapper around two full-page generators** — small but leaves whole-page replacement semantics intact. Rejected.

W5A therefore introduces a real patch core and adapts W1/W3 to it incrementally.

---

## 4. Core principles

### 4.1 Markdown/frontmatter remains the Wiki source of truth

Applied Wiki pages remain knowledge truth. Git remains the durable audit/rollback mechanism. `_suggestions/` contains workflow artifacts only.

### 4.2 Patches are the unit of change

Existing-page changes must be explicit operations. No caller may authoritatively replace a whole existing page outside the shared compiler.

### 4.3 Evidence is normalized independently of Markdown style

Internal compiler objects use one normalized evidence model. Rendering may preserve an existing legacy citation style or use the current canonical schema for new pages.

### 4.4 W5A is conservative on existing-page content

The patch model may represent a **scoped H2 section replacement**, because W5B will need that primitive. However, during W5A, any substantive existing-page body mutation is **suggestion-only**. It MUST NOT auto-apply.

W5A may auto-apply to an existing page only narrowly safe non-substantive changes explicitly allowed by policy, such as a deterministic source merge or metadata update that preserves all existing body content.

Therefore W5A never automatically deletes or replaces an existing paragraph, section, image, or cross-reference.

### 4.5 Optimistic concurrency is mandatory

Every update patch carries the base page digest seen when proposed. Apply fails safely if the target changed before final write.

### 4.6 W3 stays non-blocking

No new Tavily/Databricks/LLM/network work is added to the production ingest hook. W3 remains bounded and failure-isolated. Semantic enrichment belongs to W5B or an out-of-band worker.

---

## 5. Internal compiler data model

Exact Python names may differ, but the observable contract must be equivalent.

### 5.1 `EvidenceRef`

```text
EvidenceRef
- evidence_id
- type: article | web | builtin
- ref: article hash | URL | null
- title
- provenance
- metadata: optional non-secret mapping
```

Rules:

- article refs are canonical 10-char lowercase hex and must resolve before apply;
- web refs are URLs;
- builtin refs are null;
- `evidence_id` is compiler-local and is not a Markdown footnote number.

### 5.2 `EvidencePack`

```text
EvidencePack
- pack_id
- subject_slug
- subject_title
- trigger: w1_batch | w3_incremental | manual_test
- article_hashes[]
- evidence[]
- context_blocks[]
- existing_page_path | null
- existing_page_digest | null
- created_at
- compiler_version
```

W1 and W3 may populate different context richness; they still feed the same compiler contract.

### 5.3 `WikiPatch`

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

Allowed W5A operations:

```text
CREATE_PAGE
UPSERT_SECTION
MERGE_SOURCES
SET_METADATA
```

There is no generic `REPLACE_PAGE`, `DELETE_SECTION`, or `DELETE_SOURCE` operation.

`CREATE_PAGE` is valid only when the target does not exist.

`UPSERT_SECTION` targets exactly one normalized H2 heading. The pure patch engine may assemble a candidate with that section inserted/replaced while preserving all other sections. **For an existing page, such a substantive operation is suggestion-only in W5A.**

`MERGE_SOURCES` is union/dedup and never subtractive.

`SET_METADATA` may change only compiler-approved fields such as `last_updated`, `confidence_level`, and narrowly required schema metadata. It must preserve `created`.

### 5.4 Structured suggestions

New W5A proposal source of truth:

```text
kb/wiki/_suggestions/<slug>-<patch-id>.json
```

It stores serialized `WikiPatch` plus validation/policy outcome. Legacy `.md` suggestions remain readable and are not bulk-migrated.

---

## 6. Citation/schema strategy

Repository truth is currently split:

- `kb/wiki/SCHEMA.md` defines typed `sources[]` dictionaries + GFM `[^N]` as canonical for newly authored pages;
- legacy `^[article:<10-char>]` remains lint-supported;
- current W1 generator still explicitly emits the legacy format.

W5A resolves this without rewriting all existing pages.

### New pages

Every new page created through the W5A compiler MUST emit the current canonical `SCHEMA.md` representation: typed article/web/builtin sources and GFM footnote citations.

### Existing pages

Existing pages are not mass-converted. The renderer detects and preserves existing citation/frontmatter style by default.

If a legacy existing page cannot safely represent a proposed non-article source without broader format migration, the patch becomes `suggestion_only`; W5A does not silently drop provenance or convert the full page.

Both legacy and canonical forms continue to lint-pass.

---

## 7. Module boundaries

Recommended structure:

```text
kb/wiki_compiler/
  models.py       # EvidenceRef/EvidencePack/WikiPatch + serialization
  patch.py        # pure candidate assembly / section/source merge
  validate.py     # deterministic patch + candidate validation
  apply.py        # policy, base-digest guard, atomic apply/suggestion
  adapters/
    w1.py
    w3.py
```

Hermes may use fewer files if that fits repository conventions, but source acquisition, network/LLM calls, patch mechanics, validation, and filesystem apply must not collapse into one new monolith.

### Pure patch engine

Input:

```text
existing page or null + WikiPatch
```

Output:

```text
candidate Markdown + deterministic diagnostics
```

No network calls.

### Validator

Validation order:

1. patch schema/version/type;
2. target path/kind;
3. base digest / existence precondition;
4. evidence identity;
5. operation safety;
6. candidate frontmatter/schema parse;
7. citation integrity;
8. wikilink validity under existing policy;
9. Wiki-health-compatible integrity checks;
10. existing contradiction/staleness checks where meaningful.

Blocking integrity failures do not apply and are recorded in the existing Error Book with patch provenance.

### Apply engine

Observable behavior:

```text
validate
 -> acquire narrow per-page guard
 -> re-check target existence/base digest
 -> assemble candidate
 -> final validation
 -> atomic tempfile + replace OR structured suggestion
 -> release guard
```

Two concurrent patches based on the same old page must not silently overwrite one another.

---

## 8. W1 adapter

W1 keeps its current evidence acquisition in W5A:

```text
LightRAG + Tavily + builtin/Opus
```

W5A does not redesign provider choice or retrieval quality.

Its output seam changes to:

```text
W1 source catalog/context
 -> normalized EvidencePack
 -> candidate synthesis
 -> WikiPatch
 -> shared validation/policy/apply
```

W1 must no longer authoritatively `_atomic_write()` an existing page outside the shared compiler.

Policy:

- **new page:** valid `CREATE_PAGE` may auto-apply;
- **existing page substantive body update:** structured suggestion only in W5A;
- **existing page narrowly safe source/metadata merge:** may auto-apply if explicitly allowed and all deterministic gates pass.

`--dry-run`, cost gate, and `--skip-existing` remain compatible unless current repository truth requires a narrowly documented adjustment.

---

## 9. W3 adapter

W3 keeps production-safe evidence acquisition:

```text
article hashes + entity buffers + current page state
```

No external LLM/web call in the ingest hook.

W3 changes from opaque full-page `content` suggestions to `EvidencePack + WikiPatch`.

Policy:

- **existing rich page substantive update:** always structured suggestion; never placeholder overwrite;
- **new page:** low-confidence canonical `CREATE_PAGE` may auto-apply only when frequency threshold, source resolution, schema/citation validation, Wiki health, and final target-existence checks all pass;
- otherwise store a structured suggestion.

Any compiler failure remains bounded and must not abort successful article ingestion.

---

## 10. Deterministic W5A policy matrix

Do not build a generalized rule engine.

```text
W1 new + valid CREATE_PAGE                  -> auto_apply
W1 existing + body UPSERT_SECTION           -> suggestion_only
W1 existing + safe source/metadata merge    -> auto_apply only if explicitly allowed
W3 new + threshold + all gates pass         -> auto_apply
W3 existing + substantive body change       -> suggestion_only
stale base digest                           -> conflict/retry/suggestion, never overwrite
missing or invalid evidence                 -> reject
candidate health/lint ERROR                 -> reject
candidate WARN only                         -> conservative policy; no silent promotion
```

W5B, not W5A, adds semantic utility/risk scoring and affected/guard query evaluation.

---

## 11. Error Book integration

True integrity failures must be recordable in the existing Error Book with patch ID, page/path, check/type, evidence/message, trigger, compiler version, and normal lifecycle semantics.

Do not create another error database.

Expected workflow outcomes such as `suggestion_only` are not lint errors. A stale base digest is a concurrency conflict and should be observable/retryable rather than classified as Wiki corruption.

---

## 12. Compatibility and migration

W5A must preserve:

- all existing Wiki pages;
- legacy citation parsing/lint support;
- production ingest success/failure semantics;
- W3 timeout/failure isolation;
- Wiki health/index tooling;
- Error Book;
- W5-0 baseline artifacts;
- Git rollback/audit semantics.

W5A may change:

- W1 authoritative write path -> shared patch core;
- W3 suggestion artifact -> structured JSON patch;
- new-page rendering -> current canonical schema;
- duplicated W1/W3 helpers -> shared compiler modules.

W5A must not bulk-rewrite the 19 existing pages, bulk-migrate citations, or delete legacy suggestion artifacts merely for cleanup.

---

## 13. Testing strategy

Acceptance uses behavior anchors.

### Model/serialization

- patch JSON round trip;
- unknown schema version rejected;
- invalid op/path rejected.

### Create

- new `CREATE_PAGE` emits canonical typed sources + GFM citations;
- invalid article evidence blocks apply;
- create loses safely if target appears before final write.

### Existing page

- adding a new H2 preserves all unrelated content;
- pure engine can build a scoped section update without changing other sections;
- W5A policy holds substantive existing-section update as suggestion-only;
- `created` preserved;
- source merge deduplicates and never subtracts;
- legacy page preserves legacy style;
- canonical page remains canonical;
- unrelated images/cross-links survive.

### Concurrency

- stale base digest cannot overwrite newer page;
- two same-base patches cannot both silently win.

### Validation/health

- bad citation/frontmatter/path rejected;
- health ERROR blocks apply;
- Error Book dedup lifecycle remains intact.

### W1

- new page goes through shared seam;
- existing substantive update becomes structured patch/suggestion, not direct overwrite;
- cost gate/dry-run remain intact.

### W3

- hook still fires once after relevant ingest path;
- W3 failure never aborts successful ingest;
- rich page update becomes structured suggestion;
- valid new page may apply through shared core;
- canonical entity-buffer path remains first.

Run all existing W5-0 Wiki tests plus directly affected generator/ingest tests.

---

## 14. Production UAT

Because W3 runtime code is expected to change, Mode A production UAT is required.

Minimum UAT:

1. deploy only verified runtime files by current authoritative mechanism;
2. confirm ingest healthy before/after;
3. run or observe one bounded W3 cycle on real entity buffers;
4. prove W3 emits a structured patch/suggestion through the shared compiler;
5. prove an existing rich page is not overwritten;
6. if a naturally safe new-page candidate exists, prove create through shared core; otherwise use a controlled non-destructive fixture/UAT and do not manufacture production knowledge;
7. run Wiki health and index consistency checks;
8. rollback immediately on ingest/Wiki regression.

W1 is an offline/batch path; deploy only code actually consumed by production jobs.

---

## 15. Acceptance gates

### Gate A — Shared typed contract

Versioned, serializable `EvidenceRef`, `EvidencePack`, `WikiPatch` (or equivalent) exist and are used by both adapters.

### Gate B — Patch engine

Existing-page intent is operation-based. Whole-page blind replacement is impossible through the authoritative apply path. Substantive existing-page mutation remains suggestion-only in W5A.

### Gate C — Concurrency-safe atomic apply

Base digest/existence guards and atomic write prevent lost updates.

### Gate D — Canonical new-page schema

New W5A pages emit current canonical typed sources + GFM citations; legacy pages remain compatible without bulk migration.

### Gate E — W1 convergence

W1 no longer authoritatively direct-writes existing pages outside shared validation/policy/apply.

### Gate F — W3 convergence

W3 emits structured patches/suggestions, remains non-blocking, adds no external network/LLM work to ingest, and cannot overwrite rich pages with placeholders.

### Gate G — Deterministic validation + Error Book

Invalid evidence/schema/citation/health fails closed with durable diagnostics where appropriate.

### Gate H — Regression + production UAT

Relevant tests pass; controlled production W3 UAT proves shared-core behavior; Wiki health/index and ingest remain healthy.

### Gate I — Independent verification + closeout

Fresh reviewer checks actual diff/evidence against Gates A-H, including explicit review for scope creep into W5B/W6/W7/W8. Planning/ISSUES/SUMMARY/VERIFICATION artifacts are reconciled and pushed.

---

## 16. Later Hermes execution discipline

After user approval of this spec and creation of an implementation plan, Hermes may execute Mode A using:

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
-> DIAGNOSE / REVISE until PASS
```

Hermes must rediscover current repo/live truth and must not weaken the gates.

Existing safety boundaries remain: no destructive corpus/DB/Qdrant operation, secret rotation, force push, new paid service, security-control bypass, or leaving production degraded after a failed deploy.

---

## 17. W5A exit state

W5A is complete when this is true:

```text
W1 rich batch evidence ---------\
                                 -> Shared Patch Compiler
W3 incremental evidence --------/       |
                                         +-> validated atomic create/safe merge
                                         +-> structured substantive-update suggestion
                                         +-> Error Book on integrity failure
```

Then W5B can focus only on semantic quality and autonomous evolution:

```text
propose patch
-> source-grounded semantic check
-> affected-query eval
-> guard-query eval
-> risk policy
-> auto-apply / hold
```

W5B must not need to redesign page mutation, concurrency, provenance, or apply semantics again.
