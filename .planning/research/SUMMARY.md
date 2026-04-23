# Project Research Summary

**Project:** OmniGraph-Vault v2.0 Knowledge Infrastructure MVP
**Domain:** Local knowledge graph + rules-engine overlay + multi-mode agent skill
**Researched:** 2026-04-23
**Confidence:** HIGH — all four research files grounded in actual source files, not external documentation

---

## Executive Summary

OmniGraph-Vault v2.0 extends a working v1.1 pipeline (LightRAG + Cognee + Gemini + Playwright CDP) with three new capabilities: a rules engine encoding 20-30 architecture heuristics, a populated knowledge base of 50+ GitHub AI tool repositories ingested via the GitHub REST API, and an `/architect` skill that combines those two data sources to give contextual architecture recommendations. The key insight from research is that **v2.0 requires zero new Python dependencies** — every feature can be built with the existing `requests`, `google-genai`, and stdlib `json` already in `requirements.txt`. The most significant technical decision confirmed is that Graphify MCP, previously referenced in planning documents as `--source graphify`, does not exist as an installable package and has no implementation in the codebase; it must be replaced by a purpose-built `ingest_github.py` script using the GitHub REST API.

The recommended implementation order is strictly driven by dependency chains: `config.py` constants patch first (2 lines), then `ingest_github.py`, then batch KB population in groups of 10-15 repos with test queries between batches, then `rules_engine.json` finalised with a human deduplication and quality audit, then the `omnigraph_architect` SKILL.md hard-capped at 100 lines with the GSD:DISCUSS protocol offloaded to `references/`, and finally `skill_runner.py` multi-turn support added alongside (not replacing) the existing `input` field. The synthesis engine `kg_synthesize.py` is **not modified** — rules injection happens at the shell layer in `architect.sh` by prepending rules text to the query string before the Python call.

The dominant risks are not architectural but quality risks: Copilot-bootstrapped rules will be generic unless explicitly audited, batch GitHub ingestion will produce entity collision in LightRAG unless batched carefully and source-tagged, and a 300-line SKILL.md will exceed the LLM's effective attention budget and degrade routing quality. All three risks have concrete, low-cost mitigations available before they become problems. The 300-line SKILL.md target in MILESTONE-2-SIMPLE-GUIDE.md is wrong and must be overridden to a 100-line hard cap.

---

## Key Findings

### Recommended Stack

No new libraries are needed. v2.0 is entirely buildable with the existing requirements.txt. The confirmed net-new artifacts are two Python scripts (`ingest_github.py`, `architect.py` invoked by `architect.sh`), two data files (`rules_engine.json`, `entity_registry.json`), two `config.py` constants (`GITHUB_TOKEN`, `ENTITY_REGISTRY_FILE`), and one skill directory (`skills/omnigraph_architect/`).

**Core technologies (existing, v2.0 usage confirmed):**

- `requests` — GitHub REST API calls in `ingest_github.py`; already in requirements.txt; 3-4 GET calls per repo
- `google-genai` — multi-turn conversation history in `skill_runner.py`; multi-turn via `contents` list is SDK-native since v0.3.x
- `lightrag-hku` — `rag.ainsert()` for GitHub repo content; same call site as article ingestion
- `cognee` — entity buffering path unchanged; same `entity_buffer/` mechanism used by `ingest_github.py`
- stdlib `json` + `os.rename()` — `rules_engine.json` loading and atomic `entity_registry.json` writes

**New environment variable:**

- `GITHUB_TOKEN` — optional flag but critical in practice; unauthenticated limit is 60 req/hr (insufficient for 50+ repos); authenticated raises to 5000/hr

**Eliminated from planning docs:**

- Graphify MCP — no Python package, no implementation, no `--source` flag in `ingest_wechat.py`; replaced by GitHub REST API per `OMNIGRAPH_VISION_Statement.md` specification

### Expected Features

**Must have (table stakes) — Phase 2.1:**

- `rules_engine.json` with 20-30 rules, schema: `id`, `condition`, `recommendation`, `dont_use`, `weight`, `tags`, `test_scenario` — without this, `/architect` Propose mode cannot fire
- 50+ GitHub AI tools indexed in LightRAG — Query mode returns empty without KB content
- `entity_registry.json` mapping GitHub URL to entity ID — prevents re-ingestion on repeat calls
- 5-10 KOL articles indexed — "best practices" queries need real-world evidence, not just docs
- Integration gate: `python query_lightrag.py "best practices for chatbot" hybrid` returns multi-source output before Phase 2.2 begins

**Must have (table stakes) — Phase 2.2:**

- `.planning/GSD_DISCUSS_PATTERN.md` documented before SKILL.md is written
- `skills/omnigraph_architect/SKILL.md` hard-capped at 100 lines with 3-mode decision tree
- GSD:DISCUSS 4-step protocol in `references/discuss-protocol.md` (Level 2 loading, not inline)
- `skills/omnigraph_architect/scripts/architect.sh` with mode-dispatch (`propose` / `query` / `ingest` as positional arg 1)
- `skill_runner.py` multi-turn: add `inputs: list[str]` field alongside (not replacing) existing `input: str` — backward compat with all 19 existing test cases is non-negotiable
- 9 test cases in `tests/skills/test_omnigraph_architect.json` (3 per mode); run `--test-all` 3 times and require 3/3 clean runs

**Should have (differentiators):**

- Rules persona-filtering by `tags` field (solo-dev / startup / researcher)
- `weight` field for priority-ordered recommendation output
- `entity_registry.json` duplicate guard in Ingest mode (check registry before calling `ingest.sh`)
- `expect_final` field in multi-turn `TestCase` (check assertions only on last turn's response)

**Defer to v2.x:**

- Rules + KB cross-reference in Propose mode (joining two data sources inside the LLM call — HIGH complexity)
- Auto-tagging ingested content by persona type
- `omnigraph_status` skill
- Streaming subprocess stdout from `architect.sh`
- Arbitrary URL ingestion beyond GitHub and WeChat/PDF

### Architecture Approach

v2.0 follows the established subprocess-as-contract pattern: the agent calls shell scripts, shell scripts call Python entry points, Python entry points call LightRAG/Cognee/Gemini. The critical architectural decision is that `kg_synthesize.py` is never modified — rules injection happens in `architect.sh` at the shell layer by prepending rules text to the `query_text` argument. This keeps the synthesis engine clean and prevents rules from contaminating the `omnigraph_query` skill's call path. The `architect.sh` dispatches on a positional mode argument (`propose` / `query` / `ingest`) using a `case` statement; mode detection is the agent's responsibility via the SKILL.md decision tree, not bash string parsing.

**Major components:**

1. `config.py` (modify) — add `ENTITY_REGISTRY_FILE` and `GITHUB_TOKEN`; 2-line additive change; prerequisite for everything else
2. `ingest_github.py` (new) — mirrors `ingest_wechat.py` structure; GitHub REST API via `requests` in executor; strips badges/boilerplate; prepends source header; writes `entity_registry.json` atomically after each repo
3. `rules_engine.json` (new) — 20-30 records; bootstrapped by Copilot, then human-audited; `test_scenario` field required on every rule
4. `skills/omnigraph_architect/` (new) — SKILL.md (100-line hard cap), `scripts/architect.sh` (mode dispatch), `references/discuss-protocol.md`, `references/rules-guide.md`
5. `skill_runner.py` (modify) — add `inputs: list[str]` and `expect_final: list[str]` to `TestCase`; add `history: list | None` to `call_gemini()`; fresh `contents = []` per `TestCase` to prevent context leakage between cases

### Critical Pitfalls

1. **Graphify MCP does not exist** — building against it would block Phase 2.1 entirely. Mitigation: `ingest_github.py` + GitHub REST API; confirmed viable by `OMNIGRAPH_VISION_Statement.md` and existing `requests` in requirements.txt.

2. **SKILL.md bloat at 300+ lines degrades routing quality** — v1.1 pitfalls confirmed 100-line threshold; 3-mode decision tree + GSD:DISCUSS + rules guidance pushes to 300-400 lines. Mitigation: hard cap at 100 lines; move GSD:DISCUSS protocol to `references/discuss-protocol.md`, rules guidance to `references/rules-guide.md` (Level 2 loading).

3. **`skill_runner.py` `input` field rename breaks 19 existing tests** — `TestCase(**c)` construction is strict; renaming `input` to `inputs` causes immediate `TypeError` on all existing test files. Mitigation: add `inputs: list[str]` as a new field alongside `input: str`; never rename the existing field; verify with `python skill_runner.py skills/omnigraph_ingest --test-file ...` before writing any new tests.

4. **LightRAG entity collision from batch GitHub ingestion** — 50+ repos share vocabulary ("Python", "API", "LLM", "agent"), creating over-connected hub nodes. Mitigation: ingest in groups of 10-15; prepend `# Source: github.com/org/repo` header to each document; run `list_entities.py` after each batch and count entities with >20 connections; strip badge images and `pip install` boilerplate before `ainsert()`.

5. **Copilot-generated rules captured by generic LLM advice** — rules bootstrapped by Copilot will repeat standard "YAGNI / no microservices" advice that Gemini already knows without the rules. Mitigation: cap Copilot-derived rules at 50% of total; add `source` field per rule; run adversarial audit ("could Gemini answer this without the rule?"); keep only rules that reference specific tools, constraints, or context.

6. **Multi-turn context leakage between test cases** — reusing a Gemini chat object across `TestCase` iterations causes history from case N to influence case N+1. Mitigation: build a fresh `contents = []` list per `TestCase`, not per turn; test by running the suite twice with cases in reversed order.

---

## Implications for Roadmap

Based on combined research, the dependency chain enforces a 4-phase structure. The internal ordering within each phase is tighter than the MILESTONE-2-SIMPLE-GUIDE.md task list implies.

### Phase 1: Foundation Patch (config.py + ingest_github.py)

**Rationale:** Everything downstream depends on these artifacts. `ingest_github.py` cannot import constants that don't exist; KB population cannot run without the script. This is a 1-2 hour task that unblocks all parallel work. The `canonical_map.json` word-boundary bug fix (`re.sub` with `\b` boundaries) must also land here — before bulk ingestion, not after. Debugging spurious string replacements in a 200-entry map after 50 repos are indexed is extremely difficult.

**Delivers:** `config.py` with `ENTITY_REGISTRY_FILE` and `GITHUB_TOKEN`; functional `ingest_github.py` with GitHub REST API, authenticated headers, `X-RateLimit-Remaining` check, source headers, README badge/boilerplate stripping, and atomic `entity_registry.json` writes; one-line `re.sub` word-boundary fix in `kg_synthesize.py`.

**Addresses:** Pitfall 4 (rate limiting), Pitfall 5 (storage explosion), Pitfall 10 (entity_registry.json write safety), Pitfall 12 (canonical_map word-boundary bug)

**Avoids:** Building against Graphify MCP

### Phase 2: Rules Engine Construction

**Rationale:** `rules_engine.json` is a standalone artifact with no code dependencies; it can be built in parallel with Phase 1. It must complete before `architect.sh` and SKILL.md are written, because the SKILL.md author needs to know the actual rule structure to write accurate routing instructions. The deduplication and quality audit is the gate, not the Copilot bootstrap.

**Delivers:** `rules_engine.json` with 20-30 rules passing the quality audit: less than 50% from Copilot; all rules have `test_scenario` fields; adversarial test shows at least 5 rules produce responses distinct from generic Gemini output without KB context; deduplication pass removes rules that overlap by more than 80%.

**Addresses:** Pitfall 1 (schema too rigid for LLM injection), Pitfall 2 (Copilot bias)

**Critical detail:** The `test_scenario` field on every rule is not optional — it becomes the Phase 4 test oracle. Without it there is no way to verify rules are being applied during `/architect` integration testing.

### Phase 3: KB Population

**Rationale:** Query mode of `/architect` is meaningless without KB content. This phase must complete and pass the integration gate before SKILL.md authoring begins. Batching discipline and quality monitoring between batches are the implementation constraints, not the ingestion logic itself.

**Delivers:** 50+ GitHub AI tools indexed, 5-10 KOL articles indexed, `entity_registry.json` populated, integration gate passing: `query_lightrag.py "best practices for chatbot" hybrid` returns multi-source output.

**Addresses:** Pitfall 3 (entity collision), Pitfall 4 (rate limiting), Pitfall 5 (storage explosion)

**Critical batching rule:** Groups of 10-15 repos maximum. After each group: run `list_entities.py` and count entities with >20 connections — if "Python" or "LLM" exceed 100 connections, pause and assess. Also run `python query_lightrag.py "What is unique about [last ingested tool]?"` — a generic answer signals entity collision has degraded quality.

### Phase 4: /architect Skill + Multi-Turn Testing

**Rationale:** All data and infrastructure prerequisites are complete. `GSD_DISCUSS_PATTERN.md` must be authored before SKILL.md authoring begins — this is a hard sequential dependency. `skill_runner.py` multi-turn enhancement can run in parallel with SKILL.md authoring since they touch different artifacts. Test cases require both SKILL.md and the updated runner.

**Delivers:** `.planning/GSD_DISCUSS_PATTERN.md`; `skills/omnigraph_architect/SKILL.md` (100-line hard cap); `scripts/architect.sh`; `references/discuss-protocol.md`; `references/rules-guide.md`; `skill_runner.py` multi-turn support; 9 architect test cases; all 28 tests passing (9/9 ingest + 10/10 query + 9/9 architect) on 3 consecutive clean runs.

**Addresses:** Pitfall 6 (mode routing), Pitfall 7 (backward compat), Pitfall 8 (context leakage), Pitfall 9 (rules context window), Pitfall 11 (GSD:DISCUSS over-engineering), Pitfall 13 (flaky temperature), Pitfall 14 (SKILL.md bloat)

**Task ordering within this phase:**

1. `GSD_DISCUSS_PATTERN.md` — document before writing SKILL.md
2. `skill_runner.py` multi-turn enhancement — can run in parallel with step 1
3. SKILL.md + `architect.sh` — requires GSD_DISCUSS_PATTERN.md to be finalised
4. 9 test cases — requires both SKILL.md and multi-turn runner
5. Integration validation: `--test-all` 3 times; require 3/3 clean runs

### Phase Ordering Rationale

- config.py before `ingest_github.py` because the script imports the constants at module load time
- `canonical_map` word-boundary fix before bulk ingestion because debugging spurious replacements at scale is extremely difficult and the fix is one line
- `rules_engine.json` construction can run in parallel with KB population since neither depends on the other
- `GSD_DISCUSS_PATTERN.md` before SKILL.md because the SKILL.md decision tree references the pattern by step number
- `skill_runner.py` multi-turn before test case authoring because tests cannot be validated without the runner
- KB population integration gate before SKILL.md authoring to ensure Query mode will function before committing to the skill design

### Research Flags

Phases likely needing research during planning:

- **Phase 4 (multi-turn `skill_runner.py`):** The Gemini `google-genai` multi-turn `contents` list API — exact parameter names for `types.Content` vs plain dicts — should be verified against the installed version with a context7 lookup before implementation to avoid a wasted debugging session.
- **Phase 3 (KB population), conditional:** If `list_entities.py` shows hub nodes with >100 connections after the first 10-repo batch, deeper research into LightRAG chunking strategies or `canonical_map.json` pre-seeding may be needed. This is a conditional flag — proceed normally and only investigate if the symptom appears.

Phases with standard patterns (skip research):

- **Phase 1 (config.py + ingest_github.py):** Fully specified in STACK.md and ARCHITECTURE.md. GitHub REST API endpoints are stable; atomic write pattern is established in the codebase.
- **Phase 2 (rules_engine.json):** Schema is fully specified in FEATURES.md. The work is content creation and auditing, not technical research.
- **Phase 4 (SKILL.md authoring):** Decision tree structure, frontmatter format, and `references/` layout are directly cloneable from existing `omnigraph_ingest` and `omnigraph_query` skills.

---

## Confidence Assessment

| Area | Confidence | Notes |
| ------ | ---------- | ------- |
| Stack | HIGH | All decisions traced to actual source files: requirements.txt, skill_runner.py, config.py, ingest_wechat.py. Graphify elimination confirmed by code absence analysis. |
| Features | HIGH | Feature list derived from MILESTONE-2-SIMPLE-GUIDE.md task breakdown and existing SKILL.md structure analysis. Backward-compat analysis is code-evidence based (TestCase dataclass at line 68-74). |
| Architecture | HIGH | All component boundaries and data flows traced to actual function signatures and file paths. `synthesize_response(query_text, mode)` confirmed at line 48 of kg_synthesize.py. |
| Pitfalls | HIGH (routing, compat, bloat) / MEDIUM (entity collision, rules injection) | Routing, backward-compat, and SKILL.md bloat are HIGH confidence from v1.1 validated pitfall evidence. Entity collision and rules injection via context window are inferred from first principles without prior experiment in this codebase. |

**Overall confidence:** HIGH

### Gaps to Address

- **Rules injection effectiveness in long-context prompts:** PITFALLS.md recommends injecting rules after the graph context and filtering by category. This is first-principles reasoning, not experimentally confirmed. During Phase 4 integration testing, include a canary rule with a distinctive `dont_use` value (e.g., `"dont_use": ["frameworkX_that_doesnt_exist"]`) to verify rules reach the generation step. If the canary never surfaces in `/architect` output on the matching scenario, rules are being ignored.
- **LightRAG entity collision threshold:** The "10-15 repo batch" recommendation is conservative. If batch 1 shows no hub-node inflation, batches can expand to 20. The `list_entities.py` entity connection count check is the signal.
- **`google-genai` multi-turn contents API:** Multi-turn pattern confirmed stable since v0.3.x, but the exact parameter names for passing the `contents` list should be verified against the installed version before implementation.
- **Copilot rule quality:** The 50% cap on Copilot-derived rules is a policy recommendation. The adversarial audit ("can Gemini answer this without the rule?") is the only reliable signal. Run it during Phase 2 before treating the rules engine as complete.

---

## Sources

### Primary (HIGH confidence — actual source files read)

- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skill_runner.py` — `TestCase` dataclass (line 68-74), `call_gemini()` (line 153), `run_test_case()` (line 196-211), temperature=0.1 (line 168)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\ingest_wechat.py` — no `--source` flag confirmed; `sys.argv[1]` only; `run_in_executor` pattern for sync calls in async context (line 118)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\kg_synthesize.py` — `synthesize_response(query_text, mode)` at line 48; canonical_map simple string replace at lines 56-62; no rules injection point confirmed
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\config.py` — existing constants pattern; `FIRECRAWL_API_KEY` already loaded; `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE` patterns to replicate
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\requirements.txt` — no pyyaml, no PyGithub, no Graphify; `requests`, `google-genai`, `lightrag-hku`, `cognee` confirmed present
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skills\omnigraph_ingest\SKILL.md` — existing skill structure, decision tree format, guard clause pattern
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\skills\omnigraph_query\SKILL.md` — Query mode routing pattern, error handling table
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\skills\test_omnigraph_ingest.json` — confirms `"input"` (singular) key in existing test cases; backward compat baseline
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\codebase\CONCERNS.md` — canonical_map fragility, bare excepts, entity_buffer idempotency, rate limiting, sequential batch processor

### Secondary (HIGH confidence — planning and spec documents)

- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\MILESTONE-2-SIMPLE-GUIDE.md` — authoritative task list and success criteria for Phase 2.1 and 2.2
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE.md` line 88 — "Graphify MCP availability and schema — validate before Phase 4" (confirms it was never implemented)
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\specs\OMNIGRAPH_VISION_Statement.md` lines 76-84 — GitHub API approach explicitly specified with `ingest_github.py` script name
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\specs\OMNIGRAPH_PRODUCT_BRIEF.md` — entity_registry.json as GitHub URL anchor design
- `C:\Users\huxxha\Desktop\OmniGraph-Vault\specs\SKILL_PACKAGING_GUIDE.md` — SkillHub packaging requirements; v1.1 pitfall evidence on SKILL.md length threshold

### Tertiary (MEDIUM confidence — inferred, not benchmarked)

- GitHub REST API rate limits (60/hr unauth, 5000/hr auth) — stable API behavior, knowledge cutoff Aug 2025; no breaking changes expected
- `google-genai` multi-turn `contents` list API since v0.3.x — verify exact parameter names against installed version before implementing
- LightRAG entity collision threshold at 50+ repos — first-principles inference from vocabulary overlap; not benchmarked on this codebase

---

*Research completed: 2026-04-23*
*Ready for roadmap: yes*
