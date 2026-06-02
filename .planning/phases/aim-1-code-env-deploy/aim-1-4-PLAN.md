---
phase: aim-1-code-env-deploy
plan: 4
type: execute
wave: 1
depends_on:
  - aim-1-3
files_modified:
  - .planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md
autonomous: false
requirements:
  - DEPLOY-04
user_setup:
  - service: aliyun-ecs-vitaclaw
    why: "Operator-channel SSH for smoke runs (mutating: pip env, scratch storage, log writes)"
    env_vars: []
    dashboard_config:
      - task: "Operator SSH alias `aliyun-vitaclaw`. Connection details NOT recorded in this plan."
        location: "Operator's local ~/.ssh/config"

must_haves:
  truths:
    - "scripts/local_e2e.sh layer1 5 reaches completion on Aliyun with no errors in the log"
    - "scripts/local_e2e.sh wechat <url> reaches completion on Aliyun with no errors in the log"
    - "Both smoke runs ingest into SCRATCH storage, NOT the production lightrag_storage path"
    - "Production path <OMNIGRAPH_BASE_DIR>/lightrag_storage/ remains empty (or untouched if it had pre-existing kb-api content)"
    - "Hermes ingest cron continues running uninterrupted during aim-1 smoke"
  artifacts:
    - path: ".planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md"
      provides: "Smoke-run evidence: command, env vars used, log tail excerpts, scratch-storage proof"
      contains: "## DEPLOY-04"
  key_links:
    - from: "Aliyun .scratch/local-e2e-layer1-<ts>.log"
      to: "DEPLOY-04-EVIDENCE.md"
      via: "operator-pasted log tail (last 30 lines)"
      pattern: "(layer1|wechat).*completed|Layer 1 batch finished"
    - from: "Aliyun /tmp/aim1-smoke/lightrag_storage/ (or operator's chosen scratch)"
      to: "DEPLOY-04-EVIDENCE.md"
      via: "ls -la output proving smoke ingests landed in scratch, not production path"
      pattern: "/tmp/aim1-smoke|/scratch/aim1"
---

<objective>
Run the two `scripts/local_e2e.sh` smoke modes on Aliyun against the venv + extended env from aim-1-2 + aim-1-3, proving the full ingest pipeline (Layer 1 + scrape + Layer 2 + LightRAG ainsert + vision) is operational on the new host. **Smoke ingests MUST land in scratch storage** (e.g., `/tmp/aim1-smoke/`), not the production path — Hermes is still authoritative until aim-2 cuts over with the 1.6 GB tar.gz transfer.

Two smoke modes (both required per REQ DEPLOY-04 + ROADMAP SC4):

1. **`scripts/local_e2e.sh layer1 5`** — Layer 1 batch on 5 candidates from `.dev-runtime/data/kol_scan.db` (or whatever DB the harness defaults to; harness handles env). Exercises Vertex AI Layer 1 + DeepSeek Layer 2 (only on candidates that pass Layer 1).
2. **`scripts/local_e2e.sh wechat <url>`** — single-URL E2E on a non-corp-restricted target. Exercises Apify scrape → Layer 2 → SiliconFlow vision → LightRAG ainsert.

Aliyun is in cn-east-mainland (per PROJECT) — all 3 LLM providers reachable (no corp Cisco Umbrella interception); this is the architectural reason migration was chartered.

Output:

- Aliyun: two log files under `/root/OmniGraph-Vault/.scratch/local-e2e-*-<ts>.log` proving zero-error completion
- Aliyun: smoke ingests in scratch storage (`/tmp/aim1-smoke/lightrag_storage/` or equivalent) — confirmed not in production path
- Local: `.planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md` with command, env, log tails, scratch-storage proof
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-Aliyun-Ingest-Migration-v1.md
@.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md
@.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md
@scripts/local_e2e.sh

<!-- Hard constraints: -->
<!-- 1. Smoke ingests → SCRATCH storage; production path stays empty (Hermes pre-cutover constraint, PROJECT §5 #6) -->
<!-- 2. Hermes ingest cron continues during aim-1 — do NOT pause Hermes here (that's aim-2 STORAGE-01) -->
<!-- 3. DeepSeek key must be REAL (not `dummy`) before this plan can fully pass — `dummy` blocks Layer 2 + LightRAG entity extraction -->
<!-- 4. Agent does NOT SSH for mutating ops; operator runs the smokes -->
<!-- 5. Use existing scripts/local_e2e.sh modes — do NOT invent new modes -->
-->

</context>

<pre_conditions>

- aim-1-1 + aim-1-2 + aim-1-3 all complete (clean tree + venv + 6 ingest keys present)
- DeepSeek key is REAL, not `dummy` (else `wechat <url>` fails at LightRAG ainsert; `layer1 5` fails at Layer 2 — operator must verify before running)
- Operator has chosen a non-corp-restricted WeChat URL for the `wechat` smoke (any current WeChat MP article works; cn-east-mainland reaches WeChat directly)
- Operator has chosen a scratch storage path (suggestion: `/tmp/aim1-smoke/`) and confirmed it does not collide with kb-api or any prior aim-1-x artifact
</pre_conditions>

<tasks>

<task type="checkpoint:human-verify">
  <name>Task 1: Operator confirms scratch path + DeepSeek real-key + verifies production path will not be written</name>
  <channel>operator-prompt + decision</channel>
  <files>(read-only diagnostic on Aliyun)</files>
  <what-built>
    Pre-smoke confirmation that the smoke run will land in scratch storage and not contaminate the production LightRAG path.
  </what-built>
  <how-to-verify>
    Operator runs on Aliyun:

    ```bash
    cd /root/OmniGraph-Vault

    echo "=== confirm DeepSeek key is real, not dummy ==="
    venv/bin/python -c "
    import os, pathlib
    for line in pathlib.Path('/root/.hermes/.env').read_text().splitlines():
        if line.startswith('DEEPSEEK_API_KEY='):
            v = line.split('=',1)[1].strip()
            print('present-ok' if len(v) > 10 else f'present-short ({len(v)}c) — likely dummy')
            break
    "

    echo "=== production OMNIGRAPH_BASE_DIR (must NOT be written by smoke) ==="
    venv/bin/python -c "
    import os, pathlib
    for line in pathlib.Path('/root/.hermes/.env').read_text().splitlines():
        if line.startswith('OMNIGRAPH_BASE_DIR='):
            print(line.split('=',1)[1].strip())
            break
    else:
        print('OMNIGRAPH_BASE_DIR not in /root/.hermes/.env — harness will use default ~/.hermes/omonigraph-vault/')
    "

    echo "=== scratch path empty (operator chooses path) ==="
    SCRATCH=/tmp/aim1-smoke   # operator may choose differently; record decision in evidence
    mkdir -p "${SCRATCH}/lightrag_storage" "${SCRATCH}/.scratch" "${SCRATCH}/checkpoints"
    ls -la "${SCRATCH}"

    echo "=== production lightrag_storage state (must be unchanged across smokes) ==="
    ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | head -3 || echo "(production path empty or missing — expected pre-aim-2)"
    ```

    Expected:
    1. DeepSeek key reports `present-ok` (NOT `present-short` — `dummy` blocks Layer 2)
    2. Production `OMNIGRAPH_BASE_DIR` (or default `~/.hermes/omonigraph-vault/`) is NOT the chosen smoke scratch path
    3. Scratch path created and empty
    4. Production lightrag_storage state recorded for pre/post comparison
  </how-to-verify>
  <resume-signal>Reply: "scratch=&lt;path&gt;, deepseek=real, production-path=&lt;path&gt;, ready" or "blocked: deepseek=dummy" / "blocked: scratch collision"</resume-signal>
  <verify>
    <automated>MISSING — operator-channel diagnostic; verification is artifact at Task 4</automated>
  </verify>
  <done>
    Operator confirms: real DeepSeek key, scratch path chosen + empty, production path identified for non-write check.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 2: Operator runs `scripts/local_e2e.sh layer1 5` smoke against scratch storage</name>
  <channel>operator-prompt (mutating: writes log, scratch DB ops, possibly paid LLM calls)</channel>
  <files>(operator runs on Aliyun; produces .scratch/local-e2e-layer1-<ts>.log)</files>
  <what-built>
    Layer 1 smoke run on 5 candidates, log file under `/root/OmniGraph-Vault/.scratch/`, smoke artifacts under chosen scratch path.
  </what-built>
  <action>
    Operator runs on Aliyun:

    ```bash
    cd /root/OmniGraph-Vault

    # Override OMNIGRAPH_BASE_DIR to scratch for the smoke duration ONLY
    # The harness honors existing env vars per ${VAR:-default} per CLAUDE.md
    export OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke   # match Task 1 chosen path

    # Run the harness Layer 1 smoke mode (existing script, do NOT modify)
    ./scripts/local_e2e.sh layer1 5

    # Note: log file is auto-written to .scratch/local-e2e-layer1-<ts>.log per CLAUDE.md "Output goes to .scratch/local-e2e-<mode>-<ts>.log"
    ```

    Expected: Layer 1 runs against 5 candidates. Per CLAUDE.md "Layer 1 (Vertex AI) is reachable from local corp dev" — on Aliyun (cn-east-mainland, all providers reachable) it MUST be reachable too. Layer 2 may fire only on candidates that pass Layer 1; that's expected behavior, not a failure.

    After run completes, operator captures:

    ```bash
    LOG=$(ls -t .scratch/local-e2e-layer1-*.log | head -1)
    echo "=== log path ==="
    echo "$LOG"
    echo "=== exit code ==="
    grep -E "(exit|completed|finished|ERROR|Traceback)" "$LOG" | tail -20
    echo "=== last 30 lines ==="
    tail -30 "$LOG"
    echo "=== scratch storage state (post-smoke) ==="
    ls -la /tmp/aim1-smoke/lightrag_storage/ 2>/dev/null || echo "scratch lightrag empty"
    echo "=== production path state (must be unchanged from Task 1) ==="
    ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | head -3 || echo "(production unchanged)"
    ```
  </action>
  <how-to-verify>
    1. `tail -30 $LOG` shows successful completion (e.g., "Layer 1 batch finished" / "5 candidates processed" / no Python traceback)
    2. `grep -E "ERROR|Traceback" $LOG` returns 0 lines (or only known-noise warnings — operator's call)
    3. Scratch path may or may not have new content depending on Layer 1 behavior (Layer 1 typically writes classification results, not LightRAG storage)
    4. Production path `ls -la` output is byte-identical to Task 1's pre-smoke capture (no smoke contamination)
  </how-to-verify>
  <resume-signal>Type "layer1-done" with log path + tail summary, or describe failures (with log path + error excerpt)</resume-signal>
  <verify>
    <automated>MISSING — operator-channel; verification is log-tail artifact at Task 4</automated>
  </verify>
  <done>
    `layer1 5` smoke completes zero errors; log path recorded; production path unchanged.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 3: Operator runs `scripts/local_e2e.sh wechat <url>` smoke against scratch storage</name>
  <channel>operator-prompt (mutating: writes log, scratch lightrag_storage, paid Apify + DeepSeek + SiliconFlow + Vertex calls)</channel>
  <files>(operator runs on Aliyun; produces .scratch/local-e2e-wechat-<ts>.log)</files>
  <what-built>
    Single-URL E2E run, log file under `/root/OmniGraph-Vault/.scratch/`, LightRAG ainsert into scratch lightrag_storage.
  </what-built>
  <action>
    Operator runs on Aliyun (use any current non-corp-restricted WeChat MP article URL — Aliyun reaches WeChat directly, no MCP fallback needed):

    ```bash
    cd /root/OmniGraph-Vault
    export OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke   # SAME scratch path as Task 2 — keeps smokes co-located

    # Operator picks a current WeChat MP article URL — any active article works
    URL='<wechat-mp-article-url-operator-chooses>'

    ./scripts/local_e2e.sh wechat "$URL"

    # Log auto-written to .scratch/local-e2e-wechat-<ts>.log
    ```

    Expected behavior:
    - Apify scrapes the article (primary tier; CDP/MCP fallback not exercised on Aliyun)
    - Layer 2 classifies (DeepSeek must be reachable from Aliyun — that's the whole architectural point of migration)
    - Vision cascade describes images (SiliconFlow primary; cascade fallback if balance/RPM hit)
    - LightRAG ainsert commits to `/tmp/aim1-smoke/lightrag_storage/` (NOT production path)

    After run completes:

    ```bash
    LOG=$(ls -t .scratch/local-e2e-wechat-*.log | head -1)
    echo "=== log path ==="
    echo "$LOG"
    echo "=== errors / completion markers ==="
    grep -E "(ainsert|completed|ERROR|Traceback|method=)" "$LOG" | tail -30
    echo "=== last 30 lines ==="
    tail -30 "$LOG"
    echo "=== scratch lightrag_storage post-smoke (MUST be non-empty) ==="
    ls -la /tmp/aim1-smoke/lightrag_storage/
    du -sh /tmp/aim1-smoke/lightrag_storage/
    echo "=== production path post-smoke (MUST be unchanged) ==="
    ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | head -3 || echo "(production unchanged)"
    ```

    **CRITICAL:** if scratch `lightrag_storage/` is empty after `wechat <url>`, the smoke either failed or wrote to the wrong path — STOP, do not declare DEPLOY-04 complete; investigate.
  </action>
  <how-to-verify>
    1. `tail -30 $LOG` shows successful completion: scrape method (likely `apify`), Layer 2 verdict, vision per-image descriptions, LightRAG `ainsert finished` / similar
    2. `grep ERROR|Traceback` returns 0 lines (or operator-acknowledged known-noise)
    3. **Scratch `lightrag_storage/` is non-empty** — `du -sh` shows non-zero size (typically 50-500 MB for one article with vision)
    4. **Production path `ls -la` is byte-identical to pre-smoke capture** — no contamination
    5. Hermes cron continues running uninterrupted (operator does NOT pause Hermes for aim-1; that's aim-2's STORAGE-01 job)
  </how-to-verify>
  <resume-signal>Type "wechat-done" with log path + scratch-storage size + production-path-unchanged confirmation, or describe failures</resume-signal>
  <verify>
    <automated>MISSING — operator-channel; verification is log-tail + scratch-state artifact at Task 4</automated>
  </verify>
  <done>
    `wechat <url>` smoke completes zero errors; LightRAG ainsert lands in scratch path; production path unchanged.
  </done>
</task>

<task type="checkpoint:human-action">
  <name>Task 4: Build DEPLOY-04-EVIDENCE.md from Tasks 1-3 outputs</name>
  <channel>local-only</channel>
  <files>.planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md</files>
  <what-built>
    Single evidence file consolidating both smoke runs: command, env, log tail, scratch-storage proof, production-path-unchanged proof.
  </what-built>
  <action>
    Create `.planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md` with template:

    ```markdown
    # DEPLOY-04 Evidence — Local E2E smokes on Aliyun

    Phase: aim-1 (Code + env deploy)
    Date: 2026-05-21+
    Operator: [name / handle]
    Aliyun host: (alias `aliyun-vitaclaw`; details NOT recorded — public repo)

    ---

    ## Pre-smoke environment (Task 1)

    - Scratch path: `/tmp/aim1-smoke/` (or operator's choice — record actual path)
    - Production OMNIGRAPH_BASE_DIR: `[path]` — confirmed NOT equal to scratch
    - DeepSeek key state: `present-ok` (NOT `dummy`) — verified
    - Production lightrag_storage pre-smoke state:
      ```
      [paste ls -la output]
      ```

    ---

    ## Smoke 1: `scripts/local_e2e.sh layer1 5` (Task 2)

    Command:
    ```
    OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke ./scripts/local_e2e.sh layer1 5
    ```

    Log path: `/root/OmniGraph-Vault/.scratch/local-e2e-layer1-<ts>.log`

    Last 30 lines (zero errors):
    ```
    [paste tail -30 output]
    ```

    Errors / tracebacks: `[count from grep ERROR|Traceback]` (target: 0)

    Production path state post-smoke (must match pre-smoke):
    ```
    [paste ls -la output]
    ```
    **Production unchanged:** YES / NO

    ---

    ## Smoke 2: `scripts/local_e2e.sh wechat <url>` (Task 3)

    Command:
    ```
    OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke ./scripts/local_e2e.sh wechat <url-redacted-or-shortened>
    ```

    Log path: `/root/OmniGraph-Vault/.scratch/local-e2e-wechat-<ts>.log`

    Last 30 lines (zero errors):
    ```
    [paste tail -30]
    ```

    Errors / tracebacks: `[count]` (target: 0)

    Pipeline marker presence (sanity):
    - Scrape method: `[apify | cdp | mcp | ua]` (typically `apify` on Aliyun)
    - Layer 2 verdict appears in log: YES / NO
    - Vision provider used: `[siliconflow | openrouter | gemini]`
    - LightRAG ainsert completion: YES / NO

    Scratch lightrag_storage post-smoke (must be non-empty):
    ```
    [paste ls -la /tmp/aim1-smoke/lightrag_storage/]
    [paste du -sh /tmp/aim1-smoke/lightrag_storage/]
    ```

    Production path post-smoke (must match pre-smoke):
    ```
    [paste ls -la ~/.hermes/omonigraph-vault/lightrag_storage/]
    ```
    **Production unchanged:** YES / NO

    ---

    ## Hermes pre-cutover constraint check

    During aim-1 smoke runs, Hermes ingest cron continued operating (NOT paused — that's aim-2's STORAGE-01).

    Hermes status check (read-only — operator may forward via Hermes operator prompt OR query the `hermes` SSH host directly):
    ```
    [paste output of: ssh hermes "ps -ef | grep batch_ingest_from_spider | grep -v grep" — or equivalent]
    ```

    **Hermes uninterrupted:** YES / NO

    ---

    ## DEPLOY-04 verdict

    - `layer1 5` zero-error completion: YES / NO
    - `wechat <url>` zero-error completion: YES / NO
    - Both smokes' scratch storage populated correctly (smoke 2): YES / NO
    - Production lightrag_storage path unchanged across both smokes: YES / NO
    - Hermes ingest cron uninterrupted during aim-1: YES / NO
    - No literal secrets / no Aliyun connection details in this evidence file: YES (operator self-attests)

    **Overall DEPLOY-04 PASS:** YES / NO

    ---
    ```

    Operator commits locally:
    ```bash
    git add .planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md
    git commit -m "docs(aim-1): record DEPLOY-04 local E2E smoke evidence"
    ```
  </action>
  <how-to-verify>
    1. DEPLOY-04-EVIDENCE.md exists with all six sections (Pre-smoke, Smoke 1, Smoke 2, Hermes check, Verdict)
    2. Both smoke verdicts are YES; both production-unchanged checks are YES; scratch-non-empty for smoke 2 is YES
    3. Hermes uninterrupted YES (operator confirmation; agent does not need to verify Hermes itself)
    4. No literal secret value (API keys / tokens) in evidence file — `grep -E '(=sk-|apify_api_|siliconflow_)' DEPLOY-04-EVIDENCE.md` returns 0 hits
    5. No Aliyun host/port/user/IP in evidence file
    6. File committed locally
  </how-to-verify>
  <resume-signal>Type "evidence-recorded" with verdict block, or describe outstanding issues</resume-signal>
  <verify>
    <automated>cd c:\Users\huxxha\Desktop\OmniGraph-Vault; git log --oneline -1 .planning/phases/aim-1-code-env-deploy/DEPLOY-04-EVIDENCE.md</automated>
  </verify>
  <done>
    DEPLOY-04-EVIDENCE.md committed with both smoke verdicts = YES, production-unchanged = YES, Hermes uninterrupted = YES, no secrets / connection details.
  </done>
</task>

</tasks>

<verification>
**No-secrets check:** Evidence file uses placeholders for any URL operator chooses to redact; no API keys, tokens, SA JSON content. `grep -E '(=sk-|apify_api_|siliconflow_|"private_key")' DEPLOY-04-EVIDENCE.md` returns 0 hits.

**No-connection-details check:** No Aliyun host / port / user / IP in evidence. SSH alias `aliyun-vitaclaw` referenced abstractly.

**Hermes pre-cutover constraint:** Aim-1 does NOT pause Hermes. Aim-1 smoke ingests in scratch. Production path stays empty across all aim-1 work. This constraint is enforced by Tasks 1, 2, 3 (production-path-unchanged checks) and Task 4 evidence "Production unchanged: YES".

**DeepSeek real-key requirement:** `dummy` blocks Layer 2 + LightRAG entity extraction; Task 1 verifies real key before Tasks 2-3 run. Operator must place real key (or this plan halts pre-Task 2).

**Scratch storage discipline:** `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke` (or operator's choice) explicitly redirects all writes; matches READY-04 pattern (per ROADMAP SC4).

**Existing harness only:** The plan uses ONLY existing `scripts/local_e2e.sh` modes (`layer1 N` + `wechat <url>` per CLAUDE.md "Available modes"); no script modifications.
</verification>

<success_criteria>
**ROADMAP SC4 (line 81):** "`scripts/local_e2e.sh layer1 5` AND `scripts/local_e2e.sh wechat <url>` both reach completion with no errors in `.scratch/local-e2e-*-<ts>.log`; smoke ingests land in **scratch** storage (production path uncontaminated, same as READY-04 discipline) (DEPLOY-04)"

Mapped:

- ✅ `layer1 5` zero-error completion: Task 2 executes; Task 4 records `tail -30` + grep ERROR count = 0
- ✅ `wechat <url>` zero-error completion: Task 3 executes; Task 4 records same evidence pattern
- ✅ Logs in `.scratch/local-e2e-*-<ts>.log`: Task 2 + Task 3 capture log paths; harness writes to that path per CLAUDE.md
- ✅ Smoke ingests in scratch storage: `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke` redirects writes; Task 3 du -sh + ls verify scratch lightrag_storage non-empty post-smoke 2
- ✅ Production path uncontaminated: Task 1 baseline + Task 2 + Task 3 post-smoke ls comparisons + Task 4 verdict "Production unchanged: YES"

**REQ DEPLOY-04 Aliyun-reachability clause:** "Aliyun is in cn-east-mainland, all 3 LLM providers reachable" — `wechat <url>` smoke proves this empirically (DeepSeek + SiliconFlow + Vertex all called within one run).
</success_criteria>

<output>
After completion, create or extend `.planning/phases/aim-1-code-env-deploy/aim-1-4-SUMMARY.md` recording:
- Both smoke verdicts (PASS/FAIL)
- Scratch path used + post-smoke lightrag_storage size
- Production path unchanged across both smokes (YES required)
- Hermes uninterrupted (YES required)
- Total operator-channel SSH sessions (target: ~3-4 sessions across aim-1-1 through aim-1-4)
- Aim-1 phase complete signal (all 4 REQs DEPLOY-01..04 → PASS) → ready for aim-2 / kb-4-lite per Gate 1 closure execution order
</output>
