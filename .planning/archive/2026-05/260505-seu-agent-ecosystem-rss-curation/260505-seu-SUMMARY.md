---
quick_id: 260505-seu
title: Agent ecosystem RSS curation — replace Karpathy 92 with 78 VitaClaw-relevant feeds (omg:* attrs)
status: complete
date: 2026-05-05
commit: 5e5465b
files_modified: 5
files_added: 3
---

# Quick Task 260505-seu Summary

## One-liner

Replaced the planned `data/karpathy_hn_2025.opml` (92 generic HN-blog feeds) with curated `data/agent_ecosystem_2026.opml` (78 VitaClaw-relevant feeds with `omg:dimension`/`omg:priority`/`omg:source_type` custom-namespace attributes), and surgically updated 3 Phase 5 plans (05-01/05-03/05-05) to consume the new schema. Phase 5 still waits for execute-gate lift; nothing executed in this task.

## OPML metrics

- **Total leaf feeds:** 78 (within 60-80 target band)
- **All 3 omg:* attrs populated on every leaf:** verified via `xml.etree.ElementTree` parse
- **Zero Twitter/X URLs:** verified via grep

### Distribution across 7 dimensions

| Dimension     | Count |
| ------------- | ----- |
| architecture  |     6 |
| framework     |    11 |
| idea          |    23 |
| library       |    11 |
| project       |     8 |
| skill         |     3 |
| tool          |    16 |

All 7 dimensions represented (≥5 required → exceeded).

### Distribution across source_type

| source_type        | Count |
| ------------------ | ----- |
| github_release     |    57 |
| official_eng_blog  |     8 |
| curated_blog       |    13 |

Both required minimums met (≥20 github_release ✓, ≥5 official_eng_blog ✓).

### Distribution across priority

| Priority   | Count |
| ---------- | ----- |
| core       |    48 |
| peripheral |    30 |

## User-mandated repos

| User mandate  | Status     | Notes |
| ------------- | ---------- | ----- |
| openclaw      | INCLUDED   | Resolved to `openclaw/openclaw` (368637 stars, "Your own personal AI assistant"). User-named override — cap-exempt anyway given star count. |
| vitaclaw      | INCLUDED   | Resolved to `vitaclaw/vitaclaw` (16 stars). Below 1000-star threshold; included as user-mandated override per plan rules. Documented in README "Known blind spots". |
| hermes        | OMITTED    | No canonical public repo found at `hermes-agent/hermes-agent`, `hermes-agent/hermes`, `hermes/hermes-agent` — likely closed-source/distributed privately. Documented in README. |
| gsd           | OMITTED    | Multiple unrelated repos use this name (`nteract/gsd` 404'd; common gamedev shorthand). No canonical match for the GSD workflow tool. Documented in README. |
| MerkleTree    | OMITTED    | Generic data-structure name. `merkletreejs/merkletreejs` (1236 stars) exists but is unrelated to agent ecosystem. Documented in README. |

## Considered but rejected sources

Star-cap rejections (≥1000 stars required, not user-mandated):

| Repo                                       | Stars | Reason                                      |
| ------------------------------------------ | ----- | ------------------------------------------- |
| lmstudio-ai/lmstudio-python                |   804 | Below 1000-star threshold                   |
| apify/apify-client-python                  |    92 | Below 1000-star threshold                   |
| pinecone-io/pinecone-python-client         |   436 | Below 1000-star threshold                   |
| run-llama/multi-agent-concierge            |   445 | Below 1000-star threshold                   |
| nirw4nna/dsc                               |   118 | Below 1000-star threshold                   |
| BCG-X-Official/agentkit                    |  1944 | Marginal stars; lower signal density        |
| allenai/scispacy                           |  1950 | Off-scope (biomedical NLP, not agents)      |
| OffchainLabs/go-ethereum                   |    77 | Off-scope (blockchain)                      |

404 / not found:

| Probed                                     | Result | Notes                                       |
| ------------------------------------------ | ------ | ------------------------------------------- |
| openai/agents-python                       | 404    | Not the canonical name                      |
| dench-ai/openclaw                          | 404    | Wrong owner (real owner: `openclaw/openclaw`) |
| nteract/gsd                                | 404    | Confirmed user mandate not resolvable here   |
| run-llama/llama-deploy                     | 404    | Likely renamed/archived                      |
| google/genai                               | 404    | SDK not under that path                      |
| context-labs/autoarena                     | 404    | Not found                                    |
| trycua/trycua                              | 404    | Use `trycua/cua` instead (15663 stars)       |

Cap-trim drops (initial pool was 92; trimmed to stay under 80-cap):

- `Cinnamon/kotaemon` (25362) — peripheral KG-RAG project
- `geekan/MetaGPT` (67704) — peripheral framework (similar coverage to autogen/crewAI)
- `camel-ai/camel` (16874) — peripheral framework
- `trycua/cua` (15663) — peripheral browser-automation
- `sgl-project/sglang` (27072) — peripheral serving (vllm covers this dimension)
- `ggml-org/llama.cpp` (108448) — peripheral serving
- `qdrant/qdrant` (31048) — peripheral vector store
- `Arize-ai/phoenix` (9531) — peripheral observability
- `comet-ml/opik` (19215) — peripheral observability

These repos all pass the 1000-star bar and could be re-added later if Phase 5 readers find dimension coverage thin in those categories.

Karpathy 92 → 13 cut: ~79 generic programming/lifestyle/security blogs dropped (paulgraham, jeffgeerling, daringfireball, krebsonsecurity, etc.). Selection rule was "would a VitaClaw reader find this useful for daily digest" — kept simonwillison, gwern, dwarkesh, garymarcus, minimaxir, lucumr, mitchellh, antirez, matklad, eli.thegreenplace, geoffreylitt, wheresyoured, rachelbythebay.

## Engineering blog probes

8 official_eng_blog feeds shipped (HuggingFace, LangChain, Cloudflare, GitHub, Microsoft Old New Thing, AWS Machine Learning, Stack Overflow, Vercel).

Tried but excluded due to 404 / proxy block during curation (operator should re-probe on Hermes production host before Phase 5 execution and add back if any return 200):

- `https://www.anthropic.com/news/rss.xml` — proxy-blocked locally
- `https://openai.com/blog/rss.xml`, `https://openai.com/news/rss.xml` — proxy-blocked locally
- `https://research.google/blog/rss/` — proxy-blocked locally
- `https://mistral.ai/news/rss.xml` — proxy-blocked locally
- Netflix / Uber / Airbnb engineering — proxy-blocked locally

Cisco Umbrella proxy on the curator's machine intercepts most of these — the URLs themselves are likely valid in production.

## Plan edits applied

| Plan file                              | Edit count | Verification |
| -------------------------------------- | ---------- | ------------ |
| `05-01-rss-schema-and-opml-PLAN.md`    |  10 edits  | `agent_ecosystem_2026.opml` present; `dimension TEXT`, `priority TEXT`, `source_type TEXT` columns added to `rss_feeds`; `dimensions TEXT` column added to `rss_classifications`; Tasks 1.3 + 1.4 wholesale-replaced for new OPML schema; verify_rss_opml.py check threshold updated `>= 90` → `>= 60`. Frontmatter wave/depends_on UNCHANGED. 4 tasks preserved. |
| `05-03-rss-classify-PLAN.md`           |   5 edits  | `CLASSIFY_PROMPT` augmented with 7-dim `dimensions` rule; `_classify` wraps result with `VALID_DIMENSIONS` guard + fallback `["idea"]`; INSERT now writes 7 columns including JSON-encoded `dimensions`; truth + acceptance criteria expanded for dimensions field. Frontmatter wave/depends_on UNCHANGED. 1 task preserved. |
| `05-05-daily-digest-PLAN.md`           |   5 edits  | CANDIDATE_SQL grew `dimensions` column (NULL on KOL branch, `c.dimensions` on RSS branch); RSS branch `enriched=2` filter REMOVED (D-07/D-19 honored); `TOP_N_PER_GROUP=3` constant + `_primary_dimension` helper introduced; render spec rewritten to two-section layout (KOL flat highlights + RSS grouped by dimension); test count 6→9; min_lines 160→180; truths + acceptance criteria refreshed. Frontmatter wave/depends_on UNCHANGED. 1 task preserved. |

Locked Phase 5 decisions all preserved:

- D-07 REVISED — RSS articles never enriched; the `enriched=2` filter removed only on the RSS branch of the asymmetric UNION ALL.
- D-08 — EN→CN inside the prompt; the new `dimensions` rule does NOT touch this.
- D-15/D-18/D-19 — asymmetric UNION ALL preserved; KOL keeps `enriched=2`; RSS does not.
- KOL `classifications` schema NOT touched; the new `dimensions` column lives only on `rss_classifications`. Phase 10 unaffected.

## Files in this commit (5e5465b)

- `data/agent_ecosystem_2026.opml` (NEW, 131 lines, 78 leaf outlines)
- `data/agent_ecosystem_2026.README.md` (NEW, 193 lines, 6 required sections)
- `.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md` (MODIFIED)
- `.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md` (MODIFIED)
- `.planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md` (MODIFIED)
- `.planning/quick/260505-seu-agent-ecosystem-rss-curation/260505-seu-PLAN.md` (NEW)

`.gitignore` had a pre-existing un-staged change in the working tree (unrelated to this task — added `.claude/skills/`, `.dev-runtime/`, etc.). Per Surgical Changes principle, that diff was NOT included in this commit. Instead, `data/agent_ecosystem_2026.opml` was force-added via `git add -f` to bypass the `data/*` ignore rule for this single commit. Operator may want to add `!data/agent_ecosystem_2026.opml` to `.gitignore` in a separate commit when convenient.

## Out-of-scope guarantees honored

- No Phase 5 plan executed (execute-gate still BLOCKED until Day-1/2/3 KOL baseline ~2026-05-06 ADT).
- No edits to 05-CONTEXT.md / 05-PRD.md / 05-RESEARCH.md / Plans 00, 02, 04, 06.
- No edits to production source code (`lib/`, `lib/scraper.py`, `lib/lightrag_embedding.py`, `ingest_wechat.py`, `batch_ingest_from_spider.py`, etc.).
- No Twitter/X handling added.
- Wave structure preserved (Wave 1 = 05-00..05-03, Wave 2 = 05-04..05-05); plan count unchanged (9 plans in Phase 5).

## Final commit

`5e5465bc6f4a0aca2ab93cbe0ce7519499865fd7`
