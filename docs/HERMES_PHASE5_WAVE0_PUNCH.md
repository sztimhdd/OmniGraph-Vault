# Hermes Punch List — Phase 5 Wave 0 Close-Out

**Opened:** 2026-05-02 by Claude dev-side planner
**Pre-requisite commit:** `585aa3b` (aget_docs_by_ids verification hook + 3 unit tests, Task 4.2 in v3.2-handoff prompt)
**Scope:** Three tasks (4.1 / 4.3 / 4.4 from the v3.2-handoff prompt) that require your production stack (real DeepSeek + real LightRAG + populated SQLite + WeChat QR session if re-scrape needed). Dev machine cannot execute these — R4 Cisco Umbrella TLS block.

**Outcome this closes:** Phase 5 Wave 0 officially closes. `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` is written. Wave 1 (RSS pipeline) unblocks.

---

## P0 — Task 4.1: Full reset + re-ingest

**Current state (from v3.2-handoff prompt §3):**
- `kv_store_full_docs.json`: 8 real docs
- `articles` rows in `kol_scan.db`: 378
- `articles.content_hash IS NOT NULL`: **0** (you already NULL'd all 57 per Task 0.8 prep)
- Embedding dim: 3072 (gemini-embedding-2 multimodal)

**Runbook** (per 05-00 PLAN Task 0.8 lines 727–740):

```bash
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && git pull --ff-only"
# Confirm HEAD is 585aa3b or later
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && git log --oneline -3"

# 1. Wipe LightRAG vector + graph + KV storage (preserve images/)
ssh -p <port> <user>@<host> "cd ~/.hermes/omonigraph-vault/lightrag_storage && \
  rm -f vdb_chunks.json vdb_entities.json vdb_relationships.json \
        kv_store_*.json graph_chunk_entity_relation.graphml full_docs.json"

# 2. Reset DB content_hash markers (should already be NULL; idempotent belt-and-braces)
ssh -p <port> <user>@<host> "sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
  'UPDATE articles SET content_hash = NULL WHERE content_hash IS NOT NULL'"

# 3. Full batch re-ingest — topic-filtered per D-10 catch-up policy
#    Keywords: openclaw, hermes, agent, harness (expand later as needed)
#    Expected wall-clock: ~60-90 min for ~50-150 filtered articles at 441s prod baseline
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && source venv/bin/activate && \
  nohup python batch_ingest_from_spider.py --from-db \
    --topic-filter openclaw,hermes,agent,harness --min-depth 2 \
    > /tmp/phase5-wave0-reingest.log 2>&1 &"
```

**Watch** (separate ssh session):

```bash
ssh -p <port> <user>@<host> "tail -F /tmp/phase5-wave0-reingest.log"
# Also watch checkpoint progression — stuck articles should be 0
ssh -p <port> <user>@<host> "python scripts/checkpoint_status.py --since '1h ago'"
```

**Gate** (verify AFTER re-ingest completes):

```bash
# A. LightRAG doc count should approximate DB ingested count (±5%)
ssh -p <port> <user>@<host> "jq 'keys | length' ~/.hermes/omonigraph-vault/lightrag_storage/kv_store_full_docs.json"
ssh -p <port> <user>@<host> "sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
  'SELECT COUNT(*) FROM articles WHERE content_hash IS NOT NULL'"
# Delta should be ≤ 5% — both numbers in same order of magnitude,
# no more "8 vs 57" ghost discrepancy

# B. Zero ghost articles — every content_hash NOT NULL row has a LightRAG doc
# Spot-check 5 random rows:
ssh -p <port> <user>@<host> "sqlite3 -header -column ~/OmniGraph-Vault/data/kol_scan.db \
  'SELECT url, content_hash FROM articles WHERE content_hash IS NOT NULL ORDER BY RANDOM() LIMIT 5'"
# Then python -c "import json; docs=json.load(open(...)); print(list(docs.keys())[:5])"
# Verify wechat_<hash> keys overlap
```

**Expected non-issues** (don't be alarmed):
- Some articles will legitimately fail classify/scrape (Vision cascade quota dips, content-length filter, etc). Those stay `content_hash IS NULL` on purpose — batch next-day picks them up.
- New Task 4.2 verification hook means any article where LightRAG returns status != PROCESSED gets skipped rather than ghosted. You'll see `WARNING post-ainsert verification: doc <id> ... skipping content_hash write` — that's the hook doing its job, not a bug.

**If anything goes sideways:**
- Share `/tmp/phase5-wave0-reingest.log` tail + `checkpoint_status.py` output
- Do NOT `git revert 585aa3b` — the hook is doing exactly what Task 0.8 specified; any regression is upstream (LightRAG doc_status shape, env, etc.) and needs diagnosis, not revert

---

## P1 — Task 4.3: Wave 0 benchmark verification

After P0 re-ingest completes cleanly:

```bash
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && source venv/bin/activate && \
  python tests/verify_wave0_benchmark.py > /tmp/wave0-benchmark.log 2>&1 && \
  python tests/verify_wave0_crossmodal.py > /tmp/wave0-crossmodal.log 2>&1"
```

**Gates** (from 05-00 PLAN success criteria lines 806–807):
- Chinese retrieval top-5 overlap ≥ **60%** per golden query
- Cross-modal text→image retrieval hits ≥ **1 of 5** golden cross-modal queries

Share both log tails back.

If overlap < 60%: means re-ingest produced a different graph shape than the pre-reset 8-doc graph. Diagnose before Wave 1.

---

## P2 — Task 4.4: kg_synthesize E2E image query

Final Wave 0 qualitative check — proves the image-URL binding fix (Hermes's 2f576b1) actually produces markdown with inline images:

```bash
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && source venv/bin/activate && \
  python kg_synthesize.py 'LightRAG 架构图' hybrid > /tmp/kg-synthesize-test.md 2>&1"
ssh -p <port> <user>@<host> "grep -c '!\[.*\](http://localhost:8765/' /tmp/kg-synthesize-test.md"
# Should be ≥ 1 — at least one inline ![desc](url) line
```

Try 2-3 more queries that should pull image-rich articles (your call; e.g., "Qwen3-VL 推理效果", "Hermes 执行流程"). Goal: subjective sense that the markdown is visual-rich, not text-only.

---

## Close-out — What to report back

After P0/P1/P2 all pass, a single message back here:

```
Hermes Phase 5 Wave 0 close-out — DONE
- P0 re-ingest: M articles ingested, LightRAG/DB gap = X% (≤5% target)
- P1 benchmarks: CN overlap Y%, cross-modal Z/5 hit
- P2 kg_synthesize: ![image](url) lines present in outputs for N/3 test queries
- Logs: /tmp/phase5-wave0-{reingest,benchmark,crossmodal}.log
```

Claude will then:
1. Write `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` closing Wave 0
2. Move Phase 5 Wave 0 to ROADMAP Done region
3. Kick off Wave 1 planning (RSS pipeline: 05-01, 05-02, 05-03, 05-03b)

---

## Red lines (same contract as prior Hermes punch lists)

- No `.planning/phases/1[2-7]*/` edits (v3.2 frozen)
- No `lib/` edits (v3.2 frozen except what you've already pushed through 2f576b1)
- No v3.1 / v3.2 Done region edits in REQUIREMENTS.md / ROADMAP.md
- No `--force`, no `--no-verify`
- DB mutations allowed per the runbook above (NULL content_hash, batch re-ingest auto-writes after verification)

---

*Drafted 2026-05-02 by Claude dev-side planner. Commit prerequisite: `585aa3b`.*
