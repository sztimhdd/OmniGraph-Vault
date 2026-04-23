# Feature Landscape: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP

**Domain:** Architecture advisor agent skill over a rules-engine + populated knowledge graph
**Researched:** 2026-04-23
**Confidence:** HIGH — derived from MILESTONE-2-SIMPLE-GUIDE.md, existing SKILL.md files, skill_runner.py source analysis, and the SKILL_PACKAGING_GUIDE.md. No external web search required; all patterns grounded in the in-repo ecosystem established in v1.

---

## Scope Clarification (What Is NOT Being Re-Researched)

The following features are ALREADY BUILT and are NOT in scope for this document:

- WeChat + PDF ingestion → LightRAG KG (`omnigraph_ingest`, `ingest_wechat.py`)
- Knowledge graph query + Gemini synthesis (`omnigraph_query`, `kg_synthesize.py`)
- `skill_runner.py` single-turn test harness (9/9 ingest + 10/10 query passing)
- SkillHub-ready packaging for the two existing skills

This document covers only the NEW features required for v2.0:
1. `rules_engine.json` — structured architecture rules
2. KB population — GitHub AI tools + KOL articles
3. `omnigraph_architect` skill — Propose / Query / Ingest decision tree
4. `skill_runner.py` multi-turn support

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that must exist for the milestone to be considered complete. Missing any = the `/architect` skill does not deliver its core value.

#### Rules Engine (`rules_engine.json`)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| JSON file at project root, loadable with `json.load()` | `/architect` must apply rules at runtime without a database | LOW | A plain file, not a DSL or database — consistent with the project's "local-first, no SaaS" constraint |
| Each rule has: `id`, `condition`, `recommendation`, `dont_use`, `weight` | Enough fields to drive a decision + a don't-use list, which is the primary user value | LOW | `id` for deduplication; `condition` for trigger matching; `recommendation` for safe default; `dont_use` as a list; `weight` (0-10 int) for priority ordering |
| 20–30 rules covering common overengineering patterns for solo/indie dev context | The MILESTONE-2-SIMPLE-GUIDE.md specifies this range; below 20 = too thin to be useful | MEDIUM | Bootstrap via Copilot (Task 2.1-01); human dedup + weighting pass (Task 2.1-02) |
| Rules testable by hand with 3 scenario types: solo dev, startup, researcher | Manual scenario testing is the acceptance gate before `/architect` is written | LOW | Three test runs through rules_engine.json with different persona inputs — no test framework needed |
| Tags on each rule for category filtering | `/architect` must filter rules by context (e.g., only "solo-dev" rules when persona = solo) | LOW | `"tags": ["solo-dev", "overengineering"]` — string array, free-form at this stage |

#### KB Population

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| 50+ GitHub AI tools indexed in LightRAG | `omnigraph_query` must return useful answers to "what is LangChain?" before `/architect` query mode can work | MEDIUM | Batch ingest via `ingest_github.py` loop (GitHub REST API); creates `entity_registry.json` as side effect |
| `entity_registry.json` mapping GitHub URL → entity ID | Required to avoid re-ingesting the same tool on repeat runs | LOW | Key: GitHub URL; Value: LightRAG entity ID or article hash; written atomically (tmp → rename) |
| 5–10 KOL articles indexed | Architecture advisory needs real-world "best practices" perspectives, not just docs | MEDIUM | Manual curation: WeChat KOL, GitHub issue discussions, Zhihu — tagged with `--tag kol --author` |
| `query_lightrag.py` returns useful answers to "best practices" questions | Integration gate before `/architect` can be written — KB must contain enough signal | MEDIUM | Verified via: `python query_lightrag.py "What are best practices for building a chatbot?" hybrid` returning multi-source output |

#### `/architect` Skill Core

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| SKILL.md frontmatter with name, description, triggers | All skills must meet SkillHub packaging standard (existing requirement from SKILL_PACKAGING_GUIDE.md) | LOW | Same format as `omnigraph_ingest` and `omnigraph_query` |
| `scripts/architect.sh` wrapper with env validation + venv activation | Shell wrapper contract is mandatory per SKILL_PACKAGING_GUIDE.md §"scripts/"; without it the skill cannot execute | LOW | Same pattern as `scripts/ingest.sh` and `scripts/query.sh` |
| Decision tree: detect Propose vs Query vs Ingest intent | The skill has 3 distinct modes; without routing, the agent applies the wrong behavior | MEDIUM | 3-case decision tree in SKILL.md body — modeled on the existing decision tree pattern |
| GSD:DISCUSS 4-step pattern for Propose mode | Propose mode requires gathering context before applying rules — a free-form response without structured questioning produces bad recommendations | MEDIUM | Step 1: Default Guess → Step 2: Q1 (context question) → Step 3: Q2 (constraint question) → Step 4: Output (stack + don't-use + TDD template). Must be documented first in `.planning/GSD_DISCUSS_PATTERN.md` |
| Propose mode output: safe defaults + don't-use list + TDD template | This is the primary value proposition of the `/architect` skill per MILESTONE-2-SIMPLE-GUIDE.md | MEDIUM | Format: (1) recommended stack as bullet list, (2) "Don't use" as ⚠️ block, (3) TDD template command or scaffold pattern |
| Query mode: pass question to `kg_synthesize.py` and return answer | Users should be able to ask knowledge questions without knowing they're hitting the KB | LOW | Route to `scripts/query.sh` — identical to `omnigraph_query`; no duplication of logic needed |
| Ingest mode: accept URL, call `scripts/ingest.sh`, confirm success | Users should be able to add new tools to the KB from within the `/architect` skill | LOW | Route to `scripts/ingest.sh` — identical to `omnigraph_ingest`; skill composes on top of existing scripts |
| Guard clause: missing GEMINI_API_KEY surfaces actionable message | Consistent with all existing skills; expected by the packaging standard | LOW | Same guard pattern as in `omnigraph_ingest` and `omnigraph_query` |

#### `skill_runner.py` Multi-Turn Support

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `TestCase` schema accepts `inputs: list[str]` instead of `input: str` | GSD:DISCUSS Propose mode requires 3–4 conversation turns; single-turn tests cannot validate this | MEDIUM | Backward-compatible: if `inputs` is absent, fall back to existing `input` field; no change to existing 19 test cases |
| Conversation context accumulates across turns within a single test case | The model must remember the GSD:DISCUSS state (what was already asked) to validate turn-by-turn behavior | MEDIUM | Implemented via `contents` parameter in the Gemini API — build a list of `{role, content}` pairs and pass the growing list on each turn |
| `expect_final` field checked only on last turn's response | Intermediate turns should not be checked for final output format — only the last response is the completion signal | LOW | New field `expect_final: list[str]` runs the same `expect_contains` check but only on the last turn; `expect_contains` on each entry in `inputs` checks per-turn assertions |
| Backward compatibility with existing single-turn test files | All 19 existing test cases (`test_omnigraph_ingest.json`, `test_omnigraph_query.json`) must continue to pass without modification | LOW | Achieved by: if `inputs` key is absent and `input` key is present, treat as single-turn; no schema migration required |

---

### Differentiators (Competitive Advantage)

Features that set this skill apart from a generic architecture advisor. Not required for MVP, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rules engine applies persona-specific filtering | A solo dev gets different recommendations than a startup CTO — the same stack is not universally "safe" | MEDIUM | `condition` field can encode persona tags; `/architect` filters on persona extracted from GSD:DISCUSS Q1 response |
| `weight` field enables priority ordering of recommendations | When 5 rules fire on the same context, the highest-weight rules surface first — avoids recommendation noise | LOW | Sort rules by `weight` descending before building the output; no algorithmic complexity |
| `/architect` can cross-reference KB entities against rules | "You mentioned LangChain — my KB says X about it, and rule_007 says avoid agent frameworks in solo projects" | HIGH | Requires joining rules engine output with kg_synthesize.py results — non-trivial; defer unless Phase 2.1 KB population quality is high |
| `entity_registry.json` prevents duplicate ingestion | If user says "add LangChain to my KB" but it's already there, the skill can say "already indexed" instead of re-running 30s ingest | LOW | Check registry before running `ingest.sh`; add to Ingest mode decision tree |
| GSD:DISCUSS pattern documented as reusable template | Other future skills (e.g., a project scoping advisor) can adopt the same 4-step conversation flow | LOW | Document in `.planning/GSD_DISCUSS_PATTERN.md` as a standalone pattern, not just in SKILL.md; this becomes a project convention |
| TDD template in Propose output | Gives the user an actionable next step, not just a stack recommendation | LOW | The TDD template is a small static block per stack category (e.g., "For a Python backend: pytest, use tdd-guide skill"); included in rules_engine.json `recommendation` field |

---

### Anti-Features (Explicitly NOT Building)

Features a solo dev might be tempted to add that create more problems than they solve.

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| `/architect` calls a live external API to enrich rules at runtime | More up-to-date rules without manual editing | Adds a network dependency to a skill that must work offline; API rate limits will cause flaky tests; breaks the "local-first" constraint | Periodically re-run Copilot bootstrapping to refresh rules_engine.json; this is a manual process, not an automated one |
| Rules engine as a database (SQLite, Redis, etc.) | More scalable and queryable at 100+ rules | 20–30 rules fit in RAM as a Python dict; a database adds a dependency, migration story, and 30+ lines of boilerplate for no benefit at this scale | Stay with `json.load()` + in-memory filtering; revisit only if rules exceed 100 |
| `/architect` exposes all 3 modes via subcommands (e.g., `/architect propose`, `/architect query`) | Cleaner interface, easier to test individually | The Hermes trigger system matches on natural language, not subcommands; rigid subcommands require the user to know the taxonomy; a good decision tree infers mode from context | Let the decision tree infer mode from the message; use trigger phrases ("should I use X?", "what is X?", "add X to KB") to route — the skill body makes this explicit |
| Streaming progress output from `architect.sh` | The GSD:DISCUSS flow involves multiple turns; the user expects to see the agent "thinking" | Hermes does not stream subprocess stdout; skills run to completion; adding streaming would require restructuring scripts with temp files + polling, which is out of scope for a solo dev | Use the announce-then-exec pattern: tell the user "Applying rules, this may take a few seconds..." before running the script |
| Multi-skill test runner in `skill_runner.py` (cross-skill routing validation) | Tests that verify `/architect query` mode does NOT fire `omnigraph_ingest` | Cross-skill routing tests require loading multiple skill system prompts simultaneously; the current architecture is per-skill; adding this is a new layer | Test cross-skill behavior manually in Gate 7 with real Hermes; add cross-skill test cases to the Gate 7 test protocol, not to `skill_runner.py` |
| Auto-tag ingested content by persona type | Automatically label KB content as "solo-dev", "startup", etc. based on LLM classification | Adds an async classification step to every ingestion; mis-classification silently corrupts rule filtering; the benefit is marginal at 50–100 articles | Manually tag KOL articles at ingest time with `--tag solo-dev`; this is faster and more accurate at the current KB size |
| Web scraping in `/architect` ingest mode (arbitrary URLs, not just WeChat) | Users want to add GitHub READMEs, blog posts, Hacker News threads directly | `ingest_wechat.py` is purpose-built for WeChat; arbitrary URL scraping requires Firecrawl or a new code path; adds a new dependency and new failure modes | Use `ingest_github.py` (GitHub REST API) for GitHub tool ingestion (Task 2.1-03); use the existing `ingest_wechat.py` for WeChat + PDF only; document the limitation clearly in the skill |

---

## Feature Dependencies

```
GEMINI_API_KEY in ~/.hermes/.env
    └──required-by──> all features (hard dependency)

rules_engine.json (Task 2.1-02)
    └──requires──> Copilot bootstrap output (Task 2.1-01)
    └──required-by──> /architect Propose mode
    └──required-by──> rules-persona filtering (differentiator)

KB population: GitHub tools (Task 2.1-03)
    └──required-by──> /architect Query mode returning useful answers
    └──required-by──> rules+KB cross-reference (differentiator — deferred)

KB population: KOL articles (Task 2.1-04)
    └──required-by──> "best practices" query answering (integration gate)
    └──enhances──> rules_engine.json (rules grounded in real-world evidence)

entity_registry.json
    └──built-as-side-effect-of──> KB population (Task 2.1-03)
    └──required-by──> duplicate ingestion prevention (differentiator)

GSD:DISCUSS pattern document (Task 2.2-01)
    └──required-by──> /architect SKILL.md Propose mode decision tree (Task 2.2-02)

/architect SKILL.md + scripts/architect.sh (Task 2.2-02)
    └──requires──> rules_engine.json (Task 2.1-02)
    └──requires──> GSD:DISCUSS pattern (Task 2.2-01)
    └──requires──> KB population passing integration gate
    └──required-by──> /architect test cases (Task 2.2-04)

skill_runner.py multi-turn support (Task 2.2-03)
    └──required-by──> /architect Propose mode test cases (multi-turn scenarios)
    └──must-not-break──> existing 19 single-turn test cases

/architect test cases (Task 2.2-04)
    └──requires──> skill_runner.py multi-turn support (Task 2.2-03)
    └──requires──> /architect SKILL.md (Task 2.2-02)
```

### Dependency Notes

- **rules_engine.json requires Copilot bootstrap:** The Copilot research pass produces unstructured text; the human dedup + weighting pass converts it to valid JSON. Neither step can be skipped; attempting to write rules directly risks narrow coverage.
- **KB population is a pre-condition for /architect Query mode:** If `query_lightrag.py "best practices for chatbot"` returns empty or low-quality results, the Query mode of `/architect` is broken regardless of how well the routing logic is written. The integration checkpoint after Task 2.1-04 is the gate.
- **skill_runner.py multi-turn must not break existing tests:** The 19 existing tests use `"input": "..."` (string). The new schema uses `"inputs": [...]` (array). These are different field names; the runner must check which key is present. If the wrong key triggers the wrong path, existing tests will silently skip turns and report false passes.
- **GSD:DISCUSS pattern must be documented before SKILL.md is written:** The decision tree in SKILL.md references specific conversation steps. If the pattern isn't documented first, the SKILL.md author will improvise and the result will be inconsistent between the SKILL.md and the test cases.

---

## Detail: GSD:DISCUSS 4-Step Pattern

This is the conversation pattern for `/architect` Propose mode. It is a table stakes feature of the skill, not a differentiator — without it, the skill can only give generic recommendations.

### What It Is

A 4-turn conversation flow the agent follows when the user asks for an architecture recommendation. The agent must gather context before applying rules, because "use LangChain" is correct for some contexts and wrong for others.

### The 4 Steps

```
Turn 1 — Default Guess (system-initiated)
  Agent: Makes an educated assumption about the user's context based on the request alone.
  Output: "It sounds like you're [persona guess, e.g., solo developer building a side project]
           and you want [goal guess]. My initial recommendation would be [safe default stack].
           Does that sound right? (yes = go with this, no = let me ask a couple of questions)"

Turn 2 — Q1: Context Question
  Triggered when: user says "no" or "not quite" to the Default Guess.
  Focus: team size + project type (the two highest-signal inputs for rule filtering).
  Template: "To give you better advice: are you building this solo or with a team?
             And is this a quick prototype, a long-term product, or a research project?"

Turn 3 — Q2: Constraint Question
  Focus: the single most important constraint (time, scale, or maintainability).
  Template: "One more question: what's your biggest constraint right now —
             speed of delivery, keeping things simple to maintain, or handling large scale?"

Turn 4 — Output
  Triggered: after Q1 + Q2 responses are collected (or directly after a "yes" to Default Guess).
  Content:
    1. Recommended stack as a bullet list (from rules_engine.json, filtered by persona + constraint)
    2. "Don't use" as a ⚠️ block (from `dont_use` field of fired rules)
    3. TDD template: one command or scaffold pattern to start testing immediately
```

### When to Skip to Output Directly

If the user's initial message already contains sufficient context (mentions team size, or explicitly says "solo" / "startup"), the agent can skip Turn 2 and Turn 3 and proceed directly to Turn 4. The skill body should state this explicitly as a Case in the decision tree.

### What "Fired Rules" Means

A rule "fires" when the `condition` text matches the user's stated context. At the current scale (20–30 rules), this is string matching / keyword overlap between the rule's `condition` field and the user's context collected across Turns 2–3. It is NOT an LLM classification step — the agent reads the rules and applies them with its own judgment. This is intentional: it keeps the rules engine simple and avoids adding an LLM call inside the skill.

---

## Detail: `skill_runner.py` Multi-Turn Schema

### Current Schema (Single-Turn)

```json
{
  "description": "golden path: WeChat URL triggers ingest.sh",
  "input": "add this article to my knowledge base: https://mp.weixin.qq.com/s/...",
  "expect_contains": ["ingest.sh"],
  "expect_not_contains": ["omnigraph_query"]
}
```

### New Schema (Multi-Turn)

```json
{
  "description": "propose mode: solo dev context — 4-turn GSD:DISCUSS flow",
  "inputs": [
    "should I use LangChain for my personal assistant project?",
    "no, not quite — tell me more",
    "solo developer, side project prototype",
    "speed is the main constraint"
  ],
  "expect_contains": ["scripts/architect.sh"],
  "expect_final": ["don't use", "recommended", "tdd"],
  "expect_not_contains": ["omnigraph_ingest", "kg_synthesize"]
}
```

### Key Design Decisions

- `inputs` (array) signals multi-turn; `input` (string) signals single-turn. Both schemas are valid; the runner checks for `inputs` first.
- `expect_contains` checks every turn's response — useful for verifying the routing command appears in the first response.
- `expect_final` is a new field checked only on the last turn's response — the final output must contain safe-defaults + don't-use language.
- Conversation context is accumulated as a growing `contents` list passed to the Gemini API. The system prompt (SKILL.md) is unchanged across turns — it stays as the `system_instruction`.
- The `TestCase` dataclass gains an `inputs: list[str]` field and an `expect_final: list[str]` field, both defaulting to empty list. The existing `input: str` field defaults to `""`.

### Implementation Scope

The multi-turn change is confined to three functions in `skill_runner.py`:
1. `TestCase` dataclass — add `inputs` and `expect_final` fields
2. `run_test_case()` — detect single vs multi-turn from `TestCase`, loop over `inputs` maintaining a `contents` list, check `expect_final` on last response only
3. `run_test_file()` — unchanged (already calls `run_test_case` per case)

The `call_gemini()` function needs a new `contents` parameter (replacing the `user_message: str` for multi-turn paths) that accepts either a string (single-turn) or a `list[dict]` (multi-turn contents array). This is the lowest-risk change surface.

---

## Detail: `/architect` Decision Tree

### Mode Detection Logic

The skill must detect intent from natural language. Three cases:

```
Case 1 — PROPOSE mode
  Triggers: "should I use X", "what stack for Y", "help me choose", "architect advice",
            "best approach for", "recommend a framework", "what would you use for"
  Requires: rules_engine.json loaded
  Flow: GSD:DISCUSS 4-step pattern → Output with stack + don't-use + TDD template

Case 2 — QUERY mode
  Triggers: "what is X", "tell me about X", "what do you know about X",
            "search my KB for X", "explain X", "compare X and Y"
  Requires: KB populated (kg_synthesize.py returns non-empty)
  Flow: Route to scripts/query.sh "<question>" → return synthesis output

Case 3 — INGEST mode
  Triggers: "add X to my KB", "save this", "ingest this URL",
            WeChat URL (mp.weixin.qq.com) provided with save intent
  Requires: ingest.sh available
  Flow: Route to scripts/ingest.sh "<url>" → confirm ingestion success

Guard Cases (handled before any mode routing):
  - GEMINI_API_KEY not set → ⚠️ error message, do not proceed
  - Ambiguous intent → ask clarifying question ("Are you asking for a recommendation, 
    searching your KB, or adding something new?")
  - Destructive operation request → redirect to omnigraph_manage
```

### SKILL.md Structure for `/architect`

Following the existing pattern from `omnigraph_ingest` and `omnigraph_query`, the SKILL.md should:
- Frontmatter: name (`omnigraph_architect`), description (100–200 words, 3–5 trigger phrases, 2–3 "when NOT to use" redirects), metadata.openclaw.requires
- Body sections (in order): Quick Reference table, When to Use, When NOT to Use, Decision Tree (3 cases + guard cases), GSD:DISCUSS Pattern, Propose Output Format, Error Handling table
- Body length target: 300–400 lines (longer than the two existing skills because the decision tree is more complex; still under 500-line SkillHub limit)
- References: `references/rules-reference.md` (full rules_engine.json schema documentation), `references/discuss-examples.md` (GSD:DISCUSS example transcripts for 3 personas)

---

## MVP Definition

### Phase 2.1: Launch With (Rules Engine + KB)

These are the minimum features needed to begin building `/architect`.

- [x] `rules_engine.json` with 20–30 rules, schema: `id`, `condition`, `recommendation`, `dont_use`, `weight`, `tags` — why essential: `/architect` Propose mode cannot fire without rules
- [x] `entity_registry.json` mapping GitHub URL → entity ID — why essential: prevents re-ingestion on repeat use; required for Ingest mode duplicate guard
- [x] 50+ GitHub AI tools indexed in LightRAG — why essential: Query mode must return useful answers
- [x] 5–10 KOL articles indexed — why essential: "best practices" questions need real-world evidence, not just docs
- [x] Integration gate passing: `python query_lightrag.py "best practices for chatbot" hybrid` returns multi-source output — why essential: this is the go/no-go gate for starting Phase 2.2

### Phase 2.2: Launch With (/architect Skill + Multi-Turn Testing)

- [x] `.planning/GSD_DISCUSS_PATTERN.md` — documented before SKILL.md is written
- [x] `skills/omnigraph_architect/SKILL.md` (300–400 lines, 3-mode decision tree + GSD:DISCUSS) — core deliverable
- [x] `skills/omnigraph_architect/scripts/architect.sh` — required for skill to execute
- [x] `skill_runner.py` multi-turn support — required for Propose mode test cases
- [x] 9 test cases in `tests/skills/test_omnigraph_architect.json` (3 per mode) — required for milestone completion gate
- [x] All tests passing: `python skill_runner.py skills/ --test-all`

### Add After Validation (v2.x)

- [ ] Rules+KB cross-reference in Propose mode — add when KB quality is high enough to give reliable tool-specific advice (trigger: user feedback that recommendations feel generic)
- [ ] Persona-specific tags applied at ingest time — add when KB exceeds 100 articles (trigger: rules filtering starts producing noisy results)
- [ ] `omnigraph_status` skill — add when debugging KB health becomes a recurring need (trigger: user asks "how many tools are in my KB?" 3+ times manually)

### Future Consideration (v3+)

- [ ] Streaming progress output — defer until Hermes supports streaming subprocess stdout; significant script restructuring required
- [ ] Arbitrary URL ingestion in `/architect` Ingest mode — defer; requires Firecrawl or a new code path; current WeChat + PDF coverage is sufficient
- [ ] Rules engine as queryable database — defer until rules exceed 100; `json.load()` in memory is adequate at current scale

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `rules_engine.json` (20–30 rules) | HIGH | MEDIUM (bootstrapped by Copilot) | P1 |
| KB: 50+ GitHub tools indexed | HIGH | MEDIUM (batch ingest script + 4h) | P1 |
| KB: 5–10 KOL articles | MEDIUM | MEDIUM (manual curation + ingest) | P1 |
| `entity_registry.json` | MEDIUM | LOW (side effect of KB population) | P1 |
| `/architect` SKILL.md (3-mode decision tree) | HIGH | MEDIUM (300–400 lines, complex tree) | P1 |
| `scripts/architect.sh` | HIGH | LOW (same shell wrapper pattern) | P1 |
| `skill_runner.py` multi-turn support | HIGH | MEDIUM (dataclass + API change) | P1 |
| GSD:DISCUSS 4-step pattern | HIGH | LOW (documentation + SKILL.md section) | P1 |
| 9 test cases for `/architect` | HIGH | LOW (follows existing test file pattern) | P1 |
| Rules persona-filtering by tag | MEDIUM | LOW (sort + filter on existing fields) | P2 |
| `entity_registry.json` duplicate guard in Ingest | MEDIUM | LOW (registry lookup before ingest.sh) | P2 |
| GSD:DISCUSS pattern as project convention | LOW | LOW (document once in .planning/) | P2 |
| Rules + KB cross-reference in Propose | HIGH | HIGH (join two data sources + LLM call) | P3 |
| Auto-tagging ingested content | LOW | MEDIUM | P3 |
| `omnigraph_status` skill | LOW | LOW | P3 |

---

## Questions Answered by This Research

### Q1: Minimal JSON schema for a rule

```json
{
  "id": "rule_001",
  "condition": "solo developer building a side project with no team",
  "recommendation": "Use a single Python script or FastAPI for the backend; avoid microservices",
  "dont_use": ["microservices", "Kubernetes", "distributed message queues"],
  "weight": 8,
  "tags": ["solo-dev", "overengineering", "backend"]
}
```

**Rationale for each field:**
- `id`: enables deduplication, logging, and rule attribution in output
- `condition`: plain English — the agent reads this and decides if it applies; no query language needed at 20–30 rules
- `recommendation`: the "do this" answer — safe default stack
- `dont_use`: list of specific anti-recommendations — this is the primary user value differentiator ("tell me what NOT to use")
- `weight`: integer 0–10; higher = more important; used to sort when multiple rules fire; 8 = "this matters a lot for solo devs"
- `tags`: free-form string array; used for persona-based filtering; `"solo-dev"` / `"startup"` / `"researcher"` are the three target tags

### Q2: /architect decision tree in detail

See the "Detail: /architect Decision Tree" section above.

### Q3: GSD:DISCUSS 4-step pattern

See the "Detail: GSD:DISCUSS 4-Step Pattern" section above.

### Q4: Table stakes vs differentiators for architecture advisor skill

Table stakes: rules_engine.json loads cleanly, Propose mode fires when user asks for a recommendation, Query mode routes to kg_synthesize.py, Ingest mode routes to ingest.sh, GSD:DISCUSS pattern prevents free-form "just tell me what to use" responses that produce generic answers, Guard clauses for missing GEMINI_API_KEY and missing URL.

Differentiators: persona-specific rule filtering (solo vs startup vs researcher), `weight` field for priority ordering, entity_registry duplicate guard, TDD template in Propose output.

### Q5: What multi-turn skill_runner.py needs

See the "Detail: skill_runner.py Multi-Turn Schema" section above.

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Rules engine JSON schema | HIGH | Derived from MILESTONE-2-SIMPLE-GUIDE.md task 2.1-02 explicit field list + first-principles analysis of what `/architect` needs at runtime |
| GSD:DISCUSS 4-step pattern | HIGH | Derived from MILESTONE-2-SIMPLE-GUIDE.md task 2.2-01 explicit step definition; pattern is self-consistent with existing decision-tree SKILL.md structure |
| `/architect` decision tree | HIGH | Derived from existing SKILL.md decision tree patterns (omnigraph_ingest, omnigraph_query); 3-mode structure maps directly to MILESTONE-2-SIMPLE-GUIDE.md goals |
| multi-turn skill_runner.py schema | HIGH | Derived from current skill_runner.py source analysis (TestCase dataclass, call_gemini signature, run_test_case logic) + MILESTONE-2-SIMPLE-GUIDE.md task 2.2-03 explicit requirements |
| KB population complexity | MEDIUM | GitHub ingestion uses `ingest_github.py` + GitHub REST API; batch run is a manual loop over a curated repo list |
| Table stakes vs differentiators split | HIGH | Based on direct dependency analysis: anything the `/architect` output claims to deliver (stack + don't-use + TDD) is table stakes; anything that improves quality/personalization is a differentiator |

---

## Sources

- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\MILESTONE-2-SIMPLE-GUIDE.md` — milestone scope, task breakdown, success criteria, explicit field names for rules_engine.json
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skills\omnigraph_ingest\SKILL.md` — existing skill structure, decision tree pattern, guard clause format, output format
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skills\omnigraph_query\SKILL.md` — existing skill structure, Query mode routing pattern, error handling table
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skill_runner.py` — TestCase dataclass fields, call_gemini signature, run_test_case implementation — basis for multi-turn change surface analysis
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\skills\test_omnigraph_ingest.json` — existing test case schema (single-turn `input` field); backward compatibility baseline
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\skills\test_omnigraph_query.json` — existing test case schema; backward compatibility baseline
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\specs\SKILL_PACKAGING_GUIDE.md` — SkillHub packaging requirements, SKILL.md length limit (500 lines), scripts/ wrapper contract, evals/ schema

---

*Feature landscape for: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP*
*Researched: 2026-04-23*
*Scope: NEW features only — rules engine, KB population, /architect skill, multi-turn skill_runner*
