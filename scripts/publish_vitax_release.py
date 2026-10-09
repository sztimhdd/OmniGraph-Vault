"""Publish one verified VitaX reader snapshot to the cloud reader host.

Compose the current public release and library snapshot into one package, copy
it to the reader host, verify it there, switch ``current`` and restart only
``vitax-reader``. Old releases are kept; one JSON line reports the result.

Usage:
    .venv/bin/python scripts/publish_vitax_release.py --root <runtime-root>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Verified reader host: the address is dialled, the host key is looked up under
# the known 47.103.73.20 alias, and an unknown key refuses the connection.
READER_HOST = "root@172.18.12.150"
READER_HOST_KEY_ALIAS = "47.103.73.20"
READER_ROOT = "/root/vitax-mvp"
READER_SERVICE = "vitax-reader"
_RELEASE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "HostKeyAlias=" + READER_HOST_KEY_ALIAS,
    "-o", "StrictHostKeyChecking=yes",
]


class PublishError(RuntimeError):
    """The release could not be published to the reader host."""


def compose_package(root: str | Path, destination: str | Path, *, code_dir: str | Path | None = None) -> str:
    """Copy the current release and library snapshot into one reader package."""
    root = Path(root)
    release = (root / "public/current").resolve(strict=True)
    library = (root / "library/current").resolve(strict=True)
    manifest = json.loads((release / "manifest.json").read_text())
    if manifest.get("schema_version") != 1 or not manifest.get("files"):
        raise PublishError("invalid release manifest")
    release_id = str(manifest.get("release_id") or "")
    if not _RELEASE_ID.match(release_id):
        raise PublishError("release id is not a safe path segment")
    destination = Path(destination)
    destination.mkdir(parents=True, mode=0o700)
    for name in ("public.sqlite", "manifest.json"):
        source = release / name
        if not source.is_file():
            raise PublishError("release is missing " + name)
        shutil.copy2(source, destination / name)
    if not (release / "site/index.html").is_file():
        raise PublishError("release site is missing index.html")
    shutil.copytree(release / "site", destination / "site")
    if (release / "images").is_dir():
        shutil.copytree(release / "images", destination / "images")
    for name in ("articles.sqlite", "receipt.json"):
        source = library / name
        if not source.is_file():
            raise PublishError("library is missing " + name)
        shutil.copy2(source, destination / name)
    if code_dir is not None:
        code = Path(code_dir)
        if not code.is_dir():
            raise PublishError("code directory is missing: " + str(code))
        shutil.copytree(code, destination / "code" / code.name)
    return release_id


def _run(command: list[str], *, input: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, input=input, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublishError(f"cannot run {command[0]}: {exc}") from exc


def _check(result: subprocess.CompletedProcess[str], what: str) -> subprocess.CompletedProcess[str]:
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
        raise PublishError(f"{what} failed: {detail}")
    return result


def _ssh(host: str, remote_command: str, *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return _check(_run(["ssh", *_SSH_OPTS, host, remote_command], timeout=timeout), remote_command)


def _ssh_python(host: str, program: str, arguments: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return _check(_run(["ssh", *_SSH_OPTS, host, "python3", "-", *arguments], input=program, timeout=timeout), "remote verify")


def _scp(host: str, source: Path, destination: str) -> None:
    _check(_run(["scp", "-r", "-q", "-C", *_SSH_OPTS, str(source) + "/.", f"{host}:{destination}/"]), "package transfer")


# Runs on the reader host: verify the uploaded package, then atomically switch
# ``current`` to it. The deployment identity includes the article snapshot hash.
_REMOTE_PROMOTE = r'''
import hashlib,json,os,pathlib,shutil,sqlite3,sys
release,staging,root=sys.argv[1],pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3])
manifest=json.loads((staging/'manifest.json').read_text())
if str(manifest.get('release_id'))!=release or manifest.get('schema_version')!=1 or not manifest.get('files'):
 raise SystemExit('invalid release manifest')
for entry in manifest['files']:
 path=staging/entry['path']
 if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
  raise SystemExit('release hash mismatch: '+entry['path'])
con=sqlite3.connect('file:'+str(staging/'public.sqlite')+'?mode=ro',uri=True)
try: row=con.execute("SELECT value FROM metadata WHERE key='release_id'").fetchone()
finally: con.close()
if row is None or row[0]!=release: raise SystemExit('release identity mismatch')
with (staging/'articles.sqlite').open('rb') as stream:
 digest=hashlib.sha256()
 for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
deployment=release+'-'+digest.hexdigest()[:16]
final=root/'releases'/deployment
if final.exists():
 shutil.rmtree(staging)
else:
 staging.rename(final)
link=root/'current'
if os.path.lexists(link) and not link.is_symlink():
 raise SystemExit('current must be a managed symlink')
previous=os.path.realpath(link) if link.is_symlink() else None
changed=previous!=str(final)
if changed:
 tmp=link.with_name('.current-'+os.urandom(8).hex())
 tmp.symlink_to(final,target_is_directory=True)
 tmp.replace(link)
print(json.dumps({'release_id':release,'deployment_id':deployment,'files':len(manifest['files']),'current':str(final),'previous_current':previous,'changed':changed}))
'''

_REMOTE_ROLLBACK = r'''
import os,pathlib,sys
previous,root=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2])
if not previous.is_dir(): raise SystemExit('previous release missing')
link=root/'current'
tmp=link.with_name('.current-'+os.urandom(8).hex())
tmp.symlink_to(previous,target_is_directory=True)
tmp.replace(link)
'''

_REMOTE_SMOKE = r'''
import json,sys,time,urllib.request,urllib.error
def read(path):
 with urllib.request.urlopen('http://127.0.0.1:8788'+path,timeout=3) as response:
  return json.load(response)
for attempt in range(15):
 try:
  release=read('/api/release')['release_id']
  if not release or (sys.argv[1] and release!=sys.argv[1]): raise SystemExit('reader release mismatch')
  read('/api/library/status')
  break
 except (urllib.error.URLError,ConnectionError,TimeoutError):
  if attempt==14: raise
  time.sleep(2)
'''


def publish(package: str | Path, *, host: str = READER_HOST, remote_root: str = READER_ROOT, service: str = READER_SERVICE) -> dict[str, object]:
    """Upload, verify, switch and restart one already-composed package."""
    package = Path(package).absolute()
    if not (package / "manifest.json").is_file():
        raise PublishError("package has no manifest.json")
    release = str(json.loads((package / "manifest.json").read_text()).get("release_id") or "")
    if not _RELEASE_ID.match(release):
        raise PublishError("release id is not a safe path segment")
    staging = f"{remote_root}/releases/.staging-{uuid.uuid4().hex}"
    _ssh(host, f"mkdir -p {remote_root}/releases {staging}")
    _scp(host, package, staging)
    state = json.loads(_ssh_python(host, _REMOTE_PROMOTE, [release, staging, remote_root]).stdout)
    if state.get("changed"):
        try:
            _ssh(host, f"systemctl restart {service}")
            _ssh_python(host, _REMOTE_SMOKE, [release])
        except Exception as exc:
            previous = state.get("previous_current")
            if not previous:
                raise PublishError(f"reader update failed; no previous release: {exc}") from exc
            try:
                _ssh_python(host, _REMOTE_ROLLBACK, [previous, remote_root])
                _ssh(host, f"systemctl restart {service}")
                _ssh_python(host, _REMOTE_SMOKE, [""])
            except Exception as recovery:
                raise PublishError(f"reader update failed: {exc}; recovery failed: {recovery}") from recovery
            raise PublishError(f"reader update failed; previous release restored: {exc}") from exc
    return {
        "release_id": state["release_id"],
        "deployment_id": state["deployment_id"],
        "files": state["files"],
        "changed": state["changed"],
        "current": state["current"],
        "service": service,
        "host": host,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/publish_vitax_release.py",
        description="Publish the current VitaX release snapshot to the cloud reader host.",
    )
    parser.add_argument("--root", help="local runtime root holding public/current and library/current")
    parser.add_argument("--package", help="pre-composed package directory to publish as-is")
    parser.add_argument("--code-dir", default=None, help="reader code directory to include when composing (default: bundled vitax package)")
    parser.add_argument("--host", default=READER_HOST)
    parser.add_argument("--remote-root", default=READER_ROOT)
    parser.add_argument("--service", default=READER_SERVICE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.package:
            package = Path(args.package)
        else:
            if not args.root:
                raise PublishError("provide --root or --package")
            code_dir = REPO_ROOT / "vitax" if args.code_dir is None else (args.code_dir or None)
            package = Path(tempfile.mkdtemp(prefix="vitax-publish-")) / "package"
            compose_package(args.root, package, code_dir=code_dir)
        result = publish(package, host=args.host, remote_root=args.remote_root, service=args.service)
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
