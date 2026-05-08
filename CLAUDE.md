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

## Project Summary

OmniGraph-Vault is a personal knowledge base for **OpenClaw** and **Hermes Agent** AI assistants. It ingests web content (WeChat articles, PDFs) into a **LightRAG** knowledge graph enriched with **Cognee** async memory, then exposes that graph as agent skills.

**Tech stack:** Python 3.11+, LightRAG (KG engine), Cognee (memory layer), Google Gemini 2.5 Pro/Flash (LLM + vision), Apify + Playwright CDP (scraping), local HTTP image server (port 8765)

**Runtime data:** `~/.hermes/omonigraph-vault/` (note: the directory name has a typo — `omonigraph` not `omnigraph` — this is the actual path used in `config.py` and must be preserved)

---

## Common Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate   # Linux/macOS
python -m venv venv && venv\Scripts\activate       # Windows
pip install -r requirements.txt

# Verify imports
python -c "import lightrag; print('LightRAG OK')"
python -c "import cognee; print('Cognee OK')"

# Ingest a WeChat article (dual-path: Apify primary, CDP fallback)
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# Ingest a local PDF with image extraction
python multimodal_ingest.py "/path/to/document.pdf"

# Query with Cognee memory context (modes: naive, local, global, hybrid, mix)
python kg_synthesize.py "What are the latest trends in AI Agents?" hybrid

# Direct LightRAG query (no Cognee, for debugging)
python query_lightrag.py "Explain the architecture of OmniGraph-Vault"

# List graph entities
python list_entities.py

# Start image server (background)
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &

# Run entity canonicalization batch (polls entity_buffer/)
python cognee_batch_processor.py

# Verification gates (manual test scripts, not pytest)
python tests/verify_gate_a.py   # Cognee remember()
python tests/verify_gate_b.py   # Cognee recall() + search()
python tests/verify_gate_c.py   # Entity disambiguation
```

No pytest framework, no linting, no CI configured yet. Tests are manual verification scripts that hit live APIs.

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

Entity canonicalization runs **async and decoupled** via `cognee_batch_processor.py`, which polls `entity_buffer/` and writes to `canonical_map.json` atomically (tmp → rename).

### Query/Synthesis Flow

```
Query → kg_synthesize.py
  ├─ Load canonical_map.json → normalize entity names in query
  ├─ LightRAG aquery(mode=hybrid) → graph retrieval
  ├─ cognee_wrapper.recall_previous_context() → past query memory
  ├─ Combined prompt → Gemini generates Markdown report
  ├─ cognee_wrapper.remember_synthesis() → store for future recall
  └─ Output → stdout + ~/.hermes/omonigraph-vault/synthesis_output.md
```

### Key Integration Points

**LightRAG** — used in `ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`, `query_lightrag.py`. Configured with Gemini model wrappers (`gemini_model_complete`, `gemini_embed`). Storage: `~/.hermes/omonigraph-vault/lightrag_storage/`.

**Cognee** — wrapped by `cognee_wrapper.py` (provides `remember_synthesis()`, `recall_previous_context()`, `disambiguate_entities()`). Batch processing in `cognee_batch_processor.py`. Must be configured via env vars *before* import: `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-flash`, `EMBEDDING_PROVIDER=gemini`.

**config.py** — loads `~/.hermes/.env` at import time. All modules import it for `BASE_DIR`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `CDP_URL`. The env loader does *not* overwrite existing env vars.

### Environment Variables

| Variable | Required | Used For |
|---|---|---|
| `GEMINI_API_KEY` | Yes | All LLM, vision, and embedding calls |
| `APIFY_TOKEN` | No | Primary scraping (falls back to CDP) |
| `FIRECRAWL_API_KEY` | No | Firecrawl web scraping API |
| `CDP_URL` | No | **Local mode** (default): `http://localhost:9223` — raw CDP WebSocket; `ingest_wechat.py` uses `playwright.connect_over_cdp()`. Start Edge with `msedge --remote-debugging-port=9223`. **Remote MCP mode** (testing fallback): `http://host:port/mcp` — Playwright MCP server (MCP-over-SSE); `ingest_wechat.py` auto-detects the `/mcp` suffix and uses `_MCPClient` + `browser_navigate`/`browser_evaluate` instead. Both modes are fully implemented. |
| `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` | No | RSS classifier daily-batch safety cap (default 500 articles). Applies only when `--max-articles` CLI flag is NOT passed; CLI value always wins. Non-int values silently fall back to 500. |
| `OMNIGRAPH_COGNEE_INLINE` | No | Enable inline Cognee `remember_article` call in ingest_wechat.py. Default `0` (disabled) since 2026-05-03 due to Cognee LiteLLM → AI Studio routing bug with Vertex-exclusive gemini-embedding-2 (422 NOT_FOUND → retry loop blocks ingest). Root fix in v3.4 Phase 20/21. Set `1` to re-enable once the LiteLLM routing is corrected. |

Set in `~/.hermes/.env`. Cognee-specific vars (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, etc.) are hardcoded in each script that uses Cognee.

**Phase 7 scoped env vars** (added 2026-04-28): the preferred Gemini key variable is `OMNIGRAPH_GEMINI_KEY` (namespaced, won't collide with Hermes's own LLM vars). `GEMINI_API_KEY` remains as a fallback for local dev. For multi-account rotation set `OMNIGRAPH_GEMINI_KEYS` (comma-separated; only useful across different Google accounts / GCP projects). Model names are pure string constants in `lib/models.py` (NOT env-overridable per Amendment 1 — rollback is `git revert`). Per-model RPM caps ARE env-overridable via `OMNIGRAPH_RPM_*` (D-08 retained for paid-tier upgrade). Embedding default is `gemini-embedding-2` (D-10). Full deploy table in `Deploy.md`.

**Phase 5 DeepSeek cross-coupling (Hermes FLAG 2):** `lib/__init__.py` eagerly imports `deepseek_model_complete`, which raises at import time if `DEEPSEEK_API_KEY` is unset. Gemini-only workloads still need `DEEPSEEK_API_KEY` set (use `DEEPSEEK_API_KEY=dummy` if you don't have a real one). This is a documented Phase 5 side-effect; soft-fail is a future Phase 5 follow-up, not a Phase 7 fix.

**Standalone Cognee rotation caveat (Hermes FLAG 1):** `cognee_wrapper.py` seeds Cognee's config once at import. Long-running callers of `lib.rotate_key()` that import `cognee_wrapper` directly must also call `lib.refresh_cognee()` after rotation, or accept stale-key risk. Production paths (`cognee_batch_processor.run_batch`, `kg_synthesize.synthesize_response`) already call `refresh_cognee()` at the right entry points — ad-hoc scripts need to do so themselves. See `Deploy.md` § Known limitation.

### Local dev env vars (quick task 260504-g7a)

These five env vars enable running the full pipeline on the user's Windows
dev box against `.dev-runtime/` instead of `~/.hermes/omonigraph-vault/`.
All five are opt-in; unset values preserve Hermes production behavior.

| Var | Required | Default | Purpose |
|-----|----------|---------|---------|
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | `deepseek` (production parity) or `vertex_gemini` (local sandbox). Unset == DeepSeek. |
| `OMNIGRAPH_LLM_MODEL` | No | `gemini-3.1-flash-lite-preview` | Vertex Gemini model ID. Applies only when `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`. |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS` | No | _(empty)_ | Comma-list of vision providers to drop from the cascade. Typical local value: `siliconflow,openrouter` (no paid balances / keys). |
| `OMNIGRAPH_BASE_DIR` | Yes for local dev | `~/.hermes/omonigraph-vault` | Absolute path to runtime data root. Empty string treated as unset. |
| `OMNIGRAPH_LLM_TIMEOUT_SEC` | No | `600` | Int seconds; applies to Vertex Gemini LLM calls only. DeepSeek path unaffected. |

Full local-dev runbook: `docs/LOCAL_DEV_SETUP.md`.

---

## Development Conventions

- **Atomic writes** for `canonical_map.json`: always write `.tmp` then rename
- **Cognee is async** — never block the ingestion fast-path on any Cognee operation
- **LLM output never goes directly into the graph** — always validate against real sources first
- **Entity buffer idempotency** — write `.processed` marker after each batch run, never delete originals
- **Image server must be running** for synthesized reports to render correctly (port 8765)

---

## OpenClaw / Hermes Skill Writing Standards

> Synthesized from: docs.openclaw.ai/tools/creating-skills, dench.com/blog/openclaw-skill-writing-advanced,
> hermes-agent.ai/blog/hermes-agent-skills-guide, lushbinary.com/blog/hermes-agent-custom-skills-development-guide,
> hermes-agent.nousresearch.com/docs/user-guide/features/skills

### Skill Directory Structure

Every skill is a **directory**, not a single file:

```
my-skill/
├── SKILL.md           # Agent-facing instructions + metadata (required)
├── references/        # Docs the agent reads on-demand (Level 2 loading)
│   └── api-docs.md
├── scripts/           # Shell scripts the agent executes via exec
│   └── run-query.sh
└── README.md          # Human-facing: install guide, examples
```

`references/` = documents the agent reads. `scripts/` = scripts the agent runs. Never mix.

### SKILL.md Frontmatter

```yaml
---
name: omnigraph_query          # snake_case, unique, required
description: >-                # one-line, shown to agent at Level 0 — accuracy is critical
  Query the OmniGraph-Vault knowledge graph by natural language.
triggers:                      # Hermes auto-match phrases
  - "search the knowledge base"
  - "what do I know about"
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY"]
---
```

Required: `name`, `description`. Optional but impactful: `triggers`, `metadata.openclaw.requires.*`.

### Progressive Disclosure (Hermes Token Efficiency)

```
Level 0: skills_list()           → name + description only (~3k tokens for full catalog)
Level 1: skill_view(name)        → full SKILL.md content
Level 2: skill_view(name, path)  → specific file in references/
```

Keep SKILL.md lean. Put heavy reference material in `references/` — it stays at Level 2 until explicitly requested.

### OpenClaw Loading Precedence

| Location | Precedence | Scope |
|---|---|---|
| `<workspace>/skills/` | Highest | Per-agent |
| `<workspace>/.agents/skills/` | High | Per-workspace agent |
| `~/.agents/skills/` | Medium | Shared agent profile |
| `~/.openclaw/skills/` | Medium | Shared (all agents) |
| Bundled | Low | Global |
| `skills.load.extraDirs` | Lowest | Custom shared |

Reload: `/new` in chat or `openclaw gateway restart`.

### Instruction Writing Patterns

**1. Explicit decision trees, not vague instructions.** Write if/then branches for every trigger scenario and every "when NOT to trigger" case. The agent should never guess.

**2. Focused scope.** One skill per pipeline stage (`omnigraph_ingest`, `omnigraph_query`, `omnigraph_synthesize`, `omnigraph_status`, `omnigraph_manage`), not a monolithic skill.

**3. Guard clauses before destructive actions.** Any skill that deletes/overwrites KG data must: show what will change, ask for explicit confirmation, wait for "yes"/"y"/"confirm", and never batch-delete >10 nodes without listing them.

**4. Consistent output formatting.** Define in the skill body: >5 items = markdown table, ≤5 = bullet list, COUNT = plain number, errors = `⚠️ [Type]: [What happened]. [What to do next].`

**5. Environment variables, not hardcoded paths.** Reference env vars by name in the skill body (`GEMINI_API_KEY`, `OMNIGRAPH_DATA_DIR`, `OMNIGRAPH_IMAGE_PORT`).

**6. Skill composition via references.** Skills can't call each other directly. Document dependencies explicitly: "For ingestion, see the `omnigraph_ingest` skill."

### Planned Skills for This Project

| Skill | Description | Triggers |
|---|---|---|
| `omnigraph_ingest` | Ingest a URL into the knowledge graph | "add this to my kb", "ingest", "save this article" |
| `omnigraph_query` | Query the KG by natural language | "what do I know about", "search my kb" |
| `omnigraph_synthesize` | Generate a synthesized report from the KG | "write a report on", "summarize what I know about" |
| `omnigraph_status` | Check pipeline health and graph stats | "kg status", "how many nodes" |
| `omnigraph_manage` | List, delete, or re-index KG entities | "remove entity", "list all tools", "reindex" |

### Testing Skills

- `openclaw agent --message "<trigger phrase>"` exercises the golden path
- Test with missing env vars — guard clause should fire cleanly
- Test destructive actions — confirmation prompt must appear
- Test edge cases (empty result, ambiguous entity) — output format must hold
- `openclaw skills list` to verify skill appears with correct description

### Publishing

```bash
# OpenClaw → ClawHub
openclaw skills publish my-skill --to clawhub

# Hermes → GitHub
hermes skills publish skills/omnigraph-query --to github --repo sztimhdd/OmniGraph-Vault
```

SkillHub reviewers check: metadata correctness, focused scope, guard clauses on destructive ops, references/scripts separation, README.md present.

### Agent-Created Skills (Hermes Self-Improvement)

After 5+ tool calls on a complex task, Hermes evaluates whether to auto-create a skill at `~/.hermes/skills/[category]/`. Let these accumulate during development — they capture real usage patterns. Review periodically and promote good ones to the project skills directory.

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

A production Hermes instance runs OmniGraph-Vault on a remote PC (WSL2 Linux). It is the only place where the full skill → script → LightRAG → Gemini flow can be exercised against real deployed state: real KG data, real `~/.hermes/.env`, real gateway routing, real scraper credentials. The remote PC is also the primary dev machine for Hermes-integration work, so its git state may be ahead of GitHub.

**When to use it:**

- End-to-end testing of ingest / query / architect skills against deployed Hermes
- Reproducing bugs the user reports from their actual Hermes workflow
- Verifying a local code change behaves correctly on the target environment
- Confirming deployed env vars, runtime data state, or KG contents

**How to reach it:**

SSH connection details (host, port, user, auth) are in project memory at `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md` — loaded automatically into every session for this project via the memory index. Never commit credentials or hostnames into this repo.

**Before running a remote test, always reconcile git state first:**

```bash
# Check if remote has unpushed commits before assuming local view is current
ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && git status -sb && git log --oneline -5"
```

If remote is ahead: push from remote, pull locally, and re-read any changed files before making recommendations. Decisions based on stale local code will mislead the user.

**Typical workflow:**

1. SSH into the remote PC (details from memory)
2. `cd ~/OmniGraph-Vault && git pull --ff-only`
3. `source venv/bin/activate` (remote uses `venv/bin/`, not `venv/Scripts/`)
4. Reproduce the issue or run the test
5. Capture logs and KG state changes
6. Propose a fix locally, push, pull on remote, re-test

**Remote runtime paths (WSL2 Linux):**

- Code: `~/OmniGraph-Vault`
- Runtime data: `~/.hermes/omonigraph-vault/` (typo is canonical — do not rename)
- Env: `~/.hermes/.env`
- Hermes gateway state: `~/.hermes/gateway.pid`, `~/.hermes/state.db`

**Do NOT commit credentials, hostnames, ports, or usernames to this file.**

---

## Lessons Learned

- Cognee batch operations silently drop entities if the buffer path isn't checked for `.processed` markers — always verify idempotency
- The runtime data directory is `omonigraph-vault` (typo is baked into config.py and deployed environments — do not "fix" it without a coordinated migration)
- `CDP_URL` supports two modes auto-detected by the `/mcp` URL suffix: local Edge (`localhost:9223`) uses `playwright.connect_over_cdp()`; remote testing (`host:port/mcp`) uses `_MCPClient` (MCP-over-SSE with `mcp-session-id` header). The MCP server requires `initialize` first, then subsequent requests must include `mcp-session-id` in the header — without it every call returns "Server not initialized".

### 2026-05-04 (Day-2 cron prep)

1. **SQLite CHECK constraint 不能 ALTER** — 加 status 枚举值需要 table-rebuild 流程（CREATE TABLE new → INSERT SELECT → DROP → RENAME）。或者从一开始用宽松类型 + 应用层校验。教训：所有 status/enum 字段建表前想好全集，否则 migration 成本高且容易忘。

2. **Commit 在前，报告在后** — 工作目录里的改动不算完成。报 "Done" 之前必须 `git log` 看到 commit（最好已 push）。没 commit 的改动在下次 rebase / 环境切换时就丢了。连续两次忘记 commit 后加入此条作为强制规则。

3. **CHECK constraint vs INSERT 值偏离是 latent bug 模式** — `skipped_ingested` 和 `dry_run` 值在 INSERT 里已存在至少一周，但 CHECK whitelist 没同步更新，直到某天有人跑一条特定的 code path 才触发 `IntegrityError`。防御：CI 应跑 schema consistency check（INSERT 里出现的所有 status 值是否都在 CREATE TABLE CHECK 白名单里）。有空加 `tests/unit/test_schema_consistency.py`。

### 2026-05-05 (Day-2 trigger analysis)

1. **LightRAG entity/relation upserts are 1-text-per-call; only chunks are batched.** `operate.py:1920-1938` (entity) and `:2472-2490` (relation) pass single-item dicts to vdb upsert; `nano_vector_db_impl.py:108-124` then calls `embedding_func` once per single-item batch. Only `chunks_vdb` (`lightrag.py:1311-1338`) passes multi-chunk dicts that actually exercise `embedding_batch_num`. Implication: rewriting `lib/lightrag_embedding.py:207` (host-side `for text in texts` loop) into a Vertex batch-API call only helps the ~5-30 chunks/article; entities + relations (hundreds/article) stay 1-text-per-call regardless. Realistic S2 speedup is 3-6× from in-flight concurrency (`embedding_func_max_async × graph_max_async`), NOT 10-20× from HTTP batching. To get true N-text batches on entity/relation paths requires upstream LightRAG changes (bulk upsert at `operate.py`), out of host scope. See `docs/research/lightrag_internals_2026-05-04.md`.

2. **Scrape-first classify has irreducible Apify cost on filter-rejected articles.** When `--topic-filter` rejects post-classify, the ~75-90s Apify scrape happens BEFORE rejection is known. Day-2 trigger 2026-05-05 wasted 17/32 min (53%) on 5 such articles. The pre-scrape checkpoint guard at `batch_ingest_from_spider.py:1140-1155` (commit 9150246) only catches anomalous partial-state (scrape ckpt exists + body=NULL); does NOT address fresh-article scrape-then-filter waste. Permanent fix: graded classification (cheap title+excerpt LLM probe before scrape). See REQUIREMENTS.md "Future Requirements / v3.5".

3. **Verify ingest progress from DB, not in-process counters.** Day-2 trigger's in-process report claimed "ok=0 new at 00:08 ADT" while `SELECT * FROM ingestions WHERE date(ingested_at)='2026-05-05'` showed `article_id=372 status=ok @ 00:06:09 ADT`. In-process counters can lag committed rows or count differently. When monitoring long batches, query `ingestions` table directly.

### 2026-05-05 (afternoon — cascade + body persistence work)

1. **"Half-fix" pattern is silent and expensive.** `ecaa2df` (SCR-06) fixed the cascade orchestrator (`lib/scraper.py`) to extract Apify's `markdown` key, but the consumer at `batch_ingest_from_spider.py:948` still only checked `content_html` — silent reject of 121 articles overnight (53% of pool). When changing data-shape contracts, **always audit producer↔consumer pairs together** — diff the new field against every call site before declaring done.

2. **Body must persist atomically before any downstream gate.** Pre-Bug 3 (`8ac3cb1`), if scrape succeeded but classify or LightRAG ingest failed (timeout, hang, exception), the scraped body lived only in memory and was discarded on reject — paid Apify call wasted, next run re-scrapes. Architectural rule: write `articles.body` immediately on scrape success, **independent of downstream success**. Verified via Hermes Phase 1 inventory — 113 SCR-06 victims had `body=NULL` despite Apify having succeeded.

3. **Multi-page WeChat articles (`idx=1..N`) are normal article structure, not enrichment.** Same `__biz + mid` with different `idx` are pages of one long-form article. Pre-`ecaa2df`, each sub-page incurred 180s CDP timeout waste — multi-page articles took 28+ min vs ~10 min after fix. Don't try to "optimize" sub-pages away; they're real content.

4. **Apify result lost on consumer reject = silent paid-for waste.** Same root cause as #1, but the operational angle: every Apify success consumed real API quota. Pre-fix every consumer reject (121 articles overnight) burned that quota with zero data captured. Even monitoring tools won't catch this — Apify dashboard says SUCCEEDED, ingestions table says skipped, no log connects them. Periodic audit: cross-reference Apify spend × ingestions outcomes.

5. **Embedding/Vision worker timeouts disproportional to LLM timeout.** Track 3 (Hermes B) flagged: when `OMNIGRAPH_LLM_TIMEOUT_SEC` bumped 600 → 1800 for image-heavy articles, the embedding worker still has a 60s timeout (and Vision per-image timeouts are similar). Currently doesn't bite, but as graph grows or vision providers get slower, the 30× ratio becomes a hidden ceiling. Worth tracking as a v3.5 candidate (proportional timeouts).

6. **DB candidate SELECT does not exclude `status='skipped'` rows.** Articles previously rejected for any reason are naturally re-pulled by the next `--from-db` ingest run. Useful: rejection due to fixed bug auto-recovers without explicit reset. Risky: a permanent reject reason (genuinely dead URL) will be retried daily forever. Worth tracking in a `skip_reason_version` field — see REQUIREMENTS.md "Future Requirements / v3.5" reject-reason versioning.

### 2026-05-06 (v3.4 prep hardening + reliability test)

1. **Reliability-N test ahead of cron cutover catches regressions cheaply.** A focused 5-article `--max-articles 5` run on the production target (Hermes) takes ~22 min wall-clock at 4-5 min/article post-ecaa2df, exercises the full pipeline (scrape → classify → ingest → vision), and produces DB rows + log evidence within one tea break. Compare: chasing a regression after it surfaces in a hours-long automated cron means correlating logs across thousands of failure points. Keep this pattern — cheap pre-cutover smoke after every batch of fixes, before signing off the cron baseline.

2. **DB rollback hygiene: backup file before DELETE, never trust the WHERE clause alone.** Rolling back the 845 'CV'-corrupted rows from Phase 2b+ overnight, the safe form was `cp data/kol_scan.db data/kol_scan.db.backup-pre-rollback-$(date +%Y%m%d-%H%M%S)` THEN `DELETE FROM ... WHERE classified_at >= '...'`. Backup file lets you `cp` back if the WHERE clause was wrong; the timestamped name self-documents what state the backup represents. Phase 2b+ rollback touched 53% of recent classifications — a typo'd WHERE could have cost a week of work.

3. **Synthesis output overwrite was a latent bug masked by infrequent use.** `kg_synthesize.py` wrote every answer to a single canonical filename (`synthesis_output.md`). User noticed only after morning's first answer was lost when they queried again in the afternoon. Pattern: any "single canonical output file" that is read-after-write by a downstream consumer (Telegram skill, in this case) should also be archived to a unique-per-call file when there is any chance the canonical file gets re-written before the consumer reads it. The fix (`1a2daed`) writes both: unique archive (`synthesis_archive/YYYY-MM-DD_HHMMSS_<slug>.md`) for permanence, canonical file for back-compat consumer.

4. **Manual reliability test is NOT a substitute for automated cron baseline.** Reliability-5 5/5 OK proves the pipeline is correct at 5-article scale; it does NOT prove the Hermes cron scheduler will not SIGTERM the process at the 600s inactivity ceiling, will not lose stdout buffering across hour-scale runs, will not interact badly with concurrent Hermes background tasks. Until the next 06:00 ADT cron fires successfully, the v3.4 milestone gate stays BLOCKED. Don't let "manual run worked" tempt you into lifting the gate early.

5. **并发 GSD agent 共享 commit staging — `git reset --soft` race lost STK-02/03 file attribution.** 2026-05-06 evening Phase 21 quick (260506-rjs) shipped `scripts/cleanup_stuck_docs.py` + 13 unit tests + closure doc; the orchestrator's quick wrapper called a `git reset --soft` to repackage the commit message, but a parallel `gsd-roadmapper` agent on the same worktree had already staged its own roadmap files in the meantime. The reset rolled both agents' staged areas together, and the next commit (`8a4a18e`, message `docs(agentic-rag-v1): create roadmap`) swept the STK-02/03 deliverables into the roadmapper's commit — file contents byte-identical to spec, but attribution is wrong. Lesson: on a shared worktree with concurrent GSD agents, NEVER `git reset --soft`/`--mixed`/`--hard` and NEVER `git commit --amend` — those operations touch the staging area / HEAD, both shared between agents. Use only `git add <explicit-files>` + `git commit` (forward-only, atomic). Solo quick(无并发)无此风险。

### 2026-05-07 (CV mass-classify postmortem)

1. **任何 schema/SQL 改动必须在 production-shape 数据上跑过完整使用场景才能 push。** Quick 260506-se5 (commit `c786a83`) 把 classifications 表从 `(article_id, topic)` 多行模型改成 `(article_id)` 单行 + UPSERT,migration 004 加了 `idx_classifications_article_id` 单列 UNIQUE INDEX,production INSERT 改成 `ON CONFLICT(article_id) DO UPDATE SET topic=excluded.topic, ...`。单元测试用 mock SQLite 单 INSERT 验证 dedup + UPSERT 行为都正确,migration 跑完表里只剩一行也是预期。**但生产 cron 用的是多次 sequential CLI invocation(每次一个 `--topic`,共 5 个 topic),5 次 INSERT 在新 schema 下变成 5 次 UPSERT 覆盖 topic 字段,最后一个 topic('CV')赢**。结果 2026-05-07 08:29 ADT cron 把全部 653 行 classifications 都标成 'CV',下游 ingest cron(filter `agent,hermes,openclaw,harness`)滤完零候选。修复 `428b16f` 反转两处生产调用点回 `ON CONFLICT(article_id, topic)`,migration 005 反向 drop 了 004 的 article_id 单列 UNIQUE。教训:**任何涉及 ON CONFLICT 子句或 UNIQUE 约束的 schema 改动,ship 之前必须 grep 整个 codebase 把所有使用该约束的 INSERT 调用点都过一遍,并在 production-shape 数据上模拟完整 cron 调用序列(包括 sequential per-topic invocation),Mock-only 单元测试不抓这种 cross-component bug**。

   **可操作的预防**:在 v3.5 候选清单加 1 条 "production-shape local snapshot + cron loop simulator" — 本地能跑 24h cron 路径仿真(包括 multi-invocation sequence),任何重大改动 push 前必跑一遍。`.dev-runtime/data/kol_scan.db` 已是 production schema 的本地镜像,缺的是 cron 调用序列的 driver 脚本。

2. **migration 反向必须配套 INSERT call site 反向。** 修 CV 事故时第一反应是只改 `batch_classify_kol.py:447`,但 grep 发现 `batch_ingest_from_spider.py:1024` 也用了同一 `ON CONFLICT(article_id)` 子句(Phase 20 RIN-01 加的 full-body classify 写入路径)。如果只 drop 索引不改第二处 INSERT,migration 005 部署后 ingest 路径会 raise `sqlite3.OperationalError: ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`。教训:**`ON CONFLICT(col)` 在 SQLite 里需要 col 上有 UNIQUE/PRIMARY KEY 约束才能解析;dropping 这个约束必须同步把所有 `ON CONFLICT(col)` 改成绑定到剩余的 UNIQUE 上**。grep 模式:`grep -rn "ON CONFLICT.<column>." production_paths/` 在每次改 UNIQUE 约束前后都跑一次。

### 2026-05-08 (cron failure → 260508-ev2 quick + ir-1 fabrication + token leak incident)

1. **Cascade order divergence between `lib/scraper.py` and `ingest_wechat.py` was a latent bug.** `lib/scraper.py:_scrape_wechat()` cascade was `Apify→CDP→MCP→UA`(paid first); `ingest_wechat.py:920-942` had `UA→Apify→MCP→CDP`(free first). `batch_ingest_from_spider.py` routes through `lib/scraper.py`, so 2026-05-08 09:00 ADT cron used the bad order — wasted ~600s/article on Apify (账号余额耗尽) + CDP (browser session 不可用) + MCP (返回空) before falling through to UA which works 100%。诊断 `docs/bugreports/2026-05-08-cron-ingest-failure.md` (commit `29486aa`),quick `260508-ev2` 修了:F1a Apify dual-token rotation(`APIFY_TOKEN_BACKUP` env var),F1b cascade reorder + `SCRAPE_CASCADE` env var override,F2 tmux helper 取代 Hermes 900s 终端超时。教训:**重构 cascade 顺序时,必须 grep 全 codebase 找所有 parallel cascade 实现并同步**。grep 模式:`grep -rn "scrape_wechat_apify\|scrape_wechat_cdp\|scrape_wechat_mcp\|scrape_wechat_ua" lib/ *.py` 任何修改前后都跑一次。

2. **Agent fabrication 在 execute phase 高风险,smoke-evidence-required 是必须的。** 2026-05-07 ir-1 execute agent ship `fc13098` 的 commit message body 灌了完全伪造的 smoke stats(声称 18 batches × 0 NULL × 531 rows × 76% reject rate,实际只跑了 1 batch 撞 403 PERMISSION_DENIED 全 NULL)。被 user 自己 review 发现并要求 cleanup:`b874696` revert + `f38138b` re-author with truthful body。教训:**任何 commit message body / SUMMARY.md / runbook 的"我跑了 X 验证 Y"声明,都必须 cite raw log 文件 + 行号** (`see .scratch/...log L1-L20`)。Mitigation:agent prompt 强约束 "no unverifiable claims, all smoke data must reference .scratch/...log file path",从此固化(见 quick `260508-ev2` 的反 fabrication 段)。

3. **Never put literal secrets in agent prompts — use placeholders.** Quick `260508-dep` 第一版 prompt 直接 paste 了 Apify backup token literal:`echo "APIFY_TOKEN_BACKUP=apify_api_FB3..." >> ~/.hermes/.env`。Agent 顺从地把这行 verbatim 写进 `HERMES-DEPLOY-260508-ev2.md` + PLAN/SUMMARY,7 local commits 后 push 被 GitHub secret scanning 阻断。Recovery 走:rotate token → rebase local 7 → 5 commits → push clean。教训:**任何 agent prompt 中的 token / key / credential 都必须用 placeholder**(`$VAR_NAME` / `<retrieve from password manager>` / `<see Hai's session notes>`),operator side-channel 直接 inject 到 `~/.hermes/.env`,**不留 literal 进任何 commit history**。Memory 也 record:`feedback_no_literal_secrets_in_prompts.md`。

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
- **Platform**: Windows-primary (Edge for CDP); Cognee requires Python 3.12 venv per wrapper
- **Single user**: No auth, no isolation required — personal tool only
- **Stack**: Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ - Entire application, core pipeline logic, ingestion, synthesis
- Python 3.12 - Virtual environment target (referenced in `cognee_wrapper.py`)
- Markdown - Documentation and content rendering (`.md` files, synthesis outputs)
## Runtime
- Python 3.11+ interpreter
- Virtual environment: `venv/` (standard Python venv)
- OS-agnostic with Windows Edge CDP integration fallback
- pip (Python package manager)
- Lockfile: `requirements.txt` (present, pinned dependencies)
## Frameworks
- LightRAG - Knowledge graph construction and querying engine
- Cognee - Stateful memory layer for context tracking
- pytest (implied from `tests/` directory structure with `verify_gate_*.py` files)
- No explicit build system (pure Python scripts)
- Environment: Python standard library + third-party packages
## Key Dependencies
- google-genai - Google Gemini API client for LLM and vision
- apify-client - Apify platform SDK for web scraping
- playwright - Browser automation with CDP (Chrome DevTools Protocol) fallback
- beautifulsoup4 - HTML/XML parsing and DOM navigation
- pymupdf (fitz) - PDF extraction
- html2text - HTML to Markdown conversion
- lancedb - Vector database for embeddings (installed, usage in LightRAG)
- kuzu - Graph database backend (installed, used by LightRAG for graph storage)
- numpy - Numerical computing for embedding operations
- Pillow (PIL) - Image file handling and processing
- python-dotenv - Environment variable loading from `.env` files
- nest-asyncio - Async event loop nesting for Jupyter-like environments
- requests - HTTP client for image/file downloads
- watchdog - File system event monitoring (installed, likely for future batch processing)
- litellm - LLM provider abstraction layer
- instructor - Structured output extraction for LLMs
## Configuration
- `.env.example` provided for reference
- Actual secrets loaded from: `~/.hermes/.env` (user home directory)
- Key required variables:
- Base data directory: `~/.hermes/omonigraph-vault/` (user home)
- RAG working directory: `~/.hermes/omonigraph-vault/lightrag_storage/`
- Image storage: `~/.hermes/omonigraph-vault/images/`
- Synthesis output: `~/.hermes/omonigraph-vault/synthesis_output.md`
- Entity buffer: `entity_buffer/` directory for async processing
- Canonical mapping: `canonical_map.json` for entity normalization
- No build configuration files (pure Python, no compilation)
- Entry points are command-line scripts:
## Platform Requirements
- Python 3.11+ interpreter
- Virtual environment support (`venv`)
- Windows Edge browser (for CDP fallback at `http://localhost:9223`)
- Linux/Mac: Chromium or Chrome with CDP support
- Python 3.11+ runtime
- Local HTTP server capability (port 8765 for image serving)
- CDP-enabled browser (Edge on Windows, Chrome/Chromium on Linux)
- Network access to:
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module scripts: lowercase with underscores (`cognee_wrapper.py`, `multimodal_ingest.py`, `kg_synthesize.py`)
- Configuration: `config.py`
- Test verification scripts: `verify_gate_*.py` (e.g., `verify_gate_a.py`)
- Async functions: lowercase with underscores, descriptive names (`disambiguate_entities`, `ingest_pdf`, `synthesize_response`, `query_and_synthesize`)
- Helper functions: lowercase with underscores (`load_env`, `describe_image`, `llm_model_func`, `embedding_func`)
- Main entry points: `main()` in `if __name__ == "__main__"` blocks
- Constants: UPPERCASE with underscores (`GEMINI_API_KEY`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `VENV_SITE_PACKAGES`)
- Local variables: lowercase with underscores (`query_text`, `response`, `canonical_map`, `pdf_path`)
- Cache/state: prefixed with underscore for internal use (`_disambiguation_cache`)
- Type hints used in function signatures: `list[str]`, `np.ndarray`, `dict`
- Return types documented in async functions: `async def function_name(...) -> ReturnType:`
## Code Style
- No explicit formatter configured (black/ruff not detected)
- Manual formatting conventions observed:
- No `.eslintrc`, `.pylintrc`, or similar configuration found
- No linting tool requirements detected in `requirements.txt`
- Manual code review likely the primary quality control
## Import Organization
- None detected. Full module paths used throughout (`from lightrag.lightrag import LightRAG`).
- Local modules imported directly by name (`import cognee_wrapper`).
## Error Handling
- Return `None` on non-critical failures: `cognee_wrapper.py` functions
- `sys.exit(1)` on critical startup failures (missing API keys, imports)
- Print warnings and continue on recoverable errors
## Logging
- Module-level logger: `logger = logging.getLogger("module_name")`
- Levels used: `INFO`, `ERROR`, `WARNING`
- Basic configuration: `logging.basicConfig(level=logging.INFO)`
- File handlers for batch processes: `logging.FileHandler("/path/to/logfile.log")`
- Heavy use of `print()` for console output (not using logging in all cases)
- Examples: `query_lightrag.py`, `multimodal_ingest.py` use both print and logging
- Convention: Use `print()` for user-facing output, `logger` for operational logs
## Comments
- Inline comments for non-obvious logic (rare in this codebase)
- TODO/FIXME comments: None detected
- Configuration comments: Yes (e.g., "Force standard Gemini API mode")
- Minimal docstrings present
- Examples:
- Not consistently applied across all functions
## Function Design
- Functions range from 5 lines to 50+ lines
- Typical: 15-35 lines for business logic
- Larger functions: `ingest_pdf()` (~55 lines), `ingest_wechat()` (~150 lines)
- Use keyword arguments with defaults: `mode: str = "naive"`
- Environment-based configuration common (from `os.environ`)
- Async functions accept `**kwargs` for flexibility
- Early returns on error conditions
- Multiple return paths (success/failure):
## Module Design
- No explicit `__all__` definitions detected
- Functions defined at module level are importable
- Internal module state: `_disambiguation_cache = {}`
- Not used. Each module is self-contained.
- `config.py` serves as shared configuration module.
- Configuration loaded at module import time (top-level code execution)
- Example from `cognee_wrapper.py` (lines 7-45): Environment variables, logging setup, and module imports all happen at import time
- This means configuration is not testable without modifying environment
## Async Patterns
- `nest_asyncio.apply()` used to allow nested event loops (development/Jupyter compatibility)
## Antipatterns Observed
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Asynchronous pipeline-based processing (all I/O operations use `async`/`await`)
- Dual-fallback scraping strategy (primary + redundant methods)
- Pluggable LLM backends (Gemini for both generation and embeddings)
- Decoupled memory layer (Cognee) for entity canonicalization and context recall
- Local-first data persistence (all artifacts stored in `~/.hermes/kg-vault/`)
## Layers
- Purpose: Extract content from external sources (web, PDF) and normalize to markdown
- Location: `ingest_wechat.py`, `ingest_pdf()` in `ingest_wechat.py`, `multimodal_ingest.py`
- Contains: Web scraping (Apify + CDP fallback), PDF extraction (PyMuPDF), image download/description
- Depends on: Playwright (CDP), Apify SDK, BeautifulSoup, html2text, Gemini Vision API
- Used by: Orchestration scripts (command-line interfaces)
- Purpose: Build and maintain the graph structure (entities, relationships, concepts)
- Location: LightRAG (external library in `requirements.txt`)
- Contains: Graph construction via `ainsert()`, querying via `aquery()`
- Depends on: Gemini LLM (generation) + Gemini Embeddings (vector representation)
- Used by: Synthesis layer for retrieval and inference
- Purpose: Track conversation history, learn entity aliases, deduplicate synonyms
- Location: `cognee_wrapper.py`, `cognee_batch_processor.py`
- Contains: Entity disambiguation, past query recall, synthesis memory storage
- Depends on: Cognee library with Gemini backend
- Used by: Synthesis layer to add historical context and entity normalization
- Purpose: Answer queries by combining LightRAG retrieval with memory context
- Location: `kg_synthesize.py`, `query_lightrag.py`
- Contains: Custom prompt engineering, response generation, Cognee integration
- Depends on: LightRAG queries + Cognee context recall
- Used by: External agents (Openclaw, Hermes Agent) via subprocess calls
- Purpose: Centralized path and secret management
- Location: `config.py`
- Contains: Environment loading from `~/.hermes/.env`, base paths for storage
- Depends on: OS environment variables, pathlib
- Used by: All other layers during initialization
## Data Flow
- **LightRAG index**: Persistent in `~/.hermes/kg-vault/lightrag_storage/` (graph edges, entities, embeddings)
- **Cognee memory**: Persistent in Cognee's internal DB (conversation state, entity aliases)
- **Canonical map**: JSON file at `~/.hermes/kg-vault/canonical_map.json` (entity normalization rules)
- **Entity buffer**: Temporary JSON files in `entity_buffer/` directory, processed async by batch processor
- **Images**: Local copies at `~/.hermes/kg-vault/images/{article_hash}/` with metadata.json + final_content.md
## Key Abstractions
- Purpose: Represents a software tool or framework in the knowledge graph
- Examples: LightRAG, Cognee, n8n, Cursor (as described in `specs/OMNIGRAPH_VISION_Statement.md`)
- Pattern: Tree-like schema with identity fields (name, aliases, category), knowledge layers (official_docs, community_zh, tutorials), and relationship edges (BASED_ON, INTEGRATES, COMPETES, USED_WITH)
- Purpose: Encapsulates query mode and response type for LightRAG
- Examples: `QueryParam(mode="hybrid", response_type="Detailed Markdown Article")`
- Pattern: Simple dataclass passed to `rag.aquery()` to control retrieval strategy
- Purpose: Intermediate data structure from scraping (Apify or CDP)
- Pattern: Dictionary with keys: title, markdown/content_html, publish_time, url, method
- Example: `{"title": "...", "markdown": "...", "publish_time": "2024-04-01", "method": "apify"}`
## Entry Points
- Location: Project root
- Triggers: `python ingest_wechat.py <url>` (or default hardcoded URL)
- Responsibilities: Primary ingestion script for WeChat articles and web content
- Invokes: Apify client, CDP browser, Gemini Vision for images, LightRAG insertion, Cognee entity buffering
- Location: Project root
- Triggers: `python kg_synthesize.py "<query>" [mode]` (subprocess call from agent)
- Responsibilities: Answer user queries with synthesis
- Returns: Markdown response to stdout and file at `~/.hermes/kg-vault/synthesis_output.md`
- Location: Project root
- Triggers: `python query_lightrag.py "<query>"` (direct LightRAG query without Cognee)
- Responsibilities: Raw knowledge graph queries for debugging/validation
- Returns: Direct LightRAG response to stdout
- Location: Project root
- Triggers: `python multimodal_ingest.py <pdf_path>` (local file ingestion)
- Responsibilities: PDF extraction with image description and indexing
- Returns: Ingested content in LightRAG, local copies in images directory
- Location: Project root (meant to run as daemon/background task)
- Triggers: Scheduled or continuous polling of `entity_buffer/` directory
- Responsibilities: Async entity canonicalization and map building
- Operates: Watches for new `*_entities.json` files, processes them, marks `.processed`
## Error Handling
- Scraping: Apify (primary) → CDP (secondary) → fail with clear message
- Image download: HTTP error → log warning, continue (don't block article ingestion)
- Image description: Gemini API error → fallback string "Error describing image: {e}"
- Cognee operations: Always wrapped in try/except, warnings logged, main flow unaffected (async + non-blocking)
- LightRAG queries: Retry loop (3 attempts with 5s backoff) before raising exception
```python
```
## Cross-Cutting Concerns
- Print-based for CLI scripts (no structured logging framework)
- File-based for batch processor: `cognee_batch.log` at `/home/sztimhdd/OmniGraph-Vault/cognee_batch.log`
- Input URL validation: Basic `startswith('http')` checks for images
- File existence checks before processing (PDFs, env files)
- API response status code checks (HTTP 200 for image downloads)
- Gemini API: Via environment variable `GEMINI_API_KEY`
- Apify: Via `APIFY_TOKEN` (optional, non-critical fallback)
- CDP: Via `CDP_URL` environment variable (default `http://localhost:9223`)
- Cognee/LiteLLM: Credentials sourced from Gemini API key
- Image downloads: Atomic write to temp, no partial files left behind
- Canonical map: Atomic JSON write (write to `.tmp`, then `os.rename()`)
- Entity buffer: Explicit `.processed` marker after each file processed (idempotent)
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
