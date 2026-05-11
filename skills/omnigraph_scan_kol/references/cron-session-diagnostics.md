# Cron Session Dump Diagnostic Reference

Quick-access diagnostic commands for unattended cron failures.

## Immediate Triage (3 commands)

```bash
# 1. List today's cron sessions
ls -lt ~/.hermes/sessions/session_cron_*$(date +%Y%m%d)*.json 2>/dev/null | head -10

# 2. Check which cron jobs have error status
hermes cronjob list 2>/dev/null | grep -A3 "error"

# 3. Quick DB coverage check
cd ~/OmniGraph-Vault && PYTHONPATH=. python3 -c "
import sqlite3
con = sqlite3.connect('data/kol_scan.db')
cur = con.cursor()
today = '$(date +%Y-%m-%d)'
cur.execute('SELECT COUNT(*) FROM articles WHERE date(scanned_at) = ?', (today,))
print(f'Articles today: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(DISTINCT account_id) FROM articles WHERE date(scanned_at) = ?', (today,))
print(f'Accounts today: {cur.fetchone()[0]}')
cur.execute('SELECT status, COUNT(*) FROM ingestions WHERE date(ingested_at) = ? GROUP BY status', (today,))
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')
con.close()
"
```

## Session Dump JSON Structure

Key fields in `session_cron_*.json`:

| Field | Meaning | Diagnostic Value |
|-------|---------|-----------------|
| `model` | LLM used | If `gemini-2.5-flash` for ingest → wrong model |
| `base_url` | API endpoint | If `127.0.0.1:8787` → going through gateway proxy |
| `messages[N]` | Conversation turns | Tool calls, errors, assistant responses |
| `messages[N].role` | `user`/`assistant`/`tool` | Filter for tool errors |
| `messages[N].name` | Tool name | `terminal`, `browser_navigate`, etc. |
| `messages[N].error` | Tool error message | Non-empty = failure |
| `messages[N].content` | Tool output (JSON) | For terminal, parse as JSON to get stdout |
| `session_start` | ISO timestamp | When cron fired |
| `last_updated` | ISO timestamp | When session ended |

## Extracting Terminal Output from Session Dump

The terminal tool stores output as JSON in `content`:

```python
import json
with open("session_cron_XXX.json") as f:
    data = json.load(f)
for msg in data['messages']:
    if msg.get('name') == 'terminal' and msg.get('role') == 'tool':
        content = msg.get('content', '')
        try:
            parsed = json.loads(content)
            print(parsed.get('output', content))
        except:
            print(content)
```

## Common Error Patterns

| Pattern | Meaning | Fix |
|---------|---------|-----|
| `ret=200003` in session | WeChat session expired | Run health check for credential refresh |
| `ret=200013` in session | WeChat rate limited | Wait 30-60 min |
| `model: gemini-2.5-flash` for ingest | Wrong model for batch | Set cron job provider to deepseek |
| `base_url: 127.0.0.1:8787` | Routing through gateway | OK if intentional, but adds latency |
| Terminal output empty | Command failed / timeout | Check if timeout killed it |
| `last_status: error` but assistant says success | Delivery failure (Telegram) | Check TELEGRAM_HOME_CHANNEL |
| 4 messages total | Agent couldn't complete | Check last assistant message for error |

## Post-Mortem Protocol

When a cron job shows `error` but actually succeeded (delivery failure only):
- The session dump contains the full success report
- The error is in delivery, NOT execution
- Extract the report from the session and deliver manually
- Fix the delivery config (TELEGRAM_HOME_CHANNEL)
