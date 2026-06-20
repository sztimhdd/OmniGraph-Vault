"""Direct CDP-over-websocket helper for the WeChat-cookie refresh wrapper.

Designed to run on Hermes with system python3 + websocket-client ONLY — NO
project venv, NO playwright, NO MCP /mcp layer. The proven probe pattern from
RESEARCH.md Test 1 (GET /json → pick mp.weixin.qq.com target → ws connect →
Network.getCookies) is encoded here verbatim.

Three pure helper functions at module top are importable and unit-testable
WITHOUT a live browser (they do no I/O). The websocket import is deferred into
``CdpClient.connect`` so the pure helpers load even where websocket-client is
absent.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

# 5 critical auth cookies that MUST be present post-extract (RESEARCH.md Test 1:
# slave_sid, data_ticket, rand_info, bizuin, slave_user — all retrieved live).
CRITICAL_COOKIES = ("slave_sid", "data_ticket", "rand_info", "bizuin", "slave_user")


# ---------------------------------------------------------------------------
# Pure helpers (no network — unit-tested directly)
# ---------------------------------------------------------------------------

def build_cookie_string(cookies):
    """Build a single cookie line: sorted ``name=value`` joined by ``"; "``.

    Matches the kol_config.py COOKIE expectation (SKILL.md Step 3).
    """
    return "; ".join(sorted(f"{c['name']}={c['value']}" for c in cookies))


def extract_token_from_url(url):
    """Return the ``token`` query param of *url*, or None if absent.

    A subpage URL without ``token=`` returns None so the orchestrator can
    trigger a root-nav retry rather than crash (RESEARCH.md tab-drift gotcha).
    """
    qs = parse_qs(urlparse(url).query)
    values = qs.get("token")
    if not values:
        return None
    return values[0]


def critical_cookies_present(names):
    """True iff all 5 CRITICAL_COOKIES appear in *names*."""
    name_set = set(names)
    return all(c in name_set for c in CRITICAL_COOKIES)


# ---------------------------------------------------------------------------
# CDP websocket client
# ---------------------------------------------------------------------------

class NoWeChatTab(RuntimeError):
    """Raised when there is no usable page target to drive."""


class CdpClient:
    """Minimal CDP JSON-RPC client over a websocket.

    Connects to the headed Edge running with --remote-debugging-port (default
    9222, consistent with Plan 01). Provides the four CDP wrappers the
    orchestrator needs: navigate / current_url / evaluate / get_cookies.
    """

    def __init__(self, base_url="http://localhost:9222", url_filter="mp.weixin.qq.com"):
        self.base_url = base_url.rstrip("/")
        self.url_filter = url_filter
        self._ws = None
        self._msg_id = 0

    # -- liveness / connect -------------------------------------------------

    def is_alive(self):
        """True iff GET {base_url}/json/version returns HTTP 200 within 5s.

        Self-heal pre-step uses this to decide whether to relaunch Edge.
        """
        try:
            with urllib.request.urlopen(f"{self.base_url}/json/version", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def _list_targets(self):
        with urllib.request.urlopen(f"{self.base_url}/json", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def connect(self):
        """Pick the WeChat page target (fallback: first page target) and open
        the websocket. Raise NoWeChatTab if no page target exists at all."""
        import websocket  # deferred: keeps pure helpers importable without it

        targets = self._list_targets()
        page_targets = [t for t in targets if t.get("type") == "page"]
        match = next(
            (t for t in page_targets if self.url_filter in t.get("url", "")),
            None,
        )
        if match is None:
            # Fall back to the first page target so root-nav can still proceed
            # on a blank/drifted tab.
            match = page_targets[0] if page_targets else None
        if match is None:
            raise NoWeChatTab("No page target found on the CDP browser")

        ws_url = match["webSocketDebuggerUrl"]
        self._ws = websocket.create_connection(ws_url, timeout=30)
        return match

    # -- JSON-RPC core ------------------------------------------------------

    def send(self, method, params=None):
        """Send a CDP JSON-RPC command; block-read frames until the matching id."""
        if self._ws is None:
            raise NoWeChatTab("connect() must be called before send()")
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._ws.send(json.dumps(payload))

        while True:
            frame = self._ws.recv()
            if not frame:
                continue
            data = json.loads(frame)
            if data.get("id") != msg_id:
                # Skip events / other responses (CDP interleaves them).
                continue
            if "error" in data:
                raise RuntimeError(f"CDP error for {method}: {data['error']}")
            return data.get("result", {})

    def close(self):
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    # -- convenience wrappers ----------------------------------------------

    def navigate(self, url):
        """Page.navigate to *url* (used for root-nav token rebind)."""
        return self.send("Page.navigate", {"url": url})

    def current_url(self):
        """Read the current/landing URL via Page.getNavigationHistory.

        Returns entries[currentIndex].url — the redirect landing URL, NOT the
        drifted tab (RESEARCH.md gotcha)."""
        hist = self.send("Page.getNavigationHistory")
        entries = hist.get("entries", [])
        idx = hist.get("currentIndex", -1)
        if 0 <= idx < len(entries):
            return entries[idx].get("url", "")
        return ""

    def evaluate(self, expression):
        """Runtime.evaluate with returnByValue=true, awaitPromise=true.

        returnByValue avoids the terminal `***` redaction trap (SKILL.md Step 3)
        — returns the REAL value. Returns the .result.value."""
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        return result.get("result", {}).get("value")

    def get_cookies(self):
        """Network.getCookies scoped to mp.weixin.qq.com.

        Always returns the complete cookie set regardless of the current tab URL
        (RESEARCH.md Test 1: 15 cookies, all 5 critical present)."""
        result = self.send(
            "Network.getCookies",
            {"urls": ["https://mp.weixin.qq.com"]},
        )
        return result.get("cookies", [])
