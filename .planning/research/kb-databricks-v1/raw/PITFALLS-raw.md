# PITFALLS — Raw Materials

> Pulled 2026-05-14 by main session. Aggregates likely failure modes for kb-databricks-v1, drawn from MS Learn, Apps Cookbook, OmniGraph project memory, and KB-v2 close-out lessons. Each entry: **Symptom · Root cause · Detection · Mitigation**.

## Category A — Secret leakage / config

### A1. Literal `DEEPSEEK_API_KEY` value committed to `app.yaml`
- **Symptom:** GitHub secret scanner blocks push; or worse, value lives in repo history forever
- **Root cause:** Operator pastes literal token into YAML during testing, forgets to revert
- **Detection:** Pre-commit `git diff --cached -- app.yaml | grep -iE "sk-[a-zA-Z0-9]{20,}"`; post-commit audit `git log -p app.yaml`
- **Mitigation:** Project-wide rule (memory `feedback_no_literal_secrets_in_prompts.md`): zero literal tokens, ever. Always `valueFrom: <resource-key>`. **Add to phase verification:** `git log --all -p -- app.yaml | grep -iE "sk-"` returns empty
- **Status:** Pre-existing project lesson, hard rule

### A2. Secret value visible on App's "Environment" page
- **Symptom:** Workspace UI shows the literal secret in the Environment tab
- **Root cause:** Used `value:` with literal instead of `valueFrom:` resource reference
- **Detection:** Manual UI check after first deploy; should never see `sk-...` in Environment tab
- **Mitigation:** ALWAYS use `valueFrom:` for secrets per MS Learn best-practices
- **Status:** MS Learn explicit warning

### A3. Secret resource created but ACL not granted to App SP
- **Symptom:** App start fails with `PERMISSION_DENIED` on secret scope read; or env var resolves to empty string
- **Root cause:** Created scope + put-secret, but didn't grant SP read on scope
- **Detection:** `databricks secrets list-acls --scope omnigraph-kb` should show app-omnigraph-kb with READ
- **Mitigation:** kdb-2 deploy runbook MUST grant SP READ on scope before first start

## Category B — UC Volume access

### B1. `LightRAG(working_dir="/Volumes/...")` raises at construction
- **Symptom:** App startup logs show `OSError: [Errno 30] Read-only file system` from `os.makedirs(workspace_dir, exist_ok=True)`
- **Root cause:** Volume mounted read-only (App SP has only `READ VOLUME`); `os.makedirs` enters write path even with `exist_ok=True`; documented at `lightrag/kg/json_kv_impl.py:39`
- **Detection:** Cold-start log scan on first deploy
- **Mitigation:** Either grant `WRITE VOLUME` (broader surface, accept) OR copy-to-/tmp pattern at startup (safer; trigger kdb-1.5)

### B2. SQLite `kol_scan.db` refuses to open from `/Volumes/...`
- **Symptom:** `sqlite3.OperationalError: unable to open database file` or `database is locked`
- **Root causes (likely several):**
  - WAL/SHM sidecars from Hermes side present on Volume → SQLite refuses
  - FUSE mount lacks fcntl(F_SETLK) → SQLite locking unsupported
  - `kb/data/article_query.py` opens RW instead of RO
- **Detection:** kdb-2 smoke `/api/articles` endpoint; first hit shows error
- **Mitigation:** WAL-checkpoint + delete sidecars before sync (per ARCHITECTURE Option A runbook); confirm `kb/data/article_query.py` uses `:?mode=ro`; if FUSE locking is the issue, fall back to copy-to-/tmp

### B3. Volume not FUSE-mounted in Apps runtime
- **Symptom:** Path `/Volumes/...` returns "not found" even though `databricks fs ls` shows files
- **Root cause:** Apps runtime exposes Volume only via Files API, not FUSE
- **Detection:** `python -c "import os; print(os.listdir('/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault'))"` from running App container (use `databricks apps run-local` or App console)
- **Mitigation:** Replace POSIX reads with `w.files.download()` (Apps Cookbook pattern); replace `StaticFiles` mount with proxy route. **Note:** this would balloon scope — likely trigger kdb-1.5

### B4. Sync interrupted mid-flight leaves Volume inconsistent
- **Symptom:** App shows half-old, half-new article state; some articles 404
- **Root cause:** `databricks fs cp -r --overwrite` is per-file, not transactional
- **Detection:** Manual UAT after sync; spot-check article counts pre/post
- **Mitigation:** Run sync with no concurrent App reads if possible (briefly stop App). Or accept "eventually consistent" with the understanding that brief partial reads are tolerable for internal preview

## Category C — Apps runtime quirks

### C1. App stuck in "STARTING" → 20m timeout
- **Symptom:** `databricks apps deploy` returns timeout; UI shows STARTING indefinitely
- **Root causes:**
  - Slow LightRAG cold-start (loading large graphml/JSON from `/Volumes/...` over FUSE)
  - DeepSeek API key fetch loops (network egress blocked)
  - Port mismatch: app binds to `8766` (KB-v2 default) but runtime expects `$DATABRICKS_APP_PORT=8080`
- **Detection:** Apps "Logs" tab; first 60 seconds show what's happening
- **Mitigation:**
  - Verify `command:` uses `$DATABRICKS_APP_PORT` substitution OR hardcoded 8080 (NOT 8766)
  - Verify FUSE mount latency before deploy (run a perf test)
  - Verify outbound HTTPS to api.deepseek.com works (test with simple curl from app)

### C2. App auto-stop after idle period (cost optimization)
- **Symptom:** App responds instantly during demo, then 30s cold-start the next day
- **Root cause:** Apps default behavior — idle apps may be paused (compute released)
- **Detection:** Pattern of cold-starts in Apps runtime metrics
- **Mitigation:** Internal preview is OK with cold-starts. Document this for stakeholders. v2 = warm pool / scheduled keep-alive if needed

### C3. App.yaml in nested directory not picked up
- **Symptom:** App ignores app.yaml; uses default `python <first-py>`; wrong port; no env vars
- **Root cause:** `app.yaml` MUST be at root of project directory (MS Learn explicit)
- **Detection:** Apps logs show wrong startup command
- **Mitigation:** Hard-rule — `app.yaml` lives at repo root or at the deploy `--source-code-path` root. If we deploy from a subdirectory, that subdirectory's root holds the file

### C4. Service principal grants forgotten before first start
- **Symptom:** `databricks apps start omnigraph-kb` succeeds technically but App can't read Volume → 500s on every endpoint
- **Root cause:** SP has no grants by default
- **Detection:** Apps logs show PERMISSION_DENIED on first `/Volumes/...` access
- **Mitigation:** kdb-2 runbook checklist has 3 grants documented + verifiable via `databricks-mcp-server execute_sql "SHOW GRANTS ..."` before starting App

### C5. `valueFrom:` typo or non-existent resource key
- **Symptom:** App starts, but `os.environ["DEEPSEEK_API_KEY"]` is empty, DeepSeek calls 401
- **Root cause:** Typo in resource key — `valueFrom: secret_typo` doesn't match any defined resource
- **Detection:** Smoke test `/synthesize` shows 401; inspect via app log
- **Mitigation:** kdb-2 verification checklist: deploy → tail logs → confirm key resolves

## Category D — Cross-system coupling

### D1. KB-v2 D-19 fallback contract broken in Databricks deploy
- **Symptom:** `/synthesize` returns 500 instead of FTS5 fallback when LightRAG storage missing/broken
- **Root cause:** Volume sync forgot `lightrag_storage/` dir; or copy-to-/tmp adapter has a bug
- **Detection:** Smoke 3 negative path
- **Mitigation:** Reuse KB-v2 contract test for fallback; verify in kdb-3

### D2. Hermes ingest writes new articles, but Databricks App still serves stale
- **Symptom:** User does ingest on Hermes, expects to see new article in Databricks KB; doesn't appear
- **Root cause:** Manual sync not run; or App not restarted after sync; or copy-to-/tmp pattern uses cached `/tmp` from previous instance
- **Detection:** UAT — user expectation gap
- **Mitigation:** v1 documents this in user-facing readme: "after sync, restart App via UI or `databricks apps stop/start`". v2 adds auto-detection (file mtime change in Volume → restart trigger)

### D3. Two App instances writing same Volume path concurrently
- **Symptom:** LightRAG storage corruption; non-atomic `write_json` race
- **Root cause:** If App is scaled horizontally OR if a deploy overlaps with running App
- **Detection:** Volume file partial / invalid JSON
- **Mitigation:** Apps default = single instance. Don't enable horizontal scaling for v1. If we ever enable WRITE VOLUME on App SP, also enforce single-instance constraint

## Category E — Operational / observability

### E1. App logs not accessible after auth lockout
- **Symptom:** App fails, logs needed for diagnosis, but workspace is logged-out / 2FA-stuck
- **Mitigation:** `databricks apps get omnigraph-kb -o json` from CLI works once profile auth refreshed; document fallback path in v1 runbook

### E2. Cold-start during demo
- **Symptom:** Demo to stakeholders → 30s spinner → bad first impression
- **Mitigation:** Hit the App URL ~5 minutes before demo to warm it; revisit auto-stop timing for v2

### E3. Forgotten `databricks bundle` deploy when using bundle pattern
- **Symptom:** Code changes don't take effect after `databricks apps deploy`
- **Root cause:** `--source-code-path` points to workspace path that's stale; deployer forgot `databricks bundle deploy` first
- **Mitigation:** Single-command `make deploy` recipe in kdb-2 that does both bundle deploy + apps deploy in sequence

## Category F — Cost / quota

### F1. Apps compute always-on burns budget
- **Symptom:** Internal preview generates monthly Databricks Apps cost user didn't expect
- **Mitigation:** Apps idle policy auto-pauses; verify Apps configuration sets a sensible idle timeout. Document cost in PROJECT.md after first month of running.

### F2. DeepSeek quota / balance depletion
- **Symptom:** `/synthesize` returns DeepSeek 402 Payment Required mid-flight
- **Mitigation:** Pre-existing project monitoring (DeepSeek balance check); not new for kb-databricks-v1. Document in runbook

## Category G — Carry-over from prior project lessons

These are documented OmniGraph lessons (memory + CLAUDE.md) that apply equally to Apps deployment:

- **G1.** "Half-fix" pattern (memory `feedback_contract_shape_change_full_audit.md`): when changing app.yaml or app config, grep all sites that consume the changed key
- **G2.** "Verify with Playwright after major tasks" (CLAUDE.md Rule 2): after kdb-2 deploy, hit the App URL with `mcp__playwright__browser_*` to confirm visual rendering — not just `curl /api/health`
- **G3.** "Don't outsource SSH to user" (memory `feedback_dont_outsource_ssh.md`): if Hermes-side commands needed for sync prep, write a Hermes prompt or run via Bash, don't ask user to paste

## Pitfall coverage matrix — which phase blocks each

| Pitfall | kdb-1 | kdb-1.5 | kdb-2 | kdb-3 | runbook only |
|---------|-------|---------|-------|-------|--------------|
| A1 Secret in commit | | | ✅ verify | ✅ audit | |
| A2 Plaintext on Env page | | | ✅ verify | | |
| A3 Scope ACL missing | | | ✅ runbook | | |
| B1 makedirs raises | ✅ verify | ✅ fix | | | |
| B2 SQLite refuses | ✅ verify | ✅ fix | | | |
| B3 No FUSE mount | ✅ verify | ✅ fix | | | |
| B4 Partial sync | | | | | ✅ |
| C1 STARTING timeout | | | ✅ smoke | | |
| C2 Idle pause | | | | | ✅ documented |
| C3 app.yaml location | | | ✅ smoke | | |
| C4 SP grants | ✅ runbook | | | | |
| C5 valueFrom typo | | | ✅ smoke | | |
| D1 Fallback broken | | | | ✅ smoke 3 | |
| D2 Stale serve | | | | ✅ runbook | |
| D3 Concurrent writes | | | | | ✅ |
| E1-E3 Ops | | | | | ✅ |
| F1-F2 Cost | | | | | ✅ |
