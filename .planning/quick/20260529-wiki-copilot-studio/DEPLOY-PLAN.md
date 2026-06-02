# Deploy Plan — Surface 5 New Wiki Entities to Databricks Apps

**Status:** PLAN (deploy not yet executed)
**Created:** 2026-05-29
**Scope:** Surface 5 new entity pages on the EDC Agentic AI Knowledge Base Databricks App at
`omnigraph-kb-2717931942638877.17.azure.databricksapps.com/wiki/<slug>.html`.

---

## What needs to ship

5 new entity .md files (already committed locally on `main`, not pushed):

| File | Slug | URL after deploy |
|------|------|------------------|
| kb/wiki/entities/copilot-studio.md | copilot-studio | /wiki/copilot-studio.html |
| kb/wiki/entities/declarative-agent.md | declarative-agent | /wiki/declarative-agent.html |
| kb/wiki/entities/generative-orchestration.md | generative-orchestration | /wiki/generative-orchestration.html |
| kb/wiki/entities/copilot-studio-vs-azure-ai-foundry.md | copilot-studio-vs-azure-ai-foundry | /wiki/copilot-studio-vs-azure-ai-foundry.html |
| kb/wiki/entities/mcp-in-copilot-studio.md | mcp-in-copilot-studio | /wiki/mcp-in-copilot-studio.html |

Plus 2 cross-link patches that don't need re-rendering of new HTML *content* but do need the
old entity HTML re-rendered to pick up the new "See also" line:

| File | Why |
|------|-----|
| kb/wiki/entities/claude-code.md | Added `[[copilot-studio]]` to Cross-references |
| kb/wiki/entities/anthropic.md   | Added `[[mcp-in-copilot-studio]]` to Cross-references |

## Deploy pipeline (verified against `databricks-deploy/deploy.sh`)

The full pipeline is required by **CLAUDE.md Rule 9** (touching `kb/static/` or `kb/templates/`
needs full Makefile deploy). This change only touches `kb/wiki/entities/` — *strictly* Rule 9
allows sync-only Pass 1+2+3 since `kb/wiki/entities/` is not under `kb/static/` or
`kb/templates/`. **However** wiki rendering is part of the SSG bake (`_render_wiki_pages` in
`kb/export_knowledge_base.py`), so without Pass 0 the new pages won't materialize as HTML
inside `_ssg/`. **Conclusion: full Makefile deploy is required.**

```
Pass 0:  bake kb/wiki/entities/*.md → kb/output/wiki/*.html  ★ critical for new pages
Pass 0:  rm -rf databricks-deploy/_ssg && cp -R kb/output databricks-deploy/_ssg
Pass 0b: <html lang="zh-CN"> → <html lang="en"> sed across _ssg
Pass 0c: stage kg_synthesize.py / config.py / lib/** into databricks-deploy/
Pass 0d: VitaClaw → "EDC Agentic AI Knowledge Base" rebrand sed across _ssg
Pass 1:  databricks sync --full ./databricks-deploy → workspace/databricks-deploy/
Pass 2:  databricks sync --full ./kb              → workspace/databricks-deploy/kb/
Pass 3:  databricks apps deploy omnigraph-kb --source-code-path workspace/databricks-deploy/
```

**Key gap:** `databricks-deploy/deploy.sh` Pass 0 does `cp -R kb/output databricks-deploy/_ssg`
but I haven't seen Pass 0 invoke the SSG bake itself. Need to verify whether `kb/output/`
is checked in (i.e. SSG runs offline as a separate command) OR whether `deploy.sh` should
run `python kb/export_knowledge_base.py` first.

## Pre-deploy checks I need to do before running the deploy

### 1. Confirm how `kb/output/` gets refreshed

`deploy.sh` Pass 0 is `rm -rf _ssg && cp -R kb/output _ssg`. It does NOT bake. So one of:

- (a) `kb/output/` is git-tracked and pre-baked → I need to bake locally, commit `kb/output/`,
      then deploy.
- (b) `kb/output/` is .gitignored, baked on-demand by a separate command.
- (c) Bake step lives elsewhere (CI? Makefile target? deploy.sh predecessor?).

Action: `git ls-files kb/output/wiki/ | head -5` and `cat .gitignore | grep -i output`.

### 2. Locate the SSG bake entry point and command line

`kb/export_knowledge_base.py` is the rendering module. There's likely a CLI runner —
either `python -m kb.export_knowledge_base` with args, or a Makefile target, or a wrapper
script. Need to identify before deploying.

### 3. Verify `kb/templates/wiki_entity.html` exists and renders the new pages

The renderer (`_render_wiki_pages`) calls `env.get_template("wiki_entity.html")`. If the
template assumes the legacy frontmatter shape (`sources: [article:hex, article:hex]` flat
list) and not the new dict-shape (`sources: [{id, type, ref, title}]`), my 5 new pages may
render with empty / broken sources sections.

Action: `cat kb/templates/wiki_entity.html` and verify it iterates `wiki.sources` as the
shape `_convert_wiki_citations` produces.

### 4. Verify `_convert_wiki_citations` handles new GFM `[^N]` form

The audit confirmed lint accepts both legacy `^[article:hex]` and new `[^N]`. The
SSG converter `_convert_wiki_citations` may or may not handle `[^N]` — needs source review.
If it doesn't, my 5 pages will render with raw `[^1]` text and missing source list.

Action: read `_convert_wiki_citations` (around `kb/export_knowledge_base.py:985`).

### 5. Re-bake claude-code.html + anthropic.html for cross-link patches

Pass 0 `_render_wiki_pages` iterates ALL `.md` under `kb/wiki/entities/`, so claude-code.md
and anthropic.md will be re-rendered with their new "See also" lines automatically. No
extra step.

### 6. Verify the wiki index page picks up the 5 new entries

`_render_wiki_index_page` consumes the summary list from `_render_wiki_pages`. If the
index template is plain (loops over the summaries), 5 new entries appear automatically.
If it's curated / hand-edited, I need a separate edit. Inspect
`kb/templates/wiki_index.html` (or whatever the index template is named).

## Halt triggers (re-stating CLAUDE.md Rule 9 + orchestrator constraints)

The original quick orchestrator said: NO push origin main; atomic local commit only;
wait for user review. The local commits (7 in total, see `git log --oneline -10`) are
ready. **Do not push and do not deploy without explicit user GO**.

Specific halts:

- **STOP if `kb/output/` is git-tracked AND user hasn't reviewed the full diff** including
  the auto-generated HTML for 5 new pages. If `kb/output/` is .gitignored, this concern
  is moot.
- **STOP if SSG template (`wiki_entity.html`) doesn't render new dict-shape sources
  correctly** — the SSG bake of my 5 pages would ship visibly broken pages. Fix the
  template (separate ticket) before deploying.
- **STOP on any deploy.sh failure** — Pass 0 / Pass 1 / Pass 2 / Pass 3 each have
  documented failure modes (see CLAUDE.md Rule 7 + Aliyun lessons). Don't paper over.
- **STOP if W3 lint catches a real failure post-deploy** — `kb/services/wiki_inject.py`
  uses `lint_staleness` to gate wiki context injection into synthesize. If staleness
  fails, synthesize will skip the wiki context (degraded but not broken).

## Two-phase execution plan

### Phase 1 — Local SSG bake + verification (no deploy)

1. Locate SSG bake command (action #1 + #2 above). Call it `BAKE_CMD` for now.
2. Run `BAKE_CMD` locally. Verify:
   - `kb/output/wiki/copilot-studio.html` exists and is non-empty.
   - Same for the other 4 new slugs.
   - `kb/output/wiki/index.html` lists all 5 new entries.
   - `kb/output/wiki/claude-code.html` body contains `copilot-studio` (cross-ref).
   - `kb/output/wiki/anthropic.html` body contains `mcp-in-copilot-studio` (cross-ref).
3. Open `kb/output/wiki/copilot-studio.html` in a local browser:
   - Frontmatter sources rendered as a numbered footnote bibliography.
   - `[[claude-code]]` rendered as a link to `/wiki/claude-code.html`.
   - Mermaid / ASCII diagrams render (or at least are readable).
4. If any of the above fails, fix the SSG template / converter (separate quick task) and
   re-bake. Do NOT proceed to Phase 2 until the local browser version looks right.

### Phase 2 — Databricks deploy (after Phase 1 green)

1. `git push origin main` (only after explicit user GO).
2. `bash databricks-deploy/deploy.sh` (full pipeline, Pass 0 → 0d → 1 → 2 → 3).
3. Monitor `make logs` (BUILD frame for Apps build success, APP frame for first
   request). The `databricks apps deploy` call blocks until deployment_id is returned;
   `apps get -o json` confirms `compute.state = ACTIVE`.
4. Open in browser: `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/wiki/`
5. Verify all 5 new entries appear in the wiki index.
6. Click into each — check rendering, footnote links, cross-link `[[claude-code]]`
   resolves to the existing entity, See also section is intact.
7. Click `[[copilot-studio]]` from the (re-baked) claude-code.html and `[[mcp-in-copilot-studio]]`
   from the (re-baked) anthropic.html — verify cross-link patches landed.

## Risk register

| Risk | Mitigation |
|------|-----------|
| `wiki_entity.html` template assumes legacy `sources: [article:hex]` flat list and breaks on dict-shape | Phase 1 step 3 catches this in local browser before deploy; fix template separately before deploying |
| `_convert_wiki_citations` doesn't handle `[^N]` GFM form | Same — Phase 1 catches it; fix converter separately |
| SSG bake refreshes `kb/output/wiki/` but doesn't track index → orphaned old HTML files | `_render_wiki_pages` writes only the slugs it finds in `kb/wiki/entities/`; old HTML for deleted slugs would persist. Not a concern this round (no deletions). |
| Pass 0d `sed` rebrand accidentally rewrites new entity content (unlikely — it targets HTML, not body claims, and uses specific brand strings) | Inspect `_ssg/wiki/copilot-studio.html` after bake: if it says "EDC Agentic AI Knowledge Base" instead of "Microsoft Copilot Studio" anywhere, the sed pattern over-matched. Audit pattern set in deploy.sh L46-58. |
| Deploy succeeds but synthesize wiki context injection lints stale | Acceptable — synthesize degrades gracefully (no wiki context, falls back to LightRAG only). Investigate as a separate issue if it triggers. |

## Decision pending from user

1. **Push?** Local 7 commits, `main...origin/main [ahead 7]`. Push needs explicit GO.
2. **Bake locally first?** Whether to run SSG bake locally (Phase 1) before deploying,
   or to trust the deploy pipeline to bake. Strongly recommend Phase 1 — visual
   verification catches template/converter mismatches that lint cannot.
3. **Repo where `kb/output/` is tracked or ignored?** Phase 1 step 1 answers this; user
   may have prior context. If tracked, bake commit becomes part of the deploy diff.

---

## Open questions raised during this plan write-up (parked for follow-up)

- Does the SSG bake currently run `_render_wiki_pages` against ALL `.md` (including
  files like `_suggestions/`) or only `entities/`? Lint contract suggests `_suggestions/`
  is gated by W3 first, but bake might pre-stage. Verify.
- Is there a way to tell the deploy whether to wipe-and-rebuild OR incremental-bake
  `kb/output/`? Important for fast iteration when only one entity changes.
- Pratiyush/llmwiki has `llmwiki build --strict` for CI. Does OmniGraph's bake have an
  analogous strict mode? If not, worth proposing as a separate quick — strict mode
  would catch SSG-template/converter mismatches in CI before they hit Databricks.
