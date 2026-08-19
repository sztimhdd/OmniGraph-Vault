# OmniGraph-Vault — Operations Reference

> Loaded on demand. The project CLAUDE.md carries only invariants + entry points; runbook detail lives here.

## Runtime data & env

- **Runtime dir:** `~/.hermes/omonigraph-vault/` — the typo (`omonigraph` not `omnigraph`) is baked into `config.py` and every deployed env. Do NOT "fix" it without a coordinated migration.
- **config.py** loads `~/.hermes/.env` at import; does NOT overwrite existing env vars. Exposes `BASE_DIR`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `CDP_URL`.

| Var | Req | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | LLM/vision/embedding |
| `APIFY_TOKEN` | No | Primary scraping (falls back to CDP) |
| `FIRECRAWL_API_KEY` | No | Firecrawl scraping |
| `CDP_URL` | No | Local Edge `localhost:9222` (`connect_over_cdp`) OR remote `host:port/mcp` (`_MCPClient`, auto-detected by `/mcp` suffix) |
| `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` | No | RSS classifier cap (default 500; CLI `--max-articles` always wins; non-int → 500) |

**Scoped:** `OMNIGRAPH_GEMINI_KEY` (canonical, `GEMINI_API_KEY` fallback), `OMNIGRAPH_GEMINI_KEYS` (comma, multi-account rotation) — Gemini keys now only serve the vision-cascade fallback leg. Models hard-coded in `lib/models.py` (embedding = `bge-m3`, 1024-dim, local). Per-model RPM via `OMNIGRAPH_RPM_*`. Full deploy table in `Deploy.md`.

**DeepSeek cross-coupling:** `lib/__init__.py` eagerly imports `deepseek_model_complete` → raises at import if `DEEPSEEK_API_KEY` unset. Gemini-only workloads still need `DEEPSEEK_API_KEY=dummy`.

**Local-dev vars** (opt-in, run against `.dev-runtime/`; unset preserves prod): `OMNIGRAPH_LLM_PROVIDER` (`deepseek` prod / `vertex_gemini` sandbox), `OMNIGRAPH_LLM_MODEL`, `OMNIGRAPH_VISION_SKIP_PROVIDERS` (comma-list, e.g. `siliconflow,openrouter`), `OMNIGRAPH_BASE_DIR` (abs path), `OMNIGRAPH_LLM_TIMEOUT_SEC` (600), `OMNIGRAPH_PROCESSED_RETRY` (30), `OMNIGRAPH_PROCESSED_BACKOFF` (2.0), `OMNIGRAPH_DEEPSEEK_TIMEOUT` (300). Runbook: `docs/LOCAL_DEV_SETUP.md`.

## Architecture

**Ingestion:** URL → `ingest_wechat.py` → Apify(primary)/CDP(fallback) → HTML → BeautifulSoup+html2text → Markdown → image download to `images/{hash}/` → Gemini Vision descriptions → Gemini Flash entity extraction to `entity_buffer/{hash}_entities.json` → LightRAG `ainsert()` → `lightrag_storage/`. (Cognee canonicalization retired 2026-05-10, quick 260510-gfg.)

**Query/synthesis:** Query → `kg_synthesize.py` → load `canonical_map.json` normalize → LightRAG `aquery(mode=hybrid)` → past-query memory (HYG-03 JSONL) → Gemini Markdown report → stdout + `synthesis_output.md`.

**LightRAG** used in `ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`, `query_lightrag.py` with Gemini wrappers. See `docs/architecture.md`, `docs/tech-stack.md`, `docs/conventions.md`.

## Common commands

For local test/validation/smoke, ALWAYS use `scripts/local_e2e.sh` (corp-network-aware; DeepSeek+SiliconFlow blocked, Cisco Umbrella TLS). Modes: `rss`/`kol`/`wechat <url>`/`layer1 N`/`layer2 N`/`cleanup`/`help`. Raw commands below are reference-only.
```bash
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."     # WeChat article
python multimodal_ingest.py "/path/to/document.pdf"          # PDF + images
python kg_synthesize.py "query" hybrid                        # synthesis (naive/local/global/hybrid/mix)
python query_lightrag.py "query"                              # direct debug query
python list_entities.py                                       # list graph entities
cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &   # image server
```

## Development conventions

- Atomic writes for `canonical_map.json` (`.tmp` then rename).
- LLM output never goes straight into the graph — validate against real sources first.
- Entity buffer idempotency — write `.processed` marker after each batch; never delete originals.
- Image server (port 8765) must run for synthesized reports to render.
- Skill writing standards: `docs/skills/SKILL_STANDARDS.md`.

## Testing the CDP / MCP scraping paths

Three paths (manual exercise):
1. **Apify (primary):** set `APIFY_TOKEN`, run `ingest_wechat.py <url>` → look for `method: apify`.
2. **Local Edge CDP (prod fallback):** `Start-Process msedge.exe -ArgumentList "--remote-debugging-port=9222 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9222"`; `CDP_URL=http://localhost:9222`; unset `APIFY_TOKEN` → `Falling back to local CDP...` `method: cdp`.
3. **Remote Playwright MCP (testing fallback):** `CDP_URL=http://ohca.ddns.net:58931/mcp` (the `/mcp` suffix triggers `_MCPClient`); unset `APIFY_TOKEN` → `method: mcp`. MCP requires `initialize` first, then `mcp-session-id` header on every call (else "Server not initialized").

**Skill simulator (no Hermes):** `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` (and `_query`). Exit 0 = pass. Needs only `GEMINI_API_KEY`.

## Remote Hermes deployment (real E2E)

Prod Hermes runs on a remote PC (WSL2). Only place for full skill→script→LightRAG→Gemini against deployed state. SSH details in project memory `hermes_ssh.md` (auto-loaded; never commit). Reconcile git before any remote test: `ssh -p <port> <user>@<host> "cd ~/OmniGraph-Vault && git status -sb && git log --oneline -5"`; if remote ahead, push from remote/pull locally/re-read. Remote paths: code `~/OmniGraph-Vault` (venv `venv/bin/`), runtime `~/.hermes/omonigraph-vault/`, env `~/.hermes/.env`, gateway `~/.hermes/gateway.pid` + `state.db`.

## Embedding: local BGE-M3 (production since the BGE-M3 migration; Vertex retired 2026-08-19)

Prod split: **LLM** DeepSeek chat (primary; required even on other paths due to eager import) · **Embedding** local BGE-M3 (`BAAI/bge-m3`, 1024-dim) served by `embed-server.service` on the Aliyun ingest box (`:7997`, Infinity); consumers set `OMNIGRAPH_LOCAL_EMBED=1` (+ `OMNIGRAPH_LOCAL_EMBED_URL`/`_TOKEN` for remote callers — the Databricks App reaches it via the bearer-gated Caddy route `/omnigraph/embed` on `:80`; TLS upgrade pending a security-group change for `:443`) · **Vision** SiliconFlow Qwen3-VL-32B → OpenRouter → Gemini cascade (¥0.0013/img — the Gemini vision leg is the last remaining Google call in the pipeline). Vertex AI Gemini embedding (`gemini-embedding-2`, 3072-dim, SA JSON) is fully retired: no `GOOGLE_*` env in `databricks-deploy/app.yaml`, `google-genai` is an optional lazy import in `lib/`, and the historical spec is frozen at `docs/VERTEX_AI_MIGRATION_SPEC.md`. The `aliyun_oauth_pin` `/etc/hosts` entries only matter for the Gemini vision leg now.

## Checkpoint mechanism

Per-article checkpoint dir makes long batches resumable. Stages write markers into `checkpoints/{hash}/`: `01_scrape` → `02_filter` → `03_manifest` → `04_vision` → `05_ingest` + `metadata.json`. On restart, skip stages with existing markers, resume at first missing. Writes atomic (`.tmp` + `os.rename`). Commands: `scripts/checkpoint_status.py` (list in-flight), `scripts/checkpoint_reset.py --hash {h}` (force re-ingest one), `batch_ingest_from_spider.py --reset-checkpoint` (wipe all). **Pitfall:** removing `checkpoints/` mid-batch corrupts in-flight `metadata.json` — stop the batch first.

## Vision cascade

Three-provider failover + per-provider circuit breaker so one 503/429 never kills an article. Order (hard-coded): SiliconFlow Qwen3-VL-32B (¥0.0013/img) → OpenRouter (free) → Gemini (500 RPD ceiling). Circuit opens after 3 consecutive same-provider failures (skipped until recovery); 429 cascades immediately; 4xx auth does NOT count (needs operator action). Pre-batch balance alert to stderr if SiliconFlow balance < ¥0.0013×expected_images. `batch_validation_report.json` records `provider_usage`; healthy = Gemini <10%.

## SiliconFlow balance

Paid, hard cap. Depletion doesn't hang (cascades to OpenRouter+Gemini) but shifts to 500-RPD Gemini free tier → can exhaust in one batch. Rule: ¥1.00 ≈ 770 images; 263-article batch (~2630 imgs) → budget ≥¥10. Monitor: `watch -n 30 'python scripts/checkpoint_status.py | tail -20'`; if Vision flips to Gemini for many consecutive images, check balance. Top-up mid-batch is safe: Ctrl+C (checkpoints atomic), top up, resume same command (no `--reset-checkpoint`).

## Batch execution

```bash
python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint   # from scratch
python batch_ingest_from_spider.py --topics ai --depth 2                       # resume (default)
watch -n 5 'python scripts/checkpoint_status.py | tail -20'
```
Resume for interrupted/transient/top-up; `--reset-checkpoint` after fixture/ingestion-logic change or clean regression baseline. Never run two batches concurrently per host (checkpoint writes atomic per-article, not cross-process).

**MAX_ARTICLES is a tri-governor** (default 5 via `cron_daily_ingest.sh 5`): (1) throughput cap; (2) SiliconFlow ¥-budget (~¥0.04/article → 5 ≈ ¥0.20/cron, 50 ≈ ¥2.00); (3) embed-server throughput (entity-rich articles = 100-300 embed calls each; local BGE-M3 has no 429 quota but saturates CPU). Bumping without checking all three regresses cost/throughput.

## Known limitations

- Gemini 500 RPD (free tier) — Vision cascade's last resort; a big batch falling through can exhaust it for the day.
- WeChat throttle — `ingest_wechat.py` enforces 50 articles/batch + cooldown (WeChat-side, not configurable). Slice large batches.

## Hermes PC + Mac Chrome browser architecture (deployed 2026-07-14)

Hermes PC (`ohca.ddns.net`, 24/7) is primary headed-browser provider for Aliyun's prod OmniGraph. Mac Chrome is graceful fallback-only (may be offline; no auto-start; no SSH tunnel — privacy). Topology: Hermes Edge `--remote-debugging-port=9222` (user-data-dir `~/.hermes/edge-cdp-profile`, persistent WeChat MP login) + Playwright MCP `--cdp-endpoint :9222 --port 58931`. Aliyun `kol-refresh.timer` (24h proactive) runs `scripts/refresh_wechat_cookie.py` fallback chain: Hermes Edge CDP → Mac Chrome → fail + Telegram alert. Cookie flow: proactive timer 5 min pre-scan extracts fresh token + 5 cookies, atomic writeback to Aliyun `kol_config.py`, single-account verify (ret=0 gate), Telegram on success/failure; reactive on daily-scan ret=200003 (session expired) via `omnigraph-daily-ingest.service` OnFailure → `kol-scan-alert.service` retry + Telegram if QR needed. Env (Aliyun `/root/.hermes/.env`): `HERMES_CDP_URL=http://localhost:9222`. systemd: `deploy/aliyun/systemd/omnigraph-kol-refresh.{service,timer}`. Removed 2026-07-14: Mac SSH reverse tunnel, `omnigraph-mcp-tunnel.service`.

## Lessons learned

Evergreen invariants only — dated postmortems archived in `docs/lessons/` and surfaced in project memory `MEMORY.md` when load-bearing. Recent: `docs/lessons/2026-05-archive.md` (9 postmortems). Behavior-anchor harness discipline for `ingest_from_db` is in the project CLAUDE.md.
