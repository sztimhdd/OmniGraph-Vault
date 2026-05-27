---
phase: kb-2-topic-pillar-entity-pages
plan: 03
subsystem: ui-icons
tags: [svg, jinja2-macro, ui]
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/templates/_icons.html
autonomous: true
requirements:
  - TOPIC-05
  - LINK-02
  - LINK-03

must_haves:
  truths:
    - "`folder-tag` icon clause exists in _icons.html macro"
    - "`users` icon clause exists in _icons.html macro"
    - "Both icons follow kb-1 SVG contract: 24×24 viewBox, currentColor stroke, 1.5px stroke-width, fill=none"
    - "Existing kb-1 icons NOT modified (additive only — surgical changes principle)"
  artifacts:
    - path: "kb/templates/_icons.html"
      provides: "+2 icon clauses appended to existing macro"
      contains: "name == 'folder-tag', name == 'users'"
  key_links:
    - from: "kb/templates/_icons.html"
      to: "kb/templates/topic.html (plan 06: uses 'users' for sidebar header) + article.html (plan 07: uses 'folder-tag' for related-topics) + index.html (plan 07: uses 'folder-tag' for Browse by Topic section)"
      via: "{{ icon('folder-tag', size=20) }} / {{ icon('users', size=16) }} macro calls"
      pattern: "icon\\('(folder-tag|users)'"
---

<objective>
Add 2 new SVG icon clauses to the existing `kb/templates/_icons.html` Jinja2 macro per `kb-2-UI-SPEC.md §3.5`. Pure additive change — kb-1 icons untouched. Plans 06 + 07 use these icons in template render; this is a Wave 1 prerequisite.

Purpose: kb-1 ships 19 icon clauses (`home`, `articles`, `chevron-right`, `arrow-right`, `search`, `wechat`, `rss`, `web`, `inbox`, `globe-alt`, `fire`, `thumb-up`, `thumb-down`, `sources`, `tag`, `warning`, `clock`, `sparkle`, `ask`). kb-2 adds 2: `folder-tag` (Browse by Topic + related-topic chips) and `users` (topic page sidebar "Related Entities" header).

Output: `kb/templates/_icons.html` with 2 new `{%- elif name == ... -%}` clauses. SVG path data verbatim from UI-SPEC §3.5 table.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@kb/templates/_icons.html
@CLAUDE.md
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Append folder-tag + users icon clauses to _icons.html macro</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.5 (verbatim SVG paths — copy do not paraphrase)
    - kb/templates/_icons.html (full file — observe existing macro structure: `{%- elif name == 'X' -%} <path d="..."/> {%- elif ... %}`)
  </read_first>
  <files>kb/templates/_icons.html</files>
  <action>
    Locate the existing Jinja2 macro `icon(name, size, cls)` body in `kb/templates/_icons.html`. The macro is a chain of `{%- elif name == 'X' -%}` clauses, ending with a final `{%- endif -%}` and `</svg>`. Insert the two new clauses BEFORE the final `{%- endif -%}` (so they slot in like every existing icon).

    Per UI-SPEC §3.5 table, append exactly:

    ```jinja2
    {%- elif name == 'folder-tag' -%}
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
      <path d="M9 12h7M9 15h5"/>
    {%- elif name == 'users' -%}
      <circle cx="9" cy="8" r="3.5"/>
      <path d="M3 20a6 6 0 0 1 12 0"/>
      <circle cx="17" cy="9" r="2.5"/>
      <path d="M16 14h2a3 3 0 0 1 3 3v2"/>
    ```

    SVG paths are verbatim from UI-SPEC §3.5. Do NOT modify coordinates, viewBox, or stroke values — they are part of the ratified design contract.

    Surgical-changes principle: the file must be IDENTICAL except for the 2 new clauses inserted in the macro. Do NOT reformat the existing 19 clauses, do NOT change indentation of unrelated lines, do NOT touch the macro signature or `</svg>` close.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); tpl = env.get_template('_icons.html'); ns = tpl.module; html = ns.icon('folder-tag', 16); assert '&lt;svg' in html, 'svg open tag missing'; assert 'M3 7a2 2 0 0 1 2-2h4' in html, 'folder-tag path missing'; html2 = ns.icon('users', 16); assert 'circle cx=&quot;9&quot;' in html2, 'users circle missing'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "name == 'folder-tag'" kb/templates/_icons.html`
    - `grep -q "name == 'users'" kb/templates/_icons.html`
    - `grep -q "M3 7a2 2 0 0 1 2-2h4" kb/templates/_icons.html` (folder-tag main path verbatim)
    - `grep -q 'circle cx="9" cy="8" r="3.5"' kb/templates/_icons.html` (users first circle verbatim)
    - Macro renders without error: verify command above exits 0
    - Existing icons not regressed: `grep -q "name == 'home'" kb/templates/_icons.html && grep -q "name == 'sparkle'" kb/templates/_icons.html`
    - File is parseable Jinja2: `python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('kb/templates')).get_template('_icons.html')"` exits 0
  </acceptance_criteria>
  <done>2 new icon clauses appended; macro renders both `folder-tag` and `users`; kb-1 icons untouched.</done>
</task>

</tasks>

<verification>
- _icons.html macro renders both new icon names without error
- Both clauses present per UI-SPEC §3.5 verbatim
- File still parseable Jinja2; existing 19 icons still work
</verification>

<success_criteria>
- TOPIC-05 enabled: topic page sidebar header can render `{{ icon('users', size=16) }}` per UI-SPEC §3.1
- LINK-02 enabled: article.html related-topics chip can render `{{ icon('folder-tag', size=12) }}` per UI-SPEC §3.4
- LINK-03 enabled: homepage Browse by Topic section header can render `{{ icon('folder-tag', size=20) }}` per UI-SPEC §3.3.1
- 1 task, 1 file extended; trivial context budget
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-03-SUMMARY.md` documenting:
- 2 new icon clauses appended (folder-tag, users)
- Verbatim from UI-SPEC §3.5
- Foundation for plans 06 + 07 (templates can `{{ icon(...) }}` these names)
</output>
