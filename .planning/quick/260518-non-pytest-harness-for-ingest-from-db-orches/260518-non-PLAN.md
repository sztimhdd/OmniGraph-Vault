---
phase: quick/260518-non-pytest-harness-for-ingest-from-db-orches
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/_ingest_fixtures.py
  - tests/unit/test_ingest_from_db_orchestration.py
  - CLAUDE.md
autonomous: true
requirements:
  - HARNESS-01
  - HARNESS-02
  - HARNESS-03

must_haves:
  truths:
    - "tests/unit/_ingest_fixtures.py exists and exports in_memory_db, mock_rag, patch_layer_funcs, sample_kol_row, sample_rss_row"
    - "tests/unit/test_ingest_from_db_orchestration.py contains exactly 5 tests (T1..T5) and all pass under venv/Scripts/python.exe -m pytest"
    - "CLAUDE.md HIGHEST PRIORITY PRINCIPLES section ends with new principle #7 inserted after #6's 'Full discipline doc' line and before '## Project Summary'"
    - "No business code is modified — git diff against batch_ingest_from_spider.py / lib/article_filter.py / lib/scraper.py / ingest_wechat.py shows zero changes"
    - "Tests are deterministic — no real DeepSeek / Vertex AI / SiliconFlow / Apify HTTP, no time.time wallclock dependence outside the explicit T4 budget-exhausted scenario"
  artifacts:
    - path: "tests/unit/_ingest_fixtures.py"
      provides: "Reusable fixture module: in-memory SQLite seeded with production schema (incl. ingestions L1585-L1600 verbatim), AsyncMock rag, all-layer patch helper, 8-col KOL/RSS row factories"
      min_lines: 120
    - path: "tests/unit/test_ingest_from_db_orchestration.py"
      provides: "5 behavior-anchoring tests T1..T5 against ingest_from_db()"
      contains: "test_layer1_reject_writes_skipped_with_correct_source"
    - path: "CLAUDE.md"
      provides: "Updated HIGHEST PRIORITY PRINCIPLES section with new principle #7 (behavior-anchor harness rule)"
      contains: "Behavior-Anchor Harness"
  key_links:
    - from: "tests/unit/test_ingest_from_db_orchestration.py"
      to: "tests/unit/_ingest_fixtures.py"
      via: "import"
      pattern: "from tests\\.unit\\._ingest_fixtures import|from \\._ingest_fixtures import"
    - from: "tests/unit/_ingest_fixtures.py"
      to: "batch_ingest_from_spider.py L1585-L1600 ingestions schema"
      via: "verbatim CREATE TABLE copy"
      pattern: "CHECK \\(source IN \\('wechat', 'rss'\\)\\)"
    - from: "CLAUDE.md HIGHEST PRIORITY PRINCIPLES section"
      to: "test_ingest_from_db_orchestration.py"
      via: "principle #7 names the file as the canonical harness"
      pattern: "test_ingest_from_db_orchestration"
---

<objective>
Build a pytest behavior-anchoring harness for `batch_ingest_from_spider.py:ingest_from_db()` consisting of (A) a reusable fixture module, (B) 5 regression tests covering historical prod-only failure modes, and (C) a new HIGHEST PRIORITY PRINCIPLE #7 in CLAUDE.md that codifies the behavior-anchor harness rule.

Purpose: pin the post-v1.0.y ingest orchestration contract so the next contract-shape change (e.g. another column added to the layer2_queue tuple, a new SKIP_REASON_VERSION bump, a new ingestions status) breaks tests at unit level — BEFORE prod cron silently swallows the regression. Direct response to the 2026-05-15 v1.0.z imc bug (single missed call site, plan-checker substring match passed, ghost successes in prod) and the 2026-05-16 image_count_row stale-0 bug.

Output:

- tests/unit/_ingest_fixtures.py (new, ~150 lines)
- tests/unit/test_ingest_from_db_orchestration.py (new, ~280 lines, 5 tests)
- CLAUDE.md (modified, +~25 lines for principle #7)

Scope strictness:

- Pure ADDITIVE — no business code touched
- Single atomic commit (feat(test/quick-260518): ...)
- Verification: `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` shows 5 passed
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@batch_ingest_from_spider.py
@lib/article_filter.py
@lib/scraper.py
@tests/unit/test_max_articles_hard_cap.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from production code. -->
<!-- Use these directly — no codebase exploration needed. -->

From batch_ingest_from_spider.py (top-level constants — do NOT recompute):

```python
SKIP_REASON_VERSION_CURRENT = 1   # L90 — used in every INSERT INTO ingestions
LAYER1_BATCH_SIZE = 30            # imported from lib.article_filter
LAYER2_BATCH_SIZE = 5             # imported from lib.article_filter
DB_PATH                           # module-level Path; monkeypatch this for tests
SLEEP_BETWEEN_ARTICLES            # int; monkeypatch to 0 for fast tests
```

From batch_ingest_from_spider.py L1585-L1600 (ingestions CREATE TABLE — copy VERBATIM into fixture):

```sql
CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'wechat'
        CHECK (source IN ('wechat', 'rss')),
    status TEXT NOT NULL CHECK (status IN (
        'ok', 'failed', 'skipped', 'skipped_ingested',
        'dry_run', 'skipped_graded'
    )),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    skip_reason_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (article_id, source)
)
```

From batch_ingest_from_spider.py L1899 (8-col candidate row tuple unpacked in outer loop):

```python
for i, (art_id, source, title, url, account, body, summary, image_count_row) in enumerate(candidate_rows, 1):
```

From batch_ingest_from_spider.py L2064-L2067 (the queue.append site that 2026-05-15 imc missed):

```python
layer2_queue.append((
    (art_id, source, title, url, account, body, summary, image_count_row),
    body,
))
```

From batch_ingest_from_spider.py L1840-L1841 (drain calls _compute_article_budget_s with kwarg=image_count):

```python
image_count_d = row[7]
article_budget = _compute_article_budget_s(body or "", url=url_d, image_count=image_count_d)
```

From batch_ingest_from_spider.py L2009-L2032 (image_count_row refresh after fresh scrape — 260516-htm fix):

```python
if _needs_scrape(source, body):
    try:
        from lib.scraper import scrape_url
        scraped = await scrape_url(url)
        if scraped and not scraped.summary_only:
            persisted = _persist_scraped_body(conn, art_id, source, scraped)
            if persisted:
                body = persisted
                if (image_count_row or 0) == 0 and len(scraped.images) > 0:
                    image_count_row = len(scraped.images)
    except Exception as e:
        logger.warning(...)
```

From lib/article_filter.py (data classes):

```python
@dataclass(frozen=True)
class ArticleMeta:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    summary: str | None
    content_length: int | None

@dataclass(frozen=True)
class ArticleWithBody:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    body: str

@dataclass(frozen=True)
class FilterResult:
    verdict: Literal["candidate", "reject", "ok", "scrape_fail"] | None
    reason: str
    prompt_version: str

PROMPT_VERSION_LAYER1: str = "layer1_v1_20260512"
PROMPT_VERSION_LAYER2: str = "layer2_v1_20260513"
```

From lib/scraper.py:

```python
@dataclass(frozen=True)
class ScrapeResult:
    markdown: str
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    method: str = ""
    summary_only: bool = False
    content_html: Optional[str] = None
```

Mock-stack reference (mirror tests/unit/test_max_articles_hard_cap.py:_patch_downstream — STYLE NOT VERBATIM):

- monkeypatch.setattr(bi, "DB_PATH", db_path)
- monkeypatch.setattr(bi, "_load_hermes_env", lambda: None)
- monkeypatch.setattr(bi, "get_deepseek_api_key", lambda: "dummy")
- monkeypatch.setattr(bi, "SLEEP_BETWEEN_ARTICLES", 0)
- monkeypatch.setattr(bi, "layer1_pre_filter", AsyncMock(...))
- monkeypatch.setattr(bi, "layer2_full_body_score", AsyncMock(...))
- monkeypatch.setattr(bi, "ingest_article", AsyncMock(...))
- monkeypatch.setattr(bi, "_drain_pending_vision_tasks", AsyncMock(return_value=None))
- monkeypatch.setattr(bi, "has_stage", lambda h, s: False)
- monkeypatch.setitem(sys.modules, "ingest_wechat", fake_iw)  # fake_iw.get_rag = AsyncMock(...)
- monkeypatch.setattr(logging, "basicConfig", lambda *a, **kw: None)  # caplog defence

Late-import patching note (CRITICAL):

- `from ingest_wechat import get_rag` happens INSIDE ingest_from_db at L1705 → patch via sys.modules
- `from lib.scraper import scrape_url` happens INSIDE ingest_from_db at L2011 → patch lib.scraper.scrape_url BEFORE await ingest_from_db
- `_compute_article_budget_s` is module-level in batch_ingest_from_spider — patch via mocker.patch.object(bi, "_compute_article_budget_s", spy)
</interfaces>

<historical_failure_modes_addressed>
T1 — 2026-05-08 dual-source contract: skip_reason_version + source column
T2 — 2026-05-15 v1.0.z imc D2: single missed queue.append leaves row[7] absent → IndexError swallowed → 900s floor → ghost success
T3 — 2026-05-11 quick-260511-mxc: max_articles cap was processed-only → up to LAYER2_BATCH_SIZE-1 leak past cap
T4 — v1.0.x stable: finally block must drain vision + finalize storages on early-exit (budget exhaustion path)
T5 — 2026-05-16 quick-260516-htm: image_count_row stale-0 + post-vision body markers stripped → 900s floor → outer-timeout ghost
</historical_failure_modes_addressed>

<claude_md_principle_7_text>
Insert verbatim into CLAUDE.md after the line `Full discipline doc: \`kb/docs/10-DESIGN-DISCIPLINE.md\` Rule 3 (extended version with concrete curl + Playwright examples).` and before the `## Project Summary` heading. One blank line before, one blank line after.

```
7. Behavior-Anchor Harness for Hot Orchestration Code

**Long-running orchestrators that batch I/O and silently swallow exceptions need pytest harnesses anchored on observable behavior, not internal call shape.**

`batch_ingest_from_spider.py:ingest_from_db()` is the canonical example: 600+ lines, 4 levels of late-imports, 3 layer batches (Layer 1 / scrape / Layer 2), broad `except Exception` handlers around every external call. Five distinct prod-only failure modes have shipped through 256-test green CI in the past 90 days (2026-05-08 dual-source skip, 2026-05-15 missed queue.append, 2026-05-11 max-articles leak, v1.0.x finally-block bypass, 2026-05-16 image_count_row stale-0). Substring-matching plan checkers, mocked unit tests on the modified function, and Hermes natural cron all missed each one — the bug only surfaced as ghost successes / silent budget-floor / wrong source attribution.

**Rule:** any contract-shape change to ingest_from_db (column added to candidate_rows tuple, new SKIP_REASON_VERSION, new layer2 verdict alphabet member, new persistence column, new mid-loop early-exit branch) MUST be accompanied by:

1. A new test in `tests/unit/test_ingest_from_db_orchestration.py` that pins the new behavior on observable post-conditions (rows in seeded in-memory DB; arguments passed to mocked downstream callables; files written under tmp_path).
2. The schema in `tests/unit/_ingest_fixtures.py:in_memory_db()` updated to include any new columns the production SELECT/INSERT touches — fixture drift is itself a contract-change failure mode (mirrors the 2026-05-15 lesson #2 "test fixture CREATE TABLE not synced with migration silently masks the downstream bug").
3. Verification command run locally: `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` shows all tests pass.

This rule applies ONLY to `ingest_from_db` and any future orchestrator that meets these three signals: (a) >300 LOC of nested batches, (b) silent broad except handlers around external calls, (c) cost-or-correctness consequences from missed call sites (paid API spend / DB writes that affect tomorrow's candidate pool / ghost successes). Smaller helpers covered by their own focused tests do not need this discipline. The list of in-scope orchestrators is currently {`ingest_from_db`} and grows ONLY by adding a name to this rule, never implicitly.
```

</claude_md_principle_7_text>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build _ingest_fixtures.py harness module</name>
  <files>tests/unit/_ingest_fixtures.py</files>
  <action>
Create the fixture module. Single file, ~150 lines, no test functions (NOT a conftest — leading underscore prevents pytest auto-collection on the file basename, and it's not named conftest.py so it's NOT auto-applied to other tests).

Module-level imports + setup (top of file):

```python
"""Behavior-anchor harness fixtures for ingest_from_db orchestration tests.

See CLAUDE.md HIGHEST PRIORITY PRINCIPLE #7. Any contract-shape change to
batch_ingest_from_spider.ingest_from_db requires updating both this module
(if a new column or SQL touched) AND test_ingest_from_db_orchestration.py.

Fixture drift = silent contract-change failure (2026-05-15 lesson #2).
"""
from __future__ import annotations

import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")  # Phase 5 cross-coupling defence

import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
```

Required exports:

1. `in_memory_db() -> sqlite3.Connection` — opens `:memory:` connection, runs `executescript` with the production schema. The ingestions CREATE TABLE clause MUST be byte-identical to batch_ingest_from_spider.py L1585-L1600 (incl. CHECK + UNIQUE + DEFAULT 0 for skip_reason_version). Other tables: accounts (id, name), articles (id, account_id, title, url, digest, body, image_count INTEGER DEFAULT 0, layer1_verdict, layer1_reason, layer1_at, layer1_prompt_version, layer2_verdict, layer2_reason, layer2_at, layer2_prompt_version), rss_feeds (id, name), rss_articles (mirror of articles but with feed_id + summary instead of account_id + digest), classifications (article_id, topic, depth_score, depth, topics, rationale, relevant, UNIQUE(article_id, topic)). Pre-seed `INSERT INTO accounts(id, name) VALUES (1, 'kol-acc-A')` and `INSERT INTO rss_feeds(id, name) VALUES (1, 'rss-feed-A')`. Return the connection.

2. `mock_rag() -> MagicMock` — returns MagicMock with `.ainsert = AsyncMock(return_value=None)`, `.finalize_storages = AsyncMock(return_value=None)`, `.adelete_by_doc_id = AsyncMock(return_value=None)`.

3. `patch_layer_funcs(monkeypatch, *, layer1_results=None, layer2_results=None, scrape_result=None, ingest_outcome=(True, 100.0, True), rag=None) -> dict[str, Any]` — applies the full mock stack and returns a dict of installed mocks for assertion access. Implementation outline:

```python
import batch_ingest_from_spider as bi
import lib.scraper

# 1. layer1
layer1_mock = AsyncMock(return_value=list(layer1_results or []))
monkeypatch.setattr(bi, "layer1_pre_filter", layer1_mock)

# 2. layer2
layer2_mock = AsyncMock(return_value=list(layer2_results or []))
monkeypatch.setattr(bi, "layer2_full_body_score", layer2_mock)

# 3. persist helpers — no-op MagicMock (sync, not async)
p1 = MagicMock(return_value=None)
p2 = MagicMock(return_value=None)
monkeypatch.setattr(bi, "persist_layer1_verdicts", p1)
monkeypatch.setattr(bi, "persist_layer2_verdicts", p2)

# 4. scrape
scrape_mock = AsyncMock(return_value=scrape_result)
monkeypatch.setattr(lib.scraper, "scrape_url", scrape_mock)

# 5. drain vision
drain_mock = AsyncMock(return_value=None)
monkeypatch.setattr(bi, "_drain_pending_vision_tasks", drain_mock)

# 6. api key + env
monkeypatch.setattr(bi, "_load_hermes_env", lambda: None)
monkeypatch.setattr(bi, "get_deepseek_api_key", lambda: "dummy")

# 7. checkpoint stages (always False = never skip on checkpoint)
monkeypatch.setattr(bi, "has_stage", lambda h, s: False)

# 8. _persist_scraped_body — return body verbatim so flow continues
monkeypatch.setattr(bi, "_persist_scraped_body",
                    lambda conn, art_id, source, scraped: scraped.markdown)

# 9. ingest_article (success, wall_seconds, doc_confirmed)
ingest_mock = AsyncMock(return_value=tuple(ingest_outcome))
monkeypatch.setattr(bi, "ingest_article", ingest_mock)

# 10. ingest_wechat.get_rag — late import inside function
fake_rag = rag if rag is not None else mock_rag()
fake_iw = MagicMock()
fake_iw.get_rag = AsyncMock(return_value=fake_rag)
monkeypatch.setitem(sys.modules, "ingest_wechat", fake_iw)

# 11. logging.basicConfig no-op (caplog defence)
import logging as _logging
monkeypatch.setattr(_logging, "basicConfig", lambda *a, **kw: None)

# 12. SLEEP_BETWEEN_ARTICLES → 0
monkeypatch.setattr(bi, "SLEEP_BETWEEN_ARTICLES", 0)

return {
    "layer1": layer1_mock, "layer2": layer2_mock,
    "persist_layer1": p1, "persist_layer2": p2,
    "scrape": scrape_mock, "drain_vision": drain_mock,
    "ingest_article": ingest_mock, "rag": fake_rag,
}
```

4. `sample_kol_row(id: int = 1, image_count_row: int = 0, body: str | None = None, title: str = "KOL Article", url: str | None = None) -> tuple` — returns 8-tuple matching the L1899 outer-loop unpack: `(id, "wechat", title, url or f"https://mp.weixin.qq.com/s/test-{id}", "kol-acc-A", body, f"digest-{id}", image_count_row)`.

5. `sample_rss_row(id: int = 1, image_count_row: int = 0, body: str | None = None, title: str = "RSS Article", url: str | None = None) -> tuple` — same shape with "rss" + "rss-feed-A".

6. `seed_kol_article(conn, *, art_id, body=None, image_count=0, layer1_verdict=None, layer1_prompt_version=None) -> None` — INSERT helper for tests that need DB rows the production SELECT will pick up. Use parameterised SQL.

7. `seed_rss_article(conn, *, art_id, body=None, image_count=0, layer1_verdict=None, layer1_prompt_version=None) -> None` — mirror.

Module `__all__` list at bottom for clarity.

CRITICAL — verbatim ingestions schema check: after writing the file, verify by grep that `CHECK (source IN ('wechat', 'rss'))` AND `UNIQUE (article_id, source)` AND `skip_reason_version INTEGER NOT NULL DEFAULT 0` all appear in _ingest_fixtures.py — if any is missing, the production SELECT's NOT IN sub-query won't fire correctly and tests will pass for the wrong reason.

Style notes per project rules:

- PEP 8, type hints on all signatures (per ~/.claude/rules/python/coding-style.md)
- No `print()` — use `logging.getLogger(__name__)` if needed (per python/hooks.md)
- Frozen dataclasses where applicable (re-use ones from lib.article_filter; don't duplicate)
- snake_case naming (per CLAUDE.md Naming Patterns)
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "from tests.unit import _ingest_fixtures as f; assert callable(f.in_memory_db) and callable(f.mock_rag) and callable(f.patch_layer_funcs) and callable(f.sample_kol_row) and callable(f.sample_rss_row); c=f.in_memory_db(); cur=c.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"); tables=[r[0] for r in cur.fetchall()]; assert {'accounts','articles','classifications','ingestions','rss_articles','rss_feeds'}.issubset(set(tables)), tables; c.execute(\"INSERT INTO ingestions(article_id,source,status,skip_reason_version) VALUES (1,'wechat','skipped',1)\"); c.execute(\"INSERT INTO ingestions(article_id,source,status,skip_reason_version) VALUES (1,'rss','skipped',1)\"); print('FIXTURE OK')"</automated>
  </verify>
  <done>
    File tests/unit/_ingest_fixtures.py exists. The verify command prints `FIXTURE OK`. UNIQUE(article_id, source) allows the same article_id with different source values (proves dual-source UNIQUE is correct, not a single-column UNIQUE on article_id).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write 5 behavior-anchor tests + update CLAUDE.md principle #7</name>
  <files>tests/unit/test_ingest_from_db_orchestration.py, CLAUDE.md</files>
  <behavior>
Test file produces exactly 5 pytest items, all pass. Each test pins one historical failure mode:
- T1 [test_layer1_reject_writes_skipped_with_correct_source]: 1 KOL + 1 RSS rejected → ingestions has 2 rows, one per source, both with skip_reason_version=SKIP_REASON_VERSION_CURRENT
- T2 [test_drain_unpacks_8_col_tuple_with_image_count]: candidate with DB image_count=15 → spy on `_compute_article_budget_s` captures kwarg image_count=15 (not 0, not None)
- T3 [test_max_articles_cap_includes_queued_count]: 5 candidates, max_articles=3, LAYER2_BATCH_SIZE patched to 10 so queue does not auto-drain → ok+failed ingestions count never exceeds 3
- T4 [test_budget_exhausted_finally_drains_vision_and_finalizes]: budget=1s + monkeypatched time.time post-init → finally block runs: drain_vision called once, rag.finalize_storages called once
- T5 [test_image_count_refresh_after_persist]: candidate with body=NULL, image_count=0 → scrape returns ScrapeResult(images=[41 paths]) → spy on `_compute_article_budget_s` captures kwarg image_count=41 (NOT 0, NOT the stale DB 0)

CLAUDE.md gets new principle #7 inserted at the precise location.
  </behavior>
  <action>
**Step A: Write tests/unit/test_ingest_from_db_orchestration.py**

File header docstring (top, before imports):

```python
"""Behavior-anchor regression tests for batch_ingest_from_spider.ingest_from_db.

Pins five historical prod-only failure modes that survived green unit tests
and shipped to Hermes cron — surfacing only as ghost successes / silent
budget-floor / wrong source attribution. Mandated by CLAUDE.md HIGHEST
PRIORITY PRINCIPLE #7 (behavior-anchor harness for hot orchestration code).

Anchor IDs:
    T1 — 2026-05-08 dual-source skip_reason_version + source dispatch
    T2 — 2026-05-15 v1.0.z imc D2 single-missed queue.append → IndexError
         swallowed → 900s floor → ghost success
    T3 — 2026-05-11 quick-260511-mxc max_articles cap was processed-only;
         pre-fix up to LAYER2_BATCH_SIZE-1 leak past cap
    T4 — v1.0.x stable: finally block MUST drain vision + finalize storages
         even on early-exit (budget exhaustion path)
    T5 — 2026-05-16 quick-260516-htm image_count_row stale-0 + post-vision
         body markers stripped → 900s floor → outer-timeout ghost

Style mirror: tests/unit/test_max_articles_hard_cap.py (same monkeypatch
pattern, same DB_PATH override approach, same caplog basicConfig defence).
"""
from __future__ import annotations
```

Common imports + setup:

```python
import logging
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import pytest

import batch_ingest_from_spider as bi
from lib.article_filter import (
    FilterResult, PROMPT_VERSION_LAYER1, PROMPT_VERSION_LAYER2,
)
from lib.scraper import ScrapeResult

from tests.unit._ingest_fixtures import (
    in_memory_db, mock_rag, patch_layer_funcs,
    seed_kol_article, seed_rss_article,
)
```

Shared helper to redirect ingest_from_db's own sqlite3.connect to a shared in-memory DB:

```python
def _wire_db(monkeypatch, tmp_path: Path) -> sqlite3.Connection:
    """Create one in-memory DB connection; redirect both DB_PATH (.exists()
    gate) and the function's own sqlite3.connect() call to this connection.
    
    The function calls sqlite3.connect(str(DB_PATH)) once at L1578. We patch
    bi.sqlite3.connect to return our shared in-memory connection so all
    INSERT/SELECT in the function and our test assertions hit the same DB.
    """
    fake_db = tmp_path / "fake.db"
    fake_db.touch()
    monkeypatch.setattr(bi, "DB_PATH", fake_db)
    conn = in_memory_db()
    
    def _connect(*args, **kwargs):
        return conn
    
    monkeypatch.setattr(bi.sqlite3, "connect", _connect)
    return conn
```

**T1 — test_layer1_reject_writes_skipped_with_correct_source:**

Seed 1 KOL article (art_id=1) and 1 RSS article (art_id=1) — same id across sources is the deliberate stress test for the UNIQUE(article_id, source) two-row contract. Both with body present (so they're real candidates). Layer1 returns 2 reject FilterResults. Verify after `await bi.ingest_from_db(...)`:

- `SELECT article_id, source, status, skip_reason_version FROM ingestions ORDER BY source` returns exactly 2 rows
- One row has source='wechat', one has source='rss'
- Both rows have status='skipped' and skip_reason_version=`bi.SKIP_REASON_VERSION_CURRENT`
- `monkeypatch.chdir(tmp_path)` before the call so any data/ dir created by metrics writer lands under tmp.

**T2 — test_drain_unpacks_8_col_tuple_with_image_count:**

Seed 1 KOL article with body present + image_count=15 in DB + layer1_verdict='candidate' + layer1_prompt_version=PROMPT_VERSION_LAYER1 (so it skips Layer 1 reject branch and lands directly as candidate).

Spy on `_compute_article_budget_s`:

```python
captured: dict = {}
real_budget = bi._compute_article_budget_s
def spy_budget(content, *, url=None, image_count=None):
    captured["image_count"] = image_count
    captured["url"] = url
    return real_budget(content, url=url, image_count=image_count)
monkeypatch.setattr(bi, "_compute_article_budget_s", spy_budget)
```

layer1_results=[FilterResult("candidate", "ok", PROMPT_VERSION_LAYER1)], layer2_results=[FilterResult("ok", "depth=2", PROMPT_VERSION_LAYER2)], ingest_outcome=(True, 50.0, True).

Verify: `captured["image_count"] == 15`. The bug case would produce 0 (if row[7] read failed and fell back to default) or None (if kwarg dropped).

**T3 — test_max_articles_cap_includes_queued_count:**

Seed 5 KOL articles all with body present + layer1_verdict='candidate'. `monkeypatch.setattr(bi, "LAYER2_BATCH_SIZE", 10)` so queue does NOT auto-drain at 5. layer1_results = 5×candidate, layer2_full_body_score = passthrough returning 5×ok (will be called once at end-of-loop drain).

```python
async def fake_layer2(articles_with_body):
    return [FilterResult("ok", "depth=2", PROMPT_VERSION_LAYER2)
            for _ in articles_with_body]
monkeypatch.setattr(bi, "layer2_full_body_score", AsyncMock(side_effect=fake_layer2))
```

ingest_outcome=(True, 1.0, True). Call with `max_articles=3`.

Verify: `SELECT status, COUNT(*) FROM ingestions GROUP BY status` — `ok + failed <= 3`. The pre-fix bug would produce 4 or 5 (queue leak past cap).

**T4 — test_budget_exhausted_finally_drains_vision_and_finalizes:**

Seed 1 KOL candidate. layer1=candidate, layer2=ok, ingest_outcome=(True, 0.5, True). Pass `rag=mock_rag()` to patch_layer_funcs and capture handles dict.

Force budget exhaustion via stepping time.time:

```python
real_time = time.time
call_count = {"n": 0}
base = real_time()
def stepping_time():
    call_count["n"] += 1
    if call_count["n"] <= 2:
        return base
    return base + 10000.0
monkeypatch.setattr(bi.time, "time", stepping_time)
```

monkeypatch.chdir(tmp_path); (tmp_path / "data").mkdir(exist_ok=True).

Call `await bi.ingest_from_db(topic="ai", min_depth=2, dry_run=False, batch_timeout=1)`.

Assert (finally contract):

- `handles["drain_vision"].assert_called()` (called at least once)
- `handles["rag"].finalize_storages.assert_called_once()`
- (Tolerant) metrics file written under tmp_path/data/ OR finalize_storages call_count==1 (PROJECT_ROOT path may diverge).

**Fallback strategy if time.time stepping proves unreliable:** patch `_resolve_batch_timeout` to return 0 directly, so the very first `get_remaining_budget` call returns ≤ 0 — but verify the function still reaches the loop body at least once before exiting. If neither approach yields a stable test, accept a simpler form: drive ingest to completion successfully and assert the finally block STILL ran (drain_vision + finalize_storages both called) — this still tests the core regression net (finally must execute on every exit path).

**T5 — test_image_count_refresh_after_persist:**

Seed 1 KOL article with body=NULL + image_count=0 + layer1_verdict='candidate' + layer1_prompt_version=PROMPT_VERSION_LAYER1. Construct ScrapeResult with images=[41 paths]. layer2=ok, ingest_outcome=(True, 1.0, True).

Spy on `_compute_article_budget_s` capturing list of image_count kwargs across all calls:

```python
captured: dict = {}
real_budget = bi._compute_article_budget_s
def spy_budget(content, *, url=None, image_count=None):
    captured.setdefault("calls", []).append(image_count)
    return real_budget(content, url=url, image_count=image_count)
monkeypatch.setattr(bi, "_compute_article_budget_s", spy_budget)
```

monkeypatch.chdir(tmp_path); (tmp_path / "data").mkdir(exist_ok=True).

Call ingest_from_db. Verify: `captured["calls"][0] == 41` — the post-scrape refresh logic (L2031-L2032) replaced stale 0 with `len(scraped.images)=41`. The bug regression would yield 0.

**Step B: Update CLAUDE.md with HIGHEST PRIORITY PRINCIPLE #7**

Use the Edit tool to insert principle #7. Locate the line:
`Full discipline doc: \`kb/docs/10-DESIGN-DISCIPLINE.md\` Rule 3 (extended version with concrete curl + Playwright examples).`

Insert AFTER that line (with one blank line before the new "7. ..." heading and one blank line after the closing paragraph), and BEFORE `## Project Summary`. Use the exact text from `<claude_md_principle_7_text>` in the <context> section above — copy verbatim.

**Step C: Commit (atomic, ONE commit covering all three deliverables)**

After all three files are written + the verify command for Task 1 passes + the pytest run for Task 2 shows 5 passed, do a single explicit `git add` + `git commit` (NOT `git add -A` per CLAUDE.md feedback rule + `feedback_git_add_explicit_in_parallel_quicks.md`).

Files to add explicitly: `tests/unit/_ingest_fixtures.py`, `tests/unit/test_ingest_from_db_orchestration.py`, `CLAUDE.md`.

Commit message (HEREDOC):

```
feat(test/quick-260518): behavior-anchor harness for ingest_from_db()

Adds 5 regression tests pinning historical prod-only failure modes
(2026-05-08 dual-source / 2026-05-15 imc 8-col / 2026-05-11 max-articles
cap / v1.0.x finally / 2026-05-16 image_count refresh) + a reusable
fixture module + new CLAUDE.md HIGHEST PRIORITY PRINCIPLE #7.

Pure additive — no business code touched.

Verification: venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v → 5 passed
```

  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v 2>&1 | tail -25</automated>
  </verify>
  <done>
    Exactly 5 tests collected and all 5 pass (output ends with `5 passed`). CLAUDE.md contains the new principle #7 inserted between the Full discipline doc line and the `## Project Summary` heading. `git diff --stat HEAD~1` after commit shows exactly 3 files (2 new test files, CLAUDE.md modified). `git diff HEAD~1 -- batch_ingest_from_spider.py lib/article_filter.py lib/scraper.py ingest_wechat.py` is empty (zero business code touched).
  </done>
</task>

</tasks>

<verification>
After both tasks complete, run:
1. `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` — expects `5 passed`
2. `git show --stat HEAD` (after commit) — expects exactly 3 files: `tests/unit/_ingest_fixtures.py` (new), `tests/unit/test_ingest_from_db_orchestration.py` (new), `CLAUDE.md` (modified, ~+25 lines)
3. `git diff HEAD~1 -- batch_ingest_from_spider.py lib/article_filter.py lib/scraper.py ingest_wechat.py` — expects empty output (zero business-code changes)

Cross-cutting checks:

- Tests are deterministic — re-running 3× produces identical result
- No HTTP egress: tests pass with network disabled (mocks cover DeepSeek/Vertex/SiliconFlow/Apify)
- No real DEEPSEEK_API_KEY needed: `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` at top of both files handles Phase 5 cross-coupling
</verification>

<success_criteria>

- 5 tests pass with `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v`
- tests/unit/_ingest_fixtures.py is callable as a module (in_memory_db / mock_rag / patch_layer_funcs / sample_kol_row / sample_rss_row exported)
- CLAUDE.md HIGHEST PRIORITY PRINCIPLES section now ends with principle #7 (search "Behavior-Anchor Harness" returns one match in CLAUDE.md, sitting immediately before "## Project Summary")
- Single atomic commit landed (not amended), 3 files modified/added, no business code touched
- Verification command output captured in commit body's last line for traceability
</success_criteria>

<output>
This is a `/gsd:quick` task — no SUMMARY.md required by default. If the executor produces follow-up notes (e.g. T4 fallback strategy used because time.time monkeypatch unreliable), drop them inline in the commit message body, not a separate file.
</output>
