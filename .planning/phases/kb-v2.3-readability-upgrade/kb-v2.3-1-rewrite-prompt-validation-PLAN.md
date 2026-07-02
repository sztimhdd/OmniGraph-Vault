---
phase: kb-v2.3-readability-upgrade
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/rewrite.py
  - tests/unit/test_rewrite.py
  - .scratch/kb-v2.3-validate-rewrite.py
autonomous: false
requirements: [PROMPT-GATE]
must_haves:
  truths:
    - "A rewrite function exists that cleans a dirty WeChat body while pinning every localhost:8765 image URL byte-identical"
    - "Running the rewrite on 5-10 real dirty samples produces 0 mangled/added/dropped image URLs per sample"
    - "The URL-set diff safety valve returns None (reject -> fall back to body) when input vs output URL sets differ"
    - "Output on validated samples has 0 raw HTML tags, 0 remaining boilerplate markers, length >= 20% of input"
  artifacts:
    - path: "lib/rewrite.py"
      provides: "rewrite_body_with_deepseek() + _extract_image_urls() + URL-set diff safety valve"
      exports: ["rewrite_body_with_deepseek"]
      min_lines: 60
    - path: ".scratch/kb-v2.3-validate-rewrite.py"
      provides: "Standalone validation harness that runs the prompt on real dirty samples and prints per-sample pass/fail on all gates"
    - path: "tests/unit/test_rewrite.py"
      provides: "Unit tests for URL-set diff valve + prompt-constant presence (mocked LLM, no network)"
  key_links:
    - from: "lib/rewrite.py:rewrite_body_with_deepseek"
      to: "lib/llm_deepseek.py:deepseek_model_complete"
      via: "await asyncio.wait_for(deepseek_model_complete(prompt, model=_REWRITE_MODEL), timeout=REWRITE_BODY_TIMEOUT_S)"
      pattern: "deepseek_model_complete"
    - from: "lib/rewrite.py:rewrite_body_with_deepseek"
      to: "URL-set diff safety valve"
      via: "compare _extract_image_urls(input) vs _extract_image_urls(output); return None if sets differ"
      pattern: "_extract_image_urls"
---

<objective>
Design and validate the single LLM semantic rewrite pass that bears the FULL content-cleaning load for this phase (no regex safety net — Decision: "No regex / hand-rolled cleaning"). This is the critical-path GATE that MUST pass before any schema or batch work in plans 02/03.

Produces:
1. `lib/rewrite.py` — a reusable `rewrite_body_with_deepseek(title, body)` function that cleans + reformats within the source language, pins image URLs verbatim, and enforces the per-article URL-set diff safety valve (reject -> return None -> caller leaves body_rewritten NULL -> falls back to body, no regression).
2. `.scratch/kb-v2.3-validate-rewrite.py` — a validation harness that runs the prompt against 5-10 REAL dirty WeChat article bodies pulled from the live DB and prints programmatic pass/fail on every CONTEXT.md prompt gate.
3. `tests/unit/test_rewrite.py` — network-free unit tests pinning the URL-set diff valve behavior.

Purpose: The rewrite-prompt quality is the new critical path. There is no cheap deterministic net, so this plan makes the Task-1 validation an ENFORCEABLE programmatic check (URL-set grep-diff), not eyeballing. Getting the prompt + valve right here de-risks the 572-article backfill in plan 03.

Output: A validated prompt + a proven rewrite+verify function that plan 03's cron imports lazily.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH-WEB.md

<interfaces>
<!-- Contracts the executor needs. Extracted from the codebase — do NOT re-explore. -->

From lib/translate.py (the wrapper to MIRROR, do NOT rebuild):
```python
# lines 35-41 — constants
TRANSLATE_TITLE_TIMEOUT_S: float = 15.0
TRANSLATE_BODY_TIMEOUT_S: float = 300.0
_BAKE_MODEL: str = "deepseek-v4-pro"   # body work pins the model explicitly, ignores module _MODEL env

# lines 70-82 — reuse unchanged for source-lang detection
def detect_source_lang(text: str) -> str: ...   # Chinese-char-ratio based, handles empty string

# lines 274-285 — the DeepSeek call shape to replicate
translated = await asyncio.wait_for(
    deepseek_model_complete(prompt, model=_BAKE_MODEL),
    timeout=TRANSLATE_BODY_TIMEOUT_S,
)
cleaned = (translated or "").strip()
if not cleaned:
    return None
```

From lib/llm_deepseek.py:
```python
async def deepseek_model_complete(prompt: str, model: str = ...) -> str: ...
# NOTE: lib/__init__.py eagerly imports this; DEEPSEEK_API_KEY must be set (or 'dummy') at import time.
```

SSG image-URL contract (image URLs MUST survive verbatim — from kb/data/article_query.py):
```python
# the SSG rewrite depends on the EXACT prefix 'http://localhost:8765/' + ![](...) form
_IMAGE_SERVER_REWRITE  # rewrites 'http://localhost:8765/' -> '{KB_BASE_PATH}/static/img/'
```
Image reference lines in the appended block look like: `Image N from article '{title}': http://localhost:8765/{hash}/{name}`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write lib/rewrite.py — rewrite function + URL-set diff safety valve + prompt constant</name>
  <files>lib/rewrite.py, tests/unit/test_rewrite.py</files>
  <read_first>
    - lib/translate.py (lines 35-41 constants, 70-82 detect_source_lang, 149-195 boilerplate-strip prompt to adapt, 274-285 DeepSeek call pattern)
    - lib/llm_deepseek.py (deepseek_model_complete signature, import-time key requirement)
    - lib/__init__.py (confirm eager deepseek import — the DEEPSEEK_API_KEY guard reason)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md (Finding 6 — DeepSeek wrapper patterns to reuse; Pitfall 6 image URL mangling)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH-WEB.md (Section A markdown-cleaning prompt patterns, Section B image-URL verbatim technique)
    - kb-v2.3-CONTEXT.md (success_criteria Stage 1 prompt gate — copy the checklist verbatim into the prompt)
  </read_first>
  <behavior>
    - Test 1 (RW-VALVE-PASS): given input body + an output whose localhost:8765 URL set is IDENTICAL, the valve accepts and returns the cleaned string.
    - Test 2 (RW-VALVE-REJECT-DROP): output missing one localhost:8765 URL -> valve returns None.
    - Test 3 (RW-VALVE-REJECT-ADD): output has an extra/hallucinated localhost:8765 URL -> valve returns None.
    - Test 4 (RW-VALVE-REJECT-MUTATE): output has a mutated URL (e.g. shortened path) -> valve returns None.
    - Test 5 (RW-EMPTY): LLM returns empty/whitespace -> function returns None (no crash).
    - Test 6 (RW-PROMPT-CONSTANTS): the prompt string contains the literal image-URL-verbatim constraint AND the boilerplate markers checklist (关注公众号, 点赞, 扫码).
    - Test 7 (RW-LAZY-IMPORT / Pitfall 2): with DEEPSEEK_API_KEY unset in the environment, `import lib.rewrite` succeeds with NO RuntimeError (the module must NOT import lib.translate / lib.llm_deepseek at module top — detect_source_lang + deepseek_model_complete are imported INSIDE rewrite_body_with_deepseek). Use monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False) + importlib to force a fresh import.
    These are all mockable with no network — patch deepseek_model_complete.
  </behavior>
  <action>
Create `lib/rewrite.py` mirroring `lib/translate.py` structure but simpler (no Tavily, no target-lang, no title output). Concrete requirements:

1. Module constants (mirror translate.py lines 35-41):
   ```python
   REWRITE_BODY_TIMEOUT_S: float = 300.0
   _REWRITE_MODEL: str = "deepseek-v4-pro"   # pin explicitly per RESEARCH Finding 6; steady-state stays on this (Open Question 2 recommendation)
   IMAGE_URL_RE = re.compile(r"http://localhost:8765/\S+")
   ```

2. `_extract_image_urls(text: str) -> set[str]` — return the SET of `http://localhost:8765/...` URLs via `IMAGE_URL_RE.findall`. Strip trailing markdown punctuation `)`, `]`, `>` so `![](http://localhost:8765/a/0.jpg)` and a bare reference-line URL compare equal.

3. `_build_rewrite_prompt(title: str, body: str, src_lang: str) -> str` — adapt translate.py's boilerplate-strip prompt (lines 149-195) but WITHOUT any "translate to X" instruction. The task is: clean + reformat WITHIN `src_lang`. The prompt MUST include (copy CONTEXT.md success-gate checklist verbatim):
   - Strip ads/boilerplate/tracking-JS: `关注公众号`, `点赞`, `在看`, `扫码`, `转载声明`, `作者简介`, subscription CTAs, nav residue.
   - Strip lead filler (`今天我们来聊`, `大家好`, `本文将介绍`).
   - Reflow paragraphs, fix headings/lists/code-blocks. Preserve structural elements (headers=chunk boundaries; lists stay lists; code blocks stay code blocks) — RESEARCH-WEB Section A.
   - Output markdown ONLY, no raw HTML (`<script>`, `<style>`, `<div>` forbidden in output).
   - CRITICAL image constraint (RESEARCH-WEB Section B — include a positive+negative few-shot pair): "Image URLs of the form `http://localhost:8765/{hash}/{name}` and the `![...](...)` markdown around them MUST be reproduced BYTE-FOR-BYTE. Never alter, shorten, or invent a URL. Treat image lines as opaque tokens — do NOT describe or improve images." Preserve the appended `Image N from article '{title}': <url>` reference lines' URLs too.
   - Use explicit delimiters around the dirty input (RESEARCH-WEB Section A — reduces hallucination): wrap the body in a clearly-marked fenced block.
   - Do NOT over-delete: keep all substantive content (guard the >=20% length gate).

4. `async def rewrite_body_with_deepseek(title: str, body: str) -> str | None`:
   - `src_lang = detect_source_lang(body)` (import from lib.translate).
   - Build prompt, call `await asyncio.wait_for(deepseek_model_complete(prompt, model=_REWRITE_MODEL), timeout=REWRITE_BODY_TIMEOUT_S)` (mirror translate.py 274-285).
   - `cleaned = (result or "").strip()`; if not cleaned -> return None.
   - SAFETY VALVE (the locked per-article check): `if _extract_image_urls(body) != _extract_image_urls(cleaned): return None` — reject, caller leaves body_rewritten NULL, falls back to body (no regression). Log at WARNING with the symmetric-difference URL set when rejecting.
   - Return `cleaned`.

Keep the module under ~100 lines. Type-annotate all signatures (PEP 8). Use logging, not print.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_rewrite.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def rewrite_body_with_deepseek" lib/rewrite.py` == 1 and it is `async def`.
    - `grep -c "def _extract_image_urls" lib/rewrite.py` == 1.
    - `grep "http://localhost:8765/" lib/rewrite.py` matches (URL constraint present in prompt + regex).
    - `grep -E "关注公众号|点赞|扫码" lib/rewrite.py` matches (boilerplate checklist embedded in prompt).
    - `grep "_REWRITE_MODEL" lib/rewrite.py | grep "deepseek-v4-pro"` matches (model pinned, not env).
    - `grep -c "asyncio.wait_for" lib/rewrite.py` >= 1 and `grep "deepseek_model_complete" lib/rewrite.py` matches.
    - LAZY IMPORT enforced (Pitfall 2): `grep -n "from lib.translate\|from lib.llm_deepseek\|import lib" lib/rewrite.py` shows every such import is FUNCTION-BODY-INDENTED (>= 4 leading spaces), NOT at module top (column 0). Equivalently, Test 7 (RW-LAZY-IMPORT) proves `import lib.rewrite` succeeds with DEEPSEEK_API_KEY unset — no RuntimeError.
    - `venv/Scripts/python.exe -m pytest tests/unit/test_rewrite.py -v` — all 7 behavior tests pass, 0 network calls (deepseek_model_complete mocked).
  </acceptance_criteria>
  <done>lib/rewrite.py exists with rewrite_body_with_deepseek + _extract_image_urls + URL-set diff valve; tests/unit/test_rewrite.py green with 7 mocked tests (incl. RW-LAZY-IMPORT); no import-time crash (module importable with DEEPSEEK_API_KEY unset because it does not import lib.* at module top — lazy detect_source_lang import inside the function, matching translate cron discipline).</done>
</task>

<task type="auto">
  <name>Task 2: Write .scratch/kb-v2.3-validate-rewrite.py — real-sample validation harness</name>
  <files>.scratch/kb-v2.3-validate-rewrite.py</files>
  <read_first>
    - lib/rewrite.py (the function just built — this is the file under exercise)
    - scripts/translate_body_cron.py (lines 48-49 DEEPSEEK_API_KEY guard, 52-54 sys.path bootstrap, 62-78 _resolve_db_path — copy verbatim for DB access)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md (success_criteria Stage 1 prompt gate — the 5 checks this harness must automate)
    - CLAUDE.md ("Always use scripts/local_e2e.sh" / corp-network + DEEPSEEK egress notes — this runs on the corp laptop OR is copied to Aliyun; document which)
  </read_first>
  <action>
Create `.scratch/kb-v2.3-validate-rewrite.py` — a standalone harness (NOT a pytest file; it makes real DeepSeek calls) that proves the prompt on real dirty data. Structure:

1. Copy the `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` guard, sys.path bootstrap, and `_resolve_db_path()` from translate_body_cron.py:48-78 VERBATIM.
2. `--limit N` argparse (default 8) — how many real dirty samples to pull.
3. Pull N candidate rows from the live DB with the DATA-07 filter (mirror the SELECT WHERE in translate cron, but pick the DIRTIEST samples — order by `length(body) DESC` so you exercise long/messy bodies incl. near the 30K guard). SELECT `id, title, body` from `articles WHERE layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL AND body != '' AND body_rewritten IS NULL`.
4. For each sample, `await rewrite_body_with_deepseek(title, body)` and run the 5 CONTEXT.md programmatic gates, printing PASS/FAIL per gate per sample:
   - GATE-URL: `_extract_image_urls(input) == _extract_image_urls(output)` (byte-identical set). If the function returned None, mark this sample REJECTED-BY-VALVE and count it (a valve reject is a SAFE outcome, not a harness failure).
   - GATE-HTML: `output` contains 0 of `<script`, `<style`, `<div` (grep-count == 0).
   - GATE-BOILERPLATE: 0 of `关注公众号`, `点赞`, `扫码` and subscription-CTA markers remain in output.
   - GATE-MARKDOWNLINT: pipe output through markdownlint (or a minimal in-process check if markdownlint CLI unavailable — document which); 0 errors.
   - GATE-LENGTH: `len(output) >= 0.20 * len(input)`.
5. Print a summary table: samples run, per-gate pass counts, valve-reject count. Exit code 0 ONLY if every non-rejected sample passes ALL gates AND valve-reject rate is < 30% (a high reject rate means the prompt is mangling URLs and must be tuned before batch).
6. Write the raw input/output pairs to `.scratch/kb-v2.3-rewrite-samples/` for eyeball review.

This harness is the ENFORCEABLE form of the CONTEXT.md "PROMPT VALIDATION GATE (blocks batch)". Its exit-0 is the gate that unblocks plan 03's backfill.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe .scratch/kb-v2.3-validate-rewrite.py --limit 8</automated>
  </verify>
  <acceptance_criteria>
    - Harness runs against the LIVE DB (real DeepSeek calls) on >= 5 dirty samples without crashing.
    - Exit code 0: every non-valve-rejected sample passes all 5 gates (URL-set byte-identical, 0 HTML tags, 0 boilerplate markers, markdownlint 0 errors, length >= 20%).
    - Valve-reject rate < 30% across the sample (else the prompt needs tuning — iterate Task 1 prompt and re-run).
    - `.scratch/kb-v2.3-rewrite-samples/` contains the input/output pairs for the run.
    - The SUMMARY.md for this plan cites the harness output (per-gate pass counts + valve-reject count) as the batch-unblock evidence.
  </acceptance_criteria>
  <done>Harness prints a per-sample per-gate PASS table with exit 0; the prompt is proven on real dirty data with 0 mangled URLs on accepted samples and < 30% valve rejects; evidence cited in SUMMARY.md.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Human eyeball of rewrite quality on real samples (subjective readability the gates can't catch)</name>
  <files>.scratch/kb-v2.3-rewrite-samples/</files>
  <action>
This is a human-verification checkpoint (no code change). The executor presents the validation-harness output and the input/output sample pairs for operator review of SUBJECTIVE readability that the programmatic gates cannot catch (e.g. sensible paragraph reflow, no wrongly-deleted substantive content, natural image reference lines). The executor takes NO further action until the operator responds to the resume-signal.
  </action>
  <what-built>
    lib/rewrite.py (clean rewrite + URL-set diff valve) and .scratch/kb-v2.3-validate-rewrite.py, which ran the prompt on >= 8 real dirty WeChat bodies and passed all programmatic gates (0 mangled URLs, 0 HTML, 0 boilerplate, markdownlint clean, length >= 20%).
  </what-built>
  <how-to-verify>
    1. Open the input/output pairs in `.scratch/kb-v2.3-rewrite-samples/`.
    2. For 3-4 pairs, read the OUTPUT as a human: is it a clean, well-structured article? Are paragraphs reflowed sensibly? Are code blocks / lists intact? Is any SUBSTANTIVE content wrongly deleted (the gates only catch length < 20%, not "dropped the one important paragraph")?
    3. Confirm image reference lines still read naturally and the URLs are untouched.
    4. Spot-check the longest sample (near the 30K/154K range) for truncation.
  </how-to-verify>
  <verify>
    <automated>ls .scratch/kb-v2.3-rewrite-samples/ | head</automated>
  </verify>
  <resume-signal>Type "approved" to unblock the schema + backfill plans, or describe prompt issues to iterate Task 1/2 before proceeding.</resume-signal>
  <done>Operator has read >= 3 rewrite input/output pairs and confirmed subjective readability (sensible reflow, no substantive content dropped, natural image lines, no truncation on the longest sample); "approved" recorded to unblock plans 02/03.</done>
</task>

</tasks>

<verification>
- lib/rewrite.py importable with no network and no DEEPSEEK_API_KEY (lazy lib import inside function).
- tests/unit/test_rewrite.py green (7 mocked behavior tests, incl. RW-LAZY-IMPORT enforcing Pitfall 2).
- .scratch/kb-v2.3-validate-rewrite.py exit 0 on >= 5 real dirty samples: 0 mangled URLs on accepted samples, all gates pass, valve-reject < 30%.
- Human approval of subjective readability recorded (Task 3).
</verification>

<success_criteria>
The CONTEXT.md "PROMPT VALIDATION GATE (blocks batch)" is satisfied and ENFORCEABLE:
- For each validated sample: every localhost:8765 URL byte-identical (0 mangled), 0 boilerplate markers, 0 raw HTML tags, markdownlint 0 errors, length >= 20% of original.
- The per-article URL-set diff safety valve is implemented and unit-tested (reject -> None -> body fallback).
- A reusable rewrite+verify function exists for plan 03's cron to import.
</success_criteria>

<output>
After completion, create `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-1-rewrite-prompt-validation-SUMMARY.md`.
</output>
