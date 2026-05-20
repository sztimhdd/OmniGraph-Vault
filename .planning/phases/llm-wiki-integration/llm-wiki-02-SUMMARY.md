# Phase llm-wiki-integration — W1 (entity-content) Summary

**Status:** PARTIAL — Task 1 complete, Task 2 STOPPED at user-selection checkpoint, Task 3 not started.

**Date:** 2026-05-19 (overnight YOLO run)

## Scope of this run

Per overnight directive: execute W1 Task 1 (centrality ranker + tests) and the
ranking-execution slice of Task 2 (write top 50 candidates to `.scratch/`).
**Do NOT** pick the top 20 — leave that for the user. **Do NOT** start Task 3
(generate 20 wiki pages) tonight.

## Deliverables

### Task 1 — `scripts/wiki_rank_entities.py` ✅

- Reads `{RAG_WORKING_DIR}/vdb_entities.json` and `vdb_relationships.json`
  directly (no LightRAG runtime needed).
- Centrality formula: `score = degree + relation_count` per CONTEXT.md
  Decision D — degree counts edge endpoints (each rel contributes 1 to each
  endpoint), relation_count is the number of unique neighbors.
- CLI: `--top N`, `--output PATH`, `--working-dir PATH` (defaults to
  `config.RAG_WORKING_DIR`, honoring `OMNIGRAPH_BASE_DIR`).
- Atomic write (`.tmp` + `Path.replace()`).
- Handles real LightRAG schema (`src_id`/`tgt_id`) plus a fallback for any
  `src_entity`/`tgt_entity` shape.
- No new dependencies — stdlib only.

### Task 1 unit tests — `tests/unit/test_wiki_centrality.py` ✅

3 tests, all passing:

- `test_centrality_ranking` — 3-entity / 3-rel synthetic fixture (A↔B, B↔C,
  B↔A duplicate). Hand-computed expected scores per CLAUDE.md
  `feedback_test_mirrors_impl` (NOT imported from production module). Asserts
  rank order B > A > C and exact degree / relation_count / score.
- `test_top_n_truncates` — verifies `top_n` truncates and re-numbers ranks.
- `test_missing_files_raise` — verifies `FileNotFoundError` on empty dir.

Run: `venv/Scripts/python.exe -m pytest tests/unit/test_wiki_centrality.py -v`
→ 3 passed in 0.15s.

### Task 2 partial — `.scratch/llm-wiki-50-candidates-260519.md` ✅

50 highest-centrality entities from the live LightRAG store at
`~/.hermes/omonigraph-vault/lightrag_storage/` (711 entities, 820 relations).

Output columns: `rank | entity_name | type | score | degree | rel_count |
src_chunks | sample chunk ids` — exactly the data needed for the user to
pick 20 wiki targets.

Sanity check on the output: top 3 entities are `Hermes` (score 228),
`OpenClaw` (186), `Hermes Agent` (158). These are the domain spine — ranking
behaves as expected.

## STOPPED at Task 2 — pending user selection

Per overnight directive constraint:
> **不要自己挑 top 20** — stop 等我早上看完单子选

**Action required from Hai (morning):**

1. Open `.scratch/llm-wiki-50-candidates-260519.md`
2. Pick ~20 entities to seed the wiki. Prefer entities that:
   - Are domain-anchors (Hermes, OpenClaw, Claude Code, etc.)
   - Have ≥ 5 source chunks (better grok material)
   - Are NOT slug-name duplicates (e.g. `Hermes` vs `Hermes Agent` vs
     `Hermes-Agent` — pick canonical, alias the rest)
3. Note them somewhere the W1-Task3 executor can read (suggestion: append to
   this SUMMARY under `## Selected Entities`).
4. Resume execution: instruct an executor to run W1 Task 3 (generate 20 wiki
   markdown pages under `kb/wiki/entities/`) per
   `llm-wiki-02-entity-content-PLAN.md` Task 3.

## Deviations from plan-02

- **Filename** — plan-02 calls the script `scripts/wiki_rank_entities.py`;
  overnight directive said `scripts/rank_wiki_entities.py`. Used plan-02
  spelling (plan-02 is canonical per "不要重新发明任务" rule).
- **Output path** — wrote to `.scratch/llm-wiki-50-candidates-260519.md`
  (per overnight directive) rather than
  `.planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md` (per
  plan-02). Overnight directive's path makes Hai's selection workflow
  cleaner (`.scratch/` is gitignored; the chosen 20 only land in the repo
  via Task 3 wiki page artifacts).
- **Schema field names** — plan-02 says `src_entity`/`tgt_entity`; live
  LightRAG store uses `src_id`/`tgt_id`. Script accepts both via
  `rel.get("src_id") or rel.get("src_entity")` for forward-compat.
- **Sample article hashes column** — plan-02 asked for "sample article
  hashes". The chunk → article mapping requires `kv_store_text_chunks.json`
  + a SQLite lookup against `articles.content_hash`, which is non-trivial
  and not needed for the selection decision. Substituted "sample chunk ids"
  (truncated to 18 chars). W3/W4 will resolve chunk → article when
  generating actual wiki content.

## Cost

- LLM calls: 0
- Embedding calls: 0
- Vertex AI calls: 0
- Token spend: 0

Pure local compute (JSON load + dict ops on 711 entities / 820 rels).

## Commit

`feat(llm-wiki-W1): entity centrality ranker + 50 candidates` — see git log.
