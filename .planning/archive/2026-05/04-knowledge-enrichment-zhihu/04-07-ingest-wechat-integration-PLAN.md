---
phase: 04-knowledge-enrichment-zhihu
plan: 07
type: execute
wave: 5
depends_on: [04-01, 04-04, 04-06]
files_modified:
  - config.py
  - ingest_wechat.py
  - skills/omnigraph_ingest/SKILL.md
  - enrichment/fetch_zhihu.py
  - enrichment/merge_and_ingest.py
autonomous: false
requirements: [D-07, D-12-REVISED]
must_haves:
  truths:
    - "config.py has all 8 Phase 4 ENRICHMENT_* + ZHIHAO_SKILL_NAME + IMAGE_SERVER_BASE_URL keys per RESEARCH.md §9"
    - "config.py ENRICHMENT_LLM_MODEL is 'gemini-2.5-flash' (D-12-REVISED: flash, not flash-lite; flash-lite 20/day quota empirically unusable per Wave 4 test)"
    - "config.py introduces INGEST_LLM_MODEL = 'gemini-2.5-flash' for LightRAG entity extraction + image-vision paths"
    - "ingest_wechat.py writes articles.enriched = -1 for articles < ENRICHMENT_MIN_LENGTH chars"
    - "ingest_wechat.py does NOT add a --enrich flag (D-07 supersession)"
    - "ingest_wechat.py replaces all 3 hardcoded 'gemini-2.5-flash-lite' strings with INGEST_LLM_MODEL import from config (D-12-REVISED)"
    - "ingest_wechat.py calls batch_scan_kol.init_db(DB_PATH) at module import so the _ensure_column migration runs on every deploy (closes Wave 3 deployment gap)"
    - "enrichment/fetch_zhihu.py and enrichment/merge_and_ingest.py pop GOOGLE_GENAI_USE_VERTEXAI before any genai.Client (matches extract_questions.py pattern; fixes test report blocker 1)"
    - "ingest_wechat.py ingests un-enriched articles itself; enrichment happens via the enrich_article skill layer (not embedded in Python)"
    - "skills/omnigraph_ingest/SKILL.md no longer documents an --enrich flag"
    - "Remote E2E: rerun merge_and_ingest on the 8ac04218b4 fixtures captured during Wave 4 test → acceptance criteria 7-12 from 04-06-test-results.md all flip to PASS"
  artifacts:
    - path: "config.py"
      provides: "Phase 4 enrichment configuration keys"
      contains: "ENRICHMENT_LLM_MODEL"
    - path: "ingest_wechat.py"
      provides: "WeChat ingest with short-article enriched=-1 marker"
      contains: "ENRICHMENT_MIN_LENGTH"
    - path: "skills/omnigraph_ingest/SKILL.md"
      provides: "Updated skill body — no --enrich flag documentation"
  key_links:
    - from: "config.py"
      to: "ENRICHMENT_MIN_LENGTH and ENRICHMENT_MAX_QUESTIONS constants"
      via: "module-level assignments"
      pattern: "ENRICHMENT_MIN_LENGTH = 2000"
    - from: "ingest_wechat.py"
      to: "articles.enriched = -1 for short articles"
      via: "SQLite UPDATE after length check"
      pattern: "enriched = -1|enriched=-1"
---

<objective>
Finalize Phase 4 integration: add all enrichment config keys to `config.py`,
update `ingest_wechat.py` to mark short articles (<2000 chars) as `enriched=-1`
per D-07, and strip any `--enrich` flag documentation from
`skills/omnigraph_ingest/SKILL.md` (D-07 supersedes the flag).

CRITICAL design note: enrichment runs OUTSIDE `ingest_wechat.py`, not inside.
The Hermes `enrich_article` skill (plan 06) owns the full flow: it calls
`extract_questions.py`, drives the per-question loop, then calls
`merge_and_ingest.py` which handles LightRAG + SQLite. `ingest_wechat.py`'s
job is reduced to: scrape the article and mark the length-based short-skip.

Purpose: Close out Phase 4 by wiring config + preserving D-07's "enrichment is
the default path" semantics without the superseded flag.

Output: Updated config.py, minimally modified ingest_wechat.py (just the
enriched=-1 marker + content_hash write), cleaned omnigraph_ingest/SKILL.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-01-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-04-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-06-SUMMARY.md
@config.py
@ingest_wechat.py
@skills/omnigraph_ingest/SKILL.md

<interfaces>
RESEARCH.md §9 — exact config.py additions block (verbatim, minus the supersession comments):

```python
# === Phase 4: Knowledge Enrichment ===

ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"
ENRICHMENT_MIN_LENGTH = 2000
ENRICHMENT_MAX_QUESTIONS = 3
ENRICHMENT_LLM_MODEL = "gemini-2.5-flash-lite"
ENRICHMENT_GROUNDING_ENABLED = True
ENRICHMENT_HAOWEN_TIMEOUT = 120
ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60
ENRICHMENT_BASE_DIR = BASE_DIR / "enrichment"
ZHIHAO_SKILL_NAME = "zhihu-haowen-enrich"
IMAGE_SERVER_BASE_URL = "http://localhost:8765"
```

Current config.py contents end at line 37 (Gemini env var cleanup block). New
keys go AFTER line 37.

D-07 enriched state machine:
- 0 = pending (default for new)
- 2 = success (partial >= 1 q) — set by merge_and_ingest.py
- -1 = skipped (< 2000 chars) — SET HERE in ingest_wechat.py
- -2 = all fail — set by merge_and_ingest.py

ingest_wechat.py currently does NOT write enriched=-1. The length check + UPDATE
must be added when the scrape completes and the article is ingested without
enrichment.

Where in ingest_wechat.py to add the length check: after `full_content` is
assembled and before (or right after) `rag.ainsert(full_content)`. Currently
around line 680.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 7.1: Add Phase 4 config keys to config.py (D-12-REVISED: flash, not flash-lite)</name>
  <files>config.py</files>
  <read_first>
    - config.py (entire file — to see the insertion point at line 36)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §9 (original keys)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-12 (Gemini not DeepSeek)
    - docs/testing/04-06-test-results.md §"Recommendations" (flash-lite 20/day empirically unusable; use flash 250/day)
  </read_first>
  <action>
    Append the Phase 4 enrichment config block to `config.py`, AFTER the existing
    line `os.environ.pop("GOOGLE_CLOUD_LOCATION", None)` (currently line 36).

    IMPORTANT: This is REVISED from RESEARCH.md §9. The Wave 4 live E2E test
    (docs/testing/04-06-test-results.md) proved that `gemini-2.5-flash-lite`
    free tier (20 RPD) is exhausted by a single article's LightRAG entity
    extraction + image vision + question extraction pipeline. Use
    `gemini-2.5-flash` (250 RPD) instead. D-12 stands (Gemini over DeepSeek),
    but the specific model choice is superseded to flash.

    Exact content to append (after a blank line):

    ```python

    # === Phase 4: Knowledge Enrichment ===
    # Master switch. Per D-07 this is always True in production; the key exists
    # so that individual invocations can set ENRICHMENT_ENABLED=0 to bypass.
    ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

    # Article character threshold below which extraction is skipped (enriched=-1).
    ENRICHMENT_MIN_LENGTH = 2000

    # Maximum questions per article.
    ENRICHMENT_MAX_QUESTIONS = 3

    # LLM for extract_questions. D-12-REVISED: flash (250/day), not flash-lite
    # (20/day). Live E2E test 2026-04-27 proved flash-lite quota insufficient.
    ENRICHMENT_LLM_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", "gemini-2.5-flash")

    # LLM for the ingest path: LightRAG entity extraction + image-vision in
    # ingest_wechat.py / image_pipeline.py. Separate from ENRICHMENT_LLM_MODEL
    # so either path can be tuned independently. D-12-REVISED: flash default.
    INGEST_LLM_MODEL = os.environ.get("INGEST_LLM_MODEL", "gemini-2.5-flash")

    # Enable google_search grounding tool on the extract_questions call (D-12).
    ENRICHMENT_GROUNDING_ENABLED = True

    # Per-question 好问 search timeout (PRD §8).
    ENRICHMENT_HAOWEN_TIMEOUT = 120

    # Per-question Zhihu source-article fetch timeout (PRD §8).
    ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60

    # Artifact root (D-03). Hermes skill writes per-question subdirs here.
    ENRICHMENT_BASE_DIR = BASE_DIR / "enrichment"

    # Hermes skill name for Zhihu 好问 (referenced by the top-level skill body).
    ZHIHAO_SKILL_NAME = "zhihu-haowen-enrich"

    # Local image server (reused for Zhihu article images).
    IMAGE_SERVER_BASE_URL = "http://localhost:8765"
    ```

    Do NOT modify any existing keys (BASE_DIR, RAG_WORKING_DIR, etc.). Strictly
    additive.
  </action>
  <verify>
    <automated>python -c "import config; assert config.ENRICHMENT_LLM_MODEL == 'gemini-2.5-flash'; assert config.INGEST_LLM_MODEL == 'gemini-2.5-flash'; assert config.ENRICHMENT_MIN_LENGTH == 2000; assert config.ENRICHMENT_MAX_QUESTIONS == 3; assert config.ENRICHMENT_BASE_DIR.name == 'enrichment'; assert config.ZHIHAO_SKILL_NAME == 'zhihu-haowen-enrich'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "ENRICHMENT_ENABLED = " config.py` succeeds
    - `grep -q "ENRICHMENT_MIN_LENGTH = 2000" config.py` succeeds
    - `grep -q "ENRICHMENT_MAX_QUESTIONS = 3" config.py` succeeds
    - `grep -qE "ENRICHMENT_LLM_MODEL.*gemini-2\\.5-flash\"" config.py` succeeds AND `! grep -q "flash-lite" config.py` (D-12-REVISED enforced)
    - `grep -qE "INGEST_LLM_MODEL.*gemini-2\\.5-flash\"" config.py` succeeds (new key)
    - `grep -q "ENRICHMENT_GROUNDING_ENABLED = True" config.py` succeeds
    - `grep -q "ENRICHMENT_HAOWEN_TIMEOUT = 120" config.py` succeeds
    - `grep -q "ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60" config.py` succeeds
    - `grep -q "ENRICHMENT_BASE_DIR = BASE_DIR / \"enrichment\"" config.py` succeeds
    - `grep -q "ZHIHAO_SKILL_NAME = \"zhihu-haowen-enrich\"" config.py` succeeds
    - `grep -q "IMAGE_SERVER_BASE_URL = \"http://localhost:8765\"" config.py` succeeds
    - `grep -q "deepseek" config.py` returns NO matches
    - `python -c "import config"` exits 0
    - All 11 new keys importable: `python -c "from config import ENRICHMENT_ENABLED, ENRICHMENT_MIN_LENGTH, ENRICHMENT_MAX_QUESTIONS, ENRICHMENT_LLM_MODEL, INGEST_LLM_MODEL, ENRICHMENT_GROUNDING_ENABLED, ENRICHMENT_HAOWEN_TIMEOUT, ENRICHMENT_ZHIHU_FETCH_TIMEOUT, ENRICHMENT_BASE_DIR, ZHIHAO_SKILL_NAME, IMAGE_SERVER_BASE_URL; print('ok')"` exits 0
  </acceptance_criteria>
  <done>config.py has all 11 new keys (10 original + new INGEST_LLM_MODEL); flash model default; no flash-lite references</done>
</task>

<task type="auto">
  <name>Task 7.2: ingest_wechat.py — enriched=-1 marker + INGEST_LLM_MODEL swap + SQLite auto-migrate</name>
  <files>ingest_wechat.py</files>
  <read_first>
    - ingest_wechat.py entire file (current state — line 36 imports config; lines 95-121 and 505 use hardcoded flash-lite; line 681+ has SQLite UPDATE block)
    - config.py (to see ENRICHMENT_MIN_LENGTH + INGEST_LLM_MODEL just added)
    - batch_scan_kol.py (init_db + _ensure_column helper — signature: init_db(db_path: Path | str) -> None)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-07 (enriched=-1 semantics)
    - docs/testing/04-06-test-results.md §"Step 4" (proves flash-lite quota blocks LightRAG entity extraction)
    - .planning/STATE.md §"Blockers/Concerns" (SQLite migration deployment gap requirement)
  </read_first>
  <action>
    Three surgical changes to ingest_wechat.py. Do NOT refactor anything else.

    (A) Expand the existing `from config import ...` line at line 36 to also
    import `ENRICHMENT_MIN_LENGTH` and `INGEST_LLM_MODEL`:

    Current line 36:
        from config import RAG_WORKING_DIR, BASE_IMAGE_DIR, load_env, CDP_URL, ENTITY_BUFFER_DIR

    Change to (same line, appended imports):
        from config import RAG_WORKING_DIR, BASE_IMAGE_DIR, load_env, CDP_URL, ENTITY_BUFFER_DIR, ENRICHMENT_MIN_LENGTH, INGEST_LLM_MODEL

    (B) Replace all 3 hardcoded "gemini-2.5-flash-lite" strings with
    INGEST_LLM_MODEL (D-12-REVISED). Locations:
      - Line 100: `model_name="gemini-2.5-flash-lite"` → `model_name=INGEST_LLM_MODEL`
      - Line 121: `llm_model_name="gemini-2.5-flash-lite"` → `llm_model_name=INGEST_LLM_MODEL`
      - Line 505: `model='gemini-2.5-flash-lite'` → `model=INGEST_LLM_MODEL`

    After the edits: `grep -c "gemini-2.5-flash-lite" ingest_wechat.py` should
    return 0 (no remaining references).

    (C) Auto-run SQLite migration at module import time. Immediately after the
    `DB_PATH = Path(__file__).parent / "data" / "kol_scan.db"` line (currently
    line 49), add a guarded `init_db()` call that ensures the Phase 4
    `articles.enriched` and `ingestions.enrichment_id` columns exist even on
    fresh deploys. (Closes Wave 3 deployment gap; see STATE.md Blockers.)

    Exact insertion AFTER the DB_PATH line:

        # Phase 4: ensure SQLite has the enriched + enrichment_id columns on
        # every deploy. init_db() is idempotent (uses _ensure_column ALTER TABLE
        # guards). Guarded by DB_PATH existence so fresh installs (no DB at all)
        # don't fail here — those get init_db() called later via batch_scan_kol.
        if DB_PATH.exists():
            try:
                from batch_scan_kol import init_db as _kol_init_db
                _kol_init_db(DB_PATH)
            except Exception as _e:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Phase 4 SQLite auto-migrate skipped: %s", _e
                )

    (D) Find the SQLite UPDATE block around lines 681-690 (the `if DB_PATH.exists()`
    guard where `content_hash` and related fields are written). ADD a parallel
    UPDATE for `enriched = -1` when `len(full_content) < ENRICHMENT_MIN_LENGTH`.

    Insertion point: immediately AFTER the existing content_hash UPDATE and
    BEFORE `conn.commit()`. Exact insertion:

            # D-07: mark short articles as enriched=-1 so the enrich_article skill
            # (or batch re-enrichment job) knows to skip them permanently.
            if len(full_content) < ENRICHMENT_MIN_LENGTH:
                conn.execute(
                    "UPDATE articles SET enriched = ? WHERE url = ?",
                    (-1, url),
                )

    Preserve the surrounding try/except, the conn.close(), other UPDATEs, etc.
    Touch only the lines needed.

    (E) Do NOT add a `--enrich`, `--no-enrich`, or ENRICHMENT_ENABLED conditional
    path. Enrichment is owned by the enrich_article skill, not this file.
  </action>
  <verify>
    <automated>grep -q "ENRICHMENT_MIN_LENGTH" ingest_wechat.py && grep -q "INGEST_LLM_MODEL" ingest_wechat.py && grep -q "UPDATE articles SET enriched" ingest_wechat.py && ! grep -q "gemini-2.5-flash-lite" ingest_wechat.py && grep -q "_kol_init_db\|from batch_scan_kol import init_db" ingest_wechat.py && python -c "import ast; ast.parse(open('ingest_wechat.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "ENRICHMENT_MIN_LENGTH" ingest_wechat.py` succeeds
    - `grep -q "INGEST_LLM_MODEL" ingest_wechat.py` succeeds (at least 3 usages + 1 import = 4 total)
    - `grep -c "INGEST_LLM_MODEL" ingest_wechat.py` returns >= 4
    - `grep -c "gemini-2.5-flash-lite" ingest_wechat.py` returns 0 (D-12-REVISED enforced)
    - `grep -q "UPDATE articles SET enriched" ingest_wechat.py` succeeds
    - `grep -q "len(full_content) < ENRICHMENT_MIN_LENGTH" ingest_wechat.py` succeeds
    - `grep -q "from batch_scan_kol import init_db" ingest_wechat.py` succeeds (SQLite auto-migrate)
    - `grep -q "\-\-enrich" ingest_wechat.py` returns NO matches
    - `python -c "import ast; ast.parse(open('ingest_wechat.py').read())"` exits 0
    - The cache-hit branch (lines ~532-566), UA scrape, Apify fallback, CDP fallback, and image_pipeline calls from plan 01 are ALL still present (no unrelated changes)
  </acceptance_criteria>
  <done>ingest_wechat.py: uses INGEST_LLM_MODEL (flash), auto-migrates SQLite on import, marks short articles enriched=-1, no --enrich flag</done>
</task>

<task type="auto">
  <name>Task 7.2b: Pop GOOGLE_GENAI_USE_VERTEXAI in enrichment/fetch_zhihu.py and enrichment/merge_and_ingest.py</name>
  <files>enrichment/fetch_zhihu.py, enrichment/merge_and_ingest.py</files>
  <read_first>
    - enrichment/extract_questions.py lines 53-61 (the existing pop pattern the user committed 7fb89de — this is the reference)
    - enrichment/fetch_zhihu.py (find any `genai.Client(...)` construction site)
    - enrichment/merge_and_ingest.py (find any `genai.Client(...)` construction site AND the LightRAG init — LightRAG's own genai client is created in ingest_wechat.py, not here)
    - docs/testing/04-06-test-results.md §"BLOCKER 1" (VERTEXAI env var global leak)
  </read_first>
  <action>
    Match extract_questions.py's pattern: pop GOOGLE_GENAI_USE_VERTEXAI
    immediately before any genai.Client construction. These two modules are
    entry points (invoked via `python -m enrichment.fetch_zhihu` and
    `python -m enrichment.merge_and_ingest`) and do NOT import config.py, so
    they must pop the env var themselves.

    (A) enrichment/fetch_zhihu.py — if the file contains any `genai.Client(` or
    any `from google import genai`/`import google.genai` usage that ultimately
    builds a client, add the pop before that. If the file uses image_pipeline's
    describe_images (which has its own genai.Client at image_pipeline.py:75),
    add the pop immediately AFTER the `import os` statement near the top of the
    file, module-level:

        # Hermes env has GOOGLE_GENAI_USE_VERTEXAI=true globally which forces
        # genai.Client to Vertex AI (rejects API keys). Unset at import time so
        # any downstream genai.Client (including image_pipeline.describe_images)
        # routes to the Gemini API. See test report 04-06.
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

    Place this AFTER all other imports at module top, before any function
    definition. Match extract_questions.py's wording style.

    (B) enrichment/merge_and_ingest.py — same pattern. Place the pop at module
    top, AFTER imports, BEFORE any function. This covers the case where
    merge_and_ingest triggers LightRAG's async entity extraction (which calls
    genai via ingest_wechat.gemini_model_complete — but that path already
    benefits from config.py's pop since ingest_wechat imports config). The pop
    here is defensive redundancy: it guarantees that even if somebody invokes
    merge_and_ingest from an environment where config.py wasn't imported first,
    the env var is unset.

    Do not modify any other lines. Do not rename imports.
  </action>
  <verify>
    <automated>grep -q 'os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI"' enrichment/fetch_zhihu.py && grep -q 'os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI"' enrichment/merge_and_ingest.py && python -c "import ast; ast.parse(open('enrichment/fetch_zhihu.py').read()); ast.parse(open('enrichment/merge_and_ingest.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'GOOGLE_GENAI_USE_VERTEXAI' enrichment/fetch_zhihu.py` succeeds
    - `grep -q 'GOOGLE_GENAI_USE_VERTEXAI' enrichment/merge_and_ingest.py` succeeds
    - `grep -q 'GOOGLE_GENAI_USE_VERTEXAI' enrichment/extract_questions.py` still succeeds (we did NOT remove the existing one)
    - Both files parse as valid Python
    - Pop is at module top (before any function/class definition) in both new files
  </acceptance_criteria>
  <done>Both enrichment entry-point modules pop VERTEXAI defensively at import, matching extract_questions.py</done>
</task>

<task type="auto">
  <name>Task 7.3: Strip any --enrich flag doc from omnigraph_ingest/SKILL.md</name>
  <files>skills/omnigraph_ingest/SKILL.md</files>
  <read_first>
    - skills/omnigraph_ingest/SKILL.md (full file — verify current state has no --enrich flag already)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-07 (no flag, enrichment is skill-layer concern)
  </read_first>
  <action>
    First read the entire skills/omnigraph_ingest/SKILL.md to check current state.
    Per the context provided, the current SKILL.md does NOT contain any `--enrich`
    flag documentation. Since D-07 supersedes PRD §12's flag proposal, the skill
    body simply needs to acknowledge this via a single "Related Skills" update.

    Perform these edits:

    (A) In the "Related Skills" section at the bottom (around lines 124-129), ADD
    ONE line as the first bullet. The section currently reads:

    ```
    ## Related Skills

    - To query ingested content: `omnigraph_query`
    ...
    ```

    Change it to:

    ```
    ## Related Skills

    - For Zhihu-enriched ingest (production default per Phase 4): `enrich_article` — orchestrates question extraction, 好问, and cross-referenced Zhihu ingest.
    - To query ingested content: `omnigraph_query`
    ...
    ```

    (B) In the skill's top-level description (the frontmatter `description:`
    field), consider adding ONE sentence clarifying that this skill is the
    un-enriched ingest path. Minimal change — do not rewrite the description.
    Add this sentence at the END of the first paragraph of `description:`:

    Locate: `"...or any time a WeChat URL (mp.weixin.qq.com) or a .pdf file path is provided with intent to index it."`

    Append, joined by a space:

    `" For the Phase 4 Zhihu-enriched production ingest path, the orchestrator calls this skill's underlying scraper but routes first through the enrich_article skill; use enrich_article when enrichment is desired."`

    (C) If the file contains ANY mention of `--enrich`, `--no-enrich`, or
    `ENRICHMENT_ENABLED` flag toggling: remove those lines. (From the Read above,
    this should be none — verify via grep after edit.)

    Preserve everything else exactly as-is: the Decision Tree cases, Error
    Handling table, Output Format, Privacy Note. Surgical changes only.
  </action>
  <verify>
    <automated>! grep -q "\-\-enrich" skills/omnigraph_ingest/SKILL.md && grep -q "enrich_article" skills/omnigraph_ingest/SKILL.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "\-\-enrich" skills/omnigraph_ingest/SKILL.md` returns NO matches
    - `grep -q "\-\-no-enrich" skills/omnigraph_ingest/SKILL.md` returns NO matches
    - `grep -q "enrich_article" skills/omnigraph_ingest/SKILL.md` succeeds (related skill referenced)
    - The existing Decision Tree cases (Case 1: WeChat URL, Case 2: PDF, Case 3: no URL, Case 4: GEMINI_API_KEY missing, Case 5: non-WeChat URL) are all still present: `grep -c "### Case" skills/omnigraph_ingest/SKILL.md` returns >= 5
    - The existing Error Handling table is still present: `grep -q "| Error | Response |" skills/omnigraph_ingest/SKILL.md` succeeds
  </acceptance_criteria>
  <done>omnigraph_ingest/SKILL.md has no --enrich flag docs; cross-references enrich_article</done>
</task>

<task type="auto">
  <name>Task 7.4: Remote live-validate merge_and_ingest against Wave 4 fixtures — flip criteria 7-12 to PASS</name>
  <files>(no file changes — remote validation only)</files>
  <read_first>
    - docs/testing/04-06-test-results.md §4 "Acceptance Criteria" (rows 7-12 are blocked; this task flips them to PASS)
    - skills/enrich_article/README.md
    - enrichment/merge_and_ingest.py (CLI contract)
    - .planning/STATE.md §"Waiting / Blocked On" (this task closes the blocker)
  </read_first>
  <action>
    This is automated (not a human-verify checkpoint) because SSH can drive the
    full flow: the Wave 4 test already captured all the upstream artifacts
    (questions.json, 0/haowen.json, 0/final_content.md, 1/*, 2/*) on remote at
    ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/. The only step that got
    blocked was merge_and_ingest itself due to flash-lite quota. With the flash
    model swap (Task 7.2) plus SQLite auto-migrate, rerunning merge_and_ingest
    against the existing fixtures will flip criteria 7-12 to PASS.

    Orchestrator (not executor) runs this via SSH after Wave 5 ships.

    Steps:

    1. SSH to remote; `cd ~/OmniGraph-Vault && git fetch origin && git checkout gsd/phase-04 && git pull --ff-only`
    2. Verify flash model swap landed: `grep -c "gemini-2.5-flash-lite" ingest_wechat.py` returns 0; `grep -q "INGEST_LLM_MODEL" ingest_wechat.py` succeeds.
    3. Verify SQLite auto-migrate on import: `source venv/bin/activate && python -c "import ingest_wechat; print('migration ran')"` exits 0.
    4. Verify fixtures still present: `ls ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/questions.json ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/{0,1,2}/haowen.json ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/{0,1,2}/final_content.md`
    5. Pre-run LightRAG graph baseline: `grep -c '<node' ~/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml` (record N).
    6. Rerun merge_and_ingest:
       `cd ~/OmniGraph-Vault && source venv/bin/activate && set -a && source ~/.hermes/.env && set +a && python -m enrichment.merge_and_ingest 8ac04218b4 --article-path ~/.hermes/omonigraph-vault/images/8ac04218b4/final_content.md --article-url "https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA" 2>&1 | tee /tmp/mi_rerun.log`
    7. Capture last line of stdout — must be D-03 single-line JSON: `{"hash": "8ac04218b4", "status": "ok", "enriched": 2, "question_count": 3, "success_count": 3, "zhihu_docs_ingested": N'', "enrichment_id": "enrich_8ac04218b4"}` where N'' >= 1.
    8. Verify filesystem: `ls ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/final_content.enriched.md` exists AND is non-empty AND contains inline 好问 summaries (grep for "好问" or the first question text).
    9. Verify SQLite:
       - `sqlite3 ~/OmniGraph-Vault/data/kol_scan.db "SELECT enriched FROM articles WHERE url='https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA'"` returns 2
       - `sqlite3 ~/OmniGraph-Vault/data/kol_scan.db "SELECT enrichment_id FROM ingestions WHERE article_id=(SELECT id FROM articles WHERE url='https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA')"` returns `enrich_8ac04218b4`
    10. Verify LightRAG: `python -c "import json; d=json.load(open('/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json')); new=[(k,v['status']) for k,v in d.items() if '8ac04218b4' in k]; print(new)"` — all status values must be `processed`, none `failed`.
    11. Verify graph grew: post-run `grep -c '<node'` > baseline N from step 5.
    12. Record all outputs in a commit-ready validation note (orchestrator adds this to 04-07-SUMMARY.md).

    If any step fails: capture logs + error to docs/testing/04-07-validation-results.md on gsd/phase-04; plan follow-up gap-closure.
  </action>
  <verify>
    <automated>true</automated>
  </verify>
  <acceptance_criteria>
    - D-03 JSON emitted with `"status": "ok"` AND `"success_count" >= 1` AND `"zhihu_docs_ingested" >= 1`
    - `~/.hermes/omonigraph-vault/enrichment/8ac04218b4/final_content.enriched.md` exists, non-empty, contains 好问 summaries inline (closes criterion 7)
    - SQLite `articles.enriched == 2` for the test URL (closes criterion 9)
    - SQLite `ingestions.enrichment_id == "enrich_8ac04218b4"` (closes criterion 10)
    - LightRAG `kv_store_doc_status.json` shows all `8ac04218b4`-tagged docs with status `processed`, none `failed` (closes criterion 12)
    - LightRAG graph grew (node count post > baseline) (closes criterion 11)
    - merge_and_ingest exit code 0 (closes criterion 14 already-PASS reinforcement)
    - All 6 blocked criteria (7, 8, 9, 10, 11, 12) from 04-06-test-results.md §4 flip to PASS
    - If ALL 6 flip: Phase 4 exit gate passed. Orchestrator proceeds to phase verification + merge.
  </acceptance_criteria>
  <done>Wave 4 test report §4 criteria 7-12 flipped to PASS; Phase 4 end-to-end pipeline proven on real remote data</done>
</task>

</tasks>

<verification>
  - `python -c "import config; print(config.ENRICHMENT_LLM_MODEL)"` prints `gemini-2.5-flash`
  - `python -c "import config; print(config.INGEST_LLM_MODEL)"` prints `gemini-2.5-flash`
  - `! grep -q "flash-lite" config.py` (D-12-REVISED)
  - `! grep -q "gemini-2.5-flash-lite" ingest_wechat.py` (D-12-REVISED)
  - `grep -q "from batch_scan_kol import init_db" ingest_wechat.py` (SQLite auto-migrate)
  - `grep -q "UPDATE articles SET enriched" ingest_wechat.py` (D-07 short-article marker)
  - `grep -q "deepseek" config.py` returns no matches
  - `grep -q "\-\-enrich" skills/omnigraph_ingest/SKILL.md` returns no matches
  - `grep -q "GOOGLE_GENAI_USE_VERTEXAI" enrichment/fetch_zhihu.py` (VERTEXAI guard)
  - `grep -q "GOOGLE_GENAI_USE_VERTEXAI" enrichment/merge_and_ingest.py` (VERTEXAI guard)
  - Remote live-validation succeeds per Task 7.4 acceptance criteria (all 6 blocked criteria flip to PASS)
</verification>

<success_criteria>
- All 11 Phase 4 config keys present in config.py (10 original + new INGEST_LLM_MODEL); default model = flash
- ingest_wechat.py: uses INGEST_LLM_MODEL (no hardcoded flash-lite), auto-migrates SQLite on import, marks short articles enriched=-1, no --enrich flag
- enrichment/fetch_zhihu.py and enrichment/merge_and_ingest.py pop GOOGLE_GENAI_USE_VERTEXAI at import (defensive; matches extract_questions.py)
- omnigraph_ingest SKILL.md cross-references enrich_article; no --enrich flag docs
- Remote live-validation: rerunning merge_and_ingest against Wave 4 fixtures flips test report §4 criteria 7-12 from BLOCKED to PASS
- Phase 4 complete end-to-end on real article 8ac04218b4: 1 enriched WeChat doc + 3 Zhihu docs in LightRAG, articles.enriched=2, ingestions.enrichment_id=enrich_8ac04218b4
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-07-SUMMARY.md`.
</output>
