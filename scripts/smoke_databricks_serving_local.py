"""Local smoke for Databricks Foundation Model + embedding endpoints.

Run from project root with the venv interpreter:

    venv\\Scripts\\python scripts\\smoke_databricks_serving_local.py

Loads ``databricks-deploy/.env.local`` via python-dotenv, then exercises:

  1. ``WorkspaceClient.current_user.me()`` (auth + SSL trust path)
  2. ``serving_endpoints.query`` against ``KB_LLM_MODEL``
  3. ``serving_endpoints.query`` against ``KB_EMBEDDING_MODEL``

All three must print ``ok`` for Phase 5 to pass. Failures map to the
playbook failure-mode lookup table in CLAUDE.md.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "databricks-deploy" / ".env.local"

load_dotenv(ENV_FILE, override=False)

# Force SSL bundle to certifi's merged cacert.pem (which has corp CAs appended
# per CLAUDE.md "SSL fix" recipe). The user's shell sets REQUESTS_CA_BUNDLE
# to a corp-only bundle that lacks public roots; pointing at certifi.where()
# gives both corp AND public roots, satisfying Umbrella-intercepted and
# direct chains alike.
import certifi  # noqa: E402

_CERTIFI_PATH = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = _CERTIFI_PATH
os.environ["SSL_CERT_FILE"] = _CERTIFI_PATH
os.environ["CURL_CA_BUNDLE"] = _CERTIFI_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_databricks_serving")


def main() -> int:
    if not ENV_FILE.exists():
        logger.error("env file not found: %s", ENV_FILE)
        return 2

    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if not profile:
        logger.error("DATABRICKS_CONFIG_PROFILE not set after loading %s", ENV_FILE)
        return 2

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

    w = WorkspaceClient(profile=profile, auth_type="pat")

    me = w.current_user.me()
    logger.info("auth ok: %s", me.user_name)

    llm_model = os.environ["KB_LLM_MODEL"]
    llm_resp = w.serving_endpoints.query(
        name=llm_model,
        messages=[
            ChatMessage(role=ChatMessageRole.USER, content="Reply with the single word ok"),
        ],
        max_tokens=8,
    )
    llm_text = llm_resp.choices[0].message.content
    logger.info("llm ok (%s): %r", llm_model, llm_text)

    emb_model = os.environ["KB_EMBEDDING_MODEL"]
    emb_resp = w.serving_endpoints.query(
        name=emb_model,
        input=["hello world"],
    )
    try:
        vec = emb_resp.data[0].embedding
    except AttributeError:
        data = getattr(emb_resp, "embeddings", None) or emb_resp.data
        first = data[0]
        vec = first["embedding"] if isinstance(first, dict) else first.embedding
    logger.info("emb ok (%s): dim=%d", emb_model, len(vec))

    return 0


if __name__ == "__main__":
    sys.exit(main())
