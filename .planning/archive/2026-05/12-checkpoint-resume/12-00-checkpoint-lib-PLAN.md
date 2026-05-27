---
revised: "2026-05-01 — v3.1 closure alignment (commit 2b38e98). Added stage 6 `sub_doc_ingest` to STAGE_FILES + added `list_vision_markers()` helper to public API. Absorbs v3.1 closure Finding 1 (sub-doc lifecycle moves into checkpoint state machine; see 12-CONTEXT.md D-SUBDOC)."
phase: 12-checkpoint-resume
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/checkpoint.py
  - tests/unit/test_checkpoint.py
autonomous: true
requirements:
  - CKPT-01
  - CKPT-02
  - CKPT-04
user_setup: []

must_haves:
  truths:
    - "get_article_hash(url) returns 16-char SHA256 prefix (deterministic)"
    - "Checkpoint directory lives at ~/.hermes/omonigraph-vault/checkpoints/{article_hash}/ (typo preserved)"
    - "All checkpoint file writes are atomic (tmp → rename); crash mid-write leaves no corrupted partial"
    - "has_stage() returns correct bool for each of the 5 stages based on presence of exact filenames"
    - "read_stage()/write_stage() correctly marshal JSON, HTML string, and binary image bytes"
  artifacts:
    - path: "lib/checkpoint.py"
      provides: "Public API: get_article_hash, get_checkpoint_dir, has_stage, read_stage, write_stage, write_metadata, read_metadata, reset_article, reset_all, list_checkpoints, STAGE_FILES"
      contains: "def get_article_hash"
      min_lines: 180
    - path: "tests/unit/test_checkpoint.py"
      provides: "Unit coverage: hash determinism, atomic write semantics (simulated crash), stage detection matrix, metadata upsert, reset idempotency"
      contains: "def test_atomic_write"
      min_lines: 150
  key_links:
    - from: "lib/checkpoint.py::get_checkpoint_dir"
      to: "config.BASE_DIR"
      via: "from config import BASE_DIR"
      pattern: "from config import.*BASE_DIR"
    - from: "lib/checkpoint.py::write_stage"
      to: "atomic write pattern"
      via: "write to .tmp then os.rename"
      pattern: "os\\.rename\\(.*tmp"
---

<objective>
Create the foundation `lib/checkpoint.py` module — the public API consumed by every downstream Phase 12 plan (12-01 CLIs, 12-02 integration, 12-03 batch+tests). Covers CKPT-01 (stage boundaries), CKPT-02 (format), CKPT-04 (atomicity). Ships with comprehensive unit tests.

Purpose: Foundational infrastructure. Every other Phase 12 plan depends on this module. Atomic write semantics + stage detection MUST be provably correct before any integration code is wired.

Output: `lib/checkpoint.py` module + `tests/unit/test_checkpoint.py`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@config.py
@cognee_batch_processor.py
@lib/__init__.py

<interfaces>
<!-- Key types and path constants the executor needs. Do NOT re-read CONTEXT.md; everything needed is here. -->

From config.py:
```python
from pathlib import Path
BASE_DIR: Path  # = Path.home() / ".hermes" / "omonigraph-vault"   (typo canonical)
# Note: "omonigraph" NOT "omnigraph" — per CLAUDE.md Lessons Learned, do NOT rename.
```

From cognee_batch_processor.py (atomic write reference, lines 87-90):
```python
tmp_file = MAP_FILE + ".tmp"
with open(tmp_file, 'w') as f:
    json.dump(canonical_map, f, indent=2, ensure_ascii=False)
os.rename(tmp_file, MAP_FILE)
```

Public API contract for lib/checkpoint.py (MANDATORY signatures):
```python
from pathlib import Path

STAGE_FILES: dict[str, str] = {
    "scrape":         "01_scrape.html",
    "classify":       "02_classify.json",
    "image_download": "03_images/manifest.json",  # presence of manifest = stage complete
    "text_ingest":    "04_text_ingest.done",
    "vision_worker":  "05_vision/",               # directory; per-image success markers (partial OK)
    "sub_doc_ingest": "06_sub_doc_ingest.done",   # NEW 2026-05-01 D-SUBDOC: terminal marker when sub-doc LightRAG ainsert + entity extraction complete
}

def get_article_hash(url: str) -> str: ...
    # return hashlib.sha256(url.encode()).hexdigest()[:16]

def get_checkpoint_dir(article_hash: str) -> Path: ...
    # return BASE_DIR / "checkpoints" / article_hash   (mkdir parents=True, exist_ok=True)

def has_stage(article_hash: str, stage: str) -> bool: ...
    # True iff the stage file (or manifest for image_download) exists.
    # For vision_worker: True iff 05_vision/ dir exists AND contains >=1 *.json file.

def read_stage(article_hash: str, stage: str) -> dict | str | bytes | None: ...
    # scrape → str (HTML text);  classify → dict (parsed JSON);
    # image_download → dict (parsed manifest.json);  text_ingest → True | False (marker);
    # vision_worker → dict[str, dict] (per-image filename → parsed JSON);
    # Returns None if stage absent.

def write_stage(article_hash: str, stage: str, data: dict | str | bytes) -> None: ...
    # Atomic. For image_download pass {"manifest": [...]} (or the list directly; planner picks).
    # For text_ingest data is ignored (marker only).

def write_metadata(article_hash: str, metadata: dict) -> None: ...
    # Atomic upsert of metadata.json. Merge-on-write (read old, update, write new).
    # Required fields written: url, title, created_at, updated_at, last_completed_stage.

def read_metadata(article_hash: str) -> dict: ...
    # Returns {} if absent.

def reset_article(article_hash: str) -> None: ...
    # shutil.rmtree(get_checkpoint_dir(article_hash), ignore_errors=True)

def reset_all() -> None: ...
    # shutil.rmtree(BASE_DIR / "checkpoints", ignore_errors=True)

def list_checkpoints() -> list[dict]: ...
    # For each subdir under BASE_DIR/checkpoints/:
    #   {hash, url, title, last_stage, age_seconds, status: "complete"|"in_flight"}
    # last_stage = highest stage marker present (scrape < classify < image_download < text_ingest < sub_doc_ingest).
    # status = "complete" if sub_doc_ingest marker present, else "in_flight". (Pre-2026-05-01 this used text_ingest; sub_doc_ingest is the new terminal marker per D-SUBDOC.)

def list_vision_markers(article_hash: str) -> list[dict]: ...
    # NEW 2026-05-01 (D-SUBDOC). Reads every 05_vision/*.json file and returns the
    # parsed dicts ordered by filename. Returns [] if 05_vision/ missing or empty.
    # Consumed by Phase 12-02 (ingest_wechat sub_doc_ingest stage) and Phase 13-02
    # (image_pipeline provider usage aggregation).
    # Each dict shape: {"image_id", "provider", "description", "latency_ms", "timestamp"}.
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write unit tests for lib/checkpoint.py (RED phase)</name>
  <files>tests/unit/test_checkpoint.py</files>

  <read_first>
    - .planning/phases/12-checkpoint-resume/12-CONTEXT.md (decisions section, Public API block — already summarized in <interfaces> above; re-read only if ambiguity)
    - cognee_batch_processor.py lines 87-90 (atomic write reference)
    - tests/unit/test_api_keys.py (existing unit test pattern — use its style for fixtures, imports)
  </read_first>

  <behavior>
    Test matrix (write ALL of these as failing tests; implementation comes in Task 2):

    - test_get_article_hash_deterministic: same URL → same 16-char lowercase hex
    - test_get_article_hash_length_16: `len(get_article_hash("https://example.com")) == 16`
    - test_get_article_hash_sha256_not_md5: known vector — `get_article_hash("https://example.com") == "100680ad546ce6a5"` (first 16 chars of SHA256("https://example.com"))
    - test_get_checkpoint_dir_under_base: path startswith BASE_DIR/"checkpoints"; typo `omonigraph` preserved in str(path)
    - test_get_checkpoint_dir_creates_parents: dir exists after call (idempotent)
    - test_write_stage_scrape_atomic: write HTML; assert file exists, no .tmp remains, roundtrip equals input
    - test_write_stage_classify_atomic: write dict → JSON roundtrip matches
    - test_write_stage_image_manifest: write manifest; file is `03_images/manifest.json`; parent dir created
    - test_write_stage_text_ingest_marker: creates empty `04_text_ingest.done` file; no data payload required
    - test_write_stage_atomic_no_partial_on_crash: monkeypatch `os.rename` to raise; assert neither `.tmp` nor final file appear as a committed stage (`has_stage` returns False)
    - test_has_stage_matrix: parametrize over the 5 stages; for each, write the stage file directly and assert `has_stage` returns True; assert False when absent
    - test_has_stage_vision_requires_at_least_one_json: empty `05_vision/` dir → False; dir with `img_0.json` → True
    - test_read_stage_returns_none_if_absent: all 5 stages return None before any write
    - test_read_stage_roundtrip_per_stage: write then read for each of {scrape, classify, image_download, vision_worker}
    - test_write_metadata_upsert: first call writes all fields; second call merges new fields without losing old
    - test_write_metadata_updates_updated_at: updated_at is later after second call
    - test_reset_article_removes_dir: after reset, `has_stage` returns False for every stage; dir gone
    - test_reset_article_idempotent: reset when dir does not exist does not raise
    - test_reset_all_removes_root: creates 2 article dirs; reset_all; both gone
    - test_list_checkpoints_empty: returns []
    - test_list_checkpoints_status_complete_vs_in_flight: one article with text_ingest marker → "complete"; one with only scrape → "in_flight"
    - test_list_checkpoints_includes_url_and_title_from_metadata

    Fixtures:
    - Use `pytest.fixture tmp_checkpoints_base(monkeypatch, tmp_path)`: monkeypatch `lib.checkpoint.BASE_DIR = tmp_path / "omonigraph-vault"` so tests never touch real `~/.hermes/` state.
    - All tests must pass on Windows (use `pathlib.Path`, no `/` string literals for paths).
  </behavior>

  <action>
    Create `tests/unit/test_checkpoint.py`. Import pattern matches other unit tests in the repo:

    ```python
    import json
    import os
    import time
    from pathlib import Path
    import pytest

    from lib import checkpoint as ckpt


    @pytest.fixture(autouse=True)
    def _isolate_base(monkeypatch, tmp_path):
        fake_base = tmp_path / "omonigraph-vault"
        monkeypatch.setattr(ckpt, "BASE_DIR", fake_base)
        yield fake_base
    ```

    Write all test cases listed in `<behavior>`. One assertion per test where possible. For the crash simulation test use `monkeypatch.setattr(os, "rename", <raises>)`. For the SHA256 known vector, compute it once manually and assert the literal:
    ```python
    import hashlib
    assert ckpt.get_article_hash("https://example.com") == \
        hashlib.sha256(b"https://example.com").hexdigest()[:16]
    ```

    Tests MUST all fail at this point (module does not yet export these symbols). Verify with `pytest tests/unit/test_checkpoint.py -v` exit != 0 and failures are all `ImportError` or `AttributeError`.

    Do NOT use `print()` — follow `~/.claude/rules/python/hooks.md`: use `pytest`'s built-in output.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v --collect-only 2>&amp;1 | grep -c "test_" | awk '{exit ($1 &gt;= 20) ? 0 : 1}'</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "^def test_" tests/unit/test_checkpoint.py` returns >= 20
    - `grep -q "def test_get_article_hash_deterministic" tests/unit/test_checkpoint.py`
    - `grep -q "def test_write_stage_atomic_no_partial_on_crash" tests/unit/test_checkpoint.py`
    - `grep -q "def test_has_stage_matrix" tests/unit/test_checkpoint.py`
    - `grep -q "def test_list_checkpoints_status_complete_vs_in_flight" tests/unit/test_checkpoint.py`
    - `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py --collect-only` exits 0 (tests collect without syntax errors)
    - All tests currently FAIL (RED phase confirmed)
  </acceptance_criteria>

  <done>All test cases written and collect cleanly; every test fails with ImportError/AttributeError (module does not exist yet).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement lib/checkpoint.py (GREEN phase)</name>
  <files>lib/checkpoint.py</files>

  <read_first>
    - tests/unit/test_checkpoint.py (the contract — all tests in Task 1 must pass)
    - cognee_batch_processor.py lines 87-90 (atomic write pattern to replicate)
    - lib/__init__.py (Phase 7 package-export convention; decide whether to re-export from `__init__.py` — planner discretion, but keep public API minimal. RECOMMEND: do NOT re-export from `lib/__init__.py` — callers use `from lib.checkpoint import ...` to keep the 13-symbol `lib` surface clean per Phase 7 precedent)
    - config.py (BASE_DIR constant)
  </read_first>

  <action>
    Create `lib/checkpoint.py`. Full module skeleton:

    ```python
    """Phase 12 checkpoint/resume — per-article stage persistence.

    Public API documented in .planning/phases/12-checkpoint-resume/12-CONTEXT.md.
    5 stages: scrape, classify, image_download, text_ingest, vision_worker.

    Atomicity: every write follows the .tmp → os.rename() pattern established by
    cognee_batch_processor.py. A crash mid-write leaves only a .tmp file which is
    invisible to has_stage() — so resume logic is always safe.

    Path: ~/.hermes/omonigraph-vault/checkpoints/{article_hash}/
    (typo "omonigraph" is canonical per CLAUDE.md Lessons Learned — do NOT rename.)
    """
    import hashlib
    import json
    import logging
    import os
    import shutil
    import time
    from pathlib import Path

    from config import BASE_DIR as _CONFIG_BASE_DIR

    logger = logging.getLogger(__name__)

    # Module-level for monkeypatch-friendliness in tests.
    BASE_DIR: Path = _CONFIG_BASE_DIR

    STAGE_FILES: dict[str, str] = {
        "scrape": "01_scrape.html",
        "classify": "02_classify.json",
        "image_download": "03_images/manifest.json",
        "text_ingest": "04_text_ingest.done",
        "vision_worker": "05_vision/",
    }

    _VALID_STAGES = set(STAGE_FILES.keys())


    def _checkpoints_root() -> Path:
        return BASE_DIR / "checkpoints"


    def get_article_hash(url: str) -> str:
        """SHA256 first-16-hex-chars of URL bytes. Deterministic + collision-safe for URL scale."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


    def get_checkpoint_dir(article_hash: str) -> Path:
        """Return {BASE_DIR}/checkpoints/{article_hash}/ — creates parents idempotently."""
        path = _checkpoints_root() / article_hash
        path.mkdir(parents=True, exist_ok=True)
        return path


    def _stage_path(article_hash: str, stage: str) -> Path:
        if stage not in _VALID_STAGES:
            raise ValueError(f"Unknown stage: {stage!r}. Valid: {sorted(_VALID_STAGES)}")
        return get_checkpoint_dir(article_hash) / STAGE_FILES[stage]


    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        """Write bytes via .tmp → os.rename (crash-safe; replicates cognee_batch_processor.py pattern)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.rename(tmp_path, path)


    def _atomic_write_text(path: Path, text: str) -> None:
        _atomic_write_bytes(path, text.encode("utf-8"))


    def _atomic_write_json(path: Path, obj: dict | list) -> None:
        _atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


    def has_stage(article_hash: str, stage: str) -> bool:
        """Return True iff the stage's marker file/dir is present. Crash-safe: ignores .tmp."""
        path = _stage_path(article_hash, stage)
        if stage == "vision_worker":
            # 05_vision/ dir exists AND contains >= 1 committed *.json (ignore *.tmp).
            if not path.is_dir():
                return False
            return any(p.suffix == ".json" for p in path.iterdir())
        return path.exists()


    def read_stage(article_hash: str, stage: str) -> dict | list | str | bool | None:
        """Load committed stage data. Returns None if absent. See <interfaces> block for per-stage types."""
        if not has_stage(article_hash, stage):
            return None
        path = _stage_path(article_hash, stage)
        if stage == "scrape":
            return path.read_text(encoding="utf-8")
        if stage == "classify":
            return json.loads(path.read_text(encoding="utf-8"))
        if stage == "image_download":
            return json.loads(path.read_text(encoding="utf-8"))
        if stage == "text_ingest":
            return True  # marker presence == done
        if stage == "vision_worker":
            # Return {filename: parsed_json} for every committed .json in 05_vision/
            return {
                p.name: json.loads(p.read_text(encoding="utf-8"))
                for p in path.iterdir()
                if p.suffix == ".json"
            }
        raise ValueError(stage)


    def write_stage(article_hash: str, stage: str, data: dict | list | str | bytes | None = None) -> None:
        """Atomic write for a stage. For text_ingest, `data` is ignored (marker only)."""
        path = _stage_path(article_hash, stage)
        if stage == "scrape":
            if not isinstance(data, str):
                raise TypeError("scrape stage expects HTML string")
            _atomic_write_text(path, data)
        elif stage == "classify":
            if not isinstance(data, dict):
                raise TypeError("classify stage expects dict")
            _atomic_write_json(path, data)
        elif stage == "image_download":
            # Accept dict or list — normalize to list for manifest.json.
            manifest = data["manifest"] if isinstance(data, dict) and "manifest" in data else data
            _atomic_write_json(path, manifest)  # type: ignore[arg-type]
        elif stage == "text_ingest":
            # Empty marker file; atomic write of empty bytes.
            _atomic_write_bytes(path, b"")
        elif stage == "vision_worker":
            # vision_worker is per-image; callers should use write_vision_description.
            raise ValueError(
                "vision_worker is per-image; use write_vision_description(hash, image_id, desc) instead"
            )
        else:
            raise ValueError(stage)
        logger.debug("checkpoint stage=%s written for %s", stage, article_hash)


    def write_vision_description(article_hash: str, image_id: str, description: dict) -> None:
        """Per-image Vision result. Path: 05_vision/{image_id}.json. Atomic."""
        target_dir = get_checkpoint_dir(article_hash) / "05_vision"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{image_id}.json"
        _atomic_write_json(path, description)


    _METADATA_FILE = "metadata.json"


    def read_metadata(article_hash: str) -> dict:
        """Return {} if metadata.json absent or unreadable."""
        path = get_checkpoint_dir(article_hash) / _METADATA_FILE
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("metadata.json corrupt for %s: %s; treating as empty", article_hash, e)
            return {}


    def write_metadata(article_hash: str, metadata: dict) -> None:
        """Atomic upsert: merge new fields into existing metadata. Always refreshes updated_at."""
        path = get_checkpoint_dir(article_hash) / _METADATA_FILE
        now = time.time()
        existing = read_metadata(article_hash)
        merged = {**existing, **metadata}
        merged.setdefault("created_at", now)
        merged["updated_at"] = now
        _atomic_write_json(path, merged)


    def reset_article(article_hash: str) -> None:
        """Idempotent removal of one article's checkpoint dir."""
        shutil.rmtree(get_checkpoint_dir(article_hash), ignore_errors=True)


    def reset_all() -> None:
        """Idempotent removal of the entire checkpoints/ root."""
        shutil.rmtree(_checkpoints_root(), ignore_errors=True)


    # Stage ordering for list_checkpoints "last_stage" computation.
    _STAGE_ORDER = ["scrape", "classify", "image_download", "text_ingest"]


    def list_checkpoints() -> list[dict]:
        """Return one record per article_hash under checkpoints/.

        Record: {hash, url, title, last_stage, age_seconds, status}.
        status: "complete" if text_ingest marker present, else "in_flight".
        """
        root = _checkpoints_root()
        if not root.is_dir():
            return []
        out: list[dict] = []
        now = time.time()
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            h = sub.name
            meta = read_metadata(h)
            last = None
            for stage in _STAGE_ORDER:
                if has_stage(h, stage):
                    last = stage
            status = "complete" if has_stage(h, "text_ingest") else "in_flight"
            updated_at = meta.get("updated_at")
            age = (now - updated_at) if isinstance(updated_at, (int, float)) else None
            out.append({
                "hash": h,
                "url": meta.get("url", ""),
                "title": meta.get("title", ""),
                "last_stage": last,
                "age_seconds": age,
                "status": status,
            })
        return out
    ```

    Do NOT re-export from `lib/__init__.py` — callers use `from lib.checkpoint import ...`. Keep Phase 7's 13-symbol public API surface untouched (surgical changes principle).

    Run `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v`. All tests from Task 1 MUST pass. Fix any failures by adjusting implementation, not tests (tests define contract).
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q "^def get_article_hash" lib/checkpoint.py`
    - `grep -q "^def get_checkpoint_dir" lib/checkpoint.py`
    - `grep -q "^def has_stage" lib/checkpoint.py`
    - `grep -q "^def read_stage" lib/checkpoint.py`
    - `grep -q "^def write_stage" lib/checkpoint.py`
    - `grep -q "^def write_metadata" lib/checkpoint.py`
    - `grep -q "^def read_metadata" lib/checkpoint.py`
    - `grep -q "^def reset_article" lib/checkpoint.py`
    - `grep -q "^def reset_all" lib/checkpoint.py`
    - `grep -q "^def list_checkpoints" lib/checkpoint.py`
    - `grep -q "os.rename" lib/checkpoint.py` (atomic write pattern present)
    - `grep -q "hashlib.sha256" lib/checkpoint.py`
    - `grep -q '\[:16\]' lib/checkpoint.py` (16-char hash truncation)
    - `grep -q "STAGE_FILES" lib/checkpoint.py`
    - `grep -qi "omonigraph" config.py` (verifies typo still canonical, not accidentally renamed)
    - `.venv/Scripts/python -c "from lib.checkpoint import get_article_hash; assert len(get_article_hash('https://example.com')) == 16"` exits 0
    - `.venv/Scripts/python -c "from lib.checkpoint import STAGE_FILES; assert set(STAGE_FILES) == {'scrape','classify','image_download','text_ingest','vision_worker'}"` exits 0
    - `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v` exits 0 (all tests pass)
  </acceptance_criteria>

  <done>Module implements full public API; all Task 1 unit tests pass; atomic write pattern verified via crash-simulation test; typo `omonigraph` preserved.</done>
</task>

</tasks>

<verification>
1. Unit tests all pass: `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v`
2. Module loads cleanly: `.venv/Scripts/python -c "from lib.checkpoint import get_article_hash, has_stage, write_stage, read_stage, write_metadata, read_metadata, reset_article, reset_all, list_checkpoints, STAGE_FILES; print('OK')"` prints "OK"
3. Grep-verifiable API surface complete (see acceptance_criteria above)
4. No regressions: `.venv/Scripts/python -m pytest tests/unit/ -q` passes at least as many tests as before (spot check — full suite is downstream plan concern)
</verification>

<success_criteria>
- lib/checkpoint.py exports the 10 mandatory public functions + STAGE_FILES constant
- Every checkpoint write uses the tmp → os.rename atomic pattern (grep confirms)
- Every stage file/dir name matches the locked schema verbatim (verified in test_has_stage_matrix)
- SHA256 truncated to 16 chars (verified in test_get_article_hash_sha256_not_md5)
- Typo "omonigraph" preserved (BASE_DIR imported from config.py, not redefined)
- All >= 20 unit tests pass
- Public API NOT re-exported from lib/__init__.py (surgical — Phase 7 surface preserved)
</success_criteria>

<output>
After completion, create `.planning/phases/12-checkpoint-resume/12-00-SUMMARY.md` with:
- Public API snapshot (function signatures only)
- Test count + pass rate
- Any deviations from the <interfaces> contract
- Files modified: `lib/checkpoint.py` (new), `tests/unit/test_checkpoint.py` (new)
</output>
