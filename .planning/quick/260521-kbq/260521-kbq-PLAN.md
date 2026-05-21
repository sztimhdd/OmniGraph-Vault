# Quick 260521-kbq — KB Working-Tree Triage (3 atomic commits)

**Date:** 2026-05-21 ADT
**Scope:** Close out three independent KB working-tree tracks with three atomic commits, no cross-pollution (PRINCIPLE #3).

---

## Pre-flight Audit (done)

### Working-tree inventory
- 10 modified files
- 17 untracked entries

### In-scope (3 commits)
- `databricks-deploy/translate_kb.py` (M)
- `.planning/STATE-KB-v2.md` (M — forward-only addendum, written by orchestrator)
- `kb/export_knowledge_base.py` (M)
- `kb/locale/en.json` (M)
- `kb/locale/zh-CN.json` (M)
- `kb/templates/_icons.html` (M)
- `kb/templates/base.html` (M)
- `kb/templates/wiki_entity.html` (??)
- `kb/templates/wiki_index.html` (??)
- `kb/kb-logo.png` (??)
- `kb/services/search_index.py` (M)

### Out-of-scope (DO NOT stage; user redline)
- `.planning/PROJECT.md`
- `.planning/phases/aim-0-readiness-aliyun-ecs/aim-0-01-spec-rtt-mem-dryrun-PLAN.md`
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md`
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` + ROADMAP/REQUIREMENTS/STATE-Aliyun-Ingest-Migration-v1.md
- `.planning/phases/aim-0-readiness-aliyun-ecs/VERIFICATION-PLANS.md`
- `.databricksignore`, `.vscode/`
- `databricks-deploy/_ssg/`, `_wave0_probe.py`, `app.yaml.production-backup`, `app_entry.py`, `config.py`, `kg_synthesize.py`, `lib/`, `scripts/`
- `kb/data/__pycache__/`, `kb/data/migrations/__pycache__/`
- `kb/deploy/RUNBOOK-aliyun-deploy.md`

### Commit-2 audit verdict (real increment vs dev residue)
- Last llm-wiki commits: `58a4e18` (docs flip nyquist + close), `3f65082` (VERIFICATION evidence + VALIDATION tick), `0acbe46` (W2 SKILL.md preflight) — all docs-only or single-file feature.
- Current diff adds the W4-tail SSG render pipeline (3 new helpers in export_knowledge_base.py + 11 nav/wiki locale strings + book-open icon + wiki nav links + 3 entirely new files for templates and logo).
- Verdict: REAL new W4-tail SSG rendering pipeline never committed. Proceed with `feat(llm-wiki-W4-tail)`.

---

## Commits

### Commit 1 — kb-v2.2-7 Phase 5 translation backfill closure

Files: databricks-deploy/translate_kb.py + .planning/STATE-KB-v2.md (forward-only addendum just below current "Last activity").

Addendum content (Chinese, evidence-cited): Phase 5 closed 2026-05-21; 234/238 translated; 4 RSS failures id=45/60/1394/5144; model databricks-claude-opus-4-7; $0; Hermes apply 0.1s; terminal 170 + 67 = 237 rows; backup data/kol_scan.db.backup-pre-phase5-20260520-194310; report .scratch/translate-backfill-260520.md; single-batch design risk queued for v2.2-future.

Commit message: `feat(kb-v2.2-7-phase5-backfill): Tavily + apply.sql + SCP push, 234/238 translated $0`

### Commit 2 — llm-wiki W4-tail SSG render + nav + locale + templates

Files (8): kb/export_knowledge_base.py, kb/locale/en.json, kb/locale/zh-CN.json, kb/templates/_icons.html, kb/templates/base.html, kb/templates/wiki_entity.html, kb/templates/wiki_index.html, kb/kb-logo.png.

Commit message: `feat(llm-wiki-W4-tail): SSG render + nav + locale + templates`

### Commit 3 — FTS5 rebuild race micro-fix

File: kb/services/search_index.py (1-liner: drop ?mode=ro URI flag, add timeout=10).

Commit message: `fix(kb-search): drop ?mode=ro + add timeout=10 for FTS5 rebuild race`

---

## Redlines (verbatim from user)

- 严禁 `git add -A` / `-.` / `--all`,显式列文件
- 严禁 `--amend` / `reset --hard` / `rebase -i` / `push --force`
- 三个 commit 各自 atomic 单 && 链 stage-commit-push
- 工作树残留(databricks-deploy 部署产物 / aim-0 milestone 4 件套 / kdb-2 SMOKE-EVIDENCE / PROJECT.md +29 / kb/data/__pycache__)不在本 quick 范围,跳过不动
- 若审计发现 4th 类未列入的 working tree 改动需要 commit,停下报告,不扩 scope
- 不向 commit message body 灌伪造数据,只引 `.scratch/<log>` 真实路径

---

## Closure

After all 3 commits land: write SUMMARY.md, append row to `.planning/STATE.md` Quick Tasks Completed table, final docs commit.
