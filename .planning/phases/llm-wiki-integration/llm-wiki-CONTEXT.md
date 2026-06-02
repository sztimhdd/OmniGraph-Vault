# Phase llm-wiki-integration: LLM Wiki Integration — Context

**Gathered:** 2026-05-19
**Status:** Ready for planning
**Source:** Research-driven planning session (5 locked decisions confirmed via discussion 2026-05-19)

<domain>
## Phase Boundary

**In scope (this phase):**

- Karpathy LLM Wiki pattern integration: compounding markdown artifact maintained by LLM on top of LightRAG graph
- 5 waves: scaffold → entity selection + content → P0 Hermes skill → P2 ingest hook + lint → P3 synthesize injection
- Ship 20 high-centrality entity wiki pages live in `kb/wiki/`
- Hermes `omnigraph_query` skill checks wiki first, falls through to graph
- `batch_ingest_from_spider.py` end-of-cron generates wiki update suggestions, applies after lint passes
- `kb/services/synthesize.py` injects wiki context into LLM prompt before LightRAG query

**Out of scope (this phase, deferred):**

- P1 KB Web UI wiki-first rendering (entity.html / topic.html / index.html template work) — separate later phase
- P4 standalone lint script — folded into W3 (P2) and W4 (P3) as pre-application guard, not standalone
- Synthesize answer-cache-back loop (decided NO — low usage, complexity not worth it)
- Mem0/Letta/Zep alternative memory patterns (rejected — Karpathy markdown is the chosen pattern)
- Multi-language wiki content (only English first; bilingual deferred until kb-v2.2-7 SSG settles)

</domain>

<decisions>
## Implementation Decisions (5 LOCKED)

### Decision 1: Wiki pattern — Karpathy markdown (compounding artifact)

- LOCKED: pure Karpathy markdown pages with `^[article:id]` source citations
- Rejected alternatives: Mem0 (episodic memory, overkill), Letta (single-agent stateful memory, unsuitable for shared KB), Zep (temporal graph, post-processing delays + high baseline tokens)
- Rationale: OmniGraph KOL articles are read-heavy (~80% queries vs 20% updates), mostly immutable, and benefit from human-readable + git-versionable artifacts

### Decision 2: Wiki location — `kb/wiki/` (committed, version-controlled)

- LOCKED: `kb/wiki/` under the kb subsystem in OmniGraph-Vault repo
- Rationale: git version control, PR review workflow, public artifact, treats wiki as a kb sub-feature alongside templates/services
- Hermes side: `~/wiki-omnigraph/` continues to exist as the production-ingest write target; sync via git pull (Hermes is git tracked) or symlink. Decided to keep kb/wiki/ as the source of truth in repo
- Initial seed: port `~/wiki-omnigraph/SCHEMA.md`, `index.md`, `log.md`, `entities/openclaw.md` (5763 chars, 6-article synthesis) from Hermes into `kb/wiki/`

### Decision 3: Ingest hook strategy — auto-apply after lint passes

- LOCKED: `batch_ingest_from_spider.py` end-of-cron `_wiki_update_check()` generates suggestions, applies them automatically IF lint passes
- Lint runs BEFORE application as a pre-application guard (NOT after-the-fact detection)
- Lint failures: log structured warning, drop suggestion, do NOT block the cron run
- Rationale: manual review queue would never get reviewed; auto-apply with lint guard balances velocity and safety
- Async execution: hook runs as fire-and-forget after main ingest completes; never blocks ingest

### Decision 4: Synthesize storage — NO storage by default

- LOCKED: `kb/services/synthesize.py` reads wiki context for INJECTION, but does NOT write synthesized answers back to wiki
- Rejected: three-tier confidence-scored cache-back (high→auto-store, medium→suggest, low→discard) — too complex, low usage
- Rationale: storage path adds significant complexity (confidence scoring, deduplication, page-merge logic) for limited benefit at current usage scale
- Future option: revisit if wiki query volume grows to justify the complexity

### Decision 5: Lint integration — folded into W3/W4 (NOT standalone P4)

- LOCKED: lint runs as a pre-application guard inside the ingest hook (W3) and inside the synthesize injection (W4 read-time validation)
- W3 lint scope: contradiction detection (new suggestion vs existing wiki content), backlink validation (cross-references resolve), staleness check (page age vs source date), source-citation integrity (`^[article:id]` resolves)
- W4 lint scope: minimal read-time check (page exists, citations resolve) before injecting into LLM prompt
- Rationale: lint as ACTIVE protection (block bad updates) is more valuable than as RETROACTIVE detection (find drift after the fact); single-pass eliminates need for separate cron

### Implementation details (Claude's discretion)

- Wave 0 scaffold tooling can be Python script or shell — pick simpler
- Wave 1 entity ranking algorithm: LightRAG centrality score (degree + entity-relation count) — exact formula left to executor; document choice in W1 SUMMARY
- Wave 1 wiki page generation prompt: derive from `~/wiki-omnigraph/entities/openclaw.md` style, executor adapts as needed
- File-extension choice for wiki pages: `.md` (standard markdown)
- Whether to use front-matter on wiki pages (created/updated/sources/confidence): YES — follow nashsu/llm_wiki convention for lint and consumer access
- Wave 2 Hermes skill change: minimal LOC (~20), wiki-first lookup in `omnigraph_query` SKILL.md
- Wave 3 lint detector implementation: regex + simple syntax checks; LLM-based contradiction detection deferred to v2 if needed
- Wave 4 synthesize prompt template change: append wiki context BEFORE LightRAG-retrieved chunks, mark with `<wiki_context>` tag

</decisions>

<canonical_refs>

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Original design + research

- `.planning/wiki-integration-design.md` (commit 7eda4ff — NOT in current working tree, read via `git cat-file -p 7eda4ff:.planning/wiki-integration-design.md`) — original 202-line design doc; defines three integration angles (A reading layer / B query layer / C ingest layer) and P0–P4 LOC roadmap. Authoritative on architecture intent.
- `.scratch/wiki-integration-research-260519.md` — 280-line research summary; comparison vs Mem0/Letta/Zep, Karpathy pattern details, OmniGraph localization challenges, common failure modes (drift, contradictions, orphan pages, over-synthesis, degeneration loops). Authoritative on pattern choice rationale.

### Existing wiki seed (Hermes side, to be ported in W0)

- `~/wiki-omnigraph/SCHEMA.md` — Agent behavior rules, tag taxonomy
- `~/wiki-omnigraph/index.md` — content directory
- `~/wiki-omnigraph/log.md` — operation log
- `~/wiki-omnigraph/entities/openclaw.md` — first wiki page reference (5763 chars, 6-article synthesis with `^[article:id]` citations)
- `~/.hermes/skills/research/llm-wiki/SKILL.md` — full ingest/query/lint operation definitions for the existing Hermes-side llm-wiki skill (reference template for our omnigraph_query update in W2)

### Codebase integration points (read before modifying)

- `kb/api.py` — FastAPI app on port 8766; route registration site
- `kb/api_routers/` — existing router directory; W3/W4 may need wiki router (deferred to P1) but synthesize injection touches existing synthesize router
- `kb/services/synthesize.py` — long-form synthesis service; W4 modifies this for wiki context injection (pre-LLM-call)
- `kb/services/search_index.py` — FTS5 search service; reference pattern for new `kb/services/wiki.py` (deferred to P1)
- `batch_ingest_from_spider.py` — cron entry point; W3 adds end-of-cron hook
- `lib/lightrag_embedding.py`, `lib/llm_client.py` — LightRAG wrapper layer; W1 entity ranking calls LightRAG aquery to get centrality data

### Project root references

- `CLAUDE.md` — HIGHEST PRIORITY PRINCIPLES (think before coding, simplicity, surgical, goal-driven, no SSH outsourcing) + Rule 6 (KB Local Deploy + UAT mandatory before phase complete) + Rule 7 (behavior-anchor harness for hot orchestration code — applies to W3 ingest hook)
- `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3 — KB local UAT mandatory; phase MUST run `.scratch/local_serve.py` + browser UAT + cite evidence in VERIFICATION.md before complete

### Long-form bug context (resolved as of 2026-05-19)

- Image URL bug (localhost:8765 → /static/img/) — FIXED in commit 974f888
- Citation format bug ([Entity: X] → /article/{hash}.html) — FIXED in commit 1683a58
- Both bugs would have polluted wiki content quality if unfixed; W4 synthesize work assumes them fixed
- `.scratch/kb-long-form-bug-report-260519.md` — historical reference

</canonical_refs>

<specifics>
## Specific Ideas

### Wave 0 — `.wiki/` scaffold (kb/wiki/ at repo root under kb)

- Create directory structure: `kb/wiki/{SCHEMA.md, index.md, log.md, entities/, concepts/, comparisons/, queries/, _suggestions/}`
- Port content from Hermes `~/wiki-omnigraph/` (SCHEMA, index, log, entities/openclaw.md) — content can be retrieved via Hermes operator prompt or exported by user
- Add `kb/wiki/README.md` documenting the structure for human readers
- No code changes outside `kb/wiki/` in this wave

### Wave 1 — Entity selection + content generation

- Step 1: rank top 50 entities by LightRAG centrality (combine entity-degree from `vdb_entities.json` + relationship count)
- Step 2: present 50 to user, collect 20 selections (interactive — likely separate skill invocation or interactive script)
- Step 3: for each of 20 entities, retrieve COMPLETE LightRAG context (multi-hop graph query, all related text/entities, no token truncation)
- Step 4: generate wiki page using prompt template derived from openclaw.md style; ensure `^[article:id]` citations on every claim
- Step 5: write to `kb/wiki/entities/<entity>.md`
- Update `kb/wiki/index.md` and `kb/wiki/log.md` after each batch
- Token budget per page: trust LLM to self-filter signal from noise (no artificial truncation, but don't blow context window — use Vertex Gemini 2.5 Pro with large context if needed)

### Wave 2 — Hermes omnigraph_query skill update (P0, ~20 LOC)

- Modify `~/.hermes/skills/omnigraph_query/SKILL.md` — add wiki-first lookup logic
- Steps in skill: (1) extract entity from query, (2) check `kb/wiki/entities/<entity>.md`, (3) if exists return wiki content + suggest "deeper detail via graph?", (4) else fall through to existing LightRAG graph query
- Hermes operator prompt to apply (NOT user paste of SSH commands per CLAUDE.md Rule 5)
- Cross-reference: `~/.hermes/skills/research/llm-wiki/SKILL.md` already has wiki ingest/query/lint patterns — reuse where possible

### Wave 3 — Ingest hook + lint guard (P2 + P4 lint, ~150 LOC)

- Add `_wiki_update_check()` to `batch_ingest_from_spider.py` end-of-cron path (after `_drain_layer2_queue` completes)
- Logic: identify new entities/topics from this cron's ingested articles → query wiki for related pages → for each:
  - Existing page: generate update-suggestion markdown delta
  - No page but high-frequency entity: generate new-page suggestion
- Run lint guard on each suggestion BEFORE applying:
  - Contradiction check (new claim vs existing claims, conservative diff-based)
  - Citation integrity (`^[article:id]` references resolve to real article hashes)
  - Backlink validity (cross-references `[[other-entity]]` exist in wiki)
  - Source freshness (suggestion-source dated newer than existing claims)
- If all lint passes: apply suggestion (write to wiki page)
- If any lint fails: log structured warning to JSONL, drop suggestion, continue cron
- Async fire-and-forget: hook never blocks ingest exit; uses async tasks with timeout

### Wave 4 — Synthesize wiki context injection (P3, ~60 LOC)

- Modify `kb/services/synthesize.py` — before LightRAG `aquery()` call, look up wiki context
- Logic: extract main entity from question → check `kb/wiki/entities/<entity>.md` → if exists, prepend to LLM prompt as `<wiki_context>...</wiki_context>` block before LightRAG-retrieved chunks
- Read-time lint guard: validate page exists, citations resolve, page not stale (configurable max age)
- If lint fails: skip injection silently, fall through to standard LightRAG-only synthesize
- NO write-back: per Decision 4, do NOT cache synthesized answers back to wiki

</specifics>

<deferred>
## Deferred Ideas

### Deferred to a separate later phase (after this phase ships)

- **P1 KB Web UI wiki-first rendering** — entity.html / topic.html / index.html template changes (~217 LOC). Requires kb-v2.2-7 bilingual SSG to fully settle first. Will be its own phase after this phase verifies content quality and wiki-update flow stability.
- **Bilingual wiki content** — currently English-only; bilingual sync deferred until kb-v2.2-7 lands
- **`kb/services/wiki.py` + `kb/api_routers/wiki.py`** — REST API for wiki (~160 LOC). Part of P1 deferred bundle.
- **Wiki authentication** — KB Web UI auth question deferred (current KB is internal-only on Aliyun, no auth needed yet)

### Deferred indefinitely (low value at current scale)

- Synthesize answer cache-back (per Decision 4)
- LLM-based contradiction detection in lint (currently regex/diff-based — escalate only if v1 lint produces too many false-pass)
- Multi-version wiki page tracking (`supersedes` / `superseded_by` relationships from nashsu/llm_wiki — over-engineering for current scale)
- Wiki search backend (full-text search across wiki) — covered by KB FTS5 indirectly when P1 ships

### Wave count and structure

- 5 waves agreed (W0 scaffold / W1 content / W2 P0 skill / W3 P2 hook+lint / W4 P3 synthesize)
- 4-wave compression rejected (W0+W1 too big to gate independently)
- 3-wave aggressive rejected (mixes architectural layers)
- W2/W3/W4 can run in parallel after W1 completes (linear chain W0→W1, then fan-out)

</deferred>

---

*Phase: llm-wiki-integration*
*Context gathered: 2026-05-19 via research-driven session (Karpathy gist + nashsu/llm_wiki + context7 lightrag + Mem0/Letta/Zep comparison)*
