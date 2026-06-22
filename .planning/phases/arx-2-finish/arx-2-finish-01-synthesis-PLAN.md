---
phase: arx-2-finish
plan: 01
type: execute
wave: 2
depends_on: ["arx-2-finish-00"]
files_modified:
  - lib/research/stages/synthesizer.py
autonomous: true
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3]
must_haves:
  truths:
    - "Synthesizer produces real LLM prose, not chunks[0].snippet verbatim"
    - "The synthesis prompt incorporates ALL retrieved chunks, reasoner + verifier summaries, and image context"
    - "Prose threads [n] inline citations referencing source indices"
    - "Image markdown is woven into the report using /static/img/{parent}/{name}"
    - "An LLM failure degrades gracefully (note_line + fallback template), never raises (terminal stage Axis 8)"
  artifacts:
    - path: "lib/research/stages/synthesizer.py"
      provides: "Real LLM synthesis via lazy get_llm_func() plain-text provider"
      contains: "get_llm_func"
      min_lines: 140
  key_links:
    - from: "lib/research/stages/synthesizer.py"
      to: "lib.llm_complete.get_llm_func"
      via: "lazy import + await llm(prompt)"
      pattern: "from lib\\.llm_complete import get_llm_func"
    - from: "lib/research/stages/synthesizer.py"
      to: "all retrieved chunks"
      via: "enumerate(sources) into [n]-numbered prompt block"
      pattern: "enumerate\\(sources\\)"
---

<objective>
GAP A — replace the synthesizer stub (line 99-138) with real LLM synthesis. The
synthesizer currently IGNORES the LLM and returns `state.retrieved.chunks[0].snippet`
verbatim under a hardcoded heading. Make it build a real synthesis prompt from ALL
chunks + reasoner/verifier summaries + image context, await the PLAIN-TEXT provider
(not the JSON adapter `cfg.llm_complete`), thread [n] citations, weave images, and
degrade gracefully on failure.

Purpose: This is the single change that turns "endpoint responds with a template"
into "endpoint responds with a real cited report" — the precondition for every
downstream UAT (Wave 2/3/4). It is the GREEN gate for the 3 RED tests from Wave 0.

Output: 1 modified file (`synthesizer.py`), single forward-only commit.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md
@lib/research/stages/synthesizer.py
@lib/research/config.py
@lib/research/types.py
@lib/llm_complete.py

<interfaces>
<!-- Locked decision (RESEARCH §Risk A): Option (b) — synthesizer lazy-imports get_llm_func(). -->
<!-- get_llm_func() is SYNCHRONOUS (lib/llm_complete.py:41), returns an ASYNC provider. -->
<!-- Pattern: llm = get_llm_func(); raw = await llm(prompt). -->
<!-- Do NOT use cfg.llm_complete — that is make_json_decision_adapter (JSON tool-calling, -->
<!-- for Reasoner/Verifier ONLY). config.py:50-59 confirms underlying_llm = get_llm_func() -->
<!-- is the plain (prompt)->str provider; ResearchConfig stores only the adapter. -->
<!-- Do NOT add a field to the frozen ResearchConfig dataclass (types.py:104) — Option (a) rejected. -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace synthesizer stub (lines 99-138) with real LLM synthesis</name>
  <read_first>
    - lib/research/stages/synthesizer.py (the FULL file — you replace lines 99-138; lines 32-98 that compute `lang`, `note_lines`, `sources`, `image_entries`, `embedded_images` STAY UNCHANGED)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §Risk A lines 92-170 (the change sketch is written out verbatim — COPY it)
    - lib/llm_complete.py (confirm get_llm_func() signature: `def get_llm_func() -> Callable:` sync, returns async callable)
    - lib/research/config.py lines 50-59 (confirms the lazy-import-of-get_llm_func pattern already used in from_env())
  </read_first>
  <behavior>
    - All-chunk usage: the prompt string contains every `sources[i].snippet` numbered `[i+1]`, not just sources[0].
    - Real prose: when LLM returns non-empty markdown, that markdown becomes result.markdown (NOT chunks[0].snippet verbatim).
    - Graceful degrade: when `await llm(prompt)` raises (or returns empty), append a note_line containing "failed", fall back to the OLD template body (title + chunks[0].snippet), and return normally — NEVER raise.
    - Image weaving: after the LLM prose (success OR degrade), append `![{alt}](/static/img/{path.parent.name}/{path.name})` for each entry in the pre-computed `image_entries` (REQ-1.1-A-4 URL pattern preserved).
    - note_lines: existing upstream-stage degradation notes (lines 84-97) STAY; append the LLM-failure note only on failure.
  </behavior>
  <action>
    Open `lib/research/stages/synthesizer.py`. KEEP lines 32-98 exactly (the `_detect_language`
    helper, the `sources` collection at 61-68, the `image_entries` collection at 73-80, the
    `embedded_images` at 82, and the upstream-stage `note_lines` loop at 84-97). REPLACE the
    block from line 99 ("# Minimal markdown body — real LLM synthesis lands in ar-2.") through
    line 127 (`markdown = title + body`) with the real-synthesis block from RESEARCH §Risk A
    lines 96-166. Concretely:

    1. Add the lazy import at the top of the replacement block:
       `from lib.llm_complete import get_llm_func`  (function-body-level, mirrors config.py:50).
    2. Build `chunks_text` numbering ALL sources:
       ```python
       chunks_text = "\n\n".join(
           f"[{i+1}] {s.snippet or '(empty)'}" for i, s in enumerate(sources)
       )
       ```
    3. Pull reasoner/verifier summaries defensively (they may be None):
       ```python
       reasoner_md = (state.reasoned.inferences_md or "") if state.reasoned else ""
       verifier_md = (state.verified.fact_check_summary_md or "") if state.verified else ""
       ```
       VERIFY the exact attribute names (`inferences_md`, `fact_check_summary_md`) against
       lib/research/types.py — if they differ, use the real field names; RESEARCH inferred these.
    4. Build `images_context` from `image_entries`:
       ```python
       images_context = "\n".join(
           f"Image: {alt} — path: /static/img/{path.parent.name}/{path.name}"
           for path, alt in image_entries
       )
       ```
    5. Branch the prompt on `lang` ("zh" vs "en") using the bilingual prompt text from
       RESEARCH lines 111-135 (Chinese report requirements: flowing structure, [n] citations,
       inline image markdown, NO References section since the page renders Sources separately).
    6. The try/except (RESEARCH lines 137-156):
       ```python
       try:
           llm = get_llm_func()
           raw_markdown = await llm(prompt)
           if not raw_markdown or not raw_markdown.strip():
               raise ValueError("empty LLM response")
           markdown = raw_markdown
       except Exception as exc:  # noqa: BLE001 — terminal stage MUST NOT raise
           note_lines.append(f"> ❌ LLM synthesis failed: {exc!s}")
           if lang == "zh":
               title = f"# 关于「{query}」的研究答复"
               body = "\n## 知识图谱检索结果\n\n"
           else:
               title = f"# Research Answer: {query}"
               body = "\n## Knowledge Graph Retrieval\n\n"
           if state.retrieved is not None and state.retrieved.chunks:
               body += state.retrieved.chunks[0].snippet or "(empty)"
           else:
               body += "(no chunks retrieved)\n"
           markdown = title + body
       ```
    7. Image-append block (RESEARCH lines 158-162) — runs in BOTH success and degrade paths:
       ```python
       if image_entries:
           markdown += "\n\n"
           for path, alt in image_entries:
               markdown += f"![{alt}](/static/img/{path.parent.name}/{path.name})\n"
       ```
    8. KEEP the existing note-append (lines 124-125) and the `return SynthesizerOutput(...)`
       at lines 133-139 unchanged (markdown=markdown, confidence as currently computed,
       sources=sources, embedded_images=embedded_images, note_lines=note_lines).

    Update the module docstring "real LLM synthesis lands in ar-2" comment to reflect it
    now lands (replace the stale TODO comment text at line 99). Do NOT touch the CJK
    `_detect_language` heuristic (deferred per locked decision).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_llm.py tests/unit/research/test_synthesizer_caption_embeds.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from lib.llm_complete import get_llm_func" lib/research/stages/synthesizer.py` succeeds.
    - `grep -q "enumerate(sources)" lib/research/stages/synthesizer.py` succeeds (all-chunk numbering).
    - `grep -q "noqa: BLE001" lib/research/stages/synthesizer.py` succeeds (the must-not-raise guard present).
    - `grep -q "/static/img/" lib/research/stages/synthesizer.py` succeeds (REQ-1.1-A-4 URL pattern preserved).
    - All 3 tests in `tests/unit/research/test_synthesizer_llm.py` now PASS (GREEN).
    - All 10 tests in `tests/unit/research/test_synthesizer_caption_embeds.py` still PASS (no regression).
    - Full research suite green: `venv/Scripts/python.exe -m pytest tests/unit/research/ tests/integration/test_research_router.py` — 0 failures.
  </acceptance_criteria>
  <done>3 RED tests now GREEN; 10 caption tests still green; transport tests green; synthesizer emits real prose with [n] + woven images, degrades without raising.</done>
</task>

<task type="auto">
  <name>Task 2: Local CLI verify real prose + single forward-only commit</name>
  <read_first>
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §Validation Architecture
    - lib/research/__main__.py (if present — the `python -m lib.research` entrypoint; confirm the `--dump-state` flag exists)
    - CLAUDE.md PRINCIPLE #2 (forward-only commits) + memory feedback_git_add_explicit_in_parallel_quicks
  </read_first>
  <action>
    Run a LOCAL CLI smoke proving real prose (not the stub) on the local store. This is a
    quick local sanity check — the real KG E2E is Wave 3/4. Use the local-dev env per
    docs/LOCAL_DEV_SETUP.md if a local store exists; if no local KG is hydrated, this step
    MAY return 0 chunks — that is acceptable for THIS task as long as the markdown shows the
    real-LLM code path executed (real prose OR a graceful degrade note, NOT the bare stub
    heading with chunks[0] verbatim). The unit tests in Task 1 are the authoritative GAP-A
    proof; this CLI run is a confidence check.

    Then commit, forward-only, explicit add:
    ```bash
    git add lib/research/stages/synthesizer.py tests/unit/research/test_synthesizer_llm.py tests/unit/research/conftest.py
    git commit -m "feat(arx-2-finish): real LLM synthesis in research synthesizer (GAP A)

    Replace chunks[0].snippet stub with real get_llm_func() synthesis:
    all-chunk prompt, [n] citations, woven images, graceful degrade.
    GREEN: tests/unit/research/test_synthesizer_llm.py (3 tests)."
    ```
    Do NOT use `git add -A` / `-u`. Do NOT amend or reset. If Wave 0's test files were
    committed separately already, add only synthesizer.py here.
  </action>
  <verify>
    <automated>git log --oneline -1 && git status --porcelain lib/research/stages/synthesizer.py</automated>
  </verify>
  <acceptance_criteria>
    - `git log --oneline -1` shows the synthesizer commit on HEAD.
    - `git status --porcelain lib/research/stages/synthesizer.py` returns EMPTY (committed, clean).
    - The commit touches ONLY the explicit files listed (no stray `-A` adds) — verify with `git show --stat HEAD`.
    - CLI run output recorded in SUMMARY shows the real-LLM path executed (real prose or graceful-degrade note, not bare stub verbatim).
  </acceptance_criteria>
  <done>Forward-only commit on HEAD containing only the explicit GAP-A files; CLI confidence check recorded.</done>
</task>

</tasks>

<verification>
- `venv/Scripts/python.exe -m pytest tests/unit/research/ tests/integration/test_research_router.py -v` — all green (3 new GAP-A + 10 caption + 12 transport).
- synthesizer.py greps confirm: lazy get_llm_func import, enumerate(sources), BLE001 guard, /static/img/ URL.
- One forward-only commit, explicit git add.
</verification>

<success_criteria>
- Synthesizer emits real LLM prose using all chunks, with [n] citations and woven images.
- LLM failure degrades gracefully (note_line + fallback), never raises.
- All research unit + transport tests green.
</success_criteria>

<output>
After completion, create `.planning/phases/arx-2-finish/arx-2-finish-01-SUMMARY.md`
</output>
