# aim-1-3 SUMMARY — DEPLOY-03 env extension

Status: ✅ DONE
Date: 2026-05-22
Commit: (pending — committed alongside DEPLOY-NOTES.md §DEPLOY-03 append)

## Outcome

- **2 ingest keys appended** to `/root/.hermes/.env`: `OMNIGRAPH_VERTEX_SA_JSON_PATH` + `APIFY_TOKEN_BACKUP`. Other 4 ingest keys (DEEPSEEK / SILICONFLOW / GEMINI / APIFY) were already present byte-identical from earlier deploys; not rewritten.
- **File mode 600 root:root preserved** pre + post (`-rw------- 1 root root`). Line count 49 → 51 (+2 net).
- **kb-api `.env` keys unchanged** — WEIXIN_TOKEN / GATEWAY_ALLOW_ALL_USERS / HERMES_CRON_TIMEOUT / TELEGRAM_BOT_TOKEN / BRAVE_API_KEY all count=1 pre + post.
- **kb-api PID 3512216 still serving** uvicorn on `127.0.0.1:8766` throughout aim-1-3; `kb-api.service.d/override.conf` not touched; no `systemctl` ops; no kb-api restart.
- **venv-aim1 env-presence smoke ✅:** `venv-aim1/bin/python` reads all 6 ingest keys from `os.environ` after `set -a; . /root/.hermes/.env`. SA JSON path resolves (file_exists=True). Token shapes match expected provider prefixes (sk-/AIza/apify_ap).
- **HEAD on Aliyun:** `4eaef45` (unchanged from aim-1-1/aim-1-2) — `.env` is not git-tracked.
- **Operator round-trips:** all env-extension + audit + smoke ops ran via direct Bash SSH (`ssh aliyun-vitaclaw '...'` and `ssh hermes ... | ssh aliyun-vitaclaw ...` pipe). Zero user round-trips after the 3-decision message at session start.

## Decision: Option A — 2-key minimal append

User-directed (2026-05-22) after agent surfaced 4-of-6 ingest keys already present:

- Append-only-the-absent (A) chosen over (B) full 6-key normalization. The 4 pre-existing keys are byte-identical to what aim-1-3 would write — rewriting them is pure churn and creates diff noise that hides the actual 2-line change.
- Backup file `/root/.hermes/.env.bak-aim1-20260522-233253` (2276 bytes, mode 600 root:root) preserved in-place for rollback. Rolls back via `cp -p .env.bak-aim1-20260522-233253 .env`.

## Two value-derivation decisions

**Decision 1 — `OMNIGRAPH_VERTEX_SA_JSON_PATH` from existing `GOOGLE_APPLICATION_CREDENTIALS` (semantic equivalence):**

- `GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json` already present in `/root/.hermes/.env`. Both env vars reference the same SA JSON file (mode 600 root:root, 2400 bytes).
- Agent SSH'd Aliyun, read the path string only via `grep "^GOOGLE_APPLICATION_CREDENTIALS=" | cut -d= -f2-`, used the path as `OMNIGRAPH_VERTEX_SA_JSON_PATH=<path>`. **SA JSON file bytes never read or transmitted.**
- Eliminates "where does the SA come from" ambiguity for future operators — same file, two namespaced references.

**Decision 2 — `APIFY_TOKEN_BACKUP` via Hermes → Aliyun SSH-pipe (no literal in agent context):**

- Source: Hermes `~/.hermes/.env` (canonical source-of-truth for ingest secrets since aim-1 is migrating ingest from Hermes → Aliyun). `APIFY_TOKEN_BACKUP` was deployed there 2026-05-08 as part of dual-token rotation (quick `260508-ev2`).
- Channel: `ssh hermes 'grep ^APIFY_TOKEN_BACKUP= ~/.hermes/.env' | ssh aliyun-vitaclaw 'cat >> /root/.hermes/.env'`. Value transits the local SSH client process pipe between two `ssh` invocations; the receiving `cat >> file` produces empty stdout, so the literal token never appears in agent stdout / context / artifacts.
- Honors both `feedback_aim1_agent_is_operator.md` (no SSH outsourcing) AND `feedback_no_literal_secrets_in_prompts.md` (no literal token in agent context). Pipe exit code 0; post-extension audit confirms the key is present with Apify-shape prefix.

## Pre/post evidence (masked)

```
=== Pre-extension (Aliyun /root/.hermes/.env) ===
mode/owner:  -rw------- 1 root root 2276 May 22
line count:  49

ingest keys present:
  DEEPSEEK_API_KEY              count=1
  SILICONFLOW_API_KEY           count=1
  GEMINI_API_KEY                count=1
  APIFY_TOKEN                   count=1
  GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json   (Vertex SA path, 600 root:root, 2400 bytes)
  OMNIGRAPH_VERTEX_SA_JSON_PATH count=0   (ABSENT)
  APIFY_TOKEN_BACKUP            count=0   (ABSENT)

kb-api keys: WEIXIN_TOKEN / GATEWAY_ALLOW_ALL_USERS / HERMES_CRON_TIMEOUT /
             TELEGRAM_BOT_TOKEN / BRAVE_API_KEY                  all count=1


=== Post-extension (Aliyun /root/.hermes/.env) ===
mode/owner:  -rw------- 1 root root 2403 May 22 23:43   (mode 600 root:root preserved)
line count:  51   (was 49, +2 net)

ingest keys present:
  DEEPSEEK_API_KEY              count=1   (unchanged)
  SILICONFLOW_API_KEY           count=1   (unchanged)
  OMNIGRAPH_VERTEX_SA_JSON_PATH count=1   (NEW, value=/root/.hermes/gcp-paid-sa.json, exists)
  GEMINI_API_KEY                count=1   (unchanged)
  APIFY_TOKEN                   count=1   (unchanged)
  APIFY_TOKEN_BACKUP            count=1   (NEW, len=47 bytes incl \n, prefix=apify_ap)

kb-api keys: all count=1   (unchanged)

backup:  /root/.hermes/.env.bak-aim1-20260522-233253  (-rw------- root:root 2276 bytes)
```

## venv-aim1 env-presence smoke (masked)

```
=== venv-aim1 env presence smoke ===
DEEPSEEK_API_KEY:               len=35  prefix=sk-06d83        (DeepSeek shape ✓)
SILICONFLOW_API_KEY:            len=51  prefix=sk-yhhvd        (SiliconFlow shape ✓)
OMNIGRAPH_VERTEX_SA_JSON_PATH:  path-shape (file_exists=True)
GEMINI_API_KEY:                 len=39  prefix=AIzaSyDt        (Google AIza shape ✓)
APIFY_TOKEN:                    len=46  prefix=apify_ap        (Apify shape ✓)
APIFY_TOKEN_BACKUP:             len=46  prefix=apify_ap        (Apify shape ✓)

=== kb-api keys still loadable from same .env ===
WEIXIN_TOKEN:             PRESENT (len=58)
GATEWAY_ALLOW_ALL_USERS:  PRESENT (len=4)
HERMES_CRON_TIMEOUT:      PRESENT (len=5)
```

All 6 ingest keys readable by `venv-aim1/bin/python` via `os.environ`; kb-api spot-check keys still readable from same `.env` post-extension. SA JSON file resolves on disk. No literal token values emitted at any step.

## Audit verdict

- 2 absent ingest keys appended (no rewrite of pre-existing 4): ✅ YES
- `/root/.hermes/.env` mode 600 root:root preserved: ✅ YES (pre + post)
- `/root/.hermes/.env` line count delta +2 net: ✅ YES (49 → 51)
- 6 ingest keys all present count=1 post-extension: ✅ YES
- kb-api keys unchanged (5/5 spot-checked count=1): ✅ YES
- venv-aim1 reads all 6 keys via `os.environ` after `. .env`: ✅ YES
- SA JSON file referenced by `OMNIGRAPH_VERTEX_SA_JSON_PATH` exists on disk: ✅ YES
- Token-shape sanity (sk-/AIza/apify_ap): ✅ YES (4/4 token-shaped keys match expected provider prefix)
- Backup file `/root/.hermes/.env.bak-aim1-20260522-233253` preserved (2276 bytes, 600 root:root): ✅ YES
- HEAD unchanged (`4eaef45`): ✅ YES
- kb-api PID 3512216 still serving uvicorn on 127.0.0.1:8766: ✅ YES
- `kb-api.service.d/override.conf` not touched: ✅ YES
- No literal token values in DEPLOY-NOTES.md / SUMMARY / agent stdout: ✅ YES

## Discipline checks

- ✅ **No-secrets:** DEPLOY-NOTES.md §DEPLOY-03 + this SUMMARY contain only key NAMES, length-bytes, 8-char prefixes (token-shape sanity), file paths, file mode/owner, line counts, backup filename. No full token values, no SA JSON contents.
- ✅ **No-connection-details:** No SSH host / port / user / IP / private key. Agent uses local SSH aliases `aliyun-vitaclaw` and `hermes`.
- ✅ **Operator-channel:** Agent IS operator per `feedback_aim1_agent_is_operator.md`. All env-extension + audit + smoke ops ran via direct Bash SSH. APIFY_TOKEN_BACKUP transited Hermes → Aliyun via SSH-pipe; literal token never entered agent context. Zero user round-trips after the initial 3-decision message.
- ✅ **Red lines honored:** No `git add -A` / `git add .`, no `--amend`, no `--force`, no `--hard`, no `systemctl` ops, no `kb-api.service.d/override.conf` touched, no kb-api restart, no kb-api venv (`venv/`) touched, no rewrite of pre-existing kb-api or ingest keys.
- ✅ **Forward-only edit:** §DEPLOY-03 is a net-new append to DEPLOY-NOTES.md; §DEPLOY-01 + §DEPLOY-02 unchanged. This SUMMARY is a net-new file.
- ✅ **kb-api preservation:** PID 3512216 still serving uvicorn on `127.0.0.1:8766` throughout aim-1-3; `venv/` Python version (3.10.12) and package count (160) unchanged; `kb-api.service.d/override.conf` mode/contents untouched.
- ✅ **Backup recoverable:** `/root/.hermes/.env.bak-aim1-20260522-233253` (2276 bytes, 600 root:root) preserves pre-extension state. Rollback: `ssh aliyun-vitaclaw 'cp -p /root/.hermes/.env.bak-aim1-20260522-233253 /root/.hermes/.env'`.

## Bridge to aim-1-4

`/root/.hermes/.env` now exposes all 6 ingest provider keys to `venv-aim1/bin/python` via standard `set -a; . .env; set +a` shell loading. aim-1-4 (DEPLOY-04 e2e smoke) can run the full ingest path against scratch storage with `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke`, exercising:

- DeepSeek API (Layer 2 full-body classify + LightRAG entity extraction)
- SiliconFlow Qwen3-VL (vision cascade primary)
- Vertex AI Gemini (Layer 1 classify + embedding fallback) — via `OMNIGRAPH_VERTEX_SA_JSON_PATH`
- Gemini API (vision cascade last-resort)
- Apify (scrape cascade primary + dual-token rotation via `APIFY_TOKEN_BACKUP`)

kb-api on `:8766` remains untouched — aim-1-4 smoke is a parallel-tenant test, not a kb-api co-tenant test. `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke` redirects all LightRAG / image / entity-buffer storage away from `/root/.hermes/omonigraph-vault/` (Hermes prod data), so the smoke run produces no side effects on Hermes ingest cron state.

## Files modified by aim-1-3

- `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md` (§DEPLOY-03 appended)
- `.planning/phases/aim-1-code-env-deploy/aim-1-3-SUMMARY.md` (this file, net-new)

No code / config / runtime changes other than 2 net-new lines appended to Aliyun-side `/root/.hermes/.env` (with rollback backup `.env.bak-aim1-20260522-233253` preserved). The `.env` file is not git-tracked; this commit captures only the planning artifacts.
