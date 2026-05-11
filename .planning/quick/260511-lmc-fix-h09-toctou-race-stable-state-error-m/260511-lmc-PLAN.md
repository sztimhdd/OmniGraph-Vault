---
phase: quick-260511-lmc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingest_wechat.py
  - tests/unit/test_ingest_article_processed_gate.py
autonomous: true
requirements: [H09-RACE-FIX]

must_haves:
  truths:
    - "_verify_doc_processed_or_raise returns True only when status='processed' AND error_msg is empty/null"
    - "A 'processed' entry with error_msg set causes the helper to continue retrying (not return early)"
    - "After seeing 'processed' + no error_msg, re-poll after STABLE_VERIFY_DELAY_S and confirm still 'processed' + no error_msg before returning"
    - "If stable re-check sees status flipped to non-processed, continue retry loop"
    - "pytest for test_ingest_article_processed_gate.py passes with 5 original tests + 5 new TOCTOU race tests"
    - "No changes to outer batch_ingest_from_spider.ingest_article, no changes to checkpoint, no changes to deepseek timeout"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Updated _verify_doc_processed_or_raise with stable-state + error_msg guard"
      contains: "STABLE_VERIFY_DELAY_S"
    - path: "tests/unit/test_ingest_article_processed_gate.py"
      provides: "5 new tests covering TOCTOU race scenarios"
      contains: "test_processed_with_error_msg_continues_retry"
  key_links:
    - from: "ingest_wechat._verify_doc_processed_or_raise"
      to: "rag.aget_docs_by_ids"
      via: "stable-check: re-poll after delay when first 'processed' seen"
      pattern: "asyncio.sleep.*STABLE_VERIFY_DELAY"
    - from: "_verify_doc_processed_or_raise"
      to: "entry.error_msg or entry.get('error_msg')"
      via: "error_msg guard before returning True"
      pattern: "error_msg.*continue"
---

<objective>
Fix the h09 TOCTOU race: _verify_doc_processed_or_raise must not return True when
LightRAG's doc_status shows 'processed' but is either (a) about to flip to 'failed'
or (b) already has error_msg set from a partial-failure DeepSeek 402.

Phase 0 investigation (cited below) confirms:
- lightrag/base.py:784 — DocProcessingStatus.error_msg: str | None = None; populated
  when status=FAILED (set to str(e) at lightrag/lightrag.py:2104 and :2236)
- lightrag/base.py:752-759 — DocStatus enum: PENDING/PROCESSING/PREPROCESSED/PROCESSED/FAILED
- LightRAG CAN write PROCESSED (lightrag.py:2158, after merge_nodes_and_edges succeeds)
  then write FAILED+error_msg (lightrag.py:2232, if merge raises) for the same doc_id
- For 2026-05-11 incident (DeepSeek 402): entity_relation_task at lightrag.py:2043
  raises 402 → caught at :2051 → FAILED+error_msg at :2100. Most likely mechanism:
  prior successful ingest left status='processed'; re-ingest started but poller saw
  the stale 'processed' before PROCESSING write landed; or concurrent task ordering
  caused a brief PROCESSED window before the FAILED overwrite.
- In all failure scenarios, LightRAG sets error_msg to the exception string.
  A genuinely processed doc has error_msg=None.

Fix: Combined Option C — (1) error_msg guard: if 'processed' AND error_msg non-empty
→ continue retry loop; (2) stable-state re-poll: if 'processed' AND error_msg empty
→ sleep STABLE_VERIFY_DELAY_S, re-fetch, confirm still 'processed' + no error_msg,
then return. Both checks must pass before returning True.

Purpose: Eliminate 2026-05-11 mystery rows (art_id=154/155/157/184 wrote
ingestions.ok despite LightRAG doc_status='failed'+'error_msg=Insufficient Balance').
Output: Updated ingest_wechat.py + 5 new tests in test_ingest_article_processed_gate.py
</objective>

<execution_context>
@/c/Users/huxxha/Desktop/OmniGraph-Vault/.planning/quick/260511-lmc-fix-h09-toctou-race-stable-state-error-m/260511-lmc-PLAN.md
</execution_context>

<context>
@/c/Users/huxxha/Desktop/OmniGraph-Vault/ingest_wechat.py
@/c/Users/huxxha/Desktop/OmniGraph-Vault/tests/unit/test_ingest_article_processed_gate.py

<interfaces>
<!-- Phase 0 findings: LightRAG SDK — cite for anti-fabrication -->

From venv/Lib/site-packages/lightrag/base.py:752-759:
```python
class DocStatus(str, Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    PREPROCESSED = "preprocessed"
    PROCESSED = "processed"
    FAILED = "failed"
```

From venv/Lib/site-packages/lightrag/base.py:762-787:
```python
@dataclass
class DocProcessingStatus:
    status: DocStatus
    error_msg: str | None = None  # set when status=FAILED, str(e)
    # ... other fields
```

From venv/Lib/site-packages/lightrag/lightrag.py (state transition sequence):
- Line 2000-2004: upsert(PROCESSING) — start of doc processing
- Line 2043-2049: entity_relation_task (_process_extract_entities) — calls DeepSeek
- Line 2051-2100: except block → upsert(FAILED, error_msg=str(e)) when entity extraction raises
- Line 2158-2178: upsert(PROCESSED) — only reached after merge_nodes_and_edges succeeds
- Line 2232-2253: upsert(FAILED, error_msg=str(e)) — merge failure path

Key insight: error_msg is NEVER set on a genuinely PROCESSED doc. It is always
set alongside FAILED status. If aget_docs_by_ids returns an entry with
status='processed' AND error_msg non-empty, that entry is stale/corrupt.

Existing _verify_doc_processed_or_raise (ingest_wechat.py:69-127):
```python
async def _verify_doc_processed_or_raise(
    rag, doc_id: str, *,
    max_retries: int = PROCESSED_VERIFY_MAX_RETRIES,
    backoff_s: float = PROCESSED_VERIFY_BACKOFF_S,
) -> None:
    last_status_val: str | None = None
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            statuses = await rag.aget_docs_by_ids([doc_id])
        except Exception as exc:
            last_exc = exc
            last_status_val = None
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_s)
            continue

        if not statuses or doc_id not in statuses:
            last_status_val = None
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_s)
            continue

        entry = statuses[doc_id]
        status_val = getattr(entry, "status", None)
        if status_val is None and isinstance(entry, dict):
            status_val = entry.get("status")
        last_status_val = status_val

        if _status_is_processed(status_val):
            return  # <-- BUG: no error_msg check, no stable-state re-poll

        if attempt < max_retries - 1:
            await asyncio.sleep(backoff_s)

    raise RuntimeError(
        f"post-ainsert PROCESSED verification failed for doc_id={doc_id} "
        f"after {max_retries} retries (backoff {backoff_s}s). "
        f"Last status={last_status_val!r}, "
        f"last_exc={last_exc.__class__.__name__ if last_exc else None}. ..."
    )
```

Constants to add (alongside existing PROCESSED_VERIFY_MAX_RETRIES / PROCESSED_VERIFY_BACKOFF_S):
```python
STABLE_VERIFY_DELAY_S = float(os.getenv("OMNIGRAPH_STABLE_VERIFY_DELAY", "5.0"))
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add stable-state + error_msg guard to _verify_doc_processed_or_raise</name>
  <files>ingest_wechat.py, tests/unit/test_ingest_article_processed_gate.py</files>
  <behavior>
    - Test A: doc has status='processed', error_msg="Insufficient Balance" → continues retry loop, eventually raises RuntimeError with "processed-with-error" in message
    - Test B: doc reaches 'processed' + no error_msg on first poll → re-polled after stable delay → still 'processed' + no error_msg → returns (no raise)
    - Test C: doc reaches 'processed' + no error_msg on first poll → stable re-poll sees status='failed' → continues retry loop, eventually raises RuntimeError
    - Test D: doc reaches 'processed' + no error_msg on first poll → stable re-poll sees 'processed' + error_msg="Insufficient Balance" → continues retry loop, eventually raises
    - Test E: DocStatus enum member (not string) passed as status_val — both dict and dataclass-like entries work
  </behavior>
  <action>
**Step 1 — Write 5 new tests in tests/unit/test_ingest_article_processed_gate.py**

Append after existing Test 6 (line 206). Tests must use `backoff_s=0.0` and
`stable_delay_s=0.0` to keep them fast. The helper will need a new `stable_delay_s`
kwarg (default = STABLE_VERIFY_DELAY_S) for test injection — add it alongside
existing `max_retries` and `backoff_s`.

Test naming:
- `test_processed_with_error_msg_continues_retry` — Option B error_msg guard (Test A above)
- `test_processed_stable_recheck_confirms_ok` — Option A stable-check happy path (Test B above)
- `test_processed_stable_recheck_sees_failed` — Option A stable-check flips to failed (Test C above)
- `test_processed_stable_recheck_sees_error_msg` — combined: stable recheck sees error_msg (Test D above)
- `test_processed_enum_member_with_error_msg` — DocStatus.PROCESSED enum object (not string) + error_msg set (Test E above)

For Test A, B, C, D: mock aget_docs_by_ids returns dict entries like:
  `{doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}}` (TOCTOU case)
  `{doc_id: {"status": "processed", "error_msg": None}}` (genuine success)
  `{doc_id: {"status": "failed", "error_msg": "..."}}` (flip case)

For Test E: use a MagicMock entry with `.status = DocStatus.PROCESSED` and
  `.error_msg = "Insufficient Balance"` (dataclass-like object path).

**Step 2 — Run tests in RED state (should fail because guard not yet added):**
```bash
cd /c/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v 2>&1 | tee .scratch/h09race-pytest-red-$(date +%Y%m%d-%H%M%S).log
```
Confirm 5 new tests FAIL, 6 existing tests PASS.

**Step 3 — Update ingest_wechat.py:**

3a. Add constant after PROCESSED_VERIFY_BACKOFF_S (around line 56):
```python
# quick-260511-lmc: stable-state re-poll delay. After first 'processed' observation,
# wait this many seconds and re-poll to confirm status is stable (not about to flip
# to 'failed' due to TOCTOU race). Eliminates 2026-05-11 mystery rows.
STABLE_VERIFY_DELAY_S = float(os.getenv("OMNIGRAPH_STABLE_VERIFY_DELAY", "5.0"))
```

3b. Add `stable_delay_s` parameter to `_verify_doc_processed_or_raise` signature:
```python
async def _verify_doc_processed_or_raise(
    rag,
    doc_id: str,
    *,
    max_retries: int = PROCESSED_VERIFY_MAX_RETRIES,
    backoff_s: float = PROCESSED_VERIFY_BACKOFF_S,
    stable_delay_s: float = STABLE_VERIFY_DELAY_S,
) -> None:
```

3c. Replace the `if _status_is_processed(status_val): return` block (line 114-115)
with the combined Option C guard. Extract error_msg from both dict and object entries:

```python
        if _status_is_processed(status_val):
            # Option B — error_msg guard: a genuinely processed doc has
            # error_msg=None. If error_msg is set, LightRAG wrote FAILED after
            # our status read — treat as failure and continue retry loop.
            # (lightrag/base.py:784; lightrag.py:2104,2236)
            error_msg = getattr(entry, "error_msg", None)
            if error_msg is None and isinstance(entry, dict):
                error_msg = entry.get("error_msg")
            if error_msg:
                last_status_val = f"processed-with-error: {str(error_msg)[:120]}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_s)
                continue

            # Option A — stable-state re-poll: sleep briefly then re-fetch to
            # confirm 'processed' is stable (not a stale entry about to flip).
            await asyncio.sleep(stable_delay_s)
            try:
                stable_statuses = await rag.aget_docs_by_ids([doc_id])
            except Exception:
                # Re-poll failed; don't trust the initial 'processed' — retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_s)
                continue
            stable_entry = (stable_statuses or {}).get(doc_id)
            stable_status_val = getattr(stable_entry, "status", None)
            if stable_status_val is None and isinstance(stable_entry, dict):
                stable_status_val = (stable_entry or {}).get("status")
            stable_error_msg = getattr(stable_entry, "error_msg", None)
            if stable_error_msg is None and isinstance(stable_entry, dict):
                stable_error_msg = (stable_entry or {}).get("error_msg")
            if _status_is_processed(stable_status_val) and not stable_error_msg:
                return  # confirmed stable: no error_msg, still processed
            # Stable check failed — update last_status_val and continue retry
            last_status_val = f"unstable-processed: recheck={stable_status_val!r} error={str(stable_error_msg or '')[:80]}"
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_s)
            continue
```

3d. Update the RuntimeError message to mention the new failure modes:
Replace the existing `raise RuntimeError(...)` to include note about stable-check
and error_msg guard in the diagnostic text. Keep doc_id, max_retries, last_status_val,
last_exc in the message — just update the final explanation sentence.

**Step 4 — Run tests GREEN:**
```bash
cd /c/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v 2>&1 | tee .scratch/h09race-pytest-green-$(date +%Y%m%d-%H%M%S).log
```
All 11 tests (6 existing + 5 new) must PASS. If any existing test fails, the
signature change broke something — check that `stable_delay_s=0.0` is not
required (it has a default and callers don't pass it).

**HARD STOPS (do NOT touch):**
- Do NOT modify batch_ingest_from_spider.py
- Do NOT modify tests/unit/test_ainsert_persistence_contract.py
- Do NOT change PROCESSED_VERIFY_MAX_RETRIES or PROCESSED_VERIFY_BACKOFF_S defaults
- Do NOT change MIN_INGEST_BODY_LEN
- Do NOT change lib/ files
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v 2>&1 | tee .scratch/h09race-pytest-$(date +%Y%m%d-%H%M%S).log; echo "Exit: $?"</automated>
  </verify>
  <done>
    - All 11 tests pass (6 original h09 tests + 5 new TOCTOU race tests)
    - ingest_wechat.py contains STABLE_VERIFY_DELAY_S constant
    - _verify_doc_processed_or_raise has stable_delay_s parameter
    - error_msg guard precedes stable re-poll in the processed branch
    - Commit: "fix(ingest-260511-h09r): h09 TOCTOU race — verify processed is stable + error_msg empty before returning, eliminates 2026-05-11 mystery rows from DeepSeek 402 partial-failure"
    - pytest log saved to .scratch/h09race-pytest-green-*.log (cited in commit body)
  </done>
</task>

</tasks>

<verification>
After task completion:

1. Full test suite regression check:
   ```bash
   cd /c/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -30
   ```
   All existing unit tests must still pass. No regressions.

2. Confirm STABLE_VERIFY_DELAY_S is in ingest_wechat.py:
   ```bash
   grep -n "STABLE_VERIFY_DELAY_S\|stable_delay_s\|error_msg" /c/Users/huxxha/Desktop/OmniGraph-Vault/ingest_wechat.py | head -20
   ```

3. Confirm OMNIGRAPH_STABLE_VERIFY_DELAY is env-overridable (present in grep above).

4. Confirm git commit landed:
   ```bash
   git -C /c/Users/huxxha/Desktop/OmniGraph-Vault log --oneline -3
   ```
</verification>

<success_criteria>
- 11/11 tests pass in test_ingest_article_processed_gate.py
- No regression in tests/unit/ suite
- _verify_doc_processed_or_raise performs two guards before returning True:
  1. error_msg guard (continue loop if error_msg non-empty even when status='processed')
  2. stable re-poll (sleep STABLE_VERIFY_DELAY_S, re-fetch, confirm status still 'processed' + no error_msg)
- STABLE_VERIFY_DELAY_S defaults to 5.0s, env-overridable via OMNIGRAPH_STABLE_VERIFY_DELAY
- Commit message exactly: "fix(ingest-260511-h09r): h09 TOCTOU race — verify processed is stable + error_msg empty before returning, eliminates 2026-05-11 mystery rows from DeepSeek 402 partial-failure"
- pytest log at .scratch/h09race-pytest-green-*.log cited in commit body
</success_criteria>

<output>
After completion, create `.planning/quick/260511-lmc-fix-h09-toctou-race-stable-state-error-m/260511-lmc-SUMMARY.md`
</output>
