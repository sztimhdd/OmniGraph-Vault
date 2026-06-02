---
phase: quick-260524-tvg
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/runbooks/wechat-cookie-refresh.md
  - batch_scan_kol.py
  - tests/unit/test_batch_scan_kol_session_invalid.py
  - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service
  - deploy/aliyun/systemd/omnigraph-kol-scan.service
  - scripts/deploy-aliyun-session-alert.sh
  - skills/wechat-cdp-credential-refresh/
autonomous: true
requirements:
  - TVG-A-runbook
  - TVG-B1-ret200003-exit
  - TVG-B2-systemd-onfailure
  - TVG-C-skill-ingestion

must_haves:
  truths:
    - "Operator (Hai) has a self-contained runbook to refresh WeChat cookie when stale, with no sensitive literals"
    - "When >=30% of KOLs return ret=200003 in a scan, batch_scan_kol.py exits 2 and prints WECHAT_SESSION_INVALID:N/total to stderr"
    - "When omnigraph-kol-scan.service exits non-zero on Aliyun, an OnFailure unit creates ~/.hermes/wechat-session-stale with current mtime"
    - "skills/wechat-cdp-credential-refresh/SKILL.md exists in repo, ready for Hermes-side reuse, with no cookie / token literals"
  artifacts:
    - path: "docs/runbooks/wechat-cookie-refresh.md"
      provides: "Self-contained cookie-refresh runbook"
      min_lines: 40
    - path: "batch_scan_kol.py"
      provides: "ret=200003 counter + threshold-based non-zero exit"
      contains: "WECHAT_SESSION_INVALID"
    - path: "tests/unit/test_batch_scan_kol_session_invalid.py"
      provides: "4 unit tests pinning exit-code behavior at boundaries"
      contains: "test_"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-alert.service"
      provides: "OnFailure handler that touches stale-marker file"
      contains: "Type=oneshot"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan.service"
      provides: "Updated to fire OnFailure handler on non-zero exit"
      contains: "OnFailure="
    - path: "scripts/deploy-aliyun-session-alert.sh"
      provides: "Aliyun-side deployment of alert service via aliyun-vitaclaw SSH alias"
      contains: "scp"
    - path: "skills/wechat-cdp-credential-refresh/SKILL.md"
      provides: "Hermes-side skill copied into repo"
      contains: "name:"
  key_links:
    - from: "batch_scan_kol.py scan_account exception handler"
      to: "session-invalid counter"
      via: "string match for 'ret=200003' in exception message"
      pattern: "ret=200003"
    - from: "deploy/aliyun/systemd/omnigraph-kol-scan.service [Unit]"
      to: "omnigraph-kol-scan-alert.service"
      via: "OnFailure= directive"
      pattern: "OnFailure=omnigraph-kol-scan-alert.service"
---

<objective>
Harden the silent-failure mode that hid 2026-05-24's full WeChat-cookie expiry (54/54 ret=200003 → systemd exit 0 → no alerts). Three orthogonal defenses + a runbook + skill capture: detect-and-fail-loud at the application layer (B1), surface failures at the systemd layer (B2), document the recovery procedure (A), and persist the recovery skill in-repo (C).

Purpose: Next cookie expiry is detected and operator-actionable within one scan cycle, not silently absorbed.
Output: 4 tracks shipped + pushed to origin/main + Aliyun OnFailure handler installed and verified.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@batch_scan_kol.py
@deploy/aliyun/systemd/omnigraph-kol-scan.service

<interfaces>
<!-- Key contracts the executor needs. Extracted from spiders/wechat_spider.py. -->

`spiders/wechat_spider.py` raises on non-zero ret codes:

```python
# Lines 110-122 and 213-225 (two API call sites — list-articles + digest)
if base_resp.get("ret") != 0:
    ret_code = base_resp.get("ret")
    err_msg = base_resp.get("err_msg", "")
    # ... retries on 200013 only ...
    raise RuntimeError(f"WeChat API error (ret={ret_code}): {err_msg}")
```

`batch_scan_kol.py:scan_account` (line 211-228) catches this exception:

```python
except Exception as exc:
    logger.error("  Failed to scan %s: %s", name, exc)
    return False, 0, 0
```

So `str(exc)` contains literal `ret=200003` when cookie expires. Detection key: substring match on the exception string before the `return False, 0, 0`.

Aliyun systemd unit currently has NO OnFailure (deploy/aliyun/systemd/omnigraph-kol-scan.service:1-17 — see file in context).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1 (Track A): Cookie-refresh runbook + MEMORY.md index</name>
  <files>docs/runbooks/wechat-cookie-refresh.md, ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md</files>
  <action>
Create `docs/runbooks/wechat-cookie-refresh.md` with these sections (no sensitive literals — use placeholders only):

1. **When to trigger** — symptoms list:
   - `~/.hermes/wechat-session-stale` exists on Aliyun (B2 marker)
   - `journalctl -u omnigraph-kol-scan.service` shows `WECHAT_SESSION_INVALID: N/total` on stderr (B1)
   - Daily digest shows 0 new articles for 2+ days
   - Manual `python batch_scan_kol.py --daily` exits 2

2. **Hermes-side refresh (operator runs in Hermes session)** — paste-ready Hermes prompt that invokes the `wechat-cdp-credential-refresh` skill. Reference the skill by name only; do NOT inline cookie values.

3. **Transfer to Aliyun (2-hop scp)** — sequence:
   - From Hermes: cookie/token written to `~/.hermes/<staging-path>/kol_config.py`
   - Hai's laptop: `scp <hermes-staging>:kol_config.py /tmp/` then `scp /tmp/kol_config.py aliyun-vitaclaw:/root/OmniGraph-Vault/kol_config.py`
   - Reference SSH details by alias only (`hermes` / `aliyun-vitaclaw`) — NEVER inline host/port/user

4. **Verification on Aliyun** — commands:
   - `ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && venv-aim1/bin/python -c 'import kol_config; print(len(kol_config.COOKIE))'"` (sanity-check non-empty)
   - `ssh aliyun-vitaclaw "rm -f ~/.hermes/wechat-session-stale"` (clear marker)
   - `ssh aliyun-vitaclaw "systemctl start omnigraph-kol-scan.service && sleep 30 && systemctl status omnigraph-kol-scan.service"` (manual trigger; expect Result=success)
   - `ssh aliyun-vitaclaw "tail -50 /var/log/syslog | grep batch_scan_kol"` — expect ok>0, no `WECHAT_SESSION_INVALID`

5. **Hard constraints** — explicit list:
   - Never paste cookie / token values into chat, commits, or this runbook
   - Never inline SSH host/port/user — only aliases
   - `kol_config.py` is gitignored on both machines — never `git add` it

After file is committed, append ONE line to MEMORY.md (file path: `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md`) under the existing index list:

```
- [WeChat cookie-refresh runbook](feedback_wechat_cookie_refresh_runbook.md) — When ret=200003 storm fires (B1 stderr / B2 ~/.hermes/wechat-session-stale), follow docs/runbooks/wechat-cookie-refresh.md: Hermes-side wechat-cdp-credential-refresh skill → 2-hop scp to Aliyun → verification commands. Authored 260524-tvg.
```

Also create the memory note file `feedback_wechat_cookie_refresh_runbook.md` in the same memory directory with a 5-10 line summary pointing to `docs/runbooks/wechat-cookie-refresh.md` as canonical source.
  </action>
  <verify>
    <automated>powershell -Command "if ((Get-Content docs/runbooks/wechat-cookie-refresh.md -Raw) -match '101\.133|49221|root@|slave_sid|data_ticket') { exit 1 } else { exit 0 }"</automated>
    Manual: file exists, >=40 lines, four sections present (When/Hermes-side/Transfer/Verification + constraints).
  </verify>
  <done>Runbook committed; MEMORY.md has new index entry; no sensitive literals (grep verification command above exits 0).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2 (Track B1): ret=200003 counter + non-zero exit + 4 tests</name>
  <files>batch_scan_kol.py, tests/unit/test_batch_scan_kol_session_invalid.py</files>
  <behavior>
    - case 1: 0/54 invalid → run() exits 0
    - case 2: 16/54 (29.6%) invalid → run() exits 0 (under 30% threshold)
    - case 3: 17/54 (31.5%) invalid → run() raises SystemExit(2) AND stderr contains "WECHAT_SESSION_INVALID: 17/54"
    - case 4: 54/54 (100%) invalid → run() raises SystemExit(2) AND stderr contains "WECHAT_SESSION_INVALID: 54/54"
  </behavior>
  <action>
Patch `batch_scan_kol.py`:

1. Add module-level constant near `SESSION_LIMIT` (line 38):

   ```python
   # Threshold for ret=200003 cookie-expiry detection. NOT env-overridable
   # per CLAUDE.md v1.0.x lesson #1 (cross-coupling risk). Forward-only fix
   # if tuning needed.
   SESSION_INVALID_THRESHOLD = 0.30  # 30% of attempts returning ret=200003
   ```

2. Modify `scan_account` (lines 211-228) to return a 4-tuple `(ok, new, skipped, session_invalid: bool)`:
   - In the `except Exception as exc` block, set `session_invalid = "ret=200003" in str(exc)`
   - Return `False, 0, 0, session_invalid`
   - On success path: return `True, new, skipped, False`

3. Modify `run()` (lines 270-299) to:
   - Initialize `invalid_count = 0` before the loop
   - Unpack the new 4-tuple: `ok, new, skipped, session_invalid = scan_account(...)`
   - `if session_invalid: invalid_count += 1`
   - After the loop completes (after the existing "Scan complete" log line at line 296-299), add:

     ```python
     total_attempts = scanned_count + failed_count
     if total_attempts > 0 and invalid_count / total_attempts >= SESSION_INVALID_THRESHOLD:
         print(f"WECHAT_SESSION_INVALID: {invalid_count}/{total_attempts}", file=sys.stderr)
         sys.exit(2)
     ```

   - Place this BEFORE the `if summary_json:` block so JSON-summary path also triggers exit.
   - The `try/finally` ensures `conn.close()` still runs (sys.exit raises SystemExit, finally fires).

4. Create `tests/unit/test_batch_scan_kol_session_invalid.py`:
   - Use `pytest` + `monkeypatch` to stub out `init_db`, `init_accounts`, `load_env`, `time.sleep`, and the conn.execute("SELECT name, fakeid FROM accounts ...") to return 54 fake (name, fakeid) rows.
   - Stub `scan_account` to return `(False, 0, 0, True)` for the first N rows and `(True, 0, 0, False)` for the rest, parameterized per case.
   - For cases 3 & 4: assert `pytest.raises(SystemExit) as exc_info` and `exc_info.value.code == 2`, capture stderr via `capsys`, assert `"WECHAT_SESSION_INVALID: <N>/54"` in `capsys.readouterr().err`.
   - For cases 1 & 2: call `run(...)` directly, assert no SystemExit raised (or exit code != 2).

5. Verify imports still work: `python -c "import batch_scan_kol"` exits 0.

Pure surgical: SESSION_LIMIT preserved, all existing args preserved, new constant + 1-bool return field + ~6 new lines in run(). No env-var. No new imports needed (sys already imported).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_batch_scan_kol_session_invalid.py -v 2>&1 | tee .scratch/quick-260524-tvg-b1-pytest.log</automated>
    Also: `venv/Scripts/python.exe -c "import batch_scan_kol; print('import ok')"` exits 0.
  </verify>
  <done>4 tests green; module imports; commit message body cites `.scratch/quick-260524-tvg-b1-pytest.log` real line numbers (no fabrication).</done>
</task>

<task type="auto">
  <name>Task 3 (Track B2): systemd OnFailure alert + Aliyun deployment</name>
  <files>deploy/aliyun/systemd/omnigraph-kol-scan-alert.service, deploy/aliyun/systemd/omnigraph-kol-scan.service, scripts/deploy-aliyun-session-alert.sh</files>
  <action>
1. Create `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service`:
   ```ini
   [Unit]
   Description=OmniGraph KOL scan failure alert (touches ~/.hermes/wechat-session-stale)

   [Service]
   Type=oneshot
   User=root
   ExecStart=/bin/bash -c 'mkdir -p /root/.hermes && date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ > /root/.hermes/wechat-session-stale'

   ```
   Note: `%%` escapes `%` in systemd unit files. The marker file content is a UTC ISO-8601 timestamp; mtime is set automatically.

2. Modify `deploy/aliyun/systemd/omnigraph-kol-scan.service` — add ONE line under `[Unit]` (after line 4 `Wants=network-online.target`):
   ```

   OnFailure=omnigraph-kol-scan-alert.service

   ```
   No other changes to that file.

3. Create `scripts/deploy-aliyun-session-alert.sh` (bash, executable):
   ```bash
   #!/usr/bin/env bash
   # Deploy session-invalid alert handler to Aliyun.
   # Run from local repo root. Uses ssh alias `aliyun-vitaclaw` (see ~/.ssh/config).
   # Idempotent — safe to re-run.
   set -euo pipefail

   REMOTE=aliyun-vitaclaw
   REMOTE_DIR=/etc/systemd/system

   echo "[1/4] scp alert service unit ..."
   scp deploy/aliyun/systemd/omnigraph-kol-scan-alert.service "$REMOTE:$REMOTE_DIR/"

   echo "[2/4] scp updated kol-scan service unit ..."
   scp deploy/aliyun/systemd/omnigraph-kol-scan.service "$REMOTE:$REMOTE_DIR/"

   echo "[3/4] systemctl daemon-reload ..."
   ssh "$REMOTE" "systemctl daemon-reload"

   echo "[4/4] enable alert unit (it's OnFailure-triggered, no enable strictly needed but explicit is good) ..."
   ssh "$REMOTE" "systemctl enable omnigraph-kol-scan-alert.service 2>&1 || true"

   echo "Done. To verify: bash scripts/deploy-aliyun-session-alert.sh && ssh $REMOTE 'systemctl start omnigraph-kol-scan-alert.service && ls -la /root/.hermes/wechat-session-stale'"
   ```

   `chmod +x scripts/deploy-aliyun-session-alert.sh`.

4. **Agent runs the deployment directly** (PRINCIPLE 5 override per memory `feedback_aim1_agent_is_operator.md` — aim-1+ phases SSH Aliyun directly):

   ```bash
   bash scripts/deploy-aliyun-session-alert.sh 2>&1 | tee .scratch/quick-260524-tvg-b2-deploy.log
   ```

5. **Agent runs verification directly** via SSH:

   ```bash
   ssh aliyun-vitaclaw "rm -f /root/.hermes/wechat-session-stale && systemctl start omnigraph-kol-scan-alert.service && sleep 2 && ls -la /root/.hermes/wechat-session-stale && cat /root/.hermes/wechat-session-stale" 2>&1 | tee .scratch/quick-260524-tvg-b2-verify.log
   ```

   Expected output: file exists, mtime ~now, content is current UTC timestamp.

6. After verification passes, clean up the test marker on Aliyun so it doesn't trigger a false runbook execution:

   ```bash
   ssh aliyun-vitaclaw "rm -f /root/.hermes/wechat-session-stale"
   ```

  </action>
  <verify>
    <automated>powershell -Command "if (Select-String -Path .scratch/quick-260524-tvg-b2-verify.log -Pattern 'wechat-session-stale' -Quiet) { exit 0 } else { exit 1 }"</automated>
    Manual: log shows `ls -la` output with current mtime + cat output is ISO-8601 timestamp.
  </verify>
  <done>Alert unit deployed on Aliyun; manual systemctl start creates marker file; deploy + verify logs in .scratch/.</done>
</task>

<task type="auto">
  <name>Task 4 (Track C): Copy wechat-cdp-credential-refresh skill into repo</name>
  <files>skills/wechat-cdp-credential-refresh/</files>
  <action>
Source: `.scratch/hermes-cookie-refresh/20260524-211033/wechat-cdp-credential-refresh/`

1. Verify source exists:

   ```bash
   ls .scratch/hermes-cookie-refresh/20260524-211033/wechat-cdp-credential-refresh/
   ```

   Expected: at minimum `SKILL.md`, possibly `references/` and/or `scripts/`.

2. Copy entire directory tree to `skills/`:

   ```bash
   mkdir -p skills/wechat-cdp-credential-refresh
   cp -r .scratch/hermes-cookie-refresh/20260524-211033/wechat-cdp-credential-refresh/* skills/wechat-cdp-credential-refresh/
   ```

   Preserve original SKILL.md / references/ / scripts/ separation (per CLAUDE.md "OpenClaw / Hermes Skill Writing Standards" section).

3. **Audit copied files for sensitive literals** before staging:

   ```bash
   grep -rE 'slave_sid|data_ticket|rand_info|bizuin|xid|wxuin|slave_user|TOKEN=' skills/wechat-cdp-credential-refresh/
   ```

   If ANY match, STOP and remove the offending lines / replace with placeholders (`<COOKIE_VALUE>` / `<TOKEN>`). The Hermes skill should already use placeholders, but verify.

4. Create `skills/wechat-cdp-credential-refresh/README.md`:

   ```markdown
   # wechat-cdp-credential-refresh

   Copied from Hermes session 20260524-211033 (quick `260524-tvg` Track C).

   ## Runtime requirements

   This skill ONLY runs on a Windows host with Microsoft Edge launched with
   `--remote-debugging-port=9223` (CDP). Hermes is currently the only such
   machine in this project; running this skill on Aliyun or any Linux box
   will fail at the CDP-connect step.

   ## Usage

   See SKILL.md for the canonical instructions. Operator-side wrapper /
   when-to-trigger guidance lives in `docs/runbooks/wechat-cookie-refresh.md`.

   ## Do not commit

   - Cookie values, TOKEN values — these are runtime data, never source-of-truth
   - The output `kol_config.py` produced by this skill (gitignored)
   ```

  </action>
  <verify>
    <automated>powershell -Command "if (Test-Path skills/wechat-cdp-credential-refresh/SKILL.md) { if ((Get-ChildItem skills/wechat-cdp-credential-refresh -Recurse | Select-String -Pattern 'slave_sid|data_ticket|rand_info|wxuin').Count -eq 0) { exit 0 } else { exit 1 } } else { exit 1 }"</automated>
  </verify>
  <done>SKILL.md present; README.md present; grep finds zero cookie-component literals.</done>
</task>

</tasks>

<verification>
After all 4 tasks:

1. `git status` — only the listed `files_modified` paths appear. `kol_config.py` MUST NOT be staged.
2. `venv/Scripts/python.exe -m pytest tests/unit/test_batch_scan_kol_session_invalid.py -v` — 4 passed.
3. `venv/Scripts/python.exe -c "import batch_scan_kol; print('ok')"` — prints "ok".
4. `.scratch/quick-260524-tvg-b2-verify.log` exists and shows `wechat-session-stale` file with current mtime.
5. `grep -rE 'slave_sid|data_ticket|wxuin|49221|101\.133|root@' docs/runbooks/wechat-cookie-refresh.md skills/wechat-cdp-credential-refresh/ scripts/deploy-aliyun-session-alert.sh` — zero matches.
6. Single chained git commit per CLAUDE.md `feedback_git_add_explicit_in_parallel_quicks.md`:

   ```
   git add docs/runbooks/wechat-cookie-refresh.md \
           batch_scan_kol.py \
           tests/unit/test_batch_scan_kol_session_invalid.py \
           deploy/aliyun/systemd/omnigraph-kol-scan-alert.service \
           deploy/aliyun/systemd/omnigraph-kol-scan.service \
           scripts/deploy-aliyun-session-alert.sh \
           skills/wechat-cdp-credential-refresh \
       && git commit -m "..." \
       && git push
   ```

   NEVER `git add -A` / `git add .` / `--amend` / `git reset --hard`.
7. Commit message body MUST cite the real `.scratch/quick-260524-tvg-*.log` paths with line ranges (no fabricated test-output text).
</verification>

<success_criteria>

- [ ] `docs/runbooks/wechat-cookie-refresh.md` exists, >=40 lines, no sensitive literals
- [ ] MEMORY.md has new index entry pointing to `feedback_wechat_cookie_refresh_runbook.md`
- [ ] `batch_scan_kol.py` has SESSION_INVALID_THRESHOLD constant + 4-tuple return + post-loop exit-2 block
- [ ] 4 unit tests in `tests/unit/test_batch_scan_kol_session_invalid.py` all pass
- [ ] `import batch_scan_kol` raises no error
- [ ] `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` exists; `omnigraph-kol-scan.service` has `OnFailure=` line
- [ ] `scripts/deploy-aliyun-session-alert.sh` is executable; agent has run it on Aliyun successfully (log in .scratch/)
- [ ] Agent has manually triggered `systemctl start omnigraph-kol-scan-alert.service` on Aliyun and confirmed `~/.hermes/wechat-session-stale` was created (log in .scratch/)
- [ ] After verification, agent removed the test marker file from Aliyun
- [ ] `skills/wechat-cdp-credential-refresh/SKILL.md` + `README.md` exist; zero cookie-component literals
- [ ] All commits pushed to origin/main; `kol_config.py` NOT in git history
</success_criteria>

<output>
After completion, create `.planning/quick/260524-tvg-wechat-session-hardening/260524-tvg-SUMMARY.md` with:
- One section per track (A / B1 / B2 / C) — what was changed, evidence (commit hash, log path)
- Verification results (pytest log line refs, .scratch/quick-260524-tvg-b2-verify.log line refs)
- Confirmation that no sensitive literals reached git history
- Note that orchestrator (not executor) appends STATE.md row
</output>
