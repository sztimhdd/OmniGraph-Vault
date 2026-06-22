---
quick: 260605-pwl-probe-rerun-cert-rebuild
type: execute
mode: quick
wave: 1
depends_on: [260605-mz1]
files_modified:
  - .planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md  # Section 5 append only
  - .planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md     # new
  - .planning/STATE.md                                                            # row append
autonomous: true
requirements: [PWL-01, PWL-02, PWL-03, PWL-04]
must_haves:
  truths:
    - "venv certifi cacert.pem contains 4 corp roots (Cisco / Umbrella / EDC / cPKI) AND public roots (≥119 vanilla)"
    - "Probe `260605-mz1-concurrent-probe.py` is byte-identical to its 260605-mz1 state (sha256 match before/after)"
    - "Probe runs to completion OR halts on a documented Halt branch (A/B/C/D/E)"
    - "Section 5 of 260605-mz1-RESEARCH.md states a single verdict: GO | RISKY | BLOCKED-by-{perf|correctness|corruption|cert-rebuild}"
    - "Single forward-only commit lands on origin/main with explicit file list, no `--amend`, no `-A`"
  artifacts:
    - path: ".planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md"
      provides: "Section 5 — Probe re-run results (260605-pwl) appended; existing 4 sections untouched"
      contains: "## Section 5 — Probe re-run results (260605-pwl)"
    - path: ".planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md"
      provides: "Quick close-out: tasks completed, halt log, decision matrix row hit, commit hash"
    - path: ".scratch/260605-pwl-probe-output.txt"
      provides: "Raw probe stdout JSON (gitignored evidence) — captured to disk for SUMMARY citation"
  key_links:
    - from: ".scratch/260605-mz1-concurrent-probe.py"
      to: "venv certifi cacert.pem (rebuilt)"
      via: "`from lightrag import LightRAG` → tiktoken `o200k_base` bootstrap → openaipublic.blob.core.windows.net (TLS verified via certifi)"
      pattern: "no SSLCertVerificationError on tiktoken bootstrap"
    - from: "Section 5 verdict"
      to: "decision matrix row in this PLAN"
      via: "speedup_ratio + both_processed + corruption check"
      pattern: "verdict_string ∈ {GO, RISKY, BLOCKED-by-perf, BLOCKED-by-correctness, BLOCKED-by-corruption, BLOCKED-by-cert-rebuild}"
---

<objective>
Convert v1.2 batch_ingest concurrent rewrite viability from UNKNOWN → GO / RISKY / BLOCKED.

Parent quick `260605-mz1` (commits `b17bccb` + `adcb59d`) verified 3 walls SYSTEMIC across 5-day Aliyun audit but its local concurrent probe halted at corp Cisco Umbrella TLS interception of LightRAG's tiktoken bootstrap blob. **No wall_s data captured.** This follow-up rebuilds venv certifi (merge corp CA roots) then re-runs the SAME probe byte-identically and appends a Section 5 verdict to the existing RESEARCH.md.

Purpose: unblock v1.2 plan-phase decision. With a verdict, the orchestrator either fires `/gsd:plan-phase v1.2` (GO/RISKY) or queues alt-paths from parent RESEARCH.md Section 3 (BLOCKED).

Output:
- Section 5 appended to `260605-mz1-RESEARCH.md` (existing 4 sections untouched)
- `260605-pwl-SUMMARY.md` (this quick's close-out)
- STATE.md row append (last_activity)
- Single forward-only commit on origin/main
</objective>

<execution_context>
@C:/Users/huxxha/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/huxxha/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md
@.planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-SUMMARY.md
@.scratch/260525-rebuild-cacert.py
@.scratch/260605-mz1-concurrent-probe.py
@CLAUDE.md
@C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/corp_pem_rebuild_pattern.md
@C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_git_add_explicit_in_parallel_quicks.md
@C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_no_amend_in_concurrent_quicks.md

<known_state>
- Probe script `.scratch/260605-mz1-concurrent-probe.py` exists, 78 LoC, valid Python 3.13, byte-identical to its 260605-mz1 state (gitignored).
- Probe inputs `.dev-runtime/260605-mz1-probe/data/body_{1,2}.md` exist (verified by orchestrator pre-flight at 2026-06-05 — 14 KB / 9 KB). Article hashes: `c8cc5b1fb7` (img=2, "OpenClaw 入门") + `b37b0df5fb` (img=5, "智能体网络综述"). Both `layer2_verdict='ok'`.
- Rebuild script `.scratch/260525-rebuild-cacert.py` exists, ~125 LoC, validated runbook (per memory `corp_pem_rebuild_pattern`).
- Corp bundle source `~/.claude/certs/combined-ca-bundle.pem` exists (4 corp roots: Cisco / Umbrella / EDC / cPKI).
- Three env vars are pre-set on this dev machine and OVERRIDE certifi: `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE` → `C:\Users\huxxha\Downloads\corp-ca-bundle.pem` (corp-roots-only, no public DigiCert). Even after rebuild, `requests` calls fail unless these are unset for the probe shell.
- Read-only SSH to `aliyun-vitaclaw` is permitted via Bash tool (no operator-channel) — only relevant if Halt E fires.
</known_state>

<contracts>
**`.scratch/260605-mz1-concurrent-probe.py` — DO NOT MODIFY.** This is a fixed contract from quick 260605-mz1. The plan's whole point is byte-identical re-run.

Probe reads:
- `OMNIGRAPH_BASE_DIR=.dev-runtime/260605-mz1-probe/`
- `OMNIGRAPH_LLM_PROVIDER=deepseek` (prod parity)
- `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter,gemini`
- 2 article body files at `$OMNIGRAPH_BASE_DIR/data/body_{1,2}.md`

Probe runs:
1. PASS A: serial ainsert(body_1) → ainsert(body_2) → measure `wall_s_serial`
2. PASS B: clean storage, re-init LightRAG → `asyncio.gather(ainsert(body_1), ainsert(body_2))` → measure `wall_s_concurrent`
3. Post-conditions: graphml valid (XML parse OK), kv_store_doc_status valid (JSON parse OK), `both_processed` (both doc_ids status='processed')
4. Print JSON: `serial`, `concurrent`, `speedup_ratio`, `both_processed`, `serial_exception`, `concurrent_exception`, `graphml_valid`, `kv_store_valid`

If you need to add new logic, copy to a sibling `260605-pwl-concurrent-probe-v2.py` — but do NOT for this quick.
</contracts>

<decision_matrix>
After probe completes, the verdict is determined by exactly ONE row of this matrix:

| speedup_ratio | both_processed | corruption | Verdict | Section 5 conclusion |
|---|---|---|---|---|
| ≥ 1.7× | True | None | **GO** | v1.2 plan-phase fires; refined LoC ~+150-300 (asyncio.gather wrapper + per-task budget + partial-failure handling + telemetry + tests) |
| 1.4× ≤ s < 1.7× | True | None | **RISKY** | Spike follow-up quick to investigate which LightRAG/Qdrant lock site is serializing |
| < 1.4× | True | None | **BLOCKED-by-perf** | 4 alt paths in parent RESEARCH.md Sec 3; subprocess isolation likely best |
| any | False | None | **BLOCKED-by-correctness** | Concurrent ainsert breaks data; subprocess isolation forced |
| any | any | True | **BLOCKED-by-corruption** | Halt C; same as above |

"corruption" = `graphml_valid` is not `True` OR `kv_store_valid` is not `True` OR `concurrent_exception` is not None.
</decision_matrix>

<halt_branches>
**Halt A — `260525-rebuild-cacert.py` probe FAILS** (script auto-rolls back):
- Symptom: script exit code ≠ 0, OR stdout shows `post-rebuild corp hits=N < expected=4 - rolling back` / `post-rebuild probe RAISED ... rolling back`
- Backup at `venv/Lib/site-packages/certifi/cacert.pem.bak-260525-pre-rebuild` (auto-restored by script)
- Action: STOP. Do NOT proceed to T2/T3. Skip to T4 with verdict **BLOCKED-by-cert-rebuild** in Section 5. Cite exact stderr output.

**Halt B — env-var override forgotten**:
- Symptom: `env | grep -iE 'REQUESTS_CA_BUNDLE|SSL_CERT_FILE|CURL_CA_BUNDLE'` returns ANY of those vars set during probe shell
- Action: `unset REQUESTS_CA_BUNDLE SSL_CERT_FILE CURL_CA_BUNDLE` for the probe-launching shell, then re-launch probe. Do NOT modify settings globally.
- If unset is forgotten and probe SSL-fails despite cert rebuild, this is the cause — fix and retry. Do NOT mark BLOCKED for this.

**Halt C — kv_store / graphml corruption during concurrent ainsert** (the original Halt #2 from parent quick):
- Symptom: probe stdout shows `graphml_valid: "corrupt: ..."` OR `kv_store_valid: "corrupt: ..."` OR `concurrent_exception: "..."` (not None) OR `both_processed: false`
- Action: STOP probe (already complete — single run). Do NOT retry. Mark **BLOCKED-by-correctness** OR **BLOCKED-by-corruption** in Section 5. Capture full probe JSON to `.scratch/260605-pwl-probe-output.txt`. Diagnostic: graphml SHA before/after, kv_store_doc_status JSON dump showing inconsistency, both_processed boolean.

**Halt D — Vertex 429** (the original Halt #3, unlikely):
- Symptom: probe exception traceback contains `429` / `RESOURCE_EXHAUSTED` / `Quota exceeded`
- Action: probe is small (2 articles × 2 passes); if 429 fires, surface in Section 5 and mark **BLOCKED-by-quota**. Capture exception. Do NOT retry.

**Halt E — body data missing**:
- Symptom: `.dev-runtime/260605-mz1-probe/data/body_{1,2}.md` not present (e.g., user re-cloned repo, dir cleaned). T2 verifies presence.
- Action: re-extract via read-only SSH `ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT body FROM articles WHERE content_hash IN ('c8cc5b1fb7','b37b0df5fb') AND layer2_verdict='ok'\""` then write to local `body_{1,2}.md`. Prefer SSH+sqlite re-extract over `scp` (deterministic; no path ambiguity). Then proceed to T3.

**Halt log requirement:** any halt fires → STOP at that boundary, jump to T4 with the appropriate Section 5 verdict (do NOT swallow the failure into "GO/RISKY/BLOCKED" generic).
</halt_branches>

<task_count_justification>
This quick has 4 tasks (above the standard 1-3 quick cap). Justification follows the same shape as parent 260605-mz1's 4-task plan:

- **T1 (cert rebuild + smoke)** — environment mutation; isolated failure modes (Halt A script rollback, Halt B env-var trap). MUST verify success before any probe run, otherwise we're back at Halt #1 from parent.
- **T2 (probe pre-flight + body data hydrate)** — verify articles present OR re-pull from Aliyun (Halt E); verify env vars unset; verify provider config.
- **T3 (probe run + capture)** — execute the probe (the actual measurement); halt branches C/D fire here.
- **T4 (Section 5 append + commit)** — synthesis + git discipline; separated so pre-commit checks (no .scratch leak, no probe modification, no parent RESEARCH structure broken) can run cleanly.

Combining T1+T2 risks running the probe with stale env-var override (Halt B silent failure mode). Combining T3+T4 risks committing partial Section 5 if Halt C/D fires mid-write.
</task_count_justification>

<forbidden>
- ❌ Modify `.scratch/260605-mz1-concurrent-probe.py` (sha256 before/after MUST match — verify in T3)
- ❌ Modify any production source (`batch_ingest_from_spider.py`, `ingest_wechat.py`, `kb/`, `lib/`, `kg_synthesize.py`, etc.)
- ❌ Modify `~/.hermes/` anything
- ❌ Modify Aliyun anything (read-only SSH only — Halt E uses `sqlite3 SELECT`)
- ❌ Run prod batch_ingest at any scale
- ❌ `git --amend` / `git reset --hard` / `git push --force` / `git rebase -i`
- ❌ `git add -A` / `git add .` (always explicit file list)
- ❌ Co-Authored-By in commit messages
- ❌ Run probe with corp env vars still set (`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE`)
- ❌ Modify settings globally (registry / system env)
- ❌ Create a new RESEARCH.md for this quick — Section 5 appends to the parent's existing file
</forbidden>
</context>

<tasks>

<task type="auto">
  <name>T1: Rebuild venv certifi with corp CA roots (atomic + probed)</name>
  <files>
    venv/Lib/site-packages/certifi/cacert.pem (mutated; gitignored)
    venv/Lib/site-packages/certifi/cacert.pem.bak-260525-pre-rebuild (created if missing; gitignored)
    .scratch/260605-pwl-cert-rebuild.log (new; gitignored)
  </files>
  <action>
    Run the canonical atomic rebuild script per memory `corp_pem_rebuild_pattern`. Three steps in sequence (single PowerShell or Git Bash run):

    **Step 1 — backup** (only if backup not yet present):
    ```
    if not exists venv/Lib/site-packages/certifi/cacert.pem.bak-260525-pre-rebuild:
        copy venv/Lib/site-packages/certifi/cacert.pem -> venv/Lib/site-packages/certifi/cacert.pem.bak-260525-pre-rebuild
    ```

    **Step 2 — force-restore vanilla certifi** (mandatory; the script's `if corp >= 4 already-have shortcut` does NOT trigger when bundle is half-merged):
    ```
    venv/Scripts/pip install --force-reinstall --no-deps certifi
    ```

    **Step 3 — atomic rebuild** (the script does the rest: parse corp PEM strictly, re-serialize with newlines, atomic .tmp + os.replace, ssl probe, auto-rollback on failure):
    ```
    venv/Scripts/python.exe .scratch/260525-rebuild-cacert.py 2>&1 | tee .scratch/260605-pwl-cert-rebuild.log
    ```

    **Expected stdout (last line):** `REBUILD OK: 123 total certs, 4 corp hits` (vanilla 119 + corp 4; total may drift ±2 with certifi version, but corp hits MUST be exactly 4).

    **Halt A:** if script exits non-zero OR last log line is `rolling back` → STOP this quick. Skip T2/T3. Jump to T4 with verdict **BLOCKED-by-cert-rebuild**, citing the rebuild log.

    **Note for executor:** the script itself enforces atomic .tmp + os.replace + ssl probe + auto-rollback. Trust it — do NOT manually `cat >>` the corp bundle (broken per memory `corp_pem_rebuild_pattern`).
  </action>
  <verify>
    <automated>
      venv/Scripts/python.exe -c "import ssl, certifi; ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.load_verify_locations(cafile=certifi.where()); certs=ctx.get_ca_certs(); hits=sum(1 for c in certs if any(k in dict(x[0] for x in c['subject']).get('commonName','') for k in ('Cisco','Umbrella','EDC','cPKI'))); assert len(certs) >= 119 and hits == 4, f'FAIL: total={len(certs)}, corp={hits}'; print(f'OK: total={len(certs)}, corp={hits}')"
    </automated>
    Expected stdout: `OK: total=123, corp=4` (or total within 119-130 range; corp MUST be 4).
    If verify fails: Halt A applies — restore from `cacert.pem.bak-260525-pre-rebuild`, log the failure, jump to T4 BLOCKED-by-cert-rebuild.
  </verify>
  <done>
    cacert.pem contains exactly 4 corp roots AND ≥119 vanilla roots. The ssl ground-truth probe loads the bundle without raising. Rebuild log saved to `.scratch/260605-pwl-cert-rebuild.log`.
  </done>
</task>

<task type="auto">
  <name>T2: Probe pre-flight — verify env, body data, probe sha256</name>
  <files>
    .dev-runtime/260605-mz1-probe/data/body_1.md (read-verify; gitignored)
    .dev-runtime/260605-mz1-probe/data/body_2.md (read-verify; gitignored)
    .scratch/260605-pwl-probe-sha256-before.txt (new; gitignored)
  </files>
  <action>
    **Step 1 — verify body data exists.** If missing, Halt E:
    ```
    test -s .dev-runtime/260605-mz1-probe/data/body_1.md && \
    test -s .dev-runtime/260605-mz1-probe/data/body_2.md
    ```
    If either missing → Halt E recovery via read-only SSH:
    ```
    mkdir -p .dev-runtime/260605-mz1-probe/data/
    ssh aliyun-vitaclaw "sqlite3 -separator $'\t' /root/OmniGraph-Vault/data/kol_scan.db \"SELECT body FROM articles WHERE content_hash='c8cc5b1fb7' AND layer2_verdict='ok' LIMIT 1\"" > .dev-runtime/260605-mz1-probe/data/body_1.md
    ssh aliyun-vitaclaw "sqlite3 -separator $'\t' /root/OmniGraph-Vault/data/kol_scan.db \"SELECT body FROM articles WHERE content_hash='b37b0df5fb' AND layer2_verdict='ok' LIMIT 1\"" > .dev-runtime/260605-mz1-probe/data/body_2.md
    test -s .dev-runtime/260605-mz1-probe/data/body_1.md && test -s .dev-runtime/260605-mz1-probe/data/body_2.md
    ```
    (kol_scan.db is symlinked → /root/OmniGraph-Vault/data/kol_scan.db on Aliyun per project memory.)

    **Step 2 — capture probe sha256 (byte-identical contract):**
    ```
    sha256sum .scratch/260605-mz1-concurrent-probe.py > .scratch/260605-pwl-probe-sha256-before.txt
    cat .scratch/260605-pwl-probe-sha256-before.txt
    ```
    Save the hash; T3 will compare post-run.

    **Step 3 — env-var sanity** (Halt B prevention):
    ```
    env | grep -iE 'REQUESTS_CA_BUNDLE|SSL_CERT_FILE|CURL_CA_BUNDLE' || echo "OK: corp CA env vars NOT set in current shell"
    ```
    If ANY of the 3 vars are listed → mandatory unset for the probe-launching shell in T3 (encoded in T3 action). DO NOT unset globally / persistently.

    **Step 4 — provider config sanity:**
    ```
    grep -E '^(DEEPSEEK_API_KEY|GEMINI_API_KEY|OMNIGRAPH_GEMINI_KEY)=' ~/.hermes/.env | sed 's/=.*/=<set>/'
    ```
    DEEPSEEK_API_KEY MUST be set (probe uses `OMNIGRAPH_LLM_PROVIDER=deepseek`); empty/missing → halt with cite, do NOT silent-skip. Embedding requires `OMNIGRAPH_GEMINI_KEY` (or `GEMINI_API_KEY`) — also MUST be set.
  </action>
  <verify>
    <automated>
      ls -la .dev-runtime/260605-mz1-probe/data/body_1.md .dev-runtime/260605-mz1-probe/data/body_2.md && \
      test -s .scratch/260605-pwl-probe-sha256-before.txt && \
      grep -q '^DEEPSEEK_API_KEY=<set>' &lt;(grep -E '^(DEEPSEEK_API_KEY|GEMINI_API_KEY|OMNIGRAPH_GEMINI_KEY)=' ~/.hermes/.env | sed 's/=.*/=<set>/') && \
      echo "PRE-FLIGHT OK"
    </automated>
    Expected stdout ends with `PRE-FLIGHT OK`.
  </verify>
  <done>
    Both body files exist + non-empty. Probe sha256 captured to `.scratch/260605-pwl-probe-sha256-before.txt`. DEEPSEEK_API_KEY and embedding key both present in `~/.hermes/.env`. Env-var override status documented (set or unset).
  </done>
</task>

<task type="auto">
  <name>T3: Run probe byte-identically + capture output</name>
  <files>
    .scratch/260605-pwl-probe-output.txt (new; gitignored — full probe stdout JSON + stderr)
    .scratch/260605-pwl-probe-sha256-after.txt (new; gitignored)
  </files>
  <action>
    Run the probe in a single shell invocation that:
    1. Unsets the 3 corp CA env vars for THIS shell only (Halt B fix; non-persistent)
    2. Sets the probe's required env vars (provider config + isolated base dir)
    3. Loads `~/.hermes/.env` for DeepSeek/Gemini keys
    4. Invokes the probe with the 2 article hashes as positional args
    5. Captures stdout+stderr to `.scratch/260605-pwl-probe-output.txt`

    **Single-shell run** (Git Bash; PowerShell variant included as fallback below):
    ```
    set -a; source ~/.hermes/.env; set +a; \
    unset REQUESTS_CA_BUNDLE SSL_CERT_FILE CURL_CA_BUNDLE; \
    OMNIGRAPH_BASE_DIR=$(realpath .dev-runtime/260605-mz1-probe) \
    OMNIGRAPH_LLM_PROVIDER=deepseek \
    OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter,gemini \
    LIGHTRAG_EMBEDDING_TIMEOUT=180 \
    venv/Scripts/python.exe .scratch/260605-mz1-concurrent-probe.py c8cc5b1fb7 b37b0df5fb \
    > .scratch/260605-pwl-probe-output.txt 2>&1
    echo "exit=$?"
    ```

    PowerShell variant (if Git Bash unavailable):
    ```
    Get-Content $env:USERPROFILE\.hermes\.env | ForEach-Object { if ($_ -match '^([^=#]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] } }
    Remove-Item Env:REQUESTS_CA_BUNDLE,Env:SSL_CERT_FILE,Env:CURL_CA_BUNDLE -ErrorAction SilentlyContinue
    $env:OMNIGRAPH_BASE_DIR = (Resolve-Path .dev-runtime/260605-mz1-probe).Path
    $env:OMNIGRAPH_LLM_PROVIDER = 'deepseek'
    $env:OMNIGRAPH_VISION_SKIP_PROVIDERS = 'siliconflow,openrouter,gemini'
    $env:LIGHTRAG_EMBEDDING_TIMEOUT = '180'
    venv\Scripts\python.exe .scratch\260605-mz1-concurrent-probe.py c8cc5b1fb7 b37b0df5fb *> .scratch\260605-pwl-probe-output.txt
    "exit=$LASTEXITCODE"
    ```

    **Time budget:** 5-30 min wall (LightRAG entity extract typically 30-180s × 2 articles × 2 passes). If still running at T+45 min, halt — symptom of stuck embedding worker (see ISSUES #31 / #32 / #33 background).

    **After probe completes** (regardless of exit code), capture sha256 and compare:
    ```
    sha256sum .scratch/260605-mz1-concurrent-probe.py > .scratch/260605-pwl-probe-sha256-after.txt
    diff .scratch/260605-pwl-probe-sha256-before.txt .scratch/260605-pwl-probe-sha256-after.txt
    ```
    Diff MUST be empty (byte-identical contract). If diff non-empty: surface as a CRITICAL finding in T4 — the probe was modified during run, voiding the experiment.

    **Parse probe output:**
    - `.scratch/260605-pwl-probe-output.txt` should contain a JSON object printed at end with keys: `wall_s_serial`, `wall_s_concurrent`, `speedup_ratio`, `both_processed`, `serial_exception`, `concurrent_exception`, `graphml_valid`, `kv_store_valid`, `hashes`.
    - If JSON parse fails (probe crashed before printing) → Halt C/D depending on traceback content. Capture full stderr for Section 5.

    **Halt C trigger** (corruption): `graphml_valid != True` OR `kv_store_valid != True` OR `concurrent_exception != null` OR `both_processed != true`.

    **Halt D trigger** (Vertex 429): traceback contains `429` / `RESOURCE_EXHAUSTED` / `Quota exceeded`. Probe uses DeepSeek for LLM but Gemini for embedding — embedding 429 hits here.

    **No retries.** Single run is the data point. Multiple runs may smear results from cached entities and bias speedup.
  </action>
  <verify>
    <automated>
      test -s .scratch/260605-pwl-probe-output.txt && \
      diff .scratch/260605-pwl-probe-sha256-before.txt .scratch/260605-pwl-probe-sha256-after.txt && \
      python -c "import json,re; t=open('.scratch/260605-pwl-probe-output.txt').read(); m=re.search(r'\{[\s\S]+\}', t); j=json.loads(m.group(0)) if m else None; print('OK' if j and 'wall_s_serial' in j else 'PROBE-CRASHED'); print(j)" 2>&1 | tee /dev/null
    </automated>
    Expected stdout starts with `OK` AND prints a dict with `wall_s_serial` key. If `PROBE-CRASHED`: probe halted before completion — content of `.scratch/260605-pwl-probe-output.txt` informs which Halt fired (B/C/D).
    sha256 diff MUST be empty (byte-identical).
  </verify>
  <done>
    Probe output captured to `.scratch/260605-pwl-probe-output.txt`. Probe script sha256 matches before/after (byte-identical). One of: (a) probe completed → JSON contains `wall_s_serial`/`wall_s_concurrent`/`speedup_ratio`/`both_processed`/`graphml_valid`/`kv_store_valid`; OR (b) probe halted → traceback in stdout/stderr identifies Halt branch.
  </done>
</task>

<task type="auto">
  <name>T4: Append Section 5 to RESEARCH.md + STATE row + atomic commit</name>
  <files>
    .planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md (append-only; existing 4 sections untouched)
    .planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md (new)
    .planning/STATE.md (last_activity row append)
  </files>
  <action>
    **Step 1 — apply decision matrix.** Read `.scratch/260605-pwl-probe-output.txt`, parse JSON, look up the verdict in the matrix above. The verdict string MUST be exactly one of:
    - `GO` (speedup ≥1.7× AND both_processed AND no corruption)
    - `RISKY` (1.4× ≤ speedup < 1.7× AND both_processed AND no corruption)
    - `BLOCKED-by-perf` (speedup < 1.4× AND both_processed AND no corruption)
    - `BLOCKED-by-correctness` (both_processed = False, no graph corruption)
    - `BLOCKED-by-corruption` (graphml/kv corrupt OR concurrent_exception)
    - `BLOCKED-by-quota` (Halt D Vertex 429)
    - `BLOCKED-by-cert-rebuild` (Halt A — only if T1 failed and we skipped to T4)

    **Step 2 — append Section 5 to existing RESEARCH.md.** Use `Read` then `Edit` (NOT Write — Edit prevents accidental whole-file overwrite of the parent's 4 sections). Insertion point: after the existing `## Cross-references` section's last line. Section 5 template:

    ```markdown

    ## Section 5 — Probe re-run results (260605-pwl)

    **Quick:** `260605-pwl-probe-rerun-cert-rebuild`
    **Date:** 2026-06-05/06 ADT
    **Pre-step:** `.scratch/260525-rebuild-cacert.py` rebuild — `{rebuild_status_one_line}` (log: `.scratch/260605-pwl-cert-rebuild.log`)
    **Probe contract:** byte-identical to 260605-mz1 (sha256 verified before/after)

    ### Run results

    | Metric | Value |
    |---|---|
    | PASS A serial wall_s | `{wall_s_serial}` |
    | PASS B 2-concurrent wall_s | `{wall_s_concurrent}` |
    | Speedup ratio | `{speedup_ratio}` |
    | both_processed | `{both_processed}` |
    | graphml_valid | `{graphml_valid}` |
    | kv_store_valid | `{kv_store_valid}` |
    | serial_exception | `{serial_exception_or_None}` |
    | concurrent_exception | `{concurrent_exception_or_None}` |

    ### Verdict — v1.2 batch_ingest concurrent rewrite viability

    **{VERDICT}** — {one-line rationale citing the decision matrix row hit}

    {2-3 paragraphs of analysis tied to the verdict:}
    - If GO: refined LoC estimate, critical path through `batch_ingest_from_spider.py`, telemetry hooks needed
    - If RISKY: which lock site to spike (Qdrant client pool / kv_store_doc_status mutex / LightRAG entity-merge global lock)
    - If BLOCKED-*: which alt path from Section 3 is recommended (subprocess isolation / parallel systemd / wait upstream / raise wrapper cap)

    ### Halt log

    {list any Halt branches that fired in this re-run; if none: "No halts fired — probe completed clean."}

    ### Cross-references

    - Probe output: `.scratch/260605-pwl-probe-output.txt` (gitignored, raw JSON)
    - Cert rebuild log: `.scratch/260605-pwl-cert-rebuild.log` (gitignored)
    - sha256 contract: `.scratch/260605-pwl-probe-sha256-{before,after}.txt`
    - Quick close-out: `.planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md`
    ```

    **Step 3 — write SUMMARY.md.** Standard quick close-out template:
    - Header: quick id, date, mode (execute), status (COMMITTED), commit hash (filled post-commit if needed via forward-fix per `feedback_no_amend_in_concurrent_quicks.md` — prefer pre-write if hash known)
    - Tasks completed table (4 rows: T1-T4)
    - Halt log
    - Verdict + matrix row hit
    - Artifacts produced (Section 5 in RESEARCH.md, SUMMARY.md, STATE.md row, .scratch/* gitignored evidence files)
    - Discipline note: explicit `git add` only, no `--amend`, byte-identical probe contract honored

    **Step 4 — STATE.md row append.** Insert a `Last activity` row at the top of the activity log section per existing convention (mirror format from line 36 of STATE.md). Update `last_updated` ISO8601 timestamp + `last_activity` summary string. Do NOT touch `progress` counters (this is a research quick, not a phase plan/plan completion).

    **Step 5 — atomic commit.** Per `feedback_git_add_explicit_in_parallel_quicks` strengthened pattern, run `git add` + `git commit` + `git push` as a single Bash &&-chain to minimize sibling-quick `-A` absorption window:

    ```
    git add \
      .planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md \
      .planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-PLAN.md \
      .planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md \
      .planning/STATE.md && \
    git commit -m "$(cat <<'EOF'
    docs(quick-260605-pwl): probe-rerun results — v1.2 viability {VERDICT}

    Pre-step: .scratch/260525-rebuild-cacert.py rebuild OK ({N} total / 4 corp hits)
    Probe re-run (byte-identical to 260605-mz1):
    - serial: {N}s
    - 2-concurrent: {M}s
    - speedup: {ratio}x
    - both_processed: {bool}
    - corruption: {None|description}

    Verdict for v1.2 batch_ingest concurrent rewrite: {GO|RISKY|BLOCKED-by-*}
    {One-line rationale citing decision matrix row hit}

    Files: 260605-mz1-RESEARCH.md (Section 5 append), 260605-pwl-{PLAN,SUMMARY}.md, STATE.md
    EOF
    )" && \
    git push origin main
    ```

    **Post-commit audit** (per `feedback_git_add_explicit_in_parallel_quicks`):
    ```
    git show --stat HEAD
    ```
    Verify exactly the 4 files listed above are in the commit (no sibling-quick artifacts absorbed). If absorption detected → forward-fix only (attribution-drift note in SUMMARY.md), NEVER `--amend` per `feedback_no_amend_in_concurrent_quicks`.

    **Forbidden in commit message:** `Co-Authored-By:` (CLAUDE.md global rule).
  </action>
  <verify>
    <automated>
      grep -q '^## Section 5 — Probe re-run results (260605-pwl)$' .planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md && \
      grep -qE '^\*\*\{?(GO|RISKY|BLOCKED-by-(perf|correctness|corruption|quota|cert-rebuild))\}?\*\*' .planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md && \
      test -s .planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md && \
      grep -q "260605-pwl" .planning/STATE.md && \
      git log --oneline -1 | grep -q "quick-260605-pwl" && \
      git show --stat HEAD | grep -qE "(260605-mz1-RESEARCH|260605-pwl-(PLAN|SUMMARY)|STATE)\.md" && \
      echo "T4 OK"
    </automated>
    Expected stdout ends with `T4 OK`.
    Manual cross-check (no automated test):
    - parent RESEARCH.md still has its original 4 sections (1, 2, 3, 4) before the new Section 5 — read the first 154 lines, confirm unchanged structure
    - commit subject contains exactly one verdict token from {GO, RISKY, BLOCKED-by-perf, BLOCKED-by-correctness, BLOCKED-by-corruption, BLOCKED-by-quota, BLOCKED-by-cert-rebuild}
    - commit body contains numeric serial/concurrent/speedup/both_processed values
    - `git show HEAD --name-only` lists exactly 4 files (no `.scratch/` absorbed)
  </verify>
  <done>
    Section 5 appended to RESEARCH.md with verdict + run results + halt log + cross-refs. SUMMARY.md created. STATE.md row append. Single forward-only commit on origin/main with explicit file list. v1.2 viability gate is now GO/RISKY/BLOCKED — orchestrator can pick next action without re-running probe.
  </done>
</task>

</tasks>

<verification>
After all 4 tasks complete, the orchestrator can ask one closure question: **"What's the v1.2 batch_ingest concurrent rewrite verdict?"**

Answer must be exactly one of:
- `GO` → fire `/gsd:plan-phase v1.2` next (refined LoC ~+150-300)
- `RISKY` → fire follow-up spike quick to investigate the dominant lock site
- `BLOCKED-by-perf` → pick alt path from parent RESEARCH.md Section 3 (subprocess isolation likely best)
- `BLOCKED-by-correctness` / `BLOCKED-by-corruption` → subprocess isolation forced; concurrent ainsert is unsafe
- `BLOCKED-by-quota` → embedding RPM cap hit; investigate per-key rotation OR Vertex paid-tier migration before retrying
- `BLOCKED-by-cert-rebuild` → environment unblocker quick needed before re-attempting probe

The verdict must be cited in the commit subject AND in Section 5's "Verdict" line, identical strings.
</verification>

<success_criteria>
1. `venv/Lib/site-packages/certifi/cacert.pem` ssl-loadable AND contains exactly 4 corp roots (Cisco / Umbrella / EDC / cPKI) AND ≥119 vanilla roots.
2. `.scratch/260605-mz1-concurrent-probe.py` byte-identical before/after probe run (sha256 match).
3. `.scratch/260605-pwl-probe-output.txt` exists and contains either (a) a JSON object with `wall_s_serial`/`wall_s_concurrent`/`speedup_ratio`/`both_processed`/`graphml_valid`/`kv_store_valid` keys; OR (b) a halt traceback identifying Halt B/C/D.
4. `260605-mz1-RESEARCH.md` Section 5 appended (parent's existing Sections 1-4 byte-identical pre/post — read line range to confirm).
5. `260605-pwl-SUMMARY.md` exists with verdict + commit hash + halt log + matrix row hit.
6. `STATE.md` last_activity row updated with this quick's outcome.
7. Single forward-only commit on `origin/main` with explicit file list (4 files: RESEARCH.md, PLAN.md, SUMMARY.md, STATE.md). Push accepted (forward-only). No `--amend` / `git reset` / `--force-push`. No `git add -A` / `git add .`.
8. v1.2 viability state transitioned UNKNOWN → one of {GO, RISKY, BLOCKED-by-{perf,correctness,corruption,quota,cert-rebuild}}.
</success_criteria>

<output>
After completion, create `.planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md` with:
- Header: quick id, date, mode (execute), status, commit hash
- Tasks completed table (T1-T4 + halt status per task)
- Halt log (which Halts fired, with symptom + action taken)
- Verdict + decision matrix row hit + verbatim probe metrics
- Artifacts list (RESEARCH.md Section 5 anchor, SUMMARY.md, STATE.md row, .scratch/* gitignored evidence)
- Discipline notes: explicit git add, no amend/reset/force, byte-identical probe contract honored, env-var trap addressed in T3
- Cross-refs: parent quick `260605-mz1`, memory `corp_pem_rebuild_pattern`, decision matrix in PLAN.md, ISSUES #38/#39/#40
</output>
