"""
Batch ingestion bridge for WeChat KOL cold-start seeding.

Usage:
    python batch_ingest_from_spider.py [--dry-run] [--days-back N] [--max-articles N]

Reads accounts from kol_config.py (local only, gitignored).
For each account, lists recent articles via WeChat MP API.
For each article, calls: python ingest_wechat.py "<url>"
Writes summary JSON to data/coldstart_run_{timestamp}.json
"""
import argparse
import json
import logging
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import kol_config
except ImportError:
    print("ERROR: kol_config.py not found. Create it locally — see docs/KOL_COLDSTART_SETUP.md")
    sys.exit(1)

from spiders.wechat_spider import list_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

VENV_PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
INGEST_SCRIPT = str(PROJECT_ROOT / "ingest_wechat.py")


def get_python_exe() -> str:
    """Use venv python if available, else current interpreter."""
    if Path(VENV_PYTHON).exists():
        return VENV_PYTHON
    return sys.executable


def ingest_article(url: str, dry_run: bool) -> bool:
    """Call ingest_wechat.py for a single URL. Returns True on success."""
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True

    result = subprocess.run(
        [get_python_exe(), INGEST_SCRIPT, url],
        capture_output=False,
        timeout=300,
    )
    return result.returncode == 0


def run(days_back: int, max_articles: int, dry_run: bool) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary: list[dict] = []

    for account_name, fakeid in kol_config.FAKEIDS.items():
        logger.info("=== Account: %s (fakeid=%s) ===", account_name, fakeid)

        try:
            articles = list_articles(
                token=kol_config.TOKEN,
                cookie=kol_config.COOKIE,
                fakeid=fakeid,
                days_back=days_back,
                max_articles=max_articles,
            )
        except Exception as exc:
            logger.error("Failed to list articles for %s: %s", account_name, exc)
            summary.append({"account": account_name, "error": str(exc)})
            continue

        logger.info("Found %d articles for %s", len(articles), account_name)

        for i, article in enumerate(articles, 1):
            title = article.get("title", "(no title)")
            url = article.get("url", "")
            logger.info("[%d/%d] %s", i, len(articles), title)

            if not url:
                logger.warning("  Skipping — no URL")
                summary.append({"account": account_name, "title": title, "url": "", "status": "skipped_no_url"})
                continue

            success = ingest_article(url, dry_run)
            summary.append({
                "account": account_name,
                "title": title,
                "url": url,
                "status": "dry_run" if dry_run else ("ok" if success else "failed"),
            })

    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"coldstart_run_{timestamp}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Summary written to %s", out_path)

    ok = sum(1 for r in summary if r.get("status") in ("ok", "dry_run"))
    fail = sum(1 for r in summary if r.get("status") == "failed")
    logger.info("Done — %d ok, %d failed, %d skipped", ok, fail, len(summary) - ok - fail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest WeChat KOL articles into OmniGraph-Vault")
    parser.add_argument("--dry-run", action="store_true", help="List articles without ingesting")
    parser.add_argument("--days-back", type=int, default=90, help="How many days back to fetch (default: 90)")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles per account (default: 50)")
    args = parser.parse_args()

    run(days_back=args.days_back, max_articles=args.max_articles, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
