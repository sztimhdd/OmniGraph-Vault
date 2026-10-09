"""Shared public knowledge and explicit loopback-only article reading surface.

Public HTTP/MCP use KnowledgeReader. Private articles use the configured mirror;
importing this module opens no database, credentials, or server.
"""
from __future__ import annotations

import argparse
import ipaddress
import logging
import sqlite3
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from .knowledge import (
    DEFAULT_LIMIT,
    KnowledgeError,
    KnowledgeNotFound,
    KnowledgeReader,
)
from .mcp import create_server
from .local_articles import (SnapshotChanged, fingerprint, list_local_articles, read_local_article, local_article_counts, load_local_snapshot, render_body)


_LOG = logging.getLogger(__name__)


def _client_route(path: str) -> bool:
    """Return True for client routes that may fall back to the built site index."""
    if path == "/api" or path.startswith("/api/"):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def create_app(database_path: str | Path | None = None, site_dir: str | Path | None = None, *, local_articles_database: str | Path | None = None, local_articles_receipt: str | Path | None = None, allow_remote_articles: bool = False, mount_mcp: bool = True, images_dir: str | Path | None = None) -> FastAPI:
    """Build the read-only app for one public release and an optional built site.

    ``allow_remote_articles`` and ``mount_mcp`` are explicit opt-ins for a cloud
    reader: the default keeps the loopback-only article gate and the MCP mount.
    ``images_dir`` is an explicit opt-in that serves referenced article media
    under ``/static/img``; Starlette rejects any traversal outside that directory.
    """
    database = Path(database_path) if database_path is not None else None
    if database is None and local_articles_database is None:
        raise KnowledgeError("configure a public database or local articles database")
    if (local_articles_database is None) != (local_articles_receipt is None):
        raise KnowledgeError("local article database and receipt must be supplied together")
    if database is not None:
        with KnowledgeReader(database):
            pass
    local_cache = {}
    if local_articles_database is not None:
        initial = load_local_snapshot(local_articles_database, local_articles_receipt, local_cache)
        local_article_counts(initial["database"])
    site = Path(site_dir) if site_dir is not None else None
    if site is not None and not (site / "index.html").is_file():
        raise KnowledgeError(f"site directory must contain index.html: {site}")
    images = Path(images_dir).resolve() if images_dir is not None else None
    if images is not None and not images.is_dir():
        raise KnowledgeError(f"images directory must exist: {images}")

    mcp_server = create_server(database) if database is not None and mount_mcp else None
    mcp_app = mcp_server.streamable_http_app() if mcp_server is not None else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if mcp_server is None:
            yield
        else:
            async with mcp_server.session_manager.run():
                yield

    app = FastAPI(title="VitaX knowledge read API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def unavailable(exc: BaseException) -> JSONResponse:
        _LOG.warning("knowledge release read failed: %s", exc)
        return JSONResponse({"error": "knowledge release is unavailable"}, status_code=500)

    def respond(operation: Callable[[KnowledgeReader], dict[str, object]]) -> JSONResponse:
        try:
            reader = KnowledgeReader(database)
        except (KnowledgeError, sqlite3.Error, OSError) as exc:
            return unavailable(exc)
        try:
            with reader:
                payload = operation(reader)
        except KnowledgeNotFound as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except KnowledgeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except (sqlite3.Error, OSError) as exc:
            return unavailable(exc)
        return JSONResponse(payload)

    if database is not None:
        @app.get("/api/release")
        def release_metadata() -> JSONResponse:
            return respond(lambda reader: {"release_id": reader.release_id, "published_at": reader.published_at})

        @app.get("/api/health")
        def health() -> JSONResponse:
            return respond(
                lambda reader: {
                    "status": "ok",
                    "release_id": reader.release_id,
                    "published_at": reader.published_at,
                }
            )

        @app.get("/api/knowledge")
        def knowledge_index(q: str | None = None, kind: str | None = None, limit: int = DEFAULT_LIMIT) -> JSONResponse:
            if q is None:
                return respond(lambda reader: reader.list_knowledge(kind=kind, limit=limit))
            return respond(lambda reader: reader.search(q, limit, kind))

        @app.get("/api/knowledge/{knowledge_id}")
        def knowledge_item(knowledge_id: str) -> JSONResponse:
            def detail(reader):
                payload = reader.read_knowledge(knowledge_id)
                item = payload["knowledge"]
                item["rendered_html"] = render_body(item["body"])
                return payload
            return respond(detail)

        @app.get("/api/evidence/{evidence_id}")
        def evidence_item(evidence_id: str) -> JSONResponse:
            return respond(lambda reader: reader.read_evidence(evidence_id))

        @app.get("/api/entities")
        def entity_index(limit: int = DEFAULT_LIMIT) -> JSONResponse:
            return respond(lambda reader: reader.list_entities(limit=limit))

        @app.get("/api/entities/{entity_id}/related")
        def entity_relations(entity_id: str, limit: int = DEFAULT_LIMIT) -> JSONResponse:
            return respond(lambda reader: reader.related(entity_id, limit))

    @app.get("/api/capabilities")
    def capabilities() -> dict:
        return {"public_knowledge": database is not None, "local_articles": local_articles_database is not None}

    if local_articles_database is not None:
        def local_response(request: Request, operation) -> JSONResponse:
            if not allow_remote_articles:
                # Explicit loopback gate; a reverse proxy cannot grant access by
                # forwarding a loopback address (proxy headers stay untrusted).
                try:
                    peer = ipaddress.ip_address(request.client.host) if request.client else None
                    if peer is None or not peer.is_loopback:
                        return JSONResponse({"error": "local access required"}, status_code=403)
                except ValueError:
                    return JSONResponse({"error": "local access required"}, status_code=403)
            try:
                snapshot = load_local_snapshot(local_articles_database, local_articles_receipt, local_cache)
                payload = operation(snapshot)
                if fingerprint(snapshot["database"]) != snapshot["fingerprint"]:
                    raise SnapshotChanged("snapshot_changed")
                return JSONResponse({"snapshot_id": snapshot["snapshot_id"], **payload})
            except SnapshotChanged:
                return JSONResponse({"error": "snapshot_changed"}, status_code=409)
            except KnowledgeNotFound:
                return JSONResponse({"error": "article not found"}, status_code=404)
            except KnowledgeError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            except (sqlite3.Error, OSError):
                return JSONResponse({"error": "local articles unavailable"}, status_code=503)

        @app.get("/api/library/status")
        def library_status(request: Request) -> JSONResponse:
            return local_response(request, lambda snapshot: {"counts": local_article_counts(snapshot["database"]), "observed_at": snapshot["observed_at"]})

        @app.get("/api/library")
        def library_index(request: Request, q: str = "", source: str | None = None, limit: int = DEFAULT_LIMIT, offset: int = 0, has_body: bool = False) -> JSONResponse:
            return local_response(request, lambda snapshot: list_local_articles(snapshot["database"], q=q, source=source, limit=limit, offset=offset, has_body=has_body))

        @app.get("/api/library/{source}/{record_id}")
        def library_item(request: Request, source: str, record_id: int) -> JSONResponse:
            def detail(snapshot):
                item = read_local_article(snapshot["database"], source, record_id)
                # Render the reading views here so the producer-side reader stays raw.
                for view in ("body", "body_translated", "body_rewritten"):
                    item[f"{view}_html"] = render_body(item.get(view), item.get("source_url"))
                return item
            return local_response(request, detail)

        if site is not None:
            @app.get("/library")
            def library_page(request: Request) -> Response:
                result = library_status(request)
                return FileResponse(site / "index.html") if result.status_code == 200 else result

            @app.get("/library/{source}/{record_id}")
            def library_detail_page(request: Request, source: str, record_id: int) -> Response:
                result = library_item(request, source, record_id)
                return FileResponse(site / "index.html") if result.status_code == 200 else result

    @app.api_route("/api/{rest:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def unknown_api(rest: str) -> JSONResponse:
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404 and site is not None and _client_route(request.url.path):
            return FileResponse(site / "index.html", status_code=404)
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    if mcp_app is not None:
        @app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
        def mcp_redirect(request: Request) -> RedirectResponse:
            return RedirectResponse(str(request.url.replace(path=request.url.path + "/")), status_code=307)

        app.mount("/mcp", mcp_app, name="mcp")
    if site is not None and database is not None:
        @app.get("/knowledge")
        def knowledge_list_page() -> Response:
            # The SPA renders the knowledge list here when the article library owns `/`.
            return FileResponse(site / "index.html")
    if images is not None:
        # Registered before the site mount so /static/img wins over any site file.
        app.mount("/static/img", StaticFiles(directory=images), name="article-images")
    if site is not None:
        app.mount("/", StaticFiles(directory=site, html=True), name="site")

    return app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vitax.api",
        description="Serve the read-only VitaX public knowledge API on localhost.",
    )
    parser.add_argument("database", nargs="?", help="path to a public VitaX knowledge SQLite release")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default: %(default)s)")
    parser.add_argument("--site-dir", default=None, help="optional built site directory to serve")
    parser.add_argument("--local-articles-db", default=None)
    parser.add_argument("--local-articles-receipt", default=None)
    parser.add_argument("--allow-remote-articles", action="store_true", help="explicitly serve the article mirror to any peer (cloud reader)")
    parser.add_argument("--no-mcp", action="store_true", help="do not mount the MCP server")
    parser.add_argument("--images-dir", default=None, help="optional directory served read-only under /static/img")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.local_articles_db is not None and not args.allow_remote_articles and not ipaddress.ip_address(args.host).is_loopback:
            raise KnowledgeError("local articles require a loopback bind address")
        app = create_app(args.database, site_dir=args.site_dir, local_articles_database=args.local_articles_db, local_articles_receipt=args.local_articles_receipt, allow_remote_articles=args.allow_remote_articles, mount_mcp=not args.no_mcp, images_dir=args.images_dir)
    except (KnowledgeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=args.local_articles_db is None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
