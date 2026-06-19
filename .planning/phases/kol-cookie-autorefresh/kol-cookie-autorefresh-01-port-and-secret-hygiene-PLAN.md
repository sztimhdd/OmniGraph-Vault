---
phase: kol-cookie-autorefresh
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - config.py
  - CLAUDE.md
  - skills/omnigraph_scan_kol/SKILL.md
  - skills/wechat-cdp-credential-refresh/SKILL.md
  - scripts/capture_qr.py
autonomous: true
requirements: [KCA-7, KCA-8]
actor: REPO-CODE
must_haves:
  truths:
    - "Every canonical project file references CDP port 9222, not 9223"
    - "SKILL.md contains no literal WeChat account or password"
    - "The B-level account-login flow documents reading creds from env vars, not literals"
  artifacts:
    - path: "config.py"
      provides: "CDP_URL default standardized on 9222"
      contains: "9222"
    - path: "skills/omnigraph_scan_kol/SKILL.md"
      provides: "Account-Login-Fallback section with env placeholders, no literals"
      contains: "WECHAT_MP_ACCOUNT"
  key_links:
    - from: "skills/omnigraph_scan_kol/SKILL.md Account-Login-Fallback"
      to: "~/.hermes/.env"
      via: "env placeholder ${WECHAT_MP_ACCOUNT} / ${WECHAT_MP_PASSWORD}"
      pattern: "WECHAT_MP_(ACCOUNT|PASSWORD)"
---

<objective>
Reconcile the 9222/9223 CDP port mismatch (ISSUES #57) consistently across all canonical
project files, and redact the plaintext WeChat account password from the public repo (ISSUES
#58, P0 security), wiring the B-level account-login fallback to read credentials from env vars.

Purpose: These are independent hygiene fixes that unblock the rest of the phase — the refresh
wrapper (Plan 02) targets the correct port, and the B-level flow (Plan 02) reads creds from env
instead of a public literal. No dependency on Hermes or Aliyun; pure repo-code, lands first.

Output: Updated config.py + CLAUDE.md + 2 SKILL.md files + capture_qr.py default, all on 9222;
SKILL.md password literal removed and replaced with env placeholders.

Actor: [REPO-CODE] — orchestrator edits locally + commits. No Aliyun/Hermes write.
</objective>

<decision_note>
Port standardization decision (from CONTEXT.md #57 + RESEARCH.md): standardize on **9222**, NOT
9223. Rationale: the live headed Edge on Hermes with the logged-in WeChat MP profile
(`C:\Edge-Auto-Profile`) listens on 9222 and persists login state across relaunch. Relaunching it
on 9223 to match stale code would lose the warm profile / require re-login. The code is the thing
that is wrong; fix the code to 9222.
</decision_note>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-CONTEXT.md
@.planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md
@config.py
@skills/omnigraph_scan_kol/SKILL.md

<interfaces>
<!-- The exact 9223 sites to change (verified by grep, excluding .claude/worktrees/** and venv/**). -->
config.py:30          CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")
CLAUDE.md:308         CDP_URL table row "Local mode (default): http://localhost:9223 ... --remote-debugging-port=9223"
CLAUDE.md:370         Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 ..."
CLAUDE.md:373         Set CDP_URL=http://localhost:9223 in ~/.hermes/.env
CLAUDE.md:426         lessons-learned bullet "local Edge (localhost:9223) uses connect_over_cdp()"
skills/omnigraph_scan_kol/SKILL.md:210   "⚠️ CDP 浏览器不可达（端口 9223）"
skills/omnigraph_scan_kol/SKILL.md:371   "Windows host at port 9223 must have a real screen"
skills/wechat-cdp-credential-refresh/SKILL.md   frontmatter + Overview reference "--remote-debugging-port=9223"
scripts/capture_qr.py:9, :26, :92        usage text + CDP_URL default "http://localhost:9223"

<!-- The exact secret literal to remove (verified). SECRET VALUE INTENTIONALLY NOT REPRODUCED HERE
     (ISSUES #58 discipline). It lives at skills/omnigraph_scan_kol/SKILL.md:91 in a line of the form:
       Expected pre-filled values: `"account: <REDACTED-ACCOUNT>"` and `"password: <REDACTED-PASSWORD>"`. ...
     The executor reads the real literal directly from the file via grep/Read; do not echo it back. -->
skills/omnigraph_scan_kol/SKILL.md:91   (the literal account + password line to redact)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: [REPO-CODE] Reconcile all 9223 references to 9222 (KCA-7)</name>
  <files>config.py, CLAUDE.md, skills/omnigraph_scan_kol/SKILL.md, skills/wechat-cdp-credential-refresh/SKILL.md, scripts/capture_qr.py</files>
  <read_first>
    - config.py (line 30, CDP_URL default)
    - CLAUDE.md (lines 308, 370, 373, 426 — CDP_URL doc, Path 2 launch cmd, env example, lessons bullet)
    - skills/omnigraph_scan_kol/SKILL.md (lines 210, 371 — port-unreachable message + QR-flow note)
    - skills/wechat-cdp-credential-refresh/SKILL.md (frontmatter `compatibility:` + Overview)
    - scripts/capture_qr.py (lines 9, 26, 92 — usage docstring + CDP_URL default + argparse default)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (the 9222-is-live evidence: "Live Edge launch cmdline ... --remote-debugging-port=9222"; "9223 is DEAD")
  </read_first>
  <action>
    Change every canonical-project reference to CDP port 9223 → 9222. Standardize on 9222 because
    that is what the live logged-in Edge on Hermes actually runs (RESEARCH.md Test 1/2).

    Exact edits (do NOT touch `.claude/worktrees/**` or `venv/**` — those are git worktrees and
    vendored deps, out of scope):

    1. `config.py:30` — change `os.environ.get("CDP_URL", "http://localhost:9223")` to
       `os.environ.get("CDP_URL", "http://localhost:9222")`.
    2. `CLAUDE.md` — in the Environment Variables table row for `CDP_URL` (line ~308): replace both
       `http://localhost:9223` and `--remote-debugging-port=9223` with the 9222 equivalents. Line
       ~370 (the `Start-Process "msedge.exe" ... --remote-debugging-port=9223 --user-data-dir=...EdgeDebug9223`):
       change port to 9222 and the user-data-dir suffix `EdgeDebug9223`→`EdgeDebug9222`. Line ~373
       (`CDP_URL=http://localhost:9223`)→9222. Line ~426 (lessons bullet `localhost:9223`)→9222.
    3. `skills/omnigraph_scan_kol/SKILL.md:210` — change the Chinese message `端口 9223`→`端口 9222`.
       Line ~371 — `port 9223`→`port 9222`.
    4. `skills/wechat-cdp-credential-refresh/SKILL.md` — frontmatter `compatibility:` block and the
       Overview paragraph both say `--remote-debugging-port=9223` / `port 9223` → change all to 9222.
    5. `scripts/capture_qr.py` — docstring usage line `--cdp-url http://localhost:9223` (line ~6/9),
       the `--remote-debugging-port=9223` requires-note (line ~9), the module-level
       `CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")` (line ~26), and the argparse
       `--cdp-url` help/default text (line ~92) → all 9222.

    Do NOT change historical/archived docs (docs/bugreports/*, docs/runbooks/*, README.md,
    Deploy.md, docs/architecture.md, docs/tech-stack.md, docs/LOCAL_DEV_SETUP.md, specs/) in THIS
    task — those are dated artifacts. The 5 files in files_modified are the live config + the two
    skills the wrapper depends on + the QR helper. (If reviewer flags doc drift, file a follow-up;
    do not expand scope here.)
  </action>
  <verify>
    <automated>grep -rn "9223" config.py CLAUDE.md skills/omnigraph_scan_kol/SKILL.md skills/wechat-cdp-credential-refresh/SKILL.md scripts/capture_qr.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "9223" config.py` returns 0 matches.
    - `grep -n "9222" config.py` shows the CDP_URL default line.
    - `grep -rn "9223" CLAUDE.md skills/omnigraph_scan_kol/SKILL.md skills/wechat-cdp-credential-refresh/SKILL.md scripts/capture_qr.py` returns 0 matches.
    - `grep -c "9222" CLAUDE.md` returns ≥ 4.
    - `python -c "import config; print(config.CDP_URL)"` prints a URL containing `9222` (when CDP_URL env unset).
  </acceptance_criteria>
  <done>All canonical-project references to CDP 9223 changed to 9222; config.CDP_URL default is 9222; no 9223 remains in the 5 listed files.</done>
</task>

<task type="auto">
  <name>Task 2: [REPO-CODE] Redact plaintext WeChat password from SKILL.md, wire env placeholders (KCA-8)</name>
  <files>skills/omnigraph_scan_kol/SKILL.md</files>
  <read_first>
    - skills/omnigraph_scan_kol/SKILL.md (lines 79-117, the entire "Account Login Fallback" section, esp. line 91 with the literal account+password — read it from the file to identify the exact literal; do NOT echo it back in output)
    - .planning/ISSUES.md (row #58 — the P0-security framing, "secret value intentionally NOT reproduced", rotation note)
    - CLAUDE.md (Environment Variables section + "Scoped env vars" — the project pattern for reading from ~/.hermes/.env)
  </read_first>
  <action>
    Remove the literal WeChat credentials from the public repo and replace with env placeholders.
    (Read the exact literal directly from SKILL.md:91 via Read/grep — the secret is intentionally not
    reproduced in this plan per ISSUES #58 discipline; never echo the real value into output/logs.)

    1. In `skills/omnigraph_scan_kol/SKILL.md`, locate the line (currently :91) that begins
       `Expected pre-filled values:` and contains a literal `account: ...` and `password: ...` pair.
       Replace that entire sentence with this env-placeholder text:
       `Expected pre-filled values come from the browser's saved credentials, which must match
       ${WECHAT_MP_ACCOUNT} / ${WECHAT_MP_PASSWORD} set in ~/.hermes/.env (NOT committed to the repo).
       Verify the account field shows the configured account (first chars only) and password is
       non-empty. If fields show empty, the browser's saved credentials may have been cleared —
       re-enter them in the Edge profile, and ensure ~/.hermes/.env carries the same values for any
       scripted fallback.`
       (Wrap the ${...} tokens and ~/.hermes/.env in backticks to match the surrounding markdown style.)
    2. Add a short security note immediately after that paragraph (still inside the Account Login
       Fallback section):
       `> **Security:** This account password was previously committed as a literal in this public
       repo (redacted 2026-06-19, ISSUES #58). The password MUST be rotated; redaction alone does
       not undo the historical git exposure. The B-level scripted fallback reads WECHAT_MP_ACCOUNT /
       WECHAT_MP_PASSWORD from ~/.hermes/.env, never a hardcoded value.`
    3. Grep the rest of the file for any other occurrence of the same literal account/password
       fragments and remove/replace identically (there may be more than one). Use the values you read
       from the file in step 1 as the grep needles; do not paste them into any committed artifact.

    Do NOT add the real credential values anywhere in the repo. Do NOT touch `~/.hermes/.env`
    (that is Hermes-side, operator-channel — handled in Plan 04).
  </action>
  <verify>
    <automated>grep -rn "huhai\|Hardun" skills/ ; echo "exit_was_$?"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "huhai" skills/` returns 0 matches.
    - `grep -rn "Hardun" skills/` returns 0 matches.
    - `grep -n "WECHAT_MP_ACCOUNT" skills/omnigraph_scan_kol/SKILL.md` returns ≥ 1 match.
    - `grep -n "WECHAT_MP_PASSWORD" skills/omnigraph_scan_kol/SKILL.md` returns ≥ 1 match.
    - `grep -n "rotated\|rotate" skills/omnigraph_scan_kol/SKILL.md` shows the security/rotation note.
  </acceptance_criteria>
  <done>No literal WeChat account or password remains anywhere under skills/; the Account-Login-Fallback section references ${WECHAT_MP_ACCOUNT}/${WECHAT_MP_PASSWORD} from ~/.hermes/.env and carries a rotation security note.</done>
</task>

</tasks>

<verification>
- `grep -rn "9223" config.py CLAUDE.md skills/omnigraph_scan_kol/SKILL.md skills/wechat-cdp-credential-refresh/SKILL.md scripts/capture_qr.py` → 0 matches (KCA-7).
- `grep -rn "huhai\|Hardun" skills/` → 0 matches (KCA-8).
- `python -c "import config; print(config.CDP_URL)"` → contains 9222.
- The Account-Login-Fallback section in skills/omnigraph_scan_kol/SKILL.md references env placeholders + rotation note (KCA-8).
</verification>

<success_criteria>
- All canonical config + skill + QR-helper files consistently target CDP 9222 (KCA-7 closed for repo side).
- Public repo carries no plaintext WeChat credential; env placeholders + rotation note in place (KCA-8 repo side closed; actual password rotation is operator action noted for Plan 04).
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-01-SUMMARY.md`
</output>
