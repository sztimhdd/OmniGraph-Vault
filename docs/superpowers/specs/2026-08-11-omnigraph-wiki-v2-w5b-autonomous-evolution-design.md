# OmniGraph Wiki v2 — W5B Autonomous Evolution Design

**Status:** AUTHORITATIVE DESIGN CONTRACT — implementation not started  
**Date:** 2026-08-11  
**Depends on:** W5A FINAL PASS through `23eb430df195a6fc6bc8e2afe65fcdc2ba44da13`  
**Next phase:** W6 Agent-Native Wiki Navigation

---

## 1. Goal

W5B turns W5A's durable `suggestion_only` WikiPatch artifacts into a **zero-human-maintenance autonomous evolution loop** for this personal knowledge base.

The user explicitly chose high autonomy:

- substantive existing-page rewrites may be applied automatically;
- no human approval queue is part of the normal path;
- if the model is uncertain or unavailable, the system retries automatically later;
- explicit semantic failure is rejected automatically;
- W3 ingest remains non-blocking and must not gain LLM/network work;
- **all successfully ingested historical articles that predate W3 Wiki hooks must also be brought into the Wiki evolution path, rather than being permanently invisible.**

W5B is intentionally small. It is not a general knowledge-evolution platform.

---

## 2. Ponytail / YAGNI constraints

The following are explicitly **out of scope** because they would over-design a personal knowledge base:

- no `EvaluationCertificate` subsystem;
- no dedicated queue database;
- no event bus or resident daemon;
- no evaluator ensemble or voting framework;
- no generic provider registry;
- no per-patch affected-query / guard-query benchmark framework;
- no risk-scoring framework;
- no snapshot/rollback database;
- no generalized rule engine;
- no second historical-ingest pipeline;
- no W6 navigation graph, `wiki_search`, `wiki_read`, N-hop traversal, retrieval fusion, or query-feedback loop.

Existing components must be reused before new abstractions are introduced.

The minimum runtime shape is:

```text
historical successful ingestions -- one-time bootstrap --\
                                                       +-> suggestion JSON
future W1 / W3 ---------------------------------------/
                                                            |
                                                            v
                                                   scripts/wiki_evolve.py
                                                            |
                                                    one DeepSeek call
                                                            |
                                                   APPLY | RETRY | REJECT
                                                            |
                                                   existing W5A compiler
```

The historical bootstrap is a mode of the same `wiki_evolve.py` script, not a new daemon/service/database.

---

## 3. Existing foundation that W5B reuses

W5A already provides the safety mechanisms W5B needs:

- complete serialized `WikiPatch` in deterministic suggestion JSON;
- page `base_digest` optimistic concurrency;
- per-page `fcntl.flock` locking;
- canonical / legacy rendering compatibility;
- evidence validation;
- candidate frontmatter/citation validation before write;
- Error Book integration;
- atomic tempfile + `os.replace` writes;
- no generic delete operation;
- no authoritative full-page blind replacement.

Existing repo components also already expose the historical truth W5B needs:

- `scripts/reconcile_ingestions.py` defines successful ingestion truth as `ingestions.status='ok'` reconciled against LightRAG `kv_store_doc_status.json` status `processed`, covering WeChat and RSS;
- `kb/wiki_compiler/adapters/w3.py` already converts article/entity-buffer evidence into `EvidencePack` / `WikiPatch`;
- `scripts/wiki_rank_entities.py` already reads LightRAG entities/relationships and their `source_id` chunk references;
- `scripts/wiki_generate_pages.py` already contains chunk -> article mapping logic from LightRAG chunk/full-doc stores to local article identities.

W5B MUST reuse these truths/mechanics rather than create a second source of ingestion or graph identity.

---

## 4. One new runtime component

Add one oneshot script:

```text
scripts/wiki_evolve.py
```

It has two modes:

```text
normal mode             -> scan/process due suggestion JSON files
--bootstrap-existing    -> one-time historical coverage/backfill, then seed the same suggestion queue
```

A single systemd oneshot + timer runs **normal mode** periodically. The exact clock time is chosen during implementation from live production timer truth so it does not collide with ingest. The design requirement is daily periodic execution, not a resident service.

`--bootstrap-existing` is run during W5B production rollout after verification. It is not scheduled as a second recurring job.

No LLM/evaluator work is added to `batch_ingest_from_spider.py` or the W3 hook.

---

## 5. Suggestion JSON is the queue

Do not introduce a new persistence layer.

The existing deterministic suggestion JSON gains one small nested state object:

```json
{
  "patch": { "...": "complete WikiPatch" },
  "policy_hint": "suggestion_only",
  "reason": "...",
  "suggested_content": "...",
  "evolution": {
    "status": "pending",
    "attempts": 0,
    "next_retry_at": null,
    "last_evaluated_at": null,
    "last_decision": null,
    "last_reason": null,
    "applied_patch_id": null
  }
}
```

Allowed evolution states:

```text
pending
retry
rejected
applied
superseded
```

Rules:

- missing `evolution` means legacy/pending and is initialized lazily;
- `pending` is eligible now;
- `retry` is eligible only when `next_retry_at <= now`;
- `rejected`, `applied`, `superseded` are terminal for that suggestion file;
- repeated runs update the same deterministic JSON file; no timestamp-spam artifacts;
- no history table is added.

The queue remains suggestion-oriented. Historical coverage must seed this same queue rather than inventing a separate backfill queue.

---

## 6. Two input paths: ongoing + historical

### 6.1 Ongoing path

Future W3 incremental article-backed suggestions keep the existing path:

```text
new ingest
  -> W3 local entity-buffer discovery
  -> EvidencePack / WikiPatch
  -> suggestion JSON for substantive existing-page change
  -> daily evolution worker
```

W3 remains no-network/non-blocking.

### 6.2 Historical path

Articles that were successfully ingested **before the W3 Wiki hook existed** will not naturally re-enter the ingest pipeline. W5B therefore includes a one-time historical bootstrap.

The authoritative historical eligible set is:

```text
ingestions.status == 'ok'
AND corresponding LightRAG doc_status == 'processed'
```

using the same source-specific URL/doc-id identity rules already implemented by `scripts/reconcile_ingestions.py`.

This set is the coverage denominator. W5B MUST NOT define historical coverage as "whatever happens to have an entity_buffer file", because that silently drops older successfully ingested content.

W1 batch generation remains supported by W5A, but W5B does not require Tavily/Databricks/W1 regeneration merely to recover historical coverage.

---

## 7. Historical Coverage Bootstrap

`python scripts/wiki_evolve.py --bootstrap-existing` performs a **one-time, idempotent-at-seeding-time** coverage pass before the daily timer is enabled.

It does not re-run article ingestion and does not modify the ingestion database.

### 7.1 Phase 0 — coverage audit

Before writing anything, compute and report:

```text
eligible_processed_ingestions
mapped_via_entity_buffer
mapped_via_lightrag_graph
unmapped_needing_llm_fallback
seeded_entity_jobs
no_wiki_entity
retry_unresolved
```

The report must reconcile to the eligible historical denominator. No eligible article may disappear from accounting.

### 7.2 Entity discovery priority

For each eligible historical article, discover Wiki entities using existing local artifacts in this order:

1. **existing canonical entity buffers** when available;
2. **LightRAG graph source mapping** when no usable buffer exists:
   - entity/relationship `source_id` chunk references from the current LightRAG stores;
   - chunk/full-doc -> URL/article mapping using the same mechanics already present in `wiki_generate_pages.py`;
3. **DeepSeek fallback only for still-unmapped articles**.

The graph path must enumerate all relevant locally available entities for the historical corpus; do **not** reuse `wiki_rank_entities.py`'s top-N presentation limit as a coverage cutoff.

### 7.3 Noise control without losing articles

Keep the normal W3 repeated-entity signal where possible:

```text
entity mentioned by >=2 distinct historical articles
  -> seed directly using local evidence
```

After those groups are formed, compute historical articles that are still not represented by any seeded entity job.

Only those uncovered articles use one bootstrap-only DeepSeek call against the locally stored article text. The fallback returns either:

```json
{"entities": ["up to 3 genuinely wiki-worthy entity names"]}
```

or

```json
{"entities": []}
```

An empty list means `no_wiki_entity`: the article was scanned and intentionally produced no Wiki entity. Model failure/timeout/invalid JSON means `retry_unresolved`; it is not silently dropped.

This is not a new entity-extraction framework. It is a narrow one-time fallback for concrete historical coverage gaps.

### 7.4 Seeding the existing W5A/W3 path

Historical entity groups are converted into the same article-backed `EvidencePack` / `WikiPatch` shape used by W3, with real local article titles and canonical refs.

For an **existing Wiki page**:

```text
historical EvidencePack
  -> normal W3-style MERGE_SOURCES + UPSERT_SECTION + SET_METADATA patch
  -> deterministic structured suggestion JSON
  -> W5B evolution worker later performs semantic rewrite
```

For a **missing Wiki page**, reuse W5A instead of inventing a second create renderer:

```text
historical EvidencePack
  -> existing canonical W3 CREATE_PAGE path creates the safe source-backed skeleton
  -> rebuild EvidencePack against that newly created page/digest
  -> immediately create the normal substantive suggestion for that page
  -> W5B evolution worker enriches/restructures it with the real article text
```

Thus a historical CREATE_PAGE is never the end of the process: it must have a corresponding queued semantic-evolution suggestion unless the bootstrap explicitly records a terminal `no_wiki_entity` outcome before page creation.

The bootstrap uses the existing deterministic suggestion writer/format. If implementation needs to expose the current private suggestion-write helper as a tiny public function to avoid format duplication, that small reuse seam is allowed; no new suggestion persistence abstraction is allowed.

### 7.5 Historical coverage exit condition

Bootstrap coverage is complete only when every eligible historical article is accounted for as exactly one of:

```text
represented by >=1 seeded Wiki entity job
no_wiki_entity (explicit DeepSeek fallback decision)
retry_unresolved (temporary failure; must be retried before bootstrap is declared complete)
```

`retry_unresolved > 0` means historical bootstrap is not complete.

The implementation may re-run the bootstrap during rollout if interrupted **before enabling the daily evolution timer**. Deterministic seeding must avoid timestamp-spam duplicates during that rollout window.

---

## 8. Local evidence hydration

Current W3 `EvidencePack` carries article identities but only minimal context. Before asking the model to rewrite an existing page, `wiki_evolve.py` hydrates article evidence from the existing local article corpus / SQLite database by canonical article identity.

Properties:

- read-only local access;
- no web calls;
- no new index/database;
- support the source types proven by live historical ingestion truth (at minimum current WeChat and RSS successful-ingestion rows if both are present in production);
- use the current article text/title fields discovered from live repository schema;
- rebuild promoted patch article `EvidenceRef` values with the **real local article title** while preserving canonical ref/provenance, so W3's placeholder hash-as-title never leaks into evolved Wiki frontmatter;
- bounded prompt size with a simple fixed cap documented in code; no token-budget framework;
- missing/unreadable required article evidence causes `RETRY`, never a fabricated rewrite.

The model sees:

1. current page text;
2. current page style (canonical or legacy);
3. hydrated article evidence with stable refs and real titles;
4. the original suggestion's subject/patch provenance;
5. strict structured-output instructions.

The old suggestion's `suggested_content` is not treated as authoritative content. The suggestion is an evidence trigger; W5B produces a fresh scoped patch against the latest page.

---

## 9. Reuse one existing LLM path

Use the existing production DeepSeek wrapper:

```text
lib.llm_deepseek.deepseek_model_complete
```

Do not add a provider abstraction, router, voting layer, or new paid service.

Normal evolution uses **one LLM call per suggestion attempt**.

The only additional LLM use allowed in W5B is the bootstrap-only fallback in §7.3 for historical articles that cannot be mapped to any entity using existing local artifacts.

Model/provider failure, timeout, invalid JSON, or ambiguous answer => `RETRY`.

---

## 10. One structured semantic decision

The normal evolution evaluator returns strict JSON with only three decisions:

```text
APPLY
RETRY
REJECT
```

For `APPLY`, it also returns one or more H2 section replacements/additions:

```json
{
  "decision": "APPLY",
  "reason": "short machine-auditable explanation",
  "sections": [
    {
      "heading": "Definition / Overview",
      "content": "replacement markdown with valid citations"
    }
  ]
}
```

No numeric score is required.

The prompt asks exactly these semantic questions:

1. Are factual additions/changes supported by the supplied evidence?
2. Does the rewrite avoid deleting still-correct important information without justification?
3. Is the candidate more accurate, more current, or materially clearer than the current page?
4. Does the rewrite avoid obvious contradiction with the supplied current page/evidence?

Decision policy:

```text
all clearly satisfied                          -> APPLY
explicitly unsupported / harmful / worse       -> REJECT
uncertain / insufficient evidence / model fail -> RETRY
```

`RETRY` never asks the user for review.

---

## 11. Citation/style contract

The worker does not invent a second Markdown renderer.

Before the LLM call it derives citation instructions from the target page:

- canonical page -> GFM `[^N]` citation form;
- legacy page -> existing legacy article citation form;
- article refs exposed to the model must map deterministically to the source representation the compiler will merge.

The model returns section body markdown only. It does not author frontmatter, source lists, or the whole page.

The worker converts model output into normal W5A operations:

```text
MERGE_SOURCES
UPSERT_SECTION (one or more)
SET_METADATA
```

There is still no `REPLACE_PAGE`, `DELETE_PAGE`, `DELETE_SECTION`, or generic destructive operation.

A large rewrite is represented as several scoped H2 `UPSERT_SECTION` operations, not a whole-page replacement.

---

## 12. Minimal compiler extension

W5A currently classifies any existing-page `UPSERT_SECTION` as `suggestion_only`.

W5B adds the smallest possible promotion seam:

```text
apply_patch(..., semantic_approved=False)
classify_patch(..., semantic_approved=False)
```

Default behavior is unchanged.

When `semantic_approved=True`:

- existing-page `UPSERT_SECTION` may become eligible for `auto_apply`;
- all existing W5A safety constraints still apply;
- metadata allowlist still applies;
- legacy provenance compatibility still applies;
- base digest must still match;
- page lock still applies;
- final candidate validation still runs;
- atomic write still applies;
- unknown/destructive operations remain rejected/suggestion-only as before.

This boolean is deliberately not generalized into a certificate subsystem.

Only `scripts/wiki_evolve.py` is expected to use `semantic_approved=True` in W5B.

---

## 13. Stale page / concurrency behavior

The worker always reads the latest current page before the LLM call and creates a fresh promoted WikiPatch with that page's current digest.

Therefore an old suggestion is used as an evidence trigger, not blindly re-applied against its historical `suggested_content`.

If the page changes during the LLM call or before the compiler lock is acquired:

```text
W5A base_digest conflict
  -> no write
  -> suggestion evolution state = retry
```

No separate rebase subsystem is created.

On the next retry the worker simply reads the newest page and asks the model again using the same evidence.

If the target page no longer exists or the suggestion is no longer meaningful, mark `superseded`.

---

## 14. Retry policy

No queue framework or scheduler library.

Use a tiny deterministic retry function:

```text
attempt 1 -> retry in 1 day
attempt 2 -> retry in 3 days
attempt 3+ -> retry in 7 days
```

`RETRY` can continue indefinitely at the 7-day cadence until:

- a later run returns APPLY;
- a later run returns REJECT;
- a newer state makes the suggestion superseded.

Historical bootstrap `retry_unresolved` items must be cleared before bootstrap is declared complete and before the daily timer is enabled.

---

## 15. REJECT and supersession

`REJECT` means the model found a clear semantic reason not to apply this evidence/patch attempt, such as unsupported factual rewrite or material regression.

A rejected suggestion is terminal for that deterministic suggestion file. New incoming evidence naturally creates a new patch/suggestion and can be evaluated independently.

`superseded` is used when the original suggestion no longer maps to a meaningful current-page evolution target.

Neither state requires human review.

---

## 16. Error handling

Expected outcomes are not Error Book failures:

- APPLY
- RETRY due to uncertainty/model timeout
- REJECT semantic decision
- superseded
- stale-base conflict
- historical `no_wiki_entity`

True implementation/integrity failures continue to use the existing Error Book where appropriate:

- malformed suggestion JSON that cannot deserialize WikiPatch;
- compiler candidate-integrity failure;
- filesystem corruption/write failure;
- impossible invariant violations.

Do not create another error database.

---

## 17. Post-apply behavior

Do not build a rollback subsystem.

The existing W5A compiler already validates the candidate before write and performs an atomic replace.

After `apply_patch(..., semantic_approved=True)` returns `applied`:

- mark the suggestion JSON `applied`;
- store `applied_patch_id`, timestamp, and decision reason;
- do not run a second post-write validation/rollback framework in W5B v1.

Standalone Wiki health remains a deployment/UAT regression check, not a per-patch transaction layer.

A later bad semantic conclusion is corrected by future evidence/evolution, not by maintaining a second transactional history store. Git/runtime backups remain the operational rollback mechanism.

---

## 18. CLI and runtime surface

Keep the script small.

Required CLI:

```text
python scripts/wiki_evolve.py
python scripts/wiki_evolve.py --dry-run
python scripts/wiki_evolve.py --limit N
python scripts/wiki_evolve.py --bootstrap-existing
python scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

Rules:

- normal `--dry-run` may call the evaluator but MUST NOT mutate Wiki pages or suggestion JSON state;
- bootstrap `--dry-run` performs the coverage audit/mapping without creating pages/suggestions; if implementation chooses to avoid paid/model calls in dry-run, unmapped articles are reported as `would_need_llm_fallback` rather than silently treated as covered;
- `--limit N` bounds normal evolution attempts for UAT/timer workload;
- bootstrap is one-time rollout work, not a recurring timer mode.

No HTTP API, MCP tool, UI, daemon socket, or admin console is added.

---

## 19. Tests

Behavior-anchor tests must prove at least:

### Queue/state

- suggestion without `evolution` initializes as pending during a normal run;
- terminal states are skipped;
- retry due-time logic follows 1d/3d/7d schedule;
- repeated runs mutate the same JSON file, not create duplicates;
- dry-run does not mutate suggestion state.

### Historical bootstrap / coverage

- historical denominator comes from successful ingestion truth, not entity-buffer filenames;
- rows not reconciled as LightRAG `processed` are excluded from eligible coverage;
- WeChat/RSS identity handling matches current reconciliation truth when both source types exist in fixtures/live schema;
- entity-buffer mapping is reused when available;
- LightRAG graph `source_id` / chunk mapping covers historical articles lacking buffers;
- graph discovery does not impose a top-N ranking cutoff;
- repeated-entity groups (>=2 distinct articles) seed without an LLM extraction call;
- an eligible historical article left uncovered invokes exactly one bootstrap fallback DeepSeek extraction call;
- fallback entity list seeds normal Wiki jobs; empty list records `no_wiki_entity`;
- fallback failure is `retry_unresolved`, never silently dropped;
- bootstrap accounting reconciles exactly to the eligible historical denominator;
- missing page gets canonical W5A/W3 create plus an immediate substantive evolution suggestion, not create-only terminal behavior;
- bootstrap dry-run mutates nothing.

### Evidence

- article evidence hydrates from local corpus read-only;
- promoted article EvidenceRefs use real local titles, not hash placeholders;
- missing required evidence -> RETRY;
- no Tavily/web dependency is introduced for historical hydration/evolution.

### Evaluator

- valid strict APPLY JSON parses;
- RETRY and REJECT parse;
- malformed/timeout model response -> RETRY;
- exactly one DeepSeek completion is used per normal evolution attempt.

### Promotion

- default W5A `UPSERT_SECTION` remains suggestion-only;
- `semantic_approved=True` permits scoped substantive apply;
- multiple H2 replacements can apply without full-page replacement;
- `created` remains immutable;
- invalid citation/candidate remains rejected even when semantic-approved;
- stale digest remains conflict even when semantic-approved;
- legacy existing pages preserve legacy citation style.

### Worker end-to-end

- APPLY -> fresh promoted patch -> compiler applied -> suggestion state `applied`;
- RETRY -> no page mutation -> next retry persisted;
- REJECT -> no page mutation -> terminal rejected;
- conflict -> no page mutation -> retry;
- target superseded -> terminal superseded;
- original historical `suggested_content` is never blindly applied.

### Regression

- full W5A suite remains green;
- `tests/unit/test_ingest_from_db_orchestration.py` remains green;
- W3 hook stays no-network/non-blocking.

---

## 20. Production UAT and historical bootstrap rollout

Because W5B adds an autonomous networked worker, changes existing-page apply policy, and introduces historical corpus backfill, production UAT is required.

Use existing Aliyun deployment discipline and isolated Wiki roots first.

Minimum sequence:

1. confirm current production host/path/venv/timers from live truth;
2. run **read-only historical coverage recon** on production and record:
   - successful/processed historical denominator;
   - buffer-mapped count;
   - graph-mapped count;
   - still-unmapped count;
3. confirm DeepSeek wrapper can make one real structured evaluator call under production environment;
4. isolated Wiki root with real production evidence: APPLY path succeeds through shared compiler;
5. controlled RETRY -> no page write, state persists;
6. controlled REJECT -> no page write;
7. stale-base conflict -> no overwrite, retry state;
8. invalid candidate remains blocked despite semantic approval;
9. historical bootstrap fixture proves all three discovery paths where production data permits: buffer, graph-only, fallback-unmapped;
10. deploy oneshot/timer **disabled**;
11. run production `--bootstrap-existing --dry-run`; verify exact accounting and no mutation;
12. run production `--bootstrap-existing` to completion; require `retry_unresolved == 0` and record pages/suggestions seeded;
13. run a controlled manual normal worker cycle with small `--limit` and verify real seeded historical suggestion can reach semantic evolution safely;
14. confirm production W3 ingest service remains unchanged/healthy;
15. run standalone Wiki health / index consistency regression;
16. only then enable the daily normal-mode timer.

Do not manufacture fake knowledge into production Wiki merely to prove UAT. Isolated Wiki roots may use real production article evidence.

---

## 21. Acceptance gates

### Gate A — Minimal architecture

One evolution script + small W5A compiler extension + one systemd oneshot/timer. Historical coverage is a mode of the same script. No new DB/daemon/framework/backfill service.

### Gate B — Zero-human state machine

Every due suggestion autonomously converges toward `applied`, `rejected`, `retry`, or `superseded`; no approval queue is required.

### Gate C — Historical corpus coverage

Every successfully ingested historical article (`ingestions=ok` + LightRAG processed) is accounted for and either represented by at least one Wiki evolution job or explicitly classified `no_wiki_entity`. No history is silently skipped merely because it predates W3 or lacks an entity-buffer file.

### Gate D — Local evidence grounding

Autonomous evolution uses real locally stored article evidence and real titles; missing evidence fails to RETRY rather than hallucinating.

### Gate E — One-call normal semantic decision

One existing DeepSeek call per normal evolution attempt returns APPLY/RETRY/REJECT and scoped H2 rewrites; malformed/uncertain output retries. Bootstrap-only entity fallback is allowed solely for historical articles that existing local artifacts cannot map.

### Gate F — Shared compiler remains authoritative

Semantic approval only relaxes the existing-page `UPSERT_SECTION` policy gate. Digest, lock, citation validation, metadata safety, legacy compatibility, Error Book, and atomic write remain authoritative.

### Gate G — No full-page destructive rewrite

Large semantic evolution is represented by multiple scoped H2 operations. No generic whole-page replace/delete is introduced.

### Gate H — W3 isolation preserved

No DeepSeek/evaluator/network work is added to the ingest hook.

### Gate I — Regression + production UAT

W5A tests remain green; historical bootstrap accounting closes with zero unresolved articles; controlled production evaluator/apply/retry/reject/conflict paths pass; ingest remains healthy; daily timer is enabled only after bootstrap and bounded manual UAT are clean.

### Gate J — Ponytail final review

Before completion, a fresh review must explicitly ask:

- can any new module be deleted and existing code reused instead?
- is any abstraction serving only one implementation unnecessarily?
- did a queue/database/framework appear despite this design?
- did historical coverage accidentally become a second ingest system?
- did query-eval/navigation/W6 scope creep in?
- is the worker still understandable as one small personal-KB evolution loop?

Any unnecessary subsystem is removed before PASS.

---

## 22. Exit state

W5B is complete when both old and new knowledge enter one autonomous Wiki maintenance loop:

```text
HISTORICAL (one-time rollout)
all successful processed ingestions
  -> buffer / LightRAG graph discovery
  -> DeepSeek entity fallback only for unmapped articles
  -> every article accounted for
  -> seed same deterministic Wiki suggestions

ONGOING
new articles
  -> W3 creates deterministic structured suggestion

BOTH
suggestion JSON
  -> daily wiki_evolve.py reads local article evidence
  -> one DeepSeek semantic decision
  -> APPLY | RETRY | REJECT
  -> APPLY builds a fresh scoped patch against latest page
  -> W5A compiler runs with semantic_approved=True
  -> digest/lock/lint/atomic safety remains intact
  -> suggestion state updates automatically
```

The user is not expected to review or maintain suggestion files, and historical articles are not permanently excluded merely because they will never pass through the ingest hook again.

W6 may later add navigation/search/query-aware evaluation only after this small autonomous loop is proven useful in production.
