# Local E2E Testing (Cisco Umbrella corp network aware)

> ⚠️ **CRITICAL — local harness is NOT a full e2e validator.** Corp network blocks DeepSeek (`api.deepseek.com`) and SiliconFlow unconditionally. These providers are required by:
>
> - `enrichment/rss_classify.py` (writes `rss_articles.depth` — RSS pipeline's stage ④ hard gate; without it, stage ② skips immediately)
> - LightRAG entity extraction inside `rss_ingest.py:367` + `ingest_wechat.py` ainsert path (hardcoded `deepseek_model_complete`)
> - Layer 2 (`lib/article_filter.layer2_full_body_score`) — `deepseek-chat` per LF-2.3 contract
> - Vision cascade primary (SiliconFlow Qwen3-VL); cascade falls through to Gemini Vision (Vertex AI ✅)
>
> **Full happy-path validation only happens on Hermes** (production deploy + cron firing). The local harness is for: single-stage smoke (`layer1 N`, `wechat <url>`), dry-run dispatch verification, env validation, stuck-doc cleanup. **Do NOT plan local tasks that traverse stages ② → ⑥** — they will block at stage ④ (depth gate) or stage ⑥ (LightRAG entity extraction). 2026-05-08 RSS smoke ran 1/5 stages real (Apify scrape only); the other 4 were either gate-skipped or structurally unreachable. See `.scratch/rss-e2e-local-20260508-151955.md` for the audit.

**`scripts/local_e2e.sh`** — single-entry harness for local end-to-end testing.
Auto-configures all corp-network env vars (TLS CA bundle, Vertex SA, `OMNIGRAPH_BASE_DIR`, scrape cascade) and dispatches to the target script via a mode arg. **Use this for any local smoke / e2e / spike — do NOT manually export env vars.**

```bash
./scripts/local_e2e.sh help                           # show all modes
./scripts/local_e2e.sh rss --max-articles 1           # RSS 1-article e2e
./scripts/local_e2e.sh rss --dry-run                  # RSS dry-run (no scrape, no LLM)
./scripts/local_e2e.sh kol --max-articles 1 --dry-run # KOL dry-run
./scripts/local_e2e.sh wechat <url>                   # single WeChat URL
./scripts/local_e2e.sh layer1 5                       # Layer 1 smoke on 5 candidates
./scripts/local_e2e.sh layer2 5                       # Layer 2 smoke on 5 layer1=candidate articles
./scripts/local_e2e.sh cleanup                        # stuck-doc dry-run
```

Output goes to `.scratch/local-e2e-<mode>-<ts>.log` (gitignored). Existing env vars are honored via `${VAR:-default}` — set them in your shell to override any default.

Known limitations (corp network reachability — verified 2026-05-08):

| Provider | Status | Affects |
|---|---|---|
| Vertex AI Gemini (embedding + LLM) | ✅ Reachable | Layer 1 (`lib/article_filter.py`), Vertex LLM smoke via `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` |
| DeepSeek API (`api.deepseek.com`) | ❌ Blocked by corp | Layer 2, LightRAG entity extraction, legacy `enrichment/rss_classify.py` + `enrichment/rss_ingest.py` |
| SiliconFlow (Qwen3-VL primary) | ❌ Blocked by corp | Vision cascade primary; cascade falls to Gemini Vision (Vertex AI) |
| OpenRouter (Vision fallback) | ❓ Untested locally | Vision cascade secondary |
| Apify | ✅ Reachable (with valid token) | Scrape cascade tier 2 |
| UA scrape | ✅ Reachable | Scrape cascade tier 1 |

**Implication**: full v3.5 e2e (Layer 1 → scrape → Layer 2 → ainsert → vision) is **NOT possible 100% locally** as of 2026-05-08 — each stage has a different reachability profile. Use individual mode runs (`layer1 N`, `wechat <url>`) for stages that work, and rely on Hermes deploy for stages that need DeepSeek / SiliconFlow.

**Legacy script note**: `enrichment/rss_classify.py:129` and `enrichment/rss_ingest.py:367` both hardcode DeepSeek and bypass the `lib/llm_complete.py` dispatcher — `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` has no effect on either. They will be retired in ir-4 (see `docs/research/rss-flow-as-of-260508.md`); post-ir-4, RSS will route through `batch_ingest_from_spider.py` + `lib/article_filter.py`. Layer 2 will still need DeepSeek (corp-blocked → Hermes-only), so RSS local e2e parity with KOL is bottlenecked on DeepSeek reachability regardless of ir-4. Realistic local-test scope: Layer 1 (Vertex), scrape (UA + Apify), individual stage smokes.

**Stage-02 gate**: `.dev-runtime/data/kol_scan.db` rows with `rss_articles.depth IS NULL` will skip stage 02 in `enrichment/rss_ingest.py` regardless of body presence (legacy gate at `enrichment/rss_ingest.py:228-230`). To exercise stages 03+ locally, manually set `depth >= 2` on a fixture row, or run `enrichment/rss_classify.py` first (will fail without DeepSeek reachability).

`DEEPSEEK_API_KEY=dummy` is the import-time defense against the Phase 5 cross-coupling bug at `lib/__init__.py:35` — prevents module import from failing. Any real DeepSeek call still fails, as expected.

**For new local tests:** read `scripts/local_e2e.sh help` first. If an existing mode covers the target script, use it; if not, add a new `case)` branch — do not reinvent env setup.
