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
    - "A rewrite function exists that cleans a dirty article DISPLAY body while pinning every localhost:8765 image URL byte-identical (input = D-14-resolved display content, NOT raw DB body)"
    - "Running the rewrite on 5-10 real dirty samples resolved the SAME way get_article_body resolves display content produces 0 mangled/added/dropped image URLs per sample"
    - "The validated samples INCLUDE image-bearing articles with non-empty localhost:8765 URL sets, so the URL-set diff valve's MAIN defense (localhost preservation) is actually exercised"
    - "The URL-set diff safety valve returns None (reject -> fall back to body) when input vs output URL sets differ"
    - "Output on validated samples has 0 raw HTML tags, 0 remaining boilerplate markers, length >= 20% of input"
  artifacts:
    - path: "lib/rewrite.py"
      provides: "rewrite_body_with_deepseek(title, body_text) + _extract_image_urls() + URL-set diff safety valve — PURE function, caller passes the resolved display content"
      exports: ["rewrite_body_with_deepseek"]
      min_lines: 60
    - path: ".scratch/kb-v2.3-validate-rewrite.py"
      provides: "Validation harness that resolves each candidate's D-14 DISPLAY content from disk (final_content.enriched.md -> final_content.md -> body_cleaned -> body) and runs the prompt + per-gate pass/fail"
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
    - from: ".scratch/kb-v2.3-validate-rewrite.py"
      to: "D-14 display-content resolution (mirrors get_article_body fs read)"
      via: "read {KB_IMAGES_DIR}/{resolve_url_hash(rec)}/final_content.enriched.md -> final_content.md, fall back to body_cleaned/body; localhost:8765 URLs kept intact (no _rewrite_image_paths)"
      pattern: "final_content"
---

<objective>
Design and validate the single LLM semantic rewrite pass that bears the FULL content-cleaning load for this phase (no regex safety net — Decision: "No regex / hand-rolled cleaning"). This is the critical-path GATE that MUST pass before any schema or batch work in plans 02/03.

Produces:
1. `lib/rewrite.py` — a reusable `rewrite_body_with_deepseek(title, body_text)` function that cleans + reformats within the source language, pins image URLs verbatim, and enforces the per-article URL-set diff safety valve (reject -> return None -> caller leaves body_rewritten NULL -> falls back to body, no regression). **The `body_text` arg the caller passes is the D-14-resolved DISPLAY content — NOT raw DB `body`.**
2. `.scratch/kb-v2.3-validate-rewrite.py` — a validation harness that resolves each candidate's DISPLAY content the SAME way `get_article_body()` does (filesystem `final_content.enriched.md` -> `final_content.md`, falling back to `body_cleaned` -> `body`), runs the prompt against 5-10 REAL dirty samples, and prints programmatic pass/fail on every CONTEXT.md prompt gate.
3. `tests/unit/test_rewrite.py` — network-free unit tests pinning the URL-set diff valve behavior.

Purpose: The rewrite-prompt quality is the new critical path. There is no cheap deterministic net, so this plan makes the Task-1 validation an ENFORCEABLE programmatic check (URL-set grep-diff), not eyeballing. Getting the prompt + valve right here de-risks the 572-article backfill in plan 03.

**⚠️ CORRECTED PREMISE (LIVE-PROBE-VERIFIED 2026-07-03):** The original version of this plan assumed the rewrite reads DB `body` and diffs `localhost:8765` URLs in `body`. That premise was FALSED by a live Aliyun probe during Wave-1 execution: DB `body` has ZERO `localhost:8765` URLs (0/467 KOL, 0/109 RSS) — it carries WeChat CDN (`mmbiz.qpic.cn`) + data-URIs. The `localhost:8765` URLs AND the content most users actually see live in filesystem `final_content.md` (D-14 resolves fs first for ~70% of articles). So the rewrite INPUT is the **D-14-resolved DISPLAY content** (what `get_article_body()` returns pre-image-rewrite), NOT raw `body`. This makes `_extract_image_urls(input)` NON-EMPTY so the valve's main defense actually fires. Full rationale: memory `decision_rewrite_display_only_kg_uses_original.md` "CRITICAL CORRECTION" section + CONTEXT.md "⚠️ CORRECTED PREMISE" block.

**Task 1 code is DONE + committed (0565e3e/0bbcc25/45fdc00/2f05622) and its function body + valve logic are SOUND — do NOT rewrite them.** The ONLY changes in this revision: (a) document the caller-contract that the input is D-14 display content (the pure `(title, body_text)` signature STAYS — the CALLER resolves D-14); (b) fix the harness sampling to read the display content from disk (the committed harness's `--with-images` flag uses a WRONG `body LIKE '%localhost:8765%'` predicate — body never has localhost URLs — replace with the fs-read approach).

Output: A validated prompt + a proven rewrite+verify function that plan 03's cron imports lazily, exercised on REAL image-bearing display content.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH-WEB.md
@~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/decision_rewrite_display_only_kg_uses_original.md

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

D-14 DISPLAY-CONTENT resolution — what the harness (Task 2) and plan-03 cron must mirror (from kb/data/article_query.py:587-619 get_article_body + resolve_url_hash 134-153):
```python
# resolve_url_hash (PURE, no DB/fs): wechat -> content_hash or md5(url)[:10]; rss -> content_hash[:10]
# get_article_body reads, IN ORDER, at {KB_IMAGES_DIR}/{url_hash}/:
#   final_content.enriched.md   (fs) -> the display content
#   final_content.md            (fs) -> the display content   (~70% of articles land here or above)
#   rec.body_cleaned or rec.body (db) -> only when NO fs file exists (~30%)
# CRITICAL for the rewrite INPUT: read the RAW fs/db content — do NOT apply _rewrite_image_paths.
# get_article_body converts localhost:8765 -> /static/img/; the rewrite input must KEEP the raw
# localhost:8765 URLs so the valve has real URLs to diff and images survive.
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
  <name>Task 1: lib/rewrite.py — DOCUMENT the input-contract (input = D-14 display content); function body + valve are ALREADY committed and SOUND, do not rewrite</name>
  <files>lib/rewrite.py, tests/unit/test_rewrite.py</files>
  <read_first>
    - lib/rewrite.py (ALREADY EXISTS — committed 0565e3e/0bbcc25/45fdc00/2f05622; read it in full before touching)
    - tests/unit/test_rewrite.py (ALREADY EXISTS — 7 mocked tests; read before touching)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/decision_rewrite_display_only_kg_uses_original.md ("CRITICAL CORRECTION" section — the input-source correction)
    - kb/data/article_query.py (lines 587-619 get_article_body, 134-153 resolve_url_hash — the resolution the caller-contract references)
    - lib/translate.py (lines 35-41 constants, 70-82 detect_source_lang, 274-285 DeepSeek call pattern)
    - lib/__init__.py (confirm eager deepseek import — the DEEPSEEK_API_KEY guard reason)
  </read_first>
  <behavior>
    The 7 committed tests already cover the valve + lazy-import + prompt-constants:
    - Test 1 (RW-VALVE-PASS): identical localhost:8765 URL set -> valve accepts, returns cleaned string.
    - Test 2 (RW-VALVE-REJECT-DROP): output missing one localhost:8765 URL -> None.
    - Test 3 (RW-VALVE-REJECT-ADD): output has an extra/hallucinated localhost:8765 URL -> None.
    - Test 4 (RW-VALVE-REJECT-MUTATE): mutated URL (shortened path) -> None.
    - Test 5 (RW-EMPTY): LLM returns empty/whitespace -> None (no crash).
    - Test 6 (RW-PROMPT-CONSTANTS): prompt contains the image-URL-verbatim constraint AND the boilerplate markers checklist (关注公众号, 点赞, 扫码).
    - Test 7 (RW-LAZY-IMPORT): with DEEPSEEK_API_KEY unset, `import lib.rewrite` succeeds with NO RuntimeError (no lib.* import at module top).
    These MUST stay green after this revision — they test behavior that is UNCHANGED. Do NOT add tests that require passing a record or fs read into rewrite_body_with_deepseek (the function stays pure: it takes a string body_text and does not know or care that the caller resolved it from disk).
  </behavior>
  <action>
This is a DOCUMENTATION-ONLY revision to the ALREADY-COMMITTED `lib/rewrite.py`. The function body, the prompt, the `_extract_image_urls` helper, and the URL-set diff valve are SOUND and must NOT be re-implemented (they were committed in 0565e3e/0bbcc25/45fdc00/2f05622 and the 7 tests are green). Only the caller-CONTRACT wording changes.

1. KEEP the signature `async def rewrite_body_with_deepseek(title: str, body_text: str) -> str | None` PURE (RECOMMENDED per revision brief — keeps the tested function unchanged; the CALLER resolves D-14). If the committed parameter name is `body`, you MAY rename it to `body_text` for clarity OR leave it as `body` — either is acceptable; do NOT change the arity or the logic.

2. Update the function docstring to state the caller-contract EXPLICITLY:
   ```
   The `body_text` argument MUST be the D-14-resolved DISPLAY content — i.e. exactly
   what get_article_body() would return for this article BEFORE image-path rewriting
   (filesystem final_content.enriched.md -> final_content.md -> body_cleaned -> body).
   It must still contain raw `http://localhost:8765/{hash}/{name}` URLs so the URL-set
   diff valve has real URLs to diff. Do NOT pass raw DB `body` — DB body carries WeChat
   CDN (mmbiz.qpic.cn) URLs, not localhost URLs, which makes the valve inert (∅==∅).
   The CALLER (validation harness / rewrite_body_cron.py) is responsible for the D-14
   resolution; this function is pure and only cleans + valve-checks the string it is given.
   ```
   Add a one-line module-level comment near the valve pointing at `decision_rewrite_display_only_kg_uses_original.md` "CRITICAL CORRECTION" so the input-source expectation is discoverable at the call site.

3. Do NOT touch: `_extract_image_urls`, `IMAGE_URL_RE`, `_build_rewrite_prompt`, `_REWRITE_MODEL`, `REWRITE_BODY_TIMEOUT_S`, the `asyncio.wait_for` call, the valve comparison, or the lazy-import discipline. If a `git diff` of `lib/rewrite.py` for this task shows ANY change outside docstrings/comments, revert it.

4. Do NOT modify `tests/unit/test_rewrite.py` UNLESS a test hard-codes an assumption that the input is raw `body` (it should not — the tests are about valve behavior on arbitrary strings). Re-run the suite to confirm still-green.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_rewrite.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def rewrite_body_with_deepseek" lib/rewrite.py` == 1 and it is `async def` (UNCHANGED signature — pure string in/out).
    - `grep -c "def _extract_image_urls" lib/rewrite.py` == 1 (unchanged).
    - The docstring of `rewrite_body_with_deepseek` mentions "D-14" AND "display" AND "localhost:8765" (input-contract documented): `grep -A20 "def rewrite_body_with_deepseek" lib/rewrite.py | grep -iE "D-14|display|localhost:8765"` matches.
    - `grep "http://localhost:8765/" lib/rewrite.py` matches (URL constraint present in prompt + regex — unchanged).
    - `grep -E "关注公众号|点赞|扫码" lib/rewrite.py` matches (boilerplate checklist embedded in prompt — unchanged).
    - `grep "_REWRITE_MODEL" lib/rewrite.py | grep "deepseek-v4-pro"` matches (model pinned — unchanged).
    - LAZY IMPORT still enforced: `grep -n "from lib.translate\|from lib.llm_deepseek\|import lib" lib/rewrite.py` shows every such import FUNCTION-BODY-INDENTED (>= 4 leading spaces), NOT at module top. Test 7 (RW-LAZY-IMPORT) still passes.
    - `git diff lib/rewrite.py` for this task shows ONLY docstring/comment changes (no logic change) — confirm the valve + prompt + helpers are byte-unchanged.
    - `venv/Scripts/python.exe -m pytest tests/unit/test_rewrite.py -v` — all 7 committed tests still pass, 0 network calls.
  </acceptance_criteria>
  <done>lib/rewrite.py's function body + valve + prompt are UNCHANGED (still the committed 0565e3e/... code); only the docstring now documents that the input is D-14 display content (not raw body) and points at the CRITICAL CORRECTION memory; the 7 committed tests are still green.</done>
</task>

<task type="auto">
  <name>Task 2: Fix .scratch/kb-v2.3-validate-rewrite.py sampling — resolve each candidate's D-14 DISPLAY content from disk (replace the WRONG body-LIKE-localhost predicate)</name>
  <files>.scratch/kb-v2.3-validate-rewrite.py</files>
  <read_first>
    - .scratch/kb-v2.3-validate-rewrite.py (ALREADY EXISTS — committed with a `--with-images` flag whose `body LIKE '%localhost:8765%'` predicate is WRONG; read it in full)
    - lib/rewrite.py (the function under exercise — pure string in/out)
    - kb/data/article_query.py (lines 587-619 get_article_body, 134-153 resolve_url_hash — MIRROR this resolution to build the rewrite INPUT; but do NOT call _rewrite_image_paths — keep localhost URLs)
    - scripts/translate_body_cron.py (lines 48-49 DEEPSEEK_API_KEY guard, 52-54 sys.path bootstrap, 62-78 _resolve_db_path — copy verbatim for DB access)
    - config.py (KB_IMAGES_DIR / BASE_IMAGE_DIR — the {hash} dir root; confirm the exact attribute name)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md (success_criteria Stage 1 prompt gate — the 5 checks this harness must automate)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/decision_rewrite_display_only_kg_uses_original.md (CRITICAL CORRECTION — why body-LIKE-localhost is wrong: body has 0 localhost URLs)
    - CLAUDE.md ("Always use scripts/local_e2e.sh" / corp-network + DEEPSEEK egress notes — document whether this runs on the corp laptop or is copied to Aliyun)
  </read_first>
  <action>
The committed harness pulls samples via `SELECT body ... WHERE body LIKE '%localhost:8765%'` (the `--with-images` flag). This is WRONG: DB `body` has ZERO `localhost:8765` URLs (verified 0/467 KOL, 0/109 RSS) — that predicate returns nothing, and any body it did return would be CDN-URL content that makes `_extract_image_urls(input)` empty and the valve inert. REPLACE the sampling with the D-14 display-content read from disk. Concrete requirements:

1. KEEP VERBATIM (already present): the `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` guard, sys.path bootstrap, and `_resolve_db_path()` from translate_body_cron.py:48-78.

2. Change the candidate SELECT to fetch the columns needed to resolve the fs hash (NOT `WHERE body LIKE '%localhost:8765%'`). SELECT `id, source_or_table, title, url, content_hash, body_cleaned, body` from `articles` (source='wechat') and `rss_articles` (source='rss') with the DATA-07 filter `layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL AND body != '' AND body_rewritten IS NULL`. Keep the `--limit N` argparse (default 8).

3. Add a `_resolve_display_content(source, content_hash, url, body_cleaned, body) -> str` helper that MIRRORS get_article_body's fs read but returns the RAW markdown (do NOT apply _rewrite_image_paths — keep localhost:8765 intact):
   - compute `url_hash` per resolve_url_hash rules (wechat: content_hash or md5(url)[:10]; rss: content_hash[:10]);
   - for fname in ("final_content.enriched.md", "final_content.md"): read `{KB_IMAGES_DIR}/{url_hash}/{fname}` if it exists, return its text;
   - else return `body_cleaned or body or ""`.
   This is exactly the display content the LLM must clean and the localhost URLs the valve diffs.

4. SAMPLING STRATEGY (fixes the prior blind spot): among the candidates, PREFER rows whose resolved display content has a NON-EMPTY localhost:8765 URL set (i.e. `_extract_image_urls(resolved) != set()`). Order/select so that the run INCLUDES at least 3 image-bearing samples — the prior 0-image run left the valve's main defense untested (the exact blind spot that caused this re-plan). Also include the longest resolved body (order by resolved length DESC among image-bearing) to exercise near-30K content.

5. For each sample, `await rewrite_body_with_deepseek(title, resolved_display_content)` and run the 5 CONTEXT.md programmatic gates, printing PASS/FAIL per gate per sample:
   - GATE-URL: `_extract_image_urls(resolved_input) == _extract_image_urls(output)` (byte-identical set). If the function returned None, mark REJECTED-BY-VALVE (a SAFE outcome, not a harness failure).
   - GATE-HTML: output contains 0 of `<script`, `<style`, `<div` (grep-count == 0).
   - GATE-BOILERPLATE: 0 of `关注公众号`, `点赞`, `扫码` and subscription-CTA markers remain in output.
   - GATE-MARKDOWNLINT: pipe output through markdownlint (or a minimal in-process check if markdownlint CLI unavailable — document which); 0 errors.
   - GATE-LENGTH: `len(output) >= 0.20 * len(resolved_input)`.

6. Print a summary table: samples run, IMAGE-BEARING sample count (MUST be >= 3), per-gate pass counts, valve-reject count. Exit code 0 ONLY if: (a) >= 3 image-bearing samples were run, AND (b) every non-rejected sample passes ALL gates, AND (c) valve-reject rate < 30%.

7. Write the raw input/output pairs to `.scratch/kb-v2.3-rewrite-samples/` for eyeball review (Task 3).

This harness is the ENFORCEABLE form of the CONTEXT.md "PROMPT VALIDATION GATE (blocks batch)". Its exit-0 (now REQUIRING image-bearing samples) is the gate that unblocks plan 03's backfill.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe .scratch/kb-v2.3-validate-rewrite.py --limit 8</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "body LIKE '%localhost:8765%'" .scratch/kb-v2.3-validate-rewrite.py` == 0 (the WRONG body-predicate is REMOVED).
    - `grep -c "final_content" .scratch/kb-v2.3-validate-rewrite.py` >= 1 (the fs display-content read is present).
    - `grep -E "resolve_url_hash|content_hash.*md5|md5\(.*url" .scratch/kb-v2.3-validate-rewrite.py` matches (url-hash resolution mirrors get_article_body, handles NULL content_hash for wechat).
    - Harness runs against the LIVE DB (real DeepSeek calls) on >= 5 dirty samples without crashing, and >= 3 of them are IMAGE-BEARING (non-empty localhost:8765 URL set in the resolved input) — the summary table prints the image-bearing count and it is >= 3.
    - Exit code 0: >= 3 image-bearing samples run AND every non-valve-rejected sample passes all 5 gates (URL-set byte-identical, 0 HTML tags, 0 boilerplate markers, markdownlint 0 errors, length >= 20%) AND valve-reject rate < 30%.
    - `.scratch/kb-v2.3-rewrite-samples/` contains the input/output pairs for the run (incl. at least one image-bearing pair).
    - The SUMMARY.md for this plan cites the harness output (image-bearing count + per-gate pass counts + valve-reject count) as the batch-unblock evidence.
  </acceptance_criteria>
  <done>Harness resolves each candidate's D-14 display content from disk (final_content.enriched.md -> final_content.md -> body_cleaned -> body, localhost URLs intact), NOT the WRONG body-LIKE-localhost predicate; runs >= 3 image-bearing samples so the URL valve's main defense is exercised; exit 0 with 0 mangled URLs on accepted samples and < 30% valve rejects; evidence cited in SUMMARY.md.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Human eyeball of rewrite quality on real IMAGE-BEARING samples (subjective readability the gates can't catch)</name>
  <files>.scratch/kb-v2.3-rewrite-samples/</files>
  <action>
This is a human-verification checkpoint (no code change). The executor presents the validation-harness output and the input/output sample pairs for operator review of SUBJECTIVE readability that the programmatic gates cannot catch (e.g. sensible paragraph reflow, no wrongly-deleted substantive content, natural image reference lines, images preserved). The executor takes NO further action until the operator responds to the resume-signal.
  </action>
  <what-built>
    lib/rewrite.py (clean rewrite + URL-set diff valve — function body unchanged from the committed version, docstring now documents the D-14 display-content input contract) and .scratch/kb-v2.3-validate-rewrite.py, which resolves each sample's D-14 DISPLAY content from disk and ran the prompt on >= 8 real dirty article bodies (>= 3 IMAGE-BEARING) and passed all programmatic gates (0 mangled URLs, 0 HTML, 0 boilerplate, markdownlint clean, length >= 20%).
  </what-built>
  <how-to-verify>
    1. Open the input/output pairs in `.scratch/kb-v2.3-rewrite-samples/`.
    2. For 3-4 pairs — INCLUDING at least 2 IMAGE-BEARING pairs (non-empty localhost:8765 URL set) — read the OUTPUT as a human: is it a clean, well-structured article? Are paragraphs reflowed sensibly? Are code blocks / lists intact? Is any SUBSTANTIVE content wrongly deleted (the gates only catch length < 20%, not "dropped the one important paragraph")?
    3. Confirm the localhost:8765 image reference lines still read naturally and the URLs are untouched (this is now testable because the input is real display content with real localhost URLs — the prior all-0-image run could not verify this).
    4. Spot-check the longest sample (near the 30K range) for truncation.
  </how-to-verify>
  <verify>
    <automated>ls .scratch/kb-v2.3-rewrite-samples/ | head</automated>
  </verify>
  <resume-signal>Type "approved" to unblock the schema + backfill plans, or describe prompt issues to iterate Task 1/2 before proceeding.</resume-signal>
  <done>Operator has read >= 3 rewrite input/output pairs (>= 2 image-bearing) and confirmed subjective readability (sensible reflow, no substantive content dropped, localhost image lines untouched, no truncation on the longest sample); "approved" recorded to unblock plans 02/03.</done>
</task>

</tasks>

<verification>
- lib/rewrite.py function body + valve UNCHANGED (docstring-only revision); importable with no network and no DEEPSEEK_API_KEY (lazy lib import inside function).
- tests/unit/test_rewrite.py still green (7 committed mocked behavior tests, incl. RW-LAZY-IMPORT).
- .scratch/kb-v2.3-validate-rewrite.py resolves D-14 display content from disk, exit 0 on >= 5 real dirty samples (>= 3 image-bearing): 0 mangled URLs on accepted samples, all gates pass, valve-reject < 30%.
- Human approval of subjective readability recorded on image-bearing samples (Task 3).
</verification>

<success_criteria>
The CONTEXT.md "PROMPT VALIDATION GATE (blocks batch)" is satisfied and ENFORCEABLE, exercised on REAL image-bearing display content:
- The rewrite INPUT is the D-14-resolved DISPLAY content (not raw body) — documented in lib/rewrite.py's caller-contract and implemented in the harness's fs read.
- For each validated sample: every localhost:8765 URL byte-identical (0 mangled), 0 boilerplate markers, 0 raw HTML tags, markdownlint 0 errors, length >= 20% of original.
- >= 3 image-bearing samples run so the URL-set diff valve's MAIN defense actually fires (fixes the prior blind spot).
- A reusable rewrite+verify function exists for plan 03's cron to import (pure signature preserved).
</success_criteria>

<output>
After completion, create `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-1-rewrite-prompt-validation-SUMMARY.md`.
</output>
