---
phase: kol-cookie-autorefresh
plan: 01
subsystem: infra
tags: [cdp, edge, wechat, secrets, port-reconcile, kol-scan]

# Dependency graph
requires: []
provides:
  - "All canonical repo files reference CDP port 9222 (not 9223), matching the live logged-in Edge profile on Hermes"
  - "Plaintext WeChat account+password removed from the public repo; B-level account-login fallback documents reading creds from ${WECHAT_MP_ACCOUNT}/${WECHAT_MP_PASSWORD} in ~/.hermes/.env"
affects: [kol-cookie-autorefresh-02-refresh-wrapper, kol-cookie-autorefresh-04-hermes-operator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Env-placeholder convention for secrets in SKILL.md docs: ${WECHAT_MP_ACCOUNT}/${WECHAT_MP_PASSWORD} sourced from ~/.hermes/.env, never literal"

key-files:
  created: []
  modified:
    - config.py
    - CLAUDE.md
    - skills/omnigraph_scan_kol/SKILL.md
    - skills/omnigraph_scan_kol/references/account-login-flow.md
    - skills/wechat-cdp-credential-refresh/SKILL.md
    - scripts/capture_qr.py

key-decisions:
  - "Standardized CDP port on 9222 (live Edge with warm logged-in profile) rather than relaunching on 9223 — the code was wrong, fix the code"
  - "databricks-deploy/config.py:30 intentionally left on 9223 (KB/ingest pipeline out of scope per CONTEXT.md)"
  - "Redacted credentials in BOTH SKILL.md:91 and references/account-login-flow.md (3 extra literal sites) — KCA-8 gate is repo-wide under skills/, not just the planned line"

patterns-established:
  - "Secret docs use env-placeholder + explicit rotation security note when a literal was historically committed"

requirements-completed: [KCA-7, KCA-8]

# Metrics
duration: 9min
completed: 2026-06-20
---

# Phase kol-cookie-autorefresh Plan 01: Port + Secret Hygiene Summary

**Reconciled all canonical CDP references from port 9223 to 9222 across 5 files, and redacted the plaintext WeChat account/password from the public repo (SKILL.md + references doc), wiring the B-level account-login fallback to `${WECHAT_MP_ACCOUNT}`/`${WECHAT_MP_PASSWORD}` env placeholders.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-20T00:11:41Z
- **Completed:** 2026-06-20T00:20:43Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- KCA-7: every canonical project reference to CDP port 9223 changed to 9222 (config.py default, 4 CLAUDE.md sites, 2 omnigraph_scan_kol/SKILL.md sites, 8 wechat-cdp-credential-refresh/SKILL.md sites incl. live ws/curl snippets, 6 scripts/capture_qr.py sites incl. the LIVE `cdp_http` builder at :58). Authoritative grep gate returns 0 matches across all 5 files.
- KCA-8 (P0 security): plaintext WeChat account+password removed from the public repo. The Account-Login-Fallback section now documents reading creds from `${WECHAT_MP_ACCOUNT}`/`${WECHAT_MP_PASSWORD}` in `~/.hermes/.env` and carries an explicit rotation security note. `grep -rn "huhai\|Hardun" skills/` returns 0.
- `databricks-deploy/config.py` confirmed left on 9223 (KB pipeline out of scope, exclusion auditable).
- `python -c "import config; print(config.CDP_URL)"` prints `http://localhost:9222` with env unset.

## Task Commits

Each task was committed atomically (`--no-verify`, explicit `git add`, forward-only):

1. **Task 1: Reconcile all 9223 references to 9222 (KCA-7)** - `338dd90` (fix)
2. **Task 2: Redact plaintext WeChat creds, wire env placeholders (KCA-8)** - `9fc5dcf` (fix)

_Note: This was a parallel-executor run (Plan 02 ran concurrently on disjoint files); Plan 02 commits are interleaved in the shared `main` history between these two._

## Files Created/Modified
- `config.py` - CDP_URL default 9223 -> 9222
- `CLAUDE.md` - CDP_URL env table row, Path 2 launch cmd + user-data-dir suffix (EdgeDebug9223 -> EdgeDebug9222), env example, lessons-learned bullet
- `skills/omnigraph_scan_kol/SKILL.md` - port-unreachable Telegram message + QR-flow display note (9223 -> 9222); Account-Login-Fallback line 91 literal creds replaced with env placeholders + rotation security note
- `skills/omnigraph_scan_kol/references/account-login-flow.md` - 3 literal-account sites (pre-filled note, bizlogin URL param, verified-use note) replaced with `${WECHAT_MP_ACCOUNT}` + redaction/rotation note
- `skills/wechat-cdp-credential-refresh/SKILL.md` - all 8 port sites (frontmatter description, Requires lines, curl /json/version, ws connect snippets, troubleshooting launch cmd) flipped to 9222
- `scripts/capture_qr.py` - all 6 port sites (usage docstring, requires-note, module CDP_URL default, LIVE `cdp_http` f-string builder at :58, comment example, argparse default) flipped to 9222

## Decisions Made
- **Standardize on 9222, not 9223:** the live headed Edge on Hermes with the warm WeChat MP login profile (`C:\Edge-Auto-Profile`) listens on 9222 and persists login state. Relaunching on 9223 to match stale code would lose the warm profile / force re-login. The code was the thing that was wrong (CONTEXT.md #57, RESEARCH.md Test 1/2).
- **databricks-deploy/config.py left on 9223:** it is the KB Databricks app's own copy of config.py; the KB/ingest pipeline is explicitly out of scope per CONTEXT.md. The acceptance grep deliberately omits it so the exclusion is auditable.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Redacted credential literals in references/account-login-flow.md (3 extra sites)**
- **Found during:** Task 2 (secret redaction)
- **Issue:** The plan's primary target was `skills/omnigraph_scan_kol/SKILL.md:91`, but `grep -rn "huhai\|Hardun" skills/` also found the literal WeChat account email in `skills/omnigraph_scan_kol/references/account-login-flow.md` (lines 8, 14, 45). The KCA-8 acceptance gate is repo-wide under `skills/` (returns 0 matches), so leaving these would have failed the gate and left a P0 plaintext credential in the public repo. The plan's Task 2 action step 3 explicitly directs grepping the rest of the file set and replacing identically.
- **Fix:** Replaced all 3 literal-account occurrences with `${WECHAT_MP_ACCOUNT}` env placeholder and added a redaction/rotation note. The real literal values were never echoed into any committed artifact.
- **Files modified:** skills/omnigraph_scan_kol/references/account-login-flow.md
- **Verification:** `grep -rn "huhai\|Hardun" skills/` returns 0 matches (exit 1, no match).
- **Committed in:** 9fc5dcf (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical — security)
**Impact on plan:** The deviation was required to satisfy the plan's own KCA-8 acceptance gate (repo-wide `skills/` clean). No scope creep — same secret, adjacent doc file in the same skill directory.

## Issues Encountered
None. Both tasks executed cleanly. The Git Bash `grep` redirected through the background-task harness in a couple of probes; switched to the Grep tool for the broader-repo scan, which confirmed all remaining `huhai`/`Hardun` matches outside `skills/` are either grep-needle strings inside `.planning/` phase PLAN acceptance criteria (not real secret values) or historical `.planning/archive/` artifacts — both out of scope for KCA-8.

## Security Note (P0 carry-forward)
Redaction stops the credential from being in the *current* tree but does NOT undo the historical git exposure. **The WeChat account password MUST be rotated** — this is an operator action tracked for Plan 04 (Hermes-operator). The `~/.hermes/.env` vars `WECHAT_MP_ACCOUNT`/`WECHAT_MP_PASSWORD` are Hermes-side (operator-channel) and were intentionally NOT touched here. Git-history scrub is a separate deferred decision (CONTEXT.md `<deferred>`); rotation is the real mitigation.

## User Setup Required
None at the repo-code level. Operator follow-ups (rotate WeChat password, add `WECHAT_MP_ACCOUNT`/`WECHAT_MP_PASSWORD` to `~/.hermes/.env`) are handled in Plan 04.

## Next Phase Readiness
- Plan 02 (refresh wrapper) can now target the correct CDP port 9222 and read creds from env placeholders rather than a public literal.
- Plan 04 (Hermes operator) must rotate the exposed password and set the two env vars on Hermes.
- No blockers introduced.

## Self-Check: PASSED

- FOUND: `.planning/phases/kol-cookie-autorefresh/kol-cookie-autorefresh-01-SUMMARY.md`
- FOUND: commit `338dd90` (Task 1)
- FOUND: commit `9fc5dcf` (Task 2)
- GATE-7 PASS: `grep -rn "9223" <5 scoped files>` → 0 matches
- GATE-8 PASS: `grep -rn "huhai\|Hardun" skills/` → 0 matches

---
*Phase: kol-cookie-autorefresh*
*Completed: 2026-06-20*
