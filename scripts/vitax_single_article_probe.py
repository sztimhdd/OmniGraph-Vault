#!/usr/bin/env python3
"""Fail-closed, single synthetic-text LightRAG probe for later controller review.

Running without ``--execute`` only creates a receipt.  Runtime imports, Hermes,
the local embedding endpoint, and storage writes are unreachable in that mode.
``--execute`` is intentionally for a separately authorized isolated host run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as etree
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlparse


class IsolationError(ValueError):
    """A requested probe path could overlap an unsafe destination."""


class ProbeError(RuntimeError):
    """A redacted probe failure whose details remain in an owned local log."""

    def __init__(self, code: str, log_path: Path):
        self.code = code
        self.log_path = log_path
        super().__init__(f"{code}; see {log_path}")


_MARKER = "VITAX_SINGLE_ARTICLE_PROBE_MARKER"
_URL = "https://vitax.invalid/single-article-probe"
_MAX_HERMES_COMPLETIONS = 12
_VERIFY_TIMEOUT_SECONDS = 20 * 60
_OWNER_FILE = ".vitax-single-article-owned.json"


@dataclass(frozen=True)
class ProbePlan:
    run_dir: Path
    base_dir: Path
    rag_dir: Path
    checkpoint_dir: Path
    sqlite_path: Path
    environment: dict[str, str]


def _candidate_root() -> Path:
    """Use only the candidate checkout containing this runner, never a production root."""
    root = Path(__file__).resolve().parents[1]
    if not (root / "scripts" / Path(__file__).name).is_file():
        raise IsolationError("runner is not located below a candidate repository root")
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return root


def _assert_candidate_imports(root: Path) -> None:
    """Fail if any loaded project module came from a production checkout fallback."""
    project_names = {"config", "ingest_wechat", "image_pipeline"}
    offenders: list[str] = []
    for name, module in tuple(sys.modules.items()):
        if name not in project_names and not name.startswith("lib"):
            continue
        module_path = getattr(module, "__file__", None)
        if not module_path:
            continue
        try:
            Path(module_path).resolve().relative_to(root)
        except ValueError:
            offenders.append(name)
    if offenders:
        raise ProbeError("CANDIDATE_IMPORT_FALLBACK", root / "runtime.log")


def _symlink_ancestor(path: Path) -> Path | None:
    current = Path(path.absolute().anchor)
    for component in path.absolute().parts[1:]:
        current /= component
        if current.is_symlink():
            return current
    return None


def _validated_parent(parent_dir: Path) -> Path:
    if ".." in parent_dir.parts:
        raise IsolationError(f"unsafe parent path traversal: {parent_dir}")
    symlink = _symlink_ancestor(parent_dir)
    if symlink is not None:
        raise IsolationError(f"unsafe parent symlink ancestor: {symlink}")
    parent = parent_dir.resolve(strict=True)
    if parent in {Path("/"), Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}:
        raise IsolationError(f"unsafe parent directory: {parent}")
    if not parent.is_dir():
        raise IsolationError(f"parent is not a directory: {parent}")
    return parent


def _validated_loopback_embedding_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if (
        parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
        or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
    ):
        raise IsolationError("embedding URL must be an explicit http loopback endpoint with a port")
    if parsed.path != "/embeddings" or raw_url != f"http://127.0.0.1:{parsed.port}/embeddings":
        raise IsolationError("embedding URL must target an /embeddings endpoint")
    return raw_url


def create_probe_plan(*, parent_dir: Path, hermes_bin: Path, embedding_url: str) -> ProbePlan:
    """Create one empty, owned run directory and a credential-free env plan."""
    parent = _validated_parent(parent_dir)
    if not hermes_bin.is_absolute():
        raise IsolationError("Hermes binary must be an absolute path")
    embedding_url = _validated_loopback_embedding_url(embedding_url)
    run_dir = Path(tempfile.mkdtemp(prefix="vitax-single-article-", dir=parent)).resolve()
    if run_dir.parent != parent or run_dir.is_symlink():
        raise IsolationError(f"unsafe generated run directory: {run_dir}")
    base_dir = run_dir / "base"
    rag_dir = run_dir / "rag"
    base_dir.mkdir()
    rag_dir.mkdir()
    (run_dir / _OWNER_FILE).write_text(
        json.dumps({"schema": 1, "run_dir": str(run_dir)}, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ProbePlan(
        run_dir=run_dir,
        base_dir=base_dir,
        rag_dir=rag_dir,
        checkpoint_dir=base_dir,
        sqlite_path=base_dir / "kol_scan.db",
        environment={
            "OMNIGRAPH_LOAD_ENV": "0",
            "OMNIGRAPH_BASE_DIR": str(base_dir),
            "RAG_WORKING_DIR": str(rag_dir),
            "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(base_dir),
            "KOL_SCAN_DB_PATH": str(base_dir / "kol_scan.db"),
            "OMNIGRAPH_VECTOR_STORAGE": "nanovectordb",
            "OMNIGRAPH_LLM_PROVIDER": "hermes",
            "OMNIGRAPH_HERMES_BIN": str(hermes_bin),
            "OMNIGRAPH_LOCAL_EMBED": "1",
            "OMNIGRAPH_LOCAL_EMBED_URL": embedding_url,
            "ENRICHMENT_ENABLED": "0",
        },
    )


def _write_synthetic_cache(plan: ProbePlan) -> str:
    """Create the shortest cache-path input that bypasses fetch, images, and classify."""
    article_hash = hashlib.md5(_URL.encode()).hexdigest()[:10]
    article_dir = plan.base_dir / "images" / article_hash
    article_dir.mkdir(parents=True, exist_ok=False)
    body = (
        f"# VitaX single article probe\n\nURL: {_URL}\n\n"
        f"{_MARKER} describes the relationship between VitaX, LightRAG, and Hermes. "
        "VitaX stores a short synthetic text so the isolated graph can extract entities "
        "and relationships without any fetch, image, category, translation, or vision work. "
    )
    # ``ingest_article`` rejects bodies below 500 characters even on the cache path.
    body += "The probe text is intentionally repetitive only to satisfy that production guard. " * 7
    (article_dir / "final_content.md").write_text(body, encoding="utf-8")
    (article_dir / "metadata.json").write_text(
        json.dumps({"title": "VitaX single article probe", "images": []}), encoding="utf-8"
    )
    return body


@contextmanager
def _runtime_environment(plan: ProbePlan) -> Iterator[None]:
    """Replace inherited environment before any runtime import; never read ~/.hermes/.env."""
    original = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update({"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **plan.environment})
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _reader_command(plan: ProbePlan) -> list[str]:
    return [
        sys.executable, str(Path(__file__).resolve()), "--verify",
        "--run-dir", str(plan.run_dir), "--hermes-bin", plan.environment["OMNIGRAPH_HERMES_BIN"],
        "--embedding-url", plan.environment["OMNIGRAPH_LOCAL_EMBED_URL"],
    ]


def _reopen_reader(plan: ProbePlan, label: str) -> dict[str, Any]:
    result = subprocess.run(
        _reader_command(plan),
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **plan.environment},
        text=True,
        capture_output=True,
        timeout=_VERIFY_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError("FRESH_READER_FAILED", plan.run_dir / "fresh-reader.log")
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("FRESH_READER_INVALID_RECEIPT", plan.run_dir / "fresh-reader.log") from exc
    if evidence.get("status") != "PASS":
        raise ProbeError("FRESH_READER_REJECTED_EVIDENCE", plan.run_dir / "fresh-reader.log")
    return evidence


async def _execute_runtime_async(plan: ProbePlan, *, reopen_reader: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Run the real cache path twice and rely on fresh-process evidence, never logs."""
    _write_synthetic_cache(plan)
    candidate_root = _candidate_root()
    import ingest_wechat  # Delayed: config.py reads paths and load_env at import time.
    _assert_candidate_imports(candidate_root)

    counts = {"entity_canonicalization": 0, "lightrag_extraction": 0}
    budget_refused = False
    observed_ainserts: list[bool] = []
    real_factory = ingest_wechat.get_llm_func

    def budgeted_factory():
        real_callback = real_factory()

        async def budgeted_callback(prompt: str, *args: Any, **kwargs: Any) -> str:
            nonlocal budget_refused
            bucket = "entity_canonicalization" if prompt.startswith("Extract a comma-separated") else "lightrag_extraction"
            if sum(counts.values()) >= _MAX_HERMES_COMPLETIONS:
                budget_refused = True
                raise RuntimeError(f"Hermes completion budget exceeded ({_MAX_HERMES_COMPLETIONS})")
            counts[bucket] += 1
            return await real_callback(prompt, *args, **kwargs)

        return budgeted_callback

    ingest_wechat.get_llm_func = budgeted_factory

    async def ingest_and_finalize(rag: Any) -> None:
        real_ainsert = rag.ainsert

        async def observed_ainsert(*args: Any, **kwargs: Any) -> Any:
            try:
                result = await real_ainsert(*args, **kwargs)
            except BaseException:
                observed_ainserts.append(False)
                raise
            observed_ainserts.append(True)
            return result

        rag.ainsert = observed_ainsert
        try:
            await ingest_wechat.ingest_article(_URL, source="wechat", rag=rag)
        finally:
            await rag.finalize_storages()

    try:
        rag = await ingest_wechat.get_rag(flush=True)
        await ingest_and_finalize(rag)
        first = reopen_reader("first")

        rerun_rag = await ingest_wechat.get_rag(flush=True)
        await ingest_and_finalize(rerun_rag)
        rerun = reopen_reader("rerun")
    finally:
        ingest_wechat.get_llm_func = real_factory
    if budget_refused:
        raise ProbeError("HERMES_COMPLETION_BUDGET_REJECTED", plan.run_dir / "runtime.log")
    if observed_ainserts != [True, True]:
        raise ProbeError("RAG_AINSERT_NOT_CONFIRMED", plan.run_dir / "runtime.log")
    if rerun["graph_entities"] != first["graph_entities"] or rerun["graph_relationships"] != first["graph_relationships"]:
        raise RuntimeError("rerun changed graph cardinality; deduplication not proven")
    return {"first": first, "rerun": rerun, "request_budget": counts}


def _execute_runtime(plan: ProbePlan, *, reopen_reader: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    loaded = sorted(name for name in sys.modules if name in {"config", "ingest_wechat", "image_pipeline", "lib"} or name.startswith("lib."))
    if loaded:
        raise ProbeError("RUNTIME_MODULES_ALREADY_IMPORTED", plan.run_dir / "runtime.log")
    with _runtime_environment(plan):
        log_path = plan.run_dir / "runtime.log"
        with log_path.open("a", encoding="utf-8") as log, redirect_stdout(log):
            try:
                return asyncio.run(_execute_runtime_async(plan, reopen_reader=reopen_reader))
            except BaseException:
                traceback.print_exc(file=log)
                raise


def run_probe(plan: ProbePlan, *, execute: bool, reopen_reader: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Produce an offline receipt, or invoke the separately authorized real exercise."""
    receipt: dict[str, Any] = {
        "run_dir": str(plan.run_dir),
        "environment": plan.environment,
        "storage_backend": "nanovectordb",
        "request_budget_limit": _MAX_HERMES_COMPLETIONS,
    }
    if not execute:
        receipt.update({
            "status": "OFFLINE_ONLY",
            "network_or_model_execution": "not attempted",
            "request_budget": {"entity_canonicalization": 0, "lightrag_extraction": 0},
        })
    else:
        try:
            details = _execute_runtime(plan, reopen_reader=reopen_reader or (lambda label: _reopen_reader(plan, label)))
            receipt.update({"status": "READY_FOR_REVIEW", "network_or_model_execution": "attempted", **details})
        except ProbeError as exc:
            receipt.update({
                "status": "FAILED",
                "network_or_model_execution": "attempted",
                "error": {"type": type(exc).__name__, "code": exc.code, "log_path": str(exc.log_path)},
            })
        except Exception as exc:
            log_path = plan.run_dir / "runtime.log"
            receipt.update({
                "status": "FAILED",
                "network_or_model_execution": "attempted",
                "error": {"type": type(exc).__name__, "code": "UNEXPECTED_RUNTIME_FAILURE", "log_path": str(log_path)},
            })
    (plan.run_dir / "VITAX_SINGLE_ARTICLE_PROBE.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _graph_source_associations(rag_dir: Path, chunk_ids: set[str]) -> tuple[int, int]:
    graph_path = rag_dir / "graph_chunk_entity_relation.graphml"
    if not graph_path.is_file():
        raise RuntimeError("GraphML storage missing after finalize")
    root = etree.parse(graph_path).getroot()
    key_names = {
        key.get("id"): key.get("attr.name")
        for key in root.iter()
        if key.tag.endswith("key")
    }
    def has_target_source(item: Any) -> bool:
        values = [data.text or "" for data in item if data.tag.endswith("data") and key_names.get(data.get("key")) == "source_id"]
        return any(chunk_id in value for value in values for chunk_id in chunk_ids)
    return (
        sum(1 for item in root.iter() if item.tag.endswith("node") and has_target_source(item)),
        sum(1 for item in root.iter() if item.tag.endswith("edge") and has_target_source(item)),
    )


async def _verify_async(plan: ProbePlan) -> dict[str, Any]:
    article_hash = hashlib.md5(_URL.encode()).hexdigest()[:10]
    doc_id = f"wechat_{article_hash}"
    candidate_root = _candidate_root()
    import ingest_wechat
    from lightrag import QueryParam
    _assert_candidate_imports(candidate_root)

    async def forbidden_llm(*_args: Any, **_kwargs: Any) -> str:
        raise ProbeError("FRESH_READER_LLM_FORBIDDEN", plan.run_dir / "fresh-reader.log")

    original_factory = ingest_wechat.get_llm_func
    ingest_wechat.get_llm_func = lambda: forbidden_llm
    try:
        rag = await ingest_wechat.get_rag(flush=True)
        docs = await rag.aget_docs_by_ids([doc_id])
        doc = docs.get(doc_id) if isinstance(docs, dict) else None
        status_value = getattr(doc, "status", None)
        error_message = getattr(doc, "error_msg", None)
        if isinstance(doc, dict):
            status_value = doc.get("status")
            error_message = doc.get("error_msg")
        processed = ingest_wechat._status_is_processed(status_value)
        error_free = not error_message
        query_param = QueryParam(
            mode="local", only_need_context=True,
            hl_keywords=["VitaX", "LightRAG", "Hermes"],
            ll_keywords=["VitaX", "LightRAG", "Hermes"],
        )
        context = await rag.aquery(_MARKER, param=query_param)
        context_marker = _MARKER in str(context)
    finally:
        ingest_wechat.get_llm_func = original_factory
    degraded = (plan.base_dir / "checkpoints" / hashlib.sha256(_URL.encode()).hexdigest()[:16] / "degraded.json").exists()
    full_docs = json.loads((plan.rag_dir / "kv_store_full_docs.json").read_text(encoding="utf-8"))
    full_doc = full_docs.get(doc_id, {})
    body_marker = _MARKER in json.dumps(full_doc, ensure_ascii=False)
    chunks = json.loads((plan.rag_dir / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    chunk_ids = {chunk_id for chunk_id, chunk in chunks.items() if isinstance(chunk, dict) and chunk.get("full_doc_id") == doc_id}
    entities, relationships = _graph_source_associations(plan.rag_dir, chunk_ids)
    checks = processed and error_free and not degraded and body_marker and bool(chunk_ids) and entities > 0 and relationships > 0 and context_marker
    return {
        "status": "PASS" if checks else "FAIL", "processed": processed, "error_free": error_free,
        "degraded": degraded, "target_chunk_count": len(chunk_ids), "graph_entities": entities,
        "graph_relationships": relationships, "body_marker": body_marker, "context_marker": context_marker,
        "fresh_reader_llm_calls": 0,
    }


def _plan_from_run_dir(run_dir: Path, hermes_bin: Path, embedding_url: str) -> ProbePlan:
    if ".." in run_dir.parts or run_dir.is_symlink() or _symlink_ancestor(run_dir) is not None:
        raise IsolationError("run directory has a symlink or traversal")
    run_dir = run_dir.resolve(strict=True)
    owner_path = run_dir / _OWNER_FILE
    if not run_dir.name.startswith("vitax-single-article-") or owner_path.is_symlink() or not owner_path.is_file():
        raise IsolationError("run directory is not runner-owned")
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IsolationError("run directory owner marker is invalid") from exc
    if owner != {"schema": 1, "run_dir": str(run_dir)}:
        raise IsolationError("run directory owner marker does not match")
    base_dir, rag_dir = run_dir / "base", run_dir / "rag"
    if base_dir.is_symlink() or rag_dir.is_symlink() or not base_dir.is_dir() or not rag_dir.is_dir():
        raise IsolationError("run directory does not have the required isolated paths")
    return ProbePlan(run_dir, base_dir, rag_dir, base_dir, base_dir / "kol_scan.db", {
        "OMNIGRAPH_LOAD_ENV": "0", "OMNIGRAPH_BASE_DIR": str(base_dir), "RAG_WORKING_DIR": str(rag_dir),
        "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(base_dir), "KOL_SCAN_DB_PATH": str(base_dir / "kol_scan.db"),
        "OMNIGRAPH_VECTOR_STORAGE": "nanovectordb", "OMNIGRAPH_LLM_PROVIDER": "hermes",
        "OMNIGRAPH_HERMES_BIN": str(hermes_bin), "OMNIGRAPH_LOCAL_EMBED": "1",
        "OMNIGRAPH_LOCAL_EMBED_URL": _validated_loopback_embedding_url(embedding_url), "ENRICHMENT_ENABLED": "0",
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed VitaX single article probe.")
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--hermes-bin", type=Path, required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.verify:
        if args.parent or args.execute or not args.run_dir:
            parser.error("--verify requires only --run-dir and --hermes-bin")
        try:
            plan = _plan_from_run_dir(args.run_dir, args.hermes_bin, args.embedding_url)
            with _runtime_environment(plan), (plan.run_dir / "fresh-reader.log").open("a", encoding="utf-8") as log, redirect_stdout(log):
                evidence = asyncio.run(_verify_async(plan))
        except (IsolationError, ProbeError) as exc:
            print(json.dumps({"status": "FAIL", "error": {"type": type(exc).__name__, "code": getattr(exc, "code", "INVALID_RUN_DIRECTORY")}}, sort_keys=True))
            return 21
        print(json.dumps(evidence, sort_keys=True))
        return 0 if evidence["status"] == "PASS" else 21
    if args.run_dir or not args.parent:
        parser.error("--parent is required unless --verify is used")
    plan = create_probe_plan(parent_dir=args.parent, hermes_bin=args.hermes_bin, embedding_url=args.embedding_url)
    receipt = run_probe(plan, execute=args.execute)
    print(plan.run_dir / "VITAX_SINGLE_ARTICLE_PROBE.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
