---
phase: llm-wiki-integration
plan: 04
type: execute
wave: 2
depends_on: ["llm-wiki-02"]
files_modified:
  - kb/wiki_lint.py                                    # NEW lint module (~80 LOC)
  - kb/wiki_update.py                                  # NEW update-suggestion logic (~50 LOC)
  - batch_ingest_from_spider.py                        # +async _wiki_update_check() hook + 1 call site
  - tests/unit/test_wiki_lint.py                       # fills W0 stubs (4 tests)
  - tests/integration/test_wiki_hook.py                # fills W0 stub
  - tests/unit/test_ingest_from_db_orchestration.py    # +behavior-anchor test for hook (CLAUDE.md Rule 7)
  - tests/unit/_ingest_fixtures.py                     # extend schema if needed
  - kb/wiki/log.md                                     # append "W3 hook + lint shipped" entry
autonomous: true   # no checkpoints; verification via tests + Local UAT
requirements:
  - WIKI-HOOK            # Decision 3 — auto-apply ingest suggestions after lint passes
  - WIKI-LINT-CITATION   # Decision 5 — citation integrity lint
  - WIKI-LINT-CONTRA     # Decision 5 — contradiction detection lint
  - WIKI-LINT-BACKLINK   # Decision 5 — backlink validity lint
  - WIKI-LINT-STALE      # Decision 5 — staleness check lint
  - WIKI-LINT-INTEG      # Decision 5 — lint integrated into hook (NOT standalone P4)
  - WIKI-ATOMIC-WRITE    # RESEARCH "Don't Hand-Roll" — atomic .tmp + os.rename
must_haves:
  truths:
    - "kb/wiki_lint.py exposes 4 lint functions (citation, contradiction, backlink, staleness) with unit tests"
    - "kb/wiki_update.py generates per-suggestion markdown deltas with citations from new ingested articles"
    - "batch_ingest_from_spider.py end-of-cron path invokes async _wiki_update_check() AFTER _drain_layer2_queue"
    - "Hook is fire-and-forget with timeout; never blocks ingest exit"
    - "Lint failures are logged to JSONL and dropped (do not block cron); lint passes are auto-applied via atomic write"
    - "Behavior-anchor test in test_ingest_from_db_orchestration.py pins observable post-conditions of the hook (CLAUDE.md Rule 7)"
    - "Local UAT exercised: run cron locally on fixture article, verify wiki update emerges (or is correctly dropped by lint)"
  artifacts:
    - path: "kb/wiki_lint.py"
      provides: "4 lint functions + JSONL logger"
      exports: ["lint_citation_integrity", "lint_contradicts_existing", "lint_backlink_validity", "lint_staleness"]
    - path: "kb/wiki_update.py"
      provides: "Suggestion generation from ingested article entities"
      exports: ["generate_wiki_suggestions", "apply_suggestion_atomic"]
    - path: "batch_ingest_from_spider.py"
      provides: "End-of-cron _wiki_update_check() async hook + call site"
      contains: "async def _wiki_update_check"
  key_links:
    - from: "batch_ingest_from_spider.py:_wiki_update_check"
      to: "kb/wiki_update.py:generate_wiki_suggestions"
      via: "import + asyncio.create_task with timeout"
      pattern: "from kb.wiki_update import|wiki_update.generate_wiki_suggestions"
    - from: "kb/wiki_update.py:apply_suggestion_atomic"
      to: "kb/wiki/entities/<slug>.md"
      via: "atomic .tmp + os.rename pattern from RESEARCH Example 5"
      pattern: "tempfile|os.rename"
    - from: "kb/wiki_update.py"
      to: "kb/wiki_lint.py"
      via: "lint guard before apply"
      pattern: "import.*wiki_lint|wiki_lint\\.lint_"
---

<objective>
Add an end-of-cron hook to `batch_ingest_from_spider.py` that generates wiki update suggestions, runs lint guards (citation / contradiction / backlink / staleness), and auto-applies passing suggestions to `kb/wiki/entities/`. Lint failures are logged JSONL and dropped silently; the hook never blocks cron exit. Per CLAUDE.md Rule 7 (behavior-anchor harness for hot orchestration code), the integration is pinned by an observable post-condition test extending `tests/unit/test_ingest_from_db_orchestration.py`.

Purpose: Realizes Decision 3 (auto-apply with lint guard) + Decision 5 (lint integrated, not standalone) of CONTEXT.md. Closes W3 / P2 + P4-lint of the wave structure.
Output: 2 new modules in `kb/`, 1 hot-path change in `batch_ingest_from_spider.py`, 4 unit tests filling W0 lint stubs, 1 integration test, 1 behavior-anchor test, Local UAT evidence.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md
@.planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md
@.planning/phases/llm-wiki-integration/llm-wiki-02-SUMMARY.md
@kb/wiki/SCHEMA.md
@./CLAUDE.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@batch_ingest_from_spider.py
@tests/unit/test_ingest_from_db_orchestration.py
@tests/unit/_ingest_fixtures.py
</context>

<interfaces>
<!-- Existing batch_ingest_from_spider.py orchestration patterns we extend -->

End-of-cron sequence (existing — find via grep before editing):
```python
# batch_ingest_from_spider.py — end of ingest_from_db()
# After main per-article loop:
await _drain_layer2_queue(...)   # existing call
# <-- NEW: invoke _wiki_update_check() here as async fire-and-forget
```

Atomic write pattern (per RESEARCH Example 5):
```python
import os, tempfile
from pathlib import Path

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    os.rename(tmp_path, path)
```

Citation regex (per RESEARCH "Don't Hand-Roll"):
```python
import re
CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")
BACKLINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")
```

Frontmatter parsing (per RESEARCH "Don't Hand-Roll"):
```python
import frontmatter   # python-frontmatter; added to requirements in W1
post = frontmatter.load(path)
post.metadata["last_updated"]  # ISO date string
```

JSONL logging path:
```
.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl   # append-only, one JSON object per line
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: kb/wiki_lint.py — 4 lint functions + unit tests</name>
  <files>kb/wiki_lint.py, tests/unit/test_wiki_lint.py</files>
  <read_first>
    - tests/unit/test_wiki_lint.py (W0 stub — 4 skipped tests; replace skips with real tests)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Example 2 — citation lint reference)
    - kb/wiki/SCHEMA.md (frontmatter + citation contract)
    - kb/wiki/entities/openclaw.md (canonical sample to use as fixture in tests)
  </read_first>
  <behavior>
    - lint_citation_integrity(page_path, known_article_hashes): returns [] if every `^[article:<hash>]` resolves to a hash in known_article_hashes; else returns list of unresolved citation strings.
    - lint_contradicts_existing(suggestion_text, existing_page_path): conservative diff-based — extract sentences from existing page that share ≥2 noun-phrase tokens with suggestion sentences AND contain a numeric or date token; if any sentence pair has incompatible numeric/date values (e.g., existing "founded 2024" vs suggestion "founded 2026"), return list of conflict descriptions. v1 is regex-based per CONTEXT.md "Implementation details — regex + simple syntax checks; LLM-based contradiction detection deferred to v2".
    - lint_backlink_validity(suggestion_text, wiki_root_path): for every `[[entity-slug]]` reference in suggestion, verify `wiki_root/entities/<slug>.md` exists; return list of dangling slugs.
    - lint_staleness(page_path, max_days=180): parse frontmatter `last_updated`; if older than max_days from today, return ["stale: last_updated=<date>, age=<N>d"] else [].
    - Each function returns `list[str]` of failure descriptions; empty list = pass.
  </behavior>
  <action>
    Create `kb/wiki_lint.py` with the 4 lint functions defined under `<behavior>` plus a `log_lint_failure(failure_dict)` helper that appends to `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl`.

    Implementation notes:
    1. Use `python-frontmatter` (added in W1 requirements.txt) for frontmatter parsing — DO NOT hand-roll YAML.
    2. Use the regex constants from <interfaces> block.
    3. For `lint_contradicts_existing`, keep v1 simple: regex-extract numbers (`\b\d{4}\b` for years, `\b\d+(?:\.\d+)?\b` for general numerics) from sentences. If a suggestion sentence and existing sentence share ≥2 capitalized words AND contain different year tokens, flag as contradiction. This is intentionally conservative; false negatives expected and accepted at v1.
    4. `log_lint_failure` writes one JSON line per call: `{ts, page_path, lint_name, failures: [...], suggestion_excerpt: "..."}`. Atomic per-line append via single `open(..., "a")` + write + close (line-level atomicity sufficient for JSONL — full atomic file write is overkill for append-only log).

    Replace the 4 W0 stubs in `tests/unit/test_wiki_lint.py` with real tests:

    - `test_unresolved_citation`: write a tmp wiki page with `^[article:1234567890]` and `^[article:deadbeef00]`; pass `known_article_hashes={"1234567890"}`; assert returns `["^[article:deadbeef00]"]`.
    - `test_contradicts_existing`: existing page sentence "OpenClaw was founded in 2024."; suggestion sentence "OpenClaw was founded in 2026."; assert at least one contradiction returned.
    - `test_backlink_validity`: suggestion "[[hermes-agent]] [[unknown-entity]]"; wiki_root has entities/hermes-agent.md but not unknown-entity.md; assert returns `["unknown-entity"]`.
    - `test_staleness_check`: write a tmp page with frontmatter `last_updated: 2024-01-01`; with max_days=180, assert returns 1 failure containing "stale"; with max_days=10000, assert returns [].

    Tests must use `tmp_path` and `freezegun` (or fixed date inputs); do NOT mirror impl formula (per `feedback_test_mirrors_impl.md`).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_wiki_lint.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/wiki_lint.py` exits 0
    - `pytest tests/unit/test_wiki_lint.py::test_unresolved_citation` PASSES
    - `pytest tests/unit/test_wiki_lint.py::test_contradicts_existing` PASSES
    - `pytest tests/unit/test_wiki_lint.py::test_backlink_validity` PASSES
    - `pytest tests/unit/test_wiki_lint.py::test_staleness_check` PASSES
    - `grep -E '^def lint_(citation|contradicts|backlink|staleness)' kb/wiki_lint.py` shows 4 functions defined
    - `grep -q 'log_lint_failure' kb/wiki_lint.py` exits 0
    - kb/wiki_lint.py is < 100 LOC
  </acceptance_criteria>
  <done>4 lint functions implemented + 4 unit tests pass; JSONL logger helper present; no stubs remain skipped.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: kb/wiki_update.py — suggestion generation + atomic apply + integration test</name>
  <files>kb/wiki_update.py, tests/integration/test_wiki_hook.py</files>
  <read_first>
    - kb/wiki_lint.py (just-built; this task imports its 4 lint functions)
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Example 5 — atomic write)
    - kb/wiki/SCHEMA.md (frontmatter contract for new pages)
    - tests/integration/test_wiki_hook.py (W0 stub — replace skip)
  </read_first>
  <behavior>
    - generate_wiki_suggestions(article_hashes: list[str], wiki_root: Path, db_conn) -> list[Suggestion]:
      * For each article_hash, query DB to retrieve title + entities mentioned (re-use existing entity buffer / LightRAG entity extraction; DO NOT re-run LightRAG)
      * For each entity referenced ≥3 times across the article batch (high-frequency new entity): generate a NEW-PAGE suggestion if `wiki_root/entities/<slug>.md` doesn't exist
      * For each entity that already has a wiki page: generate an UPDATE-DELTA suggestion (small diff: bump last_updated, append source if not present, optional 1-2 sentence addition with `^[article:<hash>]` citation)
      * Return list of Suggestion dicts: `{type: "new"|"update", entity_slug, page_path, content, source_articles}`
    - apply_suggestion_atomic(suggestion, lint_results) -> bool:
      * If lint_results is non-empty → call log_lint_failure, return False (no write)
      * Else → atomic write content to page_path, return True
  </behavior>
  <action>
    Create `kb/wiki_update.py` with 2 main functions per `<behavior>` plus internal helpers.

    Implementation:
    1. `generate_wiki_suggestions` — read article rows from `articles` table for given hashes (use existing `sqlite3` connection helper from `lib/` if any; else build minimal one). For entity extraction, prefer reading from `entity_buffer/<hash>_entities.json` files (already produced by ingest pipeline per CLAUDE.md "Entity buffer idempotency"). Aggregate entities across article set, count occurrences, classify into new-page vs update branches.
    2. For UPDATE-DELTA suggestions: open existing page, parse frontmatter, prepare modified content (bump `last_updated` to today, ensure new article hashes appear in `sources:` list, optionally append a one-sentence addition under a relevant section if the LLM is confident — but per CONTEXT.md Decision 5 lint runs BEFORE apply, so this is OK). Keep deltas conservative — minimal additions, no rewrites of existing claims.
    3. For NEW-PAGE suggestions: build a small page with frontmatter + 1-2 sentence stub ("Auto-generated stub from W3 hook on <date>; expand via wiki_generate_pages.py for full multi-hop synthesis.") + citations from the source articles. Mark `confidence_level: low`.
    4. `apply_suggestion_atomic` — invoke lint guards (citation_integrity using `articles.content_hash` set from DB; contradicts_existing for UPDATE type; backlink_validity; staleness for UPDATE type only). If any returns non-empty, log + skip. Else use the atomic-write helper from RESEARCH Example 5 to write the page.
    5. Expose `apply_suggestion_atomic(suggestion, db_conn)` that internally fetches `known_article_hashes` from `db_conn` then calls all 4 lint functions; returns True/False.

    **Replace W0 stub** in `tests/integration/test_wiki_hook.py`:
    - `test_end_of_cron_fires`: integration test with mocked `articles` table (sqlite3 in-memory) + tmp wiki dir + 3 fake article hashes. Mock entity_buffer JSON files. Call `generate_wiki_suggestions` then `apply_suggestion_atomic` for each suggestion. Assert: at least 1 new page created OR at least 1 page updated; lint failures (if any) appear in JSONL; no exception escapes.
    - Add second test `test_lint_blocks_unresolved_citation`: craft a suggestion containing a citation hash NOT in the DB; assert apply returns False AND JSONL has a "lint_citation_integrity" failure entry AND no file was written.

    Pin tests to observable behavior (CLAUDE.md Rule 7 + `feedback_test_mirrors_impl.md`).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/integration/test_wiki_hook.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f kb/wiki_update.py` exits 0
    - `grep -E '^def generate_wiki_suggestions|^def apply_suggestion_atomic' kb/wiki_update.py` shows 2 functions
    - `pytest tests/integration/test_wiki_hook.py::test_end_of_cron_fires` PASSES
    - `pytest tests/integration/test_wiki_hook.py::test_lint_blocks_unresolved_citation` PASSES
    - kb/wiki_update.py is < 100 LOC
    - `grep -q 'os.rename\|tempfile' kb/wiki_update.py` exits 0 (atomic write present)
    - `grep -q 'wiki_lint' kb/wiki_update.py` exits 0 (lint guard wired)
  </acceptance_criteria>
  <done>Suggestion generation + atomic-apply with lint guard implemented; 2 integration tests pass; lint failures logged not raised.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: batch_ingest_from_spider.py — _wiki_update_check() hook + behavior-anchor test (CLAUDE.md Rule 7)</name>
  <files>batch_ingest_from_spider.py, tests/unit/test_ingest_from_db_orchestration.py, tests/unit/_ingest_fixtures.py, kb/wiki/log.md</files>
  <read_first>
    - batch_ingest_from_spider.py (read CURRENT state immediately before edit; per CLAUDE.md feedback_contract_shape_change_full_audit.md and parallel-agent collision risk noted in CONTEXT.md)
    - tests/unit/test_ingest_from_db_orchestration.py (existing T1-T5 tests; this task adds T6 or similar) — **CRITICAL: copy the existing T1-T5 invocation signature for `await ingest_from_db(...)` exactly into the new test; do NOT use `...` placeholder. The literal Ellipsis is NOT valid call syntax and will fail at runtime.**
    - tests/unit/_ingest_fixtures.py (in_memory_db schema — extend if hook reads new columns)
    - kb/wiki_update.py (just-built)
    - CLAUDE.md (HIGHEST PRIORITY PRINCIPLES #7 — behavior-anchor harness for hot orchestration code; this is exactly the case it covers)
  </read_first>
  <behavior>
    Observable post-conditions of _wiki_update_check() hook (the test pins these, NOT the call shape):
    - When hook runs with N article_hashes from this cron's batch: at least one of {new wiki page exists, existing wiki page mtime updated, JSONL lint-failure entry appended} is true after hook returns.
    - When hook times out (asyncio.wait_for budget exceeded): no exception escapes ingest_from_db; ingest_from_db return value unchanged.
    - When hook raises any exception: exception is caught at the call site; ingest_from_db return value unchanged; warning logged.
    - Hook is called AFTER _drain_layer2_queue (verifiable via call order in mock).
    - Hook does NOT modify articles, classifications, or any production DB row (verifiable via row hash comparison before/after).
  </behavior>
  <action>
    **Step A — Add the hook function** to `batch_ingest_from_spider.py`:

    ```python
    async def _wiki_update_check(article_hashes: list[str], db_conn, wiki_root: Path = Path("kb/wiki")) -> dict:
        """End-of-cron wiki update hook (W3 of llm-wiki-integration).

        Generates suggestions from ingested-batch entities, runs lint guards,
        applies passing suggestions atomically. Drops + logs failures.

        Fire-and-forget: catches all exceptions; never raises. Wrapped in
        asyncio.wait_for(timeout=120) by caller.

        Returns dict for observability: {suggestions_generated, applied, dropped}.
        """
        try:
            from kb.wiki_update import generate_wiki_suggestions, apply_suggestion_atomic
            suggestions = generate_wiki_suggestions(article_hashes, wiki_root, db_conn)
            applied = 0
            dropped = 0
            for s in suggestions:
                ok = apply_suggestion_atomic(s, db_conn)
                if ok:
                    applied += 1
                else:
                    dropped += 1
            logger.info(f"wiki_update_check: generated={len(suggestions)} applied={applied} dropped={dropped}")
            return {"suggestions_generated": len(suggestions), "applied": applied, "dropped": dropped}
        except Exception as e:
            logger.warning(f"wiki_update_check failed (suppressed): {e}", exc_info=True)
            return {"error": str(e)}
    ```

    **Step B — Add the call site** at end-of-cron path AFTER `_drain_layer2_queue` completes. Find existing `_drain_layer2_queue(...)` invocation (likely inside `ingest_from_db`); add immediately after:

    ```python
    # W3 wiki update hook (fire-and-forget, never blocks ingest)
    successful_hashes = [h for h, status in per_article_status.items() if status == "ok"]
    try:
        await asyncio.wait_for(
            _wiki_update_check(successful_hashes, conn),
            timeout=120,
        )
    except asyncio.TimeoutError:
        logger.warning("wiki_update_check timed out after 120s; skipping")
    ```

    Use whatever variable name in the existing code holds the list of newly-ingested article hashes from this cron run (read the existing code carefully to identify; if no such collection exists, build it inline from `cursor.execute("SELECT article_id FROM ingestions WHERE batch_id=?")` or similar).

    **Step C — Add behavior-anchor test** in `tests/unit/test_ingest_from_db_orchestration.py`:

    Add `test_wiki_update_hook_called_after_drain_with_observable_post_condition` (per CLAUDE.md PRINCIPLE #7).

    **CRITICAL — DO NOT use `...` literal**: per Blocker 3 of plan-checker review, before writing the test, OPEN `tests/unit/test_ingest_from_db_orchestration.py` and READ the exact `await ingest_from_db(...)` invocation signature used in T1-T5. Copy that signature verbatim into the new test. The Ellipsis literal `...` is NOT valid Python call syntax and will cause runtime errors if shipped.

    Example skeleton — BUT REPLACE the sentinel comments with the real call signature copied from T1-T5:

    ```python
    @pytest.mark.asyncio
    async def test_wiki_update_hook_called_after_drain_with_observable_post_condition(
        in_memory_db, mock_rag, monkeypatch, tmp_path
    ):
        # Given: ingest_from_db running on seeded DB with 2 successful ingest articles
        wiki_dir = tmp_path / "kb" / "wiki" / "entities"
        wiki_dir.mkdir(parents=True)
        # Pre-populate one entity page so update-delta path is exercised
        (wiki_dir / "openclaw.md").write_text("---\ntitle: OpenClaw\nlast_updated: 2026-01-01\nsources:\n  - article:0000000001\nconfidence_level: high\n---\n# OpenClaw\nFounded ^[article:0000000001].\n")

        # fixture-schema-verified: in_memory_db must include articles.content_hash column
        # (per CLAUDE.md 2026-05-15 lesson #2 — fixture drift = silent bug)
        assert "content_hash" in [c[1] for c in in_memory_db.execute("PRAGMA table_info(articles)").fetchall()], \
            "fixture schema missing articles.content_hash; sync tests/unit/_ingest_fixtures.py CREATE TABLE"

        call_order = []
        async def fake_drain(*args, **kwargs):
            call_order.append("drain")
        async def fake_hook(*args, **kwargs):
            call_order.append("hook")
            return {"suggestions_generated": 1, "applied": 1, "dropped": 0}

        monkeypatch.setattr("batch_ingest_from_spider._drain_layer2_queue", fake_drain)
        monkeypatch.setattr("batch_ingest_from_spider._wiki_update_check", fake_hook)

        # When: ingest_from_db runs to completion
        # CALL: copy exact ingest_from_db(...) signature from T1-T5 in test_ingest_from_db_orchestration.py — DO NOT leave ... literal
        await ingest_from_db(<COPY-EXACT-SIGNATURE-FROM-T1-T5>)

        # Then: hook runs AFTER drain (call_order[-2:] == ["drain", "hook"])
        assert call_order[-2:] == ["drain", "hook"], f"expected drain then hook; got {call_order}"

        # And: ingest_from_db return value unaffected by hook (verify articles status unchanged)
        # ... (use existing T1-T5 patterns for status assertion)

        # And: hook exception does NOT propagate
        async def raising_hook(*args, **kwargs):
            raise RuntimeError("hook crashed")
        monkeypatch.setattr("batch_ingest_from_spider._wiki_update_check", raising_hook)
        # ingest_from_db should still complete — but we wrapped hook in wait_for; the test
        # asserts the call site catches exceptions. Run again and assert no raise.
        # CALL: copy exact ingest_from_db(...) signature from T1-T5 in test_ingest_from_db_orchestration.py — DO NOT leave ... literal
        await ingest_from_db(<COPY-EXACT-SIGNATURE-FROM-T1-T5>)   # MUST NOT raise
    ```

    The test should pin: (1) drain → hook order, (2) hook-exception suppression, (3) no DB row mutation by hook.

    **Step D — Update _ingest_fixtures.py** if the hook reads any new column. Likely no new columns needed — hook reads `articles.content_hash` only, which already exists. **MEDIUM 2 fix**: the test in Step C now contains a runtime assertion that `articles.content_hash` is present in `in_memory_db()` schema (search for `# fixture-schema-verified` marker or the assert that reads `PRAGMA table_info(articles)`). This converts the previously-advisory inspection into an enforced check per CLAUDE.md 2026-05-15 lesson #2. If new columns ARE needed beyond content_hash, ADD them to `_ingest_fixtures.py:in_memory_db()` CREATE TABLE.

    **Step E — Append to `kb/wiki/log.md`**: `<ISO date> — W3 ingest hook + lint guard shipped (kb/wiki_lint.py + kb/wiki_update.py + batch_ingest_from_spider.py:_wiki_update_check)`.

    **Per CLAUDE.md feedback_contract_shape_change_full_audit.md**: grep all callers of `_drain_layer2_queue` to ensure we add the hook to ALL end-of-cron paths, not just the main one. Likely there is one path; verify with grep.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v && grep -q 'async def _wiki_update_check' batch_ingest_from_spider.py && grep -c '_wiki_update_check' batch_ingest_from_spider.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'async def _wiki_update_check' batch_ingest_from_spider.py` exits 0
    - `grep -c '_wiki_update_check' batch_ingest_from_spider.py` returns ≥ 2 (definition + at least one call site)
    - `grep -q 'asyncio.wait_for' batch_ingest_from_spider.py` near the call site (timeout wrapper present)
    - `grep -q '_drain_layer2_queue' batch_ingest_from_spider.py` AND the call site for hook is BELOW the drain call in source order (verify with `grep -n` line numbers)
    - `pytest tests/unit/test_ingest_from_db_orchestration.py::test_wiki_update_hook_called_after_drain_with_observable_post_condition` PASSES
    - Existing T1-T5 tests in test_ingest_from_db_orchestration.py still PASS (no regression)
    - **BLOCKER 3 fix**: `grep -nE 'await ingest_from_db\(\.\.\.\)' tests/unit/test_ingest_from_db_orchestration.py` returns ZERO matches (no `...` literal placeholder in shipped test code)
    - **MEDIUM 2 fix**: `grep -nE '# fixture-schema-verified|assert.*content_hash' tests/unit/test_ingest_from_db_orchestration.py` returns at least one match (enforced fixture-schema check, per CLAUDE.md 2026-05-15 lesson #2)
    - `tail -3 kb/wiki/log.md | grep -q 'W3 ingest hook'` exits 0
  </acceptance_criteria>
  <done>Hook function + call site shipped in batch_ingest_from_spider.py; behavior-anchor test pins observable post-conditions per CLAUDE.md Rule 7; existing orchestration tests still green.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Local UAT per CLAUDE.md Rule 6 — run cron locally + verify wiki update emerges</name>
  <what-built>End-to-end W3 hook: ingest a fixture article through `batch_ingest_from_spider.py` against `.dev-runtime/data/kol_scan.db`; observe wiki update at `kb/wiki/entities/<slug>.md` OR a JSONL lint-failure entry. Verify the hook does not block cron exit.</what-built>
  <how-to-verify>
    Per CLAUDE.md Rule 6 (KB local UAT mandatory before phase complete) — Wave 4 of llm-wiki-integration touches `kb/` (specifically `kb/wiki_lint.py` + `kb/wiki_update.py` + writes under `kb/wiki/`). Local UAT MUST run.

    Steps:

    1. **Pre-flight check**:
       ```bash
       venv/Scripts/python.exe -m pytest tests/unit/test_wiki_lint.py tests/integration/test_wiki_hook.py tests/unit/test_ingest_from_db_orchestration.py -v
       ```
       Expect all GREEN.

    2. **Local cron smoke** via `scripts/local_e2e.sh` (per CLAUDE.md feedback_use_local_e2e_sh.md — DO NOT manually export env vars):
       ```bash
       ./scripts/local_e2e.sh layer1 1
       ```
       (Layer 1 is reachable locally; subsequent stages are corp-blocked but the W3 hook only needs `successful_hashes` to be non-empty AND the `articles` table to have content_hashes, which Layer 1 satisfies for already-ingested rows from prior runs.)

       For a more direct test, run a focused script that simulates "end of cron" without needing the full pipeline:
       ```bash
       venv/Scripts/python.exe -c "
       import asyncio, sqlite3
       from pathlib import Path
       import sys; sys.path.insert(0, '.')
       from batch_ingest_from_spider import _wiki_update_check
       conn = sqlite3.connect('.dev-runtime/data/kol_scan.db')
       hashes = [r[0] for r in conn.execute('SELECT content_hash FROM articles ORDER BY id DESC LIMIT 3').fetchall()]
       print('hashes:', hashes)
       result = asyncio.run(_wiki_update_check(hashes, conn, Path('kb/wiki')))
       print('result:', result)
       "
       ```

    3. **Capture evidence**:
       - Output of step 2 → save to `.scratch/llm-wiki-04-uat-<ts>.log`
       - `git status kb/wiki/` → list any newly-created or modified wiki pages
       - `cat .planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl 2>/dev/null | tail -20` → any lint failures recorded
       - `git diff kb/wiki/entities/openclaw.md` → if existing page was updated, show diff

    4. **Append to phase VERIFICATION.md** (create `.planning/phases/llm-wiki-integration/llm-wiki-04-VERIFICATION.md`) a "## Local UAT" section per CLAUDE.md Rule 6 with:
       - Launcher used (`./scripts/local_e2e.sh layer1 1` or direct python invocation)
       - Env vars (auto-set by harness)
       - Result of `_wiki_update_check` call (suggestions_generated / applied / dropped)
       - Cite log file path (`.scratch/llm-wiki-04-uat-<ts>.log`)
       - List of wiki pages created/modified (or "none" if all suggestions dropped by lint — also acceptable)

    5. **Negative-path UAT**: deliberately corrupt one wiki page to have an unresolved citation (`^[article:ffffffffff]` for a hash not in DB), re-run hook, confirm:
       - Lint catches it
       - JSONL has new entry
       - Page is NOT auto-applied (atomic write skipped)
  </how-to-verify>
  <resume-signal>
    User responds with one of:
    - "uat-passed" + path to log file → Claude appends the log path to llm-wiki-04-VERIFICATION.md as evidence; plan COMPLETE
    - "uat-failed: <error>" → Claude diagnoses; if test/code bug, return to relevant task; if env issue, document in VERIFICATION.md and re-attempt
    - "skip-uat (justification: <reason>)" → discouraged per Rule 6; if accepted, document the justification clearly in VERIFICATION.md
  </resume-signal>
</task>

</tasks>

<verification>
Phase-level verification for W3:
- All wiki tests green: `pytest tests/unit/test_wiki_lint.py tests/integration/test_wiki_hook.py -v`
- Behavior-anchor test green: `pytest tests/unit/test_ingest_from_db_orchestration.py -v`
- `grep -q 'async def _wiki_update_check' batch_ingest_from_spider.py` exits 0
- `grep -q 'asyncio.wait_for' batch_ingest_from_spider.py` near hook call site
- `test -f kb/wiki_lint.py && test -f kb/wiki_update.py` exits 0
- `test -f .planning/phases/llm-wiki-integration/llm-wiki-04-VERIFICATION.md` exits 0
- Local UAT log path cited in VERIFICATION.md
- `git diff` shows surgical changes only — no edits to unrelated code in batch_ingest_from_spider.py (per CLAUDE.md HIGHEST PRIORITY #3 Surgical Changes)
- BLOCKER 3 verification: `grep -nE 'await ingest_from_db\(\.\.\.\)' tests/unit/test_ingest_from_db_orchestration.py` returns ZERO matches
</verification>

<success_criteria>
1. kb/wiki_lint.py with 4 lint functions + JSONL logger; 4 unit tests PASS
2. kb/wiki_update.py with suggestion generator + atomic apply + lint guard; 2 integration tests PASS
3. batch_ingest_from_spider.py has _wiki_update_check() function + post-drain call site with asyncio.wait_for(120) wrap
4. Behavior-anchor test pins drain→hook order + exception suppression (CLAUDE.md Rule 7)
5. Local UAT performed and cited in llm-wiki-04-VERIFICATION.md per CLAUDE.md Rule 6
6. All existing T1-T5 orchestration tests still PASS (no regression)
7. Total LOC ≤ ~150 (kb/wiki_lint.py < 100 + kb/wiki_update.py < 100 + batch_ingest_from_spider.py addition < 30)
</success_criteria>

<output>
After completion, create `.planning/phases/llm-wiki-integration/llm-wiki-04-SUMMARY.md` capturing:
- Files created (kb/wiki_lint.py, kb/wiki_update.py) + LOC each
- Hook insertion line number in batch_ingest_from_spider.py
- Test counts: 4 lint unit + 2 integration + 1 behavior-anchor = 7 new tests
- Local UAT log path + summary of UAT result (per CLAUDE.md Rule 6)
- JSONL log path: `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl`
- Any lint false-positives observed during UAT (informs v2 lint refinement)
- Note: hook is fire-and-forget; cron exit time not impacted (verify in UAT timing)
</output>
</content>
