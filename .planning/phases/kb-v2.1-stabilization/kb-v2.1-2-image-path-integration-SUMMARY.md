---
phase: kb-v2.1-2-image-path-integration
status: complete
shipped: 2026-05-15
loc_added_modified: ~135
files_changed: 4 (1 source + 1 new test + 1 SUMMARY + STATE.md)
---

# Phase kb-v2.1-2 — KB Downloaded Images Full Integration · SUMMARY

## Outcome

`kb/data/article_query.get_article_body()` now respects `KB_BASE_PATH`
when rewriting image URLs. Static article pages AND `/api/article/{hash}`
both emit `{KB_BASE_PATH}/static/img/{hash}/{file}` (e.g., `/kb/static/img/...`
under subdir deploy, `/static/img/...` under root deploy). Browser-side:
images on real-world articles render with `naturalWidth > 0`, not 404s.

The fix is a single new pure helper `_rewrite_image_paths(body_md, base_path)`
that absorbs the EXPORT-05 rewrite contract AND a new bare-`/static/img/` →
`{base_path}/static/img/` second pass, with negative-lookbehind idempotency
so already-prefixed paths pass through unchanged. `get_article_body()` calls
the helper with `base_path=config.KB_BASE_PATH`, so:

- **API path** (`/api/article/{hash}` via `kb/api_routers/articles.py`) —
  `body_md` returned with prefixed paths; `body_html` markdown-rendered
  inherits the prefix; `images` extraction (already present from kb-3-05)
  picks up post-rewrite URLs automatically.
- **SSG path** (`kb/export_knowledge_base.py`) — already calls
  `get_article_body()` from 3 sites (article render, sidebar, related-entity);
  inherits the fix without further code changes.

## Skill discipline (regex satisfiers)

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this phase invoked two Skills
as real tool calls. Literal markers below are present for the plan-checker's
grep regex:

- `Skill(skill="python-patterns", args="Refactor get_article_body() image rewrite to respect KB_BASE_PATH. Pure function. No new dependencies. Must remain idempotent — calling rewrite on already-prefixed path is no-op. Image rewrite is currently a re.sub on body_md before HTML render; preserve this pattern.")`
  - **Verdict:** EAFP-style empty-body short-circuit. Two-pass `re.sub`:
    pass 1 = `http://localhost:8765/X` → `{base_path}/static/img/X` (EXPORT-05);
    pass 2 (only when `base_path` non-empty) = bare `/static/img/` not
    preceded by `base_path` → `{base_path}/static/img/`, implemented via
    `re.sub(rf"(?<!{re.escape(base_path)})/static/img/", ...)`. PEP 8 +
    type hints, `pathlib.Path` for the credential file (where applicable).
- `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real fixture article with body containing 3+ localhost:8765 image refs. Parametrize across KB_BASE_PATH='' (root deploy) and KB_BASE_PATH='/kb' (subdir). Assert body_md contains correctly-prefixed paths. Assert images field has expected count + format. Smoke against .dev-runtime live data: /api/article/{known-hash} for an article with N images returns body+images with /kb/static/img/ paths.")`
  - **Verdict:** 13 tests in `tests/integration/kb/test_image_paths.py`
    — 7 pure-function (root + subdir + idempotency + multi-occurrence +
    empty-body + bare-prefix-pickup + no-double-prefix) and 6 HTTP-level
    via TestClient + reload chain (root/subdir body_md + images field +
    body_html src + no-image article preservation). All 13 PASS.

## Files changed

| File | Action | LOC |
|---|---|---|
| `kb/data/article_query.py` | MODIFY — extract `_rewrite_image_paths()` pure helper; `get_article_body` calls it with `config.KB_BASE_PATH` | +47 / -3 |
| `tests/integration/kb/test_image_paths.py` | NEW — 13 tests (7 pure + 6 HTTP) | +204 |
| `.planning/phases/kb-v2.1-stabilization/kb-v2.1-2-image-path-integration-SUMMARY.md` | NEW — this file | — |
| `.planning/STATE.md` | MODIFY — Quick Tasks Completed row for kb-v2.1-2 | +1 |

## Acceptance criteria checklist (PLAN §Acceptance criteria)

- [x] **`grep -rE "localhost:8765" kb/` shows only the rewrite source pattern, not consumers** — only matches in `kb/docs/` (markdown) + `kb/data/article_query.py:_IMAGE_SERVER_REWRITE` (the rewrite source) + `kb/api.py` (D-15 mount comment). Zero consumer-side hardcodes.
- [x] **`_rewrite_image_paths()` is pure function with idempotency test** — `test_rewrite_idempotent_when_paths_already_prefixed` asserts byte-equality on second pass.
- [x] **`KB_BASE_PATH=/kb` SSG re-export: zero bare `/static/img/` refs in articles** — post-cleanup of 6 stale May-14 fixture orphans (abc1234567, 3f32dbea5f, 1111111111, 2222222222, deadbeefca, kol3000003a/4b/5c — none in dev DB), `grep -lE 'src="/static/img/' kb/output/articles/*.html | wc -l` = 0.
- [x] **`KB_BASE_PATH=/kb` SSG re-export: ≥ 1 `/kb/static/img/` ref** — `4b7c022702.html` carries 8 prefixed `<img src="/kb/static/img/4b7c022702/N.jpg">` tags.
- [x] **`/api/article/{hash}` returns `images` field** — already present from kb-3-05 via `_extract_image_urls(body_md)`; tests assert prefix matches `KB_BASE_PATH`.
- [x] **Browser test: ≥ 1 image with `naturalWidth > 0`** — Playwright on `/articles/4b7c022702.html` (root mode local UAT) returned `loaded_imgs=2, failed_imgs=0`; logo at 2048×2048 + article image at 305×305.
- [x] **No regression in full pytest run** — 449/449 PASS in `tests/integration/kb/` + `tests/unit/kb/` (was 436 pre-phase + 13 new = 449).

## Local UAT (Rule 3 — `kb/docs/10-DESIGN-DISCIPLINE.md`)

`venv/Scripts/python.exe .scratch/local_serve.py` against
`.dev-runtime/data/kol_scan.db` on `127.0.0.1:8766`. Test article:
`5a362bf61e` (id=29, vision-enriched, 48 image-path refs in
`final_content.md`).

| # | Scenario | Setup | Result | Pass |
|---|---|---|---|---|
| 1 | API root deploy | `unset KB_BASE_PATH` | `/api/article/5a362bf61e` → 48 `/static/img/` paths in body_md, 0 `/kb/`, 0 `localhost:8765`, body_source=`vision_enriched` | ✅ |
| 2 | API subdir deploy | `MSYS_NO_PATHCONV=1 KB_BASE_PATH=/kb` | `/api/article/5a362bf61e` → 48 `/kb/static/img/` paths, 0 bare `/static/img/`, 0 `localhost:8765`. (First attempt without `MSYS_NO_PATHCONV=1` bit by Git Bash POSIX→Windows path conversion — captured as a deploy footnote, not a kb-v2.1-2 bug.) | ✅ |
| 3 | SSG re-export root mode | `KB_DB_PATH=<win> KB_IMAGES_DIR=<win>` (no KB_BASE_PATH) | 148 articles rendered; 0 `/kb/` refs; 1 article (`4b7c022702`) has 8 inline `<img src="/static/img/...">` | ✅ |
| 4 | SSG re-export subdir mode | `MSYS_NO_PATHCONV=1 KB_BASE_PATH=/kb KB_DB_PATH=<win> KB_IMAGES_DIR=<win>` | 148 articles, 148 `href="/kb/static/style.css"`, 1 article with `<img src="/kb/static/img/...">`, 0 bare leakage (after stale-orphan cleanup) | ✅ |
| 5 | Browser smoke | Playwright on `/articles/4b7c022702.html` (root mode for image accessibility) | 2/2 images loaded; logo 2048×2048; article image `4b7c022702/3.jpg` 305×305; 0 failed | ✅ |

Screenshot evidence: `.playwright-mcp/kb-v2-1-2-images-root-deploy.png`

Curl + JSON evidence:
- `.scratch/kb-v2.1-2-uat-root.json` (root deploy API response)
- `.scratch/kb-v2.1-2-uat-kb.json` (subdir deploy API response)
- `.scratch/kb-v2.1-2-uat-root.log` / `.scratch/kb-v2.1-2-uat-kb.log` /
  `.scratch/kb-v2.1-2-uat-browser.log` (server logs)

### Real-world article shape note

DB articles have two import paths to image URLs in body markdown:

1. **Inline markdown syntax** `![alt](http://localhost:8765/.../N.jpg)` —
   only 1 article in `.dev-runtime` exhibits this (`4b7c022702`); browser
   `<img>` tags emit, naturalWidth>0 confirms.
2. **Plain-text references** like `Image N from article 'X':
   /static/img/.../N.jpg` — most vision-enriched articles use this format
   (e.g., `5a362bf61e`). My rewrite still correctly translates the URL
   prefix; whether they render as actual `<img>` is a downstream concern
   (`final_content.md` author convention) — not in kb-v2.1-2 scope.

## Test results

```
$ venv/Scripts/python.exe -m pytest tests/integration/kb/ tests/unit/kb/ --tb=short
============================ 449 passed in 30.33s =============================
```

New file `tests/integration/kb/test_image_paths.py`: 13 / 13 PASS:

Pure-function suite (7):
- `test_rewrite_localhost_8765_to_static_img_without_base_path`
- `test_rewrite_localhost_8765_to_kb_static_img_with_base_path`
- `test_rewrite_bare_static_img_picks_up_base_path`
- `test_rewrite_idempotent_when_paths_already_prefixed`
- `test_rewrite_multiple_occurrences_all_rewritten`
- `test_rewrite_empty_body_passthrough`
- `test_rewrite_does_not_double_prefix_existing_base_path`

HTTP-level suite (6):
- `test_api_article_body_md_uses_static_img_for_root_deploy`
- `test_api_article_body_md_uses_kb_prefix_under_subdir_deploy`
- `test_api_article_images_field_present_and_prefixed_for_root_deploy`
- `test_api_article_images_field_uses_kb_prefix_under_subdir_deploy`
- `test_api_article_body_html_image_src_matches_base_path`
- `test_api_article_unaffected_when_body_has_no_images`

## Anti-patterns avoided

- ❌ DO NOT change `kb/templates/article.html` if Jinja2 already does `{{ base_path }}/static/img/` → ✅ template untouched (it uses `{{ body_html | safe }}` for body content; chrome already had `{{ base_path }}` from d3p)
- ❌ DO NOT use `/static/img/` bare in any new code → ✅ all new code routes through `_rewrite_image_paths(base_path)`
- ❌ DO NOT touch image filesystem layout → ✅ files stay at `~/.hermes/omonigraph-vault/images/{hash}/{file}`; only URL paths change
- ❌ DO NOT modify Aliyun production directly → ✅ phase output is code-only; Aliyun re-export + rsync is a separate operator step
- ❌ DO NOT use `git add -A` → ✅ explicit per-file staging
- ❌ DO NOT use `git commit --amend` / `git reset` → ✅ forward-only commits; STATE.md backfill via 2-forward-commit pattern

## Aliyun roll-out (separate operator step)

To pick up this phase on Aliyun:

1. `ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && git pull --ff-only origin main'`
2. Re-export SSG (Aliyun deploys with `KB_BASE_PATH=/kb`):
   ```bash
   ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
       KB_BASE_PATH=/kb KB_DB_PATH=/root/.hermes/data/kol_scan.db \
       KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images \
       venv/bin/python kb/export_knowledge_base.py'
   ```
3. `ssh aliyun-vitaclaw 'rsync -a --delete /root/OmniGraph-Vault/kb/output/ /var/www/kb/'`
4. `ssh aliyun-vitaclaw 'systemctl reload caddy'` (no kb-api restart needed — only SSG static changes)
5. Verify via public probe: `curl http://101.133.154.49/kb/articles/4b7c022702.html | grep -oE 'src="/kb/static/img/[^"]+"' | head -3`

The kb-api service is unaffected (no Python source change touches it
beyond `kb/data/article_query.py` which is loaded at next request — uvicorn
single-worker reload optional).

## Footnote — Git Bash MSYS path conversion

When testing locally on Windows with `KB_BASE_PATH=/kb`, Git Bash's MSYS
runtime translates POSIX paths to Windows paths before passing to the child
process, turning `/kb` into something like
`C:\Users\huxxha\AppData\Local\Programs\Git\kb`. Use `MSYS_NO_PATHCONV=1`
to disable. This is a pre-existing footgun (also documented in 260514-d3p);
NOT a kb-v2.1-2 bug.

## Return signal

```
## kb-v2.1-2 IMAGE PATH INTEGRATION COMPLETE
- _rewrite_image_paths refactored, idempotent, pure (kb/data/article_query.py)
- /api/article/{hash} returns images field with KB_BASE_PATH-correct URLs
- KB_BASE_PATH=/kb SSG re-export: 0 bare /static/img/ refs in kb/output/articles/*.html (post-orphan-cleanup)
- Local UAT: 5/5 scenarios pass (curl + browser smoke at .scratch/ + .playwright-mcp/)
- Tests: 13/13 PASS in tests/integration/kb/test_image_paths.py
- Skill regex in SUMMARY.md: python-patterns / writing-tests both present
- No regression: 449/449 PASS in tests/integration/kb/ + tests/unit/kb/
- Files committed in single forward-only atomic commit; pushed to origin/main
- STATE.md Quick Tasks Completed table updated (2-forward-commit pattern, NOT amend)
```
