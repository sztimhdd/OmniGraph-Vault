# PM/PO Handoff Plan For Claude Code

## Summary

Do not implement code directly from this planning thread. Instead, Claude Code should absorb the new SkillHub requirements, update the project's GSD planning artifacts, and then execute the revised Phase 2/3 work from GitHub.

This handoff defines:

- the new canonical internal requirements reference
- the planning changes needed in `.planning/`
- the implementation direction Claude Code should take after revising the plans

## Artifact To Add

Claude Code should treat the following as required planning assets:

- `.planning/SKILLHUB_REQUIREMENTS.md`
  - canonical internal reference
  - full content preserved from the external requirements document
- `specs/SKILL_PACKAGING_GUIDE.md`
  - public-facing condensed guide for contributors
  - summarize structure, SKILL.md rules, script rules, evals, packaging, and safety

## Planning Changes Required

### 1. Update planning system artifacts

Claude Code should update:

- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- any current or new Phase 2 / Phase 3 plan docs required to make execution decision-complete

### 2. Revise phase definitions

Phase 1 stays intact.

Revise the next phases to:

- **Phase 2: SkillHub-Ready Skill Packaging**
  - convert `omnigraph_ingest` and `omnigraph_query` into full skill packages
  - require `SKILL.md`, `scripts/`, `references/`, `evals/`, optional `assets/`
  - require deterministic wrappers/scripts, explicit env validation, and working-directory independence
  - require "pushy" descriptions, explicit NOT-triggers, and progressive-disclosure structure
  - require local eval coverage for both skills

- **Phase 3: Hermes Deployment + Gate 7 Validation**
  - deploy repo-backed skills into the real Hermes environment
  - validate trigger dispatch, wrapper execution, error guards, and cross-article synthesis end-to-end
  - validate no drift between GitHub repo skills and Hermes-loaded skills
  - validate deployment contract and operator workflow

### 3. Expand requirements

Claude Code should add new Phase 2/3 requirements covering:

- SkillHub-compliant package structure
- SKILL.md frontmatter/body quality
- deterministic script interface contract
- eval suite structure and assertion format
- packaging readiness
- Hermes deployment contract
- shadow-skill / duplicate-skill prevention

### 4. Implementation bias

Claude Code should treat this as product/platform packaging work, not just prompt tweaking:

- repo skill directories become production-grade packages
- wrappers/scripts become deterministic operational entrypoints
- docs align with real Hermes deployment
- validations are separated into local skill evals vs real Hermes runtime validation

## Concrete Scope Claude Code Should Implement

### Phase 2 implementation target

For both `skills/omnigraph_ingest` and `skills/omnigraph_query`:

- tighten `SKILL.md`
- add `scripts/` entrypoints
- add `references/`
- add `evals/evals.json`
- align tests with the new structure
- ensure scripts call repo code from `~/OmniGraph-Vault`
- ensure runtime data stays in `~/.hermes/omonigraph-vault`

### Phase 3 implementation target

- document and validate one canonical Hermes deployment flow
- ensure `skills.external_dirs` is the supported connection path
- validate `hermes skills list`, dispatch, and runtime behavior
- validate missing-env, missing-CDP, empty-KB, and wrong-trigger cases
- validate cross-article synthesis through real Hermes, not only direct Python calls

## Test Plan Claude Code Must Encode

### Local packaging/eval tests

- both skills satisfy declared directory structure
- both `SKILL.md` files meet trigger/NOT-trigger expectations
- both skill eval suites are valid and runnable
- `skill_runner.py` passes for ingest and query

### Hermes runtime validation

- skills visible in Hermes
- repo-backed skills are actually the ones loaded
- wrappers work from non-project working directories
- human-readable failure modes appear without raw traceback
- cross-article query succeeds in Hermes after Gate 6 content exists

## Assumptions

- Claude Code is the implementer and should mutate the repo.
- This PM/PO thread remains planning and handoff only.
- The internal canonical SkillHub requirements doc should be preserved verbatim.
- The public companion doc should be curated and shorter.
- Phase 1 code fixes remain the current prerequisite and should not be re-scoped.
