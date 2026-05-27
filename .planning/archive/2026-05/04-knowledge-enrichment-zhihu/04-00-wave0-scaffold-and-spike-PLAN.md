---
phase: 04-knowledge-enrichment-zhihu
plan: 00
type: execute
wave: 0
depends_on: []
files_modified:
  - pyproject.toml
  - requirements.txt
  - tests/conftest.py
  - tests/unit/__init__.py
  - tests/integration/__init__.py
  - tests/fixtures/sample_wechat_article.md
  - tests/fixtures/sample_haowen_response.json
  - tests/fixtures/sample_zhihu_page.html
  - tests/fixtures/golden/.gitkeep
  - tests/fixtures/golden_articles.txt
  - tests/unit/test_migrations.py
  - batch_scan_kol.py
  - scripts/phase0_delete_spike.py
  - deploy.sh
autonomous: true
requirements: [D-04, D-05, D-07, D-10, D-14, D-16]
must_haves:
  truths:
    - "pytest can discover and run tests from tests/ directory"
    - "SQLite init_db is idempotent: running twice adds no duplicate columns"
    - "articles.enriched column exists with default 0 after init_db"
    - "ingestions.enrichment_id column exists after init_db"
    - "articles.content_hash column is declared in CREATE TABLE (drift fix)"
    - "Phase-0 LightRAG delete+re-ainsert spike produces a machine-readable report"
    - "deploy.sh triggers a git pull on the remote host"
    - "Golden-file fixtures contain 2-3 complete WeChat article snapshots"
  artifacts:
    - path: "pyproject.toml"
      provides: "pytest configuration with asyncio_mode=auto and testpaths"
      contains: "[tool.pytest.ini_options]"
    - path: "tests/conftest.py"
      provides: "Shared fixtures for mock Gemini, mock LightRAG, tmp BASE_DIR"
      min_lines: 40
    - path: "scripts/phase0_delete_spike.py"
      provides: "Runnable LightRAG delete+re-ainsert validation spike"
      min_lines: 60
    - path: "deploy.sh"
      provides: "One-line git-push-pull helper reading host from env"
      contains: "git pull"
    - path: "tests/unit/test_migrations.py"
      provides: "Idempotency tests for SQLite migrations"
  key_links:
    - from: "batch_scan_kol.py init_db"
      to: "articles.enriched and ingestions.enrichment_id columns"
      via: "_ensure_column PRAGMA-guarded ALTER"
      pattern: "_ensure_column\\(conn, \"articles\", \"enriched\""
    - from: "scripts/phase0_delete_spike.py"
      to: ".planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md"
      via: "file write with status line"
      pattern: "status: (success|fail)"
---

<objective>
Wave 0 scaffold: stand up pytest, migrate the SQLite schema, run the mandatory
LightRAG delete-and-reinsert spike (D-14), add the git-push-pull dev-loop
helper, and capture golden-file fixtures for the image-pipeline regression gate.

Purpose: Every downstream plan depends on this infrastructure. The spike is a
hard gate — if `adelete_by_doc_id` does not produce clean orphan cleanup on a
real article, Phase 4 cannot ship D-10/re-enrichment.

Output: Working pytest config, idempotent migration, executable spike script
with a success/fail report, deploy helper, fixtures directory.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-VALIDATION.md
@CLAUDE.md
@config.py
@batch_scan_kol.py
@requirements.txt

<interfaces>
Extracted from venv/Lib/site-packages/lightrag/lightrag.py (remote version 1.4.15):

```python
# lightrag.py:3223
async def adelete_by_doc_id(doc_id: str, delete_llm_cache: bool = False) -> DeletionResult:
    """Delete document, chunks, graph elements. Orphan cleanup is LLM-cache-dependent."""

# lightrag.py:1237
async def ainsert(
    input: str | list[str],
    ids: str | list[str] | None = None,
    file_paths: str | list[str] | None = None,
    track_id: str | None = None,
) -> str:
    """Insert doc(s). When ids is provided, adelete_by_doc_id can target exactly this doc."""

@dataclass
class DeletionResult:
    status: Literal["success", "not_found", "not_allowed", "fail"]
    doc_id: str
    message: str
    status_code: int  # 200 / 404 / 403 / 500
    file_path: str | None
```

From batch_scan_kol.py:87-115 (CREATE TABLE source of truth):

```sql
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    digest TEXT,
    update_time INTEGER,
    scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
    -- content_hash TEXT   (MISSING — live DB has it, CREATE does not)
);

CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id)
);
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0.1: pytest scaffolding</name>
  <files>pyproject.toml, requirements.txt, tests/conftest.py, tests/unit/__init__.py, tests/integration/__init__.py, tests/fixtures/sample_wechat_article.md, tests/fixtures/sample_haowen_response.json, tests/fixtures/sample_zhihu_page.html, tests/fixtures/golden/.gitkeep</files>
  <read_first>
    - requirements.txt (to see current pinned deps before adding)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-VALIDATION.md (Wave 0 Requirements section — exact fixture list)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md (§10 Validation Architecture — framework choice + fixture list)
    - config.py (to understand BASE_DIR pattern — conftest fixtures will mock it)
  </read_first>
  <action>
    Create pyproject.toml at repo root with exactly this content (project may already have pyproject.toml — if it exists, MERGE the `[tool.pytest.ini_options]` block into it rather than overwriting):

    ```toml
    [tool.pytest.ini_options]
    testpaths = ["tests"]
    asyncio_mode = "auto"
    markers = [
        "unit: unit-tier tests (fast, mocked, local-runnable)",
        "integration: integration-tier tests (remote-only, live deps)",
        "remote: tests that must run on the remote WSL host (see private memory for connection)",
    ]
    ```

    Append to requirements.txt (only if not already present — grep first):
    ```
    pytest>=7.4
    pytest-asyncio>=0.23
    pytest-mock>=3.12
    ```

    Create tests/conftest.py with shared fixtures:
    ```python
    """Shared pytest fixtures for Phase 4 enrichment tests."""
    from __future__ import annotations
    import json
    from pathlib import Path
    from unittest.mock import MagicMock
    import pytest


    @pytest.fixture
    def tmp_base_dir(tmp_path: Path) -> Path:
        """A temporary directory that mirrors ~/.hermes/omonigraph-vault/."""
        base = tmp_path / "omonigraph-vault"
        (base / "lightrag_storage").mkdir(parents=True)
        (base / "images").mkdir()
        (base / "enrichment").mkdir()
        (base / "entity_buffer").mkdir()
        return base


    @pytest.fixture
    def fixtures_dir() -> Path:
        return Path(__file__).parent / "fixtures"


    @pytest.fixture
    def mock_gemini_client(mocker):
        """Mock google.genai.Client — returns a client whose generate_content returns stub text."""
        client = MagicMock()
        response = MagicMock()
        response.text = "stub gemini response"
        response.candidates = [MagicMock(grounding_metadata=MagicMock(grounding_chunks=[]))]
        client.models.generate_content.return_value = response
        return client


    @pytest.fixture
    def mock_lightrag(mocker):
        """Mock LightRAG instance with async ainsert / adelete_by_doc_id."""
        rag = MagicMock()
        async def _ainsert(*a, **kw): return "stub-track-id"
        async def _adelete(*a, **kw):
            r = MagicMock()
            r.status = "success"
            r.status_code = 200
            return r
        rag.ainsert = _ainsert
        rag.adelete_by_doc_id = _adelete
        return rag


    @pytest.fixture
    def mock_requests_get(mocker):
        """Mock requests.get for image download tests — returns 200 with bytes body."""
        m = mocker.patch("requests.get")
        m.return_value.status_code = 200
        m.return_value.content = b"\xff\xd8\xff\xe0FAKE_JPEG_BYTES"
        return m
    ```

    Create empty `tests/unit/__init__.py` and `tests/integration/__init__.py`.

    Create `tests/fixtures/sample_wechat_article.md` with a ~2500-char plausible Chinese AI/Agent article (can be lorem-ipsum style — just needs to exceed 2000 chars and have a title/body structure). Use this text:

    ```markdown
    # 大模型 Agent 在企业知识管理中的工程化实践

    URL: https://mp.weixin.qq.com/s/sample-fixture
    Time: 2024-04-01 12:00:00

    近年来，大语言模型（LLM）Agent 在企业内部知识检索与决策辅助场景中...

    [CONTINUE — write approximately 2500-3000 characters of plausible Chinese
    content about AI Agents, LightRAG, knowledge graphs, vector retrieval,
    multi-hop reasoning, RAG vs fine-tuning tradeoffs. Any prose that exceeds
    2000 chars is acceptable — this is a fixture for length-threshold tests.]
    ```

    Create `tests/fixtures/sample_haowen_response.json`:
    ```json
    {
      "question": "How does LightRAG handle multi-hop entity resolution?",
      "summary": "LightRAG combines local and global retrieval modes...",
      "best_source_url": "https://zhuanlan.zhihu.com/p/123456789",
      "timestamp": "2026-04-27T10:00:00Z"
    }
    ```

    Create `tests/fixtures/sample_zhihu_page.html` — save a minimal HTML page with a Zhihu-like structure: `<div class="RichContent-inner">` containing a paragraph and two `<img>` tags (one width=200, one width=50 for filter test). ~30 lines is enough.

    Create empty `tests/fixtures/golden/.gitkeep` to track the directory (actual golden snapshots are captured in Task 0.5).
  </action>
  <verify>
    <automated>pytest --collect-only -q 2>&1 | grep -E "tests/unit|tests/integration|no tests collected"</automated>
  </verify>
  <acceptance_criteria>
    - File `pyproject.toml` exists at repo root and `grep -q "\[tool.pytest.ini_options\]" pyproject.toml` succeeds
    - `grep -q "asyncio_mode = \"auto\"" pyproject.toml` succeeds
    - `grep -q "^pytest" requirements.txt` succeeds
    - File `tests/conftest.py` exists and contains `def tmp_base_dir` and `def mock_lightrag`
    - Files `tests/unit/__init__.py` and `tests/integration/__init__.py` exist (may be empty)
    - `wc -c tests/fixtures/sample_wechat_article.md` reports >= 2000
    - `python -c "import json; json.load(open('tests/fixtures/sample_haowen_response.json'))"` exits 0
    - `test -d tests/fixtures/golden` returns 0
    - `pytest --collect-only -q` exits 0 (even with zero tests discovered)
  </acceptance_criteria>
  <done>pytest framework installed and discoverable; all fixture files present</done>
</task>

<task type="auto">
  <name>Task 0.2: SQLite migration (drift fix + enrichment columns)</name>
  <files>batch_scan_kol.py, tests/unit/test_migrations.py</files>
  <read_first>
    - batch_scan_kol.py lines 71-140 (current init_db + CREATE TABLE statements)
    - ingest_wechat.py line 718 (the UPDATE articles SET content_hash query that proves the column is used)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §8 (exact migration pattern)
  </read_first>
  <action>
    Modify `batch_scan_kol.py` `init_db` function (currently at lines 71-140):

    (A) In the `CREATE TABLE IF NOT EXISTS articles` block, add `content_hash TEXT` and `enriched INTEGER DEFAULT 0` columns. The column declarations go AFTER `scanned_at TEXT DEFAULT (datetime('now', 'localtime'))` and BEFORE the closing `)`. Final columns list for articles: `id, account_id, title, url, digest, update_time, scanned_at, content_hash, enriched`.

    (B) In the `CREATE TABLE IF NOT EXISTS ingestions` block, add `enrichment_id TEXT` column. Goes AFTER `ingested_at` and BEFORE `UNIQUE(article_id)`.

    (C) After `conn.commit()` on line 139 (after the existing executescript), INSERT these lines BEFORE the existing `conn.commit()`:

    ```python
        # Idempotent runtime migrations. SQLite ALTER TABLE ADD COLUMN is only safe
        # with an explicit PRAGMA table_info guard.
        def _ensure_column(c, table: str, column: str, type_def: str) -> None:
            cols = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")

        _ensure_column(conn, "articles", "content_hash", "TEXT")
        _ensure_column(conn, "articles", "enriched", "INTEGER DEFAULT 0")
        _ensure_column(conn, "ingestions", "enrichment_id", "TEXT")
    ```

    Make sure `_ensure_column` is defined INSIDE `init_db` (nested function) so it has access to `conn`. The final `conn.commit()` should come AFTER all three `_ensure_column` calls.

    Create `tests/unit/test_migrations.py`:

    ```python
    """Phase 4 SQLite migration tests — D-07 enriched state, enrichment_id, content_hash drift."""
    from __future__ import annotations
    import sqlite3
    from pathlib import Path
    import pytest
    from batch_scan_kol import init_db


    @pytest.mark.unit
    def test_init_db_creates_enriched_column(tmp_path: Path):
        db = tmp_path / "k.db"
        conn = init_db(db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        assert "enriched" in cols
        assert "content_hash" in cols
        conn.close()


    @pytest.mark.unit
    def test_init_db_creates_enrichment_id_column(tmp_path: Path):
        db = tmp_path / "k.db"
        conn = init_db(db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(ingestions)")}
        assert "enrichment_id" in cols
        conn.close()


    @pytest.mark.unit
    def test_init_db_is_idempotent(tmp_path: Path):
        db = tmp_path / "k.db"
        conn1 = init_db(db); conn1.close()
        # Second call must not raise (ALTER TABLE on existing column would error)
        conn2 = init_db(db)
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(articles)")}
        assert "enriched" in cols and "content_hash" in cols
        conn2.close()


    @pytest.mark.unit
    def test_enriched_default_is_zero(tmp_path: Path):
        db = tmp_path / "k.db"
        conn = init_db(db)
        conn.execute("INSERT INTO accounts (name, fakeid) VALUES ('X', 'fx1')")
        conn.execute(
            "INSERT INTO articles (account_id, title, url) VALUES (1, 't', 'http://example.com/1')"
        )
        row = conn.execute("SELECT enriched FROM articles WHERE url='http://example.com/1'").fetchone()
        assert row[0] == 0
        conn.close()
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_migrations.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "enriched INTEGER DEFAULT 0" batch_scan_kol.py` succeeds
    - `grep -q "content_hash TEXT" batch_scan_kol.py` succeeds (in CREATE TABLE)
    - `grep -q "enrichment_id TEXT" batch_scan_kol.py` succeeds
    - `grep -q "_ensure_column" batch_scan_kol.py` succeeds
    - `pytest tests/unit/test_migrations.py -x -v` exits 0
    - All 4 tests pass (enriched column, enrichment_id column, idempotency, default value)
  </acceptance_criteria>
  <done>Migration is in-place, idempotent, and has 4 passing tests</done>
</task>

<task type="auto">
  <name>Task 0.3: LightRAG delete+re-ainsert spike (D-14)</name>
  <files>scripts/phase0_delete_spike.py</files>
  <read_first>
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §3 (LightRAG Delete API + validation checklist)
    - ingest_wechat.py lines 110-125 (get_rag helper pattern — embedding_func, llm_model_func)
    - config.py (BASE_DIR, RAG_WORKING_DIR pattern)
  </read_first>
  <action>
    Create `scripts/phase0_delete_spike.py` — a standalone runnable Python script that validates LightRAG delete+re-ainsert behavior on a real article, then writes a machine-readable status report.

    The script must:
    1. Use asyncio (LightRAG APIs are all async).
    2. Reuse `get_rag()` from `ingest_wechat.py` (import it) OR reconstruct an equivalent LightRAG instance if the import pulls too many transitive deps.
    3. Execute this sequence:
       - Read a hard-coded test document (use `tests/fixtures/sample_wechat_article.md`).
       - Call `rag.ainsert(text, ids=["phase0_spike_test_doc"], file_paths=["spike:phase0"])`.
       - Query for entities using `rag.aquery("list entities", param=QueryParam(mode="local", top_k=10))` (record entity count via logging).
       - Call `rag.adelete_by_doc_id("phase0_spike_test_doc", delete_llm_cache=False)` and capture the returned `DeletionResult`.
       - Re-query entities; record delta.
       - Re-insert the same document with the same `ids=["phase0_spike_test_doc"]`; capture success/failure.
    4. Write a Markdown report to `.planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md` with this exact structure:

    ```markdown
    # Phase 0 LightRAG Delete+Reinsert Spike — Report

    **Run at:** <ISO timestamp>
    **Host:** <`os.uname()` or `platform.node()`>
    **LightRAG version:** <`lightrag.__version__`>

    status: <success|fail>

    ## Steps

    1. Initial ainsert with ids=[phase0_spike_test_doc]: <ok|err: ...>
    2. Pre-delete entity count: <N>
    3. adelete_by_doc_id result: status=<...>, status_code=<...>, message="<...>"
    4. Post-delete entity count: <N>
    5. Re-ainsert with same ids: <ok|err: ...>
    6. Post-reinsert entity count: <N>

    ## Observations

    - Orphan entity cleanup: <clean|leaked: N entities remained>
    - Re-insert idempotency: <stable|produced duplicates>
    - Notes: <any surprises, edge cases, or library warnings>
    ```

    The final `status:` line MUST be `success` only if: (a) initial ainsert succeeded, (b) `DeletionResult.status == "success"`, (c) re-ainsert succeeded. Otherwise `fail`.

    Script exits 0 on success, 1 on fail (so Wave 1 can gate on this via `ssh remote 'python scripts/phase0_delete_spike.py' && echo go`).

    Use `argparse` to allow `--skip-if-exists` flag that short-circuits and returns 0 if the report already exists and its status is success (useful for re-running Wave 0 on remote without re-spiking).

    Keep the script under ~120 lines. Put detailed docstring at top explaining: (1) this is a ONE-TIME Phase-0 gate, (2) it must run on remote (D-04/D-06), (3) its report gates Wave 1 execution.
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('scripts/phase0_delete_spike.py').read()); print('syntax ok')"</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/phase0_delete_spike.py` exists and parses as valid Python
    - `grep -q "adelete_by_doc_id" scripts/phase0_delete_spike.py` succeeds
    - `grep -q "phase0_spike_test_doc" scripts/phase0_delete_spike.py` succeeds
    - `grep -q "phase0_spike_report.md" scripts/phase0_delete_spike.py` succeeds
    - `grep -q "status: success" scripts/phase0_delete_spike.py` OR `grep -q '"success"' scripts/phase0_delete_spike.py` succeeds (status string literal)
    - `grep -q "argparse" scripts/phase0_delete_spike.py` succeeds
    - Script exit-code contract verified by reading the script's main entry (asserts `sys.exit(0|1)` is called)
    - NOTE: Actual spike execution is a MANUAL step — run `ssh -p $SSH_PORT $SSH_USER@$SSH_HOST 'cd ~/OmniGraph-Vault && source venv/bin/activate && python scripts/phase0_delete_spike.py'` AFTER this task is committed. Archive the report file once produced.
  </acceptance_criteria>
  <done>Spike script exists, parses, has correct exit-code contract; report is produced by a downstream manual remote run (not blocking this task)</done>
</task>

<task type="auto">
  <name>Task 0.4: deploy.sh helper + golden-file fixture capture stub</name>
  <files>deploy.sh, tests/fixtures/golden_articles.txt</files>
  <read_first>
    - CLAUDE.md (Remote Hermes Deployment section — SSH reconcile pattern, git push/pull)
    - skills/omnigraph_ingest/scripts/ingest.sh (shell pattern reference — set -euo pipefail, env sourcing)
  </read_first>
  <action>
    Create `deploy.sh` at repo root — a single-purpose shell script that syncs Windows-local commits to the remote WSL host via git push + remote git pull. Credentials MUST come from env vars (repo is public; no committed hostnames/users).

    ```bash
    #!/usr/bin/env bash
    # deploy.sh — Windows-local → remote WSL sync for Phase 4 dev loop.
    #
    # Required env vars (set in your shell, NEVER committed):
    #   OMNIGRAPH_SSH_HOST   remote hostname (set in your shell; never committed)
    #   OMNIGRAPH_SSH_PORT   SSH port (set in your shell; never committed)
    #   OMNIGRAPH_SSH_USER   remote username (set in your shell; never committed)
    # Optional:
    #   OMNIGRAPH_REMOTE_DIR remote repo path (default: ~/OmniGraph-Vault)
    #
    # Usage:
    #   ./deploy.sh            # push local, pull on remote
    #   ./deploy.sh --no-push  # skip local push, only pull on remote

    set -euo pipefail

    : "${OMNIGRAPH_SSH_HOST:?OMNIGRAPH_SSH_HOST not set}"
    : "${OMNIGRAPH_SSH_PORT:?OMNIGRAPH_SSH_PORT not set}"
    : "${OMNIGRAPH_SSH_USER:?OMNIGRAPH_SSH_USER not set}"
    REMOTE_DIR="${OMNIGRAPH_REMOTE_DIR:-OmniGraph-Vault}"

    if [[ "${1:-}" != "--no-push" ]]; then
      echo "→ git push (local)"
      git push
    fi

    echo "→ git pull (remote ${OMNIGRAPH_SSH_HOST}:${OMNIGRAPH_SSH_PORT})"
    ssh -p "${OMNIGRAPH_SSH_PORT}" "${OMNIGRAPH_SSH_USER}@${OMNIGRAPH_SSH_HOST}" \
      "cd ${REMOTE_DIR} && git pull --ff-only && git log -1 --oneline"

    echo "✓ deploy complete"
    ```

    Make it executable via git: after writing, run `git update-index --chmod=+x deploy.sh` locally (or `chmod +x deploy.sh` if on bash).

    Create `tests/fixtures/golden_articles.txt` with this placeholder content:

    ```
    # Golden-file regression fixtures (Phase 4 image_pipeline refactor — D-16)
    #
    # List the <article_hash> values of 2-3 WeChat articles from the remote
    # ~/.hermes/omonigraph-vault/images/ directory that have BOTH final_content.md
    # AND metadata.json with at least 3 images.
    #
    # Populated via the REMOTE capture step (see Task 0.5 below).
    # One hash per line. Lines starting with # are ignored.
    ```
  </action>
  <verify>
    <automated>bash -n deploy.sh && test -f tests/fixtures/golden_articles.txt</automated>
  </verify>
  <acceptance_criteria>
    - File `deploy.sh` exists at repo root and passes `bash -n deploy.sh` (syntax check)
    - `grep -q "OMNIGRAPH_SSH_HOST" deploy.sh` succeeds
    - `grep -q "git pull --ff-only" deploy.sh` succeeds
    - The executor MUST run a credential-leakage anti-regression grep using the actual hostname/port/username values (read from their local env vars, NOT hardcoded here) and confirm `grep -vE "^#|^$" deploy.sh | grep -v "OMNIGRAPH_SSH_" | grep -E "$OMNIGRAPH_SSH_HOST|$OMNIGRAPH_SSH_PORT|$OMNIGRAPH_SSH_USER"` returns NO matches. This check must pass before the plan is marked complete.
    - `grep -q "set -euo pipefail" deploy.sh` succeeds
    - File `tests/fixtures/golden_articles.txt` exists
  </acceptance_criteria>
  <done>Deploy helper exists, uses env vars only, passes bash syntax check</done>
</task>

<task type="checkpoint:human-action">
  <name>Task 0.5: Remote golden-file fixture capture (MANUAL)</name>
  <files>tests/fixtures/golden/</files>
  <read_first>
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §7 (golden-file regression design)
    - tests/fixtures/golden_articles.txt (placeholder to populate)
  </read_first>
  <action>
    This is a MANUAL step that cannot be automated from Windows because the data lives on the remote WSL host.

    User must perform these steps on their Windows host (with SSH env vars set per Task 0.4):

    ```bash
    # 1. SSH to remote and find articles with complete caches
    ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST \
      'cd ~/.hermes/omonigraph-vault/images && \
       for d in */; do \
         h=${d%/}; \
         if [[ -f "$d/final_content.md" && -f "$d/metadata.json" ]]; then \
           nimg=$(python3 -c "import json; print(len(json.load(open(\"$d/metadata.json\")).get(\"images\",[])))"); \
           [[ $nimg -ge 3 ]] && echo "$h $nimg"; \
         fi; \
       done | head -3'

    # 2. Pick 2-3 hashes from the output, record them in tests/fixtures/golden_articles.txt
    #    (one per line, replace the placeholder comments)

    # 3. For each picked hash $H, copy the snapshot back to local:
    ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST \
      "tar -C ~/.hermes/omonigraph-vault/images -czf - $H/final_content.md $H/metadata.json" \
      | tar -C tests/fixtures/golden -xzf -

    # 4. Commit tests/fixtures/golden/<hash>/ directories + the updated golden_articles.txt
    ```

    Resume-signal: type "golden fixtures captured" once `tests/fixtures/golden/` contains at least 2 subdirectories each with `final_content.md` and `metadata.json`.
  </action>
  <verify>
    <automated>find tests/fixtures/golden -name "final_content.md" | wc -l | awk '{exit ($1 < 2)}'</automated>
  </verify>
  <acceptance_criteria>
    - `find tests/fixtures/golden -name "final_content.md" | wc -l` returns >= 2
    - `find tests/fixtures/golden -name "metadata.json" | wc -l` returns >= 2
    - `grep -vE "^#|^$" tests/fixtures/golden_articles.txt | wc -l` returns >= 2 (at least 2 hashes listed)
    - Each golden subdirectory hash matches an entry in `golden_articles.txt`
  </acceptance_criteria>
  <done>At least 2 golden-file snapshots captured locally; hashes recorded in golden_articles.txt</done>
</task>

</tasks>

<verification>
  Wave 0 sign-off:
  1. `pytest --collect-only -q` exits 0
  2. `pytest tests/unit/test_migrations.py -x` — all 4 tests pass
  3. `bash -n deploy.sh` exits 0
  4. `python -c "import ast; ast.parse(open('scripts/phase0_delete_spike.py').read())"` exits 0
  5. `find tests/fixtures/golden -name "final_content.md" | wc -l` >= 2
  6. (Remote, manual) `ssh remote 'python scripts/phase0_delete_spike.py'` produces `.planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md` with `status: success`
</verification>

<success_criteria>
- pytest discovers tests/ and runs
- SQLite migration has 4 passing idempotency tests
- Phase-0 spike script exists with correct exit-code contract + auto-generates a success/fail report on first remote run
- deploy.sh drives remote git pull using only env vars (no committed credentials)
- Golden fixtures captured for Wave 1 regression gate
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-00-SUMMARY.md`.
</output>
