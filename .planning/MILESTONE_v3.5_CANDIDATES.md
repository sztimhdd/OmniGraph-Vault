# Milestone v3.5 — Parked Candidates

> Research material only. **Does NOT enter ROADMAP "Next" until a milestone
> charter is opened.** Three pre-baked design streams that crystallized during
> v3.4 hardening (2026-05-03 → 2026-05-06) but were intentionally deferred to
> keep v3.4 scope tight. Pull from here when starting `/gsd:new-milestone v3.5`.

Created: 2026-05-06 (quick 260506-se5)
Last updated: 2026-05-06

---

## Section 1 — Ingest Pipeline Simplification

**Hypothesis (NOT validated):** the current 4-LLM-gate + 1-paid-API + multi-SQL
pipeline is over-decoupled for the actual workload. A 4-stage redesign could
trim **25-40% per-article cost** and remove 4 of the 6 fragility points enumerated
below. Estimate is a researcher's back-of-envelope, not measured — flag for
spike before any commitment.

### Current architecture inventory

LLM gates per article (4):
1. **Graded probe** (`OMNIGRAPH_GRADED_CLASSIFY=1`) — DeepSeek title+digest probe before scrape; saves Apify cost on obvious rejects but introduces latency+probability of false-negative (cf 2026-05-06 `_classify_full_body` topic_filter regression in quick 260506-en4).
2. **Full-body classify** (`_classify_full_body` in `batch_ingest_from_spider.py`) — single LLM call after scrape, writes `classifications` row.
3. **Entity extract** (`extract_entities` in `ingest_wechat.py`, on the LightRAG ainsert path) — independent LLM call, output buffered to `entity_buffer/`.
4. **Cognee remember** (`cognee_wrapper.remember_article`, currently behind `OMNIGRAPH_COGNEE_INLINE` since 2026-05-04) — async LLM call for memory-layer storage; gated off in production after the LiteLLM→AI-Studio routing 422 loop.

Paid API (1):
- **Apify WeChat scraper** — 75-90s wall-clock per article on success path; `~$0.001-0.005` per call.

SQL state writes per article (4 tables):
- `articles.body` (atomically written post-scrape since quick 260505-m9e)
- `classifications` (one INSERT, post-classify; UPSERT post-quick 260506-se5)
- `ingestions` (one row per terminal outcome — ok/failed/skipped/skipped_ingested/skipped_graded/dry_run)
- `checkpoints/{hash}/` filesystem markers (5 ordered stages)

Per-image side pipeline:
- **Vision cascade** (3 providers + circuit breaker — SiliconFlow → OpenRouter → Gemini)
- **Image download → local persist → vision describe** all happen once per image

### Per-article cost table

| Path | Wall-clock | Apify | LLM (DeepSeek/Vertex) | Vision | Notes |
|------|-----------|-------|----------------------|--------|-------|
| Success (avg ~10 images) | 4-6 min | ¥0.005 | ~¥0.10 | ~¥0.013 | dominant cost: vision |
| Graded reject (filter out before scrape) | <30s | ¥0 | ~¥0.001 | ¥0 | best case |
| Scrape-then-filter reject | 80-120s | ¥0.005 | ~¥0.001 | ¥0 | **irreducible Apify waste** (CLAUDE.md Lessons 2026-05-05 #2) |
| Multi-page article (sub-page expansion) | 10-28 min | ¥0.005-0.025 | ~¥0.10-0.50 | scales with images | each `idx=N` is its own scrape |

Cost estimate per 1000 successful articles: **~$0.15-0.50/article success path**, **$0.01-0.05/article paid-then-rejected path**.

### 6 fragility points

1. **Async-drain D-10.09 hang** — root cause never identified. Currently soft-mitigated via 120s drain cap in vision worker (`scripts/bench_ingest_fixture.py` Phase 11 wiring). Reproduces under image-heavy articles when an upstream Vision provider stalls. Cited in STATE.md "Phase 5 Exit State" deferred items.

2. **Embed worker (60s) vs LLM (1800s) timeout asymmetry** (CLAUDE.md Lessons 2026-05-05 #5). Track 3 Hermes-B flagged: when `OMNIGRAPH_LLM_TIMEOUT_SEC` bumped 600→1800 for image-heavy articles, embedding worker still has 60s timeout. 30× ratio is a hidden ceiling — currently doesn't bite, but as graph grows or vision providers slow down, will surface.

3. **WHERE-clause hot-keying — `articles.body=NULL` excluded if scrape failed but ingest retried.** Pre-quick 260505-m9e, scrape success that lost downstream (classify or LightRAG ingest failed) discarded the body in memory. Fixed in `239f4a0` (atomic body persist). Future fragility: if any new code path forgets to write body before failure, regression returns silently.

4. **Image cascade circuit breaker false-positive on 4xx auth.** Per CLAUDE.md "Vision Cascade" section: 4xx auth errors should NOT count toward circuit breaker (auth fix is operator action, not auto-fallback target). Current implementation is documented as such but no test enforces — a regression would silently route auth-misconfigured SiliconFlow into "circuit open" and exhaust Gemini quota.

5. **`skip_reason_version` absent — permanent vs transient rejects indistinguishable** (CLAUDE.md Lessons 2026-05-05 #6). DB candidate SELECT does NOT exclude `status='skipped'` — articles previously rejected for any reason are naturally re-pulled. Useful for transient-bug auto-recovery; risky for permanent dead URLs that retry daily forever. Need a `skip_reason_version` column on `ingestions` so retries can decide based on reason cohort.

6. **Cognee inline gate behind `OMNIGRAPH_COGNEE_INLINE` env var since 2026-05-04** (CLAUDE.md env-vars table). LiteLLM → AI-Studio routing bug with Vertex-exclusive `gemini-embedding-2` (422 NOT_FOUND → retry loop blocks ingest). Gated off pending root fix. Either remove the inline call entirely (move all Cognee work to `cognee_batch_processor.py` async path) or fix the routing.

### Idealized 4-stage flow

A v3.5 redesign hypothesis — surgical simplification keeping the data flow but
collapsing the LLM gate count from 4 → 2:

```
SCAN     | cheap, no LLM | RSS/KOL fetch + dedup hash + write articles.* row
SCRAPE   | paid Apify    | scrape + atomic write articles.body (write before any
         |               | downstream decision; idempotent)
CLASSIFY | 1 LLM call    | full-body, multi-topic single response, write all
         |               | topics in one classifications row (UPSERT post-260506-se5)
INGEST   | 1 LLM call    | LightRAG ainsert (entity extract happens inside LightRAG;
         |               | decoupled from classify; image vision is a side-thread)
```

What changes vs current:
- **Drop graded probe** — accept the irreducible Apify cost on filter rejects; the cost is dominated by vision-on-success not Apify-on-reject anyway. Or: keep graded probe as a `--cheap-mode` opt-in flag rather than the default.
- **Move entity extract inside LightRAG** — already happens internally, but currently `ingest_wechat.extract_entities` is a separate pre-ingest call buffering to `entity_buffer/`. Removing this buffer + relying on LightRAG's own pipeline would simplify state.
- **Resolve Cognee inline disablement** — either fix LiteLLM routing OR commit to the async-only `cognee_batch_processor.py` path and delete the inline code.

Estimated impact: 25-40% cost reduction (mostly from removed redundant LLM
calls + dropped buffer state). **NOT measured** — design hypothesis only.

---

## Section 2 — Operational Hardening

Four sub-items already documented in CLAUDE.md / memory; collated here so v3.5
charter can pull them as a single track.

1. **Hermes agent cron → systemd timer migration** (memory file: `~/.claude/projects/.../memory/hermes_agent_cron_timeout.md`).
   Current band-aid: `HERMES_CRON_TIMEOUT=28800` env var bumps the activity-based inactivity timeout from 600s → 8h. Long-term fix: bypass Hermes agent entirely for ingest — register a systemd timer + service unit on the Hermes box. Reproduces Day-1 cron failure 2026-05-04 (Hermes agent SIGTERM'd `batch_ingest_from_spider.py` at 600s of zero-stdout activity during Apify wait). Tracks 1 v3.4-deferred + 1 v3.5 candidate together.

2. **60s embed vs 1800s LLM timeout asymmetry** — embed worker timeout has not been bumped proportionally. Currently doesn't bite, but as graph grows or vision providers get slower, the 30× ratio becomes a hidden ceiling. CLAUDE.md Lessons 2026-05-05 #5. Fix: introduce `OMNIGRAPH_EMBED_TIMEOUT_SEC` and scale proportionally with `OMNIGRAPH_LLM_TIMEOUT_SEC` (or share the same env var with a separate ratio multiplier).

3. **Reject-reason versioning** (CLAUDE.md Lessons 2026-05-05 #6). Add `skip_reason_version` column to `ingestions` so retry policy can distinguish permanent (URL gone) from transient (rate limit) rejects. Bumps schema migration count by 1; backfill existing rows with `skip_reason_version=0` (= legacy).

4. **Async-drain D-10.09 hang** — root cause never identified; currently soft-mitigated via 120s drain cap in vision worker. STATE.md/CLAUDE.md mention this as architectural / known issue. v3.5 spike: instrument the drain path with explicit `asyncio.gather(return_exceptions=True)` + per-task timing logs to localize which subtask hangs. Likely interaction with image download retry × Gemini Vision 500 RPD ceiling × circuit-breaker false-positive — the diagnosis spike should run before redesign decisions.

---

## Section 3 — Agentic-RAG-v1 Post-Launch Enhancements

Placeholder. The Agentic-RAG-v1 milestone (10 reqs + 10 axes locked at
`docs/design/agentic_rag_internal_api.md`, design converged 2026-05-06) is
about to ship via `/gsd:new-milestone`. Post-launch enhancements should be
captured here as real usage data accumulates — DO NOT pre-spec.

References:
- `docs/design/agentic_rag_internal_api.md` (locked design)
- Memory file `~/.claude/projects/.../memory/project_agentic_rag_design_in_progress.md`
- KG-side cross-milestone contract (PROJECT.md): `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` must stay stable.

Known candidates to track (from design discussion, not yet proven needed):
- Multi-turn query state (carry-over across follow-up questions)
- Result re-ranking with Cognee memory context
- Streaming partial answers vs current batch synthesis
- Telemetry: per-query mode breakdown + retrieval-set size distribution

Defer triage until ≥ 2 weeks of real Agentic-RAG-v1 production usage.

---

这是 v3.5 candidates 研究素材,不是 milestone plan;不进 ROADMAP "Next" 段。
