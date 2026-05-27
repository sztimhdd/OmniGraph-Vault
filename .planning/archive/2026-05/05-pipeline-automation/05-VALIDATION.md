---
phase: 5
slug: pipeline-automation
status: final
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-28
closed: 2026-05-06
closure_doc: 05-CLOSURE.md
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Manual verification scripts (project pattern) — `tests/verify_*.py` |
| **Config file** | None (no pytest.ini yet) — Wave 0 may install pytest if executor chooses |
| **Quick run command** | `ssh remote "cd ~/OmniGraph-Vault && venv/bin/python tests/verify_<gate>.py"` |
| **Full suite command** | `ssh remote "cd ~/OmniGraph-Vault && for f in tests/verify_*.py; do venv/bin/python \"$f\" || exit 1; done"` |
| **Estimated runtime** | ~60 seconds (Wave 0 benchmark is the slowest; others <10s) |

---

## Sampling Rate

- **After every task commit:** Run the task's associated `verify_*.py` script
- **After every plan wave:** Run full suite command (all `verify_*.py`)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (benchmark is the long pole; everything else <10s)

---

## Per-Task Verification Map

> Planner fills this during task breakdown. Each task gets one row.

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-00-XX | 00 | 0 | D-01 consolidation | unit | `grep -c "from lightrag_embedding import embedding_func" ingest_wechat.py` (expect 1) | ❌ W0 | ⬜ pending |  <!-- M-19 fix: module name is lightrag_embedding, not config.embedding -->
| 5-00-XX | 00 | 0 | D-04 multimodal in-band | smoke | `venv/bin/python scripts/wave0_reembed.py --dry-run --one-doc` | ❌ W0 | ⬜ pending |
| 5-00-XX | 00 | 0 | Wave 0 benchmark | benchmark | `venv/bin/python tests/verify_wave0_benchmark.py` | ❌ W0 | ⬜ pending |
| 5-00-XX | 00 | 0 | Wave 0 cross-modal | smoke | `venv/bin/python tests/verify_wave0_crossmodal.py` | ❌ W0 | ⬜ pending |
| 5-00b-XX | 00b | 0 | D-10 filter correctness | SQL | `sqlite3 data/kol_scan.db "SELECT ..."` | ❌ W0 | ⬜ pending |
| 5-01-XX | 01 | 1 | OPML parse ≥ 90 | unit | `venv/bin/python tests/verify_rss_opml.py` | ❌ W0 | ⬜ pending |
| 5-02-XX | 02 | 1 | RSS fetch no crash | smoke | `venv/bin/python enrichment/rss_fetch.py --max-feeds 5 --dry-run` | ✅ | ⬜ pending |
| 5-03-XX | 03 | 1 | RSS classify | unit | `venv/bin/python enrichment/rss_classify.py --article-id 1 --dry-run` | ✅ | ⬜ pending |
| 5-03b-XX | 03b | 1 | RSS ingest (D-09 translate) | unit | `venv/bin/python enrichment/rss_ingest.py --dry-run` + `pytest tests/unit/test_rss_ingest.py tests/unit/test_run_enrich_for_id.py` | ✅ | ⬜ pending |  <!-- Added by revision: closes BLOCKER 1/2/3 -->
| 5-04-XX | 04 | 2 | Orchestrator dry-run | smoke | `venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan` | ✅ | ⬜ pending |
| 5-05-XX | 05 | 2 | Digest Markdown | unit | `venv/bin/python enrichment/daily_digest.py --date <date> --dry-run` | ✅ | ⬜ pending |
| 5-06-XX | 06 | 3 | Cron registered | manual | `hermes cronjob list \| grep -E "rss\|kol\|digest"` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/verify_wave0_benchmark.py` — golden-query benchmark; 5-10 queries, top-5 overlap ≥ 60%
- [ ] `tests/verify_wave0_crossmodal.py` — text query "某架构图" → top-5 must include ≥1 chunk with image URL reference
- [ ] `tests/verify_rss_opml.py` — OPML parse ≥ 90 feeds assertion
- [ ] `scripts/wave0_reembed.py` — re-embed 18 docs via delete-by-id + re-ainsert; supports `--dry-run` and `--one-doc`
- [ ] `scripts/wave0b_classify_and_ingest.py` (or extend `batch_classify_kol.py` + `batch_ingest_from_spider.py`) — classify all 302, filter by keyword+depth, submit batch

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cron jobs fire on schedule | D-16 Hermes drives | Time-based; cannot simulate without 24h observation | Check `hermes cronjob list` shows all jobs enabled; observe Telegram digest arrives ≥ 2 of 3 consecutive days |
| Telegram digest renders correctly on mobile | D-18 delivery | Visual formatting on Telegram client | Trigger `daily_digest.py` manually; inspect Markdown rendering in Telegram app |
| Zhihu login QR recovery path (reused from Phase 4 D-13) | D-18 | Requires user mobile interaction | Reuse Phase 4 validation; no new manual gate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (benchmark, cross-modal, OPML, re-embed script)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter (M-18: flipped to true by 05-06 Task 6.3 post-observation wrap-up)

**Approval:** pending
