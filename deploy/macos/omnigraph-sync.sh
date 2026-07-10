#!/bin/bash
# OmniGraph weekly data sync: Aliyun → Mac
# Run by Hermes cron every Sunday 03:00
set -e

LOCAL="/Users/hai/.hermes/omonigraph-vault"
REMOTE="root@47.117.244.253"
REMOTE_PATH="/root/.hermes/omonigraph-vault"
LOG="$HOME/.hermes/logs/omnigraph-sync.log"
RSYNC_OPTS="-av --partial --inplace --timeout=120 -e ssh"

echo "$(date): START syn...[truncated]