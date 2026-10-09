"""Build and read an offline, public-only VitaX knowledge projection.

FTS5 uses SQLite's built-in ``unicode61`` tokenizer. It does not provide
Chinese word segmentation, so Chinese searches are most useful for exact
phrases until a separately evaluated tokenizer is introduced.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Mapping
from datetime import date, datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlparse


MAX_LIMIT = 100
DEFAULT_LIMIT = 20
MAX_QUERY_LENGTH = 512
KNOWLEDGE_KINDS = ("article", "wiki")


class KnowledgeError(ValueError):
    """The projection or its read-model database violates the public contract."""


class KnowledgeNotFound(KnowledgeError):
    """A requested public identifier is absent from this release."""


def validate_kind(kind: object) -> str:
    """Reject any kind outside the fixed public knowledge kinds."""
    if not isinstance(kind, str) or kind not in KNOWLEDGE_KINDS:
        raise KnowledgeError("kind must be article or wiki")
    return kind


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError(f"{name} must be a nonempty string")
    return value


def _visibility(item: Mapping[str, object], name: str) -> str:
    value = item.get("visibility")
    if not isinstance(value, str) or value not in {"public", "private"}:
        raise KnowledgeError(f"{name}.visibility must be public or private")
    return value


def _items(payload: Mapping[str, object], name: str) -> list[Mapping[str, object]]:
    value = payload.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise KnowledgeError(f"{name} must be a list of objects")
    return list(value)


def _public_ids(
    items: list[Mapping[str, object]], key: str, collection: str
) -> dict[str, Mapping[str, object]]:
    seen: set[str] = set()
    public: dict[str, Mapping[str, object]] = {}
    for item in items:
        identifier = _require_text(item.get(key), key)
        if identifier in seen:
            raise KnowledgeError(f"duplicate {key}: {identifier}")
        seen.add(identifier)
        if _visibility(item, collection) == "public":
            public[identifier] = item
    return public


def _optional_time(value: object, name: str) -> None:
    """Accept ISO-8601 dates or datetimes; historical precision remains unchanged."""
    if value is None:
        return
    text = _require_text(value, name)
    try:
        date.fromisoformat(text)
    except ValueError:
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise KnowledgeError(f"{name} must be an ISO-8601 date, datetime, or null") from exc


def _source_url(value: object) -> str:
    source_url = _require_text(value, "document.source_url")
    try:
        parsed = urlparse(source_url)
        host = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise KnowledgeError("document.source_url must have a valid host and port") from exc
    if parsed.scheme not in {"http", "https"}:
        raise KnowledgeError("document.source_url must be an http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise KnowledgeError("document.source_url must not contain userinfo")
    if not host or any(character.isspace() for character in host):
        raise KnowledgeError("document.source_url must have a valid host and port")
    try:
        ip_address(host)
        return source_url
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise KnowledgeError("document.source_url must have a valid host and port") from exc
    labels = host.rstrip(".").split(".")
    if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
        raise KnowledgeError("document.source_url must have a valid host and port")
    return source_url


def _evidence_ids(item: Mapping[str, object], name: str) -> list[str]:
    values = item.get("evidence_ids")
    if not isinstance(values, list) or not values:
        raise KnowledgeError(f"{name}.evidence_ids must be a nonempty list")
    if not all(isinstance(value, str) and value for value in values):
        raise KnowledgeError(f"{name}.evidence_ids must contain nonempty strings")
    if len(set(values)) != len(values):
        raise KnowledgeError(f"{name}.evidence_ids must not contain duplicates")
    return list(values)


def body_evidence_ids(body: str) -> list[str]:
    """Recognize the canonical evidence IDs emitted by the existing producer."""
    pattern = r"(?<![A-Za-z0-9_-])evidence-[0-9a-f]{20}(?![A-Za-z0-9_-])"
    return list(dict.fromkeys(re.findall(pattern, body)))


def _validate_projection(source: Mapping[str, object]) -> dict[str, object]:
    if type(source.get("schema_version")) is not int or source["schema_version"] != 1:
        raise KnowledgeError("schema_version must be 1")
    release_id = _require_text(source.get("release_id"), "release_id")
    published_at = _require_text(source.get("published_at"), "published_at")
    try:
        timestamp = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeError("published_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None:
        raise KnowledgeError("published_at must be an ISO-8601 timestamp")

    documents = _public_ids(_items(source, "documents"), "revision_id", "documents")
    for revision_id, document in documents.items():
        _require_text(document.get("doc_id"), "doc_id")
        _require_text(document.get("title"), "document.title")
        _source_url(document.get("source_url"))
        for timestamp in ("source_published_at", "fetched_at"):
            _optional_time(document.get(timestamp), f"document.{timestamp}")

    evidence = _public_ids(_items(source, "evidence"), "evidence_id", "evidence")
    for evidence_id, item in evidence.items():
        revision_id = _require_text(item.get("revision_id"), "evidence.revision_id")
        if revision_id not in documents:
            raise KnowledgeError(f"evidence {evidence_id} references unknown or private revision_id: {revision_id}")
        _require_text(item.get("locator"), "evidence.locator")
        _require_text(item.get("quote"), "evidence.quote")

    knowledge = _public_ids(_items(source, "knowledge"), "knowledge_id", "knowledge")
    for knowledge_id, item in knowledge.items():
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in KNOWLEDGE_KINDS:
            raise KnowledgeError("knowledge.kind must be article or wiki")
        _require_text(item.get("title"), "knowledge.title")
        body = _require_text(item.get("body"), "knowledge.body")
        linked = _evidence_ids(item, f"knowledge {knowledge_id}")
        closed = list(dict.fromkeys([*linked, *body_evidence_ids(body)]))
        for evidence_id in closed:
            if evidence_id not in evidence:
                raise KnowledgeError(f"unknown evidence_id: {evidence_id}")
        # Add only links to evidence already approved for this public release.
        knowledge[knowledge_id] = {**item, "evidence_ids": closed}

    entities = _public_ids(_items(source, "entities"), "entity_id", "entities")
    for item in entities.values():
        _require_text(item.get("name"), "entity.name")

    relations = _public_ids(_items(source, "relations"), "relation_id", "relations")
    for relation_id, item in relations.items():
        source_id = _require_text(item.get("source_id"), "relation.source_id")
        target_id = _require_text(item.get("target_id"), "relation.target_id")
        if source_id not in entities or target_id not in entities:
            raise KnowledgeError(f"relation {relation_id} references unknown or private entity")
        _require_text(item.get("relation_type"), "relation.relation_type")
        for evidence_id in _evidence_ids(item, f"relation {relation_id}"):
            if evidence_id not in evidence:
                raise KnowledgeError(f"unknown evidence_id: {evidence_id}")

    return {
        "release_id": release_id,
        "published_at": published_at,
        "documents": documents,
        "evidence": evidence,
        "knowledge": knowledge,
        "entities": entities,
        "relations": relations,
    }


_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
    revision_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, title TEXT NOT NULL,
    source_url TEXT NOT NULL, source_published_at TEXT, fetched_at TEXT
);
CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES documents,
    locator TEXT NOT NULL, quote TEXT NOT NULL
);
CREATE TABLE knowledge (
    knowledge_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE knowledge_evidence (
    knowledge_id TEXT NOT NULL REFERENCES knowledge, evidence_id TEXT NOT NULL REFERENCES evidence,
    position INTEGER NOT NULL, PRIMARY KEY (knowledge_id, evidence_id)
);
CREATE TABLE entities (entity_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE relations (
    relation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES entities,
    target_id TEXT NOT NULL REFERENCES entities, relation_type TEXT NOT NULL
);
CREATE INDEX relations_source_id ON relations(source_id);
CREATE INDEX relations_target_id ON relations(target_id);
CREATE TABLE relation_evidence (
    relation_id TEXT NOT NULL REFERENCES relations, evidence_id TEXT NOT NULL REFERENCES evidence,
    position INTEGER NOT NULL, PRIMARY KEY (relation_id, evidence_id)
);
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    knowledge_id UNINDEXED, title, body, tokenize='unicode61'
);
"""

_REQUIRED_COLUMNS = {
    "metadata": {"key", "value"},
    "documents": {"revision_id", "doc_id", "title", "source_url", "source_published_at", "fetched_at"},
    "evidence": {"evidence_id", "revision_id", "locator", "quote"},
    "knowledge": {"knowledge_id", "kind", "title", "body"},
    "knowledge_evidence": {"knowledge_id", "evidence_id", "position"},
    "entities": {"entity_id", "name"},
    "relations": {"relation_id", "source_id", "target_id", "relation_type"},
    "relation_evidence": {"relation_id", "evidence_id", "position"},
    "knowledge_fts": {"knowledge_id", "title", "body"},
}


def _load_projection(projection: Mapping[str, object] | str | Path) -> Mapping[str, object]:
    if isinstance(projection, Mapping):
        return projection
    try:
        value = json.loads(Path(projection).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"cannot read projection JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise KnowledgeError("projection JSON must be an object")
    return value


def build(projection: Mapping[str, object] | str | Path, output_path: str | Path) -> dict[str, object]:
    """Validate a public DTO then create its new SQLite read model exactly once."""
    validated = _validate_projection(_load_projection(projection))
    target = Path(output_path)
    if os.path.lexists(target):
        raise KnowledgeError(f"output path already exists: {target}")
    if not target.parent.is_dir():
        raise KnowledgeError(f"output directory does not exist: {target.parent}")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(_SCHEMA)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                [("schema_version", "1"), ("release_id", validated["release_id"]), ("published_at", validated["published_at"])],
            )
            connection.executemany(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (revision_id, item["doc_id"], item["title"], item["source_url"], item.get("source_published_at"), item.get("fetched_at"))
                    for revision_id, item in validated["documents"].items()
                ],
            )
            connection.executemany(
                "INSERT INTO evidence VALUES (?, ?, ?, ?)",
                [(identifier, item["revision_id"], item["locator"], item["quote"]) for identifier, item in validated["evidence"].items()],
            )
            connection.executemany(
                "INSERT INTO knowledge VALUES (?, ?, ?, ?)",
                [(identifier, item["kind"], item["title"], item["body"]) for identifier, item in validated["knowledge"].items()],
            )
            connection.executemany(
                "INSERT INTO knowledge_fts VALUES (?, ?, ?)",
                [(identifier, item["title"], item["body"]) for identifier, item in validated["knowledge"].items()],
            )
            connection.executemany(
                "INSERT INTO knowledge_evidence VALUES (?, ?, ?)",
                [(identifier, evidence_id, position) for identifier, item in validated["knowledge"].items() for position, evidence_id in enumerate(item["evidence_ids"])],
            )
            connection.executemany(
                "INSERT INTO entities VALUES (?, ?)",
                [(identifier, item["name"]) for identifier, item in validated["entities"].items()],
            )
            connection.executemany(
                "INSERT INTO relations VALUES (?, ?, ?, ?)",
                [(identifier, item["source_id"], item["target_id"], item["relation_type"]) for identifier, item in validated["relations"].items()],
            )
            connection.executemany(
                "INSERT INTO relation_evidence VALUES (?, ?, ?)",
                [(identifier, evidence_id, position) for identifier, item in validated["relations"].items() for position, evidence_id in enumerate(item["evidence_ids"])],
            )
            connection.commit()
        finally:
            connection.close()
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise KnowledgeError(f"output path already exists: {target}") from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"release_id": validated["release_id"], "published_at": validated["published_at"], "path": str(target)}


class KnowledgeReader:
    """Read a validated public release without importing runtime configuration."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        if not self.path.is_file():
            raise KnowledgeError(f"database does not exist or is not a file: {self.path}")
        try:
            self.connection = sqlite3.connect(f"file:{quote(str(self.path))}?mode=ro", uri=True)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only = ON")
            self._validate_shape()
            self.release_id, self.published_at = self._metadata()
        except (sqlite3.Error, KnowledgeError) as exc:
            if hasattr(self, "connection"):
                self.connection.close()
            raise KnowledgeError(f"invalid VitaX knowledge database: {exc}") from exc

    def __enter__(self) -> "KnowledgeReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    def _metadata(self) -> tuple[str, str]:
        try:
            rows = dict(self.connection.execute("SELECT key, value FROM metadata"))
        except sqlite3.Error as exc:
            raise KnowledgeError("metadata table is missing") from exc
        if rows.get("schema_version") != "1" or not rows.get("release_id") or not rows.get("published_at"):
            raise KnowledgeError("unsupported schema or missing release metadata")
        return rows["release_id"], rows["published_at"]

    def _validate_shape(self) -> None:
        for table, required_columns in _REQUIRED_COLUMNS.items():
            columns = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
            if not required_columns <= columns:
                raise KnowledgeError("required table or columns are missing")
        fts_sql = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'knowledge_fts'"
        ).fetchone()
        if fts_sql is None or "virtual table" not in fts_sql[0].lower() or "using fts5" not in fts_sql[0].lower():
            raise KnowledgeError("knowledge_fts must be an FTS5 virtual table")

    def _response(self, **payload: object) -> dict[str, object]:
        return {"release_id": self.release_id, "published_at": self.published_at, **payload}

    @staticmethod
    def _limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
            raise KnowledgeError(f"limit must be between 1 and {MAX_LIMIT}")
        return limit

    def _evidence_ids(self, table: str, owner_column: str, owner_id: str) -> list[str]:
        return [row[0] for row in self.connection.execute(
            f"SELECT evidence_id FROM {table} WHERE {owner_column} = ? ORDER BY position", (owner_id,)
        )]

    def search(self, query: str, limit: int = 10, kind: str | None = None) -> dict[str, object]:
        """Rank matches by relevance, optionally restricted to one validated kind."""
        if not isinstance(query, str) or not query or len(query) > MAX_QUERY_LENGTH:
            raise KnowledgeError(f"query must be a nonempty string up to {MAX_QUERY_LENGTH} characters")
        limit = self._limit(limit)
        if any("\u3400" <= character <= "\u9fff" for character in query):
            # ponytail: scan small public text; use an index only after measured latency requires it.
            predicate = ""
            parameters: tuple[object, ...] = (query, query)
            if kind is not None:
                predicate = " AND kind = ?"
                parameters += (validate_kind(kind),)
            rows = self.connection.execute(
                "SELECT knowledge_id,kind,title FROM knowledge "
                f"WHERE (instr(title,?)>0 OR instr(body,?)>0){predicate} "
                "ORDER BY CASE WHEN instr(title,?)>0 THEN 0 ELSE 1 END,knowledge_id LIMIT ?",
                (*parameters, query, limit),
            )
            return self._response(results=[dict(row) for row in rows])
        literal_query = '"' + query.replace('"', '""') + '"'
        predicate = ""
        parameters: tuple[object, ...] = (literal_query, limit)
        if kind is not None:
            predicate = " AND k.kind = ?"
            parameters = (literal_query, validate_kind(kind), limit)
        rows = self.connection.execute(
            "SELECT k.knowledge_id, k.kind, k.title FROM knowledge_fts f "
            "JOIN knowledge k ON k.knowledge_id = f.knowledge_id "
            f"WHERE knowledge_fts MATCH ?{predicate} "
            "ORDER BY bm25(knowledge_fts), k.knowledge_id LIMIT ?",
            parameters,
        )
        return self._response(results=[dict(row) for row in rows])

    def list_knowledge(self, kind: str | None = None, limit: int = DEFAULT_LIMIT) -> dict[str, object]:
        """List stable knowledge rows, optionally filtered to one validated kind."""
        limit = self._limit(limit)
        if kind is None:
            rows = self.connection.execute(
                "SELECT knowledge_id, kind, title FROM knowledge ORDER BY knowledge_id LIMIT ?", (limit,)
            )
        else:
            rows = self.connection.execute(
                "SELECT knowledge_id, kind, title FROM knowledge WHERE kind = ? ORDER BY knowledge_id LIMIT ?",
                (validate_kind(kind), limit),
            )
        return self._response(results=[dict(row) for row in rows])

    def list_entities(self, limit: int = DEFAULT_LIMIT) -> dict[str, object]:
        """List stable entity rows so a caller can discover relation entry points."""
        limit = self._limit(limit)
        rows = self.connection.execute(
            "SELECT entity_id, name FROM entities ORDER BY entity_id LIMIT ?", (limit,)
        )
        return self._response(results=[dict(row) for row in rows])

    def read_knowledge(self, knowledge_id: str) -> dict[str, object]:
        row = self.connection.execute("SELECT knowledge_id, kind, title, body FROM knowledge WHERE knowledge_id = ?", (knowledge_id,)).fetchone()
        if row is None:
            raise KnowledgeNotFound(f"knowledge item not found: {knowledge_id}")
        item = dict(row)
        item["evidence_ids"] = self._evidence_ids("knowledge_evidence", "knowledge_id", knowledge_id)
        return self._response(knowledge=item)

    def read_evidence(self, evidence_id: str) -> dict[str, object]:
        row = self.connection.execute(
            "SELECT e.evidence_id, e.revision_id, e.locator, e.quote, d.doc_id, d.title, d.source_url "
            "FROM evidence e JOIN documents d ON d.revision_id = e.revision_id WHERE e.evidence_id = ?", (evidence_id,)
        ).fetchone()
        if row is None:
            raise KnowledgeNotFound(f"evidence item not found: {evidence_id}")
        value = dict(row)
        value["document"] = {key: value.pop(key) for key in ("doc_id", "title", "source_url")}
        return self._response(evidence=value)

    def related(self, entity_id: str, limit: int = 10) -> dict[str, object]:
        limit = self._limit(limit)
        if self.connection.execute("SELECT 1 FROM entities WHERE entity_id = ?", (entity_id,)).fetchone() is None:
            raise KnowledgeNotFound(f"entity not found: {entity_id}")
        rows = self.connection.execute(
            "SELECT r.relation_id, r.source_id, r.target_id, r.relation_type, "
            "s.name AS source_name, t.name AS target_name FROM relations r "
            "JOIN entities s ON s.entity_id = r.source_id JOIN entities t ON t.entity_id = r.target_id "
            "WHERE r.source_id = ? OR r.target_id = ? ORDER BY r.relation_id LIMIT ?", (entity_id, entity_id, limit),
        ).fetchall()
        relations = []
        for row in rows:
            value = dict(row)
            relation_id = value["relation_id"]
            value["evidence_ids"] = self._evidence_ids("relation_evidence", "relation_id", relation_id)
            relations.append(value)
        return self._response(entity_id=entity_id, relations=relations)
