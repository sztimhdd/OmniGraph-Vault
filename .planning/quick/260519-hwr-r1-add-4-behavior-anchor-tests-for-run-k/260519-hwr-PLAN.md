---
quick_id: 260519-hwr
description: R1 — add 4 behavior-anchor tests for run() KOL orchestrator
---

# Plan: R1 behavior-anchor harness for `run()`

Companion to T1–T5 in `tests/unit/test_ingest_from_db_orchestration.py`.
Implements CLAUDE.md HIGHEST PRIORITY PRINCIPLE #7 for the sister
orchestrator at `batch_ingest_from_spider.py:793-1014`.

## Tasks

### Task 1 — create `tests/unit/test_run_kol_scan_orchestration.py`

**Files**: `tests/unit/test_run_kol_scan_orchestration.py` (new)

**Action**:
- Add four `@pytest.mark.asyncio` tests R1, R2, R3, R4
- Reuse `mock_rag` from `tests/unit/_ingest_fixtures.py`
- Patch boundary (per test, via `monkeypatch`):
  - `bi.kol_config` → `SimpleNamespace(FAKEIDS=..., TOKEN="t", COOKIE="c")`
  - `bi.list_articles` → `MagicMock(return_value=[...])` (sync — `list_articles_with_digest` aliased)
  - `bi.ingest_article` → `AsyncMock`
  - `bi.has_stage`, `bi.get_article_hash` → simple lambdas
  - `bi._load_hermes_env` → no-op
  - `bi.PROJECT_ROOT` → `tmp_path` (so summary + metrics writes land under tmp_path)
  - `bi.SLEEP_BETWEEN_ARTICLES`, `bi.RATE_LIMIT_SLEEP_ACCOUNTS` → 0
  - `logging.basicConfig` → no-op (caplog defence)
  - `sys.modules["ingest_wechat"]` → MagicMock with `get_rag = AsyncMock(...)`
- Pin behavior on observable post-conditions (file presence/contents,
  spy call counts) — never on internal call shape

**Verify**:
```
venv/Scripts/python.exe -m pytest tests/unit/test_run_kol_scan_orchestration.py -v
```
Must show `4 passed`.

**Done when**:
- File exists at the path above
- All 4 tests green
- Pre-existing T1–T5 still 5 passed (regression check)
