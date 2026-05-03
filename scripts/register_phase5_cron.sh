#!/usr/bin/env bash
# register_phase5_cron.sh — idempotent Phase 5 cron registration on Hermes.
#
# Registers 6 NEW cron jobs per PRD §3.4. Does NOT touch the two existing
# jobs (health-check @ 07:55, scan-kol @ 08:00) — they were registered in
# earlier phases and are preserved.
#
# Idempotent: re-running prints `SKIP <name>` for each already-registered
# job and leaves the cron table unchanged.
#
# Usage (on remote Hermes host):
#   ssh <hermes> "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_phase5_cron.sh"
#
# Per D-16 "Hermes drives": each cron prompt is natural-language. The
# Hermes skill system translates the prompt into the appropriate
# Python subprocess invocation.

set -euo pipefail

# H-12: --model deepseek-v4-flash is the default identifier per PRD. If
# the remote host rejects it, re-run with MODEL env override:
#   MODEL=gemini-2.5-flash bash scripts/register_phase5_cron.sh
MODEL="${MODEL:-deepseek-v4-flash}"

# Snapshot existing registrations once to short-circuit re-registration.
EXISTING="$(hermes cronjob list 2>/dev/null || echo '')"

add_job() {
  local name="$1"
  local schedule="$2"
  local prompt="$3"

  if printf '%s\n' "$EXISTING" | grep -qE "\b${name}\b"; then
    echo "SKIP ${name} (already registered)"
    return 0
  fi

  echo "ADD  ${name} @ ${schedule}"
  hermes cronjob add \
    --name "${name}" \
    --schedule "${schedule}" \
    --prompt "${prompt}" \
    --model "${MODEL}"
}

# -----------------------------------------------------------------------
# 6 NEW Phase 5 jobs (PRD §3.4). Existing health-check (07:55) and
# scan-kol (08:00) are intentionally NOT registered here.
# -----------------------------------------------------------------------

add_job "rss-fetch" \
  "0 6 * * *" \
  "run enrichment/rss_fetch.py"

add_job "rss-classify" \
  "0 7 * * *" \
  "run enrichment/rss_classify.py"

add_job "daily-classify-kol" \
  "15 8 * * *" \
  "run batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1"

# D-07 REVISED 2026-05-02 + D-19: KOL only, RSS excluded, forward-only
# (today's fresh scans only). The prompt wording is load-bearing — the
# Hermes skill resolver uses it to decide which table to enumerate.
add_job "daily-enrich" \
  "30 8 * * *" \
  "run the enrich_article skill for all KOL articles (WeChat source only; RSS excluded per D-07 REVISED 2026-05-02 + D-19) with depth_score >= 2 fetched today"

add_job "daily-ingest" \
  "0 9 * * *" \
  "run batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2"

# H-11 fix: no --deliver flag — daily_digest.py delivers unconditionally
# unless --dry-run is passed.
add_job "daily-digest" \
  "30 9 * * *" \
  "run enrichment/daily_digest.py"

# -----------------------------------------------------------------------
# Final state — show full cron table for operator verification.
# -----------------------------------------------------------------------
echo ""
echo "=== hermes cronjob list ==="
hermes cronjob list
