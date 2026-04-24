"""Canonical WeChat KOL registry — single source of truth for account identity.

Usage:
    from kol_registry import get_fakeid, get_wechat_id, get_account, list_accounts

    # Lookup by name
    fakeid = get_fakeid("叶小钗")   # → "Mzg2MzcyODQ5MQ=="
    wid = get_wechat_id("叶小钗")   # → "yexiaochai"

    # Get full account info
    acc = get_account("智猩猩")     # → {"name": "智猩猩", "wechat_id": "zhixingxing", ...}
    print(acc["tags"])

    # List all / filter
    all_kols = list_accounts()                          # 20 accounts
    csv_only = list_accounts(source="CSV_Scrape")       # 4 scraped-only
    agent_tagged = [a for a in all_kols if "Agent" in a.get("tags", [])]
"""

from pathlib import Path
from typing import Optional

_registry: list[dict] | None = None


def _load() -> list[dict]:
    global _registry
    if _registry is not None:
        return _registry
    path = Path(__file__).parent / "docs" / "wechat_kol_registry.json"
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _registry = data["accounts"]
    return _registry


def get_account(name: str) -> Optional[dict]:
    """Return full account dict (name, wechat_id, fakeid, source, tags) or None."""
    for acc in _load():
        if acc["name"] == name:
            return acc
    return None


def get_fakeid(name: str) -> Optional[str]:
    """Return fakeid (__biz) for an account name, or None."""
    acc = get_account(name)
    return acc["fakeid"] if acc else None


def get_wechat_id(name: str) -> Optional[str]:
    """Return WeChat ID (微信号) for an account name, or None."""
    acc = get_account(name)
    return acc["wechat_id"] if acc else None


def list_accounts(source: Optional[str] = None) -> list[dict]:
    """Return all accounts, optionally filtered by source (KOL_List, CSV_Scrape, etc.)."""
    accounts = _load()
    if source:
        return [a for a in accounts if a.get("source") == source]
    return accounts
