#!/usr/bin/env bash
# scripts/local_dev_start.sh
# LDEV-08 (quick task 260504-g7a): Bash / WSL local-dev bootstrap.
# Loads .dev-runtime/.env (no-overwrite), verifies prereqs, starts image server.

set -u

# --- Banner ---
echo "================================================================"
echo "  OmniGraph-Vault local dev bootstrap"
echo "  Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Cwd:  $(pwd)"
echo "================================================================"

# --- UTF-8 for stdout ---
export PYTHONIOENCODING=utf-8
echo "[OK ] PYTHONIOENCODING=utf-8"

# --- Load .dev-runtime/.env without overwriting existing process env ---
env_file=".dev-runtime/.env"
if [[ ! -f "$env_file" ]]; then
    echo "[FAIL] $env_file not found."
    echo "       Pre-populate .dev-runtime/ first (see docs/LOCAL_DEV_SETUP.md sec 2)."
    exit 1
fi
echo "[OK ] .dev-runtime/.env exists"

loaded=0
while IFS= read -r line || [[ -n "$line" ]]; do
    # trim
    trimmed="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "$trimmed" || "$trimmed" == \#* ]] && continue
    [[ "$trimmed" != *=* ]] && continue
    k="${trimmed%%=*}"
    v="${trimmed#*=}"
    k="$(echo "$k" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    v="$(echo "$v" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    # strip one pair of surrounding quotes
    v="${v%\'}"; v="${v#\'}"; v="${v%\"}"; v="${v#\"}"
    [[ -z "$k" ]] && continue
    # No-overwrite
    if [[ -z "${!k:-}" ]]; then
        export "$k=$v"
        loaded=$((loaded + 1))
    fi
done < "$env_file"
echo "[OK ] loaded $loaded var(s) from .dev-runtime/.env (no-overwrite)"

# --- Prereq: SA JSON (only when vertex_gemini) ---
if [[ "${OMNIGRAPH_LLM_PROVIDER:-}" == "vertex_gemini" ]]; then
    if [[ ! -f ".dev-runtime/gcp-paid-sa.json" ]]; then
        echo "[FAIL] .dev-runtime/gcp-paid-sa.json missing (required for vertex_gemini mode)"
        exit 1
    fi
    echo "[OK ] .dev-runtime/gcp-paid-sa.json exists"
else
    echo "[--] vertex_gemini mode not active; skipping SA JSON check"
fi

# --- Prereq: OMNIGRAPH_BASE_DIR (if set) points at an existing dir ---
if [[ -n "${OMNIGRAPH_BASE_DIR:-}" ]]; then
    if [[ ! -d "$OMNIGRAPH_BASE_DIR" ]]; then
        echo "[FAIL] OMNIGRAPH_BASE_DIR=$OMNIGRAPH_BASE_DIR is not an existing directory"
        exit 1
    fi
    echo "[OK ] OMNIGRAPH_BASE_DIR exists: $OMNIGRAPH_BASE_DIR"
else
    echo "[WARN] OMNIGRAPH_BASE_DIR unset; using Hermes default (~/.hermes/omonigraph-vault)"
fi

# --- Prereq: kol_scan.db (canonical pipeline DB — batch_ingest_from_spider.py:86) ---
if [[ ! -f ".dev-runtime/data/kol_scan.db" ]]; then
    echo "[FAIL] .dev-runtime/data/kol_scan.db missing (DB sanity check)"
    exit 1
fi
echo "[OK ] .dev-runtime/data/kol_scan.db exists"

# --- Prereq: venv python (Windows layout — local dev targets venv/Scripts/) ---
if [[ ! -f "venv/Scripts/python.exe" ]]; then
    echo "[FAIL] venv/Scripts/python.exe missing — activate venv or re-create it"
    exit 1
fi
echo "[OK ] venv/Scripts/python.exe exists"

# --- Start image server on port 8765 (background) ---
if [[ -n "${OMNIGRAPH_BASE_DIR:-}" ]]; then
    img_dir="$OMNIGRAPH_BASE_DIR/images"
    log_dir="$OMNIGRAPH_BASE_DIR/logs"
else
    img_dir="$HOME/.hermes/omonigraph-vault/images"
    log_dir=".dev-runtime/logs"
fi
if [[ ! -d "$img_dir" ]]; then
    echo "[FAIL] image dir $img_dir does not exist"
    exit 1
fi
mkdir -p "$log_dir"
log_path="$log_dir/image_server.log"
nohup venv/Scripts/python -m http.server 8765 --directory "$img_dir" \
    > "$log_path" 2>&1 &
image_pid=$!
echo "[OK ] image server started  PID=$image_pid  URL=http://localhost:8765"
echo "       logs -> $log_path"

# --- Next-step commands ---
echo ""
echo "Next:"
echo "  venv/Scripts/python -c \"from lib.llm_complete import get_llm_func; print(get_llm_func().__name__)\""
echo "  venv/Scripts/python -c \"import config; print(config.BASE_DIR)\""
echo "  venv/Scripts/python ingest_wechat.py <test-url>"
echo ""
echo "Image server PID: $image_pid  (kill $image_pid to stop)"
