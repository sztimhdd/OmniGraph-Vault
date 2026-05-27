---
phase: kb-1-ssg-export-i18n-foundation
plan: 04b
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/static/VitaClaw-Logo-v0.png
  - kb/static/favicon.svg
  - kb/static/README.md
autonomous: false
requirements:
  - UI-04

must_haves:
  truths:
    - "kb/static/favicon.svg exists (real vitaclaw-site asset OR documented placeholder SVG)"
    - "kb/static/VitaClaw-Logo-v0.png exists OR kb/static/VitaClaw-Logo-v0.png.MISSING.txt documents the gap"
    - "kb/static/README.md documents asset provenance + whether kb-4 deploy needs real assets"
    - "User has signed off on real-vs-placeholder choice via resume signal"
  artifacts:
    - path: "kb/static/favicon.svg"
      provides: "Brand favicon (vitaclaw-site reuse OR placeholder)"
    - path: "kb/static/README.md"
      provides: "Asset provenance documentation"
  key_links:
    - from: "kb/templates/base.html (later plan)"
      to: "/static/VitaClaw-Logo-v0.png + /static/favicon.svg"
      via: "<img src=...> and <link rel=icon>"
      pattern: "VitaClaw-Logo-v0\\.png|favicon\\.svg"
---

<objective>
Source brand assets (logo + favicon) for the SSG. Either copy real assets from the vitaclaw-site sibling repo, or generate a documented placeholder SVG favicon and a `.MISSING.txt` stub for the logo. User confirms which path is acceptable for this milestone via a checkpoint resume signal.

**REVISION 1 (2026-05-12) — New plan:** extracted from former kb-1-04 Task 3 per Issue #4. The original plan mixed fully-autonomous CSS/JS work with this human-checkpoint asset-sourcing task, forcing the entire plan to be `autonomous: false`. Splitting allows kb-1-04 (Tasks 1+2: style.css + lang.js) to run autonomously in Wave 1, and this plan handles only the brand-asset checkpoint (also Wave 1, no dependencies — runs in parallel with kb-1-04).

Purpose: UI-04 requires VitaClaw branding present in `kb/static/`. Templates in plans kb-1-07 and kb-1-08 reference `/static/VitaClaw-Logo-v0.png` and `/static/favicon.svg`. The CHECKPOINT exists because vitaclaw-site sibling repo location is uncertain — the Claude executor cannot autonomously decide whether to commit a placeholder or wait for real assets without user input.

Output: Two brand asset files (real or placeholder) + README.md documenting provenance.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@kb/docs/09-AGENT-QA-HANDBOOK.md
@CLAUDE.md

<interfaces>
File targets:

- `kb/static/VitaClaw-Logo-v0.png` — referenced by templates as `<img src="/static/VitaClaw-Logo-v0.png">` in base.html nav (kb-1-07)
- `kb/static/favicon.svg` — referenced by templates as `<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">` in base.html `<head>` (kb-1-07)

Source candidates (in order of preference):

1. `../vitaclaw-site/public/` (relative path from OmniGraph-Vault repo)
2. `C:/Users/huxxha/Desktop/vitaclaw-site/public/`
3. `~/vitaclaw-site/public/` (Linux/Hermes path; not applicable for local Windows dev but documented for future deploy)

Placeholder favicon SVG (if no real asset found) — exact content to write:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect width="24" height="24" fill="#0f172a"/>
  <text x="12" y="16" font-family="sans-serif" font-size="10" font-weight="bold" fill="#f0f4f8" text-anchor="middle">VC</text>
</svg>
```

Templates already include `onerror="this.style.display='none'"` on `<img>` so a missing PNG degrades gracefully — the placeholder favicon SVG is the only mandatory asset for visual completeness.
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1 (CHECKPOINT): Brand assets — copy from vitaclaw-site OR generate placeholder</name>
  <read_first>
    - kb/docs/09-AGENT-QA-HANDBOOK.md V-3 (vitaclaw-site asset reuse decision)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Brand asset strategy (UI-04)"
  </read_first>
  <files>kb/static/VitaClaw-Logo-v0.png, kb/static/favicon.svg, kb/static/README.md</files>
  <action>
    The Claude executor MUST attempt the following automated approaches BEFORE pausing for human verification.

    **Tooling note:** the executor uses the **Bash tool** for shell commands. Bash on Windows runs Git Bash which provides Unix utilities (`cp`, `ls`, `file`) natively — the commands below work as-is. PowerShell equivalents are listed in comments for operator reference if running checks manually outside the executor.

    1. **Check sibling repo locations** for `VitaClaw-Logo-v0.png` and `favicon.svg`:

       ```bash
       # Bash (executor's default for shell commands):
       ls ../vitaclaw-site/public/ 2>/dev/null
       ls C:/Users/huxxha/Desktop/vitaclaw-site/public/ 2>/dev/null

       # PowerShell equivalent (operator reference only):
       #   Get-ChildItem ../vitaclaw-site/public/ -ErrorAction SilentlyContinue
       #   Get-ChildItem C:/Users/huxxha/Desktop/vitaclaw-site/public/ -ErrorAction SilentlyContinue
       ```

       If found, copy via:

       ```bash
       # Bash:
       cp ../vitaclaw-site/public/VitaClaw-Logo-v0.png kb/static/
       cp ../vitaclaw-site/public/favicon.svg kb/static/

       # PowerShell equivalent:
       #   Copy-Item ../vitaclaw-site/public/VitaClaw-Logo-v0.png kb/static/
       #   Copy-Item ../vitaclaw-site/public/favicon.svg kb/static/
       ```

    2. **If sibling repo not present**, generate a SVG placeholder favicon at `kb/static/favicon.svg` using the Write tool with EXACTLY this content:

       ```xml
       <?xml version="1.0" encoding="UTF-8"?>
       <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
         <rect width="24" height="24" fill="#0f172a"/>
         <text x="12" y="16" font-family="sans-serif" font-size="10" font-weight="bold" fill="#f0f4f8" text-anchor="middle">VC</text>
       </svg>
       ```

    3. **For the logo**, if sibling repo absent, write `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` (use Write tool) with a note explaining the gap and that templates degrade gracefully via `onerror="this.style.display='none'"`. Do NOT generate a placeholder PNG.

    4. **Always write `kb/static/README.md`** (use Write tool) documenting:
        - Whether each asset is real (copied from vitaclaw-site) or placeholder
        - Path to the canonical source (vitaclaw-site sibling repo) for future re-sync
        - Whether human action is needed before kb-4 deploy (real PNG required if v2.0 launches publicly)

    After automation: PAUSE for human to verify visually. Showing the favicon.svg open in a browser is the verification step.
  </action>
  <what-built>
    Brand asset files now exist in kb/static/ — either real assets copied from vitaclaw-site, or a placeholder favicon.svg with documented "missing" stub for the logo. README.md documents which path was taken.
  </what-built>
  <how-to-verify>
    1. Run: `ls -la kb/static/` (Bash) OR `Get-ChildItem kb/static/` (PowerShell) — confirm `VitaClaw-Logo-v0.png` (or `.MISSING.txt`) AND `favicon.svg` AND `README.md` exist.
    2. Open `kb/static/favicon.svg` in a browser (drag-drop the file). It should render as some SVG (real logo OR a "VC" placeholder).
    3. Read `kb/static/README.md` — confirm it states whether assets are real or placeholder, and what the next step is.
    4. If real vitaclaw-site assets were copied: `file kb/static/VitaClaw-Logo-v0.png` (Bash) should report `PNG image data`. PowerShell equivalent: `Get-Item kb/static/VitaClaw-Logo-v0.png | Select-Object Length, Name` (a real PNG should be > 1 KB).
    5. If `VitaClaw-Logo-v0.png.MISSING.txt` exists instead, the user must decide:
        - (a) copy real assets manually now
        - (b) accept placeholder and proceed (kb-4 may need real assets before public launch)

    Decide which path is acceptable for this milestone:
    - If real assets present: type "approved" — proceed.
    - If placeholders only: type "approved-placeholder" — note in SUMMARY that real assets are a kb-4 prerequisite.
    - If you want to source the assets yourself first: type "pause-for-asset-sourcing &lt;path&gt;" with the path to copy from.
  </how-to-verify>
  <resume-signal>Type "approved" / "approved-placeholder" / "pause-for-asset-sourcing &lt;path&gt;"</resume-signal>
  <acceptance_criteria>
    - Files exist: `kb/static/favicon.svg` AND (`kb/static/VitaClaw-Logo-v0.png` OR `kb/static/VitaClaw-Logo-v0.png.MISSING.txt`)
    - `kb/static/README.md` exists and contains the words `placeholder` OR `vitaclaw-site` (documenting source)
    - User has provided one of the listed resume signals
  </acceptance_criteria>
  <done>Brand assets present (real or placeholder) + README.md documents provenance + user signed off.</done>
</task>

</tasks>

<verification>
- `ls kb/static/favicon.svg` succeeds (or PowerShell equivalent)
- `ls kb/static/README.md` succeeds
- Either `kb/static/VitaClaw-Logo-v0.png` or `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` exists
- README.md mentions provenance (real vs placeholder)
</verification>

<success_criteria>
- UI-04 satisfied: brand assets (or documented stubs) present in kb/static/
- User has explicitly signed off on real-vs-placeholder choice
- Downstream plans kb-1-07 (base template) and kb-1-08 (article detail) can reference `/static/VitaClaw-Logo-v0.png` and `/static/favicon.svg` without missing-asset errors
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04b-SUMMARY.md` documenting:
- Whether real vitaclaw-site assets were copied OR placeholder generated
- README.md content summary
- Whether kb-4 deploy needs real assets before launch
- User resume-signal received
</output>
