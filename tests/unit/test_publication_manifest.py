"""Offline contract tests for a publication release manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lib.publication_manifest import ManifestError, validate_manifest


RELEASE = "2026-09-09.1"


def _write(root: Path, relative_path: str, contents: bytes) -> dict[str, str]:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "release_version": RELEASE,
    }


def _manifest(root: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "release_version": RELEASE,
        "private_backups": {
            "sqlite": _write(root, "private/kol_scan.db", b"sqlite snapshot"),
            "vector": _write(root, "private/vectors.json", b"vector snapshot"),
            "graph_kv": _write(root, "private/graph-kv.json", b"graph snapshot"),
        },
        "public_read_collection": {
            "wiki": _write(root, "public/wiki.json", b"wiki"),
            "images": _write(root, "public/images.json", b"images"),
            "public_content": _write(root, "public/content.json", b"content"),
        },
    }


def _write_manifest(root: Path, manifest: dict[str, object]) -> Path:
    path = root / "publication-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_validates_a_single_versioned_private_and_public_release(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, _manifest(tmp_path))

    validated = validate_manifest(manifest_path, tmp_path)

    assert validated["release_version"] == RELEASE
    assert set(validated["private_backups"]) == {"sqlite", "vector", "graph_kv"}
    assert set(validated["public_read_collection"]) == {
        "wiki", "images", "public_content"
    }


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda manifest: manifest["private_backups"].pop("vector"),
            "missing required private backup component: vector",
        ),
        (
            lambda manifest: manifest["public_read_collection"]["wiki"].update(
                {"release_version": "other-release"}
            ),
            "does not match manifest release_version",
        ),
        (
            lambda manifest: manifest["private_backups"]["sqlite"].update(
                {"sha256": "0" * 64}
            ),
            "sha256 mismatch",
        ),
        (
            lambda manifest: manifest["public_read_collection"]["images"].update(
                {"path": "../private/kol_scan.db"}
            ),
            "must stay within manifest root",
        ),
    ],
    ids=["missing-component", "mixed-version", "hash-mismatch", "path-traversal"],
)
def test_rejects_invalid_release_contract(
    tmp_path: Path, mutate, reason: str
) -> None:
    manifest = _manifest(tmp_path)
    mutate(manifest)

    with pytest.raises(ManifestError, match=reason):
        validate_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_rejects_boolean_schema_version(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["schema_version"] = True

    with pytest.raises(ManifestError, match="schema_version must be 1"):
        validate_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_rejects_parent_symlink_that_escapes_manifest_root(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    outside = tmp_path.parent / "outside-publication-artifacts"
    outside.mkdir()
    (outside / "images.json").write_bytes(b"outside images")
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    manifest["public_read_collection"]["images"]["path"] = "escape/images.json"

    with pytest.raises(ManifestError, match="must not contain symlinks"):
        validate_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_rejects_in_root_directory_symlink_alias(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "alias").symlink_to(tmp_path / "public", target_is_directory=True)
    manifest["public_read_collection"]["images"]["path"] = "alias/images.json"

    with pytest.raises(ManifestError, match="must not contain symlinks"):
        validate_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_rejects_duplicate_artifact_paths_between_private_and_public_sections(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    content = manifest["public_read_collection"]["public_content"]
    manifest["public_read_collection"]["images"] = dict(content)

    with pytest.raises(ManifestError, match="must not share an artifact path"):
        validate_manifest(_write_manifest(tmp_path, manifest), tmp_path)
