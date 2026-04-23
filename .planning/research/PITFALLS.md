# Domain Pitfalls: OmniGraph-Vault v2.0 Knowledge Infrastructure MVP

**Project:** OmniGraph-Vault — v2.0 (Rules Engine + KB Population + /architect Skill)
**Domain:** Adding rules engine, batch GitHub ingestion, and multi-mode LLM skill to an existing
LightRAG/Cognee/Gemini Python knowledge-graph system
**Researched:** 2026-04-23
**Confidence:** HIGH for in-repo evidence (codebase analysis, existing CONCERNS.md, SKILL.md files,
skill_runner.py source); MEDIUM for GitHub API rate-limit specifics (derived from known GitHub REST
API documentation); LOW where noted (first-principles reasoning without direct evidence)

**Scope note:** This file covers v2.0-specific pitfalls only — the 6 question domains below. For
v1.1 pitfalls (hardcoded paths, trigger collisions, env pre-flight, skill_runner false passes, etc.)
see the v1.1 PITFALLS.md in the same directory. Those pitfalls are prerequisites for v2.0 and must
be resolved before Phase 4 begins.

**Phase assignment key:**
- **Phase 4** = Rules Engine + Knowledge Base population
- **Phase 5** = /architect Skill Design + Testing

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or fundamentally wrong system behavior.

---

### Pitfall 1: rules_engine.json Schema Too Rigid to Be Queryable by an LLM

**Domain:** Rules engine design (Question 1)
**Phase:** Phase 4 (prevention), Phase 5 (symptom surfaces during architect skill integration)

**What goes wrong:** The rules JSON schema is designed for human readability — nested objects,
conditional logic encoded as prose, long natural language `condition` fields — but when
`kg_synthesize.py` or the `/architect` skill injects rules into an LLM prompt, the LLM either
ignores most rules (too much text), hallucinates rules that sound plausible, or applies the wrong
rule because the `condition` field required human interpretation that the LLM cannot do reliably.

A concrete example from the SIMPLE-GUIDE plan: each rule has `{ "condition": "...", "recommendation": "...", "dont_use": [...] }`.
If `condition` is `"when building a solo hobby project with no team requirements"`, the LLM must
match that condition against the user's conversational context — a subjective inference, not a
lookup. When multiple rules have similar conditions (common in architecture guidance), the LLM picks
one semi-randomly based on recency in the prompt rather than best match.

**Why it happens:** Rule schemas are written to look clean in JSON, not to be queried. The schema
optimises for human authoring, not for LLM injection. There is no forcing function that makes the
LLM apply rules correctly unless the schema is designed with the query path in mind.

**Consequences:**
- `/architect` gives confident but rule-ignoring advice in Phase 5 integration tests
- The rules become decoration — the LLM uses its training data instead, defeating the purpose of
  having a local rules engine
- No test in `skill_runner.py` can catch this because tests check text format, not whether a rule
  was actually applied

**Prevention:**
1. Design the schema for injection. Each rule must be a self-contained sentence the LLM can apply
   as a filter. Prefer: `"if_context_matches": "solo developer, hobby, no funding"` as a
   classification tag, not a prose condition. Tag-based matching is more reliable than prose-matching.
2. Keep rules short. Each rule entry must fit in one LLM "attention unit" — aim for 50-word
   `recommendation` fields. Move elaboration to a `details` field that is only injected on demand.
3. Index rules by `category` (e.g., `"tech_stack"`, `"testing"`, `"architecture"`) and inject only
   the relevant category into the LLM context for a given question. Injecting all 20-30 rules at
   once risks exceeding useful attention budget.
4. Add a `test_scenario` field to each rule: the scenario where this rule should fire and the
   expected keyword in the response. This becomes your Phase 5 test oracle.

**Detection:** During Phase 5 integration test: inject all 30 rules into a prompt alongside a
specific user scenario. Check whether the LLM response quotes or references a specific rule ID.
If it never quotes rule IDs, the rules are being ignored.

---

### Pitfall 2: Copilot-Generated Rules Have Systematic Bias Toward Mainstream Use Cases

**Domain:** Copilot as rule source (Question 5)
**Phase:** Phase 4 (occurs during Task 2.1-01 rule bootstrapping)

**What goes wrong:** Copilot GPT-5.4 (or any frontier LLM used as a researcher) has training data
heavily skewed toward well-documented, public, mainstream software engineering advice. When asked
"overengineering patterns in indie/hobby projects" or "solo-dev constraints", the generated rules
will systematically:

1. **Repeat generic advice:** Rules that are already in every "clean code" or "YAGNI" article,
   not OmniGraph-Vault-specific or AI-tool-specific guidance. Example: "Don't over-abstract early"
   appears in >90% of such rule sets and adds no signal for `/architect`.

2. **Assume VC-funded startup context:** Rules about scalability, team workflows, and CI/CD pipelines
   that apply to funded startups, not solo researchers. When injected into `/architect`, these rules
   will steer advice toward over-engineering for a single-user local tool.

3. **Miss Chinese developer ecosystem nuance:** Copilot's English-language training underweights
   WeChat/Zhihu/GitHub Chinese community patterns. KOL articles ingested into this KB are Chinese-
   language AI content. Rules about "community-validated tools" will reference Western ecosystems
   (Hacker News, Product Hunt) while the user's context is Chinese AI development.

4. **Overstate certainty:** Copilot generates rules with confident phrasing. There is no mechanism
   to distinguish "we know this is true" from "this sounds plausible." Without weighting or
   confidence annotation, all 20-30 rules carry equal apparent authority in the LLM prompt.

**Why it happens:** Copilot optimises for plausible-sounding output, not for the user's specific
context. The researcher prompt is too open-ended to elicit system-specific guidance.

**Consequences:**
- Rules engine gives advice indistinguishable from generic LLM advice without a KB
- `/architect` Propose mode returns correct-looking but contextually wrong recommendations for
  Chinese-market or solo-researcher personas
- After integration, developer cannot tell whether `/architect` is using the rules or just drawing
  from Gemini's training data

**Prevention:**
1. Before running Copilot, write 3 concrete example scenarios the rules must distinguish:
   (a) "solo researcher with local tools", (b) "startup CTO with 3 engineers", (c) "indie hacker
   with $0 budget". Use these as the evaluation frame when reviewing generated rules.
2. After generation, apply a deduplication + quality filter: discard any rule that Gemini could
   derive without looking at the rules (i.e., it is just training data). Keep only rules that
   reference specific tools, constraints, or context (AI agent tools, WeChat/Zhihu ecosystem, Gemini
   vs Claude trade-offs, LightRAG-specific patterns).
3. Add a `source` field to each rule: `"copilot"`, `"kol_article"`, or `"codebase_experience"`.
   Rules from KOL articles (Phase 4 KB) should be weighted higher than Copilot-generated ones.
4. Cap Copilot-derived rules at 50% of total. The remaining 50% must come from ingested KB content
   (KOL articles + GitHub README + your own decisions documented in CLAUDE.md).
5. Write 3 "adversarial" `/architect` test cases in Phase 5 that specifically check whether rules
   override generic Gemini advice. If generic advice wins, the rules are not working.

**Detection:** After Phase 4 rule bootstrapping, do a "rules audit": for each rule, ask "could
Gemini answer this without the rule?". If yes for >60% of rules, the rule set has been captured
by generic advice.

---

### Pitfall 3: LightRAG Entity Collision When Batch-Ingesting 50+ GitHub Repositories

**Domain:** Batch GitHub ingestion (Question 2)
**Phase:** Phase 4 (during KB population Task 2.1-03)

**What goes wrong:** When 50+ GitHub repositories are ingested sequentially into LightRAG, many
share the same entity names: "Python", "API", "agent", "LLM", "memory", "vector database",
"embedding". LightRAG builds a knowledge graph by extracting entity-relationship triples. When the
same entity name appears hundreds of times across dozens of READMEs, LightRAG either:
(a) merges all occurrences into one super-entity with contradictory attributes, or
(b) creates duplicate entity nodes with the same name, degrading retrieval quality.

The existing `canonical_map.json` mechanism (async batch processor) is designed for
cross-article canonicalization, but it was designed for article-scale ingestion (5-10 items),
not batch ingestion of 50+ repositories with highly overlapping terminology.

**Why it happens:** GitHub AI tool READMEs are written with similar vocabulary. The entity
extraction (Gemini via LightRAG) will extract "LLM" as an entity from every repository that
mentions LLMs. After 50 ingestions, "LLM" becomes a massively over-connected hub node with
relationships to 50+ tools, degrading retrieval specificity.

**Consequences:**
- Queries like "what do I know about LangChain" retrieve content about every tool that mentions
  "LangChain" anywhere, not just LangChain-specific content
- Hub entities ("Python", "API", "agent") accumulate so many edges that they create noise in
  every query result
- `canonical_map.json` grows large and the simple string-replace canonicalization
  (`kg_synthesize.py` lines 56-58) becomes increasingly incorrect (already flagged as fragile
  in CONCERNS.md) at scale

**Prevention:**
1. Batch in groups of 10-15, not all at once. After each group, run a test query to verify
   retrieval quality is still acceptable. Stop if quality degrades.
2. Tag each ingested document with its source repository URL as metadata. LightRAG does not
   natively support document-level metadata in retrieval, but you can prepend a source header
   to the content: `"# Source: github.com/org/repo\n\n<readme content>"`. This gives the LLM
   retrieval context to distinguish sources.
3. Before ingestion, strip boilerplate from READMEs: badges, install instructions (`pip install`
   blocks), license text, and contributor tables. These add token cost without knowledge value
   and contribute noise entities.
4. Focus entity extraction on differentiating facts: what the tool does, what it is comparable
   to, what constraints it has. Consider writing a pre-processing step that extracts only the
   "Description" and "Features" sections of each README.
5. After ingestion, run a test query: "What is unique about [tool X] compared to [tool Y]?"
   If the answer is generic, entity collision has degraded the graph.

**Detection:** After ingesting 15 repositories, run `list_entities.py`. Count how many entities
have >20 connections. Hub entities (>50 connections) are a sign of collision. If "Python" has
>100 connections, the entity namespace is already polluted.

---

### Pitfall 4: GitHub API Rate Limiting Silently Breaks Mid-Batch Ingestion

**Domain:** Batch GitHub ingestion (Question 2)
**Phase:** Phase 4 (during KB population Task 2.1-03)

**What goes wrong:** The confirmed approach for GitHub ingestion is the GitHub REST API via
`requests` library in a new `ingest_github.py` script (Graphify MCP is NOT available). GitHub
REST API enforces rate limits: 60 requests/hour for unauthenticated, 5,000/hour for authenticated.
For 50-100 repositories, each repository requires at minimum:
- 1 request to get repo metadata
- 1 request to fetch README content
- Optional: N requests for additional files (CHANGELOG, docs/, etc.)

At 60 unauthenticated requests/hour, 50 repos = 100+ requests = fails in the first hour.
At 5,000 authenticated requests/hour, 50 repos is fine — but the `ingest_github.py` script
may not handle the 403/429 response codes that signal rate limit exhaustion.

The existing ingestion pipeline (`ingest_wechat.py`) has retry logic only for 503 errors (line 179
in `skill_runner.py` — Gemini retries), and has no retry logic for GitHub rate limits. If
`ingest_github.py` is written following the existing pattern, rate limit errors will cause a
silent crash mid-batch.

**Why it happens:** No GitHub API integration exists yet; `ingest_github.py` will be written fresh
in Phase 4. Without explicitly building rate-limit handling, it will be omitted (consistent with
existing ingestion scripts which have minimal retry logic per CONCERNS.md).

**Consequences:**
- Batch ingestion fails silently at repo 30/50 with a 403 response
- No `.processed` marker pattern exists for GitHub repos (unlike `entity_buffer/`), so there is
  no idempotency — a re-run starts from scratch
- `entity_registry.json` (GitHub URL → entity ID) is partially populated, making it an unreliable
  source of truth

**Prevention:**
1. Use authenticated requests. Set `GITHUB_TOKEN` in `~/.hermes/.env` and add it to the
   `Authorization: Bearer <token>` header. This raises the rate limit to 5,000/hour. Add
   `GITHUB_TOKEN` to the `config.py` constant list alongside `GEMINI_API_KEY`.
2. Implement the `.processed` marker pattern from `entity_buffer/` for GitHub ingestion:
   maintain a `github_ingested.json` manifest (atomic write — same pattern as `canonical_map.json`).
   Check the manifest before each repo to skip already-processed repos.
3. Add explicit rate-limit handling: check `X-RateLimit-Remaining` response header; if it falls
   below 10, sleep until `X-RateLimit-Reset`.
4. Test with 5 repos first, then 20, then 50. Each increment should produce a test query that
   returns multi-repository results.

**Detection:** Check `X-RateLimit-Remaining` header in the first GitHub API response. If 0 or
unauthenticated, stop before starting the batch.

---

### Pitfall 5: Storage Explosion from Unfiltered GitHub README + Image Ingestion

**Domain:** Batch GitHub ingestion, storage (Question 2)
**Phase:** Phase 4

**What goes wrong:** LightRAG stores embeddings, entity relationships, and raw document chunks in
`~/.hermes/omonigraph-vault/lightrag_storage/`. The current KB contains 5-10 articles.
Adding 50-100 GitHub repositories will multiply storage by 5-10x minimum. The risks:
1. The embedding dimension is 768 (gemini-embedding-001). Each document chunk generates one vector.
   A typical GitHub README (1,000-3,000 words) generates 5-20 chunks. 100 repos × 20 chunks ×
   768 floats × 4 bytes = ~6MB for embeddings alone. The graph edges and entity tables will be
   comparable. Total: ~20-50MB additional. On Windows with limited SSD, this is manageable, but
   LightRAG's graph structure may have higher constant factors — verify before starting.
2. If `ingest_github.py` downloads images from GitHub READMEs (badges, screenshots, diagrams),
   the `~/.hermes/omonigraph-vault/images/` directory will grow rapidly. GitHub badges alone are
   hundreds of PNG/SVG files per repository.
3. The existing `entity_buffer/` grows with each ingestion. 100 repos × average 20 extracted
   entities = 2,000 entity buffer files. The `cognee_batch_processor.py` processes these
   sequentially (flagged in CONCERNS.md as a performance bottleneck) — at ~100ms per file, this is
   a ~3-minute blocking operation.

**Prevention:**
1. Strip badge images from READMEs before ingestion. They carry no knowledge value. Use a regex
   to remove `[![...](badge.svg)](link)` patterns before passing to `LightRAG.ainsert()`.
2. Set a maximum README size (e.g., 10,000 tokens) before ingestion. Repositories with very long
   READMEs (documentation repos, monorepos) should be ingested selectively by section, not fully.
3. Skip image download for GitHub READMEs unless the image is a diagram (not a badge/logo). Add a
   content-type filter: only download images with `image/png` MIME type and >5KB size.
4. Run a disk usage check before and after each batch of 10 repos: `du -sh ~/.hermes/omonigraph-vault/`.
   Set a budget (e.g., 500MB cap).

---

### Pitfall 6: /architect Skill Mode Confusion — Propose vs Query vs Ingest Routing Errors

**Domain:** Multi-mode LLM skill routing (Question 3)
**Phase:** Phase 5 (primary), Phase 4 (must be considered when writing test cases)

**What goes wrong:** The `/architect` skill has three modes — Propose (multi-turn conversation),
Query (single-turn KB lookup), and Ingest (URL/doc ingestion). These modes are distinguished by
the agent's interpretation of natural language intent. The routing decision is made by the LLM
reading the SKILL.md decision tree, not by code logic.

The three critical failure modes for `/architect`:

**Mode 1: Propose → Query confusion**
User says "what framework should I use for my agent?" — ambiguously either a KB query (what does
OmniGraph-Vault know about agent frameworks?) or a Propose-mode conversation (the skill should ask
clarifying questions about the user's context before recommending). If the skill routes to Query
mode, it dumps a synthesis report without the GSD:DISCUSS conversation. The user gets raw KB
content without architecture guidance through the rules engine.

**Mode 2: Query → Ingest confusion**
User says "add LangChain to my architect knowledge base" — ambiguously either Ingest mode (ingest
the LangChain GitHub repo) or a Query about something called "architect knowledge base". The word
"add" should trigger Ingest but the phrase "architect knowledge base" could confuse the routing.

**Mode 3: Propose → Ingest escalation**
During a Propose-mode conversation (multi-turn), the user shares a GitHub URL "here is what I'm
building on: github.com/X/Y" as context for the recommendation. The skill should NOT auto-ingest
the URL — it should use it as conversational context. But if the SKILL.md decision tree is not
explicit about this, the LLM may route to Ingest mode mid-conversation.

**Why it happens:** These three modes are semantically close. "What should I use for X?" can be
Propose or Query. "Add X" can be Ingest or Query filter. The SKILL.md decision tree must
disambiguate them with explicit boundary conditions, not general intent descriptions.

The existing `omnigraph_ingest` and `omnigraph_query` skills already demonstrate the pattern
correctly — they have explicit "When NOT to Use" sections. But the `/architect` skill is more
complex because it has three internal modes plus boundaries with two other skills.

**Prevention:**
1. Design the SKILL.md decision tree for `/architect` with explicit mode-locking: the first
   message determines the mode; subsequent messages in the same conversation do not re-trigger
   routing. This prevents Mode 3 (Propose → Ingest escalation).
2. Write the routing rules as syntactic pattern-matching, not semantic intent:
   - Propose mode: user asks a "what should I" / "how should I" / "which X for my Y" question
     with no specific KB query intent
   - Query mode: user says "what do I know about", "search", "find", or names a specific tool
   - Ingest mode: user provides a GitHub URL or says "add this", "ingest this", "learn about"
3. Add a `mode_lock` concept to the multi-turn test harness (Phase 5): after the first turn
   establishes Propose mode, subsequent turns must not retrigger mode detection.
4. Write 3 "boundary" test cases in Phase 5: one for each of the three failure modes above.
   These are harder to pass than the golden-path tests and will reveal routing ambiguity.

**Detection:** In `skill_runner.py` multi-turn tests, include a second turn that looks like an
Ingest trigger but is actually conversational context. If the response includes `ingest.sh` or
`scripts/architect.sh --ingest`, Mode 3 is occurring.

---

## Moderate Pitfalls

---

### Pitfall 7: skill_runner.py Multi-Turn Support Breaks Backward Compatibility With Existing Tests

**Domain:** Multi-turn conversation support (Question 4)
**Phase:** Phase 5 (Task 2.2-03)

**What goes wrong:** The current `skill_runner.py` `TestCase` dataclass has `input: str` (single
string). The plan calls for enhancing it to support `inputs: list[str]` for multi-turn. The most
likely implementation approach is to rename `input` to `inputs` and accept both `str` (old) and
`list[str]` (new). If the rename is done without a backward-compatibility shim, all existing
19 test cases in `test_omnigraph_ingest.json` and `test_omnigraph_query.json` (which use `"input"`)
will break with a `TypeError`.

The existing test files use the `"input"` key. `TestCase(**c)` at line 216 of `skill_runner.py`
will fail with `TypeError: __init__() got an unexpected keyword argument 'input'` if `input` is
removed and replaced with `inputs`.

**Why it happens:** The existing test JSON uses `"input"` as the key name. Python dataclass
construction with `**c` is strict — unknown or missing fields cause immediate failures.

**Consequences:**
- After the enhancement, `python skill_runner.py skills/ --test-all` fails immediately for
  the two existing skills before even reaching the new `/architect` tests
- Developer either (a) patches all existing test files (risky, introduces errors) or
  (b) rolls back the enhancement (defeats the purpose)

**Prevention:**
1. Use a field alias or union type in the `TestCase` dataclass:
   ```python
   @dataclass
   class TestCase:
       description: str
       input: str = ""          # backward compat — old single-turn tests
       inputs: list[str] = field(default_factory=list)  # new multi-turn
       ...
   ```
   In the test runner, treat `input` as `inputs[0]` if `inputs` is empty:
   ```python
   def _get_inputs(case: TestCase) -> list[str]:
       return case.inputs if case.inputs else [case.input]
   ```
2. Do NOT rename the existing field. Add the new field alongside it.
3. Write one test case that mixes old `"input"` format and new `"inputs"` format in the same
   JSON file to verify both work together.
4. The success criterion for Task 2.2-03 must include: "all existing 19 tests still pass after
   enhancement".

**Detection:** After the enhancement, run `python skill_runner.py skills/omnigraph_ingest
--test-file tests/skills/test_omnigraph_ingest.json` before writing any new tests. If it fails,
fix backward compat first.

---

### Pitfall 8: Multi-Turn Context Leakage Between Test Cases

**Domain:** Multi-turn conversation support (Question 4)
**Phase:** Phase 5

**What goes wrong:** Multi-turn test execution sends all turns of a single test case in one
Gemini API call using a `contents` list (conversation history). If the test runner reuses the same
Gemini client session state or passes accumulated history from one test case into the next, context
leaks between tests.

The current `call_gemini()` in `skill_runner.py` (line 153) takes a single `user_message: str`.
For multi-turn, it must accept a `contents: list` (Gemini chat format). The current implementation
creates a new `genai.Client` object on each call — this avoids session state leakage. But if the
multi-turn enhancement reuses a chat session object across test cases (a common simplification), the
second test case starts with the conversation history from the first.

**Why it happens:** Gemini `genai.Client.chats.create()` returns a persistent chat object that
accumulates history. If this object is passed between test cases for efficiency, context leaks.

**Consequences:**
- Test case 2 of a multi-turn suite gets influence from test case 1's conversation
- Tests appear to pass individually but fail when run together (`--test-all`)
- Flaky tests: results depend on test execution order

**Prevention:**
1. Create a fresh Gemini chat session (or equivalently, build a fresh `contents` list) for each
   `TestCase`, not for each turn. The session is per-test-case, not shared across cases.
2. In `run_test_case()`, build the `contents` list by appending each turn:
   ```python
   contents = []
   for turn_input in inputs:
       contents.append({"role": "user", "parts": [turn_input]})
       response = call_gemini_multi(system_prompt, contents)
       contents.append({"role": "model", "parts": [response]})
   ```
   Each `TestCase` gets its own `contents = []` starting point.
3. Add a multi-turn test case where turn 2 explicitly contradicts turn 1 context. If the response
   to turn 2 is correct (uses turn 2 context), context handling is correct. If it uses turn 1
   context, there is leakage.

**Detection:** Run the test suite twice with test cases in reversed order. If results differ, there
is ordering-dependent context leakage.

---

### Pitfall 9: rules_engine.json + kg_synthesize.py Integration — Rules Injected After Context Window is Saturated

**Domain:** Rules engine + kg_synthesize.py integration (Question 6)
**Phase:** Phase 5 (integration of Phase 4 rules engine with Phase 4 KB synthesis)

**What goes wrong:** `kg_synthesize.py` builds its prompt by concatenating: historical Cognee
context + custom prompt + LightRAG graph retrieval results. When the `/architect` skill adds the
rules engine, the combined prompt becomes:

```
[system preamble] +
[historical Cognee context (variable)] +
[rules_engine.json content (20-30 rules = ~2,000 tokens)] +
[LightRAG graph retrieval results (500-2,000 tokens per query)] +
[user query]
```

With 20-30 rules × 50 words each = ~1,500 tokens for rules alone. If LightRAG retrieves a rich
multi-document result (common for "best practices" queries), the total prompt can exceed 4,000-6,000
tokens. Gemini 2.5 Flash has a large context window, so this will not cause an API error — but the
effective attention budget for rules is diluted by the large graph context. The LLM tends to weight
recent tokens more heavily; rules injected before graph context get deprioritized.

Additionally, `kg_synthesize.py`'s current architecture has no injection point for rules. The
function signature is `synthesize_response(query_text: str, mode: str)` — there is no `rules`
parameter. Adding rules injection means modifying `kg_synthesize.py`, which risks breaking the
existing `omnigraph_query` skill if the parameter addition is not backward-compatible.

**Why it happens:** `kg_synthesize.py` was designed for KB-only synthesis. The rules engine is
being bolted on in Phase 5. The integration point was not designed in Phase 4.

**Consequences:**
- Rules are injected but have diminishing effect in long-context prompts
- Modifying `kg_synthesize.py` signature breaks `omnigraph_query` skill test compatibility
- Developer discovers the integration problem only during Phase 5, requiring a Phase 4 rework

**Prevention:**
1. In Phase 4, design `kg_synthesize.py` with the rules injection point in mind. Add an optional
   `rules: list[dict] | None = None` parameter now, so Phase 5 only needs to pass data rather than
   redesign the function.
2. Inject rules AFTER the graph context, not before, so they are closer to the generation point
   in the LLM's attention window.
3. Inject only the rules that match the query category (filter by `category` field), not all rules.
   This keeps the rules injection to 5-8 rules (~400 tokens) rather than all 30.
4. Write a Phase 5 integration test that checks the response contains a specific
   `dont_use` item from a known rule that applies to the test scenario. If it does not appear,
   rule injection is not working.

**Detection:** During Phase 5 testing, inject a rule with an unusual, distinctive `dont_use` value
(e.g., `"dont_use": ["frameworkX_that_doesnt_exist"]`) into the rules engine. If `/architect` never
mentions it when the relevant scenario is triggered, rules are not reaching the generation step.

---

### Pitfall 10: entity_registry.json Becomes a Single Point of Failure for KB Population

**Domain:** Batch GitHub ingestion (Question 2)
**Phase:** Phase 4

**What goes wrong:** The plan calls for `entity_registry.json` (GitHub URL → entity ID mapping).
This file is the only record linking each GitHub repository to its corresponding LightRAG entity.
If it is partially written (script crashes mid-batch), corrupted (concurrent writes from a retry
run), or lost, there is no way to re-establish which repositories are already in the KB without
re-reading all of LightRAG's internal graph storage.

The existing `canonical_map.json` uses atomic write (tmp → rename), but there is no specification
for `entity_registry.json` write safety. The `ingest_github.py` script does not exist yet — it
will be written fresh in Phase 4 without established write-safety conventions unless they are
explicitly required.

**Why it happens:** The entity_registry.json requirement is stated in PROJECT.md as a goal without
specifying write semantics. New scripts written quickly tend to omit atomic write patterns unless
the developer explicitly remembers to apply the pattern.

**Prevention:**
1. Apply the same atomic write pattern as `canonical_map.json`: always write to `entity_registry.json.tmp`
   then `os.rename()`. Document this requirement in the Phase 4 plan task description.
2. Design `entity_registry.json` as an append-only log, not a full-rewrite file. Append a new
   entry after each successful repo ingestion. This minimises the write window and makes
   partial-batch recovery safe.
3. Add a `"status"` field: `{"url": "...", "entity_id": "...", "status": "indexed", "indexed_at": "..."}`.
   On restart, skip entries with `status: "indexed"` — same idempotency pattern as `.processed` markers.

---

### Pitfall 11: GSD:DISCUSS Pattern Over-Engineering the Conversation Flow

**Domain:** Rules engine over-engineering (Question 1), multi-mode routing (Question 3)
**Phase:** Phase 4 (pattern design), Phase 5 (implementation)

**What goes wrong:** The GSD:DISCUSS pattern (Task 2.2-01) is a 4-step multi-turn conversation
flow: Default Guess → Question 1 → Question 2 → Output. This is an elegant design on paper.
In practice, the 4-step structure is over-specified for an LLM skill:

1. The LLM may collapse steps 2 and 3 into a single message ("I'll ask both questions at once")
   because nothing prevents it. The SKILL.md can specify the flow, but the LLM optimises for
   helpfulness, not compliance with a rigid conversation script.
2. If the user answers "yes" to the Default Guess at step 1, the flow should short-circuit to
   Output. The SKILL.md must explicitly handle this case, otherwise the LLM forces the user
   through 3 more steps even when the answer is already obvious.
3. The multi-turn test harness must encode the exact expected flow (turn 1 = default guess,
   turn 2 = user confirms, turn 3 = output). If the LLM produces the output in turn 2 (skipping
   step 3 confirmation), the test fails even though the behavior is actually correct.

**Prevention:**
1. Design the GSD:DISCUSS pattern with explicit branch conditions:
   - If user says "yes"/"correct"/"that's right" at step 1 → skip to Output immediately
   - If user gives more details at step 1 → treat as partial answer to step 2 questions
   - Only require the full 4 steps if the user provides no context at all
2. Write 3 test scenarios: (a) user confirms at step 1 (short circuit), (b) user gives full
   context at step 1 (collapse all questions), (c) user gives no context at all (full 4-step flow).
3. The `expect_final` check (checking only the last response) in multi-turn tests must be flexible
   enough to accept output in turn 2 or turn 4. Avoid encoding a specific turn number as the
   expected output turn.

---

## Minor Pitfalls

---

### Pitfall 12: ingest_github.py Missing the `canonical_map.json` Word-Boundary Bug

**Domain:** Integration of GitHub ingestion with existing kg_synthesize.py (Question 6)
**Phase:** Phase 4

**What goes wrong:** `kg_synthesize.py` applies `canonical_map.json` using simple string
replacement (flagged in CONCERNS.md as fragile). At 5-10 articles, this is a tolerable risk.
After ingesting 50+ GitHub repositories, `canonical_map.json` will have hundreds of entity
canonical mappings. The probability of a destructive replacement (e.g., replacing "AI" inside
"FAIL", or replacing "Lang" inside "LangChain" when trying to map "Lang" → "Language") increases
linearly with the number of entries.

**Prevention:**
The CONCERNS.md already identifies the fix: use regex with word boundaries.
Apply this fix in Phase 4 BEFORE KB population, not after. Once 50+ repos are ingested and
canonical_map.json has hundreds of entries, debugging spurious replacements is extremely hard.

This is a one-line fix (`re.sub(r'\b' + re.escape(raw) + r'\b', canonical, query_text)`)
that must be done in Phase 4 as a prerequisite to bulk ingestion, not treated as Phase 5 cleanup.

---

### Pitfall 13: Flaky skill_runner.py Tests Due to LLM Temperature Variation

**Domain:** Test harness reliability (Question 4)
**Phase:** Phase 5

**What goes wrong:** `skill_runner.py` uses `temperature=0.1` for Gemini calls (line 168). This
is low but not zero, and Gemini 2.5 Flash does not guarantee deterministic output even at
temperature=0. Test cases with `expect_contains` checks pass 9 times out of 10 but fail
intermittently because the LLM paraphrases the expected keyword.

For example, a test might `expect_contains: ["ingest.sh"]`. The LLM might output
`"run the ingestion script"` instead of `"ingest.sh"`. At temperature=0.1, this variant appears
~5-10% of the time. As the test suite grows to 28 cases (9 ingest + 10 query + 9 architect),
running the full suite has ~40-50% probability of at least one flaky failure.

The multi-turn tests added in Phase 5 amplify this: each turn has independent temperature noise,
so a 3-turn test has 3× the flakiness surface.

**Prevention:**
1. For critical routing tests, make `expect_contains` match multiple acceptable phrasings:
   `"expect_contains": ["ingest.sh", "ingest script", "ingest.sh"]` (use OR semantics in the checker).
2. Keep temperature at 0.1 but document that the test suite should be run 2-3 times to confirm
   a failure is real, not flaky.
3. For the final integration validation (Phase 5 Task 2.2-05), run `--test-all` 3 times and
   require 3/3 clean runs before declaring the milestone complete.
4. Add `temperature: 0` as an option to `skill_runner.py` for CI-style deterministic runs
   (accepting that Gemini does not guarantee it).

---

### Pitfall 14: `/architect` SKILL.md Bloat From 3-Mode + Rules + GSD:DISCUSS Pattern

**Domain:** Multi-mode skill design (Question 3), skill maintainability
**Phase:** Phase 5

**What goes wrong:** The v1.1 PITFALLS.md identified SKILL.md bloat as a moderate pitfall at
80-100 lines. The `/architect` SKILL.md has a much higher inherent complexity: 3 decision trees
(Propose/Query/Ingest) + GSD:DISCUSS 4-step flow + rules engine reference + error handling for
all 3 modes + output format specifications for each mode. The plan calls for 300-400 lines.
The v1.1 pitfall analysis showed that 100-line skills are already at the attention boundary.
A 300-line SKILL.md is 3× over the safe limit.

**Prevention:**
1. Keep the SKILL.md body under 100 lines. The body contains routing logic only.
2. Move the GSD:DISCUSS conversation protocol to `references/discuss-protocol.md`.
3. Move rules engine guidance to `references/rules-guide.md`.
4. Move Ingest-mode instructions to `references/ingest-instructions.md`.
5. Use Level 2 loading: the skill body references these files explicitly, and the agent loads
   them on demand via `skill_view(name, path)`.
6. The SKILL.md frontmatter description must be under 200 words (SkillHub pushy format).

---

## Phase-Specific Warnings

| Phase / Task | Likely Pitfall | Mitigation |
|--------------|----------------|------------|
| Phase 4 Task 2.1-01: Copilot rule bootstrap | Rules are generic, not system-specific | Cap Copilot at 50% of rules; audit with adversarial test |
| Phase 4 Task 2.1-02: rules_engine.json design | Schema not queryable by LLM | Tag-based conditions, short recommendations, `test_scenario` field |
| Phase 4 Task 2.1-02: rules_engine.json design | No rules injection point in kg_synthesize.py | Add optional `rules` parameter NOW, before Phase 5 |
| Phase 4 Task 2.1-03: GitHub batch ingestion | GitHub rate limiting mid-batch | Authenticate, check `X-RateLimit-Remaining`, pause on exhaustion |
| Phase 4 Task 2.1-03: GitHub batch ingestion | Entity collision from shared vocabulary | Batch 10-15 at a time; add source headers; strip boilerplate |
| Phase 4 Task 2.1-03: GitHub batch ingestion | entity_registry.json corruption | Atomic write; append-only; status field for idempotency |
| Phase 4 Task 2.1-03: GitHub batch ingestion | Storage explosion from images/badges | Strip badge images; cap README size; skip images under 5KB |
| Phase 4 Task 2.1-03: KB population | canonical_map word-boundary bug at scale | Fix `re.sub` word boundary BEFORE bulk ingestion |
| Phase 5 Task 2.2-01: GSD:DISCUSS design | Over-specified 4-step flow | Add short-circuit for "yes" at step 1; test collapse scenarios |
| Phase 5 Task 2.2-02: /architect SKILL.md | 300-line bloat degrades routing | Hard cap at 100 lines; offload to references/ |
| Phase 5 Task 2.2-02: /architect routing | Propose vs Query vs Ingest confusion | Syntactic routing rules; explicit mode-lock; boundary test cases |
| Phase 5 Task 2.2-03: skill_runner enhancement | `input` rename breaks 19 existing tests | Add `inputs` alongside `input`; never rename existing field |
| Phase 5 Task 2.2-03: multi-turn context | Context leakage between test cases | Fresh `contents = []` per TestCase; test with reversed order |
| Phase 5 Task 2.2-04: architect test cases | Flaky expect_contains at temperature 0.1 | Multi-phrasings in expect_contains; require 3/3 clean runs |
| Phase 5 Task 2.2-05: integration | Rules ignored after long graph context | Inject rules AFTER graph context; filter by category |

---

## Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Copilot bias in rules | HIGH | Well-documented LLM training data skew toward mainstream advice; corroborated by the 3 Copilot prompts in SIMPLE-GUIDE which are open-ended enough to produce generic output |
| rules_engine.json LLM queryability | MEDIUM | First-principles reasoning about LLM attention; no direct LightRAG/rules-injection experiment in codebase |
| GitHub API rate limits | HIGH | GitHub REST API rate limits are documented facts; the lack of retry logic in existing scripts confirmed in CONCERNS.md |
| Entity collision in LightRAG batch ingest | MEDIUM | Inferred from LightRAG entity extraction behavior; no prior large-batch evidence in this codebase |
| Storage explosion | MEDIUM | Estimated from embedding dimensions and file count; not benchmarked on this system |
| /architect mode routing errors | HIGH | Pattern directly confirmed by existing trigger collision pitfall from v1.1; complexity multiplied by 3 modes |
| skill_runner backward compat | HIGH | Direct code evidence: TestCase uses `input: str` (line 70); existing test JSON uses `"input"` key; `TestCase(**c)` is strict |
| Multi-turn context leakage | MEDIUM | Common pattern failure in multi-turn test harness design; not yet code-confirmed since the enhancement doesn't exist |
| rules + kg_synthesize integration | MEDIUM | Inferred from function signature analysis (line 48, kg_synthesize.py); no injection point exists yet |
| entity_registry.json write safety | HIGH | Pattern confirmed by existing canonical_map.json atomic write requirement; new script has no such requirement yet |
| SKILL.md bloat at 300 lines | HIGH | v1.1 pitfall confirmed at 100 lines; 300-line target is 3× the identified limit |

---

## Sources

- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\codebase\CONCERNS.md` — canonical_map fragility,
  bare excepts, entity_buffer idempotency, rate limiting, sequential batch processor (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skill_runner.py` — TestCase dataclass structure (input: str,
  line 71), Gemini temperature=0.1 (line 168), test execution architecture (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\kg_synthesize.py` — synthesize_response signature (line 48),
  canonical_map simple string replace (lines 56-62), no rules injection point (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\MILESTONE-2-SIMPLE-GUIDE.md` — rules JSON schema
  from plan, Copilot prompts, GSD:DISCUSS 4-step flow specification (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\PROJECT.md` — entity_registry.json requirement,
  active requirements for v2.0, platform constraints (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE.md` — Graphify MCP NOT available confirmed;
  GitHub REST API via requests confirmed as approach (HIGH confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skills\omnigraph_ingest\SKILL.md` — trigger phrase patterns
  for comparison with /architect routing design (MEDIUM confidence)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\skills\test_omnigraph_ingest.json` — existing test
  JSON format uses `"input"` key (HIGH confidence, backward compat analysis)
- `.planning\research\PITFALLS.md` (v1.1) — trigger collision, SKILL.md bloat patterns confirmed
  in Phase 2 (HIGH confidence, prior validated research)
