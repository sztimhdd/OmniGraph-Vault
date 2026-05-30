#!/usr/bin/env bash
# scripts/run_with_env.sh — Aliyun OmniGraph SSH manual trigger wrapper.
#
# Sources /root/.hermes/.env so DEEPSEEK_API_KEY / GEMINI_API_KEY / TAVILY_API_KEY
# are inherited by the Python subprocess. Without this, default shell env has
# DEEPSEEK_API_KEY=dummy (CLAUDE.md global fallback) → silent 401 from DeepSeek
# on every API call.
#
# Bypasses the systemd EnvironmentFile=/root/.hermes/.env injection that the
# omnigraph-*.service units use; for manual SSH-triggered runs only.
#
# Usage (from local orchestrator):
#   ssh aliyun-vitaclaw "bash /root/OmniGraph-Vault/scripts/run_with_env.sh \
#     /root/OmniGraph-Vault/venv-aim1/bin/python \
#     /root/OmniGraph-Vault/scripts/translate_body_cron.py --limit 50"
#
# See: memory aliyun_ssh_manual_trigger_env.md
#
# Companion runbook: scripts/sync_to_databricks.md (similar pattern)

set -euo pipefail

ENV_FILE="${ENV_FILE:-/root/.hermes/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  echo "Example: $0 venv-aim1/bin/python scripts/translate_body_cron.py --limit 50" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

exec "$@"
