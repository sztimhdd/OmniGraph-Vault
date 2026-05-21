# Aliyun ECS Readiness Report — aim-0

Date: 2026-05-21
Aliyun ECS spec at test time: 2 vCPU / 14 GiB RAM (Q6 upgrade cancelled — recorded informationally)
Executor: aim-0-01-PLAN.md (Wave 1) + aim-0-02-PLAN.md (Wave 2)

Scope deviation from PLAN: per user direction "no operator for Aliyun — you SSH yourself", all aim-0 mutating operations on Aliyun (originally specified as operator-channel per CLAUDE.md PRINCIPLE #5) are run agent-side via the `aliyun-vitaclaw` SSH alias. PRINCIPLE #5's operator-channel rule is explicitly overridden for this milestone by user authorization. This applies to: WireGuard activation, scratch venv setup, READY-03 dry-run, and READY-04 smoke ingest. Hermes side remains read-only diagnostics only.

---

## Host spec (READY-01)

```
=== nproc ===
2
=== free -h ===
               total        used        free      shared  buff/cache   available
Mem:            14Gi       1.3Gi        11Gi        91Mi       2.5Gi        13Gi
Swap:          4.0Gi          0B       4.0Gi
=== df -h / ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda3        99G   23G   72G  24% /
```

Inline: vCPU=2, MemTotal=14Gi (13Gi available), RootAvail=72G, Swap=4G.

**READY-01: INFORMATIONAL — recorded.** Q6's 8 vCPU / 16 GB upgrade was cancelled; current shape is the working assumption for downstream gates. Soft observations:

- `df -h /` Avail = 72G — well above 5G threshold; ample headroom for scratch venv (~1-2 GB) and aim-1 production deploy.
- `free -h` Mem total = 14Gi — close to expected ~14 GiB; tightens headroom against READY-03's 8 GB peak-RSS budget but does not invalidate the gate. 4 GiB of swap available as safety margin.
- vCPU=2 — tight for LightRAG concurrency settings; aim-1 sizing must keep `embedding_func_max_async` and `graph_max_async` modest.

---

## Provider RTT — Aliyun vs Hermes same-day baseline (READY-02)

Captured 2026-05-21 evening (CST). 5 sequential samples per provider per side via `curl -o /dev/null -s -w '%{time_total}\n'`. Vertex from Aliyun was UNREACHABLE on first measurement (5×timeout), prompting WireGuard split-tunnel activation (see § WireGuard activation note below); Vertex re-tested post-WG.

Raw samples (seconds):

| Side | Provider | Sample 1 | Sample 2 | Sample 3 | Sample 4 | Sample 5 |
|---|---|---|---|---|---|---|
| Aliyun | DeepSeek | 0.123591 | 0.150129 | 0.148091 | 0.137378 | 0.147060 |
| Aliyun | SiliconFlow | 0.082423 | 0.083574 | 0.083161 | 0.078070 | 0.073966 |
| Aliyun | Vertex (pre-WG) | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT |
| Aliyun | Vertex (post-WG) | 1.499431 | 1.987139 | 1.483464 | 1.889765 | 1.977379 |
| Hermes | DeepSeek | 0.590519 | 0.483224 | 0.424310 | 0.484012 | 0.442003 |
| Hermes | SiliconFlow | 1.602259 | 0.949522 | 0.962695 | 0.953162 | 0.942221 |
| Hermes | Vertex | 0.331221 | 0.282021 | 0.305643 | 0.161797 | 0.301215 |

Computed:

| Provider | Aliyun median (s) | Aliyun p95 (s) | Hermes median (s) | Hermes p95 (s) | Ratio (Aliyun/Hermes) | PASS? |
|---|---|---|---|---|---|---|
| DeepSeek | 0.147 | 0.150 | 0.483 | 0.591 | 0.30× | ✅ PASS (Aliyun 3.3× faster) |
| SiliconFlow | 0.082 | 0.084 | 0.953 | 1.602 | 0.09× | ✅ PASS (Aliyun ~11× faster) |
| Vertex (post-WG) | 1.890 | 1.987 | 0.301 | 0.331 | 6.27× | ⚠️ WARN — exceeds 2× ratio |

**READY-02: WARN — Vertex partial pass.**

- DeepSeek + SiliconFlow PASS by wide margin: cn-east-mainland Aliyun is 3-11× faster to these providers than Hermes (residential Canada). Both exceed the production-readiness bar comfortably.
- Vertex from Aliyun routes via WireGuard split-tunnel to GCP Singapore (35.198.243.36) then onward to us-central1 — adds ~1.5-2.0s RTT vs Hermes direct path. Ratio 6.27× exceeds the 2× threshold.
- Per plan provision (`aim-0-01-PLAN.md` Step 2 Fail Action): "If only one provider fails, note it and continue — READY-02 partial pass is acceptable if the failing provider is Vertex AI." Vertex AI is the predicted-acceptable failure case; continue.
- Operational note: Vertex 1.89s median is workable for LightRAG embedding (~hundreds of calls per article × 1.89s ≈ 5-10 min/article embedding cost, dominant over LLM cost). aim-1 sizing must account for this; consider `embedding_func_max_async ≥ 8` to amortize the latency.
- The critical change is Vertex went from UNREACHABLE (network-blocked) to REACHABLE (1.89s) — gating goal achieved.

### WireGuard activation note (scope-creep extension to aim-0)

Vertex AI was UNREACHABLE from Aliyun cn-east-mainland on initial RTT measurement (5×timeout, despite `/etc/hosts` pin to 142.250.73.106 from the `aliyun_oauth_pin.md` memory). Decision (user, 2026-05-21): pause aim-0 RTT step, activate the pre-installed WireGuard split-tunnel config on Aliyun, then re-measure.

State observed pre-activation:

- Active config `/etc/wireguard/wg-gcp-sg.conf` already split-tunnel — AllowedIPs scoped to Google CIDRs (`142.250.0.0/15`, `142.251.0.0/16`, `172.217.0.0/16`, `172.253.0.0/16`, `216.58.192.0/19`, `216.239.32.0/19`, plus `10.0.0.0/24` for peer link). Endpoint `35.198.243.36:51820` (GCP Singapore).
- Backup file `wg-gcp-sg.conf.bak-split-tunnel-20260517-212515` exists with AllowedIPs=`0.0.0.0/0` (full-tunnel snapshot taken at moment of switching TO split-tunnel — not a config to use).
- Module not loaded; `.ko` file present at `/lib/modules/5.15.0-1032-realtime/kernel/drivers/net/wireguard/wireguard.ko`.
- ip_forward = 1.

Activation steps (run agent-side via SSH, per user override of operator-channel rule):

1. `modprobe wireguard` — module loaded, deps `curve25519_x86_64`, `libchacha20poly1305`, `libcurve25519_generic`, `ip6_udp_tunnel`, `udp_tunnel`.
2. `systemctl start wg-quick@wg-gcp-sg` — interface up at `10.0.0.2/24`, MTU 1420; routes added for all 6 Google CIDRs.
3. Verified handshake: `latest handshake: 22 seconds ago`, `transfer: 220 B received, 744 B sent` after first traffic; ICMP to endpoint host 35.198.243.36 RTT ~74ms.
4. Verified split-tunnel correctness: Vertex now HTTP 404 in 1.57s (post-WG path), DeepSeek HTTP 401 in 0.16s (native cn-east route preserved — did NOT route through Singapore).
5. `systemctl enable wg-quick@wg-gcp-sg` — persistent across reboots.

Aliyun own public key recorded for server-side reference: `NS8I+SaOgYoqfXl0xQnxDA2xL5CAOVHAS9qOR4ztmBE=`. Server peer pubkey already present in conf file (non-secret).

---

## LightRAG ainsert peak RSS dry-run (READY-03)

Executed 2026-05-21 21:37 → 22:04 CST (UTC 13:37 → 14:04). Agent-side SSH per user override of operator-channel rule.

**Article selected:** id=701, KOL pool (`layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL`, sorted by image_count DESC).

- URL: `http://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247497581&idx=1&sn=480ba094de631b19f023a29648be4fb9&chksm=fd8c5772cafbde64e7b0b9bc4c9246358bbe088f3610c43449ae4d47ac151f0fa77db8628216#rd`
- Title (post-scrape): `OpenClaw+Kimi K2.5+Moltbook保姆级部署指南，确实可以封神了！`
- Hash: `805773ee29`
- Body length: ~29,781 chars
- Image count: 55 (56 files including the cover) — heaviest in candidate set

**Mode:** Full production parity — DeepSeek LLM (Layer 2 + LightRAG entity extraction), SiliconFlow Qwen3-VL-32B primary vision, OpenRouter secondary, Vertex AI Gemini embedding (post-WG). All keys sourced from existing `/root/.hermes/.env` on Aliyun (STATE doc claim that Aliyun has Vertex SA only was outdated — actual file already provisioned with all production keys).

**Scratch workspace:** `/tmp/aliyun-readiness/{repo,venv,lightrag_storage,images}` only — production paths (`/opt/omnigraph-vault/`, `/etc/omnigraph/`) not touched.

**Command:**

```
/usr/bin/time -v /tmp/aliyun-readiness/venv/bin/python ingest_wechat.py "$ARTICLE_URL"
```

**`/usr/bin/time -v` summary:**

```
Command being timed: "/tmp/aliyun-readiness/venv/bin/python ingest_wechat.py http://mp.weixin.qq.com/s?__biz=MzU4NTE1Mjg4MA==&mid=2247497581&idx=1&sn=480ba094de631b19f023a29648be4fb9..."
User time (seconds): 53.66
System time (seconds): 0.87
Percent of CPU this job got: 3%
Elapsed (wall clock) time (h:mm:ss or m:ss): 26:46.26
Maximum resident set size (kbytes): 361604
Major (requiring I/O) page faults: 16
Minor (reclaiming a frame) page faults: 90074
Voluntary context switches: 18550
Involuntary context switches: 40467
Swaps: 0
File system inputs: 4400
File system outputs: 40248
Exit status: 0
```

**Pipeline observed in log (`/tmp/aliyun-readiness/ready03-20260521-213712.log`):**

- Scrape: method=ua (UA fallback succeeded — Apify not needed; cascade tier 1)
- Layer 2 + LightRAG entity extraction: 83 entities, 97 relations, graph written (DeepSeek LLM via cn-east-mainland direct route)
- Embedding: Vertex AI via WG split-tunnel; ainsert pipeline completed before vision phase began
- Vision cascade: 56 images via SiliconFlow primary, 100% success on first attempt; per-image latency 8-46s (mostly ~10s); 0 fallthroughs to OpenRouter / Gemini Vision
- 20 raw entities buffered to `entity_buffer/` (Cognee-retired buffer marker for downstream analysis)
- Final: `--- Successfully Ingested! ---`

**Computed:**

- Peak RSS = 361,604 kbytes = **353.13 MiB = 0.345 GiB**
- Gate predicate: `peak_rss_gb < 8.0` → **0.345 < 8.0** ✅
- Headroom: peak RSS uses 4.3% of 8 GB budget; 95.7% headroom remaining vs gate.
- Against host total RAM (14 GiB): peak RSS uses ~2.5% of total memory. No swap activity (`Swaps: 0`).

**READY-03: ✅ PASS — peak_rss_gb = 0.345 GB < 8.0 GB (gate)**

Q6's vCPU/RAM upgrade cancellation is comfortably absorbed: actual peak memory is more than 1 order of magnitude below the budget. The 14 GiB host has ample headroom for ingest workload, even with future LightRAG storage growth (graph currently empty in scratch test; production graph at ~1.6 GB on Hermes adds working-set pressure but stays well under budget). Wall-clock 26:46 for a 55-image article is consistent with Hermes baseline and within the v1.0.x dynamic timeout budget (`_compute_article_budget_s` would compute ~1620s for image_count=55, observed 1606s actual — within 1%).

---

## Smoke ingest E2E (READY-04)

Executed 2026-05-21 22:17 → 22:27 CST (UTC 14:17 → 14:27). Agent-side SSH per user override of operator-channel rule. Independent run from READY-03 — distinct article, distinct KOL, image_count complementary band (5-15 target vs READY-03's 56) to avoid double-counting evidence.

**Article selected:** id=567, KOL pool (`layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL`, image_count 5-15 band, distinct KOL from id=701).

- URL: `http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516624&idx=1&sn=971d123207c5e04194b43a61a398d0f3&chksm=feb4cf71c9c346675162bb94a8e28409ed92c4eecfd54b7800c967a9cd8a181af72203c4c0a0#rd`
- Title (post-scrape): `BM25 + Vectors：为什么真实 RAG 系统通常两者都需要`
- Hash: `e3b2b8e720`
- Body length: ~58,817 bytes (16,321 chars per Hermes pre-flight)
- Image count: 19 unique → 14 after small-image filter (filter dropped 5 < 300px)
- KOL: `MzU5OTM2NjYwNg==` (different from READY-03's `MzU4NTE1Mjg4MA==`)

**Mode:** Same env as READY-03 — full production parity from `/root/.hermes/.env` on Aliyun.

**Command:**

```
nohup /usr/bin/time -v /tmp/aliyun-readiness/venv/bin/python ingest_wechat.py "$ARTICLE_URL" > /tmp/aliyun-readiness/ready04-id567-20260521-221705.log 2>&1 &
```

PID 177220. Background ingest watched via tail+grep monitor.

**`/usr/bin/time -v` summary:**

```
Command being timed: "/tmp/aliyun-readiness/venv/bin/python ingest_wechat.py http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516624&idx=1&sn=971d123207c5e04194b43a61a398d0f3..."
User time (seconds): 57.03
System time (seconds): 0.85
Percent of CPU this job got: 9%
Elapsed (wall clock) time (h:mm:ss or m:ss): 9:49.84
Maximum resident set size (kbytes): 375660
Major (requiring I/O) page faults: 0
Minor (reclaiming a frame) page faults: 93421
Voluntary context switches: 18007
Involuntary context switches: 40754
Swaps: 0
File system inputs: 16
File system outputs: 22992
Exit status: 0
```

**Pipeline observed in log (`/tmp/aliyun-readiness/ready04-id567-20260521-221705.log`):**

- Scrape: method=ua (UA fallback first-tier success — no Apify, no MCP, no CDP fallthrough)
- Layer 2 + LightRAG entity extraction: 17 entities buffered, graph written (DeepSeek LLM via cn-east-mainland direct route)
- Embedding: Vertex AI gemini-embedding-2 via WG split-tunnel; ainsert pipeline completed before vision phase began
- Vision cascade: 14 images processed; 12/14 SiliconFlow primary success; 1 SiliconFlow timeout → OpenRouter HTTP 402 (prompt token limit exceeded) → Gemini Vision success (img_005); 1 additional Gemini fallthrough recorded — total 2/14 = 14.3% Gemini usage. Cascade alert fired (`gemini used for 14.3% of images (>5% threshold) -- upstream provider issues detected`); cascade behavior nominal — fallback succeeded, all 14 images described, 0 ingest failures.
- Final: `--- Successfully Ingested! ---`

**Storage + buffer evidence:**

- `lightrag_storage/` baseline (post READY-03): 4.9 MB → post READY-04: 11 MB (Δ ≈ +6 MB)
- `vdb_entities.json` 4.59 MB, `vdb_relationships.json` 4.91 MB — both populated by id=567 ainsert
- `entity_buffer/e3b2b8e720_entities.json` present (alongside READY-03's `805773ee29_entities.json`)
- Image artifacts at `/tmp/aliyun-readiness/images/e3b2b8e720/` (14 final files post-filter)

**Computed:**

- Peak RSS = 375,660 kbytes = 366.86 MiB = 0.358 GiB (slightly above READY-03's 0.345 GiB; consistent — second ingest into a non-empty graph)
- Wall-clock 9:49.84 vs predicted ~10 min for image_count=14 article — within budget
- Gate predicate (PLAN aim-0-02-PLAN.md `READY-04 PASS`): `Exit code 0 ∧ lightrag_storage non-empty ∧ entity_buffer/*.json exists for ingested article` — **all three satisfied** ✅

**READY-04: ✅ PASS — full E2E ingest succeeded against scratch-path Aliyun deployment**

Cascade observation (operational, not blocking): OpenRouter HTTP 402 prompt-token-limit error indicates the OpenRouter key on Aliyun is on a tier that caps prompt tokens at 1386; img_005 hit 1468. Resolution path is independent of aim-0 verdict — either upgrade OpenRouter tier or shrink Vision prompt; tracked as v1.x candidate, not a migration blocker.

---

## Decision: aim-0 PASS / FAIL → next step (aim-1 plan-phase)

| REQ | Predicate | Result | Verdict |
|---|---|---|---|
| READY-01 | Informational record of `nproc` / `free -h` / `df -h /` | 2 vCPU, 14 GiB RAM (13 Gi avail), 72 GiB root free | ✅ INFORMATIONAL — recorded |
| READY-02 | Each provider Aliyun median ≤ 2× Hermes median (same-day) | DeepSeek 0.30× ✅ · SiliconFlow 0.09× ✅ · Vertex post-WG 6.27× ⚠️ | ⚠️ WARN — Vertex partial pass (acceptable per PLAN aim-0-01 single-failure clause: "READY-02 partial pass is acceptable if the failing provider is Vertex AI") |
| READY-03 | peak_rss_gb < 8.0 (50% of 16 GB budget) | 0.345 GiB (4.3% of budget) | ✅ PASS — 95.7% headroom |
| READY-04 | Exit 0 ∧ lightrag_storage non-empty ∧ entity_buffer evidence present | Exit 0, storage 4.9→11 MB (+6 MB), buffer file present, 17 entities, 14/14 images | ✅ PASS |

**Overall aim-0 verdict: ✅ PASS (with WARN on Vertex RTT — acceptable & documented)**

Q6's vCPU/RAM upgrade cancellation is comfortably absorbed: the 2 vCPU / 14 GiB shape carries the workload at ~4% of the 8 GB peak-RSS budget on a 56-image heavy article, and ~9.6% CPU utilization on a 14-image typical article. WireGuard split-tunnel resolves Vertex unreachability at the cost of ~1.5-2.0s additional embedding RTT — workable for LightRAG embedding cadence at production scale; aim-1 sizing should default `embedding_func_max_async ≥ 8` to amortize.

### Operational observations (informational, not blocking)

1. **OpenRouter prompt-token cap (HTTP 402)** — Aliyun OpenRouter key tier caps prompts at 1386 tokens. Cascade fallback to Gemini works correctly; investigate at v1.x to keep Gemini usage < 5% threshold (current run 14.3%).
2. **Vertex RTT 1.89s median** — dominant single-cost factor in production embedding rate; tracked in PROJECT-Aliyun-Ingest-Migration-v1.md §6 risk row.
3. **WireGuard `wg-quick@wg-gcp-sg` enabled persistent** — survives reboots; no aim-1 action needed.

### Next step

**Hard-stop per STATE-Aliyun-Ingest-Migration-v1.md:138-167:** aim-0 PASS does NOT auto-flow into `/gsd:plan-phase aim-1`. Two deferred-action items must be resolved next, in this order, by the orchestrator:

1. **Gate 1 (P3, hard-stop)** — kb-4 vs aim-1 overlap audit via `AskUserQuestion` (3-way: supersede / parallel / serial). Must be answered before any aim-1 plan-phase invocation.
2. **Memo 2 (P4, register-only)** — forward-only append to `STATE-KB-v2.md` "v2.2-future" section about `translate_kb.py` incremental apply.sql flush + resume guard.

Both items remain queued; agent will not initiate either without explicit user direction.
