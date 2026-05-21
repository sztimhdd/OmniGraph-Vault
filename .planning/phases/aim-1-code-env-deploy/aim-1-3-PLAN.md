---
phase: aim-1-code-env-deploy
plan: 3
type: execute
wave: 1
depends_on:
  - aim-1-2
files_modified:
  - .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
autonomous: false
requirements:
  - DEPLOY-03
user_setup:
  - service: deepseek
    why: "Layer 2 + LightRAG entity extraction LLM"
    env_vars:
      - name: DEEPSEEK_API_KEY
        source: "DeepSeek dashboard — operator side-channel; placeholder `<DEEPSEEK_API_KEY>` in this PLAN. `dummy` acceptable per Phase 5 import-time defense."
  - service: siliconflow
    why: "Vision cascade primary (Qwen3-VL)"
    env_vars:
      - name: SILICONFLOW_API_KEY
        source: "SiliconFlow dashboard — operator side-channel"
  - service: vertex-ai
    why: "Layer 1 LLM + embedding"
    env_vars:
      - name: OMNIGRAPH_VERTEX_SA_JSON_PATH
        source: "Path to GCP SA JSON file already on Aliyun (operator places file, then sets env var to its absolute path)"
  - service: gemini-api
    why: "Legacy fallback (vision tail of cascade + embedding fallback)"
    env_vars:
      - name: GEMINI_API_KEY
        source: "Google AI Studio — operator side-channel"
  - service: apify
    why: "WeChat scraping primary tier"
    env_vars:
      - name: APIFY_TOKEN
        source: "Apify dashboard — operator side-channel"
      - name: APIFY_TOKEN_BACKUP
        source: "Apify dashboard (rotation) — operator side-channel"

must_haves:
  truths:
    - "All 6 ingest provider keys are present in /root/.hermes/.env after append"
    - "All pre-existing kb-api keys remain unchanged (additive append only)"
    - "File mode + ownership of /root/.hermes/.env match the pre-aim-1 state"
    - "No literal secret value is committed to repo or any planning doc"
    - "Venv import of provider SDKs picks up the new keys (sanity-checked via env presence)"
  artifacts:
    - path: ".planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md"
      provides: "§DEPLOY-03 env-extension audit (key names only, no values)"
      contains: "## DEPLOY-03"
  key_links:
    - from: "Operator side-channel (NOT this PLAN)"
      to: "/root/.hermes/.env"
      via: "operator manual edit / append on Aliyun"
      pattern: "^DEEPSEEK_API_KEY=|^SILICONFLOW_API_KEY=|^OMNIGRAPH_VERTEX_SA_JSON_PATH=|^GEMINI_API_KEY=|^APIFY_TOKEN=|^APIFY_TOKEN_BACKUP="
---

<objective>
Append the 6 ingest-side LLM/scraper provider keys to the **existing** `/root/.hermes/.env` on Aliyun (the file already used by kb-api), preserving existing file mode + ownership and all pre-existing kb-api keys. Verify presence of all 6 keys via a key-names-only audit (never read values into any artifact).

Hard constraint: **no literal secret values appear in this PLAN, in DEPLOY-NOTES.md, in any commit, in any agent prompt** (per `feedback_no_literal_secrets_in_prompts.md`). Operator places real values directly on Aliyun via SSH side-channel — never paste secrets into Claude Code, never commit them.

Purpose: DEPLOY-04 smoke (`scripts/local_e2e.sh layer1 5` + `wechat <url>`) requires DeepSeek + SiliconFlow + Vertex + Gemini + Apify all configured. Without env extension, the smoke fails at the first provider call.

Output:
- Aliyun: `/root/.hermes/.env` extended with 6 ingest keys (real values placed by operator side-channel)
- Local: DEPLOY-NOTES.md §DEPLOY-03 records key names + verification artifacts (no values)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-Aliyun-Ingest-Migration-v1.md
@.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md
@.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md

<!-- Hard constraints: -->
<!-- 1. Extend EXISTING /root/.hermes/.env — do NOT create /etc/omnigraph/.env -->
<!-- 2. Preserve file mode + ownership exactly — do NOT chmod 600 if existing mode differs -->
<!-- 3. Preserve pre-existing kb-api keys unchanged — additive append only -->
<!-- 4. NO literal secret values anywhere — placeholders + side-channel only -->
<!-- 5. Agent does NOT SSH for mutating ops; operator-channel only -->
</context>

<pre_conditions>
- aim-1-1 + aim-1-2 complete (working tree clean + venv operational)
- DEPLOY-NOTES.md §DEPLOY-01 + §DEPLOY-02 populated
- Operator has SSH access via alias `aliyun-vitaclaw`
- Operator has the 6 secret values ready in their own password manager / secure notes (NOT in any chat / agent prompt)
</pre_conditions>

<tasks>

<task type="checkpoint:human-action">
  <name>Task 1: Operator audits pre-extension env file state (read-only, key names only)</name>
  <channel>operator-prompt</channel>
  <files>(read-only diagnostic on Aliyun — key names only, no values)</files>
  <what-built>
    Pre-extension snapshot of `/root/.hermes/.env`: file mode, ownership, existing key inventory (key names only).
  </what-built>
  <action>
    Operator runs on Aliyun via `ssh aliyun-vitaclaw` (read-only — values masked):

    ```bash
    echo "=== file mode + ownership ==="
    stat -c '%a %U:%G %n' /root/.hermes/.env

    echo "=== existing key names (values masked) ==="
    grep -E '^[A-Z_][A-Z0-9_]*=' /root/.hermes/.env | sed 's/=.*$/=<MASKED>/' | sort

    echo "=== check ingest keys absent or already present (names only) ==="
    grep -cE '^DEEPSEEK_API_KEY=' /root/.hermes/.env || true
    grep -cE '^SILICONFLOW_API_KEY=' /root/.hermes/.env || true
    grep -cE '^OMNIGRAPH_VERTEX_SA_JSON_PATH=' /root/.hermes/.env || true
    grep -cE '^GEMINI_API_KEY=' /root/.hermes/.env || true
    grep -cE '^APIFY_TOKEN=' /root/.hermes/.env || true
    grep -cE '^APIFY_TOKEN_BACKUP=' /root/.hermes/.env || true

    echo "=== line count ==="
    wc -l /root/.hermes/.env
    ```

    Operator captures all four blocks. **Critical: only the masked output (values replaced with `<MASKED>`) is suitable for the planning artifact. Do NOT paste raw env file contents anywhere.**
  </action>
  <how-to-verify>
    1. Block 1 (`stat`) shows mode + owner — operator records these for Task 3 preservation check
    2. Block 2 lists all key names with `=<MASKED>` suffix — never raw values
    3. Block 3 prints `0` or `1` for each ingest key (0 = absent, must be added; 1 = already present, replace value if needed but key already there)
    4. Block 4 records line count for post-extension delta check
  </how-to-verify>
  <resume-signal>Reply with the four masked blocks pasted, or summarize "mode=&lt;X&gt; owner=&lt;Y&gt; ingest-keys absent: 6/6"</resume-signal>
  <verify>
    <automated>MISSING — operator-channel diagnostic; verification is artifact review at Task 3</automated>
  </verify>
  <done>
    Operator captured masked pre-extension state; planner knows file mode/ownership/line-count baseline.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 2: Operator side-channel places real secret values + appends 6 keys to /root/.hermes/.env</name>
  <channel>operator-prompt (mutating; secrets handled side-channel)</channel>
  <files>(operator edits Aliyun /root/.hermes/.env directly — never via this PLAN)</files>
  <what-built>
    `/root/.hermes/.env` on Aliyun extended with 6 ingest provider keys with real values; file mode + ownership preserved; pre-existing keys untouched.
  </what-built>
  <action>
    **CRITICAL — secrets handling:**
    - Operator retrieves real secret values from their OWN secure store (password manager, encrypted notes, GCP secret manager, etc.)
    - Operator does NOT paste real values into this PLAN, into Claude Code, into git, into chat with the agent, or into any commit
    - Real values go directly into `/root/.hermes/.env` via the operator's editor on Aliyun (vim / nano / `cat >>` heredoc — operator's choice)

    **Step 2a — Operator opens the file on Aliyun:**

    ```bash
    ssh aliyun-vitaclaw
    cd /root/.hermes
    cp .env .env.bak-aim1-$(date +%Y%m%d-%H%M%S)   # safety backup before edit
    vim .env                                       # or nano / sudoedit per operator preference
    ```

    **Step 2b — Operator appends the following block at end of file** (replacing each `<PLACEHOLDER>` with the real value from operator's secure store; do NOT type real values into this PLAN):

    ```
    # === aim-1 ingest-side keys (appended 2026-05-21+) ===
    DEEPSEEK_API_KEY=<DEEPSEEK_API_KEY>
    SILICONFLOW_API_KEY=<SILICONFLOW_API_KEY>
    OMNIGRAPH_VERTEX_SA_JSON_PATH=<absolute-path-to-vertex-SA-JSON-on-Aliyun>
    GEMINI_API_KEY=<GEMINI_API_KEY>
    APIFY_TOKEN=<APIFY_TOKEN>
    APIFY_TOKEN_BACKUP=<APIFY_TOKEN_BACKUP>
    ```

    Notes:
    - **DeepSeek key:** if operator does not yet have a real DeepSeek key, set `DEEPSEEK_API_KEY=dummy` (Phase 5 cross-coupling import-time defense — see CLAUDE.md "Phase 5 DeepSeek cross-coupling"). DEPLOY-04 smoke modes that exercise DeepSeek (`layer1 5` triggers Layer 2; `wechat <url>` triggers LightRAG entity extraction) will fail until a real key replaces `dummy` — this is acceptable for the import smoke but blocks the full DEPLOY-04 pass; operator must place real key before declaring DEPLOY-04 complete.
    - **OMNIGRAPH_VERTEX_SA_JSON_PATH:** the SA JSON file itself (the actual JSON content) MUST already exist on Aliyun at the path operator names; the env var stores the absolute path, NOT the JSON content. SA JSON file goes under `/root/.config/` or similar — operator's choice; not part of this PLAN.
    - **Apify rotation:** `APIFY_TOKEN` is primary, `APIFY_TOKEN_BACKUP` is rotation per quick `260508-ev2` F1a. Both required.

    **Step 2c — Operator preserves file mode + ownership:**

    ```bash
    # If Task 1 reported mode=600, operator does NOT change it
    # If Task 1 reported mode=644 (or other), operator does NOT change it either
    # The intent: leave mode + ownership EXACTLY as Task 1 captured.
    stat -c '%a %U:%G' /root/.hermes/.env   # confirm post-edit matches pre-edit
    ```

    If mode changed unintentionally (some editors write a new file): `chmod <pre-edit-mode>` + `chown <pre-edit-owner>:<pre-edit-group>` to restore.
  </action>
  <how-to-verify>
    1. `cat .env.bak-aim1-*` exists as a safety net (operator can roll back if append corrupted file)
    2. Post-edit `stat -c '%a %U:%G' /root/.hermes/.env` matches Task 1's recorded mode + ownership exactly
    3. `wc -l /root/.hermes/.env` shows pre-edit line count + 7 (6 keys + 1 comment line) — within ±1 for editor-added trailing newline
    4. Operator manually checks: every kb-api key from Task 1 Block 2 is still present (no values changed for pre-existing keys)
    5. **No real secret value has been pasted into Claude Code / agent prompt / repo / any chat.** This is verified by absence — if operator suspects a leak, rotate the key immediately.
  </how-to-verify>
  <resume-signal>Type "env-extended" + confirm mode/ownership preserved + confirm no secret leak, or describe issues</resume-signal>
  <verify>
    <automated>MISSING — operator-channel mutating op; verification is post-state audit at Task 3</automated>
  </verify>
  <done>
    `/root/.hermes/.env` on Aliyun has 6 new ingest keys appended with real values; mode + ownership preserved; pre-existing keys unchanged; safety backup `.env.bak-aim1-<ts>` exists.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 3: Operator audits post-extension state + records audit in DEPLOY-NOTES.md (key names only)</name>
  <channel>operator-prompt + local-only</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</files>
  <what-built>
    Audit evidence proving 6/6 ingest keys present + pre-existing keys preserved + mode/ownership unchanged. Recorded in DEPLOY-NOTES.md §DEPLOY-03 (key names only — no values).
  </what-built>
  <action>
    **Step 3a — Operator audits post-extension state on Aliyun (read-only, masked):**

    ```bash
    echo "=== post-edit file mode + ownership ==="
    stat -c '%a %U:%G %n' /root/.hermes/.env

    echo "=== post-edit key names (values masked) ==="
    grep -E '^[A-Z_][A-Z0-9_]*=' /root/.hermes/.env | sed 's/=.*$/=<MASKED>/' | sort

    echo "=== ingest keys presence (must all be 1) ==="
    for k in DEEPSEEK_API_KEY SILICONFLOW_API_KEY OMNIGRAPH_VERTEX_SA_JSON_PATH GEMINI_API_KEY APIFY_TOKEN APIFY_TOKEN_BACKUP; do
      n=$(grep -cE "^${k}=" /root/.hermes/.env)
      echo "${k}: ${n}"
    done

    echo "=== post-edit line count ==="
    wc -l /root/.hermes/.env

    echo "=== venv-side env presence smoke (key NAMES only — values still masked) ==="
    cd /root/OmniGraph-Vault
    venv/bin/python -c "
    import os
    from pathlib import Path
    # Load /root/.hermes/.env without echoing values
    for line in Path('/root/.hermes/.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, _ = line.split('=', 1)
            os.environ.setdefault(k.strip(), 'sentinel')
    keys = ['DEEPSEEK_API_KEY','SILICONFLOW_API_KEY','OMNIGRAPH_VERTEX_SA_JSON_PATH','GEMINI_API_KEY','APIFY_TOKEN','APIFY_TOKEN_BACKUP']
    for k in keys:
        v = os.environ.get(k)
        # Print only presence + length category — never the value
        if v is None: print(f'{k}: MISSING')
        elif v == 'sentinel': print(f'{k}: present-empty')
        elif len(v) < 8: print(f'{k}: present-short ({len(v)}c)')
        else: print(f'{k}: present-ok ({len(v)}c)')
    "
    ```

    All 6 keys must report `present-ok` with reasonable length (typical: 32-512 chars; `dummy` for DeepSeek is `present-short (5c)` and acceptable per Phase 5 defense).

    **Step 3b — Operator extends DEPLOY-NOTES.md locally (key names only — no values):**

    Append to `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md`:

    ```markdown
    ## DEPLOY-03 — Env extension

    ### Pre-extension audit (Task 1)

    File mode + ownership: `[paste from Task 1 stat output]`

    Pre-existing key inventory (masked):
    ```
    [paste Task 1 Block 2 — values masked as `=<MASKED>`]
    ```

    Pre-existing line count: `[N]`

    Ingest keys absent / present pre-extension:
    - DEEPSEEK_API_KEY: [0/1]
    - SILICONFLOW_API_KEY: [0/1]
    - OMNIGRAPH_VERTEX_SA_JSON_PATH: [0/1]
    - GEMINI_API_KEY: [0/1]
    - APIFY_TOKEN: [0/1]
    - APIFY_TOKEN_BACKUP: [0/1]

    ### Append execution (Task 2)

    - Backup created: `/root/.hermes/.env.bak-aim1-<ts>` (operator-side, NOT committed)
    - Edit method: [vim | nano | cat heredoc | sudoedit]
    - DeepSeek key handling: [real | dummy per Phase 5 defense]
    - Vertex SA JSON file path on Aliyun: `[absolute-path]` (path only — file content NOT in artifact)

    ### Post-extension audit (Task 3a)

    File mode + ownership (post-edit): `[paste]` — **MATCHES pre-edit:** YES / NO

    Post-extension key inventory (masked):
    ```
    [paste Step 3a Block 2 — values masked]
    ```

    Ingest keys presence (must all be 1):
    ```
    [paste Step 3a Block 3 output]
    ```

    Post-extension line count: `[N]` (delta from pre: `[+7]` typical)

    Venv-side env presence smoke (key NAMES + length category only):
    ```
    [paste Step 3a Block 5 output]
    ```

    ### Audit verdict

    - Mode + ownership preserved: YES / NO
    - Pre-existing kb-api keys unchanged: YES / NO (operator visually compared masked inventories)
    - 6/6 ingest keys present with non-sentinel values: YES / NO
    - No literal secret pasted into Claude / repo / chat: YES (operator self-attests)

    ---
    ```

    Operator commits locally:
    ```bash
    git add .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md
    git commit -m "docs(aim-1): record DEPLOY-03 env-extension audit"
    ```
  </action>
  <how-to-verify>
    1. Step 3a Block 1: post-edit `stat` mode + ownership exactly matches Task 1 Block 1
    2. Step 3a Block 3: all 6 ingest keys report `1` (present)
    3. Step 3a Block 4: line count delta is `+6` to `+7` from Task 1 Block 4 (6 keys ± 1 trailing newline ± 1 comment)
    4. Step 3a Block 5: all 6 keys report `present-ok` (or DeepSeek `present-short` if `dummy`)
    5. DEPLOY-NOTES.md §DEPLOY-03 has Pre-audit, Append execution, Post-audit, Verdict subsections — values masked everywhere
    6. **No literal secret value appears anywhere in DEPLOY-NOTES.md** (manual grep before commit: `grep -E '(=sk-|=siliconflow_|=apify_api_)' DEPLOY-NOTES.md` should return zero hits)
    7. Audit verdict reports YES on all four lines
  </how-to-verify>
  <resume-signal>Type "audited" + paste verdict block, or describe failures</resume-signal>
  <verify>
    <automated>cd c:\Users\huxxha\Desktop\OmniGraph-Vault; git log --oneline -1 .planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md</automated>
  </verify>
  <done>
    DEPLOY-NOTES.md §DEPLOY-03 records audit pass: mode/ownership preserved, kb-api keys unchanged, 6/6 ingest keys present (`present-ok` or `present-short` for DeepSeek dummy), no secret leak. Committed locally.
  </done>
</task>

</tasks>

<verification>
**No-secrets check (PRIMARY):** Every artifact (this PLAN, DEPLOY-NOTES.md, commit messages, agent prompts) uses placeholders only. Real values are placed by operator side-channel directly on Aliyun. **If a literal secret is found in any planning artifact, ROTATE THE KEY IMMEDIATELY** (per `feedback_no_literal_secrets_in_prompts.md`).

**No-connection-details check:** No SSH host/port/user/IP in DEPLOY-NOTES.md or this PLAN. Operator uses local SSH alias.

**File integrity:** `.env.bak-aim1-<ts>` is a side-channel backup on Aliyun for rollback — NOT committed to repo.

**Mode/ownership preservation:** Explicit pre-edit and post-edit `stat -c '%a %U:%G'` must match.

**kb-api preservation:** Pre-existing kb-api keys remain in masked-inventory comparison; operator visually verifies "every Task 1 Block 2 entry still appears in Task 3 Step 3a Block 2".

**Phase 5 escape hatch:** `DEPLOY-03` accepts `DEEPSEEK_API_KEY=dummy` for the import-time defense; full DEPLOY-04 smoke needs a real DeepSeek key for the modes that exercise Layer 2 / LightRAG entity extraction.
</verification>

<success_criteria>
**ROADMAP SC3 (line 80):** "Ingest provider keys appended to existing `/root/.hermes/.env` (preserve existing mode + ownership; do NOT create separate `/etc/omnigraph/.env`); required keys present after append: `DEEPSEEK_API_KEY`, `SILICONFLOW_API_KEY`, `OMNIGRAPH_VERTEX_SA_JSON_PATH`, `GEMINI_API_KEY`, `APIFY_TOKEN`, `APIFY_TOKEN_BACKUP`; pre-existing kb-api keys preserved unchanged; no literal secret committed to repo or any planning doc (DEPLOY-03)"

Mapped:
- ✅ Append to existing `/root/.hermes/.env`: Tasks 2 explicitly targets this path; alternative `/etc/omnigraph/.env` forbidden in PLAN context
- ✅ Preserve mode + ownership: Task 1 captures pre-state; Task 2 Step 2c preserves; Task 3 audit verifies match
- ✅ All 6 ingest keys present: Task 3 Step 3a Block 3 + Block 5 verify presence + non-sentinel
- ✅ kb-api keys preserved: Task 1 Block 2 + Task 3 Step 3a Block 2 masked-inventory comparison
- ✅ No literal secret committed: Task 3 verification step 6 + No-secrets check + operator self-attest in audit verdict
</success_criteria>

<output>
After completion, create or extend `.planning/phases/aim-1-code-env-deploy/aim-1-3-SUMMARY.md` recording:
- 6/6 ingest keys present (with note if DeepSeek is `dummy`)
- Mode + ownership match (YES required)
- kb-api keys unchanged (YES required)
- Audit verdict block from DEPLOY-NOTES.md
- Confirmation of no-secrets / no-connection-details / operator-channel checks
</output>
