#!/bin/bash
# OmniGraph-Vault Installation Script for Hermes
#
# Phase 2: Infrastructure hardening
# This is a template with logical flow documented.
# Full bash implementation to follow in Phase 2 execution.
#
# Purpose: Setup venv, install dependencies, validate environment, run smoke test
# Exit: 0 on success, 1 on error
#
# Usage:
#   bash scripts/install-for-hermes.sh
#   bash scripts/install-for-hermes.sh --skip-test  # skip smoke test
#

set -e  # Exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

# ============================================================================
# Step 1: Check if GEMINI_API_KEY is set
# ============================================================================
# Purpose: Fail fast if core API key is missing
#
# Pseudocode:
#   if GEMINI_API_KEY is not set (env var or ~/.hermes/.env):
#     print error message to stderr
#     suggest how to fix: "Add GEMINI_API_KEY to ~/.hermes/.env"
#     exit 1
#   endif

echo "Step 1: Checking GEMINI_API_KEY..."
# Load ~/.hermes/.env if it exists
if [[ -f "$HOME/.hermes/.env" ]]; then
    export $(cat "$HOME/.hermes/.env" | grep GEMINI_API_KEY)
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo "⚠️  Configuration error: GEMINI_API_KEY is not set." >&2
    echo "   Add it to ~/.hermes/.env and restart." >&2
    echo "   Example: echo 'GEMINI_API_KEY=your_key_here' >> ~/.hermes/.env" >&2
    exit 1
fi

echo "✓ GEMINI_API_KEY found"

# ============================================================================
# Step 2: Create runtime directories
# ============================================================================
# Purpose: Ensure ~/.hermes/omonigraph-vault/ exists with all required subdirs
#
# Pseudocode:
#   mkdir -p ~/.hermes/omonigraph-vault/
#   mkdir -p ~/.hermes/omonigraph-vault/images/
#   mkdir -p ~/.hermes/omonigraph-vault/lightrag_storage/
#   mkdir -p ~/.hermes/omonigraph-vault/entity_buffer/
#   echo "Created runtime data directories"

echo "Step 2: Creating runtime directories..."
mkdir -p "$HOME/.hermes/omonigraph-vault/"{images,lightrag_storage,entity_buffer}
echo "✓ Runtime directories created"

# ============================================================================
# Step 3: Create .env file from template if missing
# ============================================================================
# Purpose: Provide a starting point for ~/.hermes/.env
#
# Pseudocode:
#   if ~/.hermes/.env does not exist:
#     copy .env.template to ~/.hermes/.env
#     print "Created ~/.hermes/.env from template"
#     print "Edit it and add your actual API keys"
#   endif

echo "Step 3: Setting up environment file..."
if [[ ! -f "$HOME/.hermes/.env" ]]; then
    cp "$PROJECT_ROOT/.env.template" "$HOME/.hermes/.env"
    echo "✓ Created ~/.hermes/.env from template"
    echo "  Edit it and add your actual API keys"
else
    echo "✓ ~/.hermes/.env already exists"
fi

# ============================================================================
# Step 4: Create Python venv
# ============================================================================
# Purpose: Isolated Python environment for OmniGraph-Vault
#
# Pseudocode:
#   if venv does not exist:
#     python -m venv $VENV_PATH
#     print "Created Python venv at $VENV_PATH"
#   endif
#   activate venv
#   print "Venv activated"

echo "Step 4: Setting up Python virtual environment..."
if [[ ! -d "$VENV_PATH" ]]; then
    python3 -m venv "$VENV_PATH"
    echo "✓ Created venv at $VENV_PATH"
else
    echo "✓ Venv already exists"
fi

# Activate venv (both Windows and Unix)
if [[ -f "$VENV_PATH/Scripts/activate" ]]; then
    source "$VENV_PATH/Scripts/activate"
elif [[ -f "$VENV_PATH/bin/activate" ]]; then
    source "$VENV_PATH/bin/activate"
else
    echo "⚠️  Error: Could not find venv activation script" >&2
    exit 1
fi
echo "✓ Venv activated"

# ============================================================================
# Step 5: Install Python dependencies
# ============================================================================
# Purpose: Install all packages from requirements.txt
#
# Pseudocode:
#   pip install --upgrade pip
#   pip install -r requirements.txt
#   print "Dependencies installed"

echo "Step 5: Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
echo "✓ Dependencies installed"

# ============================================================================
# Step 6: Validate imports
# ============================================================================
# Purpose: Verify core libraries are importable (fail fast on broken env)
#
# Pseudocode:
#   for each library in [lightrag, cognee, google.genai]:
#     try:
#       python -c "import <library>"
#       print "✓ <library> OK"
#     except:
#       print error message
#       exit 1

echo "Step 6: Validating imports..."
VALIDATORS=(
    "from lightrag import LightRAG|LightRAG"
    "import cognee|Cognee"
    "from google import genai|Gemini"
)

for validator in "${VALIDATORS[@]}"; do
    IFS='|' read -r import_statement lib_name <<< "$validator"
    if python -c "$import_statement" 2>/dev/null; then
        echo "✓ $lib_name OK"
    else
        echo "⚠️  Import failed: $import_statement" >&2
        exit 1
    fi
done

# ============================================================================
# Step 7: Run smoke test (optional)
# ============================================================================
# Purpose: Quick validation that skill_runner works and can reach Gemini API
#
# Pseudocode:
#   if --skip-test flag not passed:
#     print "Running smoke test (this may take 30-60 seconds)..."
#     python skill_runner.py skills/ --quick
#     if skill_runner exits 0:
#       print "Smoke test passed"
#     else:
#       print error message
#       exit 1

if [[ "$1" != "--skip-test" ]]; then
    echo "Step 7: Running smoke test..."
    if python "$PROJECT_ROOT/skill_runner.py" skills/ --quick 2>&1; then
        echo "✓ Smoke test passed"
    else
        echo "⚠️  Smoke test failed. Run for details:" >&2
        echo "   python skill_runner.py skills/ --test-all" >&2
        exit 1
    fi
fi

# ============================================================================
# Success
# ============================================================================
echo ""
echo "✅ Setup complete. Ready to use OmniGraph-Vault skills."
echo ""
echo "Next steps:"
echo "1. Start local Edge CDP (if not already running):"
echo "   msedge --remote-debugging-port=9223"
echo "2. Test a skill:"
echo "   python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json"
echo "3. Ingest an article:"
echo "   python ingest_wechat.py 'https://mp.weixin.qq.com/s/...'"
echo ""

exit 0
