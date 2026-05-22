---
status: complete
phase: aim-1-code-env-deploy
source:
  - aim-1-1-SUMMARY.md
  - aim-1-2-SUMMARY.md
  - aim-1-3-SUMMARY.md
  - aim-1-4-SUMMARY.md
  - DEPLOY-04-EVIDENCE.md
started: 2026-05-23T00:00:00Z
updated: 2026-05-23T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Working tree reconciled on Aliyun (DEPLOY-01)
expected: |
  /root/OmniGraph-Vault/ HEAD reconciled to a known commit; `git status` reports clean
  working tree; HEAD hash recorded in DEPLOY-NOTES.md §DEPLOY-01 with reconcile rationale;
  origin confirmed as sztimhdd/OmniGraph-Vault.git; no secrets or connection details in artifact.
result: pass
evidence: |
  HEAD=4eaef45 (v1.0.x stable). Method: `git stash push -u` (fully reversible).
  Stash ref: `stash@{0}: aim-1 pre-deploy stash 20260522-1110`. git status = "nothing to
  commit, working tree clean". DEPLOY-NOTES.md §DEPLOY-01 contains all 4 subsections
  (Pre-reconcile / Decision / Execution / Post-reconcile). Commit 96502da.

### 2. Ingest venv operational on Aliyun (DEPLOY-02)
expected: |
  Python 3.11+ venv at /root/OmniGraph-Vault/venv/ with pip install -r requirements.txt
  EXITCODE=0 and `python -c "import lightrag, google.genai, deepseek; print('OK')"` passing.
  kb-api venv (venv/) and process PID 3512216 untouched throughout.
result: pass
deviation: |
  PLAN said venv/ but actual delivery used venv-aim1/ (sibling). Reason: kb-api occupies
  venv/ at Python 3.10.12 (< 3.11 requirement). Rather than destroying kb-api's prod venv
  (Option C in PLAN), user directed Option C-variant: sibling venv-aim1/ on py3.11.0rc1.
  This achieves the SC goal (py3.11+ venv with clean pip install + import smoke) without
  the destructive consequence the PLAN's Option C warning flagged. Deviation recorded in
  DEPLOY-NOTES.md §DEPLOY-02.
evidence: |
  venv-aim1/bin/python = Python 3.11.0rc1, 153 packages. pip install EXITCODE=0.
  Import smoke: 25/25 modules PASS (including lightrag, google.genai, openai, apify_client,
  playwright, lancedb, kuzu, pymupdf, litellm, instructor). venv/ py3.10.12 160 packages
  unchanged; kb-api PID 3512216 still serving uvicorn 127.0.0.1:8766.

### 3. 6 ingest provider keys in /root/.hermes/.env (DEPLOY-03)
expected: |
  DEEPSEEK_API_KEY, SILICONFLOW_API_KEY, OMNIGRAPH_VERTEX_SA_JSON_PATH, GEMINI_API_KEY,
  APIFY_TOKEN, APIFY_TOKEN_BACKUP all count=1 in /root/.hermes/.env; file mode 600
  root:root preserved pre- and post-extension; all 5 kb-api keys unchanged; no literal
  secret committed to repo or any planning artifact.
result: pass
evidence: |
  Option A (2-key minimal append): 4 of 6 keys were already present pre-extension;
  OMNIGRAPH_VERTEX_SA_JSON_PATH + APIFY_TOKEN_BACKUP appended via 2-key minimal append.
  Post-extension: mode -rw------- 1 root root 2403 bytes, 51 lines (was 49, +2 net).
  6/6 ingest keys count=1; 5/5 kb-api keys count=1 unchanged. APIFY_TOKEN_BACKUP
  transited Hermes→Aliyun SSH-pipe (literal never in agent context).
  Backup: /root/.hermes/.env.bak-aim1-20260522-233253 (2276 bytes, 600 root:root).
  venv-aim1 env-presence smoke: all 6 keys present-ok (sk-/AIza/apify_ap prefix shapes).

### 4. Layer 1 smoke passed on Aliyun (DEPLOY-04 pre-flight)
expected: |
  `scripts/local_e2e.sh layer1 5` reaches completion on Aliyun with EXIT=0; Vertex AI
  Gemini Layer 1 LLM reachable from cn-east-mainland; log in .scratch/local-e2e-layer1-*.log.
result: pass
deviation: |
  TLS bundle attempt 1 failed (OSError: could not find cert bundle at Windows-dev path
  /root/.claude/certs/combined-ca-bundle.pem). Fixed via caller-side REQUESTS_CA_BUNDLE
  override → venv-aim1 certifi bundle. Layer 1 attempt 2: EXIT=0. v3.5 harness fix deferred.
evidence: |
  log: local-e2e-layer1-20260523-010856.log (377 bytes, EXIT=0).
  5 articles selected. Verdicts: id=3 candidate / id=4 reject / id=5 reject /
  id=7 candidate / id=8 reject. totals: candidate=2 reject=3 none=0.
  Vertex AI Gemini Layer 1 reachable from Aliyun via OMNIGRAPH_VERTEX_SA_JSON_PATH. ✅

### 5. WeChat E2E smoke passed on Aliyun (DEPLOY-04)
expected: |
  `scripts/local_e2e.sh wechat <url>` reaches completion on Aliyun with EXIT=0; scrape
  → Layer 2 → vision cascade → LightRAG ainsert all exercised; scratch lightrag_storage/
  non-empty after run; production path (/root/.hermes/omonigraph-vault/) uncontaminated.
result: pass
deviation: |
  SCRAPE_CASCADE=ua,apify does NOT cascade through ingest_wechat.py's embedded scraper
  selection (architectural finding). All wechat runs method=ua (UA tier succeeded on every
  URL). Apify runtime verification deferred to v3.5 (accepted per user pre-approval).
evidence: |
  Run #1 (short article, 0 images): hash=99a2043522, body=15422 bytes, 7 entities + 7
  relations, 8 nodes / 7 edges, EXIT=0.
  Run #2 (image-rich, 2 images): hash=eec0c82bdb, body=71085 bytes, 2/2 SiliconFlow
  Qwen3-VL (7871ms + 7097ms), 21 entities + 20 relations, 29 nodes / 27 edges, EXIT=0.
  Scratch lightrag_storage populated (non-empty). Production path unchanged.

### 6. KOL batch E2E smoke passed on Aliyun (DEPLOY-04 extended — exceeds PLAN scope)
expected: |
  Full batch_ingest_from_spider.py --from-db path exercised: candidate-pool SQL → Layer 1
  batches → scrape → Layer 2 → vision cascade → LightRAG ainsert → reconcile gate;
  EXIT=0; budget compliance; scratch storage only.
  [NOTE: PLAN required only layer1+wechat. KOL batch is an additional validation beyond
  ROADMAP SC4 requirements — pure upside evidence.]
result: pass
evidence: |
  Run #3 (kol --from-db --max-articles 1, id=185 "李宏毅老师详解 Harness Engineering"):
  hash=4597c6fefe, 185 articles → 7 layer1 batches → 180 candidate / 5 reject → 1 processed.
  Scrape: UA HTTP 200, 2945 KB HTML, body=32227 bytes.
  Vision: 38/38 SiliconFlow Qwen3-VL-32B (6451-53622ms median ~12s).
  Layer 2: verdict=ok (chunks=2, budget=1320s).
  LightRAG: delta +56 nodes / +66 edges → final 85 nodes / 93 edges.
  batch_elapsed=778.44s / budget=28800s (2.7%). EXIT=0.

### 7. Production isolation maintained throughout aim-1 (DEPLOY-04 audit)
expected: |
  /root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml
  size and mtime unchanged across all smoke runs; entity_buffer/ count=0; kb-api PID
  3512216 still serving uvicorn 127.0.0.1:8766 throughout; kb-api.service.d/override.conf
  not touched; /root/.hermes/.env mode/ownership/line-count unchanged from DEPLOY-03.
result: pass
evidence: |
  Prod graphml: size=25841098 bytes, mtime=2026-05-17 23:55:39 (unchanged across all 3 runs;
  size delta=0). Prod entity_buffer/: count=0 (no scrape pollution from smoke).
  All smoke writes landed in /tmp/aim1-smoke/ exclusively. kb-api PID 3512216 still
  serving uvicorn 127.0.0.1:8766 throughout aim-1-4. /root/.hermes/.env mode 600 root:root
  51 lines 2403 bytes unchanged post-aim-1-3.
  Hermes alias unreachable from Aliyun this session → proxy attestation via prod LightRAG
  untouched accepted (deviation 4, recorded in SUMMARY).

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Deferred Items (not gaps — deliberate decisions)

- ⚠️ **Apify runtime unverified** (all 3 runs method=ua): accepted per user pre-approval; import-only
  verification (aim-1-2 25/25) covers apify_client 3.0.0 ABI compat. Runtime deferred to v3.5.
- ⚠️ **Hermes alias unreachable from Aliyun** (deviation 4): Windows ~/.ssh/config alias not
  forwarded to Aliyun jumphost. Proxy attestation via prod LightRAG unchanged accepted.
  v3.5: reciprocal SSH aliases for Hermes ↔ Aliyun direct pipe ops.
- ⚠️ **Harness TLS bundle path env-aware** (deviation 2): scripts/local_e2e.sh:73-74 hardcodes
  Windows-dev Cisco Umbrella path. Caller-side override is the current workaround. v3.5 fix.

## Gaps

[none — all 7 tests pass, no fix plans required]
