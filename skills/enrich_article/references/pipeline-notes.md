# enrich_article Pipeline Notes

Level-2 reference document for the `enrich_article` skill.
Update after each real invocation to capture observed behavior.

## Turn budget observations

Target budget per full article: ~60 turns (3 questions × 20 turns each).
Update this table after real runs:

```
Date:
Article hash:
Questions extracted: N
Turns used per question: [q0: X, q1: Y, q2: Z]
Total turns: N
Notes:
```

## Step 1 — extract_questions observations

- Typical latency on remote (Gemini Flash Lite + grounding): ~5–10s
- Articles around 2000 chars boundary: verified `status=skipped` path fires correctly

## Step 2 for-loop observations

Update after each run. Track which questions succeed/fail and why.

## Step 4 — merge_and_ingest observations

- Typical LightRAG ainsert latency for one enriched WeChat doc: TBD
- Zhihu child doc ainsert per doc: TBD
