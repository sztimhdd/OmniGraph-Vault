#!/usr/bin/env bash
# Local E2E test harness — corp-network-aware env setup + multi-mode dispatch.
#
# Usage:
#   ./scripts/local_e2e.sh <mode> [args...]
#
# Modes:
#   rss [--max-articles N | --dry-run]    — enrichment/rss_ingest.py
#   kol [--max-articles N | --dry-run]    — batch_ingest_from_spider.py --from-db
#   wechat <url>                          — ingest_wechat.py 单 URL
#   layer1 <N>                            — Layer 1 only smoke,N 篇 candidates
#   layer2 <N>                            — Layer 2 only smoke,N 篇 (post-Layer1)
#   cleanup                               — scripts/cleanup_stuck_docs.py --dry-run
#   help                                  — print usage + exit 0
#
# Env vars (defaults set, can override via existing env):
#   NODE_EXTRA_CA_CERTS  — ~/.claude/certs/combined-ca-bundle.pem (Cisco Umbrella TLS)
#   GOOGLE_APPLICATION_CREDENTIALS — $(pwd)/.dev-runtime/gcp-paid-sa.json
#   OMNIGRAPH_LLM_PROVIDER         — vertex_gemini (corp blocks DeepSeek)
#   OMNIGRAPH_LLM_MODEL            — gemini-3.1-flash-lite-preview
#   OMNIGRAPH_BASE_DIR             — $(pwd)/.dev-runtime
#   KOL_SCAN_DB_PATH               — $OMNIGRAPH_BASE_DIR/data/kol_scan.db
#                                    (rss_ingest / batch_ingest read this; defaults
#                                    to repo-root data/kol_scan.db without it)
#   PYTHONPATH                     — $(pwd) (so `python -c` snippets can import
#                                    top-level modules like config / lib)
#   DEEPSEEK_API_KEY               — dummy (Phase 5 cross-coupling defense)
#   SCRAPE_CASCADE                 — ua,apify (free first)
#
# Known caveats:
#   - .dev-runtime/gcp-paid-sa.json LACKS aiplatform.endpoints.predict permission;
#     Vertex Gemini calls 403 → LF-1.5 graceful failure path. Happy-path validation
#     runs on Hermes deploy.
#   - DEEPSEEK_API_KEY=dummy 是 import-time defense,任何真 DeepSeek call 会失败 —
#     这是预期(corp network 不可达 api.deepseek.com)。
#
# Output:
#   .scratch/local-e2e-<mode>-<YYYYMMDD-HHMMSS>.log (all stdout+stderr)

set -euo pipefail

# Defaults — override via existing env (the ${VAR:-default} pattern)
export NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-${HOME}/.claude/certs/combined-ca-bundle.pem}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$(pwd)/.dev-runtime/gcp-paid-sa.json}"
export OMNIGRAPH_LLM_PROVIDER="${OMNIGRAPH_LLM_PROVIDER:-vertex_gemini}"
export OMNIGRAPH_LLM_MODEL="${OMNIGRAPH_LLM_MODEL:-gemini-3.1-flash-lite-preview}"
export OMNIGRAPH_BASE_DIR="${OMNIGRAPH_BASE_DIR:-$(pwd)/.dev-runtime}"
export KOL_SCAN_DB_PATH="${KOL_SCAN_DB_PATH:-${OMNIGRAPH_BASE_DIR}/data/kol_scan.db}"
export PYTHONPATH="${PYTHONPATH:-$(pwd)}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-dummy}"
export SCRAPE_CASCADE="${SCRAPE_CASCADE:-ua,apify}"

# Cross-platform Python venv resolution: Windows (Git Bash) → Linux/Mac fallback
if [[ -x "venv/Scripts/python.exe" ]]; then
  PYTHON="venv/Scripts/python.exe"
elif [[ -x "venv/Scripts/python" ]]; then
  PYTHON="venv/Scripts/python"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON="venv/bin/python"
else
  echo "ERROR: Python venv not found at venv/Scripts/python(.exe) or venv/bin/python" >&2
  exit 1
fi

print_usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^#\{1,2\} \{0,1\}//;s/^#//'
}

MODE="${1:-help}"
[[ $# -ge 1 ]] && shift

# help short-circuit BEFORE pre-flight (so help works on a broken environment)
if [[ "$MODE" == "help" || "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  print_usage
  exit 0
fi

# --- pre-flight ---
[[ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]] || {
  echo "ERROR: SA missing at $GOOGLE_APPLICATION_CREDENTIALS" >&2; exit 1; }
[[ -d "$OMNIGRAPH_BASE_DIR" ]] || {
  echo "ERROR: OMNIGRAPH_BASE_DIR missing: $OMNIGRAPH_BASE_DIR" >&2; exit 1; }
[[ -f "$OMNIGRAPH_BASE_DIR/data/kol_scan.db" ]] || {
  echo "ERROR: DB missing at $OMNIGRAPH_BASE_DIR/data/kol_scan.db" >&2; exit 1; }

mkdir -p .scratch

TS=$(date +%Y%m%d-%H%M%S)
LOG=".scratch/local-e2e-${MODE}-${TS}.log"
EXIT=0

# --- mode dispatch ---
# Disable -e here so a non-zero python exit doesn't bypass our EXIT capture +
# trailing log marker. pipefail still propagates the python rc into PIPESTATUS[0].
set +e
case "$MODE" in
  rss)
    echo "[local-e2e] mode=rss → python -m enrichment.rss_ingest $*" | tee "$LOG"
    # Module form so repo root stays on sys.path (enrichment/rss_ingest.py
    # imports top-level image_pipeline / config — invoking the path directly
    # makes Python set sys.path[0] = enrichment/ and the imports break).
    "$PYTHON" -m enrichment.rss_ingest "$@" 2>&1 | tee -a "$LOG"
    ;;
  kol)
    echo "[local-e2e] mode=kol → batch_ingest_from_spider.py --from-db $*" | tee "$LOG"
    "$PYTHON" batch_ingest_from_spider.py --from-db "$@" 2>&1 | tee -a "$LOG"
    ;;
  wechat)
    [[ $# -ge 1 ]] || { echo "ERROR: wechat mode requires a URL" >&2; exit 2; }
    echo "[local-e2e] mode=wechat → ingest_wechat.py $1" | tee "$LOG"
    "$PYTHON" ingest_wechat.py "$1" 2>&1 | tee -a "$LOG"
    ;;
  layer1)
    N="${1:-5}"
    echo "[local-e2e] mode=layer1 → Layer 1 only smoke, N=$N" | tee "$LOG"
    "$PYTHON" -c "
import asyncio, sqlite3, os
from lib.article_filter import layer1_pre_filter, ArticleMeta
db = sqlite3.connect(os.path.join(os.environ['OMNIGRAPH_BASE_DIR'], 'data', 'kol_scan.db'))
rows = db.execute('SELECT id, title, digest FROM articles WHERE layer1_verdict IS NULL LIMIT ?', (${N},)).fetchall()
metas = [ArticleMeta(id=r[0], source='wechat', title=r[1] or '', summary=r[2] or '', content_length=None) for r in rows]
print(f'[layer1-smoke] selected {len(metas)} articles')
res = asyncio.run(layer1_pre_filter(metas))
for m, r in zip(metas, res):
    print(f'id={m.id} verdict={r.verdict} reason={r.reason}')
" 2>&1 | tee -a "$LOG"
    ;;
  layer2)
    N="${1:-5}"
    echo "[local-e2e] mode=layer2 → Layer 2 only smoke, N=$N" | tee "$LOG"
    "$PYTHON" -c "
import asyncio, sqlite3, os
from lib.article_filter import layer2_full_body_score, ArticleWithBody
db = sqlite3.connect(os.path.join(os.environ['OMNIGRAPH_BASE_DIR'], 'data', 'kol_scan.db'))
rows = db.execute(\"SELECT id, title, body FROM articles WHERE layer1_verdict='candidate' AND body IS NOT NULL AND length(body) > 0 LIMIT ?\", (${N},)).fetchall()
arts = [ArticleWithBody(id=r[0], source='wechat', title=r[1] or '', body=r[2] or '') for r in rows]
print(f'[layer2-smoke] selected {len(arts)} articles with body+layer1=candidate')
res = asyncio.run(layer2_full_body_score(arts))
for a, r in zip(arts, res):
    print(f'id={a.id} verdict={r.verdict} reason={r.reason}')
" 2>&1 | tee -a "$LOG"
    ;;
  cleanup)
    echo "[local-e2e] mode=cleanup → cleanup_stuck_docs.py --dry-run" | tee "$LOG"
    "$PYTHON" scripts/cleanup_stuck_docs.py --dry-run 2>&1 | tee -a "$LOG"
    ;;
  *)
    set -e
    echo "ERROR: unknown mode '$MODE'" >&2
    print_usage
    exit 0
    ;;
esac

EXIT=${PIPESTATUS[0]}
set -e
echo "[local-e2e] EXIT=$EXIT  log=$LOG"
exit "$EXIT"
