# OmniGraph-Vault End-to-End Health Test

**Purpose:** Verify complete ingestion pipeline health from source scanning through knowledge graph indexing.

**Scope:** One full article cycle through both KOL and RSS sources, covering all 10 pipeline stages.

**Frequency:** Can be run daily or on-demand. Recommended: 1x/week or post-deployment.

**Expected Duration:** 15–30 minutes (wall-clock; includes waiting for async operations).

**Success Criteria:**
- ✅ Both KOL and RSS scans return candidates
- ✅ Layer 1 & 2 classification completes without NULL verdicts
- ✅ One article selected for full ingestion (ok verdict)
- ✅ End-to-end pipeline completes: scrape → rewrite → translate → vision → ainsert
- ✅ SQLite ingestions table shows `status='ok'` for the article
- ✅ graphml node/edge count increases
- ✅ LightRAG long_form synthesis can retrieve and cite the new article

---

## Pre-Flight Checklist

Run these read-only checks before starting the test:

```bash
ssh aliyun-vitaclaw << 'EOF'
# 1. Disk space: must be >5% free on /
df / | tail -1 | awk '{printf "Disk: %s used (%s)\n", $3, $5}'

# 2. Services alive: KOL scan, ingest, kb-api
systemctl is-active omnigraph-kol-scan-batch@1 omnigraph-daily-ingest kb-api

# 3. Dependencies reachable: Vertex, DeepSeek, SiliconFlow
cd /root/OmniGraph-Vault && python3 -c "
from lib.models import INGESTION_LLM, EMBEDDING_MODEL
print(f'INGESTION_LLM: {INGESTION_LLM}')
print(f'EMBEDDING_MODEL: {EMBEDDING_MODEL}')
"

# 4. Database accessible: kol_scan.db exists, graphml parses
sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT COUNT(*) FROM ingestions WHERE status='ok' LIMIT 1;"
python3 -c "import networkx as nx; g = nx.read_graphml('/root/.hermes/omonigraph-vault/lightrag_storage/graphml'); print(f'Nodes: {g.number_of_nodes()}, Edges: {g.number_of_edges()}')"
EOF
```

**Exit if any check fails.** Resolve the blocker before proceeding.

---

## Phase 1: Source Scanning

### 1a. KOL Scan

**Objective:** Discover recent WeChat Official Account articles.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Run a single KOL scan account (叶小钗 is reliable test account)
# --max-articles 5 limits the candidate pool for this test
python3 batch_scan_kol.py --max-accounts 1 --max-articles 5

# Capture the output
# Expected: "X articles discovered, Y pending classification"
EOF
```

**Check output:**
- Look for `ret=0` and article titles in the log
- If `ret=200003`, WeChat session is expired — run refresh script and retry
- If 0 articles discovered, pick a different account (user choice from kol_config.py FAKEIDS)

**Record:**
- Timestamp: ___________
- Articles discovered: _____ (should be > 0)
- Any errors: _____________

---

### 1b. RSS Scan

**Objective:** Discover recent RSS feed articles.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Run RSS classifier with a small batch for testing
# OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP env var caps classification throughput
python3 scripts/rss_classifier.py --max-articles 3

# Or if that doesn't exist, use batch_classify:
# python3 batch_classify_kol.py --topics ai --max-articles 3

# Expected: classifier runs, marks some as candidate, some as reject
EOF
```

**Check output:**
- Look for `candidate=X reject=Y` summary
- If all rejected or 0 articles, RSS feed may be stale — note but continue with KOL articles

**Record:**
- Timestamp: ___________
- RSS articles processed: _____
- Candidate count: _____ (should be > 0)

---

## Phase 2: Layer 1 & Layer 2 Classification

### 2. Combined Classification Run

**Objective:** Filter candidates through dual-layer DeepSeek classification.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Run the classification pipeline (both Layer 1 & Layer 2)
# This reads recent candidates from kol_scan.db and classifies them
python3 batch_classify_kol.py --topics ai --max-articles 10

# Capture the final summary:
# Expected: "layer1: candidate=X reject=Y null=0, layer2: ok=A reject=B"
EOF
```

**Check output:**
- Layer 1 verdict: should have candidate > 0
- Layer 2 verdict: should have ok > 0 (at least 1 article passed both filters)
- NULL count: should be 0 (if any NULL, note the error)

**Record:**
- Layer 1 verdict: candidate=___ reject=___ null=___
- Layer 2 verdict: ok=___ reject=___
- Errors: _________________

---

## Phase 3: Article Selection

### 3. Pick One Article for Full Ingestion

**Objective:** Select a single article that passed both layers for end-to-end verification.

```bash
ssh aliyun-vitaclaw << 'EOF'
# Query the database for a recent ok article
cd /root/OmniGraph-Vault
sqlite3 data/kol_scan.db << 'SQL'
SELECT id, title, url, layer2_verdict 
FROM ingestions 
WHERE layer2_verdict='ok' AND scraped_at IS NULL
ORDER BY created_at DESC 
LIMIT 1;
SQL
EOF
```

**Record the selected article:**
- Article ID: ___________
- Title: ___________________________________________
- URL: ___________________________________________
- Source: KOL / RSS (circle one)

---

## Phase 4: Scrape → Vision → Ainsert (Full Pipeline)

### 4a. Scrape

**Objective:** Download article HTML and extract markdown body.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Scrape the selected article URL via the ingest_wechat.py scraper
python3 ingest_wechat.py "PASTE_URL_HERE"

# Or for RSS: use the RSS scraper (if different)
# python3 multimodal_ingest.py "PASTE_URL_HERE"

# Expected output:
# - "Scraping successful using method: apify" or "method: cdp" or "method: mcp"
# - Body text extracted (N characters)
# - Images downloaded (N images)
EOF
```

**Record:**
- Scrape timestamp: ___________
- Body length (chars): _____
- Images downloaded: _____
- Scrape method used: apify / cdp / mcp (circle one)
- Any errors: _____________

---

### 4b. Rewrite (Optional, but Verify)

**Objective:** LLM rewrites the article body for clarity (via kb-api or local script).

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Check if rewrite_body_cron has run recently:
sqlite3 data/kol_scan.db "SELECT body_rewritten FROM ingestions WHERE id=YOUR_ARTICLE_ID"

# If NULL, manually trigger rewrite for this article:
python3 scripts/rewrite_body_cron.py --article-id YOUR_ARTICLE_ID --limit 1

# Expected: body_rewritten field populated with rewritten text
EOF
```

**Record:**
- Body rewritten: yes / no
- Rewrite timestamp: ___________

---

### 4c. Translate

**Objective:** Translate article body to target language (if applicable).

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Check if translation already ran:
sqlite3 data/kol_scan.db "SELECT body_translated FROM ingestions WHERE id=YOUR_ARTICLE_ID"

# If NULL and needed, manually trigger:
python3 scripts/translate_body_cron.py --article-id YOUR_ARTICLE_ID --limit 1

# Expected: body_translated field populated
EOF
```

**Record:**
- Body translated: yes / no
- Translate timestamp: ___________

---

### 4d. Vision Cascade (Image Descriptions)

**Objective:** Generate descriptions for all images via SiliconFlow → OpenRouter → Gemini cascade.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# The batch_ingest_from_spider.py pipeline handles this automatically
# But you can verify the results:
ls /root/.hermes/omonigraph-vault/images/YOUR_ARTICLE_HASH/

# Check if vision descriptions were generated:
# (this is captured in entity_buffer/YOUR_ARTICLE_HASH_entities.json)
cat /root/.hermes/omonigraph-vault/entity_buffer/YOUR_ARTICLE_HASH_entities.json | \
  python3 -m json.tool | head -50
EOF
```

**Record:**
- Images with descriptions: _____
- Vision provider used: SiliconFlow / OpenRouter / Gemini (circle one)
- Errors: _____________

---

### 4e. Full Ingest (Ainsert)

**Objective:** Run the complete ingestion pipeline: scrape → classify → extract → embed → KG ainsert.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Option A: Run via batch_ingest_from_spider.py (recommended — matches production)
python3 batch_ingest_from_spider.py --topics ai --depth 1 --max-articles 1 --reset-checkpoint

# This will:
# 1. Fetch 1 article (max-articles 1)
# 2. Run through Layer 1 & 2 if not yet classified
# 3. Scrape, extract, download images
# 4. Vision cascade on images
# 5. LightRAG ainsert (entity extraction, relation building, embedding, graph update)
# 6. Verify PROCESSED status

# Capture the final summary line, e.g.:
# "batch 0: n=1 candidate=1 reject=0 null=0 skipped_ingested=0 ok=1 failed=0 skipped=0 wall_sec=287.4"

# Watch for any of these errors:
# - TransportError (network issue with LLM/embedding provider)
# - Timeout (LightRAG worker timeout)
# - PROCESSED-gate failure (ainsert verification didn't complete)
EOF
```

**Record:**
- Ingest start timestamp: ___________
- Ingest end timestamp: ___________
- Wall time: _________ seconds
- Batch summary: 
  - n (submitted): _____
  - ok (succeeded): _____
  - failed: _____
  - Any errors: _____________

---

## Phase 5: Database Verification

### 5. Verify Article in SQLite

**Objective:** Confirm the article was written to the database with ok status.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Query the ingestions table
sqlite3 data/kol_scan.db << 'SQL'
SELECT 
  id, 
  title, 
  status, 
  layer1_verdict, 
  layer2_verdict, 
  scraped_at, 
  ingested_at,
  LENGTH(body) as body_len
FROM ingestions 
WHERE id=YOUR_ARTICLE_ID;
SQL

# Expected output: one row with status='ok', ingested_at is recent (within last 10 min)
EOF
```

**Record:**
- Row found: yes / no
- status: ___________
- layer1_verdict: ___________
- layer2_verdict: ___________
- ingested_at: ___________

---

### 6. Verify graphml Updated

**Objective:** Confirm LightRAG graphml file was updated with new nodes/edges.

```bash
ssh aliyun-vitaclaw << 'EOF'
# Get baseline from earlier (if you didn't capture, that's OK)
python3 -c "
import networkx as nx
g = nx.read_graphml('/root/.hermes/omonigraph-vault/lightrag_storage/graphml')
print(f'Current graphml: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges')
print(f'Graphml mtime: $(stat -c %y /root/.hermes/omonigraph-vault/lightrag_storage/graphml)')
"
EOF
```

**Record:**
- graphml mtime (should be recent): ___________
- Node count (compare to baseline): _____ → _____
- Edge count (compare to baseline): _____ → _____
- New nodes added: _____ (should be > 0)
- New edges added: _____ (should be > 0)

---

## Phase 6: RAG Retrieval Verification

### 7. Test Long-Form Synthesis (Query the KG)

**Objective:** Verify LightRAG can retrieve and cite the newly ingested article.

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Query the KG for content related to the article topic
# Use a query that should match entities/relationships from the new article
# Example: if article is about "AI agents", query for that

python3 kg_synthesize.py "What did the most recent article say about AI agents?" hybrid

# Expected output:
# - Long-form response with 1-5 sources cited
# - confidence=kg (not just fts5_fallback)
# - sources > 0 (not empty)
# - The new article URL appears in the references
EOF
```

**Record:**
- Query used: ___________________________________________
- Response length (chars): _____
- Sources cited: _____
- confidence: kg / fts5_fallback / none (circle one)
- New article appears in sources: yes / no

---

## Phase 7: Final Health Report

### Summary Checklist

| Stage | Status | Notes |
|-------|--------|-------|
| KOL Scan | ✅ / ⚠️ / ❌ | Articles discovered: _____ |
| RSS Scan | ✅ / ⚠️ / ❌ | Articles discovered: _____ |
| L1 Classification | ✅ / ⚠️ / ❌ | Candidate: _____ Null: _____ |
| L2 Classification | ✅ / ⚠️ / ❌ | Ok: _____ Null: _____ |
| Scrape | ✅ / ⚠️ / ❌ | Method: _____ Body: _____ chars |
| Rewrite | ✅ / ⚠️ / ❌ | Completed: yes/no |
| Translate | ✅ / ⚠️ / ❌ | Completed: yes/no |
| Vision | ✅ / ⚠️ / ❌ | Images: _____ Provider: _____ |
| Ainsert | ✅ / ⚠️ / ❌ | Wall: _____ sec Status: ok/failed |
| DB Verify | ✅ / ⚠️ / ❌ | ingested_at: _____ |
| graphml Update | ✅ / ⚠️ / ❌ | +Nodes: _____ +Edges: _____ |
| RAG Query | ✅ / ⚠️ / ❌ | Sources: _____ Confidence: _____ |

**Overall Health:** 🟢 PASS / 🟡 DEGRADE / 🔴 FAIL (circle one)

**Blockers (if any):**
1. ___________________________________________
2. ___________________________________________
3. ___________________________________________

**Improvements for next run:**
1. ___________________________________________
2. ___________________________________________

---

## Troubleshooting

### Common Issues

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| WeChat ret=200003 | Session expired | Run `ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py"` |
| 0 RSS candidates | Feed stale or all rejected | Use KOL articles instead; check RSS feed URL in config |
| Layer 1 null verdict | DeepSeek timeout or API error | Check `journalctl -u omnigraph-daily-ingest` for error; retry |
| Scrape fails (all methods) | Article structure changed or access blocked | Manually verify URL opens in browser; try different account |
| Vision timeout | SiliconFlow quota depleted | Check balance; cascade will fall back to OpenRouter/Gemini |
| Ainsert hangs (1h+) | LightRAG worker deadlock or embedding timeout | Kill process; check `LIGHTRAG_EMBEDDING_TIMEOUT` env |
| graphml unchanged | Ainsert didn't reach completion | Check for `.tmp` file (mid-write crash); verify PROCESSED gate |
| RAG returns 0 sources | graphml-Qdrant divergence (vector chunks not aligned) | Known issue #44; restart kb-api and retry |

---

## Cleanup & Next Steps

### After Test Completion

```bash
ssh aliyun-vitaclaw << 'EOF'
# Optional: view the full log of what just ran
journalctl -u omnigraph-daily-ingest --since "30 min ago" | tail -100

# Optional: manually verify the article is in the KG
cd /root/OmniGraph-Vault
python3 query_lightrag.py "Summarize the most recent article"

# Cleanup checkpoint if you used --reset-checkpoint
# (normally not needed; checkpoints auto-clean after 7 days)
EOF
```

### Report Results

Fill in the Health Report above and share with the team. If all green, pipeline is healthy. If any yellow/red, file an issue with the blockers list.

---

## Appendix: Command Reference

**Quick single-command end-to-end (if you trust the pipeline):**

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# KOL + RSS scan
python3 batch_scan_kol.py --max-accounts 1 --max-articles 3
python3 scripts/rss_classifier.py --max-articles 1

# Classification
python3 batch_classify_kol.py --topics ai --max-articles 3

# Full ingest (will pick an ok-verdict article)
python3 batch_ingest_from_spider.py --topics ai --depth 1 --max-articles 1

# Verify
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM ingestions WHERE status='ok' AND ingested_at > datetime('now', '-30 min')"

# Test RAG
python3 kg_synthesize.py "What was the main topic of the most recent article?" hybrid
EOF
```

**Time estimate:** 15–30 minutes depending on network latency and provider response times.
