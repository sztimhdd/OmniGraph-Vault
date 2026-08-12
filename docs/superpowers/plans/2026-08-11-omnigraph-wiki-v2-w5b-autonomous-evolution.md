# OmniGraph Wiki v2 W5B Autonomous Evolution + Article Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a zero-human-maintenance Wiki evolution worker while closing both Wiki article-coverage gaps: historical successfully-ingested articles that predate W3, and ongoing source-aware WeChat/RSS ingestion so new successful articles cannot silently disappear from Wiki discovery.

**Architecture:** Keep W5A as the only authoritative Wiki compiler/write path. Introduce one small source-aware local article resolver reused by W3, health checks, evidence hydration, and bootstrap mapping; tighten the ingest hook so W3 sees only actual successful/confirmed current-batch articles; add one `scripts/wiki_evolve.py` worker that consumes the existing deterministic suggestion JSON queue, hydrates local article evidence, makes one DeepSeek semantic decision per normal attempt, and promotes scoped H2 patches through W5A with an explicit `semantic_approved=True` seam. The same script owns a rollout-only `--bootstrap-existing` mode that accounts for every historically successful+processed article using entity buffers, all local LightRAG graph mappings, and DeepSeek only for the remaining uncovered articles. No second queue, DB, daemon, renderer, or write path is introduced.

**Tech Stack:** Python 3, stdlib `sqlite3/hashlib/json/pathlib/datetime/tempfile/re`, python-frontmatter, existing LightRAG JSON stores, existing `lib.llm_deepseek.deepseek_model_complete`, existing W5A `kb.wiki_compiler`, pytest, systemd oneshot/timer, Aliyun production UAT.

## Global Constraints

- Authoritative approved design: `docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5b-autonomous-evolution-design.md` at commit `4cb537e94f16035816e63538ae583319c184bfff`.
- W5A FINAL PASS through `23eb430df195a6fc6bc8e2afe65fcdc2ba44da13` is a fixed prerequisite. Do not weaken, bypass, or reimplement its compiler guarantees.
- Markdown/frontmatter remains authoritative Wiki state. Existing deterministic `kb/wiki/_suggestions/*.json` files remain the queue; do not add a queue/history database.
- No `EvaluationCertificate`, event bus, resident daemon, evaluator ensemble/voting, provider registry, risk engine, rollback DB, generalized rule engine, or second historical-ingest service.
- No W6 work: no `wiki_search`, `wiki_read`, navigation graph, N-hop traversal, retrieval fusion, query feedback, answer cache, or query-aware acceptance.
- W3 ingest remains local/no-network/no-LLM and failure-isolated under the existing outer `asyncio.wait_for(..., timeout=120)` contract.
- The article coverage denominator is successful ingestion truth, not buffer count: `ingestions.status='ok'` AND corresponding LightRAG document status `processed`.
- Current article-source identity is `(article_id, source)` with at least `wechat` and `rss`. Unsupported live `ingestions.source` values are completion blockers, never silent skips.
- Canonical Wiki article evidence identity remains lowercase `MD5(url)[:10]`. Preserve source identity in evidence metadata/resolution even though the public citation `ref` remains the canonical 10-char hash.
- Ongoing W3 receives only rows that actually achieved `status == 'ok'` and `doc_confirmed == True` in the current batch. Failed/skipped/dry-run/candidate-only rows never seed Wiki.
- Historical bootstrap is rollout-only and idempotent at suggestion seeding. It must not modify the ingestion DB or re-run article ingestion.
- Historical discovery order is buffer -> all relevant LightRAG graph/chunk mappings -> one DeepSeek fallback call only for each still-uncovered article. Never use a top-N ranking as a coverage cutoff.
- Normal evolution uses exactly one `deepseek_model_complete` call per eligible suggestion attempt. Bootstrap fallback is the only extra W5B LLM use.
- Model output is never authoritative whole-page Markdown. It returns strict decision JSON and scoped H2 bodies only.
- Existing-page semantic apply is permitted only through `apply_patch(..., semantic_approved=True)` in `scripts/wiki_evolve.py`. The default remains W5A behavior.
- No `REPLACE_PAGE`, `DELETE_PAGE`, `DELETE_SECTION`, source subtraction, generic destructive operation, or bulk citation migration.
- Canonical citations remain GFM `[^N]`; legacy pages preserve legacy article citation style.
- Canonical semantic updates must keep frontmatter `sources[]`, inline citation IDs, and `## References` definitions synchronized. The worker deterministically renders the References H2 from the projected source catalog; the LLM never authors the source list or References definitions.
- `created` stays immutable. Existing W5A metadata allowlist, evidence validation, candidate validation, base digest, flock, atomic replace, and Error Book rules remain authoritative even with semantic approval.
- Expected semantic/state outcomes (`APPLY`, `RETRY`, `REJECT`, `superseded`, stale conflict, bootstrap `no_wiki_entity`) are not Error Book integrity failures.
- `--dry-run` mutates neither Wiki pages nor suggestion JSON. Bootstrap dry-run performs mapping/accounting only and must not pay for fallback DeepSeek calls.
- Use TDD. Each task lands as an atomic commit after its focused tests pass.
- Before implementation, use `superpowers:using-git-worktrees` and work in an isolated worktree if the main tree is dirty or concurrent work exists. Never absorb unrelated conflict/staged files.
- No force push. Reconcile against current `origin/main` before final regression and production deployment.
- Any production deployment must rediscover live host/repo path/venv/systemd timer truth; historical hostnames/times are hints only.

---

## File Map

### Create

- `kb/wiki_compiler/article_resolver.py` — small source-aware local article resolver and chunk->article mapping helpers; no network, no persistence.
- `scripts/wiki_evolve.py` — the only W5B worker: normal queue evolution plus rollout-only historical bootstrap.
- `tests/unit/test_wiki_article_resolver.py` — WeChat/RSS identity, hydration, unknown-source, known-ref, and chunk mapping behavior.
- `tests/unit/test_wiki_w3_source_coverage.py` — ongoing source-aware W3 behavior and successful-current-batch handoff anchors.
- `tests/unit/test_wiki_evolve.py` — queue state, evaluator, hydration, semantic promotion, retry, dry-run, citation style.
- `tests/unit/test_wiki_evolve_bootstrap.py` — historical denominator/mapping/fallback/seeding/accounting/idempotence.
- `tests/unit/test_wiki_evolve_systemd.py` — static oneshot/timer contract.
- `deploy/aliyun/systemd/omnigraph-wiki-evolve.service` — normal-mode oneshot only.
- `deploy/aliyun/systemd/omnigraph-wiki-evolve.timer` — daily schedule selected from live production timer truth during Task 6.

### Modify

- `kb/wiki_compiler/adapters/w3.py` — resolve source-aware article records, preserve source metadata, support WeChat+RSS, keep buffer discovery local.
- `kb/wiki_update.py` — pass normalized source-aware article records through the W3 adapter/compiler while preserving public compatibility entry points where necessary.
- `batch_ingest_from_spider.py` — accumulate only actual successful+confirmed current-batch rows and pass those to W3; preserve 120s isolation.
- `tests/unit/test_ingest_from_db_orchestration.py` — mandatory contract anchors for changed `ingest_from_db` behavior.
- `tests/unit/test_wiki_compiler_w3_convergence.py` — update production-route anchors for source-aware W3.
- `kb/wiki_compiler/engine.py` — minimal `semantic_approved=False` policy seam; preserve evolution state when deterministic suggestion JSON is rewritten; optionally expose a tiny public `write_suggestion()` wrapper over the existing writer for bootstrap reuse.
- `tests/unit/test_wiki_compiler_engine.py` — semantic-approval/default-policy tests and deterministic suggestion-state preservation.
- `tests/unit/test_wiki_compiler_candidate_gates.py` — semantic approval cannot bypass integrity gates.
- `scripts/reconcile_ingestions.py` — expose a read-only reusable processed-ingestion iterator/helper using its existing source/doc-status truth; keep CLI behavior unchanged.
- `scripts/wiki_generate_pages.py` — only if needed to reuse the new source-aware chunk->article helper; no W1 retrieval/prompt/provider redesign.
- `scripts/wiki_health.py` — known article refs cover both WeChat and RSS.
- `tests/unit/test_wiki_citations.py`, `tests/unit/test_wiki_lint.py`, `tests/unit/test_wiki_w5_0.py` — only source-aware citation/health regressions that intentionally change.
- `tests/unit/test_reconcile_ingestions.py`, `tests/unit/test_reconcile_rss.py` — reusable processed-ingestion helper behavior.
- `deploy/aliyun/systemd/README.md` — document the normal evolution service/timer and rollout-only bootstrap command.
- `.planning/ISSUES.md` — close only verified W5B-related issues at final closeout; do not rewrite unrelated entries.

### Do not modify unless a test proves it is required

- `kb/wiki_compiler/models.py` public evidence/patch schema.
- `kb/wiki_compiler/assembler.py` W5A operation model/canonical create behavior.
- `lib/llm_deepseek.py` provider implementation.
- MCP/API/frontend/navigation code.
- GitHub curated `entity_registry.json` ingestion path.

---

## Task 1: Source-aware local article resolver and citation corpus

**Files:**
- Create: `kb/wiki_compiler/article_resolver.py`
- Create: `tests/unit/test_wiki_article_resolver.py`
- Modify: `scripts/wiki_health.py`
- Modify: `tests/unit/test_wiki_citations.py`
- Modify: `tests/unit/test_wiki_lint.py` only if needed for the public health behavior

**Interfaces:**

Keep this module deliberately small and dict-based. Do not create a generalized source registry class.

Required public functions:

```python
def canonical_article_ref(url: str) -> str:
    """Lowercase MD5(url)[:10]."""


def list_article_sources(conn: sqlite3.Connection) -> set[str]:
    """Distinct source values present in ingestions."""


def resolve_ingestion_article(
    conn: sqlite3.Connection,
    *,
    source: str,
    article_id: int,
) -> dict[str, object] | None:
    """Resolve one source-aware DB article and compute canonical_ref."""


def build_article_ref_index(
    conn: sqlite3.Connection,
    *,
    sources: set[str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Map canonical_ref -> one or more source-aware records."""


def resolve_article_ref(
    conn: sqlite3.Connection,
    canonical_ref: str,
    *,
    source: str | None = None,
) -> dict[str, object] | None:
    """Unique local ref lookup; ambiguity is explicit, never guessed."""


def known_article_refs(conn: sqlite3.Connection) -> set[str]:
    """Canonical refs across all supported live article sources."""


def build_chunk_article_map(
    lightrag_dir: Path,
    conn: sqlite3.Connection,
) -> dict[str, dict[str, object]]:
    """Source-aware chunk_id -> local article record from existing LightRAG KV stores."""
```

Supported source->table mapping in W5B v1 is intentionally explicit:

```python
_SOURCE_TABLE = {
    "wechat": "articles",
    "rss": "rss_articles",
}
```

Unknown source must raise an explicit `UnsupportedArticleSource` (or equivalent `ValueError`) when resolution is requested. Do not dynamically interpolate arbitrary table names.

Each returned record contains at minimum:

```python
{
    "source": "wechat" | "rss",
    "article_id": 123,
    "canonical_ref": "0123456789",
    "url": "https://...",
    "title": "real local title",
    "body": "local full text or best local fallback",
}
```

Implementation must inspect the live/test schema with `PRAGMA table_info(articles)` and `PRAGMA table_info(rss_articles)` rather than assuming optional columns. Preferred field policy when columns exist:

```text
title = non-empty title_translated -> title -> canonical_ref
body  = non-empty body -> summary -> ""
```

`content_hash` is not required for RSS identity. Canonical identity is computed from URL for both sources.

- [ ] **Step 1: Write RED resolver tests for both sources**

Use an in-memory SQLite fixture with `articles`, `rss_articles`, and `ingestions` rows. Assert:

```python
assert canonical_article_ref("https://example.com/a") == hashlib.md5(
    b"https://example.com/a"
).hexdigest()[:10]

assert resolve_ingestion_article(conn, source="wechat", article_id=1)["source"] == "wechat"
assert resolve_ingestion_article(conn, source="rss", article_id=7)["source"] == "rss"
assert resolve_ingestion_article(conn, source="rss", article_id=7)["canonical_ref"] == canonical_article_ref(rss_url)
```

Also prove translated-title fallback, body->summary fallback, missing row -> `None`, and URL is required for a canonical article record.

- [ ] **Step 2: Write RED unknown-source and collision tests**

Assert:

```python
with pytest.raises(UnsupportedArticleSource):
    resolve_ingestion_article(conn, source="future_source", article_id=1)
```

For an intentionally constructed same-ref collision across two sources, `resolve_article_ref(conn, ref)` must not pick one silently. It may raise a dedicated ambiguity error; passing `source=` must resolve deterministically.

- [ ] **Step 3: Write RED chunk->article mapping tests**

Fixture `kv_store_text_chunks.json` and `kv_store_full_docs.json` with `URL:` metadata for one WeChat and one RSS article. Assert both map to records containing the correct `source`, `canonical_ref`, title, and article id.

No LightRAG runtime import and no network call is allowed.

- [ ] **Step 4: Implement the resolver with schema introspection**

Use only read-only SELECTs. Build the ref index by reading supported tables and computing MD5 from each URL. Do not add DB columns or migrations.

For `build_chunk_article_map`, reuse the current `scripts/wiki_generate_pages.py` semantics:

```text
kv_store_text_chunks[chunk_id].full_doc_id
    -> kv_store_full_docs[doc_id].content
    -> parse `URL: <url>`
    -> source-aware local URL/ref index
```

Normalize `http://` <-> `https://` as the existing W1 helper does, but keep the stored canonical ref based on the DB article's authoritative URL.

- [ ] **Step 5: Make Wiki health source-aware**

Replace `scripts/wiki_health.py:load_known_hashes()`'s WeChat-only `articles.content_hash` query with canonical URL-derived refs across supported article sources. Preserve the function name for compatibility if changing it would churn callers; document that it now returns canonical refs, not merely the old column values.

Add tests proving a canonical Wiki page that cites an RSS ref does not emit `article ref ... not in DB corpus`, while an actually unknown ref still does.

- [ ] **Step 6: Run focused tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_article_resolver.py \
  tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_lint.py -v
```

- [ ] **Step 7: Commit Task 1**

```bash
git add \
  kb/wiki_compiler/article_resolver.py \
  scripts/wiki_health.py \
  tests/unit/test_wiki_article_resolver.py \
  tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_lint.py
git commit -m "feat(wiki-v2-w5b): add source-aware article resolver"
```

---

## Task 2: Close the ongoing W3 source-coverage gap

**Files:**
- Modify: `kb/wiki_compiler/adapters/w3.py`
- Modify: `kb/wiki_update.py`
- Modify: `batch_ingest_from_spider.py`
- Create: `tests/unit/test_wiki_w3_source_coverage.py`
- Modify: `tests/unit/test_wiki_compiler_w3_convergence.py`
- Modify: `tests/unit/test_ingest_from_db_orchestration.py`

**Interfaces:**

The ingest->W3 handoff is a simple list of source-aware dicts, not a new public identity model:

```python
{
    "source": source_d,
    "article_id": art_id_d,
    "url": url_d,
    "canonical_ref": canonical_article_ref(url_d),
}
```

`kb.wiki_compiler.adapters.w3.build_w3_evidence_packs(...)` must accept these normalized records on the production path. A narrow legacy bare-hash compatibility path may remain for existing tests/callers, but it must resolve uniquely through `article_resolver`; it must not preserve the current WeChat-only SQL.

Each W3 article `EvidenceRef` should now carry real title/provenance and source metadata when resolvable:

```python
EvidenceRef(
    evidence_id=f"article-{canonical_ref}",
    type="article",
    ref=canonical_ref,
    title=record["title"],
    provenance="w3-entity-buffer",
    metadata={"source": record["source"], "article_id": record["article_id"]},
)
```

- [ ] **Step 1: Write RED W3 adapter tests for WeChat + RSS**

Create one WeChat and one RSS article, each with canonical `<ref>_entities.json` buffers naming the same entity. Assert one pack is produced at `min_frequency=2`, and its evidence contains both refs/source metadata. This must fail against the current `SELECT 1 FROM articles WHERE content_hash=?` implementation.

Also assert an unsupported explicit source raises/returns a visible error rather than being silently ignored.

- [ ] **Step 2: Write RED successful-current-batch handoff tests**

Extend `tests/unit/test_ingest_from_db_orchestration.py` with a fake batch containing:

```text
wechat A -> success=True, doc_confirmed=True
rss B    -> success=True, doc_confirmed=True
wechat C -> success=False
rss D    -> success=True, doc_confirmed=False
row E    -> skipped before ingest
```

Spy on `_wiki_update_check` and assert exactly A+B are handed off with source/article_id/url/ref; C/D/E are absent.

Do not derive W3 input from every `candidate_rows` URL after the batch.

- [ ] **Step 3: Implement successful article accumulation**

In `ingest_from_db`, initialize a current-batch list before the nested drain:

```python
wiki_successes: list[dict[str, object]] = []
```

Only append inside the exact branch where:

```python
success and doc_confirmed
```

and `status` becomes `ok`. Build the canonical ref with the shared helper. At post-drain W3 invocation, pass `wiki_successes`, not `candidate_rows` hashes.

Dry-run must leave this list empty.

- [ ] **Step 4: Route source-aware records through W3**

Update `_wiki_update_check`, `kb/wiki_update.py`, and the W3 adapter so production flow remains:

```text
source-aware successful records
  -> build_w3_evidence_packs
  -> propose_w3_patch
  -> engine.apply_patch
  -> stats
```

Keep canonical-first `DEFAULT_BUFFER_DIRS`, first matching buffer wins, distinct-article frequency, rich-page suggestion protection, structured JSON suggestions, and W5A compiler convergence.

Do not add DB body hydration, DeepSeek, Tavily, HTTP, or LightRAG query work to W3.

- [ ] **Step 5: Preserve failure isolation and 120s timeout**

Behavior tests must prove:

```python
await asyncio.wait_for(_wiki_update_check(...), timeout=120)
```

still wraps the hook, and any hook exception/timeout only logs warning and does not fail `ingest_from_db`.

- [ ] **Step 6: Add live-source blocker helper/test**

Use `article_resolver.list_article_sources(conn)` in a W5B recon/test helper and assert every returned live source is in the explicit resolver set. Fixture `future_source` must make this gate fail loudly.

Do not change migration 008's current enum merely to manufacture a future source; test the resolver/gate function directly.

- [ ] **Step 7: Run focused tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_w3_source_coverage.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_ingest_from_db_orchestration.py \
  tests/unit/test_wiki_w5_0.py -v
```

- [ ] **Step 8: Commit Task 2**

```bash
git add \
  kb/wiki_compiler/adapters/w3.py \
  kb/wiki_update.py \
  batch_ingest_from_spider.py \
  tests/unit/test_wiki_w3_source_coverage.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_ingest_from_db_orchestration.py \
  tests/unit/test_wiki_w5_0.py
git commit -m "fix(wiki-v2-w5b): make W3 article coverage source-aware"
```

---

## Task 3: Add the minimal W5A semantic-approval seam and preserve queue state

**Files:**
- Modify: `kb/wiki_compiler/engine.py`
- Modify: `tests/unit/test_wiki_compiler_engine.py`
- Modify: `tests/unit/test_wiki_compiler_candidate_gates.py`

**Interfaces:**

Change only these signatures:

```python
def classify_patch(
    patch: WikiPatch,
    wiki_root: Path,
    page_registry: dict | None = None,
    *,
    semantic_approved: bool = False,
) -> str:
    ...


def apply_patch(
    patch: WikiPatch,
    wiki_root: Path,
    wiki_update=None,
    error_book=None,
    *,
    semantic_approved: bool = False,
) -> dict:
    ...
```

Default behavior must remain byte-for-byte equivalent at policy level for W5A callers.

If bootstrap needs direct deterministic suggestion seeding without fake apply classification, expose only this tiny wrapper:

```python
def write_suggestion(patch: WikiPatch, wiki_root: Path) -> Path:
    return _write_suggestion(patch, wiki_root)
```

Do not create a suggestion repository/manager class.

- [ ] **Step 1: Write RED default-policy regression**

Existing-page patch containing `UPSERT_SECTION` must still classify `suggestion_only` when `semantic_approved` is omitted/False.

- [ ] **Step 2: Write RED semantic promotion tests**

For an existing canonical page with matching digest and a scoped `MERGE_SOURCES + UPSERT_SECTION + SET_METADATA` patch:

```python
assert classify_patch(patch, wiki_root, semantic_approved=True) == "auto_apply"
result = apply_patch(patch, wiki_root, semantic_approved=True)
assert result["status"] == "applied"
```

Prove multiple H2 operations may apply. Prove no full-page replace operation exists.

- [ ] **Step 3: Prove semantic approval cannot bypass W5A safety**

With `semantic_approved=True`, assert:

- stale `base_digest` -> `conflict`, no write;
- invalid/unresolved article evidence -> `rejected`;
- invalid canonical citation/source candidate -> `rejected`;
- `created` cannot change;
- unknown/destructive operation remains impossible/rejected by the model layer;
- legacy page with incompatible non-article evidence remains non-auto-applied;
- flock/atomic path remains the same.

- [ ] **Step 4: Implement the smallest policy branch**

Do not add semantic scores/certificates. The change should be structurally equivalent to:

```python
if any(o.op == "UPSERT_SECTION" for o in ops):
    if semantic_approved and exists and not incompatible_legacy_evidence:
        return "auto_apply"
    return "suggestion_only"
```

Preserve every downstream validation/locking/digest step unchanged.

- [ ] **Step 5: Preserve `evolution` state on deterministic suggestion rewrites**

Current `_write_suggestion()` rewrites the same `<slug>-<patch-id>.json`. Before writing a deterministic same-patch file, if a valid existing JSON contains an `evolution` object and its embedded `patch.patch_id` equals the current patch id, carry that object forward into the new payload.

This prevents a repeated W3 discovery of the same patch from resetting `applied/rejected/retry` state.

Do **not** carry state from a different patch id or malformed file.

Add tests:

```text
existing same patch + evolution.applied -> rewrite preserves applied
existing different patch id -> no state copied
malformed existing JSON -> fresh payload, no crash of normal suggestion creation
```

Malformed old suggestion itself is later an Error Book concern only when the worker tries to consume it; W3 suggestion generation should remain failure-isolated.

- [ ] **Step 6: Run engine tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py \
  tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_compiler_models.py -v
```

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  kb/wiki_compiler/engine.py \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py
git commit -m "feat(wiki-v2-w5b): add semantic approval policy seam"
```

---

## Task 4: Implement normal autonomous evolution worker

**Files:**
- Create: `scripts/wiki_evolve.py`
- Create: `tests/unit/test_wiki_evolve.py`

**Interfaces / internal shape:**

Keep this as one understandable script. Do not split queue/evaluator/retry into packages unless a concrete test proves the file cannot remain maintainable.

Suggested internal functions:

```python
def load_suggestion(path: Path) -> tuple[dict, WikiPatch]: ...
def evolution_state(payload: dict) -> dict: ...
def is_due(state: dict, now: datetime) -> bool: ...
def next_retry_at(attempts: int, now: datetime) -> str: ...
def hydrate_article_evidence(patch: WikiPatch, conn) -> tuple[EvidenceRef, ...]: ...
def build_projected_citation_catalog(current_page: str, evidence: tuple[EvidenceRef, ...]) -> dict: ...
def build_evaluator_prompt(current_page: str, evidence_text: list[dict], citation_catalog: dict) -> str: ...
def parse_decision(raw: str) -> dict: ...
def build_promoted_patch(..., decision: dict, current_page: str) -> WikiPatch: ...
async def process_suggestion(..., dry_run: bool = False) -> dict: ...
```

Required CLI:

```text
python scripts/wiki_evolve.py
python scripts/wiki_evolve.py --dry-run
python scripts/wiki_evolve.py --limit N
python scripts/wiki_evolve.py --bootstrap-existing
python scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

Task 4 implements normal mode; Task 5 adds bootstrap behavior to the same script.

### Queue state contract

Lazy default:

```python
{
    "status": "pending",
    "attempts": 0,
    "next_retry_at": None,
    "last_evaluated_at": None,
    "last_decision": None,
    "last_reason": None,
    "applied_patch_id": None,
}
```

Terminal: `rejected|applied|superseded`.

Retry schedule after incrementing attempts:

```python
1 -> now + 1 day
2 -> now + 3 days
3+ -> now + 7 days
```

### Normal eligibility

Consume article-backed W3/W5B historical suggestions only. At minimum allow triggers:

```text
w3_incremental
w5b_historical_bootstrap
```

Do not silently mutate unsupported W1/web/builtin suggestion files; report them as skipped/unsupported and leave their state unchanged.

- [ ] **Step 1: Write RED queue/state tests**

Assert:

- missing `evolution` is treated pending;
- pending is due immediately;
- future retry is skipped;
- due retry is processed;
- terminal states skipped;
- 1d/3d/7d exact schedule;
- repeat state writes update the same path only;
- `--dry-run` does not add `evolution` to disk.

Use a fixed timezone-aware `now` in tests.

- [ ] **Step 2: Write RED source-aware evidence hydration tests**

Create a suggestion whose article evidence includes one WeChat and one RSS canonical ref. Assert hydration returns real local titles and bodies, preserving:

```text
EvidenceRef.ref
EvidenceRef.provenance
metadata.source/article_id when known
```

Old W3 hash-placeholder titles must not reach the semantic prompt when a local title exists.

If an evidence ref is missing or ambiguous locally, return `RETRY` with no page write.

Bound article prompt text with one simple constant, for example:

```python
MAX_EVIDENCE_CHARS_PER_ARTICLE = 24_000
```

Document the exact constant in code and test truncation. Do not build a token-budget framework.

- [ ] **Step 3: Write RED evaluator parser tests**

Accept only strict object decisions:

```json
{"decision":"APPLY","reason":"...","sections":[{"heading":"Definition / Overview","content":"..."}]}
{"decision":"RETRY","reason":"..."}
{"decision":"REJECT","reason":"..."}
```

Reject/convert to RETRY:

- invalid JSON;
- missing decision/reason;
- unknown decision;
- APPLY with no sections;
- duplicate section headings;
- heading `References` supplied by the model;
- empty heading/content;
- model attempting frontmatter/full-page fenced output;
- timeout/provider exception.

Malformed model output is semantic `RETRY`, not Error Book corruption.

- [ ] **Step 4: Build citation instructions from the projected source catalog**

For canonical pages, parse frontmatter `sources[]` and project the exact source IDs that W5A `_merge_sources` will produce after deduplication. Existing `(type,ref)` sources keep their current ids; new evidence is assigned in the same order and positional convention as the compiler.

The prompt gives the model an explicit allowed mapping, e.g.:

```text
[^1] = existing article A
[^2] = new RSS article B
Only these citation IDs are legal.
```

For legacy pages, expose only:

```text
^[article:<canonical_ref>]
```

for hydrated article refs.

Do not let the model invent source ids, source frontmatter, or URLs.

- [ ] **Step 5: Deterministically maintain canonical `## References`**

A canonical APPLY that may introduce new sources must keep three representations synchronized:

```text
frontmatter sources[]
inline [^N]
## References definitions
```

The worker, not the LLM, builds the full projected References section from the projected source catalog and includes:

```python
PatchOperation(
    op="UPSERT_SECTION",
    section="References",
    content=rendered_reference_definitions_without_h2_heading,
    metadata={},
)
```

The model is forbidden from returning `heading="References"`.

For legacy pages, do not create/convert a canonical References section.

Tests must assert new canonical source `[^N]` has matching frontmatter source id and matching `[^N]: ...` definition after compiler apply.

- [ ] **Step 6: Implement exactly one normal DeepSeek call**

Use only:

```python
from lib.llm_deepseek import deepseek_model_complete
raw = await deepseek_model_complete(prompt, system_prompt=SYSTEM_PROMPT)
```

One eligible normal suggestion attempt invokes this function exactly once. Do not call an LLM separately for scoring, rewrite, citation repair, or validation.

Prompt asks the four approved semantic questions:

```text
1. Are factual changes supported by supplied evidence?
2. Does the rewrite avoid unjustified deletion of still-correct important information?
3. Is it more accurate/current/materially clearer?
4. Does it avoid obvious contradiction with page/evidence?
```

Decision policy is APPLY / RETRY / REJECT exactly as the spec.

- [ ] **Step 7: Build a fresh promoted patch against the latest page**

Immediately before the LLM call:

1. read latest target page;
2. compute latest `page_digest`;
3. hydrate evidence;
4. call LLM;
5. create a new W5A `WikiPatch` whose `base_digest` is that latest digest;
6. operations are `MERGE_SOURCES`, model-approved scoped `UPSERT_SECTION`s, deterministic canonical `References` UPSERT when applicable, and `SET_METADATA` (`last_updated` / confidence only);
7. call `engine.apply_patch(..., semantic_approved=True)`.

Never apply historical `suggested_content`.

A compiler conflict becomes `RETRY`. A compiler integrity rejection is a true compiler failure and may use existing Error Book behavior; do not reinterpret it as semantic approval.

- [ ] **Step 8: Persist outcomes atomically**

Normal non-dry-run state transitions:

```text
compiler applied    -> status=applied, applied_patch_id=<fresh patch id>
semantic RETRY      -> status=retry, attempts+=1, next_retry_at=1d/3d/7d
semantic REJECT     -> status=rejected, terminal
stale conflict      -> status=retry
missing target/evidence no longer meaningful -> superseded only when deterministically proven
```

Write back the same suggestion file atomically. Preserve the original complete `patch`, `suggested_content`, and provenance fields.

- [ ] **Step 9: Prove dry-run is truly read-only**

Hash both target page and suggestion JSON before/after `process_suggestion(..., dry_run=True)`. Even if the evaluator returns APPLY, both hashes must remain unchanged.

- [ ] **Step 10: Run normal-worker tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_evolve.py \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py -v
```

- [ ] **Step 11: Commit Task 4**

```bash
git add scripts/wiki_evolve.py tests/unit/test_wiki_evolve.py
git commit -m "feat(wiki-v2-w5b): add autonomous wiki evolution worker"
```

---

## Task 5: Add historical successful-article bootstrap and exact coverage accounting

**Files:**
- Modify: `scripts/wiki_evolve.py`
- Modify: `scripts/reconcile_ingestions.py`
- Modify: `scripts/wiki_generate_pages.py` only if reusing the shared chunk mapping removes duplicate WeChat-only identity logic cleanly
- Create: `tests/unit/test_wiki_evolve_bootstrap.py`
- Modify: `tests/unit/test_reconcile_ingestions.py`
- Modify: `tests/unit/test_reconcile_rss.py`
- Modify: `tests/unit/test_wiki_compiler_w1_adapter.py` only if W1 chunk mapping behavior is intentionally made source-aware

### Reusable processed-ingestion truth

Expose a read-only helper from `scripts/reconcile_ingestions.py`; do not duplicate its status semantics:

```python
def list_processed_ingestions(
    db_path: Path,
    storage_dir: Path,
) -> list[dict[str, object]]:
    """Rows with ingestions.status='ok' whose source-specific LightRAG doc id is processed."""
```

Each row must include `source`, `article_id`, `url`, `canonical_ref`, and local article record fields via the shared resolver.

The helper must preserve existing CLI output/auto-patch behavior.

- [ ] **Step 1: Write RED historical denominator tests**

Fixture rows:

```text
wechat 1 ingestions=ok, LightRAG=processed      -> eligible
rss    2 ingestions=ok, LightRAG=processed      -> eligible
wechat 3 ingestions=ok, LightRAG=pending        -> not eligible
rss    4 ingestions=failed, LightRAG=processed  -> not eligible for bootstrap denominator
```

Assert denominator exactly contains rows 1+2 with source-aware canonical refs.

- [ ] **Step 2: Implement reusable reconciliation helper**

Reuse `_compute_doc_id`, DB joins, and `_load_doc_status`. No writes. Do not invoke `--auto-patch` logic from bootstrap.

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py -v
```

- [ ] **Step 3: Write RED buffer-first bootstrap mapping test**

Given two eligible articles with valid canonical entity buffers mentioning the same entity, `--bootstrap-existing --dry-run` accounting must report:

```text
eligible_processed_ingestions = 2
mapped_via_entity_buffer = 2
mapped_via_lightrag_graph = 0 for those articles
unmapped_needing_llm_fallback = 0
seeded_entity_jobs >= 1 (would seed in dry-run reporting)
```

No DeepSeek function may be called in bootstrap dry-run.

- [ ] **Step 4: Write RED graph fallback mapping tests with no top-N cutoff**

Fixture:

- eligible article has no entity buffer;
- its full doc URL maps through `kv_store_text_chunks.json`/`kv_store_full_docs.json`;
- an entity appears in `vdb_entities.json` source ids;
- optionally a relationship endpoint appears only through `vdb_relationships.json` source ids.

Assert the article maps to those entity names.

Create >50 dummy entities and put the relevant entity after position 50; mapping must still find it. Do not call `rank_entities(top_n=...)` for coverage.

Graph association rules:

```text
entity row source chunks -> entity_name associated with each mapped article
relationship row source chunks -> both src_id and tgt_id associated with each mapped article
```

Deduplicate entity names after slug normalization.

- [ ] **Step 5: Form repeated-entity groups before LLM fallback**

After buffer/graph mapping, group by normalized entity slug and count distinct eligible articles.

```text
count >= 2 -> direct seeded entity job
count < 2  -> does not by itself satisfy article coverage
```

Then compute each eligible article represented by at least one direct seeded job. Only articles represented by zero seeded jobs proceed to DeepSeek fallback.

This ordering is essential: do not call DeepSeek first and do not call it merely because one local mapping source is absent.

- [ ] **Step 6: Write RED bootstrap DeepSeek fallback tests**

For each still-uncovered article, exactly one fallback call returns strict JSON:

```json
{"entities":["Entity A","Entity B"]}
```

or:

```json
{"entities":[]}
```

Rules:

```text
1-3 names -> seed article-backed entity jobs even if singleton
[]        -> no_wiki_entity
invalid/timeout/provider failure -> retry_unresolved
>3 names or invalid shape -> retry_unresolved
```

Fallback prompt gets only local article title/body; no Tavily/web/LightRAG query.

Bootstrap dry-run must report `would_need_llm_fallback`/equivalent count and skip the call entirely.

- [ ] **Step 7: Seed the existing W5A/W3 path, not a new renderer**

For each entity job, build a W3-compatible `EvidencePack` using real source-aware records and `trigger="w5b_historical_bootstrap"`.

Existing target page:

```text
EvidencePack -> propose W3-style update -> deterministic structured suggestion
```

Missing target page:

```text
EvidencePack(create state)
  -> W5A canonical CREATE_PAGE -> engine apply
  -> re-read created page + digest
  -> rebuild same evidence pack as existing-page state
  -> propose substantive update
  -> deterministic structured suggestion
```

The second suggestion is mandatory. A CREATE_PAGE-only result does not count as a complete seeded entity job.

Use the existing engine suggestion format. If required, call the Task 3 `write_suggestion()` wrapper; do not hand-code a second suggestion schema.

- [ ] **Step 8: Make seeding rerunnable without duplicate timestamp artifacts**

Run bootstrap twice against the same fixture. Assert:

- same logical patch addresses same deterministic JSON path;
- no extra timestamp-named suggestion file appears;
- existing terminal `evolution` state on same patch is preserved by engine writer;
- an already-created page is handled as existing on rerun and is not overwritten as CREATE_PAGE.

No bootstrap state DB/file is required. The production verification artifact records final one-time coverage accounting.

- [ ] **Step 9: Enforce exact accounting invariant**

Bootstrap result must expose at least:

```python
{
    "eligible_processed_ingestions": N,
    "mapped_via_entity_buffer": ...,
    "mapped_via_lightrag_graph": ...,
    "unmapped_needing_llm_fallback": ...,
    "seeded_entity_jobs": ...,
    "no_wiki_entity": ...,
    "retry_unresolved": ...,
    "represented_articles": ...,
}
```

Track article identities as `(source, article_id)` sets internally, not summed counters only.

Final closure assertion:

```python
eligible_ids == represented_ids | no_wiki_entity_ids | retry_unresolved_ids
assert not (represented_ids & no_wiki_entity_ids)
assert not (represented_ids & retry_unresolved_ids)
assert not (no_wiki_entity_ids & retry_unresolved_ids)
```

Bootstrap exit status must be non-zero / `complete=False` while `retry_unresolved > 0`.

- [ ] **Step 10: Optionally converge W1 chunk mapping onto the shared helper**

Current `scripts/wiki_generate_pages.py:_build_chunk_article_map()` is WeChat-only. If the shared Task 1 helper can replace it without changing W1 retrieval/prompt semantics, delegate to it and update W1 tests so RSS local article sources become article evidence rather than anonymous web sources.

This is a reuse cleanup, not a W1 redesign. If replacing it would materially enlarge scope, leave W1 behavior unchanged and document why bootstrap directly uses the shared resolver instead.

- [ ] **Step 11: Run bootstrap tests GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_evolve_bootstrap.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py \
  tests/unit/test_wiki_article_resolver.py \
  tests/unit/test_wiki_compiler_w3_convergence.py -v
```

If W1 mapping changed, also run:

```bash
venv/bin/python -m pytest tests/unit/test_wiki_compiler_w1_adapter.py -v
```

- [ ] **Step 12: Commit Task 5**

Stage only files actually changed:

```bash
git add \
  scripts/wiki_evolve.py \
  scripts/reconcile_ingestions.py \
  tests/unit/test_wiki_evolve_bootstrap.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py
# Add scripts/wiki_generate_pages.py / W1 test only if Step 10 was used.
git commit -m "feat(wiki-v2-w5b): bootstrap historical article coverage"
```

---

## Task 6: Add the daily normal-mode systemd oneshot/timer

**Files:**
- Create: `deploy/aliyun/systemd/omnigraph-wiki-evolve.service`
- Create: `deploy/aliyun/systemd/omnigraph-wiki-evolve.timer`
- Create: `tests/unit/test_wiki_evolve_systemd.py`
- Modify: `deploy/aliyun/systemd/README.md`

- [ ] **Step 1: Recon live production timers before choosing an `OnCalendar` value**

From the actual production host, capture:

```bash
systemctl list-timers --all --no-pager
systemctl cat omnigraph-daily-ingest.service
systemctl cat omnigraph-afternoon-ingest.service
systemctl cat omnigraph-daily-digest.service
```

Also inspect any additional currently enabled OmniGraph timers. Choose one daily clock slot that does not overlap ingest/digest/backup pressure.

Do not copy a historical assumed time into the unit before this recon.

Record the selected time and live evidence in the Task 8 verification artifact.

- [ ] **Step 2: Write RED static unit tests**

The service must assert:

```text
Type=oneshot
ExecStart=<current production venv python> <repo>/scripts/wiki_evolve.py
```

and must **not** include:

```text
--bootstrap-existing
--dry-run
```

The timer must target the service, run once daily, use the live-selected `OnCalendar`, and be persistently catch-up capable if consistent with existing unit conventions (`Persistent=true`).

- [ ] **Step 3: Add units matching current Aliyun service conventions**

Use the same `User`, `WorkingDirectory`, environment loading, Python path, resource limits, and logging conventions as current production units discovered at execution time. Do not invent a second deployment environment.

Bootstrap remains a manual rollout command:

```bash
<venv-python> scripts/wiki_evolve.py --bootstrap-existing
```

It is never a timer `ExecStart`.

- [ ] **Step 4: Update systemd README**

Document:

- normal daily purpose;
- `--limit` for manual UAT;
- bootstrap is rollout-only;
- timer must remain disabled until Task 8 gates pass.

- [ ] **Step 5: Run tests GREEN**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_evolve_systemd.py -v
```

- [ ] **Step 6: Commit Task 6**

```bash
git add \
  deploy/aliyun/systemd/omnigraph-wiki-evolve.service \
  deploy/aliyun/systemd/omnigraph-wiki-evolve.timer \
  deploy/aliyun/systemd/README.md \
  tests/unit/test_wiki_evolve_systemd.py
git commit -m "ops(wiki-v2-w5b): add daily evolution oneshot timer"
```

---

## Task 7: Full regression, adversarial review, and Ponytail deletion pass

**Files:**
- Modify only files required by concrete findings.
- Do not create a review framework.

- [ ] **Step 1: Reconcile execution branch with latest `origin/main`**

Because this repo has concurrent work, verify ancestry and scope before broad tests:

```bash
git fetch origin
git status --short
git log --oneline --decorate -20
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Resolve only W5B-owned conflicts. Never absorb unrelated staged/conflicted work.

- [ ] **Step 2: Run focused W5B + W5A regression**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_article_resolver.py \
  tests/unit/test_wiki_w3_source_coverage.py \
  tests/unit/test_wiki_evolve.py \
  tests/unit/test_wiki_evolve_bootstrap.py \
  tests/unit/test_wiki_evolve_systemd.py \
  tests/unit/test_wiki_compiler_models.py \
  tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py \
  tests/unit/test_wiki_compiler_w1_adapter.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_wiki_lint.py \
  tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_w5_0.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py \
  tests/unit/test_ingest_from_db_orchestration.py -v
```

Expected: all green.

- [ ] **Step 3: Run standalone Wiki health in a controlled local/fixture root**

```bash
venv/bin/python scripts/wiki_health.py --json --wiki-root <controlled-wiki-root> --db-path <fixture-db>
```

Prove both WeChat and RSS citation refs resolve.

Do not rebuild production index as part of a local test.

- [ ] **Step 4: Adversarially attack Article Coverage Gate**

A fresh reviewer/subagent must explicitly try to demonstrate each failure:

1. RSS still filtered through `articles` only.
2. W3 still uses all `candidate_rows` instead of only successful+confirmed rows.
3. failed/skipped/doc-unconfirmed rows can seed buffers/suggestions.
4. unknown live source disappears silently.
5. historical denominator is buffer count instead of `ok+processed`.
6. graph coverage uses top-N and drops a late entity.
7. relationship-only entity provenance is missed.
8. an eligible article vanishes from final accounting.
9. bootstrap reports PASS with `retry_unresolved > 0`.
10. bootstrap rerun creates timestamp-spam suggestions.
11. missing-page CREATE_PAGE is treated as terminal without substantive suggestion.

Any reproduced issue is blocking.

- [ ] **Step 5: Adversarially attack semantic evolution safety**

Reviewer must try to demonstrate:

1. normal attempt calls DeepSeek more than once;
2. model can author frontmatter or whole page;
3. model can author/override `References` directly;
4. canonical new citation lacks matching source id or footnote definition;
5. legacy page is silently migrated to canonical style;
6. `semantic_approved=True` is used anywhere besides W5B worker/tests;
7. stale digest can overwrite a changed page;
8. `created` can change;
9. candidate lint/evidence errors are bypassed after semantic approval;
10. semantic RETRY/REJECT writes Error Book noise;
11. dry-run mutates page or queue state;
12. old `suggested_content` is applied directly.

Any reproduced issue is blocking.

- [ ] **Step 6: Ponytail deletion review**

Ask exactly:

- Can any new W5B module be deleted and existing code reused instead?
- Is any abstraction serving only one implementation unnecessarily?
- Did a queue DB/history store/framework appear?
- Did a provider/router/evaluator framework appear?
- Did query-eval/navigation/W6 scope creep in?
- Is `scripts/wiki_evolve.py` still understandable as one personal-KB evolution loop?
- Did we add a second Markdown renderer rather than use W5A operations?

Delete unnecessary abstractions before PASS.

- [ ] **Step 7: Run complete relevant regression after fixes**

Re-run Step 2 plus any tests covering touched shared modules. If `batch_ingest_from_spider.py` changed, `tests/unit/test_ingest_from_db_orchestration.py` is mandatory in the final green run.

- [ ] **Step 8: Commit Task 7 fixes/review evidence**

If code fixes were required, commit them atomically with focused messages. If no code changed, do not create an empty commit. Record reviewer findings/results for Task 8 closeout.

---

## Task 8: Aliyun rollout, historical closure proof, ongoing closure proof, and closeout

**Files:**
- Modify/create verification/closeout docs following the existing Wiki phase convention discovered in repo.
- Modify: `.planning/ISSUES.md` only after verified PASS.

This task is mandatory because W5B adds a networked autonomous writer and changes the ingest->W3 source contract.

### Phase A — Live truth recon

- [ ] **Step 1: Rediscover production identity**

Capture live:

```bash
hostname
pwd
readlink -f <repo-path>
<venv-python> --version
git rev-parse HEAD
git status --short
systemctl list-timers --all --no-pager
```

Confirm actual service names/paths/env/venv. Do not rely on historical IP/service assumptions.

- [ ] **Step 2: Audit all live article sources**

Against production DB:

```sql
SELECT source, COUNT(*)
FROM ingestions
GROUP BY source
ORDER BY source;

SELECT DISTINCT source FROM ingestions ORDER BY source;
```

For every returned source, record one of:

```text
supported by article_resolver
or
proven non-Wiki-eligible with explicit reason
```

Current expected supported sources are WeChat and RSS. Any unexpected live source without resolver is `W5B RESULT: BLOCKED` until resolved by a spec-compatible narrow fix.

- [ ] **Step 3: Capture pre-fix/pre-rollout Wiki coverage facts**

Record at least:

- total successful `ingestions.status='ok'` by source;
- successful+LightRAG-processed denominator by source;
- current Wiki page/suggestion counts;
- current entity buffer counts by source/ref where derivable;
- proof whether production has RSS rows that the old W3 adapter would have discarded.

This is evidence, not a reason to re-run ingest.

### Phase B — Deploy code with timer disabled

- [ ] **Step 4: Deploy W5B code and units, but do not enable timer**

Use normal repo deployment discipline. Because W5B does not require `kb/static/` or `kb/templates/` changes, do not run an unnecessary SSG build unless the actual diff contains those paths.

After unit install:

```bash
sudo systemctl daemon-reload
sudo systemctl disable --now omnigraph-wiki-evolve.timer || true
```

Confirm disabled before any bootstrap.

### Phase C — Read-only and isolated-root UAT

- [ ] **Step 5: Run production read-only historical coverage recon**

Use production DB + LightRAG stores to compute the eligible denominator without writing Wiki/suggestions.

Run:

```bash
<venv-python> scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

Requirements:

- zero Wiki page hash changes;
- zero suggestion JSON hash changes;
- no DeepSeek fallback call in dry-run;
- exact denominator accounting;
- explicit `would_need_llm_fallback` count.

- [ ] **Step 6: Run isolated Wiki-root coverage cases with real production evidence**

Copy only required Wiki fixtures into an isolated temp root and prove:

1. real WeChat processed article resolves/hydrates;
2. real RSS processed article resolves/hydrates;
3. real entity-buffer mapping works;
4. a real graph-only mapping works if production contains one; otherwise use a fixture generated from production-shaped local stores and mark it clearly as fixture;
5. bootstrap fallback strict JSON path works with one controlled article;
6. missing-page create uses canonical `[^N]` + typed sources;
7. missing-page immediately seeds substantive deterministic suggestion;
8. existing-page historical evidence seeds suggestion without body overwrite.

- [ ] **Step 7: Run isolated semantic APPLY/RETRY/REJECT/conflict/integrity UAT**

Using real production article evidence but isolated Wiki pages:

- APPLY -> shared compiler writes scoped update with synchronized sources/citations/References;
- RETRY -> page unchanged, retry state persisted;
- REJECT -> page unchanged, terminal state;
- stale digest -> no overwrite, retry;
- invalid citation candidate -> compiler blocks despite semantic approval;
- legacy page preserves legacy citation style.

- [ ] **Step 8: Make one real production DeepSeek structured call**

Use `lib.llm_deepseek.deepseek_model_complete` under the actual production env. Validate strict parser behavior. Do not manufacture fake knowledge into authoritative production Wiki for this call.

### Phase D — Production historical bootstrap closure

- [ ] **Step 9: Run the real one-time bootstrap**

With timer still disabled:

```bash
<venv-python> scripts/wiki_evolve.py --bootstrap-existing
```

If interrupted or `retry_unresolved > 0`, fix transient cause and rerun. Deterministic seeding must not create duplicates.

- [ ] **Step 10: Require exact historical closure**

Final production report must prove set equality:

```text
eligible successful+processed historical articles
=
represented by >=1 seeded Wiki entity job
UNION explicit no_wiki_entity
```

and:

```text
retry_unresolved = 0
```

Record counts by source and total, plus seeded page/suggestion counts.

No eligible article may be absent from one of those outcomes.

### Phase E — Normal worker + ongoing source closure

- [ ] **Step 11: Run one bounded manual normal cycle**

```bash
<venv-python> scripts/wiki_evolve.py --limit <small-N>
```

At least one real historical/ongoing article-backed suggestion must be processed end-to-end. Record decision, patch id, target page, source refs, and compiler outcome. Do not require APPLY if the model legitimately returns RETRY/REJECT; if no eligible suggestion can demonstrate APPLY, use an isolated-root controlled APPLY plus production queue processing evidence.

- [ ] **Step 12: Prove ongoing W3 no longer drops supported sources**

Run a bounded normal ingestion cycle or equivalent controlled production path. For each actual `status=ok + doc_confirmed` article in the cycle:

- capture source-aware W3 handoff;
- prove WeChat resolves;
- prove RSS resolves when RSS success is present;
- failed/skipped/unconfirmed rows absent;
- W3 remains within 120s/failure-isolated.

If the bounded cycle happens to have no RSS success, perform a production-read-only resolver proof plus fixture behavior test and record that limitation explicitly; do not force-ingest fake RSS content.

### Phase F — Health + enable timer

- [ ] **Step 13: Run production Wiki health/index regression**

```bash
<venv-python> scripts/wiki_health.py --json --wiki-root <production-wiki-root> --db-path <production-db>
```

No new ERROR may be introduced. Investigate WARNs caused by W5B; do not blanket-ignore them.

If the authoritative runtime deployment expects an index rebuild after page creation, perform the existing documented rebuild only after page set is stable, then rerun health.

- [ ] **Step 14: Verify ingest and API/service health**

Confirm production ingest service/timers remain healthy and W3 still cannot fail main ingest. Check relevant journals for W5B/W3 exceptions.

- [ ] **Step 15: Enable the daily timer only now**

```bash
sudo systemctl enable --now omnigraph-wiki-evolve.timer
systemctl status omnigraph-wiki-evolve.timer --no-pager
systemctl list-timers --all --no-pager | grep wiki-evolve
```

Record next run time and verify no collision with live ingest/digest timers.

### Phase G — Closeout

- [ ] **Step 16: Write verification closeout**

Use existing phase-doc conventions and include:

- final commit range/HEAD;
- exact unit/regression commands + pass counts;
- live source audit;
- historical denominator by source;
- buffer/graph/fallback mapping counts;
- represented/no_wiki_entity/retry_unresolved counts;
- exact accounting closure;
- production DeepSeek UAT;
- semantic APPLY/RETRY/REJECT/conflict/integrity UAT;
- ongoing WeChat/RSS W3 proof;
- Wiki health result;
- service/timer state;
- Ponytail review result;
- unrelated concurrent files explicitly excluded.

- [ ] **Step 17: Reconcile `.planning/ISSUES.md`**

Close only issues proven resolved by evidence above. Add any material unresolved W5B issue discovered during UAT. Do not rewrite unrelated backlog.

- [ ] **Step 18: Final independent verification**

A fresh verifier must inspect actual final code/diff and sign these gates:

```text
A Minimal architecture                         PASS/FAIL
B Historical article coverage closure          PASS/FAIL
C Ongoing source-aware article coverage        PASS/FAIL
D Zero-human queue state machine               PASS/FAIL
E Local evidence grounding                     PASS/FAIL
F Exactly one normal DeepSeek call             PASS/FAIL
G Shared W5A compiler authoritative             PASS/FAIL
H No whole-page destructive rewrite            PASS/FAIL
I W3 no-network/non-blocking isolation          PASS/FAIL
J Regression + production UAT                  PASS/FAIL
K Ponytail deletion review                     PASS/FAIL
```

Any FAIL means final result is BLOCKED.

- [ ] **Step 19: Commit closeout and push verified W5B commits**

```bash
git add <verification-docs> .planning/ISSUES.md
git commit -m "docs(wiki-v2-w5b): verify autonomous evolution rollout"
git push origin HEAD:main
```

Do not push unrelated concurrent changes.

Final report must end with exactly one of:

```text
W5B RESULT: PASS
```

or:

```text
W5B RESULT: BLOCKED
```

---

## Implementation Order and Dependency Graph

Execute strictly:

```text
Task 1 source-aware resolver
  -> Task 2 ongoing W3 closure
  -> Task 3 semantic approval seam
  -> Task 4 normal evolution worker
  -> Task 5 historical bootstrap
  -> Task 6 systemd unit/timer after live time recon
  -> Task 7 adversarial + Ponytail review
  -> Task 8 production rollout + independent verification
```

Task 5 depends on Tasks 1/3/4 because bootstrap must use the same resolver, suggestion format, and W5A writer path. Task 8 must not enable the timer before bootstrap historical closure and controlled normal UAT pass.

---

## Plan Self-Review Checklist

Before starting implementation, the executing agent must verify this plan against the approved spec:

- [ ] Every historically eligible article is accounted for from `ingestions.status='ok' + LightRAG processed`, not entity buffers.
- [ ] WeChat and RSS are explicit resolver paths.
- [ ] Unknown live sources block completion.
- [ ] Ongoing W3 input is actual successful+confirmed rows only.
- [ ] W3 still performs no network/LLM work and retains 120s isolation.
- [ ] Bootstrap searches buffers first, full graph second, DeepSeek last.
- [ ] No top-N historical coverage cutoff exists.
- [ ] Repeated-entity threshold is applied before fallback LLM.
- [ ] Fallback empty means explicit `no_wiki_entity`; failure means `retry_unresolved`.
- [ ] `retry_unresolved > 0` prevents bootstrap completion.
- [ ] Missing historical page is CREATE_PAGE then substantive suggestion, never create-only.
- [ ] Existing deterministic suggestion JSON remains the only queue.
- [ ] Same patch rewrite preserves `evolution` state.
- [ ] Normal evolution uses one DeepSeek call exactly.
- [ ] Old `suggested_content` is trigger/provenance only, never authoritative apply content.
- [ ] Canonical source IDs, inline citations, and References definitions remain synchronized deterministically.
- [ ] Legacy citation style is preserved.
- [ ] Only W5B worker invokes `semantic_approved=True`.
- [ ] Default W5A policy stays unchanged.
- [ ] Dry-run mutates no page/queue state; bootstrap dry-run pays no fallback LLM cost.
- [ ] No new DB/daemon/framework/router/navigation/query-eval subsystem appears.
- [ ] Production timer stays disabled until historical closure + controlled UAT pass.
- [ ] Final verifier is independent from the implementation self-report.

### Placeholder / ambiguity scan

The implementation agent must reject any attempted shortcut equivalent to:

```text
"handle RSS somehow"
"scan old files"
"use top entities"
"call LLM if needed"
"validate later"
"add generic source framework"
```

The concrete interfaces, state transitions, mapping order, accounting set equality, retry cadence, deployment gates, and expected test commands in this plan are the implementation contract. If live repo truth invalidates a named optional column or production path, adapt the narrow resolver/query to live truth, add a behavior test, and document the deviation; do not silently broaden architecture.
