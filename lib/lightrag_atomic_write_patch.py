"""ISSUES #47: sitecustomize-importable monkey-patch making LightRAG's
``NetworkXStorage.write_nx_graph`` atomic (tmp + fsync + os.replace).

Background: 2026-06-07 a SIGTERM landed mid-``nx.write_graphml()`` on Aliyun and
truncated the live ``graph_chunk_entity_relation.graphml`` (35h compound outage,
see ``2026_06_08_aliyun_recovery_postmortem`` memory). The ``260608-e8l``
recovery patched ``lightrag/kg/networkx_impl.py`` in-place in both venvs, but
``pip install --force-reinstall lightrag`` (or any version bump) silently reverts
that vendored edit — the corruption class would then be free to recur.

This module re-applies the same atomic-write wrapper at interpreter startup via
a ``sitecustomize.py`` that calls :func:`apply` (installed by
``scripts/apply_lightrag_atomic_write_patch.sh``). The guard therefore survives
package reinstalls. The function is idempotent and fail-soft.
"""
from __future__ import annotations

_PATCH_FLAG = "_omnigraph_atomic_write_patched"


def apply() -> bool:
    """Monkey-patch ``NetworkXStorage.write_nx_graph`` to write atomically.

    Writes the graphml to a sibling ``.tmp`` file, ``os.fsync``s it, then
    ``os.replace``s it over the target — so a SIGKILL/SIGTERM at any instant
    leaves either the old intact file or the new intact file, never a torn one.

    Returns:
        True  — patch applied (or already applied; idempotent no-op).
        False — LightRAG not importable yet (fail-soft, e.g. fresh deploy
                before ``pip install``).
    """
    try:
        from lightrag.kg import networkx_impl
    except Exception:  # noqa: BLE001 — fail-soft: missing/partial install
        return False

    storage_cls = getattr(networkx_impl, "NetworkXStorage", None)
    if storage_cls is None:
        return False
    if getattr(storage_cls, _PATCH_FLAG, False):
        return True  # already patched this interpreter

    import os
    import tempfile

    import networkx as nx
    from lightrag.utils import logger

    def _atomic_write_nx_graph(graph, file_name, workspace="_"):
        logger.info(
            f"[{workspace}] Writing graph with {graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges (atomic, ISSUES #47)"
        )
        target_dir = os.path.dirname(os.path.abspath(file_name)) or "."
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".graphml-", suffix=".tmp")
        os.close(fd)
        try:
            nx.write_graphml(graph, tmp_path)
            # fsync the tmp file's data to disk before the rename so a crash
            # immediately after os.replace cannot expose a zero-length file.
            with open(tmp_path, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp_path, file_name)  # atomic on POSIX same-filesystem
        except BaseException:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise

    storage_cls.write_nx_graph = staticmethod(_atomic_write_nx_graph)
    setattr(storage_cls, _PATCH_FLAG, True)
    return True
