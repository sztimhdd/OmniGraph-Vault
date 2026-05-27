---
phase: 19
slug: generic-scraper-schema-kol-hotfix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-03
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `19-RESEARCH.md § Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + pytest-mock |
| **Config file** | none at repo root (pytest auto-discovers `tests/`) |
| **Quick run command** | `venv/Scripts/python -m pytest tests/unit/test_scraper.py tests/unit/test_batch_ingest_hash.py tests/unit/test_rss_schema_migration.py -x -q` |
| **Full suite command** | `venv/Scripts/python -m pytest tests/ -x` |
| **Estimated runtime** | ~10s quick / ~60s full |

---

## Sampling Rate

- **After every task commit:** Run quick command (< 10s)
- **After every plan wave:** Run full suite command (< 60s)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-00-01 | 00 | 0 | SCR-07 | smoke | `venv/Scripts/python -c "import trafilatura; print(trafilatura.__version__)"` → 2.0.0 | ❌ W0 | ⬜ pending |
| 19-00-02 | 00 | 0 | SCR-01..05 | scaffold | `ls tests/unit/test_scraper.py` | ❌ W0 | ⬜ pending |
| 19-00-03 | 00 | 0 | SCR-06, SCH-02 | scaffold | `ls tests/unit/test_batch_ingest_hash.py` | ❌ W0 | ⬜ pending |
| 19-00-04 | 00 | 0 | SCH-01 | scaffold | `ls tests/unit/test_rss_schema_migration.py` | ❌ W0 | ⬜ pending |
| 19-01-01 | 01 | 1 | SCR-01 | unit | `pytest tests/unit/test_scraper.py::test_import_and_dataclass_shape -x` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | SCR-03 | unit | `pytest tests/unit/test_scraper.py::test_route_dispatch -x` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | SCR-04 | unit | `pytest tests/unit/test_scraper.py::test_quality_gate -x` | ❌ W0 | ⬜ pending |
| 19-01-04 | 01 | 1 | SCR-05 | unit | `pytest tests/unit/test_scraper.py::test_backoff_429 -x` | ❌ W0 | ⬜ pending |
| 19-01-05 | 01 | 1 | SCR-02 | unit | `pytest tests/unit/test_scraper.py::test_cascade_layer_order -x` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 2 | SCR-06 | unit | `pytest tests/unit/test_batch_ingest_hash.py::test_classify_full_body_uses_scraper -x` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 2 | SCH-02 | unit | `pytest tests/unit/test_batch_ingest_hash.py::test_hash_is_sha256_16 -x` | ❌ W0 | ⬜ pending |
| 19-02-03 | 02 | 2 | SCH-01 | unit | `pytest tests/unit/test_rss_schema_migration.py::test_ensure_columns_idempotent -x` | ❌ W0 | ⬜ pending |
| 19-03-01 | 03 | 3 | regression | suite | `venv/Scripts/python -m pytest tests/ -x` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_scraper.py` — stubs for SCR-01, SCR-02, SCR-03, SCR-04, SCR-05 (RED, to go GREEN in Wave 1)
- [ ] `tests/unit/test_batch_ingest_hash.py` — stubs for SCR-06, SCH-02 (RED, to go GREEN in Wave 2)
- [ ] `tests/unit/test_rss_schema_migration.py` — stubs for SCH-01 (RED, to go GREEN in Wave 2)
- [ ] Framework install: `venv/Scripts/python -m pip install "trafilatura>=2.0.0,<3.0" "lxml>=4.9,<6"` (bootstraps SCR-07 local install verification — `<6` pinned per REQUIREMENTS.md SCR-07 authoritative spec for hotfix rollback safety)

*No new fixtures required — mock-only constraint per project policy (Cisco Umbrella blocks live HTTPS to scrape targets).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hermes pull + checkpoint reset | SCH-02 | Production migration op — requires SSH into Hermes (see `memory/hermes_ssh.md`) | After landing Phase 19 on main: SSH to Hermes → `cd ~/OmniGraph-Vault && git pull && python scripts/checkpoint_reset.py --all --confirm && source venv/bin/activate && python -m pytest tests/ -x` — confirm green + CLI dry-run `python batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2 --max-articles 1 --dry-run` parses without crash |
| Live WeChat fetch via KOL path | SCR-06 | Cisco Umbrella blocks real HTTPS from dev box; Hermes side can reach WeChat | On Hermes only: `python batch_ingest_from_spider.py --from-db --topic-filter AI --min-depth 2 --max-articles 1 --dry-run` — method logged should be `apify` or `cdp`, not `ua` |
| `pip install` fresh resolution | SCR-07 | Dependency resolution only meaningful against live PyPI | `venv/Scripts/python -m pip install -r requirements.txt --dry-run` — exit 0 expected |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (3 new test files + `pip install` step)
- [ ] No watch-mode flags (pytest -x exits on first failure; no `--watch`)
- [ ] Feedback latency < 10s (quick command)
- [ ] `nyquist_compliant: true` set in frontmatter after planner confirms task-IDs match

**Approval:** pending
