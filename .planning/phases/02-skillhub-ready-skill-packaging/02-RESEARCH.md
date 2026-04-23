# Phase 2: SkillHub-Ready Skill Packaging - Research

**Researched:** 2026-04-22
**Domain:** Hermes/OpenClaw skill packaging, shell wrappers, eval suites, LLM-based skill testing
**Confidence:** HIGH

## Summary

Phase 2 is a packaging and validation phase -- not a greenfield build. Most files already exist on disk from pre-Phase-1 scaffolding. The work is auditing existing content against requirements, filling gaps, and ensuring `skill_runner.py` passes all test cases.

Both skill directories (`skills/omnigraph_ingest/`, `skills/omnigraph_query/`) already contain SKILL.md, scripts/, references/api-surface.md, and evals/evals.json. Shell wrappers already implement CWD independence, venv activation (Windows + Unix), env validation, and announcements. The `install-for-hermes.sh` script is complete. Test case files exist at `tests/skills/`.

**Primary recommendation:** Audit each existing file against its requirement checklist, fix gaps (description word counts, missing test cases, eval schema compliance), then run `skill_runner.py` to validate. The embedding experiment (EMBEDDING_STRATEGY_DECISION.md) is a separate investigation task that does not block packaging.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PKG-01 | Both SKILL.md descriptions 100-200 words, pushy format | Existing descriptions need word count audit; ingest ~160 words, query ~170 words -- likely compliant |
| PKG-02 | SKILL.md bodies <=500 lines | Ingest: 127 lines, Query: 146 lines -- both compliant |
| PKG-03 | Scripts resolve OMNIGRAPH_ROOT, activate venv, validate env, CWD-independent | Both wrappers already implement all 4 behaviors -- verify only |
| PKG-04 | README covers install, env setup, skill_runner invocation | Already marked Done in STATE.md |
| SKILL-01 | ingest.sh announces timing, dispatches URL vs PDF, exits non-zero on missing env | Already implemented in ingest.sh lines 53-59 |
| SKILL-02 | Ingest SKILL.md frontmatter: name, pushy description, no triggers block | Frontmatter present and correct; verify no `triggers:` key |
| SKILL-03 | Ingest SKILL.md decision tree: WeChat URL, PDF, no URL, missing key, non-WeChat guard | All 5 cases present (Cases 1-5) |
| SKILL-04 | Ingest SKILL.md "When NOT to Use" section | Present with 5 redirects |
| SKILL-05 | Ingest references/api-surface.md covers CLI args, env vars, dispatch, exit codes | Present and comprehensive |
| SKILL-07 | query.sh announces timing, calls kg_synthesize.py, exits non-zero on missing env | Already implemented in query.sh |
| SKILL-08 | Query SKILL.md frontmatter with pushy description | Present and correct |
| SKILL-09 | Query SKILL.md: image server warning, decision tree, empty KB, destructive guard | All present |
| SKILL-10 | Query SKILL.md "When NOT to Use" section | Present with 5 redirects |
| SKILL-11 | Query references/api-surface.md | Present and comprehensive |
| EVAL-01 | Ingest evals/evals.json >=3 cases in SkillHub schema | 5 cases present in correct schema |
| EVAL-02 | Query evals/evals.json >=3 cases | 5 cases present in correct schema |
| TEST-01 | test_omnigraph_ingest.json covers trigger matching, guards, redirects | 9 cases present |
| TEST-02 | test_omnigraph_query.json covers trigger matching, empty KB, redirects | 10 cases present |
| TEST-03 | skill_runner ingest tests exit 0 | Requires execution validation |
| TEST-04 | skill_runner query tests exit 0 | Requires execution validation |
</phase_requirements>

## Current State Audit

### Files Already on Disk

| File | Lines | Status |
|------|-------|--------|
| `skills/omnigraph_ingest/SKILL.md` | 127 | Complete -- all 5 decision tree cases, When NOT to Use, error table |
| `skills/omnigraph_ingest/scripts/ingest.sh` | 59 | Complete -- OMNIGRAPH_ROOT, venv (Win+Unix), env check, dispatch, announce |
| `skills/omnigraph_ingest/references/api-surface.md` | 87 | Complete -- CLI args, env vars, dispatch logic, exit codes, error messages |
| `skills/omnigraph_ingest/evals/evals.json` | 40 | 5 eval cases in SkillHub schema |
| `skills/omnigraph_query/SKILL.md` | 146 | Complete -- image server note, 5 cases, When NOT to Use, mode table |
| `skills/omnigraph_query/scripts/query.sh` | 57 | Complete -- OMNIGRAPH_ROOT, venv, env check, announce, mode dispatch |
| `skills/omnigraph_query/references/api-surface.md` | 86 | Complete -- CLI args, modes table, exit codes, output paths |
| `skills/omnigraph_query/evals/evals.json` | 40 | 5 eval cases in SkillHub schema |
| `tests/skills/test_omnigraph_ingest.json` | 53 | 9 test cases |
| `tests/skills/test_omnigraph_query.json` | 57 | 10 test cases |
| `scripts/install-for-hermes.sh` | 205 | Complete -- 7-step installer with venv, deps, import validation, smoke test |
| `skill_runner.py` | 368 | Complete -- test-file, test-all, validate, verbose modes; exit 0/1/2 |

### Gaps Identified

1. **Description word count verification** -- descriptions appear to be 100-200 words but need exact count from frontmatter YAML only (not full file). Confidence: HIGH that they comply.

2. **skill_runner.py exit codes** -- requirements say exit 0 pass, non-zero fail. Current code supports exit 0/1/2. Needs execution to confirm TEST-03 and TEST-04 pass.

3. **install-for-hermes.sh argument handling** -- line 179 checks `$1` but the script has already consumed no positional args by that point. The `--skip-test` check works but only for the first positional argument.

4. **Embedding strategy experiment** -- EMBEDDING_STRATEGY_DECISION.md exists as a protocol template but experiment has not been run. This is listed in Phase 2 success criteria item 8 but is NOT a requirement ID in the requirements list. It is a separate investigation that can be a standalone plan.

## Architecture Patterns

### Skill Directory Contract

```
skills/omnigraph_{name}/
  SKILL.md              # <=500 lines; frontmatter + body
  scripts/{name}.sh     # CWD-independent bash wrapper
  references/           # Heavy docs loaded on demand
    api-surface.md
  evals/
    evals.json          # SkillHub schema: skill_name + evals[]
```

### Shell Wrapper Pattern (already implemented)

```bash
OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"
# 1. Validate OMNIGRAPH_ROOT exists
# 2. Validate required args
# 3. Validate GEMINI_API_KEY
# 4. Activate venv (Windows Scripts/ or Unix bin/)
# 5. cd to project root
# 6. Announce timing + run Python script
```

### Test Case Schema (skill_runner)

```json
[
  {
    "description": "human-readable test name",
    "input": "simulated user message",
    "expect_contains": ["strings that MUST appear in LLM response"],
    "expect_not_contains": ["strings that must NOT appear"]
  }
]
```

### Eval Schema (SkillHub)

```json
{
  "skill_name": "omnigraph_ingest",
  "evals": [
    {
      "id": 0,
      "name": "snake_case_name",
      "prompt": "user message",
      "expected_output": "description of expected behavior",
      "files": []
    }
  ]
}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Skill testing | Custom test harness | `skill_runner.py` (already exists) | Already handles LLM routing, expect_contains/not_contains, exit codes |
| Venv activation | Platform-specific script | Dual-path check in shell wrapper | Windows Scripts/ vs Unix bin/ already handled |
| Env loading | Manual source in wrapper | `config.py` handles it at Python import time | Shell wrapper only needs GEMINI_API_KEY for pre-flight; Python gets the rest |

## Common Pitfalls

### Pitfall 1: SKILL.md Description Word Count
**What goes wrong:** Description is too short (<100 words) and Claude under-triggers the skill, or too long (>200 words) and wastes Level 0 tokens.
**How to avoid:** Count words in the `description:` YAML field only (not the full file). Both existing descriptions appear to be in range.

### Pitfall 2: skill_runner Test Flakiness
**What goes wrong:** LLM-based tests are non-deterministic. A test that passes 9/10 times fails on the 10th.
**How to avoid:** Keep `expect_contains` strings short and fundamental (e.g., "ingest.sh" not "Starting ingestion -- this may take 30-120 seconds"). Existing test cases use this pattern correctly.

### Pitfall 3: Shell Wrapper Path Quoting
**What goes wrong:** Paths with spaces break unquoted variables in bash.
**How to avoid:** Both wrappers already quote `$OMNIGRAPH_ROOT` and `$TARGET`/`$QUERY` correctly.

### Pitfall 4: install-for-hermes.sh Env Loading
**What goes wrong:** `export $(cat file | grep KEY)` can fail with multi-line .env files or comments.
**How to avoid:** Current implementation on line 38 uses simple grep -- works for single-key extraction. Not a blocker but fragile.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | skill_runner.py (custom, LLM-based) |
| Config file | None -- test cases are JSON files |
| Quick run command | `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` |
| Full suite command | `python skill_runner.py skills/ --test-all` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-03 | Ingest skill_runner passes | LLM routing | `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` | Yes |
| TEST-04 | Query skill_runner passes | LLM routing | `python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json` | Yes |
| PKG-01 | Description word count | manual | Count words in YAML frontmatter description field | N/A |
| PKG-02 | SKILL.md <=500 lines | manual | `wc -l skills/*/SKILL.md` | N/A |
| PKG-03 | CWD independence | manual | `cd /tmp && bash ~/Desktop/OmniGraph-Vault/skills/omnigraph_ingest/scripts/ingest.sh` | N/A |

### Sampling Rate
- **Per task commit:** `python skill_runner.py skills/ --test-all`
- **Per wave merge:** Same
- **Phase gate:** Full suite green + manual CWD independence check

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. `skill_runner.py` and all test JSON files already exist.

## Embedding Strategy (Separate Investigation)

The EMBEDDING_STRATEGY_DECISION.md documents an experiment protocol comparing:
- **Option A (current):** Image -> Gemini Vision describe -> Gemini Embeddings embed text (2 API calls/image, ~$0.05/article)
- **Option B:** Image -> multimodal embedding-2 directly (1 call, ~$0.001/article, 50-100x cheaper IF LightRAG supports it)

This experiment is listed as Phase 2 success criterion #8 but has no requirement ID. It is investigation work that should be a separate plan, not blocking the packaging tasks.

**Key constraint:** LightRAG compatibility with multimodal vectors is unverified. If LightRAG cannot store/retrieve multimodal vectors, Option B is not viable and the decision is "keep current."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All scripts | Needs verification at execution | -- | -- |
| bash | Shell wrappers | Yes (Git Bash on Windows) | -- | -- |
| GEMINI_API_KEY | LLM calls in skill_runner | Needs env check | -- | Cannot run tests without it |

## Sources

### Primary (HIGH confidence)
- Direct file reads of all skill files, test files, wrappers, and skill_runner.py
- `specs/SKILL_PACKAGING_GUIDE.md` -- SkillHub contract definition
- `.planning/REQUIREMENTS.md` -- all requirement IDs and acceptance criteria

### Secondary (MEDIUM confidence)
- `specs/EMBEDDING_STRATEGY_DECISION.md` -- experiment protocol (not yet executed)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all files already exist, just need audit
- Architecture: HIGH -- patterns are established and documented in SKILL_PACKAGING_GUIDE.md
- Pitfalls: HIGH -- based on direct code inspection of existing files

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (stable -- no external dependencies changing)
