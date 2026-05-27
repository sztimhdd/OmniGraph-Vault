---
phase: 05-pipeline-automation
plan: 01
type: execute
wave: 1
depends_on: [05-00]
files_modified:
  - batch_scan_kol.py
  - data/agent_ecosystem_2026.opml
  - enrichment/__init__.py
  - enrichment/rss_schema.py
  - scripts/seed_rss_feeds.py
  - tests/verify_rss_opml.py
  - tests/unit/test_rss_schema.py
  - requirements.txt
autonomous: true
requirements: [D-11, D-15]
must_haves:
  truths:
    - "SQLite schema includes `rss_feeds`, `rss_articles`, `rss_classifications` tables with PRD §3.1.4 columns"
    - "Schema creation is idempotent (running twice adds no duplicate columns or tables)"
    - "OPML file `data/agent_ecosystem_2026.opml` is bundled in-repo and contains 60-80 RSS outline entries, each with `omg:dimension`, `omg:priority`, `omg:source_type` attributes (custom namespace `xmlns:omg=\"https://omnigraph-vault/ns\"`)"
    - "`scripts/seed_rss_feeds.py` parses the OPML, extracts the 3 omg:* attributes, and inserts 60-80 rows into `rss_feeds` populating `dimension`, `priority`, `source_type` columns (idempotent via UNIQUE xml_url)"
    - "`feedparser` and `langdetect` are added to `requirements.txt`"
    - "`tests/verify_rss_opml.py` asserts ≥ 60 feeds parse from the bundled OPML and every leaf carries all 3 omg:* attributes"
  artifacts:
    - path: "data/agent_ecosystem_2026.opml"
      provides: "Versioned OPML snapshot of curated VitaClaw-relevant agent-ecosystem feed list (60-80 entries with omg:dimension|priority|source_type custom-namespace attributes)"
    - path: "enrichment/rss_schema.py"
      provides: "CREATE TABLE IF NOT EXISTS statements for RSS tables, callable as init_rss_schema(conn)"
      contains: "CREATE TABLE IF NOT EXISTS rss_feeds"
    - path: "scripts/seed_rss_feeds.py"
      provides: "OPML parse + INSERT OR IGNORE INTO rss_feeds"
      min_lines: 40
    - path: "tests/verify_rss_opml.py"
      provides: "OPML parse assertion (≥90 feeds)"
      contains: ">= 60"
    - path: "batch_scan_kol.py"
      provides: "Auto-runs init_rss_schema alongside init_db"
      contains: "init_rss_schema"
  key_links:
    - from: "batch_scan_kol.init_db"
      to: "enrichment.rss_schema.init_rss_schema"
      via: "auto-import and call in init_db()"
      pattern: "init_rss_schema"
    - from: "scripts/seed_rss_feeds.py"
      to: "data/kol_scan.db rss_feeds table"
      via: "xml.etree.ElementTree parse + sqlite3 INSERT OR IGNORE"
      pattern: "INSERT OR IGNORE INTO rss_feeds"
---

<objective>
Establish the RSS SQLite schema, bundle the Karpathy HN 2025 OPML snapshot in-repo, seed `rss_feeds` with 92 entries, and add new deps. This is the foundation all other Wave 1 RSS work depends on.

Purpose: Without schema + 92-feed registry, `rss_fetch.py` has nothing to iterate over. Bundling the OPML in-repo provides reproducible cold-starts with no gist-fetch dependency.

Output: three new SQLite tables; 92 feeds registered; bundled OPML; deps installed; idempotent migration call wired into `batch_scan_kol.init_db`.

**v3.1/v3.2 composition note (added 2026-05-01):** `rss_classifications` column design MUST mirror v3.1 Phase 10's `classifications` schema (columns `article_id`, `depth_score`, `topic`, `rationale`, `classified_at`). Keep tables separate (different FK targets: `rss_articles` vs `articles`) but identical column pattern for operator-tooling compatibility. See `05-CONTEXT.md` § infra_composition.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-VALIDATION.md
@batch_scan_kol.py
@requirements.txt

<interfaces>
From `batch_scan_kol.py` (per STATE.md 9e2a0c1 — init_db auto-runs at import via `_ensure_column`):
```python
def init_db(db_path: Path) -> None:
    """Idempotent CREATE TABLE + ALTER TABLE for articles + ingestions."""
    conn = sqlite3.connect(db_path)
    # ... existing CREATE TABLE articles, ingestions, classifications ...
    _ensure_column(conn, "articles", "enriched", "INTEGER DEFAULT 0")
    # ... etc
    conn.commit(); conn.close()
```

Target: extend `init_db` to also call `init_rss_schema(conn)` from the new module.

From RESEARCH.md Pattern 5 (verified OPML parse shape):
```python
import xml.etree.ElementTree as ET
tree = ET.parse(path)
for outline in tree.getroot().findall(".//outline[@type='rss']"):
    name = outline.get("text")
    xml_url = outline.get("xmlUrl")
    html_url = outline.get("htmlUrl")
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1.1: Create `enrichment/rss_schema.py` with idempotent CREATE TABLE statements</name>
  <files>enrichment/__init__.py, enrichment/rss_schema.py, tests/unit/test_rss_schema.py</files>
  <behavior>
    - Test 1: `init_rss_schema(conn)` creates all three tables: `rss_feeds`, `rss_articles`, `rss_classifications`.
    - Test 2: Running `init_rss_schema(conn)` twice on the same DB does not error and does not duplicate tables (idempotency).
    - Test 3: Each table has the exact columns from PRD §3.1.4 — verify via `PRAGMA table_info(<table>)`.
    - Test 4: UNIQUE constraints hold — inserting a duplicate `xml_url` into `rss_feeds` raises IntegrityError; duplicate `(article_id, topic)` into `rss_classifications` raises IntegrityError.
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md §3.1.4 (exact schema DDL)
    - batch_scan_kol.py (search for `CREATE TABLE IF NOT EXISTS` and `_ensure_column` — existing idempotent pattern)
    - CLAUDE.md (Simplicity First — minimum DDL that matches PRD)
  </read_first>
  <action>
    **1. Create `enrichment/__init__.py`** — empty file (just a marker; the package already exists from Phase 4, but make sure it is importable).

    **2. Create `enrichment/rss_schema.py`:**
    ```python
    """RSS schema migration — idempotent CREATE TABLE IF NOT EXISTS for three RSS tables.

    PRD §3.1.4 is the source of truth for the DDL. Called from batch_scan_kol.init_db.
    """
    from __future__ import annotations

    import sqlite3

    _DDL = [
        """
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            xml_url TEXT NOT NULL UNIQUE,
            html_url TEXT,
            category TEXT,
            active INTEGER DEFAULT 1,
            last_fetched_at TEXT,
            error_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            dimension TEXT,
            priority TEXT,
            source_type TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS rss_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL REFERENCES rss_feeds(id),
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            author TEXT,
            summary TEXT,
            content_hash TEXT,
            published_at TEXT,
            fetched_at TEXT DEFAULT (datetime('now', 'localtime')),
            enriched INTEGER DEFAULT 0,
            content_length INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS rss_classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES rss_articles(id),
            topic TEXT NOT NULL,
            depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT,
            dimensions TEXT,
            classified_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id, topic)
        )
        """,
    ]

    def init_rss_schema(conn: sqlite3.Connection) -> None:
        """Create RSS tables if they don't exist. Idempotent."""
        cur = conn.cursor()
        for ddl in _DDL:
            cur.execute(ddl)
        conn.commit()
    ```

    **3. Create `tests/unit/test_rss_schema.py`** with the 4 behavioral tests using `sqlite3.connect(":memory:")` and `pytest`.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_rss_schema.py -v"</automated>
  </verify>
  <acceptance_criteria>
    - `enrichment/rss_schema.py` exists and contains `def init_rss_schema` and all 3 `CREATE TABLE IF NOT EXISTS` statements.
    - `grep -c "CREATE TABLE IF NOT EXISTS rss_" enrichment/rss_schema.py` returns 3.
    - `grep -q "UNIQUE(article_id, topic)" enrichment/rss_schema.py` returns 0.
    - `grep -q "xml_url TEXT NOT NULL UNIQUE" enrichment/rss_schema.py` returns 0.
    - All 4 pytest tests pass.
  </acceptance_criteria>
  <done>Schema module ready for wiring and seeding.</done>
</task>

<task type="auto">
  <name>Task 1.2: Wire `init_rss_schema` into `batch_scan_kol.init_db`</name>
  <files>batch_scan_kol.py</files>
  <read_first>
    - batch_scan_kol.py (search for `def init_db` — exact location of current init and `_ensure_column` pattern)
    - enrichment/rss_schema.py (Task 1.1 output)
    - .planning/STATE.md (9e2a0c1 note: ingest_wechat.py auto-runs init_db on import)
    - CLAUDE.md (Surgical Changes — do not touch unrelated init logic)
  </read_first>
  <action>
    In `batch_scan_kol.py`:

    1. Add import near the other module imports (after existing stdlib/3rd-party imports, grouped):
    ```python
    from enrichment.rss_schema import init_rss_schema
    ```

    2. In the `init_db(db_path: Path)` function, at the END (after all existing `_ensure_column` calls and before `conn.commit(); conn.close()`), add:
    ```python
    # Phase 5 Plan 05-01: RSS schema (idempotent)
    init_rss_schema(conn)
    ```

    Do NOT touch any other code in `batch_scan_kol.py`. No formatting changes, no reordering of existing `_ensure_column` calls.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -c 'import batch_scan_kol; print(\"ok\")'" | grep -q "^ok$" &amp;&amp; ssh remote "cd ~/OmniGraph-Vault &amp;&amp; sqlite3 data/kol_scan.db '.tables' | tr ' ' '\n' | grep -E '^rss_(feeds|articles|classifications)$' | wc -l" | grep -q "^3$"</automated>
  </verify>
  <acceptance_criteria>
    - `batch_scan_kol.py` contains `from enrichment.rss_schema import init_rss_schema`.
    - `batch_scan_kol.py` contains a call to `init_rss_schema(conn)` inside `init_db`.
    - After any import of `batch_scan_kol` or any run of `ingest_wechat.py` on remote, `data/kol_scan.db` has all three tables present: `sqlite3 data/kol_scan.db ".tables"` shows `rss_feeds rss_articles rss_classifications`.
    - H-7: On the remote production DB, capture table count BEFORE running `init_rss_schema` (`ssh remote "sqlite3 data/kol_scan.db '.tables' | tr ' ' '
' | grep -v '^$' | wc -l"`) and AFTER — the delta MUST be exactly +3, no existing tables lost, no ALTER TABLE drops, and existing row counts in articles/classifications/ingestions/kols unchanged.
  </acceptance_criteria>
  <done>Schema auto-migrates on every ingestion run.</done>
</task>

<task type="auto">
  <name>Task 1.3: Bundle OPML snapshot + add feedparser/langdetect deps + verify parse</name>
  <files>data/agent_ecosystem_2026.opml, requirements.txt, tests/verify_rss_opml.py</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (Claude's Discretion: OPML source strategy — decision: bundle in-repo)
    - data/agent_ecosystem_2026.README.md (curation rationale; OPML structure)
    - requirements.txt (existing structure — alphabetical grouping preferred)
  </read_first>
  <action>
    **1. The OPML snapshot is already bundled.**
    `data/agent_ecosystem_2026.opml` was created by quick task 260505-seu (see `.planning/quick/260505-seu-agent-ecosystem-rss-curation/`). It is in-repo, 60-80 leaf outlines, each carrying `omg:dimension`, `omg:priority`, `omg:source_type` under custom namespace `xmlns:omg="https://omnigraph-vault/ns"`. No fetch needed — verify presence:
    ```bash
    ssh remote "cd ~/OmniGraph-Vault && test -f data/agent_ecosystem_2026.opml && wc -l data/agent_ecosystem_2026.opml"
    ```

    **2. Add deps to `requirements.txt`.**
    Append two lines preserving alphabetical order if the file is alphabetized, otherwise at the end:
    ```
    feedparser>=6.0
    langdetect>=1.0
    ```
    DO NOT re-sort or reformat the rest of the file (surgical change).

    Install on remote:
    ```bash
    ssh remote "cd ~/OmniGraph-Vault && venv/bin/pip install feedparser langdetect"
    ```

    **3. Create `tests/verify_rss_opml.py`:**
    ```python
    """Verify bundled OPML parses to at least 60 RSS feeds with all omg:* attrs set."""
    import sys
    from pathlib import Path
    import xml.etree.ElementTree as ET

    OPML = Path("data/agent_ecosystem_2026.opml")
    NS = {"omg": "https://omnigraph-vault/ns"}
    assert OPML.exists(), f"OPML not found at {OPML}"
    tree = ET.parse(OPML)
    feeds = tree.getroot().findall(".//outline[@type='rss']")
    print(f"feed_count: {len(feeds)}")
    assert 60 <= len(feeds) <= 80, f"Expected 60-80 feeds, got {len(feeds)}"

    # Every leaf has all 3 omg:* attrs non-empty
    missing = []
    for f in feeds:
        for attr in ("dimension", "priority", "source_type"):
            v = f.get(f"{{{NS['omg']}}}{attr}")
            if not v:
                missing.append((f.get("text") or f.get("xmlUrl"), attr))
    assert not missing, f"Missing omg:* attrs on {len(missing)} entries: {missing[:5]}"

    # Spot check expected VitaClaw-relevant feeds
    urls = {f.get("xmlUrl") for f in feeds}
    expected_samples = [
        "langchain-ai",
        "microsoft",
        "huggingface.co",
    ]
    missing_samples = [s for s in expected_samples if not any(s in (u or "") for u in urls)]
    assert not missing_samples, f"Missing expected sample feeds: {missing_samples}"
    print("OK: OPML parse + omg-attr + sample check passed")
    sys.exit(0)
    ```
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; test -f data/agent_ecosystem_2026.opml &amp;&amp; venv/bin/python tests/verify_rss_opml.py &amp;&amp; venv/bin/pip list 2&gt;/dev/null | grep -E '^(feedparser|langdetect)\s'" | wc -l | awk '{if($1 &gt;= 2) exit 0; else exit 1}'</automated>
  </verify>
  <acceptance_criteria>
    - File `data/agent_ecosystem_2026.opml` exists; `python -c "import xml.etree.ElementTree as ET; ET.parse('data/agent_ecosystem_2026.opml')"` exits 0.
    - `tests/verify_rss_opml.py` exits 0 (60-80 feeds parsed, all omg:* attrs present, 3 known samples present).
    - `requirements.txt` contains `feedparser>=6.0` and `langdetect>=1.0`.
    - On remote, `venv/bin/pip list | grep -iE 'feedparser|langdetect'` returns both packages.
  </acceptance_criteria>
  <done>OPML bundled; deps installed; parse + omg:* validation verified.</done>
</task>

<task type="auto">
  <name>Task 1.4: Create seed script that populates `rss_feeds` from bundled OPML</name>
  <files>scripts/seed_rss_feeds.py</files>
  <read_first>
    - data/agent_ecosystem_2026.opml (Task 1.3 — already bundled)
    - enrichment/rss_schema.py (Task 1.1 output — schema DDL with dimension/priority/source_type columns added)
    - tests/verify_rss_opml.py (Task 1.3 output — parse pattern with namespace handling to reuse)
    - config.py (path to data dir — uses `BASE_DIR`, but `kol_scan.db` is at `data/kol_scan.db` relative to repo root)
  </read_first>
  <action>
    Create `scripts/seed_rss_feeds.py`:
    ```python
    """Seed rss_feeds table from bundled OPML.

    Idempotent via INSERT OR IGNORE (xml_url UNIQUE constraint). Safe to re-run.
    Run after batch_scan_kol.init_db has created the rss_feeds table.

    Reads the 3 custom-namespace attributes (omg:dimension, omg:priority, omg:source_type)
    and writes them into the new dimension/priority/source_type columns added in 05-01 Task 1.1.

    Usage:
        venv/bin/python scripts/seed_rss_feeds.py                # run
        venv/bin/python scripts/seed_rss_feeds.py --dry-run      # preview
    """
    from __future__ import annotations

    import argparse
    import sqlite3
    import sys
    import xml.etree.ElementTree as ET
    from pathlib import Path

    OPML = Path("data/agent_ecosystem_2026.opml")
    DB = Path("data/kol_scan.db")
    NS = {"omg": "https://omnigraph-vault/ns"}

    def parse_opml(path: Path) -> list[dict]:
        tree = ET.parse(path)
        feeds = []
        for outline in tree.getroot().findall(".//outline[@type='rss']"):
            feeds.append({
                "name": outline.get("text") or outline.get("title") or "",
                "xml_url": outline.get("xmlUrl") or "",
                "html_url": outline.get("htmlUrl") or None,
                "category": None,
                "dimension": outline.get(f"{{{NS['omg']}}}dimension") or None,
                "priority": outline.get(f"{{{NS['omg']}}}priority") or None,
                "source_type": outline.get(f"{{{NS['omg']}}}source_type") or None,
            })
        return [f for f in feeds if f["xml_url"]]

    def seed(db_path: Path, feeds: list[dict], dry_run: bool) -> tuple[int, int]:
        conn = sqlite3.connect(db_path)
        try:
            before = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
            if not dry_run:
                conn.executemany(
                    """INSERT OR IGNORE INTO rss_feeds
                       (name, xml_url, html_url, category, dimension, priority, source_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [(f["name"], f["xml_url"], f["html_url"], f["category"],
                      f["dimension"], f["priority"], f["source_type"]) for f in feeds],
                )
                conn.commit()
            after = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
            return before, after
        finally:
            conn.close()

    def main() -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--dry-run", action="store_true")
        args = p.parse_args()
        feeds = parse_opml(OPML)
        print(f"Parsed {len(feeds)} feeds from {OPML}")
        before, after = seed(DB, feeds, args.dry_run)
        print(f"rss_feeds count: {before} -> {after}")
        if args.dry_run:
            print("(dry-run: no writes)")

    if __name__ == "__main__":
        main()
    ```

    Ensure the script prints the before/after count. On a fresh DB (empty `rss_feeds`), after count should be 60-80 (matching the OPML). On re-run, before == after (dedup via UNIQUE constraint).
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python scripts/seed_rss_feeds.py &amp;&amp; sqlite3 data/kol_scan.db 'SELECT COUNT(*) FROM rss_feeds'" | tail -1 | awk '{if($1 &gt;= 60) exit 0; else exit 1}'</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/seed_rss_feeds.py` exists.
    - After running on remote, `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds"` returns ≥ 60.
    - Re-running the script produces "rss_feeds count: <N> -> <N>" (no duplicates inserted).
    - The new columns are populated: `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds WHERE dimension IS NOT NULL AND priority IS NOT NULL AND source_type IS NOT NULL"` returns ≥ 60 (every row has all 3 attrs).
    - At least 5 distinct dimension values present: `sqlite3 data/kol_scan.db "SELECT COUNT(DISTINCT dimension) FROM rss_feeds"` returns ≥ 5.
    - Three known feeds are present: `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds WHERE xml_url LIKE '%langchain%' OR xml_url LIKE '%microsoft%' OR xml_url LIKE '%huggingface%'"` returns ≥ 3.
  </acceptance_criteria>
  <done>60-80 feeds registered with dimension/priority/source_type populated; ready for `rss_fetch.py` in Plan 05-02.</done>
</task>

</tasks>

<verification>
- Three RSS tables created in `data/kol_scan.db`.
- 92 feeds registered in `rss_feeds`.
- OPML file bundled in repo and versioned.
- feedparser + langdetect installed on remote venv.
</verification>

<success_criteria>
- Idempotent RSS schema migration wired into init_db.
- Bundled OPML parses to 92 feeds.
- `rss_feeds` seeded; re-running seed is a no-op.
- Deps locked in requirements.txt.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-01-SUMMARY.md` with: feed counts (parsed, seeded), schema DDL reference, any OPML quirks encountered, and confirmation that re-seed is a no-op.
</output>
