"""Build one local VitaX reader release directory from an accepted public projection.

Usage:
    OMNIGRAPH_LOAD_ENV=0 .venv/bin/python scripts/build_vitax_release.py \
        <accepted-public-projection.json> <new-release-directory>

The output directory is created exclusively and contains exactly
``public.sqlite``, ``site/``, ``images/`` and ``manifest.json``. An existing
target is refused; a failed build removes only the package this run created.

A trusted prebuilt site directory may be supplied instead of building the SPA
with npm and prerendering it; the prebuilt SPA reads the same reader HTTP API,
so the default npm build/prerender path is unchanged when none is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# The script is run as `python scripts/build_vitax_release.py`, so the repository
# root is not on sys.path unless vitax is installed into the environment.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vitax.knowledge import KnowledgeReader, build


SITE_SOURCE = REPO_ROOT / "vitax-site"
PRERENDER = SITE_SOURCE / "scripts" / "prerender.mjs"
MANIFEST_NAME = "manifest.json"

_PRERENDER_CALL = """
import {readFile} from 'node:fs/promises';
import {prerenderRelease} from __MODULE_URL__;
const snapshot = JSON.parse(await readFile(process.env.VITAX_SNAPSHOT, 'utf8'));
const site = process.env.VITAX_SITE;
const {written, skipped} = await prerenderRelease({snapshot, distDir: site, outDir: site});
process.stdout.write(JSON.stringify({written, skipped}));
"""


class ReleaseError(RuntimeError):
    """A local release build failed before producing a complete package."""


def _export_public_dto(database: Path) -> dict[str, object]:
    """Read the new public release with fixed columns and mark every row public."""
    with KnowledgeReader(database) as reader:
        connection = reader.connection
        documents = [
            {"visibility": "public", **dict(row)}
            for row in connection.execute(
                "SELECT revision_id, doc_id, title, source_url, source_published_at, fetched_at "
                "FROM documents ORDER BY revision_id"
            )
        ]
        evidence = [
            {"visibility": "public", **dict(row)}
            for row in connection.execute(
                "SELECT evidence_id, revision_id, locator, quote FROM evidence ORDER BY evidence_id"
            )
        ]
        knowledge = [
            {
                "visibility": "public",
                **dict(row),
                "evidence_ids": [
                    value["evidence_id"]
                    for value in connection.execute(
                        "SELECT evidence_id FROM knowledge_evidence WHERE knowledge_id = ? ORDER BY position",
                        (row["knowledge_id"],),
                    )
                ],
            }
            for row in connection.execute(
                "SELECT knowledge_id, kind, title, body FROM knowledge ORDER BY knowledge_id"
            )
        ]
        entities = [
            {"visibility": "public", **dict(row)}
            for row in connection.execute("SELECT entity_id, name FROM entities ORDER BY entity_id")
        ]
        relations = [
            {
                "visibility": "public",
                **dict(row),
                "evidence_ids": [
                    value["evidence_id"]
                    for value in connection.execute(
                        "SELECT evidence_id FROM relation_evidence WHERE relation_id = ? ORDER BY position",
                        (row["relation_id"],),
                    )
                ],
            }
            for row in connection.execute(
                "SELECT relation_id, source_id, target_id, relation_type FROM relations ORDER BY relation_id"
            )
        ]
        release_id, published_at = reader.release_id, reader.published_at
    return {
        "schema_version": 1,
        "release_id": release_id,
        "published_at": published_at,
        "documents": documents,
        "evidence": evidence,
        "knowledge": knowledge,
        "entities": entities,
        "relations": relations,
    }


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ReleaseError(f"cannot run {command[0]}: {exc}") from exc


def _build_site(site_dir: Path, env: dict[str, str]) -> None:
    result = _run(["npm", "run", "build", "--", "--outDir", str(site_dir)], cwd=SITE_SOURCE, env=env)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ReleaseError(f"site build failed with exit code {result.returncode}: {detail}")
    if not (site_dir / "index.html").is_file():
        raise ReleaseError(f"site build did not produce index.html in {site_dir}")


def _prerender(snapshot_path: Path, site_dir: Path, env: dict[str, str]) -> None:
    call = _PRERENDER_CALL.replace("__MODULE_URL__", json.dumps(PRERENDER.as_uri()))
    prerender_env = {**env, "VITAX_SNAPSHOT": str(snapshot_path), "VITAX_SITE": str(site_dir)}
    result = _run(["node", "--input-type=module", "--eval", call], cwd=SITE_SOURCE, env=prerender_env)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ReleaseError(f"prerender failed with exit code {result.returncode}: {detail}")
    try:
        report = json.loads(result.stdout)
        skipped = report["skipped"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReleaseError(f"prerender returned an unreadable report: {exc}") from exc
    if skipped:
        raise ReleaseError(f"prerender skipped {len(skipped)} unpublishable item(s): {json.dumps(skipped)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(database: Path, target: Path) -> dict[str, object]:
    with KnowledgeReader(database) as release:
        release_id, published_at = release.release_id, release.published_at
    files = [
        {"path": path.relative_to(target).as_posix(), "sha256": _sha256(path)}
        for path in (database, *sorted(path for path in (target / "site").rglob("*") if path.is_file()))
    ]
    return {
        "schema_version": 1,
        "release_id": release_id,
        "published_at": published_at,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "images": [],
        "files": sorted(files, key=lambda entry: entry["path"]),
    }


def build_release(projection_path: str | Path, output_dir: str | Path, *, site_dir: str | Path | None = None) -> dict[str, object]:
    """Build one new release directory and return its manifest."""
    # absolute(), not resolve(): the caller's cwd defines a relative target and a
    # symlinked target must still be refused by lexists rather than followed.
    target = Path(output_dir).absolute()
    prebuilt = Path(site_dir) if site_dir is not None else (Path(os.environ["VITAX_PREBUILT_SITE"]) if os.environ.get("VITAX_PREBUILT_SITE") else None)
    if os.path.lexists(target):
        raise ReleaseError(f"output path already exists: {target}")
    if not target.parent.is_dir():
        raise ReleaseError(f"output parent directory does not exist: {target.parent}")
    if prebuilt is not None and not (prebuilt / "index.html").is_file():
        raise ReleaseError(f"prebuilt site directory has no index.html: {prebuilt}")
    os.mkdir(target)
    try:
        database = target / "public.sqlite"
        build(projection_path, database)
        (target / "images").mkdir()
        if prebuilt is not None:
            shutil.copytree(prebuilt, target / "site")
        else:
            dto = _export_public_dto(database)
            with tempfile.TemporaryDirectory(prefix="vitax-release-") as scratch:
                snapshot_path = Path(scratch) / "snapshot.json"
                snapshot_path.write_text(json.dumps(dto, ensure_ascii=False), encoding="utf-8")
                _build_site(target / "site", dict(os.environ))
                _prerender(snapshot_path, target / "site", dict(os.environ))
        manifest = _manifest(database, target)
        (target / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/build_vitax_release.py",
        description="Build one local VitaX reader release from an accepted public projection.",
    )
    parser.add_argument("projection", help="path to the accepted public projection JSON")
    parser.add_argument("output_dir", help="new release directory to create")
    parser.add_argument("--prebuilt-site", default=None, help="trusted prebuilt site directory to copy instead of npm build + prerender")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = build_release(args.projection, args.output_dir, site_dir=args.prebuilt_site)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{manifest['release_id']}: {len(manifest['files'])} file(s) -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
