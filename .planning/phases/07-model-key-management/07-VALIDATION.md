---
phase: 07
slug: model-key-management
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `07-RESEARCH.md § Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4+ + pytest-asyncio 0.23+ + pytest-mock 3.12+ |
| **Config file** | none — default pytest config; tests/ directory exists |
| **Quick run command** | `.venv/Scripts/python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `.venv/Scripts/python -m pytest tests/ -v` |
| **Skill suite command** | `.venv/Scripts/python skill_runner.py skills/ --test-all` |
| **Estimated runtime** | ~30 seconds unit; ~2 min full suite; ~5 min skill suite |

---

## Sampling Rate

- **After every task commit:** `.venv/Scripts/python -m pytest tests/unit/ -x -q`
- **After every plan wave:** `.venv/Scripts/python -m pytest tests/ -v` + skill suite for affected skill
- **Before `/gsd:verify-work`:** Full suite green + live `python ingest_wechat.py <cached_url>` run + `kg_synthesize.py` smoke (exercises Cognee bridge)
- **Max feedback latency:** 30 seconds (unit), 120 seconds (full)

---

## Per-Task Verification Map

Task IDs will be assigned during planning. Placeholder map derived from phase decisions:

| Decision | Wave | Test Type | Automated Command | File Exists | Status |
|----------|------|-----------|-------------------|-------------|--------|
| D-02 (hybrid model config) | 0 | unit | `pytest tests/unit/test_models.py -x` | ❌ W0 | ⬜ pending |
| D-04 (BACKUP fold into pool) | 0 | unit | `pytest tests/unit/test_api_keys.py::test_backup_fold -x` | ❌ W0 | ⬜ pending |
| Precedence (primary→fallback→pool→error) | 0 | unit | `pytest tests/unit/test_api_keys.py::test_precedence -x` | ❌ W0 | ⬜ pending |
| Rotation + Cognee listener | 0 | integration | `pytest tests/integration/test_cognee_rotation.py -x` | ❌ W0 | ⬜ pending |
| D-08 (RPM env override) | 0 | unit | `pytest tests/unit/test_rate_limit.py::test_env_override -x` | ❌ W0 | ⬜ pending |
| Limiter singleton per model | 0 | unit | `pytest tests/unit/test_rate_limit.py::test_singleton -x` | ❌ W0 | ⬜ pending |
| Retry predicate (429/503 only) | 0 | unit | `pytest tests/unit/test_llm_client.py::test_is_retriable -x` | ❌ W0 | ⬜ pending |
| Retry re-acquires limiter slot | 0 | integration | `pytest tests/unit/test_llm_client.py::test_retry_reacquires_limiter -x` | ❌ W0 | ⬜ pending |
| Key rotation on 429 | 0 | integration | `pytest tests/unit/test_llm_client.py::test_rotate_on_429 -x` | ❌ W0 | ⬜ pending |
| D-06 (tests mock at lib level) | 0 | fixture | `grep -r 'lib.llm_client' tests/conftest.py` | ❌ W0 | ⬜ pending |
| `lib` importable | 0 | unit | `python -c "from lib import generate, aembed, generate_sync; print('ok')"` | ❌ W0 | ⬜ pending |
| D-09 (lightrag_embedding absorbed into lib/) | 0 | unit | `pytest tests/unit/test_lightrag_embedding.py -x` + `python -c "from lib import embedding_func; from lightrag_embedding import embedding_func as f2; assert embedding_func is f2; print('ok')"` | ❌ W0 | ⬜ pending |
| D-10 (EMBEDDING_MODEL default = gemini-embedding-2) | 0 | unit | `pytest tests/unit/test_models.py::test_embedding_model_default -x` + `python -c "from lib import EMBEDDING_MODEL; assert EMBEDDING_MODEL == 'gemini-embedding-2'; print('ok')"` | ❌ W0 | ⬜ pending |
| Wave 1 parity: ingest_wechat.py | 1 | integration | `python ingest_wechat.py <cached_url>` (cached, no HTTP) | ✅ manual | ⬜ pending |
| Wave 2 parity: P0 files migrate cleanly | 2 | e2e | `python skill_runner.py skills/omnigraph_ingest skills/omnigraph_query skills/omnigraph_architect --test-all` | ✅ | ⬜ pending |
| D-11 (config.py shims) | 2 | unit | `python -c "import config; from lib.models import INGESTION_LLM, VISION_LLM; assert config.INGEST_LLM_MODEL == INGESTION_LLM; assert config.IMAGE_DESCRIPTION_MODEL == VISION_LLM; assert config.ENRICHMENT_LLM_MODEL == INGESTION_LLM; print('ok')"` | ✅ | ⬜ pending |
| Wave 3 parity: Cognee rotation end-to-end | 3 | integration | `pytest tests/integration/test_cognee_rotation.py -x` + live `kg_synthesize.py` smoke | ❌ W0 + manual | ⬜ pending |
| D-05 (GITHUB_INGEST_LLM preserved) | 2 | unit | `pytest tests/unit/test_models.py::test_github_uses_preview -x` | ❌ W0 | ⬜ pending |
| D-07 (SKILL.md frontmatter updated) | 4 | grep | `grep "OMNIGRAPH_GEMINI_KEY" skills/*/SKILL.md` returns 3 matches | ✅ | ⬜ pending |
| Wave 4 parity: all skill tests green | 4 | e2e | `python skill_runner.py skills/ --test-all` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Files that must exist at the end of Wave 0 for subsequent waves to have verifiable acceptance criteria:

- [ ] `tests/unit/test_api_keys.py` — covers D-01 precedence, D-04 BACKUP fold, rotation, listener registration
- [ ] `tests/unit/test_rate_limit.py` — covers D-08 RPM env override, limiter singleton per model
- [ ] `tests/unit/test_llm_client.py` — covers retry predicate (429/503 only, not 400/401/403), re-acquire on retry, key rotation on ResourceExhausted
- [ ] `tests/unit/test_models.py` — covers D-02 hybrid pattern (constant default + env override), D-05 GITHUB_INGEST_LLM preservation, D-10 EMBEDDING_MODEL=gemini-embedding-2 default, RATE_LIMITS_RPM completeness (both embedding-001 and embedding-2)
- [ ] `tests/unit/test_lightrag_embedding.py` — covers D-09 absorption: embedding_func uses lib.api_keys.current_key() + lib.models.EMBEDDING_MODEL; root shim re-exports from lib
- [ ] `tests/integration/test_cognee_rotation.py` — covers Cognee `@lru_cache` singleton mutation via `cognee_bridge` listener
- [ ] `tests/conftest.py` — extend existing conftest with `mock_lib_llm` fixture that patches `lib.llm_client.generate` / `lib.llm_client.aembed` (D-06: lib-level mocking)

---

## Manual-Only Verifications

| Behavior | Decision | Why Manual | Test Instructions |
|----------|----------|------------|-------------------|
| Multi-account rotation actually increases quota | D-04 (multi-account support) | Requires 2+ real Google accounts; can't mock per-project quota semantics | User runs ingest workload that normally 429s with single key; with OMNIGRAPH_GEMINI_KEYS set to 2+ keys from different projects, expect 2× throughput before hitting 429 |
| Cached article replay (ingest_wechat parity) | Wave 1 gate | Requires cached article on disk (from prior ingest); no-HTTP path | `python ingest_wechat.py <url>` where `~/.hermes/omonigraph-vault/images/{hash}/final_content.md` exists; expect "Cached article found" log + LightRAG insert success |
| End-to-end kg_synthesize + Cognee rotation | Wave 3 gate | Requires live Gemini API + real Cognee DB; rotation triggered by wall-clock quota window | User invokes `python kg_synthesize.py "test query" hybrid` while mid-rotation; verify synthesis returns and Cognee context was retrieved (log `Recalled previous context` line) |
| SKILL.md live deploy validation | D-07 Wave 4 | Requires deployed Hermes instance | SSH to Hermes PC, run `hermes skills list omnigraph_ingest` → shows `OMNIGRAPH_GEMINI_KEY` as required env var |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ W0 references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30 s unit / 120 s full
- [ ] `nyquist_compliant: true` set in frontmatter
- [ ] `wave_0_complete: true` set in frontmatter after Wave 0 tests land

**Approval:** pending
</content>
</invoke>