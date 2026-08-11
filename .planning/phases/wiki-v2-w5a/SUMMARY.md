# W5A — Unified Patch Compiler Core — SUMMARY

**Phase:** wiki-v2-w5a
**Design:** `docs/superpowers/specs/2026-08-11-omnigraph-wiki-v2-w5a-patch-compiler-design.md` (approved commit `8f4c8090`; plan `bc9fcce5`)
**Status:** CLOSED — PASS (including master-review gap closure)

## Objective

Build a shared WikiPatch compiler (`kb/wiki_compiler/`) and converge the production W1/W3 write paths onto one seam: deterministic typed patches, shared validation/policy/apply, structured suggestions, no opaque placeholder page writes, no second lint implementation.

## Commit chain (new → old)

| Commit | Content |
|---|---|
| `727f6cfb` | docs: gap-closure production UAT report (8/8 PASS) |
| `ae5b8097` | docs: gap-closure verification report (18/18 PASS) |
| `7c1c57cc` | fix: final candidate validation gates before authoritative apply (§7) — GAP 1 |
| `cbf3b77f` | fix: SET_METADATA allowlist in classify_patch + full WikiPatch serialization in suggestions (§5.3/§5.4) — GAP 2 + GAP 3 |
| `507396fd` | docs: production UAT evidence report (A/B/C/D/E PASS) |
| `0d084d84` | docs: independent verification report (19/19 design properties) |
| `6146048a` | docs: ISSUES R46 |
| `c8ec5227` | fix: W1 engine seam + merge insertion + sources id emission (Task 6 repairs) |
| `cbec5264` | feat: converge production W3 path onto shared compiler (T4) |
| `ec787b3e` | feat: W3 adapter module (T4 first pass) |
| `e8bdc664` + `f40bfa34` | feat/fix: W1 canonical + prompt literal fix (T5) |
| `df573e1c` / `8150e928` / `64298303` | feat: engine / models / assembler (T3/T1/T2) |

## Verification

- Compiler core tests: 73/73 (models 29 + assembler 17 + engine 27)
- Full W5A suite: **164 passed / 0 failed** (13-file set incl. `test_wiki_compiler_candidate_gates.py`)
- Task 6 adversarial review: 13/15 PASS + 1 BLOCKER + 2 MAJOR → all repaired in `c8ec5227`
- Independent verification (19 design properties): PASS (report `docs/superpowers/reviews/w5a-adversarial-review.md` + `w5a-independent-verification.md`)
- **Master-review gap closure** (GPT-5.6): 3 contract gaps closed in shared compiler:
  - GAP 1 §7 candidate validation gates → `7c1c57cc` (frontmatter/citation BLOCKING → Error Book; wikilink WARN per wiki_health policy; 6 behavior-anchor tests)
  - GAP 2 §5.3 SET_METADATA allowlist → `cbf3b77f` (`created` never mutable; MERGE_SOURCES+SET_METADATA{created} → suggestion_only)
  - GAP 3 §5.4 full WikiPatch serialization → `cbf3b77f` (round-trippable `payload["patch"]` + policy/validation outcome)
  - Fresh verifier: **18/18 PASS** (report `w5a-gap-closure-verification.md`)

## Production

- Deployed via SCP (git 443-blocked): 9 files from `c8ec5227` (md5 9/9 match) + `engine.py` from `ae5b8097` (md5 match, `IMPORTS_OK`)
- venv: `venv-aim1`; rollback: `/root/w5a-rollback/` (engine.py.bak, engine.py.bak-gapclosure)
- UAT A/B/C/D/E (original) + gap-closure UAT A-E: **all PASS** on isolated `/tmp/w5a-uat-*` roots; production wiki pages never touched
- `omnigraph-daily-ingest.service` active; restart deferred (lazy import at `batch_ingest_from_spider.py:1592` delivers new code at hook time)
- Final service state: healthy

## Deferred to W5B (not W5A contract)

- Contradiction/staleness candidate checks (§7 order 9-10) — auto-apply candidate fresh by construction; LLM contradiction review is W5B
- Suggestion re-apply consumption (JSON now round-trippable; apply path not yet wired)
- Buffer ⊋ DB drift reconciliation (875 buffer files vs 234 DB∩buffer hashes; DB-first filter makes production safe)
