# Phase llm-wiki-integration — Technical Research

**Date:** 2026-05-19
**Phase:** llm-wiki-integration
**Source:** Synthesized from 3-round research: Round 1 (Karpathy gist + nashsu/llm_wiki + context7 lightrag) · Round 2 (Mem0/Letta/Zep/LangMem comparison) · Round 3 (OmniGraph localization)
**Full research notes:** `.scratch/wiki-integration-research-260519.md`

---

## Executive Summary

Karpathy's LLM Wiki pattern (60+ implementations as of April 2026) is the proven and chosen approach. The wiki is NOT a RAG replacement — it is a persistent, evolving synthesis layer ON TOP of LightRAG's graph. Wiki = compiled view; Graph = source of truth. Industrial alternatives (Mem0, Letta, Zep) all end up doing this same layered approach in different forms.

**Key adoption signal:** Karpathy concept proven in production; OmniGraph is positioned for hybrid approach (wiki layer built on top of LightRAG, not replacing it).

---

## Standard Stack

The libraries and tools every task in this phase will use (no hand-rolled alternatives):

### Markdown + Frontmatter (wiki page format)
- **Pattern:** Plain markdown files with YAML frontmatter for metadata
- **Frontmatter fields (from nashsu/llm_wiki SCHEMA conventions):**
  - `title` — page display name
  - `created` — ISO date
  - `last_updated` — ISO date
  - `sources` — list of `article:<hash>` references
  - `confidence_level` — `high` / `medium` / `low`
- **Why standard:** human-readable, git-versionable, no parser dependency, works with any markdown viewer
- **Use:** `python-frontmatter` library if Python parsing needed (DO NOT hand-roll YAML parser)

### LightRAG (existing — entity/relationship extraction + graph query)
- **API surface:** `aquery(question, mode="hybrid")` for multi-hop retrieval; `vdb_entities.json` + `vdb_relationships.json` on disk for centrality scoring
- **What's available:** entity extraction (`entity_name`, `entity_type`, `entity_description`, `source_id`), relationship extraction (`src_entity`, `tgt_entity`, `keywords`, `description`), custom KG insert API
- **What's MISSING:** native markdown synthesis, canonical entity deduplication at export, cross-reference indexing — these are app-layer concerns
- **Use:** existing wrappers in `lib/lightrag_embedding.py`, `lib/llm_client.py`. DO NOT modify LightRAG itself

### Citations format: `^[article:<hash>]`
- **Pattern:** inline footnote-like markers tied to article content_hash (10-char hex from `articles.content_hash`)
- **Resolution:** wiki consumer (synthesize, KB UI later) resolves hashes to `/article/<hash>.html` URLs
- **Source:** Karpathy gist convention, also matches OmniGraph's existing kb/services/synthesize.py:_resolve_sources_from_markdown regex

### Hermes operator prompts (deployment channel for Hermes-side changes)
- **Pattern:** generate paste-ready prompt for user to forward to Hermes; never `ssh` from local Bash for mutations
- **Per CLAUDE.md Rule 5:** read-only diagnostic SSH ok; mutations via prompt
- **Wave 2 W2 will use this pattern for omnigraph_query SKILL.md update on Hermes**

### Existing KB infrastructure (don't recreate)
- **kb/services/search_index.py** — FTS5 trigram search; reference pattern for any future kb/services/wiki.py (deferred to P1)
- **kb/services/synthesize.py:_resolve_sources_from_markdown** — citation-resolution regex; W4 reuses
- **kb/api.py** — FastAPI app + route registration; W4 doesn't add new routes (just modifies synthesize logic)
- **batch_ingest_from_spider.py** — existing cron orchestrator; W3 adds end-of-cron hook

---

## Architecture Patterns

### Pattern: Wiki as compiled view, Graph as source of truth
- **Source layers:** raw articles (immutable in SQLite) → LightRAG graph (auto-extracted entities/relations) → wiki pages (LLM-synthesized markdown with citations)
- **Sync direction:** wiki is FED FROM graph; graph is never modified by wiki. Wiki contains nothing that isn't traceable back to graph + raw articles via `^[article:<hash>]` citations
- **Implication:** every task in this phase that writes to wiki must also write source citations; no claim without provenance

### Pattern: Three operations (Ingest / Query / Lint)
1. **Ingest** (W3): Read new sources → extract key facts → update 10–15 wiki pages atomically (per Karpathy)
2. **Query** (W2 + W4): Search wiki first → if miss, fall through to graph + synthesize. (Storage-back rejected per Decision 4)
3. **Lint** (folded into W3 + W4): Pre-application guard — contradictions, dangling links, stale claims, coverage gaps

### Pattern: Compounding artifact (vs stateless RAG)
| Aspect | Traditional RAG | LLM Wiki Pattern |
|--------|---|---|
| Retrieval model | Stateless (re-search every query) | Stateful (wiki caches synthesis) |
| Knowledge form | Facts in vector DB | Structured markdown pages + cross-refs |
| Maintenance | None (static index) | Continuous (LLM updates pages incrementally) |
| Token cost | Per-query embedding + LLM | Amortized across many queries |
| Multi-hop reasoning | Weak (limited context reuse) | Strong (wiki preserves intermediate reasoning) |

### Pattern: Pre-application lint guard (vs post-hoc detection)
- **Decided:** lint runs BEFORE applying suggestions (W3) and BEFORE injecting into prompt (W4 read-time)
- **Rationale:** active protection against bad updates beats retroactive detection of drift
- **Lint checks (W3):** contradiction (new claim vs existing), citation integrity (article hashes resolve), backlink validity (`[[entity]]` references exist), staleness (suggestion source newer than existing claims)
- **Lint checks (W4):** minimal — page exists, citations resolve, page not too stale

### Pattern: Hermes/repo separation
- **kb/wiki/** — source of truth, in repo, Claude Code edits here
- **~/wiki-omnigraph/** (Hermes side) — production read target; sync via git pull on Hermes (Hermes already runs `git pull` in cron) or symlink `~/wiki-omnigraph -> ~/OmniGraph-Vault/kb/wiki`
- **W0 task:** decide and document the sync mechanism; recommend symlink (zero ongoing cost)

---

## Don't Hand-Roll

These categories of solution have battle-tested standard approaches — DO NOT build custom alternatives:

### YAML frontmatter parsing
- **Use:** `python-frontmatter` (already common pattern, MIT license)
- **DON'T:** hand-roll YAML parser, regex-based field extraction, or use raw `yaml.safe_load` with manual delimiter handling
- **Why:** edge cases (multiline values, unicode, escaping) are non-trivial; library is small + battle-tested

### Markdown citation resolution
- **Use:** existing regex `\/article\/([a-f0-9]{10})` from `kb/services/synthesize.py:_resolve_sources_from_markdown`
- **DON'T:** re-implement citation parsing in W4
- **Why:** existing code already handles edge cases (escaped slashes, malformed hashes); reuse via import

### LightRAG centrality / multi-hop query
- **Use:** existing LightRAG `aquery(mode="hybrid")` for multi-hop; read `vdb_entities.json` + `vdb_relationships.json` JSON directly for centrality counts
- **DON'T:** invoke graph DB APIs directly (kuzu / lancedb) or write custom centrality algorithms beyond degree+relation count
- **Why:** LightRAG already handles vector + graph hybrid retrieval; centrality from JSON files is O(N) read

### Atomic file writes
- **Use:** existing OmniGraph pattern — write `.tmp` then `os.rename()` (e.g., `canonical_map.json` write pattern)
- **DON'T:** direct write to wiki page file (risk corrupted page on crash mid-write)
- **Why:** crash safety is non-trivial; existing pattern works

### Cron hook async execution
- **Use:** `asyncio.create_task()` + `asyncio.wait_for(timeout=...)` pattern from `batch_ingest_from_spider.py`'s existing layer2 queue
- **DON'T:** spawn subprocess, fork, or use threading for the wiki update hook
- **Why:** existing async ingest infra already handles task lifetime + timeout + cleanup

### Skill writing (W2 Hermes update)
- **Use:** existing `~/.hermes/skills/research/llm-wiki/SKILL.md` as template + `~/.hermes/skills/omnigraph_query/SKILL.md` as the file to modify
- **DON'T:** rewrite the skill from scratch or invent new metadata fields
- **Why:** skill convention is documented in CLAUDE.md "OpenClaw / Hermes Skill Writing Standards" section — follow it

---

## Common Pitfalls

LLM-maintained knowledge systems hit predictable failure modes. Verification steps in plans MUST check for these:

### Pitfall 1: Drift (wiki diverges from truth)
- **Symptom:** wiki summary contradicts raw source after new article ingest
- **Defense:** Lint contradiction check before apply (W3); periodic resync mode in W3 hook (compare wiki claims against article body samples)
- **Verification:** test scenario in W3 plan — ingest article that contradicts existing wiki page, verify lint blocks the conflicting suggestion

### Pitfall 2: Cross-reference rot (page A links to page B, B doesn't exist or doesn't link back)
- **Symptom:** `[[entity-x]]` references unresolved pages; one-way backlinks
- **Defense:** Symmetry lint — if A links to B, B must link to A (W3 lint check)
- **Verification:** test scenario — generate suggestion with new `[[entity-y]]` reference, verify lint either rejects (B doesn't exist) or auto-creates B-side link

### Pitfall 3: Orphan pages (unmaintained, unreachable)
- **Symptom:** wiki pages with last_updated date older than 6 months
- **Defense:** staleness check during W3 lint (skip injection in W4 if page too old); periodic backlink-count + access-frequency monitoring (deferred to v2)
- **Verification:** test scenario — set page last_updated to 1 year ago, verify W4 falls through to LightRAG-only

### Pitfall 4: Over-synthesis (LLM hallucinates connections beyond source evidence)
- **Symptom:** wiki page contains claims with no `^[article:<hash>]` citation
- **Defense:** strict citation requirement (every paragraph must cite); confidence scores in frontmatter; lint check rejects suggestions with uncited claims
- **Verification:** test scenario in W1 — generate page from 3-article source set, verify every claim has citation

### Pitfall 5: Degeneration loops (small LLM errors compound through update cycles)
- **Symptom:** wiki page quality degrades over multiple W3 update cycles
- **Defense:** git version control (every wiki write is tracked, rollback possible); lint blocks low-confidence suggestions
- **Verification:** rollback procedure documented in W0 README

### OmniGraph-specific pitfall: Image URLs and citations format
- **Status:** RESOLVED 2026-05-19 (commits 974f888 + 1683a58) — long-form synthesize now emits `/static/img/<hash>/<n>.jpg` + `/article/<hash>.html` correctly
- **Implication for W1/W4:** wiki page generation can rely on this; no need to post-process synthesize output for URL/citation rewrites
- **Verification:** W1 plan must run a sample synthesize against the test article and confirm output paths

### OmniGraph-specific pitfall: Parallel agent on kb/
- **Status:** kb-v2.2-7 bilingual SSG agent active; modifies `kb/services/search_index.py`, `kb/services/synthesize.py`, `databricks-deploy/*`
- **Implication:** W3 hook (modifies `batch_ingest_from_spider.py`) and W4 (modifies `kb/services/synthesize.py`) MAY collide
- **Defense:** W4 must `git pull` and re-read `kb/services/synthesize.py` immediately before editing; W4 plan tasks include explicit "read current state" step

### OmniGraph-specific pitfall: LightRAG embedding quota / cost
- **Status:** Vertex AI embedding GA on `global` endpoint; pool quota across projects
- **Implication for W1:** generating 20 wiki pages with multi-hop graph queries may consume embedding budget; W1 plan should batch + cache
- **Defense:** estimate cost in W1 plan task before generation; user budget approval gate

---

## Code Examples

### Example 1: Wiki page format (W0/W1 reference)

```markdown
---
title: OpenClaw
created: 2026-05-08
last_updated: 2026-05-19
sources:
  - article:a3f2c1d8e9
  - article:b2e1d9c8a7
  - article:c1d8e9b2a3
confidence_level: high
---

# OpenClaw

OpenClaw is a Tauri-based AI desktop assistant ^[article:a3f2c1d8e9] that ships
with a five-layer architecture ^[article:b2e1d9c8a7].

## Architecture

The five layers are: skill loader, gateway router, LLM dispatcher, ... ^[article:b2e1d9c8a7]

## Comparison: vs Hermes

OpenClaw and [[hermes-agent]] share the gateway/skill model but differ in ...
^[article:c1d8e9b2a3]

## Cross-references

- [[hermes-agent]]
- [[mcp-protocol]]
- [[agent-skills]]
```

### Example 2: Lint check (W3 reference — citation integrity)

```python
import re
from pathlib import Path

CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")

def lint_citations(wiki_page: Path, article_hashes: set[str]) -> list[str]:
    """Return list of unresolved citations; empty list = pass."""
    failures = []
    for match in CITATION_RE.finditer(wiki_page.read_text()):
        if match.group(1) not in article_hashes:
            failures.append(f"unresolved: {match.group(0)}")
    return failures
```

### Example 3: Wiki-first lookup in synthesize (W4 reference)

```python
# kb/services/synthesize.py — pseudocode for W4
async def synthesize(question: str, mode: str = "long_form"):
    entity = extract_main_entity(question)  # existing helper
    wiki_context = ""
    wiki_page = Path(f"kb/wiki/entities/{entity}.md")
    if wiki_page.exists() and not is_stale(wiki_page, max_days=180):
        if lint_citations(wiki_page, known_article_hashes()) == []:
            wiki_context = f"<wiki_context>\n{wiki_page.read_text()}\n</wiki_context>\n\n"

    prompt = wiki_context + standard_synthesize_prompt(question)
    return await rag.aquery(prompt, mode=mode)
```

### Example 4: Hermes skill diff (W2 reference — wiki-first lookup)

```diff
# ~/.hermes/skills/omnigraph_query/SKILL.md (Hermes side)

  ## Behavior

+ ### Wiki-first lookup (added 2026-05-19)
+ Before invoking `kg_synthesize.py`, check if a wiki page exists for the query entity:
+ ```bash
+ entity=$(echo "$query" | extract-entity)
+ wiki="$REPO/kb/wiki/entities/${entity}.md"
+ if [ -f "$wiki" ]; then
+   cat "$wiki"
+   echo "Need deeper detail? Reply 'go deeper'."
+   exit 0
+ fi
+ ```
+
  ### Fallback (existing)
  Run `python kg_synthesize.py "$query" hybrid` ...
```

### Example 5: Atomic wiki write (W3 reference)

```python
import os, tempfile
from pathlib import Path

def atomic_write_wiki_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    os.rename(tmp_path, path)  # atomic on POSIX + Windows
```

---

## Validation Architecture (for VALIDATION.md if Nyquist enabled)

If the Nyquist validation gate is enforced, every requirement in this phase needs at least one verification — typical mappings:

| Requirement Type | Verification Strategy |
|---|---|
| Wiki content present | grep + file existence test |
| Citation integrity | regex over wiki content + cross-check article DB |
| Hermes skill change applied | curl/SSH read of remote SKILL.md + diff against expected |
| Ingest hook fires | log line presence + suggestion file count |
| Lint blocks bad suggestion | unit test with crafted bad input |
| Synthesize injects wiki context | integration test inspecting prompt sent to LLM |
| End-to-end ingest cron | local UAT per CLAUDE.md Rule 6 |

---

## Source URLs (full list, condensed)

- Karpathy LLM Wiki Gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Medium explainer: https://medium.com/@urvvil08/andrej-karpathys-llm-wiki-create-your-own-knowledge-base-8779014accd5
- Reddit lessons: https://www.reddit.com/r/learnmachinelearning/comments/1shfkx5/
- Mem0 framework: https://mem0.ai/blog/state-of-ai-agent-memory-2026
- Letta framework: https://www.letta.com/blog/agent-memory
- Zep memory system: https://atlan.com/know/best-ai-agent-memory-frameworks-2026
- LightRAG context7 docs: /hkuds/lightrag (verified 2026-04 via context7 MCP)
- nashsu/llm_wiki: https://github.com/nashsu/llm_wiki

---

*Research complete. Ready for planning.*
