"""
test_mcp_approaches.py — Test 3 approaches to beat the 5s heartbeat limit.

Approach A: browser_navigate (standard tool, fails >5s pages)
Approach B: browser_run_code with domcontentloaded (single atomic call)
Approach C: browser_run_code with full content extraction (production-ready)

Tests against: Google, Wikipedia, Baidu, and 5 WeChat articles.
"""
import requests
import json
import sys
import re
import time

sys.stdout.reconfigure(encoding="utf-8")

MCP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://ohca.ddns.net:58931/mcp"
HEADERS_BASE = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

TEST_URLS = [
    ("Google", "https://www.google.com"),
    ("Wikipedia", "https://en.wikipedia.org/wiki/Main_Page"),
    ("Baidu", "https://www.baidu.com"),
    ("WeChat-1", "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"),
    ("WeChat-2", "https://mp.weixin.qq.com/s/8SGRMIyspvUcLMcmeDa2Mw"),
    ("WeChat-3", "https://mp.weixin.qq.com/s/4bE4AZPAAYVdtQIlf9hP9A"),
    ("WeChat-4", "https://mp.weixin.qq.com/s/qzacaj9XHfq9etTOBt8r5Q"),
    ("WeChat-5", "https://mp.weixin.qq.com/s/oGXo8psXgP6A24mmKbTGIw"),
]


class MCPClient:
    def __init__(self, url):
        self.url = url
        self.sid = None
        self.mid = 0

    def _post(self, method, params=None, timeout=30):
        self.mid += 1
        h = dict(HEADERS_BASE)
        if self.sid:
            h["mcp-session-id"] = self.sid
        p = {"jsonrpc": "2.0", "id": self.mid, "method": method}
        if params:
            p["params"] = params
        resp = requests.post(self.url, json=p, headers=h, timeout=timeout)
        resp.encoding = "utf-8"
        if "mcp-session-id" in resp.headers:
            self.sid = resp.headers["mcp-session-id"]
        return resp

    def init(self):
        self.sid = None
        self.mid = 0
        resp = self._post("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcp-test", "version": "1.0"},
        })
        if resp.status_code != 200:
            return False
        # send notification
        h = dict(HEADERS_BASE)
        if self.sid:
            h["mcp-session-id"] = self.sid
        requests.post(self.url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h, timeout=5)
        return True

    def tool(self, name, arguments=None, timeout=30):
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        start = time.time()
        resp = self._post("tools/call", params, timeout=timeout)
        elapsed = time.time() - start
        if resp.status_code != 200 or len(resp.text) == 0:
            return None, elapsed
        for m in re.finditer(r"data: ({.+})", resp.text, re.DOTALL):
            try:
                obj = json.loads(m.group(1))
                if "result" in obj:
                    return obj["result"], elapsed
            except json.JSONDecodeError:
                pass
        return None, elapsed

    def text(self, result):
        if not result or "content" not in result:
            return ""
        return "".join(c["text"] for c in result["content"] if c.get("type") == "text")

    def extract_eval(self, t):
        if "### Result\n" in t:
            return t.split("### Result\n")[1].split("\n### Ran")[0].strip()
        return t


def test_approach_a(client, name, url):
    """Approach A: browser_navigate + browser_evaluate (two separate calls)"""
    r, t1 = client.tool("browser_navigate", {"url": url})
    nav = client.text(r)
    if not nav:
        return {"approach": "A", "name": name, "status": "FAIL", "reason": "nav empty", "time": t1}

    r, t2 = client.tool("browser_evaluate", {"function": "() => document.title"})
    if not r:
        return {"approach": "A", "name": name, "status": "FAIL", "reason": "session dead after nav", "time": t1 + t2}

    title = client.extract_eval(client.text(r))
    return {"approach": "A", "name": name, "status": "OK", "title": title, "time": t1 + t2}


def parse_run_code_json(text_result):
    """Parse double-JSON-encoded result from browser_run_code."""
    if "### Result\n" not in text_result:
        return None
    raw = text_result.split("### Result\n")[1].split("\n### Ran")[0].strip()
    # Result is double-encoded: json.loads to unwrap string, then json.loads to parse object
    try:
        unwrapped = json.loads(raw)  # removes outer quotes and unescapes
        if isinstance(unwrapped, str):
            return json.loads(unwrapped)  # parse inner JSON
        return unwrapped  # already parsed
    except (json.JSONDecodeError, TypeError):
        return None


def test_approach_b(client, name, url):
    """Approach B: browser_run_code with domcontentloaded (atomic, fast)"""
    code = f'''async (page) => {{
  await page.goto('{url}', {{waitUntil: 'domcontentloaded', timeout: 4500}});
  var title = await page.title();
  var bodyLen = await page.evaluate(() => document.body.innerHTML.length);
  return JSON.stringify({{title, bodyLen}});
}}'''
    r, elapsed = client.tool("browser_run_code_unsafe", {"code": code}, timeout=15)
    t = client.text(r) if r else ""
    data = parse_run_code_json(t)
    if data:
        return {"approach": "B", "name": name, "status": "OK", "title": data.get("title"), "bodyLen": data.get("bodyLen"), "time": elapsed}
    if "Error" in t:
        return {"approach": "B", "name": name, "status": "FAIL", "reason": t[:150], "time": elapsed}
    return {"approach": "B", "name": name, "status": "FAIL", "reason": "empty/unparseable", "time": elapsed}


def test_approach_c(client, name, url):
    """Approach C: browser_run_code full extraction (production scrape)"""
    code = f'''async (page) => {{
  await page.goto('{url}', {{waitUntil: 'domcontentloaded', timeout: 4500}});
  var title = await page.title();
  var pubTime = await page.evaluate(() => {{
    var el = document.querySelector('#publish_time');
    return el ? el.innerText : '';
  }});
  var contentEl = await page.evaluate(() => {{
    var el = document.querySelector('#js_content');
    return el ? {{found: true, len: el.innerHTML.length}} : {{found: false, len: document.body.innerHTML.length}};
  }});
  var textSnippet = await page.evaluate(() => {{
    var el = document.querySelector('#js_content') || document.body;
    return el.innerText.substring(0, 300);
  }});
  var imgs = await page.evaluate(() => {{
    var all = document.querySelectorAll('#js_content img, img[data-src]');
    return {{count: all.length, urls: Array.from(all).slice(0, 5).map(i => i.getAttribute('data-src') || i.src).filter(Boolean)}};
  }});
  return JSON.stringify({{title, pubTime, content: contentEl, textSnippet, imgs}});
}}'''
    r, elapsed = client.tool("browser_run_code_unsafe", {"code": code}, timeout=15)
    t = client.text(r) if r else ""
    data = parse_run_code_json(t)
    if data:
        return {
                "approach": "C", "name": name, "status": "OK",
                "title": data.get("title"),
                "pubTime": data.get("pubTime"),
                "contentFound": data.get("content", {}).get("found"),
                "contentLen": data.get("content", {}).get("len"),
                "imgCount": data.get("imgs", {}).get("count"),
                "textSnippet": data.get("textSnippet", "")[:150],
                "time": elapsed,
            }
    if "Error" in t:
        return {"approach": "C", "name": name, "status": "FAIL", "reason": t[:150], "time": elapsed}
    return {"approach": "C", "name": name, "status": "FAIL", "reason": "empty", "time": elapsed}


# ============================================================
print("=" * 70)
print("MCP APPROACH COMPARISON TEST")
print(f"Server: {MCP_URL}")
print("=" * 70)

client = MCPClient(MCP_URL)

# ---------- Approach A: browser_navigate ----------
print("\n" + "=" * 70)
print("APPROACH A: browser_navigate + browser_evaluate (2 calls)")
print("=" * 70)
results_a = []
for name, url in TEST_URLS:
    if not client.init():
        print(f"  {name}: INIT FAILED")
        results_a.append({"approach": "A", "name": name, "status": "INIT_FAIL"})
        continue
    r = test_approach_a(client, name, url)
    status = r["status"]
    t = r.get("time", 0)
    title = r.get("title", r.get("reason", ""))[:50]
    print(f"  {name:12s}: {status:4s} | {t:.1f}s | {title}")
    results_a.append(r)

# ---------- Approach B: browser_run_code (fast) ----------
print("\n" + "=" * 70)
print("APPROACH B: browser_run_code + domcontentloaded (atomic, fast)")
print("=" * 70)
results_b = []
for name, url in TEST_URLS:
    if not client.init():
        print(f"  {name}: INIT FAILED")
        results_b.append({"approach": "B", "name": name, "status": "INIT_FAIL"})
        continue
    r = test_approach_b(client, name, url)
    status = r["status"]
    t = r.get("time", 0)
    title = r.get("title", r.get("reason", ""))[:50]
    blen = r.get("bodyLen", "")
    print(f"  {name:12s}: {status:4s} | {t:.1f}s | {title} | body={blen}")
    results_b.append(r)

# ---------- Approach C: browser_run_code (full extract) ----------
print("\n" + "=" * 70)
print("APPROACH C: browser_run_code + full extraction (production)")
print("=" * 70)
results_c = []
for name, url in TEST_URLS:
    if not client.init():
        print(f"  {name}: INIT FAILED")
        results_c.append({"approach": "C", "name": name, "status": "INIT_FAIL"})
        continue
    r = test_approach_c(client, name, url)
    status = r["status"]
    t = r.get("time", 0)
    title = r.get("title", r.get("reason", ""))[:40]
    clen = r.get("contentLen", "")
    imgs = r.get("imgCount", "")
    snippet = r.get("textSnippet", "")[:60]
    print(f"  {name:12s}: {status:4s} | {t:.1f}s | {title}")
    if status == "OK":
        print(f"  {'':12s}  content={clen} chars | imgs={imgs} | {snippet}")
    results_c.append(r)

# ---------- Summary ----------
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'Site':12s} | {'A (navigate)':14s} | {'B (run_code)':14s} | {'C (full)':14s}")
print("-" * 70)
for i, (name, _) in enumerate(TEST_URLS):
    a = results_a[i]["status"] if i < len(results_a) else "?"
    b = results_b[i]["status"] if i < len(results_b) else "?"
    c = results_c[i]["status"] if i < len(results_c) else "?"
    ta = f'{results_a[i].get("time",0):.1f}s' if i < len(results_a) else ""
    tb = f'{results_b[i].get("time",0):.1f}s' if i < len(results_b) else ""
    tc = f'{results_c[i].get("time",0):.1f}s' if i < len(results_c) else ""
    print(f"  {name:12s} | {a:4s} {ta:>6s}   | {b:4s} {tb:>6s}   | {c:4s} {tc:>6s}")
