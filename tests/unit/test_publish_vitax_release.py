"""Publish composes, uploads, verifies and switches one reader snapshot."""
import hashlib
import json
import subprocess
import sqlite3
import sys

import pytest

import scripts.publish_vitax_release as publisher


RELEASE_ID = "release-local-abc123"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime(root):
    """A runtime root shaped like the refresh output: public/current + library/current."""
    release = root / "public/releases" / RELEASE_ID
    release.mkdir(parents=True)
    (release / "public.sqlite").write_bytes(b"PUBLIC")
    (release / "site").mkdir()
    (release / "site/index.html").write_text("index")
    files = [
        {"path": "public.sqlite", "sha256": _sha(b"PUBLIC")},
        {"path": "site/index.html", "sha256": _sha(b"index")},
    ]
    (release / "manifest.json").write_text(json.dumps({"schema_version": 1, "release_id": RELEASE_ID, "files": files}))
    (root / "public/current").symlink_to(release, target_is_directory=True)
    library = root / "library/snapshots/s1"
    library.mkdir(parents=True)
    (library / "articles.sqlite").write_bytes(b"ARTICLES")
    (library / "receipt.json").write_text('{"snapshot_id": "s1"}')
    (root / "library/current").symlink_to(library, target_is_directory=True)
    return release


def test_compose_package_gathers_release_library_and_code(tmp_path):
    _runtime(tmp_path)
    code = tmp_path / "vitax"; code.mkdir(); (code / "api.py").write_text("x")
    package = tmp_path / "package"

    assert publisher.compose_package(tmp_path, package, code_dir=code) == RELEASE_ID

    assert sorted(p.name for p in package.iterdir()) == [
        "articles.sqlite", "code", "manifest.json", "public.sqlite", "receipt.json", "site",
    ]
    assert (package / "code/vitax/api.py").read_text() == "x"
    assert (package / "articles.sqlite").read_bytes() == b"ARTICLES"


def test_compose_package_refuses_a_bad_release_id(tmp_path):
    release = _runtime(tmp_path)
    manifest = json.loads((release / "manifest.json").read_text())
    manifest["release_id"] = "../escape"
    (release / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(publisher.PublishError, match="safe path segment"):
        publisher.compose_package(tmp_path, tmp_path / "package")


def test_publish_uploads_verifies_switches_and_restarts(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"; _runtime(runtime)
    package = tmp_path / "package"; publisher.compose_package(runtime, package)
    calls = []

    def run(command, **kwargs):
        assert command[0] == ("scp" if "scp" in command else "ssh")
        calls.append(" ".join(command))
        if "python3" in command:
            stdout = json.dumps({"release_id": RELEASE_ID, "deployment_id": RELEASE_ID + "-snapshot", "files": 2, "current": "/root/vitax-mvp/releases/" + RELEASE_ID, "changed": True})
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(publisher, "_run", run)
    result = publisher.publish(package)

    assert result["release_id"] == RELEASE_ID
    assert result["changed"] is True and result["service"] == "vitax-reader"
    assert any("HostKeyAlias=47.103.73.20" in call and "StrictHostKeyChecking=yes" in call for call in calls)
    assert any(call.startswith("scp -r -q") and "root@172.18.12.150" in call for call in calls)
    assert any("systemctl restart vitax-reader" in call for call in calls)


def test_publish_skips_restart_when_the_release_is_already_current(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"; _runtime(runtime)
    package = tmp_path / "package"; publisher.compose_package(runtime, package)
    calls = []

    def run(command, **kwargs):
        assert command[0] == ("scp" if "scp" in command else "ssh")
        calls.append(" ".join(command))
        stdout = json.dumps({"release_id": RELEASE_ID, "deployment_id": RELEASE_ID + "-snapshot", "files": 2, "current": "/root/vitax-mvp/releases/" + RELEASE_ID, "changed": False}) if "python3" in command else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(publisher, "_run", run)
    result = publisher.publish(package)
    assert result["changed"] is False
    assert not any("systemctl restart" in call for call in calls)


def test_main_prints_one_result_line(tmp_path, monkeypatch, capsys):
    runtime = tmp_path / "runtime"; _runtime(runtime)
    monkeypatch.setattr(publisher, "publish", lambda package, **kwargs: {"release_id": RELEASE_ID, "changed": True})
    assert publisher.main(["--root", str(runtime), "--code-dir", ""]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["release_id"] == RELEASE_ID


def test_remote_promote_versions_article_updates_and_reuses_identical_data(tmp_path):
    runtime = tmp_path / "runtime"
    release = _runtime(runtime)
    # Exercise the actual promotion program offline, including its SQLite identity check.
    (release / "public.sqlite").unlink()
    with sqlite3.connect(release / "public.sqlite") as connection:
        connection.execute("CREATE TABLE metadata(key TEXT, value TEXT)")
        connection.execute("INSERT INTO metadata VALUES('release_id', ?)", (RELEASE_ID,))
    manifest = json.loads((release / "manifest.json").read_text())
    manifest["files"][0]["sha256"] = _sha((release / "public.sqlite").read_bytes())
    (release / "manifest.json").write_text(json.dumps(manifest))
    reader = tmp_path / "reader"
    (reader / "releases").mkdir(parents=True)

    def promote(number):
        staging = reader / "releases" / ("staging-" + str(number))
        publisher.compose_package(runtime, staging)
        result = subprocess.run(
            [sys.executable, "-c", publisher._REMOTE_PROMOTE, RELEASE_ID, str(staging), str(reader)],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)

    first = promote(1)
    same = promote(2)
    assert first["changed"] and not same["changed"]
    assert first["deployment_id"] == RELEASE_ID + "-" + _sha(b"ARTICLES")[:16]
    assert same["deployment_id"] == first["deployment_id"]
    (runtime / "library/current/articles.sqlite").write_bytes(b"UPDATED_TRANSLATION")
    updated = promote(3)
    assert updated["release_id"] == first["release_id"] == RELEASE_ID
    assert updated["changed"] and updated["deployment_id"] != first["deployment_id"]
    assert (reader / "current/articles.sqlite").read_bytes() == b"UPDATED_TRANSLATION"
    assert (reader / "releases" / first["deployment_id"] / "articles.sqlite").read_bytes() == b"ARTICLES"


def test_compose_package_copies_existing_manifest_images(tmp_path):
    release = _runtime(tmp_path)
    (release / "images").mkdir()
    (release / "images/source.png").write_bytes(b"EXISTING_ASSET")
    manifest = json.loads((release / "manifest.json").read_text())
    manifest["files"].append({"path": "images/source.png", "sha256": _sha(b"EXISTING_ASSET")})
    (release / "manifest.json").write_text(json.dumps(manifest))
    package = tmp_path / "package"
    publisher.compose_package(tmp_path, package)
    assert (package / "images/source.png").read_bytes() == b"EXISTING_ASSET"
    for entry in manifest["files"]:
        assert _sha((package / entry["path"]).read_bytes()) == entry["sha256"]


@pytest.mark.parametrize("failure", ["restart", "smoke"])
def test_failed_reader_update_rolls_back_and_restores_only_reader(tmp_path, monkeypatch, failure):
    runtime = tmp_path / "runtime"; _runtime(runtime)
    package = tmp_path / "package"; publisher.compose_package(runtime, package)
    reader = tmp_path / "reader"; reader.mkdir()
    previous = reader / "old"; previous.mkdir()
    candidate = reader / "new"; candidate.mkdir()
    current = reader / "current"; current.symlink_to(candidate)
    calls = []
    failed = False

    def run(command, **kwargs):
        nonlocal failed
        assert command[0] in ("ssh", "scp")
        calls.append((command, kwargs.get("input")))
        program = kwargs.get("input")
        if program == publisher._REMOTE_PROMOTE:
            stdout = json.dumps({"release_id": RELEASE_ID, "deployment_id": "new", "files": 2,
                                 "current": str(candidate), "previous_current": str(previous), "changed": True})
        elif program == publisher._REMOTE_ROLLBACK:
            # Execute the exact rollback program locally, without SSH.
            result = subprocess.run([sys.executable, "-c", program, str(previous), str(reader)],
                                    capture_output=True, text=True, check=True)
            return result
        else:
            stdout = ""
        trigger = command[-1] == "systemctl restart vitax-reader" if failure == "restart" else program == publisher._REMOTE_SMOKE
        if trigger and not failed:
            failed = True
            return subprocess.CompletedProcess(command, 1, "", "synthetic reader failure")
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(publisher, "_run", run)
    with pytest.raises(publisher.PublishError, match="previous release restored"):
        publisher.publish(package, remote_root=str(reader))
    assert current.resolve() == previous and candidate.is_dir()
    restarts = [command[-1] for command, _ in calls if "systemctl" in command[-1]]
    assert restarts == ["systemctl restart vitax-reader"] * 2
    assert sum(program == publisher._REMOTE_ROLLBACK for _, program in calls) == 1
    assert calls[-1][1] == publisher._REMOTE_SMOKE


def test_producer_wrapper_runs_each_round_with_shared_daily_lane(tmp_path):
    recorder = tmp_path / "record.py"
    output = tmp_path / "args.jsonl"
    import os
    wrapper = publisher.REPO_ROOT / "deploy/vitax-producer/producer"
    environment = {**os.environ, "VITAX_CODE": str(tmp_path), "VITAX_PYTHON": str(recorder), "OMNIGRAPH_REPO_ROOT": "/old/repo"}
    # A shell recorder captures argv; it never loads producer code or credentials.
    recorder.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + str(output) + "\n")
    recorder.write_text(recorder.read_text()+'case "$*" in *rebuild_fts*) test "$OMNIGRAPH_REPO_ROOT" = /root/OmniGraph-Vault;; *) test "$OMNIGRAPH_REPO_ROOT" = "$VITAX_CODE";; esac || exit 9\n')
    recorder.chmod(0o700)
    rsync = tmp_path / "rsync"
    rsync.write_text("#!/bin/sh\nprintf '%s\\n' \"rsync $*\" >> " + str(output) + "\n")
    rsync.chmod(0o700)
    environment["PATH"] = str(tmp_path) + os.pathsep + environment["PATH"]
    for _ in range(2):
        subprocess.run(["sh", str(wrapper)], env=environment, check=True)
    lines = output.read_text().splitlines()
    assert len(lines) == 8
    assert all("--backfill --backfill-lane D --queue 50" in line for line in lines[::4])
    assert all("kb.scripts.rebuild_fts" in line for line in lines[1::4])
    assert all("HostKeyAlias=47.103.73.20" in line for line in lines[2::4])


def test_reader_smoke_waits_for_owned_service_startup(monkeypatch):
    import io,sys,urllib.request,urllib.error
    from scripts import publish_vitax_release as publisher
    calls=[]
    def response(url,timeout):
        calls.append(url)
        if len(calls)==1:raise urllib.error.URLError('not ready')
        return io.BytesIO(json.dumps({'release_id':'ready'} if url.endswith('/api/release') else {'snapshot_id':'snapshot'}).encode())
    monkeypatch.setattr(urllib.request,'urlopen',response)
    monkeypatch.setattr(sys,'argv',['smoke','ready'])
    monkeypatch.setattr(__import__('time'),'sleep',lambda _:None)
    exec(publisher._REMOTE_SMOKE,{})
    assert len(calls)==3
