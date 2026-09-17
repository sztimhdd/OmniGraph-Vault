"""Offline contract for the ingest systemd pre-start status report."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "cleanup_stuck_docs.py"
SERVICE_COMMANDS = {
    "deploy/aliyun/systemd/omnigraph-daily-ingest.service": (
        "/root/OmniGraph-Vault/venv-aim1/bin/python "
        "/root/OmniGraph-Vault/batch_ingest_from_spider.py "
        "--from-db --max-articles 10 --batch-timeout 6300"
    ),
    "deploy/aliyun/systemd/omnigraph-afternoon-ingest.service": (
        "/root/OmniGraph-Vault/venv-aim1/bin/python "
        "/root/OmniGraph-Vault/batch_ingest_from_spider.py "
        "--from-db --max-articles 10"
    ),
    "deploy/aliyun/systemd/omnigraph-evening-ingest.service": (
        "/root/OmniGraph-Vault/venv-aim1/bin/python "
        "/root/OmniGraph-Vault/batch_ingest_from_spider.py "
        "--from-db --max-articles 10"
    ),
}


def _load_cleanup_with_fake_config(storage_dir: Path):
    """Load the CLI without importing config.py or reading its environment."""
    fake_config = ModuleType("config")
    fake_config.RAG_WORKING_DIR = storage_dir
    spec = importlib.util.spec_from_file_location("_cleanup_prestart_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original_config = sys.modules.get("config")
    sys.modules["config"] = fake_config
    try:
        spec.loader.exec_module(module)
    finally:
        if original_config is None:
            del sys.modules["config"]
        else:
            sys.modules["config"] = original_config
    return module


def _service_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"{key} missing from {path}")


def test_ingest_prestart_is_a_read_only_status_report(tmp_path, capsys) -> None:
    """Pre-start must report residue without creating RAG or changing its status file."""
    status_path = tmp_path / "kv_store_doc_status.json"
    status_path.write_text(
        json.dumps({"orphan": {"status": "processing"}}), encoding="utf-8"
    )
    cleanup = _load_cleanup_with_fake_config(tmp_path)

    async def unexpected_rag_construction():
        raise AssertionError("pre-start must not construct RAG")

    cleanup._build_rag = unexpected_rag_construction
    before = status_path.read_bytes()
    assert cleanup.main(["--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["docs_identified"] == 1
    assert report["docs_deleted"] == 0
    assert status_path.read_bytes() == before
    for relative_path, expected_exec_start in SERVICE_COMMANDS.items():
        service_path = REPO_ROOT / relative_path
        prestart = _service_value(service_path, "ExecStartPre")
        assert prestart.endswith("cleanup_stuck_docs.py --dry-run")
        assert "--all-failed" not in prestart
        assert _service_value(service_path, "ExecStart") == expected_exec_start
