"""
Batch ingestion bridge for WeChat KOL cold-start seeding.

Usage:
    python batch_ingest_from_spider.py [--dry-run] [--days-back N] [--max-articles N]
                                       [--topic-filter TOPIC] [--exclude-topics TOPICS]
                                       [--min-depth N]

Reads accounts from kol_config.py (local only, gitignored).
For each account, lists recent articles via WeChat MP API.
If --topic-filter or --exclude-topics is set, classifies all titles via
DeepSeek API (depth_score 1-3, relevance, exclusion) and filters before ingesting.
For each passing article, calls: python ingest_wechat.py "<url>"
Writes summary JSON to data/coldstart_run_{timestamp}.json
"""
import argparse
import json
import logging
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

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import kol_config
except ImportError:
    print("ERROR: kol_config.py not found. Create it locally — see docs/KOL_COLDSTART_SETUP.md")
    sys.exit(1)

from spiders.wechat_spider import list_articles_with_digest as list_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

VENV_PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
INGEST_SCRIPT = str(PROJECT_ROOT / "ingest_wechat.py")

SLEEP_BETWEEN_ARTICLES = 60


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


def get_deepseek_api_key() -> str | None:
    """Resolve DeepSeek API key from env var or ~/.hermes/config.yaml."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
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


def _build_filter_prompt(
    titles: list[str],
    topic_filter: str | None,
    exclude_topics: str | None,
    digests: list[str] | None = None,
) -> str:
    """Build the classification prompt for DeepSeek.

    When digests are available, appends each article's WeChat summary
    (first 200 chars) as additional signal for the LLM classifier.
    """
    topic_instruction = ""
    if topic_filter:
        topic_instruction = (
            f'- relevant: true/false — is this article substantially about "{topic_filter}"?\n'
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


def batch_classify_articles(
    articles: list[dict],
    topic_filter: str | None,
    exclude_topics: str | None,
    min_depth: int,
) -> tuple[list[dict], list[dict]]:
    """
    Classify all article titles via DeepSeek batch API call.
    Returns (passed_articles, filtered_out_articles).
    On API failure, passes all through (fail-open).
    """
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
        logger.info(
            "Classifying articles %d–%d of %d via DeepSeek...",
            batch_start + 1,
            min(batch_start + batch_size, len(titles)),
            len(titles),
        )
        prompt = _build_filter_prompt(batch_titles, topic_filter, exclude_topics, batch_digests)
        result = _call_deepseek(prompt, api_key)
        if result is None:
            logger.warning("DeepSeek API failed — passing all articles through (fail open)")
            return articles, []
        all_classifications.extend(result)

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
            filter_reasons.append(f"off-topic (not about {topic_filter})")
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

    topic_filter = kwargs.get("topic_filter")
    exclude_topics = kwargs.get("exclude_topics")
    min_depth = kwargs.get("min_depth", 2)

    # Phase 1: Scan all accounts (with 2s throttle between accounts)
    accounts = list(kol_config.FAKEIDS.items())
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
            logger.error("Failed to list articles for %s: %s", account_name, exc)
            summary.append({"account": account_name, "error": str(exc)})
            continue

        logger.info("Found %d articles for %s", len(articles), account_name)
        for article in articles:
            article["account"] = account_name
            all_articles.append(article)

        if i < total_accounts:
            time.sleep(2.0)

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
            all_articles, topic_filter, exclude_topics, min_depth,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest WeChat KOL articles into OmniGraph-Vault")
    parser.add_argument("--dry-run", action="store_true", help="List articles without ingesting")
    parser.add_argument("--days-back", type=int, default=90, help="How many days back to fetch (default: 90)")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles per account (default: 50)")
    parser.add_argument("--topic-filter", type=str, default=None, help="Required topic to include (e.g. 'AI agents')")
    parser.add_argument("--exclude-topics", type=str, default=None, help="Comma-separated topics to exclude (e.g. 'OpenClaw,crypto')")
    parser.add_argument("--min-depth", type=int, default=2, choices=[1, 2, 3], help="Minimum depth score 1-3 (default: 2)")
    args = parser.parse_args()

    run(
        days_back=args.days_back,
        max_articles=args.max_articles,
        dry_run=args.dry_run,
        topic_filter=args.topic_filter,
        exclude_topics=args.exclude_topics,
        min_depth=args.min_depth,
    )


if __name__ == "__main__":
    main()
