"""
WeChat MP article lister with rate-limiting.
Calls the WeChat MP backend API directly using token + cookie + fakeid.
"""
import time
import json
import random
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("wechat_spider")

WECHAT_API_URL = "https://mp.weixin.qq.com/cgi-bin/appmsg"
DEFAULT_PAGE_SIZE = 20
# WeChat MP API rate limit is ~60 RPM per token.
# 2.0s page sleep = 30 RPM, safe margin under the limit.
# 5.0s account sleep = 12 accounts/min, also safe.
# Once ret=200013 fires, WeChat needs a 30–60s hard cooldown.
RATE_LIMIT_SLEEP_ACCOUNTS = 5.0
RATE_LIMIT_SLEEP_PAGES = 2.0
MAX_RETRIES = 3
RATE_LIMIT_COOLDOWN = 60.0  # hard cooldown after hitting ret=200013

# Session-level request counter to avoid triggering the anti-crawl mechanism.
# ret=200013 triggers at ~60 requests regardless of spacing — once hit,
# recovery can take 30–60 min. We stop proactively at 50 requests per session.
_session_request_count = 0
SESSION_REQUEST_LIMIT = 50
SESSION_COOLDOWN_MINUTES = 30


def _check_session_limit() -> None:
    """Raise RuntimeError if the session request budget is exhausted.

    ret=200013 is WeChat's anti-crawling mechanism, NOT a standard rate limit.
    It triggers at ~60 requests regardless of spacing. Once hit, recovery takes
    30–60 minutes (subscription accounts). We proactively stop at 50 requests
    rather than triggering the penalty box.
    """
    global _session_request_count
    if _session_request_count >= SESSION_REQUEST_LIMIT:
        raise RuntimeError(
            f"Session request limit reached ({_session_request_count}/{SESSION_REQUEST_LIMIT}). "
            f"WeChat anti-crawl triggers at ~60 req. "
            f"Wait ~{SESSION_COOLDOWN_MINUTES} min before running again."
        )
    _session_request_count += 1


def _backoff_sleep(attempt: int) -> float:
    return (2 ** attempt) + random.uniform(0, 1)


def list_articles(
    token: str,
    cookie: str,
    fakeid: str,
    days_back: int = 90,
    max_articles: int = 50,
) -> list[dict]:
    """
    List recent articles for a WeChat Official Account.

    Returns list of dicts with keys: title, url, update_time (unix ts), fakeid.
    Handles 429 with exponential backoff. Raises RuntimeError on persistent failure.
    """
    cutoff_ts = int((datetime.now() - timedelta(days=days_back)).timestamp())
    headers = {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://mp.weixin.qq.com/",
    }

    articles: list[dict] = []
    begin = 0

    while len(articles) < max_articles:
        params = {
            "token": token,
            "fakeid": fakeid,
            "action": "list_ex",
            "type": "9",
            "count": str(DEFAULT_PAGE_SIZE),
            "begin": str(begin),
            "f": "json",
            "ajax": "1",
        }

        data = None
        for attempt in range(1, MAX_RETRIES + 1):
            _check_session_limit()
            try:
                resp = requests.get(WECHAT_API_URL, params=params, headers=headers, timeout=15)
                if resp.status_code == 429:
                    wait = RATE_LIMIT_COOLDOWN + _backoff_sleep(attempt)
                    logger.warning(f"HTTP 429 for fakeid={fakeid}, "
                                 f"cooldown {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                base_resp = data.get("base_resp", {})
                if base_resp.get("ret") != 0:
                    ret_code = base_resp.get("ret")
                    err_msg = base_resp.get("err_msg", "unknown error")
                    if ret_code in (200013,):
                        if attempt < MAX_RETRIES:
                            # WeChat needs a hard cooldown — exponential backoff alone won't work.
                            wait = RATE_LIMIT_COOLDOWN + _backoff_sleep(attempt)
                            logger.warning(f"WeChat API rate limit (ret={ret_code}) for fakeid={fakeid}, "
                                         f"hard cooldown {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})")
                            time.sleep(wait)
                            continue
                        raise RuntimeError(f"WeChat API rate limit (ret={ret_code}) after {MAX_RETRIES} attempts: {err_msg}")
                    raise RuntimeError(f"WeChat API error (ret={ret_code}): {err_msg}")
                break
            except requests.RequestException as e:
                if attempt < MAX_RETRIES:
                    wait = _backoff_sleep(attempt)
                    logger.warning(f"Request failed (attempt {attempt}): {e}, retrying in {wait:.1f}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Failed to list articles for fakeid={fakeid} after {MAX_RETRIES} attempts: {e}") from e

        if data is None:
            raise RuntimeError(f"Failed to get valid data for fakeid={fakeid}")

        msg_list = data.get("app_msg_list", [])
        if not msg_list:
            logger.info("No more articles at begin=%d for fakeid=%s", begin, fakeid)
            break

        for item in msg_list:
            ts = item.get("update_time", 0)
            if ts < cutoff_ts:
                logger.info("Reached cutoff date at begin=%d for fakeid=%s", begin, fakeid)
                return articles

            articles.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "update_time": ts,
                "fakeid": fakeid,
            })

            if len(articles) >= max_articles:
                return articles

        begin += DEFAULT_PAGE_SIZE
        time.sleep(RATE_LIMIT_SLEEP_PAGES)

    return articles


def list_articles_with_digest(
    token: str,
    cookie: str,
    fakeid: str,
    days_back: int = 90,
    max_articles: int = 50,
) -> list[dict]:
    """
    Like list_articles but also returns the 'digest' (summary) field
    for each article — needed for LLM topic classification.
    """
    cutoff_ts = int((datetime.now() - timedelta(days=days_back)).timestamp())
    headers = {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://mp.weixin.qq.com/",
    }

    articles: list[dict] = []
    begin = 0

    while len(articles) < max_articles:
        params = {
            "token": token,
            "fakeid": fakeid,
            "action": "list_ex",
            "type": "9",
            "count": str(DEFAULT_PAGE_SIZE),
            "begin": str(begin),
            "f": "json",
            "ajax": "1",
        }

        data = None
        for attempt in range(1, MAX_RETRIES + 1):
            _check_session_limit()
            try:
                resp = requests.get(WECHAT_API_URL, params=params, headers=headers, timeout=15)
                if resp.status_code == 429:
                    wait = RATE_LIMIT_COOLDOWN + _backoff_sleep(attempt)
                    logger.warning(f"HTTP 429 for fakeid={fakeid}, "
                                 f"cooldown {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                base_resp = data.get("base_resp", {})
                if base_resp.get("ret") != 0:
                    ret_code = base_resp.get("ret")
                    err_msg = base_resp.get("err_msg", "unknown error")
                    if ret_code in (200013,):
                        if attempt < MAX_RETRIES:
                            # WeChat needs a hard cooldown — exponential backoff alone won't work.
                            wait = RATE_LIMIT_COOLDOWN + _backoff_sleep(attempt)
                            logger.warning(f"WeChat API rate limit (ret={ret_code}) for fakeid={fakeid}, "
                                         f"hard cooldown {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})")
                            time.sleep(wait)
                            continue
                        raise RuntimeError(f"WeChat API rate limit (ret={ret_code}) after {MAX_RETRIES} attempts: {err_msg}")
                    raise RuntimeError(f"WeChat API error (ret={ret_code}): {err_msg}")
                break
            except requests.RequestException as e:
                if attempt < MAX_RETRIES:
                    wait = _backoff_sleep(attempt)
                    logger.warning(f"Request failed (attempt {attempt}): {e}, retrying in {wait:.1f}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Failed to list articles for fakeid={fakeid} after {MAX_RETRIES} attempts: {e}") from e

        if data is None:
            raise RuntimeError(f"Failed to get valid data for fakeid={fakeid}")

        msg_list = data.get("app_msg_list", [])
        if not msg_list:
            logger.info("No more articles at begin=%d for fakeid=%s", begin, fakeid)
            break

        for item in msg_list:
            ts = item.get("update_time", 0)
            if ts < cutoff_ts:
                logger.info("Reached cutoff date at begin=%d for fakeid=%s", begin, fakeid)
                return articles

            articles.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "digest": item.get("digest", ""),
                "update_time": ts,
                "fakeid": fakeid,
            })

            if len(articles) >= max_articles:
                return articles

        begin += DEFAULT_PAGE_SIZE
        time.sleep(RATE_LIMIT_SLEEP_PAGES)

    return articles


def scan_all_accounts(
    token: str,
    cookie: str,
    fakeids: dict[str, str],
    days_back: int = 90,
    max_per_account: int = 20,
    account_sleep: float = RATE_LIMIT_SLEEP_ACCOUNTS,
) -> list[dict]:
    """
    Scan articles from all accounts with throttling between accounts.

    Args:
        fakeids: dict of {account_name: fakeid}
        account_sleep: seconds to sleep between scanning different accounts
                       (WeChat MP API ~60 RPM per token, so 2s is safe)

    Returns:
        Combined list of article dicts from all accounts.
        Each dict has: title, url, digest, update_time, fakeid, account_name
    """
    all_articles: list[dict] = []
    total_accounts = len(fakeids)

    for i, (account_name, fakeid) in enumerate(fakeids.items(), 1):
        logger.info(
            "Scanning account %d/%d: %s (fakeid=%s)",
            i, total_accounts, account_name, fakeid,
        )
        try:
            articles = list_articles_with_digest(
                token=token, cookie=cookie, fakeid=fakeid,
                days_back=days_back, max_articles=max_per_account,
            )
            for art in articles:
                art["account_name"] = account_name
            all_articles.extend(articles)
            logger.info("  Got %d articles from %s", len(articles), account_name)
        except Exception as exc:
            logger.error("  Failed to scan %s: %s", account_name, exc)

        if i < total_accounts:
            logger.debug("  Sleeping %.1fs before next account...", account_sleep)
            time.sleep(account_sleep)

    logger.info("Scan complete: %d articles from %d accounts", len(all_articles), total_accounts)
    return all_articles
