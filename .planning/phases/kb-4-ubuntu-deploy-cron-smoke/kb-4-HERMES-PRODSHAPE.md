# kb-4-07 Prod-shape smoke (Aliyun-retargeted)

**Phase:** kb-4-ubuntu-deploy-cron-smoke / 07
**Date:** 2026-05-22
**Host:** aliyun-vitaclaw (101.133.154.49) — NOT Hermes (filename retained per kb-4 supersession map)
**Verdict:** PASS
**Evidence:** `.scratch/kb-4-07-aliyun-evidence-260522.log` (≈170 lines)

---

## Why filename says "HERMES" but content is Aliyun

Per `STATE-KB-v2.md:174-189` (Gate 1 supersession map), kb-4-07 was originally
specified against Hermes as host. Production deployment of kb-api +
vitaclaw-site landed on Aliyun ECS (101.133.154.49) instead. Filename
retained for supersession traceability; ALL probe targets are
Aliyun-retargeted.

---

## Scope (kb-4-lite Gate 1 Option A)

Goal: Verify production-shape kb-api on real prod traffic patterns.

5 probe families:
1. SSH + systemd surface
2. DB integrity + schema (820-article scale)
3. HTTP layer (Caddy reverse-proxy + localhost direct)
4. NEVER-500 contract on synthesize job (15+ polls, ZERO 5xx)
5. og:* per-article metadata + FTS trigram correctness

Plus 1 unplanned root-cause diagnosis + remediation:
6. cgroup MemoryHigh throttle (2G insufficient → 4G insufficient → infinity/8G)

---

## Findings

### F1 — Caddy route map (verified)

```
/kb/api/*        → uri strip_prefix /kb → reverse_proxy 127.0.0.1:8766
/kb/static/img/* → uri strip_prefix /kb → reverse_proxy 127.0.0.1:8766
/kb/*            → root /var/www/kb, strip_prefix /kb, try_files
```

**Implication for direct-localhost probes:** must use `/api/...`, NOT
`/kb/api/...`. The `/kb` prefix is a Caddy public-route convention,
stripped before reaching kb-api.

### F2 — DB scale (820 articles)

| Metric | Value | Notes |
|---|---|---|
| `articles` rows | 820 | up from kb-3 baseline ~520 |
| `layer2_verdict=ok` | 103 (12.6%) | DATA-07 visibility 2× kb-3 (6.4%) |
| `layer2_verdict=reject` | 30 | |
| `layer2_verdict=NULL` | 687 | not yet classified |
| `articles_fts` rows | 197 (24%) | 623-article gap; FTS rebuild candidate for kb-5 |
| `articles_fts` tokenizer | `trigram` | requires queries ≥3 chars |
| `kb_visible` column | absent | dev-runtime artifact, not on prod |
| layer2 alphabet observed | NULL/ok/reject | dev-runtime "keep" not present |

### F3 — NEVER-500 contract: PASS

| Metric | Result |
|---|---|
| Polls | 16 |
| HTTP 5xx | 0 |
| HTTP 200 | 15 |
| HTTP 000 (client timeout) | 1 (poll[1], during graph load — not a server 5xx) |
| Terminal envelope captured | yes (poll[16]) |
| kg-confidence field present | yes (`confidence:"no_results"`) |
| fallback_used | true |

**Terminal envelope (poll[16]):**

```json
{
  "job_id": "fb52986f76ab",
  "status": "done",
  "result": {
    "markdown": "> Synthesis + fallback both failed.\n\nReason: C1 timeout; FTS5 reason: OperationalError",
    "confidence": "no_results",
    "fallback_used": true,
    "sources": [],
    "entities": [],
    "error": "C1 timeout | fts5: OperationalError: fts5: syntax error near \"?\""
  },
  "fallback_used": true,
  "confidence": "no_results",
  "error": "C1 timeout | fts5: OperationalError: fts5: syntax error near \"?\""
}
```

**Why this is PASS, not FAIL:** the NEVER-500 contract requires that
*every* error path graceful-degrades into HTTP 200 + structured envelope.
The C1 LLM timeout (180s ceiling) and FTS5 query syntax error (special
character `?` from question text) are both severe internal failures
that, in a naive implementation, would manifest as 5xx. They did not.
Both surfaced as informational fields in a 200-status JSON body. This
is exactly what kb-3 §3 8-state matrix promises.

### F4 — Synthesize endpoint schema (corrected)

| Field | Original probe | Corrected |
|---|---|---|
| Request | `{"q": "..."}`  → HTTP 422 | `{"question": "..."}` → HTTP 202 |
| Response (running) | — | `{"job_id":"...","status":"running"}` |
| Polled key | `task_id` | `job_id` |
| Poll URL | `/api/synthesize/<task_id>` | `/api/synthesize/<job_id>` |

### F5 — og:* metadata (per-article gap)

All 5 og:* tags PRESENT but every value is template default:

```html
<meta property="og:title"       content="企小勤知识库 — AI Agent 技术内容站" />
<meta property="og:description" content="AI Agent 技术圈双语知识库" />
<meta property="og:image"       content="/kb/static/VitaClaw-Logo-v0.png" />
<meta property="og:type"        content="website" />
<meta property="og:locale"      content="zh_CN" />
<meta property="og:url"         content="/kb/" />
```

**Gap:** `og:title` should be article title, `og:description` excerpt,
`og:image` article hero, `og:url` per-article canonical. Currently all
are site-wide defaults — social-share previews would show site name +
logo, not article-specific preview.

**Defer to v1.1:** not v1.0 / kb-4 blocker. Tracked as `kb-5-og-per-article`
candidate.

### F6 — FTS trigram correctness (not a bug)

```
SELECT MATCH 'AI'         → 0   (2 chars, structurally cannot match)
SELECT MATCH 'AIA'        → 3   (3 chars, minimum threshold)
SELECT MATCH 'agent'      → 136
SELECT MATCH 'memory'     → 45
SELECT MATCH 'Cloudflare' → 1
```

The Probe 3 empty-result on `q=AI` is **expected behavior**, not a bug.
trigram tokenizer requires ≥3 character queries. UI affordance for
short-query users (autocomplete, suggested queries, "minimum 3 chars"
hint) is a kb-5 candidate.

---

## Cgroup remediation narrative (2-iteration bump)

### Pre-state (pre-bump)

```
MemoryHigh=2G  MemoryMax=2.8G  KB_DEFAULT_LANG=zh-CN
```

LightRAG graph (22412 nodes / 31566 edges) loads to 2.0+ GB resident.
`MemoryHigh=2G` is a soft PSI-throttle threshold: when crossed, kernel
reclaim throttles all syscalls in the cgroup. Result: uvicorn workers
hang on every endpoint after first synthesize POST triggers graph load.

System has 13.7G headroom. This is purely a cgroup config issue, NOT
host memory pressure.

### Iteration 1 — INSUFFICIENT

```
MemoryHigh=4G  MemoryMax=6G
```

Logic: assumed graph footprint ~2G + headroom = 4G soft cap should hold.

Reality: during initial graph load (entity_chunks=22412, relation_chunks=31567,
KV stores being warmed) `MemoryCurrent` peaked at **4.13G** transiently —
exceeded `MemoryHigh=4G`, PSI throttle re-engaged exactly as 2G case.

15-poll probe under this config: ALL 15 returned HTTP 000 / 5s timeout.
Process completely silent in journalctl after the "Loaded graph from..."
log entry at 21:19:32.

### Iteration 2 — CURRENT (PASS)

```
MemoryHigh=infinity  MemoryMax=8G  KB_DEFAULT_LANG=zh-CN
```

Logic: kb-api is the **single** prod service on this host (13.7G
headroom). The dual-soft-hard cgroup pattern is the wrong design for
single-tenant prod where the only legitimate use of `MemoryHigh` would
be to throttle one tenant's burstiness in favor of another. With one
tenant, `MemoryHigh=infinity` (disable PSI) + `MemoryMax` (hard OOM
guard) is the canonical pattern.

Outcome:
- Graph loaded successfully through transient peak (no soft cap to
  trigger reclaim)
- 16-poll NEVER-500 probe: 0 × 5xx, terminal envelope captured
- Steady-state post-load: `MemoryCurrent=1.88G` under 8G hard cap
  (4.25× runway for KG growth through ~30k+ nodes)

### Files changed

```
/etc/systemd/system/kb-api.service.d/override.conf
/etc/systemd/system/kb-api.service.d/override.conf.bak-260522  (pre-bump backup)
```

Caddy unmodified. Systemd unit file (main `kb-api.service`) unmodified.
Binary unmodified. App code unmodified.

---

## What changed on prod

| Asset | Change | Notes |
|---|---|---|
| `kb-api.service.d/override.conf` | 2G/2.8G → infinity/8G | 2-iter |
| `kb-api.service.d/override.conf.bak-260522` | new file | pre-bump backup |
| Caddy | unchanged | |
| `/var/www/kb/` static SSG | unchanged | |
| App binary / code | unchanged | |
| DB (`/root/OmniGraph-Vault/data/kol_scan.db`) | unchanged | |

---

## What did NOT execute (out of scope per Gate 1 Option A)

| Item | Status | Reason |
|---|---|---|
| og:* per-article metadata override | not done | v1.1 candidate (kb-5) |
| FTS5 article-pool fill (623 gap) | not done | requires fts rebuild script, kb-5 |
| FTS5 query special-char sanitizer (the `?` issue) | not done | kb-5 hardening |
| Rerank model config | not done | LightRAG warning, not blocking |
| Aliyun cron install | kb-4-08 scope | sequential gate after this PASS |

---

## Closure criteria (per kb-4-07 PLAN)

| Criterion | Met? | Evidence |
|---|---|---|
| SSH connectivity OK | yes | Probe 1 |
| systemd kb-api active | yes | Probes 1, 7 (post-bump), 8 |
| DB integrity_check ok | yes | Probe 2 |
| Caddy public route 200 | yes | Probe 3 (`/kb/api/articles`) |
| Localhost direct 200 | yes | Probe 7 sanity (`/api/articles?limit=1`) |
| Synthesize POST 202 + job_id | yes | Probe 8 (`fb52986f76ab`) |
| 15+ polls ZERO 5xx | yes (16 polls) | Probe 8 |
| Terminal envelope captured | yes | Probe 8 poll[16] |
| kg-confidence field present | yes | `"confidence":"no_results"` |
| Graceful-degrade on internal failure | yes | C1 timeout + FTS5 syntax error → HTTP 200 body |
| Evidence log saved | yes | `.scratch/kb-4-07-aliyun-evidence-260522.log` |

**Verdict: PASS**

---

## Cross-references

- `STATE-KB-v2.md:174-189` — Gate 1 supersession map (kb-4-07 host pivot)
- `kb-3-UI-SPEC.md:§3` — QA 8-state matrix terminal envelope contract
- `kb-4-07-hermes-prodshape-smoke-PLAN.md` — original PLAN (Hermes-targeted)
- `.scratch/kb-4-07-aliyun-evidence-260522.log` — raw probe evidence
- `kb-4-08-verification-close-PLAN.md` — next phase (cron install + close)
