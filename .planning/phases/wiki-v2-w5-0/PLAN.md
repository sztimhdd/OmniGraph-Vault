# W5-0 PLAN.md

**Date:** 2026-08-11
**Executor:** Hermes autonomous Mode A
**Status:** Awaiting adversarial review

## Summary

W5-0 fixes one blocking bug (W3 hash mismatch → zero suggestions) and adds correctness infrastructure (health checker, error book, baseline, convergence contract). The hash fix is 1 line; the rest are standalone tools that don't touch the hot ingestion path.

## Implementation Plan — 7 atomic commits

### C1: Fix W3 hash contract (Gate A+B, ~5 LoC)

**Root cause:** `batch_hashes` computed via `get_article_hash(url)` → SHA256[:16] (16 chars). DB stores MD5[:10] (10 chars). Entity buffers use 10-char names. Lookups always fail.

**Fix in `batch_ingest_from_spider.py:2206-2208`:**
```python
# OLD (broken):
batch_hashes = [
    get_article_hash(r[3]) for r in candidate_rows if r[3]
]
# NEW (fixed):
import hashlib
batch_hashes = [
    hashlib.md5(r[3].encode()).hexdigest()[:10]
    for r in candidate_rows if r[3]
]
```

**Test update:** `tests/unit/test_batch_ingest_hash.py` — `test_hash_is_sha256_16` must be updated to assert MD5[:10] hash is used for article identity. Add `test_w3_batch_hashes_match_db_content_hash` that verifies the computed hashes are 10 chars.

**Why not extract a shared function:** The 39 call sites across the codebase use inline `hashlib.md5(url.encode())[:10]`. Extracting a canonical function is a refactor (not W5-0 scope). The fix is surgical: change the one wrong function call at the W3 batch_hashes call site.

**Backward compatibility:**
- `get_article_hash` (SHA256[:16]) remains for checkpoint use — not touched
- `LEGACY_CITATION_RE` (10 chars) is already correct — not touched  
- Wiki pages use 10-char hashes — no migration needed

### C2: Wiki health checker (Gate C, ~200 LoC new)

New script: `scripts/wiki_health.py`

Read-only. Checks:
1. page-count/index consistency
2. frontmatter required fields (per SCHEMA.md)
3. YAML parse validity
4. citation/source integrity (legacy + GFM footnote)
5. wikilink target validity
6. orphan/unindexed pages
7. duplicate slugs
8. staleness (last_updated vs today)
9. index.md freshness (mtime of any constituent file newer than index)

CLI: `python scripts/wiki_health.py [--json] [--wiki-root kb/wiki] [--db-path data/kol_scan.db]`
- Exit 0 = all checks pass
- Exit 1 = one or more ERROR-level failures
- Exit 2 = only WARN-level issues
- `--json` outputs machine-readable format

WARN vs ERROR:
- ERROR: missing frontmatter, broken wikilink, orphan citation, duplicate slug
- WARN: stale page, missing optional fields, index slightly out of date

### C3: Index generation determinism (Gate D, ~30 LoC)

Move `_rebuild_index()` from `scripts/wiki_generate_pages.py` into `scripts/wiki_health.py` as a `--rebuild-index` flag.

Key fix: verify `_suggestions/` is excluded from index generation (already excluded — `_suggestions` starts with `_` and `sorted(d.glob("*.md"))` won't match non-.md files). Add explicit skip for `_suggestions/` directory.

### C4: Error Book (Gate E, ~150 LoC)

Replace flat `wiki-lint-failures.jsonl` with SQLite-backed error store: `kb/wiki/_errors.db`

Schema:
```sql
CREATE TABLE errors (
    fingerprint TEXT PRIMARY KEY,  -- sha256(check_type + page_path + evidence_key)
    check_type TEXT NOT NULL,
    page_path TEXT NOT NULL,
    evidence TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',  -- open|resolved|ignored
    resolution_note TEXT,
    checker_version TEXT
);
```

New helper: `kb/wiki_error_book.py`

API:
- `record_error(check_type, page_path, evidence)` → upserts, returns fingerprint
- `resolve_error(fingerprint, note)` → sets status=resolved
- `ignore_error(fingerprint, reason)` → sets status=ignored
- `get_open_errors()` → list of current open errors
- `prune_resolved(page_path)` → if page no longer has this error, auto-resolve

Update `log_lint_failure()` to use Error Book instead of JSONL append. Keep backward compat: if Error Book DB doesn't exist, fall back to JSONL log.

### C5: Compiler convergence contract (Gate G, ~40 LoC)

**Problem:** `_build_page()` in `kb/wiki_update.py` produces placeholder pages that would blindly overwrite rich W1-generated pages if the hash lookup were fixed.

**Fix:** Add `_page_is_rich()` check before `apply_suggestion_atomic`:
```python
def _page_is_rich(page_path: Path) -> bool:
    """A page is 'rich' if it has substantive body content beyond placeholder."""
    if not page_path.exists():
        return False
    try:
        post = frontmatter.load(page_path)
        body = post.content.strip()
        # Placeholder pages have <200 chars of body content
        return len(body) > 200
    except Exception:
        return False
```

In `generate_wiki_suggestions`, set `type: "update"` for existing pages, and in `apply_suggestion_atomic`, skip auto-apply if the existing page is rich and the suggestion is placeholder-style. Instead, emit a suggestion artifact to `_suggestions/`.

Contract documented in `kb/wiki/CONTRACT.md`:
```
source/evidence collection
    -> propose page patch
    -> validate patch
    -> if existing page is rich: save to _suggestions/, do NOT overwrite
    -> if existing page is placeholder or new: apply atomically
```

### C6: Retrieval baseline (Gate F, ~100 LoC new)

New script: `scripts/wiki_baseline.py`

20-30 query benchmark covering:
- Direct entity lookup (5 queries): "What is OpenClaw?", "Who created Hermes Agent?", etc.
- Comparison (4 queries): "OpenClaw vs Hermes", "Claude Code vs Codex", etc.
- 2-hop relationship (4 queries): "What memory system does OpenClaw use?", etc.
- 3-hop synthesis (3 queries): "How does Harness Engineering relate to Agent Skills?", etc.
- Enumeration (3 queries): "List all agent frameworks mentioned in the wiki", etc.
- Freshness (3 queries): "What is the latest version of Claude Code?", etc.
- Negative/no-answer (3 queries): "What is the capital of Mars?", etc.

For each query, capture:
- Route: wiki_inject hit/miss, kg_search result count, FTS fallback
- Answer quality: correct/partial/incorrect
- Sources cited
- Latency (where measurable)

Output: `kb/wiki/_baseline/baseline-2026-08-11.json` + summary markdown.

### C7: Regression tests (Gate H, ~100 LoC)

New/modified tests:

1. `tests/unit/test_w3_hash_contract.py` — NEW
   - `test_batch_hashes_are_10_char_md5`: computed hashes match DB content_hash length
   - `test_w3_suggestions_integration_with_fixture`: end-to-end with fixture DB + entity buffers
   
2. `tests/unit/test_wiki_health.py` — NEW (expand existing test_wiki_lint.py)
   - `test_health_detects_missing_frontmatter`: synthetic bad fixture
   - `test_health_detects_broken_wikilink`
   - `test_health_passes_clean_fixture`
   - `test_health_exit_code_on_errors`
   
3. `tests/unit/test_wiki_error_book.py` — NEW
   - `test_dedupe_same_error`: re-recording produces same fingerprint
   - `test_resolve_then_reopen`: status transition
   
4. `tests/unit/test_wiki_rich_page_protection.py` — NEW
   - `test_rich_page_not_overwritten`
   - `test_placeholder_page_can_be_overwritten`

5. `tests/unit/test_batch_ingest_hash.py` — MODIFY
   - Update `test_hash_is_sha256_16` → `test_w3_batch_hashes_use_md5_10`

6. `tests/unit/test_wiki_lint.py` — existing, should still pass

## Deployment plan (Gate I)

After C1-C5 land:
1. `git push origin main`
2. SSH to Aliyun, `cd /root/OmniGraph-Vault && git pull --ff-only`
3. Wait for next ingest cron (~2h cycle) to fire
4. Verify journald shows `W3 wiki hook: {'suggestions_generated': N, ...}` with N > 0
5. If suggestions > 0 but applied = 0 (rich page protection working correctly), that's expected PASS
6. If ingest fails: revert commit and push revert

## What W5-0 does NOT touch

- No graph.json navigation (W6)
- No multi-hop traversal in kg_search (W7)
- No Wiki-first UI (W8)  
- No bulk wiki regeneration
- No LightRAG, ingest pipeline, MCP, KOL scan changes
- No new dependencies (sqlite3 already used everywhere)
