---
phase: aim-0
plan_id: aim-0-01
slug: spec-rtt-mem-dryrun
wave: 1
depends_on:
  - none
estimated_time: 0.5d
requirements:
  - READY-01
  - READY-02
  - READY-03
skills: []
autonomous: false
---

# aim-0-01 — Host Spec + Provider RTT + LightRAG ainsert Memory Dry-Run

## Objective

Verify that the Aliyun ECS host meets the runtime pre-conditions required before any
code is deployed. The vCPU/RAM upgrade originally planned in Q6 was cancelled — the
host stays at the current ~2 vCPU / ~14 GiB shape — so READY-01 (host spec) is recorded
as **informational only** in this plan: actual values are captured for the record but
do not gate downstream work. The real go/no-go for "can this host carry the ingest
workload" shifts entirely onto READY-03, which measures actual LightRAG ainsert peak
RSS on a heavy representative article and gates on `peak_rss_gb < 8.0`. READY-02
(provider RTT) and READY-03 (peak RSS) remain hard gates. All measurements are written
to a shared READINESS.md in this phase directory. Plan 02 (smoke ingest) appends to
the same file.

## Read-First

- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` lines 29-36 (READY-01..03 verbatim pass criteria)
- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` lines 41-65 (Phase aim-0 Goal + Success Criteria)
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` §6 Risk rows 1-2 (resource + RTT risks)
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` § "Operator Channel" (channel decision)
- `CLAUDE.md` PRINCIPLE #5 (operator-prompt vs agent-Bash channel rule)

## Scope

**In scope:**

- READY-01: Host spec check via read-only SSH (`nproc`, `free -h`, `df -h /`)
- READY-02: LLM provider RTT — Aliyun side AND Hermes same-day baseline, both captured in one step
- READY-03: LightRAG ainsert peak RSS dry-run on Aliyun using a heavy article URL

**Out of scope:**

- Code deployment (aim-1)
- venv / requirements.txt install on Aliyun — READY-03 uses a TEMPORARY scratch venv in /tmp (see Step 3 operator prompt)
- Any production path writes — scratch venv at `/tmp/aliyun-readiness/` only
- Hermes cron disruption — Hermes keeps running throughout aim-0

## Pre-Conditions

- Agent SSH alias `aliyun-vitaclaw` must be reachable (read-only probe in Step 1)
- Note: the vCPU upgrade gate from Q6 has been retired — current ~2 vCPU / ~14 GiB shape is the working assumption for READY-03's memory budget

---

## Steps

### Step 1 — READY-01: Host spec snapshot (agent-run, read-only SSH — INFORMATIONAL)

**Who runs:** Agent via Bash tool (`ssh aliyun-vitaclaw`).
**What runs:**

```bash
ssh aliyun-vitaclaw "echo '=== nproc ===' && nproc && echo '=== free ===' && free -h && echo '=== df ===' && df -h /"
```

**Evidence lands:** Copy stdout verbatim into `READINESS.md` under `## Host spec (READY-01)`. Also capture the three values inline for quick reference: `vCPU=N, MemTotal=NG, RootAvail=NG`.

**Status:** **INFORMATIONAL — no hard gate.** Q6's 8 vCPU / 16 GB upgrade was cancelled; spec numbers in this step are recorded for the audit trail and to inform aim-1 sizing decisions, but do NOT block downstream READY-02 / READY-03 execution. The actual "can this host carry ingest" judgment is made by READY-03's peak-RSS measurement against an 8 GB budget.

**Soft observations to record in READINESS.md:**

- If `df -h /` Avail < 5 G → flag as a separate operational concern (READY-03's scratch venv install needs ~1-2 GB; production deploy in aim-1 needs more) but still continue.
- If `free -h` Mem total is meaningfully below ~14 GiB (e.g., < 10 GiB) → note explicitly, since it tightens the headroom against READY-03's 8 GB peak RSS budget.
- Otherwise: record values, mark `READY-01: INFORMATIONAL — recorded`, proceed to Step 2.

---

### Step 2 — READY-02: LLM provider RTT — Aliyun + Hermes same-day baseline (agent-run, read-only SSH)

**Who runs:** Agent via Bash tool. Both sides run in sequence (same day = same-day baseline control).

**Aliyun side** (run first):

```bash
ssh aliyun-vitaclaw "
  echo '=== DeepSeek RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://api.deepseek.com/ 2>&1 || echo 'FAIL'
  done &&
  echo '=== SiliconFlow RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://api.siliconflow.cn/ 2>&1 || echo 'FAIL'
  done &&
  echo '=== Vertex AI RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://us-central1-aiplatform.googleapis.com/ 2>&1 || echo 'FAIL'
  done
"
```

**Hermes side** (run second, same session):

```bash
ssh -p <hermes-port> <hermes-user>@<hermes-host> "
  echo '=== DeepSeek RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://api.deepseek.com/ 2>&1 || echo 'FAIL'
  done &&
  echo '=== SiliconFlow RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://api.siliconflow.cn/ 2>&1 || echo 'FAIL'
  done &&
  echo '=== Vertex AI RTT (5 samples) ===' &&
  for i in 1 2 3 4 5; do
    curl -o /dev/null -s -w '%{time_total}\n' https://us-central1-aiplatform.googleapis.com/ 2>&1 || echo 'FAIL'
  done
"
```

Note: Hermes SSH connection details are in `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`. Do NOT embed port/host/user in this plan.

**Post-processing (agent computes):** For each provider × side, compute median and p95 from the 5 raw `time_total` floats.

**Evidence lands:** Write a markdown table into `READINESS.md` under `## Provider RTT — Aliyun vs Hermes same-day baseline (READY-02)`:

```
| Provider         | Aliyun median (s) | Aliyun p95 (s) | Hermes median (s) | Hermes p95 (s) | Ratio (Aliyun/Hermes) | PASS? |
|------------------|-------------------|----------------|-------------------|----------------|-----------------------|-------|
| DeepSeek         | X.XXX             | X.XXX          | X.XXX             | X.XXX          | X.XX×                 | YES/NO |
| SiliconFlow      | ...               |                |                   |                |                       |       |
| Vertex AI        | ...               |                |                   |                |                       |       |
```

**Pass predicate:** For each provider, `Aliyun median ≤ 2 × Hermes median`.

**Fail action:** Record actual ratios. If only one provider fails, note it and continue — READY-02 partial pass is acceptable if the failing provider is Vertex AI (corp-network RTT outlier from Hermes is expected; Aliyun should be lower). If SiliconFlow or DeepSeek exceeds 2× Hermes, flag as "READY-02 WARN — investigate provider reachability before aim-1."

**Note on FAIL cases:** `curl` to a root path may return a non-200 but still records `time_total` (the connection+handshake time is what matters). `FAIL` output means curl itself errored (no route, DNS failure) — that is a hard network block, record as `UNREACHABLE`.

---

### Step 3 — READY-03: LightRAG ainsert peak RSS dry-run (operator prompt — mutating, Aliyun-side)

**Who runs:** User via Aliyun operator channel. Agent writes a paste-ready operator prompt block. Do NOT run this via Bash tool.

**Rationale for operator channel:** This step installs a scratch Python venv and runs LightRAG ainsert on Aliyun — mutating (file writes to /tmp) and requires LLM API keys injected server-side. Per PRINCIPLE #5, mutating Aliyun ops go through the operator prompt channel.

**Operator prompt to write (paste-ready):**

---

**ALIYUN OPERATOR PROMPT — READY-03 (LightRAG ainsert peak RSS dry-run)**

Run on Aliyun ECS as root (or the user who owns `/tmp`):

```bash
# 1. Create scratch workspace
mkdir -p /tmp/aliyun-readiness/{lightrag_storage,repo,venv}

# 2. Clone repo (use HTTPS so no deploy key needed yet)
cd /tmp/aliyun-readiness/repo
git clone https://github.com/sztimhdd/OmniGraph-Vault.git . --depth=1

# 3. Create scratch venv + install requirements
cd /tmp/aliyun-readiness/repo
python3 -m venv /tmp/aliyun-readiness/venv
/tmp/aliyun-readiness/venv/bin/pip install --quiet -r requirements.txt

# 3.5. Pre-flight: list keys actually present in production env file BEFORE setting env.
#      Confirm GEMINI_API_KEY / GOOGLE_APPLICATION_CREDENTIALS / SILICONFLOW_API_KEY all present.
#      If any required key is missing here, STOP — fix Aliyun secrets before continuing.
grep -oE '^[A-Z_][A-Z_0-9]*=' /etc/omnigraph/.env | sort -u

# 4. Set minimal env for ainsert dry-run
export OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness
export DEEPSEEK_API_KEY=dummy
# Inject real keys from /etc/omnigraph/.env or paste inline:
#   export GEMINI_API_KEY=<retrieve from /etc/omnigraph/.env or Aliyun secrets>
#   export GOOGLE_APPLICATION_CREDENTIALS=<path to Vertex SA JSON on Aliyun>
#   export GOOGLE_CLOUD_LOCATION=global
#   export GOOGLE_CLOUD_PROJECT=<project id>
# Vision cascade order is SiliconFlow (primary, paid) → OpenRouter (secondary, free)
# → Gemini Vision (last resort, Vertex 500 RPD ceiling). For READY-03 memory test,
# all three are optional — without any vision keys, ingest_wechat.py either skips
# image description or fails through the cascade and continues without vision.
#   export SILICONFLOW_API_KEY=<if available — improves throughput, prevents Vertex 500 RPD ceiling>

# 5. Pick a representative "heavy" article URL
#    Choose one from the Hermes candidate pool: layer1_verdict='candidate' AND
#    layer2_verdict='ok', preferably a KOL article with >= 10 images.
#    You can get one via: ssh hermes "sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
#      \"SELECT url FROM articles WHERE layer1_verdict='candidate' AND layer2_verdict='ok' \
#        AND image_count >= 10 ORDER BY image_count DESC LIMIT 1;\""
# Fallback if Hermes SSH unreachable: use the verified KOL article URL hardcoded
# as ingest_wechat.py:1647 default — known good (medium-image, candidate verdict).
# ARTICLE_URL="https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA"
ARTICLE_URL="<paste chosen URL here>"

# 6. Run ingest under /usr/bin/time -v to capture peak RSS
cd /tmp/aliyun-readiness/repo
/usr/bin/time -v \
  /tmp/aliyun-readiness/venv/bin/python ingest_wechat.py "$ARTICLE_URL" \
  2>&1 | tee /tmp/aliyun-readiness/ready03-$(date +%Y%m%d-%H%M%S).log

# 7. Extract peak RSS from /usr/bin/time -v output (last few lines of the log)
#    Look for: "Maximum resident set size (kbytes): NNNNN"
#    Convert to MB: NNNNN / 1024
#    Convert to GB: NNNNN / 1024 / 1024

# 8. Report back: paste the "Maximum resident set size" line + article URL used
```

**What to report back:** Paste the final `Maximum resident set size (kbytes): NNNNN` line from the `/usr/bin/time -v` output, the article URL used, and any errors. Agent will record in READINESS.md.

---

**Agent action after operator reports back:** Record operator stdout in `READINESS.md` under `## LightRAG ainsert peak RSS dry-run (READY-03)`. Compute `peak_rss_gb = reported_kbytes / 1024 / 1024`. Record pass/fail.

**Pass predicate:** `peak_rss_gb < 8.0` (50% of 16 GB total).

**Fail action:** If peak_rss_gb ≥ 8.0, record actual value and flag "READY-03 FAIL — peak memory exceeds 50% budget. Investigate LightRAG storage size, embedding concurrency settings. Do NOT proceed to aim-1 until investigated."

---

## Verification (per-REQ)

| REQ | Pass Criterion | Evidence Location |
|-----|----------------|-------------------|
| READY-01 | **Informational only** — record actual `nproc`, `free -h` Mem total, `df -h /` Avail. No threshold gate. | `READINESS.md § Host spec (READY-01)` |
| READY-02 | Each provider Aliyun median RTT ≤ 2× Hermes median (same-day) | `READINESS.md § Provider RTT (READY-02)` — table with Ratio + PASS column |
| READY-03 | peak RSS < 8 GB (= < 8,388,608 kbytes) | `READINESS.md § LightRAG ainsert peak RSS (READY-03)` — `/usr/bin/time -v` line + computed GB value |

READY-02 and READY-03 are the hard gates. READY-01 is recorded for the audit trail and to inform aim-1 sizing. A WARN on READY-02 (Vertex AI only) is acceptable — document reason and continue. Any hard FAIL on READY-02 (DeepSeek/SiliconFlow) or READY-03 blocks aim-1.

---

## Output: Create READINESS.md

At the start of Step 1, create `.planning/phases/aim-0-readiness-aliyun-ecs/READINESS.md` with this structure:

```markdown
# Aliyun ECS Readiness Report — aim-0

Date: YYYY-MM-DD
Aliyun ECS spec at test time: X vCPU / Y GB RAM (Q6 upgrade cancelled — recorded informationally)
Executor: aim-0-01-PLAN.md

---

## Host spec (READY-01)

[Paste Step 1 SSH stdout here]

READY-01: PASS / FAIL

---

## Provider RTT — Aliyun vs Hermes same-day baseline (READY-02)

[RTT table from Step 2]

READY-02: PASS / WARN / FAIL — [reason if not PASS]

---

## LightRAG ainsert peak RSS dry-run (READY-03)

Article URL: [URL used]
/usr/bin/time -v output (relevant lines):
[paste]

Peak RSS: X,XXX,XXX kbytes = X.X GB
READY-03: PASS / FAIL

---

## Smoke ingest E2E (READY-04)

(Populated by aim-0-02-PLAN.md)

---

## Decision: aim-0 PASS / FAIL → next step (aim-1 plan-phase)

(Populated by aim-0-02-PLAN.md after all 4 REQs resolved)
```

---

## Rollback

aim-0 is read-only on Aliyun for Steps 1-2. For Step 3 (operator-run READY-03):

- Scratch workspace is entirely under `/tmp/aliyun-readiness/` — no production paths touched
- Rollback = `rm -rf /tmp/aliyun-readiness/` (safe; no persistent state)
- Aliyun production paths (`/opt/omnigraph-vault/`, `/etc/omnigraph/`) are NOT touched by this plan

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Host shape (~2 vCPU / ~14 GiB) tighter than originally chartered (Q6 upgrade cancelled) | Headroom against READY-03's 8 GB peak-RSS budget is reduced; OOM risk if LightRAG concurrency too high | READY-03 is the sole runtime gate — measure actual peak RSS on a heavy article. If `peak_rss_gb >= 8.0`, investigate LightRAG `embedding_batch_num` + `graph_max_async`; do not force-continue to aim-1. |
| LLM provider blocked on Aliyun (READY-02 UNREACHABLE result) | ingest pipeline cannot use that provider at aim-1 | Record as UNREACHABLE; evaluate impact — SiliconFlow reachability from cn-east-mainland is expected to be BETTER than from Hermes corp network; DeepSeek UNREACHABLE would be a serious blocker for aim-1 |
| `/usr/bin/time -v` not available on Aliyun (some minimal distros have only `time` builtin) | READY-03 cannot measure peak RSS | Fallback: use `command /usr/bin/time -v` to confirm it's the GNU time binary; if absent, install via `apt-get install -y time` or use `psrecord` (available after pip install in scratch venv) |
| Peak RSS ≥ 8 GB (READY-03 FAIL) | Cannot safely run ingest on 16 GB host without OOM risk | Investigate: LightRAG `embedding_batch_num` + `graph_max_async` settings; reduce concurrency; re-measure |
