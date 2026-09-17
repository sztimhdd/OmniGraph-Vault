"""Offline validation for a versioned publication artifact manifest.

This module verifies files that an external release process has already
produced.  It neither creates snapshots nor opens storage backends.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    """Raised when a publication artifact manifest is unsafe or incomplete."""


_PRIVATE_COMPONENTS = frozenset({"sqlite", "vector", "graph_kv"})
_PUBLIC_COMPONENTS = frozenset({"wiki", "images", "public_content"})


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"{label} must be an object")
    return value


def _release_version(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{label} must be a non-empty string")
    return value


def _component_set(section: Mapping[str, Any], required: frozenset[str], label: str) -> None:
    missing = required - set(section)
    if missing:
        raise ManifestError(f"missing required {label} component: {sorted(missing)[0]}")
    unexpected = set(section) - required
    if unexpected:
        raise ManifestError(f"unexpected {label} component: {sorted(unexpected)[0]}")


def _safe_file(root: Path, relative_path: Any, label: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ManifestError(f"{label}.path must be a non-empty string")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestError(f"{label}.path must stay within manifest root")
    candidate = root / relative
    prefix = root
    for part in relative.parts:
        prefix = prefix / part
        if prefix.is_symlink():
            raise ManifestError(f"{label}.path must not contain symlinks")
    if not candidate.is_file():
        raise ManifestError(f"{label}.path must name a regular file")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ManifestError(f"{label}.path must stay within manifest root") from error
    return resolved


def _validate_component(
    root: Path, release_version: str, label: str, component: Any
) -> Path:
    data = _mapping(component, label)
    component_version = _release_version(data.get("release_version"), f"{label}.release_version")
    if component_version != release_version:
        raise ManifestError(f"{label}.release_version does not match manifest release_version")
    expected_hash = data.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ManifestError(f"{label}.sha256 must be a SHA-256 hex digest")
    try:
        int(expected_hash, 16)
    except ValueError as error:
        raise ManifestError(f"{label}.sha256 must be a SHA-256 hex digest") from error
    path = _safe_file(root, data.get("path"), label)
    with path.open("rb") as artifact:
        actual_hash = hashlib.file_digest(artifact, "sha256").hexdigest()
    if actual_hash != expected_hash:
        raise ManifestError(f"{label}.sha256 mismatch")
    return path


def validate_manifest(manifest_path: str | Path, root: str | Path) -> dict[str, Any]:
    """Return a validated manifest or raise ``ManifestError``.

    ``root`` bounds every declared artifact.  The manifest separates private
    snapshot inputs (SQLite, vector, graph/KV) from the public read collection
    (Wiki, images, public content), and binds all six to one release version.
    """
    root_path = Path(root).resolve()
    source_path = Path(manifest_path)
    if not source_path.is_file():
        raise ManifestError("manifest_path must name a regular file")
    try:
        source_path.resolve().relative_to(root_path)
    except ValueError as error:
        raise ManifestError("manifest_path must stay within manifest root") from error
    try:
        manifest = _mapping(json.loads(source_path.read_text(encoding="utf-8")), "manifest")
    except json.JSONDecodeError as error:
        raise ManifestError("manifest must contain valid JSON") from error
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ManifestError("manifest.schema_version must be 1")
    release_version = _release_version(manifest.get("release_version"), "manifest.release_version")
    private = _mapping(manifest.get("private_backups"), "manifest.private_backups")
    public = _mapping(manifest.get("public_read_collection"), "manifest.public_read_collection")
    _component_set(private, _PRIVATE_COMPONENTS, "private backup")
    _component_set(public, _PUBLIC_COMPONENTS, "public read collection")

    resolved_paths = set()
    for section_name, section in (("private_backups", private), ("public_read_collection", public)):
        for component_name, component in section.items():
            path = _validate_component(
                root_path, release_version, f"{section_name}.{component_name}", component
            )
            if path in resolved_paths:
                raise ManifestError("manifest components must not share an artifact path")
            resolved_paths.add(path)
    return dict(manifest)
