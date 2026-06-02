---
phase_set: kb-v2.2-translation-and-kg-search
created: 2026-05-17
authored_by: orchestrator from 2026-05-17 evening user-orchestrator alignment session + overnight Aliyun storage stale-snapshot discovery
status: ready-to-execute
ceremony: skipped — direct phase plans, no /gsd:new-milestone / discuss-phase / roadmapper (parallel-track suffix files; gsd-tools.cjs init does not parse PROJECT-KB-v2.md / ROADMAP-KB-v2.md / STATE-KB-v2.md, so init returns phase_found=false; orchestrator hand-drives setup per memory `feedback_parallel_track_gates_manual_run.md`)
---

# kb-v2.2 — Translation + KG Search + Storage Sync + Citation/Image — Input

## Source

2026-05-17 evening user-orchestrator session locked the v2.2 scope: bidirectional
article translation (F1'), KG search promoted to default (F8'), Hermes → Aliyun
`lightrag_storage` sync mechanism (F12), citation URL format + image injection
(FU-1), plus two hygiene phases (F5 test-isolation autouse, F6 SSG data-lang
regularization) and one optional cleanup (F10 hash collision id=731).

The 2026-05-17 night Aliyun debug session surfaced a critical empirical finding
that reshaped the milestone: Aliyun's `lightrag_storage` is a **2026-05-08 stale
snapshot** (graphml mtime), and Hermes current data is **~3.9× larger**:

| Metric | Aliyun (stale 2026-05-08) | Hermes (current) | Ratio |
|---|---|---|---|
| Articles with image refs | 44 | 172 | 3.9× |
| Image URLs in chunks | 1189 | 4603 | 3.9× |
| Sub-doc descriptions | 460 | 1789 | 3.9× |

Without F12 sync, F8' KG search quality + FU-1 image-rich answers are **bounded
by ~25% of Hermes content**. F12 was promoted from "optional later" to **P0
prereq blocking Wave 2**.

This INPUT.md is the canonical scope-locking record; the agent does NOT need to
re-discuss scope. Subsequent `/gsd:plan-phase kb-v2.2-N` invocations consume
this document.

## Phases (7 in-scope + F9 already shipped)

| # | Phase | Feature | REQ source | Priority | Dependencies | T-shirt |
|---|---|---|---|---|---|---|
| **(F9)** | _Aliyun KG mode enable_ | F9 | post-go-live ops | — | systemd override + GCP creds + /etc/hosts oauth pin | ✅ **DONE 2026-05-17 night** |
| 1 | F12 storage sync | F12 | tonight's stale-snapshot discovery | **P0 — Wave 2 prereq** | — | 1-1.5d |
| 2 | F1' bidirectional translation | F1' | 2026-05-17 user decision (zh ↔ en) | P1 — flagship 主题 1 | DB migration; reuses i18n button pattern | 1.5-2d |
| 3 | F8' KG search default | F8' | 2026-05-17 user decision (no keyword search) | P1 — search quality | F12 sync (storage parity); existing `/api/search?mode=kg` | 1.5-2.5d |
| 4 | FU-1 citation + image | FU-1 | tonight's long_form `confidence=no_results` bug | P1 — UX correctness | F12 sync (image URL parity); kg_synthesize prompt change | 1-1.5d |
| 5 | F5 test-isolation autouse | F5 | hygiene from v2.1 backlog | P2 — test cleanliness | — | 1-2h |
| 6 | F6 SSG data-lang regularization | F6 | hygiene from v2.1 backlog | P2 — i18n cleanliness | — | 0.5h |
| 7 | F10 hash collision cleanup _(optional)_ | F10 | id=731 known dup | P3 — opportunistic | optional, alongside F1' DB migration | 0.5d |

Total in-scope estimate: **7-10 days**. F9 already shipped (no plan needed).

## Wave / parallelization

- **Wave 1 (parallel, no deps):**
  - kb-v2.2-1 F12 sync (P0 prereq for Wave 2)
  - kb-v2.2-5 F5 test-isolation (1-2h hygiene)
  - kb-v2.2-6 F6 data-lang regularization (0.5h hygiene)
- **Wave 2 (after F12 ships):**
  - kb-v2.2-2 F1' bidirectional translation
  - kb-v2.2-3 F8' KG search default _(parallel with -2)_
  - kb-v2.2-4 FU-1 citation + image _(after -3 settles, audit-cycle parallel possible)_
- **Wave 3 (optional):**
  - kb-v2.2-7 F10 hash collision cleanup (alongside F1' DB migration if convenient)

F1' and F8' touch different layers (F1' = DB schema + translation service; F8' =
search routing + dedup) and can run concurrently with explicit-file `git add`
discipline (per `feedback_git_add_explicit_in_parallel_quicks.md`).

## Out-of-scope for v2.2 — **CUT-FINAL** (not "deferred")

User decisions 2026-05-17 evening, explicitly closed forever (not "maybe v2.3"):

| Cut item | Rationale | Status |
|---|---|---|
| **F2 en→zh 单独 phase** | 合并进 F1' bidirectional (对称简化) | merged into F1' |
| **F3 跨语言搜索** | User decision: 翻译目的只为阅读,不需要跨语言 search | CUT-FINAL |
| **F4 跨语言 Q&A** | User decision: 同上 | CUT-FINAL |
| **F11 Path B DeepSeek-only long_form** | Violates `feedback_lightrag_is_core_asset_no_bypass` — LightRAG 是 substrate,deployment 友好性问题用 fix infra(F12 sync + memory monitoring)解决,不绕开 | replaced by F12 |
| **F7 11 B4 prod-drift xfail items** | 4-7d 散修;each needs domain decision;不 batch。Move to v2.2.x quick set,各自 0.5-1d 单点 triage | → v2.2.x quicks |
| **Long-form UX: Preview** | No speculative product features without user signal | CUT-FINAL |
| **Long-form UX: Save** | Same | CUT-FINAL |
| **Long-form UX: Export** | Same | CUT-FINAL |
| **Long-form UX: Versioning** | Same | CUT-FINAL |
| **Dedicated `/kb/research/` page** | Same | CUT-FINAL |
| **Image curation UI** | Same | CUT-FINAL |
| **Citation-rich (footnotes / endnotes / bibliography)** | Same | CUT-FINAL |

Also out of scope (existing v2.1 boundary, unchanged):

- HTTPS/TLS, ingest cron migration, Hermes retire — v2.3+ if ever
- Databricks Apps deployment — kdb-* track (parallel)
- Auth, multi-tenancy, admin features — out of v2.x entirely

## Architectural choices (locked)

- **LightRAG hybrid mode native for KG search** — `omnigraph_search.query.search`
  already wraps LightRAG hybrid (entity + relation merge). F8' promotes this
  path to default `/api/search?mode=kg` and removes FTS5 user-facing fallback;
  FTS5 retained as `/admin` debug entry only.
- **Sync cadence weekly for F12** — one-time ~1.3GB initial transfer + delta
  thereafter. Cross-border path: **Hermes → Windows dev → Aliyun (双跳)**
  because direct Hermes→Aliyun is unreliable through GFW. Stop-rsync-cgroup-
  verify-start protocol; ~2 min downtime per sync.
- **Bidirectional translation as columns on `articles` table for F1'** —
  `body_translated` + `title_translated` + `translated_lang` + `translated_at`
  columns, NOT a separate `article_translations` table. Reads stay single-row.
- **DATA-07 filter applies to translations** — only quality-passed articles
  get translated (no wasted LLM cost on filtered-out content).
- **KG_MODE_AVAILABLE=False → 503 + retry_after** for F8', NOT FTS5 fallback
  (per user 2026-05-17 "no keyword search").
- **Cgroup memory budget monitoring as part of F12** — vdb continues to grow;
  current `MemoryMax=2.5G` is near ceiling with full Hermes vdb at ~1.3GB.
  Phase plan must include monitoring hooks + alert threshold.
- **`/article/{hash}.html` URL citation enforcement in kg_synthesize prompt**
  for FU-1 — currently emits Chinese "(来源:Entity X 描述)" which wrapper
  regex can't extract. Fix prompt template + extend wrapper regex (optional
  Chinese fallback with entity-name lookup).

## Inheritance

All phases inherit:

- `kb-1-UI-SPEC.md` + `kb-2-UI-SPEC.md` + `kb-3-UI-SPEC.md` design tokens (ZERO new `:root` vars)
- C1 contract (`kg_synthesize.synthesize_response`) — F8' and FU-1 may extend prompt template but signature stays
- C2 contract (`omnigraph_search.query.search`) — F8' may add `score` field surface but signature stays
- C3 contract (`kol_scan.db` schema) — F1' adds new columns (additive non-breaking, same pattern as kb-1 lang column)
- C4 contract (`images/{hash}/final_content.md` path) — read-only

## Skill discipline

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 — Skills are tool calls, not reading
material (memory `feedback_skill_invocation_not_reference.md`).

Mandatory floors per phase (planner agent MUST emit literal `Skill(skill="...")`
tool calls in PLAN.md):

- **kb-v2.2-1 (F12 sync):** `databricks-patterns` (n/a — Aliyun not Databricks; substitute `python-patterns` for SDK / cgroup ops) + `writing-tests` + `security-review` (credential / SSH / cgroup paths)
- **kb-v2.2-2 (F1' translation):** `python-patterns` + `writing-tests` + `database-migrations` (additive columns + backfill strategy)
- **kb-v2.2-3 (F8' KG search):** `python-patterns` + `writing-tests` + `api-design` (503 contract + retry_after header)
- **kb-v2.2-4 (FU-1 citation + image):** `python-patterns` + `writing-tests` + `frontend-design` (UI surfacing of corrected citation URLs / inline images)
- **kb-v2.2-5 (F5 test-isolation):** `python-testing` + `refactoring-code` (autouse fixture extraction)
- **kb-v2.2-6 (F6 data-lang):** `frontend-design` + `writing-tests` (zh→zh-CN unification)
- **kb-v2.2-7 (F10 hash collision):** `database-migrations` + `writing-tests`

## Pre-execution requirements

- **Wave 1 (F12) blocks Wave 2.** Do not start kb-v2.2-2/3/4 plans until F12
  sync runs successfully end-to-end at least once with cgroup MemoryMax bumped
  to accommodate full Hermes vdb (~1.3GB → likely 3.5G ceiling).
- **F9 (Aliyun KG mode enable)** already in place on prod (systemd override +
  GCP creds + /etc/hosts oauth pin per memory `aliyun_oauth_pin.md`). Verified
  2026-05-17 night. No plan needed.
- **Hermes → Windows dev dataflow path** must be validated before F12
  cross-border phase (existing rsync test from Hermes to Windows is sufficient
  for sanity).
- **F1' translation provider choice** — locked to existing `lib/llm_complete.py`
  dispatcher (DeepSeek / Vertex Gemini per env var). No new provider integration
  in v2.2.

## Verification convention (Rule 3 — local UAT mandatory)

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 3 + memory `feedback_kb_local_uat_mandatory.md`,
every phase MUST run local UAT via `.scratch/local_serve.py` against
`.dev-runtime/` before declaring complete. Browser smoke at desktop + mobile.
Capture screenshots into `.playwright-mcp/` with phase-specific filename
prefixes.

For F12 specifically, local UAT also covers:

- Aliyun staging sync dry-run (rsync `--dry-run`) capturing diff size
- cgroup memory ceiling verification under full vdb load
- KG search smoke at `/api/search?mode=kg` returning ~3.9× more image-bearing
  articles post-sync

## Concurrent-quick discipline (CRITICAL)

Per `feedback_no_amend_in_concurrent_quicks.md` + `feedback_git_add_explicit_in_parallel_quicks.md`:

- **NO `git commit --amend`** — forward-only follow-up commits to backfill
  hashes into STATE.md
- **NO `git reset --hard` / `--soft` / `--mixed`** — staging area is shared
  across concurrent agents on main checkout
- **NO `git rebase -i`** — same reason
- **NO `git push --force` / `--force-with-lease` to main**
- **NO `git add -A` / `git add .`** — concurrent quicks may have staged
  sibling artifacts; absorb-collision is silent and corruptive
- Use `git add <explicit-files>` only

Possible concurrent territories during v2.2 milestone:

- kdb-2 Wave 3 deploy + UAT (different files: `databricks-deploy/*`, `.planning/phases/kdb-*`)
- v2.2.x quick set散修 (from F7 11 B4 prod-drift items, post-Wave-1)

## Authors

- Original v2.2 scope: 2026-05-17 evening user-orchestrator session (canonical record in this INPUT.md)
- Phase decomposition + cuts: orchestrator, 2026-05-18
- Critical empirical finding (Aliyun stale snapshot): user + orchestrator night debug, 2026-05-17

## Source spec references

- 2026-05-17 user-orchestrator alignment session (this INPUT.md is the canonical record)
- `.planning/phases/kb-v2.1-stabilization/INPUT.md` (structural template)
- `.planning/phases/kb-v2.1-stabilization/DEFERRED.md` (existing deferred list — updated to CUT-FINAL alongside this open)
- Memory entries baked: `aliyun_oauth_pin.md`, `feedback_lightrag_is_core_asset_no_bypass.md`, `aliyun_vitaclaw_ssh.md`, `feedback_parallel_track_gates_manual_run.md`, `feedback_skill_invocation_not_reference.md`, `feedback_kb_local_uat_mandatory.md`, `feedback_no_amend_in_concurrent_quicks.md`, `feedback_git_add_explicit_in_parallel_quicks.md`
- Project rules: `CLAUDE.md` Principle 5 (don't outsource SSH/mechanical work) + Principle 6 (KB local UAT mandatory)
