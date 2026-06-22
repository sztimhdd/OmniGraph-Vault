"""Unit coverage for the Hermes-side WeChat-cookie refresh wrapper.

These tests cover the PURE primitives in scripts/lib/cdp_client.py (no live
browser / network) plus the writeback rollback-on-bad-creds branch in
scripts/refresh_wechat_cookie.py (injectable ssh runner, no live Aliyun).

Run with the project venv:
    venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v
"""
import importlib.util
import os
import sys

import pytest

# The wrapper resolves its sibling helper at runtime via
#   sys.path.insert(0, <scripts dir>); from lib.cdp_client import ...
# In pytest, pyproject's `pythonpath = ["."]` puts the repo root first, where a
# DIFFERENT top-level `lib/` package shadows `scripts/lib`. To test the real
# helper without that collision we load scripts/lib/cdp_client.py by file path
# and register it under the `lib.cdp_client` name the wrapper imports, then put
# scripts/ on sys.path so `from lib.cdp_client import ...` (in the wrapper) and
# `from refresh_wechat_cookie import ...` (below) both resolve.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
_CDP_CLIENT_PATH = os.path.join(_SCRIPTS_DIR, "lib", "cdp_client.py")


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Register lib.cdp_client (scripts/lib) so the wrapper's `from lib.cdp_client
# import ...` binds to the real helper, not the shadowing top-level lib/.
_cdp_client = _load_module("lib.cdp_client", _CDP_CLIENT_PATH)
build_cookie_string = _cdp_client.build_cookie_string
extract_token_from_url = _cdp_client.extract_token_from_url
critical_cookies_present = _cdp_client.critical_cookies_present

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ---------------------------------------------------------------------------
# Task 1 — pure primitives (6 behaviors)
# ---------------------------------------------------------------------------

def test_build_cookie_string_sorts_by_name():
    cookies = [{"name": "b", "value": "2"}, {"name": "a", "value": "1"}]
    assert build_cookie_string(cookies) == "a=1; b=2"


def test_build_cookie_string_empty():
    assert build_cookie_string([]) == ""


def test_extract_token_from_url_present():
    url = (
        "https://mp.weixin.qq.com/cgi-bin/home?t=home/index"
        "&lang=zh_CN&token=949047506"
    )
    assert extract_token_from_url(url) == "949047506"


def test_extract_token_from_url_absent_returns_none():
    # Subpage without token → None, must trigger root-nav retry, not crash.
    url = "https://mp.weixin.qq.com/misc/appmsgcomment?x=1"
    assert extract_token_from_url(url) is None


def test_critical_cookies_present_true():
    names = [
        "slave_sid",
        "data_ticket",
        "rand_info",
        "bizuin",
        "slave_user",
        "ua_id",
    ]
    assert critical_cookies_present(names) is True


def test_critical_cookies_present_false():
    assert critical_cookies_present(["ua_id", "_clck"]) is False


# ---------------------------------------------------------------------------
# Task 3 — writeback rollback-on-bad-creds branch (injectable ssh runner)
# ---------------------------------------------------------------------------

class _FakeSshRunner:
    """Records every ssh command and returns a canned exit code per call.

    Mimics subprocess.CompletedProcess(returncode, stdout, stderr). The verify
    test-scan call (the one containing 'batch_scan_kol.py --account') returns the
    configured failure code; all other calls (write, rollback) return 0.
    """

    def __init__(self, verify_returncode):
        self.verify_returncode = verify_returncode
        self.calls = []

    def __call__(self, command):
        self.calls.append(command)

        class _Result:
            def __init__(self, rc, out="", err=""):
                self.returncode = rc
                self.stdout = out
                self.stderr = err

        if "batch_scan_kol.py --account" in command:
            return _Result(
                self.verify_returncode,
                err="WECHAT_SESSION_INVALID: 50/54" if self.verify_returncode else "",
            )
        return _Result(0, out="ok")


def test_writeback_rolls_back_on_bad_creds():
    """When the verify test-scan exits nonzero (bad creds), writeback MUST:
    (a) issue a rollback command restoring kol_config.py.bak-pre-refresh,
    (b) NOT declare success — return a falsey/failure result.
    No live Aliyun: the ssh runner is injected.
    """
    from refresh_wechat_cookie import writeback_to_aliyun

    fake = _FakeSshRunner(verify_returncode=2)  # bad creds → exit 2
    result = writeback_to_aliyun(
        token="123456789",
        cookie_str="a=1; b=2",
        test_account="叶小钗",
        dry_run=False,
        run_ssh=fake,
    )

    # (b) failure returned (not success)
    assert not result, "writeback must return failure when verify scan fails"

    # (a) a rollback ssh command targeting the backup was issued
    rollback_issued = any("bak-pre-refresh" in c for c in fake.calls)
    assert rollback_issued, (
        "writeback must roll back to kol_config.py.bak-pre-refresh on bad creds; "
        f"calls were: {fake.calls}"
    )


def test_writeback_success_when_verify_passes():
    """When the verify test-scan exits 0, writeback declares success and does
    NOT roll back."""
    from refresh_wechat_cookie import writeback_to_aliyun

    fake = _FakeSshRunner(verify_returncode=0)  # ret=0 → valid
    result = writeback_to_aliyun(
        token="123456789",
        cookie_str="a=1; b=2",
        test_account="叶小钗",
        dry_run=False,
        run_ssh=fake,
    )

    assert result, "writeback must return success when verify scan passes"
    rollback_issued = any("bak-pre-refresh" in c and "os.replace" in c for c in fake.calls)
    # No rollback restore on the happy path (the .bak copy is still made pre-write,
    # but no restore-from-bak should run).
    restore_calls = [
        c for c in fake.calls
        if "bak-pre-refresh" in c and "kol_config.py.bak-pre-refresh" in c
        and "replace(" in c and "bak-pre-refresh" in c.split("replace(")[1][:60]
    ]
    assert not restore_calls, f"happy path must not restore from backup: {restore_calls}"
