---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/static/VitaClaw-Logo-v0.png
  - kb/static/VitaClaw-Logo-v0.png.MISSING.txt
  - kb/static/README.md
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-03-SUMMARY.md
autonomous: false
requirements: [UI-04]
must_haves:
  truths:
    - "kb/static/VitaClaw-Logo-v0.png exists as a real binary PNG (not a text stub)"
    - "PNG dimensions ≥ 256×256 px (verified via PIL Image.open)"
    - "PNG renders correctly in <img src='/static/VitaClaw-Logo-v0.png'> (browser smoke or Playwright)"
    - "kb/static/VitaClaw-Logo-v0.png.MISSING.txt is removed"
    - "kb/static/README.md updated to reflect logo provenance"
  artifacts:
    - path: "kb/static/VitaClaw-Logo-v0.png"
      provides: "real branded PNG logo for nav"
      file_type: "PNG (image/png)"
    - path: "kb/static/README.md"
      provides: "asset provenance + sourcing documentation"
  key_links:
    - from: "kb/templates/base.html"
      to: "kb/static/VitaClaw-Logo-v0.png"
      via: "<img src='/static/VitaClaw-Logo-v0.png' onerror='this.style.display=none'>"
      pattern: "VitaClaw-Logo-v0.png"
---

<objective>
Close the UI-04 carry-forward gate from kb-1 + kb-1-04b: source a real `VitaClaw-Logo-v0.png` (≥ 256×256 px) and place it at `kb/static/VitaClaw-Logo-v0.png`, removing the `.MISSING.txt` stub.

This is a **checkpoint task** because sourcing the PNG requires a decision the user/operator must make: (a) pull from `vitaclaw-site` sibling repo, (b) commission generation (logo gen tool / designer), or (c) accept a temporary placeholder PNG and document the gap.

Purpose: UI-04 (carry-forward from kb-1; documented in `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` as kb-4 prerequisite).
Output: Real PNG file at `kb/static/VitaClaw-Logo-v0.png` + provenance note in README.md + SUMMARY documenting which sourcing path was taken.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@kb/static/VitaClaw-Logo-v0.png.MISSING.txt
@kb/static/README.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04b-brand-assets-checkpoint-PLAN.md
@.planning/PROJECT-KB-v2.md

<interfaces>
- UI-04 (REQUIREMENTS-KB-v2.md): Brand assets reused from vitaclaw-site (logo `VitaClaw-Logo-v0.png` in nav, `favicon.svg`).
- kb-1-04b shipped favicon.svg as an SVG placeholder + accepted .MISSING.txt for the PNG, deferring to kb-4.
- base.html references logo with `onerror="this.style.display='none'"` — graceful degradation works today.
- Real PNG required for kb-4 public deploy (per .MISSING.txt comment).
</interfaces>
</context>

<tasks>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 1 (CHECKPOINT): Choose logo sourcing path</name>
  <decision>How to source `kb/static/VitaClaw-Logo-v0.png` for public deploy</decision>
  <context>
    The vitaclaw-site sibling repo was NOT present locally at any of the candidate paths checked at kb-1-04b time:
    - ../vitaclaw-site/public/  (not found)
    - C:/Users/huxxha/Desktop/vitaclaw-site/public/  (not found)
    - ~/vitaclaw-site/public/  (Linux/Hermes — N/A locally)

    Three viable paths to source the real PNG. Each has tradeoffs:
  </context>
  <options>
    <option id="option-a">
      <name>Pull from vitaclaw-site repo (Hermes-side)</name>
      <pros>
        - Authentic vitaclaw brand asset (the design intent of UI-04)
        - One-time copy, never need to commission again
        - User likely has access to vitaclaw-site source on Hermes prod (where vitaclaw deploys)
      </pros>
      <cons>
        - Requires user to scp the file from vitaclaw-site Hermes path → local repo
        - If vitaclaw-site doesn't have a v0 PNG (it's a site repo not an asset repo), this option fails
        - Needs SSH coordination
      </cons>
      <action_if_chosen>
        User scp's the PNG from vitaclaw-site (or any other authoritative source) to:
        C:\Users\huxxha\Desktop\OmniGraph-Vault\kb\static\VitaClaw-Logo-v0.png
        Then resume this plan to verify dimensions + remove .MISSING.txt + commit.
      </action_if_chosen>
    </option>
    <option id="option-b">
      <name>Commission/generate a placeholder logo (e.g., text-based PNG)</name>
      <pros>
        - Self-contained — no external coordination needed
        - PIL can generate a minimal "VitaClaw" text-on-dark-bg PNG meeting ≥256×256 dimension requirement
        - Unblocks kb-4 deploy without dependency on vitaclaw-site
      </pros>
      <cons>
        - Not the real brand asset (UI-04 says "reused from vitaclaw-site")
        - Likely needs a follow-up swap when real asset becomes available
        - "Commission" implies designer involvement which is out of GSD scope
      </cons>
      <action_if_chosen>
        Generate a 512×512 dark-bg PNG with "VitaClaw / 企小勤" text using PIL (Pillow already in requirements.txt). Save to kb/static/VitaClaw-Logo-v0.png. Document as "interim placeholder pending vitaclaw-site PNG source".
      </action_if_chosen>
    </option>
    <option id="option-c">
      <name>Accept current state (text-fallback only) + document explicit operator override path</name>
      <pros>
        - Zero work; base.html `onerror` handler already silently hides missing image
        - Defers asset sourcing to actual deploy operator with no GSD-side blocker
      </pros>
      <cons>
        - UI-04 stays "partial" — kb-4 phase cannot mark UI-04 fully satisfied
        - Site nav shows no logo until operator manually drops the file in
        - Risk: kb-4 declared complete but UI-04 still pending
      </cons>
      <action_if_chosen>
        Update kb/static/VitaClaw-Logo-v0.png.MISSING.txt with explicit operator-override instructions and a v2.0 deploy checklist item. UI-04 stays "carry-forward to operator deploy".
      </action_if_chosen>
    </option>
  </options>
  <resume-signal>Type: option-a / option-b / option-c</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Apply chosen sourcing path + verify PNG validity</name>
  <files>
    kb/static/VitaClaw-Logo-v0.png
    kb/static/VitaClaw-Logo-v0.png.MISSING.txt
    kb/static/README.md
  </files>
  <read_first>
    - kb/static/README.md (existing provenance doc)
    - kb/static/VitaClaw-Logo-v0.png.MISSING.txt
  </read_first>
  <action>
    Based on Task 1 decision:

    **If option-a (pull from vitaclaw-site)**:
    - User scp's the PNG to kb/static/VitaClaw-Logo-v0.png
    - Run: `python -c "from PIL import Image; im = Image.open('kb/static/VitaClaw-Logo-v0.png'); print(im.size, im.mode, im.format)"`
    - Verify size ≥ 256×256, format == 'PNG'
    - Delete kb/static/VitaClaw-Logo-v0.png.MISSING.txt
    - Update kb/static/README.md with provenance: "Sourced from vitaclaw-site at <hash> on <date>"

    **If option-b (PIL generated placeholder)**:
    Create the PNG via PIL:
    ```python
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGBA', (512, 512), color=(15, 23, 42, 255))  # #0f172a (kb-1 --bg)
    draw = ImageDraw.Draw(img)
    # Centered text "VitaClaw" + "企小勤" using default font (no external font dep)
    font_large = ImageFont.load_default()
    text_top = "VitaClaw"
    text_bot = "企小勤"
    # Approximate centering (PIL default font is small; this is interim)
    draw.text((180, 220), text_top, fill=(240, 244, 248, 255), font=font_large)
    draw.text((220, 270), text_bot, fill=(34, 211, 160, 255), font=font_large)
    img.save('kb/static/VitaClaw-Logo-v0.png', 'PNG')
    ```
    - Verify size ≥ 256×256 (it's 512×512), format == 'PNG'
    - Delete kb/static/VitaClaw-Logo-v0.png.MISSING.txt
    - Update kb/static/README.md noting "PIL-generated interim placeholder, swap with real vitaclaw asset post-launch"

    **If option-c (defer)**:
    - Leave kb/static/VitaClaw-Logo-v0.png absent
    - Update kb/static/VitaClaw-Logo-v0.png.MISSING.txt with explicit operator deploy-time checklist item
    - DO NOT delete the .MISSING.txt
    - Update kb/static/README.md noting kb-4 deferred this; operator owns
    - **Mark UI-04 in SUMMARY as "carry-forward-to-operator" — NOT satisfied in kb-4 codebase**
    - This is the only path where UI-04 stays unsatisfied; SUMMARY must call this out

    SUMMARY.md must record:
    - Which option was chosen + rationale
    - PIL verification output (size, mode, format) — except option-c
    - Provenance line in README.md
    - Whether UI-04 is satisfied in this phase or carry-forward
  </action>
  <verify>
    <automated>
      # Branches by chosen option — SUMMARY.md must declare which:
      # option-a or option-b: file exists + valid PNG ≥ 256×256
      # option-c: .MISSING.txt remains with updated content
      grep -E 'Chosen option: option-[abc]' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-03-SUMMARY.md

      # If option-a or option-b:
      python -c "
import sys
from pathlib import Path
summary = Path('.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-03-SUMMARY.md').read_text(encoding='utf-8')
if 'option-a' in summary or 'option-b' in summary:
    from PIL import Image
    im = Image.open('kb/static/VitaClaw-Logo-v0.png')
    assert im.size[0] >= 256 and im.size[1] >= 256, f'PNG too small: {im.size}'
    assert im.format == 'PNG', f'Not a PNG: {im.format}'
    print('PNG verified:', im.size, im.format)
elif 'option-c' in summary:
    assert Path('kb/static/VitaClaw-Logo-v0.png.MISSING.txt').exists(), '.MISSING.txt should remain for option-c'
    print('option-c carry-forward documented')
"
    </automated>
  </verify>
  <done>
    - SUMMARY explicitly records "Chosen option: option-{a|b|c}"
    - Branch verification passes (PNG verified OR .MISSING.txt updated)
    - kb/static/README.md provenance line updated
    - If option-c: UI-04 status in phase VERIFICATION clearly says "carry-forward to operator", not "satisfied"
  </done>
</task>

</tasks>

<verification>
- Logo sourcing decision documented + applied
- UI-04 status (satisfied vs carry-forward) explicit in SUMMARY
</verification>

<success_criteria>
- UI-04 closed: real PNG present (option-a/b) OR carry-forward documented (option-c)
- No silent acceptance — user/operator made an explicit decision
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-03-SUMMARY.md`
</output>
