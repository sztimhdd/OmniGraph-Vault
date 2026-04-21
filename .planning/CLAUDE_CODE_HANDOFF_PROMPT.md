You are implementing as the engineer. Treat this as a PM/PO handoff and revise the repo plans before coding.

Context:
- The repo now has GSD planning artifacts under `.planning/`
- Phase 1 is already defined and should remain intact
- A new external requirements document exists at `D:\Downloads\SKILLHUB_REQUIREMENTS.md`
- Your job is to ingest that document, revise the current milestone/phases, then implement the revised Phase 2/3 direction in GitHub

Your instructions:

1. Read these first:
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- '.planning\PM_PO_HANDOFF_PLAN.md'
- `.planning/STATE.md`
- `.planning/phases/01-bug-fixes-gate-6-validation/01-01-PLAN.md`
- `.planning/phases/01-bug-fixes-gate-6-validation/01-02-PLAN.md`
- `README.md`
- `Deploy.md`
- `skills/omnigraph_ingest/SKILL.md`
- `skills/omnigraph_query/SKILL.md`
- `.planning\SKILLHUB_REQUIREMENTS.md`

2. Add two new docs:
- `.planning/SKILLHUB_REQUIREMENTS.md`
  - copy the external document in full as the canonical internal reference
- `specs/SKILL_PACKAGING_GUIDE.md`
  - create a contributor-facing condensed guide summarizing structure, SKILL.md rules, script rules, evals, packaging, and safety

3. Revise planning artifacts:
- update `.planning/REQUIREMENTS.md`
- update `.planning/ROADMAP.md`
- update `.planning/STATE.md`
- add or replace Phase 2/3 plan docs as needed

4. Revise phase intent to:
- Phase 2 = SkillHub-ready skill packaging
- Phase 3 = Hermes deployment + Gate 7 validation

5. Add requirements for:
- full skill package structure (`SKILL.md`, `scripts/`, `references/`, `evals/`, optional `assets/`)
- pushy descriptions and explicit NOT-triggers
- deterministic script/CLI contract
- eval suite structure and assertion format
- packaging readiness
- Hermes deployment contract
- prevention of skill drift between repo-backed skills and copied local skills

6. Then begin implementation in the repo for the revised Phase 2 direction:
- upgrade `skills/omnigraph_ingest` and `skills/omnigraph_query` into production-grade skill packages
- add deterministic scripts/wrappers
- add references
- add eval definitions
- keep repo/runtime separation explicit:
  - source repo: `~/OmniGraph-Vault`
  - runtime data: `~/.hermes/omonigraph-vault`

7. Do not collapse Phase 2 and Phase 3 together:
- local eval/packaging work belongs in Phase 2
- real Hermes deployment/dispatch validation belongs in Phase 3

8. Before finishing, produce:
- updated planning artifacts
- implementation summary
- what remains for Phase 3 Hermes validation

Important constraints:
- preserve the `omonigraph-vault` runtime path spelling
- do not let Hermes “guess” repo paths or runtime paths
- prefer extending existing repo infrastructure over inventing parallel systems
- keep the repo as the single source of truth for skills

Start by revising the plans, then implement the revised Phase 2 work.
