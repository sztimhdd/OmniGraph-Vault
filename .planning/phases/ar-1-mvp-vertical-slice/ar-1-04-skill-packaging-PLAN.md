---
phase: ar-1-mvp-vertical-slice
plan: 04
type: execute
wave: 4
depends_on:
  - ar-1-03
files_modified:
  - skills/omnigraph_research/SKILL.md
  - skills/omnigraph_research/scripts/research.sh
  - skills/omnigraph_research/README.md
  - tests/skills/test_omnigraph_research.json
autonomous: true
requirements:
  - SKILL-01
  - SKILL-02
  - SKILL-03
  - SKILL-04
  - SKILL-05

must_haves:
  truths:
    - "skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json exits 0"
    - "SKILL.md frontmatter conforms to OpenClaw / Hermes skill schema (name, description, triggers, requires)"
    - "scripts/research.sh is a thin shell wrapper invoking `python -m omnigraph.research \"$1\"` — ~50 lines max"
    - "Internal stages (web_baseline, retriever, reasoner, verifier, synthesizer) are NOT exposed as separate skills (design § Skill exposure — hard rule)"
    - "README.md documents human install + cost/quality/latency table for ar-1 (cost: ~$0; quality: stub; latency: <2s) vs ar-4 final state"
  artifacts:
    - path: "skills/omnigraph_research/SKILL.md"
      provides: "Skill definition discoverable by Hermes/OpenClaw skill loader"
      contains: "name=omnigraph_research, description, triggers list, metadata.openclaw.requires"
    - path: "skills/omnigraph_research/scripts/research.sh"
      provides: "Skill-invoked wrapper that activates venv and runs `python -m omnigraph.research`"
      contains: "shebang, venv activation, $1 query forwarding, exit-code propagation"
    - path: "skills/omnigraph_research/README.md"
      provides: "Human-facing install + cost/quality/latency reference"
    - path: "tests/skills/test_omnigraph_research.json"
      provides: "skill_runner harness covering ≥ 1 trigger phrase + non-empty markdown assertion"
  key_links:
    - from: "skills/omnigraph_research/scripts/research.sh"
      to: "lib/research/__main__.py"
      via: "python -m omnigraph.research"
    - from: "tests/skills/test_omnigraph_research.json"
      to: "skill_runner.py"
      via: "skill_runner.py skills/omnigraph_research --test-file ..."
---

<objective>
Wrap the runnable lib + CLI (delivered by ar-1-01..03) as an OpenClaw / Hermes skill so the agent can invoke research via natural-language triggers.

Purpose:

- SKILL-01..05: Single user-facing skill `omnigraph_research`. Triggers like "research X", "deep dive on Y", "what do I know about Z synthesized" route through Hermes skill loader → scripts/research.sh → `python -m omnigraph.research` → orchestrator.
- Hard constraint from design § Skill exposure: internal stages NEVER exposed as separate skills. Only ONE skill ships from this milestone, regardless of how many internal stages exist.

Output:

- `skills/omnigraph_research/SKILL.md` — frontmatter + body following Hermes skill writing standards (CLAUDE.md § OpenClaw / Hermes Skill Writing Standards)
- `skills/omnigraph_research/scripts/research.sh` — ~50-line wrapper
- `skills/omnigraph_research/README.md` — human install guide + cost/quality/latency table
- `tests/skills/test_omnigraph_research.json` — skill_runner test harness

Phase deliverable: `venv/Scripts/python.exe skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json` exits 0.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-03-cli-image-server-PLAN.md
@CLAUDE.md
@docs/design/agentic_rag_internal_api.md
@skill_runner.py
@skills/omnigraph_ingest/SKILL.md
@skills/omnigraph_query/SKILL.md
@tests/skills/test_omnigraph_ingest.json
@tests/skills/test_omnigraph_query.json

<interfaces>
Existing sibling skills `skills/omnigraph_ingest/` and `skills/omnigraph_query/` are the canonical templates. Read both before writing the new skill — match their:

- SKILL.md frontmatter style (name, description, triggers, metadata.openclaw.requires.bins/config)
- Body structure (Decision tree → Trigger phrases → Output format → Error guard clauses)
- README.md tone (human install steps, no agent-facing instructions)
- scripts/*.sh shape (shebang, venv activation, env preservation, $1 forwarding, exit-code propagation)

Existing test JSON files at `tests/skills/test_omnigraph_ingest.json` and `tests/skills/test_omnigraph_query.json` show the skill_runner.py expected schema — match it exactly for `tests/skills/test_omnigraph_research.json`.

After ar-1-03, `python -m omnigraph.research "<query>"` is fully functional. This plan ONLY wraps that command — no new logic.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write skills/omnigraph_research/SKILL.md</name>
  <read_first>
    - skills/omnigraph_ingest/SKILL.md (template — match frontmatter style)
    - skills/omnigraph_query/SKILL.md (template — match body structure)
    - CLAUDE.md § "OpenClaw / Hermes Skill Writing Standards" (frontmatter required fields, decision tree pattern, guard clauses)
    - docs/design/agentic_rag_internal_api.md § "Skill exposure" (hard rule: only ONE skill, NEVER expose internal stages)
  </read_first>
  <files>skills/omnigraph_research/SKILL.md</files>
  <action>
    Create `skills/omnigraph_research/SKILL.md` with:

    Frontmatter:
    ```yaml
    ---
    name: omnigraph_research
    description: >-
      Deep multi-stage research over the OmniGraph knowledge graph.
      Combines KG retrieval, web search, vision analysis, and verification
      to produce a long-form markdown answer with embedded images.
    triggers:
      - "research"
      - "deep dive"
      - "synthesize a report on"
      - "what do I know about (synthesized)"
      - "深度解析"
      - "深度研究"
    metadata:
      openclaw:
        os: ["darwin", "linux", "win32"]
        requires:
          bins: ["python"]
          config: ["GEMINI_API_KEY"]
          optional_config: ["TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY"]
    ---
    ```

    Body sections (match `skills/omnigraph_query/SKILL.md` shape):

    1. **When to invoke** — decision tree:
       - User asks "research X" / "deep dive on X" / "深度解析 X" → invoke this skill
       - User asks "search KB for X" / "what's in my KB about X" → use `omnigraph_query` instead (KG-only, no web/synthesis)
       - User asks "add this article" → use `omnigraph_ingest` instead

    2. **Trigger phrases** — list of natural-language patterns; prefer this skill over `omnigraph_query` when query implies long-form answer with citations.

    3. **Invocation** — `bash scripts/research.sh "<query>"` (the only callable form)

    4. **Output format** — markdown to stdout. Always contains a top-level title section, may contain `> ℹ️ ... skipped` degradation notes (especially in ar-1 stub mode). Image URLs use `http://localhost:8765/<hash>/<N>.jpg`.

    5. **Error guard clauses**:
       - If `GEMINI_API_KEY` unset → skill fails fast with clear message
       - If query is empty → exit 1 with "Query argument required"
       - If `python -m omnigraph.research` returns non-zero → propagate exit code

    6. **What NOT to do**:
       - DO NOT call internal stages directly (web_baseline, retriever, reasoner, verifier, synthesizer) — they are not exposed as skills (design § Skill exposure)
       - DO NOT bypass the wrapper to invoke `python -m omnigraph.research` directly — keep the skill as the single entrypoint so future telemetry / wrapping lands in one place
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; ls skills/omnigraph_research/SKILL.md &amp;&amp; head -30 skills/omnigraph_research/SKILL.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists with valid YAML frontmatter
    - `name: omnigraph_research` (snake_case, matches sibling skills convention)
    - `triggers` list contains ≥ 4 entries including ≥ 1 Chinese phrase
    - `metadata.openclaw.requires.bins` includes `python`
    - `metadata.openclaw.requires.config` includes `GEMINI_API_KEY`
    - Body contains explicit decision tree distinguishing this skill from `omnigraph_query` and `omnigraph_ingest`
    - Body contains explicit "DO NOT expose internal stages as separate skills" line referencing design § Skill exposure
  </acceptance_criteria>
  <done>SKILL.md present with frontmatter + body, follows sibling-skill template.</done>
</task>

<task type="auto">
  <name>Task 2: Write skills/omnigraph_research/scripts/research.sh</name>
  <read_first>
    - skills/omnigraph_ingest/scripts/*.sh (shape template)
    - skills/omnigraph_query/scripts/*.sh (shape template)
    - lib/research/__main__.py (after ar-1-03) — confirms `python -m omnigraph.research "$query"` is the canonical invocation
  </read_first>
  <files>skills/omnigraph_research/scripts/research.sh</files>
  <action>
    Create `skills/omnigraph_research/scripts/research.sh` (~50 lines max) following the sibling-skill pattern:

    ```bash
    #!/usr/bin/env bash
    # omnigraph_research skill — invoke the agentic-RAG research pipeline.
    #
    # SKILL-01..05: thin wrapper around `python -m omnigraph.research`.
    # All logic lives in lib/research/. This script ONLY:
    #   1. Validates query argument
    #   2. Resolves repo root and venv
    #   3. Forwards to `python -m omnigraph.research "$query"`
    #   4. Propagates exit code

    set -euo pipefail

    if [[ $# -lt 1 ]]; then
        echo "Usage: research.sh <query>" >&2
        exit 1
    fi

    QUERY="$1"

    # Resolve repo root: skill is at <repo>/skills/omnigraph_research/scripts/research.sh
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

    # Pick the right venv python (Windows vs POSIX)
    if [[ -x "$REPO_ROOT/venv/Scripts/python.exe" ]]; then
        PY="$REPO_ROOT/venv/Scripts/python.exe"
    elif [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
        PY="$REPO_ROOT/venv/bin/python"
    else
        echo "ERROR: venv not found at $REPO_ROOT/venv" >&2
        exit 2
    fi

    cd "$REPO_ROOT"
    exec "$PY" -m omnigraph.research "$QUERY"
    ```

    Make executable: `chmod +x skills/omnigraph_research/scripts/research.sh` (on POSIX; Windows ignores).
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; bash skills/omnigraph_research/scripts/research.sh "test query" | head -20</automated>
  </verify>
  <acceptance_criteria>
    - File exists and is ≤ 60 lines
    - Has `#!/usr/bin/env bash` shebang and `set -euo pipefail`
    - Validates `$1` is provided; exits 1 with clear usage if not
    - Resolves repo root via `BASH_SOURCE` (works regardless of CWD)
    - Selects venv Python correctly on Windows (`venv/Scripts/python.exe`) and POSIX (`venv/bin/python`)
    - Invocation `bash research.sh "test"` produces non-empty stdout and exits 0
    - Script does NOT call internal stages — only `python -m omnigraph.research`
  </acceptance_criteria>
  <done>research.sh works on Windows Git Bash; sibling-skill style preserved.</done>
</task>

<task type="auto">
  <name>Task 3: Write skills/omnigraph_research/README.md (human-facing)</name>
  <read_first>
    - skills/omnigraph_ingest/README.md
    - skills/omnigraph_query/README.md
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Out of Scope for ar-1" (so README is honest about ar-1 stub state)
  </read_first>
  <files>skills/omnigraph_research/README.md</files>
  <action>
    Create `skills/omnigraph_research/README.md` with sections:

    1. **What this skill does** — short summary (1 paragraph)
    2. **Install** — symlink or copy `skills/omnigraph_research/` into the agent's skill directory; ensure `GEMINI_API_KEY` is set; venv created with `pip install -r requirements.txt`
    3. **Trigger examples** — 3-5 natural-language phrases that invoke this skill
    4. **Cost / Quality / Latency table** — current ar-1 stub state vs ar-4 final state:

       | Metric | ar-1 (current) | ar-4 (target) |
       |---|---|---|
       | Cost per query | ~$0 (stubs only) | ~$0.10-0.30 (Tavily + Vertex Gemini grounding + DeepSeek synth) |
       | Quality | Stub markdown with degradation notes | Full deep synthesis with image embeds + verifier confidence ≥ 60 |
       | Latency | < 2s | ≤ 120s for typical "deep dive" query |
       | Image embeds | None (retriever stub returns empty) | ≥ 3 images for image-rich KG topics |

    5. **What's deferred to later phases** — table mapping unfinished work to ar-2 / ar-3 / ar-4 (lift directly from CONTEXT.md § "Out of Scope")
    6. **Troubleshooting** — common failure modes:
       - Port 8765 already in use → `ensure_image_server` returns None silently; existing server is reused
       - `GEMINI_API_KEY` unset → ar-2 onward will fail; ar-1 stubs may still produce non-empty markdown but verifier degrades silently
       - Query produces "skipped" notes → expected in ar-1 (web_baseline, reasoner, verifier are stubs)
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; ls skills/omnigraph_research/README.md &amp;&amp; wc -l skills/omnigraph_research/README.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists, ≥ 50 lines
    - Contains the cost/quality/latency table (ar-1 vs ar-4 columns)
    - "What's deferred" section names ar-2, ar-3, ar-4 explicitly
    - Troubleshooting section addresses port-8765 + missing-API-key + skipped-notes scenarios
    - README is human-facing only (no agent triggers / decision-tree language — that lives in SKILL.md)
  </acceptance_criteria>
  <done>README.md is honest about ar-1 stub state; users can install and triage.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Write tests/skills/test_omnigraph_research.json + verify with skill_runner</name>
  <read_first>
    - skill_runner.py (top-level, to confirm test JSON schema)
    - tests/skills/test_omnigraph_ingest.json (sibling — schema template)
    - tests/skills/test_omnigraph_query.json (sibling — schema template)
  </read_first>
  <files>tests/skills/test_omnigraph_research.json</files>
  <behavior>
    - skill_runner harness must exit 0 when run as `venv/Scripts/python.exe skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json`
    - JSON contains ≥ 2 test cases: one English query, one Chinese query
    - Each test case asserts non-empty stdout (≥ 200 chars) and exit code 0
  </behavior>
  <action>
    Create `tests/skills/test_omnigraph_research.json` matching the schema from sibling test files. Approximate shape (verify against actual sibling JSON before committing):

    ```json
    {
      "skill": "omnigraph_research",
      "description": "ar-1 smoke harness — verifies research skill produces non-empty markdown",
      "tests": [
        {
          "name": "english_smoke",
          "trigger": "deep dive on Hermes Harness architecture",
          "expected_script": "scripts/research.sh",
          "expected_args": ["Hermes Harness architecture"],
          "expected_exit_code": 0,
          "stdout_min_chars": 200
        },
        {
          "name": "chinese_smoke",
          "trigger": "深度解析 Hermes Harness 是什么",
          "expected_script": "scripts/research.sh",
          "expected_args": ["Hermes Harness 是什么"],
          "expected_exit_code": 0,
          "stdout_min_chars": 200
        }
      ]
    }
    ```

    The exact field names depend on `skill_runner.py`'s parsing logic — read sibling test files first and match their schema verbatim. Do NOT invent fields skill_runner doesn't understand.

    Then run: `venv/Scripts/python.exe skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json` and verify exit code 0.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json; echo "exit=$?"</automated>
  </verify>
  <acceptance_criteria>
    - `tests/skills/test_omnigraph_research.json` exists and is valid JSON (`python -m json.tool < ...` succeeds)
    - Contains ≥ 2 test cases (English + Chinese)
    - JSON schema matches sibling test files (verified by reading them before writing)
    - `skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json` exits 0
    - Phase deliverable Layer 3 from CONTEXT.md is satisfied
  </acceptance_criteria>
  <done>Skill is discoverable, invokable, and testable via the canonical Hermes skill harness.</done>
</task>

</tasks>

<verification>
- All 4 tasks pass automated checks
- `skill_runner.py skills/omnigraph_research --test-file tests/skills/test_omnigraph_research.json` exits 0 (CONTEXT.md Layer 3 smoke test)
- All 3 layers from CONTEXT.md § "Smoke test for ar-1" pass:
  - Layer 1: pytest tests/unit/research/ -v (covered by ar-1-01..03)
  - Layer 2: python -m omnigraph.research "..." exits 0 with non-empty markdown (covered by ar-1-03)
  - Layer 3: skill_runner harness exits 0 (this plan)
- CONTRACT-01 grep still clean (no forbidden omnigraph_search imports added by skill files — should be clean since skill files are bash + json + md, no python)
</verification>

<success_criteria>

- 4 skill artifacts present: SKILL.md, scripts/research.sh, README.md, tests/skills/test_omnigraph_research.json
- skill_runner.py harness exits 0
- Internal stages remain hidden — no separate `omnigraph_web_baseline` / `omnigraph_retriever` / etc. skills exist (design § Skill exposure honored)
- README.md honestly documents ar-1 stub state vs ar-4 target state
- Skill is discoverable: `ls skills/omnigraph_research/` shows the 3 artifacts (SKILL.md, scripts/, README.md)
</success_criteria>

<output>
After completion, create `.planning/phases/ar-1-mvp-vertical-slice/ar-1-04-SUMMARY.md` documenting:
- Files created (count + list)
- skill_runner exit code + stdout char counts for each test case
- Verification that ALL 3 smoke layers (pytest + CLI + skill_runner) now pass
- Phase-level summary: ar-1 phase deliverable status (planned → ready-for-execution)
- Any deviations from plan (with reason)
</output>
