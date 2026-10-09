"""HTTP contract tests for the shared read-only VitaX knowledge API."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vitax.api import _parser, create_app
from vitax.knowledge import KnowledgeError, build


RELEASE_ID = "release-2026-09-09"
PRIVATE_SENTINEL = "PRIVATE_SENTINEL"


def _projection() -> dict[str, object]:
    """Reuse the accepted public DTO shape with one private record per collection."""
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
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
            {
                "doc_id": "doc-private",
                "revision_id": "rev-private",
                "title": f"{PRIVATE_SENTINEL} document",
                "source_url": "https://example.test/private",
                "visibility": "private",
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
            {
                "evidence_id": "ev-private",
                "revision_id": "rev-a",
                "locator": "paragraph:9",
                "quote": f"{PRIVATE_SENTINEL} quote",
                "visibility": "private",
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
            {
                "knowledge_id": "article-private",
                "kind": "article",
                "title": f"{PRIVATE_SENTINEL} knowledge",
                "body": f"{PRIVATE_SENTINEL} body",
                "evidence_ids": ["ev-a"],
                "visibility": "private",
            },
        ],
        "entities": [
            {"entity_id": "entity-alpha", "name": "Alpha", "visibility": "public"},
            {"entity_id": "entity-beta", "name": "Beta", "visibility": "public"},
            {"entity_id": "entity-private", "name": f"{PRIVATE_SENTINEL} entity", "visibility": "private"},
        ],
        "relations": [
            {
                "relation_id": "rel-alpha-beta",
                "source_id": "entity-alpha",
                "target_id": "entity-beta",
                "relation_type": "supports",
                "evidence_ids": ["ev-a", "ev-b"],
                "visibility": "public",
            },
            {
                "relation_id": "rel-private",
                "source_id": "entity-alpha",
                "target_id": "entity-beta",
                "relation_type": f"{PRIVATE_SENTINEL} relation",
                "evidence_ids": ["ev-b"],
                "visibility": "private",
            },
        ],
    }


@pytest.fixture
def release_database(tmp_path: Path) -> Path:
    database = tmp_path / "public.sqlite"
    build(_projection(), database)
    return database


def _ranking_projection() -> dict[str, object]:
    """One term matches both kinds, ranked so the article precedes the wiki."""
    projection = _projection()
    projection["knowledge"].extend(
        [
            {
                "knowledge_id": "article-dominant",
                "kind": "article",
                "title": "bounded bounded",
                "body": "bounded " * 8 + "article rows rank first.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
            {
                "knowledge_id": "wiki-matched",
                "kind": "wiki",
                "title": "Bounded wiki",
                "body": "One bounded mention only.",
                "evidence_ids": ["ev-a"],
                "visibility": "public",
            },
        ]
    )
    return projection


@pytest.fixture
def client(release_database: Path) -> TestClient:
    with TestClient(create_app(release_database)) as test_client:
        yield test_client


def test_kind_filtered_search_applies_kind_before_the_limit(tmp_path: Path) -> None:
    """Breaks if a kind-filtered search can omit the requested kind by relevance rank."""
    database = tmp_path / "ranking.sqlite"
    build(_ranking_projection(), database)

    with TestClient(create_app(database)) as client:
        unfiltered = client.get("/api/knowledge", params={"q": "bounded", "limit": 1})
        wiki = client.get("/api/knowledge", params={"q": "bounded", "kind": "wiki", "limit": 1})
        article = client.get("/api/knowledge", params={"q": "bounded", "kind": "article", "limit": 1})

    assert [row["knowledge_id"] for row in unfiltered.json()["results"]] == ["article-dominant"]
    assert [row["knowledge_id"] for row in wiki.json()["results"]] == ["wiki-matched"]
    assert [row["kind"] for row in wiki.json()["results"]] == ["wiki"]
    assert [row["knowledge_id"] for row in article.json()["results"]] == ["article-dominant"]
    assert {unfiltered.json()["release_id"], wiki.json()["release_id"], article.json()["release_id"]} == {RELEASE_ID}


def test_release_and_health_endpoints_report_the_served_release(client: TestClient) -> None:
    """Breaks if a client cannot confirm which release the API reads."""
    release = client.get("/api/release")
    health = client.get("/api/health")

    assert release.status_code == 200
    assert release.json() == {"release_id": RELEASE_ID, "published_at": "2026-09-09T12:00:00Z"}
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["release_id"] == RELEASE_ID


def test_list_search_read_evidence_and_related_endpoints_share_one_release(client: TestClient) -> None:
    """Breaks if any read path bypasses the shared reader or mixes release metadata."""
    listing = client.get("/api/knowledge")
    articles = client.get("/api/knowledge", params={"kind": "article"})
    bounded = client.get("/api/knowledge", params={"limit": 1})
    search = client.get("/api/knowledge", params={"q": "Alpha", "limit": 5})
    wiki_search = client.get("/api/knowledge", params={"q": "combines", "kind": "wiki"})
    article = client.get("/api/knowledge/article-a")
    wiki = client.get("/api/knowledge/wiki-ai")
    evidence = client.get("/api/evidence/ev-b")
    entities = client.get("/api/entities")
    first_entity = client.get("/api/entities", params={"limit": 1})
    related = client.get("/api/entities/entity-alpha/related")

    assert listing.status_code == 200
    assert [row["knowledge_id"] for row in listing.json()["results"]] == ["article-a", "wiki-ai"]
    assert [row["kind"] for row in listing.json()["results"]] == ["article", "wiki"]
    assert [row["knowledge_id"] for row in articles.json()["results"]] == ["article-a"]
    assert len(bounded.json()["results"]) == 1
    assert [row["knowledge_id"] for row in search.json()["results"]] == ["article-a", "wiki-ai"]
    assert [row["knowledge_id"] for row in wiki_search.json()["results"]] == ["wiki-ai"]
    assert article.json()["knowledge"]["kind"] == "article"
    assert article.json()["knowledge"]["evidence_ids"] == ["ev-a"]
    assert wiki.json()["knowledge"]["evidence_ids"] == ["ev-a", "ev-b"]
    assert evidence.json()["evidence"]["document"]["doc_id"] == "doc-b"
    assert evidence.json()["evidence"]["document"]["source_url"] == "https://example.test/b"
    assert [row["entity_id"] for row in entities.json()["results"]] == ["entity-alpha", "entity-beta"]
    assert [row["entity_id"] for row in first_entity.json()["results"]] == ["entity-alpha"]
    assert related.json()["relations"][0]["relation_type"] == "supports"
    assert related.json()["relations"][0]["evidence_ids"] == ["ev-a", "ev-b"]

    responses = [listing, articles, bounded, search, wiki_search, article, wiki, evidence, entities, first_entity, related]
    assert {response.json()["release_id"] for response in responses} == {RELEASE_ID}


def test_unknown_identifiers_and_paths_return_json_404_without_server_detail(
    client: TestClient, release_database: Path
) -> None:
    """Breaks if unknown IDs leak internals instead of a bounded JSON 404."""
    responses = [
        client.get("/api/knowledge/missing-id"),
        client.get("/api/evidence/missing-id"),
        client.get("/api/entities/missing-id/related"),
        client.get("/api/does-not-exist"),
        client.get("/api"),
        client.get("/not-an-api-route"),
        client.get("/knowledge"),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert "not found" in response.json()["error"].lower()
        assert "Traceback" not in response.text
        assert str(release_database) not in response.text
        assert ".sqlite" not in response.text


@pytest.mark.parametrize(
    ("path", "params", "fragment"),
    [
        ("/api/knowledge", {"limit": 0}, "limit must be between 1 and 100"),
        ("/api/knowledge", {"limit": 101}, "limit must be between 1 and 100"),
        ("/api/knowledge", {"kind": "article OR 1=1"}, "kind must be article or wiki"),
        ("/api/knowledge", {"q": "Alpha", "kind": "unknown"}, "kind must be article or wiki"),
        ("/api/entities", {"limit": 0}, "limit must be between 1 and 100"),
        ("/api/entities/entity-alpha/related", {"limit": 0}, "limit must be between 1 and 100"),
    ],
)
def test_invalid_reader_input_returns_a_bounded_client_error(
    client: TestClient, release_database: Path, path: str, params: dict[str, object], fragment: str
) -> None:
    """Breaks if reader validation surfaces as a server error or leaks paths."""
    response = client.get(path, params=params)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert fragment in response.json()["error"]
    assert "Traceback" not in response.text
    assert str(release_database) not in response.text


def test_non_integer_limit_is_rejected_without_server_detail(client: TestClient) -> None:
    """Breaks if malformed query input becomes an unhandled server exception."""
    response = client.get("/api/knowledge", params={"limit": "ten"})

    assert 400 <= response.status_code < 500
    assert response.headers["content-type"].startswith("application/json")
    assert "Traceback" not in response.text


def test_private_candidate_records_are_unreachable_through_http(client: TestClient) -> None:
    """Breaks if an endpoint can discover private documents, evidence, or entities."""
    for path in (
        "/api/release",
        "/api/health",
        "/api/knowledge",
        "/api/entities",
        "/api/knowledge/article-private",
        "/api/evidence/ev-private",
        "/api/entities/entity-private/related",
    ):
        assert PRIVATE_SENTINEL not in client.get(path).text

    assert client.get("/api/knowledge", params={"q": PRIVATE_SENTINEL}).json()["results"] == []
    assert client.get("/api/knowledge/article-private").status_code == 404
    assert client.get("/api/evidence/ev-private").status_code == 404
    assert client.get("/api/entities/entity-private/related").status_code == 404


def test_factory_rejects_invalid_release_and_site_inputs(tmp_path: Path) -> None:
    """Breaks if the app factory accepts a missing release or an unbuilt site directory."""
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(KnowledgeError, match="does not exist"):
        create_app(missing)
    assert not missing.exists()

    database = tmp_path / "public.sqlite"
    build(_projection(), database)
    empty_site = tmp_path / "site"
    empty_site.mkdir()
    with pytest.raises(KnowledgeError, match="index.html"):
        create_app(database, site_dir=empty_site)


def test_a_release_removed_after_startup_fails_closed_without_paths(release_database: Path, tmp_path: Path) -> None:
    """Breaks if a vanished release leaks its path or recreates an empty database."""
    client = TestClient(create_app(release_database))
    release_database.unlink()

    response = client.get("/api/knowledge")

    assert response.status_code == 500
    assert response.json() == {"error": "knowledge release is unavailable"}
    assert str(tmp_path) not in response.text
    assert "Traceback" not in response.text
    assert not release_database.exists()


def test_static_site_serves_files_and_falls_back_to_index_for_client_routes(
    release_database: Path, tmp_path: Path
) -> None:
    """Breaks if built files, client routes, API 404s, or asset failures are conflated.

    A client route without a prerendered page still receives the built shell so the
    reader can bootstrap, but it must report 404 rather than a successful page.
    """
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>VitaX reader</title>", encoding="utf-8")
    (site / "assets" / "app.js").write_text("console.log('reader');", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("OUTSIDE_SENTINEL", encoding="utf-8")

    with TestClient(create_app(release_database, site_dir=site)) as client:
        root = client.get("/")
        client_route = client.get("/wiki/contextual-retrieval-vs-graphrag")
        knowledge_list = client.get("/knowledge")
        script = client.get("/assets/app.js")
        missing_asset = client.get("/assets/missing.js")
        api_unknown = client.get("/api/unknown")
        traversal = client.get("/..%2Foutside.txt")

    assert root.status_code == 200
    assert "VitaX reader" in root.text
    assert client_route.status_code == 404
    assert "VitaX reader" in client_route.text
    assert knowledge_list.status_code == 200
    assert "VitaX reader" in knowledge_list.text
    assert script.status_code == 200
    assert "console.log" in script.text
    assert missing_asset.status_code == 404
    assert "VitaX reader" not in missing_asset.text
    assert api_unknown.status_code == 404
    assert api_unknown.headers["content-type"].startswith("application/json")
    assert api_unknown.json()["error"]
    assert "OUTSIDE_SENTINEL" not in traversal.text


def test_importing_the_api_module_does_not_load_environment_or_open_a_database(tmp_path: Path) -> None:
    """Breaks if importing the read API reads credentials or touches a database."""
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    (home / ".hermes" / ".env").write_text("HERMES_ENV_SENTINEL=leaked\n", encoding="utf-8")
    script = (
        "import json, os, sys; import vitax.api; "
        "print(json.dumps({'sentinel': os.environ.get('HERMES_ENV_SENTINEL'), 'config': 'config' in sys.modules}))"
    )
    environment = {key: value for key, value in os.environ.items() if key != "OMNIGRAPH_LOAD_ENV"}
    environment["HOME"] = str(home)

    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=environment, check=False
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"sentinel": None, "config": False}
    assert list(tmp_path.glob("*.sqlite")) == []


def test_cli_defaults_to_loopback_and_requires_a_database(tmp_path: Path) -> None:
    """Breaks if the local entry point binds remotely by default or starts without a release."""
    parsed = _parser().parse_args([str(tmp_path / "public.sqlite")])
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 8000
    assert parsed.site_dir is None

    environment = {**os.environ, "OMNIGRAPH_LOAD_ENV": "0", "HOME": str(tmp_path / "home")}
    without_database = subprocess.run(
        [sys.executable, "-m", "vitax.api"], capture_output=True, text=True, env=environment, check=False
    )
    missing_release = subprocess.run(
        [sys.executable, "-m", "vitax.api", str(tmp_path / "missing.sqlite")],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    help_text = subprocess.run(
        [sys.executable, "-m", "vitax.api", "--help"], capture_output=True, text=True, env=environment, check=False
    )

    assert without_database.returncode != 0
    assert "database" in without_database.stderr
    assert "Traceback" not in without_database.stderr
    assert missing_release.returncode == 2
    assert "does not exist" in missing_release.stderr
    assert "Traceback" not in missing_release.stderr
    assert help_text.returncode == 0
    assert "127.0.0.1" in help_text.stdout
    assert "--site-dir" in help_text.stdout


def test_knowledge_detail_renders_markdown_safely_and_keeps_evidence(tmp_path):
    projection = _projection()
    projection['knowledge'][1]['body'] = '# Wiki heading\n\n**Definition**\n\n<script>unsafe()</script>'
    database = tmp_path / 'wiki.sqlite'
    build(projection, database)
    with TestClient(create_app(database, mount_mcp=False)) as client:
        item = client.get('/api/knowledge/wiki-ai').json()['knowledge']
    assert '<h1>Wiki heading</h1>' in item['rendered_html']
    assert '<strong>Definition</strong>' in item['rendered_html']
    assert '<script' not in item['rendered_html'] and 'unsafe()' not in item['rendered_html']
    assert item['evidence_ids'] == ['ev-a', 'ev-b']
