---
phase: kol-cookie-autorefresh
plan: 05
type: execute
wave: 4
depends_on: [01, 02, 03, 04]
files_modified:
  - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md
autonomous: false
requirements: [KCA-9]
actor: ALIYUN-WRITE
must_haves:
  truths:
    - "Plan 05 branches on Plan 04's outcome: if Plan 04 EXECUTED → run the full live chain; if DEFERRED → write VERIFICATION.md marking live-verification blocked-on-operator/RO-window and close the phase as code-complete, runtime-verification-pending"
    - "When run live: the full option-A chain runs end-to-end against real infrastructure: Aliyun detect → ssh hermes → CDP refresh (level A live) → scp writeback → Aliyun single-account test scan returns ret=0"
    - "When run live: after the refresh, MAX(scanned_at) advances to today (proves the scan ran against a LIVE session) AND ret=0 across accounts (no ret=200003); a COUNT increase is confirmatory-if-present but NOT required (no KOL may have published since last scan)"
    - "The QR-capture + Telegram-send path (level C) is exercised at least once: a real image lands in Telegram if hermes send --image is supported, else the QR png is produced at /tmp and its path is sent as text"
    - "Evidence is cited in VERIFICATION.md (Principle #6): commands run, exit codes, scan deltas, screenshot/Telegram confirmation; deferred items recorded explicitly"
  artifacts:
    - path: ".planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md"
      provides: "End-to-end real verification evidence per Principle #6 (or the blocked-on-operator branch record)"
      contains: "ret=0"
  key_links:
    - from: "Aliyun omnigraph-kol-scan-alert.service fire"
      to: "Aliyun kol_config.py refreshed + test-scan ret=0"
      via: "ssh hermes → refresh_wechat_cookie.py → scp writeback → batch_scan_kol.py --account"
      pattern: "ret=0"
---

<objective>
Prove the self-healing chain works end-to-end against real infrastructure (Principle #6 — green unit
tests are necessary but NOT sufficient), OR — if the Hermes operator steps (Plan 04) are deferred —
record the live-verification items as blocked-on-operator and close the phase as code-complete,
runtime-verification-pending.

BRANCH ON PLAN 04 OUTCOME (WARNING 4 — read the Plan 04 SUMMARY first):
- **Plan 04 EXECUTED** (wrapper synced to Hermes, env creds set, alias repointed, --image capability
  recorded): run the FULL live chain — Aliyun detect → ssh hermes → CDP refresh (level A live) → scp
  writeback → Aliyun single-account test scan ret=0 → confirm MAX(scanned_at) advances; and exercise
  the level-C QR-capture + Telegram-send path at least once. Phase closes as fully complete.
- **Plan 04 DEFERRED** (operator deferred to post-2026-06-22, Hermes RO window still open — today is
  2026-06-19, ~3 days left): the live chain CANNOT run (no wrapper on Hermes, no env creds, alias
  unresolved). Write VERIFICATION.md marking A/B/C live-verification as "blocked on operator/RO-window,
  scheduled post-2026-06-22", record what IS verifiable now (Plan 01/02/03 code + unit tests + the
  Aliyun trigger deploy + the rollback unit test), and close the phase as **code-complete,
  runtime-verification-pending** (NOT fully complete).

Purpose: This is the gate that closes the phase. The chain's individual hops are already GREEN
(RESEARCH.md); this plan runs them as ONE flow when Plan 04 has executed, or honestly records the
runtime-pending state when it hasn't. The writeback ret=0 + scan-recency delta is the load-bearing
proof the cookie is genuinely recovered when live.

Output: kol-cookie-autorefresh-VERIFICATION.md with cited evidence (live branch) OR the blocked-on-
operator branch record (deferred branch); phase marked complete only after the chain demonstrably
recovers the cookie (live branch), else marked code-complete/runtime-verification-pending.

Actor: [ALIYUN-WRITE] + [HERMES read] — orchestrator drives the live test directly via the Aliyun key
and ssh-hermes (read/execute is allowed; this exercises already-deployed artifacts, no new Hermes
write). Depends on ALL prior plans; the live branch additionally requires Plan 04 to have EXECUTED.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-04-SUMMARY.md
@batch_scan_kol.py
@scripts/refresh_wechat_cookie.py

<interfaces>
<!-- READ FIRST: the Plan 04 SUMMARY's EXECUTED-vs-DEFERRED line + the --image capability result.
     This plan branches on both (WARNING 4 + WARNING 3). -->

<!-- The chain to exercise (RESEARCH.md "POST-P0 end-to-end verification" — hops already individually
     GREEN; this plan runs them as ONE flow — LIVE BRANCH ONLY). -->
Aliyun: systemctl start omnigraph-kol-scan-alert.service       (hop ①② trigger)
  → ssh hermes "python3 ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py"  (hop ③ CDP refresh)
  → wrapper scp kol_config.py back to Aliyun + atomic write     (hop ④ writeback)
  → Aliyun: venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1  → ret=0  (verify)

<!-- Recovery proof (WARNING 2 — the cookie is REALLY recovered, not a stale dashboard read).
     The RELIABLE signal is scan RECENCY + ret=0, NOT a row-count increase: a healthy cookie can
     legitimately yield ZERO new articles if no KOL published since the last scan, so a COUNT
     increase must be treated as confirmatory-if-present, never mandatory. -->
Before: ssh aliyun "cd /root/OmniGraph-Vault && sqlite3 data/kol_scan.db 'SELECT MAX(scanned_at), COUNT(*) FROM articles'"
  (currently MAX ~2026-06-10 — dead 7+ days)
After a full refresh + scan: MAX(scanned_at) ADVANCES to today (the scan ran against a LIVE session)
  AND the scan reports ret=0 across accounts (no ret=200003). New rows MAY appear (confirmatory) but
  their absence does NOT fail the criterion if MAX advanced + ret=0.

<!-- Level-C QR→Telegram (mandatory single exercise — capability-gated per Plan 02/04, WARNING 3). -->
On Hermes: python3 scripts/refresh_wechat_cookie.py --level C   (or the QR-capture function directly)
  → canvas toDataURL → /tmp/wx_qr_code.png →
     IF `hermes send --image` supported (Plan 04 STEP D result): hermes send -t telegram --image ...
       → user sees the QR image in Telegram.
     ELSE: /tmp/wx_qr_code.png is produced AND its path is sent as text via hermes send -t telegram.
  (The full human-scan completion is dry-run/manual-confirm; the png production + a send are real.)

<!-- Aliyun ssh target (orchestrator-direct): root@47.117.244.253 + ~/.ssh/aliyun_orchestrator_ed25519
     -o IdentitiesOnly=yes  (alias aliyun-vitaclaw stale until Plan 04). -->
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: [ALIYUN-WRITE] Branch on Plan 04, then (live) trigger → refresh → writeback → ret=0 → scan-recency delta (KCA-9)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-04-SUMMARY.md (FIRST — the EXECUTED-vs-DEFERRED outcome + --image capability result; this decides the branch)
    - scripts/refresh_wechat_cookie.py (the wrapper being exercised — esp. STEP 4 writeback + verify)
    - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service (the deployed trigger)
    - batch_scan_kol.py (the verify scan + the daily scan that produces new articles)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (POST-P0 chain evidence — the hops are individually GREEN; this runs them as one flow)
  </read_first>
  <action>
    STEP 0 — BRANCH (WARNING 4): read the Plan 04 SUMMARY.
    - If Plan 04 = DEFERRED (Hermes RO until 2026-06-22, operator steps not run): DO NOT attempt the
      live chain (the wrapper is not on Hermes, env creds unset, alias unresolved). Skip to Task 3 and
      write VERIFICATION.md in the DEFERRED branch: mark A/B/C live-verification "blocked on
      operator/RO-window, scheduled post-2026-06-22"; cite what IS verified now (Plan 01 hygiene grep,
      Plan 02 unit tests incl. the rollback test, Plan 03 deployed Aliyun trigger + manual-fire
      checkpoint); set phase status = code-complete, runtime-verification-pending. Tell the human the
      live verification is scheduled for after 2026-06-22 and ask them to confirm the deferred close.
    - If Plan 04 = EXECUTED: proceed with the live chain below.

    LIVE BRANCH — Orchestrator drives the live A-level chain directly (Aliyun-direct + ssh-hermes
    execute — exercises already-deployed artifacts, no new Hermes write): take the BEFORE sqlite
    snapshot (MAX(scanned_at) + COUNT), fire the alert unit, confirm the hand-off reached Hermes,
    confirm the wrapper's writeback + its own test-scan ret=0, re-run an independent single-account
    test scan + a small real scan, take the AFTER snapshot, and confirm the Telegram summary. Capture
    every command + output for VERIFICATION.md (Task 3). Then present the ret=0 + scan-recency-delta
    evidence to the human for sign-off.
  </action>
  <what-built>
    Full option-A chain: Aliyun alert unit (Plan 03) ssh-hands-off to the Hermes refresh wrapper
    (Plan 02), which does a level-A CDP refresh (root-nav token + cookie extract), scps the result
    back to Aliyun atomically, and verifies with a single-account test scan (ret=0). (Live branch only;
    if Plan 04 deferred, this is recorded as runtime-pending.)
  </what-built>
  <how-to-verify>
    FIRST confirm the branch (Plan 04 SUMMARY). If DEFERRED → see Task 3 deferred branch; no live run.

    If EXECUTED, orchestrator drives this live (Aliyun-direct + ssh-hermes execute; safe — exercises
    deployed artifacts). Steps + evidence to capture into VERIFICATION.md:

    1. BEFORE snapshot: `ssh <aliyun> "cd /root/OmniGraph-Vault && python3 -c \"import sqlite3;print(sqlite3.connect('data/kol_scan.db').execute('SELECT MAX(scanned_at), COUNT(*) FROM articles').fetchone())\""`
       — record the stale MAX(scanned_at) (~2026-06-10) + row count.
    2. TRIGGER: `ssh <aliyun> "systemctl start omnigraph-kol-scan-alert.service"`. Confirm the
       breadcrumb refreshed AND the hand-off reached Hermes (`ssh <aliyun> "ssh hermes 'tail -20 ~/.hermes/kol-refresh.log'"`).
    3. WRAPPER RAN (level A): the log should show root-nav → token extracted → cookies extracted
       (all 5 critical present) → writeback. If the session is already valid, level A is the expected
       path. Capture the wrapper's exit code from the log.
    4. WRITEBACK + VERIFY: confirm the wrapper's own single-account test scan returned ret=0 (in the
       log), AND independently re-run on Aliyun:
       `ssh <aliyun> "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1; echo EXIT=$?"`
       — expect `EXIT=0` and `Scan complete: 1 ok, 0 failed`.
    5. SCAN-RECENCY DELTA (the real proof — WARNING 2): run a small real scan
       `ssh <aliyun> "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --daily"`
       (or wait for the next scheduled scan), then re-take the AFTER snapshot from step 1. The PASS
       signal is: MAX(scanned_at) ADVANCES past 2026-06-10 to today (the scan ran against a LIVE
       session) AND the scan reported ret=0 across accounts (no ret=200003). A COUNT increase is
       confirmatory-if-present but is NOT required — if no KOL published since the last scan, COUNT can
       legitimately stay flat on a fully-recovered cookie. Record both the MAX delta and whether COUNT
       moved.
    6. NOTIFY: confirm a Telegram summary message was sent by the wrapper (KCA-5) — check the chat.

    Report: did ret=0 AND did MAX(scanned_at) advance to today (with no ret=200003)? "approved" if
    both, else describe the failure point. (COUNT movement is noted but not gating.)
  </how-to-verify>
  <verify>
    <automated>ssh "$ALIYUN_SSH" "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1; echo EXIT=$?"</automated>
  </verify>
  <resume-signal>Type "approved" (ret=0 + MAX advanced), "deferred-close" (Plan 04 deferred → runtime-pending), or describe the failure point</resume-signal>
  <acceptance_criteria>
    - BRANCH recorded: VERIFICATION.md states whether Plan 04 was EXECUTED (live chain ran) or DEFERRED (runtime-pending close).
    - LIVE branch: the single-account test scan returns `EXIT=0` (ret=0) post-writeback — captured in VERIFICATION.md.
    - LIVE branch: MAX(scanned_at) in kol_scan.db ADVANCES past 2026-06-10 to today after the post-refresh real scan, AND the scan reports ret=0 (no ret=200003) — captured with before/after values. COUNT delta recorded as confirmatory (not gating).
    - LIVE branch: the kol-refresh.log on Hermes shows the level-A path: root-nav, 5 critical cookies present, atomic writeback, ret=0 verify.
    - LIVE branch: a Telegram success summary was received (KCA-5).
    - DEFERRED branch: VERIFICATION.md marks A/B/C live-verification blocked-on-operator/RO-window, scheduled post-2026-06-22, and the phase is closed as code-complete/runtime-verification-pending (NOT fully complete).
  </acceptance_criteria>
  <done>EITHER the live A-level chain ran end-to-end (test-scan ret=0 post-writeback, MAX(scanned_at) advanced past 2026-06-10 with ret=0 across accounts, Hermes log shows the level-A path with 5 critical cookies, Telegram summary received — COUNT delta recorded but not gating) OR, if Plan 04 deferred, the deferred branch is recorded (live-verification blocked-on-operator, phase code-complete/runtime-verification-pending) — all captured for VERIFICATION.md.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: [HERMES read] Level-C QR-capture + capability-gated Telegram delivery real exercise (KCA-9, KCA-3, KCA-5)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-04-SUMMARY.md (the --image capability result from STEP D — gates the acceptance below)
    - scripts/refresh_wechat_cookie.py (the level-C branch: canvas toDataURL → /tmp/wx_qr_code.png → capability-gated hermes send)
    - skills/omnigraph_scan_kol/SKILL.md (QR Code Login Flow Q2 — canvas toDataURL primary, ~10KB PNG; the Page.captureScreenshot freeze pitfall to avoid)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Verification note: level C QR-capture + Telegram-send MUST be exercised at least once with a real test image; full human-scan loop can be dry-run/manual-confirm)
  </read_first>
  <action>
    Branch note: this task only runs in the LIVE branch (Plan 04 EXECUTED). If Plan 04 DEFERRED, skip
    and record in VERIFICATION.md as part of the runtime-pending deferral.

    Orchestrator (Hermes read/execute) drives the wrapper's level-C QR-capture path: navigate the
    :9222 Edge tab to a login state (or use any page carrying the QR <img>), run the level-C branch so
    it captures the QR via canvas toDataURL to /tmp/wx_qr_code.png and delivers it via the
    capability-gated notify path (--image if Plan 04 STEP D recorded support, else text + /tmp path).
    Confirm the file size (canvas output, not a multi-MB screenshot) and the Telegram delivery
    (image OR text-with-path depending on capability), then present to the human for sign-off.
  </action>
  <what-built>
    The level-C branch of the wrapper: when cookies are truly dead, it captures the WeChat MP login QR
    via canvas toDataURL (no screenshot freeze), saves /tmp/wx_qr_code.png, and delivers it to the user
    via `hermes send -t telegram` — as an image if `--image` is supported, otherwise as text carrying
    the /tmp path (capability-gated, WARNING 3 / Plan 02 notify_image).
  </what-built>
  <how-to-verify>
    True cookie death is hard to force on demand, so exercise the QR-capture + delivery path directly
    (the png production + a real send must happen; the full human-scan completion is dry-run/manual-confirm):

    1. On Hermes, drive the wrapper's QR-capture function against the live Edge login page. Either:
       (a) `ssh hermes "cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --level C"`
       after navigating the :9222 Edge tab to a logout/login state; OR
       (b) call the QR-capture function in isolation against the current page if a QR <img> is present.
    2. Confirm `/tmp/wx_qr_code.png` was created on Hermes and is a valid PNG ~8-14KB (canvas toDataURL
       output, NOT a multi-MB screenshot):
       `ssh hermes "ls -la /tmp/wx_qr_code.png && file /tmp/wx_qr_code.png"`.
    3. Confirm Telegram delivery, gated on the Plan 04 STEP D `--image` capability:
       - If `--image` SUPPORTED: the user sees the QR image (or a clearly-labeled test image) in the
         configured Telegram chat.
       - If `--image` NOT supported: the user receives a text message carrying the `/tmp/wx_qr_code.png`
         path (and the png exists on Hermes for the operator to open). Either outcome PASSES — the
         capability gate is the contract, not a mandatory image.
    4. If a live QR was available, optionally complete the two-phone scan (SKILL.md note: WeChat QR
       can't be scanned from a screenshot — use a second phone) to confirm the resume → re-extract →
       CSRF-rebind path. This is OPTIONAL (dry-run acceptable).

    Report: was /tmp/wx_qr_code.png produced AND delivered per the capability gate (image if supported,
    else text+path)? "approved" if yes.
  </how-to-verify>
  <verify>
    <automated>ssh hermes "ls -la /tmp/wx_qr_code.png && file /tmp/wx_qr_code.png"</automated>
  </verify>
  <resume-signal>Type "approved" (QR png produced + delivered per capability gate) or describe issues</resume-signal>
  <acceptance_criteria>
    - /tmp/wx_qr_code.png exists on Hermes and is a valid PNG of canvas-toDataURL size (≤ ~50KB, not a multi-MB screenshot).
    - Delivery satisfies the capability gate: a real image delivered to Telegram IF `hermes send --image` is supported (Plan 04 STEP D); OTHERWISE the QR png is produced at /tmp AND its path is sent as text via `hermes send -t telegram` (KCA-5). Either outcome passes.
    - VERIFICATION.md cites the file size + which delivery path was taken (image vs text+path) + the Plan 04 capability result (Principle #6).
  </acceptance_criteria>
  <done>The level-C QR-capture path produced a canvas-sized /tmp/wx_qr_code.png on Hermes and delivered it per the Plan 04 `--image` capability gate (image if supported, else text carrying the /tmp path); evidence + which path was taken captured for VERIFICATION.md.</done>
</task>

<task type="auto">
  <name>Task 3: [REPO-CODE] Write VERIFICATION.md with cited end-to-end evidence (or the deferred-branch record) (KCA-9)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-04-SUMMARY.md (EXECUTED vs DEFERRED — which branch to document)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Verification section — what end-to-end real means here)
    - CLAUDE.md (Principle #6 — cite launcher, env, command outputs, exit codes, deltas, screenshots/Telegram confirmation; green tests insufficient)
  </read_first>
  <action>
    Create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md`. The
    content depends on the Plan 04 branch (WARNING 4):

    DEFERRED branch (Plan 04 not executed, Hermes RO until 2026-06-22):
    - State clearly at the top: **Phase status: code-complete, runtime-verification-pending.**
    - Section "What IS verified now": Plan 01 hygiene (grep 0×9223 in the 5 files, no leaked secret),
      Plan 02 unit tests green incl. the rollback-on-bad-creds test, Plan 03 deployed Aliyun trigger +
      manual-fire checkpoint (breadcrumb + ssh hand-off reached Hermes).
    - Section "Blocked on operator / RO-window": A/B/C live-verification, the writeback ret=0 + scan-
      recency delta, the level-C QR→Telegram exercise — all "scheduled post-2026-06-22 once Plan 04
      operator steps run (wrapper synced, env creds, alias repointed, --image capability)".
    - Requirement coverage table KCA-1..KCA-9 with status (code-complete / runtime-pending) per req.
    - Residual/deferred: password rotation status, git-history scrub decision.

    LIVE branch (Plan 04 executed): document the live end-to-end run (Principle #6). Include sections:
    1. **Chain exercised** — the full hop list (① detect/trigger → ② ssh hermes → ③ CDP level-A refresh
       → ④ atomic writeback → verify ret=0 → scan-recency delta → ⑤ Telegram notify).
    2. **A-level evidence** (from Task 1): before/after MAX(scanned_at) + COUNT, the `EXIT=0` test-scan
       output, the kol-refresh.log excerpt (root-nav token, 5 critical cookies present, atomic write),
       the Telegram summary confirmation. State the PASS basis as MAX advanced + ret=0 (COUNT noted as
       confirmatory, not gating — WARNING 2).
    3. **C-level evidence** (from Task 2): /tmp/wx_qr_code.png size + `file` type, which delivery path
       was taken (image vs text+path per the Plan 04 --image capability), and whether the full human-scan
       was completed or dry-run.
    4. **B-level note**: whether account-login was forceable; if not, mark as code-verified (grep gates
       from Plan 02) + reused-SKILL-logic, runtime-deferred to first natural occurrence.
    5. **Requirement coverage table**: KCA-1..KCA-9 each → where verified (plan + evidence).
    6. **Residual / deferred**: any operator step deferred (from Plan 04), password-rotation status
       (KCA-8), git-history scrub decision (CONTEXT deferred).

    Cite exact commands + outputs; do NOT paraphrase ("it worked"). Redact secret values (show only
    lengths / first-6-chars per the SKILL.md discipline).
  </action>
  <verify>
    <automated>grep -n "ret=0\|scanned_at\|KCA-9\|wx_qr_code.png\|runtime-verification-pending\|code-complete" .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md` exists.
    - The file states the branch explicitly: either live-evidence sections OR a "code-complete, runtime-verification-pending" header with the blocked-on-operator section (`grep -n "runtime-verification-pending\|code-complete\|ret=0" ...` returns ≥ 1 either way).
    - LIVE branch only: `grep -n "ret=0" ...VERIFICATION.md` ≥ 1 AND `grep -n "scanned_at" ...VERIFICATION.md` ≥ 1 (MAX-advance proof, WARNING 2) AND `grep -n "wx_qr_code.png" ...VERIFICATION.md` ≥ 1.
    - `grep -cE "KCA-[1-9]" ...VERIFICATION.md` returns ≥ 9 (all requirements in the coverage table, both branches).
    - `grep -ni "Hardun\|huhai" ...VERIFICATION.md` returns 0 (no leaked secret).
  </acceptance_criteria>
  <done>VERIFICATION.md documents the correct branch: LIVE → cites the A-level chain (ret=0 + MAX-advance scan-recency delta + Telegram, COUNT noted not gating), the C-level QR delivery per the --image capability gate, the B-level note, a KCA-1..9 coverage table, and residual/deferred items; DEFERRED → marks live-verification blocked-on-operator/RO-window with a code-complete/runtime-verification-pending header, what-is-verified-now, and the KCA coverage table; no leaked secret in either branch.</done>
</task>

</tasks>

<verification>
- Branch determined from Plan 04 SUMMARY (WARNING 4): LIVE chain run OR deferred runtime-pending close.
- LIVE branch: test-scan ret=0 post-writeback AND MAX(scanned_at) advances past 2026-06-10 with ret=0 across accounts (COUNT delta confirmatory, not gating — WARNING 2) (KCA-9, Principle #6).
- LIVE branch: level-C QR png produced AND delivered per the `hermes send --image` capability gate (image if supported, else text+path — WARNING 3) (KCA-3, KCA-5).
- DEFERRED branch: VERIFICATION.md marks live-verification blocked-on-operator/RO-window, phase code-complete/runtime-verification-pending, with KCA-1..9 coverage table.
- VERIFICATION.md cites all evidence; no secret leak (both branches).
</verification>

<success_criteria>
- LIVE: the self-healing chain demonstrably recovers the WeChat cookie end-to-end for level A (and B if forceable); ret=0 + MAX-advance prove genuine recovery; the level-C QR delivery is exercised per the capability gate.
- DEFERRED: the phase closes honestly as code-complete/runtime-verification-pending with the live items scheduled post-2026-06-22; no false "fully complete" claim.
- Evidence is cited per Principle #6 (not unit-test-only); operator-deferred items + password-rotation status recorded.
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-05-SUMMARY.md`
(state which branch was taken: LIVE fully-complete OR DEFERRED code-complete/runtime-verification-pending).
</output>
