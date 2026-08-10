#!/usr/bin/env python3
"""sogou_kol_scan MVP — discover recent WeChat articles for a KOL via Sogou Weixin public index.

Pipeline: sogou type=2 search -> parse results -> exact publisher filter -> dedupe
        -> (optional) resolve sogou /link to real mp.weixin.qq.com/s?src=11&timestamp&ver&signature

No login needed. Free-path replacement for the dead appmsgpublish cross-account list API.

Usage:
    python3 scripts/sogou_kol_scan.py "阮一峰的网络日志" [--resolve] [--pages N]
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request

# Optional CDP fallback — the last weapon against any anti-bot wall.
# Requires: websocket-client (`pip install websocket-client`) and a reachable
# Edge/Chrome CDP endpoint (default http://127.0.0.1:9223).
try:
    import websocket  # noqa: F401
    _HAS_WS = True
except ImportError:
    _HAS_WS = False

CDP_HTTP = "http://127.0.0.1:9223"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def clean(s: str) -> str:
    """Strip em/highlight tags and whitespace from a search snippet."""
    s = re.sub(r"<[^>]+>", "", s or "")
    return s.strip()


def make_opener():
    """Opener with cookie jar + sogou-ish headers. Session is REQUIRED for /link resolution."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,*/*;q=0.8"),
        ("Accept-Language", "zh-CN,zh;q=0.9"),
        ("Referer", "https://weixin.sogou.com/"),
    ]
    return op


# ── CDP fallback (the last weapon) ─────────────────────────────────────────

def cdp_new_tab(url: str) -> str:
    """Open a new Edge/Chrome tab via CDP HTTP /json/new. Returns targetId."""
    if not _HAS_WS:
        raise RuntimeError("websocket-client not installed; cannot use CDP fallback")
    # Modern Chrome/Edge requires PUT for /json/new
    req = urllib.request.Request(CDP_HTTP + "/json/new?" + urllib.parse.quote(url, safe=""),
                                 method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        info = json.loads(r.read().decode())
    return info["id"]


def cdp_close_tab(target_id: str) -> None:
    try:
        req = urllib.request.Request(CDP_HTTP + "/json/close/" + target_id, method="PUT")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def cdp_eval(target_id: str, expression: str, timeout: int = 20):
    """Run Runtime.evaluate on a tab via its websocket debugger URL."""
    with urllib.request.urlopen(CDP_HTTP + "/json", timeout=10) as r:
        targets = json.loads(r.read().decode())
    ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t["id"] == target_id)
    ws = websocket.create_connection(ws_url, timeout=timeout)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expression, "returnByValue": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError("CDP eval error: %s" % msg["error"])
                return msg["result"].get("result", {}).get("value")
    finally:
        ws.close()


def cdp_fetch_search(query: str, page: int = 1, wait: float = 3.0) -> str:
    """Navigate a real browser to the sogou search URL and return rendered HTML."""
    url = ("https://weixin.sogou.com/weixin?type=2&query="
           + urllib.parse.quote(query)
           + (f"&page={page}" if page > 1 else ""))
    tid = cdp_new_tab("about:blank")
    try:
        cdp_eval(tid, "location.href = %r; 'nav'" % url)
        time.sleep(wait)
        return cdp_eval(tid, "document.documentElement.outerHTML") or ""
    finally:
        cdp_close_tab(tid)


def cdp_resolve_link(link: str, wait: float = 2.5) -> str:
    """Let a real browser follow sogou /link (JS + antispider) and return the final URL."""
    full = "https://weixin.sogou.com" + link
    tid = cdp_new_tab("about:blank")
    try:
        cdp_eval(tid, "location.href = %r; 'nav'" % full)
        time.sleep(wait)
        return cdp_eval(tid, "location.href") or full
    finally:
        cdp_close_tab(tid)


def fetch_search(op, query: str, page: int = 1, timeout: int = 15) -> str:
    url = ("https://weixin.sogou.com/weixin?type=2&query="
           + urllib.parse.quote(query)
           + (f"&page={page}" if page > 1 else ""))
    with op.open(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def parse_results(html: str) -> list[dict]:
    """Extract article rows from sogou weixin search page."""
    rows = re.findall(
        r'<li[^>]*id="sogou_vr_11002601_box_\d+"[^>]*>(.*?)</li>',
        html, re.S)
    out = []
    for li in rows:
        t = re.search(r"<h3>.*?<a[^>]*>(.*?)</a>", li, re.S)
        link = re.search(r'<h3>.*?<a[^>]*href="([^"]+)"', li, re.S)
        acct = re.search(r"class=\"[^\"]*all-time-y2[^\"]*\"[^>]*>(.*?)</span>",
                         li, re.S)
        ts = re.search(r"timeConvert\('(\d+)'\)", li)
        if not (t and link):
            continue
        out.append({
            "title": clean(t.group(1)),
            "account": clean(acct.group(1)) if acct else "",
            "ts": int(ts.group(1)) if ts else 0,
            "sogou_link": link.group(1),
        })
    return out


def resolve_link(op, link: str, timeout: int = 15) -> str:
    """Follow sogou /link redirect page, reassemble the JS-concatenated target URL.

    Sogou's link page builds the target with `url += 'fragment'` lines then
    window.location.replace(url). We read the fragments and join them — no JS
    execution. Returns the original link URL on failure (caller checks prefix).
    """
    if link.startswith("http"):
        return link
    full = "https://weixin.sogou.com" + link
    with op.open(full, timeout=timeout) as r:
        body = r.read().decode("utf-8", "ignore")
    frags = re.findall(r"url\s*\+=\s*'([^']*)'", body)
    if not frags:
        return full
    target = "".join(frags)
    return target if target.startswith("http") else full


def extract_article_meta(op, mp_url: str, timeout: int = 15) -> dict:
    """Open a mp.weixin.qq.com/s article page and extract stable identity metadata.

    Returns {biz, mid, idx, ct, nickname} from the page's inline JS variables.
    These are the stable dedup/attribution keys (URL signature params rotate,
    biz+mid+idx do not). Empty values mean the page didn't expose them.
    """
    req = urllib.request.Request(mp_url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://weixin.sogou.com/",
    })
    with op.open(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "ignore")
    meta = {}
    for var in ("biz", "mid", "idx", "ct", "nickname"):
        m = re.search(r'var\s+' + var + r'\s*=\s*"([^"]*)"', html)
        meta[var] = m.group(1) if m else ""
    return meta


def scan_kol(query: str, max_pages: int = 1, resolve: bool = False,
             exact_account: bool = True, use_cdp: bool = False,
             expect_biz: str = "", verify: bool = False,
             days: int = 0, account_name: str = "") -> dict:
    """Search sogou; keep rows whose publisher matches; optionally resolve links.

    query: the sogou search keyword (can differ from the account name).
    account_name: the expected publisher name for exact_account filtering.
                  Defaults to query (backward compat: search-by-account-name).

    use_cdp=True forces the real-browser path (last weapon against antispider).
    Otherwise the HTTP path is tried first and auto-falls back to CDP when the
    page looks like an antispider/empty wall.

    expect_biz: the KOL's real fakeid from the registry. When verify=True, each
    resolved article's page biz is compared; mismatches are marked invalid
    (usually a referencing account, not the target KOL itself).

    days: keep only articles published within the last N days (0 = no filter).
    Uses the per-row publish timestamp from the search page — zero extra requests.
    """
    op = make_opener()
    seen = set()
    hits = []
    pub_name = account_name or query
    cutoff = int(time.time()) - days * 86400 if days > 0 else 0
    for page in range(1, max_pages + 1):
        if use_cdp:
            html = cdp_fetch_search(query, page=page)
        else:
            html = fetch_search(op, query, page=page)
            if _looks_blocked(html):
                if not _HAS_WS:
                    raise RuntimeError("Sogou blocked HTTP path and websocket-client "
                                       "is missing — install it or pass --cdp")
                html = cdp_fetch_search(query, page=page)
        if "暂无" in html and "相关" in html:
            break
        rows = parse_results(html)
        if not rows:
            break
        for r in rows:
            if exact_account and pub_name not in r["account"]:
                continue
            if r["title"] in seen:
                continue
            if cutoff and r["ts"] and r["ts"] < cutoff:
                continue
            seen.add(r["title"])
            if resolve:
                if use_cdp:
                    r["url"] = cdp_resolve_link(r["sogou_link"])
                else:
                    r["url"] = resolve_link(op, r["sogou_link"])
                    if r["url"].startswith("https://weixin.sogou.com/link"):
                        r["url"] = cdp_resolve_link(r["sogou_link"])
            else:
                r["url"] = ""
            if verify and r["url"] and r["url"].startswith("http"):
                try:
                    meta = extract_article_meta(op, r["url"])
                    r["meta"] = meta
                    r["verified"] = bool(expect_biz) and (meta.get("biz") == expect_biz)
                except Exception as e:
                    r["meta"] = {}
                    r["verified"] = False
                    r["verify_error"] = str(e)
            hits.append(r)
        if len(rows) < 10:
            break
        time.sleep(1.5)  # polite crawl, avoid sogou captcha
    return {"kol": query, "hits": hits, "total": len(hits)}


def _looks_blocked(html: str) -> bool:
    """Heuristic: sogou returned an antispider/empty wall instead of results."""
    return ("antispider" in html.lower()
            or ("<title>搜狗搜索</title>" in html and "news-list" not in html))


if __name__ == "__main__":
    args = sys.argv[1:]
    resolve = "--resolve" in args
    use_cdp = "--cdp" in args
    verify = "--verify" in args
    days = 0
    if "--days" in args:
        days = int(args[args.index("--days") + 1])
    names = [a for a in args if not a.startswith("--")] or ["叶小钗"]
    results = []
    for n in names:
        try:
            results.append(scan_kol(n, resolve=resolve, use_cdp=use_cdp,
                                    verify=verify, days=days))
        except Exception as e:
            results.append({"kol": n, "error": str(e)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
