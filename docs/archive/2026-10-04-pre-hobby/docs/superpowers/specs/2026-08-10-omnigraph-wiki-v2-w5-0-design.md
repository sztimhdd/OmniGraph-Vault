# OmniGraph Wiki v2 — W5-0 Integrity, Eval Baseline & Compiler Convergence

> **Date:** 2026-08-10  
> **Authoritative design owner:** GPT-5.6 Sol (orchestrator)  
> **Executor:** Hermes `/goal` autonomous loop  
> **Status:** APPROVED FOR AUTONOMOUS EXECUTION (Mode A: code + deploy + production UAT)  
> **Scope:** W5-0 only. This document does **not** authorize W6 navigation graph, W7 hybrid retrieval, or W8 UI work.

## 1. Goal

Make the existing OmniGraph Wiki trustworthy enough to become the input to the next compiler/navigation waves.

W5-0 is **not** a new Wiki feature wave. It is a convergence and correctness wave that must:

1. establish production truth for the existing W3 incremental hook;
2. eliminate the current Wiki identity/schema inconsistencies;
3. provide an independent deterministic health checker;
4. create a persistent error lifecycle rather than fire-and-forget lint logs;
5. establish a reproducible retrieval/query baseline before later architecture claims;
6. converge the existing W1 batch generator and W3 incremental updater onto one compiler contract;
7. prevent rich existing Wiki pages from being blindly overwritten by the current placeholder-style W3 update path.

The intended next-stage architecture after W5-0 is:

```text
raw corpus / newly ingested articles
          |
          v
  affected-page detection
          |
          v
     propose PATCH
          |
          v
 deterministic + semantic validation
          |
          v
 downstream query evaluation
          |
          v
       apply patch
          |
          v
 Markdown/frontmatter Wiki = source of truth
```

A future navigation graph must be a **derived artifact** from Wiki pages, never a second source of truth.

---

## 2. Why this wave exists

The repository already contains more Wiki machinery than the old roadmap implies:

- `scripts/wiki_generate_pages.py` is a real 3-source W1 batch generator (LightRAG corpus + web + LLM synthesis), not merely manual page authoring.
- `kb/wiki_update.py` is a second, much simpler W3 incremental generator/updater.
- `batch_ingest_from_spider.py` already wires `_wiki_update_check()` after the ingest batch.
- `kb/services/wiki_inject.py` already injects one literal-slug-matched Wiki page into synthesize.
- `kb/wiki_lint.py` already contains several pre-apply lints.

The immediate architectural risk is therefore **compiler divergence**, not absence of a compiler.

Known repository facts that MUST be re-verified at execution time:

1. `lib.checkpoint.get_article_hash(url)` currently returns SHA256 first **16** hex characters.
2. the legacy Wiki citation regex/schema still describes `^[article:<10-char-hex>]`.
3. `kb/wiki/index.md` has historically been generated from fewer pages than are actually present under `kb/wiki/entities/`.
4. W3's `_build_page()` is placeholder-style output and is not acceptable as an unconditional overwrite path for a rich W1 page.
5. existing `wiki-lint-failures.jsonl` is a log, not a durable error-book lifecycle.

Do not assume these are still true merely because this spec says so: inspect current HEAD and production first.

---

## 3. Authority and truth-source order

When documents disagree, use this order:

1. **Live production evidence** (systemd/journald/API/SQLite/files actually serving users)
2. **Current code call sites on current HEAD**
3. **Current deploy units / scripts in repo**
4. **This W5-0 design contract** for intent and acceptance boundaries
5. `CLAUDE.md` execution discipline
6. `.planning/ISSUES.md`
7. historical Wiki design/planning documents

Historical design documents are evidence of prior intent, not present runtime truth.

### Mandatory repository reads before planning

At minimum read:

- `CLAUDE.md`
- `.planning/ISSUES.md`
- `.planning/wiki-integration-design.md`
- `kb/wiki/SCHEMA.md`
- `kb/wiki/index.md`
- `kb/wiki/log.md`
- `kb/wiki_lint.py`
- `kb/wiki_update.py`
- `kb/services/wiki_inject.py`
- `scripts/wiki_generate_pages.py`
- `batch_ingest_from_spider.py` (especially `_wiki_update_check` and its call site)
- current Wiki-related tests
- current Aliyun deployment/runbook docs and the actual systemd unit that invokes ingest

Also inspect recent Wiki-related commits rather than relying on old STATE text.

---

## 4. External design principles to preserve

These are design inputs, not implementation dependencies:

- **LLM-Wiki (arXiv:2605.25480):** agent-native Wiki retrieval works through progressive `search -> read -> follow links` navigation; progressive traversal is more important than merely having structured pages.
- **WikiLoop (arXiv:2607.26604):** Wiki edits should eventually be judged by downstream query utility, not only by structural validity. Use affected queries + guard queries as the engineering analogue; no RL work is required in W5-0.
- **WiCER (arXiv:2605.07068):** compile and evaluate cannot be separated into distant phases; compilation needs an evaluation/diagnosis/refinement loop.
- **Alibaba/Qwen LLM-Wiki production article (2026-06):** compile-time Wiki and runtime RAG are complementary; deterministic graph/health compilation is valuable, but OmniGraph must not copy data-warehouse relation semantics blindly.

W5-0 adopts these principles only to establish contracts and evaluation. It does not implement the future multi-hop navigator yet.

---

## 5. Explicit non-goals

Do **not** implement any of the following in W5-0 unless a minimal compatibility shim is strictly required to satisfy a W5-0 gate:

- no `graph.json` / `wiki_nav_graph.json` runtime navigation;
- no N-hop graph expansion inside `kg_search`;
- no new MCP `wiki_search` / `wiki_read` production tools;
- no weighted multi-retriever fusion/reranker design;
- no concepts/domains aggregation wave;
- no Wiki-first frontend redesign;
- no answer-cache-to-`queries/` feature;
- no bulk regeneration/rewrite of all existing Wiki pages;
- no new paid vendor/subscription/account registration;
- no unrelated refactor of ingest, LightRAG, MCP, Databricks, or KOL scan.

If implementation naturally grows into these areas, stop that branch of work and record it as follow-up, not as W5-0 scope.

---

## 6. Required execution loop

Hermes must operate as the **temporary project orchestrator**, not as a single coding subagent.

For every material change, execute this loop:

```text
DISCOVER
  -> DECIDE
  -> PLAN
  -> ADVERSARIAL PLAN REVIEW
  -> RED / REPRODUCE
  -> BUILD MINIMUM CHANGE
  -> TEST
  -> ADVERSARIAL DIFF REVIEW
  -> VERIFY AGAINST CONTRACT
  -> DEPLOY / PROD UAT when relevant
  -> if any gate fails: DIAGNOSE -> REVISE -> repeat
```

### Plan-review rule

Before editing production code, obtain an independent review perspective (fresh subagent/reviewer/judge) that actively tries to reject the plan for:

- duplicated compiler paths;
- unsupported assumptions about production;
- unnecessary architecture;
- weak/no behavior-anchor tests;
- scope creep into W6/W7/W8;
- data-loss/overwrite risk;
- a test that only validates implementation shape instead of observable behavior.

Do not proceed until blocking review findings are either fixed or explicitly disproved with evidence.

### Right-size rule

Honor `CLAUDE.md` Right-Size GSD discipline after diagnosis. Diagnostic complexity does not justify a heavy implementation ceremony if the actual change is tiny. Separate independent fixes into atomic commits.

---

## 7. W5-0 deliverables and acceptance gates

### Gate A — Production W3 truth established

Produce evidence showing what the currently deployed ingest actually does after a batch:

- identify the authoritative production host/service from current deployment truth;
- show the deployed code contains/does not contain `_wiki_update_check`;
- inspect recent journald for `W3 wiki hook:` / timeout / failure evidence;
- capture actual `suggestions`, `applied`, `dropped` behavior if present;
- determine whether production Wiki files are modified by the hook and where;
- determine whether current production hashes are 10-char, 16-char, mixed, or another form.

If natural cron evidence is insufficient, run the **smallest safe controlled production UAT** that can prove the hook contract without bulk-changing Wiki content.

**Pass condition:** a human can read the evidence and know whether W3 is actually live, what it touches, and whether its hash identity contract works.

### Gate B — Article identity/citation contract unified

Resolve the 10-vs-16-char ambiguity into one documented canonical rule while maintaining backward compatibility where required.

Requirements:

- one canonical article identity length/format for new Wiki compiler output;
- legacy pages continue to lint/render correctly;
- lint must not silently ignore a citation merely because its length differs;
- tests must cover legacy and canonical formats plus invalid/nonexistent hashes;
- W3 suggestion lookup and produced citations must use the same contract as the DB/corpus truth.

Do not mass-edit old Wiki pages solely to normalize formatting unless tests demonstrate it is required.

### Gate C — Independent deterministic Wiki health checker

Implement a standalone health command/script that can run read-only against the Wiki and emit both human-readable and machine-readable output.

At minimum check:

1. page-count/index consistency;
2. required frontmatter/schema fields;
3. YAML parse validity;
4. citation/source integrity;
5. wikilink target validity;
6. orphan/unindexed pages;
7. duplicate slugs/titles where relevant;
8. staleness signal under the canonical current schema;
9. compiler-generated artifact consistency if any artifact is introduced inside W5-0.

Exit code must be non-zero on blocking integrity errors. Distinguish ERROR vs WARN so harmless staleness does not necessarily make the Wiki unusable.

**Pass condition:** it detects at least one known synthetic bad fixture and passes the repaired real Wiki with explained warnings only.

### Gate D — Index generation drift eliminated

`kb/wiki/index.md` must be derived reproducibly from the actual page set according to an explicit inclusion policy.

Requirements:

- no manual stale page-count list;
- deterministic ordering;
- test or health assertion proving every expected visible page is indexed exactly once;
- no accidental exposure of `_suggestions/` or internal artifacts.

### Gate E — Persistent Error Book lifecycle

Upgrade lint failure handling into a durable, reviewable error lifecycle. This can be a JSONL/SQLite/Markdown design, but it must support stable identity and status, not an append-only stream of duplicate warnings.

Minimum fields/semantics:

- stable error key/fingerprint;
- first_seen / last_seen;
- page/path;
- check/type;
- evidence/message;
- status (`open`, `resolved`, optionally `ignored` with reason);
- compiler/checker version or equivalent provenance.

Re-running health must update existing errors rather than explode duplicates. A repaired issue must become resolvably closed/absent according to documented semantics.

### Gate F — Retrieval/evaluation baseline established before W6

Create a version-controlled benchmark set of roughly **20-30 queries** that covers at least:

- direct entity/fact lookup;
- comparison;
- 2-hop relationship/bridge queries;
- 3-hop or cross-page synthesis;
- enumeration/global questions;
- freshness/time-sensitive questions;
- negative/no-answer questions.

Benchmark current behavior only; do not fabricate claimed percentage improvements.

Capture, where technically feasible:

- route/path used (`wiki injection`, `kg_search`, FTS fallback, etc.);
- answer/no-answer correctness judged against explicit expected facts/sources;
- citation/source quality;
- latency;
- token/cost fields if already observable without major instrumentation.

The benchmark must be rerunnable later by W6/W7. Store raw results/evidence separately from aggregate summary.

### Gate G — Compiler convergence contract written and enforced at one narrow seam

By the end of W5-0 there must be a documented and code-visible convergence direction for W1 and W3:

```text
source/evidence collection
       -> propose page patch
       -> validate patch
       -> optional downstream eval hook
       -> atomic apply
```

W5-0 does **not** need to fully rewrite W1 and W3 into a finished compiler. It does require eliminating the most dangerous divergence: W3 must not blindly overwrite a rich existing page with its placeholder `_build_page()` representation.

Acceptable minimal behavior for existing rich pages includes one of:

- emit/update a suggestion artifact for later compiler processing;
- produce a structured patch proposal without applying it;
- safely skip auto-apply and log an actionable Error Book/suggestion entry.

For brand-new low-risk placeholder pages, existing auto-create behavior may remain only if it passes canonical schema + health gates.

### Gate H — Regression protection

At minimum include behavior-anchor tests for:

- W3 hook invoked exactly once after the relevant ingest batch path;
- W3 failure never corrupts/aborts successful article ingestion;
- rich existing page is not destructively overwritten;
- canonical/legacy citation handling;
- index generation/health drift;
- Error Book dedupe/resolution lifecycle.

Run the relevant existing Wiki/ingest tests plus any broader suite justified by touched files.

### Gate I — Production deploy/UAT if runtime code changes

Mode A authorizes autonomous production deployment.

If runtime W3/ingest/KB code is modified:

- deploy through the current authoritative mechanism discovered from repo/live truth;
- restart only the minimal relevant services;
- preserve current env/secrets;
- run health/readiness checks;
- run a controlled Wiki/W3 UAT;
- verify ingestion remains healthy;
- verify no existing rich Wiki page was degraded;
- automatically rollback to the last known-good revision if production health regresses.

If only offline tooling/docs/tests are changed, do not manufacture a production restart merely to satisfy ceremony.

### Gate J — Closeout and provenance

Before declaring the goal complete:

- commits are atomic and pushed;
- no force-push;
- no secrets/database/runtime blobs committed;
- update the appropriate planning/verification artifacts;
- as the temporary orchestrator, reconcile `.planning/ISSUES.md` for newly discovered out-of-scope issues and resolved issues;
- produce a final `SUMMARY.md` / `VERIFICATION.md` containing commands, results, production evidence, commit SHAs, and remaining risks;
- explicitly state which future work belongs to W5, W6, W7, W8.

---

## 8. Safety boundaries for autonomous Mode A

The user has authorized unattended autonomous code changes, commits/pushes, SSH operations, relevant service restarts, production deployment, and production UAT.

The following are still forbidden without stopping for the user:

- destructive production DB/schema migration with irreversible data loss;
- deleting or bulk-rewriting production Wiki/raw corpus without a tested rollback;
- deleting Qdrant/LightRAG collections;
- rotating/removing secrets or authentication credentials;
- registering a new paid service, buying credits, or materially increasing paid spend;
- force-pushing or rewriting shared Git history;
- changing the core product architecture outside W5-0 because it is "cleaner";
- disabling security controls to make a test pass.

Normal use of already-configured providers within ordinary project operating cost is allowed.

If a runtime deploy fails, first rollback automatically and restore service. Do not leave production degraded while continuing experimentation.

---

## 9. Stop conditions

### SUCCESS

Stop only when **all Gates A-J applicable to the actual touched scope pass**, evidence is committed/pushed, and an independent verifier/judge agrees there is no blocking gap.

### BLOCKED

Stop and report BLOCKED only if one of these is true:

1. success requires one of the forbidden actions above;
2. required secret/credential is absent and cannot be recovered from existing approved project configuration;
3. production cannot be restored to healthy state after an attempted deployment rollback;
4. repository/live truth reveals a major architectural contradiction that makes this W5-0 contract unsafe to interpret without the user;
5. the same root cause fails three materially different repair attempts with no new evidence/progress.

Do **not** stop merely to ask stylistic questions, naming preferences, minor implementation choices, or permission for routine deploy/test/restart actions already authorized by Mode A.

---

## 10. Expected artifacts

Use existing project conventions where possible. Suggested W5-0 artifact set:

```text
.planning/phases/wiki-v2-w5-0/
  RESEARCH.md                 # repo + live audit, W3 truth, hash truth
  PLAN.md                     # Hermes-produced reviewed implementation plan
  BASELINE.md                 # benchmark definition + aggregate baseline
  VERIFICATION.md             # gate-by-gate evidence
  SUMMARY.md                  # final closeout

kb/wiki/...
  # only changes justified by gates

scripts/ or kb/
  # standalone wiki health implementation in the most natural existing location

tests/...
  # behavior anchors and health fixtures
```

Do not create planning files solely for ceremony if the actual fix decomposes into small quicks; the artifact names may be adapted to current project conventions. The **evidence content** is mandatory, not the exact folder naming.

---

## 11. Future architecture intentionally deferred

After W5-0, a new design/review gate is required before implementation of:

### W5 — Patch Compiler

Converge W1 batch generation + W3 incremental changes into a source-grounded patch compiler with affected-page detection and semantic evaluation.

### W6 — Agent-Native Wiki Navigation

Derived page-level navigation graph plus `wiki_search` / `wiki_read`, with progressive traversal controlled by the agent. Markdown/frontmatter remains source of truth; graph is rebuildable.

### W7 — Hybrid + Feedback Loop

Wiki navigation first, LightRAG/FTS fallback when evidence is insufficient, benchmark-driven routing/fusion, affected-query + guard-query feedback to compiler.

### W8 — Aggregation + Wiki-first UX

Concept/domain/MOC pages and user-facing Wiki-first rendering after retrieval/compiler value is proven.

Do not silently pull these future waves into W5-0.

---

## 12. Completion statement format

The final Hermes `/goal` report must end with exactly one of:

```text
W5-0 RESULT: PASS
```

or

```text
W5-0 RESULT: BLOCKED
Blocking reason: <specific hard stop condition>
Production state: <healthy/rolled back/degraded>
```

A green test suite without live/runtime evidence where applicable is **not** PASS.
A successful deploy without independent health/evaluation evidence is **not** PASS.
A judge verdict based only on the agent's summary rather than commands/artifacts is **not** PASS.
