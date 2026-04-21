# Project Research Summary

**Project:** OmniGraph-Vault — Phase 2 (Skill Packaging + Gate 6/7)
**Domain:** Hermes Agent skill packaging over a Python knowledge-graph pipeline
**Researched:** 2026-04-21
**Confidence:** HIGH (codebase-grounded) / MEDIUM (Hermes runtime conventions)

---

## Executive Summary

OmniGraph-Vault Phase 2 is a skill-packaging project: wrapping an existing Python knowledge-base pipeline (`ingest_wechat.py`, `kg_synthesize.py`) in Hermes/OpenClaw agent skills so a user can say "add this to my kb" or "what do I know about X" and get a correct, well-formatted response. The domain is well-understood internally — the underlying scripts work and the skill interface conventions are documented authoritatively in CLAUDE.md. The recommended approach is two focused skills (`omnigraph_ingest`, `omnigraph_query`), each backed by a shell wrapper that handles venv activation and working-directory setup before calling Python.

The build is blocked by four known bugs that must be fixed before any gate testing: (1) hardcoded `/home/sztimhdd/` paths in multiple scripts that will silently break on Windows, (2) a missing `import json` in `kg_synthesize.py` that crashes on the first cross-article query, (3) a `"naive"` default query mode in `kg_synthesize.py` that produces poor cross-article results, and (4) a subprocess CWD assumption that will cause `ModuleNotFoundError` if Hermes execs the skill from a non-project-root directory. All four are confirmed from `CONCERNS.md` and must be fixed in Phase 1 (Gate 6 prep) before packaging.

The primary risk is the gap between `skill_runner.py` LLM tests (which validate routing logic only) and real Hermes execution (which validates actual script execution). Skills can pass all local tests while broken in deployment. The mitigation is a mandatory shell-level execution test run from `/tmp` before declaring Gate 7 complete. Secondary risk is trigger-phrase collision as future skills (`omnigraph_synthesize`, `omnigraph_manage`) are added; this must be managed proactively with explicit per-skill "when NOT to trigger" sections.

---

## Key Findings

### Recommended Stack

The skill interface is: agent → shell wrapper (`scripts/run-*.sh`) → Python script. A bare `exec python ingest_wechat.py` from an agent cannot activate the venv or guarantee working directory. Shell wrappers solve both: they `cd` to an absolute project root derived from `$(dirname "$0")`, activate the venv (checking both `venv/Scripts/activate` for Windows and `venv/bin/activate` for Linux/macOS), perform env var pre-flight checks, then invoke Python. This pattern is cross-platform and produces clean error messages before Python even starts.

A local `skill_runner.py` test harness (already in the repo) simulates Hermes by loading SKILL.md as a system prompt and sending test case JSON files through the same Gemini backend. It validates routing and format — but not script execution. Both layers are required for full confidence.

**Core technologies:**
- `scripts/run-*.sh` shell wrappers — venv activation, cwd, env pre-flight — required because exec cannot source a venv
- `SKILL.md` YAML frontmatter — name, description, triggers, metadata.openclaw.requires — agent dispatch mechanism
- `skill_runner.py` — LLM routing test harness — validates decision trees before real Hermes deploy
- `config.py` constants (`BASE_DIR`, `RAG_WORKING_DIR`, `SYNTHESIS_OUTPUT`) — single source of truth for all paths; all scripts must import from here

### Expected Features

**Must have (table stakes — missing any = broken experience):**

For `omnigraph_ingest`:
- GEMINI_API_KEY guard clause in shell wrapper before Python is invoked
- WeChat URL pattern validation before exec (prevents 300s wasted wait)
- Pre-exec announcement: "Starting ingestion — this takes 30–120 seconds"
- Success confirmation: title + hash + method (apify/cdp) + "entity extraction queued"
- Distinct failure messages: missing key, scrape failure (Apify+CDP both failed), non-WeChat URL

For `omnigraph_query`:
- GEMINI_API_KEY guard clause in shell wrapper
- Pre-exec announcement: "Querying — this takes 15–60 seconds"
- Default mode `hybrid` (not `naive` — this is a confirmed bug to fix)
- Image server warning if port 8765 not listening
- Synthesis output rendered as Markdown + save path shown
- Empty KB detection: response shorter than 100 chars or contains "I don't have enough information"

**Should have (differentiators):**
- URL validation before exec (regex check for `mp.weixin.qq.com` pattern)
- Query mode selection exposed to user (accept naive/local/global/hybrid/mix as optional keyword)
- Cognee recall notice: "drawing on N past queries" when past context non-empty
- PDF ingest redirect: detect `.pdf` extension in `omnigraph_ingest` and route to `multimodal_ingest.py`

**Defer to v2+:**
- Duplicate URL detection (check images/ dir for existing hash — medium complexity)
- Streaming progress feedback (requires restructuring scripts to write to temp file)
- `omnigraph_synthesize`, `omnigraph_status`, `omnigraph_manage` skills (out of Phase 2 scope)
- Batch ingestion loop (single URL per call is correct scope for Phase 2)

### Architecture Approach

The system has four layers: Hermes agent (NL interface) → skill layer (`skills/` at project root, highest OpenClaw precedence) → Python pipeline (project root scripts) → data layer (`~/.hermes/omonigraph-vault/`). The subprocess call is the contract boundary — the agent sees only stdin/stdout/exit-code. Argument order for both scripts is frozen on publish: `run-ingest.sh "<url>"` and `run-query.sh "<query>" [mode]`. SKILL.md bodies must be explicit decision trees under 150 lines; informational content (query modes table, troubleshooting) goes in `references/`.

**Major components:**
1. `SKILL.md` — agent decision tree: when to trigger, when not to, how to call, how to interpret output and errors
2. `scripts/run-*.sh` — shell wrappers: venv activation, cwd resolution, env pre-flight, python invocation
3. `references/api-surface.md` — Level 2 documentation: script args, output schema, all query modes
4. `skill_runner.py` — local LLM routing tests (validates SKILL.md logic, not script execution)
5. `tests/verify_gate_6.py` — cross-article synthesis validation (pipeline-level gate test)

### Critical Pitfalls

1. **Hardcoded `/home/sztimhdd/` paths** — silently breaks on Windows and any other machine. Fix: replace all occurrences in `ingest_wechat.py` (lines 279, 280, 368), `kg_synthesize.py` (line 50), `cognee_batch_processor.py` (lines 9, 30, 35, 36), `cognee_wrapper.py` (line 8), `init_cognee.py` (lines 5, 23), `list_entities.py` (line 5), `query_lightrag.py` (line 12), and all `tests/verify_gate_*.py` files with `config.py` constants. Add `ENTITY_BUFFER_DIR` and `CANONICAL_MAP_FILE` to `config.py`. Run `grep -r '/home/' *.py` before any gate.

2. **Missing `import json` in `kg_synthesize.py`** — `NameError` on first cross-article query when `canonical_map.json` exists. One-line fix, but a Gate 6 blocker. `py_compile` will not catch it — only manifests at runtime when the conditional branch at line 54 is reached.

3. **Subprocess CWD mismatch** — Hermes may exec the skill wrapper from any directory. If the wrapper does not `cd` to an absolute project root before invoking Python, every script fails with `ModuleNotFoundError: No module named 'config'`. Prevention: derive `PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"` in every shell wrapper, then `cd "$PROJECT_ROOT"` before calling Python.

4. **`skill_runner.py` gives false passes for script execution failures** — the test harness validates LLM routing, not actual script execution. All 6 critical script bugs (hardcoded paths, missing import, naive default, etc.) pass `skill_runner.py`. Mandatory complement: run the shell wrapper script directly from `/tmp` and assert exit 0 and expected stdout before Gate 7.

5. **Trigger phrase collisions** — overlapping triggers between skills cause wrong-skill dispatch with no error surfaced. Current risk: `"what do I know about"` and `"search my kb"` may collide with future `omnigraph_synthesize`. Prevention: write `description` field as an explicit mutex; maintain "when NOT to trigger" sections in every skill body; test ambiguous phrases across the full skill catalog, not just one skill at a time.

---

## Implications for Roadmap

Research points to three sequential phases with clear dependency ordering.

### Phase 1: Bug Fixes and Gate 6 Validation

**Rationale:** Gate 6 (cross-article synthesis) is the pre-condition for skill packaging. Four confirmed bugs will cause Gate 6 to fail: the missing `import json`, hardcoded paths, the `"naive"` default mode, and the missing `ENTITY_BUFFER_DIR`/`CANONICAL_MAP_FILE` constants. These must be fixed and verified before writing a single skill file. Attempting skill packaging before Gate 6 passes leads to debugging two unknowns simultaneously.

**Delivers:** A working `kg_synthesize.py` + `ingest_wechat.py` stack validated against 3 real WeChat articles with confirmed cross-article entity references in the synthesis output. `tests/verify_gate_6.py` exits 0.

**Addresses features:** Fixes the `hybrid` mode default (query feature), fixes path portability (prerequisite for all features), fixes `import json` (prerequisite for all query features).

**Avoids pitfalls:** Hardcoded paths (Pitfall 1), missing import json (Pitfall 6), naive default mode (Pitfall 8), batch processor timing (Pitfall 11).

**Tasks in order:**
1. Add `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE` to `config.py`
2. Replace all hardcoded `/home/sztimhdd/` paths across all affected files
3. Add `import json` to `kg_synthesize.py`
4. Change default mode from `"naive"` to `"hybrid"` in `kg_synthesize.py`
5. Choose 3 real WeChat article URLs with shared named entities
6. Fill `EXPECTED_ENTITIES` in `verify_gate_6.py`
7. Run ingestion for all 3 articles, run batch processor, run `python tests/verify_gate_6.py`

### Phase 2: Skill Packaging

**Rationale:** Once Gate 6 passes, the pipeline is confirmed working. Phase 2 creates the skill layer: SKILL.md files, shell wrappers, references, and README files. The shell wrapper pattern (venv activation + cwd resolution + env pre-flight) is the most critical artifact. SKILL.md bodies must follow the decision-tree pattern with "when NOT to trigger" sections to prevent future collision.

**Delivers:** `skills/omnigraph-ingest/` and `skills/omnigraph-query/` directories, each with SKILL.md, `scripts/run-*.sh`, `references/api-surface.md`, and README.md. All table-stakes features implemented. `skill_runner.py --test-all` exits 0 for both skills.

**Uses:** Shell wrapper pattern (STACK.md), trigger phrase design and error format specification (FEATURES.md), SKILL.md decision tree structure (ARCHITECTURE.md).

**Implements:** Skill layer component in the 4-layer architecture.

**Avoids pitfalls:** CWD mismatch (Pitfall 5), env var pre-flight opacity (Pitfall 3), SKILL.md bloat (Pitfall 7), trigger collisions (Pitfall 2).

**Tasks in order:**
1. Write `skills/omnigraph-ingest/scripts/run-ingest.sh` (env pre-flight, venv activation, cwd, python call)
2. Write `skills/omnigraph-ingest/SKILL.md` (frontmatter, decision tree under 150 lines)
3. Write `skills/omnigraph-ingest/references/api-surface.md`
4. Write `skills/omnigraph-ingest/README.md`
5. Run `python skill_runner.py skills/omnigraph-ingest --test-file tests/skills/test_omnigraph_ingest.json`
6. Repeat steps 1–5 for `omnigraph-query`
7. Write `tests/skills/test_omnigraph_ingest.json` and `test_omnigraph_query.json` if not already complete

### Phase 3: Deploy and Gate 7 Validation

**Rationale:** Gate 7 validates the skills in real Hermes, which is the only context that tests actual subprocess execution, Hermes trigger-phrase matching against the live catalog, and Windows shell compatibility. `skill_runner.py` must pass first (Phase 2), but it is not sufficient for Gate 7 confidence.

**Delivers:** Both skills verified end-to-end in real Hermes Agent: trigger-phrase dispatch works, scripts execute from correct cwd, GEMINI_API_KEY guard clause fires cleanly when key is absent, cross-article query returns a multi-source synthesis, wrong-topic inputs do not fire either skill.

**Avoids pitfalls:** skill_runner false passes (Pitfall 4), Windows path separators (Pitfall 10), CWD mismatch on real Hermes (Pitfall 5).

**Tasks in order:**
1. Shell-level execution test: run `run-ingest.sh` and `run-query.sh` from `/tmp`, assert exit 0
2. Windows compatibility test: run wrappers from both Git Bash and PowerShell
3. Deploy skills to `<workspace>/skills/` on Hermes machine; run `hermes skills list` or `/new`
4. Run 6-test Gate 7 protocol: ingest trigger, query trigger, cross-article query, wrong-trigger rejection, missing-key guard, CDP-not-running guard
5. Document Gate 7 pass evidence (screenshots or terminal output)

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** Cannot package a skill that wraps a broken pipeline. Gate 6 failure after packaging creates double-debugging confusion.
- **Phase 2 before Phase 3:** Cannot Gate 7 a skill that doesn't exist. `skill_runner.py` is the entry filter; real Hermes is the exit validation.
- **Bug fixes grouped in Phase 1:** The 4 confirmed bugs are all pre-conditions for both Gate 6 and Gate 7. Fixing them together in one sweep also allows a single re-read pass over all affected files.
- **Both skills built together in Phase 2:** They share the shell wrapper pattern and the test harness; building them together catches trigger collision issues before deploy.

### Research Flags

Phases that are well-documented (standard patterns — skip additional research):
- **Phase 1 bug fixes:** All locations and fixes are known. Grep-and-replace with config constants. No research needed.
- **Phase 2 shell wrapper:** Canonical pattern documented in STACK.md and ARCHITECTURE.md. Ready to implement directly.
- **Phase 2 SKILL.md:** Template, frontmatter spec, and decision-tree pattern are fully documented in CLAUDE.md and ARCHITECTURE.md.

Phases that may need targeted validation:
- **Phase 3 Windows shell:** Exact shell type Hermes uses on Windows (Git Bash vs PowerShell vs cmd.exe) is not confirmed. Test both before declaring Gate 7 complete. If PowerShell is used, the `source` command in shell wrappers will fail — Python wrapper scripts may be needed as a fallback (see PITFALLS.md Pitfall 10).
- **Phase 3 Hermes trigger resolution:** The multi-skill catalog trigger collision behavior (Pitfall 2) is inferred from CLAUDE.md, not directly observed. Confirm with a cross-skill ambiguity test case in Gate 7 protocol.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Shell wrapper pattern, SKILL.md format, and error protocol all derived from in-repo sources (CLAUDE.md, codebase analysis). Official Hermes/OpenClaw URLs unreachable — CLAUDE.md treated as authoritative proxy since it was synthesized from those docs. |
| Features | HIGH | Trigger phrases, failure modes, and response formats derived from direct code analysis of ingest_wechat.py and kg_synthesize.py + CLAUDE.md output formatting rules. Empty KB detection heuristic is MEDIUM — needs live validation. |
| Architecture | HIGH | 4-layer structure and component boundaries confirmed from codebase. Gate 6 test structure derived from existing verify_gate_a/b/c pattern. Hermes exec environment not directly observed — inferred from CLAUDE.md conventions. |
| Pitfalls | HIGH | 6 critical pitfalls confirmed directly from CONCERNS.md with file/line evidence. Trigger collision analysis and Windows shell pitfalls are MEDIUM — inferred from structure, not directly tested. |

**Overall confidence:** HIGH for the in-repo implementation work. MEDIUM for Hermes runtime behavior specifically.

### Gaps to Address

- **Exact Hermes shell on Windows:** Unknown whether Hermes uses Git Bash, PowerShell, or cmd.exe for skill exec. If not Git Bash, `source` will fail and shell wrappers need to be replaced with Python launcher scripts. Validate in Phase 3 before any other Gate 7 testing.
- **`metadata.openclaw.requires.config` enforcement:** Whether Hermes actually performs a pre-flight check for listed config vars or treats this field as advisory text only is unconfirmed. Do not rely on it — the shell wrapper must always perform the env pre-flight check independently.
- **Empty KB detection strings:** The heuristic (response < 100 chars or contains "I don't have enough information") is based on expected LightRAG output patterns, not confirmed live behavior. Validate against a real empty-storage run after Phase 1 bug fixes are in place.
- **Gate 7 cross-skill collision test:** `skill_runner.py` tests one skill at a time. Testing trigger disambiguation across the full catalog requires real Hermes. Add at least one cross-skill ambiguity test phrase to the Gate 7 protocol.

---

## Sources

### Primary — HIGH confidence (in-repo, direct codebase analysis)

- `c:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/codebase/CONCERNS.md` — confirmed bugs, hardcoded paths, bare except clauses, missing import json, naive default mode
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/CLAUDE.md` — skill writing standards (synthesized from hermes-agent.ai, docs.openclaw.ai, lushbinary.com by project author; treated as authoritative proxy)
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/kg_synthesize.py` — exit code conventions, json.load usage, mode default
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/ingest_wechat.py` — error surfacing pattern, hardcoded paths
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skill_runner.py` — test harness design, LLM-only validation scope
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/config.py` — BASE_DIR, RAG_WORKING_DIR, SYNTHESIS_OUTPUT constants
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/tests/verify_gate_a/b/c.py` — gate test structure pattern
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skills/omnigraph_ingest/SKILL.md` — existing trigger phrases
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skills/omnigraph_query/SKILL.md` — existing trigger phrases, synthesis_output.md path
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/PROJECT.md` — phase requirements, subprocess interface design decision, Windows-primary platform constraint

### Secondary — MEDIUM confidence (inferred from CLAUDE.md conventions, not directly observed)

- Hermes trigger-phrase matching behavior across multi-skill catalog
- Hermes exec shell type on Windows
- `metadata.openclaw.requires.config` enforcement behavior
- Empty KB detection string patterns from LightRAG

---

*Research completed: 2026-04-21*
*Ready for roadmap: yes*
