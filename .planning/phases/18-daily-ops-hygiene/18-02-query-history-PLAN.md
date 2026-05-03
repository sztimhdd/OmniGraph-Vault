---
phase: 18-daily-ops-hygiene
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - kg_synthesize.py
  - tests/unit/test_query_history.py
autonomous: true
requirements: [HYG-03]
must_haves:
  truths:
    - "`kg_synthesize.py` no longer depends on Cognee for recall/remember (maintains 2026-05-02 post-0109c02 state)"
    - "New lightweight JSONL history at `~/.hermes/omonigraph-vault/query_history.jsonl` captures past queries"
    - "Before each synthesize, the last 10 entries are read and injected into the prompt as `Previous queries for context:`"
    - "After each successful synthesize, `{timestamp, query, mode, response_length}` is appended to the JSONL (atomic: open+write+close per line, no rewrite)"
    - "JSONL read/write never blocks synthesis (read wrapped in try/except → empty list on failure; write wrapped in try/except → logger.warning on failure)"
    - "Cognee import and call sites remain REMOVED from `kg_synthesize.py` — no regression to 2026-05-02 fix"
  artifacts:
    - path: "kg_synthesize.py"
      provides: "Past-query memory via local JSONL — replaces removed Cognee recall/remember"
      min_lines_touched: 30
    - path: "tests/unit/test_query_history.py"
      provides: "Tests for JSONL append, read-latest, empty-file tolerance, prompt-injection verification"
      min_lines: 80
  key_links:
    - from: "kg_synthesize.py::synthesize_response"
      to: "query_history.jsonl"
      via: "read last 10 entries before LLM call; append 1 entry after"
      pattern: "query_history.jsonl"
---

<objective>
Decide the HYG-03 restoration question (per Wave 0 Close-Out § F) with the YOLO default: **do NOT restore Cognee**. Replace the "past-query memory" feature with a lightweight local JSONL history.

Rationale:
- The 2026-05-02 removal (`0109c02`) fixed two root causes at once: (1) Cognee's LiteLLM→Vertex chain hit model-name 404s; (2) Cognee's module-level import blocked the asyncio event loop. Even with the parallel GSD:quick `_resolve_model()` fix, (2) remains a latent risk on any synthesis call.
- Cognee was providing one feature to `kg_synthesize.py`: recall past queries to add context. That feature is recoverable with ~30 lines of file I/O.
- Ingestion-side Cognee (`remember_article` in `ingest_wechat.py`, `cognee_batch_processor.py`) is untouched per 05-00-SUMMARY § D and stays untouched here.

Decision locked: **JSONL history replacement, no Cognee restoration.** If future evidence shows Cognee's graph-aware recall beats flat JSONL history for synthesis quality, reopen as v3.4 work — not v3.3.
</objective>

<execution_context>
Windows dev machine. `kg_synthesize.py` touches LightRAG + DeepSeek — the LightRAG init path is live and reaches Vertex AI; the DeepSeek LLM call is Umbrella-blocked locally. Unit tests mock the DeepSeek call and the LightRAG init — they operate on pure text transforms around the prompt.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-00-SUMMARY.md
@kg_synthesize.py
@config.py

<where_the_data_lives>
Runtime path: `~/.hermes/omonigraph-vault/query_history.jsonl` (follows the typo-preserving convention in CLAUDE.md — DO NOT rename to `omnigraph-vault`).

Format: one JSON object per line:
```
{"ts": "2026-05-03T09:00:00Z", "query": "...", "mode": "hybrid", "response_len": 1466}
```

Readable with `jq` for ops. Writable append-only. No locking needed — single-writer (one synthesis call at a time from one operator or one cron invocation; concurrent writes would mean two synthesis calls racing, which is not a current use case).
</where_the_data_lives>

<prompt_injection_shape>
Current custom_prompt in `kg_synthesize.py:58–65`:

```python
custom_prompt = (
    "You are a knowledge synthesizer. "
    "CRITICAL: when the context below contains image URLs like "
    "http://localhost:8765/..., you MUST include them as "
    "![description](url) INLINE in your answer near the relevant text. "
    "Do NOT skip images. Do NOT drop URLs.\n\n"
    f"Query: {query_text}"
)
```

Extension: read last 10 history entries, inject as a prefix block between the CRITICAL directive and the query:

```python
history = _read_recent_query_history(limit=10)  # returns list[str] of prior queries
history_block = ""
if history:
    history_block = "Previous queries for context (most recent first):\n" + \
                    "\n".join(f"- {q}" for q in history) + "\n\n"

custom_prompt = (
    "You are a knowledge synthesizer. ..."
    "\n\n"
    + history_block
    + f"Query: {query_text}"
)
```

After `rag.aquery` returns successfully: `_append_query_history(query_text, mode, len(response))`. Before-return so the history reflects only successful synthesis attempts.
</prompt_injection_shape>

<helper_shape>
Two module-level helpers in `kg_synthesize.py`:

```python
from pathlib import Path

QUERY_HISTORY_FILE = Path.home() / ".hermes" / "omonigraph-vault" / "query_history.jsonl"

def _read_recent_query_history(limit: int = 10) -> list[str]:
    """Return the most-recent N queries, newest first. Empty list on any failure."""
    try:
        if not QUERY_HISTORY_FILE.exists():
            return []
        with QUERY_HISTORY_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        # Newest first. Parse each line; skip malformed.
        out: list[str] = []
        for line in reversed(lines):
            try:
                entry = json.loads(line)
                q = entry.get("query")
                if isinstance(q, str) and q:
                    out.append(q)
                    if len(out) >= limit:
                        break
            except Exception:
                continue
        return out
    except Exception:
        return []

def _append_query_history(query: str, mode: str, response_len: int) -> None:
    """Atomic-per-line append. Silent on failure (never blocks synthesis)."""
    try:
        QUERY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        entry = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "query": query,
            "mode": mode,
            "response_len": response_len,
        }
        with QUERY_HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Never raise; history is best-effort.
        print(f"Warning: query history append failed: {e}")
```
</helper_shape>

<unit_test_shape>
Tests use `tmp_path` + monkeypatch of `QUERY_HISTORY_FILE` to avoid polluting real `~/.hermes/omonigraph-vault/`. Four tests:

1. `test_read_empty_file_returns_empty_list` — no file on disk → `_read_recent_query_history()` returns `[]`.
2. `test_append_then_read_roundtrip` — append 3 entries, read with `limit=10` → 3 entries returned, newest-first order.
3. `test_read_skips_malformed_lines` — write 2 valid + 1 garbage line → 2 queries returned, no exception.
4. `test_append_survives_missing_parent_dir` — delete parent dir first → append auto-creates dir, succeeds.

(A 5th integration test that exercises the prompt-injection path lives as a smoke check in the verify step, not as a pytest — it requires mocking `rag.aquery` which is architecturally awkward for unit scope.)
</unit_test_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-02.1: Add JSONL query-history helpers + wire into synthesize_response</name>
  <files>kg_synthesize.py, tests/unit/test_query_history.py</files>
  <behavior>
    - `_read_recent_query_history(limit)` returns list[str] newest-first; empty list on any failure.
    - `_append_query_history(query, mode, response_len)` appends one JSONL line; silent on any failure.
    - `synthesize_response` reads history before building `custom_prompt`; injects as `Previous queries for context:` prefix block when non-empty; skipped when empty.
    - After successful `rag.aquery`, appends `{ts, query, mode, response_len}`.
    - **Cognee stays OUT of `kg_synthesize.py`** — no `import cognee`, no `recall_previous_context`, no `remember_synthesis`. Regression-guarded by a static grep test.
  </behavior>
  <read_first>
    - kg_synthesize.py entire file — current post-Cognee-removal state is the baseline
    - 05-00-SUMMARY § D + § F — Cognee removal rationale + restoration decision context
    - CLAUDE.md — `~/.hermes/omonigraph-vault/` typo-preserving rule
  </read_first>
  <action>
    1. Add `QUERY_HISTORY_FILE` module constant + two helpers `_read_recent_query_history` + `_append_query_history`.
    2. In `synthesize_response`, insert `history_block` between the CRITICAL directive and the query line.
    3. After successful `rag.aquery`, call `_append_query_history(query_text, mode, len(response))` — wrap in try/except that never propagates.
    4. Write 4 unit tests per `<unit_test_shape>` above. Add a 5th static-grep test that asserts `import cognee` is NOT in `kg_synthesize.py` (regression guard).
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_query_history.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "QUERY_HISTORY_FILE" kg_synthesize.py` — constant present.
    - `grep -q "query_history.jsonl" kg_synthesize.py` — correct filename.
    - `grep -q "Previous queries for context" kg_synthesize.py` — injection string present.
    - `! grep -q "import cognee" kg_synthesize.py` — Cognee stays out (regression guard).
    - `! grep -q "recall_previous_context\|remember_synthesis" kg_synthesize.py` — Cognee call sites stay removed.
    - 5 pytest tests pass.
  </acceptance_criteria>
  <done>kg_synthesize has past-query memory without Cognee dependency.</done>
</task>

</tasks>

<verification>
- Unit tests green (4 functional + 1 regression-guard).
- Cognee removal preserved.
- No Hermes-side live run required for Wave 1 — real-deployment smoke lives in HYG-05 (Wave 2) single-fixture gate.
</verification>

<success_criteria>
- HYG-03 satisfied: `kg_synthesize` has history-aware prompting without reintroducing Cognee's Vertex + async-blocking risks.
- Reversible: if a future v3.4 decision is to restore Cognee, the helpers + JSONL file coexist with Cognee calls; JSONL history remains the "always-on" floor.
</success_criteria>

<output>
After completion, create `.planning/phases/18-daily-ops-hygiene/18-02-SUMMARY.md` documenting: decision rationale (JSONL over Cognee restoration), file location, prompt-injection shape, any follow-up v3.4 reopening criteria.
</output>
