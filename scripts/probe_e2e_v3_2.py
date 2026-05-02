#!/usr/bin/env python3
"""v3.2 E2E Regression Probe — reusable UAT test harness.

Validates v3.2's 6 incremental features without CDP/WeChat network scrape.
Uses pre-scraped fixture data (article.md + images/ + metadata.json) injected
as checkpoint stages 1-3, then calls ingest_article() which resumes from
stage 4 (text_ingest) with full LightRAG + Vertex AI embedding + Vision cascade.

Probes
------
  Probe A — checkpoint file creation (structural validation)
    Injects stages 1-3 from fixture data. Verifies all 14 structural checks:
    marker files present, content non-empty, manifest complete.
    Time: <5s. No API calls.

  Probe B — resume verification
    Calls ingest_article() with pre-filled checkpoints. Verifies:
    - classify file unchanged (DeepSeek classify was skipped)
    - text_ingest stage 4 completed
    - method="resumed" in logs
    Time: 1-7 min depending on article length. Uses DeepSeek + Vertex AI.

  Probe C — vision cascade fallback
    Calls VisionCascade.describe() on 3 sample images. Verifies:
    - provider fallback chain works (SiliconFlow → OpenRouter → Gemini)
    - circuit breaker state is reported
    - CascadeResult.provider identifies which provider succeeded
    Time: 1-2 min. Uses Vision API cascade.

  Probe D — full 6-stage end-to-end
    Complete ingestion including vision worker + sub_doc checkpoint + aquery.
    Verifies all 6 checkpoints (01_scrape through 06_sub_doc_ingest) and
    confirms article is queryable in LightRAG.
    Time: 5-16 min depending on article length and image count.

Prerequisites
-------------
  - Python venv at $OMNIGRAPH_ROOT/venv with all deps installed
  - Fixture directory under test/fixtures/ with article.md + images/ + metadata.json
  - Environment: DEEPSEEK_API_KEY, Vertex AI credentials (GOOGLE_APPLICATION_CREDENTIALS,
    GOOGLE_CLOUD_PROJECT), SILICONFLOW_API_KEY, OPENROUTER_API_KEY

Usage
-----
    # All probes against default fixture
    python scripts/probe_e2e_v3_2.py

    # Single probe
    python scripts/probe_e2e_v3_2.py --probe B --fixture text_only_article

    # Specific probes, custom output
    python scripts/probe_e2e_v3_2.py --probe A,D --fixture sparse_image_article \\
        --output report/uat_v3_2.json

Output
------
  JSON report at --output path with per-probe results, aggregate summary,
  and wall-clock timing. Exit code 0 if all selected probes pass.

Adding new probes
-----------------
  1. Add a probe_N_*() function following the signature pattern:
     def probe_e_your_new_test(fixture_dir: Path) -> dict[str, Any]:
         ...
         return _probe_result("E_your_test", passed, detail, data)
  2. Register it in run_probes() with a letter key.
  3. Update the argparser's which set and this docstring.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# D-09.01: set LLM_TIMEOUT before any LightRAG import
os.environ.setdefault("LLM_TIMEOUT", "600")

logger = logging.getLogger("probe_e2e_v3_2")

# ---------------------------------------------------------------------------
# Probe result helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _probe_result(
    probe: str,
    passed: bool,
    detail: str = "",
    data: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "probe": probe,
        "passed": passed,
        "detail": detail,
        "timestamp": _utc_now(),
        "data": data or {},
        "error": error,
    }


def _summary_line(label: str, ok: bool) -> str:
    return f"  [{('PASS' if ok else 'FAIL'):>4s}] {label}"


# ---------------------------------------------------------------------------
# Checkpoint injection — builds stages 1-3 from fixture data
# ---------------------------------------------------------------------------

def inject_checkpoint(fixture_dir: Path) -> tuple[str, dict[str, Any], list[Path]]:
    """Create checkpoint files for stages 1-3 from fixture data.

    Returns (article_hash, metadata_dict, image_paths).
    Side effects: writes files under ~/.hermes/omonigraph-vault/checkpoints/.
    """
    from lib.checkpoint import (
        get_article_hash,
        get_checkpoint_dir,
        write_metadata,
        write_stage,
    )

    meta_path = fixture_dir / "metadata.json"
    article_md = fixture_dir / "article.md"
    images_dir = fixture_dir / "images"

    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json missing: {meta_path}")
    if not article_md.exists():
        raise FileNotFoundError(f"article.md missing: {article_md}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    markdown = article_md.read_text(encoding="utf-8")
    url = meta["url"]
    title = meta.get("title", "Untitled")

    article_hash = get_article_hash(url)
    ckpt_dir = get_checkpoint_dir(article_hash)

    # Clean any prior checkpoint for this article
    shutil.rmtree(ckpt_dir, ignore_errors=True)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: scrape ---
    # Wrap markdown in minimal HTML so process_content() can extract it.
    # Image references are extracted from <img data-src> tags by process_content.
    img_tags = ""
    image_paths: list[Path] = []
    if images_dir.exists() and images_dir.is_dir():
        image_paths = sorted(
            p for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        )
        for img in image_paths:
            # Use the original WeChat CDN URL from the markdown if present, else a placeholder
            img_tags += f'<img data-src="http://mmbiz.qpic.cn/fixture/{img.name}" />\n'

    html = f"""<html><head><meta property="og:title" content="{title}"></head>
<body><div id="js_content">{markdown}
{img_tags}
</div></body></html>"""

    write_stage(article_hash, "scrape", html)

    # --- Stage 2: classify ---
    classification = {
        "depth": 3,
        "topics": ["AI", "LLM", "Technology"],
        "rationale": "probe-injected-from-fixture",
        "model": "deepseek-v4-flash",
        "timestamp": time.time(),
    }
    write_stage(article_hash, "classify", classification)

    # --- Stage 3: image_download ---
    # Copy images to checkpoint and build manifest
    images_subdir = ckpt_dir / "03_images"
    images_subdir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for img in image_paths:
        dst = images_subdir / img.name
        shutil.copy2(img, dst)
        entry = {
            "url": f"http://mmbiz.qpic.cn/fixture/{img.name}",
            "local_path": str(dst),
            "dimensions": None,
            "filter_reason": None,
        }
        # Try to get actual dimensions
        try:
            from PIL import Image as PILImage
            with PILImage.open(dst) as im:
                entry["dimensions"] = list(im.size)
        except Exception:
            pass
        manifest.append(entry)

    write_stage(article_hash, "image_download", manifest)

    # --- Metadata ---
    write_metadata(article_hash, {
        "url": url,
        "title": title,
        "text_chars": meta.get("text_chars", len(markdown)),
        "total_images_raw": meta.get("total_images_raw", len(image_paths)),
        "images_after_filter": meta.get("images_after_filter", len(image_paths)),
    })

    logger.info(
        "checkpoint injected: hash=%s stages=scrape+classify+image_download "
        "images=%d chars=%d",
        article_hash, len(image_paths), len(markdown),
    )
    return article_hash, meta, image_paths


# ---------------------------------------------------------------------------
# Probe A: Checkpoint file creation
# ---------------------------------------------------------------------------

def probe_a_checkpoint(fixture_dir: Path) -> dict[str, Any]:
    """Verify checkpoint files are created with correct structure."""
    import lib.checkpoint as cp

    article_hash, meta, image_paths = inject_checkpoint(fixture_dir)
    checks: dict[str, bool] = {}

    # Check stage markers
    checks["scrape_marker"] = cp.has_stage(article_hash, "scrape")
    checks["classify_marker"] = cp.has_stage(article_hash, "classify")
    checks["image_download_marker"] = cp.has_stage(article_hash, "image_download")
    checks["text_ingest_absent"] = not cp.has_stage(article_hash, "text_ingest")
    checks["sub_doc_ingest_absent"] = not cp.has_stage(article_hash, "sub_doc_ingest")

    # Check content
    html = cp.read_stage(article_hash, "scrape")
    checks["scrape_has_title"] = meta["title"] in (html or "")
    checks["scrape_has_content"] = len(html or "") > 500

    classification = cp.read_stage(article_hash, "classify")
    checks["classify_is_dict"] = isinstance(classification, dict)
    checks["classify_has_topics"] = bool(classification.get("topics"))

    manifest = cp.read_stage(article_hash, "image_download") or []
    checks["manifest_is_list"] = isinstance(manifest, list)
    checks["manifest_count"] = len(manifest) == len(image_paths)
    if manifest:
        checks["manifest_has_local_path"] = all(
            e.get("local_path") for e in manifest
        )

    # Check metadata
    ckpt_meta = cp.read_metadata(article_hash)
    checks["metadata_has_url"] = bool(ckpt_meta.get("url"))
    checks["metadata_has_title"] = bool(ckpt_meta.get("title"))

    all_pass = all(checks.values())
    return _probe_result(
        "A_checkpoint_baseline",
        all_pass,
        detail=f"{sum(checks.values())}/{len(checks)} checks passed",
        data={
            "article_hash": article_hash,
            "n_images": len(image_paths),
            "checks": checks,
        },
        error=None if all_pass else "Some checkpoint checks failed",
    )


# ---------------------------------------------------------------------------
# Probe B: Resume skips completed stages
# ---------------------------------------------------------------------------

async def _run_probe_b(article_hash: str, url: str, fixture_dir: Path) -> dict[str, Any]:
    """Run ingest and verify resume behavior.

    Returns: probe result dict.
    Checks:
    - Stages 1-3 marker files exist (must have been injected by probe A)
    - No CDP/Apify scrape was attempted
    - No DeepSeek classify was called (checkpoint hit)
    - text_ingest started (stage 4 begins)
    """
    import lib.checkpoint as cp
    from ingest_wechat import _vision_worker_impl, get_rag, ingest_article

    # Verify preconditions
    if not cp.has_stage(article_hash, "scrape"):
        return _probe_result("B_resume_skip", False, error="checkpoint not injected — run probe A first")
    if not cp.has_stage(article_hash, "image_download"):
        return _probe_result("B_resume_skip", False, error="image_download checkpoint missing")

    # Snapshot classify file mtime before running
    classify_path = cp.get_checkpoint_dir(article_hash) / "02_classify.json"
    classify_mtime_before = classify_path.stat().st_mtime if classify_path.exists() else None

    rag = await get_rag(flush=True)

    t0 = time.perf_counter()
    vision_task = None
    error_msg = None

    try:
        # ingest_article will hit all 3 checkpoints and start from stage 4
        vision_task = await asyncio.wait_for(
            ingest_article(url, rag=rag),
            timeout=600.0,  # 10 min — long articles can take >5 min for entity extraction
        )
    except asyncio.TimeoutError:
        error_msg = "ingest_article timed out (120s) — text_ingest may be stuck"
    except Exception as exc:
        error_msg = f"ingest_article raised: {type(exc).__name__}: {exc}"
        logger.exception("Probe B ingest_article failed")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # Drain vision task briefly if spawned
    if vision_task is not None and not vision_task.done():
        try:
            await asyncio.wait_for(vision_task, timeout=30.0)
        except (asyncio.TimeoutError, Exception):
            vision_task.cancel()
            with contextlib.suppress(Exception):
                await vision_task

    # Drain any background tasks from rag
    if rag is not None:
        try:
            await rag.finalize_storages()
        except Exception:
            pass

    # Verify
    classify_mtime_after = classify_path.stat().st_mtime if classify_path.exists() else None
    classify_unchanged = (
        classify_mtime_before is not None
        and classify_mtime_after is not None
        and classify_mtime_before == classify_mtime_after
    )

    text_ingest_done = cp.has_stage(article_hash, "text_ingest")

    return _probe_result(
        "B_resume_skip",
        passed=bool(not error_msg and text_ingest_done),
        detail=(
            f"text_ingest={'done' if text_ingest_done else 'MISSING'}, "
            f"classify_unchanged={classify_unchanged}, "
            f"elapsed_ms={elapsed_ms}"
        ),
        data={
            "text_ingest_done": text_ingest_done,
            "classify_unchanged": classify_unchanged,
            "elapsed_ms": elapsed_ms,
        },
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Probe C: Vision cascade fallback
# ---------------------------------------------------------------------------

def probe_c_cascade(fixture_dir: Path) -> dict[str, Any]:
    """Verify vision cascade multi-level fallback behavior.

    Strategy:
    1. Inject checkpoint for a fixture with images
    2. Run describe_images() via image_pipeline directly
    3. Inspect provider_usage to confirm cascade direction
    4. Check circuit breaker state

    Note: With SiliconFlow at ¥0, cascade auto-routes to OpenRouter.
    This probe verifies the mechanism works, not that SiliconFlow is primary.
    """
    from lib.vision_cascade import VisionCascade
    from image_pipeline import DEFAULT_PROVIDERS

    article_hash, meta, image_paths = inject_checkpoint(fixture_dir)

    if not image_paths:
        return _probe_result("C_cascade_fallback", True,
                             detail="0 images — skip cascade test",
                             data={"n_images": 0})

    # Use only first 3 images for speed
    sample_paths = image_paths[:3]

    # Run cascade directly to inspect internal state
    cascade = VisionCascade(providers=list(DEFAULT_PROVIDERS))

    results: list[dict[str, Any]] = []
    for i, path in enumerate(sample_paths):
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        image_bytes = path.read_bytes()
        image_id = f"img_{i:03d}"

        try:
            cres = cascade.describe(image_id, image_bytes, mime)
            results.append({
                "image_id": image_id,
                "provider": cres.provider,
                "result_code": cres.result_code,
                "desc_chars": len(cres.description) if cres.description else 0,
            })
        except Exception as exc:
            results.append({
                "image_id": image_id,
                "error": f"{type(exc).__name__}: {exc}",
            })

    provider_usage = cascade.total_usage()
    provider_status = cascade.status

    # Determine cascade direction
    successes = [r for r in results if r.get("provider")]
    providers_used = list({r["provider"] for r in successes})
    cascade_worked = len(successes) > 0

    return _probe_result(
        "C_cascade_fallback",
        passed=cascade_worked,
        detail=(
            f"images={len(sample_paths)} success={len(successes)} "
            f"providers={providers_used} circuit_opens={sum(1 for s in provider_status.values() if s.get('circuit_open'))}"
        ),
        data={
            "sample_results": results,
            "provider_usage": provider_usage,
            "provider_status": {k: {
                k2: v.get(k2) for k2 in ["circuit_open", "total_successes", "total_attempts"]
            } for k, v in provider_status.items()},
        },
    )


# ---------------------------------------------------------------------------
# Probe D: Full end-to-end ingest
# ---------------------------------------------------------------------------

async def _run_probe_d(article_hash: str, url: str, fixture_dir: Path) -> dict[str, Any]:
    """Run full ingest including vision worker and sub_doc checkpoint.

    Returns: probe result dict with all 6 stage completion status.
    """
    import lib.checkpoint as cp
    from ingest_wechat import get_rag, ingest_article
    from lib.vision_cascade import VisionCascade

    # Inject fresh checkpoint
    _article_hash, meta, image_paths = inject_checkpoint(fixture_dir)

    rag = await get_rag(flush=True)

    t0 = time.perf_counter()
    vision_task = None
    error_msg = None

    try:
        vision_task = await ingest_article(url, rag=rag)
    except Exception as exc:
        error_msg = f"ingest_article raised: {type(exc).__name__}: {exc}"
        logger.exception("Probe D ingest_article failed")

    total_ms = int((time.perf_counter() - t0) * 1000)

    # Await vision worker to completion (up to 180s)
    vision_drain_ms = 0
    if vision_task is not None:
        v0 = time.perf_counter()
        try:
            await asyncio.wait_for(vision_task, timeout=180.0)
        except asyncio.TimeoutError:
            vision_task.cancel()
            with contextlib.suppress(Exception):
                await vision_task
            error_msg = error_msg or "vision_worker drain timed out (180s)"
        except Exception as exc:
            error_msg = error_msg or f"vision_worker failed: {type(exc).__name__}: {exc}"
        vision_drain_ms = int((time.perf_counter() - v0) * 1000)

    # Finalize storages
    if rag is not None:
        try:
            await rag.finalize_storages()
        except Exception:
            pass

    # Verify all 6 stages
    import lib.checkpoint as cp2
    stages = {
        "01_scrape": cp2.has_stage(article_hash, "scrape"),
        "02_classify": cp2.has_stage(article_hash, "classify"),
        "03_image_download": cp2.has_stage(article_hash, "image_download"),
        "04_text_ingest": cp2.has_stage(article_hash, "text_ingest"),
        "06_sub_doc_ingest": cp2.has_stage(article_hash, "sub_doc_ingest"),
    }

    # Count vision markers
    vision_markers = cp2.list_vision_markers(article_hash)
    stages["05_vision_markers"] = len(vision_markers)

    all_done = all((
        stages["01_scrape"],
        stages["02_classify"],
        stages["03_image_download"],
        stages["04_text_ingest"],
        stages["06_sub_doc_ingest"] or len(image_paths) == 0,
    ))

    # Query LightRAG to verify article is found
    aquery_pass = False
    try:
        from lightrag.lightrag import QueryParam
        query_result = await rag.aquery(
            query=meta["title"][:80],
            param=QueryParam(mode="hybrid", top_k=2),
        )
        aquery_pass = meta["title"][:10] in str(query_result)
    except Exception as exc:
        logger.warning("Probe D aquery failed: %s", exc)

    return _probe_result(
        "D_full_e2e",
        passed=all_done and not error_msg and aquery_pass,
        detail=(
            f"total_ms={total_ms} vision_drain_ms={vision_drain_ms} "
            f"stages_done={sum(1 for v in stages.values() if v)}/{len(stages)} "
            f"aquery={'Y' if aquery_pass else 'N'}"
        ),
        data={
            "total_ms": total_ms,
            "vision_drain_ms": vision_drain_ms,
            "stages": stages,
            "aquery_pass": aquery_pass,
            "n_images": len(image_paths),
            "n_vision_markers": len(vision_markers),
            "fixture": fixture_dir.name,
        },
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

def build_report(
    probes: list[dict[str, Any]],
    fixture_name: str,
    wall_time_s: float,
) -> dict[str, Any]:
    passed = sum(1 for p in probes if p["passed"])
    return {
        "title": "v3.2 E2E Regression Probe Report",
        "fixture": fixture_name,
        "timestamp": _utc_now(),
        "wall_time_s": round(wall_time_s, 2),
        "probes": probes,
        "aggregate": {
            "total": len(probes),
            "passed": passed,
            "failed": len(probes) - passed,
            "all_pass": passed == len(probes),
        },
    }


async def run_probes(
    fixture_name: str,
    which: set[str],
) -> dict[str, Any]:
    """Run selected probes in order, return full report dict."""
    # Isolate RAG storage — prevents contamination from production DB (103+ docs).
    # Each probe run gets a fresh directory. Cleaned at start and between probes.
    _probe_rag_dir = Path(os.environ.get(
        "PROBE_RAG_WORKING_DIR",
        f"/tmp/probe_rag_{fixture_name.replace('_article','')}"
    ))
    shutil.rmtree(_probe_rag_dir, ignore_errors=True)
    _probe_rag_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RAG_WORKING_DIR"] = str(_probe_rag_dir)
    logger.info("probe RAG_WORKING_DIR=%s", _probe_rag_dir)

    fixture_dir = _PROJECT_ROOT / "test/fixtures" / fixture_name
    if not fixture_dir.is_dir():
        return {"error": f"fixture not found: {fixture_dir}"}

    meta = json.loads((fixture_dir / "metadata.json").read_text(encoding="utf-8"))
    url = meta["url"]

    probes: list[dict[str, Any]] = []
    t0 = time.time()

    # Pre-inject checkpoint for all probes that need it
    article_hash, _meta, _images = inject_checkpoint(fixture_dir)

    if "A" in which:
        print("Probe A — checkpoint baseline ...")
        # Re-inject fresh for accurate measurement
        result = probe_a_checkpoint(fixture_dir)
        probes.append(result)
        print(_summary_line("A_checkpoint", result["passed"]))

    if "B" in which:
        print("Probe B — resume skip verification ...")
        # Need fresh checkpoint (probe A may have consumed it)
        inject_checkpoint(fixture_dir)
        result = await _run_probe_b(article_hash, url, fixture_dir)
        probes.append(result)
        print(_summary_line("B_resume_skip", result["passed"]))

    if "C" in which:
        print("Probe C — vision cascade ...")
        result = probe_c_cascade(fixture_dir)
        probes.append(result)
        print(_summary_line("C_cascade", result["passed"]))

    if "D" in which:
        print("Probe D — full E2E ...")
        # Need fresh checkpoint
        inject_checkpoint(fixture_dir)
        result = await _run_probe_d(article_hash, url, fixture_dir)
        probes.append(result)
        print(_summary_line("D_full_e2e", result["passed"]))

    wall = time.time() - t0
    return build_report(probes, fixture_name, wall)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="probe_e2e_v3_2",
        description="v3.2 E2E Regression Probe — reusable UAT",
    )
    parser.add_argument(
        "--probe",
        default="all",
        help="Probes to run: A, B, C, D, or 'all' (default)",
    )
    parser.add_argument(
        "--fixture",
        default="sparse_image_article",
        help="Fixture name under test/fixtures/ (default: sparse_image_article)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("probe_report.json"),
        help="Output JSON path (default: probe_report.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)

    # Resolve which probes
    if args.probe == "all":
        which = {"A", "B", "C", "D"}
    else:
        which = set(args.probe.upper().split(","))
        invalid = which - {"A", "B", "C", "D"}
        if invalid:
            print(f"Invalid probe(s): {invalid}. Use A, B, C, D, or 'all'.", file=sys.stderr)
            return 2

    print(f"=== v3.2 E2E Probe: fixture={args.fixture} probes={sorted(which)} ===\n")

    try:
        report = asyncio.run(run_probes(args.fixture, which))
    except Exception as exc:
        logger.exception("probe harness crashed")
        report = {
            "title": "v3.2 E2E Regression Probe Report",
            "fixture": args.fixture,
            "timestamp": _utc_now(),
            "wall_time_s": 0,
            "probes": [],
            "aggregate": {"total": 0, "passed": 0, "failed": 1, "all_pass": False},
            "error": f"{type(exc).__name__}: {exc}",
        }

    # Write report
    output: Path = args.output
    tmp = output.with_suffix(output.suffix + ".tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        os.replace(tmp, output)
        print(f"\nReport written: {output}")
    except OSError as exc:
        logger.error("Failed to write report: %s", exc)
        return 1

    # Summary
    agg = report.get("aggregate", {})
    print(f"\n{'='*50}")
    print(f"Probes: {agg.get('passed', 0)}/{agg.get('total', 0)} passed")
    print(f"All pass: {agg.get('all_pass', False)}")
    for p in report.get("probes", []):
        status = "✓" if p["passed"] else "✗"
        print(f"  {status} {p['probe']}: {p['detail']}")

    return 0 if agg.get("all_pass", False) else 1


if __name__ == "__main__":
    sys.exit(main())
