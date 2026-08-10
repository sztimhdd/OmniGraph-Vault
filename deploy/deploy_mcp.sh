#!/bin/bash
# deploy_mcp.sh — One-command deploy of OmniGraph MCP server to Aliyun.
# Run from the OmniGraph-Vault repo root.
set -euo pipefail

ALIYUN="vitaclaw-aliyun"
REPO="/root/OmniGraph-Vault"
VENV_PIP="$REPO/venv-aim1/bin/pip"
VENV_PY="$REPO/venv-aim1/bin/python"

echo "=== 1. Install deps ==="
ssh "$ALIYUN" "$VENV_PIP install mcp httpx -q"

echo "=== 2. Deploy mcp_server.py ==="
scp kb/mcp_server.py "$ALIYUN:$REPO/kb/mcp_server.py"

echo "=== 3. Deploy systemd unit ==="
scp deploy/systemd/omni-mcp.service "$ALIYUN:/etc/systemd/system/omni-mcp.service"
ssh "$ALIYUN" "systemctl daemon-reload"

echo "=== 4. Start MCP server ==="
ssh "$ALIYUN" "systemctl enable --now omni-mcp.service"

echo "=== 5. Verify ==="
sleep 3
ssh "$ALIYUN" "systemctl is-active omni-mcp.service && echo 'MCP server: RUNNING'"
ssh "$ALIYUN" "curl -s http://127.0.0.1:8767/health | python3 -m json.tool 2>/dev/null || echo 'Health check: checking...'"
ssh "$ALIYUN" "ss -tnlp | grep 8767"

echo ""
echo "=== DEPLOY COMPLETE ==="
echo "MCP server: http://127.0.0.1:8767/mcp"
echo "Run tests:   ssh $ALIYUN 'cd $REPO && $VENV_PY -m pytest tests/test_omni_mcp.py -v'"
