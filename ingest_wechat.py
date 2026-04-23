import os
import sys
import json
import hashlib
import requests
import re

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import nest_asyncio
import fitz  # PyMuPDF
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import html2text
from google import genai
from PIL import Image
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

from config import RAG_WORKING_DIR, BASE_IMAGE_DIR, load_env, CDP_URL, ENTITY_BUFFER_DIR
load_env()


def _is_mcp_endpoint(url: str) -> bool:
    return bool(url) and url.rstrip("/").endswith("/mcp")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

os.makedirs(BASE_IMAGE_DIR, exist_ok=True)
os.makedirs(RAG_WORKING_DIR, exist_ok=True)

# Force standard Gemini API mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# --- LightRAG Setup ---
async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=GEMINI_API_KEY,
        model_name="gemini-3.1-flash-lite-preview",
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
        llm_model_name="gemini-3.1-flash-lite-preview",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag

# --- Image Processing ---
def describe_image(image_path):
    try:
        vision_client = genai.Client(api_key=GEMINI_API_KEY)
        img = Image.open(image_path)
        response = vision_client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=["Describe this image in detail for a knowledge graph. Return only the description.", img]
        )
        return response.text
    except Exception as e:
        return f"Error describing image: {e}"

# --- Scraping Methods ---

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
            model='gemini-3.1-flash-lite-preview',
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
    
    print("Starting ingestion process...")
# 1. Try Apify first
    article_data = await scrape_wechat_apify(url)
    
    # Check if Apify returned a verification/login page instead of real content.
    # Real verification pages are very short (<500 chars); real articles with "验证"
    # in them (e.g., "模型验证") are thousands of chars long.
    is_invalid = False
    if article_data:
        content = article_data.get("markdown", "") + article_data.get("title", "")
        is_short = len(content) < 500
        has_block_keywords = any(kw in content for kw in ["环境异常", "请完成验证", "请登录"])
        if is_short and has_block_keywords:
            is_invalid = True
            print(f"Apify returned verification/login page ({len(content)} chars), triggering fallback...")

    # 2. Fallback to browser scraping if Apify fails
    if not article_data or is_invalid:
        if _is_mcp_endpoint(CDP_URL):
            print("Apify failed or returned invalid results. Falling back to remote Playwright MCP...")
            article_data = await scrape_wechat_mcp(url)
        else:
            print("Apify failed or returned invalid results. Falling back to local CDP...")
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
    else: # CDP
        title = article_data['title']
        publish_time = article_data['publish_time']
        markdown, img_urls = process_content(article_data['content_html'])

    full_content = f"# {title}\n\nURL: {url}\nTime: {publish_time}\n\n{markdown}"
    
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = os.path.join(BASE_IMAGE_DIR, article_hash)
    os.makedirs(article_dir, exist_ok=True)

    processed_images = []
    unique_img_urls = list(dict.fromkeys([u for u in img_urls if u.startswith('http')]))

    print(f"Found {len(unique_img_urls)} unique potential images. Downloading and describing...")

    image_success_count = 0
    image_fail_count = 0

    for i, img_url in enumerate(unique_img_urls):
        try:
            img_path = os.path.join(article_dir, f"{i}.jpg")
            resp = requests.get(img_url, timeout=10)
            if resp.status_code == 200:
                with open(img_path, "wb") as f:
                    f.write(resp.content)

                print(f"  [Image {i}] Describing...")
                description = describe_image(img_path)

                local_url = f"http://localhost:8765/{article_hash}/{i}.jpg"
                full_content = full_content.replace(img_url, local_url)

                full_content += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {description}\n"
                processed_images.append({"index": i, "description": description, "local_url": local_url})
                image_success_count += 1
            else:
                print(f"  [Image {i}] Download failed: HTTP {resp.status_code}")
                image_fail_count += 1
        except Exception as e:
            print(f"  [Image {i}] Error: {e}")
            image_fail_count += 1

    total_images = image_success_count + image_fail_count
    if total_images > 0 and image_success_count / total_images < 0.5:
        print(f"Warning: Only {image_success_count}/{total_images} images downloaded successfully (< 50% success rate)")

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
    except Exception as e:
        print(f'Warning: Entity buffering failed: {e}')
        
    await rag.ainsert(full_content)
    
    # Save files for inspection
    with open(os.path.join(article_dir, "metadata.json"), "w") as f:
        json.dump({
            "title": title, 
            "url": url, 
            "hash": article_hash, 
            "method": method,
            "images": processed_images
        }, f, indent=2)
    
    with open(os.path.join(article_dir, "final_content.md"), "w", encoding="utf-8") as f:
        f.write(full_content)
    
    print(f"--- Successfully Ingested! ---")
    print(f"Article: {title}")
    print(f"Hash: {article_hash}")
    print(f"Method: {method}")
    print(f"Local Path: {article_dir}")

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
            description = describe_image(img_path)
            
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
    except Exception as e:
        print(f'Warning: Entity buffering failed: {e}')

if __name__ == "__main__":
    import asyncio
    url = sys.argv[1] if len(sys.argv) > 1 else "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"
    asyncio.run(ingest_article(url))
