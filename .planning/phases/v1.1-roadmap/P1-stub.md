# P1 — K2 chunk-metadata citation injection

**Wave:** 1 (parallel with P5)
**LoC estimate:** 30–50
**Risk:** Low
**Mainstream alignment:** ⭐⭐⭐⭐⭐ (validated by [Tensorlake citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations) + [arxiv DRM paper](https://arxiv.org/html/2603.19251v1))
**Dependencies:** P6.0 (fixture green floor)
**Recommended GSD ceremony:** `/gsd:plan-phase`

## Goal

Replace the regex-grep `_resolve_sources_from_markdown` citation extraction (which parses LLM-generated Markdown output) with deterministic source extraction directly from LightRAG's chunk retrieval metadata. arx-3 Q1 verified `chunk.full_doc_id` is 100% present in retrieved chunks (1967/1967 sampled). Mapping `full_doc_id` → article hash → article URL gives provider-agnostic, compliance-independent citations. This is the **real fix** for arx-3 bug 2c — eliminates the LLM-compliance dependency that broke identically across DeepSeek + Vertex Gemini + Databricks Claude. Also resolves [RESEARCH.md §4](RESEARCH.md) "ghost references" anti-pattern.

## File-touch list (best guess; verified at /gsd:plan-phase time)

- `kb/services/synthesize.py` — replace regex extraction with metadata extraction; deterministic source-chip population
- `kb/api_routers/search.py` — `/api/search/kg` ensure metadata flows through to response (also where P7 Pydantic mode-arg lives — fold-or-park decision at end of Wave 1)
- `tests/unit/kb/test_synthesize.py` — pin observable output: same chunk metadata → same source chips, regardless of LLM output text
- `tests/unit/kb/test_search_kg.py` — same pinning, KG search path
- `tests/integration/kb/test_synthesize_e2e.py` — provider-agnostic test: run against DeepSeek + Vertex Gemini + Databricks Claude; all three produce identical source-chip set

## Success criteria

1. `/api/synthesize` long_form returns deterministic source chips populated from chunk metadata, not LLM regex matches
2. Provider-swap test: same query against DeepSeek / Vertex Gemini / Databricks Claude all return identical source-chip set (different prose body is fine)
3. arx-3 bug 2c reproducer: cases that previously hit `c1_timeout` due to LLM non-compliance now succeed with citations populated
4. Zero regression on 953 pytest baseline; new behavior-anchor tests added per CLAUDE.md `# Behavior-Anchor Harness` discipline (`kb/services/synthesize.py` qualifies if it has the silent-broad-except + cost-consequence pattern; verify at plan-phase time)
5. Local UAT per Principle #6: `local_serve.py` + browser session + 3 sample queries with screenshots in `P1-VERIFICATION.md`

## Mainstream alignment notes (cite RESEARCH.md)

- [Tensorlake](https://www.tensorlake.ai/blog/rag-citations): *"This approach adds minimal overhead to the chunk text while still letting the retriever and LLM map answers back to exact locations in the source."*
- [aarontay.substack ghost references](https://aarontay.substack.com/p/why-ghost-references-still-haunt): LLMs do not naturally cite chunks; deterministic injection is the validated 2026 approach.

## Deferred decisions (resolve at /gsd:plan-phase time)

- Whether to use LightRAG `QueryParam(only_context=True)` to get raw chunk metadata in addition to the synthesized answer, or whether the existing return path already exposes `full_doc_id`. Read LightRAG source to confirm.
- P7 fold-or-park: if `kb/api_routers/search.py` is in the P1 atomic commit, fold the 1-line Pydantic mode-arg fix in. Otherwise park as `v1.1.x` quick.

---

**Execution detail TBD at `/gsd:plan-phase v1.1.P1` time.**
