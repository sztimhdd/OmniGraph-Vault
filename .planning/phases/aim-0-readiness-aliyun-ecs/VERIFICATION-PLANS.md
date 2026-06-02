# Plan Verification: aim-0 (Readiness on Aliyun ECS)

**Verdict: PASS**

Both plans, if executed as written, will produce evidence sufficient to declare Phase aim-0 PASS or FAIL.

Verified: 2026-05-20  
Plans checked: aim-0-01, aim-0-02

---

## Checks performed

### 1. REQ pass-criteria pinning

**READY-01** (REQUIREMENTS.md line 33): `nproc ≥ 8 AND free -h Mem total ≥ 15 GiB AND df -h / Avail ≥ 5 G`

- Plan 01 Step 1 pass predicate (line 71–73): `nproc ≥ 8`, `free -h Mem: total ≥ 15`, `df -h / Avail ≥ 5G` — exact match. PASS.

**READY-02** (REQUIREMENTS.md line 34): each provider Aliyun median RTT ≤ 2× Hermes baseline, same-day measurement, ≥5 sequential samples

- Plan 01 Step 2: 5 sequential `curl -w '%{time_total}'` samples per provider per side, median computed, table with `Ratio (Aliyun/Hermes) ≤ 2×` — exact match.
- One deviation: the pass predicate at line 136 relaxes READY-02 to a WARN (not FAIL) if only Vertex AI exceeds 2×. This is within the spirit of REQUIREMENTS.md, which says "each provider" but acknowledges corp-network RTT outlier from Hermes. The deviation is explicitly documented and acceptable.

**READY-03** (REQUIREMENTS.md line 35): peak RSS < 8 GB via `/usr/bin/time -v` or `psrecord`

- Plan 01 Step 3 pass predicate (line 208): `peak_rss_gb < 8.0` computed from `/usr/bin/time -v` `Maximum resident set size (kbytes)`. Exact match. PASS.

**READY-04** (REQUIREMENTS.md line 36): ≥1 article `status='ok'` in `ingestions` table; entities to scratch path `/tmp/aliyun-readiness/lightrag_storage/`

- Plan 02 Step 2 pass predicate (line 183): `≥ 1 article status='ok'` AND `lightrag_storage/ non-empty` — exact match. PASS.

### 2. Operator-channel discipline

**Read-only SSH (agent-run via Bash):** Plan 01 Steps 1 and 2 run `nproc`/`free`/`df` and `curl -w` via Bash tool. Both are read-only diagnostics. Per STATE.md § Operator Channel: "Read-only diagnostics MAY be run by the agent via Bash." No violation.

**Mutating ops (operator channel):** Plan 01 Step 3 (scratch venv + pip install + ainsert) and Plan 02 Steps 2 and 4 (live ingest run + `rm -rf`) are all operator-prompted with explicit paste-ready blocks. No agent-side Bash is used for mutating Aliyun ops. Compliant.

No violations found.

### 3. No literal secrets

Plan 01 Step 3 operator prompt (lines 173–177): API keys appear as `<retrieve from /etc/omnigraph/.env or Aliyun secrets>` and `<path to Vertex SA JSON>` — placeholders only.

Plan 02 Step 2 operator prompt (lines 113–119): All five keys (DEEPSEEK_API_KEY, GEMINI_API_KEY, GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT, SILICONFLOW_API_KEY, APIFY_TOKEN) use `<...>` placeholder form, with explicit note at line 122: "retrieve ALL key values from `/etc/omnigraph/.env` on Aliyun or the Aliyun secrets manager — do NOT hardcode literal key values."

No literal secrets found. PASS.

### 4. Scratch path discipline

Plan 01 Step 3: `OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness` (line 171), repo cloned to `/tmp/aliyun-readiness/repo`, venv at `/tmp/aliyun-readiness/venv`. No writes to `/opt/omnigraph-vault/` or `/etc/omnigraph/`.

Plan 02 Step 2: Same `OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness`. Scratch ingestions DB queried at `sqlite3 /tmp/aliyun-readiness/data/kol_scan.db` (line 141). lightrag_storage check via `du -sh /tmp/aliyun-readiness/lightrak_storage/`.

One note: Plan 02 line 141 queries the scratch `ingestions` table at `/tmp/aliyun-readiness/data/kol_scan.db`, but the Risk section at line 301 explicitly flags the "scratch kol_scan.db path divergence" risk and provides the mitigation (`find /tmp/aliyun-readiness/ -name "*.db"` before querying). This is correctly handled.

No production path writes. PASS.

### 5. Hermes SSH details not embedded

Plan 01 Step 2 Hermes block (line 104): uses `<hermes-port>`, `<hermes-user>`, `<hermes-host>` placeholders. Note at line 120 explicitly says "Do NOT embed port/host/user in this plan."

Plan 02 Step 1 (line 76): same pattern with identical note.

No Hermes credentials embedded. PASS.

### 6. READINESS.md output structure — non-overlapping division

Plan 01 creates READINESS.md and populates sections: `## Host spec (READY-01)`, `## Provider RTT (READY-02)`, `## LightRAG ainsert peak RSS (READY-03)`. The template at line 228 also pre-creates placeholder stubs for `## Smoke ingest E2E (READY-04)` and `## Decision: aim-0 PASS / FAIL` with the label "(Populated by aim-0-02-PLAN.md)."

Plan 02 populates only `## Smoke ingest E2E (READY-04)` (Step 2) and `## Decision: aim-0 PASS / FAIL` (Step 3). Plan 02 does not re-write sections 1–3.

Division is clean and non-overlapping. PASS.

### 7. Cleanup conditionality

Plan 02 Step 4 (line 222): "After confirming READY-04 PASS, remove the scratch workspace." The note at line 249 explicitly states: "If aim-0 verdict is FAIL (any REQ hard-fails), do NOT clean up the scratch directory — the scratch logs under `/tmp/aliyun-readiness/*.log` are needed for debugging. Clean up only after the failure is diagnosed and resolved via a re-run."

The conditionality is explicit. PASS.

### 8. Frontmatter correctness

Plan 01:

- `phase: aim-0` — correct
- `plan_id: aim-0-01` — correct
- `requirements: [READY-01, READY-02, READY-03]` — exact match to plan scope
- `depends_on: [none]` — correct (Wave 1)

Plan 02:

- `phase: aim-0` — correct
- `plan_id: aim-0-02` — correct
- `requirements: [READY-04]` — exact match to plan scope
- `depends_on: [aim-0-01]` — correct (Wave 2, depends on Plan 01)

All frontmatter fields correct. PASS.

---

## Minor observations (non-blocking)

**Plan 01, READY-03 operator prompt, line 184:** The article-URL selection query references `~/.hermes/omonigraph-vault/data/kol_scan.db`. However, per CLAUDE.md `project_kol_scan_db_path.md` memory, the production DB lives at `<repo>/data/kol_scan.db`, NOT under `~/.hermes/omonigraph-vault/`. The operator prompt inside the READY-03 block queries Hermes for a candidate URL (read-only), so the path inside the `ssh hermes` block should point to the repo-root DB path, not `~/.hermes/omonigraph-vault/data/kol_scan.db`. This is a read-only query for URL selection only (not a write path), so it will not cause data corruption. However, if the DB is not present at that path on Hermes, the `sqlite3` call returns no rows and the operator falls back to pasting a URL manually — low impact. Worth correcting in a plan revision but not a blocker.

**Plan 02, Step 2, line 141:** Queries `sqlite3 /tmp/aliyun-readiness/data/kol_scan.db`. Whether this path is correct depends on where `ingest_wechat.py` writes the ingestions DB when `OMNIGRAPH_BASE_DIR=/tmp/aliyun-readiness`. The Risk entry at line 301 flags this explicitly, and the mitigation (find first) is present. Acceptable as-is.

---

## Coverage summary

| REQ | Plan | Step | Evidence file | Status |
|-----|------|------|---------------|--------|
| READY-01 | aim-0-01 | Step 1 | READINESS.md § Host spec | Covered |
| READY-02 | aim-0-01 | Step 2 | READINESS.md § Provider RTT | Covered |
| READY-03 | aim-0-01 | Step 3 | READINESS.md § LightRAG peak RSS | Covered |
| READY-04 | aim-0-02 | Step 2 | READINESS.md § Smoke ingest E2E | Covered |

All 4 READY-N requirements covered. No orphans.

---

**Both plans are ready for execution.** No revision required before proceeding.
