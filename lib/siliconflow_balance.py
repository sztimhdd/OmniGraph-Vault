"""SiliconFlow balance API + cost estimation for Phase 13 CASC-06.

Pure functions + two exceptions. Caller (image_pipeline integration Plan 13-02)
decides when to call and how to react to warnings. No module-level cache,
no module state -- balance fluctuates; always fresh.

D-BENCH-PRECHECK (absorbs v3.1 closure Finding 2): importing `config` at module
load guarantees `~/.hermes/.env` is sourced into os.environ BEFORE any key
reads. Without this, callers invoked from fresh shells (e.g. bench scripts)
would see SILICONFLOW_API_KEY as unset even when it exists in the dotenv file.
"""
from __future__ import annotations

# Trigger ~/.hermes/.env load before any SILICONFLOW_API_KEY reads.
# D-BENCH-PRECHECK correct-by-construction guarantee: any caller of
# check_siliconflow_balance() automatically gets env sourced.
import config  # noqa: F401 -- import for side effect (dotenv load)

import logging
import os
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

# CASC-06 LOCKED constants.
SILICONFLOW_PRICE_PER_IMAGE = Decimal("0.0013")   # CNY per image for Qwen3-VL-32B
OPENROUTER_SWITCH_THRESHOLD = Decimal("0.05")     # CNY -- switch to OpenRouter below this
BALANCE_API_TIMEOUT_SECS = 5.0

_BALANCE_URL = "https://api.siliconflow.cn/v1/user/info"


class BalanceCheckError(RuntimeError):
    """Raised when balance cannot be fetched (HTTP error, timeout, parse).

    Caller decides whether to abort batch, warn, or proceed assuming OK.
    """


class MissingKeyError(BalanceCheckError):
    """SILICONFLOW_API_KEY missing even after ~/.hermes/.env load.

    Subclasses BalanceCheckError so existing `except BalanceCheckError` catches
    still work.
    """


def check_siliconflow_balance() -> Decimal:
    """Fetch current SiliconFlow balance in CNY.

    Raises:
        MissingKeyError: SILICONFLOW_API_KEY unset in env and in ~/.hermes/.env.
        BalanceCheckError: on HTTP error, timeout, or parse failure.
    """
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        raise MissingKeyError(
            "SILICONFLOW_API_KEY not set in env or ~/.hermes/.env -- "
            "required for balance check."
        )
    try:
        resp = requests.get(
            _BALANCE_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=BALANCE_API_TIMEOUT_SECS,
        )
    except requests.Timeout as e:
        raise BalanceCheckError(
            f"timeout fetching SiliconFlow balance: {e}"
        ) from e
    except requests.RequestException as e:
        raise BalanceCheckError(
            f"network error fetching SiliconFlow balance: {e}"
        ) from e

    if resp.status_code != 200:
        raise BalanceCheckError(
            f"SiliconFlow balance HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        balance_str = resp.json()["data"]["totalBalance"]
        return Decimal(str(balance_str))
    except (KeyError, ValueError, TypeError) as e:
        raise BalanceCheckError(
            f"malformed balance response: {resp.text[:200]}"
        ) from e


def estimate_cost(
    remaining_articles: int, avg_images_per_article: int
) -> Decimal:
    """Estimate SiliconFlow cost for remaining batch in CNY.

    Cost model: remaining_articles * avg_images_per_article * CNY 0.0013/image.
    Returns Decimal("0") if either input is 0 or negative (graceful -- caller
    may pass 0 on a small batch).
    """
    articles = max(0, remaining_articles)
    images = max(0, avg_images_per_article)
    return Decimal(articles) * Decimal(images) * SILICONFLOW_PRICE_PER_IMAGE


def should_warn(balance: Decimal, estimated_cost: Decimal) -> bool:
    """Return True if operator should see a pre-batch / mid-batch warning.

    Trigger conditions (either):
        1. balance < estimated_cost    (not enough for planned work)
        2. balance < OPENROUTER_SWITCH_THRESHOLD  (already at critical floor)
    """
    return balance < estimated_cost or balance < OPENROUTER_SWITCH_THRESHOLD


def should_switch_to_openrouter(balance: Decimal) -> bool:
    """Return True if cascade should switch to OpenRouter-only for remaining
    images.

    Strict less-than against OPENROUTER_SWITCH_THRESHOLD (CNY 0.05).
    Rationale (CASC-06): prevents partial batch where half images have
    SiliconFlow descriptions and half have OpenRouter.
    """
    return balance < OPENROUTER_SWITCH_THRESHOLD
