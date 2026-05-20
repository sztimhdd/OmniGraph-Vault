---
phase: aim-0
plan_id: aim-0-02
slug: smoke-ingest-scratch
wave: 2
depends_on:
  - aim-0-01
estimated_time: 0.5d
requirements:
  - READY-04
skills: []
autonomous: false
---

# aim-0-02 — 1-2 Article Smoke Ingest E2E to Scratch Path

## Objective

Run a full end-to-end ingest smoke of 1-2 verified candidate articles on the Aliyun ECS
host, using the scratch venv/repo installed by aim-0-01 READY-03. Success is measured by
`status='ok'` rows landing in the `ingestions` table, with entities and relations written
to the scratch LightRAG storage path (`/tmp/aliyun-readiness/lightrag_storage/`) — never
to the production path. At the end, the shared READINESS.md is completed with the READY-04
results and an overall aim-0 PASS / FAIL verdict. The scratch venv is then removed to keep
the Aliyun host clean for aim-1's production install.

## Read-First

- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` lines 36 (READY-04 verbatim pass criteria)
- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` lines 56-64 (Phase aim-0 Success Criteria #4 + Notes)
- `.planning/phases/aim-0-readiness-aliyun-ecs/READINESS.md` (written by aim-0-01 — must exist and show READY-01..03 PASS before this plan begins)
- `scripts/local_e2e.sh` (reference for env var setup convention — READY-04 mirrors its pattern on Aliyun)
- `CLAUDE.md` PRINCIPLE #5 (operator-prompt vs agent-Bash channel rule)

## Pre-Conditions

- aim-0-01 complete: READY-01, READY-02, READY-03 all PASS (or READY-02 WARN with acceptable reason)
- Scratch venv from READY-03 still present at `/tmp/aliyun-readiness/venv/` and `/tmp/aliyun-readiness/repo/`
  - If it was removed after READY-03, the operator prompt in Step 1 includes the re-setup
- Candidate articles available from Hermes pool: `layer1_verdict='candidate' AND layer2_verdict='ok'`
- Agent has access to Hermes SSH to query candidate pool (read-only)

## Scope

**In scope:**
- READY-04: 1-2 article E2E smoke ingest reaching `status='ok'` in `ingestions` table
- Scratch storage path only: `/tmp/aliyun-readiness/lightrag_storage/`
- Completing READINESS.md with READY-04 result + overall aim-0 verdict
- Cleanup: `rm -rf /tmp/aliyun-readiness/` after successful READY-04

**Out of scope:**
- Production storage path (`/opt/omnigraph-vault/` — aim-1)
- Production env file (`/etc/omnigraph/.env` — aim-1)
- systemd timer setup (aim-3)
- kol_scan.db write path (still Hermes during aim-0; cutover is aim-3)

---

## Steps

### Step 1 — Select candidate articles from Hermes pool (agent-run, read-only SSH)

**Who runs:** Agent via Bash tool (read-only query to Hermes).

```bash
ssh -p <hermes-port> <hermes-user>@<hermes-host> \
  "sqlite3 ~/.hermes/omonigraph-vault/data/kol_scan.db \
    \"SELECT article_id, url, image_count, char_length(body) AS body_len \
      FROM articles \
      WHERE layer1_verdict='candidate' AND layer2_verdict='ok' \
        AND body IS NOT NULL AND char_length(body) >= 5000 \
      ORDER BY image_count DESC \
      LIMIT 5;\""
```

Note: Hermes SSH details in `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`. Do NOT embed in this plan.

**Agent action:** Pick the top 1-2 rows (highest image_count with body_len ≥ 5000). Record selected `article_id` and `url` values. If zero rows returned (no body-populated candidates), fall back to `layer1_verdict='candidate'` without `body IS NOT NULL` constraint and pick URLs anyway — the smoke ingest will re-scrape.

**Evidence lands:** Record chosen URLs in `READINESS.md § Smoke ingest E2E (READY-04)` under "Selected articles for READY-04 smoke:".

---

### Step 2 — READY-04: Smoke ingest E2E to scratch path (operator prompt — mutating, Aliyun-side)

**Who runs:** User via Aliyun operator channel. Agent writes a paste-ready operator prompt block. Do NOT run via Bash tool.

**Rationale for operator channel:** This step runs live LLM API calls (DeepSeek / SiliconFlow / Vertex) and writes to `/tmp` on Aliyun. Requires real API keys injected server-side. Per PRINCIPLE #5, mutating Aliyun ops go through operator prompt.

**Operator prompt to write (paste-ready):**

---

**ALIYUN OPERATOR PROMPT — READY-04 (Smoke ingest E2E to scratch path)**

Run on Aliyun ECS. The scratch venv from READY-03 should still be at `/tmp/aliyun-readiness/`.
If it was removed, re-create it:

```bash
# (Only if scratch venv was removed after READY-03)
mkdir -p /tmp/aliyun-readiness/{lightrag_storage,repo,venv}
cd /tmp/aliyun-readiness/repo
git clone https://github.com/sztimhdd/OmniGraph-Vault.git . --depth=1
python3 -m venv /tmp/aliyun-readiness/venv
/tmp/aliyun-readiness/venv/bin/pip install --quiet -r requirements.txt
```

Set environment (same keys as READY-03):

```bash
export OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness
export DEEPSEEK_API_KEY=<real DeepSeek key from /etc/omnigraph/.env or Aliyun secrets manager>
export GEMINI_API_KEY=<real Gemini key>
export GOOGLE_APPLICATION_CREDENTIALS=<path to Vertex SA JSON on Aliyun>
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_CLOUD_PROJECT=<project id>
export SILICONFLOW_API_KEY=<real SiliconFlow key if available>
export SCRAPE_CASCADE=apify,ua
export APIFY_TOKEN=<Apify token — can borrow from Hermes ~/.hermes/.env temporarily>
```

Note on API keys: retrieve ALL key values from `/etc/omnigraph/.env` on Aliyun or the Aliyun
secrets manager — do NOT hardcode literal key values in chat or operator prompts.

Run smoke ingest for Article 1:

```bash
ARTICLE_URL_1="<URL from Step 1 selection>"

cd /tmp/aliyun-readiness/repo
/tmp/aliyun-readiness/venv/bin/python ingest_wechat.py "$ARTICLE_URL_1" \
  2>&1 | tee /tmp/aliyun-readiness/ready04-article1-$(date +%Y%m%d-%H%M%S).log

echo "Exit code: $?"
```

After Article 1 completes, verify `status='ok'` in the scratch ingestions table:

```bash
sqlite3 /tmp/aliyun-readiness/data/kol_scan.db \
  "SELECT article_id, status, ingested_at FROM ingestions ORDER BY ingested_at DESC LIMIT 5;"
```

If Article 1 is `status='ok'` and image_count ≥ 5 → single article is sufficient for READY-04.
Optionally run Article 2 for higher confidence:

```bash
ARTICLE_URL_2="<URL from Step 1 selection, second row>"

/tmp/aliyun-readiness/venv/bin/python ingest_wechat.py "$ARTICLE_URL_2" \
  2>&1 | tee /tmp/aliyun-readiness/ready04-article2-$(date +%Y%m%d-%H%M%S).log
```

Verify both reach `status='ok'`:

```bash
sqlite3 /tmp/aliyun-readiness/data/kol_scan.db \
  "SELECT article_id, status, ingested_at FROM ingestions ORDER BY ingested_at DESC LIMIT 5;"
```

Check that scratch LightRAG storage has actual data (not empty):

```bash
du -sh /tmp/aliyun-readiness/lightrag_storage/
ls /tmp/aliyun-readiness/lightrag_storage/
```

**What to report back:** Paste:
1. The final sqlite3 SELECT output showing `status='ok'` rows
2. The `du -sh /tmp/aliyun-readiness/lightrag_storage/` output (confirms entities/relations written)
3. Any errors from the log (especially provider failures or timeout lines)
4. Wall-clock time for each article ingest (visible as timestamps in the log)

---

**Agent action after operator reports back:** Record in `READINESS.md § Smoke ingest E2E (READY-04)`:
- Articles used (URL + article_id)
- sqlite3 output showing `status='ok'`
- lightrag_storage size post-ingest
- Wall-clock time per article
- Any provider cascade fallbacks observed

**Pass predicate:** ≥ 1 article reaches `status='ok'` in the scratch ingestions table AND `/tmp/aliyun-readiness/lightrag_storage/` is non-empty (entities + relations written).

**Fail action:** If `status='failed'` for all attempted articles, record the error pattern:
- Provider UNREACHABLE (network block) → note which provider; assess if cascade fallback is sufficient
- OOM / process killed → check if READY-03 peak RSS was close to limit; escalate
- Timeout → note wall-clock time; if > 30 min/article, flag for aim-1 systemd timer timeout config
Do NOT proceed to aim-1 on a hard FAIL. Investigate root cause first.

---

### Step 3 — Complete READINESS.md with overall aim-0 verdict (agent-run)

**Who runs:** Agent (reads existing READINESS.md sections, appends verdict section).

**Agent action:** Based on all four REQ results, fill in `## Decision: aim-0 PASS / FAIL → next step`:

```markdown
## Decision: aim-0 PASS / FAIL → next step (aim-1 plan-phase)

Date: YYYY-MM-DD
Completed by: aim-0-02-PLAN.md

| REQ      | Result | Notes |
|----------|--------|-------|
| READY-01 | PASS/FAIL | |
| READY-02 | PASS/WARN/FAIL | [provider ratios] |
| READY-03 | PASS/FAIL | [peak RSS GB] |
| READY-04 | PASS/FAIL | [articles N/N ok] |

**Overall: aim-0 PASS / FAIL**

Next step:
- PASS → Proceed to `/gsd:plan-phase aim-1`. Aliyun ECS is verified ready for code deploy.
- FAIL → Document which REQ failed and why. Do NOT proceed to aim-1 until resolved.
```

---

### Step 4 — Scratch venv cleanup (operator prompt — mutating, Aliyun-side)

**Who runs:** User via Aliyun operator channel (after READY-04 confirmed PASS).

**Why operator channel:** `rm -rf` on Aliyun is mutating; agent does not run destructive ops on remote hosts via Bash.

**Operator prompt (paste-ready):**

---

**ALIYUN OPERATOR PROMPT — aim-0 scratch cleanup**

After confirming READY-04 PASS, remove the scratch workspace to keep Aliyun clean for aim-1's
production install at `/opt/omnigraph-vault/`:

```bash
rm -rf /tmp/aliyun-readiness/

# Verify clean
ls /tmp/ | grep aliyun || echo "Clean — /tmp/aliyun-readiness removed"
```

This removes: scratch repo clone, scratch venv, scratch lightrag_storage, scratch kol_scan.db, and all READY-03/READY-04 log files.

Report back: paste the `ls /tmp/` output confirming removal.

---

Note: If aim-0 verdict is FAIL (any REQ hard-fails), **do NOT clean up the scratch directory** — the scratch logs under `/tmp/aliyun-readiness/*.log` are needed for debugging. Clean up only after the failure is diagnosed and resolved via a re-run.

---

## Verification (per-REQ)

| REQ | Pass Criterion | Evidence Location |
|-----|----------------|-------------------|
| READY-04 | ≥ 1 article `status='ok'` in scratch `ingestions` table AND `/tmp/aliyun-readiness/lightrag_storage/` non-empty | `READINESS.md § Smoke ingest E2E (READY-04)` — sqlite3 output + `du -sh` |

Overall aim-0 is PASS when READY-01 + READY-02 (PASS or documented WARN) + READY-03 + READY-04 are all satisfied.

---

## Output: Complete READINESS.md

After Step 3, `READINESS.md` has all five sections populated:

```
## Host spec (READY-01)              ← aim-0-01
## Provider RTT (READY-02)           ← aim-0-01
## LightRAG ainsert peak RSS (READY-03) ← aim-0-01
## Smoke ingest E2E (READY-04)       ← aim-0-02
## Decision: aim-0 PASS / FAIL       ← aim-0-02
```

Commit `READINESS.md` to git after all sections are complete:

```bash
git add .planning/phases/aim-0-readiness-aliyun-ecs/READINESS.md
git commit -m "docs(aim-0): record readiness results — PASS/FAIL"
```

---

## Rollback

- Steps 1, 3: read-only or local file writes — no rollback needed
- Steps 2, 4 (operator): all writes are under `/tmp/aliyun-readiness/` (scratch)
  - Production paths on Aliyun (`/opt/omnigraph-vault/`, `/etc/omnigraph/`, kb-api) are never touched
  - Rollback = `rm -rf /tmp/aliyun-readiness/` (already the Step 4 cleanup)
- If READY-04 FAIL: do NOT run Step 4 cleanup — preserve scratch logs for debugging

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scratch venv from READY-03 was removed before READY-04 | Step 2 operator prompt fails on missing venv | Operator prompt Step 2 includes re-setup block with `git clone` + `pip install` — safe to re-run |
| DeepSeek UNREACHABLE from Aliyun (READY-02 WARN) | Layer 2 + LightRAG entity extraction cannot run; READY-04 smoke may not reach `status='ok'` | Evaluate: if DeepSeek RTT is UNREACHABLE, READY-04 smoke will fail at entity extraction stage (LightRAG). This is a blocker — must resolve before aim-1. Consider `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` for the smoke run to validate the pipeline structure, but flag the DeepSeek dependency clearly. |
| SiliconFlow key not yet on Aliyun (`/etc/omnigraph/.env` only has Vertex SA) | Vision cascade primary (SiliconFlow) fails; falls to Vertex (500 RPD free ceiling) | For 1-2 article smoke this is acceptable — Vertex Vision fallback handles the smoke; note in READINESS.md that aim-1 must deploy SiliconFlow key |
| Scratch `kol_scan.db` path divergence (`OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness` may put db in unexpected location) | Article tracking written to wrong path; sqlite3 verification query finds no rows | Verify path with `find /tmp/aliyun-readiness/ -name "*.db"` before running sqlite3 query; adjust path in verification command accordingly |
| Smoke articles fail scrape (WeChat anti-scrape, Apify balance) | READY-04 fails at scrape stage; never reaches `status='ok'` | Select 2 candidate articles from Hermes pool (not just 1) so there's a fallback; ensure `APIFY_TOKEN` injected from Hermes env; if both fail scrape, pick a different article from the pool |
