#!/bin/bash
# OmniGraph weekly data sync: Aliyun → Mac
# Run by Hermes cron every Sunday
set -e

LOCAL="/Users/hai/.hermes/omonigraph-vault"
REMOTE="root@47.117.244.253"
REMOTE_PATH="/root/.hermes/omonigraph-vault"
LOG="$HOME/.hermes/logs/omnigraph-sync.log"

echo "$(date): starting sync" >> "$LOG"

# 1. DB (via rsync — efficient, only transfers changed blocks)
rsync -avz --progress \
    -e "ssh -o BatchMode=yes -o ConnectTimeout=15" \
    "$REMOTE:$REMOTE_PATH/kol_scan.db" \
    "$LOCAL/kol_scan.db" \
    >> "$LOG" 2>&1

# 2. LightRAG storage
rsync -avz --delete \
    -e "ssh -o BatchMode=yes -o ConnectTimeout=15" \
    "$REMOTE:$REMOTE_PATH/lightrag_storage/" \
    "$LOCAL/lightrag_storage/" \
    >> "$LOG" 2>&1

# 3. Entity buffer
rsync -avz --delete \
    -e "ssh -o BatchMode=yes -o ConnectTimeout=15" \
    "$REMOTE:$REMOTE_PATH/entity_buffer/" \
    "$LOCAL/entity_buffer/" \
    >> "$LOG" 2>&1

# 4. Images
rsync -avz \
    -e "ssh -o BatchMode=yes -o ConnectTimeout=15" \
    "$REMOTE:$REMOTE_PATH/images/" \
    "$LOCAL/images/" \
    >> "$LOG" 2>&1

echo "$(date): sync complete" >> "$LOG"
echo "SYNC OK"
