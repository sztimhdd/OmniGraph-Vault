import os
import hashlib
import asyncio
import nest_asyncio
import fitz  # PyMuPDF
from google import genai
from PIL import Image
import numpy as np
import sys
import json

# For LightRAG
try:
    from lightrag.lightrag import LightRAG
    from lightrag.llm.gemini import gemini_model_complete, gemini_embed
    from lightrag.utils import wrap_embedding_func_with_attrs
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_IMAGE_DIR = os.path.expanduser("./data/images")
RAG_WORKING_DIR = os.path.expanduser("./data/lightrag_storage")

os.makedirs(BASE_IMAGE_DIR, exist_ok=True)
os.makedirs(RAG_WORKING_DIR, exist_ok=True)

# Force standard Gemini API mode
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# --- LightRAG Setup ---
async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=GEMINI_API_KEY,
        model_name="gemini-2.0-flash",
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
        llm_model_name="gemini-2.0-flash",
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
            model='gemini-2.0-flash',
            contents=["Describe this image in detail for a knowledge graph. Return only the description.", img]
        )
        return response.text
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
    rag = await get_rag()
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
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in environment.")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python multimodal_ingest.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    asyncio.run(ingest_pdf(pdf_path))
