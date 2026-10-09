"""Read-only MCP tools over the same public reader used by HTTP."""
import sqlite3
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import StrictInt

from .knowledge import DEFAULT_LIMIT, KnowledgeError, KnowledgeReader


def create_server(database_path: str | Path) -> FastMCP:
    """Bind six evidence-reading tools to one public release, without a model."""
    database = Path(database_path)
    server = FastMCP(
        "VitaX public knowledge",
        instructions="Read public knowledge and its source evidence from one release.",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )

    def read(operation: Callable[[KnowledgeReader], dict[str, object]]) -> dict[str, object]:
        try:
            reader = KnowledgeReader(database)
        except (KnowledgeError, sqlite3.Error, OSError):
            raise ValueError("knowledge release is unavailable") from None
        try:
            with reader:
                return operation(reader)
        except (sqlite3.Error, OSError):
            raise ValueError("knowledge release is unavailable") from None

    @server.tool()
    def release_info() -> dict[str, object]:
        """Return the release identity shared by all query results."""
        return read(lambda reader: {"release_id": reader.release_id, "published_at": reader.published_at})

    @server.tool()
    def search(query: str, limit: StrictInt = DEFAULT_LIMIT, kind: str | None = None) -> dict[str, object]:
        """Search public article/Wiki titles and text; no model calls."""
        return read(lambda reader: reader.search(query, limit, kind))

    @server.tool()
    def read_knowledge(knowledge_id: str) -> dict[str, object]:
        """Read one public article or Wiki with its evidence identifiers."""
        return read(lambda reader: reader.read_knowledge(knowledge_id))

    @server.tool()
    def read_evidence(evidence_id: str) -> dict[str, object]:
        """Read a necessary source excerpt, locator and source link."""
        return read(lambda reader: reader.read_evidence(evidence_id))

    @server.tool()
    def list_entities(limit: StrictInt = DEFAULT_LIMIT) -> dict[str, object]:
        """Discover public entities before requesting their relations."""
        return read(lambda reader: reader.list_entities(limit))

    @server.tool()
    def related(entity_id: str, limit: StrictInt = DEFAULT_LIMIT) -> dict[str, object]:
        """Read bounded, source-linked relations for one public entity."""
        return read(lambda reader: reader.related(entity_id, limit))

    return server
