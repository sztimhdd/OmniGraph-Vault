---
phase: 18-daily-ops-hygiene
plan: 02
subsystem: query-history
tags: [wave1, synthesis, cognee-replacement, jsonl, hyg-03]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 18-02 SUMMARY — JSONL query history replacing Cognee recall

**Status:** Complete
**Wave:** 1
**Requirements:** HYG-03
**Depends on:** —

---

## 1. What shipped

| Artifact | Change | Purpose |
|---|---|---|
| `kg_synthesize.py` | `+48` lines (constant + 2 helpers + prompt-injection + post-synth append) | Past-query memory via local JSONL |
| `tests/unit/test_query_history.py` | 112 lines, 7 tests | JSONL roundtrip + malformed tolerance + Cognee regression guard |

Tests: **7/7 pass**. Includes a static regression guard asserting `import cognee` + `recall_previous_context` + `remember_synthesis` stay OUT of `kg_synthesize.py`.

---

## 2. Decision locked

**Do NOT restore Cognee in `kg_synthesize.py`.** Replace with lightweight local JSONL history.

Rationale (carried from 18-02-PLAN `<objective>`):
- Wave 0 commit `0109c02` removed Cognee because (a) its LiteLLM→Vertex chain hit model-name 404s and (b) its module-level import blocked the asyncio loop. Even with GSD:quick's `_resolve_model()` fix for (a), (b) remains a latent risk.
- Cognee was providing ONE feature to `kg_synthesize.py`: recall past queries to add context. That feature is recoverable with ~30 lines of file I/O.
- Ingestion-side Cognee (`remember_article`, `cognee_batch_processor`) stays untouched per 05-00-SUMMARY § D.

Reopening condition for v3.4: empirical evidence that Cognee graph-aware recall outperforms flat JSONL for synthesis quality. Not anticipated.

---

## 3. File layout

```
~/.hermes/omonigraph-vault/query_history.jsonl
```

- Typo-preserving parent dir name (CLAUDE.md convention).
- Append-only; one JSON object per line.
- Format: `{"ts": "2026-05-03T09:00:00Z", "query": "...", "mode": "hybrid", "response_len": 1466}`
- Readable via `jq` for ops.

---

## 4. Prompt injection shape

Before each `rag.aquery`, reads last 10 queries (newest first) and injects a `Previous queries for context:` block between the CRITICAL image-URL directive and the current query. When history is empty, the block is skipped (empty string concatenation is safe).

After a successful `rag.aquery` (non-empty response), appends one entry. Failure paths (aquery raises, response is `None`) skip the append — history reflects only successful synthesis attempts.

---

## 5. Acceptance criteria reconciliation

| Criterion | Status |
|---|---|
| `grep -q "QUERY_HISTORY_FILE"` | ✅ 5 occurrences |
| `grep -q "query_history.jsonl"` | ✅ 1 occurrence |
| `grep -q "Previous queries for context"` | ✅ 1 occurrence |
| `! grep -q "^import cognee"` | ✅ absent |
| `! grep -q "recall_previous_context\|remember_synthesis"` | ✅ absent |
| 5 pytest tests pass | ✅ 7/7 pass (6 functional + 1 regression guard) |

---

## 6. Safety properties

1. **Read never blocks synthesis.** `_read_recent_query_history` wraps the entire read in one try/except → returns `[]` on any failure. Corrupted file = zero history; synthesis proceeds.
2. **Write never blocks synthesis.** `_append_query_history` wraps the write → prints a warning and continues. Disk full / permission error = zero history recorded; synthesis output already returned.
3. **Malformed lines tolerated.** Read loop `continue`s on json.loads errors so a single corrupted line does not poison the rest of the history.
4. **Missing parent dir auto-created.** `QUERY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)` on every append — first-run survives cleanly.

---

## 7. Commits

1. `feat(18-00): vertex live-probe ...` — previous plan
2. `feat(18-01): cap kept images per article at 60 ...` — previous plan
3. (this plan) — `feat(18-02): JSONL query history replacing Cognee (HYG-03)`

---

## 8. Hand-off

Plan 18-02 complete. Plan 18-03 (prompt directive extraction) starts next and depends on this plan's `custom_prompt` shape.
