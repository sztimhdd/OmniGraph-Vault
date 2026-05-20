"""Databricks Apps runner for app_minimal.

Uses environment variables (UVICORN_PORT, UVICORN_HOST) as per Databricks
Apps system environment documentation.
"""
import os
import sys

# Add source roots to path
sys.path.insert(0, "/app/python/source_code")
sys.path.insert(0, "/app/python/source_code/databricks-deploy")

import uvicorn
from app_minimal import app

if __name__ == "__main__":
    port = int(os.environ.get("UVICORN_PORT", 8080))
    host = os.environ.get("UVICORN_HOST", "0.0.0.0")

    print(f"[RUNNER] Starting app on {host}:{port}", flush=True)

    uvicorn.run(app, host=host, port=port, log_level="info")
