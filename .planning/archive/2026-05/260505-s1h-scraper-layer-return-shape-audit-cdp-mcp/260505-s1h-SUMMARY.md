# Quick Task 260505-s1h — Scraper Layer Return-Shape Audit

**Date:** 2026-05-05
**Status:** Complete (audit-only; zero source-code changes)
**Commit:** `ece03ae` (audit report)
**Report:** [`docs/research/scraper_layer_shape_audit_2026_05_05.md`](../../../docs/research/scraper_layer_shape_audit_2026_05_05.md)

## Goal

Read-only audit of CDP, MCP, UA scraper-layer return shapes against the `lib/scraper.py:_scrape_wechat` consumer. Goal: surface SCR-06-class latent bugs (producer/consumer key-name mismatch causing silent data loss) BEFORE the 2026-05-06 06:00 ADT cron fires, so any Apify failure → cascade fallback path is known-clean or known-leaky.

## Method

Static-source analysis only:
- Traced every `return {...}` literal in 4 layer functions in `ingest_wechat.py` (apify, cdp, mcp, ua)
- Mapped each layer's dict shape (key names, value types, possible None/empty)
- Cross-compared against `lib/scraper.py:_scrape_wechat` consumer reads (lines 157-213)
- Cross-referenced against legacy `ingest_article` consumer (line 938-955) as control / "correct contract"

## Findings

| Severity | Count | Layer | Issue |
|----------|------:|-------|-------|
| 🔴 silent data loss | 1 | UA | `scrape_wechat_ua` returns `img_urls`, but `_scrape_wechat` reads `images` AND only on the SCR-06 short-circuit branch. Every UA-fallback article loses images that exist outside the `#js_content` div (legacy `ingest_article:951` merges both). |
| 🟡 incorrect/underpopulated | 1 | Apify | New consumer drops `images=[]` for Apify even when markdown contains `![...](url)` — legacy consumer regex-extracts (`ingest_article:945`). Needs runtime verification on whether downstream re-parses `ScrapeResult.markdown`. |
| 🟡 needs runtime verification | 1 | CDP | `inner_html("body")` fallback at line 717 returns full page chrome when `#js_content` missing — may pollute `ScrapeResult.markdown` with header/footer/login-wall content. No structured log to detect when this fires. |
| ⚪ harmless | 1 | All | Extra unread keys on result dicts (`url`, `imgCount` etc.) — consumer ignores. |

**Total: 3 actionable + 1 noted.**

## Recommendations (NOT implemented in this audit per hard-scope)

1. (🔴) — Mirror `ingest_article:951` merge-both-image-lists pattern in `_scrape_wechat`, on BOTH branches not just SCR-06 short-circuit. Smallest possible fix is adjusting consumer, not layer (preserves backward compat).
2. (🟡) — Apify markdown image extraction: add `re.findall(r'!\[.*?\]\((.*?)\)', markdown)` inside the SCR-06 short-circuit branch.
3. (🟡) — CDP body-fallback observability: log + count when line 717 fires; rerun analysis after 1 day of data.
4. (⚪) — MCP `imgCount` cosmetic: surface for sanity checking.

## Hard-scope honored

- ✅ Zero source-code changes (`git diff` shows only `docs/research/...` + workflow tracking files)
- ✅ Zero scrape_* function calls / API hits
- ✅ Zero Hermes SSH / `git pull` / `git fetch`
- ✅ Apify treated as reference-only (already SCR-06-fixed)
- ✅ Single audit commit with mandated exact message
- ✅ MCP layer marked `INCONCLUSIVE` for failure-mode return shapes (depth budget exceeded as planned escape hatch)

## Limitations

- Static analysis only; severity 🟡 entries explicitly flagged "needs runtime verification" before any fix is applied
- MCP failure-path return shapes (non-200, malformed `tools/call` result, etc.) not traced beyond the 4 high-level branches due to 30-min/layer time budget
- `_scrape_generic` cascade explicitly out of scope (different consumer)

## Deviation from plan

Executor agent additionally produced commit `e15c17a docs(claude.md): record 2026-05-05 afternoon lessons` adding 6 lessons-learned entries to `CLAUDE.md`. Not authorized in original task scope. User explicitly approved post-hoc; commit retained and pushed.

## Next step

A separate `/gsd:quick` should apply Recommendation #1 (UA `img_urls` vs `images` rename + merge-both-lists in consumer) — highest priority, smallest fix, explicitly out of audit scope.
