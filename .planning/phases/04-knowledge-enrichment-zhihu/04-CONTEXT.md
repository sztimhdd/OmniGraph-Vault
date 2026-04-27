# Phase 4: knowledge-enrichment-zhihu - Context

**Gathered:** 2026-04-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Insert a mandatory knowledge enrichment step between WeChat scrape and LightRAG
ingestion. For each WeChat article: extract 1–3 unanswered technical questions,
drive Zhihu 好问 (zhida.zhihu.com) per question to get an AI summary + best-cited
source URL, fetch that Zhihu source article (text + images), then ingest the
enriched WeChat MD plus 3 standalone Zhihu answer docs into LightRAG. Image
handling is refactored out of `ingest_wechat.py` into a shared `image_pipeline.py`
used by both paths.

**In scope:**
- `enrichment/` package: extract_questions, fetch_zhihu, merge_md, orchestrate helpers
- `image_pipeline.py` refactor (shared by WeChat + Zhihu paths)
- `skills/zhihu-haowen-enrich/` Hermes skill (CDP-driven Zhihu AI search)
- Top-level Hermes skill that owns the per-article enrichment loop
- `articles.enriched` + `ingestions.enrichment_id` SQLite migration
- Phase-0 LightRAG delete-by-id + re-ainsert spike (for retry paths)
- Telegram-based Zhihu login recovery UX

**Out of scope (belongs elsewhere):**
- Sources other than Zhihu (e.g., X/Twitter, HN, blogs)
- Review UI for enriched articles
- Scheduled re-enrichment of already-enriched articles
- Generalizing the bridge pattern for other Hermes skills
</domain>

<decisions>
## Implementation Decisions

### Orchestration model — Hermes drives

- **D-01:** Top-level orchestration lives in a **new Hermes skill** (working
  name: `enrich_article` or `omnigraph_enrich`), not in Python. The skill's
  Markdown body contains the per-question for-loop. Python helpers are pure
  deterministic subprocesses with no Hermes calls. This eliminates the
  Python→Hermes bridge problem entirely.
- **D-02:** Per-question loop is owned by the **Hermes skill body in Markdown**.
  For each question, Hermes invokes `zhihu-haowen-enrich` natively, then shells
  to `python enrichment/fetch_zhihu.py`, accumulates results, and finally calls
  `python enrichment/merge_and_ingest.py`.
- **D-03:** Contract between Hermes and Python helpers: **single-line JSON on
  stdout for small metadata + control flow, large artifacts (MDs, image dirs)
  written to disk at predictable paths under
  `~/.hermes/omonigraph-vault/enrichment/<article_hash>/<q_idx>/`**. Non-zero
  exit + stderr on failure. Matches Hermes's documented subprocess pattern and
  stays under the 50KB stdout truncation cap.

### Where it runs

- **D-04:** Everything in the enrichment path runs on the **remote WSL host**
  (connection details in `~/.claude/projects/.../memory/hermes_ssh.md` —
  never commit hostnames/ports/usernames to this public repo), co-located with
  Hermes, CDP, and the repo. The dev machine is edit-only.
- **D-05:** Dev loop is **git push (Windows) → git pull (remote)**, done via a
  one-line helper (e.g., `./deploy.sh` that runs
  `ssh remote 'cd OmniGraph-Vault && git pull'`). Phase 4 adds this helper.
- **D-06:** No local testability of the enrichment pipeline — every validation
  (unit tests, golden-file diffs, skill runs) happens on the remote. CI is
  `ssh remote 'cd OmniGraph-Vault && pytest tests/...'`.

### LightRAG structure

- **D-07:** **Enrichment is mandatory** for every WeChat article. Articles
  below 2000 chars still skip question extraction (enriched=-1) and ingest
  un-enriched. Articles where all 3 好问 attempts fail (enriched=-2) ingest
  un-enriched and remain eligible for retry. There is no un-enriched article
  that later gets "upgraded" on a happy path — enrichment runs on first
  ingest or not at all. **PRD section 12 Phase 5 `--enrich` flag is
  superseded**: enrichment is default-on and not flagged.
- **D-08:** The 3 Zhihu answers are ingested as **independent LightRAG docs**
  with metadata `enriches=<wechat_article_hash>`. Hybrid retrieval naturally
  surfaces the parent + children when queried.
- **D-09:** The 3 好问 AI summaries are appended inline to the enriched WeChat
  MD (per PRD section 4 rationale) and ingested as part of that MD — not as
  separate LightRAG docs.
- **D-10:** Re-enrichment of `enriched=-2` articles requires delete-by-id +
  re-ainsert. This path is not exercised in Phase 4 happy path but must be
  **feasible**, so the Phase-0 spike (D-14) is still mandatory.

### Failure handling

- **D-11:** Partial failure (≥1 question succeeds, others fail) → `enriched=2`
  for the article. Failed questions are **abandoned, not retried per-question**
  (PRD section 9 policy stands). No per-question retry state table. If the
  article needs more enrichment later, it gets a full re-enrichment pass.

### LLM selection

- **D-12:** `extract_questions` uses **Gemini 2.5 Flash Lite with Google
  Search grounding enabled** (`google_search` tool). Reasoning: grounding
  lets the LLM avoid picking questions that are already well-covered on the
  public web, so the 好问 step spends its budget on genuinely under-documented
  gaps. Reuses existing `GEMINI_API_KEY`. **PRD section 8's
  `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"` is superseded.**

### Zhihu login recovery

- **D-13:** When the skill detects a Zhihu login wall, it **captures a
  screenshot of the login QR code and sends it to the user's Telegram bot**
  (reusing FR-20 delivery infra). User scans with Zhihu mobile app to
  re-authenticate remote Edge. Skill retries after user replies `/resume` (or
  equivalent). This turns a hard-fail into a graceful bounce.

### Image pipeline refactor

- **D-14 (Phase-0 spike):** Before Phase 1 coding, verify LightRAG
  **delete-by-id + re-ainsert** on one real article on remote. Must
  confirm: entities removed cleanly, no orphaned nodes, re-ainsert produces
  the expected updated doc. If delete API is broken/missing, escalate before
  planning continues.
- **D-15:** `image_pipeline.py` exposes **batch-style**
  `describe_images(paths: list[str]) → dict[path, description]`. Callers
  (WeChat + Zhihu) pass all images at once; rate-limiting (the existing 4-second
  inter-image sleep at `ingest_wechat.py:640`) lives inside the pipeline module.
- **D-16:** Regression gate for image_pipeline refactor is **golden-file diffs
  + pytest unit tests**:
  - Golden-file: pick 2-3 already-cached WeChat articles
    (`~/.hermes/omonigraph-vault/images/<hash>/final_content.md` exists), run
    `ingest_wechat.py` with cache disabled, diff new vs saved `final_content.md`
    and `metadata.json`. Required: identical structure, same image count, same
    local URLs. Image descriptions may drift by up to a line (Gemini
    non-determinism); explicitly tolerate that in the diff.
  - Unit tests: one test module per extracted function (`download_images`,
    `localize_markdown`, `describe_images`, `save_markdown_with_images`).
  - Both must pass before `image_pipeline.py` is merged. The refactor PR
    touches `ingest_wechat.py`, so regression green-light is a **merge
    prerequisite**.

### Claude's Discretion

- Exact CLI argument shapes for Python helpers
- File names inside `~/.hermes/omonigraph-vault/enrichment/<hash>/<q_idx>/`
- Exact SQLite migration sequencing (one ALTER per commit vs batch)
- Python helper module internal structure
- Golden-file article selection (pick any 2-3 that have complete cache)
- Where the Telegram QR screenshot code lives (new util vs extend existing)
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product spec
- `docs/enrichment-prd.md` — full PRD, the source of truth. Note the
  supersessions called out in D-07 (mandatory enrichment, no `--enrich` flag)
  and D-12 (Gemini Flash Lite not DeepSeek).

### Project context
- `CLAUDE.md` — project rules, typo'd data dir, highest-priority principles
- `specs/PRD_TDD.md` v1.3 — current product state (FR-20 Telegram delivery,
  FR-5 LightRAG indexing, FR-4 Gemini Vision)
- `.planning/PROJECT.md` — phase constraints, privacy posture

### Code touch points
- `ingest_wechat.py` lines 125-135 (`describe_image`), 614-651 (image loop),
  704-716 (SQLite update after ingest) — refactor targets
- `config.py` — new config keys land here
- `batch_scan_kol.py` lines 87-115 — existing `articles` and `ingestions`
  CREATE TABLE, schema basis for the two ALTER TABLE statements
- `skills/omnigraph_ingest/scripts/ingest.sh` — existing pattern for
  skill-script shell wrappers (venv activation, env sourcing, arg validation)
- `skills/hermes_claude_code_bridge/SKILL.md` — nearest precedent for
  orchestration-in-Markdown, useful as style reference (but the
  reverse direction of what we're doing)

### Hermes docs (read during planning)
- `https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills`
  — skill structure, `required_environment_variables`, template vars like
  `${HERMES_SKILL_DIR}`, inline `` !`cmd` `` snippets, no-external-deps guideline
- `https://hermes-agent.nousresearch.com/docs/guides/automate-with-cron` —
  the "script stdout becomes agent context" pattern we're adopting (D-03)
- `https://hermes-agent.nousresearch.com/docs/user-guide/configuration/` —
  `tool_output.max_bytes: 50000` cap; confirms why we can't put full MDs on
  stdout
- `https://hermes-agent.nousresearch.com/docs/user-guide/features/skills` —
  skill discovery and `skills.external_dirs` (remote already points at
  `$HOME/OmniGraph-Vault/skills` on the remote WSL host)

### Deferred docs to locate/create during research
- Zhihu 好问 UI structure reference — no canonical doc exists; skill body
  must capture the 10-step flow empirically (PRD section 7)
- LightRAG delete-by-id API reference — confirm in `venv/Lib/site-packages/lightrag`
  during Phase-0 spike
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`describe_image(path)`** at `ingest_wechat.py:125-135` — move into
  `image_pipeline.describe_images` as batch form
- **Per-image download+describe loop** at `ingest_wechat.py:614-651` —
  split into `download_images`, per-image rate-limit, `describe_images`
- **`process_content(html)`** at `ingest_wechat.py:484-496` (BS4 +
  html2text) — unchanged; stays in `ingest_wechat.py` since it's WeChat-HTML
  specific
- **Article cache skip** at `ingest_wechat.py:522-556` — the enrichment
  pipeline must respect this (cached article → skip scrape but still enrich
  if `enriched=0`)
- **`_persist_entities_to_sqlite`** at `ingest_wechat.py:49-67` — pattern
  for SQLite write with failure tolerance; enrichment status updates should
  follow this shape
- **`cognee_wrapper.remember_article`** at `ingest_wechat.py:676-683` —
  called fire-and-forget after LightRAG insert; enriched ingest should do
  the same for both the enriched WeChat MD and the 3 Zhihu docs
- **`skills/omnigraph_ingest/scripts/ingest.sh`** — shell wrapper pattern
  (OMNIGRAPH_ROOT, venv activation, env source from `~/.hermes/.env`, cd to
  project root); enrichment scripts follow this pattern

### Established Patterns
- **Async fast-path discipline** (NFR-1, NFR-2): ingestion must stay under
  200ms for the synchronous portion. Enrichment is NOT in the fast path —
  it's a pre-ingest synchronous step that precedes LightRAG `ainsert`.
  Time budget: PRD section 8 caps 好问 at 120s/question, Zhihu fetch at
  60s/question. 3 questions × 180s = up to 9 minutes per article. This is
  acceptable because enrichment is not on the user's query-response path.
- **SQLite dual-write + file fallback** (Phase 2 entity migration) —
  enrichment status writes follow the same pattern: SQLite primary,
  file-based fallback not required here since enriched state is ephemeral
  within a single ingestion run.
- **Atomic writes** (CLAUDE.md) — `canonical_map.json` uses tmp→rename.
  Any new JSON files under `enrichment/<hash>/` must use the same pattern.
- **Telegram delivery via existing bot** (FR-20) — D-13 reuses this for
  Zhihu login QR delivery. Bot credentials already in `~/.hermes/.env`.

### Integration Points
- **SQLite `articles` + `ingestions` tables** — migration adds `enriched`
  and `enrichment_id` columns. `batch_scan_kol.py` owns the CREATE TABLE;
  migration script goes into a new `migrations/` dir or inline in
  `batch_scan_kol.py`.
- **LightRAG storage at `~/.hermes/omonigraph-vault/lightrag_storage/`** —
  delete-by-id + re-ainsert hits this store.
- **Image server on port 8765** — enriched MD (WeChat + Zhihu) uses
  `http://localhost:8765/<hash>/<i>.jpg` URLs. Image server already runs.
  Zhihu image hashes must not collide with WeChat hashes (namespace under
  `<article_hash>/zhihu_<q_idx>/` to avoid cross-article collisions).
- **`config.py`** — new keys go here, not scattered. Enrichment config keys
  per PRD section 8, but `ENRICHMENT_LLM_MODEL` changes to Gemini (D-12)
  and `ENRICHMENT_ENABLED` defaults to True with no flag path (D-07).

</code_context>

<specifics>
## Specific Ideas

- **Telegram QR login rescue** is load-bearing for D-13 — the flow is:
  skill detects login wall → `browser_cdp` screenshot → upload screenshot via
  existing Telegram bot → wait for user `/resume` → retry skill. The skill
  owns this flow entirely (not a Python helper).
- **"Hermes drives" for this phase only** — D-01's inversion is scoped to
  enrichment. It does NOT imply other pipelines should flip. WeChat scraping
  stays Python-led; the `omnigraph_ingest` skill stays a thin shell wrapper.
- **Mandatory enrichment = default-on** — no `--enrich` flag. If a user
  wants to skip enrichment for a specific article (debugging), they invoke
  `ingest_wechat.py` directly and bypass the top-level Hermes skill.
</specifics>

<deferred>
## Deferred Ideas

### Not this phase
- **Per-question retry state table** (SQLite `enrichment_questions`) —
  considered and rejected for Phase 4 (D-11). If retry granularity becomes
  necessary, a follow-up phase can add the table and a retry batch job.
- **Scheduled nightly re-enrichment** of `enriched=-2` or `enriched=0` legacy
  articles — legacy because existing pre-Phase-4 articles are un-enriched.
  Backfill is a separate phase.
- **Sources beyond Zhihu** (X threads, HN comments, blog posts) — out of
  scope; Phase 4 is Zhihu 好问 only.
- **Review UI** to manually approve/reject enrichment results before ingest
  — out of scope; Phase 4 is automatic.
- **Generalized Python↔Hermes bridge** (HTTP API or CLI) — not needed given
  D-01 inversion. If future phases need Python to call Hermes, that's a
  dedicated infrastructure phase.
- **DeepSeek v4 Pro for extract_questions** — considered (better reasoning
  quality, matches Hermes primary) but not chosen because grounding matters
  more than raw quality for this task.
- **Cookie-export-based Zhihu session** — considered (no re-login needed
  over weeks) but rejected for brittleness when Zhihu rotates session format.

### PRD inconsistencies surfaced during discussion
- PRD section 5.3 test file #14 references `ingest_enriched.py` as a test
  target, but section 5.1 deliverables doesn't list `ingest_enriched.py` as
  a new file to create. Section 12 Phase 4 lists it. The planner should
  treat `ingest_enriched.py` (or equivalent merge-and-ingest helper) as a
  new file to create, and the PRD deliverables table is incomplete.
- PRD section 6.1 `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"` is superseded
  by D-12 (Gemini 2.5 Flash Lite + grounding).
- PRD section 12 Phase 5 `--enrich` flag is superseded by D-07 (mandatory,
  no flag).
- PRD implicitly assumes a Python→Hermes bridge via `call_hermes_skill()`
  but never specifies the mechanism. D-01 resolves this by inverting control.
</deferred>

---

*Phase: 04-knowledge-enrichment-zhihu*
*Context gathered: 2026-04-27*
