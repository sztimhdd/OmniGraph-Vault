# KOL Cold-Start Test Guide

Run this on the PC where you're logged into WeChat MP.

---

## Step 1 — Pull latest code

```bash
cd C:\Users\<you>\Desktop\OmniGraph-Vault   # adjust path if different
git pull
```

---

## Step 2 — Create kol_config.py

This file is gitignored and must be created manually on every machine.

Create `kol_config.py` in the project root with your real values:

```python
# kol_config.py — LOCAL ONLY, never commit
TOKEN = "352072792"

COOKIE = "appmsglist_action_3964447985=card; ..."   # paste your full cookie here

FAKEIDS = {
    "kol_1": "MzkyMDU5Mjc4OA==",   # replace kol_1 with the real account name if you know it
    "kol_2": "Mzg5NzczNjE0NQ==",
}
```

Where to find the values: `docs/KOL_COLDSTART_SETUP.md` has the extraction steps.

---

## Step 3 — Install dependencies (first time only)

```bash
venv\Scripts\pip install requests
```

(Everything else is already installed.)

---

## Step 4 — Dry run

Lists articles without ingesting anything:

```bash
venv\Scripts\python batch_ingest_from_spider.py --dry-run --max-articles 5
```

Expected output: article titles printed for both accounts, a `data/coldstart_run_*.json` file written with `"status": "dry_run"` entries.

If you see `ERROR: kol_config.py not found` → Step 2 is missing.

If you see HTTP 403 or cookie errors → your TOKEN/COOKIE has expired, re-extract from the WeChat MP browser session.

---

## Step 5 — Live ingest (1 article first)

```bash
venv\Scripts\python batch_ingest_from_spider.py --max-articles 1 --days-back 90
```

Check the output for `Done — 1 ok`. Then verify it landed in the graph:

```bash
venv\Scripts\python list_entities.py | head -20
```

---

## Step 6 — Full cold-start batch

Once 1 article works, run the full batch:

```bash
venv\Scripts\python batch_ingest_from_spider.py --days-back 90 --max-articles 50
```

This will take a while (~1-2 min per article). Progress is logged to the terminal.
Final summary JSON is at `data/coldstart_run_{timestamp}.json`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `kol_config.py not found` | Create the file (Step 2) |
| `HTTP 403` or empty `app_msg_list` | TOKEN/COOKIE expired — re-extract from browser |
| `SSL error` on WeChat API | You're on the corporate proxy — must run from the WeChat PC (not your work laptop) |
| `ingest_wechat.py` fails per article | Check `GEMINI_API_KEY` is set in `~/.hermes/.env` |
| Empty entity list after ingest | LightRAG indexing takes a moment; wait 30s and retry |
