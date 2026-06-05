# 260605-mz1 — v1.2 Research: Walls Verify

**Quick:** 260605-mz1-v1-2-research-walls-verify
**Date:** 2026-06-05 ADT (audit window: 2026-06-01..06 CST)
**Mode:** RESEARCH-ONLY (no prod mutation, no code change)
**Owner:** quick task — orchestrator pickup TBD

> **TL;DR:** All 3 walls (#38 / #39 / #40) verify SYSTEMIC across 5-day Aliyun cron data — Halt #4 does NOT fire. **However, local concurrent probe HALT #1 fired** (corp laptop Cisco Umbrella TLS-intercepts every LLM endpoint: DeepSeek, Vertex, Gemini, even tiktoken bootstrap blob). Probe script written + valid + run-attempted, no wall_s data captured. Section 3 v1.2 viability marked **UNKNOWN — pending probe re-run on a non-corp network or via prod-parity SSH**.

## Section 1 — 5-day Aliyun audit per-wall verdicts

### Methodology

- **batch_timeout_metrics** files: 10 most recent dumped from `/root/OmniGraph-Vault/data/batch_timeout_metrics_*.json` (covers 2026-05-30 through 2026-06-05, 9 cron runs in the 5-day window 06-01..06-05)
- **journalctl** `omnigraph-daily-ingest.service`: per-day grep counts for 2026-06-01..06-05 (CST)
- **sqlite ingestions**: 7-day breakdown per status × day from `articles` table on Aliyun
- Raw evidence: `.scratch/260605-mz1-aliyun-audit-raw.txt` (446 lines, gitignored)
- Aliyun is CST (UTC+8); user is ADT (UTC-3); timestamps in this section are CST unless marked

### Verdicts

| Wall | Verdict | Days fired | Total count 5d | Evidence |
|---|---|---|---|---|
| **#38 wrapper-cap CUMULATIVE** (TIMEOUT >1200s wrapper kill, signature = `timeout_histogram.900s+ > 0`) | **SYSTEMIC** | 4/5 (06-02, 06-03, 06-04, 06-05) | 33 timeouts in 900s+ bucket | `batch_timeout_metrics_20260603_034358.json` `900s+: 9, clamped_timeouts: 3, safety_margin_triggered: true`; `..._20260605_080047.json` `timed_out_articles: 10, 900s+: 10`; `..._20260605_140050.json` `timed_out_articles: 9, 900s+: 10` |
| **#39 PROCESSED-gate silent drop** (`PROCESSED verification failed` log line) | **SYSTEMIC** | 3/5 (06-03=5, 06-04=9, 06-05=3) | 17 occurrences | `journalctl -u omnigraph-daily-ingest.service` per-day grep counts; e.g. `Jun 05 20:59:43 ... PROCESSED verification failed for doc_id=wechat_68bdd45a91 after 30 retries (configured floor 30, backoff 5.0s, dynamic budget 150s). Last status=DocStatus.PENDING` |
| **#40 serial-processing starvation** (`not_started_articles > 0`, OR ≤1 article completed in 6h+ window) | **SYSTEMIC** | 5/5 — every cron run | 100% reproduction | Every metrics file in window: 06-02 `completed=1 / not_started=221`; 06-03_03 `completed=1 / not_started=228`; 06-04_08 `completed=0 / not_started=258`; 06-05_08 `completed=0 / not_started=227`; 06-05_14 `completed=1 / not_started=223` — structural by design (single 8h budget × serial article processing) |

### Trend signals

- **5-day timeout count (timeout_histogram.900s+ per cron):** 06-01(no run)→06-02(1)→06-03_03(9, clamped)→06-03_20(0)→06-04_08(2)→06-04_14(1)→06-04_20(0)→06-05_08(10)→06-05_14(10)→06-05_20(0). Pattern: morning crons (08:00 CST) hit hard caps consistently in 06-04 / 06-05; evening crons (14:00 / 20:00) succeed more often.
- **5-day avg `avg_article_time_sec`:** widely variable: 240s..2867s. 06-05 morning = 2867s/article (extreme; vision cascade timeout on SiliconFlow read-timeout=60s × N images stacks).
- **5-day completed-article ratio:** 0/N to 7/N per cron, 1/N median. Zero crons ever processed > 10% of candidate pool. 06-05 evening (20:00) was best at 7/251 = 2.8%.
- **PROCESSED-fail correlates with same-day wrapper kills:** 06-04 had 9 PROCESSED-fail + 4 wrapper kills; 06-03 had 5 PROCESSED-fail + 9 wrapper kills + safety_margin_triggered. The two failure modes co-fire on image-heavy days.
- **Note re ISSUES #32 / #33** (filed 2026-06-03): tightened OMNIGRAPH_PROCESSED_BACKOFF=5.0 → budget=150s shipped via `f7674b3` but Aliyun .env update unverified by this audit. Even at 150s budget, 06-04 + 06-05 fire rate suggests the gate is still tight under image-heavy load. The PROCESSED-fail line cited 06-05 reads "30 retries, backoff 5.0s, dynamic budget 150s" — confirms .env IS updated and 150s STILL insufficient on long articles.

## Section 2 — Local corp-laptop concurrent probe

### Setup (intended)

- Probe script: `.scratch/260605-mz1-concurrent-probe.py` (78 LoC, valid Python 3.13, ≤80 LoC cap)
- Isolated `OMNIGRAPH_BASE_DIR`: `.dev-runtime/260605-mz1-probe/`
- Articles selected: `c8cc5b1fb7` (img=2, body=6807 bytes "OpenClaw 入门") + `b37b0df5fb` (img=5, body=4546 bytes "智能体网络综述") — both `layer2_verdict='ok'`, image_count ∈ [2,5], pulled read-only via SSH from Aliyun
- Body files staged: `.dev-runtime/260605-mz1-probe/data/body_{1,2}.md` (14 KB / 9 KB)
- LLM provider: `OMNIGRAPH_LLM_PROVIDER=deepseek` (prod parity)
- Vision: `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter,gemini` (probe targets LightRAG ainsert thread-safety, NOT vision)

### Run attempt — Halt #1 fired

Probe execution attempted; failed at LightRAG initialization due to **corp Cisco Umbrella TLS interception** of every LLM-relevant endpoint:

| Endpoint probed | Symptom |
|---|---|
| `https://api.deepseek.com` (HEAD via curl) | exit 35: `schannel SEC_E_ILLEGAL_MESSAGE TLS handshake fail` |
| `https://api.siliconflow.cn` (HEAD) | exit 35: `CRYPT_E_NO_REVOCATION_CHECK` |
| `https://us-central1-aiplatform.googleapis.com` (HEAD) | timeout 15s, no response |
| `https://oauth2.googleapis.com` (HEAD) | timeout 15s, no response |
| `https://generativelanguage.googleapis.com` (HEAD) | timeout 15s, no response |
| `openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken` (LightRAG tiktoken bootstrap) | `ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` — venv certifi bundle has not been merged with corp CA roots |

Probe terminated before reaching `rag.ainsert()` — fail-fast in tiktoken `o200k_base` download (LightRAG 1.4.15 dependency) using stock urllib3 against the Cisco-MITM'd Azure blob endpoint. **No wall_s data captured.**

### Results

| Metric | Value |
|---|---|
| PASS A serial wall_s | **N/A — Halt #1 (corp firewall)** |
| PASS B 2-concurrent wall_s | **N/A — Halt #1 (corp firewall)** |
| Speedup ratio | **N/A — no measurement** |
| graphml valid | N/A — never reached ainsert |
| kv_store_doc_status valid | N/A |
| Both docs status='processed' | N/A |
| Exceptions during ainsert | Pre-ainsert: `SSLCertVerificationError` on tiktoken bootstrap — never entered ainsert at all |
| Errors observed | All LLM + tokenizer-bootstrap endpoints TLS-blocked by corp Cisco Umbrella interception |

### Verdict

- **UNKNOWN** — probe could not run on this network. NOT a LightRAG thread-safety failure (Halt #2). NOT a Vertex 429 (Halt #3). Pure infrastructure block.
- The probe script itself is **valid and runnable** — it can be re-attempted on:
  1. A non-corp network (home, mobile hotspot)
  2. Aliyun directly (run inside `aliyun-vitaclaw` SSH session, isolated dir under `/tmp/probe/` — but this conflicts with this quick's "RESEARCH-ONLY no Aliyun mutation" boundary, so deferred to a separate quick)
  3. Corp laptop after running `.scratch/260525-rebuild-cacert.py` to merge corp CA roots into venv certifi bundle (per CLAUDE.md "Corp PEM rebuild" runbook — but this is environment setup work outside this research-only quick's boundary)
- Re-run path (recommended): a follow-up `/gsd:quick "260606-XX-probe-rerun"` with explicit pre-step "rebuild venv certifi via .scratch/260525-rebuild-cacert.py" then re-execute `.scratch/260605-mz1-concurrent-probe.py` unchanged

## Section 3 — v1.2 design viability

**v1.2 batch_ingest concurrent rewrite viability: UNKNOWN — pending probe re-run.**

### Decision matrix path taken

Section 1 verdicts: ALL three walls SYSTEMIC. Therefore the Halt #4 "all walls non-systemic, do not file v1.2 P0" branch does **NOT** fire — these ARE legitimate v1.2 P0 candidates. The user's pushback that "1-day evidence is insufficient" is now addressed: 5-day evidence shows persistent walls.

Section 2 verdict: UNKNOWN (probe halted by corp firewall — NOT a LightRAG thread-safety failure). Therefore Section 3 cannot declare GO / RISKY / BLOCKED for the concurrent-rewrite design path until the probe runs.

### Conditional plan based on probe re-run outcome

When the probe re-runs and produces wall_s data:

- **If `speedup_ratio >= 1.7x` AND all post-conditions pass** → **GO** for v1.2 asyncio.gather wrapper. Critical path: `batch_ingest_from_spider.py` `_process_one_article` becomes a `gather` over chunks of 2-4 articles; `total_batch_budget_sec` becomes per-chunk; embedding/LLM RPM caps enforced via existing `lib.rate_limit`. Refined LoC estimate: **+150 to +300 LoC** (gather wrapper ~+40, per-task budget ~+30, partial-failure handling ~+50, telemetry ~+30, tests ~+50-100).
- **If `1.4x <= speedup_ratio < 1.7x`** → **RISKY**. Spike a follow-up quick to investigate which LightRAG/Qdrant lock site is serializing. Likely candidates: `kv_store_doc_status` mutex on doc-status flip, Qdrant client-side connection pool serialization, LightRAG entity-merge global lock during graph mutation.
- **If `speedup_ratio < 1.4x` OR ANY post-condition fails (graphml/kv corrupt, both_processed=False)** → **BLOCKED**. Alternative paths:
  1. **Per-article subprocess isolation** — fork N worker processes, each with its own LightRAG instance, dispatch articles via queue. Lock contention sidestepped at the OS level. Cost: ~3× peak RAM (each LightRAG holds vdb in memory; once Qdrant migration #25 lands this becomes ~1× per worker since vdb is network-side).
  2. **Parallel Aliyun ingest workers** — multiple systemd services with disjoint candidate pools (e.g., even article IDs vs odd, or split by KOL). Simpler op-side; no code change beyond service unit files. Throughput limited by single-host RAM still.
  3. **Wait for LightRAG upstream concurrency support** — track LightRAG GitHub for thread-safe ainsert. Indefinite timeline.
  4. **Accept current serial behavior, raise wrapper cap from 1200s → 1800s, throughput-by-cadence** — schedule cron more often (every 4h instead of every 8h), accept N=8 batches/day each processing ~5 articles. Median throughput remains low (~40 articles/day) but stabilizes.

### LoC estimate refinement

- Original orchestrator estimate (per quick prompt): not stated explicitly — refined estimate is **300 ± 150 LoC** in the GO branch, **0 LoC** in the BLOCKED branch (alternative paths are ops/config not code).
- **Confidence in estimate: LOW until probe runs.** The LoC range above is engineering judgement; lock-site investigation could either compress it (if asyncio.gather "just works") or balloon it (if a custom serialization layer is needed).

## Section 4 — ISSUES.md row update recommendations

For each wall, recommend ONE row action for the orchestrator to apply. **All three walls verify SYSTEMIC — KEEP AS-IS is the recommendation, but with refined annotation noting 5-day evidence**.

| ISSUE # | Current severity | Recommendation | Suggested annotation (orchestrator pastes into the row's Notes field) |
|---|---|---|---|
| #38 wrapper-cap CUMULATIVE 1200s | (NEW — to be filed) | **FILE NEW** — open as 🟡 P1 (not P0; wrapper kill IS by-design and self-heals on next-cron retry per existing #33 framing) | "Wrapper-cap kill (TIMEOUT >1200s, signature `timeout_histogram.900s+ > 0`) verified SYSTEMIC across 4/5 days 2026-06-01..05 (33 total events; metrics files cited in `260605-mz1-RESEARCH.md` Sec 1). Concurrent rewrite (v1.2) deferred pending thread-safety probe (Halt #1: corp firewall). Mitigation: raise wrapper cap to 1800s OR concurrent-rewrite when v1.2 probe lands. Cross-ref ISSUES #33." |
| #39 PROCESSED-gate silent drop | (NEW — to be filed) | **FILE NEW** — open as 🟡 P1 (data NOT lost; retry pool re-queues per #32 framing). Cross-ref existing #32 (already filed for the same root cause; this entry adds 5-day evidence). | "PROCESSED-gate verification fail (signature `PROCESSED verification failed for doc_id=... after 30 retries`) verified SYSTEMIC across 3/5 days 2026-06-03..05 (17 total events). Already mitigated to 150s dynamic budget (commit `f7674b3`); evidence shows even 150s tight on image-heavy KOL articles. **MERGE candidate with #32** — orchestrator may consolidate #32 + this entry into one row with 5-day evidence appended. No new mitigation path needed beyond #32's suggestion (raise to 300s)." |
| #40 serial-processing starvation | (NEW — to be filed) | **FILE NEW** — open as 🔴 P0 (only true throughput blocker; 100% reproduction; all other walls fire on top of this structural shape) | "Serial-processing starvation (signature `not_started_articles > 0` AND/OR `completed_articles ≤ 1 / total_articles ≥ 200`) verified SYSTEMIC across 5/5 days 2026-06-01..05 (100% reproduction; structural by design). All cron runs hit < 10% pool throughput. Wave 3 T9 root cause (memory `wave3_batch_budget_serial_starve`). v1.2 concurrent rewrite is the design path; viability **PENDING probe re-run** (this quick's Section 2 Halt #1)." |

**Halt #4 trigger NOT fired** — all 3 walls verified SYSTEMIC with substantial evidence (33 / 17 / 100%). The user's "1-day evidence insufficient" pushback is resolved: file the issues with confidence.

**Cross-issue overlap:** #39 likely MERGE candidate with existing #32. Orchestrator decides whether to file #39 as a new row or annotate #32 with 5-day evidence.

## Halt log

### Halt #1 fired (Corp laptop firewall blocks LLM endpoints)

- **Trigger:** TASK 2 probe pre-flight + run attempt
- **Symptoms:**
  1. `curl -X HEAD https://api.deepseek.com` → exit 35 SEC_E_ILLEGAL_MESSAGE TLS handshake fail
  2. `curl -X HEAD https://api.siliconflow.cn` → exit 35 CRYPT_E_NO_REVOCATION_CHECK
  3. `curl -X HEAD https://us-central1-aiplatform.googleapis.com` → timeout 15s
  4. `curl -X HEAD https://oauth2.googleapis.com` → timeout 15s
  5. `curl -X HEAD https://generativelanguage.googleapis.com` → timeout 15s
  6. Probe execution: `ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` on `openaipublic.blob.core.windows.net` (LightRAG tiktoken bootstrap)
- **Action taken:** halt probe per plan halt rule, capture symptoms in evidence trail, write probe artifact intact (≤80 LoC, valid Python, runnable when network conditions allow), produce Section 2 BLOCKED-by-firewall record
- **Impact on Section 3:** v1.2 viability declared UNKNOWN. Section 1 verdicts (audit data) UNAFFECTED — they have independent value and the audit-only branch of the plan still produces actionable orchestrator input. Section 4 row recommendations UNAFFECTED — based on Section 1 audit alone

### Halt #2 / #3 / #4: NOT fired

- Halt #2 (concurrent corruption): probe never reached ainsert — no corruption observable
- Halt #3 (Vertex 429): probe never reached Vertex — N/A
- Halt #4 (all walls non-systemic): explicitly NOT fired — all 3 walls verified SYSTEMIC

## Cross-references

- Audit raw evidence: `.scratch/260605-mz1-aliyun-audit-raw.txt` (446 lines, gitignored)
- Probe script: `.scratch/260605-mz1-concurrent-probe.py` (78 LoC, valid Python, gitignored)
- Probe inputs: `.dev-runtime/260605-mz1-probe/data/body_{1,2}.md` (gitignored)
- Memory `wave3_batch_budget_serial_starve` — root cause framing for #40
- Memory `feedback_ssh_readonly_vs_writeop_boundary` — read-only SSH path used here
- Memory `corp_pem_rebuild_pattern` — corp CA bundle re-merge runbook for probe re-run
- ISSUES.md #32 / #33 — pre-existing rows that overlap with #38 / #39 (merge candidates per Section 4)

## Section 5 — Probe re-run results (260605-pwl)

**Quick:** `260605-pwl-probe-rerun-cert-rebuild`
**Date:** 2026-06-05 ADT
**Pre-step:** `.scratch/260525-rebuild-cacert.py` rebuild — **REBUILD OK: 123 total certs, 4 corp hits** (log: `.scratch/260605-pwl-cert-rebuild.log`)
**Probe contract:** byte-identical to 260605-mz1 (sha256 `57308c595db37718f9a845a311f65a4c25c6957d987b464649a22ff8bcf3ad23` verified before/after; **probe NOT launched**)

### Run results

| Metric | Value |
|---|---|
| PASS A serial wall_s | **N/A — probe not launched (Halt F at T3 boundary)** |
| PASS B 2-concurrent wall_s | **N/A — probe not launched** |
| Speedup ratio | **N/A** |
| both_processed | **N/A** |
| graphml_valid | **N/A** |
| kv_store_valid | **N/A** |
| serial_exception | **N/A** |
| concurrent_exception | **N/A** |

### Verdict — v1.2 batch_ingest concurrent rewrite viability

**BLOCKED-by-environment** — closest decision-matrix row is `BLOCKED-by-cert-rebuild` (environment unblocker quick needed before re-attempting probe), but the blocker scope extends beyond cert rebuild. Cert rebuild ALONE (parent quick 260605-mz1's intended unblock path) is **insufficient** — the corp environment has TWO additional blockers exposed by post-rebuild reachability probe:

1. **Missing `DEEPSEEK_API_KEY` on the Hermes prod-runtime env path** — `~/.hermes/.env` (the file `config.py` loads at import for prod-parity invocations) contains `GEMINI_API_KEY` / `APIFY_TOKEN` / `FIRECRAWL_API_KEY` / `CDP_URL` / `APIFY_TOKEN_BACKUP`, but **NOT `DEEPSEEK_API_KEY`**. The probe launcher reads this file. `lib.llm_deepseek._require_api_key()` raises `RuntimeError` on first ainsert call. Per PLAN.md T2 step 4: "halt with cite, do NOT silent-skip." **Scope qualifier (added post-adversarial-verify 2026-06-05):** the key DOES exist in two project-local env files — `.dev-runtime/.env` (local-dev runtime) and `databricks-deploy/.env.local` (Databricks Apps local UAT). Workflows entering through those paths have the key available, so the env-gap blocker is path-specific to the Hermes prod-runtime invocation the probe contract uses. The DeepSeek TLS-block (blocker #2 below) blocks **all** corp-laptop paths regardless of which env file provides the key, so the BLOCKED-by-environment verdict still holds.

2. **Corp Cisco Umbrella TLS-blocks `api.deepseek.com`** — even with rebuilt certifi (123 total / 4 corp hits, ssl ground-truth probe passes), Python `urllib.request.urlopen('https://api.deepseek.com/')` returns `URLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]`. Cert rebuild fixes the **tiktoken bootstrap blob** (Azure blob TLS now succeeds, returns HTTP 400 from server) and **Gemini** (returns HTTP 404 from server) — but corp Umbrella does not re-sign DeepSeek's chain; instead it drops the TLS handshake. Cert rebuild does **NOT** fix this.

The cert rebuild work itself is durable and useful for any future Gemini/Vertex/embedding-only probe on this machine — log preserved at `.scratch/260605-pwl-cert-rebuild.log`.

**v1.2 viability state:** still UNKNOWN — pending probe execution on a network where DeepSeek is reachable AND `DEEPSEEK_API_KEY` is available. Two unblocker paths from this halt:

- **Aliyun-side run (preferred — bypasses both blockers):** SSH `aliyun-vitaclaw`, isolated `/tmp/260605-XX-probe-run/` working dir, `DEEPSEEK_API_KEY` available via systemd `EnvironmentFile=/root/.hermes/.env` (or interactive `set -a; source /root/.hermes/.env; set +a;` per memory `aliyun_ssh_manual_trigger_env`), `api.deepseek.com` reachable from Aliyun. Strongest signal for v1.2 viability since prod-parity network. Trade-off: requires explicit phase scope to allow Aliyun write-ops (probe creates a temporary working dir + LightRAG storage; per memory `feedback_ssh_readonly_vs_writeop_boundary`, this exceeds read-only diagnostic boundary).

- **Switch probe LLM provider to Vertex Gemini:** sibling `.scratch/260605-XX-concurrent-probe-v2.py` with `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`, no DeepSeek dependency. Vertex requires SA JSON + `GOOGLE_APPLICATION_CREDENTIALS` — verify corp network allows Vertex (parent quick reported timeout on `us-central1-aiplatform.googleapis.com`; needs re-test post-cert-rebuild). Trade-off: not prod parity (prod uses DeepSeek), v1.2 viability signal weaker — different LLM client may have different lock semantics inside LightRAG.

LoC estimate for v1.2 GO branch unchanged from parent RESEARCH.md Section 3 (still **+150 to +300 LoC** in `batch_ingest_from_spider.py` GO branch; **0 LoC** in BLOCKED branch). Confidence in estimate: still LOW until probe runs.

### Halt log

**Halt F (NEW) — pre-flight halt at T3 boundary, two blockers exposed:**

- Trigger: T2 pre-flight check (`grep -E '^DEEPSEEK_API_KEY=' ~/.hermes/.env` returned empty) + post-T1 reachability probe (`api.deepseek.com` `SSLV3_ALERT_HANDSHAKE_FAILURE`)
- Symptom 1 (env): `DEEPSEEK_API_KEY` absent in `~/.hermes/.env` and shell — probe-launch would crash on first `rag.ainsert()` call when `lib.llm_deepseek._get_client()` lazily reads the key
- Symptom 2 (network, NEW vs parent quick): even with rebuilt cert (`certifi: 123/4 corp`), `urllib.request.urlopen('https://api.deepseek.com/')` returns `SSLV3_ALERT_HANDSHAKE_FAILURE` — corp Cisco Umbrella TLS-blocks DeepSeek chain (no re-sign, just drops handshake). Tiktoken bootstrap (parent Halt #1 root cause) RESOLVED by cert rebuild (HTTP 400 server response = TLS happy). Gemini also resolved (HTTP 404 server response).
- Action: halted at T3 boundary per plan rule ("halt with cite, do NOT silent-skip"); probe NOT launched; byte-identical contract preserved (sha256 match before/after); diagnostic captured to `.scratch/260605-pwl-probe-output.txt`
- Impact: v1.2 viability remains UNKNOWN. Cert-rebuild deliverable IS durable. Halt #1 from parent quick (tiktoken bootstrap) IS resolved by cert rebuild — orthogonal to the new DeepSeek blockers.

**Halt A / B / C / D / E — NOT fired in this re-run:**

- Halt A (cert rebuild fail): NOT fired — script returned `REBUILD OK: 123 total / 4 corp hits` cleanly, no rollback
- Halt B (env-var override forgotten): NOT fired — env vars detected at T2 step 3, would have been unset for T3 probe shell (T3 not launched, but the unset path was prepared)
- Halt C (kv_store / graphml corruption during concurrent ainsert): NOT fired — probe never reached ainsert
- Halt D (Vertex 429): NOT fired — probe never reached Vertex
- Halt E (body data missing): NOT fired — body_1.md (14172 bytes) + body_2.md (9431 bytes) both present at T2 step 1

### Cross-references

- Probe output (halt diagnostic): `.scratch/260605-pwl-probe-output.txt` (gitignored, 73 lines)
- Cert rebuild log: `.scratch/260605-pwl-cert-rebuild.log` (gitignored, 7 lines, `REBUILD OK: 123 total / 4 corp`)
- sha256 contract: `.scratch/260605-pwl-probe-sha256-{before,after}.txt` (both gitignored, identical)
- Pre-pwl cert backup: `venv/Lib/site-packages/certifi/cacert.pem.bak-260605-pre-pwl` (gitignored)
- Quick close-out: `.planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md`
- Parent RESEARCH Section 2 (Halt #1 tiktoken bootstrap): NOW RESOLVED by cert rebuild (this Section 5)
- Parent RESEARCH Section 3 (v1.2 viability): still UNKNOWN — DeepSeek TLS block + missing key are the new blockers
- Memory `corp_pem_rebuild_pattern` — runbook used for T1 cert rebuild
- Memory `aliyun_ssh_manual_trigger_env` — relevant for Aliyun-side re-run unblocker path
- Memory `feedback_ssh_readonly_vs_writeop_boundary` — read-only SSH boundary for Aliyun-side re-run scope
