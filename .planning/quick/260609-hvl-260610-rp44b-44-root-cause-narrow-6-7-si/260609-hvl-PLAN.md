---
quick: 260609-hvl
description: "260610-rp44b — #44 root cause narrow: 6/7 SIGTERM truncate-window cross-check + (conditional) DeepSeek vs Aliyun-side replay"
type: execute
wave: 1
mode: quick
autonomous: true
diagnostic_only: true
no_code_change: true
files_modified:
  # Diagnostic-only quick. Final commit ships:
  - .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-PLAN.md
  - .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md
  - .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md
  - .planning/STATE.md (last_activity bump)
  # Gitignored evidence (NOT committed):
  # - .scratch/rp44b/journal_*.txt (read-only Aliyun journal greps for bad-doc ingest timestamps)
  # - .scratch/rp44b/cluster_histogram.txt (Phase A bucket analysis)
  # - .scratch/rp44b/replay_<hash>.log + replay_<hash>-result.json (only if Phase B fires)
requirements:
  - RP44B-01: SSH-read-only enumerate ingest start timestamps for the 3 known bad-set article doc_hashes
  - RP44B-02: cluster timestamps in 1h buckets across 6/1-6/9 + cross-check against 6/7 08:00-08:50 CST SIGTERM truncate-window AND 6/8-6/9 daily-ingest cron windows post-atomic-write-patch
  - RP44B-03: emit Phase A verdict (H1 hit / H1 missed) into VERIFICATION.md
  - RP44B-04: GATED — if H1 missed, run isolated Aliyun-side DeepSeek replay (1 doc, /tmp/repro44b_<hash>, cron-idle window), capture entity count + LLM output sample
  - RP44B-05: emit final verdict (H1 / H2 / H3) into VERIFICATION.md with cluster histogram + (if Phase B) replay evidence; recommend follow-up scope (no fix-tier work in this quick)
---

<objective>
Narrow ISSUES #44 (entity-extract 0-entity silent failure) root cause to ONE of three remaining hypotheses after parent quick `260609-eg1` ruled out LightRAG code path + content (3/3 docs ingested cleanly through local Corp Vertex Gemini producing 24 / 47 / 5 entities respectively):

| Hypothesis | Description | Closure path |
|---|---|---|
| **H1** | 6/7 08:40 CST SIGTERM truncate-window collision — doc_status='processed' marker survived but graphml mid-write was killed | Atomic write patch already shipped in `260608-e8l` Step 4 (commit `4b7be6e`) — verifying H1 hits closes #44 cleanly |
| **H2** | DeepSeek-specific entity-extract gap on these particular texts (provider parse swallow / prompt-following failure) | Follow-up quick to fix DeepSeek prompt template OR migrate to vertex_gemini for ingest |
| **H3** | Aliyun-side run-condition (timeout / async race / memory pressure / OOM-kill leaving doc_status='processed' but graphml unwritten) | Follow-up quick to study cron-time LightRAG worker queue / asyncio pressure under prod load |

Methodology: cheap read-only diagnostic. Phase A is 100% read-only SSH (journal grep + sqlite SELECT + json read). Phase B is gated — only fires if Phase A fails to localize H1 — and runs an isolated single-doc replay on Aliyun in a cron-idle window with `/tmp/repro44b_<hash>` working_dir to avoid prod state collision.

**Bad-set premise correction (inherited from parent quick `260609-eg1`):** PLAN-level reference to "96 docs" is wrong. Actual bad set per corrected `chunks_list × graphml source_id` join is **11 docs** total (3 pure `wechat_<10hex>` article docs + 8 `_images` companions). Of the 3 article docs, only 2 still exist in sqlite. Plan operates on the 3 known hashes from parent quick:

| Slot | doc_hash | sqlite_id | body_len | image_count |
|------|----------|-----------|----------|-------------|
| MEDIUM | c7fb080361 | 500 | 5592 | 7 |
| LARGE | edc745d793 | 2445 | 9880 | 11 |
| SHORT | 75c8e99998 | 515 | 85 | 4 |

(Parent `.scratch/repro44/SELECTION.md` documents the corrected join logic — DO NOT re-derive it; reuse.)

Output:
- Phase A: cluster histogram + verdict (H1 hit / H1 missed)
- Phase B (CONDITIONAL): single-doc DeepSeek replay log + LLM output sample (first 2KB)
- VERIFICATION.md citing final verdict + recommended follow-up (no fix in this quick)
- One atomic forward-only commit, push origin/main forward

Strict scope: **NO code change** to production source (`batch_ingest_from_spider.py`, `ingest_wechat.py`, `kb/`, `lib/`, `config.py`); **NO Hermes touches** (RO until 06-22); **NO Aliyun prod LightRAG storage write** (`~/.hermes/omonigraph-vault/lightrag_storage/`); **NO Aliyun prod sqlite write** (read-only OK); **NO Aliyun cron collision** (Phase B uses cron-idle window CST 02:00-06:00 between 08:00 / 14:00 / 20:00 CST daily fires); **NO LightRAG fork**; **NO `pip install --force-reinstall lightrag`** (would wipe atomic-write patch); **NO Corp DeepSeek call** (Cisco Umbrella blocks, Aliyun-only via SSH); **NO new ISSUES row** (#44 already filed; this quick produces follow-up scope per PRINCIPLE #10 — orchestrator updates row, NOT this subagent).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ISSUES.md  <!-- Read row #44 (P0) carefully — context only; DO NOT add a new row, this quick produces follow-up scope -->
@CLAUDE.md  <!-- PRINCIPLE #5 (do mechanical SSH yourself), #7 (Claude owns Databricks/Aliyun), #8 (right-sized GSD: diagnostic ≠ fix), #10 (ISSUES.md tracker — orchestrator-curated) -->
@.planning/quick/260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-SUMMARY.md  <!-- Parent verdict: Path A 0/3 reproduce on Vertex -->
@.planning/quick/260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-VERIFICATION.md  <!-- Parent's evidence + 3 hashes + Reproduction count 0/3 -->
@.scratch/repro44/SELECTION.md  <!-- Corrected chunks_list × source_id join logic — REUSE, DO NOT re-derive -->
@.scratch/repro44/bad_doc_ids.json  <!-- 3 pure hashes: c7fb080361, edc745d793, 75c8e99998 -->

<!-- Memory references — patterns to follow -->
<!-- aliyun_vitaclaw_ssh.md — SSH alias `aliyun-vitaclaw` -->
<!-- feedback_ssh_readonly_vs_writeop_boundary.md — read-only SSH allowed for diagnostics -->
<!-- aliyun_ssh_manual_trigger_env.md — SSH shell does NOT inherit systemd EnvironmentFile=; must wrap `set -a; source /root/.hermes/.env; set +a;` for DeepSeek API key in Phase B -->
<!-- aliyun_translation_pipeline_l2_gated.md — same env-source pattern context -->
<!-- feedback_ssh_throttle_poll_loop.md — #27/#42/#43 banner-timeout class self-heals 1-5h; use `until ssh; sleep 180` background poll-loop with 60-min ceiling, NOT foreground retry storms -->
<!-- 2026_06_08_aliyun_recovery_postmortem.md — full context on the 6/7 SIGTERM truncate at 08:40 CST that birthed #44 -->
<!-- systemd_schedule_overlap_sigterm_corruption.md — Conflicts= cascade SIGTERM windows on overlapping cron firings (the original 6/7 root cause); MemoryHigh/MemoryMax raised in 260608-e8l Step 7 -->
<!-- lightrag_pin_drift_115_vs_116.md — Aliyun prod is LightRAG 1.4.15; venv-aim1 = py3.11 (ingest cron); venv = py3.10 (kb-api). Use venv-aim1 for prod parity in Phase B -->
<!-- lightrag_networkx_write_not_atomic.md — atomic-write patch in `lightrag/kg/networkx_impl.py` (BOTH venvs); pip force-reinstall would wipe -->
<!-- timezone_drift_adt_vs_cst.md — User local = ADT (UTC-3), Aliyun = CST (UTC+8), 11h delta; never assume server log timestamp is local -->

<interfaces>
<!-- Aliyun read-only SSH commands — pre-built so executor doesn't speculate -->

<!-- 1. journal grep per doc_hash — find ingest_from_spider.py lines emitting the hash -->
<!-- Service unit pattern: omnigraph-{daily,afternoon,evening}-ingest.service, see 260608-e8l-SUMMARY.md -->
<!-- Sample command (executor will iterate over the 3 hashes c7fb080361 / edc745d793 / 75c8e99998): -->
<!--
ssh aliyun-vitaclaw "journalctl -u 'omnigraph-*-ingest.service' --since '2026-06-01' --until '2026-06-10' --no-pager | grep -E 'c7fb080361|edc745d793|75c8e99998' | head -200"
-->

<!-- 2. doc_status created_at — secondary timestamp -->
<!-- kv_store_doc_status entry has 'created_at' field per LightRAG schema -->
<!--
ssh aliyun-vitaclaw "python3 -c '
import json
ds = json.loads(open(\"/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json\").read())
for h in (\"wechat_c7fb080361\",\"wechat_edc745d793\",\"wechat_75c8e99998\"):
    e = ds.get(h, {})
    print(h, e.get(\"created_at\"), e.get(\"updated_at\"), e.get(\"chunks_count\"), e.get(\"status\"))
'"
-->

<!-- 3. Daily-ingest cron windows (post-atomic-write-patch boundary 2026-06-08 22:04 CST) -->
<!-- 260608-e8l Step 7 manual fire: 22:04:50-22:37:15 CST (5/5 articles, atomic write VERIFIED in production: graphml grew +47KB, +29 nodes, +51 edges, no .tmp orphan) -->
<!-- Subsequent timer-driven fires: 06-09 08:00 / 14:00 / 20:00 CST (per 260608-e8l Step 7 close) -->
<!-- 6/7 truncate window per 260608-e8l Step 4 SUMMARY: 08:40 CST graphml mid-write SIGTERM, exact boundary 08:00-08:50 CST -->

<!-- 4. Phase B (CONDITIONAL) Aliyun-side replay env -->
<!-- Aliyun .env (`/root/.hermes/.env`) is the systemd EnvironmentFile - plain SSH shell does NOT source it -->
<!-- Per memory aliyun_ssh_manual_trigger_env.md, must wrap with `set -a; source /root/.hermes/.env; set +a;` -->
<!-- Aliyun prod provider: OMNIGRAPH_LLM_PROVIDER=deepseek (per .env), OMNIGRAPH_LLM_MODEL=deepseek-chat -->
<!-- venv-aim1 (Python 3.11) for LightRAG 1.4.15 + atomic-write patch parity -->

<!-- 5. Cron-idle window CST 02:00-06:00 -->
<!-- Aliyun's 3 daily ingests (per aim-3 systemd timers) fire at 08:00 / 14:00 / 20:00 CST -->
<!-- Max gap between cron fires = 12h (20:00 yesterday → 08:00 today). Sub-window 02:00-06:00 CST = ADT 13:00-17:00 prior day -->
<!-- Conflicts= directive on each unit prevents overlap, but Phase B avoiding cron-near windows protects against schedule shift -->

<!-- 6. Bad-doc article body source — read-only sqlite (already done in parent quick, files exist) -->
<!-- .scratch/repro44/c7fb080361.json + edc745d793.json + 75c8e99998.json contain article.body field -->
<!-- Phase B reads from one of these (NOT from Aliyun sqlite again) -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Phase A — SIGTERM truncate-window cross-check (~30 min, READ-ONLY)</name>
  <files>
    .scratch/rp44b/journal_c7fb080361.txt
    .scratch/rp44b/journal_edc745d793.txt
    .scratch/rp44b/journal_75c8e99998.txt
    .scratch/rp44b/doc_status_timestamps.txt
    .scratch/rp44b/cluster_histogram.txt
    .scratch/rp44b/phase_a_verdict.md
  </files>
  <action>
**This task runs SSH read-only against `aliyun-vitaclaw`. NO writes to Aliyun. Per PRINCIPLE #5, agent runs SSH directly via Bash tool — DO NOT outsource to user.**

The 3 known bad-set article hashes (from parent quick `.scratch/repro44/bad_doc_ids.json` and SELECTION.md):
- `c7fb080361` (sqlite_id=500, body_len=5592, image_count=7) — MEDIUM
- `edc745d793` (sqlite_id=2445, body_len=9880, image_count=11) — LARGE
- `75c8e99998` (sqlite_id=515, body_len=85, image_count=4) — SHORT (anti-bot boilerplate)

LightRAG doc_id form: `wechat_<hash>` (prefix) — both forms appear in journal lines depending on log path.

**Step 1.1 — Create scratch dir:**

```bash
mkdir -p .scratch/rp44b
```

**Step 1.2 — Per-hash journal grep (read-only SSH):**

For each hash, grep the union of `omnigraph-*-ingest.service` journals across 6/1-6/10. Capture the line(s) showing the hash was being ingested:

```bash
for H in c7fb080361 edc745d793 75c8e99998; do
  ssh aliyun-vitaclaw "journalctl -u 'omnigraph-daily-ingest.service' -u 'omnigraph-afternoon-ingest.service' -u 'omnigraph-evening-ingest.service' --since '2026-06-01' --until '2026-06-10' --no-pager 2>/dev/null | grep -E '$H|wechat_$H' || echo '__NO_MATCH__'" > ".scratch/rp44b/journal_$H.txt"
  echo "=== $H ==="
  head -5 ".scratch/rp44b/journal_$H.txt"
  wc -l ".scratch/rp44b/journal_$H.txt"
done
```

If a hash returns `__NO_MATCH__`, that's still a data point (means the doc was ingested before 6/1 OR journal rotation has dropped older entries OR doc_id form differs in logs). Capture the result anyway and note in `phase_a_verdict.md`.

**Step 1.3 — doc_status created_at fallback (read-only SSH):**

For any hash with no journal hit, fall back to LightRAG's per-doc `created_at` / `updated_at` field as secondary timestamp:

```bash
ssh aliyun-vitaclaw "python3 -c '
import json
ds = json.loads(open(\"/root/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json\").read())
for h in (\"wechat_c7fb080361\",\"wechat_edc745d793\",\"wechat_75c8e99998\"):
    e = ds.get(h, {})
    print(h, \"created_at=\", e.get(\"created_at\"), \"updated_at=\", e.get(\"updated_at\"), \"chunks_count=\", e.get(\"chunks_count\"), \"status=\", e.get(\"status\"))
'" > .scratch/rp44b/doc_status_timestamps.txt
cat .scratch/rp44b/doc_status_timestamps.txt
```

**Step 1.4 — Cluster analysis (local, no SSH):**

Build a 1-hour-bucket histogram of bad-doc ingest timestamps across 6/1-6/9 (CST). For each timestamp source (journal first, doc_status fallback):
1. Extract timestamp (ISO 8601 or `YYYY-MM-DD HH:MM:SS CST`)
2. Bucket to nearest hour `YYYY-MM-DD HH:00 CST`
3. Tally per-bucket count

**Cross-check windows (annotate buckets):**

| Window | Boundary (CST) | Significance |
|--------|-----------------|--------------|
| W1: 6/7 truncate | 08:00-08:50 6/7 | SIGTERM mid-write killed graphml (per `260608-e8l-SUMMARY.md` Step 4) |
| W2: 6/8 daily-ingest manual fire (post-atomic-patch) | 22:04-22:37 6/8 | First ingest run AFTER atomic-write patch shipped |
| W3: 6/9 timer-driven cron fires | 08:00-? / 14:00-? / 20:00-? 6/9 | Daily timer cadence post-260608-e8l recovery |
| W4: any other Conflicts= cascade SIGTERM windows | (search journal for `Conflicts=` / SIGTERM lines) | Pre-260608-e8l overlapping cron schedule trap (per memory `systemd_schedule_overlap_sigterm_corruption`) |

Scan cluster output for: (a) what fraction of bad-doc timestamps fall inside W1; (b) whether ANY bad-doc timestamps fall inside W2 or W3 (post-atomic-patch).

**Step 1.5 — Write `.scratch/rp44b/cluster_histogram.txt`:**

```
=== bad-doc ingest timestamp histogram (CST, 1h buckets) ===
Source: journal first, doc_status created_at fallback

YYYY-MM-DD HH:00 | count | hash(es) | window-tag
-----------------+-------+----------+-----------
2026-06-07 08:00 | 2     | c7fb…/edc7… | W1 (6/7 truncate)
2026-06-05 14:00 | 1     | 75c8…    | (no window)
...

=== window membership tally ===
W1 (6/7 08:00-08:50 truncate): X / 3 hashes
W2 (6/8 22:04-22:37 manual atomic-fire): X / 3
W3 (6/9 timer fires): X / 3
W4 (other SIGTERM cascade): X / 3
Outside-any-window: X / 3

=== W1-cluster threshold ===
≥80% of bad docs in W1 ?  YES / NO
ANY bad doc in W2 or W3 (post-atomic-patch new failure) ?  YES / NO
```

**Step 1.6 — Phase A verdict gate. Write `.scratch/rp44b/phase_a_verdict.md`:**

| Outcome | Action | Verdict slug |
|---|---|---|
| ≥80% bad docs cluster in W1 (or other clear pre-atomic-patch SIGTERM window) **AND** zero bad docs in W2/W3 | **H1 命中** — atomic-write fix in `260608-e8l` Step 4 commit `4b7be6e` closes recurrence path | `H1_HIT` |
| <80% W1-cluster, **OR** ≥1 bad doc in W2/W3 (post-patch new failure) | **H1 missed** — proceed to Phase B (Task 2) | `H1_MISSED` |
| All 3 hashes have no timestamp in journal AND no doc_status timestamp | **INCONCLUSIVE** — log finding, recommend follow-up to find pre-6/1 archive sources | `INCONCLUSIVE` |

The verdict file should contain ONE of `H1_HIT` / `H1_MISSED` / `INCONCLUSIVE` plus the justification (cluster fractions + window membership counts).

**Halt rules (Phase A):**

| Symptom | Action |
|---------|--------|
| SSH banner timeout (#27/#42/#43-class) | Background poll-loop pattern per memory `feedback_ssh_throttle_poll_loop`: `until ssh aliyun-vitaclaw "true"; do sleep 180; done` with 60-min ceiling. NO foreground retry storms. |
| journalctl returns 0 lines for all 3 hashes AND doc_status has created_at | Use doc_status timestamps; note in verdict that journal rotation may have aged out |
| journalctl + doc_status BOTH miss any timestamp for all 3 | Verdict = INCONCLUSIVE; do NOT proceed to Phase B (different root needs different probe) |

**Constraints:**
- 100% read-only SSH. NO `INSERT`, `UPDATE`, `DELETE`, `cp`, `rm`, `mv`, `systemctl restart`, `git pull`, `docker stop` on Aliyun.
- All scratch output goes under `.scratch/rp44b/` which is gitignored via `.scratch/`.
- No Aliyun .env mutation. No Aliyun python wheel install. No Aliyun systemd timer change.
  </action>
  <verify>
    <automated>test -f .scratch/rp44b/cluster_histogram.txt && test -f .scratch/rp44b/phase_a_verdict.md && grep -qE "H1_HIT|H1_MISSED|INCONCLUSIVE" .scratch/rp44b/phase_a_verdict.md && for H in c7fb080361 edc745d793 75c8e99998; do test -f .scratch/rp44b/journal_$H.txt || { echo "missing journal_$H.txt"; exit 1; }; done && test -f .scratch/rp44b/doc_status_timestamps.txt</automated>
  </verify>
  <done>
    `.scratch/rp44b/` contains 3 per-hash journal grep outputs + doc_status timestamps + cluster histogram + phase_a_verdict.md citing one of H1_HIT / H1_MISSED / INCONCLUSIVE with justification (W1 cluster %, post-patch hit count). Zero Aliyun mutation events.
  </done>
</task>

<task type="auto">
  <name>Task 2: Phase B (CONDITIONAL) — Aliyun isolated DeepSeek replay (~1.5h, GATED on Phase A)</name>
  <files>
    .scratch/rp44b/replay_<hash>.log
    .scratch/rp44b/replay_<hash>-result.json
    .scratch/rp44b/phase_b_verdict.md
  </files>
  <action>
**HALT GATE — DO NOT EXECUTE THIS TASK IF PHASE A VERDICT IS `H1_HIT` OR `INCONCLUSIVE`.**

Read `.scratch/rp44b/phase_a_verdict.md`:
- If verdict = `H1_HIT`: SKIP this task entirely. Jump to Task 3 and write VERIFICATION.md citing H1 verdict.
- If verdict = `INCONCLUSIVE`: SKIP this task entirely. Jump to Task 3 and write VERIFICATION.md citing INCONCLUSIVE verdict + recommend a different probe (pre-6/1 archive).
- If verdict = `H1_MISSED`: PROCEED with Phase B below.

**Phase B summary:** isolated single-doc replay on Aliyun (cron-idle window) using prod DeepSeek + venv-aim1 (LightRAG 1.4.15 prod parity), into `/tmp/repro44b_<hash>` working_dir to avoid prod state collision.

**Step 2.1 — Pick the replay doc.**

Preferred priority order (pick first that exists in the bad set):
1. A 6/8 or 6/9 fresh failure (post-atomic-patch) — strongest H3 signal
2. A pre-6/7 baseline failure (rules out SIGTERM context cleanly)
3. Default: `c7fb080361` (MEDIUM, 5592 chars, real Claude-Code-conversation content; non-boilerplate)

Document the choice + rationale in the replay log.

**Step 2.2 — Pick a cron-idle window.**

Aliyun cron fires at 08:00 / 14:00 / 20:00 CST per aim-3 systemd timers (max 12h gap between 20:00 yesterday → 08:00 today). Sub-window CST 02:00-06:00 (= ADT 13:00-17:00 prior day) gives 6h cushion to next 08:00 fire.

Verify the window before launch:
```bash
ssh aliyun-vitaclaw "systemctl list-timers --no-pager | grep -E 'omnigraph|ingest'"
ssh aliyun-vitaclaw "date '+%Y-%m-%d %H:%M:%S %Z (%z)'"
```

If next cron fire is < 2h away, defer Phase B by waiting for the gap window. Do NOT collide with a live cron run.

**Step 2.3 — Setup isolated working dir on Aliyun (read-only inputs, write only to `/tmp/repro44b_<hash>`):**

```bash
HASH=c7fb080361   # or whichever doc was picked in 2.1
ssh aliyun-vitaclaw "mkdir -p /tmp/repro44b_$HASH && ls -la /tmp/repro44b_$HASH"
```

**Step 2.4 — Construct the replay command. Honor the env-source pattern per memory `aliyun_ssh_manual_trigger_env.md`:**

The Aliyun .env has `OMNIGRAPH_LLM_PROVIDER=deepseek`, `OMNIGRAPH_LLM_MODEL=deepseek-chat`, `DEEPSEEK_API_KEY=<real>`, etc. Plain SSH shell does NOT inherit systemd `EnvironmentFile=` — must wrap.

Override `OMNIGRAPH_BASE_DIR=/tmp/repro44b_$HASH` to redirect LightRAG storage writes; keep all other env vars at prod values.

Read article body from sqlite (read-only) inside the same SSH command (do NOT scp the body to local; this is Aliyun-only):

```bash
ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; \
  export OMNIGRAPH_BASE_DIR=/tmp/repro44b_$HASH; \
  export OMNIGRAPH_LLM_PROVIDER=deepseek; \
  export OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter,gemini; \
  cd /root/OmniGraph-Vault && \
  venv-aim1/bin/python3 -c '
import asyncio, json, os, sqlite3, sys, time, traceback, xml.etree.ElementTree as ET
from pathlib import Path

HASH = \"$HASH\"
WD = Path(os.environ[\"OMNIGRAPH_BASE_DIR\"]) / \"lightrag_storage\"
WD.mkdir(parents=True, exist_ok=True)

# 1. Read body from sqlite (read-only)
conn = sqlite3.connect(\"/root/OmniGraph-Vault/data/kol_scan.db\")
conn.row_factory = sqlite3.Row
row = conn.execute(\"SELECT id, content_hash, body, image_count FROM articles WHERE content_hash=?\", (HASH,)).fetchone()
conn.close()
assert row, f\"hash {HASH} not in sqlite\"
body = row[\"body\"] or \"\"
print(f\"body_len={len(body)} sqlite_id={row[\\\"id\\\"]} images={row[\\\"image_count\\\"]}\", flush=True)

# 2. Build LightRAG with DeepSeek + isolated working_dir
sys.path.insert(0, \"/root/OmniGraph-Vault\")
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status
from lib import embedding_func
from lib.llm_complete import get_llm_func

rag = LightRAG(
    working_dir=str(WD),
    llm_model_func=get_llm_func(),
    embedding_func=embedding_func,
    default_embedding_timeout=int(os.environ.get(\"LIGHTRAG_EMBEDDING_TIMEOUT\", \"180\")),
)

async def run():
    await rag.initialize_storages()
    await initialize_pipeline_status()
    t0 = time.monotonic()
    try:
        await rag.ainsert(body, ids=[HASH])
        exc = None
    except Exception as e:
        exc = f\"{type(e).__name__}: {e}\"
        traceback.print_exc()
    wall = round(time.monotonic()-t0, 2)
    # Count entities
    n_ent, gstatus = 0, \"missing\"
    g = WD / \"graph_chunk_entity_relation.graphml\"
    if g.exists():
        try:
            ns = {\"g\": \"http://graphml.graphdrawing.org/xmlns\"}
            tree = ET.parse(str(g))
            root = tree.getroot()
            src_key = None
            for k in root.findall(\"g:key\", ns):
                if k.get(\"attr.name\") == \"source_id\":
                    src_key = k.get(\"id\"); break
            for node in root.findall(\"g:graph/g:node\", ns):
                for data in node.findall(\"g:data\", ns):
                    if data.get(\"key\") == src_key and data.text and HASH in data.text:
                        n_ent += 1; break
            gstatus = \"ok\"
        except Exception as e:
            gstatus = f\"corrupt:{e}\"
    # Read doc_status
    ds_status, chunks_count = None, None
    ds_path = WD / \"kv_store_doc_status.json\"
    if ds_path.exists():
        ds = json.loads(ds_path.read_text())
        entry = ds.get(HASH) or {}
        ds_status = entry.get(\"status\")
        chunks_count = entry.get(\"chunks_count\")
    await rag.finalize_storages()
    print(\"=== RESULT ===\", flush=True)
    print(json.dumps({
        \"hash\": HASH,
        \"body_len\": len(body),
        \"wall_s\": wall,
        \"exception\": exc,
        \"status\": ds_status,
        \"chunks_count\": chunks_count,
        \"entity_count\": n_ent,
        \"graphml\": gstatus,
        \"provider\": os.environ.get(\"OMNIGRAPH_LLM_PROVIDER\"),
        \"model\": os.environ.get(\"OMNIGRAPH_LLM_MODEL\"),
    }, indent=2))

asyncio.run(run())
' 2>&1 " | tee ".scratch/rp44b/replay_$HASH.log"
```

Capture stdout + stderr to `.scratch/rp44b/replay_$HASH.log`. Extract the `=== RESULT ===` JSON block to `.scratch/rp44b/replay_$HASH-result.json`.

**Step 2.5 — Capture LLM output sample for evidence:**

The replay log may contain LightRAG's per-chunk `INFO: Chunk N of M extracted X Ent + Y Rel` lines. If 0 entities, capture the first 2KB of any LLM response that LightRAG logged at DEBUG level (some provider wrappers log raw responses on DEBUG). If logging didn't surface raw responses, note that in the verdict file (still useful — absence of structured "extracted N Ent" line at INFO level itself signals the failure mode).

**Step 2.6 — Write `.scratch/rp44b/phase_b_verdict.md`:**

| Result | Verdict | Implication |
|---|---|---|
| `entity_count == 0` AND `status == "processed"` | **H2 命中** — DeepSeek-specific entity-extract gap reproduces on isolated working_dir; rules out Aliyun storage state | Follow-up quick `260611-*` to (a) capture raw DeepSeek response on these texts and (b) decide DeepSeek prompt fix vs vertex_gemini migration for ingest |
| `entity_count > 0` AND `status == "processed"` | **H3 命中** — DeepSeek extracts cleanly in isolated working_dir; bug must be Aliyun-side run-condition under prod load | Follow-up quick `260611-*` to study cron-time worker queue / asyncio pressure / OOM-kill window during prod load |
| `exception is not None` | **PROBE-BLOCKED** — env / network / SDK error; not a verdict on H2 vs H3 | Document exception, recommend retry with fix (likely env-source typo or DeepSeek API expired) |
| Replay wall > 1800s without completion | **AMBIGUOUS** — could be H3 (timeout race) but also probe-side. Re-check cron-window collision. | Document, recommend re-run in different cron-idle window |

The verdict file should contain ONE of `H2_HIT` / `H3_HIT` / `PROBE_BLOCKED` / `AMBIGUOUS` plus result JSON snippet + LLM output sample (or absence note).

**Halt rules (Phase B):**

| Symptom | Action |
|---------|--------|
| Cron is firing within 2h | Wait for next cron-idle window OR halt + document deferral |
| `set -a; source /root/.hermes/.env` fails (file moved/permission) | HALT — Aliyun env state changed; re-verify with `ls -la /root/.hermes/.env` |
| DeepSeek API 401 / 402 (key expired or balance depleted) | HALT — document; recommend Hermes operator refresh DeepSeek key |
| LightRAG ImportError under venv-aim1 (vendor patch wiped by accident) | HALT — do NOT pip-reinstall; recommend manual patch re-apply via `260608-e8l` Step 4 procedure |
| /tmp/repro44b_$HASH already exists with prior run state | `rm -rf /tmp/repro44b_$HASH/lightrag_storage` (NOT prod path — `/tmp` only) and retry |
| Cron-idle window exhausted mid-run (Phase B started 02:00 CST but ran past 06:00 CST and now collides with 08:00 fire) | The Conflicts= mutex protects prod (08:00 fire blocks until Phase B finishes), but document the schedule shift |

**Constraints:**
- ONLY `/tmp/repro44b_<hash>` is writable. Aliyun prod paths (`/root/.hermes/omonigraph-vault/lightrag_storage`, `/root/OmniGraph-Vault/data/kol_scan.db` for write, systemd units, docker containers) are READ-ONLY in this task.
- NO Corp DeepSeek call. All DeepSeek calls happen Aliyun-side via SSH-wrapped python.
- NO Hermes touches (RO until 06-22).
- NO `pip install` on Aliyun (would risk wiping atomic-write patch in venv-aim1 lightrag/kg/networkx_impl.py).
- Use `venv-aim1` (Python 3.11, ingest cron's prod venv) for LightRAG 1.4.15 + atomic-write patch parity.
- Vision providers all skipped (`OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter,gemini`) — this probe is text-only entity-extract; no images involved.
  </action>
  <verify>
    <automated>if grep -qE "^H1_HIT|^INCONCLUSIVE" .scratch/rp44b/phase_a_verdict.md 2>/dev/null; then echo "Phase B SKIPPED per Phase A gate (H1_HIT or INCONCLUSIVE) — task verify trivially passes"; exit 0; else test -f .scratch/rp44b/phase_b_verdict.md && grep -qE "H2_HIT|H3_HIT|PROBE_BLOCKED|AMBIGUOUS" .scratch/rp44b/phase_b_verdict.md && ls .scratch/rp44b/replay_*.log 2>/dev/null | head -1 | grep -q "replay_" && ls .scratch/rp44b/replay_*-result.json 2>/dev/null | head -1 | grep -q "result"; fi</automated>
  </verify>
  <done>
    Either: (a) Phase A verdict was H1_HIT or INCONCLUSIVE → this task skipped (verifier trivially passes), Task 3 picks up directly; OR (b) Phase A was H1_MISSED → exactly one replay log + one result JSON exist under `.scratch/rp44b/`, plus phase_b_verdict.md citing H2_HIT / H3_HIT / PROBE_BLOCKED / AMBIGUOUS with result JSON snippet + (where present) LLM output sample. Zero Aliyun prod state mutation; only `/tmp/repro44b_<hash>` written.
  </done>
</task>

<task type="auto">
  <name>Task 3: Write VERIFICATION.md + SUMMARY.md, update STATE.md, atomic forward-only commit + push</name>
  <files>
    .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md
    .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md
    .planning/STATE.md
  </files>
  <action>
**Step 3.1 — Synthesize the final verdict from Phase A (and, if applicable, Phase B) verdicts:**

| Phase A | Phase B | Final verdict | Recommended follow-up |
|---|---|---|---|
| H1_HIT | (skipped) | **H1 — 6/7 SIGTERM truncate-window collision** | Recommend ISSUES.md #44 row → `RESOLVED 2026-06-10 by atomic write patch (260608-e8l Step 4 commit 4b7be6e); follow-up paths X/Y for graphml↔Qdrant divergence remain open as separate work`. NO new fix-tier quick needed — atomic write already shipped. |
| INCONCLUSIVE | (skipped) | **INCONCLUSIVE** — journal aged-out / doc_status missing | Recommend follow-up quick `260611-*-rp44c-archive-source` to find pre-6/1 timestamps from log archives or Hermes-side history (post 06-22 RO unfreeze) |
| H1_MISSED | H2_HIT | **H2 — DeepSeek-specific entity-extract gap** | Recommend follow-up quick `260611-*-rp44c-deepseek-prompt` (raw DeepSeek response capture + prompt template fix OR ingest provider migration to vertex_gemini) |
| H1_MISSED | H3_HIT | **H3 — Aliyun-side run-condition** | Recommend follow-up quick `260611-*-rp44c-aliyun-run-condition` (study cron-time LightRAG worker queue / asyncio pressure / OOM-kill window during prod load) |
| H1_MISSED | PROBE_BLOCKED | **PROBE-BLOCKED** | Recommend re-run quick after fixing probe blocker |
| H1_MISSED | AMBIGUOUS | **PARTIAL — H1 ruled out, H2/H3 not disambiguated** | Recommend re-run Phase B with longer wall budget OR different cron-idle window |

**Step 3.2 — Write `260609-hvl-VERIFICATION.md`:**

```markdown
---
quick: 260609-hvl
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES.md row #44 (P0)
status: passed
verdict: "{H1 / H2 / H3 / INCONCLUSIVE / PROBE-BLOCKED / PARTIAL}"
followup_slug: "{260611-*-... or 'no-followup-h1-already-fixed'}"
followup_mode: "{/gsd:quick OR DEFER OR NONE}"
---

# 260609-hvl VERIFICATION — #44 root cause narrow

**Quick:** 260609-hvl
**Filed:** 2026-06-09
**Mode:** diagnostic (NO code change, NO prod state mutation)
**Issue:** [ISSUES.md row #44](../../ISSUES.md) (P0 — graphml↔Qdrant 14-day divergence; entity-extract 0-entity silent failure)
**Parent quick:** [260609-eg1](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-VERIFICATION.md) — Path A 0/3 reproduce on Vertex (rules out LightRAG code path + content)

## Premise correction (inherited from parent)

Bad set per corrected `chunks_list × source_id` join is **11 docs** (3 pure `wechat_<hex>` article docs + 8 `_images` companions), NOT 96. Of the 3 article docs, only 2 still in sqlite. Plan operates on the 3 known hashes from parent quick.

## Phase A — SIGTERM truncate-window cross-check

### Hashes investigated

| Slot | doc_hash | sqlite_id | body_len |
|------|----------|-----------|----------|
| MEDIUM | c7fb080361 | 500 | 5592 |
| LARGE | edc745d793 | 2445 | 9880 |
| SHORT | 75c8e99998 | 515 | 85 |

### Timestamps recovered

| Hash | Source | Timestamp (CST) | Window-tag |
|------|--------|------------------|------------|
| ... | journal/doc_status | YYYY-MM-DD HH:MM | W1 / W2 / W3 / outside |

### Cluster histogram

{paste contents of `.scratch/rp44b/cluster_histogram.txt` window-membership tally}

### Phase A verdict

**{H1_HIT / H1_MISSED / INCONCLUSIVE}**

{Justification — cite cluster fraction, post-patch new-failure presence/absence, with concrete numbers.}

## Phase B — DeepSeek replay {EXECUTED / SKIPPED-per-gate}

{IF SKIPPED: "Phase B was skipped per the gate (Phase A verdict = H1_HIT / INCONCLUSIVE). The atomic-write fix shipped in 260608-e8l Step 4 commit 4b7be6e closes the H1 recurrence path."}

{IF EXECUTED:}

### Replay configuration

- Doc: `<hash>` (sqlite_id=`<id>`, body_len=`<N>`)
- Window: `<CST start - CST end>` (cron-idle gap between `<prev>` and `<next>` cron fires)
- Working dir: `/tmp/repro44b_<hash>/lightrag_storage` (isolated; prod paths read-only)
- Provider: deepseek (`<model>`)
- venv: venv-aim1 (Python 3.11, LightRAG 1.4.15, atomic-write patched per 260608-e8l)

### Replay result

```json
{paste from .scratch/rp44b/replay_<hash>-result.json}
```

### LLM output sample (first 2KB or absence note)

{paste sample OR note "no raw LLM response surfaced at INFO level; LightRAG INFO logs `Chunk N of M extracted X Ent + Y Rel` line absent for all chunks"}

### Phase B verdict

**{H2_HIT / H3_HIT / PROBE_BLOCKED / AMBIGUOUS}**

{Justification — cite entity_count, status, exception (if any).}

## Final verdict

**{H1 / H2 / H3 / INCONCLUSIVE / PROBE-BLOCKED / PARTIAL}**

{1-3 sentence justification combining Phase A + Phase B (where applicable).}

## Recommended follow-up

**Slug:** `{slug or "no-followup"}`
**Mode:** `{/gsd:quick OR DEFER OR NONE}`
**Rationale:** {why this matches the verdict}

**ISSUES.md row #44 update guidance** (orchestrator updates row, NOT this subagent):
- If H1: status='resolved 2026-06-10 by atomic write patch (260608-e8l Step 4 commit 4b7be6e); follow-up paths X/Y for graphml↔Qdrant divergence remain open as separate work'
- If H2: status='narrowed to DeepSeek-specific entity-extract gap; follow-up quick {slug} to capture raw response + prompt fix decision'
- If H3: status='narrowed to Aliyun-side run-condition; follow-up quick {slug} to study cron-time worker queue / asyncio pressure'
- If INCONCLUSIVE / PROBE_BLOCKED / PARTIAL: status='narrow attempt {date} did not localize root cause; follow-up quick {slug} to re-run with adjusted probe'

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md) — graphml↔Qdrant 14-day divergence
- [260609-eg1 VERIFICATION](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-VERIFICATION.md) — Path A parent (Vertex 3/3 normal)
- [260608-e8l SUMMARY](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md) — graphml truncation 6/7 08:40 CST + atomic write structural fix (commit 4b7be6e)
- Memory `2026_06_08_aliyun_recovery_postmortem`
- Memory `systemd_schedule_overlap_sigterm_corruption`
- Memory `lightrag_pin_drift_115_vs_116`
- Memory `feedback_ssh_throttle_poll_loop`
- Memory `aliyun_ssh_manual_trigger_env`
- Local evidence: `.scratch/rp44b/journal_*.txt`, `.scratch/rp44b/cluster_histogram.txt`, `.scratch/rp44b/phase_a_verdict.md`{IF Phase B ran: ", `.scratch/rp44b/replay_*.log`, `.scratch/rp44b/replay_*-result.json`, `.scratch/rp44b/phase_b_verdict.md`"}
```

**Step 3.3 — Write `260609-hvl-SUMMARY.md`** (close-out narrative):

```markdown
---
quick: 260609-hvl
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES #44 (P0)
verdict: "{from VERIFICATION.md}"
followup_slug: "{from VERIFICATION.md}"
---

# Quick 260609-hvl — SUMMARY

Diagnostic-only quick. Goal: narrow ISSUE #44 root cause to ONE of three hypotheses (H1 SIGTERM truncate / H2 DeepSeek-specific / H3 Aliyun-side run-condition) after parent quick `260609-eg1` ruled out LightRAG code path + content (Vertex 0/3 reproduce).

## Outcome

**{Final verdict}.** {1-paragraph plain-English summary citing Phase A + B verdicts, key numbers, and what each means for #44 path cost.}

## Phase summary

- **Phase A** (SIGTERM cross-check, ~30 min, READ-ONLY SSH): {verdict + key numbers — W1 cluster fraction, post-patch hits}
- **Phase B** ({EXECUTED / SKIPPED}, ~1.5h if ran): {verdict + key numbers — entity_count, status; OR "skipped per gate"}

## Premise correction

(Inherited from parent quick.) Bad set is 11 docs not 96. 3 article hashes from parent: c7fb080361 / edc745d793 / 75c8e99998.

## Recommended follow-up

**Slug:** `{from VERIFICATION.md}`
**Mode:** `{/gsd:quick / DEFER / NONE}`

{1-2 sentences on why.}

## Discipline checklist

- [x] No production source change (`batch_ingest_from_spider.py`, `ingest_wechat.py`, `kb/`, `lib/`, `config.py` untouched)
- [x] No LightRAG fork (no `pip install --force-reinstall lightrag`; atomic-write patch in venv-aim1 NOT modified)
- [x] No Hermes touches (RO until 2026-06-22 honored)
- [x] No Aliyun prod state mutation (Phase A read-only SSH; Phase B writes only to `/tmp/repro44b_<hash>`)
- [x] No Aliyun cron collision (Phase B in cron-idle window CST 02:00-06:00 OR skipped)
- [x] No Corp DeepSeek call (Aliyun-side only; Cisco Umbrella block honored)
- [x] No literal secrets in any committed artifact (DeepSeek key / SA token stay in Aliyun .env, not echoed to scratch)
- [x] Forward-only commit; explicit `git add <files>` (NEVER `-A`)
- [x] No `--amend` / `reset --hard` / `--force-push` per `feedback_no_amend_in_concurrent_quicks`
- [x] omonigraph typo preserved
- [x] No new ISSUES.md row added (per PRINCIPLE #10 — orchestrator curates, this quick produces follow-up scope only)

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md)
- [260609-eg1 SUMMARY](../260609-eg1-260609-rp44-path-a-corp-44-entity-extrac/260609-eg1-SUMMARY.md)
- [260608-e8l SUMMARY](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md)
- Local evidence under `.scratch/rp44b/` (gitignored)

## Wall-clock

~{N} min total ({Phase A} + {Phase B if ran or 0}).
```

**Step 3.4 — Update `.planning/STATE.md`:**

Insert ONE new "Quick Tasks Completed" table row (or append to existing — match existing format) with:

| field | value |
|---|---|
| date | 2026-06-09 |
| quick_id | 260609-hvl |
| description | "260610-rp44b — #44 root cause narrow" |
| verdict | {from VERIFICATION.md} |
| commit | (filled after Step 3.5) |

Bump the top-level `last_activity` field to a 1-paragraph summary including verdict + numbers + follow-up slug. Update `last_updated:` ISO-8601 timestamp.

**Step 3.5 — Atomic forward-only commit + push:**

Pre-commit safety:

```bash
# 1. Verify .gitignore covers .scratch/
grep -E "^\.scratch/?$" .gitignore || { echo "FATAL: .gitignore missing .scratch/ — abort"; exit 1; }

# 2. Verify no scratch leak into staging
git status --porcelain
# Expected: ONLY 3 files in M/A status:
#   .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-PLAN.md
#   .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md
#   .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md
#   .planning/STATE.md

# 3. Verify no SA token / API key string in any file we're about to commit
git diff --cached -- ":!.scratch/" | grep -iE "deepseek_api_key|google_application_credentials|gcp.*sa.*json|-----BEGIN.*KEY-----" && { echo "FATAL: secret in staged content — abort"; exit 1; } || echo "no secrets found in staged content"
```

Explicit `git add` per memory `feedback_git_add_explicit_in_parallel_quicks` (NEVER `-A`):

```bash
git add \
  .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-PLAN.md \
  .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md \
  .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md \
  .planning/STATE.md

git pull --ff-only origin main

git commit -m "$(cat <<'EOF'
docs(quick-260609-hvl): #44 root-cause narrow — {VERDICT}

Phase A SIGTERM truncate-window cross-check on 3 bad-set article hashes
(c7fb080361 / edc745d793 / 75c8e99998 from parent quick 260609-eg1).
{Phase A verdict line.}
{Phase B verdict line OR "Phase B skipped per H1 hit gate."}
Final: {H1/H2/H3/INCONCLUSIVE/PROBE-BLOCKED/PARTIAL}.
Recommended follow-up: {slug-or-no-followup}.

Diagnostic-only — no code change, no prod state mutation. Honors
PRINCIPLE #5 (Claude runs SSH directly), #8 (right-sized as quick:
diagnostic ≠ fix scope), #10 (does NOT add new ISSUES row; #44 row
update guidance written in VERIFICATION.md for orchestrator to
transcribe).
EOF
)"

git push origin main
```

If pre-commit hook fails: fix the issue, re-stage, NEW commit (NEVER `--amend`, NEVER `--force-push`).

**Step 3.6 — Verify push:**

```bash
git log --oneline origin/main..HEAD   # should be empty after push
git status                             # should be clean
```

**Halt rules (Task 3):**

| Symptom | Action |
|---------|--------|
| `.scratch/rp44b/` files appear in `git status` as tracked | HALT — gitignore bug. Fix `.gitignore` first, NEVER force-add scratch evidence. |
| Secret string detected in staged content | HALT — review diff, redact, re-stage. |
| `git pull --ff-only` rejects | Sibling commit landed. `git pull --ff-only` again or `git rebase --autostash origin/main` (NOT `--amend`). |
| Push rejected (auth / non-fast-forward) | HALT — diagnose; do NOT `--force` push. |
  </action>
  <verify>
    <automated>test -f .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md && test -f .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md && grep -qE "verdict:" .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md && grep -qE "Recommended follow-up" .planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md && grep -qE "260609-hvl" .planning/STATE.md && git log --oneline origin/main..HEAD | wc -l | grep -qE "^0$" && git status --porcelain | wc -l | grep -qE "^0$"</automated>
  </verify>
  <done>
    VERIFICATION.md cites final verdict (H1 / H2 / H3 / INCONCLUSIVE / PROBE-BLOCKED / PARTIAL) + recommended follow-up slug + ISSUES.md #44 row update guidance for orchestrator. SUMMARY.md narrates discipline checklist. STATE.md `last_activity` updated with the verdict. Single forward-only commit on main pushed to origin/main. No scratch / replay / journal files entered the commit. No production source modification.
  </done>
</task>

</tasks>

<verification>

**Quick-level acceptance gates:**

1. **Diagnostic boundary preserved** — `git diff origin/main..HEAD --name-only` shows ONLY 4 files: PLAN, SUMMARY, VERIFICATION, STATE. NO production source edits. NO test edits. NO `.scratch/` or `.dev-runtime/` files. NO ISSUES.md edits.
2. **Aliyun read-only honored (Phase A)** — review SSH commands; assert ZERO `INSERT|UPDATE|DELETE|cp |rm |mv |systemctl restart|git pull|git push|docker stop|docker start|pip install` patterns on Aliyun (`/tmp/repro44b_<hash>` mkdir + write is OK in Phase B; Aliyun prod paths are read-only).
3. **Phase B isolation honored (if ran)** — only `/tmp/repro44b_<hash>` written; `/root/.hermes/omonigraph-vault/lightrag_storage/` unchanged; `/root/OmniGraph-Vault/data/kol_scan.db` read-only.
4. **No Hermes touches** — Hermes RO until 2026-06-22 honored. No `ssh hermes-*` lines in any artifact.
5. **No new ISSUES row** — `git diff origin/main..HEAD .planning/ISSUES.md` is empty. Per PRINCIPLE #10 + plan constraint.
6. **No literal secrets in committed artifacts** — DeepSeek API key / SA token / GOOGLE_APPLICATION_CREDENTIALS path values not present in PLAN/SUMMARY/VERIFICATION.
7. **Phase A → Phase B gate honored** — IF `phase_a_verdict.md` says `H1_HIT` or `INCONCLUSIVE`, then NO Phase B replay log/result files exist (Task 2 was skipped). IF `H1_MISSED`, then Phase B artifacts MUST exist.
8. **Verdict reproducible** — VERIFICATION.md cites:
   - Phase A: 3 hashes' timestamps + cluster histogram + W1/W2/W3 fractions + verdict
   - Phase B (if ran): replay JSON snippet + entity_count + status + LLM output sample (or absence note) + verdict
   - Final verdict mapped per the matrix in Task 3.1
   - Follow-up slug + ISSUES.md row update guidance
9. **Push successful** — `git log origin/main..HEAD` is empty after push.

**Halt log expectations** (NOT failures, but expected friction modes):

| Halt | Cause | Recovery |
|------|-------|----------|
| H-SSH-banner | #27/#42/#43-class throttle | background poll-loop with 60-min ceiling per memory `feedback_ssh_throttle_poll_loop` |
| H-journal-aged-out | journalctl missing 6/1-6/9 entries | doc_status `created_at` fallback per Task 1.3 |
| H-no-timestamps | both journal + doc_status miss all 3 hashes | verdict = INCONCLUSIVE; skip Phase B; recommend follow-up to find pre-6/1 archive |
| H-cron-near | < 2h to next cron fire when starting Phase B | wait or defer Phase B |
| H-deepseek-401-402 | API key expired or balance depleted | HALT Phase B; recommend Hermes operator refresh |
| H-vendor-patch-wiped | `pip install --force-reinstall` happened upstream | HALT; do NOT pip-reinstall; recommend manual patch re-apply per `260608-e8l` Step 4 |
| H-replay-timeout | Phase B wall > 1800s | kill python; verdict = AMBIGUOUS; recommend re-run |

</verification>

<success_criteria>

- [ ] **RP44B-01** — `.scratch/rp44b/journal_<hash>.txt` files exist for all 3 known hashes (with content or `__NO_MATCH__`); doc_status_timestamps.txt exists
- [ ] **RP44B-02** — `.scratch/rp44b/cluster_histogram.txt` shows 1h-bucket histogram + W1/W2/W3 window-membership tally
- [ ] **RP44B-03** — `.scratch/rp44b/phase_a_verdict.md` cites one of `H1_HIT` / `H1_MISSED` / `INCONCLUSIVE` with justification
- [ ] **RP44B-04** — IF `H1_MISSED`: `.scratch/rp44b/replay_<hash>.log` + result JSON + `phase_b_verdict.md` exist; ELSE: Phase B skipped (no replay artifacts present)
- [ ] **RP44B-05** — VERIFICATION.md cites final verdict + recommended follow-up slug + ISSUES.md #44 row update guidance for orchestrator
- [ ] Diagnostic boundary preserved (no prod source edits, Aliyun read-only / `/tmp` only, no Hermes, no new ISSUES row, no LightRAG fork)
- [ ] Single atomic forward-only commit pushed to origin/main
- [ ] STATE.md `last_activity` reflects the quick's verdict in one paragraph

</success_criteria>

<output>
After completion:

1. `.planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-VERIFICATION.md` (final verdict + ISSUES row update guidance)
2. `.planning/quick/260609-hvl-260610-rp44b-44-root-cause-narrow-6-7-si/260609-hvl-SUMMARY.md` (close-out narrative)
3. `.scratch/rp44b/` evidence trail (gitignored, retained on local FS):
   - `journal_<hash>.txt` × 3
   - `doc_status_timestamps.txt`
   - `cluster_histogram.txt`
   - `phase_a_verdict.md`
   - `replay_<hash>.log` + `replay_<hash>-result.json` + `phase_b_verdict.md` (only if Phase A = H1_MISSED)
4. `.planning/STATE.md` `last_activity` bumped
5. Single forward-only commit on `main`, pushed to `origin/main`

**Return format to orchestrator:**

```
## QUICK COMPLETE — 260609-hvl

**Final verdict:** {H1 | H2 | H3 | INCONCLUSIVE | PROBE-BLOCKED | PARTIAL}
**Phase A:** {H1_HIT | H1_MISSED | INCONCLUSIVE}
**Phase B:** {EXECUTED with H2_HIT/H3_HIT/PROBE_BLOCKED/AMBIGUOUS | SKIPPED per Phase A gate}
**Follow-up:** `{slug or no-followup-h1-already-fixed}` ({/gsd:quick | DEFER | NONE})
**ISSUES.md #44 row update guidance:** {one-line for orchestrator to transcribe}
**Commit:** {sha}
**Wall:** ~{N} min (target ≤4h)
**Halts fired:** {none | list}
```
</output>
