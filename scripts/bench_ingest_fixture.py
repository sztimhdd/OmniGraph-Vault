"""Phase 11 Plan 11-00: benchmark harness skeleton.

Reads a pre-scraped fixture (article.md + metadata.json + images/) from disk and
runs a 5-stage timing scaffold (scrape, classify, image_download, text_ingest,
async_vision_start) WITHOUT performing any WeChat network scrape.

Plan 11-00 scope:
    - CLI entry point with --fixture / --output args
    - Pure helper functions: _read_fixture, _compute_article_hash,
      _utc_now_iso, _build_result_json, _write_result
    - SiliconFlow balance precheck (D-11.05) — 4 branches covered by tests
    - Atomic JSON write (D-11.07 — tmp + os.rename)
    - Stub text_ingest (gate_pass=false in this plan)

Plan 11-02 scope (follow-up):
    - Populate stage timings with real LightRAG + DeepSeek + embedding calls
    - Populate counters from LightRAG internal state
    - aquery-based gate.aquery_returns_fixture_chunk evaluation

Entry point:
    python scripts/bench_ingest_fixture.py [--fixture <path>] [--output <json>]

Decisions referenced:
    - D-11.01 — local CLI reads fixture from disk (no network scrape)
    - D-11.03 — 5 stage timings
    - D-11.05 — SiliconFlow balance precheck via GET /v1/user/info
    - D-11.07 — benchmark_result.json exact schema + atomic write
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_FIXTURE: Path = Path("test/fixtures/gpt55_article")
DEFAULT_OUTPUT: Path = DEFAULT_FIXTURE / "benchmark_result.json"

# Estimated SiliconFlow cost for single-article vision ingest (CNY).
# Source: 11-PRD.md — 0.036 CNY for 28-image fixture single run.
ESTIMATED_COST_CNY: float = 0.036

# SiliconFlow user-info endpoint (D-11.05).
SILICONFLOW_URL: str = "https://api.siliconflow.cn/v1/user/info"

# HTTP timeout for balance precheck (seconds).
BALANCE_TIMEOUT_S: float = 10.0


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable)
# ---------------------------------------------------------------------------


def _compute_article_hash(url: str) -> str:
    """Return md5(url)[:10] — matches ingest_wechat.py:689 article_hash shape."""
    # nosec B324 — md5 used as stable identity hash, not a cryptographic primitive
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:10]  # noqa: S324


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 with 'Z' suffix (not '+00:00')."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_fixture(fixture_path: Path) -> dict[str, Any]:
    """Read article.md + metadata.json + images/ from a fixture directory.

    No network I/O — pure disk reads. Raises FileNotFoundError if fixture is
    incomplete (missing article.md or metadata.json).

    Returns dict with keys:
        title, url, markdown, image_paths, text_chars,
        total_images_raw, images_after_filter
    """
    fixture_path = Path(fixture_path)
    article_md = fixture_path / "article.md"
    metadata_json = fixture_path / "metadata.json"
    images_dir = fixture_path / "images"

    if not article_md.exists():
        raise FileNotFoundError(f"fixture article.md not found at {article_md}")
    if not metadata_json.exists():
        raise FileNotFoundError(f"fixture metadata.json not found at {metadata_json}")

    markdown = article_md.read_text(encoding="utf-8")
    metadata = json.loads(metadata_json.read_text(encoding="utf-8"))

    image_paths: list[Path] = []
    if images_dir.exists() and images_dir.is_dir():
        image_paths = sorted(
            p for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        )

    return {
        "title": metadata.get("title", ""),
        "url": metadata.get("url", ""),
        "markdown": markdown,
        "image_paths": image_paths,
        "text_chars": metadata.get("text_chars", len(markdown)),
        "total_images_raw": metadata.get("total_images_raw", len(image_paths)),
        "images_after_filter": metadata.get("images_after_filter", len(image_paths)),
    }


def _build_result_json(
    *,
    article_hash: str,
    fixture_path: str,
    timings: dict[str, int],
    counters: dict[str, int],
    gate_flags: dict[str, bool],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the PRD-exact benchmark_result.json payload.

    gate_pass = all(gate_flags.values()). Timestamp is computed at call time.
    """
    return {
        "article_hash": article_hash,
        "fixture_path": fixture_path,
        "timestamp_utc": _utc_now_iso(),
        "stage_timings_ms": {
            "scrape": int(timings.get("scrape", 0)),
            "classify": int(timings.get("classify", 0)),
            "image_download": int(timings.get("image_download", 0)),
            "text_ingest": int(timings.get("text_ingest", 0)),
            "async_vision_start": int(timings.get("async_vision_start", 0)),
        },
        "counters": {
            "images_input": int(counters.get("images_input", 0)),
            "images_kept": int(counters.get("images_kept", 0)),
            "images_filtered": int(counters.get("images_filtered", 0)),
            "chunks_extracted": int(counters.get("chunks_extracted", 0)),
            "entities_ingested": int(counters.get("entities_ingested", 0)),
        },
        "gate": {
            "text_ingest_under_2min": bool(gate_flags.get("text_ingest_under_2min", False)),
            "aquery_returns_fixture_chunk": bool(
                gate_flags.get("aquery_returns_fixture_chunk", False)
            ),
            "zero_crashes": bool(gate_flags.get("zero_crashes", False)),
        },
        "gate_pass": bool(all(gate_flags.values())) if gate_flags else False,
        "warnings": list(warnings),
        "errors": list(errors),
    }


def _write_result(path: Path, result: dict[str, Any]) -> None:
    """Atomic JSON write: open <path>.tmp, json.dump, os.rename to <path>.

    On any failure during write, clean up .tmp and re-raise the original
    exception so the final path is NEVER left in a partial state.
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.rename(tmp_path, path)
    except Exception:
        # Clean up the tmp file so no partial write is left behind
        with contextlib.suppress(OSError):
            if tmp_path.exists():
                tmp_path.unlink()
        raise


# ---------------------------------------------------------------------------
# Stage timing context manager
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _time_stage(name: str, timings: dict[str, int]) -> Iterator[None]:
    """Context manager that records elapsed ms (int) into timings[name].

    Uses time.perf_counter() — monotonic, sub-ms resolution (per D-11.02).
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        timings[name] = int((time.perf_counter() - t0) * 1000)


# ---------------------------------------------------------------------------
# SiliconFlow balance precheck (D-11.05)
# ---------------------------------------------------------------------------


def _balance_precheck() -> dict[str, Any]:
    """Call SiliconFlow /v1/user/info and emit a structured warning.

    Four branches (per D-11.05):
        1. SILICONFLOW_API_KEY unset → event=balance_precheck_skipped
        2. balance >= ESTIMATED_COST_CNY → event=balance_warning, status=ok
        3. balance < ESTIMATED_COST_CNY → event=balance_warning, status=insufficient_for_batch
        4. HTTP / JSON / timeout error → event=balance_precheck_failed

    Non-fatal for v3.1 gate — always returns a dict, never raises.
    """
    api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not api_key:
        return {
            "event": "balance_precheck_skipped",
            "provider": "siliconflow",
            "reason": "api_key_unset",
        }

    try:
        req = urllib.request.Request(
            SILICONFLOW_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=BALANCE_TIMEOUT_S) as resp:  # noqa: S310
            raw = resp.read()
        payload = json.loads(raw)
        # SiliconFlow response shape: {"data": {"balance": <str|number>}, ...}
        # TODO(11-02): confirm field path against live response; `data.balance` is
        # the documented field per https://docs.siliconflow.cn as of 2026-04.
        balance_raw = payload.get("data", {}).get("balance", 0)
        balance = float(balance_raw)
        status = "ok" if balance >= ESTIMATED_COST_CNY else "insufficient_for_batch"
        return {
            "event": "balance_warning",
            "provider": "siliconflow",
            "balance_cny": balance,
            "estimated_cost_cny": ESTIMATED_COST_CNY,
            "status": status,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            ValueError, TimeoutError, OSError) as exc:
        return {
            "event": "balance_precheck_failed",
            "provider": "siliconflow",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Benchmark runner (stub — Plan 11-02 populates with real work)
# ---------------------------------------------------------------------------


async def _run_benchmark(fixture_path: Path) -> dict[str, Any]:
    """Run the 5-stage scaffold against a fixture directory.

    Plan 11-00 scope: stages are stubs (no real LightRAG / DeepSeek / vision).
    Plan 11-02 will replace stubs with real work.

    Returns a dict with keys:
        article_hash, timings, counters, gate_flags, warnings, errors, fixture
    """
    timings: dict[str, int] = {}
    counters: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fixture_data: dict[str, Any] = {}
    article_hash = ""

    # Balance precheck (non-fatal, runs before any expensive stage)
    warnings.append(_balance_precheck())

    # Stage 1: scrape — fixture read (no network per D-11.01)
    try:
        with _time_stage("scrape", timings):
            fixture_data = _read_fixture(fixture_path)
        article_hash = _compute_article_hash(fixture_data.get("url", ""))
    except Exception as exc:  # noqa: BLE001
        errors.append({"stage": "scrape", "type": type(exc).__name__, "message": str(exc)})
        # Unsurvivable failure — zero-fill remaining stage keys for schema stability
        for stage in ("classify", "image_download", "text_ingest", "async_vision_start"):
            timings.setdefault(stage, 0)

    if fixture_data:
        # Populate counters from fixture metadata (Plan 11-02 will augment with
        # LightRAG-derived chunks_extracted / entities_ingested).
        counters["images_input"] = int(fixture_data.get("total_images_raw", 0))
        counters["images_kept"] = int(fixture_data.get("images_after_filter", 0))
        counters["images_filtered"] = counters["images_input"] - counters["images_kept"]
        counters["chunks_extracted"] = 0  # Plan 11-02
        counters["entities_ingested"] = 0  # Plan 11-02

        # Stage 2: classify — STUB (Plan 11-02 calls DeepSeek classifier)
        with _time_stage("classify", timings):
            await asyncio.sleep(0)

        # Stage 3: image_download — STUB (Plan 11-02 copies fixture images into
        # runtime article_dir; no HTTP per D-11.03)
        with _time_stage("image_download", timings):
            await asyncio.sleep(0)

        # Stage 4: text_ingest — STUB (Plan 11-02 calls rag.ainsert(full_content))
        # Intentionally left as a no-op in this plan; gate.text_ingest_under_2min
        # will be False because text_ingest is effectively a no-op.
        with _time_stage("text_ingest", timings):
            await asyncio.sleep(0)

        # Stage 5: async_vision_start — STUB (Plan 11-02 spawns Vision task)
        with _time_stage("async_vision_start", timings):
            await asyncio.sleep(0)

    # Gate evaluation (stub-mode — Plan 11-02 fills in real values)
    # In stub mode, text_ingest_under_2min is False because we haven't actually
    # ingested anything. aquery is also False. zero_crashes depends on errors[].
    gate_flags = {
        "text_ingest_under_2min": False,
        "aquery_returns_fixture_chunk": False,
        "zero_crashes": len(errors) == 0,
    }

    return {
        "article_hash": article_hash,
        "timings": timings,
        "counters": counters,
        "gate_flags": gate_flags,
        "warnings": warnings,
        "errors": errors,
        "fixture_data": fixture_data,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_ingest_fixture",
        description=(
            "Benchmark OmniGraph-Vault ingest pipeline against a pre-scraped "
            "fixture (no WeChat network scrape). Writes benchmark_result.json."
        ),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help=(
            "Path to the fixture directory (default: test/fixtures/gpt55_article/). "
            "Must contain article.md, metadata.json, and images/ subdir."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Path to write benchmark_result.json (default: "
            "<fixture>/benchmark_result.json)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 iff gate_pass is True, else 1."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    fixture_path: Path = args.fixture
    output_path: Path = args.output

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    article_hash = ""
    timings: dict[str, int] = dict.fromkeys(
        ["scrape", "classify", "image_download", "text_ingest", "async_vision_start"],
        0,
    )
    counters: dict[str, int] = dict.fromkeys(
        ["images_input", "images_kept", "images_filtered",
         "chunks_extracted", "entities_ingested"],
        0,
    )
    gate_flags = {
        "text_ingest_under_2min": False,
        "aquery_returns_fixture_chunk": False,
        "zero_crashes": False,
    }

    # Wrap top-level to satisfy D-11.06 (zero unhandled exceptions escape main).
    try:
        bench_state = asyncio.run(_run_benchmark(fixture_path))
        article_hash = bench_state["article_hash"]
        timings.update(bench_state["timings"])
        counters.update(bench_state["counters"])
        gate_flags = bench_state["gate_flags"]
        warnings = bench_state["warnings"]
        errors = bench_state["errors"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("benchmark harness crashed at top level")
        errors.append({
            "stage": "main",
            "type": type(exc).__name__,
            "message": str(exc),
        })
        gate_flags["zero_crashes"] = False

    result = _build_result_json(
        article_hash=article_hash,
        fixture_path=str(fixture_path),
        timings=timings,
        counters=counters,
        gate_flags=gate_flags,
        warnings=warnings,
        errors=errors,
    )

    try:
        _write_result(output_path, result)
        print(f"benchmark_result written: {output_path}")
    except OSError as exc:
        logger.exception("failed to write benchmark_result.json")
        print(f"ERROR: failed to write {output_path}: {exc}", file=sys.stderr)
        return 1

    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
