"""Nightly body-translation cron (260520-trans-inc).

Translates ~10 articles per run that have passed Layer 1 + Layer 2 but lack
``body_translated``. Runs on Hermes only; Aliyun + Databricks consume the
translated DB via existing SCP / Databricks-deploy mechanisms.

Behavior:
  - SELECT from articles + rss_articles (UNION ALL) where
        layer1_verdict='candidate' AND layer2_verdict='ok'
        AND body IS NOT NULL AND body != ''
        AND body_translated IS NULL
    ORDER BY layer2_at ASC LIMIT N (default 10)
  - For each row: detect source lang, call translate_body_with_deepseek_tavily,
    on success UPDATE body_translated + translated_lang + translated_at
    (DO NOT touch title_translated — preserve any pre-existing inline title)
  - Per-row failure logged and skipped; whole run never crashes on individual
    LLM/Tavily errors.

Logs to both stdout AND .scratch/translate-body-cron-YYYYMMDD.log

CLI:
    venv/bin/python scripts/translate_body_cron.py                # production
    venv/bin/python scripts/translate_body_cron.py --dry-run      # SELECT only, no LLM, no UPDATE
    venv/bin/python scripts/translate_body_cron.py --limit 3      # custom batch size

Cron registration (operator action on Hermes — NOT in this repo):
    Add to ~/.hermes/cron/jobs.json:
        {"schedule": "30 3 * * *",
         "command": "cd ~/OmniGraph-Vault && venv/bin/python scripts/translate_body_cron.py",
         "timeout_sec": 1800}
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# Phase 5 cross-coupling defense: ensure DEEPSEEK_API_KEY is set before any
# lib.* import chain pulls in lib.llm_deepseek (which raises at import-time
# if key is unset). config.load_env() will populate from ~/.hermes/.env.
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

# Make repo root importable when running as a script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import BASE_DIR  # noqa: E402

DEFAULT_LIMIT = 10
LOG_DIR = _REPO_ROOT / ".scratch"


def _resolve_db_path() -> Path:
    """Locate the SQLite DB.

    Production (Hermes): ``$BASE_DIR/kol_scan.db`` =
    ``~/.hermes/omonigraph-vault/kol_scan.db`` (typo is canonical).

    Local dev: when ``OMNIGRAPH_BASE_DIR`` is set to ``.dev-runtime``,
    config.BASE_DIR resolves to ``.dev-runtime``, but the production layout
    nests data under ``data/``. Try ``BASE_DIR/data/kol_scan.db`` first
    (matches local dev layout used by .scratch/local_serve.py and the
    rest of the test fixtures), fall back to ``BASE_DIR/kol_scan.db``.
    """
    base = Path(BASE_DIR)
    nested = base / "data" / "kol_scan.db"
    if nested.exists():
        return nested
    return base / "kol_scan.db"


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"translate-body-cron-{date.today():%Y%m%d}.log"
    fmt = "%(asctime)s %(levelname)s %(message)s"
    # Reconfigure stdout to UTF-8 so Chinese article titles render in the
    # Windows console (Hermes Linux is already UTF-8 by default; this is a
    # no-op on POSIX). Using reconfigure() requires Python 3.7+; safe-guard
    # via getattr in case stdout is wrapped by something non-standard.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    return logging.getLogger("translate_body_cron")


def _select_candidate_rows(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[int, str, str, str]]:
    """Return list of (id, table_name, title, body) for body translation.

    Wraps the UNION ALL in a subquery so ORDER BY layer2_at applies across
    both tables (cannot ORDER BY layer2_at directly across UNION without
    the subquery wrap).
    """
    sql = """
        SELECT id, table_name, title, body
          FROM (
            SELECT id, 'articles' AS table_name, title, body, layer2_at
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_translated IS NULL
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, title, body, layer2_at
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_translated IS NULL
          )
         ORDER BY layer2_at ASC, id ASC
         LIMIT ?
    """
    return list(conn.execute(sql, (limit,)))


async def _translate_one_row(
    row: tuple[int, str, str, str],
    conn: sqlite3.Connection,
    dry_run: bool,
    logger: logging.Logger,
) -> str:
    """Translate one row and UPDATE the source table (or log only on dry-run).

    Returns: 'ok' / 'fail' / 'dry_run' so the caller can tally.
    """
    art_id, table, title, body = row
    if dry_run:
        logger.info(
            "[dry-run] WOULD translate id=%s table=%s title=%s body_len=%d",
            art_id, table, (title or "")[:80], len(body or ""),
        )
        return "dry_run"

    # Lazy import inside the per-row loop so the dry-run path never imports
    # the translate / DeepSeek chain (keeps --dry-run runnable without keys).
    from lib.translate import (
        detect_source_lang,
        translate_body_with_deepseek_tavily,
    )

    src_lang = detect_source_lang(title or body or "")
    try:
        result = await translate_body_with_deepseek_tavily(
            title or "", body, source_lang=src_lang
        )
    except Exception as e:
        logger.warning(
            "translate_body raised (id=%s table=%s): %s — leaving NULL",
            art_id, table, e,
        )
        return "fail"

    if not result:
        logger.info(
            "translate_body returned None (id=%s table=%s) — leaving NULL",
            art_id, table,
        )
        return "fail"

    # NB: do NOT touch title_translated — preserve any inline-translated title
    # from batch_ingest_from_spider.py path. Only update the body fields.
    conn.execute(
        f"UPDATE {table} SET body_translated = ?, "  # noqa: S608 (table is a fixed literal from SELECT)
        "translated_lang = ?, translated_at = ? WHERE id = ?",
        (
            result["body_translated"],
            result["lang"],
            datetime.now(timezone.utc).isoformat(),
            art_id,
        ),
    )
    conn.commit()
    logger.info(
        "ok id=%s table=%s lang=%s body_len_in=%d body_len_out=%d",
        art_id, table, result["lang"], len(body or ""),
        len(result["body_translated"]),
    )
    return "ok"


async def _run(args: argparse.Namespace, logger: logging.Logger) -> int:
    db_path = _resolve_db_path()
    if not db_path.exists():
        logger.error("DB not found: %s", db_path)
        return 1
    logger.info(
        "translate_body_cron starting (limit=%d dry_run=%s db=%s)",
        args.limit, args.dry_run, db_path,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = _select_candidate_rows(conn, args.limit)
        if not rows:
            logger.info("0 candidates — nothing to translate")
            return 0
        logger.info("selected %d candidate(s) for translation", len(rows))

        start = time.time()
        tally = {"ok": 0, "fail": 0, "dry_run": 0}
        for row in rows:
            outcome = await _translate_one_row(row, conn, args.dry_run, logger)
            tally[outcome] = tally.get(outcome, 0) + 1
        elapsed = time.time() - start
        logger.info(
            "summary attempted=%d ok=%d fail=%d dry_run=%d elapsed=%.1fs",
            len(rows), tally["ok"], tally["fail"], tally["dry_run"], elapsed,
        )
        return 0
    finally:
        conn.close()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Translate ~N untranslated article bodies via DeepSeek + Tavily.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print SELECT result + LLM call shape; do NOT call LLM, do NOT UPDATE.",
    )
    p.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Max articles per run (default {DEFAULT_LIMIT}).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logger = _setup_logging()
    return asyncio.run(_run(args, logger))


if __name__ == "__main__":
    raise SystemExit(main())
