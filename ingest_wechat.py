import os
import sys
import json
import hashlib
import requests
import re
import time
import sqlite3
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import nest_asyncio
import fitz  # PyMuPDF
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import html2text
from google import genai
import numpy as np
import cognee_wrapper
from apify_client import ApifyClient

# For LightRAG
try:
    from lightrag.lightrag import LightRAG, QueryParam
    from lightrag.llm.gemini import gemini_model_complete, gemini_embed
    from lightrag.utils import wrap_embedding_func_with_attrs
except ImportError as e:
    print(f"Import error: {e}")
    print("Python path:", sys.path)
    sys.exit(1)

nest_asyncio.apply()

from config import RAG_WORKING_DIR, BASE_IMAGE_DIR, load_env, CDP_URL, ENTITY_BUFFER_DIR, ENRICHMENT_MIN_LENGTH, INGEST_LLM_MODEL
load_env()

from image_pipeline import (
    download_images, localize_markdown, describe_images, save_markdown_with_images,
)


def _is_mcp_endpoint(url: str) -> bool:
    return bool(url) and url.rstrip("/").endswith("/mcp")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

DB_PATH = Path(__file__).parent / "data" / "kol_scan.db"

# Phase 4: ensure SQLite has the enriched + enrichment_id columns on
# every deploy. init_db() is idempotent (uses _ensure_column ALTER TABLE
# guards). Guarded by DB_PATH existence so fresh installs (no DB at all)
# don't fail here — those get init_db() called later via batch_scan_kol.
if DB_PATH.exists():
    try:
        from batch_scan_kol import init_db as _kol_init_db
        _kol_init_db(DB_PATH)
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Phase 4 SQLite auto-migrate skipped: %s", _e
        )


def _persist_entities_to_sqlite(url: str, entities: list[str]) -> None:
    """Write extracted entities to kol_scan.db if it exists. No-op otherwise."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        article = conn.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()
        if article:
            article_id = article[0]
            for entity in entities:
                conn.execute(
                    "INSERT OR IGNORE INTO extracted_entities(article_id, entity_name) VALUES (?, ?)",
                    (article_id, entity.strip()),
                )
            conn.commit()
    except Exception:
        pass  # entity_buffer files remain the primary path
    finally:
        conn.close()


os.makedirs(BASE_IMAGE_DIR, exist_ok=True)
os.makedirs(RAG_WORKING_DIR, exist_ok=True)

# Force standard Gemini API mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# --- LightRAG Setup ---
# --- Rate Limiting for Gemini Free Tier ---
_llm_lock = asyncio.Lock()
_last_llm_time = 0.0
_LLM_MIN_INTERVAL = 15.0  # 4 RPM, safe below 5 RPM free tier limit


async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    global _last_llm_time
    async with _llm_lock:
        now = time.time()
        elapsed = now - _last_llm_time
        if _last_llm_time > 0 and elapsed < _LLM_MIN_INTERVAL:
            wait = _LLM_MIN_INTERVAL - elapsed
            await asyncio.sleep(wait)
        _last_llm_time = time.time()
        return await gemini_model_complete(
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=GEMINI_API_KEY,
            model_name=INGEST_LLM_MODEL,
            **kwargs,
        )

@wrap_embedding_func_with_attrs(
    embedding_dim=768,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001",
        embedding_dim=768,
    )

async def get_rag():
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name=INGEST_LLM_MODEL,
        # Throttle concurrency to fit Gemini free-tier quotas:
        # gemini-embedding-*: 100 RPM → serialize embeddings with max_async=1
        # flash/flash-lite LLM: 250/20 RPD → cap LLM concurrency at 2
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag

# --- Scraping Methods ---

# Rotating UA pool — avoids detection by varying WeChat client fingerprints
_UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.34(0x16082222) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.42(0x18042a23) NetType/4G Language/zh_CN",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.144 Mobile Safari/537.36 MicroMessenger/8.0.45(0x28004534) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.44(0x18004428) NetType/5G Language/zh_CN",
    "Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/118.0.5993.111 Mobile Safari/537.36 MicroMessenger/8.0.41(0x28004135) NetType/WIFI Language/zh_CN",
]
_ua_index = 0


def _next_ua() -> str:
    global _ua_index
    ua = _UA_POOL[_ua_index % len(_UA_POOL)]
    _ua_index += 1
    return ua


# Random cooldown between UA requests to avoid WeChat frequency bans
_last_ua_request: float = 0.0
_UA_MIN_INTERVAL = 3.0   # minimum seconds
_UA_MAX_INTERVAL = 8.0   # maximum seconds
_UA_SESSION_LIMIT = 40    # requests before mandatory long cooldown
_ua_session_count = 0


def _ua_cooldown():
    """Enforce random delay between UA-scraped WeChat requests."""
    global _last_ua_request, _ua_session_count
    now = __import__("time").time()
    elapsed = now - _last_ua_request
    
    if _ua_session_count >= _UA_SESSION_LIMIT:
        cooldown = 60 + __import__("random").uniform(0, 30)
        print(f"UA session limit ({_UA_SESSION_LIMIT}) reached. Cooling down {cooldown:.0f}s...")
        __import__("time").sleep(cooldown)
        _ua_session_count = 0
    elif elapsed < _UA_MIN_INTERVAL:
        delay = __import__("random").uniform(_UA_MIN_INTERVAL, _UA_MAX_INTERVAL)
        __import__("time").sleep(delay)
    
    _last_ua_request = __import__("time").time()
    _ua_session_count += 1


async def scrape_wechat_ua(url: str):
    """Primary method: UA spoofing with MicroMessenger token.
    
    WeChat's anti-scraping checks for 'MicroMessenger' in User-Agent.
    If found, serves full HTML. No cookies, no login, no proxy needed.
    Parses only the article content div (js_content) to avoid loading
    3MB+ of JavaScript overhead.
    """
    import re as _re
    
    try:
        _ua_cooldown()
        ua = _next_ua()
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: __import__("requests").get(
                url,
                headers={"User-Agent": ua},
                timeout=15,
            ),
        )
        if resp.status_code != 200:
            print(f"UA scrape: HTTP {resp.status_code}")
            return None

        html = resp.text
        content_len = len(html)
        print(f"UA scrape: HTTP 200, {content_len // 1024}KB")

        # --- Parse title from og:title (fast, no full DOM parse) ---
        title = ""
        og_match = _re.search(r'property="og:title"[^>]*content="([^"]+)"', html)
        if og_match:
            title = og_match.group(1)
        else:
            t_match = _re.search(r"<title>([^<]+)</title>", html)
            if t_match:
                title = t_match.group(1)

        # --- Parse publish_time: var ct unix timestamp (primary), fallback to #publish_time element ---
        publish_time = ""
        ct_match = _re.search(r'var\s+ct\s*=\s*"(\d+)"', html)
        if ct_match:
            publish_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ct_match.group(1))))
        else:
            pt_match = _re.search(r'id="publish_time"[^>]*>([^<]+)<', html)
            if pt_match:
                publish_time = pt_match.group(1).strip()

        # --- Extract article body (1-4KB text, not 3MB JS) ---
        content_html = ""
        for div_id in ["js_content", "img-content"]:
            start = html.find(f'id="{div_id}"')
            if start < 0:
                continue
            start = html.rfind("<", start - 100, start)  # rewind to opening <
            # Find matching close — look for next </div> after content ends
            depth = 0
            i = start
            while i < len(html):
                if html[i : i + 4] == "<div":
                    depth += 1
                elif html[i : i + 5] == "</div":
                    depth -= 1
                    if depth == 0:
                        content_html = html[start : i + 6]
                        break
                i += 1
            if content_html:
                break

        if not content_html:
            print("UA scrape: article body not found in HTML")
            return None

        # --- Extract images ---
        img_urls: list[str] = []
        for m in _re.finditer(r'data-src="(https?://mmbiz[^"]+)"', html):
            img_urls.append(m.group(1))

        print(f"UA scrape: title='{title[:40]}', body={len(content_html)}B, {len(img_urls)} imgs, publish_time='{publish_time}'")
        return {
            "title": title,
            "content_html": content_html,
            "img_urls": img_urls,
            "url": url,
            "publish_time": publish_time,
            "method": "ua",
        }
    except Exception as e:
        print(f"UA scrape failed: {e}")
        return None


async def scrape_wechat_apify(url):
    """Try scraping with Apify WeChat actor."""
    if not APIFY_TOKEN:
        print("Apify Token not found, skipping Apify.")
        return None
        
    try:
        client = ApifyClient(APIFY_TOKEN)
        run_input = {
            "startUrls": [{"url": url}],
            "crawlerConfig": {
                "magic": True,
                "wait_until": "domcontentloaded",
                "simulate_user": True,
            }
        }
        # 增加 ingestion 超时时间，并在中间步骤添加打印以跟踪进度
        print(f"Starting Apify actor for {url}...")
        loop = asyncio.get_event_loop()
        # 使用较长的 timeout
        future = loop.run_in_executor(None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input))
        run = await asyncio.wait_for(future, timeout=300)
        print("Apify run finished.")
        
        results = [item for item in client.dataset(run["defaultDatasetId"]).iterate_items()]
        if results:
            item = results[0]
            return {
                "title": item.get("title", ""),
                "markdown": item.get("markdown", item.get("data", "")),
                "publish_time": item.get("publish_time", ""),
                "url": url,
                "method": "apify"
            }
    except Exception as e:
        print(f"Apify scraping failed: {e}")
    return None

async def scrape_wechat_mcp(url):
    """Fallback scraping via remote Playwright MCP server.

    Uses browser_run_code with async (page) => {...} to do navigate + extract
    in a single atomic MCP call. This avoids the 5-second heartbeat timeout
    that kills sessions between separate browser_navigate/browser_evaluate calls.
    """
    import json as _json

    mcp_url = CDP_URL.rstrip("/")
    session_id = None
    msg_id = 0
    _headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

    def _post(method, params=None, timeout=30):
        nonlocal session_id, msg_id
        msg_id += 1
        h = dict(_headers)
        if session_id:
            h["mcp-session-id"] = session_id
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params:
            payload["params"] = params
        resp = requests.post(mcp_url, json=payload, headers=h, timeout=timeout)
        resp.encoding = "utf-8"
        if "mcp-session-id" in resp.headers:
            session_id = resp.headers["mcp-session-id"]
        if resp.status_code != 200 or len(resp.text) == 0:
            return None
        for m in re.finditer(r"data: ({.+})", resp.text, re.DOTALL):
            try:
                obj = _json.loads(m.group(1))
                if "result" in obj:
                    return obj["result"]
                if "error" in obj:
                    raise RuntimeError(f"MCP error: {obj['error']}")
            except _json.JSONDecodeError:
                pass
        return None

    def _text(result):
        if not result or "content" not in result:
            return ""
        return "".join(c["text"] for c in result["content"] if c.get("type") == "text")

    def _parse_run_code_json(text_result):
        if "### Result\n" not in text_result:
            return None
        raw = text_result.split("### Result\n")[1].split("\n### Ran")[0].strip()
        try:
            unwrapped = _json.loads(raw)
            if isinstance(unwrapped, str):
                return _json.loads(unwrapped)
            return unwrapped
        except (_json.JSONDecodeError, TypeError):
            return None

    js_code = f"""async (page) => {{
  await page.goto('{url}', {{waitUntil: 'domcontentloaded', timeout: 4500}});
  var title = await page.title();
  var pubTime = await page.evaluate(() => {{
    var el = document.querySelector('#publish_time');
    return el ? el.innerText : '';
  }});
  var contentHtml = await page.evaluate(() => {{
    var el = document.querySelector('#js_content');
    return el ? el.innerHTML : '';
  }});
  var imgCount = await page.evaluate(() => {{
    return document.querySelectorAll('#js_content img, img[data-src]').length;
  }});
  return JSON.stringify({{title: title, pubTime: pubTime, contentLen: contentHtml.length, contentHtml: contentHtml, imgCount: imgCount}});
}}"""

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Connecting to MCP at {mcp_url}... (attempt {attempt}/{max_attempts})")
            session_id = None
            msg_id = 0
            _post("initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "omnigraph-ingest", "version": "1.0"}
            })
            h = dict(_headers)
            if session_id:
                h["mcp-session-id"] = session_id
            requests.post(mcp_url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h, timeout=5)

            print(f"Navigating and extracting {url} (atomic browser_run_code)...")
            result = _post("tools/call", {"name": "browser_run_code", "arguments": {"code": js_code}}, timeout=15)
            text_out = _text(result)

            if "Error" in text_out and "Timeout" in text_out and attempt < max_attempts:
                print(f"Timeout on attempt {attempt}, retrying...")
                continue

            data = _parse_run_code_json(text_out)
            if not data:
                if "Error" in text_out:
                    print(f"MCP browser_run_code error: {text_out[:200]}")
                else:
                    print(f"MCP returned unparseable result ({len(text_out)} chars)")
                if attempt < max_attempts:
                    continue
                return None

            content_html = data.get("contentHtml", "")
            if len(content_html) < 100:
                print(f"MCP returned too little content ({len(content_html)} chars)")
                if attempt < max_attempts:
                    continue
                return None

            title = data.get("title", "Untitled")
            publish_time = data.get("pubTime", "")
            img_count = data.get("imgCount", 0)
            print(f"MCP scraped: title='{title[:50]}', content={len(content_html)} chars, images={img_count}")
            return {
                "title": title,
                "content_html": content_html,
                "publish_time": publish_time,
                "url": url,
                "method": "mcp"
            }
        except Exception as e:
            print(f"MCP scraping failed (attempt {attempt}): {e}")
            if attempt < max_attempts:
                continue
            return None
    return None


async def scrape_wechat_cdp(url):
    """Fallback scraping via CDP."""
    async with async_playwright() as p:
        print(f"Connecting to CDP at {CDP_URL}...")
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"Failed to connect to CDP: {e}")
            return None
            
        context = browser.contexts[0]
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="networkidle")
        
        # Scroll to bottom to ensure all images are loaded
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)
        
        title = await page.title()
        try:
            content_html = await page.inner_html("#js_content")
        except:
            print("Warning: #js_content not found, grabbing body.")
            content_html = await page.inner_html("body")
        
        publish_time = ""
        try:
            publish_time = await page.inner_text("#publish_time")
        except Exception as e:
            print(f"Warning: Could not extract publish_time: {e}")
        
        await page.close()
        # Don't close browser, it's shared with other tools
        
        return {
            "title": title,
            "content_html": content_html,
            "publish_time": publish_time,
            "url": url,
            "method": "cdp"
        }

def process_content(html):
    soup = BeautifulSoup(html, 'html.parser')
    images = []
    for img in soup.find_all('img'):
        src = img.get('data-src') or img.get('src')
        if src and src.startswith('http'):
            images.append(src)
    
    h = html2text.HTML2Text()
    h.ignore_links = False
    markdown = h.handle(html)
    
    return markdown, images


async def extract_entities(text):
    """Extract entities using Gemini for canonicalization."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"Extract a comma-separated list of key entities (people, organizations, technical concepts, products) from the following text:\n\n{text[:5000]}"
        response = client.models.generate_content(
            model=INGEST_LLM_MODEL,
            contents=[prompt]
        )
        entities = [e.strip() for e in response.text.split(',')]
        return [e for e in entities if e]
    except Exception as e:
        print(f"Warning: Entity extraction failed: {e}")
        return []

# --- Main Logic ---
async def ingest_article(url):
    print(f"--- Starting Ingestion: {url} ---")
    
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = os.path.join(BASE_IMAGE_DIR, article_hash)
    os.makedirs(article_dir, exist_ok=True)
    
    # Cache check: if already scraped and stored, skip HTTP entirely
    cache_content = os.path.join(article_dir, "final_content.md")
    if os.path.exists(cache_content):
        print(f"📦 Cached article found → reusing {cache_content}")
        with open(cache_content, encoding='utf-8') as f:
            full_content = f.read()
        
        # Load cached images metadata
        processed_images = []
        cache_meta = os.path.join(article_dir, "metadata.json")
        if os.path.exists(cache_meta):
            try:
                meta = json.load(open(cache_meta))
                processed_images = meta.get("images", [])
                title = meta.get("title", "")
            except:
                title = ""
        
        # Skip scrape + image download, jump to entity extraction
        raw_entities = await extract_entities(full_content)
        buffer_data = {'url': url, 'raw_entities': raw_entities, 'timestamp': time.time()}
        os.makedirs(ENTITY_BUFFER_DIR, exist_ok=True)
        with open(os.path.join(ENTITY_BUFFER_DIR, f'{article_hash}_entities.json'), 'w') as f:
            json.dump(buffer_data, f)
        print(f'Buffered {len(raw_entities)} entities (from cache).')
        _persist_entities_to_sqlite(url, raw_entities)
        
        try:
            rag = await get_rag()
            await rag.ainsert(full_content)
        except Exception as e:
            print(f"LightRAG insert failed: {e}")
        
        print(f"✅ Cached article processed (scrape skipped)")
        return
    
    print("Starting ingestion process...")
    
    # 1. UA spoofing (primary — fast, free, reliable)
    article_data = await scrape_wechat_ua(url)
    
    if not article_data:
        # 2. Apify (backup)
        article_data = await scrape_wechat_apify(url)
        
        # Check if Apify returned a verification/login page
        if article_data:
            content = article_data.get("markdown", "") + article_data.get("title", "")
            is_short = len(content) < 500
            has_block_keywords = any(kw in content for kw in ["环境异常", "请完成验证", "请登录"])
            if is_short and has_block_keywords:
                print(f"Apify returned verification/login page ({len(content)} chars), triggering fallback...")
                article_data = None
    
    # 3. CDP fallback (last resort)
    if not article_data:
        if _is_mcp_endpoint(CDP_URL):
            print("UA & Apify failed. Falling back to remote Playwright MCP...")
            article_data = await scrape_wechat_mcp(url)
        else:
            print("UA & Apify failed. Falling back to local CDP...")
            article_data = await scrape_wechat_cdp(url)

    if not article_data:
        print("Scraping failed (both Apify and browser fallback).")
        return

    method = article_data.get("method", "unknown")
    print(f"Scraping successful using method: {method}")

    if method == "apify":
        title = article_data.get("title", "Untitled")
        markdown = article_data.get("markdown", "")
        publish_time = article_data.get("publish_time", "")
        img_urls = re.findall(r'!\[.*?\]\((.*?)\)', markdown)
    elif method == "ua":
        title = article_data["title"]
        publish_time = article_data.get("publish_time", "")
        markdown, _img_urls = process_content(article_data["content_html"])
        # Merge UA-extracted data-src images with process_content images
        img_urls = article_data.get("img_urls", []) + _img_urls
    else:  # CDP / MCP
        title = article_data['title']
        publish_time = article_data['publish_time']
        markdown, img_urls = process_content(article_data['content_html'])

    full_content = f"# {title}\n\nURL: {url}\nTime: {publish_time}\n\n{markdown}"
    
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = os.path.join(BASE_IMAGE_DIR, article_hash)
    os.makedirs(article_dir, exist_ok=True)

    # Localize + describe images via shared pipeline (D-15)
    unique_img_urls = list(dict.fromkeys([u for u in img_urls if u.startswith('http')]))
    print(f"Found {len(unique_img_urls)} unique potential images. Downloading and describing...")
    url_to_path = download_images(unique_img_urls, Path(article_dir))
    descriptions = describe_images(list(url_to_path.values()))
    full_content = localize_markdown(full_content, url_to_path, article_hash=article_hash)
    processed_images = []
    for i, (url_img, path) in enumerate(url_to_path.items()):
        desc = descriptions.get(path, "")
        local_url = f"http://localhost:8765/{article_hash}/{path.name}"
        full_content += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {desc}\n"
        processed_images.append({"index": i, "description": desc, "local_url": local_url})
    image_success_count = len(url_to_path)
    image_fail_count = len(unique_img_urls) - image_success_count

    # Ingest into LightRAG
    print("Ingesting into LightRAG...")
    rag = await get_rag()
    
    # Cognee integration: Buffered
    try:
        raw_entities = await extract_entities(full_content)
        buffer_data = {'url': url, 'raw_entities': raw_entities, 'timestamp': os.path.getmtime(article_dir)}
        os.makedirs(ENTITY_BUFFER_DIR, exist_ok=True)
        with open(os.path.join(ENTITY_BUFFER_DIR, f'{article_hash}_entities.json'), 'w') as f:
            json.dump(buffer_data, f)
        print(f'Buffered {len(raw_entities)} entities for async processing.')
        _persist_entities_to_sqlite(url, raw_entities)
    except Exception as e:
        print(f'Warning: Entity buffering failed: {e}')
        raw_entities = []

    await rag.ainsert(full_content)

    # Cognee episodic memory: fire-and-forget article metadata
    # Per 2026 RAG best practices — dual-store: LightRAG (semantic) + Cognee (episodic)
    # Never blocks the fast path — timeout 5s, all exceptions swallowed
    try:
        await cognee_wrapper.remember_article(
            title=title,
            url=url,
            entities=raw_entities,
            summary_gist=full_content[:1000],
        )
    except Exception:
        pass

    # Save files via shared pipeline (atomic write, D-16)
    save_markdown_with_images(
        full_content,
        Path(article_dir),
        {
            "title": title,
            "url": url,
            "hash": article_hash,
            "method": method,
            "images": processed_images,
        },
    )
    
    print(f"--- Successfully Ingested! ---")
    print(f"Article: {title}")
    print(f"Hash: {article_hash}")
    print(f"Method: {method}")
    print(f"Local Path: {article_dir}")
    
    # Update DB: store content_hash so batch processor can skip re-scrape
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("UPDATE articles SET content_hash = ? WHERE url = ?", (article_hash, url))
            # D-07: mark short articles as enriched=-1 so the enrich_article skill
            # (or batch re-enrichment job) knows to skip them permanently.
            if len(full_content) < ENRICHMENT_MIN_LENGTH:
                conn.execute(
                    "UPDATE articles SET enriched = ? WHERE url = ?",
                    (-1, url),
                )
            conn.execute(
                "INSERT OR IGNORE INTO ingestions(article_id, status) VALUES ((SELECT id FROM articles WHERE url = ?), 'ok')",
                (url,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB update failed: {e}")

async def ingest_pdf(file_path):
    print(f"--- Starting PDF Ingestion: {file_path} ---")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return

    doc = fitz.open(file_path)
    title = os.path.basename(file_path)
    
    with open(file_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()[:10]
    
    article_dir = os.path.join(BASE_IMAGE_DIR, file_hash)
    os.makedirs(article_dir, exist_ok=True)
    
    full_text = f"# {title}\n\nFile: {file_path}\n\n"
    processed_images = []
    image_counter = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text()
        full_text += f"## Page {page_index + 1}\n\n{text}\n\n"
        
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            img_filename = f"page{page_index+1}_img{img_index}.{image_ext}"
            img_path = os.path.join(article_dir, img_filename)
            
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            
            print(f"  [Page {page_index+1}, Image {img_index}] Describing...")
            description = describe_images([Path(img_path)]).get(Path(img_path), "")
            
            local_url = f"http://localhost:8765/{file_hash}/{img_filename}"
            full_text += f"\n\n[Image {image_counter} Reference]: {local_url}\n[Image {image_counter} Description]: {description}\n\n"
            processed_images.append({
                "page": page_index + 1,
                "index": img_index,
                "description": description,
                "local_url": local_url,
                "filename": img_filename
            })
            image_counter += 1

    doc.close()

    article_hash = file_hash

    # Ingest into LightRAG
    print("Ingesting into LightRAG...")
    rag = await get_rag()

    # Cognee integration: Buffered
    try:
        raw_entities = await extract_entities(full_text)
        buffer_data = {'url': file_path, 'raw_entities': raw_entities, 'timestamp': os.path.getmtime(article_dir)}
        os.makedirs(ENTITY_BUFFER_DIR, exist_ok=True)
        with open(os.path.join(ENTITY_BUFFER_DIR, f'{article_hash}_entities.json'), 'w') as f:
            json.dump(buffer_data, f)
        print(f'Buffered {len(raw_entities)} entities for async processing.')
        _persist_entities_to_sqlite(file_path, raw_entities)
    except Exception as e:
        print(f'Warning: Entity buffering failed: {e}')

if __name__ == "__main__":
    import asyncio
    url = sys.argv[1] if len(sys.argv) > 1 else "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"
    asyncio.run(ingest_article(url))
