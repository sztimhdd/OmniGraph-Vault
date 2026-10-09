"""Integration tests for the local VitaX release builder.

The builder shells out to the real prereender path: it calls the real
``vitax.knowledge.build`` and the real ``vitax-site`` prerender. The ``npm``
step is stubbed with a shell shim that writes a minimal built shell, so no
Vite build runs per test.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import scripts.build_vitax_release as builder
from scripts.build_vitax_release import ReleaseError, build_release
from vitax.api import create_app


RELEASE_ID = "release-2026-10-01"
PUBLISHED_AT = "2026-10-01T12:00:00Z"
PRIVATE_SENTINEL = "PRIVATE_SENTINEL_RELEASE"

# Must keep the exact empty root element and a <title> the prerender rewrites.
SHELL = (
    '<!doctype html><html><head><meta charset="utf-8">'
    "<title>VitaX reader</title></head>"
    '<body><div id="root"></div></body></html>'
)


def _projection(knowledge_extra: list[dict[str, object]] | None = None) -> dict[str, object]:
    """A public projection that also carries one private record per collection."""
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "published_at": PUBLISHED_AT,
        "documents": [
            {
                "doc_id": "doc-a",
                "revision_id": "rev-a",
                "title": "First source",
                "source_url": "https://example.test/a",
                "source_published_at": None,
                "fetched_at": "2026-10-01T11:00:00Z",
                "visibility": "public",
            },
            {
                "doc_id": "doc-private",
                "revision_id": "rev-private",
                "title": f"{PRIVATE_SENTINEL} document",
                "source_url": "https://example.test/private",
                "visibility": "private",
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev-a",
                "revision_id": "rev-a",
                "locator": "paragraph:2",
                "quote": "Alpha source quote",
                "visibility": "public",
            },
            {
                "evidence_id": "ev-private",
                "revision_id": "rev-a",
                "locator": "paragraph:9",
                "quote": f"{PRIVATE_SENTINEL} quote",
                "visibility": "private",
            },
        ],
        "knowledge": [
            {
                "knowledge_id": "article-a",
                "kind": "article",
                "title": "Alpha interpretation",
                "body": "Alpha interpretation body about Chinese AI research.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
            {
                "knowledge_id": "wiki-ai",
                "kind": "wiki",
                "title": "AI Wiki",
                "body": "A wiki built from Alpha evidence.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
            {
                "knowledge_id": "article-private",
                "kind": "article",
                "title": f"{PRIVATE_SENTINEL} knowledge",
                "body": f"{PRIVATE_SENTINEL} body",
                "evidence_ids": ["ev-a"],
                "visibility": "private",
            },
            *(knowledge_extra or []),
        ],
        "entities": [
            {"entity_id": "entity-alpha", "name": "Alpha", "visibility": "public"},
            {"entity_id": "entity-private", "name": f"{PRIVATE_SENTINEL} entity", "visibility": "private"},
        ],
        "relations": [
            {
                "relation_id": "rel-alpha",
                "source_id": "entity-alpha",
                "target_id": "entity-alpha",
                "relation_type": "supports",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
            {
                "relation_id": "rel-private",
                "source_id": "entity-alpha",
                "target_id": "entity-alpha",
                "relation_type": f"{PRIVATE_SENTINEL} relation",
                "evidence_ids": ["ev-a"],
                "visibility": "private",
            },
        ],
    }


def _write_projection(tmp_path: Path, projection: dict[str, object]) -> Path:
    source = tmp_path / "projection.json"
    source.write_text(json.dumps(projection), encoding="utf-8")
    return source


def _stub_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, exit_code: int = 0) -> None:
    """Put a fake `npm` first on PATH that writes the minimal built shell."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "npm"
    script.write_text(
        "#!/bin/sh\n"
        f"if [ {exit_code} -ne 0 ]; then echo 'stubbed npm failure' >&2; exit {exit_code}; fi\n"
        'out=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        '    --outDir) out="$2"; shift 2;;\n'
        "    *) shift;;\n"
        "  esac\n"
        "done\n"
        'mkdir -p "$out/assets"\n'
        f"printf '%s' '{SHELL}' > \"$out/index.html\"\n"
        "printf '%s' 'console.log(\"reader\");' > \"$out/assets/app.js\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")


def test_build_release_writes_a_public_only_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks if the package leaks private records, misses a hash, or serves a wrong status."""
    source = _write_projection(tmp_path, _projection())
    _stub_npm(tmp_path, monkeypatch)
    target = tmp_path / "release"

    manifest = build_release(source, target)

    assert sorted(path.name for path in target.iterdir()) == ["images", "manifest.json", "public.sqlite", "site"]
    assert list((target / "images").iterdir()) == []
    assert manifest["schema_version"] == 1
    assert manifest["release_id"] == RELEASE_ID
    assert manifest["published_at"] == PUBLISHED_AT
    assert manifest["images"] == []
    assert datetime.fromisoformat(str(manifest["generated_at"]).replace("Z", "+00:00")).tzinfo is not None
    assert "selected_images" not in json.dumps(manifest)
    assert str(source) not in json.dumps(manifest)

    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths)
    assert paths[0] == "public.sqlite"
    assert any(path.startswith("site/") for path in paths)
    assert not any("manifest" in path for path in paths)
    for entry in manifest["files"]:
        assert entry["sha256"] == hashlib.sha256((target / entry["path"]).read_bytes()).hexdigest()

    for path in target.rglob("*"):
        if path.is_file():
            assert PRIVATE_SENTINEL.encode() not in path.read_bytes()

    with TestClient(create_app(target / "public.sqlite", site_dir=target / "site")) as client:
        index = client.get("/")
        article = client.get("/article/article-a/")
        wiki = client.get("/wiki/wiki-ai/")
        unknown_detail = client.get("/article/does-not-exist/")
        unknown_api = client.get("/api/knowledge/does-not-exist")
        missing_image = client.get("/images/missing.png")

    assert index.status_code == 200
    assert "Alpha interpretation" in index.text
    assert article.status_code == 200
    assert "Alpha interpretation body about Chinese AI research." in article.text
    assert wiki.status_code == 200
    assert "A wiki built from Alpha evidence." in wiki.text
    assert unknown_detail.status_code == 404
    assert unknown_api.status_code == 404
    assert missing_image.status_code == 404
    assert PRIVATE_SENTINEL not in index.text + article.text + wiki.text


def test_build_release_resolves_a_relative_output_in_the_calling_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if a relative CLI target is resolved against the vitax-site cwd instead."""
    source = _write_projection(tmp_path, _projection())
    _stub_npm(tmp_path, monkeypatch)
    seen: list[Path] = []
    real_build_site = builder._build_site

    def record(site_dir: Path, env: dict[str, str]) -> None:
        seen.append(site_dir)
        real_build_site(site_dir, env)

    monkeypatch.setattr(builder, "_build_site", record)
    monkeypatch.chdir(tmp_path)

    manifest = build_release(source, "release")

    target = tmp_path / "release"
    assert seen == [target / "site"]
    assert seen[0].is_absolute()
    assert (target / "public.sqlite").is_file()
    assert (target / "site" / "index.html").is_file()
    assert [entry["path"] for entry in manifest["files"]][0] == "public.sqlite"
    assert all(not Path(entry["path"]).is_absolute() for entry in manifest["files"])
    assert not (builder.SITE_SOURCE / "release").exists()


def test_build_release_refuses_existing_targets_and_preserves_their_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if a build can overwrite a directory, file, or symlink target."""
    source = _write_projection(tmp_path, _projection())
    _stub_npm(tmp_path, monkeypatch)

    directory = tmp_path / "release"
    directory.mkdir()
    (directory / "keep.txt").write_bytes(b"KEEP_BYTES")
    before = {path.name: path.read_bytes() for path in directory.iterdir()}

    with pytest.raises(ReleaseError, match="already exists"):
        build_release(source, directory)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before

    plain_file = tmp_path / "file-release"
    plain_file.write_bytes(b"FILE_BYTES")
    with pytest.raises(ReleaseError, match="already exists"):
        build_release(source, plain_file)
    assert plain_file.read_bytes() == b"FILE_BYTES"

    link = tmp_path / "link-release"
    link.symlink_to(tmp_path / "nowhere")
    with pytest.raises(ReleaseError, match="already exists"):
        build_release(source, link)
    assert link.is_symlink()


@pytest.mark.parametrize("failure", ["site", "prerender"])
def test_failed_build_leaves_no_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Breaks if a failed build leaves a half-written release behind."""
    extra = (
        [
            {
                "knowledge_id": "bad/id",
                "kind": "article",
                "title": "Unusable identifier",
                "body": "Cannot be one directory name.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            }
        ]
        if failure == "prerender"
        else []
    )
    source = _write_projection(tmp_path, _projection(extra))
    _stub_npm(tmp_path, monkeypatch, exit_code=1 if failure == "site" else 0)
    target = tmp_path / "release"

    with pytest.raises(ReleaseError):
        build_release(source, target)

    assert not target.exists()


def test_prebuilt_site_is_copied_without_building_or_prerendering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A trusted prebuilt SPA is copied as-is; npm and prerender are not run."""
    source = _write_projection(tmp_path, _projection())
    prebuilt = tmp_path / "spa"
    (prebuilt / "assets").mkdir(parents=True)
    (prebuilt / "index.html").write_text(SHELL, encoding="utf-8")
    (prebuilt / "assets/app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(builder, "_build_site", lambda *a, **k: pytest.fail("prebuilt site must not run npm"))
    monkeypatch.setattr(builder, "_prerender", lambda *a, **k: pytest.fail("prebuilt site must not prerender"))
    target = tmp_path / "release"

    manifest = build_release(source, target, site_dir=prebuilt)

    assert (target / "site/assets/app.js").read_text(encoding="utf-8") == "console.log(1)"
    assert manifest["release_id"] == RELEASE_ID
    assert any(entry["path"] == "site/index.html" for entry in manifest["files"])
    with TestClient(create_app(target / "public.sqlite", site_dir=target / "site")) as client:
        assert client.get("/").status_code == 200


def test_prebuilt_site_env_var_is_honoured_and_missing_one_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The env seam selects a prebuilt site and refuses one with no index.html."""
    source = _write_projection(tmp_path, _projection())
    prebuilt = tmp_path / "spa"; prebuilt.mkdir()
    (prebuilt / "index.html").write_text(SHELL, encoding="utf-8")
    monkeypatch.setenv("VITAX_PREBUILT_SITE", str(prebuilt))
    monkeypatch.setattr(builder, "_build_site", lambda *a, **k: pytest.fail("prebuilt site must not run npm"))
    monkeypatch.setattr(builder, "_prerender", lambda *a, **k: pytest.fail("prebuilt site must not prerender"))

    target = tmp_path / "release"
    build_release(source, target)
    assert (target / "site/index.html").is_file()

    monkeypatch.setenv("VITAX_PREBUILT_SITE", str(tmp_path / "empty"))
    with pytest.raises(ReleaseError, match="no index.html"):
        build_release(source, tmp_path / "release2")
    assert not (tmp_path / "release2").exists()
