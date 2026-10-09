"""Read-only content inventory. Output hashes and gaps, never text or credentials."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urldefrag, urlsplit


TABLES = {'wechat': 'articles', 'rss': 'rss_articles'}
LEGACY_IMAGE = re.compile(r'https?://(?:localhost|127\.0\.0\.1):8765/[^\s<>"\'\)\]\}`]+')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def artifact(row, columns, field):
    text = row.get(field) or ''
    return {
        'status': 'not_exported' if field not in columns else 'present' if text.strip() else 'missing',
        'sha256': digest(text) if text.strip() else None,
        'utf8_bytes': len(text.encode('utf-8')),
    }


def audit_content(database, assets=None):
    database = Path(database).resolve(strict=True)
    assets = Path(assets).resolve(strict=True) if assets is not None else None
    rows, schemas = [], {}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        for source, table in TABLES.items():
            columns = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            if not {'id', 'url', 'body'} <= columns:
                raise ValueError(f'{table} source schema is incomplete')
            schemas[source] = sorted(columns)
            # Select only contract fields; never load tokens, cookies or account tables.
            fields = ['id', 'url', 'body', 'body_translated', 'body_rewritten', 'body_cleaned',
                      'translated_lang', 'lang', 'layer2_verdict', 'rewritten_at', 'translated_at',
                      'author', 'account_id', 'feed_id', 'published_at', 'update_time']
            selected = ','.join(f for f in fields if f in columns)
            for raw in conn.execute(f'SELECT {selected} FROM {table} ORDER BY id'):
                raw = dict(raw)
                body = artifact(raw, columns, 'body')
                translation = artifact(raw, columns, 'body_translated')
                rewrite = artifact(raw, columns, 'body_rewritten')
                translation['language'] = raw.get('translated_lang') or 'unknown'
                translation['association'] = 'same_record_no_revision_receipt'
                rewrite['reuse'] = 'excluded_missing_revision_and_recipe_receipt' if rewrite['status'] == 'present' else 'not_available'
                # Same title or fragment-free URL alone must not merge different revisions.
                canonical = urldefrag(raw.get('url') or '')[0]
                version = body['sha256'] or f'unknown:{source}:{raw["id"]}'
                identity = digest((canonical or f'{source}:{raw["id"]}') + '\0' + version)
                urls = {u.rstrip(')]}') for field in ('body', 'body_translated', 'body_rewritten')
                        for u in LEGACY_IMAGE.findall(raw.get(field) or '')}
                resources = {'legacy_references': len(urls), 'present': 0, 'missing': 0, 'outside_root': 0, 'uncheckable': 0}
                for url in urls:
                    if assets is None:
                        continue
                    try:
                        path = (assets / unquote(urlsplit(url).path).lstrip('/')).resolve()
                        if not path.is_relative_to(assets):
                            resources['outside_root'] += 1
                        elif path.is_file():
                            resources['present'] += 1
                        else:
                            resources['missing'] += 1
                    except (OSError, ValueError):
                        # Malformed legacy references remain UNKNOWN; never log source text.
                        resources['uncheckable'] += 1
                eligible = raw.get('layer2_verdict') == 'ok'
                original_present = body['status'] == 'present'
                translation_present = translation['status'] == 'present'
                language = raw.get('lang') or 'unknown'
                if not original_present:
                    gap = 'translation_without_original' if translation_present else 'original_missing'
                elif source == 'rss' and language == 'en' and (not translation_present or translation['language'] not in ('zh', 'zh-CN', 'zh-TW')):
                    gap = 'chinese_translation_missing' if eligible else 'not_eligible_for_generation'
                else:
                    gap = 'existing_original_and_translation' if translation_present else 'existing_original'
                rows.append({
                    'source': source, 'record_id': raw['id'], 'source_revision': identity,
                    'language': language, 'eligible': eligible, 'body': body,
                    'translation': translation, 'rewrite': rewrite,
                    'cleaned': artifact(raw, columns, 'body_cleaned'), 'assets': resources,
                    'metadata_present': {f: bool(raw.get(f)) for f in ('author', 'account_id', 'feed_id', 'published_at', 'update_time')},
                    'gap': gap,
                })
    counts = {
        'records': len(rows), 'source_revisions': len({r['source_revision'] for r in rows}),
        'with_original': sum(r['body']['status'] == 'present' for r in rows),
        'with_translation': sum(r['translation']['status'] == 'present' for r in rows),
        'with_rewrite_unverified': sum(r['rewrite']['status'] == 'present' for r in rows),
        'translation_without_original': sum(r['gap'] == 'translation_without_original' for r in rows),
        'eligible_english_rss_missing_chinese': sum(r['gap'] == 'chinese_translation_missing' for r in rows),
        'eligible_long_originals': sum(r['eligible'] and r['body']['utf8_bytes'] > 25000 for r in rows),
        'gaps': dict(Counter(r['gap'] for r in rows)),
        'languages': dict(Counter(r['language'] for r in rows)),
    }
    return {'schema_version': 1, 'observed_at': datetime.now(UTC).isoformat(),
            'source_database': str(database), 'asset_checks': assets is not None,
            'schemas': schemas, 'counts': counts, 'rows': rows,
            'limits': ['Hashes prove byte identity, not translation fidelity or full-source coverage.',
                       'Legacy derived fields have no source revision or recipe receipt; rewrites are excluded from reuse.',
                       'Asset checks cover legacy localhost:8765 references only; external assets remain unverified.',
                       'This is a read-only inventory, not a billing ledger or model queue.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--assets')
    args = parser.parse_args()
    print(json.dumps(audit_content(args.source, args.assets), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
