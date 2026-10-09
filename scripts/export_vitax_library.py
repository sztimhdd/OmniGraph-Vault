"""Export a complete private article view and promote its verified directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vitax.local_articles import TABLES, load_local_snapshot, local_article_counts


FIELDS = ('id','title','url','body','title_translated','body_translated','translated_lang','lang','layer1_verdict','layer2_verdict','body_rewritten')


def export_library(source_database, output_dir):
    source = Path(source_database).resolve(strict=True)
    target = Path(output_dir).absolute()
    if os.path.lexists(target):
        raise ValueError('snapshot output must be new')
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.mkdir(mode=0o700)
    database = target / 'articles.sqlite'
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as incoming, sqlite3.connect(database) as outgoing:
        incoming.execute('PRAGMA query_only=ON')
        incoming.execute('BEGIN')
        for table, captured in TABLES.values():
            columns = {r[1] for r in incoming.execute(f'PRAGMA table_info({table})')}
            if not {'id','title','url','body'} <= columns:
                raise ValueError('source article schema is incomplete')
            fields = (*FIELDS, captured)
            declarations = ','.join(f'{f} '+('INTEGER PRIMARY KEY' if f=='id' else 'TEXT') for f in fields)
            outgoing.execute(f'CREATE TABLE {table} ({declarations})')
            selected = ','.join(f if f in columns else f'NULL AS {f}' for f in fields)
            rows = incoming.execute(f'SELECT {selected} FROM {table} ORDER BY id')
            outgoing.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in fields)})', rows)
        outgoing.commit()
        if outgoing.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('exported SQLite failed integrity check')
    database.chmod(0o600)
    counts = local_article_counts(database)
    if not sum(c['total'] for c in counts.values()):
        raise ValueError('refusing an empty historical snapshot')
    with database.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    value = {'schema_version':1, 'snapshot_id':str(uuid.uuid4()), 'observed_at':datetime.now(UTC).isoformat(), 'sqlite_sha256':digest, 'counts':counts}
    receipt = target / 'receipt.json'
    receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    receipt.chmod(0o600)
    load_local_snapshot(database, receipt, {})
    return value


def promote_library(snapshot_dir, current):
    snapshot = Path(snapshot_dir).resolve(strict=True)
    load_local_snapshot(snapshot/'articles.sqlite', snapshot/'receipt.json', {})
    link = Path(current).absolute()
    if os.path.lexists(link) and not link.is_symlink():
        raise ValueError('current must be a managed symlink')
    link.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    staging = link.with_name(link.name+'.'+uuid.uuid4().hex)
    staging.symlink_to(snapshot, target_is_directory=True)
    staging.replace(link)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--current')
    args = parser.parse_args()
    try:
        receipt = export_library(args.source, args.output)
        if args.current:
            promote_library(args.output, args.current)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
