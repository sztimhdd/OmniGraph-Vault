# W5-0 RESEARCH.md

**Date:** 2026-08-11
**Executor:** Hermes autonomous Mode A

## Gate A — Production W3 Truth

### Production host
- **Host:** `iZj1imk39yc55iZ` (Aliyun ECS, 47.117.244.253:22)
- **SSH:** `ssh vitaclaw-aliyun` (key: `~/.ssh/vitaclaw_aliyun_ed25519`)
- **Ingest unit:** `omnigraph-daily-ingest.service` — active, fires every ~2h

### W3 hook status
- **Code deployed:** YES — `batch_ingest_from_spider.py:2203-2216` wires `_wiki_update_check`
- **Code running:** YES — journald shows `W3 wiki hook:` log every cron fire
- **Results:** **ZERO suggestions** on every single run since deployment (3+ days, ~20+ runs):
  ```
  {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}
  ```
- **Root cause:** Hash length mismatch.

### Hash discovery

| Component | Algorithm | Length | Example |
|-----------|-----------|--------|---------|
| DB `articles.content_hash` | MD5(url)[:10] | 10 | `16e23156b6` |
| Entity buffer filenames | MD5(url)[:10] | 10 | `00258cb49d_entities.json` |
| Image dirs (`images/<hash>/`) | MD5(url)[:10] | 10 | — |
| Wiki citations (`^[article:<hash>]`) | MD5(url)[:10] | 10 | `article:8a5a502c8b` |
| Checkpoints | SHA256(url)[:16] | 16 | — |
| **W3 batch_hashes** | **SHA256(url)[:16]** | **16** | — |

The W3 hook computes `batch_hashes` via `get_article_hash(r[3])` which returns SHA256[:16] (16 chars). These hashes are passed to `generate_wiki_suggestions()` which:

1. Queries `SELECT 1 FROM articles WHERE content_hash=?` with each 16-char hash → DB stores 10-char → NEVER matches → skip
2. Checks `entity_buffer/<hash>_entities.json` → files use 10-char → NEVER matches → skip

**Result: `entity_to_hashes` dict is ALWAYS empty → zero suggestions → zero applied.**

### Additional findings

- Wiki lint log has 2 entries (minimal) at `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl`
- `_suggestions/` directory is empty
- Entity buffer has 841 files on Aliyun production, all using 10-char hash filenames
- 295 articles in DB with 10-char content_hash
- 39 locations across codebase use `md5(url.encode())[:10]` as article identity
- Only `lib/checkpoint.get_article_hash` and its 2 callers use SHA256[:16]
- Test `test_hash_is_sha256_16` explicitly enforces the 16-char hash in `batch_ingest_from_spider.py`

## Gate B — Citation Contract Reality

- Legacy citation regex: `^[article:([a-f0-9]{10})]` — matches 10 chars ✓ (correct for actual data)
- `LEGACY_CITATION_RE` in `kb/wiki_lint.py` is correct at 10 chars
- All wiki body citations use 10-char hashes (verified on Aliyun openclaw.md)
- The 16-char hash is the outlier, not the 10-char hash
- Canonical identity should be 10-char MD5 (matches every existing system)

## Current Wiki State

- 19 entity pages in `kb/wiki/entities/`
- W3 has never produced a suggestion → wiki pages are from W1 batch generation only
- KB Web UI serves wiki pages via SSG bake
- `wiki_inject.py` (W4 synthesize injection) uses `extract_main_entity` which matches on slug, not hash — so that path is unaffected
