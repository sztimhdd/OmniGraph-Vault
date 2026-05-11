---
phase: quick-260511-n0b
plan: 01
type: summary
status: complete
requirements:
  - F-1
  - F-2
key_files:
  modified:
    - image_pipeline.py
    - lib/llm_client.py
  created:
    - .planning/quick/260511-n0b-q-vision-hyg-bundled-f1-f2-fix-from-t5-r/260511-n0b-PLAN.md
    - .planning/quick/260511-n0b-q-vision-hyg-bundled-f1-f2-fix-from-t5-r/260511-n0b-SUMMARY.md
metrics:
  loc_removed: 100
  loc_added: 3
  loc_net: -97
  pytest_pre: "642 passed, 23 failed, 5 skipped"
  pytest_post: "642 passed, 23 failed, 5 skipped"
  pytest_delta: "0 new fail / 0 new pass — zero new failures introduced"
---

# Quick 260511-n0b — Q-VISION-HYG bundled F-1 + F-2

## Headline
F-1 deleted 100 LOC of unreachable `_describe_via_*` code from `image_pipeline.py`; F-2 changed `lib/llm_client.py:51` Vertex `GOOGLE_CLOUD_LOCATION` default `"us-central1"` → `"global"`.

## Outcome
Both T5 review HIGH findings closed in one forward-only commit:
- **F-1**: Deleted 3 unreachable `_describe_via_*` functions in `image_pipeline.py` (Phase 13 dead code, replaced by `lib.vision_cascade` delegation 2026-05-02). 100 LOC removed (3 function bodies + trailing blank-line trailers).
- **F-2**: Aligned `lib/llm_client.py:_make_client` Vertex location default with quick 260511-b3y (`b1e7fc8`) pattern: `"us-central1"` → `"global"`. Net +2 LOC (1-line literal swap + 2-line citation comment).

## Evidence

### F-1 (image_pipeline.py — 3 function delete)

**Pre-flight verification (orchestrator):**
- `.scratch/q-vision-hyg-pre-grep-f1.log` — 0 production callers anywhere (only the 3 self-definitions at lines 306, 352, 379).
- `.scratch/q-vision-hyg-pre-grep-cascade.log` — production cascade is `lib/vision_cascade.py:_call_provider`; `image_pipeline.py:6` docstring documents the delegation.

**Post-delete verification:**
- `.scratch/q-vision-hyg-post-grep.log` — 0 hits for `_describe_via_siliconflow|_describe_via_openrouter|_describe_via_gemini` across all `*.py` (excluding `venv/`, `__pycache__/`, `.planning/`, `.claude/`, `.scratch/`, `.dev-runtime/`).

**Module-scope import preservation:**
- `os` import (line 16) — still used at lines 68, 328, 345, 381, 389.
- `requests` import (line 24) — still used at line 178.
- Function-local `from google import genai` / `from google.genai import types` / `import base64` vanished naturally with the deleted bodies.

**LOC count:** `git diff --numstat image_pipeline.py` reports `0 added / 100 removed`.

### F-2 (lib/llm_client.py — Vertex location default)

**Pre-flight baseline:**
- `.scratch/q-vision-hyg-pre-grep-f2.log` — confirmed `lib/llm_client.py:51` was the second `us-central1` site; `lib/lightrag_embedding.py:141` already uses `"global"`; `lib/vertex_gemini_complete.py:61` defines `_DEFAULT_LOCATION = "global"`.

**Post-fix verification:**
- `grep -n "GOOGLE_CLOUD_LOCATION" lib/llm_client.py` shows line 53: `location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),` — default literal flipped, with 2-line comment block above citing quick 260511-n0b + b3y commit `b1e7fc8`.

**LOC count:** `git diff --numstat lib/llm_client.py` reports `3 added / 1 removed` (net +2).

### Pytest delta

| Metric | Pre-fix | Post-fix | Delta |
|---|---|---|---|
| Passed | 642 | 642 | +0 |
| Failed | 23 | 23 | 0 |
| Skipped | 5 | 5 | 0 |
| Wall time | 268.12s | 276.00s | +7.88s (noise) |

- Pre-pytest log: `.scratch/q-vision-hyg-pre-pytest.log`
- Post-pytest log: `.scratch/q-vision-hyg-post-pytest.log`

The 23 pre-existing failures are unchanged in identity — verified by visual inspection of the trailing failure list (`test_scrape_first_classify`, `test_siliconflow_balance`, `test_text_first_ingest`, `test_timeout_budget`, `test_vision_worker`, etc.). None of the failing tests touch `image_pipeline.py:_describe_via_*` or `lib/llm_client.py:_make_client`. **Zero new failures introduced.**

### Source references
- T5 REVIEW (F-1 + F-2 rationale): `.planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md` §3-§4
- b3y pattern source: commit `b1e7fc8` (`lib/lightrag_embedding.py:141`, `lib/vertex_gemini_complete.py:61,92-93`)

## LOC impact
- F-1: -100 LOC (image_pipeline.py: 3 function bodies + spacing removed)
- F-2: +3 LOC, -1 LOC (lib/llm_client.py: 2-line citation comment + 1 default literal swap)
- **Net: -97 LOC**

## Hermes deploy notes

**F-1 (image_pipeline.py dead code delete):**
Pure code hygiene. Hermes pulls + cron auto-uses new code. No `.env` changes.

**F-2 (lib/llm_client.py GOOGLE_CLOUD_LOCATION default):**
Hermes `~/.hermes/.env` already has `GOOGLE_CLOUD_LOCATION=global` → no runtime change.
Future-proof:
1. Anyone editing `.env` who deletes that line: default is now correct.
2. New machine deploy doesn't need `.env` to set this var.
3. Local dev / `scripts/local_e2e.sh` doesn't need explicit `GOOGLE_CLOUD_PROJECT` defaults to depend on regional endpoints.

Recommended sanity check: `grep GOOGLE_CLOUD_LOCATION ~/.hermes/.env` confirms env mask still active (defense-in-depth).

**No SSH / Hermes operator prompt needed** for this quick. Standard `git pull --ff-only` on Hermes after user pushes locally. No env var changes, no service restart, no schema migration.

## Concurrent-quick discipline observed
- `git pull --ff-only` performed before commit (pre-commit defensive sync).
- Staged only the 4 in-scope files via explicit `git add <path>` (no `git add -A` / `git add .`).
- No `git reset` / `--amend` / `--rebase` / force-push per CLAUDE.md "Lessons Learned" 2026-05-06 #5 (concurrent-quick attribution race lesson).
- `git status --short` re-checked before stage to detect any concurrent-quick `M` files; none touched outside the 4 in-scope paths.
- No literal secrets in any artifact (CLAUDE.md "Lessons Learned 2026-05-08 #3").

## Push
Not pushed by agent. User pushes when ready (per global CLAUDE.md "DO NOT push to the remote repository unless the user explicitly asks").

## Self-Check: PASSED
- F-1 verified: `_describe_via_*` removed from `image_pipeline.py`; 0 hits in `.scratch/q-vision-hyg-post-grep.log`.
- F-2 verified: `lib/llm_client.py:53` reads `"global"`; comment block cites `260511-n0b` + `b1e7fc8`.
- Pytest delta: 642/23/5 → 642/23/5 (identical).
- All evidence files exist and are non-empty: `.scratch/q-vision-hyg-{pre-pytest,post-pytest,post-grep,pre-grep-f1,pre-grep-f2,pre-grep-cascade}.log`.
