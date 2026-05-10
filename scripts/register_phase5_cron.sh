#!/usr/bin/env bash
# register_phase5_cron.sh — idempotent Phase 5 cron registration on Hermes.
#
# Registers 6 NEW cron jobs per PRD §3.4. Does NOT touch the two existing
# jobs (health-check @ 07:55, scan-kol @ 08:00) — they were registered in
# earlier phases and are preserved.
#
# Re-running the script prints SKIP for the 5 unchanged jobs; the
# daily-ingest job is replaced unconditionally via replace_job so the
# body stays in sync with this file (quick-260503-jn6).
#
# Usage (on remote Hermes host):
#   ssh <hermes> "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_phase5_cron.sh"
#
# Per D-16 "Hermes drives": each cron prompt is natural-language. The
# Hermes skill system translates the prompt into the appropriate
# Python subprocess invocation.

set -euo pipefail

# Model is controlled by the agent's config, not per-job, per H-12.
# All 6 jobs use whatever model the agent is currently configured with.

# Snapshot existing registrations once to short-circuit re-registration.
EXISTING="$(hermes cron list 2>/dev/null || echo '')"

add_job() {
  local name="$1"
  local schedule="$2"
  local prompt="$3"

  if printf '%s\n' "$EXISTING" | grep -qE "\b${name}\b"; then
    echo "SKIP ${name} (already registered)"
    return 0
  fi

  echo "ADD  ${name} @ ${schedule}"
  hermes cron add \
    --name "${name}" \
    --workdir "${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}" \
    "${schedule}" \
    "${prompt}"
}

# quick-260503-jn6 (JN6-03): update-or-add helper used by daily-ingest
# so re-running this script actually swaps the body when it already exists.
# Best-effort remove; if the Hermes CLI uses a different subcommand name
# (delete / rm / unregister), all variants will fail quietly and the caller
# must manually remove per SUMMARY § Operator Checklist.
replace_job() {
  local name="$1"
  local schedule="$2"
  local prompt="$3"

  if printf '%s\n' "$EXISTING" | grep -qE "\b${name}\b"; then
    echo "REPLACE ${name} — removing existing then re-adding"
    hermes cron remove --name "${name}" 2>/dev/null \
      || hermes cron delete --name "${name}" 2>/dev/null \
      || hermes cron rm --name "${name}" 2>/dev/null \
      || { echo "  (remove failed; see SUMMARY § Operator Checklist for manual steps)"; return 0; }
  else
    echo "ADD  ${name} @ ${schedule}"
  fi

  hermes cron add \
    --name "${name}" \
    --workdir "${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}" \
    "${schedule}" \
    "${prompt}"
}

# -----------------------------------------------------------------------
# 6 NEW Phase 5 jobs (PRD §3.4). Existing health-check (07:55) and
# scan-kol (08:00) are intentionally NOT registered here.
# -----------------------------------------------------------------------

add_job "rss-fetch" \
  "0 6 * * *" \
  "run enrichment/rss_fetch.py"

# v3.5 ir-4 (LF-5.2): rss-classify cron retired. RSS classification now
# happens inside Layer 1 of batch_ingest_from_spider's --from-db dual-source
# candidate SQL, exercised by the daily-ingest cron below. The legacy
# enrichment/rss_classify.py was deleted along with this registration block.
# Operators upgrading from a pre-ir-4 deploy must remove the existing
# 'rss-classify' job from Hermes manually:  hermes cron remove <id>

add_job "daily-classify-kol" \
  "15 8 * * *" \
  "run batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1"

# D-07 REVISED 2026-05-02 + D-19: KOL only, RSS excluded, forward-only
# (today's fresh scans only). The prompt wording is load-bearing — the
# Hermes skill resolver uses it to decide which table to enumerate.
add_job "daily-enrich" \
  "30 8 * * *" \
  "run the enrich_article skill for all KOL articles (WeChat source only; RSS excluded per D-07 REVISED 2026-05-02 + D-19) with depth_score >= 2 fetched today"

# Bug-fix 2026-05-03 (quick-260503-jn6): old body only ingested KOL — RSS
# was never in any cron. New body invokes step_7 of orchestrate_daily which
# runs BOTH KOL + RSS branches with per-branch rate caps (20/20) to consume
# the Day-1 backlog (249 KOL + 479 RSS) in controlled chunks.
replace_job "daily-ingest" \
  "0 9 * * *" \
  "run enrichment/orchestrate_daily.py --step 7 --max-kol 20 --max-rss 20"

# H-11 fix: no --deliver flag — daily_digest.py delivers unconditionally
# unless --dry-run is passed.
add_job "daily-digest" \
  "30 9 * * *" \
  "run enrichment/daily_digest.py"

# quick-260510-k5q (RCN-01..05): daily reconciliation canary for commit
# 949e3f4 (h09 PROCESSED-gate hot-fix). Detects ingestions=ok rows whose
# LightRAG doc_status is missing or != 'processed' and exits 1 to surface
# them in cron logs. RSS reconciliation deferred to ar-1.
add_job "reconcile-ingestions" \
  "30 9 * * *" \
  "cd ~/OmniGraph-Vault && source venv/bin/activate && python scripts/reconcile_ingestions.py 2>&1 | tee /tmp/reconcile-\$(date +%Y%m%d).log"

# -----------------------------------------------------------------------
# Final state — show full cron table for operator verification.
# -----------------------------------------------------------------------
echo ""
echo "=== hermes cron list ==="
hermes cron list
