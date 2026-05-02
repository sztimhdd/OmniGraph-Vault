---
phase: 15-docs-runbook
plan: 02
status: complete
completed: 2026-05-01
key-files:
  created: []
  modified:
    - Deploy.md
---

## What was built

Appended 3 new top-level sections to the end of `Deploy.md` (after §9 Troubleshooting): "SiliconFlow Paid Tier vs Gemini Free" (3-row trade-off table), "Vertex AI Infrastructure Plan (Milestone B.5)" (current state, problem, solution design, timeline), "Recommended Upgrade Path" (decision matrix + forward link to VERTEX_AI_MIGRATION_SPEC.md).

## Acceptance criteria

All 12 grep checks pass:
- 3 section headings present
- 3-row provider trade-off table (SiliconFlow, Gemini, Vertex AI rows verified)
- `docs/VERTEX_AI_MIGRATION_SPEC.md` forward link present
- Verbatim cost `¥0.0013/img` and quota `500 RPD` figures preserved
- Both migration `Option A` and `Option B` documented
- Append-only insertion (all new sections after §9 Troubleshooting line number)

## Deviations

None.

## Notes

MD lint warnings (MD060 table-column-style compact, MD036 emphasis-as-heading) are not addressed — content matches PRD §B4.3/§B5 verbatim; style reformatting would violate surgical-change rule and drift from PRD.
