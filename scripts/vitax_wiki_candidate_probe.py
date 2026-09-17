#!/usr/bin/env python3
"""Persist one isolated Wiki candidate from an accepted synthetic article run.

The probe reads only the accepted run's persisted LightRAG stores and entity
buffer.  It invokes the existing W3 adapter, assembler, and shared engine; it
does not import ingestion, call a model, or write to the accepted run.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


class ProbeError(RuntimeError):
    """A fail-closed source or output boundary violation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_OWNER_FILE = ".vitax-single-article-owned.json"
_URL_LINE = re.compile(r"^URL:\s*(\S+)\s*$", re.MULTILINE)


def _regular_file_hashes(root: Path) -> dict[str, str]:
    """Return a stable snapshot of every regular source file below *root*."""
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProbeError("SOURCE_SYMLINK")
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _repository_wiki(root: Path | None) -> Path:
    wiki = root if root is not None else Path(__file__).resolve().parents[1] / "kb" / "wiki"
    if not wiki.is_dir() or wiki.is_symlink():
        raise ProbeError("CANDIDATE_REPO_WIKI_MISSING")
    return wiki


def _candidate_error_book(path: Path):
    """Return an Error Book callback constrained to the candidate directory."""
    def record(failure: dict) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(failure, sort_keys=True) + "\n")
    return record


def _validated_accepted_run(accepted_run: Path, output_parent: Path) -> tuple[Path, Path]:
    if accepted_run.is_symlink() or output_parent.is_symlink():
        raise ProbeError("SOURCE_OR_OUTPUT_SYMLINK")
    try:
        accepted = accepted_run.resolve(strict=True)
        parent = output_parent.resolve(strict=True)
    except OSError as exc:
        raise ProbeError("SOURCE_OR_OUTPUT_MISSING") from exc
    if not accepted.is_dir() or not parent.is_dir() or accepted.parent != parent:
        raise ProbeError("OUTPUT_PARENT_MUST_BE_ACCEPTED_RUN_SIBLING")
    if not accepted.name.startswith("vitax-single-article-"):
        raise ProbeError("UNOWNED_ACCEPTED_RUN")
    owner_path = accepted / _OWNER_FILE
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError("INVALID_ACCEPTED_RUN_OWNER") from exc
    if owner != {"schema": 1, "run_dir": str(accepted)}:
        raise ProbeError("INVALID_ACCEPTED_RUN_OWNER")
    return accepted, parent


def _bounded_article_text(content: str) -> tuple[str, str]:
    """Derive display-safe title and short context from persisted source text."""
    lines = [line.strip() for line in content.splitlines()]
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    body = " ".join(
        line for line in lines
        if line and not line.startswith("#") and not line.startswith("URL:")
    )
    if not title or not body:
        raise ProbeError("SOURCE_CONTENT_INCOMPLETE")
    return title[:160], body[:480]


def _assert_no_runtime_modules() -> None:
    blocked = {"config", "ingest_wechat", "image_pipeline"}
    if any(name in sys.modules for name in blocked):
        raise ProbeError("RUNTIME_MODULE_PRELOADED")


def _accepted_source(accepted_run: Path) -> dict[str, str]:
    """Read the one processed source URL and its matching buffered entity."""
    rag = accepted_run / "rag"
    try:
        docs = json.loads((rag / "kv_store_full_docs.json").read_text(encoding="utf-8"))
        statuses = json.loads((rag / "kv_store_doc_status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError("ACCEPTED_STORES_UNREADABLE") from exc
    processed = sorted(
        doc_id for doc_id, value in statuses.items()
        if isinstance(value, dict) and value.get("status") == "processed" and doc_id in docs
    )
    if len(processed) != 1:
        raise ProbeError("SOURCE_NOT_PROCESSED")
    document = docs[processed[0]]
    content = document.get("content") if isinstance(document, dict) else None
    match = _URL_LINE.search(content) if isinstance(content, str) else None
    if match is None:
        raise ProbeError("SOURCE_URL_MISSING")

    title, summary = _bounded_article_text(content)
    _assert_no_runtime_modules()
    from kb.wiki_articles import canonical_article_ref
    from kb.wiki_compiler.adapters import w3
    _assert_no_runtime_modules()

    ref = canonical_article_ref(match.group(1))
    buffer_path = accepted_run / "base" / "entity_buffer" / f"{ref}_entities.json"
    try:
        buffer = json.loads(buffer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError("ENTITY_BUFFER_MISSING") from exc
    names = [
        item.get("name", "") if isinstance(item, dict) else str(item)
        for item in buffer.get("raw_entities", [])
    ]
    slugs = sorted({w3._slugify(name) for name in names if w3._slugify(name)})
    if not slugs:
        raise ProbeError("ENTITY_BUFFER_EMPTY")
    return {
        "processed_doc_id": processed[0],
        "source_url": match.group(1),
        "source_ref": ref,
        "slug": slugs[0],
        "title": title,
        "summary": summary,
    }


def create_wiki_candidate(
    *, accepted_run: Path, output_parent: Path, today: str, repository_wiki_root: Path | None = None
) -> dict[str, Any]:
    """Apply one source-linked page in a fresh, isolated candidate Wiki root."""
    accepted, parent = _validated_accepted_run(accepted_run, output_parent)
    source_hashes = _regular_file_hashes(accepted)
    repo_wiki = _repository_wiki(repository_wiki_root)
    repo_wiki_hashes = _regular_file_hashes(repo_wiki)
    source = _accepted_source(accepted)
    try:
        candidate_date = date.fromisoformat(today)
    except ValueError as exc:
        raise ProbeError("INVALID_CANDIDATE_DATE") from exc

    candidate = Path(tempfile.mkdtemp(prefix="vitax-wiki-candidate-", dir=parent)).resolve()
    if candidate.parent != parent or candidate.is_symlink():
        raise ProbeError("UNSAFE_CANDIDATE_DIRECTORY")
    wiki_root = candidate / "wiki"
    # The W3 boundary adapter resolves an engine-ready relative target only
    # when the bare wiki root already has its entities directory.
    (wiki_root / "entities").mkdir(parents=True)
    record = {
        "source": "synthetic",
        "ref": source["source_ref"],
        "title": source["title"],
        "text": source["summary"],
    }
    from kb.wiki_compiler.adapters import w3
    from kb.wiki_compiler.engine import apply_patch
    _assert_no_runtime_modules()

    pack = w3.build_w3_pack_from_records(
        source["slug"], [record], wiki_root, trigger="vitax_accepted_synthetic",
    )
    # W3's record adapter intentionally emits a generic frequency statement.
    # This bounded probe retains its evidence/identity contract but substitutes
    # its sole context block with text deterministically read from the accepted
    # synthetic source; it never requests an LLM summary.
    pack = replace(pack, context_blocks=(source["summary"],))
    patch = w3.propose_w3_patch(pack, wiki_root=wiki_root, today=candidate_date)
    result = apply_patch(
        w3.engine_ready_patch(patch),
        w3.engine_wiki_root(wiki_root),
        error_book=_candidate_error_book(candidate / "compiler_failures.jsonl"),
    )
    if _regular_file_hashes(accepted) != source_hashes:
        raise ProbeError("SOURCE_INPUT_MUTATED")
    if _regular_file_hashes(repo_wiki) != repo_wiki_hashes:
        raise ProbeError("REPOSITORY_WIKI_MUTATED")
    artifact_hashes = _regular_file_hashes(candidate)
    receipt = {
        "status": result["status"].upper(),
        "candidate_dir": str(candidate),
        "wiki_page": str(candidate / "wiki" / "entities" / f"{source['slug']}.md"),
        "patch_id": result["patch_id"],
        "source": "synthetic",
        "processed_doc_id": source["processed_doc_id"],
        "source_url": source["source_url"],
        "source_ref": source["source_ref"],
        "source_input_hashes": source_hashes,
        "repository_wiki_hashes": repo_wiki_hashes,
        "artifact_hashes": artifact_hashes,
        "network_or_model_execution": "not attempted",
    }
    (candidate / "VITAX_WIKI_CANDIDATE_PROBE.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if result["status"] not in {"applied", "suggestion"}:
        raise ProbeError("WIKI_CANDIDATE_NOT_APPLIED")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist one isolated VitaX Wiki candidate.")
    parser.add_argument("--accepted-run", type=Path, required=True)
    parser.add_argument("--output-parent", type=Path, required=True)
    parser.add_argument("--repository-wiki-root", type=Path)
    parser.add_argument("--today", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required to write a candidate")
    receipt = create_wiki_candidate(
        accepted_run=args.accepted_run,
        output_parent=args.output_parent,
        today=args.today,
        repository_wiki_root=args.repository_wiki_root,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
