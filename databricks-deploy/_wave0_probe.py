"""Wave 0 layout probe — kdb-2-04 Task 4.0.

TEMPORARY: discovers /app/ filesystem layout in the Apps container by
binding $DATABRICKS_APP_PORT and serving the introspection results as
a JSON HTTP response. User opens App URL post-workspace-SSO and sees
the layout info directly.

Will be deleted in the next commit (Wave 0 → production deploy swap).
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def gather_layout_info() -> dict:
    info: dict = {
        "marker": "WAVE0-PROBE",
        "pwd": os.getcwd(),
        "sys_path": sys.path,
        "env_DATABRICKS_APP_PORT": os.environ.get("DATABRICKS_APP_PORT"),
    }
    try:
        info["ls_cwd"] = sorted(os.listdir("."))
    except Exception as e:
        info["ls_cwd_error"] = repr(e)
    try:
        info["ls_app"] = sorted(os.listdir("/app"))
    except Exception as e:
        info["ls_app_error"] = repr(e)
    if os.path.isdir("/app"):
        deeper = []
        for entry in os.listdir("/app"):
            full = os.path.join("/app", entry)
            if os.path.isdir(full):
                try:
                    children = sorted(os.listdir(full))[:20]
                    deeper.append({"dir": entry, "children": children})
                except Exception as e:
                    deeper.append({"dir": entry, "error": repr(e)})
        info["app_subdir_listings"] = deeper
    info["kb_checks"] = {
        "/app/kb/api.py": os.path.isfile("/app/kb/api.py"),
        "/app/api.py": os.path.isfile("/app/api.py"),
        "/app/databricks-deploy/kb/api.py": os.path.isfile("/app/databricks-deploy/kb/api.py"),
    }
    info["adapter_checks"] = {
        "/app/databricks-deploy/startup_adapter.py": os.path.isfile(
            "/app/databricks-deploy/startup_adapter.py"
        ),
        "/app/startup_adapter.py": os.path.isfile("/app/startup_adapter.py"),
    }
    return info


_INFO = gather_layout_info()
_BODY = json.dumps(_INFO, indent=2, default=str).encode("utf-8")
print("WAVE0-PROBE-START", flush=True)
print(json.dumps(_INFO, default=str), flush=True)
print("WAVE0-PROBE-END", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, *args, **kwargs):  # silence default logging
        pass


def main() -> None:
    port_str = os.environ.get("DATABRICKS_APP_PORT") or "8080"
    port = int(port_str)
    print(f"WAVE0-LISTENING on 0.0.0.0:{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
