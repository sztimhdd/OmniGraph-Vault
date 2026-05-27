---
phase: kdb-1.5-lightrag-databricks-provider-adapter
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - databricks-deploy/startup_adapter.py
  - databricks-deploy/tests/__init__.py
  - databricks-deploy/tests/conftest.py
  - databricks-deploy/tests/test_startup_adapter.py
  - databricks-deploy/CONFIG-EXEMPTIONS.md
  - databricks-deploy/requirements.txt
  - .planning/STATE-kb-databricks-v1.md
autonomous: true
requirements:
  - STORAGE-DBX-05
priority: P0
estimated_loc: 280
estimated_time: 2h
skills_required:
  - python-patterns
  - writing-tests

must_haves:
  truths:
    - "Adapter copies /Volumes/.../lightrag_storage/ to /tmp/omnigraph_vault/lightrag_storage/ idempotently"
    - "Adapter handles empty-source case (pre-kdb-2.5 first deploy) without raising"
    - "Adapter logs copy-elapsed-time + bytes for kdb-2 cold-start calibration"
    - "kol_scan.db stays on Volume (NOT copied to /tmp), opened via existing ?mode=ro pattern"
    - "STATE-kb-databricks-v1.md reflects kdb-1.5 phase progress per 2-forward-commit pattern"
  artifacts:
    - path: "databricks-deploy/startup_adapter.py"
      provides: "hydrate_lightrag_storage_from_volume() function — STORAGE-DBX-05 alt path"
      exports: ["hydrate_lightrag_storage_from_volume", "CopyResult", "VOLUME_ROOT", "TMP_ROOT"]
      min_lines: 80
    - path: "databricks-deploy/tests/test_startup_adapter.py"
      provides: "Idempotency + copy-correctness + empty-source unit tests"
      min_lines: 100
    - path: "databricks-deploy/CONFIG-EXEMPTIONS.md"
      provides: "Records that this phase modifies NO files under kb/ or lib/ — initial empty exemption list (kdb-2 will populate)"
      min_lines: 20
    - path: "databricks-deploy/requirements.txt"
      provides: "Pins databricks-sdk for adapter + factory"
      contains: "databricks-sdk"
  key_links:
    - from: "databricks-deploy/startup_adapter.py"
      to: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/lightrag_storage"
      via: "shutil.copytree (FUSE primary) or w.files.download_directory (SDK fallback)"
      pattern: "shutil\\.copytree|files\\.download_directory"
    - from: "databricks-deploy/startup_adapter.py"
      to: "/tmp/omnigraph_vault/lightrag_storage"
      via: "Path(TMP_ROOT) / 'lightrag_storage'"
      pattern: "/tmp/omnigraph_vault"
    - from: "databricks-deploy/tests/test_startup_adapter.py"
      to: "databricks-deploy/startup_adapter.py"
      via: "import + pytest invocations"
      pattern: "from startup_adapter import|from databricks_deploy.startup_adapter"
---

<objective>
Implement the kdb-1.5 storage adapter — `hydrate_lightrag_storage_from_volume()` — that copies the read-only UC Volume `lightrag_storage/` payload into App-local `/tmp/` so LightRAG's mandatory `os.makedirs(workspace_dir, exist_ok=True)` succeeds at App startup. This satisfies STORAGE-DBX-05 via the alternative copy-to-/tmp path (the FUSE-direct approach is broken by `READ_VOLUME`-only grant per AUTH-DBX-03).

Purpose: Defends against the documentary-inferred SPIKE-DBX-01b failure (`os.makedirs` raises `OSError [Errno 30] Read-only file system` on FUSE-mounted UC Volume). Logs copy-elapsed-time + bytes so kdb-2 first deploy has data to calibrate cold-start budget.

Output:
- `databricks-deploy/startup_adapter.py` (idempotent, FUSE-primary + SDK-fallback, structured logging)
- `databricks-deploy/tests/test_startup_adapter.py` (unit tests using tmp_path; mocks for SDK fallback)
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (initial empty exemption list — kdb-2 will populate when it adds `lib/llm_complete.py` + `kg_synthesize.py`)
- `databricks-deploy/requirements.txt` (pins databricks-sdk)
- `.planning/STATE-kb-databricks-v1.md` updated to reflect kdb-1.5 progress (2-forward-commit pattern: this is the FORWARD commit; hash backfill happens in plan 02 STATE update or executor's follow-up)

## Deferred to kdb-2

**ROADMAP-kb-databricks-v1.md rev 3 line 74 success criterion #4** ("`app.yaml` updated to invoke storage adapter via wrapper shell or pre-uvicorn step") is **explicitly deferred to kdb-2 phase (DEPLOY-DBX-04)** — NOT delivered in kdb-1.5. Rationale:

1. **Single owner for `app.yaml`**: kdb-2 DEPLOY-DBX-04 (ROADMAP line 99) and LLM-DBX-05 (REQUIREMENTS lines 47-50) own ALL `app.yaml` env values + `command:` line end-to-end. Splitting `app.yaml` authoring across kdb-1.5 + kdb-2 risks merge-conflict / drift.
2. **Cannot test in isolation here**: validating wired-`app.yaml` requires deploying an App, which is squarely kdb-2 scope (DEPLOY-DBX-01..09).
3. **The kdb-1.5 deliverable is the adapter MODULE**: wiring is a 1-line invocation contract that kdb-2 first-deploy adds to the `command:` field along with the 4 required literal env vars (`OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` + 3 LLM vars).
4. **RESEARCH Decision 2 reference to `OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault in app.yaml`** is about library naming convention, not phase ownership — kdb-2 still authors the literal env line.

This deferral MUST be recorded explicitly in `kdb-1.5-VERIFICATION.md` (Plan 01's STATE/CONFIG-EXEMPTIONS task — see Task 1.3) listing ROADMAP success criterion #4 as "intentionally deferred to kdb-2 DEPLOY-DBX-04, see ROADMAP line 99".
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-kb-databricks-v1.md
@.planning/REQUIREMENTS-kb-databricks-v1.md
@.planning/ROADMAP-kb-databricks-v1.md
@.planning/STATE-kb-databricks-v1.md
@.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md
@.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-WAVE2-FINDINGS.md
@.planning/phases/kdb-1-uc-volume-and-data-snapshot/kdb-1-SPIKE-FINDINGS.md

<interfaces>
<!-- Concrete contracts the adapter must satisfy. Verbatim from RESEARCH.md Decision 1 + Decision 2. -->

VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
TMP_ROOT = "/tmp/omnigraph_vault"

Source: VOLUME_ROOT + "/lightrag_storage"  (read-only, may be empty pre-kdb-2.5)
Dest:   TMP_ROOT + "/lightrag_storage"     (writable, query-time cache lives here)

Files to copy (post-kdb-2.5 — measured against Hermes prod 2026-05-15):
  - vdb_chunks.json, vdb_entities.json, vdb_relationships.json (1024-dim, ~400 MB total post-Qwen3)
  - graph_chunk_entity_relation.graphml
  - kv_store_full_docs.json, kv_store_text_chunks.json,
    kv_store_full_entities.json, kv_store_full_relations.json,
    kv_store_entity_chunks.json, kv_store_relation_chunks.json,
    kv_store_doc_status.json
  - kv_store_llm_response_cache.json (may not exist on first copy; query-time-created)

Existing read-only DB pattern (DO NOT MODIFY — kb/ exemption list does not include this file):
  kb/data/article_query.py:140-143 — uses `?mode=ro` URI; works on FUSE without copy.

Hermes DB journal_mode = 'delete' (NOT WAL); confirmed via SSH 2026-05-15.

API shape — CopyResult dataclass (frozen):
  status: str               # one of: "copied", "skipped"
  reason: str | None        # populated when status == "skipped"
  method: str | None        # one of: "fuse", "sdk", None when skipped
  elapsed_s: float | None   # populated when status == "copied"
  bytes_copied: int | None  # populated when status == "copied"
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1.1: Invoke python-patterns Skill for adapter design</name>
  <read_first>
    - .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md (Decision 1, Decision 2, Pitfall 5 sections)
    - C:\Users\huxxha\.claude\skills\python-patterns\SKILL.md
  </read_first>
  <action>
    Invoke the python-patterns Skill explicitly with the adapter-specific args. Emit the literal tool call:

    Skill(skill="python-patterns", args="Design databricks-deploy/startup_adapter.py per RESEARCH.md Decision 1 + Decision 2. Requirements: (1) Define a frozen @dataclass CopyResult with fields status: str, reason: str | None, method: str | None, elapsed_s: float | None, bytes_copied: int | None. (2) Define module-level constants VOLUME_ROOT='/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault' and TMP_ROOT='/tmp/omnigraph_vault'. (3) Define hydrate_lightrag_storage_from_volume() -> CopyResult that copies VOLUME_ROOT/lightrag_storage to TMP_ROOT/lightrag_storage idempotently. (4) Idiomatic Python 3.11+ — pathlib.Path, type hints on all public callables, structured logging via the standard logging module (NOT print). (5) FUSE primary via shutil.copytree(src, dst, dirs_exist_ok=True), SDK fallback via WorkspaceClient().files.download_directory() (lazy import inside the fallback branch to avoid hard dependency at import time). (6) Idempotency: if dst exists and is non-empty, return CopyResult(status='skipped', reason='already_hydrated') WITHOUT raising. (7) Empty-source case: if src exists but is empty (pre-kdb-2.5 deploy), return CopyResult(status='skipped', reason='source_empty_pre_seed'). (8) Defensive top-of-file check: if not os.access('/tmp', os.W_OK): raise RuntimeError per RESEARCH.md Risk 5. (9) Compute bytes_copied via sum of stat().st_size for all files in dst after copy. Output the recommended file structure as a code skeleton I can implement against in Task 1.2.")

    Capture the Skill output and use it as the design baseline for Task 1.2. The Skill output MUST be referenced verbatim in the SUMMARY.md commit body (literal substring "Skill(skill=\"python-patterns\")" must appear).
  </action>
  <verify>
    <automated>grep -c 'Skill(skill="python-patterns")' .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-01-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - Skill tool call literally invoked (NOT just referenced in <read_first>)
    - Skill output captured and informs Task 1.2 implementation
    - Substring `Skill(skill="python-patterns")` appears in eventual SUMMARY.md (verified at commit time)
  </acceptance_criteria>
  <done>Skill invoked; design skeleton captured for Task 1.2.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 1.2: Invoke writing-tests Skill, then write startup_adapter.py + unit tests (RED → GREEN)</name>
  <read_first>
    - .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md (Decision 1 sketch lines 320-368, Pitfall 5 lines 437-443, Risk 5 lines 437-443)
    - C:\Users\huxxha\.claude\skills\writing-tests\SKILL.md
    - kb/data/article_query.py (existing ?mode=ro pattern — DO NOT modify, just understand)
    - venv/Lib/site-packages/lightrag/kg/json_kv_impl.py (lines 30-39 — the os.makedirs that this adapter defends against)
  </read_first>
  <behavior>
    Test 1 — `test_hydrate_skipped_when_source_empty`:
      - tmp_path acts as VOLUME_ROOT (monkeypatched); create lightrag_storage/ subdir but leave it empty
      - Call hydrate_lightrag_storage_from_volume() — assert returns CopyResult(status='skipped', reason='source_empty_pre_seed', method=None)
      - Assert TMP_ROOT/lightrag_storage exists (mkdir parents=True, exist_ok=True succeeded)
      - Assert no files inside dst

    Test 2 — `test_hydrate_copies_via_fuse_when_source_populated`:
      - tmp_path source contains 3 fake files: vdb_chunks.json (1KB), graph_chunk_entity_relation.graphml (2KB), kv_store_full_docs.json (3KB)
      - Call hydrate — assert returns CopyResult(status='copied', method='fuse', elapsed_s > 0, bytes_copied == 6144)
      - Assert dst contains all 3 files with byte-identical content

    Test 3 — `test_hydrate_idempotent_skip_on_repeat`:
      - First call copies (per Test 2 setup)
      - Second call returns CopyResult(status='skipped', reason='already_hydrated', method=None) — verifies the dst.exists() and any(dst.iterdir()) short-circuit

    Test 4 — `test_hydrate_falls_back_to_sdk_when_fuse_unavailable`:
      - Monkeypatch os.path.ismount to return False
      - Monkeypatch the source path to NOT exist locally (simulates "no FUSE mount")
      - Mock WorkspaceClient.files.download_directory to write 1 fake file to dst
      - Assert returns CopyResult(status='copied', method='sdk', ...)

    Test 5 — `test_raises_when_tmp_not_writable`:
      - Monkeypatch os.access('/tmp', os.W_OK) to False
      - Assert hydrate_lightrag_storage_from_volume() raises RuntimeError with clear message
  </behavior>
  <action>
    Step 0 (Skill invocation — REQUIRED before writing any test code):

    Invoke the writing-tests Skill explicitly with concrete args. Emit the literal tool call:

    Skill(skill="writing-tests", args="Design 5 unit tests for databricks-deploy/startup_adapter.py::hydrate_lightrag_storage_from_volume() covering: (1) idempotency on second call — first call copies, second short-circuits via dst.exists() + any(dst.iterdir()) returning CopyResult(status='skipped', reason='already_hydrated'); (2) empty-source no-op — src exists but iterdir is empty, returns CopyResult(status='skipped', reason='source_empty_pre_seed') without writing to dst; (3) shutil.copytree FUSE-primary path — src non-empty + os.path.ismount True, asserts CopyResult(status='copied', method='fuse', bytes_copied matches sum of fixture sizes); (4) SDK download_directory fallback — monkeypatch os.path.ismount False, mock WorkspaceClient.files.download_directory, assert CopyResult(status='copied', method='sdk'); (5) /tmp not writable defensive raise — monkeypatch os.access('/tmp', os.W_OK) to False, assert RuntimeError. Use pytest fixtures: monkeypatch (for VOLUME_ROOT / TMP_ROOT / os.access / os.path.ismount), tmp_path for synthetic source/dest, unittest.mock.MagicMock for SDK without installing databricks-sdk. Tests must follow the Testing Trophy: these are unit tests with monkeypatched filesystem boundaries — NOT integration. Output the full test file structure with imports + fixture defs + 5 test functions.")

    The Skill output MUST be referenced verbatim in the eventual SUMMARY.md commit body (literal substring `Skill(skill="writing-tests")` must appear).

    Then implement RED-first:

    Step 1 (RED): Write databricks-deploy/tests/test_startup_adapter.py implementing all 5 tests above. Use pytest fixtures: monkeypatch (for VOLUME_ROOT / TMP_ROOT / os.access / os.path.ismount), tmp_path (for synthetic source/dest). Mock the SDK via unittest.mock.MagicMock — do NOT install or import databricks-sdk in the test (lazy-import in adapter means tests don't need it).

    Step 2 (RED): Run `pytest databricks-deploy/tests/test_startup_adapter.py -v` — must fail (module doesn't exist).

    Step 3 (GREEN): Write databricks-deploy/startup_adapter.py implementing the design from Task 1.1. Concrete shape:

    ```python
    """Startup storage adapter for Databricks Apps.

    Copies /Volumes/.../lightrag_storage to /tmp/ so LightRAG's mandatory
    os.makedirs(workspace_dir, exist_ok=True) at storage init time does not
    raise OSError [Errno 30] on the read-only UC Volume FUSE mount.

    See .planning/phases/kdb-1.5-.../kdb-1.5-RESEARCH.md Decision 1 for rationale.
    """
    from __future__ import annotations

    import logging
    import os
    import shutil
    import time
    from dataclasses import dataclass
    from pathlib import Path

    logger = logging.getLogger(__name__)

    VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
    TMP_ROOT = "/tmp/omnigraph_vault"
    LIGHTRAG_SUBDIR = "lightrag_storage"


    @dataclass(frozen=True)
    class CopyResult:
        status: str
        reason: str | None = None
        method: str | None = None
        elapsed_s: float | None = None
        bytes_copied: int | None = None


    def _bytes_in_dir(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


    def hydrate_lightrag_storage_from_volume(
        volume_root: str = VOLUME_ROOT,
        tmp_root: str = TMP_ROOT,
    ) -> CopyResult:
        """Copy lightrag_storage from Volume to /tmp. Idempotent."""
        if not os.access("/tmp", os.W_OK):
            raise RuntimeError("/tmp is not writable; adapter cannot proceed")

        src = Path(volume_root) / LIGHTRAG_SUBDIR
        dst = Path(tmp_root) / LIGHTRAG_SUBDIR

        # Idempotency check
        if dst.exists() and any(dst.iterdir()):
            logger.info("startup_adapter: skip already_hydrated dst=%s", dst)
            return CopyResult(status="skipped", reason="already_hydrated")

        dst.mkdir(parents=True, exist_ok=True)

        # FUSE primary path
        if (os.path.ismount(volume_root) or src.exists()):
            if not src.exists() or not any(src.iterdir()):
                logger.info("startup_adapter: skip source_empty_pre_seed src=%s", src)
                return CopyResult(status="skipped", reason="source_empty_pre_seed")
            t0 = time.time()
            shutil.copytree(src, dst, dirs_exist_ok=True)
            elapsed = time.time() - t0
            n_bytes = _bytes_in_dir(dst)
            logger.info(
                "startup_adapter: copied via fuse elapsed_s=%.3f bytes=%d",
                elapsed, n_bytes,
            )
            return CopyResult(
                status="copied", method="fuse",
                elapsed_s=elapsed, bytes_copied=n_bytes,
            )

        # SDK fallback path (lazy import keeps tests independent of databricks-sdk install)
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        t0 = time.time()
        w.files.download_directory(str(src), str(dst), overwrite=True)
        elapsed = time.time() - t0
        n_bytes = _bytes_in_dir(dst)
        logger.info(
            "startup_adapter: copied via sdk elapsed_s=%.3f bytes=%d",
            elapsed, n_bytes,
        )
        return CopyResult(
            status="copied", method="sdk",
            elapsed_s=elapsed, bytes_copied=n_bytes,
        )
    ```

    Step 4 (GREEN verify): Run `pytest databricks-deploy/tests/test_startup_adapter.py -v` — all 5 tests must PASS.

    Step 5 (REFACTOR): Inspect adapter for clarity; ensure no print(), all logs go through `logger`. Type hints on all public callables. No dead code.

    Also create:
    - `databricks-deploy/tests/__init__.py` (empty)
    - `databricks-deploy/tests/conftest.py` (containing a `tmp_volume_root` fixture that returns tmp_path / "vol" with sub-dir lightrag_storage created — used by tests above)

    Do NOT install databricks-sdk in this task (Plan 02 handles requirements.txt + install). The lazy-import keeps tests independent.
  </action>
  <verify>
    <automated>pytest databricks-deploy/tests/test_startup_adapter.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Skill(skill="writing-tests") literally invoked as a tool call (NOT just listed in <read_first>); literal substring will appear in SUMMARY.md
    - File `databricks-deploy/startup_adapter.py` exists with `hydrate_lightrag_storage_from_volume` exported
    - File contains literal substring `VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"`
    - File contains literal substring `TMP_ROOT = "/tmp/omnigraph_vault"`
    - File contains `@dataclass(frozen=True)` decorator
    - File contains `from databricks.sdk import WorkspaceClient` inside a function body (lazy import — verify by `grep -n "from databricks.sdk" databricks-deploy/startup_adapter.py` shows the line is indented, not at module top)
    - All 5 tests pass: `pytest databricks-deploy/tests/test_startup_adapter.py -v` shows `5 passed`
    - No `print(` statements in startup_adapter.py: `grep -c "print(" databricks-deploy/startup_adapter.py` returns 0
    - Logger used: `grep -c "logger\." databricks-deploy/startup_adapter.py` returns >= 3
  </acceptance_criteria>
  <done>Both Skills (python-patterns from Task 1.1, writing-tests from this task) invoked; adapter implemented; all 5 tests green; no regressions in existing test suite (`pytest -q` does not break — adapter is new code under databricks-deploy/, so existing tests untouched).</done>
</task>

<task type="auto">
  <name>Task 1.3: Write CONFIG-EXEMPTIONS.md + requirements.txt + STATE update + record app.yaml deferral</name>
  <read_first>
    - .planning/STATE-kb-databricks-v1.md (current rev 3 content; 2-forward-commit pattern at lines 136-138)
    - .planning/REQUIREMENTS-kb-databricks-v1.md (CONFIG-DBX-01 section lines 100-110, CONFIG-DBX-02 lines 111)
    - .planning/ROADMAP-kb-databricks-v1.md (Phase kdb-1.5 spec lines 60-78; success criterion #4 line 74; kdb-2 DEPLOY-DBX-04 line 99)
  </read_first>
  <action>
    Write three files PLUS one VERIFICATION.md note.

    File 1 — `databricks-deploy/CONFIG-EXEMPTIONS.md` (concrete content):

    ```markdown
    # CONFIG-EXEMPTIONS — kb-databricks-v1

    > Initial empty exemption ledger. Created in kdb-1.5; populated in kdb-2 when LLM-DBX-01 + LLM-DBX-02 modify `lib/llm_complete.py` and `kg_synthesize.py`.

    ## Allowed kb/ + lib/ + top-level *.py edits in this milestone

    Per REQUIREMENTS-kb-databricks-v1.md rev 3 constraint #5 ("zero kb/ edits" relaxed):

    | File | REQ | Phase | Status |
    |------|-----|-------|--------|
    | `lib/llm_complete.py` | LLM-DBX-01 | kdb-2 | NOT YET MODIFIED |
    | `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | NOT YET MODIFIED |

    ## Verification command (run at kdb-3 close per CONFIG-DBX-01)

    ```bash
    git log <milestone-base>..HEAD --grep '(kdb-' --name-only -- \
      kb/ \
      lib/ \
      | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' \
      | sort -u
    ```

    Returns empty when CONFIG-DBX-01 is satisfied. `<milestone-base>` is `cfe47b4` per STATE-kb-databricks-v1.md.

    ## Phase kdb-1.5 contribution

    Phase kdb-1.5 modifies ZERO files under `kb/`, `lib/`, or top-level `*.py`. All deliverables are NEW files under `databricks-deploy/`. CONFIG-DBX-01 verification for this phase's commits MUST return empty.
    ```

    File 2 — `databricks-deploy/requirements.txt` (concrete content):

    ```
    # databricks-deploy runtime + dry-run dependencies (pinned).
    # Authored in kdb-1.5; consumed by kdb-2 first deploy + kdb-2.5 re-index Job.
    databricks-sdk>=0.30.0
    lightrag-hku==1.4.15
    numpy>=1.26.0
    fastapi>=0.115.0
    uvicorn>=0.30.0
    jinja2>=3.1.0
    markdown>=3.6
    pygments>=2.18.0
    ```

    File 3 — Update `.planning/STATE-kb-databricks-v1.md`:

    Edit existing file. Modify the "## Current Position" block to:

    ```markdown
    ## Current Position

    - **Milestone:** kb-databricks-v1 (parallel track)
    - **Phase:** kdb-1.5 — LightRAG-Databricks Provider Adapter (in flight)
    - **Plan:** kdb-1.5-01 (storage adapter — STORAGE-DBX-05) + kdb-1.5-02 (factory file + dry-run e2e — LLM-DBX-03), running parallel in Wave 1
    - **Status:** kdb-1.5 plans authored; storage adapter shipped (this commit); factory file + dry-run e2e in flight (plan 02)
    - **Last activity:** 2026-05-15 — kdb-1.5 storage adapter `databricks-deploy/startup_adapter.py` shipped + 5 unit tests green; CONFIG-EXEMPTIONS.md initial-empty ledger created; requirements.txt pinned databricks-sdk
    ```

    Also update "## Next Step" to:

    ```markdown
    ## Next Step

    Execute kdb-1.5 plan 02 (factory file + dry-run e2e against REAL Model Serving). After both plans land + 2-forward STATE backfill: proceed to kdb-2 (Databricks App Deploy).
    ```

    Do NOT touch any other section of STATE.md (locked decisions, milestone-base hash, accumulated context all stay).

    File 4 — Create / append to `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-VERIFICATION.md` with an explicit deferral note (this file may not yet exist; create it with this section, OR append if it does):

    ```markdown
    ## Phase kdb-1.5 ROADMAP success criteria

    | # | Criterion | Status |
    |---|-----------|--------|
    | 1 | `databricks-deploy/startup_adapter.py` implements copy-on-startup pattern, idempotent across restarts | ✅ Plan 01 (this PLAN) |
    | 2 | `databricks-deploy/lightrag_databricks_provider.py` instantiated against MosaicAI in dry-run e2e (5 articles, ainsert + aquery, embedding_dim=1024 verified) | ✅ Plan 02 |
    | 3 | Adapter integration documented in `kdb-1.5-VERIFICATION.md` | ✅ This file |
    | 4 | `app.yaml` updated to invoke storage adapter via wrapper shell or pre-uvicorn step | ⚠️ **Intentionally deferred to kdb-2 DEPLOY-DBX-04 (ROADMAP line 99)**. Rationale: kdb-2 owns `app.yaml` end-to-end; splitting authoring across phases risks merge-drift. Adapter MODULE shipped here; wiring is a 1-line `command:` invocation kdb-2 first-deploy adds alongside the 4 required literal env vars (`OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` + 3 LLM vars per LLM-DBX-05). |
    ```

    Per `feedback_no_amend_in_concurrent_quicks.md`: this is a forward-only commit. NO `git commit --amend`, NO `git reset`, NO `git add -A`. Stage explicit files only.
  </action>
  <verify>
    <automated>test -f databricks-deploy/CONFIG-EXEMPTIONS.md && test -f databricks-deploy/requirements.txt && grep -q "kdb-1.5" .planning/STATE-kb-databricks-v1.md && grep -q "databricks-sdk>=0.30.0" databricks-deploy/requirements.txt && grep -q "Initial empty exemption ledger" databricks-deploy/CONFIG-EXEMPTIONS.md && grep -q "Intentionally deferred to kdb-2 DEPLOY-DBX-04" .planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-VERIFICATION.md</automated>
  </verify>
  <acceptance_criteria>
    - File `databricks-deploy/CONFIG-EXEMPTIONS.md` exists; contains "NOT YET MODIFIED" for both lib/llm_complete.py and kg_synthesize.py
    - File `databricks-deploy/requirements.txt` exists; contains literal `databricks-sdk>=0.30.0` and `lightrag-hku==1.4.15`
    - `.planning/STATE-kb-databricks-v1.md` "## Current Position" block updated to reference kdb-1.5; locked decisions table at lines 39-50 unchanged; milestone-base hash at line 17 unchanged (`cfe47b4`)
    - No other STATE.md sections modified: `git diff .planning/STATE-kb-databricks-v1.md` should show changes confined to ## Current Position + ## Next Step blocks
    - `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-VERIFICATION.md` exists with explicit deferral entry for ROADMAP success criterion #4 referencing "kdb-2 DEPLOY-DBX-04"
  </acceptance_criteria>
  <done>4 files written/updated; STATE reflects kdb-1.5 progress; app.yaml deferral to kdb-2 explicitly recorded in VERIFICATION.md; no scope creep into other STATE sections.</done>
</task>

</tasks>

<verification>
Phase-level verification anchors (this plan's contribution):

1. `databricks-deploy/startup_adapter.py` exists, importable, 5 unit tests green
2. `databricks-deploy/tests/test_startup_adapter.py` covers idempotency + empty-source + FUSE-copy + SDK-fallback + tmp-not-writable
3. `databricks-deploy/CONFIG-EXEMPTIONS.md` initial-empty ledger created
4. `databricks-deploy/requirements.txt` pins `databricks-sdk>=0.30.0`
5. `.planning/STATE-kb-databricks-v1.md` reflects kdb-1.5 in flight (## Current Position + ## Next Step)
6. `.planning/phases/kdb-1.5-.../kdb-1.5-VERIFICATION.md` records ROADMAP success criterion #4 (`app.yaml` wiring) as explicitly deferred to kdb-2 DEPLOY-DBX-04
7. CONFIG-DBX-01 verification: `git log cfe47b4..HEAD --name-only -- kb/ lib/` returns empty for this plan's commits (we touch nothing under kb/ or lib/)
8. Skill discipline: 2 literal Skill invocations in SUMMARY.md (`Skill(skill="python-patterns")` from Task 1.1 + `Skill(skill="writing-tests")` from Task 1.2)
</verification>

<success_criteria>
- All 5 unit tests pass: `pytest databricks-deploy/tests/test_startup_adapter.py -v` → `5 passed`
- File presence: `ls databricks-deploy/{startup_adapter.py,CONFIG-EXEMPTIONS.md,requirements.txt}` returns all three
- Frontmatter requirement (STORAGE-DBX-05) maps to deliverable: adapter implements alt-path copy mechanism
- Skill discipline: BOTH `Skill(skill="python-patterns")` AND `Skill(skill="writing-tests")` literal substrings in SUMMARY.md (matches trimmed `skills_required: [python-patterns, writing-tests]` in frontmatter)
- ROADMAP success criterion #4 deferral recorded in VERIFICATION.md (NOT silently dropped)
- Forward-only commit: `git log -1` shows new commit (NOT amended); `git reflog` shows no `--amend` operations on this plan's branch
- No regressions: existing project test suite (`pytest -q`) unaffected (no kb/, lib/, top-level *.py touched)
</success_criteria>

<output>
After completion, create `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-01-SUMMARY.md` containing:
- What shipped (4 files + STATE update + VERIFICATION.md deferral note)
- Test counts (5/5 green)
- Skill invocations made: BOTH literal `Skill(skill="python-patterns")` AND `Skill(skill="writing-tests")` substrings (matches trimmed frontmatter)
- Commit hash(es) for plan 02 STATE backfill to reference
- Any deviations from RESEARCH.md (should be NONE — research was high-confidence)
- Note that ROADMAP success criterion #4 (`app.yaml` wiring) is intentionally deferred to kdb-2 DEPLOY-DBX-04 — recorded in VERIFICATION.md
</output>
</output>
