---
phase: 260515-cvh
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/services/synthesize.py
  - kb/static/qa.js
  - kb/static/search.js
  - kb/static/VitaClaw-Logo-v0.png
  - tests/integration/kb/test_qa_link_contract.py
  - tests/unit/kb/test_synthesize_hotfix.py
  - .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md
  - .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md
  - .planning/STATE.md
autonomous: true
requirements:
  - HOTFIX-QA-LINK
  - HOTFIX-FALLBACK-STATE
  - HOTFIX-SEARCH-RETRY
  - HOTFIX-KG-CHIP-BACKFILL
  - HOTFIX-LOGO-CARRY
  - HOTFIX-RUNBOOK

must_haves:
  truths:
    - "Q&A source chip click resolves to {KB_BASE_PATH}/articles/{hash}.html and never to /article/{hash}.html"
    - "qa.js sets data-qa-state='fts5_fallback' (never bare 'fallback') on both timeout and fallback_used=true paths"
    - "Search input retries with no lang filter when locale-filtered query returns 0 items, and shows results from the other language"
    - "kb_synthesize KG-happy-path populates result.sources via FTS fallback when markdown lacks /article/{hash} refs, and result.entities via _entity_candidates"
    - "kb/static/VitaClaw-Logo-v0.png exists at 470KB with sha256=2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54"
    - "tests/integration/kb/test_qa_link_contract.py + tests/unit/kb/test_synthesize_hotfix.py both pass"
    - "SSG re-render succeeds for KB_BASE_PATH unset AND KB_BASE_PATH=/kb without errors"
    - "Single atomic commit on origin/main with explicit file list (no git add -A); commit message documents hero-strip deferral + PNG sha256 mismatch + Skill invocations"
    - "RUNBOOK.md gives Aliyun operator both Path A (preserve hero-strip via hot-patch sync) and Path B (full re-export, accepts hero-strip loss) with explicit warnings"
  artifacts:
    - path: "kb/services/synthesize.py"
      provides: "_ENTITY_HINTS tuple, _dedupe, _fallback_search_terms, _source_hashes_from_fts, _entity_candidates helpers + 2 wiring sites in _fts5_fallback and kb_synthesize happy path"
      contains: "_ENTITY_HINTS"
    - path: "kb/static/qa.js"
      provides: "fixed source chip link path + fts5_fallback state name (2 sites)"
      contains: "/articles/"
    - path: "kb/static/search.js"
      provides: "buildSearchUrl + fetchSearch helpers + cross-language retry on empty results"
      contains: "fetchSearch"
    - path: "kb/static/VitaClaw-Logo-v0.png"
      provides: "UI-04 logo carry-forward (already copied by orchestrator)"
    - path: "tests/integration/kb/test_qa_link_contract.py"
      provides: "Regression test pinning qa.js link contract + state name (closes kb-3-12 gap)"
    - path: "tests/unit/kb/test_synthesize_hotfix.py"
      provides: "Unit tests for _dedupe / _fallback_search_terms / _entity_candidates / _ENTITY_HINTS immutability"
    - path: ".planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md"
      provides: "Aliyun operator runbook with Path A (sync) and Path B (re-export) flows"
    - path: ".planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md"
      provides: "Quick closure doc with verbatim Skill(skill=...) invocations for discipline regex"
      contains: "Skill(skill=\"python-patterns\""
  key_links:
    - from: "kb/static/qa.js renderSources"
      to: "kb/templates/article.html (path /articles/{hash}.html)"
      via: "anchor href = (window.KB_BASE_PATH || '') + '/articles/' + hash + '.html'"
      pattern: "/articles/' \\+ encodeURIComponent\\(hash\\)"
    - from: "kb/static/qa.js pollOnce timeout/fallback branches"
      to: "style.css [data-qa-state='fts5_fallback'] selector (UI-SPEC §3.2 D-8)"
      via: "setState('fts5_fallback')"
      pattern: "setState\\('fts5_fallback'\\)"
    - from: "kb/services/synthesize.py kb_synthesize happy path"
      to: "qa.js renderSources / renderEntities consumers"
      via: "result.sources = _source_hashes_from_fts(question) when markdown empty; result.entities = _entity_candidates(question, markdown)"
      pattern: "_source_hashes_from_fts|_entity_candidates"
    - from: "kb/static/search.js runSearch"
      to: "/api/search?mode=fts (no lang param on retry)"
      via: "fetchSearch(q, null) when first response items.length === 0 and lang was set"
      pattern: "fetchSearch\\(q, null\\)"
---

<objective>
Land 4 hotfixes that the vitaclaw-site go-live agent applied directly on Aliyun production into origin/main as one atomic commit, with regression tests + Aliyun operator runbook.

Purpose: Close 4 production-traceable defects (Q&A 404 on source chip click, CSS contract drift on fallback state, empty-state UX on cross-language search, KG happy-path missing source/entity chips) and carry the UI-04 logo forward — without bringing along the deferred hero-strip migration.

Output: Patched code + new tests + RUNBOOK + SUMMARY + STATE update + atomic commit pushed to origin/main.

Out of scope (DO NOT implement):
- Hero-image-strip template migration (deferred to v2.1 backlog `kb-templates-index-hero-strip-migration`)
- Replacing _ENTITY_HINTS hardcoded list with proper LightRAG entity_canonical query (v2.1 backlog)
- Changing C1 contract (kg_synthesize.synthesize_response signature read-only per KB-v2)
- Refactoring search.js further beyond the 3-helper extraction
- Touching kb/output/ build artifacts (regenerated by export driver)
- Aliyun-side ops (covered by RUNBOOK deliverable)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@.planning/STATE.md
@kb/services/synthesize.py
@kb/static/qa.js
@kb/static/search.js

<patch_to_apply>
The patch is committed below as a heredoc. Save to /tmp/kb-go-live-hotfix.patch then `git apply --check`. If --check passes, `git apply`. If --check fails (line drift), use `git apply -3` for 3-way merge or apply hunks manually.

```
cat > /tmp/kb-go-live-hotfix.patch <<'PATCH_END'
diff --git a/kb/services/synthesize.py b/kb/services/synthesize.py
index 862f67f..baa8de0 100644
--- a/kb/services/synthesize.py
+++ b/kb/services/synthesize.py
@@ -89,6 +89,71 @@ def _extract_source_hashes(markdown: str) -> list[str]:
     return sorted({m for m in _SOURCE_HASH_PATTERN.findall(markdown)})


+_ENTITY_HINTS: tuple[str, ...] = (
+    "AI Agent",
+    "LangGraph",
+    "LangChain",
+    "CrewAI",
+    "RAG",
+    "MCP",
+    "OpenAI",
+    "Claude Code",
+    "Claude",
+    "DeepSeek",
+    "LightRAG",
+    "Agent",
+)
+
+
+def _dedupe(items: list[str]) -> list[str]:
+    seen: set[str] = set()
+    out: list[str] = []
+    for item in items:
+        key = item.lower()
+        if key in seen:
+            continue
+        seen.add(key)
+        out.append(item)
+    return out
+
+
+def _fallback_search_terms(question: str) -> list[str]:
+    """Return broad FTS terms for source chips when the KG markdown has no links."""
+    q = (question or "").strip()
+    lower = q.lower()
+    terms: list[str] = []
+    if q:
+        terms.append(q)
+    if "ai" in lower and "agent" in lower:
+        terms.append("AI Agent")
+    if "agent" in lower:
+        terms.append("Agent")
+    for hint in _ENTITY_HINTS:
+        if hint.lower() in lower:
+            terms.append(hint)
+    return _dedupe(terms)
+
+
+def _source_hashes_from_fts(question: str, limit: int = 3) -> list[str]:
+    """Best-effort source chips for KG answers that omit explicit source links."""
+    try:
+        from kb.services.search_index import fts_query
+
+        for term in _fallback_search_terms(question):
+            rows = fts_query(term, lang=None, limit=limit)
+            if rows:
+                return [h for h, _title, _snippet, _lg, _source in rows]
+    except Exception:
+        return []
+    return []
+
+
+def _entity_candidates(question: str, markdown: str) -> list[str]:
+    """Small visible entity list for the UI chip surface; not a KG canonicalizer."""
+    haystack = ((question or "") + "\n" + (markdown or "")).lower()
+    return [hint for hint in _ENTITY_HINTS if hint.lower() in haystack][:8]
+
+
 def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
     """QA-05: FTS5 top-3 fallback when LightRAG synthesis fails or times out.

@@ -108,7 +173,11 @@ def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
         # Lazy import — keeps module-import cheap and lets tests monkeypatch.
         from kb.services.search_index import fts_query

-        rows = fts_query(question, lang=None, limit=3)
+        rows = []
+        for term in _fallback_search_terms(question):
+            rows = fts_query(term, lang=None, limit=3)
+            if rows:
+                break
         if not rows:
             markdown = (
                 "> Note: 暂时无法生成完整回答 / Synthesis temporarily unavailable.\n\n"
@@ -197,6 +266,8 @@ async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
     # Happy path: C1 wrote synthesis_output.md; read it back.
     markdown = _read_synthesis_output()
     sources = _extract_source_hashes(markdown)
+    if not sources:
+        sources = _source_hashes_from_fts(question)
     job_store.update_job(
         job_id,
         status="done",
@@ -204,7 +275,7 @@ async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
             "markdown": markdown,
             "sources": sources,
             # v2.0 minimum-viable; v2.1 may extend via canonicalization.
-            "entities": [],
+            "entities": _entity_candidates(question, markdown),
         },
         fallback_used=False,
         confidence="kg",
diff --git a/kb/static/qa.js b/kb/static/qa.js
index a11b493..5fce9e8 100644
--- a/kb/static/qa.js
+++ b/kb/static/qa.js
@@ -90,7 +90,7 @@
       var li = document.createElement('li');
       li.className = 'qa-source-chip';
       var a = document.createElement('a');
-      a.href = '/article/' + encodeURIComponent(hash) + '.html';
+      a.href = (window.KB_BASE_PATH || '') + '/articles/' + encodeURIComponent(hash) + '.html';
       a.target = '_blank';
       a.rel = 'noopener';
       a.className = 'qa-source-link';
@@ -173,7 +173,7 @@
       setState('timeout');
       // Auto-transition to fts5_fallback after 500ms (UI-SPEC §3.2 D-8)
       setTimeout(function () {
-        setState('fallback');
+        setState('fts5_fallback');
       }, 500);
       clearPoll();
       return;
@@ -196,7 +196,7 @@
         if (data.status === 'done') {
           var fallback = data.fallback_used === true;
           if (fallback) {
-            setState('fallback');
+            setState('fts5_fallback');
           } else {
             setState('done');
           }
diff --git a/kb/static/search.js b/kb/static/search.js
index bb2d330..27f7409 100644
--- a/kb/static/search.js
+++ b/kb/static/search.js
@@ -181,18 +181,39 @@
     resultsEl.innerHTML = html;
   }

-  function runSearch(q) {
-    if (inFlight) inFlight.abort();
-    inFlight = (typeof AbortController === 'function') ? new AbortController() : null;
-    showLoading();
+  function buildSearchUrl(q, lang) {
     var url = (window.KB_BASE_PATH || '') + '/api/search?q=' + encodeURIComponent(q)
       + '&mode=fts'
-      + '&lang=' + encodeURIComponent(getLang())
       + '&limit=' + FETCH_LIMIT;
-    fetch(url, { signal: inFlight ? inFlight.signal : undefined, headers: { 'Accept': 'application/json' } })
+    if (lang) url += '&lang=' + encodeURIComponent(lang);
+    return url;
+  }
+
+  function fetchSearch(q, lang) {
+    return fetch(buildSearchUrl(q, lang), {
+      signal: inFlight ? inFlight.signal : undefined,
+      headers: { 'Accept': 'application/json' }
+    })
       .then(function (r) {
         if (!r.ok) throw new Error('HTTP ' + r.status);
         return r.json();
+      });
+  }
+
+  function runSearch(q) {
+    if (inFlight) inFlight.abort();
+    inFlight = (typeof AbortController === 'function') ? new AbortController() : null;
+    showLoading();
+    var lang = getLang();
+    fetchSearch(q, lang)
+      .then(function (data) {
+        // Locale-filtered search is useful for bilingual browsing, but ASCII
+        // tech terms such as "langchain" often only exist in the other language.
+        // Retry once without lang before showing an empty state.
+        if ((!data.items || data.items.length === 0) && lang) {
+          return fetchSearch(q, null);
+        }
+        return data;
       })
       .then(function (data) {
         renderItems(data.items || [], data.total || 0, q);
PATCH_END
```

</patch_to_apply>

<runbook_spec>
RUNBOOK.md must give the Aliyun operator BOTH paths with explicit warnings:

**Path A — Hot-patch sync (preserves Aliyun's hero-strip):**
- rsync only the 4 changed files (synthesize.py, qa.js, search.js, VitaClaw-Logo-v0.png) into the Aliyun deploy dir
- DO NOT re-run `kb/export_knowledge_base.py` (would clobber hero-strip in index.html)
- Restart uvicorn / kb service
- Verify: visit /ask, submit a question, click a source chip → should land on /articles/{hash}.html (not /article/{hash}.html, not 404)

**Path B — Full re-export (accepts hero-strip loss):**
- Pull origin/main on Aliyun
- Run `kb/export_knowledge_base.py` (regenerates kb/output/ from templates — hero-strip in index.html will be lost since templates don't have it)
- Restart uvicorn / kb service
- WARNING: hero-strip on homepage will disappear; documented as known regression to be re-added in v2.1 via `kb-templates-index-hero-strip-migration` backlog item
- This path is the standard, lower-risk-of-drift option for ops who don't need hero-strip preserved

**PNG sha256 note (both paths):**
- The committed kb/static/VitaClaw-Logo-v0.png has sha256=2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54 (470KB, 2048x2048 RGBA)
- This is NOT byte-identical to the Aliyun production blob (3c827d3...). It is a re-encoded but visually equivalent PNG.
- If Aliyun ops cares about byte-identity, they should keep the existing Aliyun PNG and skip syncing the new one.
</runbook_spec>

<commit_message_spec>
Atomic commit message must include:

```
fix(kb): land 4 Aliyun go-live hotfixes (qa.js link + state, search retry, KG chip backfill, logo)

Hotfixes applied directly on Aliyun production by vitaclaw-site go-live agent
on 2026-05-15; this commit lands them into origin/main.

1. kb/static/qa.js — source chip link path (/article/ → /articles/, add KB_BASE_PATH);
   fallback state name (bare 'fallback' → 'fts5_fallback' per UI-SPEC §3.2 + CSS contract)
2. kb/static/search.js — cross-language retry when locale-filtered search returns 0 items
3. kb/services/synthesize.py — KG-happy-path source/entity chip backfill via FTS fallback
   (75-line addition; v2.0 minimum-viable workaround for C1 read-only contract)
4. kb/static/VitaClaw-Logo-v0.png — UI-04 carry-forward

Tests added:
- tests/integration/kb/test_qa_link_contract.py (closes kb-3-12 test gap)
- tests/unit/kb/test_synthesize_hotfix.py (covers 4 new helpers)

Skills invoked (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):
- Skill(skill="python-patterns", args="...")  # see SUMMARY.md verbatim
- Skill(skill="writing-tests", args="...")     # see SUMMARY.md verbatim

Notes:
- Hero-image-strip migration deferred to v2.1 backlog
  `kb-templates-index-hero-strip-migration` — go-live agent added it directly
  to Aliyun's index.html outside the template; template-side migration is its
  own quick.
- PNG sha256=2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54
  (470KB, 2048x2048 RGBA) does NOT match Aliyun production blob (3c827d3...).
  Re-encoded but visually equivalent. Operator RUNBOOK documents this.
- _ENTITY_HINTS is a v2.0 minimum-viable hardcoded list. v2.1 backlog will
  replace with extracted_entities table join or LightRAG entity_canonical.
```
</commit_message_spec>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Apply patch + python-patterns polish on synthesize.py</name>
  <files>
    kb/services/synthesize.py
    kb/static/qa.js
    kb/static/search.js
  </files>
  <behavior>
    After this task:
    - synthesize.py defines `_ENTITY_HINTS: tuple[str, ...]` with ≥8 items, plus `_dedupe`, `_fallback_search_terms`, `_source_hashes_from_fts`, `_entity_candidates` helpers
    - synthesize.py `_fts5_fallback` iterates `_fallback_search_terms(question)` and breaks on first non-empty rows
    - synthesize.py `kb_synthesize` happy path falls back to `_source_hashes_from_fts(question)` when `_extract_source_hashes(markdown)` is empty, AND populates `entities` via `_entity_candidates(question, markdown)`
    - synthesize.py contains the v2.0 inline comment block above `_ENTITY_HINTS` documenting v2.1 backlog reference
    - synthesize.py `_source_hashes_from_fts` has the upgraded thorough docstring
    - qa.js renderSources uses `(window.KB_BASE_PATH || '') + '/articles/' + encodeURIComponent(hash) + '.html'` (NOT `/article/`)
    - qa.js setState in BOTH timeout (line ~176) AND fallback_used branch (line ~199) uses `'fts5_fallback'` (NOT bare `'fallback'`)
    - search.js extracts `buildSearchUrl(q, lang)` + `fetchSearch(q, lang)` helpers, and runSearch retries once with `lang=null` if first response is empty AND lang was set
    - All existing _extract_source_hashes / _fts5_fallback / kb_synthesize signatures unchanged (no breaking change to C1 contract or kb-3-09 wrapper contract)
  </behavior>
  <action>
    Step 1 — Save patch and apply:

    1. Write the heredoc patch (verbatim from `<patch_to_apply>` above) to `/tmp/kb-go-live-hotfix.patch`
    2. Run `git apply --check /tmp/kb-go-live-hotfix.patch` from repo root
    3. If --check passes: `git apply /tmp/kb-go-live-hotfix.patch`
    4. If --check fails (line-number drift): try `git apply -3 /tmp/kb-go-live-hotfix.patch` for 3-way merge; if still fails, apply each of the 3 file diffs hunk-by-hunk manually using Edit tool. Do NOT modify patch content — only adjust line numbers.

    Step 2 — Invoke python-patterns Skill verbatim (REQUIRED for discipline regex):

    Skill(skill="python-patterns", args="Review kb/services/synthesize.py 75-line hotfix for idiomatic Python (immutable tuple OK, lazy import OK, try/except scope appropriate). Add inline comment marking _ENTITY_HINTS as v2.0 minimum-viable + v2.1 backlog reference. Confirm no breaking change to existing _extract_source_hashes / _fts5_fallback contracts.")

    Step 3 — Apply the 2 polish edits to synthesize.py per task spec Step 3:

    (a) Insert this 5-line comment block IMMEDIATELY ABOVE `_ENTITY_HINTS: tuple[str, ...] = (`:
    ```
    # v2.0 minimum-viable hardcoded list — covers most-asked entities for UI chip surface.
    # v2.1 backlog: replace with systematic entity source resolution from
    # extracted_entities table joined to KG result articles, OR from LightRAG
    # entity_canonical lookup. C1 contract is read-only; resolution stays in this
    # wrapper.
    ```

    (b) Replace the bare `_source_hashes_from_fts` docstring (the single-line `"""Best-effort source chips for KG answers that omit explicit source links."""`) with the thorough multi-line version from task spec Step 3(b).

    Step 4 — Sanity verify the 3 file changes locally:
    - `grep -n "_ENTITY_HINTS\|_fallback_search_terms\|_entity_candidates\|_dedupe\|_source_hashes_from_fts" kb/services/synthesize.py` should show ALL 5 names defined + at least 2 use sites in `_fts5_fallback` and `kb_synthesize`
    - `grep -n "/articles/\|fts5_fallback\|/article/" kb/static/qa.js` should show 1 `/articles/` hit, 2 `setState('fts5_fallback')` hits, ZERO bare `setState('fallback')` hits
    - `grep -n "buildSearchUrl\|fetchSearch" kb/static/search.js` should show both helpers defined + used in runSearch retry chain

    Do NOT touch any other files. Do NOT run the export driver yet (Task 4).
  </action>
  <verify>
    <automated>
    grep -q "_ENTITY_HINTS: tuple" kb/services/synthesize.py && \
    grep -q "v2.0 minimum-viable hardcoded list" kb/services/synthesize.py && \
    grep -q "_source_hashes_from_fts(question)" kb/services/synthesize.py && \
    grep -q "_entity_candidates(question, markdown)" kb/services/synthesize.py && \
    grep -q "/articles/' + encodeURIComponent" kb/static/qa.js && \
    grep -c "setState('fts5_fallback')" kb/static/qa.js | grep -q "^2$" && \
    ! grep -q "setState('fallback')" kb/static/qa.js && \
    grep -q "function fetchSearch" kb/static/search.js && \
    grep -q "fetchSearch(q, null)" kb/static/search.js && \
    venv/Scripts/python.exe -c "import ast; ast.parse(open('kb/services/synthesize.py').read())" && \
    echo "TASK 1 PASS"
    </automated>
  </verify>
  <done>
    All 5 grep checks above pass; synthesize.py parses cleanly via ast; python-patterns Skill was invoked with the verbatim args string from Step 2 (will be cited in SUMMARY.md by Task 5).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add regression tests (writing-tests Skill)</name>
  <files>
    tests/integration/kb/test_qa_link_contract.py
    tests/unit/kb/test_synthesize_hotfix.py
  </files>
  <behavior>
    After this task:
    - test_qa_link_contract.py exists with 3 mock-free string-assertion tests against qa.js source: source chip uses /articles/ plural, link includes KB_BASE_PATH, state name is 'fts5_fallback' (not bare 'fallback')
    - test_synthesize_hotfix.py exists with 7 unit tests covering: _ENTITY_HINTS immutability + min length, _dedupe case-insensitive + edge cases, _fallback_search_terms includes question + handles empty/None + AI Agent special case, _entity_candidates matches both question and markdown haystack + capped at 8
    - Both files run under pytest with no monkeypatching of synthesize.py imports
    - Both files pass when run together via `pytest tests/integration/kb/test_qa_link_contract.py tests/unit/kb/test_synthesize_hotfix.py -v`
  </behavior>
  <action>
    Step 1 — Invoke writing-tests Skill verbatim (REQUIRED for discipline regex):

    Skill(skill="writing-tests", args="Testing Trophy: regression > unit. Mock-free tests reading qa.js source as string + asserting required patterns present, forbidden patterns absent. Unit tests for _dedupe / _fallback_search_terms / _entity_candidates pure functions.")

    Step 2 — Create `tests/integration/kb/test_qa_link_contract.py` with EXACT contents from task spec Step 4 (3 tests: test_source_chip_path_uses_articles_plural, test_source_chip_path_includes_kb_base_path, test_state_name_is_fts5_fallback). Verify the parent directory exists (`tests/integration/kb/` should already exist from kb-3); if missing, create it.

    Step 3 — Create `tests/unit/kb/test_synthesize_hotfix.py` with EXACT contents from task spec Step 4 (7 tests covering _ENTITY_HINTS / _dedupe / _fallback_search_terms / _entity_candidates). Verify `tests/unit/kb/` exists.

    Step 4 — Run only the 2 new test files to confirm green:
    `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m pytest tests/integration/kb/test_qa_link_contract.py tests/unit/kb/test_synthesize_hotfix.py -v 2>&1 | tail -20`

    Step 5 — Optional smoke (non-blocking): full pytest suite to confirm failure count remains 51 pre-existing (no new regressions introduced). Do NOT block task completion on full-suite count.

    Do NOT modify any production code in this task. Do NOT add additional test cases beyond the spec — the task spec EXACTLY specifies which tests to add.
  </action>
  <verify>
    <automated>
    test -f tests/integration/kb/test_qa_link_contract.py && \
    test -f tests/unit/kb/test_synthesize_hotfix.py && \
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m pytest tests/integration/kb/test_qa_link_contract.py tests/unit/kb/test_synthesize_hotfix.py -v 2>&1 | tee /tmp/pytest-260515-cvh.log | tail -3 && \
    grep -E "passed|failed" /tmp/pytest-260515-cvh.log | tail -1 | grep -qE "10 passed" && \
    echo "TASK 2 PASS — 10 tests green (3 integration + 7 unit)"
    </automated>
  </verify>
  <done>
    Both test files exist, all 10 tests pass when run together, writing-tests Skill was invoked with the verbatim args string (will be cited in SUMMARY.md by Task 5).
  </done>
</task>

<task type="auto">
  <name>Task 3: Verify PNG carry-forward + SSG re-render (no regression gate)</name>
  <files>
    kb/static/VitaClaw-Logo-v0.png (verify only — already present)
  </files>
  <action>
    Step 1 — Verify PNG present at expected size and sha256:

    `ls -lh kb/static/VitaClaw-Logo-v0.png` — expect ~470K (NOT 1.3MB; the orchestrator copy is documented to differ from Aliyun production blob)
    `sha256sum kb/static/VitaClaw-Logo-v0.png` — expect `2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54`

    If either check fails, STOP — escalate to user. The orchestrator was supposed to copy the file before this quick fired.

    Step 2 — Re-render SSG twice (KB_BASE_PATH unset + KB_BASE_PATH=/kb) to verify no template breakage from changed JS files:

    Run A:
    `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py 2>&1 | tail -5`

    Run B:
    `KB_DB_PATH=.dev-runtime/data/kol_scan.db KB_BASE_PATH=/kb venv/Scripts/python.exe kb/export_knowledge_base.py 2>&1 | tail -5`

    Both runs must complete without error (last line should be a success indicator, not a Python traceback).

    Step 3 — Verify no CSS regression (no edits made; numbers should be unchanged):
    - `grep -cE "^\s*--[a-z-]+:" kb/static/style.css` — expect 31
    - `wc -l < kb/static/style.css` — expect ≤ 2200

    These are tripwires: if either count drifted, an unexpected edit slipped in — investigate before proceeding to Task 4.
  </action>
  <verify>
    <automated>
    test -f kb/static/VitaClaw-Logo-v0.png && \
    [ "$(stat -c %s kb/static/VitaClaw-Logo-v0.png 2>/dev/null || stat -f %z kb/static/VitaClaw-Logo-v0.png)" -gt 400000 ] && \
    [ "$(stat -c %s kb/static/VitaClaw-Logo-v0.png 2>/dev/null || stat -f %z kb/static/VitaClaw-Logo-v0.png)" -lt 600000 ] && \
    sha256sum kb/static/VitaClaw-Logo-v0.png 2>/dev/null | grep -q "2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54" && \
    KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py > /tmp/ssg-a.log 2>&1 && \
    KB_DB_PATH=.dev-runtime/data/kol_scan.db KB_BASE_PATH=/kb venv/Scripts/python.exe kb/export_knowledge_base.py > /tmp/ssg-b.log 2>&1 && \
    ! grep -qE "Traceback|Error" /tmp/ssg-a.log && \
    ! grep -qE "Traceback|Error" /tmp/ssg-b.log && \
    echo "TASK 3 PASS"
    </automated>
  </verify>
  <done>
    PNG verified at expected size + sha256, SSG re-renders without error in both KB_BASE_PATH modes, CSS counts unchanged.
  </done>
</task>

<task type="auto">
  <name>Task 4: Write RUNBOOK.md + SUMMARY.md + STATE.md update</name>
  <files>
    .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md
    .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md
    .planning/STATE.md
  </files>
  <action>
    Step 1 — Write RUNBOOK.md per `<runbook_spec>` in context section:
    - Title + 2026-05-15 date + author note
    - Path A (hot-patch sync, preserves hero-strip): explicit rsync command of 4 files only, DO NOT re-export, restart service, click-test source chip
    - Path B (full re-export, accepts hero-strip loss): pull main, run kb/export_knowledge_base.py, restart, WARNING about hero-strip
    - PNG sha256 note shared by both paths (470KB blob is re-encoded, not byte-identical to Aliyun's 1.3MB; ops can keep theirs if byte-identity matters)
    - Recommendation: Path B is the lower-risk-of-drift default; Path A only if hero-strip preservation is critical

    Step 2 — Write SUMMARY.md (quick closure doc) with these MANDATORY sections:
    - "## Mission" — one-paragraph mission summary
    - "## Files Changed" — list 4 prod files + 2 test files + 3 planning files
    - "## Skill Invocations" — MUST contain the EXACT verbatim Skill call strings (including double quotes around skill names) so the discipline regex matches:
      - `Skill(skill="python-patterns", args="Review kb/services/synthesize.py 75-line hotfix for idiomatic Python (immutable tuple OK, lazy import OK, try/except scope appropriate). Add inline comment marking _ENTITY_HINTS as v2.0 minimum-viable + v2.1 backlog reference. Confirm no breaking change to existing _extract_source_hashes / _fts5_fallback contracts.")`
      - `Skill(skill="writing-tests", args="Testing Trophy: regression > unit. Mock-free tests reading qa.js source as string + asserting required patterns present, forbidden patterns absent. Unit tests for _dedupe / _fallback_search_terms / _entity_candidates pure functions.")`
    - "## Tests Added" — count + names + pass evidence (cite /tmp/pytest-260515-cvh.log row)
    - "## Out of Scope" — bullet list (hero-strip → v2.1 backlog kb-templates-index-hero-strip-migration; _ENTITY_HINTS replacement → v2.1 backlog; C1 contract unchanged; search.js no further refactor; kb/output/ untouched; Aliyun-side ops covered by RUNBOOK)
    - "## PNG sha256 mismatch" — explicit note (committed=2c71bdf..., Aliyun=3c827d3..., re-encoded but visually equivalent)
    - "## Verify Evidence" — cite /tmp/ssg-a.log, /tmp/ssg-b.log, /tmp/pytest-260515-cvh.log
    - "## Next Steps" — operator follows RUNBOOK on Aliyun

    Step 3 — Append entry to .planning/STATE.md "Recent activity" / "Quick log" section (use existing convention in STATE.md — read it first to match format). Entry should be a single-line bullet:
    `- 2026-05-15 quick 260515-cvh — kb Aliyun go-live hotfix upstream commit (qa.js link/state, search retry, KG chip backfill, logo) — 4 prod files + 2 test files + RUNBOOK; hero-strip deferred to v2.1`

    DO NOT modify any other STATE.md content beyond the single-line append.

    Do NOT make the commit yet — Task 5 handles atomic commit + push.
  </action>
  <verify>
    <automated>
    test -f .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md && \
    test -f .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md && \
    grep -q "Skill(skill=\"python-patterns\"" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md && \
    grep -q "Skill(skill=\"writing-tests\"" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md && \
    grep -q "Path A" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md && \
    grep -q "Path B" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md && \
    grep -q "kb-templates-index-hero-strip-migration" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md && \
    grep -q "2c71bdf" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md && \
    grep -q "260515-cvh" .planning/STATE.md && \
    echo "TASK 4 PASS"
    </automated>
  </verify>
  <done>
    RUNBOOK.md has both Path A + Path B + PNG note; SUMMARY.md has both verbatim Skill invocations + scope/PNG/evidence sections; STATE.md has the single-line append.
  </done>
</task>

<task type="auto">
  <name>Task 5: Atomic commit + push to origin/main</name>
  <files>
    .git (commit only — no source changes)
  </files>
  <action>
    Step 1 — Sanity check no unrelated changes are staged:
    `git status -sb` — confirm only the 9 expected files appear (4 prod + 2 test + 2 planning + STATE.md), nothing else. If unrelated changes are present, STOP and escalate.

    Step 2 — Stage EXPLICITLY (NEVER `git add -A`, NEVER `git add .` — per memory `feedback_git_add_explicit_in_parallel_quicks.md`):

    ```
    git add \
      kb/services/synthesize.py \
      kb/static/qa.js \
      kb/static/search.js \
      kb/static/VitaClaw-Logo-v0.png \
      tests/integration/kb/test_qa_link_contract.py \
      tests/unit/kb/test_synthesize_hotfix.py \
      .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-PLAN.md \
      .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md \
      .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-RUNBOOK.md \
      .planning/STATE.md
    ```

    Step 3 — Verify staging via `git diff --cached --stat` — confirm 10 files staged, no surprise additions.

    Step 4 — Commit with the message from `<commit_message_spec>` via HEREDOC:

    ```
    git commit -m "$(cat <<'EOF'
    fix(kb): land 4 Aliyun go-live hotfixes (qa.js link + state, search retry, KG chip backfill, logo)

    Hotfixes applied directly on Aliyun production by vitaclaw-site go-live agent
    on 2026-05-15; this commit lands them into origin/main.

    1. kb/static/qa.js — source chip link path (/article/ → /articles/, add KB_BASE_PATH);
       fallback state name (bare 'fallback' → 'fts5_fallback' per UI-SPEC §3.2 + CSS contract)
    2. kb/static/search.js — cross-language retry when locale-filtered search returns 0 items
    3. kb/services/synthesize.py — KG-happy-path source/entity chip backfill via FTS fallback
       (75-line addition; v2.0 minimum-viable workaround for C1 read-only contract)
    4. kb/static/VitaClaw-Logo-v0.png — UI-04 carry-forward

    Tests added:
    - tests/integration/kb/test_qa_link_contract.py (closes kb-3-12 test gap)
    - tests/unit/kb/test_synthesize_hotfix.py (covers 4 new helpers)

    Skills invoked (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):
    - Skill(skill="python-patterns", args="...")  # see SUMMARY.md verbatim
    - Skill(skill="writing-tests", args="...")     # see SUMMARY.md verbatim

    Notes:
    - Hero-image-strip migration deferred to v2.1 backlog
      kb-templates-index-hero-strip-migration — go-live agent added it directly
      to Aliyun's index.html outside the template; template-side migration is its
      own quick.
    - PNG sha256=2c71bdf438045ea6c3511cb3722c1ac4673d427032571a36971fa5d0c2fc6f54
      (470KB, 2048x2048 RGBA) does NOT match Aliyun production blob (3c827d3...).
      Re-encoded but visually equivalent. Operator RUNBOOK documents this.
    - _ENTITY_HINTS is a v2.0 minimum-viable hardcoded list. v2.1 backlog will
      replace with extracted_entities table join or LightRAG entity_canonical.
    EOF
    )"
    ```

    Step 5 — Verify commit landed cleanly:
    `git log --oneline -1` — should show the new commit hash + message subject
    `git status -sb` — should show clean working tree

    Step 6 — Push to origin/main:
    `git push origin main`

    If push is rejected (non-fast-forward, secret-scanning block, etc.), STOP — do NOT force-push, do NOT amend. Escalate to user with the rejection reason.

    Step 7 — Verify push:
    `git status -sb` — should show `## main...origin/main` with no ahead/behind divergence.
  </action>
  <verify>
    <automated>
    git log --oneline -1 | grep -q "fix(kb): land 4 Aliyun go-live hotfixes" && \
    git diff HEAD~1 HEAD --stat | grep -qE "10 files? changed" && \
    git status -sb | head -1 | grep -qE "main\.\.\.origin/main\$" && \
    echo "TASK 5 PASS — commit pushed atomically to origin/main"
    </automated>
  </verify>
  <done>
    Single atomic commit on origin/main containing exactly 10 files; commit subject matches spec; working tree clean; no divergence from origin.
  </done>
</task>

</tasks>

<verification>
After all 5 tasks complete:

1. **Discipline regex** — both Skill names appear verbatim in SUMMARY.md:
   ```
   grep -c "Skill(skill=\"python-patterns\"" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md  # ≥1
   grep -c "Skill(skill=\"writing-tests\"" .planning/quick/260515-cvh-kb-aliyun-go-live-hotfix-upstream-commit/260515-cvh-SUMMARY.md   # ≥1
   ```

2. **Test gate** — 10 new tests green:
   ```
   PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m pytest tests/integration/kb/test_qa_link_contract.py tests/unit/kb/test_synthesize_hotfix.py -v
   # expect: 10 passed
   ```

3. **SSG gate** — no template-rendering regression in either KB_BASE_PATH mode (already verified in Task 3).

4. **Atomic commit gate** — exactly 10 files in the new HEAD commit, pushed to origin/main, no divergence (verified in Task 5).

5. **Out-of-scope gate** — `git diff HEAD~1 HEAD --name-only` MUST contain ONLY:
   - kb/services/synthesize.py
   - kb/static/qa.js
   - kb/static/search.js
   - kb/static/VitaClaw-Logo-v0.png
   - tests/integration/kb/test_qa_link_contract.py
   - tests/unit/kb/test_synthesize_hotfix.py
   - .planning/quick/260515-cvh-.../{PLAN,SUMMARY,RUNBOOK}.md (3 files)
   - .planning/STATE.md

   Any other path = scope creep. Investigate.

6. **Forbidden-touch gate** — `git diff HEAD~1 HEAD --name-only | grep -E "^kb/templates/|^kb/output/|^kg_synthesize\.py$"` MUST return empty (templates not touched, build artifacts not touched, C1 contract not touched).
</verification>

<success_criteria>
- All 5 tasks pass their automated verify commands
- 10 new tests green (3 integration + 7 unit)
- SSG re-renders cleanly in both KB_BASE_PATH modes
- Atomic commit on origin/main with exactly 10 files
- Both Skill invocations cited verbatim in SUMMARY.md (discipline regex passes)
- RUNBOOK.md gives Aliyun operator both Path A + Path B with PNG sha256 note
- STATE.md has single-line quick log entry
- No scope creep: no template edits, no kb/output/ edits, no C1 contract edits, no hero-strip work
</success_criteria>

<output>
After all 5 tasks complete, the executor returns:
- Quick ID: 260515-cvh
- Commit hash: (from `git log --oneline -1`)
- Push status: clean on origin/main
- Test result: 10/10 passed
- Skill invocation count in SUMMARY.md: 2 (python-patterns + writing-tests)
- Operator handoff: RUNBOOK.md path
</output>
