---
type: runbook
plan: 05-00b
status: ready-to-execute
audience: operator (user) running on Hermes WSL host
created: 2026-04-29
---

# Plan 05-00b Runbook — Finish the 22 stuck KOL articles

## Context recap (read first — 2 min)

- **Goal:** ingest the remaining 22 keyword-matched KOL articles (`{Agent, Hermes, OpenClaw, Harness}` ∧ `depth_score ≥ 2`) into LightRAG so Plan 05-00b is 31/31 complete. Topic labels are case-sensitive per `classifications.topic`; see Gotcha 1 below.
- **What already shipped:**
  - 05-00c: Deepseek LLM + 2-key Gemini embedding rotation — proven on real workloads.
  - 05-00: graph at 3072 dim (29 docs / 263 nodes / 301 edges) via your Hermes-side run.
  - Your earlier run landed 9/31 articles.
  - Quick-task `260429-got` (commit `4bf1613`): `--topic-filter` now accepts comma-separated multi-keyword.
  - `CDP_URL` migrated to `~/.hermes/.env`; stale `~/OmniGraph-Vault/.env` deleted → Cognee `dotenv(override=True)` no longer has a stale file to override with.
- **What was NOT a real blocker:**
  - `content_preview` vs `digest` schema gap — confirmed false alarm. No code in the repo references `content_preview`. Your ad-hoc script referenced it; `batch_ingest_from_spider.py` uses `digest` correctly.
  - `subprocess.run(capture_output=True)` pipe deadlock — confined to your ad-hoc batch runner. `batch_ingest_from_spider.py:91` uses `capture_output=False`, so the child's stdout streams to terminal and never fills the pipe buffer. The runbook path avoids the deadlock entirely.
- **Cognee dotenv side-effect:** structurally fixed (stale `.env` deleted), so rotation pool will no longer silently collapse to 1 key.

## Pre-flight checks (~2 min)

Run these 4 checks before the real run. Abort if any fails.

### 1. Remote is at latest main

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && git fetch origin && git status -sb && git log --oneline -5"
```

Expect: HEAD at or ahead of `00e4b17` (the latest pushed commit). If behind:
```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && git pull --ff-only"
```

### 2. Multi-keyword CLI parses correctly

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python batch_ingest_from_spider.py --from-db --topic-filter 'Agent,Hermes,OpenClaw,Harness' --min-depth 2 --dry-run 2>&1 | head -30"
```

Expect:
- Prints candidate articles (or "no matches" if DB has no new matches)
- No `TypeError`, `ArgumentParser` error, or SQL syntax error
- Should list ~22 articles (the ones your earlier run didn't finish — the 9 already ingested are skipped via the `ingestions` table dedup)

### 3. Both Gemini keys are live

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python3 -c '
from pathlib import Path
from google import genai
from google.genai import types
env = Path.home() / \".hermes/.env\"
keys = []
for line in env.read_text().splitlines():
    if line.startswith(\"GEMINI_API_KEY=\"):
        keys.append((\"primary\", line.split(\"=\",1)[1].strip().strip(chr(34)).strip(chr(39))))
    elif line.startswith(\"GEMINI_API_KEY_BACKUP=\"):
        keys.append((\"backup\", line.split(\"=\",1)[1].strip().strip(chr(34)).strip(chr(39))))
for name, key in keys:
    try:
        r = genai.Client(api_key=key).models.embed_content(
            model=\"gemini-embedding-2\", contents=[\"probe\"],
            config=types.EmbedContentConfig(output_dimensionality=3072))
        print(f\"{name} ends ...{key[-4:]}: OK {len(r.embeddings[0].values)}-dim\")
    except Exception as e:
        print(f\"{name} ends ...{key[-4:]}: FAIL {str(e)[:150]}\")
'"
```

Expect: both probes return `OK 3072-dim`. If one is 429:
- That key's project burned its daily budget elsewhere today → wait for UTC midnight reset OR substitute a fresh key.
- Running with 1 working key is fine-ish for 22 articles (22 × ~300 calls = 6600 — over single-key 1000/day cap). Strongly prefer both keys working.

### 4. Deepseek is live

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python3 -c '
import os
from pathlib import Path
env = Path.home() / \".hermes/.env\"
for line in env.read_text().splitlines():
    if line.startswith(\"DEEPSEEK_API_KEY=\"):
        key = line.split(\"=\",1)[1].strip().strip(chr(34)).strip(chr(39))
        break
import urllib.request, json
req = urllib.request.Request(
    \"https://api.deepseek.com/v1/models\",
    headers={\"Authorization\": f\"Bearer {key}\"})
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read())
    print(\"models:\", [m.get(\"id\") for m in data.get(\"data\", [])])
'"
```

Expect: `models: ['deepseek-v4-flash', 'deepseek-v4-pro']`.

## CLI gotchas (⚠ READ BEFORE MAIN RUN — learned from the Hermes-side run)

### Gotcha 1 — `--topic-filter` is case-sensitive

The SQL predicate is `WHERE c.topic IN ({placeholders})` at `batch_ingest_from_spider.py:553`, which is **case-sensitive in SQLite by default** (no `COLLATE NOCASE` applied).

The classifier stores topic values **capitalized** — e.g. `'Agent'`, not `'agent'` — because that's what you pass in via `batch_classify_kol.py --topic Agent`. So:

```bash
# ✅ CORRECT — matches 'Agent' rows in classifications
--topic-filter 'Agent,Hermes,OpenClaw,Harness'

# ❌ WRONG — zero matches; silently returns empty set
--topic-filter 'agent,hermes,openclaw,harness'
```

**Rule of thumb:** case each keyword to match what you passed to the classifier. If unsure, query first:

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "sqlite3 ~/OmniGraph-Vault/data/kol_scan.db 'SELECT DISTINCT topic FROM classifications WHERE relevant=1 ORDER BY topic;'"
```

Then paste the exact topic labels into `--topic-filter`.

**Follow-up improvement (not blocking):** switch line 553 to `WHERE LOWER(c.topic) IN ({placeholders})` and `.lower()` each keyword in Python before binding. Small surgical change, eliminates the whole class of case mismatch bugs. File a quick-task if this keeps biting.

### Gotcha 2 — `SLEEP_BETWEEN_ARTICLES = 60` is over-conservative post-05-00c

`batch_ingest_from_spider.py:71` hardcodes `SLEEP_BETWEEN_ARTICLES = 60` with a comment `# Gemini free tier: 15 RPM`. That 60s delay was sized for the **old** single-key Gemini Flash LLM path, which hit 15 RPM on free tier.

**That constraint no longer applies post-Plan 05-00c:**
- LLM calls go to Deepseek (independent RPM pool; measured ~plenty for serial ingest)
- Embedding calls use 2-key Gemini rotation (~200 RPM combined on free tier)
- A 22-article run at 60s/article = 22 min of *pure sleep* on top of actual work

**Recommended override before the main run:** drop to `10s` (or `5s` if the run feels smooth).

Option A — sed the constant on remote before running (fastest):

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && sed -i 's/^SLEEP_BETWEEN_ARTICLES = 60$/SLEEP_BETWEEN_ARTICLES = 10  # reduced from 60 post-05-00c (DeepSeek+dual-key rotation)/' batch_ingest_from_spider.py && grep '^SLEEP_BETWEEN_ARTICLES' batch_ingest_from_spider.py"
```

Expect: prints the new line so you can eyeball the change. Verify with a dry-run before the main run.

Option B — full code fix (belongs in a follow-up quick-task): make it CLI-configurable via `--sleep-between-articles N` with default 10.

**Caveat:** if any of the 22 articles is a giant (>30K chars content), per-doc LightRAG work can itself take 3–5 min. Don't drop `SLEEP_BETWEEN_ARTICLES` below 5s — the dedup/rotation layer doesn't protect against wall-clock bursts on a single doc.

## Main run (~5–10 min with SLEEP_BETWEEN_ARTICLES=10; ~25 min with default 60)

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python batch_ingest_from_spider.py --from-db --topic-filter 'Agent,Hermes,OpenClaw,Harness' --min-depth 2 2>&1 | tee /tmp/wave0b_run.log"
```

What you should see:
- For each of ~22 articles: fetch → LLM entity extraction (Deepseek) → embedding (Gemini, rotated) → LightRAG `ainsert` → `ingestions` row marked `ok`.
- Per-doc wall-clock: ~30–60s typical, longer for dense content.
- Expect occasional transient 429s (per-minute) → the embedding wrapper's failover rotates to the other key.

If the run produces 22 `ok` rows in `ingestions`, you're done.

## Post-run verification (~2 min)

### Count new ingests

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python3 -c '
import sqlite3
conn = sqlite3.connect(\"data/kol_scan.db\")
# Count articles ingested today that match our keyword+depth filter
q = \"\"\"
SELECT count(DISTINCT i.article_id)
FROM ingestions i
JOIN classifications c ON i.article_id = c.article_id
WHERE i.status = \"ok\"
  AND date(i.created_at) = date(\"now\", \"localtime\")
  AND c.depth_score >= 2
  AND c.topic IN (\"Agent\",\"Hermes\",\"OpenClaw\",\"Harness\")
\"\"\"
print(\"articles ingested today:\", conn.execute(q).fetchone()[0])
'"
```

Expect: ≥ 20 (aiming for 22; allow ≤ 2 transient failures).

### Graph size grew

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && python3 -c '
import json
from pathlib import Path
for name in (\"vdb_chunks.json\", \"vdb_entities.json\", \"vdb_relationships.json\"):
    p = Path.home() / \".hermes/omonigraph-vault/lightrag_storage\" / name
    d = json.loads(p.read_text())
    print(f\"{name}: rows={len(d.get(\\\"data\\\", []))} dim={d.get(\\\"embedding_dim\\\")}\")
'"
```

Expect: all 3 vdb files show `dim=3072` and rows meaningfully higher than the pre-run 263/301/19 snapshot.

### LLM usage went to Deepseek (not Gemini)

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "grep -c 'api.deepseek.com' /tmp/wave0b_run.log" || echo "log grep failed; check run output directly"
```

Expect: non-zero count (one line per Deepseek call). Also confirm zero `generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent` calls — LLM side should be 100% Deepseek.

## Failure modes + mitigations

| Symptom | Likely cause | Mitigation |
|---------|--------------|------------|
| CLI crashes on `--topic-filter "a,b,c,d"` | Remote not at commit `4bf1613`+ | `git pull --ff-only` then retry pre-flight 2 |
| `All 2 Gemini keys exhausted (429)` | Both keys actually drained (per-project daily cap) | Wait for UTC midnight reset OR rotate in a fresh key pair in `~/.hermes/.env` |
| `Cannot send a request, as the client has been closed` | google-genai SDK lifecycle bug in sync scripts | Not expected in the real pipeline (uses `client.aio.models.embed_content`). If it fires in the ingest path, file a follow-up. |
| Some articles fail with Apify timeout | WeChat fetch issue | Per-article try/except in the batch script continues to next; re-run with `--from-db` after the main run to retry only the failed ones (dedup skips the successes) |
| LightRAG `AssertionError: embedding_dim` | Someone changed `_OUTPUT_DIM` in `lib/lightrag_embedding.py` to a non-3072 value without wiping storage | Check `grep "_OUTPUT_DIM" lib/lightrag_embedding.py`; if not 3072, fix. If intentional dim change, run `scripts/wave0_reembed.py` first. |
| Run hangs on one article for >5 min | Apify actor stuck OR Gemini 5xx retry loop | Ctrl+C the outer `python`; `ingestions` state is per-row atomic — re-run picks up where left off |

## Hand-off criteria (05-00b complete)

- 22 new articles in the `ingestions` table with `status=ok` (total 31/31 for keyword-matched depth≥2 subset)
- LightRAG graph grew by ≥ 20 docs' worth of entities/relations at 3072 dim
- Both rotation keys logged usage (rotation confirmed in production)
- SUMMARY at `.planning/phases/05-pipeline-automation/05-00b-SUMMARY.md` with: pre/post graph counts, article count deltas, any failures + root cause
- STATE.md + ROADMAP updated via `roadmap update-plan-progress 05 00b complete`

## If partially successful (20 or 21 of 22)

Treat as complete if ≥ 20 landed. Add the 1–2 failures to SUMMARY as known gaps; they can be retried in a later Wave 0b++ run. The graph is substantively complete for the keyword scope and Wave 1+ daily pipeline has a healthy floor.

## If scope expands (e.g., add `claude-code` keyword later)

```bash
python batch_ingest_from_spider.py --from-db --topic-filter 'Agent,Hermes,OpenClaw,Harness,ClaudeCode' --min-depth 2
```

Dedup prevents re-ingesting the existing 31; new `claude-code`-tagged matches flow through cleanly. This is D-11 "re-runnable as keyword scope grows" — now a one-command operation.

---

*Runbook ready. When you're ready to execute, SSH + run the pre-flight checks, then main run, then post-run verification. Report back any deviations — I'll investigate and patch.*
