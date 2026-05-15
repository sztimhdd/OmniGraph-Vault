---
phase_set: kb-v2.1-stabilization
created: 2026-05-15
authored_by: orchestrator from vitaclaw-site agent's "OmniGraph KB v2.1 Stabilization Requirements" (2026-05-15)
status: ready-to-execute
ceremony: skipped — direct phase plans, no /gsd:new-milestone / discuss-phase / roadmapper
---

# kb-v2.1 Stabilization — Input

## Source

vitaclaw-site agent produced "OmniGraph KB v2.1 Stabilization Requirements" 2026-05-15
after observing Aliyun production go-live state. Captured here as the input for
4 in-scope phases + 1 explicit deferral.

The document contained 5 requirements; the orchestrator analyzed each and split:

- 4 reqs become phases in this stabilization set
- 1 req (long-form illustrated synthesis) defers to a separate decision
  (see `DEFERRED.md`)

## Phases (5 in-scope)

| # | Phase | Reqs | Priority | Dependencies | T-shirt |
|---|---|---|---|---|---|
| 1 | KG mode hardening | REQ 5 | **P0 — production stability** | — | 1d |
| 2 | Image path integration | REQ 1 | P1 — UX visible | — | 0.5-1d |
| 3 | Hero-strip migration | REQ 4 residual | P2 — cosmetic | needs hero-strip HTML extracted from Aliyun first | 0.5d |
| 4 | Structured synthesize output | REQ 2 | P1 — UX quality | benefits if Phase 1 ships first (KG mode reliable) | 1d |
| 5 | Long-form synthesis minimum-viable | REQ 3 minimum | P1 — synthesis completeness | shares `SynthesizeResult` schema with Phase 4; image paths from Phase 2 | 0.5d |

Total estimate: 3.5-4 days.

## Wave / parallelization

- Wave 1: Phase 1 (alone — production stability first)
- Wave 2: Phase 2 + Phase 3 (parallel — independent surfaces)
- Wave 3: Phase 4, then Phase 5 (sequential — Phase 5 reuses Phase 4 schema)

## Out-of-scope for this stabilization set

- **REQ 3 full long-form (preview / save / export UI)** — minimum-viable shipped via Phase 5; full UX deferred to v2.2+ (see `DEFERRED.md`)
- HTTPS/TLS, ingest cron migration, Hermes retire — not in v2.1 scope
- Databricks Apps deployment — covered by parallel kb-databricks-v1 milestone
- Auth, multi-tenancy, admin features — out of v2.1 entirely

## Inheritance

All phases inherit:
- `kb-1-UI-SPEC.md` + `kb-2-UI-SPEC.md` + `kb-3-UI-SPEC.md` design tokens (ZERO new `:root` vars)
- C1 contract (`kg_synthesize.synthesize_response`) read-only
- C2 contract (`omnigraph_search.query.search`) read-only
- C3 contract (kol_scan.db schema) read-only — no new migrations
- C4 contract (`images/{hash}/final_content.md` path) read-only

## Skill discipline

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 — Skills are tool calls, not reading material.

Mandatory floors per phase:

- **Phase 1 (KG hardening):** `security-reviewer` (mandatory — credential paths + production safety) + `python-patterns` + `writing-tests`
- **Phase 2 (image paths):** `python-patterns` + `writing-tests`
- **Phase 3 (hero-strip):** `frontend-design` + `writing-tests`
- **Phase 4 (structured synthesize):** `python-patterns` + `writing-tests`

Plan SUMMARY.md files MUST contain literal `Skill(skill="...", args="...")` strings for discipline regex match.

## Pre-execution requirements

- Aliyun upstream-hotfix quick (260515-xxx) MUST ship before Phase 4 (so structured synthesize work starts from clean main, not from production drift)
- Phase 3 needs hero-strip HTML extracted from `/var/www/kb/index.html` — request via vitaclaw-site agent OR user paste
- Phase 1 may want to know: does Aliyun's `/etc/systemd/system/kb-api.service` already have any `MemoryMax=` or `MemoryHigh=` directive, or none? Affects rollout strategy
- All phases assume `.dev-runtime/data/kol_scan.db` matches Hermes prod schema (verified 2026-05-13)

## Verification convention (Rule 3 — local UAT mandatory)

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3, every phase MUST run local UAT via
`.scratch/local_serve.py` against `.dev-runtime/` before declaring complete.
Browser smoke at desktop + mobile. Capture screenshots into `.playwright-mcp/`
with phase-specific filename prefixes.

## Authors

Original requirements: vitaclaw-site agent on Aliyun ECS post go-live, 2026-05-15.
Phase decomposition: OmniGraph orchestrator, 2026-05-15.
