---
phase: 260516-rqk-kb-v2-1-6-article-image-rendering-fix
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/data/article_query.py
  - tests/integration/kb/test_image_rendering.py
  - .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md
  - .planning/STATE.md
autonomous: true
requirements:
  - kb-v2.1-6-A1   # _rewrite_image_text_refs_to_html() helper exists in kb/data/article_query.py
  - kb-v2.1-6-A2   # get_article_body() invokes helper AFTER _rewrite_image_paths()
  - kb-v2.1-6-A3   # ingest_wechat.py UNCHANGED (Phase 5-00 retrieval binding preserved)
  - kb-v2.1-6-A4   # LightRAG storage UNCHANGED (regression guard test passes)
  - kb-v2.1-6-A5   # ≥6 integration tests in tests/integration/kb/test_image_rendering.py, all PASS
  - kb-v2.1-6-A6   # tests/integration/kb/test_image_paths.py unchanged + still PASS
  - kb-v2.1-6-A7   # Local UAT (Rule 3): 3 multi-image articles render <img>; naturalWidth>0; image URLs HTTP 200
  - kb-v2.1-6-A8   # KB_BASE_PATH=/kb SSG export emits <img src="/kb/static/img/...">
  - kb-v2.1-6-A9   # STATE.md edit limited to v2.1-6 phase line (concurrent-quick safety)
  - kb-v2.1-6-A10  # No regression in full kb pytest

must_haves:
  truths:
    - "/api/article/{hash} body_html contains <img> tags for Phase 5-00 image refs (no 'Image N from article ...' literal text in rendered output for multi-image articles)"
    - "ingest_wechat.py:1303 line 'Image {i} from article ...' UNCHANGED — Phase 5-00 retrieval binding preserved (verifiable via git diff)"
    - "LightRAG parent doc + sub-doc still contain the plain-text reference line (storage UNTOUCHED — verifiable via grep on lightrag_storage/)"
    - "KB_BASE_PATH=/kb SSG export produces <img src=\"/kb/static/img/...\"> for fresh re-export"
    - "Browser UAT: 3 multi-image article URLs render images with naturalWidth>0 (Playwright MCP browser_evaluate)"
    - "Existing kb-v2.1-2 image-path integration tests still green (no regression on _rewrite_image_paths semantics)"
    - "Function is idempotent: applying _rewrite_image_text_refs_to_html twice on the same body produces identical output"
  artifacts:
    - path: "kb/data/article_query.py"
      provides: "Phase 5-00 → <img> rewrite helper + wiring in get_article_body()"
      contains: "_rewrite_image_text_refs_to_html"
    - path: "tests/integration/kb/test_image_rendering.py"
      provides: "≥6 integration tests covering helper semantics + idempotency + KB_BASE_PATH + LightRAG regression guard"
      min_lines: 60
    - path: ".planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md"
      provides: "Closure doc citing Local UAT evidence (curl status, screenshot paths, browser_evaluate naturalWidth results) + Skill regex (python-patterns + writing-tests)"
  key_links:
    - from: "kb/data/article_query.py:get_article_body()"
      to: "_rewrite_image_text_refs_to_html()"
      via: "function call AFTER _rewrite_image_paths() returns"
      pattern: "_rewrite_image_text_refs_to_html\\(.*\\)"
    - from: "kb/export_knowledge_base.py:render_article_detail()"
      to: "kb/data/article_query.py:get_article_body()"
      via: "existing import (line 308) — no change required, inherits new rewrite"
      pattern: "body_md, body_source = get_article_body\\(rec\\)"
---

<objective>
Convert Phase 5-00 retrieval-binding plain-text image refs ("Image N from article 'X': URL") into <img> HTML tags in the SSG export + API body retrieval path. Fix is export-side ONLY — Phase 5-00 ingestion-side design (Hermes commit 2f576b1) is preserved verbatim because LightRAG aquery uses the plain-text refs to correlate parent doc with sub-doc image descriptions for kg_synthesize inline image rendering.

Purpose: Historic articles in kb/output/articles/{hash}.html currently display image refs as plain text instead of rendered <img> tags. Users see "Image 3 from article 'Foo': /kb/static/img/abc/3.jpg" as literal text. Browser cannot render this. Root cause is at ingest_wechat.py:1303 where retrieval-binding requires plain-text format. Cannot modify ingestion. Must transform at body retrieval / export time.

Output: One new helper function (_rewrite_image_text_refs_to_html), one wiring line in get_article_body(), ≥6 integration tests, validated via Local UAT (Rule 3 mandatory) on 3 multi-image articles.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@kb/data/article_query.py
@kb/export_knowledge_base.py
@kb/templates/article.html
@tests/integration/kb/test_image_paths.py

<root_cause>
Phase 5-00 retrieval binding (Hermes commit 2f576b1, ingest_wechat.py:1300-1310):

```python
processed_images = []
for i, (url_img, path) in enumerate(url_to_path.items()):
    local_url = f"http://localhost:8765/{article_hash}/{path.name}"
    full_content += f"\n\nImage {i} from article '{title}': {local_url}"
    processed_images.append({"index": i, "local_url": local_url})
```

This `Image {i} from article '{title}': {local_url}` line is INTENTIONAL — it lives in:
- The parent LightRAG doc (full article body)
- The sub-doc inserted by background _vision_worker_impl (image descriptions: `[image N]: desc (URL)`)

LightRAG aquery() in kg_synthesize correlates the two via this exact plain-text format → enables inline image embedding in synthesis output.

DO NOT MODIFY ingest_wechat.py. DO NOT MODIFY LightRAG storage.
</root_cause>

<call_chain_for_ssg>
1. kb/export_knowledge_base.py:308 — `body_md, body_source = get_article_body(rec)`
2. kb/data/article_query.py:407 — `get_article_body(rec)` reads markdown (file fallback OR rec.body)
3. kb/data/article_query.py:429 — calls `_rewrite_image_paths(md, base_path)` (kb-v2.1-2 EXPORT-05)
4. kb/data/article_query.py:431 — returns rewritten md
5. kb/export_knowledge_base.py:309 — `body_html = _annotate_code_block_lang_label(_render_body_html(body_md))` (markdown → HTML)
6. kb/templates/article.html:116 — `{{ body_html | safe }}`

The fix point is Step 3 — add `_rewrite_image_text_refs_to_html()` AFTER `_rewrite_image_paths()`. This way:
- Image URLs already have correct prefix (KB_BASE_PATH applied first)
- Markdown processor (Step 5) sees raw <img> HTML (not markdown image syntax) → passes through verbatim because Markdown allows raw HTML

The fix is single source of truth: kb/api.py also imports and calls get_article_body(), so the FastAPI endpoint inherits the fix automatically — no separate edit needed.
</call_chain_for_ssg>

<helper_implementation>
Insert in kb/data/article_query.py near line 364 (next to existing _IMAGE_SERVER_REWRITE / _rewrite_image_paths):

```python
# kb-v2.1-6: Phase 5-00 retrieval-binding plain-text image refs
# (ingest_wechat.py:1303 — DO NOT MODIFY ingestion; this is the export-side bridge).
# Format emitted by ingestion: "Image {N} from article '{title}': {local_url}"
# After _rewrite_image_paths runs, {local_url} has been rewritten to the deploy
# URL (e.g. "/static/img/abc/0.jpg" or "/kb/static/img/abc/0.jpg"); this regex
# converts the plain-text line into a real <img> tag for browser rendering.
#
# Single-quote in title is permitted (greedy match the URL up to next whitespace).
_IMG_TEXT_REF_PATTERN = re.compile(
    r"Image (\d+) from article '([^']*)': (\S+)"
)


def _rewrite_image_text_refs_to_html(body: str) -> str:
    """Convert Phase 5-00 retrieval-binding plain-text image refs into <img> tags.

    Phase 5-00 (Hermes 2f576b1) emits each downloaded image as a plain-text
    line in the article body so LightRAG aquery can correlate the parent doc
    with the sub-doc image descriptions during kg_synthesize. SSG export +
    /api/article/{hash} need <img> tags for browser rendering. This function
    is the export-side bridge.

    Idempotent: <img> output does not contain the literal "Image N from article"
    so the regex won't re-match.

    Caller order: invoke AFTER _rewrite_image_paths() so URL prefix is already
    correct for the deployment target (KB_BASE_PATH).

    Pure function — no I/O, no global mutation. Safe to call from anywhere
    that has body markdown post-_rewrite_image_paths.
    """
    if not body:
        return body
    return _IMG_TEXT_REF_PATTERN.sub(
        lambda m: f'<img src="{m.group(3)}" alt="image {m.group(1)}" loading="lazy">',
        body,
    )
```

Wire into get_article_body() — modify lines 425-431 to call the new helper AFTER _rewrite_image_paths:

```python
def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]:
    base_path = config.KB_BASE_PATH
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = images_dir / url_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = _rewrite_image_paths(md, base_path)
            md = _rewrite_image_text_refs_to_html(md)   # kb-v2.1-6
            return md, "vision_enriched"
    body = rec.body or ""
    body = _rewrite_image_paths(body, base_path)
    body = _rewrite_image_text_refs_to_html(body)        # kb-v2.1-6
    return body, "raw_markdown"
```
</helper_implementation>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Helper + wiring + tests + Local UAT (single atomic task)</name>
  <files>
    kb/data/article_query.py,
    tests/integration/kb/test_image_rendering.py,
    .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md,
    .planning/STATE.md
  </files>
  <behavior>
    Per writing-tests Trophy (integration > unit), tests/integration/kb/test_image_rendering.py covers ≥7 cases:

    1. test_plain_text_ref_converted_to_img_tag
       - Input body: "Image 3 from article 'Foo': /static/img/abc/3.jpg"
       - Expect: contains '<img src="/static/img/abc/3.jpg" alt="image 3" loading="lazy">'
       - Expect: does NOT contain literal "Image 3 from article 'Foo':"

    2. test_rewrite_idempotent_on_already_converted_body
       - Apply helper twice to same input; assert byte-equality of output

    3. test_kb_base_path_subdir_deploy_renders_kb_prefix_in_img_src
       - Use ArticleRecord with body containing 'Image 0 from article ...: http://localhost:8765/h/0.jpg'
       - Set KB_BASE_PATH=/kb (monkeypatch + reload kb.config); call get_article_body(rec)
       - Expect output contains '<img src="/kb/static/img/h/0.jpg" alt="image 0" loading="lazy">'
       - Verifies _rewrite_image_paths runs FIRST, then _rewrite_image_text_refs_to_html

    4. test_multi_image_article_emits_one_img_tag_per_ref
       - Body has 3 Phase 5-00 lines (i=0,1,2)
       - Expect output.count('<img ') == 3
       - Expect each src attribute matches the corresponding original URL

    5. test_title_with_apostrophe_handled_safely
       - Body line: "Image 1 from article 'Foo': /static/img/x/1.jpg" (title has no apostrophe — current Phase 5-00 emit format uses single quotes around title; if title itself has apostrophe the line would have '...Foo's...' which our [^']* pattern stops short of capturing — DOCUMENT this as known limitation; assert no crash and input unchanged)
       - Expect: function returns without exception
       - Expect: malformed input passes through unchanged (graceful degradation)

    6. test_existing_markdown_image_syntax_not_double_wrapped
       - Body contains both: "![alt](/static/img/abc/0.jpg)" markdown AND "Image 0 from article 'X': /static/img/abc/0.jpg" plain-text
       - After helper: markdown image syntax UNCHANGED; only plain-text ref converted
       - Markdown processor renders the ![alt]() to <img> in next step (not our concern)

    7. test_lightrag_storage_untouched_after_export (regression guard for Phase 5-00)
       - Verify ingest_wechat.py source contains the literal: 'Image {i} from article'
       - Verify our helper module does NOT modify or reference ~/.hermes/omonigraph-vault/lightrag_storage/
       - Use git rev-parse to confirm ingest_wechat.py is unchanged vs origin/main:
         `subprocess.run(['git', 'diff', 'origin/main', '--', 'ingest_wechat.py'], capture_output=True)` → stdout empty
  </behavior>

  <action>
    **STEP 0 — Concurrent-quick safety prologue (BEFORE touching files):**

    1. Confirm we are on main, pulled to latest:
       ```bash
       git fetch origin main && git status -sb
       git log --oneline -3
       ```
       If local main is ahead of origin/main with non-260516-rqk commits, STOP and report.

    2. Acquire UAT port lockfile (collision with kb-v2.1-7):
       ```bash
       LOCK=".scratch/.uat-port-8766.lock"
       mkdir -p .scratch
       for i in 1 2 3; do
         if [ ! -e "$LOCK" ]; then
           echo "$$ rqk-kb-v2.1-6 $(date -u +%FT%TZ)" > "$LOCK"
           # Re-check to defeat TOCTOU racing with kb-v2.1-7 quick:
           grep -q "rqk-kb-v2.1-6" "$LOCK" || { echo "lost race"; sleep 60; continue; }
           break
         fi
         echo "lock held: $(cat $LOCK); waiting 60s (attempt $i/3)"
         sleep 60
       done
       [ -e "$LOCK" ] && grep -q "rqk-kb-v2.1-6" "$LOCK" || { echo "BLOCKED: another quick holds .uat-port-8766.lock"; exit 1; }
       trap "rm -f .scratch/.uat-port-8766.lock" EXIT
       ```

    **STEP 1 — Invoke skills (per feedback_skill_invocation_not_reference.md):**

    Skill(skill="python-patterns", args="Pure-function regex helper. Module-level compiled re.Pattern (not per-call). EAFP empty-body short-circuit. Type hints (str -> str). Lambda in re.sub for capture-group → format string. Idempotency via output shape that does not match input pattern. PEP 8 + isort + black-compatible.")

    Skill(skill="writing-tests", args="Testing Trophy: integration > unit. ≥6 integration tests in tests/integration/kb/test_image_rendering.py. Pure-function tests use direct import + assertion. End-to-end tests use ArticleRecord fixture + get_article_body() to verify wiring order (rewrite_paths runs FIRST, then rewrite_text_refs). Idempotency test passes function its own output and asserts byte-equality. Regression guard test for ingest_wechat.py unchanged via subprocess git diff. Parametrize KB_BASE_PATH='' vs '/kb' across applicable cases. Mirror the pytest patterns from tests/integration/kb/test_image_paths.py (importlib.reload, monkeypatch.setenv).")

    **STEP 2 — Implement helper in kb/data/article_query.py:**

    Per <helper_implementation> block above:
    - Add `_IMG_TEXT_REF_PATTERN` module-level constant + `_rewrite_image_text_refs_to_html()` function near line 364 (next to existing `_IMAGE_SERVER_REWRITE` / `_rewrite_image_paths`).
    - Modify `get_article_body()` to call the new helper AFTER `_rewrite_image_paths()` in BOTH the file-fallback branch (line 429) AND the rec.body branch (line 431).
    - DO NOT modify any other function. DO NOT touch ingest_wechat.py. DO NOT touch LightRAG storage.

    **STEP 3 — Write tests (TDD: write tests, run, expect FAIL on cases 1-6 before implementation; case 7 is independent of helper):**

    Create tests/integration/kb/test_image_rendering.py per <behavior> above. Mirror the structure from tests/integration/kb/test_image_paths.py:
    - Module docstring with both Skill(skill="python-patterns", args="...") and Skill(skill="writing-tests", args="...") regex sentinels (per feedback_skill_invocation_not_reference.md these regex sentinels are the auditable artifact).
    - Pure-function tests (no fixture_db needed) for cases 1, 2, 6.
    - HTTP / ArticleRecord-level tests for cases 3, 4, 5 — reuse fixture_db pattern.
    - Regression guard test (case 7) using subprocess.run(['git', 'diff', 'origin/main', '--', 'ingest_wechat.py']).

    Run tests:
    ```bash
    .venv/Scripts/python.exe -m pytest tests/integration/kb/test_image_rendering.py -v
    ```
    All ≥6 tests must PASS.

    **STEP 4 — No-regression run on existing tests:**

    ```bash
    .venv/Scripts/python.exe -m pytest tests/integration/kb/test_image_paths.py -v
    .venv/Scripts/python.exe -m pytest tests/ -k "kb" -v 2>&1 | tail -50
    ```
    All previously-green tests stay green.

    **STEP 5 — Local UAT (Rule 3 MANDATORY per CLAUDE.md HIGHEST PRIORITY PRINCIPLE 6):**

    Pick 3 known multi-image article hashes (use SQL to find articles with body containing "Image 0 from article"):
    ```bash
    KB_DB_PATH=.dev-runtime/data/kol_scan.db .venv/Scripts/python.exe -c "
    import sqlite3
    c = sqlite3.connect('.dev-runtime/data/kol_scan.db')
    rows = c.execute(\"SELECT content_hash, title FROM articles WHERE body LIKE '%Image 0 from article%' AND content_hash IS NOT NULL LIMIT 3\").fetchall()
    for h, t in rows: print(h, '|', t[:60])
    "
    ```
    Save the 3 hashes as $HASH1, $HASH2, $HASH3.

    Start local serve on port 8766:
    ```bash
    .venv/Scripts/python.exe .scratch/local_serve.py &
    sleep 5
    ```

    Smoke 3 articles via curl:
    ```bash
    for H in $HASH1 $HASH2 $HASH3; do
      echo "=== /api/article/$H ==="
      curl -s "http://localhost:8766/api/article/$H" | .venv/Scripts/python.exe -c "
    import json, sys
    d = json.load(sys.stdin)
    bh = d.get('body_html', '')
    n = bh.count('<img ')
    has_literal = 'Image 0 from article' in bh
    print(f'  body_html len={len(bh)} img_count={n} has_literal_text={has_literal}')
    "
    done
    ```
    Expect: img_count >= 1 for each, has_literal_text=False for each.

    KB_BASE_PATH=/kb fresh SSG export verification:
    ```bash
    rm -rf kb/output-uat-rqk
    KB_BASE_PATH=/kb KB_DB_PATH=.dev-runtime/data/kol_scan.db .venv/Scripts/python.exe kb/export_knowledge_base.py --output-dir kb/output-uat-rqk --limit 50
    grep -c '<img src="/kb/static/img/' kb/output-uat-rqk/articles/*.html | grep -v ':0$' | head -5
    ```
    Expect: ≥1 article HTML files contain `<img src="/kb/static/img/...`.

    Browser UAT via Playwright MCP (in main session, NOT sub-agent):
    ```
    mcp__playwright__browser_navigate(url="http://localhost:8766/article/$HASH1")
    mcp__playwright__browser_take_screenshot(filename=".playwright-mcp/kb-v2-1-6-article-$HASH1.png", fullPage=True)
    mcp__playwright__browser_evaluate(function="() => Array.from(document.querySelectorAll('article.article-body img')).map(i => ({src: i.src, naturalWidth: i.naturalWidth, naturalHeight: i.naturalHeight, alt: i.alt}))")
    ```
    Expect: every img has naturalWidth > 0 and naturalHeight > 0. Repeat for $HASH2, $HASH3.

    Curl each unique image URL → HTTP 200 + Content-Type image/*:
    ```bash
    # extract first 3 unique img srcs from /api/article/$HASH1 body_html, curl HEAD each
    for SRC in $(curl -s "http://localhost:8766/api/article/$HASH1" | .venv/Scripts/python.exe -c "
    import json, sys, re
    d = json.load(sys.stdin)
    print('\n'.join(re.findall(r'<img src=\"([^\"]+)\"', d['body_html'])[:3]))
    "); do
      curl -sI "http://localhost:8766$SRC" | head -3
    done
    ```

    Mobile viewport screenshot:
    ```
    mcp__playwright__browser_resize(width=375, height=667)
    mcp__playwright__browser_navigate(url="http://localhost:8766/article/$HASH1")
    mcp__playwright__browser_take_screenshot(filename=".playwright-mcp/kb-v2-1-6-article-$HASH1-mobile.png", fullPage=True)
    ```

    Stop local serve + release lockfile (trap on EXIT handles this).

    **STEP 6 — Write SUMMARY.md** at `.planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md`:
    - Mission + root cause recap (Phase 5-00 retrieval binding preserved)
    - Files changed (kb/data/article_query.py only — production code change)
    - Test results (≥6 tests PASS, full kb pytest no regression)
    - Local UAT evidence section (Rule 3 mandatory):
      - Local serve launcher: `.venv/Scripts/python.exe .scratch/local_serve.py`
      - Env values: KB_DB_PATH=.dev-runtime/data/kol_scan.db, KB_BASE_PATH variants tested
      - Curl smoke results table: hash | img_count_in_body_html | has_literal_text (False expected)
      - Browser_evaluate naturalWidth output for 3 articles (paste raw JSON)
      - Image URL HEAD response status + Content-Type
      - Screenshot paths: .playwright-mcp/kb-v2-1-6-article-{hash1,hash2,hash3}.png + -mobile variants
      - SSG export verification: KB_BASE_PATH=/kb grep count
    - Acceptance criteria checklist (all 12 items)
    - Skill regex (mandatory): both `Skill(skill="python-patterns", args="...")` and `Skill(skill="writing-tests", args="...")` quoted verbatim with the args used
    - Concurrent safety: confirm STATE.md edit limited to v2.1-6 phase line, no -A in git add, no amend used
    - Known limitation: title containing apostrophe (Phase 5-00 line "Image 1 from article 'Foo's bar': URL") — `[^']*` pattern stops at first `'`, so URL capture would fail. Document as low-priority; if observed in prod data, escalate to v2.1-6.x. Test 5 verifies graceful pass-through.

    **STEP 7 — STATE.md surgical update:**

    Open .planning/STATE.md, find the kb-v2.1-6 phase line (or append new one if absent):
    ```
    | kb-v2.1-6 | article image rendering fix | DONE | 260516-rqk | <commit-hash-after-commit> |
    ```
    DO NOT touch any other phase line. DO NOT rewrite STATE.md whole.

    **STEP 8 — Commit (forward-only, explicit file list, NO -A, NO --amend):**

    ```bash
    git add kb/data/article_query.py tests/integration/kb/test_image_rendering.py .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-PLAN.md .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md .playwright-mcp/kb-v2-1-6-article-*.png
    git commit -m "fix(kb-v2.1-6): convert Phase 5-00 image text refs to <img> tags in SSG export

    Historic article body retrieval path now wraps Phase 5-00 retrieval-binding
    plain-text image refs (Image N from article 'X': URL) into <img> HTML tags
    for browser rendering. Phase 5-00 ingestion design (ingest_wechat.py:1303,
    Hermes commit 2f576b1) is PRESERVED — LightRAG aquery still uses the
    plain-text format to correlate parent doc with sub-doc image descriptions.

    Single source of truth: _rewrite_image_text_refs_to_html() in
    kb/data/article_query.py runs AFTER _rewrite_image_paths() inside
    get_article_body(). SSG (kb/export_knowledge_base.py) and FastAPI
    (kb/api.py) both inherit the fix via the shared get_article_body() call.

    Tests: 7 integration tests in tests/integration/kb/test_image_rendering.py.
    Local UAT (Rule 3): 3 multi-image articles validated, naturalWidth>0,
    image URLs HTTP 200. Screenshots in .playwright-mcp/."
    ```

    Backfill commit hash to STATE.md:
    ```bash
    HASH=$(git rev-parse HEAD)
    sed -i "s/<commit-hash-after-commit>/${HASH:0:8}/" .planning/STATE.md
    git add .planning/STATE.md
    git commit -m "docs(kb-v2.1-6): backfill commit hash in STATE.md"
    ```

    Push (with collision handling):
    ```bash
    git push origin main || (
      git fetch origin main &&
      git merge --ff-only origin/main &&
      git push origin main
    )
    ```
    If ff-merge fails on STATE.md conflict: keep our v2.1-6 line, take incoming for other phase lines, `git add .planning/STATE.md && git commit -m "merge: integrate concurrent STATE.md updates" && git push origin main`. NEVER `--force`, NEVER `--amend`, NEVER `git reset --hard`.
  </action>

  <verify>
    <automated>.venv/Scripts/python.exe -m pytest tests/integration/kb/test_image_rendering.py tests/integration/kb/test_image_paths.py -v</automated>
  </verify>

  <done>
    1. _rewrite_image_text_refs_to_html() exists in kb/data/article_query.py with type hints + docstring
    2. get_article_body() calls it AFTER _rewrite_image_paths() in BOTH branches (file fallback + rec.body)
    3. ingest_wechat.py UNCHANGED: `git diff origin/main -- ingest_wechat.py` returns empty
    4. LightRAG storage UNTOUCHED: no edits under ~/.hermes/omonigraph-vault/lightrag_storage/
    5. tests/integration/kb/test_image_rendering.py has ≥6 (target: 7) tests, all PASS
    6. tests/integration/kb/test_image_paths.py unchanged + still PASS
    7. Local UAT (Rule 3): 3 multi-image articles render <img>; naturalWidth > 0 reported by browser_evaluate; image URLs HTTP 200 + Content-Type image/*; screenshots saved
    8. KB_BASE_PATH=/kb fresh SSG export emits `<img src="/kb/static/img/...">` (grep count ≥1)
    9. STATE.md edit limited to kb-v2.1-6 phase line (verify via `git diff HEAD~2 -- .planning/STATE.md`)
    10. No regression in `pytest tests/ -k "kb"`
    11. SUMMARY.md contains both `Skill(skill="python-patterns", args="...")` and `Skill(skill="writing-tests", args="...")` regex (verifiable via grep)
    12. Forward-only commits: 1 main + 1 STATE backfill, no --amend, no -A in git add (verify `git log --oneline -3`); ff-merge if push collision
  </done>
</task>

</tasks>

<verification>
Per task 1's <verify> block: pytest passes on test_image_rendering.py (≥7 cases) AND test_image_paths.py (no regression).

Cross-checks:
- `git diff origin/main -- ingest_wechat.py` → empty (Phase 5-00 untouched)
- `grep "Image 0 from article" kb/output-uat-rqk/articles/*.html` → 0 occurrences (all converted)
- `grep "<img src=\"/kb/static/img/" kb/output-uat-rqk/articles/*.html | wc -l` → ≥1
- `.playwright-mcp/kb-v2-1-6-article-*.png` exists for 3 hashes (desktop + mobile)
- `grep "Skill(skill=\"python-patterns\"" .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md` → match
- `grep "Skill(skill=\"writing-tests\"" .planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md` → match
- `git log --oneline -3` → 2 forward commits, no --amend
</verification>

<success_criteria>
All 12 acceptance criteria from the task brief satisfied:

1. Helper exists in kb/data/article_query.py
2. get_article_body() calls it AFTER _rewrite_image_paths()
3. ingest_wechat.py UNCHANGED
4. LightRAG storage UNCHANGED (regression guard test green)
5. ≥6 tests in tests/integration/kb/test_image_rendering.py, all PASS
6. tests/integration/kb/test_image_paths.py unchanged + PASS
7. Local UAT done + cited in SUMMARY.md (3 articles, naturalWidth>0, HTTP 200, screenshots)
8. KB_BASE_PATH=/kb SSG export emits `<img src="/kb/static/img/...">`
9. STATE.md edit limited to v2.1-6 phase line
10. No regression in full kb pytest
11. Skill regex (python-patterns + writing-tests) in SUMMARY.md
12. Forward-only commits + ff-merge if collision

Plus Rule 3 (KB Local UAT mandatory) compliance verified by SUMMARY.md UAT evidence section.
</success_criteria>

<concurrent_quick_safety>
**CAVEAT 1 — STATE.md edit discipline (concurrent with kb-v2.1-7 + possibly kdb-1.5):**
- Add/modify ONLY the kb-v2.1-6 phase line. NEVER rewrite STATE.md whole.
- Push collision handling: `git fetch origin main && git merge --ff-only origin/main && git push origin main`.
- ABSOLUTELY FORBIDDEN: `git reset --hard origin/main`, `git rebase -i`, `git push --force`, `git commit --amend`.
- If ff-merge has conflict in STATE.md: keep our v2.1-6 line, take incoming for others, `git add .planning/STATE.md && git commit -m "merge: ..." && push`.

**CAVEAT 2 — UAT port 8766 lockfile (collision with kb-v2.1-7):**
- Lockfile: `.scratch/.uat-port-8766.lock`
- Acquire BEFORE starting `local_serve.py`. Wait 60s × max 3 retries; STOP + report blocked if exhausted.
- TOCTOU defeat: write to lock then `grep` the lock file to confirm we won the race.
- Trap-release on shell exit.

**git add discipline (per feedback_git_add_explicit_in_parallel_quicks.md):**
- Use `git add <explicit-paths>` ONLY. NEVER `git add -A` / `git add .`.

**Per feedback_no_amend_in_concurrent_quicks.md:**
- NO `git commit --amend`. Use forward-only follow-up commits to backfill commit hashes into STATE.md.
</concurrent_quick_safety>

<output>
After completion, create `.planning/quick/260516-rqk-kb-v2-1-6-article-image-rendering-fix/260516-rqk-SUMMARY.md` with full UAT evidence + Skill regex + acceptance checklist.
</output>
