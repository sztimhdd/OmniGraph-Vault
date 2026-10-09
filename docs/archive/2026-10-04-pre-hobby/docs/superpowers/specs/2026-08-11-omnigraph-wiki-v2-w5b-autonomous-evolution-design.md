# OmniGraph Wiki v2 — W5B Autonomous Evolution Design

**Status:** AUTHORITATIVE DESIGN CONTRACT — implementation not started  
**Date:** 2026-08-11  
**Depends on:** W5A FINAL PASS through `23eb430df195a6fc6bc8e2afe65fcdc2ba44da13`  
**Next phase:** W6 Agent-Native Wiki Navigation

---

## 1. Goal

W5B makes the Wiki maintain itself for a personal knowledge base, with no normal human-review queue.

It must solve **two** problems together:

1. **Autonomous evolution:** substantive existing-page changes can be evaluated by one LLM call and safely auto-applied through the W5A compiler.
2. **Complete article coverage:** articles that were already successfully ingested before W3 existed must not remain invisible forever, and current ingestion sources must not continue creating new Wiki blind spots.

User policy:

- high autonomy;
- no routine manual approval;
- uncertainty/model failure => automatic retry;
- clear semantic failure => reject automatically;
- W3 ingest remains no-network/non-blocking;
- all successfully ingested Wiki-eligible articles must be accounted for.

W5B is intentionally small. It is not a general knowledge-evolution platform.

---

## 2. Ponytail / YAGNI constraints

Do **not** add:

- EvaluationCertificate subsystem;
- queue/history database;
- event bus or resident daemon;
- evaluator ensemble or voting;
- generic provider registry;
- per-patch affected-query/guard-query framework;
- risk-scoring framework;
- snapshot/rollback database;
- generalized rule engine;
- second historical-ingest service;
- W6 navigation/search/query-feedback work.

Reuse current repo truth and current W5A compiler.

Minimum runtime shape:

```text
HISTORICAL successful articles -- one-time bootstrap --\
                                                        +--> existing suggestion JSON
ONGOING successful articles ---- W3 source-aware hook --/
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

Historical bootstrap is a mode of `wiki_evolve.py`, not another subsystem.

---

## 3. Repo truth and the coverage bug

### 3.1 Successful article truth

The current article-ingestion SoT is the `ingestions` table plus LightRAG doc status.

Current schema makes ingestion identity source-aware:

```text
(article_id, source)
source in {wechat, rss}
```

A historically eligible article is:

```text
ingestions.status == 'ok'
AND corresponding LightRAG kv_store_doc_status == 'processed'
```

using the existing source-specific URL/doc-id rules from `scripts/reconcile_ingestions.py`.

### 3.2 Current W3 blind spot

`batch_ingest_from_spider.py` processes both WeChat and RSS in the same production pipeline, but current W3 receives bare URL-derived hashes and `build_w3_evidence_packs()` validates them only against:

```sql
SELECT 1 FROM articles WHERE content_hash=?
```

Therefore W5B MUST repair W3 article resolution so current RSS successes are not silently discarded.

### 3.3 Scope boundary

The historical coverage gate in W5B is for the **article ingestion system represented by `ingestions`**.

`batch_ingest_github.py` is a separate curated repository-ingestion path backed by `entity_registry.json`, not an `ingestions` article source. It is not silently reclassified as an article source in W5B. Existing W1/LightRAG knowledge may still use that corpus; broadening autonomous coverage to non-article registries is a separate future decision if needed.

---

## 4. Existing foundations to reuse

W5A already provides:

- complete serialized WikiPatch suggestions;
- deterministic suggestion filenames;
- base-digest optimistic concurrency;
- per-page flock;
- canonical/legacy rendering compatibility;
- evidence validation;
- pre-write candidate validation;
- Error Book;
- atomic writes;
- no generic whole-page replace/delete.

Existing repo code also provides:

- `scripts/reconcile_ingestions.py` — WeChat/RSS successful-ingestion reconciliation;
- `kb/wiki_compiler/adapters/w3.py` — article/entity-buffer -> EvidencePack/WikiPatch;
- `scripts/wiki_rank_entities.py` — LightRAG entity/relationship `source_id` chunk references;
- `scripts/wiki_generate_pages.py` — existing chunk/full-doc/URL -> article mapping mechanics;
- `lib.llm_deepseek.deepseek_model_complete` — production LLM wrapper.

W5B extends these; it does not build alternatives.

---

## 5. One runtime script, two modes

Add:

```text
scripts/wiki_evolve.py
```

Modes:

```text
normal                 process due suggestion JSONs
--bootstrap-existing   one-time historical coverage/backfill
```

CLI:

```text
python scripts/wiki_evolve.py
python scripts/wiki_evolve.py --dry-run
python scripts/wiki_evolve.py --limit N
python scripts/wiki_evolve.py --bootstrap-existing
python scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

One systemd oneshot/timer runs **normal mode daily**. Timer time is selected from live production timer truth during deployment to avoid collision with ingest.

`--bootstrap-existing` is rollout-only and is never put on a second timer.

No evaluator/network work is added inside the W3 ingest hook.

---

## 6. Article identity and source-aware W3

### 6.1 Canonical Wiki article ref

For Wiki evidence, current WeChat/RSS article identity remains the canonical 10-char lowercase URL identity:

```text
md5(url)[:10]
```

The `source` dimension is carried alongside the ref while resolving local data, because `(article_id, source)` is the ingestion identity.

Implementation should use a simple tuple/dict internally; do not create a new public identity framework solely for this.

### 6.2 Source-specific resolver

A small shared local resolver must be the single place that maps source-aware article evidence to local data:

```text
wechat -> articles
rss    -> rss_articles
```

It returns at minimum:

```text
source
article_id
canonical_ref = md5(url)[:10]
url
title
body/summary usable for hydration
```

The exact body/title column fallback order is discovered from live schema and then behavior-tested.

If standalone Wiki health builds a known-article-ref corpus, it must recognize the same source-aware article identities so valid RSS citations are not treated as foreign merely because they are not in `articles.content_hash`.

No new evidence type is introduced for RSS.

### 6.3 Ongoing W3 success set

Current W3 computes hashes from all candidate rows after the batch. W5B tightens this to the actual successful set.

The W3 hook must receive only source-aware articles that reached:

```text
status == 'ok'
AND LightRAG document confirmed processed
```

for that batch.

Failed/skipped/candidate-only rows must not seed Wiki work.

### 6.4 Ongoing-source coverage audit

At implementation/deployment recon, run:

```sql
SELECT DISTINCT source FROM ingestions
```

Every live source must be either:

1. supported by the W3 local source resolver and tested end-to-end; or
2. explicitly proven non-Wiki-eligible and documented.

For the current schema, WeChat and RSS are required supported paths.

An unknown live source is a completion blocker, not a silent skip.

---

## 7. Suggestion JSON remains the queue

No new persistence layer.

Existing deterministic suggestion JSON gains only:

```json
"evolution": {
  "status": "pending",
  "attempts": 0,
  "next_retry_at": null,
  "last_evaluated_at": null,
  "last_decision": null,
  "last_reason": null,
  "applied_patch_id": null
}
```

States:

```text
pending
retry
rejected
applied
superseded
```

Rules:

- missing `evolution` => lazily treated as pending;
- retry runs only when due;
- rejected/applied/superseded are terminal for that suggestion file;
- repeated attempts update the same deterministic file;
- no history table.

Historical bootstrap seeds this same queue.

---

## 8. Historical Coverage Bootstrap

`wiki_evolve.py --bootstrap-existing` performs one idempotent-at-seeding-time historical pass before the daily timer is enabled.

It does **not** rerun ingestion and does not modify the ingestion database.

### 8.1 Coverage denominator

Build the denominator from source-aware `ingestions.status='ok'` rows whose corresponding LightRAG doc status is `processed`.

Report at minimum:

```text
eligible_processed_ingestions
mapped_via_entity_buffer
mapped_via_lightrag_graph
unmapped_needing_llm_fallback
seeded_entity_jobs
no_wiki_entity
retry_unresolved
```

Every eligible article must reconcile into the accounting. Entity-buffer file count is never used as the denominator.

### 8.2 Discovery order

For each historical article:

1. reuse canonical entity buffer if available;
2. otherwise reuse LightRAG entity/relationship `source_id` chunk mapping and existing chunk/full-doc -> URL/article mechanics;
3. only if still unmapped, use one bootstrap-only DeepSeek entity extraction call.

The graph path must enumerate all relevant local entities. `wiki_rank_entities.py` top-N output is a presentation tool and MUST NOT be used as a coverage cutoff.

### 8.3 Noise control without silent loss

First preserve W3's repeated-entity signal:

```text
entity observed in >=2 distinct eligible historical articles
  -> directly seed a Wiki entity job
```

Then calculate eligible articles still represented by **zero** seeded entity jobs.

Only those uncovered articles receive the bootstrap fallback call against locally stored text.

Strict fallback output:

```json
{"entities": ["up to 3 genuinely wiki-worthy entity names"]}
```

or:

```json
{"entities": []}
```

Outcomes:

- names returned -> merge them into historical entity groups;
- empty list -> `no_wiki_entity`;
- timeout/model failure/invalid JSON -> `retry_unresolved`.

No article is silently dropped.

### 8.4 Seed through W5A/W3, not a new renderer

For an existing Wiki page:

```text
historical source-aware EvidencePack
 -> normal W3-style substantive WikiPatch
 -> deterministic structured suggestion
```

For a missing Wiki page:

```text
historical EvidencePack
 -> existing W5A/W3 canonical CREATE_PAGE
 -> rebuild EvidencePack against the new page/digest
 -> immediately seed a substantive suggestion
```

A historical CREATE_PAGE is therefore not the terminal semantic result; the page still enters the evolution queue.

Use the existing suggestion JSON writer/format. Exposing the current private helper as one tiny reuse seam is acceptable if necessary; creating a new suggestion repository/manager class is not.

### 8.5 Bootstrap completion

Every eligible historical article must end in exactly one accounting class:

```text
represented by >=1 seeded Wiki entity job
no_wiki_entity
retry_unresolved
```

Bootstrap is **not complete while `retry_unresolved > 0`**.

Interrupted rollout may rerun bootstrap before timer enablement. Deterministic seeding must avoid duplicate timestamp artifacts.

---

## 9. Local evidence hydration

Before semantic evolution, hydrate every suggestion from the source-aware local resolver.

Properties:

- read-only local corpus access;
- supports current WeChat and RSS sources;
- no Tavily/web lookup;
- real title replaces W3 hash-as-title placeholder;
- stable canonical 10-char article refs are preserved;
- bounded prompt using one simple documented character/token cap, not a budget framework;
- missing required evidence => RETRY, never fabricate.

The model sees:

1. latest current Wiki page;
2. current citation style;
3. local evidence text with source/ref/real title;
4. suggestion/patch provenance;
5. strict output instructions.

Historical `suggested_content` is only an old artifact; it is never blindly applied.

---

## 10. One DeepSeek semantic decision per normal attempt

Reuse:

```text
lib.llm_deepseek.deepseek_model_complete
```

No provider abstraction/router/voting.

Normal evolution makes exactly **one** LLM call per attempt.

Strict result:

```text
APPLY
RETRY
REJECT
```

For APPLY:

```json
{
  "decision": "APPLY",
  "reason": "short explanation",
  "sections": [
    {"heading": "Definition / Overview", "content": "scoped markdown with citations"}
  ]
}
```

The prompt asks only:

1. Are factual additions/changes supported by supplied evidence?
2. Does the rewrite avoid unjustified deletion of still-correct important information?
3. Is it more accurate/current/materially clearer?
4. Does it avoid obvious contradiction with current page/evidence?

Policy:

```text
clearly safe and useful                    -> APPLY
clearly unsupported/harmful/worse          -> REJECT
uncertain/insufficient/model/format failure -> RETRY
```

Bootstrap-only entity fallback in §8 is the only allowed additional W5B LLM use.

---

## 11. Scoped rewrite and citations

The LLM returns **section bodies only**. It does not write frontmatter, sources lists, or a whole page.

Worker converts APPLY output to normal W5A operations:

```text
MERGE_SOURCES
UPSERT_SECTION (one or more)
SET_METADATA
```

Citation instructions match the current target style:

- canonical -> GFM `[^N]`;
- legacy -> existing legacy article citation style.

No `REPLACE_PAGE`, `DELETE_PAGE`, `DELETE_SECTION`, generic delete/source subtraction, or whole-page rewrite is added.

A large rewrite is several scoped H2 UPSERT_SECTION operations.

---

## 12. Minimal W5A compiler extension

Add only:

```text
apply_patch(..., semantic_approved=False)
classify_patch(..., semantic_approved=False)
```

Default behavior remains W5A-compatible.

With `semantic_approved=True`, existing-page UPSERT_SECTION may become auto-apply eligible, but **all** current W5A safety remains authoritative:

- source/evidence validation;
- metadata allowlist (`created` immutable);
- legacy compatibility;
- base digest;
- per-page lock;
- final candidate validation;
- atomic write;
- destructive/unknown operation restrictions.

Only `wiki_evolve.py` should pass this flag in W5B.

Do not replace this boolean with a certificate framework.

---

## 13. Concurrency, retry, terminal states

Worker reads the latest page before the LLM call and creates a fresh promoted patch with the latest digest.

If page changes before apply:

```text
W5A conflict -> no write -> retry
```

No rebase subsystem. Next retry simply rereads the page and asks again.

Retry schedule:

```text
attempt 1 -> +1 day
attempt 2 -> +3 days
attempt 3+ -> +7 days
```

`RETRY` may continue indefinitely without human action.

`REJECT` is terminal for that deterministic suggestion. New evidence may create a new suggestion later.

`superseded` is terminal when the target/path/evidence trigger is no longer meaningful.

Expected APPLY/RETRY/REJECT/superseded/conflict/no_wiki_entity outcomes are not Error Book failures. True malformed-state/compiler/filesystem/invariant failures continue using the existing Error Book.

---

## 14. Dry-run and post-apply behavior

`--dry-run` may evaluate but MUST NOT mutate Wiki pages or suggestion JSON.

Bootstrap dry-run performs coverage/mapping only. It may report `would_need_llm_fallback` instead of paying for fallback calls.

Do not build a second rollback/validation transaction system. W5A already validates before atomic write.

After successful semantic apply:

- mark same suggestion JSON `applied`;
- store applied patch id, timestamp, decision reason.

Standalone Wiki health remains deployment/UAT regression evidence, not a per-patch rollback engine.

---

## 15. Required behavior tests

### Article coverage / ongoing W3

- current live/fixture sources are enumerated from `ingestions.source`;
- WeChat success resolves through `articles`;
- RSS success resolves through `rss_articles`;
- W3 receives only actual status=ok + doc-confirmed current-batch articles;
- failed/skipped rows do not seed W3;
- both WeChat and RSS can produce EvidencePacks/suggestions;
- source-aware canonical refs stay deterministic;
- known-citation corpus/health recognizes valid refs for both required sources;
- unknown live ingestion source cannot silently disappear.

### Historical bootstrap

- denominator = successful + LightRAG-processed ingestions, not buffer files;
- source-specific reconciliation matches WeChat/RSS rules;
- buffer path reused when available;
- graph/chunk mapping covers historical article without buffer;
- no top-N graph cutoff;
- >=2-article entity group seeds without extraction LLM;
- uncovered article makes exactly one fallback extraction call;
- fallback names seed normal jobs;
- fallback empty => no_wiki_entity;
- fallback failure => retry_unresolved;
- full accounting equals denominator;
- missing page gets canonical create **and** immediate substantive suggestion;
- rerun does not create duplicate timestamp suggestions;
- bootstrap dry-run mutates nothing.

### Queue/evolution

- missing evolution state => pending;
- terminal states skipped;
- retry schedule 1d/3d/7d;
- repeated run updates same JSON;
- real titles replace hash placeholders;
- missing local evidence => RETRY;
- APPLY/RETRY/REJECT strict parsing;
- malformed/timeout => RETRY;
- one DeepSeek call per normal attempt.

### Promotion safety

- normal W5A UPSERT_SECTION remains suggestion-only;
- semantic_approved permits scoped substantive update;
- multiple H2 updates do not become whole-page replace;
- created remains immutable;
- invalid citation/candidate still rejects;
- stale digest still conflicts;
- legacy style preserved.

### Regression

- full W5A suite green;
- `tests/unit/test_ingest_from_db_orchestration.py` green with new source-aware success contract;
- W3 remains no-network/non-blocking;
- no W6/query-eval scope.

---

## 16. Production rollout / UAT

Required sequence:

1. rediscover live host/repo/venv/timers/schema;
2. `SELECT DISTINCT source FROM ingestions` and prove every live article source has an explicit resolver;
3. verify current W3 blind-spot baseline, including RSS if present;
4. deploy code with new daily evolution timer **disabled**;
5. read-only historical coverage recon: denominator, buffer mapped, graph mapped, fallback needed;
6. run `--bootstrap-existing --dry-run`; prove zero mutation and exact accounting;
7. isolated Wiki root using real production evidence:
   - WeChat path;
   - RSS path;
   - buffer mapping;
   - graph-only mapping where available;
   - fallback-unmapped fixture;
   - semantic APPLY/RETRY/REJECT;
   - stale conflict;
   - invalid candidate blocked;
8. confirm one real DeepSeek structured evaluation works in production environment;
9. run production `--bootstrap-existing` to completion;
10. require `retry_unresolved == 0` before declaring historical coverage closed;
11. record seeded pages/suggestions and historical denominator reconciliation;
12. run bounded manual normal worker `--limit N` and prove at least one real historical seeded suggestion can safely evolve;
13. observe/execute one bounded ongoing W3 cycle and prove current supported ingestion sources no longer disappear at W3 resolution;
14. standalone Wiki health/index regression;
15. confirm ingest service healthy and W3 hook remains bounded/non-blocking;
16. only then enable daily normal-mode systemd timer.

Do not manufacture fake knowledge into production Wiki merely for UAT; isolated roots may use real production evidence.

---

## 17. Acceptance gates

### Gate A — Ponytail-minimal architecture

One evolution script + small source-aware W3 correction + small W5A semantic flag + one normal-mode timer. No new DB/daemon/framework/backfill service.

### Gate B — Historical article coverage

Every eligible historical article is accounted for as:

```text
represented by >=1 seeded Wiki entity job
OR no_wiki_entity
```

Bootstrap cannot PASS with unresolved articles.

### Gate C — Ongoing article coverage

Every live Wiki-eligible `ingestions.source` has an explicit source-aware W3 resolver and behavior test. Current required WeChat/RSS successes reach W3; failed/skipped rows do not.

### Gate D — Zero-human autonomous evolution

Due suggestions converge automatically to applied/rejected/retry/superseded. No human approval queue.

### Gate E — Local grounding

Semantic evolution uses real locally stored source-aware article evidence and real titles. Missing evidence retries rather than hallucinating.

### Gate F — One-call normal semantic decision

Exactly one existing DeepSeek call per normal attempt. Bootstrap-only fallback is allowed solely for historically uncovered articles.

### Gate G — W5A compiler stays authoritative

Semantic approval relaxes only substantive UPSERT policy. Digest/lock/evidence/citation/metadata/legacy/atomic safety remains intact.

### Gate H — No destructive full-page rewrite

No generic replace/delete operations. Large changes remain scoped H2 upserts.

### Gate I — W3 isolation

No external LLM/web work is added to ingest hook. Source-awareness changes are local DB/file work only.

### Gate J — Production proof

Historical accounting closes, ongoing sources are proven, W5A regressions stay green, production ingest/Wiki health remain healthy, timer enabled only after bounded manual UAT.

### Gate K — Final Ponytail review

Fresh reviewer explicitly asks:

- can any new module be deleted and existing code reused?
- is there a one-implementation abstraction?
- did a queue/DB/framework appear?
- did historical coverage become a second ingest system?
- did source-awareness become an unnecessary generic source framework?
- did W6/query-eval work creep in?
- is this still understandable as one small personal-KB maintenance loop?

Remove unnecessary machinery before PASS.

---

## 18. Exit state

```text
ONE-TIME HISTORICAL
successful processed WeChat/RSS articles
 -> buffer / LightRAG graph discovery
 -> DeepSeek fallback only for still-uncovered articles
 -> exact coverage accounting
 -> same deterministic suggestion queue

ONGOING
successful current WeChat/RSS ingest only
 -> source-aware local W3 discovery
 -> same deterministic suggestion queue

AUTONOMOUS MAINTENANCE
suggestion JSON
 -> local evidence hydration
 -> one DeepSeek semantic decision
 -> APPLY | RETRY | REJECT
 -> fresh scoped WikiPatch
 -> W5A compiler with semantic_approved=True
 -> existing digest/lock/lint/atomic safety
 -> state updated automatically
```

The user is not expected to review suggestion files, historical articles do not remain invisible merely because they predate W3, and current supported article sources do not continue creating new blind spots.
