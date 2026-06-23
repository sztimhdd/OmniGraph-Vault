# 260623-g6e Follow-up: Apify vs UA scrape — stable failure or flaky?

**Investigated:** 2026-06-24 ~03:00 CST (post-restore diagnostic, user question)

## Question
Is Apify a **stable** failure or **occasional** flake? What about UA scrape?

## Method
- Aggregated scrape-outcome log lines across journald (only retains 06-21→now, 3.9G rotated).
- Harvested **all 65 `batch_timeout_metrics_*.json`** on disk (2026-05-04 → 2026-06-23) — these persist beyond journald and record `completed_articles` per run.
- Read scrape dispatch order in `ingest_wechat.py`.

## Scrape chain (order, from `ingest_wechat.py` ~line 1274-1300)
1. **UA scrape** (`scrape_wechat_ua`, primary) — plain `requests.get` with a `MicroMessenger` User-Agent, parses `id="js_content"` / `id="img-content"` div. Cheap, no Apify cost.
2. **Apify** (`scrape_wechat_apify`, secondary) — only if UA returns None. Detects WeChat verification/login page (short body + block keywords) → triggers fallback.
3. **CDP / MCP** (last resort) — `localhost:9223` on Aliyun (NOT present — that path is for Hermes). On Aliyun this always ECONNREFUSEDs, so steps 1-2 are effectively the whole chain.

## KEY FINDING: this is the **long-standing baseline**, NOT a new failure or the docker outage

`completed_articles` per run, every run on disk (total 65 runs, 150 articles ingested all-time):

| Window | done/run pattern | Note |
|---|---|---|
| 05-10 → 05-29 (good days) | 3–10 done/run | peak: 06-26 = 10/215, 05-26 = 10/144 |
| 05-30 → 06-13 (typical) | 1–7 done/run | avg ~2-3 done out of ~200 candidates/run |
| **06-14 → 06-16** | **0 done, elapsed 72-202s** | runs exit near-instantly — **scrape produced nothing**; these are the run-fast-fail pattern right before the docker outage |
| 06-17 → 06-22 | **(no metrics files)** | the 7-day docker/Qdrant outage — runs crashed at ainsert |
| **06-23 23:29 (post-restore)** | **4/197 done, elapsed 1352s** | back to the NORMAL baseline — real scrape work, 4 landed |

**The scrape success rate has ALWAYS been low** — typically only **1-10 articles land per run out of ~150-250 candidates** (~1-5%). This is not a regression from the docker fix; it's the steady-state behavior of the WeChat-scrape layer going back to early May. The docker outage (06-17→22) was a *separate, total* failure (0 ingest, ainsert ConnectRefused) layered on top.

## Per-run scrape breakdown (06-23 post-restore run, n=5 candidates attempted)
- 10 Apify actor starts, **2 scrape successes** (`method: apify` + `method: resumed`)
- 3 "Apify returned verification/login page", 3 "Scraping failed (both)", 10 "UA scrape: article body not found"

## ANSWER

**Neither "stable dead" nor pure "flaky" — both layers are partially-working with a structurally low hit rate:**

- **UA scrape (primary):** **predominantly fails** on WeChat — `article body not found in HTML` dominates (10 occurrences last run). WeChat increasingly serves JS-rendered / anti-bot pages where the `js_content` div isn't in the raw HTML. UA succeeds only on a minority of articles (the simpler/older ones). This is a *stable structural limitation*, not flaky — WeChat's anti-scrape has been tightening for weeks.
- **Apify (secondary):** **flaky / partial** — sometimes returns the real article, sometimes a verification/login page (3/10 last run). When Apify hits the verification page, there's no working fallback on Aliyun (CDP=9223 absent), so that article is dropped. The verification-page rate is the WeChat-anti-crawl variable; it fluctuates.
- **Net effect:** the two combined land ~1-5% of candidates per run. The backlog drains slowly because most candidates need multiple cron attempts before a scrape attempt happens to succeed (Apify not serving a verification page that moment + UA finding the div).

**This is by-design tolerated** (checkpoint resume + cron retry means a dropped article is re-attempted next run), but it explains the slow backlog drain (191 ok-verdict articles not yet ingested). It is NOT caused by the docker fix and NOT a cookie problem.

## Real levers (if throughput matters — out of scope for this quick)
1. **Apify verification-page rate** is the dominant loss — investigate Apify actor config / whether a different actor or `proxy` setting reduces verification pages. (ISSUES candidate)
2. **CDP fallback is dead on Aliyun** (9223 absent) — the #2→#3 fallback never fires there. Either wire a real headless browser on Aliyun or accept Apify-only.
3. **UA scrape structural** — WeChat JS-rendering means UA-only will keep mostly failing; it's a free first-try, low cost to keep, but not improvable without a JS renderer.
4. Cross-ref ISSUES #36 (per-article wall), #40 (concurrency) — throughput-class issues.

## NOT a fault to fix in this quick
The docker+Qdrant restore goal is fully met. Scrape-layer hit rate is a separate, pre-existing throughput characteristic. Filed as a throughput observation, not a regression.

---

## RESOLUTION 2026-06-24 03:20 CST — CDP/MCP fallback WIRED + LIVE-VERIFIED

User requested the CDP/MCP fallback be added (the #2→#3 cascade step that was dead on Aliyun because `CDP_URL=http://localhost:9223` had no browser behind it).

### Topology discovered
- Hermes runs a **live Playwright MCP HTTP server on `localhost:8931`** (Playwright 1.61.0; `initialize` handshake over `/mcp`+`/sse` succeeds). The `--headless` stdio procs were a red herring; `:8931` is the real HTTP/SSE server.
- Hermes `:9222` CDP Edge (cookie-refresh browser) is alive but localhost-bound.
- Public port `ohca.ddns.net:58931` accepts TCP but **resets on HTTP** — stale router forward, nothing serving behind it. So no direct public path.
- **Aliyun already has passwordless `ssh hermes`** (alias in `~/.ssh/config`, set up by the kol-cookie-autorefresh phase) and `:49221` is reachable.

### Solution: SSH reverse-forward tunnel (no router/Windows change, no user action)
`omnigraph-mcp-tunnel.service` (systemd, Aliyun) holds an `ssh -N -L 127.0.0.1:8931:localhost:8931 hermes` tunnel open 24/7:
- `Restart=always`, `RestartSec=10`, `ServerAliveInterval=30`/`CountMax=3` keepalive, `ExitOnForwardFailure=yes`.
- Aliyun `CDP_URL` set to `http://localhost:8931/mcp` (backup: `/root/.hermes/.env.bak-pre-mcp-tunnel-260624`). The `/mcp` suffix routes `ingest_wechat.py` to `_MCPClient`/`scrape_wechat_mcp` (MCP-over-SSE), per the documented dual-mode.

### Verification (live, Principle #6)
1. **MCP handshake through tunnel:** `initialize` → Playwright 1.61.0 serverInfo. ✅
2. **Real scrape through tunnel:** ran `scrape_wechat_mcp` directly on a backlog WeChat URL (id=2973) → **`method=mcp`, 28327 chars content, 6 images**. ✅ (proves the fallback actually pulls article bodies, not just handshakes)
3. **Cron-path wiring:** fired `omnigraph-daily-ingest` with the new `CDP_URL` via EnvironmentFile; ran clean, chunks +1, no errors. ✅
4. **Durability:** `kill -9` the tunnel pid → systemd auto-restarted it in ~13s (new pid), handshake works again. ✅ With Hermes 24/7, the fallback is robust.

### Cascade now (Aliyun)
1. UA scrape (mostly fails — WeChat JS-render) →
2. Apify (flaky; verification-page ~30%) →
3. **MCP via tunnel → Hermes Playwright (NOW LIVE)** — the previously-dead fallback. When Apify returns a verification page, the article now routes to Hermes's logged-in browser instead of being dropped.

### Caveat / dependency
The fallback depends on: Hermes online + `:8931` MCP server running + Aliyun→Hermes SSH. User committed to 24/7 Hermes + MCP. If the MCP server on Hermes ever stops, articles needing fallback will hang to timeout then drop (UA/Apify still try first). A future hardening is a **local headless Playwright on Aliyun** (self-contained, no Hermes dependency) — larger work, filed as a follow-up consideration, not done here.

### Artifacts
- `deploy/aliyun/systemd/omnigraph-mcp-tunnel.service` (version-controlled copy of the deployed unit)
- Deployed + enabled on Aliyun; `CDP_URL` flipped with backup.
