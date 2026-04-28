"""
Topic-driven batch KOL ingestion pipeline.

Usage:
    python batchkol_topic.py "https://github.com/nousresearch/hermes" --dry-run
    python batchkol_topic.py "OpenClaw agent framework" --max 10

Pipeline (3 passes):
    Pass 1 — Scan all 20 KOL accounts -> collect (title, digest, url, account)
    Pass 2 — Batch all titles+digests -> classifier (DeepSeek or Gemini) -> returns qualifying URLs
    Pass 3 — Ingest survivors at 1 article/min (enforces Gemini Flash 15 RPM limit)

Rate limits enforced:
    - WeChat MP API: 2s sleep between accounts during scan
    - Gemini Flash: exactly 1 ingestion per 60s minimum (subprocess per article)
    - Classifier: 5s sleep before Gemini classification (15 RPM free tier)
    - DeepSeek: generous limits, default classifier
    - Apify: credit check before batch, stop if free tier nearly exhausted

NOTE: The old batchingestkolmvp.py pattern (hardcoded article list, no topic filter,
per-article LLM spend) is deprecated. Use this script or batch_ingest_from_spider.py.

Plan 05-00c Task 0c.4: default classifier is 'deepseek' (see :576). This script
routes to the DeepSeek chat completions endpoint directly for classification.
The ingestion sub-step (Pass 3) subprocesses out to ingest_wechat.py, which
was swapped to deepseek_model_complete in Task 0c.3 — so the FULL pipeline
(classify + ingest) now uses only Deepseek for LLM, Gemini only for embeds.
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import load_env
load_env()

try:
    import requests
except ImportError:
    requests = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    import kol_config
except ImportError:
    print("ERROR: kol_config.py not found. Create it locally — see docs/KOL_COLDSTART_SETUP.md")
    sys.exit(1)

from kol_registry import list_accounts
from spiders.wechat_spider import list_articles_with_digest as list_articles
from spiders.wechat_spider import RATE_LIMIT_SLEEP_ACCOUNTS, RATE_LIMIT_COOLDOWN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batchkol_topic")

GEMINI_RPM_LIMIT = 15
SLEEP_BETWEEN_INGESTIONS = 60
MAX_APIFY_FREE_CREDITS = 100
APIFY_LOW_CREDIT_THRESHOLD = 5

GITHUB_REPO_RE = re.compile(r"github\.com/([^/]+/[^/\s?#]+)")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
GEMINI_CLASSIFY_SLEEP = 5.0   # Gemini free tier: 15 RPM


def get_python_exe() -> str:
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    venv_win = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_win.exists():
        return str(venv_win)
    return sys.executable


def resolve_topic(raw_topic: str) -> str:
    """Resolve topic string — GitHub URL or free-text."""
    m = GITHUB_REPO_RE.search(raw_topic)
    if not m:
        return raw_topic.strip()
    if requests is None:
        logger.warning("requests unavailable — using raw repo name as topic")
        return m.group(1)

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{m.group(1)}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("GitHub API returned %d — using repo name as topic", resp.status_code)
            return m.group(1)
        data = resp.json()
        description = data.get("description", "")
        name = data.get("full_name", m.group(1))
        topics = data.get("topics", [])
        if description:
            topic = f"{name}: {description}"
        else:
            topic = name
        if topics:
            topic += f" ({', '.join(topics[:5])})"
        logger.info("Resolved GitHub topic: %s", topic)
        return topic
    except Exception as exc:
        logger.warning("GitHub API call failed: %s — using repo name as topic", exc)
        return m.group(1)


def check_apify_credits() -> int | None:
    """Check remaining Apify credits. Returns None if check fails."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        return None
    if requests is None:
        return None
    try:
        resp = requests.get(
            "https://api.apify.com/v2/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        usage = data.get("data", {}).get("usage", {})
        monthly = usage.get("monthly", {})
        used = monthly.get("currentMonthUsageTotalUsd", 0)
        limit = monthly.get("monthlyUsageLimitUsd", MAX_APIFY_FREE_CREDITS)
        remaining = limit - used
        logger.info("Apify credits: %.2f USD used, %.2f USD remaining (limit: %.2f)", used, remaining, limit)
        return int(remaining)
    except Exception as exc:
        logger.warning("Apify credit check failed: %s", exc)
        return None


def ingest_article(url: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True
    ingest_script = str(PROJECT_ROOT / "ingest_wechat.py")
    result = subprocess.run(
        [get_python_exe(), ingest_script, url],
        capture_output=False,
        timeout=300,
    )
    return result.returncode == 0


def _get_deepseek_api_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    config_path = Path.home() / ".hermes" / "config.yaml"
    if config_path.exists():
        try:
            import yaml as _yaml
            cfg = _yaml.safe_load(config_path.read_text())
            raw = cfg.get("providers", {}).get("deepseek", {}).get("api_key", "")
            if raw and not raw.startswith("${"):
                return raw
        except Exception:
            pass
    return None


def _get_gemini_api_key() -> str | None:
    """Gemini API key is already in os.environ via config.load_env()."""
    return os.environ.get("GEMINI_API_KEY")


def _call_gemini(prompt: str) -> list[dict] | None:
    """Call Gemini API and parse JSON response. Returns None on failure."""
    if genai is None:
        logger.warning("google-genai package not available — cannot call Gemini API")
        return None
    api_key = _get_gemini_api_key()
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


def classify_articles(
    articles: list[dict],
    topic_filter: str,
    min_depth: int = 2,
    classifier: str = "deepseek",
) -> tuple[list[dict], list[dict]]:
    """
    Batch-classify articles via DeepSeek or Gemini. Returns (passed, filtered_out).
    Falls back to passing all if classifier unavailable or fails.
    """
    if classifier == "gemini":
        logger.info("  Rate limit: sleeping %.0fs (Gemini free tier: 15 RPM)", GEMINI_CLASSIFY_SLEEP)
        time.sleep(GEMINI_CLASSIFY_SLEEP)
    else:
        api_key = _get_deepseek_api_key()
        if not api_key:
            logger.warning("No DeepSeek API key — passing all articles through unfiltered")
            return articles, []

    if not articles:
        return [], []

    titles = [a.get("title", "(no title)") for a in articles]
    digests = [a.get("digest", "") for a in articles]

    entries = []
    for i, (t, d) in enumerate(zip(titles, digests)):
        prefix = t
        if d:
            prefix = f"{t} [digest: {d[:200]}]"
        entries.append(f"{i}: {prefix}")

    prompt = f"""You are a technical article curator. Classify each article below.

For each article, return a JSON array of objects with:
- index: the 0-based index
- depth_score: 1 (shallow news blurb / brief announcement), 2 (moderate analysis with some detail), 3 (deep technical deep-dive, substantive content)
- relevant: true/false — is this article substantially about "{topic_filter}"?
- reason: brief explanation (e.g. "news blurb", "deep technical analysis", "event notice", "off-topic")

Articles:
{chr(10).join(entries)}

Return ONLY valid JSON, no other text."""

    if classifier == "gemini":
        parsed = _call_gemini(prompt)
        if parsed is None:
            logger.warning("Gemini classification failed — passing all through")
            return articles, []
    else:
        if requests is None:
            logger.warning("requests unavailable — passing all articles through")
            return articles, []

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
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                start = content.find("\n") + 1
                end = content.rfind("```")
                if end > start:
                    content = content[start:end].strip()
            parsed = json.loads(content)
        except Exception as exc:
            logger.warning("DeepSeek classification failed: %s — passing all through", exc)
            return articles, []

    # Shared JSON parsing and filtering (Gemini and DeepSeek converge here)
    if isinstance(parsed, dict):
        for key in ("results", "articles", "classifications"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        logger.warning("Classifier returned unexpected format — passing all through")
        return articles, []

    cls_by_idx = {int(c["index"]): c for c in parsed if "index" in c}

    passed = []
    filtered_out = []
    for i, article in enumerate(articles):
        cls = cls_by_idx.get(i, {})
        depth_score = cls.get("depth_score", min_depth)
        if not isinstance(depth_score, int) or depth_score < 1:
            depth_score = min_depth
        relevant = cls.get("relevant", True)
        reason = cls.get("reason", "")

        skip_reasons = []
        if not relevant:
            skip_reasons.append(f"off-topic ({reason or 'not about ' + topic_filter})")
        if depth_score < min_depth:
            skip_reasons.append(f"depth too low ({reason or 'shallow'})")

        if skip_reasons:
            filtered_out.append({
                **article,
                "filter_reason": "; ".join(skip_reasons),
                "depth_score": depth_score,
            })
        else:
            article["depth_score"] = depth_score
            passed.append(article)

    return passed, filtered_out


def print_dry_run_report(passed: list[dict], filtered_out: list[dict]) -> None:
    print(f"\n=== Topic Filter Results ===")
    print(f"Passed: {len(passed)} articles")

    if filtered_out:
        reasons: dict[str, int] = {}
        for art in filtered_out:
            r = art.get("filter_reason", "unknown")
            reasons[r] = reasons.get(r, 0) + 1
        print(f"Filtered out: {len(filtered_out)} articles")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {count} — {reason}")

    if passed:
        print(f"\n=== Would Ingest ({len(passed)} articles) ===")
        for i, art in enumerate(passed, 1):
            depth = art.get("depth_score", "?")
            print(f"  {i}. [{art.get('account_name', '?')}] {art.get('title', '(no title)')}  (depth={depth})")
        mins = len(passed)
        print(f"\nEstimated time: ~{mins} min ({mins} x 60s rate limit)")

    print()


def run(topic: str, max_ingest: int, days_back: int, max_per_account: int,
        min_depth: int, dry_run: bool, classifier: str = "deepseek") -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary: list[dict] = []

    topic_filter = resolve_topic(topic)
    logger.info("Topic: %s", topic_filter)

    accounts = list_accounts()
    if not accounts:
        logger.error("No accounts found in kol_registry")
        sys.exit(1)

    logger.info("=== Pass 1: Scanning %d KOL accounts ===", len(accounts))

    all_articles: list[dict] = []
    consecutive_rate_limits = 0
    retry_accounts: list[dict] = []

    for i, acc in enumerate(accounts, 1):
        name = acc["name"]
        fakeid = acc.get("fakeid")
        if not fakeid:
            logger.warning("  Skipping %s — no fakeid", name)
            continue

        logger.info("  Account %d/%d: %s", i, len(accounts), name)
        try:
            articles = list_articles(
                token=kol_config.TOKEN,
                cookie=kol_config.COOKIE,
                fakeid=fakeid,
                days_back=days_back,
                max_articles=max_per_account,
            )
        except Exception as exc:
            err_str = str(exc)
            logger.error("  Failed: %s", err_str)
            if "rate limit" in err_str.lower() or "freq control" in err_str.lower():
                consecutive_rate_limits += 1
                retry_accounts.append(acc)
                logger.info("  Cooling down %.0fs (rate limit hit, %d consecutive)...",
                          RATE_LIMIT_COOLDOWN, consecutive_rate_limits)
                time.sleep(RATE_LIMIT_COOLDOWN)
                consecutive_rate_limits = 0
            continue

        for art in articles:
            art["account_name"] = name
            art["fakeid"] = fakeid
        all_articles.extend(articles)
        logger.info("    Found %d articles", len(articles))
        consecutive_rate_limits = 0

        if i < len(accounts):
            time.sleep(RATE_LIMIT_SLEEP_ACCOUNTS)

    for acc in retry_accounts:
        name = acc["name"]
        fakeid = acc.get("fakeid")
        logger.info("  Retry: %s (after cooldown)", name)
        try:
            articles = list_articles(
                token=kol_config.TOKEN,
                cookie=kol_config.COOKIE,
                fakeid=fakeid,
                days_back=days_back,
                max_articles=max_per_account,
            )
            for art in articles:
                art["account_name"] = name
                art["fakeid"] = fakeid
            all_articles.extend(articles)
            logger.info("    Retry OK: %d articles", len(articles))
        except Exception as exc:
            logger.error("  Retry failed: %s", exc)

    logger.info("Scan complete: %d articles from %d accounts\n", len(all_articles), len(accounts))

    if not all_articles:
        logger.info("No articles found.")
        return

    logger.info("=== Pass 2: Classifying %d articles via %s ===", len(all_articles), classifier.title())
    passed, filtered_out = classify_articles(all_articles, topic_filter, min_depth, classifier=classifier)

    logger.info("Classification: %d passed, %d filtered out", len(passed), len(filtered_out))

    if max_ingest > 0 and len(passed) > max_ingest:
        logger.info("Capping to --max %d articles (sorted by depth_score descending)", max_ingest)
        passed.sort(key=lambda a: a.get("depth_score", 0), reverse=True)
        trimmed = passed[:max_ingest]
        over_limit = passed[max_ingest:]
        for art in over_limit:
            art["filter_reason"] = "over max limit"
            filtered_out.append(art)
        passed = trimmed

    if dry_run:
        print_dry_run_report(passed, filtered_out)
        for art in passed:
            summary.append({
                "account": art.get("account_name", "?"),
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "depth_score": art.get("depth_score"),
                "status": "dry_run",
            })
        for art in filtered_out:
            summary.append({
                "account": art.get("account_name", "?"),
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "depth_score": art.get("depth_score"),
                "status": "filtered",
                "filter_reason": art.get("filter_reason", ""),
            })
    else:
        apify_credits = check_apify_credits()
        if apify_credits is not None and apify_credits <= 0:
            logger.error("Apify credits exhausted (%d). Aborting.", apify_credits)
            sys.exit(1)
        if apify_credits is not None and apify_credits <= APIFY_LOW_CREDIT_THRESHOLD:
            logger.warning(
                "Low Apify credits (%d/%d). Ingestion stopped early to conserve credits.",
                apify_credits, APIFY_LOW_CREDIT_THRESHOLD + 1,
            )
            sys.exit(1)

        logger.info("\n=== Pass 3: Ingesting %d articles (1/min rate limit) ===", len(passed))
        logger.info("Estimated time: ~%d min\n", len(passed))

        processed = 0
        for i, article in enumerate(passed, 1):
            title = article.get("title", "(no title)")
            url = article.get("url", "")
            account = article.get("account_name", "?")
            depth = article.get("depth_score", "?")

            logger.info("[%d/%d] [%s] (depth=%s) %s", i, len(passed), account, depth, title)

            if not url:
                logger.warning("  Skipping — no URL")
                summary.append({
                    "account": account, "title": title, "url": "",
                    "depth_score": depth, "status": "skipped_no_url",
                })
                continue

            success = ingest_article(url, dry_run=False)
            summary.append({
                "account": account,
                "title": title,
                "url": url,
                "depth_score": depth,
                "status": "ok" if success else "failed",
            })

            processed += 1
            if processed < len(passed):
                logger.info("  Sleeping %ds (Gemini Flash 15 RPM limit)...", SLEEP_BETWEEN_INGESTIONS)
                time.sleep(SLEEP_BETWEEN_INGESTIONS)

            new_credits = check_apify_credits()
            if new_credits is not None and new_credits <= APIFY_LOW_CREDIT_THRESHOLD:
                logger.warning(
                    "Apify credits low (%d). Stopping ingestion early.", new_credits,
                )
                for remaining in passed[i:]:
                    summary.append({
                        "account": remaining.get("account_name", "?"),
                        "title": remaining.get("title", ""),
                        "url": remaining.get("url", ""),
                        "depth_score": remaining.get("depth_score"),
                        "status": "skipped_apify_low_credit",
                    })
                break

        for art in filtered_out:
            summary.append({
                "account": art.get("account_name", "?"),
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "depth_score": art.get("depth_score"),
                "status": "filtered",
                "filter_reason": art.get("filter_reason", ""),
            })

    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"batchkol_topic_{timestamp}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Summary written to %s", out_path)

    ok = sum(1 for r in summary if r.get("status") in ("ok", "dry_run"))
    fail = sum(1 for r in summary if r.get("status") == "failed")
    filt = sum(1 for r in summary if r.get("status") == "filtered")
    skip = len(summary) - ok - fail - filt
    logger.info("Done — %d ok, %d failed, %d filtered, %d skipped", ok, fail, filt, skip)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Topic-driven batch KOL ingestion into OmniGraph-Vault",
    )
    parser.add_argument(
        "topic", type=str,
        help="Topic query or GitHub URL (e.g. 'OpenClaw agent framework' or https://github.com/nousresearch/hermes)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan and classify, but do not ingest")
    parser.add_argument("--max", type=int, default=10, dest="max_ingest",
                        help="Max articles to ingest (default: 10)")
    parser.add_argument("--days-back", type=int, default=90,
                        help="How many days back to scan (default: 90)")
    parser.add_argument("--max-per-account", type=int, default=20,
                        help="Max articles per account to scan (default: 20)")
    parser.add_argument("--min-depth", type=int, default=2, choices=[1, 2, 3],
                        help="Minimum depth score 1-3 (default: 2)")
    parser.add_argument("--classifier", type=str, default="deepseek", choices=["deepseek", "gemini"],
                        help="Classifier model: deepseek (default) or gemini")
    args = parser.parse_args()

    run(
        topic=args.topic,
        max_ingest=args.max_ingest,
        days_back=args.days_back,
        max_per_account=args.max_per_account,
        min_depth=args.min_depth,
        dry_run=args.dry_run,
        classifier=args.classifier,
    )


if __name__ == "__main__":
    main()
