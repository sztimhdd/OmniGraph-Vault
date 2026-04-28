"""Wave 0 spike for Phase 5: Gemini embedding-2 feasibility probe.

Runs three probes on the remote WSL host and emits a Markdown report to stdout:

    1. Batch API availability — does ``client.batches.create_embeddings`` work on
       this API key? (Paid-tier required per SDK ExperimentalWarning.)
    2. Free-tier RPM ceiling — fire 120 sync ``embed_content`` calls in a
       60-second window, count 200s.
    3. Multimodal smoke — send one aggregated text+image ``embed_content`` call;
       check that we get back exactly one 768-dim vector.

Recommendation is ``proceed`` iff multimodal works AND ``rpm_ceiling`` >= 30;
otherwise ``block``.

Usage (on remote):

    ssh <host> "cd ~/OmniGraph-Vault && venv/bin/python scripts/phase5_wave0_spike.py" \
        > docs/spikes/embedding-002-contract.md
"""
from __future__ import annotations

import glob
import os
import socket
import sys
import time
import traceback
from datetime import date
from pathlib import Path

from google import genai
from google.genai import types


MODEL = "gemini-embedding-2"
OUTPUT_DIM = 768


def _emit(line: str = "") -> None:
    """Write a single Markdown line to stdout and flush."""
    print(line, flush=True)


def probe_batch_api(client: genai.Client) -> tuple[bool, str]:
    """Return (available, error_message). Never raises."""
    try:
        src = types.EmbeddingsBatchJobSource(
            inlined_requests=types.EmbedContentBatch(
                contents=["hello", "world"],
                config=types.EmbedContentConfig(output_dimensionality=OUTPUT_DIM),
            )
        )
        job = client.batches.create_embeddings(
            model=MODEL,
            src=src,
            config=types.CreateEmbeddingsBatchJobConfig(display_name="wave0-spike"),
        )
        # If we got here, submission succeeded. Job name is recorded for audit.
        return True, getattr(job, "name", "<no-name>")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def probe_rpm(client: genai.Client, total_calls: int = 120, window_s: float = 60.0) -> int:
    """Fire ``total_calls`` sync embed calls within a ~window_s budget.

    Returns count of successful (HTTP-200) calls completed within the first
    60 seconds of the run.
    """
    success = 0
    start = time.time()
    for i in range(total_calls):
        if time.time() - start >= window_s:
            break
        try:
            client.models.embed_content(
                model=MODEL,
                contents="ping",
                config=types.EmbedContentConfig(output_dimensionality=OUTPUT_DIM),
            )
            success += 1
        except Exception:
            # 429, 5xx, etc. — don't record, just continue.
            pass
    return success


def probe_multimodal(client: genai.Client) -> tuple[bool, str]:
    """Send one aggregated text+image embed call; verify shape.

    Returns (works, detail).
    """
    images_dir = Path.home() / ".hermes" / "omonigraph-vault" / "images"
    candidates = sorted(glob.glob(str(images_dir / "**" / "*.jpg"), recursive=True))
    if not candidates:
        return False, f"no *.jpg under {images_dir}"

    img_path = candidates[0]
    try:
        img_bytes = Path(img_path).read_bytes()
    except Exception as exc:
        return False, f"read error: {exc}"

    try:
        resp = client.models.embed_content(
            model=MODEL,
            contents=[
                "title: none | text: a diagram of system architecture",
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            ],
            config=types.EmbedContentConfig(output_dimensionality=OUTPUT_DIM),
        )
    except Exception as exc:
        return False, f"embed error: {type(exc).__name__}: {exc}"

    embeddings = getattr(resp, "embeddings", None) or []
    if not embeddings:
        return False, "no embeddings in response"

    values = embeddings[0].values
    if len(values) != OUTPUT_DIM:
        return False, f"unexpected dim {len(values)}"
    return True, f"image={img_path} dim={len(values)}"


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)
    host = socket.gethostname()

    # Header
    _emit("# Wave 0 Embedding Spike Report")
    _emit(f"date: {date.today().isoformat()}")
    _emit(f"host: {host}")
    _emit(f"model: {MODEL}")
    _emit()

    # Probe 1 — Batch API
    batch_available, batch_detail = probe_batch_api(client)
    _emit(f"batch_api_available: {str(batch_available).lower()}")
    _emit(f'batch_detail: "{batch_detail}"')

    # Probe 2 — RPM ceiling
    rpm_ceiling = probe_rpm(client)
    _emit(f"rpm_ceiling: {rpm_ceiling}")

    # Probe 3 — multimodal smoke
    try:
        mm_works, mm_detail = probe_multimodal(client)
    except Exception:
        mm_works = False
        mm_detail = traceback.format_exc().splitlines()[-1]
    _emit(f"multimodal_works: {str(mm_works).lower()}")
    _emit(f'multimodal_detail: "{mm_detail}"')

    # Recommendation
    if mm_works and rpm_ceiling >= 30:
        recommendation = "proceed"
    else:
        recommendation = "block"
    _emit(f"recommendation: {recommendation}")
    _emit()
    _emit("## Notes")
    if not batch_available:
        _emit(
            "- Batch API unavailable on this key. Wave 0b falls back to "
            "chunked sync embedding with per-call throttling."
        )
    if rpm_ceiling < 100:
        _emit(
            f"- Measured RPM ceiling ({rpm_ceiling}) is below 100. Keep "
            "``embedding_func_max_async=1`` and ``embedding_batch_num=20`` "
            "for the 18-doc re-embed."
        )
    if not mm_works:
        _emit(
            "- Multimodal smoke failed. Wave 0 cannot proceed to consolidation "
            "until this is resolved."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
