---
phase: aim-1-code-env-deploy
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
autonomous: false
requirements:
  - DEPLOY-01
user_setup:
  - service: aliyun-ecs-vitaclaw
    why: "Operator-channel SSH for working-tree reconciliation (mutating git ops on prod host)"
    env_vars: []
    dashboard_config:
      - task: "Operator SSH alias `aliyun-vitaclaw` (memory: aliyun_vitaclaw_ssh.md). Connection details NOT recorded in this plan — public repo."
        location: "Operator's local ~/.ssh/config"

must_haves:
  truths:
    - "Pre-aim-1 dirty working tree at /root/OmniGraph-Vault/ is reconciled to a known HEAD"
    - "git status on Aliyun reports clean working tree post-reconcile"
    - "HEAD commit hash is recorded in DEPLOY-NOTES.md with operator's reconcile rationale"
    - "Repo origin matches sztimhdd/OmniGraph-Vault.git (or operator's fork)"
  artifacts:
    - path: ".planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md"
      provides: "Reconcile rationale + HEAD hash + git status snapshot"
      contains: "## DEPLOY-01"
  key_links:
    - from: "Aliyun /root/OmniGraph-Vault/"
      to: "DEPLOY-NOTES.md"
      via: "operator-captured `git status` + `git log -1` output pasted into local artifact"
      pattern: "HEAD=[a-f0-9]{7,}"
---

<objective>
Reconcile the pre-aim-1 dirty working tree at `/root/OmniGraph-Vault/` (kb-api's existing checkout, HEAD=`4eaef45` at 2026-05-16, dirty from manual SCP per Gate 1 SSH probe) to a clean known HEAD. End state: `git status` reports an empty working tree on Aliyun, the HEAD commit hash is recorded, and the operator's reconcile method (commit / stash / discard) is documented in `DEPLOY-NOTES.md`.

Purpose: DEPLOY-02..04 require a clean tree they can trust. Without reconciliation, `pip install` may run against an unknown `requirements.txt`, env-file edits may collide with uncommitted changes, and smoke logs will not be reproducible against a known commit.

Output:

- Aliyun: clean working tree at `/root/OmniGraph-Vault/`, HEAD reconciled to a known commit
- Local: `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md` with §DEPLOY-01 section
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-Aliyun-Ingest-Migration-v1.md
@.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md
@.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md
@.planning/STATE-Aliyun-Ingest-Migration-v1.md

<!-- Hard constraints (operator MUST honor): -->
<!-- 1. In-place at /root/OmniGraph-Vault/ — do NOT clone to /opt/omnigraph-vault/ -->
<!-- 2. Agent does NOT SSH for mutating ops on Aliyun (operator-channel only) -->
<!-- 3. No connection details (host/port/user/IP) in any artifact — public repo -->
<!-- 4. Gate 1 closure (STATE:132-133) is the authoritative path-correction record -->
</context>

<pre_conditions>

- aim-0 verdict = PASS (recorded in STATE Gate 1 CLOSED line 132-133)
- `.planning/phases/aim-1-code-env-deploy/` directory exists (orchestrator created it)
- Operator has SSH access via alias `aliyun-vitaclaw` (memory file `aliyun_vitaclaw_ssh.md`)
- No mutating SSH commands have been issued by agent for this phase
</pre_conditions>

<tasks>

<task type="checkpoint:human-action">
  <name>Task 1: Operator captures pre-reconcile state</name>
  <channel>operator-prompt</channel>
  <files>(read-only diagnostic on Aliyun)</files>
  <what-built>
    Pre-reconcile snapshot of `/root/OmniGraph-Vault/` working tree state.
  </what-built>
  <action>
    Operator runs the following on Aliyun via `ssh aliyun-vitaclaw` (read-only — does NOT mutate the tree):

    ```bash
    cd /root/OmniGraph-Vault
    echo "=== git remote -v ==="
    git remote -v
    echo "=== git log -1 --oneline ==="
    git log -1 --oneline
    echo "=== git status ==="
    git status
    echo "=== git diff --stat ==="
    git diff --stat
    echo "=== git diff --stat --cached ==="
    git diff --stat --cached
    ```

    Operator copies the full output (all five sections) into a local scratch file or directly into `DEPLOY-NOTES.md` §DEPLOY-01 "Pre-reconcile state".
  </action>
  <how-to-verify>
    1. Output begins with `git@github.com:sztimhdd/OmniGraph-Vault.git` (or operator's fork URL) confirming origin
    2. `git log -1 --oneline` shows a real commit hash (expected baseline: `4eaef45` per STATE:132-133, but may have advanced)
    3. `git status` output is captured verbatim — exact lines matter for reconcile decision
    4. Operator pastes all five blocks into DEPLOY-NOTES.md §DEPLOY-01 (template in Task 3)
  </how-to-verify>
  <resume-signal>Type "captured" when pre-reconcile state is recorded in DEPLOY-NOTES.md, or describe issues</resume-signal>
  <verify>
    <automated>MISSING — operator-channel task; verification is artifact review at Task 3</automated>
  </verify>
  <done>
    DEPLOY-NOTES.md contains a §DEPLOY-01 "Pre-reconcile state" subsection with all five command outputs verbatim.
  </done>
</task>

<task type="checkpoint:decision">
  <name>Task 2: Operator decides reconcile method</name>
  <channel>local-only (decision recorded in artifact)</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</files>
  <decision>How to reconcile the dirty working tree to a clean known HEAD?</decision>
  <context>
    Per Gate 1 SSH probe (STATE:132-133), tree was dirty from manual SCP residue at 2026-05-21. The dirty changes may be:
    (a) experimental edits from prior debug work (discard candidate),
    (b) genuine improvements not yet pushed (commit candidate),
    (c) work-in-progress to preserve but not commit (stash candidate).

    Only the operator can judge — they made the changes. Repo is **public on GitHub**, so any commit must be cleanly attributable.
  </context>
  <options>
    <option id="commit">
      <name>Commit dirty changes (forward-only)</name>
      <pros>Preserves work; tree clean immediately; cleanly traceable in git log</pros>
      <cons>Requires a real commit message; pollutes history if changes are debug residue</cons>
      <when>Dirty changes are genuine improvements operator wants to keep on Aliyun</when>
    </option>
    <option id="stash">
      <name>Stash dirty changes</name>
      <pros>Tree clean; work preserved in stash; recoverable later via `git stash pop`</pros>
      <cons>Stash is local-only on Aliyun (not pushed); silent loss risk if box rebuilt</cons>
      <when>Operator wants to preserve work but is not yet sure how to commit it</when>
    </option>
    <option id="discard">
      <name>Discard dirty changes (`git checkout -- .` + `git clean -fd`)</name>
      <pros>Tree clean; no residual history pollution; resets to known HEAD</pros>
      <cons>Permanent loss of uncommitted changes — irreversible</cons>
      <when>Dirty changes are confirmed debug residue / SCP artifacts with no value</when>
    </option>
    <option id="checkout">
      <name>Discard + checkout to a different known good commit</name>
      <pros>Combines discard with explicit HEAD selection (e.g., `git checkout v1.0.x-stable`)</pros>
      <cons>Same loss risk as discard; requires operator to choose target commit</cons>
      <when>Operator wants to align Aliyun HEAD with a specific tagged release rather than current `4eaef45`</when>
    </option>
  </options>
  <resume-signal>Reply: "commit", "stash", "discard", "checkout &lt;target&gt;", or describe alternative</resume-signal>
  <verify>
    <automated>MISSING — decision-only task; recorded in DEPLOY-NOTES.md §DEPLOY-01 "Reconcile decision"</automated>
  </verify>
  <done>
    DEPLOY-NOTES.md contains a §DEPLOY-01 "Reconcile decision" subsection naming the chosen method + one-paragraph rationale.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 3: Operator executes reconcile + records final state in DEPLOY-NOTES.md</name>
  <channel>operator-prompt + local-only</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</files>
  <what-built>
    Clean working tree on Aliyun at known HEAD; reconcile artifact (DEPLOY-NOTES.md §DEPLOY-01) complete.
  </what-built>
  <action>
    **Step 3a — Operator executes reconcile on Aliyun (mutating ops, operator-channel only):**

    Based on Task 2 decision, operator runs ONE of (on Aliyun via `ssh aliyun-vitaclaw`):

    - If `commit`:
      ```bash
      cd /root/OmniGraph-Vault
      git add <explicit-files>           # NOT git add -A — explicit attribution
      git commit -m "<message>"
      git push origin main               # if operator wants this on github
      ```
    - If `stash`:
      ```bash
      cd /root/OmniGraph-Vault
      git stash push -m "aim-1 pre-deploy stash $(date +%Y%m%d-%H%M)"
      ```
    - If `discard`:
      ```bash
      cd /root/OmniGraph-Vault
      git checkout -- .
      git clean -fd
      ```
    - If `checkout <target>`:
      ```bash
      cd /root/OmniGraph-Vault
      git checkout -- .
      git clean -fd
      git fetch origin
      git checkout <target>
      ```

    **Step 3b — Operator captures post-reconcile state (read-only):**

    ```bash
    cd /root/OmniGraph-Vault
    echo "=== git status ==="
    git status                          # MUST be empty / "nothing to commit, working tree clean"
    echo "=== git log -1 --oneline ==="
    git log -1 --oneline                # capture HEAD hash
    echo "=== git remote -v ==="
    git remote -v
    ```

    **Step 3c — Operator writes / completes DEPLOY-NOTES.md locally:**

    Create or extend `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md` with the following template (operator fills in the bracketed sections):

    ```markdown
    # aim-1 Deploy Notes

    Phase: aim-1 (Code + env deploy)
    Operator: [name / handle]
    Date: 2026-05-21+

    ---

    ## DEPLOY-01 — Working tree reconcile

    ### Pre-reconcile state (Task 1 capture)

    ```
    [paste verbatim output of: git remote -v / git log -1 / git status / git diff --stat / git diff --stat --cached]
    ```

    ### Reconcile decision (Task 2)

    **Method:** [commit | stash | discard | checkout &lt;target&gt;]

    **Rationale:** [one paragraph — why this method was chosen for these specific dirty changes]

    ### Reconcile execution (Task 3a)

    Commands run on Aliyun:
    ```
    [paste verbatim commands run]
    ```

    ### Post-reconcile state (Task 3b)

    ```
    [paste verbatim output of: git status / git log -1 --oneline / git remote -v]
    ```

    **HEAD commit hash (post-reconcile):** `[hash]`
    **Working tree clean:** YES / NO

    ---
    ```

    Operator commits this file locally:
    ```bash
    git add .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
    git commit -m "docs(aim-1): record DEPLOY-01 working-tree reconcile"
    ```
  </action>
  <how-to-verify>
    1. Aliyun `git status` output (Step 3b) is exactly `nothing to commit, working tree clean` (or equivalent language)
    2. Aliyun `git log -1 --oneline` output (Step 3b) shows a real commit hash + message
    3. DEPLOY-NOTES.md exists locally with all four §DEPLOY-01 subsections (Pre / Decision / Execution / Post) populated verbatim
    4. DEPLOY-NOTES.md is committed locally (planner artifact tracked in git)
    5. No literal secrets present in DEPLOY-NOTES.md (paths + commit hashes + git status output only)
    6. No Aliyun connection details (host/port/user/IP) present in DEPLOY-NOTES.md
  </how-to-verify>
  <resume-signal>Type "reconciled" with the new HEAD hash, or describe issues</resume-signal>
  <verify>
    <automated>cd c:\Users\huxxha\Desktop\OmniGraph-Vault; git log --oneline -1 .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</automated>
  </verify>
  <done>
    Aliyun working tree clean at known HEAD; DEPLOY-NOTES.md §DEPLOY-01 has all four subsections; file committed locally; no secrets / connection details leaked.
  </done>
</task>

</tasks>

<verification>
**No-secrets check:** No literal API keys, tokens, passwords, or private keys appear in DEPLOY-NOTES.md or any planning artifact. Only paths, commit hashes, git status output, and operator rationale.

**No-connection-details check:** No SSH hostname / port / username / IP address appears in DEPLOY-NOTES.md or this PLAN. Operator uses local SSH alias `aliyun-vitaclaw` (per memory `aliyun_vitaclaw_ssh.md`).

**Operator-channel discipline:** All mutating git ops (commit / stash / discard / checkout) are operator-channel. Agent does NOT SSH to Aliyun for any mutating operation in this plan.
</verification>

<success_criteria>
**ROADMAP SC1 (line 78):** "Code deployed in-place at `/root/OmniGraph-Vault/` (existing kb-api checkout per STATE:132-133; HEAD reconciled to a known commit; pre-aim-1 dirty working tree captured / committed / discarded per operator judgement and recorded in DEPLOY-NOTES.md); `git status` clean post-reconcile; HEAD commit hash recorded (DEPLOY-01)"

Mapped to plan acceptance:

- ✅ In-place at `/root/OmniGraph-Vault/`: Tasks 1, 3 operate on this path; Task 2 forbids alternative
- ✅ HEAD reconciled to known commit: Task 3a executes reconcile; Task 3b captures HEAD hash
- ✅ Dirty working tree captured / committed / discarded per operator judgement: Task 2 decision options exhaust the four reconcile methods; Task 3a executes choice
- ✅ Recorded in DEPLOY-NOTES.md: Task 3c builds the artifact with all four subsections
- ✅ `git status` clean post-reconcile: Task 3b verification step
- ✅ HEAD commit hash recorded: DEPLOY-NOTES.md template "HEAD commit hash (post-reconcile)" field
</success_criteria>

<output>
After completion, create `.planning/phases/aim-1-code-env-deploy/aim-1-1-SUMMARY.md` recording:
- HEAD hash post-reconcile (the bridge to aim-1-2)
- Reconcile method chosen + one-line rationale
- Total operator round-trips (target: 1 SSH session covering Tasks 1 + 3a + 3b)
- Confirmation that no-secrets / no-connection-details / operator-channel checks all pass
</output>
