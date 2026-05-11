# OmniGraph-Vault Database Schema (kol_scan.db)

Path: `~/OmniGraph-Vault/data/kol_scan.db`

## Key Tables

### articles (WeChat KOL articles)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| account_id | INTEGER | FK → accounts |
| title | TEXT | |
| url | TEXT | WeChat article URL |
| body | TEXT | Full scraped content |
| content_hash | TEXT | Dedup hash |
| update_time | INTEGER | |
| scanned_at | TEXT | |
| layer1_verdict | TEXT | L1 filter result |
| layer1_reason | TEXT | |
| layer2_verdict | TEXT | L2 filter result |
| layer2_reason | TEXT | |

### ingestions (pipeline dedup & status)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| article_id | INTEGER | FK → articles.id |
| status | TEXT | ok / skipped / skipped_ingested / failed |
| ingested_at | TEXT | Timestamp |
| enrichment_id | TEXT | |

**Dedup mechanism**: Every article that enters the ingest pipeline gets a row here.
`batch_ingest_from_spider.py` uses `article_id NOT IN (SELECT article_id FROM ingestions)`
to avoid re-processing.

### rss_articles
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| feed_id | INTEGER | FK → rss_feeds |
| title | TEXT | |
| url | TEXT | |
| body | TEXT | Scraped content |
| layer1_verdict | TEXT | |
| layer2_verdict | TEXT | |

### classifications (KOL topic classification — deprecated in v3.5)
| Column | Type |
|--------|------|
| article_id | INTEGER |
| topic | TEXT |
| depth_score | INTEGER |
| relevant | INTEGER |

### rss_classifications
Empty (0 rows) — RSS classification pipeline not active.

## Common Queries

### Pending articles (have body, not yet ingested)
```sql
SELECT COUNT(*) FROM articles a
WHERE a.body IS NOT NULL AND a.body != ''
AND a.id NOT IN (SELECT DISTINCT article_id FROM ingestions)
```

### Today's ingestions by status
```sql
SELECT status, COUNT(*) FROM ingestions
WHERE date(ingested_at) = date('now')
GROUP BY status
```

### Ingestions last 7 days
```sql
SELECT date(ingested_at) d, status, COUNT(*)
FROM ingestions WHERE date(ingested_at) >= date('now','-7 days')
GROUP BY d, status ORDER BY d DESC
```

## Tool Notes

- **mcp_sqlite_* tools**: May return empty results for some tables. Fall back to direct Python `sqlite3`:
  ```python
  import sqlite3
  c = sqlite3.connect('/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db')
  ```
- `sqlite3` CLI is NOT installed — use Python's built-in module.
