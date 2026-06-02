# W3 — llm-wiki-04 Verification (ingest hook + lint guard)

**Date:** 2026-05-19 (Phase D Task 4)
**Mode:** Local UAT, mock (no real LLM)
**Log:** `.scratch/llm-wiki-04-uat-260519-2243.log`

## Pre-flight

- pytest green at T3 commit `ef564c3` — 13/13 (5 T1-T5 orchestration + new wiki_update_hook anchor + 5 wiki_lint unit + 2 wiki_hook integration).
- Dev DB: `.dev-runtime/data/kol_scan.db` — 59 articles with non-NULL `content_hash`.

## Happy path UAT (mock, no LLM)

Direct invocation of `_wiki_update_check` per plan-04 Task 4 step 2:

```bash
venv/Scripts/python.exe -c "
import asyncio, sqlite3
from pathlib import Path
import sys; sys.path.insert(0, '.')
from batch_ingest_from_spider import _wiki_update_check
conn = sqlite3.connect('.dev-runtime/data/kol_scan.db')
hashes = [r[0] for r in conn.execute('SELECT content_hash FROM articles WHERE content_hash IS NOT NULL ORDER BY id DESC LIMIT 3').fetchall()]
result = asyncio.run(_wiki_update_check(hashes, conn, Path('kb/wiki')))
print(result)
"
```

**Result:**

```
hashes: ['9cbd555c68', '26b555ac6b', 'c94352c89c']
result: {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}
```

Hook fired, completed cleanly, no exceptions. Acceptable per plan-04 Task 4 ("all suggestions dropped by lint — also acceptable" — these dev DB hashes don't match content currently referenced in `kb/wiki/entities/openclaw.md`).

`git status kb/wiki/`: **working tree clean** — no atomic writes occurred (expected, no candidate suggestions emerged from the W0 placeholder entity page).

## Negative path UAT (lint guard)

Corrupted a synthetic wiki page with unresolved `^[article:ffffffffff]` + invalid `[[nonexistent-slug]]`, ran lint guards, verified JSONL log:

| Lint | Result |
|------|--------|
| `lint_citation_integrity` | caught `^[article:ffffffffff]` (not in known hashes) |
| `lint_backlink_validity` | caught `nonexistent-slug` (no `kb/wiki/entities/nonexistent-slug.md`) |
| Atomic write skipped | YES (corrupted page lived in tmp; never landed in `kb/wiki/`) |
| JSONL log persisted | YES — 2 entries written to `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl` |

JSONL evidence:

```json
{"ts": "2026-05-20T01:45:58.169646+00:00", "lint_name": "citation_integrity", "page": "...\\bad.md", "failures": ["^[article:ffffffffff]"], "context": "uat-negative-path"}
{"ts": "2026-05-20T01:45:58.171500+00:00", "lint_name": "backlink_validity", "page": "...\\bad.md", "failures": ["nonexistent-slug"], "context": "uat-negative-path"}
```

## Findings (non-blocking, surfaced for v1 cleanup)

1. **Hash format mismatch between lint regex and production hash function.**
   - `kb/wiki_lint.py:12` — `CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")` (10-char)
   - `lib/checkpoint.py:get_article_hash()` — returns 16-char SHA256 prefix
   - Dev DB content_hashes happen to be 10-char (older scheme), so lint regex aligns with stored data; new hashes from `get_article_hash` would NOT match the regex. Not blocking for W3 mock UAT, but real W1/W4 page generation will need either: (a) lint regex widened to `{10,16}`, or (b) `get_article_hash` truncated to 10-char in citation render.
   - Decision deferred to morning user review.

## Acceptance criteria (plan-04 Task 4)

- [x] Server-equivalent invocation succeeded — used direct Python entry per plan-04 Task 4 step 2 alternate (more focused than spinning local_serve.py for hook smoke)
- [x] Hook fires from end-of-cron path (covered by behavior-anchor test `test_wiki_hook_fires_after_layer2_drain` — committed at T3 `ef564c3`)
- [x] Lint blocks bad input (negative path verified above)
- [x] JSONL log evidence captured
- [x] Atomic write skipped on lint failure (verified)
- [x] Mode = mock (no real LLM call), 0 LLM cost incurred

## Status: PASS

W3 is shippable. Two findings flagged for morning review (hash regex width + decision on truncate-vs-widen).
