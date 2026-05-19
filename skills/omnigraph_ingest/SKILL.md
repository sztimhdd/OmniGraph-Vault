---
name: omnigraph_ingest
description: |
  Ingest WeChat articles and PDFs into the OmniGraph knowledge graph. Handles scraping
  (Apify/CDP/MCP/UA cascade), image download + Vision description, entity extraction,
  and LightRAG graph indexing. For Zhihu-enriched ingest, use enrich_article first.
  Do NOT use for queries (omnigraph_query), synthesis (omnigraph_synthesize),
  or graph health checks (omnigraph_status).
compatibility: |
  Requires: OMNIGRAPH_GEMINI_KEY (preferred) or GEMINI_API_KEY (fallback) in ~/.hermes/.env;
  Python venv at $OMNIGRAPH_ROOT/venv.
  Optional: APIFY_TOKEN (enables primary scraping path), CDP_URL (default localhost:9223).
required_environment_variables:
  - name: OMNIGRAPH_GEMINI_KEY
    prompt: "Gemini API key for OmniGraph-Vault (get from https://aistudio.google.com/apikey)"
    help: "Required for LLM, embedding, and vision calls. Falls back to GEMINI_API_KEY if unset."
    required_for: full functionality
metadata:
  openclaw:
    skillKey: omnigraph-vault
    primaryEnv: OMNIGRAPH_GEMINI_KEY
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["OMNIGRAPH_GEMINI_KEY"]
---

# omnigraph_ingest

## Pre-flight Checks (always run FIRST)
1. **Check if already ingested**: grep doc_status.json for `wechat_<hash>` — if `status: "processed"`, skip.
2. **Verify DeepSeek balance**: try a trivial LLM call or check last ingest log for `402 Insufficient Balance`.
3. **If 402**: revert affected ingestions rows to `failed`, recharge, then re-fire.

## Quick Reference

| Task | Input | Command |
|------|-------|---------|
| Ingest WeChat article | `mp.weixin.qq.com` URL | `scripts/ingest.sh "<url>"` |
| Ingest local PDF | `.pdf` file path | `scripts/ingest.sh "<path>"` |
| Missing URL/path | No location given | Ask first — do not run |

## When to Use

- User says "add this to my KB", "ingest", "save this article", "add to knowledge base"
- User provides a WeChat URL (`mp.weixin.qq.com/...`) and wants it saved
- User provides a local file path ending in `.pdf` and wants it ingested
- User says "remember this" about an article or document

**⚠️ Always use tmux for ingestion.**
Hermes terminal tool has a 900s ceiling. Single-article ingest takes 8-15 min
(UA scrape + LightRAG entity extraction + merge + embedding). Always launch in a
detached tmux session:

```bash
tmux new-session -d -s ingest-<slug> \
  "cd ~/OmniGraph-Vault && PYTHONPATH=. venv/bin/python ingest_wechat.py '<url>' \
   2>&1 | tee /tmp/ingest-$(date +%Y%m%d-%H%M).log; echo 'EXIT='\$?"
```

Then verify with `tmux capture-pane` after ~10 min. Check `clean_lightrag_zombies.py`
if stuck as `processing`.

## When NOT to Use

- User asks "what do I know about X" or "search my KB" → use `omnigraph_query` instead
- User asks for a synthesis report → use `omnigraph_synthesize` instead
- User asks about graph health or node counts → use `omnigraph_status` instead
- User wants to delete or manage entities → use `omnigraph_manage` instead
- URL is not a WeChat article and not a PDF → ask for clarification, do not run blindly

## Decision Tree

### Case 1: WeChat URL provided

Launch in tmux (required — exceeds Hermes terminal 900s ceiling):

```bash
tmux new-session -d -s ingest-article \
  "cd ~/OmniGraph-Vault && PYTHONPATH=. venv/bin/python ingest_wechat.py '<url>' \
   2>&1 | tee /tmp/ingest.log; echo 'EXIT='\$?"
```

Wait ~10 min, then check progress:
```bash
tmux capture-pane -t ingest-article -p | tail -30
```

On completion, verify KV store and clean any zombies:
```bash
venv/bin/python scripts/clean_lightrag_zombies.py
```
Same as Case 1 with the file path.

### Case 3: No URL or file path provided

Ask the user: "Please provide the WeChat article URL or local PDF path."

### Case 4: GEMINI_API_KEY not set

"⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`"

### Case 5: URL not WeChat article and not PDF

"⚠️ This skill only ingests WeChat articles or local PDF files."

## Cron Failure Patterns

When `batch_ingest_from_spider.py --from-db` runs as a cron job, these failure modes
are common. Full timeline at `references/cron-failure-timeline.md` (failure) and
`references/cron-normal-run-20260510.md` (healthy baseline for comparison).

### Case 2: Local PDF path provided

Same as Case 1 but use `multimodal_ingest.py` instead:

```bash
tmux new-session -d -s ingest-pdf \
  "cd ~/OmniGraph-Vault && PYTHONPATH=. venv/bin/python multimodal_ingest.py '<path>' \
   2>&1 | tee /tmp/ingest.log; echo 'EXIT='\$?"
```

### Case 3: No URL or file path provided

**Symptom:** Every article: Apify❌ CDP❌ MCP❌ UA✅ (~90s waste each).

**Fix:** `SCRAPE_CASCADE=ua` env var to skip broken cascade levels.

### F3: Terminal 900s timeout kills mid-batch

**Symptom:** `[Command timed out after 900s]` after 1 article.

**Fix:** tmux detached session:
```bash
bash scripts/cron_daily_ingest.sh 10
```
Script runs batch_ingest in `tmux new-session -d`, independent of Hermes timeouts.

### F5: `--from-db` scope mismatch — pulls full backlog, not today's Layer2

**Symptom:** Re-running `--from-db --max-articles N` after cron failure ingests
different articles than expected. The command queries ALL articles without
`content_hash`, sorted by ID — not just today's Layer2 candidates.

**Example:** 2026-05-08 cron ingested 1/3 Layer2 articles. Manual re-run with
`--max-articles 2` pulled 3 AINLP articles from the 94-article backlog instead
of the 2 remaining Layer2 candidates (#2 Obsidian+CodingAgent, #3 DeepSeek-V4).

**Fix:** Scope to today's scan date:
```bash
PYTHONPATH=. venv/bin/python batch_ingest_from_spider.py \
  --from-db --days-back 1 --max-articles 10
```
Or query `kol_scan.db` first to identify specific article IDs, then use
individual `scripts/ingest.sh <url>` for each target.

### F6: Post-ainsert PENDING — doc inserted but never PROCESSED

**Symptom:** log shows `post-ainsert verification: doc wechat_... status=<DocStatus.PENDING: 'pending'> (not PROCESSED) — skipping content_hash write`. Article counts as `ok` in layer2 tally but LightRAG never finishes graph merge/embedding for it.

**Consequence:** No `content_hash` written to ingestion row. On next cron cycle, the article appears un-ingested and gets re-processed from scratch — wasting Layer1, Layer2, and scrape cycles. If the LightRAG PENDING state persists (stale worker thread), the article will loop forever.

**Detection during cron monitoring:**
```bash
# Check for PENDING docs in LightRAG storage
python3 -c "
import json
f='/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json'
try:
    with open(f) as fh:
        docs = json.load(fh)
        pending = {k:v for k,v in docs.items() if v == 'pending'}
        if pending:
            print(f'PENDING docs: {len(pending)}')
            for k in pending:
                print(f'  {k}')
except FileNotFoundError:
    print('No doc_status file')
"
```

**Fix:**
1. Identify the doc ID from the log warning or from `kv_store_doc_status.json`
2. Remove the affected doc from LightRAG storage (or clean up the status file)
3. Manually re-ingest the specific URL:
   ```bash
   cd ~/OmniGraph-Vault && bash scripts/ingest.sh "<original_url>"
   ```

**Prevention:** None currently — this is a race condition between batch ingest and LightRAG's async graph merge pipeline. The `lightrag_health_check` reference has additional diagnostic steps.

## Error Handling

For detailed cron failure analysis, see `references/cron-failure-timeline.md`.

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Config error: GEMINI_API_KEY not set" |
| Apify quota exceeded | Falls back to CDP then UA. If all fail, use `SCRAPE_CASCADE=ua`. |
| Apify "requires full access" | Actor permissions unapproved. Login to Apify Console, go to Actor → Access → approve. Cascade continues to CDP/UA (wastes ~30s per article). Consider `SCRAPE_CASCADE=ua` until approved. |
| CDP not reachable | "⚠️ CDP unavailable. Start Edge: `msedge --remote-debugging-port=9223`" |
| Gemini 429 | Rate limiter in `ingest_wechat.py` (~4 RPM). Clean zombie docs in `lightrag_storage/`. Switch model if persistent. |
| Gemini 503 | Retry after 30s. Transient. |
| `ret=200003` all accounts | Token is wrong or literal `***` from redaction. See F4. |
| Cron timed out at 900s | Model too slow or cascade waste. See F1-F3 above. |
| UA scrape → 正文缺失/正文环境异常 | WeChat anti-scraping returns empty body. Cascade exhausted → `layer2 enqueue skipped — no body for art_id=N; will retry next tick`. Article is deferred to next cron cycle. This is expected for ~30% of WeChat URLs. |
| Post-ainsert verification PENDING | `doc status=<DocStatus.PENDING: 'pending'> (not PROCESSED) — skipping content_hash write`. Article passed layer2 and was inserted into LightRAG DB but never reached PROCESSED status. **Consequence:** no content_hash written → article can be re-ingested on next cron. **Check:** query `kv_store_doc_status.json` for PENDING docs. **Fix:** manual ingest of the specific URL with `scripts/ingest.sh <url>` after the pipeline completes. |

## Output Format (Success)

```
[article-title] ingested successfully
Images: X downloaded, Y described
Entity extraction queued.
```

## Privacy Note

Article content stored locally in `~/.hermes/omonigraph-vault/`. Images downloaded
locally. Only Gemini API and optionally Apify receive external data.

## Manual Catch-Up Batch (cron_daily_ingest.sh)

For running a bulk catch-up ingest (50+ articles) manually, outside the cron schedule.
This is NOT a cron failure recovery — it's an intentional one-shot batch run.

### Entry Point

```bash
cd ~/OmniGraph-Vault && bash scripts/cron_daily_ingest.sh 50
```

This launches a detached tmux session (`daily-ingest-YYYYMMDD`), runs
`cleanup_stuck_docs` + Layer1 filtering + Layer2 scraping/ingest, and
writes to `/tmp/daily-ingest-YYYYMMDD-HHMM.log`.

### Pre-Flight: Kill Old Zombie (Dead Pane)

Previous smoke tests leave behind tmux sessions with hung vision async drain.
The script detects same-date sessions and exits 1. **If the session is dead**
(pane PID gone), kill manually:

```bash
tmux kill-session -t daily-ingest-$(date +%Y%m%d) 2>/dev/null
```

**Exception — Live Pane from Previous Cron Tick:** If the script exits 1 but
the session's pane process is still running (check with `ps -p <pane_pid>`),
a prior cron tick is still actively ingesting. **Do NOT kill it.** Switch to
monitor mode instead (see Cron Tick Overlap below).

### Cron Tick Overlap (Session Already Running)

When a cron job tries to launch `cron_daily_ingest.sh` but the same-date session
already has live panes (previous tick still running), the script exits 1. This is
**not a failure** — it means the previous tick's ingest is still active. The cron
job should switch to monitor mode. See `references/cron-monitor-example-20260509.md`
for a concrete production walkthrough.

1. **Check tmux session:** `tmux list-panes -t daily-ingest-YYYYMMDD -F '#{pane_pid}'`
2. **Tail log:** Find the latest log with `ls -t /tmp/daily-ingest-YYYYMMDD-*.log | head -1`,
   then `tail -50` for progress/errors
3. **Query DB counts:** Use python3 with explicit path:
   ```python
   import sqlite3
   conn = sqlite3.connect('/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db')
   cur = conn.execute("SELECT source, status, COUNT(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime') GROUP BY source, status")
   print(cur.fetchall())
   ```
4. **Report:** tmux session status + log tail summary + DB counts by source/status
5. **Do NOT** attach to tmux, kill the session, or SIGTERM batch_ingest

### Monitoring: no_agent Script Cronjob (REQUIRED — Agent-Based Fails)

**DO NOT use agent-based monitoring crons.** The LLM agent may skip or simplify
terminal command outputs → Telegram gets empty progress reports. Use a `no_agent`
Python script instead that writes its report directly to stdout — stdout is
delivered verbatim to Telegram with no LLM middle layer.

The canonical monitor script is at `scripts/daily_ingest_monitor.py`. Deploy it:

```bash
hermes cronjob create \
  --name daily-ingest-50-monitor \
  --schedule "every 30m" \
  --deliver telegram \
  --script daily_ingest_monitor.py \
  --no-agent
```

The script handles:
1. DB queries via python3+sqlite3 (NOT `sqlite3` CLI — not installed)
2. Log tail for progress (`[layer1]`/`[layer2]` batch lines)
3. Completion detection: `max-articles cap reached` OR `articles processed`
4. On completion: verify DB counts stable (2 checks 30s apart), kill zombie tmux,
   output full report, write `/tmp/daily_ingest_done` sentinel → silent thereafter
5. Sentinel prevents repeated delivery of the "done" report on subsequent cron ticks

**Why agent-based failed (2026-05-09):** agent with `terminal,send_message,cronjob`
toolsets received terminal output but summarized/omitted it in the Telegram message.
`no_agent=true` + `--script` bypasses all LLM reasoning — stdout IS the message.

### Completion Detection

- `max-articles cap reached (50)` in log tail → batch cap hit
- `376 articles processed` → pool exhausted before cap
- DB counts stable across 2 queries 30s apart → no more in-flight writes
- **batch_timeout_metrics is misleading:** The JSON block at script exit may show
  `completed_articles: 1, not_started_articles: 155` even when **4 articles were
  successfully ingested**. This metric apparently counts only layer2-completed
  threads, not total ingestion rows written. **Do not use it to judge success.**
  Use DB counts (`SELECT source, status, COUNT(*) FROM ingestions WHERE ...`)
  or grep `Successfully Ingested` in the log instead.

### Zombie Cleanup

The tmux session may auto-exit on small batches (max-articles ≤5, ~54 min runtime)
but will **hang as a zombie** on large batches (max-articles 50+, especially with
vision async-drain). After confirming completion:

```bash
tmux kill-session -t daily-ingest-$(date +%Y%m%d)
```

## LightRAG Version Upgrades

### lightrag-hku 1.4.15 (2026-05-18): EmbeddingFunc Wrapper Required

`lightrag-hku==1.4.15` changed `LightRAG.__post_init__` (line 636) to access
`self.embedding_func.func` — expecting an `EmbeddingFunc` dataclass instance,
NOT a bare async function.

**Symptom:**
```
File "lightrag/lightrag.py", line 636, in __post_init__
    )(self.embedding_func.func)
AttributeError: 'function' object has no attribute 'func'
```

**Fix in `lib/lightrag_embedding.py`:**
1. Rename the plain `embedding_func` function to `_embed` (internal helper)
2. At module bottom, wrap it in `EmbeddingFunc`:
```python
from lightrag.utils import EmbeddingFunc

embedding_func = EmbeddingFunc(
    embedding_dim=EMBEDDING_DIM,
    func=_embed,
    max_token_size=EMBEDDING_MAX_TOKENS,
    model_name=EMBEDDING_MODEL,
)
embedding_func.send_dimensions = True
```

**Verification:**
```python
from lightrag.utils import EmbeddingFunc
from lib import embedding_func
assert isinstance(embedding_func, EmbeddingFunc)
assert hasattr(embedding_func, 'func')
```

### Current Version (post-1.4.15, ~2026-05-19): dataclass.replace() + __call__ Required

A subsequent LightRAG upgrade added:
1. `dataclasses.replace(self.embedding_func, func=wrapped_func)` in `__post_init__`
   — requires `EmbeddingFunc` to be a `@dataclass`
2. `self.embedding_func(batch)` in `nano_vector_db_impl.py` upsert
   — requires `EmbeddingFunc` to have `async def __call__`

**Symptom:** First attempt fails with `replace() should be called on dataclass instances`;
second attempt (if code was retried unchanged) fails with
`'EmbeddingFunc' object is not callable`.

**Fix in `lib/lightrag_embedding.py`:**

Convert the project's own `EmbeddingFunc` from a plain class to a `@dataclass`
with an `async __call__`:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class EmbeddingFunc:
    embedding_dim: int
    func: Any  # callable
    max_token_size: int | None = None
    model_name: str | None = None
    send_dimensions: bool = False

    async def __call__(self, *args: Any, **kwargs: Any) -> np.ndarray:
        return await self.func(*args, **kwargs)
```

Do NOT use `lightrag.utils.EmbeddingFunc` here — the project's own class
shields against breakage when upstream LightRAG changes its EmbeddingFunc
interface again. Keep the project-local copy and maintain the dataclass
contract manually.

**Verification:**
```python
from lib.lightrag_embedding import embedding_func
assert hasattr(embedding_func, '__dataclass_fields__'), 'must be @dataclass'
assert callable(embedding_func), 'must have __call__'
import asyncio
assert asyncio.iscoroutinefunction(embedding_func.__call__)
```

Upgrades to future lightrag-hku versions should verify this interface hasn't
changed again before deploying.

## Pitfalls

### LightRAG EmbeddingFunc dataclass incompatibility

**Symptom:** `ingest_wechat.py` or `batch_ingest_from_spider.py` crashes during
`LightRAG.__post_init__` or extract phase:
```
TypeError: replace() should be called on dataclass instances   # init-phase
TypeError: 'EmbeddingFunc' object is not callable              # extract-phase
```

**Root cause:** LightRAG was upgraded to a version where `__post_init__` calls
`dataclasses.replace(self.embedding_func, func=wrapped_func)` (line 638 of
`lightrag.py`), which requires `self.embedding_func` to be a `@dataclass`
instance. The project's custom `EmbeddingFunc` in `lib/lightrag_embedding.py`
was a plain class — not a dataclass, and had no `__call__` method, which the
newer vector DB implementation also requires.

**Fix (applied 2026-05-19 to `lib/lightrag_embedding.py`):**

1. Add `@dataclass` decorator to the project's `EmbeddingFunc` class
2. Convert fields from `__init__` parameters to dataclass field declarations
3. Add `async def __call__` that delegates to `self.func`
4. Add `from dataclasses import dataclass` import

**Verification:**
```python
from lib.lightrag_embedding import embedding_func
print('is dataclass:', hasattr(embedding_func, '__dataclass_fields__'))
print('is callable:', callable(embedding_func))
# Both must be True
```

**Fallback:** If standalone `ingest_wechat.py` consistently fails, add the
article to `kol_scan.db` and let the next cron cycle ingest it via the batch
path. Full details: `references/lightrag-1.4.15-extract-compat.md`

### Other Pitfalls
- **Duplicate ingest**: Always grep `kv_store_doc_status.json` for `wechat_<hash>` before ingesting. If already `processed`, skip. The ingest cycle is 8-15 min per article — duplicates waste API credits.
- **402 Insufficient Balance**: DeepSeek returns 402 mid-extraction. Check `doc_status` error_msg for 402. Recovery: recharge DeepSeek → revert affected ingestions rows to `failed` → delete checkpoint files → re-fire.
- **Foreground terminal ingest**: NEVER run `ingest_wechat.py` directly in foreground. Hermes terminal tool has a 900s ceiling; single ingest takes 8-15 min. Always use `bash scripts/ingest.sh "<url>"` (auto-launches detached tmux).
- **scripts/ingest.sh missing**: If the script doesn't exist, create it from the template in this skill's `templates/` directory before any ingest. The Quick Reference command depends on it.
| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Old session alive — dead pane | Script exits 1 "session already exists", pane PID gone | Kill old session first (see Pre-Flight): `tmux kill-session -t daily-ingest-$(date +%Y%m%d)` |
| Old session alive — live pane | Script exits 1 "session already exists", process actively running | **Do NOT kill.** Previous cron tick's session is still running. Monitor the existing session (check log tail + DB counts) instead of relaunching. |
| `sqlite3` not in PATH | Command not found | Use `python3 -c "import sqlite3..."` instead |
| Wrong home dir | `/home/hai` doesn't exist | WSL home is `/home/sztimhdd` |
| MCP SQLite returns no tables | `mcp_sqlite_read_query` shows 0 tables for `kol_scan.db` | The MCP SQLite tool may be pointed at `./kol_scan.db` (bootstrap-only, no schema). The real DB with `ingestions` table is at **`data/kol_scan.db`**. Use explicit python path: `python3 -c "import sqlite3; conn = sqlite3.connect('data/kol_scan.db')"` |
| Pool unexpectedly small | 376 not 1749 articles | Normal — pool varies by day. Run with what's available |
| Monitoring cron uses agent | DB queries fail or empty Telegram | Use `no_agent=true` + `--script` (see Monitoring section above) |
| Ainsert graph-build silent hang | Log stops for 1.5h+, process S/sleeping, 52 threads, 1.2GB RAM, 147k voluntary ctx switches, lightrag_storage empty, no network sockets | **Distinct from post-loop vision drain.** Process is stuck in LightRAG graph merge/embedding phase. Kill tmux and restart — BUT first run mystery row cleanup (see below) because ingestions may show `ok` for articles that never made it into LightRAG. |
| **UA scrape returns empty body** | Layer2 log shows "正文环境异常无有效内容", "正文缺失", or "正文不可访问" for multiple WeChat URLs. All cascade layers (Apify → CDP → MCP → UA) return None. | WeChat anti-scraping blocks the request. These are logged as `layer2 enqueue skipped — no body for art_id=N; will retry next tick`. **Normal** — ~30% of WeChat URLs fail scrape on any given tick. The article is deferred and re-attempted on the next cron cycle. No action needed unless the same article fails repeatedly for 3+ consecutive days. |
| **Checkpoint-skip dominates loop time** | The per-article loop pauses on ~28 `checkpoint-skip: already-ingested hash=...` lines. This is the main time sink in the scraping phase. | Expected — the script checks `content_hash` against the DB. These are quick hash lookups and only consume ~1-2s each. No action needed. |
| **Enrichment NOT automatic** | WeChat articles go through bare ingest only (Layer1→Layer2→scrape→ainsert). Zhihu 好问 enrichment is NOT part of `cron_daily_ingest.sh`. CDP browser will have no Zhihu visit records. | By design. Enrichment is a separate manual pipeline via the `enrich_article` skill (extract_questions → zhihu-haowen-enrich → fetch_zhihu → merge_and_ingest). To add enrichment to cron, either schedule `enrich_article` as a second cron pass or add it to the batch_ingest loop. |
| Status reports: user wants raw data, not narration | User asks for status reports with explicit "不要 narrate / 不要 summarize / 不要解读" instructions. | When asked for a status report, dump raw command output verbatim. Use `echo "=== section ==="` dividers. Do NOT add interpretation, analysis, or summary paragraphs. Let the user read the raw data and draw their own conclusions. This applies to: cron status checks, DB queries, log analysis, contract reconciliation, pipeline progress monitoring. |
| Non-interference monitoring | User asks to check cron/tmux progress with "不打断不干扰" or "不要打断". | Use `tmux capture-pane` (NOT `tmux attach`), `tail` log files, and `grep` for stage indicators. NEVER kill, SIGTERM, attach to, or interact with the running session. Use `ps -p <pane_pid>` if needed to verify liveness. If session is a zombie (dead pane), kill ONLY after confirming completion via log/DB counts. |
| LightRAG entity extraction returns 0 entities | Articles stored in full_docs (status=processed) but entity/relation counts don't increase. Can query via full-text but not entity graph. | LightRAG entity extraction (DeepSeek LLM) may return empty entity list. Articles ARE searchable via full-text. Check with entity count before/after ingest. Note: DeepSeek 402 "Insufficient Balance" causes doc_status='failed' + 0 entities (different — see mystery-row-cleanup). |

### h09 Smoke Test (Contract Reconciliation)

After deploying commits that touch the ainsert→ingestion boundary (especially
`_verify_doc_processed_or_raise` at commit 949e3f4), run a pre-cron smoke test
to verify the contract: `ingestions.status='ok' == LightRAG doc_status='processed'`.

Full procedure: `references/h09-smoke-test.md`

Quick summary:
1. Baseline — record today's ingestions counts + LightRAG processed count
2. Trigger — `bash scripts/cron_daily_ingest.sh 3` (max 3 articles, ~15-25 min)
3. Poll — wait for tmux to end, kill if >30 min
4. Reconcile — STRICT check (status='processed' only) against new ingestions=ok rows
   - PASS: mystery=0, processed_ok≥1
   - FAIL: mystery≥1 → revert per mystery-row-cleanup.md
   - INCONCLUSIVE: 0 new ok rows (all rejected by Layer1/Layer2)

### Pitfall: h09 False-Negative (h09 Raise=0, Canary Mystery>0)

**Discovered 2026-05-11:** The 09:00 cron's `grep -c "post-ainsert PROCESSED
verification failed"` returned 0, but the 09:30 `reconcile-ingestions` canary
reported `4 ok rows / 0 matched / 4 mystery`.

**Root cause:** `_verify_doc_processed_or_raise` in `ingest_wechat.py` passed (doc_status was PROCESSING, transient, or 'failed'), the outer loop wrote `ingestions.status='ok'`, but LightRAG never completed to 'processed'.

**Common root cause variants:**
- **Race condition:** h09 gate passes on PROCESSING state → outer writes ok → merge never completes
- **DeepSeek 402 "Insufficient Balance":** ainsert LLM calls return 402 → doc_status='failed' → h09 gate treats 'failed' as terminal (not retry-worthy) → passes → ingestions written as 'ok'. Check `error_msg` field in doc_status JSON first.

**Detection:** Only the canary catches this. The h09 log grep cannot — it
only flags explicit verification failures, not silent pass-throughs.

**Recovery:** Mystery row cleanup (references/mystery-row-cleanup.md) +
investigate why h09 gate passed (was doc_status PROCESSING? PENDING? FAILED?).
For 402: recharge DeepSeek → revert mystery rows to failed → verify candidate
pool (SKIP_REASON_VERSION_CURRENT only gates `status='skipped'`, reverted
`status='failed'` rows correctly pass the filter) → re-fire ingest.

### Reconcile Canary (k5q — Daily Automated Contract Check)

The `reconcile-ingestions` cron runs at 09:30 ADT daily. It is an **agent-driven**
cron (NOT no_agent) — output goes to session JSON, not `/tmp/reconcile-*.log`.

To retrieve output, see `references/reconcile-canary.md`.

Quick retrieval:
```bash
python3 -c "
import json
with open('\$(ls -t ~/.hermes/sessions/session_cron_*_0931* | head -1)') as f:
    data = json.load(f)
for m in data.get('messages',[]):
    c = m.get('content','')
    if isinstance(c,str) and 'mystery' in c.lower():
        print(c[:3000])
"
```

### Mystery Row Cleanup (Emergency)

When ainsert hangs after setting `ingestions.status='ok'` but BEFORE LightRAG
persists the doc, the DB has phantom ok rows. If left uncleaned, tomorrow's cron
skips these articles → permanent data loss.

Full 4-step procedure: `references/mystery-row-cleanup.md`

Quick summary:
1. **Reconcile** — Compare `ingestions` ok rows vs `kv_store_doc_status.json`
2. **Backup + Kill** — Backup kol_scan.db (≥16MB), kill tmux session
3. **UPDATE** — Set mystery rows to `status='failed'`
4. **Verify** — Re-reconcile, confirm mystery_post=[]

Audit trail goes to `.scratch/cleanup-*-step{1,2,3,4}-*.log`.

### LightRAG Pipeline Health Check

For checking stuck docs, graph health, and storage hygiene after a hung ingest:
`references/lightrag-health-check.md`

### Pitfall: Stale Code from No Git-Pull in Cron

`cron_daily_ingest.sh` does NOT run `git pull`. If origin has critical fixes
landed after the last manual pull (e.g., D-10.09 vision drain fix at f715f06),
the cron will run stale pre-fix code. After any manual `git pull` or when a
fix lands on origin, verify HEAD before the next cron window:

```bash
cd ~/OmniGraph-Vault && git pull --ff-only && git log --oneline origin/main -3
```

## Related Skills

- `enrich_article` — Zhihu-enriched ingest
- `omnigraph_query` — query ingested content
- `omnigraph_synthesize` — synthesis reports
- `omnigraph_status` — graph health
- `omnigraph_manage` — delete/manage entities

## References

- `references/lightrag-1.4.15-extract-compat.md` — extract-phase EmbeddingFunc object-not-callable error (2026-05-19)
- `references/rss-pipeline-investigation.md` — why 0 RSS articles reached ok status (empirical investigation)
- `references/scraper-coverage-matrix.md` — 45/45 stuck RSS URLs scrapable with simple UA probe (proves bug internal)
- `references/reconcile-canary.md` — daily automated contract check: retrieval, interpretation, false-negative pattern
- `references/mystery-row-cleanup.md` — emergency procedure for phantom ok rows
- `references/h09-smoke-test.md` — pre-cron contract reconciliation smoke test
- `references/lightrag-health-check.md` — LightRAG pipeline health + storage hygiene
- `references/cron-failure-timeline.md` — cron failure patterns and fixes
- `references/cron-normal-run-20260510.md` — healthy baseline for comparison
- `references/cron-monitor-example-20260509.md` — cron tick overlap monitoring workflow
- `references/db-schema.md` — database schema reference
- `references/manual-catch-up-batch.md` — manual bulk catch-up ingest workflow
