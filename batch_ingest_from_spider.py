"""
Batch ingestion bridge for WeChat KOL cold-start seeding.

Usage:
    python batch_ingest_from_spider.py [--dry-run] [--days-back N] [--max-articles N]
                                       [--topic-filter TOPIC] [--exclude-topics TOPICS]
                                       [--min-depth N] [--classifier deepseek|gemini]

Reads accounts from kol_config.py (local only, gitignored).
For each account, lists recent articles via WeChat MP API.
If --topic-filter or --exclude-topics is set, classifies all titles via
DeepSeek (default) or Gemini API and filters before ingesting.
For each passing article, calls: python ingest_wechat.py "<url>"
Writes summary JSON to data/coldstart_run_{timestamp}.json

Plan 05-00c Task 0c.4: default classifier is 'deepseek' (see :606). This
script subprocesses out to ingest_wechat.py, which was swapped to
deepseek_model_complete in Task 0c.3 — so the ingestion leg is also on
Deepseek. Full pipeline now uses Deepseek for LLM, Gemini only for embeds.
"""
import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import time
import os
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import kol_config
except ImportError:
    print("ERROR: kol_config.py not found. Create it locally — see docs/KOL_COLDSTART_SETUP.md")
    sys.exit(1)

from spiders.wechat_spider import list_articles_with_digest as list_articles
from spiders.wechat_spider import RATE_LIMIT_SLEEP_ACCOUNTS, RATE_LIMIT_COOLDOWN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

VENV_PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
INGEST_SCRIPT = str(PROJECT_ROOT / "ingest_wechat.py")

SLEEP_BETWEEN_ARTICLES = 60
GEMINI_BATCH_SLEEP = 5.0   # Gemini free tier: 15 RPM
DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"


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


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def _load_hermes_env() -> None:
    """Load env vars from ~/.hermes/.env if not already set."""
    dotenv_paths = [
        Path.home() / ".hermes" / ".env",
        Path("//wsl.localhost/Ubuntu-24.04/home/sztimhdd/.hermes/.env"),
    ]
    dotenv_path = None
    for p in dotenv_paths:
        if p.exists():
            dotenv_path = p
            break
    if dotenv_path is None:
        return
    try:
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and val and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def get_deepseek_api_key() -> str | None:
    """Resolve DeepSeek API key from env var, ~/.hermes/.env, or ~/.hermes/config.yaml."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    # Fallback 1: read from ~/.hermes/.env
    dotenv_path = Path.home() / ".hermes" / ".env"
    if dotenv_path.exists():
        try:
            for line in dotenv_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
        except Exception:
            pass
    # Fallback 2: read from ~/.hermes/config.yaml (skips ${...} template vars)
    config_path = Path.home() / ".hermes" / "config.yaml"
    if config_path.exists() and yaml is not None:
        try:
            cfg = yaml.safe_load(config_path.read_text())
            raw = cfg.get("providers", {}).get("deepseek", {}).get("api_key", "")
            if raw and not raw.startswith("${"):
                return raw
        except Exception:
            pass
    return None


def get_gemini_api_key() -> str | None:
    """Resolve Gemini API key from env var or ~/.hermes/.env."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    dotenv_path = Path.home() / ".hermes" / ".env"
    if dotenv_path.exists():
        try:
            for line in dotenv_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
        except Exception:
            pass
    return None


def _build_filter_prompt(
    titles: list[str],
    topic_filter: list[str] | None,
    exclude_topics: str | None,
    digests: list[str] | None = None,
) -> str:
    """Build the classification prompt for DeepSeek.

    When digests are available, appends each article's WeChat summary
    (first 200 chars) as additional signal for the LLM classifier.
    """
    topic_instruction = ""
    if topic_filter:
        keywords_quoted = ", ".join(f'"{k}"' for k in topic_filter)
        topic_instruction = (
            f"- relevant: true/false — is this article substantially about ANY of: {keywords_quoted}?\n"
        )
    if exclude_topics:
        topic_instruction += (
            f'- excluded: true/false — is this article about any of: {exclude_topics}?\n'
        )

    entries = []
    for i, title in enumerate(titles):
        entry = title
        if digests and i < len(digests) and digests[i]:
            entry = f"{title} [digest: {digests[i][:200]}]"
        entries.append(f"{i}: {entry}")
    articles_text = "\n".join(entries)

    return f"""You are a technical article curator. Classify each article below.

For each article, return a JSON array of objects with:
- index: the 0-based index
- depth_score: 1 (shallow news blurb / brief announcement), 2 (moderate analysis with some detail), 3 (deep technical deep-dive, substantive content)
{topic_instruction}- reason: brief explanation for the depth score (e.g. "news blurb", "deep technical analysis", "event notice")

Articles:
{articles_text}

Return ONLY valid JSON, no other text."""


def _call_deepseek(prompt: str, api_key: str) -> list[dict] | None:
    """Call DeepSeek API and parse JSON response. Returns None on failure."""
    if requests is None:
        logger.warning("requests library not available — cannot call DeepSeek API")
        return None
    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            # Extract JSON from code block
            start = content.find("\n") + 1
            end = content.rfind("```")
            if end > start:
                content = content[start:end].strip()
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        # Handle case where response wraps in {"results": [...]}
        if isinstance(parsed, dict):
            for key in ("results", "articles", "classifications"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
        logger.warning("DeepSeek returned unexpected format: %s", type(parsed))
        return None
    except Exception as exc:
        logger.warning("DeepSeek API call failed: %s", exc)
        return None


def _call_gemini(prompt: str) -> list[dict] | None:
    """Call Gemini API and parse JSON response. Returns None on failure."""
    if genai is None:
        logger.warning("google-genai package not available — cannot call Gemini API")
        return None
    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("No Gemini API key found")
        return None
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception as exc:
        logger.warning("Gemini API call failed: %s", exc)
        return None


def batch_classify_articles(
    articles: list[dict],
    topic_filter: list[str] | None,
    exclude_topics: str | None,
    min_depth: int,
    classifier: str = "deepseek",
) -> tuple[list[dict], list[dict]]:
    """
    Classify all article titles via DeepSeek or Gemini batch API call.
    Returns (passed_articles, filtered_out_articles).
    On API failure, passes all through (fail-open).
    """
    is_gemini = classifier == "gemini"
    if is_gemini:
        api_key = get_gemini_api_key()
        if not api_key:
            logger.warning("No Gemini API key found — passing all articles through")
            return articles, []
    else:
        api_key = get_deepseek_api_key()
        if not api_key:
            logger.warning("No DeepSeek API key found — passing all articles through")
            return articles, []

    # Build title entries with index
    titles = [a.get("title", "(no title)") for a in articles]
    digests = [a.get("digest", "") for a in articles]

    # Split into batches of 200
    batch_size = 200
    all_classifications: list[dict] = []
    for batch_start in range(0, len(titles), batch_size):
        batch_titles = titles[batch_start : batch_start + batch_size]
        batch_digests = digests[batch_start : batch_start + batch_size]
        label = "Gemini" if is_gemini else "DeepSeek"
        logger.info(
            "Classifying articles %d–%d of %d via %s...",
            batch_start + 1,
            min(batch_start + batch_size, len(titles)),
            len(titles),
            label,
        )
        prompt = _build_filter_prompt(batch_titles, topic_filter, exclude_topics, batch_digests)
        if is_gemini:
            result = _call_gemini(prompt)
        else:
            result = _call_deepseek(prompt, api_key)
        if result is None:
            logger.warning("%s API failed — passing all articles through (fail open)", label)
            return articles, []
        all_classifications.extend(result)
        if is_gemini and batch_start + batch_size < len(titles):
            logger.info("  Rate limit: sleeping %.0fs (Gemini free tier: 15 RPM)", GEMINI_BATCH_SLEEP)
            time.sleep(GEMINI_BATCH_SLEEP)

    # Build lookup by index
    cls_by_idx: dict[int, dict] = {}
    for cls in all_classifications:
        idx = cls.get("index")
        if idx is not None:
            cls_by_idx[int(idx)] = cls

    passed: list[dict] = []
    filtered_out: list[dict] = []

    for i, article in enumerate(articles):
        cls = cls_by_idx.get(i, {})
        depth_score = cls.get("depth_score", min_depth)
        if not isinstance(depth_score, int) or depth_score < 1:
            depth_score = min_depth
        relevant = cls.get("relevant", True) if topic_filter else True
        excluded = cls.get("excluded", False) if exclude_topics else False
        reason = cls.get("reason", "")

        filter_reasons: list[str] = []
        if topic_filter and not relevant:
            keywords_str = ", ".join(topic_filter)
            filter_reasons.append(f"off-topic (not about any of: {keywords_str})")
        if exclude_topics and excluded:
            filter_reasons.append(f"excluded topic ({reason or exclude_topics})")
        if depth_score < min_depth:
            reason_text = reason or "shallow"
            filter_reasons.append(f"depth too low ({reason_text})")

        if filter_reasons:
            filtered_out.append({
                **article,
                "filter_reason": "; ".join(filter_reasons),
                "depth_score": depth_score,
            })
        else:
            article["depth_score"] = depth_score
            passed.append(article)

    return passed, filtered_out


def print_filter_summary(passed: list[dict], filtered_out: list[dict]) -> None:
    """Print a summary table of filter results."""
    # Count filter reasons
    depth_low = 0
    off_topic = 0
    excluded_topic = 0
    other = 0

    for art in filtered_out:
        reason = art.get("filter_reason", "")
        if "depth too low" in reason:
            depth_low += 1
        elif "off-topic" in reason:
            off_topic += 1
        elif "excluded topic" in reason:
            excluded_topic += 1
        else:
            other += 1

    lines = [f"=== Filter Results ===", f"Pass: {len(passed)} articles"]
    if filtered_out:
        lines.append("Filtered out:")
        if depth_low:
            lines.append(f"  {depth_low} - depth too low")
        if off_topic:
            lines.append(f"  {off_topic} - off-topic")
        if excluded_topic:
            lines.append(f"  {excluded_topic} - excluded topic")
        if other:
            lines.append(f"  {other} - other")
        lines.append("  ---")
        lines.append(f"  {len(filtered_out)} total skipped")
    print("\n".join(lines))


def run(days_back: int, max_articles: int, dry_run: bool, **kwargs) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary: list[dict] = []
    processed = 0

    _load_hermes_env()

    topic_filter = kwargs.get("topic_filter")  # list[str] | None after main() split
    exclude_topics = kwargs.get("exclude_topics")
    min_depth = kwargs.get("min_depth", 2)
    account_filter = kwargs.get("account_filter")
    classifier = kwargs.get("classifier", "deepseek")

    # Phase 1: Scan accounts (with 2s throttle between accounts)
    all_accounts = list(kol_config.FAKEIDS.items())
    if account_filter:
        accounts = [(name, fid) for name, fid in all_accounts if name == account_filter]
        if not accounts:
            logger.error("Account '%s' not found in kol_config. Available: %s", account_filter, [n for n, _ in all_accounts])
            return
    else:
        accounts = all_accounts
    total_accounts = len(accounts)
    all_articles: list[dict] = []

    for i, (account_name, fakeid) in enumerate(accounts, 1):
        logger.info("=== Account %d/%d: %s (fakeid=%s) ===", i, total_accounts, account_name, fakeid)

        try:
            articles = list_articles(
                token=kol_config.TOKEN,
                cookie=kol_config.COOKIE,
                fakeid=fakeid,
                days_back=days_back,
                max_articles=max_articles,
            )
        except Exception as exc:
            err_str = str(exc)
            logger.error("Failed to list articles for %s: %s", account_name, exc)
            summary.append({"account": account_name, "error": err_str})
            if "rate limit" in err_str.lower() or "freq control" in err_str.lower() or "200013" in err_str:
                logger.info("  Cooling down %.0fs (WeChat rate limit hit)...", RATE_LIMIT_COOLDOWN)
                time.sleep(RATE_LIMIT_COOLDOWN)
            continue

        logger.info("Found %d articles for %s", len(articles), account_name)
        for article in articles:
            article["account"] = account_name
            all_articles.append(article)

        if i < total_accounts:
            time.sleep(RATE_LIMIT_SLEEP_ACCOUNTS)

    # Phase 2: Filter
    scanning_active = bool(topic_filter or exclude_topics)
    if scanning_active:
        logger.info(
            "--- Filtering %d articles (topic=%s, exclude=%s, min_depth=%d) ---",
            len(all_articles),
            topic_filter,
            exclude_topics,
            min_depth,
        )
        passed, filtered_out = batch_classify_articles(
            all_articles, topic_filter, exclude_topics, min_depth, classifier=classifier,
        )
        print_filter_summary(passed, filtered_out)
    else:
        passed = all_articles
        filtered_out = []

    # Phase 3: Ingest survivors
    total = len(passed)
    for i, article in enumerate(passed, 1):
        title = article.get("title", "(no title)")
        url = article.get("url", "")
        account_name = article.get("account", "?")

        logger.info("[%d/%d] [%s] %s", i, total, account_name, title)

        if not url:
            logger.warning("  Skipping — no URL")
            summary.append({
                "account": account_name,
                "title": title,
                "url": "",
                "status": "skipped_no_url",
            })
            continue

        success = ingest_article(url, dry_run)
        summary.append({
            "account": account_name,
            "title": title,
            "url": url,
            "status": "dry_run" if dry_run else ("ok" if success else "failed"),
        })

        processed += 1
        if not dry_run and processed < total:
            logger.info("  Sleeping %ds (rate limit: 15 RPM free tier)...", SLEEP_BETWEEN_ARTICLES)
            time.sleep(SLEEP_BETWEEN_ARTICLES)

    # Add filtered-out articles to summary with their filter status
    for art in filtered_out:
        summary.append({
            "account": art.get("account", "?"),
            "title": art.get("title", "(no title)"),
            "url": art.get("url", ""),
            "status": "filtered",
            "filter_reason": art.get("filter_reason", ""),
            "depth_score": art.get("depth_score"),
        })

    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"coldstart_run_{timestamp}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Summary written to %s", out_path)

    ok = sum(1 for r in summary if r.get("status") in ("ok", "dry_run"))
    fail = sum(1 for r in summary if r.get("status") == "failed")
    filt = sum(1 for r in summary if r.get("status") == "filtered")
    logger.info("Done — %d ok, %d failed, %d filtered, %d skipped", ok, fail, filt, len(summary) - ok - fail - filt)


def ingest_from_db(topic: str | list[str], min_depth: int, dry_run: bool) -> None:
    """Ingest articles that passed classification for a topic (or list of topics). Reads from kol_scan.db."""
    topics = [topic] if isinstance(topic, str) else topic

    if not DB_PATH.exists():
        logger.error("DB not found: %s. Run batch_scan_kol.py first.", DB_PATH)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id)
        )
    """)
    conn.commit()

    placeholders = ",".join("?" for _ in topics)
    rows = conn.execute(f"""
        SELECT a.id, a.title, a.url, acc.name, c.depth_score
        FROM articles a
        JOIN accounts acc ON a.account_id = acc.id
        JOIN classifications c ON a.id = c.article_id
        WHERE c.topic IN ({placeholders}) AND c.relevant = 1 AND c.depth_score >= ?
          AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
        ORDER BY c.depth_score DESC, a.id
    """, (*topics, min_depth)).fetchall()

    if not rows:
        logger.info("No passed articles found for topics %s (min_depth=%d)", topics, min_depth)
        conn.close()
        return

    logger.info("%d articles to ingest for topics %s", len(rows), topics)
    processed = 0
    for i, (art_id, title, url, account, depth) in enumerate(rows, 1):
        logger.info("[%d/%d] [%s] (depth=%s) %s", i, len(rows), account, depth, title)

        if not url:
            logger.warning("  Skipping — no URL")
            conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')", (art_id,))
            conn.commit()
            continue

        success = ingest_article(url, dry_run)
        status = "dry_run" if dry_run else ("ok" if success else "failed")
        conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, ?)", (art_id, status))
        conn.commit()

        processed += 1
        if not dry_run and processed < len(rows):
            logger.info("  Sleeping %ds (Gemini Flash 15 RPM limit)...", SLEEP_BETWEEN_ARTICLES)
            time.sleep(SLEEP_BETWEEN_ARTICLES)

    ok = sum(1 for r in rows if True)  # count is tracked via status in DB
    logger.info("Done — %d articles processed", len(rows))
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest WeChat KOL articles into OmniGraph-Vault")
    parser.add_argument("--dry-run", action="store_true", help="List articles without ingesting")
    parser.add_argument("--days-back", type=int, default=90, help="How many days back to fetch (default: 90)")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles per account (default: 50)")
    parser.add_argument("--topic-filter", type=str, default=None, help="Required topic to include (e.g. 'AI agents')")
    parser.add_argument("--exclude-topics", type=str, default=None, help="Comma-separated topics to exclude (e.g. 'OpenClaw,crypto')")
    parser.add_argument("--min-depth", type=int, default=2, choices=[1, 2, 3], help="Minimum depth score 1-3 (default: 2)")
    parser.add_argument("--account", type=str, default=None, help="Only process this specific account name")
    parser.add_argument("--classifier", type=str, default="deepseek", choices=["deepseek", "gemini"],
                        help="Classifier model: deepseek (default) or gemini")
    parser.add_argument("--from-db", action="store_true",
                        help="Ingest articles already classified in kol_scan.db (requires --topic-filter)")
    args = parser.parse_args()

    # Convert comma-separated string to list; strip whitespace; drop empty strings
    topic_keywords: list[str] | None = None
    if args.topic_filter:
        topic_keywords = [k.strip() for k in args.topic_filter.split(",") if k.strip()]
        if not topic_keywords:
            topic_keywords = None

    if args.from_db:
        if not topic_keywords:
            logger.error("--topic-filter is required with --from-db")
            sys.exit(1)
        ingest_from_db(topic_keywords, args.min_depth, args.dry_run)
    else:
        run(
            days_back=args.days_back,
            max_articles=args.max_articles,
            dry_run=args.dry_run,
            topic_filter=topic_keywords,
            exclude_topics=args.exclude_topics,
            min_depth=args.min_depth,
            account_filter=args.account,
            classifier=args.classifier,
        )


if __name__ == "__main__":
    main()
