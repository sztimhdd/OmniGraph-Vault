# Graded probe prompt rewrite — 2026-05-05

## Background

Hermes overnight (2026-05-05 ~01:35 ADT) flagged severe false-negatives from
the freshly-shipped graded MVP (commit `e833206` + migration 003):

- "RAG systems"               → wrongly skipped
- "multi-agent orchestration" → wrongly skipped
- "AI agents"                 → wrongly skipped

The model interpreted "agent" word-literally (treating it as a single
keyword) and missed the entire RAG / multi-agent / agentic-reasoning
ecosystem the cron is designed to ingest.

## Diagnosis

Two separate problems compounded:

1. **Routing**: `_graded_probe` hardcoded DeepSeek HTTP. On the local
   Cisco-proxied Windows dev box DeepSeek is unreachable
   (`SEC_E_ILLEGAL_MESSAGE` / `SSLV3_ALERT_HANDSHAKE_FAILURE` on direct
   curl, not just Python), so prompt iteration could only happen on
   Hermes — the very environment the bug was discovered in.

2. **Prompt**: the prompt asked the model "is this OBVIOUSLY unrelated
   to ALL of [agent, openclaw, hermes, harness]?" and let the model
   define "agent" however it wanted. Both DeepSeek (production) and
   Vertex Gemini (local) interpreted it narrowly enough to skip
   GraphRAG / multi-agent / autonomous-research articles.

Routing is fixed in commit 1 (provider switch via
`OMNIGRAPH_LLM_PROVIDER`). This document covers commit 2: the prompt
rewrite.

## Prompt design — path B (conservative reject-list)

Instead of asking the model to decide what counts as agent, we now hand
it an explicit reject-list of off-topic domains and tell it that ANY
mention of agent / RAG / tool-use / autonomous-reasoning vocab flips the
answer back to `unrelated=false` (let full classify decide). Ambiguous
cases also fail open.

This trades some false-positives for **zero false-negatives** — a
deliberate recall-over-precision choice given that a missed agent
article costs much more than an extra scrape.

Full prompt body in `batch_ingest_from_spider._graded_probe_prompts`.

## Validation

### Fixture test — `tests/unit/test_graded_classify_prompt_quality.py`

15-sample fixture with real Vertex Gemini calls (no mocks):

- 9 RELATED (agent / RAG / multi-agent / autonomous / OpenClaw / coding-agent / ReAct / agent-memory / multi-agent)
- 4 OFF-TOPIC (CV survey, edge CV, hardware, image generation)
- 2 AMBIGUOUS (LLM release, training-data quality)

| | iteration 1 result |
|---|---|
| false-negatives (HARD gate, must = 0) | **0 / 9** |
| false-positives (soft gate, < 30%) | **0 / 4** (0%) |
| ambiguous correctly passed through | **2 / 2** |

The same fixture run against the *unchanged* prompt reproduced the bug
locally on Vertex (`graph-rag` → `unrelated=True conf=0.95 reason='Topic
is about RAG frameworks, not specified terms.'`), confirming this is a
prompt-level bug not a provider-level one.

### Real-DB spot-check — 30 random articles from `kol_scan.db`

Skip rate: **3 / 30 (10%)**. All 3 skips genuinely off-topic:

| skip | reason |
|------|--------|
| "Python标准库里藏着的7个代码简化利器" | Pure Python stdlib utilities, no AI |
| "TPAMI 2025 BIPNet 框架" | Pure CV image restoration research |
| "三年连下三癌，阿里AI跑通了多癌筛查" | Pure medical AI screening |

All 27 PASSes were either explicit agent-ecosystem content or borderline
topics (CVPR survey mentioning agentic paradigm, business commentary on
LLM companies) where the conservative bias correctly let them through to
full classify.

## Caveats — Hermes spot-check after pull

The prompt was tuned against **Vertex Gemini**
(`gemini-3.1-flash-lite-preview`). Production Hermes uses **DeepSeek
chat**. Both providers reproduced the original bug under the old
prompt, which suggests the fix transfers — but DeepSeek may behave
slightly differently on edge cases.

Hermes-side validation after `git pull`:

```bash
# Pick 5-10 articles from the last 24h that the cron actually saw
sqlite3 ~/.hermes/data/kol_scan.db "
  SELECT a.title, a.digest FROM articles a
  WHERE a.created_at > datetime('now','-24 hours') ORDER BY RANDOM() LIMIT 10
"

# Run them through the probe and eyeball
OMNIGRAPH_LLM_PROVIDER=deepseek venv/bin/python -m pytest \
  tests/unit/test_graded_classify_prompt_quality.py -v -s
```

If DeepSeek shows new false-negatives the fixture didn't catch, add the
failing case to `SAMPLES` in the test file and iterate again.

## Out of scope

- Threshold (kept at 0.9 confidence)
- Short-digest guard (kept at < 10 chars early-return)
- `_classify_full_body` and the rest of the pipeline (untouched)
- `OMNIGRAPH_GRADED_CLASSIFY` feature flag (still default OFF; cron sets `=1`)
