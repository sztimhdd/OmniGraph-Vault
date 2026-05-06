"""Static check: every status literal INSERTed into ingestions lives in a CHECK whitelist.

Quick: 260506-se5 (2026-05-06)

Records the latent-bug pattern from CLAUDE.md "Lessons Learned 2026-05-04 #3"
as a CI backstop. Day-2 cron prep that day surfaced a schema-shift bug:
INSERT INTO ingestions wrote 'skipped_ingested' / 'dry_run' literals at
least a week before migrations/002 added them to the CHECK whitelist; the
mismatch was latent until a specific code path triggered IntegrityError
mid-batch.

Logic:
    1. Walk repo tree (excluding tests/, venv/, .venv/, .dev-runtime/,
       __pycache__/) and grep all .py files for `INSERT INTO ingestions ...
       VALUES ... '<literal>'` patterns.
    2. Build whitelist by reading migrations/002, migrations/003, AND
       batch_scan_kol.py CHECK clauses.
    3. Assert inserted_set ⊆ whitelist_union. Mismatch → assertion failure
       with explicit list of missing literals.

Stdlib only — no DEEPSEEK_API_KEY import-time coupling.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXCLUDE_DIRS = {"tests", "venv", ".venv", ".dev-runtime", "__pycache__", "node_modules"}

# Permissive: matches `INSERT INTO ingestions ... VALUES ... '<word>'` across
# arbitrary intervening text (column lists may include parens, so we allow
# `.` not `[^)]`). Backstop, not a SQL parser. The `.{0,400}?` cap prevents
# greedy runaway across unrelated SQL elsewhere in the file.
INSERT_RE = re.compile(
    r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+ingestions\b.{0,400}?VALUES.{0,400}?'(\w+)'",
    re.IGNORECASE | re.DOTALL,
)
CHECK_RE = re.compile(r"CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)", re.IGNORECASE)
QUOTED_LITERAL_RE = re.compile(r"'([^']+)'")


def _iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDE_DIRS:
            continue
        yield path


def _iter_sql_files(root: Path):
    for path in (root / "migrations").rglob("*.sql"):
        yield path


def _scan_inserted_statuses() -> dict[str, set[str]]:
    """Return mapping of status_literal -> set of source files mentioning it."""
    found: dict[str, set[str]] = {}
    for py_path in _iter_py_files(REPO_ROOT):
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in INSERT_RE.finditer(text):
            literal = m.group(1)
            found.setdefault(literal, set()).add(
                str(py_path.relative_to(REPO_ROOT)).replace("\\", "/")
            )
    return found


def _scan_check_whitelist() -> set[str]:
    """Union of every status literal listed inside a CHECK(status IN (...)) clause."""
    whitelist: set[str] = set()
    sources: list[Path] = [REPO_ROOT / "batch_scan_kol.py"]
    sources.extend(_iter_sql_files(REPO_ROOT))
    for src in sources:
        if not src.exists():
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in CHECK_RE.finditer(text):
            inner = m.group(1)
            for q in QUOTED_LITERAL_RE.finditer(inner):
                whitelist.add(q.group(1))
    return whitelist


def test_ingestions_status_inserts_match_check_whitelist() -> None:
    inserted = _scan_inserted_statuses()
    whitelist = _scan_check_whitelist()

    inserted_set = set(inserted.keys())
    missing = inserted_set - whitelist

    # Sanity: scanners must actually find something — guard against silent
    # regex breakage (false-pass via empty-set ⊆ anything).
    assert whitelist, (
        "schema-consistency scanner found no CHECK whitelist literals — "
        "regex broken or migrations/ moved"
    )
    assert inserted_set, (
        "schema-consistency scanner found no INSERT INTO ingestions "
        "literals — regex broken or call sites moved"
    )

    if missing:
        missing_detail = "\n".join(
            f"  - '{lit}' inserted from: {sorted(inserted[lit])}" for lit in sorted(missing)
        )
        pytest.fail(
            "ingestions.status literals INSERTed but NOT in any CHECK whitelist:\n"
            f"{missing_detail}\n"
            f"Whitelist union (migrations/*.sql + batch_scan_kol.py): "
            f"{sorted(whitelist)}\n"
            "Fix: add missing literals to migrations/<next>.sql CHECK clause "
            "(see CLAUDE.md 'Lessons Learned 2026-05-04 #3')."
        )
