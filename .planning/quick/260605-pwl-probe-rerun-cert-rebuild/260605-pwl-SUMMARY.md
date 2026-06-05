# 260605-pwl — Execution Summary

**Quick:** 260605-pwl-probe-rerun-cert-rebuild
**Date:** 2026-06-05 ADT
**Mode:** execute (quick)
**Status:** COMMITTED — partial (Halt F fired at T3 boundary, T4 verdict written)
**Commit:** filled in post-commit (forward-only on origin/main; explicit-add discipline honored)

## Tasks completed

| # | Task | Status | Done condition |
|---|---|---|---|
| 1 | T1 Cert rebuild (atomic via `.scratch/260525-rebuild-cacert.py`) | DONE | `REBUILD OK: 123 total certs, 4 corp hits`; ssl ground-truth probe passes; log preserved at `.scratch/260605-pwl-cert-rebuild.log`; backup at `venv/Lib/site-packages/certifi/cacert.pem.bak-260605-pre-pwl` |
| 2 | T2 Pre-flight (body data verify, sha256 capture, env-var sanity, provider-key audit) | DONE | body_1.md (14172 B) + body_2.md (9431 B) verified; probe sha256 `57308c595db37718...` captured; 3 env vars detected; **DEEPSEEK_API_KEY MISSING** flagged at step 4 |
| 3 | T3 Probe run | **HALTED (Halt F)** at boundary | Probe NOT launched — pre-flight identified TWO blockers: (a) `DEEPSEEK_API_KEY` absent in `~/.hermes/.env` and shell, (b) corp Cisco Umbrella TLS-blocks `api.deepseek.com` (`SSLV3_ALERT_HANDSHAKE_FAILURE` even with rebuilt cert). sha256 byte-identical contract preserved. Diagnostic captured to `.scratch/260605-pwl-probe-output.txt`. |
| 4 | T4 Section 5 append + SUMMARY + atomic commit | DONE | Section 5 appended to parent `260605-mz1-RESEARCH.md` (pre-existing 4 sections untouched); SUMMARY.md written; atomic chain `git add <explicit> && git commit && git push origin main`; `git show --stat HEAD` audit clean. |

## Halt triggers fired

### Halt F (NEW — pre-flight halt at T3 boundary)

**Trigger:** T2 step 4 (provider-key audit) + post-T1 reachability probe revealed two blockers that no Halt branch in the plan covered.

**Blocker 1 — missing `DEEPSEEK_API_KEY` on the Hermes prod-runtime env path:**

- `~/.hermes/.env` content (T2 step 4 grep): `GEMINI_API_KEY=<set>`, `APIFY_TOKEN=<set>`, `FIRECRAWL_API_KEY=<set>`, `CDP_URL=<set>`, `APIFY_TOKEN_BACKUP=<set>` — **no `DEEPSEEK_API_KEY`**.
- Shell `DEEPSEEK_API_KEY: <NOT SET>`.
- Probe contract requires `OMNIGRAPH_LLM_PROVIDER=deepseek` (prod parity); `lib.llm_deepseek._get_client()` lazily reads `DEEPSEEK_API_KEY` on first ainsert call and raises `RuntimeError` if missing.
- Per PLAN.md T2 step 4: "DEEPSEEK_API_KEY MUST be set... empty/missing → halt with cite, do NOT silent-skip."
- **Scope qualifier (added post-adversarial-verify 2026-06-05):** orchestrator independently verified that the key DOES exist non-empty in two project-local env files this quick's T2 step 4 missed — `.dev-runtime/.env` (local-dev runtime) and `databricks-deploy/.env.local` (Databricks Apps local UAT). The env gap is specific to the Hermes prod-runtime invocation path that the probe launcher reads (`~/.hermes/.env` via `config.py:load_env`). Blocker 2 below TLS-blocks all corp-laptop paths regardless of which env file provides the key, so this distinction does not change the BLOCKED verdict — but a future probe-rerun quick that runs locally should source the key from `.dev-runtime/.env`, not re-stamp it into `~/.hermes/.env`.

**Blocker 2 — corp Cisco Umbrella TLS-block on `api.deepseek.com`:**

Post-T1 cert rebuild reachability probe (env-vars unset, certifi=123/4 corp):

```text
OK   tiktoken bootstrap blob (openaipublic.blob.core.windows.net): HTTP 400  ← server-side; TLS handshake succeeded
FAIL DeepSeek (api.deepseek.com): URLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]
OK   Gemini (generativelanguage.googleapis.com): HTTP 404                    ← server-side; TLS handshake succeeded
```

- Tiktoken bootstrap (parent quick Halt #1 root cause) **RESOLVED** by cert rebuild — TLS layer now succeeds (HTTP 400 is the Azure server saying "bad URL" for a bare HEAD on root, which means the request reached the server).
- Gemini also TLS-reachable (HTTP 404 is server response).
- DeepSeek TLS-handshake **DROPPED** by Cisco Umbrella — corp does not re-sign DeepSeek's chain (probably because DeepSeek isn't on Cisco's intercept list); instead the handshake itself fails. Cert rebuild does NOT fix this.

**Action:** halted at T3 boundary per plan rule ("halt with cite, do NOT silent-skip"); probe NOT launched; sha256 byte-identical contract preserved (before+after match `57308c595db37718...`); diagnostic captured to `.scratch/260605-pwl-probe-output.txt` (73 lines).

**Mapping to decision matrix:** closest row is `BLOCKED-by-cert-rebuild` (rationale: "environment unblocker quick needed before re-attempting probe"), but the blocker scope is broader than cert. Surfaced as **`BLOCKED-by-environment`** in Section 5 verdict to capture the extended scope (key + network, not just cert).

### Halts A / B / C / D / E — NOT fired

- **A (cert rebuild fail):** NOT fired — `REBUILD OK: 123 total certs, 4 corp hits`, no rollback
- **B (env-var override forgotten):** NOT fired — env vars detected at T2 step 3 (`REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE` all set); would have been `unset`-ed for T3 probe shell, but T3 was not launched (Halt F preempted)
- **C (kv_store / graphml corruption during concurrent ainsert):** NOT fired — probe never reached ainsert
- **D (Vertex 429):** NOT fired — probe never reached Vertex
- **E (body data missing):** NOT fired — both body files present (14172 B / 9431 B)

## Final verdict

**v1.2 batch_ingest concurrent rewrite viability: BLOCKED-by-environment**

- Decision matrix row hit: `BLOCKED-by-cert-rebuild` (extended to `BLOCKED-by-environment` to capture both blockers)
- Probe metrics: ALL N/A (probe not launched)
- Cert rebuild: SUCCESS — `123 total / 4 corp hits` (parent quick's intended unblocker DOES work; just isn't sufficient)

**Two unblocker paths for the next quick** (orchestrator picks):

1. **Aliyun-side run (preferred — bypasses both blockers).** SSH `aliyun-vitaclaw`, isolated `/tmp/260605-XX-probe-run/` working dir, `DEEPSEEK_API_KEY` from `/root/.hermes/.env`, `api.deepseek.com` reachable from Aliyun. Strongest signal for v1.2 viability (prod-parity network). Trade-off: requires explicit phase scope to allow Aliyun write-ops (probe creates temp working dir + LightRAG storage; per memory `feedback_ssh_readonly_vs_writeop_boundary`, this exceeds read-only diagnostic boundary).

2. **Switch probe LLM provider to Vertex Gemini.** Sibling `.scratch/260605-XX-concurrent-probe-v2.py` with `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`, no DeepSeek dependency. Vertex requires SA JSON + `GOOGLE_APPLICATION_CREDENTIALS`; verify corp network allows Vertex post-cert-rebuild (parent quick reported timeout on `us-central1-aiplatform.googleapis.com` PRE-rebuild; needs re-test). Trade-off: not prod parity.

## Artifacts produced

- `.planning/quick/260605-mz1-v1-2-research-walls-verify/260605-mz1-RESEARCH.md` — Section 5 appended (parent's 4 sections untouched; verified pre/post line range)
- `.planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-PLAN.md` — committed (already authored by orchestrator pre-spawn)
- `.planning/quick/260605-pwl-probe-rerun-cert-rebuild/260605-pwl-SUMMARY.md` — this file
- `.planning/STATE.md` — last_activity row appended (separate STATE update; orchestrator may follow-up per executor instructions)
- `.scratch/260605-pwl-cert-rebuild.log` (gitignored) — `REBUILD OK: 123 total / 4 corp hits`
- `.scratch/260605-pwl-probe-output.txt` (gitignored, 73 lines) — halt diagnostic + reachability matrix + recommended unblocker paths
- `.scratch/260605-pwl-probe-sha256-before.txt` and `…-after.txt` (gitignored, identical) — byte-identical contract receipt
- `venv/Lib/site-packages/certifi/cacert.pem` (gitignored) — rebuilt with corp roots
- `venv/Lib/site-packages/certifi/cacert.pem.bak-260605-pre-pwl` (gitignored) — pre-T1 backup
- `venv/Lib/site-packages/certifi/cacert.pem.bak-260525-pre-rebuild` (gitignored, pre-existing) — pre-T1 vanilla restore staging

## Discipline notes

- **Probe contract:** byte-identical sha256 honored — `.scratch/260605-mz1-concurrent-probe.py` NOT modified (sha256 `57308c595db37718f9a845a311f65a4c25c6957d987b464649a22ff8bcf3ad23` before+after).
- **Production source:** untouched — no edits to `batch_ingest_from_spider.py`, `ingest_wechat.py`, `kb/*`, `lib/*`, `config.py`, `requirements.txt`.
- **Hermes runtime data:** untouched — `~/.hermes/` not mutated.
- **Aliyun:** read-only SSH attempted to verify `DEEPSEEK_API_KEY` presence; SSH connection timed out from corp network (`Connection timed out during banner exchange`). No mutation attempted. Aliyun-side run is queued as unblocker path #1 for orchestrator pickup.
- **Git hygiene:** explicit `git add <files>` (no `-A`/`.`); single forward-only commit; no `--amend`/`--force`/`reset --hard`; no `Co-Authored-By:` line per CLAUDE.md global rule. Atomic stage-commit-push chain (per `feedback_git_add_explicit_in_parallel_quicks` strengthened pattern) executed in single Bash call.
- **Worktree path drift:** parent quick (260605-mz1) noted `Write` calls landing in parent repo path instead of worktree; this quick uses `cp` from parent → worktree for the parent-quick artifacts (PLAN/RESEARCH/SUMMARY) before edit, and uses Edit on the canonical worktree path (`C:\…\agent-a22717911b509f293\…`) for the new Section 5 append. No data loss; commit lands cleanly on worktree branch.
- **Lint:** Section 5 introduces duplicate `### Halt log` and `### Cross-references` heading IDs vs the parent's existing same-named headings (MD024 warnings at lines 194 + 212). Section 5 template in PLAN.md mandated those exact subheadings — accepting the duplicate-heading lint warning per CLAUDE.md PRINCIPLE #3 (Surgical Changes — don't restructure parent's existing 4 sections to silence a lint warning that the plan template explicitly created). Markdown renderers handle duplicate headings fine.

## Cross-references

- **Parent quick:** `260605-mz1-v1-2-research-walls-verify` (commits `b17bccb` + `adcb59d`) — verified 3 walls SYSTEMIC across 5-day Aliyun audit; Halt #1 (corp firewall) blocked local probe re-run. This quick (`260605-pwl`) was the intended unblocker — succeeded on cert rebuild (Halt #1 root cause resolved) but exposed two new blockers (Halt F).
- **Decision matrix:** PLAN.md `<decision_matrix>` section — verdict `BLOCKED-by-environment` maps to closest row `BLOCKED-by-cert-rebuild`.
- **Memory `corp_pem_rebuild_pattern`** — runbook for T1; followed exactly (force-restore vanilla certifi → atomic rebuild → ssl probe).
- **Memory `aliyun_ssh_manual_trigger_env`** — relevant for Aliyun-side re-run (must `set -a; source /root/.hermes/.env; set +a;` else `DEEPSEEK_API_KEY=dummy` silent 401 fail).
- **Memory `feedback_ssh_readonly_vs_writeop_boundary`** — Aliyun-side re-run scope decision (probe creates write-ops on Aliyun → exceeds read-only boundary; needs explicit phase scope).
- **Memory `feedback_git_add_explicit_in_parallel_quicks`** — atomic stage-commit-push pattern used in T4.
- **Memory `feedback_no_amend_in_concurrent_quicks`** — no `--amend` used; single forward-only commit.
- **ISSUES.md:** orchestrator may file new entry for the discovered DeepSeek TLS block (Cisco Umbrella SSLV3_ALERT_HANDSHAKE_FAILURE on `api.deepseek.com`). This is environmental tech-debt — `🟠 P2` (cleanup / corp network policy issue, not code defect). Cross-ref ISSUES #38/#39/#40 (filed by parent quick).
