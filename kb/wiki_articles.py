"""Source-aware local article truth (W5B Task 1).

The single small shared place that maps source-aware article evidence to local
data for the wiki system:

- ``wechat -> articles``
- ``rss    -> rss_articles``

Canonical Wiki article ref for BOTH sources is ``md5(url)[:10]`` lowercase
(design §6.1). ``rss_articles.content_hash`` is a 32-char body MD5 and is
NEVER used as URL/Wiki identity.

Each article record is a plain dict:

.. code-block:: python

    {
        "source": "wechat" | "rss",
        "article_id": 123,
        "ref": "0123456789",
        "url": "https://...",
        "title": "real title",
        "text": "body, falling back to summary",
    }

Read-only: no writes to the article/ingestion DB, no network imports.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

SUPPORTED_ARTICLE_SOURCES = ("wechat", "rss")

#: Fixed source -> table mapping (explicit code, no plugin registry).
_TABLES = {"wechat": "articles", "rss": "rss_articles"}

#: LightRAG full-doc content embeds the source URL as "URL: <url>".
_URL_RE = re.compile(r"URL:\s*(\S+)")

#: Valid legacy citation ref shape: 10-char lowercase hex.
_LEGACY_REF_RE = re.compile(r"^[a-f0-9]{10}$")


class UnsupportedArticleSource(ValueError):
    """Raised for an article source outside ``SUPPORTED_ARTICLE_SOURCES``.

    Never silently skip: an unknown live ingestion source must block
    (design §6.4) instead of disappearing.
    """


def canonical_article_ref(url: str) -> str:
    """Return lowercase MD5(url)[:10] — canonical Wiki article ref."""
    return hashlib.md5(url.encode()).hexdigest()[:10]


def lightrag_doc_id(source: str, url: str) -> str:
    """Return ``wechat_<ref>`` or ``rss_<ref>``; reject unsupported source.

    Byte-for-byte parity with ``scripts/reconcile_ingestions._compute_doc_id``
    for the two supported sources.
    """
    if source not in SUPPORTED_ARTICLE_SOURCES:
        raise UnsupportedArticleSource(source)
    return f"{source}_{canonical_article_ref(url)}"


def live_ingestion_sources(conn: sqlite3.Connection) -> set[str]:
    """Return the distinct ``source`` values present in ``ingestions``."""
    rows = conn.execute("SELECT DISTINCT source FROM ingestions").fetchall()
    return {r[0] for r in rows if r[0]}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Discover existing columns via PRAGMA table_info (fixtures may lack optional cols)."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _first_nonempty(*values: object) -> str:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v
    return ""


def load_article_index(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], dict]:
    """Map ``(source, canonical_ref)`` -> local article record.

    Ref is always derived from ``url`` for both tables. Optional columns
    (``title_translated``, ``body``) are read only when present.

    Title fallback: ``title_translated`` (non-empty) > ``title`` > ref.
    Text fallback: ``body`` (non-empty) > ``summary`` > "".
    """
    index: dict[tuple[str, str], dict] = {}
    for source, table in _TABLES.items():
        cols = _table_columns(conn, table)
        select_cols = ["id", "url"]
        for c in ("title", "title_translated", "body", "summary"):
            if c in cols:
                select_cols.append(c)
        if "url" not in cols:
            continue
        sql = (
            f"SELECT {', '.join(select_cols)} FROM {table} "
            "WHERE url IS NOT NULL AND url != ''"
        )
        for row in conn.execute(sql):
            rec = dict(zip(select_cols, row))
            url = rec["url"]
            ref = canonical_article_ref(url)
            title = _first_nonempty(rec.get("title_translated"), rec.get("title"), ref)
            text = _first_nonempty(rec.get("body"), rec.get("summary"), "")
            index[(source, ref)] = {
                "source": source,
                "article_id": rec["id"],
                "ref": ref,
                "url": url,
                "title": title,
                "text": text,
            }
    return index


def resolve_article(
    index: dict[tuple[str, str], dict],
    ref: str,
    *,
    source: str | None = None,
) -> dict | None:
    """Strict source lookup; ``source=None`` only when exactly one row matches.

    - ``source`` given: return ``index[(source, ref)]`` (or None).
    - ``source=None``: allowed only when exactly one local row matches the ref;
      multiple matches (e.g. same URL ingested as both wechat and rss) raise
      ``ValueError`` instead of guessing.
    """
    if source is not None:
        if source not in SUPPORTED_ARTICLE_SOURCES:
            raise UnsupportedArticleSource(source)
        return index.get((source, ref))
    matches = [rec for (src, r), rec in index.items() if r == ref]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sources = sorted(rec["source"] for rec in matches)
        raise ValueError(f"ambiguous article ref {ref!r}: matches sources {sources}")
    return None


def _load_doc_status(lightrag_dir: Path) -> dict[str, dict]:
    path = Path(lightrag_dir) / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _url_for_article(
    conn: sqlite3.Connection, source: str, article_id: int
) -> str | None:
    table = _TABLES[source]
    row = conn.execute(
        f"SELECT url FROM {table} WHERE id = ?", (article_id,)
    ).fetchone()
    if row is None or not row[0]:
        return None
    return str(row[0])


def processed_ingestions(
    conn: sqlite3.Connection,
    lightrag_dir: Path,
) -> list[dict]:
    """Return ``ingestions.status='ok'`` rows whose source-specific LightRAG
    ``doc_status`` is ``processed`` (design §3.1, §8.1).

    Each returned dict carries ``id``, ``article_id``, ``source``,
    ``ingested_at``, ``url``, ``ref`` and ``doc_id`` (doc_id parity with
    ``scripts/reconcile_ingestions``). Rows whose URL cannot be recovered are
    excluded (their LightRAG doc status cannot be confirmed). An unknown
    ``ingestions.source`` raises ``UnsupportedArticleSource``.
    """
    status_map = _load_doc_status(lightrag_dir)
    rows = conn.execute(
        "SELECT id, article_id, source, ingested_at FROM ingestions "
        "WHERE status = 'ok' ORDER BY id"
    ).fetchall()
    processed: list[dict] = []
    for row in rows:
        source = row[2]
        if source not in SUPPORTED_ARTICLE_SOURCES:
            raise UnsupportedArticleSource(source)
        url = _url_for_article(conn, source, row[1])
        if url is None:
            continue
        doc_id = lightrag_doc_id(source, url)
        entry = status_map.get(doc_id)
        actual = entry.get("status") if isinstance(entry, dict) else None
        if not (isinstance(actual, str) and actual.lower() == "processed"):
            continue
        processed.append(
            {
                "id": row[0],
                "article_id": row[1],
                "source": source,
                "ingested_at": row[3],
                "url": url,
                "ref": canonical_article_ref(url),
                "doc_id": doc_id,
            }
        )
    return processed


def _source_from_doc_id(doc_id: str) -> str | None:
    """Return the source named by a LightRAG full-doc id prefix.

    Full-doc ids for the supported sources are ``wechat_<ref>`` / ``rss_<ref>``
    (``lightrag_doc_id``); anything else has no recognized source prefix and
    returns None.
    """
    for source in SUPPORTED_ARTICLE_SOURCES:
        if doc_id.startswith(source + "_"):
            return source
    return None


def build_chunk_article_map(
    lightrag_dir: Path,
    conn: sqlite3.Connection,
) -> dict[str, dict]:
    """Map chunk-id -> source-aware local article record via full-doc URL.

    Pipeline (design §8.2, plan Task 1 step 1.5)::

        kv_store_text_chunks.json
         -> full_doc_id
         -> kv_store_full_docs.json content
         -> parse `URL: <url>`
         -> local source-aware URL index
         -> source/ref/title/text record

    Source identity is preserved end to end: a full doc id with a recognized
    source prefix (``wechat_<ref>`` / ``rss_<ref>``) resolves ONLY inside that
    source's URL index, so the same canonical URL ingested under both sources
    can never collide. A full doc id WITHOUT a source prefix resolves by URL:
    when exactly one source matches, it maps; when zero or multiple sources
    match, the chunk is omitted — never a silent guess.

    HTTP<->HTTPS normalization is retained for lookup robustness (as in the
    previous W1-local implementation) and stays scoped to the same source.
    Chunks whose URL does not resolve in the local source-aware index are
    absent from the result.
    """
    chunks_path = Path(lightrag_dir) / "kv_store_text_chunks.json"
    docs_path = Path(lightrag_dir) / "kv_store_full_docs.json"
    if not chunks_path.exists() or not docs_path.exists():
        return {}
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    docs = json.loads(docs_path.read_text(encoding="utf-8"))

    # Per-source URL index: the same URL may legitimately exist in both
    # sources; a flat URL->record map would silently drop one of them.
    url_index: dict[str, dict[str, dict]] = {}
    for (_key, rec) in load_article_index(conn).items():
        src_index = url_index.setdefault(rec["source"], {})
        url = rec["url"]
        src_index[url] = rec
        if url.startswith("http://"):
            src_index.setdefault("https://" + url[7:], rec)
        elif url.startswith("https://"):
            src_index.setdefault("http://" + url[8:], rec)

    result: dict[str, dict] = {}
    for chunk_id, chunk_data in chunks.items():
        if not isinstance(chunk_data, dict):
            continue
        doc_id = chunk_data.get("full_doc_id")
        if not doc_id:
            continue
        doc_data = docs.get(doc_id)
        if not isinstance(doc_data, dict):
            continue
        m = _URL_RE.search(doc_data.get("content", ""))
        if not m:
            continue
        url = m.group(1).strip()
        source = _source_from_doc_id(doc_id)
        if source is not None:
            rec = url_index.get(source, {}).get(url)
            if rec is not None:
                result[chunk_id] = rec
            continue
        matches = [idx.get(url) for idx in url_index.values()]
        matches = [rec for rec in matches if rec is not None]
        if len(matches) == 1:
            result[chunk_id] = matches[0]
        # zero or multiple source matches: omit the chunk, never guess
    return result


def known_wiki_article_refs(conn: sqlite3.Connection) -> set[str]:
    """Canonical URL-derived refs across supported article tables plus valid
    legacy 10-char WeChat refs (design §6.2 last paragraph).

    Legacy ``articles.content_hash`` values that are valid 10-char lowercase
    hex refs are preserved (WeChat content_hash historically equals the URL
    ref). RSS ``content_hash`` (32-char body MD5) is never admitted.
    """
    refs: set[str] = set()
    for source, table in _TABLES.items():
        cols = _table_columns(conn, table)
        if "url" in cols:
            for (url,) in conn.execute(
                f"SELECT url FROM {table} WHERE url IS NOT NULL AND url != ''"
            ):
                refs.add(canonical_article_ref(url))
        if source == "wechat" and "content_hash" in cols:
            for (h,) in conn.execute(
                f"SELECT content_hash FROM {table} WHERE content_hash IS NOT NULL"
            ):
                if h and _LEGACY_REF_RE.fullmatch(h):
                    refs.add(h)
    return refs
