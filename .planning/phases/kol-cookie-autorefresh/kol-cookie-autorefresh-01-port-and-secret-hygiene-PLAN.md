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
    - "Every canonical project file references CDP port 9222, not 9223 (databricks-deploy/config.py excepted — KB pipeline out of scope)"
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

Scope boundary (auditable): `databricks-deploy/config.py:30` ALSO contains a `CDP_URL ... 9223`
default, but it is the KB Databricks app's OWN copy of config.py. The KB/ingest pipeline is
explicitly OUT OF SCOPE per CONTEXT.md ("Out of scope: ... any KB/ingest pipeline changes"). It is
deliberately left on 9223, and the acceptance grep below excludes it so the exclusion is visible.
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
<!-- ALL 9223 occurrences in the 5 in-scope files (verified by grep 2026-06-19, excluding
     .claude/worktrees/** and venv/**). The line numbers below are accurate as of authoring but
     drift as files are edited — DO NOT trust them as a complete list. The authoritative
     completeness check is the acceptance grep, which MUST return 0 matches across ALL 5 files
     after the edits. Change EVERY occurrence in each file, comment or LIVE code. -->
config.py
  :30   CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")   (LIVE code, the default)
CLAUDE.md
  ~308  CDP_URL table row "Local mode (default): http://localhost:9223 ... --remote-debugging-port=9223"
  ~370  Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 ..." + --user-data-dir=...EdgeDebug9223
  ~373  Set CDP_URL=http://localhost:9223 in ~/.hermes/.env
  ~426  lessons-learned bullet "local Edge (localhost:9223) uses connect_over_cdp()"
skills/omnigraph_scan_kol/SKILL.md
  ~210  "⚠️ CDP 浏览器不可达（端口 9223）"
  ~371  "Windows host at port 9223 must have a real screen"
skills/wechat-cdp-credential-refresh/SKILL.md   (8 sites — there is NO `compatibility:` frontmatter
     block; the references are description + Overview + Requires + curl/ws snippets + troubleshooting):
  :5    frontmatter description "connects to CDP port 9223"
  :13   "Requires: Edge/Chrome on Windows with CDP flag (--remote-debugging-port=9223)"
  :14   "Requires: WSL2 ... OR cd to Windows port 9223"
  :65   curl -s http://127.0.0.1:9223/json/version
  :69   "Ensure Edge/Chrome was started with `--remote-debugging-port=9223`"
  :78   websockets.connect('ws://127.0.0.1:9223/devtools/browser/...')
  :136  websockets.connect(f'ws://127.0.0.1:9223/devtools/page/{page_id}')
  :271  "msedge --remote-debugging-port=9223 --remote-debugging-address=127.0.0.1 ..."
scripts/capture_qr.py   (6 sites — note :58 is LIVE code, not a comment):
  :6    usage docstring "--cdp-url http://localhost:9223"
  :9    "--remote-debugging-port=9223" requires-note
  :26   CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")   (module default)
  :58   cdp_http = f"http://localhost:9223{...}"   (LIVE code — builds the DevTools HTTP URL)
  :69   comment example "http://localhost:9223/devtools/page/PAGE_ID"
  :92   argparse --cdp-url help/default "http://localhost:9223"

<!-- INTENTIONALLY OUT OF SCOPE (do NOT change): databricks-deploy/config.py:30 also has
     `CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")`. This is the KB Databricks app's
     OWN copy of config.py and the KB/ingest pipeline is explicitly excluded by CONTEXT.md. Leave it
     on 9223. The acceptance grep deliberately omits databricks-deploy/config.py so the exclusion is
     auditable. -->

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
    - CLAUDE.md (lines ~308, ~370, ~373, ~426 — CDP_URL doc, Path 2 launch cmd, env example, lessons bullet)
    - skills/omnigraph_scan_kol/SKILL.md (lines ~210, ~371 — port-unreachable message + QR-flow note)
    - skills/wechat-cdp-credential-refresh/SKILL.md (ALL 8 sites — description, Overview/Requires, curl + ws snippets, troubleshooting; there is NO `compatibility:` block)
    - scripts/capture_qr.py (ALL 6 sites — usage docstring, requires-note, CDP_URL module default, the LIVE `cdp_http = f"http://localhost:9223..."` at :58, the comment example at :69, argparse default)
    - .planning/quick/260615-kol-cookie-autorefresh-investigate/RESEARCH.md (the 9222-is-live evidence: "Live Edge launch cmdline ... --remote-debugging-port=9222"; "9223 is DEAD")
  </read_first>
  <action>
    Change every canonical-project reference to CDP port 9223 → 9222. Standardize on 9222 because
    that is what the live logged-in Edge on Hermes actually runs (RESEARCH.md Test 1/2).

    DO NOT trust the cited line numbers as a complete list — run `grep -n "9223" <file>` on each of
    the 5 files first, change EVERY hit (comment or LIVE code), then re-grep to confirm 0 remain.
    The `<interfaces>` block above lists the known occurrences but the acceptance grep is the
    authoritative safety net.

    Exact edits (do NOT touch `.claude/worktrees/**` or `venv/**` — those are git worktrees and
    vendored deps, out of scope):

    1. `config.py:30` — change `os.environ.get("CDP_URL", "http://localhost:9223")` to
       `os.environ.get("CDP_URL", "http://localhost:9222")`.
    2. `CLAUDE.md` — in the Environment Variables table row for `CDP_URL` (line ~308): replace both
       `http://localhost:9223` and `--remote-debugging-port=9223` with the 9222 equivalents. Line
       ~370 (the `Start-Process "msedge.exe" ... --remote-debugging-port=9223 --user-data-dir=...EdgeDebug9223`):
       change port to 9222 and the user-data-dir suffix `EdgeDebug9223`→`EdgeDebug9222`. Line ~373
       (`CDP_URL=http://localhost:9223`)→9222. Line ~426 (lessons bullet `localhost:9223`)→9222.
    3. `skills/omnigraph_scan_kol/SKILL.md` — change the Chinese message `端口 9223`→`端口 9222`
       (~210) and `port 9223`→`port 9222` (~371).
    4. `skills/wechat-cdp-credential-refresh/SKILL.md` — change ALL 8 occurrences (description at :5,
       Requires at :13/:14, curl at :65, troubleshooting at :69/:271, ws snippets at :78/:136) from
       `9223`→`9222`. There is NO `compatibility:` block; do not look for one — just grep and replace.
    5. `scripts/capture_qr.py` — change ALL 6 occurrences: docstring usage (:6), requires-note (:9),
       module-level `CDP_URL` default (:26), the LIVE `cdp_http = f"http://localhost:9223{...}"` at
       :58 (this is real code, not a comment — must change), the comment example (:69), and the
       argparse `--cdp-url` help/default (:92) → all 9222.

    DO NOT change `databricks-deploy/config.py:30` — that is the KB Databricks app's own config and
    the KB/ingest pipeline is explicitly out of scope per CONTEXT.md. Leave it on 9223.

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
    - `grep -rn "9223" config.py CLAUDE.md skills/omnigraph_scan_kol/SKILL.md skills/wechat-cdp-credential-refresh/SKILL.md scripts/capture_qr.py` returns 0 matches (the authoritative completeness check — note databricks-deploy/config.py is deliberately NOT in this list, KB out of scope).
    - `grep -c "9222" CLAUDE.md` returns ≥ 4.
    - `grep -c "9222" scripts/capture_qr.py` returns ≥ 6 (all 6 sites, incl. the LIVE :58 line, flipped).
    - `python -c "import config; print(config.CDP_URL)"` prints a URL containing `9222` (when CDP_URL env unset).
  </acceptance_criteria>
  <done>All canonical-project references to CDP 9223 changed to 9222 across all 5 files (including the LIVE capture_qr.py:58 line and all 8 wechat-cdp SKILL sites); config.CDP_URL default is 9222; no 9223 remains in the 5 listed files; databricks-deploy/config.py is intentionally left on 9223 (KB out of scope).</done>
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
- `grep -rn "9223" config.py CLAUDE.md skills/omnigraph_scan_kol/SKILL.md skills/wechat-cdp-credential-refresh/SKILL.md scripts/capture_qr.py` → 0 matches (KCA-7; databricks-deploy/config.py intentionally excluded, KB out of scope).
- `grep -rn "huhai\|Hardun" skills/` → 0 matches (KCA-8).
- `python -c "import config; print(config.CDP_URL)"` → contains 9222.
- The Account-Login-Fallback section in skills/omnigraph_scan_kol/SKILL.md references env placeholders + rotation note (KCA-8).
</verification>

<success_criteria>
- All canonical config + skill + QR-helper files consistently target CDP 9222 (KCA-7 closed for repo side); databricks-deploy/config.py left on 9223 by design (KB out of scope).
- Public repo carries no plaintext WeChat credential; env placeholders + rotation note in place (KCA-8 repo side closed; actual password rotation is operator action noted for Plan 04).
</success_criteria>

<output>
After completion, create `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-01-SUMMARY.md`
</output>
