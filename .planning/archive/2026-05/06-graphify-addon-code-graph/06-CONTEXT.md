# Phase 6 — graphify-addon-code-graph — Pre-Planning Intent Brief

**Added:** 2026-04-28
**Status:** Not planned yet (run `/gsd:plan-phase 6`)

## Goal

Add code-graph query capability alongside existing domain-graph. Ship two Skills on Hermes + OpenClaw:

- `graphify_skill` — zero-code install (Graphify native)
- `omnigraph_search` — thin SKILL.md + `query.py` wrapper over existing LightRAG `get_rag()` / `aquery(mode="hybrid")`

## Single Source of Truth

- `specs/PRDTDD_GRAPHIFY_ADDON.md` — **PRD v3.0, authoritative**
- `docs/graphify-addon-plan.md` — earlier MCP-era plan, **historical only** (PRD v3.0 supersedes it with Skill form, not MCP)

## Plan Scope (PRD §5.1-5.5)

1. **Phase 1 (PRD §5.2)** — `graphify_skill` install on Hermes + OpenClaw (T1 repos only: `openclaw/openclaw`, `anthropics/claude-code`). Zero new code.
2. **Phase 2 (PRD §5.3)** — `omnigraph_search` SKILL.md + `query.py` wrapper. No new infra.
3. **Phase 3 (PRD §5.4)** — weekly cron `graphify refresh && graphify build` with atomic `tmp → rename` swap + min-node-count assert.
4. **Phase 4 (PRD §5.5, bridge nodes)** — **DEFERRED**, do not plan.

## Plan Constraints (invariants — do NOT re-litigate)

From PRD §8 Design Decisions Log:

- **D-G01** Skill form only, no MCP wrapper
- **D-G02** `graphify_skill` zero-code — Graphify native `install --platform hermes/claw`
- **D-G03** Separate storage from domain graph
- **D-G04** T1 repos ONLY (`openclaw`, `claude-code`) — do NOT add T2/T3
- **D-G05** Weekly cron, not per-commit
- **D-G06** Atomic graph swap (tmp → rename) — **INTERPRETATION AUTHORIZED 2026-04-28:** `graphifyy` 0.5.3's built-in `to_json()` shrink guard (refuses to overwrite with smaller graph) satisfies D-G06's intent. It is strictly stronger than the PRD's custom tmp-rename because it also validates content monotonicity, not just write completeness. Plan 04 relies on the shrink guard + explicit error-halt on `graphify update` failure. No custom tmp-rename wrapper required. Rationale: PRD §6.2 assumes a `graphify build --output graph.json.tmp` CLI that does not exist (research §Pitfall 2/3), so literal PRD compliance is impossible; shrink guard is the best-available equivalent.
- **D-G07** Bridge nodes deferred to later phase
- **D-G08** Rust fork NOT in graph
- **D-G09** `omnigraph_search` reuses existing LightRAG path — no new deployment
- **D-S10** OpenClaw is a first-class platform alongside Hermes

Storage path: `~/.hermes/omonigraph-vault/graphify/` (preserve `omonigraph` typo — canonical per config.py).

## Acceptance Gate (PRD §7.4 — all must pass)

- [ ] `graphify_skill` functional on Hermes + OpenClaw (both `skills list` show it)
- [ ] `omnigraph_search` SKILL.md discoverable, returns LightRAG results
- [ ] Demo 1 (streaming tool output) — agent autonomously routes to both skills
- [ ] Demo 2 (self-evolution) — agent combines design intent + call-chain from both graphs
- [ ] Weekly cron rebuilds `graph.json` atomically

## Risk Mitigations (PRD §9)

| Risk | Mitigation |
|------|------------|
| Graphify skill interface unstable | Pin Graphify version |
| Weekly cron silently fails | Refresh script adds min-node-count assert |
| Agent doesn't auto-use both skills | Demo scenario tests; fall back to bridge nodes if needed |
| Repos renamed/moved | Cron tolerates `git pull` failure, keeps stale graph |
| graph.json exceeds skill context | Monitor size; add node filter if >10MB |
| LightRAG unavailable | Skill returns error, doesn't block agent |

## Planning Instruction

When `/gsd:plan-phase 6` runs: produce `.planning/phases/06-graphify-addon-code-graph/06-00-PLAN.md` with goal-backward tasks mapped to the acceptance gate above. Use D-G01 through D-S10 as invariants. Stop before execution; wait for approval.
