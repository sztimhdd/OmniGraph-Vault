# WeChat Cookie Refresh Runbook

## Overview

When the WeChat MP API session (TOKEN + COOKIE) expires, all 54 KOL account scans
return `ret=200003` ("invalid session"). The B1 + B2 defenses surface this within
one scan cycle. This runbook describes how to refresh credentials end-to-end.

**Authored:** 260524-tvg (quick `260524-tvg` Track A)  
**Canonical skill:** `skills/wechat-cdp-credential-refresh/SKILL.md`

---

## 1. When to Trigger

Check for any of these symptoms:

- `~/.hermes/wechat-session-stale` exists on Aliyun (created by B2 OnFailure handler).
  Check: `ssh aliyun-vitaclaw "ls -la /root/.hermes/wechat-session-stale 2>/dev/null"`
- `journalctl -u omnigraph-kol-scan.service --since '1 hour ago' -n 50` on Aliyun
  shows `WECHAT_SESSION_INVALID: N/total` on stderr (B1 detection, threshold >= 30%).
- Daily digest shows 0 new articles for 2+ consecutive days.
- Manual scan exits with code 2: `ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && venv-aim1/bin/python batch_scan_kol.py --daily; echo exit=$?"`
  — `exit=2` + `WECHAT_SESSION_INVALID:` in stderr confirms session is stale.

---

## 2. Hermes-Side Refresh (Operator Runs in Hermes Session)

The WeChat CDP credential refresh ONLY runs on a Windows host with Microsoft Edge
launched with `--remote-debugging-port=9223`. Hermes is currently the only such
machine in this project.

**Paste this prompt into a Hermes chat session to invoke the refresh skill:**

```
Refresh the WeChat MP credentials using the wechat-cdp-credential-refresh skill.
Follow Step 0 (cookie-based session recovery) first before requesting a QR code.
After successful extraction, write updated credentials to kol_config.py. Then run
the Step 5 verification query (list_articles for first KOL, 1 article) and confirm
VALID output before reporting done. Do NOT paste or report any cookie / token values
in chat.
```

The skill (`skills/wechat-cdp-credential-refresh/SKILL.md`) handles:
- Step 0: Tries "登录" button click to revive stale token without QR scan
- Step 3-A: CDP WebSocket `Network.getCookies` for full untruncated `slave_sid`
- Step 3-D: Falls back to HITL QR scan only if cookies are truly absent
- Step 4: Writes TOKEN + COOKIE to `kol_config.py`
- Step 5: Verifies with live `list_articles` call

**Do NOT inline cookie or token values into the Hermes prompt.**  
Hermes reads `kol_config.py` from disk after credential refresh — no value needs
to flow through chat.

---

## 3. Transfer to Aliyun (2-Hop SCP)

After Hermes refreshes credentials, transfer the updated `kol_config.py` to Aliyun.

`kol_config.py` is gitignored on both machines — transfer via SCP, never via git.

**Step 1 — Copy from Hermes to local laptop:**

```bash
scp hermes:~/OmniGraph-Vault/kol_config.py /tmp/kol_config.py
```

(`hermes` = SSH alias defined in `~/.ssh/config`. Never inline host/port/user.)

**Step 2 — Copy from local laptop to Aliyun:**

```bash
scp /tmp/kol_config.py aliyun-vitaclaw:/root/OmniGraph-Vault/kol_config.py
```

(`aliyun-vitaclaw` = SSH alias defined in `~/.ssh/config`.)

**Step 3 — Clean up local temp file:**

```bash
rm /tmp/kol_config.py
```

---

## 4. Verification on Aliyun

Run these commands in sequence to confirm the new credentials work:

```bash
# Sanity-check: non-empty COOKIE value (no cookie values printed to terminal)
ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && venv-aim1/bin/python -c 'import kol_config; print(len(kol_config.COOKIE))'"
# Expected: a number > 100

# Clear the stale marker (created by B2 OnFailure handler)
ssh aliyun-vitaclaw "rm -f /root/.hermes/wechat-session-stale"

# Manual trigger: run one scan cycle and check result
ssh aliyun-vitaclaw "systemctl start omnigraph-kol-scan.service && sleep 30 && systemctl status omnigraph-kol-scan.service"
# Expected: Active: inactive (dead) with Result=success (not failed)

# Confirm scan produced articles and no WECHAT_SESSION_INVALID
ssh aliyun-vitaclaw "journalctl -u omnigraph-kol-scan.service --since '5 minutes ago' -n 100 | grep -E 'ok|failed|WECHAT_SESSION_INVALID'"
# Expected: log lines showing "ok" accounts, zero WECHAT_SESSION_INVALID
```

---

## 5. Hard Constraints

These are absolute rules — never violate them:

- **Never paste cookie or token values** into chat, commits, prompts, or this runbook.
  Credentials are runtime data, not source-of-truth. Only `kol_config.py` holds them,
  and it is gitignored on all machines.
- **Never inline SSH host/port/user** — use only SSH aliases (`hermes`, `aliyun-vitaclaw`).
  Actual connection details live in `~/.ssh/config` and the project memory files, never
  in committed files.
- **Never `git add kol_config.py`** — it is listed in `.gitignore`. Verify before any
  commit: `git status | grep kol_config` must produce no output.
- **Always use CDP `Network.getCookies`** for extraction — the DevTools UI truncates
  long Base64 `slave_sid` values and produces a broken cookie string. CDP API returns
  the full untruncated value.
- **Cookie changes propagate to Aliyun via SCP only** — never commit, never paste into
  Hermes prompts as literal values.

---

## See Also

- `skills/wechat-cdp-credential-refresh/SKILL.md` — full CDP procedure + edge cases
- `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` — B2 OnFailure handler
- `batch_scan_kol.py:SESSION_INVALID_THRESHOLD` — B1 detection threshold (30%)
- Project memory: `feedback_wechat_cookie_refresh_runbook.md`
