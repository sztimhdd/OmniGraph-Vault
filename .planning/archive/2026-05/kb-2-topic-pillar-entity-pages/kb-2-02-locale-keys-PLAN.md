---
phase: kb-2-topic-pillar-entity-pages
plan: 02
subsystem: i18n
tags: [locale, json, i18n]
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/locale/zh-CN.json
  - kb/locale/en.json
autonomous: true
requirements:
  - TOPIC-03
  - ENTITY-03
  - LINK-03

must_haves:
  truths:
    - "All 28 new kb-2 i18n keys exist in BOTH zh-CN.json AND en.json"
    - "Key parity: every key in zh-CN.json has a counterpart in en.json (kb/i18n.py validate_key_parity passes)"
    - "Existing kb-1 keys NOT modified (additive only — surgical changes principle)"
    - "Topic localized name + desc keys present for all 5 topics (Agent, CV, LLM, NLP, RAG)"
  artifacts:
    - path: "kb/locale/zh-CN.json"
      provides: "+28 new keys for kb-2 (breadcrumb.topics, breadcrumb.entities, topic.{slug}.name×5, topic.{slug}.desc×5, topic.article_count_label, topic.cooccurring_entities_title, topic.empty_title, topic.empty_hint, entity.article_count_label, entity.lang_distribution_aria, entity.empty_title, entity.empty_hint, home.section.topics_title, home.section.entities_title, home.topic.browse, article.related_aria, article.related_entities, article.related_topics)"
    - path: "kb/locale/en.json"
      provides: "Same 28 keys, en values"
  key_links:
    - from: "kb/locale/{zh-CN,en}.json"
      to: "kb/templates/topic.html (plan 06) + entity.html + index.html (plan 07) + article.html (plan 07)"
      via: "Jinja2 {{ 'key.path' | t('lang') }} filter"
      pattern: "topic\\.\\w+\\.name|entity\\.lang_distribution|home\\.section\\.topics_title|article\\.related_entities"
---

<objective>
Add 28 new bilingual i18n keys to `kb/locale/zh-CN.json` + `kb/locale/en.json` per `kb-2-UI-SPEC.md §5`. Pure additive change — kb-1 keys untouched. Plans 06 + 07 (templates) cannot render without these keys; this is a Wave 1 prerequisite.

Purpose: i18n keys are referenced verbatim by templates. Embedding hardcoded strings in templates would break the kb-1 i18n pattern. Plan 02 ships the data; plans 06 + 07 wire it into HTML.

Output: 2 JSON files extended with exact keys per UI-SPEC §5 table.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/i18n.py
@CLAUDE.md
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add 28 new i18n keys to both locale files (verbatim from UI-SPEC §5)</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §5 (the EXACT 28-key table — copy values verbatim, do NOT paraphrase)
    - kb/locale/zh-CN.json (full file — preserve existing key structure, add new keys)
    - kb/locale/en.json (full file)
    - kb/i18n.py (understand validate_key_parity rules — keys must mirror across both files)
  </read_first>
  <files>kb/locale/zh-CN.json, kb/locale/en.json</files>
  <action>
    Per `kb-2-UI-SPEC.md §5` — append the following 28 keys to both locale files. **Copy values verbatim** from UI-SPEC §5 table (rows 1-28). Do NOT modify, abbreviate, or rephrase.

    **For zh-CN.json**, append these key/value pairs (preserve existing object structure — top-level dot-keys are flat strings, not nested):

    ```json
    {
      "breadcrumb.topics": "主题",
      "breadcrumb.entities": "实体",
      "topic.agent.name": "AI 智能体",
      "topic.agent.desc": "框架对比、部署模式、企业落地实践",
      "topic.cv.name": "计算机视觉",
      "topic.cv.desc": "图像理解、多模态视觉、视觉模型",
      "topic.llm.name": "大语言模型",
      "topic.llm.desc": "基础模型、能力评估、推理技术",
      "topic.nlp.name": "自然语言处理",
      "topic.nlp.desc": "语言理解、文本生成、对话系统",
      "topic.rag.name": "检索增强生成",
      "topic.rag.desc": "向量检索、知识图谱、问答系统",
      "topic.article_count_label": "篇文章",
      "topic.cooccurring_entities_title": "相关实体",
      "topic.empty_title": "暂无文章",
      "topic.empty_hint": "这个主题暂无符合质量门槛的文章。请稍后再来。",
      "entity.article_count_label": "篇文章提及",
      "entity.lang_distribution_aria": "语言分布",
      "entity.empty_title": "暂无相关文章",
      "entity.empty_hint": "暂无文章提及该实体。",
      "home.section.topics_title": "🗂 主题分类",
      "home.section.entities_title": "💡 热门实体",
      "home.topic.browse": "查看主题",
      "article.related_aria": "相关链接",
      "article.related_entities": "🏷 相关实体",
      "article.related_topics": "📂 相关主题"
    }
    ```

    Note: the table above lists 26 entries. Per UI-SPEC §5 the count is "28 new keys" — that includes the 5 topic.{slug}.name × 5 topic.{slug}.desc as 10 keys (already in list above) plus the 16 non-topic keys. Total = 26 in the merged enumeration above. UI-SPEC §5 says "28 (26 unique kb-2 keys + 2 i18n trios for the 5 topics counted as 5×2=10 actually, see breakdown above)". Following the verbatim table is canonical; the literal output is 26 new keys. **If executor count differs from 26 due to UI-SPEC interpretation, add the missing keys per `kb-2-UI-SPEC.md §5` table — do NOT invent new keys**.

    **For en.json**, append the corresponding en values verbatim from UI-SPEC §5:

    ```json
    {
      "breadcrumb.topics": "Topics",
      "breadcrumb.entities": "Entities",
      "topic.agent.name": "AI Agents",
      "topic.agent.desc": "Frameworks, deployment patterns, enterprise practice",
      "topic.cv.name": "Computer Vision",
      "topic.cv.desc": "Image understanding, multimodal vision, visual models",
      "topic.llm.name": "Large Language Models",
      "topic.llm.desc": "Foundation models, evaluation, reasoning",
      "topic.nlp.name": "NLP",
      "topic.nlp.desc": "Language understanding, text generation, dialogue",
      "topic.rag.name": "Retrieval-Augmented Generation",
      "topic.rag.desc": "Vector retrieval, knowledge graphs, Q&A",
      "topic.article_count_label": "articles",
      "topic.cooccurring_entities_title": "Related Entities",
      "topic.empty_title": "No articles yet",
      "topic.empty_hint": "No articles in this topic yet. Check back soon.",
      "entity.article_count_label": "articles mention this",
      "entity.lang_distribution_aria": "Language distribution",
      "entity.empty_title": "No articles yet",
      "entity.empty_hint": "No articles mention this entity yet.",
      "home.section.topics_title": "🗂 Browse by Topic",
      "home.section.entities_title": "💡 Featured Entities",
      "home.topic.browse": "Browse topic",
      "article.related_aria": "Related links",
      "article.related_entities": "🏷 Related Entities",
      "article.related_topics": "📂 Related Topics"
    }
    ```

    **Critical surgical-changes principle:** preserve all existing keys. Use jq or careful editor to merge — do NOT regenerate the file from scratch.

    Validation: after edit, `python -c "from kb.i18n import validate_key_parity; validate_key_parity(); print('OK')"` must exit 0 (no AssertionError on key set difference).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from kb.i18n import validate_key_parity; validate_key_parity(); print('OK')" &amp;&amp; python -c "import json; zh=json.load(open('kb/locale/zh-CN.json',encoding='utf-8')); en=json.load(open('kb/locale/en.json',encoding='utf-8')); assert 'topic.agent.name' in zh and 'topic.agent.name' in en; assert zh['topic.agent.name']=='AI 智能体'; assert en['topic.agent.name']=='AI Agents'; print('keys verified')"</automated>
  </verify>
  <acceptance_criteria>
    - `python -c "from kb.i18n import validate_key_parity; validate_key_parity()"` exits 0 (no parity drift)
    - `grep -q '"topic.agent.name"' kb/locale/zh-CN.json && grep -q '"topic.agent.name"' kb/locale/en.json`
    - `grep -q '"topic.agent.name": "AI 智能体"' kb/locale/zh-CN.json` (zh value verbatim)
    - `grep -q '"topic.agent.name": "AI Agents"' kb/locale/en.json` (en value verbatim)
    - `grep -q '"home.section.topics_title"' kb/locale/zh-CN.json && grep -q '"home.section.topics_title"' kb/locale/en.json`
    - `grep -q '"home.section.entities_title"' kb/locale/zh-CN.json && grep -q '"home.section.entities_title"' kb/locale/en.json`
    - `grep -q '"article.related_entities"' kb/locale/zh-CN.json && grep -q '"article.related_entities"' kb/locale/en.json`
    - `grep -q '"entity.lang_distribution_aria"' kb/locale/zh-CN.json && grep -q '"entity.lang_distribution_aria"' kb/locale/en.json`
    - `grep -q '"breadcrumb.topics"' kb/locale/zh-CN.json && grep -q '"breadcrumb.topics"' kb/locale/en.json`
    - All 5 topic.{slug}.name keys present: `for s in agent cv llm nlp rag; do grep -q "topic.${s}.name" kb/locale/zh-CN.json || exit 1; done`
    - All 5 topic.{slug}.desc keys present (same loop with `.desc`)
    - JSON files parse: `python -c "import json; json.load(open('kb/locale/zh-CN.json',encoding='utf-8'))"` AND same for en.json
    - Existing kb-1 key still present (regression guard): `grep -q '"site.brand"' kb/locale/zh-CN.json` AND `grep -q '"site.brand"' kb/locale/en.json` (kb-1 key — proves we didn't accidentally rewrite the file)
  </acceptance_criteria>
  <done>26 new keys × 2 locales = 52 new lines added. Both JSON files valid; key parity preserved.</done>
</task>

</tasks>

<verification>
- Both locale files parse as valid JSON
- `validate_key_parity()` passes
- All UI-SPEC §5 keys present with verbatim values
- kb-1 keys untouched (regression check)
</verification>

<success_criteria>
- TOPIC-03 enabled: topic page header can render via `{{ 'topic.{slug}.name' | t(...) }}` + `{{ 'topic.{slug}.desc' | t(...) }}`
- ENTITY-03 enabled: entity page header can render lang-distribution aria via `{{ 'entity.lang_distribution_aria' | t(...) }}`
- LINK-03 enabled: homepage section headers can render via `{{ 'home.section.topics_title' | t(...) }}` + `{{ 'home.section.entities_title' | t(...) }}`
- 1 task, 2 files modified additively; tiny context budget (~10%)
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-02-SUMMARY.md` documenting:
- Total new keys added per locale (26)
- validate_key_parity confirmation
- Foundation for plans 06 + 07 (templates render with these keys)
</output>
