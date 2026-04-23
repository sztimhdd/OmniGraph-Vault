# Architecture Patterns: v2.0 Knowledge Infrastructure MVP

**Domain:** Local knowledge graph + agent skill system (rules-engine overlay)
**Researched:** 2026-04-23
**Confidence:** HIGH — derived entirely from actual source files; no external docs needed.

---

## Standard Architecture

### System Overview

v2.0 adds three new layers on top of the existing v1.1 pipeline. The existing code is largely
untouched; new components plug in at well-defined seams.

```
┌──────────────────────────────────────────────────────────────────────┐
│  HERMES / OPENCLAW AGENT                                             │
│  - SKILL.md Level-0 catalog → Level-1 dispatch                      │
│  - Matches trigger phrases to skill                                  │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  exec (shell)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SKILL LAYER  (skills/ at project root)          [v2.0 ADDS]        │
│                                                                      │
│  omnigraph_ingest/    omnigraph_query/    omnigraph_architect/ (NEW) │
│  ├── SKILL.md         ├── SKILL.md        ├── SKILL.md               │
│  └── scripts/         └── scripts/        └── scripts/              │
│      ingest.sh            query.sh            architect.sh (NEW)     │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  subprocess (activated venv python)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PYTHON PIPELINE  (project root)                                     │
│                                                                      │
│  EXISTING:                          NEW (v2.0):                      │
│  ingest_wechat.py                   ingest_github.py                 │
│  multimodal_ingest.py               rules_engine.json (data file)    │
│  kg_synthesize.py  ◄── called by    GSD_DISCUSS_PATTERN.md (doc)    │
│  cognee_batch_processor.py                                           │
│  skill_runner.py   ◄── MODIFIED (multi-turn support)                │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  async I/O
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DATA LAYER  (~/.hermes/omonigraph-vault/)                           │
│                                                                      │
│  EXISTING:                          NEW (v2.0):                      │
│  lightrag_storage/                  entity_registry.json (project root)│
│  images/{hash}/                                                      │
│  canonical_map.json                                                  │
│  entity_buffer/                                                      │
│  synthesis_output.md                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

### Existing components (v1.1 — no modification required unless noted)

| Component | File | Responsibility | v2.0 change |
|-----------|------|----------------|-------------|
| Ingestion entry point | `ingest_wechat.py` | Apify/CDP scrape → LightRAG ainsert + entity buffer | NONE — GitHub ingestion is a separate script |
| PDF ingestion | `multimodal_ingest.py` | PDF extract → LightRAG ainsert | NONE |
| Synthesis engine | `kg_synthesize.py` | canonical_map → LightRAG aquery → Cognee recall → Gemini → stdout | NONE — architect.sh calls it directly |
| Config | `config.py` | Path constants, `~/.hermes/.env` loader | ADD 2 constants: `ENTITY_REGISTRY_FILE`, `GITHUB_TOKEN` |
| Skill simulator | `skill_runner.py` | Load SKILL.md as system prompt, run JSON test cases (single-turn) | MODIFY — add multi-turn `inputs: list[str]` support |
| Ingest skill | `skills/omnigraph_ingest/` | Agent decision tree → `ingest.sh` | NONE |
| Query skill | `skills/omnigraph_query/` | Agent decision tree → `query.sh` | NONE |

### New components (v2.0 — net-new, does not exist yet)

| Component | File | Responsibility |
|-----------|------|----------------|
| Rules data file | `rules_engine.json` | 20–30 structured architecture rules: id, condition, recommendation, dont_use |
| GitHub ingestion | `ingest_github.py` | GitHub REST API batch fetch → markdown → LightRAG ainsert + entity_registry.json update |
| Entity registry | `entity_registry.json` | GitHub URL → entity ID mapping (written by ingest_github.py, read by /architect) |
| Architect skill | `skills/omnigraph_architect/SKILL.md` | Decision tree for 3 modes: Propose, Query, Ingest |
| Architect shell wrapper | `skills/omnigraph_architect/scripts/architect.sh` | venv activate → mode-dispatch → kg_synthesize.py or ingest_github.py |
| Discussion pattern doc | `.planning/GSD_DISCUSS_PATTERN.md` | 4-step Propose-mode conversation template (doc only, not executable) |
| Architect test suite | `tests/skills/test_omnigraph_architect.json` | 9 test cases (3 per mode) for skill_runner.py |

---

## Recommended Project Structure

```
OmniGraph-Vault/
├── config.py                         # MODIFY: add ENTITY_REGISTRY_FILE, GITHUB_TOKEN
├── ingest_wechat.py                  # no change
├── ingest_github.py                  # NEW: GitHub REST API batch ingestion
├── kg_synthesize.py                  # no change
├── skill_runner.py                   # MODIFY: multi-turn support
├── rules_engine.json                 # NEW: 20-30 architecture rules
├── entity_registry.json              # NEW: GitHub URL → entity ID map
│
├── skills/
│   ├── omnigraph_ingest/             # no change
│   ├── omnigraph_query/              # no change
│   └── omnigraph_architect/          # NEW skill directory
│       ├── SKILL.md                  # NEW: 3-mode decision tree
│       ├── scripts/
│       │   └── architect.sh          # NEW: mode-dispatch shell wrapper
│       ├── references/
│       │   ├── rules-overview.md     # NEW: human-readable rules summary for Level-2
│       │   └── api-surface.md        # NEW: architect.sh args, output format
│       ├── evals/
│       │   └── evals.json            # NEW: eval metadata (mirrors ingest/query pattern)
│       └── README.md                 # NEW: human-facing install + test guide
│
├── tests/
│   └── skills/
│       ├── test_omnigraph_ingest.json   # no change
│       ├── test_omnigraph_query.json    # no change
│       └── test_omnigraph_architect.json # NEW: 9 test cases
│
└── .planning/
    └── GSD_DISCUSS_PATTERN.md        # NEW: Propose-mode 4-step template (doc)
```

---

## Architectural Patterns

### Pattern 1: rules_engine.json as read-only lookup — loaded by architect.sh, not kg_synthesize.py

**What:** `rules_engine.json` lives at the project root and is read directly by `architect.sh`
before it calls `kg_synthesize.py`. The synthesis engine is NOT modified. Rules are injected
into the query as a prepended system context, not embedded in the Python pipeline.

**Concrete flow:**

```bash
# architect.sh (Propose mode)
RULES=$(python -c "import json,sys; rules=json.load(open('rules_engine.json')); \
  print('\n'.join(f\"[{r['id']}] {r['recommendation']}\" for r in rules))")
python kg_synthesize.py "ARCHITECTURE RULES:\n$RULES\n\nUSER QUERY: $QUERY" hybrid
```

Alternatively, architect.sh can pass rules as a prepended file argument — but the subprocess
contract for `kg_synthesize.py` already accepts a free-text query string, so inline prepending
is the lowest-friction approach. `kg_synthesize.py::synthesize_response(query_text, mode)` at
line 48 takes `query_text` as a plain string — rules text prepended to this string requires zero
changes to the Python side.

**When to use:** Rules are stable reference data, not runtime state. Loading them at the shell
layer keeps `kg_synthesize.py` ignorant of the rules concept (clean separation).

**Trade-offs:** Rules text grows the Gemini context window for every Propose query. At 20–30
rules averaging ~50 words each, this is ~1500 tokens — acceptable for Gemini 2.5 Flash.

### Pattern 2: architect.sh mode dispatch from parsed input, SKILL.md routes conceptually

**What:** The SKILL.md decision tree instructs the agent which mode applies (Propose/Query/Ingest)
based on natural language. The agent then calls `architect.sh <mode> "<query_or_url>"`. The shell
script dispatches based on the mode argument.

**Concrete architect.sh structure:**

```bash
#!/usr/bin/env bash
# skills/omnigraph_architect/scripts/architect.sh
# Usage: architect.sh propose "<question>"
#        architect.sh query "<question>"
#        architect.sh ingest "<github-url>"

set -euo pipefail

OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"
MODE="${1:-}"
INPUT="${2:-}"

# ... venv activation (same pattern as ingest.sh and query.sh) ...

cd "$OMNIGRAPH_ROOT"

case "$MODE" in
  propose)
    RULES=$(python -c "
import json
rules = json.load(open('rules_engine.json'))
for r in rules:
    print(f\"[{r['id']}] {r['recommendation']}\")
")
    python kg_synthesize.py "ARCHITECTURE RULES CONTEXT:
$RULES

USER ARCHITECTURE QUESTION: $INPUT" hybrid
    ;;
  query)
    python kg_synthesize.py "$INPUT" hybrid
    ;;
  ingest)
    python ingest_github.py "$INPUT"
    ;;
  *)
    echo "Usage: architect.sh <propose|query|ingest> <input>" >&2
    exit 1
    ;;
esac
```

**Why SKILL.md routing handles mode selection:** The agent reads the SKILL.md decision tree and
identifies which mode applies from the user's natural language. It then calls
`scripts/architect.sh <mode> "<query>"` with the explicit mode argument. This avoids NLP parsing
in bash, which is fragile. The shell script's job is pure dispatch, not intent detection.

**When to use:** Any multi-mode skill. Mode-as-first-argument is a stable CLI convention that
`skill_runner.py` test cases can directly assert against.

### Pattern 3: ingest_github.py follows ingest_wechat.py architecture exactly

**What:** `ingest_github.py` is a new entry point script with the same structure as
`ingest_wechat.py`. It uses the GitHub REST API (no Graphify MCP — confirmed unavailable) to
fetch README + description for a repository, then calls `rag.ainsert()` and writes
`entity_registry.json`.

**Concrete structure:**

```python
# ingest_github.py — mirrors ingest_wechat.py structure
import asyncio, json, os, sys, requests
from config import RAG_WORKING_DIR, load_env, ENTITY_REGISTRY_FILE

load_env()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # optional, avoids rate limiting

async def fetch_github_repo(url: str) -> dict:
    """Convert github.com/owner/repo URL → REST API call → markdown content."""
    # Parse owner/repo from URL
    # GET https://api.github.com/repos/{owner}/{repo}
    # GET https://raw.githubusercontent.com/{owner}/{repo}/main/README.md
    ...

async def ingest_repo(url: str):
    content = await fetch_github_repo(url)
    rag = await get_rag()  # same get_rag() pattern as ingest_wechat.py
    await rag.ainsert(content["markdown"])
    # Update entity_registry.json atomically (tmp → rename, same as canonical_map.json)
    _update_entity_registry(url, content["entity_id"])

if __name__ == "__main__":
    url = sys.argv[1]
    asyncio.run(ingest_repo(url))
```

**Why not extend ingest_wechat.py:** Adding GitHub as a source to `ingest_wechat.py` would
require a `--source` flag and conditional dispatch, which complicates the existing script's
contract and the ingest skill's test cases. A separate script preserves the subprocess-as-contract
boundary pattern.

### Pattern 4: skill_runner.py multi-turn — inputs list replaces single input field

**What:** The `TestCase` dataclass gains an `inputs: list[str]` field (plural). When present,
the runner maintains a conversation history across turns and checks `expect_contains` only on the
final turn's response. The existing `input: str` field remains for backward compatibility
(single-turn cases).

**Concrete TestCase change (skill_runner.py):**

```python
@dataclass
class TestCase:
    description: str
    input: str = ""                          # kept for backward compat (single-turn)
    inputs: list[str] = field(default_factory=list)  # NEW: multi-turn
    expect_contains: list[str] = field(default_factory=list)
    expect_not_contains: list[str] = field(default_factory=list)
    load_references: list[str] = field(default_factory=list)
    expect_final_only: bool = True           # NEW: when True, check expects on last turn only
```

`call_gemini()` needs a `history: list[dict]` parameter. The Gemini SDK `types.Content` object
supports multi-turn via the `contents` list (alternating user/model roles).

**Impact on existing test cases:** Zero — existing JSON files use `"input"` (singular).
The runner checks `inputs` first; if empty, falls back to `input`.

---

## Data Flow

### /architect Propose Mode (rules + KB → structured recommendation)

```
User: "I'm building a solo project, should I use microservices?"
    ↓
SKILL.md decision tree → identifies Propose mode
    ↓
Agent calls: scripts/architect.sh propose "should I use microservices?"
    ↓
architect.sh:
    1. Load rules_engine.json → flatten to rules text (~1500 tokens)
    2. Build augmented query: "ARCHITECTURE RULES CONTEXT:\n{rules}\n\nUSER QUESTION: {input}"
    3. Call: python kg_synthesize.py "{augmented_query}" hybrid
    ↓
kg_synthesize.py::synthesize_response():
    1. Load canonical_map.json → normalize entity names in query (line 54-64)
    2. Cognee recall → fetch past synthesis context (line 66-72)
    3. Build custom_prompt with historical context (line 72-74)
    4. LightRAG aquery(mode=hybrid) → graph retrieval against populated KB (line 75-85)
    5. Gemini synthesis → Markdown response
    6. Cognee remember → store for future recall (line 87-90)
    7. Write to synthesis_output.md + stdout
    ↓
Agent reads stdout → presents recommendation to user
```

Note: The GSD:DISCUSS 4-step pattern is documented in `.planning/GSD_DISCUSS_PATTERN.md` and
referenced in the SKILL.md body. It describes how the agent conducts the multi-turn conversation
(default guess → Q1 → Q2 → output). This is an instruction pattern in SKILL.md, not a code
component. No Python changes are needed to implement GSD:DISCUSS — it is purely agent behavior
guided by SKILL.md.

### /architect Query Mode (direct KB lookup, no rules injection)

```
User: "What is LangChain's relationship to LlamaIndex?"
    ↓
SKILL.md → Query mode (factual question, no design decision)
    ↓
architect.sh query "What is LangChain's relationship to LlamaIndex?"
    ↓
python kg_synthesize.py "{query}" hybrid
    ↓ (same flow as omnigraph_query skill — no rules overhead)
stdout → agent
```

### /architect Ingest Mode (GitHub URL → KB)

```
User: "Add this GitHub tool to my KB: github.com/langchain-ai/langchain"
    ↓
SKILL.md → Ingest mode
    ↓
architect.sh ingest "https://github.com/langchain-ai/langchain"
    ↓
python ingest_github.py "https://github.com/langchain-ai/langchain"
    ↓
ingest_github.py:
    1. Parse owner/repo from URL
    2. GitHub REST API: GET /repos/{owner}/{repo} → metadata
    3. Fetch README.md via raw.githubusercontent.com
    4. Build markdown: "# {name}\n\n{description}\n\n{readme_content}"
    5. rag.ainsert(markdown) → LightRAG storage
    6. Atomic write: entity_registry.json[url] = entity_id (tmp → rename)
    ↓
stdout: "Ingested {repo_name} (entity: {entity_id})"
    ↓
Agent confirms to user
```

### skill_runner.py Multi-Turn Flow (Propose mode testing)

```
test_omnigraph_architect.json (Propose case):
    "inputs": [
        "I'm planning a new project, help me choose the architecture",
        "It's a solo hobby project",
        "I want to add features incrementally"
    ],
    "expect_contains": ["monolith", "avoid microservices"]

    ↓
run_test_case():
    Turn 1: call_gemini(system_prompt, inputs[0]) → response_1
    Turn 2: call_gemini(system_prompt, inputs[1], history=[{user:inputs[0]}, {model:response_1}])
    Turn 3: call_gemini(system_prompt, inputs[2], history=[...accumulated...]) → final_response
    Check expect_contains against final_response only (expect_final_only=True)
```

---

## New vs Modified Components

### New (does not exist, must be created from scratch)

| Component | File path | Phase |
|-----------|-----------|-------|
| Architecture rules | `rules_engine.json` | Phase 2.1 |
| GitHub ingestion script | `ingest_github.py` | Phase 2.1 |
| Entity registry | `entity_registry.json` | Phase 2.1 (written by ingest_github.py on first run) |
| config.py additions | `config.py` lines | Phase 2.1 (prerequisite for ingest_github.py) |
| Discussion pattern doc | `.planning/GSD_DISCUSS_PATTERN.md` | Phase 2.2 |
| Architect skill | `skills/omnigraph_architect/SKILL.md` | Phase 2.2 |
| Architect shell wrapper | `skills/omnigraph_architect/scripts/architect.sh` | Phase 2.2 |
| Architect skill references | `skills/omnigraph_architect/references/` | Phase 2.2 |
| Architect test cases | `tests/skills/test_omnigraph_architect.json` | Phase 2.2 |

### Modified (exists, requires targeted changes)

| Component | File path | Change | Phase |
|-----------|-----------|--------|-------|
| Config constants | `config.py` | Add `ENTITY_REGISTRY_FILE = BASE_DIR / "entity_registry.json"` and `GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")` | Phase 2.1 |
| Skill simulator | `skill_runner.py` | Add `inputs: list[str]` to `TestCase`; add `history` param to `call_gemini()`; update `run_test_case()` loop | Phase 2.2 |

### Unchanged (confirmed stable, do not touch)

| Component | Reason |
|-----------|--------|
| `ingest_wechat.py` | architect.sh never calls it; GitHub has its own script |
| `kg_synthesize.py` | architect.sh calls it as-is; rules text is prepended in the query string |
| `multimodal_ingest.py` | Not involved in v2.0 |
| `cognee_batch_processor.py` | Not involved in v2.0 |
| `skills/omnigraph_ingest/` | No change to existing skill |
| `skills/omnigraph_query/` | No change to existing skill |
| `config.py` `load_env()` | Stable; GITHUB_TOKEN + ENTITY_REGISTRY_FILE are additive |

---

## Build Order

The dependency graph enforces this sequence:

```
Phase 2.1 — Rules Engine + KB Population
─────────────────────────────────────────

Step 1: config.py additions
  Adds: ENTITY_REGISTRY_FILE, GITHUB_TOKEN constants
  Required by: ingest_github.py (imports these constants)
  Dependency: none — this is the root

Step 2: rules_engine.json
  Bootstrapped via Copilot GPT-5.4 researcher mode (external)
  Required by: architect.sh at runtime (shell reads this file)
  Dependency: none — standalone JSON data file

Step 3: ingest_github.py
  Required by: architect.sh (Ingest mode calls this script)
  Required by: KB population (50+ GitHub tools)
  Dependency: Step 1 (config.py constants must exist)

Step 4: entity_registry.json
  Created automatically on first run of ingest_github.py
  Dependency: Step 3

Step 5: KB population (data work, not code)
  Run ingest_github.py for 50+ repos
  Run ingest_wechat.py for 5-10 KOL articles
  Dependency: Step 3 (ingest_github.py must work)
  Verify: query_lightrag.py returns substantive answers

Phase 2.2 — /architect Skill
─────────────────────────────

Step 6: GSD_DISCUSS_PATTERN.md
  Documents the 4-step Propose conversation flow
  Required by: SKILL.md author (needs pattern defined before writing decision tree)
  Dependency: Step 2 (rules_engine.json must be finalized so pattern is concrete)

Step 7: skills/omnigraph_architect/SKILL.md + architect.sh
  Writes the 3-mode decision tree + shell dispatch wrapper
  Dependency: Step 2 (rules), Step 3 (ingest_github.py), Step 6 (GSD_DISCUSS_PATTERN.md)
  Note: architect.sh calls kg_synthesize.py (existing, no change) and ingest_github.py (Step 3)

Step 8: skill_runner.py multi-turn enhancement
  Adds inputs: list[str] + history accumulation
  Dependency: independent of Steps 1-7 (can be done in parallel with Step 7)
  Note: existing test files (test_omnigraph_ingest.json, test_omnigraph_query.json) are
        backward compatible — no changes to passing test suites

Step 9: tests/skills/test_omnigraph_architect.json
  Writes 9 test cases (3 per mode)
  Dependency: Step 7 (SKILL.md must exist to know what to test), Step 8 (multi-turn runner needed)

Step 10: Integration validation
  python skill_runner.py skills/ --test-all
  All 3 skills must pass: omnigraph_ingest (9/9), omnigraph_query (10/10), omnigraph_architect (9/9)
  Dependency: Steps 7, 8, 9 complete
```

Critical path: Step 1 → Step 3 → Step 7 → Step 9 → Step 10.
Step 2 (rules_engine.json) and Step 8 (skill_runner.py) can proceed in parallel with their
respective phases.

---

## Integration Points

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| GitHub REST API | `GET /repos/{owner}/{repo}` and raw README fetch in `ingest_github.py` | GITHUB_TOKEN optional but recommended (60 req/hr unauth vs 5000 auth). No OAuth needed — read-only public API. |
| Gemini API | `kg_synthesize.py` (existing). `ingest_github.py` uses same `llm_model_func` / `embedding_func` pattern. | Same API key, same quota. ingest_github.py adds ~2 Gemini calls per repo (embed + entity extract). |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `architect.sh` → `kg_synthesize.py` | subprocess call with augmented query string | rules_engine.json content is prepended to query_text; no changes to kg_synthesize.py interface |
| `architect.sh` → `ingest_github.py` | subprocess call with GitHub URL as argv[1] | same subprocess-as-contract-boundary pattern as ingest.sh → ingest_wechat.py |
| `ingest_github.py` → `entity_registry.json` | atomic write (tmp → rename) | mirrors canonical_map.json write pattern already established in cognee_batch_processor.py |
| `skill_runner.py` → `TestCase.inputs` | backward-compatible dataclass field | `input` (singular) still works; `inputs` (list) enables multi-turn; runner checks `inputs` first |
| `SKILL.md` (architect) → `rules_engine.json` | runtime — architect.sh reads the file | SKILL.md body instructs agent to call `architect.sh propose "<question>"`; shell loads rules |

---

## Anti-Patterns

### Anti-Pattern 1: Modifying kg_synthesize.py to be "rules-aware"

**What people do:** Add a `rules_file` argument to `kg_synthesize.py` or `synthesize_response()`;
load and inject rules inside the Python function.

**Why it's wrong:** `kg_synthesize.py` is called by three paths (architect.sh Propose mode,
architect.sh Query mode, query.sh). Injecting rules-awareness into the function means rules apply
to all calls — including Query mode and omnigraph_query calls — which is incorrect. It also
adds a new required parameter to an existing passing interface.

**Do this instead:** Load rules in `architect.sh` at the shell layer and prepend to the query
string before calling `python kg_synthesize.py`. The Python interface stays clean; rules
injection is the caller's responsibility.

### Anti-Pattern 2: Three-argument dispatch in architect.sh

**What people do:** Pass mode as an embedded prefix in the query string:
`architect.sh "propose: should I use microservices?"` and parse in bash with `cut`.

**Why it's wrong:** Fragile string parsing in bash; breaks when user input contains `:` or
spaces before the mode keyword. The SKILL.md decision tree already extracts intent — it should
pass the mode explicitly as a positional argument.

**Do this instead:** `architect.sh <mode> "<query>"` — explicit positional arg, clean case
statement in shell, no parsing.

### Anti-Pattern 3: Writing entity_registry.json to ~/.hermes/ data dir

**What people do:** Store `entity_registry.json` in `BASE_DIR` (`~/.hermes/omonigraph-vault/`)
alongside `canonical_map.json`.

**Why it's wrong:** `entity_registry.json` maps GitHub URLs to LightRAG entity IDs. It is code
metadata, not user data — it should travel with the repository (committed to git) so it is
reproducible. `canonical_map.json` contains learned entity aliases from Cognee (dynamic, user-data,
not committed). These are conceptually different.

**Do this instead:** Store `entity_registry.json` at project root. Add to `.gitignore` only if
it will contain private repo URLs; for public AI tool repos, commit it.

### Anti-Pattern 4: Blocking the architect skill on batch GitHub ingestion

**What people do:** architect.sh Ingest mode triggers ingestion of an entire curated list
(e.g., 50 repos) in one synchronous call.

**Why it's wrong:** Single-repo ingest takes 15–60 seconds (LightRAG ainsert + Gemini embed).
50 repos = 12–50 minutes blocking the agent. Hermes will time out or the user will kill it.

**Do this instead:** architect.sh Ingest mode ingests one URL at a time (same as ingest.sh).
Bulk ingestion is a separate data-population task run manually: `for url in ...; do python ingest_github.py "$url"; done`.

---

## Scaling Considerations

This is a single-user, local tool. Scaling is about pipeline reliability over time, not load.

| Concern | Current state (v2.0 target) | Mitigation |
|---------|------------------------------|------------|
| Rules engine size | 20–30 rules (~1500 tokens) | Acceptable. At 100+ rules, split into rule categories and load only matching category in architect.sh |
| entity_registry.json growth | 50–100 GitHub repos initially | JSON file with 100 entries is <10 KB. No database needed until 10k+ entries. |
| LightRAG graph with 50+ repos + 10 articles | ~60 documents total | LightRAG (kuzu backend) handles thousands of nodes; no concern at this scale |
| Gemini quota during bulk ingestion | 50 repos × 2 calls = 100 Gemini calls | Run ingest_github.py sequentially with 1–2 second sleep between calls; free tier handles this over ~2 hours |
| skill_runner.py multi-turn context | 3-turn Propose test × 9 cases = 27 Gemini calls per test run | Acceptable; existing 19 test cases already make 19 calls |

---

## Sources

- `kg_synthesize.py` — `synthesize_response(query_text, mode)` signature at line 48; `query_text`
  is a plain string that architect.sh can prepend rules text to without any Python changes.
- `config.py` — current constants at lines 5-13; `ENTITY_REGISTRY_FILE` and `GITHUB_TOKEN`
  additions follow the exact same pattern as existing constants.
- `ingest_wechat.py` — `ingest_article()` structure, `get_rag()` pattern, entity buffer write
  pattern at lines 437-445; `ingest_github.py` mirrors this exactly.
- `skills/omnigraph_ingest/scripts/ingest.sh` and `skills/omnigraph_query/scripts/query.sh` —
  canonical shell wrapper pattern (OMNIGRAPH_ROOT resolution, venv activation, cd, dispatch).
  `architect.sh` follows this pattern with a mode-dispatch case statement added.
- `skill_runner.py` — `TestCase` dataclass at line 68-74; `call_gemini()` at line 153;
  `run_test_case()` at line 196-211. Multi-turn enhancement is additive to these exact functions.
- `skills/omnigraph_query/SKILL.md` and `skills/omnigraph_ingest/SKILL.md` — SKILL.md structure,
  decision-tree body format, frontmatter schema. `omnigraph_architect` SKILL.md follows the same format.
- `PROJECT.md` — confirmed Graphify MCP unavailable (line 50 notes this); GitHub REST API is
  the replacement approach for `ingest_github.py`.
- `.planning/MILESTONE-2-SIMPLE-GUIDE.md` — authoritative task list and success criteria for
  Phase 2.1 and 2.2; used to derive build order.

---

*Architecture research for: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP*
*Researched: 2026-04-23*
*Confidence: HIGH — all findings derived from actual source files, no external docs.*
