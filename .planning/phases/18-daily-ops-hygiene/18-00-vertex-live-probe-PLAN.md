---
phase: 18-daily-ops-hygiene
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/vertex_live_probe.py
  - scripts/register_vertex_probe_cron.sh
  - tests/unit/test_vertex_live_probe.py
autonomous: true
requirements: [HYG-01]
must_haves:
  truths:
    - "`scripts/vertex_live_probe.py` probes 3 candidate embedding model names against Vertex AI paid-tier SA and exits 0 if any returns dims>0, else exit 1 with which names 404'd"
    - "Probe uses `genai.Client(vertexai=True)` — no api_key, Vertex SA auth only"
    - "Probe sends Telegram alert on non-zero exit (critical 🔴 emoji prefix) reusing `~/.hermes/.env` TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"
    - "`scripts/register_vertex_probe_cron.sh` is idempotent (SKIP on re-run); registers monthly (day 1 @ 08:00) via `hermes cron add`"
    - "Unit tests mock `google.genai.Client` — no network calls from Windows"
  artifacts:
    - path: "scripts/vertex_live_probe.py"
      provides: "Live probe of Vertex embedding catalog — detects model-name flips before they kill prod batches"
      min_lines: 80
    - path: "scripts/register_vertex_probe_cron.sh"
      provides: "Idempotent Hermes cron registration for monthly Vertex probe"
      min_lines: 30
    - path: "tests/unit/test_vertex_live_probe.py"
      provides: "Mock-only unit tests for probe logic (all green / all 404 / partial / Telegram call shape)"
      min_lines: 80
  key_links:
    - from: "scripts/vertex_live_probe.py"
      to: "google.genai.Client(vertexai=True).aio.models.embed_content"
      via: "probe loop over candidate model names"
      pattern: "vertexai=True"
    - from: "scripts/vertex_live_probe.py"
      to: "Telegram Bot API"
      via: "requests.post to api.telegram.org/bot{token}/sendMessage on non-zero exit"
      pattern: "sendMessage"
---

<objective>
Build `scripts/vertex_live_probe.py`: a self-contained script that probes 3 candidate Vertex AI embedding model names (`gemini-embedding-2`, `gemini-embedding-2-preview`, `gemini-embedding-001`) against the paid-tier SA + `us-central1`, exits 0 if ANY returns a non-zero-dim vector, and exits 1 + sends Telegram alert if ALL 404.

Purpose: catch the Vertex catalog model-name flip BEFORE it kills a production batch. Wave 0 Close-Out observed the flip twice in 24h. Monthly cron + immediate Telegram alert is the minimum cost vs. batch-time 404 storms.

Output: runnable probe script + Hermes cron registrar + unit tests (all mocked locally).
</objective>

<execution_context>
This plan runs on a Windows dev machine with Cisco Umbrella. Vertex AI endpoints DO reach local via the paid-tier SA (per `memory/vertex_ai_smoke_validated.md`), but:
- Telegram Bot API delivery: Hermes-side only (Umbrella blocks `api.telegram.org` from local in past sessions — probe writes message to stdout in local mode if delivery fails, for test visibility).
- Cron registration: Hermes-side only (the `hermes cron` CLI exists only on Hermes).

Local unit tests mock the `google.genai.Client` entirely — no live network.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-00-SUMMARY.md
@lib/lightrag_embedding.py
@scripts/register_phase5_cron.sh

<why_this_matters>
From `memory/vertex_ai_smoke_validated.md` (summarized):

- **2026-04-30 / 05-02**: `gemini-embedding-2` returned 404 on `us-central1`; `-preview` returned 3072-dim OK. Code mapped `2 → 2-preview`. Commit `8e4b132`.
- **2026-05-03 morning**: EXACT OPPOSITE — `gemini-embedding-2` returned 3072-dim; `-preview` returned 404. Code became pass-through. Commits `9069f59` + `ae3a030`.

Two flips in ~24h. Neither was announced publicly. The only automation that would have caught the second flip before production Hermes hit 404 storms was a live probe against the real endpoint. This plan IS that automation.
</why_this_matters>

<probe_script_shape>
```python
#!/usr/bin/env python3
"""Vertex AI embedding model-name live probe — HYG-01.

Probes 3 candidate model names against the paid-tier Vertex AI endpoint.
Exits 0 if ANY returns a non-zero-dim vector. Exits 1 + Telegram alert otherwise.

Runs as a monthly cron on Hermes; also runnable ad-hoc before any
Vertex-touching code change (the "hard prerequisite" from memory file).

Usage:
    python scripts/vertex_live_probe.py
    python scripts/vertex_live_probe.py --no-telegram   # skip alert delivery
    python scripts/vertex_live_probe.py --json          # machine-readable output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import requests  # Telegram delivery

# Candidates in preference order. First non-404 wins for the "any green" gate.
CANDIDATES: tuple[str, ...] = (
    "gemini-embedding-2",          # 2026-05-03 ground truth
    "gemini-embedding-2-preview",  # 2026-05-02 ground truth
    "gemini-embedding-001",        # older fallback
)

LOCATION = "us-central1"
TEST_INPUT = "probe"


async def probe_one(client: Any, model: str) -> tuple[str, int | None, str | None]:
    """Returns (model, dims, error_str). dims=None indicates failure."""
    try:
        r = await client.aio.models.embed_content(model=model, contents=[TEST_INPUT])
        dims = len(r.embeddings[0].values)
        return (model, dims, None)
    except Exception as e:
        return (model, None, str(e)[:200])


async def run(candidates: tuple[str, ...]) -> list[tuple[str, int | None, str | None]]:
    from google import genai  # imported lazily so unit tests can monkeypatch
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT unset — cannot probe Vertex AI")
    client = genai.Client(vertexai=True, project=project, location=LOCATION)
    return [await probe_one(client, m) for m in candidates]


def send_telegram(message: str) -> bool:
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
    p.add_argument("--no-telegram", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    results = asyncio.run(run(CANDIDATES))
    greens = [(m, d) for (m, d, _) in results if d and d > 0]
    if args.json:
        print(json.dumps([{"model": m, "dims": d, "error": e} for (m, d, e) in results], indent=2))
    else:
        for (m, d, e) in results:
            mark = f"✅ dims={d}" if d else f"❌ {e}"
            print(f"{mark:40s} {m}")

    if greens:
        print(f"[OK] {len(greens)} / {len(CANDIDATES)} candidate(s) green. First: {greens[0][0]}")
        return 0

    msg = (
        f"🔴 Vertex AI embedding probe FAILED ({LOCATION}). All {len(CANDIDATES)} candidates 404:\n"
        + "\n".join(f"  {m}: {e}" for (m, _, e) in results)
        + "\nAction: run scripts/vertex_live_probe.py locally + ping human on OmniGraph-Vault."
    )
    print(msg, file=sys.stderr)
    if not args.no_telegram:
        send_telegram(msg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```
</probe_script_shape>

<cron_registrar_shape>
```bash
#!/usr/bin/env bash
# register_vertex_probe_cron.sh — HYG-01 monthly Vertex catalog probe.
#
# Idempotent: re-running prints SKIP if already registered.
# Schedule: 08:00 local on day 1 of every month.
#
# Usage (on Hermes):
#   ssh <hermes> "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_vertex_probe_cron.sh"
set -euo pipefail

EXISTING="$(hermes cron list 2>/dev/null || echo '')"
NAME="vertex-probe-monthly"

if printf '%s\n' "$EXISTING" | grep -qE "\b${NAME}\b"; then
  echo "SKIP ${NAME} (already registered)"
else
  echo "ADD ${NAME} @ 0 8 1 * *"
  hermes cron add \
    --name "${NAME}" \
    --workdir "${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}" \
    "0 8 1 * *" \
    "run scripts/vertex_live_probe.py; on non-zero exit send a Telegram alert with the script stderr output"
fi

echo ""
echo "=== hermes cron list ==="
hermes cron list
```
</cron_registrar_shape>

<unit_test_shape>
Tests MUST mock `google.genai.Client` and `requests.post` — no live network.

Five tests:
1. `test_all_green_exits_zero` — mock returns 3072-dim for all 3 → exit 0, no Telegram
2. `test_all_404_exits_one_and_sends_telegram` — mock raises on all 3 → exit 1, `requests.post` called once
3. `test_partial_green_exits_zero` — first candidate 404, second 3072-dim → exit 0, no Telegram
4. `test_no_telegram_flag_suppresses_delivery` — all 404 + `--no-telegram` → exit 1 but NO `requests.post`
5. `test_json_output_schema` — `--json` flag outputs valid JSON with model/dims/error fields
</unit_test_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-00.1: Write `scripts/vertex_live_probe.py` + unit tests</name>
  <files>scripts/vertex_live_probe.py, tests/unit/test_vertex_live_probe.py</files>
  <behavior>
    - All 3 candidates green → exit 0, stdout lists greens, no Telegram call
    - All 3 candidates 404 → exit 1, Telegram sendMessage called with 🔴 prefix + error summary
    - Partial (candidate 1 red, candidate 2 green) → exit 0 (first green wins)
    - `--no-telegram` suppresses delivery even on all-404
    - `--json` emits machine-readable output
    - Missing `GOOGLE_CLOUD_PROJECT` raises RuntimeError (fail loud, do not attempt probe)
  </behavior>
  <read_first>
    - memory/vertex_ai_smoke_validated.md — exact probe template + candidate model names + 2-flip history
    - lib/lightrag_embedding.py — `_is_vertex_mode()` + `_make_client()` pattern (this script reuses Vertex-mode construction directly)
    - scripts/register_phase5_cron.sh — cron name uniqueness check via `hermes cron list` grep
  </read_first>
  <action>
    Build the probe script per `<probe_script_shape>` above. Build unit tests per `<unit_test_shape>` — all mocked (`monkeypatch.setattr("google.genai.Client", ...)` and `monkeypatch.setattr("requests.post", ...)`). Tests must run on Windows without Hermes access or live Vertex.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_vertex_live_probe.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/vertex_live_probe.py` exists ≥ 80 lines.
    - Script is executable (`#!/usr/bin/env python3` shebang).
    - `grep -q "gemini-embedding-2" scripts/vertex_live_probe.py` — candidate present.
    - `grep -q "vertexai=True" scripts/vertex_live_probe.py` — Vertex mode only.
    - `! grep -q "api_key=" scripts/vertex_live_probe.py` — no api-key mode (SA only).
    - `grep -q "sendMessage" scripts/vertex_live_probe.py` — Telegram wired.
    - 5 pytest tests pass on Windows (mocks only, no network).
  </acceptance_criteria>
  <done>Probe script ready to run ad-hoc or via cron.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 18-00.2: Write `scripts/register_vertex_probe_cron.sh`</name>
  <files>scripts/register_vertex_probe_cron.sh</files>
  <behavior>
    - Idempotent: re-running prints `SKIP vertex-probe-monthly`
    - Registers via `hermes cron add` with natural-language prompt per D-16 "Hermes drives"
    - Uses `OMNIGRAPH_ROOT` env var with `$HOME/OmniGraph-Vault` fallback (same pattern as `register_phase5_cron.sh`)
  </behavior>
  <read_first>
    - scripts/register_phase5_cron.sh — `add_job` function shape, idempotency via `hermes cron list` grep, workdir handling
  </read_first>
  <action>
    Write the cron registrar per `<cron_registrar_shape>` above. Make it executable.
  </action>
  <verify>
    <automated>bash -n scripts/register_vertex_probe_cron.sh  # syntax check, safe on Windows via Git Bash</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/register_vertex_probe_cron.sh` ≥ 30 lines.
    - `bash -n scripts/register_vertex_probe_cron.sh` exits 0 (valid bash).
    - `grep -q "hermes cron add" scripts/register_vertex_probe_cron.sh` — registers via Hermes CLI.
    - `grep -q "0 8 1 \* \*" scripts/register_vertex_probe_cron.sh` — monthly schedule.
    - `grep -q "SKIP" scripts/register_vertex_probe_cron.sh` — idempotency branch.
  </acceptance_criteria>
  <done>Cron registrar ready for Hermes-side invocation.</done>
</task>

</tasks>

<verification>
Local:
- Unit tests all green.
- Script files present, executable, syntax-valid.

Hermes (operator sign-off, not blocking):
- `bash scripts/register_vertex_probe_cron.sh` — ADDs `vertex-probe-monthly`, prints confirmation.
- Manual trigger: `python scripts/vertex_live_probe.py` — at least `gemini-embedding-2` returns 3072-dim (per 2026-05-03 ground truth); exit 0; no Telegram alert.
- Re-run of registrar prints SKIP.
</verification>

<success_criteria>
- HYG-01 satisfied: any future Vertex catalog flip fires a 🔴 Telegram alert within 24h of the flip (worst case: flip happens on day 2, discovered on day 1 of next month).
- Zero new code paths in production ingest/synthesis flow — probe is external.
- Any `_resolve_model()` change going forward has a hard prerequisite in Definition of Ready ("run probe first"), codified in 05-00-SUMMARY § C operational lesson.
</success_criteria>

<output>
After completion, create `.planning/phases/18-daily-ops-hygiene/18-00-SUMMARY.md` documenting: probe results if Hermes-side probe ran, cron registration confirmation, any candidate not yet covered by the 3-model list.
</output>
