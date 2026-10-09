"""Read an explicit private article mirror; never load config or publish it."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import markdown

from .knowledge import KnowledgeError, KnowledgeNotFound


TABLES = {"wechat": ("articles", "scanned_at"), "rss": ("rss_articles", "fetched_at")}
SUMMARY = "source,record_id,title,title_translated,source_url,lang,captured_at,body_available,translation_available,rewrite_available"
SUMMARY_FIELDS = ("source", "record_id", "title", "title_translated", "source_url", "lang", "captured_at", "body_available", "translation_available", "rewrite_available")
SEARCH_FIELDS = ("title", "title_translated", "body", "body_translated", "body_rewritten")

# Display rendering reuses Python Markdown, then keeps only a safe HTML subset.
# Markdown conversion alone is not sanitization (a raw <script> passes through),
# so every tag and URL scheme is re-checked before the page may inject it.
MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "nl2br"]
_BARE_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
# Legacy 整理稿 / final_content bodies hardcode the old local image server; the
# reader resolves them under the optional /static/img mount instead.
IMAGE_SERVER_REWRITE = re.compile(r"http://localhost:8765/")
_ANY_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.I)
_BAD_SCHEME = re.compile(r"^(?:javascript|data|vbscript|file|blob|jar):", re.I)
_ALLOWED_SCHEMES = ("http://", "https://", "mailto:")
_ALLOWED_TAGS = frozenset({"p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "code", "span", "div", "strong", "em", "b", "i", "del", "ins", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "a", "img", "figure", "figcaption", "sup", "sub"})
_VOID_TAGS = frozenset({"br", "hr", "img"})
_DROP_CONTENT = frozenset({"script", "style"})
_GLOBAL_ATTRS = frozenset({"class", "id"})
_TAG_ATTRS = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title", "loading"}),
    "th": frozenset({"colspan", "rowspan", "align"}),
    "td": frozenset({"colspan", "rowspan", "align"}),
}


def _safe_url(value):
    """Return ``value`` only when its scheme is http(s)/mailto or it is relative."""
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    probe = re.sub(r"[\x00-\x20]+", "", stripped).lower()
    if _BAD_SCHEME.match(probe):
        return None
    if _ANY_SCHEME.match(probe) and not probe.startswith(_ALLOWED_SCHEMES):
        return None
    return stripped


def _trim_url(url):
    url = url.rstrip(".,;:!?、，。；：！？\"'")
    for closer, opener in ((")", "("), ("】", "【"), ("）", "（"), ("]", "["), ("}", "{")):
        while url.endswith(closer) and url.count(closer) > url.count(opener):
            url = url[:-1]
    return url


def _autolink(text):
    out, last = [], 0
    for match in _BARE_URL.finditer(text):
        out.append(escape(text[last:match.start()], quote=False))
        url = _trim_url(match.group(0))
        trailing = match.group(0)[len(url):]
        safe = _safe_url(url)
        if safe is None:
            out.append(escape(url, quote=False))
        else:
            out.append(f'<a href="{escape(safe, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(url, quote=False)}</a>')
        out.append(escape(trailing, quote=False))
        last = match.end()
    out.append(escape(text[last:], quote=False))
    return "".join(out)


class _SafeHTML(HTMLParser):
    """Rebuild markdown output with an allowlist; drop scripts and unsafe URLs."""

    def __init__(self, source_url=None):
        super().__init__(convert_charrefs=True)
        self.source_url = None
        if source_url and _safe_url(source_url):
            try:
                parsed = urlsplit(source_url)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    self.source_url = source_url
            except ValueError:
                pass
        self.out: list[str] = []
        self._open: list[str] = []
        self._dropping = 0
        self._literal = 0

    def _attrs(self, tag, attrs):
        allowed = _GLOBAL_ATTRS | _TAG_ATTRS.get(tag, frozenset())
        rendered = []
        for name, value in attrs:
            name = name.lower()
            if value is None or name not in allowed:
                continue
            if name in {"href", "src"}:
                value = _safe_url(value)
                if value is None:
                    return None
                if not value.startswith(("/static/img/", "#")) and not _ANY_SCHEME.match(value):
                    if self.source_url is None:
                        return None
                    value = urljoin(self.source_url, value)
                    if _safe_url(value) is None:
                        return None
            rendered.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a" and not any(part.startswith(" href=") for part in rendered):
            return None
        return "".join(rendered)

    def _emit(self, tag, attrs, void):
        tag = tag.lower()
        if tag in _DROP_CONTENT:
            self._dropping += 1
            return
        if self._dropping or tag not in _ALLOWED_TAGS:
            return
        rendered = self._attrs(tag, attrs)
        if rendered is None:
            return
        if void or tag in _VOID_TAGS:
            self.out.append(f"<{tag}{rendered} />")
            return
        self._open.append(tag)
        if tag in {"pre", "code", "a"}:
            self._literal += 1
        self.out.append(f"<{tag}{rendered}>")

    def handle_starttag(self, tag, attrs):
        self._emit(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._emit(tag, attrs, True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT:
            self._dropping = max(0, self._dropping - 1)
            return
        if self._dropping or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        while tag in self._open:
            top = self._open.pop()
            if top in {"pre", "code", "a"}:
                self._literal = max(0, self._literal - 1)
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if self._dropping or not data:
            return
        self.out.append(escape(data, quote=False) if self._literal else _autolink(data))

    def close(self):
        super().close()
        while self._open:
            self.out.append(f"</{self._open.pop()}>")


def render_body(text, source_url=None):
    """Render mirror markdown to safe HTML, or ``None`` when there is no body."""
    if not isinstance(text, str) or not text.strip():
        return None
    text = IMAGE_SERVER_REWRITE.sub("/static/img/", text)
    parser = _SafeHTML(source_url)
    parser.feed(markdown.markdown(text, extensions=MD_EXTENSIONS))
    parser.close()
    return "".join(parser.out)


class SnapshotChanged(KnowledgeError):
    pass


def fingerprint(path):
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise SnapshotChanged("snapshot_changed")
    stat = Path(path).stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def load_local_snapshot(database, receipt, cache):
    try:
        db = Path(database).resolve(strict=True)
        metadata = Path(receipt).resolve(strict=True)
        if db.parent != metadata.parent or not db.is_file() or not metadata.is_file():
            raise SnapshotChanged("snapshot_changed")
        signature = (str(db), fingerprint(db), str(metadata), fingerprint(metadata))
        if cache.get("signature") == signature:
            return cache["snapshot"]
        value = json.loads(metadata.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise KnowledgeError("invalid local article receipt")
        snapshot_id = value.get("snapshot_id")
        digest = value.get("sqlite_sha256")
        observed_at = value.get("observed_at")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip() or len(snapshot_id) > 128:
            raise KnowledgeError("invalid local article snapshot id")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KnowledgeError("invalid local article hash")
        if not isinstance(observed_at, str) or datetime.fromisoformat(observed_at.replace("Z", "+00:00")).tzinfo is None:
            raise KnowledgeError("invalid local article observation time")
        # ponytail: one verified mirror cache; hash only on promotion, revisit for very large mirrors.
        with db.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest or signature != (str(db), fingerprint(db), str(metadata), fingerprint(metadata)):
            raise SnapshotChanged("snapshot_changed")
        snapshot = {"database": db, "fingerprint": signature[1], "snapshot_id": snapshot_id, "observed_at": observed_at}
        cache.update(signature=signature, snapshot=snapshot)
        return snapshot
    except SnapshotChanged:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise KnowledgeError("local article snapshot is unavailable") from exc


@contextmanager
def _connection(database):
    fingerprint(database)
    conn = sqlite3.connect(Path(database).absolute().as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        for table, captured in TABLES.values():
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            required = {"id", "title", "url", "body", "title_translated", "body_translated", "translated_lang", "lang", captured}
            if not required.issubset(columns):
                raise KnowledgeError("local article mirror schema is incomplete")
        yield conn
    finally:
        conn.close()


def _rewrite_sql(conn, table):
    """Return ``(value, flag, count)`` SQL for the optional 整理稿 column.

    Older mirrors were exported before ``body_rewritten`` existed; they must
    keep reading as "no 整理稿" instead of failing the whole snapshot.
    """
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if "body_rewritten" in columns:
        return ("body_rewritten", "length(trim(coalesce(body_rewritten,'')))>0 AS rewrite_available", "coalesce(sum(length(trim(coalesce(body_rewritten,'')))>0),0) AS with_rewrite")
    return ("NULL AS body_rewritten", "0 AS rewrite_available", "0 AS with_rewrite")


def _source(source):
    if not isinstance(source, str) or source not in TABLES:
        raise KnowledgeError("source must be wechat or rss")
    return TABLES[source]


def _summary(row):
    result = {field: row[field] for field in SUMMARY_FIELDS}
    for field in ("body_available", "translation_available", "rewrite_available"):
        result[field] = bool(result[field])
    return result


def _rows_sql(conn):
    parts = []
    for source, (table, captured) in TABLES.items():
        value, flag, _ = _rewrite_sql(conn, table)
        parts.append(
            f"SELECT '{source}' AS source,id AS record_id,title,title_translated,url AS source_url,lang,{captured} AS captured_at,"
            "length(trim(coalesce(body,'')))>0 AS body_available,length(trim(coalesce(body_translated,'')))>0 AS translation_available,"
            f"{flag},body,body_translated,{value},translated_lang FROM {table}"
        )
    return " UNION ALL ".join(parts)


def _display_match(row, needle):
    """Match on the visible text only: URL substrings must not count as a hit."""
    pattern = re.compile(r"(?<![a-z0-9_])" + re.escape(needle) + r"(?![a-z0-9_])") if needle.isascii() else None
    for field in SEARCH_FIELDS:
        value = row[field]
        if value:
            text = _BARE_URL.sub(" ", value).lower()
            if (pattern.search(text) if pattern else needle in text):
                return True
    return False


def list_local_articles(database_path, *, q="", source=None, limit=20, offset=0, has_body=False):
    if not isinstance(q, str) or len(q) > 512:
        raise KnowledgeError("query must be text up to 512 characters")
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise KnowledgeError("limit must be 1–100 and offset nonnegative integers")
    if type(has_body) is not bool:
        raise KnowledgeError("has_body must be boolean")
    clauses, params = [], []
    if has_body:
        clauses.append("body_available=1")
    if source is not None:
        _source(source)
        clauses.append("source=?")
        params.append(source)
    needle = q.strip().lower()
    if needle:
        # ponytail: literal text scan; add an index only after measured mirror latency warrants it.
        clauses.append("(" + " OR ".join(f"instr(lower(coalesce({field},'')),lower(?))>0" for field in SEARCH_FIELDS) + ")")
        params.extend([needle] * len(SEARCH_FIELDS))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    selected = SUMMARY if not needle else SUMMARY + "," + ",".join(SEARCH_FIELDS)
    with _connection(database_path) as conn:
        rows = conn.execute(
            f"SELECT {selected} FROM ({_rows_sql(conn)}){where} ORDER BY captured_at IS NULL,captured_at DESC,source,record_id DESC",
            params,
        )
        items, skipped = [], 0
        for row in rows:
            # URL-only matches are dropped after the SQL prefilter; offset counts
            # only the records a reader can actually see.
            if needle and not _display_match(row, needle):
                continue
            if skipped < offset:
                skipped += 1
                continue
            items.append(row)
            if len(items) > limit:
                break
    return {"items": [_summary(row) for row in items[:limit]], "next_offset": offset + limit if len(items) > limit else None}


def read_local_article(database_path, source, record_id):
    table, captured = _source(source)
    if type(record_id) is not int or record_id < 1:
        raise KnowledgeError("record_id must be a positive integer")
    with _connection(database_path) as conn:
        value, flag, _ = _rewrite_sql(conn, table)
        row = conn.execute(
            f"SELECT '{source}' AS source,id AS record_id,title,title_translated,url AS source_url,lang,{captured} AS captured_at,"
            "length(trim(coalesce(body,'')))>0 AS body_available,length(trim(coalesce(body_translated,'')))>0 AS translation_available,"
            f"{flag},body,body_translated,{value},translated_lang FROM {table} WHERE id=?", (record_id,),
        ).fetchone()
    if row is None:
        raise KnowledgeNotFound("article not found")
    item = _summary(row)
    item.update({field: row[field] for field in ("body", "body_translated", "body_rewritten", "translated_lang")})
    return item


def local_article_counts(database_path):
    with _connection(database_path) as conn:
        return {
            source: dict(conn.execute(
                "SELECT count(*) AS total,coalesce(sum(length(trim(coalesce(body,'')))>0),0) AS with_body,"
                "coalesce(sum(length(trim(coalesce(body_translated,'')))>0),0) AS with_translation,"
                f"{_rewrite_sql(conn, table)[2]} FROM {table}"
            ).fetchone())
            for source, (table, _) in TABLES.items()
        }
