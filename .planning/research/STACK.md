# Stack Research: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP

**Domain:** Local knowledge graph pipeline with rules engine + agent skill layer
**Researched:** 2026-04-23
**Confidence:** HIGH for codebase-grounded decisions; MEDIUM for Graphify (no official source reachable)

---

## Scope

This document covers ONLY additions and changes required for v2.0 features:

1. Rules engine (`rules_engine.json` — 20–30 structured rules)
2. GitHub AI tool ingestion (~100 repos into OmniGraph-Vault KB)
3. `entity_registry.json` (GitHub URL → entity ID mapping)
4. `skill_runner.py` multi-turn conversation support
5. `/architect` skill (`omnigraph_architect`) reading rules_engine.json + calling kg_synthesize.py

Validated v1.1 stack (LightRAG, Cognee, Gemini, Apify, Playwright CDP) is not re-researched.

---

## Feature-by-Feature Analysis

### Feature 1: Rules Engine (`rules_engine.json`)

**Verdict: No new libraries required. Pure Python + stdlib json.**

The rules engine is a structured JSON file with 20–30 records. The `/architect` skill reads it at
runtime and passes relevant rules to the prompt context sent to kg_synthesize.py. This is a data file,
not a rule-execution engine. No external DSL or rule-engine library (e.g., `durable-rules`, `pyknow`,
`business-rules`) is warranted for 20–30 static rules — those add dependency weight for zero benefit
at this scale.

**Structure confirmed from PROJECT.md:**

```json
{
  "id": "rule_001",
  "condition": "solo developer, greenfield project",
  "recommendation": "Use SQLite before Postgres; add complexity when you hit limits",
  "dont_use": ["microservices", "Kubernetes", "event sourcing"]
}
```

**What the `/architect` script does with it:**

1. Load `rules_engine.json` with `json.load()` (stdlib — already imported in codebase)
2. Match rules to user query context (simple string/keyword matching is sufficient for v2.0)
3. Inject matched rules into the system prompt passed to `kg_synthesize.py`

**requirements.txt change:** None.

---

### Feature 2: GitHub AI Tool Ingestion (~100 repos)

**Verdict: Graphify MCP is NOT viable for v2.0. Use GitHub REST API + existing ingest_wechat.py pipeline instead.**

#### Graphify MCP — Investigation

"Graphify MCP" is mentioned in MILESTONE-2-SIMPLE-GUIDE.md (Task 2.1-03) and OMNIGRAPH_PRODUCT_BRIEF.md
as a tool for "工具结构理解" (structural tool understanding). STATE.md explicitly flags it as an open
question: "Graphify MCP availability and schema — validate before Phase 4 GitHub tools ingestion task."

After exhaustive search through the codebase, specs, and planning docs:

- No Graphify Python package exists in requirements.txt or any import statement
- No Graphify MCP configuration file exists (no `mcp.json`, no server registration)
- The only references are in planning/specs documents, never in implementation files
- The MILESTONE-2-SIMPLE-GUIDE.md command `python ingest_wechat.py --source graphify --list tools.json`
  refers to a `--source` flag that does NOT exist in the current `ingest_wechat.py` (confirmed by
  reading the file — `sys.argv[1]` is the only argument, no argparse, no `--source`)

**Conclusion:** Graphify MCP is a planning placeholder from an earlier design session. It was never
implemented, never installed, and the interface assumed in the planning doc (`--source graphify`) was
speculative. There is no evidence it is a real, available package in the Python ecosystem that would
serve this purpose.

**Recommended alternative: GitHub REST API + new `ingest_github.py` script**

The OMNIGRAPH_VISION_Statement.md already specifies this approach explicitly:

> "Use GitHub public API (no CDP, no auth beyond token)"
> "Per repo, ingest: README.md, all .md files under /docs, issues labeled: question, help wanted,
>  tutorial, High-upvote Discussions"
> "Script: ingest_github.py"

The GitHub REST API at `https://api.github.com` returns JSON with repository metadata, README content
(base64-encoded), and issues. The existing `requests` library (already in requirements.txt) is
sufficient to call it. The content (README markdown + issue text) feeds directly into
`rag.ainsert()` — the same path used by article ingestion.

**GitHub API approach — key endpoints:**

| Endpoint | What it returns | Rate limit |
|----------|-----------------|------------|
| `GET /repos/{owner}/{repo}` | Stars, description, language, updated_at | 60/hr unauthenticated; 5000/hr with token |
| `GET /repos/{owner}/{repo}/readme` | Base64-encoded README.md | Same |
| `GET /repos/{owner}/{repo}/contents/docs` | Listing of /docs directory | Same |
| `GET /repos/{owner}/{repo}/issues?labels=tutorial` | Labeled issues | Same |

For 100 repos: with a `GITHUB_TOKEN` (fine-grained personal access token, read-only public repos),
rate limit is 5000/hr — sufficient to ingest 100 repos in one session.

**New library required: None.** The `requests` library already in requirements.txt handles all GitHub
API calls. `base64` is stdlib (used to decode README content). `json` is stdlib.

**New script required: `ingest_github.py`** — a new file at the project root following the same
pattern as `ingest_wechat.py`:

```python
# Signature (not an existing file — must be created)
async def ingest_github_repo(repo_url: str, github_token: str | None = None) -> None:
    """Fetch README + docs + issues for a GitHub repo and insert into LightRAG."""
    ...

async def ingest_github_batch(repo_list: list[str], github_token: str | None = None) -> None:
    """Batch-ingest a list of GitHub repo URLs."""
    ...
```

**New environment variable: `GITHUB_TOKEN`** — optional, raises rate limit from 60 to 5000/hr. Add
to `config.py` as `GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")` and document in `.env.template`.

**requirements.txt change:** None (requests already present).

---

### Feature 3: `entity_registry.json` (GitHub URL → entity ID mapping)

**Verdict: No new libraries required. Stdlib json + atomic write pattern (already established).**

`entity_registry.json` maps each GitHub repo URL to the entity ID LightRAG assigns it after ingestion.
This gives the `/architect` skill a stable anchor: "LangChain is at github.com/langchain-ai/langchain,
and its entity ID in the graph is X."

**Structure (inferred from OMNIGRAPH_PRODUCT_BRIEF.md):**

```json
{
  "github.com/langchain-ai/langchain": "entity_abc123",
  "github.com/anthropics/anthropic-sdk-python": "entity_def456"
}
```

**How to populate:** After each `ingest_github_repo()` call, the script queries LightRAG for the
entity matching the repo name, records the ID, and writes to `entity_registry.json` using the
existing atomic write pattern (write to `.tmp`, then `os.rename()`).

**LightRAG entity ID extraction:** LightRAG does not expose a direct "give me the entity ID for X"
query. The practical approach for v2.0 is to store the GitHub URL as the entity identifier directly
(the URL is globally unique and stable), rather than trying to map it to LightRAG's internal IDs.
The registry then serves as a human-readable index for the `/architect` skill.

**New constant for config.py:** `ENTITY_REGISTRY_FILE = BASE_DIR / "entity_registry.json"` — mirrors
the `CANONICAL_MAP_FILE` constant pattern.

**requirements.txt change:** None.

---

### Feature 4: `skill_runner.py` Multi-Turn Conversation Support

**Verdict: No new libraries required. Modify skill_runner.py to support `inputs: list[str]` in TestCase and maintain conversation history across turns using the existing Gemini client.**

#### Current state (confirmed from reading skill_runner.py)

`call_gemini()` currently takes `system_prompt: str` and `user_message: str`. It creates a new
stateless request each call. `TestCase` has a single `input: str` field. The Gemini `google-genai`
client supports multi-turn conversations via a `contents` list of alternating `user`/`model` messages.

#### Required changes (surgical — touch only what's needed)

**1. Extend `TestCase` dataclass** to support both single-turn and multi-turn:

```python
@dataclass
class TestCase:
    description: str
    input: str = ""                               # kept for backward compat
    inputs: list[str] = field(default_factory=list)  # new: multi-turn
    expect_contains: list[str] = field(default_factory=list)
    expect_not_contains: list[str] = field(default_factory=list)
    load_references: list[str] = field(default_factory=list)
```

Resolution rule: if `inputs` is non-empty, use `inputs`; else fall back to `input`. This preserves
all 19 existing test cases (9 ingest + 10 query) without modification.

**2. Extend `call_gemini()` to accept optional conversation history:**

The Gemini `google-genai` client accepts `contents` as a list of `types.Content` objects for
multi-turn. The pattern:

```python
def call_gemini(
    system_prompt: str,
    user_message: str,
    history: list | None = None,
) -> tuple[str, list]:
    """Returns (response_text, updated_history)."""
    ...
```

`history` is a list of `{"role": "user"|"model", "parts": [{"text": "..."}]}` dicts accumulated
across turns. On the first turn it's empty. Each turn appends the user message and the model response.

**3. New `run_multi_turn_test_case()` function:**

```python
def run_multi_turn_test_case(skill: SkillDef, case: TestCase) -> TestResult:
    """Run a multi-turn TestCase. Only check expect_* on the FINAL turn response."""
    system_prompt = _build_system_prompt(skill, case.load_references)
    history = []
    final_response = ""
    for turn_input in case.inputs:
        try:
            response, history = call_gemini(system_prompt, turn_input, history)
            final_response = response
        except Exception as exc:
            return TestResult(case=case, passed=False, response="", failures=[f"API error: {exc}"])
    # Evaluate expect_contains/not_contains only on final_response
    failures: list[str] = []
    response_lower = final_response.lower()
    for expected in case.expect_contains:
        if expected.lower() not in response_lower:
            failures.append(f"expected to contain: '{expected}'")
    for forbidden in case.expect_not_contains:
        if forbidden.lower() in response_lower:
            failures.append(f"expected NOT to contain: '{forbidden}'")
    return TestResult(case=case, passed=not failures, response=final_response, failures=failures)
```

**4. Update `run_test_case()` to dispatch:**

```python
def run_test_case(skill: SkillDef, case: TestCase) -> TestResult:
    if case.inputs:
        return run_multi_turn_test_case(skill, case)
    # existing single-turn path unchanged
    ...
```

**requirements.txt change:** None. `google-genai` already installed; multi-turn is a client-side
feature using the existing SDK.

**pyyaml dependency note:** `skill_runner.py` already conditionally imports `yaml` with a fallback
parser. For multi-turn test JSON files, no YAML is needed — test cases are JSON. `pyyaml` is NOT
required and should NOT be added; the fallback parser handles frontmatter correctly for v2.0.

---

### Feature 5: `/architect` Skill (`omnigraph_architect`)

**Verdict: No new libraries required. Uses existing kg_synthesize.py + rules_engine.json loaded via stdlib json.**

The `/architect` skill follows the identical pattern as `omnigraph_ingest` and `omnigraph_query`:

```
SKILL.md body (decision tree: Propose/Query/Ingest modes)
  → scripts/architect.sh (CWD-independent shell wrapper)
    → architect.py (new script, reads rules_engine.json, builds prompt, calls kg_synthesize.py)
      → kg_synthesize.py (existing, no changes)
        → LightRAG aquery() → Gemini → synthesized response
```

**Three modes for `/architect` (from MILESTONE-2-SIMPLE-GUIDE.md):**

| Mode | Trigger | What it does |
|------|---------|--------------|
| Propose | "what stack should I use for X" / "design a system for Y" | Applies rules engine + KG query to produce safe defaults + dont_use list + TDD template |
| Query | "what does OmniGraph know about LangChain" / "compare X vs Y" | Direct KG query, no rules application |
| Ingest | "add this tool to KB: [URL]" | Routes to ingest pipeline (calls ingest.sh / ingest_wechat.py) |

**architect.py script design:**

```python
# New file: architect.py
# Usage: python architect.py "<query>" [--mode propose|query|ingest]

def load_rules(rules_file: Path) -> list[dict]:
    with open(rules_file) as f:
        return json.load(f)

def match_rules(rules: list[dict], query: str) -> list[dict]:
    """Simple keyword match — no ML needed for 20-30 rules."""
    query_lower = query.lower()
    return [r for r in rules if any(kw in query_lower for kw in r.get("condition", "").lower().split())]

def build_propose_prompt(query: str, matched_rules: list[dict]) -> str:
    """Prepend matched rules to the query before kg_synthesize."""
    rules_text = "\n".join(
        f"- Rule {r['id']}: {r['recommendation']} (avoid: {', '.join(r.get('dont_use', []))})"
        for r in matched_rules
    )
    return f"Relevant architecture rules:\n{rules_text}\n\nUser question: {query}"
```

**Why not call kg_synthesize.py as a Python module (vs subprocess):** kg_synthesize.py uses
`nest_asyncio.apply()` and runs its own async event loop. Importing it as a module risks event loop
conflicts. The existing shell wrapper pattern (subprocess call) is cleaner and consistent with how
omnigraph_ingest and omnigraph_query work.

**requirements.txt change:** None.

---

## Recommended Stack: Summary Table

### New Libraries — NONE required

All v2.0 features are implementable with the existing stack. The table below confirms the analysis:

| Feature | New library? | Reason |
|---------|-------------|--------|
| rules_engine.json | No | stdlib json |
| GitHub repo ingestion | No | requests (already in requirements.txt) |
| entity_registry.json | No | stdlib json + atomic write |
| skill_runner multi-turn | No | google-genai already installed (multi-turn is SDK-native) |
| /architect skill | No | kg_synthesize.py subprocess call (existing pattern) |

### New Environment Variables Required

| Variable | File | Purpose | Optional? |
|----------|------|---------|-----------|
| `GITHUB_TOKEN` | `~/.hermes/.env` | GitHub REST API authentication (5000/hr vs 60/hr without) | Yes — unauthenticated is workable for one-time 100-repo ingest |

Add to `config.py`:

```python
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ENTITY_REGISTRY_FILE = BASE_DIR / "entity_registry.json"
```

Add to `.env.template`:

```
GITHUB_TOKEN=your_github_pat_here  # Optional. Read-only public repos token.
```

### New Files Required (Not Library Changes)

| File | Type | Purpose |
|------|------|---------|
| `ingest_github.py` | Python script | GitHub REST API → README + docs + issues → LightRAG ainsert() |
| `rules_engine.json` | JSON data | 20–30 architecture rules (bootstrapped via Copilot) |
| `entity_registry.json` | JSON data | GitHub URL → entity identifier mapping (populated by ingest_github.py) |
| `architect.py` | Python script | Rules matching + kg_synthesize.py dispatcher for /architect |
| `skills/omnigraph_architect/SKILL.md` | YAML + Markdown | Agent decision tree: Propose/Query/Ingest modes |
| `skills/omnigraph_architect/scripts/architect.sh` | Bash | CWD-independent wrapper calling architect.py |

### requirements.txt Changes

**None.** Current requirements.txt already includes all dependencies needed for v2.0.

For reference, the relevant existing dependencies and their v2.0 usage:

| Existing Package | v2.0 Usage |
|-----------------|-----------|
| `requests` | GitHub REST API calls in ingest_github.py |
| `google-genai` | Multi-turn conversation history in skill_runner.py |
| `lightrag-hku` | `rag.ainsert()` for GitHub repo content |
| `cognee` | Entity buffering (same path as article ingestion) |

**Note on unpinned versions:** requirements.txt currently has no version pins. This is acceptable for
a single-developer local tool — no production deployment, no CI, no dependency conflict risk with
other projects (isolated venv). Pinning is recommended if/when this moves to shared deployment.

---

## Alternatives Considered

### GitHub Ingestion Alternatives

| Considered | Recommended | Why Not |
|-----------|-------------|---------|
| Graphify MCP | GitHub REST API + requests | Graphify has no confirmed Python package, no implementation in codebase, `--source graphify` flag doesn't exist in ingest_wechat.py — it's a planning placeholder |
| PyGithub library | requests (raw API) | PyGithub is a full-featured GitHub API client — useful for complex workflows, but adds a dependency for what amounts to 3-4 simple GET calls per repo. Raw requests is 10 lines, no new install. |
| Firecrawl scraping | GitHub REST API | config.py already has FIRECRAWL_API_KEY loaded (suggesting it was considered). Firecrawl is external SaaS, adds latency, and charges per crawl. GitHub API is free for public repos and returns structured JSON — strictly better. |
| CDP/Playwright scraping of GitHub pages | GitHub REST API | GitHub has rate-limited REST API specifically designed for programmatic access. Scraping via CDP for repos that have a proper API is unnecessary complexity. |

### Rules Engine Alternatives

| Considered | Recommended | Why Not |
|-----------|-------------|---------|
| `durable-rules` / `pyknow` (Rete algorithm) | stdlib json + keyword matching | A 20–30 rule set does not benefit from Rete complexity. Loading and filtering a small JSON array is O(n) and entirely sufficient. These libraries add >10MB install, complex DSLs, and were designed for thousands of rules with complex interdependencies. |
| SQLite for rules storage | JSON file | Single developer, local tool, rules are bootstrapped once and rarely change. JSON is human-editable in any text editor. SQLite adds a schema migration concern with no benefit at this scale. |
| YAML for rules | JSON | JSON is already the project standard (canonical_map.json, entity_buffer/*.json, test case files). No reason to introduce a second serialization format. |

### skill_runner Multi-Turn Alternatives

| Considered | Recommended | Why Not |
|-----------|-------------|---------|
| Separate `multi_turn_runner.py` | Extend existing skill_runner.py | One tool, one entry point — simpler for users. The change is additive and backward-compatible (existing single `input` field still works). |
| LangChain ConversationChain for history | google-genai native history | No LangChain in this project. Introducing it for conversation history management would violate the "no framework migrations" constraint. google-genai natively supports multi-turn via a contents list. |

---

## What NOT to Add

| Avoid | Why | v2.0 Alternative |
|-------|-----|-----------------|
| `pyyaml` | Already conditionally imported in skill_runner.py with a working fallback; adding it to requirements.txt would change behavior for existing test infrastructure in an untested way | Leave optional import as-is |
| `PyGithub` | Adds a dependency for 3–4 GET calls; raw `requests` handles GitHub REST API cleanly | `requests` (already installed) |
| Graphify MCP | No confirmed Python package; planning doc uses a non-existent `--source` flag; blocked by Cisco Umbrella proxy anyway | GitHub REST API via `requests` |
| `durable-rules`, `pyknow`, `business-rules` | Rule-engine libraries designed for 1000+ rules with complex firing logic; massively over-engineered for 20–30 static rules | `json.load()` + list comprehension filter |
| `aiohttp` | Async HTTP for GitHub API calls would require refactoring ingest_github.py's event loop handling | `requests` in executor (same pattern as apify_client in ingest_wechat.py) |

---

## Integration Notes

### ingest_github.py must follow the existing async pattern

```python
# Correct pattern — mirrors ingest_wechat.py
async def ingest_github_repo(repo_url: str) -> None:
    rag = await get_rag()           # same get_rag() from ingest_wechat.py (or shared)
    content = await fetch_repo_content(repo_url)  # uses requests in executor
    await rag.ainsert(content)
    # entity buffering — same ENTITY_BUFFER_DIR pattern
```

`requests` is synchronous. Wrap in `asyncio.get_event_loop().run_in_executor(None, lambda: ...)` —
the same pattern used in `ingest_wechat.py` line 118 for the Apify client call.

### entity_registry.json write pattern

Use atomic rename — same as canonical_map.json:

```python
import tempfile, os
def write_entity_registry(registry: dict, path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as f:
        json.dump(registry, f, indent=2)
        tmp = f.name
    os.rename(tmp, path)
```

### /architect skill — rules_engine.json must be at a config-derived path

Do not hardcode the path. Add to config.py:

```python
RULES_ENGINE_FILE = Path(__file__).parent / "rules_engine.json"
```

Project-root relative is appropriate here (unlike runtime data, which goes under `~/.hermes/`). Rules
are source artifacts, not user data.

---

## Version Compatibility

No version changes required. The multi-turn Gemini conversation history pattern has been available in
`google-genai` since v0.3.x (when the `Contents` API was introduced). Current requirements.txt uses
unpinned `google-genai`, which will get the latest version — all relevant features are stable.

| Feature | API | Available Since |
|---------|-----|-----------------|
| Multi-turn via contents list | `google-genai` | v0.3.x (stable, well-documented) |
| GitHub REST API `/readme` endpoint | GitHub REST v3 | Stable, no versioning changes expected |
| `os.rename()` atomic file write | Python stdlib | Always |

---

## Sources

- `C:/Users/huxxha/Desktop/OmniGraph-Vault/requirements.txt` — confirmed no pyyaml, no PyGithub; all listed packages available (HIGH confidence — source file)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/skill_runner.py` — confirmed single-turn only, optional yaml import, `call_gemini()` signature (HIGH confidence — source file)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/ingest_wechat.py` — confirmed no `--source` flag, `sys.argv[1]` only; run_in_executor pattern for sync calls in async context (HIGH confidence — source file)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/config.py` — confirmed FIRECRAWL_API_KEY already loaded; ENTITY_BUFFER_DIR, CANONICAL_MAP_FILE patterns to replicate (HIGH confidence — source file)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/PROJECT.md` — v2.0 feature list, Graphify MCP mention, "no framework migrations" constraint (HIGH confidence — planning doc)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/STATE.md` line 88 — "Graphify MCP availability and schema — validate before Phase 4" (HIGH confidence — confirms it's an open question, not implemented)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/MILESTONE-2-SIMPLE-GUIDE.md` Task 2.1-03 — speculative `--source graphify` command that doesn't match actual ingest_wechat.py interface (HIGH confidence — confirms planning doc was aspirational, not implemented)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/specs/OMNIGRAPH_VISION_Statement.md` lines 76–84 — GitHub API approach explicitly specified (`ingest_github.py`, public API, README + docs + labeled issues) (HIGH confidence — spec doc)
- `C:/Users/huxxha/Desktop/OmniGraph-Vault/specs/OMNIGRAPH_PRODUCT_BRIEF.md` lines 147–203 — Graphify positioned as "工具结构理解" data source alongside LightRAG, entity_registry.json as GitHub URL anchor (MEDIUM confidence — design vision, implementation approach not yet validated)
- GitHub REST API public documentation — `/readme`, `/contents`, `/issues` endpoints; 60/hr unauthenticated, 5000/hr with token (MEDIUM confidence — knowledge cutoff Aug 2025; API has been stable for years, no breaking changes expected)
- `google-genai` multi-turn conversation history — Contents API with alternating user/model roles (MEDIUM confidence — training data; pattern is stable and well-established)

---

*Stack research for: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP*
*Researched: 2026-04-23*
*Prior stack (v1.1): unchanged — LightRAG, Cognee, Gemini, Apify, Playwright CDP, requests, google-genai*
