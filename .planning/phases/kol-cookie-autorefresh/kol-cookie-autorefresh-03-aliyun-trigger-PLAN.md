---
phase: kol-cookie-autorefresh
plan: 03
type: execute
wave: 2
depends_on: [02]
files_modified:
  - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service
  - scripts/deploy-aliyun-session-alert.sh
autonomous: false
requirements: [KCA-1]
actor: ALIYUN-WRITE
must_haves:
  truths:
    - "When the Aliyun kol-scan exits 2 (cookie expiry ≥30%), OnFailure fires the alert unit which ssh-hands-off to Hermes to run the refresh wrapper"
    - "The alert unit still touches /root/.hermes/wechat-session-stale as a breadcrumb"
    - "The hand-off invokes the Plan-02 wrapper non-interactively on Hermes via ssh hermes"
  artifacts:
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-alert.service"
      provides: "ssh-hermes hand-off ExecStart replacing the no-op"
      contains: "ssh hermes"
    - path: "scripts/deploy-aliyun-session-alert.sh"
      provides: "idempotent deploy of the updated alert unit to Aliyun"
      contains: "daemon-reload"
  key_links:
    - from: "deploy/aliyun/systemd/omnigraph-kol-scan.service (OnFailure=)"
      to: "omnigraph-kol-scan-alert.service"
      via: "systemd OnFailure"
      pattern: "OnFailure=omnigraph-kol-scan-alert"
    - from: "omnigraph-kol-scan-alert.service ExecStart"
      to: "Hermes refresh_wechat_cookie.py"
      via: "ssh hermes ... python3 scripts/refresh_wechat_cookie.py"
      pattern: "refresh_wechat_cookie.py"
---

<objective>
Replace the no-op Aliyun alert unit with a real hand-off: when the daily kol-scan detects cookie
expiry (ret=200003 ≥30% → exit 2 → OnFailure), the alert unit ssh-es to Hermes and invokes the
Plan-02 refresh wrapper non-interactively, while still touching the stale-flag breadcrumb. Deploy it
to Aliyun via the existing idempotent deploy script.

Purpose: This is hop ①②  of the locked option-A chain — the trigger. Today the alert unit only runs
`date > wechat-session-stale` and nothing consumes it (ISSUES #56). Aliyun→Hermes ssh is empirically
LIVE (RESEARCH.md post-P0: `ALIYUN_TO_HERMES_OK`). Aliyun is agent-direct per Principle #5 — the
orchestrator has the key and can do this write directly.

Output: Updated omnigraph-kol-scan-alert.service (repo template) + deploy-aliyun-session-alert.sh,
deployed to Aliyun (/etc/systemd/system) with daemon-reload. A checkpoint confirms the OnFailure
wiring fires the hand-off.

Actor: [ALIYUN-WRITE] — orchestrator edits the repo templates locally, then deploys to Aliyun
directly via ssh/scp (has the key). Depends on Plan 02: the ssh hand-off invokes
refresh_wechat_cookie.py, which must exist on Hermes (synced via the existing channel) for the
trigger to land on something real. The actual Hermes-side sync + the trigger's target path are
verified in Plan 04 (operator) + Plan 05 (end-to-end).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md
@deploy/aliyun/systemd/omnigraph-kol-scan-alert.service
@deploy/aliyun/systemd/omnigraph-kol-scan.service
@scripts/deploy-aliyun-session-alert.sh

<interfaces>
<!-- Current no-op alert unit (the thing being replaced). -->
omnigraph-kol-scan-alert.service:
  [Service]
  Type=oneshot
  User=root
  ExecStart=/bin/bash -c 'mkdir -p /root/.hermes && date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ > /root/.hermes/wechat-session-stale'

<!-- The scan unit that fires OnFailure (unchanged). -->
omnigraph-kol-scan.service:  OnFailure=omnigraph-kol-scan-alert.service

<!-- Aliyun→Hermes ssh hand-off (LIVE, RESEARCH.md post-P0). The Aliyun ~/.ssh/config has a `hermes`
     stanza: HostName ohca.ddns.net, Port 49221, User sztimhdd, IdentityFile ~/.ssh/id_ed25519. -->
ssh hermes "<command on Hermes>"   →  ALIYUN_TO_HERMES_OK / OH-Desktop

<!-- Hermes refresh wrapper path (Plan 02 artifact; on Hermes the repo is ~/OmniGraph-Vault, system
     python3, venv NOT used for the wrapper). -->
ssh hermes "cd ~/OmniGraph-Vault && nohup python3 scripts/refresh_wechat_cookie.py >> ~/.hermes/kol-refresh.log 2>&1 &"
  (run detached + log so the oneshot Aliyun unit returns promptly; the refresh can take minutes,
   esp. level C polling ~5min — do NOT block the systemd oneshot on it.)

<!-- Aliyun deploy target + scp/ssh discipline. The deploy script currently uses ssh alias
     `aliyun-vitaclaw` which is STALE post-rebuild (points at dead old IP). The orchestrator runs
     this with the explicit live target `root@47.117.244.253` + key during this plan. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: [ALIYUN-WRITE/REPO-CODE] Rewrite alert unit ExecStart to ssh-hermes hand-off (KCA-1)</name>
  <files>deploy/aliyun/systemd/omnigraph-kol-scan-alert.service</files>
  <read_first>
    - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service (the no-op ExecStart to replace)
    - deploy/aliyun/systemd/omnigraph-kol-scan.service (confirm OnFailure= still points here)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (ssh hermes stanza details; ALIYUN_TO_HERMES_OK live evidence; the stale-flag breadcrumb history)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Hop ①②: keep touching the stale flag too, as a breadcrumb)
  </read_first>
  <action>
    Edit `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service`. Keep `Type=oneshot`, `User=root`.
    Replace the single no-op ExecStart with TWO ExecStart lines (systemd runs them in order; oneshot
    supports multiple ExecStart):

    1. Breadcrumb (keep): `ExecStart=/bin/bash -c 'mkdir -p /root/.hermes && date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ > /root/.hermes/wechat-session-stale'`
    2. Hand-off (new): an ExecStart that ssh-es to Hermes and launches the refresh wrapper DETACHED so
       the oneshot returns promptly (level-C polling can take ~5min — never block the unit on it):
       `ExecStart=/bin/bash -c 'ssh -o BatchMode=yes -o ConnectTimeout=20 hermes "cd ~/OmniGraph-Vault && nohup python3 scripts/refresh_wechat_cookie.py >> ~/.hermes/kol-refresh.log 2>&1 &" || echo "kol-alert: ssh hermes hand-off failed" | systemd-cat -t kol-scan-alert'`
       Use `BatchMode=yes` (never prompt) and `ConnectTimeout=20` (don't hang the unit if Hermes
       is unreachable). The `|| ... systemd-cat` makes a failed hand-off visible in the journal
       instead of failing the oneshot silently.

    Add a `[Unit]` Description update: `Description=OmniGraph KOL scan failure alert (ssh-hermes
    refresh hand-off + stale breadcrumb)`. Do NOT add `[Install]` (it's OnFailure-triggered, no
    WantedBy needed). Preserve the `%%` escaping for systemd (literal `%` must be `%%` in unit files).

    Note: the Hermes-side `~/.ssh` / repo path and `python3` availability are assumed from RESEARCH.md
    (Hermes repo at ~/OmniGraph-Vault, system python3 + websocket-client). If the wrapper is not yet
    synced to Hermes, the hand-off logs a failure but the breadcrumb still fires — Plan 04 ensures the
    wrapper is present on Hermes; Plan 05 verifies the live fire.
  </action>
  <verify>
    <automated>grep -n "ssh.*hermes\|refresh_wechat_cookie.py\|wechat-session-stale" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "ExecStart=" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` returns 2.
    - `grep -n "ssh.*hermes" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` returns ≥ 1.
    - `grep -n "refresh_wechat_cookie.py" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` returns ≥ 1.
    - `grep -n "wechat-session-stale" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` returns ≥ 1 (breadcrumb preserved).
    - `grep -n "BatchMode=yes\|ConnectTimeout" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` returns ≥ 1 (non-blocking, non-prompting).
    - `grep -n "OnFailure=omnigraph-kol-scan-alert" deploy/aliyun/systemd/omnigraph-kol-scan.service` returns 1 (wiring intact, unchanged).
  </acceptance_criteria>
  <done>The alert unit fires the stale breadcrumb AND ssh-hermes-launches the refresh wrapper detached, non-blocking/non-prompting; the kol-scan OnFailure wiring is unchanged.</done>
</task>

<task type="auto">
  <name>Task 2: [ALIYUN-WRITE] Deploy updated alert unit to Aliyun + daemon-reload (KCA-1)</name>
  <files>scripts/deploy-aliyun-session-alert.sh</files>
  <read_first>
    - scripts/deploy-aliyun-session-alert.sh (the existing idempotent deploy script — scp unit + daemon-reload + enable)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (Aliyun new EIP 47.117.244.253; ssh alias aliyun-vitaclaw is STALE → explicit IP + key `~/.ssh/aliyun_orchestrator_ed25519` for now)
    - CLAUDE.md (Principle #5 Aliyun is agent-direct; Principle #7 PowerShell for databricks paths — N/A here, this is bash scp; #6 verify end-to-end real)
  </read_first>
  <action>
    Update `scripts/deploy-aliyun-session-alert.sh` so its `REMOTE` target works against the rebuilt
    Aliyun box. The current script hardcodes `REMOTE=aliyun-vitaclaw` (stale alias). Change it to read
    an overridable target: `REMOTE="${ALIYUN_SSH:-aliyun-vitaclaw}"` at the top, so the orchestrator
    can run `ALIYUN_SSH="-i ~/.ssh/aliyun_orchestrator_ed25519 -o IdentitiesOnly=yes root@47.117.244.253"`
    until the alias is repointed (Plan 04 / memory `aliyun_vitaclaw_ssh.md`). Keep the 4-step flow
    (scp alert unit, scp kol-scan unit, daemon-reload, enable). The script is idempotent — safe to
    re-run.

    Then DEPLOY (this is the [ALIYUN-WRITE] action — orchestrator runs it directly, has the key):
    - Run the deploy script against the live box. Because the working directory resets between Bash
      calls in this environment, run from an absolute path:
      `cd /c/Users/huxxha/Desktop/OmniGraph-Vault && ALIYUN_SSH="root@47.117.244.253" bash scripts/deploy-aliyun-session-alert.sh`
      (with the explicit key flags if the alias is not yet live).
    - The script scps the updated `omnigraph-kol-scan-alert.service` to `/etc/systemd/system/`, scps
      the (unchanged) kol-scan unit, runs `systemctl daemon-reload`, and `systemctl enable` the alert
      unit.

    Confirm the deployed unit on Aliyun matches the repo file:
    `ssh <target> "cat /etc/systemd/system/omnigraph-kol-scan-alert.service"` and diff against the
    repo template — they MUST be byte-identical for the ExecStart lines.
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault && grep -n "ALIYUN_SSH\|daemon-reload" scripts/deploy-aliyun-session-alert.sh</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "ALIYUN_SSH" scripts/deploy-aliyun-session-alert.sh` returns ≥ 1 (overridable target).
    - `grep -n "daemon-reload" scripts/deploy-aliyun-session-alert.sh` returns ≥ 1.
    - Live Aliyun check (orchestrator runs): `ssh <aliyun> "systemctl cat omnigraph-kol-scan-alert.service | grep -c ssh.*hermes"` returns ≥ 1 — the DEPLOYED unit (not just the repo file) contains the ssh-hermes hand-off.
    - Live Aliyun check: `ssh <aliyun> "systemctl show omnigraph-kol-scan-alert.service -p LoadState"` returns `LoadState=loaded` (daemon-reload picked it up).
  </acceptance_criteria>
  <done>The deploy script targets the live Aliyun box (overridable ALIYUN_SSH); the updated alert unit is deployed to /etc/systemd/system, daemon-reloaded, and the DEPLOYED unit contains the ssh-hermes hand-off.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: [ALIYUN-WRITE] Checkpoint — confirm OnFailure hand-off fires (KCA-1)</name>
  <files>deploy/aliyun/systemd/omnigraph-kol-scan-alert.service</files>
  <read_first>
    - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service (deployed version)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (the chain ②③ live-test evidence)
  </read_first>
  <action>
    Orchestrator (Aliyun-direct) manually fires the deployed alert unit to exercise the OnFailure
    handler path WITHOUT needing a real scan failure — automated work done before the human sign-off:
    `ssh <aliyun> "systemctl start omnigraph-kol-scan-alert.service"`. Then collect the breadcrumb
    timestamp, the Hermes kol-refresh.log tail, and the alert-unit journal, and present them to the
    human for confirmation that the trigger hop reached Hermes.
  </action>
  <what-built>
    The Aliyun alert unit now ssh-hands-off to Hermes to launch the refresh wrapper (KCA-1), in
    addition to the stale-flag breadcrumb. Deployed to /etc/systemd/system, daemon-reloaded.
  </what-built>
  <how-to-verify>
    The orchestrator triggers a manual fire of the alert unit on Aliyun (safe — it does not require an
    actual scan failure; we just exercise the OnFailure handler directly):
    1. `ssh <aliyun> "systemctl start omnigraph-kol-scan-alert.service"`
    2. Confirm the breadcrumb refreshed: `ssh <aliyun> "cat /root/.hermes/wechat-session-stale"` shows
       a current UTC timestamp.
    3. Confirm the hand-off reached Hermes: `ssh <aliyun> "ssh hermes 'tail -5 ~/.hermes/kol-refresh.log'"`
       — should show a recent wrapper-start log line (even if the wrapper then no-ops because the
       session is already valid, OR errors because the wrapper isn't synced yet — Plan 04 fixes that).
    4. Confirm no journal error from the hand-off:
       `ssh <aliyun> "journalctl -u omnigraph-kol-scan-alert.service -n 20 --no-pager"` — the
       `kol-scan-alert: ssh hermes hand-off failed` line should be ABSENT (or, if the wrapper is not
       yet on Hermes, present and explained — that is expected pre-Plan-04).

    Report: did the breadcrumb refresh + did the ssh hand-off reach Hermes (log line present)?
    "approved" if both, or describe what failed.
  </how-to-verify>
  <verify>
    <automated>ssh "$ALIYUN_SSH" "cat /root/.hermes/wechat-session-stale && ssh hermes 'tail -5 ~/.hermes/kol-refresh.log'"</automated>
  </verify>
  <resume-signal>Type "approved" or describe issues (e.g. ssh hand-off failed, breadcrumb stale)</resume-signal>
  <acceptance_criteria>
    - /root/.hermes/wechat-session-stale shows a fresh timestamp after the manual fire.
    - ~/.hermes/kol-refresh.log on Hermes shows a wrapper-start line OR a clear "wrapper not found" error (the ssh path itself works either way).
    - No silent failure: the journal either shows clean completion or the explicit hand-off-failed message.
  </acceptance_criteria>
  <done>A manual fire of the deployed alert unit refreshes the breadcrumb AND the ssh hand-off reaches Hermes (kol-refresh.log line present); no silent failure in the journal.</done>
</task>

</tasks>

<verification>
- `grep -c "ExecStart=" deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` → 2 (breadcrumb + hand-off).
- Live: deployed unit on Aliyun contains `ssh ... hermes ... refresh_wechat_cookie.py` (KCA-1).
- Live: manual `systemctl start omnigraph-kol-scan-alert.service` refreshes the breadcrumb AND reaches Hermes (kol-refresh.log line) — end-to-end real for the trigger hop (Principle #6).
</verification>

<success_criteria>
- The Aliyun alert unit is no longer a no-op: it ssh-hands-off to the Hermes refresh wrapper and keeps the breadcrumb (KCA-1).
- The deploy script works against the rebuilt Aliyun box; the deployed unit matches the repo template.
- A manual fire confirms the OnFailure → ssh hermes → wrapper-launch path reaches Hermes.
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-03-SUMMARY.md`
</output>
