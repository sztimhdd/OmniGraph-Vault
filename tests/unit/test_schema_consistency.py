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

# 2026-05-10 hot-fix (quick 260510-h09): regex made column-aware so it picks
# the literal at the position of the ``status`` column, not the first quoted
# literal after VALUES. Previously a multi-column INSERT with `'wechat'` in
# the source column would cause the test to flag 'wechat' as a missing
# status literal.
#
# INSERT_RE captures (col_list, values_list) so we can index by column name.
# Backstop, not a SQL parser. The `.{0,400}?` cap prevents greedy runaway.
INSERT_RE = re.compile(
    r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+ingestions\s*\(([^)]+)\).{0,400}?VALUES\s*\((.{0,400}?)\)",
    re.IGNORECASE | re.DOTALL,
)
CHECK_RE = re.compile(r"CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)", re.IGNORECASE)
QUOTED_LITERAL_RE = re.compile(r"'([^']+)'")


def _extract_status_literal(col_list: str, values_list: str) -> str | None:
    """Return the literal at the position of the ``status`` column, or None.

    Returns None when:
      - ``status`` is not in the column list
      - the value at status's position is a non-literal (e.g. ?, :placeholder,
        or an embedded SELECT) — those are dynamic, not static literals.
    """
    cols = [c.strip().lower() for c in col_list.split(",")]
    if "status" not in cols:
        return None
    idx = cols.index("status")
    # Splitting values by comma is naive but adequate for the simple
    # `((SELECT ... ?), 'wechat', 'ok')` shape used by all known call sites.
    # If a SELECT subquery is at idx, it'll have parens that won't quote-strip
    # — those return None (dynamic, not a literal).
    vals = [v.strip() for v in values_list.split(",")]
    if idx >= len(vals):
        return None
    val = vals[idx]
    # Strip outer quotes if literal; otherwise this is a placeholder/expr.
    if val.startswith("'") and val.endswith("'") and len(val) >= 2:
        return val[1:-1]
    return None


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
    """Return mapping of status_literal -> set of source files mentioning it.

    Uses column-aware extraction so multi-column INSERTs (e.g. with a 'wechat'
    source column added by mig 008) only flag literals from the actual
    ``status`` column, not arbitrary quoted strings elsewhere in VALUES.
    """
    found: dict[str, set[str]] = {}
    for py_path in _iter_py_files(REPO_ROOT):
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in INSERT_RE.finditer(text):
            literal = _extract_status_literal(m.group(1), m.group(2))
            if literal is None:
                continue
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
