---
name: enrich_article
description: |
  Use this skill to enrich a WeChat article with 知乎 好问 AI-search insights
  BEFORE ingesting it into the OmniGraph-Vault knowledge graph. Trigger phrases
  include: "enrich this article", "do the full knowledge enrichment pass",
  "add this article with Zhihu enrichment".

  This skill orchestrates the complete per-article enrichment pipeline:

    1. Extract 1–3 under-documented questions from the article (Python helper
       `enrichment/extract_questions.py`, Gemini + Google Search grounding).
    2. For EACH question, invoke the `/zhihu-haowen-enrich` child skill to
       drive zhida.zhihu.com and get the AI summary + best-cited Zhihu URL.
    3. For EACH successful 好问 result, shell to `enrichment/fetch_zhihu.py`
       to fetch the full Zhihu answer (markdown + images).
    4. Shell to `enrichment/merge_and_ingest.py` to merge artifacts, ingest
       into LightRAG with D-08 metadata, and update SQLite status.

  Total runtime: up to ~10 minutes per article (3 questions × 180s + overhead).

  Do NOT use this skill when:
  - The user just wants un-enriched ingest (no Zhihu step) — call
    `omnigraph_ingest` directly instead. Note: per D-07 (Phase 4 policy),
    enrichment is the DEFAULT path for production ingest. Direct
    `omnigraph_ingest` without this skill is a debug-only escape hatch.
  - The article is < 2000 chars (the extract-questions helper will return
    `skipped` and no 好问 calls will happen; this skill still completes
    cleanly and calls merge_and_ingest with empty haowen_list — enriched=-1
    or regular ingest path handled by the outer caller)
  - The article has already been enriched (articles.enriched = 2) — idempotency
    is handled by the caller, not this skill
compatibility: |
  Requires: GEMINI_API_KEY, Python venv at $OMNIGRAPH_ROOT/venv, CDP-reachable
  Edge at $CDP_URL (for child skill), Hermes `send_message` tool (for login-wall
  recovery), Python helpers under enrichment/ package.
metadata:
  openclaw:
    os: ["linux", "darwin"]
    requires:
      bins: ["python", "bash"]
      config: ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "CDP_URL"]
---

# enrich_article

**Purpose**: End-to-end Zhihu-enriched ingest of ONE WeChat article.

## Inputs

| Variable | Required | Source |
|----------|----------|--------|
| `ARTICLE_PATH` | yes | Local path to the scraped WeChat MD file (typically `~/.hermes/omonigraph-vault/images/<hash>/final_content.md`) |
| `ARTICLE_URL` | yes | Original WeChat URL (used for SQLite updates) |
| `ARTICLE_HASH` | optional | md5[:10] of article bytes; derived automatically if omitted |
| `ENRICHMENT_DIR` | optional | Defaults to `~/.hermes/omonigraph-vault/enrichment` |

## Decision Tree

### Step 1 — Extract questions

Shell:

```bash
cd $OMNIGRAPH_ROOT
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate
python -m enrichment.extract_questions "$ARTICLE_PATH" --hash "$ARTICLE_HASH"
```

The helper prints a single-line JSON to stdout. Parse the JSON.

#### Branch — `status == "skipped"` (article too short)

The article is under the `ENRICHMENT_MIN_LENGTH` threshold (default 2000 chars).
Skip directly to **Step 4: Merge & ingest** (with `success_count=0`; merge_and_ingest
will handle the empty-haowen path). No questions to ask — no child-skill calls.

Do NOT mark as failure. The outer caller (e.g., ingest_wechat.py) decides whether
this article gets `enriched=-1` or passes through a regular ingest.

#### Branch — `status == "error"`

Report the error to the user and HALT. Do NOT proceed to Step 4 (no questions.json
to merge from). This protects the SQLite state — article stays `enriched=0`
(pending) and is eligible for retry.

Response format: "⚠️ Question extraction failed: <error>. Article unchanged. Retry
after fix."

#### Branch — `status == "ok"`

The output `artifact` path points to `$ENRICHMENT_DIR/$ARTICLE_HASH/questions.json`.

Read the file. Extract the `questions` array (list of `{question, context}` dicts).
Note the length N (will be 1–3).

### Step 2 — Per-question 好问 + Zhihu fetch (FOR LOOP)

For each question Q at index Q_IDX in `0..N-1`:

#### 2a — Invoke `/zhihu-haowen-enrich` child skill

Invoke the child skill, passing the question text and context via environment:

- Set `ARTICLE_HASH = $ARTICLE_HASH`
- Set `Q_IDX = <current index>`
- Set `QUESTION = <question text>`

Then execute `/zhihu-haowen-enrich`.

After the child skill returns, read the file
`$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/haowen.json`:

- If file contains `{question, summary, best_source_url, timestamp}` →
  success for this question. Continue to 2b.
- If file contains `{question, error, timestamp}` → this question failed.
  SKIP 2b for this index; move on to the next question. Log: "⚠️ /zhihu-haowen-enrich
  error for q_idx=<N>: <error value from haowen.json>."
- If file is missing entirely → treat as failure. Log: "⚠️ /zhihu-haowen-enrich
  produced no output for q_idx=<N>." Continue to next question.

#### 2b — Fetch the Zhihu source article (only if 2a succeeded)

Shell:

```bash
python -m enrichment.fetch_zhihu "$BEST_SOURCE_URL" \
  --hash "$ARTICLE_HASH" --q-idx "$Q_IDX"
```

where `$BEST_SOURCE_URL` is the value from the haowen.json `best_source_url` field.

Parse the single-line JSON stdout:

- `status == "ok"` → great, Zhihu MD is on disk at `md_path`. Continue loop.
- `status == "error"` → log the error to stderr, continue loop. The question
  still counts as partial-success for merge (summary was captured, just the
  deep-fetch failed).

**Loop iteration budget**: the outer agent has `max_turns=90`. Each iteration
consumes ~15–20 turns. Budget: 3 × 20 = 60 turns for the loop, leaving margin
for steps 1, 3, and 4.

### Step 3 — (no-op — all per-question work done in step 2)

### Step 4 — Merge & ingest

Shell:

```bash
python -m enrichment.merge_and_ingest "$ARTICLE_HASH" \
  --article-path "$ARTICLE_PATH" \
  --article-url "$ARTICLE_URL"
```

Parse the single-line JSON stdout:

- `status == "ok"` with `enriched == 2` → full or partial success. Report to
  user: "Article enriched with <success_count>/<question_count> questions.
  Ingested to LightRAG as 1 enriched WeChat doc + <zhihu_docs_ingested> Zhihu
  child docs."
- `status == "ok"` with `enriched == -2` → all questions failed but the
  un-enriched WeChat MD was ingested. Report: "Article ingested without
  enrichment (all 3 Zhihu searches failed). SQLite status: enriched=-2;
  re-enrichable later."
- `status == "error"` → CRITICAL: ingestion failed. Report the error to the
  user, recommend inspecting `$ENRICHMENT_DIR/$ARTICLE_HASH/` for artifacts
  and `~/.hermes/omonigraph-vault/lightrag_storage/` for state.

## Error Handling Summary

| At step | Error | User-facing response |
|---------|-------|----------------------|
| 1 | `extract_questions` error | "⚠️ Question extraction failed: <error>. Article unchanged. Retry after fix." |
| 1 | `extract_questions` skipped | "ℹ️ Article too short (<2000 chars); proceeding to un-enriched ingest." → Step 4 |
| 2a | child skill error (haowen.json has error field) | silent log — question abandoned, loop continues |
| 2a | child skill didn't produce file | "⚠️ /zhihu-haowen-enrich produced no output for q_idx=<N>." — loop continues |
| 2b | `fetch_zhihu` error | silent log — question still partial-success, loop continues |
| 4 | `merge_and_ingest` error | "⚠️ Ingest failed: <error>. Inspect enrichment dir. SQLite: article remains enriched=0 (pending). Eligible for retry." |

## Output Format (Success)

```
Starting enrichment — up to 10 minutes for 3 questions...
Extracted N questions from article.
Question 1: <text> ... ✓ haowen found, ✓ Zhihu fetched
Question 2: <text> ... ✗ 好问 timeout, skipped
Question 3: <text> ... ✓ haowen found, ✓ Zhihu fetched
Merging and ingesting...
✅ Article enriched (2/3 questions). LightRAG: 1 WeChat + 2 Zhihu docs. enriched=2.
```

## Privacy Note

All artifacts stored locally under `$ENRICHMENT_DIR`. External API calls:
Gemini (question extraction + image vision), Zhihu (content fetch only, no
auth data leaves the machine), Telegram bot (QR image only, if login-wall fires).

## Related Skills

- Child: `/zhihu-haowen-enrich` (invoked N times inside Step 2a)
- Alternative: `omnigraph_ingest` — un-enriched ingest (debug-only per D-07)
- Follow-on: `omnigraph_query` — query the enriched graph

## References

For additional flow notes, selector strategies, and per-run observations,
see `references/pipeline-notes.md`.
