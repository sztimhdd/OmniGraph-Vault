#!/usr/bin/env bash
# Deploy session-invalid alert handler to Aliyun.
# Run from local repo root. Uses ssh alias `aliyun-vitaclaw` (see ~/.ssh/config).
# Idempotent — safe to re-run.
set -euo pipefail

REMOTE=aliyun-vitaclaw
REMOTE_DIR=/etc/systemd/system

echo "[1/4] scp alert service unit ..."
scp deploy/aliyun/systemd/omnigraph-kol-scan-alert.service "$REMOTE:$REMOTE_DIR/"

echo "[2/4] scp updated kol-scan service unit ..."
scp deploy/aliyun/systemd/omnigraph-kol-scan.service "$REMOTE:$REMOTE_DIR/"

echo "[3/4] systemctl daemon-reload ..."
ssh "$REMOTE" "systemctl daemon-reload"

echo "[4/4] enable alert unit (it's OnFailure-triggered, no enable strictly needed but explicit is good) ..."
ssh "$REMOTE" "systemctl enable omnigraph-kol-scan-alert.service 2>&1 || true"

echo "Done. To verify: ssh $REMOTE 'systemctl start omnigraph-kol-scan-alert.service && ls -la /root/.hermes/wechat-session-stale'"
