#!/usr/bin/env python3
"""dajiala_kol_scan — replace dead appmsgpublish KOL scanning with the 极致了 (dajiala.com) API.

Pipeline: for each KOL nickname -> POST /fbmain/monitor/v3/post_history (page=1)
          -> extract title/url/digest/post_time -> import into kol_scan.db articles
          (same shape batch_scan_kol._import_articles expects).

Why: WeChat closed appmsgpublish/list_ex on 2026-07-30. Sogou index can't do
     per-account lists. Dajiala API does — with today's articles.

Cost: 0.14-0.16 CNY/call, page=1 returns the latest 5 sends (1-8 articles each).

Usage:
    python dajiala_kol_scan.py --key JZL... [--account "叶小钗"] [--db data/kol_scan.db]
    python dajiala_kol_scan.py --key JZL... --dry-run          # JSON only, no DB write
    python dajiala_kol_scan.py --key JZL... --top 20           # scan top-N KOLs by prior value
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

API = "https://www.dajiala.com/fbmain/monitor/v3/post_history"
# Pro endpoint: 10 sends/page (vs 5), returns long links + Read/Zan/AccountInfo.
# Cheaper per article: 0.2 CNY/10 sends vs 0.16 CNY/5 sends.
API_PRO = "https://www.dajiala.com/fbmain/monitor/v3/history_by_ghid"
# Direct IP fallback from the vendor docs (faster, avoids DNS/CDN issues):
API_IP = "http://47.96.22.8:8000/fbmain/monitor/v3/post_history"
API_IP_PRO = "http://47.96.22.8:8000/fbmain/monitor/v3/history_by_ghid"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_history(key: str, nickname: str, page: int = 1, use_ip: bool = False) -> dict:
    """Call post_history with the nickname param. Returns parsed JSON."""
    params = urllib.parse.urlencode({"key": key, "nickname": nickname, "page": page})
    url = f"{API_IP if use_ip else API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_by_url(key: str, article_url: str, page: int = 1, use_ip: bool = False) -> dict:
    """Call post_history with a standard mp.weixin.qq.com/s?__biz= URL.

    The URL must be full percent-encoded (including & -> %26) or the API
    returns 20003. Standard __biz URLs work; sogou signature URLs do not.
    """
    enc = urllib.parse.quote(article_url, safe="")
    params = urllib.parse.urlencode({"key": key, "url": enc, "page": page})
    url = f"{API_IP if use_ip else API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def normalize_url(url: str) -> str:
    """Strip volatile query params (scene, sessionid) and #rd fragment.

    The API returns URLs with scene=126&sessionid=<unix>#rd that change every
    call — UNIQUE(url) dedup would break. Keep the stable biz/mid/idx/sn.
    """
    if not url:
        return url
    base, _, frag = url.partition("#")
    parts = base.split("?", 1)
    if len(parts) == 1:
        return base
    query = "&".join(
        kv for kv in parts[1].split("&")
        if kv and not kv.startswith(("scene=", "sessionid="))
    )
    return f"{parts[0]}?{query}" if query else parts[0]


def extract(entry: dict) -> dict:
    """Map a dajiala API entry to the articles-table row shape."""
    url = normalize_url(entry.get("url", ""))
    return {
        "title": entry.get("title", ""),
        "url": url,
        "digest": entry.get("digest", ""),
        "update_time": entry.get("post_time", 0),
        "original": entry.get("original"),
        "is_deleted": entry.get("is_deleted", "0"),
    }


def import_articles(conn: sqlite3.Connection, articles: list[dict],
                    account_name: str) -> tuple[int, int]:
    """INSERT OR IGNORE into articles (url UNIQUE = dedup). Returns (new, skipped)."""
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if row is None:
        print(f"  ! account '{account_name}' not in accounts table; skipping import")
        return 0, 0
    account_id = row[0]
    new = skipped = 0
    for art in articles:
        cur = conn.execute(
            "INSERT OR IGNORE INTO articles (account_id, title, url, digest, update_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, art["title"], art["url"], art["digest"], art["update_time"]),
        )
        if cur.rowcount > 0:
            new += 1
        else:
            skipped += 1
    conn.commit()
    return new, skipped


def fetch_by_ghid(key: str, ghid: str, offset: str = "", use_ip: bool = False) -> dict:
    """Call history_by_ghid (Pro). ghid accepts: gh_ id, wxid_, alias/wechat_id.

    Returns raw JSON. Cost 0.2 CNY/call, 10 sends/page.
    """
    params = urllib.parse.urlencode({
        "key": key, "ghid": ghid, "offset": offset,
    })
    url = f"{API_IP_PRO if use_ip else API_PRO}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def extract_pro(entry: dict) -> dict:
    """Map a history_by_ghid DetailInfo entry to the articles-table row shape."""
    url = normalize_url(entry.get("ContentUrl", ""))
    return {
        "title": entry.get("Title", ""),
        "url": url,
        "digest": entry.get("Digest", ""),
        "update_time": entry.get("send_time", 0),
        "original": entry.get("IsOriginal"),
        "is_deleted": "0",
        "read": entry.get("Read"),
        "zan": entry.get("Zan"),
    }


def scan_account_pro(key: str, conn: sqlite3.Connection | None, nickname: str,
                     wechat_id: str = "", dry_run: bool = False,
                     use_ip: bool = False, pages: int = 1) -> dict:
    """Scan one KOL via the Pro endpoint (history_by_ghid).

    Tries ghid/wechat_id first, falls back to nickname (Pro accepts both).
    Each page returns 10 sends; weekly scans need pages=2 to cover ~7 days
    even for active daily accounts.
    """
    out: dict = {"kol": nickname, "endpoint": "pro"}
    all_rows: list[dict] = []
    seen_urls: set[str] = set()
    total_cost = 0.0
    offset = ""
    # Pro needs a ghid; if we only have a nickname the vendor supports that too.
    ident = wechat_id or nickname
    for page in range(1, pages + 1):
        try:
            d = fetch_by_ghid(key, ident, offset=offset, use_ip=use_ip)
        except Exception as e:
            out["error"] = f"HTTP/parse: {e}"
            break
        code = d.get("code")
        out["code"] = code
        total_cost += d.get("cost") or 0.0
        out["cost"] = round(total_cost, 2)
        out["remain"] = d.get("remain_money")
        if code != 0:
            out["error"] = d.get("msg", f"code={code}")
            break
        msg_list = (d.get("MsgList") or {}).get("Msg") or []
        for send in msg_list:
            detail = ((send.get("AppMsg") or {}).get("DetailInfo") or [])
            for art in detail:
                row = extract_pro(art)
                if not row["url"]:
                    continue
                if row["url"] in seen_urls:
                    continue
                seen_urls.add(row["url"])
                all_rows.append(row)
        paging = (d.get("MsgList") or {}).get("PagingInfo") or {}
        offset = paging.get("Offset", "")
        if paging.get("IsEnd") == 1:
            break
    out["found"] = len(all_rows)
    if dry_run or conn is None:
        out["articles"] = all_rows[:5]
        return out
    new, skipped = import_articles(conn, all_rows, nickname)
    out["new"] = new
    out["skipped"] = skipped
    return out


def load_accounts(db_path: str, top: int | None = None) -> list[dict]:
    """Load (name, wechat_id) from the accounts table, optionally top-N by prior value."""
    conn = sqlite3.connect(db_path)
    try:
        if top:
            rows = conn.execute(
                "SELECT a.name, a.wechat_id FROM accounts a "
                "LEFT JOIN articles ar ON ar.account_id = a.id "
                "LEFT JOIN ingestions ig ON ig.article_id = ar.id AND ig.source='wechat' "
                "WHERE ig.status='ok' "
                "GROUP BY a.id ORDER BY COUNT(*) DESC LIMIT ?",
                (top,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT name, wechat_id FROM accounts").fetchall()
    finally:
        conn.close()
    return [{"name": r[0], "wechat_id": r[1] or ""} for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Dajiala API KOL scanner")
    ap.add_argument("--key", default=os.environ.get("DAJIALA_API_KEY", ""),
                    help="dajiala API key (or DAJIALA_API_KEY env)")
    ap.add_argument("--account", help="scan a single KOL nickname")
    ap.add_argument("--db", default="data/kol_scan.db")
    ap.add_argument("--top", type=int, help="scan top-N KOLs by prior value")
    ap.add_argument("--pages", type=int, default=1,
                    help="pages per KOL (1 page = latest 5 sends; weekly scan: 2-3)")
    ap.add_argument("--dry-run", action="store_true", help="JSON only, no DB write")
    ap.add_argument("--use-ip", action="store_true", help="use direct IP endpoint")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between KOLs")
    args = ap.parse_args()

    if not args.key:
        ap.error("missing API key: pass --key or set DAJIALA_API_KEY")

    if args.account:
        names = [{"name": args.account, "wechat_id": ""}]
    else:
        names = load_accounts(args.db, top=args.top)

    conn = None if args.dry_run else sqlite3.connect(args.db)
    results = []
    try:
        for i, acc in enumerate(names):
            name = acc["name"]
            print(f"[{i+1}/{len(names)}] {name}", flush=True)
            results.append(scan_account_pro(args.key, conn, name,
                                            wechat_id=acc["wechat_id"],
                                            dry_run=args.dry_run,
                                            use_ip=args.use_ip,
                                            pages=args.pages))
            if i < len(names) - 1:
                time.sleep(args.sleep)
    finally:
        if conn:
            conn.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
