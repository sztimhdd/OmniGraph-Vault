---
artifact: CONTEXT
phase: kdb-2
created: 2026-05-16
locked_decisions: 6
plans: 4
total_estimate: 1.5-2.25d
---

# Phase kdb-2 — Databricks App Deploy — Context

> One-page summary tying together: phase mission, the 6 user-locked decisions distilled from the orchestrator prompt, and the plan decomposition. Read alongside `kdb-2-RESEARCH.md` (the architectural foundation, ~1140 lines).

## Mission

Stand up the production Databricks App `omnigraph-kb`, integrate the MosaicAI provider end-to-end via the `lib/llm_complete.py` dispatcher (LLM-DBX-01), wire the kdb-1.5 storage adapter into `app.yaml`'s `command:` (DEPLOY-DBX-04), grant the App SP everything it needs against UC + Model Serving (AUTH-DBX-01..04), and prove Smoke 1 + Smoke 2 PASS via browser-SSO interactive UAT.

The phase builds DIRECTLY on kdb-1.5's two frozen artifacts (`databricks-deploy/startup_adapter.py` + `databricks-deploy/lightrag_databricks_provider.py`) — kdb-2 IMPORTS them, never modifies them. Smoke 3 (KG-mode RAG round-trip) is intentionally deferred to kdb-3 because the LightRAG storage Volume is empty until kdb-2.5 re-indexes it.

## REQs in scope (20 total)

| Group | IDs | Count |
|-------|-----|-------|
| AUTH | AUTH-DBX-01..05 | 5 |
| LLM  | LLM-DBX-01, LLM-DBX-02, LLM-DBX-04, LLM-DBX-05 | 4 |
| DEPLOY | DEPLOY-DBX-01..09 | 9 |
| OPS  | OPS-DBX-01, OPS-DBX-02 | 2 |

LLM-DBX-03 was satisfied by kdb-1.5-02 (factory file shipped + dry-run verified). Smoke 3 (OPS-DBX-03 / kdb-3 closure scope) NOT in kdb-2.

## Six locked decisions (NON-NEGOTIABLE)

These were locked by the orchestrator after researcher surfaced the trade-offs. The plans MUST honor them; they are NOT to be re-litigated.

### Decision 1 — LLM-DBX-04 implementation lives in `lib/llm_complete.py` (NOT kb/services/synthesize.py)

Translation in dispatcher. `lib/llm_complete.py` `databricks_serving` branch catches Databricks SDK 503/429/timeout/connection exceptions and re-raises them as generic exception types that kb/services/synthesize.py's EXISTING `kg_unavailable` reason-code path already handles (kb-v2.1-1 KG MODE HARDENING shipped that pattern in commit `eff934f`).

Implementation footprint:
- `lib/llm_complete.py` — exception translation in the `databricks_serving` branch (already in CONFIG-EXEMPTIONS)
- `kb/services/synthesize.py` — NOT MODIFIED. CONFIG-EXEMPTIONS NOT extended.
- No new `kg_serving_unavailable` literal added; existing `kg_unavailable` (or whichever literal kb-v2.1-1 implements) is reused.

Rationale: minimizes blast radius (one-file change, already exempted). The REQ doc's mention of "new reason code" is satisfied by translating-into-existing-bucket without a literal-name change. Override of RESEARCH.md Q4 default-recommendation (Option A — extending CONFIG-EXEMPTIONS to kb/services/synthesize.py).

### Decision 2 — Embedding dim mismatch (Vertex 3072 vs Qwen3 1024) DEFERRED

RESEARCH.md Q3 surfaced this as the biggest sleeper risk: `kg_synthesize.py:106` still imports `embedding_func` from `lib.lightrag_embedding` (Vertex/Gemini, dim=3072), while kdb-2.5 will populate the Volume with Qwen3 dim=1024 vectors. First synthesis call post-kdb-2.5 will dim-mismatch.

Decision: kdb-2 does NOT include embedding dispatcher work. This risk is documented in RESEARCH.md Risk #4 + Q3 and is surfaced for post-kdb-2 (kdb-2.5/kdb-3 or new phase kdb-2.7).

kdb-2-04 verification MUST cite this explicitly: "Smoke 1+2 use FTS5 fallback path — embedding code path NOT exercised; embedding-side dim mismatch risk DEFERRED to post-kdb-2 (see RESEARCH.md § Risks #4)."

### Decision 3 — LLM-DBX-02 actual scope is REDUCED

Pre-existing dispatcher work (quick-260509-s29 W3, see commit history) already covers `kg_synthesize.py:19` (import line: `from lib.llm_complete import get_llm_func`) + `kg_synthesize.py:106` (call site: `llm_model_func=get_llm_func()`).

LLM-DBX-02 work in kdb-2 is therefore reduced to:
- (a) Test confirming `OMNIGRAPH_LLM_PROVIDER=databricks_serving` actually exercises the new dispatcher branch through `kg_synthesize.synthesize_response`
- (b) CONFIG-EXEMPTIONS.md ledger flip: `kg_synthesize.py` row from `NOT YET MODIFIED` → `MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2 confirms via test)`
- (c) Verify NO other hardcoded LLM call sites in kg_synthesize.py beyond the dispatcher path (researcher confirmed clean per RESEARCH.md Q3)

**Diff scope to `kg_synthesize.py` file in kdb-2: ZERO new lines.** Only CONFIG-EXEMPTIONS ledger update + new test.

### Decision 4 — Smoke 1+2 verification path = BROWSER-SSO INTERACTIVE UAT

Workspace Private Link (verified by kdb-1 SPIKE-FINDINGS) blocks external Bearer + browser-SSO from external network. Recommended path:
1. User opens App URL in browser via workspace UI Apps tab (`https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb`)
2. Completes SSO inside the workspace UI session
3. Captures screenshots + Apps Logs panel
4. Pastes screenshots into `kdb-2-SMOKE-EVIDENCE.md`

NO curl + Bearer attempt. NO Playwright-from-local-Windows attempt for Smoke 1+2 (Cisco Umbrella + Private Link both block this path). Workspace serverless notebook proxy is a fallback if user opts in, but plan defaults to browser-SSO UAT.

### Decision 5 — `app.yaml` `command:` shape (locked)

```yaml
command:
  - bash
  - -c
  - "cd /app/databricks-deploy && PYTHONPATH=/app:/app/databricks-deploy python -c 'from startup_adapter import hydrate_lightrag_storage_from_volume; print(hydrate_lightrag_storage_from_volume())' && exec uvicorn kb.api.app:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT"
```

Single bash -c step. `$DATABRICKS_APP_PORT` substitution survives bash invocation (Apps runtime substitutes BEFORE invoking command). Layout uncertainty (PYTHONPATH semantics) is MEDIUM confidence per RESEARCH.md Q7 — **kdb-2-04 Wave 0 (Step 0) minimal-deploy validation step CONFIRMS** before wiring full multi-step.

### Decision 6 — Smoke 3 DEFERRED to kdb-3

Plans MUST NOT include Smoke 3 (KG-mode RAG round-trip). It is post-kdb-2.5 work. kdb-2-04 verification MUST explicitly say "Smoke 3 DEFERRED to kdb-3 post-kdb-2.5 re-index".

## Plan decomposition (4 plans, 3 waves)

| Plan | Slug | Wave | REQs | Est | One-line scope |
|------|------|------|------|-----|----------------|
| **kdb-2-01** | `app-sp-and-uc-grants` | 1 | AUTH-DBX-01..05 (5) | 0.25d | App SP create + 5 grants (USE CATALOG + USE SCHEMA + READ VOLUME + CAN_QUERY×2 + SSO) |
| **kdb-2-02** | `llm-dispatcher-databricks-serving` | 1 | LLM-DBX-01 (1) + LLM-DBX-04 implementation | 0.5d | `lib/llm_complete.py` `databricks_serving` branch + Decision-1 exception translation + 4 unit tests; CONFIG-EXEMPTIONS row flip |
| **kdb-2-03** | `kg-synthesize-routing-and-degrade` | 2 | LLM-DBX-02, LLM-DBX-04 (2) | 0.25-0.5d | Integration test for `OMNIGRAPH_LLM_PROVIDER=databricks_serving` exercising synthesize_response; LLM-DBX-04 verified via dispatcher-translation 503/429/timeout test → existing kg_unavailable fallback; CONFIG-EXEMPTIONS row flip |
| **kdb-2-04** | `deploy-and-smoke` | 3 | DEPLOY-DBX-01..09 (9), LLM-DBX-05 (1), OPS-DBX-01/02 (2) | 0.5-1d | `databricks-deploy/{app.yaml, Makefile, requirements.txt}` (extend); deploy + Wave-0 minimal-deploy validation per Decision 5; Smoke 1+2 browser-SSO UAT per Decision 4; SMOKE-EVIDENCE.md |

**Total estimate:** 1.5-2.25d (within budget; reduced lower bound because LLM-DBX-02 work is mostly pre-existing per Decision #3).

### Wave dependency graph

```
Wave 1 (parallel):
  kdb-2-01 (AUTH)            ──┐
  kdb-2-02 (LLM dispatcher)  ──┤
                                │
Wave 2:                         │
  kdb-2-03 (routing+degrade) ◄──┘ (depends on kdb-2-02 dispatcher landing)

Wave 3:
  kdb-2-04 (deploy+smoke)    ◄── (depends on kdb-2-01 + kdb-2-02 + kdb-2-03)
```

### Why this decomposition (not vertical slicing)

The mostly-vertical "AUTH | LLM-side | deploy" decomposition was chosen because:
- AUTH (plan 01) is pure CLI/SQL with no Python dependencies — independent.
- LLM dispatcher branch (plan 02) is pure Python in `lib/` — independent of AUTH and of the integration tests.
- LLM-DBX-04 verification (plan 03) needs the dispatcher branch to exist before testing the translated-exception path → depends on plan 02.
- Deploy (plan 04) consumes BOTH the SP grants (plan 01) and the dispatcher branch (plan 02) at runtime, plus the integration test from plan 03 to prove the wired path works pre-deploy → depends on all three.

Plans 01 + 02 file-modification sets are disjoint (`app.yaml` not yet existing; `lib/llm_complete.py` only) — safe parallel.

## Hard constraints inherited from ROADMAP rev 3 lines 98-105

Plan-checker WILL block plans missing any of these. Each plan's "Hard constraints honored" section MUST cite the relevant subset.

1. `app.yaml` at root of `--source-code-path` (i.e., `databricks-deploy/app.yaml` is at root of the deployed source tree per `--source-code-path .../databricks-deploy`)
2. `command:` uses `$DATABRICKS_APP_PORT` substitution (NOT hardcoded `:8766`)
3. 3 LLM env literals present in `app.yaml` `env:` (per LLM-DBX-05): `OMNIGRAPH_LLM_PROVIDER=databricks_serving`, `KB_LLM_MODEL=databricks-claude-sonnet-4-6`, `KB_EMBEDDING_MODEL=databricks-qwen3-embedding-0-6b`
4. ZERO `valueFrom:` for any LLM-related env (Apps SP injection carries auth, not secrets)
5. ZERO DeepSeek references in `databricks-deploy/`, `app.yaml`, `requirements.txt`
6. LLM-DBX-02 diff scope STRICTLY limited per Decision #3 (CONFIG-EXEMPTIONS ledger flip only, ZERO new lines in `kg_synthesize.py`)
7. (DEPLOY-DBX-09) `app.yaml` does NOT set `KB_KG_GCP_SA_KEY_PATH` or `GOOGLE_APPLICATION_CREDENTIALS` (verifiable via grep)
8. (Decision 1) LLM-DBX-04 implementation lives entirely in `lib/llm_complete.py`; `kb/services/synthesize.py` NOT modified; CONFIG-EXEMPTIONS NOT extended
9. (Decision 2) Embedding dim risk DEFERRED — kdb-2 plans do NOT include `lib/embedding_complete.py` or any embedding-side migration
10. (Decisions 4 + 6) Smoke 1+2 use BROWSER-SSO INTERACTIVE UAT; Smoke 3 DEFERRED to kdb-3
11. (kdb-1.5 territory) `databricks-deploy/startup_adapter.py` + `databricks-deploy/lightrag_databricks_provider.py` NOT modified by kdb-2 (kdb-2 IMPORTS only)

## Concurrent-agent safety

Per `feedback_no_amend_in_concurrent_quicks.md` + `feedback_git_add_explicit_in_parallel_quicks.md`:

- Forward-only commits — NO `git add -A`, NO `--amend`, NO `git reset --hard`, NO `git rebase -i`, NO `git push --force`
- Use `git add <explicit-files>` for plan commits
- ff-merge fallback if push collision
- Plans 01 + 02 are concurrent-safe because file-modification sets are disjoint.
- Plans 03 + 04 are sequential after 01 + 02 land.

ZERO overlap with v2.1-6/7 territory (`kb/data/article_query.py`, `kb/data/lang_detect.py`).

ZERO overlap with kdb-1.5 territory (don't modify `databricks-deploy/{startup_adapter.py, lightrag_databricks_provider.py}`).

## Skills baked per plan

Per `feedback_skill_invocation_not_reference.md`: each plan's frontmatter `skills:` list MUST be matched 1:1 by literal `Skill(skill="<name>", ...)` invocation in at least one task. SUMMARY.md plan-checker greps for these substrings.

| Plan | Skills |
|------|--------|
| kdb-2-01 | `databricks-patterns`, `security-review` |
| kdb-2-02 | `python-patterns`, `writing-tests` |
| kdb-2-03 | `python-patterns`, `writing-tests` |
| kdb-2-04 | `databricks-patterns`, `search-first` |

## Anti-patterns blocked

These MUST NOT appear in any plan or executor SUMMARY:

- Smoke 3 / RAG round-trip work (kdb-3 territory)
- `WRITE_VOLUME` grant (AUTH-DBX-03 forbids)
- Modifications to `kb/services/synthesize.py` (Decision 1 — CONFIG-EXEMPTIONS not extended)
- Modifications to `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 territory; frozen)
- New file `lib/embedding_complete.py` (Decision 2 — embedding work deferred)
- DeepSeek references in `databricks-deploy/`
- Literal secrets in any commit (`feedback_no_literal_secrets_in_prompts.md`)
- `git commit --amend` or `git reset --hard` (`feedback_no_amend_in_concurrent_quicks.md`)
- `git add -A` (`feedback_git_add_explicit_in_parallel_quicks.md`)
- Aliyun deploy / Hermes runtime work (different milestones)

## Open questions surfaced for plan-checker / kdb-3

1. (Q7 layout) `--source-code-path` + PYTHONPATH semantics — kdb-2-04 Wave 0 (Step 0) minimal-deploy validation answers this concretely before full deploy.
2. (Q1c) AUTH-DBX-04 CLI grammar (`databricks serving-endpoints get-permissions` accepts endpoint name?) — kdb-2-01 verifies; falls through to in-app probe (Path B) if Path A CLI rejects.
3. (Q8 stop) `databricks apps stop` subcommand existence in v0.260+ — kdb-2-04 search-first skill invocation verifies before adding to Makefile.
4. (Decision 2 deferral) Embedding-side dim mismatch — explicitly deferred; carried forward to kdb-3 RUNBOOK risk register.

## Files affected (kdb-2 scope)

### NEW (kdb-2 creates)

| Path | Plan | Purpose |
|------|------|---------|
| `databricks-deploy/app.yaml` | kdb-2-04 | DEPLOY-DBX-02..04 + LLM-DBX-05 + DEPLOY-DBX-08/09 |
| `databricks-deploy/Makefile` | kdb-2-04 | DEPLOY-DBX recipes (deploy/logs/stop/smoke/sp-grants) |
| `tests/integration/test_kg_synthesize_dispatcher.py` | kdb-2-03 | LLM-DBX-02 + LLM-DBX-04 verification |
| `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md` | kdb-2-04 | OPS-DBX-01/02 evidence |

### MODIFY (CONFIG-EXEMPTIONS scope)

| Path | Plan | Scope |
|------|------|-------|
| `lib/llm_complete.py` | kdb-2-02 | Add `databricks_serving` branch + Decision-1 exception translation + extend `_VALID` (already in CONFIG-EXEMPTIONS — no extra approval) |
| `tests/unit/test_llm_complete.py` | kdb-2-02 | Extend with 4 new tests for `databricks_serving` branch (tests/ — outside CONFIG-DBX-01 scope per CONFIG-DBX-02) |
| `databricks-deploy/CONFIG-EXEMPTIONS.md` | kdb-2-02 + kdb-2-03 | Flip both kdb-1.5 `NOT YET MODIFIED` rows to `MODIFIED — see commit <hash>` |
| `databricks-deploy/requirements.txt` | kdb-2-04 (optional) | Possibly extend if FastAPI/uvicorn baseline incomplete (verify) |
| `databricks-deploy/CONFIG-EXEMPTIONS.md` | kdb-2-04 | (No new exemption rows — Decision 1 means kb/services/synthesize.py NOT added) |

### VERIFY-ONLY (kdb-2 imports, doesn't modify)

| Path | Why imported, not modified |
|------|----------------------------|
| `databricks-deploy/startup_adapter.py` | kdb-1.5-01 deliverable — kdb-2 wires into `app.yaml` `command:` |
| `databricks-deploy/lightrag_databricks_provider.py` | kdb-1.5-02 deliverable — kdb-2 imports via dispatcher branch |
| `kg_synthesize.py` | Per Decision 3 — already-integrated dispatcher; ZERO net change |
| `kb/services/synthesize.py` | Per Decision 1 — translation in dispatcher reuses existing kg_unavailable path |
| `kb/data/article_query.py` | Existing `?mode=ro` URI pattern works on Volume (kdb-1.5-RESEARCH Q4) |
| `kb/config.py` | `OMNIGRAPH_BASE_DIR` + `KB_DB_PATH` already split correctly |

## REQ → plan map (all 20)

| REQ | Plan | Verification |
|-----|------|--------------|
| AUTH-DBX-01 | kdb-2-01 | `SHOW GRANTS ON CATALOG mdlg_ai_shared` filtered to App SP returns USE_CATALOG row |
| AUTH-DBX-02 | kdb-2-01 | `SHOW GRANTS ON SCHEMA mdlg_ai_shared.kb_v2` returns USE_SCHEMA row |
| AUTH-DBX-03 | kdb-2-01 | `SHOW GRANTS ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault` returns READ_VOLUME (NOT WRITE) |
| AUTH-DBX-04 | kdb-2-01 | `databricks serving-endpoints get-permissions` Path A; Path B in-app probe fallback |
| AUTH-DBX-05 | kdb-2-01 | Workspace SSO is Apps default; verified via direct browser test in kdb-2-04 Step 0 |
| LLM-DBX-01 | kdb-2-02 | `pytest tests/unit/test_llm_complete.py -v` 9 tests PASS (5 existing + 4 new) |
| LLM-DBX-02 | kdb-2-03 | Integration test confirms env-var path; CONFIG-EXEMPTIONS row flipped |
| LLM-DBX-04 | kdb-2-03 | Integration test forces 503 → confirms FTS5 fallback + existing kg_unavailable reason path (per Decision 1) |
| LLM-DBX-05 | kdb-2-04 | `grep -c "OMNIGRAPH_LLM_PROVIDER\\|KB_LLM_MODEL\\|KB_EMBEDDING_MODEL" databricks-deploy/app.yaml` returns 3 |
| DEPLOY-DBX-01 | kdb-2-04 | `databricks apps get omnigraph-kb` returns non-error JSON |
| DEPLOY-DBX-02 | kdb-2-04 | `find databricks-deploy -maxdepth 1 -name app.yaml` returns 1 file |
| DEPLOY-DBX-03 | kdb-2-04 | `grep -c "DATABRICKS_APP_PORT" app.yaml` ≥1; `grep -c ":8766" app.yaml` = 0 |
| DEPLOY-DBX-04 | kdb-2-04 | env literals + adapter wiring grep-checked |
| DEPLOY-DBX-05 | kdb-2-04 | `databricks apps deploy --timeout 20m` returns SUCCEEDED |
| DEPLOY-DBX-06 | kdb-2-04 | Browser-SSO UAT — App URL renders 200 after SSO |
| DEPLOY-DBX-07 | kdb-2-04 | `grep -ci "deepseek" databricks-deploy/requirements.txt` = 0 |
| DEPLOY-DBX-08 | kdb-2-04 | grep `OMNIGRAPH_LLM_PROVIDER=databricks_serving` literal in app.yaml; grep `valueFrom:` for that env returns 0 |
| DEPLOY-DBX-09 | kdb-2-04 | `grep -cE "KB_KG_GCP_SA_KEY_PATH\|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml` = 0 |
| OPS-DBX-01 | kdb-2-04 | KB-v2 Smoke 1 verbatim — bilingual UI toggle screenshots in SMOKE-EVIDENCE.md |
| OPS-DBX-02 | kdb-2-04 | KB-v2 Smoke 2 verbatim — search + detail page + image render screenshots |

20/20 covered.

## References

- `kdb-2-RESEARCH.md` (this directory; 1140 lines) — architectural foundation
- `.planning/REQUIREMENTS-kb-databricks-v1.md` rev 3 — REQ definitions
- `.planning/ROADMAP-kb-databricks-v1.md` rev 3 lines 82-117 — kdb-2 spec + hard constraints
- `.planning/STATE-kb-databricks-v1.md` rev 3 — milestone-base hash + locked defaults
- `.planning/PROJECT-kb-databricks-v1.md` rev 3 — milestone goals + scope
- `databricks-deploy/CONFIG-EXEMPTIONS.md` — exemption ledger (kdb-2 EXTENDS, does NOT add new rows under Decision 1)
- `databricks-deploy/startup_adapter.py` (133 lines) — frozen kdb-1.5-01 deliverable
- `databricks-deploy/lightrag_databricks_provider.py` (148 lines) — frozen kdb-1.5-02 deliverable
- `lib/llm_complete.py` (48 lines) — kdb-2-02 modifies
- `kg_synthesize.py:19,106` — already-integrated dispatcher (quick-260509-s29 W3)
- `tests/unit/test_llm_complete.py` (60 lines, 5 tests) — kdb-2-02 extends
- `kdb-1.5-VERIFICATION.md` — phase-prior verification artifacts

---

_Authored: 2026-05-16 by gsd-planner. Honors all 6 locked decisions, 11 hard constraints, 4 anti-pattern blocks. Plans follow._
