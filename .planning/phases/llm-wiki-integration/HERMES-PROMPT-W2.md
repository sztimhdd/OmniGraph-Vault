# Hermes Operator Prompt — W2 Wiki-First Lookup in `omnigraph_query`

> **Source:** `llm-wiki-integration` phase, Wave 2 (commit-pinned via `.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md`).
>
> **Per CLAUDE.md Rule 5** — Claude does not SSH-mutate Hermes. The user forwards the relevant section of this prompt to Hermes; Hermes runs it and pastes any output back into the Claude session.

This prompt has **four sequential steps with one mandatory pause**. Do **not** run Step 2 until the user has reviewed the Step 0 output and explicitly told Hermes to proceed.

---

## Step 0 — Pre-flight diagnostic (read-only, run immediately)

Forward this block to Hermes. It is **read-only** — it prints state but does not modify any file.

```bash
echo "=== symlink target ==="
test -L ~/wiki-omnigraph && readlink ~/wiki-omnigraph || echo "(NOT a symlink — W0 sync may not have completed)"

echo ""
echo "=== wiki content visible ==="
ls ~/wiki-omnigraph/entities/ 2>/dev/null | head -10 || echo "(no entities directory)"

echo ""
echo "=== current SKILL.md ==="
cat ~/.hermes/skills/omnigraph_query/SKILL.md || echo "(SKILL.md missing — investigate before continuing)"

echo ""
echo "=== current line count ==="
wc -l ~/.hermes/skills/omnigraph_query/SKILL.md
```

Hermes pastes back: the `readlink`, the entities `ls`, the current SKILL.md content, and `wc -l`.

---

## Step 1 — PAUSE for user confirmation

**Hermes: stop here after Step 0. Do NOT proceed to Step 2 until the user explicitly says "go" / "proceed" / "apply" in the Claude session.**

While paused, the user does the following in the Claude session:

1. Pastes Step 0 output.
2. Claude appends the captured before-state into `.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` under `## Applied (audit trail)`.
3. Claude confirms the file structure looks as expected (has a `## Behavior` header, has at least one existing subsection beneath it).
4. User then tells Hermes "proceed with Step 2".

This pause is mandatory — it is the only point where the actual current state of `~/.hermes/skills/omnigraph_query/SKILL.md` enters the audit trail.

---

## Step 2 — Apply the SKILL.md edit (only after Step 1 confirmation)

Forward this block to Hermes after the user has explicitly approved the edit.

```bash
set -e

# 0) Make a timestamped backup (single-source rollback path; works even if SKILL.md is not git-tracked)
cp ~/.hermes/skills/omnigraph_query/SKILL.md \
   ~/.hermes/skills/omnigraph_query/SKILL.md.bak-260519

# 1) Open the file in your editor of choice and insert the subsection
#    BELOW the line that reads:
#        ## Behavior
#    and ABOVE the first existing subsection under that header.
#
#    The exact text to paste (≤ 20 lines including the markdown header
#    and the trailing fall-through sentence) is the verbatim block
#    fenced as the "After — new section" in
#    .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md
#    on the user's repo. The same block is reproduced below for
#    convenience:

cat <<'WIKI_FIRST_SUBSECTION_END'

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

WIKI_FIRST_SUBSECTION_END

# 2) After saving the edit, verify insertion:
grep -A 25 'Wiki-first lookup' ~/.hermes/skills/omnigraph_query/SKILL.md

# 3) Confirm the file is ~20 lines longer than before:
wc -l ~/.hermes/skills/omnigraph_query/SKILL.md
wc -l ~/.hermes/skills/omnigraph_query/SKILL.md.bak-260519
```

The `cat <<'WIKI_FIRST_SUBSECTION_END' ... END` heredoc is a **printer**, not an in-place edit — it shows Hermes the exact verbatim text to paste, so the operator can copy from terminal output into their editor without losing whitespace or accidentally mangling backticks. The actual file mutation happens in the editor between the `cp` (step 0) and the `grep` (step 2).

Hermes pastes back:

- The `grep -A 25 'Wiki-first lookup'` output (must show the new subsection in place).
- Both `wc -l` values (post-edit minus pre-edit ≈ 20).

---

## Step 3 — Smoke test (read-only, run after Step 2 verification)

```bash
# Pick a known entity slug from the wiki
ls ~/wiki-omnigraph/entities/ | head -5

# Manually exercise the new code block with a fake $query
query="What is OpenClaw?"
entity_slug=$(echo "$query" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-|-$//g')
wiki="$HOME/wiki-omnigraph/entities/${entity_slug}.md"
echo "computed wiki path: $wiki"
test -f "$wiki" && echo "FOUND" || echo "MISSING (slug extraction may need refinement; see follow-up)"

# Try with a slug-shaped query (the realistic NLU-routed case)
query="openclaw"
entity_slug=$(echo "$query" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-|-$//g')
wiki="$HOME/wiki-omnigraph/entities/${entity_slug}.md"
echo "computed wiki path: $wiki"
test -f "$wiki" && echo "FOUND" || echo "MISSING"
```

**Expected behavior:**

- `query="What is OpenClaw?"` → slug becomes `what-is-openclaw` → MISSING (known limitation; Hermes' upstream NLU layer narrows to bare entity name before calling the skill).
- `query="openclaw"` → slug becomes `openclaw` → FOUND (assuming W3/W4 has populated the page; FOUND for the placeholder file post-W0 / real content post-W4).

A MISSING in the first case is **expected** and not a defect — it is documented in the diff artifact's Acceptance section as the known limitation of the naive slug extractor. Wave 5 of a future phase can iterate on the slug logic if needed.

Hermes pastes back: both `echo "computed wiki path:"` lines plus their `FOUND` / `MISSING` outcomes.

---

## Step 4 — Report back to the Claude session

The user pastes the following back into the Claude session, in order:

1. Step 0 output (current SKILL.md before the edit).
2. Step 2 grep output (new subsection visible after the edit).
3. Step 2 `wc -l` outputs (before vs after).
4. Step 3 smoke output (FOUND / MISSING per query shape).

Claude appends all four under `## Applied (audit trail)` in
`.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md`,
then appends a "W2 applied on Hermes" entry to `kb/wiki/log.md`,
and the W2 plan transitions to COMPLETE.

---

## Rollback

If Step 2 results in a corrupt SKILL.md (wrong location, mangled
markdown, accidental deletion of unrelated text), restore from the
timestamped backup:

```bash
cp ~/.hermes/skills/omnigraph_query/SKILL.md.bak-260519 \
   ~/.hermes/skills/omnigraph_query/SKILL.md

# Verify restore
diff ~/.hermes/skills/omnigraph_query/SKILL.md \
     ~/.hermes/skills/omnigraph_query/SKILL.md.bak-260519
# (no output = identical = restore OK)
```

If `~/.hermes/skills/omnigraph_query/SKILL.md` is git-tracked on Hermes,
`git checkout HEAD -- ~/.hermes/skills/omnigraph_query/SKILL.md` is also
a valid rollback. Either path leaves no residue from the W2 attempt.

After rollback, the user reports back in the Claude session and Claude
revises this prompt before retry.

---

## Notes for the user

- **Mandatory pause at Step 1** — without the captured before-state, the
  audit trail in SKILL-DIFF.md cannot show what changed.
- **Backup is per-day, not per-attempt** — if you re-run Step 2 in the
  same day, the `SKILL.md.bak-260519` from the first attempt is the
  canonical pre-W2 state. Subsequent attempts overwriting it will lose
  the original; rename the existing `.bak-260519` first if a redo is
  needed (`mv SKILL.md.bak-260519 SKILL.md.bak-260519-attempt1`).
- **No SSH from Claude** — every command in this prompt runs on Hermes,
  initiated by the user pasting it into Hermes. Claude only reads outputs
  the user pastes back.
