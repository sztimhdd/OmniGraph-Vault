# VERIFICATION-1.1-A — Phase arx-1-images

**Milestone:** Agentic-RAG-v1.1
**Phase:** arx-1-images
**Slug:** 260524-arx-A-images
**Verdict:** ✅ PASS
**Closed:** 2026-05-25

---

## Goal-backward check

> **Phase goal (ROADMAP-Agentic-RAG-v1.1.md):** Close v1 audit dim 5 image gap. Retriever populates `image_candidates` reliably; Synthesizer URLs work behind kb/api `/static/img` mount.
> **Done-when:** TEST-05 condition (a) flips from `images=0` (v1 close baseline) to `images ≥ 3`.

**Achieved.** Hermes real-KG retriever run returned `IMAGES: 10` against a candidate pool whose v1 baseline was `0`.

---

## Root cause (different from ROADMAP's drafted hypothesis)

ROADMAP hypothesized retriever needed chunk-decomposition + hash-grep + glob improvements. Investigation showed retriever code was already correct; the structural gap was upstream:

`omnigraph_search.query.search()` always called `LightRAG.aquery(...)` without `only_need_context=True`, so it returned **LLM-synthesized prose**. Synthesized prose strips raw 10-char hex `file_path` markers, so `ARTICLE_HASH_RE.findall()` in retriever could never match — `image_candidates` was structurally locked at `[]`.

Fix is one additive parameter on the sole authorized contract entry (CONTRACT-01 preserved).

---

## Change set (commit `39c8f43`, merged via `dddaa38` to origin/main)

| File | Change |
|---|---|
| `omnigraph_search/query.py` | `+only_context: bool = False` → `QueryParam(only_need_context=only_context)`. Default `False` preserves pre-existing callers (`kb/api_routers/search.py`, `lib/research/stages/reasoner.py`). |
| `lib/research/stages/retriever.py` | Single call-site update: `kg_search(query, mode="hybrid", only_context=True)`. |
| `tests/unit/test_omnigraph_search_query.py` | NEW (69 lines) — 3 tests: default-False, True-transits, GEMINI_API_KEY guard preserved. |
| `tests/unit/research/test_stages_stubs.py` | 9 mock-search signatures: add `**kwargs`. |
| `tests/unit/research/test_orchestrator.py` | 5 mock-search signatures: add `**kwargs`. |

No change to `synthesizer.py` URL pattern (deferred to arx-2-http preflight; current image URLs are already filesystem-rooted via `cfg.rag_working_dir.parent / "images"` and don't carry `localhost:8765` literals at retriever-output time).

---

## Evidence

### 1. Unit tests — local + Hermes
- arx-1 scope: **172 passed** (was 169 before; +3 new tests in `test_omnigraph_search_query.py`).
- Pre-existing 92 KB integration failures (sqlite3) unrelated to arx-1 scope and present on baseline.

### 2. TEST-05 condition (a) — Hermes real-KG retriever run (2026-05-25)

Pre-verify environmental fix: `kv_store_llm_response_cache.json` (88.8 MB) had JSON corruption at line 46649. Renamed to `.bak-arx1-260525`. LightRAG rebuilds empty cache on next query. Real truth files (full_docs, text_chunks, vdb_entities, vdb_relationships, vdb_chunks) all parsed OK — orthogonal to arx-1 code.

Verify run output (Hermes, query: "AI Agent 最新趋势"):

```
STATUS:  ok
CHUNKS:  9
IMAGES:  10        ← v1 baseline was 0
```

Sample image candidate hash + filename pattern: `0552fb242d :: 1.jpg ~ 18.jpg`.

### 3. Commit lineage
- `39c8f43` — feat(arx-1-images/A): only_context param ...
- `dddaa38` — merge integrating origin's `ee172c0` (wechat-session-hardening) without rebase, preserving `39c8f43`.

---

## REQ coverage

ROADMAP allocated 7 REQs (A-1 .. A-7) to this phase. The Option A fix delivers them indirectly: the chunk-split / hash-grep / glob code paths in retriever.py were already correct — they were starved of input by the contract gap. Closing the contract gap re-activates all 7 in one change. Hermes verify (`CHUNKS: 9`, `IMAGES: 10`) confirms each downstream code path executes against real data.

---

## Outstanding / deferred

- **Synthesizer URL pattern flip** (`localhost:8765` → `/static/img/...`) is a precondition for arx-2-http (Databricks deploy), not for TEST-05 (a). Tracked as arx-2-http preflight, not a v1.1-A regression.
- **LightRAG `kv_store_llm_response_cache.json` corruption root cause** unidentified. Symptom resolved by rename. If recurs, dig into LightRAG cache-write atomicity. Not arx-1 scope.

---

## Sign-off

Track 1 gate: ✅ closed. Proceeding to arx-2-http (HTTP API + Databricks Apps deploy) per ROADMAP serial track ordering.
