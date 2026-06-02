---
quick_id: 260520-rou
description: KDB Agent — fix Databricks Apps broken images by hydrating UC volume images dir to /tmp on boot
mode: quick
date: 2026-05-20
must_haves:
  truths:
    - kb/api.py uses StaticFiles(check_dir=False) to mount /static/img → KB_IMAGES_DIR
    - KB_IMAGES_DIR default in kb/config.py is ~/.hermes/omonigraph-vault/images (does not exist on Databricks Apps container)
    - UC volume /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/ holds 254 hash-dirs / ~2500 .jpg / ~47MB total
    - Existing _db_bootstrap.py already hydrates DB + LightRAG storage but NOT images
    - 'omonigraph' typo is canonical (preserved in KB_IMAGES_DIR / OMNIGRAPH_BASE_DIR)
    - app.yaml is currently committed clean — kb-v2.2-7 SSG agent's prior changes already merged in commit de96738
  artifacts:
    - databricks-deploy/app.yaml (append 2 env vars)
    - databricks-deploy/_db_bootstrap.py (add hydrate_images_dir + main() invocation)
    - databricks-deploy/_kdb_images_fix_VERIFICATION.md (new file, post-deploy)
  key_links:
    - databricks-deploy/app.yaml:17-62 (env block to append to)
    - databricks-deploy/_db_bootstrap.py:35-76 (hydrate_lightrag_storage to mirror)
    - databricks-deploy/_db_bootstrap.py:147-159 (main() invocation pattern to mirror)
    - kb/api.py:49-50 (StaticFiles mount that consumes KB_IMAGES_DIR)
    - kb/config.py:35-38 (KB_IMAGES_DIR default)
    - databricks-deploy/Makefile (deploy target — will run via PowerShell)
---

# Quick Task 260520-rou — Plan

## Goal

Fix /static/img/<hash>/N.jpg 404s on the deployed Databricks Apps URL. Local
http://localhost:8766 renders correctly; only Databricks side broken because
KB_IMAGES_DIR on the container points to a non-existent path and StaticFiles
mounts silently because of `check_dir=False`.

## Approach

Mirror the existing `hydrate_lightrag_storage` pattern in `_db_bootstrap.py`
to add an `hydrate_images_dir` function that recursively walks the UC volume
images directory (2 levels: `<hash>/<N>.jpg`) and downloads every file in
parallel via `ThreadPoolExecutor(max_workers=16)`. Wire it through env vars
`KB_VOLUME_IMAGES_DIR` (source UC volume path) and `KB_IMAGES_DIR` (local
/tmp target — already what kb.config reads at runtime).

## Tasks

### Task 1 — Edit databricks-deploy/app.yaml

**Files:** `databricks-deploy/app.yaml`

**Action:** Append two env entries to the end of the `env:` block (do NOT
rewrite/reorder the existing block). Both target paths are already canonical
in the spec:

```yaml
  # kdb-images-fix: hydrate UC volume images → /tmp at boot.
  # /static/img mount in kb/api.py reads from KB_IMAGES_DIR; without this
  # the path does not exist in the Databricks Apps container and every
  # image request 404s. Volume layout: <root>/<article_hash>/<N>.jpg.
  - name: KB_VOLUME_IMAGES_DIR
    value: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images"

  - name: KB_IMAGES_DIR
    value: "/tmp/omnigraph_vault/images"
```

**Verify:** `grep -c 'KB_VOLUME_IMAGES_DIR\|KB_IMAGES_DIR' databricks-deploy/app.yaml` returns `2`.
**Done when:** Both env vars present at end of env block; no other env entries reordered or changed.

### Task 2 — Edit databricks-deploy/_db_bootstrap.py

**Files:** `databricks-deploy/_db_bootstrap.py`

**Action:**

1. Add `import concurrent.futures` to the imports.
2. Add a new function `hydrate_images_dir(src_dir: str, dst_dir: str) -> int` that:
   - Lists `src_dir` via `w.files.list_directory_contents(src_dir)` to get hash subdirectories.
   - For each hash dir, lists its contents via the same SDK call to get the per-file URIs.
   - Submits each file download to a `ThreadPoolExecutor(max_workers=16)`.
   - Each worker: `mkdir(parents=True, exist_ok=True)` on `<dst>/<hash>/`, then `w.files.download(<src_path>)` → write chunked to `<dst>/<hash>/<filename>`.
   - On per-file exception: `logger.warning(...)` and continue (return non-zero from outer fn if any failed).
   - Logs `"Hydrating images: %s -> %s"` at start, `"Image hydration complete: %d files, %d bytes"` at end.
   - Return `0` on full success, non-zero on partial/total failure.
3. In `main()`, after the LightRAG hydration block (lines 147-159), add a parallel
   block reading `KB_VOLUME_IMAGES_DIR` and `KB_IMAGES_DIR`, calling
   `hydrate_images_dir`, and on non-zero rc emit a `logger.warning(...)` —
   never abort boot (image-only failure should not block /api/articles or /api/search).

**Verify:**

- `grep -n 'def hydrate_images_dir' databricks-deploy/_db_bootstrap.py` returns 1 line.
- `grep -n 'KB_VOLUME_IMAGES_DIR' databricks-deploy/_db_bootstrap.py` returns ≥1 line in main().
- `python -c "import ast; ast.parse(open('databricks-deploy/_db_bootstrap.py').read())"` succeeds.
- The function uses `concurrent.futures.ThreadPoolExecutor` (not asyncio).
- Logging calls only — no `print()`.

**Done when:** File parses, function defined, main() invokes it, error path is `logger.warning` (degrade gracefully).

### Task 3 — Atomic local commit

**Action:**

```bash
git add databricks-deploy/app.yaml databricks-deploy/_db_bootstrap.py
git commit -m "fix(databricks): hydrate UC volume images on boot to fix /static/img 404s"
```

**Verify:** `git log --oneline -1` shows the new commit; `git status` clean.
**Done when:** New commit on local main; no push.

### Task 4 — Deploy via PowerShell (main session)

**Run from main session, NOT executor (Databricks CLI through workspace path requires PowerShell, no path conversion).**

**Action:** Run Makefile-equivalent deploy steps directly with `databricks` CLI:

- Pass 0: refresh databricks-deploy/_ssg/ from kb/output/ (kb-v2.2-7 SSG snapshot, already automated in Makefile but Makefile may not exist as `make` binary on Windows — replicate the steps inline)
- Pass 1: `databricks --profile dev sync --full ./databricks-deploy /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy`
- Pass 2: `databricks --profile dev sync --full ./kb /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy/kb`
- Apps deploy: `databricks --profile dev apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy`

**Verify:** `databricks --profile dev apps get omnigraph-kb -o json` returns status RUNNING with new deployment_id.
**Done when:** Deployment succeeds (apps deploy returns SUCCEEDED).

### Task 5 — Verify boot logs

**Action:** Run `databricks-deploy/scripts/tail_app_logs.py --once --max-seconds 30` (or equivalent) and grep boot stream for:

- `"Hydrating images: /Volumes/.../images -> /tmp/omnigraph_vault/images"`
- `"Image hydration complete: N files, M bytes"` where N≈2500 and M≈47MB
- No `Traceback` mentioning `hydrate_images_dir`

**Done when:** Both log lines visible, count plausible.

### Task 6 — Write VERIFICATION.md

**Files:** `databricks-deploy/_kdb_images_fix_VERIFICATION.md` (new file)

**Action:** Capture:

- Files changed + diff stat
- Local commit hash
- Deployment_id + SUCCEEDED timestamp
- Boot log key lines (Hydrating + complete)
- Operator UAT prompt for browser screenshot relay
- Any anomalies

**Done when:** File present, all sections filled.

### Task 7 — Update STATE.md and final docs commit

**Action:** Append Quick Tasks Completed row to `.planning/STATE.md` (or whichever STATE file the project uses — confirm at commit time). Final commit bundles PLAN.md + SUMMARY.md + STATE.md + VERIFICATION.md.

**Done when:** STATE row added; final commit landed locally; no push.

## Risks

- **app.yaml conflict:** Operator warned about kb-v2.2-7 SSG agent in-progress edits. Verified at plan-time: working tree clean, prior changes already in commit `de96738`. Risk: now LOW.
- **Boot time:** ~2,500 files at 16 workers ≈ 10-30s of extra boot. Databricks Apps container has a boot timeout we should not exceed. ThreadPoolExecutor mitigates serial worst-case.
- **Per-file SDK errors:** Volume access via SDK Files API has been reliable for DB + LightRAG hydration; degrade-gracefully path means a transient blip doesn't break the deploy.
- **Browser UAT requires user relay:** App is OAuth-gated — no autonomous browser test possible. Operator prompt written for user.
