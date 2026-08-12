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
- W3 ingest remains non-blocking and must not gain LLM/network work.

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
- no W6 navigation graph, `wiki_search`, `wiki_read`, N-hop traversal, retrieval fusion, or query-feedback loop.

Existing components must be reused before new abstractions are introduced.

The minimum new runtime shape is:

```text
W1 / W3
  -> existing deterministic suggestion JSON
  -> scripts/wiki_evolve.py (oneshot)
  -> one DeepSeek call
  -> APPLY | RETRY | REJECT
  -> existing W5A compiler
```

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

W5B MUST extend this compiler rather than create a second write path.

---

## 4. One new runtime component

Add one oneshot script:

```text
scripts/wiki_evolve.py
```

It scans existing:

```text
kb/wiki/_suggestions/*.json
```

and processes due suggestions.

A single systemd oneshot + timer runs it periodically. The exact clock time is chosen during implementation from live production timer truth so it does not collide with ingest. The design requirement is **daily periodic execution**, not a resident service.

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

---

## 6. Scope of autonomous consumption

W5B v1 is optimized for the ongoing production evolution path: **W3 incremental article-backed suggestions**.

Required autonomous path:

```text
trigger == w3_incremental
article evidence -> local evidence hydration -> semantic rewrite -> W5A apply
```

W1 batch generation remains supported by W5A. W5B is not required to autonomously consume every historical W1 suggestion with web/builtin evidence.

If a suggestion cannot be evaluated from locally available evidence without introducing new web retrieval, it is `retry` or `rejected` according to the semantic result. W5B MUST NOT add Tavily or another new retrieval stage merely to consume old suggestions.

This is a deliberate Ponytail scope cut: W3 is the continuous maintenance mechanism; W1 is the bootstrap/batch authoring mechanism.

---

## 7. Local evidence hydration

Current W3 `EvidencePack` carries article identities but only minimal context. Before asking the model to rewrite an existing page, `wiki_evolve.py` hydrates article evidence from the **existing local article corpus / SQLite database** by canonical 10-character article hash.

Properties:

- read-only local access;
- no web calls;
- no new index/database;
- use the current article text/title fields discovered from live repository schema;
- bounded prompt size with a simple fixed cap documented in code; no token-budget framework;
- missing/unreadable required article evidence causes `RETRY`, never a fabricated rewrite.

The model sees:

1. current page text;
2. current page style (canonical or legacy);
3. hydrated article evidence with stable article hashes;
4. the original suggestion's subject/patch provenance;
5. strict structured-output instructions.

---

## 8. Reuse one existing LLM path

Use the existing production DeepSeek wrapper:

```text
lib.llm_deepseek.deepseek_model_complete
```

Do not add a provider abstraction, router, voting layer, or new paid service.

W5B uses **one LLM call per evolution attempt**.

Model/provider failure, timeout, invalid JSON, or ambiguous answer => `RETRY`.

The W5B prompt asks the model to make one combined semantic decision and, on success, return the scoped rewrite plan.

---

## 9. One structured semantic decision

The evaluator returns strict JSON with only three decisions:

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
all clearly satisfied                         -> APPLY
explicitly unsupported / harmful / worse      -> REJECT
uncertain / insufficient evidence / model fail -> RETRY
```

`RETRY` never asks the user for review.

---

## 10. Citation/style contract

The worker does not invent a second Markdown renderer.

Before the LLM call it derives the citation instructions from the target page:

- canonical page -> GFM `[^N]` citation form;
- legacy page -> existing legacy article citation form;
- article hashes exposed to the model must map deterministically to the source representation the compiler will merge.

The model returns section body markdown only. It does **not** author frontmatter, source lists, or the whole page.

The worker converts model output into normal W5A operations:

```text
MERGE_SOURCES
UPSERT_SECTION (one or more)
SET_METADATA
```

There is still no `REPLACE_PAGE`, `DELETE_PAGE`, `DELETE_SECTION`, or generic destructive operation.

A large rewrite is represented as several scoped H2 `UPSERT_SECTION` operations, not a whole-page replacement.

---

## 11. Minimal compiler extension

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

## 12. Stale page / concurrency behavior

The worker always reads the **latest current page before the LLM call** and creates a fresh promoted WikiPatch with that page's current digest.

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

## 13. Retry policy

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

This matches the user's zero-maintenance requirement without creating an operational backlog that requires human action.

---

## 14. REJECT and supersession

`REJECT` means the model found a clear semantic reason not to apply this evidence/patch attempt, such as unsupported factual rewrite or material regression.

A rejected suggestion is terminal for that deterministic suggestion file. New incoming evidence naturally creates a new patch/suggestion and can be evaluated independently.

`superseded` is used when the original suggestion no longer maps to a meaningful current-page evolution target (for example, target removed/replaced by a newer canonical path).

Neither state requires human review.

---

## 15. Error handling

Expected outcomes are not Error Book failures:

- APPLY
- RETRY due to uncertainty/model timeout
- REJECT semantic decision
- superseded
- stale-base conflict

True implementation/integrity failures continue to use the existing Error Book where appropriate:

- malformed suggestion JSON that cannot deserialize WikiPatch;
- compiler candidate-integrity failure;
- filesystem corruption/write failure;
- impossible invariant violations.

Do not create another error database.

---

## 16. Post-apply behavior

Do not build a rollback subsystem.

The existing W5A compiler already validates the candidate before write and performs an atomic replace.

After `apply_patch(..., semantic_approved=True)` returns `applied`:

- mark the suggestion JSON `applied`;
- store `applied_patch_id`, timestamp, decision reason;
- optionally perform the existing lightweight target health/lint smoke if it is already exposed cheaply;
- do not run a new snapshot lifecycle.

A later bad semantic conclusion is corrected by future evidence/evolution, not by maintaining a second transactional history store. Git/runtime backups remain the operational rollback mechanism.

---

## 17. CLI and runtime surface

Keep the script small.

Required CLI:

```text
python scripts/wiki_evolve.py
python scripts/wiki_evolve.py --dry-run
python scripts/wiki_evolve.py --limit N
```

`--dry-run` may call the evaluator but must not mutate Wiki pages; it may report decisions without changing suggestion state unless explicitly documented for testing.

`--limit N` exists only to bound controlled runs/UAT and timer workload.

No HTTP API, MCP tool, UI, daemon socket, or admin console is added.

---

## 18. Tests

Behavior-anchor tests must prove at least:

### Queue/state

- suggestion without `evolution` initializes as pending;
- terminal states are skipped;
- retry due-time logic follows 1d/3d/7d schedule;
- repeated runs mutate the same JSON file, not create duplicates.

### Evidence

- W3 article hashes hydrate from local corpus read-only;
- missing required evidence -> RETRY;
- no Tavily/web/network dependency is introduced for evidence hydration.

### Evaluator

- valid strict APPLY JSON parses;
- RETRY and REJECT parse;
- malformed/timeout model response -> RETRY;
- exactly one DeepSeek completion is used per attempt.

### Promotion

- default W5A `UPSERT_SECTION` remains suggestion-only;
- `semantic_approved=True` permits scoped substantive apply;
- multiple H2 replacements can apply without full-page replacement;
- `created` remains immutable;
- invalid citation/candidate remains rejected even when semantic-approved;
- stale digest remains conflict even when semantic-approved;
- legacy existing pages preserve legacy citation style.

### Worker end-to-end

- APPLY -> promoted patch -> compiler applied -> suggestion state `applied`;
- RETRY -> no page mutation -> next retry persisted;
- REJECT -> no page mutation -> terminal rejected;
- conflict -> no page mutation -> retry;
- target superseded -> terminal superseded.

### Regression

- full W5A suite remains green;
- `tests/unit/test_ingest_from_db_orchestration.py` remains green;
- W3 hook stays no-network/non-blocking.

---

## 19. Production UAT

Because W5B adds an autonomous networked worker and changes existing-page apply policy, production UAT is required.

Use the existing Aliyun deployment discipline and isolated Wiki roots first.

Minimum UAT:

1. confirm current production host/path/venv/timers from live truth;
2. confirm DeepSeek wrapper can make one real structured evaluator call under the production environment;
3. real production W3 suggestion/article hashes + isolated Wiki root -> APPLY path succeeds through shared compiler;
4. controlled RETRY model result -> no page write, state persists;
5. controlled REJECT -> no page write;
6. stale-base conflict -> no overwrite, retry state;
7. invalid candidate remains blocked despite semantic approval;
8. production W3 ingest service remains unchanged/healthy;
9. deploy oneshot/timer disabled first, run one controlled manual production worker cycle with a small `--limit`;
10. only after the controlled cycle is clean, enable the daily timer.

Do not manufacture fake knowledge into the production Wiki merely to prove UAT. Isolated Wiki roots may use real production article evidence.

---

## 20. Acceptance gates

### Gate A — Minimal architecture

One evolution script + small W5A compiler extension + one systemd oneshot/timer. No new DB/daemon/framework.

### Gate B — Zero-human state machine

Every suggestion autonomously converges toward `applied`, `rejected`, `retry`, or `superseded`; no approval queue is required.

### Gate C — Local evidence grounding

W3 autonomous evolution uses real locally stored article evidence by canonical hash; missing evidence fails to RETRY rather than hallucinating.

### Gate D — One-call semantic decision

One existing DeepSeek call per attempt returns APPLY/RETRY/REJECT and scoped H2 rewrites; malformed/uncertain output retries.

### Gate E — Shared compiler remains authoritative

Semantic approval only relaxes the existing-page `UPSERT_SECTION` policy gate. Digest, lock, citation validation, metadata safety, legacy compatibility, Error Book, and atomic write remain authoritative.

### Gate F — No full-page destructive rewrite

Large semantic evolution is represented by multiple scoped H2 operations. No generic whole-page replace/delete is introduced.

### Gate G — W3 isolation preserved

No DeepSeek/evaluator/network work is added to the ingest hook.

### Gate H — Regression + production UAT

W5A tests remain green; controlled production evaluator/apply/retry/reject/conflict paths pass; ingest remains healthy; daily timer is enabled only after manual bounded UAT.

### Gate I — Ponytail final review

Before completion, a fresh review must explicitly ask:

- can any new module be deleted and existing code reused instead?
- is any abstraction serving only one implementation unnecessarily?
- did a queue/database/framework appear despite this design?
- did query-eval/navigation/W6 scope creep in?
- is the worker still understandable as one small personal-KB evolution loop?

Any unnecessary subsystem is removed before PASS.

---

## 21. Exit state

W5B is complete when the ongoing Wiki maintenance path is:

```text
new articles
  -> W3 creates deterministic structured suggestion
  -> daily wiki_evolve.py reads local article evidence
  -> one DeepSeek semantic decision
  -> APPLY | RETRY | REJECT
  -> APPLY uses the existing W5A compiler with semantic_approved=True
  -> digest/lock/lint/atomic safety remains intact
  -> suggestion state updates automatically
```

The user is not expected to review or maintain suggestion files.

W6 may later add navigation/search/query-aware evaluation only after this small autonomous loop is proven useful in production.
