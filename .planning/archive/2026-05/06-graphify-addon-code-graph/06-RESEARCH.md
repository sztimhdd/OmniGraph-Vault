# Phase 6: graphify-addon-code-graph — Research

**Researched:** 2026-04-28
**Domain:** Hermes/OpenClaw skill installation + Graphify CLI integration + LightRAG wrapper skill
**Confidence:** HIGH (Graphify internals fetched directly from `safishamsi/graphify@v5` on GitHub; existing repo skills read verbatim)

---

## Summary

Graphify is a real, actively maintained tool. The PyPI package is **`graphifyy`** (double-y), not `graphify` — this is the single most important correction the planner must absorb. The CLI exists and genuinely supports `install --platform hermes`, `install --platform claw`, `clone <url>`, `update <path>`, and `hook install`. The PRD v3.0 is substantially correct about form; it is wrong about a handful of specific commands and flags that the plan must replace with real equivalents.

Three command-level facts the PRD gets wrong and the planner must fix:

1. **`pip install graphify` installs the wrong package.** The official installer is `pip install graphifyy` (or `uv tool install graphifyy`, or `pipx install graphifyy`). The PRD Appendix §10 is incorrect.
2. **`graphify build` does not exist.** The graph is built by an AI agent driving the installed skill — the installed `SKILL.md` runs a seven-step pipeline that includes a semantic extraction pass that requires an LLM. There is no agent-free, pure-CLI `graphify build` that produces a full `graph.json` from scratch. The only LLM-free build path is `graphify update <path>`, which is AST-only and requires an existing `graph.json` to merge into.
3. **`graphify refresh` does not exist.** The closest CLI-only equivalents are `graphify update <path>` (AST re-extract, no LLM) and `graphify hook install` (post-commit/post-checkout git hooks that auto-rebuild). There is no `--output graph.json.tmp` flag — the output path is fixed at `graphify-out/graph.json`.

Most of the Phase plan still works. These differences change the *shape* of Wave 3 (cron), not the rest. Demo 1 and Demo 2 remain valid acceptance scenarios but cannot be fully automated with the existing `skill_runner.py` harness — they need manual Hermes/OpenClaw session verification because the semantic graph build is LLM-driven and non-deterministic.

**Primary recommendation:** Adopt Graphify's two-step install pattern verbatim (`graphify install --platform hermes` + `graphify hermes install`), point the per-project `graphify clone + /graphify` flow at `~/.hermes/omonigraph-vault/graphify/` as a working directory, defer the weekly LLM rebuild to a human-triggered Hermes session (with an AST-only cron as best-effort filler), and model `omnigraph_search` exactly on the shape of `omnigraph_query` (SKILL.md + `scripts/query.sh` + `references/api-surface.md`).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

From PRD §8 Design Decisions Log (copied verbatim from CONTEXT.md):

- **D-G01** Skill form only, no MCP wrapper
- **D-G02** `graphify_skill` zero-code — Graphify native `install --platform hermes/claw`
- **D-G03** Separate storage from domain graph
- **D-G04** T1 repos ONLY (`openclaw`, `claude-code`) — do NOT add T2/T3
- **D-G05** Weekly cron, not per-commit
- **D-G06** Atomic graph swap (tmp → rename)
- **D-G07** Bridge nodes deferred to later phase
- **D-G08** Rust fork NOT in graph
- **D-G09** `omnigraph_search` reuses existing LightRAG path — no new deployment
- **D-S10** OpenClaw is a first-class platform alongside Hermes

Storage path: `~/.hermes/omonigraph-vault/graphify/` (preserve `omonigraph` typo — canonical per `config.py`).

### Claude's Discretion

The CONTEXT.md does not call out a dedicated "discretion" section. Pragmatically, Claude has discretion over:

- The exact shape of the `omnigraph_search` SKILL.md frontmatter and triggers (must match the project's established pattern documented below).
- The `scripts/query.sh` + `references/api-surface.md` file layout (should mirror `omnigraph_query`).
- The cron script internals, including how to handle the PRD's `graphify build --output graph.json.tmp` command that does not exist (see §6 below).
- The Phase 3 cron scope: "weekly rebuild on remote WSL2 Hermes PC only, no local Windows cron."
- Wave ordering and how many waves to split the four phases across — the PRD's numbered phases are logical, not wave-mapped.

### Deferred Ideas (OUT OF SCOPE)

- **Phase 5.5 — Bridge nodes** (domain-graph → code-graph pre-linking). Deferred until Phase 1-2 acceptance passes.
- **T2/T3 repo coverage** (Hermes, LightRAG, anything beyond openclaw + claude-code).
- **Rust fork in the graph** (D-G08 — fork is the product, not a knowledge source).
- **Per-commit rebuild** (D-G05 — weekly is enough).
- **MCP wrapper** (D-G01 — skill form only).
- **Gemini-free-tier embedding quota fix** (separate infra track, not this phase).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

Mapped from PRD §7.4 acceptance gate → research findings that enable each requirement.

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-01 | `graphify_skill` installed and functional on Hermes | §1: `graphify install --platform hermes` and `graphify hermes install` both work and are distinct. Installer writes to `~/.hermes/skills/graphify/SKILL.md`. Confirmed by reading `_PLATFORM_CONFIG["hermes"]` in `graphify/__main__.py`. |
| REQ-02 | `graphify_skill` installed and functional on OpenClaw | §1: `graphify install --platform claw` + `graphify claw install`. Skill goes to `~/.openclaw/skills/graphify/SKILL.md`. Both platforms use the same `skill-claw.md` source file. |
| REQ-03 | `omnigraph_search` SKILL.md exists and skill is discoverable | §2: Template = `omnigraph_query` SKILL.md. Pattern = `---` YAML frontmatter (`name`, `description`, `compatibility`, `metadata.openclaw.*`) + body with Quick Reference table + Decision Tree + Error Handling + Related Skills. Deployment = `scp skills/omnigraph_search/ → remote ~/OmniGraph-Vault/skills/`. |
| REQ-04 | `omnigraph_search` returns LightRAG query results | §3: Exact LightRAG pattern lifted from `kg_synthesize.py` lines 47–63 + `query_lightrag.py` lines 48–63. No new `get_rag()` helper exists — each script re-initializes. `omnigraph_search/query.py` should mirror `query_lightrag.py` verbatim (simpler than `kg_synthesize.py` because no Cognee needed). |
| REQ-05 | Agent autonomously uses both skills in Demo 1 (streaming output) | §7: Cannot be fully automated in `skill_runner.py`. Requires a live Hermes session on the remote PC. Researcher recommends a checkpoint: "orchestrator drives a Hermes session and attaches the transcript as evidence." |
| REQ-06 | Agent autonomously uses both skills in Demo 2 (self-evolution) | §7: Same as REQ-05. Demo 2 additionally depends on the graph being built and the domain graph containing Hermes self-evolution articles — check with `list_entities.py` before running the demo. |
| REQ-07 | Code output architecturally consistent with OpenClaw/Hermes | §7: Qualitative, not automatable. Orchestrator judges from the Hermes session transcript. |
| REQ-08 | Weekly cron successfully rebuilds `graph.json` | §6: PRD §6.2 script is not runnable as-written. See §6 below for the concrete, tested-shape replacement. |

</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

Extracted from `./CLAUDE.md` — planner must honor these:

| Directive | Source section | Impact on planning |
|-----------|---------------|--------------------|
| Skill = directory, never single file | "OpenClaw / Hermes Skill Writing Standards" → Skill Directory Structure | `omnigraph_search/` must have SKILL.md + `scripts/` + `references/`; never a flat file. |
| SKILL.md frontmatter: `name`, `description` required; `triggers`, `metadata.openclaw.requires.*` impactful | same | Match the exact frontmatter shape used by `omnigraph_query` (see §2). |
| `references/` = read; `scripts/` = execute. Never mix. | same | Put `api-surface.md` in `references/`; put `query.sh` in `scripts/`. |
| Progressive disclosure — keep SKILL.md lean, heavy material in `references/` | same | `omnigraph_search/SKILL.md` should not embed LightRAG internals; point to `references/api-surface.md`. |
| Env vars, not hardcoded paths | Skill Writing Standards → point 5 | Reference `GEMINI_API_KEY`, `OMNIGRAPH_ROOT` by name. Do not hardcode `~/.hermes/omonigraph-vault/`. |
| `~/.hermes/omonigraph-vault/` typo is canonical — do not "fix" | Common Commands + Remote Hermes Deployment + Lessons Learned | Graphify working dir under this path preserves the typo. |
| Testing = `skill_runner.py skills/<skill> --test-file tests/skills/test_<skill>.json` | "Skill simulator" section | Add `tests/skills/test_omnigraph_search.json` mirroring the structure of `test_omnigraph_query.json`. |
| Remote = WSL2 Linux (venv/bin, not venv/Scripts) | Remote Hermes Deployment | Cron runs on remote. `scripts/graphify-refresh.sh` targets Linux paths. |
| No Windows cron | (implicit — local dev is Windows, cron is Linux-only) | Phase 3 cron scope = remote only. |
| Never commit credentials/hostnames | Remote Hermes Deployment | Cron script uses `$HOME` paths, no hardcoded user names. |
| `simplicity first` + `surgical changes` | HIGHEST PRIORITY PRINCIPLES | `omnigraph_search` = SKILL.md + one script + one reference. Not a framework. |
| Touch only what you must | HIGHEST PRIORITY PRINCIPLES | Do not modify `kg_synthesize.py` or `query_lightrag.py` when adding `omnigraph_search/query.py`. |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `graphifyy` (double-y!) | **0.5.3** (verified 2026-04-28 via PyPI JSON API) | Code-graph builder + platform skill installer. Only the Graphify build pipeline produces the `graph.json` the installed skill queries. | Project uses Python 3.10–3.13 (works with the project's 3.11+ venv). 85 PyPI releases, actively maintained (last push `2026-04-28T10:22:40Z`). 37,020 GitHub stars. Explicit first-class support for both Hermes and OpenClaw in `_PLATFORM_CONFIG`. |
| `lightrag-hku` | (already installed) | Domain-graph query backend for `omnigraph_search`. Reused verbatim — no version change. | D-G09 pins this. |
| `watchdog` | (already installed, `requirements.txt`) | Only relevant if we wire `graphify watch`. Not needed for this phase. | Graphify's `watch.py` optional; cron + git hook cover the same need. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `networkx` | pulled by graphifyy | Transitively; `graph.json` is a NetworkX node-link dump | Only if skill needs to read `graph.json` directly (it shouldn't — `graphify query`/`path`/`explain` subcommands handle this). |
| `tree-sitter` + language grammars | pulled by graphifyy | AST extraction for 25 languages | Automatic; nothing to configure for Python/TS/Go. |
| `faster-whisper`, `yt-dlp` | optional extras (`graphifyy[video]`) | Only needed if we want to ingest video/audio — we do NOT for this phase | Skip. Document as "not installed." |
| `graphifyy[mcp]` | optional extras | Only needed if we want to run `python -m graphify.serve graph.json` — we do NOT (D-G01 forbids MCP) | Skip. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| `graphifyy` | tree-sitter + custom indexer (hand-roll) | Would need to replicate AST extraction, community clustering (Leiden), semantic extraction dispatch. Weeks of work. | REJECTED — D-G02 requires zero-code and Graphify delivers it. |
| `graphifyy` | Sourcegraph Cody / code-search-only | Cody is SaaS, gives call-chain but no "why" rationale nodes; violates privacy constraint | REJECTED — doesn't produce the `rationale` attribute that differentiates graphify |
| `graphify build` (PRD CLI) | `graphify update <path>` (AST-only, no LLM) | `update` cannot seed a graph from scratch; it can only merge AST re-extraction into an existing `graph.json` (shrink-guard protected) | Both needed: initial seed via agent-driven `/graphify` in Hermes; weekly refresh via `graphify update` from cron. |

**Installation (verified):**

```bash
# Preferred (per Graphify README)
uv tool install graphifyy && graphify install --platform hermes
# or
pipx install graphifyy && graphify install --platform hermes
# or (project's existing venv):
~/OmniGraph-Vault/venv/bin/pip install graphifyy
~/OmniGraph-Vault/venv/bin/graphify install --platform hermes
~/OmniGraph-Vault/venv/bin/graphify install --platform claw
```

**Version verification:** `pip index versions graphifyy` → returns `0.5.3` latest, `0.5.2`, `0.5.1`, `0.5.0`, ... (85 total). Confirmed HIGH.

---

## Architecture Patterns

### Recommended Project Structure (phase output)

```
skills/
└── omnigraph_search/                   # NEW — the only new skill
    ├── SKILL.md                        # follows omnigraph_query frontmatter pattern
    ├── scripts/
    │   └── query.sh                    # thin bash wrapper (OMNIGRAPH_ROOT, venv activation, arg validation)
    ├── references/
    │   └── api-surface.md              # doc — env vars, exit codes, modes (like omnigraph_query/references/api-surface.md)
    └── evals/
        └── evals.json                  # optional; evals.json format per omnigraph_query

omnigraph_search/                       # NEW — top-level python module (mirror of query_lightrag.py)
└── query.py                            # stripped-down kg_synthesize.py: LightRAG init + aquery(hybrid), no Cognee

scripts/                                # already exists
└── graphify-refresh.sh                 # NEW — weekly cron script (remote only)

# Graphify install artifacts (not committed — user home):
# ~/.hermes/skills/graphify/SKILL.md
# ~/.openclaw/skills/graphify/SKILL.md
# ~/.hermes/omonigraph-vault/graphify/repos/openclaw/openclaw/   (git clone)
# ~/.hermes/omonigraph-vault/graphify/repos/anthropics/claude-code/
# ~/.hermes/omonigraph-vault/graphify/graphify-out/graph.json    (LLM-seeded via /graphify . in Hermes session)
```

### Pattern 1: Project SKILL.md frontmatter (HIGH confidence)

Copied from `skills/omnigraph_query/SKILL.md` (verbatim verified). Matches what all four existing skills use:

```yaml
---
name: omnigraph_search
description: |
  Use this skill when the user wants to query the OmniGraph-Vault knowledge graph for
  design rationale, best practices, usage patterns, or pitfalls from ingested WeChat/
  Zhihu content. Trigger phrases include: "why was X designed this way", "what's the
  best practice for Y", "how does OpenClaw handle Z", "what are the pitfalls for A".

  This skill runs scripts/query.sh which invokes omnigraph_search/query.py — a
  LightRAG hybrid-mode wrapper over the domain knowledge graph. No synthesis step
  (that's omnigraph_query's job); returns the raw graph retrieval with entity
  attribution.

  Do NOT use this skill when: the user asks about code structure, function signatures,
  call chains, or module dependencies — that's the graphify skill. Do NOT use when the
  user wants to ingest new content — use omnigraph_ingest / enrich_article. Do NOT use
  when the user wants a long-form synthesis report with images — use omnigraph_query.
compatibility: |
  Requires: GEMINI_API_KEY in ~/.hermes/.env, Python venv at $OMNIGRAPH_ROOT/venv,
  populated LightRAG index at ~/.hermes/omonigraph-vault/lightrag_storage/.
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
---
```

Notes for the planner:
- The `description` is multi-line with "use when" / "do NOT use when" pairs — this is the established pattern for disambiguating against sibling skills. The Graphify skill and `omnigraph_search` must explicitly reference each other in their "Do NOT use when" sections to prevent agent confusion.
- `metadata.openclaw.requires.bins` and `.config` are used by OpenClaw's skill gateway — keep them.
- No `triggers` array field — existing skills embed triggers in the `description`. Follow that convention for consistency.

### Pattern 2: `scripts/query.sh` wrapper (HIGH confidence)

Mirror `skills/omnigraph_query/scripts/query.sh` verbatim with two substitutions: script name + Python entry point. The pattern is already battle-tested (6 steps: resolve project root → source `~/.hermes/.env` → check repo exists → validate args → check `GEMINI_API_KEY` → activate venv → `cd $OMNIGRAPH_ROOT` → run Python). Key invariants:

- `OMNIGRAPH_ROOT` env var with fallback `"$HOME/OmniGraph-Vault"`
- Venv detection tries both `venv/Scripts/activate` (Windows) and `venv/bin/activate` (Linux) — critical because Windows dev vs Linux remote
- Always `cd "$OMNIGRAPH_ROOT"` before invoking Python so imports resolve
- Exit codes: 0 = success, 1 = actionable error (missing env var, missing venv, bad args)
- Stderr carries the `⚠️ ...` messages; stdout carries the LLM response

### Pattern 3: LightRAG call site (HIGH confidence — verified in `query_lightrag.py` L43-63 and `kg_synthesize.py` L47-63)

There is NO `get_rag()` helper in the repo. Each script re-initializes. The minimal pattern for `omnigraph_search/query.py` is a trimmed copy of `query_lightrag.py`:

```python
# Source: query_lightrag.py L1-63 (verified verbatim in repo)
# Strip the Cognee integration — omnigraph_search is query-only, no memory log.

import os
import sys
import asyncio
import numpy as np

from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs
from config import RAG_WORKING_DIR, load_env  # config.py auto-loads ~/.hermes/.env at import

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"  # Force standard Gemini API
load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await gemini_model_complete(
        prompt, system_prompt=system_prompt, history_messages=history_messages,
        api_key=GEMINI_API_KEY, model_name="gemini-2.5-flash-lite", **kwargs,
    )

@wrap_embedding_func_with_attrs(
    embedding_dim=768, send_dimensions=True, max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001", embedding_dim=768,
    )

async def search(query_text: str, mode: str = "hybrid"):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name="gemini-2.5-flash-lite",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return await rag.aquery(query_text, param=QueryParam(mode=mode))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m omnigraph_search.query '<query>' [mode]", file=sys.stderr)
        sys.exit(1)
    q = sys.argv[1]
    m = sys.argv[2] if len(sys.argv) > 2 else "hybrid"
    print(asyncio.run(search(q, mode=m)))
```

Notes for the planner:
- Entry point shape is identical to `query_lightrag.py` (which already works). Differences: no Cognee memory log call (simpler), exposes `mode` arg for optional override.
- `RAG_WORKING_DIR` comes from `config.py` which reads `~/.hermes/omonigraph-vault/lightrag_storage/`. No new path.
- Default mode is `hybrid` (matches PRD §3.2 code sample).

### Anti-Patterns to Avoid

- **Do not write a new `get_rag()` helper.** Neither `kg_synthesize.py` nor `query_lightrag.py` uses one — each re-initializes LightRAG per invocation. Adding a shared helper would be a refactor outside this phase's scope (surgical changes principle).
- **Do not add Cognee to `omnigraph_search`.** PRD D-G09 says "reuses existing LightRAG path." Cognee memory is an `omnigraph_query`/`kg_synthesize` concern.
- **Do not bundle the installed Graphify SKILL.md into the repo.** `graphify install` writes it to `~/.hermes/skills/graphify/SKILL.md` at run time; committing a copy creates version drift. If the plan needs to reference Graphify's skill behavior, cite the SKILL.md source path in the installed package instead.
- **Do not use Hermes absolute paths in the project-level `omnigraph_search/SKILL.md`.** Use env vars (`$OMNIGRAPH_ROOT`, `~/.hermes/.env`).
- **Do not create a separate `graphify_skill/` directory in `skills/`.** `graphify` is installed by the `graphifyy` package into `~/.hermes/skills/graphify/` — there is nothing for us to author. Phase 1 has no deliverable in `skills/`; its deliverables are provisioning steps (pip install + two CLI invocations) and a verification step (`hermes skills list | grep graphify`).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Code-graph construction (AST extraction, call-chain, module deps) | Custom tree-sitter wrapper + networkx indexer | `graphifyy` (D-G02) | Graphify handles 25 languages, Leiden community detection, `rationale` attribute extraction, HTML viz, confidence tagging. Weeks of work for equivalence. |
| Skill installation on Hermes / OpenClaw | Manual `cp` + `~/.hermes/skills/*` layout | `graphify install --platform hermes`, `graphify install --platform claw` | Graphify's installer also writes `.graphify_version` stamps that drive the stale-skill warning system (see `_refresh_all_version_stamps` in `graphify/__main__.py` L188-190). Rolling our own loses this. |
| AGENTS.md / CLAUDE.md registration | Append text manually | `graphify hermes install` / `graphify claw install` | These use a `_AGENTS_MD_MARKER` that makes uninstall surgical. Manual appending would make uninstall fragile. |
| Atomic JSON swap with pre-check | Custom tmp-file-rename + size check | `to_json()` in `graphify.export` (has built-in **shrink guard**: refuses to overwrite if the new graph is smaller than the existing one — see `graphify/watch.py` L102-104 and v0.5.0 release notes) | The shrink guard covers the "graph too small, refusing to swap" logic PRD §6.2 wrote manually. Don't duplicate it. |
| LightRAG init + Gemini wiring | Custom setup code | Copy `query_lightrag.py` lines 1-63 | That file is already proven; re-use verbatim. |
| Skill test harness | pytest fixtures that simulate Hermes | `skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` | Already in repo, used by 3 existing skills. Exit code 0 = all pass. |

**Key insight:** Almost every "brick" in Phase 6 already exists. The work is orchestration (installing, verifying, wiring), not construction. If a task feels like it needs 100 lines of Python, you've picked the wrong abstraction.

---

## Runtime State Inventory

Phase 6 does NOT rename anything pre-existing. But it does provision new filesystem state at install time on two machines. Documenting what will live where:

| Category | Items (new or existing) | Action Required |
|----------|-------------------------|------------------|
| Stored data | (a) `~/.hermes/omonigraph-vault/graphify/repos/openclaw/openclaw/` — git clone of openclaw on remote WSL2 only. (b) `~/.hermes/omonigraph-vault/graphify/repos/anthropics/claude-code/` — same. (c) `~/.hermes/omonigraph-vault/graphify/graphify-out/graph.json` — generated graph. *Default `graphify clone` destination is `~/.graphify/repos/<owner>/<repo>` — we override via `--out` to put it under the project's canonical data dir.* | Plan Phase 1 must invoke `graphify clone <url> --out ~/.hermes/omonigraph-vault/graphify/repos/<owner>/<repo>` explicitly (the default `~/.graphify/repos/...` would violate D-G03's "separate storage" intent of colocating with other vault data). |
| Live service config | (a) Hermes gateway SQLite (`~/.hermes/state.db`) — registers the skill at load time. (b) OpenClaw gateway — same pattern. Neither is committed to git. | Plan must include a "restart Hermes / `claw gateway restart`" step or equivalent after `graphify install`. Per graphify README: `graphify install` writes the skill file; Hermes picks it up on next load. No explicit register call needed. |
| OS-registered state | Remote WSL2 crontab — the weekly refresh job will live in `$(crontab -l)`. | Phase 3 plan must include `crontab` installation on the remote PC only. Do NOT attempt on Windows dev machine — `crontab` does not exist there. Plan should include a `crontab -l | grep graphify-refresh` verification step. |
| Secrets/env vars | `GEMINI_API_KEY` already in `~/.hermes/.env` — no change. `OMNIGRAPH_ROOT` already set by Hermes gateway. No new secrets. | None — verified by reading `config.py` + `skills/omnigraph_query/scripts/query.sh`. |
| Build artifacts | (a) `~/.hermes/skills/graphify/SKILL.md` + `~/.hermes/skills/graphify/.graphify_version` — written by `graphify install`. (b) `~/.openclaw/skills/graphify/SKILL.md` + version stamp — same. (c) `AGENTS.md` at repo root may be modified by `graphify hermes install` / `graphify claw install` (appends a `## graphify` section via `_AGENTS_MD_MARKER`). | Plan must check whether repo already has an `AGENTS.md` (currently none in the tree — verified via file listing). If it does: `graphify hermes install` appends; if not: it creates. Either way, the change must be committed. Plan Phase 1 should include a `git status` check + commit step after `graphify *install`. |

**Canonical question answered:** After Phase 6 executes on the remote PC, the following new runtime state exists beyond the git repo: (1) two git clones under `~/.hermes/omonigraph-vault/graphify/repos/`, (2) `graph.json` + `graph.html` + `GRAPH_REPORT.md` under `~/.hermes/omonigraph-vault/graphify/graphify-out/`, (3) Graphify skill files in `~/.hermes/skills/graphify/` and `~/.openclaw/skills/graphify/`, (4) one weekly crontab entry, (5) appended `## graphify` section in `AGENTS.md` (in git), (6) new skill dir in `skills/omnigraph_search/` (in git), (7) new `omnigraph_search/query.py` module (in git), (8) new `scripts/graphify-refresh.sh` (in git), (9) new `tests/skills/test_omnigraph_search.json` (in git).

---

## Environment Availability

Remote WSL2 Hermes PC is the execution target for Phase 1/3. Local Windows is the dev target for skill authoring (Phase 2). Probing results:

| Dependency | Required By | Available (local Windows) | Available (remote WSL2, expected) | Version | Fallback |
|------------|-------------|--------------------------|-----------------------------------|---------|----------|
| Python 3.10+ (graphifyy requires) | Phase 1 install | ✓ (3.13 per env output) | ✓ (assumed 3.11 per project convention) | graphifyy requires `<3.14,>=3.10` | — |
| `graphifyy` PyPI package | Phase 1 | ✗ (not installed) | ✗ (must install) | 0.5.3 | — |
| `git` CLI | Phase 1 `graphify clone` + Phase 3 cron | ✓ (git bash) | ✓ | — | — |
| `crontab` | Phase 3 cron registration | ✗ (Windows) | ✓ (Linux) | — | **Windows scope-out**: Phase 3 is remote-only. No fallback needed for local. |
| Hermes gateway CLI (`hermes skills list`) | Phase 1 verification | ✗ (Hermes runs remote) | ✓ | — | Can be verified via SSH. Alternatively inspect `~/.hermes/skills/graphify/SKILL.md` file existence. |
| OpenClaw gateway CLI (`claw skills list`) | Phase 1 verification | ✗ | Likely ✓ (deployed alongside Hermes) | — | Falls back to file-existence check: `test -f ~/.openclaw/skills/graphify/SKILL.md`. **Needs confirmation** that OpenClaw is actually installed on the remote PC (not mentioned in `hermes_ssh.md`). |
| `skill_runner.py` local harness | Phase 2 testing | ✓ (at repo root) | ✓ | — | — |
| SSH to remote | All phases that verify remotely | ✓ (keys in ~/.ssh) | N/A | — | — |
| LightRAG storage populated | REQ-04, Demo 2 | ✓ (local) / ✓ (remote, live — 713 nodes / 820 edges per `STATE.md`) | ✓ | — | If remote graph is empty, demo falls back to qualitative "skill returned something" check. |

**Missing dependencies with no fallback:**
- `graphifyy` on remote (must install in Phase 1 step 1)
- `crontab` — by design; Phase 3 is Linux-only

**Missing dependencies with fallback:**
- `claw skills list` — if OpenClaw is not installed on the remote PC, Phase 1 REQ-02 cannot be verified through the CLI. **ACTION for planner:** Include an early check in Phase 1 — `ssh remote "command -v claw"` — and branch: if OpenClaw present, proceed; if absent, treat D-S10 as aspirational and scope Phase 1 to Hermes-only. Document this in the plan.

---

## Common Pitfalls

### Pitfall 1: `pip install graphify` installs the wrong package

**What goes wrong:** Following the PRD Appendix §10 literally installs a stale, unrelated package.
**Why it happens:** Three different packages named `graphify`/`graph-ify`/`graphify-cli` are squatted on PyPI; the actual project is `graphifyy` (double-y). The Graphify README §Install explicitly warns about this.
**How to avoid:** Every installation step in the plan must use `graphifyy`, never `graphify`. Add a post-install check: `python -c "import graphify; print(graphify.__version__)"` — should print `0.5.3`+.
**Warning signs:** `pip install graphify` succeeds but `graphify --help` does not produce the expected command list (no `install --platform`, no `clone`, no `update`), OR `pip install graphify` fails with "No matching distribution found."

### Pitfall 2: PRD's `graphify build`, `graphify refresh`, `graphify build --output` do not exist

**What goes wrong:** The PRD §5.2 step 3 (`graphify build`), §5.3 Appendix (`graphify build`), §6.2 (`graphify build --output graph.json.tmp`), and Appendix §10 (`graphify refresh`) all reference commands that are not in the Graphify CLI.
**Why it happens:** PRD was written against the conceptual model of a pure CLI build tool. The actual tool is an AI-agent-driven skill: the `/graphify` command inside Hermes/OpenClaw runs a 7-step pipeline that *includes* the semantic extraction LLM pass. There is no agent-free pure-CLI build.
**How to avoid:**
  - **Initial graph seed:** invoke `/graphify .` *inside a Hermes or OpenClaw session* on the remote PC, in the directory that contains the cloned repos. Document this as a one-shot step in the runbook.
  - **Weekly rebuild:** use `graphify update <path>` (AST-only, LLM-free) for code-only updates that cron can handle unsupervised. For doc/image changes, `graphify update` writes a `needs_update` flag file; a human must run `/graphify --update` inside Hermes to trigger the semantic re-extraction.
  - **Atomic swap:** already handled by Graphify's shrink guard in `to_json()` (refuses to overwrite if new graph < existing). No custom `tmp → rename` needed.
**Warning signs:** Plan references `graphify build` anywhere. A script fails with "`error: unknown command 'build'`."

### Pitfall 3: OpenClaw may not be deployed on the remote PC

**What goes wrong:** Phase 1 REQ-02 assumes both Hermes and OpenClaw are installed. `hermes_ssh.md` mentions only Hermes. If OpenClaw isn't there, `graphify install --platform claw` runs but `claw skills list` produces "command not found."
**Why it happens:** The PRD treats OpenClaw as first-class (D-S10) but project ops state only documents Hermes.
**How to avoid:** Phase 1 task 1 must probe both: `ssh remote "command -v hermes && command -v claw"` and either (a) proceed with both if both exist, or (b) scope Phase 1 to Hermes-only and flag D-S10 as partially deferred (graphify skill installed but OpenClaw binary absent).
**Warning signs:** `claw: command not found` or `~/.openclaw/` does not exist on remote.

### Pitfall 4: Skill file location conflict — `graphify install --platform hermes` vs `graphify hermes install`

**What goes wrong:** These are **two different commands** that do **different things**. `install --platform hermes` copies the skill file to `~/.hermes/skills/graphify/SKILL.md`. `hermes install` appends a `## graphify` section to the current working directory's `AGENTS.md`.
**Why it happens:** The PRD §5.2 mentions only `graphify install --platform hermes`. The README shows both are needed for complete "always-on" behavior.
**How to avoid:** Phase 1 must invoke BOTH: first `graphify install --platform hermes` (skill file), then `cd ~/OmniGraph-Vault && graphify hermes install` (AGENTS.md entry). Same for claw. Commit the AGENTS.md change.
**Warning signs:** Hermes session doesn't auto-route to graphify when user asks a codebase question, even though `hermes skills list` shows graphify as enabled. Fix: run `graphify hermes install` in the repo root.

### Pitfall 5: Graphify's default clone path is `~/.graphify/`, not the project vault dir

**What goes wrong:** `graphify clone <url>` clones to `~/.graphify/repos/<owner>/<repo>` by default (see `_clone_repo` in `graphify/__main__.py` L922-972). This violates D-G03's implicit intent that all vault-adjacent data lives under `~/.hermes/omonigraph-vault/`.
**Why it happens:** Graphify has its own data-root convention independent of Hermes.
**How to avoid:** Use `graphify clone <url> --out ~/.hermes/omonigraph-vault/graphify/repos/<owner>/<repo>` explicitly. The `--out` flag is real (see L946-947).
**Warning signs:** `~/.graphify/` directory exists and is growing; vault dir's `graphify/repos/` is empty. Plan missed the `--out` flag.

### Pitfall 6: LightRAG initialization racing

**What goes wrong:** If `omnigraph_search/query.py` is called in rapid succession, LightRAG storage init may race (`kv_store_*.json` read-modify-write).
**Why it happens:** LightRAG's storage layer is not designed for concurrent processes. The existing `kg_synthesize.py` sidesteps this with `await asyncio.sleep(2)` after init (L61).
**How to avoid:** Copy the `await asyncio.sleep(2)` pattern if the plan anticipates multi-user scenarios. For Phase 6 scope (agent triggers one call at a time), this is not a blocker — but document the constraint so the plan doesn't promise concurrent queries.
**Warning signs:** Mysterious JSON decode errors or "file in use" errors during demos.

### Pitfall 7: `omnigraph_search` vs `omnigraph_query` disambiguation

**What goes wrong:** Both skills query LightRAG. If descriptions overlap, Hermes may pick the wrong one.
**Why it happens:** `omnigraph_query` does hybrid-mode query + Cognee recall + custom synthesis prompt + saves to `synthesis_output.md`. `omnigraph_search` (per PRD §3.2) does hybrid-mode query + return results with attribution, no synthesis. The user-facing outputs are different shapes but the internal backend is the same.
**How to avoid:** `omnigraph_search` description must explicitly say "Do NOT use when the user wants a long-form synthesis with inline images — use `omnigraph_query` instead." And `omnigraph_query`'s description must gain a "Do NOT use when the user wants raw entity-attributed retrieval with source citations — use `omnigraph_search`" clause. The planner should add the cross-reference to BOTH sides.
**Warning signs:** Test case "why was X designed this way" routes to `omnigraph_query` instead of `omnigraph_search`, or vice versa.

### Pitfall 8: `graphify update` shrinks the graph on failure

**What goes wrong:** `_rebuild_code` in `graphify/watch.py` includes a shrink guard (L102-104) that refuses to write a new `graph.json` if it's smaller than the existing one. Cron job running `graphify update` may log "`[graphify watch] Rebuild failed: ...`" and keep a stale graph — but if the existing graph gets corrupted, `update` won't heal it.
**Why it happens:** Intentional — preserves the LLM-generated semantic layer across code-only refreshes.
**How to avoid:** Cron script (Phase 3) should log `graphify update` output to a file on remote, and include a "graph too old" alert if the `graphify-out/graph.json` mtime is > 2 weeks. PRD §6.2's "minimum node count" assertion is one approach; a simpler approach is mtime check.
**Warning signs:** Old graph being queried weeks after cron claimed success — shrink guard silently kept the old one.

---

## Code Examples

Verified patterns from official sources / in-repo files.

### Example 1 — Install Graphify on Hermes + OpenClaw (Phase 1)

```bash
# Source: Graphify README § Platform support + safishamsi/graphify/__main__.py L1053-1146
# Run on the remote WSL2 PC.

# Step 1: install the package into the project venv
cd ~/OmniGraph-Vault && source venv/bin/activate
pip install graphifyy                                # 0.5.3 as of 2026-04-28

# Step 2a: write the Hermes skill file (~/.hermes/skills/graphify/SKILL.md)
graphify install --platform hermes

# Step 2b: register graphify in the repo's AGENTS.md (appends ## graphify section)
cd ~/OmniGraph-Vault
graphify hermes install

# Step 3a: write the OpenClaw skill file (~/.openclaw/skills/graphify/SKILL.md)
graphify install --platform claw

# Step 3b: register graphify in the repo's AGENTS.md for OpenClaw too
graphify claw install   # idempotent if marker already present

# Verify
ls -la ~/.hermes/skills/graphify/ ~/.openclaw/skills/graphify/
hermes skills list 2>/dev/null | grep graphify        # expect: graphify | enabled
command -v claw && claw skills list | grep graphify   # skip if claw absent

# Commit the AGENTS.md change
cd ~/OmniGraph-Vault
git add AGENTS.md
git commit -m "chore(graphify): register graphify skill for hermes + openclaw"
```

### Example 2 — Clone T1 repos into vault-canonical paths (Phase 1)

```bash
# Source: graphify/__main__.py L922-972 (_clone_repo) + README § Usage clone
# Run on remote. Explicit --out overrides default ~/.graphify/repos/.

GRAPHIFY_ROOT="$HOME/.hermes/omonigraph-vault/graphify"
mkdir -p "$GRAPHIFY_ROOT/repos"

graphify clone https://github.com/openclaw/openclaw \
  --out "$GRAPHIFY_ROOT/repos/openclaw/openclaw"

graphify clone https://github.com/anthropics/claude-code \
  --out "$GRAPHIFY_ROOT/repos/anthropics/claude-code"

# Verify
ls "$GRAPHIFY_ROOT/repos/openclaw/openclaw/.git" \
   "$GRAPHIFY_ROOT/repos/anthropics/claude-code/.git"
```

### Example 3 — Seed the initial graph (Phase 1, one-shot manual step)

```text
# Run INSIDE a Hermes or OpenClaw session on the remote PC.
# This invokes the /graphify skill the previous steps installed.

cd ~/.hermes/omonigraph-vault/graphify
/graphify repos           # dispatches the 7-step pipeline from skill-claw.md

# Expected outputs (per skill-claw.md Step 4):
#   graphify-out/GRAPH_REPORT.md
#   graphify-out/graph.json
#   graphify-out/graph.html
#   graphify-out/cache/
#   ("Graph: N nodes, M edges, K communities")

# This step IS LLM-dependent and may consume significant Gemini tokens
# (semantic extraction pass over non-code files). Budget accordingly.
```

Note: because the semantic pass is inside the agent, we cannot shell-script this from cron. It's the one-time bootstrap; subsequent code changes are handled by the AST-only `graphify update` in cron.

### Example 4 — Weekly cron refresh script (Phase 3)

Replacement for the broken PRD §6.2 script. Uses commands that actually exist.

```bash
#!/bin/bash
# scripts/graphify-refresh.sh
# Source: graphify/__main__.py L1412-1424 (update command) + watch.py L36-135 (_rebuild_code with shrink guard)
# Runs weekly on the remote WSL2 PC via crontab. Local Windows dev should not invoke this.

set -euo pipefail

GRAPHIFY_ROOT="$HOME/.hermes/omonigraph-vault/graphify"
LOG_FILE="$HOME/.hermes/omonigraph-vault/graphify-refresh.log"
GRAPH_JSON="$GRAPHIFY_ROOT/graphify-out/graph.json"

cd "$GRAPHIFY_ROOT"

# 1. Pull latest code for each T1 repo; keep stale on pull failure (per risk register).
for repo_dir in repos/*/*/; do
    if [[ -d "$repo_dir/.git" ]]; then
        (cd "$repo_dir" && git pull --ff-only) 2>&1 | tee -a "$LOG_FILE" \
            || echo "WARN: $repo_dir git pull failed — keeping stale checkout" >> "$LOG_FILE"
    fi
done

# 2. AST-only rebuild (no LLM, cron-safe).
# graphify update refuses to shrink the graph (watch.py L102-104); uses semantic
# nodes from existing graph.json. Preserves the LLM-extracted rationale layer.
source "$HOME/OmniGraph-Vault/venv/bin/activate"
graphify update . 2>&1 | tee -a "$LOG_FILE"

# 3. Soft-fail min-node assertion (preserves existing graph on bad output).
if [[ -f "$GRAPH_JSON" ]]; then
    NODES=$(python -c "import json; print(len(json.load(open('$GRAPH_JSON'))['nodes']))")
    if (( NODES < 100 )); then
        echo "WARN: graph too small ($NODES nodes) — investigate" >> "$LOG_FILE"
    fi
fi

# 4. Notify flag for non-code changes (see watch.py L138-150 check_update).
#    A pending flag means doc/paper/image files changed and need /graphify --update
#    inside a Hermes session to re-run semantic extraction.
graphify check-update . 2>&1 | tee -a "$LOG_FILE"

echo "=== $(date -Is) refresh complete ===" >> "$LOG_FILE"
```

Crontab entry (remote only):

```
0 3 * * 0 $HOME/OmniGraph-Vault/scripts/graphify-refresh.sh
```

### Example 5 — `omnigraph_search/query.py` entry point (Phase 2)

```python
# Source: trimmed from query_lightrag.py L1-70 (verbatim, with Cognee stripped)
"""LightRAG hybrid-mode query wrapper for the omnigraph_search skill."""

import asyncio
import os
import sys
from pathlib import Path

import numpy as np

from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs

from config import RAG_WORKING_DIR, load_env

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
load_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


async def _llm_model_func(prompt, system_prompt=None, history_messages=(), **kwargs):
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=list(history_messages),
        api_key=GEMINI_API_KEY,
        model_name="gemini-2.5-flash-lite",
        **kwargs,
    )


@wrap_embedding_func_with_attrs(
    embedding_dim=768,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def _embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(
        texts,
        api_key=GEMINI_API_KEY,
        model="gemini-embedding-001",
        embedding_dim=768,
    )


async def search(query_text: str, mode: str = "hybrid") -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=_llm_model_func,
        embedding_func=_embedding_func,
        llm_model_name="gemini-2.5-flash-lite",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return await rag.aquery(query_text, param=QueryParam(mode=mode))


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m omnigraph_search.query '<question>' [mode]",
            file=sys.stderr,
        )
        sys.exit(1)
    question = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "hybrid"
    try:
        print(asyncio.run(search(question, mode=mode)))
    except Exception as exc:   # noqa: BLE001 - surface to caller
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Example 6 — Skill test JSON (mirror of `test_omnigraph_query.json`)

```json
[
  {
    "description": "golden path: design-intent question triggers omnigraph_search",
    "input": "why was OpenClaw streaming tool output designed this way?",
    "expect_contains": ["omnigraph_search", "query.sh"],
    "expect_not_contains": ["graphify", "get_node"]
  },
  {
    "description": "code-structure question routes to graphify, NOT omnigraph_search",
    "input": "what is the signature of stream_query and who calls it?",
    "expect_contains": ["graphify"],
    "expect_not_contains": ["omnigraph_search"]
  },
  {
    "description": "synthesis request routes to omnigraph_query, NOT omnigraph_search",
    "input": "write me a detailed markdown report with inline images about LightRAG",
    "expect_contains": ["omnigraph_query"],
    "expect_not_contains": ["omnigraph_search"]
  },
  {
    "description": "guard clause: missing GEMINI_API_KEY surfaces actionable error",
    "input": "search for agent routing patterns — but GEMINI_API_KEY is not set",
    "expect_contains": ["GEMINI_API_KEY", ".env"]
  }
]
```

---

## State of the Art

| Old approach (PRD v3.0) | Current approach (Graphify v0.5.3) | When changed | Impact |
|--------------------------|------------------------------------|--------------|--------|
| `pip install graphify` | `pip install graphifyy` (double-y) | README § Install note | Plan instructions must say `graphifyy`. |
| `graphify build` after `clone` | No such command. Initial seed = `/graphify <dir>` inside Hermes session (LLM-driven semantic pass). Weekly = `graphify update <dir>` (AST-only). | CLI design has been skill-oriented from v0.1 onward | Phase 1 seed is a one-shot manual step; Phase 3 cron is AST-only. |
| `graphify refresh && graphify build` weekly | `graphify update <path>` + optional `graphify hook install` for git-triggered | CLI never had `refresh`/`build` | Cron script uses `update`, not `refresh`. |
| `graphify build --output graph.json.tmp` | Shrink guard in `to_json()` (v0.5.0+) protects `graph.json` automatically. Output path is always `graphify-out/graph.json`. | v0.5.0 release | No custom tmp-rename needed. PRD §6.2 simplification possible. |
| Standalone MCP server: `python -m graphify.serve` | Still exists (`graphify [path] --mcp`) but conflicts with D-G01 (skill form only). Skip. | — | Ignored by D-G01. |

**Deprecated/outdated (PRD → real-world):**
- PRD's weekly rebuild strategy needs refinement: code-only changes go through cron; doc/paper/image changes need a human-in-the-loop Hermes session (`check-update` flag + notification).
- PRD treats `graphify install --platform hermes` as sufficient. The real install pattern is TWO commands per platform (install skill + register in AGENTS.md).

---

## Validation Architecture

*(The config at `.planning/config.json` does not set `workflow.nyquist_validation`. Per instructions, treat as enabled. Include this section.)*

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `skill_runner.py` (in-repo, Gemini-backed) + pytest (available but not used for skills) |
| Config file | none — `skill_runner.py` reads `tests/skills/test_<skill>.json` by convention |
| Quick run command | `python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` |
| Full suite command | `python skill_runner.py skills/ --test-all` |
| Graphify install smoke-test | `graphify --version && graphify install --platform hermes --help` (no side effects) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-01 | `graphify` skill installed on Hermes | smoke | `ssh remote "test -f ~/.hermes/skills/graphify/SKILL.md && hermes skills list \| grep -q graphify"` | ❌ Wave 0 |
| REQ-02 | `graphify` skill installed on OpenClaw | smoke | `ssh remote "test -f ~/.openclaw/skills/graphify/SKILL.md"` — `claw skills list` only if `claw` CLI exists | ❌ Wave 0 |
| REQ-03 | `omnigraph_search` SKILL.md discoverable | unit (structure) | `python skill_runner.py skills/omnigraph_search --validate` | ❌ Wave 0 — no skill yet |
| REQ-04 | `omnigraph_search` returns LightRAG results | integration | `python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` + live call: `OMNIGRAPH_ROOT=. venv/Scripts/python -m omnigraph_search.query "test"` | ❌ Wave 0 — test file + module don't exist yet |
| REQ-05 | Demo 1 (streaming output) — agent uses both skills | **manual-only** | Hermes session transcript on remote; orchestrator attaches as evidence | N/A — no automation possible without mock Hermes |
| REQ-06 | Demo 2 (self-evolution) — agent uses both skills | **manual-only** | Same as REQ-05 | N/A |
| REQ-07 | Code output architecturally consistent | **manual-only** (qualitative) | Human review of Hermes session output | N/A |
| REQ-08 | Weekly cron rebuilds graph atomically | smoke + integration | `bash -n scripts/graphify-refresh.sh` (syntax) + `ssh remote "crontab -l \| grep graphify-refresh"` (registered) + `ssh remote "bash ~/OmniGraph-Vault/scripts/graphify-refresh.sh && stat -c %Y ~/.hermes/omonigraph-vault/graphify/graphify-out/graph.json"` (mtime updates) | ❌ Wave 0 — script doesn't exist |

### Sampling Rate

- **Per task commit:** `bash -n scripts/graphify-refresh.sh` (shell syntax); `python skill_runner.py skills/omnigraph_search --validate` (structure)
- **Per wave merge:** `python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` + remote SSH smoke tests for installed skills
- **Phase gate:** Manual Demo 1 + Demo 2 transcript captured from live Hermes session; orchestrator approves qualitatively before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/skills/test_omnigraph_search.json` — covers REQ-03, REQ-04, and disambiguation vs `omnigraph_query`/`graphify`
- [ ] `skills/omnigraph_search/SKILL.md` + `scripts/query.sh` + `references/api-surface.md`
- [ ] `omnigraph_search/__init__.py` + `omnigraph_search/query.py` (new top-level module)
- [ ] `scripts/graphify-refresh.sh` (with `bash -n` validation)
- [ ] No framework install needed — `skill_runner.py` already in repo; `graphifyy` installs into the existing venv

---

## Open Questions

1. **Is OpenClaw actually installed on the remote Hermes PC?**
   - What we know: `hermes_ssh.md` describes a Hermes-only deployment. PRD D-S10 treats OpenClaw as first-class.
   - What's unclear: Whether `claw` CLI is present on `ohca.ddns.net`. Whether `~/.openclaw/skills/` is a live directory.
   - Recommendation: Phase 1 task 1 probes `ssh remote "command -v claw"`. If absent, plan continues with Hermes-only and documents D-S10 as partially deferred (skill file written to `~/.openclaw/` location but not live-verified on OpenClaw gateway).

2. **Does Hermes gateway auto-reload `~/.hermes/skills/` after a file write, or does it need a restart?**
   - What we know: Project skills (`omnigraph_query` etc.) are deployed via `scp` to `~/OmniGraph-Vault/skills/` and picked up on next gateway load. Graphify writes to `~/.hermes/skills/graphify/` — a different directory.
   - What's unclear: Whether Hermes watches both dirs with the same semantics, or whether `~/.hermes/skills/` requires `gateway restart`.
   - Recommendation: Plan includes a defensive `ssh remote "systemctl --user restart hermes || pkill -HUP hermes-gateway || true"` step after `graphify install --platform hermes`. If unnecessary, it's a no-op; if necessary, it's the fix.

3. **What fraction of `openclaw/openclaw` + `anthropics/claude-code` content does the Gemini free-tier budget accommodate during the initial LLM-driven graph seed?**
   - What we know: Phase 4 hit the Gemini embedding 100 RPM limit during bulk ingest. Graphify's semantic pass may hit similar limits.
   - What's unclear: How many tokens `/graphify .` consumes for these two repos. Whether the `.graphifyignore` can trim enough to stay under quota.
   - Recommendation: Before running the seed, invoke `graphify check-update .` and inspect the `detect` output (file count + word count). If `total_words > 500,000`, plan an initial seed with `--no-viz` and a `.graphifyignore` that excludes test dirs, docs, and translations. This is an execution-time concern the plan should flag, not block on.

4. **How is REQ-05 / REQ-06 "agent autonomously uses both skills" empirically confirmed without a Hermes-scripting API?**
   - What we know: No evidence of a Hermes CLI that can be driven by a test script to send messages and parse tool-use events.
   - What's unclear: Whether Hermes supports replay / transcript export.
   - Recommendation: Treat Demo 1/2 as human-in-the-loop checkpoints. Orchestrator runs the Hermes session, saves transcript to `docs/testing/06-demo1-transcript.md` and `06-demo2-transcript.md`, asserts both `graphify` and `omnigraph_search` appear in the tool-use log. Planner adds these as manual verification tasks in Wave 5.

---

## Sources

### Primary (HIGH confidence)

- **Graphify GitHub repo** — `safishamsi/graphify@v5` (default branch), 37,020 stars, last push 2026-04-28
  - `README.md` — fetched via GitHub REST API
  - `graphify/__main__.py` — CLI entry point (lines 70-1514 read directly)
  - `graphify/watch.py` — `_rebuild_code` / `check_update` / `watch` internals
  - `graphify/skill-claw.md` — skill pipeline that Hermes/OpenClaw run (7 steps including LLM semantic pass)
  - URL: https://github.com/safishamsi/graphify
- **PyPI package metadata** — `graphifyy 0.5.3` (85 releases), verified via `curl https://pypi.org/pypi/graphifyy/json` and `pip index versions graphifyy`
- **In-repo source of truth:**
  - `skills/omnigraph_query/SKILL.md` (frontmatter template)
  - `skills/omnigraph_query/scripts/query.sh` (bash wrapper pattern)
  - `skills/omnigraph_query/references/api-surface.md` (reference doc pattern)
  - `query_lightrag.py` L1-90 (LightRAG init pattern — copy into `omnigraph_search/query.py`)
  - `kg_synthesize.py` L39-117 (confirms the same pattern + Cognee layering we intentionally skip)
  - `config.py` L1-48 (`RAG_WORKING_DIR`, `BASE_DIR`, `load_env`)
  - `skill_runner.py` + `tests/skills/test_omnigraph_query.json` (test harness)
  - `specs/PRDTDD_GRAPHIFY_ADDON.md` (v3.0, authoritative)
  - `.planning/phases/06-graphify-addon-code-graph/06-CONTEXT.md` (phase intent)

### Secondary (MEDIUM confidence)

- Remote deployment state inferred from `~/.claude/projects/.../memory/hermes_ssh.md` + `STATE.md` Phase 4 exit report (live-validated). OpenClaw presence on remote NOT confirmed.

### Tertiary (LOW confidence)

- None — all claims verifiable against the two HIGH-confidence sources above.

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — `graphifyy 0.5.3` verified via PyPI JSON + pip + GitHub release tags; project's existing LightRAG stack is already live.
- Architecture (skill layout, LightRAG init pattern): **HIGH** — existing in-repo skills read verbatim; patterns verified across 4 skills.
- Pitfalls: **HIGH for 1-5** (directly contradict PRD text by reading Graphify source); **MEDIUM for 6-8** (extrapolations from source code behavior, not live-tested).
- Environment availability: **HIGH for local**, **MEDIUM for remote** (Hermes confirmed; OpenClaw presence not probed in this research — deferred to Phase 1 task 1).
- Demo automation feasibility: **HIGH** — no evidence of a scriptable Hermes API; manual-only is a firm conclusion.

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 for Graphify (version 0.5.3 is fresh; any later breaking change would require re-reading `__main__.py`). Valid indefinitely for in-repo patterns (don't change unless the project itself refactors).
