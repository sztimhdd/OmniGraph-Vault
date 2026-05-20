---
plan: llm-wiki-02-entity-content
task: 3
generated: 2026-05-20
approved: yes
approved_by: Hai
approved_at: 2026-05-20 morning (after cleanup discussion)
selection_count: 14
---

# W1 Task 3 Cost Estimate

## Selection (14 entities, locked 2026-05-20)

| Tier | Entities |
|------|----------|
| Tier 1 (6) | Hermes · OpenClaw · Superpowers · Agent · Harness · Claude Code |
| Tier 2 (7) | Skills · Context Engineering · Anthropic · Memory System · SOUL.md · Gateway · LangChain |
| Tier 3 (1) | MemoryProvider |

**Source:** `.scratch/llm-wiki-50-candidates-260519-cleaned.md` after 4-entity drop (Mem0/Codex/Karpathy/A2A — all <2 chunks in corpus per Decision D citation contract). MCP also dropped per user `C 不加`.

**Scope deviation from plan:** plan-02 spec says 20 pages; user picked 14 after corpus-thinness audit. Lower count is per-decision, not under-delivery.

## Cost estimate (Vertex AI Gemini 2.5 Flash, conservative)

| Stage | Per-entity | × 14 |
|-------|-----------|------|
| LightRAG hybrid aquery (embedding query + vector top-K + graph traverse) | ~5K input tok @ embedding + ~20K tok LLM context | $0.005 |
| LLM synthesis (long-form prompt → wiki page markdown) | ~25K input + ~3K output | $0.003 |
| Validation retries (assume 0.3 retries avg per entity) | ~30% × per-entity cost | +$0.002 |
| **Per-entity total** | | **~$0.010** |
| **14 × per-entity** | | **~$0.14** |

**Conservative upper bound** (worst case all retries trigger 2x, switching to Vertex Gemini 2.5 Pro mid-run if Flash fails): ~$0.50.

DeepSeek path (cheaper) would be ~$0.05 total but Vertex is the configured default per `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` for local dev.

## Hard cap monitor

Hard Constraint #8 ($5 USD cumulative cap across run) is far above this estimate. If actual spend exceeds **$1**, stop and re-prompt user (overshoot safety margin).

## Wallclock estimate

| Stage | Per-entity | × 14 |
|-------|-----------|------|
| aquery hybrid mode | ~10-20s | ~3-5 min |
| LLM synthesis | ~10-30s | ~3-7 min |
| Validation + retries | ~5s | ~1 min |
| **Total wallclock** | | **~7-15 min** |

## Failure modes anticipated

1. **Citation regex 0 matches in output** — long-form bug fix (commit 1683a58) is supposed to ensure correct citation format; if it slips, LLM may emit `[Entity: X]` instead of `^[article:<hash>]`. Mitigation: explicit citation directive in custom_prompt; up to 2 retries; skip-with-log if still failing.
2. **Citations don't resolve to real article hashes** — LLM may hallucinate hashes. Mitigation: post-generation validation against SQLite `articles.content_hash`; any hallucinated hash → retry with stricter prompt or skip.
3. **Empty/sparse aquery response** — for entities like Skills (3-way alias merge), hybrid mode may not surface all related content. Mitigation: trust LLM to consolidate from canonical-name aquery; document degraded pages with `confidence_level: low` in frontmatter.
4. **OpenClaw regenerated, lost hand-written 5763-char Hermes version** — user explicitly approved regeneration ("原来版本也没有充分利用我们已经超级丰富的 LightRAG 知识库"). Hand-written version remains on Hermes if needed for future merge.

## Approval

Approved by Hai 2026-05-20 morning via terse session decisions:
- "A 18 / B 剔除 / C 不加" (filter contract)
- "不需要 就14个" (final count: 14)
- "重写吧 本来原来版本也没有充分利用我们已经超级丰富的LightRAG知识库" (OpenClaw regenerate OK)

`approved: yes` set in this file's frontmatter — `scripts/wiki_generate_pages.py` reads it as cost-gate prerequisite per llm-wiki-02-entity-content-PLAN.md Task 3 step 1.
