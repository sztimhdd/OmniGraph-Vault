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
autonomous: false
requirements: [D-07]
must_haves:
  truths:
    - "config.py has all 8 Phase 4 ENRICHMENT_* + ZHIHAO_SKILL_NAME + IMAGE_SERVER_BASE_URL keys per RESEARCH.md §9"
    - "config.py ENRICHMENT_LLM_MODEL is 'gemini-2.5-flash-lite' (not deepseek; D-12 supersession)"
    - "ingest_wechat.py writes articles.enriched = -1 for articles < ENRICHMENT_MIN_LENGTH chars"
    - "ingest_wechat.py does NOT add a --enrich flag (D-07 supersession)"
    - "ingest_wechat.py ingests un-enriched articles itself; enrichment happens via the enrich_article skill layer (not embedded in Python)"
    - "skills/omnigraph_ingest/SKILL.md no longer documents an --enrich flag"
    - "Remote E2E: invoking /enrich_article on one real WeChat article produces 1 enriched WeChat doc + up to 3 Zhihu docs in LightRAG"
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
  <name>Task 7.1: Add Phase 4 config keys to config.py</name>
  <files>config.py</files>
  <read_first>
    - config.py (entire file — to see the insertion point)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §9 (exact keys + values — copy verbatim)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-12 (Gemini not DeepSeek)
  </read_first>
  <action>
    Append the Phase 4 enrichment config block to `config.py`, AFTER the existing
    line `os.environ.pop("GOOGLE_CLOUD_LOCATION", None)` (currently line 36).

    Exact content to append (after a blank line):

    ```python

    # === Phase 4: Knowledge Enrichment ===
    # Master switch. Per D-07 this is always True in production; the key exists
    # so that individual invocations (e.g., direct `python ingest_wechat.py` for
    # debugging) can set ENRICHMENT_ENABLED=0 via env to bypass.
    ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

    # Article character threshold below which extraction is skipped (enriched=-1).
    ENRICHMENT_MIN_LENGTH = 2000

    # Maximum questions per article.
    ENRICHMENT_MAX_QUESTIONS = 3

    # LLM for extract_questions (D-12 supersedes the PRD DeepSeek choice).
    ENRICHMENT_LLM_MODEL = "gemini-2.5-flash-lite"

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
    <automated>python -c "import config; assert config.ENRICHMENT_LLM_MODEL == 'gemini-2.5-flash-lite'; assert config.ENRICHMENT_MIN_LENGTH == 2000; assert config.ENRICHMENT_MAX_QUESTIONS == 3; assert config.ENRICHMENT_BASE_DIR.name == 'enrichment'; assert config.ZHIHAO_SKILL_NAME == 'zhihu-haowen-enrich'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "ENRICHMENT_ENABLED = " config.py` succeeds
    - `grep -q "ENRICHMENT_MIN_LENGTH = 2000" config.py` succeeds
    - `grep -q "ENRICHMENT_MAX_QUESTIONS = 3" config.py` succeeds
    - `grep -q "ENRICHMENT_LLM_MODEL = \"gemini-2.5-flash-lite\"" config.py` succeeds
    - `grep -q "ENRICHMENT_GROUNDING_ENABLED = True" config.py` succeeds
    - `grep -q "ENRICHMENT_HAOWEN_TIMEOUT = 120" config.py` succeeds
    - `grep -q "ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60" config.py` succeeds
    - `grep -q "ENRICHMENT_BASE_DIR = BASE_DIR / \"enrichment\"" config.py` succeeds
    - `grep -q "ZHIHAO_SKILL_NAME = \"zhihu-haowen-enrich\"" config.py` succeeds
    - `grep -q "IMAGE_SERVER_BASE_URL = \"http://localhost:8765\"" config.py` succeeds
    - `grep -q "deepseek" config.py` returns NO matches (D-12 supersession enforced)
    - `python -c "import config"` exits 0 (file parses as valid Python)
    - The 8 ENRICHMENT_* + 2 other new keys are all importable: `python -c "from config import ENRICHMENT_ENABLED, ENRICHMENT_MIN_LENGTH, ENRICHMENT_MAX_QUESTIONS, ENRICHMENT_LLM_MODEL, ENRICHMENT_GROUNDING_ENABLED, ENRICHMENT_HAOWEN_TIMEOUT, ENRICHMENT_ZHIHU_FETCH_TIMEOUT, ENRICHMENT_BASE_DIR, ZHIHAO_SKILL_NAME, IMAGE_SERVER_BASE_URL; print('ok')"` exits 0
  </acceptance_criteria>
  <done>config.py has all 10 new keys with exact values from RESEARCH.md §9</done>
</task>

<task type="auto">
  <name>Task 7.2: Mark short articles as enriched=-1 in ingest_wechat.py</name>
  <files>ingest_wechat.py</files>
  <read_first>
    - ingest_wechat.py entire file (the SQLite UPDATE pattern around line 713-725)
    - config.py (to see the ENRICHMENT_MIN_LENGTH constant just added)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-07 (enriched=-1 semantics)
  </read_first>
  <action>
    Modify `ingest_wechat.py` to write `articles.enriched = -1` when the scraped
    article is shorter than `ENRICHMENT_MIN_LENGTH` characters. Minimal surgical
    change — do NOT refactor anything else.

    (A) Add import near the top of the file (next to other config imports — grep
    for existing `from config import` to find the right place; if no such import
    exists, use `from config import BASE_DIR, RAG_WORKING_DIR, ...`, and ADD
    `ENRICHMENT_MIN_LENGTH` to that import list):

    ```python
    from config import ENRICHMENT_MIN_LENGTH
    ```

    If `config` module-level values are accessed via a different pattern (e.g.
    `import config` then `config.BASE_DIR`), match that pattern instead. Grep
    first to determine which.

    (B) Find the SQLite UPDATE block around lines 713-725 (where `content_hash`
    is written). ADD a parallel UPDATE for `enriched` when `len(full_content) <
    ENRICHMENT_MIN_LENGTH`. The exact insertion point: immediately AFTER the
    existing `conn.execute("UPDATE articles SET content_hash = ? WHERE url = ?", ...)`
    line and BEFORE `conn.commit()`.

    Exact insertion:

    ```python
            # D-07: mark short articles as enriched=-1 so the enrich_article skill
            # (or batch re-enrichment job) knows to skip them permanently.
            if len(full_content) < ENRICHMENT_MIN_LENGTH:
                conn.execute(
                    "UPDATE articles SET enriched = ? WHERE url = ?",
                    (-1, url),
                )
    ```

    Preserve EVERYTHING else about the UPDATE block — the `try/except`, the
    `conn.close()`, other UPDATEs, etc. Touch only the lines needed.

    (C) Do NOT add a `--enrich` flag, `--no-enrich` flag, or any conditional path
    based on an ENRICHMENT_ENABLED env var in this task. Enrichment is owned by
    the `enrich_article` skill, not by ingest_wechat.py. This file's
    responsibility for Phase 4 is limited to: (1) run image_pipeline (already
    done in plan 01), (2) write enriched=-1 for short articles (this task), (3)
    write content_hash (already present).
  </action>
  <verify>
    <automated>grep -q "ENRICHMENT_MIN_LENGTH" ingest_wechat.py && grep -q "UPDATE articles SET enriched" ingest_wechat.py && python -c "import ast; ast.parse(open('ingest_wechat.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from config import.*ENRICHMENT_MIN_LENGTH\|import config" ingest_wechat.py` succeeds AND `grep -q "ENRICHMENT_MIN_LENGTH" ingest_wechat.py` succeeds
    - `grep -q "UPDATE articles SET enriched" ingest_wechat.py` succeeds
    - `grep -q "(-1, url)\|-1, url" ingest_wechat.py` succeeds (the -1 value is passed)
    - `grep -q "len(full_content) < ENRICHMENT_MIN_LENGTH" ingest_wechat.py` succeeds
    - `grep -q "\-\-enrich" ingest_wechat.py` returns NO matches (D-07 no flag)
    - `python -c "import ast; ast.parse(open('ingest_wechat.py').read())"` exits 0
    - The cache-hit branch (lines ~532-566), UA scrape, Apify fallback, CDP fallback, and image_pipeline calls from plan 01 are ALL still present (no unrelated changes)
  </acceptance_criteria>
  <done>ingest_wechat.py marks short articles as enriched=-1; no --enrich flag introduced</done>
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

<task type="checkpoint:human-verify">
  <name>Task 7.4: Remote E2E — one real WeChat article through enrich_article</name>
  <files>(no file changes — verification only)</files>
  <read_first>
    - skills/enrich_article/README.md (E2E test instructions)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-VALIDATION.md (E2E tier — full skill run against one real article)
    - All of: skills/enrich_article/SKILL.md, skills/zhihu-haowen-enrich/SKILL.md, enrichment/*.py (to mentally trace the expected data flow)
  </read_first>
  <action>
    Execute the end-to-end Phase 4 validation against the live remote Hermes
    instance. This is the phase's exit gate.

    Steps (user performs on Windows host):

    1. Push all Phase 4 code: `./deploy.sh`
    2. Ensure the Phase-0 spike report exists on remote with `status: success`:
       ```
       ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST \
         'grep "^status:" OmniGraph-Vault/.planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md'
       ```
    3. On remote, run full unit + integration test suite:
       ```
       ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST \
         'cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/ -v --tb=short'
       ```
       All tests must pass (or skip cleanly for missing-fixture cases).
    4. Pick ONE real production WeChat article URL (≥2000 chars; ideally one
       that's already been scraped and cached — fast path). Let `HASH` = the
       md5[:10] of its URL.
    5. Ensure the article is scraped (cache exists at
       `~/.hermes/omonigraph-vault/images/$HASH/final_content.md`) OR run
       `python ingest_wechat.py "<url>"` first to scrape.
    6. From Hermes chat/CLI on remote:
       ```
       /enrich_article
       ARTICLE_URL=<the url>
       ARTICLE_PATH=/home/<user>/.hermes/omonigraph-vault/images/<hash>/final_content.md
       ```
    7. Wait up to 15 minutes. Observe the agent executing:
       - Step 1 (extract_questions) → one-line JSON with `status:ok, question_count:N`
       - Step 2 (for-each question) → /zhihu-haowen-enrich invocations + fetch_zhihu calls
       - Step 4 (merge_and_ingest) → one-line JSON with `status:ok, enriched:2`
    8. Verify artifacts:
       ```
       # On remote:
       ls ~/.hermes/omonigraph-vault/enrichment/<hash>/questions.json
       ls ~/.hermes/omonigraph-vault/enrichment/<hash>/*/haowen.json
       ls ~/.hermes/omonigraph-vault/enrichment/<hash>/*/final_content.md   # zhihu MDs
       ```
    9. Verify SQLite:
       ```
       sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
         "SELECT enriched FROM articles WHERE url = '<the url>'"
       # Expect: 2 (success/partial) or -2 (all-fail)

       sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
         "SELECT enrichment_id FROM ingestions WHERE article_id=(SELECT id FROM articles WHERE url='<the url>')"
       # Expect: enrich_<hash>
       ```
    10. Verify LightRAG:
        ```
        ssh remote 'cd ~/OmniGraph-Vault && source venv/bin/activate && \
          python -c "
        import asyncio
        from ingest_wechat import get_rag
        async def main():
            rag = await get_rag()
            # Inspect doc store for zhihu_<hash>_* ids
            # (LightRAG API detail — use repl to check)
        asyncio.run(main())
        "'
        ```
        (Exact API call may vary — user confirms visually via inspection.)

    Resume-signal: type "phase 4 E2E passed" with a one-line summary:
    - Question count extracted
    - Successful/failed 好问 per question
    - Final `enriched` state
    - LightRAG zhihu_<hash>_* doc count

    If ANY step fails, capture the error + logs and plan a follow-up gap-closure
    phase (`/gsd:plan-phase 4 --gaps`).
  </action>
  <verify>
    <automated>true</automated>
  </verify>
  <acceptance_criteria>
    - Remote Phase-0 spike report shows `status: success`
    - Remote pytest suite green (unit + integration, skips ok)
    - Remote E2E invocation produces:
      - `~/.hermes/omonigraph-vault/enrichment/<hash>/questions.json` exists with at least 1 question
      - At least one `~/.hermes/omonigraph-vault/enrichment/<hash>/*/haowen.json` exists (success or graceful error)
      - SQLite `articles.enriched` for the test URL is in {2, -2} (NOT 0, NOT null)
      - SQLite `ingestions.enrichment_id` starts with `enrich_`
    - User reports (in resume signal) how many questions succeeded and the final enriched state
  </acceptance_criteria>
  <done>End-to-end pipeline works on one real article on remote; all artifacts present; SQLite state correct</done>
</task>

</tasks>

<verification>
  - `python -c "import config; print(config.ENRICHMENT_LLM_MODEL)"` prints `gemini-2.5-flash-lite`
  - `grep -q "deepseek" config.py` returns no matches
  - `grep -q "\-\-enrich" skills/omnigraph_ingest/SKILL.md` returns no matches
  - `grep -q "UPDATE articles SET enriched" ingest_wechat.py` succeeds
  - Remote E2E succeeds per Task 7.4 acceptance criteria
</verification>

<success_criteria>
- All 10 Phase 4 config keys present in config.py with exact values from RESEARCH.md §9
- ingest_wechat.py marks short articles as enriched=-1 (no flag added)
- omnigraph_ingest SKILL.md cross-references enrich_article; no --enrich flag docs
- Remote E2E: one real article produces enriched LightRAG state and correct SQLite values
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-07-SUMMARY.md`.
</output>
