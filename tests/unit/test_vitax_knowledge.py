"""Offline behavior tests for VitaX's public knowledge read model."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from vitax.knowledge import KnowledgeError, KnowledgeReader, build


def _projection() -> dict[str, object]:
    return {
        "schema_version": 1,
        "release_id": "release-2026-09-09",
        "published_at": "2026-09-09T12:00:00Z",
        "documents": [
            {
                "doc_id": "doc-a",
                "revision_id": "rev-a",
                "title": "First source",
                "source_url": "https://example.test/a",
                "source_published_at": None,
                "fetched_at": "2026-09-09T11:00:00Z",
                "visibility": "public",
            },
            {
                "doc_id": "doc-b",
                "revision_id": "rev-b",
                "title": "Second source",
                "source_url": "https://example.test/b",
                "source_published_at": None,
                "fetched_at": None,
                "visibility": "public",
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev-a",
                "revision_id": "rev-a",
                "locator": "paragraph:2",
                "quote": "Alpha source quote",
                "visibility": "public",
            },
            {
                "evidence_id": "ev-b",
                "revision_id": "rev-b",
                "locator": "section:1",
                "quote": "Beta source quote",
                "visibility": "public",
            },
        ],
        "knowledge": [
            {
                "knowledge_id": "article-a",
                "kind": "article",
                "title": "Alpha interpretation",
                "body": "Alpha interpretation about Chinese AI research.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
            {
                "knowledge_id": "wiki-ai",
                "kind": "wiki",
                "title": "AI Wiki",
                "body": "A wiki combines Alpha and Beta evidence.",
                "evidence_ids": ["ev-a", "ev-b"],
                "visibility": "public",
            },
        ],
        "entities": [
            {"entity_id": "entity-alpha", "name": "Alpha", "visibility": "public"},
            {"entity_id": "entity-beta", "name": "Beta", "visibility": "public"},
        ],
        "relations": [
            {
                "relation_id": "rel-alpha-beta",
                "source_id": "entity-alpha",
                "target_id": "entity-beta",
                "relation_type": "supports",
                "evidence_ids": ["ev-a", "ev-b"],
                "visibility": "public",
            }
        ],
    }


def test_build_reopens_and_searches_article_and_wiki(tmp_path: Path) -> None:
    """Breaks if public knowledge is not persisted in the release-bound FTS index."""
    database = tmp_path / "public.sqlite"
    build(_projection(), database)

    with KnowledgeReader(database) as reader:
        article = reader.read_knowledge("article-a")
        wiki = reader.read_knowledge("wiki-ai")
        matches = reader.search("Alpha", limit=5)

    assert article["release_id"] == "release-2026-09-09"
    assert article["knowledge"]["kind"] == "article"
    assert wiki["knowledge"]["evidence_ids"] == ["ev-a", "ev-b"]
    assert [item["knowledge_id"] for item in matches["results"]] == [
        "article-a",
        "wiki-ai",
    ]


def test_reader_returns_evidence_provenance_and_cross_document_relations(tmp_path: Path) -> None:
    """Breaks if a citation loses its source revision or relations lose their evidence."""
    database = tmp_path / "public.sqlite"
    build(_projection(), database)

    with KnowledgeReader(database) as reader:
        evidence = reader.read_evidence("ev-b")
        related = reader.related("entity-alpha")

    assert evidence["evidence"] == {
        "evidence_id": "ev-b",
        "revision_id": "rev-b",
        "locator": "section:1",
        "quote": "Beta source quote",
        "document": {
            "doc_id": "doc-b",
            "title": "Second source",
            "source_url": "https://example.test/b",
        },
    }
    assert related["relations"][0]["relation_type"] == "supports"
    assert related["relations"][0]["evidence_ids"] == ["ev-a", "ev-b"]


def test_private_and_unknown_projection_data_never_reaches_public_database(tmp_path: Path) -> None:
    """Breaks if the builder serializes source objects instead of its public allowlist."""
    database = tmp_path / "public.sqlite"
    projection = _projection()
    projection["documents"].append(
        {
            "doc_id": "doc-private",
            "revision_id": "rev-private",
            "title": "PRIVATE_SENTINEL",
            "source_url": "https://example.test/private",
            "visibility": "private",
        }
    )
    projection["documents"][0]["raw_html"] = "UNKNOWN_SENTINEL"
    projection["documents"][0]["api_key"] = "UNKNOWN_SECRET_SENTINEL"
    build(projection, database)

    raw = database.read_bytes()
    with KnowledgeReader(database) as reader:
        results = reader.search("PRIVATE_SENTINEL")

    assert b"PRIVATE_SENTINEL" not in raw
    assert b"UNKNOWN_SENTINEL" not in raw
    assert b"UNKNOWN_SECRET_SENTINEL" not in raw
    assert results["results"] == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update({"schema_version": True}), "schema_version must be 1"),
        (lambda p: p.update({"schema_version": 1.0}), "schema_version must be 1"),
        (lambda p: p["documents"][0].update({"title": "   "}), "document.title"),
        (lambda p: p["documents"][0].update({"visibility": []}), "documents.visibility"),
        (lambda p: p["knowledge"][0].update({"kind": {}}), "knowledge.kind"),
        (
            lambda p: p["documents"][0].update({"source_url": "https://user:password@example.test/a"}),
            "must not contain userinfo",
        ),
        (
            lambda p: p["documents"][0].update({"source_url": "https://example.test:not-a-port/a"}),
            "must have a valid host and port",
        ),
        (
            lambda p: p["documents"][0].update({"source_url": "https://bad host.test/a"}),
            "must have a valid host and port",
        ),
        (
            lambda p: p["documents"][0].update({"source_url": "https://[broken"}),
            "must have a valid host and port",
        ),
        (
            lambda p: p["documents"][0].update({"fetched_at": "historical-text"}),
            "document.fetched_at must be an ISO-8601 date, datetime, or null",
        ),
    ],
)
def test_builder_rejects_nonpublic_safe_values_before_creating_target(
    tmp_path: Path, mutate, message: str
) -> None:
    """Breaks if loose DTO types or source credentials reach the public database."""
    projection = _projection()
    mutate(projection)

    with pytest.raises(KnowledgeError, match=message):
        build(projection, tmp_path / "unsafe.sqlite")

    assert not (tmp_path / "unsafe.sqlite").exists()


def test_builder_wraps_non_utf8_projection_errors_without_creating_target(tmp_path: Path) -> None:
    """Breaks if ordinary invalid projection bytes escape the public error contract."""
    projection = tmp_path / "invalid-encoding.json"
    target = tmp_path / "public.sqlite"
    projection.write_bytes(b"\xff")

    with pytest.raises(KnowledgeError, match="cannot read projection JSON"):
        build(projection, target)

    assert not target.exists()


def test_builder_accepts_a_bracketed_ipv6_source_url(tmp_path: Path) -> None:
    """Breaks if valid native URL parsing is replaced with hostname-only validation."""
    projection = _projection()
    projection["documents"][0]["source_url"] = "https://[2001:db8::1]/a"
    database = tmp_path / "public.sqlite"
    build(projection, database)

    with KnowledgeReader(database) as reader:
        evidence = reader.read_evidence("ev-a")

    assert evidence["evidence"]["document"]["source_url"] == "https://[2001:db8::1]/a"


def test_cli_hides_malformed_url_input_behind_a_clear_error(tmp_path: Path) -> None:
    """Breaks if parser failures expose a traceback or credential-bearing URL text."""
    projection = _projection()
    malformed_url = "https://[broken"
    projection["documents"][0]["source_url"] = malformed_url
    source = tmp_path / "projection.json"
    source.write_text(json.dumps(projection), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "vitax", "build", str(source), str(tmp_path / "public.sqlite")],
        capture_output=True,
        text=True,
        env={**os.environ, "OMNIGRAPH_LOAD_ENV": "0", "HOME": str(tmp_path / "home")},
        check=False,
    )

    assert result.returncode != 0
    assert "must have a valid host and port" in result.stderr
    assert "Traceback" not in result.stderr
    assert malformed_url not in result.stderr


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda p: p["evidence"].append(
                {"evidence_id": "ev-private", "revision_id": "rev-a", "locator": "p:3", "quote": "private", "visibility": "private"}
            ) or p["knowledge"][0].update({"evidence_ids": ["ev-private"]}),
            "unknown evidence_id: ev-private",
        ),
        (
            lambda p: p["entities"].append({"entity_id": "entity-private", "name": "private", "visibility": "private"}) or p["relations"][0].update({"target_id": "entity-private"}),
            "references unknown or private entity",
        ),
        (
            lambda p: p["evidence"].append(
                {"evidence_id": "ev-private", "revision_id": "rev-a", "locator": "p:3", "quote": "private", "visibility": "private"}
            ) or p["relations"][0].update({"evidence_ids": ["ev-private"]}),
            "unknown evidence_id: ev-private",
        ),
    ],
)
def test_public_references_to_private_items_are_rejected(tmp_path: Path, mutate, message: str) -> None:
    """Breaks if a public artifact can retain a private provenance edge."""
    projection = _projection()
    mutate(projection)

    with pytest.raises(KnowledgeError, match=message):
        build(projection, tmp_path / "private-edge.sqlite")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda p: p["knowledge"][0].update({"evidence_ids": ["missing"]}),
            "unknown evidence_id: missing",
        ),
        (
            lambda p: p["evidence"].append(dict(p["evidence"][0])),
            "duplicate evidence_id: ev-a",
        ),
        (
            lambda p: p.update({"published_at": "not-a-timestamp"}),
            "published_at must be an ISO-8601 timestamp",
        ),
    ],
)
def test_invalid_projection_does_not_create_or_replace_target(
    tmp_path: Path, mutate, message: str
) -> None:
    """Breaks if validation happens after the release target is made visible."""
    missing_target = tmp_path / "missing.sqlite"
    invalid = _projection()
    mutate(invalid)
    with pytest.raises(KnowledgeError, match=message):
        build(invalid, missing_target)
    assert not missing_target.exists()

    existing_target = tmp_path / "existing.sqlite"
    existing_target.write_bytes(b"preexisting")
    with pytest.raises(KnowledgeError, match="already exists"):
        build(_projection(), existing_target)
    assert existing_target.read_bytes() == b"preexisting"


def test_builder_refuses_a_symlink_target_without_changing_its_destination(tmp_path: Path) -> None:
    """Breaks if promotion follows or replaces a pre-existing symlink."""
    destination = tmp_path / "destination.sqlite"
    destination.write_bytes(b"preexisting")
    target = tmp_path / "public.sqlite"
    target.symlink_to(destination)

    with pytest.raises(KnowledgeError, match="already exists"):
        build(_projection(), target)

    assert target.is_symlink()
    assert destination.read_bytes() == b"preexisting"


def test_reader_rejects_metadata_only_database_and_stays_query_only(tmp_path: Path) -> None:
    """Breaks if an incomplete database opens or a reader can mutate a release."""
    malformed = tmp_path / "metadata-only.sqlite"
    connection = sqlite3.connect(malformed)
    connection.executescript(
        "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "INSERT INTO metadata VALUES ('schema_version', '1');"
        "INSERT INTO metadata VALUES ('release_id', 'release');"
        "INSERT INTO metadata VALUES ('published_at', '2026-09-09T12:00:00Z');"
    )
    connection.close()
    with pytest.raises(KnowledgeError, match="required table or columns"):
        KnowledgeReader(malformed)
    malformed_cli = subprocess.run(
        [sys.executable, "-m", "vitax", "search", str(malformed), "Alpha"],
        capture_output=True,
        text=True,
        env={**os.environ, "OMNIGRAPH_LOAD_ENV": "0", "HOME": str(tmp_path / "home")},
        check=False,
    )
    assert malformed_cli.returncode != 0
    assert "required table or columns" in malformed_cli.stderr
    assert "Traceback" not in malformed_cli.stderr

    database = tmp_path / "public.sqlite"
    build(_projection(), database)
    with KnowledgeReader(database) as reader:
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute("DELETE FROM knowledge")


def test_reader_and_cli_reject_missing_paths_and_invalid_limits(tmp_path: Path) -> None:
    """Breaks if reads create files or unbounded query input is accepted."""
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(KnowledgeError, match="does not exist"):
        KnowledgeReader(missing)
    assert not missing.exists()

    database = tmp_path / "public.sqlite"
    source = tmp_path / "projection.json"
    source.write_text(json.dumps(_projection()), encoding="utf-8")
    environment = {**os.environ, "OMNIGRAPH_LOAD_ENV": "0", "HOME": str(tmp_path / "home")}
    built = subprocess.run(
        [sys.executable, "-m", "vitax", "build", str(source), str(database)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    invalid_limit = subprocess.run(
        [sys.executable, "-m", "vitax", "search", str(database), "Alpha", "--limit", "0"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    search = subprocess.run(
        [sys.executable, "-m", "vitax", "search", str(database), "Alpha"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    evidence = subprocess.run(
        [sys.executable, "-m", "vitax", "read-evidence", str(database), "ev-a"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    related = subprocess.run(
        [sys.executable, "-m", "vitax", "related", str(database), "entity-alpha"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert built.returncode == 0
    assert json.loads(built.stdout)["release_id"] == "release-2026-09-09"
    assert invalid_limit.returncode != 0
    assert "limit must be between 1 and 100" in invalid_limit.stderr
    assert json.loads(search.stdout)["results"][0]["knowledge_id"] == "article-a"
    assert json.loads(evidence.stdout)["evidence"]["document"]["doc_id"] == "doc-a"
    assert json.loads(related.stdout)["relations"][0]["target_id"] == "entity-beta"
