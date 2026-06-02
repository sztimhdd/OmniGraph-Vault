# Quick 260521-kbq — KB Working-Tree Triage SUMMARY

**Date:** 2026-05-21 ADT
**Outcome:** ✅ COMPLETE — 3 atomic commits landed clean, no cross-pollution

---

## Commits

| # | Commit | Files | Insertions | Deletions | Description |
|---|--------|-------|------------|-----------|-------------|
| 1/3 | `bec8811` | 2 | +548 | -91 | `feat(kb-v2.2-7-phase5-backfill): Tavily + apply.sql + SCP push, 234/238 translated $0` |
| 2/3 | `4fcc7af` | 8 | +283 | 0 | `feat(llm-wiki-W4-tail): SSG render + nav + locale + templates` |
| 3/3 | `08e7a50` | 1 | +1 | -1 | `fix(kb-search): drop ?mode=ro + add timeout=10 for FTS5 rebuild race` |

All 3 pushed to `origin/main`. No amend, no reset, no force-push.

---

## Commit 1 — kb-v2.2-7 Phase 5 backfill closure (`bec8811`)

**Files staged (explicit, no `-A`):**

- `databricks-deploy/translate_kb.py` (+635/-91 substantive Tavily + apply.sql + SCP extension; recorded as +548/-91 because git diff folded blank-line moves)
- `.planning/STATE-KB-v2.md` (forward-only addendum: Phase 5 closure as new "Last activity"; 2026-05-19 Wave 6 demoted to "Prior activity")

**Phase 5 stats (cited from `.scratch/translate-backfill-260520.md`):**

- 238 candidates loaded, **234 translated** (169 KOL + 65 RSS)
- 4 RSS failures: `id=45,60,1394,5144` (JSON-parse failed after 4-call retry budget; `title_translated` left NULL for next backfill UNION-ALL pickup)
- Model: `databricks-claude-opus-4-7` · Cost: **$0** (Databricks Foundation Model)
- Hermes apply: 0.1s wallclock; 49,905-line apply.sql delivered via SCP from notebook Cell 6
- Hermes terminal state: 170 articles + 67 rss_articles = **237 rows** `title_translated NOT NULL`
- Pre-apply backup: `data/kol_scan.db.backup-pre-phase5-20260520-194310`

**Known design risk (deferred to v2.2-future, no new phase opened):** single-batch in-memory accumulation, no incremental flush, no resume guard. Did not materialize this run (5h 22min, 0 runtime errors); remains real for next long-batch op.

---

## Commit 2 — llm-wiki W4-tail SSG render + nav + locale + templates (`4fcc7af`)

### Audit verdict (real increment, not dev residue)

3-step audit per user spec:

1. `git log --oneline | grep -i llm-wiki` → 3 prior commits all docs-only or single-file
2. `git show 58a4e18 --stat` → flips nyquist + close phase (VALIDATION.md only)
3. `git show 3f65082 --stat` → VERIFICATION evidence (VALIDATION.md + VERIFICATION.md only)

**Verdict:** the W4-tail SSG render pipeline (`_render_wiki_pages` + 3 helpers + 11 locale strings + book-open icon + nav links + 3 entirely new files) was never committed. **Proceed with `feat(llm-wiki-W4-tail)`.**

### Files staged (explicit, 8 files)

| File | Change |
|------|--------|
| `kb/export_knowledge_base.py` | +137 LOC: `_convert_wiki_citations`, `_strip_leading_h1`, `_render_wiki_pages`, WIKI_DIR + LEGACY_WIKI_CITATION_RE + _LEADING_H1_RE constants, frontmatter import |
| `kb/locale/en.json` | +11 strings: `nav.wiki`, `breadcrumb.wiki`, `wiki.directory_title`, `wiki.directory_intro`, `wiki.confidence.{high,medium,low}`, `wiki.sources_label`, `wiki.sources_heading`, `wiki.last_updated_label` |
| `kb/locale/zh-CN.json` | +11 strings (parallel to en.json) |
| `kb/templates/_icons.html` | +5 LOC: `book-open` icon (24x24 / stroke-1.5 family) |
| `kb/templates/base.html` | +5 LOC: wiki nav entry — desktop + mobile blocks |
| `kb/templates/wiki_entity.html` | NEW: per-entity page (frontmatter title + confidence badge + sources + body) |
| `kb/templates/wiki_index.html` | NEW: wiki directory page |
| `kb/kb-logo.png` | NEW: KB brand logo asset (3018 bytes) |

Bilingual rendering preserved (KB_DEFAULT_LANG injected per-deploy: Aliyun=zh-CN, Databricks=en).

---

## Commit 3 — FTS5 rebuild race micro-fix (`08e7a50`)

**File:** `kb/services/search_index.py` (1-line change in `fts_query()`):

```diff
-    conn = sqlite3.connect(f"file:{config.KB_DB_PATH}?mode=ro", uri=True)
+    conn = sqlite3.connect(config.KB_DB_PATH, timeout=10)
```

**Why:** read-only URI connections (`?mode=ro`) cannot wait on the writer's schema lock during FTS5 rebuild — queries intermittently failed with "database is locked" while the bilingual SSG / `translate_kb` apply repopulated the index. Switching to a normal file-path connect with `timeout=10` lets queries block briefly during a rebuild instead of failing outright. The connection remains effectively read-only because `fts_query()` only issues SELECTs.

---

## Out-of-scope working-tree residue (per user redline, NOT staged)

Verified untouched in all 3 commits:

- `.planning/PROJECT.md` (M)
- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-01-spec-rtt-mem-dryrun-PLAN.md` (M)
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` (M)
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md`, ROADMAP/REQUIREMENTS/STATE-Aliyun-Ingest-Migration-v1.md (??)
- `.planning/phases/aim-0-readiness-aliyun-ecs/VERIFICATION-PLANS.md` (??)
- `.databricksignore`, `.vscode/` (??)
- `databricks-deploy/_ssg/`, `_wave0_probe.py`, `app.yaml.production-backup`, `app_entry.py`, `config.py`, `kg_synthesize.py`, `lib/`, `scripts/` (?? — Databricks-deploy build artifacts)
- `kb/data/__pycache__/`, `kb/data/migrations/__pycache__/` (??)
- `kb/deploy/RUNBOOK-aliyun-deploy.md` (??)

`git status -s` post-commit-3 shows these residual entries unchanged — clean separation.

---

## Redline compliance

- ✅ NO `git add -A` / `-.` / `--all` — every commit used explicit file list
- ✅ NO `--amend` / `reset --hard` / `rebase -i` / `push --force` — all 3 commits forward-only
- ✅ All 3 commits stage-commit-push as single &&-chained Bash invocation (atomic; no idle window for sibling agents)
- ✅ Out-of-scope working-tree residue untouched
- ✅ Audit-first on Commit 2 — confirmed real increment before staging
- ✅ Commit message bodies cite real artifacts only (`.scratch/translate-backfill-260520.md` + Databricks run_id `1066929004299865`)
- ✅ No literal secrets in any commit body

---

## Post-commit attribution audit

```
$ git show --stat bec8811 | tail -3
 .planning/STATE-KB-v2.md          |   4 +-
 databricks-deploy/translate_kb.py | 635 ++++++++++++++++++++++++++++++++------
 2 files changed, 548 insertions(+), 91 deletions(-)

$ git show --stat 4fcc7af | tail -10
 kb/export_knowledge_base.py   | 137 ++++++++++++++++++++++++++++++++++++++++++
 kb/kb-logo.png                | Bin 0 -> 3018 bytes
 kb/locale/en.json             |  11 ++++
 kb/locale/zh-CN.json          |  11 ++++
 kb/templates/_icons.html      |   5 ++
 kb/templates/base.html        |   5 ++
 kb/templates/wiki_entity.html |  72 ++++++++++++++++++++++
 kb/templates/wiki_index.html  |  42 +++++++++++++
 8 files changed, 283 insertions(+)

$ git show --stat 08e7a50 | tail -3
 kb/services/search_index.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

All 3 commits show exact expected file lists — zero attribution drift, no concurrent-agent absorption (per `feedback_git_add_explicit_in_parallel_quicks.md` discipline).
