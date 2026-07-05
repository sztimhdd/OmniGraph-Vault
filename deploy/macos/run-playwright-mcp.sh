#!/bin/bash
# Playwright MCP server wrapper — connects to Brave CDP on :9222

LOG="$HOME/.hermes/logs/mcp-playwright.log"
export HOME="$HOME"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

echo "$(date): starting Playwright MCP on :8931 → CDP :9222" >> "$LOG"
exec /opt/homebrew/bin/npx -y @playwright/mcp \
  --cdp-endpoint http://localhost:9222 \
  --port 8931 \
  --host localhost \
  2>>"$LOG"
