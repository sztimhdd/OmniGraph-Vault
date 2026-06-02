# SCHEMA Extension Proposal — `type=local`

**Status:** PROPOSAL (not applied)
**Created:** 2026-05-29
**Owner:** wiki/copilot-studio quick task author (this session)
**Related:** `kb/wiki/SCHEMA.md` §1 (frontmatter source types)
**Trigger:** Karpathy/Pratiyush methodology audit, finding #2 (`type=builtin` overloaded as raw-source placeholder)

---

## Problem

`kb/wiki/SCHEMA.md` §1 currently allows three frontmatter source `type` values:

| type | ref required | Semantic meaning |
|------|--------------|------------------|
| `article` | yes (10-char hex) | LightRAG corpus content_hash |
| `web` | yes (full URL) | Tavily / external URL |
| `builtin` | no | LLM training-corpus knowledge |

The Copilot Studio quick task ingested **7 raw markdown files** sitting under `~/Desktop/mml_loan_doc_assembly/.planning/research/copilot-studio/`. These files are:

- Not in the LightRAG corpus (no content_hash) → can't use `type=article` (also explicitly forbidden by orchestrator constraint B).
- Not URLs → can't use `type=web`.
- Not LLM training knowledge — they are **synthesized research that lives on disk in a sibling project's planning folder** → `type=builtin` is a semantic abuse.

Current workaround: 5 new entity pages each ship 1–2 `type=builtin` sources with `title="Microsoft public documentation synthesis (Copilot Studio research, 2026-05-29)"` etc. Lint passes (W3 doesn't validate `type=builtin` ref because there isn't one), but the source-type list lies about provenance.

This is the same shape Karpathy describes as Layer 1 (raw sources, immutable, user-curated, never edited after capture) but **not** stored as W1 LightRAG articles. `kb/wiki/SCHEMA.md` does not currently have a slot for this.

## Proposal

Add a fourth source type:

```yaml
sources:
  - id: 4
    type: local
    ref: .planning/research/copilot-studio/INTEGRATIONS.md
    title: Local research notes — Copilot Studio integrations
```

Semantics:

| type | ref required | ref format | Semantic meaning |
|------|--------------|------------|------------------|
| `article` | yes | 10-char hex | LightRAG corpus content_hash (unchanged) |
| `web` | yes | full URL | External URL (unchanged) |
| `builtin` | no | — | LLM training-corpus knowledge (unchanged) |
| **`local`** | **yes** | **repo-relative path** | **A markdown / text source on disk that lives outside the LightRAG corpus but inside this repo's tracked file tree** |

Repo-relative path is from the repo root (e.g., `.planning/research/...`, `docs/...`, `kb/wiki/_research/...`). Path must point to an existing file at lint time.

## Why `local` and not just extend `article` to accept paths

Three reasons:

1. **`type=article` is structurally tied to the LightRAG W1/W3 pipeline.** `kb/wiki_lint.py:lint_citation_integrity` validates `article` refs against `known_article_hashes` which is the LightRAG corpus snapshot. Path-shaped refs would either need a separate code path (defeating the point of the same `type` value) or forced inclusion in the corpus (defeating immutability).
2. **`type=builtin` semantics are about LLM training, not about disk location.** Conflating "this file on my disk" with "the LLM remembered this from pretraining" weakens the staleness story (built-in knowledge is permanently recent; disk files are file-mtime-recent).
3. **`type=local` makes the audit story honest** — a wiki page citing 7 local research markdowns is structurally identifiable as "synthesized from a research dump", which is a different reliability story than "synthesized from web canon" or "from LightRAG corpus".

## Lint changes

Patch to `kb/wiki_lint.py:lint_citation_integrity`:

```python
elif stype in ("web", "builtin"):
    # web ref is a URL (not validated against corpus); builtin has no ref.
    continue
elif stype == "local":
    ref = str(src.get("ref") or "")
    if not ref:
        failures.append(f"[^{sid}]: type=local missing ref")
        continue
    repo_root = _find_repo_root(page_path)  # new helper, walks up to find .git
    if not (repo_root / ref).exists():
        failures.append(f"[^{sid}]: type=local ref={ref!r} not found in repo")
else:
    failures.append(f"[^{sid}]: unknown source type {stype!r}")
```

Patch to `kb/wiki/SCHEMA.md` §1:

```markdown
- `type` — `article` (LightRAG corpus, ref = 10-char hex content_hash)
        | `web` (Tavily / external URL, ref = full URL)
        | `builtin` (LLM training knowledge, no ref)
        | `local` (in-repo markdown / text file, ref = repo-relative path)
- `ref` — required for `article`, `web`, and `local`; omitted for `builtin`
```

Patch to `kb/wiki/SCHEMA.md` §6 lint contract — add bullet:

```markdown
1. **Citation integrity** — every body citation resolves:
   - …existing bullets…
   - **type=local: ref MUST be a repo-relative path resolving to an existing file**
```

## Migration of the 5 new Copilot Studio entity pages

If this proposal is accepted:

- `copilot-studio.md` — change `id: 20` (currently `type=builtin`, "Microsoft public documentation synthesis") to `type=local, ref=.planning/research/copilot-studio/<filename>` for whichever of the 7 files actually carried the relevant claim. Same for `id: 21` (Reddit community reports — these are public web sources but the synthesis was done locally, so probably leave `builtin` for community-anecdote sources and `local` for the structured 7-doc materials).
- `declarative-agent.md`, `generative-orchestration.md`, `copilot-studio-vs-azure-ai-foundry.md`, `mcp-in-copilot-studio.md` — same pattern. Each currently has 2 `type=builtin` sources; the synthesis-of-7-docs one becomes `type=local`.

This migration is mechanical and can be done in a single commit after the SCHEMA + lint patches land.

## Out of scope for this proposal

- Changing W1 generation behavior (the LightRAG/Tavily ingest pipeline does not produce `type=local` and shouldn't — `type=local` is for hand-authored entity pages that pre-process raw research outside W1).
- Reorganizing `.planning/research/` into `kb/wiki/_research/` or similar. The location of local raw sources is a separate question; the proposal works with whatever path convention the repo settles on.
- Adding `type=session` for Claude Code session transcripts (Pratiyush's `llmwiki` adapter shape). Out of scope until OmniGraph adopts the session-ingest pattern.

## Acceptance gate

To accept this proposal:

1. Patch `kb/wiki/SCHEMA.md` (§1 + §6).
2. Patch `kb/wiki_lint.py` (`lint_citation_integrity` + new `_find_repo_root` helper).
3. Add unit tests in `tests/test_wiki_lint.py` for: type=local with valid path; type=local with missing ref; type=local with non-existent path; type=local in addition to other types in same page.
4. Migrate the 5 Copilot Studio entity pages' `type=builtin` placeholders to `type=local` where appropriate.
5. Update any ingest agent prompts (orchestrator constraint B currently says "NEVER USE type=article — you don't have hash"; extend to "use type=local for in-repo research files, type=builtin only for genuine LLM training-corpus claims").

Cost estimate: 1 quick task (~30–45 min total).

## Decision pending

User decides whether to:

- **A.** Accept and schedule a `/gsd:quick "260530-schema-add-type-local"` follow-up.
- **B.** Reject — keep `type=builtin` as the catch-all and document the semantic looseness.
- **C.** Defer — revisit when a third independent quick task hits the same problem.
