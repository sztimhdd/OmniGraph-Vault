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
requirements: [D-07, D-08, D-09, D-15, D-16]
must_haves:
  truths:
    - "English RSS articles are translated to Chinese BEFORE LightRAG ingest (D-09)"
    - "All depth_score>=2 RSS articles flow through enrich_article skill then LightRAG ainsert"
    - "`rss_articles.enriched` is set to 2 on success and -2 on all-questions-failure (mirrors Phase 4 D-11)"
    - "`final_content.md` is written atomically (.tmp then rename) to ~/.hermes/omonigraph-vault/rss_content/<hash>/"
    - "Original English source is preserved as original.md for debug"
    - "enrich_article skill is invoked via env-var contract (ARTICLE_PATH, ARTICLE_URL, ARTICLE_HASH), NOT CLI flags"
    - "A shared bridge script `run_enrich_for_id.py` works for BOTH kol and rss sources"
    - "`--dry-run` prints planned actions per row with no API calls"
  artifacts:
    - path: "enrichment/run_enrich_for_id.py"
      provides: "Bridge that resolves ARTICLE_PATH/URL/HASH from DB + source type, then invokes enrich_article skill via env vars"
      min_lines: 80
      contains: "ARTICLE_PATH"
    - path: "enrichment/rss_ingest.py"
      provides: "EN-to-CN translation + enrich_article invocation + LightRAG ainsert for depth>=2 RSS articles"
      min_lines: 160
      contains: "rss_articles SET enriched"
    - path: "tests/unit/test_rss_ingest.py"
      provides: "Unit tests for translation branch, ingest branch, enriched=2/-2 state updates, atomic write"
      min_lines: 60
    - path: "tests/unit/test_run_enrich_for_id.py"
      provides: "Unit tests for env-var setup and subprocess invocation for both kol and rss sources"
      min_lines: 40
  key_links:
    - from: "enrichment/rss_ingest.py"
      to: "rss_articles JOIN rss_classifications WHERE depth_score>=2 AND enriched=0"
      via: "sqlite3 SELECT"
      pattern: "rss_classifications"
    - from: "enrichment/rss_ingest.py"
      to: "Gemini translate API (EN->CN) via google.genai"
      via: "client.models.generate_content for english-only articles"
      pattern: "generate_content"
    - from: "enrichment/rss_ingest.py"
      to: "enrichment/run_enrich_for_id.py"
      via: "subprocess with --source rss --article-id <id>"
      pattern: "run_enrich_for_id"
    - from: "enrichment/run_enrich_for_id.py"
      to: "enrich_article Hermes skill"
      via: "os.environ injection + subprocess hermes skill run"
      pattern: "hermes.*skill.*run.*enrich_article"
    - from: "enrichment/rss_ingest.py"
      to: "lightrag.ainsert for Chinese final_content.md"
      via: "LightRAG import pattern matching merge_and_ingest.py"
      pattern: "ainsert"
---

<objective>
Close the RSS ingest gap: translate English RSS articles to Chinese (D-09), run them through the existing enrich_article skill (D-07), and ingest into LightRAG. Ship a shared bridge `run_enrich_for_id.py` that both KOL and RSS paths use to invoke `enrich_article` correctly via its env-var contract.

Purpose: Without this plan the 92 Karpathy RSS feeds half of Phase 5 is non-functional — fetched + classified articles never reach LightRAG, never appear in the digest. BLOCKER 1/2/3 from the checker report.

Output: `enrichment/rss_ingest.py` produces LightRAG entries for depth>=2 RSS articles; `enrichment/run_enrich_for_id.py` is the canonical skill-invocation bridge for both sources.
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
- **Translation path unchanged**: D-08/D-09 EN→CN translation happens as specified. Cascade/checkpoint are post-translation concerns.
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
    - Test 1: `--source kol --article-id 1` resolves ARTICLE_PATH to `~/.hermes/omonigraph-vault/images/<hash>/final_content.md`, ARTICLE_URL from `articles.url`, ARTICLE_HASH from `articles.content_hash`.
    - Test 2: `--source rss --article-id 1` resolves ARTICLE_PATH to `~/.hermes/omonigraph-vault/rss_content/<hash>/final_content.md`, ARTICLE_URL from `rss_articles.url`, ARTICLE_HASH = md5(url)[:12].
    - Test 3: Non-zero exit when article not found in DB.
    - Test 4: `subprocess.run` is called with `["hermes", "skill", "run", "enrich_article"]` and the env dict contains ARTICLE_PATH, ARTICLE_URL, ARTICLE_HASH — NOT as CLI flags.
    - Test 5: Invalid `--source` value exits with clear error.
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

        if args.source == "kol":
            resolved = _resolve_kol(args.article_id)
        else:
            resolved = _resolve_rss(args.article_id)

        if resolved is None:
            print(f"ERROR: {args.source} article id={args.article_id} not found", file=sys.stderr)
            return 2

        article_path, article_url, article_hash = resolved
        env = os.environ.copy()
        env["ARTICLE_PATH"] = article_path
        env["ARTICLE_URL"] = article_url
        env["ARTICLE_HASH"] = article_hash

        print(f"Invoking enrich_article skill for {args.source} id={args.article_id}")
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
    - All 5 pytest tests pass.
  </acceptance_criteria>
  <done>Bridge script ready; both KOL and RSS callers can invoke enrich_article correctly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3b.2: Build `enrichment/rss_ingest.py` — EN->CN translate + enrich + LightRAG ingest</name>
  <files>enrichment/rss_ingest.py, tests/unit/test_rss_ingest.py</files>
  <behavior>
    - Test 1: An English RSS article (langdetect='en') triggers ONE Gemini translate call; the resulting Chinese body is written to `final_content.md`.
    - Test 2: A Chinese RSS article (langdetect in {'zh-cn','zh-tw','zh'}) skips translation; body is written to `final_content.md` as-is.
    - Test 3: `original.md` is always written (English source preserved for debug) before `final_content.md`.
    - Test 4: `final_content.md` is written via .tmp + os.replace (atomic).
    - Test 5: After a successful run on an article, `UPDATE rss_articles SET enriched=2` is executed for that id.
    - Test 6: When enrich_article subprocess returns non-zero, `UPDATE rss_articles SET enriched=-2` is executed (partial — body was ingested but enrichment failed).
    - Test 7: `--dry-run` skips Gemini calls, skips subprocess, skips LightRAG; prints planned actions per row.
  </behavior>
  <read_first>
    - skills/enrich_article/SKILL.md (env-var contract reused via run_enrich_for_id.py)
    - enrichment/merge_and_ingest.py (pattern for LightRAG ainsert + articles.enriched update)
    - enrichment/rss_schema.py (rss_articles + rss_classifications column names)
    - enrichment/run_enrich_for_id.py (Task 3b.1 output — invoked per article)
    - config.py (BASE_DIR typo preserved)
    - ingest_wechat.py lines 704-716 (articles.enriched update pattern)
    - CLAUDE.md (atomic write; surgical changes; type hints)
  </read_first>
  <action>
    Create `enrichment/rss_ingest.py`:

    ```python
    """RSS ingest: translate English body to Chinese (D-09), run enrich_article,
    then ingest into LightRAG. Updates rss_articles.enriched state (2 or -2).

    Pipeline per article:
      1. Fetch body + metadata (title, url, summary) from rss_articles + rss_classifications.
      2. langdetect on body:
           - 'en'                -> Gemini translate to Chinese (one LLM call)
           - 'zh-cn'/'zh-tw'/'zh' -> skip translation
           - anything else       -> skip article (shouldn't happen; prefilter catches)
      3. Atomic write original.md (English source) + final_content.md (Chinese) to
         ~/.hermes/omonigraph-vault/rss_content/<article_hash>/.
      4. Invoke enrichment/run_enrich_for_id.py --source rss --article-id <id>.
         On non-zero exit: set enriched=-2; body is ingested un-enriched in step 5 anyway.
         On zero exit: the skill appends Zhihu summaries to final_content.md.
      5. lightrag.ainsert(final_content) with metadata {source: 'rss', rss_article_id: <id>}.
      6. UPDATE rss_articles SET enriched = (2 if enrich ok else -2) WHERE id = ?.

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
    import logging
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path
    from typing import Any

    from google import genai
    from google.genai import types
    from langdetect import DetectorFactory, LangDetectException, detect

    from config import BASE_DIR, RAG_WORKING_DIR

    DetectorFactory.seed = 0
    DB = Path("data/kol_scan.db")
    RSS_CONTENT_DIR = BASE_DIR / "rss_content"
    TRANSLATE_MODEL = os.environ.get("TRANSLATE_MODEL", "gemini-2.5-flash")
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

    def _translate_to_chinese(client: Any, body: str) -> str:
        prompt = _TRANSLATE_PROMPT.format(body=body)
        response = client.models.generate_content(
            model=TRANSLATE_MODEL,
            contents=prompt,
        )
        return response.text.strip()

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
        """Ingest final_content.md into LightRAG. Mirrors merge_and_ingest pattern."""
        from lightrag import LightRAG
        from lightrag_embedding import embedding_func
        from ingest_wechat import llm_model_func  # reuse existing wrapper

        rag = LightRAG(
            working_dir=str(RAG_WORKING_DIR),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            llm_model_name="gemini-2.5-flash",
            embedding_func_max_async=1,
            embedding_batch_num=20,
            llm_model_max_async=2,
        )
        await rag.initialize_storages()
        try:
            await rag.ainsert(final_md, ids=[f"rss-{rss_article_id}"])
            return True
        except Exception as ex:
            logger.error(f"LightRAG ainsert failed rss_id={rss_article_id}: {ex}")
            return False

    def run(article_id: int | None, max_articles: int | None, dry_run: bool) -> dict:
        conn = sqlite3.connect(DB)
        rows = _eligible_articles(conn, article_id, max_articles)
        logger.info(f"Eligible: {len(rows)} RSS articles")

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"]) if not dry_run else None
        stats = {"translated": 0, "ingested": 0, "enrich_ok": 0, "enrich_fail": 0,
                 "errors": 0, "dry_run_planned": 0}

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
                    chinese_body = _translate_to_chinese(client, body)
                    stats["translated"] += 1
                elif lang in CHINESE_LANGS:
                    chinese_body = body
                else:
                    logger.warning(f"skip rss id={aid}: unsupported lang={lang}")
                    stats["errors"] += 1
                    continue

                final_md = f"# {row['title']}\n\n{chinese_body}\n\n<!-- source: {url} -->\n"
                _atomic_write(hash_dir / "final_content.md", final_md)

                enrich_rc = subprocess.run(
                    ["venv/bin/python", "enrichment/run_enrich_for_id.py",
                     "--source", "rss", "--article-id", str(aid)],
                    timeout=900,
                ).returncode
                enrich_ok = (enrich_rc == 0)
                if enrich_ok:
                    stats["enrich_ok"] += 1
                else:
                    stats["enrich_fail"] += 1

                # Re-read final_content.md since enrich_article may have appended Zhihu summaries
                final_md = (hash_dir / "final_content.md").read_text(encoding="utf-8")
                ingest_ok = asyncio.run(_ingest_lightrag(final_md, aid))
                if ingest_ok:
                    stats["ingested"] += 1

                final_state = 2 if (enrich_ok and ingest_ok) else -2
                cur = conn.cursor()
                cur.execute(
                    "UPDATE rss_articles SET enriched = ? WHERE id = ?",
                    (final_state, aid),
                )
                conn.commit()
                if cur.rowcount != 1:
                    logger.warning(f"enriched update affected {cur.rowcount} rows for rss id={aid}")

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

    Create `tests/unit/test_rss_ingest.py` with the 7 behavioral tests:
    - Use `:memory:` SQLite seeded with rss_feeds + rss_articles + rss_classifications via init_rss_schema.
    - Patch `google.genai.Client`, `langdetect.detect`, `subprocess.run`, and `asyncio.run` (so LightRAG is never actually called).
    - Patch `config.BASE_DIR` to a tmp dir.
    - Assert atomic write by patching `os.replace` and checking it is called with a `.tmp` suffix source.
    - Assert `UPDATE rss_articles SET enriched = ?` is executed with value 2 on success path, -2 on enrich-failure path.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_rss_ingest.py -v &amp;&amp; venv/bin/python enrichment/rss_ingest.py --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/rss_ingest.py` exists; >= 160 lines.
    - `grep -q "UPDATE rss_articles SET enriched" enrichment/rss_ingest.py` returns 0.
    - `grep -q "os.replace" enrichment/rss_ingest.py` returns 0 (atomic write).
    - `grep -q "run_enrich_for_id.py" enrichment/rss_ingest.py` returns 0 (uses bridge, not hardcoded skill call).
    - `grep -q "ainsert" enrichment/rss_ingest.py` returns 0.
    - `grep -q "final_content.md" enrichment/rss_ingest.py` returns 0.
    - All 7 pytest tests pass.
    - `--dry-run` on remote exits 0 and prints a plan line per eligible article.
    - Manual smoke on a seeded RSS test article: after real run, `sqlite3 data/kol_scan.db "SELECT enriched FROM rss_articles WHERE id=?"` returns 2; `~/.hermes/omonigraph-vault/rss_content/<hash>/final_content.md` exists and contains Chinese text.
  </acceptance_criteria>
  <done>RSS articles flow end-to-end: fetch -> classify -> translate -> enrich -> LightRAG. Digest can now see them.</done>
</task>

</tasks>

<verification>
- `tests/unit/test_run_enrich_for_id.py` passes (5 tests).
- `tests/unit/test_rss_ingest.py` passes (7 tests).
- `--dry-run` smoke on remote exits 0.
- After one real article run: `enriched=2`, `final_content.md` exists in Chinese, LightRAG entity count grows.
</verification>

<success_criteria>
- D-09 satisfied: English RSS body is translated to Chinese before LightRAG ingest.
- D-07 satisfied: all depth>=2 RSS go through enrich_article via the correct env-var contract.
- D-16 satisfied: Hermes skill drives the enrichment via the bridge, not hardcoded CLI flags.
- `rss_articles.enriched` state machine mirrors Phase 4 D-11.
- BLOCKER 1/2/3 from checker closed.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-03b-SUMMARY.md` with: eligible-row count, translate-call count, enrich_ok/fail split, LightRAG entity delta, sample `final_content.md` Chinese excerpt.
</output>
