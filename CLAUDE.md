# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HIGHEST PRIORITY PRINCIPLES

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

LLMs often pick an interpretation silently and run with it. This principle forces explicit reasoning:

State assumptions explicitly — If uncertain, ask rather than guess
Present multiple interpretations — Don't pick silently when ambiguity exists
Push back when warranted — If a simpler approach exists, say so
Stop when confused — Name what's unclear and ask for clarification
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

Combat the tendency toward overengineering:

No features beyond what was asked
No abstractions for single-use code
No "flexibility" or "configurability" that wasn't requested
No error handling for impossible scenarios
If 200 lines could be 50, rewrite it
The test: Would a senior engineer say this is overcomplicated? If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting
Don't refactor things that aren't broken
Match existing style, even if you'd do it differently
If you notice unrelated dead code, mention it — don't delete it
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused
Don't remove pre-existing dead code unless asked
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform imperative tasks into verifiable goals:

Instead of...	Transform to...
"Add validation"	"Write tests for invalid inputs, then make them pass"
"Fix the bug"	"Write a test that reproduces it, then make it pass"
"Refactor X"	"Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let the LLM loop independently. Weak criteria ("make it work") require constant clarification.

5. Don't Outsource Mechanical Work to the User

Two execution channels exist; pick the right one and run it yourself.

The wrong pattern is making the user copy-paste SSH commands, bash one-liners, or any other rote command the agent could run. The agent has a Bash tool. The user has higher-leverage work to do.

| Need | Channel | Who runs |
| --- | --- | --- |
| Mutate Hermes prod state (cron, env, deploy, restart, ssh-side script registration) | Write a Hermes operator prompt | Hermes (paste-ready prompt for user to forward) |
| Read-only diagnostic / file ops on Hermes prod | Run SSH yourself via the Bash tool | Agent |
| Read/grep local repo, run pytest locally, git commit, edit local files | Run yourself via Bash/Read/Edit/Grep | Agent |

Hard rule: never write "paste this SSH command and report back" to the user. Either run the SSH yourself with Bash, or write a Hermes prompt that does the work in prod. The only thing the user should be pasting is Hermes report output (because they own that channel) or explicit decisions ("go", "stop", "A or B").

If you're tempted to write a `ssh -p 49221 ...` block for the user to copy, stop. Either run it yourself or convert it into a Hermes prompt.

6. KB Local Deploy + UAT is Mandatory Before Any KB Phase Marked Complete

**Authored 2026-05-14 after kb-3 local-deploy revealed runtime issues that 256 green tests + Skill discipline regex + REQ coverage all missed.**

Any change to anything under `kb/` (templates, static, api, services, scripts, data, locale, export driver) MUST be verified end-to-end via local one-port deploy before the phase is marked complete. A green test suite is necessary but NOT sufficient.

**Mandatory steps before any KB phase complete:**

1. **Start local deploy:** `venv/Scripts/python.exe .scratch/local_serve.py` — single port `:8766` serves SSG + `/api/*` + `/static/*`
2. **Smoke every endpoint family the phase touched:** `curl` `/health`, `/api/articles`, `/api/article/{hash}`, `/api/search?mode=fts`, `/api/synthesize`, etc. — actual deployed app, not TestClient
3. **Browser UAT:** open the changed pages in a real browser at desktop / tablet / mobile (Playwright MCP works); capture screenshots to `.playwright-mcp/<phase>-uat-*.png`
4. **Cite UAT evidence in `<phase>-VERIFICATION.md`:** add a "Local UAT" section listing launcher used, env values, curl smoke results (status + key fields), screenshot paths, runtime issues discovered

**Failure mode this rule closes** (kb-3 case study, 2026-05-14):
- 256 tests green, all 5 Skill discipline floors met, 19/19 REQs verifiable
- Phase declared "complete" before any browser session
- First local deploy revealed: missing `/static/qa.js` (SSG never re-rendered after kb-3-10), LightRAG embedding-dim mismatch (3072 vs 768), FTS5 schema drift in dev DB
- These were all runtime issues invisible to TestClient + isolated unit tests

**Phase verification status MUST NOT be marked `complete` in `*-VERIFICATION.md` / `STATE-KB-v2.md` / `ROADMAP-KB-v2.md` until Local UAT has been performed and cited.**

This rule applies to ALL KB phases — UI, backend, ops, deploy. Run the deploy. Open a browser. See it work. Then mark complete.

Full discipline doc: `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3 (extended version with concrete curl + Playwright examples).

7. Claude Code Owns All Databricks App Deployments Autonomously

**Principle:** Never ask the user to manually run `databricks sync`, `databricks apps deploy`, or `databricks apps get-logs` commands. These are mechanical operations that Claude Code should handle autonomously via PowerShell + Databricks CLI.

**Why:** The CLI is already installed and authenticated (oauth). Asking the user to run commands wastes their time, causes context switches, and loses visibility into whether the deployment actually succeeded. The user should only care about the result ("search works" / "logs show FTS populated"), not the mechanical steps.

**How to apply:**

1. **After making code changes:** Run `databricks sync --watch . <workspace_path>` yourself (PowerShell, never Git Bash)
2. **Deploy the app:** Run `databricks apps deploy <app_name> --source-code-path <workspace_path>` yourself
3. **Check logs:** Fetch deployment logs via `databricks apps get-logs` to verify success or identify errors
4. **Report to user:** "Deployment successful. FTS table populated with 2598 articles. Search should work."

**Tool choice:** Use PowerShell for all `databricks` CLI calls — Git Bash path conversion breaks workspace paths (`/Workspace/...` → `C:/Users/.../Workspace/...` → `"Path doesn't start with '/'" error`).

**Related:** Principle #5 (Don't Outsource Mechanical Work) covers SSH and Hermes prompts; this principle extends it to Databricks CLI.

8. Right-Size GSD Ceremony — Diagnostic Complexity ≠ Fix Complexity

**Principle:** GSD mode must be re-picked AFTER the diagnostic phase reveals actual fix scope. Heavy `/gsd:plan-phase` ceremony is the wrong tool for tiny fixes, even when the diagnostic was complex.

**Why:** 2026-05-26 bug 2c spent 5+ hours in `/gsd:plan-phase` Phase 0/1/2 doc ceremony to ship 16 LoC. The diagnostic was genuinely complex (LightRAG storage transplant + 3-mode dispatch + chunk-anchor injection theory + provider-agnostic LLM compliance failure across DeepSeek + Vertex Gemini), but once root-caused the actual fix was 1 line in `kb/services/synthesize.py:552` plus ~15 LoC FTS5 fallback in `kb/api_routers/search.py:_kg_local_worker`. Writing PLAN.md + verifying tests across 4 phases for 16 LoC is value/cost negative — the doc-writing burned more wall-clock than the fix.

**How to apply:**

After Phase 1 DECIDE produces a fix-scope estimate (LoC + files touched + risk), downshift the remaining work:

| Fix scope | Remaining-work mode |
| --- | --- |
| LoC ≤ 5, single file, obvious, tests already cover the path | Exit GSD entirely. Direct `Edit` → `git add` → `git commit` → deploy in chat. No agent, no phase, no doc. |
| 5 < LoC ≤ 50, single concern, single deploy | Downshift to `/gsd:quick` — atomic commit + STATE tracking, NO Phase 2 PLAN.md doc. TDD red→green→commit inline. |
| LoC > 50, multi-file, architectural, or unclear blast radius | Keep `/gsd:plan-phase` — PLAN.md + plan-checker + verifier worth the cost. |

**Investigation-heavy + fix-light = 2 quicks, NOT 1 plan-phase.** When the diagnostic is unclear but the fix is likely small, structure as two separate quicks:

1. `/gsd:quick "investigate <symptom>"` — read-only, produces RESEARCH.md / DECISION.md only, no Phase 2/3/4
2. `/gsd:quick "ship <fix>"` — atomic commit + deploy

**Trigger to downshift:** Phase 1 DECIDE MUST produce a numeric LoC estimate. If estimate ≤ 50, immediately fork to `/gsd:quick` or exit GSD. Do NOT auto-proceed to Phase 2 PLAN.md for tiny fixes — that's the failure mode this principle prevents.

**Inverse trigger:** during a `/gsd:quick`, if the work expands past ~50 LoC or starts touching multiple subsystems / requiring architectural decisions, halt the quick and escalate to `/gsd:plan-phase`. Don't grind a quick into a plan-phase by accretion.

**Related:** Principle #2 (Simplicity First) — process simplicity matches code simplicity. Principle #4 (Goal-Driven Execution) — don't manufacture milestones for trivial fixes.

---

## Project-Specific Disciplines

### Behavior-Anchor Harness for Hot Orchestration Code

**Long-running orchestrators that batch I/O and silently swallow exceptions need pytest harnesses anchored on observable behavior, not internal call shape.**

`batch_ingest_from_spider.py:ingest_from_db()` is the canonical example: 600+ lines, 4 levels of late-imports, 3 layer batches (Layer 1 / scrape / Layer 2), broad `except Exception` handlers around every external call. Five distinct prod-only failure modes have shipped through 256-test green CI in the past 90 days (2026-05-08 dual-source skip, 2026-05-15 missed queue.append, 2026-05-11 max-articles leak, v1.0.x finally-block bypass, 2026-05-16 image_count_row stale-0). Substring-matching plan checkers, mocked unit tests on the modified function, and Hermes natural cron all missed each one — the bug only surfaced as ghost successes / silent budget-floor / wrong source attribution.

**Rule:** any contract-shape change to ingest_from_db (column added to candidate_rows tuple, new SKIP_REASON_VERSION, new layer2 verdict alphabet member, new persistence column, new mid-loop early-exit branch) MUST be accompanied by:

1. A new test in `tests/unit/test_ingest_from_db_orchestration.py` that pins the new behavior on observable post-conditions (rows in seeded in-memory DB; arguments passed to mocked downstream callables; files written under tmp_path).
2. The schema in `tests/unit/_ingest_fixtures.py:in_memory_db()` updated to include any new columns the production SELECT/INSERT touches — fixture drift is itself a contract-change failure mode (mirrors the 2026-05-15 lesson #2 "test fixture CREATE TABLE not synced with migration silently masks the downstream bug").
3. Verification command run locally: `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` shows all tests pass.

This rule applies ONLY to `ingest_from_db` and any future orchestrator that meets these three signals: (a) >300 LOC of nested batches, (b) silent broad except handlers around external calls, (c) cost-or-correctness consequences from missed call sites (paid API spend / DB writes that affect tomorrow's candidate pool / ghost successes). Smaller helpers covered by their own focused tests do not need this discipline. The list of in-scope orchestrators is currently {`ingest_from_db`} and grows ONLY by adding a name to this rule, never implicitly.

## Project Summary

OmniGraph-Vault is a personal knowledge base for **OpenClaw** and **Hermes Agent** AI assistants. It ingests web content (WeChat articles, PDFs) into a **LightRAG** knowledge graph, then exposes that graph as agent skills.

**Tech stack:** Python 3.11+, LightRAG (KG engine), Google Gemini 2.5 Pro/Flash (LLM + vision), Apify + Playwright CDP (scraping), local HTTP image server (port 8765)

**Runtime data:** `~/.hermes/omonigraph-vault/` (note: the directory name has a typo — `omonigraph` not `omnigraph` — this is the actual path used in `config.py` and must be preserved)

---

## Release Status

**v1.0 (Knowledge Collection + Ingestion)** declared 2026-05-13. All v1.0.x/y/z patches closed by 2026-05-17. Stable baseline: end-to-end pipeline (scan → Layer 1 → scrape → Layer 2 → enrich → ainsert → reconcile), KOL + RSS first-class.

**Closed 2026-05-24:** aim-2 LightRAG storage migration (Aliyun byte-identical to Hermes, 27654 ent / 39604 rel; Hermes frozen RO until 2026-06-22) · aim-3 systemd timers cutover (Aliyun daily cron LIVE) · agentic-rag-v1 (41/41 REQs, 165 tests).

**In flight (2026-05-26):** arx-2 · arx-3 · aim-4 · aim-5 · repo-cleanup.

**Future:** v1.1 (KB content scale + throughput) · agentic-rag-v2.

See [README.md](README.md) for v1.0 declaration.

---

## Common Commands

> **For local testing / validation / smoke runs, ALWAYS use `scripts/local_e2e.sh`** (see "Local E2E testing" section below). The corp network has reachability constraints (DeepSeek + SiliconFlow blocked, Cisco Umbrella TLS interception) that the harness handles via auto-configured env vars. Manual `python` invocations bypass that handling and will fail or hit the wrong DB / quota.
>
> Available modes: `rss` / `kol` / `wechat <url>` / `layer1 N` / `layer2 N` / `cleanup` / `help`. The raw commands listed in this section are reference-only — for any new local invocation prefer the harness mode.

```bash
# Ingest a WeChat article (dual-path: Apify primary, CDP fallback)
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# Ingest a local PDF with image extraction
python multimodal_ingest.py "/path/to/document.pdf"

# Query with synthesis (modes: naive, local, global, hybrid, mix)
python kg_synthesize.py "What are the latest trends in AI Agents?" hybrid

# Direct LightRAG query (for debugging)
python query_lightrag.py "Explain the architecture of OmniGraph-Vault"

# List graph entities
python list_entities.py

# Start image server (background)
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &
```

### Local E2E testing

See [docs/e2e-testing.md](docs/e2e-testing.md).

---

## Architecture

### Ingestion Flow

```
URL → ingest_wechat.py
  ├─ Apify (primary) or CDP/Playwright (fallback) → HTML
  ├─ BeautifulSoup + html2text → Markdown
  ├─ Image download → ~/.hermes/omonigraph-vault/images/{hash}/
  ├─ Gemini Vision → image descriptions appended to content
  ├─ Gemini Flash → entity extraction → entity_buffer/{hash}_entities.json
  └─ LightRAG ainsert() → knowledge graph stored in lightrag_storage/
```

Raw entities are buffered to `entity_buffer/{hash}_entities.json` for downstream
analysis (Cognee canonicalization was retired 2026-05-10 in quick 260510-gfg).

### Query/Synthesis Flow

```
Query → kg_synthesize.py
  ├─ Load canonical_map.json → normalize entity names in query
  ├─ LightRAG aquery(mode=hybrid) → graph retrieval
  ├─ Past-query memory (HYG-03 JSONL append-only file)
  ├─ Combined prompt → Gemini generates Markdown report
  └─ Output → stdout + ~/.hermes/omonigraph-vault/synthesis_output.md
```

### Key Integration Points

**LightRAG** — used in `ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`, `query_lightrag.py`. Configured with Gemini model wrappers (`gemini_model_complete`, `gemini_embed`). Storage: `~/.hermes/omonigraph-vault/lightrag_storage/`.

**config.py** — loads `~/.hermes/.env` at import time. All modules import it for `BASE_DIR`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `CDP_URL`. The env loader does *not* overwrite existing env vars.

### Environment Variables

| Variable | Required | Used For |
|---|---|---|
| `GEMINI_API_KEY` | Yes | All LLM, vision, and embedding calls |
| `APIFY_TOKEN` | No | Primary scraping (falls back to CDP) |
| `FIRECRAWL_API_KEY` | No | Firecrawl web scraping API |
| `CDP_URL` | No | **Local mode** (default): `http://localhost:9223` — raw CDP WebSocket; `ingest_wechat.py` uses `playwright.connect_over_cdp()`. Start Edge with `msedge --remote-debugging-port=9223`. **Remote MCP mode** (testing fallback): `http://host:port/mcp` — Playwright MCP server (MCP-over-SSE); `ingest_wechat.py` auto-detects the `/mcp` suffix and uses `_MCPClient` + `browser_navigate`/`browser_evaluate` instead. Both modes are fully implemented. |
| `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` | No | RSS classifier daily-batch safety cap (default 500 articles). Applies only when `--max-articles` CLI flag is NOT passed; CLI value always wins. Non-int values silently fall back to 500. |

Set in `~/.hermes/.env`.

**Scoped env vars:** `OMNIGRAPH_GEMINI_KEY` (canonical; `GEMINI_API_KEY` fallback for local dev). `OMNIGRAPH_GEMINI_KEYS` (comma-separated; multi-account rotation across Google accounts / GCP projects). Model names hard-coded in `lib/models.py` (not env-overridable). Per-model RPM caps env-overridable via `OMNIGRAPH_RPM_*`. Embedding default: `gemini-embedding-2`. Full deploy table in `Deploy.md`.

**DeepSeek cross-coupling:** `lib/__init__.py` eagerly imports `deepseek_model_complete`, which raises at import time if `DEEPSEEK_API_KEY` is unset. Gemini-only workloads still need `DEEPSEEK_API_KEY` set (use `DEEPSEEK_API_KEY=dummy`).

### Local dev env vars

Opt-in vars for local-dev runs against `.dev-runtime/` instead of `~/.hermes/omonigraph-vault/`. Unset preserves prod behavior.

| Var | Required | Default | Purpose |
|-----|----------|---------|---------|
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | `deepseek` (prod parity) or `vertex_gemini` (local sandbox). |
| `OMNIGRAPH_LLM_MODEL` | No | `gemini-3.1-flash-lite-preview` | Vertex Gemini model ID. Applies only when provider=`vertex_gemini`. |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS` | No | _(empty)_ | Comma-list of vision providers to skip. Typical local: `siliconflow,openrouter`. |
| `OMNIGRAPH_BASE_DIR` | Yes for local dev | `~/.hermes/omonigraph-vault` | Runtime data root (absolute path). |
| `OMNIGRAPH_LLM_TIMEOUT_SEC` | No | `600` | Int seconds; Vertex Gemini LLM only. |
| `OMNIGRAPH_PROCESSED_RETRY` | No | `30` | Int. PROCESSED-gate max retries (×`_BACKOFF` = post-ainsert verification budget). |
| `OMNIGRAPH_PROCESSED_BACKOFF` | No | `2.0` | Float seconds. PROCESSED-gate retry backoff. |
| `OMNIGRAPH_DEEPSEEK_TIMEOUT` | No | `300` | Float seconds. DeepSeek client-side per-call timeout. See `lib/llm_deepseek.py`. |

Full local-dev runbook: `docs/LOCAL_DEV_SETUP.md`.

---

## Development Conventions

- **Atomic writes** for `canonical_map.json`: always write `.tmp` then rename
- **LLM output never goes directly into the graph** — always validate against real sources first
- **Entity buffer idempotency** — write `.processed` marker after each batch run, never delete originals
- **Image server must be running** for synthesized reports to render correctly (port 8765)

---

## OpenClaw / Hermes Skill Writing Standards

See [docs/skills/SKILL_STANDARDS.md](docs/skills/SKILL_STANDARDS.md) — directory layout, frontmatter, progressive disclosure, loading precedence, writing patterns, planned skills, testing, publishing.

---

## Testing the CDP / MCP Scraping Path

The ingestion pipeline has three paths. Here's how to exercise each one manually:

### Path 1 — Apify (primary)

Set `APIFY_TOKEN` in `~/.hermes/.env` and run:

```bash
python ingest_wechat.py "https://mp.weixin.qq.com/s/<article-id>"
```

Look for `Scraping successful using method: apify` in the output.

### Path 2 — Local Edge CDP (production fallback)

1. Start Edge with remote debugging (Windows):

   ```powershell
   Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
   ```

2. Set `CDP_URL=http://localhost:9223` in `~/.hermes/.env`
3. Leave `APIFY_TOKEN` unset (or set an invalid value) so Apify fails and the fallback fires.
4. Run `python ingest_wechat.py "<url>"` — look for `Falling back to local CDP...` then `method: cdp`.

### Path 3 — Remote Playwright MCP (testing fallback)

1. Set `CDP_URL=http://ohca.ddns.net:58931/mcp` in `~/.hermes/.env`
   (The `/mcp` suffix is what triggers `_MCPClient` instead of `connect_over_cdp`.)
2. Leave `APIFY_TOKEN` unset so the fallback fires.
3. Run `python ingest_wechat.py "<url>"` — look for `Falling back to remote Playwright MCP...` then `method: mcp`.

### Skill simulator (no Hermes required)

```bash
# All test cases for ingest routing
python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json

# All test cases for query routing
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
```

Exit code 0 = all pass. Requires only `GEMINI_API_KEY`.

---

## Remote Hermes Deployment (E2E testing against real deployment)

Production Hermes runs OmniGraph-Vault on a remote PC (WSL2 Linux) — only place to exercise full skill → script → LightRAG → Gemini against real deployed state. Remote git may be ahead of GitHub.

**SSH details:** project memory `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md` (auto-loaded). Never commit credentials/hostnames to this repo.

**Reconcile git state before any remote test:**

```bash
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && git status -sb && git log --oneline -5"
```

If remote is ahead: push from remote, pull locally, re-read changed files. Decisions on stale code mislead.

**Remote paths (WSL2 Linux):**

- Code: `~/OmniGraph-Vault` (venv at `venv/bin/`, not `venv/Scripts/`)
- Runtime data: `~/.hermes/omonigraph-vault/` (typo canonical — do not rename)
- Env: `~/.hermes/.env`
- Hermes gateway state: `~/.hermes/gateway.pid`, `~/.hermes/state.db`

---

## Lessons Learned

Evergreen invariants only — dated postmortems are archived in [docs/lessons/](docs/lessons/) and surfaced in [MEMORY.md](../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md) when still load-bearing.

- The runtime data directory is `omonigraph-vault` (typo is baked into config.py and deployed environments — do not "fix" it without a coordinated migration)
- `CDP_URL` supports two modes auto-detected by the `/mcp` URL suffix: local Edge (`localhost:9223`) uses `playwright.connect_over_cdp()`; remote testing (`host:port/mcp`) uses `_MCPClient` (MCP-over-SSE with `mcp-session-id` header). The MCP server requires `initialize` first, then subsequent requests must include `mcp-session-id` in the header — without it every call returns "Server not initialized".

Recent archives:
- [2026-05](docs/lessons/2026-05-archive.md) — 9 postmortems: SQLite CHECK constraint, half-fix pattern, cascade divergence, CV mass-classify, ghost success class, D2 contract bug

## Vertex AI Migration Path

### Problem: Quota Coupling

All current Gemini API calls (embedding + Vision + LLM) share a single GCP project's free-tier quota pool. When any one service triggers a 429 (rate limit), the entire batch stops — one slow endpoint kills ingestion of unrelated articles. This is the primary motivator for migrating to Vertex AI paid tier with cross-project quota isolation.

### Recommendation (current)

Until batch volume justifies the migration, stay on the split-provider approach:

- **Vision:** SiliconFlow Qwen3-VL-32B (¥0.0013/image, no GCP dependency)
- **Embedding:** Gemini API free tier (100 RPM — sufficient for current batches)
- **LLM:** DeepSeek chat (on-prem, no GCP dependency)

Only Gemini embedding still touches the GCP free-tier quota. If you observe repeated 429 errors on embedding calls during batch runs, it is time to trigger the migration.

**Vertex endpoint + model pairing (for deployed Vertex paths):** The production-recommended value is `GOOGLE_CLOUD_LOCATION=global` (not `us-central1`). Hermes's `~/.hermes/.env` uses `global` to pool embedding quota across GCP projects. Embedding model naming is endpoint-dependent: gemini-embedding-2 is GA on global; gemini-embedding-2-preview is regional-only. Always match model to endpoint.

### When to Migrate

Trigger the Vertex AI migration when **any** of these become routinely true:
- Batch ingestion regularly hits > 100 RPM embedding ceiling (visible as embedding-only 429s)
- Batch ingestion hits > 500 RPD vision ceiling (only applies if you move Vision back to Gemini — not current config)
- A single 429 on embedding kills the entire batch despite cascade retries

### Full Specification

See `docs/VERTEX_AI_MIGRATION_SPEC.md` for the complete migration runbook: GCP project setup, service account creation, OAuth2 token management, pricing comparison, code integration roadmap, and phased rollout plan.

To estimate monthly cost before migrating, run:

```bash
python scripts/estimate_vertex_ai_cost.py --articles {N} --avg-images-per-article {M}
```

## Checkpoint Mechanism

The batch ingestion pipeline uses a per-article checkpoint directory to make long-running batches resumable without re-doing expensive work (scraping, image download, vision description, LightRAG ainsert).

**Stage boundaries** — each article progresses through ordered stages; a completed stage writes a marker file into `checkpoints/{article_hash}/`:
- `01_scrape` — raw HTML + markdown extracted from WeChat / Apify / CDP
- `02_filter` — small/boilerplate images filtered (Phase 8 rule)
- `03_manifest` — image download manifest (URLs + local paths)
- `04_vision` — per-image descriptions from the Vision Cascade
- `05_ingest` — LightRAG `ainsert()` committed
- `metadata.json` — current stage + last-updated timestamp

**Resume semantics** — on batch restart, each article's checkpoint dir is inspected; the pipeline skips stages whose marker file exists and resumes at the first missing stage. Checkpoint writes are atomic (`.tmp` then `os.rename()`), so a crash mid-write never leaves corrupted partial files.

**Operator commands:**
- `python scripts/checkpoint_status.py` — list all in-flight articles and their current stage
- `python scripts/checkpoint_reset.py --hash {article_hash}` — remove one article's checkpoint dir to force full re-ingest
- `rm -rf checkpoints/{article_hash}` — same as above, manual form (respects WeChat throttle, so no speedup)
- `python batch_ingest_from_spider.py --reset-checkpoint` — wipe all checkpoints and start a full batch from scratch

**Known pitfall:** removing `checkpoints/` mid-batch while the process is running can corrupt in-flight `metadata.json` writes — always stop the batch first.

## Vision Cascade

Per-image description uses a three-provider cascade with automatic failover and a per-provider circuit breaker. The goal is that a single provider 503/429 never kills an article.

**Fallback order** (hard-coded, not env-overridable):
1. **SiliconFlow Qwen3-VL-32B** (primary; ¥0.0013/image, paid tier)
2. **OpenRouter** (secondary; free-tier fallback)
3. **Gemini Vision** (last resort; 500 RPD free-tier ceiling)

**Circuit breaker** — after **3 consecutive failures** of the same provider within a batch, `circuit_open = True` for that provider and it is skipped for subsequent images until a recovery retry succeeds. A 429 cascades immediately to the next provider. 4xx auth errors do NOT count toward the circuit breaker (fixing auth requires operator action, not automatic fallback).

**Per-provider balance alerts** — pre-batch, the cascade layer emits a structured warning to stderr if `SiliconFlow balance < estimated remaining cost`. Estimated cost is `¥0.0013 × expected_image_count`.

**Cascade evidence** — `batch_validation_report.json` records `provider_usage` (per-provider attempt count + success count). A healthy batch shows Gemini usage below 10%; if Gemini usage is >10%, investigate SiliconFlow + OpenRouter health before the next batch.

## SiliconFlow Balance Management

SiliconFlow is a paid-tier provider with a hard balance cap. Running out of balance mid-batch does NOT hang the pipeline (the cascade falls through to OpenRouter + Gemini), but it does shift all remaining images onto the 500-RPD Gemini free tier, which can exhaust quota in a single batch.

**Pre-batch check** — before starting any batch, verify SiliconFlow balance covers the expected image count at ¥0.0013/image. Rule of thumb: **¥1.00 covers ~770 images**. For a 263-article batch averaging 10 images/article (~2,630 images), budget **≥ ¥10** before starting.

**Mid-batch monitoring** — `watch -n 30 'python scripts/checkpoint_status.py | tail -20'` shows in-flight articles; if the Vision provider flips to Gemini for more than a handful of consecutive images, check the balance.

**Depletion scenario** — when balance hits 0:
1. Cascade logs a structured warning per image: `SiliconFlow balance depleted; cascading to OpenRouter/Gemini`
2. Subsequent images auto-route to OpenRouter (if available) and Gemini
3. Gemini 500-RPD quota will exhaust within one batch of any scale — either **pause the batch + top up**, or **accept the degraded run** and treat the resulting Gemini-heavy articles as lower-fidelity

**Top-up flow** — topping up mid-batch is safe: pause batch (Ctrl+C — checkpoints are atomic), top up on the SiliconFlow dashboard, then resume with the same command (no `--reset-checkpoint`).

## Batch Execution

Two canonical commands govern all batch runs:

```bash
# Full batch from scratch (wipes all checkpoints first)
python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint

# Resume from last checkpoint (the default — skips already-completed stages)
python batch_ingest_from_spider.py --topics ai --depth 2

# Monitor progress (refreshes every 5s)
watch -n 5 'python scripts/checkpoint_status.py | tail -20'
```

**When to use which:**
- **Resume** (default) — interrupted batch, transient failure, mid-batch top-up; safe to run repeatedly
- **`--reset-checkpoint`** — you have changed fixture logic, ingestion logic, or want a clean baseline for a regression run; this wipes ALL checkpoints and re-downloads all images

**Never run both simultaneously** — checkpoint writes are atomic per article but not across concurrent processes. One batch at a time per host.

### MAX_ARTICLES is a tri-governor

`MAX_ARTICLES` (default 5 in cron via `cron_daily_ingest.sh 5`) is NOT
just a throughput cap. It governs THREE concerns simultaneously:

1. **Throughput cap** — how many articles per cron invocation
2. **SiliconFlow ¥-budget governor** — at ~¥0.04/article (30 imgs avg ×
   ¥0.0013/img), 5 articles ≈ ¥0.20/cron. Bumping to 50 ≈ ¥2.00/cron.
3. **Vertex AI embedding RPM governor** — entity-rich articles trigger
   100-300 embedding calls each. 5 articles burst ≈ 500-1500 RPM hits;
   raising the cap risks 429 quota exceed (see v1.0.z scope).

Bumping `MAX_ARTICLES` without checking all three regresses cost and/or
quota. Cross-reference: "SiliconFlow Balance Management" + "Vertex AI
Migration Path" sections above.

## Known Limitations

- **Gemini 500 RPD ceiling** (free tier) — the Gemini fallback at the end of the Vision Cascade is capped at 500 requests per day across the shared GCP project. A single large batch falling through to Gemini can exhaust this quota and cause Vision to fail for the remainder of the day.
- **WeChat account throttle** — `ingest_wechat.py` enforces **50 articles per batch + cooldown** before the next batch; this is a WeChat-side limit, not configurable. Large batches should be sliced into 50-article chunks with cooldown between chunks.
- **Vertex AI migration path (future)** — the current Gemini API key couples embedding quota with LLM quota in the same GCP project, so an embedding 429 can kill a batch mid-ingest. The **Recommended Upgrade Path** (see `Deploy.md` § Recommended Upgrade Path) migrates production deployments to Vertex AI OAuth2 with per-project quota isolation. Design is frozen (Phase 16 spec); code migration is deferred to post-Milestone B.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**OmniGraph-Vault**

A local, graph-based personal knowledge base that gives Hermes Agent (and Openclaw) persistent memory over articles and documents. You drop in a WeChat article URL or PDF; the vault scrapes it, extracts entities and images, indexes everything into LightRAG, and surfaces it back on demand via two skills: one to ingest content, one to answer questions.

**Core Value:** When Hermes sees "add this to my KB" or "what do I know about X?" it calls the right script and gets a useful answer back.

### Constraints

- **Privacy**: All data stays local; no SaaS KB subscriptions; only Gemini API + Apify make external calls
- **Platform**: Windows-primary (Edge for CDP)
- **Single user**: No auth, no isolation required — personal tool only
- **Stack**: Python 3.11+, LightRAG, Gemini 2.5 Flash/Pro — no framework migrations
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

See [docs/tech-stack.md](docs/tech-stack.md).
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

See [docs/conventions.md](docs/conventions.md).
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

See [docs/architecture.md](docs/architecture.md).
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
