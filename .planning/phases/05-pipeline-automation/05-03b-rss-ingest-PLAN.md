---
phase: 05-pipeline-automation
plan: 03b
type: execute
wave: 1
depends_on: [05-03]
files_modified:
  - enrichment/rss_ingest.py
  - enrichment/run_enrich_for_id.py
  - tests/unit/test_rss_ingest.py
  - tests/unit/test_run_enrich_for_id.py
autonomous: true
requirements: [D-07, D-08, D-09, D-15, D-16, D-19]
must_haves:
  truths:
    - "English RSS articles are translated to Chinese BEFORE LightRAG ingest (D-09)"
    - "Per D-07 REVISED 2026-05-02 + D-19: RSS articles do NOT invoke enrich_article. Direct path: translate (D-09) → LightRAG ainsert — no Zhihu 好问 layer."
    - "`rss_articles.enriched` is set to 2 ONLY after both ainsert succeeds AND `aget_docs_by_ids` confirms status=='PROCESSED' (Task 4.2 anti-ghost gate). On ainsert exception OR non-PROCESSED status, `enriched` is left UNCHANGED at its prior value (0) so the next batch retries. `rss_ingest.py` does NOT write `-2`. NO enrichment success/failure branching."
    - "`final_content.md` is written atomically (.tmp then rename) to ~/.hermes/omonigraph-vault/rss_content/<hash>/"
    - "Original English source is preserved as original.md for debug"
    - "A shared bridge script `run_enrich_for_id.py` still ships (for Task 05-04 step_6 KOL-only enrichment); `--source rss` branch exists but is a guarded no-op that logs 'RSS excluded per D-07 REVISED' and exits 0 without invoking enrich_article"
    - "`--dry-run` prints planned actions per row with no API calls"
    - "Post-ainsert verification hook (Task 4.2 pattern): after `rag.ainsert(...)`, call `rag.aget_docs_by_ids([doc_id])` and require status=='PROCESSED' before setting `rss_articles.enriched=2` — prevents RSS ghosts just like WeChat (see ingest_wechat.py lines 1086-1120)"
  artifacts:
    - path: "enrichment/run_enrich_for_id.py"
      provides: "Bridge that resolves ARTICLE_PATH/URL/HASH from DB + source type, then invokes enrich_article skill via env vars. --source kol: normal path. --source rss: guarded no-op per D-07 REVISED 2026-05-02 + D-19."
      min_lines: 80
      contains: "ARTICLE_PATH"
    - path: "enrichment/rss_ingest.py"
      provides: "EN-to-CN translation + LightRAG ainsert (with Task 4.2 verification hook) for depth>=2 RSS articles. NO enrich_article invocation per D-07 REVISED."
      min_lines: 140
      contains: "rss_articles SET enriched"
    - path: "tests/unit/test_rss_ingest.py"
      provides: "Unit tests for DeepSeek translation branch, direct-ainsert branch, aget_docs_by_ids PROCESSED verification gate, enriched=2 state update on happy path, enriched left unchanged on non-PROCESSED, atomic write, absence of subprocess calls"
      min_lines: 60
    - path: "tests/unit/test_run_enrich_for_id.py"
      provides: "Unit tests for env-var setup (kol path) + guarded-noop behavior for --source rss"
      min_lines: 40
  key_links:
    - from: "enrichment/rss_ingest.py"
      to: "rss_articles JOIN rss_classifications WHERE depth_score>=2 AND enriched=0"
      via: "sqlite3 SELECT"
      pattern: "rss_classifications"
    - from: "enrichment/rss_ingest.py"
      to: "DeepSeek chat completions API (EN→CN translation) via raw HTTP"
      via: "requests.post to api.deepseek.com/v1/chat/completions for english-only articles (Phase 7 D-09 supersession: LLM → DeepSeek)"
      pattern: "api.deepseek.com"
    - from: "enrichment/rss_ingest.py"
      to: "lightrag.ainsert for Chinese final_content.md"
      via: "LightRAG import pattern matching merge_and_ingest.py; reuse Task 4.2 aget_docs_by_ids verification hook from ingest_wechat.py"
      pattern: "aget_docs_by_ids"
    - from: "enrichment/run_enrich_for_id.py --source kol"
      to: "enrich_article Hermes skill"
      via: "os.environ injection + subprocess hermes skill run"
      pattern: "hermes.*skill.*run.*enrich_article"
---

<objective>
Close the RSS ingest gap: translate English RSS articles to Chinese (D-09) and ingest directly into LightRAG (no Zhihu enrichment layer per D-07 REVISED 2026-05-02 + D-19). Ship `run_enrich_for_id.py` as the KOL-only enrichment bridge (invoked by 05-04 step_6 / daily-enrich cron); its `--source rss` branch exists as a guarded no-op for backwards-compat but actively refuses to invoke enrich_article.

Purpose: RSS reaches LightRAG via the shortest safe path — translate → verify → ainsert. Zhihu 好问 enrichment is a Chinese-corpus operation; layering it over English-origin RSS produces language-mismatched edges that degrade retrieval (see 05-CONTEXT.md D-07 REVISED 2026-05-02 rationale).

Output: `enrichment/rss_ingest.py` produces LightRAG entries for depth>=2 RSS articles with post-ainsert verification gate; `enrichment/run_enrich_for_id.py` is the canonical KOL-only enrichment bridge.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md
@.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md
@skills/enrich_article/SKILL.md
@enrichment/merge_and_ingest.py
@enrichment/rss_schema.py
@config.py
@ingest_wechat.py
@lib/checkpoint.py
@lib/vision_cascade.py
@CLAUDE.md

<infra_composition>
**v3.1/v3.2 infrastructure composition (added 2026-05-01):** See `05-CONTEXT.md` § infra_composition. Key points for this plan:

- **Checkpoint guards are mandatory**: `rss_ingest.py`'s per-article loop MUST wrap each article's processing in the same 6-stage checkpoint pattern v3.2 Phase 12-02 applied to `ingest_wechat.py`. Stages relevant here: `scrape` (RSS fetch already done in 05-02 — treat as pre-completed), `classify` (05-03 already done), `image_download` (if the RSS body has images), `vision` (via `lib/vision_cascade.py` — automatic through `image_pipeline.describe_images()`), `text_ingest` (LightRAG `ainsert`), `sub_doc_ingest` (image sub-doc append if images). Use `lib.checkpoint.has_stage(ckpt_hash, stage)` + `mark_stage(ckpt_hash, stage)`. `ckpt_hash = lib.checkpoint.get_article_hash(url)` (sha256[:16]).
- **No new Vision code**: Images in RSS articles go through `image_pipeline.describe_images()` — which v3.2 Phase 13-02 wired to `lib.vision_cascade.VisionCascade`. Cascade (SiliconFlow → OpenRouter → Gemini) + circuit breaker inherit automatically.
- **No new timeout code**: `ainsert` inherits v3.1 Phase 9 LLM_TIMEOUT=600 + per-article timeout formula `max(120+30×chunks, 900)` via `get_rag(flush=False)`. Do NOT wrap in additional `asyncio.wait_for`.
- **Translation path unchanged**: D-09 EN→CN body translation happens as specified (D-08 `extract_questions` prompt is N/A for RSS since enrichment is excluded). Cascade/checkpoint are post-translation concerns.
- **Post-ainsert verification hook (Task 4.2 pattern, MANDATORY for RSS per D-19)**: After `rag.ainsert(content, ids=[doc_id])` returns, call `statuses = await rag.aget_docs_by_ids([doc_id])`. Require `statuses[doc_id]['status'] == 'PROCESSED'` before writing `rss_articles SET enriched=2`. On non-PROCESSED (absent / failed / exception): log warning, leave `rss_articles.enriched` at its prior value (0 or -2), let next batch retry. Pattern ported verbatim from `ingest_wechat.py:1086-1120` (commit 585aa3b). This is what prevents RSS from regrowing the same ghost-article drift that KOL had.
- **Enrichment path excluded (D-07 REVISED 2026-05-02 + D-19)**: `rss_ingest.py` does NOT invoke `run_enrich_for_id.py --source rss`, does NOT call `enrich_article` skill, does NOT interact with `enrichment/{extract_questions,fetch_zhihu,merge_and_ingest}.py`. Direct path: translate → image_pipeline + checkpoint → ainsert → verify → mark `enriched=2`. If operator manually runs `run_enrich_for_id.py --source rss --article-id N` as a test, the guarded branch logs "RSS excluded per D-07 REVISED" and exits 0 without side-effects.
</infra_composition>

<interfaces>
From `skills/enrich_article/SKILL.md` (confirmed by read):
```
Inputs (env vars, NOT CLI flags):
  ARTICLE_PATH  required — local path to final_content.md
  ARTICLE_URL   required — original article URL
  ARTICLE_HASH  optional — md5[:10]; derived if omitted
  ENRICHMENT_DIR optional — defaults to ~/.hermes/omonigraph-vault/enrichment
```

From `enrichment/merge_and_ingest.py` (pattern for setting articles.enriched=2):
```python
# After successful LightRAG ainsert:
conn.execute(
    "UPDATE articles SET enriched = ? WHERE url = ?",
    (2, article_url),
)
```
RSS must follow the same pattern but target `rss_articles` by id.

From Phase 4 D-11 state-machine (inherited):
```
  0  = pending
  2  = full or partial enrichment success
  -2 = all enrichment questions failed (body still ingested un-enriched)
```

From CLAUDE.md atomic-write convention:
```python
tmp = target.with_suffix(target.suffix + ".tmp")
tmp.write_text(content, encoding="utf-8")
os.replace(tmp, target)
```

From `ingest_wechat.py:704-716` (update pattern for articles table):
```python
conn.execute(
    "UPDATE articles SET enriched = 2 WHERE content_hash = ?",
    (content_hash,),
)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 3b.1: Build `enrichment/run_enrich_for_id.py` — bridge for env-var skill invocation</name>
  <files>enrichment/run_enrich_for_id.py, tests/unit/test_run_enrich_for_id.py</files>
  <behavior>
    - Test 1 (KOL normal path): `--source kol --article-id 1` resolves ARTICLE_PATH to `~/.hermes/omonigraph-vault/images/<hash>/final_content.md`, ARTICLE_URL from `articles.url`, ARTICLE_HASH from `articles.content_hash`; `subprocess.run` IS called.
    - Test 2 (RSS guarded no-op per D-07 REVISED 2026-05-02 + D-19): `--source rss --article-id 1` returns exit code 0 WITHOUT invoking `subprocess.run` (no enrich_article skill call), prints a log line containing "RSS excluded per D-07 REVISED". DB is NOT queried for the RSS article — the guard short-circuits before resolution.
    - Test 3 (KOL not found): `--source kol --article-id 999` where id does not exist in `articles` — exits non-zero with an error message; `subprocess.run` is NOT called.
    - Test 4 (KOL env-var contract): on the kol path, `subprocess.run` is called with exactly `["hermes", "skill", "run", "enrich_article"]` and the env dict contains ARTICLE_PATH, ARTICLE_URL, ARTICLE_HASH — NOT as CLI flags.
    - Test 5 (invalid source): an invalid `--source` value exits with clear error (argparse choices enforcement).
  </behavior>
  <read_first>
    - skills/enrich_article/SKILL.md (CONFIRM env-var contract, DO NOT assume CLI flags)
    - enrichment/merge_and_ingest.py (pattern for SQLite lookup + path resolution)
    - config.py (BASE_DIR typo preserved — `omonigraph-vault`)
    - enrichment/rss_schema.py (rss_articles columns)
    - CLAUDE.md (surgical changes, type hints)
  </read_first>
  <action>
    Create `enrichment/run_enrich_for_id.py`:

    ```python
    """Bridge: resolve article path + URL + hash from DB, then invoke enrich_article
    via env-var contract (ARTICLE_PATH, ARTICLE_URL, ARTICLE_HASH).

    The enrich_article Hermes skill (skills/enrich_article/SKILL.md) takes inputs
    via env vars, NOT CLI flags. Phase 5 orchestrator calls this bridge per
    article instead of hardcoding `hermes skill run enrich_article --article-id ...`
    which would silently fail.

    Usage:
        venv/bin/python enrichment/run_enrich_for_id.py --source kol --article-id 42
        venv/bin/python enrichment/run_enrich_for_id.py --source rss --article-id 17
    """
    from __future__ import annotations

    import argparse
    import hashlib
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    from config import BASE_DIR

    DB = Path("data/kol_scan.db")

    def _resolve_kol(article_id: int) -> tuple[str, str, str] | None:
        conn = sqlite3.connect(DB)
        try:
            row = conn.execute(
                "SELECT url, content_hash FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        url, content_hash = row
        if not content_hash:
            return None
        path = BASE_DIR / "images" / content_hash / "final_content.md"
        return str(path), url, content_hash

    def _resolve_rss(article_id: int) -> tuple[str, str, str] | None:
        conn = sqlite3.connect(DB)
        try:
            row = conn.execute(
                "SELECT url FROM rss_articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        (url,) = row
        article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
        path = BASE_DIR / "rss_content" / article_hash / "final_content.md"
        return str(path), url, article_hash

    def main() -> int:
        p = argparse.ArgumentParser()
        p.add_argument("--source", required=True, choices=["kol", "rss"])
        p.add_argument("--article-id", type=int, required=True)
        args = p.parse_args()

        # D-07 REVISED 2026-05-02 + D-19: RSS is excluded from enrichment entirely.
        # The branch exists for backwards-compat with any legacy caller; it logs + exits 0
        # without resolving DB or invoking the enrich_article skill. RSS articles flow
        # through enrichment/rss_ingest.py's direct translate → ainsert path instead.
        if args.source == "rss":
            print(
                f"RSS excluded per D-07 REVISED 2026-05-02 + D-19 — "
                f"article-id={args.article_id} not enriched (no-op)",
            )
            return 0

        resolved = _resolve_kol(args.article_id)
        if resolved is None:
            print(f"ERROR: kol article id={args.article_id} not found", file=sys.stderr)
            return 2

        article_path, article_url, article_hash = resolved
        env = os.environ.copy()
        env["ARTICLE_PATH"] = article_path
        env["ARTICLE_URL"] = article_url
        env["ARTICLE_HASH"] = article_hash

        print(f"Invoking enrich_article skill for kol id={args.article_id}")
        print(f"  ARTICLE_PATH={article_path}")
        print(f"  ARTICLE_URL={article_url}")
        print(f"  ARTICLE_HASH={article_hash}")

        result = subprocess.run(
            ["hermes", "skill", "run", "enrich_article"],
            env=env,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min per article matches SKILL.md's "up to 10 minutes" ceiling
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode

    if __name__ == "__main__":
        sys.exit(main())
    ```

    **Note on `_resolve_rss`**: keep the helper in the file (unit-tested by Test 2's guard assertion that it is NOT called), but it is unused by `main()` after D-07 REVISED. The helper preserves path-resolution parity with `_resolve_kol` in case future work re-enables the RSS enrich path. If the reviewer prefers, `_resolve_rss` may be deleted — it is not load-bearing.

    Create `tests/unit/test_run_enrich_for_id.py` with the 5 behavioral tests:
    - Use `:memory:` SQLite seeded via `batch_scan_kol.init_db` (for articles) and `enrichment.rss_schema.init_rss_schema` (for rss_articles).
    - Patch `subprocess.run` to capture the env dict and assert env["ARTICLE_PATH"], env["ARTICLE_URL"], env["ARTICLE_HASH"] are set.
    - Patch `config.BASE_DIR` to a tmp dir ending in `omonigraph-vault` to preserve the typo in assertions.
    - Assert the subprocess args list is exactly `["hermes", "skill", "run", "enrich_article"]` — NO --article-id or --source flags.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_run_enrich_for_id.py -v"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/run_enrich_for_id.py` exists.
    - `grep -q "ARTICLE_PATH" enrichment/run_enrich_for_id.py` returns 0.
    - `grep -q "ARTICLE_URL" enrichment/run_enrich_for_id.py` returns 0.
    - `grep -q "ARTICLE_HASH" enrichment/run_enrich_for_id.py` returns 0.
    - `grep -q "hermes.*skill.*run.*enrich_article" enrichment/run_enrich_for_id.py` returns 0.
    - `! grep -q -- "--article-id.*enrich_article" enrichment/run_enrich_for_id.py` — wrong CLI usage MUST be absent.
    - `grep -q "RSS excluded per D-07 REVISED" enrichment/run_enrich_for_id.py` returns 0 (guard message present).
    - `grep -q 'args.source == "rss"' enrichment/run_enrich_for_id.py` returns 0 (short-circuit branch present before any DB/subprocess call).
    - All 5 pytest tests pass (Test 2 MUST assert `subprocess.run` was NOT called on the rss branch).
  </acceptance_criteria>
  <done>Bridge script ready; both KOL and RSS callers can invoke enrich_article correctly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3b.2: Build `enrichment/rss_ingest.py` — EN->CN translate + enrich + LightRAG ingest</name>
  <files>enrichment/rss_ingest.py, tests/unit/test_rss_ingest.py</files>
  <behavior>
    - Test 1: An English RSS article (langdetect='en') triggers ONE DeepSeek translate call (`_translate_to_chinese`); the resulting Chinese body is written to `final_content.md`.
    - Test 2: A Chinese RSS article (langdetect in {'zh-cn','zh-tw','zh'}) skips translation (0 DeepSeek calls for translate); body is written to `final_content.md` as-is.
    - Test 3: `original.md` is always written (English source preserved for debug) before `final_content.md`.
    - Test 4: `final_content.md` is written via .tmp + os.replace (atomic).
    - Test 5 (happy path): `_ingest_lightrag` returns True (ainsert OK AND aget_docs_by_ids returns status='PROCESSED') → `UPDATE rss_articles SET enriched=2 WHERE id=?` is executed for that id.
    - Test 6 (Task 4.2 PROCESSED gate — NEW, MANDATORY per D-19): when `aget_docs_by_ids` returns status='FAILED' or missing doc_id, `_ingest_lightrag` returns False; `UPDATE rss_articles SET enriched=...` is NOT executed (enriched stays at prior value 0). Assert the update statement was never called for that row.
    - Test 7 (`subprocess.run` is NEVER called from `rss_ingest.run()`): use `unittest.mock.patch("subprocess.run")` and assert `mock.call_count == 0` after a full run — enforces D-07 REVISED "no enrich_article invocation".
    - Test 8: `--dry-run` skips DeepSeek translate, skips LightRAG, skips DB writes; prints "DRY: rss id=..." lines per row.
  </behavior>
  <read_first>
    - batch_classify_kol.py (`_call_deepseek` + `get_deepseek_api_key` pattern — mirror for translation)
    - enrichment/merge_and_ingest.py (pattern for LightRAG ainsert + articles.enriched update)
    - enrichment/rss_schema.py (rss_articles + rss_classifications column names)
    - enrichment/run_enrich_for_id.py (Task 3b.1 output — NOT invoked by rss_ingest.py per D-07 REVISED; exists as KOL-only bridge)
    - config.py (BASE_DIR typo preserved: `omonigraph-vault`)
    - ingest_wechat.py lines 1086-1120 (Task 4.2 aget_docs_by_ids verification hook — port this pattern into `_ingest_lightrag`; commit 585aa3b is the reference)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md § infra_composition (v3.1/v3.2 composition + D-07 REVISED + D-19)
    - .planning/phases/05-pipeline-automation/05-00-SUMMARY.md § D (Phase 7 D-09 supersession: LLM → DeepSeek)
    - CLAUDE.md (atomic write; surgical changes; type hints; LLM routing rule)
  </read_first>
  <action>
    Create `enrichment/rss_ingest.py`. **Translation uses DeepSeek via raw HTTP** (CLAUDE.md routing rule: LLM → DeepSeek; Gemini is Vision+Embedding only). **NO enrich_article invocation** per D-07 REVISED 2026-05-02 + D-19 — RSS takes the direct path `translate → ainsert → aget_docs_by_ids verify → enriched=2`.

    ```python
    """RSS ingest: translate English body to Chinese (D-09), then ingest into LightRAG.
    Updates rss_articles.enriched to 2 on success (post-ainsert verification).

    Pipeline per article (D-07 REVISED 2026-05-02 + D-19 — NO enrichment):
      1. Fetch body + metadata (title, url, summary) from rss_articles + rss_classifications.
      2. langdetect on body:
           - 'en'                  -> DeepSeek translate to Chinese (one HTTP call)
           - 'zh-cn'/'zh-tw'/'zh'  -> skip translation
           - anything else         -> skip article (shouldn't happen; prefilter catches)
      3. Atomic write original.md (English source) + final_content.md (Chinese) to
         ~/.hermes/omonigraph-vault/rss_content/<article_hash>/.
      4. lightrag.ainsert(final_content) with doc id f"rss-{article_id}".
      5. Task 4.2 verification hook (MANDATORY per D-19): aget_docs_by_ids([doc_id])
         must return status=='PROCESSED' before the enriched=2 write.
      6. On PROCESSED: UPDATE rss_articles SET enriched=2 WHERE id=?.
         On non-PROCESSED / exception: leave rss_articles.enriched at its prior value
         (0 or -2) so the next batch retries this article — mirrors ingest_wechat.py
         lines 1086-1120 anti-ghost pattern.

    Usage:
        venv/bin/python enrichment/rss_ingest.py                 # ingest all eligible
        venv/bin/python enrichment/rss_ingest.py --dry-run       # preview
        venv/bin/python enrichment/rss_ingest.py --article-id 17 # single article
        venv/bin/python enrichment/rss_ingest.py --max-articles 5
    """
    from __future__ import annotations

    import argparse
    import asyncio
    import hashlib
    import json
    import logging
    import os
    import sqlite3
    import sys
    from pathlib import Path

    import requests
    from langdetect import DetectorFactory, LangDetectException, detect

    # Reuse the key resolver from batch_classify_kol.py (env → ~/.hermes/.env → config.yaml)
    from batch_classify_kol import get_deepseek_api_key
    from config import BASE_DIR, RAG_WORKING_DIR

    DetectorFactory.seed = 0
    DB = Path("data/kol_scan.db")
    RSS_CONTENT_DIR = BASE_DIR / "rss_content"
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")
    CHINESE_LANGS = {"zh-cn", "zh-tw", "zh"}

    logger = logging.getLogger("rss_ingest")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    _TRANSLATE_PROMPT = """请将下面的英文技术文章翻译为中文。保持技术术语的准确性；代码块、URL、Markdown 语法原样保留。不要添加解释性文字，只输出翻译后的中文 Markdown。

英文原文：
{body}
"""

    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)

    def _detect_lang(text: str) -> str:
        try:
            return detect(text[:2000])
        except LangDetectException:
            return "unknown"

    def _translate_to_chinese(api_key: str, body: str) -> str:
        """Translate English body → Chinese via DeepSeek chat completions."""
        prompt = _TRANSLATE_PROMPT.format(body=body)
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
            timeout=300,  # translation of long-form content can be slow
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _eligible_articles(conn: sqlite3.Connection, article_id: int | None,
                            max_articles: int | None) -> list[dict]:
        if article_id is not None:
            sql = """SELECT ra.id, ra.title, ra.url, COALESCE(ra.summary,'') AS summary,
                            MAX(rc.depth_score) AS depth_score, ra.enriched
                     FROM rss_articles ra
                     JOIN rss_classifications rc ON rc.article_id = ra.id
                     WHERE ra.id = ?
                     GROUP BY ra.id"""
            rows = conn.execute(sql, (article_id,)).fetchall()
        else:
            sql = """SELECT ra.id, ra.title, ra.url, COALESCE(ra.summary,'') AS summary,
                            MAX(rc.depth_score) AS depth_score, ra.enriched
                     FROM rss_articles ra
                     JOIN rss_classifications rc ON rc.article_id = ra.id
                     WHERE rc.depth_score >= 2 AND COALESCE(ra.enriched, 0) = 0
                     GROUP BY ra.id
                     ORDER BY ra.fetched_at DESC
                     LIMIT ?"""
            rows = conn.execute(sql, (max_articles or 1000,)).fetchall()
        return [
            {"id": r[0], "title": r[1], "url": r[2], "summary": r[3],
             "depth_score": r[4], "enriched": r[5]}
            for r in rows
        ]

    async def _ingest_lightrag(final_md: str, rss_article_id: int) -> bool:
        """Ingest final_content.md into LightRAG + Task 4.2 PROCESSED verification.

        Returns True ONLY if both (a) ainsert completes without raising AND (b)
        aget_docs_by_ids confirms doc.status == 'PROCESSED'. On any other outcome
        returns False so the caller leaves rss_articles.enriched untouched and the
        next batch retries. Pattern ported verbatim from ingest_wechat.py:1086-1120
        (commit 585aa3b).
        """
        from lightrag import LightRAG
        from lib.lightrag_embedding import embedding_func  # 3072-dim Vertex AI path
        from lib import deepseek_model_complete  # Phase 5 DeepSeek LLM wrapper

        doc_id = f"rss-{rss_article_id}"
        rag = LightRAG(
            working_dir=str(RAG_WORKING_DIR),
            llm_model_func=deepseek_model_complete,
            embedding_func=embedding_func,
            llm_model_name="deepseek-chat",
            embedding_func_max_async=1,
            embedding_batch_num=20,
            llm_model_max_async=2,
        )
        await rag.initialize_storages()

        # Step 1: ainsert
        try:
            await rag.ainsert(final_md, ids=[doc_id])
        except Exception as ex:
            logger.error(f"LightRAG ainsert failed rss_id={rss_article_id}: {ex}")
            return False

        # Step 2: Task 4.2 verification hook — MANDATORY per D-19
        try:
            statuses = await rag.aget_docs_by_ids([doc_id])
        except Exception as ex:
            logger.warning(f"aget_docs_by_ids failed rss_id={rss_article_id}: {ex}")
            return False
        doc_info = (statuses or {}).get(doc_id)
        status = (doc_info or {}).get("status") if isinstance(doc_info, dict) else None
        if status != "PROCESSED":
            logger.warning(
                f"rss_id={rss_article_id} post-ingest status={status!r} (expected 'PROCESSED') — "
                f"leaving rss_articles.enriched unchanged; next batch will retry"
            )
            return False
        return True

    def run(article_id: int | None, max_articles: int | None, dry_run: bool) -> dict:
        conn = sqlite3.connect(DB)
        rows = _eligible_articles(conn, article_id, max_articles)
        logger.info(f"Eligible: {len(rows)} RSS articles")

        api_key = None
        if not dry_run:
            api_key = get_deepseek_api_key()
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY not found in env / ~/.hermes/.env / config.yaml")

        # Per D-07 REVISED + D-19: NO enrich_article invocation, NO enrich_ok/enrich_fail stats.
        stats = {"translated": 0, "ingested": 0, "errors": 0, "dry_run_planned": 0}

        for row in rows:
            aid = row["id"]
            url = row["url"]
            body = row["summary"]  # feedparser summary is our ingestable body
            article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
            hash_dir = RSS_CONTENT_DIR / article_hash

            if dry_run:
                print(f"DRY: rss id={aid} hash={article_hash} -> {hash_dir}/final_content.md")
                stats["dry_run_planned"] += 1
                continue

            try:
                _atomic_write(hash_dir / "original.md", body)

                lang = _detect_lang(body)
                if lang == "en":
                    chinese_body = _translate_to_chinese(api_key, body)
                    stats["translated"] += 1
                elif lang in CHINESE_LANGS:
                    chinese_body = body
                else:
                    logger.warning(f"skip rss id={aid}: unsupported lang={lang}")
                    stats["errors"] += 1
                    continue

                final_md = f"# {row['title']}\n\n{chinese_body}\n\n<!-- source: {url} -->\n"
                _atomic_write(hash_dir / "final_content.md", final_md)

                # Direct LightRAG path — NO enrich_article subprocess (D-07 REVISED + D-19).
                # _ingest_lightrag returns True only if ainsert succeeded AND aget_docs_by_ids
                # confirmed status=='PROCESSED' (Task 4.2 verification hook).
                ingest_ok = asyncio.run(_ingest_lightrag(final_md, aid))
                if ingest_ok:
                    stats["ingested"] += 1
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE rss_articles SET enriched = 2 WHERE id = ?",
                        (aid,),
                    )
                    conn.commit()
                    if cur.rowcount != 1:
                        logger.warning(f"enriched update affected {cur.rowcount} rows for rss id={aid}")
                else:
                    # ainsert threw OR post-ingest status was not PROCESSED.
                    # Leave rss_articles.enriched at its prior value (0 or -2) so the
                    # next batch retries. This mirrors Task 4.2's anti-ghost semantics.
                    logger.warning(f"rss id={aid}: ingest_ok=False, enriched left unchanged for retry")
                    stats["errors"] += 1

            except Exception as ex:
                logger.exception(f"rss id={aid} failed: {ex}")
                stats["errors"] += 1

        conn.close()
        return stats

    def main() -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--article-id", type=int, default=None)
        p.add_argument("--max-articles", type=int, default=None)
        args = p.parse_args()
        stats = run(args.article_id, args.max_articles, args.dry_run)
        print(f"rss_ingest done: {stats}")

    if __name__ == "__main__":
        main()
    ```

    Create `tests/unit/test_rss_ingest.py` with the 8 behavioral tests:
    - Use `:memory:` SQLite seeded with rss_feeds + rss_articles + rss_classifications via init_rss_schema.
    - Patch `enrichment.rss_ingest._translate_to_chinese` (replaces the DeepSeek HTTP call — return a fake Chinese string directly; do NOT patch `requests.post` at the low level).
    - Patch `enrichment.rss_ingest.get_deepseek_api_key` to return a fake key.
    - Patch `enrichment.rss_ingest.asyncio.run` OR `enrichment.rss_ingest._ingest_lightrag` so LightRAG is never actually imported. For Test 5 (happy path) have the patched `_ingest_lightrag` return True; for Test 6 (PROCESSED-gate fail) have it return False.
    - Patch `enrichment.rss_ingest.subprocess.run` and assert it is NOT called across the full run (Test 7 — enforces D-07 REVISED).
    - Patch `config.BASE_DIR` to a tmp dir.
    - Assert atomic write by patching `os.replace` and checking it is called with a `.tmp` suffix source.
    - Assert `UPDATE rss_articles SET enriched = 2` is executed with value 2 on the happy path. Assert it is NOT executed on the PROCESSED-gate-fail path (enriched left unchanged).
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_rss_ingest.py -v &amp;&amp; venv/bin/python enrichment/rss_ingest.py --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/rss_ingest.py` exists; >= 160 lines.
    - `grep -q "UPDATE rss_articles SET enriched = 2" enrichment/rss_ingest.py` returns 0 (only terminal state is 2; no -2 branch in rss_ingest).
    - `grep -q "os.replace" enrichment/rss_ingest.py` returns 0 (atomic write).
    - `grep -q "aget_docs_by_ids" enrichment/rss_ingest.py` returns 0 (Task 4.2 verification hook present).
    - `grep -q "PROCESSED" enrichment/rss_ingest.py` returns 0 (post-ainsert status gate).
    - `grep -q "api.deepseek.com" enrichment/rss_ingest.py` returns 0 (DeepSeek translation endpoint).
    - `grep -q "from batch_classify_kol import get_deepseek_api_key" enrichment/rss_ingest.py` returns 0 (reuses production key resolver).
    - `grep -q "ainsert" enrichment/rss_ingest.py` returns 0.
    - `grep -q "final_content.md" enrichment/rss_ingest.py` returns 0.
    - `! grep -q "google.genai\|from google import genai\|GEMINI_API_KEY" enrichment/rss_ingest.py` — Gemini path MUST be absent per Phase 7 D-09 supersession.
    - `! grep -q "run_enrich_for_id" enrichment/rss_ingest.py` — NO enrich_article invocation per D-07 REVISED 2026-05-02 + D-19.
    - `! grep -q "subprocess" enrichment/rss_ingest.py` — rss_ingest does not spawn subprocesses (belt-and-suspenders on the D-07 REVISED guard).
    - `! grep -q "enriched = -2\|enriched=-2" enrichment/rss_ingest.py` — no -2 terminal state (Task 4.2 leaves enriched at prior value for retry instead).
    - All 8 pytest tests pass.
    - `--dry-run` on remote exits 0 and prints a plan line per eligible article.
    - Manual smoke on a seeded RSS test article: after real run, `sqlite3 data/kol_scan.db "SELECT enriched FROM rss_articles WHERE id=?"` returns 2; `~/.hermes/omonigraph-vault/rss_content/<hash>/final_content.md` exists and contains Chinese text.
  </acceptance_criteria>
  <done>RSS articles flow end-to-end: fetch -> classify -> translate -> enrich -> LightRAG. Digest can now see them.</done>
</task>

</tasks>

<verification>
- `tests/unit/test_run_enrich_for_id.py` passes (5 tests — Test 2 asserts `subprocess.run` was NOT called on the `--source rss` branch).
- `tests/unit/test_rss_ingest.py` passes (8 tests — Test 6 asserts the PROCESSED gate; Test 7 asserts `subprocess.run` is NEVER called from `rss_ingest.run()`).
- `--dry-run` smoke on remote exits 0.
- After one real article run: `enriched=2`, `final_content.md` exists in Chinese, LightRAG entity count grows.
</verification>

<success_criteria>
- D-09 satisfied: English RSS body is translated to Chinese via DeepSeek before LightRAG ingest.
- D-07 REVISED 2026-05-02 + D-19 satisfied: RSS does NOT invoke enrich_article. `rss_ingest.py` takes the direct path translate → ainsert → verify. `run_enrich_for_id.py --source rss` is a guarded no-op for backwards-compat.
- D-16 satisfied: KOL enrichment (out of scope for this plan, handled by Plan 05-04 step_6) is driven by Hermes via the `run_enrich_for_id.py` bridge with the env-var contract.
- Phase 7 D-09 supersession satisfied: translation uses DeepSeek (CLAUDE.md routing rule: LLM → DeepSeek; Gemini is Vision+Embedding only).
- Task 4.2 verification hook satisfied (D-19 anti-ghost): `aget_docs_by_ids([doc_id])` gates the `rss_articles.enriched=2` write; non-PROCESSED outcomes leave `enriched` at its prior value for the next-batch retry.
- `rss_articles.enriched` state machine: 0 (pending) → 2 (ainsert verified). The -2 terminal state is NOT used by `rss_ingest.py` (simplified from earlier Phase 4 D-11 which predated D-07 REVISED).
- BLOCKER 1/2/3 from checker closed.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-03b-SUMMARY.md` with: eligible-row count, DeepSeek translate-call count, ingested count (ainsert + PROCESSED verified), non-PROCESSED retry count (articles left at `enriched=0` for next batch), LightRAG entity delta, sample `final_content.md` Chinese excerpt, confirmation that `subprocess.run` was never invoked from `rss_ingest.py` (D-07 REVISED compliance).
</output>
