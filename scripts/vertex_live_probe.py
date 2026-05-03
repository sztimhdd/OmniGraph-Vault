#!/usr/bin/env python3
"""Vertex AI embedding model-name live probe — HYG-01 (Phase 18-00).

Probes a 2×3 matrix: (global, us-central1) × (gemini-embedding-2,
gemini-embedding-2-preview, gemini-embedding-001) = 6 combinations.
Each combination has a known-good/known-bad expectation baked in. The
probe exits 1 + alerts via Telegram only when a known-good combo
returns 404 (or any non-OK); known-bad 404s are silent (expected).

Known-good/bad matrix (2026-05-03):

    (global,      gemini-embedding-2)         -> GA, expected OK
    (global,      gemini-embedding-2-preview) -> not on global, expected 404
    (global,      gemini-embedding-001)       -> GA legacy, expected OK
    (us-central1, gemini-embedding-2)         -> not in regional, expected 404
    (us-central1, gemini-embedding-2-preview) -> preview regional, expected OK
    (us-central1, gemini-embedding-001)       -> GA legacy, expected OK

Runs as a monthly Hermes cron (day 1 @ 08:00) per v3.3 HYG-01. Also a
hard prerequisite before any code change that touches the embedding
model name — Vertex catalog naming is endpoint-dependent, and a single
endpoint probe historically yielded misleading results. ~6 paid calls
per run (still cheap).

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

LOCATIONS: tuple[str, ...] = ("global", "us-central1")

# Endpoint × model expectation matrix. True = expect OK (dims>0); False =
# expect 404. Known-bad combos returning 404 are SILENT — that is the
# expected state. Known-good combos returning 404 trigger an alert.
known_good: dict[tuple[str, str], bool] = {
    ("global", "gemini-embedding-2"): True,
    ("global", "gemini-embedding-2-preview"): False,
    ("global", "gemini-embedding-001"): True,
    ("us-central1", "gemini-embedding-2"): False,
    ("us-central1", "gemini-embedding-2-preview"): True,
    ("us-central1", "gemini-embedding-001"): True,
}

TEST_INPUT = "probe"


async def probe_one(
    client: Any, model: str
) -> tuple[str, int | None, str | None]:
    """Return (model_name, dims_or_None, error_str_or_None)."""
    try:
        r = await client.aio.models.embed_content(
            model=model, contents=[TEST_INPUT]
        )
        dims = len(r.embeddings[0].values)
        return (model, dims, None)
    except Exception as e:
        return (model, None, str(e)[:200])


async def run(
    locations: tuple[str, ...],
    candidates: tuple[str, ...],
) -> list[tuple[str, str, int | None, str | None]]:
    """Instantiate a Vertex client per location and probe each candidate.

    Returns a flat list of (location, model, dims_or_None, error_or_None)
    tuples, in (location, model) iteration order.
    """
    from google import genai

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT unset — cannot probe Vertex AI")

    out: list[tuple[str, str, int | None, str | None]] = []
    for loc in locations:
        client = genai.Client(vertexai=True, project=project, location=loc)
        for model in candidates:
            m, dims, err = await probe_one(client, model)
            out.append((loc, m, dims, err))
    return out


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


def _classify(
    loc: str, model: str, dims: int | None
) -> tuple[str, bool]:
    """Return (human_mark, alert_bool) for a single (loc, model) result.

    Alert fires only when known_good[(loc, model)] is True and the combo
    did NOT return a positive dim (i.e. it 404'd a combo that should work).
    """
    expected_ok = known_good.get((loc, model), False)
    actual_ok = bool(dims and dims > 0)
    if expected_ok and actual_ok:
        return (f"✅ dims={dims} (expected OK)", False)
    if expected_ok and not actual_ok:
        return ("❌ 404 (expected OK, ALERT)", True)
    if not expected_ok and actual_ok:
        # Unexpected success on a known-bad combo — catalog shifted.
        # Treat as alert (informational signal that our table is stale).
        return (f"⚠️ dims={dims} (expected 404 — catalog may have shifted)", True)
    # not expected_ok and not actual_ok → benign 404
    return ("➖ 404 (expected 404, ok)", False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--no-telegram",
        action="store_true",
        help="suppress Telegram delivery on failure",
    )
    p.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    args = p.parse_args()

    results = asyncio.run(run(LOCATIONS, CANDIDATES))

    # Classify each combo and detect alerts.
    alerts: list[tuple[str, str, str | None]] = []
    per_combo: list[dict[str, Any]] = []
    for (loc, model, dims, err) in results:
        mark, alert = _classify(loc, model, dims)
        expected_ok = known_good.get((loc, model), False)
        per_combo.append(
            {
                "loc": loc,
                "model": model,
                "dims": dims,
                "error": err,
                "expected_ok": expected_ok,
                "alert": alert,
            }
        )
        if alert:
            alerts.append((loc, model, err))
        if not args.json:
            print(f"{mark:50s} {loc:12s} {model}")

    if args.json:
        print(json.dumps(per_combo, indent=2))

    if not alerts:
        if not args.json:
            known_good_count = sum(1 for v in known_good.values() if v)
            print(
                f"[OK] all {known_good_count} known-good combos green "
                f"({len(per_combo)} probed total)."
            )
        return 0

    msg = (
        f"🔴 Vertex AI embedding probe FAILED. "
        f"{len(alerts)} known-good combo(s) regressed:\n"
        + "\n".join(
            f"  ({loc}, {model}): {err}" for (loc, model, err) in alerts
        )
        + "\nAction: run scripts/vertex_live_probe.py locally + ping human on OmniGraph-Vault."
    )
    print(msg, file=sys.stderr)
    if not args.no_telegram:
        send_telegram(msg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
