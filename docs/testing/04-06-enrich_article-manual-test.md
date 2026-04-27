# Manual Test Guide — `enrich_article` Hermes Skill (Phase 4 Wave 4)

**Purpose:** End-to-end validation of the top-level `enrich_article` Hermes skill that
orchestrates the full per-article enrichment pipeline (per-question for-loop over
`extract_questions` → `zhihu-haowen-enrich` → `fetch_zhihu` → `merge_and_ingest`).

This test cannot be driven from the orchestrator's SSH session because it requires
a live interactive Hermes agent turn-taking through skill invocations, CDP browser
control, and (potentially) the D-13 Telegram login-recovery branch.

**Who runs this:** You, on the remote Hermes PC (`OH-Desktop`, WSL2 Linux), via an
interactive Hermes session.

**Estimated time:** 10–20 minutes, excluding LLM/CDP wait times.

---

## 0. Pre-flight checklist

Before starting, confirm on the remote PC:

```bash
# (a) gsd/phase-04 is checked out OR the skill files are deployed
ls ~/OmniGraph-Vault/skills/enrich_article/SKILL.md
ls ~/OmniGraph-Vault/skills/zhihu-haowen-enrich/SKILL.md
ls ~/OmniGraph-Vault/enrichment/extract_questions.py
ls ~/OmniGraph-Vault/enrichment/fetch_zhihu.py
ls ~/OmniGraph-Vault/enrichment/merge_and_ingest.py

# (b) Hermes sees both skills
/home/sztimhdd/.local/bin/hermes skills list | grep -E "enrich_article|zhihu-haowen-enrich"
# expect both present with source=local, status=enabled

# (c) SQLite has the phase-4 columns (orchestrator already migrated this)
python3 -c "import sqlite3; c=sqlite3.connect('/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db'); print([r[1] for r in c.execute('PRAGMA table_info(articles)')])"
# expect 'enriched' in the list

# (d) Edge CDP is running (port 9223) for the zhihu-haowen-enrich skill
ss -ltn | grep 9223
# expect LISTEN on 127.0.0.1:9223 (or equivalent); skill needs CDP for zhida.zhihu.com

# (e) Gemini burst capacity: check if you recently hit the 20-RPM limit
# If yes, wait ~60s before starting. Otherwise proceed.
```

If any check fails, fix before continuing.

---

## 1. Test inputs

- **Article hash:** `8ac04218b4`  (one of the three captured golden-fixture articles)
- **Article URL:** `https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA`
- **Article MD path:** `~/.hermes/omonigraph-vault/images/8ac04218b4/final_content.md`

Rationale: already-scraped, 2 images, no login wall, small-ish markdown (~10KB).

---

## 2. Test procedure

Open an interactive Hermes session:

```bash
/home/sztimhdd/.local/bin/hermes agent
```

Paste this prompt into Hermes:

```
Please enrich the WeChat article at
~/.hermes/omonigraph-vault/images/8ac04218b4/final_content.md
using the enrich_article skill. The article URL is
https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA and the content
hash is 8ac04218b4.

Pace LLM calls at ≤1 per 5 seconds to respect Gemini burst quota (20 RPM
on flash-lite). If you hit a 429, wait 60 seconds and retry once.

When complete, report which questions were extracted, which Zhihu URLs
were found, and whether the final LightRAG ingest succeeded.
```

Hermes should:

1. **Invoke `enrich_article`** skill (progressive disclosure — reads SKILL.md).
2. **Run `extract_questions`** (Gemini flash-lite + `google_search` grounding) →
   produces `~/.hermes/omonigraph-vault/enrichment/8ac04218b4/questions.json` with
   1–3 questions.
3. **For each question (q_idx = 0..N-1):**
   a. **Invoke `zhihu-haowen-enrich`** sub-skill. This drives `zhida.zhihu.com`
      via CDP (Edge on port 9223) to find the best-cited Zhihu answer URL.
      - **D-13 Telegram fallback:** if zhida.zhihu.com shows a login wall, the
        skill will `send_message` to Telegram with `MEDIA:` attachments so you
        can manually log in on your phone and signal continuation. Expect this
        to trigger at least once.
      - Writes `~/.hermes/omonigraph-vault/enrichment/8ac04218b4/<q_idx>/haowen.json`.
   b. **Run `fetch_zhihu`** on the URL from haowen.json → fetches the Zhihu page,
      filters <100px images, runs Gemini Vision on retained images, writes
      `~/.hermes/omonigraph-vault/enrichment/8ac04218b4/<q_idx>/final_content.md`
      plus numbered `*.jpg` files.
4. **Run `merge_and_ingest 8ac04218b4 --article-path ... --article-url ...`** →
   merges 好问 summaries inline into the WeChat MD, inserts 1 WeChat doc + up to
   3 Zhihu docs into LightRAG with D-08 IDs (`wechat:8ac04218b4`,
   `zhihu_8ac04218b4_<q_idx>`, `file_paths=[enriches:8ac04218b4]`), updates
   `articles.enriched = 2` and `ingestions.enrichment_id = "enrich_8ac04218b4"`.

---

## 3. Expected outputs

### 3.1 Filesystem artifacts (on remote)

```
~/.hermes/omonigraph-vault/enrichment/8ac04218b4/
├── questions.json                          # 1-3 questions with `context` field
├── 0/
│   ├── haowen.json                         # { source_url, summary, ... }
│   ├── final_content.md                    # Zhihu answer markdown
│   ├── 0.jpg, 1.jpg, ...                   # filtered + described images
│   └── metadata.json                       # image_pipeline output
├── 1/                                      # same shape as 0/
├── 2/                                      # same shape as 0/ (if 3 questions)
└── final_content.enriched.md               # merged WeChat+haowen MD
```

### 3.2 SQLite state changes

```sql
-- Before:
SELECT enriched FROM articles WHERE url = 'https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA';
-- expected: 0 (or NULL)

-- After:
-- expected: 2   (D-07 partial-or-full success)

SELECT enrichment_id FROM ingestions WHERE article_id = (
  SELECT id FROM articles WHERE url = 'https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA');
-- expected: 'enrich_8ac04218b4'
```

### 3.3 LightRAG state changes

```bash
# Doc records should show the enriched WeChat + Zhihu docs as PROCESSED (not FAILED)
python3 -c "import json; d=json.load(open('/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json')); new=[k for k,v in d.items() if '8ac04218b4' in k or '8ac04218b4' in v.get('file_path','')]; print('enrichment docs:', new)"
# expected: ['wechat:8ac04218b4', 'zhihu_8ac04218b4_0', 'zhihu_8ac04218b4_1', ...] all with status=processed

# Graph growth (baseline: 713 nodes, 820 edges)
grep -c '<node' /home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml
# expected: >= 713 + ~20-60 new entities
```

### 3.4 merge_and_ingest stdout JSON

The final line emitted by `merge_and_ingest` should be a single-line JSON per D-03:

```json
{"hash": "8ac04218b4", "status": "ok", "enriched": 2, "question_count": N, "success_count": N', "zhihu_docs_ingested": N'', "enrichment_id": "enrich_8ac04218b4"}
```

- `N` = total questions (1–3)
- `N'` = questions that produced any haowen.json (even if fetch_zhihu failed later)
- `N''` = questions whose Zhihu MD was actually ingested into LightRAG

### 3.5 Exit codes

- `extract_questions`: exit 0
- `zhihu-haowen-enrich` (Hermes skill): no exit code; success signaled by haowen.json
- `fetch_zhihu`: exit 0
- `merge_and_ingest`: exit 0

---

## 4. Acceptance criteria (fill these in after the run)

| # | Criterion | Pass / Fail | Notes |
|---|-----------|-------------|-------|
| 1 | `questions.json` created with 1–3 questions, each with `context` field | | |
| 2 | For each question, `<q_idx>/haowen.json` exists with a real `source_url` (not a stub) | | |
| 3 | Hermes agent correctly looped over N questions (no skipping, no double-counting) | | |
| 4 | D-13 Telegram fallback fired cleanly if login wall hit (or gracefully skipped if not) | | |
| 5 | Each `<q_idx>/final_content.md` exists and is non-empty | | |
| 6 | All `<100px` Zhihu decorative images correctly filtered out | | |
| 7 | `final_content.enriched.md` exists at the expected path with inline 好问 summaries | | |
| 8 | `merge_and_ingest` emitted D-03 JSON with `status: ok` and non-zero `success_count` | | |
| 9 | SQLite `articles.enriched = 2` for the article row | | |
| 10 | SQLite `ingestions.enrichment_id = "enrich_8ac04218b4"` | | |
| 11 | LightRAG graph grew by ≥1 doc (≥1 enrichment ID present) | | |
| 12 | LightRAG `kv_store_doc_status.json` shows no NEW `failed` entries tagged to this article | | |
| 13 | End-to-end runtime <10 minutes (excluding Telegram-fallback waits) | | |
| 14 | Exit codes 0 across all Python invocations | | |

---

## 5. Failure-mode playbook (to help classify if it fails)

| Observation | Likely cause | Next step |
|---|---|---|
| `extract_questions` raises 429 | Gemini burst quota | Wait 60s, retry |
| `zhihu-haowen-enrich` skill runs but returns no URL | CDP not running / Zhida layout change | Inspect `ss -ltn \| grep 9223`; screenshot zhida.zhihu.com |
| Skill invocation gets stuck on login wall with no Telegram message | D-13 fallback broken | Capture skill output; report as 04-05 defect |
| `fetch_zhihu` raises TimeoutError | CDP slow / target page heavy | Retry once; else report with timing info |
| `merge_and_ingest` emits `status: ok` but `enriched=0` in SQL | Migration not applied OR article row missing | Run `init_db` manually; check article row exists |
| LightRAG shows new docs in `failed` state | Gemini quota during entity extraction | Not a skill bug; retry ingest later when quota open |
| `final_content.enriched.md` exists but no inline 好问 summaries | merge_md bug (D-09 violation) | Capture before/after MD; report as 04-04 defect |

---

## 6. Clean-up after the test

If you want to restore the LightRAG to pre-test state (for repeatable testing):

```bash
cd ~/OmniGraph-Vault && set -a && source ~/.hermes/.env && set +a
venv/bin/python - <<'EOF'
import asyncio, sys, os
sys.path.insert(0, '/home/sztimhdd/OmniGraph-Vault')
os.chdir('/home/sztimhdd/OmniGraph-Vault')
from ingest_wechat import get_rag

async def cleanup():
    rag = await get_rag()
    for did in ['wechat:8ac04218b4', 'zhihu_8ac04218b4_0', 'zhihu_8ac04218b4_1', 'zhihu_8ac04218b4_2']:
        try:
            r = await rag.adelete_by_doc_id(did, delete_llm_cache=False)
            print(f'{did}: {r.status}')
        except Exception as e:
            print(f'{did}: ERROR {type(e).__name__}')

asyncio.run(cleanup())
EOF

# Also delete the enrichment artifacts
rm -rf ~/.hermes/omonigraph-vault/enrichment/8ac04218b4/

# And reset the enriched flag in SQLite
python3 -c "
import sqlite3
c = sqlite3.connect('/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db')
c.execute('UPDATE articles SET enriched = 0 WHERE url = ?', ('https://mp.weixin.qq.com/s/-1CQxvdc1bDMrPzIHFPpbA',))
c.commit()
print('articles row reset')
c.close()
"
```

---

## 7. Reporting template

After the run, reply to the orchestrator with a fill-in of section 4 above plus:

### What worked
(prose, 1–3 paragraphs)

### What failed or surprised you
(prose with concrete evidence — error messages, file paths, timing)

### Logs to share
- Hermes session transcript (copy-paste from terminal or attach file)
- Relevant stderr/stdout from the Python invocations
- `questions.json` contents
- `merge_and_ingest` final JSON line

### Recommendation
- [ ] Wave 4 passes — proceed to Wave 5 (04-07 ingest_wechat integration)
- [ ] Wave 4 has defects — list them with phase-plan target (e.g., "04-05: D-13 Telegram fallback hangs")
- [ ] Infrastructure blocked — list blockers (e.g., "CDP port 9223 not running")

---

*Generated by orchestrator at the end of Wave 4 execution. Once this test passes, we
proceed to Wave 5 (04-07 ingest_wechat integration).*
