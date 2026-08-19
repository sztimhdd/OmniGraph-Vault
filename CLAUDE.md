# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Detailed runbooks live in `docs/OPERATIONS.md` (loaded on demand). Global behavioral principles + security + Databricks/MCP rules live in `~/.claude/CLAUDE.md` and `~/.claude/docs/`.

## Agent skills

### Issue tracker

Local markdown, one file per ticket under `.scratch/<feature-slug>/` for active engineering-flow work; cross-referenced with the durable `.planning/ISSUES.md` backlog for known-but-not-in-flight issues. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root (created lazily by `/domain-modeling`, not yet present). See `docs/agents/domain.md`.

## Highest-Priority Principles

Principles **1–4** (Think Before Coding · Simplicity First · Surgical Changes · Goal-Driven Execution) are defined in `~/.claude/CLAUDE.md` — they apply here verbatim, not restated.

> **Surgical-changes exception — wiki cross-link 反链:** adding `[[your-new-slug]]` back-links to *other people's* wiki entity files is a common need (互通图谱) but violates surgical-changes. Handle as a separate follow-up quick, NOT folded into the current wiki-writing quick — atomic commit boundaries stay clean. (Ref: 2026-05-29 commit f5da904.)

**5. Don't outsource mechanical work to the user.** Pick the right channel and run it yourself. Mutate Hermes prod state (cron/env/deploy/restart) → write a paste-ready Hermes operator prompt. Read-only diagnostic / file ops on Hermes → run SSH yourself via Bash. Local repo read/grep/pytest/git/edit → run yourself. **Hard rule:** never write "paste this SSH command and report back." Either run it yourself or convert it to a Hermes prompt. The only thing the user pastes is Hermes report output or explicit decisions.

**6. KB local deploy + UAT is mandatory before any KB phase marked complete.** Any change under `kb/` MUST be verified end-to-end via local one-port deploy before "complete" — green tests are necessary but NOT sufficient. Steps: (1) `venv/Scripts/python.exe .scratch/local_serve.py` (`:8766` serves SSG + `/api/*` + `/static/*`); (2) curl every endpoint family the phase touched; (3) browser UAT desktop/tablet/mobile, screenshots to `.playwright-mcp/`; (4) cite UAT evidence in `<phase>-VERIFICATION.md`. Never mark `complete` in VERIFICATION/STATE/ROADMAP until Local UAT is done + cited. (Authored 2026-05-14 after kb-3: 256 green tests missed missing `/static/qa.js`, embedding-dim mismatch, FTS5 drift.) Full doc: `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3.

**7. Claude owns all Databricks App deployments autonomously.** Never ask the user to run `databricks sync`/`apps deploy`/logs — run them yourself via PowerShell (Git Bash breaks `/Workspace/...` paths). Report the result ("FTS populated with 2598 articles, search works"), not the mechanical steps.

**8. Right-size ceremony — diagnostic complexity ≠ fix complexity.** (GSD tooling removed 2026-08-09; the ceremony ladder survives it.) Re-pick workflow weight AFTER diagnosis reveals fix scope, with a numeric LoC estimate. LoC ≤5 (single file, obvious, tests cover it) → direct Edit→commit→deploy, no ceremony. 5–50 → "quick": one atomic commit tagged `quick-<yymmdd>-<id>` in the message, no plan doc. >50 / multi-file / architectural → plan first (plan mode or planner agent), then implement→verify. Investigation-heavy + fix-light = 2 quicks (investigate read-only, then ship), NOT one planned phase. Inverse: if a quick expands past ~50 LoC or multiple subsystems, halt and write a plan. (2026-05-26 bug 2c burned 5+h of plan ceremony to ship 16 LoC.)

**9. Touching `kb/static/` or `kb/templates/` requires full Makefile deploy.** These layers need the full pipeline (Pass 0a SSG bake → 0b lang flip → 0c dep stage → 0d brand flip → Pass 1→2→3). Sync-only (Pass 2+3) is invariably wrong — Databricks Apps serves `databricks-deploy/_ssg/static/`, regenerated only by Pass 0a bake. Decision rule: `git diff <prev>..HEAD --name-only | grep -E 'kb/(static|templates)/'` → any match forbids sync-only. `kb/services/`, `kb/api_routers/`, `kb/api.py` → sync-only Pass 2+3 OK. When in doubt, full pipeline. Hot-patch inverse: may directly edit `databricks-deploy/_ssg/...` + sync `_ssg/` only for diagnostics, but flag as temporary (next bake rolls it back) + queue permanent full-pipeline fix. (2026-05-27 bug 2c shipped a qa.js fix that never reached users via sync-only.)

**10. `.planning/ISSUES.md` is the single source of truth for known unfixed issues** outside active phases/quicks. Grep it before starting any quick or planned phase (inherit prior context; annotate `In flight: <slug>` when picking one up). During close-out, orchestrator (NOT agent) adds rows for newly surfaced out-of-scope issues before marking CLOSED; update `Last updated:`. Never delete — move resolved rows to "Resolved (recent)" with date+commit+slug, archive after 30d to `.planning/archive/`. Severity: 🔴P0 / 🟡P1 / 🟠P2 / 🟢P3 / 🔵Doc. Not a replacement for ROADMAP/STATE/SUMMARY. Agents read it; orchestrator curates it.

## Project-Specific Discipline — Behavior-Anchor Harness for Hot Orchestration Code

Long-running orchestrators that batch I/O and silently swallow exceptions need pytest harnesses anchored on **observable behavior**, not internal call shape. `batch_ingest_from_spider.py:ingest_from_db()` is the canonical case (600+ LOC, nested batches, broad `except`; 5 prod-only failure modes shipped through 256-green CI in 90 days). **Rule:** any contract-shape change to `ingest_from_db` (candidate_rows tuple column, SKIP_REASON_VERSION, layer2 verdict member, persistence column, mid-loop early-exit) MUST add (1) a test in `tests/unit/test_ingest_from_db_orchestration.py` pinning behavior on observable post-conditions (seeded-DB rows, mocked-callable args, tmp_path files); (2) matching schema update in `tests/unit/_ingest_fixtures.py:in_memory_db()` (fixture drift is itself a failure mode); (3) `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` passing. Applies ONLY to `ingest_from_db` and future orchestrators meeting all three signals (>300 LOC nested batches, silent broad-except around external calls, cost/correctness consequence from missed call sites). The in-scope set is `{ingest_from_db}` and grows only by editing this rule.

## Project Summary

Personal graph-based KB giving Hermes Agent (and OpenClaw) persistent memory over articles/PDFs. Drop a WeChat URL or PDF → scrape → extract entities+images → index into LightRAG → surface via two skills (ingest, query). **Stack:** Python 3.11+, LightRAG (KG), Gemini 2.5 Pro/Flash (LLM+vision), Apify + Playwright CDP (scraping), local image server (:8765). **Constraints:** all data local (only Gemini API + Apify make external calls); Windows-primary; single-user (no auth); no framework migrations. **Runtime data:** `~/.hermes/omonigraph-vault/` (typo canonical — do NOT rename without coordinated migration).

## Release Status

**v1.0 (Knowledge Collection + Ingestion)** declared 2026-05-13; all v1.0.x/y/z closed by 2026-05-17. Stable baseline: scan → Layer 1 → scrape → Layer 2 → enrich → ainsert → reconcile; KOL + RSS first-class. **Closed 2026-05-24:** aim-2 LightRAG storage migration (Aliyun byte-identical to Hermes, 27654 ent / 39604 rel), aim-3 systemd timers cutover (Aliyun daily cron live), agentic-rag-v1 (41/41 REQs, 165 tests). **Future:** v1.1 (KB scale + throughput), agentic-rag-v2. See `README.md`.

## Commands

Always the venv interpreter, never system Python: `venv/Scripts/python.exe` (Windows local) / `venv/bin/python` (Hermes/Aliyun).

```bash
venv/Scripts/python.exe -m pytest tests/unit -v                    # fast unit tier (default local run)
venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v   # one file
venv/Scripts/python.exe -m pytest tests/unit -k "checkpoint" -v    # one test by keyword
venv/Scripts/python.exe -m pytest -m slow                          # opt-in slow tier
```

- Markers (`pyproject.toml`): `unit` (fast, mocked) · `integration`/`remote` (live deps — remote WSL host only, skip locally) · `slow`/`eval` (opt-in). `asyncio_mode=auto` — async tests need no decorator.
- No linter/formatter is configured — match surrounding style by hand.
- Local smoke/E2E: **always** `scripts/local_e2e.sh <mode>` (`kol` | `wechat <url>` | `layer1 N` | `layer2 N` | `cleanup`) — corp-network-aware env setup; raw script invocations bypass it.
- Skill validation (no Hermes needed): `python skill_runner.py skills/ --test-all`, or single: `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json`. Exit 0 = pass.
- KB local one-port deploy: `venv/Scripts/python.exe .scratch/local_serve.py` → `:8766` (see Principle #6).
- Databricks App deploy: `databricks-deploy/Makefile` (`make deploy | logs | smoke | stop`) — PowerShell only; full-pipeline vs sync-only rule in Principle #9.

## Architecture (big picture)

- **Ingestion pipeline** (`ingest_wechat.py`): URL → Apify (primary) / Edge CDP (prod fallback) / remote Playwright MCP (auto-selected by `/mcp` suffix on `CDP_URL`) → markdown + image download → Vision cascade descriptions (SiliconFlow → OpenRouter → Gemini, circuit-breakered) → entity extraction → LightRAG `ainsert()` → `~/.hermes/omonigraph-vault/lightrag_storage/`.
- **KOL/RSS batch pipeline** (3 stages over `data/kol_scan.db` SQLite): `batch_scan_kol.py` (scan → DB) → `batch_classify_kol.py` (Layer 1 + Layer 2 LLM topic filters) → `batch_ingest_from_spider.py --from-db` (checkpointed/resumable via `checkpoints/{hash}/` stage markers; never two batches per host).
- **Query/synthesis**: `kg_synthesize.py` (LightRAG hybrid retrieve + DeepSeek Markdown report) and `query_lightrag.py` (raw debug query).
- **`kb/`** — FastAPI + Jinja2 SSG knowledge-base site: FTS5 fast search + `?mode=kg` deep QA reusing `kg_synthesize`. Cross-module contracts listed in `kb/README.md`; breaking one requires `BREAKING: kb-contract-X` in the commit message.
- **`lib/`** — shared LLM/embedding clients: DeepSeek chat (prod LLM) + Vertex AI Gemini embeddings (SA JSON). Gotcha: `lib/__init__.py` eagerly imports DeepSeek → set `DEEPSEEK_API_KEY=dummy` even for Gemini-only runs. `lib/research/` = agentic-RAG lib (aliased to `omnigraph.research` after `pip install -e .`).
- **`skills/`** — Hermes agent skills (`omnigraph_ingest`, `omnigraph_query`) that call repo scripts; validated via `skill_runner.py`.
- **Prod topology**: Aliyun ECS (systemd-timer daily crons + Qdrant + kb-api) · Hermes PC (24/7 headed-browser/CDP provider with persistent WeChat login) · Databricks Apps (KB static snapshot) · this Windows machine (dev only).

## Operations

All runbook detail — env vars, ingestion/query architecture, common commands, dev conventions, CDP/MCP scraping paths, remote Hermes deployment, Vertex AI prod split, checkpoint mechanism, vision cascade, SiliconFlow balance, batch execution + MAX_ARTICLES tri-governor, known limitations, Hermes/Mac browser architecture, lessons — is in **`docs/OPERATIONS.md`**.

Quick pointers: local test/validation → always `scripts/local_e2e.sh` (corp-network-aware). Architecture → `docs/architecture.md`, `docs/tech-stack.md`, `docs/conventions.md`. Skill standards → `docs/skills/SKILL_STANDARDS.md`. Local-dev → `docs/LOCAL_DEV_SETUP.md`. E2E → `docs/e2e-testing.md`.

## Workflow

GSD tooling is removed (2026-08-09) — no `/gsd:*` commands. Orchestrate as plain plan → implement → verify with TodoWrite for tracking, sized per Principle #8. Existing `.planning/` GSD artifacts (PROJECT/ROADMAP/STATE/quick dirs) are inert history — read for context, don't extend, with one exception: `.planning/ISSUES.md` stays live per Principle #10.

**ISSUES.md integration:** before starting any task, grep `.planning/ISSUES.md` for related keywords (annotate `In flight: <slug>` when picking one up). At close-out, the orchestrator (NOT a subagent) transcribes newly surfaced out-of-scope issues into ISSUES.md + updates `Last updated:`. Move resolved rows (don't delete) with date+commit+slug; archive after 30d. Subagents read ISSUES.md but never edit it — they surface issues in close-out reports for the orchestrator to transcribe. (See Principle #10.)
