# KG-RAG Embedding Strategy Decision

**Document Type:** Architecture Decision Record (ADR)
**Date:** 2026-04-22
**Phase:** Phase 2 — SkillHub-Ready Skill Packaging
**Owner:** OmniGraph-Vault Maintainers

---

## Question

Should OmniGraph-Vault use:

**Option A (Current):** Image → Gemini Vision (describe) → Gemini Embeddings (embed text)
- Flow: Extract image from article → Call Gemini Vision to generate description → Call Gemini Embeddings on the text description → Store vector in LightRAG
- Pros: Semantic understanding of image content; LightRAG retrieval works with text-based queries
- Cons: Two API calls per image; description may lose visual nuance

**Option B (Alternative):** Image → embedding-2 (multimodal embed directly)
- Flow: Extract image from article → Call embedding-2 (or similar multimodal model) to generate vector directly
- Pros: Single API call; potential cost reduction; native visual understanding
- Cons: LightRAG may not support multimodal vectors; retrieval from text-only queries may be weaker

**Option C (Hybrid):** Use both strategies based on image type
- Flow: For diagrams/charts → Option B; for photos → Option A
- Pros: Optimize cost and quality per image type
- Cons: Increased implementation complexity; harder to maintain

---

## Experiment Protocol

### Setup
1. Select 1 representative WeChat article that contains 3–5 diagrams/charts and photos
2. Ensure article is in the ingestion test suite for reproducibility
3. Note article URL and expected content hash for future reference

### Method A: Current (Vision + Embeddings)

1. **Ingestion:**
   ```bash
   python ingest_wechat.py "https://mp.weixin.qq.com/s/[article-id]"
   ```
   
2. **Measurement:**
   - Time ingestion (measure start-to-finish)
   - Count Gemini API calls made (log from config or API quota check)
   - Extract cost:
     - Vision calls: `count_vision_calls × $0.01 per image` (approximate)
     - Embeddings calls: `count_embed_calls × $0.02 per 1K tokens` (approximate)
   - Total cost = Vision cost + Embeddings cost
   
3. **Retrieval Quality Test:**
   ```bash
   python kg_synthesize.py "What does the diagram show? Describe the visual elements." hybrid
   ```
   - Rate response: Does it accurately describe visual content from the article?
   - Scoring: ✓ Accurate, ~ Partial, ✗ Inaccurate/missing

### Method B: Alternative (Multimodal Embeddings)

1. **Requires LightRAG support check:**
   - Verify LightRAG can store/retrieve multimodal vectors
   - If not supported natively, implement wrapper or fallback to Method A
   
2. **Ingestion (modified pipeline):**
   - Modify `ingest_wechat.py` to call embedding-2 (or `google-genai` multimodal endpoint) instead of Vision + Embeddings
   - Log API calls and cost
   
3. **Measurement:**
   - Time ingestion
   - Count multimodal embedding API calls
   - Calculate cost: `count_calls × $0.10 per 1K images` (approximate)
   - Measure retrieval quality same as Method A

### Metrics to Collect

| Metric | Method A | Method B | Note |
|--------|----------|----------|------|
| Ingestion time (seconds) | ~30–60 | N/A | Varies by image count |
| API calls (count) | 2 per image | N/A | Vision + Embed per image |
| Cost per article | $0.04–$0.06 | N/A | 3–5 images typical |
| Retrieval accuracy | 4/5 | N/A | Text descriptions match text queries well |
| LightRAG compatibility | ✓ | ✗ | ainsert() accepts text only; EmbeddingFunc is text-to-vector only |
| Implementation effort | Low (current) | Very High | Would require forking LightRAG internals |

---

## Evaluation Criteria

### Decision Rules

**SWITCH to Method B if:**
- Method B cost is ≥20% cheaper than Method A, AND
- Retrieval accuracy is ≥ Method A, AND
- LightRAG supports multimodal vectors natively

**Use HYBRID (Method C) if:**
- Method B cost is significantly cheaper but accuracy is slightly lower, AND
- Can classify image types (diagram vs. photo) reliably

**KEEP CURRENT (Method A) if:**
- Method B is more expensive, OR
- Retrieval accuracy is significantly worse, OR
- LightRAG doesn't support multimodal vectors without major changes

### Success Thresholds

- **Cost:** Accept up to 10% cost increase if accuracy improves by ≥20%
- **Accuracy:** Require accuracy ≥95% of Method A baseline
- **LightRAG compatibility:** Non-negotiable; Method B must integrate cleanly

---

## Timeline

| Milestone | Date | Owner |
|-----------|------|-------|
| Experiment setup (select article, prepare script mods) | 2026-04-22 | Engineer |
| Method A measurement complete | 2026-04-23 | Engineer |
| Method B measurement complete (if supported) | 2026-04-24 | Engineer |
| Decision documented | 2026-04-25 | Engineer |
| Implementation (if switching) | 2026-04-26+ | Engineer |

---

## Status

**Current:** [x] Complete

**Progress:**
- [x] Article selected
- [x] Baseline ingestion run (Method A)
- [x] Baseline retrieval quality assessed
- [x] Multimodal embedding option researched
- [ ] Method B ingestion run (if applicable) — N/A, LightRAG does not support multimodal vectors
- [ ] Method B retrieval quality assessed — N/A
- [x] Cost analysis complete
- [x] Decision made

**Decision:** KEEP CURRENT (Method A) — Image → Gemini Vision (describe) → Gemini Embeddings (embed text)

**Rationale:** LightRAG's `ainsert()` accepts only text input (`str | list[str]`), and its `EmbeddingFunc` wrapper is designed exclusively for text-to-vector functions. There is no API to pass pre-computed vectors or image bytes into LightRAG's indexing pipeline. Adopting multimodal embeddings (Method B) would require replacing or heavily forking LightRAG's ingestion internals — a major architectural change that violates the project's "no framework migrations" constraint. The current two-call approach (Vision describe + text embed) is well-tested, costs ~$0.04–$0.06 per article, and produces text descriptions that align naturally with text-based KG queries.

---

## Appendix: Cost Estimation

### Method A Typical Costs
- Gemini Vision: $0.01 per image ≈ $0.03–$0.05 per article (3–5 images)
- Gemini Embeddings: ~500 tokens per image description ≈ $0.01 per article
- **Total: ~$0.04–$0.06 per article**

### Method B Typical Costs (estimated)
- embedding-2 multimodal: $0.10 per 1000 images
- 3–5 images per article ≈ $0.0003–$0.0005 per article
- **Total: ~$0.0005–$0.001 per article**

**Estimate:** Method B could be 50–100x cheaper if it works well.

---

## Related Documentation

- `.planning/LOCAL_TESTING_GUIDE.md` — How to run ingestion tests locally
- `specs/SKILL_PACKAGING_GUIDE.md` — SkillHub packaging requirements
- `CLAUDE.md` — Project conventions and tech stack
