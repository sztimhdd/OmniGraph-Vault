# Wiki Schema — Agent Behavior + Tag Taxonomy

This is the formal contract every wiki page MUST follow. Lint (W3) enforces it.

**Note (2026-05-20 update):** Citation format upgraded from single-type
`^[article:<hex>]` to GFM-footnote `[^N]` + multi-type frontmatter `sources`
list. Reason: W1 generation mixes 3 source types (LightRAG corpus articles,
Tavily web results, LLM built-in knowledge) — old single-type inline format
couldn't represent web/builtin sources. New format is Wikipedia-aligned
(numbered footnotes + bibliography) + Markdown-native (GFM `[^N]` syntax).
Old `^[article:<hex>]` form on existing pages continues to lint-pass as a
legacy fallback (see §6 W3 contract).

## 1. Frontmatter (required, YAML)

Every `.md` page under `kb/wiki/` MUST start with this block:

```yaml
---
title: <page display name>
created: <ISO date, YYYY-MM-DD>
last_updated: <ISO date, YYYY-MM-DD>
sources:
  - id: 1
    type: article            # article | web | builtin
    ref: <10-char-hex>       # required for type=article and type=web (URL); omitted for type=builtin
    title: <short label>     # required: human-readable source label
  - id: 2
    type: web
    ref: https://github.com/example/repo
    title: Example GitHub README
  - id: 3
    type: builtin
    title: Opus 4.7 training corpus through 2026-01
confidence_level: high | medium | low
---
```

Fields:

- `title` — human-readable page name (any case)
- `created` — date the page was first authored
- `last_updated` — date of latest substantive edit
- `sources` — ordered list of all sources used. Each item:
  - `id` — integer ≥1, unique within the page; referenced inline as `[^id]`
  - `type` — `article` (LightRAG corpus, ref = 10-char hex content_hash) | `web` (Tavily / external URL, ref = full URL) | `builtin` (LLM training knowledge, no ref)
  - `ref` — required for `article` and `web`; omitted for `builtin`
  - `title` — required for all types; short human-readable label
- `confidence_level` — author judgment of synthesis quality. `high` = multi-source triangulation across ≥2 types; `medium` = single-type triangulation OR mixed-but-thin; `low` = sparse evidence, marker for human review

## 2. Citation format (body)

Every claim paragraph MUST cite at least one source via GFM footnote syntax:

```
[^N]
```

where `N` matches an `id` in the frontmatter `sources` list. Citations may
appear inline (mid-sentence) or trailing (end of paragraph). Multiple
citations stack: `[^1][^3]`.

**Examples:**

```markdown
**Hermes** is an open-source AI agent system [^1][^2]. It uses a
five-layer architecture [^1] modeled after broader agent-runtime
patterns [^3].
```

**Legacy fallback (lint-accepted, generation-deprecated):** Pages authored
before 2026-05-20 may use `^[article:<10-char-hex>]` inline form. W3 lint
treats those as type=article citations resolving to corpus hashes directly.
W1 generation on or after 2026-05-20 emits the new `[^N]` form exclusively.

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

1. **Citation integrity** — every body citation resolves:
   - New `[^N]` form: `N` MUST be the `id` of a frontmatter `sources` entry; for `type=article` entries, `ref` MUST be a real article hash in the LightRAG store
   - Legacy `^[article:<hex>]` form: hash MUST be a real article hash in the LightRAG store (treated as implicit type=article source)
2. **Backlink validity** — every `[[entity-slug]]` cross-reference resolves to an existing file under one of the wiki subdirs
3. **Contradiction detection** — new claims do not directly contradict existing claims on the same entity (regex/diff-based v1; LLM-based v2 deferred)
4. **Staleness check** — page `last_updated` not older than the maximum of its source articles' publish dates by more than the configured threshold (default: 90 days). For pages with NO type=article sources (e.g., pure web/builtin), staleness is measured against `last_updated` itself relative to a global ceiling (default 180 days).

If any check fails, the suggestion is dropped and a structured warning is logged to `.planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl`. The cron run continues.

## 7. Rollback

All wiki content is git-tracked. To undo an applied update:

```bash
git revert <commit-hash>            # if isolated commit
git checkout <hash> -- kb/wiki/<path>  # to restore one file to a prior state
```

See `kb/wiki/README.md` for sync mechanism with Hermes side.
