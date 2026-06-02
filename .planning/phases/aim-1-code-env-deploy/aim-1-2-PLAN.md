---
phase: aim-1-code-env-deploy
plan: 2
type: execute
wave: 1
depends_on:
  - aim-1-1
files_modified:
  - .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
autonomous: false
requirements:
  - DEPLOY-02
user_setup:
  - service: aliyun-ecs-vitaclaw
    why: "Operator-channel SSH for venv + pip install (mutating ops on prod host)"
    env_vars: []
    dashboard_config:
      - task: "Operator SSH alias `aliyun-vitaclaw`. Connection details NOT recorded in this plan."
        location: "Operator's local ~/.ssh/config"

must_haves:
  truths:
    - "Python 3.11+ venv exists at /root/OmniGraph-Vault/venv/ on Aliyun"
    - "pip install -r requirements.txt completes with zero errors"
    - "Smoke import (lightrag + google.genai + deepseek) prints OK"
    - "If kb-api venv pre-existed at this path, it is reused after Python version verification"
  artifacts:
    - path: ".planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md"
      provides: "§DEPLOY-02 venv path + Python version + pip install summary + smoke import output"
      contains: "## DEPLOY-02"
  key_links:
    - from: "Aliyun /root/OmniGraph-Vault/venv/"
      to: "DEPLOY-NOTES.md §DEPLOY-02"
      via: "operator-pasted python --version + pip install tail + import smoke output"
      pattern: "Python 3\\.(11|12|13)"
---

<objective>
Stand up (or verify-and-reuse) a Python 3.11+ virtual environment at `/root/OmniGraph-Vault/venv/` on Aliyun, install ingest dependencies via `pip install -r requirements.txt`, and prove the install by running an import smoke (`python -c "import lightrag, google.genai, deepseek; print('OK')"`).

Two scenarios are explicitly handled:

- **(a) Fresh venv** — kb-api has no venv at this path; create with `python3.11 -m venv venv`
- **(b) Reuse kb-api venv** — kb-api's venv already lives at `/root/OmniGraph-Vault/venv/`; verify Python 3.11+, run `pip install -r requirements.txt` to converge to ingest deps without breaking kb-api imports

Purpose: DEPLOY-04 smoke (`scripts/local_e2e.sh layer1 5` + `wechat <url>`) needs a working Python environment with lightrag + provider SDKs. Without this, every smoke run fails at import time.

Output:

- Aliyun: working venv at `/root/OmniGraph-Vault/venv/` with all `requirements.txt` deps installed and import smoke passing
- Local: `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md` extended with §DEPLOY-02 section
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-Aliyun-Ingest-Migration-v1.md
@.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md
@.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md
@requirements.txt

<!-- Hard constraints: -->
<!-- 1. Venv at /root/OmniGraph-Vault/venv/ — do NOT create sibling at /opt/omnigraph-vault/venv/ -->
<!-- 2. If kb-api venv exists at this path, reuse — do NOT delete + recreate -->
<!-- 3. Python 3.11+ MUST be confirmed before pip install -->
<!-- 4. Agent does NOT SSH for mutating ops — operator-channel only -->
</context>

<pre_conditions>

- aim-1-1 complete: working tree clean at known HEAD on Aliyun
- DEPLOY-NOTES.md §DEPLOY-01 populated with HEAD hash
- Operator has SSH access via alias `aliyun-vitaclaw`
</pre_conditions>

<tasks>

<task type="checkpoint:human-action">
  <name>Task 1: Operator probes existing venv state (read-only)</name>
  <channel>operator-prompt</channel>
  <files>(read-only diagnostic on Aliyun)</files>
  <what-built>
    Decision input for Task 2: does a venv already exist at the target path? What Python version?
  </what-built>
  <action>
    Operator runs on Aliyun via `ssh aliyun-vitaclaw` (read-only):

    ```bash
    cd /root/OmniGraph-Vault
    echo "=== venv directory ==="
    ls -la venv/ 2>&1 | head -5      # exists or "No such file or directory"
    echo "=== venv python version ==="
    venv/bin/python --version 2>&1   # exists if venv exists
    echo "=== system python3.11 ==="
    which python3.11 || which python3.12 || which python3.13   # candidate base python
    python3.11 --version 2>&1 || python3.12 --version 2>&1 || python3.13 --version 2>&1
    echo "=== disk free under /root ==="
    df -h /root | tail -1            # ensure ≥ 2 GB free for pip install + wheel cache
    ```

    Operator captures all five output blocks for Task 2 decision and Task 3 evidence.
  </action>
  <how-to-verify>
    1. Block 1 (`ls -la venv/`) clearly says either "exists" (with `bin/`, `lib/`, `pyvenv.cfg`) or "No such file or directory"
    2. If venv exists, Block 2 reports `Python 3.11.x` / `3.12.x` / `3.13.x` (must be ≥ 3.11)
    3. Block 3 (`which python3.11`) confirms a usable base interpreter exists on the host (else venv create cannot proceed)
    4. Block 5 (`df -h /root`) shows ≥ 2 GB free
  </how-to-verify>
  <resume-signal>Reply with the captured outputs (paste verbatim), or report "venv exists, Py 3.X" / "venv missing, system has Py 3.X"</resume-signal>
  <verify>
    <automated>MISSING — operator-channel diagnostic; verification is artifact review at Task 3</automated>
  </verify>
  <done>
    Operator has captured all five diagnostic blocks; planner has decision input for Task 2.
  </done>
</task>

<task type="checkpoint:decision">
  <name>Task 2: Decide create-fresh vs reuse based on Task 1 probe</name>
  <channel>local-only (decision recorded in artifact)</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</files>
  <decision>Create fresh venv or reuse existing kb-api venv?</decision>
  <context>
    Task 1 probe reveals one of:
    - **(A)** No venv at `/root/OmniGraph-Vault/venv/` → create-fresh path (no risk)
    - **(B)** Venv exists, Python ≥ 3.11 → reuse path (run `pip install -r requirements.txt`; deps may already be partially present from kb-api)
    - **(C)** Venv exists, Python &lt; 3.11 → blocked; must remove and recreate (LightRAG + lib/ require ≥3.11 per CLAUDE.md project summary)
    - **(D)** Disk free &lt; 2 GB → blocked; must free space first

    Reuse (B) is preferred to avoid disrupting kb-api. Fresh (A) is safe. (C)/(D) are blockers — escalate to operator + halt aim-1.
  </context>
  <options>
    <option id="reuse">
      <name>(B) Reuse existing venv at correct Python version</name>
      <pros>Zero kb-api disruption; pip install converges incrementally</pros>
      <cons>requirements.txt may downgrade a kb-api-pinned dep — must verify kb-api still works post-install (smoke kb-api separately if concerned)</cons>
      <when>Task 1 reports venv exists + Python ≥ 3.11</when>
    </option>
    <option id="fresh">
      <name>(A) Create fresh venv</name>
      <pros>Clean slate; no dep-collision risk</pros>
      <cons>None when kb-api has no venv at this path</cons>
      <when>Task 1 reports no venv at /root/OmniGraph-Vault/venv/</when>
    </option>
    <option id="recreate">
      <name>(C) Remove + recreate venv (Python &lt; 3.11 case)</name>
      <pros>Forces Python 3.11+; clean slate</pros>
      <cons>If kb-api was using this venv, kb-api will need its own re-install too — escalate to user before executing</cons>
      <when>Task 1 reports venv exists but Python &lt; 3.11. STOP and surface to user before proceeding.</when>
    </option>
    <option id="blocker">
      <name>(D) Halt — disk free &lt; 2 GB</name>
      <pros>Prevents partial pip install + corrupted venv</pros>
      <cons>Blocks aim-1 progress until operator frees space</cons>
      <when>Task 1 reports df -h /root with &lt; 2 GB free. Halt + surface to user.</when>
    </option>
  </options>
  <resume-signal>Reply: "reuse", "fresh", "recreate (escalating)", or "blocker (escalating)"</resume-signal>
  <verify>
    <automated>MISSING — decision recorded in DEPLOY-NOTES.md §DEPLOY-02 "Venv strategy"</automated>
  </verify>
  <done>
    DEPLOY-NOTES.md §DEPLOY-02 contains "Venv strategy" subsection naming the chosen path + rationale; (C)/(D) cases halt aim-1.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 3: Operator executes venv setup + pip install + import smoke; records output</name>
  <channel>operator-prompt + local-only</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</files>
  <what-built>
    Working venv at `/root/OmniGraph-Vault/venv/` with deps installed; smoke import passes; DEPLOY-NOTES.md §DEPLOY-02 populated.
  </what-built>
  <action>
    **Step 3a — Operator executes venv setup on Aliyun (operator-channel; mutating):**

    Based on Task 2 decision:

    - If `reuse` (B):
      ```bash
      cd /root/OmniGraph-Vault
      venv/bin/python --version          # confirm Python 3.11+
      venv/bin/pip install --upgrade pip
      venv/bin/pip install -r requirements.txt
      ```
    - If `fresh` (A):
      ```bash
      cd /root/OmniGraph-Vault
      python3.11 -m venv venv            # or python3.12 / python3.13 — whichever Task 1 confirmed
      venv/bin/python --version          # confirm 3.11+
      venv/bin/pip install --upgrade pip
      venv/bin/pip install -r requirements.txt
      ```

    Operator captures the **last 30 lines** of `pip install` output (the summary block including any warnings) — sufficient for evidence without dumping the full wheel-build log.

    **Step 3b — Operator runs import smoke (operator-channel):**

    ```bash
    cd /root/OmniGraph-Vault
    venv/bin/python -c "import lightrag, google.genai, deepseek; print('OK')"
    ```

    Expected output: a single line `OK`. Any exception → halt + surface to user.

    Optional secondary smoke (recommended for reuse path — verify kb-api still imports):
    ```bash
    venv/bin/python -c "from kb.app import app; print('kb-api OK')" 2>&1 | tail -5
    ```

    **Step 3c — Operator extends DEPLOY-NOTES.md locally:**

    Append to `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md`:

    ```markdown
    ## DEPLOY-02 — Venv setup

    ### Pre-setup probe (Task 1)

    ```
    [paste verbatim 5-block output from Task 1]
    ```

    ### Venv strategy (Task 2)

    **Strategy:** [reuse | fresh | recreate (escalated) | blocker (escalated)]
    **Rationale:** [one paragraph]

    ### Setup execution (Task 3a)

    Commands run on Aliyun:
    ```
    [paste verbatim commands]
    ```

    Pip install tail (last 30 lines):
    ```
    [paste tail of pip install output]
    ```

    ### Import smoke (Task 3b)

    ```
    $ venv/bin/python -c "import lightrag, google.genai, deepseek; print('OK')"
    [paste verbatim output — MUST be `OK`]
    ```

    [If reuse path — paste kb-api smoke output here too]

    **Python version (post-setup):** `Python 3.X.Y`
    **Venv path:** `/root/OmniGraph-Vault/venv/`
    **Import smoke result:** PASS / FAIL

    ---
    ```

    Operator commits locally:
    ```bash
    git add .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
    git commit -m "docs(aim-1): record DEPLOY-02 venv setup + import smoke"
    ```
  </action>
  <how-to-verify>
    1. `venv/bin/python --version` reports Python 3.11+ on Aliyun
    2. `pip install -r requirements.txt` final line shows no `ERROR:` (warnings acceptable; pip resolution warnings about kb-api deps acceptable in reuse path if import smoke still passes)
    3. Import smoke prints exactly `OK` (no traceback, no extra warnings on stderr that would obscure the OK line)
    4. DEPLOY-NOTES.md §DEPLOY-02 has all four subsections (Probe / Strategy / Execution / Smoke) populated verbatim
    5. DEPLOY-NOTES.md committed locally
    6. No literal secrets / connection details in DEPLOY-NOTES.md
  </how-to-verify>
  <resume-signal>Type "venv-ready" with Python version, or describe issues</resume-signal>
  <verify>
    <automated>cd c:\Users\huxxha\Desktop\OmniGraph-Vault; git log --oneline -1 .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</automated>
  </verify>
  <done>
    Aliyun venv operational at `/root/OmniGraph-Vault/venv/`; import smoke passes; DEPLOY-NOTES.md §DEPLOY-02 complete; committed locally.
  </done>
</task>

</tasks>

<verification>
**No-secrets check:** No API keys, tokens, or service-account JSON content appear in DEPLOY-NOTES.md or PLAN. Only Python version strings, pip install summaries, and import success messages.

**No-connection-details check:** No SSH host / port / user / IP in DEPLOY-NOTES.md. Operator uses local SSH alias.

**Reuse-path safety:** If reuse path is taken (B), the import smoke (Task 3b primary) covers ingest-side imports; kb-api re-import smoke is recommended (operator's call). Re-import failure → halt + surface to user.

**Path discipline:** Only `/root/OmniGraph-Vault/venv/` referenced. No `/opt/omnigraph-vault/venv/`.
</verification>

<success_criteria>
**ROADMAP SC2 (line 79):** "Python venv at `/root/OmniGraph-Vault/venv/` with Python 3.11+; `pip install -r requirements.txt` succeeds zero errors; `python -c \"import lightrag, google.genai, deepseek; print('OK')\"` prints OK (DEPLOY-02)"

Mapped:

- ✅ Venv at `/root/OmniGraph-Vault/venv/`: Tasks 1, 3 explicitly target this path
- ✅ Python 3.11+: Task 1 probes; Task 2 (C) blocks &lt;3.11; Task 3a confirms post-setup
- ✅ `pip install -r requirements.txt` zero errors: Task 3a executes; Task 3c records tail; verification step 2 checks for `ERROR:`
- ✅ Import smoke prints `OK`: Task 3b executes; Task 3c records output; verification step 3 checks exact match

**REQ DEPLOY-02 reuse clause:** "if the kb-api venv is already at this path, reuse + verify Python 3.11+ + run `pip install -r requirements.txt` to converge to ingest deps" — Task 2 option (B) handles exactly this; Task 3a's `reuse` branch executes it.
</success_criteria>

<output>
After completion, create or extend `.planning/phases/aim-1-code-env-deploy/aim-1-2-SUMMARY.md` recording:
- Venv strategy chosen (reuse | fresh)
- Python version on Aliyun post-setup
- Import smoke result (must be PASS)
- Any kb-api side-smoke result if reuse path taken
- Confirmation of no-secrets / no-connection-details / operator-channel checks
</output>
