---
phase: 18-daily-ops-hygiene
plan: 03
type: execute
wave: 1
depends_on: [18-02]
files_modified:
  - kg_synthesize.py
  - skills/omnigraph_query/SKILL.md
  - tests/unit/test_image_directive_shared.py
autonomous: true
requirements: [HYG-04]
must_haves:
  truths:
    - "`kg_synthesize.py` exports the image-URL directive as a module-level constant `IMAGE_URL_DIRECTIVE` (no magic string)"
    - "The `synthesize_response` `custom_prompt` references `IMAGE_URL_DIRECTIVE` by name (not duplicated text)"
    - "`skills/omnigraph_query/SKILL.md` cross-references the directive rule in a visible section so the skill reader knows synthesis preserves image URLs"
    - "A unit test asserts the constant exists and is non-empty, and that the constant string appears in `synthesize_response`'s built prompt"
  artifacts:
    - path: "kg_synthesize.py"
      provides: "`IMAGE_URL_DIRECTIVE` constant + referenced in custom_prompt"
      min_lines_touched: 5
    - path: "skills/omnigraph_query/SKILL.md"
      provides: "Cross-reference to the image-URL preservation behavior in synthesize"
      min_lines_touched: 3
    - path: "tests/unit/test_image_directive_shared.py"
      provides: "Unit tests for constant existence + prompt inclusion"
      min_lines: 40
  key_links:
    - from: "kg_synthesize.py::IMAGE_URL_DIRECTIVE"
      to: "kg_synthesize.py::synthesize_response custom_prompt"
      via: "string concatenation"
      pattern: "IMAGE_URL_DIRECTIVE"
---

<objective>
Wave 0 Close-Out § B + § E surfaced a prompt-dependent behavior: LightRAG retrieval delivered 16 image URLs into LLM context, but the default synthesis prompt did not instruct URL preservation → 0 inline images. The fix was a `CRITICAL: ... ![description](url) INLINE` directive (commit `0109c02`). But the directive is currently a magic string inside one function.

This plan extracts the directive into a module-level constant so future skills / scripts / test fixtures can reference it by name, and cross-references it from `omnigraph_query` SKILL.md so the skill documentation matches the code behavior.

Non-goal: this plan does NOT create `skills/omnigraph_synthesize/` (it doesn't exist — confirmed by `ls skills/` in planning). If a future `omnigraph_synthesize` skill is added, it inherits the constant. Same for `scripts/bench_ingest_fixture.py` — it's query-less today; future extension gets the constant for free.
</objective>

<execution_context>
Windows dev machine. Pure text-level refactor + skill doc update + 2 tiny tests. No live API.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-00-SUMMARY.md
@kg_synthesize.py
@skills/omnigraph_query/SKILL.md

<ordering_dependency>
This plan `depends_on: [18-02]` because 18-02 rewrites `synthesize_response`'s `custom_prompt` construction (adding the history_block). Landing 18-03 AFTER 18-02 lets this plan's refactor operate on 18-02's post-state cleanly (one diff, not a 2-way merge).
</ordering_dependency>

<proposed_diff_sketch>
In `kg_synthesize.py`:

```python
# Module-level constant. Captured from Wave 0 commit 0109c02. Any future
# synthesis-layer prompt (omnigraph_synthesize, scripts/bench_ingest_fixture,
# skills) that pipes a query to an LLM over image-containing LightRAG context
# MUST include this directive, or inline image URLs are dropped by the model
# (observed 2026-05-02 in P2 of Wave 0 gate).
IMAGE_URL_DIRECTIVE = (
    "CRITICAL: when the context below contains image URLs like "
    "http://localhost:8765/..., you MUST include them as "
    "![description](url) INLINE in your answer near the relevant text. "
    "Do NOT skip images. Do NOT drop URLs."
)
```

Then in `synthesize_response`:

```python
custom_prompt = (
    "You are a knowledge synthesizer. "
    + IMAGE_URL_DIRECTIVE
    + "\n\n"
    + history_block  # from 18-02
    + f"Query: {query_text}"
)
```

In `skills/omnigraph_query/SKILL.md`, extend the existing "Image Server Note" section (around line 69):

```markdown
## Image Server Note

If the user expects inline images in the synthesis output, the image server must be
running on port 8765:

    cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &

If images are not loading, mention this to the user.

### How image URLs reach the synthesis output

`kg_synthesize.py` uses a `CRITICAL ... ![description](url) INLINE` directive
(constant `IMAGE_URL_DIRECTIVE` in that module) to instruct the LLM to preserve
any `http://localhost:8765/...` URLs pulled from LightRAG retrieval context.
If the image server is running and the graph has images for the query topic
but the output still contains zero images, the directive may have been dropped
or overridden — flag this to the operator.
```
</proposed_diff_sketch>

<unit_test_shape>
Two tests:

1. `test_image_url_directive_constant_is_defined_and_non_empty` — import `IMAGE_URL_DIRECTIVE`; assert `isinstance(x, str)` and `len(x) > 50` and `"![description](url)" in x`.
2. `test_directive_appears_in_synthesize_response_prompt` — this is a light white-box check. Read the source of `synthesize_response` via `inspect.getsource` and assert `"IMAGE_URL_DIRECTIVE"` is referenced by name (not by duplicated literal). Protects against future drift.
</unit_test_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-03.1: Extract `IMAGE_URL_DIRECTIVE` constant + cross-reference in SKILL.md</name>
  <files>kg_synthesize.py, skills/omnigraph_query/SKILL.md, tests/unit/test_image_directive_shared.py</files>
  <behavior>
    - `kg_synthesize.IMAGE_URL_DIRECTIVE` is a non-empty string containing `"![description](url)"`.
    - `synthesize_response` uses the constant by name, not via duplicated literal.
    - `skills/omnigraph_query/SKILL.md` has a subsection explaining the directive mechanism under "Image Server Note".
    - The pre-existing custom_prompt behavior is functionally unchanged (same text reaches the LLM).
  </behavior>
  <read_first>
    - kg_synthesize.py (post-18-02 state) — the region around `custom_prompt`
    - skills/omnigraph_query/SKILL.md — the "Image Server Note" section (~line 69)
    - 05-00-SUMMARY § B + § E — the P2 inline-image finding
  </read_first>
  <action>
    1. Add `IMAGE_URL_DIRECTIVE` module constant at top of `kg_synthesize.py` (just after imports, before `synthesize_response`).
    2. Replace the inline CRITICAL sentence in `custom_prompt` with `+ IMAGE_URL_DIRECTIVE +` reference.
    3. Add "How image URLs reach the synthesis output" subsection in `skills/omnigraph_query/SKILL.md`.
    4. Write 2 pytest tests per `<unit_test_shape>`.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_image_directive_shared.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "^IMAGE_URL_DIRECTIVE = " kg_synthesize.py` — constant at module scope.
    - `grep -c "CRITICAL: when the context below contains image URLs" kg_synthesize.py` returns `1` — directive text appears EXACTLY once (in the constant; not duplicated in the function).
    - `grep -q "IMAGE_URL_DIRECTIVE" skills/omnigraph_query/SKILL.md` — cross-ref present.
    - `grep -q "How image URLs reach the synthesis output" skills/omnigraph_query/SKILL.md` — subsection heading present.
    - 2 pytest tests pass.
  </acceptance_criteria>
  <done>Directive has a single source of truth and is discoverable from SKILL.md.</done>
</task>

</tasks>

<verification>
- Unit tests green (2 new + existing tests pass).
- No behavior change in the synthesized prompt (same text reaches the LLM).
- SKILL.md renders correctly in skill_runner (simple Markdown, no code executed).
</verification>

<success_criteria>
- HYG-04 satisfied: future skills / scripts that build synthesis prompts over LightRAG image-containing contexts have a named import point for the directive.
- SKILL.md documents the mechanism so operators know where to look when images don't render.
- Trivially reversible (revert constant extraction; inline text back).
</success_criteria>

<output>
After completion, create `.planning/phases/18-daily-ops-hygiene/18-03-SUMMARY.md` documenting: constant location + length, skill cross-ref location, future-extension hook (how an omnigraph_synthesize skill would import this), test coverage.
</output>
