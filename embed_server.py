#!/usr/bin/env python3
"""Minimal HTTP embedding server using FlagEmbedding BGE-M3.
Replaces Infinity — same OpenAI-compatible API shape, fewer deps, same port.
"""
import sys, os, json, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np

PORT = int(os.environ.get("EMBED_PORT", "7997"))
MODEL_PATH = os.environ.get("EMBED_MODEL_PATH", "/models/bge-m3/BAAI/bge-m3")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("embed-server")

# Lazy load
_model = None

def get_model():
    global _model
    if _model is None:
        log.info(f"Loading BGE-M3 from {MODEL_PATH}...")
        from FlagEmbedding import BGEM3FlagModel
        # Use local path with local_files_only (ModelScope download, no HF hub)
        _model = BGEM3FlagModel(MODEL_PATH, use_fp16=True, local_files_only=True)
        log.info("BGE-M3 model loaded")
    return _model

class EmbedHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/embeddings", "/embed"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        texts = body.get("input", [])
        if isinstance(texts, str):
            texts = [texts]

        try:
            model = get_model()
            result = model.encode(texts, batch_size=min(len(texts), 64))
            embeddings = result["dense_vecs"]

            data = [{"embedding": e.tolist(), "index": i} for i, e in enumerate(embeddings)]

            resp = json.dumps({"object": "list", "data": data, "model": "bge-m3",
                               "usage": {"prompt_tokens": sum(len(t) for t in texts)}})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode())
        except Exception as e:
            log.error(f"Embed error: {e}")
            self.send_error(500, str(e))

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} {fmt % args}")

if __name__ == "__main__":
    # Warm up model before accepting requests
    log.info("Warming up model...")
    get_model().encode(["warmup"])

    server = HTTPServer(("0.0.0.0", PORT), EmbedHandler)
    log.info(f"Embedding server on 0.0.0.0:{PORT}")
    server.serve_forever()
