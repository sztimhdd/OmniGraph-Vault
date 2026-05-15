---
phase: kb-v2.1-4-structured-synthesize
requirements: [REQ-2]
priority: P1
skills_required: [python-patterns, writing-tests]
wave: 3
depends_on: [kb-v2.1-1 KG mode hardening (KG mode safe enough to test against), 260515-xxx upstream-hotfix quick (synthesize.py drift closed)]
estimated_loc: 150-300
estimated_time: 1d
---

# Phase kb-v2.1-4 — Structured Synthesize Output

## Goal

Replace the v2.0 `_ENTITY_HINTS` heuristic + FTS source-inference workaround in
`kb/services/synthesize.py` with a proper structured output contract.
`kg_synthesize` happy path returns `{markdown, sources, entities, confidence,
fallback_used}` reliably; UI no longer needs heuristic backfill.

## Why

The 260515-xxx upstream-hotfix quick committed (correctly) a v2.0
minimum-viable workaround:

- `_ENTITY_HINTS` hardcoded list of 12 entity names
- FTS-based source backfill when KG markdown lacks `/article/{hash}` refs
- Substring matching for entity chips

This works but is:
- Hardcoded (won't surface entities outside the 12-name list)
- Heuristic (substring matching is brittle)
- Architecturally wrong place long-term — wrapper backfilling because C1 output
  is unreliable

This phase replaces the heuristic with structured resolution. Architecture
constraint: C1 contract (`kg_synthesize.synthesize_response()` signature) is
read-only — must NOT change. Resolution stays in `kb/services/synthesize.py`
wrapper, but uses real data sources instead of hardcoded hints.

## Source-of-truth options

Three architectural paths for sources/entities resolution:

| Option | Source | Pros | Cons |
|---|---|---|---|
| **A.** Parse LightRAG result metadata | LightRAG's internal `query_param.return_type` includes source doc IDs in some response modes | Direct — uses what KG actually retrieved | Requires understanding LightRAG internals; may need new parameter to surface |
| **B.** Query `extracted_entities` table for entities seen in KG result articles | DB query joining articles cited in markdown to their extracted_entities | Reuses existing kb-2 query patterns; no LightRAG internals needed | Two-pass: first find article hashes from markdown, then query entities |
| **C.** Hybrid — markdown-mention extraction + DB validation | Find `/article/{hash}` refs in markdown OR fall back to extract from sentences; validate against DB | Robust to LightRAG output variation | More LOC; entity match still imperfect |

**Recommendation: Option B** — fits existing kb-2 infrastructure
(`related_entities_for_article` query already does this kind of lookup). C1
contract remains read-only; KB wrapper does the structured resolution.

If executor finds Option A is feasible during research, switch with documented
rationale.

## Files affected

| File | Action |
|---|---|
| `kb/services/synthesize.py` | MAJOR REFACTOR — replace `_ENTITY_HINTS` + heuristic helpers with structured resolution; add `SynthesizeResult` schema |
| `kb/data/article_query.py` | EXTEND — add `entities_for_articles(hashes: list[str], limit: int)` query (mirrors kb-2 `related_entities_for_article` but for multi-hash batch) |
| `kb/api.py` | VERIFY — `/api/synthesize` job result shape matches new schema; no breaking change to client (qa.js) |
| `kb/static/qa.js` | VERIFY — already consumes `result.sources` + `result.entities` arrays; should be no-op if schema preserved |
| `tests/integration/kb/test_synthesize_structured.py` | NEW — covers KG success / no-sources / exception / timeout / fallback paths |
| `tests/unit/kb/test_synthesize_hotfix.py` (from 260515 quick) | UPDATE — drop tests for `_ENTITY_HINTS` (which is being removed); add tests for new `entities_for_articles` |

## Read first

1. `kb/services/synthesize.py` post-260515-quick state (with `_ENTITY_HINTS` heuristic)
2. `kb/data/article_query.py` — `related_entities_for_article()` pattern
3. `kg_synthesize.py` line ~105 — C1 contract (`synthesize_response(query_text, mode='hybrid')`)
4. `lib/lightrag_*.py` — LightRAG internals that may surface source doc IDs
5. `kb/api.py` — `/api/synthesize` route + job_store schema
6. `kb/static/qa.js` — consumer side; what fields it reads from result
7. `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md` § 3.1 (Q&A result component contract)

## Action

### Task 1 — Define `SynthesizeResult` schema

Invoke `Skill(skill="python-patterns", args="Define SynthesizeResult dataclass with frozen=True. Fields: markdown (str), sources (list[ArticleSource]), entities (list[EntityMention]), confidence (Literal['kg', 'fts5_fallback', 'kg_unavailable', 'no_results']), fallback_used (bool), error (Optional[str]). ArticleSource has hash + title + lang. EntityMention has name + frequency or article_count. Idiomatic Python — no breaking changes to existing job_store update contract.")`.

```python
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass(frozen=True)
class ArticleSource:
    hash: str
    title: str
    lang: Optional[str]  # 'zh-CN' / 'en' / 'unknown' / None

@dataclass(frozen=True)
class EntityMention:
    name: str
    article_count: int

ConfidenceLevel = Literal["kg", "fts5_fallback", "kg_unavailable", "no_results"]

@dataclass(frozen=True)
class SynthesizeResult:
    markdown: str
    sources: list[ArticleSource]
    entities: list[EntityMention]
    confidence: ConfidenceLevel
    fallback_used: bool
    error: Optional[str] = None
```

### Task 2 — Decide Option A vs B vs C; implement source resolution

Spawn investigation subagent OR research locally:

```bash
# Question: does LightRAG's aquery() expose source doc IDs alongside markdown?
grep -rE "source.*id|doc.*id|reference" lib/lightrag*.py
# look for return shape with ID list
```

If Option A feasible: implement `_extract_sources_from_lightrag(result_obj)` returning list of doc_ids.

If Option B (recommended): implement:

```python
def _resolve_sources_from_markdown(markdown: str) -> list[ArticleSource]:
    """Parse /article/{hash}.html refs from markdown and join to articles table for title+lang."""
    hashes = _extract_source_hashes(markdown)  # existing helper
    if not hashes:
        return []
    # JOIN against articles + rss_articles for title + lang
    return article_query.articles_by_hashes(hashes)  # NEW helper
```

### Task 3 — Implement entity resolution

Add to `kb/data/article_query.py`:

```python
def entities_for_articles(article_hashes: list[str], limit: int = 8) -> list[EntityMention]:
    """For a set of article hashes, return top-N entities mentioned across them.

    Joins extracted_entities table to articles_by_hashes. Returns entities
    sorted by article_count DESC (most-cross-referenced first), capped at limit.
    """
    if not article_hashes:
        return []
    placeholders = ",".join("?" for _ in article_hashes)
    sql = f"""
        SELECT e.entity_name, COUNT(DISTINCT e.article_id) AS article_count
        FROM extracted_entities e
        JOIN articles a ON a.id = e.article_id
        WHERE {_DATA07_KOL_FRAGMENT.replace('a.layer1_verdict', 'a.layer1_verdict')}
          AND a.url_hash IN ({placeholders})  -- (or whatever hash join pattern existing queries use)
        GROUP BY e.entity_name
        ORDER BY article_count DESC
        LIMIT ?
    """
    # ... DATA-07 filter applies as in other kb-3 queries
```

(Exact JOIN may differ — check existing `related_entities_for_article` for the
correct hash → article_id resolution pattern.)

### Task 4 — Refactor `kb_synthesize` happy path

```python
async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    # ... existing C1 call ...
    markdown = _read_synthesis_output()

    sources = _resolve_sources_from_markdown(markdown)
    entity_hashes = [s.hash for s in sources]
    entities = article_query.entities_for_articles(entity_hashes, limit=8) if entity_hashes else []

    job_store.update_job(
        job_id,
        status="done",
        result=SynthesizeResult(
            markdown=markdown,
            sources=sources,
            entities=entities,
            confidence="kg" if sources else "no_results",
            fallback_used=False,
        ).asdict(),  # or use dataclasses.asdict
        ...
    )
```

### Task 5 — Remove `_ENTITY_HINTS` + heuristic helpers

After structured resolution lands:

```python
# DELETE from kb/services/synthesize.py:
# - _ENTITY_HINTS tuple
# - _fallback_search_terms function
# - _source_hashes_from_fts function
# - _entity_candidates function
# - _dedupe function (if not used elsewhere; grep first)
```

Update FTS5 fallback path to use simpler query (just the question itself, not the broad-term iteration the 260515 hotfix added).

### Task 6 — Tests

Invoke `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + real FastAPI TestClient + MOCKED kg_synthesize.synthesize_response (because real LightRAG is slow + non-deterministic). Test: KG success with markdown containing 3 /article/{hash}.html refs → SynthesizeResult.sources has 3 entries with title+lang. Test: KG success with markdown lacking refs → sources=[], confidence='no_results'. Test: KG exception → fts5_fallback path. Test: KG timeout → fts5_fallback path. Test: FTS5 fallback returns valid SynthesizeResult shape. Cover edge cases: empty hashes list, non-existent hash, hash with NULL lang.")`.

`tests/integration/kb/test_synthesize_structured.py`:
- `test_kg_success_returns_structured_sources`
- `test_kg_success_no_sources_returns_no_results_confidence`
- `test_kg_exception_falls_back_to_fts5`
- `test_kg_timeout_falls_back_to_fts5`
- `test_fts5_fallback_response_shape`
- `test_entities_extracted_from_source_articles`
- `test_data07_filter_applies_to_synthesize_sources`

`tests/unit/kb/test_synthesize_hotfix.py` (UPDATE):
- DROP tests for `_ENTITY_HINTS`, `_fallback_search_terms`, `_entity_candidates`, `_dedupe` (they're being removed)
- ADD tests for `_resolve_sources_from_markdown` (pure function on markdown string)

### Task 7 — Local UAT (Rule 3 mandatory)

```bash
venv/Scripts/python.exe .scratch/local_serve.py &
sleep 2

# Q&A test — should return structured sources/entities
curl -X POST -H "content-type: application/json" \
  -d '{"question":"AI Agent 框架对比","lang":"zh"}' \
  http://127.0.0.1:8766/api/synthesize | python -m json.tool
# returns {job_id: ..., status: "running"}

JOB_ID=...
curl -sS http://127.0.0.1:8766/api/synthesize/$JOB_ID | python -m json.tool
# eventually returns: {status: "done", result: {markdown, sources: [...], entities: [...], confidence: "kg"}}

# Browser smoke
mcp__playwright__browser_navigate http://127.0.0.1:8766/ask/
# submit question, observe source chips + entity chips populated
mcp__playwright__browser_take_screenshot kb-v2.1-4-qa-structured.png
```

Capture screenshots in `.playwright-mcp/`.

## Acceptance criteria

- [ ] `_ENTITY_HINTS` tuple REMOVED from `kb/services/synthesize.py`
- [ ] `_fallback_search_terms`, `_source_hashes_from_fts`, `_entity_candidates` REMOVED
- [ ] `SynthesizeResult` dataclass exists with all 6 fields
- [ ] `entities_for_articles()` exists in `kb/data/article_query.py`
- [ ] `kb_synthesize` happy path uses structured resolution (no heuristic backfill on the KG path)
- [ ] FTS5 fallback path returns same `SynthesizeResult` shape
- [ ] Test file `tests/integration/kb/test_synthesize_structured.py` exists with ≥7 tests, all PASS
- [ ] Existing kb-3-09 fts5_fallback regression tests still PASS
- [ ] qa.js consumer side unchanged (no breaking API)
- [ ] Browser smoke: Q&A page returns visible source chips + entity chips for KG happy-path query
- [ ] DATA-07 filter applies to source resolution (DATA-07 articles only)
- [ ] No regression in full pytest

## Skill discipline

SUMMARY.md MUST contain:
- `Skill(skill="python-patterns"`
- `Skill(skill="writing-tests"`

## Anti-patterns

- ❌ DO NOT modify C1 contract (`kg_synthesize.synthesize_response()` signature)
- ❌ DO NOT keep `_ENTITY_HINTS` as a fallback "in case structured resolution fails" — kill the heuristic entirely
- ❌ DO NOT change `/api/synthesize` job_store schema in a way that breaks qa.js (sources + entities arrays of objects with at least `.hash`/`.title`/`.name` fields)
- ❌ DO NOT bypass DATA-07 — sources must filter through quality filter unless explicit override (preserve kb-3-02 behavior)
- ❌ DO NOT add new `_DATA07_*_FRAGMENT` SQL strings — reuse existing
- ❌ DO NOT use `git add -A`

## Return signal

```
## kb-v2.1-4 STRUCTURED SYNTHESIZE COMPLETE
- _ENTITY_HINTS + heuristic helpers REMOVED from synthesize.py
- SynthesizeResult dataclass shipped (6 fields)
- entities_for_articles() added to article_query.py
- kb_synthesize happy path uses structured resolution (Option <A/B/C>)
- /api/synthesize job result schema preserved (no qa.js breakage)
- Tests: <X>/<X> PASS (added <Y> regression tests; dropped <Z> _ENTITY_HINTS tests)
- Local UAT: KG happy-path returns structured chips (screenshot captured)
- Skill regex: python-patterns / writing-tests in SUMMARY
- No regression in full pytest
```
