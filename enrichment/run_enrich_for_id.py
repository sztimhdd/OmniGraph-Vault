"""Bridge: resolve article path + URL + hash from DB, then invoke enrich_article
via the env-var contract (ARTICLE_PATH, ARTICLE_URL, ARTICLE_HASH).

The enrich_article Hermes skill (skills/enrich_article/SKILL.md) reads its
inputs from env vars — NOT CLI flags. Phase 5 orchestrator step_6 calls
this bridge per KOL article instead of hardcoding
``hermes skill run enrich_article --article-id ...``, which would silently
no-op.

RSS is excluded from enrichment per D-07 REVISED 2026-05-02 + D-19.
``--source rss`` is kept as a guarded no-op branch for backwards-compat
with any legacy caller: it logs the exclusion and exits 0 without
resolving DB or invoking the skill.

Usage:
    venv/bin/python enrichment/run_enrich_for_id.py --source kol --article-id 42
    venv/bin/python enrichment/run_enrich_for_id.py --source rss --article-id 17  # no-op
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from config import BASE_DIR

DB = Path("data/kol_scan.db")
SKILL_CMD = ["hermes", "skill", "run", "enrich_article"]
# SKILL.md puts a ~10 min ceiling on enrich_article; 15 min timeout = safety margin.
SKILL_TIMEOUT_SECONDS = 900


def _resolve_kol(article_id: int) -> tuple[str, str, str] | None:
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute(
            "SELECT url, content_hash FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    url, content_hash = row
    if not content_hash:
        return None
    path = BASE_DIR / "images" / content_hash / "final_content.md"
    return str(path), url, content_hash


def _resolve_rss(article_id: int) -> tuple[str, str, str] | None:
    """Preserved for parity with _resolve_kol. Not used by main() after
    D-07 REVISED 2026-05-02 + D-19 — kept so any future reactivation of
    RSS enrichment can reuse the path-derivation logic without
    re-authoring it."""
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute(
            "SELECT url FROM rss_articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    (url,) = row
    article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    path = BASE_DIR / "rss_content" / article_hash / "final_content.md"
    return str(path), url, article_hash


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True, choices=["kol", "rss"])
    p.add_argument("--article-id", type=int, required=True)
    args = p.parse_args()

    # D-07 REVISED 2026-05-02 + D-19: RSS is excluded from enrichment.
    # The branch exists for backwards-compat with any legacy caller; it
    # logs the exclusion and exits 0 WITHOUT resolving DB, WITHOUT invoking
    # the enrich_article skill. RSS articles flow through
    # enrichment/rss_ingest.py's direct translate -> ainsert path instead.
    if args.source == "rss":
        print(
            "RSS excluded per D-07 REVISED 2026-05-02 + D-19 — "
            f"article-id={args.article_id} not enriched (no-op)"
        )
        return 0

    resolved = _resolve_kol(args.article_id)
    if resolved is None:
        print(
            f"ERROR: kol article id={args.article_id} not found or missing content_hash",
            file=sys.stderr,
        )
        return 2

    article_path, article_url, article_hash = resolved
    env = os.environ.copy()
    env["ARTICLE_PATH"] = article_path
    env["ARTICLE_URL"] = article_url
    env["ARTICLE_HASH"] = article_hash

    print(f"Invoking enrich_article skill for kol id={args.article_id}")
    print(f"  ARTICLE_PATH={article_path}")
    print(f"  ARTICLE_URL={article_url}")
    print(f"  ARTICLE_HASH={article_hash}")

    result = subprocess.run(
        SKILL_CMD,
        env=env,
        capture_output=True,
        text=True,
        timeout=SKILL_TIMEOUT_SECONDS,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
