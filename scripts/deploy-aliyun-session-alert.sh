#!/usr/bin/env bash
# Deploy the WeChat-cookie self-healing units to Aliyun.
# Run from local repo root. Uses ssh alias `aliyun-vitaclaw` (see ~/.ssh/config) by default.
# Override the target for a rebuilt box via ALIYUN_SSH, e.g.
#   ALIYUN_SSH="root@47.117.244.253" bash scripts/deploy-aliyun-session-alert.sh
# Idempotent — safe to re-run. Ships BOTH the reactive OnFailure alert hand-off AND the
# proactive pre-scan refresh timer (the "never block the scan" hardening).
set -euo pipefail

REMOTE="${ALIYUN_SSH:-aliyun-vitaclaw}"
REMOTE_DIR=/etc/systemd/system

echo "[1/6] scp alert service unit (reactive OnFailure hand-off) ..."
scp deploy/aliyun/systemd/omnigraph-kol-scan-alert.service "$REMOTE:$REMOTE_DIR/"

echo "[2/6] scp kol-scan service unit (OnFailure= wiring) ..."
scp deploy/aliyun/systemd/omnigraph-kol-scan.service "$REMOTE:$REMOTE_DIR/"

echo "[3/6] scp proactive pre-scan refresh service + timer ..."
scp deploy/aliyun/systemd/omnigraph-kol-refresh.service "$REMOTE:$REMOTE_DIR/"
scp deploy/aliyun/systemd/omnigraph-kol-refresh.timer "$REMOTE:$REMOTE_DIR/"

echo "[4/6] systemctl daemon-reload ..."
ssh "$REMOTE" "systemctl daemon-reload"

echo "[5/6] enable alert unit (OnFailure-triggered; enable is explicit, not strictly required) ..."
ssh "$REMOTE" "systemctl enable omnigraph-kol-scan-alert.service 2>&1 || true"

echo "[6/6] enable + start the proactive pre-scan refresh timer (18:55 CST, before the 19:00 scan) ..."
ssh "$REMOTE" "systemctl enable --now omnigraph-kol-refresh.timer"

echo "Done. To verify:"
echo "  ssh $REMOTE 'systemctl list-timers omnigraph-kol-refresh.timer omnigraph-kol-scan.timer --no-pager'"
echo "  ssh $REMOTE 'systemctl start omnigraph-kol-refresh.service && ssh hermes \"tail -6 ~/.hermes/kol-refresh.log\"'"
