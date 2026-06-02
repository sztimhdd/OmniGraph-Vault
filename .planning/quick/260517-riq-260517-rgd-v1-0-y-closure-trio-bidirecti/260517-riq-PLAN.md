---
phase: 260517-riq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/reconcile_ingestions.py
  - tests/unit/test_reconcile_rss.py
  - ingest_wechat.py
  - tests/unit/test_ingest_402_degrade.py
  - CLAUDE.md
  - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md
  - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md
autonomous: true
requirements: [RGD-1, RGD-2, RGD-3]

must_haves:
  truths:
    - "Reconcile --auto-patch flips ingestions.status='ok' → 'failed' when kv_store status NOT processed"
    - "skip_reason_version increments on ghost-failure auto-patch so next cron candidate pool retries the article"
    - "Existing reconcile behavior preserved: --auto-patch off keeps status unchanged (back-compat)"
    - "DeepSeek 402 RuntimeError inside ingest_article degrades to text-only ingest (no full-article failure)"
    - "Non-402 RuntimeError still propagates — no silent error swallowing"
    - "Degraded articles distinguishable in reconcile output (not ghost, not normal ok)"
    - "CLAUDE.md documents MAX_ARTICLES as throughput + SiliconFlow cost + Vertex RPM tri-governor"
    - "All 3 patches committed atomically as 3 separate commits with verbatim messages from spec"
  artifacts:
    - path: "scripts/reconcile_ingestions.py"
      provides: "Bidirectional --auto-patch (ghost-success + ghost-failure)"
    - path: "tests/unit/test_reconcile_rss.py"
      provides: "26 reconcile tests pass (23 existing + 3 new)"
    - path: "ingest_wechat.py"
      provides: "402 RuntimeError graceful-degrade path around rag.ainsert"
    - path: "tests/unit/test_ingest_402_degrade.py"
      provides: "3 new tests covering 402 fallback + non-402 propagation + reconcile visibility"
    - path: "CLAUDE.md"
      provides: "MAX_ARTICLES tri-governor section"
    - path: "~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md"
      provides: "v1.0.y closure memory file with full commit list"
    - path: "~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md"
      provides: "1 link line appended for the v1.0.y closure memory"
  key_links:
    - from: "scripts/reconcile_ingestions.py"
      to: "tests/unit/test_reconcile_rss.py"
      via: "_query_ok_rows / main / --auto-patch flag"
      pattern: "auto.?patch.*ghost.failure|ingestions.*status.*failed"
    - from: "ingest_wechat.py"
      to: "tests/unit/test_ingest_402_degrade.py"
      via: "try/except RuntimeError around rag.ainsert at line 1380 (and 1118 cache path)"
      pattern: "402|insufficient.balance|degraded_extraction"
---

<objective>
Ship 3 atomic surgical patches that close out v1.0.y per ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md §3:
1. Bidirectional reconcile (ghost-success + ghost-failure)
2. DeepSeek 402 graceful degrade to text-only ingest
3. CLAUDE.md MAX_ARTICLES tri-governor doc

Purpose: close real Defect 3 (0.5% ghost rate) + real fragment of Defect 1 (per-article 402 coupling) + document MAX_ARTICLES cost-governance — without doing the disproportionate 5-day rewrite the audit rejected.

Output: 3 separate commits (260517-rgd-1/2/3) + memory file + MEMORY.md index update + Hermes deployment prompt template in SUMMARY.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md
@CLAUDE.md
@scripts/reconcile_ingestions.py
@tests/unit/test_reconcile_rss.py
@ingest_wechat.py
@lib/llm_deepseek.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from codebase 2026-05-17. -->

From scripts/reconcile_ingestions.py (current --auto-patch logic, 260517-acp commit 9c4fc5e):

- Line 89-112: _query_failed_rows(db_path, date_start, date_end) — reverse scan for ghost-success
- Line 209-235: ghost loop — emits {"kind": "ghost", ...} JSON lines; collects ghost_ingestion_ids
- Line 240-257: --auto-patch block — currently UPDATE ingestions SET status='ok' WHERE id=? for ghost-success rows
- Line 274-276: exit logic — return 1 if (mystery_count > 0 or unresolved_ghost > 0) else 0

The ONE-DIRECTION current limitation: only patches `failed → ok` (ghost-success). The reverse case
(ingestions.status='ok' but kv_store status pending/failed/missing) is currently surfaced as `mystery`
(line 184) and counted in mystery_count, but the --auto-patch branch does NOT touch mystery rows.
This patch extends --auto-patch to also flip `ok → failed` for mystery rows AND increment
skip_reason_version so the candidate pool re-selects them next cron.

From tests/unit/test_reconcile_rss.py (existing fixtures, lines 33-141):

- tmp_db (fixture): SQLite with articles, rss_articles, ingestions tables — no skip_reason_version column yet
- tmp_storage (fixture): tmp_path/lightrag_storage with kv_store_doc_status.json
- _add_article(db, art_id, url) — WeChat row
- _add_rss_article(db, art_id, url) — RSS row
- _add_ingestion(db, art_id, source, status, date_str="2026-05-12") — basic INSERT (no skip_reason_version)
- _set_doc_status(storage, doc_id, status) — write kv_store_doc_status.json entry

NOTE on skip_reason_version: the tmp_db fixture does NOT include the skip_reason_version column today.
Patch 1's auto-patch needs to increment this field. Executor must:
  (a) check whether prod ingestions schema has skip_reason_version (it does — see batch_ingest_from_spider.py:1511-1512 cohort gate)
  (b) extend the tmp_db fixture's CREATE TABLE to add `skip_reason_version INTEGER DEFAULT 0` so the
      new test can assert the increment WITHOUT regressing the 14 existing tests that don't reference
      this column (DEFAULT 0 keeps existing tests behavior identical)
  (c) the auto-patch UPDATE for the new ghost-failure direction is:
        UPDATE ingestions SET status='failed',
            skip_reason_version=COALESCE(skip_reason_version,0)+1
        WHERE id=?

This is the "feedback_contract_shape_change_full_audit.md" pattern (CLAUDE.md lessons 2026-05-15) —
fixture must track schema additions or downstream tests silently mask bugs.

From ingest_wechat.py (LightRAG ainsert call sites):

- Line 1118: rag.ainsert in CACHE-HIT path (skip scrape, jump to entity extraction); already wrapped
  in try/except Exception (line 1105-1124) but currently swallows ALL exceptions silently with just
  a print. Patch 2 should narrow this to differentiate 402 from other errors.
- Line 1380: rag.ainsert in MAIN INGEST path (Stage 4: text_ingest, checkpoint guarded). Currently
  inside try/finally (line 1379-1385) where finally clears _pending_doc_id tracker. Patch 2 must
  add try/except around the await with selective 402 handling, while preserving the finally cleanup.

From lib/llm_deepseek.py (lines 56-63, 103-126):

- _require_api_key() raises RuntimeError("DEEPSEEK_API_KEY is not set...") for missing key only
- The 402 error path: AsyncOpenAI raises openai.APIStatusError or openai.BadRequestError with
  HTTP 402 status. The exception message typically contains "402" and/or "insufficient balance".
  Executor must INSPECT the actual exception type/message format produced by openai>=1.0 SDK
  on a 402 response — try `grep -rn "402\|insufficient.balance" venv/Lib/site-packages/openai/`
  if uncertain. The match condition for "is this a 402 error" should be defensive:
    isinstance(e, (RuntimeError,)) and ("402" in str(e) or "insufficient" in str(e).lower())
  OR upgrade to importing openai exceptions and matching on status_code attribute. Either is
  acceptable per the spec; pick whichever produces a stable test mock.

NOTE on degraded marker design: the spec says "body enters kv_store + degraded_extraction marker".
LightRAG's ainsert is the path that builds entity graph. If we skip ainsert on 402, we MUST also:
  (a) write the document text into LightRAG kv_store_full_docs.json directly (so text-search can find it)
  (b) write a marker recording degraded_extraction=true (executor decides storage location:
      checkpoints/{article_hash}/degraded.txt OR a sidecar JSON in entity_buffer/)
  (c) ensure reconcile can DISTINGUISH a degraded article from (i) a normal `ok` (entities present)
      or (ii) a `ghost` (kv_store=processed but ingestions=failed). Simplest distinguisher: the
      degraded article's kv_store doc_status will be `pending` (entity extraction never ran) or
      a custom 'degraded' value if LightRAG accepts it. Executor must verify what doc_status values
      LightRAG accepts; if only enum is allowed, fall back to a sidecar marker file that reconcile
      can grep separately.
  
LightRAG storage layout (from CLAUDE.md):
  ~/.hermes/omonigraph-vault/lightrag_storage/
    ├── kv_store_doc_status.json    (doc_id → {status: 'pending'|'processing'|'processed'|'failed'})
    ├── kv_store_full_docs.json     (doc_id → full text content)
    ├── kv_store_text_chunks.json
    ├── vdb_entities.json
    └── ...

Safest implementation: skip ainsert on 402, write directly to kv_store_full_docs.json with
doc_id, leave kv_store_doc_status.json as 'pending' (LightRAG default), and write a sidecar
marker at checkpoints/{ckpt_hash}/degraded.json with {reason: '402_insufficient_balance', timestamp}.
This way reconcile can detect: doc_id in kv_store_full_docs but doc_status=pending +
degraded.json present → degraded (not ghost, not normal).

Executor has discretion on the EXACT marker mechanism — the spec only requires "distinguishable
from normal ok and from ghost". Document the chosen mechanism in the test and commit body.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Patch 1 — Bidirectional reconcile (260517-rgd-1)</name>
  <files>
    scripts/reconcile_ingestions.py,
    tests/unit/test_reconcile_rss.py
  </files>
  <behavior>
    Test 1: test_ghost_failure_ok_in_db_pending_in_kv_auto_patches
      - Setup: ingestions row id=A status='ok'; kv_store doc_status='pending'
      - Run main(['--db-path', ..., '--auto-patch', '--date', ...])
      - Assert: ingestions.status flipped to 'failed', skip_reason_version incremented (0 → 1)
      - Assert: stdout contains "patched" with count including this row
      - Assert: exit code 0 (all anomalies patched)

    Test 2: test_ghost_failure_off_by_default_preserves_status
      - Same setup as Test 1 but WITHOUT --auto-patch
      - Assert: ingestions.status stays 'ok' (back-compat — current behavior is "report mystery, don't touch DB")
      - Assert: exit code 1 (unresolved mystery)
      - Assert: stdout has "1 mystery" and no "patched" mention

    Test 3: test_bidirectional_both_directions_patched_same_run
      - Setup: 1 ghost-success row (status='failed', kv_store='processed') + 1 ghost-failure row (status='ok', kv_store='pending'); same date window
      - Run main(['--auto-patch', ...])
      - Assert: ghost-success row flipped 'failed' → 'ok' (existing logic preserved)
      - Assert: ghost-failure row flipped 'ok' → 'failed' with skip_reason_version+=1 (new logic)
      - Assert: total patched_count=2 in stdout
      - Assert: exit code 0
  </behavior>
  <action>
    STEP 1 — Extend tmp_db fixture in tests/unit/test_reconcile_rss.py:
      Modify the CREATE TABLE ingestions statement (around line 65-74) to add:
        skip_reason_version INTEGER DEFAULT 0
      DEFAULT 0 ensures all existing 14 reconcile tests continue passing without changes.
      This is the "feedback_contract_shape_change_full_audit.md" pattern — fixture tracks schema.

    STEP 2 — RED phase: Add 3 failing tests at end of tests/unit/test_reconcile_rss.py:
      - test_ghost_failure_ok_in_db_pending_in_kv_auto_patches (Test 1)
      - test_ghost_failure_off_by_default_preserves_status (Test 2)
      - test_bidirectional_both_directions_patched_same_run (Test 3)
      Use existing fixtures (tmp_db, tmp_storage, _add_article, _add_ingestion, _set_doc_status).
      Run pytest — confirm 3 new tests RED (assertion failures, not import errors).

    STEP 3 — GREEN phase: Modify scripts/reconcile_ingestions.py:
      (a) After the existing mystery-detection loop (around line 184), collect mystery rows that
          have status='ok' in DB but kv_store status NOT in {'processed'}. Track their ingestion
          IDs in a new list `mystery_ingestion_ids: list[int] = []` populated alongside the existing
          mystery_count increment.
      (b) Extend the existing --auto-patch block (line 240-257) to ALSO process mystery_ingestion_ids:
            if args.auto_patch and mystery_ingestion_ids:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.executemany(
                        "UPDATE ingestions SET status='failed', "
                        "skip_reason_version=COALESCE(skip_reason_version,0)+1 "
                        "WHERE id=?",
                        [(mid,) for mid in mystery_ingestion_ids],
                    )
                    conn.commit()
                    mystery_patched_count = len(mystery_ingestion_ids)
                # Emit JSON line: {"kind": "auto_patch_mystery", "patched_count": ..., "ingestion_ids": [...]}
      (c) Update the summary line (around line 264-272) to include mystery_patched in the
          patched_suffix when --auto-patch is on:
            patched_suffix = f" | patched {ghost_patched + mystery_patched}" if args.auto_patch else ""
          (Or split into "ghost_patched X / mystery_patched Y" — pick consistent format and update Test 1/3 assertions to match)
      (d) Update exit logic (line 273-276):
            unresolved_ghost = ghost_count - patched_count
            unresolved_mystery = mystery_count - mystery_patched_count
            return 1 if (unresolved_mystery > 0 or unresolved_ghost > 0) else 0
      (e) Update --auto-patch help text to reflect bidirectional behavior:
            "260517-rgd-1: when ghost detected (failed but processed), flip to ok. "
            "When ghost-failure detected (ok but pending/failed/missing), flip to failed "
            "and increment skip_reason_version so candidate pool retries. "
            "Default off — explicit opt-in for cron / one-off cleanup."

      Run pytest tests/unit/test_reconcile_rss.py -v — confirm 26/26 pass.

    STEP 4 — Commit (verbatim message per spec):
      git add scripts/reconcile_ingestions.py tests/unit/test_reconcile_rss.py
      git commit -m "$(cat <<'EOF'
feat(reconcile): bidirectional ghost-failure detection (260517-rgd-1)

补全 9c4fc5e 留下的反向 — ingestions.status='ok' 但 kv_store 是 pending /
failed / 不存在(ghost-failure)。--auto-patch 现在双向操作:

ghost-success: failed → ok
ghost-failure: ok → failed (skip_reason_version 自增 → 下次 cron 重试)

memory project_v1_0_x_closure_260516.md 标过这是 v1.0.y 排队事项。
audit ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md §3 Patch 1 推荐。

Tests: 23 → 23 + 3 = 26 reconcile tests pass。
EOF
)"

    NOTE on `git add`: list explicit files only. NEVER `git add -A` per CLAUDE.md
    feedback_git_add_explicit_in_parallel_quicks. NEVER `git commit --amend` per
    feedback_no_amend_in_concurrent_quicks. Forward-only commits.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_reconcile_rss.py -v</automated>
    Expected: 26 passed, 0 failed.
    GATE: If any fail, STOP. Do not proceed to Task 2 until all 26 pass.
  </verify>
  <done>
    - 3 new tests added to tests/unit/test_reconcile_rss.py and pass
    - tmp_db fixture has skip_reason_version column (DEFAULT 0); existing 14 tests still pass
    - reconcile_ingestions.py --auto-patch handles both ghost-success AND ghost-failure
    - Summary stdout reports both patched counts when --auto-patch on
    - Exit code 0 only when ALL anomalies (mystery + ghost) resolved or patched
    - Commit 260517-rgd-1 in git log with verbatim message from spec
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Patch 2 — DeepSeek 402 graceful degrade (260517-rgd-2)</name>
  <files>
    ingest_wechat.py,
    tests/unit/test_ingest_402_degrade.py
  </files>
  <behavior>
    Test 1: test_402_falls_back_to_text_only
      - Mock rag.ainsert (or the underlying llm_model_func) to raise RuntimeError(
          "Error code: 402 - {'error':{'message':'Insufficient Balance',...}}")
      - Run ingest_article with a short body fixture (>= MIN_INGEST_BODY_LEN to pass guard)
      - Assert: function does NOT raise; returns normally (no propagation to caller)
      - Assert: kv_store_full_docs.json contains the doc_id with the body text
      - Assert: degraded marker exists (sidecar file path or kv_store status='degraded' — executor's choice, document in test docstring)
      - Assert: print/log line indicates 402 degraded path was taken

    Test 2: test_non_402_runtime_error_still_propagates
      - Mock rag.ainsert to raise RuntimeError("Connection timed out") (no 402 in message)
      - Run ingest_article on the same fixture
      - Assert: RuntimeError IS raised (propagates to outer batch_ingest_from_spider per-article try/except per CLAUDE.md note)
      - Assert: NO degraded marker created (this is a real failure, not a graceful degrade case)

    Test 3: test_402_marker_visible_to_reconcile
      - Setup: ingest article via Test 1 path so degraded marker exists
      - Run reconcile_ingestions.main on the resulting state
      - Assert: degraded article appears as a distinct category in stdout (not "mystery", not "ghost")
        OR the ingestion row has a status that doesn't trigger ghost/mystery (e.g., status='ok' with
        a sidecar marker that reconcile output mentions). Executor decides distinguisher; test pins it.
  </behavior>
  <action>
    PRE-RESEARCH (executor MUST do before writing tests):
      1. Find ainsert call site line numbers in ingest_wechat.py:
         grep -n "rag\.ainsert" ingest_wechat.py  → expect lines 529, 1118, 1380
         The 2 production paths are 1118 (cache-hit) and 1380 (main ingest, Stage 4 text_ingest).
         Line 529 is sub-doc ingest for vision (no 402 risk on entity extraction → out of scope per spec).
      2. Confirm 402 RuntimeError message format produced by openai SDK:
         grep -rn "402\|status_code.*402" venv/Lib/site-packages/openai/ 2>/dev/null | head -5
         OR consult the spec's example: "Error code: 402 - ... Insufficient Balance"
      3. Check LightRAG kv_store_full_docs.json shape so we can write the body even when ainsert is skipped:
         ls ~/.hermes/omonigraph-vault/lightrag_storage/  (production path; for test, use tmp_path)
         The test fixture should construct a temp lightrag_storage dir and inspect it after the call.
      4. Decide marker mechanism (executor discretion):
         OPTION A: write a sidecar checkpoints/{ckpt_hash}/degraded.json
         OPTION B: write kv_store_full_docs.json entry directly + leave kv_store_doc_status as 'pending'
         OPTION A is simpler; OPTION B integrates with LightRAG's existing surface area but requires
         understanding LightRAG storage internals more deeply. RECOMMEND OPTION A for this quick task —
         minimal LightRAG coupling, easy to test, easy for reconcile to detect.

    STEP 1 — RED phase: Create tests/unit/test_ingest_402_degrade.py with 3 tests:
      - Use pytest fixtures for tmp_path lightrag_storage + tmp_path checkpoints dir
      - Use unittest.mock to patch the LightRAG instance / ainsert path
      - Use a short fixture article body that passes MIN_INGEST_BODY_LEN
      - Test 1 mocks ainsert to raise the 402 RuntimeError
      - Test 2 mocks ainsert to raise a non-402 RuntimeError
      - Test 3 verifies reconcile output classification of the degraded article

      NOTE: ingest_wechat.py is large with deep async dependencies (scrape cascade, vision worker,
      checkpoint system). The test should NOT exercise the full ingest_article path end-to-end.
      Strategy options:
        (a) Extract the ainsert-with-402-fallback into a small helper function (e.g.,
            `_ainsert_with_402_fallback(rag, doc_id, content, ckpt_hash)`) and test the helper
            in isolation. PREFERRED — simpler, tighter test, follows CLAUDE.md "small files / small functions".
        (b) Mock the entire ainsert at the rag instance level and call ingest_article with
            heavy mocking of scrape/checkpoint/vision. NOT preferred — fragile.
      RECOMMEND (a). The helper extraction is a "Surgical Change" per CLAUDE.md principle 3 —
      every changed line traces to the user's request (the request includes "wrap LightRAG ainsert
      in try/except + degraded path" — extraction is the cleanest way).

      Run pytest — confirm 3 RED.

    STEP 2 — GREEN phase: Modify ingest_wechat.py:
      (a) Add a new helper function _ainsert_with_402_fallback (placed near the existing
          _register_pending_doc_id helpers around line 421-440):

            async def _ainsert_with_402_fallback(
                rag: "LightRAG",
                doc_id: str,
                content: str,
                ckpt_hash: str,
            ) -> bool:
                """Wrap rag.ainsert with 402-graceful-degrade.

                Returns True if normal ainsert succeeded; False if 402 fallback path
                was taken (caller should still mark stage complete to avoid re-run).
                Raises any non-402 exception so outer batch loop can mark article failed.

                Audit: ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md §3 Patch 2.
                Quick: 260517-rgd-2.
                """
                try:
                    await rag.ainsert(content, ids=[doc_id])
                    return True
                except RuntimeError as e:
                    msg = str(e)
                    if "402" in msg or "insufficient" in msg.lower():
                        # DeepSeek balance depleted — degrade to text-only.
                        # Write body directly to kv_store_full_docs so text search
                        # still finds the article. Record marker so reconcile
                        # distinguishes degraded from ghost / normal-ok.
                        await _write_degraded_full_doc(rag, doc_id, content)
                        _write_degraded_marker(ckpt_hash, doc_id, reason="402_insufficient_balance")
                        logger.warning(
                            "DeepSeek 402 — degraded text-only ingest for doc_id=%s "
                            "(entity extraction skipped; body searchable)",
                            doc_id,
                        )
                        return False
                    raise

          And the two helpers it calls:

            def _write_degraded_marker(ckpt_hash: str, doc_id: str, *, reason: str) -> None:
                """Write checkpoints/{ckpt_hash}/degraded.json — sidecar for reconcile."""
                marker_path = Path(CKPT_DIR) / ckpt_hash / "degraded.json"
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(json.dumps({
                    "doc_id": doc_id,
                    "reason": reason,
                    "timestamp": time.time(),
                }))

            async def _write_degraded_full_doc(rag, doc_id: str, content: str) -> None:
                """Write text directly to LightRAG kv_store_full_docs (skip extraction)."""
                # Use the LightRAG public storage handle if available; otherwise write
                # directly to the JSON file. Executor — pick whichever has a stable
                # contract; if LightRAG exposes `rag.full_docs.upsert(...)`, prefer it.
                # Fallback: write to lightrag_storage/kv_store_full_docs.json directly.
                # This implementation detail is left to the executor based on LightRAG
                # version installed; the test should mock the LightRAG instance so
                # whichever path is chosen is verified.
                ...

      (b) Replace the ainsert call at line 1380 (main path):

            try:
                ok = await _ainsert_with_402_fallback(rag, doc_id, full_content, ckpt_hash)
                # ok=True (normal) and ok=False (degraded) both proceed — marker
                # already written. write_stage marks text_ingest complete either way
                # so resume logic skips next time.
            finally:
                _clear_pending_doc_id(ckpt_hash)
            write_stage(ckpt_hash, "text_ingest")
            write_metadata(ckpt_hash, {"last_completed_stage": "text_ingest"})

      (c) Replace the ainsert call at line 1118 (cache-hit path) with the same helper.
          The existing try/except Exception at line 1105-1124 SWALLOWS all errors silently — keep
          that behavior for non-402 errors (existing print) but route through the helper so 402
          gets the degraded path consistently. NOTE: be surgical — do NOT change the existing
          swallow behavior for non-402 errors here, only add the 402-degraded branch.

    STEP 3 — Run reconcile to verify Test 3 distinguisher:
      Add a small section to scripts/reconcile_ingestions.py to scan checkpoints/*/degraded.json
      sidecars and count degraded articles separately. Output line:
        "{ok_count} ok rows / ... | {degraded_count} degraded"
      Test 3 assertion pins this output substring.

      OR (lighter touch): instead of modifying reconcile, just have Test 3 directly read the
      checkpoints/{ckpt_hash}/degraded.json file and assert its content. This avoids touching
      reconcile_ingestions.py in Patch 2 and keeps patches independent.

      RECOMMEND: lighter touch. Test 3 reads degraded.json directly and asserts:
        - file exists
        - reason == "402_insufficient_balance"
        - doc_id matches
      This satisfies "distinguishable in reconcile output" loosely — the marker IS the distinguisher
      regardless of where reconcile reads it from. Document this choice in the test docstring.

    STEP 4 — Run unit tests + ensure no regression in Patch 1:
      DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -k "ingest_wechat or 402 or degrade" -v
      DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_reconcile_rss.py -v
      Expected: new 3 pass + existing ingest_wechat tests no regression + Patch 1's 26 still pass.

    STEP 5 — Commit (verbatim message per spec):
      git add ingest_wechat.py tests/unit/test_ingest_402_degrade.py
      git commit -m "$(cat <<'EOF'
feat(ingest): 402 fallback to text-only ingest (260517-rgd-2)

DeepSeek 402(余额不足)在 entity extraction 中抛出时,article 不再
完全失败。降级路径:body 进 kv_store + degraded_extraction marker。

Article 仍可被 text search 检索;充值后可批量补 entity extraction
(future v1.x throughput patch)。

Closes audit ARCHITECTURE-AUDIT §3 Patch 2 — per-article 失败模式耦合
的合理修复,无需切分进程。

Tests: 3 新增,mock DeepSeek 覆盖 402 路径 + 非-402 propagation +
reconcile visibility。所有现有 ingest_wechat 测试仍 pass。
EOF
)"

      Forward-only commit. Explicit `git add` files. No `--amend`.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -k "ingest_wechat or 402 or degrade" -v && DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_reconcile_rss.py -v</automated>
    Expected: new 3 tests pass + existing ingest_wechat tests no regression + Patch 1's 26 still pass.
    GATE: If any test fails (Patch 2's new 3 OR Patch 1's 26 OR existing ingest_wechat tests),
          STOP. Do not proceed to Task 3 until all green.
  </verify>
  <done>
    - tests/unit/test_ingest_402_degrade.py exists with 3 tests, all pass
    - ingest_wechat.py has _ainsert_with_402_fallback helper called at lines 1118 (cache-hit) and 1380 (main)
    - Helper raises non-402 RuntimeError for caller; degrades silently on 402
    - Degraded sidecar marker mechanism documented in test docstring
    - All existing ingest_wechat tests still pass (no regression)
    - Patch 1's 26 reconcile tests still pass (no cross-patch regression)
    - Commit 260517-rgd-2 in git log with verbatim message from spec
  </done>
</task>

<task type="auto">
  <name>Task 3: Patch 3 — MAX_ARTICLES tri-governor doc + memory closure (260517-rgd-3)</name>
  <files>
    CLAUDE.md,
    ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md,
    ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md
  </files>
  <action>
    STEP 1 — Add MAX_ARTICLES tri-governor section to CLAUDE.md:
      Locate the "Batch Execution" section (currently has "Full batch from scratch", "Resume",
      "Monitor progress" subsections). Insert a new subsection AFTER "Batch Execution" and BEFORE
      "Known Limitations". Section content (executor may adjust phrasing but MUST keep the 3 numbered
      governors intact and reference both SiliconFlow + Vertex sections):

        ### MAX_ARTICLES is a tri-governor

        `MAX_ARTICLES` (default 5 in cron via `cron_daily_ingest.sh 5`) is NOT
        just a throughput cap. It governs THREE concerns simultaneously:

        1. **Throughput cap** — how many articles per cron invocation
        2. **SiliconFlow ¥-budget governor** — at ~¥0.04/article (30 imgs avg ×
           ¥0.0013/img), 5 articles ≈ ¥0.20/cron. Bumping to 50 ≈ ¥2.00/cron.
        3. **Vertex AI embedding RPM governor** — entity-rich articles trigger
           100-300 embedding calls each. 5 articles burst ≈ 500-1500 RPM hits;
           raising the cap risks 429 quota exceed (see v1.0.z scope).

        Bumping `MAX_ARTICLES` without checking all three regresses cost and/or
        quota. Cross-reference: "SiliconFlow Balance Management" + "Vertex AI
        Migration Path" sections above.

    STEP 2 — Verify no test regression with full unit suite:
      DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v 2>&1 | tail -10
      Expected: all pass; pre-existing flaky test_embedding_func_reads_current_key (commit 6c93d67)
      does NOT count as a new failure.

    STEP 3 — Commit Patch 3 (verbatim message per spec):
      git add CLAUDE.md
      git commit -m "$(cat <<'EOF'
docs(claude): MAX_ARTICLES is tri-governor (260517-rgd-3)

明确 MAX_ARTICLES 不只是 throughput cap,而是 throughput + SiliconFlow ¥

+ Vertex AI RPM 三重 governor。未来 ingest 扩量讨论需引用本节。

Closes audit ARCHITECTURE-AUDIT §3 Patch 3。
EOF
)"

    STEP 4 — Closure tasks (post-commit, NOT in the rgd-3 commit):
      Write memory file at:
        ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md
      Mirror project_v1_0_x_closure_260516.md template. Required content:
        - Headline: "v1.0.y closure trio shipped 2026-05-17"
        - Full v1.0.y commit list (resolve actual hashes from git log AFTER all 3 commits land):
            * bd67f06 — kwarg=0 fallback (v1.0.x background context)
            * 4eaef45 — image_count_row refresh from ScrapeResult.images (v1.0.x context)
            * 1b74fc1 — (cite from project_v1_0_x_closure_260516.md if listed; else research)
            * 9c4fc5e — initial --auto-patch (260517-acp, ghost-success)
            * 6c93d67 — embedding 429 self-describing error msg
            * <hash>  — 260517-rgd-1 (Patch 1)
            * <hash>  — 260517-rgd-2 (Patch 2)
            * <hash>  — 260517-rgd-3 (Patch 3)
          Use `git log --oneline -20` to extract the actual short hashes after Patch 3 commit.
        - Audit decision context: cite ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md §3, summarize
          why the 5-day rewrite was rejected and 3 surgical patches chosen instead.
        - "Out of scope deferred to v1.0.z or later":
            * Vertex AI 429 research (separate quick)
            * 4-worker rewrite (audit rejected)
            * Reconcile schema migration (no new columns)
            * MAX_ARTICLES default value change (only documented, not raised)
        - "Hermes deployment status": filled in by SUMMARY.md template (see STEP 6).

      Append 1 link line to ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md:
        - [v1.0.y closure trio 2026-05-17](project_v1_0_y_closure_260517.md) — 3 surgical patches
          (bidirectional reconcile + 402 graceful degrade + MAX_ARTICLES tri-governor doc) shipped
          per audit recommendation; rejected 5-day rewrite alternative.

      DO NOT update .planning/ROADMAP.md or .planning/STATE-kb-databricks-v1.md — this is v1.0.y
      maintenance, not a phase milestone (per spec constraint).

      DO NOT commit the memory file changes — memory files live in ~/.claude/ and are user-private,
      not in this repo.

    STEP 5 — Output the Hermes deployment prompt template at end of SUMMARY.md so user can relay it.
      Append a section "## Hermes Deployment Prompt" to SUMMARY.md with content like:

        ```
        Hermes deployment for OmniGraph-Vault v1.0.y closure trio (commits 260517-rgd-1/2/3).

        Steps:
        1. cd ~/OmniGraph-Vault && git pull --ff-only
        2. Verify the 3 commits are present:
             git log --oneline -5
           Expected: 260517-rgd-3, 260517-rgd-2, 260517-rgd-1 in last few entries.
        3. Run the unit suite to sanity-check the deploy:
             source venv/bin/activate
             DEEPSEEK_API_KEY=dummy pytest tests/unit/test_reconcile_rss.py -v
             DEEPSEEK_API_KEY=dummy pytest tests/unit/test_ingest_402_degrade.py -v
           Expected: 26 pass + 3 pass.
        4. (Optional, no behavior change required) Add --auto-patch flag to next reconcile cron:
             scripts/reconcile_ingestions.py --auto-patch ...
           This now flips BOTH directions automatically. Without --auto-patch, behavior is
           unchanged (back-compat).
        5. No service restart needed — these are pure code-path additions; daily_ingest cron
           picks up the new 402 fallback on next invocation.

        Report back:
        - git log -5 output
        - pytest summary lines (26 passed / 3 passed)
        - Any deploy-time errors
        ```

  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v 2>&1 | tail -10</automated>
    Expected: full unit suite passes (or only pre-existing flaky test_embedding_func_reads_current_key
    fails — that's a known fixture-pollution issue per commit 6c93d67, NOT a regression).
  </verify>
  <done>
    - CLAUDE.md has new "MAX_ARTICLES is a tri-governor" section between "Batch Execution" and
      "Known Limitations"
    - Section enumerates 3 governors: throughput, SiliconFlow ¥, Vertex RPM
    - Section cross-references "SiliconFlow Balance Management" and "Vertex AI Migration Path"
    - Commit 260517-rgd-3 in git log with verbatim message
    - Memory file project_v1_0_y_closure_260517.md created with full v1.0.y commit list + audit
      decision context + scope-deferred items
    - MEMORY.md has new index line linking to the closure memory
    - ROADMAP.md and STATE-kb-databricks-v1.md UNTOUCHED (v1.0.y is maintenance, not phase work)
    - Hermes deployment prompt template appears at end of SUMMARY.md
    - Full unit suite passes (no NEW failures beyond pre-existing flaky)
  </done>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. git log --oneline -5 shows the 3 atomic commits in order:
     <hash> docs(claude): MAX_ARTICLES is tri-governor (260517-rgd-3)
     <hash> feat(ingest): 402 fallback to text-only ingest (260517-rgd-2)
     <hash> feat(reconcile): bidirectional ghost-failure detection (260517-rgd-1)

2. Test gate confirmation (run after Task 3):
     DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_reconcile_rss.py tests/unit/test_ingest_402_degrade.py -v
     Expected: 26 + 3 = 29 reconcile + 402-degrade tests pass.

3. Full suite (sanity):
     DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v 2>&1 | tail -10
     Expected: ALL pass except pre-existing flaky test_embedding_func_reads_current_key (per commit 6c93d67).

4. CLAUDE.md grep:
     grep -A2 "MAX_ARTICLES is a tri-governor" CLAUDE.md
     Expected: section header + first numbered governor visible.

5. Memory file exists:
     test -f ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md
     grep -c "260517-rgd" ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md
     Expected: ≥3 mentions.

6. MEMORY.md updated:
     grep "project_v1_0_y_closure_260517.md" ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md
     Expected: 1 link line found.

7. SUMMARY.md has Hermes deployment prompt:
     grep -A1 "Hermes Deployment Prompt" SUMMARY.md  (in the quick directory)
     Expected: section header + first content line.
</verification>

<success_criteria>

- 3 commits land atomically with verbatim messages from spec (260517-rgd-1, -2, -3)
- 3 + 26 = 29 patch-related tests pass; full unit suite has no NEW failures
- CLAUDE.md documents MAX_ARTICLES as tri-governor with cross-references
- Memory file project_v1_0_y_closure_260517.md exists with full v1.0.y commit list + audit context
- MEMORY.md index updated with link line
- ROADMAP.md and STATE-kb-databricks-v1.md UNCHANGED (maintenance, not phase work)
- SUMMARY.md ends with Hermes deployment prompt template the user can relay
- Local test gates honored: STOP between patches if tests fail
- No `git add -A` (explicit files only); no `git commit --amend` (forward-only)
- No literal secrets in any file (per CLAUDE.md feedback rule)
- No SSH commands handed to user (per CLAUDE.md PRINCIPLE #5)
</success_criteria>

<output>
After completion, create `.planning/quick/260517-riq-260517-rgd-v1-0-y-closure-trio-bidirecti/260517-riq-SUMMARY.md`
following the standard summary template, with an additional final section "## Hermes Deployment Prompt"
containing the deployment prompt template from Task 3 STEP 5 (so the user can paste it directly to Hermes).
</output>
</content>
</invoke>