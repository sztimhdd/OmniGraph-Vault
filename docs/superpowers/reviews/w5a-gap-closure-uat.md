# W5A Gap-Closure Production Deploy + UAT — vitaclaw-aliyun

- **Date:** 2026-08-12 (CST)
- **Deployed:** `kb/wiki_compiler/engine.py` @ local HEAD `ae5b8097` (md5 `44f10cf7533e36fd0ac7ecddf2074af4`) — contains both gap fixes: GAP 1 final candidate validation gates (7c1c57cc) + SET_METADATA allowlist / full-WikiPatch suggestion JSON (cbf3b77f)
- **Operator:** PRODUCTION OPS subagent; no commits made; no production data touched
- **Prior art:** `docs/superpowers/reviews/w5a-gap-closure-verification.md` (18/18 PASS, fresh verifier)

---

## Phase 0 — Recon evidence

| Item | Value |
|---|---|
| Local engine.py md5 (@ ae5b8097) | `44f10cf7533e36fd0ac7ecddf2074af4` |
| Remote engine.py md5 (pre-deploy, c8ec5227-era) | `819d5259ef8020b44a8e3322242d73f1` → **DIFFERS as expected** |
| Service | `omnigraph-daily-ingest.service` **active**; ActiveEnterTimestamp `Wed 2026-08-12 03:21:39 CST` |
| Batch state | **BUSY** — MainPID `3741157`, `venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 10`, elapsed 29:33 at recon, still running at close (33:11). `ps aux \| grep -c batch_ingest` = 3 (process + shell wrappers; verified via MainPID) |
| Remote file set | `kb/wiki_compiler/` = `__init__.py, assembler.py, engine.py, models.py, adapters/` (`__init__.py, w3.py`) — all present from prior c8ec5227 deploy; only engine.py changed locally since |
| Lazy import | `batch_ingest_from_spider.py:1592` = function-level `from kb.wiki_update import apply_suggestion_atomic, generate_wiki_suggestions` → SCP'd code goes live at W3 hook time; **no restart needed** |
| Journal (since 03:20) | Only `image_processed` events; W3 hook **not yet fired** → in-flight run will load the NEW engine.py at hook time |
| Production baseline | `kb/wiki/entities` = 26; `kb/wiki/_suggestions` = 5 visible files (+hidden `.gitkeep`); `.locks/` = 0 |

## Phase 1 — Deploy mapping

Procedure: backup working copy → `scp` to `/tmp/engine.py.new` → atomic `mv` into place (avoids a half-written file being imported mid-batch) → both-side md5 → remote import check with venv-aim1 python.

| File | Local md5 | Remote md5 (post) | Match |
|---|---|---|---|
| `kb/wiki_compiler/engine.py` | `44f10cf7…` | `44f10cf7533e36fd0ac7ecddf2074af4` | ✅ |

- **Rollback:** `/root/w5a-rollback/engine.py.bak-gapclosure` — md5 `819d5259…` verified == pre-deploy live file. Restore: `cp /root/w5a-rollback/engine.py.bak-gapclosure /root/OmniGraph-Vault/kb/wiki_compiler/engine.py`
- **Import check:** `/tmp/verify_imports_gap.py` (`apply_patch, classify_patch, validate_evidence, _validate_candidate, WikiPatch`) → `IMPORTS_OK gap-closure` ✅
- Other W5A files (`models.py`, `assembler.py`, `adapters/*`) unchanged by cbf3b77f/7c1c57cc — left untouched per brief.

## Phase 2 — Production UAT A–E (isolated `/tmp/w5a-uat-*` roots only; venv-aim1 python 3.11)

One script `/tmp/uat_gaps.py`, all five checks, run twice (second run after harness fix — see Issues). **Final run: 8/8 PASS.**

```
PASS  A valid CREATE_PAGE auto-applies: classify=auto_apply status=applied file_exists=True ids=[1, 2, 3] lint=[] warnings=[]
PASS  B invalid candidate rejected before write: status=rejected error="[^1]: type=article ref='9999999999' not in corpus; [^1]: ... not in corpus" file_exists=False candidate_tmp_leftovers=0 suggestion_files=0 error_book_entries=1 error_book_lint_name=wiki_compiler:candidate_integrity
PASS  C1 MERGE_SOURCES+SET_METADATA{created} never auto-applies; created preserved: classify=suggestion_only status=suggestion page_unchanged=True created='2026-01-01' (before '2026-01-01') suggestion=uat-existing-wpatch-1c08d692a8dd777a.json
PASS  C2 SET_METADATA{created} alone is suggestion_only; created preserved: classify=suggestion_only status=suggestion page_unchanged=True created='2026-01-01'
PASS  C3 SET_METADATA{last_updated}: created never mutated on any path: classify=auto_apply (observed; allowlisted key -> auto_apply per design §5.3) status=applied created='2026-01-01' last_updated=datetime.date(1999, 1, 1)
PASS  D suggestion JSON round-trips full WikiPatch + outcome fields: file=uat-existing-wpatch-1c08d692a8dd777a.json ops=['MERGE_SOURCES', 'SET_METADATA'] recon.patch_id==True recon.target_path==True policy_hint=suggestion_only suggested_content_len=448
PASS  E production service healthy after UAT: systemctl is-active -> 'active'
PASS  E production kb/wiki free of UAT artifacts: grep w5a-uat hits='' candidate/tmp leftovers=''
TOTAL: 8/8 PASS
```

Per-check detail:

- **A — valid CREATE_PAGE auto-applies:** canonical 3-source page (article/web/article, `id: 1..3` id-first), GFM `[^1] [^2] [^3]` + `## References` defs, all article refs in evidence known-hashes. `classify=auto_apply`, `status=applied`, file written with `ids=[1,2,3]`, `lint_citation_integrity=[]`, `warnings=[]`.
- **B — invalid candidate rejected before write:** CREATE_PAGE whose `sources[0].ref = '9999999999'` is absent from evidence known-hashes. Candidate gate fired pre-write: `status=rejected`, error = citation-integrity `ref='9999999999' not in corpus` (flagged twice — body citation AND `## References` definition, the documented whole-page lint scan), target file **does not exist**, **0** `.candidate-check-*` leftovers, 0 suggestion files, exactly 1 Error Book entry with `lint_name=wiki_compiler:candidate_integrity` + patch provenance (captured via injected `error_book` hook — nothing written to the production Error Book).
- **C — forbidden SET_METADATA cannot mutate `created`:**
  - C1 `MERGE_SOURCES` + `SET_METADATA{created:'1999-01-01'}` on existing page (`created:'2026-01-01'`): `classify=suggestion_only` (MINOR-5 fix live), `status=suggestion`, page byte-identical, `created` preserved.
  - C2 `SET_METADATA{created}` alone: `suggestion_only`, page untouched, `created` preserved.
  - C3 `SET_METADATA{last_updated}` alone: **observed `classify=auto_apply`** (allowlisted key — engine design §5.3; brief predicted suggestion_only, see Issues), `status=applied`, `last_updated` rewritten, **`created` still `'2026-01-01'`** — critical key preserved even on the auto-apply path (`_set_metadata` allowlist defense-in-depth).
- **D — suggestion JSON round-trips:** C1's suggestion file `kb/wiki/_suggestions/uat-existing-wpatch-1c08d692a8dd777a.json` (isolated root): `payload["patch"]` present; `WikiPatch.from_dict(payload["patch"])` reconstructs identical `patch_id`, `target_path`, `target_slug`, 2 operations (`MERGE_SOURCES`, `SET_METADATA`), 1 evidence; outcome fields `policy_hint=suggestion_only`, `reason`, `suggested_content` (448 chars) present.
- **E — production healthy + untouched:** `systemctl is-active` → `active` after all UAT; `grep -rl w5a-uat kb/wiki/` → empty; no `.candidate-check-*`/`*.tmp` in production `kb/wiki/`. Production counts entities 26→26; `_suggestions` 5 visible → 5 (the 6-vs-5 delta is the hidden `.gitkeep`, a measurement artifact — all file mtimes predate this session). Honest git status: `M kb/wiki/index.md` (auto-generated index regenerated by the in-flight production batch; pre-existing dirty tree per prior deploys) + pre-existing untracked `kb/wiki/entities/*.md` and `_suggestions/*.md` — none are UAT artifacts.

## Phase 3 — Restart decision

**NO RESTART — deferred.** Service was BUSY (MainPID 3741157 mid-batch) at deploy time and still busy at close; W3 hook had not yet fired. `batch_ingest_from_spider.py:1592` imports `kb.wiki_update` (→ `engine.py`) lazily at hook time, so the in-flight run loads the new engine.py when its W3 hook fires, and the next scheduled run (09:00) unconditionally uses it. Never restart a mid-batch ingest. Final state: `omnigraph-daily-ingest.service` **active**, MainPID 3741157, 33:11 elapsed.

## Issues found

1. **Brief-vs-engine expectation on C3 (informational, not a defect):** brief expected `SET_METADATA{last_updated}` alone on an existing page to classify `suggestion_only`; the engine classifies `auto_apply` because `last_updated`/`confidence_level` are the design-§5.3 allowlisted keys (matches the 18/18 verifier contract, `test_classify_set_metadata_confidence_level_auto_apply`). The W5A invariant that matters — `created` can never be mutated — held on every path. Recorded as observed behavior; no engine change needed.
2. **UAT harness bug (fixed, re-run):** first C3 check compared `last_updated` string to a `datetime.date` (PyYAML parses the engine's unquoted `1999-01-01` scalar into a date). Harness now normalizes via `.isoformat()`. Engine output is valid YAML and consistent with `frontmatter`-lib handling (same as `lint_staleness`).
3. **Pre-existing production dirt:** `M kb/wiki/index.md` + untracked entity/suggestion files predate this deploy (auto-generated index / prior W3-W1 activity, remote tree documented as carrying uncommitted hotfixes). Zero UAT artifacts verified.
4. **B error duplication:** the same citation-integrity failure appears twice in `result["error"]` (body citation + `## References` definition both scanned by `lint_citation_integrity`) — documented behavior, cosmetic only.

## Files created / modified

- **Local:** `docs/superpowers/reviews/w5a-gap-closure-uat.md` (this report) — only repo change; **nothing committed**
- **Remote (runtime):** `/root/OmniGraph-Vault/kb/wiki_compiler/engine.py` (deployed), `/root/w5a-rollback/engine.py.bak-gapclosure` (backup), `/tmp/verify_imports_gap.py`, `/tmp/uat_gaps.py` (test scripts)

## Verdict

**DEPLOY SUCCESSFUL — 8/8 UAT PASS.** All three W5A contract gaps confirmed live on production hardware: candidate integrity gates block bad writes before they happen (B), forbidden `SET_METADATA` can never mutate `created` (C1/C2/C3), suggestion JSONs round-trip full WikiPatches (D), valid CREATE_PAGE still auto-applies cleanly (A), and the service is healthy with zero production writes from UAT (E).
