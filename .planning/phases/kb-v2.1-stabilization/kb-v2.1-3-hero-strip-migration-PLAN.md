---
phase: kb-v2.1-3-hero-strip-migration
requirements: [REQ-4 residual]
priority: P2
skills_required: [frontend-design, writing-tests]
wave: 2
depends_on: [hero-strip HTML extracted from Aliyun]
estimated_loc: 50-100
estimated_time: 0.5d
---

# Phase kb-v2.1-3 — Hero Image Strip Migration

## Goal

Move the homepage hero-image-strip from a deploy-artifact-only state into the
template source. After this phase, `kb/templates/index.html` contains the strip;
SSG re-export emits it; production survives `git pull` + re-export without
losing the strip.

## Why

Aliyun production observation 2026-05-15:
- Hero-strip exists in `/var/www/kb/index.html` (deploy artifact) AND
  `kb/output/index.html` (build output)
- NOT in `kb/templates/index.html` source
- Next full SSG re-export → strip wiped → user experience degrades

Upstream-hotfix quick (260515-xxx) explicitly DEFERRED this migration to v2.1
because:
1. Migration needs the hero-strip HTML extracted from Aliyun first
2. Should be Jinja2-templatized + KB_BASE_PATH-respecting, not raw paste
3. Belongs in template work, not the urgent ops-drift quick

## Pre-execution requirement

**The hero-strip HTML snippet MUST be extracted from Aliyun before this phase
starts.** Source: `/var/www/kb/index.html`. Provide via:

```bash
# On Aliyun:
sed -n '/hero-image-strip/,/<\/section>/p' /var/www/kb/index.html
```

Paste the snippet into the executor's input (or save it to
`.planning/phases/kb-v2.1-stabilization/HERO-STRIP-SOURCE.md` for context).

If the snippet is unavailable (Aliyun changed, file lost, etc.), this phase
becomes "design + implement a hero-strip from spec" — bigger scope. Document
that path separately and don't proceed without explicit user OK.

## Files affected

| File | Action |
|---|---|
| `kb/templates/index.html` | MODIFY — insert hero-strip section between hero `<header>` and "Latest Articles" `<section>` |
| `kb/locale/zh-CN.json` + `kb/locale/en.json` | MODIFY — add hero-strip locale keys (e.g., section heading, image alt text) if needed |
| `kb/static/style.css` | VERIFY — reuse existing kb-1/kb-2/kb-3 chip + grid classes; **ZERO new `:root` vars** |
| `tests/integration/kb/test_homepage_hero_strip.py` | NEW — assert strip section emits correctly under both `KB_BASE_PATH=""` and `KB_BASE_PATH="/kb"` |
| `kb/templates/_partials/hero_strip.html` | OPTIONAL NEW — extract as partial if reusable; otherwise inline in `index.html` |

## Read first

1. `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md` — homepage layout token baseline
2. `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md` — homepage section composition
3. `kb/templates/index.html` — current state (target for migration)
4. `kb/templates/article.html` — image emission patterns to mirror
5. `kb/static/style.css` — existing image / chip / grid utility classes
6. The hero-strip snippet from Aliyun (REQUIRED INPUT)

## Action

### Task 1 — Snippet analysis + Jinja2-ization

Invoke `Skill(skill="frontend-design", args="Convert raw HTML hero-strip snippet (provided as input) into Jinja2-templatized form for kb/templates/index.html. Image URLs use {{ base_path }}/static/img/{hash}/{file}. Reuse kb-1 + kb-2 + kb-3 token classes verbatim — ZERO new :root vars. Position semantically between hero and 'Latest Articles' section. Output: revised index.html block + locale keys if needed.")`.

Specifically:
- Replace any hardcoded `/kb/static/img/...` paths with `{{ base_path }}/static/img/...`
- Replace hardcoded text with `{{ "key" | t(lang) }}` Jinja2 i18n calls if section has user-visible labels
- Preserve image hash references (image filenames stay literal)
- Wrap in `<section class="hero-strip">` (or whatever class the original used) — reuse existing CSS class names

### Task 2 — Add locale keys (if needed)

Likely keys (depending on snippet content):

```json
{
  "homepage.hero_strip.heading": "<text>",
  "homepage.hero_strip.alt_image_N": "<alt text>"
}
```

Add to BOTH `zh-CN.json` and `en.json`. If snippet has no user-visible text (just images), skip this task.

### Task 3 — Tests

Invoke `Skill(skill="writing-tests", args="Testing Trophy. Render kb/templates/index.html via export driver with KB_BASE_PATH='' and KB_BASE_PATH='/kb'. Parse output. Assert hero-strip section present. Assert image src attributes contain correct prefix. Browser smoke via Playwright: homepage shows ≥N images visible (naturalWidth>0).")`.

`tests/integration/kb/test_homepage_hero_strip.py`:
- `test_hero_strip_present_in_rendered_index_html`
- `test_hero_strip_image_paths_use_kb_base_path_when_set`
- `test_hero_strip_image_paths_bare_when_kb_base_path_unset`
- `test_hero_strip_locale_keys_render_correctly_zh_and_en` (if locale keys added)

### Task 4 — Local UAT (Rule 3 mandatory)

```bash
# 1. Default deploy
unset KB_BASE_PATH
KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py
grep -c "hero-image-strip\|hero-strip" kb/output/index.html
# expect: ≥ 1

# 2. Subdir deploy
KB_BASE_PATH=/kb KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py
grep -c "/kb/static/img/" kb/output/index.html
# expect: ≥ N (N = number of images in strip)

# 3. Browser smoke
venv/Scripts/python.exe .scratch/local_serve.py &
mcp__playwright__browser_navigate http://127.0.0.1:8766/
mcp__playwright__browser_evaluate '() => document.querySelectorAll(".hero-strip img, .hero-image-strip img").length'
# expect: ≥ N

mcp__playwright__browser_take_screenshot kb-v2.1-3-hero-strip-desktop.png
mcp__playwright__browser_resize 375 667
mcp__playwright__browser_take_screenshot kb-v2.1-3-hero-strip-mobile.png
```

Capture screenshots in `.playwright-mcp/`.

## Acceptance criteria

- [ ] `kb/templates/index.html` contains hero-strip section (`grep "hero-image-strip\|hero-strip" kb/templates/index.html` returns matches)
- [ ] Image refs use `{{ base_path }}/static/img/...` (no hardcoded `/kb/static/img/...` literals in template)
- [ ] SSG re-export with `KB_BASE_PATH=/kb`: hero-strip in output with `/kb/static/img/...` paths
- [ ] SSG re-export without `KB_BASE_PATH`: hero-strip in output with bare `/static/img/...` paths
- [ ] No new `:root` vars in `kb/static/style.css` (count == kb-1 baseline 31)
- [ ] CSS LOC ≤ 2200
- [ ] Locale keys present in both `zh-CN.json` and `en.json` (if any text labels)
- [ ] Test file `tests/integration/kb/test_homepage_hero_strip.py` exists with ≥4 tests, all PASS
- [ ] Playwright homepage screenshots at desktop + mobile
- [ ] No regression in full pytest

## Skill discipline

SUMMARY.md MUST contain:
- `Skill(skill="frontend-design"`
- `Skill(skill="writing-tests"`

## Anti-patterns

- ❌ DO NOT introduce new `:root` vars in style.css
- ❌ DO NOT hardcode `/kb/...` paths — always `{{ base_path }}/...`
- ❌ DO NOT skip locale keys for user-visible text
- ❌ DO NOT create new chip / card / grid classes — reuse existing
- ❌ DO NOT use `git add -A`
- ❌ DO NOT migrate without the actual Aliyun snippet (would be a different scope — design from spec)

## Return signal

```
## kb-v2.1-3 HERO STRIP MIGRATION COMPLETE
- kb/templates/index.html now contains hero-strip section
- {{ base_path }}/static/img/ pattern used; ZERO hardcoded paths
- Locale keys added (if applicable): N keys in zh-CN + N in en
- :root var count: 31 (preserved); CSS LOC ≤ 2200
- Tests: <X>/<X> PASS
- Local UAT: hero-strip visible at desktop + mobile screenshots in .playwright-mcp/
- Skill regex: frontend-design / writing-tests in SUMMARY
- No regression in full pytest
```
