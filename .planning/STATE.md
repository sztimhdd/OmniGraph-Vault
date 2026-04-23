---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Knowledge Infrastructure MVP
current_phase: 4
status: planning
last_updated: "2026-04-23T00:00:00.000Z"
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

**Project:** OmniGraph-Vault
**Milestone:** v2.0 — Knowledge Infrastructure MVP
**Current Phase:** 4 (not started — roadmap defined, awaiting Gate 6 prerequisite)
**Status:** Ready to plan
**Last Updated:** 2026-04-23

---

## Phase Status

- Phase 4 — Foundation Patch + Rules Bootstrap: not started
- Phase 5 — KB Population + Rules Quality Gate: not started
- Phase 6 — /architect Skill + Multi-Turn Testing: not started

---

## Current Focus

Roadmap defined. v2.0 has 3 phases (4, 5, 6) covering 13 requirements.

**Carry-over from v1.1:**
- Gate 6 manual checkpoint still pending (ingest 3 articles, cross-article synthesis) — prerequisite for Phase 4
- Phase 3 (Hermes deployment) deferred until after v2.0 completion

**Next action:** Complete Gate 6 manual checkpoint, then `/gsd:plan-phase 4`

---

## Progress Bar

```text
Phase 4 [          ] 0%
Phase 5 [          ] 0%
Phase 6 [          ] 0%
```

---

## Performance Metrics

- Requirements mapped: 13/13 (FOUND-01/02/03, RULES-01/02, KB-01/02/03/04, ARCH-01/02, TEST-05/06/07)
- Phases planned: 3 (phases 4, 5, 6)
- Plans written: 0
- Requirements completed: 0

---

## Accumulated Context

### Key Decisions (inherited from prior milestone)

- Cognee is always async — never block ingestion fast-path on any Cognee operation
- Atomic rename pattern for `canonical_map.json` (write `.tmp` then rename)
- `.processed` marker on entity_buffer files for batch processor idempotency
- Runtime data directory name is `omonigraph-vault` (typo baked in — do not rename)
- Two separate skills (ingest + query) rather than one unified skill

### Key Decisions (v1.1 milestone)

- Hermes must load skills via `skills.external_dirs` pointing at repo — never copy skills to `~/.hermes/skills/` (prevents drift)
- Script wrappers resolve project root from `OMNIGRAPH_ROOT` env var (fallback: `$HOME/Desktop/OmniGraph-Vault`) — not from `$(dirname "$0")` which can break on Windows paths with spaces
- SKILL.md descriptions use SkillHub pushy format (100–200 words, explicit NOT-triggers) — Claude under-triggers without this
- evals/evals.json format follows SkillHub schema for future SkillHub submission compatibility
- Repo path (`~/Desktop/OmniGraph-Vault`) and runtime path (`~/.hermes/omonigraph-vault`) must always be explicit in wrappers
- KEEP CURRENT embedding strategy (Method A): Vision describe + text embed — LightRAG has no multimodal vector support

### Key Decisions (v2.0 roadmap)

- Graphify MCP does not exist — replace with `ingest_github.py` using GitHub REST API (already in requirements.txt via `requests`)
- SKILL.md hard cap at 100 lines — GSD:DISCUSS protocol moves to `references/discuss-protocol.md` (Level 2 loading)
- `skill_runner.py` multi-turn: add `inputs: list[str]` alongside (not replacing) existing `input: str` — backward compat is non-negotiable
- `kg_synthesize.py` is NOT modified for rules injection — rules prepended at shell layer in `architect.sh`
- RULES-01 (content creation) runs in Phase 4 alongside Foundation code work — no code dependency blocks it
- RULES-02 quality audit gates Phase 6 start alongside KB-04 integration gate

### Constraints

- Windows-primary platform (Git Bash + Edge for CDP)
- Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations
- All data stays local; only Gemini API + Apify make external calls
- No LLM abstraction layer — skills wrap existing pipeline, not new standalone Python scripts
- Zero new Python dependencies for v2.0 — everything builds on existing requirements.txt

### Open Questions (v2.0)

- `google-genai` multi-turn `contents` list API exact parameter names — verify against installed version before implementing TEST-05 (context7 lookup recommended)
- LightRAG entity collision threshold — 10-15 repo batch cap is conservative; expand if first batch shows no hub-node inflation
- Copilot rule quality — 50% cap is policy; adversarial audit is the only reliable signal; run during Phase 4

---

## Session Continuity

Last activity: 2026-04-23 - Completed quick task 260423-fq7: WeChat KOL Cold-Start Bridge

---

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260423-fq7 | WeChat KOL Cold-Start Bridge | 2026-04-23 | df89da7 | [260423-fq7-wechat-kol-cold-start-bridge](./quick/260423-fq7-wechat-kol-cold-start-bridge/) |

---

Last session: 2026-04-23 — v2.0 roadmap created. 3 phases defined (4, 5, 6). 13/13 v2.0 requirements mapped. ROADMAP.md, STATE.md, and REQUIREMENTS.md traceability updated.

**Completed in prior milestone (v1.1):**

- Phase 1 Plan 01-01: All INFRA fixes (hardcoded paths, imports, bare excepts) — DONE
- Phase 1 Plan 01-02: skill_runner 9/9 automated (Gate 6 manual checkpoint still pending)
- Phase 2 Plans 02-01, 02-02, 02-03: Both skill packages complete, embedding strategy decided — DONE

**Phase dependency chain (v2.0):**

```text
Gate 6 checkpoint (carry-over)
  └─> Phase 4: FOUND-01/02/03 + RULES-01
        └─> Phase 5: KB-01/02/03/04 + RULES-02
              └─> Phase 6: ARCH-01/02 + TEST-05/06/07
```
