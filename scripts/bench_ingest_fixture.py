"""Phase 11 Plan 11-02: benchmark harness wired to real LightRAG.

Reads a pre-scraped fixture (article.md + metadata.json + images/) from disk,
runs the real ingest pipeline stages (classify via DeepSeek, text ingest via
rag.ainsert, aquery validation, background Vision worker), and writes a
PRD-exact benchmark_result.json atomically.

This is the milestone v3.1 CLOSING harness. It does NOT perform any WeChat
network scrape — all article content comes from the fixture on disk.

Entry point:
    python scripts/bench_ingest_fixture.py [--fixture <path>] [--output <json>]

Decisions referenced:
    - D-11.01 — local CLI reads fixture from disk (no network scrape)
    - D-11.02 — text_ingest_ms < 120000 is THE gate measurement
    - D-11.03 — 5 stage timings (scrape, classify, image_download,
      text_ingest, async_vision_start); async_vision_start measures
      time-to-spawn only, NOT worker completion
    - D-11.04 — aquery with query="GPT-5.5 benchmark results",
      QueryParam(mode="hybrid", top_k=3); pass = file_path match OR
      signature-fragment substring match
    - D-11.05 — SiliconFlow balance precheck via GET /v1/user/info
    - D-11.06 — zero crashes: top-level try/except; JSON always written
    - D-11.07 — PRD-exact schema + atomic write (tmp + os.rename)
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# D-09.01 (TIMEOUT-01): LightRAG reads LLM_TIMEOUT at dataclass-definition
# time. Must be set BEFORE any `from lightrag import ...` in the import
# chain. setdefault preserves any explicit override.
os.environ.setdefault("LLM_TIMEOUT", "600")

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

# D-11.04 pass criteria — signature fragments from the fixture article.
# Any one of these substrings appearing in the aquery response body
# satisfies `gate.aquery_returns_fixture_chunk` when a direct file_path
# match is not available on the response object.
_AQUERY_SIGNATURE_FRAGMENTS: tuple[str, ...] = ("GPT-5.5", "Opus 4.7", "OpenAI")

# D-11.04 — exact query string (LITERAL, do not parameterize).
_AQUERY_QUERY_STRING: str = "GPT-5.5 benchmark results"

# Vision worker drain timeout — matches D-10.09 batch orchestrator behavior.
_VISION_DRAIN_TIMEOUT_S: float = 120.0


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable, no network / LightRAG / LLM)
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
        3. balance < ESTIMATED_COST_CNY → event=balance_warning,
           status=insufficient_for_batch
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
# DeepSeek classify wrapper (D-11.03 classify stage)
# ---------------------------------------------------------------------------


def _classify_with_deepseek(title: str, body: str) -> tuple[dict | None, int]:
    """Classify the article via full-body DeepSeek.

    Returns (classification_dict, elapsed_ms). On any failure (no API key,
    transport error, JSON parse failure), returns (None, elapsed_ms). Never
    raises — callers treat classify as non-fatal for the v3.1 gate.

    Late imports inside the body keep `--help` invocation fast and avoid
    pulling in the DeepSeek client when the key is absent.
    """
    t0 = time.perf_counter()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "dummy":
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return None, elapsed_ms

    try:
        # Late import — only pulled in when classify is actually exercised.
        from batch_classify_kol import (
            _build_fullbody_prompt,
            _call_deepseek_fullbody,
        )
        prompt = _build_fullbody_prompt(title=title, body=body)
        result = _call_deepseek_fullbody(prompt, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DeepSeek classify failed: %s", exc)
        result = None

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return result, elapsed_ms


# ---------------------------------------------------------------------------
# Fixture image prep (D-11.03 image_download stage)
# ---------------------------------------------------------------------------


def _copy_fixture_images(
    fixture_images_dir: Path, article_hash: str
) -> dict[str, Path]:
    """Copy fixture images into the runtime article directory.

    Returns the {remote_url: local_path} map that matches what
    `ingest_wechat.ingest_article` produces post-download. Each image file
    under `fixture_images_dir` is copied to
    `<BASE_IMAGE_DIR>/<article_hash>/<filename>`.

    The "remote URL" used as the dict key mirrors the local image server
    URL that LightRAG embedding expects
    (http://localhost:8765/<hash>/<name>) — this keeps the embedding path's
    in-band multimodal pattern working even though we never hit a network.
    """
    from config import BASE_IMAGE_DIR  # late-import to honor load_env() timing

    article_dir = Path(BASE_IMAGE_DIR) / article_hash
    article_dir.mkdir(parents=True, exist_ok=True)

    url_to_path: dict[str, Path] = {}
    if not fixture_images_dir.exists():
        return url_to_path

    for src in sorted(fixture_images_dir.iterdir()):
        if not src.is_file():
            continue
        if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            continue
        dst = article_dir / src.name
        shutil.copyfile(src, dst)
        local_url = f"http://localhost:8765/{article_hash}/{src.name}"
        url_to_path[local_url] = dst

    return url_to_path


# ---------------------------------------------------------------------------
# Text-first ingest (D-11.02 text_ingest stage, D-11.03 gate measurement)
# ---------------------------------------------------------------------------


async def _ingest_text_first(
    rag: Any,
    url: str,
    title: str,
    markdown: str,
    url_to_path: dict[str, Path],
    article_hash: str,
) -> tuple[str, str]:
    """Synthesize full_content in the ingest_wechat.ingest_article shape
    and call rag.ainsert(full_content, ids=[doc_id]).

    Returns (full_content, doc_id). Raises on ainsert failure — caller
    captures the exception into errors[] (D-11.06).
    """
    # Late imports so `--help` doesn't pay the LightRAG init cost.
    from image_pipeline import localize_markdown
    from ingest_wechat import _clear_pending_doc_id, _register_pending_doc_id

    full_content = f"# {title}\n\nURL: {url}\nTime: \n\n{markdown}"
    full_content = localize_markdown(
        full_content, url_to_path, article_hash=article_hash
    )
    for i, (url_img, path) in enumerate(url_to_path.items()):
        local_url = f"http://localhost:8765/{article_hash}/{path.name}"
        full_content += f"\n\n[Image {i} Reference]: {local_url}"

    doc_id = f"wechat_{article_hash}"
    _register_pending_doc_id(article_hash, doc_id)
    try:
        await rag.ainsert(full_content, ids=[doc_id])
    finally:
        # D-09.05: clear tracker AFTER ainsert attempt (success OR failure).
        # If ainsert failed we still want the tracker cleared because our
        # finally-block-level drain does its own cleanup of rag state.
        _clear_pending_doc_id(article_hash)
    return full_content, doc_id


# ---------------------------------------------------------------------------
# aquery validation (D-11.04)
# ---------------------------------------------------------------------------


def _response_contains_fixture_chunk(response: Any, doc_id: str) -> bool:
    """Evaluate D-11.04 pass criteria on an aquery response.

    Passes when EITHER:
      (a) response exposes chunk metadata with a file_path matching doc_id, OR
      (b) response text contains at least one of _AQUERY_SIGNATURE_FRAGMENTS.
    """
    # Stringify the response for substring scans. LightRAG's response is
    # typically a string ("mix" / "hybrid" modes return formatted text).
    # For robustness we also handle dict-ish shapes that some modes return.
    response_text = ""
    if isinstance(response, str):
        response_text = response
    elif isinstance(response, dict):
        # Some LightRAG modes return {"response": "...", "chunks": [...]} etc.
        response_text = str(response.get("response", response))
        # Check chunk metadata for file_path match (criterion a)
        for chunk in response.get("chunks", []) or []:
            if isinstance(chunk, dict) and chunk.get("file_path") == doc_id:
                return True
    else:
        # Fall back to str() for arbitrary objects
        response_text = str(response)

    # Criterion b: signature-fragment substring match (case-sensitive —
    # these are proper nouns / model names).
    for frag in _AQUERY_SIGNATURE_FRAGMENTS:
        if frag in response_text:
            return True

    return False


async def _validate_semantic_query(
    rag: Any, doc_id: str
) -> tuple[bool, int]:
    """Run the D-11.04 aquery and evaluate the pass criteria.

    Returns (passed, elapsed_ms). elapsed_ms is informational only — NOT
    part of stage_timings_ms per PRD.
    """
    from lightrag.lightrag import QueryParam  # late import

    t0 = time.perf_counter()
    response = await rag.aquery(
        query=_AQUERY_QUERY_STRING,
        param=QueryParam(mode="hybrid", top_k=3),
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = _response_contains_fixture_chunk(response, doc_id)
    return passed, elapsed_ms


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


async def _run_benchmark(fixture_path: Path) -> dict[str, Any]:
    """Run the 5-stage real-pipeline benchmark against a fixture directory.

    Returns a dict with keys:
        article_hash, timings, counters, gate_flags, warnings, errors,
        fixture_data
    """
    timings: dict[str, int] = {}
    counters: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fixture_data: dict[str, Any] = {}
    article_hash = ""
    gate_flags = {
        "text_ingest_under_2min": False,
        "aquery_returns_fixture_chunk": False,
        "zero_crashes": True,
    }

    # Balance precheck (non-fatal, runs before any expensive stage)
    warnings.append(_balance_precheck())

    # Stage 1: scrape — fixture read (no network per D-11.01)
    try:
        with _time_stage("scrape", timings):
            fixture_data = _read_fixture(fixture_path)
        article_hash = _compute_article_hash(fixture_data.get("url", ""))
    except Exception as exc:  # noqa: BLE001
        errors.append({"stage": "scrape", "type": type(exc).__name__, "message": str(exc)})
        gate_flags["zero_crashes"] = False
        for stage in ("classify", "image_download", "text_ingest", "async_vision_start"):
            timings.setdefault(stage, 0)
        return {
            "article_hash": article_hash,
            "timings": timings,
            "counters": counters,
            "gate_flags": gate_flags,
            "warnings": warnings,
            "errors": errors,
            "fixture_data": fixture_data,
        }

    # Populate counters from fixture metadata
    counters["images_input"] = int(fixture_data.get("total_images_raw", 0))
    counters["images_kept"] = int(fixture_data.get("images_after_filter", 0))
    counters["images_filtered"] = counters["images_input"] - counters["images_kept"]
    # Chunk-count heuristic per D-11.07 Claude's Discretion item 2:
    # LightRAG default chunk size is ~1200 tokens ≈ 4800 chars. Emit a
    # best-effort heuristic; 11-02 does not introspect LightRAG internals.
    counters["chunks_extracted"] = max(1, len(fixture_data["markdown"]) // 4800)
    counters["entities_ingested"] = -1  # sentinel — LightRAG state not cleanly accessible

    # Late import — avoid LightRAG init on --help and keep import failure
    # contained to the benchmark run (D-11.06: captured into errors[]).
    try:
        from ingest_wechat import _vision_worker_impl, get_rag
    except Exception as exc:  # noqa: BLE001
        errors.append({
            "stage": "import",
            "type": type(exc).__name__,
            "message": str(exc),
        })
        gate_flags["zero_crashes"] = False
        # Zero-fill remaining stage timings so the schema is stable
        for stage in ("classify", "image_download", "text_ingest", "async_vision_start"):
            timings.setdefault(stage, 0)
        return {
            "article_hash": article_hash,
            "timings": timings,
            "counters": counters,
            "gate_flags": gate_flags,
            "warnings": warnings,
            "errors": errors,
            "fixture_data": fixture_data,
        }

    rag: Any = None
    vision_task: "asyncio.Task | None" = None
    doc_id = f"wechat_{article_hash}"

    try:
        rag = await get_rag(flush=True)

        # Stage 2: classify (non-fatal — warning on failure per D-11.06)
        with _time_stage("classify", timings):
            classify_result, _ = _classify_with_deepseek(
                fixture_data["title"], fixture_data["markdown"]
            )
        if classify_result is None:
            warnings.append({
                "event": "classify_skipped",
                "reason": "deepseek_unavailable_or_failed",
            })

        # Stage 3: image_download (copy from fixture)
        with _time_stage("image_download", timings):
            url_to_path = _copy_fixture_images(
                fixture_path / "images", article_hash
            )

        # Stage 4: text_ingest — THE gate measurement
        with _time_stage("text_ingest", timings):
            _full_content, doc_id = await _ingest_text_first(
                rag, fixture_data["url"], fixture_data["title"],
                fixture_data["markdown"], url_to_path, article_hash,
            )
        gate_flags["text_ingest_under_2min"] = timings["text_ingest"] < 120000

        # Stage 5: async_vision_start — spawn Vision worker (spawn time only)
        with _time_stage("async_vision_start", timings):
            vision_task = asyncio.create_task(
                _vision_worker_impl(
                    rag=rag,
                    article_hash=article_hash,
                    url_to_path=url_to_path,
                    title=fixture_data["title"],
                    filter_stats=None,
                    download_input_count=len(url_to_path),
                    download_failed=0,
                )
            )

        # aquery validation (POST text_ingest, NOT counted in stage_timings_ms)
        passed, _q_ms = await _validate_semantic_query(rag, doc_id)
        gate_flags["aquery_returns_fixture_chunk"] = passed

    except Exception as exc:  # noqa: BLE001
        gate_flags["zero_crashes"] = False
        # Attribute the error to the most recent stage that was in flight.
        # If text_ingest is absent from timings, the failure was in
        # text_ingest itself (never reached the closing `)`; timings is
        # populated in the finally of _time_stage so we CAN rely on the key
        # being present — use "text_ingest" as the default attribution).
        stage = "text_ingest"
        if "async_vision_start" not in timings and "text_ingest" in timings:
            stage = "async_vision_start"
        errors.append({
            "stage": stage,
            "type": type(exc).__name__,
            "message": str(exc),
        })
        logger.exception("Benchmark run failed during %s", stage)

    finally:
        # Drain Vision task with D-10.09 120s cap. Vision failure is D-10.08
        # non-fatal — so only emit a warning, never fail the gate from here.
        if vision_task is not None:
            try:
                await asyncio.wait_for(vision_task, timeout=_VISION_DRAIN_TIMEOUT_S)
            except asyncio.TimeoutError:
                vision_task.cancel()
                try:
                    await vision_task
                except (asyncio.CancelledError, Exception):
                    pass
                warnings.append({
                    "event": "vision_worker_drain_timeout",
                    "timeout_s": _VISION_DRAIN_TIMEOUT_S,
                })
            except Exception as vexc:  # noqa: BLE001
                warnings.append({
                    "event": "vision_worker_exception",
                    "error": f"{type(vexc).__name__}: {vexc}",
                })

        # Finalize storages so any deferred vdb/graphml writes land on disk.
        if rag is not None:
            try:
                await rag.finalize_storages()
            except Exception as fexc:  # noqa: BLE001
                warnings.append({
                    "event": "finalize_storages_failed",
                    "error": str(fexc),
                })

    # Zero-fill any stage timing keys that failures short-circuited
    for stage in ("scrape", "classify", "image_download",
                  "text_ingest", "async_vision_start"):
        timings.setdefault(stage, 0)

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


def _print_gate_summary(result: dict[str, Any]) -> None:
    """Print a final PASS/FAIL line to stdout (user-facing)."""
    gate_pass = result["gate_pass"]
    text_ingest_ms = result["stage_timings_ms"]["text_ingest"]
    stamp = "PASS" if gate_pass else "FAIL"
    aq = "Y" if result["gate"]["aquery_returns_fixture_chunk"] else "N"
    ti = "Y" if result["gate"]["text_ingest_under_2min"] else "N"
    zc = "Y" if result["gate"]["zero_crashes"] else "N"
    err_count = len(result.get("errors", []))
    warn_count = len(result.get("warnings", []))
    print(
        f"[bench {stamp}] text_ingest_ms={text_ingest_ms} "
        f"gate[ti={ti} aq={aq} zc={zc}] errors={err_count} warnings={warn_count}"
    )


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

    _print_gate_summary(result)
    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
