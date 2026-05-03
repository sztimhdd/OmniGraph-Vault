#!/usr/bin/env python3
"""Vertex AI embedding model-name live probe — HYG-01 (Phase 18-00).

Probes 3 candidate embedding model names against the paid-tier Vertex AI
endpoint on ``us-central1``. Exits 0 if ANY returns a non-zero-dim vector.
Exits 1 + optional Telegram alert if ALL 404.

Runs as a monthly Hermes cron (day 1 @ 08:00) per v3.3 HYG-01. Also a hard
prerequisite before any code change that touches ``_resolve_model()`` or the
``EMBEDDING_MODEL`` constant — Vertex catalog flipped twice in ~24h during
Wave 0 Close-Out (2026-05-02 / 05-03); visual review of comments was
empirically wrong in both directions.

Usage:
    python scripts/vertex_live_probe.py
    python scripts/vertex_live_probe.py --no-telegram
    python scripts/vertex_live_probe.py --json

Env (required for live run):
    GOOGLE_APPLICATION_CREDENTIALS  — SA JSON path (paid-tier)
    GOOGLE_CLOUD_PROJECT            — project ID

Env (optional, for alert delivery):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — reused from Phase 5 Wave 2.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import requests

CANDIDATES: tuple[str, ...] = (
    "gemini-embedding-2",
    "gemini-embedding-2-preview",
    "gemini-embedding-001",
)

LOCATION = "us-central1"
TEST_INPUT = "probe"


async def probe_one(client: Any, model: str) -> tuple[str, int | None, str | None]:
    """Return (model_name, dims_or_None, error_str_or_None)."""
    try:
        r = await client.aio.models.embed_content(model=model, contents=[TEST_INPUT])
        dims = len(r.embeddings[0].values)
        return (model, dims, None)
    except Exception as e:
        return (model, None, str(e)[:200])


async def run(candidates: tuple[str, ...]) -> list[tuple[str, int | None, str | None]]:
    """Instantiate Vertex client and probe each candidate serially."""
    from google import genai
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT unset — cannot probe Vertex AI")
    client = genai.Client(vertexai=True, project=project, location=LOCATION)
    return [await probe_one(client, m) for m in candidates]


def send_telegram(message: str) -> bool:
    """Deliver the alert message. Return True on 200, False otherwise."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[no-telegram-creds] {message}", file=sys.stderr)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": message},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[telegram-delivery-failed] {e}: {message}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-telegram", action="store_true",
                   help="suppress Telegram delivery on failure")
    p.add_argument("--json", action="store_true",
                   help="machine-readable output")
    args = p.parse_args()

    results = asyncio.run(run(CANDIDATES))
    greens = [(m, d) for (m, d, _) in results if d and d > 0]

    if args.json:
        payload = [{"model": m, "dims": d, "error": e} for (m, d, e) in results]
        print(json.dumps(payload, indent=2))
    else:
        for (m, d, e) in results:
            mark = f"✅ dims={d}" if d else f"❌ {e}"
            print(f"{mark:50s} {m}")

    if greens:
        if not args.json:
            print(f"[OK] {len(greens)} / {len(CANDIDATES)} candidate(s) green. First: {greens[0][0]}")
        return 0

    msg = (
        f"🔴 Vertex AI embedding probe FAILED ({LOCATION}). "
        f"All {len(CANDIDATES)} candidates 404:\n"
        + "\n".join(f"  {m}: {e}" for (m, _, e) in results)
        + "\nAction: run scripts/vertex_live_probe.py locally + ping human on OmniGraph-Vault."
    )
    print(msg, file=sys.stderr)
    if not args.no_telegram:
        send_telegram(msg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
