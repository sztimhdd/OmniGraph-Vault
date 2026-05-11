#!/usr/bin/env python3
"""Export OmniGraph Agent news for the VitaClaw website static contract."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


CONTRACT_VERSION = 1
EXPORT_COUNT = 5
DEFAULT_DB = Path("data/kol_scan.db")
DEFAULT_OUTPUT = Path("/home/sztimhdd/vitaclaw-site/public/data/agent-news.json")


class ExportError(RuntimeError):
    """Raised when OmniGraph cannot produce a valid VitaClaw export."""


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _source_domain(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed.netloc.lower().removeprefix("www.")


def _iso_timestamp(value: str | int | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return datetime.fromtimestamp(int(text), tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    normalized = text.replace(" ", "T")
    if normalized.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", normalized):
        return normalized
    return f"{normalized}Z"


def _keyword_tags(*values: str | None) -> list[str]:
    text = " ".join(v or "" for v in values)
    checks = [
        ("MCP", r"\bMCP\b|Model Context Protocol"),
        ("Agent", r"Agent|智能体|代理"),
        ("RAG", r"\bRAG\b|检索|知识库"),
        ("多模态", r"多模态|multimodal|视觉"),
        ("安全", r"安全|prompt injection|注入|劫持"),
        ("工程化", r"工程|架构|生产|部署|工作流"),
        ("推理优化", r"推理|解码|缓存|KV"),
    ]
    tags: list[str] = []
    for label, pattern in checks:
        if re.search(pattern, text, re.IGNORECASE):
            tags.append(label)
    return tags


def _tags(source_name: str | None, topics: str | None, title: str, reason: str | None) -> list[str]:
    tags: list[str] = []
    for raw in (topics or "").split("|"):
        tag = _clean_text(raw)
        if tag and tag not in tags:
            tags.append(tag)
    for tag in _keyword_tags(title, reason):
        if tag not in tags:
            tags.append(tag)
    if source_name:
        source = _clean_text(source_name)
        if source and source not in tags:
            tags.insert(0, source)
    return tags[:3]


def _candidate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT 'kol' AS source_type,
               a.id AS article_id,
               a.title,
               a.url,
               a.digest AS summary,
               acc.name AS source_name,
               GROUP_CONCAT(c.topic, '|') AS topics,
               a.update_time AS published_at,
               a.scanned_at AS collected_at,
               a.layer2_at AS curated_at,
               a.layer2_reason AS reason
        FROM articles a
        LEFT JOIN accounts acc ON acc.id = a.account_id
        LEFT JOIN classifications c
          ON c.article_id = a.id
         AND COALESCE(c.depth_score, 0) >= 2
         AND COALESCE(c.relevant, 0) = 1
         AND COALESCE(c.excluded, 0) = 0
        WHERE a.layer1_verdict = 'candidate'
          AND a.layer2_verdict = 'ok'
          AND COALESCE(a.title, '') != ''
          AND COALESCE(a.url, '') != ''
          AND COALESCE(a.digest, '') != ''
        GROUP BY a.id
        UNION ALL
        SELECT 'rss' AS source_type,
               r.id AS article_id,
               r.title,
               r.url,
               r.summary,
               f.name AS source_name,
               r.topics,
               r.published_at,
               r.fetched_at AS collected_at,
               r.layer2_at AS curated_at,
               r.layer2_reason AS reason
        FROM rss_articles r
        LEFT JOIN rss_feeds f ON f.id = r.feed_id
        WHERE r.layer1_verdict = 'candidate'
          AND r.layer2_verdict = 'ok'
          AND COALESCE(r.title, '') != ''
          AND COALESCE(r.url, '') != ''
          AND COALESCE(r.summary, '') != ''
        ORDER BY curated_at DESC, collected_at DESC, article_id DESC
        """
    ).fetchall()


def _item_from_row(row: sqlite3.Row) -> dict | None:
    title = _clean_text(row["title"])
    url = _clean_text(row["url"])
    summary = _clean_text(row["summary"])
    domain = _source_domain(url)
    if not title or not domain or not summary or not _has_cjk(summary):
        return None
    tags = _tags(row["source_name"], row["topics"], title, row["reason"])
    if not tags:
        return None

    item = {
        "originalTitle": title,
        "originalUrl": url,
        "summaryZh": summary,
        "tags": tags,
        "sourceDomain": domain,
        "layer": "layer2",
        "curationStatus": "passed",
    }
    source_name = _clean_text(row["source_name"])
    if source_name:
        item["sourceName"] = source_name
    for out_key, row_key in (
        ("publishedAt", "published_at"),
        ("collectedAt", "collected_at"),
        ("curatedAt", "curated_at"),
    ):
        timestamp = _iso_timestamp(row[row_key])
        if timestamp:
            item[out_key] = timestamp
    return item


def build_export(
    conn: sqlite3.Connection,
    *,
    generated_at: str | None = None,
) -> dict:
    generated = generated_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    items: list[dict] = []
    seen_urls: set[str] = set()
    for row in _candidate_rows(conn):
        item = _item_from_row(row)
        if item is None or item["originalUrl"] in seen_urls:
            continue
        seen_urls.add(item["originalUrl"])
        items.append(item)
        if len(items) == EXPORT_COUNT:
            break
    if len(items) != EXPORT_COUNT:
        raise ExportError(
            f"expected 5 eligible items, found {len(items)}; "
            "run Layer 2 or add Chinese summaries before exporting"
        )
    return {
        "contractVersion": CONTRACT_VERSION,
        "generatedAt": generated,
        "items": items,
    }


def write_export(db_path: Path, output_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        export = build_export(conn)
    finally:
        conn.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(export, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export 5 Layer 2-passed OmniGraph articles for VitaClaw."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_export(args.db, args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
