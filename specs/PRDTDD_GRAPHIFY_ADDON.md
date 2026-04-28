# PRD/TDD: Graphify Code Graph Addon for OmniGraph-Vault

> **Audience:** Claude Code — use this document as the single source of truth to implement the addon.
> **Repository:** [OmniGraph-Vault](https://github.com/sztimhdd/OmniGraph-Vault)
> **Status:** Design complete — ready for implementation.

---

## 1. Product Overview

### 1.1 What This Is

A **zero-code MCP addon** that adds code-structure query capability to OmniGraph-Vault's existing domain-knowledge graph. It answers the question:

> *"I know WHY OpenClaw designed streaming tool output this way (from WeChat articles in the domain graph). Now show me HOW it's implemented — the exact function, its callers, and its dependencies."*

### 1.2 Target User

**Not a human developer.** The consumer is **Claude Code** — an AI coding agent tasked with implementing features in a Rust fork of OpenClaw. Claude Code uses this addon's MCP tools autonomously during coding sessions.

### 1.3 Competitive Positioning

| Competitor | What It Offers | OmniGraph + Graphify Advantage |
|------------|---------------|-------------------------------|
| **Context7** | API docs lookup | Adds design-intent from WeChat articles + causal reasoning in graph edges |
| **Tavily** | Web search | WeChat closed ecosystem — content only available through our manual ingestion |
| **Sourcegraph Cody** | Code search + jump-to-def | Adds cross-project semantic matching + article-to-code bridging |

**Unique selling point:** When Claude Code asks "how does OpenClaw handle streaming tool output?", it receives: (a) design rationale from domain articles, (b) exact function signatures from code graph, (c) call-chain traversal, and (d) cross-project comparisons (OpenClaw vs Hermes). No competitor combines these four layers.

### 1.4 Core Metric

**Claude Code output quality improvement on OpenClaw/Hermes implementation tasks**, measured qualitatively: code architectural consistency, fewer hallucinations about API behavior, correct integration patterns.

---

## 2. Architecture

### 2.1 Dual-Graph / Dual-Tool Design

```
                      Claude Code
                     /            \
        search_knowledge          lookup_code
        (LightRAG MCP)            (Graphify MCP)
              │                        │
     ┌────────┴────────┐      ┌────────┴────────┐
     │  Domain Graph    │      │   Code Graph     │
     │  (LightRAG)      │      │  (Graphify JSON)  │
     │                  │      │                   │
     │ • Design intent  │      │ • Function nodes  │
     │ • Usage guides   │      │ • Class hierarchy │
     │ • Best practices │      │ • Call chains     │
     │ • Pitfalls       │      │ • Module deps     │
     │ • Concept links  │      │ • Import graphs   │
     └──────────────────┘      └───────────────────┘
              │                        │
              └────────┬───────────────┘
                       │
              ┌────────┴────────┐
              │  Bridge Nodes    │
              │  (future Phase)  │
              │  pre-link domain │
              │  concepts → code │
              │  entities        │
              └─────────────────┘
```

### 2.2 Why Two Graphs, Not One

| Decision | Reasoning |
|----------|-----------|
| **Separate stores** | Domain entities (opinions, entities, arguments) and code entities (functions, classes, modules) use fundamentally different grammars. Merging creates semantic noise. |
| **Separate MCP tools** | Claude Code selects the right tool for the right task. Mixed-tool queries are composed by Claude Code, not by our pipeline. |
| **Physical separation** | LightRAG stores entities internally; Graphify outputs graph.json. No shared database, no coupling. |

### 2.3 Claude Code's Autonomous Routing Logic

```
User: "Implement streaming tool output in my Rust fork, like OpenClaw"

Claude Code reasoning:
  1. "I need design rationale" → search_knowledge("streaming tool output 设计")
     → Returns: WeChat article explaining AsyncGenerator choice, perf tradeoffs
  2. "I have the design. Now find implementation" → lookup_code.get_node("stream_query")
     → Returns: function signature, file path, docstring
  3. "What else calls this?" → lookup_code.get_neighbors("stream_query")
     → Returns: callers (agent_loop, router) + callees (token_stream, response_builder)
  4. Combine → implement in Rust with Tokio
```

---

## 3. Graphify MCP Tool Interface

### 3.1 Exposed Tools

Graphify's `python -m graphify.serve graphify-out/graph.json` exposes exactly four MCP tools. No wrapper code needed.

| Tool | Signature | Description | Claude Code Use Case |
|------|-----------|-------------|---------------------|
| `query_graph` | `(query: str) → list[Node]` | Natural-language graph search | "find all auth-related functions" |
| `get_node` | `(node_id: str) → Node` | Fetch single node by ID | "show me stream_query's signature" |
| `get_neighbors` | `(node_id: str) → list[Node]` | Incoming + outgoing edges | "who calls stream_query, what does it call" |
| `shortest_path` | `(source: str, target: str) → list[Node]` | BFS between two nodes | "how does auth connect to the agent loop" |

### 3.2 Node Schema (from Graphify output)

```json
{
  "id": "openclaw::router::Router::route",
  "type": "function",           // function | class | module | variable
  "name": "route",
  "file": "src/router.ts",
  "line": 145,
  "signature": "async route(request: Request): Promise<Response>",
  "docstring": "Routes incoming tool requests to registered handlers.",
  "language": "typescript",
  "parent": "openclaw::router::Router"  // containing class/module
}
```

### 3.3 Edge Schema

```json
{
  "source": "openclaw::agent_loop::execute",
  "target": "openclaw::router::Router::route",
  "type": "calls"              // calls | inherits | imports | contains
}
```

---

## 4. Data Design

### 4.1 Storage Layout

```
~/.hermes/omonigraph-vault/
├── graphify/                    # NEW: Graphify working directory
│   ├── repos/                   # Cloned T1 repositories
│   │   ├── openclaw/           # git clone cache
│   │   └── claude-code/        # git clone cache
│   └── graph.json               # Built code graph (Graphify output)
│
├── lightrag_storage/            # Existing: Domain graph (unchanged)
├── enrichment/                  # Existing: Zhihu enrichment (unchanged)
└── images/                      # Existing: Article images (unchanged)
```

### 4.2 T1 Repository Scope

| Repository | URL | Reason | Priority |
|-----------|-----|--------|:--------:|
| openclaw | `https://github.com/openclaw/openclaw` | Core framework — Rust fork's primary reference | P0 |
| claude-code | `https://github.com/anthropics/claude-code` | Claude Code internals — understanding the consumer | P0 |

**Expansion rule:** Add a repository only when Claude Code manually searches its source ≥3 times in one session. Never pre-emptively add T3 repos (AutoGen, LangGraph) — marginal utility approaches zero.

### 4.3 Update Strategy

```
cron: 0 3 * * 0  (every Sunday 3am)
command: graphify refresh && python -m graphify.build
```

- **Frequency reasoning:** OpenClaw/Hermes ship 5-10 commits/week. Weekly snapshots capture feature-level changes without excessive compute.
- **Atomic swap:** Build to `graph.json.tmp` → validate → `mv graph.json.tmp graph.json`. Graphify MCP server auto-reloads on file change (or restart via cron).

---

## 5. Implementation Plan

### 5.1 Zero-Code Philosophy

Graphify MCP is integrated declaratively — no Python wrapper, no adapter code, no custom MCP server. The only "implementation" is configuration and cron.

### 5.2 Phase 1: Initial T1 Build (Task List)

| # | Task | Command | Verify |
|---|------|---------|--------|
| 1 | Install Graphify | `pip install graphify` | `graphify --version` |
| 2 | Clone openclaw | `graphify clone https://github.com/openclaw/openclaw` | `ls repos/openclaw/` non-empty |
| 3 | Clone claude-code | `graphify clone https://github.com/anthropics/claude-code` | `ls repos/claude-code/` non-empty |
| 4 | Build graph | `graphify build` | `graph.json` exists, > 1MB |
| 5 | Validate Node Count | `python -c "import json; g=json.load(open('graph.json')); print(len(g['nodes']))"` | > 500 nodes |
| 6 | Start MCP server | `python -m graphify.serve graph.json &` | `curl localhost:PORT/health` or process alive |
| 7 | Register in .mcp.json | See §6.1 | `claude mcp list` shows `lookup_code` |
| 8 | Smoke test query | `claude mcp call lookup_code get_node '{"node_id":"Router"}'` | Returns node data |

### 5.3 Phase 2: Weekly Cron (Task List)

| # | Task | Verify |
|---|------|--------|
| 1 | Create `scripts/graphify-refresh.sh` | `bash -n` passes |
| 2 | Register cron job | `crontab -l` shows entry |
| 3 | Simulate refresh | Run script manually, verify graph.json timestamp updates |

### 5.4 Phase 3: Bridge Nodes (Future — Not In Scope Now)

When domain graph entities reference specific code symbols (e.g., a WeChat article discusses `OpenClaw.Router`), pre-compute cross-graph links:

```
Domain Graph                          Code Graph
─────────────                         ──────────
Entity: "Router"  ────bridge────→    Node: openclaw::router::Router
  metadata: {                           type: class
    code_ref: "openclaw::router::Router"
  }
```

Bridge nodes eliminate Claude Code's guesswork when routing between tools. Implementation deferred until T1 build is validated with Demo scenarios.

---

## 6. Integration Details

### 6.1 MCP Registration

Add to Claude Code's `.mcp.json`:

```json
{
  "mcpServers": {
    "lookup_code": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "graphify.serve", "~/.hermes/omonigraph-vault/graphify/graph.json"]
    }
  }
}
```

`search_knowledge` is already registered via the existing OmniGraph-Vault MCP server (not changed by this addon).

### 6.2 Cron Job

```bash
# scripts/graphify-refresh.sh
#!/bin/bash
set -euo pipefail

GRAPHIFY_DIR="$HOME/.hermes/omonigraph-vault/graphify"
cd "$GRAPHIFY_DIR"

# Refresh git clones
for repo in repos/*/; do
    (cd "$repo" && git pull --ff-only) || echo "WARN: $repo pull failed, using stale"
done

# Rebuild graph (atomic)
graphify build --output graph.json.tmp
python3 -c "
import json
with open('graph.json.tmp') as f:
    g = json.load(f)
assert len(g['nodes']) > 100, 'Graph too small, refusing to swap'
"
mv graph.json.tmp graph.json

# Restart MCP server (if managed by systemd)
systemctl --user restart graphify-mcp || true
```

### 6.3 Cron Registration

```bash
# Add to crontab
(crontab -l 2>/dev/null; echo "0 3 * * 0 $HOME/OmniGraph-Vault/scripts/graphify-refresh.sh") | crontab -
```

---

## 7. Test & Acceptance Strategy

### 7.1 Unit Tests

No Python code to test. Graphify is integrated declaratively.

**What IS tested:**
- `graphify-refresh.sh` syntax (`bash -n`)
- Graph JSON schema validation after build
- MCP tool invocation round-trip

### 7.2 Demo Scenario 1: Streaming Tool Output

> **Task:** Implement OpenClaw-style streaming tool output in the Rust fork.

```yaml
setup:
  - search_knowledge already populated with WeChat articles about OpenClaw architecture
  - lookup_code registered and pointing to fresh graph.json

expected_claude_code_behavior:
  1. "I need context" → calls search_knowledge("streaming tool output design")
  2. "I have the why. Now the how" → calls lookup_code.get_node("stream_query")
  3. "Who interacts with this?" → calls lookup_code.get_neighbors("stream_query")
  4. Combines results → produces Rust/Tokio implementation consistent with OpenClaw's design

acceptance:
  - Code structure mirrors OpenClaw (AsyncGenerator → Tokio Stream)
  - No hallucinated API signatures (all from get_node output)
  - Integration points correct (from get_neighbors call-chain)
```

### 7.3 Demo Scenario 2: Self-Evolution Integration

> **Task:** Add Hermes-style self-evolution to the Rust fork.

```yaml
expected_claude_code_behavior:
  1. calls search_knowledge("hermes self evolution genetic optimizer prompt")
     → Returns: article about optimizer selection, parameter tuning, pitfalls
  2. calls lookup_code.query_graph("evolution optimizer")
     → Returns: genetic_optimizer, prompt_evaluator modules
  3. calls lookup_code.shortest_path("genetic_optimizer", "agent_loop")
     → Returns: exact files and interfaces to modify for integration
  4. Implements with knowledge of: which libraries, how to integrate, what to avoid

acceptance:
  - Uses libraries recommended in articles (not arbitrarily chosen)
  - Integration follows shortest_path output (modifies correct files)
  - Avoids documented pitfalls (e.g., "don't use population_size > 50" from article)
```

### 7.4 Acceptance Gate

```
[ ] lookup_code MCP tool responds to all 4 Graphify tools
[ ] search_knowledge + lookup_code used together in at least one Claude Code session
[ ] Claude Code output on Demo 1 is architecturally consistent with OpenClaw
[ ] Claude Code output on Demo 2 uses article-recommended libraries and avoids documented pitfalls
[ ] Weekly cron successfully rebuilds graph.json
[ ] No Python wrapper code exists (zero-code integration preserved)
```

---

## 8. Design Decisions Log

| ID | Decision | Rationale |
|----|----------|-----------|
| D-G01 | Zero wrapper code | Graphify MCP tools cover all query patterns. Wrapper code adds maintenance burden with no functional gain. |
| D-G02 | Separate storage from domain graph | Code and domain entities use different grammars; merging creates noise and complicates Claude Code's tool selection. |
| D-G03 | T1 only (openclaw + claude-code) | Marginal utility of T2/T3 repos is near zero. Claude Code rarely queries them. |
| D-G04 | Weekly cron, not per-commit | 5-10 commits/week is sufficient for feature tracking. Per-commit rebuilds waste compute. |
| D-G05 | Atomic graph swap (tmp → rename) | Prevents MCP server from reading half-written graph.json. |
| D-G06 | Bridge nodes deferred to Phase 3 | Claude Code handles routing autonomously in Phase 1-2. Bridge nodes are an optimization, not a requirement. |
| D-G07 | No Rust fork in graph | The fork is the product being built, not a knowledge source. Graph covers reference implementations only. |
| D-G08 | Claude Code as user persona | All tool design and acceptance criteria are framed around Claude Code's autonomous usage patterns, not human query behavior. |

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Graphify MCP tool signature changes | Low | MCP registration breaks | Pin Graphify version in requirements.txt |
| Weekly cron fails silently | Medium | Stale code graph | Add minimum node count assertion in refresh script |
| Claude Code doesn't autonomously use both tools | Medium | Loses cross-graph benefit | Demo scenario testing proves or disproves; add bridge nodes if needed |
| openclaw/claude-code repos rename or move | Low | `git pull` breaks | Cron script tolerates pull failure, keeps stale graph |
| Graph JSON too large for MCP context | Low | Tool calls time out | Monitor graph.json size; add node filtering if > 10MB |

---

## 10. Appendix: Graphify Quick Reference

```bash
# Install
pip install graphify

# Clone + build
graphify clone https://github.com/openclaw/openclaw
graphify clone https://github.com/anthropics/claude-code
graphify build                          # → graph.json

# Serve as MCP
python -m graphify.serve graph.json     # exposes 4 tools via stdio

# Update
graphify refresh                        # git pull all clones
graphify build                          # rebuild graph
```

**MCP tools exposed:** `query_graph`, `get_node`, `get_neighbors`, `shortest_path`

---

*Document version: 1.0 · 2026-04-27*
