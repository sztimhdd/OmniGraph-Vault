import os
import hashlib
import asyncio
import nest_asyncio
import fitz  # PyMuPDF
from google import genai
from PIL import Image
import sys
import json

# For LightRAG
try:
    from lightrag.lightrag import LightRAG
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.
from lib import embedding_func
# Quick 260509-s29 Wave 3: route via OMNIGRAPH_LLM_PROVIDER dispatcher
# (defaults to deepseek; Plan 05-00c Task 0c.3 DeepSeek routing preserved
# as the dispatcher's default).
from lib.llm_complete import get_llm_func

# VISION_LLM stays on Gemini — the describe_image() multimodal path is Gemini-only.
from lib import INGESTION_LLM, VISION_LLM, current_key, get_limiter, generate_sync

nest_asyncio.apply()

# Load GEMINI_API_KEY from ~/.hermes/.env if not set
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

# Phase 7: GEMINI_API_KEY now accessed via lib.current_key() — supports rotation.
BASE_IMAGE_DIR = os.path.expanduser("./data/images")
RAG_WORKING_DIR = os.path.expanduser("./data/lightrag_storage")

os.makedirs(BASE_IMAGE_DIR, exist_ok=True)
os.makedirs(RAG_WORKING_DIR, exist_ok=True)

# Force standard Gemini API mode
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# --- LightRAG Setup ---
# Plan 05-00c Task 0c.3: LightRAG LLM routes to Deepseek; VISION_LLM stays on
# Gemini (multimodal image description is a Gemini-only path).
async def get_rag():
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
        # Phase 4 throttle guardrails preserved (Gemini embedding RPM limits).
        embedding_func_max_async=1,
        embedding_batch_num=20,
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag

# --- Image Processing ---
def describe_image(image_path):
    """Describe an image via lib.generate_sync (Amendment 5 multimodal path)."""
    try:
        from google.genai import types
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return generate_sync(
            VISION_LLM,
            contents=[
                "Describe this image in detail for a knowledge graph. Return only the description.",
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
        )
    except Exception as e:
        return f"Error describing image: {e}"

async def ingest_pdf(pdf_path):
    print(f"--- Starting PDF Ingestion: {pdf_path} ---")
    
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return

    # Generate hash for the PDF
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
        pdf_hash = hashlib.md5(pdf_content).hexdigest()[:10]

    pdf_dir = os.path.join(BASE_IMAGE_DIR, pdf_hash)
    os.makedirs(pdf_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    full_text = []
    processed_images = []
    
    img_counter = 0
    for page_index in range(len(doc)):
        page = doc[page_index]
        full_text.append(f"## Page {page_index + 1}\n")
        full_text.append(page.get_text())
        
        # Extract images
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            img_filename = f"page{page_index+1}_img{img_index}.{image_ext}"
            img_path = os.path.join(pdf_dir, img_filename)
            
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            
            print(f"  [Image {img_counter}] Describing {img_filename}...")
            description = describe_image(img_path)
            
            local_url = f"http://localhost:8765/{pdf_hash}/{img_filename}"
            full_text.append(f"\n\n[Image {img_counter} Reference]: {local_url}\n[Image {img_counter} Description]: {description}\n")
            
            processed_images.append({
                "filename": img_filename,
                "description": description,
                "local_url": local_url,
                "page": page_index + 1
            })
            img_counter += 1

    doc.close()
    
    final_content = "\n".join(full_text)
    
    # Ingest into LightRAG
    print("Ingesting into LightRAG...")
    # D-09.07 / D-09.04: flush=True → fresh instance, no replay of prior pending buffer.
    rag = await get_rag(flush=True)
    await rag.ainsert(final_content)
    
    # Save metadata
    with open(os.path.join(pdf_dir, "metadata.json"), "w") as f:
        json.dump({
            "filename": os.path.basename(pdf_path),
            "hash": pdf_hash,
            "images": processed_images
        }, f, indent=2)
        
    with open(os.path.join(pdf_dir, "final_content.md"), "w") as f:
        f.write(final_content)
        
    print(f"--- Successfully Ingested PDF! ---")
    print(f"File: {os.path.basename(pdf_path)}")
    print(f"Hash: {pdf_hash}")
    print(f"Local Path: {pdf_dir}")

if __name__ == "__main__":
    # Phase 7: key presence is validated lazily by lib.current_key() —
    # load_keys() raises RuntimeError with a remediation message if none are set.
    if len(sys.argv) < 2:
        print("Usage: python multimodal_ingest.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    asyncio.run(ingest_pdf(pdf_path))
