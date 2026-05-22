"""Local image HTTP server bring-up for the research CLI.

ORCH-08: Synthesized markdown embeds http://localhost:8765/<hash>/<N>.jpg URLs.
The CLI must ensure the server is listening before research() runs so those
URLs resolve when the user views the output.

Idempotent: re-running the CLI when a server is already running on port 8765
returns None and does NOT spawn a duplicate.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path


def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Probe whether ``port`` on ``host`` is currently accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def ensure_image_server(base_image_dir: Path, port: int = 8765) -> int | None:
    """Ensure ``python -m http.server <port> --directory <base_image_dir>`` is running.

    Returns the spawned PID if a new server was started, or ``None`` if one was
    already listening on ``port``.

    Raises ``FileNotFoundError`` if ``base_image_dir`` does not exist — we
    refuse to spawn a server pointing at a missing directory.

    The spawned subprocess is detached so it survives the parent Python
    process exit (Windows: ``CREATE_NEW_PROCESS_GROUP``; POSIX:
    ``start_new_session=True``).
    """
    base_image_dir = Path(base_image_dir)
    if not base_image_dir.is_dir():
        raise FileNotFoundError(
            f"base_image_dir does not exist: {base_image_dir}"
        )

    if _is_port_listening(port):
        return None

    cmd = [
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--directory",
        str(base_image_dir),
    ]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid
