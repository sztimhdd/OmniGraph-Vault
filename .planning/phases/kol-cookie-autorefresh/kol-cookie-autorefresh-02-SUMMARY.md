---
phase: kol-cookie-autorefresh
plan: 02
subsystem: infra
tags: [cdp, websocket, wechat, cookie-refresh, hermes, aliyun, telegram, atomic-write]

# Dependency graph
requires:
  - phase: 260615-kol-cookie-autorefresh-investigate
    provides: "Proven direct-CDP probe (Network.getCookies 5/5 critical), WSL PowerShell relaunch, tab-drift gotcha, A/B/C decision tree (SKILL.md)"
provides:
  - "scripts/refresh_wechat_cookie.py — Hermes-side self-healing A/B/C refresh orchestrator (self-heal + CDP detect/recover + CSRF rebind + atomic Aliyun writeback + verify + rollback + capability-gated Telegram notify)"
  - "scripts/lib/cdp_client.py — direct CDP-over-websocket helper (is_alive/connect/send/navigate/current_url/evaluate/get_cookies) + 3 pure primitives (build_cookie_string, extract_token_from_url, critical_cookies_present)"
  - "writeback_to_aliyun with INJECTABLE run_ssh — atomic .tmp+os.replace preserving FAKEIDS, single-account test-scan verify (ret=0 gate), tested rollback to .bak-pre-refresh on bad creds"
  - "tests/unit/test_refresh_wechat_cookie.py — 6 pure-primitive behavior tests + 2 writeback rollback-branch tests (all green)"
affects: [kol-cookie-autorefresh-03 (Aliyun trigger ssh-hermes invocation), kol-cookie-autorefresh-04 (Hermes operator registration + alias repoint + env creds), kol-cookie-autorefresh-05 (live end-to-end exercise)]

# Tech tracking
tech-stack:
  added: [websocket-client (system python3, already on Hermes; venv 1.9.0 used for tests)]
  patterns:
    - "Direct CDP-over-websocket (no playwright, no MCP /mcp layer, no project venv) — proven in RESEARCH.md Test 1"
    - "Injectable ssh runner (run_ssh callable) makes the prod-write + verify + rollback branches unit-testable without a live Aliyun"
    - "Pinned sys.path.insert(0, script_dir) + `from lib.cdp_client import ...` so repo-root invocation resolves the sibling helper (INFO 7)"
    - "Capability-gated notify_image: probe `hermes send --help` for --image, fall back to text+path (WARNING 3)"

key-files:
  created:
    - scripts/lib/cdp_client.py
    - scripts/refresh_wechat_cookie.py
    - tests/unit/test_refresh_wechat_cookie.py
  modified: []

key-decisions:
  - "Port 9222 default (consistent with Plan 01, matches the live headed Edge); not 9223 (stale code/CLAUDE.md value)"
  - "Token + cookie passed base64-encoded into the remote python one-liner to dodge shell-escaping ; + = / in the cookie string"
  - "Remote in-place re.sub of TOKEN/COOKIE lines (NOT full file overwrite) so Aliyun-only FAKEIDS survive the writeback"
  - "Deferred `import websocket` into CdpClient.connect so the 3 pure helpers import without websocket-client present"
  - "Test loads scripts/lib/cdp_client.py by explicit file path (importlib) to bypass the shadowing top-level lib/ package under pytest's pythonpath=['.']"

patterns-established:
  - "Pure primitives at module top + I/O class below — primitives unit-tested without network/browser"
  - "verify-before-success + rollback-on-failure as the three non-negotiables for any prod-config writeback"

requirements-completed: [KCA-2, KCA-3, KCA-5, KCA-6, KCA-4]

# Metrics
duration: 8min
completed: 2026-06-20
---

# Phase kol-cookie-autorefresh Plan 02: Refresh Wrapper Summary

**Hermes-side self-healing WeChat-cookie refresh orchestrator over direct CDP-websocket — A/B/C failure-level detect + recover, PowerShell Edge self-heal, CSRF-rebind token extract, atomic Aliyun writeback with single-account test-scan verify and unit-tested rollback, and capability-gated QR-to-Telegram.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-20T00:11:53Z
- **Completed:** 2026-06-20T00:19:36Z
- **Tasks:** 3
- **Files modified:** 3 (all created)

## Accomplishments
- `scripts/lib/cdp_client.py` — stdlib + websocket-client CDP client (`CdpClient`) driving Network.getCookies / Runtime.evaluate (returnByValue) / Page.navigate / Page.getNavigationHistory; plus 3 pure helpers (sorted cookie string, token-from-URL, 5-critical-cookie check). No playwright / config / venv import.
- `scripts/refresh_wechat_cookie.py` (the orchestrator) — STEP 0 self-heal (is_alive → PowerShell `-EncodedCommand` Edge relaunch + 30s poll) → STEP 1 A/B/C detect+recover → STEP 2 CSRF rebind via second root-nav → STEP 3 extract with all-5-critical assertion → STEP 4 atomic writeback → STEP 5 capability-gated Telegram summary. Exit codes 0/1/2 (success/failure/needs-human).
- `writeback_to_aliyun` — atomic remote `.tmp`+`os.replace` preserving FAKEIDS, single-account `batch_scan_kol.py --account` verify (ret=0 gate), `***` hex-redaction guard, and rollback to `kol_config.py.bak-pre-refresh` on bad creds. INJECTABLE `run_ssh` closes the WARNING 5 untested-rollback gap.
- 8 unit tests green (6 pure primitives + 2 writeback rollback-branch) in the project venv.

## Task Commits

Each task was committed atomically (`--no-verify`, explicit `git add`, parallel-executor discipline):

1. **Task 1 (TDD): CDP-over-websocket helper + cookie/token primitives (KCA-2)** — `c71d148` (feat) — RED (test import fail) → GREEN (6 primitives pass). Test + helper committed together.
2. **Task 2: A/B/C refresh orchestrator + self-heal + Telegram notify (KCA-2,3,5,6)** — `6ebbf0d` (feat)
3. **Task 3 (TDD): atomic writeback + test-scan verify + tested rollback (KCA-4)** — `692f18b` (feat) — RED (writeback import fail) → GREEN (8 tests pass)

_Note: TDD RED/GREEN cycles were run but each task's test+impl committed in a single atomic commit (the shared test file holds both Task 1 and Task 3 tests; Task 1's commit carried the test file, Task 3 edited the impl-under-test only)._

## Files Created/Modified
- `scripts/lib/cdp_client.py` (189 LoC) — direct CDP-over-websocket client + 3 pure primitives
- `scripts/refresh_wechat_cookie.py` (526 LoC) — A/B/C self-healing orchestrator + atomic writeback
- `tests/unit/test_refresh_wechat_cookie.py` (175 LoC) — 6 primitive + 2 rollback-branch tests

## Decisions Made
- **Port 9222 default** — consistent with Plan 01 (KCA-7) and the live headed Edge; the stale `9223` in code/CLAUDE.md is reconciled by Plan 01's track.
- **Base64 transport for token/cookie** — the cookie string contains `;`, `+`, `=`, `/`; base64-encoding into the remote python one-liner avoids ssh shell-escaping entirely.
- **In-place re.sub of TOKEN/COOKIE lines** — rather than overwriting the whole file, so Aliyun-only `FAKEIDS` (never present on Hermes) survives.
- **Deferred websocket import** — `import websocket` lives inside `CdpClient.connect`, so the pure helpers (and the unit tests) import even where websocket-client is absent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test import collided with the shadowing top-level `lib/` package**
- **Found during:** Task 1 (pytest collection)
- **Issue:** The plan's pinned runtime contract is `from lib.cdp_client import ...`. At runtime (`python3 scripts/refresh_wechat_cookie.py`) the script's `sys.path.insert(0, script_dir)` makes `lib` resolve to `scripts/lib` correctly. But under pytest, `pyproject.toml`'s `pythonpath = ["."]` puts the repo root first, where a DIFFERENT top-level `lib/` package (the project's DeepSeek/models lib) shadows `scripts/lib` — `from lib.cdp_client import` raised `ModuleNotFoundError`.
- **Fix:** The test loads `scripts/lib/cdp_client.py` by explicit file path via `importlib`, registers it under the `lib.cdp_client` name the wrapper imports, then puts `scripts/` on sys.path so both `from lib.cdp_client import` (wrapper) and `from refresh_wechat_cookie import` (test) resolve. The wrapper's runtime contract is UNCHANGED (still `from lib.cdp_client import ...`, verified working via `--help` smoke under PYTHONUTF8=1).
- **Files modified:** tests/unit/test_refresh_wechat_cookie.py
- **Verification:** `--help` runtime smoke proves the pinned import resolves to scripts/lib at runtime; 8/8 tests green under pytest.
- **Committed in:** `c71d148` (Task 1 commit)

**2. [Rule 1 - Bug] Removed orphaned `ROOT_URL` constant + duplicate nav line (my own mess)**
- **Found during:** Task 2 (satisfying the KCA-2 literal-navigate grep gate)
- **Issue:** The acceptance gate greps for the literal `navigate('https://mp.weixin.qq.com/')` ≥ 2 times. My first draft routed both root-navs through a `ROOT_URL` constant (1 textual occurrence) and had a duplicate `landing = ...` line in the CSRF-rebind step.
- **Fix:** Inlined the literal URL at the two semantic root-nav sites (level-detect inside `root_nav`, CSRF-rebind in `run`), then removed the now-orphaned `ROOT_URL` constant and the duplicate line.
- **Files modified:** scripts/refresh_wechat_cookie.py
- **Verification:** literal navigate count = 2; orchestrator `--help` still runs.
- **Committed in:** `6ebbf0d` (Task 2 commit)

**3. [Rule 1 - Bug] Verify command split broke the `batch_scan_kol.py --account` grep gate**
- **Found during:** Task 3 (acceptance gate check)
- **Issue:** The f-string for the verify command split `batch_scan_kol.py ` and `--account ...` across two source lines, so the contiguous literal `batch_scan_kol.py --account` did not appear in the source (gate returned 0).
- **Fix:** Re-split the f-string so `batch_scan_kol.py --account {test_account}` stays on one literal segment.
- **Files modified:** scripts/refresh_wechat_cookie.py
- **Verification:** gate returns 1; 8/8 tests still green; runtime verify string unchanged.
- **Committed in:** `692f18b` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking import collision, 2 self-inflicted gate/orphan bugs)
**Impact on plan:** No scope creep. The import-collision fix preserves the plan's exact runtime contract (`from lib.cdp_client import`) while making the test resolve the real helper. The other two were tidying my own draft to meet the literal grep gates. All locked decisions (port 9222, env creds, atomic write, pinned import) honored.

## Issues Encountered
- **Windows cp1252 vs Hermes UTF-8 parse:** the plan's verify command `ast.parse(open(...).read())` (no `encoding=`) trips a `UnicodeDecodeError` on this Windows dev box because the file contains the Chinese dashboard markers (`AI老兵日记` etc., load-bearing for SKILL.md detection). On Hermes (Linux, UTF-8 locale) the exact command passes. Verified equivalently here with `open(..., encoding='utf-8')` → `parse_ok`, and confirmed runtime validity with `PYTHONUTF8=1 ... --help`. No code change needed (the file IS valid UTF-8 Python; the markers must stay).

## Known Stubs
None. `writeback_to_aliyun` is fully implemented (not a stub) — its live exercise against real Aliyun is intentionally deferred to Plan 05 (no logged-in Edge / live Aliyun in the repo env). The rollback branch — the most dangerous path (writes prod kol_config.py) — IS unit-tested here via the injectable `run_ssh`, so it is no longer live-only (closes WARNING 5).

## User Setup Required
None in this plan. Hermes-side registration (cron/systemd invocation of the wrapper, `vitaclaw-aliyun` alias repoint to 47.117.244.253, `WECHAT_MP_ACCOUNT`/`WECHAT_MP_PASSWORD` in `~/.hermes/.env`) is Plan 04 (operator-channel; Hermes RO until 2026-06-22).

## Next Phase Readiness
- **Plan 03 (Aliyun trigger):** can wire `omnigraph-kol-scan-alert.service` to `ssh hermes "cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py"`. The wrapper resolves its helper via the pinned import from repo-root cwd (INFO 7 verified).
- **Plan 04 (Hermes operator):** repoint `vitaclaw-aliyun` alias to 47.117.244.253, set env creds, confirm `hermes send --image` support (the wrapper already capability-gates it).
- **Plan 05 (live exercise):** exercise level A path live on Hermes, scp/writeback to Aliyun, single-account test scan ret=0, send a real QR to Telegram (level C dry-run). The rollback branch is already unit-tested; live writeback is the remaining unproven step.
- **No blockers.** All grep gates pass; 8/8 tests green; both files parse clean.

## Self-Check: PASSED

- Files: all 3 source files + SUMMARY.md FOUND on disk.
- Commits: c71d148, 6ebbf0d, 692f18b all FOUND in git log.
- Tests: 8/8 green. Parse: both source files parse_ok (UTF-8).
- Acceptance gates: all Task 1/2/3 grep gates pass; KCA-8 secret gate = 0.

---
*Phase: kol-cookie-autorefresh*
*Completed: 2026-06-20*
