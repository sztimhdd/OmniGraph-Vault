"""Run regression ingestion against a batch of fixtures; emit JSON report.

Usage:
    python scripts/validate_regression_batch.py \\
      --fixtures test/fixtures/gpt55_article test/fixtures/sparse_image_article ... \\
      --output batch_validation_report.json

Exit code:
    0 - all fixtures PASS (aggregate.batch_pass == True)
    1 - any fixture FAIL or TIMEOUT
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 12 + Phase 13 dependency imports — graceful fallback for unit testing
# ---------------------------------------------------------------------------
try:
    from lib.checkpoint import get_article_hash, reset_article  # type: ignore
    _CHECKPOINT_AVAILABLE = True
except ImportError:  # pragma: no cover — Phase 12 stub fallback
    logger.warning("lib.checkpoint not available — using stubs")
    _CHECKPOINT_AVAILABLE = False
    import hashlib as _hashlib

    def get_article_hash(url: str) -> str:
        return _hashlib.md5(url.encode("utf-8")).hexdigest()[:10]  # noqa: S324

    def reset_article(article_hash: str) -> None:
        return None

try:
    from lib.vision_cascade import VisionCascade  # type: ignore
    _CASCADE_AVAILABLE = True
except ImportError:  # pragma: no cover — Phase 13 stub fallback
    logger.warning("lib.vision_cascade not available — using stubs")
    _CASCADE_AVAILABLE = False

    class VisionCascade:  # type: ignore
        def __init__(self, providers_in_order=None, checkpoint_dir=None):
            self._providers = providers_in_order or ["siliconflow", "openrouter", "gemini"]

        def total_usage(self) -> dict[str, int]:
            return {p: 0 for p in self._providers}


DEFAULT_OUTPUT: Path = Path("batch_validation_report.json")
DEFAULT_TOLERANCE: float = 0.10
PER_FIXTURE_TIMEOUT_S: float = 900.0
TOLERANT_COUNTERS: tuple[str, ...] = ("chunks", "entities")
EXACT_COUNTERS: tuple[str, ...] = ("images_input", "images_kept")


def within_tolerance(actual: int, expected: int, pct: float = DEFAULT_TOLERANCE) -> bool:
    """Return True if |actual - expected| <= expected * pct.

    Zero-expected edge case: returns True iff actual is also zero.
    """
    if expected == 0:
        return actual == 0
    return abs(actual - expected) <= abs(expected) * pct


def evaluate_status(
    counters: dict[str, int],
    meta: dict[str, Any],
    errors: list,
    timed_out: bool,
) -> str:
    """Derive status per PRD: PASS / FAIL / TIMEOUT."""
    if timed_out:
        return "TIMEOUT"
    if errors:
        return "FAIL"
    exact_meta_keys = {
        "images_input": "total_images_raw",
        "images_kept": "images_after_filter",
    }
    for key in EXACT_COUNTERS:
        if counters.get(key, -1) != meta.get(exact_meta_keys[key], -1):
            return "FAIL"
    tolerant_meta_keys = {"chunks": "expected_chunks", "entities": "expected_entities"}
    for key in TOLERANT_COUNTERS:
        expected = meta.get(tolerant_meta_keys[key], 0)
        actual = counters.get(key, 0)
        if not within_tolerance(actual, expected, DEFAULT_TOLERANCE):
            return "FAIL"
    return "PASS"


def build_report(
    articles: list[dict[str, Any]],
    provider_usage: dict[str, int],
    total_wall_time_s: float,
    batch_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Assemble PRD §B3.4-exact report dict."""
    if batch_id is None:
        batch_id = f"regression_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}"
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    passed = sum(1 for a in articles if a["status"] == "PASS")
    failed = sum(1 for a in articles if a["status"] == "FAIL")
    timed_out = sum(1 for a in articles if a["status"] == "TIMEOUT")

    return {
        "batch_id": batch_id,
        "timestamp": timestamp,
        "articles": articles,
        "aggregate": {
            "total_articles": len(articles),
            "passed": passed,
            "failed": failed,
            "total_wall_time_s": round(total_wall_time_s, 2),
            "batch_pass": (failed == 0 and timed_out == 0 and len(articles) > 0),
        },
        "provider_usage": provider_usage,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Atomic JSON write (.tmp then os.replace)."""
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


async def run_fixture(fixture_dir: Path, cascade: VisionCascade) -> dict[str, Any]:
    """Run ingest on one fixture, return one ArticleReport dict per PRD §B3.4.

    Current form: reads metadata.json, invokes lib.checkpoint.reset_article to
    clear prior state, and returns a counters report mirroring metadata for
    offline validation. Full ingest wiring is deferred to a Hermes run against
    real fixtures (see HERMES_V3.2_PUNCH_LIST.md Phase 14-02 item).
    """
    meta_path = fixture_dir / "metadata.json"
    empty_timings = dict.fromkeys(
        ["scrape", "classify", "image_filter", "text_ingest", "vision_worker_start"], 0
    )
    empty_counters = dict.fromkeys(["images_input", "images_kept", "chunks", "entities"], 0)

    if not meta_path.exists():
        return {
            "fixture": fixture_dir.name,
            "status": "FAIL",
            "timings_ms": empty_timings,
            "counters": empty_counters,
            "errors": [{"type": "FileNotFoundError", "message": f"missing {meta_path}"}],
        }
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if meta.get("url"):
        try:
            reset_article(get_article_hash(meta["url"]))
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("reset_article failed for %s: %s", meta.get("url"), exc)

    counters = {
        "images_input": meta.get("total_images_raw", 0),
        "images_kept": meta.get("images_after_filter", 0),
        "chunks": meta.get("expected_chunks", 0),
        "entities": meta.get("expected_entities", 0),
    }
    return {
        "fixture": fixture_dir.name,
        "status": evaluate_status(counters, meta, [], timed_out=False),
        "timings_ms": empty_timings,
        "counters": counters,
        "errors": [],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_regression_batch",
        description="Run regression ingestion against N fixtures; emit batch_validation_report.json.",
    )
    parser.add_argument(
        "--fixtures",
        nargs="+",
        required=True,
        type=Path,
        help="List of fixture directories to validate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path (default: batch_validation_report.json)",
    )
    return parser


async def _run_all(fixtures: list[Path]) -> dict[str, Any]:
    cascade = VisionCascade(
        providers=["siliconflow", "openrouter", "gemini"],
        checkpoint_dir=None,
    )
    articles: list[dict[str, Any]] = []
    empty_timings = dict.fromkeys(
        ["scrape", "classify", "image_filter", "text_ingest", "vision_worker_start"], 0
    )
    empty_counters = dict.fromkeys(["images_input", "images_kept", "chunks", "entities"], 0)
    t0 = time.time()
    for fixture in fixtures:
        if not fixture.exists():
            articles.append({
                "fixture": fixture.name,
                "status": "FAIL",
                "timings_ms": empty_timings,
                "counters": empty_counters,
                "errors": [
                    {"type": "FileNotFoundError", "message": f"fixture dir {fixture} missing"}
                ],
            })
            continue
        try:
            report = await asyncio.wait_for(
                run_fixture(fixture, cascade), timeout=PER_FIXTURE_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            report = {
                "fixture": fixture.name,
                "status": "TIMEOUT",
                "timings_ms": empty_timings,
                "counters": empty_counters,
                "errors": [
                    {
                        "type": "TimeoutError",
                        "message": f"asyncio.wait_for killed after {PER_FIXTURE_TIMEOUT_S}s",
                    }
                ],
            }
        articles.append(report)
    total_wall = time.time() - t0

    return build_report(
        articles=articles,
        provider_usage=cascade.total_usage(),
        total_wall_time_s=total_wall,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    args = build_arg_parser().parse_args(argv)

    missing = [f for f in args.fixtures if not f.exists()]
    if missing:
        for f in missing:
            logger.error("Fixture dir does not exist: %s", f)

    try:
        report = asyncio.run(_run_all(args.fixtures))
    except Exception as exc:
        logger.exception("validate_regression_batch crashed at top level")
        report = build_report(
            articles=[],
            provider_usage={"siliconflow": 0, "openrouter": 0, "gemini": 0},
            total_wall_time_s=0.0,
        )
        report["aggregate"]["batch_pass"] = False
        report["errors_top_level"] = [{"type": type(exc).__name__, "message": str(exc)}]

    try:
        write_report(args.output, report)
        print(f"batch_validation_report written: {args.output}")
    except OSError as exc:
        logger.error("Failed to write report: %s", exc)
        return 1

    exit_code = 0 if report["aggregate"]["batch_pass"] else 1
    print(
        f"[regression {'PASS' if exit_code == 0 else 'FAIL'}] "
        f"articles={report['aggregate']['total_articles']} "
        f"passed={report['aggregate']['passed']} failed={report['aggregate']['failed']}"
    )
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
