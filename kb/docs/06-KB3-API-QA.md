# KB-3: RAG问答API + 问答UI (2天)

## Goal
Build FastAPI backend on Hermes (:8766) and React Q&A UI island.

## Backend (kb_api.py, FastAPI)

### Endpoints
| Method | Path | Description | Data Source |
|--------|------|-------------|-------------|
| GET | /articles | Article list with pagination+filter | SQLite |
| GET | /article/{hash} | Article detail with MD body | filesystem → SQLite fallback |
| GET | /search?q=&mode= | Search (FTS5 default, ?mode=kg=LightRAG) | FTS5 / LightRAG |
| POST | /synthesize | Deep research answer | BackgroundTasks |
| GET | /synthesize/{job_id} | Poll research result | in-memory |
| GET | /entities | Entity list | SQLite entity_canonical |
| GET | /entity/{name} | Entity detail + linked articles | SQLite |

### Search Implementation
- Default: SQLite FTS5 on articles.title + articles.body (<10ms)
  ```sql
  CREATE VIRTUAL TABLE articles_fts USING fts5(title, body, content='articles', content_rowid='id');
  SELECT a.id, a.title, a.content_hash FROM articles_fts f JOIN articles a ON a.id=f.rowid
  WHERE articles_fts MATCH ? ORDER BY rank LIMIT 20;
  ```
- ?mode=kg: call kg_synthesize.synthesize_response() via LightRAG (async, 5-30s)

### Synthesize Async
- POST /synthesize creates background task → returns 202 + job_id
- GET /synthesize/{job_id} returns {status: "running"|"done"|"failed", result}
- Internally calls kg_synthesize.synthesize_response() with IMAGE_URL_DIRECTIVE

### Image Serving
```python
from fastapi.staticfiles import StaticFiles
IMAGES_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "images"
app.mount("/static/img", StaticFiles(directory=str(IMAGES_DIR)), name="images")
```

### Article Detail Logic
```python
def get_article_body(hash, article_id):
    for path in [IMAGES_DIR/hash/"final_content.enriched.md", IMAGES_DIR/hash/"final_content.md"]:
        if path.exists():
            md = path.read_text()
            md = re.sub(r'http://localhost:8765/', '/static/img/', md)
            return md, "vision_enriched"
    body = db.execute("SELECT body FROM articles WHERE id=?", [article_id]).fetchone()
    return body[0], "raw_markdown"
```

## Frontend (React Island in ask/index.html)
- Question input box + send button
- Loading state (spinner + "正在检索知识图谱...")
- Markdown render for answer (react-markdown or similar)
- Source articles as links (→ actual article page)
- Entity tags as links (→ entity page)
- "Helpful / Not helpful" feedback buttons
- Hot questions list (hardcoded initial, API-driven later)

## Caddy Config
```
ohca.ddns.net {
    reverse_proxy /static/img/* localhost:8766
    reverse_proxy /kb/* localhost:8766
    reverse_proxy /* localhost:3001
}
```
