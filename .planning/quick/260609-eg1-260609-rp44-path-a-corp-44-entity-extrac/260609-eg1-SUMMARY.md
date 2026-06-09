---
quick: 260609-eg1
filed: 2026-06-09
mode: diagnostic
no_code_change: true
issue: ISSUES #44 (P0 — graphml↔Qdrant 14-day divergence; long_form 0 sources visible symptom)
verdict: "DOES-NOT-REPRODUCE — 3/3 docs ingest cleanly with entities on Corp Vertex Gemini"
followup_slug: "260610-rp44b-deepseek-or-aliyun-side-investigation"
---

# Quick 260609-eg1 — SUMMARY

Diagnostic-only quick. Goal: cheap reproduction of #44 (96 docs in Aliyun LightRAG `kv_store_doc_status` show `status='processed'` but graphml has 0 entities). Run the local Corp Vertex Gemini path against representative bad docs to disambiguate three hypotheses: content/LightRAG-bug (locally fixable) vs DeepSeek-specific (Hermes-side, post-2026-06-22) vs content-specific.

## Outcome

**0/3 reproduce.** All 3 docs from the actual Aliyun 0-entity bad set ingest cleanly through the local Corp Vertex Gemini pipeline, producing 24 / 47 / 5 entity nodes respectively.

| Slot | doc_hash | sqlite_id | body_len | image_count | wall_s | entities | outcome |
|------|----------|-----------|----------|-------------|--------|----------|---------|
| MEDIUM | c7fb080361 | 500 | 5592 | 7 | 84.2 | **24** | NORMAL |
| LARGE | edc745d793 | 2445 | 9880 | 11 | 166.83 | **47** | NORMAL |
| SHORT | 75c8e99998 | 515 | 85 | 4 | 22.55 | **5** | NORMAL |

**Verdict:** maps to the **DEEPSEEK-SPECIFIC-OR-ALIYUN-SIDE-CONDITIONS** slot. Bug is NOT in LightRAG code path nor in document content (otherwise both providers would reproduce). Bug is either DeepSeek prompt-following gap on these specific texts, OR an Aliyun-side run-condition (transplant gap, SIGTERM mid-write window per `260608-e8l`, OOM-kill leaving doc_status=processed but graphml unwritten).

N=3 evidence is insufficient to disambiguate between "DeepSeek prompt gap" and "Aliyun-side flush race / partial-write window". Both hypotheses survive.

## Premise correction

Plan cited 96 bad docs (per ISSUES #44 row). Actual count via correct chunks_list × source_id join: **11 processed docs**. Of those 11: 3 pure article docs (`wechat_<10hex>`), 8 `_images` companions. Of the 3 pure docs, only 2 still exist in sqlite. Plan's SHORT/MEDIUM/LONG band was structurally unsatisfiable. Selection adapted to all available bad-set article docs (N=3 including a WeChat anti-bot boilerplate row for evidence). See `.scratch/repro44/SELECTION.md` for the corrected query and audit trail.

## Recommended follow-up

**Slug:** `260610-rp44b-deepseek-or-aliyun-side-investigation`
**Mode:** `/gsd:quick` (read-only investigation, ≤2h budget)

Two short read-only probes to narrow remaining hypotheses without committing to either of #44's expensive paths X/Y prematurely:

1. **DeepSeek replay (read-only on Aliyun):** SSH Aliyun, `venv-aim1/python3` with `OMNIGRAPH_LLM_PROVIDER=deepseek` (Aliyun's prod provider) ingest one of the 3 bad docs into a fresh isolated `working_dir=/tmp/repro44_<hash>`. If 0 entities reproduce → DeepSeek-specific entity-extract gap on this content. If entities produced → Aliyun-side run-condition issue.
2. **6/7 SIGTERM truncate-window cross-check:** inspect ingest journal for any of the 3 hashes around 6/7 08:40 CST (per `260608-e8l-SUMMARY.md`). If they were in flight at SIGTERM, that's the smoking gun — doc_status='processed' marker survived, graphml entities never persisted.

Either outcome dramatically reduces #44 path cost.

## Discipline

- **Diagnostic-only:** zero production source change, zero LightRAG fork, zero prod cron mutation, zero Aliyun write ops, zero Hermes touches (RO until 2026-06-22 honored).
- **Read-only SSH:** Aliyun queries via SELECT statements + read-only file open + scp pull; no INSERT/UPDATE/DELETE/systemctl/docker mutate.
- **Atomic write patch surface:** Aliyun's `os.fsync(fd)` after `os.O_RDONLY` open is Linux-specific; raised `[Errno 9] Bad file descriptor` on Windows when probe ran. Reverted to vanilla `nx.write_graphml(graph, file_name)` for the probe (graphml integrity verified post-run by node count). Surfaced as a future Windows-compat patch follow-up — does NOT block this quick's verdict (the question was content/provider behavior, not Windows fsync semantics).
- **No literal secrets:** SA token / API keys not inlined in any committed artifact; `.env.repro44` lives under gitignored `.scratch/repro44/`.
- **Forward-only commit:** explicit `git add <files>`; NO `--amend` / `reset --hard` / `--force-push` per `feedback_no_amend_in_concurrent_quicks`.
- **Worktree isolation:** executor ran in `.claude/worktrees/agent-a7afddca962ffcfdd` (locked branch); orchestrator copied artifacts to main and finalized commit (executor crashed at API-error after VERIFICATION.md was complete; commit step recovered by orchestrator).

## Cross-references

- [ISSUES.md row #44 (P0)](../../ISSUES.md) — long_form 0 sources visible symptom; 14-day graphml↔Qdrant divergence (NOT modified — this quick produces follow-up scope only, per PRINCIPLE #10)
- [260608-e8l-SUMMARY.md](../260608-e8l-260608-aliyun-recover-graphml-truncate-q/260608-e8l-SUMMARY.md) — graphml truncation 6/7 08:40 CST + atomic write structural fix
- Memory `graphml_qdrant_cross_version_divergence`
- Memory `lightrag_pin_drift_115_vs_116` (1.4.15 prod parity verified)
- Memory `lightrag_networkx_write_not_atomic` (atomic-write patch — Windows-compat issue surfaced this run)
- Memory `corp_pem_rebuild_pattern` (cert rebuild applied during pre-flight, 119/0 → 123/4 corp)
- Memory `vertex_ai_smoke_validated` (SA + endpoint matrix)
- Local evidence: `.scratch/repro44/SELECTION.md`, per-doc logs, per-doc result JSONs, `run_repro44.py` (gitignored, kept for follow-up)

## Wall-clock

~50 min total (Phase 0 SSH + bad-set query ~12 min, Phase 1 SCP + Phase 2 venv setup + cert rebuild + atomic-patch attempt ~15 min, Phase 3 three single-doc ingests ~22 min, VERIFICATION.md write + orchestrator commit ~12 min after executor API-error recovery).
