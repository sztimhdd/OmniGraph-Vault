"""Minimal FastAPI test - just to verify startup works."""
from fastapi import FastAPI

app = FastAPI(title="Test")

@app.get("/health")
def health():
    return {"status": "ok"}
