---
phase: quick-260510-uai
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_ingest_from_spider.py
  - ingest_wechat.py
  - tests/unit/test_text_first_ingest.py
  - tests/unit/test_checkpoint_ingest_integration.py
  - tests/unit/test_ingest_article_processed_gate.py
  - tests/unit/test_rollback_on_timeout.py
  - .planning/STATE.md
autonomous: true
requirements:
  - UAI-01  # source threaded from outer dispatch into doc_id
  - UAI-02  # doc_id format = <source>_<article_hash>, default 'wechat'
  - UAI-03  # body-length fail-fast at MIN_INGEST_BODY_LEN=500 before ainsert
  - UAI-04  # tests updated + 3 new tests added; baseline pytest unchanged
  - UAI-05  # test_ainsert_persistence_contract.py untouched (gkw WIP guard)

must_haves:
  truths:
    - "T1: Every URL dispatched from batch_ingest_from_spider carries a `source` label down through `ingest_article` and into doc_id construction."
    - "T2: doc_id format is `<source>_<article_hash>` where `source` defaults to 'wechat' for back-compat with direct CLI callers. (Vision sub-doc IDs at ingest_wechat.py:450 — `wechat_<hash>_images` — are explicitly OUT OF SCOPE; sub-docs have a separate lifecycle and are not part of source-aware dispatch.)"
    - "T3: Bodies shorter than MIN_INGEST_BODY_LEN (500 chars) are rejected before LightRAG ainsert with a clear error (defends against the 3 short-body RSS rows that bypassed RSS_SCRAPE_THRESHOLD=100 per t1o evidence)."
    - "T4: `pytest tests/unit/ -v` passes with zero new regressions vs siw baseline; existing 4 callsite tests updated (test_text_first_ingest, test_checkpoint_ingest_integration, test_ingest_article_processed_gate, test_rollback_on_timeout); 3 new doc_id/body tests added."
    - "T5: `tests/unit/test_ainsert_persistence_contract.py` is NOT modified by this task (gkw WIP locally modified — explicit out-of-scope per pre/post sha256 equality assertion captured in Task 3 verify)."
  artifacts:
    - path: ".scratch/uai-pytest-<ts>.log"
      provides: "Last 50 lines verbatim of pytest tests/unit/ -v output"
    - path: ".scratch/uai-grep-<ts>.log"
      provides: "Verification greps proving (1) only parameterized doc_id form remains in ingest_wechat.py (excluding _images sub-doc line), (2) batch_ingest_from_spider.py BOTH outer call sites pass source, (3) git diff --stat scope is correct"
    - path: ".scratch/uai-pre-sha-<ts>.txt / uai-post-sha-<ts>.txt"
      provides: "sha256 of tests/unit/test_ainsert_persistence_contract.py captured at Task 3 start and end — equality asserted in Task 3 verify automated block (gkw WIP guard)"
    - path: "ingest_wechat.py"
      provides: "Inner ingest_article signature accepts source kwarg; main-article doc_id is f\"{source or 'wechat'}_{article_hash}\" at the 2 sites in ingest_article (cache-hit + post-scrape branches); MIN_INGEST_BODY_LEN constant + early raise before ainsert. Vision sub-doc id at L450 (`wechat_<hash>_images`) intentionally untouched."
    - path: "batch_ingest_from_spider.py"
      provides: "Outer ingest_article wrapper threads `source` as first positional param; line ~286 dispatch call passes source kwarg to ingest_wechat.ingest_article; BOTH outer call sites updated — L822 (legacy KOL-only branch, hardcodes 'wechat') and L1730 (dual-source UNION ALL drain loop, threads source_d from row tuple)."
    - path: ".planning/STATE.md"
      provides: "Quick Tasks Completed row appended for 260510-uai"
    - path: ".planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md"
      provides: "SUMMARY citing log file paths verbatim (not paraphrased)"
  key_links:
    - from: "batch_ingest_from_spider.py:286"
      to: "ingest_wechat.ingest_article(url, source=..., rag=rag)"
      via: "asyncio.wait_for dispatch site — THE inner-dispatch bug location"
      pattern: "ingest_wechat\\.ingest_article\\(.*source="
    - from: "batch_ingest_from_spider.py:822"
      to: "ingest_article('wechat', url, dry_run, rag, effective_timeout=...)"
      via: "legacy KOL-only batch loop branch — no source_d local; hardcode 'wechat' literal (this branch only sees WeChat rows by code path)"
      pattern: "await ingest_article\\("
    - from: "batch_ingest_from_spider.py:1730"
      to: "ingest_article(source_d, url_d, dry_run, rag, effective_timeout=...)"
      via: "dual-source UNION ALL drain loop — source_d available from row tuple, thread it through"
      pattern: "await ingest_article\\(source_d"
    - from: "ingest_wechat.py:984"
      to: "doc_id = f\"{source or 'wechat'}_{article_hash}\""
      via: "main-article doc_id construction — second bug location (cache-hit + post-scrape branches both)"
      pattern: "f\"\\{source or 'wechat'\\}_"
    - from: "ingest_wechat.py:450"
      to: "sub_doc_id = f\"wechat_{article_hash}_images\" (UNCHANGED — Vision sub-doc, separate lifecycle)"
      via: "explicitly out of scope — sub-doc IDs are not part of source-aware dispatch; verify grep excludes `_images`"
      pattern: "(do not modify)"
    - from: "lib/article_filter.py:639-683"
      to: "persist_layer2_verdicts (REFERENCE ONLY — already source-aware, NOT touched by this plan)"
      via: "by_source dict + table_for routing"
      pattern: "(do not modify)"
    - from: ".planning/quick/260510-t1o-rss-pipeline-empirical-investigation-per/260510-t1o-RSS-INVESTIGATION.md"
      to: "Sections 1-4 — bug evidence + DB cross-tab proving 4/4 RSS ainsert failures"
      via: "preceding investigation citation"
      pattern: "(read-only reference)"
---

<objective>
Fix the RSS ingest dispatch bug surfaced by quick 260510-t1o: every URL flowing through `batch_ingest_from_spider.py:286` is dispatched to `ingest_wechat.ingest_article` regardless of source, and `ingest_wechat.py:984` hardcodes `doc_id = f"wechat_{article_hash}"`. Result (per t1o DB evidence): 4 RSS rows reached ainsert and ALL FAILED — 3 with body<200 chars (bypassed RSS_SCRAPE_THRESHOLD=100), 1 with real content but hit WeChat-only code paths.

Purpose: close the source-awareness gap that produces 0 RSS `ingestions(status='ok')` despite 546 RSS bodies persisted. Add a body-length fail-fast guard so future short-body rows are rejected with a clear error before they hit LightRAG.

Output: source param threaded through outer + inner ingest_article (BOTH outer call sites — L822 + L1730); main-article doc_id parameterized at the 2 sites in `ingest_article` (cache-hit + post-scrape), with the Vision sub-doc id at L450 explicitly untouched; MIN_INGEST_BODY_LEN=500 fail-fast guard; 4 existing test files updated for signature (test_text_first_ingest, test_checkpoint_ingest_integration, test_ingest_article_processed_gate, test_rollback_on_timeout) + 3 new tests covering the new behaviour.

Single atomic commit, single push.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260510-t1o-rss-pipeline-empirical-investigation-per/260510-t1o-RSS-INVESTIGATION.md
@batch_ingest_from_spider.py
@ingest_wechat.py
@tests/unit/test_text_first_ingest.py
@tests/unit/test_checkpoint_ingest_integration.py
@tests/unit/test_ingest_article_processed_gate.py
@tests/unit/test_rollback_on_timeout.py

<interfaces>
Current contracts (extracted from working tree before fix — executor uses these as the baseline diff target):

batch_ingest_from_spider.py:237-242 (CURRENT — outer wrapper, post-siw):
```python
async def ingest_article(
    url: str,
    dry_run: bool,
    rag,
    effective_timeout: int | None = None,
) -> tuple[bool, float, bool]:
    # Returns (success, wall_clock_seconds, doc_confirmed)
```

batch_ingest_from_spider.py:285-288 (CURRENT — inner dispatch site, THE bug):
```python
await asyncio.wait_for(
    ingest_wechat.ingest_article(url, rag=rag),
    timeout=timeout_s,
)
```

batch_ingest_from_spider.py — TWO outer call sites (BOTH need updating):
  (a) L822: legacy KOL-only batch loop branch. Surrounding code path is WeChat-only (no RSS rows reach this branch) — there is NO `source_d` local variable here. Hardcode the literal `'wechat'`:
      `await ingest_article('wechat', url, dry_run, rag, effective_timeout=effective_timeout)`
  (b) L1730: dual-source UNION ALL drain loop. Layer 2 binds `source` via the SQL at L1407 + ArticleWithBody dataclass at L1645-1652 — `source_d` (or whatever the local row-tuple name is) IS available. Thread it through:
      `await ingest_article(source_d, url_d, dry_run, rag, effective_timeout=effective_timeout)`

  Verification: `grep -nE "await ingest_article\(" batch_ingest_from_spider.py` MUST return ≥2 sites, ALL with `source=` literal-or-variable as first positional arg.

ingest_wechat.py:916 (CURRENT — inner signature):
```python
async def ingest_article(url, rag=None) -> "asyncio.Task | None":
```

ingest_wechat.py — THREE `f"wechat_..."` doc_id sites:
  (a) ~line 984: cache-hit branch, main-article doc_id `f"wechat_{article_hash}"` — UPDATE to parameterized form.
  (b) post-scrape branch (the second `f"wechat_{article_hash}"` further down): main-article doc_id — UPDATE to parameterized form.
  (c) ingest_wechat.py:450: `sub_doc_id = f"wechat_{article_hash}_images"` — Vision sub-doc, separate code path. **EXPLICITLY OUT OF SCOPE.** Sub-doc IDs are not part of source-aware dispatch (Vision sub-docs have their own lifecycle, never touched by RSS path). DO NOT MODIFY.

  Verification grep MUST exclude `_images` lines:
  `grep -nE 'f"wechat_[^"]*"' ingest_wechat.py | grep -v "_images"` should return 0 matches after the fix (only L450 _images line + parameterized `f"{source or 'wechat'}_{article_hash}"` form remain).

Outer signature target (NEW — after fix):
```python
async def ingest_article(
    source: str,
    url: str,
    dry_run: bool,
    rag,
    effective_timeout: int | None = None,
) -> tuple[bool, float, bool]:
```

Inner signature target (NEW — after fix):
```python
async def ingest_article(url, *, source: str = "wechat", rag=None) -> "asyncio.Task | None":
```

doc_id construction (NEW — both main-article sites; L450 sub-doc unchanged):
```python
doc_id = f"{source or 'wechat'}_{article_hash}"
```

Body fail-fast (NEW — top-level constant + guard inside inner ingest_article):
```python
MIN_INGEST_BODY_LEN = 500  # defends against short-body bypass of RSS_SCRAPE_THRESHOLD=100

# Inside ingest_article, after body has been determined (cache-hit OR scrape branches),
# BEFORE rag.ainsert(...) is called:
if len(full_content) < MIN_INGEST_BODY_LEN:
    raise ValueError(
        f"Body too short for ingest: len={len(full_content)} < MIN_INGEST_BODY_LEN={MIN_INGEST_BODY_LEN} (url={url[:80]})"
    )
```
</interfaces>

<scope_guards>
HARD STOPS — anti-pattern callouts. The executor MUST NOT:
- ❌ Rename `ingest_wechat.py` file or function (cosmetic, deferred to ar-1 milestone)
- ❌ Touch `_verify_doc_processed_or_raise` (h09 quick preserved)
- ❌ Touch `lib/article_filter.py` (already source-aware per t1o §1, working)
- ❌ Refactor scraper cascade in `lib/scraper.py` (works for RSS already per t1o §2)
- ❌ Modify the Vision sub-doc id at `ingest_wechat.py:450` (`sub_doc_id = f"wechat_<hash>_images"`) — separate lifecycle, not part of source-aware dispatch
- ❌ Modify `tests/unit/test_ainsert_persistence_contract.py` (gkw WIP, locally modified — `git status` shows M; sha256 pre/post equality asserted in Task 3 verify)
- ❌ Manually re-process the 4 failed RSS rows (mig 009 retry pool catches them on next cron)
- ❌ Touch cron / register_phase5_cron.sh / rl2 artifacts
- ❌ Use `git reset --soft` / `--mixed` / `--hard` / `git commit --amend` (per 2026-05-06 lesson — concurrent agent worktree corruption)

CONFLICT AWARENESS:
- siw landed earlier today on the same files: outer signature is now `(success, wall, doc_confirmed)`. PRESERVE — just add `source` param at front of outer wrapper.
- gkw WIP on `tests/unit/test_ainsert_persistence_contract.py` (locally modified, M shown in `git status`). Excluded from this scope.
- N=10 smoke running on Hermes tmux — does not touch local code.
- Pre-push: `git fetch origin && git rebase origin/main` defensive (origin/main HEAD currently behind local — recent commits include `2829fb2 docs(quick-260510-rl2)`, `5d4e294 fix(ingest-wechat-260510-rl2): F-4 trivial cleanups`).
</scope_guards>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Thread source through outer + inner ingest_article and parameterize main-article doc_id</name>
  <files>
    - batch_ingest_from_spider.py
    - ingest_wechat.py
  </files>
  <behavior>
    Production behaviour (verified by smoke + test in Task 3):
    - Outer call from main loop: `await ingest_article(source, url_d, dry_run, rag, effective_timeout=...)` returns `(success, wall, doc_confirmed)` — 3-tuple unchanged.
    - Outer dispatches `await ingest_wechat.ingest_article(url, source=source, rag=rag)` (kwarg form).
    - Inner with `source='rss'` produces main-article `doc_id == f"rss_{article_hash}"`.
    - Inner with `source='wechat'` (default for direct CLI) produces main-article `doc_id == f"wechat_{article_hash}"`.
    - Inner with no source kwarg (legacy direct call) defaults to 'wechat' — back-compat preserved.
    - Vision sub-doc id at ingest_wechat.py:450 (`wechat_<hash>_images`) is **unchanged** — separate lifecycle.
    - BOTH outer call sites updated (L822 hardcodes 'wechat' literal; L1730 threads source_d from row tuple).
  </behavior>
  <action>
    Implementation steps (in this order — interface-first):

    A. ingest_wechat.py — INNER signature + main-article doc_id (do this FIRST so the outer can call it):
       1. Change signature at ~line 916 from `async def ingest_article(url, rag=None)` to `async def ingest_article(url, *, source: str = "wechat", rag=None)`. Keyword-only enforced via `*,` so all callers must spell `source=...` explicitly.
       2. Update docstring (one-line addition): "Phase quick-260510-uai: `source` parameter (default 'wechat') threads source label into MAIN-ARTICLE doc_id; non-WeChat sources (e.g. 'rss') get prefix `<source>_<article_hash>` per quick 260510-t1o investigation. Vision sub-doc ids at L450 (`wechat_<hash>_images`) are unchanged — separate lifecycle, not part of source-aware dispatch."
       3. Find the TWO main-article hardcoded `doc_id = f"wechat_{article_hash}"` sites with this grep — explicitly excluding the L450 Vision sub-doc:
          `grep -nE 'f"wechat_[^"]*"' ingest_wechat.py | grep -v "_images"`
          Replace each match with `doc_id = f"{source or 'wechat'}_{article_hash}"`. The L450 `f"wechat_{article_hash}_images"` line must remain untouched (verify by re-grepping the same expression after edit — should still return 0 main-article matches AND L450 `_images` line is preserved).

    B. batch_ingest_from_spider.py — OUTER signature + inner-dispatch + BOTH outer call sites:
       1. Change signature at line 237 from `async def ingest_article(url, dry_run, rag, effective_timeout=None)` to `async def ingest_article(source, url, dry_run, rag, effective_timeout=None)`. `source` is FIRST positional param (caller-side breaks loud, not silent).
       2. Update line ~286 inner dispatch from `ingest_wechat.ingest_article(url, rag=rag)` → `ingest_wechat.ingest_article(url, source=source, rag=rag)`.
       3. Update outer docstring (one-line addition): "Phase quick-260510-uai: accepts `source` (positional 0) — threaded into ingest_wechat.ingest_article kwarg so RSS rows get doc_id `rss_<hash>` instead of `wechat_<hash>`."
       4. Update **BOTH** outer `ingest_article(...)` call sites in the file. There are exactly 2:

          **L822 (legacy KOL-only batch loop branch):** No `source_d` local variable — this branch only processes WeChat rows by code-path construction. Hardcode the literal `'wechat'`:
          ```python
          # BEFORE (line 822):
          success, wall, doc_confirmed = await ingest_article(url, dry_run, rag, effective_timeout=...)
          # AFTER:
          success, wall, doc_confirmed = await ingest_article('wechat', url, dry_run, rag, effective_timeout=...)
          ```

          **L1730 (dual-source UNION ALL drain loop):** `source_d` (or whatever the local name is for the source field of the drained row tuple — Layer 2 binds it via SQL at L1407 + ArticleWithBody dataclass at L1645-1652) IS available. Thread it through:
          ```python
          # BEFORE (line 1730):
          success, wall, doc_confirmed = await ingest_article(url_d, dry_run, rag, effective_timeout=effective_timeout)
          # AFTER:
          success, wall, doc_confirmed = await ingest_article(source_d, url_d, dry_run, rag, effective_timeout=effective_timeout)
          ```
          (If the surrounding code uses a different local name for source — e.g. `row[1]` or `article.source` — use whatever name is already in scope. Do NOT introduce a new variable.)

       5. Verify enumeration: `grep -nE "await ingest_article\(" batch_ingest_from_spider.py` MUST return ≥2 lines. Each line MUST have a source value (literal `'wechat'` for L822, variable name for L1730) as the first positional arg. Capture grep output to log.

    Anti-pattern callouts (do NOT do):
    - Don't rename functions or modules.
    - Don't change the inner return type or 3-tuple outer return shape.
    - Don't touch `_verify_doc_processed_or_raise`.
    - Don't touch `ingest_wechat.py:450` Vision sub-doc id.
    - Don't add backward-compat shim for the OUTER signature (caller is in-repo, breaking is intentional and surfaces missed call sites).
    - Don't `git commit --amend` or use `git reset --soft` mid-task.
  </action>
  <verify>
    <automated>
      bash -lc 'set -e
      ts=$(date +%Y%m%d-%H%M%S)
      mkdir -p .scratch
      LOG=.scratch/uai-grep-${ts}.log
      {
        echo "=== Verification 1: hardcoded MAIN-ARTICLE doc_id eliminated (expect 0 hits, excluding L450 _images sub-doc) ==="
        # MUST exclude _images sub-doc line at L450 — that is intentionally out of scope
        N_MAIN=$(grep -nE "f\"wechat_[^\"]*\"" ingest_wechat.py | grep -v "_images" | wc -l | tr -d " ")
        grep -nE "f\"wechat_[^\"]*\"" ingest_wechat.py | grep -v "_images" || echo "(no main-article matches — OK)"
        echo "main-article hardcoded count: $N_MAIN (must be 0)"
        if [ "$N_MAIN" -ne 0 ]; then
          echo "FAIL: hardcoded main-article doc_id still present"
          exit 1
        fi
        echo
        echo "=== Verification 2: L450 Vision sub-doc id PRESERVED (expect 1 match, untouched) ==="
        grep -nE "f\"wechat_[^\"]*_images\"" ingest_wechat.py || (echo "FAIL: L450 _images sub-doc id missing — accidentally removed?" && exit 1)
        echo
        echo "=== Verification 3: parameterized form present (expect exactly 2 — cache-hit + post-scrape) ==="
        N_PARAM=$(grep -cE "f\"\\{source or " ingest_wechat.py || true)
        grep -nE "f\"\\{source or " ingest_wechat.py
        echo "parameterized count: $N_PARAM (must be >=2)"
        if [ "$N_PARAM" -lt 2 ]; then
          echo "FAIL: expected >=2 parameterized doc_id sites; got $N_PARAM"
          exit 1
        fi
        echo
        echo "=== Verification 4: inner dispatch passes source kwarg ==="
        grep -nE "ingest_wechat\.ingest_article" batch_ingest_from_spider.py
        grep -nE "ingest_wechat\.ingest_article\(.+source=" batch_ingest_from_spider.py || (echo "FAIL: inner dispatch missing source kwarg" && exit 1)
        echo
        echo "=== Verification 5: BOTH outer call sites enumerated (expect >=2 sites, each with source as first positional) ==="
        N_OUTER=$(grep -cE "await ingest_article\(" batch_ingest_from_spider.py || true)
        grep -nE "await ingest_article\(" batch_ingest_from_spider.py
        echo "outer call site count: $N_OUTER (must be >=2)"
        if [ "$N_OUTER" -lt 2 ]; then
          echo "FAIL: expected >=2 outer call sites (L822 + L1730); got $N_OUTER"
          exit 1
        fi
        echo
        echo "=== Verification 6: L822 hardcodes wechat literal ==="
        grep -nE "await ingest_article\(.wechat." batch_ingest_from_spider.py || (echo "FAIL: no outer call site with wechat literal — L822 not updated?" && exit 1)
        echo
        echo "=== Verification 7: L1730 threads source variable (any non-literal first arg) ==="
        # Match `await ingest_article(<identifier>,` where identifier is not a quoted string
        grep -nE "await ingest_article\([a-zA-Z_][a-zA-Z0-9_]*," batch_ingest_from_spider.py || (echo "FAIL: no outer call site with source variable as first positional — L1730 not updated?" && exit 1)
        echo
        echo "=== Verification 8: outer ingest_article signature has source as first param ==="
        grep -nE "^async def ingest_article\(source" batch_ingest_from_spider.py || (echo "FAIL: outer signature missing source param" && exit 1)
        echo
        echo "=== Verification 9: inner ingest_article signature has source kwarg-only ==="
        grep -nE "^async def ingest_article\(url, \*, source" ingest_wechat.py || (echo "FAIL: inner signature missing keyword-only source param" && exit 1)
      } | tee "$LOG"'
    </automated>
  </verify>
  <done>
    - `grep -nE 'f"wechat_[^"]*"' ingest_wechat.py | grep -v "_images"` returns exactly 0 matches (main-article hardcoded form gone; L450 Vision sub-doc `wechat_<hash>_images` is intentionally OUT OF SCOPE and remains).
    - `grep -nE 'f"wechat_[^"]*_images"' ingest_wechat.py` returns 1 match (L450 sub-doc preserved).
    - `grep -nE 'f"\{source or ' ingest_wechat.py` returns exactly 2 matches — cache-hit + post-scrape branches; L450 Vision sub-doc out of scope, has its own lifecycle.
    - `grep -nE 'ingest_wechat\.ingest_article\(.+source=' batch_ingest_from_spider.py` returns 1 match (the L286 dispatch).
    - `grep -nE 'await ingest_article\(' batch_ingest_from_spider.py` returns ≥2 matches (L822 + L1730).
    - `grep -nE "await ingest_article\(.wechat." batch_ingest_from_spider.py` returns ≥1 match (L822 hardcoded literal).
    - `grep -nE "await ingest_article\([a-zA-Z_][a-zA-Z0-9_]*," batch_ingest_from_spider.py` returns ≥1 match (L1730 source variable).
    - `grep -nE '^async def ingest_article\(source' batch_ingest_from_spider.py` returns 1 match.
    - `grep -nE '^async def ingest_article\(url, \*, source' ingest_wechat.py` returns 1 match.
    - All grep output captured to `.scratch/uai-grep-<ts>.log`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add MIN_INGEST_BODY_LEN constant and body-length fail-fast guard in inner ingest_article</name>
  <files>
    - ingest_wechat.py
  </files>
  <behavior>
    - Module-level constant `MIN_INGEST_BODY_LEN = 500` defined near other ingest constants (e.g. near `RSS_SCRAPE_THRESHOLD` if present in this file, otherwise top-level after imports).
    - In `ingest_article`, AFTER `full_content` is determined (both cache-hit branch and post-scrape branch), BEFORE `rag.ainsert(full_content, ids=[doc_id])`, raise `ValueError` if `len(full_content) < MIN_INGEST_BODY_LEN`.
    - Error message format: `f"Body too short for ingest: len={N} < MIN_INGEST_BODY_LEN=500 (url={url[:80]})"` — clear, one line, includes both lengths and a truncated URL.
    - The raise propagates up to outer `ingest_article` at `batch_ingest_from_spider.py:319` `except Exception as exc:` branch, which logs `Ingest failed (ValueError): ...` and returns `(False, wall, False)` — exactly the path that currently handles other ainsert failures. No special-case handling required at the outer layer.
  </behavior>
  <action>
    1. Add constant near top of `ingest_wechat.py` (after imports, before first function — group with other ingest-policy constants if any exist; otherwise after the `BASE_IMAGE_DIR`-style constants):
       ```python
       # Phase quick-260510-uai: defends against short-body bypass of RSS_SCRAPE_THRESHOLD=100.
       # t1o investigation showed 3 RSS rows with body<200 chars reached ainsert and failed.
       # 500 is a soft floor — well above the 200-char floor used by Layer 2 prompt tolerance,
       # well below the typical real-article length (61k chars in the t1o sample row).
       MIN_INGEST_BODY_LEN = 500
       ```

    2. In inner `ingest_article` cache-hit branch (~ between current L953 `full_content = f.read()` and the existing `await rag.ainsert(full_content, ids=[doc_id])` at L986): insert guard:
       ```python
       if len(full_content) < MIN_INGEST_BODY_LEN:
           raise ValueError(
               f"Body too short for ingest: len={len(full_content)} < "
               f"MIN_INGEST_BODY_LEN={MIN_INGEST_BODY_LEN} (url={url[:80]})"
           )
       ```

    3. In inner `ingest_article` post-scrape branch: find the second `await rag.ainsert(...)` site (the one not in the cache-hit branch). Insert the same guard immediately before it.

    4. Run `grep -nE "MIN_INGEST_BODY_LEN" ingest_wechat.py` to confirm 1 constant definition + 2 guard usages = 3 total matches.

    Anti-pattern callouts:
    - Don't catch + log the ValueError inside `ingest_article`. Let it propagate. Outer `except Exception` already handles it.
    - Don't make MIN_INGEST_BODY_LEN env-overridable. Constant per locked design — if future tuning needed, future quick.
    - Don't add a unit test for the guard inside this task — Task 3 owns all test changes.
  </action>
  <verify>
    <automated>
      bash -lc 'set -e
      ts=$(date +%Y%m%d-%H%M%S)
      LOG=.scratch/uai-grep-${ts}.log
      {
        echo "=== Verification: MIN_INGEST_BODY_LEN constant + 2 guard usages ==="
        grep -nE "MIN_INGEST_BODY_LEN" ingest_wechat.py
        n=$(grep -cE "MIN_INGEST_BODY_LEN" ingest_wechat.py)
        echo "match count: $n"
        if [ "$n" -lt 3 ]; then
          echo "FAIL: expected >=3 matches (1 constant def + 2 guard usages); got $n"
          exit 1
        fi
        echo
        echo "=== Verification: guard raises ValueError (literal expected) ==="
        grep -nE "Body too short for ingest" ingest_wechat.py
      } | tee -a "$LOG"'
    </automated>
  </verify>
  <done>
    - `MIN_INGEST_BODY_LEN = 500` defined at module level (single match for the assignment).
    - At least 2 guard usages (`len(full_content) < MIN_INGEST_BODY_LEN`) inside `ingest_article` — one per `rag.ainsert` call site.
    - `Body too short for ingest` literal string present in raise — same wording every site.
    - All grep output appended to `.scratch/uai-grep-<ts>.log`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Update existing tests for source param (4 files), add 3 new tests, run pytest, commit, push</name>
  <files>
    - tests/unit/test_text_first_ingest.py
    - tests/unit/test_checkpoint_ingest_integration.py
    - tests/unit/test_ingest_article_processed_gate.py
    - tests/unit/test_rollback_on_timeout.py
    - .planning/STATE.md
    - .planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md
  </files>
  <behavior>
    - Existing tests calling `ingest_wechat.ingest_article(url, rag=...)` continue to pass (default source='wechat' preserves legacy behaviour).
    - Existing tests calling outer `batch_ingest_from_spider.ingest_article(...)` UPDATED to pass `source` as new first positional arg: `ingest_article('wechat', url, dry_run, rag, ...)`.
    - **`tests/unit/test_rollback_on_timeout.py`** uses module alias `import batch_ingest_from_spider as bi` — so calls take the form `bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)` at L63, L91, L124, L162, L170 (5 callsites). All 5 MUST be updated to inject `source='wechat'` (test is wechat-flow-focused; preserve existing behaviour). Without this change, all 5 raise TypeError after the outer signature change in Task 1.
    - 3 NEW tests added (each goes into the most natural test file — keep clustered):
       (a) `test_inner_ingest_article_rss_source_yields_rss_doc_id` — calls inner with `source='rss'`, asserts the captured `doc_id` argument to `rag.ainsert` starts with `rss_`. Lives in `test_text_first_ingest.py` next to the existing doc_id capture test.
       (b) `test_inner_ingest_article_default_source_yields_wechat_doc_id` — calls inner without source kwarg, asserts captured `doc_id` starts with `wechat_`. Same file.
       (c) `test_inner_ingest_article_rejects_short_body` — monkeypatches scrape to return a body <500 chars (or sets cache-hit final_content with <500 chars), asserts `ValueError` with `"Body too short for ingest"` is raised before `rag.ainsert` is called (assert via mock `rag.ainsert.assert_not_called()`). Same file.
    - `pytest tests/unit/ -v` baseline (per siw earlier today — see commit `5d4e294`): existing failure set MUST be a strict subset of post-fix failure set + the 3 new tests added. Zero new regressions in previously-passing tests.
    - `tests/unit/test_ainsert_persistence_contract.py` byte-identical to its pre-task state (gkw WIP guard) — verified via sha256 pre/post equality in <verify><automated>.
  </behavior>
  <action>
    1. Enumerate ALL callsites in tests/ — broadened grep catches module aliases like `bi.` and `bifs.`:
       ```bash
       grep -rnE "\.ingest_article\(" tests/unit/
       ```
       Expected output covers 4 files:
       - `tests/unit/test_text_first_ingest.py` — inner calls (`ingest_wechat.ingest_article(url, rag=...)`); these are inner, default source='wechat' preserves behaviour, NO change unless test asserts doc_id (existing doc_id test already expects `wechat_` prefix → also unchanged).
       - `tests/unit/test_checkpoint_ingest_integration.py` — outer calls (`batch_ingest_from_spider.ingest_article(...)`); update positional args to inject `source='wechat'` as new first positional arg.
       - `tests/unit/test_ingest_article_processed_gate.py` — outer calls; same treatment.
       - `tests/unit/test_rollback_on_timeout.py` — uses module alias `import batch_ingest_from_spider as bi`; calls at **L63, L91, L124, L162, L170** — 5 callsites in form `bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)`. Update each to `bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)` (kwargs are already in use; just inject `source='wechat'` as additional kwarg). Test is wechat-flow-focused — preserve existing behaviour.

       Re-run `pytest` after each file to localize regressions.

    2. Add 3 new tests in `tests/unit/test_text_first_ingest.py` (cluster with existing doc_id test for locality). Pattern after the existing `_fake_rag` + monkeypatch fixture style already used in that file (see lines 82-127 for the existing fixture pattern):
       ```python
       async def test_inner_ingest_article_rss_source_yields_rss_doc_id(monkeypatch, _fake_rag, _common_fixtures):
           """quick-260510-uai T2: source='rss' → doc_id `rss_<article_hash>`."""
           import ingest_wechat
           url = "https://example.com/some-rss-article"
           # ... (use existing _fake_rag.ainsert MagicMock to capture call kwargs)
           await ingest_wechat.ingest_article(url, source="rss", rag=_fake_rag)
           call_kwargs = _fake_rag.ainsert.call_args.kwargs
           assert call_kwargs["ids"][0].startswith("rss_"), \
               f"expected rss_ prefix, got {call_kwargs['ids'][0]}"

       async def test_inner_ingest_article_default_source_yields_wechat_doc_id(...):
           """quick-260510-uai T2: default source='wechat' → doc_id `wechat_<article_hash>`."""
           # No source kwarg — relies on default
           await ingest_wechat.ingest_article(url, rag=_fake_rag)
           assert _fake_rag.ainsert.call_args.kwargs["ids"][0].startswith("wechat_")

       async def test_inner_ingest_article_rejects_short_body(monkeypatch, _fake_rag, tmp_path):
           """quick-260510-uai T3: body<MIN_INGEST_BODY_LEN raises before ainsert."""
           import ingest_wechat
           # Force cache-hit branch with short body (cleanest path — no scrape mocks)
           article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
           article_dir = tmp_path / article_hash
           article_dir.mkdir()
           (article_dir / "final_content.md").write_text("too short")  # 9 chars
           monkeypatch.setattr(ingest_wechat, "BASE_IMAGE_DIR", str(tmp_path))
           with pytest.raises(ValueError, match="Body too short for ingest"):
               await ingest_wechat.ingest_article(url, rag=_fake_rag)
           _fake_rag.ainsert.assert_not_called()
       ```
       (Adapt fixture names to match what's actually in the file — executor MUST read the file and reuse existing fixture style. The skeleton above is the contract, not literal code.)

    3. Run pytest and capture last 50 lines verbatim:
       ```bash
       ts=$(date +%Y%m%d-%H%M%S)
       LOG=.scratch/uai-pytest-${ts}.log
       .venv/Scripts/python -m pytest tests/unit/ -v 2>&1 | tee "$LOG"
       echo "=== last 50 lines ===" >> "$LOG"
       tail -n 50 "$LOG" >> "$LOG"  # double-tail for SUMMARY citation
       ```

    4. Verify scope guard — `tests/unit/test_ainsert_persistence_contract.py` UNTOUCHED. The pre/post sha256 equality is asserted in the <verify><automated> block (NOT prose only) to catch any `git add -u` slip that could sweep gkw WIP into uai's commit.

    5. Verify scope via `git diff --stat HEAD`:
       ```bash
       git diff --stat HEAD | tee -a "$LOG"
       # Expect ONLY:
       #   batch_ingest_from_spider.py
       #   ingest_wechat.py
       #   tests/unit/test_text_first_ingest.py
       #   tests/unit/test_checkpoint_ingest_integration.py  (if outer call sites present in this file)
       #   tests/unit/test_ingest_article_processed_gate.py  (if outer call sites present in this file)
       #   tests/unit/test_rollback_on_timeout.py
       #   .planning/STATE.md
       #   .planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md
       # FAIL if test_ainsert_persistence_contract.py appears.
       ```

    6. Append STATE.md "Quick Tasks Completed" row for 260510-uai. Append after the existing 260510-rl2 / 260510-t1o entries. Format match prior rows:
       ```
       | 2026-05-10 | 260510-uai | source-aware ingest dispatch — RSS uses rss_ doc_id prefix + body-length fail-fast | <commit-sha> | ✅ |
       ```

    7. Write SUMMARY.md citing the log files VERBATIM (per anti-fabrication constraint):
       ```
       Pytest result: see `.scratch/uai-pytest-<ts>.log` last 50 lines (raw output).
       Grep verification: see `.scratch/uai-grep-<ts>.log`.
       sha256 pre/post: see `.scratch/uai-pre-sha-<ts>.txt` + `.scratch/uai-post-sha-<ts>.txt` (must be byte-equal).
       ```
       SUMMARY MUST NOT paraphrase test counts. SUMMARY MUST quote the actual `==== N passed, M failed ====` line from the log.

    8. ATOMIC COMMIT with the exact required message — note the **explicit file list** (no `git add -u`, no `git add .`):
       ```bash
       git add batch_ingest_from_spider.py ingest_wechat.py \
               tests/unit/test_text_first_ingest.py \
               tests/unit/test_checkpoint_ingest_integration.py \
               tests/unit/test_ingest_article_processed_gate.py \
               tests/unit/test_rollback_on_timeout.py \
               .planning/STATE.md \
               .planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-PLAN.md \
               .planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md \
               .scratch/uai-pytest-<ts>.log \
               .scratch/uai-grep-<ts>.log
       git commit -m "fix(ingest-260510-uai): source-aware dispatch — RSS articles use rss_ doc_id prefix + body-length fail-fast eliminates short-body ainsert failures"
       ```
       (NOTE: `.scratch/` may be gitignored — if so, drop those two log paths from the `git add`. SUMMARY.md citing them by path is the canonical record.)

    9. Pre-push defensive rebase + push:
       ```bash
       git fetch origin
       git rebase origin/main   # no-op if local already current
       git push origin main
       ```
       NEVER `--force-push` — if rebase fails, STOP and surface to user.
  </action>
  <verify>
    <automated>
      bash -lc 'set -e
      ts=$(date +%Y%m%d-%H%M%S)
      LOG=.scratch/uai-pytest-${ts}.log
      mkdir -p .scratch

      # === sha256 PRE-task capture (gkw WIP guard) ===
      PRE_SHA_FILE=.scratch/uai-pre-sha-${ts}.txt
      sha256sum tests/unit/test_ainsert_persistence_contract.py > "$PRE_SHA_FILE"
      echo "=== sha256 pre-task: $(cat $PRE_SHA_FILE) ===" | tee -a "$LOG"

      # === broadened test grep (catches module aliases like bi., bifs.) ===
      echo "=== Verification: enumerate ALL test callsites of ingest_article (broadened to catch module aliases) ===" | tee -a "$LOG"
      grep -rnE "\.ingest_article\(" tests/unit/ | tee -a "$LOG"
      echo

      echo "=== Verification: test_rollback_on_timeout.py callsites updated (expect 5 callsites, all with source=) ===" | tee -a "$LOG"
      N_RB=$(grep -cE "\.ingest_article\(.*source=" tests/unit/test_rollback_on_timeout.py || true)
      grep -nE "\.ingest_article\(" tests/unit/test_rollback_on_timeout.py | tee -a "$LOG"
      echo "test_rollback_on_timeout.py callsites with source=: $N_RB (expect >=5)" | tee -a "$LOG"
      if [ "$N_RB" -lt 5 ]; then
        echo "FAIL: test_rollback_on_timeout.py has $N_RB callsites with source= kwarg; expected >=5 (L63, L91, L124, L162, L170)" | tee -a "$LOG"
        exit 1
      fi

      # === run full pytest suite ===
      echo "=== pytest tests/unit/ -v ===" | tee -a "$LOG"
      .venv/Scripts/python -m pytest tests/unit/ -v 2>&1 | tee -a "$LOG"

      # === sha256 POST-task assertion (gkw WIP guard) ===
      POST_SHA_FILE=.scratch/uai-post-sha-${ts}.txt
      sha256sum tests/unit/test_ainsert_persistence_contract.py > "$POST_SHA_FILE"
      echo "=== sha256 post-task: $(cat $POST_SHA_FILE) ===" | tee -a "$LOG"
      PRE_HASH=$(awk "{print \$1}" "$PRE_SHA_FILE")
      POST_HASH=$(awk "{print \$1}" "$POST_SHA_FILE")
      if [ "$PRE_HASH" != "$POST_HASH" ]; then
        echo "FAIL: tests/unit/test_ainsert_persistence_contract.py modified by this task (pre=$PRE_HASH post=$POST_HASH) — gkw WIP guard violated" | tee -a "$LOG"
        exit 1
      fi
      echo "(sha256 byte-equal — gkw WIP guard preserved)" | tee -a "$LOG"

      # === scope verification ===
      echo "=== git diff --stat HEAD ===" | tee -a "$LOG"
      git diff --stat HEAD | tee -a "$LOG"
      echo "=== assert test_ainsert_persistence_contract.py NOT in HEAD commit (post-commit) ===" | tee -a "$LOG"
      git show --stat HEAD | grep -E "test_ainsert_persistence_contract\.py" && \
        (echo "FAIL: test_ainsert_persistence_contract.py modified by this commit" && exit 1) || \
        echo "(no match — OK, test_ainsert_persistence_contract.py untouched by commit)"
      echo "=== last 50 lines of pytest output (for SUMMARY citation) ===" | tee -a "$LOG"
      tail -n 50 "$LOG"'
    </automated>
  </verify>
  <done>
    - `pytest tests/unit/ -v` runs to completion with output captured to `.scratch/uai-pytest-<ts>.log`.
    - Pytest summary line shows zero NEW failures vs siw baseline (28/667 known failures from rl2 SUMMARY — post-fix should be 28/670 with 3 new tests passing, OR same 28/667 + 3 new added = 28/670 baseline). Executor cites EXACT counts from the log, not paraphrased.
    - 3 new test names appear in pytest output: `test_inner_ingest_article_rss_source_yields_rss_doc_id`, `test_inner_ingest_article_default_source_yields_wechat_doc_id`, `test_inner_ingest_article_rejects_short_body`.
    - `tests/unit/test_rollback_on_timeout.py` has ≥5 callsites with `source=` kwarg (verified by grep in <verify><automated>).
    - sha256 of `tests/unit/test_ainsert_persistence_contract.py` byte-equal pre vs post (verified in <verify><automated>; pre/post hash files at `.scratch/uai-pre-sha-<ts>.txt` and `.scratch/uai-post-sha-<ts>.txt`).
    - `git show --stat HEAD` shows ONLY the files in `<files>` list. `tests/unit/test_ainsert_persistence_contract.py` does NOT appear.
    - Commit message exact match: `fix(ingest-260510-uai): source-aware dispatch — RSS articles use rss_ doc_id prefix + body-length fail-fast eliminates short-body ainsert failures`.
    - `git push` succeeds against origin/main (no force-push, no skip-hooks).
    - SUMMARY.md exists at `.planning/quick/260510-uai-.../260510-uai-SUMMARY.md` citing log paths verbatim.
    - STATE.md "Quick Tasks Completed" row appended for 260510-uai with commit SHA.
  </done>
</task>

</tasks>

<verification>
End-to-end phase verification (executor runs after Task 3 commit + push):

1. **Source threading verified at all sites:**
   ```bash
   grep -nE "ingest_wechat\.ingest_article\(.+source=" batch_ingest_from_spider.py
   # Expect: 1 match (the L286 inner dispatch)
   grep -nE "await ingest_article\(" batch_ingest_from_spider.py
   # Expect: >=2 matches (L822 + L1730 outer call sites)
   grep -nE "^async def ingest_article\(source" batch_ingest_from_spider.py
   # Expect: 1 match
   grep -nE "^async def ingest_article\(url, \*, source" ingest_wechat.py
   # Expect: 1 match
   ```

2. **doc_id parameterized at main-article sites; L450 sub-doc preserved:**
   ```bash
   grep -nE 'f"wechat_[^"]*"' ingest_wechat.py | grep -v "_images"
   # Expect: 0 matches (main-article hardcoded form gone)
   grep -nE 'f"wechat_[^"]*_images"' ingest_wechat.py
   # Expect: 1 match (L450 Vision sub-doc id intentionally preserved)
   grep -nE 'f"\{source or ' ingest_wechat.py
   # Expect: exactly 2 matches (cache-hit + post-scrape branches)
   ```

3. **Body fail-fast guard present:**
   ```bash
   grep -cE "MIN_INGEST_BODY_LEN" ingest_wechat.py
   # Expect: >=3 (1 constant + 2 guards)
   ```

4. **Test scope correct (gkw WIP guard via sha256):**
   ```bash
   git show --stat HEAD | grep "test_ainsert_persistence_contract"
   # Expect: empty output (file NOT modified by uai commit)
   diff .scratch/uai-pre-sha-<ts>.txt .scratch/uai-post-sha-<ts>.txt
   # Expect: empty output (sha256 byte-equal)
   ```

5. **All 4 test files updated, including module-alias callsites:**
   ```bash
   grep -rnE "\.ingest_article\(" tests/unit/
   # Verify each callsite has source= kwarg or 'wechat' literal as first positional
   grep -cE "\.ingest_article\(.*source=" tests/unit/test_rollback_on_timeout.py
   # Expect: >=5 (L63, L91, L124, L162, L170 all updated)
   ```

6. **Pytest baseline preserved (zero new regressions):**
   - Compare last-50-line pytest summary in `.scratch/uai-pytest-<ts>.log` vs siw baseline pre-task. New failure count must be ≤ baseline failure count. New test count = baseline + 3.

7. **Push succeeded:**
   ```bash
   git log origin/main -1 --format='%H %s'
   # Expect: <new-sha> fix(ingest-260510-uai): source-aware dispatch — ...
   ```
</verification>

<success_criteria>
Quick complete when ALL of the following are true:

- [ ] All 5 truths (T1-T5) verified by automated greps + pytest run + sha256 equality.
- [ ] All artifacts exist on disk and are committed (or in the case of `.scratch/*.log` and `.scratch/uai-{pre,post}-sha-*.txt`, paths are referenced verbatim in SUMMARY.md).
- [ ] BOTH outer call sites updated (L822 hardcoded `'wechat'`, L1730 threads source variable). Verified by grep enumerating ≥2 sites.
- [ ] L450 Vision sub-doc id at `ingest_wechat.py:450` (`wechat_<hash>_images`) untouched — verified by grep returning 1 match for `_images` form.
- [ ] All 5 callsites in `tests/unit/test_rollback_on_timeout.py` (L63, L91, L124, L162, L170) updated to inject `source='wechat'` — verified by grep returning ≥5.
- [ ] sha256 of `tests/unit/test_ainsert_persistence_contract.py` byte-equal pre vs post — verified in `<verify><automated>` of Task 3.
- [ ] Single atomic commit on local main with the exact required message.
- [ ] Pushed to origin/main after `git fetch origin && git rebase origin/main` succeeded.
- [ ] STATE.md "Quick Tasks Completed" row appended for 260510-uai with commit SHA.
- [ ] SUMMARY.md cites log file paths verbatim — does NOT paraphrase test counts.
- [ ] Pytest `tests/unit/ -v` shows zero NEW failures vs siw rl2 baseline; 3 new tests added all pass.
- [ ] No use of `git reset --soft/mixed/hard`, `git commit --amend`, `--no-verify`, `--force-push`.
</success_criteria>

<output>
After completion, write `.planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md` containing:

1. **One-paragraph outcome:** "Closed source-aware ingest dispatch gap surfaced by t1o. Source threaded through outer + inner ingest_article (BOTH outer call sites — L822 hardcoded 'wechat', L1730 threaded source variable); main-article doc_id parameterized at the 2 sites in `ingest_article` (cache-hit + post-scrape); L450 Vision sub-doc id intentionally preserved; MIN_INGEST_BODY_LEN=500 guard added. <N> existing tests updated for signature across 4 files (including 5 callsites in test_rollback_on_timeout.py via module alias); 3 new tests added."

2. **Truths verified:** T1-T5 with checkbox + grep evidence (cite line ranges from .scratch logs).

3. **Artifacts list:** with file paths.

4. **Test result citation (verbatim, no paraphrase):**
   ```
   Pytest output: .scratch/uai-pytest-<ts>.log (last 50 lines)
   Pytest summary line: ==== N passed, M failed in T.TTs ==== (paste literal line from log)
   New tests added (3): test_inner_ingest_article_rss_source_yields_rss_doc_id, test_inner_ingest_article_default_source_yields_wechat_doc_id, test_inner_ingest_article_rejects_short_body
   Baseline comparison: siw rl2 = 28/667 → uai post = N/(667+3)=N/670
   ```

5. **Grep verification citation:** `.scratch/uai-grep-<ts>.log` — list each grep result line.

6. **gkw WIP guard:** sha256 pre/post of `tests/unit/test_ainsert_persistence_contract.py` from `.scratch/uai-pre-sha-<ts>.txt` and `.scratch/uai-post-sha-<ts>.txt` — must be byte-equal.

7. **Scope-guard verification:** `git show --stat HEAD` output excerpt — confirm test_ainsert_persistence_contract.py absent.

8. **Commit + push:** SHA, full message line, push timestamp.

9. **Out-of-scope reaffirmed:** lib/article_filter.py untouched, _verify_doc_processed_or_raise untouched, scraper cascade untouched, ar-1 rename deferred, 4 failed RSS rows left to mig 009 retry pool, gkw test file untouched, **L450 Vision sub-doc id (`wechat_<hash>_images`) intentionally preserved — separate lifecycle, not part of source-aware dispatch**.
</output>
