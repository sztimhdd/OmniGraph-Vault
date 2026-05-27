---
phase: 04
slug: knowledge-enrichment-zhihu
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-27
updated: 2026-04-27
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from RESEARCH.md §10 "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (per `~/.claude/rules/python/testing.md`) |
| **Config file** | `pyproject.toml` + `tests/conftest.py` — **Wave 0 creates** |
| **Quick run command** | `pytest tests/unit -x --ff -q` (runs unit tier only; <10s) |
| **Full suite command** | `ssh remote 'cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/ -v'` |
| **Estimated runtime** | Unit ~5–10s local+remote; Integration ~2–5 min remote only; E2E ~10 min remote only |

**Platform split** (per D-04/D-06 remote-only constraint):

- **Unit tier** (local-runnable): Pure-Python helpers. Gemini / Telegram / CDP / LightRAG all mocked via fixtures. Runs on Windows dev box.
- **Integration tier** (remote-only): Hermes skill invocation flow, CDP + Zhihu, LightRAG delete+re-insert, Telegram delivery, golden-file regression diff.
- **E2E tier** (remote-only): Full `enrich_article` skill run against one real WeChat article; assert enriched MD + 3 Zhihu docs land in LightRAG with correct metadata.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit -x --ff -q` locally on Windows (fast feedback)
- **After every plan wave:** Run full unit tier locally + relevant integration tier on remote (`ssh remote pytest tests/integration/<wave_N>`)
- **Before `/gsd:verify-work`:** Full suite green on remote + Phase-0 spike outputs archived
- **Max feedback latency:** <10s for unit tier, <5 min for integration tier

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-00 / Task 0.1 | 00 | 0 | pytest scaffold | unit | `pytest --collect-only -q` | ❌ W0 | ⬜ pending |
| 04-00 / Task 0.2 | 00 | 0 | SQLite migration (drift + new cols) | unit | `pytest tests/unit/test_migrations.py -x` | ❌ W0 | ⬜ pending |
| 04-00 / Task 0.3 | 00 | 0 | D-14 LightRAG spike script | integration+manual | `ssh remote 'python scripts/phase0_delete_spike.py'` → produces `phase0_spike_report.md` with `status: success` | ❌ W0 | ⬜ pending |
| 04-00 / Task 0.4 | 00 | 0 | deploy.sh helper | unit | `bash -n deploy.sh` | ❌ W0 | ⬜ pending |
| 04-00 / Task 0.5 | 00 | 0 | Golden-file fixtures captured | manual | `find tests/fixtures/golden -name final_content.md \| wc -l` >= 2 | n/a | ⬜ pending |
| 04-01 / Task 1.1 | 01 | 1 | image_pipeline 4 functions | unit | `pytest tests/unit/test_image_pipeline.py -x` | ❌ W0 | ⬜ pending |
| 04-01 / Task 1.2 | 01 | 1 | ingest_wechat uses image_pipeline | unit | `grep -q "from image_pipeline import" ingest_wechat.py && python -c "import ast; ast.parse(open('ingest_wechat.py').read())"` | ❌ W0 | ⬜ pending |
| 04-01 / Task 1.3 | 01 | 1 | Golden-file regression | integration | `ssh remote 'pytest tests/integration/test_image_pipeline_golden.py -v'` | ❌ W0 | ⬜ pending |
| 04-02 / Task 2.1 | 02 | 2 | extract_questions (Gemini+grounding, D-03 contract) | unit | `pytest tests/unit/test_extract_questions.py -x` | ❌ W0 | ⬜ pending |
| 04-03 / Task 3.1 | 03 | 2 | fetch_zhihu (parser + image namespacing) | unit | `pytest tests/unit/test_fetch_zhihu.py -x` | ❌ W0 | ⬜ pending |
| 04-04 / Task 4.1 | 04 | 3 | merge_md pure function | unit | `pytest tests/unit/test_merge_md.py -x` | ❌ W0 | ⬜ pending |
| 04-04 / Task 4.2 | 04 | 3 | merge_and_ingest D-07/D-08/D-11 | unit | `pytest tests/unit/test_merge_and_ingest.py -x` | ❌ W0 | ⬜ pending |
| 04-05 / Task 5.1 | 05 | 4 | zhihu-haowen-enrich SKILL.md | static | grep frontmatter + 10 steps + MEDIA: | ❌ W0 | ⬜ pending |
| 04-05 / Task 5.2 | 05 | 4 | skill references + README | static | `test -f skills/zhihu-haowen-enrich/references/flow.md` | ❌ W0 | ⬜ pending |
| 04-05 / Task 5.3 | 05 | 4 | Skill remote smoke-test | manual | `ls ~/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json` | n/a | ⬜ pending |
| 04-06 / Task 6.1 | 06 | 4 | enrich_article SKILL.md | static | grep for-loop + /zhihu-haowen-enrich + 3 python helpers | ❌ W0 | ⬜ pending |
| 04-06 / Task 6.2 | 06 | 4 | enrich_article README | static | `test -f skills/enrich_article/README.md` | ❌ W0 | ⬜ pending |
| 04-07 / Task 7.1 | 07 | 5 | config.py Phase 4 keys | unit | `python -c "from config import ENRICHMENT_LLM_MODEL, ENRICHMENT_BASE_DIR, ZHIHAO_SKILL_NAME"` | ❌ W0 | ⬜ pending |
| 04-07 / Task 7.2 | 07 | 5 | ingest_wechat enriched=-1 marker | unit | `grep -q "UPDATE articles SET enriched" ingest_wechat.py` | ❌ W0 | ⬜ pending |
| 04-07 / Task 7.3 | 07 | 5 | strip --enrich flag | static | `! grep -q "\-\-enrich" skills/omnigraph_ingest/SKILL.md` | n/a | ⬜ pending |
| 04-07 / Task 7.4 | 07 | 5 | Remote E2E on 1 real article | E2E | manual `/enrich_article` + SQLite + LightRAG inspection | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements (created by plan 04-00)

- [ ] `pyproject.toml` — add `[tool.pytest.ini_options]` block with `testpaths = ["tests"]` and `asyncio_mode = "auto"`
- [ ] `requirements.txt` — add `pytest`, `pytest-asyncio`, `pytest-mock`
- [ ] `tests/conftest.py` — shared fixtures: temp BASE_DIR, fake Gemini client, fake LightRAG, fake requests.get
- [ ] `tests/unit/__init__.py` + `tests/integration/__init__.py`
- [ ] `tests/fixtures/golden/` — 2–3 WeChat article cache snapshots (captured manually from remote)
- [ ] `tests/fixtures/sample_wechat_article.md` — 2500-char fixture for extract_questions tests
- [ ] `tests/fixtures/sample_haowen_response.json` — mock child-skill return
- [ ] `tests/fixtures/sample_zhihu_page.html` — saved Zhihu HTML for parser tests
- [ ] `scripts/phase0_delete_spike.py` — D-14 standalone spike runner (remote only)
- [ ] `deploy.sh` — Windows→remote git pull helper (env-var driven, no committed creds)
- [ ] SQLite migration inline in `batch_scan_kol.py` (idempotent `_ensure_column`)
- [ ] `tests/unit/test_migrations.py` — 4 migration tests
- [ ] (Manual, remote) `.planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md` with `status: success`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase-0 LightRAG delete+reinsert spike | D-14 | Requires live LightRAG + Gemini on remote | `ssh remote 'python scripts/phase0_delete_spike.py'`; confirm `phase0_spike_report.md` has `status: success` |
| Zhihu 好问 10-step CDP flow | §2 research / Plan 05 Task 5.3 | Live Zhihu site, CN-gated, React+Draft.js selectors need empirical tuning | Invoke `/zhihu-haowen-enrich` on remote with a test question; confirm `haowen.json` written at `$ENRICHMENT_DIR/smoketest/0/` |
| D-13 Telegram QR login recovery | D-13 | Requires live login wall + user phone to scan QR | Force cookie expiry on remote Edge; invoke enrichment; confirm Telegram receives QR image; scan; reply `/resume`; confirm skill retries |
| `/skill-name` chaining on remote Hermes | D-02 / Plan 06 | Agent-level native invocation — not scriptable | First `/enrich_article` run: check `~/.hermes/sessions/` log confirms `skill_view("zhihu-haowen-enrich")` was called per iteration |
| Enriched WeChat MD visual quality | PRD §6.4 | Subjective — are the 3 好问 summaries readable? | Open the final MD in a Markdown viewer; eyeball before production ingest |
| Phase-4 Phase-Gate E2E | Plan 07 Task 7.4 | Whole-pipeline validation against one real article | Follow Plan 07 Task 7.4 step-by-step; assert SQLite `articles.enriched ∈ {2,-2}` and LightRAG contains `zhihu_<hash>_*` doc ids |

---

## Validation Sign-Off

- [x] All Wave-0 task stubs created by planner (plan 04-00)
- [x] Every Plan task has `<acceptance_criteria>` grep/cmd-verifiable OR listed in Manual-Only table above
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (except plan 05 which is pure Markdown — explicitly manual per §2)
- [x] Wave 0 covers all ❌ MISSING references in the verification map
- [x] No watch-mode flags (CI-safe)
- [x] Feedback latency: unit <10s, integration <5 min
- [x] `nyquist_compliant: true` — verification map populated, every auto task has a command, manual tasks enumerated above

**Approval:** approved (planner 2026-04-27)
