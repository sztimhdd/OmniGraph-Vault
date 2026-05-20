# kb/wiki/ — OmniGraph LLM Wiki

A compounding markdown artifact synthesizing the LightRAG knowledge graph into human- and agent-readable pages. Pattern: Karpathy LLM Wiki (`^[article:id]` citations, cross-references via `[[slug]]`, frontmatter convention from nashsu/llm_wiki).

For the design rationale and full integration plan, see `.planning/wiki-integration-design.md` and `.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md`.

## Layout

```
kb/wiki/
├── SCHEMA.md          # Formal contract: frontmatter + citation + lint
├── index.md           # Page directory
├── log.md             # Operation log (reverse-chronological)
├── README.md          # This file
├── entities/          # One page per canonical entity (openclaw.md, hermes-agent.md, ...)
├── concepts/          # Cross-cutting concepts (agent-skills.md, ...)
├── comparisons/       # X-vs-Y pages (lightrag-vs-graphrag.md, ...)
├── queries/           # Saved high-value Q&A
└── _suggestions/      # Auto-generated W3 suggestions awaiting lint
```

See `SCHEMA.md` for the formal contract.

## Sync to Hermes

`kb/wiki/` in this repo is the source of truth. Hermes side has `~/wiki-omnigraph/` as the production read path; both are kept in sync via a **symlink** so a `git pull` on Hermes refreshes the wiki without copying files.

The symlink is set up via the operator prompt at `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md` (per CLAUDE.md Rule 5 — Claude does not SSH-mutate Hermes).

After symlink is in place:

```text
~/wiki-omnigraph -> ~/OmniGraph-Vault/kb/wiki
```

Hermes-side `cd ~/OmniGraph-Vault && git pull --ff-only` keeps content fresh.

## Rollback

All wiki writes are git-tracked. If a W3 ingest hook applies a bad update:

```bash
git revert <commit-hash>                   # roll back one wiki commit
git checkout <hash> -- kb/wiki/<path>      # restore one file to a prior state
```

The W3 lint guard runs BEFORE any update is applied, so bad suggestions are dropped and logged to `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl` rather than committed. Rollback is the safety net for the rare lint false-pass case.

See RESEARCH.md "Pitfall 5" for the failure mode this addresses.

## Formal contract

See `SCHEMA.md` for the authoritative frontmatter + citation + cross-reference + lint contract that every page MUST follow. Lint W3 enforces it.
