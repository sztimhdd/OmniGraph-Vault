#!/bin/bash
# kg-sync failure alert: old -> ssh hermes -> Telegram (stdin pipe avoids quote nesting)
# Invoked by omnigraph-kg-sync-alert.service OnFailure.
MSG='🔴 OmniGraph KG sync FAILED — 新机 MCP 数据过期风险，查旧机 /var/log/omnigraph-kg-sync.log'
if ! printf '%s' "$MSG" | ssh -o BatchMode=yes -o ConnectTimeout=20 hermes "~/.local/bin/hermes send -t telegram" 2>/dev/null; then
    echo "kg-sync-alert: ssh hermes send failed" | systemd-cat -t kg-sync-alert
fi
