---
phase: llm-wiki-integration
plan: 05
type: execute
wave: 2
depends_on: ["llm-wiki-02"]
files_modified:
  - kb/services/synthesize.py                          # +wiki context injection (~40 LOC)
  - kb/services/wiki_inject.py                         # NEW helper (~30 LOC)
  - tests/unit/kb/test_synthesize_wiki_fallthrough.py  # fills W0 stub
  - tests/integration/kb/test_synthesize_wiki_inject.py # fills W0 stub
  - kb/wiki/log.md
  - .planning/phases/llm-wiki-integration/llm-wiki-VALIDATION.md  # NTH-1: flip nyquist_compliant after sign-off
autonomous: false   # Local UAT is now checkpoint:human-verify (Blocker 4 fix)
requirements:
  - WIKI-INJECT             # Decision (Wave 4) — synthesize prepends <wiki_context> block
  - WIKI-INJECT-LINT        # Decision 5 — read-time lint guard before inject
  - WIKI-NO-WRITEBACK       # Decision 4 — synthesize does NOT cache answers back to wiki
  - WIKI-FALLTHROUGH        # standard synthesize path when wiki absent / stale / lint fails
must_haves:
  truths:
    - "kb/services/synthesize.py reads kb/wiki/entities/<entity>.md if present and lint passes"
    - "Wiki content is prepended to LLM prompt as <wiki_context>...</wiki_context> block BEFORE LightRAG retrieval chunks"
    - "When wiki page is missing, stale, or fails lint: synthesize falls through to standard LightRAG-only path silently"
    - "Synthesize NEVER writes back to kb/wiki/ (Decision 4)"
    - "Local UAT exercised: query an entity with wiki page → response references wiki claims; query an entity without page → falls through cleanly"
  artifacts:
    - path: "kb/services/wiki_inject.py"
      provides: "Helper that resolves entity → wiki page path, runs read-time lint, returns wiki_context string or empty"
      exports: ["resolve_wiki_context", "extract_main_entity"]
    - path: "kb/services/synthesize.py"
      provides: "Modified synthesize path with wiki injection"
      contains: "wiki_inject"
  key_links:
    - from: "kb/services/synthesize.py"
      to: "kb/services/wiki_inject.py"
      via: "import + call before aquery"
      pattern: "from kb.services.wiki_inject import|wiki_inject\\."
    - from: "kb/services/wiki_inject.py"
      to: "kb/wiki_lint.py"
      via: "read-time lint subset (citation_integrity + staleness)"
      pattern: "from kb.wiki_lint|wiki_lint\\.lint_"
    - from: "kb/services/wiki_inject.py"
      to: "kb/wiki/entities/<slug>.md"
      via: "Path.read_text"
      pattern: "kb/wiki/entities|wiki_root"
---

<objective>
Modify `kb/services/synthesize.py` to look up an entity's wiki page (when present) and prepend its content as a `<wiki_context>` block to the LLM prompt before the LightRAG retrieval call. Read-time lint (citation integrity + staleness) gates the injection — if lint fails, fall through silently to standard synthesis. Per Decision 4, synthesize NEVER writes synthesized answers back to wiki.

Purpose: Realizes Decision 4 (no write-back) + Wave 4 of CONTEXT.md. Closes W4 / P3 of the wave structure.
Output: 1 new helper `kb/services/wiki_inject.py` (~30 LOC) + a small modification to `kb/services/synthesize.py` (~40 LOC) + 2 tests filling W0 stubs + Local UAT evidence.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md
@.planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md
@.planning/phases/llm-wiki-integration/llm-wiki-02-SUMMARY.md
@kb/services/synthesize.py
@kb/wiki/SCHEMA.md
@kb/wiki_lint.py
@./CLAUDE.md
@kb/docs/10-DESIGN-DISCIPLINE.md
</context>

<interfaces>
<!-- Existing kb/services/synthesize.py contracts (CRITICAL: read CURRENT state before editing per CONTEXT.md collision warning) -->

The kb-v2.2-7 parallel agent may modify kb/services/synthesize.py. The first read_first item in every task touching synthesize.py is "read current state of kb/services/synthesize.py immediately before editing".

Existing helper to reuse (per RESEARCH "Don't Hand-Roll"):
```python
# kb/services/synthesize.py
def _resolve_sources_from_markdown(md: str) -> list[str]:
    # regex: r'\/article\/([a-f0-9]{10})'
    # already handles citation resolution; do NOT re-implement
```

Existing async synthesize entry (placeholder; verify exact signature when reading):
```python
async def synthesize(question: str, mode: str = "long_form") -> dict:
    rag = await get_rag()
    result = await rag.aquery(question, param=QueryParam(mode="hybrid"))
    return {...}
```

Wiki inject contract (NEW — this plan defines):
```python
# kb/services/wiki_inject.py
def extract_main_entity(question: str) -> str | None:
    """Best-effort entity extraction. v1: lowercase + slug + match against known wiki pages.

    Returns slug if found; None if no match.
    """

async def resolve_wiki_context(question: str, wiki_root: Path = Path("kb/wiki"), max_age_days: int = 180) -> str:
    """Returns <wiki_context>...</wiki_context> block string if wiki page exists and lint passes; else returns ''."""
```

Read-time lint subset (from kb/wiki_lint.py — built in W3):
- `lint_citation_integrity(page_path, known_article_hashes)` — must return [] (all citations resolve)
- `lint_staleness(page_path, max_days=180)` — must return []
- (Skip backlink/contradiction at read-time — those are write-time concerns)

`<wiki_context>` block format (per CONTEXT.md Wave 4 implementation details):
```
<wiki_context>
# Entity wiki page content (raw markdown including frontmatter and citations)
</wiki_context>

[then standard LightRAG retrieval continues]
```

DB connection / config-driven path resolution (MEDIUM 3 fix — wiki_inject.py MUST use these patterns, not hardcoded paths):
- `config.py` exposes `BASE_DIR`, `RAG_WORKING_DIR`, and `KOL_SCAN_DB_PATH` (or equivalent). All path resolution MUST honor `OMNIGRAPH_BASE_DIR` env override.
- `kb/api.py` exposes the FastAPI app + DB connection helper used by other `kb/services/*` modules. wiki_inject.py SHOULD import the same helper rather than opening its own sqlite3 connection with a hardcoded path.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: kb/services/wiki_inject.py — entity extraction + read-time lint + context block</name>
  <files>kb/services/wiki_inject.py, tests/unit/kb/test_synthesize_wiki_fallthrough.py</files>
  <read_first>
    - kb/wiki_lint.py (W3 deliverable — citation_integrity + staleness functions to import)
    - kb/wiki/SCHEMA.md (frontmatter contract)
    - kb/services/synthesize.py (CURRENT state — to understand existing patterns; read-only here)
    - tests/unit/kb/test_synthesize_wiki_fallthrough.py (W0 stub — replace skip)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Example 3 — wiki-first lookup pseudocode)
    - **MEDIUM 3 fix**: config.py (BASE_DIR / RAG_WORKING_DIR / KOL_SCAN_DB_PATH resolution pattern; honors `OMNIGRAPH_BASE_DIR`)
    - **MEDIUM 3 fix**: kb/api.py (DB connection helper used by other kb/services/* — reference pattern for wiki_inject.py; do NOT hardcode sqlite3 paths)
  </read_first>
  <behavior>
    extract_main_entity(question):
    - Returns slug (str) if a known entity (one of `kb/wiki/entities/*.md` filenames without extension) appears in the question (case-insensitive substring match against the slug or its de-hyphenated form).
    - Returns None otherwise.
    - v1 is intentionally simple. LLM-based extraction deferred.

    resolve_wiki_context(question, wiki_root, max_age_days):
    - entity = extract_main_entity(question, wiki_root)
    - If entity is None → return ''
    - page = wiki_root / "entities" / f"{entity}.md"
    - If not page.exists() → return ''
    - Run lint_staleness(page, max_age_days); if non-empty → return '' (and log debug)
    - Run lint_citation_integrity(page, known_article_hashes); if non-empty → return '' (and log debug)
    - Else → return f"<wiki_context>\n{page.read_text()}\n</wiki_context>\n\n"

    NEVER raises. On any unexpected error, log debug + return ''.
  </behavior>
  <action>
    Create `kb/services/wiki_inject.py` with the 2 functions per <behavior>.

    Implementation:
    1. `extract_main_entity` — list `wiki_root/entities/*.md`, build slug set, lowercase the question, for each slug check if `slug in question` OR `slug.replace('-', ' ') in question`. Return first match or None. Document v1 limitation in docstring; future: integrate LightRAG entity extraction.
    2. `resolve_wiki_context` — async function (so the caller can `await`); but internal work is sync IO (file reads). Use `asyncio.to_thread` only if file IO becomes a bottleneck — for v1 keep synchronous reads inside the async function (acceptable for ≤20 wiki pages).
    3. **MEDIUM 3 fix — `known_article_hashes` MUST resolve DB path via config-driven helpers**, NOT a hardcoded `sqlite3.connect(".dev-runtime/data/kol_scan.db")` literal:
       - Import `BASE_DIR` (or `KOL_SCAN_DB_PATH` if available) from `config.py`. Resolve the SQLite DB path as `Path(os.environ.get("OMNIGRAPH_BASE_DIR", config.BASE_DIR)) / "data" / "kol_scan.db"` OR — preferred — reuse the connection helper already used by `kb/api.py` and other `kb/services/*` modules. Inspect `kb/api.py` to identify the canonical helper before writing this code.
       - Cache the resolved hash set via `functools.lru_cache(maxsize=1)` keyed on db path mtime to avoid re-querying every synthesize call.
       - Acceptance gate: `grep -qE '(BASE_DIR|RAG_WORKING_DIR|KOL_SCAN_DB_PATH|config\.|os\.environ\.get)' kb/services/wiki_inject.py` exits 0 (confirms config-driven resolution, not hardcoded literal).
    4. Total LOC budget: ≤ 30 (per CONTEXT.md Wave 4 budget split).

    **Replace W0 stub** in `tests/unit/kb/test_synthesize_wiki_fallthrough.py`:
    - `test_falls_through_when_wiki_missing`: tmp_path wiki root has empty entities/ dir; call `resolve_wiki_context("What is OpenClaw?", tmp_path, 180)` → assert returns ''.
    - `test_returns_context_block_when_page_valid` (additional): tmp_path has entities/openclaw.md with valid frontmatter + citation that resolves; mock known_article_hashes to include that hash; assert returns string starting with `<wiki_context>` and containing the page content.
    - `test_falls_through_when_stale`: page with `last_updated: 2020-01-01`; max_age_days=30; assert returns ''.
    - `test_falls_through_when_unresolved_citation`: page citation hash NOT in known_article_hashes set; assert returns ''.
    - `test_extract_main_entity_basic`: known entities = {"openclaw", "hermes-agent"}; question "Tell me about OpenClaw" → returns "openclaw"; question "Random unrelated query" → returns None.

    Tests must pin observable behavior (return value), not internal call shape. Hand-compute expected outputs.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/services/wiki_inject.py` exits 0
    - `grep -E '^def extract_main_entity|^async def resolve_wiki_context' kb/services/wiki_inject.py` shows 2 functions
    - `pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py -v` all 5 tests PASS (no skip remains)
    - kb/services/wiki_inject.py is ≤ 50 LOC (target ≤ 30)
    - `grep -q 'wiki_lint' kb/services/wiki_inject.py` exits 0 (lint imported, not re-implemented)
    - **MEDIUM 3 fix**: `grep -qE '(BASE_DIR|RAG_WORKING_DIR|KOL_SCAN_DB_PATH|config\.|os\.environ\.get)' kb/services/wiki_inject.py` exits 0 (confirms config-driven path resolution, not hardcoded literal sqlite path)
    - File never raises exceptions to caller (verify by inspection — try/except wraps the resolve function)
  </acceptance_criteria>
  <done>wiki_inject.py implements 2 functions, all 5 fallthrough tests PASS, lint subset wired in, config-driven DB path resolution (no hardcoded literals), no exceptions escape.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: kb/services/synthesize.py — inject wiki context before LightRAG aquery + integration test</name>
  <files>kb/services/synthesize.py, tests/integration/kb/test_synthesize_wiki_inject.py, kb/wiki/log.md</files>
  <read_first>
    - kb/services/synthesize.py (CRITICAL: read CURRENT state immediately before editing — kb-v2.2-7 parallel agent may have modified this file; per CONTEXT.md "Parallel agent on kb/" pitfall and CLAUDE.md `feedback_contract_shape_change_full_audit.md`)
    - kb/services/wiki_inject.py (just-built; this task imports it)
    - tests/integration/kb/test_synthesize_wiki_inject.py (W0 stub — replace skip)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Example 3 — wiki-first synthesize pseudocode)
  </read_first>
  <behavior>
    Modified synthesize() observable behavior:
    - When question references a known wiki entity AND lint passes: prompt sent to LLM contains `<wiki_context>...</wiki_context>` block before any LightRAG retrieval content.
    - When wiki resolution returns '' (any reason — missing, stale, lint fail, no entity match): prompt does NOT contain `<wiki_context>` tag; standard LightRAG-only path runs.
    - synthesize() return value structure unchanged (same dict keys; same response field).
    - synthesize() NEVER writes to kb/wiki/ — verify via filesystem mtime comparison before/after call.
    - synthesize() NEVER raises a new exception class — wiki resolution failures are silent fall-through.
  </behavior>
  <action>
    **Step A — Read current synthesize.py state**: use Read tool on `kb/services/synthesize.py` immediately before editing. Identify:
    1. The exact entry function (likely `async def synthesize(question, mode, ...)` or similar)
    2. The exact line/place where the LightRAG `aquery` is invoked
    3. The exact prompt-construction sequence (raw question → augmented prompt → aquery)

    **Step B — Add the import** at top of `kb/services/synthesize.py`:
    ```python
    from kb.services.wiki_inject import resolve_wiki_context
    ```

    **Step C — Inject wiki_context before aquery** at the prompt-construction site:
    ```python
    # W4 wiki context injection (llm-wiki-integration phase)
    # Per Decision 4: read-only injection; NO write-back to wiki.
    wiki_context = await resolve_wiki_context(question, wiki_root=Path("kb/wiki"), max_age_days=180)
    # wiki_context is either '' or '<wiki_context>...</wiki_context>\n\n'

    # Construct final prompt: wiki_context first, then existing prompt body
    final_prompt = wiki_context + existing_prompt_or_question
    ```

    The exact integration depends on what synthesize.py currently does. Two cases:

    Case A — synthesize calls `rag.aquery(question, ...)` directly: change to `rag.aquery(wiki_context + question, ...)` where wiki_context is '' on miss.

    Case B — synthesize builds a prompt template internally then calls aquery: prepend wiki_context to the template before the LightRAG call.

    Determine which case applies during Step A; document the chosen integration in the SUMMARY.

    **Step D — NO write-back**: explicitly do NOT add any `wiki_update` call after the response. Per Decision 4 — synthesize is read-only with respect to wiki.

    **Step E — Replace W0 stub** in `tests/integration/kb/test_synthesize_wiki_inject.py`:

    - `test_wiki_context_injected_into_prompt`: integration test that mocks `rag.aquery` to capture the prompt argument. tmp_path wiki root with entities/openclaw.md valid + lint-passing. Mock known_article_hashes set. Call `await synthesize("What is OpenClaw?")` → assert the captured prompt argument starts with `<wiki_context>` AND contains "OpenClaw".
    - `test_no_wiki_writeback`: snapshot mtime of `kb/wiki/entities/openclaw.md` before synthesize → call synthesize → assert mtime unchanged after (Decision 4 verification).
    - `test_falls_through_when_no_entity`: question with no known entity (e.g., "What is the meaning of life?") → assert prompt does NOT contain `<wiki_context>`.
    - `test_falls_through_when_lint_fails`: page exists but stale (last_updated 2020) → assert prompt does NOT contain `<wiki_context>`.

    These pin observable behavior — capture the prompt sent to aquery via mock, inspect, assert.

    **Step F — Append to `kb/wiki/log.md`**: `<ISO date> — W4 synthesize wiki context injection shipped (kb/services/wiki_inject.py + kb/services/synthesize.py modification)`.

    **CRITICAL — Surgical Changes (CLAUDE.md HIGHEST PRIORITY #3)**: do NOT touch any other code in synthesize.py. Do NOT improve adjacent code, comments, or formatting. Every changed line must trace to wiki context injection.

    **CRITICAL — feedback_skill_invocation_not_reference.md**: This plan does NOT need any specific Skill invocation since it's a small Python edit; no UI design, no complex refactoring. (`refactoring-code` Skill is unnecessary for ≤40 LOC of straightforward code.)
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/integration/kb/test_synthesize_wiki_inject.py -v && grep -q 'resolve_wiki_context' kb/services/synthesize.py && grep -q 'wiki_context' kb/services/synthesize.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from kb.services.wiki_inject import resolve_wiki_context' kb/services/synthesize.py` exits 0
    - `grep -c 'wiki_context' kb/services/synthesize.py` returns ≥ 2 (import + usage site)
    - `pytest tests/integration/kb/test_synthesize_wiki_inject.py::test_wiki_context_injected_into_prompt` PASSES
    - `pytest tests/integration/kb/test_synthesize_wiki_inject.py::test_no_wiki_writeback` PASSES
    - `pytest tests/integration/kb/test_synthesize_wiki_inject.py::test_falls_through_when_no_entity` PASSES
    - `pytest tests/integration/kb/test_synthesize_wiki_inject.py::test_falls_through_when_lint_fails` PASSES
    - `git diff kb/services/synthesize.py | grep '^+'` shows ≤ 50 added lines (surgical) (run in Git Bash)
    - `git diff kb/services/synthesize.py | grep '^-'` shows ≤ 5 removed lines (no rewrites) (run in Git Bash)
    - Existing synthesize tests (any pre-existing tests/integration/kb/test_synthesize*.py NOT named test_synthesize_wiki_*) still PASS — no regression
    - `tail -3 kb/wiki/log.md | grep -q 'W4 synthesize wiki context'` exits 0 (run in Git Bash)
  </acceptance_criteria>
  <done>synthesize.py prepends wiki_context to prompt; 4 integration tests PASS; no write-back; surgical change (LOC limit honored); no regression on existing synthesize tests.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Local UAT per CLAUDE.md Rule 6 — run kb local server + verify injection in prod-like flow</name>
  <what-built>End-to-end W4 wiki injection: start the local KB server, hit /api/synthesize with both a wiki-known entity and an unknown query, capture evidence, confirm Decision 4 (no write-back) holds. **Blocker 4 fix**: this task is now `checkpoint:human-verify` (was incorrectly `type="auto"` before). Bash-only idioms (`kill $LOCAL_SERVE_PID`, `LOCAL_SERVE_PID=$!`, `2>/dev/null`, glob `ls`) are NOT cross-platform on Windows PowerShell. The user runs this in Git Bash and pastes evidence back.</what-built>
  <how-to-verify>
    Per CLAUDE.md Rule 6 — Wave 5 of llm-wiki-integration touches `kb/services/synthesize.py`. Local UAT MUST run before this plan is marked complete.

    **Run all shell snippets below in Git Bash on Windows** (PowerShell does not support `$!`, `2>/dev/null`, or shell-glob `ls`).

    **Step 1 — Pre-flight tests** (Git Bash):
    ```bash
    venv/Scripts/python.exe -m pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py tests/integration/kb/test_synthesize_wiki_inject.py -v
    ```
    All GREEN before proceeding to live UAT.

    **Step 2 — Start local KB server** (per CLAUDE.md Rule 6 + kb/docs/10-DESIGN-DISCIPLINE.md). Run in Git Bash:
    ```bash
    venv/Scripts/python.exe .scratch/local_serve.py &
    LOCAL_SERVE_PID=$!
    sleep 3
    curl -sS http://localhost:8766/health
    ```

    Expected: HTTP 200 with health JSON.

    **Step 3 — Smoke synthesize endpoint with wiki-known entity** (Git Bash):
    Pick an entity slug from `kb/wiki/entities/*.md` (e.g., `openclaw`). Build a question that references it:
    ```bash
    mkdir -p .scratch/llm-wiki-05-uat-evidence
    curl -sS -X POST 'http://localhost:8766/api/synthesize?question=What+is+OpenClaw%3F&mode=long_form' \
      | tee .scratch/llm-wiki-05-uat-evidence/synth-openclaw-$(date +%Y%m%d-%H%M%S).json
    ```

    Verify response references content from the wiki page (any sentence from `kb/wiki/entities/openclaw.md` should be reflected in the synthesized answer, since wiki was injected as authoritative context).

    **Step 4 — Smoke synthesize endpoint without wiki entity** (Git Bash):
    ```bash
    curl -sS -X POST 'http://localhost:8766/api/synthesize?question=What+is+the+meaning+of+life%3F&mode=long_form' \
      | tee .scratch/llm-wiki-05-uat-evidence/synth-no-entity-$(date +%Y%m%d-%H%M%S).json
    ```

    Verify response is generated via fallthrough path (no wiki injection; no error).

    **Step 5 — Browser UAT** (per Rule 6 step 3):
    If KB has a UI surface for the synthesize endpoint, open it in a browser. Otherwise (synthesize is API-only), the curl evidence above is sufficient. Use Playwright MCP if any UI is involved:
    - Open `http://localhost:8766/` (or whichever route shows synthesize results)
    - Take screenshot to `.playwright-mcp/llm-wiki-05-uat-*.png`
    - Cite path

    **Step 6 — Inspect server logs** (per Rule 6 step 4):
    Check that the prompt sent to LLM contained `<wiki_context>` for the openclaw query. May require enabling DEBUG log on the synthesize path; if so, document the env var or log-level toggle in VERIFICATION.md.

    **Step 7 — Write `.planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md`** with a "## Local UAT" section containing:
    - Launcher used: `venv/Scripts/python.exe .scratch/local_serve.py` (run in Git Bash)
    - Env vars at run-time
    - curl smoke results: status code + key fields from each response
    - Screenshot paths (if UI involved)
    - Confirmation: openclaw query response references wiki content; no-entity query does not
    - Log evidence (or path to log file): `<wiki_context>` tag visible in prompt for openclaw query

    **Step 8 — Cleanup** (Git Bash):
    ```bash
    # Tear down local server. Run in Git Bash; the variable was set in Step 2.
    if [ -n "$LOCAL_SERVE_PID" ]; then kill "$LOCAL_SERVE_PID" 2>/dev/null || true; fi
    ```

    (Windows PowerShell equivalent if not in Git Bash: `Stop-Process -Id $LOCAL_SERVE_PID -ErrorAction SilentlyContinue` — but Git Bash is the canonical environment for this UAT.)

    **Step 9 — Confirm no wiki write-back** (Git Bash):
    ```bash
    git status kb/wiki/
    ```
    Should show NO modifications under `kb/wiki/` from the UAT (Decision 4 — no write-back). If any wiki page was modified, that's a Decision 4 violation; investigate and fix.

    **Step 10 — NTH-1 housekeeping**: After all 5 plans complete and the "Validation Sign-Off" checkboxes in `.planning/phases/llm-wiki-integration/llm-wiki-VALIDATION.md` are verified, update its frontmatter to set `nyquist_compliant: true` and `wave_0_complete: true`.

    **Resume signal expectations**: User pastes back curl outputs + paths to evidence files. Claude appends them to VERIFICATION.md and flips VALIDATION.md frontmatter as the final housekeeping action.
  </how-to-verify>
  <verify>
    <!-- Blocker 4 fix: cross-platform-safe verification using `test -f` for specific paths instead of bash `ls ... 2>/dev/null` glob. -->
    <automated>test -f .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md && grep -q '## Local UAT' .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md && test -d .scratch/llm-wiki-05-uat-evidence</automated>
  </verify>
  <acceptance_criteria>
    - `test -f .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md` exits 0
    - `grep -q '## Local UAT' .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md` exits 0
    - `grep -qi 'curl\|status' .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md` exits 0 (curl evidence cited)
    - `test -d .scratch/llm-wiki-05-uat-evidence` exits 0 (evidence dir created)
    - At least one openclaw evidence file exists. Cross-platform check (run in Git Bash): `find .scratch/llm-wiki-05-uat-evidence -name 'synth-openclaw-*.json' | head -1` returns at least 1 line.
    - At least one no-entity evidence file exists: `find .scratch/llm-wiki-05-uat-evidence -name 'synth-no-entity-*.json' | head -1` returns at least 1 line.
    - `git status kb/wiki/` shows no modifications attributable to the UAT (Decision 4 verification)
    - VERIFICATION.md notes "No write-back observed (Decision 4 satisfied)"
    - **NTH-1 fix**: `.planning/phases/llm-wiki-integration/llm-wiki-VALIDATION.md` frontmatter has `nyquist_compliant: true` and `wave_0_complete: true` after all 5 plans complete and Validation Sign-Off checkboxes are verified
  </acceptance_criteria>
  <resume-signal>
    User responds with one of:
    - "uat-passed" + paths to evidence files → Claude appends paths to llm-wiki-05-VERIFICATION.md, flips VALIDATION.md frontmatter (`nyquist_compliant: true`, `wave_0_complete: true`); plan COMPLETE
    - "uat-failed: <error>" → Claude diagnoses; if test/code bug, return to Task 2; if env issue, document in VERIFICATION.md and re-attempt
    - "skip-uat (justification: <reason>)" → discouraged per Rule 6; if accepted, document the justification clearly in VERIFICATION.md
  </resume-signal>
  <done>Local KB server exercised with both wiki-hit and wiki-miss queries; evidence captured in VERIFICATION.md per CLAUDE.md Rule 6; Decision 4 (no write-back) confirmed; VALIDATION.md frontmatter flipped to nyquist_compliant: true.</done>
</task>

</tasks>

<verification>
Phase-level verification for W4:
- `pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py tests/integration/kb/test_synthesize_wiki_inject.py -v` all PASS
- `grep -q 'resolve_wiki_context' kb/services/synthesize.py` exits 0
- `test -f kb/services/wiki_inject.py` exits 0
- `test -f .planning/phases/llm-wiki-integration/llm-wiki-05-VERIFICATION.md` exits 0
- VERIFICATION.md contains "## Local UAT" section per CLAUDE.md Rule 6
- `git diff kb/services/synthesize.py | grep '^+' | wc -l` ≤ ~50 (surgical) (Git Bash)
- No wiki page mtime changed during UAT (Decision 4 satisfied)
- VALIDATION.md frontmatter flipped to `nyquist_compliant: true` after sign-off (NTH-1)
</verification>

<success_criteria>
1. kb/services/wiki_inject.py exposes extract_main_entity + resolve_wiki_context; ≤30 LOC; config-driven DB path resolution (no hardcoded literals)
2. kb/services/synthesize.py has the wiki-context prepend; ≤40 LOC change; no other modifications
3. 5 fallthrough unit tests + 4 injection integration tests all PASS
4. Local UAT performed (checkpoint:human-verify, Git-Bash-driven) and cited per CLAUDE.md Rule 6
5. Decision 4 confirmed: synthesize never writes to kb/wiki/ (mtime check during UAT)
6. No regression on existing kb/services/synthesize.py tests
7. VALIDATION.md frontmatter `nyquist_compliant` flipped to true after sign-off (NTH-1)
8. Total LOC for plan ≤ ~70 (kb/services/wiki_inject.py + synthesize.py mod)
</success_criteria>

<output>
After completion, create `.planning/phases/llm-wiki-integration/llm-wiki-05-SUMMARY.md` capturing:
- Files created (kb/services/wiki_inject.py) + modified (kb/services/synthesize.py)
- LOC counts
- Integration approach used (Case A inline prepend or Case B template-based) + why
- DB path resolution strategy actually used in wiki_inject.py (config.BASE_DIR vs kb/api.py helper) — MEDIUM 3 fix
- Test counts: 5 fallthrough unit + 4 injection integration = 9 new tests
- Local UAT log paths + summary of UAT results (per CLAUDE.md Rule 6)
- Confirmation: Decision 4 satisfied (no write-back observed)
- Confirmation: synthesize.py current state was read immediately before edit (per CONTEXT.md collision warning re kb-v2.2-7)
- Confirmation: VALIDATION.md frontmatter `nyquist_compliant` flipped to true
- Any discrepancies vs original synthesize.py structure if kb-v2.2-7 changed it (and how integration was adjusted)
</output>
</content>
