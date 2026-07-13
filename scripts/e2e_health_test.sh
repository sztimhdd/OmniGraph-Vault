#!/bin/bash
# OmniGraph E2E Health Test — Automated Test Runner
#
# Purpose: Run the complete ingestion pipeline in a controlled test environment
# Usage: ./e2e_health_test.sh [--dry-run] [--quick]
#
# Modes:
#   (default)  : Full E2E test (all 7 phases, ~20-30 min)
#   --quick    : Abbreviated test (KOL + L1/L2 + ainsert only, ~10 min)
#   --dry-run  : Report what would run without actually running

set -u

readonly TEST_MODE="${1:---full}"
readonly ALIYUN_SSH="aliyun-vitaclaw"
readonly ALIYUN_DIR="/root/OmniGraph-Vault"
readonly REPORT_DIR="/tmp/e2e_health_test_$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

preflight_check() {
    log_info "Running preflight checks..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"

# Check disk
DISK_USED=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [[ $DISK_USED -gt 90 ]]; then
    echo "ERROR: Disk usage ${DISK_USED}% — cleanup first"
    exit 1
fi

# Check services
systemctl is-active omnigraph-kol-scan-batch@1 > /dev/null || {
    echo "WARN: KOL scan service not active"
}

# Check DB
sqlite3 data/kol_scan.db "SELECT 1" > /dev/null || {
    echo "ERROR: kol_scan.db not accessible"
    exit 1
}

# Check graphml
python3 -c "import networkx as nx; g = nx.read_graphml('/root/.hermes/omonigraph-vault/lightrag_storage/graphml'); print(f'OK: {g.number_of_nodes()} nodes')" || {
    echo "ERROR: graphml not readable"
    exit 1
}

echo "Preflight OK"
EOF
}

phase_1_kol_scan() {
    log_info "Phase 1a: KOL Scan..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 batch_scan_kol.py --max-accounts 1 --max-articles 5 2>&1 | tail -20
EOF
}

phase_1_rss_scan() {
    log_info "Phase 1b: RSS Scan..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 scripts/rss_classifier.py --max-articles 3 2>&1 | tail -20
EOF
}

phase_2_classification() {
    log_info "Phase 2: Layer 1 & 2 Classification..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 batch_classify_kol.py --topics ai --max-articles 10 2>&1 | tail -30
EOF
}

phase_4_full_ingest() {
    log_info "Phase 4: Full Ingest Pipeline (scrape → ainsert)..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 batch_ingest_from_spider.py --topics ai --depth 1 --max-articles 1 2>&1 | tail -50
EOF
}

phase_5_db_verify() {
    log_info "Phase 5: Database Verification..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
sqlite3 data/kol_scan.db << 'SQL'
SELECT
  COUNT(*) as total_ok,
  MAX(ingested_at) as latest_ingest
FROM ingestions
WHERE status='ok' AND ingested_at > datetime('now', '-30 min');
SQL
EOF
}

phase_6_graphml_verify() {
    log_info "Phase 6: graphml Update Verification..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 -c "
import networkx as nx
g = nx.read_graphml('/root/.hermes/omonigraph-vault/lightrag_storage/graphml')
print(f'graphml: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges')
"
EOF
}

phase_7_rag_query() {
    log_info "Phase 7: RAG Retrieval Test..."

    ssh "$ALIYUN_SSH" << 'EOF'
cd "$ALIYUN_DIR"
python3 kg_synthesize.py "What was the main topic of the most recent article?" hybrid 2>&1 | head -50
EOF
}

run_full_test() {
    log_info "===== E2E HEALTH TEST (FULL MODE) ====="

    preflight_check || {
        log_error "Preflight failed"
        return 1
    }

    phase_1_kol_scan
    phase_1_rss_scan
    phase_2_classification
    phase_4_full_ingest
    phase_5_db_verify
    phase_6_graphml_verify
    phase_7_rag_query

    log_info "===== E2E TEST COMPLETE ====="
    log_info "Review the output above for any errors (look for ERROR or exception lines)"
}

run_quick_test() {
    log_info "===== E2E HEALTH TEST (QUICK MODE) ====="

    preflight_check || {
        log_error "Preflight failed"
        return 1
    }

    phase_1_kol_scan
    phase_2_classification
    phase_4_full_ingest
    phase_5_db_verify

    log_info "===== QUICK TEST COMPLETE ====="
}

dry_run_test() {
    log_info "===== DRY RUN MODE ====="
    echo "Would execute:"
    echo "  1. KOL Scan (--max-accounts 1 --max-articles 5)"
    echo "  2. RSS Scan (--max-articles 3)"
    echo "  3. L1/L2 Classification (--max-articles 10)"
    echo "  4. Full Ingest (--max-articles 1)"
    echo "  5. DB Verification"
    echo "  6. graphml Verification"
    echo "  7. RAG Query Test"
    echo ""
    echo "To run: ./e2e_health_test.sh --full"
}

main() {
    mkdir -p "$REPORT_DIR"

    case "$TEST_MODE" in
        --full)
            run_full_test
            ;;
        --quick)
            run_quick_test
            ;;
        --dry-run)
            dry_run_test
            ;;
        *)
            log_error "Unknown mode: $TEST_MODE"
            echo "Usage: $0 [--full | --quick | --dry-run]"
            return 1
            ;;
    esac
}

main "$@"
