"""FastAPI app with health check."""
from fastapi import FastAPI

app = FastAPI(title="OmniGraph KB")

@app.get("/health")
def health():
    return {"status": "ok"}
