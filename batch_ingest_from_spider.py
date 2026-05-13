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
import hashlib
import json
import logging
import re
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
from lib.batch_timeout import (
    BATCH_SAFETY_MARGIN_S,
    clamp_article_timeout,
    get_remaining_budget,
)
from lib.article_filter import (
    ArticleMeta,
    ArticleWithBody,
    FilterResult,
    LAYER1_BATCH_SIZE,
    LAYER2_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    layer1_pre_filter,
    layer2_full_body_score,
    persist_layer1_verdicts,
    persist_layer2_verdicts,
)


# Quick 260509-s29 Wave 2: reject-reason cohort version.
#
# Bumped manually whenever the Layer 1 reject taxonomy or prompt changes
# (deliberate, like PROMPT_VERSION_LAYER1). The candidate SELECT in
# ``_build_topic_filter_query`` excludes ``status='skipped'`` rows whose
# ``skip_reason_version`` matches this constant — so a permanently dead
# URL stays excluded forever, but a taxonomy bump puts older skipped rows
# back into the candidate pool for re-evaluation.
#
# 0 = legacy (backfill value applied by migrations/009_skip_reason_version)
# 1 = current taxonomy (initial value at schema introduction)
SKIP_REASON_VERSION_CURRENT = 1
from lib.checkpoint import get_article_hash, has_stage
from lib.vision_tracking import drain_vision_tasks

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
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    force=True,  # v3.5 ir-2 hotfix: prevent LightRAG get_rag() from swallowing [layer2] output
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SLEEP_BETWEEN_ARTICLES = 10  # Phase 5-00c: DeepSeek LLM + 2-key Gemini embedding rotation (not 15 RPM Gemini)
GEMINI_BATCH_SLEEP = 2.0   # DeepSeek: no RPM concern; light pause for API stability
DB_PATH = Path(os.environ.get(
    "KOL_SCAN_DB_PATH",
    str(PROJECT_ROOT / "data" / "kol_scan.db"),
))

# D-10.09: aggregate deadline for draining pending Vision worker tasks before
# rag.finalize_storages(). 120s covers the worst-case backlog of ~30 articles
# @ ~4s/article describe time. Tests override this to a small value via monkeypatch.
VISION_DRAIN_TIMEOUT = 120.0


async def _drain_pending_vision_tasks() -> None:
    """Drain Vision worker tasks lingering on the event loop (D-10.09 / 260509-p1n).

    Thin wrapper around ``lib.vision_tracking.drain_vision_tasks`` that
    preserves the existing function name (call sites at :873 and :1937
    unchanged) and the module-level ``VISION_DRAIN_TIMEOUT`` constant
    (existing tests monkeypatch it).

    Replaces the prior ``asyncio.all_tasks()`` broad-scan implementation
    that captured LightRAG / Cognee / kuzu library tasks alongside actual
    Vision workers, causing the post-cap event-loop hang on Hermes
    2026-05-09.  See ``lib/vision_tracking.py`` for the dedicated
    ``_VISION_TASKS`` set + spawn-site registration via
    ``track_vision_task``.
    """
    await drain_vision_tasks(timeout_s=VISION_DRAIN_TIMEOUT)


# D-09.03 (TIMEOUT-03): per-article outer budget formula.
# Inner LightRAG per-chunk LLM timeout is LLM_TIMEOUT=600 (D-09.01) — set via
# setdefault at top of file.
_CHUNK_SIZE_CHARS = 4800        # ~1200 tokens × 4 chars/token; LightRAG default chunk size
_BASE_BUDGET_S = 120
_PER_CHUNK_S = 30
_PER_IMAGE_S = 30               # T1 (2026-05-13): vision cascade per image, with safety
                                # Hermes prod measurement 2026-05-13: 60-image batch avg 24.5s/img,
                                # 34-image article = 833s vision + 100s ainsert = 933s actual.
                                # 30s/img = ~20% safety margin above empirical avg.
                                # No image-side cap: vision cascade (SiliconFlow primary +
                                # OpenRouter fallback) is stable; large articles let cascade
                                # finish naturally rather than truncating image set.
_SINGLE_CHUNK_FLOOR_S = 900     # guarantees one slow 800s DeepSeek chunk completes


_MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')

# Image extensions counted on disk fallback. Lower-case match.
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _count_images_on_disk(url: str | None) -> int:
    """Count downloaded image files in ``$BASE/images/{md5(url)[:10]}/``.

    Production images are stored under article-URL-based MD5[:10] hash
    (verified 2026-05-13: same scheme for WeChat and RSS — see
    ``ingest_wechat.py:1017`` and prod kv_store sample ``rss_9f52f6cbef``).

    Returns 0 on missing dir / missing url / I/O error. This is a budget
    *estimator*, never a correctness gate.
    """
    if not url:
        return 0
    base = os.environ.get("OMNIGRAPH_BASE_DIR") or str(Path("~/.hermes/omonigraph-vault").expanduser())
    article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    img_dir = Path(base).expanduser() / "images" / article_hash
    if not img_dir.is_dir():
        return 0
    try:
        return sum(
            1 for p in img_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _IMG_EXT
        )
    except OSError:
        return 0


def _count_images_in_body(body: str, *, url: str | None = None) -> int:
    """Best-effort image count for budget computation.

    Strategy (cheap → expensive):
      1. Markdown ``![...](...)`` regex — works for fresh RSS and articles
         where image markers are preserved.
      2. Disk fallback — when regex returns 0 AND ``url`` provided, count
         downloaded files in ``$BASE/images/{md5(url)[:10]}/``. Catches
         the WeChat case where post-vision-description bodies have image
         markers stripped/replaced (issue #2, T1-b1).

    Returns 0 on empty body and no disk fallback hit. ``url`` is keyword-only
    to keep call sites self-documenting.
    """
    if not body:
        # Fresh ingest path may have empty body. Try disk anyway if url given.
        return _count_images_on_disk(url)
    md_count = len(_MD_IMAGE_RE.findall(body))
    if md_count > 0:
        return md_count
    return _count_images_on_disk(url)


def _compute_article_budget_s(
    full_content: str,
    *,
    url: str | None = None,
    image_count: int | None = None,
) -> int:
    """Compute outer asyncio.wait_for budget for an article.

    Two-layer timeout semantics:
      - Outer (this budget): governs whole-article ingest call.
      - Inner (LLM_TIMEOUT=600 via D-09.01): governs each per-chunk LLM call.

    Image count resolution priority (D2 + T1 + T1-b1):
      1. Explicit ``image_count`` kwarg — preferred. Populated at scrape
         time from articles.image_count (mig 011, D2). Includes the case
         where caller knows the exact count and wants to bypass body /
         disk lookup.
      2. Markdown ``![](...)`` regex on body — RSS path (body retains
         remote refs) and KOL pre-vision path.
      3. Disk fallback under ``$BASE/images/{md5(url)[:10]}/`` — T1-b1
         defense-in-depth for WeChat re-ingestion when post-vision body
         has stripped markers.

    Formula: ``max(BASE + PER_CHUNK*chunks + PER_IMAGE*images, FLOOR)``

    chunk_count derived from ``len(full_content) // _CHUNK_SIZE_CHARS`` (floor, min 1).
    No upper cap — vision cascade is stable, large articles let it finish.

    T1 (2026-05-13): pre-fix had no image term, 51-image article hit 900s
    floor and timed out (Hermes prod measurement: 34-image needed 933s, 60-image
    1468s; vision avg 24.5s/img + ainsert overhead). Post-fix the same 51-image
    article (text=180s + 51×30=1530s) gets max(1710, 900) = 1710s budget.
    Light articles (≤5 images) unaffected because text+image still under floor.
    """
    chunk_count = max(1, len(full_content) // _CHUNK_SIZE_CHARS)
    if image_count is not None and image_count >= 0:
        resolved_image_count = image_count
    else:
        resolved_image_count = _count_images_in_body(full_content, url=url)
    text_budget = _BASE_BUDGET_S + _PER_CHUNK_S * chunk_count
    image_budget = _PER_IMAGE_S * resolved_image_count
    return max(text_budget + image_budget, _SINGLE_CHUNK_FLOOR_S)


# --- Phase 17 (BTIMEOUT-04): batch-timeout metrics helpers ---

_HISTOGRAM_BUCKETS: tuple[tuple[str, float], ...] = (
    ("0-60s", 60.0),
    ("60-300s", 300.0),
    ("300-900s", 900.0),
    # Anything above 900s falls into "900s+"
)


def _bucket_article_time(seconds: float) -> str:
    """Classify an article wall-clock time into a histogram bucket (BTIMEOUT-04)."""
    for label, upper in _HISTOGRAM_BUCKETS:
        if seconds < upper:
            return label
    return "900s+"


def _resolve_batch_timeout(cli_value: int | None) -> int:
    """Resolve the total batch budget (OMNIGRAPH_BATCH_TIMEOUT_SEC wins over CLI).

    Phase 7 env var idiom: namespaced OMNIGRAPH_* prefix. If env unset, use CLI
    value; if CLI also None, default to 28800 (8h — covers 56-article batch at 441s
    Hermes baseline per v3.1 closure §3).
    """
    env_val = os.environ.get("OMNIGRAPH_BATCH_TIMEOUT_SEC")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            logger.warning(
                "OMNIGRAPH_BATCH_TIMEOUT_SEC=%r is not an int — falling back", env_val
            )
    return int(cli_value) if cli_value else 28800


def _build_batch_timeout_metrics(
    total_budget: int,
    batch_start: float,
    completed_times: list[float],
    total_articles: int,
    timed_out: int,
    clamped_count: int,
    safety_margin_triggered: bool,
    histogram: dict[str, int],
) -> dict:
    """Assemble the batch_timeout_metrics dict per design § Monitoring Metrics (BTIMEOUT-04)."""
    elapsed = time.time() - batch_start
    completed_count = len(completed_times)
    not_started = total_articles - completed_count - timed_out
    avg_article_time = (
        sum(completed_times) / completed_count if completed_count > 0 else None
    )
    return {
        "total_batch_budget_sec": total_budget,
        "total_elapsed_sec": round(elapsed, 2),
        "batch_progress_vs_budget": round(elapsed / total_budget, 4) if total_budget > 0 else None,
        "total_articles": total_articles,
        "completed_articles": completed_count,
        "timed_out_articles": timed_out,
        "not_started_articles": max(0, not_started),
        "avg_article_time_sec": round(avg_article_time, 2) if avg_article_time else None,
        "timeout_histogram": dict(histogram),
        "clamped_timeouts": clamped_count,
        "safety_margin_triggered": safety_margin_triggered,
    }


async def ingest_article(
    source: str,
    url: str,
    dry_run: bool,
    rag,
    effective_timeout: int | None = None,
) -> tuple[bool, float, bool]:
    """Ingest a single URL in-process against the shared LightRAG instance.

    Phase quick-260510-uai: accepts ``source`` (positional 0) — threaded into
    ``ingest_wechat.ingest_article`` kwarg so RSS rows get doc_id ``rss_<hash>``
    instead of ``wechat_<hash>``. Closes the t1o-investigation gap where every
    URL was dispatched to the WeChat-specific ingester regardless of source.

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

    Phase 17 additions:
      * Returns ``(success, wall_clock_seconds)`` instead of just ``bool`` so
        the batch loop can record per-article durations into the histogram.
      * If ``effective_timeout`` is provided (from the batch interlock via
        ``clamp_article_timeout``), use it; otherwise fall back to Phase 9's
        ``_SINGLE_CHUNK_FLOOR_S`` (900s) for backward compatibility.
      * On ``asyncio.TimeoutError``, the checkpoint flush runs OUTSIDE the
        ``asyncio.wait_for`` (BTIMEOUT-03); guarded with ``try/ImportError``
        so the plan merges standalone if Phase 12 ``flush_partial_checkpoint``
        is not yet available.
    """
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True, 0.0, False

    import ingest_wechat

    # SCH-02: canonical article_hash lives in lib.checkpoint.get_article_hash
    # (SHA-256 first 16 hex). Phase 19 unifies the namespace so Phase 22 backlog
    # and checkpoint_reset.py operate on one hash format. get_article_hash is
    # already imported at module scope (line 63).
    article_hash = get_article_hash(url)
    timeout_s = effective_timeout if effective_timeout is not None else _SINGLE_CHUNK_FLOOR_S

    t_start = time.time()
    try:
        # D-09.03: 900s floor covers a worst-case single-chunk 800s DeepSeek call.
        # Phase 17 (BTIMEOUT-02): if the caller passed a clamped budget, use it.
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, source=source, rag=rag),
            timeout=timeout_s,
        )
        return True, time.time() - t_start, True
    except asyncio.TimeoutError:
        wall = time.time() - t_start
        logger.warning("TIMEOUT (%ds) — skipping: %s", timeout_s, url[:80])
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
        # Phase 17 BTIMEOUT-03: checkpoint flush runs OUTSIDE wait_for (we're
        # already past it in this except branch). If Phase 12 checkpoint infra
        # exposes flush_partial_checkpoint, call it; otherwise skip silently.
        try:
            from lib.checkpoint import flush_partial_checkpoint  # type: ignore
            await flush_partial_checkpoint(article_hash)
        except ImportError:
            pass  # Phase 12 flush API not yet available; skip silently.
        except Exception as flush_exc:
            logger.warning("Checkpoint flush failed: %s", flush_exc)
        return False, wall, False
    except Exception as exc:
        wall = time.time() - t_start
        logger.warning("Ingest failed (%s): %s — skipping: %s",
                       exc.__class__.__name__, exc, url[:80])
        return False, wall, False


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
            f"- relevant: true/false — does this article provide deep technical content"
            f" about agent framework architecture, core modules, or infrastructure"
            f" (not just passingly mention AI/agents)? Is it substantially about ANY of:"
            f" {keywords_quoted}?\n"
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

    return f"""You are a technical article curator for an AI agent framework developer
who tracks OpenClaw, Hermes, and emerging agent frameworks. The goal is to catch
articles that provide deep technical insight into agent framework architecture,
core module design, and related infrastructure projects.

For each article, return a JSON array of objects with:

- index: the 0-based index

- depth_score:
    1 = SHALLOW — news headline, product announcement, event notice, job posting,
        tool download/"一键包" page, sponsored content
    2 = MODERATE — overview/summary with some technical detail but no deep analysis
        of architecture, tradeoffs, or implementation
    3 = DEEP — substantive analysis of architecture design, implementation detail,
        benchmark methodology with data, design tradeoffs, or novel technical approach.
        Must go beyond "what" to explain "how" and "why".

{topic_instruction}
- reason: 10-20 word explanation in English — depth justification + why relevant/not

RELEVANCE EXCLUSIONS: Do NOT mark as relevant articles about:
- Pure model releases (new LLM, vision/TTS/speech model) without agent integration
- CV/vision papers, image/video/audio generation, 3D reconstruction
- Chip hardware, GPU benchmarks, inference optimization unrelated to agents
- General AI industry news, corporate strategy, funding, hiring
- "How to use AI" tutorials without agent architecture discussion
- Job postings, tool download pages (一键包), course advertisements

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

    # Phase 17 BTIMEOUT-01: batch-budget state
    total_batch_budget = _resolve_batch_timeout(kwargs.get("batch_timeout"))
    batch_start = time.time()
    completed_times: list[float] = []
    timeout_histogram: dict[str, int] = {label: 0 for label, _ in _HISTOGRAM_BUCKETS}
    timeout_histogram["900s+"] = 0
    timed_out_count = 0
    clamped_count = 0
    safety_margin_triggered = False

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

            # Phase 17 BTIMEOUT-02: clamp per-article timeout to batch budget.
            remaining = get_remaining_budget(batch_start, total_batch_budget)
            effective_timeout = clamp_article_timeout(
                _SINGLE_CHUNK_FLOOR_S, remaining, BATCH_SAFETY_MARGIN_S
            )
            if effective_timeout < _SINGLE_CHUNK_FLOOR_S:
                clamped_count += 1
                logger.info(
                    "  Clamped article timeout: %ds (remaining=%.0fs, margin=%ds)",
                    effective_timeout, remaining, BATCH_SAFETY_MARGIN_S,
                )
            if remaining - BATCH_SAFETY_MARGIN_S <= 0:
                safety_margin_triggered = True

            success, wall, doc_confirmed = await ingest_article(
                'wechat', url, dry_run, rag, effective_timeout=effective_timeout
            )
            if dry_run:
                status = "dry_run"
            elif success and doc_confirmed:
                status = "ok"
                completed_times.append(wall)
                timeout_histogram[_bucket_article_time(wall)] += 1
            else:
                status = "failed"
                if wall >= effective_timeout:  # heuristic for wait_for kill
                    timed_out_count += 1
                    timeout_histogram["900s+"] += 1

            summary.append({
                "account": account_name,
                "title": title,
                "url": url,
                "status": status,
            })

            processed += 1
            if not dry_run and processed < total:
                logger.info("  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...", SLEEP_BETWEEN_ARTICLES)
                await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)

            # Phase 17 BTIMEOUT-01: early-exit if budget fully exhausted.
            if get_remaining_budget(batch_start, total_batch_budget) <= 0:
                logger.warning(
                    "Batch budget exhausted (%ds elapsed >= %ds) — stopping loop; "
                    "remaining %d article(s) will show as not_started in metrics.",
                    int(time.time() - batch_start), total_batch_budget, total - i,
                )
                break
    finally:
        if rag is not None:
            # D-10.09: drain pending Vision worker tasks before flushing storages.
            await _drain_pending_vision_tasks()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()

        # Phase 17 BTIMEOUT-04: emit metrics (always, even on early exit).
        metrics = _build_batch_timeout_metrics(
            total_budget=total_batch_budget,
            batch_start=batch_start,
            completed_times=completed_times,
            total_articles=len(passed),
            timed_out=timed_out_count,
            clamped_count=clamped_count,
            safety_margin_triggered=safety_margin_triggered,
            histogram=timeout_histogram,
        )
        logger.info("batch_timeout_metrics: %s", json.dumps(metrics))
        metrics_path = PROJECT_ROOT / "data" / f"batch_timeout_metrics_{timestamp}.json"
        metrics_path.parent.mkdir(exist_ok=True)
        metrics_path.write_text(
            json.dumps({"batch_timeout_metrics": metrics}, indent=2),
            encoding="utf-8",
        )
        logger.info("Metrics written to %s", metrics_path)

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


# v3.5 ir-4 (LF-4.4): RSS rows with body length above this threshold are
# trusted as "good enough" and skip the scrape stage. Below this threshold
# (or NULL body) the row goes through ``lib.scraper.scrape_url`` which
# auto-routes to the generic cascade for non-WeChat URLs. KOL rows always
# skip scrape when body is non-empty (legacy semantic preserved).
RSS_SCRAPE_THRESHOLD = 100


def _needs_scrape(source: str, body: str | None) -> bool:
    """Return True iff the per-article scrape stage should run.

    KOL (source='wechat'): scrape only when body is missing/empty.
    Preserves the pre-ir-4 behavior where KOL rows always re-use the DB
    body if any was previously scraped (any length >0).

    RSS (source='rss'): scrape when body is missing OR shorter than
    ``RSS_SCRAPE_THRESHOLD`` chars. The RSS feed's <description> is often
    a 50-char excerpt — too short for Layer 2 / ainsert. Lengths above
    the threshold come from rss_fetch's full <content:encoded> path and
    are good enough to skip the scrape (W0 audit: 27% of local RSS rows
    already have body >100 chars).
    """
    if not body:
        return True
    if source == "rss" and len(body) <= RSS_SCRAPE_THRESHOLD:
        return True
    return False


# v3.5 ir-4: source → source-table mapping for body persistence dispatch.
_BODY_TABLE_FOR: dict[str, str] = {"wechat": "articles", "rss": "rss_articles"}


def _persist_scraped_body(
    conn: sqlite3.Connection,
    article_id: int,
    source: str,
    scrape: "ScrapeResult",  # forward-ref str — keeps lib.scraper import lazy
) -> str | None:
    """BODY-01 + ir-4: atomically persist scraped body to the correct
    source-table.

    Dispatch by ``source``:
      ``wechat`` → ``articles.body``
      ``rss``    → ``rss_articles.body``

    Idempotent: SQL guard ``body IS NULL OR length(body) < 500`` prevents
    overwriting an already-ingested body (race-safe across batch retries).

    Body source: prefer ``ScrapeResult.markdown`` when non-empty, else
    ``ScrapeResult.content_html``. Empty/None bodies are a no-op.

    DB failures are logged at WARNING and swallowed -- caller continues.

    Returns the body string on successful UPDATE; None on any failure or
    no-op (including unknown source — caller treated as a soft-skip).
    """
    table = _BODY_TABLE_FOR.get(source)
    if table is None:
        logger.warning(
            "BODY-01 persist refused: unknown source=%r article_id=%s",
            source, article_id,
        )
        return None
    try:
        body = (scrape.markdown or "").strip() or (scrape.content_html or "").strip()
        if not body:
            return None
        conn.execute(
            f"UPDATE {table} SET body = ? "
            f"WHERE id = ? AND (body IS NULL OR length(body) < 500)",
            (body, article_id),
        )
        conn.commit()
        return body
    except Exception as e:  # noqa: BLE001 -- never raise into main loop
        logger.warning(
            "BODY-01 persist failed for source=%s article_id=%s: %s",
            source, article_id, e,
        )
        return None


async def _classify_full_body(
    conn: sqlite3.Connection,
    article_id: int,
    url: str,
    title: str,
    body: str | None,
    api_key: str,
    topic_filter: list[str] | None = None,
) -> dict | None:
    """Scrape-first per-article classification (D-10.01 / D-10.02 / D-10.04).

    ``topic_filter`` is forwarded to ``_build_fullbody_prompt`` to bias the
    LLM toward user-specified keywords. Default ``None`` = no hint
    (backward compat). Quick-260506-en4: closes 99% CV-tag regression.

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
    # 1. Scrape on demand if body absent (D-10.01).
    # SCR-06 hotfix (Phase 19): route via lib.scraper.scrape_url which runs
    # the full 4-layer WeChat cascade (apify -> cdp -> mcp -> ua) -- not UA-only.
    # Closes Day-1 KOL 06:00 ADT regression where UA-only path was the sole
    # fallback when Apify / CDP were misconfigured.
    if not body:
        import ingest_wechat
        from lib.scraper import scrape_url

        scraped = await scrape_url(url, site_hint="wechat")
        if not scraped or (not scraped.content_html and not scraped.markdown):
            logger.warning(
                "scrape-on-demand failed for %s -- skipping classify", url[:80]
            )
            return None
        # SCR-06: Apify returns \"markdown\" key without \"content_html\".
        # When markdown is already available, use it directly — process_content
        # would produce the same output from an HTML wrapper.
        if not scraped.content_html and scraped.markdown:
            body = scraped.markdown
        else:
            body, _ = ingest_wechat.process_content(scraped.content_html)
        conn.execute(
            "UPDATE articles SET body = ? WHERE id = ?", (body, article_id)
        )
        conn.commit()

    # 2. Call DeepSeek on the full body (D-10.02).
    from batch_classify_kol import _build_fullbody_prompt, _call_deepseek_fullbody

    prompt = _build_fullbody_prompt(title, body, topic_filter=topic_filter)
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
        """INSERT INTO classifications
           (article_id, topic, depth_score, depth, topics, rationale, relevant)
           VALUES (?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(article_id, topic) DO UPDATE SET
               depth_score=excluded.depth_score,
               depth=excluded.depth,
               topics=excluded.topics,
               rationale=excluded.rationale,
               relevant=excluded.relevant""",
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


def _graded_probe_prompts(
    title: str,
    account: str,
    digest: str,
    filter_keywords: tuple[str, ...],
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the graded probe.

    Extracted so the DeepSeek HTTP path and the Vertex Gemini SDK path build
    the same prompt — keeps the two providers semantically equivalent and
    lets prompt-quality tests target one well-known string.

    Prompt design (2026-05-05 rewrite, post Hermes false-negative report):
    The previous prompt asked "is this OBVIOUSLY unrelated to ALL of [agent,
    openclaw, hermes, harness]?" and let the model interpret "agent"
    word-literally. Both DeepSeek and Vertex Gemini then skipped articles
    on RAG, GraphRAG, and multi-agent orchestration — all of which are
    core agent-ecosystem content the cron is supposed to ingest.

    The fix is path B (conservative): instead of asking the model to define
    "agent", we hand it an explicit reject-list of obvious off-topic domains
    and tell it that ANY agent / RAG / tool-use / autonomous-reasoning
    signal flips the answer back to ``unrelated=false`` (let full classify
    decide). Ambiguous cases also fail open. This trades some false-positives
    for zero false-negatives — a deliberate recall-over-precision choice
    given that a missed agent article costs much more than an extra scrape.
    """
    truncated_digest = digest.strip()[:200]
    keywords_str = ", ".join(t.strip() for t in filter_keywords if t.strip())

    system_prompt = (
        "You are a topic relevance filter for an LLM-agent knowledge base. "
        "Reply ONLY with valid JSON. "
        'Format: {"unrelated": bool, "confidence": 0-1, "reason": "<=50 chars"}'
    )
    user_prompt = (
        f"Filter keywords: {keywords_str}\n"
        f"Title: {title}\n"
        f"Account: {account}\n"
        f"Excerpt: {truncated_digest}\n\n"
        "Set unrelated=true ONLY when the article is OBVIOUSLY about one of "
        "these non-agent topics, with NO mention of LLMs, agents, RAG, "
        "tool-use, or autonomous reasoning:\n"
        "  - Pure computer vision / image segmentation / pose estimation\n"
        "  - Medical AI / bioinformatics (unless agent-applied)\n"
        "  - Recommender systems / ad ranking / search ranking\n"
        "  - Pure image or video generation (Stable Diffusion, Sora, etc.)\n"
        "  - Hardware / chip architecture / GPU benchmarks\n"
        "  - Pure training infrastructure (DeepSpeed, FSDP, etc. with no "
        "agent layer)\n\n"
        "Set unrelated=false (let full classify decide) if the article "
        "mentions ANY of: LLM, AI agent, multi-agent, agentic, RAG, "
        "retrieval-augmented, tool use, function calling, ReAct, "
        "LangChain / LangGraph / AutoGen / CrewAI, coding agent, browser "
        "agent, agent memory, agent orchestration, agent evaluation, "
        "OpenClaw, Hermes, autonomous reasoning, or a topic that COULD "
        "plausibly cover agents (e.g. a major LLM release, prompting "
        "techniques, evaluation benchmarks).\n\n"
        "If ambiguous or excerpt < 50 chars: unrelated=false. "
        "Bias toward unrelated=false — false-negatives cost more than "
        "extra scrapes."
    )
    return system_prompt, user_prompt


def _parse_probe_json(content: str) -> dict | None:
    """Parse the model's JSON response into a dict; None on any failure."""
    try:
        result = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        logger.warning("graded probe parse error: %s — failing open", e)
        return None
    if not isinstance(result, dict):
        return None
    return result


async def _graded_probe_deepseek(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    timeout: float,
) -> dict | None:
    """DeepSeek HTTP path. Returns None on any error (fail-open)."""
    import aiohttp

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 100,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "graded probe HTTP %d — failing open", resp.status
                    )
                    return None
                data = await resp.json()
    except Exception as e:
        logger.warning("graded probe exception: %s — failing open", e)
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        logger.warning("graded probe parse error: %s — failing open", e)
        return None
    return _parse_probe_json(content)


async def _graded_probe_vertex(
    system_prompt: str,
    user_prompt: str,
    timeout: float,
) -> dict | None:
    """Vertex Gemini SDK path. Returns None on any error (fail-open).

    Uses ``OMNIGRAPH_GRADED_VERTEX_MODEL`` for the model id (default
    ``gemini-3.1-flash-lite-preview``) so the lightweight probe can stay on
    a cheap/fast model even when the heavy classifier on the same box uses a
    different ``OMNIGRAPH_LLM_MODEL``. Falls back to ``OMNIGRAPH_LLM_MODEL``
    when the probe-specific override is unset.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        logger.warning("graded probe vertex import failed: %s — failing open", e)
        return None

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        logger.warning(
            "graded probe vertex: GOOGLE_CLOUD_PROJECT unset — failing open"
        )
        return None
    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip() or "global"
    )
    model = (
        os.environ.get("OMNIGRAPH_GRADED_VERTEX_MODEL", "").strip()
        or os.environ.get("OMNIGRAPH_LLM_MODEL", "").strip()
        or "gemini-3.1-flash-lite-preview"
    )

    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            max_output_tokens=128,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                types.Content(role="user", parts=[types.Part(text=system_prompt)]),
                types.Content(role="user", parts=[types.Part(text=user_prompt)]),
            ],
            config=config,
        )
    except Exception as e:
        logger.warning("graded probe vertex exception: %s — failing open", e)
        return None

    text = getattr(response, "text", None) or ""
    if not text:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content_obj = getattr(candidates[0], "content", None)
            parts = getattr(content_obj, "parts", None) or []
            if parts:
                text = getattr(parts[0], "text", "") or ""
    if not text:
        logger.warning("graded probe vertex: empty response — failing open")
        return None
    return _parse_probe_json(text)


async def _graded_probe(
    title: str,
    account: str,
    digest: str,
    filter_keywords: tuple[str, ...],
    api_key: str,
    timeout: float = 30.0,
) -> dict | None:
    """Graded classification probe — lightweight pre-scrape relevance filter.

    Builds a ≤200 token prompt asking the model whether the article is
    OBVIOUSLY unrelated to ALL filter keywords. Returns None on any error
    (fail-open: let full classify decide).

    Provider routing follows ``OMNIGRAPH_LLM_PROVIDER`` (mirrors
    ``lib/llm_complete.get_llm_func`` and ``batch_classify_kol.py:269``):
      - ``deepseek`` (default, unset)  → DeepSeek HTTP API (production / Hermes)
      - ``vertex_gemini``              → Vertex AI Gemini SDK (local Cisco-proxy box)

    Threshold (decided by caller): unrelated=True AND confidence≥0.9 → skip.
    Conservative by design — false-negatives cost more than extra scrapes.

    ``api_key`` is required for the DeepSeek path and ignored on the Vertex
    path (Vertex uses SA auth via ``GOOGLE_APPLICATION_CREDENTIALS``).
    """
    if not digest or len(digest.strip()) < 10:
        # Too short to judge → fail open
        return None

    system_prompt, user_prompt = _graded_probe_prompts(
        title, account, digest, filter_keywords
    )

    provider = (
        os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip()
        or "deepseek"
    )
    if provider == "vertex_gemini":
        return await _graded_probe_vertex(system_prompt, user_prompt, timeout)
    if provider == "deepseek":
        return await _graded_probe_deepseek(
            system_prompt, user_prompt, api_key, timeout
        )
    logger.warning(
        "graded probe: unknown OMNIGRAPH_LLM_PROVIDER=%r — failing open",
        provider,
    )
    return None


def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
    """Build the --from-db candidate SELECT as (sql, params).

    v3.5 ir-4 (LF-4.4): dual-source UNION ALL. Pulls candidates from BOTH
    ``articles`` (KOL/WeChat) and ``rss_articles`` (RSS feeds) with a
    constant 'wechat'/'rss' literal in the second column so the consumer
    can dispatch persist + scrape paths by row[1].

    Returned shape: 7 columns named (id, source, title, url, source_name,
    body, summary). Source-name is ``accounts.name`` for KOL,
    ``rss_feeds.name`` for RSS. Summary is ``articles.digest`` for KOL
    (aliased) and ``rss_articles.summary`` for RSS (already named).

    v3.5 ir-1 (LF-3.4) Layer 1 verdict predicate is preserved on each
    UNION branch. Rows are candidates when ALL of the following hold:
      - row is NOT in ingestions for the SAME source with status='ok'
        (source-aware anti-join — KOL id=42 and RSS id=42 do NOT
        cross-exclude each other), AND
      - row falls into one of three buckets:
        (a) layer1_verdict IS NULL — never evaluated; needs Layer 1
        (b) layer1_prompt_version IS NOT current — prompt-bump re-eval
            (LF-1.8 pattern)
        (c) layer1_verdict = 'candidate' — passed Layer 1, ready for ingest

    Reject rows are excluded by the absence of an ``OR layer1_verdict =
    'reject'`` clause — they already wrote ``ingestions(status='skipped')``
    rows at Layer 1 stage and don't need re-processing.

    The ``topics`` parameter is retained for --topic-filter / --min-depth
    CLI back-compat (Foundation Quick V35-FOUND-03) but is NOT used in
    SQL; Layer 1 LLM call replaces topic filtering. Returned params is a
    4-tuple — each UNION branch binds (SKIP_REASON_VERSION_CURRENT,
    PROMPT_VERSION_LAYER1) for the source-aware anti-join's reject-cohort
    gate (quick-260509-s29 Wave 2: skipped rows whose skip_reason_version
    matches CURRENT are permanently dead URLs and stay excluded; rows
    with version != CURRENT re-enter the candidate pool when the Layer 1
    reject taxonomy is bumped) and the Layer 1 prompt-version predicate.

    ORDER BY ``source DESC, id``: 'wechat' DESC > 'rss' so KOL rows come
    first (FIFO within KOL), then RSS rows (FIFO within RSS). Preserves
    KOL priority while letting RSS clear over time.

    rss_feeds JOIN: INNER JOIN — rss_articles.feed_id NOT NULL and
    rss_feeds has 92 rows with name populated (W0 audit verified). An
    orphan feed_id excludes the row, surfacing data corruption rather
    than silently labeling it 'rss-feed-N'.
    """
    sql = """
        SELECT a.id   AS id,
               'wechat' AS source,
               a.title AS title,
               a.url   AS url,
               acc.name AS source_name,
               a.body  AS body,
               a.digest AS summary,
               COALESCE(a.image_count, 0) AS image_count
          FROM articles a
          JOIN accounts acc ON a.account_id = acc.id
         WHERE a.id NOT IN (
                  SELECT article_id FROM ingestions
                   WHERE source = 'wechat'
                     AND (status = 'ok'
                          OR (status = 'skipped'
                              AND skip_reason_version = ?))
               )
           AND (a.layer1_verdict IS NULL
                OR a.layer1_prompt_version IS NOT ?
                OR a.layer1_verdict = 'candidate')
        UNION ALL
        SELECT r.id,
               'rss',
               r.title,
               r.url,
               f.name,
               r.body,
               r.summary,
               COALESCE(r.image_count, 0) AS image_count
          FROM rss_articles r
          JOIN rss_feeds f ON r.feed_id = f.id
         WHERE r.id NOT IN (
                  SELECT article_id FROM ingestions
                   WHERE source = 'rss'
                     AND (status = 'ok'
                          OR (status = 'skipped'
                              AND skip_reason_version = ?))
               )
           AND (r.layer1_verdict IS NULL
                OR r.layer1_prompt_version IS NOT ?
                OR r.layer1_verdict = 'candidate')
        ORDER BY source DESC, id
    """
    return sql, (
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
    )


async def ingest_from_db(
    topic: str | list[str],
    min_depth: int,
    dry_run: bool,
    batch_timeout: int | None = None,
    max_articles: int | None = None,
) -> None:
    """Ingest articles that passed classification for a topic (or list of topics). Reads from kol_scan.db.

    Phase 5-00b: in-process orchestration with shared LightRAG instance.
    Rag is created once (skipped for dry-run) and finalized in ``finally``
    so Ctrl+C during a long batch still flushes vdb + graphml cleanly.

    Phase 17: accepts ``batch_timeout`` (seconds) for the batch-level budget
    interlock; defaults resolved via ``_resolve_batch_timeout`` so the env var
    ``OMNIGRAPH_BATCH_TIMEOUT_SEC`` still wins if set.

    quick-260503-jn6 (JN6-02): ``max_articles`` caps the number of
    SUCCESSFULLY-processed rows (skips for no-URL / checkpoint / classify /
    depth do NOT count toward the cap). Default None = unlimited.
    """
    topics = [topic] if isinstance(topic, str) else topic
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not DB_PATH.exists():
        logger.error("DB not found: %s. Run batch_scan_kol.py first.", DB_PATH)
        sys.exit(1)

    _load_hermes_env()

    conn = sqlite3.connect(str(DB_PATH))
    # v3.5 ir-4 (LF-4.4): dual-source schema — see migration 008. CREATE TABLE
    # IF NOT EXISTS for fresh-DB bootstrap; existing tables migrate via the
    # migrations/008_ingestions_dual_source.py runner. The FK to articles(id)
    # is intentionally absent because dual-source rows can reference either
    # articles.id (source='wechat') or rss_articles.id (source='rss');
    # integrity is enforced at the application layer.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'wechat'
                CHECK (source IN ('wechat', 'rss')),
            status TEXT NOT NULL CHECK (status IN (
                'ok', 'failed', 'skipped', 'skipped_ingested',
                'dry_run', 'skipped_graded'
            )),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            enrichment_id TEXT,
            skip_reason_version INTEGER NOT NULL DEFAULT 0,
            UNIQUE (article_id, source)
        )
    """)
    conn.commit()

    # D-10.01 / D-10.04: schema-additive migration for scrape-first flow.
    _ensure_fullbody_columns(conn)

    # Phase 10 plan 10-00: scrape-first SELECT — classification happens per-article
    # inside the loop, so we no longer pre-filter by `c.depth_score >= min_depth`.
    # Unclassified articles have NULL depth_score; they are classified on the fly.
    # quick-260503-sd7: case-insensitive topic filter via _build_topic_filter_query.
    sql, params = _build_topic_filter_query(topics)
    # quick-260504-vm9: save normalized topics for per-article re-validation after
    # scrape-first re-classify (prevents stale classification rows from serving as
    # entry tickets when the re-classified topic doesn't match the filter).
    normalized_topics = tuple(t.strip().lower() for t in topics)
    rows = conn.execute(sql, params).fetchall()

    if not rows:
        logger.info("No articles found for topics %s", topics)
        conn.close()
        return

    logger.info("%d articles to process (scrape-first) for topics %s", len(rows), topics)

    # v3.5 ir-1 (LF-3.1): batch Layer 1 BEFORE scrape. Chunk candidate rows
    # into LAYER1_BATCH_SIZE batches; each chunk: build ArticleMeta, call
    # real Layer 1 LLM, persist verdicts atomically, write skipped
    # ingestions for rejects, and accumulate candidates for the per-article
    # loop below. Whole-batch failure (verdict=None for every result) leaves
    # rows NULL — they will be re-evaluated on the next ingest tick.
    chunks = [
        rows[i:i + LAYER1_BATCH_SIZE]
        for i in range(0, len(rows), LAYER1_BATCH_SIZE)
    ]
    candidate_rows: list = []
    for chunk_idx, chunk in enumerate(chunks):
        # v3.5 ir-4 (LF-4.4): row tuple is now 7 cols
        # (id, source, title, url, source_name, body, summary).
        # ArticleMeta.source comes from row[1] so persist_layer1_verdicts
        # dispatches to articles vs rss_articles correctly.
        articles_meta = [
            ArticleMeta(
                id=row[0],
                source=row[1],          # 'wechat' or 'rss' from SQL literal
                title=row[2] or "",
                summary=row[6] or None, # KOL: a.digest aliased; RSS: r.summary
                content_length=None,    # neither source provides length pre-scrape
            )
            for row in chunk
        ]

        t0 = time.monotonic()
        layer1_results = await layer1_pre_filter(articles_meta)
        wall_ms = int((time.monotonic() - t0) * 1000)

        cand_count = sum(1 for r in layer1_results if r.verdict == "candidate")
        rej_count = sum(1 for r in layer1_results if r.verdict == "reject")
        null_count = sum(1 for r in layer1_results if r.verdict is None)

        if null_count == len(layer1_results):
            err_class = layer1_results[0].reason if layer1_results else "empty_batch"
            logger.warning(
                "[layer1] batch %d NULL reason=%s n=%d wall_ms=%d — rows stay NULL",
                chunk_idx, err_class, len(chunk), wall_ms,
            )
            continue

        logger.info(
            "[layer1] batch %d n=%d candidate=%d reject=%d null=%d wall_ms=%d",
            chunk_idx, len(chunk), cand_count, rej_count, null_count, wall_ms,
        )

        persist_layer1_verdicts(conn, articles_meta, layer1_results)

        for row, result in zip(chunk, layer1_results):
            if result.verdict == "reject":
                logger.info(
                    "[layer1] reject id=%s source=%s reason=%s",
                    row[0], row[1], result.reason,
                )
                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                    "VALUES (?, ?, 'skipped', ?)",
                    (row[0], row[1], SKIP_REASON_VERSION_CURRENT),
                )
            elif result.verdict == "candidate":
                candidate_rows.append(row)
        conn.commit()

    if not candidate_rows:
        logger.info(
            "[layer1] no candidates after batch filtering "
            "(total inputs=%d); nothing to ingest", len(rows),
        )
        conn.close()
        return

    logger.info(
        "[layer1] total inputs=%d candidates=%d (per-article loop starts)",
        len(rows), len(candidate_rows),
    )

    # Phase 5-00b: initialize LightRAG ONCE; skip for dry-run.
    rag = None
    if not dry_run:
        from ingest_wechat import get_rag
        # D-09.04 (STATE-01): flush=True discards any in-memory pending buffer
        # from a prior crashed run → no replay → no wasted embed quota.
        logger.info("Initializing fresh LightRAG instance (flush=True; STATE-01)...")
        rag = await get_rag(flush=True)
        # v3.5 ir-2 hotfix: LightRAG get_rag() reconfigures root logger;
        # restore our format so [layer2] batch lines are visible.
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(name)s %(message)s',
            datefmt='%H:%M:%S',
            force=True,
        )

    # Phase 17 BTIMEOUT-01: batch-budget state
    total_batch_budget = _resolve_batch_timeout(batch_timeout)
    batch_start = time.time()
    completed_times: list[float] = []
    timeout_histogram: dict[str, int] = {label: 0 for label, _ in _HISTOGRAM_BUCKETS}
    timeout_histogram["900s+"] = 0
    timed_out_count = 0
    clamped_count = 0
    safety_margin_triggered = False

    try:
        processed = 0
        api_key = get_deepseek_api_key()

        # v3.5 ir-2 (LF-3.2): Layer 2 batch accumulator.
        # Successfully-scraped candidates queue here; drain at LAYER2_BATCH_SIZE
        # boundaries (and once at end-of-loop for the final partial batch) to
        # call the batched DeepSeek Layer 2.
        layer2_queue: list[tuple[tuple, str]] = []  # (row_tuple, scraped_body)
        layer2_chunk_idx = 0

        async def _drain_layer2_queue() -> None:
            """Drain pending layer2 batch: call layer2_full_body_score, persist
            verdicts, ainsert non-rejected articles. Called when the queue
            reaches LAYER2_BATCH_SIZE and once at end-of-loop."""
            nonlocal layer2_chunk_idx, processed, timed_out_count, clamped_count, safety_margin_triggered
            if not layer2_queue:
                return

            queue_snapshot = list(layer2_queue)
            layer2_queue.clear()

            # v3.5 ir-4 (LF-4.4): row is the 7-col candidate tuple
            # (id, source, title, url, source_name, body, summary).
            # ArticleWithBody.source from row[1] so persist_layer2_verdicts
            # dispatches verdict UPDATE to articles vs rss_articles correctly.
            articles_with_body = [
                ArticleWithBody(
                    id=row[0],
                    source=row[1],
                    title=row[2] or "",
                    body=body or "",
                )
                for row, body in queue_snapshot
            ]

            t0 = time.monotonic()
            layer2_results = await layer2_full_body_score(articles_with_body)
            wall_ms = int((time.monotonic() - t0) * 1000)

            ok_count = sum(1 for r in layer2_results if r.verdict == "ok")
            rej_count = sum(1 for r in layer2_results if r.verdict == "reject")
            null_count = sum(1 for r in layer2_results if r.verdict is None)

            chunk_idx = layer2_chunk_idx
            layer2_chunk_idx += 1

            if null_count == len(layer2_results):
                err_class = layer2_results[0].reason if layer2_results else "empty_batch"
                logger.warning(
                    "[layer2] batch %d NULL reason=%s n=%d wall_ms=%d — "
                    "rows stay layer2_verdict=NULL, retry next tick",
                    chunk_idx, err_class, len(queue_snapshot), wall_ms,
                )
                return

            logger.info(
                "[layer2] batch %d n=%d ok=%d reject=%d null=%d wall_ms=%d",
                chunk_idx, len(queue_snapshot), ok_count, rej_count, null_count, wall_ms,
            )

            persist_layer2_verdicts(conn, articles_with_body, layer2_results)

            # Per-row processing: reject → skipped, ok → ainsert, None → skip
            # ainsert (mixed-batch failure; row stays NULL via persist above).
            for (row, body), result in zip(queue_snapshot, layer2_results):
                # v3.5 ir-4: 7-col tuple — url is at row[3] now (was [2]).
                art_id_d = row[0]
                source_d = row[1]
                url_d = row[3]

                if result.verdict in ("reject", "scrape_fail"):
                    logger.info(
                        "  [layer2] %s id=%s source=%s reason=%s",
                        result.verdict, art_id_d, source_d, result.reason,
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                        "VALUES (?, ?, 'skipped', ?)",
                        (art_id_d, source_d, SKIP_REASON_VERSION_CURRENT),
                    )
                    conn.commit()
                    continue

                if result.verdict is None:
                    # Mixed-batch failure on this slot. Row was just persisted
                    # with verdict=NULL via persist_layer2_verdicts; next tick
                    # will re-evaluate. Do NOT write ingestions row.
                    continue

                # Verdict must be 'ok' to reach ainsert. Future non-'ok' verdicts
                # (post 'scrape_fail' precedent) MUST add an explicit branch above —
                # do not fall through to ainsert on unknown verdict values.
                if result.verdict != "ok":
                    logger.warning(
                        "  [layer2] unexpected verdict=%r id=%s — skipping (future verdicts need explicit handling)",
                        result.verdict, art_id_d,
                    )
                    continue
                # Phase 17 BTIMEOUT-02 (2026-05-08) + T1 (2026-05-13) + T1-b1 (issue #2):
                # per-article timeout scales with text length AND image count.
                # Image count uses regex on body first (cheap), falls back to
                # disk count under $BASE/images/{md5(url)[:10]}/ when regex=0
                # (catches WeChat post-vision-description bodies that have
                # image markers stripped). Pre-T1 51-image article hit 900s
                # floor; post-fix gets proportional headroom.
                # D2 (issue #2 follow-up): row[7] is COALESCE(image_count, 0) from SELECT.
                # Pre-mig-011 rows = 0 -> falls through to T1 regex / T1-b1 disk via the
                # priority ladder inside _compute_article_budget_s.
                image_count_d = row[7]
                article_budget = _compute_article_budget_s(body or "", url=url_d, image_count=image_count_d)
                _img_count = _count_images_in_body(body or "", url=url_d)
                if _img_count >= 10 or article_budget > _SINGLE_CHUNK_FLOOR_S:
                    logger.info(
                        "  article budget=%ds (chunks=%d images=%d)",
                        article_budget,
                        max(1, len(body or "") // _CHUNK_SIZE_CHARS),
                        _img_count,
                    )
                remaining = get_remaining_budget(batch_start, total_batch_budget)
                effective_timeout = clamp_article_timeout(
                    article_budget, remaining, BATCH_SAFETY_MARGIN_S
                )
                if effective_timeout < article_budget:
                    clamped_count += 1
                    logger.info(
                        "  Clamped article timeout: %ds (article_budget=%ds remaining=%.0fs margin=%ds)",
                        effective_timeout, article_budget, remaining, BATCH_SAFETY_MARGIN_S,
                    )
                if remaining - BATCH_SAFETY_MARGIN_S <= 0:
                    safety_margin_triggered = True

                success, wall, doc_confirmed = await ingest_article(
                    source_d, url_d, dry_run, rag, effective_timeout=effective_timeout
                )
                if dry_run:
                    status = "dry_run"
                elif success and doc_confirmed:
                    status = "ok"
                    completed_times.append(wall)
                    timeout_histogram[_bucket_article_time(wall)] += 1
                else:
                    status = "failed"
                    if wall >= effective_timeout:
                        timed_out_count += 1
                        timeout_histogram["900s+"] += 1

                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                    "VALUES (?, ?, ?, ?)",
                    (art_id_d, source_d, status, SKIP_REASON_VERSION_CURRENT),
                )
                conn.commit()

                processed += 1
                if not dry_run:
                    logger.info(
                        "  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...",
                        SLEEP_BETWEEN_ARTICLES,
                    )
                    await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)

        # v3.5 ir-1 (LF-3.1) + ir-4 (LF-4.4): iterate over candidate_rows
        # (Layer 1 candidates only). Rejects already wrote skipped ingestions
        # rows above. Row tuple is now 7 cols
        # (id, source, title, url, source_name, body, summary). The legacy
        # 6-col shape (digest as last col) became the 7-col shape with
        # 'wechat'/'rss' inserted at row[1] and digest aliased to summary.
        for i, (art_id, source, title, url, account, body, summary, image_count_row) in enumerate(candidate_rows, 1):
            # quick-260511-mxc: strict hard cap. Pre-fix this check was
            # processed-only, so queued-but-not-yet-drained rows leaked past
            # the cap (up to LAYER2_BATCH_SIZE-1 = 4 extra). Charging the
            # in-flight queue against the budget at enqueue time makes
            # --max-articles a true per-article hard cap on ok+failed
            # (skipped statuses are excluded by their `continue` branches
            # below). See quick 260511-lmx investigation_findings.
            if max_articles is not None and (processed + len(layer2_queue)) >= max_articles:
                logger.info(
                    "max-articles cap reached (processed=%d + queued=%d >= %d); stopping --from-db loop.",
                    processed, len(layer2_queue), max_articles,
                )
                break

            logger.info("[%d/%d] [%s] %s", i, len(candidate_rows), account, title)

            # v3.5 ir-1 (LF-3.6): dry-run short-circuits per-article work.
            # Layer 1 already ran (cost intentional for filter-pipeline validation);
            # scrape, Layer 2, ainsert, ingestions writes all skipped here.
            if dry_run:
                logger.info(
                    "[dry-run] would-process candidate id=%d url=%s",
                    art_id, url[:60] if url else "<no-url>",
                )
                continue

            if not url:
                logger.warning("  Skipping — no URL")
                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                    "VALUES (?, ?, 'skipped', ?)",
                    (art_id, source, SKIP_REASON_VERSION_CURRENT),
                )
                conn.commit()
                continue

            # Phase 12 CKPT-03: batch-level checkpoint skip (DB-driven loop).
            ckpt_hash = get_article_hash(url)
            if has_stage(ckpt_hash, "text_ingest"):
                logger.info("checkpoint-skip: already-ingested hash=%s url=%s", ckpt_hash, url)
                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                    "VALUES (?, ?, 'skipped_ingested', ?)",
                    (art_id, source, SKIP_REASON_VERSION_CURRENT),
                )
                conn.commit()
                continue

            # Pre-scrape guard: if article was previously scraped (has scrape
            # checkpoint stage) but body is absent from DB (anomalous partial
            # state), skip instead of re-scraping. Avoids wasted Apify/CDP calls
            # (~150s/article) when the article was classified and filtered before.
            # Normal case: scrape checkpoint + body in DB → classify reuses DB
            # body without re-scrape (handled inside _classify_full_body).
            if has_stage(ckpt_hash, "scrape") and not body:
                logger.warning(
                    "pre-scrape skip: checkpoint scrape exists but body=NULL — "
                    "partial state, url=%s", url[:80])
                conn.execute(
                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                    "VALUES (?, ?, 'skipped', ?)",
                    (art_id, source, SKIP_REASON_VERSION_CURRENT),
                )
                conn.commit()
                continue

            # Graded classification probe (v3.5 MVP). Feature flag:
            # OMNIGRAPH_GRADED_CLASSIFY=1 (default OFF). Uses articles.digest
            # (99.6% coverage, ~50 chars) to detect OBVIOUSLY unrelated
            # articles BEFORE expensive scrape+classify. Threshold:
            # unrelated=True + confidence≥0.9. Fail-open on any error.
            GRADED_ENABLED = os.environ.get("OMNIGRAPH_GRADED_CLASSIFY", "0") == "1"
            if GRADED_ENABLED and normalized_topics and summary:
                probe = await _graded_probe(
                    title, account, summary, normalized_topics, api_key)
                if probe and probe.get("unrelated") and probe.get("confidence", 0) >= 0.9:
                    logger.info(
                        "graded-skip: art_id=%d source=%s conf=%.2f reason=%r",
                        art_id, source, probe["confidence"], probe.get("reason", ""))
                    logger.debug(
                        "graded-skip-detail: title=%r summary=%r",
                        title, summary.strip()[:200])
                    conn.execute(
                        "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
                        "VALUES (?, ?, 'skipped_graded', ?)",
                        (art_id, source, SKIP_REASON_VERSION_CURRENT))
                    conn.commit()
                    continue

            # v3.5 ir-1 (LF-3.2) + ir-4 (LF-4.4): Layer 1 already ran at the
            # chunk boundary above; this row is a candidate. Pre-scrape +
            # persist body so the next batch run skips re-scraping
            # (~75-90s/article saved) when downstream ingest fails.
            #
            # ir-4 dispatch:
            #   * KOL (source='wechat'): scrape only when body missing.
            #     scrape_url auto-routes to _scrape_wechat for mp.weixin
            #     URLs. _persist_scraped_body writes to articles.body.
            #   * RSS (source='rss'): scrape when body missing OR shorter
            #     than RSS_SCRAPE_THRESHOLD (rss_fetch sometimes only
            #     captured the <description> excerpt; too short for
            #     ainsert). scrape_url auto-routes to _scrape_generic for
            #     non-WeChat URLs. _persist_scraped_body writes to
            #     rss_articles.body.
            #
            # site_hint is intentionally NOT passed: ir-4's auto-route by
            # URL is correct for both sources. The W1 hardcoded
            # site_hint='wechat' would have forced WeChat cascade on
            # non-WeChat RSS URLs.
            if _needs_scrape(source, body):
                try:
                    from lib.scraper import scrape_url
                    scraped = await scrape_url(url)
                    if scraped and not scraped.summary_only:
                        persisted = _persist_scraped_body(
                            conn, art_id, source, scraped
                        )
                        if persisted:
                            body = persisted
                except Exception as e:  # noqa: BLE001 -- never block main flow
                    logger.warning(
                        "v3.5 pre-layer2 scrape/persist failed for "
                        "source=%s art_id=%s url=%s: %s",
                        source, art_id, url[:80], e,
                    )

            # v3.5 ir-2 (LF-3.2): defer Layer 2 + ainsert to batched drain.
            # Each successfully-scraped candidate is queued; the queue drains
            # at LAYER2_BATCH_SIZE boundaries and once after the loop ends.
            if not body:
                # Scrape failed earlier in this iteration; do NOT enqueue. The
                # article has no body to score; skip silently (next ingest
                # tick will see body=NULL and re-attempt scrape).
                logger.warning(
                    "  layer2 enqueue skipped — no body for art_id=%s; will retry next tick",
                    art_id,
                )
                continue

            # v3.5 ir-4 (LF-4.4): 7-col tuple (id, source, title, url,
            # source_name, body, summary) carried through the layer2 batch
            # so source-aware persist + INSERT continues to work.
            layer2_queue.append((
                (art_id, source, title, url, account, body, summary),
                body,
            ))

            if len(layer2_queue) >= LAYER2_BATCH_SIZE:
                await _drain_layer2_queue()
                # Phase 17 BTIMEOUT-01: early-exit if budget fully exhausted.
                if get_remaining_budget(batch_start, total_batch_budget) <= 0:
                    logger.warning(
                        "Batch budget exhausted (%ds elapsed >= %ds) — stopping loop; "
                        "remaining %d candidate(s) will show as not_started in metrics.",
                        int(time.time() - batch_start), total_batch_budget,
                        len(candidate_rows) - i,
                    )
                    break

            # Cap check post-drain: if max_articles cap reached, drain final
            # partial queue and break.
            if max_articles is not None and processed >= max_articles:
                logger.info(
                    "max-articles cap reached (%d) — draining final layer2 queue and stopping.",
                    max_articles,
                )
                await _drain_layer2_queue()
                break

        # Drain any remaining partial batch (size < LAYER2_BATCH_SIZE).
        await _drain_layer2_queue()

        logger.info(
            "Done — %d candidates processed (of %d total inputs)",
            processed, len(rows),
        )
    finally:
        if rag is not None:
            # D-10.09: drain pending Vision worker tasks before flushing storages.
            await _drain_pending_vision_tasks()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()

        # Phase 17 BTIMEOUT-04: emit metrics (always, even on early exit).
        metrics = _build_batch_timeout_metrics(
            total_budget=total_batch_budget,
            batch_start=batch_start,
            completed_times=completed_times,
            total_articles=len(rows),
            timed_out=timed_out_count,
            clamped_count=clamped_count,
            safety_margin_triggered=safety_margin_triggered,
            histogram=timeout_histogram,
        )
        logger.info("batch_timeout_metrics: %s", json.dumps(metrics))
        metrics_path = PROJECT_ROOT / "data" / f"batch_timeout_metrics_{timestamp}.json"
        metrics_path.parent.mkdir(exist_ok=True)
        metrics_path.write_text(
            json.dumps({"batch_timeout_metrics": metrics}, indent=2),
            encoding="utf-8",
        )
        logger.info("Metrics written to %s", metrics_path)
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest WeChat KOL articles into OmniGraph-Vault")
    parser.add_argument("--dry-run", action="store_true", help="List articles without ingesting")
    parser.add_argument("--days-back", type=int, default=90, help="How many days back to fetch (default: 90)")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles: per-account in scan mode; total cap in --from-db mode (default: 50)")
    parser.add_argument("--topic-filter", type=str, default=None, help="Required topic to include (e.g. 'AI agents')")
    parser.add_argument("--exclude-topics", type=str, default=None, help="Comma-separated topics to exclude (e.g. 'OpenClaw,crypto')")
    parser.add_argument("--min-depth", type=int, default=2, choices=[1, 2, 3], help="Minimum depth score 1-3 (default: 2)")
    parser.add_argument("--account", type=str, default=None, help="Only process this specific account name")
    parser.add_argument("--classifier", type=str, default="deepseek", choices=["deepseek", "gemini"],
                        help="Classifier model: deepseek (default) or gemini")
    parser.add_argument("--from-db", action="store_true",
                        help="Ingest articles already classified in kol_scan.db (requires --topic-filter)")
    parser.add_argument(
        "--batch-timeout", type=int, default=None,
        help="Total batch budget in seconds (default 28800 = 8h, covers 56-article batch at 441s/article Hermes baseline; overridden by OMNIGRAPH_BATCH_TIMEOUT_SEC env var)",
    )
    args = parser.parse_args()

    # Convert comma-separated string to list; strip whitespace; drop empty strings
    topic_keywords: list[str] | None = None
    if args.topic_filter:
        topic_keywords = [k.strip() for k in args.topic_filter.split(",") if k.strip()]
        if not topic_keywords:
            topic_keywords = None

    if args.from_db:
        # v3.5 (Quick 260507-lai patch): --topic-filter is silently ignored
        # post-V35-FOUND-03 (candidate SQL no longer references topics). The
        # previous required-flag check at this point is removed; topic_keywords
        # is coalesced to [] so ingest_from_db's internal `for t in topics`
        # loop receives an iterable in the no-filter case.
        coro = ingest_from_db(
            topic_keywords or [], args.min_depth, args.dry_run,
            batch_timeout=args.batch_timeout,
            max_articles=args.max_articles,
        )
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
            batch_timeout=args.batch_timeout,
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
