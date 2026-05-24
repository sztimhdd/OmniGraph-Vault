"""Local uvicorn launcher for databricks-deploy/app_entry:app.

Mirrors what Databricks Apps does for the deployed container, but for the
local Windows EDC dev box:

  1. Load ``databricks-deploy/.env.local`` so all KB_*/RAG_*/DATABRICKS_*
     env vars are populated (the platform injects these in the cloud).
  2. Force ``REQUESTS_CA_BUNDLE`` / ``SSL_CERT_FILE`` / ``CURL_CA_BUNDLE``
     at certifi's merged ``cacert.pem`` (corp roots merged in per CLAUDE.md
     SSL recipe). The user's shell defaults point at a corp-only bundle that
     lacks public roots — pointing at certifi gives both, satisfying both
     Umbrella-intercepted and direct chains.
  3. Add ``databricks-deploy/`` to ``sys.path`` so ``_db_client``,
     ``app_entry``, etc. are importable without ``--app-dir`` flag confusion.
  4. Launch uvicorn programmatically against ``app_entry:app``.

Usage::

    venv\\Scripts\\python scripts\\run_local_uvicorn.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import certifi
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "databricks-deploy" / ".env.local"
APP_DIR = REPO_ROOT / "databricks-deploy"

load_dotenv(ENV_FILE, override=False)

_CERTIFI_PATH = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = _CERTIFI_PATH
os.environ["SSL_CERT_FILE"] = _CERTIFI_PATH
os.environ["CURL_CA_BUNDLE"] = _CERTIFI_PATH

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_local_uvicorn")


def main() -> int:
    if not ENV_FILE.exists():
        logger.error("env file not found: %s", ENV_FILE)
        return 2

    host = os.environ.get("LOCAL_UVICORN_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCAL_UVICORN_PORT", "8000"))
    reload = os.environ.get("LOCAL_UVICORN_RELOAD", "0") == "1"

    logger.info("starting uvicorn app_entry:app on %s:%d (reload=%s)", host, port, reload)
    logger.info("certifi bundle: %s", _CERTIFI_PATH)
    logger.info("RAG_WORKING_DIR: %s", os.environ.get("RAG_WORKING_DIR", "<unset>"))
    logger.info("KB_DB_PATH: %s", os.environ.get("KB_DB_PATH", "<unset>"))

    import uvicorn

    uvicorn.run(
        "app_entry:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
