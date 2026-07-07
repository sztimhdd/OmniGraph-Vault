"""Nightly body-translation cron (260520-trans-inc).

Translates ~10 articles per run that have passed Layer 1 + Layer 2 but lack
``body_translated`` or ``title_translated``. Runs on Hermes only; Aliyun +
Databricks consume the translated DB via existing SCP / Databricks-deploy
mechanisms.

Behavior:
  - SELECT from articles + rss_articles (UNION ALL) where
        layer1_verdict='candidate' AND layer2_verdict='ok'
        AND body IS NOT NULL AND body != ''
        AND (body_translated IS NULL OR title_translated IS NULL)
    ORDER BY layer2_at ASC LIMIT N (default 10)
  - For each row: detect source lang, then independently translate whichever
    of body / title is NULL. Body and title each have their own try/except
    so a failure in one path does not block the other (260528-mi6 BL-1).
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
) -> list[tuple[int, str, str, str, Optional[str], Optional[str]]]:
    """Return rows needing body and/or title translation.

    Tuple shape: ``(id, table_name, title, body, body_translated, title_translated)``.
    The two trailing columns let ``_translate_one_row`` decide per-row which
    field(s) actually need an LLM call — a row where body is already filled
    but title is NULL still enters the pool (260528-mi6 BL-1 backfill).

    Wraps the UNION ALL in a subquery so ORDER BY layer2_at applies across
    both tables.
    """
    sql = """
        SELECT id, table_name, title, body, body_translated, title_translated
          FROM (
            SELECT id, 'articles' AS table_name, title,
                   COALESCE(body_rewritten, body) AS body,
                   body_translated, title_translated, layer2_at
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND (body_translated IS NULL OR title_translated IS NULL)
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, title,
                   COALESCE(body_rewritten, body) AS body,
                   body_translated, title_translated, layer2_at
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND (body_translated IS NULL OR title_translated IS NULL)
          )
         ORDER BY layer2_at ASC, id ASC
         LIMIT ?
    """
    return list(conn.execute(sql, (limit,)))


async def _translate_one_row(
    row: tuple[int, str, str, str, Optional[str], Optional[str]],
    conn: sqlite3.Connection,
    dry_run: bool,
    logger: logging.Logger,
) -> str:
    """Translate one row's missing field(s) and UPDATE the source table.

    Body and title are translated independently — each path has its own
    try/except so a failure in one does not abort the other. Outcome
    aggregation: returns 'ok' if AT LEAST ONE field needed translation and
    succeeded; 'fail' if every needed field failed; 'dry_run' if dry-run.
    """
    art_id, table, title, body, body_translated, title_translated = row
    needs_body = body_translated is None
    needs_title = title_translated is None

    if dry_run:
        logger.info(
            "[dry-run] WOULD translate id=%s table=%s needs_body=%s needs_title=%s "
            "title=%s body_len=%d",
            art_id, table, needs_body, needs_title,
            (title or "")[:80], len(body or ""),
        )
        return "dry_run"

    # Lazy import inside the per-row loop so the dry-run path never imports
    # the translate / DeepSeek chain (keeps --dry-run runnable without keys).
    from lib.translate import (
        detect_source_lang,
        translate_body_with_deepseek_tavily,
        translate_title_with_deepseek_tavily,
    )

    src_lang = detect_source_lang(title or body or "")
    body_ok = False
    title_ok = False

    if needs_body:
        try:
            body_result = await translate_body_with_deepseek_tavily(
                title or "", body, source_lang=src_lang
            )
        except Exception as e:
            logger.warning(
                "translate_body raised (id=%s table=%s): %s — leaving NULL",
                art_id, table, e,
            )
            body_result = None

        if body_result:
            conn.execute(
                f"UPDATE {table} SET body_translated = ?, "  # noqa: S608 (table is a fixed literal from SELECT)
                "translated_lang = ?, translated_at = ? WHERE id = ?",
                (
                    body_result["body_translated"],
                    body_result["lang"],
                    datetime.now(timezone.utc).isoformat(),
                    art_id,
                ),
            )
            conn.commit()
            body_ok = True
            logger.info(
                "body ok id=%s table=%s lang=%s body_len_in=%d body_len_out=%d",
                art_id, table, body_result["lang"], len(body or ""),
                len(body_result["body_translated"]),
            )
        else:
            logger.info(
                "translate_body returned None (id=%s table=%s) — leaving NULL",
                art_id, table,
            )

    if needs_title and title and title.strip():
        try:
            title_result = await translate_title_with_deepseek_tavily(
                title, source_lang=src_lang
            )
        except Exception as e:
            logger.warning(
                "translate_title raised (id=%s table=%s): %s — leaving NULL",
                art_id, table, e,
            )
            title_result = None

        if title_result:
            conn.execute(
                f"UPDATE {table} SET title_translated = ? WHERE id = ?",  # noqa: S608
                (title_result["title_translated"], art_id),
            )
            conn.commit()
            title_ok = True
            logger.info(
                "title ok id=%s table=%s lang=%s title_in=%s title_out=%s",
                art_id, table, title_result["lang"],
                title[:60], title_result["title_translated"][:60],
            )
        else:
            logger.info(
                "translate_title returned None (id=%s table=%s) — leaving NULL",
                art_id, table,
            )

    return "ok" if (body_ok or title_ok) else "fail"


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
