# OmniGraph Wiki v2 W5B Autonomous Evolution + Article Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use TDD, keep commits atomic, and perform `superpowers:verification-before-completion` before any PASS claim.

**Goal:** Make Wiki maintenance autonomous while closing both historical and ongoing article-coverage gaps: every successfully processed historical WeChat/RSS article is explicitly accounted for, future successful WeChat/RSS ingests reach source-aware W3, and substantive existing-page evolution is evaluated by exactly one normal DeepSeek call then applied only through the existing W5A compiler safety path.

**Architecture:** Add one runtime script, `scripts/wiki_evolve.py`, with normal queue-consumption mode and rollout-only `--bootstrap-existing` mode. Add one small shared local article resolver, `kb/wiki_articles.py`, so WeChat/RSS URL identity, hydration, successful-ingestion reconciliation, and LightRAG chunk→article mapping use the same source-aware truth. Preserve W3 as local/no-network and tighten its input to only current-batch `status=ok AND doc_confirmed` articles. Extend the W5A compiler with only `semantic_approved=False` plus tiny suggestion-state persistence helpers. Historical bootstrap reuses entity buffers first, LightRAG graph/chunk mappings second, and DeepSeek only for still-uncovered historical articles, then seeds the same deterministic W5A/W3 suggestion path. No second ingest stack, queue DB, evaluator framework, or W6 navigation/query-eval work.

**Tech Stack:** Python 3, stdlib `sqlite3/json/hashlib/re/pathlib/asyncio/datetime/tempfile`, python-frontmatter, existing `lib.llm_deepseek.deepseek_model_complete`, existing W5A compiler (`kb/wiki_compiler/*`), existing LightRAG JSON stores, pytest, systemd/Aliyun production UAT.

## Global Constraints

- Authoritative design contract: `docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5b-autonomous-evolution-design.md` at approved commit `4cb537e94f16035816e63538ae583319c184bfff`.
- W5A prerequisite is fixed through final PASS commit `23eb430df195a6fc6bc8e2afe65fcdc2ba44da13`; do not weaken its digest/lock/citation/metadata/atomic-write protections.
- Markdown/frontmatter remains Wiki source of truth. Existing deterministic `_suggestions/*.json` files remain the only queue-like workflow artifacts.
- No new queue/history DB, daemon, event bus, evaluator ensemble, provider registry, risk score, rollback DB, generalized rule engine, or second historical-ingest service.
- No W6 `wiki_search`/`wiki_read`, navigation graph, N-hop traversal, retrieval fusion, query-feedback acceptance, or affected-query/guard-query benchmark framework.
- No whole-page `REPLACE_PAGE`, `DELETE_PAGE`, `DELETE_SECTION`, generic source subtraction, or destructive rewrite path.
- Normal semantic evolution uses exactly **one** `deepseek_model_complete` call per due suggestion attempt. The only additional W5B LLM use is one bootstrap-only entity extraction call for an eligible historical article that remains uncovered after buffer + graph discovery.
- W3 ingest hook must remain entirely local/no-network/no-LLM and stay isolated under its existing `asyncio.wait_for(..., timeout=120)` boundary.
- Canonical Wiki article ref for both WeChat and RSS is `md5(url.encode()).hexdigest()[:10]`, lowercase.
- **Do not use `rss_articles.content_hash` as Wiki article identity.** Current `enrichment/rss_fetch.py` stores MD5 of RSS text there (32 hex chars), not URL identity. Derive the canonical Wiki ref from `rss_articles.url`.
- Preserve backward compatibility for existing WeChat W3 deterministic suggestion IDs where the same article-ref set is re-emitted; do not create duplicate suggestion files merely because source-awareness was added.
- Existing W1 web/builtin acquisition remains unchanged. W5B adds no Tavily/Databricks/web retrieval stage.
- No bulk migration of existing Wiki citations/pages. Legacy pages remain supported in-place.
- Git is the durable implementation audit/rollback source. No uncommitted production-only final state.
- No force push. Before final push/deploy reconcile latest `origin/main`; preserve unrelated concurrent changes. If the primary worktree is dirty/conflicted, use an isolated worktree.
- `batch_ingest_from_spider.py:ingest_from_db` behavior changes require behavior anchors in `tests/unit/test_ingest_from_db_orchestration.py`.
- Before deploy inspect the complete diff for `kb/(static|templates)/`; W5B should not need either. If they are unexpectedly touched, use the full Makefile/SSG deploy discipline instead of a partial sync.

---

## File Map

### Create

- `kb/wiki_articles.py` — small source-aware local article resolver and LightRAG article mapping helpers. This is **not** a generic source framework; it supports only the article sources represented by the current `ingestions` contract, initially `wechat` and `rss`.
- `scripts/wiki_evolve.py` — the single W5B runtime component: due suggestion state machine, local hydration, one-call semantic evaluator, promoted patch application, and rollout-only historical bootstrap.
- `tests/unit/test_wiki_articles.py` — source-aware identity/hydration/processed-ingestion/chunk-map tests.
- `tests/unit/test_wiki_w5b_ongoing_coverage.py` — ongoing WeChat/RSS W3 success-set and source-resolution tests.
- `tests/unit/test_wiki_w5b_evolution.py` — queue state, evaluator, promotion, retry, dry-run, semantic-apply tests.
- `tests/unit/test_wiki_w5b_bootstrap.py` — historical denominator, buffer/graph/fallback/accounting/seeding/idempotency tests.
- `deploy/aliyun/systemd/omnigraph-wiki-evolve.service` — normal-mode oneshot worker.
- `deploy/aliyun/systemd/omnigraph-wiki-evolve.timer` — daily normal-mode timer; exact `OnCalendar` is committed only after live timer recon proves a safe gap.

### Modify

- `kb/wiki_compiler/adapters/w3.py` — accept source-aware article refs, resolve WeChat/RSS locally, emit real titles + source metadata, preserve legacy bare-ref compatibility, keep no-network behavior.
- `kb/wiki_update.py` — pass source-aware refs through compatibility surface without reintroducing policy/write logic.
- `batch_ingest_from_spider.py` — collect only successful+confirmed current-batch article refs for W3; preserve the 120s timeout/failure isolation.
- `kb/wiki_compiler/engine.py` — add `semantic_approved=False`; preserve suggestion evolution state on deterministic rewrites; expose one tiny atomic evolution-state update helper.
- `scripts/wiki_health.py` — known article-ref corpus recognizes canonical URL-derived WeChat + RSS refs while preserving valid legacy 10-char WeChat refs.
- `scripts/wiki_generate_pages.py` — delegate existing chunk/full-doc URL→article mapping to the shared source-aware helper; do not change W1 retrieval/provider behavior.
- `tests/unit/test_wiki_compiler_engine.py` / `tests/unit/test_wiki_compiler_candidate_gates.py` — semantic-approval regression anchors.
- `tests/unit/test_wiki_compiler_w3_convergence.py` — source-aware W3 compatibility anchors.
- `tests/unit/test_ingest_from_db_orchestration.py` — successful-only W3 hook contract + unchanged 120s isolation.
- `tests/unit/test_wiki_w5_0.py` / citation-health tests only where the known article corpus intentionally expands to RSS canonical refs.
- `deploy/aliyun/systemd/README.md` — document the W5B oneshot/timer and bootstrap rollout command after live service names/paths are verified.
- `.planning/ISSUES.md` — closeout only after verified implementation/UAT; do not use it as an implementation scratchpad.

### Explicitly do not modify

- frontend/static/templates;
- MCP/API retrieval surfaces;
- LightRAG/Qdrant schema;
- `entity_registry.json` / GitHub curated ingestion path;
- W1 Tavily/Databricks/Opus acquisition logic;
- ingestion DB schema/migrations solely for W5B;
- Error Book schema.

---

## Task 1: Source-aware local article truth (`kb/wiki_articles.py`)

**Why first:** W3, health, evolution hydration, historical denominator, and LightRAG graph mapping all currently disagree about article identity. Fix one small local truth seam before touching orchestration.

**Files:**
- Create: `kb/wiki_articles.py`
- Create: `tests/unit/test_wiki_articles.py`
- Modify: `scripts/wiki_health.py`
- Modify: `scripts/wiki_generate_pages.py`
- Modify tests that directly assert `_build_chunk_article_map` or `load_known_hashes` behavior.

**Interfaces:**

```python
SUPPORTED_ARTICLE_SOURCES = ("wechat", "rss")


def canonical_article_ref(url: str) -> str:
    """Return lowercase MD5(url)[:10]."""


def lightrag_doc_id(source: str, url: str) -> str:
    """wechat_<ref> or rss_<ref>; reject unsupported source."""


def live_ingestion_sources(conn: sqlite3.Connection) -> set[str]:
    """SELECT DISTINCT source FROM ingestions."""


def load_article_index(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """Map (source, canonical_ref) -> local article record."""


def resolve_article(
    index: dict[tuple[str, str], dict],
    ref: str,
    *,
    source: str | None = None,
) -> dict | None:
    """Strict source lookup; source=None is allowed only when exactly one local row matches ref."""


def processed_ingestions(
    conn: sqlite3.Connection,
    lightrag_dir: Path,
) -> list[dict]:
    """Return ingestions.status=ok rows whose source-specific LightRAG doc_status is processed."""


def build_chunk_article_map(
    lightrag_dir: Path,
    conn: sqlite3.Connection,
) -> dict[str, dict]:
    """Map chunk-id -> source-aware local article record via full-doc URL."""


def known_wiki_article_refs(conn: sqlite3.Connection) -> set[str]:
    """Canonical URL-derived refs across supported article tables + valid legacy 10-char WeChat refs."""
```

Each article record stays a plain dict, not a public identity class/framework:

```python
{
    "source": "wechat" | "rss",
    "article_id": 123,
    "ref": "0123456789",
    "url": "https://...",
    "title": "real title",
    "text": "body, falling back to summary",
}
```

Source table mapping is fixed, explicit code:

```python
_TABLES = {"wechat": "articles", "rss": "rss_articles"}
```

No plugin registry or generic source adapter.

- [ ] **Step 1.1 — Write RED identity tests**

In `tests/unit/test_wiki_articles.py`, fixture both tables plus `ingestions` and assert:

```python
def test_rss_canonical_ref_comes_from_url_not_content_hash(conn):
    url = "https://example.com/rss/a"
    conn.execute(
        "INSERT INTO rss_articles(id, title, url, content_hash, summary) VALUES (1, ?, ?, ?, ?)",
        ("RSS title", url, "f" * 32, "rss summary"),
    )
    idx = load_article_index(conn)
    ref = hashlib.md5(url.encode()).hexdigest()[:10]
    assert idx[("rss", ref)]["ref"] == ref
    assert idx[("rss", ref)]["ref"] != "f" * 32
```

Also test:

- WeChat canonical ref from URL;
- `title_translated` wins when present/non-empty, then `title`;
- `body` wins when present/non-empty, then `summary`;
- resolver works when optional production columns (`body`, `title_translated`) are absent by using `PRAGMA table_info` rather than assuming every migration in unit fixtures;
- `resolve_article(..., source="rss")` cannot return a WeChat record;
- legacy `source=None` lookup succeeds only for one unique matching ref and refuses ambiguity;
- unsupported source raises a named local exception such as `UnsupportedArticleSource`, never silent skip.

- [ ] **Step 1.2 — Run RED**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_articles.py -q
```

Expected: module/import failure.

- [ ] **Step 1.3 — Implement minimal source-aware resolver**

Implementation rules:

- derive canonical ref from `url` for **both** tables;
- never reinterpret RSS `content_hash` as URL identity;
- fixed source/table map only;
- dynamically inspect table columns only to choose safe title/text fallback fields;
- no writes to article/ingestion DB;
- no network imports.

Suggested fixed fallback order:

```python
title = first_nonempty(row.get("title_translated"), row.get("title"), ref)
text = first_nonempty(row.get("body"), row.get("summary"), "")
```

- [ ] **Step 1.4 — Add processed-ingestion parity tests**

Fixture LightRAG `kv_store_doc_status.json`:

```json
{
  "wechat_<refA>": {"status": "processed"},
  "rss_<refB>": {"status": "processed"},
  "rss_<refC>": {"status": "failed"}
}
```

Assert denominator includes only `ingestions.status='ok'` plus processed A/B, not failed/skipped/missing-status rows. Assert parity with `scripts/reconcile_ingestions.py` doc-id semantics for both sources.

Unknown `ingestions.source` must raise/block instead of disappearing.

- [ ] **Step 1.5 — Factor chunk/full-doc mapping without changing W1 acquisition**

Move the local mechanics currently in `scripts/wiki_generate_pages.py:_build_chunk_article_map` into `kb/wiki_articles.build_chunk_article_map`:

```text
kv_store_text_chunks.json
 -> full_doc_id
 -> kv_store_full_docs.json content
 -> parse `URL: <url>`
 -> local source-aware URL index
 -> source/ref/title/text record
```

Keep HTTP⇄HTTPS normalization already used by W1.

In `scripts/wiki_generate_pages.py`, retain a tiny compatibility wrapper returning its current catalog shape:

```python
def _build_chunk_article_map(lightrag_dir, db_path):
    with sqlite3.connect(str(db_path)) as conn:
        mapped = wiki_articles.build_chunk_article_map(lightrag_dir, conn)
    return {
        cid: {"hash": row["ref"], "title": row["title"], "url": row["url"]}
        for cid, row in mapped.items()
    }
```

This intentionally makes W1 local corpus mapping RSS-capable but does **not** alter Tavily, LightRAG query, or Opus behavior.

- [ ] **Step 1.6 — Expand standalone health corpus**

Change `scripts/wiki_health.py:load_known_hashes()` implementation (name may remain for compatibility) to use `known_wiki_article_refs()`.

Preserve valid existing legacy WeChat 10-char refs while adding canonical URL-derived RSS refs. Do not admit RSS 32-char body MD5 values.

Test a canonical page citing an RSS URL-ref has no “not in DB corpus” warning.

- [ ] **Step 1.7 — Run GREEN + focused regression**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_articles.py \
  tests/unit/test_wiki_w5_0.py \
  tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_lint.py \
  tests/unit/test_rss_schema.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py -q
```

- [ ] **Step 1.8 — Commit**

```bash
git add kb/wiki_articles.py scripts/wiki_health.py scripts/wiki_generate_pages.py tests/unit/test_wiki_articles.py tests/unit/test_wiki_*.py
git commit -m "feat(wiki-v2-w5b): add source-aware local article truth"
```

Before committing, inspect `git diff --cached --name-only`; do not accidentally stage unrelated files.

---

## Task 2: Close the ongoing W3 blind spot (successful-only + source-aware)

**Files:**
- Modify: `kb/wiki_compiler/adapters/w3.py`
- Modify: `kb/wiki_update.py`
- Modify: `batch_ingest_from_spider.py`
- Create: `tests/unit/test_wiki_w5b_ongoing_coverage.py`
- Modify: `tests/unit/test_wiki_compiler_w3_convergence.py`
- Modify: `tests/unit/test_ingest_from_db_orchestration.py`

**Required production data shape:** use a simple mapping at the hook boundary, not a new identity class:

```python
{"source": "wechat", "ref": "0123456789"}
{"source": "rss", "ref": "abcdef0123"}
```

Legacy direct callers may still pass bare 10-char strings; W3 resolves those across the local article index only when unambiguous.

- [ ] **Step 2.1 — Write RED W3 source-resolution tests**

Tests must prove:

1. WeChat source-aware input resolves through `articles`.
2. RSS source-aware input resolves through `rss_articles` using URL-derived ref even when `rss_articles.content_hash` is unrelated 32-char body MD5.
3. resulting `EvidenceRef` uses:

```python
EvidenceRef(
    type="article",
    ref=canonical_ref,
    title="real local title",
    metadata={"source": "rss", ...},
)
```

4. no network/LLM imports or calls occur in W3.
5. `min_frequency` remains **distinct article refs**, source-aware; two distinct articles are required for normal incremental seeding.
6. unknown/unsupported source cannot silently form a pack.

- [ ] **Step 2.2 — Preserve deterministic IDs for existing WeChat suggestions**

Add a behavior test using the same all-WeChat ref set as W5A and assert the resulting `pack_id` / `patch_id` is unchanged from the legacy source-unaware path.

For groups containing RSS, include source in the deterministic pack identity so `(source, ref)` collisions cannot alias. Use a stable deterministic form; do not include timestamps. For example:

```python
if all(source in (None, "wechat") for source, ref in records):
    pack_id = f"w3-{slug}-{'-'.join(sorted(refs))}"  # W5A compatibility
else:
    material = "|".join(sorted(f"{source}:{ref}" for ...))
    pack_id = f"w3-{slug}-{sha256(material.encode()).hexdigest()[:16]}"
```

- [ ] **Step 2.3 — Implement W3 adapter source awareness**

`build_w3_evidence_packs()` must:

- normalize mappings/bare refs;
- resolve against `load_article_index(db_conn)`;
- search the existing canonical-first entity-buffer dirs using `<canonical_ref>_entities.json`;
- deduplicate by source-aware article key;
- build evidence with real title + metadata source;
- keep existing page digest/path capture;
- perform no network/LLM work.

Keep `build_w3_pack_for_entity()` backward-compatible for existing tests/callers, but add the smallest internal helper needed to build a pack from already-resolved article records. Do not create a new adapter package/framework.

- [ ] **Step 2.4 — Write RED current-batch success-set orchestration tests**

In `tests/unit/test_ingest_from_db_orchestration.py` and `test_wiki_w5b_ongoing_coverage.py`, fixture a batch with:

```text
wechat A -> status ok, doc_confirmed=True
rss B    -> status ok, doc_confirmed=True
wechat C -> status failed
rss D    -> skipped/rejected
```

Spy `_wiki_update_check` and assert it receives exactly A/B source-aware refs, never C/D.

This test must fail against the current code because current post-drain W3 derives hashes from all `candidate_rows`.

- [ ] **Step 2.5 — Tighten `batch_ingest_from_spider.py` hook input**

Create a current-batch collection near the ingest orchestration state:

```python
wiki_success_refs: dict[tuple[str, str], dict[str, str]] = {}
```

Only when the existing article result is:

```python
status == "ok" and doc_confirmed
```

add:

```python
ref = hashlib.md5(url_d.encode()).hexdigest()[:10]
wiki_success_refs[(source_d, ref)] = {"source": source_d, "ref": ref}
```

After final drain:

```python
wiki_stats = await asyncio.wait_for(
    _wiki_update_check(list(wiki_success_refs.values()), conn),
    timeout=120,
)
```

Delete the current all-`candidate_rows` hash construction. Keep both exception handlers and the 120s timeout unchanged.

No DeepSeek/web work is allowed here.

- [ ] **Step 2.6 — Pass source-aware refs through `kb/wiki_update.py`**

Keep public compatibility entry points (`generate_wiki_suggestions`, `apply_suggestion_atomic`, `run_wiki_update_pipeline`) but allow source-aware mappings through to W3. Do not duplicate article resolution/policy/apply logic in this compatibility module.

- [ ] **Step 2.7 — Source audit behavior test**

Using `live_ingestion_sources(conn)`, assert fixture sources `{wechat, rss}` are both supported; inserting a fake `source='other'` (or bypassing CHECK in a dedicated fixture table) must produce an explicit unsupported-source failure in the audit helper, not a “0 packs” success.

- [ ] **Step 2.8 — Run GREEN and regressions**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_w5b_ongoing_coverage.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_ingest_from_db_orchestration.py \
  tests/unit/test_dual_source_dispatch.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py -q
```

- [ ] **Step 2.9 — Commit**

```bash
git add kb/wiki_compiler/adapters/w3.py kb/wiki_update.py batch_ingest_from_spider.py \
  tests/unit/test_wiki_w5b_ongoing_coverage.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_ingest_from_db_orchestration.py
git commit -m "fix(wiki-v2-w5b): make ongoing W3 article coverage source-aware"
```

---

## Task 3: Minimal W5A semantic-promotion seam + durable suggestion state

**Files:**
- Modify: `kb/wiki_compiler/engine.py`
- Modify: `tests/unit/test_wiki_compiler_engine.py`
- Modify: `tests/unit/test_wiki_compiler_candidate_gates.py`
- Create/extend W5B evolution tests for suggestion-state preservation.

**Interfaces:**

```python
def classify_patch(
    patch: WikiPatch,
    wiki_root: Path,
    page_registry: dict | None = None,
    *,
    semantic_approved: bool = False,
) -> str: ...


def apply_patch(
    patch: WikiPatch,
    wiki_root: Path,
    wiki_update=None,
    error_book=None,
    *,
    semantic_approved: bool = False,
) -> dict: ...


def update_suggestion_evolution(path: Path, evolution: dict) -> None:
    """Atomically replace only payload['evolution'] in an existing suggestion JSON."""
```

Do not add a certificate object/class.

- [ ] **Step 3.1 — Write RED policy tests**

Assert an existing-page patch with:

```text
MERGE_SOURCES + UPSERT_SECTION + SET_METADATA(last_updated only)
```

is:

```python
assert classify_patch(patch, root) == "suggestion_only"
assert classify_patch(patch, root, semantic_approved=True) == "auto_apply"
```

Then attack the flag:

- critical metadata (`created`, `title`, `sources`) still cannot auto-apply;
- legacy page + non-article evidence still cannot auto-apply;
- stale/missing base digest still conflicts at apply;
- invalid citation/candidate still rejects;
- unknown/destructive op is not promoted;
- `CREATE_PAGE` behavior is unchanged;
- `semantic_approved=False` is byte-for-byte/default compatible with W5A callers.

- [ ] **Step 3.2 — Implement only the boolean seam**

Preserve the existing policy ordering. The UPSERT branch becomes conceptually:

```python
if any(o.op == "UPSERT_SECTION" for o in ops):
    if not semantic_approved:
        return "suggestion_only"
    if not exists:
        return "suggestion_only"
    if legacy and _has_non_article_evidence(patch.evidence):
        return "suggestion_only"
    return "auto_apply"
```

Critical metadata gating must execute before this branch exactly as W5A does now.

`apply_patch(...semantic_approved=...)` passes the flag only to `classify_patch`; every later digest/lock/render/candidate-lint/atomic-write step stays unchanged.

- [ ] **Step 3.3 — Write RED deterministic suggestion-state tests**

Existing `_write_suggestion()` currently rewrites the full deterministic JSON payload. Add tests:

1. create suggestion;
2. add `evolution={"status":"retry", ...}` through the new helper;
3. re-emit the **same** patch through `apply_patch()`;
4. assert the same path is used and the `evolution` object is preserved exactly.

This prevents ongoing W3 reruns from resetting an already-applied/rejected/retry queue state.

- [ ] **Step 3.4 — Implement tiny state persistence helper**

Rules:

- `_write_suggestion()` loads existing deterministic JSON, if valid, and carries forward only its `evolution` field into the refreshed authoritative patch payload;
- `update_suggestion_evolution(path, evolution)` loads JSON, changes only `evolution`, then reuses engine `_atomic_write`;
- no suggestion repository class, queue DB, append-only history, or timestamped copy;
- malformed existing suggestion JSON is an integrity failure, not silently overwritten.

- [ ] **Step 3.5 — Run engine safety suite**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py \
  tests/unit/test_wiki_compiler_models.py \
  tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_compiler_w3_convergence.py -q
```

- [ ] **Step 3.6 — Commit**

```bash
git add kb/wiki_compiler/engine.py tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py tests/unit/test_wiki_compiler_w3_convergence.py
git commit -m "feat(wiki-v2-w5b): add semantic approval seam and durable suggestion state"
```

---

## Task 4: Normal evolution worker — queue, hydration, one-call evaluator

**Files:**
- Create: `scripts/wiki_evolve.py`
- Create: `tests/unit/test_wiki_w5b_evolution.py`

Keep runtime logic in this single script unless a helper becomes demonstrably reusable in a second production caller. Do not create `kb/wiki_evolution/` package, provider classes, queue classes, or policy framework.

**CLI:**

```text
python scripts/wiki_evolve.py
python scripts/wiki_evolve.py --dry-run
python scripts/wiki_evolve.py --limit N
python scripts/wiki_evolve.py --bootstrap-existing
python scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

Normal mode scans sorted `kb/wiki/_suggestions/*.json` deterministically.

**State helpers in script:**

```python
def default_evolution_state() -> dict: ...
def is_due(state: dict, now: datetime) -> bool: ...
def retry_delay(attempts: int) -> timedelta: ...
def parse_semantic_result(raw: str) -> dict: ...
```

Retry schedule:

```text
attempt 1 -> +1 day
attempt 2 -> +3 days
attempt 3+ -> +7 days
```

- [ ] **Step 4.1 — Write RED queue/state tests**

Prove:

- missing `evolution` behaves as pending;
- `pending` due immediately;
- retry before `next_retry_at` skipped;
- retry at/after due runs;
- rejected/applied/superseded skipped;
- `--limit N` counts eligible attempts, not terminal/skipped files;
- same suggestion file is updated; no new timestamp filename;
- `--dry-run` does not lazily write pending state and does not mutate any suggestion JSON.

Use injected `now` in helper-level tests; do not freeze global time via obscure dependencies.

- [ ] **Step 4.2 — Write RED source-aware hydration tests**

Given suggestion evidence:

```python
EvidenceRef(
    type="article",
    ref=ref,
    title=ref,  # old W3 placeholder
    metadata={"source": "rss"},
)
```

hydrate from `load_article_index()` and assert:

- real RSS title replaces hash placeholder;
- article text comes from local body/summary;
- canonical ref unchanged;
- source metadata preserved;
- no web request/Tavily/provider call;
- missing local evidence => worker result RETRY before semantic apply;
- old W3 evidence with no `metadata.source` may resolve only if `resolve_article(...source=None)` is unambiguous.

Define one simple prompt cap, e.g.:

```python
MAX_ARTICLE_CHARS = 12_000
MAX_TOTAL_EVIDENCE_CHARS = 48_000
```

The exact constants may be adjusted once during implementation if current test/article sizes require it, but there must be only these fixed character caps — no token-budget framework.

- [ ] **Step 4.3 — Write RED strict evaluator parsing tests**

Accept only JSON objects with decision in `{APPLY, RETRY, REJECT}`.

For APPLY require:

```json
{
  "decision": "APPLY",
  "reason": "...",
  "sections": [
    {"heading": "Definition / Overview", "content": "..."}
  ]
}
```

Reject as malformed → RETRY:

- Markdown-fenced prose around JSON unless the parser intentionally strips one outer code fence only;
- missing/unknown decision;
- APPLY without non-empty sections;
- section missing heading/content;
- H1/full-page/frontmatter content attempts;
- duplicate section headings if they would make update order ambiguous.

Do not accept numeric confidence/score as a second policy channel.

- [ ] **Step 4.4 — Build exact citation instructions before the call**

For canonical current pages:

- parse existing `sources[]`;
- evidence already present uses its existing `id`;
- new evidence receives the same append IDs the W5A `_merge_sources()` path will use (`len(existing_sources)+1...` in evidence order);
- prompt explicitly maps each article ref/title to its exact `[^N]` token.

For legacy article-only pages:

- map each ref to `^[article:<ref>]`.

Add a test comparing the worker's predicted citation mapping against the actual candidate produced by the compiler merge path so citation IDs cannot drift.

- [ ] **Step 4.5 — Implement exactly one normal DeepSeek call**

Normal evaluator function should be structurally simple:

```python
async def evaluate_suggestion(...):
    prompt = build_prompt(...)
    raw = await deepseek_model_complete(prompt, system_prompt=SYSTEM_PROMPT)
    return parse_semantic_result(raw)
```

One call only. No retries inside the same attempt, no second judge, no Tavily fallback. Provider/timeout/parse failure is returned as semantic `RETRY` state for later scheduled execution.

Prompt asks only the approved four questions:

1. supported by supplied evidence?
2. avoids unjustified deletion of still-correct important info?
3. materially more accurate/current/clear?
4. avoids obvious contradiction with current page/evidence?

The model returns H2 section bodies only, never frontmatter/source YAML/full page.

- [ ] **Step 4.6 — Run queue/evaluator GREEN**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_w5b_evolution.py -q
```

At this point APPLY does not yet need to mutate a page; Task 5 wires promotion.

- [ ] **Step 4.7 — Commit**

```bash
git add scripts/wiki_evolve.py tests/unit/test_wiki_w5b_evolution.py
git commit -m "feat(wiki-v2-w5b): add autonomous evolution queue and evaluator"
```

---

## Task 5: Fresh promoted patch + APPLY/RETRY/REJECT state transitions

**Files:**
- Modify: `scripts/wiki_evolve.py`
- Extend: `tests/unit/test_wiki_w5b_evolution.py`

- [ ] **Step 5.1 — Write RED end-to-end worker tests**

Fixture a canonical existing page + W3 suggestion and stub exactly one evaluator result for each path.

Assert:

### APPLY

- worker rereads latest page **before** LLM call;
- original historical `suggested_content` is ignored as authoritative input;
- worker builds a **fresh** patch with current `base_digest`;
- operations are exactly:

```text
MERGE_SOURCES
UPSERT_SECTION (one or more)
SET_METADATA(last_updated only, unless an already-safe existing field is intentionally preserved)
```

- no `CREATE_PAGE`, `REPLACE_PAGE`, delete, or raw whole-page op appears;
- `apply_patch(..., semantic_approved=True)` is called;
- compiler `applied` => same suggestion state becomes `applied`, `applied_patch_id` set.

### RETRY

- no page mutation;
- `attempts += 1`;
- `next_retry_at` follows 1d/3d/7d;
- `last_decision="RETRY"`, reason persisted.

### REJECT

- no page mutation;
- suggestion becomes terminal `rejected`;
- no Error Book entry solely for semantic reject.

### conflict

- simulate page change after LLM call but before apply;
- compiler returns `conflict`;
- page not overwritten;
- suggestion becomes `retry`, not Error Book corruption.

### compiler candidate rejection

- bad model citation/candidate remains blocked even with semantic approval;
- page unchanged;
- compiler integrity failure remains Error Book-visible;
- queue state becomes retryable rather than pretending it applied.

### superseded

- update target missing/replaced such that suggestion is no longer meaningful => terminal `superseded`; no page creation from an old update suggestion.

- [ ] **Step 5.2 — Fresh promoted patch identity**

Build promoted `WikiPatch` from the latest page, hydrated evidence, and model sections.

Use a deterministic per-base evolution pack id such as:

```python
promoted_pack_id = (
    f"{original.evidence_pack_id}:w5b:{current_digest[:16]}"
)
```

Then:

```python
patch_id = stable_patch_id(
    target_slug=original.target_slug,
    evidence_pack_id=promoted_pack_id,
    operations=operations,
)
```

Do not include `created_at` in identity.

Use a trigger that preserves origin while marking W5B, e.g. `f"{original.trigger}:w5b"`; do not erase source provenance.

- [ ] **Step 5.3 — Attempts semantics**

Increment `attempts` once per normal worker attempt that reaches evaluation or an evidence condition that requires scheduled retry. Do not increment merely because a terminal/not-due file was scanned.

A normal attempt makes at most one LLM call.

- [ ] **Step 5.4 — Dry-run must be side-effect free**

`--dry-run` may make the one evaluator call, but:

- never call authoritative `apply_patch()` in a way that writes;
- never mutate Wiki page;
- never write/update suggestion state;
- report `would_apply|would_retry|would_reject|would_supersede` only.

Use temp/preview rendering if needed; do not fake an authoritative apply into the real Wiki root.

- [ ] **Step 5.5 — Run promotion safety regressions**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_w5b_evolution.py \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py \
  tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_citations.py -q
```

- [ ] **Step 5.6 — Commit**

```bash
git add scripts/wiki_evolve.py tests/unit/test_wiki_w5b_evolution.py
git commit -m "feat(wiki-v2-w5b): promote approved scoped Wiki updates safely"
```

---

## Task 6: Historical bootstrap discovery + exact coverage accounting

**Files:**
- Modify: `scripts/wiki_evolve.py`
- Create: `tests/unit/test_wiki_w5b_bootstrap.py`

Bootstrap is a **mode of the same script**. Do not create another worker/service/module.

- [ ] **Step 6.1 — Write RED denominator/accounting tests**

Fixture mixed historical rows:

```text
wechat A ok + processed
rss B    ok + processed
wechat C ok + LightRAG failed
rss D    failed + processed
```

Assert denominator is A/B only and metrics reconcile.

Required report keys:

```text
eligible_processed_ingestions
mapped_via_entity_buffer
mapped_via_lightrag_graph
unmapped_needing_llm_fallback
seeded_entity_jobs
no_wiki_entity
retry_unresolved
```

Maintain an in-memory final accounting keyed by `(source, article_id)` so every denominator article ends exactly as:

```text
represented
no_wiki_entity
retry_unresolved
```

At end assert:

```python
eligible == represented + no_wiki_entity + retry_unresolved
```

No row may vanish between phase counters.

- [ ] **Step 6.2 — Buffer-first mapping test**

Given canonical `<ref>_entities.json`, assert the historical article is mapped from buffer and **not** graph/fallback-scanned first.

Reuse the same canonical-first buffer dir resolution as `kb/wiki_update.DEFAULT_BUFFER_DIRS`; do not invent another path list.

- [ ] **Step 6.3 — Graph fallback mapping test with no top-N cutoff**

Fixture:

```text
vdb_entities.json
vdb_relationships.json
kv_store_text_chunks.json
kv_store_full_docs.json
```

Use the existing W1 split semantics for `source_id` (`re.split(r"[<>|\s]+", ...)`, `chunk-*` only).

Map:

- entity row `entity_name -> source_id chunks`;
- relationship row source chunks to **both** `src_id` and `tgt_id` entity names;
- chunks -> source-aware articles via Task 1 helper.

Assert an entity outside a synthetic “top 50” ordering is still discovered. Do not call `wiki_rank_entities.py --top N` for coverage.

Graph discovery runs only for eligible articles with no usable buffer mapping.

- [ ] **Step 6.4 — Preserve repeated-entity noise control**

Build groups from local buffer/graph mappings.

An entity seen in `>=2` distinct eligible article keys immediately becomes a seedable historical entity job.

Then compute **article coverage**, not entity count:

```python
represented = articles belonging to at least one seedable >=2 group
uncovered = eligible - represented
```

An article can have local singleton entities and still be “uncovered” for Wiki purposes; it must reach the fallback instead of silently counting as mapped.

- [ ] **Step 6.5 — Bootstrap-only DeepSeek fallback tests**

For each uncovered article, exactly one fallback call receives local title/text only and strict JSON instruction:

```json
{"entities": ["up to 3 genuinely wiki-worthy entity names"]}
```

or:

```json
{"entities": []}
```

Behavior:

- valid names: slugify/dedupe, mark article represented, seed those groups even when the LLM has explicitly selected a single-article wiki-worthy entity;
- empty list: terminal bootstrap accounting `no_wiki_entity`;
- timeout/provider/malformed JSON: `retry_unresolved`;
- max 3 names; extra names invalidate/retry rather than silently truncating model contract.

No Tavily/web/provider-router call.

- [ ] **Step 6.6 — Bootstrap dry-run**

`--bootstrap-existing --dry-run` performs:

- denominator;
- buffer mapping;
- graph mapping;
- uncovered count;

but makes **no** fallback LLM calls and writes no Wiki/suggestion/state. Report `would_need_llm_fallback` (may be an extra report field) for uncovered count.

- [ ] **Step 6.7 — Exit-code contract**

Keep operational semantics simple:

```text
bootstrap normal:
  0 = exact accounting and retry_unresolved == 0
  2 = retry_unresolved > 0 (retryable/incomplete coverage)
  1 = integrity/runtime failure or accounting mismatch

bootstrap dry-run:
  0 = read-only mapping/accounting completed
  1 = integrity/runtime failure
```

Normal evolution mode may return 0 with ordinary queued RETRY outcomes; they are expected state, not process failure.

- [ ] **Step 6.8 — Run discovery GREEN**

```bash
venv/bin/python -m pytest tests/unit/test_wiki_w5b_bootstrap.py -q
```

- [ ] **Step 6.9 — Commit**

```bash
git add scripts/wiki_evolve.py tests/unit/test_wiki_w5b_bootstrap.py
git commit -m "feat(wiki-v2-w5b): add historical article coverage discovery"
```

---

## Task 7: Seed historical groups through W5A/W3, including create-then-evolve

**Files:**
- Modify: `scripts/wiki_evolve.py`
- Modify: `kb/wiki_compiler/adapters/w3.py` only if a tiny resolved-record pack helper is needed.
- Extend: `tests/unit/test_wiki_w5b_bootstrap.py`

No second renderer/suggestion writer.

- [ ] **Step 7.1 — Write RED existing-page seed test**

For a historical entity group whose Wiki page already exists:

```text
resolved historical article records
 -> W3 EvidencePack with real titles/source metadata
 -> propose_w3_patch()
 -> apply_patch(default semantic_approved=False)
```

Assert:

- page digest unchanged;
- result is deterministic `suggestion`;
- suggestion contains full serialized patch;
- same inputs rerun to same suggestion path;
- no timestamp-spam file;
- if evolution state already exists, W3 re-seed preserves it.

- [ ] **Step 7.2 — Write RED missing-page create-then-suggestion test**

For a selected historical entity with no page:

1. build W3 pack;
2. propose canonical `CREATE_PAGE`;
3. default W5A compiler auto-applies source-backed skeleton;
4. reread the newly created page and rebuild pack/digest;
5. propose existing-page substantive patch;
6. default compiler writes deterministic structured suggestion.

Assert final state has **both**:

```text
entities/<slug>.md exists with canonical typed sources + [^N]
AND
_suggestions/<slug>-<patch-id>.json exists for semantic evolution
```

A create without the follow-up suggestion fails the test.

- [ ] **Step 7.3 — Historical provenance/identity**

Resolved historical packs should carry a clear trigger such as `w3_historical_bootstrap` while using the same W3 assembler/apply path.

Pack identity must be deterministic over sorted source-aware article keys and slug; no timestamp in `pack_id`/`patch_id`.

WeChat-only ongoing W3 identity compatibility from Task 2 remains unchanged.

- [ ] **Step 7.4 — Conflict/failure accounting**

If bootstrap create/update encounters:

- digest conflict;
- candidate rejection;
- malformed source evidence;
- write failure;

it must **not** count that article as successfully represented for bootstrap closure. Convert affected article keys to `retry_unresolved` and return bootstrap incomplete rather than lying about coverage.

- [ ] **Step 7.5 — Idempotent rerun**

Run bootstrap seeding twice against the same temp Wiki root:

- no duplicate page;
- no second timestamp suggestion;
- same deterministic suggestion path;
- terminal existing evolution state preserved;
- accounting remains exact.

- [ ] **Step 7.6 — Run full bootstrap GREEN**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_w5b_bootstrap.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_wiki_compiler_engine.py -q
```

- [ ] **Step 7.7 — Commit**

```bash
git add scripts/wiki_evolve.py kb/wiki_compiler/adapters/w3.py \
  tests/unit/test_wiki_w5b_bootstrap.py tests/unit/test_wiki_compiler_w3_convergence.py
git commit -m "feat(wiki-v2-w5b): seed historical coverage through shared compiler"
```

---

## Task 8: Systemd normal-mode worker + adversarial/Ponytail regression gate

**Files:**
- Create: `deploy/aliyun/systemd/omnigraph-wiki-evolve.service`
- Create later in this task after live timer recon: `deploy/aliyun/systemd/omnigraph-wiki-evolve.timer`
- Modify: `deploy/aliyun/systemd/README.md`
- All W5B/W5A tests as needed.

### 8A — Static service file

- [ ] **Step 8.1 — Add service using current Aliyun runtime conventions**

Match the verified ingest unit conventions unless live recon disproves them:

```ini
[Unit]
Description=OmniGraph Wiki autonomous evolution worker
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/wiki_evolve.py --limit 10
StandardOutput=journal
StandardError=journal
```

Do not enable bootstrap in systemd. `--bootstrap-existing` is manual rollout only.

Set a finite `TimeoutStartSec` after measuring a bounded manual run; do not copy the ingest service's 300s blindly if one DeepSeek call × limit can legitimately exceed it.

### 8B — Adversarial implementation review

- [ ] **Step 8.2 — Run fresh attack checklist before production**

A reviewer not relying on implementation self-description must inspect actual diff/code and answer each:

1. Can semantic approval bypass critical metadata / `created` immutability?
2. Can semantic approval bypass base digest, flock, citation validation, or atomic write?
3. Can any code path write a full page from LLM output?
4. Can MERGE_SOURCES remove a source?
5. Can W3 call DeepSeek/Tavily/network after Task 2?
6. Does current-batch W3 still include failed/skipped candidates?
7. Does RSS resolution accidentally use its 32-char content/body hash?
8. Can an unknown `ingestions.source` silently disappear?
9. Can historical coverage denominator be reduced to “files with buffers”?
10. Does graph coverage accidentally use top-N centrality output?
11. Can an uncovered historical article vanish without represented/no_wiki/retry accounting?
12. Can bootstrap success while `retry_unresolved > 0`?
13. Can missing-page historical create end without a queued substantive evolution suggestion?
14. Can same W3 patch reset `evolution.status=applied|rejected|retry`?
15. Can normal worker make two LLM calls in one attempt?
16. Can dry-run mutate Wiki or suggestion JSON?
17. Can old `suggested_content` be blindly applied?
18. Can stale page during LLM call be overwritten?
19. Can legacy page receive canonical citations that its source representation cannot support?
20. Did W6/query-eval/navigation or a new queue/source/provider framework creep in?

Any “yes” to an unsafe question is blocking.

### 8C — Full regression

- [ ] **Step 8.3 — Run W5B + W5A focused suite**

```bash
venv/bin/python -m pytest \
  tests/unit/test_wiki_articles.py \
  tests/unit/test_wiki_w5b_ongoing_coverage.py \
  tests/unit/test_wiki_w5b_evolution.py \
  tests/unit/test_wiki_w5b_bootstrap.py \
  tests/unit/test_wiki_compiler_models.py \
  tests/unit/test_wiki_compiler_assembler.py \
  tests/unit/test_wiki_compiler_engine.py \
  tests/unit/test_wiki_compiler_candidate_gates.py \
  tests/unit/test_wiki_compiler_w1_adapter.py \
  tests/unit/test_wiki_compiler_w3_convergence.py \
  tests/unit/test_wiki_w5_0.py \
  tests/unit/test_wiki_citations.py \
  tests/unit/test_wiki_lint.py \
  tests/unit/test_ingest_from_db_orchestration.py \
  tests/unit/test_reconcile_ingestions.py \
  tests/unit/test_reconcile_rss.py \
  tests/unit/test_dual_source_dispatch.py -q
```

Then run the broader unit suite if environment permits:

```bash
venv/bin/python -m pytest tests/unit -q
```

If unrelated pre-existing failures exist, record exact tests/trace and prove the W5B diff did not cause them; never call a red relevant suite PASS.

- [ ] **Step 8.4 — Ponytail/YAGNI deletion review**

Explicitly attempt to delete/simplify:

- any new class around article source identity;
- any queue/repository/manager abstraction used once;
- any evaluator class wrapping one function call;
- any bootstrap service/timer separate from normal worker;
- any duplicated W1/W3 source resolver;
- any new persistence file not required by approved spec;
- any W6/search/query-eval code.

Target final new runtime architecture remains **two new Python files only**: `kb/wiki_articles.py` and `scripts/wiki_evolve.py`.

- [ ] **Step 8.5 — Commit static runtime/service + review fixes**

```bash
git add deploy/aliyun/systemd/omnigraph-wiki-evolve.service \
  deploy/aliyun/systemd/README.md \
  kb/wiki_articles.py scripts/wiki_evolve.py kb/wiki_compiler \
  kb/wiki_update.py batch_ingest_from_spider.py scripts/wiki_health.py \
  scripts/wiki_generate_pages.py tests/unit
git commit -m "test(wiki-v2-w5b): close adversarial and Ponytail gates"
```

Only stage files actually changed for W5B; the broad command above is a checklist, not permission to stage unrelated work.

---

## Task 9: Aliyun production recon, historical bootstrap UAT, normal-worker rollout

**Production changes make this task mandatory. Do not mark W5B PASS from local tests only.**

### 9A — Reconcile Git and live runtime truth

- [ ] **Step 9.1 — Reconcile latest `origin/main` without force push**

Before deploy:

```bash
git fetch origin
git status --short --branch
git log --oneline --decorate -10
git diff --name-only origin/main...HEAD
```

If remote moved during W5B, rebase/merge carefully in an isolated worktree, rerun Task 8 relevant tests, then push normally. Exclude unrelated concurrent commits from the W5B scope report.

- [ ] **Step 9.2 — Rediscover production truth**

On the live host, record:

```bash
hostname
pwd
git rev-parse HEAD
readlink -f /root/OmniGraph-Vault/venv-aim1/bin/python
systemctl list-timers --all | grep -E 'omnigraph|wiki'
systemctl list-units --type=service | grep omnigraph
```

Do not assume the historical host/IP/service schedule if live truth differs.

- [ ] **Step 9.3 — Audit live article sources and schema**

Using the production DB path discovered from env/config:

```sql
SELECT source, COUNT(*)
FROM ingestions
GROUP BY source
ORDER BY source;
```

Also inspect `PRAGMA table_info(articles)` and `PRAGMA table_info(rss_articles)`.

Completion blocker: any live `ingestions.source` that is neither explicitly supported by `kb/wiki_articles.py` nor explicitly documented as non-Wiki-eligible.

For current expected schema, prove both WeChat and RSS resolver paths with real rows.

### 9B — Historical read-only recon

- [ ] **Step 9.4 — Establish pre-change coverage evidence**

Run a read-only resolver/bootstrap dry-run with the production DB/LightRAG/entity buffers:

```bash
/root/OmniGraph-Vault/venv-aim1/bin/python scripts/wiki_evolve.py --bootstrap-existing --dry-run
```

Capture the machine-readable summary, including:

```text
eligible_processed_ingestions
mapped_via_entity_buffer
mapped_via_lightrag_graph
would_need_llm_fallback
```

Prove denominator comes from successful+processed ingestion truth, not buffer count.

- [ ] **Step 9.5 — Prove ongoing RSS blind spot is fixed**

Use a real RSS `ingestions.status=ok` row and its URL-derived ref. In an isolated temp Wiki/entity-buffer fixture using production data, prove W3 resolves the RSS record through `rss_articles` and can produce a pack/suggestion when the frequency/evidence conditions are met.

Also prove a failed/skipped row does not enter the new current-batch W3 success set.

### 9C — Isolated Wiki root UAT before production Wiki mutation

- [ ] **Step 9.6 — Copy/create an isolated Wiki root**

Use real production article evidence and LightRAG stores, but an isolated Wiki root. Do not manufacture fake claims into the authoritative production Wiki.

Prove at minimum:

1. WeChat local hydration;
2. RSS local hydration;
3. buffer historical mapping;
4. graph-only mapping for a real article if available;
5. fallback-unmapped behavior using an isolated controlled record/fixture;
6. missing-page canonical create + immediate substantive suggestion;
7. existing-page suggestion digest unchanged before semantic worker;
8. semantic APPLY through `semantic_approved=True`;
9. semantic RETRY no write;
10. semantic REJECT no write;
11. stale-base conflict no overwrite;
12. invalid citation/candidate remains blocked.

- [ ] **Step 9.7 — One real production DeepSeek structured call**

Under the production venv/env, run one bounded real normal-mode evaluator against isolated Wiki data. Record raw decision class and successful strict parse. Do not expose API keys in logs/report.

### 9D — Production historical bootstrap

- [ ] **Step 9.8 — Deploy code/service with timer disabled**

Install/sync code and service unit, then:

```bash
systemctl daemon-reload
systemctl disable --now omnigraph-wiki-evolve.timer 2>/dev/null || true
```

Do not enable the timer yet.

- [ ] **Step 9.9 — Run authoritative production bootstrap**

```bash
/root/OmniGraph-Vault/venv-aim1/bin/python scripts/wiki_evolve.py --bootstrap-existing
```

Required before continuing:

```text
retry_unresolved == 0
AND
eligible_processed_ingestions
  == represented_articles + no_wiki_entity
```

If exit code 2 / unresolved >0, fix/retry the bounded cause. Do **not** waive unresolved historical articles and do not enable timer.

Record:

- denominator count by source;
- buffer-mapped count;
- graph-mapped count;
- fallback-call count;
- explicit no_wiki_entity count;
- seeded entity-job count;
- pages created;
- substantive suggestions seeded;
- final reconciliation equation.

- [ ] **Step 9.10 — Standalone Wiki health after bootstrap seeding**

Run:

```bash
/root/OmniGraph-Vault/venv-aim1/bin/python scripts/wiki_health.py \
  --wiki-root kb/wiki --db-path <LIVE_DB_PATH> --json
```

Blocking: new ERRORs caused by W5B, invalid RSS citation refs, malformed pages, duplicate slugs. Existing known WARNs must be separated from new regressions.

### 9E — Bounded real normal worker and ongoing W3 proof

- [ ] **Step 9.11 — Manual bounded normal worker**

Run a dry-run first:

```bash
/root/OmniGraph-Vault/venv-aim1/bin/python scripts/wiki_evolve.py --dry-run --limit 3
```

Then one bounded authoritative cycle:

```bash
/root/OmniGraph-Vault/venv-aim1/bin/python scripts/wiki_evolve.py --limit 3
```

Prove at least one real historical seeded suggestion can safely converge to `applied`, `rejected`, or scheduled `retry` without human approval. Verify page/suggestion digests/state and journal output.

- [ ] **Step 9.12 — Observe/execute one bounded ongoing ingest cycle**

Use production-safe existing ingest controls (`--max-articles`/current service discipline). Prove:

- W3 hook still wrapped in 120s timeout;
- service completes/healthy;
- current successful refs only;
- if a successful RSS article is present, it no longer disappears at W3 source resolution;
- no W3 network/LLM call.

### 9F — Choose and enable daily timer from live truth

- [ ] **Step 9.13 — Select exact `OnCalendar` from current live timer schedule**

From `systemctl list-timers --all`, choose a concrete daily UTC time with a safe non-overlap gap from all ingest services. Record the chosen clock + rationale in `deploy/aliyun/systemd/omnigraph-wiki-evolve.timer` and README.

This step intentionally happens after live recon because the approved design forbids inventing a clock time from stale documentation.

Timer shape:

```ini
[Unit]
Description=OmniGraph Wiki autonomous evolution daily timer

[Timer]
OnCalendar=*-*-* <LIVE-VERIFIED-UTC-TIME>
Persistent=true

[Install]
WantedBy=timers.target
```

The committed file must contain an actual concrete time; `<LIVE-VERIFIED-UTC-TIME>` must never appear in final code.

Commit/push the concrete timer, deploy it, then:

```bash
systemctl daemon-reload
systemctl enable --now omnigraph-wiki-evolve.timer
systemctl status omnigraph-wiki-evolve.timer --no-pager
systemctl list-timers --all | grep omnigraph-wiki-evolve
```

- [ ] **Step 9.14 — Final service/health verification**

Verify:

```bash
systemctl status <CURRENT_INGEST_SERVICE> --no-pager
systemctl status omnigraph-wiki-evolve.timer --no-pager
journalctl -u omnigraph-wiki-evolve.service -n 100 --no-pager
```

Run Wiki health once more after the bounded normal worker.

### 9G — Closeout documents and final verifier

- [ ] **Step 9.15 — Write implementation verification record**

Create/update the W5B verification/summary location used by the current planning convention. Include:

- final W5B commit range only;
- test commands + fresh outputs/counts;
- live host/path/venv/service/timer truth;
- live ingestion source audit;
- historical denominator reconciliation;
- RSS ongoing proof;
- bootstrap fallback/no_wiki counts;
- APPLY/RETRY/REJECT/conflict/invalid-candidate UAT evidence;
- Wiki health result;
- timer exact time + why it does not collide;
- explicit Ponytail review result.

Do not paste secrets or entire article content.

- [ ] **Step 9.16 — Independent final verification**

A verifier must inspect actual final HEAD/diff and not rely on the implementer's summary. It must specifically verify:

```text
Historical coverage: denominator exact, retry_unresolved=0
Ongoing coverage: WeChat + RSS source-aware, successful-only
RSS identity: md5(url)[:10], never rss content_hash
W3 isolation: no network/LLM + 120s timeout
Evolution: exactly one normal DeepSeek call
Semantic promotion: only via semantic_approved=True
W5A safety: digest/flock/citation/metadata/atomic intact
Suggestion state: deterministic file, terminal/retry state preserved
No destructive whole-page path
No W6/query-eval/framework creep
Production timer enabled only after bounded UAT
```

Only after fresh evidence for all gates may the implementation report exactly:

```text
W5B RESULT: PASS
```

Otherwise report:

```text
W5B RESULT: BLOCKED
```

with the narrow blocker and no false completion claim.

---

## Final Acceptance Matrix

| Gate | Required proof |
|---|---|
| **A — Ponytail architecture** | Only one evolution runtime script + one small local article helper + small W3/compiler changes + one normal timer; no framework/DB/daemon/backfill service. |
| **B — Historical coverage** | Every eligible `status=ok + LightRAG processed` historical article ends represented or explicit `no_wiki_entity`; `retry_unresolved=0`. |
| **C — Ongoing coverage** | Every live Wiki-eligible `ingestions.source` has explicit resolver; current WeChat/RSS success paths work; failed/skipped do not seed W3. |
| **D — Autonomous state machine** | Due suggestions converge to applied/rejected/retry/superseded without routine human approval. |
| **E — Local grounding** | Real local title/body; source-aware ref; missing evidence retries; no W5B web retrieval. |
| **F — One normal LLM call** | Exactly one DeepSeek completion per normal attempt; bootstrap fallback only for locally uncovered history. |
| **G — W5A authoritative safety** | `semantic_approved` relaxes only existing-page UPSERT policy; digest/lock/evidence/citation/metadata/atomic gates still block unsafe writes. |
| **H — No destructive rewrite** | Model returns scoped H2 bodies; no whole-page replace/delete/source subtraction. |
| **I — W3 isolation** | Local-only W3, successful-only refs, outer 120s timeout preserved. |
| **J — Production proof** | Historical reconciliation closes, RSS ongoing proof passes, health/regression clean, bounded worker UAT clean, timer enabled afterward. |
| **K — Ponytail final review** | Reviewer demonstrates no unnecessary class/package/queue/source/provider/query-eval subsystem remains. |

---

## Expected W5B Exit State

```text
ONE-TIME HISTORICAL
successful+processed WeChat/RSS articles
  -> source-aware denominator
  -> entity buffer
  -> LightRAG graph/chunk mapping
  -> DeepSeek fallback only for articles still uncovered
  -> exact represented | no_wiki_entity accounting
  -> W5A/W3 canonical create when missing
  -> deterministic substantive suggestion

ONGOING
current-batch status=ok + doc_confirmed WeChat/RSS only
  -> source-aware local W3
  -> deterministic suggestion queue

AUTONOMOUS MAINTENANCE
same suggestion JSON
  -> due-state check
  -> source-aware local hydration
  -> exactly one DeepSeek semantic decision
  -> APPLY | RETRY | REJECT
  -> fresh scoped WikiPatch against latest digest
  -> apply_patch(...semantic_approved=True)
  -> existing W5A digest/flock/citation/metadata/atomic safety
  -> same suggestion state updated
```

After W5B final PASS, move to **W6 design/brainstorming only**. Do not begin W6 implementation from this plan.