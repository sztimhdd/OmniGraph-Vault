---
phase: kb-2-topic-pillar-entity-pages
plan: 01
subsystem: tests
tags: [fixture, sqlite, test-infrastructure]
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/kb/test_export.py
  - tests/integration/kb/conftest.py
autonomous: true
requirements:
  - TOPIC-02
  - ENTITY-01
  - ENTITY-03
  - LINK-01
  - LINK-02

must_haves:
  truths:
    - "Fixture DB has classifications table populated for at least 5 topics × 3 articles each"
    - "Fixture DB has extracted_entities table populated with at least 6 entities crossing freq threshold (≥5 articles)"
    - "Fixture is reusable: kb-2 query function tests + integration tests both consume the same fixture"
    - "Fixture is read-only — md5 of fixture_db before and after queries is identical"
    - "Existing kb-1 test_export.py 6 tests STILL PASS unchanged — fixture extension is additive only"
  artifacts:
    - path: "tests/integration/kb/conftest.py"
      provides: "Shared `fixture_db` builder with classifications + extracted_entities"
      exports: ["fixture_db", "_BODY_*", "build_kb2_fixture_db"]
    - path: "tests/integration/kb/test_export.py"
      provides: "Existing kb-1 tests still passing against extended fixture"
      contains: "classifications + extracted_entities tables"
  key_links:
    - from: "tests/integration/kb/conftest.py::fixture_db"
      to: "kb/data/article_query.py (kb-2 query functions, plan 04)"
      via: "shared fixture passes Hermes-prod-shape rows"
      pattern: "classifications|extracted_entities"
---

<objective>
Extend the kb-1 SQLite test fixture (currently 3 articles, 1 RSS row, no classifications, no entities) to mirror Hermes prod shape: classifications populated for 5 topics × N articles each, extracted_entities populated with ≥6 entities crossing the ≥5-article frequency threshold. Move fixture builder to a shared `conftest.py` so both unit tests (plan 04 query functions) and integration tests (plan 09 end-to-end) consume the same data. EXTENDS the existing fixture additively — does NOT break the 6 kb-1 tests.

Purpose: Without this, plan 04 cannot TDD the new query functions (local dev DB has 0 classifications), and plan 09 cannot verify end-to-end SSG output. The fixture is the single ground-truth source for everything kb-2.

Output: `tests/integration/kb/conftest.py` (new) + extended fixture rows in `tests/integration/kb/test_export.py` (the 6 existing tests remain green).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-export-driver-PLAN.md
@tests/integration/kb/test_export.py
@CLAUDE.md

<interfaces>
Hermes prod schema (verified 2026-05-13 via SSH read-only):

```sql
CREATE TABLE classifications (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,                  -- FK to articles.id OR rss_articles.id
  source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
  topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
  depth_score INTEGER,                          -- 1-3, gate at >=2 in TOPIC-02
  classified_at TEXT,
  UNIQUE(article_id, source, topic)
);

CREATE TABLE extracted_entities (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
  name TEXT NOT NULL,                           -- raw entity string from LightRAG
  extracted_at TEXT
);

-- articles table extension (kb-2 reads these columns from kb-1 schema):
ALTER TABLE articles ADD COLUMN layer1_verdict TEXT;   -- 'candidate' | 'reject' | NULL
ALTER TABLE articles ADD COLUMN layer2_verdict TEXT;   -- 'ok' | 'fail' | NULL
ALTER TABLE rss_articles ADD COLUMN layer1_verdict TEXT;
ALTER TABLE rss_articles ADD COLUMN layer2_verdict TEXT;
```

Fixture target shape (per UI-SPEC §3.3.1 + ENTITY-01 threshold):
- 8 articles total (5 KOL + 3 RSS) — keeps existing 3 + adds 5 more for entity-frequency math
- classifications: 5 topics × 3-5 articles each = ~20 rows (some articles classified in multiple topics)
- extracted_entities: 6 entity names where each appears in ≥5 articles (crosses KB_ENTITY_MIN_FREQ=5 default), plus 2 noise entities at freq=2-3 (below threshold) for negative tests
- Articles have layer1_verdict='candidate' OR layer2_verdict='ok' to satisfy TOPIC-02 cohort gate
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create conftest.py with shared fixture_db extending classifications + extracted_entities + layer verdicts</name>
  <read_first>
    - tests/integration/kb/test_export.py (existing 6-test file — reuse `_BODY_WITH_LOCALHOST`, `_BODY_SHORT_FOR_OG_FALLBACK`, `_BODY_EN_PLAIN` constants; do NOT duplicate)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.1 (topic page) + §3.2 (entity page) + §3.3 (homepage sections) — drives "what fixture data must exist"
    - .planning/REQUIREMENTS-KB-v2.md TOPIC-02 (cohort gate) + ENTITY-01 (≥5 article threshold)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-export-driver-PLAN.md (kb-1's `fixture_db` pattern — extend, do not replace)
  </read_first>
  <files>tests/integration/kb/conftest.py, tests/integration/kb/test_export.py</files>
  <behavior>
    - Test 1: After conftest.py exists, `pytest tests/integration/kb/test_export.py -v` exits 0 with the original 6 tests still passing (additive change verification).
    - Test 2: New conftest.py exposes `fixture_db` pytest fixture (returns `Path` to a SQLite DB) which both kb-1 and kb-2 tests can consume via dependency injection.
    - Test 3: The fixture DB contains 8 articles total (5 in `articles`, 3 in `rss_articles`).
    - Test 4: The fixture DB contains exactly 5 topics in `classifications.topic` distinct values: Agent, CV, LLM, NLP, RAG.
    - Test 5: The fixture DB contains at least 6 entities in `extracted_entities` where each name appears in ≥5 distinct (article_id, source) tuples — these are the "above threshold" entities.
    - Test 6: At least 2 entities exist below threshold (freq 2-3) for negative-test coverage.
    - Test 7: Every article row has either `layer1_verdict='candidate'` OR `layer2_verdict='ok'` set — so they pass TOPIC-02 cohort gate when `depth_score>=2`.
  </behavior>
  <action>
    Per `python-patterns` rule (PEP 8 + type hints + dataclass-like constants), create `tests/integration/kb/conftest.py` and refactor `test_export.py` to consume from conftest.

    **Step 1 — Create `tests/integration/kb/conftest.py`** containing:

    ```python
    """Shared fixtures for kb integration tests.

    `fixture_db` builds a SQLite DB matching Hermes prod schema (kb-1 articles +
    rss_articles + lang column + kb-2 classifications + extracted_entities tables)
    populated with kb-2-shape data: 8 articles, 5 topics × 3-5 articles, 6 entities
    above ENTITY-01 threshold (>=5 articles), 2 entities below threshold for
    negative-test coverage.

    Scope: this fixture is consumed by both unit tests (kb-2 query functions in
    plan 04) and integration tests (existing kb-1 + new kb-2 SSG end-to-end in
    plan 09).
    """
    from __future__ import annotations

    import sqlite3
    from pathlib import Path

    import pytest

    # ---- Body strings — reused by kb-1 + kb-2 tests ----

    _BODY_WITH_LOCALHOST = (
        "# Test Article One\n\n"
        "Some leading paragraph with enough words to be a reasonable description "
        "for OG meta extraction so the fallback path does not trigger.\n\n"
        "![local image](http://localhost:8765/abc/img.png)\n\n"
        "More body text after the image with additional content to ensure the "
        "200-character description has plenty to work with."
    )
    _BODY_SHORT_FOR_OG_FALLBACK = "![](http://localhost:8765/img.png)"
    _BODY_EN_PLAIN = (
        "# English Article Three\n\n"
        "This is an English-language article about agent technology and tooling. "
        "It contains a meaningful chunk of prose suitable for og:description "
        "extraction in the SSG export pipeline tests."
    )
    _BODY_GENERIC_ZH = "# 中文文章\n\n人工智能和大语言模型相关讨论。"
    _BODY_GENERIC_EN = "# English Generic\n\nDiscussion of LangChain and OpenAI tooling for agents."


    def build_kb2_fixture_db(db_path: Path) -> Path:
        """Build SQLite fixture matching Hermes prod schema with kb-2 data."""
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE articles (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    body TEXT,
                    content_hash TEXT,
                    lang TEXT,
                    update_time INTEGER,
                    layer1_verdict TEXT,
                    layer2_verdict TEXT
                );
                CREATE TABLE rss_articles (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    body TEXT,
                    content_hash TEXT,
                    lang TEXT,
                    published_at TEXT,
                    fetched_at TEXT,
                    layer1_verdict TEXT,
                    layer2_verdict TEXT
                );
                CREATE TABLE classifications (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
                    topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
                    depth_score INTEGER,
                    classified_at TEXT,
                    UNIQUE(article_id, source, topic)
                );
                CREATE TABLE extracted_entities (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
                    name TEXT NOT NULL,
                    extracted_at TEXT
                );
                """
            )

            # 5 KOL articles + 3 RSS = 8 total
            kol_rows = [
                # (id, title, url, body, content_hash, lang, update_time, l1, l2)
                (1, "测试文章一", "https://mp.weixin.qq.com/s/test1", _BODY_WITH_LOCALHOST,
                 "abc1234567", "zh-CN", 1778270400, "candidate", "ok"),
                (2, "Image Only Post Title For Fallback", "https://mp.weixin.qq.com/s/test2",
                 _BODY_SHORT_FOR_OG_FALLBACK, None, "en", 1778180400, "candidate", None),
                (3, "Agent 框架对比", "https://mp.weixin.qq.com/s/test3", _BODY_GENERIC_ZH,
                 "kol3000003a", "zh-CN", 1778090400, "candidate", "ok"),
                (4, "RAG 检索增强生成实践", "https://mp.weixin.qq.com/s/test4", _BODY_GENERIC_ZH,
                 "kol4000004b", "zh-CN", 1778000400, "candidate", "ok"),
                (5, "LLM Reasoning Patterns", "https://mp.weixin.qq.com/s/test5", _BODY_GENERIC_EN,
                 "kol5000005c", "en", 1777910400, "candidate", "ok"),
            ]
            conn.executemany(
                "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,layer1_verdict,layer2_verdict) "
                "VALUES (?,?,?,?,?,?,?,?,?)", kol_rows,
            )

            rss_rows = [
                (10, "English Article Three", "https://example.com/article-three", _BODY_EN_PLAIN,
                 "deadbeefcafebabe1234567890abcdef", "en", "2026-05-10 08:00:00", "2026-05-10 08:01:00",
                 "candidate", "ok"),
                (11, "NLP Tooling Roundup", "https://example.com/nlp-roundup", _BODY_GENERIC_EN,
                 "11111111111111111111111111111111", "en", "2026-05-09 08:00:00", "2026-05-09 08:01:00",
                 "candidate", "ok"),
                (12, "CV Multimodal Vision", "https://example.com/cv-mm", _BODY_GENERIC_EN,
                 "22222222222222222222222222222222", "en", "2026-05-08 08:00:00", "2026-05-08 08:01:00",
                 "candidate", "ok"),
            ]
            conn.executemany(
                "INSERT INTO rss_articles (id,title,url,body,content_hash,lang,published_at,fetched_at,layer1_verdict,layer2_verdict) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", rss_rows,
            )

            # Classifications — 5 topics, distribute so each topic has 3-5 articles
            # depth_score >= 2 throughout (above TOPIC-02 cohort gate)
            classifications_rows = [
                # Agent: articles 1, 3, 5 (KOL) + 10, 11 (RSS) = 5
                (1, "wechat", "Agent", 3), (3, "wechat", "Agent", 2), (5, "wechat", "Agent", 2),
                (10, "rss", "Agent", 2), (11, "rss", "Agent", 2),
                # LLM: articles 1, 5 (KOL) + 10 (RSS) = 3
                (1, "wechat", "LLM", 2), (5, "wechat", "LLM", 3), (10, "rss", "LLM", 2),
                # RAG: articles 1, 4 (KOL) + 10 (RSS) = 3
                (1, "wechat", "RAG", 2), (4, "wechat", "RAG", 3), (10, "rss", "RAG", 2),
                # NLP: articles 2, 5 (KOL) + 11 (RSS) = 3
                (2, "wechat", "NLP", 2), (5, "wechat", "NLP", 2), (11, "rss", "NLP", 3),
                # CV: articles 2 (KOL) + 12 (RSS) = 2  (intentionally lower-density)
                (2, "wechat", "CV", 2), (12, "rss", "CV", 3),
            ]
            for article_id, source, topic, depth in classifications_rows:
                conn.execute(
                    "INSERT INTO classifications (article_id,source,topic,depth_score,classified_at) "
                    "VALUES (?,?,?,?,?)", (article_id, source, topic, depth, "2026-05-12 10:00:00"),
                )

            # Extracted entities — 6 above threshold (>=5 articles each), 2 below (2-3 articles)
            # Above-threshold entities (each appears in 5+ articles):
            above_freq_entities = {
                "OpenAI": [(1,"wechat"),(3,"wechat"),(5,"wechat"),(10,"rss"),(11,"rss")],
                "LangChain": [(1,"wechat"),(3,"wechat"),(4,"wechat"),(10,"rss"),(11,"rss")],
                "LightRAG": [(1,"wechat"),(4,"wechat"),(5,"wechat"),(10,"rss"),(11,"rss")],
                "Anthropic": [(2,"wechat"),(3,"wechat"),(5,"wechat"),(10,"rss"),(12,"rss")],
                "AutoGen": [(1,"wechat"),(3,"wechat"),(5,"wechat"),(10,"rss"),(11,"rss")],
                "MCP": [(1,"wechat"),(2,"wechat"),(4,"wechat"),(10,"rss"),(12,"rss")],
            }
            for name, refs in above_freq_entities.items():
                for article_id, source in refs:
                    conn.execute(
                        "INSERT INTO extracted_entities (article_id,source,name,extracted_at) "
                        "VALUES (?,?,?,?)", (article_id, source, name, "2026-05-12 10:00:00"),
                    )

            # Below-threshold (negative-test coverage — must NOT appear in entity pages):
            below_freq_entities = {
                "ObscureLib": [(1,"wechat"),(2,"wechat")],   # 2
                "OneOffMention": [(3,"wechat"),(10,"rss"),(11,"rss")],  # 3
            }
            for name, refs in below_freq_entities.items():
                for article_id, source in refs:
                    conn.execute(
                        "INSERT INTO extracted_entities (article_id,source,name,extracted_at) "
                        "VALUES (?,?,?,?)", (article_id, source, name, "2026-05-12 10:00:00"),
                    )

            conn.commit()
        finally:
            conn.close()
        return db_path


    @pytest.fixture
    def fixture_db(tmp_path: Path) -> Path:
        """Hermes-prod-shape SQLite DB with 8 articles + classifications + entities."""
        return build_kb2_fixture_db(tmp_path / "fixture.db")
    ```

    **Step 2 — Refactor `tests/integration/kb/test_export.py`:**

    Remove the local `fixture_db` definition and the `_BODY_*` constants (now in conftest.py). The 6 existing tests automatically pick up the new shared fixture. Verify by running pytest — all 6 must still pass; the test fixture now has 8 articles instead of 3, so update the `len(detail_files) == 3` assertion to `len(detail_files) == 8`, and the `sitemap.count("<url>") == 6` assertion to `== 11` (3 index + 8 articles), and the `len(url_index) == 3` assertion to `== 8`. These are mechanical bumps reflecting the larger fixture.

    Use surgical-changes principle: only the assertion numbers + the import-from-conftest change. Do NOT modify test logic.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/integration/kb/test_export.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/integration/kb/conftest.py`
    - `grep -q "build_kb2_fixture_db" tests/integration/kb/conftest.py`
    - `grep -q "classifications" tests/integration/kb/conftest.py`
    - `grep -q "extracted_entities" tests/integration/kb/conftest.py`
    - `grep -q "layer1_verdict" tests/integration/kb/conftest.py`
    - `grep -q "OpenAI" tests/integration/kb/conftest.py` (one of the 6 above-threshold entities)
    - `grep -c "above_freq_entities" tests/integration/kb/conftest.py` returns ≥1
    - `pytest tests/integration/kb/test_export.py -v` exits 0 with 6 tests passing (kb-1 baseline preserved — additive only)
    - `python -c "from tests.integration.kb.conftest import build_kb2_fixture_db; print('OK')"` exits 0 — module imports without errors
    - Negative: `grep -c "_BODY_WITH_LOCALHOST = " tests/integration/kb/test_export.py` returns 0 — body constants moved to conftest, not duplicated
  </acceptance_criteria>
  <done>conftest.py shared fixture extended with classifications (5 topics × 3-5 articles) + extracted_entities (6 above + 2 below threshold) + layer verdicts; kb-1 6 tests still pass.</done>
</task>

</tasks>

<verification>
- All kb-1 integration tests still pass after fixture extension
- New conftest.py exposes `fixture_db` pytest fixture and `build_kb2_fixture_db` builder for direct calls (used by plan 04 unit tests)
- Fixture data matches Hermes prod shape: 5 topics, 6 entities ≥ threshold, 2 entities < threshold, all articles pass TOPIC-02 cohort gate
</verification>

<success_criteria>
- TOPIC-02 cohort filter testable: fixture has rows where `depth_score >= 2 AND (layer1='candidate' OR layer2='ok')`
- ENTITY-01 threshold testable: 6 entities above 5-article threshold, 2 below
- ENTITY-03 article-list testable: each above-threshold entity has ≥5 distinct article references
- LINK-01 + LINK-02 testable: classifications + extracted_entities both present per-article for related-link queries
- 1 task, 1 file created + 1 file extended; ~50% context budget; pure test infra (no skill invocation needed)
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-01-SUMMARY.md` documenting:
- Fixture row counts (5 KOL + 3 RSS = 8 articles, 16 classifications, 6 above + 2 below threshold = 22+ entity rows)
- kb-1 6-test pass confirmation (no regression)
- Foundation for plan 04 (query functions) + plan 09 (integration test)
</output>
