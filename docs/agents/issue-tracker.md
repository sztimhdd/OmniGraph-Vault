# Issue tracker: Local Markdown (reconciled with `.planning/ISSUES.md`)

This repo has two issue-tracking layers that serve different jobs — don't collapse them into one.

- **`.scratch/<feature-slug>/`** — ephemeral, per-effort ticket mechanics for whatever `/to-spec` → `/to-tickets` → `/implement` (or `/wayfinder`) is actively building right now. Needs one file per ticket so blocking edges, claim/resolve state, and the wayfinder frontier scan work.
- **`.planning/ISSUES.md`** — the durable, single source of truth for known unfixed issues *outside* active work (project CLAUDE.md Principle #10). Rows, not files; curated by the orchestrator only; never deleted, moved to "Resolved (recent)" then archived after 30 days.

## Conventions (active tickets)

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Cross-referencing `.planning/ISSUES.md`

- **Before `/to-tickets` creates new tickets**, grep `.planning/ISSUES.md` for related known issues. If one exists, add a `Related: .planning/ISSUES.md #<N>` line near the top of the new ticket file instead of duplicating the description.
- **When a ticket resolves a row that's tracked in `.planning/ISSUES.md`**, don't edit ISSUES.md from inside the ticket flow — surface it in the `/implement` close-out report. The orchestrator (not an agent) transcribes the resolution into ISSUES.md's "Resolved (recent)" section per its existing lifecycle, same as any other closed quick/phase.
- **When a ticket surfaces a new out-of-scope issue**, same rule: report it at close-out, orchestrator transcribes it into ISSUES.md as a new row — don't create a second backlog entry inside `.scratch/`.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
