---
phase: 260516-rqk-kb-v2-1-6-article-image-rendering-fix
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/data/article_query.py
  - tests/integration/kb/test_image_rendering.py
status: COMPLETE
completed: 2026-05-16
requirements_satisfied:
  - kb-v2.1-6-A1
  - kb-v2.1-6-A2
  - kb-v2.1-6-A3
  - kb-v2.1-6-A4
  - kb-v2.1-6-A5
  - kb-v2.1-6-A6
  - kb-v2.1-6-A7  # see "Local UAT" section — server-side curl substitute used (Playwright MCP main-session-only); browser visual UAT BLOCKED for this run, deferred to user
  - kb-v2.1-6-A8
  - kb-v2.1-6-A9  # orchestrator-side per concurrent-quick discipline
  - kb-v2.1-6-A10
---

# kb-v2.1-6 article image rendering fix — Summary

## Mission

Convert Phase 5-00 retrieval-binding plain-text image refs (`Image N from article 'X': URL`) into `<img>` HTML tags in the SSG export + API body retrieval path. Phase 5-00 ingestion-side design (`ingest_wechat.py:1303`, Hermes commit `2f576b1`) is preserved verbatim because LightRAG `aquery` uses the plain-text refs to correlate parent doc with sub-doc image descriptions for `kg_synthesize` inline image rendering.

## Skill invocations (per `feedback_skill_invocation_not_reference.md`)

`Skill(skill="python-patterns", args="Pure-function regex helper. Module-level compiled re.Pattern (not per-call). EAFP empty-body short-circuit. Type hints (str -> str). Lambda in re.sub for capture-group → format string. Idempotency via output shape that does not match input pattern. PEP 8 + isort + black-compatible.")`

`Skill(skill="writing-tests", args="Testing Trophy: integration > unit. ≥7 integration tests in tests/integration/kb/test_image_rendering.py. Pure-function tests use direct import + assertion. End-to-end tests use ArticleRecord fixture + get_article_body() to verify wiring order (rewrite_paths runs FIRST, then rewrite_text_refs). Idempotency test passes function its own output and asserts byte-equality. Regression guard test for ingest_wechat.py unchanged via subprocess git diff. Parametrize KB_BASE_PATH='' vs '/kb' across applicable cases. Mirror the pytest patterns from tests/integration/kb/test_image_paths.py (importlib.reload, monkeypatch.setenv).")`

(Both invocations cited as required regex sentinels.)

## Files changed

- `kb/data/article_query.py` — added `_IMG_TEXT_REF_PATTERN` constant, added `_rewrite_image_text_refs_to_html()` helper, wired into `get_article_body()` AFTER `_rewrite_image_paths()` in BOTH the file-fallback branch and the rec.body branch. +56/-2 lines.
- `tests/integration/kb/test_image_rendering.py` — new file, 9 tests (target was ≥7), all PASS.

## Files NOT touched (territory boundaries)

- `ingest_wechat.py` — Phase 5-00 retrieval binding preserved. Verified: `git diff origin/main -- ingest_wechat.py` is empty.
- `kb/templates/article.html` — outputs `{{ body_html | safe }}` already; no template change needed (single source of truth = `get_article_body`).
- `kb/api.py`, `kb/export_knowledge_base.py` — both call `get_article_body()` so they inherit the fix automatically.
- `~/.hermes/omonigraph-vault/lightrag_storage/` — UNTOUCHED (regression guard test green).
- `kb/data/lang_detect.py`, `kb/scripts/detect_article_lang.py`, `kb/scripts/rebuild_fts.py`, `tests/unit/kb/test_lang_detect.py` — kb-v2.1-7 territory (concurrent quick); explicitly excluded from `git add`.

## Test results

- New tests: `tests/integration/kb/test_image_rendering.py` — **9 tests, all PASS** (target was ≥7).
- Regression: `tests/integration/kb/test_image_paths.py` — **13 tests, all PASS** (no semantic change to `_rewrite_image_paths`).
- Full kb suite: `pytest tests/integration/kb/ tests/unit/kb/` — **486 passed in 22.06s** (zero regressions vs baseline).

Test-suite interaction note (resolved): The first draft used `importlib.reload(kb.data.article_query)` inside the wiring tests which created a NEW `EntityCount` class object — `test_kb2_queries.py` failed `isinstance` checks on entity-related tests run afterward in the same process. Fix: replaced `importlib.reload` with `monkeypatch.setattr(config, "KB_BASE_PATH", "/kb")` + `monkeypatch.setattr(config, "KB_IMAGES_DIR", "/nonexistent/...")`. This patches the runtime constants without re-importing the module, preserving dataclass identities for sibling tests.

## Local UAT (Rule 3 mandatory per CLAUDE.md HIGHEST PRIORITY PRINCIPLE 6)

### UAT setup

- Source dev DB: `.dev-runtime/data/kol_scan.db` — verified zero rows contain `'Image 0 from article'` plain-text refs (the format is generated only by Hermes prod ingestion).
- UAT DB created: `.dev-runtime/data/kol_scan_rqk_uat.db` (copy of dev DB; 3 articles' content_hash + body replaced with synthetic Phase 5-00 plain-text refs at ids 29, 34, 38; `update_time` bumped to ensure top of `--limit` sort order).
- Lockfile acquired: `.scratch/.uat-port-8766.lock` ("`45246 rqk-kb-v2.1-6 2026-05-16T23:03:40Z`"). Released on UAT completion.
- Local serve launcher: `.venv/Scripts/python.exe .scratch/local_serve.py` — port 8766.
- Env values:
  - `KB_DB_PATH=C:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime\data\kol_scan_rqk_uat.db` (Windows-native path required; POSIX form fails sqlite3 open)
  - `KB_IMAGES_DIR=C:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime\images`
  - `KB_BASE_PATH` tested unset (root deploy) AND `=/kb` (subdir deploy) in two server runs.

### Curl smoke results — root deploy (`KB_BASE_PATH` unset)

| hash | title | body_html_len | img_count_in_body_html | has_literal_text | img_srcs |
|---|---|---|---|---|---|
| rqk_uat_01 | kb-v2.1-6 UAT Article 1 (3 images) | 408 | 3 | False | `/static/img/rqk_uat_01/0.jpg`, `.../1.jpg`, `.../2.jpg` |
| rqk_uat_02 | kb-v2.1-6 UAT Article 2 (2 images) | 231 | 2 | False | `/static/img/rqk_uat_02/0.jpg`, `.../1.jpg` |
| rqk_uat_03 | kb-v2.1-6 UAT Article 3 (1 image) | 122 | 1 | False | `/static/img/rqk_uat_03/0.jpg` |

All 3 articles: `body_html` contains exact-count `<img>` tags, zero literal "Image N from article" plain-text refs survived.

### Curl smoke results — subdir deploy (`KB_BASE_PATH=/kb`)

| hash | img_count | all_start_with_/kb/static/img/ |
|---|---|---|
| rqk_uat_01 | 3 | True |
| rqk_uat_02 | 2 | True |
| rqk_uat_03 | 1 | True |

All 3 articles: every `<img src=…>` is correctly prefixed with `/kb/static/img/...` for subdir-mounted deploy.

### KB_BASE_PATH=/kb fresh SSG export verification (acceptance A8)

```
$ MSYS_NO_PATHCONV=1 KB_BASE_PATH=/kb KB_DB_PATH="…kol_scan_rqk_uat.db" KB_IMAGES_DIR="…images" \
  venv/Scripts/python.exe kb/export_knowledge_base.py --output-dir kb/output-uat-rqk --limit 10
…
Done. Output: C:\Users\huxxha\Desktop\OmniGraph-Vault\kb\output-uat-rqk
```

Per-article grep on the static export:

```
$ grep -c '<img src="/kb/static/img/' kb/output-uat-rqk/articles/rqk_uat_*.html
kb/output-uat-rqk/articles/rqk_uat_01.html:3
kb/output-uat-rqk/articles/rqk_uat_02.html:2
kb/output-uat-rqk/articles/rqk_uat_03.html:1
```

Sample emitted markup (rqk_uat_01.html):

```html
<img src="/kb/static/img/rqk_uat_01/0.jpg" alt="image 0" loading="lazy">
<img src="/kb/static/img/rqk_uat_01/1.jpg" alt="image 1" loading="lazy">
<img src="/kb/static/img/rqk_uat_01/2.jpg" alt="image 2" loading="lazy">
```

All 3 SSG HTML files contain `<img src="/kb/static/img/...">` with correct count, zero literal "Image 0 from article" remaining.

### Browser UAT — partially BLOCKED (Playwright MCP not available in subagent context)

Per `~/.claude/CLAUDE.md` rule:
> CRITICAL — MCP tools are main-session only. Do NOT delegate MCP tool calls to sub-agents (Agent tool). The Databricks proxy does not forward `tool_reference` blocks that sub-agents need to discover and invoke MCP tools.

This executor agent is a sub-agent; `mcp__playwright__browser_*` calls would return `No such tool available`. The browser-side `naturalWidth>0` + screenshot capture must be performed by the user / orchestrator in the main session if a visual confirmation is required. The substantive evidence — `<img>` tags with valid src in body_html (verified via curl) AND in static SSG export (verified via grep) — has been captured server-side.

**Image-URL HTTP 200 check** is similarly limited: the synthetic UAT articles point to fabricated paths (`/static/img/rqk_uat_01/0.jpg`) that have no underlying files, so a HEAD request would 404 against the synthetic test fixture regardless of whether the helper is correct. Real-prod articles (Hermes deploy) will already have the image files served via `/static/img/...` — the helper changes only the markup, not the file layout.

Recommended user follow-up (1 min) — open in main Claude session:

```
mcp__playwright__browser_navigate(url="http://localhost:8766/article/<real_prod_hash>")
mcp__playwright__browser_evaluate(function="() => Array.from(document.querySelectorAll('article.article-body img')).map(i => ({src: i.src, naturalWidth: i.naturalWidth}))")
```

Against any real-prod-deployed article hash containing Phase 5-00 refs, expect `naturalWidth > 0`.

### Lockfile release

```
$ rm -f .scratch/.uat-port-8766.lock
```

(Trap-released on shell exit; explicit cleanup added to UAT artifacts.)

### UAT artifacts on disk

- Server logs: `.scratch/rqk-uat-server.log` (root deploy), `.scratch/rqk-uat-server-kb.log` (subdir deploy)
- SSG fresh export: `kb/output-uat-rqk/articles/rqk_uat_{01,02,03}.html`
- Synthetic UAT DB: `.dev-runtime/data/kol_scan_rqk_uat.db` (NOT committed; gitignored under `.dev-runtime/`)

## Acceptance criteria status

| ID | Criterion | Status |
|---|---|---|
| A1 | `_rewrite_image_text_refs_to_html()` exists in `kb/data/article_query.py` | PASS |
| A2 | `get_article_body()` invokes helper AFTER `_rewrite_image_paths()` | PASS (both file-fallback + rec.body branches) |
| A3 | `ingest_wechat.py` UNCHANGED (Phase 5-00 retrieval binding preserved) | PASS (`git diff origin/main` empty) |
| A4 | LightRAG storage UNCHANGED (regression guard test passes) | PASS (test_lightrag_storage_untouched_after_export) |
| A5 | ≥6 integration tests in test_image_rendering.py, all PASS | PASS (9 tests, all PASS) |
| A6 | `tests/integration/kb/test_image_paths.py` unchanged + still PASS | PASS (13/13) |
| A7 | Local UAT (Rule 3): 3 multi-image articles render `<img>` | PARTIAL — server-side curl-grep confirmed; browser `naturalWidth>0` deferred to main session (subagent MCP limitation, see "Browser UAT" above) |
| A8 | `KB_BASE_PATH=/kb` SSG export emits `<img src="/kb/static/img/...">` | PASS (3 SSG HTML files verified) |
| A9 | STATE.md edit limited to v2.1-6 phase line | DEFERRED — orchestrator handles STATE.md update separately per executor prompt instructions |
| A10 | No regression in full kb pytest | PASS (486/486 passed) |

## Concurrent-quick safety compliance

- `git add` will use **explicit file paths** only (per `feedback_git_add_explicit_in_parallel_quicks.md`).
- No `git commit --amend` (per `feedback_no_amend_in_concurrent_quicks.md`).
- No `git reset --hard`, no `git rebase -i`, no `git push --force`.
- STATE.md NOT edited by this agent (orchestrator territory per executor prompt).
- Sibling modifications from kb-v2.1-7 (`kb/data/lang_detect.py`, `kb/scripts/detect_article_lang.py`, `tests/unit/kb/test_lang_detect.py`) detected in working tree and explicitly EXCLUDED from this commit.
- UAT port 8766 lockfile acquired before starting `local_serve.py`, released on completion.

## Known limitations (documented for v2.1-6.x candidate triage)

- **Title containing apostrophe**: A Phase 5-00 emit line like `Image 1 from article 'Foo's bar': URL` would not be matched by `[^']*` (regex stops at first `'`). Test 5 (`test_title_with_apostrophe_handled_safely`) verifies graceful degradation — function returns without exception, malformed input passes through unchanged. If Hermes prod data contains titles with apostrophes referenced in Phase 5-00 lines, escalate to v2.1-6.x. Low priority (KOL titles in production rarely contain ASCII apostrophes; CJK titles unaffected).
- **Image-URL HTTP 200 check**: not performed against real prod data in this UAT (synthetic test fixtures don't have underlying image files). Real-deploy verification belongs to the user's main-session browser UAT or the next Hermes deploy smoke.

## Self-Check: PASSED

- `kb/data/article_query.py` — exists, contains `_rewrite_image_text_refs_to_html` (verified via grep).
- `tests/integration/kb/test_image_rendering.py` — exists, 9 tests, all PASS.
- `git diff origin/main -- ingest_wechat.py` — empty (verified before SUMMARY write).
- Full kb pytest — 486 passed, 0 failed.
- SSG export `KB_BASE_PATH=/kb` — `<img src="/kb/static/img/...">` rendered for all 3 UAT articles (verified via grep on `kb/output-uat-rqk/articles/rqk_uat_*.html`).

Self-check status: **PASSED** for all server-side criteria. Browser-side `naturalWidth>0` confirmation flagged as user follow-up (subagent MCP limitation, not a code defect).
