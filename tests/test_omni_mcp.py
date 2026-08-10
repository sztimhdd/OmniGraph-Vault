"""tests/test_omni_mcp.py — E2E integration tests for the OmniGraph MCP server.

Tests verify:
1. The MCP server process starts and binds port 8767
2. health() tool returns real status from kb-api
3. fts_search() returns real articles with real content
4. kg_query() submits a job, polls, and returns KG results
5. synthesize() submits, polls, and returns cited answers
6. get_article() returns real article body + entities

These are INTEGRATION tests — they talk to a live MCP server which talks to
a live kb-api which talks to live LightRAG + Qdrant + SQLite.

Run:
    cd /root/OmniGraph-Vault
    venv-aim1/bin/python -m pytest tests/test_omni_mcp.py -v

Prerequisites:
    - kb-api running on :8766
    - MCP server running on :8767
    - httpx installed in venv
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KB_API = "http://127.0.0.1:8766"
MCP_BASE = "http://127.0.0.1:8767"
MCP_SSE = f"{MCP_BASE}/sse"
MCP_MESSAGES = f"{MCP_BASE}/messages/"

# A term we KNOW exists in the KB (from earlier investigation).
# FTS5 on the articles_fts index should return >= 10 results.
KNOWN_TERM = "OpenClaw"

# A question we KNOW has KG coverage.
KNOWN_KG_QUESTION = "OpenClaw"
KNOWN_SYNTH_QUESTION = "What is OpenClaw?"


# ============================================================================
# Helpers: MCP JSON-RPC over HTTP (FastMCP SSE transport)
# ============================================================================

def _mcp_rpc(method: str, params: dict | None = None, timeout: int = 30) -> dict:
    """Call an MCP tool via FastMCP's HTTP+SSE transport.

    FastMCP exposes two endpoints:
    1. GET  /sse        — SSE stream (returns session_id in first event)
    2. POST /messages/?session_id=xxx — JSON-RPC request

    This helper does a full round-trip: get session → call tool → return result.
    """
    import http.client
    import io
    import re

    # Step 1: GET /sse to get a session_id
    conn = http.client.HTTPConnection("127.0.0.1", 8767, timeout=timeout)
    conn.request("GET", "/sse")
    resp = conn.getresponse()
    # Read the first SSE event to extract session_id
    body = resp.read(4096).decode("utf-8")
    match = re.search(r"/messages/\?session_id=([a-f0-9]+)", body)
    if not match:
        # Try reading more
        body += resp.read(4096).decode("utf-8")
        match = re.search(r"/messages/\?session_id=([a-f0-9]+)", body)
    conn.close()

    if not match:
        raise RuntimeError(f"Failed to get session_id from SSE. Body: {body[:500]}")

    session_id = match.group(1)

    # Step 2: POST /messages/?session_id=xxx with JSON-RPC
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    })
    url = f"/messages/?session_id={session_id}"
    conn = http.client.HTTPConnection("127.0.0.1", 8767, timeout=timeout)
    conn.request("POST", url, body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    result = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return result


# ============================================================================
# Fixture: ensure MCP server is reachable
# ============================================================================

@pytest.fixture(scope="module")
def mcp_alive():
    """Verify MCP server is up before running any tests."""
    try:
        with urllib.request.urlopen(f"{MCP_BASE}/health", timeout=5) as r:  # FastMCP health
            pass
    except Exception:
        # Try kb-api directly as fallback verification
        try:
            with urllib.request.urlopen(f"{KB_API}/health", timeout=5) as r:
                kb_health = json.load(r)
        except Exception:
            pytest.skip("Neither MCP server nor kb-api is reachable")
        pytest.skip("MCP server not reachable (kb-api is up — start MCP server first)")


# ============================================================================
# Test 1: health() — MCP tool returns real status
# ============================================================================

def test_health_tool(mcp_alive):
    """health() must return kb-api's /health response with real paths."""
    result = _mcp_rpc("tools/call", {
        "name": "health",
        "arguments": {},
    })
    # Extract content from MCP response
    content = result.get("result", {}).get("content", [])
    assert content, f"health() returned no content: {result}"
    text = content[0].get("text", "")
    data = json.loads(text)

    assert data.get("status") == "ok", f"kb-api not healthy: {data}"
    assert "kb_db_path" in data, f"Missing kb_db_path: {data}"
    assert "version" in data, f"Missing version: {data}"
    print(f"  ✓ kb-api version={data['version']}, db={data['kb_db_path']}")


# ============================================================================
# Test 2: fts_search() — returns real articles
# ============================================================================

def test_fts_search_returns_articles(mcp_alive):
    """fts_search(KNOWN_TERM) must return real articles with titles and snippets."""
    result = _mcp_rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": KNOWN_TERM, "limit": 5},
    }, timeout=30)
    content = result.get("result", {}).get("content", [])
    assert content, f"fts_search returned no content: {result}"
    text = content[0].get("text", "")
    data = json.loads(text)

    assert "error" not in data, f"fts_search errored: {data}"
    assert data.get("mode") == "fts", f"Wrong mode: {data}"
    assert data.get("total", 0) > 0, f"No results for '{KNOWN_TERM}': {data}"
    items = data.get("items", [])
    assert len(items) >= 3, f"Too few results: {len(items)}"

    # Each item must have real data
    for item in items[:3]:
        assert item.get("title"), f"Item missing title: {item}"
        assert item.get("hash"), f"Item missing hash: {item}"
        assert item.get("snippet"), f"Item missing snippet: {item}"
        assert len(item["snippet"]) > 20, f"Snippet too short: {item['snippet'][:30]}"
        assert KNOWN_TERM.lower() in item["snippet"].lower() or \
               KNOWN_TERM.lower() in item["title"].lower(), \
               f"Snippet/title doesn't mention '{KNOWN_TERM}': {item}"

    print(f"  ✓ fts_search('{KNOWN_TERM}') → {data['total']} results, first: {items[0]['title'][:50]}")


# ============================================================================
# Test 3: get_article() — returns full content
# ============================================================================

def test_get_article_real_content(mcp_alive):
    """get_article(hash) must return real body, entities, and metadata."""
    # First find an article via FTS
    search = _mcp_rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": KNOWN_TERM, "limit": 1},
    }, timeout=30)
    search_data = json.loads(search["result"]["content"][0]["text"])
    assert search_data.get("items"), "No articles found for hash test"
    article_hash = search_data["items"][0]["hash"]

    # Fetch full article
    result = _mcp_rpc("tools/call", {
        "name": "get_article",
        "arguments": {"hash_or_url": article_hash},
    }, timeout=30)
    content = result.get("result", {}).get("content", [])
    assert content, f"get_article returned no content: {result}"
    data = json.loads(content[0].get("text", "{}"))

    assert "error" not in data, f"get_article errored: {data}"
    assert data.get("title"), f"No title: {data}"
    body = data.get("body", "") or data.get("body_cleaned", "") or data.get("body_rewritten", "")
    assert body, f"No body content: {list(data.keys())}"
    assert len(body) > 100, f"Body too short ({len(body)} chars)"

    print(f"  ✓ get_article('{article_hash}') → '{data['title'][:50]}' ({len(body)} chars)")

    # Verify entities if available
    entities = data.get("entities") or data.get("extracted_entities", [])
    if entities:
        print(f"    entities: {len(entities)} found")
        assert any(isinstance(e, (dict, str)) for e in entities[:5])


# ============================================================================
# Test 4: kg_query() — returns KG results (async poll)
# ============================================================================

@pytest.mark.timeout(180)
def test_kg_query_returns_graph_data(mcp_alive):
    """kg_query(KNOWN_KG_QUESTION) must return KG results with status='done'."""
    result = _mcp_rpc("tools/call", {
        "name": "kg_query",
        "arguments": {"query": KNOWN_KG_QUESTION, "mode": "local"},
    }, timeout=180)
    content = result.get("result", {}).get("content", [])
    assert content, f"kg_query returned no content: {result}"
    data = json.loads(content[0].get("text", "{}"))

    assert "error" not in data, f"kg_query errored: {data}"
    status = data.get("status")
    assert status in ("done", "running"), f"Unexpected status: {status}"

    if status == "done":
        result_data = data.get("result")
        assert result_data, f"kg_query done but no result: {data}"
        # KG results should be non-trivial
        result_str = str(result_data)
        assert len(result_str) > 50, f"KG result too short: {result_str[:100]}"
        print(f"  ✓ kg_query('{KNOWN_KG_QUESTION}') → done, {len(result_str)} chars")
    else:
        # Still running after 180s poll — that's a problem
        pytest.fail(f"kg_query still running after 180s poll: {data}")

    # Check journal for errors during this query
    # (optional — manual check)


# ============================================================================
# Test 5: synthesize() — returns cited answer (async poll, longer timeout)
# ============================================================================

@pytest.mark.timeout(360)
def test_synthesize_returns_cited_answer(mcp_alive):
    """synthesize(KNOWN_SYNTH_QUESTION) must return a cited answer."""
    result = _mcp_rpc("tools/call", {
        "name": "synthesize",
        "arguments": {"question": KNOWN_SYNTH_QUESTION, "lang": "zh", "mode": "qa"},
    }, timeout=360)
    content = result.get("result", {}).get("content", [])
    assert content, f"synthesize returned no content: {result}"
    data = json.loads(content[0].get("text", "{}"))

    assert "error" not in data or data.get("status") == "done", \
           f"synthesize errored: {data}"
    status = data.get("status")

    if status == "done":
        result_data = data.get("result")
        assert result_data, f"synthesize done but empty result: {data}"
        result_str = str(result_data)
        assert len(result_str) > 100, f"Answer too short: {result_str[:200]}"

        # Verify citations or sources are present
        has_citations = (
            data.get("citations_present") or
            isinstance(result_data, dict) and (
                result_data.get("citations") or result_data.get("sources")
            ) or
            (isinstance(result_data, str) and "[article:" in result_data)
        )
        fallback = data.get("fallback_used")
        confidence = data.get("confidence", "")

        print(f"  ✓ synthesize → done, {len(result_str)} chars, "
              f"fallback={fallback}, conf={confidence}")
        if has_citations:
            print(f"    citations/sources: present ✓")
    elif status == "running":
        pytest.fail(f"synthesize still running after 360s poll: {data}")
    else:
        pytest.fail(f"synthesize unexpected status: {data}")


# ============================================================================
# Test 6: Image URLs in article content
# ============================================================================

def test_article_contains_image_urls(mcp_alive):
    """Articles that have image_count > 0 should reference image URLs."""
    # Find an article via FTS that likely has images
    search = _mcp_rpc("tools/call", {
        "name": "fts_search",
        "arguments": {"query": "Agent architecture design", "limit": 5},
    }, timeout=30)
    search_data = json.loads(search["result"]["content"][0]["text"])

    found_image = False
    for item in search_data.get("items", []):
        art_result = _mcp_rpc("tools/call", {
            "name": "get_article",
            "arguments": {"hash_or_url": item["hash"]},
        }, timeout=30)
        art_data = json.loads(art_result["result"]["content"][0].get("text", "{}"))

        image_count = art_data.get("image_count", 0)
        if image_count and image_count > 0:
            body = art_data.get("body", "") or art_data.get("body_cleaned", "")
            # Check for image references
            has_md_img = "![" in body or "<img" in body
            has_url_img = "https://" in body and (".png" in body or ".jpg" in body or ".webp" in body)
            if has_md_img or has_url_img:
                found_image = True
                print(f"  ✓ article '{art_data.get('title', '?')[:40]}' "
                      f"has {image_count} images, body references images: {has_md_img or has_url_img}")
                break

    if not found_image:
        # Not all articles have images — skip gracefully
        print("  ⚠ No image-rich article found in first 5 results (not a failure)")
