# arx-3 Phase 1 — DECISION (REVISED)

**Phase:** arx-3 (Long-form citation compliance + KG search empty-results fix + Q1 chunk-metadata verification)
**Date:** 2026-05-26 (revised post-K1/K2/Q1 surfacing)
**Gate:** Phase 1 DECIDE (REVISED) → halt → await `go plan G+K1` / `halt revise: <X>`

---

## 0. Preamble — hash-length refutation (carried forward from RESEARCH.md § H, unchanged)

User's hash-length theory (`/api/articles/43c013601f9d`, 12 chars → relax `_HASH_PAT` from `{10}` to `{12}` or `[a-f0-9]+`) is **REFUTED** in RESEARCH.md § H.

Evidence summary (full detail in RESEARCH.md § H.1):

- Canonical generator at `kb/data/article_query.py:148` uses `hashlib.md5(...).hexdigest()[:10]` (single source of truth)
- Decision **D-20** (`kb/docs/02-DECISIONS.md:251,331`) freezes `URL = md5[:10]`
- 5 hardcoded `[a-f0-9]{10}` sites; **zero** `{12}` matches anywhere in `kb/`
- Aliyun homepage probe: 20 of 20 article URLs are 10 chars
- SSG output: 100% match `[a-f0-9]{10}\.html`
- Direct `GET /api/articles/43c013601f9d` → **HTTP 404** (the 12-char hash doesn't exist)
- Probable misobservation: `kb/services/job_store.py:40` uses `uuid.uuid4().hex[:12]` for synthesize-job IDs — that's almost certainly what the user saw in Network tab

**`_HASH_PAT = r"/article/([a-f0-9]{10})"` stays as-is. No regex change in arx-3.**

One outlier flagged for follow-up (out of scope): `kb/export_knowledge_base.py:558` has a `[:12]` slice (likely chunk-id, separate concern).

---

## 0.5 What changed in this revision

User HALT after first DECISION.md draft surfaced **scope incompleteness**: G-remove fixes `/api/synthesize` long-form answer rendering, but the **original screenshot symptom (KG search tab empty)** is `/api/search/kg` — different code path, different worker (`_kg_local_worker`), G-remove does NOT cover it.

This revision adds:

- **K1 (KG SEARCH FALLBACK — ship tonight alongside G-remove):** ~10-15 LoC fallback inside `_kg_local_worker` that calls `search_index.fts_query` when LLM emits non-empty markdown but zero `/article/{hash}` citations
- **K2 (DEFERRED v1.1):** Replace `_kg_local_worker` LLM-synthesize-then-grep with direct LightRAG retrieval + chunk-metadata article extraction. **Now unblocked by Q1.**
- **Q1 (Phase 1 read-only verification — EXECUTED THIS TURN):** Sampled production `vdb_chunks.json` schema. Verdict: K2 viable for v1.1.

Revised tonight scope: **G-remove + K1 atomic** (~16 LoC + 6-9 tests + Q1 addendum + browser UAT, single commit, single deploy).

---

## 1. Options on the table (REVISED)

### Option G-remove (recommended — `/api/synthesize` long-form fix)

**Patch:** 1-line change at `kb/services/synthesize.py:552`.

```python
# BEFORE
confidence: ConfidenceLevel = "kg" if sources else "no_results"

# AFTER
confidence: ConfidenceLevel = "kg" if markdown.strip() else "no_results"
```

**Theory:** `kg_synthesize.synthesize_response()` already returns full markdown with images (verified by AR Gate 4 probe — Probe 2 hybrid: `response_chars=5513` with 3 `/static/img/` refs in raw markdown). The frontend hides the answer because `confidence='no_results'` triggers the empty-state UI. Removing the over-strict gate exposes the real markdown content to the user.

**Tradeoff:** `sources=[]` when LLM doesn't emit `/article/` refs. Source-chip ribbon below answer is empty. The answer body + images render correctly. v1.1 can add chunk-metadata-based source resolution as a separate phase.

**Status:** unchanged from prior draft. Wrapper-preservation audit § 3 + never-500 audit § 4 still apply.

### Option K1 (NEW — `/api/search/kg` empty-results fix, ship atomic with G-remove)

**Patch target:** `kb/api_routers/search.py:_kg_local_worker` (lines 91-146, current shape).

**Current behavior (lines 122-141):**

1. Wraps query with citation directive
2. `markdown = await asyncio.wait_for(synthesize_response(wrapped, mode="local"), ...)`
3. `hashes = list(dict.fromkeys(_HASH_PAT.findall(markdown or "")))`
4. For each hash → `get_article_by_hash(h)` → append result row
5. On any exception → `results=[]`

**The hole:** when step 2 succeeds with non-empty markdown but step 3 returns `[]` (LLM didn't emit `/article/` citations — same cross-provider regression observed for long_form), step 4 builds zero rows. User's KG search tab shows empty results despite the LLM having actually retrieved relevant content.

**K1 patch:** insert FTS5 fallback BETWEEN step 4 and the final `update_job` call. When `markdown.strip()` is non-empty AND `results == []` after the hash-resolution loop:

```python
# K1 fallback — LLM emitted non-empty markdown but zero parseable /article/ citations
# (cross-provider regression — same root cause as G-remove). Degrade gracefully to
# FTS5 keyword-match articles so the KG search tab is non-empty for the user.
if not results and markdown and markdown.strip():
    logger.warning(
        "kg_local_worker_fts_fallback jid=%s reason=no_citations_in_markdown markdown_len=%d",
        job_id, len(markdown),
    )
    try:
        fts_rows = search_index.fts_query(query, lang=None, limit=10)
        results = [
            {"hash": h, "title": t, "snippet": s, "lang": lg, "source": src}
            for (h, t, s, lg, src) in fts_rows
        ]
    except Exception as fts_err:  # noqa: BLE001 — graceful degrade, never raise
        logger.warning("kg_local_worker_fts_fallback_failed jid=%s err=%s", job_id, fts_err)
        results = []  # explicit reset; keep the never-raise contract intact
```

**~12 LoC** (the conditional + try/except + log lines).

**Why this is wrap-don't-mutate (Skill discipline Rule 1 in `search.py:16` + project memory `kg_synthesize is core asset, no bypass`):**

- `kg_synthesize.synthesize_response` is **NOT modified** — still called at line 122-125 unchanged
- `omnigraph_search.query.search` C2 signature is **NOT touched** — that's `_kg_worker` (line 56-70), a different function on the `/api/search?mode=kg` path
- LightRAG retrieval still runs first; FTS is the **fallback**, not the primary substrate
- Never-raise contract in the outer `except Exception` (line 142-144) is preserved — the new try/except does its own catch

**Tradeoff (must document in user-visible response somehow — TBD in Phase 2 PLAN):** when fallback fires, results are FTS keyword-match (BM25-trigram), NOT semantic-KG-ranked. UX is degraded vs ideal but **NOT empty** — which is the original screenshot symptom.

### Option K2 (DEFERRED to v1.1 — unblocked by Q1)

**Goal:** Replace the LLM-synthesize-then-grep architecture in `_kg_local_worker` with direct chunk-metadata extraction:

1. Call LightRAG `aquery(only_context=True)` to retrieve top-N relevant chunks (no LLM synthesis)
2. Read `full_doc_id` field from each chunk (Q1 verified present in 1967/1967 chunks)
3. Parse `wechat_<10char_hash>` → article hash
4. `get_article_by_hash(hash)` → result rows

This bypasses the LLM-citation-emission failure mode entirely (no LLM in the search path). Estimated ~50-80 LoC + new tests + retrieval-quality validation.

**Status:** v1.1 phase scope. Q1 verification (§ 1.7 below) confirms feasibility. Do NOT plan in arx-3.

---

## 1.7 Q1 — Production chunk metadata schema verification (READ-ONLY, EXECUTED 2026-05-26)

**Method:** SSH `aliyun-vitaclaw` (read-only Python json.load against live `vdb_chunks.json`).

**Source file:** `/root/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json` (55 MB, mtime 2026-05-26 21:17 — current production state).

**Top-level structure:**

```json
{
  "embedding_dim": 3072,                    // matches Vertex Gemini-embedding-2 spec
  "data": [...],                             // 1967 chunks
  "matrix": "<base64 zlib>"                 // packed embedding matrix
}
```

**Per-chunk schema (verified 100% present across all 1967 chunks):**

| Field | Type | Example | Use for K2? |
| --- | --- | --- | --- |
| `__id__` | str | `"chunk-4e2ebff8e9cb075039147d54413ebf9e"` | No (chunk PK, not source link) |
| `__created_at__` | int | `1777753152` (unix timestamp) | No (metadata only) |
| `content` | str | `"# FlashQLA：让 Qwen 的注意力层跑得更快\n\nURL: ..."` | Optional (already in prompt context) |
| **`full_doc_id`** | **str** | **`"wechat_a36a66bc44"`** OR **`"wechat_b41671909d_images"`** | **YES — primary linking field** |
| `file_path` | str | `"unknown_source"` (constant) | No (not informative) |
| `vector` | str | `"eJwNl3l8DVcbxxFCJEGSm7vOcmbmzNybvBLFWxK7EBSx7+2rEUtEkCCWEl0Qa5D9brPPmbkXEWIvqoiqfQtqqVir9lbV3vLm3/PX+fyec77P93eXW0gt/K4dUw3+sIzx2NBI6teNcfxWYynqHuwsj1Yus6KWo8aJJ+0p4hplUVlv/y3GSx3WbwYGJd42KGMh+0qXqHxf..."` (zlib-compressed embedding) | No (vector data) |

**Sampled chunks (3 random indices: 0, 100, 1000):**

- `data[0].full_doc_id` = `"wechat_a36a66bc44"` (body chunk)
- `data[100].full_doc_id` = `"wechat_b41671909d_images"` (image-derived chunk)
- `data[1000].full_doc_id` = `"wechat_28c974c2cd_images"` (image-derived chunk)

**Schema consistency:** all 6 keys present in 1967/1967 chunks (no schema drift, no nulls).

**`full_doc_id` format observed:**

- `wechat_<10char_hex_hash>` for body chunks
- `wechat_<10char_hex_hash>_images` for image-extracted chunks (multimodal pipeline)

Both formats expose the canonical 10-char article hash via `re.match(r"wechat_([a-f0-9]{10})(?:_images)?$", full_doc_id).group(1)`.

**K2 viability verdict: ✅ YES**

- Source-article linking field is `full_doc_id` (verified present, schema-consistent)
- Hash format matches the canonical D-20 spec (10-char md5 prefix, recoverable via simple regex)
- LightRAG `aquery(only_context=True)` API is available (LightRAG 1.4.16 spec; not verified in this turn but standard)
- Estimated v1.1 LoC: ~50-80 (worker rewrite + retrieval-quality validation)

**Q1 status: COMPLETE.** No further Phase 1 work blocked on Q1.

---

## 2. Side-by-side comparison: revised tonight scope (G-remove + K1) vs prior alternatives

| Dimension | G-remove + K1 (revised tonight) | G-remove alone (prior draft) | R-narrow (prior alternative) |
| --- | --- | --- | --- |
| **Total LoC delta** | ~13 (1 + ~12) | 1 | ~30-50 |
| **Files touched** | `kb/services/synthesize.py` + `kb/api_routers/search.py` | `kb/services/synthesize.py` | `kb/services/synthesize.py` (+ helper) |
| **Test additions** | 2 unit (G) + 1 integration (G) + 3 unit (K1) + 1 integration (K1) = **7 new** | 2 unit + 1 integration = 3 new | 3-5 unit + 1-2 integration = 4-7 new |
| **`/api/synthesize` long-form fix** | ✅ (G-remove) | ✅ (G-remove) | ⚠️ unknown (LLM compliance gated) |
| **`/api/search/kg` empty-results fix** | ✅ (K1 fallback) | ❌ NOT covered | ❌ NOT covered |
| **Risk: break existing tests** | Low — gate fix + fallback added below an existing graceful-degrade path | Low | High (anchor injection changes prompt shape) |
| **Risk: LLM compliance dependency** | None on G; None on K1 (fallback fires PRECISELY when LLM didn't comply) | None | **HIGH** |
| **Risk: cross-provider drift** | None | None | High |
| **User-visible result (synthesize tab)** | Answer + images render | Answer + images render | (best case) Answer + chips; (likely) Answer + empty chips |
| **User-visible result (search tab)** | Articles always non-empty (KG-ranked OR FTS fallback) | **Empty** (unchanged from current) | Empty (unchanged from current) |
| **Rollback cost** | Revert ~13 LoC across 2 files | Revert 1 line | Revert ~30-50 LoC |
| **Time to ship** | 1.5-2 hours (G + K1 plan + tests + commit + deploy + UAT) | 30-60 min | 2-4 hours + iterative LLM tuning |
| **Atomicity** | 1 commit, 1 deploy, 1 Gate 4 | 1 commit, 1 deploy, 1 Gate 4 | 1 commit, 1 deploy, may need iteration |

**Headline:** G-remove alone fixes only half the symptom (long_form). K1 closes the other half (KG search tab) for ~12 LoC at no LLM-compliance risk. Atomic shipment is strictly dominant — **same deploy, same UAT session, both regressions resolved.**

---

## 3. G-remove — 7-feature wrapper preservation audit (UNCHANGED)

User's claim: G-remove preserves the wrapper's 7 valuable features. Verified each at the cited line numbers in `kb/services/synthesize.py` (1-indexed):

| # | Feature | Line(s) | Verified preserved? |
| --- | --- | --- | --- |
| 1 | `KB_SYNTHESIZE_TIMEOUT` async `wait_for` | **521-524** | ✅ keep — line 552 change does not touch the await/timeout block |
| 2 | FTS5 fallback on C1 fail/timeout | **535** (timeout) + **538** (broad except) | ✅ keep — fallback paths are unchanged; the change is past the try/except, only on the happy path |
| 3 | `_rewrite_image_urls` (260519-s65 belt-and-suspenders) | **549** (call site) + **293+** (definition) | ✅ keep — runs at line 549 before the gate at 552; image URLs still get rewritten |
| 4 | `lang_directive_for` + `_DIRECTIVES` (I18N-07 + QA-02) | **282-290** | ✅ keep — applied at line 500-501 for non-template modes; unaffected by gate |
| 5 | `_LONG_FORM_PROMPT_TEMPLATE_*` + `_QA_PROMPT_TEMPLATE_*` (kb-v2.1-5 + kb-v2.2-4) | **87-122** + **136-162** | ✅ keep — applied at line 498 via `_wrap_question_for_mode`; unaffected by gate |
| 6 | `KG_MODE_AVAILABLE` import-time SA file probe | **245-275** | ✅ keep — module-level, runs at import; gate change is in the request path |
| 7 | `resolve_wiki_context` (W4 wiki context injection, llm-wiki-integration) | **505** | ✅ keep — runs at line 505-506 before C1 call; unaffected by gate |

**All 7 wrapper features verified preserved.** The 1-line patch surgically removes only the over-strict `if sources` predicate.

`_resolve_sources_from_markdown` (line 550) and `_resolve_entities_for_sources` (line 551) **still run** — `sources` and `entities` are still populated when the LLM does emit citations. The ONLY behavior change: when markdown is non-empty AND sources happen to be empty, `confidence='kg'` instead of `'no_results'`.

---

## 3.5 K1 — `_kg_local_worker` invariant audit (NEW)

K1 patches `kb/api_routers/search.py:_kg_local_worker` (lines 91-146). Audit each invariant:

| Invariant | Pre-K1 | Post-K1 | Status |
| --- | --- | --- | --- |
| `synthesize_response` called once with `mode='local'` (line 122-125) | runs first; never bypassed | unchanged — K1 fallback fires AFTER synthesize_response returns and AFTER hash-resolution loop completes | ✅ kg_synthesize is still the primary substrate |
| C2 signature (`omnigraph_search.query.search`) | not touched (different worker, line 56-70) | not touched | ✅ |
| `KB_KG_SEARCH_TIMEOUT` outer budget (line 41, default 90s) | applies to `synthesize_response` only | unchanged — K1 FTS query is fast (P50 < 100ms per kb-v2.2-3) and runs after the timeout-bounded call | ✅ |
| Outer never-raise contract (line 142-144 broad except) | catches everything, returns results=[] | unchanged — K1 fallback has its own try/except, but if its except fires, the outer except still catches anything else | ✅ |
| `_HASH_PAT` regex unchanged | `r"/article/([a-f0-9]{10})"` | unchanged | ✅ (per § 0 hash refutation) |
| Job state machine (running → done, never failed for `_kg_local_worker`) | always reaches `update_job(status="done")` | unchanged — K1 doesn't add a "failed" path | ✅ |
| Result row schema | `{hash, title, snippet, lang, source}` | identical (FTS rows mapped via the same dict comprehension as `search_endpoint` line 181-186) | ✅ |
| Logging discipline (WARNING for diagnostic survives Databricks root=WARNING) | uses `logger.warning` for start/done/errors | K1 adds `logger.warning("kg_local_worker_fts_fallback ...")` consistent with existing pattern | ✅ |
| FTS5 query side effects | `search_index.fts_query` is read-only | unchanged | ✅ |

**K1 invariant audit: all preserved.** The patch is wrap-don't-mutate by construction — the existing `_kg_local_worker` body runs unchanged through line 141; K1 adds a tail-only conditional before the final `logger.warning(...kg_local_worker_done)` and `update_job` calls.

---

## 4. Never-500 invariant audit (G-remove, UNCHANGED)

The `/api/synthesize` endpoint must never return HTTP 500. This contract is defended at three layers:

| Layer | Pre-G-remove | Post-G-remove | Status |
| --- | --- | --- | --- |
| `asyncio.TimeoutError` (line 530) | → `_fts5_fallback` + `return` | unchanged | ✅ |
| broad `Exception` (line 537, `except Exception`) | → `_fts5_fallback` + `return` | unchanged | ✅ |
| `synthesize_response` returns non-str | line 545 `markdown = response if isinstance(response, str) else ""` → `markdown=""` → confidence='no_results' (sources also `[]`) | line 545 unchanged → `markdown=""` → `markdown.strip()=""` → falsy → confidence='no_results' | ✅ |
| `_resolve_sources_from_markdown` raises | already wrapped in try/except returning `[]` (line 339-341) | unchanged | ✅ |
| `_resolve_entities_for_sources` raises | already wrapped in try/except returning `[]` (line 357-360) | unchanged | ✅ |

**Defensive isinstance fallback case (line 545):** when `synthesize_response` returns `None` (3-attempt retry exhausted), `markdown=""`, `markdown.strip()=""` is falsy, gate sets `confidence='no_results'`. Same outcome as pre-G-remove for this edge case. Note: this path **does NOT trigger FTS5 fallback** in either pre- or post-G-remove — FTS5 fallback is only entered on `TimeoutError` or broad `Exception`. The `None` return path persists `result.confidence='no_results'` with empty markdown. (Same behavior as today; not a regression.)

**Never-500 invariant preserved.** Status code is HTTP 200 in all paths.

---

## 4.5 Never-raise invariant audit (K1, NEW)

`/api/search/kg` `_kg_local_worker` MUST never raise out of the BackgroundTask wrapper (would leave job in "running" forever — observed prior bug, see `KB_KG_SEARCH_TIMEOUT` doc-comment line 33-40).

| Path | Pre-K1 | Post-K1 | Status |
| --- | --- | --- | --- |
| `synthesize_response` TimeoutError | caught by outer except (line 142-144) → results=[] → `update_job(done, [])` | unchanged | ✅ |
| `synthesize_response` returns valid markdown WITH `/article/` citations | hashes parsed → loop builds rows → results populated → `update_job(done, results)` | **K1 conditional `not results` is False → fallback skipped → unchanged** | ✅ |
| `synthesize_response` returns valid markdown WITHOUT `/article/` citations | hashes=[] → loop runs zero times → results=[] → `update_job(done, [])` (the regression — empty UI) | **K1 fallback fires → fts_query → results populated → `update_job(done, fts_results)`** | ✅ FIXED |
| `synthesize_response` returns empty markdown (defensive None case) | hashes=[] → results=[] → `update_job(done, [])` | **K1 conditional `markdown.strip()` is falsy → fallback skipped → results=[] → unchanged** | ✅ (no spurious FTS results when LLM produced nothing) |
| `get_article_by_hash` raises for one hash | inner except (line 130-132) → `continue` → other hashes still processed | unchanged | ✅ |
| `search_index.fts_query` raises | (no prior path) | **K1 inner try/except → logged + results=[] → `update_job(done, [])`** | ✅ |
| Anything else unexpected | outer except (line 142-144) → results=[] | unchanged (K1's inner except does NOT shadow this — outer still catches anything K1's try/except didn't) | ✅ |

**K1 never-raise invariant preserved.** All paths reach `update_job(status="done")` with a list (possibly empty).

---

## 5. Test design (Phase 2 TDD spec — REVISED for G-remove + K1)

Per user directive, on `go plan G+K1` proceed to Phase 2 PLAN.md with these tests.

### 5.1 G-remove tests (existing, unchanged)

#### Unit test 1: real markdown, no `/article/` refs → `confidence='kg'`, `sources=[]`

```python
# tests/unit/test_synthesize_confidence_gate.py (new)
async def test_confidence_kg_when_markdown_present_but_no_citations(...):
    # Given: synthesize_response mocked to return real markdown WITHOUT /article/ refs
    # When: synthesize_for_job runs
    # Then: result.confidence == "kg"
    #       result.markdown == <the mocked markdown>
    #       result.sources == []
    #       result.fallback_used == False
```

#### Unit test 2: empty markdown → `confidence='no_results'`

```python
async def test_confidence_no_results_when_markdown_empty(...):
    # Given: synthesize_response mocked to return "" (or None → defensive fallback)
    # When: synthesize_for_job runs
    # Then: result.confidence == "no_results"
    #       result.markdown == ""
    #       result.sources == []
    #       result.fallback_used == False
    #       (no TimeoutError, no broad Exception → FTS5 fallback NOT triggered)
```

#### Integration test: POST /api/synthesize, mocked C1, no citations

```python
# tests/integration/test_synthesize_router_confidence_gate.py (new)
def test_synthesize_returns_200_with_confidence_kg_when_markdown_has_no_citations(...):
    # Given: kg_synthesize.synthesize_response monkeypatched to return real markdown w/o /article/
    # When: client.post("/api/synthesize", json={"question": "test", "lang": "en", "mode": "long_form"})
    # Then: response.status_code == 200
    #       result["confidence"] == "kg"
    #       result["markdown"] contains the LLM content
    #       result["sources"] == []
```

### 5.2 K1 tests (NEW — `_kg_local_worker` FTS fallback)

#### Unit test K1-1: markdown non-empty, zero `/article/{hash}` matches → FTS fallback fires

```python
# tests/unit/test_kg_local_worker_fts_fallback.py (new)
async def test_kg_local_worker_falls_back_to_fts_when_no_citations_in_markdown(monkeypatch, ...):
    # Given: synthesize_response mocked to return markdown WITHOUT /article/{hash} refs
    #        search_index.fts_query mocked to return 3 rows
    # When: _kg_local_worker(jid, query) runs
    # Then: job_store.get_job(jid)["status"] == "done"
    #       job_store.get_job(jid)["result"] has 3 entries
    #       each entry has keys {hash, title, snippet, lang, source}
    #       fts_query was called once with query=<query>, lang=None, limit=10
```

#### Unit test K1-2: markdown empty (C1 raised) → existing path unchanged, no FTS fallback

```python
async def test_kg_local_worker_no_fts_fallback_when_outer_except_caught(monkeypatch, ...):
    # Given: synthesize_response mocked to raise asyncio.TimeoutError
    #        search_index.fts_query mock spy (assert NOT called)
    # When: _kg_local_worker runs
    # Then: job_store.get_job(jid)["result"] == []
    #       fts_query NOT called (outer except sets results=[] before K1 conditional reached)
```

#### Unit test K1-3: markdown has `/article/{hash}` → existing path unchanged (KG-quality results)

```python
async def test_kg_local_worker_no_fts_fallback_when_kg_results_present(monkeypatch, ...):
    # Given: synthesize_response mocked to return markdown WITH "[/article/abcdef0123.html]"
    #        get_article_by_hash mocked to return a valid record
    #        search_index.fts_query mock spy (assert NOT called)
    # When: _kg_local_worker runs
    # Then: results == [{hash: "abcdef0123", ...}]
    #       fts_query NOT called (results non-empty → K1 conditional skipped)
```

#### Integration test K1-4: POST /api/search/kg adversarial query → 200 + non-empty results

```python
# tests/integration/test_search_kg_fts_fallback.py (new)
def test_search_kg_returns_200_with_fts_fallback_when_llm_omits_citations(monkeypatch, client, fixture_db_with_articles_fts):
    # Given: kg_synthesize.synthesize_response monkeypatched to return markdown w/o /article/
    #        articles_fts table has rows matching "claude"
    # When: POST /api/search/kg {"query": "claude"} → poll GET /api/search/kg/{jid} until done
    # Then: poll_response.status_code == 200
    #       poll_response.json()["results"] is a non-empty list
    #       each row has {hash, title, snippet, lang, source}
    #       (F1 sanitizer + ?-suffix regression intact — covered by existing tests)
```

### 5.3 Browser UAT (post-deploy, REVISED)

- **Synthesize tab UAT (G-remove validation):**
  - Navigate to Aliyun KB UI; submit "What is LightRAG?" via long-form mode
  - Verify answer body renders (5K+ chars expected based on AR Gate 4 probe)
  - Verify images render (or "no images returned" gracefully)
  - Verify source-chip ribbon either populated (if LLM emits citations) or empty (acceptable degradation)
- **KG search tab UAT (K1 validation — NEW):**
  - Navigate to KG search tab; query "claude" (or whatever yielded the original empty screenshot)
  - Verify article list renders (KG-ranked rows OR FTS fallback rows — both acceptable)
  - Network tab: `POST /api/search/kg` → 200 + `job_id`; `GET /api/search/kg/{jid}` polls → 200 + `{results: [...]}` non-empty
  - Backend logs (Databricks `make logs` / Aliyun `journalctl`): look for `kg_local_worker_start` then either `kg_local_worker_done n_results=N>0` (KG path) OR `kg_local_worker_fts_fallback` then `kg_local_worker_done n_results=N>0` (K1 path)
- Capture screenshots to `.scratch/arx-3-uat-grem-k1-<ts>.png` (synthesize + KG search) and cite in EVIDENCE.md

### 5.4 Regression checklist (existing tests)

- All `tests/integration/test_synthesize_router*.py` — should still pass; only the `confidence` field semantics shifted, not endpoint contract
- All `tests/unit/test_synthesize*.py` — review for any test that asserts `confidence='no_results'` when markdown is non-empty; those need updating to reflect new gate semantics
- All `tests/integration/test_search_router*.py` (and any `test_search_kg_*.py`) — F1 sanitizer + ?-suffix regression tests must stay green; K1 only adds a new tail branch in `_kg_local_worker` — pre-existing call paths are unchanged

---

## 6. Side-bug fold-in decision: `/api/search/kg` Pydantic mode-arg silently ignored

**Verdict (UNCHANGED): PARK as separate quick `.planning/quick/260526-kgs-mode-arg/`.**

Rationale:

- G+K1 diff is intentionally surgical (~13 LoC + 7 tests). Folding in the `mode` arg fix expands scope and breaks atomic-commit hygiene.
- The `mode` arg fix is independent surface (request validation, not worker logic); no shared test fixtures.
- Suggest filename: `.planning/quick/260526-kgs-mode-arg/` (separate quick task, ~1 line + 1 test, can ship same day after arx-3 closes).

---

## 7. Out-of-scope confirmations (REVISED)

Per user directive:

- **ARAG dead-code question** (`lib/research/*` + `kb/api_routers/research.py` + `tests/integration/test_research_router.py`): OUT OF arx-3 SCOPE. Belongs to repo-cleanup phase. Not touching ARAG files this turn.
- **K2 (worker chunk-metadata rewrite, ~50-80 LoC):** v1.1 phase. **Q1 (§ 1.7 above) confirms feasibility — `full_doc_id` field is present in 1967/1967 chunks, format `wechat_<10char_hash>(_images)?`.**
- **`kb/export_knowledge_base.py:558` `[:12]` outlier:** deferred to follow-up quick.

---

## 8. RECOMMENDATION (REVISED)

**Recommend: G-remove + K1 atomic (single commit, single deploy, single Gate 4 verify).**

Rationale (evidence-driven):

1. **G-remove is strictly dominant on `/api/synthesize`.** AR Gate 4 probe confirms `kg_synthesize.synthesize_response` returns 5K+ chars of real markdown with 3 image refs — the answer is being computed correctly today; the `confidence='no_results'` gate is what hides it. G-remove exposes that working markdown.
2. **K1 closes the original screenshot symptom (`/api/search/kg` empty).** The same cross-provider citation regression that motivates G-remove also breaks `_kg_local_worker`'s hash-grep architecture — when the LLM emits non-empty markdown but zero `/article/` refs, the worker silently returns empty results. K1's FTS fallback provides graceful degradation for the original user-reported empty-tab symptom.
3. **Both fixes are compositional, not entangled.** G-remove and K1 patch separate files (`kb/services/synthesize.py` and `kb/api_routers/search.py`), separate functions (`synthesize_for_job` vs `_kg_local_worker`), separate test files. Atomic shipment is purely a deployment-cadence convenience — neither fix depends on the other.
4. **Wrapper features + invariants verified preserved** (G-remove § 3 + § 4; K1 § 3.5 + § 4.5).
5. **Q1 verdict ✅** — K2 unblocked for v1.1 (§ 1.7).
6. **Ship cost is 1.5-2 hours total** (~13 LoC + 7 tests + commit + deploy + UAT covering both tabs).
7. Tradeoff (FTS fallback returns BM25-trigram results vs KG-semantic ranking when fallback fires) is an **acceptable degradation** vs the current empty UI. The user gets non-empty results in every case; UX-quality refinement is K2's v1.1 job.

---

## 9. Halt — awaiting Phase 2 PLAN gate (REVISED)

If user replies **`go plan G+K1`** → proceed to Phase 2 TDD PLAN.md (G-remove + K1 atomic scope; ~13 LoC + 7 tests + browser UAT covering both tabs).

If user replies **`halt revise: <X>`** → revise this DECISION.md per redirected feedback X.

**No code changes this turn. No commits. No deploys.**
