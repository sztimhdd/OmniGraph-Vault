#!/bin/bash
# harden_mcp_firewall.sh — H1 Ponytail audit 2026-08-04
# MCP :8767 and health :8768 currently open to 0.0.0.0/0 with no auth/TLS/rate-limit.
# This script applies immediate iptables-based mitigation.
#
# TWO PHASES (run in order):
#   Phase 1: Rate limiting (safe to apply immediately, no lockout risk)
#   Phase 2: IP allowlist (REQUIRES user to set ALLOWED_IPS first)
#
# Usage:
#   Phase 1 (safe):  bash scripts/harden_mcp_firewall.sh --rate-limit
#   Phase 2 (caution): ALLOWED_IPS="1.2.3.4,5.6.7.8" bash scripts/harden_mcp_firewall.sh --allowlist
#   Status:          bash scripts/harden_mcp_firewall.sh --status
#   Rollback:        bash scripts/harden_mcp_firewall.sh --rollback

set -euo pipefail

MCP_PORT=8767
HEALTH_PORT=8768
CHAIN_NAME="OMNIGRAPH-MCP"

# ── Parse args ─────────────────────────────────────────────────────
ACTION="${1:-}"

if [ "$ACTION" = "--status" ]; then
  echo "=== iptables rules for MCP ==="
  iptables -L INPUT -n -v --line-numbers | grep -E "$MCP_PORT|$HEALTH_PORT|$CHAIN_NAME" || echo "(none)"
  echo ""
  echo "=== Rate limit hits (last hour) ==="
  iptables -L "$CHAIN_NAME" -n -v 2>/dev/null || echo "Chain $CHAIN_NAME does not exist"
  exit 0
fi

if [ "$ACTION" = "--rollback" ]; then
  echo "Rolling back MCP firewall hardening..."
  iptables -D INPUT -p tcp --dport $MCP_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -D INPUT -p tcp --dport $HEALTH_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -F "$CHAIN_NAME" 2>/dev/null || true
  iptables -X "$CHAIN_NAME" 2>/dev/null || true
  echo "Rollback complete. Ports $MCP_PORT and $HEALTH_PORT are now unfiltered."
  exit 0
fi

# ── Phase 1: Rate limiting ────────────────────────────────────────
if [ "$ACTION" = "--rate-limit" ]; then
  echo "Applying rate limiting to MCP ports $MCP_PORT,$HEALTH_PORT..."

  # Create chain if not exists
  iptables -N "$CHAIN_NAME" 2>/dev/null || iptables -F "$CHAIN_NAME"

  # Rate limit: 30 conn/min per source IP, burst 10
  iptables -A "$CHAIN_NAME" \
    -m state --state NEW \
    -m recent --set --name mcp_ratelimit

  iptables -A "$CHAIN_NAME" \
    -m state --state NEW \
    -m recent --update --seconds 60 --hitcount 30 --name mcp_ratelimit \
    -j DROP

  iptables -A "$CHAIN_NAME" -j ACCEPT

  # Wire chain to INPUT
  iptables -D INPUT -p tcp --dport $MCP_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -D INPUT -p tcp --dport $HEALTH_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -I INPUT -p tcp --dport $MCP_PORT -j "$CHAIN_NAME"
  iptables -I INPUT -p tcp --dport $HEALTH_PORT -j "$CHAIN_NAME"

  echo "Rate limiting applied: 30 conn/min per IP, burst 10."
  echo "Persist with: iptables-save > /etc/iptables/rules.v4"
  echo ""
  echo "Next: Phase 2 IP allowlist — set ALLOWED_IPS and run with --allowlist"
  exit 0
fi

# ── Phase 2: IP allowlist ─────────────────────────────────────────
if [ "$ACTION" = "--allowlist" ]; then
  ALLOWED="${ALLOWED_IPS:-}"
  if [ -z "$ALLOWED" ]; then
    echo "ERROR: ALLOWED_IPS not set."
    echo "Usage: ALLOWED_IPS=\"1.2.3.4,5.6.7.8/32\" bash $0 --allowlist"
    echo ""
    echo "Allowed IPs should include:"
    echo "  - Your Hermes client public IP"
    echo "  - Any VPN/proxy IPs that access the MCP"
    echo "  - 127.0.0.1 (localhost)"
    exit 1
  fi

  echo "WARNING: This will restrict MCP access to ONLY these IPs: $ALLOWED"
  echo "If you lock yourself out, run: bash $0 --rollback"
  echo ""
  echo "Applying IP allowlist..."

  # Ensure chain exists
  iptables -N "$CHAIN_NAME" 2>/dev/null || iptables -F "$CHAIN_NAME"

  # Add allow rules per IP
  IFS=',' read -ra IPS <<< "$ALLOWED"
  for ip in "${IPS[@]}"; do
    ip=$(echo "$ip" | xargs)  # trim whitespace
    iptables -A "$CHAIN_NAME" -s "$ip" -j ACCEPT
    echo "  ALLOW $ip"
  done

  # Drop everything else
  iptables -A "$CHAIN_NAME" -j DROP

  # Wire chain
  iptables -D INPUT -p tcp --dport $MCP_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -D INPUT -p tcp --dport $HEALTH_PORT -j "$CHAIN_NAME" 2>/dev/null || true
  iptables -I INPUT -p tcp --dport $MCP_PORT -j "$CHAIN_NAME"
  iptables -I INPUT -p tcp --dport $HEALTH_PORT -j "$CHAIN_NAME"

  echo ""
  echo "IP allowlist applied. Persist with: iptables-save > /etc/iptables/rules.v4"
  echo ""
  echo "⚠ Aliyun security group (console): also restrict 8767,8768 to same IPs."
  echo "  This provides defense-in-depth: iptables + cloud firewall."
  exit 0
fi

echo "Usage: $0 --rate-limit | --allowlist | --status | --rollback"
exit 1
