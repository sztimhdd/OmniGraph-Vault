"""Tests for lib.research.image_server — idempotent local image HTTP server bring-up."""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.research.image_server import _is_port_listening, ensure_image_server


def _free_port() -> int:
    """Ask the OS for a free port (it's released between this call and the test
    binding it again, but the small race window is acceptable for unit tests)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# _is_port_listening
# ---------------------------------------------------------------------------


def test_is_port_listening_returns_false_on_free_port() -> None:
    port = _free_port()
    assert _is_port_listening(port) is False


def test_is_port_listening_returns_true_when_socket_bound() -> None:
    """Bind a real listening socket on a free port, then probe it."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        # Accept-loop in a thread so the connect() in _is_port_listening succeeds.
        accepted: list[socket.socket] = []

        def _accept_once() -> None:
            try:
                conn, _ = server.accept()
                accepted.append(conn)
            except OSError:
                pass

        t = threading.Thread(target=_accept_once, daemon=True)
        t.start()

        assert _is_port_listening(port) is True
    finally:
        for c in accepted:
            try:
                c.close()
            except OSError:
                pass
        server.close()


# ---------------------------------------------------------------------------
# ensure_image_server
# ---------------------------------------------------------------------------


def test_ensure_image_server_spawns_when_port_free(tmp_path: Path) -> None:
    """When port is free, ensure_image_server spawns a subprocess and returns its PID."""
    port = _free_port()

    fake_proc = MagicMock()
    fake_proc.pid = 99999

    with patch(
        "lib.research.image_server.subprocess.Popen", return_value=fake_proc
    ) as mock_popen:
        pid = ensure_image_server(tmp_path, port=port)

    assert pid == 99999
    mock_popen.assert_called_once()


def test_ensure_image_server_returns_none_when_port_busy(tmp_path: Path) -> None:
    """When port is already listening, returns None and does NOT spawn."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        # Background accept so _is_port_listening's connect succeeds.
        def _accept_loop() -> None:
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                pass

        threading.Thread(target=_accept_loop, daemon=True).start()

        with patch(
            "lib.research.image_server.subprocess.Popen"
        ) as mock_popen:
            result = ensure_image_server(tmp_path, port=port)

        assert result is None
        mock_popen.assert_not_called()
    finally:
        server.close()


def test_ensure_image_server_idempotent(tmp_path: Path) -> None:
    """Calling twice in sequence: first spawns, second sees port busy and returns None.

    We simulate the second call's port-busy view by patching _is_port_listening
    to return True on the second invocation.
    """
    port = _free_port()
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    listen_results = iter([False, True])

    def _fake_listen(p: int, host: str = "127.0.0.1") -> bool:
        return next(listen_results)

    with patch("lib.research.image_server._is_port_listening", side_effect=_fake_listen), \
         patch("lib.research.image_server.subprocess.Popen", return_value=fake_proc) as mock_popen:
        first = ensure_image_server(tmp_path, port=port)
        second = ensure_image_server(tmp_path, port=port)

    assert first == 12345
    assert second is None
    assert mock_popen.call_count == 1


def test_ensure_image_server_uses_http_server_argv(tmp_path: Path) -> None:
    """Subprocess is spawned with `python -m http.server <port> --directory <dir>` form."""
    port = _free_port()
    fake_proc = MagicMock()
    fake_proc.pid = 22222

    with patch(
        "lib.research.image_server.subprocess.Popen", return_value=fake_proc
    ) as mock_popen:
        ensure_image_server(tmp_path, port=port)

    args, _ = mock_popen.call_args
    cmd = args[0]
    assert cmd[0] == sys.executable
    assert cmd[1:5] == ["-m", "http.server", str(port), "--directory"]
    assert Path(cmd[5]) == tmp_path


def test_ensure_image_server_raises_on_missing_dir(tmp_path: Path) -> None:
    """If base_image_dir doesn't exist, raise FileNotFoundError BEFORE spawning."""
    missing = tmp_path / "does-not-exist"
    with patch("lib.research.image_server.subprocess.Popen") as mock_popen:
        with pytest.raises(FileNotFoundError):
            ensure_image_server(missing, port=_free_port())
    mock_popen.assert_not_called()


def test_ensure_image_server_uses_detached_subprocess_kwargs(tmp_path: Path) -> None:
    """Verify subprocess is detached (survives parent exit).

    On Windows: creationflags=subprocess.CREATE_NEW_PROCESS_GROUP.
    On POSIX: start_new_session=True.
    """
    port = _free_port()
    fake_proc = MagicMock()
    fake_proc.pid = 33333

    with patch(
        "lib.research.image_server.subprocess.Popen", return_value=fake_proc
    ) as mock_popen:
        ensure_image_server(tmp_path, port=port)

    _, kwargs = mock_popen.call_args
    if sys.platform == "win32":
        assert kwargs.get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kwargs.get("start_new_session") is True
