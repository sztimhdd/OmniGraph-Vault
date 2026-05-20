# Wiki Schema — Agent Behavior + Tag Taxonomy

This is the formal contract every wiki page MUST follow. Lint (W3) enforces it.

## 1. Frontmatter (required, YAML)

Every `.md` page under `kb/wiki/` MUST start with this block:

```yaml
---
title: <page display name>
created: <ISO date, YYYY-MM-DD>
last_updated: <ISO date, YYYY-MM-DD>
sources:
  - article:<10-char-hex>
  - article:<10-char-hex>
confidence_level: high | medium | low
---
```

Fields:

- `title` — human-readable page name (any case)
- `created` — date the page was first authored
- `last_updated` — date of latest substantive edit
- `sources` — list of source articles. Each item is `article:<10-char-hex>` referencing a hash in the LightRAG store
- `confidence_level` — author judgment of synthesis quality. `high` = multi-article triangulation; `medium` = single-article-derived but reviewed; `low` = sparse evidence, marker for human review

## 2. Citation format (body)

Every claim paragraph MUST cite at least one source article:

```
^[article:<10-char-hex>]
```

Citations may appear inline (mid-sentence) or trailing (end of paragraph). All `^[article:...]` references MUST resolve to a hash listed in this page's frontmatter `sources` OR to a real article hash in the LightRAG store. Lint W3 validates resolution.

## 3. Cross-reference format

Reference another wiki page using the entity slug:

```
[[entity-slug]]
```

`entity-slug` is lowercase, hyphenated, matching the file name (without `.md`) under `entities/`. Lint W3 validates that every `[[slug]]` resolves to an existing file.

## 4. Subdirectory layout

| Subdir | Purpose | Naming |
|--------|---------|--------|
| `entities/` | One page per canonical entity (person, tool, concept, organization) | `<entity-slug>.md` |
| `concepts/` | Cross-cutting concepts that span multiple entities (e.g., `agent-skills.md`) | `<concept-slug>.md` |
| `comparisons/` | X-vs-Y pages comparing two entities or concepts | `<a-slug>-vs-<b-slug>.md` |
| `queries/` | Saved high-value Q&A pages for recurring questions | `<query-slug>.md` |
| `_suggestions/` | Auto-generated W3 suggestions awaiting lint pass; not user-visible | `<entity-slug>-<ts>.md` |

## 5. Naming convention

- Lowercase, ASCII, hyphenated
- Match the entity/concept slug exactly
- File extension always `.md`

Examples: `openclaw.md`, `hermes-agent.md`, `lightrag-vs-graphrag.md`.

## 6. Lint contract (W3 enforces)

The W3 lint guard runs four checks before applying any wiki update:

1. **Citation integrity** — every `^[article:<hex10>]` reference resolves to a real article hash in the LightRAG store
2. **Backlink validity** — every `[[entity-slug]]` cross-reference resolves to an existing file under one of the wiki subdirs
3. **Contradiction detection** — new claims do not directly contradict existing claims on the same entity (regex/diff-based v1; LLM-based v2 deferred)
4. **Staleness check** — page `last_updated` not older than the maximum of its source articles' publish dates by more than the configured threshold (default: 90 days)

If any check fails, the suggestion is dropped and a structured warning is logged to `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl`. The cron run continues.

## 7. Rollback

All wiki content is git-tracked. To undo an applied update:

```bash
git revert <commit-hash>            # if isolated commit
git checkout <hash> -- kb/wiki/<path>  # to restore one file to a prior state
```

See `kb/wiki/README.md` for sync mechanism with Hermes side.
