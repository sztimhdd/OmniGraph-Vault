# Architecture Patterns: Hermes Skill Deployment

**Project:** OmniGraph-Vault — Phase 2 (Skill Packaging + Gate 6/7)
**Researched:** 2026-04-21
**Confidence:** HIGH for in-repo patterns (codebase analysis); MEDIUM for Hermes-specific conventions
(official URLs unreachable from this endpoint; CLAUDE.md treated as authoritative proxy since it
was synthesized from those docs by the project author).

---

## Recommended Architecture

The system has two distinct deployment layers:

```
┌─────────────────────────────────────────────────────────────┐
│  HERMES AGENT (natural language interface)                  │
│  - Loads SKILL.md at Level 1 on dispatch                    │
│  - Matches trigger phrases to skill catalog                 │
│  - Reads exec output as free-text response                  │
└────────────────────┬────────────────────────────────────────┘
                     │  exec (shell)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  SKILL LAYER  (skills/ at project root)                     │
│                                                             │
│  omnigraph-ingest/           omnigraph-query/               │
│  ├── SKILL.md                ├── SKILL.md                   │
│  ├── scripts/run-ingest.sh   ├── scripts/run-query.sh       │
│  └── references/             └── references/               │
│      api-surface.md              api-surface.md             │
└────────────────────┬────────────────────────────────────────┘
                     │  subprocess (activated venv python)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PYTHON PIPELINE  (project root)                            │
│                                                             │
│  ingest_wechat.py            kg_synthesize.py               │
│  multimodal_ingest.py        query_lightrag.py              │
│  cognee_batch_processor.py   list_entities.py               │
└────────────────────┬────────────────────────────────────────┘
                     │  async I/O
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER  (~/.hermes/omonigraph-vault/)                  │
│                                                             │
│  lightrag_storage/   images/{hash}/   canonical_map.json   │
│  entity_buffer/      synthesis_output.md                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `SKILL.md` | Decision tree for agent: when to trigger, what args to pass, how to surface errors | Agent reads at Level 1 |
| `scripts/run-*.sh` | Venv activation, cwd setup, pre-flight env checks, python call | Shell exec from agent |
| `ingest_wechat.py` | Web scraping → content enrichment → LightRAG insert | LightRAG, Gemini, Apify/CDP |
| `kg_synthesize.py` | Query normalization → graph retrieval → synthesis → Cognee store | LightRAG, Cognee, Gemini |
| `cognee_batch_processor.py` | Async entity canonicalization (runs separately) | Cognee, entity_buffer/ |
| `skill_runner.py` | Local test harness: load SKILL.md as system prompt, run JSON test cases | Gemini (direct API call) |

---

## Skill Directory Structure

Every skill is a **directory**, not a single file. Placement in the repo: `skills/` at project root.
This is the highest OpenClaw/Hermes precedence scope (`<workspace>/skills/`).

```
skills/
├── omnigraph-ingest/
│   ├── SKILL.md              # Agent-facing: triggers, decision tree, error handling (required)
│   ├── scripts/
│   │   └── run-ingest.sh     # Shell wrapper: venv activate → python ingest_wechat.py "$1"
│   ├── references/
│   │   └── api-surface.md    # Script args, output format, method strings — Level 2 only
│   └── README.md             # Human-facing: install, test, publish steps
│
└── omnigraph-query/
    ├── SKILL.md
    ├── scripts/
    │   └── run-query.sh      # Shell wrapper: venv activate → python kg_synthesize.py "$1" "$2"
    ├── references/
    │   └── api-surface.md    # Query modes, output schema, synthesis_output.md path
    └── README.md
```

**Separation rule:** `references/` = files the agent reads. `scripts/` = files the agent executes.
Never put Python modules in `scripts/` and never put shell scripts in `references/`.

---

## Invocation Chain: Async Python from a Shell Exec

This is the most critical architectural detail. The agent executes a shell script via `exec`. That
shell script must activate the venv and call Python. The Python scripts use `asyncio.run()` (not
`nest_asyncio`) when invoked as CLI entry points.

### Why two layers (shell wrapper + python)?

1. **Venv activation requires a shell source step.** A bare `exec python ingest_wechat.py` uses the
   system Python without packages. The shell wrapper `source venv/Scripts/activate` (Windows) or
   `source venv/bin/activate` (Linux/macOS) before calling python resolves this.
2. **Working directory must be the project root.** Scripts do `from config import RAG_WORKING_DIR` —
   relative imports require cwd to be the project root. The shell wrapper sets `cd "$PROJECT_DIR"`.
3. **Cross-platform path.** Windows uses `venv\Scripts\python`; Linux/macOS uses `venv/bin/python`.
   The wrapper checks both and falls back cleanly.

### Shell wrapper pattern (canonical)

```bash
#!/bin/bash
# skills/omnigraph-ingest/scripts/run-ingest.sh
set -e

# Resolve project root relative to this script's location (skills/omnigraph-ingest/scripts/)
PROJECT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$PROJECT_DIR"

# Pre-flight: required env vars
if [ -z "$GEMINI_API_KEY" ]; then
  echo "ERROR: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env" >&2
  exit 1
fi

# Activate venv (cross-platform)
if [ -f "venv/Scripts/activate" ]; then
  source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "ERROR: venv not found. Run: python -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi

python ingest_wechat.py "$1"
```

The query wrapper passes two args:

```bash
python kg_synthesize.py "$1" "${2:-hybrid}"
```

### asyncio.run() vs nest_asyncio in CLI context

`ingest_wechat.py` uses `nest_asyncio.apply()` at module level (line 29). This is fine when the
script is invoked as a subprocess (fresh Python process, no existing event loop). The pattern is:

```
Shell exec (no event loop) → python ingest_wechat.py → nest_asyncio.apply() (no-op, no loop) → asyncio.run(ingest_article(url))
```

`nest_asyncio` is harmless in CLI context. It only matters when another async framework (e.g.,
Jupyter, an existing uvloop) has already created an event loop. In the skill's subprocess invocation,
there is no existing loop, so `asyncio.run()` works directly and `nest_asyncio.apply()` does nothing.

**Do not remove nest_asyncio** from the scripts — it is needed for the interactive Python / Jupyter
development workflow. It is transparent in the subprocess path.

---

## SKILL.md Body Patterns

### Decision tree structure (required for agent determinism)

The body of SKILL.md must be explicit decision trees, not prose descriptions. The agent uses this
as a system prompt and must never guess which branch to take.

```markdown
## When to Trigger

Trigger this skill when the user wants to:
- Add a URL to the knowledge base
- Save an article for later reference
- Ingest content into the graph

DO NOT trigger for:
- Questions about stored knowledge → use `omnigraph_query`
- PDF files → also handled here (pass the file path, not a URL)
- Status checks → use `omnigraph_status`

## How to Call

1. Extract the URL or file path from the user's message.
2. Call: `scripts/run-ingest.sh "<url_or_path>"`
3. Wait for output (may take 30–300 seconds for web scraping).
4. Present the output summary to the user.

## Output Interpretation

Success output contains:
- "--- Successfully Ingested! ---"
- Article title, hash, method (apify or cdp), local path

On success, respond: "Saved '[title]' to your knowledge base (method: [method], id: [hash])."

## Error Handling

If exit code is non-zero:
- GEMINI_API_KEY error → ⚠️ Config: GEMINI_API_KEY not set. Add it to ~/.hermes/.env
- Import error → ⚠️ Setup: Python package missing. Run: pip install -r requirements.txt
- CDP error → ⚠️ Browser: CDP not running. Start Edge with --remote-debugging-port=9223
- "Query attempt 3 failed" → ⚠️ API: Gemini rate limit. Wait 60s and retry.
- Any other error → ⚠️ Unknown: [last stderr line]. Check console for full traceback.
```

### Progressive disclosure: what goes in SKILL.md vs references/

| Content | Location | Why |
|---------|----------|-----|
| Trigger conditions + "do not trigger" list | SKILL.md body | Agent reads at Level 1 — must be fast to load |
| Call sequence, output interpretation, error table | SKILL.md body | Core operating instructions |
| Full argument table with all modes | `references/api-surface.md` | Heavy; only needed for advanced usage |
| Output schema details (field names, types) | `references/api-surface.md` | Reference, not operating instructions |
| Troubleshooting deep-dives | `references/troubleshooting.md` | Agent fetches only when error occurs |

Target: SKILL.md body under 150 lines. If it grows beyond that, extract to references/.

---

## Gate 6: Cross-Article Synthesis Validation

Gate 6 goal: ingest 3 articles, then run one query that produces a response drawing from all three.

### Test script structure (`tests/verify_gate_6.py`)

The gate test follows the same pattern as verify_gate_a/b/c but operates at the pipeline level:

```python
#!/usr/bin/env python3
"""
tests/verify_gate_6.py — Cross-article synthesis validation.

Pass condition: kg_synthesize.py produces a response that contains
entity references from at least 2 of the 3 ingested articles.

Usage:
    python tests/verify_gate_6.py

Requires:
    - GEMINI_API_KEY set in ~/.hermes/.env
    - 3 articles already ingested (or runs fresh ingestion)
    - LightRAG storage populated at ~/.hermes/omonigraph-vault/lightrag_storage/
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RAG_WORKING_DIR, SYNTHESIS_OUTPUT, load_env
load_env()

# --- Test articles (use URLs that are publicly accessible and known to contain
#     distinct entities — choose 3 with overlapping domain but distinct subjects)
TEST_URLS = [
    "https://mp.weixin.qq.com/s/<article_1_hash>",  # Replace with real URLs
    "https://mp.weixin.qq.com/s/<article_2_hash>",
    "https://mp.weixin.qq.com/s/<article_3_hash>",
]

# Entities expected to appear in synthesis response — at least 2 of these
# must be present for the gate to pass. Choose entities that are unique to
# the chosen articles, not generic terms.
EXPECTED_ENTITIES = [
    "<entity_from_article_1>",
    "<entity_from_article_2>",
    "<entity_from_article_3>",
]

CROSS_ARTICLE_QUERY = (
    "Summarize the key themes and relationships across the articles I've ingested."
)

async def check_storage_populated() -> bool:
    """Return True if LightRAG storage has graph data."""
    graph_file = RAG_WORKING_DIR / "graph_chunk_entity_relation.graphml"
    if not graph_file.exists():
        return False
    stat = graph_file.stat()
    return stat.st_size > 1000  # non-trivial graph

async def run_synthesis(query: str, mode: str = "hybrid") -> str:
    """Run kg_synthesize.py as subprocess and return stdout."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "kg_synthesize.py", query, mode],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,  # project root
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"kg_synthesize.py failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
    # Read the synthesis output file (more reliable than stdout parsing)
    if SYNTHESIS_OUTPUT.exists():
        return SYNTHESIS_OUTPUT.read_text(encoding="utf-8")
    return result.stdout

async def main():
    print("=== Gate 6: Cross-Article Synthesis ===\n")

    # Step 1: Check LightRAG storage is populated
    print("Step 1: Checking LightRAG storage...")
    if not await check_storage_populated():
        print("FAIL: LightRAG storage empty or missing. Ingest 3 articles first.")
        sys.exit(1)
    print("  OK: LightRAG storage has data.\n")

    # Step 2: List ingested article hashes for audit trail
    images_dir = RAG_WORKING_DIR.parent / "images"
    article_hashes = [d.name for d in images_dir.iterdir() if d.is_dir()] if images_dir.exists() else []
    print(f"Step 2: Ingested article directories found: {len(article_hashes)}")
    if len(article_hashes) < 3:
        print(f"  WARNING: Only {len(article_hashes)} article(s) found. Gate 6 requires 3+.")
    for h in article_hashes[:5]:  # show up to 5
        meta_file = images_dir / h / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            print(f"  - {h}: {meta.get('title', '(no title)')}")
    print()

    # Step 3: Run cross-article synthesis
    print(f"Step 3: Running cross-article synthesis query...")
    print(f"  Query: \"{CROSS_ARTICLE_QUERY}\"")
    print("  (This may take 30–90 seconds...)\n")
    try:
        response = await run_synthesis(CROSS_ARTICLE_QUERY, mode="hybrid")
    except RuntimeError as e:
        print(f"FAIL: Synthesis script error:\n{e}")
        sys.exit(1)

    # Step 4: Check response is non-trivial
    if not response or len(response.strip()) < 200:
        print("FAIL: Synthesis response is empty or too short.")
        print(f"  Response length: {len(response)} chars")
        sys.exit(1)
    print(f"  OK: Synthesis response received ({len(response)} chars)\n")

    # Step 5: Check for cross-article signals in response
    # A genuine cross-article synthesis contains references to entities from
    # multiple articles. We check for the expected entities as a proxy.
    print("Step 4: Checking for cross-article entity coverage...")
    response_lower = response.lower()
    found = [e for e in EXPECTED_ENTITIES if e.lower() in response_lower]
    missing = [e for e in EXPECTED_ENTITIES if e.lower() not in response_lower]

    print(f"  Expected entities: {EXPECTED_ENTITIES}")
    print(f"  Found in response: {found}")
    print(f"  Missing:          {missing}")

    # Pass condition: at least 2 of N expected entities present
    MIN_ENTITIES_REQUIRED = max(2, len(EXPECTED_ENTITIES) // 2)
    if len(found) >= MIN_ENTITIES_REQUIRED:
        print(f"\n=== Gate 6 PASSED ({len(found)}/{len(EXPECTED_ENTITIES)} entities found) ===")
        # Save synthesis output for audit
        print(f"  Synthesis saved to: {SYNTHESIS_OUTPUT}")
        sys.exit(0)
    else:
        print(f"\n=== Gate 6 FAILED ({len(found)}/{len(EXPECTED_ENTITIES)} entities found, need {MIN_ENTITIES_REQUIRED}) ===")
        print("\nFull synthesis response (first 500 chars):")
        print(response[:500])
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

### Gate 6 checklist (manual, before running the script)

1. Start the image server: `cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &`
2. Ingest article 1: `python ingest_wechat.py "<url_1>"`
3. Ingest article 2: `python ingest_wechat.py "<url_2>"`
4. Ingest article 3: `python ingest_wechat.py "<url_3>"`
5. Note the unique entity names from each article's stdout (titles, author names, product names)
6. Fill `EXPECTED_ENTITIES` in verify_gate_6.py with those entity names
7. Run: `python tests/verify_gate_6.py`

**What "cross-article" actually means in LightRAG hybrid mode:** the hybrid query runs both local
(entity-focused) and global (theme-focused) retrieval. A genuine cross-article synthesis will surface
relationships that span document boundaries — e.g., "Article 1 discusses X, which also appears in
Article 3 as Y." The entity check in the gate script is a proxy for this: if the response mentions
entities from multiple distinct articles, it pulled from multiple graph segments.

---

## Gate 7: Hermes End-to-End Integration Test

Gate 7 validates that the skills work in a real Hermes Agent environment. This is a manual test
protocol, not an automated script (no Hermes install on the CI machine).

### Prerequisites

- Hermes Agent installed and running on the target PC
- Skills directory at `<workspace>/skills/` (highest precedence scope)
- `~/.hermes/.env` with `GEMINI_API_KEY` set
- Edge browser running with `--remote-debugging-port=9223` (for CDP fallback)
- Image server running on port 8765

### Trigger-phrase validation test plan

```
Test 1: Ingest trigger
  Input:  "add this to my kb: https://mp.weixin.qq.com/s/..."
  Pass:   Hermes dispatches omnigraph_ingest skill
  Verify: Response contains "Successfully Ingested" and article title

Test 2: Query trigger
  Input:  "what do I know about [entity from ingested article]?"
  Pass:   Hermes dispatches omnigraph_query skill
  Verify: Response is a multi-paragraph synthesis, not "I don't know"

Test 3: Cross-article query (Gate 6 at skill level)
  Input:  "summarize the key themes across everything I've saved"
  Pass:   Response references entities from more than one article
  Verify: Manual check of response content

Test 4: Wrong trigger rejection
  Input:  "what's the weather today?"
  Pass:   Hermes does NOT dispatch an omnigraph skill
  Verify: Normal Hermes response, no script execution

Test 5: Guard clause — missing env var
  Setup:  Temporarily remove GEMINI_API_KEY from ~/.hermes/.env
  Input:  "search my knowledge base for LightRAG"
  Pass:   Skill surfaces "⚠️ Config: GEMINI_API_KEY not set" error message
  Verify: No Python traceback visible to user; clean error message only

Test 6: CDP not running
  Setup:  Stop Edge CDP, remove APIFY_TOKEN
  Input:  "ingest https://mp.weixin.qq.com/s/..."
  Pass:   Skill surfaces "⚠️ Browser: CDP not running" error (after Apify fallback attempt)
  Verify: Error message includes remediation step
```

### skill_runner.py as Gate 7 pre-validation

Before running in real Hermes, validate all test cases locally:

```bash
# Structural validation (no API call)
python skill_runner.py skills/ --validate --test-all

# Run JSON test suites against Gemini (same backend as Hermes)
python skill_runner.py skills/ --test-all

# Single skill, verbose on failure
python skill_runner.py skills/omnigraph-query --test-file tests/skills/test_omnigraph_query.json -v
```

The `skill_runner.py` (already implemented at project root) loads SKILL.md as a system prompt and
sends test cases through `gemini-2.5-flash`. It validates:
- Trigger-phrase matching (does the LLM correctly identify when to use this skill?)
- Guard clause firing (does it surface the right error for missing env vars?)
- Output format compliance (does the response follow the defined format rules?)
- Wrong-skill rejection (does the LLM NOT invoke the skill for off-topic inputs?)

---

## Patterns to Follow

### Pattern 1: Subprocess-as-skill-boundary

The subprocess call is the contract boundary between the agent and the Python pipeline. The agent
knows nothing about Python internals — it only sees stdin/stdout/exit-code.

Keep the subprocess contract stable:
- Argument order is frozen once published (`"<url>"` for ingest, `"<query>" [mode]` for query)
- Exit 0 = success; exit 1 = error
- Success summary on stdout (last few lines are the user-facing result)
- Error explanation on stderr OR last stdout line

Do not add new required positional arguments to existing scripts after skills are in use. Add optional
flags with defaults instead.

### Pattern 2: Env var pre-flight in shell wrapper

The shell wrapper performs the env check before Python starts. This gives a clean, immediate error
message instead of a Python traceback 30 seconds into a scraping run.

```bash
if [ -z "$GEMINI_API_KEY" ]; then
  echo "ERROR: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env" >&2
  exit 1
fi
```

The agent SKILL.md body maps this stderr pattern to a user-friendly `⚠️ Config:` message.

### Pattern 3: Windows/macOS path resolution in shell wrapper

The `PROJECT_DIR` calculation must work when Hermes executes the script from any cwd:

```bash
# Resolve project root from script location (3 levels up: scripts/ → skill-dir → skills/ → project/)
PROJECT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$PROJECT_DIR"
```

On Windows Git Bash and macOS/Linux, `dirname "$0"` resolves correctly when the script is called
with an absolute path. Hermes/OpenClaw always passes absolute paths to exec scripts.

### Pattern 4: Keep Cognee off the ingestion fast path

`cognee_batch_processor.py` runs separately from ingestion. The ingest skill shell wrapper should
NOT start the batch processor — that would block the agent for minutes. The batch processor is a
background daemon the user runs independently.

The ingest SKILL.md body should mention this: "Entity canonicalization runs asynchronously. Run
`cognee_batch_processor.py` separately to update the canonical entity map."

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Calling Python directly without venv activation

**What:** `exec python ingest_wechat.py "$1"` directly in SKILL.md body
**Why bad:** Uses system Python (no lightrag, cognee, etc.); import errors at runtime
**Instead:** Always route through the shell wrapper in `scripts/`

### Anti-Pattern 2: Hardcoded absolute paths in scripts

**What:** `/home/sztimhdd/OmniGraph-Vault/entity_buffer` (seen in ingest_wechat.py lines 279-280)
**Why bad:** Silently breaks on any other machine (including the Windows deployment target)
**Instead:** Use `config.py` constants (`BASE_DIR / "entity_buffer"`)

This is a known pre-flight issue identified in STACK.md. Must be fixed before Gate 7.

### Anti-Pattern 3: Monolithic SKILL.md body

**What:** Putting all reference material (arg tables, output schemas, troubleshooting) in SKILL.md body
**Why bad:** Slow Level 1 load; Hermes loads the full body on every dispatch; token cost
**Instead:** Keep body under 150 lines; move heavy material to `references/`

### Anti-Pattern 4: Starting Cognee batch processor from skill

**What:** Shell wrapper runs `python cognee_batch_processor.py &` on every ingest
**Why bad:** Multiple background processes accumulate; batch processor is a long-running daemon
**Instead:** Run batch processor independently as a scheduled task; document this in SKILL.md

### Anti-Pattern 5: JSON-on-stdout as agent response format

**What:** Script prints `{"status": "ok", "title": "..."}` to stdout for the agent to parse
**Why bad:** Hermes reads stdout as free text; JSON adds parsing complexity with zero benefit
**Instead:** Print human-readable summary lines; the agent reads them directly

---

## Scalability Considerations

This is a single-user, local tool. Scalability concerns are about pipeline reliability, not load.

| Concern | Current state | Mitigation |
|---------|--------------|------------|
| LightRAG graph size | Unbounded growth | `omnigraph_manage` skill to prune; list_entities.py already exists |
| Gemini API quota | 15 requests/min (free tier) | Retry loop in kg_synthesize.py already handles this |
| Cognee memory size | Grows with every synthesis | Periodic Cognee reset via init_cognee.py |
| Entity buffer accumulation | entity_buffer/ grows without bound | `.processed` marker + periodic cleanup |
| Image disk usage | Each article: 5–50 MB | Manual management; `omnigraph_manage` skill for deletion |

---

## Sources

- CLAUDE.md (project), "OpenClaw / Hermes Skill Writing Standards" section — HIGH confidence for
  skill directory structure, SKILL.md format, trigger phrases, progressive disclosure levels
  (synthesized from hermes-agent.ai, docs.openclaw.ai, lushbinary.com by project author)
- PROJECT.md — subprocess interface as stated design decision, Gate 6/7 requirements
- STACK.md (research) — shell wrapper pattern, error surfacing protocol, known pre-flight issues
- ARCHITECTURE.md (codebase, .planning/codebase/) — layer boundaries, entry points, data flow
- ingest_wechat.py — nest_asyncio usage (line 29), asyncio.run() entry point (line 377)
- kg_synthesize.py — synthesize_response() async pattern, sys.exit() error protocol
- verify_gate_a/b/c.py — gate test script structure (asyncio.run(main()) pattern)
- skill_runner.py — test harness design, SKILL.md loading, Gemini call pattern
- config.py — BASE_DIR, RAG_WORKING_DIR, SYNTHESIS_OUTPUT constants (path management)
