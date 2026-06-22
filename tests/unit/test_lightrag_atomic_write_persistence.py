"""ISSUES #47 behavior pin: lib.lightrag_atomic_write_patch.apply() must
replace LightRAG's NetworkXStorage.write_nx_graph with an atomic implementation
(tmp + os.fsync + os.replace), so the 6/7 graphml-truncation corruption class
cannot recur even after `pip install --force-reinstall lightrag` reverts the
in-place vendored edit.

The patch is delivered in production via a .pth file (written into both Aliyun
venvs by scripts/apply_lightrag_atomic_write_patch.sh) whose `import`-prefixed
line is exec()'d by the site module at interpreter startup. .pth (not
sitecustomize.py) because Debian ships /usr/lib/python3.11/sitecustomize.py
which shadows any venv-local one — verified 2026-06-11 on Aliyun: the
sitecustomize approach left patch_flag=False at startup. .pth files have no
such first-wins collision; the site module processes ALL of them. These tests
exercise apply() directly so they are hermetic (do NOT depend on the local venv
being pre-patched), plus a static guard on the delivery script so the .pth
mechanism cannot silently regress back to sitecustomize.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_APPLY_SCRIPT = _REPO_ROOT / "scripts" / "apply_lightrag_atomic_write_patch.sh"


@pytest.fixture
def restore_write_nx_graph():
    """Save/restore NetworkXStorage.write_nx_graph so the monkey-patch does not
    leak into other tests in the session (shared module-global class state)."""
    from lightrag.kg import networkx_impl

    cls = networkx_impl.NetworkXStorage
    original = cls.__dict__.get("write_nx_graph")
    flag = "_omnigraph_atomic_write_patched"
    had_flag = flag in cls.__dict__
    try:
        yield
    finally:
        if original is not None:
            cls.write_nx_graph = original
        if not had_flag and flag in cls.__dict__:
            delattr(cls, flag)


@pytest.mark.unit
def test_apply_makes_write_nx_graph_atomic(restore_write_nx_graph) -> None:
    """After apply(), the live write_nx_graph source contains os.replace +
    os.fsync — the two markers that distinguish the atomic implementation from
    vanilla `nx.write_graphml(graph, file_name)`."""
    from lib.lightrag_atomic_write_patch import apply
    from lightrag.kg import networkx_impl

    assert apply() is True, "apply() should succeed when lightrag is importable"

    source = inspect.getsource(networkx_impl.NetworkXStorage.write_nx_graph)
    assert "os.replace" in source, (
        "ISSUES #47 patch missing os.replace — write is not atomic. "
        "graphml truncation corruption class re-opened."
    )
    assert "os.fsync" in source, (
        "ISSUES #47 patch missing os.fsync — tmp data may not be flushed "
        "before rename; a crash post-replace could expose a zero-length file."
    )


@pytest.mark.unit
def test_apply_is_idempotent(restore_write_nx_graph) -> None:
    """apply() twice returns True both times and does not double-wrap (the
    second call is a no-op guarded by the patch flag)."""
    from lib.lightrag_atomic_write_patch import apply
    from lightrag.kg import networkx_impl

    assert apply() is True
    first = networkx_impl.NetworkXStorage.write_nx_graph
    assert apply() is True
    second = networkx_impl.NetworkXStorage.write_nx_graph
    assert first is second, "second apply() must not re-wrap (idempotent)"


@pytest.mark.unit
def test_delivery_uses_pth_not_sitecustomize() -> None:
    """Regression guard for the 2026-06-11 Aliyun deploy bug: the apply script
    MUST deliver the patch via a .pth file, NOT sitecustomize.py. Debian's
    system /usr/lib/pythonX.Y/sitecustomize.py shadows any venv-local one (only
    the first sitecustomize on sys.path is imported), so the original
    sitecustomize approach silently never fired. A .pth `import`-line is exec'd
    by the site module unconditionally and cannot be shadowed."""
    script = _APPLY_SCRIPT.read_text(encoding="utf-8")
    assert ".pth" in script, "delivery must use a .pth file"
    assert 'lib.lightrag_atomic_write_patch' in script, (
        "the .pth line must import + apply the patch module"
    )
    # The script may still `rm -f` the superseded sitecustomize.py, but it must
    # NOT *write* one (the bug). Assert no `> .../sitecustomize.py` redirect.
    assert "sitecustomize.py" not in script or "rm -f" in script, (
        "script must not write sitecustomize.py (Debian shadow bug); "
        "only cleanup of the old file via rm -f is allowed"
    )
