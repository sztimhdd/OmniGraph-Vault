# 260606-bd-cache-async-quickwin — SUMMARY

**Date:** 2026-06-06
**Quick slug:** `260606-bd-cache-async-quickwin`
**Outcome:** B HALTED (architecturally infeasible) · D HALTED (OOM red line) · **A3 + A2 SHIPPED** (replacement path picked after TASK 1 surface)

---

## Outcome

The original plan asked for "B + D zero-LoC quick-wins, ~30-50% speedup". TASK 1 source-read invalidated all three plan premises. Pivoted (orchestrator decision, user-confirmed) to **A3 + A2** replacement path. Both shipped.

| Plan task | Status | Why |
|---|---|---|
| ~~B (cross-article LLM-extract cache wrapper)~~ | **HALTED** | LightRAG cache key is `compute_args_hash(prompt)`, NOT chunk-salted; entity-extract returns batch from one chunk so wrapper can't dedup by `entity_name` pre-call; summary path's `description_list` differs per article → ~0% cross-article hit. Wrapper architecturally cannot achieve the claimed save without forking LightRAG's `_merge_nodes_then_upsert`. |
| ~~D (max_async 8→16 env-driven)~~ | **HALTED** | Env vars `LIGHTRAG_*_MAX_ASYNC` don't exist (only `MAX_ASYNC` + `EMBEDDING_FUNC_MAX_ASYNC`). `ingest_wechat.py:414-417` hardcodes ctor kwargs to **2/2/2** (set by `91b33f1` 260601-ipo OOM postmortem after 4 OOM-kills/24h on 15GB ECS, paired with `MemoryMax=4G`). 2→16 = 8× the OOM-tested ceiling = guaranteed re-OOM on next cron. #41/#42 already firing on the same RAM ceiling. |
| **A3 (PROCESSED-gate budget 150s→300s)** | ✅ **SHIPPED** repo-side via `b6f4a23`; Aliyun .env apply DEFERRED (#42-class SSH throttle). |
| **A2 (opt-in global embedding cache wrapper)** | ✅ **SHIPPED** via `1354a22`. Default-OFF byte-identical pre-A2; opt-in via `OMNIGRAPH_EMBEDDING_CACHE=1`. |

---

## Tasks (executed)

### TASK 1 — Source verify (DONE)

Read LightRAG 1.4.15 (`venv/Lib/site-packages/lightrag/utils.py:540-2123`, `operate.py:2950-3030, 3290-3338`, `lightrag.py:370-465`, `constants.py:89-93`) + repo `ingest_wechat.py:355-428` + `git log` + `.planning/ISSUES.md` rows #41/#42.

**Wrote:** `.planning/quick/260606-bd-cache-async-quickwin/260606-bd-TASK1-SURFACE.md` (full source-citation table + halt rationale + 5-path decision matrix).

**Time:** ~10 min wall (planned 15).

### TASK 2 (A3) — repo PROCESSED-gate default raise

`ingest_wechat.py:57` default `OMNIGRAPH_PROCESSED_BACKOFF` 5.0 → 10.0 (30 retries × 10s = 300s budget).

**Commit:** `b6f4a23` `fix(ingest): #39 raise PROCESSED-gate default 5.0->10.0 (300s budget)`.

**Aliyun .env apply:** **DEFERRED** — SSH banner timeout to `aliyun-vitaclaw` across all retries (15s/60s/120s/30s/15s connection budgets, ~45+ min into throttle window). Same symptom as ISSUES #42 (50-80 min cross-border SLB throttle). Repo-side fix takes effect on next Aliyun `git pull` + `systemctl restart` of `daily-ingest.service` / `omnigraph-ingest.service`. Aliyun explicit override (sed-append `OMNIGRAPH_PROCESSED_BACKOFF=10.0` to `/root/.hermes/.env`) is logged as new ISSUE row #43 sub-bullet for orchestrator to apply when SSH unblocks.

**Verification:** `git diff` validated (5 +1 lines), pushed clean, no force / no amend.

### TASK 3 (A2) — opt-in global embedding cache wrapper

**New file:** `lib/llm_cache_embedding_global.py` (~150 LoC including docstring + correctness invariants).

**Hook:** `lib/lightrag_embedding.py:280-289` — `embedding_func.func = _wrap_embedding_cache(_embed)`. `_wrap_embedding_cache(inner)` is a no-op when env `OMNIGRAPH_EMBEDDING_CACHE` unset; returns wrapped callable when set.

**Key design points:**

| Decision | Why |
|---|---|
| Default OFF (env opt-in) | Quick u17 / ISSUES #38/#39/#40 evidence isn't strong enough to flip prod default; defer flip to a follow-up quick that sees real cache-hit-ratio metrics under cron |
| Cache key = `(sha256(text)[:16], is_query_bool)` | Captures the only two prompt-variant axes (`_DOC_PREFIX` vs `_QUERY_PREFIX` on the same text); image URLs in `text` already differ per article so collision-free |
| Storage = `pickle` at `OMNIGRAPH_BASE_DIR/embedding_cache.pkl` | No new dependency (avoid `diskcache`); matches existing `canonical_map.json` atomic-write pattern (`.tmp` + `os.replace`) |
| Bounded 50_000 entries, FIFO evict 5_000 | At 12 KB / 3072d-float32 vector, cap = ~600 MB. FIFO is OK because entity-description vectors are stable (idempotent per content); LRU not justified |
| Flush every 50 misses (batched) | Keeps disk write rate low (1 flush per ~50 new entities); next-call flush picks up trailing dirty count |

**Smoke verification:** in-process pytest-style assertion against `fake_embed` returning zero vectors:
- Default OFF: `wrap(inner) is inner` (truly no-op)
- ON path: `wrap(inner)` returns wrapped callable; first call populates cache, second call returns identical vectors without invoking inner

**Corp Vertex verify (real call, .scratch/260606-bd-cache-probe-vertex.py):**

```json
{
  "hashes": ["c8cc5b1fb7", "b37b0df5fb"],
  "cache_enabled": true,
  "wall_s_pass_a_cold": 207.539,
  "pass_a_exception": null,
  "cache_pre_pass_a":  {"entries": 0,   "max": 50000, "dirty": 0},
  "cache_post_pass_a": {"entries": 154, "max": 50000, "dirty": 4},
  "wall_s_pass_b_warm": 0.003,
  "pass_b_exception": null,
  "cache_pre_pass_b":  {"entries": 154, "max": 50000, "dirty": 4},
  "cache_post_pass_b": {"entries": 154, "max": 50000, "dirty": 4},
  "graphml_valid": "missing",
  "speedup_ratio": 70185.723
}
```

**Reading the data:**

- ✅ PASS A wall 207.5s — close to u17 PASS A baseline 230s (Vertex Gemini through corp network, 跨境 bandwidth-bound)
- ✅ Cache populated **154 entries** on 2 KOL articles ≈ 77 entities/article (matches dense topical baseline)
- ✅ Cache file persisted: `.dev-runtime/260606-bd-probe/embedding_cache.pkl` 1.85 MB, 150 entries (4 dirty unflushed — under 50-flush threshold)
- ✅ Vector integrity: shape `(3072,)`, dtype `float32`, L2-norm `1.0` (matches `_embed`'s post-normalization step)
- ❌ PASS B wall 0.003s **invalid** — same `lightrag.kg.shared_storage` module-singleton flaw documented in u17. `reset_storage()` rmtree's storage but doesn't clear `pipeline_namespace["busy"]`, so `initialize_pipeline_status()` short-circuits and "Duplicate document detected" → "No new unique documents to process" → no actual ingest. Real PASS B would need subprocess-per-pass (probe v3 territory)
- 🟡 True speedup ratio **NOT MEASURED** — upper bound = `cache_hit_ratio × vertex_call_share_of_wall`. With 77 entities/article and ~30% topical-overlap on dense KOL batches, **expected** 15-25% wall reduction on 2nd+ article in a same-cron batch. Real evidence comes from prod 09:00 ADT cron after the env flag flips on Aliyun (separate quick).

**Sanity proof of project_id mismatch (saved you SSH-Hermes-scp-SA roundtrip):**

First probe attempt failed 403 PERMISSION_DENIED. Root cause was env contamination — initial `GOOGLE_CLOUD_PROJECT="banded-totality-485901"` came from `~/.claude/CLAUDE.md` AI-Hero-Academy section, but the local SA `ohjch-sa@project-df08084f-6db8-4f04-be8.iam.gserviceaccount.com` belongs to OmniGraph project `project-df08084f-6db8-4f04-be8`. Re-fired with corrected env (read from `.dev-runtime/.env`) → green-path embed call (3072d). No SA scp from Hermes needed; SA was always present at `.dev-runtime/gcp-paid-sa.json`.

**Commits:**
- `1354a22` `feat(ingest): A2 — opt-in global cross-article embedding cache (#39)` — `lib/llm_cache_embedding_global.py` + `lib/lightrag_embedding.py` hook (2 files, 173 +1 lines)

---

## NOT-do red lines (all honored)

| Red line | Status |
|---|---|
| ❌ NOT 改 LightRAG 源 | ✅ untouched |
| ❌ NOT ship D 16/16/16 (撞 OOM) | ✅ HALTED at TASK 1 |
| ❌ NOT 触 Hermes / kb-api / qdrant-snapshot.timer | ✅ untouched |
| ❌ NOT --force / --amend / reset --hard | ✅ none used |
| ❌ NOT git add -A | ✅ explicit file lists only |
| ❌ NOT 触 batch_ingest_from_spider concurrent loop | ✅ untouched (v1.2 #40 territory) |
| ❌ NOT scp SA JSON 进 repo | ✅ existing `.dev-runtime/gcp-paid-sa.json` reused |

---

## What ships to prod tomorrow

**Auto** (next Aliyun `git pull` + service restart cycle):
- `b6f4a23` lifts default `OMNIGRAPH_PROCESSED_BACKOFF` 5.0 → 10.0 → effective budget 300s on every fresh ingest_wechat process even without `.env` override

**Opt-in** (no auto-enable, gated):
- `1354a22` ships A2 wrapper but `OMNIGRAPH_EMBEDDING_CACHE` env unset by default → byte-identical pre-A2 behavior

**Deferred to follow-up quick** (when SSH throttle clears):
- Aliyun `/root/.hermes/.env` explicit `OMNIGRAPH_PROCESSED_BACKOFF=10.0` override (belt-and-suspenders alongside repo default raise)
- Aliyun `OMNIGRAPH_EMBEDDING_CACHE=1` opt-in flip + first-day cron metrics review (cache file size growth + cache-hit-ratio observation)

---

## ISSUES.md updates (orchestrator-curated; for the close commit)

- **#39 row** — annotate "**A3 mitigation 2026-06-06 b6f4a23**: repo default `OMNIGRAPH_PROCESSED_BACKOFF` 5.0→10.0 (300s budget). **A2 mitigation 2026-06-06 1354a22**: opt-in cross-article embedding cache wrapper (default OFF; flip via `OMNIGRAPH_EMBEDDING_CACHE=1`). **Aliyun explicit `.env` override DEFERRED** — SSH throttled (#42-class) at quick close; orchestrator will apply when SSH clears."
- **#43 NEW row** — "Aliyun SSH cross-border throttle DURING `260606-bd` quick close — orchestrator could not apply the explicit `/root/.hermes/.env` `OMNIGRAPH_PROCESSED_BACKOFF=10.0` override. Same symptom class as #42 (banner timeout 15s/60s/120s/30s budgets all fail across ~45 min). Different trigger context — `qdrant-snapshot.timer` confirmed disabled (R-context vs #41), so no in-flight snapshot scroll OOM as the cause. Possible alternates: corp-side egress route hop / SLB rate-limit on this client IP / Aliyun-side scheduled maintenance. **Action:** retry SSH at next session start; if still throttled, file as a tracking row under #42 with the new trigger context. **No user impact** — `b6f4a23` repo default already provides the 300s budget once Aliyun does its next `git pull`."

(orchestrator will write these into ISSUES.md as part of the close-out commit.)

---

## STATE.md row (Quick Tasks Completed)

```
| 260606-bd-cache-async-quickwin | 2026-06-06 | A3 + A2 ship; B/D HALTED at TASK 1 (premises invalid) | b6f4a23 1354a22 |
```

---

## Time budget (vs plan)

| Phase | Plan | Actual | Notes |
|---|---|---|---|
| TASK 1 (source verify) | 15 min | ~10 min | source-read efficient |
| TASK 2 (D ship → A3 ship) | 15 min | ~5 min repo edit + ~5 min SSH retry-loop | SSH throttle ate retry budget |
| TASK 3 (B layer → A2 wrapper) | 60 min | ~25 min implement + 5 min smoke | clean wrapper design |
| TASK 4 (corp verify) | 30 min | ~3.5 min (PASS A 207s + setup) | first attempt failed env-contamination, second attempt clean |
| TASK 5 (close + commit) | 20 min | ~15 min | this doc + ISSUES + STATE |
| **Total** | **~2h 20min** | **~70 min** | under budget |

---

## Artifacts

- `260606-bd-TASK1-SURFACE.md` — premise-by-premise refutation + decision matrix
- This SUMMARY
- `lib/llm_cache_embedding_global.py` — wrapper (NEW, committed)
- `lib/lightrag_embedding.py` — hook + opt-in switch (modified, committed)
- `ingest_wechat.py` — A3 default raise (modified, committed earlier)
- `.scratch/260606-bd-cache-probe-vertex.py` — corp probe script (gitignored, kept for follow-up quicks)
- `.scratch/260606-bd-probe-output.txt` — probe stdout JSON dump
- `.dev-runtime/260606-bd-probe/embedding_cache.pkl` — 1.85 MB persisted cache (corp-local sandbox; not pushed)

---

## Commits

| Commit | What | Files |
|---|---|---|
| `b6f4a23` | A3: `OMNIGRAPH_PROCESSED_BACKOFF` default 5.0→10.0 | `ingest_wechat.py` |
| `1354a22` | A2: opt-in global embedding cache wrapper | `lib/llm_cache_embedding_global.py` + `lib/lightrag_embedding.py` |

(this SUMMARY + ISSUES + STATE updates land in a third docs commit, no prod-code touch.)
