---
phase: kb-v2.1-2-image-path-integration
requirements: [REQ-1]
priority: P1
skills_required: [python-patterns, writing-tests]
wave: 2
depends_on: []
estimated_loc: 80-150
estimated_time: 0.5-1d
---

# Phase kb-v2.1-2 — KB Downloaded Images Full Integration

## Goal

Static article pages AND `/api/article/{hash}` API responses must reference
downloaded images via `{KB_BASE_PATH}/static/img/{hash}/{file}` (e.g.,
`/kb/static/img/...` under subdir deploy, `/static/img/...` under root deploy).
Browser-side: images render with `naturalWidth > 0`, not HTML fallback, not
404.

## Why

Aliyun production observation 2026-05-14:
- Article body markdown still contains `/static/img/...` (bare prefix) in some
  paths — falls through Caddy `/kb/*` matcher → catch-all returns SPA HTML
- `naturalWidth=0` for content images on multiple test articles
- `/api/article/{hash}` API response inconsistent: sometimes returns body with
  image refs that render in browser (after Caddy strip), sometimes not

Root cause: image path rewriting in `get_article_body()` (D-14 fallback) doesn't
respect `KB_BASE_PATH` env var. Was added as part of kb-1 EXPORT-05 (rewriting
`http://localhost:8765/` → `/static/img/`) but predates KB_BASE_PATH (added by
d3p quick).

## Files affected

| File | Action |
|---|---|
| `kb/data/article_query.py` | MODIFY — `get_article_body()` image rewrite respects `KB_BASE_PATH` |
| `kb/api.py` | MODIFY — `/api/article/{hash}` response includes `images` field with full paths; `body_md`/`body_html` also use prefixed paths |
| `kb/export_knowledge_base.py` | VERIFY — already-rendered article HTML uses `{{ base_path }}/static/img/...`; if not, fix the rewrite |
| `kb/templates/article.html` | VERIFY — image references use `{{ base_path }}` |
| `tests/integration/kb/test_image_paths.py` | NEW — fixture article with body containing image refs; test rewrite under `KB_BASE_PATH=/kb` and `KB_BASE_PATH=""` |
| `tests/integration/kb/test_api_article_detail.py` | EXTEND — assert `images` field present + `body_md` contains correctly-prefixed paths |

## Read first

1. `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3 (local UAT)
2. `kb/data/article_query.py` — `get_article_body()` D-14 fallback chain + image rewrite (kb-1 EXPORT-05)
3. `kb/api.py` — `/api/article/{hash}` route handler
4. `kb/export_knowledge_base.py` — article rendering pipeline + body rewrite hooks
5. `kb/templates/article.html` — image emission
6. `kb/config.py` — `KB_BASE_PATH` env var (added by d3p)
7. `.planning/quick/260514-d3p-*/SUMMARY.md` — context on KB_BASE_PATH introduction

## Action

### Task 1 — Audit image rewrite call sites

```bash
grep -rnE "localhost:8765|/static/img|http://localhost" kb/ tests/
```

Map every call site. Expected:
- `kb/data/article_query.py` `get_article_body()` — D-14 fallback + EXPORT-05 rewrite
- `kb/templates/article.html` — image emission (Jinja2)
- `kb/api.py` — JSON response shape

### Task 2 — Fix `get_article_body()` rewrite

Invoke `Skill(skill="python-patterns", args="Refactor get_article_body() image rewrite to respect KB_BASE_PATH. Pure function. No new dependencies. Must remain idempotent — calling rewrite on already-prefixed path is no-op. Image rewrite is currently a re.sub on body_md before HTML render; preserve this pattern.")`.

Implementation:

```python
def _rewrite_image_paths(body_md: str, base_path: str = "") -> str:
    """Rewrite localhost:8765 / static/img refs to KB_BASE_PATH-aware paths.

    EXPORT-05 contract: localhost:8765/{hash}/{file} → {base_path}/static/img/{hash}/{file}
    Idempotent: already-prefixed paths pass through unchanged.
    """
    if not body_md:
        return body_md
    # localhost:8765 path → /static/img path
    rewritten = re.sub(
        r"http://localhost:8765/([^)\s]+)",
        f"{base_path}/static/img/\\1",
        body_md,
    )
    # bare /static/img/ → {base_path}/static/img/ (only when base_path non-empty
    # AND the path isn't already prefixed)
    if base_path:
        rewritten = re.sub(
            r"(?<!{base})\/static\/img\/".replace("{base}", re.escape(base_path)),
            f"{base_path}/static/img/",
            rewritten,
        )
    return rewritten
```

Then `get_article_body()` calls this with `base_path=config.KB_BASE_PATH`.

### Task 3 — `/api/article/{hash}` response shape

Verify response includes:

```json
{
  "id": ...,
  "source": "wechat" | "rss",
  "title": "...",
  "url": "...",
  "lang": "zh-CN" | "en",
  "body_md": "...",       // KB_BASE_PATH-prefixed image refs
  "body_html": "...",     // same; HTML render after rewrite
  "body_source": "vision_enriched" | "raw_markdown",
  "images": ["/kb/static/img/abc/0.jpg", "/kb/static/img/abc/1.jpg", ...]
}
```

Image extraction: post-rewrite, `re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body_md)` finds markdown image URLs; OR HTML `<img src=...>` if body_html.

### Task 4 — Tests

Invoke `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real fixture article with body containing 3+ localhost:8765 image refs. Parametrize across KB_BASE_PATH='' (root deploy) and KB_BASE_PATH='/kb' (subdir). Assert body_md contains correctly-prefixed paths. Assert images field has expected count + format. Smoke against .dev-runtime live data: /api/article/{known-hash} for an article with N images returns body+images with /kb/static/img/ paths.")`.

`tests/integration/kb/test_image_paths.py`:
- `test_rewrite_localhost_8765_to_kb_static_img_with_base_path`
- `test_rewrite_localhost_8765_to_static_img_without_base_path`
- `test_rewrite_idempotent_when_paths_already_prefixed`
- `test_get_article_body_returns_rewritten_body_md`
- `test_export_driver_emits_prefixed_paths_when_kb_base_path_set`

`tests/integration/kb/test_api_article_detail.py` (extend):
- `test_api_article_detail_response_includes_images_field`
- `test_api_article_detail_body_md_paths_match_kb_base_path`

### Task 5 — Local UAT (Rule 3 mandatory)

Pick a known article with multiple images (vitaclaw-site agent flagged
`5a362bf61e` — verify it exists in `.dev-runtime/data/kol_scan.db`):

```bash
# 1. Default deploy (no base_path)
unset KB_BASE_PATH
venv/Scripts/python.exe .scratch/local_serve.py &
curl -sS http://127.0.0.1:8766/api/article/5a362bf61e | python -m json.tool | grep -E '"images"|/static/img/'
# expect: image refs with /static/img/...

# 2. Subdir deploy (base_path=/kb)
KB_BASE_PATH=/kb venv/Scripts/python.exe .scratch/local_serve.py &
curl -sS http://127.0.0.1:8766/api/article/5a362bf61e | python -m json.tool | grep -E '/kb/static/img/'
# expect: image refs with /kb/static/img/...

# 3. Browser smoke — Playwright
mcp__playwright__browser_navigate http://127.0.0.1:8766/articles/5a362bf61e.html
mcp__playwright__browser_evaluate '() => Array.from(document.querySelectorAll(".article-body img")).filter(i => i.naturalWidth > 0).length'
# expect: ≥ 1
```

Capture screenshots: `.playwright-mcp/kb-v2.1-2-images-{step}.png`.

## Acceptance criteria

- [ ] `grep -rE "localhost:8765" kb/` shows only the rewrite source pattern, not consumers
- [ ] `_rewrite_image_paths()` is pure function with idempotency test
- [ ] `KB_BASE_PATH=/kb` SSG re-export: zero `/static/img/` bare refs in `kb/output/articles/*.html` (`grep -lE 'src="/static/img/' kb/output/articles/ | wc -l` → 0)
- [ ] `KB_BASE_PATH=/kb` SSG re-export: ≥ N `/kb/static/img/` refs in articles with images (`grep -clE '/kb/static/img/' kb/output/articles/ | wc -l` → > 0)
- [ ] `/api/article/{hash}` returns `images` field with at least 1 entry for image-bearing article
- [ ] Browser test on `5a362bf61e` (or equivalent): ≥ 1 image with `naturalWidth > 0`
- [ ] No regression in full pytest run

## Skill discipline

SUMMARY.md MUST contain:
- `Skill(skill="python-patterns"`
- `Skill(skill="writing-tests"`

## Anti-patterns

- ❌ DO NOT change `kb/templates/article.html` if Jinja2 already does `{{ base_path }}/static/img/` — only fix the BODY rewrite (which goes through markdown → HTML, separate from template)
- ❌ DO NOT use `/static/img/` bare in any new code — always go through `_rewrite_image_paths` with `base_path` param
- ❌ DO NOT touch image filesystem layout — paths are url-side concern, files stay at `~/.hermes/omonigraph-vault/images/{hash}/{file}`
- ❌ DO NOT use `git add -A`

## Return signal

```
## kb-v2.1-2 IMAGE PATH INTEGRATION COMPLETE
- _rewrite_image_paths refactored, idempotent, pure
- /api/article/{hash} returns images field
- KB_BASE_PATH=/kb: 0 bare /static/img/ refs in output
- Local UAT: ≥N images naturalWidth > 0 on test article
- Tests: <X>/<X> PASS (added <Y> regression tests)
- Skill regex: python-patterns / writing-tests in SUMMARY
- No regression in full pytest
```
