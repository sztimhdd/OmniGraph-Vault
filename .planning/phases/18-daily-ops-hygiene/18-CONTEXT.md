# Phase 18: Daily-Ops Hygiene · CONTEXT

**Milestone:** v3.3 — Daily-Ops Hygiene
**Phase goal:** Ship the 6 HYG-* requirements from v3.3. Close Wave 0 Close-Out deferred items + 2026-05-03 Vertex flip follow-up.
**Requirements covered:** HYG-01..HYG-06

---

## Locked decisions (inherited from Wave 0 Close-Out, no re-discussion)

- **D-18-01 LLM routing (from Phase 7 D-09 supersession):** DeepSeek via raw HTTP for LLM work. Gemini is Vision + Embedding only. No `google.genai` for classification / translation / synthesis logic. Reference pattern: `batch_classify_kol._call_deepseek` + `enrichment/rss_classify._call_deepseek` (raw `requests.post` to `api.deepseek.com/v1/chat/completions`).
- **D-18-02 Vertex embedding model name (2026-05-03 ground truth):** `gemini-embedding-2` (NO suffix). `lib.lightrag_embedding._resolve_model()` is a pass-through (commit `9069f59`). Do NOT reintroduce `-preview` mapping. Any new code touching this must run the live probe in `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/vertex_ai_smoke_validated.md` first.
- **D-18-03 Telegram alerts:** reuse Phase 5 Wave 2 Telegram plumbing (same bot token, same chat id from `~/.hermes/.env`) — HYG-01 and HYG-06 send to the same chat as the daily digest, distinguished by emoji prefix (🔴 critical, 🟡 warning, ✅ recovery).
- **D-18-04 Regression fixture source (HYG-05):** single fixture `test/fixtures/gpt55_article/` (production baseline, already wired into `scripts/bench_ingest_fixture.py`). No new fixtures created — Wave 0 Close-Out empirically showed real-batch > synthetic fixtures for defect yield. v3.3 adds the cheap single-fixture gate on top of (not in place of) the real-batch cron.
- **D-18-05 Atomic commits per plan:** one commit per plan, prefix `feat(18-0X)` / `fix(18-0X)` / `docs(18-0X)`. Each commit is push-and-rebase-safe against concurrent Phase 5 Wave 2/3 pushes.
- **D-18-06 Hermes-side verification:** all live probes (Vertex catalog hit, Telegram delivery, cron registration) executed on Hermes. Windows local testing is mock-only for any endpoint the Cisco Umbrella proxy blocks (`api.deepseek.com`, `api.siliconflow.cn`). Vertex AI endpoints do reach local from the paid-tier SA (see memory file) but live probes against real API are Hermes-side.

---

## Waves

| Wave | Plans | Blocked by | Start |
|---|---|---|---|
| 1 | 18-00, 18-01, 18-02, 18-03 | — | Immediately |
| 2 | 18-04, 18-05 | Phase 5 Task 6.2 (observation) + Task 6.3 (Exit State) | User signal after observation window |

Wave 1 → Wave 2 handoff: after 18-03 SUMMARY lands, halt and report to user. Do NOT start Wave 2 autonomously.

---

## Non-goals (hard boundaries)

- No new milestone v3.4 decisions (defer until v3.3 data accumulated over 14 days)
- No new data sources (GitHub / Twitter / etc.) — v3.3 is hardening only
- No new UI / query-layer work beyond HYG-04 prompt standardization
- Do NOT modify Phases 7-17 artifacts (all archived/closed)
- Do NOT touch Phase 5 Wave 2/3 files (`05-04/05/06*`, `enrichment/orchestrate_daily.py`, `enrichment/daily_digest.py`, `scripts/register_phase5_cron.sh`) — concurrent session owns them. HYG-06 extends `orchestrate_daily.py` ONLY after Wave 2 unblocks.

---

## File ownership

Wave 1 plans touch these files (no overlap with Phase 5 concurrent work):

| Plan | Files created/modified |
|---|---|
| 18-00 | `scripts/vertex_live_probe.py` (new), `scripts/register_vertex_probe_cron.sh` (new), `tests/unit/test_vertex_live_probe.py` (new) |
| 18-01 | `ingest_wechat.py` (surgical: image cap after `filter_small_images`), `tests/unit/test_image_cap.py` (new) |
| 18-02 | `kg_synthesize.py` (surgical: JSONL history read/write), `tests/unit/test_query_history.py` (new) |
| 18-03 | `kg_synthesize.py` (extract `IMAGE_URL_DIRECTIVE` constant), `skills/omnigraph_query/SKILL.md` (image-server-note cross-ref), `tests/unit/test_image_directive_shared.py` (new) |

No file touched by more than one Wave 1 plan. No file touched by both Wave 1 and Phase 5 Wave 2/3.

---

## Stop-and-ping conditions (Wave 1)

- gsd-plan-checker would BLOCK a plan twice
- 18-01 decision: if entity-merge timeout extension becomes more defensible than N-image cap → re-scope with user
- 18-02 decision: if restoring Cognee becomes more defensible than JSONL history → re-scope with user
- Any Hermes-side probe shows `gemini-embedding-2` → 404 (= third Vertex flip) → do NOT auto-patch; ping user immediately
- Any architecture smell that wasn't visible during planning

---

## References

- `.planning/MILESTONE_v3.3_REQUIREMENTS.md` — this milestone
- `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` § A–G — Wave 0 Close-Out narrative
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/vertex_ai_smoke_validated.md` — live probe template
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md` — SSH connection details (do NOT commit)
- `CLAUDE.md` § "Vertex AI Migration Path" + § "LLM routing" + § "Cisco Umbrella" — hard constraints
- `scripts/register_phase5_cron.sh` — Hermes cron registration template
- `batch_classify_kol.py` / `enrichment/rss_classify.py` — DeepSeek raw HTTP pattern
