#!/usr/bin/env bash
# Unit test for register_phase5_cron.sh PATH bug fix
# Verifies that generated cron commands use absolute paths to venv python

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTER_SCRIPT="${SCRIPT_DIR}/scripts/register_phase5_cron.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

test_count=0
pass_count=0
fail_count=0

# Test runner
run_test() {
    local test_name="$1"
    local test_fn="$2"
    ((test_count++))
    echo -n "Test $test_count: $test_name ... "
    if $test_fn; then
        echo -e "${GREEN}PASS${NC}"
        ((pass_count++))
    else
        echo -e "${RED}FAIL${NC}"
        ((fail_count++))
    fi
}

# Test 1: Check that absolute path to venv python is present
test_absolute_path_present() {
    grep -q "/home/sztimhdd/OmniGraph-Vault/venv/bin/python" "${REGISTER_SCRIPT}" && return 0 || return 1
}

# Test 2: Check that bare 'python ' (space after) does NOT appear in job commands
test_no_bare_python() {
    # Search for patterns like "python enrichment/" or "python batch_classify" (bare python)
    # but exclude lines that define the VENV_PY variable itself
    if grep -E 'add_job|replace_job' "${REGISTER_SCRIPT}" | grep -v 'VENV_PY=' | grep -E '&& python [a-z]' > /dev/null; then
        return 1  # Found bare python in job commands
    else
        return 0  # No bare python in job commands
    fi
}

# Test 3: Check that rss-rescrape-bodies job uses absolute path
test_rss_rescrape_absolute_path() {
    grep -A 2 '"rss-rescrape-bodies"' "${REGISTER_SCRIPT}" | grep -q '${VENV_PY}' && return 0 || return 1
}

# Test 4: Check that daily-classify-rss-layer2 job uses absolute path
test_daily_classify_rss_absolute_path() {
    grep -A 2 '"daily-classify-rss-layer2"' "${REGISTER_SCRIPT}" | grep -q '${VENV_PY}' && return 0 || return 1
}

# Test 5: Check that reconcile-ingestions job uses absolute path
test_reconcile_ingestions_absolute_path() {
    grep -A 2 '"reconcile-ingestions"' "${REGISTER_SCRIPT}" | grep -q '${VENV_PY}' && return 0 || return 1
}

# Test 6: Check that OMNIGRAPH_DIR variable is defined with default
test_omnigraph_dir_defined() {
    grep -q 'OMNIGRAPH_DIR="${OMNIGRAPH_DIR:-' "${REGISTER_SCRIPT}" && return 0 || return 1
}

# Test 7: Check that cd uses OMNIGRAPH_DIR not tilde
test_cd_uses_omnigraph_dir() {
    # Look for problematic "cd ~/" patterns in job commands
    if grep -A 1 'add_job\|replace_job' "${REGISTER_SCRIPT}" | grep -q 'cd ~/'; then
        return 1  # Found problematic tilde usage
    else
        return 0  # No tilde usage in job commands
    fi
}

# Test 8: Count that exactly 3 jobs use ${VENV_PY}
test_three_jobs_fixed() {
    local count=$(grep -c '${VENV_PY}' "${REGISTER_SCRIPT}")
    # Should be 3 uses in the three fixed job commands, plus 1 in variable definition = 4 total
    [[ $count -ge 4 ]] && return 0 || return 1
}

# Test 9: Syntax check
test_bash_syntax() {
    bash -n "${REGISTER_SCRIPT}" && return 0 || return 1
}

# Test 10: Check that other jobs (using hermes cron add "run") are not affected
test_hermes_run_jobs_unchanged() {
    # Count "run enrichment/" and "run batch_" patterns — should still use "run" keyword
    local run_count=$(grep -c 'hermes cron add.*"run ' "${REGISTER_SCRIPT}")
    [[ $run_count -ge 5 ]] && return 0 || return 1  # At least 5 jobs use "run" pattern
}

# Run all tests
run_test "Absolute venv python path present" test_absolute_path_present
run_test "No bare 'python ' in job commands" test_no_bare_python
run_test "rss-rescrape-bodies uses absolute path" test_rss_rescrape_absolute_path
run_test "daily-classify-rss-layer2 uses absolute path" test_daily_classify_rss_absolute_path
run_test "reconcile-ingestions uses absolute path" test_reconcile_ingestions_absolute_path
run_test "OMNIGRAPH_DIR variable defined with default" test_omnigraph_dir_defined
run_test "cd commands use OMNIGRAPH_DIR not tilde" test_cd_uses_omnigraph_dir
run_test "Exactly 3+ jobs use \${VENV_PY}" test_three_jobs_fixed
run_test "Bash syntax is valid" test_bash_syntax
run_test "Other 'run' jobs unchanged" test_hermes_run_jobs_unchanged

# Report
echo ""
echo "========================================"
echo "Test Results: $pass_count/$test_count PASSED"
echo "========================================"

if [[ $fail_count -gt 0 ]]; then
    exit 1
else
    exit 0
fi
