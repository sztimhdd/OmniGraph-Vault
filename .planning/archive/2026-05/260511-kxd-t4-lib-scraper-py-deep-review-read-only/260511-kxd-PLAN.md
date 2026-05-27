---
phase: quick-260511-kxd
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md
autonomous: true
requirements:
  - KXD-T4-A1   # Dead code / migration debris
  - KXD-T4-A2   # Cascade configuration + ordering (STAR — F-1 unlock)
  - KXD-T4-A3   # Producer↔Consumer data shape
  - KXD-T4-A4   # Cross-module coupling
  - KXD-T4-A5   # Error-handling silent-fail audit
  - KXD-T4-A6   # Async engineering
  - KXD-T4-A7   # Test coverage
  - KXD-T4-VERDICT  # F-1 unlock readiness verdict (ready-now / needs-T5 / not-needed)
must_haves:
  truths:
    - "REVIEW.md exists at the configured path and contains all 10 schema sections in the exact order/heading shape specified."
    - "Every finding (HIGH/MEDIUM/LOW) cites raw evidence (file:line, commit SHA, or .scratch log path) — no `looks fine` / `seems ok` stubs."
    - "All 7 audit angles A1..A7 each appear in REVIEW.md with either substantive findings or an explicit `no findings` declaration."
    - "All 5 anchor CLAUDE.md lessons are cross-referenced in §2 with status (still-applicable / fixed / partial / N/A) + evidence."
    - "Section §3 (cascade divergence) lists the *actual* cascade order found in lib/scraper.py AND in ingest_wechat.py, with file:line citations for both."
    - "F-1 unlock verdict (ready-now / needs-T5 / blocked-on-X / not-needed) is explicit in TL;DR and §9, with a one-line justification tied to severity counts."
    - "git status --short shows ONLY .planning/quick/260511-kxd-*/PLAN.md and .planning/quick/260511-kxd-*/REVIEW.md as untracked/modified — no business-file edits."
  artifacts:
    - path: ".planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md"
      provides: "T4 deep-review output covering 7 audit angles, 5 anchor lessons, F-1 unlock verdict"
      min_lines: 200
      contains: "## TL;DR"
  key_links:
    - from: "REVIEW.md §3"
      to: "lib/scraper.py:_scrape_wechat() and ingest_wechat.py cascade dispatcher"
      via: "explicit cascade-order list with file:line citation for each"
      pattern: "lib/scraper\\.py:[0-9]+|ingest_wechat\\.py:[0-9]+"
    - from: "REVIEW.md TL;DR"
      to: "REVIEW.md §9 verdict"
      via: "F-1 unlock verdict appears in both, must agree"
      pattern: "ready-now|needs-T5|blocked-on|not-needed"
---

<objective>
T4 — Deep read-only review of `lib/scraper.py` (418 LOC, last commit at HEAD).

Purpose: Decide whether F-1 (cascade-order divergence between `lib/scraper.py` and `ingest_wechat.py`, flagged HIGH in T3 REVIEW.md and in CLAUDE.md "Lessons Learned" 2026-05-08 #1) needs its own immediate fix-quick (T5) or can be backlogged. Produce a **REVIEW.md** following the exact 10-section schema in the task brief.

Output: `260511-kxd-REVIEW.md` at the path declared in `must_haves.artifacts`.

Non-output: NO code edits. NO business-file commits. NO Hermes SSH. NO pytest invocation. The only deliverable is REVIEW.md (and PLAN.md, already authored).

This is a single-task plan because the deliverable is a single document.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@CLAUDE.md
@.planning/quick/260511-d7m-t3-batch-ingest-from-spider-py-deep-revi/260511-d7m-REVIEW.md
@lib/scraper.py
@ingest_wechat.py
@batch_ingest_from_spider.py
@tests/unit/test_scraper.py
@tests/unit/test_scraper_ua_img_merge.py
@tests/unit/test_apify_rotation.py
@tests/unit/test_apify_run_input.py

<discovery>
**Source files (verified by Glob during planning, do NOT re-discover):**
- `lib/scraper.py` — 418 LOC (`wc -l` confirmed)
- `ingest_wechat.py` — 1436 LOC (T2 audit target — see note below)
- `batch_ingest_from_spider.py` — 2035 LOC (T3 audited; treat REVIEW.md as ground truth, do not re-audit)

**T2 review note — IMPORTANT for the executor:**
The task brief asks to "self-find the T2 (ingest_wechat) review directory by globbing for `*t2-*` or `*ingest-wechat*`". Planner ran `Glob` for both patterns and found:
- `.planning/quick/260510-rl2-f-4-ingest-wechat-py-trivial-cleanups-3-/` — this is the **F-4 cleanup quick**, NOT a T2 deep-review. PLAN/SUMMARY exist; no REVIEW.md.
- No directory matching `*t2*` or otherwise containing a deep-review of `ingest_wechat.py` exists locally.

Conclusion: there is **no T2 review document to import findings from**. The executor should:
1. Note this fact in §1 or §10 of REVIEW.md (so future readers know F-1 audit is grounded directly on `ingest_wechat.py` source, not on a prior peer-review).
2. Read `ingest_wechat.py` directly (specifically the cascade dispatcher around lines 920-942 per CLAUDE.md anchor 2026-05-08 #1) to extract its real cascade order — this is unavoidable for §3.
3. NOT block planning/execution waiting for T2 — just rely on the source file.

**Cascade entry-points to inspect (per CLAUDE.md anchor 2026-05-08 #1):**
- `lib/scraper.py:_scrape_wechat()` — search for `_scrape_wechat` function definition; document order in which Apify / CDP / MCP / UA helpers are called.
- `ingest_wechat.py:920-942` — read ±20 lines around this range; document order found.

**Tests in scope for A7:**
- `tests/unit/test_scraper.py`
- `tests/unit/test_scraper_ua_img_merge.py`
- `tests/unit/test_apify_rotation.py` — added by quick 260509-elc per task brief (verify dual-token rotation coverage)
- `tests/unit/test_apify_run_input.py` — also dual-token / Apify-shape coverage

`wc -l` each before reading; document LOC + case count in §7.

**Trust boundary (from task brief — DO NOT re-audit):**

| Quick | Commit | Region |
|---|---|---|
| 260509-s29 W3 | e538b2d | LLM dispatcher (scraper doesn't call LLMs anyway) |
| 260509-p1n | f715f06 | Vision drain (in ingest_wechat, not scraper) |
| 260510-rl2 F-4 | 5d4e294 | trivial cleanups (mostly ingest_wechat) |
| 260511-b3y | b1e7fc8 | Vertex location (lib/vertex_gemini_complete.py) |
| 260511-d7m T3 | 8832e95 | batch_ingest_from_spider deep review (CLEAR) |
| 260508-ev2/dep | (see git log) | Apify dual-token + cascade reorder — verify only, don't re-audit |
| ainsert-260510 | (recent) | LightRAG ainsert path |

For 260508-ev2, "verify only" = note from `git log --grep=260508-ev2 --oneline` whether the cascade reorder commit landed and whether it touched `lib/scraper.py` or only `ingest_wechat.py`. This is the single most decisive piece of evidence for §3 / F-1 verdict. Spend ≤10 min here.
</discovery>

<interfaces>
**Trusted public API of lib/scraper.py (from header comment, lib/scraper.py:1-15):**
```python
# Public API:
#   - ScrapeResult (frozen dataclass)
#   - scrape_url(url, site_hint=None) -> ScrapeResult
#
# Internals (private, not exported):
#   - _route()              URL / site_hint → cascade identifier
#   - _passes_quality_gate() SCR-04 quality check
#   - _fetch_with_backoff_on_429() SCR-05 HTTP 429 retry schedule
#   - _scrape_wechat()       delegates to ingest_wechat existing cascade
#   - _scrape_generic()      trafilatura 4-layer cascade
```

**ScrapeResult shape (lib/scraper.py:65-77):**
```python
@dataclass(frozen=True)
class ScrapeResult:
    markdown: str
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    method: str = ""
    summary_only: bool = False
    content_html: Optional[str] = None  # WeChat-only per Phase 19
```

This shape is the consumer contract for §A3. Already-known dual-key consumer (`scraped.markdown` AND `scraped.content_html`) is documented in T3 REVIEW §2 (2026-05-05 #4 lesson, status=fixed) at `batch_ingest_from_spider.py:1041-1053`.
</interfaces>

<lessons>
**5 CLAUDE.md "Lessons Learned" anchors (MUST appear in REVIEW.md §2):**

1. **2026-05-08 #1 (THE star lesson)** — `lib/scraper._scrape_wechat()` cascade was `Apify→CDP→MCP→UA` (paid first); `ingest_wechat.py:920-942` was `UA→Apify→MCP→CDP` (free first). `batch_ingest_from_spider.py` routes through `lib/scraper.py`, so 2026-05-08 09:00 ADT cron used the bad order. Quick 260508-ev2 added F1a (`APIFY_TOKEN_BACKUP` rotation) + F1b (cascade reorder + `SCRAPE_CASCADE` env override). **Verify whether divergence still present today** — this is the F-1 unlock test.

2. **2026-05-05 #1** — half-fix pattern: scraper Apify markdown-key fix landed in `ecaa2df` but consumer at `batch_ingest_from_spider.py:948` was inconsistent → silent reject of 121 articles overnight (53% of pool). T3 says fixed (REVIEW §2). Verify scraper side hasn't regressed.

3. **2026-05-05 #4** — Apify success but consumer reject = silent paid-for waste (operational angle of #1). Test in §A3: are there *new* shape mismatches today between what `lib/scraper.py` returns and what `batch_ingest_from_spider.py` / `ingest_wechat.py` consume?

4. **2026-05-05 #5** — body must persist atomically on scrape success, before any downstream gate. T3 says fixed at `batch_ingest_from_spider.py:_persist_scraped_body:946-993`. From the scraper side: does `lib/scraper.py` itself have any path that returns "scrape succeeded" without a real body? (silent-empty-success risk → §A5)

5. **2026-05-08 ev2** — `APIFY_TOKEN_BACKUP` rotation + `SCRAPE_CASCADE` env override deployment. Look for half-finished migration debris: TODOs referencing this rollout, dead branches gated on env vars that are always-on or always-off in prod, code paths that read deprecated env names. (→ §A1)
</lessons>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Read sources + author REVIEW.md covering all 7 audit angles</name>
  <files>.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md</files>
  <action>
**Read-only deep review of lib/scraper.py.** Produce a single output: `260511-kxd-REVIEW.md`.

**Step 1 — Anchor & verify (~15 min):**
1. Read `CLAUDE.md` "Lessons Learned" — confirm the 5 anchor lessons summarized in `<lessons>` above. Quote relevant lines (file:line in CLAUDE.md if needed).
2. Read `.planning/quick/260511-d7m-t3-batch-ingest-from-spider-py-deep-revi/260511-d7m-REVIEW.md` — extract any T3 finding that touches `lib/scraper.py` (T3 found F-2 lib→app `config` import inversion; cite that finding by ID and decide whether `lib/scraper.py` is one of the affected lib files).
3. `git log --oneline --grep="260508-ev2" --all` and `git log --oneline --grep="260508-dep" --all` — record the SHAs of the cascade-reorder commits and confirm whether each touched `lib/scraper.py` (use `git show --stat <sha>`). This is the single decisive evidence for §3.
4. Confirm there is NO prior T2 review (`.planning/quick/*t2*` and `*ingest-wechat*` globs already returned empty in planning; only `260510-rl2` F-4 cleanup exists). Note this in §1.

**Step 2 — Read source (~30 min):**
1. `wc -l lib/scraper.py` (already known: 418) — `git log -1 --oneline -- lib/scraper.py` to record last-commit SHA for the §0 file header.
2. Read `lib/scraper.py` end-to-end. Build the §1 sectional map (function name + first-line + LOC + one-line purpose). Use the T3 §1 table format as a template.
3. Read `ingest_wechat.py` lines 880-980 (cascade dispatcher around the anchor 920-942) to extract the *actual* cascade order present today. Document with explicit file:line citations.
4. `wc -l` and read each test file: `tests/unit/test_scraper.py`, `tests/unit/test_scraper_ua_img_merge.py`, `tests/unit/test_apify_rotation.py`, `tests/unit/test_apify_run_input.py`. Count test cases per file (grep `^def test_` or `pytest.mark.parametrize`). This feeds §7.

**Step 3 — 7-angle audit (~60 min):** address each angle in REVIEW.md §4 (severity findings) AND in dedicated §6/§7 sections where the schema requires:

- **A1 (Dead code / migration debris):** `grep -nE "TODO|FIXME|XXX|HACK|DEPRECATED|Phase [0-9]+|Was:|Wave [0-9]+|0[abc]\.|Legacy:" lib/scraper.py` — for each hit, verdict: still-applicable / fixed / partial / N/A. Report density (count per 100 LOC).
- **A2 — STAR ANGLE (Cascade configuration + ordering):** in §3 (its own section, schema-mandated). Document:
  - Cascade order in `lib/scraper.py:_scrape_wechat()` — list each helper call in invocation order with file:line.
  - Cascade order in `ingest_wechat.py:920-942` — same list with file:line.
  - Side-by-side comparison. Divergence still present? Y/N. Source-of-truth recommendation (which file should be authoritative).
  - If quick 260508-ev2 unified them, confirm with the SHA from Step 1.3 and call out as "fixed" with evidence.
- **A3 (Producer↔Consumer data shape):** Three-way grep for the keys ScrapeResult exposes (`markdown`, `content_html`, `images`, `metadata`, `method`, `summary_only`):
  - `grep -n "scraped\.\(markdown\|content_html\|images\|metadata\|method\|summary_only\)" batch_ingest_from_spider.py ingest_wechat.py`
  - For any consumer that reads only ONE of (`markdown`, `content_html`) where the producer can return either — flag as half-fix recurrence risk.
- **A4 (Cross-module coupling):** `grep -nE "^(from|import)" lib/scraper.py` — list every import. Flag any reverse `lib → app` (e.g. `import config`, `from ingest_wechat import …`). Cross-reference T3 F-2 (lib→app `config` inversion). Reverse: `grep -rn "from lib.scraper\|from lib import scraper\|import lib.scraper" --include="*.py"` to enumerate consumers.
- **A5 (Error-handling silent-fail):** Read every `try / except` block in `lib/scraper.py`. For each: does it swallow the exception? Does it log? Does it return a `ScrapeResult(markdown="")` (silent-empty-success)? Specifically check Apify dual-token rotation logic (per F1a 260508-ev2): when primary token 401/402, does the rotation trigger? Is failure surfaced?
- **A6 (Async engineering):** `grep -nE "async def|await |asyncio\.|create_task|wait_for|gather" lib/scraper.py` — list timeouts (Apify __, UA 30s, CDP __, MCP __). Flag any `asyncio.create_task(...)` whose handle is not awaited (p1n drain pattern relevance). Inconsistent timeouts = MEDIUM.
- **A7 (Test coverage):** From Step 2.4, report LOC + case count per test file. Specifically check:
  - Is there a test that asserts the cascade *order* (e.g. mocks all four providers, fails the first, asserts second is called)?
  - Is dual-token rotation covered (`test_apify_rotation.py` LOC + cases)?
  - Is `_passes_quality_gate` (SCR-04) covered?
  Gaps → LOW or MEDIUM depending on risk.

**Step 4 — Write REVIEW.md (~30 min):** match the exact 10-section schema from the task brief. Use the T3 REVIEW.md formatting (severity tables, citation style with file:line, evidence-first prose) as a model. Skip nothing — explicit "no findings in A_X" if so.

**Step 5 — Verdict & sanity-check (~10 min):**
- Compute severity counts (HIGH/MEDIUM/LOW). Apply task-brief decision rule for §9:
  - HIGH = 0 AND MEDIUM ≤ 3 → F-1 = `ready-now` (backlog, no T5)
  - HIGH ≥ 1 → F-1 = `needs-T5` (ship fix quick)
  - Cascade divergence already independently resolved (e.g. 260508-ev2 unified both files) → F-1 = `not-needed`
  - Any blocker not in scope → F-1 = `blocked-on-X` (name X)
- Make sure TL;DR verdict and §9 verdict match (key_link in must_haves).
- `git status --short` — final check: only `.planning/quick/260511-kxd-*/PLAN.md` and `260511-kxd-REVIEW.md` should appear. If anything else is dirty, STOP and report.

**Anti-fabrication discipline (HARD):**
- Every finding: cite file:line, commit SHA, or `.scratch/...log` path. No bare assertions.
- No "looks fine" — write "no findings in A_X" explicitly if so.
- If a 7-angle question can't be answered confidently, list it in §10 (Open questions for user). Don't guess.
- Do NOT modify any code file. Do NOT commit any business file. Do NOT touch `.env`. Do NOT SSH Hermes. Do NOT run `pytest`.

**Wall-time budget:** target 2-3h. Hard cap 4h. If at 4h still not converged, ship a partial REVIEW.md with §10 explicitly noting `incomplete: angles A_X..A_Y not done` — partial review > fabricated review.

**Tools allowed:** Read, Grep, Glob, Bash for `wc -l`, `git log`, `git show`, `git status --short`. No Write outside the REVIEW.md target path.
  </action>
  <verify>
    <automated>node -e "const fs=require('fs');const p='.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md';const c=fs.readFileSync(p,'utf8');const required=['## TL;DR','## 1. File sectional map','## 2. CLAUDE.md','## 3. Cascade divergence','## 4. Findings by severity','## 5. Cross-cutting','## 6. Async','## 7. Test coverage','## 8. Recommended fix-quick','## 9. Module verdict','## 10. Open questions'];const missing=required.filter(s=>!c.includes(s));if(missing.length){console.error('MISSING SECTIONS:',missing);process.exit(1)};const hasVerdict=/ready-now|needs-T5|blocked-on|not-needed/.test(c);if(!hasVerdict){console.error('MISSING F-1 verdict token');process.exit(1)};console.log('OK '+c.length+' chars, all 11 schema markers present, verdict token found.')"</automated>
  </verify>
  <done>
- `260511-kxd-REVIEW.md` exists at the configured path.
- All 10 schema sections (plus TL;DR) present in correct order.
- All 7 audit angles A1..A7 addressed (substantive findings or explicit "no findings").
- All 5 anchor CLAUDE.md lessons cross-referenced in §2 with status + evidence.
- §3 lists actual cascade order for both `lib/scraper.py` and `ingest_wechat.py`, each with file:line citation.
- F-1 unlock verdict explicit in TL;DR and §9, both agreeing.
- Every finding cites raw evidence (file:line, commit SHA, or log path).
- `git status --short` shows ONLY `.planning/quick/260511-kxd-*/PLAN.md` and `260511-kxd-REVIEW.md`.
- The verify automated command exits 0.
  </done>
</task>

</tasks>

<verification>
**Final phase-level checks (run after task completes):**

1. **Schema completeness:** the verify command above must pass.
2. **Read-only discipline:**
   ```bash
   git status --short
   ```
   Expected output: ONLY two lines, both under `.planning/quick/260511-kxd-*/`. Anything else → STOP and report (do NOT auto-revert; surface to user).
3. **Evidence density spot-check:** REVIEW.md should contain at least 15 distinct `file:line` citations (grep `:[0-9]\+`) and at least 2 commit SHAs (grep `[0-9a-f]\{7,40\}`). Low evidence density = fabrication risk.
4. **Verdict consistency:** TL;DR verdict token (one of `ready-now` / `needs-T5` / `blocked-on-X` / `not-needed`) must match §9 verdict.
5. **No business-file edits:** `git diff --stat HEAD -- 'lib/' '*.py' '~/.hermes/'` must return empty (no diffs outside .planning/).
</verification>

<success_criteria>
- REVIEW.md exists, all 10 schema sections present, F-1 verdict explicit and consistent across TL;DR + §9.
- All 7 audit angles addressed; all 5 anchor lessons cross-referenced.
- All findings cite raw evidence; no fabrication.
- Read-only discipline preserved: `git status` shows only PLAN.md + REVIEW.md changes inside the quick directory.
- The user can read §9 and immediately know whether to schedule a T5 fix-quick or backlog F-1.
</success_criteria>

<output>
After completion, create `.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-SUMMARY.md` per execute-plan workflow defaults. SUMMARY should record:
- Severity counts (HIGH/MEDIUM/LOW)
- F-1 unlock verdict + one-line justification
- Whether cascade divergence (CLAUDE.md 2026-05-08 #1) is still present today
- Number of file:line citations in REVIEW.md (evidence density signal)
- Wall-clock time spent

Commit message: `docs(quick-260511-kxd): T4 lib/scraper.py deep review (read-only post-release hygiene)`
Files in commit: ONLY `.planning/quick/260511-kxd-*/PLAN.md`, `.planning/quick/260511-kxd-*/REVIEW.md`, `.planning/quick/260511-kxd-*/SUMMARY.md`. NO business files.
</output>
