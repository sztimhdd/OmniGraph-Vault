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
import asyncio
import json
import logging
import sqlite3
import sys
import time
import os

# D-09.01 (TIMEOUT-01): LightRAG reads LLM_TIMEOUT at dataclass-definition time
# (lightrag/lightrag.py:432: `default=int(os.getenv("LLM_TIMEOUT", 180))`).
# Must be set BEFORE any import chain that transitively loads LightRAG. The
# `from ingest_wechat import get_rag` late-imports below execute AFTER module
# init, so putting this at module top guarantees the env var is visible when
# LightRAG's @dataclass fields evaluate their defaults.
# setdefault preserves any explicit override from shell env or ~/.hermes/.env.
os.environ.setdefault("LLM_TIMEOUT", "600")

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
    from google.genai import types as genai_types
except ImportError:
    genai_types = None

from lib import INGESTION_LLM, generate_sync
from lib.checkpoint import get_article_hash, has_stage

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

SLEEP_BETWEEN_ARTICLES = 10  # Phase 5-00c: DeepSeek LLM + 2-key Gemini embedding rotation (not 15 RPM Gemini)
GEMINI_BATCH_SLEEP = 2.0   # DeepSeek: no RPM concern; light pause for API stability
DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"

# D-10.09: aggregate deadline for draining pending Vision worker tasks before
# rag.finalize_storages(). 120s covers the worst-case backlog of ~30 articles
# @ ~4s/article describe time. Tests override this to a small value via monkeypatch.
VISION_DRAIN_TIMEOUT = 120.0


async def _drain_pending_vision_tasks() -> None:
    """Drain Vision worker tasks lingering on the event loop (D-10.09 / ARCH-04).

    Called from the `finally:` block of run() and ingest_from_db() BEFORE
    rag.finalize_storages(). Without this, sub-doc ainsert may race with the
    storage-flush and be lost.

    Tasks still pending after VISION_DRAIN_TIMEOUT are cancelled; the caller
    then proceeds to finalize_storages regardless. `asyncio.all_tasks()`
    returns every task on the loop — the filter excludes the current coroutine
    and any already-done tasks, leaving only the fire-and-forget Vision workers
    spawned by ingest_wechat.ingest_article.
    """
    pending = [
        t
        for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    if not pending:
        return
    logger.info(
        "Draining %d pending Vision task(s) (%.0fs deadline; D-10.09)...",
        len(pending),
        VISION_DRAIN_TIMEOUT,
    )
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=VISION_DRAIN_TIMEOUT,
        )
        logger.info("Vision tasks drained cleanly")
    except asyncio.TimeoutError:
        still_pending = [t for t in pending if not t.done()]
        logger.warning(
            "Vision drain timeout — %d/%d task(s) still pending (cancelling)",
            len(still_pending),
            len(pending),
        )
        for t in still_pending:
            t.cancel()
        # Give cancelled tasks a brief moment to process CancelledError so
        # their observable side effects (log lines, test assertions) complete.
        if still_pending:
            await asyncio.gather(*still_pending, return_exceptions=True)


# D-09.03 (TIMEOUT-03): per-article outer budget formula.
# Inner LightRAG per-chunk LLM timeout is LLM_TIMEOUT=600 (D-09.01) — set via
# setdefault at top of file.
_CHUNK_SIZE_CHARS = 4800        # ~1200 tokens × 4 chars/token; LightRAG default chunk size
_BASE_BUDGET_S = 120
_PER_CHUNK_S = 30
_SINGLE_CHUNK_FLOOR_S = 900     # guarantees one slow 800s DeepSeek chunk completes


def _compute_article_budget_s(full_content: str) -> int:
    """Compute outer asyncio.wait_for budget for an article (D-09.03).

    Two-layer timeout semantics:
      - Outer (this budget): governs whole-article ingest call.
      - Inner (LLM_TIMEOUT=600 via D-09.01): governs each per-chunk LLM call.

    Formula: max(BASE + PER_CHUNK * chunk_count, FLOOR).

    chunk_count is derived from ``len(full_content) // _CHUNK_SIZE_CHARS``
    (floor, minimum 1). Linear scaling matters more than exact token math;
    ~4800 chars ≈ 1200 tokens ≈ LightRAG's default chunk_token_size.
    """
    chunk_count = max(1, len(full_content) // _CHUNK_SIZE_CHARS)
    return max(_BASE_BUDGET_S + _PER_CHUNK_S * chunk_count, _SINGLE_CHUNK_FLOOR_S)


async def ingest_article(url: str, dry_run: bool, rag) -> bool:
    """Ingest a single URL in-process against the shared LightRAG instance.

    Phase 5-00b refactor: replaces subprocess-per-article pattern. Shared ``rag``
    (created once by the caller) eliminates 15-30s per-article LightRAG init
    overhead. Per-article try/except isolates failures — one bad article never
    kills the batch. ``asyncio.wait_for`` replaces subprocess timeout semantics;
    CancelledError propagates cleanly to in-flight HTTP clients.

    D-09.05 (STATE-02): on ``asyncio.TimeoutError``, roll back partial state via
    ``rag.adelete_by_doc_id(doc_id)``. ``doc_id`` is computed inside
    ``ingest_wechat`` BEFORE ``ainsert`` starts and exposed via
    ``ingest_wechat.get_pending_doc_id()``. Rollback failure is logged, not
    raised — the orchestrator returns ``False`` cleanly in all error paths.
    """
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True

    import hashlib
    import ingest_wechat

    # Compute the same article_hash ingest_wechat uses to track doc_id.
    # Kept here so the rollback handler doesn't need to inspect ingest_wechat
    # internals on the error path.
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]

    try:
        # D-09.03: 900s floor covers a worst-case single-chunk 800s DeepSeek call.
        # When Plan 09-01 / Phase 10 decouple scrape from ingest, the inner
        # rag.ainsert wrap can use the chunk-count-aware budget via
        # _compute_article_budget_s(full_content). For now, the floor suffices
        # because `url` is all we have here — full_content is unknown until
        # after scrape completes inside ingest_wechat.ingest_article.
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, rag=rag),
            timeout=_SINGLE_CHUNK_FLOOR_S,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT (%ds) — skipping: %s", _SINGLE_CHUNK_FLOOR_S, url[:80])
        # D-09.05: rollback partial state if ainsert registered a doc_id.
        doc_id = ingest_wechat.get_pending_doc_id(article_hash)
        if doc_id and rag is not None:
            try:
                logger.info("  Rolling back partial doc_id=%s (STATE-02)", doc_id)
                await rag.adelete_by_doc_id(doc_id)
                logger.info("  Rollback complete — graph consistent (STATE-02)")
            except Exception as rb_exc:
                logger.error(
                    "  Rollback FAILED for doc_id=%s: %s — graph may be inconsistent",
                    doc_id,
                    rb_exc,
                )
            finally:
                ingest_wechat._clear_pending_doc_id(article_hash)
        return False
    except Exception as exc:
        logger.warning("Ingest failed (%s): %s — skipping: %s",
                       exc.__class__.__name__, exc, url[:80])
        return False


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def _ensure_fullbody_columns(conn: sqlite3.Connection) -> None:
    """Additive schema migration for Phase 10 plan 10-00 (D-10.01 + D-10.04).

    Adds ``articles.body`` and ``classifications.{depth, topics, rationale}``
    columns if missing. Idempotent — safe to call on every run-start.

    Pattern: per-column PRAGMA table_info guard + individual ALTER TABLE,
    mirroring ``batch_scan_kol._ensure_column``. SQLite before 3.35 does not
    support ``ADD COLUMN IF NOT EXISTS``, so we check before altering.
    """
    def _ensure(table: str, column: str, type_def: str) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")

    # D-10.01: articles.body holds scrape-on-demand persisted content so the
    # classifier reads the same body the ingester will later ingest.
    _ensure("articles", "body", "TEXT")

    # D-10.04: new classifications columns for the scrape-first schema.
    # Old columns (depth_score, topic, reason) are retained for batch-scan compat.
    _ensure("classifications", "depth", "INTEGER")
    _ensure("classifications", "topics", "TEXT")       # JSON-serialized list
    _ensure("classifications", "rationale", "TEXT")

    conn.commit()


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
    if genai_types is None:
        logger.warning("google-genai package not available — cannot call Gemini API")
        return None
    try:
        # lib.generate_sync handles key resolution + rotation + rate limit + retry.
        text = generate_sync(
            INGESTION_LLM,
            prompt,
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(text)
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
        # Gemini key resolution is owned by lib.current_key() — fall back to pass-through
        # if the pool is empty (same fail-open semantics as before).
        try:
            from lib import current_key
            current_key()
            api_key = "lib-managed"  # sentinel — real key supplied by generate_sync
        except Exception:
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


async def run(days_back: int, max_articles: int, dry_run: bool, **kwargs) -> None:
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
    # Phase 5-00b: initialize LightRAG ONCE and share across all articles.
    # Skip init entirely for dry-run (no ainsert calls).
    rag = None
    if not dry_run and passed:
        from ingest_wechat import get_rag
        # D-09.04 (STATE-01): flush=True discards any in-memory pending buffer
        # from a prior crashed run → no replay → no wasted embed quota.
        logger.info("Initializing fresh LightRAG instance (flush=True; STATE-01)...")
        rag = await get_rag(flush=True)

    try:
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

            # Phase 12 CKPT-03: batch-level checkpoint skip. Articles whose
            # text_ingest marker already exists are skipped without re-entering
            # the per-article ingest pipeline.
            ckpt_hash = get_article_hash(url)
            if has_stage(ckpt_hash, "text_ingest"):
                logger.info("checkpoint-skip: already-ingested hash=%s url=%s", ckpt_hash, url)
                summary.append({
                    "account": account_name,
                    "title": title,
                    "url": url,
                    "status": "skipped_ingested",
                })
                continue

            success = await ingest_article(url, dry_run, rag)
            summary.append({
                "account": account_name,
                "title": title,
                "url": url,
                "status": "dry_run" if dry_run else ("ok" if success else "failed"),
            })

            processed += 1
            if not dry_run and processed < total:
                logger.info("  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...", SLEEP_BETWEEN_ARTICLES)
                await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)
    finally:
        if rag is not None:
            # D-10.09: drain pending Vision worker tasks before flushing storages.
            await _drain_pending_vision_tasks()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()

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


async def _classify_full_body(
    conn: sqlite3.Connection,
    article_id: int,
    url: str,
    title: str,
    body: str | None,
    api_key: str,
) -> dict | None:
    """Scrape-first per-article classification (D-10.01 / D-10.02 / D-10.04).

    Flow:
      1. If ``body`` is empty, scrape on-demand via
         ``ingest_wechat.scrape_wechat_ua`` (reuses UA rotation + _ua_cooldown
         — D-10.03; no new rate-limit constants introduced), convert the
         returned HTML to markdown via ``ingest_wechat.process_content``,
         and persist the body to ``articles.body`` for reuse.
      2. Build a full-body DeepSeek prompt via
         ``batch_classify_kol._build_fullbody_prompt`` and call DeepSeek via
         ``_call_deepseek_fullbody``.
      3. On SUCCESS, write a classifications row (new columns: depth, topics,
         rationale; legacy columns: depth_score, topic, reason for back-compat)
         BEFORE returning. Caller decides whether to ingest based on the
         returned dict.
      4. On FAILURE (scrape fails OR DeepSeek returns None), return ``None``
         without writing any classifications row. Caller MUST NOT ingest —
         no fail-open (distinguishes from batch-scan behavior).

    Returns:
      The classification dict ``{"depth", "topics", "rationale"}`` on success;
      ``None`` on any failure.
    """
    # 1. Scrape on demand if body absent (D-10.01). Late import avoids
    # LightRAG init at module load for callers that only need the classifier.
    if not body:
        import ingest_wechat

        scraped = await ingest_wechat.scrape_wechat_ua(url)
        if not scraped or not scraped.get("content_html"):
            logger.warning(
                "scrape-on-demand failed for %s — skipping classify", url[:80]
            )
            return None
        body, _ = ingest_wechat.process_content(scraped["content_html"])
        conn.execute(
            "UPDATE articles SET body = ? WHERE id = ?", (body, article_id)
        )
        conn.commit()

    # 2. Call DeepSeek on the full body (D-10.02).
    from batch_classify_kol import _build_fullbody_prompt, _call_deepseek_fullbody

    prompt = _build_fullbody_prompt(title, body)
    result = _call_deepseek_fullbody(prompt, api_key)
    if result is None:
        logger.warning(
            "DeepSeek classify failed for %s — skipping (no fail-open, D-10.04)",
            url[:80],
        )
        return None

    # 3. Persist classifications row BEFORE returning (D-10.04 strict ordering).
    depth = result.get("depth", 2)
    topics = result.get("topics", []) or []
    rationale = result.get("rationale", "")
    # Legacy columns: first topic → old `topic` col; depth → old `depth_score`.
    legacy_topic = topics[0] if topics else "unknown"
    conn.execute(
        """INSERT OR REPLACE INTO classifications
           (article_id, topic, depth_score, depth, topics, rationale, relevant)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (
            article_id,
            legacy_topic,
            depth if isinstance(depth, int) else 2,
            depth if isinstance(depth, int) else None,
            json.dumps(topics, ensure_ascii=False),
            rationale,
        ),
    )
    conn.commit()
    return result


async def ingest_from_db(topic: str | list[str], min_depth: int, dry_run: bool) -> None:
    """Ingest articles that passed classification for a topic (or list of topics). Reads from kol_scan.db.

    Phase 5-00b: in-process orchestration with shared LightRAG instance.
    Rag is created once (skipped for dry-run) and finalized in ``finally``
    so Ctrl+C during a long batch still flushes vdb + graphml cleanly.
    """
    topics = [topic] if isinstance(topic, str) else topic

    if not DB_PATH.exists():
        logger.error("DB not found: %s. Run batch_scan_kol.py first.", DB_PATH)
        sys.exit(1)

    _load_hermes_env()

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

    # D-10.01 / D-10.04: schema-additive migration for scrape-first flow.
    _ensure_fullbody_columns(conn)

    # Phase 10 plan 10-00: scrape-first SELECT — classification happens per-article
    # inside the loop, so we no longer pre-filter by `c.depth_score >= min_depth`.
    # Unclassified articles have NULL depth_score; they are classified on the fly.
    placeholders = ",".join("?" for _ in topics)
    rows = conn.execute(f"""
        SELECT a.id, a.title, a.url, acc.name, c.depth_score, a.body
        FROM articles a
        JOIN accounts acc ON a.account_id = acc.id
        LEFT JOIN classifications c ON a.id = c.article_id
        WHERE (c.topic IS NULL OR c.topic IN ({placeholders}))
          AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
        ORDER BY a.id
    """, tuple(topics)).fetchall()

    if not rows:
        logger.info("No articles found for topics %s", topics)
        conn.close()
        return

    logger.info("%d articles to process (scrape-first) for topics %s", len(rows), topics)

    # Phase 5-00b: initialize LightRAG ONCE; skip for dry-run.
    rag = None
    if not dry_run:
        from ingest_wechat import get_rag
        # D-09.04 (STATE-01): flush=True discards any in-memory pending buffer
        # from a prior crashed run → no replay → no wasted embed quota.
        logger.info("Initializing fresh LightRAG instance (flush=True; STATE-01)...")
        rag = await get_rag(flush=True)

    try:
        processed = 0
        api_key = get_deepseek_api_key()
        for i, (art_id, title, url, account, depth, body) in enumerate(rows, 1):
            logger.info("[%d/%d] [%s] (prior depth=%s) %s", i, len(rows), account, depth, title)

            if not url:
                logger.warning("  Skipping — no URL")
                conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')", (art_id,))
                conn.commit()
                continue

            # Phase 12 CKPT-03: batch-level checkpoint skip (DB-driven loop).
            ckpt_hash = get_article_hash(url)
            if has_stage(ckpt_hash, "text_ingest"):
                logger.info("checkpoint-skip: already-ingested hash=%s url=%s", ckpt_hash, url)
                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped_ingested')",
                    (art_id,),
                )
                conn.commit()
                continue

            # D-10.01..04: scrape-first per-article classify. Runs BEFORE
            # the Phase 9 ingest_article call. No fail-open — skip on classify error.
            if not dry_run and api_key:
                cls_result = await _classify_full_body(
                    conn=conn,
                    article_id=art_id,
                    url=url,
                    title=title,
                    body=body,
                    api_key=api_key,
                )
                if cls_result is None:
                    logger.info("  classify failed — skipping ingest (D-10.04 no fail-open)")
                    conn.execute(
                        "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')",
                        (art_id,),
                    )
                    conn.commit()
                    continue
                cls_depth = cls_result.get("depth", 0)
                if not isinstance(cls_depth, int) or cls_depth < min_depth:
                    logger.info(
                        "  depth=%s < min_depth=%d — skipping ingest",
                        cls_depth,
                        min_depth,
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')",
                        (art_id,),
                    )
                    conn.commit()
                    continue

            success = await ingest_article(url, dry_run, rag)
            status = "dry_run" if dry_run else ("ok" if success else "failed")
            conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, ?)", (art_id, status))
            conn.commit()

            processed += 1
            if not dry_run and processed < len(rows):
                logger.info("  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...", SLEEP_BETWEEN_ARTICLES)
                await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)

        logger.info("Done — %d articles processed", len(rows))
    finally:
        if rag is not None:
            # D-10.09: drain pending Vision worker tasks before flushing storages.
            await _drain_pending_vision_tasks()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()
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
        coro = ingest_from_db(topic_keywords, args.min_depth, args.dry_run)
    else:
        coro = run(
            days_back=args.days_back,
            max_articles=args.max_articles,
            dry_run=args.dry_run,
            topic_filter=topic_keywords,
            exclude_topics=args.exclude_topics,
            min_depth=args.min_depth,
            account_filter=args.account,
            classifier=args.classifier,
        )

    # Phase 5-00b: async orchestration — rag lifecycle owned by the coroutine.
    # On Ctrl+C, KeyboardInterrupt propagates into the coroutine's finally
    # block where rag.finalize_storages() flushes vdb + graphml.
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C) — storages finalized in coroutine finally block")
        sys.exit(130)


if __name__ == "__main__":
    main()
