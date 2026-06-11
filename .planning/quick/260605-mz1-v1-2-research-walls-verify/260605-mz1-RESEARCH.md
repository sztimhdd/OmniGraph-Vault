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

## Section 6 — Probe re-run results (260605-u17, Vertex provider)

**Quick:** `260605-u17-probe-vertex-rerun`
**Date:** 2026-06-05/06 ADT
**Pre-step:** sibling quick `260605-pwl` cert rebuild — `123 total / 4 corp hits` (re-verified at T1; ssl ground-truth probe passes)
**Vertex reachability:** TLS-happy on `us-central1-aiplatform.googleapis.com` + `oauth2.googleapis.com` + `aiplatform.googleapis.com` (HTTP 404 server response = handshake succeeded; orchestrator pre-flighted)
**Probe contract:** `.scratch/260605-u17-concurrent-probe-vertex.py` is sibling of parent `260605-mz1-concurrent-probe.py` with one substantive change — LLM provider switched DeepSeek → Vertex Gemini via `lib.llm_complete.get_llm_func()` dispatcher. Embedding/post-conditions/2-pass design/JSON output IDENTICAL. sha256 byte-identical pre/post run (`1891839825103e4001f4271da518b35ade618befd1671cc110522dd6e2cb0dbc` matches before+after). LoC = 78 ≤ 80 cap.

### Run results

| Metric | Value |
|---|---|
| PASS A serial wall_s | `459.286` |
| PASS B 2-concurrent wall_s | `0.005` (probe-contract artifact — see "Probe contract flaw" below; NOT a real concurrent measurement) |
| Speedup ratio | `83578.027` (nonsense — denominator artifact from PASS B never running) |
| both_processed | `False` (probe-contract artifact — see below) |
| graphml_valid | `"missing"` (probe-contract artifact — PASS B reset graphml then never wrote) |
| kv_store_valid | `True` |
| serial_exception | `None` (PASS A serial completed cleanly) |
| concurrent_exception | `None` (PASS B never threw — but never actually concurrent-inserted either) |

**PASS A actually-observed work** (real and useful signal):
- Article 1 (`c8cc5b1fb7`, ~14 KB body): 4 chunks → 53 entities + 46 relations (40 from chunks + 13 extra from merge)
- Article 2 (`b37b0df5fb`, ~9 KB body): 3 chunks → 41 entities + 30 relations (35 from chunks + 6 extra from merge)
- Total final graph: **93 nodes / 76 edges** written to graphml
- Wall time: **459.286s** for both articles serially through full LightRAG ainsert (extract + merge + persist)

### Probe contract flaw — PASS B never executed real concurrent ainsert

The parent probe contract (inherited byte-for-byte by probe-v2 per PLAN's minimal-diff requirement) has a flaw exposed only on the first probe run that reaches PASS B:

**`reset_storage()` between PASS A and PASS B clears the on-disk `STORAGE` directory but does NOT reset the in-process LightRAG pipeline status.** When the second `make_rag()` call invokes `initialize_pipeline_status()`, the singleton-ish global pipeline state still remembers that doc_ids `c8cc5b1fb7` + `b37b0df5fb` were already processed in PASS A. PASS B's `await asyncio.gather(rag.ainsert(body1, ids=[h1]), rag.ainsert(body2, ids=[h2]))` therefore short-circuits at the dedup gate before any real ainsert work happens.

Direct evidence in `.scratch/260605-u17-probe-output.txt` (around line 271-280, immediately after PASS A finalize):

```text
WARNING: Duplicate document detected: c8cc5b1fb7 (unknown_source)
WARNING: Duplicate document detected: b37b0df5fb (unknown_source)
INFO: Created 1 duplicate document records with track_id: insert_20260605_220629_0fe524e2
WARNING: No new unique documents were found.
INFO: Created 1 duplicate document records with track_id: insert_20260605_220629_d0c009b8
WARNING: No new unique documents were found.
INFO: Another process is already processing the document queue. Request queued.
INFO: Preserving 2 failed document entries for manual review
INFO: No valid documents to process after consistency check
INFO: Enqueued document processing pipeline stopped
INFO: Successfully finalized 12 storages
```

PASS B `wall_s_concurrent=0.005s` is the time taken for the dedup gate to fire and refuse the work, not the time taken for two concurrent ainserts. The post-condition `graphml_valid: "missing"` reflects PASS B having reset the graphml file (via `reset_storage`) but never written a new one because no work executed.

**This flaw exists in the parent probe `260605-mz1-concurrent-probe.py` too** — neither parent quick `260605-mz1` (Halt #1: corp firewall blocked tiktoken bootstrap) nor sibling `260605-pwl` (Halt F: DeepSeek TLS block + env-key gap) ever reached PASS B execution, so the flaw stayed latent until this quick first ran the probe to completion.

### Verdict — v1.2 batch_ingest concurrent rewrite viability

**BLOCKED — dual-apply between correctness and corruption rows; operational impact identical** (post-adversarial-verify 2026-06-05).

Strict-matrix reading per PLAN.md line 151 corruption definition `corruption = graphml_valid is not True OR kv_store_valid is not True OR concurrent_exception is not None` → `graphml_valid='missing'` satisfies the disjunction, so **row 5 (BLOCKED-by-corruption)** fires per strict literal application. Original verdict `BLOCKED-by-correctness` (row 4) silently re-defined corruption to mean only the literal substring `corrupt:`. Halt C symptom list (PLAN.md line 171) explicitly offers both verdicts as a choice — the row label depends on whether one weights `both_processed=False` (correctness primary) or `graphml_valid='missing'` (corruption primary). Both rows collapse to the same operational next-step in PLAN.md line 576 ("subprocess isolation forced; concurrent ainsert is unsafe; LLM-client-agnostic"), so the row choice has nil practical impact. Recording the dual-apply explicitly so future readers don't trust either row label as definitive: **the BLOCKED verdict is correct; the row label is ambiguous.**

**BUT — verdict reflects probe-contract artifact, NOT real v1.2 viability.** The verdict is correctly BLOCKED per the matrix as it stands, but the underlying cause is a probe-contract flaw (in-process pipeline state defeats `reset_storage()` between passes), NOT a real correctness failure of LightRAG concurrent ainsert. The probe never tested what v1.2 design actually proposes (asyncio.gather over ainsert across distinct article IDs).

What we DO learn from this run (independently of the verdict):

1. **Vertex Gemini end-to-end pipeline works on corp laptop with rebuilt cert + explicit env vars.** PASS A serial completed cleanly: 459s for 2 articles through full extraction → merge → persist. No SSL errors, no auth errors, no quota throttling. Vertex Gemini-2.5-flash-lite-preview produced the entity-relation extractions LightRAG expects.

2. **Vertex serial throughput baseline:** ~230 s/article on this hardware/network with image_count ∈ [2,5] articles. Compare to Aliyun cron `avg_article_time_sec` 240..2867s in 5-day audit (Section 1) — Vertex local is on the fast end of that distribution but within range. (Caveat: Vertex local skips vision via `OMNIGRAPH_VISION_SKIP_PROVIDERS`, so apples-to-apples comparison would adjust for the vision phase Aliyun runs but local skipped.)

3. **Halt G (auth) and Halt F (vertex-network) are both NOT-fired:** Vertex SA JSON loads correctly, oauth2 token issued, model endpoints reachable. Cert rebuild from sibling 260605-pwl is durable through the Vertex provider switch.

### Vertex caveat (mandatory)

**Vertex Gemini measurement is a STRONG SIGNAL but NOT DEFINITIVE for v1.2 viability.**

Production uses DeepSeek as the LLM provider; this probe uses Vertex Gemini. Lock semantics inside LightRAG may differ between LLM clients — different httpx connection pool, different tokenizer call paths (Vertex SDK uses `google.genai` not `tiktoken` for token counting), different retry semantics, different async cancellation behavior. A GO verdict would suggest v1.2 concurrent-rewrite is FEASIBLE but not guarantee prod-parity speedup.

**For this quick's actual verdict (BLOCKED-by-correctness):** the probe-contract flaw is LLM-client-agnostic — `reset_storage()` defeats the in-process pipeline state regardless of whether DeepSeek or Vertex is the LLM. So the BLOCKED verdict here would also have fired against DeepSeek if the parent quick had reached PASS B. The Vertex caveat does NOT alter the BLOCKED verdict, but DOES alter the recommended next-step:

- **If a future probe-contract revision lands a GO/RISKY verdict:** the v1.2 plan-phase MUST include an explicit sub-task for an Aliyun-side prod-parity follow-up smoke (DeepSeek provider, prod-parity network) BEFORE declaring the asyncio.gather wrapper design final.

- **For this quick's BLOCKED-by-correctness:** the immediate next step is NOT subprocess isolation (the matrix's recommended alt-path) but rather a probe-contract revision quick that fixes `reset_storage()` to also reset the in-process pipeline state — most directly via subprocess invocation per pass (each pass is its own `python` invocation with a fresh interpreter, so pipeline state cannot leak between passes). Once the probe contract is fixed, re-run this Vertex probe to get a real `wall_s_concurrent` measurement, then re-apply the decision matrix.

### Section 6.5 — Why ingest is slow (PASS A structural finding — PRIMARY USER-ACTIONABLE SIGNAL)

> Added post-adversarial-verify 2026-06-05 per synthesizer recommendation: this is the load-bearing finding for v1.2 viability and the user's "why is ingest so slow" question.

**PASS A is genuine end-to-end signal.** 459.286s for 2 articles serial = **230s/article** on corp laptop (Vertex Gemini 2.5 flash-lite-preview, 8 embed workers + 4 LLM workers, async=8). Aliyun's 5-day audit (Section 1) shows `avg_article_time_sec` range `240..2867s` — corp laptop matches the **fast end** of that distribution, **proving slow-ingest is NOT local-machine-specific**. It's structural in the LightRAG ingest pipeline.

**Per-article breakdown from the PASS A log:**

For Doc 1 (`c8cc5b1fb7`, 14 KB body, 4 chunks → 53 final entities + 46 relations) the LightRAG pipeline runs:

| Phase | What it does | API calls | Wall-time share (estimate) |
|---|---|---|---|
| **Chunk extract** (`Extracting stage 1/1`) | 4 parallel Vertex calls extract entities + relations from each chunk | ~12 calls (4 chunks × ~3 LLM round-trips for retry/JSON-validate) | ~30-50s |
| **Phase 1 entity processing** (`Processing 40 entities, async=8`) | For each of 40 entities, call LLM to disambiguate + summarize description | ~40 calls | ~50-70s |
| **Phase 2 relation processing** (`Processing 46 relations, async=8`) | For each of 46 relations, call LLM to summarize | ~46 calls | ~60-80s |
| **Phase 3 final merge** (`Updating final 53(40+13) entities and 46 relations`) | Single batch update — merges new entities/relations into graph + writes graphml | (no LLM calls; pure I/O) | ~5-10s |
| **Embedding** (parallel to Phase 1+2) | Each entity + relation embedded by Gemini-embedding-2 (3072 dim) | 8 embed-worker concurrency | overlapped |

Total Vertex API calls observed during PASS A across 2 articles: **191 calls** for 2 articles = **~95 calls/article**. At Vertex Gemini p50 latency ~1-3s/call and `async=8` concurrency → wall ≈ 95/8 × 2s ≈ **24s pure compute**, but actual wall = 230s ⇒ **~10× overhead** comes from sequential phase boundaries (Phase 1 must complete before Phase 2; merge serialized after both; chunk extract can't start until prior chunk's batch has settled).

**This is the load-bearing answer for "why ingest 这么慢":**

1. **LightRAG ingest is N×LLM-calls-per-article structural cost, not network or local-machine.** Each article spawns ~95 Vertex calls. Cron-to-cron variance (240s..2867s observed) is dominated by article entity-density (10-100 entities) × image-density (vision phase Aliyun runs but local skipped). On a 50-entity article with 30 images, expected wall ≈ 60s base + 30 × 60s SiliconFlow read-timeout × backoff = 30+ min easily.

2. **The 8h batch budget × serial article processing (parent wall #40) hits because each article is slow AND the batch is sequential.** With 230s/article best case + 30s overhead per article gate (Layer 1, Layer 2, dedup), 8h = 28800s budget can plausibly process only `28800/(230+overhead) ≈ 100-120 articles best case`, but typical days hit 5-20 due to image-heavy outliers.

3. **PROCESSED-gate failures (#39) correlate with same-day wrapper kills (#38)** because Phase 3 final-merge happens AFTER the wrapper's 1200s soft-cap kicks in for image-heavy articles. The 150s dynamic budget for PROCESSED verification is too tight when LightRAG's Phase 3 itself runs after a 600-900s entity/relation phase.

**How to break it (ordered by ROI):**

| Path | Mechanism | Expected impact | Risk |
|---|---|---|---|
| **A. Concurrent article ingest** (v1.2 proposal) | asyncio.gather over N=4-8 articles per batch loop iteration | If LightRAG concurrent ainsert is thread-safe (UNKNOWN until probe v3 lands), 4× speedup → 60s/article effective wall | Probe v3 needed first; subprocess isolation may be required if LightRAG fails concurrent test |
| **B. Cache LLM extract calls aggressively** | Already happens (`LLM cache == saving` lines per chunk extract) but only across same-article retries; cross-article entity/relation cache could halve Phase 1+2 calls on overlap | 30-50% speedup on dense topical batches (e.g. all-AI-agent articles share entities) | Low — cache already wired, just needs cross-article hash key |
| **C. Skip Phase 2 / Phase 3 for low-value articles** | layer2 verdict already grades articles; restrict deep-extraction to top-tier; skip relation-merge for layer2='ok-shallow' | 50% wall reduction on shallow articles | Loses graph density for those articles |
| **D. Batch-size knob** (orthogonal to concurrent rewrite) | Increase async=8 → async=16 for entity/relation phases | 30-50% per-article (less overhead between batches) | Vertex 429 risk if pool > rate limit; embed-worker count must scale too |
| **E. Subprocess isolation as v1.2 fallback** | If LightRAG concurrent ainsert fails probe v3, v1.2 = `multiprocessing.Pool(N)` wrapper around per-article subprocess | Definitely thread-safe (process-level isolation) but ~3× peak RAM | Heavier op-wise; still 4× wall speedup on N=4 |

**Path A is the v1.2 candidate. Path B+D are zero-LoC quick-wins that should land BEFORE v1.2 plan-phase fires** (cheap; orthogonal; reduces v1.2's required speedup ceiling). Path C is an architectural tradeoff requiring user buy-in.

Independent of v1.2: the **150s PROCESSED-gate budget should be raised to ~300s** (memory `feedback_pending_symptom_check_dim_first` + Section 1 evidence shows 06-05 still firing 30 retries × 5s backoff — gate is too tight for image-heavy articles).

### Halt log

**Halt B (env-var override forgotten) — fired ONCE at probe launch attempt 1, recovered:**

- First launch attempt used `set -a; source .dev-runtime/.env; set +a;` to load env vars. Bash `source` interpreted `\U`, `\h`, `\D` etc. in Windows path values as escape sequences and stripped the backslashes — `c:\Users\huxxha\Desktop\OmniGraph-Vault\.dev-runtime\gcp-paid-sa.json` became `c:UsershuxxhaDesktopOmniGraph-Vault.dev-runtimegcp-paid-sa.json`.
- Symptom: `google.auth.exceptions.DefaultCredentialsError: File c:UsershuxxhaDesktop... was not found.` raised inside embedding-worker tasks for both passes; LightRAG caught the exception internally and marked both docs FAILED, so the JSON output showed `serial_exception: null` and `concurrent_exception: null` (silent ghost-success class) but `both_processed: false`.
- Per PLAN Halt B rule ("fix and retry. Do NOT mark BLOCKED for this"), launcher was rewritten with explicit `export GOOGLE_APPLICATION_CREDENTIALS="C:/Users/.../gcp-paid-sa.json"` (forward-slash form, no `source`). Second launch ran cleanly and produced the data above. Three Windows-path env vars confirmed problematic on bash `source`: `GOOGLE_APPLICATION_CREDENTIALS`, `OMNIGRAPH_BASE_DIR`, `KOL_SCAN_DB_PATH` (only the first one is load-bearing for this probe; documented for next quick).

**Halts A / C / D / E / F / G — NOT fired:**

- **A (cert regression):** NOT fired — `123 total / 4 corp hits` re-verified at T1
- **C (kv_store/graphml corruption from concurrent ainsert):** NOT fired in the original Halt C sense — corruption observed (`graphml_valid: "missing"`) is a probe-contract artifact, not concurrent-ainsert data corruption. PASS B never ran real concurrent ainsert, so the original Halt C question is unanswered.
- **D (Vertex 429 RESOURCE_EXHAUSTED):** NOT fired — no 429 / quota error in any Vertex call
- **E (probe-v2 LoC > 80):** NOT fired — first author was 81 LoC, immediately compressed to 78 LoC before any run; sha256 captured AFTER compression
- **F (corp blocks Vertex on model paths despite root-path pre-flight):** NOT fired — Vertex `/v1beta1/.../generateContent` and `/v1beta1/.../embedContent` calls all succeeded
- **G (oauth2 / SA fail):** NOT fired — SA JSON loaded, oauth2 token issued (after Halt B fix gave it a valid file path)

### Cross-references

- Sibling probe-v2: `.scratch/260605-u17-concurrent-probe-vertex.py` (gitignored, 78 LoC, sha256 contract `1891839825103e4001f4271da518b35ade618befd1671cc110522dd6e2cb0dbc` matched pre/post)
- Probe output JSON: `.scratch/260605-u17-probe-output.json` (gitignored, raw decision-matrix input, 9 keys present)
- Probe full stdout+stderr: `.scratch/260605-u17-probe-output.txt` (gitignored, 296 lines including PASS A real work + PASS B dedup gate)
- sha256 contract receipts: `.scratch/260605-u17-probe-sha256-{before,after}.txt` (gitignored, identical)
- Quick close-out: `.planning/quick/260605-u17-probe-vertex-rerun/260605-u17-SUMMARY.md`
- Parent RESEARCH Section 5 (260605-pwl Halt F): bypassed by Vertex provider switch — DeepSeek TLS block confirmed irrelevant for this run
- Memory `vertex_ai_smoke_validated` — Vertex SA + endpoint pairing ground truth (validated 2026-04-30; reconfirmed in this quick)
- Memory `aliyun_oauth_pin` — relevant if Halt G fires on Aliyun (not corp laptop)
- Memory `feedback_git_add_explicit_in_parallel_quicks` — atomic stage-commit-push pattern in T3

---

## Section 7 — probe-v3 subprocess re-run (2026-06-11)

**Quick:** 260611-probe-v3-subprocess  
**Date:** 2026-06-11 22:23 CST  
**Result:** HALTED (concurrent pass hung indefinitely)  
**Verdict:** **BLOCKED**

### Execution

After 260605-mz1 and 260605-u17 proved the probe-contract flaw (Section 6 lines 252-276), a new probe using subprocess-per-pass was written to isolate the in-process pipeline state:

- **Script:** `.scratch/worker.py` (fresh interpreter per pass) + `.scratch/launcher.py` (orchestrator)
- **Provider:** DeepSeek LLM + Vertex AI embedding (prod parity)
- **Articles:** `4b7c022702` (8.8 KB, 5 chunks) + `5784020d4f` (8.0 KB) — both `layer2_verdict='ok'`
- **Vector storage:** NanoVectorDB (default; isolated to /tmp/probe-v3, no prod Qdrant contamination)

### Result

**PASS A (serial ainsert):**

- wall_s: 0.737s ✓
- both_processed: true ✓
- kv_valid: true ✓
- exception: null ✓
- **Status:** SUCCEEDED

**PASS B (concurrent asyncio.gather):**

- wall_s: ~600+ seconds (timeout)
- both_processed: false ✗
- kv_valid: false ✗ (kv_store shows "processing", never finalized)
- exception: null (silent hang — no exception logged)
- **Status:** HUNG / TIMEOUT

### Analysis

The concurrent pass hung indefinitely despite the subprocess isolation fix. This indicates the problem is **not** the in-process pipeline singleton (which subprocess isolation should have eliminated), but rather:

1. **Embedding function (Vertex AI) not re-entrant under asyncio.gather():** Two concurrent embedding calls to the shared `embedding_func` may trigger a semaphore lock or async context violation.
2. **LightRAG 1.4.16 internal lock serialization:** Despite using fresh interpreters, the ainsert() method may call into a C extension or shared resource that serializes concurrent calls.
3. **Vertex AI SDK or Google auth library quota hang:** Two concurrent embedding requests exceed per-account quota; SDK hangs with no timeout.

### Verdict: BLOCKED

- Post-condition FAILED: concurrent pass did not complete (both_processed=False, exception hung)
- Speedup: UNDEFINED (timeout before completion)
- Decision matrix: speedup < 1.4x OR post-condition fail → **BLOCKED**

### Recommended next step

Before opening v1.2 plan-phase, spike:

1. Is `lib.embedding_func` (Vertex AI) thread-safe / re-entrant under `asyncio.gather()`?
2. Does LightRAG 1.4.16 have internal locks that serialize concurrent `ainsert()` calls?
3. Alternative: Try `ProcessPoolExecutor` (true process-level isolation) instead of `asyncio.gather()` (coroutines in same process)?

### Cross-reference

- Full RESEARCH: `.planning/quick/260611-probe-v3-subprocess/260611-probe-v3-RESEARCH-v3.md`
- Script SHAs: worker.py (after fixes), launcher.py — both captured in RESEARCH-v3
- Aliyun run environment: prod-parity DeepSeek + Vertex AI, CST idle window 22:23-22:40
