---
phase: llm-wiki-integration
plan: 03
type: execute
wave: 2
depends_on: ["llm-wiki-02"]
files_modified:
  - .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md
  - .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md
  - kb/wiki/log.md   # entry that operator prompt was generated
autonomous: false   # checkpoint:human-verify after user forwards prompt to Hermes
requirements:
  - WIKI-SKILL-WIKI-FIRST   # Decision (Wave 2 in CONTEXT) — wiki-first lookup before graph in omnigraph_query
  - WIKI-NO-SSH             # CLAUDE.md Rule 5 — no SSH outsourcing; deliver via Hermes operator prompt
must_haves:
  truths:
    - "Hermes operator prompt at .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md describes the exact SKILL.md edit"
    - "Diff artifact at .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md shows before/after for the wiki-first lookup snippet"
    - "User forwards prompt to Hermes; Hermes applies edit; user pastes verification output back"
    - "Verification confirms `grep -q wiki ~/.hermes/skills/omnigraph_query/SKILL.md` returns 0 on Hermes side"
  artifacts:
    - path: ".planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md"
      provides: "Paste-ready operator prompt for Hermes to apply SKILL.md change"
    - path: ".planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md"
      provides: "Authoritative diff (before / after) for the ~20 LOC SKILL.md addition"
  key_links:
    - from: ".planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md"
      to: "~/.hermes/skills/omnigraph_query/SKILL.md (Hermes side)"
      via: "operator-applied edit per CLAUDE.md Rule 5"
      pattern: "wiki-first|kb/wiki/entities"
    - from: "~/.hermes/skills/omnigraph_query/SKILL.md (after edit)"
      to: "kb/wiki/entities/<entity>.md"
      via: "wiki-first cat + fallthrough to kg_synthesize.py"
      pattern: "cat.*wiki|kg_synthesize"
---

<objective>
Update the Hermes-side `~/.hermes/skills/omnigraph_query/SKILL.md` with a wiki-first lookup that checks `kb/wiki/entities/<entity>.md` BEFORE invoking the existing graph-query path. Per CLAUDE.md Rule 5, this is delivered via an operator prompt — Claude does NOT SSH-mutate Hermes.

Purpose: Realizes Decision/Wave 2 of CONTEXT.md — the P0 read-path improvement.
Output: Two paste-ready artifacts (operator prompt + authoritative diff) + a checkpoint where user reports back from Hermes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md
@.planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md
@.planning/phases/llm-wiki-integration/llm-wiki-02-SUMMARY.md
@./CLAUDE.md
</context>

<interfaces>
<!-- Existing Hermes skill conventions (from CLAUDE.md "OpenClaw / Hermes Skill Writing Standards") -->

SKILL.md frontmatter (existing):

```yaml
---
name: omnigraph_query
description: Query the OmniGraph-Vault knowledge graph by natural language.
triggers:
  - "search the knowledge base"
  - "what do I know about"
---
```

Existing skill body (per RESEARCH.md Code Example 4 reference):

```bash
### Fallback (existing)
Run `python kg_synthesize.py "$query" hybrid` ...
```

Reference template available on Hermes:

- `~/.hermes/skills/research/llm-wiki/SKILL.md` — has wiki ingest/query/lint patterns we partially borrow

Wiki page resolution path (Hermes side, after symlink from W0):

- `~/wiki-omnigraph/entities/<slug>.md` (= `~/OmniGraph-Vault/kb/wiki/entities/<slug>.md` via symlink)
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Author SKILL.md diff artifact (~20 LOC addition)</name>
  <files>.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md</files>
  <read_first>
    - .planning/phases/llm-wiki-integration/llm-wiki-RESEARCH.md (Code Example 4 — Hermes skill diff reference; section "Don't Hand-Roll" — Skill writing convention)
    - CLAUDE.md (OpenClaw / Hermes Skill Writing Standards section)
    - .planning/phases/llm-wiki-integration/llm-wiki-CONTEXT.md (Wave 2 specifics — extract entity from query, check kb/wiki/entities/, fall through to graph)
  </read_first>
  <action>
    Write the diff artifact at `.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md`. Structure:

    1. **Header**: target file `~/.hermes/skills/omnigraph_query/SKILL.md`, change date 2026-05-19, reason "Wave 2 of llm-wiki-integration phase".

    2. **Before snippet** (placeholder): note that we don't have a verbatim copy of the current Hermes skill in repo. The operator prompt (Task 2) will instruct Hermes to first `cat ~/.hermes/skills/omnigraph_query/SKILL.md` and paste back, so we can attach the actual before-state as part of the post-application audit. The diff doc records the EXPECTED INSERTION POINT and the NEW SECTION verbatim.

    3. **Insertion point**: under the "## Behavior" header (per RESEARCH.md Example 4), as a new subsection BEFORE the existing fallback path.

    4. **New section text** (verbatim, ≤20 LOC):
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

    5. **Rationale** paragraph: cite Decision 1 (Karpathy markdown pattern) and Decision 2 (wiki at kb/wiki/, symlinked to ~/wiki-omnigraph/) from CONTEXT.md.

    6. **Rollback**: removing this subsection restores prior behavior; no other Hermes changes.

    7. **Triggers / metadata**: NO change to frontmatter or `triggers:` list. Adding a wiki-specific trigger is not in scope.

    Keep total addition ≤ 20 LOC inside SKILL.md (per CONTEXT.md Wave 2 LOC budget).
  </action>
  <verify>
    <automated>test -f .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md && grep -q 'Wiki-first lookup' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md && grep -q 'wiki-omnigraph/entities' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` exits 0
    - `grep -q 'Wiki-first lookup' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` exits 0
    - `grep -q 'go deeper' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` exits 0
    - `grep -q 'kg_synthesize' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` exits 0 (fallback referenced)
    - The new section block in the doc is ≤ 20 lines
  </acceptance_criteria>
  <done>Authoritative diff artifact exists with insertion point, verbatim new section, rationale, rollback notes.</done>
</task>

<task type="auto">
  <name>Task 2: Author Hermes operator prompt (HERMES-PROMPT-W2.md)</name>
  <files>.planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md, kb/wiki/log.md</files>
  <read_first>
    - .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md (just-written; embed the verbatim section from there)
    - CLAUDE.md (Rule 5; HIGHEST PRIORITY PRINCIPLES; OpenClaw / Hermes Skill Writing Standards)
    - .planning/phases/llm-wiki-integration/HERMES-PROMPT-W0-SYNC.md (W0 prompt — reference for tone/format)
  </read_first>
  <action>
    Write `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` as a paste-ready operator prompt. Structure:

    **Header**:
    > Hermes operator prompt — apply Wave 2 wiki-first lookup to omnigraph_query SKILL.md
    > Source: llm-wiki-integration phase, Wave 2
    > Per CLAUDE.md Rule 5 — Claude does not SSH-mutate Hermes; user forwards this prompt to Hermes.

    **Step 0 — Pre-flight diagnostic** (Hermes runs read-only):
    ```bash
    # Confirm prerequisites
    test -L ~/wiki-omnigraph && readlink ~/wiki-omnigraph   # should print absolute path inside ~/OmniGraph-Vault/kb/wiki
    ls ~/wiki-omnigraph/entities/ | head -5                   # confirm wiki content visible
    cat ~/.hermes/skills/omnigraph_query/SKILL.md             # paste current state back to Claude session
    ```

    **Step 1 — Pause for confirmation**: instruct Hermes to STOP after Step 0 and the user must paste the SKILL.md current state back into the Claude session BEFORE Step 2 runs. This way we can record the actual before-state in the audit trail.

    **Step 2 — Apply edit** (Hermes runs after Step 1 confirmed):
    Embed the verbatim new section from `llm-wiki-03-SKILL-DIFF.md`. Instruct Hermes to:
    - Open `~/.hermes/skills/omnigraph_query/SKILL.md` in editor
    - Locate the `## Behavior` header
    - Insert the wiki-first lookup subsection BEFORE any existing subsection under `## Behavior`
    - Save the file
    - Run `grep -A 25 'Wiki-first lookup' ~/.hermes/skills/omnigraph_query/SKILL.md` and paste output back to confirm insertion

    **Step 3 — Smoke test** (Hermes runs):
    Pick an entity slug from `~/wiki-omnigraph/entities/` (e.g., `openclaw`):
    ```bash
    # Manually exercise the new code block with a fake $query
    query="What is OpenClaw?"
    entity_slug=$(echo "$query" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-|-$//g')
    wiki="$HOME/wiki-omnigraph/entities/${entity_slug}.md"
    echo "computed wiki path: $wiki"
    test -f "$wiki" && echo "FOUND" || echo "MISSING (slug extraction may need refinement; see follow-up)"
    ```
    Note: simple slug extraction may not match `openclaw` for query "What is OpenClaw?" (slug becomes `what-is-openclaw`). Document this as a known limitation in this Wave 2 — Wave 5 of a future phase can iterate on entity-extraction quality. For Wave 2, the basic path-check is sufficient to demonstrate the wiki-first hook works; Hermes agent's normal NLU layer extracts the entity name before passing to the skill.

    **Step 4 — Report back to Claude session**:
    User pastes back:
    - Output of Step 0 cat (current SKILL.md)
    - Output of Step 2 grep (new section visible)
    - Output of Step 3 smoke

    **Rollback (if Step 2 goes wrong)**:
    `git checkout HEAD -- ~/.hermes/skills/omnigraph_query/SKILL.md` (if skill is git-tracked) OR restore from a copy made before Step 2.

    Append to `kb/wiki/log.md`: `<ISO date> — W2 Hermes operator prompt generated at .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md (awaiting user forward)`.

    **CRITICAL — anti-pattern check**: do NOT include any `ssh -p ... user@host ...` block in this prompt or in agent's Bash invocations during this task. The user forwards the prompt; Claude does not SSH.
  </action>
  <verify>
    <automated>test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md && grep -q 'Wiki-first lookup' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md && grep -q 'Step 0' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md && ! grep -E 'ssh -p [0-9]+ ' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` exits 0
    - File contains explicit pause-for-confirmation between Step 0 and Step 2
    - File embeds the verbatim wiki-first section from SKILL-DIFF.md
    - `grep -E 'ssh -p [0-9]+ ' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` exits 1 (NO matches — no SSH command in prompt)
    - `grep -q 'rollback\|Rollback' .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` exits 0
    - `tail -5 kb/wiki/log.md | grep -q 'W2 Hermes operator prompt'` exits 0
    - No `ssh` invocation appears in agent's Bash tool history for this task
  </acceptance_criteria>
  <done>Hermes operator prompt is paste-ready, contains pre-flight + pause + apply + smoke + report-back + rollback steps, contains the verbatim diff, no SSH commands, log.md updated.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: User forwards prompt to Hermes; reports back; Claude verifies</name>
  <what-built>HERMES-PROMPT-W2.md operator prompt + SKILL-DIFF.md authoritative diff. The actual SKILL.md mutation happens on Hermes via user-forwarded prompt.</what-built>
  <how-to-verify>
    1. User opens `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md`, copies its contents.
    2. User forwards to Hermes (paste into Hermes UI or new Hermes session).
    3. Hermes runs Step 0; user pastes Step 0 output back into THIS Claude session.
    4. After confirming current state looks right, user tells Hermes to proceed with Step 2.
    5. Hermes runs Step 2 + Step 3; user pastes outputs back.
    6. Claude appends the captured before-state + Step 2 grep output + Step 3 smoke output to `.planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` under a new `## Applied (audit trail)` section.
    7. Final verification commands user runs in this Claude session by relaying to Hermes (read-only, no SSH from Claude):
       - Tell Hermes: `grep -q 'Wiki-first lookup' ~/.hermes/skills/omnigraph_query/SKILL.md && echo OK || echo MISSING`
       - Tell Hermes: `wc -l ~/.hermes/skills/omnigraph_query/SKILL.md` (should be ~20 lines longer than before)
    8. Append final entry to `kb/wiki/log.md`: `<ISO date> — W2 applied on Hermes (commit/edit verified by user)`.

    Expected outcomes:
    - SKILL.md contains "Wiki-first lookup" subsection
    - Hermes CLI test `omnigraph_query "what do I know about openclaw"` returns wiki content (if entity extraction in Hermes NLU is good enough) OR falls through to graph (if not — acceptable; documented limitation)
  </how-to-verify>
  <resume-signal>
    User responds with one of:
    - "applied" + pastes Step 0/2/3 outputs → Claude appends audit trail to SKILL-DIFF.md, appends log.md entry, plan COMPLETE
    - "needs revision: <description>" → Claude revises HERMES-PROMPT-W2.md, return to Task 3
    - "abort" → Claude leaves artifacts in place; plan returns CHECKPOINT REACHED for follow-up
  </resume-signal>
</task>

</tasks>

<verification>
Phase-level verification for W2:
- `test -f .planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` exits 0
- `test -f .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` exits 0
- After Task 3: SKILL-DIFF.md contains "## Applied (audit trail)" section with actual Hermes output
- `kb/wiki/log.md` has 2 new entries (prompt generated; applied on Hermes)
- No `ssh -p` command issued from Claude's Bash tool in this plan
</verification>

<success_criteria>

1. SKILL.md diff artifact exists with the exact ~20 LOC addition documented
2. Hermes operator prompt is paste-ready, contains pre-flight + pause + apply + smoke + rollback
3. User has forwarded prompt to Hermes; Hermes has applied edit; user pasted verification back
4. Audit trail appended to SKILL-DIFF.md
5. Plan never invoked SSH from Claude's Bash tool (CLAUDE.md Rule 5 satisfied)
</success_criteria>

<output>
After completion, create `.planning/phases/llm-wiki-integration/llm-wiki-03-SUMMARY.md` capturing:
- Path to operator prompt + diff artifact
- The actual before-state of SKILL.md (captured from Hermes via Step 0)
- The Hermes Step 2 + Step 3 outputs
- Confirmation of "Wiki-first lookup" presence on Hermes
- Any limitations discovered (e.g., naive slug extraction not matching arbitrary user phrasing)
- Note: NO Local UAT this wave — change is on Hermes, not in repo's kb/ runtime; verification is Hermes-side per the manual checkpoint above
</output>
</content>
