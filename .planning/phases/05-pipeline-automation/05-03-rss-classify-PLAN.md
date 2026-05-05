---
phase: 05-pipeline-automation
plan: 03
type: execute
wave: 1
depends_on: [05-01, 05-02]
files_modified:
  - enrichment/rss_classify.py
  - tests/unit/test_rss_classify.py
autonomous: true
requirements: [D-08, D-15]
must_haves:
  truths:
    - "`enrichment/rss_classify.py` reads unclassified rss_articles and writes rows to rss_classifications"
    - "Classifier LLM call reuses `batch_classify_kol.py` logic (same prompt shape + same JSON parse + same topic taxonomy)"
    - "EN→CN handling happens inside the prompt per D-08 — no separate translation step"
    - "Depth score parsing is strict (1-3 integer, bounded) with UNIQUE(article_id, topic) dedup"
    - "LLM emits BOTH `depth_score (1-3)` AND `dimensions: list[str]` (subset of 7-dim taxonomy: architecture/project/library/framework/skill/tool/idea); written as JSON-encoded string into `rss_classifications.dimensions` column"
    - "Per-article try/except — one LLM failure does not abort the run"
    - "Supports `--article-id N --dry-run` for single-article test mode"
  artifacts:
    - path: "enrichment/rss_classify.py"
      provides: "LLM classifier for RSS articles writing to rss_classifications"
      min_lines: 140
    - path: "tests/unit/test_rss_classify.py"
      provides: "Mock LLM tests for parse, dedup, failure tolerance"
      min_lines: 50
  key_links:
    - from: "enrichment/rss_classify.py"
      to: "rss_articles SELECT WHERE NOT IN rss_classifications"
      via: "sqlite3 JOIN/NOT EXISTS"
      pattern: "NOT EXISTS"
    - from: "enrichment/rss_classify.py"
      to: "INSERT INTO rss_classifications"
      via: "Gemini LLM classifier output parsed to depth_score"
      pattern: "INSERT.*INTO rss_classifications"
---

<objective>
Build `enrichment/rss_classify.py`: takes unclassified rss_articles, runs Gemini LLM classification with a prompt that handles both English and Chinese input (translating to Chinese output per D-08 WITHIN the same prompt), and writes rows to `rss_classifications`. Reuses the classifier logic pattern from `batch_classify_kol.py`.

Purpose: Wave 2 orchestrator + Wave 2 daily digest both need `rss_classifications.depth_score` populated to filter for the "depth≥2" candidate pool.

Output: runnable classifier + unit tests for parse strictness, dedup, and fault tolerance.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md
@batch_classify_kol.py
@enrichment/rss_schema.py

<infra_composition>
**v3.1/v3.2 infrastructure composition (added 2026-05-01; extended 2026-05-02 post-Wave 0):**

- The `rss_classifications` table stays a separate table (different FK target than Phase 10's `classifications` which points at `articles`). **But column design MUST mirror Phase 10's `classifications` schema** for operational consistency: columns `article_id`, `depth_score`, `topic`, `rationale`, `classified_at`. If the existing schema (from 05-01) differs, flag in SUMMARY — do NOT silently diverge.
- v3.2 Phase 12 checkpoint stage `classify` is already marked by `batch_classify_kol.py` for KOL path. `enrichment/rss_classify.py` SHOULD mark `lib.checkpoint.mark_stage(ckpt_hash, "classify")` per RSS article it successfully classifies, using `ckpt_hash = lib.checkpoint.get_article_hash(rss_url)`. Non-fatal if skipped — 05-03b's ingest wrapper will re-mark anyway — but consistency is cleaner.
- **Classifier LLM is DeepSeek, NOT Gemini (Wave 0 close-out, Phase 7 D-09 supersession 2026-05-02):** Per CLAUDE.md routing rule "LLM → DeepSeek, Gemini only for Vision + Embedding" and `batch_classify_kol.py` production state (`deepseek-chat` via raw HTTP). `rss_classify.py` MUST mirror `batch_classify_kol.py:_call_deepseek` + `get_deepseek_api_key` pattern — do NOT import `google.genai` for classification. Prompt enforces JSON-only output; code strips optional ```` ``` ```` fences before `json.loads`. See `05-00-SUMMARY.md` § D (Phase 7 D-09 supersession) for rationale.
- No change to D-08 (EN→CN in prompt) or the batch_classify_kol reuse pattern.
</infra_composition>

<interfaces>
From `batch_classify_kol.py` (existing production classifier — mirror this shape; DO NOT copy the whole file, reuse only what you need):

```python
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

def get_deepseek_api_key() -> str | None:
    # checks DEEPSEEK_API_KEY env, then ~/.hermes/.env, then ~/.hermes/config.yaml providers.deepseek.api_key
    ...

def _call_deepseek(prompt: str, api_key: str) -> dict | None:
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0},
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip optional ``` fences before json.loads
    if content.startswith("```"):
        start = content.find("\n") + 1
        end = content.rfind("```")
        if end > start:
            content = content[start:end].strip()
    return json.loads(content)
```

Topic taxonomy (from `batch_classify_kol.py --topic` CLI usage in Phase 4 / Plan 05-00b Task 0b.1):
`{Agent, LLM, RAG, NLP, CV}` — RSS uses the SAME taxonomy per PRD §3.1.5 "分类 topic 与 KOL 共用同一套标签体系".

Depth score definition (PRD §3.1.5):
- 1 = 资讯/快讯 (news/quick post)
- 2 = 技术教程/分析 (tutorial/analysis)
- 3 = 深度研究/架构拆解 (deep research/architecture breakdown)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 3.1: Build `enrichment/rss_classify.py` with bilingual prompt and strict parse</name>
  <files>enrichment/rss_classify.py, tests/unit/test_rss_classify.py</files>
  <behavior>
    - Test 1: An English article + `--topic Agent` produces a `rss_classifications` row with `topic='Agent'`, `depth_score` ∈ {1,2,3}, `reason` in Chinese (D-08 enforcement).
    - Test 2: Re-classifying the same (article_id, topic) is a no-op — UNIQUE constraint raises IntegrityError caught silently.
    - Test 3: LLM returns malformed JSON — parse fails gracefully, logged, article skipped; no partial row inserted.
    - Test 4: `--article-id N --dry-run` does not write to DB; prints the would-be row.
    - Test 5: `--max-articles N` limits the batch.
  </behavior>
  <read_first>
    - batch_classify_kol.py (full file — extract `_call_deepseek` + `get_deepseek_api_key` patterns; mirror the raw HTTP shape, JSON parse, and fence-stripping. NOTE: batch_classify_kol.py has both a Gemini branch and a DeepSeek branch via `--classifier`; rss_classify.py uses DeepSeek only.)
    - .planning/phases/05-pipeline-automation/05-PRD.md §3.1.5 (RSS classifier responsibilities)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (D-08 EN→CN in prompt, not separate step)
    - .planning/phases/05-pipeline-automation/05-00-SUMMARY.md § D (Phase 7 D-09 supersession → DeepSeek for classification; rationale)
    - enrichment/rss_schema.py (exact column list for INSERT)
  </read_first>
  <action>
    Create `enrichment/rss_classify.py`. **LLM is DeepSeek via raw HTTP** (mirrors `batch_classify_kol.py`'s production pattern — do NOT use `google.genai`):

    ```python
    """RSS article classifier — DeepSeek tags each article with depth_score per topic.

    Mirrors batch_classify_kol.py's DeepSeek pattern (raw HTTP to api.deepseek.com).
    Adapted for RSS:
      - reads from rss_articles (not articles)
      - writes to rss_classifications
      - prompt asks LLM to output in Chinese regardless of source-article language (D-08)

    Topic taxonomy is shared with KOL: Agent, LLM, RAG, NLP, CV.

    Usage:
        venv/bin/python enrichment/rss_classify.py
        venv/bin/python enrichment/rss_classify.py --article-id 1 --dry-run
        venv/bin/python enrichment/rss_classify.py --max-articles 20
    """
    from __future__ import annotations

    import argparse
    import json
    import logging
    import os
    import sqlite3
    import sys
    import time
    from pathlib import Path

    import requests

    # Reuse the key resolver from batch_classify_kol.py (env → ~/.hermes/.env → config.yaml)
    from batch_classify_kol import get_deepseek_api_key

    DB = Path("data/kol_scan.db")
    DEFAULT_TOPICS = ("Agent", "LLM", "RAG", "NLP", "CV")
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL = os.environ.get("CLASSIFIER_MODEL", "deepseek-chat")
    CLASSIFY_PROMPT = """
你是技术文章分类器。给定一篇文章的标题和正文（可能是英文或中文），请对它在主题 "{topic}" 上做分类。

**规则**：
- 必须用中文回答 reason（无论原文语言）。
- depth_score: 1=资讯/快讯，2=技术教程/分析，3=深度研究/架构拆解。
- relevant: 0 或 1（是否与主题相关）。
- excluded: 0 或 1（是否应被剔除，例如广告/招聘/纯转载）。
- dimensions: list[str] — 选自 7 维分类法：{{"architecture","project","library","framework","skill","tool","idea"}}。一篇文章可对应 1-3 个维度；至少返回 1 个。第 1 个为主维度（primary），用于 daily-digest 分组。
- 只输出 JSON，不要任何其他文字。不要代码块围栏，不要解释。

输入：
title: {title}
content: {content}

输出 JSON 格式：
{{"topic": "{topic}", "depth_score": 1|2|3, "relevant": 0|1, "excluded": 0|1, "reason": "<中文简要说明>", "dimensions": ["<primary>", "<optional secondary>", ...]}}
"""

    logger = logging.getLogger("rss_classify")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def _call_deepseek(prompt: str, api_key: str) -> dict:
        """Raw HTTP call to DeepSeek chat completions. Returns parsed JSON dict. Raises on malformed."""
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip optional ``` fences (DeepSeek sometimes wraps even when told not to)
        if content.startswith("```"):
            start = content.find("\n") + 1
            end = content.rfind("```")
            if end > start:
                content = content[start:end].strip()
        return json.loads(content)

    VALID_DIMENSIONS = {"architecture", "project", "library", "framework", "skill", "tool", "idea"}

    def _classify(api_key: str, title: str, content: str, topic: str) -> dict:
        prompt = CLASSIFY_PROMPT.format(topic=topic, title=title[:200], content=content[:4000])
        data = _call_deepseek(prompt, api_key)
        # Strict parse
        depth = int(data["depth_score"])
        assert 1 <= depth <= 3
        # Dimensions: list[str] subset of 7-dim taxonomy; LLM must return ≥ 1.
        raw_dims = data.get("dimensions") or []
        if not isinstance(raw_dims, list):
            raise ValueError(f"dimensions must be list, got {type(raw_dims).__name__}")
        dims = [d for d in raw_dims if isinstance(d, str) and d in VALID_DIMENSIONS]
        if not dims:
            # Fallback: do not lose the row if LLM returned bad/empty dimensions; tag as "idea"
            dims = ["idea"]
        return {
            "topic": topic,
            "depth_score": depth,
            "relevant": int(bool(data.get("relevant", 0))),
            "excluded": int(bool(data.get("excluded", 0))),
            "reason": str(data.get("reason", ""))[:500],
            "dimensions": dims,
        }

    def _eligible_articles(conn: sqlite3.Connection, topics: tuple[str, ...],
                           article_id: int | None, max_articles: int | None) -> list[tuple[int, str, str]]:
        if article_id is not None:
            rows = conn.execute(
                "SELECT id, title, COALESCE(summary,'') FROM rss_articles WHERE id=?",
                (article_id,),
            ).fetchall()
        else:
            # Articles that do NOT yet have classifications for ALL requested topics
            placeholders = ",".join("?" for _ in topics)
            rows = conn.execute(
                f"""SELECT a.id, a.title, COALESCE(a.summary, '')
                    FROM rss_articles a
                    WHERE (SELECT COUNT(*) FROM rss_classifications c
                           WHERE c.article_id = a.id AND c.topic IN ({placeholders})) < ?
                    ORDER BY a.fetched_at DESC
                    LIMIT ?""",
                (*topics, len(topics), max_articles or 1000),
            ).fetchall()
        return rows

    def run(topics: tuple[str, ...], article_id: int | None,
            max_articles: int | None, dry_run: bool) -> dict:
        conn = sqlite3.connect(DB)
        rows = _eligible_articles(conn, topics, article_id, max_articles)
        api_key = None
        if not dry_run:
            api_key = get_deepseek_api_key()
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY not found in env / ~/.hermes/.env / config.yaml")
        stats = {"classified": 0, "failed": 0}
        for (aid, title, content) in rows:
            for topic in topics:
                try:
                    if dry_run:
                        logger.info(f"DRY: a={aid} t={topic}")
                        continue
                    result = _classify(api_key, title, content, topic)
                    logger.info(f"a={aid} t={topic} depth={result['depth_score']} exc={result['excluded']}")
                    try:
                        conn.execute(
                            """INSERT INTO rss_classifications
                               (article_id, topic, depth_score, relevant, excluded, reason, dimensions)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (aid, topic, result["depth_score"], result["relevant"],
                             result["excluded"], result["reason"], json.dumps(result["dimensions"])),
                        )
                        conn.commit()
                        stats["classified"] += 1
                    except sqlite3.IntegrityError:
                        # UNIQUE(article_id, topic) — re-classify no-op
                        pass
                except Exception as ex:
                    logger.warning(f"classify failed a={aid} t={topic}: {ex}")
                    stats["failed"] += 1
                time.sleep(0.3)  # gentle throttle
        conn.close()
        return stats

    def main() -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--topic", action="append", default=None,
                       help="Topic(s) to classify against (default: Agent,LLM,RAG,NLP,CV)")
        p.add_argument("--article-id", type=int, default=None)
        p.add_argument("--max-articles", type=int, default=None)
        p.add_argument("--dry-run", action="store_true")
        args = p.parse_args()
        topics = tuple(args.topic) if args.topic else DEFAULT_TOPICS
        stats = run(topics, args.article_id, args.max_articles, args.dry_run)
        print(f'{{"status": "ok", "classified": {stats["classified"]}, "failed": {stats["failed"]}}}')

    if __name__ == "__main__":
        main()
    ```

    Create `tests/unit/test_rss_classify.py` with the 5 behavioral tests using `unittest.mock.patch("enrichment.rss_classify._call_deepseek", ...)` returning JSON-shaped dict stub responses (the mock replaces the HTTP call + parse together — return already-parsed `dict`, e.g. `{"topic": "Agent", "depth_score": 2, "relevant": 1, "excluded": 0, "reason": "技术分析"}`). Also patch `enrichment.rss_classify.get_deepseek_api_key` to return a fake key for non-dry-run tests.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_rss_classify.py -v &amp;&amp; venv/bin/python enrichment/rss_classify.py --max-articles 2 --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/rss_classify.py` exists; ≥ 140 lines.
    - `grep -q "请用中文回答" enrichment/rss_classify.py OR grep -q "必须用中文" enrichment/rss_classify.py` returns 0 (D-08 enforcement — Chinese-output instruction in prompt).
    - `grep -q "VALID_DIMENSIONS" enrichment/rss_classify.py` returns 0 (7-dim taxonomy guard present).
    - `grep -q "json.dumps(result\[\"dimensions\"\])" enrichment/rss_classify.py` returns 0 (dimensions JSON-encoded into INSERT).
    - `grep -q "UNIQUE.*article_id.*topic\|IntegrityError" enrichment/rss_classify.py` returns 0 (dedup handled).
    - `grep -q "api.deepseek.com" enrichment/rss_classify.py` returns 0 (DeepSeek endpoint).
    - `grep -q "from batch_classify_kol import get_deepseek_api_key" enrichment/rss_classify.py` returns 0 (reuses production key resolver).
    - `! grep -q "google.genai\|from google import genai\|GEMINI_API_KEY" enrichment/rss_classify.py` — Gemini path MUST be absent per Phase 7 D-09 supersession (LLM → DeepSeek).
    - All 5 pytest tests pass.
    - `--max-articles 2 --dry-run` on remote exits 0 and prints classify results without writing.
    - Non-dry run after a fetch populates ≥ 1 row in `rss_classifications`.
  </acceptance_criteria>
  <done>RSS articles flow into `rss_classifications` with depth scores ready for filtering.</done>
</task>

</tasks>

<verification>
- `enrichment/rss_classify.py` runs dry and non-dry on remote.
- Unit tests pass (5 scenarios).
- `rss_classifications` gains rows after live run; re-run is idempotent.
</verification>

<success_criteria>
- D-08 satisfied: EN→CN handled via prompt, not separate step.
- Topic taxonomy shared with KOL (Agent, LLM, RAG, NLP, CV).
- UNIQUE constraint deduplicates re-classifications.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-03-SUMMARY.md` with: article+topic classified count, depth_score distribution, any LLM parse failures and their frequency.
</output>
