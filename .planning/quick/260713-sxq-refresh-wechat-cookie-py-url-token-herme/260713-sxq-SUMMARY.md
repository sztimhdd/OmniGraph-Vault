---
phase: quick-260713-sxq
plan: 01
subsystem: wechat-cookie-refresh
tags: [wechat, cdp, hermes, self-heal, login-detection]
requires: []
provides:
  - "URL-token-gated login detection in scripts/refresh_wechat_cookie.py"
  - "local-only Edge relaunch (no remote-SSH plumbing)"
affects:
  - scripts/refresh_wechat_cookie.py
tech-stack:
  added: []
  patterns:
    - "extract_token_from_url(landing) as definitive login-valid signal, not text-guessing"
key-files:
  created: []
  modified:
    - scripts/refresh_wechat_cookie.py
decisions:
  - "DECISION 1: extract_token_from_url(landing) is the definitive login-valid gate — token present short-circuits to Level A; Level B gated on LOGIN_PAGE_MARKERS + token-absence; Level C success detected via fresh token, not dashboard text"
  - "DECISION 2: notify() Telegram path (full-path hermes CLI, send -t telegram) verified already correct — left unchanged"
  - "DECISION 3: relaunch simplified to local PowerShell only (relaunch_edge_local); relaunch_edge_remote() and all hermes_host/remote-SSH plumbing removed"
metrics:
  duration_minutes: 4
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  completed: 2026-07-14
---

# Phase quick-260713-sxq Plan 01: WeChat cookie refresh — URL-token login detection + local-only relaunch Summary

Rewired `scripts/refresh_wechat_cookie.py` login-state detection from brittle account-specific dashboard-text guessing to the empirically-validated URL `token=` query-param signal, and stripped dead remote-SSH Edge-relaunch plumbing now that the script's runtime home (Hermes) is locked architecture.

## What Changed

**Task 1 — URL-token as the definitive login-valid signal (DECISION 1):**

- Added `LOGIN_PAGE_MARKERS = ("使用账号登录", "立即注册", "微信扫一扫")` constant.
- `detect_and_recover`: after the initial `root_nav` + `extract_token_from_url(landing)`, a non-None token with `force_level is None` now short-circuits immediately to `"A"` (login already valid — nothing to recover). This runs BEFORE any Level A/B branching.
- Level B trigger condition changed from `ACCOUNT_LOGIN_MARKER in text and not _is_dashboard(text)` to `token is None and any(m in text for m in LOGIN_PAGE_MARKERS)`. Level B's post-fill success check changed from `_is_dashboard(text)` to a root re-nav + `extract_token_from_url(landing)` check.
- `_level_c_qr_login`: the post-scan polling loop now re-navigates root and checks `extract_token_from_url(landing)` for success instead of `_is_dashboard(text)`. The `QR_EXPIRED_MARKER` re-capture branch still reads page text (unchanged) since it needs the actual expiry marker, not the token.
- `DASHBOARD_MARKERS`/`_is_dashboard` were kept (still used inside the Level A `force_level == "A"` testing branch condition and available as a corroborating signal) — not deleted, per the plan's "keep for backward-compat" instruction.

**Task 2 — Local-only relaunch + notify verification (DECISIONS 2 & 3):**

- Deleted `relaunch_edge_remote()` entirely (SSH-based PowerShell relaunch of Edge on a remote Hermes host).
- `ensure_browser_alive`: removed the `hermes_host` parameter and the `is_hermes_context`/`is_aliyun_context` platform-detection branch that chose between local vs. SSH relaunch. It is now: if alive return True; else warn + `relaunch_edge_local()` + poll ~30s; return True on recovery, notify + False on timeout.
- `connect_browser` already had no `hermes_host` param and no `retry_after_launch` loop in the current codebase (the plan's line references to that logic did not match the file's actual current state) — no changes were needed there. Verified via grep this is genuinely absent both before and after.
- `run()`: removed the `hermes_host="hermes-pc"` parameter and both internal call sites passing `hermes_host=hermes_host` to `ensure_browser_alive`.
- `main()`: removed the `--hermes-host` argparse argument and the `hermes_host=args.hermes_host` argument to `run()`.
- DECISION 2 verified (not modified): `_resolve_hermes_bin()` resolves `~/.local/bin/hermes`; `notify()` calls `subprocess.run([HERMES_BIN, "send", "-t", "telegram", text], ...)`. Confirmed correct per the locked decision, left byte-identical.

## Deviations from Plan

**1. [Scope-narrowing, not a deviation requiring Rule 4] `connect_browser` had no `hermes_host` param or `retry_after_launch` loop to remove**

- **Found during:** Task 2, step 3 of the plan's action list.
- **Context:** The plan text describes `connect_browser` (lines 277-318 in the plan's line-number references) as having a `hermes_host` param and a `retry_after_launch` two-attempt loop calling `relaunch_edge_remote`. Reading the actual file in this worktree showed `connect_browser(hermes_first=True)` already had neither — it was already a single pass over the Hermes→Mac endpoint fallback list with no relaunch logic inside it.
- **Resolution:** No code change was needed for `connect_browser` itself. This is consistent with the plan's own instruction ("connect_browser does NOT need its own relaunch" — STEP 0-HEAL in `run()` already owns relaunch). Confirmed via grep (verification #4) that zero `retry_after_launch`/`hermes_host` remnants exist anywhere in the file after edits.
- **Files affected:** none beyond what Task 2 already touched (`ensure_browser_alive`, `run`, `main`).
- **Commit:** covered by `18739d7` (no separate commit needed — this was a no-op discovery, not a fix).

No other deviations. Plan executed as written for both tasks; no Rule 1/2/3 auto-fixes were needed (no bugs, no missing critical functionality, no blocking issues encountered); no Rule 4 architectural questions arose.

## Verification Results

All 5 plan verification checks passed:

1. `ast.parse` syntax check → `SYNTAX OK`
2. `grep -n "extract_token_from_url"` → 8 matches, including inside `detect_and_recover` (3x) and `_level_c_qr_login` (1x)
3. `grep -n "send.*-t.*telegram"` → 1 match, the `notify()` subprocess.run line, unchanged
4. `grep -n "relaunch_edge_remote\|hermes_host\|retry_after_launch"` → zero matches
5. `venv/Scripts/python.exe -m pytest tests/unit/test_refresh_wechat_cookie.py -v` → 8/8 passed

Net diff across both commits: 38 insertions, 64 deletions in `scripts/refresh_wechat_cookie.py` (single file, well within the ~30-60 LoC surgical estimate — the majority is deletions from removing `relaunch_edge_remote` and the platform-detection branch).

## Manual E2E Follow-up (NOT part of this quick)

The script requires a live Hermes Edge CDP endpoint (`localhost:9222`) and an active/expired WeChat MP browser session to exercise end-to-end — neither is available on this corp dev box. Per the plan's own verification section, this is a documented operator step, not a plan gate:

- On Hermes: `cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --dry-run`
- Confirm level-detection log lines trace to the URL-token signal (e.g. "Login valid: landing URL carries token=; nothing to recover" for Level A short-circuit, or Level B/C entries gated on `LOGIN_PAGE_MARKERS`/token-absence as appropriate to the live session state).
- Confirm a Telegram test message arrives via `hermes send -t telegram` (unchanged path, but worth confirming end-to-end on the actual Hermes host where `~/.local/bin/hermes` and the Telegram bot token/chat-id env vars are live).

This follow-up is tracked here in the SUMMARY rather than filed as an ISSUES.md entry, since the plan explicitly scoped it out as "documented operator step, not a plan gate" — it is expected manual verification, not a deferred defect.

## Self-Check: PASSED

- FOUND: scripts/refresh_wechat_cookie.py (modified, exists)
- FOUND: commit 4ead87e (Task 1 — URL-token login detection)
- FOUND: commit 18739d7 (Task 2 — local-only relaunch + notify verification)
- FOUND: 8/8 unit tests passing post-edit
- FOUND: zero `relaunch_edge_remote`/`hermes_host`/`retry_after_launch` remnants (grep-confirmed)
