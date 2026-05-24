"""ar-4 Wave 2 milestone-close smoke driver (TEST-05).

Runs the full Agentic-RAG-v1 pipeline against the canonical Chinese-language
deep-dive query and verifies all 5 pass conditions:

  (a) >=3 inline ![desc](http://localhost:8765/...) images
  (b) state.verified.confidence >= 60
  (c) wall time <= 120 s
  (d) no stage with status="failed" in JSONL telemetry
  (e) answer language is Chinese

Pre-flight checklist (operator-side, must hold before invocation):
  - TAVILY_API_KEY in ~/.hermes/.env  (primary web search)
  - BRAVE_SEARCH_API_KEY in ~/.hermes/.env  (fallback web search)
  - Image HTTP server on port 8765 running (auto-started if BASE_IMAGE_DIR populated)
  - ~/.hermes/omonigraph-vault/lightrag_storage/ populated with Hermes Harness articles
  - venv activated (Linux: source venv/bin/activate)

Invocation: python scripts/smoke_milestone.py
Outputs:
  - JSON verdict on stdout (one object with per-condition pass/fail + final all_pass)
  - Exit 0 if all 5 pass; 1 otherwise
  - Telemetry JSONL: .scratch/smoke-telemetry-<ts>.jsonl
  - Markdown archive: $BASE_DIR/synthesis_archive/<ts>_hermes-harness.md

Outside lib/research/ -> exempt from CONTRACT-01/CONTRACT-02 (per ar-4-CONTEXT.md).
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so top-level `config.py` (consumed by
# lib/llm_deepseek.py and friends) resolves regardless of how the driver is
# invoked. The smoke driver lives in scripts/ so default sys.path[0] is wrong.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from omnigraph.research import research
from omnigraph.research.config import from_env

QUERY = "Hermes Harness 深度解析"
TIMEOUT_S = 180.0  # safety net; condition (c) gate is 120s


def _slugify_query(q: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "_", q)
    return s.strip("_")[:64]


async def _amain() -> int:
    scratch = Path(".scratch")
    scratch.mkdir(exist_ok=True)
    ts = int(time.time())
    telemetry_path = scratch / f"smoke-telemetry-{ts}.jsonl"

    cfg = dataclasses.replace(from_env(), telemetry_jsonl=telemetry_path)

    archive_dir = cfg.rag_working_dir.parent / "synthesis_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{ts}_{_slugify_query(QUERY)}.md"

    t0 = time.time()
    try:
        result = await asyncio.wait_for(research(QUERY, cfg), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        verdict = {
            "all_pass": False,
            "fatal": f"smoke driver wallclock exceeded {TIMEOUT_S}s safety timeout",
            "c_elapsed_s": elapsed,
            "telemetry_path": str(telemetry_path),
        }
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
        return 1
    elapsed = time.time() - t0

    archive_path.write_text(result.markdown, encoding="utf-8")

    # condition (a): inline localhost:8765 image count
    image_count = len(re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", result.markdown))

    # condition (b): verifier confidence
    confidence = (
        result.state.verified.confidence
        if result.state.verified is not None
        else 0.0
    )

    # condition (d): no stage with status="failed" in telemetry
    failed_stages: list[str] = []
    if telemetry_path.exists():
        for line in telemetry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event_type") == "stage_end" and ev.get("status") == "failed":
                failed_stages.append(ev.get("stage", "<unknown>"))

    # condition (e): answer language Chinese (CJK ratio over non-image, non-URL text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)|https?://\S+", "", result.markdown)
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    non_ws = sum(1 for c in text if not c.isspace())
    cjk_ratio = cjk / max(non_ws, 1)

    verdict = {
        "query": QUERY,
        "telemetry_path": str(telemetry_path),
        "markdown_archive_path": str(archive_path),
        "markdown_chars": len(result.markdown),
        "a_image_count": image_count,
        "a_pass": image_count >= 3,
        "b_confidence": confidence,
        "b_pass": confidence >= 60.0,
        "c_elapsed_s": elapsed,
        "c_pass": elapsed <= 120.0,
        "d_failed_stages": failed_stages,
        "d_pass": len(failed_stages) == 0,
        "e_cjk_ratio": round(cjk_ratio, 3),
        "e_pass": cjk_ratio >= 0.5,
    }
    verdict["all_pass"] = all(v for k, v in verdict.items() if k.endswith("_pass"))

    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if verdict["all_pass"] else 1


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    rc = asyncio.run(_amain())
    sys.exit(rc)


if __name__ == "__main__":
    main()
