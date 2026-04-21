import os
import json
import hashlib
import requests
import re
import asyncio
import nest_asyncio
import fitz  # PyMuPDF
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import html2text
from google import genai
from PIL import Image
import numpy as np
import sys
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

# Load GEMINI_API_KEY and APIFY_TOKEN from ~/.hermes/.env if not set
def load_env():
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if not os.environ.get(key):
                        os.environ[key] = val.strip()

load_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
CDP_URL = "http://127.0.0.1:9223"
BASE_IMAGE_DIR = os.path.expanduser("./data/images")
RAG_WORKING_DIR = os.path.expanduser("./data/lightrag_storage")

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
    embedding_dim=3072,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001"
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
        print(f"Starting Apify actor for {url}...")
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input))
        
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
        except: pass
        
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

# --- Main Logic ---
async def ingest_article(url):
    print(f"--- Starting Ingestion: {url} ---")
    
    # 1. Try Apify first
    article_data = await scrape_wechat_apify(url)
    
    # Check if invalid
    is_invalid = False
    if article_data:
        content = article_data.get("markdown", "") + article_data.get("title", "")
        if any(keyword in content for keyword in ["环境异常", "验证", "登录"]):
            is_invalid = True
            print("Apify detected verification page, triggering fallback...")

    # 2. Fallback to CDP if Apify fails
    if not article_data or is_invalid:
        print("Apify failed or returned invalid results. Falling back to CDP...")
        article_data = await scrape_wechat_cdp(url)

    if not article_data:
        print("Scraping failed (both Apify and CDP).")
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
            else:
                print(f"  [Image {i}] Download failed: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [Image {i}] Error: {e}")

    # Ingest into LightRAG
    print("Ingesting into LightRAG...")
    rag = await get_rag()
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
    
    with open(os.path.join(article_dir, "final_content.md"), "w") as f:
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

    # Ingest into LightRAG
    print("Ingesting into LightRAG...")
    rag = await get_rag()
    await rag.ainsert(full_text)
    
    with open(os.path.join(article_dir, "metadata.json"), "w") as f:
        json.dump({
            "title": title, 
            "file_path": file_path, 
            "hash": file_hash, 
            "images": processed_images
        }, f, indent=2)
    
    with open(os.path.join(article_dir, "final_content.md"), "w") as f:
        f.write(full_text)
    
    print(f"--- Successfully Ingested PDF! ---")
    print(f"Title: {title}")
    print(f"Hash: {file_hash}")
    print(f"Local Path: {article_dir}")

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in environment.")
        sys.exit(1)
    
    input_path = sys.argv[1] if len(sys.argv) > 1 else "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"
    
    if input_path.startswith("http"):
        asyncio.run(ingest_article(input_path))
    elif input_path.lower().endswith(".pdf"):
        asyncio.run(ingest_pdf(input_path))
    else:
        print(f"Unknown input type: {input_path}")
        sys.exit(1)
