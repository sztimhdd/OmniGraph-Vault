# SKILL.md Diff — Wiki-first lookup for `omnigraph_query`

| Field | Value |
|-------|-------|
| Target file (Hermes side) | `~/.hermes/skills/omnigraph_query/SKILL.md` |
| Change date | 2026-05-19 |
| Phase / wave | `llm-wiki-integration` Wave 2 |
| Reason | Realize CONTEXT.md Decision 2 — wiki-first read path BEFORE graph synthesis |
| Delivery channel | Hermes operator prompt (CLAUDE.md Rule 5 — no SSH from Claude) |
| LOC budget | ≤ 20 lines added inside SKILL.md (per CONTEXT.md Wave 2 budget) |

This artifact is the **authoritative diff** for the SKILL.md mutation Hermes
will apply. It pairs with the operator prompt at
`HERMES-PROMPT-W2.md`, which carries the same insertion verbatim plus the
pre-flight / apply / smoke / rollback procedure for the Hermes operator.

---

## Before (placeholder — captured at audit time)

We do **not** keep a verbatim copy of the current Hermes
`~/.hermes/skills/omnigraph_query/SKILL.md` in this repo. The operator
prompt's Step 0 instructs Hermes to `cat` the current file and paste it
back into the Claude session **before** Step 2 runs. That captured before-
state will be appended to this document under the
`## Applied (audit trail)` section after Task 3 completes.

Expected (per RESEARCH.md Code Example 4) the existing skill body has at
least:

```markdown
## Behavior

### Fallback (existing)
Run `python kg_synthesize.py "$query" hybrid` ...
```

The wiki-first subsection is inserted as the **first** subsection under
`## Behavior`, **before** the existing `### Fallback (existing)` (or
whatever the current first subsection is named).

---

## Insertion point

Inside `~/.hermes/skills/omnigraph_query/SKILL.md`, locate the line:

```markdown
## Behavior
```

Insert the new subsection on the next non-blank line, **before** any
existing subsection under `## Behavior`. Do not modify frontmatter,
`triggers:`, or any other section.

---

## After — new section (verbatim, ≤ 20 lines)

```markdown
### Wiki-first lookup (added 2026-05-19, llm-wiki-integration W2)

Before invoking `kg_synthesize.py`, check whether a curated wiki page exists for the query's primary entity. The wiki ships ~20 high-centrality entity pages with multi-hop graph synthesis and `^[article:<hash>]` citations.

```bash
# Extract primary entity slug from $query (lowercase, hyphenated noun phrase)
entity_slug=$(echo "$query" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-|-$//g')
wiki="$HOME/wiki-omnigraph/entities/${entity_slug}.md"
if [ -f "$wiki" ]; then
  cat "$wiki"
  echo ""
  echo "---"
  echo "(Wiki page; reply 'go deeper' for graph-level detail.)"
  exit 0
fi
```

If no wiki page exists, fall through to the standard graph synthesis path below.
```

The fenced bash block inside the new subsection is exactly 11 lines of
shell logic; the surrounding markdown brings the addition to ≤ 20 lines
total (header + paragraph + fence + footer paragraph).

---

## Rationale

- **CONTEXT.md Decision 1** — Karpathy LLM Wiki pattern uses curated
  markdown pages with `^[article:<hash>]` citations and `[[slug]]`
  cross-refs. Serving a wiki page directly is faster and cheaper than the
  ~7s `kg_synthesize.py` cold path and gives the agent deterministic,
  human-curated content for high-centrality entities.
- **CONTEXT.md Decision 2** — The wiki lives at
  `<repo>/kb/wiki/entities/<slug>.md`; on Hermes a symlink at
  `~/wiki-omnigraph` points into the deployed `OmniGraph-Vault/kb/wiki/`
  directory (created in W0 / synced via HERMES-PROMPT-W0-SYNC.md). That
  is what `$HOME/wiki-omnigraph/entities/${entity_slug}.md` resolves to.
- **Fall-through is mandatory** — the new block runs `exit 0` only on
  hit. Misses fall through to the existing `kg_synthesize.py` path,
  preserving graph-mode behavior for everything not in the curated set.
- **No frontmatter / triggers change** — Hermes NLU continues to route
  the same trigger phrases ("what do I know about", "search the
  knowledge base") to this skill. Adding a wiki-specific trigger is out
  of Wave 2 scope.

---

## Rollback

To undo: delete the `### Wiki-first lookup (added 2026-05-19, llm-wiki-integration W2)`
subsection (header + paragraph + fenced code block + trailing fall-through
sentence). Nothing else in the file is touched, so removing exactly those
lines restores the prior behavior with no side effects.

If `~/.hermes/skills/omnigraph_query/SKILL.md` is git-tracked on Hermes:

```bash
git checkout HEAD -- ~/.hermes/skills/omnigraph_query/SKILL.md
```

Otherwise the operator prompt instructs Hermes to make a timestamped
copy (`SKILL.md.bak-260519`) before applying the edit, which is the
fallback restore path.

---

## Triggers / metadata

**No change.** Frontmatter (`name`, `description`, `triggers`, optional
`metadata.openclaw.*`) is preserved exactly as-is.

---

## Acceptance / verification (Hermes side, after Task 3)

The operator prompt's Step 2 and Step 3 produce the following
verification commands, whose outputs Hermes will paste back to be
appended under `## Applied (audit trail)` below:

- `grep -A 25 'Wiki-first lookup' ~/.hermes/skills/omnigraph_query/SKILL.md`
  → must show the inserted subsection.
- `grep -q 'Wiki-first lookup' ~/.hermes/skills/omnigraph_query/SKILL.md && echo OK || echo MISSING`
  → must print `OK`.
- `wc -l ~/.hermes/skills/omnigraph_query/SKILL.md` before vs after
  → after should be ~ 20 lines longer than before.
- Smoke: `entity_slug` derivation for `query="What is OpenClaw?"` is
  expected to produce `what-is-openclaw`, which will MISS
  `~/wiki-omnigraph/entities/what-is-openclaw.md`. This is a known
  limitation of the naive slug extractor for natural-language queries —
  Hermes' upstream NLU layer is responsible for narrowing `$query` to
  the bare entity name (e.g., `openclaw`) before invoking this skill.
  Documented for follow-up; not a Wave 2 blocker.

---

## Applied (audit trail)

_To be appended after Task 3 (Hermes operator runs the prompt and pastes outputs back). Will contain:_

1. _Verbatim before-state from Step 0 `cat`_
2. _Step 2 grep output showing the new subsection in place_
3. _Step 3 smoke-test output_
4. _Date / by whom / Hermes git or backup ref_

(Empty until Task 3 completes.)
