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
    - "The full option-A chain runs end-to-end against real infrastructure: Aliyun detect → ssh hermes → CDP refresh (level A live) → scp writeback → Aliyun single-account test scan returns ret=0"
    - "After the refresh, a real Aliyun scan picks up new articles (the cookie is genuinely recovered, not just ret=0 on a stale read)"
    - "The QR-capture + Telegram-send path (level C) is exercised at least once with a real test image landing in Telegram"
    - "Evidence is cited in VERIFICATION.md (Principle #6): commands run, exit codes, scan deltas, screenshot/Telegram confirmation"
  artifacts:
    - path: ".planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md"
      provides: "End-to-end real verification evidence per Principle #6"
      contains: "ret=0"
  key_links:
    - from: "Aliyun omnigraph-kol-scan-alert.service fire"
      to: "Aliyun kol_config.py refreshed + test-scan ret=0"
      via: "ssh hermes → refresh_wechat_cookie.py → scp writeback → batch_scan_kol.py --account"
      pattern: "ret=0"
---

<objective>
Prove the self-healing chain works end-to-end against real infrastructure (Principle #6 — green unit
tests are necessary but NOT sufficient): exercise Aliyun detect → ssh hermes → CDP refresh (level A
path live) → scp writeback → Aliyun single-account test scan ret=0 → confirm a real scan picks up new
articles; and exercise the level-C QR-capture + Telegram-send path at least once with a real test
image. Cite all evidence in VERIFICATION.md.

Purpose: This is the gate that closes the phase. Level A (token/page stale) is forced and run live;
level B and C are exercised as far as is safe (C's QR→Telegram send is mandatory; the full human-scan
loop is a dry-run / manual-confirm since true cookie death is hard to force on demand — per CONTEXT
Verification note). The writeback ret=0 + new-article delta is the load-bearing proof the cookie is
genuinely recovered.

Output: kol-cookie-autorefresh-VERIFICATION.md with cited evidence; phase marked complete only after
the chain demonstrably recovers the cookie without manual intervention for A (and B if forceable).

Actor: [ALIYUN-WRITE] + [HERMES read] — orchestrator drives the live test directly via the Aliyun key
and ssh-hermes (read/execute is allowed; this exercises already-deployed artifacts, no new Hermes
write). Depends on ALL prior plans (01 hygiene, 02 wrapper, 03 trigger, 04 operator steps done or the
parts needed for A-level verified).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md
@batch_scan_kol.py
@scripts/refresh_wechat_cookie.py

<interfaces>
<!-- The chain to exercise (RESEARCH.md "POST-P0 end-to-end verification" — hops already individually
     GREEN; this plan runs them as ONE flow). -->
Aliyun: systemctl start omnigraph-kol-scan-alert.service       (hop ①② trigger)
  → ssh hermes "python3 ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py"  (hop ③ CDP refresh)
  → wrapper scp kol_config.py back to Aliyun + atomic write     (hop ④ writeback)
  → Aliyun: venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1  → ret=0  (verify)

<!-- New-article delta proof (the cookie is REALLY recovered, not a stale dashboard read). -->
Before: ssh aliyun "cd /root/OmniGraph-Vault && sqlite3 data/kol_scan.db 'SELECT MAX(scanned_at) FROM articles'"
  (currently 2026-06-10 — dead 7+ days)
After a full refresh + scan: MAX(scanned_at) advances to today; new rows appear.

<!-- Level-C QR→Telegram (mandatory single exercise). -->
On Hermes: python3 scripts/refresh_wechat_cookie.py --level C   (or the QR-capture function directly)
  → canvas toDataURL → /tmp/wx_qr_code.png → hermes send -t telegram → user sees the QR in Telegram.
  (The full human-scan completion is dry-run/manual-confirm; the SEND must be real.)

<!-- Aliyun ssh target (orchestrator-direct): root@47.117.244.253 + ~/.ssh/aliyun_orchestrator_ed25519
     -o IdentitiesOnly=yes  (alias aliyun-vitaclaw stale until Plan 04). -->
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: [ALIYUN-WRITE] Live A-level end-to-end: trigger → refresh → writeback → ret=0 → new-article delta (KCA-9)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - scripts/refresh_wechat_cookie.py (the wrapper being exercised — esp. STEP 4 writeback + verify)
    - deploy/aliyun/systemd/omnigraph-kol-scan-alert.service (the deployed trigger)
    - batch_scan_kol.py (the verify scan + the daily scan that produces new articles)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (POST-P0 chain evidence — the hops are individually GREEN; this runs them as one flow)
  </read_first>
  <action>
    Orchestrator drives the live A-level chain directly (Aliyun-direct + ssh-hermes execute — these
    exercise already-deployed artifacts, no new Hermes write): take the BEFORE sqlite snapshot, fire
    the alert unit, confirm the hand-off reached Hermes, confirm the wrapper's writeback + its own
    test-scan ret=0, re-run an independent single-account test scan + a small real scan, take the
    AFTER snapshot, and confirm the Telegram summary. Capture every command + output for VERIFICATION.md
    (Task 3). Then present the ret=0 + new-article-delta evidence to the human for sign-off.
  </action>
  <what-built>
    Full option-A chain: Aliyun alert unit (Plan 03) ssh-hands-off to the Hermes refresh wrapper
    (Plan 02), which does a level-A CDP refresh (root-nav token + cookie extract), scps the result
    back to Aliyun atomically, and verifies with a single-account test scan (ret=0).
  </what-built>
  <how-to-verify>
    Orchestrator drives this live (Aliyun-direct + ssh-hermes execute; safe — exercises deployed
    artifacts). Steps + evidence to capture into VERIFICATION.md:

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
    5. NEW-ARTICLE DELTA (the real proof): run a small real scan
       `ssh <aliyun> "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --daily"`
       (or wait for the next scheduled scan), then re-take the AFTER snapshot from step 1 — MAX(scanned_at)
       MUST advance past 2026-06-10 and COUNT must increase. This proves the cookie is genuinely
       recovered, not a stale ret=0.
    6. NOTIFY: confirm a Telegram summary message was sent by the wrapper (KCA-5) — check the chat.

    Report: did ret=0 AND did new articles appear (MAX advanced)? "approved" if both, else describe.
  </how-to-verify>
  <verify>
    <automated>ssh "$ALIYUN_SSH" "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --account 叶小钗 --max-articles 1; echo EXIT=$?"</automated>
  </verify>
  <resume-signal>Type "approved" (ret=0 + new articles) or describe the failure point</resume-signal>
  <acceptance_criteria>
    - The single-account test scan returns `EXIT=0` (ret=0) post-writeback — captured in VERIFICATION.md.
    - MAX(scanned_at) in kol_scan.db advances past 2026-06-10 after the post-refresh real scan; COUNT increases — captured with before/after values.
    - The kol-refresh.log on Hermes shows the level-A path: root-nav, 5 critical cookies present, atomic writeback, ret=0 verify.
    - A Telegram success summary was received (KCA-5).
  </acceptance_criteria>
  <done>The live A-level chain ran end-to-end: test-scan ret=0 post-writeback, MAX(scanned_at) advanced past 2026-06-10 with new rows, Hermes log shows the level-A path with 5 critical cookies, and a Telegram summary was received — all captured for VERIFICATION.md.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: [HERMES read] Level-C QR-capture + Telegram-send real exercise (KCA-9, KCA-3, KCA-5)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - scripts/refresh_wechat_cookie.py (the level-C branch: canvas toDataURL → /tmp/wx_qr_code.png → hermes send -t telegram)
    - skills/omnigraph_scan_kol/SKILL.md (QR Code Login Flow Q2 — canvas toDataURL primary, ~10KB PNG; the Page.captureScreenshot freeze pitfall to avoid)
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Verification note: level C QR-capture + Telegram-send MUST be exercised at least once with a real test image; full human-scan loop can be dry-run/manual-confirm)
  </read_first>
  <action>
    Orchestrator (Hermes read/execute) drives the wrapper's level-C QR-capture path: navigate the
    :9222 Edge tab to a login state (or use any page carrying the QR <img>), run the level-C branch so
    it captures the QR via canvas toDataURL to /tmp/wx_qr_code.png and sends it to Telegram via
    `hermes send -t telegram`. Confirm the file size (canvas output, not a multi-MB screenshot) and
    Telegram delivery, then present to the human for sign-off. The SEND must be real; the full
    human-scan completion is optional dry-run.
  </action>
  <what-built>
    The level-C branch of the wrapper: when cookies are truly dead, it captures the WeChat MP login QR
    via canvas toDataURL (no screenshot freeze), saves /tmp/wx_qr_code.png, and sends it to the user
    via `hermes send -t telegram`.
  </what-built>
  <how-to-verify>
    True cookie death is hard to force on demand, so exercise the QR-capture + send path directly
    (the SEND must be real; the full human-scan completion is dry-run/manual-confirm):

    1. On Hermes, drive the wrapper's QR-capture function against the live Edge login page. Either:
       (a) `ssh hermes "cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --level C"`
       after navigating the :9222 Edge tab to a logout/login state; OR
       (b) call the QR-capture function in isolation against the current page if a QR <img> is present.
    2. Confirm `/tmp/wx_qr_code.png` was created on Hermes and is a valid PNG ~8-14KB (canvas toDataURL
       output, NOT a multi-MB screenshot):
       `ssh hermes "ls -la /tmp/wx_qr_code.png && file /tmp/wx_qr_code.png"`.
    3. Confirm the image landed in Telegram — the user sees the QR image (or a clearly-labeled test
       image if no live QR was available) in the configured Telegram chat.
    4. If a live QR was available, optionally complete the two-phone scan (SKILL.md note: WeChat QR
       can't be scanned from a screenshot — use a second phone) to confirm the resume → re-extract →
       CSRF-rebind path. This is OPTIONAL (dry-run acceptable).

    Report: was a real image sent to Telegram from the wrapper's level-C path? "approved" if yes.
  </how-to-verify>
  <verify>
    <automated>ssh hermes "ls -la /tmp/wx_qr_code.png && file /tmp/wx_qr_code.png"</automated>
  </verify>
  <resume-signal>Type "approved" (QR/test image reached Telegram) or describe issues</resume-signal>
  <acceptance_criteria>
    - /tmp/wx_qr_code.png exists on Hermes and is a valid PNG of canvas-toDataURL size (≤ ~50KB, not a multi-MB screenshot).
    - A real image was delivered to the configured Telegram chat via `hermes send -t telegram` (KCA-5).
    - VERIFICATION.md cites the file size + Telegram-delivery confirmation (Principle #6).
  </acceptance_criteria>
  <done>The level-C QR-capture path produced a canvas-sized /tmp/wx_qr_code.png on Hermes and delivered a real image to the configured Telegram chat via hermes send; evidence captured for VERIFICATION.md.</done>
</task>

<task type="auto">
  <name>Task 3: [REPO-CODE] Write VERIFICATION.md with cited end-to-end evidence (KCA-9)</name>
  <files>.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</files>
  <read_first>
    - .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md (Verification section — what end-to-end real means here)
    - CLAUDE.md (Principle #6 — cite launcher, env, command outputs, exit codes, deltas, screenshots/Telegram confirmation; green tests insufficient)
  </read_first>
  <action>
    Create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md` documenting
    the live end-to-end run (Principle #6). Include sections:

    1. **Chain exercised** — the full hop list (① detect/trigger → ② ssh hermes → ③ CDP level-A refresh
       → ④ atomic writeback → verify ret=0 → new-article delta → ⑤ Telegram notify).
    2. **A-level evidence** (from Task 1): before/after MAX(scanned_at) + COUNT, the `EXIT=0` test-scan
       output, the kol-refresh.log excerpt (root-nav token, 5 critical cookies present, atomic write),
       the Telegram summary confirmation.
    3. **C-level evidence** (from Task 2): /tmp/wx_qr_code.png size + `file` type, Telegram-delivery
       confirmation, and whether the full human-scan was completed or dry-run.
    4. **B-level note**: whether account-login was forceable; if not, mark as code-verified
       (grep gates from Plan 02) + reused-SKILL-logic, runtime-deferred to first natural occurrence.
    5. **Requirement coverage table**: KCA-1..KCA-9 each → where verified (plan + evidence).
    6. **Residual / deferred**: any operator step deferred to post-2026-06-22 (from Plan 04), the
       password-rotation status (KCA-8), git-history scrub decision (CONTEXT deferred).

    Cite exact commands + outputs; do NOT paraphrase ("it worked"). Redact secret values (show only
    lengths / first-6-chars per the SKILL.md discipline).
  </action>
  <verify>
    <automated>grep -n "ret=0\|MAX(scanned_at)\|KCA-9\|wx_qr_code.png" .planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-VERIFICATION.md` exists.
    - `grep -n "ret=0" ...VERIFICATION.md` returns ≥ 1 (the writeback verify proof).
    - `grep -n "MAX(scanned_at)\|scanned_at" ...VERIFICATION.md` returns ≥ 1 (the new-article delta proof).
    - `grep -n "wx_qr_code.png" ...VERIFICATION.md` returns ≥ 1 (level-C evidence).
    - `grep -cE "KCA-[1-9]" ...VERIFICATION.md` returns ≥ 9 (all requirements in the coverage table).
    - `grep -ni "Hardun\|huhai" ...VERIFICATION.md` returns 0 (no leaked secret).
  </acceptance_criteria>
  <done>VERIFICATION.md cites the live A-level chain (ret=0 + new-article delta + Telegram), the C-level QR→Telegram exercise, the B-level note, a KCA-1..9 coverage table, and residual/deferred items; no leaked secret.</done>
</task>

</tasks>

<verification>
- Live A-level: test-scan ret=0 post-writeback AND MAX(scanned_at) advances past 2026-06-10 with new rows (KCA-9, Principle #6).
- Live C-level: real image delivered to Telegram from the wrapper's canvas-toDataURL path (KCA-3, KCA-5).
- VERIFICATION.md cites all evidence + a KCA-1..9 coverage table; no secret leak.
</verification>

<success_criteria>
- The self-healing chain demonstrably recovers the WeChat cookie end-to-end without manual intervention for level A (and B if forceable); ret=0 + new articles prove genuine recovery.
- The level-C QR→Telegram human-request path is exercised with a real image.
- Evidence is cited per Principle #6 (not unit-test-only); operator-deferred items + password-rotation status recorded.
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-05-SUMMARY.md`
</output>
