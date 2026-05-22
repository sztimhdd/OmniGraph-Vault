---
phase: ar-2-reasoner-vision-deepening
plan: 02
milestone: Agentic-RAG-v1
wave: 2
status: complete
last_updated: "2026-05-22"
requirements_delivered:
  - ORCH-05
  - TEST-03 (Synthesizer half — closes the data-flow assertion begun in ar-2-01)
files_modified:
  - lib/research/stages/synthesizer.py (replaced ar-1 image-source + emission blocks)
  - tests/unit/research/test_synthesizer_caption_embeds.py (new — 10 tests)
---

# ar-2-02 — Synthesizer Caption-Anchored Image Embeds Summary

## One-liner

Replaced the ar-1 filename-placeholder image emit in
`lib/research/stages/synthesizer.py` with caption-anchored embeds sourced
from `state.reasoned.analyzed_images[i].caption`, with ar-1 filename-fallback
preserved when Reasoner skipped/failed/produced no images (Axis 3
best-effort). Also surfaces `state.reasoned.additional_chunks` (Reasoner
`kg_search` findings) into `result.sources` — gated on Reasoner status="ok"
(plan-checker ruled in-scope per 2026-05-22 session).

## Files modified

| File | LOC | Change |
|---|---|---|
| `lib/research/stages/synthesizer.py` | 138 | Replaced 2 ar-1 blocks (source-collect + image-emit); module docstring updated; `_detect_language`, title/body templates, degradation note_lines, confidence calc all unchanged |
| `tests/unit/research/test_synthesizer_caption_embeds.py` | 387 | New file — 10 mock-based tests covering caption path + 3 fallback paths + URL invariance + caps + Axis 8 + extension + extension-gating |

Surgical updates to ar-1 / ar-2-01 regression suite: **0 lines** — every
existing test passed unmodified. Test 17 in `test_stages_stubs.py`
(synthesizer caps embedded_images at 5) still passes because it leaves
`state.reasoned = None` by default → fallback path engages with cap-of-5
preserved.

## Test count

- New ar-2-02 tests: **10** (all green)
- Full `tests/unit/research/` suite: **79 / 79 passing**
- ar-1 baseline + ar-2-01: 69 passing
- ar-2-02 delta: **+10 new tests, 0 ar-1 / ar-2-01 regressions**

```
============================= 79 passed in 38.67s =============================
```

Plan target was ≥47 (ar-1 ≥35 + ar-2-01 ≥7 + this plan ≥5); delivered 79.

## Test list (new file)

1. `test_synthesizer_uses_reasoned_caption` — TEST-03 hard requirement;
   asserts literal `![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)`
   in `result.markdown` + path-shape regression guard (sealed once)
2. `test_synthesizer_falls_back_to_filename_when_reasoned_none` — ar-1
   regression guard; `state.reasoned=None` → alt text = `img.name`
3. `test_synthesizer_falls_back_when_analyzed_images_empty` — Reasoner ran
   but selected no images → fall back to `retrieved.image_candidates`
4. `test_synthesizer_url_format_unchanged` — URL body byte-for-byte
   identical between caption + fallback paths for matching `image_path`
5. `test_synthesizer_no_status_field` — Axis 8: `dataclasses.fields(SynthesizerOutput)`
   has neither `status` nor `reason`
6. `test_synthesizer_caption_path_caps_at_5` — 8 entries in
   `analyzed_images` → exactly 5 inline image refs + 5 `embedded_images`
7. `test_synthesizer_caption_none_falls_back_to_filename` — defensive
   `or img.image_path.name` guard exercised when caption=None
8. `test_synthesizer_reasoned_additional_chunks_in_sources` —
   plan-checker-ruled extension; Reasoner's kg_search findings surface in
   `result.sources` when `status="ok"`
9. `test_synthesizer_failed_reasoner_does_not_leak_additional_chunks` —
   gating discipline; failed Reasoner's `additional_chunks` NOT surfaced;
   degradation note line `> ❌ Reasoner failed: ...` still appears
10. `test_synthesizer_path_shape_preserved` — `embedded_images: list[Path]`
    contract preserved across both caption + fallback paths

## Caption-path verification (Test 1 markdown excerpt)

```
# Research Answer: test query
## Knowledge Graph Retrieval

seed

## Retrieved Images

![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)
```

The literal substring `![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)`
appears in `result.markdown`. TEST-03 hard requirement satisfied.

## Fallback-path verification (Test 2 markdown excerpt)

```
# Research Answer: test
## Knowledge Graph Retrieval

text

## Retrieved Images

![3.jpg](http://localhost:8765/abc1234567/3.jpg)
```

`state.reasoned=None` → alt text = `img.name`; ar-1 behavior byte-for-byte
preserved.

## Programmatic smoke output

```
$ venv/Scripts/python.exe -X utf8 -c "<smoke harness>"
---MARKDOWN---
# Research Answer: smoke
## Knowledge Graph Retrieval

Hello world

## Retrieved Images

![SMOKE_CAP](http://localhost:8765/deadbeef00/5.jpg)


---

> ⚠️ WebBaseline did not run.
> ⚠️ Verifier did not run.

---END---
```

Caption `SMOKE_CAP` threads from `state.reasoned.analyzed_images[0].caption`
into the markdown alt text; URL format unchanged from ar-1.

## CONTRACT-01 + CONTRACT-02 grep results

```
$ bash scripts/check_contract.sh
CONTRACT-01 ok
CONTRACT-02 ok
```

```
$ grep -rE "from omnigraph_search" lib/research/ --include='*.py' | \
    grep -vE "from omnigraph_search\.query " | \
    grep -vE "from omnigraph_search\.query$" | \
    grep -vE "import omnigraph_search\.query"
(no forbidden hits)

$ grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' | \
    grep -vE "config\.py|README\.md|^Binary"
(no forbidden hits)
```

Both gates clean.

## Axis 8 invariant smoke

```
$ venv/Scripts/python.exe -c "from lib.research.types import SynthesizerOutput; \
    import dataclasses; \
    assert 'status' not in {f.name for f in dataclasses.fields(SynthesizerOutput)}; \
    print('Axis 8 invariant ok')"
Axis 8 invariant ok
```

## ar-1 surgical test edits

**None — zero edits to existing tests.** Every ar-1 + ar-2-01 test passed
unchanged. Specifically:

- Test 17 (`test_synthesizer_caps_embedded_images`) — leaves
  `state.reasoned = None` by default in `ResearchState`; fallback path
  engages naturally and the cap-of-5 is preserved on that branch.
- Test 18, 19 (Chinese / English title) — language detection unchanged;
  no image candidates supplied, so emission block is a no-op.
- Test 20 (`test_synthesizer_handles_none_snippet`) — defensive `or ""`
  guard preserved verbatim.
- Orchestrator Test 1, Test 2 — both use `state.reasoned = None` in
  practice (orchestrator no-llm path produces empty `analyzed_images`),
  fallback path engages, and asserted markdown substrings (`Research Answer`,
  chunk snippet) still appear.

## Deviations from plan

### 1. Reasoner `additional_chunks` extension — gated on `status="ok"`

**What changed**: The plan's `<interfaces>` block proposed
`if state.reasoned is not None and state.reasoned.additional_chunks:`
without a status gate. The implementation tightens this to require
`state.reasoned.status == "ok"` as well, mirroring the gating discipline
applied to `state.retrieved`.

**Rationale**: Without the status gate, a failed Reasoner could leak
partial `additional_chunks` into `result.sources` even though we already
emit a `> ❌ Reasoner failed: ...` degradation note line. Test 9
(`test_synthesizer_failed_reasoner_does_not_leak_additional_chunks`)
encodes this guard. **Plan-checker ruled in-scope** (2026-05-22 session)
— the extension itself is principled because the alternative is silently
losing the Reasoner's KG-tool findings; the gate keeps the principle
consistent with the rest of the stage's degradation handling.

### 2. Test count delta vs plan target

Plan asked for ≥5 new tests; delivered 10. Extras are:
- Tests 6-7: cap + caption=None defensive (covers the `[:5]` invariant
  and the `or img.image_path.name` defense in one direct hit each)
- Tests 8-9: extension + extension-gating (paired tests that cover both
  the principled add and the discipline guard)
- Test 10: list[Path] shape regression guard (sealed once; cheap insurance
  against future contract drift)

No deviation in semantics — every plan-mandated assertion is covered;
extras are surface area additions only.

### 3. Plan-checker nits — addressed inline

- **Test fixture brittleness**: addressed by `_make_minimal_cfg(tmp_path)`
  + `_make_image_file(tmp_path, hash, name)` helpers at the top of the
  test file; no module-scope `pytest.fixture` decorator (the helpers are
  one-line wrappers and stay local to keep imports trivial — matches
  ar-2-01 conftest pattern).
- **Path-shape regression**: `assert isinstance(result.embedded_images[0], Path)`
  in Test 1 + `assert all(isinstance(p, Path) for p in r.embedded_images)`
  in Test 10.
- **`additional_chunks` SUMMARY documentation**: this section.

## Out of scope (deferred per plan)

- Wave 3 CLI flags (`--max-iter-reasoner` / `--max-iter-verifier` /
  `--no-grounding`) — ar-2-03
- Production VisionCascade adapter (Option A deferred) — ar-3+
- Production LLM provider wiring — ar-3+
- Real LLM-driven language detection (Axis 10 ar-4 swap) — ar-4
- Reasoner module changes — frozen post-ar-2-01

## Self-Check: PASSED

- `lib/research/stages/synthesizer.py` exists (FOUND)
- `tests/unit/research/test_synthesizer_caption_embeds.py` exists (FOUND)
- 79 / 79 tests passing in `tests/unit/research/`
- CONTRACT-01 ok / CONTRACT-02 ok
- Axis 8 invariant: `SynthesizerOutput` has no `status` field
- Programmatic smoke: caption `SMOKE_CAP` threads into markdown
- Commit hash: pending (added post-commit)
