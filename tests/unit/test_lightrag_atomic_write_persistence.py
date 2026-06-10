"""ISSUES #47 behavior pin: lib.lightrag_atomic_write_patch.apply() must
replace LightRAG's NetworkXStorage.write_nx_graph with an atomic implementation
(tmp + os.fsync + os.replace), so the 6/7 graphml-truncation corruption class
cannot recur even after `pip install --force-reinstall lightrag` reverts the
in-place vendored edit.

The patch is delivered in production via a sitecustomize.py (written into both
Aliyun venvs by scripts/apply_lightrag_atomic_write_patch.sh) which imports and
calls apply() at interpreter startup. This test exercises apply() directly so
it is hermetic — it does NOT depend on the local venv being pre-patched.
"""
from __future__ import annotations

import inspect

import pytest


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
