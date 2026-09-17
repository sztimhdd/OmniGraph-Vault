# VitaX Project Cleanup Implementation Plan

**Goal:** Make VitaX the single source checkout based on upstream main, preserving recoverability and external runtime data.
**Architecture:** Promote a verified upstream clone; archive the original entries outside the project; remove inert historical documents from the working tree while preserving Git history. Keep runtime module paths unchanged.
**Tech Stack:** Python, Git, Markdown.
**Spec:** User request of 2026-09-09: consolidate historical directories against sztimhdd/OmniGraph-Vault main for Codex.

## Constraints
- No deployment, external data writes, credential copying into the new checkout, commits or pushes.
- Keep tests, benchmark fixtures, migrations, deployment sources and active issue backlog.
- Do not follow runtime symlinks during inventory or archival.

## Tasks
- [x] Record original file hashes and Git state; verify old HEAD is an upstream ancestor.
- [x] Archive original root entries with same-filesystem moves; preserve every original byte and symlink.
- [x] Promote verified upstream checkout into VitaX, retaining origin and history.
- [x] Archive inert planning, scratch, historical handoff/milestone documents and copied article; preserve active ISSUES.md.
- [x] Write README.md, AGENTS.md, concise CLAUDE.md pointer, docs/README.md and cleanup record; extend .gitignore.
- [x] Redirect retained Markdown links to archived files to immutable upstream URLs.
- [x] Verify source/test byte identity against upstream, backup identity, Git integrity, Python syntax and selected offline regression tests.

Work executes inline under the user authorization; no code behavior changes or automatic commits.
