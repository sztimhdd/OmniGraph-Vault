---
phase: 05-pipeline-automation
plan: 05
type: execute
wave: 2
depends_on: [05-04]
files_modified:
  - enrichment/daily_digest.py
  - tests/unit/test_daily_digest.py
autonomous: true
requirements: [D-15, D-18]
must_haves:
  truths:
    - "`enrichment/daily_digest.py` selects today's depth>=2 articles via asymmetric UNION ALL: KOL branch (articles JOIN classifications) requires `enriched=2` per Phase 4 contract; RSS branch (rss_articles JOIN rss_classifications) has NO enriched filter per D-07 REVISED 2026-05-02 + D-19. Sort: depth_score DESC, content_length DESC, classified_at DESC."
    - "TOP 5 (configurable) rendered as Markdown per PRD section 3.3.2 sample format"
    - "Markdown includes title, category tag, source, 1-2 line excerpt, link"
    - "Telegram delivery via existing Phase 4 path (reuses TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"
    - "Local archive written atomically to `~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md`"
    - "Empty-state behavior: if zero candidates, skip Telegram (silent log) per CONTEXT.md Claude's Discretion item 4"
    - "`--date YYYY-MM-DD` and `--dry-run` CLI flags supported"
  artifacts:
    - path: "enrichment/daily_digest.py"
      provides: "Candidate query + TOP N renderer + Telegram sender + local archive"
      min_lines: 160
    - path: "tests/unit/test_daily_digest.py"
      provides: "Sort order, Markdown shape, empty-state skip, archive atomic write"
      min_lines: 50
  key_links:
    - from: "enrichment/daily_digest.py candidate query"
      to: "articles + classifications UNION ALL rss_articles + rss_classifications"
      via: "SQL per D-19 (2026-05-02): KOL branch requires enriched=2; RSS branch has NO enriched filter (RSS never enriched per D-07 REVISED). Both branches filter date(fetched_at)=date('now','localtime') AND depth_score>=2."
      pattern: "UNION"
    - from: "enrichment/daily_digest.py Telegram send"
      to: "Phase 4 delivery path via TELEGRAM_BOT_TOKEN env var"
      via: "requests.post to telegram sendMessage"
      pattern: "api.telegram.org"
    - from: "enrichment/daily_digest.py archive"
      to: "~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md"
      via: "atomic tmp-then-rename write per CLAUDE.md convention"
      pattern: "os\\.replace"
---

<objective>
Build `enrichment/daily_digest.py`: gathers today's deep articles (KOL + RSS merged), sorts and truncates to TOP 5, renders Markdown per PRD section 3.3.2, delivers via Telegram, and archives locally with atomic write.

Purpose: The user-visible daily deliverable. Without this, the full pipeline produces no visible output; the user has no signal that the cron ran.

Output: digest generator with Telegram delivery and local archive, ready for cron registration in Plan 05-06.

**v3.1/v3.2 composition note (added 2026-05-01):** On Telegram delivery failure (network error, rate-limit), log structured error with outcome tag `delivery_error` and continue (do NOT crash — archive is the durable record). The 3-day observation in Plan 05-06 Task 6.2 cross-references `docs/OPERATOR_RUNBOOK.md` for Telegram recovery procedures; nothing to add to digest code itself. Empty-state "skip delivery silently" decision is unchanged.

**Enrichment-policy composition note (added 2026-05-02, per D-07 REVISED + D-19):** The digest candidate query is **NOT a symmetric UNION**. Two separate branches with different filters:

- **KOL branch:** `SELECT ... FROM articles a JOIN classifications c ON c.article_id=a.id WHERE c.depth_score>=2 AND a.enriched=2 AND date(a.fetched_at)=date('now','localtime')` — requires `enriched=2` because KOL articles MUST have passed enrichment to be considered "deep" per original Phase 4 contract.
- **RSS branch:** `SELECT ... FROM rss_articles a JOIN rss_classifications c ON c.article_id=a.id WHERE c.depth_score>=2 AND date(a.fetched_at)=date('now','localtime')` — **NO `enriched` filter**. RSS is never enriched (D-07 REVISED 2026-05-02), so gating on `enriched=2` would produce zero RSS candidates forever.

Implementation: `UNION ALL` the two branches then ORDER/LIMIT. Sort criterion unchanged (depth_score DESC, content_length DESC, classified_at DESC). Markdown rendering: add a small source tag like `[KOL]` / `[RSS]` per candidate so reader knows which path the item took.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-04-orchestrate-daily-PLAN.md
@enrichment/rss_schema.py
@config.py
@CLAUDE.md

<interfaces>
PRD section 3.3.2 Markdown sample (abbreviated):
- Header: "OmniGraph-Vault today's quality picks — YYYY-MM-DD"
- Numbered entries: **N. [Topic] Title**, source, excerpt, link
- Footer stats: KOL total + RSS total | deep articles | ingested

Candidate SQL (planner-supplied shape):
```
SELECT 'kol' AS src, a.id, a.title, a.url, a.author AS source, a.content AS body,
       c.topic, c.depth_score, c.classified_at, a.content_length
FROM articles a JOIN classifications c ON c.article_id = a.id
WHERE date(a.fetched_at) = ?
  AND c.depth_score >= 2 AND a.enriched = 2
UNION ALL
SELECT 'rss' AS src, a.id, a.title, a.url, f.name AS source, a.summary AS body,
       c.topic, c.depth_score, c.classified_at, a.content_length
FROM rss_articles a JOIN rss_classifications c ON c.article_id = a.id
                    JOIN rss_feeds f ON a.feed_id = f.id
WHERE date(a.fetched_at) = ?
  AND c.depth_score >= 2 AND a.enriched = 2
ORDER BY depth_score DESC, content_length DESC, classified_at DESC
LIMIT ?;
```

Archive path: `~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md` (typo'd dir preserved per CLAUDE.md).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 5.1: Build `enrichment/daily_digest.py` with candidate query, sort, render, send, archive</name>
  <files>enrichment/daily_digest.py, tests/unit/test_daily_digest.py</files>
  <behavior>
    - Test 1: Given 7 candidate articles, the query+sort returns exactly 5 sorted by depth DESC, length DESC, classified_at DESC.
    - Test 2: Markdown output matches PRD section 3.3.2 shape — header, numbered entries with [topic], source line, excerpt, link, footer stats.
    - Test 3: Empty candidate pool — no Telegram send + log line "no candidates, skipping digest" + no archive file written.
    - Test 4: `--dry-run` does not call Telegram and does not write archive; prints rendered Markdown.
    - Test 5: Archive write uses atomic tmp-then-rename (test: `os.replace` or `.tmp` suffix present in code path).
    - Test 6: Archive path is `~/.hermes/omonigraph-vault/digests/<date>.md` (typo'd dir).
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md section 3.3 full spec
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md Claude's Discretion item 4 (empty-state policy: SKIP on zero candidates, documented)
    - CLAUDE.md (atomic-write convention: .tmp then os.replace)
    - config.py (BASE_DIR — typo'd `omonigraph-vault` dir)
    - enrichment/rss_schema.py (exact column names for UNION query)
    - Search before writing: `grep -l "sendMessage" *.py enrichment/*.py scripts/*.py` to avoid duplicating Phase 4 Telegram helper.
  </read_first>
  <action>
    Create `enrichment/daily_digest.py` with this structure:

    - Module docstring documenting empty-state policy (SKIP on zero candidates) and usage.
    - Imports: argparse, datetime, logging, os, sqlite3, sys; requests; from config import BASE_DIR.
    - Constants: `DB = Path("data/kol_scan.db")`, `DIGEST_DIR = BASE_DIR / "digests"`, `TOP_N = 5`.
    - `CANDIDATE_SQL` constant: exactly the UNION ALL query from the `<interfaces>` block above, with 3 `?` placeholders (date, date, limit).
    - `def _excerpt(body: str, max_chars: int = 120) -> str`: flatten whitespace, truncate with ellipsis.
    - `def gather(date: str, top_n: int = TOP_N) -> tuple[list[dict], dict]`: execute `CANDIDATE_SQL` + stats queries (KOL total, RSS total, deep total); return `(candidates, stats)`.
    - `def render(date: str, candidates: list[dict], stats: dict) -> str`: build Markdown per PRD section 3.3.2. Header line, numbered entries with `[topic] Title`, source line (`source · WeChat` or `source · RSS`), excerpt, link. Footer: `Scanned today: {kol} KOL + {rss} RSS | Deep: {deep} | Ingested: {ingested}`.
    - `def deliver_telegram(markdown: str) -> bool`: read `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars; POST to `https://api.telegram.org/bot{token}/sendMessage` with `parse_mode=Markdown`, `disable_web_page_preview=True`, 15s timeout. Return True on 2xx; False + log on missing creds or HTTP error.
    - `def archive(date: str, markdown: str) -> Path`: mkdir `DIGEST_DIR` parents; write to `{date}.md.tmp` first; `os.replace(tmp, target)` for atomicity; return target path.
    - `def run(date: str, dry_run: bool) -> int`: call `gather`, log "no candidates…" and return 0 if empty; render Markdown; if `dry_run`, print and return 0; otherwise `deliver_telegram` + `archive`; return 0 on success, 1 if Telegram failed (so cron can alert).
    - `def main()`: argparse `--date YYYY-MM-DD` (default today via `dt.date.today().isoformat()`) and `--dry-run`; `sys.exit(run(date, dry_run))`.

    Minimum lines target: 160. Code MUST use type hints on every function signature per Python rules.

    Create `tests/unit/test_daily_digest.py` with the 6 behavioral tests:
    - Use `:memory:` SQLite, create `articles`/`classifications`/`rss_*` schema via the helper calls (init_db + init_rss_schema), seed rows for today and yesterday.
    - Test 1: insert 7 today-depth-3 articles; assert `gather(..., top_n=5)` returns 5 sorted correctly.
    - Test 2: render one row; assert Markdown contains `[topic]`, `· WeChat` or `· RSS`, `阅读原文`, and `http…` URL.
    - Test 3: no inserts; `run(date, False)` returns 0 + logs "no candidates"; no archive file created (use `tmp_path` fixture as DIGEST_DIR override).
    - Test 4: `--dry-run`; `requests.post` mock NOT called; stdout contains Markdown.
    - Test 5: assert `os.replace` is called during archive (patch with `unittest.mock.patch("os.replace")`).
    - Test 6: assert archive path contains `omonigraph-vault` (patch `BASE_DIR` to a tmp dir ending in `omonigraph-vault`).
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_daily_digest.py -v &amp;&amp; venv/bin/python enrichment/daily_digest.py --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/daily_digest.py` exists; at least 160 lines.
    - Exactly one `UNION ALL` in `CANDIDATE_SQL`.
    - `grep -q "ORDER BY depth_score DESC, content_length DESC, classified_at DESC" enrichment/daily_digest.py` returns 0.
    - `grep -q "LIMIT ?" enrichment/daily_digest.py` returns 0 (parameterized top-N).
    - `grep -q "os.replace" enrichment/daily_digest.py` returns 0 (atomic write).
    - `grep -q "BASE_DIR\|omonigraph-vault" enrichment/daily_digest.py` returns 0 (typo preserved).
    - All 6 pytest tests pass.
    - `--dry-run` on remote exits 0 and prints Markdown OR "no candidates" log line.
  </acceptance_criteria>
  <done>Daily digest ready; Wave 2 complete.</done>
</task>

</tasks>

<verification>
- `enrichment/daily_digest.py --dry-run` exits 0 on remote.
- Unit tests pass (6 scenarios).
- Archive path matches typo'd `omonigraph-vault`.
- Empty-state policy: no Telegram on zero candidates (documented).
</verification>

<success_criteria>
- PRD section 3.3.2 Markdown shape reproduced.
- Top-5 selection sorted per PRD section 3.3.1.
- Atomic archive write.
- Telegram delivery via existing Phase 4 path.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-05-SUMMARY.md` with: sample rendered Markdown, candidate query EXPLAIN, empty-state handling policy, archive file path convention.
</output>
