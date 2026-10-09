"""Prepare one or two verified original bodies for the existing producer."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vitax.local_articles import load_local_snapshot, read_local_article
from vitax.production import ProductionError, _MAX_HTML_BYTES


def build_source_packet(database_path, selections, output_dir, *, source_receipt_path) -> Path:
    if not 1 <= len(selections) <= 2 or len(set(selections)) != len(selections):
        raise ProductionError("select one or two unique source records")
    directory = Path(output_dir).resolve()
    if directory.exists():
        raise ProductionError("output directory must not already exist")
    snapshot = load_local_snapshot(database_path, source_receipt_path, {})
    saved_at = datetime.now(UTC).isoformat()
    documents, originals = [], []
    for source, record_id in selections:
        article = read_local_article(snapshot["database"], source, record_id)
        body = article.get("body")
        if not isinstance(body, str) or not body.strip():
            raise ProductionError("source record has no original body")
        raw = body.encode("utf-8")
        if len(raw) > _MAX_HTML_BYTES:
            raise ProductionError("stored original exceeds 2 MiB")
        source_id = f"{source}-{record_id}"
        originals.append((directory / f"{source_id}.md", raw))
        documents.append({"source_id": source_id, "source_url": article["source_url"], "title": article["title"], "capture_format": "stored-markdown", "markdown_path": str(originals[-1][0]), "raw_markdown_sha256": hashlib.sha256(raw).hexdigest(), "source_record_ref": {"source": source, "record_id": record_id}, "source_snapshot_id": snapshot["snapshot_id"], "representation_saved_at": saved_at, "fetched_at": None})
    if load_local_snapshot(database_path, source_receipt_path, {}) != snapshot:
        raise ProductionError("source snapshot changed while preparing packet")
    directory.mkdir(parents=True, mode=0o700)
    for path, raw in originals:
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o600)
    packet = directory / "packet.json"
    packet.write_text(json.dumps({"schema_version": 1, "documents": documents}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packet.chmod(0o600)
    return packet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--source-receipt", required=True)
    parser.add_argument("--select", action="append", required=True, help="wechat:ID or rss:ID; max two")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        selections = []
        for value in args.select:
            source, record = value.split(":", 1)
            selections.append((source, int(record)))
        path = build_source_packet(args.database, selections, args.output, source_receipt_path=args.source_receipt)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(path)


if __name__ == "__main__":
    main()
