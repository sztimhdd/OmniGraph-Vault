# Feature Landscape: Hermes Agent KB Skills

**Domain:** Personal knowledge base agent skills (ingest + query)
**Researched:** 2026-04-21
**Confidence:** HIGH — derived from official CLAUDE.md skill writing standards,
direct code analysis of the underlying scripts, and codebase concern audit.

---

## Scope

Two skills are in scope:

| Skill | Wraps | Trigger intent |
|---|---|---|
| `omnigraph_ingest` | `ingest_wechat.py` + `multimodal_ingest.py` | User wants to save something |
| `omnigraph_query` | `kg_synthesize.py` | User wants to ask about stored knowledge |

---

## Table Stakes

Features the skills must have for the agent to feel usable. Missing any = broken experience.

### ingest skill

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| Accept WeChat URL directly | Core use case | Low | Pattern: `https://mp.weixin.qq.com/s/...` |
| Confirm what was saved | Agent must close the loop | Low | Title + hash + method used |
| Surface scrape failures clearly | Scraping fails often (CDP down, Apify quota) | Low | Distinct messages per failure mode |
| Reject non-WeChat URLs with redirect | User may paste wrong URL | Low | Tell them which skill handles PDFs |
| Guard against missing GEMINI_API_KEY | System is broken without it | Low | Check before calling script, not after |
| Announce that ingestion is starting | Scraping takes 30–300s | Low | Single line before exec, not a spinner |
| Report which scrape method succeeded | Apify vs CDP matters for trust | Low | Already in script stdout |

### query skill

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| Accept natural language query | Core use case | Low | Pass through to kg_synthesize.py |
| Return formatted synthesis | kg_synthesize.py already produces Markdown | Low | Render or quote as-is |
| Handle empty KB gracefully | New installs hit this immediately | Low | Detect "no meaningful response" output |
| Indicate when synthesis is running | kg_synthesize.py takes 15–60s | Low | One-line pre-exec message |
| Surface Gemini API failures | Quota and key errors happen | Low | Catch non-zero exit code |
| Confirm output file location | Synthesis writes to synthesis_output.md | Low | Useful for downstream Telegram delivery |

---

## Differentiators

Features that make the skills noticeably better, but are not expected baseline.

| Feature | Value | Complexity | Notes |
|---|---|---|---|
| **URL validation before exec** (ingest) | Prevents wasted 30s+ wait if URL is obviously wrong | Low | Regex check for WeChat domain pattern, not full network validation |
| **Duplicate detection hint** (ingest) | Prevents user confusion when re-ingesting same article | Medium | Check if article hash exists in images/ dir before running |
| **Query mode selection** (query) | "hybrid" is faster and better; users benefit from knowing modes exist | Low | Accept "naive / local / global / hybrid / mix" as optional keyword in message; default to hybrid not naive (CONCERNS.md calls out naive default as a bug) |
| **Image server warning** (query) | Synthesis output has broken image links if server is down | Low | Check if port 8765 is listening before running; warn if not |
| **Cognee recall notice** (query) | Makes the memory layer visible — users learn the KB remembers context | Low | Surface "drawing on N past queries" if past_context is non-empty |
| **PDF ingest redirect** (ingest) | Users naturally try to ingest PDFs through ingest skill | Low | Detect `.pdf` extension or file path and redirect to multimodal_ingest.py with correct framing |

---

## Anti-Features

Things to explicitly NOT build into these two skills.

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| Status / health check inside ingest or query | Bloats scope; makes trigger matching ambiguous | Build `omnigraph_status` as a separate skill per CLAUDE.md planned skills list |
| Entity management (list, delete, reindex) inside query | Wrong scope; creates scope creep | `omnigraph_manage` is the right skill for that |
| Batch ingestion loop | Out of scope per PROJECT.md; adds untested code paths | Single URL per call; user can call ingest multiple times |
| Synthesize vs query disambiguation in one skill | query and synthesize are different output styles; merging creates a vague skill | Keep `omnigraph_query` for question-answering; add `omnigraph_synthesize` later if needed |
| Automatic Cognee batch processor launch | Side effect inside a skill is confusing and hard to test | User or system daemon runs cognee_batch_processor.py separately |
| Inline progress polling (streaming stdout) | Hermes agent skills run subprocess to completion; they don't stream | Single start announcement, then wait; report result on completion |

---

## Trigger Phrase Design

### omnigraph_ingest

**Design principle:** Trigger on verbs of preservation + knowledge storage, not on URL format. The agent should recognize intent, not just pattern-match URLs.

**Recommended triggers (put in SKILL.md frontmatter):**
```yaml
triggers:
  - "add this to my kb"
  - "save this article"
  - "ingest"
  - "add to knowledge base"
  - "remember this article"
  - "store this for me"
  - "add this to omnigraph"
  - "save this url"
```

**Negative triggers (document in SKILL.md body — when NOT to fire):**
- If user says "search", "query", "what do I know" → route to `omnigraph_query`
- If user says "status", "how many nodes", "is the kb healthy" → route to `omnigraph_status`
- If input is a local file path ending in `.pdf` → route to `multimodal_ingest.py` (or document this as a variant within ingest skill)

**Why these phrases work:**
- "add this to my kb" is the phrase in PROJECT.md core value statement — high signal
- "ingest" is a technical term that only this skill handles — low ambiguity
- "remember this article" aligns with Hermes memory framing without colliding with Cognee recall phrases

### omnigraph_query

**Design principle:** Trigger on information-retrieval intent. Avoid colliding with Hermes's built-in web search or memory recall.

**Recommended triggers:**
```yaml
triggers:
  - "what do I know about"
  - "search my kb"
  - "search the knowledge base"
  - "query my knowledge base"
  - "what's in my kb about"
  - "look up in my kb"
  - "ask omnigraph"
  - "what have I saved about"
```

**Negative triggers:**
- "search the web" / "google this" → do not fire; that's a different skill
- "list everything" / "show all entities" → route to `omnigraph_manage`
- "write a report" / "summarize everything I know" → can be handled here with mode=global, but document this explicitly

**Why these phrases work:**
- "what do I know about" is natural, personal KB framing — matches PROJECT.md core value
- "search my kb" is explicit enough to avoid triggering on general web search intents
- "ask omnigraph" gives the user a named handle for the system

---

## Response Format Specification

### omnigraph_ingest: Success

```
Ingesting: <url>
Scraping with Apify... (or: Scraping via CDP fallback...)

Saved to knowledge base.
  Title:  <title from stdout>
  Hash:   <hash>
  Images: <N> processed
  Method: apify | cdp

Entity extraction queued for async processing.
```

**Rationale:** Closing message confirms what was saved. Hash is useful if user wants to find the article's image dir. "Queued for async processing" manages expectations — entities appear in canonical map later.

### omnigraph_ingest: Failure modes

| Failure | Message |
|---|---|
| Missing GEMINI_API_KEY | `⚠️ Config: GEMINI_API_KEY is not set in ~/.hermes/.env. Ingestion cannot proceed.` |
| Non-WeChat URL | `⚠️ Input: This URL doesn't look like a WeChat article (expected mp.weixin.qq.com). If you meant to ingest a PDF, I can do that instead — just confirm.` |
| Apify + CDP both failed | `⚠️ Scrape: Both Apify and CDP failed. Check that Edge is running with remote debugging enabled (--remote-debugging-port=9223) and try again.` |
| Script exited non-zero | `⚠️ Ingest: Script failed. Last output: <last 3 lines of stdout>. Check ~/.hermes/omonigraph-vault/ for partial output.` |
| Missing APIFY_TOKEN only | No warning — CDP fallback handles it. Script already prints "Apify Token not found, skipping Apify." |

### omnigraph_query: Success

```
Querying knowledge base: "<query>" (mode: hybrid)

<synthesis output from kg_synthesize.py — rendered as Markdown>

---
Synthesis saved to: ~/.hermes/omonigraph-vault/synthesis_output.md
```

**Rationale:** Showing mode (hybrid) educates the user. Showing save path enables downstream delivery to Telegram.

### omnigraph_query: Failure modes

| Failure | Message |
|---|---|
| Missing GEMINI_API_KEY | `⚠️ Config: GEMINI_API_KEY not set. Query cannot proceed.` |
| Empty or near-empty KB | `⚠️ KB Empty: The knowledge base returned no meaningful results. Try ingesting some articles first with "add this to my kb <url>".` |
| Image server not running | `⚠️ Images: Local image server is not running on port 8765. Inline images in the report may appear broken. Start it with: cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images` |
| Cognee recall failed | Silent — Cognee recall failure is already a warning in the script; skill should not surface this unless all else fails. It degrades gracefully. |
| Script exited non-zero | `⚠️ Query: Synthesis failed. Last output: <last 3 lines of stdout>.` |

**Detection of "empty KB":** Check stdout for LightRAG's "no results" patterns. At minimum: if response is shorter than 100 characters or contains "I don't have enough information", treat as empty.

---

## Progress Feedback for Long-Running Operations

### Why this matters

- `ingest_wechat.py` takes 30–300s (Apify timeout is 300s; CDP load + image download + Gemini Vision calls add more)
- `kg_synthesize.py` takes 15–60s (LightRAG hybrid query + Cognee recall + Gemini synthesis)

Hermes agents do not stream subprocess stdout in real time — they wait for completion. This means the agent goes silent for up to 5 minutes without user feedback unless the skill's SKILL.md tells the agent to announce before running.

### Pattern to use: announce-then-exec

The agent should emit one message before calling the script:

**Ingest:**
> "Starting ingestion — this typically takes 30–120 seconds while scraping and processing images. I'll report back when it's done."

**Query:**
> "Querying your knowledge base — this takes 15–60 seconds. Sitting tight..."

**Why not a spinner/poll loop:** Skills call scripts via exec. There is no hook for mid-execution feedback without restructuring the scripts to write progress to a temp file and polling it — that's out of scope for Phase 2.

**Where to write this in SKILL.md:** In the "Execution" section, before the exec block. Write it as an explicit instruction: "Before running the script, tell the user: [phrase]."

---

## Progressive Disclosure: What Goes in SKILL.md vs References

### SKILL.md should contain (Level 1)

Keep SKILL.md under ~150 lines. Include only what the agent needs to decide and act:

- Frontmatter (name, description, triggers, metadata.openclaw.requires)
- When to trigger (decision tree: this phrase → use this skill)
- When NOT to trigger (redirect rules)
- Environment check (GEMINI_API_KEY present?)
- Pre-exec announcement phrase
- Exact exec command with argument mapping
- Success output format (what to relay to user)
- Failure message templates (⚠️ blocks)
- Explicit "do not do X" rules

### Push to references/ (Level 2)

- Full list of query modes with explanations (naive / local / global / hybrid / mix) → `references/query-modes.md`
- Troubleshooting guide for CDP / Apify setup → `references/scraping-setup.md`
- Environment variables full reference → `references/env-reference.md`
- LightRAG storage layout explanation → `references/storage-layout.md`

The agent only loads Level 2 if it explicitly needs it (e.g., user asks "what query modes are available?"). This keeps every ingest/query call lean.

---

## MVP Recommendation

Build both skills now. They are the active requirements in PROJECT.md and both underlying scripts are gate-tested.

**Priority order within each skill:**

For `omnigraph_ingest`:
1. GEMINI_API_KEY guard clause (system is broken without it)
2. WeChat URL pattern check (prevents 300s wasted wait)
3. Pre-exec progress announcement
4. Success output format (title + hash + method)
5. Failure messages for Apify+CDP failure and script non-zero exit

For `omnigraph_query`:
1. GEMINI_API_KEY guard clause
2. Pre-exec progress announcement
3. Hybrid mode default (fix the naive default per CONCERNS.md)
4. Image server warning
5. Success output (render synthesis + save path)
6. Empty KB detection

**Defer:**
- Duplicate URL detection: Adds value but requires checking images/ dir — medium complexity, can be added after Gate 7 validation
- Cognee recall visibility ("drawing on N past queries"): Nice-to-have, requires parsing script stdout — defer to second iteration
- PDF ingest redirect from `omnigraph_ingest`: Implement as a variant in the ingest skill's body (one conditional branch), not a full separate skill yet

---

## Feature Dependencies

```
GEMINI_API_KEY in ~/.hermes/.env → all features (hard dependency)
ingest success → query returns useful results (soft ordering: ingest before query)
image server running on port 8765 → synthesis output renders correctly
CDP / Edge with remote debugging → CDP fallback path (soft; Apify is primary)
cognee_batch_processor.py running → canonical map populated (async; query works without it)
```

---

## Confidence Assessment

| Area | Confidence | Basis |
|---|---|---|
| Trigger phrases | HIGH | Derived from PROJECT.md core value statement + CLAUDE.md trigger list + first-principles phrase design |
| Failure modes | HIGH | Derived from direct code analysis of ingest_wechat.py and kg_synthesize.py + CONCERNS.md audit |
| Progress feedback pattern | HIGH | Derived from CLAUDE.md progressive disclosure model + known Hermes exec behavior |
| Output formats | HIGH | Derived from CLAUDE.md "Consistent output formatting" rule (>5 items = table, ≤5 = bullets, errors = ⚠️ block) |
| SKILL.md content split | HIGH | Derived directly from CLAUDE.md Level 0/1/2 progressive disclosure specification |
| Empty KB detection heuristic | MEDIUM | Based on observed LightRAG output patterns; exact strings need validation against live system |
