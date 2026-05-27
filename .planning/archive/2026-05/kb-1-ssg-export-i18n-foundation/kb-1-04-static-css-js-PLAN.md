---
phase: kb-1-ssg-export-i18n-foundation
plan: 04
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/static/style.css
  - kb/static/lang.js
autonomous: true
requirements:
  - UI-01
  - UI-02
  - UI-03
  - I18N-01
  - I18N-02
  - I18N-08

must_haves:
  truths:
    - "kb/static/style.css contains all 8 design-token CSS variables"
    - "Font stack 'Inter','Noto Sans SC',system-ui,sans-serif present; no external font URL imports"
    - "Pygments Monokai style def included in style.css under .codehilite class"
    - "Responsive: mobile-first with @media queries at 768px and 1024px breakpoints"
    - "kb/static/lang.js detects Accept-Language via navigator.languages, persists choice in 1-year kb_lang cookie, hard-switches via ?lang= query"
  artifacts:
    - path: "kb/static/style.css"
      provides: "Global design tokens + responsive layout + Pygments style"
      min_lines: 300
    - path: "kb/static/lang.js"
      provides: "JS bootstrap for lang detection + cookie persistence + ?lang= switch"
      min_lines: 60
  key_links:
    - from: "kb/templates/base.html (later plan)"
      to: "/static/style.css"
      via: "link rel=stylesheet"
      pattern: "static/style\\.css"
    - from: "kb/static/lang.js"
      to: "document.documentElement"
      via: "DOMContentLoaded handler sets html lang and data-lang span visibility"
      pattern: "data-lang|kb_lang"
---

<objective>
Build the static asset layer's autonomous parts: design-token-driven CSS and language-toggle JS bootstrap. These are referenced by every template in plans kb-1-07 and kb-1-08; landing them in Wave 1 unblocks template work.

Purpose: UI-01..03 lock the visual identity (vitaclaw dark palette, Inter+Noto Sans SC font stack). I18N-01/02/08 require the JS bootstrap to detect Accept-Language and persist via cookie. Pygments Monokai style baked into style.css avoids a second render-time CSS file.

**REVISION 1 (2026-05-12) — Plan split per Issue #4:** brand-asset sourcing (which genuinely needs a human checkpoint due to vitaclaw-site sibling-repo location uncertainty) was extracted into a dedicated `kb-1-04b-brand-assets-checkpoint-PLAN.md`. This plan is now fully autonomous and Tasks 1+2 produce style.css + lang.js without any checkpoint pause. UI-04 (brand assets) moved to kb-1-04b. Wave assignment unchanged: both kb-1-04 and kb-1-04b run in Wave 1 with no dependencies.

Output: Single style.css file (~400 LOC), lang.js (~85 LOC).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@kb/docs/03-ARCHITECTURE.md
@kb/docs/09-AGENT-QA-HANDBOOK.md
@CLAUDE.md

<interfaces>
Design tokens (from CONTEXT.md "Design tokens (UI-01, UI-02)") — exact values, do not improvise:

```css
:root {
  --bg: #0f172a;
  --bg-card: #1e293b;
  --text: #f0f4f8;
  --text-secondary: #94a3b8;
  --accent: #3b82f6;
  --accent-green: #22d3a0;
  --border: rgba(255, 255, 255, 0.1);
  --font-sans: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

Pygments style generation: run offline once and paste output into style.css:

```bash
python -c "from pygments.formatters import HtmlFormatter; print(HtmlFormatter(style='monokai').get_style_defs('.codehilite'))"
```

JS bootstrap resolution order (CONTEXT.md "Bilingual switching strategy"):
1. ?lang=zh|en|zh-CN query param (hard switch — sets cookie)
2. kb_lang cookie (persisted choice)
3. navigator.languages (Accept-Language equivalent)
4. fallback: 'zh-CN' (KB_DEFAULT_LANG)

Cookie format: `kb_lang=zh-CN` or `kb_lang=en`, max-age=31536000, path=/, SameSite=Lax.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write kb/static/style.css with design tokens + responsive layout + Pygments Monokai</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Design tokens (UI-01, UI-02)" + "Responsive breakpoints (UI-03)"
    - kb/docs/03-ARCHITECTURE.md "页面内部链接地图" (page layout cues)
    - kb/docs/03-ARCHITECTURE.md "ui-ux-pro-max 设计系统推荐" (style direction)
  </read_first>
  <files>kb/static/style.css</files>
  <action>
    Create a single `kb/static/style.css` file with these 9 sections in order:

    Section 1 — CSS variables (`:root` block) with the EXACT 8 design tokens from the interfaces block above.

    Section 2 — Reset + base:
    - `*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }`
    - `body { background: var(--bg); color: var(--text); font-family: var(--font-sans); line-height: 1.6; }`
    - `code, pre { font-family: var(--font-mono); }`
    - `a { color: var(--accent); text-decoration: none; }` and `a:hover { text-decoration: underline; }`
    - `img { max-width: 100%; height: auto; display: block; }`

    Section 3 — Layout primitives: `.container { max-width: 1200px; margin: 0 auto; padding: 0 1rem; }`, `.card`, `.btn`, `.btn-secondary`.

    Section 4 — Top nav (used by base.html in plan 06): `.nav` (flex, justify-between, border-bottom on `--border`), `.nav-brand` (flex with logo height: 32px), `.nav-links` (flex gap: 1.5rem), `.lang-toggle` (transparent background, border, padding 0.25rem 0.75rem).

    Section 5 — i18n span toggling (CRITICAL — paired with lang.js):
    - `[data-lang] { display: none; }` (default hide all)
    - `html[lang="zh-CN"] [data-lang="zh"], html[lang="zh"] [data-lang="zh"] { display: inline; }`
    - `html[lang="en"] [data-lang="en"] { display: inline; }`
    - For block-level: `.lang-block[data-lang]` with display: block in matching html[lang] selectors.

    Section 6 — Article list cards: `.article-card`, `.article-card-title` (font-size 1.25rem), `.article-card-meta` (color var(--text-secondary), font-size 0.875rem), `.lang-badge` (display: inline-block, padding 0.125rem 0.5rem, background var(--accent-green), color var(--bg), border-radius 4px, font-size 0.75rem, font-weight 600).

    Section 7 — Article detail: `.article-body` (line-height 1.8, max-width 720px, margin 2rem auto), `.article-body h1/h2/h3` (margin-top 2rem), `.article-body p` (margin-bottom 1rem), `.article-body img` (margin 1.5rem auto, border-radius 8px), `.article-body pre` (background #272822 — Monokai bg — padding 1rem, border-radius 4px, overflow-x auto), `.article-body code` (background var(--bg-card), padding 0.125rem 0.375rem, border-radius 3px), `.article-body pre code` (transparent background), `.breadcrumb` (color var(--text-secondary), font-size 0.875rem, margin 1rem 0).

    Section 8 — Responsive (mobile-first):
    - Default styles target mobile (320-767px)
    - `@media (min-width: 768px)` — tablet adjustments (e.g. `.container { padding: 0 2rem; }`)
    - `@media (min-width: 1024px)` — desktop (sidebar layouts)
    - On mobile: `.nav-links { font-size: 0.875rem; gap: 1rem; }` so it fits at 320px
    - Add `body { overflow-x: hidden; }` to guarantee no horizontal scroll

    Section 9 — Pygments Monokai (run offline first, then paste output):
    Run `python -c "from pygments.formatters import HtmlFormatter; print(HtmlFormatter(style='monokai').get_style_defs('.codehilite'))"`. Paste the resulting ~80 lines (starts with `.codehilite .hll`, `.codehilite .c`, etc.) as the final section of style.css.

    If pygments not installed, run `pip install pygments>=2.17` first (it is in PROJECT-KB-v2.md "Tech Stack additions only" list).

    File total: 300-450 lines. NO external font URL imports. NO Tailwind utility classes. Raw CSS only.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; wc -l kb/static/style.css</automated>
  </verify>
  <acceptance_criteria>
    - `kb/static/style.css` exists with line count ≥ 300
    - Contains EXACT strings (each grep-matchable): `--bg: #0f172a`, `--bg-card: #1e293b`, `--text: #f0f4f8`, `--accent: #3b82f6`, `--accent-green: #22d3a0`
    - Contains the literal: `'Inter', 'Noto Sans SC', system-ui, sans-serif`
    - Contains at least 2 `@media (min-width:` queries (mobile-first responsive)
    - Contains `[data-lang]` selector
    - Contains `html[lang="en"]` selector
    - Contains `.codehilite` class (Pygments Monokai style def)
    - Contains `.lang-badge` class
    - `grep -E "@import.*://|googleapis|cdn\." kb/static/style.css` returns 0 hits (no external resources)
  </acceptance_criteria>
  <done>style.css written with all 9 sections, no external resources, Pygments embedded.</done>
</task>

<task type="auto">
  <name>Task 2: Write kb/static/lang.js — Accept-Language detect + cookie + ?lang= switch</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Bilingual switching strategy (UI chrome)" + "Default lang detection"
    - .planning/REQUIREMENTS-KB-v2.md I18N-01 (Accept-Language), I18N-02 (cookie), I18N-08 (toggle nav element)
  </read_first>
  <files>kb/static/lang.js</files>
  <action>
    Create `kb/static/lang.js` with EXACTLY this content (vanilla ES5-compatible JS, no jQuery, no build step). Note: ES5 compat for older WeChat in-app browser support.

    ```javascript
    /* I18N-01/02/08: Bilingual chrome switcher.
     *
     * Resolution order:
     *   1. ?lang=zh|en|zh-CN query param (hard switch — sets cookie)
     *   2. kb_lang cookie (persisted choice)
     *   3. navigator.languages (Accept-Language equivalent)
     *   4. fallback: 'zh-CN'
     *
     * Sets <html lang> on chrome pages (home, articles list, ask).
     * On article detail pages, server-side sets <html lang> = content language;
     * this script does NOT override that — only toggles UI chrome spans.
     * Detection: <html data-fixed-lang="true"> means content-fixed page.
     *
     * Toggle button (.lang-toggle): cycles zh ↔ en, sets cookie, reloads.
     */
    (function () {
      'use strict';

      var SUPPORTED = ['zh-CN', 'en'];
      var COOKIE_NAME = 'kb_lang';
      var COOKIE_MAX_AGE = 31536000; // 1 year
      var DEFAULT_LANG = 'zh-CN';

      function readCookie(name) {
        var pairs = document.cookie.split(';');
        for (var i = 0; i < pairs.length; i++) {
          var p = pairs[i].trim();
          if (p.indexOf(name + '=') === 0) return p.substring(name.length + 1);
        }
        return null;
      }

      function writeCookie(name, value) {
        document.cookie = name + '=' + value
          + '; path=/; max-age=' + COOKIE_MAX_AGE
          + '; SameSite=Lax';
      }

      function readQueryLang() {
        var params = new URLSearchParams(window.location.search);
        var q = params.get('lang');
        if (!q) return null;
        if (q === 'zh' || q === 'zh-CN') return 'zh-CN';
        if (q === 'en') return 'en';
        return null;
      }

      function detectFromBrowser() {
        var langs = navigator.languages || [navigator.language || ''];
        for (var i = 0; i < langs.length; i++) {
          var l = (langs[i] || '').toLowerCase();
          if (l.indexOf('zh') === 0) return 'zh-CN';
          if (l.indexOf('en') === 0) return 'en';
        }
        return DEFAULT_LANG;
      }

      function resolveLang() {
        var q = readQueryLang();
        if (q) {
          writeCookie(COOKIE_NAME, q);
          return q;
        }
        var c = readCookie(COOKIE_NAME);
        if (c && SUPPORTED.indexOf(c) !== -1) return c;
        return detectFromBrowser();
      }

      function applyLang(lang) {
        var html = document.documentElement;
        if (html.getAttribute('data-fixed-lang') !== 'true') {
          html.setAttribute('lang', lang);
        }
        var toggle = document.querySelector('.lang-toggle');
        if (toggle) toggle.setAttribute('data-current', lang);
      }

      function bindToggle() {
        var toggle = document.querySelector('.lang-toggle');
        if (!toggle) return;
        toggle.addEventListener('click', function (e) {
          e.preventDefault();
          var current = toggle.getAttribute('data-current') || DEFAULT_LANG;
          var next = current === 'zh-CN' ? 'en' : 'zh-CN';
          writeCookie(COOKIE_NAME, next);
          var url = new URL(window.location.href);
          url.searchParams.set('lang', next);
          window.location.href = url.toString();
        });
      }

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
          applyLang(resolveLang());
          bindToggle();
        });
      } else {
        applyLang(resolveLang());
        bindToggle();
      }
    })();
    ```

    Total: ~85 lines. No build step, no minification.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; wc -l kb/static/lang.js</automated>
  </verify>
  <acceptance_criteria>
    - `kb/static/lang.js` exists with line count between 60 and 110
    - Contains exact strings: `kb_lang`, `COOKIE_MAX_AGE = 31536000`, `SameSite=Lax`, `data-fixed-lang`, `navigator.languages`, `URLSearchParams`
    - Contains the IIFE pattern: starts with `(function ()` and ends with `})();`
    - Contains EITHER `addEventListener('DOMContentLoaded'` OR has the document.readyState check
    - Does NOT contain `import ` (no ES6 modules — must work without bundler)
    - Does NOT contain `=>` arrow functions in code body (ES5 compat for old WeChat browsers; `function()` only)
    - Does NOT contain `let ` or `const ` outside comments (use `var`)
  </acceptance_criteria>
  <done>lang.js written, ES5-compatible, all 4 resolution paths implemented.</done>
</task>

</tasks>

<verification>
- `wc -l kb/static/style.css` reports ≥ 300 lines
- `wc -l kb/static/lang.js` reports between 60 and 110 lines
- `grep "googleapis\\|cdn\\." kb/static/style.css` returns 0 hits
</verification>

<success_criteria>
- UI-01 satisfied: 5 design-token CSS variables present
- UI-02 satisfied: Inter + Noto Sans SC font stack, no external font requests
- UI-03 satisfied: mobile-first @media queries at 768px and 1024px, body overflow-x hidden
- I18N-01 satisfied: Accept-Language detection in JS via navigator.languages
- I18N-02 satisfied: kb_lang cookie with 1-year max-age + ?lang= persistence
- I18N-08 satisfied: .lang-toggle binding cycles languages
- UI-04 (brand assets) NOT in this plan — see kb-1-04b-brand-assets-checkpoint-PLAN.md
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04-SUMMARY.md` documenting:
- style.css line count + section presence
- lang.js line count + ES5 compliance
- Note that UI-04 (brand assets) is delivered by kb-1-04b
</output>
