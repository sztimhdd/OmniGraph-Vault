---
phase: kb-v2.2-7-bilingual-by-site-language
priority: P1
skills_required: [ui-ux-pro-max, frontend-design, python-patterns, writing-tests]
wave: 7
depends_on: [kb-v2.2-2]
estimated_loc: 350-500 (mostly deletions + mechanical template extension)
estimated_time: 1-1.5d
authored_by: orchestrator from 2026-05-19 user UX-review session against shipped kb-v2.2-2 button-based on-demand UX
partially_supersedes: kb-v2.2-2 (data layer from migration 006 is preserved and extended; only on-demand UX/API surface is removed)
deployment_dual: aliyun (zh-CN audience, KB_DEFAULT_LANG=zh-CN) + databricks (en audience, KB_DEFAULT_LANG=en) — same code, different env var
---

# Phase kb-v2.2-7 — Bilingual by Site Language (data-driven, no on-demand UX)

## Goal

Replace kb-v2.2-2's **button-based on-demand translation UX** with a
**site-language-driven static rendering model**:

- Site language (cookie + browser detection) IS reading language
- English mode → English title in lists + English body in article detail
  (all pre-translated server-side, embedded in single SSG output)
- No translate button, no `/api/translate` endpoint, no client-side polling
- Untranslated articles fall back to original Chinese — mixed-language EN site
  is acceptable per locked user requirement

Translation production runs on **Databricks** as a one-shot manual notebook
using company budget — no automation, no scheduling, no SCP scripts. Hermes
DB is pulled, rows translated, DB pushed back.

This phase **partially reverts kb-v2.2-2**: keeps the four `articles` translation
columns from migration 006, extends them to `rss_articles` (migration 007),
and rips out the entire on-demand translation API + service + UI surface.

## Why this phase exists (motivation, supersedes kb-v2.2-2 UX)

User ran a UX review of kb-v2.2-2 (shipped 2026-05-18) and found the
button-based on-demand model fundamentally misaligned with their mental
model of a bilingual KB:

- **kb-v2.2-2 model:** content language is per-article-fixed; user clicks
  "Read in English" to translate-on-demand; 30s polling; DOM swap
- **User mental model:** site language IS reading language; switching the
  site flips title + body simultaneously across the whole catalog; no
  per-article action; works offline-of-translation-service

The data layer from kb-v2.2-2 (migration 006: `body_translated`,
`title_translated`, `translated_lang`, `translated_at` on `articles`) is
correctly shaped for this new model — we just need to drive rendering off
it instead of putting it behind an on-demand API. Hence partial revert
(UX/API surface only) instead of full re-do.

Cross-references:

- 2026-05-19 user audit transcript locked all decisions A1-A9 below (A9 added in self-patch round after dual-deployment Aliyun/Databricks constraint surfaced)
- `feedback_kb_local_uat_mandatory.md` — UAT discipline mandatory per CLAUDE.md PRINCIPLE #6
- `feedback_skill_invocation_not_reference.md` — Skills declared inline are not
  enough; planner must emit `Skill(...)` directives in Wave bodies
- `feedback_parallel_track_gates_manual_run.md` — gsd-tools.cjs init does NOT
  parse parallel-track suffix files; this PLAN was hand-driven without init/new-phase

## Pre-locked decisions (NOT to re-litigate)

These were locked by user in the 2026-05-19 UX review session. Bake into
plan body, do not re-debate during execute. If any proves genuinely
unworkable, STOP + escalate to orchestrator with concrete alternative —
do NOT silently override.

| # | Decision | Locked value |
|---|---|---|
| A1 | Language axes | ONE axis only: site language (cookie + browser detection). `<html lang>` follows site language uniformly. **Delete `data-fixed-lang="true"` guard.** No per-article fixed-content lang. |
| A2 | Translation runs where | **Databricks** using company budget. Manual trigger, single-file notebook, no bundle yaml, no scripts/ subdir, no scheduling automation. SCP inline (2 lines), not separate script. |
| A3 | SSG rendering shape | **Single output tree** with dual-block embedding. Article detail h1 + body each emit `<span data-lang="zh">` + `<span data-lang="en">` blocks. Existing `style.css:330+` `[data-lang]` rules drive visibility off `<html lang>`. **No `/en/articles/x.html` subdirectory.** |
| A4 | Untranslated fallback | `{{ article.title_translated or article.title }}`. Mixed-language display in EN site is acceptable per user req #2 (entities can be mixed Chinese/English). No "[Translation pending]" marker, no visual flag. |
| A5 | RSS scope | RSS articles ARE in v1 scope. migration 007 mirrors migration 006 onto `rss_articles`. |
| A6 | Display set = translation set | **DATA-07 tightens:** `body非空 AND layer1_verdict='candidate' AND layer2_verdict='ok'`. Currently `article_query.py:74,79,84` uses `IS NULL OR != 'reject'` (lenient). Tightening makes display set = translation candidate set, eliminating the "visible but never translated" class. **GATE:** pre-deploy SQL count of `L2 IS NULL` rows that will become invisible (Wave 6). |
| A7 | Toggle button | **KEEP** the `.lang-toggle` button in header — lets user override browser detection. Only the `data-fixed-lang` guard in `lang.js:74-76` is removed. `bindToggle()` (lang.js:81-93) is unchanged. |
| A8 | On-demand surface | **DELETE entirely:** `POST /api/translate/{hash}`, `GET /api/translate/{hash}`, `GET /api/article/{hash}` `?lang=` query param + `_load_translation()` helper, `kb/services/translation.py`, article.html translate-row + inline `<script>`. Verify each grep returns zero references after deletion. |
| A9 | Per-deployment default lang | **`KB_DEFAULT_LANG` env var** read at SSG time, injected as `window.KB_DEFAULT_LANG` in `base.html` before `lang.js`. `lang.js` reads `window.KB_DEFAULT_LANG` (validated against `SUPPORTED`) as fallback when cookie + browser detection both fail. **Aliyun deploy** sets `KB_DEFAULT_LANG=zh-CN` (or unset → defaults to zh-CN); **Databricks deploy** sets `KB_DEFAULT_LANG=en`. Same code, different env var. Per-deployment audience: aliyun=Chinese users, databricks=English users. |

## Hard "don'ts" — features the user explicitly killed in audit

The user audited prior versions of this plan and removed these. Do NOT
re-introduce during execute:

- ❌ Bundle yaml + scheduled translation job
- ❌ Separate SCP shell scripts in `scripts/` subdir
- ❌ `merge_translations.py` helper
- ❌ `translate_log.jsonl` quality gating / `len_ratio` automatic flagging
- ❌ DB-lock concurrent-safety SCP-via-`.backup` machinery (one inline snapshot line is enough)
- ❌ "Decouple DATA-07 from translation eligibility" refactor in soon-to-be-deleted code
- ❌ `[Translation pending]` placeholder / visual marker for untranslated articles
- ❌ Speculative `<html lang>` SEO meta beyond what already exists

User's stated criterion: **"Would a senior engineer say this is overcomplicated? If yes, simplify."** Apply aggressively.

## Files affected

| File | Action |
|---|---|
| `kb/data/migrations/007_rss_translation_columns.sql` | **NEW** — mirror migration 006 onto `rss_articles` (4 cols: `body_translated`, `title_translated`, `translated_lang`, `translated_at`) |
| `kb/data/article_query.py` | **UPDATE** — tighten DATA-07 to `layer2_verdict='ok'`; add `title_translated` + `translated_lang` to `ArticleRecord` + all SELECT clauses |
| `kb/api_routers/articles.py` | **UPDATE** — surface new fields in `_record_to_list_item` + `_record_to_dict`; **DELETE** `POST /api/translate/{hash}`, `GET /api/translate/{hash}`, `_load_translation()`, `?lang=` query param logic |
| `kb/services/translation.py` | **DELETE** entire file |
| `kb/templates/article.html` | **UPDATE** — remove `data-fixed-lang="true"`; replace single h1 + body with dual-`<span data-lang>` blocks; **DELETE** translate-row div + inline `<script>` translate handler |
| `kb/templates/articles_index.html` | **UPDATE** — card title dual-`<span data-lang>` |
| `kb/templates/base.html` | **UPDATE** (A9) — inject `<script>window.KB_DEFAULT_LANG = "{{ kb_default_lang \| default('zh-CN') }}";</script>` immediately before `lang.js` script tag |
| `kb/export_knowledge_base.py` | **UPDATE** — read `body_translated` for each article; render through markdown→HTML pipeline (same as `body_md` → `body_html`, including EXPORT-05 image rewrite) → `translated_body_html`; pass to template; card record dataclass adds `title_translated`; **(A9)** read `os.environ.get('KB_DEFAULT_LANG', 'zh-CN')`, validate against `{'zh-CN', 'en'}`, pass into base template context as `kb_default_lang` |
| `kb/static/lang.js` | **UPDATE** — `resolveLang()` writes cookie on first browser-detect; `applyLang()` removes `data-fixed-lang` guard; `bindToggle()` unchanged; **(A9)** `DEFAULT_LANG` initialised from `window.KB_DEFAULT_LANG` (validated against `SUPPORTED`, fallback `'zh-CN'`) |
| `databricks-deploy/app.yaml` (Databricks) + Aliyun systemd unit / kb-api env file | **CONFIG-ONLY** — set `KB_DEFAULT_LANG=en` on Databricks deploy; `KB_DEFAULT_LANG=zh-CN` (or unset) on Aliyun deploy. Out-of-band ops change, NOT code change in this phase — but documented here for executor awareness |
| `databricks-deploy/translate_kb.py` | **NEW** — single-file Databricks notebook (SCP pull + per-row translate + UPDATE + SCP push, manual "Run all" trigger only) |
| `tests/unit/kb/test_article_query.py` (or extend existing) | **UPDATE** — fixture rows include L2 verdicts; tightened filter excludes `L2 IS NULL`; new fields surface in records |
| `tests/integration/kb/test_export_knowledge_base*.py` | **UPDATE** — SSG output contains `data-lang="en"` blocks; zh-only rendering still works for `title_translated IS NULL` |
| `tests/unit/kb/test_lang_js.py` (or jsdom-style equivalent) | **NEW or UPDATE** — first-visit cookie persistence + `<html lang>` updates on toggle (article detail page, post-`data-fixed-lang` removal) |
| Existing `tests/integration/kb/test_synthesize_*` involving translation | **DELETE** test cases that hit `/api/translate` or `_load_translation` |
| `kb/docs/<CONTENT-QUALITY-DECISIONS doc>` | **UPDATE** if it documents the old looser DATA-07 rule |
| `.planning/STATE-KB-v2.md` | **UPDATE** — append new "last_activity" row for kb-v2.2-7 only |

**Out of scope** (do NOT touch):

- Migration 006 itself (kb-v2.2-2 shipped — leave the SQL file alone; we only EXTEND via 007)
- `lib/article_filter.py` verdict alphabet (verified `'ok'` / `'reject'` / NULL — unchanged)
- `kb/api_routers/synthesize.py` and `_QA_PROMPT` (kb-v2.2-4 territory — citations not translations)
- `kb/scripts/sync_lightrag_storage.py` (kb-v2.2-1 territory)
- LightRAG storage / KG search logic (kb-v2.2-3 territory)
- Caddy / systemd / nginx — pure data + SSG + frontend phase
- Any new design tokens / new components / new CSS rules — pure mechanical extension of existing `[data-lang]` pattern

## Read first (mandatory before authoring code)

1. `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-1-lightrag-storage-sync-PLAN.md` — phase format reference
2. `.planning/PROJECT-KB-v2.md` — milestone-level context
3. `.planning/STATE-KB-v2.md` — current sub-milestone position
4. `kb/data/migrations/006_*.sql` — exact column shapes to mirror in 007
5. `kb/data/article_query.py:31-85` — existing DATA-07 fragment + schema guard helper
6. `kb/templates/article.html` — current shape (lines 2, 72, 110-118, 199-265 are the targets)
7. `kb/static/lang.js` — current resolution flow (lines 61-79 are the targets)
8. `kb/api_routers/articles.py` — current `_record_to_list_item` / `_record_to_dict` + translation endpoints to delete
9. `kb/services/translation.py` — to be deleted; verify no other module imports it
10. `kb/static/style.css:330+` `[data-lang]` rules — already in place; do NOT modify
11. Memory entries (consult, do NOT inline secrets):
    - `feedback_skill_invocation_not_reference.md` — emit literal `Skill(...)` calls in Wave bodies
    - `feedback_parallel_track_gates_manual_run.md` — gsd-tools.cjs init bypassed
    - `feedback_contract_shape_change_full_audit.md` — when columns added, grep ALL fixture CREATE TABLE
    - `feedback_test_mirrors_impl.md` — test assertions pin behavior, not formula echoes
    - `feedback_no_amend_in_concurrent_quicks.md` — forward-only commits
    - `feedback_git_add_explicit_in_parallel_quicks.md` — explicit `git add <files>`
    - `feedback_kb_local_uat_mandatory.md` — Wave 6 UAT discipline
    - `aliyun_vitaclaw_ssh.md` — Aliyun deploy target context (deploy comes AFTER this phase via existing kb-api restart flow)

## Action — Wave breakdown

This phase ships in 6 sequenced waves. Each wave has a single concern and
a verifiable end-state. Waves 4 + 6 invoke design Skills; waves 1-3 + 5
do not need design review.

---

### Wave 1 — Data layer (`articles` + `rss_articles` parity)

**Concern:** Schema + query layer parity; tightened DATA-07 filter; new
fields surfaced in API + records.

**Skill invocation (must appear as literal substring in SUMMARY.md):**

`Skill(skill="python-patterns", args="Author migration 007 mirroring 006 column shapes onto rss_articles. Update article_query.py: tighten _DATA07_KOL_FRAGMENT / _DATA07_RSS_FRAGMENT / _DATA07_BARE from '(L2 IS NULL OR L2 != reject)' to 'L2 = ok'. Update _verify_quality_columns error msg to reflect tightened semantics. Extend ArticleRecord frozen dataclass with title_translated: Optional[str] + translated_lang: Optional[str]. Update all SELECT column lists (lines 272, 284, 331, 339, 348, 567, 585, 638) to include the 2 new fields. Update list_articles + helpers + get_article_by_hash to pass through. Update _record_to_list_item / _record_to_dict in api_routers/articles.py to emit new fields in API response.")`

`Skill(skill="writing-tests", args="Update test fixture CREATE TABLE for both articles + rss_articles to include title_translated + translated_lang + body_translated + translated_at columns (per feedback_contract_shape_change_full_audit.md — fixture drift hides bugs). Extend fixture rows to include layer2_verdict values: 'ok' / 'reject' / NULL across rows. Add test cases: tightened filter excludes L2 IS NULL rows; ArticleRecord exposes new fields; _record_to_dict emits new fields in dict. Update existing tests that assumed L2 IS NULL was visible (likely 5-15 cases).")`

**Tasks:**

1. **migration 007** at `kb/data/migrations/007_rss_translation_columns.sql`:

   ```sql
   -- Mirror migration 006 onto rss_articles
   ALTER TABLE rss_articles ADD COLUMN body_translated TEXT;
   ALTER TABLE rss_articles ADD COLUMN title_translated TEXT;
   ALTER TABLE rss_articles ADD COLUMN translated_lang TEXT;
   ALTER TABLE rss_articles ADD COLUMN translated_at TEXT;
   ```

   Include rollback comment + version-bump per existing migration convention.

2. **`kb/data/article_query.py`** (5 edits):
   - Lines 33-34 comment: update to reflect tightened semantics (`AND layer2_verdict = 'ok'`)
   - Lines 60-63 `_verify_quality_columns` error msg: same update
   - Lines 71-85 `_DATA07_KOL_FRAGMENT` / `_DATA07_RSS_FRAGMENT` / `_DATA07_BARE`: change `"AND (a.layer2_verdict IS NULL OR a.layer2_verdict != 'reject')"` → `"AND a.layer2_verdict = 'ok'"` (and equivalent for `r.` and bare)
   - `ArticleRecord` dataclass: add `title_translated: Optional[str] = None` + `translated_lang: Optional[str] = None` (already has `body_translated` + `translated_at` from kb-v2.2-2)
   - SELECT clauses at approximate lines 272, 284, 331, 339, 348, 567, 585, 638 (`grep -n "SELECT" kb/data/article_query.py` to enumerate exactly): add `title_translated`, `translated_lang` columns to each; pass through to `ArticleRecord(...)` constructor

3. **`kb/api_routers/articles.py`** (`_record_to_list_item` ~line 53+, `_record_to_dict` ~line 172+): emit the two new fields in API response payloads.

4. **Tests**: extend fixtures + add cases per `writing-tests` skill above. Verify with:

   ```bash
   venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query.py tests/unit/kb/test_articles_api.py -v
   ```

5. **Doc:** if `kb/docs/<...CONTENT-QUALITY-DECISIONS>.md` (or similar) documents the old looser rule, update the prose to match tightened semantics. Skip if no such doc exists for DATA-07 specifically.

**Done when:**

- migration 007 applied to local dev DB and `PRAGMA table_info(rss_articles)` shows the 4 new columns
- `grep -n "layer2_verdict" kb/data/article_query.py` shows zero `IS NULL` clauses (only `= 'ok'`)
- `ArticleRecord` exposes `title_translated` + `translated_lang`
- API JSON response includes both new fields
- All updated unit tests PASS; no regressions in `tests/unit/kb/`

---

### Wave 2 — Databricks one-shot translation notebook

**Concern:** Translation production. Manual trigger only. Single file. No automation.

**Skill invocation:**

`Skill(skill="python-patterns", args="Single-file Databricks notebook (databricks-deploy/translate_kb.py). One frozen dataclass for the row tuple if it improves clarity, otherwise plain tuples — KISS. Use WorkspaceClient().serving_endpoints.query(name='databricks-claude-haiku-4-5') for translation calls. Body prompt MUST explicitly enforce image-position invariance — image refs ![alt](url) appear at EXACT same line/paragraph positions as in source markdown; LLM must NOT batch images at section/article end, NOT reorder paragraphs to flow images differently, NOT consolidate adjacent images. The SCRAPER pipeline (separate work, already shipped) preserves image inline positioning in articles.body markdown — the translator MUST treat that positioning as structural, not stylistic. Two LLM calls per row (title + body). UPDATE statement uses parameterized binding, no string concat. Idempotency: WHERE body_translated IS NULL guard means re-running 'Run all' only translates new rows.")`

**Tasks:**

1. Author **`databricks-deploy/translate_kb.py`** as a Databricks notebook:

   ```
   # Cell 1: SCP pull from Hermes (2 inline lines, no separate script)
   #   Read SSH credentials from Databricks workspace secret store
   #   scp <hermes>:~/.hermes/omonigraph-vault/kb.db /tmp/kb.db
   
   # Cell 2: SELECT candidate rows
   #   SELECT id, 'articles' AS table_name, title, body, lang FROM articles
   #     WHERE layer1_verdict='candidate' AND layer2_verdict='ok'
   #       AND body_translated IS NULL
   #   UNION ALL
   #   SELECT id, 'rss_articles' AS table_name, title, body, lang FROM rss_articles
   #     WHERE layer1_verdict='candidate' AND layer2_verdict='ok'
   #       AND body_translated IS NULL
   
   # Cell 3: For each row
   #   target_lang = 'en' if row.lang == 'zh-CN' else 'zh-CN'
   #   translated_title = WorkspaceClient().serving_endpoints.query(
   #       name='databricks-claude-haiku-4-5',
   #       messages=[ChatMessage(role=USER, content=title_prompt(row.title, target_lang))]
   #   ).choices[0].message.content
   #   translated_body = ... body_prompt MUST contain explicit clauses:
   #     - "Image references ![alt](url) MUST appear at the EXACT same line/paragraph
   #        positions as in the source markdown. Do NOT relocate images to section ends.
   #        Do NOT consolidate consecutive images. Do NOT reorder paragraphs."
   #     - "Code blocks ```...``` are preserved verbatim — content untranslated."
   #     - "Heading levels (#/##/###) preserved exactly."
   #     - "Translate natural-language text only. Image positioning is structural data."
   #     - "Return ONLY the translated markdown — no preamble, no explanation."
   #
   #   Post-LLM safety check (per row, log only — does NOT block UPDATE):
   #     orig_img_count = len(re.findall(r'!\[[^\]]*\]\([^)]+\)', row.body))
   #     trans_img_count = len(re.findall(r'!\[[^\]]*\]\([^)]+\)', translated_body))
   #     if orig_img_count != trans_img_count: print warning + log row.id (manual spot-check later)
   
   # Cell 4: UPDATE four columns
   #   UPDATE {table_name} SET body_translated=?, title_translated=?, 
   #       translated_lang=?, translated_at=? WHERE id=?
   #   (parameterized, no string concat)
   
   # Cell 5: SCP push back to Hermes (2 inline lines)
   #   User runs `sqlite3 ~/.hermes/omonigraph-vault/kb.db .backup /tmp/kb.db.snap` on
   #   Hermes BEFORE pulling, to avoid SQLite write lock during the snapshot.
   ```

2. **Manual trigger only.** Run inside Databricks workspace via "Run all". No `databricks bundle run`, no schedule, no CLI automation. **No `databricks.yml` job entry.**

3. **No companion files.** No `merge_translations.py`. No `translate_log.jsonl`. No quality gate. No `len_ratio` flagging. User explicitly killed all of these.

**Done when:**

- `databricks-deploy/translate_kb.py` exists and reviewable as a single file
- Notebook docstring (cell 0) documents the manual trigger workflow + the 1-line `sqlite3 .backup` pre-step user runs on Hermes
- No bundle yaml additions, no scheduling configuration, no shell scripts
- File reviewed by user before first prod run (translation cost is paid budget — verify prompt quality and cost estimate first)

---

### Wave 3 — Delete on-demand translation surface

**Concern:** Clean removal of kb-v2.2-2 UX surface. Verify each grep is empty after deletion.

No design Skill needed — surgical deletion per CLAUDE.md PRINCIPLE 3 (touch only what you must). Imports orphaned by your deletion get cleaned up; pre-existing dead code is NOT touched.

**Tasks:**

1. **`kb/api_routers/articles.py`**:
   - Delete `POST /api/translate/{hash}` route (~lines 227-262)
   - Delete `GET /api/translate/{hash}` route (~lines 265-295)
   - Delete `_load_translation()` helper
   - Remove `?lang=` query param logic from `GET /api/article/{hash}` (~lines 131, 159, 186-221) — the endpoint stays, but stops loading translation rows
   - Verify imports cleaned up (orphan `from kb.services.translation import ...` etc. — per CLAUDE.md PRINCIPLE 3: remove imports YOUR changes orphan, do not touch others)

2. **Delete entire file** `kb/services/translation.py` (`git rm`)

3. **`kb/templates/article.html`**:
   - Delete lines 110-118 (`{% if article.source == 'wechat' and article.lang in ('zh-CN', 'en') %}` block — translate-row div + button)
   - Delete lines 199-265 (`{% if article.source == 'wechat' and article.lang in ('zh-CN', 'en') %}` block — inline `<script>` translate handler with `pollArticle`, `applyTranslation`, `revertToOriginal`)

4. **Tests**: delete cases that hit deleted code:
   - `tests/integration/kb/test_synthesize_*` cases involving translation API call
   - Any unit/integration tests for `_load_translation` / `translation.py` / `/api/translate` endpoints
   - Per `feedback_contract_shape_change_full_audit.md`: `grep -rn 'translation\\|translate_article\\|_load_translation' tests/` → review each match before deciding delete-vs-keep

5. **Grep verification (must all return empty / zero matches):**

   ```bash
   grep -rn "translate_article\|_load_translation\|translate-toggle" kb/ tests/
   grep -rn "kb/services/translation\|from kb.services.translation" kb/ tests/
   grep -rn "/api/translate" kb/ tests/    # any remaining route reference
   ```

   (`_QA_PROMPT_TEMPLATE_ZH/EN` is unrelated kb-v2.2-4 territory — keep those.)

**Done when:**

- All grep checks above return empty
- `pytest tests/unit/kb/ tests/integration/kb/ -v` PASSES (no broken imports)
- `kb/services/translation.py` does not exist on disk
- Article detail page rendered locally has no `#translate-toggle` button and no inline `<script>` for translation handler

---

### Wave 4 — SSG bilingual rendering 【ui-ux-pro-max + frontend-design】

**Concern:** Render both languages in single SSG output via dual-`<span data-lang>` blocks. Untranslated articles fall back to original Chinese.

**Skill invocations (BOTH must appear as literal substrings in SUMMARY.md):**

`Skill(skill="ui-ux-pro-max", args="Validate three UX decisions for bilingual-by-site-language rendering: (a) removing translate button when site lang determines reading content matches user's mental model of bilingual KB (locked decision A1); (b) untranslated fallback to original Chinese in EN site needs no visual marker — mixed-language display acceptable per user req #2 (locked decision A4); (c) [data-lang] CSS swap doesn't introduce layout shift between zh/en versions of same card (font metrics, line-height, container width all stay stable). Output: GO/STOP signal + any UX adjustments needed before implementation.")`

`Skill(skill="frontend-design", args="Match existing chrome bilingual pattern (kb/static/style.css:330+ [data-lang] rules). Article detail h1 + body dual-block keeps line-height / font-size / color tokens identical to current article.html. Card title dual-span in articles_index.html follows same pattern as nav-brand at article.html:31. NO new design tokens, NO new components — pure mechanical extension of the existing pattern. Output: confirmed style mapping for h1 + body + card-title dual-block emission, NO layout shift between languages on any viewport.")`

**Tasks:**

1. **`kb/templates/article.html`**:
   - Line 2: change `<html lang="{{ article.lang }}" data-fixed-lang="true">` → `<html lang="{{ article.lang }}">` (keep server-rendered initial lang; lang.js will override per cookie/browser on load — see Wave 5)
   - Line ~72: replace `<h1>{{ article.title }}</h1>` with:

     ```jinja
     <h1>
       <span data-lang="zh">{{ article.title }}</span><span data-lang="en">{{ article.title_translated or article.title }}</span>
     </h1>
     ```

   - Line ~124: replace single `<article class="article-body">{{ body_html | safe }}</article>` with two sibling articles:

     ```jinja
     <article class="article-body" data-lang="zh">{{ body_html | safe }}</article>
     <article class="article-body" data-lang="en">{{ translated_body_html or body_html | safe }}</article>
     ```

   - The `.article-detail-layout` wrapper + `.article-aside` block stay unchanged
   - Line 6 `<title>` already has dual-brand format — leave as-is

2. **`kb/templates/articles_index.html`** (and any card include partial used by it): card title dual-span pattern (same shape as article.html h1):

   ```jinja
   <span data-lang="zh">{{ card.title }}</span><span data-lang="en">{{ card.title_translated or card.title }}</span>
   ```

   Card meta / breadcrumb chrome already uses the dual-span pattern, no changes there.

3. **`kb/export_knowledge_base.py`**:
   - Read `body_translated` column for each article (already available via `ArticleRecord.body_translated` from kb-v2.2-2 migration 006 + this phase Wave 1's Wave-1 update)
   - Pass `body_translated` through the SAME markdown→HTML pipeline (`get_article_body` / `body_md` → `body_html`) including EXPORT-05 image rewrite, producing `translated_body_html`
   - Add `translated_body_html` to template context for `article.html`
   - Article card record dataclass: add `title_translated: Optional[str] = None` so card template can `card.title_translated or card.title`
   - For articles with `body_translated IS NULL`: pass empty/None `translated_body_html`; template's `or body_html` fallback covers rendering
   - **Per A9**: read `os.environ.get('KB_DEFAULT_LANG', 'zh-CN')`, validate against `{'zh-CN', 'en'}` (fall back to `'zh-CN'` if invalid), pass into base template context as `kb_default_lang`

4. **`kb/templates/base.html`** (per A9 — KB_DEFAULT_LANG injection):
   - Locate the `<script src=".../static/lang.js">` tag (currently line 99-ish)
   - Insert a sibling `<script>` tag **immediately before** lang.js loads:

     ```jinja
     <script>window.KB_DEFAULT_LANG = "{{ kb_default_lang | default('zh-CN') }}";</script>
     <script src="{{ base_path }}/static/lang.js"></script>
     ```

   - The order matters: `window.KB_DEFAULT_LANG` must be set before lang.js IIFE runs

5. **CSS:** NO changes. Existing `kb/static/style.css:330+` `[data-lang]` rules already drive visibility off `<html lang>`.

**Tests:**

- SSG output regression in `tests/integration/kb/test_export_*`: rendered HTML for at least 2 articles in fixture (1 with `title_translated` populated, 1 with NULL) → grep for `data-lang="en"` in output
- Verify zh-only rendering still works for articles where `title_translated IS NULL` (the `or` fallback emits zh into the `data-lang="en"` span — existing CSS `[data-lang]` rules handle visibility)
- Verify `data-fixed-lang="true"` no longer appears in any rendered article HTML
- Verify `window.KB_DEFAULT_LANG = "..."` injection appears in rendered base template before `lang.js` script tag (parametrized test: env var unset → `"zh-CN"`; env var `en` → `"en"`; env var `bogus` → falls back to `"zh-CN"`)

**Done when:**

- SSG of fixture-DB renders article detail page with both `<span data-lang="zh">` and `<span data-lang="en">` blocks for h1 + body
- `<html data-fixed-lang>` attribute does not appear in any rendered SSG output
- Articles index card titles emit dual-span
- `<script>window.KB_DEFAULT_LANG = "..."</script>` precedes `<script src=".../lang.js">` in rendered HTML; value reflects `KB_DEFAULT_LANG` env var
- `Skill(skill="ui-ux-pro-max"` GO signal received
- `Skill(skill="frontend-design"` confirms no layout shift, no new tokens introduced
- All updated SSG tests PASS

---

### Wave 5 — `lang.js` first-visit persistence + remove `data-fixed-lang` guard

**Concern:** Pure JS behavior change. Browser-detect lang gets persisted on first visit. `applyLang()` always sets `<html lang>` (no per-page-fixed override).

**Tasks** (no design skill needed — pure behavior):

1. **`kb/static/lang.js:67-69`** (`resolveLang()`):
   - Current:

     ```js
     var c = readCookie(COOKIE_NAME);
     if (c && SUPPORTED.indexOf(c) !== -1) return c;
     return detectFromBrowser();
     ```

   - New:

     ```js
     var c = readCookie(COOKIE_NAME);
     if (c && SUPPORTED.indexOf(c) !== -1) return c;
     var detected = detectFromBrowser();
     writeCookie(COOKIE_NAME, detected);
     return detected;
     ```

2. **`kb/static/lang.js:72-79`** (`applyLang()`):
   - Current:

     ```js
     function applyLang(lang) {
       var html = document.documentElement;
       if (html.getAttribute('data-fixed-lang') !== 'true') {
         html.setAttribute('lang', lang);
       }
       var toggle = document.querySelector('.lang-toggle');
       if (toggle) toggle.setAttribute('data-current', lang);
     }
     ```

   - New:

     ```js
     function applyLang(lang) {
       document.documentElement.setAttribute('lang', lang);
       var toggle = document.querySelector('.lang-toggle');
       if (toggle) toggle.setAttribute('data-current', lang);
     }
     ```

3. **`bindToggle()` (lang.js:81-93):** UNCHANGED. Toggle button click cycles lang + sets cookie + reloads page with `?lang=` (which then takes precedence in next load via `readQueryLang()`).

4. **`DEFAULT_LANG` (lang.js:25)** — per A9, replace hardcoded constant with deployment-injected fallback:
   - Current: `var DEFAULT_LANG = 'zh-CN';`
   - New (after the `SUPPORTED` declaration so validation works):

     ```js
     var DEFAULT_LANG = (typeof window !== 'undefined'
       && typeof window.KB_DEFAULT_LANG === 'string'
       && SUPPORTED.indexOf(window.KB_DEFAULT_LANG) !== -1)
       ? window.KB_DEFAULT_LANG : 'zh-CN';
     ```

   - This preserves ES5 syntax (no arrow / no const), validates against `SUPPORTED`, falls back to `'zh-CN'` if injection missing or invalid (graceful degradation if base.html ever forgets the inject script tag)

5. **Comment block (lang.js:1-18):** update to reflect new behavior:
   - Resolution order item 3: "navigator.languages — persisted to cookie on first visit"
   - Resolution order item 4: "fallback — `window.KB_DEFAULT_LANG` (deployment env var injected by base.html), then 'zh-CN'"
   - Remove "On article detail pages, server-side sets `<html lang>` = content language; this script does NOT override that — only toggles UI chrome spans" + "Detection: `<html data-fixed-lang="true">` means content-fixed page" — NO LONGER TRUE under decision A1.

**Tests** (`tests/unit/kb/test_lang_js.py` or jsdom-style equivalent):

| Test | Validates |
|---|---|
| `test_first_visit_browser_en_writes_cookie` | Clear cookie + simulate `navigator.languages = ['en-US']` → `resolveLang()` returns `'en'` AND cookie now contains `kb_lang=en` |
| `test_first_visit_browser_zh_writes_cookie` | Same with `['zh-CN']` → `'zh-CN'` + cookie written |
| `test_existing_cookie_skips_browser_detect` | Cookie pre-set to `'en'` → `resolveLang()` returns `'en'` without consulting `navigator.languages` (verify via spy) |
| `test_apply_lang_sets_html_lang_no_fixed_guard` | Even with `<html data-fixed-lang="true">` (legacy attribute that should not exist post-Wave 4 but defensive test) → `applyLang('en')` still sets `<html lang="en">` |
| `test_toggle_button_unchanged_behavior` | Click `.lang-toggle` → cookie cycles + URL gets `?lang=` + page reload triggered |
| `test_default_lang_uses_kb_default_lang_when_set` (A9) | `window.KB_DEFAULT_LANG = 'en'` + clear cookie + `navigator.languages = ['ja-JP']` (unsupported) → `resolveLang()` returns `'en'` |
| `test_default_lang_falls_back_to_zh_when_kb_default_lang_unset` (A9) | `window.KB_DEFAULT_LANG` undefined + same Japanese-only browser → returns `'zh-CN'` |
| `test_default_lang_validates_against_supported` (A9) | `window.KB_DEFAULT_LANG = 'fr'` (not in `SUPPORTED`) → `DEFAULT_LANG` falls back to `'zh-CN'` |

If jsdom unit tests are not feasible (no existing JS test infra), promote these to Playwright UAT cases in Wave 6 instead — note in PLAN execution that this is the chosen path and document in SUMMARY.

**Done when:**

- `grep -n "data-fixed-lang" kb/` returns zero matches across kb/ subtree
- `applyLang()` always sets `<html lang>`
- First-visit cookie write validated by test (jsdom or Playwright)
- Existing toggle behavior (cookie cycle + reload) verified unchanged
- `DEFAULT_LANG` reads from `window.KB_DEFAULT_LANG` (validated against `SUPPORTED`); fallback to `'zh-CN'` verified for unset / invalid values
- `grep "KB_DEFAULT_LANG" kb/static/lang.js kb/templates/base.html kb/export_knowledge_base.py` shows ≥1 match in each file

---

### Wave 6 — Pre-deploy verification + Local UAT 【frontend-design】

**Concern:** GATE — verify tightened DATA-07 doesn't make N articles disappear. Then full Local UAT per CLAUDE.md PRINCIPLE #6.

#### 6a. Pre-deploy verification GATE (BLOCKING)

Per locked decision A6, the tightened DATA-07 (`L2='ok'`) makes any
currently-visible article with `L2 IS NULL` disappear. Run this query
on Hermes prod DB BEFORE deploying:

```sql
-- Hermes-side query: counts how many currently-visible articles
-- become invisible under tightened DATA-07.
SELECT
  source,
  COUNT(*) FILTER (WHERE layer2_verdict = 'ok') AS l2_passed_kept_visible,
  COUNT(*) FILTER (WHERE layer2_verdict IS NULL) AS l2_pending_will_disappear,
  COUNT(*) FILTER (WHERE layer2_verdict = 'reject') AS l2_rejected_already_invisible
FROM (
  SELECT 'articles' AS source, layer1_verdict, layer2_verdict FROM articles
  UNION ALL
  SELECT 'rss_articles' AS source, layer1_verdict, layer2_verdict FROM rss_articles
)
WHERE layer1_verdict='candidate' AND body IS NOT NULL AND body != ''
GROUP BY source;
```

**Decision matrix by `l2_pending_will_disappear` count:**

| Count | Action |
|---|---|
| `0` | Ship directly |
| `< 50` | Ship; next Hermes Layer-2 cron fixes within 24-48h |
| `50-300` | Trigger Hermes Layer-2 cron once before ship to drain the queue |
| `> 300` | **STOP** — raise scope concern with user; the tightened-filter scope assumption may not hold |

Capture the actual count + chosen action in `kb-v2.2-7-SUMMARY.md`
§ "Pre-deploy verification gate".

#### 6b. Local UAT (per CLAUDE.md PRINCIPLE #6)

**Skill invocation:**

`Skill(skill="frontend-design", args="UAT visual consistency: zh/en pair screenshots at desktop/tablet/mobile (3 viewports × 2 langs = 6 captures minimum). Verify no layout shift between languages, no broken images, no font fallback issues, no chrome misalignment. Verify untranslated-fallback-to-zh in EN site renders cleanly without visual flag (per locked decision A4). Output: pass/fail per scenario + any visual defects.")`

**Launcher** (per `feedback_kb_local_uat_mandatory.md`):

```bash
venv/Scripts/python.exe .scratch/local_serve.py
# → port 8766: SSG + /api/* + /static/*
```

**Test matrix (9 mandatory scenarios + screenshots):**

| # | Scenario | Expected | Screenshot |
|---|---|---|---|
| 1 | Clear cookie + browser zh locale → `/` | zh chrome (nav, footer, breadcrumb) + zh card titles | `.playwright-mcp/kb-v2.2-7-uat-1.png` |
| 2 | Clear cookie + browser en locale → `/` | en chrome + en titles for translated articles + zh titles for untranslated (mixed acceptable) | `.playwright-mcp/kb-v2.2-7-uat-2.png` |
| 3 | Click `.lang-toggle` on home | full site swaps language, cookie writes new value | `.playwright-mcp/kb-v2.2-7-uat-3.png` |
| 4 | Click `.lang-toggle` on **article detail** page | chrome + h1 + body all swap (verifies `data-fixed-lang` removal in Wave 4 + lang.js fix in Wave 5) | `.playwright-mcp/kb-v2.2-7-uat-4.png` |
| 5 | EN mode + open untranslated article | h1 + body fall back to zh; chrome stays en (mixed acceptable per A4) | `.playwright-mcp/kb-v2.2-7-uat-5.png` |
| 6 | EN mode + open translated wechat article | h1 + body + chrome ALL en, NO `#translate-toggle` button visible anywhere on page | `.playwright-mcp/kb-v2.2-7-uat-6.png` |
| 7 | **KB_DEFAULT_LANG=zh-CN deploy (Aliyun simulation)** + clear cookie + browser ja-JP locale → `/` | site renders zh-CN (deployment-default fallback when browser unsupported) | `.playwright-mcp/kb-v2.2-7-uat-7-aliyun.png` |
| 8 | **KB_DEFAULT_LANG=en deploy (Databricks simulation)** + clear cookie + browser ja-JP locale → `/` | site renders en (deployment-default fallback when browser unsupported) | `.playwright-mcp/kb-v2.2-7-uat-8-databricks.png` |
| 9 | **Image inline-mix preservation** — open translated wechat article with ≥5 images zh+en side-by-side; visually compare image-to-paragraph relative positions | image positions in `body_translated` markdown match `body` original positions (no images batched at section/article end, no consecutive-image consolidation, no paragraph reordering) | `.playwright-mcp/kb-v2.2-7-uat-9a-zh.png` + `.playwright-mcp/kb-v2.2-7-uat-9b-en.png` |

**Scenarios 7-8 launcher pattern:**

```bash
KB_DEFAULT_LANG=zh-CN venv/Scripts/python.exe .scratch/local_serve.py    # scenario 7
KB_DEFAULT_LANG=en    venv/Scripts/python.exe .scratch/local_serve.py    # scenario 8
```

Browser locale simulation via Playwright MCP `browser_navigate` after `page.context.setExtraHTTPHeaders({'Accept-Language': 'ja-JP,ja'})` or DevTools sensor.

**Scenario 9 verification protocol:**

- Pick an article with `image_count >= 5` from prod data (Aliyun / Hermes have these)
- After Databricks notebook translation, open `/article/<hash>.html` with cookie `kb_lang=zh` → screenshot 9a
- Same URL with cookie `kb_lang=en` → screenshot 9b
- Side-by-side compare: image at paragraph-position-N in zh should appear at the same paragraph-position-N in en (allow ±1 paragraph for natural translation drift)
- BLOCKER if any image relocates >1 paragraph or batches at end

**Curl smoke (all return 2xx):**

```bash
curl -i http://localhost:8766/api/articles | head -20
curl -i http://localhost:8766/api/article/<known-hash> | head -20
curl -i http://localhost:8766/api/translate/<any-hash>   # MUST 404 (route deleted in Wave 3)
```

The 404 from `/api/translate/...` is the positive signal that Wave 3 deletion shipped correctly.

**SUMMARY.md § "Local UAT" must cite all 9 screenshot paths + 3 curl outputs (status + key fields).** Phase MUST NOT be marked complete in STATE-KB-v2.md / VERIFICATION.md until all 9 screenshots captured + GATE 6a documented.

**Done when:**

- 6a query run on Hermes; count + decision documented in SUMMARY
- 6b Local UAT executed; all 9 scenarios PASS; 9 screenshots (7-9b → 10 files because scenario 9 is a pair) captured + cited
- 3 curl outputs captured (especially the `/api/translate` 404)
- `frontend-design` Skill invocation visible in SUMMARY.md (literal grep substring)
- Scenario 9 image-position comparison documented: per-article image-paragraph-position diff (∆≤1 paragraph per image) recorded in SUMMARY

---

## Test plan summary

| Wave | Tests added | Tests deleted | Tests updated |
|---|---|---|---|
| 1 | tightened-DATA-07 cases; new fields on ArticleRecord; rss_articles fixture parity | none | existing fixture CREATE TABLEs (add 4 cols × 2 tables); cases that assumed `L2 IS NULL` was visible (5-15 cases) |
| 2 | none (notebook is operator-run, not CI-tested) | none | none |
| 3 | none | translation API integration cases; `_load_translation` unit cases; translate endpoint route tests | none |
| 4 | SSG output contains `data-lang="en"` blocks; untranslated fallback renders zh | none | existing `test_export_*` regression baselines |
| 5 | first-visit cookie persistence; `applyLang` no-guard behavior; toggle on article detail page | none | none |
| 6 | none (UAT is human-verified, not pytest) | none | none |

**Acceptance:** all updated pytest cases PASS in:

```bash
venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -v
```

## Acceptance criteria (grep-verifiable + UAT-anchored — combines must_haves)

**Schema + data layer**

- [ ] `kb/data/migrations/007_rss_translation_columns.sql` exists; applied migration shows 4 new columns on `rss_articles`
- [ ] `grep -n "layer2_verdict" kb/data/article_query.py` shows zero `IS NULL` clauses inside DATA-07 fragments (only `= 'ok'`)
- [ ] `ArticleRecord` exposes `title_translated` + `translated_lang` fields (`grep -n "title_translated\|translated_lang" kb/data/article_query.py`)
- [ ] `_record_to_dict` API JSON includes both new fields (curl `/api/article/<hash>`)

**Deletion surface (kb-v2.2-2 UX revert verified empty)**

- [ ] `kb/services/translation.py` does NOT exist on disk (`ls kb/services/translation.py 2>&1 | grep -q "No such"`)
- [ ] `grep -rn "translate_article\|_load_translation\|translate-toggle\|kb/services/translation" kb/ tests/` returns ZERO matches
- [ ] `grep -rn "data-fixed-lang" kb/` returns ZERO matches
- [ ] Curl smoke: `/api/translate/<hash>` returns HTTP 404 (positive signal of Wave 3 deletion)

**Bilingual rendering**

- [ ] `grep -n 'data-lang="en"' kb/templates/article.html` shows ≥2 matches (h1 + body)
- [ ] `grep -n 'data-lang="en"' kb/templates/articles_index.html` shows ≥1 match (card title)

**Per-deployment default lang (A9, both Aliyun + Databricks)**

- [ ] `grep "KB_DEFAULT_LANG" kb/static/lang.js kb/templates/base.html kb/export_knowledge_base.py` shows ≥1 match in EACH file (3 files total)
- [ ] Rendered `base.html` output contains `<script>window.KB_DEFAULT_LANG = "..."</script>` BEFORE the `lang.js` script tag (verified by Wave-4 SSG regression test)
- [ ] UAT scenarios 7+8 PASS (KB_DEFAULT_LANG=zh-CN renders zh on ja-JP browser; KB_DEFAULT_LANG=en renders en on ja-JP browser)

**Image inline-mix preservation (R7)**

- [ ] Wave 2 notebook prompt contains the four explicit clauses (image positioning structural / no relocate to ends / no consolidate / no reorder paragraphs) — grep `databricks-deploy/translate_kb.py` for "structural" and "MUST"
- [ ] UAT scenario 9 PASS: per-article image-paragraph-position diff ≤1 paragraph between zh/en versions (recorded in SUMMARY)
- [ ] Notebook safety-check log captured: any rows where `orig_img_count != trans_img_count` flagged in `translate_kb_run.log` (manual spot-check before next batch)

**Databricks notebook (manual-trigger only)**

- [ ] `databricks-deploy/translate_kb.py` exists as single file; no `databricks.yml` job entry added; no companion shell script in `scripts/` subdir
- [ ] Notebook reviewed by user before first prod run

**Pre-deploy + UAT gates**

- [ ] Pre-deploy GATE 6a: Hermes-side L2-pending count + decision documented in SUMMARY § "Pre-deploy verification gate"
- [ ] Local UAT: 9 scenarios PASS, 10 screenshots captured under `.playwright-mcp/kb-v2.2-7-uat-*.png` (scenario 9 is a zh/en pair → 9a + 9b) + cited in SUMMARY § "Local UAT"

**Tests**

- [ ] All updated pytest cases PASS; no regressions vs baseline (`pytest tests/unit/kb/ tests/integration/kb/ -v`)

**Skill discipline (per `feedback_skill_invocation_not_reference.md`)**

- [ ] SUMMARY.md contains literal substrings:
  - `Skill(skill="python-patterns"` — Wave 1 + Wave 2 (2+ occurrences; Wave 3 deletion does NOT need skill invocation)
  - `Skill(skill="writing-tests"` — Wave 1
  - `Skill(skill="ui-ux-pro-max"` — Wave 4
  - `Skill(skill="frontend-design"` — Wave 4 + Wave 6 (2+ occurrences)
  - Verify: `grep -c 'Skill(skill="' kb-v2.2-7-bilingual-by-site-language-SUMMARY.md` ≥ 5

## Skill discipline (regex check)

After execution, SUMMARY.md MUST contain at least these literal substrings (per `feedback_skill_invocation_not_reference.md`):

- `Skill(skill="python-patterns"` — Wave 1 (article_query update) + Wave 2 (notebook with image-position prompt)
- `Skill(skill="writing-tests"` — Wave 1 (fixture extension + DATA-07 tightening tests)
- `Skill(skill="ui-ux-pro-max"` — Wave 4 (UX validation of three decisions)
- `Skill(skill="frontend-design"` — Wave 4 (style mapping) + Wave 6 (UAT visual consistency, image-position pair compare)

Wave 3 deletion surgery does NOT need a Skill invocation (pure mechanical removal per CLAUDE.md PRINCIPLE 3 — no design or pattern decisions).

These are tool-call invocations, NOT `<read_first>` references. The
executor MUST emit each as an actual `Skill` tool call during execution.

## Risks + mitigations (real risks only — no speculative defenses)

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | Tightened DATA-07 hides >300 currently-visible articles | LOW (most candidates have L2 verdict by now per ROADMAP-KB-v2 cadence) | Wave 6a GATE — count first, decide path; STOP at >300 |
| R3 | `data-fixed-lang` removal breaks something we didn't anticipate (e.g., article detail shows wrong initial lang on hard reload) | MEDIUM | UAT scenario 4 catches this — toggle on detail must swap; if it doesn't, kb-v2.2-2 had a server-side initial-lang invariant that needs preserving |
| R7 | LLM translation reorders images / batches them at section ends → undoes the SCRAPER-side image inline-positioning fix | **HIGH** (image preservation prompts often interpreted as "preserve syntax" not "preserve position"; LLM may re-flow paragraphs to "natural English reading order") | Wave 2 prompt has explicit clauses: "image positioning is structural data, not text"; "do NOT relocate images to section ends"; "do NOT consolidate consecutive images"; "do NOT reorder paragraphs". Wave 2 post-LLM safety check logs row.id when `orig_img_count != trans_img_count` (warn-only, manual spot-check). UAT scenario 9 zh/en pair screenshot compares image-paragraph relative position; ∆>1 paragraph blocks ship |
| R8 | `KB_DEFAULT_LANG` env var not set on Aliyun → site falls back to `'zh-CN'` (correct for Aliyun audience) but Databricks deploy without env var would also fall back to `'zh-CN'` (wrong for English audience) | MEDIUM | UAT scenarios 7+8 explicitly verify both deployments. Databricks `app.yaml` MUST set `KB_DEFAULT_LANG=en` before first browser session; checklist item in deploy runbook |

## Concurrent agent safety

- NO `git commit --amend` (per `feedback_no_amend_in_concurrent_quicks.md`)
- NO `git reset --hard` / `--soft` / `--mixed`
- NO `git rebase -i`
- NO `git push --force` / `--force-with-lease`
- NO `git add -A` / `git add .` (per `feedback_git_add_explicit_in_parallel_quicks.md`)
- ONLY explicit-file `git add` per Wave commit blocks
- Forward-only commits; if attribution drifts due to concurrent quick activity, document in STATE-KB-v2.md row, do NOT amend

Possible concurrent territories during this phase's execute window:

- kdb-2 / kdb-2.5 Databricks app activity (different files: `databricks-deploy/app.yaml`, `_wave0_probe.py`)
- Sibling kb-v2.2 phases — none currently active that touch the same files

Phase territory disjoint from kb-v2.2-1 (`kb/scripts/sync_*`), kb-v2.2-3 (`kb/api_routers/search.py`), kb-v2.2-4 (`kb/services/synthesize.py` `_QA_PROMPT_*`), kb-v2.2-5 (`tests/conftest.py`), kb-v2.2-6 (`kb/export_knowledge_base.py:_canonical_lang`).

**Note on `kb/export_knowledge_base.py`:** Wave 4 of this phase modifies the same file kb-v2.2-6 modified (added `_canonical_lang` helper at data-layer-to-template boundary). Verify no merge conflict before commit; if conflict, manual merge favoring both helpers (they're orthogonal: `_canonical_lang` normalizes `zh` → `zh-CN`; this phase adds `translated_body_html` rendering). Forward-fix.

## Anti-patterns (planner forbids these in execute)

- ❌ DO NOT add bundle yaml or scheduled translation job
- ❌ DO NOT split SCP into separate shell scripts
- ❌ DO NOT add `merge_translations.py`, `translate_log.jsonl`, `len_ratio` quality gate
- ❌ DO NOT add visual marker for untranslated articles in EN site (locked A4)
- ❌ DO NOT keep `data-fixed-lang` attribute "just in case" (locked A1 — delete it)
- ❌ DO NOT delete the `.lang-toggle` button (locked A7 — keep it)
- ❌ DO NOT generate per-language SSG subdirectories (`/en/articles/...`) (locked A3)
- ❌ DO NOT decouple DATA-07 from translation eligibility in soon-to-be-deleted code (kb-v2.2-2 remnants — they're going away in Wave 3)
- ❌ DO NOT modify `kb/static/style.css` `[data-lang]` rules — already correct
- ❌ DO NOT modify `_QA_PROMPT_TEMPLATE_*` (kb-v2.2-4 territory)
- ❌ DO NOT modify migration 006 itself — only EXTEND via 007
- ❌ DO NOT use `git add -A` / `--amend` / `git reset --hard` / `git rebase -i` / `git push --force`
- ❌ DO NOT skip Local UAT per CLAUDE.md PRINCIPLE #6 (KB phase touching `kb/templates` + `kb/static` + `kb/api_routers` + `kb/data` + `kb/export_knowledge_base.py` requires UAT before phase complete)
- ❌ DO NOT skip Wave 6a GATE — pre-deploy DATA-07 tightening verification is mandatory
- ❌ DO NOT hardcode `'zh-CN'` as the lang.js DEFAULT_LANG constant after A9 — it MUST come from `window.KB_DEFAULT_LANG` (validated against `SUPPORTED`) with `'zh-CN'` only as the unset/invalid fallback
- ❌ DO NOT skip Wave 6 UAT scenarios 7+8 (KB_DEFAULT_LANG dual-deployment fallback) or scenario 9 (image inline-mix preservation) — they are non-skippable per Point 2 + Point 3 of the 2026-05-19 self-audit
- ❌ DO NOT weaken the Wave 2 image-position prompt clauses ("structural data" / "do NOT relocate to ends" / "do NOT consolidate" / "do NOT reorder paragraphs") — these are R7 mitigation, not stylistic suggestions
- ❌ DO NOT auto-block UPDATE on the Wave 2 image-count safety check — log-only / warn-only; manual spot-check via UAT scenario 9 is the gate, not the notebook

## Return signal

```
## kb-v2.2-7 BILINGUAL-BY-SITE-LANGUAGE COMPLETE
- migration: kb/data/migrations/007_rss_translation_columns.sql
- updated: kb/data/article_query.py (DATA-07 tightened to L2='ok', 2 new fields surfaced)
- updated: kb/api_routers/articles.py (deleted: /api/translate/{POST,GET}, _load_translation, ?lang= param)
- deleted: kb/services/translation.py
- updated: kb/templates/article.html (no data-fixed-lang; dual-span h1 + body; deleted translate-row + inline script)
- updated: kb/templates/articles_index.html (dual-span card titles)
- updated: kb/templates/base.html (A9: window.KB_DEFAULT_LANG injection before lang.js)
- updated: kb/export_knowledge_base.py (translated_body_html pipeline + KB_DEFAULT_LANG env-var read)
- updated: kb/static/lang.js (first-visit cookie persistence; no data-fixed-lang guard; A9: DEFAULT_LANG from window.KB_DEFAULT_LANG)
- new: databricks-deploy/translate_kb.py (single-file notebook, manual Run all, image-position-preserving prompt)
- tests: <X> updated + <Y> deleted (translation API cases) + <Z> new (data-lang fallback, first-visit cookie, KB_DEFAULT_LANG fallback)
- pytest: <N>/<N> pass; 0 regressions
- Skill regex: python-patterns (W1+W2) / writing-tests (W1) / ui-ux-pro-max (W4) / frontend-design (W4+W6) all in SUMMARY
- pre-deploy GATE 6a: l2_pending=<count>, action=<ship|cron-first|stop>
- Local UAT: 9/9 scenarios PASS; 10 screenshots cited (scenario 9 = zh+en pair)
- /api/translate 404 verified (positive Wave 3 signal)
- A9 dual-deploy: scenarios 7 (zh-CN default) + 8 (en default) both PASS on ja-JP browser
- R7 image-position: scenario 9 ∆≤1 paragraph per image confirmed
- pre-locked decisions: all 9 honored (A1-A9)
- partially supersedes kb-v2.2-2 UX (data layer preserved; only on-demand surface deleted)
- commit: <hash>; pushed origin/main forward-only (ff-merge: yes/no)
- Next: user sets KB_DEFAULT_LANG=en on Databricks deploy + (unset or zh-CN) on Aliyun deploy
   THEN: user runs databricks-deploy/translate_kb.py "Run all" to populate translations on prod DB
   THEN: deploy kb-api restart on both targets + verify each in respective audience browser
```

If BLOCKED → `## kb-v2.2-7 EXECUTE BLOCKED` + cause + escalate (especially if any pre-locked decision A1-A9 proves unworkable, or if Wave 6a GATE shows >300 articles disappearing, or if UAT scenario 9 shows image rearrangement).
