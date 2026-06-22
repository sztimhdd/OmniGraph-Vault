---
phase: kol-cookie-autorefresh
plan: 04
type: execute
wave: 3
depends_on: [02, 03]
files_modified:
  - .planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md
autonomous: false
requirements: [KCA-8, KCA-2, KCA-4]
actor: HERMES-WRITE-OPERATOR
must_haves:
  truths:
    - "An operator-channel deliverable (Hermes prompt) registers the refresh wrapper on Hermes, sets the env creds, and repoints the stale ssh alias"
    - "WECHAT_MP_ACCOUNT / WECHAT_MP_PASSWORD are added to ~/.hermes/.env on Hermes (operator-only; the rotated password)"
    - "The Hermes ssh alias vitaclaw-aliyun is repointed from the dead old IP to 47.117.244.253"
    - "The refresh wrapper script is present on Hermes at ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py"
    - "The operator records whether `hermes send --image` is supported on Hermes (the level-C QR delivery capability that Plan 02/05 gate on)"
  artifacts:
    - path: ".planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md"
      provides: "Paste-ready operator prompt for the Hermes-write steps (RO until 2026-06-22)"
      contains: "WECHAT_MP_ACCOUNT"
  key_links:
    - from: "Hermes ~/.hermes/.env"
      to: "scripts/refresh_wechat_cookie.py level-B account login"
      via: "WECHAT_MP_ACCOUNT / WECHAT_MP_PASSWORD env read at runtime"
      pattern: "WECHAT_MP_(ACCOUNT|PASSWORD)"
    - from: "Hermes ssh alias vitaclaw-aliyun"
      to: "Aliyun 47.117.244.253"
      via: "~/.ssh/config HostName update (writeback scp target)"
      pattern: "47.117.244.253"
---

<objective>
Produce the operator-channel deliverable for the Hermes-side writes that the orchestrator MUST NOT
do directly (Hermes is RO until 2026-06-22, per Principle #5): (1) ensure the Plan-02 refresh wrapper
is synced to Hermes, (2) add the rotated WeChat creds to ~/.hermes/.env as WECHAT_MP_ACCOUNT /
WECHAT_MP_PASSWORD, (3) repoint the stale Hermes ssh alias vitaclaw-aliyun → 47.117.244.253 (the
writeback scp target), (4) confirm whether `hermes send --image` is supported (the level-C QR
delivery capability Plan 02/05 gate on), and (5) register the wrapper for autostart/health-check if
desired.

Purpose: The wrapper SCRIPT (Plan 02) lives in the repo and syncs to Hermes via the existing channel,
but the secrets + alias repoint + the `--image` capability probe + any cron/systemd registration are
Hermes-side facts/writes that are operator-channel (RO window). This plan packages them as a single
paste-ready Hermes prompt so they can be executed by the user-as-operator OR deferred to
post-2026-06-22 as a clearly-grouped set.

Output: .planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md — a self-contained operator
prompt. The orchestrator does NOT ssh-write Hermes; it hands the prompt to the user.

Actor: [HERMES-WRITE-OPERATOR] — Hermes is RO until 2026-06-22. The orchestrator authors the prompt
(repo-code) but the EXECUTION of the prompt's steps is operator-channel. Depends on Plan 02 (the
wrapper to sync) and Plan 03 (the Aliyun trigger that ssh-launches it). The end-to-end live test
(Plan 05) cannot fully pass until these operator steps run — Plan 05 branches on this plan's
executed-vs-deferred outcome.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md

<interfaces>
<!-- Hermes facts (RESEARCH.md). The orchestrator does NOT have write authorization here until 6/22. -->
Hermes: ssh -p 49221 sztimhdd@ohca.ddns.net (host OH-Desktop, WSL2 Ubuntu 24.04)
Repo on Hermes: ~/OmniGraph-Vault  (system python3 + websocket-client for the wrapper; venv NOT used)
Env file: ~/.hermes/.env  (EnvironmentFile-style; daily-ingest reads it)
hermes CLI: ~/.local/bin/hermes  (send -t telegram — scriptable, no gateway needed)
STALE ssh alias on Hermes: vitaclaw-aliyun → 101.133.154.49 (DEAD). New EIP: 47.117.244.253.

<!-- The env vars the Plan-02 wrapper reads at runtime (KCA-8). -->
WECHAT_MP_ACCOUNT=<the rotated account id>
WECHAT_MP_PASSWORD=<the rotated password — set ONLY in ~/.hermes/.env, never in repo>

<!-- Sync channel: the wrapper script gets to Hermes via the existing repo sync (Hermes pulls main,
     or the user's existing install-for-hermes.sh path). Confirm presence, do not re-architect. -->

<!-- `hermes send --image` capability (WARNING 3 resolution). Plan 02's level-C QR notify is
     capability-gated: it sends the QR png via `--image` IF supported, else falls back to text +
     /tmp path. This plan's operator prompt probes the actual local hermes build so the capability
     is recorded (not assumed). Plan 05 Task 2 acceptance is gated on the SAME result. -->
hermes send --help    → look for an `--image` / `--photo` / `--attach` flag
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: [REPO-CODE] Author the Hermes operator prompt (KCA-8, KCA-2, KCA-4)</name>
  <files>.planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md</files>
  <read_first>
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (Hermes facts: repo path, env file, hermes CLI, stale alias + new EIP, system-python3 requirement)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Channel discipline: Hermes-write = operator-channel; #58 env wiring + rotation note)
    - scripts/refresh_wechat_cookie.py (the wrapper — to state its dependencies: system python3 + websocket-client; the env vars it reads; the capability-gated --image notify)
    - CLAUDE.md (Principle #5 — never outsource SSH the agent can do, but Hermes WRITE ops are the operator's channel; convert to a Hermes/operator prompt, do NOT ask the user to paste raw ssh)
  </read_first>
  <action>
    Write `.planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md` — a self-contained,
    paste-ready prompt for the user-as-operator (or for post-6/22 execution). It MUST contain, as
    explicit numbered operator steps (each with a copy-paste command and an expected-result line):

    STEP A — Sync the wrapper to Hermes:
    - Pull latest main into ~/OmniGraph-Vault on Hermes (or run the existing install path) so
      `scripts/refresh_wechat_cookie.py` + `scripts/lib/cdp_client.py` are present.
    - Verify: `python3 -c "import websocket; print('ws ok')"` (system python3 has websocket-client;
      if missing, `pip install --user websocket-client`).
    - Verify: `python3 scripts/refresh_wechat_cookie.py --dry-run` runs without ImportError (it will
      connect to :9222, do A/B/C detect, and print the would-be writeback WITHOUT touching Aliyun).
      (The pinned sys.path import from Plan 02 means this resolves lib/cdp_client.py from the repo root.)

    STEP B — Add the rotated WeChat creds to ~/.hermes/.env (KCA-8):
    - First ROTATE the WeChat account password (the old one was public in the repo — ISSUES #58).
    - Append `WECHAT_MP_ACCOUNT=<rotated account>` and `WECHAT_MP_PASSWORD=<rotated password>` to
      `~/.hermes/.env` (operator enters the real values; the prompt uses placeholders).
    - Verify: `grep -c WECHAT_MP_ ~/.hermes/.env` returns 2. Do NOT echo the password back.
    - Update the Edge saved credentials in the `C:\Edge-Auto-Profile` profile to match the rotated
      password (so the B-level browser-saved-login path stays consistent).

    STEP C — Repoint the stale Hermes ssh alias (KCA-4 writeback target):
    - Edit `~/.ssh/config` on Hermes: change the `vitaclaw-aliyun` stanza HostName from
      `101.133.154.49` to `47.117.244.253` (keep port/user/key). Back up first
      (`cp ~/.ssh/config ~/.ssh/config.bak-pre-kca`).
    - Verify: `ssh vitaclaw-aliyun "hostname"` returns the Aliyun hostname (iZj1imk39yc55iZ).

    STEP D — Probe `hermes send --image` capability (WARNING 3 — level-C QR delivery):
    - Run `hermes send --help` (or `hermes send -t telegram --help`) and record whether an `--image`
      (or `--photo` / `--attach`) flag exists.
    - Verify by sending a real test image if supported:
      `hermes send -t telegram --image /tmp/test.png "kca capability probe"` — confirm it lands in the
      chat. If `--image` is NOT supported, record that the wrapper will fall back to text + the
      /tmp/wx_qr_code.png path (Plan 02 handles this gracefully).
    - Record the result (supported / not-supported) in the Plan 04 SUMMARY — Plan 05 Task 2 acceptance
      branches on it.

    STEP E (optional, operator decision) — Autostart for the headed CDP Edge:
    - Note that there is currently NO autostart task for the :9222 headed Edge (RESEARCH.md). The
      wrapper self-heals it (Plan 02 STEP 0), but a Windows Task Scheduler entry to launch Edge on
      logon with the `C:\Edge-Auto-Profile` profile + `--remote-debugging-port=9222` would reduce the
      self-heal dependency. Provide the Start-Process command; mark as optional.

    The prompt MUST be explicitly framed: "These are Hermes-WRITE operator-channel steps. Hermes is RO
    until 2026-06-22 — execute now only with explicit write authorization, otherwise run on/after
    2026-06-22." Do NOT include the orchestrator running any of these — they are operator steps.

    Use placeholders for the real account/password (NEVER write the rotated secret into this file or
    any repo file — memory `feedback_no_literal_secrets_in_prompts.md`).
  </action>
  <verify>
    <automated>grep -n "WECHAT_MP_ACCOUNT\|47.117.244.253\|RO until 2026-06-22\|refresh_wechat_cookie.py\|--image" .planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md` exists.
    - `grep -c "STEP " .planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md` returns ≥ 4 (A/B/C/D, E optional).
    - `grep -n "WECHAT_MP_ACCOUNT" ...PROMPT.md` AND `grep -n "WECHAT_MP_PASSWORD" ...PROMPT.md` each return ≥ 1.
    - `grep -n "47.117.244.253" ...PROMPT.md` returns ≥ 1 (alias repoint target).
    - `grep -n "RO until 2026-06-22\|read-only until\|2026-06-22" ...PROMPT.md` returns ≥ 1 (RO framing).
    - `grep -n "\-\-image\|hermes send --help" ...PROMPT.md` returns ≥ 1 (the --image capability probe — WARNING 3).
    - `grep -ni "Hardun\|huhai" ...PROMPT.md` returns 0 (no real secret in the prompt — placeholders only).
    - `grep -n "rotate\|ROTATE" ...PROMPT.md` returns ≥ 1 (password rotation step).
  </acceptance_criteria>
  <done>A paste-ready Hermes operator prompt exists with steps A-E, env-cred wiring (placeholders), alias repoint to 47.117.244.253, the `hermes send --image` capability probe (WARNING 3), RO-window framing, and a rotation step; no real secret in the file.</done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 2: [HERMES-WRITE-OPERATOR] Execute the Hermes operator prompt (or defer past 6/22)</name>
  <files>.planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md</files>
  <read_first>
    - .planning/phases/kol-cookie-autorefresh/HERMES-OPERATOR-PROMPT.md (the prompt just authored)
  </read_first>
  <action>
    The orchestrator hands HERMES-OPERATOR-PROMPT.md to the user-as-operator (does NOT ssh-write
    Hermes during the RO window — Principle #5). Automated work the orchestrator CAN do beforehand:
    confirm the wrapper is committed + pushed so a Hermes `git pull` will land it, and surface the
    prompt path to the user. The human then executes steps A-D (E optional) on Hermes OR records an
    explicit "deferred to post-2026-06-22" decision.

    IMPORTANT — record the executed-vs-deferred outcome explicitly in the Plan 04 SUMMARY, because
    Plan 05 BRANCHES on it: if this plan's steps EXECUTED → Plan 05 runs the full live chain; if
    DEFERRED → Plan 05 records the live-verification items as blocked-on-operator/RO-window and the
    phase closes as code-complete, runtime-verification-pending (NOT fully complete). Also record the
    STEP D `--image` capability result (supported / not).
  </action>
  <what-built>
    The operator prompt (Task 1) packages the five Hermes-write/probe steps: sync wrapper, add rotated
    env creds, repoint ssh alias, probe `hermes send --image`, optional Edge autostart. These are
    operator-channel (Hermes RO until 2026-06-22).
  </what-built>
  <how-to-verify>
    Operator executes HERMES-OPERATOR-PROMPT.md steps A-D (E optional) on Hermes, OR explicitly defers
    them to post-2026-06-22. After execution, confirm on Hermes:
    1. `ls ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py` exists (wrapper synced).
    2. `grep -c WECHAT_MP_ ~/.hermes/.env` returns 2 (env creds set; do not echo values).
    3. `ssh vitaclaw-aliyun "hostname"` returns the Aliyun hostname (alias repointed).
    4. `python3 ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py --dry-run` runs without ImportError.
    5. STEP D result recorded: is `hermes send --image` supported? (yes/no)

    Report which steps were executed vs deferred, and the --image capability result. "approved" if A-D
    done (or a clear "deferred to 6/22" decision recorded).
  </how-to-verify>
  <verify>
    <automated>ssh hermes "ls ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py && grep -c WECHAT_MP_ ~/.hermes/.env"</automated>
  </verify>
  <resume-signal>Type "approved" (steps done), "deferred" (post-6/22), or describe issues</resume-signal>
  <acceptance_criteria>
    - Either: all of (wrapper present, env creds=2, alias resolves to Aliyun, --dry-run imports clean, --image capability recorded) are confirmed on Hermes; OR an explicit "deferred to post-2026-06-22" decision is recorded in the Plan 04 SUMMARY.
    - The Plan 04 SUMMARY explicitly states EXECUTED or DEFERRED (Plan 05 reads this to choose its branch) and records the STEP D `--image` capability result.
  </acceptance_criteria>
  <done>The operator either executed steps A-D on Hermes (wrapper present, env creds=2, alias resolves, --dry-run clean, --image capability recorded) OR recorded an explicit deferral to post-2026-06-22 in the Plan 04 SUMMARY; the executed/deferred outcome is stated explicitly for Plan 05's branch.</done>
</task>

</tasks>

<verification>
- HERMES-OPERATOR-PROMPT.md exists with steps A-E, env wiring (KCA-8), alias repoint (KCA-4), `--image` capability probe (WARNING 3), RO framing, rotation step, no real secret.
- Operator checkpoint records execution (steps A-D confirmed on Hermes) OR an explicit deferral to post-2026-06-22; the executed/deferred outcome + `--image` result are recorded in the SUMMARY for Plan 05's branch.
</verification>

<success_criteria>
- The Hermes-write deliverable is a single clean operator prompt; the orchestrator never ssh-writes Hermes during the RO window (Principle #5).
- Env creds (KCA-8 Hermes side), wrapper presence (supports KCA-2), writeback alias (KCA-4), and the `--image` capability fact are either applied/recorded or clearly deferred as a grouped set, with the outcome stated for Plan 05.
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-04-SUMMARY.md`
(record whether the operator steps were executed or DEFERRED to post-2026-06-22, AND the STEP D
`hermes send --image` capability result — Plan 05 branches on both).
</output>
