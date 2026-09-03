"""
Unit regression: healthcheck alert must label the ohca/Playwright cookie MCP
distinctly from the KG MCP.

scripts/mcp-healthcheck.py probes the ohca/Playwright cookie MCP reverse
tunnel (http://127.0.0.1:58931/mcp) — NOT the knowledge-base KG MCP
(:8767/:8768). Its alert used to read `mcp=down`, which is easily misread as
the KG MCP being down (e.g. the 2026-09-01 ~21h WSL-offline alert). The
minimal fix relabels only the human-visible alert text to `ohca-mcp=down`.

The script is a top-level imperative cron script — importing it would run live
probes, SSH repair, Telegram notify and sys.exit — so this unit test executes
the pure alert-rendering function extracted from the module source via `ast`
(same pattern intent as test_mcp_scraper_tool_name.py: side-effect-free
source-level regression, no network / no mocking). A second test pins the
contract that the internal throttle signature still uses the raw `mcp` name:
no throttle-state / alert-sig change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mcp-healthcheck.py"


def _load_module_level(name: str, ns: dict) -> None:
    """Exec the module-level node defining `name` from mcp-healthcheck.py into ns."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        is_assign = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        )
        is_func = isinstance(node, ast.FunctionDef) and node.name == name
        if is_assign or is_func:
            mod = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(mod)
            exec(compile(mod, str(SCRIPT), "exec"), ns)  # noqa: S102 — isolated, file-local
            return
    pytest.fail(f"module-level {name!r} not found in {SCRIPT.name}")


@pytest.mark.unit
def test_alert_detail_labels_playwright_mcp_as_ohca_mcp() -> None:
    """The human-visible alert must say ohca-mcp=down, never mcp=down."""
    ns: dict = {}
    _load_module_level("ALERT_LABELS", ns)
    _load_module_level("alert_detail", ns)
    alert_detail = ns["alert_detail"]

    rendered = alert_detail([("mcp", "down")])
    assert rendered == "ohca-mcp=down"
    # The raw internal name must never surface as an alert key ("ohca-mcp"
    # contains the substring but the parsed key must be the full label).
    keys = [seg.split("=", 1)[0] for seg in rendered.split("; ")]
    assert keys == ["ohca-mcp"]

    # Other checks keep their names; only the Playwright-cookie MCP check is remapped.
    rendered_all = alert_detail([("kb-api", "down"), ("mcp", "down"), ("disk", "90% used")])
    keys_all = [seg.split("=", 1)[0] for seg in rendered_all.split("; ")]
    assert keys_all == ["kb-api", "ohca-mcp", "disk"]
    assert "mcp" not in keys_all
    assert rendered_all == "kb-api=down; ohca-mcp=down; disk=90% used"


@pytest.mark.unit
def test_throttle_signature_keeps_raw_internal_names() -> None:
    """Alert throttle sig must still be built from raw problem names (no sig change)."""
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "sig" for t in node.targets
        ):
            rendered = ast.unparse(node.value)
            assert "ALERT_LABELS" not in rendered, "sig must not use display labels"
            assert "alert_detail" not in rendered, "sig must not use display rendering"
            assert "{n}={s}" in rendered or "n=s" in rendered
            break
    else:
        pytest.fail("sig = ... assignment not found in report block")
