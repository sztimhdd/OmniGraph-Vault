# Reconcile-Ingestions Canary (k5q)

## What It Is

A daily cron (`reconcile-ingestions` @ 09:30 ADT) that verifies the contract:
`ingestions.status='ok' ⇄ LightRAG doc_status='processed'`.

It queries today's `ingestions` rows with `status='ok'`, checks each against
`kv_store_doc_status.json`, and reports `mystery` count (ok rows with
actual_status ≠ 'processed').

## How to Read Output

The canary runs as an **agent-driven cron** (NOT no_agent). The cron prompt
pipes output through `tee`:

```
python scripts/reconcile_ingestions.py 2>&1 | tee /tmp/reconcile-$(date +%Y%m%d).log
```

**Primary method — read the tee'd log file (fastest):**

```bash
cat /tmp/reconcile-$(date +%Y%m%d).log
```

The log contains one JSON line per mystery row plus a summary line:
`2026-05-11: 4 ok rows / 0 matched / 4 mystery`.

**Fallback — session JSON (if tee failed or log missing):**

```bash
# Find the session (runs ~09:31-09:32)
ls -lt ~/.hermes/sessions/session_cron_*_0931* | head -1

# Extract the reconcile result
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
msgs = data.get('messages', [])
for m in msgs:
    if m.get('role') == 'assistant' and 'content' in m:
        c = m['content']
        if isinstance(c, str) and 'mystery' in c.lower():
            print(c[:3000])
" $(ls -t ~/.hermes/sessions/session_cron_*_0931* | head -1)
```

Or grep the agent log:
```bash
grep "2026-05-11T09:3" ~/.hermes/logs/agent.log | grep -i "reconcile\|mystery"
```

## Interpreting Results

| Output | Meaning | Action |
|--------|---------|--------|
| `0 mystery` | Contract intact, all ok rows verified | Nothing |
| `N mystery` (any N>0) | N ok rows with actual_status=failed in LightRAG | EMERGENCY — see mystery-row-cleanup.md |
| No row yet | Cron hasn't fired, or all today's ok rows were pre-cron | Wait. If `ingestions` has ok rows but no canary output after 09:35, cron may have errored |

## Canary Registration

```bash
export PATH="$HOME/.local/bin:$PATH"
bash scripts/register_phase5_cron.sh
```

The canary is registered via `register_phase5_cron.sh`. It is NOT a no_agent
script — it uses the agent with `terminal` toolset. The agent runs
`scripts/reconcile_ingestions.py --date <today>` and reports the result.

## False-Negative Pattern: h09 Says 0, Canary Says N

This was discovered 2026-05-11 when the 09:00 cron's h09 `grep -c "post-ainsert
PROCESSED verification failed"` returned 0, but the 09:30 canary reported
`4 ok rows / 0 matched / 4 mystery`.

Root cause: `_verify_doc_processed_or_raise` in `ingest_wechat.py` passed
(doc_status was PROCESSING or a transient state), the outer loop wrote
`ingestions.status='ok'`, but LightRAG never completed to 'processed'.

**Detection:** Only the canary catches this. h09 log grep cannot — it only
flags explicit verification failures, not silent pass-throughs.

Recovery: Mystery row cleanup (references/mystery-row-cleanup.md) +
investigate why h09 gate passed (was doc_status PROCESSING? PENDING?
a transient network error swallowed?). For DeepSeek 402 specifically:
check `error_msg` field in doc_status JSON for "Insufficient Balance" →
recharge → revert mystery rows → verify candidate pool → re-fire ingest.