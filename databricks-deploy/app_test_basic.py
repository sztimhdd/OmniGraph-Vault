"""Absolutely minimal FastAPI test."""
import sys
print(f"[STARTUP] Python {sys.version}", flush=True)
print(f"[STARTUP] sys.path: {sys.path[:2]}", flush=True)

from fastapi import FastAPI

app = FastAPI(title="Test")

@app.get("/health")
def health():
    return {"status": "ok"}

print("[STARTUP] App created successfully", flush=True)
