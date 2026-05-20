---
phase: llm-wiki-integration
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - kb/wiki/SCHEMA.md
  - kb/wiki/index.md
  - kb/wiki/log.md
  - kb/wiki/README.md
  - kb/wiki/entities/openclaw.md
  - kb/wiki/_suggestions/.gitkeep
  - kb/wiki/concepts/.gitkeep
  - kb/wiki/comparisons/.gitkeep
  - kb/wiki/queries/.gitkeep
  - tests/unit/test_wiki_lint.py
  - tests/unit/test_wiki_centrality.py
  - tests/unit/test_wiki_citations.py
  - tests/integration/test_wiki_hook.py
  - tests/integration/test_wiki_generate.py
  - tests/integration/kb/test_synthesize_wiki_inject.py
  - tests/unit/kb/test_synthesize_wiki_fallthrough.py
  - .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md
autonomous: true
requirements:
  - WIKI-LOC          # Decision 2: wiki at kb/wiki/
  - WIKI-SEED         # port openclaw.md from Hermes ~/wiki-omnigraph/
  - WIKI-FRONTMATTER  # follow nashsu/llm_wiki frontmatter convention
  - WIKI-TEST-STUBS   # Wave 0 test scaffolding per VALIDATION.md
must_haves:
  truths:
    - "kb/wiki/ directory tree exists with SCHEMA.md, index.md, log.md, README.md"
    - "kb/wiki/entities/openclaw.md exists with frontmatter + ^[article:<hash>] citations"
    - "Empty test stub files for wiki tests exist with @pytest.mark.skip markers"
    - "Hermes operator prompt is generated for symlink ~/wiki-omnigraph -> ~/OmniGraph-Vault/kb/wiki"
  artifacts:
    - path: "kb/wiki/SCHEMA.md"
      provides: "Agent behavior rules + tag taxonomy"
      contains: "frontmatter convention + citation format"
    - path: "kb/wiki/entities/openclaw.md"
      provides: "First wiki page reference (ported from Hermes ~/wiki-omnigraph/)"
      contains: "^[article:"
    - path: "kb/wiki/README.md"
      provides: "Human-readable scaffold doc + sync mechanism + rollback procedure"
    - path: "tests/unit/test_wiki_lint.py"
      provides: "Empty test stub for citation/contradiction/backlink/staleness lint"
    - path: ".planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md"
      provides: "Operator prompt for Hermes-side symlink (per CLAUDE.md Rule 5 — no SSH outsourcing)"
  key_links:
    - from: "kb/wiki/SCHEMA.md"
      to: "kb/wiki/entities/openclaw.md"
      via: "frontmatter convention documented in SCHEMA, applied in openclaw.md"
      pattern: "^title:|^created:|^last_updated:|^sources:|^confidence_level:"
    - from: "kb/wiki/README.md"
      to: "Hermes ~/wiki-omnigraph/"
      via: "sync mechanism (symlink) documented for operator"
      pattern: "symlink|wiki-omnigraph"
---

<objective>
Create `kb/wiki/` scaffold and port seed content from Hermes `~/wiki-omnigraph/` into the repo. Produce all empty test stubs declared in `llm-wiki-VALIDATION.md` so subsequent waves have a place to add real tests. Generate a Hermes operator prompt (NOT SSH commands) that sets up the production symlink.

Purpose: This is W0 — the foundation. Every later wave depends on `kb/wiki/` existing and on test stubs being importable.
Output: Repository directory tree under `kb/wiki/` + 7 test stub files + 1 operator prompt file.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md
@.planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md
@.planning/phases/llm-wiki-integration/llm-wiki-VALIDATION.md
@./CLAUDE.md
</context>

<interfaces>
<!-- W0 creates contracts that W1-W4 consume. -->

Frontmatter schema for every wiki page (per RESEARCH.md "Standard Stack"):
```yaml
---
title: <page display name>
created: <ISO date>
last_updated: <ISO date>
sources:
  - article:<10-char-hex>
  - article:<10-char-hex>
confidence_level: high | medium | low
---
```

Citation format inside body (per RESEARCH.md):
```
^[article:<10-char-hex>]
```

Cross-reference format (intra-wiki):
```
[[entity-slug]]
```

Test stub pattern (per VALIDATION.md Wave 0 Requirements):
```python
import pytest

@pytest.mark.skip(reason="Wave N implementation pending; W0 stub")
def test_placeholder():
    pass
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Create kb/wiki/ directory tree + SCHEMA.md + index.md + log.md + README.md</name>
  <files>kb/wiki/SCHEMA.md, kb/wiki/index.md, kb/wiki/log.md, kb/wiki/README.md, kb/wiki/_suggestions/.gitkeep, kb/wiki/concepts/.gitkeep, kb/wiki/comparisons/.gitkeep, kb/wiki/queries/.gitkeep, kb/wiki/entities/.gitkeep</files>
  <read_first>
    - .planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md (Decision 2 — wiki at kb/wiki/)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Standard Stack frontmatter convention)
    - CLAUDE.md (HIGHEST PRIORITY PRINCIPLES — Surgical Changes; do not modify code outside kb/wiki/)
  </read_first>
  <action>
    Create the `kb/wiki/` directory tree. Use `.gitkeep` for empty subdirs so git tracks them.

    Subdirs to create: `entities/`, `concepts/`, `comparisons/`, `queries/`, `_suggestions/`.

    File contents (write each via Write tool):

    **`kb/wiki/SCHEMA.md`** — Agent behavior rules + tag taxonomy. Document:
    1. Required frontmatter fields: `title`, `created`, `last_updated`, `sources` (list of `article:<10-char-hex>`), `confidence_level` (high|medium|low). YAML.
    2. Citation format inside body: `^[article:<10-char-hex>]`. Every claim paragraph MUST cite at least one article.
    3. Cross-reference format: `[[entity-slug]]` (lowercase, hyphenated).
    4. Allowed subdirs and what each contains: `entities/` (one page per canonical entity), `concepts/` (cross-cutting concepts e.g. "agent-skills"), `comparisons/` (X-vs-Y pages), `queries/` (saved high-value Q&A), `_suggestions/` (auto-generated W3 suggestions awaiting lint pass).
    5. Naming convention: snake-case file names matching entity slug (e.g., `openclaw.md`, `hermes-agent.md`).
    6. Lint contract (W3 will enforce; documented here for transparency): citation integrity, backlink validity, contradiction detection, staleness check.

    **`kb/wiki/index.md`** — Directory of pages. Initial content lists `entities/openclaw.md` (Task 2 will add it). Format: markdown bullet list grouped by subdir. Header: `# OmniGraph Wiki Index`. Note "Last updated by W1 wiki-update process; manual edits welcome."

    **`kb/wiki/log.md`** — Operation log. Initial content one entry: `2026-05-19 — W0 scaffold created (port from ~/wiki-omnigraph/)`. Format: reverse-chronological markdown bullet list. Header: `# Wiki Operation Log`.

    **`kb/wiki/README.md`** — Human-readable doc covering:
    1. What this directory is (compounding markdown artifact synthesizing LightRAG entities; see `.planning/wiki-integration-design.md`)
    2. Sync to Hermes (per Decision 2): symlink approach `~/wiki-omnigraph -> ~/OmniGraph-Vault/kb/wiki` set up via Hermes operator prompt at `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md`. Hermes-side `git pull` keeps content fresh.
    3. Rollback procedure (per RESEARCH.md Pitfall 5): wiki writes are git-tracked; revert via `git revert <commit>` or `git checkout <hash> -- kb/wiki/<path>`.
    4. Subdir layout (mirror SCHEMA.md item 4).
    5. Pointer to `kb/wiki/SCHEMA.md` for the formal contract.

    `.gitkeep` files: empty (one byte newline ok); just ensure the empty subdirs are tracked.
  </action>
  <verify>
    <automated>test -f kb/wiki/SCHEMA.md && test -f kb/wiki/index.md && test -f kb/wiki/log.md && test -f kb/wiki/README.md && test -d kb/wiki/entities && test -d kb/wiki/concepts && test -d kb/wiki/comparisons && test -d kb/wiki/queries && test -d kb/wiki/_suggestions</automated>
  </verify>
  <acceptance_criteria>
    - `test -d kb/wiki/entities` exits 0
    - `test -f kb/wiki/SCHEMA.md` exits 0
    - `grep -q 'confidence_level' kb/wiki/SCHEMA.md` exits 0
    - `grep -q 'article:<10-char-hex>' kb/wiki/SCHEMA.md` exits 0
    - `grep -q 'symlink' kb/wiki/README.md` exits 0
    - `grep -q 'rollback\|revert' kb/wiki/README.md` exits 0 (case-insensitive: `grep -qi`)
  </acceptance_criteria>
  <done>kb/wiki/ tree exists with SCHEMA, index, log, README; 5 empty subdirs tracked via .gitkeep; SCHEMA documents frontmatter + citation + cross-ref + lint contract; README explains sync + rollback.</done>
</task>

<task type="auto">
  <name>Task 2: Port entities/openclaw.md from Hermes ~/wiki-omnigraph/ + Hermes operator prompt</name>
  <files>kb/wiki/entities/openclaw.md, .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md, kb/wiki/index.md, kb/wiki/log.md</files>
  <read_first>
    - kb/wiki/SCHEMA.md (just created in Task 1 — frontmatter convention)
    - .planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md (canonical_refs section; openclaw.md ~5763 chars, 6-article synthesis)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Examples: Example 1 wiki page format)
    - CLAUDE.md (Rule 5 — never write SSH commands for the user; produce Hermes operator prompt)
  </read_first>
  <action>
    The Hermes wiki seed content lives at `~/wiki-omnigraph/entities/openclaw.md` on the Hermes box. Per CLAUDE.md Rule 5, do NOT SSH-outsource. Two-step approach:

    **Step A — Generate Hermes operator prompt** at `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` containing two sections:

    1. **"Section 1 — Export wiki seed content (one-shot)"**: A bash block the user forwards to Hermes that prints (NOT modifies) the contents of `~/wiki-omnigraph/SCHEMA.md`, `~/wiki-omnigraph/index.md`, `~/wiki-omnigraph/log.md`, `~/wiki-omnigraph/entities/openclaw.md` so the user can paste back to this Claude session. Example format:
       ```
       echo "=== SCHEMA.md ==="; cat ~/wiki-omnigraph/SCHEMA.md
       echo "=== entities/openclaw.md ==="; cat ~/wiki-omnigraph/entities/openclaw.md
       ```
       (read-only operation; safe; does not require Hermes)

    2. **"Section 2 — Set up production symlink"**: Hermes operator prompt requesting:
       ```
       cd ~/OmniGraph-Vault && git pull --ff-only
       # Backup if existing dir
       if [ -d ~/wiki-omnigraph ] && [ ! -L ~/wiki-omnigraph ]; then
         mv ~/wiki-omnigraph ~/wiki-omnigraph.backup-$(date +%Y%m%d-%H%M%S)
       fi
       ln -sfn ~/OmniGraph-Vault/kb/wiki ~/wiki-omnigraph
       ls -la ~/wiki-omnigraph
       ```
       Include explicit "WAIT for user confirmation before running Section 2 — symlinking replaces existing dir."

    **Step B — Write `kb/wiki/entities/openclaw.md`** as a faithful port. Since we cannot reach Hermes directly:
       - If user has already pasted content from Section 1 into this session: use that content verbatim.
       - Otherwise (initial run): write a placeholder openclaw.md with the correct frontmatter shape but body content marked `<!-- TODO: Replace with port from ~/wiki-omnigraph/entities/openclaw.md via Section 1 of HERMES-PROMPT-W0-SYNC.md -->`. Include at least one valid `^[article:` citation reference (placeholder hash `0000000000`) so grep checks pass; W1 will overwrite this file with real generated content anyway.
       - Frontmatter MUST include: `title: OpenClaw`, `created: 2026-05-08`, `last_updated: 2026-05-19`, `sources:` (placeholder list with one `article:0000000000`), `confidence_level: medium`.
       - Body MUST contain at least one `^[article:0000000000]` citation marker.

    **Step C — Update `kb/wiki/index.md`**: append a bullet under entities subsection: `- [OpenClaw](entities/openclaw.md) — AI desktop assistant (placeholder; refresh in W1)`.

    **Step D — Append to `kb/wiki/log.md`**: `2026-05-19 — entities/openclaw.md placeholder seeded (W0 Task 2); Hermes operator prompt written to .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md`.

    Do NOT run `ssh` from Bash tool. Do NOT attempt to write to Hermes filesystem.
  </action>
  <verify>
    <automated>test -f kb/wiki/entities/openclaw.md && test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md && grep -q '^\^\[article:' kb/wiki/entities/openclaw.md && grep -q 'symlink\|ln -sfn' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md && grep -qi 'OpenClaw' kb/wiki/index.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/wiki/entities/openclaw.md` exits 0
    - `grep -q 'title: OpenClaw' kb/wiki/entities/openclaw.md` exits 0
    - `grep -q '^confidence_level:' kb/wiki/entities/openclaw.md` exits 0
    - `grep -E '\^\[article:[a-f0-9]{10}\]' kb/wiki/entities/openclaw.md` finds at least one match
    - `test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` exits 0
    - `grep -q 'WAIT for user confirmation' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` exits 0
    - `grep -q 'OpenClaw' kb/wiki/index.md` exits 0
    - No `ssh` invocation appears in agent's Bash history for this task
  </acceptance_criteria>
  <done>openclaw.md placeholder exists with valid frontmatter + citation; Hermes operator prompt for export + symlink generated; index.md and log.md updated.</done>
</task>

<task type="auto">
  <name>Task 3: Create empty test stubs for wiki test files (Wave 0 of VALIDATION.md)</name>
  <files>tests/unit/test_wiki_lint.py, tests/unit/test_wiki_centrality.py, tests/unit/test_wiki_citations.py, tests/integration/test_wiki_hook.py, tests/integration/test_wiki_generate.py, tests/integration/kb/test_synthesize_wiki_inject.py, tests/unit/kb/test_synthesize_wiki_fallthrough.py</files>
  <read_first>
    - .planning/phases/llm-wiki-integration/llm-wiki-VALIDATION.md (Wave 0 Requirements section — list of 7 test files)
    - tests/conftest.py (existing shared fixtures; do not duplicate)
  </read_first>
  <action>
    Create 7 empty pytest stub files, each containing one or more `@pytest.mark.skip("not implemented; W{N} fills in")` placeholder tests. Per VALIDATION.md Per-Task Verification Map, the test functions named below MUST exist as stubs so future waves can fill them without renaming.

    **`tests/unit/test_wiki_lint.py`** — stubs:
    ```python
    import pytest

    @pytest.mark.skip(reason="W3 will implement")
    def test_unresolved_citation():
        pass

    @pytest.mark.skip(reason="W3 will implement")
    def test_contradicts_existing():
        pass

    @pytest.mark.skip(reason="W3 will implement")
    def test_backlink_validity():
        pass

    @pytest.mark.skip(reason="W3 will implement")
    def test_staleness_check():
        pass
    ```

    **`tests/unit/test_wiki_centrality.py`** — single `test_centrality_ranking` stub skipped, "W1 will implement".

    **`tests/unit/test_wiki_citations.py`** — `test_all_pages_cited` stub skipped, "W1 will implement".

    **`tests/integration/test_wiki_hook.py`** — `test_end_of_cron_fires` stub skipped, "W3 will implement".

    **`tests/integration/test_wiki_generate.py`** — `test_one_entity_full` stub skipped, "W1 will implement".

    **`tests/integration/kb/test_synthesize_wiki_inject.py`** — create directory `tests/integration/kb/` if not exists (add `__init__.py` if other files in tests/integration/kb/ have one — check existing `tests/integration/kb/` dir state first). Stub: `test_wiki_context_injected_into_prompt` skipped, "W4 will implement".

    **`tests/unit/kb/test_synthesize_wiki_fallthrough.py`** — create directory `tests/unit/kb/` if not exists. Stub: `test_falls_through_when_wiki_missing` skipped, "W4 will implement".

    Each file must:
    - Start with `import pytest`
    - Have at least one test function defined
    - Use `@pytest.mark.skip(reason="...")` so pytest collects but skips them
    - Be importable (no syntax errors)
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_wiki_lint.py tests/unit/test_wiki_centrality.py tests/unit/test_wiki_citations.py tests/integration/test_wiki_hook.py tests/integration/test_wiki_generate.py tests/integration/kb/test_synthesize_wiki_inject.py tests/unit/kb/test_synthesize_wiki_fallthrough.py --collect-only 2>&1 | grep -E 'test_unresolved_citation|test_contradicts_existing|test_centrality_ranking|test_all_pages_cited|test_end_of_cron_fires|test_one_entity_full|test_wiki_context_injected_into_prompt|test_falls_through_when_wiki_missing'</automated>
  </verify>
  <acceptance_criteria>
    - All 7 stub files exist (`test -f` each)
    - `pytest --collect-only` on each file exits 0 (no import errors)
    - Each named test function is collected (visible in `--collect-only` output)
    - Running `pytest` on the 7 files reports them as SKIPPED (not failed, not passed)
  </acceptance_criteria>
  <done>7 empty test stub files exist; pytest collects all named tests; all marked skipped; downstream waves can replace skip markers with real assertions without renaming.</done>
</task>

</tasks>

<verification>
Phase-level verification for W0:
- `test -d kb/wiki/entities && test -d kb/wiki/concepts && test -d kb/wiki/comparisons && test -d kb/wiki/queries && test -d kb/wiki/_suggestions` exits 0
- `test -f kb/wiki/SCHEMA.md && test -f kb/wiki/index.md && test -f kb/wiki/log.md && test -f kb/wiki/README.md` exits 0
- `test -f kb/wiki/entities/openclaw.md && grep -E '\^\[article:[a-f0-9]{10}\]' kb/wiki/entities/openclaw.md` exits 0
- `test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` exits 0
- `venv/Scripts/python.exe -m pytest tests/unit/test_wiki_*.py tests/integration/test_wiki_*.py tests/integration/kb/test_synthesize_wiki_inject.py tests/unit/kb/test_synthesize_wiki_fallthrough.py --collect-only` exits 0 with at least 9 collected tests
</verification>

<success_criteria>
1. `kb/wiki/` directory tree exists in repo with all 5 subdirs and 4 top-level docs
2. `kb/wiki/entities/openclaw.md` exists with valid frontmatter + at least one `^[article:<hex10>]` citation
3. Hermes operator prompt for export + symlink at `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md`
4. 7 empty test stub files importable, pytest collects them as SKIPPED
5. No SSH command was issued from Bash tool during this plan
</success_criteria>

<output>
After completion, create `.planning/phases/llm-wiki-integration/llm-wiki-01-SUMMARY.md` capturing:
- Files created (full list)
- Hermes operator prompt path + when user should forward it (after W1 ships, OR before if openclaw.md content needed)
- Confirmation that openclaw.md is a placeholder (will be regenerated by W1 with real LightRAG synthesis)
- Test stubs collected count + skipped count
- Note: NO Local UAT required this wave — no kb/ runtime code changed; W3/W4 will trigger Local UAT per CLAUDE.md Rule 6
</output>
</content>
</invoke>