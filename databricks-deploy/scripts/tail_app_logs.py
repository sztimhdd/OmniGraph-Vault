"""Tail Databricks Apps runtime logs over the /logz WebSocket.

The Databricks Apps Web UI at https://<app-host>/logz uses a WebSocket at
/logz/stream to stream container stdout/stderr in real time. There is no
REST API and no `databricks apps logs` CLI subcommand (verified on CLI
v0.260.0). This script reproduces the WebSocket protocol so logs can be
fetched without copy-pasting from the browser.

Protocol (extracted from /logz HTML):
  1. Connect wss://<app-host>/logz/stream with `Authorization: Bearer <token>`
  2. Send a plain text search term as the first frame (empty string = all logs)
  3. Receive text frames:
       - "\\x00" (single null byte) means "no logs available"
       - JSON {"timestamp", "source", "message"} for a log entry
       - any other text = unstructured fallback line

Usage:
  python tail_app_logs.py                        # tail omnigraph-kb forever
  python tail_app_logs.py --filter "ERROR"        # filter via search term
  python tail_app_logs.py --once                  # print buffered logs and exit
  python tail_app_logs.py --app <name> --workspace <host>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from urllib.parse import urlparse

import websocket

# Databricks Apps build/runtime frames contain CJK + emoji from kb/ SSG
# (article titles, cron banners). On Windows, Python defaults stdout to
# cp1252 which crashes on the first non-Latin-1 char. Force UTF-8 with
# replacement so a malformed byte never aborts an autonomous log fetch.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


DEFAULT_WORKSPACE = "https://adb-2717931942638877.17.azuredatabricks.net"
DEFAULT_APP = "omnigraph-kb"
DEFAULT_PROFILE = "dev"


def get_token(workspace: str, profile: str) -> str:
    """Acquire OAuth bearer token via the databricks CLI."""
    result = subprocess.run(
        [
            "databricks",
            "auth",
            "token",
            "--host",
            workspace,
            "--profile",
            profile,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    return payload["access_token"]


def get_app_url(app: str, profile: str) -> str:
    """Resolve the public URL of a Databricks App."""
    result = subprocess.run(
        ["databricks", "apps", "get", app, "--profile", profile],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    return payload["url"]


def format_entry(raw: str) -> str | None:
    """Pretty-print a log frame; return None to drop the frame."""
    if raw == "\x00":
        return None
    try:
        entry = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw.rstrip()
    ts = entry.get("timestamp", "")
    src = entry.get("source", "?")
    msg = entry.get("message", "")
    return f"{ts} [{src}] {msg}".rstrip()


def tail(
    app: str,
    workspace: str,
    profile: str,
    filter_term: str,
    once: bool,
    max_seconds: float | None,
) -> int:
    token = get_token(workspace, profile)
    app_url = get_app_url(app, profile)
    host = urlparse(app_url).netloc
    ws_url = f"wss://{host}/logz/stream"

    print(f"[tail_app_logs] connecting to {ws_url} ...", file=sys.stderr)
    ws = websocket.create_connection(
        ws_url,
        header=[f"Authorization: Bearer {token}"],
        timeout=30,
    )

    try:
        ws.send(filter_term)
        deadline = (time.time() + max_seconds) if max_seconds else None
        empty_streak = 0
        while True:
            if deadline and time.time() > deadline:
                print("[tail_app_logs] reached --max-seconds, exiting", file=sys.stderr)
                return 0
            try:
                ws.settimeout(5 if once else None)
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                if once:
                    return 0
                continue
            except websocket.WebSocketConnectionClosedException:
                print("[tail_app_logs] connection closed by server", file=sys.stderr)
                return 1
            if frame == "":
                empty_streak += 1
                if once and empty_streak >= 2:
                    return 0
                continue
            line = format_entry(frame)
            if line is None:
                if once:
                    print("[tail_app_logs] no logs available", file=sys.stderr)
                    return 0
                continue
            empty_streak = 0
            print(line, flush=True)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tail Databricks Apps runtime logs via /logz/stream WebSocket."
    )
    parser.add_argument("--app", default=DEFAULT_APP, help="App name (default: %(default)s)")
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE,
        help="Workspace URL (default: %(default)s)",
    )
    parser.add_argument(
        "--profile", default=DEFAULT_PROFILE, help="Databricks CLI profile (default: %(default)s)"
    )
    parser.add_argument(
        "--filter",
        dest="filter_term",
        default="",
        help="Server-side substring filter (default: empty = all logs)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print currently buffered logs and exit (no live tail).",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Auto-exit after N seconds (default: tail forever).",
    )
    args = parser.parse_args()
    return tail(
        app=args.app,
        workspace=args.workspace,
        profile=args.profile,
        filter_term=args.filter_term,
        once=args.once,
        max_seconds=args.max_seconds,
    )


if __name__ == "__main__":
    sys.exit(main())
