---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 06
type: execute
wave: 3
depends_on: ["kb-4-05"]  # local UAT must come first to surface runtime issues
files_modified:
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
  - .playwright-mcp/kb-4-smoke-*.png
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-06-SUMMARY.md
autonomous: false
requirements: [DEPLOY-05]
must_haves:
  truths:
    - "Smoke 1 (双语 UI 切换) — all 4 sub-steps PASS against actual local deploy"
    - "Smoke 2 (双语搜索 + 详情页) — all 5 sub-steps PASS against actual local deploy"
    - "Smoke 3 (RAG 问答双语 + 失败降级) — all 3 sub-steps PASS, including LightRAG-unavailable fallback path"
    - "Each sub-step has Playwright screenshot evidence + curl/console output"
  artifacts:
    - path: ".planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md"
      provides: "milestone gate evidence — 3 smoke scenarios PASS with verbatim sub-step text"
      min_lines: 80
    - path: ".playwright-mcp/kb-4-smoke-*.png"
      provides: "screenshot evidence per sub-step"
  key_links:
    - from: "kb-4-SMOKE-VERIFICATION.md"
      to: "PROJECT-KB-v2.md Smoke Test section"
      via: "verbatim quote of each scenario + sub-step"
      pattern: "Smoke 1.*双语 UI 切换"
---

<objective>
Run the 3 smoke scenarios defined verbatim in `PROJECT-KB-v2.md` "Smoke Test (acceptance criterion)" section against the actual local deployed service (NOT TestClient). This is the **milestone gate** — kb-4 cannot be marked complete unless all 3 scenarios PASS.

Special attention to Smoke 3 sub-step 3 (LightRAG-unavailable simulation) — flagged in ROADMAP as the most fragile, expect 1-2 plan-internal iterations on the fallback-trigger conditions.

Purpose: DEPLOY-05 + the implicit milestone gate. The 3 smoke scenarios ARE the v2.0 acceptance bar.
Output: `kb-4-SMOKE-VERIFICATION.md` with verbatim scenario text + step-by-step PASS/FAIL evidence + Playwright artifacts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/ROADMAP-KB-v2.md
@kb/docs/10-DESIGN-DISCIPLINE.md

@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md  (kb-4-05 — runtime verified)
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-VERIFICATION.md  (FTS5 fallback NEVER-500 invariant verified)
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md

<interfaces>
- 3 Smoke scenarios (verbatim from PROJECT-KB-v2.md):

  Smoke 1 — 双语 UI 切换:
  1. 浏览器 Accept-Language: zh-CN 访问首页 → 默认中文 UI
  2. 点击右上角语言切换 → 英文 UI 全站生效(nav / labels / buttons / footer 全英文)
  3. 刷新页面 → 偏好通过 cookie 持久化,仍英文 UI
  4. 访问 /?lang=zh → 硬切回中文,cookie 同步更新

  Smoke 2 — 双语搜索 + 详情页:
  1. 中文 UI 输入 "AI Agent 框架" → 返回 ≥3 条中文文章命中
  2. 英文 UI 输入 "langchain framework" → 返回 ≥3 条英文文章命中
  3. 点击任一英文文章 → 详情页 <html lang="en"> + 标 "English" badge + 内容原文(英文)
  4. 点击任一中文文章 → 详情页 <html lang="zh-CN"> + 标 "中文" badge + 内容原文(中文)
  5. 详情页底部 og:image / og:title metadata 正确(分享到 IM 群里有预览)

  Smoke 3 — RAG 问答双语 + 失败降级:
  1. 中文输入 "LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown 答复 + 来源链接
  2. 英文输入 "What is the difference between LangGraph and CrewAI?" → 异步 → 英文 markdown 答复 + 来源链接
  3. 模拟 LightRAG 不可用(stop kg backend or block storage path) → /synthesize 降级返回 FTS5 top-3 摘要拼接 + confidence: "fts5_fallback" 标记,不 500
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Smoke 1 — 双语 UI 切换 (4 sub-steps)</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
    .playwright-mcp/kb-4-smoke-1-*.png
  </files>
  <read_first>
    - .scratch/local_serve.py (assume running from kb-4-05; if not, restart)
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
  </read_first>
  <action>
    Quote Smoke 1 verbatim into `kb-4-SMOKE-VERIFICATION.md` "## Smoke 1 — 双语 UI 切换" section.

    Use Playwright MCP to execute each sub-step and capture screenshot:

    **Sub-step 1.1**: Accept-Language: zh-CN → 默认中文 UI
    - Set extra HTTP header `Accept-Language: zh-CN` (use `browser_evaluate` or browser_run_code_unsafe to set context)
    - Navigate to http://localhost:8766/
    - Capture screenshot kb-4-smoke-1-1.png
    - Verify: nav text in zh-CN ("首页", "文章", "AI 问答" or per kb-1 i18n keys)
    - Verify: cookie `kb_lang=zh-CN` set (use browser_evaluate `document.cookie`)

    **Sub-step 1.2**: 点击语言切换 → 英文 UI 全站生效
    - Click the lang toggle button (selector per kb-1-UI-SPEC §3.1 nav)
    - Wait for page reload / state change
    - Capture screenshot kb-4-smoke-1-2.png
    - Verify: nav text in English ("Home", "Articles", "Ask AI")
    - Verify footer + buttons + labels also flipped (sample 3+ strings)

    **Sub-step 1.3**: 刷新页面 → 仍英文 UI (cookie 持久化)
    - browser_navigate(url=current_url) (forces refresh; or use F5 via browser_press_key)
    - Capture kb-4-smoke-1-3.png
    - Verify: still English UI; cookie `kb_lang=en` still set

    **Sub-step 1.4**: 访问 /?lang=zh → 硬切回中文 + cookie 同步更新
    - browser_navigate(url="http://localhost:8766/?lang=zh")
    - Capture kb-4-smoke-1-4.png
    - Verify: chrome flips to zh-CN
    - Verify: cookie now `kb_lang=zh-CN` (硬切 wrote cookie)

    For each sub-step, append to kb-4-SMOKE-VERIFICATION.md:

    ```markdown
    ### 1.1 — 浏览器 Accept-Language: zh-CN 访问首页 → 默认中文 UI

    **Status:** PASS / FAIL
    **Screenshot:** `.playwright-mcp/kb-4-smoke-1-1.png`
    **Evidence:**
    - Cookie set: `kb_lang=zh-CN`
    - Nav strings observed: 首页 / 文章 / AI 问答
    - Footer string sample: <quote 1-2 strings>

    [Description of any deviation, or 'fully PASS']
    ```

    If any sub-step FAILs, halt smoke and surface as Issue (do NOT continue painting over a failure). Disposition options:
    - In-scope hot fix (small contract drift) — fix + retest
    - Halt + reopen kb-1 / kb-3 (architectural)

    Final Smoke 1 verdict at end of section: PASS (4/4) or FAIL (counts).
  </action>
  <verify>
    <automated>
      grep '## Smoke 1 — 双语 UI 切换' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep '### 1.1' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep '### 1.4' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      ls .playwright-mcp/kb-4-smoke-1-*.png | wc -l  # ≥4
    </automated>
  </verify>
  <done>
    - All 4 sub-steps documented with screenshot + evidence + status
    - Final verdict line: "Smoke 1 verdict: PASS 4/4" (or FAIL with details)
  </done>
</task>

<task type="auto">
  <name>Task 2: Smoke 2 — 双语搜索 + 详情页 (5 sub-steps)</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md  (extend with Smoke 2 section)
    .playwright-mcp/kb-4-smoke-2-*.png
  </files>
  <action>
    Quote Smoke 2 verbatim. Execute each sub-step:

    **Sub-step 2.1**: 中文 UI 输入 "AI Agent 框架" → ≥3 条中文文章命中
    - Set lang=zh-CN (via cookie or ?lang=zh)
    - Navigate /articles/ (or /), focus search input, type "AI Agent 框架"
    - Wait for inline search reveal (per kb-3-UI-SPEC search inline pattern)
    - Capture kb-4-smoke-2-1.png
    - Count visible result cards; assert ≥3 with `lang="zh-CN"` chip

    **Sub-step 2.2**: 英文 UI 输入 "langchain framework" → ≥3 条英文文章命中
    - Switch lang=en
    - Type "langchain framework" in search
    - Capture kb-4-smoke-2-2.png
    - Count visible result cards; assert ≥3 with `lang="en"` chip

    **Sub-step 2.3**: 点击英文文章 → 详情页 <html lang="en"> + English badge + 英文原文
    - Click first English result
    - Capture kb-4-smoke-2-3.png
    - Verify via browser_evaluate: `document.documentElement.lang === 'en'`
    - Verify badge element renders with text "English" (per I18N-06)
    - Verify article body is English content (sample first paragraph)

    **Sub-step 2.4**: 点击中文文章 → 详情页 <html lang="zh-CN"> + 中文 badge + 中文原文
    - Same flow with a zh article
    - Capture kb-4-smoke-2-4.png
    - Same checks but for zh-CN

    **Sub-step 2.5**: 详情页 og:image / og:title metadata 正确
    - On article detail page, browser_evaluate to read meta tags:
      ```js
      ({
        og_title: document.querySelector('meta[property="og:title"]')?.content,
        og_description: document.querySelector('meta[property="og:description"]')?.content,
        og_image: document.querySelector('meta[property="og:image"]')?.content,
        og_type: document.querySelector('meta[property="og:type"]')?.content,
        og_locale: document.querySelector('meta[property="og:locale"]')?.content,
      })
      ```
    - Verify all 5 og:* tags present + non-empty + locale matches `<html lang>` (per UI-05)
    - Capture kb-4-smoke-2-5.png (page source view or rendered)

    Append per-sub-step markdown blocks. Final verdict: Smoke 2 PASS 5/5 or FAIL.
  </action>
  <verify>
    <automated>
      grep '## Smoke 2 — 双语搜索' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep '### 2.5' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      ls .playwright-mcp/kb-4-smoke-2-*.png | wc -l  # ≥5
    </automated>
  </verify>
  <done>
    - All 5 sub-steps documented with screenshot + evidence
    - Final verdict line: "Smoke 2 verdict: PASS 5/5"
  </done>
</task>

<task type="auto">
  <name>Task 3: Smoke 3 — RAG 问答双语 + 失败降级 (3 sub-steps, fragile)</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md  (extend with Smoke 3 section)
    .playwright-mcp/kb-4-smoke-3-*.png
  </files>
  <read_first>
    - kb/services/synthesize.py (verify timeout + fallback trigger conditions)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-09-fts5-fallback-PLAN.md (NEVER-500 invariant)
  </read_first>
  <action>
    Quote Smoke 3 verbatim. Execute:

    **Sub-step 3.1**: 中文 query "LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown + 来源
    - Navigate /ask/ with lang=zh
    - Type the question, click submit
    - Capture kb-4-smoke-3-1-submitting.png
    - Poll job status (state machine: idle → submitting → polling → done OR fts5_fallback)
    - When done, capture kb-4-smoke-3-1-done.png
    - Verify: result.markdown contains Chinese characters (`re.search(r'[一-鿿]', markdown)`)
    - Verify: sources list non-empty
    - Verify: confidence is "kg" (real LightRAG path) OR "fts5_fallback" (note + continue — fallback is acceptable as long as content is Chinese per I18N-07)

    **Sub-step 3.2**: 英文 query "What is the difference between LangGraph and CrewAI?" → English markdown + 来源
    - Same flow with lang=en
    - Capture kb-4-smoke-3-2-done.png
    - Verify: result.markdown is primarily ASCII (English)
    - Verify: sources non-empty

    **Sub-step 3.3** (FRAGILE — expect iteration): 模拟 LightRAG 不可用 → fallback FTS5 top-3 + `confidence: "fts5_fallback"` + NOT 500

    Multiple ways to simulate LightRAG unavailability — choose the cleanest:

    Option A — block storage path:
    ```bash
    # Rename the LightRAG storage dir to make it unreachable, then restore after
    mv ~/.hermes/omonigraph-vault/lightrag_storage ~/.hermes/omonigraph-vault/lightrag_storage.smoke3-disabled
    # → kg_synthesize will raise on missing path → wrapper triggers fts5_fallback
    ```

    Option B — set timeout very short:
    ```bash
    export KB_SYNTHESIZE_TIMEOUT=1  # 1 second — kg_synthesize won't finish
    # restart local_serve.py with this env
    ```

    Option C — patch via env (if kb-3-09 added a debug toggle like KB_FORCE_FTS5_FALLBACK=true):
    ```bash
    grep -E 'KB_FORCE.*FALLBACK\|KB_DISABLE_KG' kb/services/synthesize.py kb/config.py
    # if present, use it; else proceed with A or B
    ```

    Pick the option that best matches kb-3-09's design. Document choice + rationale in SMOKE-VERIFICATION.

    Then:
    - POST /api/synthesize with same English question
    - Poll until done
    - Verify response shape: `{status: "done", confidence: "fts5_fallback", fallback_used: true, result.markdown: <non-empty>}`
    - Verify HTTP status code throughout polling: ALWAYS 2xx, NEVER 500
    - Capture kb-4-smoke-3-3-fallback.png (showing fallback chip per kb-3-UI-SPEC §3.1)

    **Restore** LightRAG state after sub-step 3.3:
    ```bash
    # Option A:
    mv ~/.hermes/omonigraph-vault/lightrag_storage.smoke3-disabled ~/.hermes/omonigraph-vault/lightrag_storage
    # Option B: unset KB_SYNTHESIZE_TIMEOUT and restart
    ```

    Document restoration step explicitly in the verification doc — incomplete restoration is the kind of bug that bites operators.

    Final verdict: Smoke 3 PASS 3/3 or FAIL.

    **If sub-step 3.3 fails** (e.g., 500 returned, confidence not 'fts5_fallback', timeout too short and 3.2 also broken):
    - Investigate kb/services/synthesize.py timeout/exception handling
    - This is the iteration loop ROADMAP warned about (kb-4 success criterion #5 sub-3)
    - Document iteration in SMOKE-VERIFICATION (don't hide failed attempts)
    - Either hot-fix in scope OR escalate to user/orchestrator with failure details
  </action>
  <verify>
    <automated>
      grep '## Smoke 3 — RAG 问答双语' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep '### 3.1' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep '### 3.3' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep -E 'fts5_fallback' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      grep -E 'NEVER 500\|never returns 500\|status code.*2xx' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
      ls .playwright-mcp/kb-4-smoke-3-*.png | wc -l  # ≥3
      grep -E 'Restoration\|restored\|restore' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md  # explicit restore step
    </automated>
  </verify>
  <done>
    - All 3 sub-steps documented with screenshots
    - Sub-step 3.3 LightRAG-unavailable simulation method documented + restoration explicit
    - Final verdict line: "Smoke 3 verdict: PASS 3/3"
    - If FAIL: iteration log + disposition (hot-fix vs escalate)
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4 (CHECKPOINT): User reviews 3-scenario smoke evidence + signs off</name>
  <what-built>
    - kb-4-SMOKE-VERIFICATION.md with all 3 scenarios + 12 sub-step entries + 12+ screenshots
    - All sub-steps either PASS or have documented disposition
  </what-built>
  <how-to-verify>
    1. Open kb-4-SMOKE-VERIFICATION.md — confirm all 3 scenarios verbatim quoted from PROJECT-KB-v2.md
    2. Verify final verdicts: Smoke 1 = 4/4, Smoke 2 = 5/5, Smoke 3 = 3/3
    3. Spot-check 2-3 screenshots in .playwright-mcp/kb-4-smoke-*.png
    4. Confirm Smoke 3 sub-step 3.3 LightRAG-unavailable was actually simulated (not skipped) AND restoration was completed
    5. Type 'approved' to mark milestone gate satisfied; or describe issues
  </how-to-verify>
  <resume-signal>'approved' or 'fix: <specific sub-step>'</resume-signal>
</task>

</tasks>

<verification>
- 3 smoke scenarios verbatim documented + executed against actual local deploy
- 12 sub-steps total: 4 + 5 + 3
- ≥12 Playwright screenshots
- DEPLOY-05 satisfied via "all 3 scenarios PASS on same-host deploy"
- ROADMAP success criterion #5 satisfied (the milestone gate)
</verification>

<success_criteria>
- DEPLOY-05: same-host deploy PASS
- All 3 smoke scenarios PASS — the milestone close gate
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-06-SUMMARY.md` + `kb-4-SMOKE-VERIFICATION.md`
</output>
