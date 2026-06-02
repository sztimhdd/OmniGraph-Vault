---
phase: llm-wiki-integration
plan: 02
type: execute
wave: 1
depends_on: ["llm-wiki-01"]
files_modified:
  - scripts/wiki_rank_entities.py
  - scripts/wiki_generate_pages.py
  - kb/wiki/entities/openclaw.md           # overwrites W0 placeholder with real content
  - kb/wiki/entities/*.md                   # 19 new entity pages (final filenames decided at runtime)
  - kb/wiki/index.md
  - kb/wiki/log.md
  - tests/unit/test_wiki_centrality.py     # fills W0 stub
  - tests/unit/test_wiki_citations.py      # fills W0 stub
  - tests/integration/test_wiki_generate.py # fills W0 stub
  - .planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md  # ranking output (artifact)
  - .planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md  # cost gate evidence
autonomous: false   # checkpoint:decision for entity selection + cost approval gate
requirements:
  - WIKI-RANK         # Rank top 50 entities by LightRAG centrality
  - WIKI-SELECT       # User picks 20 from top 50
  - WIKI-CONTENT      # Generate 20 wiki pages with multi-hop LightRAG context + citations
  - WIKI-COST-GATE    # User approves Vertex embedding cost estimate before generation
  - WIKI-CITATION     # Every claim cites ^[article:<hash>]
must_haves:
  truths:
    - "Top 50 entities ranked by LightRAG centrality (degree + relationship count) and presented to user"
    - "User selects exactly 20 entities (or fewer with explicit acknowledgement)"
    - "Cost estimate written and user-approved before any LLM/embedding spend"
    - "20 wiki pages generated, each with multi-hop LightRAG context, frontmatter, and ^[article:<hash>] citations on every claim"
    - "kb/wiki/index.md and log.md updated to reflect new pages"
  artifacts:
    - path: "scripts/wiki_rank_entities.py"
      provides: "CLI that reads vdb_entities.json + vdb_relationships.json, computes centrality, prints top N"
    - path: "scripts/wiki_generate_pages.py"
      provides: "CLI that takes a list of entity slugs, runs LightRAG aquery + LLM synthesis, writes wiki pages atomically"
    - path: ".planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md"
      provides: "Top 50 ranking output + user's 20 selections (audit trail)"
    - path: ".planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md"
      provides: "Cost estimate + user approval signature before generation"
    - path: "kb/wiki/entities/<slug>.md"
      provides: "20 wiki entity pages with frontmatter + citations"
      contains: "^[article:"
  key_links:
    - from: "scripts/wiki_rank_entities.py"
      to: "~/.hermes/omonigraph-vault/lightrag_storage/vdb_entities.json"
      via: "JSON read for centrality calculation"
      pattern: "vdb_entities|vdb_relationships"
    - from: "scripts/wiki_generate_pages.py"
      to: "lib.lightrag_embedding | lib.llm_client"
      via: "import for aquery(mode='hybrid') + LLM synthesis"
      pattern: "from lib"
    - from: "kb/wiki/entities/*.md"
      to: "articles.content_hash"
      via: "^[article:<hash>] citations resolve to real article hashes"
      pattern: "\\^\\[article:[a-f0-9]{10}\\]"
---

<objective>
Generate 20 high-quality entity wiki pages in `kb/wiki/entities/` from the live LightRAG knowledge graph. Process: rank top 50 entities by centrality → user selects 20 → cost-approval gate → generate pages with full multi-hop graph context and `^[article:<hash>]` citations.

Purpose: This produces the wiki's initial content. W2/W3/W4 all depend on real wiki pages existing.
Output: ~20 markdown files in `kb/wiki/entities/`, two helper CLI scripts, ranking + cost audit trails.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md
@.planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md
@.planning/phases/llm-wiki-integration/llm-wiki-01-SUMMARY.md
@kb/wiki/SCHEMA.md
@./CLAUDE.md
</context>

<interfaces>
<!-- Existing LightRAG + lib/ APIs that this plan consumes -->

From `lib/lightrag_embedding.py` and `lib/llm_client.py`:

```python
# Get a LightRAG instance configured for current environment
from lib.lightrag_embedding import get_rag  # async; returns LightRAG instance
# Multi-hop hybrid query (existing API)
result = await rag.aquery(question, param=QueryParam(mode="hybrid"))
```

From `config.py`:

```python
RAG_WORKING_DIR  # absolute path to lightrag_storage/ — contains vdb_entities.json + vdb_relationships.json
BASE_DIR          # absolute path to ~/.hermes/omonigraph-vault/ (or .dev-runtime/)
```

LightRAG storage JSON files (read directly per RESEARCH.md "Don't Hand-Roll" — centrality is O(N) read):

```
{RAG_WORKING_DIR}/vdb_entities.json        # list of {entity_name, entity_type, content, source_id, ...}
{RAG_WORKING_DIR}/vdb_relationships.json   # list of {src_entity, tgt_entity, keywords, description, source_id, ...}
```

Existing citation regex (per RESEARCH.md "Don't Hand-Roll"):

```python
# kb/services/synthesize.py — _resolve_sources_from_markdown uses this regex
r'\/article\/([a-f0-9]{10})'
```

For wiki content we use the inline footnote form `^[article:<10hex>]` and resolve at consumer side.
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: scripts/wiki_rank_entities.py — centrality ranking CLI + unit tests</name>
  <files>scripts/wiki_rank_entities.py, tests/unit/test_wiki_centrality.py</files>
  <read_first>
    - config.py (BASE_DIR, RAG_WORKING_DIR resolution)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md ("LightRAG centrality / multi-hop query" — degree+relation count from JSON files)
    - lib/lightrag_embedding.py (sample import patterns)
    - tests/unit/test_wiki_centrality.py (W0 stub — replace skip with real test)
  </read_first>
  <action>
    Build a small CLI script that ranks entities by combined centrality and writes a markdown ranking artifact for user review.

    **`scripts/wiki_rank_entities.py`** — interface:
    ```
    python scripts/wiki_rank_entities.py --top 50 --output .planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md
    ```

    Implementation:
    1. Resolve `RAG_WORKING_DIR` from `config.py` (honors `OMNIGRAPH_BASE_DIR`).
    2. Read `vdb_entities.json` and `vdb_relationships.json` as plain JSON (no LightRAG runtime needed).
    3. For each entity, compute `centrality_score = degree + relation_count` where:
       - `degree` = number of relationships where this entity is `src_entity` or `tgt_entity`
       - `relation_count` = number of unique target entities (de-duplicated)
       (formula derives from CONTEXT.md "Wave 1 entity ranking algorithm" — exact formula left to executor; document this choice in the script docstring AND in the SUMMARY)
    4. Sort entities by `centrality_score` desc, take top N (default 50).
    5. Write a markdown file with columns: rank, entity_name, entity_type, score, degree, relation_count, source_article_count (count of unique `source_id` where entity appears in vdb_entities + vdb_relationships).
    6. Print same content to stdout for visibility.

    Use only stdlib + already-installed packages — no new dependencies.

    Provide an `--working-dir <path>` flag overriding `RAG_WORKING_DIR` (lets the unit test point at fixture data).

    **`tests/unit/test_wiki_centrality.py`** — replace W0 skip stub. Test cases:
    - `test_centrality_ranking`: build a tmp dir with synthetic `vdb_entities.json` (3 entities) and `vdb_relationships.json` (e.g. A↔B, B↔C, B↔A duplicate so dedup matters); invoke the CLI's `rank_entities()` function via Python import; assert that B ranks #1 (highest centrality with 2 unique neighbors), and the ranking output matches expected order (A, C tied at degree 1).
    - Use `tmp_path` fixture; do not require real LightRAG data.
    - Independent verification per CLAUDE.md feedback: hand-compute expected scores in test, do not import the same constant from production module.

    Make sure to expose `rank_entities(working_dir: Path, top_n: int) -> list[dict]` as an importable function so tests can call it without subprocess.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_wiki_centrality.py::test_centrality_ranking -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f scripts/wiki_rank_entities.py` exits 0
    - `python scripts/wiki_rank_entities.py --help` exits 0 (argparse usage)
    - `pytest tests/unit/test_wiki_centrality.py::test_centrality_ranking` exits 0
    - Test does NOT mirror impl formula — assertions hand-compute expected ranks (per CLAUDE.md feedback `feedback_test_mirrors_impl.md`)
    - `grep -q 'rank_entities' scripts/wiki_rank_entities.py` exits 0 (importable function exposed)
  </acceptance_criteria>
  <done>Ranking CLI works on real prod data path AND on tmp fixture; unit test passes; centrality formula documented in script docstring.</done>
</task>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 2: User entity selection + cost-estimate approval (manual checkpoint)</name>
  <decision>Which 20 entities to generate wiki pages for, AND approval of cost estimate</decision>
  <context>
    Per CONTEXT.md Wave 1 Step 2 + Step 3 + Decision 1, this is the only manual gate in the plan.

    Per RESEARCH.md "OmniGraph-specific pitfall: LightRAG embedding quota / cost", we MUST estimate cost BEFORE running generation across 20 entities. A multi-hop hybrid query against a graph with thousands of entities can spend non-trivial Vertex AI embedding budget.

    Pre-checkpoint actions Claude completes:

    1. Run `python scripts/wiki_rank_entities.py --top 50 --output .planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md` — present the table.
    2. Compute cost estimate:
       - `est_embedding_calls = 20 entities × ~5 multi-hop calls/entity = ~100 calls`
       - Cite Vertex AI pricing from `docs/VERTEX_AI_MIGRATION_SPEC.md` if present
       - Add LLM synthesis cost: `20 entities × 1 long-form synth × est_tokens`
       - Total estimated cost in USD or RMB
    3. Write estimate to `.planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md` with breakdown table.
    4. Present to user inline.
  </context>
  <options>
    <option id="select-20">
      <name>Approve 20 entities + cost estimate; proceed to Task 3</name>
      <pros>Standard path; produces 20 high-centrality wiki pages</pros>
      <cons>Spends estimated budget</cons>
    </option>
    <option id="select-fewer">
      <name>User selects fewer than 20 (e.g., top 5 for cost-conscious smoke test)</name>
      <pros>Lower cost; faster iteration; defer remainder to a follow-up plan</pros>
      <cons>Wave 1 deliverable target was "20"; produces a partial wave that should be flagged in SUMMARY</cons>
    </option>
    <option id="abort">
      <name>Abort generation; revisit cost / scope; do not run W1 yet</name>
      <pros>No spend; opportunity to revise approach</pros>
      <cons>Blocks W2/W3/W4 (all depend on real wiki content)</cons>
    </option>
  </options>
  <resume-signal>
    User responds with one of:
    - "approved: <comma-separated-list-of-20-entity-slugs>" → write to RANKING.md "User Selections" section, mark COST-ESTIMATE.md as `approved: yes`, proceed to Task 3
    - "approved (N): <list of N slugs>" → same but with smaller N
    - "abort" → mark COST-ESTIMATE.md as `approved: no`, halt plan, return CHECKPOINT REACHED
  </resume-signal>
</task>

<task type="auto">
  <name>Task 3: scripts/wiki_generate_pages.py — multi-hop synthesis + atomic write + integration test</name>
  <files>scripts/wiki_generate_pages.py, kb/wiki/entities/openclaw.md, kb/wiki/entities/*.md, kb/wiki/index.md, kb/wiki/log.md, tests/unit/test_wiki_citations.py, tests/integration/test_wiki_generate.py</files>
  <read_first>
    - .planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md (just-written; user's selected 20 entity slugs)
    - .planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md (verify `approved: yes`)
    - kb/wiki/SCHEMA.md (frontmatter + citation contract)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Examples 1 + 5 — wiki page format and atomic write helper)
    - lib/lightrag_embedding.py (get_rag)
    - lib/llm_client.py (LLM completion API)
    - kb/wiki/entities/openclaw.md (W0 placeholder — this task overwrites with real content)
  </read_first>
  <action>
    Build the generation CLI, run it for the 20 selected entities, write pages, update index/log, and add citation coverage tests.

    **`scripts/wiki_generate_pages.py`** — interface:
    ```
    python scripts/wiki_generate_pages.py \
      --entities openclaw,hermes-agent,lightrag,...   # comma-sep slugs from Task 2
      --out-dir kb/wiki/entities \
      [--dry-run]
    ```

    Implementation:
    1. Verify `.planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md` has `approved: yes` in frontmatter; abort if missing/no.
    2. For each entity slug:
       a. Resolve canonical entity name from `vdb_entities.json` (slug → entity_name).
       b. Get LightRAG instance: `rag = await get_rag()` (do NOT pass `flush=True` — we are reading not writing).
       c. Issue multi-hop hybrid query: `await rag.aquery(f"Provide a comprehensive synthesis of {entity_name}: definition, architecture, history, related entities, and notable use cases.", param=QueryParam(mode="hybrid"))`. Per CONTEXT.md Step 3 — NO token truncation; trust LLM context window.
       d. Collect every `source_id` (article hash) referenced by entities/relationships involved in the answer. These become the `sources:` frontmatter list.
       e. Build the wiki page using a prompt template adapted from `kb/wiki/entities/openclaw.md` style (per CONTEXT.md). Prompt the LLM to:
          - Output strict markdown with the frontmatter block at the top
          - Include `^[article:<hash>]` citations on every claim (refuse to emit uncited claims)
          - Use `[[entity-slug]]` cross-references when mentioning other entities present in the graph
          - Append a `## Cross-references` section listing related `[[entity-slug]]` links
       f. Validate output:
          - Frontmatter has all 5 required fields (title/created/last_updated/sources/confidence_level)
          - At least one `^[article:[a-f0-9]{10}]` match in body
          - All citations resolve to actual article hashes from `articles.content_hash` (query SQLite)
          - If validation fails, regenerate up to 2 retries; if still failing, log error + skip entity (do not write a broken page)
       g. Write atomically using the `os.rename` pattern from RESEARCH.md Example 5.
       h. Append entry to `kb/wiki/log.md`: `<ISO date> — generated entities/<slug>.md (sources: N articles, confidence: <level>)`.
    3. After all entities processed: rebuild `kb/wiki/index.md` by listing every `entities/*.md` (read frontmatter `title` and link to the file). Group by subdir.
    4. Print summary: written / skipped / errors.

    Use `asyncio.run` to drive the async LightRAG calls. Single-process; no concurrency yet (W1 is one-shot, not a hot loop).

    **`tests/unit/test_wiki_citations.py`** — replace W0 skip stub:
    - `test_all_pages_cited`: walk `kb/wiki/entities/`, for each `.md`, parse frontmatter (use `python-frontmatter` per RESEARCH.md "Don't Hand-Roll"; if not installed, add to requirements.txt and pin a version), extract body, assert at least one `^[article:[a-f0-9]{10}]` match in body, AND assert every match's hash appears in the frontmatter `sources:` list (no orphan citations). Use `kb/wiki/entities/openclaw.md` as the canonical sample. If 0 entity pages exist, skip the test with `pytest.skip` — don't fail.

    **`tests/integration/test_wiki_generate.py`** — replace W0 skip stub:
    - `test_one_entity_full`: integration test that does NOT call real LightRAG / LLM. Mock `rag.aquery` to return synthetic markdown with citations. Mock the LLM call to return a valid wiki page. Run the generation function for one entity, write to `tmp_path`, then run the same validation logic the real script uses. Assert: file exists, frontmatter parses, citations present.
    - Document at top: "This is an integration test of the orchestration; it mocks LLM/aquery to keep CI deterministic. End-to-end with real LightRAG is exercised by the actual script run on the user's machine."

    Add `python-frontmatter` to `requirements.txt` if not present.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_wiki_citations.py tests/integration/test_wiki_generate.py -v && venv/Scripts/python.exe -c "import glob; assert len(glob.glob('kb/wiki/entities/*.md')) >= 1"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f scripts/wiki_generate_pages.py` exits 0
    - `pytest tests/unit/test_wiki_citations.py::test_all_pages_cited` exits 0 with PASSED (not skipped, since pages now exist)
    - `pytest tests/integration/test_wiki_generate.py::test_one_entity_full` exits 0 with PASSED
    - Page count check (cross-platform; run in Git Bash OR via Python): `venv/Scripts/python.exe -c "import glob; print(len(glob.glob('kb/wiki/entities/*.md')))"` returns ≥ N where N = number user approved (typically 20; or smaller per "select-fewer" branch). NTH-2 fix: replace bash `ls ... | wc -l` with cross-platform Python one-liner.
    - `for f in kb/wiki/entities/*.md; do grep -qE '\^\[article:[a-f0-9]{10}\]' "$f" || echo "MISSING CITATION: $f"; done` outputs no MISSING lines (run in Git Bash)
    - `grep -q '## Cross-references' kb/wiki/entities/openclaw.md` exits 0 (cross-ref section present in the canonical sample)
    - `wc -l kb/wiki/index.md` shows the index has been refreshed (more entries than W0's 1-line) (run in Git Bash)
    - `tail -20 kb/wiki/log.md | grep -c 'generated entities/'` matches number of pages written (run in Git Bash)
  </acceptance_criteria>
  <done>20 (or user-approved N) wiki entity pages generated with valid frontmatter + citations; index.md refreshed; log.md entries appended; both test files now PASS (no skip).</done>
</task>

</tasks>

<verification>
Phase-level verification for W1:
- `venv/Scripts/python.exe -c "import glob; print(len(glob.glob('kb/wiki/entities/*.md')))"` ≥ user-approved count (typically 20)
- `pytest tests/unit/test_wiki_centrality.py tests/unit/test_wiki_citations.py tests/integration/test_wiki_generate.py -v` all PASS (no SKIPPED)
- All entity pages contain valid frontmatter (5 required fields) + at least one citation
- Cost-estimate approval document `.planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md` has `approved: yes`
- Ranking artifact `.planning/phases/llm-wiki-integration/llm-wiki-02-RANKING.md` exists with top 50 + user selections
</verification>

<success_criteria>

1. Top 50 entities ranked by centrality, audit trail in RANKING.md
2. User approved 20 (or smaller N) selection + cost estimate before any generation
3. 20 wiki pages with multi-hop graph context + citations live in kb/wiki/entities/
4. kb/wiki/index.md refreshed; kb/wiki/log.md appended with generation entries
5. tests/unit/test_wiki_centrality.py + test_wiki_citations.py + tests/integration/test_wiki_generate.py all PASS
6. No orphan citations (every `^[article:<hash>]` in body has hash in frontmatter `sources:`)
</success_criteria>

<output>
After completion, create `.planning/phases/llm-wiki-integration/llm-wiki-02-SUMMARY.md` capturing:
- Top 50 ranking + user's 20 selections (cite RANKING.md)
- Cost estimate vs actual spend (cite COST-ESTIMATE.md)
- List of 20 generated pages with title + source-count + confidence
- Centrality formula chosen + rationale (degree + unique-relation-count)
- Any pages that failed validation and were skipped + why
- Citation coverage stats: total citations / unique articles cited / orphan citations (should be 0)
- Note: NO Local UAT required this wave (no kb/ runtime code changed; W4 will run UAT)
</output>
</content>
