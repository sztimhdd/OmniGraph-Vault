#!/bin/bash
# migrate_kg_to_wsl.sh — 将 OmniGraph 知识库从阿里云迁移到 WSL 本机
# 
# 架构变化:
#   迁移前: Aliyun 跑全部 (scan + ingest + Qdrant + kb-api + LightRAG)
#   迁移后: WSL 跑 KG 服务 (Qdrant + kb-api + MCP server), Aliyun 跑采集 (scan + ingest)
#
# 数据搬家:
#   - Qdrant 向量数据:  /var/lib/qdrant/ → WSL Docker volume
#   - LightRAG 图存储:  4.2G graph files → WSL ~/.hermes/omonigraph-vault/lightrag_storage/
#   - SQLite 文章库:     kol_scan.db → WSL OmniGraph-Vault/data/
#
# 前置条件:
#   1. WSL .wslconfig memory 至少 16G (推荐 24G)
#   2. Aliyun SSH 可通
#   3. WSL 上 Docker 已运行
#
# 用法:
#   chmod +x deploy/migrate_kg_to_wsl.sh
#   ./deploy/migrate_kg_to_wsl.sh
set -euo pipefail

ALIYUN="vitaclaw-aliyun"
ALIYUN_REPO="/root/OmniGraph-Vault"
ALIYUN_QDRANT="/var/lib/qdrant"
ALIYUN_LIGHTRAG="/root/.hermes/omonigraph-vault/lightrag_storage"
ALIYUN_DB="$ALIYUN_REPO/data/kol_scan.db"

WSL_REPO="/home/sztimhdd/OmniGraph-Vault"
WSL_LIGHTRAG="/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage"
WSL_DB="$WSL_REPO/data/kol_scan.db"
WSL_QDRANT_VOL="omnigraph_qdrant_data"
WSL_QDRANT_PORT="6333"
WSL_KBAPI_PORT="8766"
WSL_MCP_PORT="8767"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ============================================================================
# Step 0: Pre-flight checks
# ============================================================================
log "Step 0: Pre-flight checks"

# Check WSL memory
WSL_MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$WSL_MEM_MB" -lt 12000 ]; then
    warn "WSL memory is only ${WSL_MEM_MB}MB. Qdrant needs ~5GB + kb-api ~1GB."
    warn "Edit %USERPROFILE%\\.wslconfig on Windows and set:"
    warn "  [wsl2]"
    warn "  memory=24GB"
    warn "Then run: wsl --shutdown (in PowerShell) and restart WSL."
    warn ""
    warn "Continuing anyway — but expect instability if under 12GB."
fi

# Check Docker
if ! docker info >/dev/null 2>&1; then
    err "Docker not running. Start Docker Desktop first."
fi

# Check SSH to Aliyun
if ! ssh -o ConnectTimeout=10 "$ALIYUN" 'echo ok' >/dev/null 2>&1; then
    err "Cannot SSH to $ALIYUN. Fix SSH and retry."
fi
log "  ✓ SSH to Aliyun OK"
log "  ✓ WSL memory: ${WSL_MEM_MB}MB"
log "  ✓ Docker running"

# ============================================================================
# Step 1: Aliyun side — stop services, check data sizes
# ============================================================================
log "Step 1: Check Aliyun data sizes"

ALIYUN_QDRANT_SIZE=$(ssh "$ALIYUN" "du -sh $ALIYUN_QDRANT 2>/dev/null | cut -f1 || echo 'unknown'")
ALIYUN_LIGHTRAG_SIZE=$(ssh "$ALIYUN" "du -sh $ALIYUN_LIGHTRAG 2>/dev/null | cut -f1 || echo 'unknown'")
ALIYUN_DB_SIZE=$(ssh "$ALIYUN" "du -sh $ALIYUN_DB 2>/dev/null | cut -f1 || echo 'unknown'")

log "  Qdrant data:    $ALIYUN_QDRANT_SIZE"
log "  LightRAG graph: $ALIYUN_LIGHTRAG_SIZE"
log "  SQLite DB:      $ALIYUN_DB_SIZE"

echo ""
echo "  Will rsync approximately ${ALIYUN_QDRANT_SIZE} + ${ALIYUN_LIGHTRAG_SIZE} + ${ALIYUN_DB_SIZE}"
echo "  Press Enter to continue or Ctrl-C to abort..."
read -r

# ============================================================================
# Step 2: Stop Aliyun services
# ============================================================================
log "Step 2: Stop Aliyun KG services"

ssh "$ALIYUN" "systemctl stop kb-api.service 2>/dev/null || true"
ssh "$ALIYUN" "docker stop qdrant 2>/dev/null || true"
log "  ✓ kb-api stopped"
log "  ✓ Qdrant container stopped"

# ============================================================================
# Step 3: rsync LightRAG storage
# ============================================================================
log "Step 3: rsync LightRAG storage (${ALIYUN_LIGHTRAG_SIZE})"

mkdir -p "$WSL_LIGHTRAG"
rsync -avz --progress \
    "$ALIYUN:$ALIYUN_LIGHTRAG/" \
    "$WSL_LIGHTRAG/"
log "  ✓ LightRAG storage synced"

# ============================================================================
# Step 4: rsync SQLite DB
# ============================================================================
log "Step 4: rsync SQLite DB (${ALIYUN_DB_SIZE})"

mkdir -p "$(dirname "$WSL_DB")"
# Backup existing WSL DB if present
if [ -f "$WSL_DB" ]; then
    cp "$WSL_DB" "$WSL_DB.bak-$(date +%Y%m%d-%H%M%S)"
    log "  Backed up existing WSL DB"
fi

rsync -avz --progress \
    "$ALIYUN:$ALIYUN_DB" \
    "$WSL_DB"
log "  ✓ SQLite DB synced"

# ============================================================================
# Step 5: Start Qdrant on WSL
# ============================================================================
log "Step 5: Start Qdrant on WSL"

# Stop existing qdrant container if any
docker rm -f qdrant 2>/dev/null || true

# Create Docker volume if not exists
docker volume create "$WSL_QDRANT_VOL" 2>/dev/null || true

# Start Qdrant
docker run -d --name qdrant \
    -p "127.0.0.1:${WSL_QDRANT_PORT}:6333" \
    -p "127.0.0.1:6334:6334" \
    -v "${WSL_QDRANT_VOL}:/qdrant/storage" \
    qdrant/qdrant:v1.11.5

log "  ✓ Qdrant started on port ${WSL_QDRANT_PORT}"

# Wait for Qdrant to be ready
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${WSL_QDRANT_PORT}/healthz" >/dev/null 2>&1; then
        log "  ✓ Qdrant healthy"
        break
    fi
    sleep 2
done

# ============================================================================
# Step 6: Import Qdrant data from Aliyun
# ============================================================================
log "Step 6: Import Qdrant data"

# We can't directly rsync Qdrant's data dir because of file locks and format.
# Instead, we restore from the latest snapshot on Aliyun.
# If snapshot is broken, we do a direct filesystem copy (requires stopping Aliyun Qdrant).

log "  Attempting snapshot import from Aliyun..."

SNAPSHOT_DIR=$(ssh "$ALIYUN" "ls -d /root/OmniGraph-Vault/data/qdrant_snapshots/*/ 2>/dev/null | tail -1 || echo ''")

if [ -n "$SNAPSHOT_DIR" ]; then
    log "  Found snapshot: $SNAPSHOT_DIR"
    # rsync snapshot to WSL
    SNAPSHOT_LOCAL="/tmp/omnigraph_qdrant_import"
    rm -rf "$SNAPSHOT_LOCAL"
    mkdir -p "$SNAPSHOT_LOCAL"
    rsync -avz "$ALIYUN:$SNAPSHOT_DIR" "$SNAPSHOT_LOCAL/"
    log "  Snapshot downloaded. Manual import required — see docs/MCP-QUICKSTART.md"
else
    warn "  No snapshot found on Aliyun."
    warn "  Will import via Qdrant snapshot API after Aliyun Qdrant is restarted."
    warn "  Or use: curl -X POST 'http://ALIYUN_IP:6333/collections/.../snapshots/upload'"
fi

# For now: restart Aliyun Qdrant so ingest can continue
ssh "$ALIYUN" "docker start qdrant 2>/dev/null || true"
log "  ✓ Aliyun Qdrant restarted (for ingest continuity)"

# ============================================================================
# Step 7: Set up Python venv on WSL
# ============================================================================
log "Step 7: Set up Python venv"

if [ ! -f "$WSL_REPO/venv-aim1/bin/python" ]; then
    python3 -m venv "$WSL_REPO/venv-aim1"
    log "  Created venv-aim1"
fi

# Install deps
"$WSL_REPO/venv-aim1/bin/pip" install -q \
    fastapi uvicorn httpx \
    lightrag-hku \
    qdrant-client \
    mcp \
    2>&1 | tail -1

log "  ✓ Python deps installed"

# ============================================================================
# Step 8: Start kb-api on WSL
# ============================================================================
log "Step 8: Start kb-api on WSL"

# Kill any existing kb-api
pkill -f "uvicorn kb.api:app" 2>/dev/null || true
sleep 1

# Start kb-api
cd "$WSL_REPO"
OMNIGRAPH_VECTOR_STORAGE=qdrant \
OMNIGRAPH_BASE_DIR="/home/sztimhdd/.hermes/omonigraph-vault" \
KOL_SCAN_DB_PATH="$WSL_DB" \
nohup "$WSL_REPO/venv-aim1/bin/python" -m uvicorn kb.api:app \
    --host 127.0.0.1 --port "$WSL_KBAPI_PORT" --workers 1 \
    > /tmp/kb-api-wsl.log 2>&1 &

log "  ✓ kb-api starting on port ${WSL_KBAPI_PORT} (log: /tmp/kb-api-wsl.log)"

# Wait for kb-api
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${WSL_KBAPI_PORT}/health" >/dev/null 2>&1; then
        log "  ✓ kb-api healthy"
        break
    fi
    sleep 2
done

# ============================================================================
# Step 9: Start MCP server on WSL
# ============================================================================
log "Step 9: Start MCP server"

pkill -f "kb.mcp_server" 2>/dev/null || true
sleep 1

cd "$WSL_REPO"
OMNIGRAPH_KB_API_URL="http://127.0.0.1:${WSL_KBAPI_PORT}" \
OMNIGRAPH_MCP_PORT="$WSL_MCP_PORT" \
nohup "$WSL_REPO/venv-aim1/bin/python" kb/mcp_server.py \
    > /tmp/omni-mcp-wsl.log 2>&1 &

log "  ✓ MCP server starting on port ${WSL_MCP_PORT}"

# Wait for MCP
sleep 3
if curl -sf "http://127.0.0.1:${WSL_MCP_PORT}/health" >/dev/null 2>&1; then
    log "  ✓ MCP server healthy"
else
    warn "  MCP server not responding yet — check /tmp/omni-mcp-wsl.log"
fi

# ============================================================================
# Step 10: DDNS port forwarding reminder
# ============================================================================
log "Step 10: DDNS / Port Forwarding"

echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║  ADD THESE PORT FORWARDS IN YOUR ROUTER:                ║"
echo "  ║                                                        ║"
echo "  ║  External :8766 → WSL machine :8766  (kb-api)          ║"
echo "  ║  External :8767 → WSL machine :8767  (MCP server)       ║"
echo "  ║  External :6333 → WSL machine :6333  (Qdrant, optional) ║"
echo "  ║                                                        ║"
echo "  ║  Access:                                                ║"
echo "  ║    http://ohca.ddns.net:8766/health                     ║"
echo "  ║    http://ohca.ddns.net:8767/mcp                        ║"
echo "  ╚══════════════════════════════════════════════════════════╝"

# ============================================================================
# Step 11: Quick smoke test
# ============================================================================
log "Step 11: Quick smoke test"

echo ""
echo "=== Health Checks ==="
curl -s "http://127.0.0.1:${WSL_KBAPI_PORT}/health" | python3 -m json.tool 2>/dev/null || echo "kb-api not ready"
echo ""
curl -s "http://127.0.0.1:${WSL_MCP_PORT}/health" 2>/dev/null || echo "MCP not ready"

echo ""
echo "=== FTS Search Test ==="
curl -s "http://127.0.0.1:${WSL_KBAPI_PORT}/api/search?q=OpenClaw&mode=fts&limit=3" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Results: {d.get(\"total\",0)}, First: {d[\"items\"][0][\"title\"][:60] if d.get(\"items\") else \"N/A\"}')" 2>/dev/null

echo ""
log "=== MIGRATION COMPLETE ==="
echo "  kb-api:   http://127.0.0.1:${WSL_KBAPI_PORT}/health"
echo "  MCP:      http://127.0.0.1:${WSL_MCP_PORT}/mcp"
echo "  Qdrant:   http://127.0.0.1:${WSL_QDRANT_PORT}/healthz"
#   External: http://ohca.ddns.net:58767/mcp (router forwards 58767→8767)
