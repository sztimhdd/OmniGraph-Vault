---
phase: quick-260429
plan: 01
subsystem: kol-ingest-cli
tags: [cli, argparse, sql, back-compat, d-11]
requirements: [D-11]
requires: []
provides:
  - "multi-keyword --topic-filter on batch_ingest_from_spider.py"
  - "IN (...) SQL query across multiple classification topics"
affects:
  - "Plan 05-00b KOL catch-up (unblocks single-pass ingest of 4 keywords)"
tech-stack:
  added: []
  patterns:
    - "argparse leaves --topic-filter as str; split happens after parse_args()"
    - "parameterised IN clause via f-string placeholders + tuple unpack"
key-files:
  created: []
  modified:
    - batch_ingest_from_spider.py
decisions:
  - "Kept argparse type=str (no nargs='+') for zero CLI interface change — split in main()"
  - "ingest_from_db accepts str | list[str] and normalises internally, preserving an ergonomic signature"
metrics:
  duration_minutes: 6
  completed: 2026-04-29
---

# Quick Task 260429-got: Multi-keyword --topic-filter Summary

One-liner: Extended `batch_ingest_from_spider.py` so `--topic-filter` accepts a comma-separated list of keywords matching any of them via SQL `IN (...)`, per D-11 of 05-CONTEXT — needed to unblock Plan 05-00b's single-pass `openclaw,hermes,agent,harness` ingest.

## What Changed

Six surgical edits to a single file, `batch_ingest_from_spider.py`:

1. **`_build_filter_prompt`** (lines 177–196) — type annotation `str | None` → `list[str] | None`; prompt text now quotes each keyword and says "ANY of: ..." instead of a single bare topic.
2. **`batch_classify_articles`** (line 288) — type annotation only: `str | None` → `list[str] | None`. No logic change; value is passed straight through.
3. **Off-topic filter reason** (lines 361–364) — builds `", ".join(topic_filter)` so the filtered-out diagnostic reads `off-topic (not about any of: openclaw, hermes, agent, harness)`.
4. **`ingest_from_db`** (lines 545–581) — signature `topic: str | list[str]`; normalises via `topics = [topic] if isinstance(topic, str) else topic`; SQL switched from `WHERE c.topic = ?` to `WHERE c.topic IN ({placeholders})` with `*topics` unpacked into the parameter tuple; log messages now show the list.
5. **`run()` kwargs** (line 424) — inline comment `# list[str] | None after main() split`; no logic change.
6. **`main()` splits** (lines 622–633) — after `args = parser.parse_args()`, converts the raw string to `topic_keywords: list[str] | None` via `split(',')` + `strip()` + filter-empty; `ingest_from_db(topic_keywords, ...)` and `run(topic_filter=topic_keywords, ...)` now receive the list.

Argparse `--topic-filter` stayed `type=str` — there is zero user-facing CLI interface change.

## Must-Haves Truths — Verified

| Truth                                     | Evidence                                                                                                              |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Multi-keyword matches ANY of N            | SQL uses `IN (?,?,?,?)` + `c.relevant = 1` — classical OR semantics                                                   |
| Single keyword still works identically    | `isinstance(topic, str)` → `[topic]` normalisation path; produces `IN (?)` with one placeholder (equivalent to `= ?`) |
| Whitespace around commas stripped         | `[k.strip() for k in raw.split(",")]` — verified: `'a, b, c'` → `['a','b','c']`                                       |
| Trailing commas ignored                   | `if k.strip()` filter — verified: `'a,b,'` → `['a','b']`                                                              |
| `--from-db` multi-keyword hits DB with OR | Confirmed via source inspection of the new SQL                                                                        |

## Verification

**Automated smoke tests** (all passed on local Windows, no DB present):

```text
python -c "import batch_ingest_from_spider; print('import OK')"
  -> import OK
python batch_ingest_from_spider.py --help
  -> unchanged interface (--topic-filter TOPIC_FILTER still listed, no nargs changes)
python batch_ingest_from_spider.py --from-db --topic-filter "openclaw,hermes,agent,harness" --min-depth 2 --dry-run
  -> ERROR DB not found: .../data/kol_scan.db. Run batch_scan_kol.py first.
  -> clean expected-failure path (argparse + split + ingest_from_db + DB-not-found guard all traced without raising)
python batch_ingest_from_spider.py --from-db --topic-filter openclaw --min-depth 2 --dry-run
  -> ERROR DB not found: ... (single-keyword back-compat path reaches the same guard identically)
```

**Split logic** exercised directly:

```text
'openclaw'                        -> ['openclaw']
'openclaw,hermes,agent,harness'   -> ['openclaw', 'hermes', 'agent', 'harness']
'a, b, c'                         -> ['a', 'b', 'c']
'a,b,'                            -> ['a', 'b']
' , , '                           -> None
''                                -> None
```

All 5 must_haves truths held.

### Deferred Smoke-Test

The full end-to-end smoke test against real `kol_scan.db` is deferred — the DB lives on the remote Hermes PC (WSL2), not on this local dev box. The local runs above confirmed:

- argparse parses the multi-keyword string without error
- the value splits into the correct list shape
- `ingest_from_db()` is invoked with the list and reaches the DB-existence guard cleanly
- no TypeError, no ArgumentParser error, no SQL-syntax-at-Python-compile-time error

Full DB-backed execution will happen when Plan 05-00b is resumed on the Hermes host.

## Deviations from Plan

None — plan executed exactly as written. Each of the 6 edits landed at the lines the plan specified, with the signatures and strings the plan specified. No auto-fixes (Rules 1–3) fired.

## Known Stubs

None. The change is a contained feature extension; no placeholder data paths introduced.

## Files Touched

- `batch_ingest_from_spider.py` — 6 surgical edits (type annotations, prompt text, filter reason, SQL `IN` clause, run() comment, main() split + dispatch)

No other files modified. `.planning/quick/260429-got-extend-batch-ingest-from-spider-py-to-su/260429-got-SUMMARY.md` (this file) is the only new artifact.

## Self-Check: PASSED

- FOUND: batch_ingest_from_spider.py (6 edits applied, verified by re-read of lines 177–206, 358–370, 543–588, 615–644)
- FOUND: .planning/quick/260429-got-extend-batch-ingest-from-spider-py-to-su/260429-got-SUMMARY.md (this file)
- FOUND: import succeeds, --help output unchanged, multi-keyword and single-keyword dry-runs both trace to the expected DB-not-found guard without raising
- Commit hash: 4bf1613 (feat(quick-260429): multi-keyword --topic-filter in batch_ingest_from_spider) — note: stored hash lags HEAD by one amend cycle; see `git log -1 -- .planning/quick/260429-got-extend-batch-ingest-from-spider-py-to-su/260429-got-SUMMARY.md` for canonical value
