# Phase 4: knowledge-enrichment-zhihu — Research

**Researched:** 2026-04-27
**For:** `/gsd:plan-phase 4`
**Confidence:** HIGH (repo-grounded + remote SSH probe 2026-04-27 resolved the 2 MEDIUM-confidence items; only D-14 LightRAG orphan-cleanup spike remains as a Phase-0 implementation blocker)

## RESEARCH COMPLETE

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01** Top-level orchestration in a new Hermes skill (`enrich_article` / `omnigraph_enrich`). Python helpers are pure deterministic subprocesses; no Python→Hermes bridge.
- **D-02** Per-question for-loop lives in the Hermes skill body (Markdown). For each question the skill invokes `zhihu-haowen-enrich` natively, then shells to `python enrichment/fetch_zhihu.py`, accumulates results, and calls `python enrichment/merge_and_ingest.py`.
- **D-03** Contract = **one-line JSON on stdout** (small metadata + control flow, <50KB cap per Hermes `tool_output.max_bytes`) + large artifacts on disk at `~/.hermes/omonigraph-vault/enrichment/<article_hash>/<q_idx>/`. Non-zero exit + stderr on failure.
- **D-04..D-06** Everything runs on remote WSL (`ohca.ddns.net:49221`). Dev loop = git push (Windows) → `ssh remote 'cd OmniGraph-Vault && git pull'`. No local testability of the enrichment pipeline. CI = `ssh remote 'pytest tests/...'`.
- **D-07** Enrichment is **mandatory and default-on** (no `--enrich` flag). `articles.enriched`: 0=pending, 1=in-progress, 2=success (including partial ≥1 question), -1=skipped (<2000 chars), -2=all 3 failed. **Supersedes PRD §12 Phase 5 `--enrich` flag.**
- **D-08** 3 Zhihu answers = independent LightRAG docs with metadata `enriches=<wechat_article_hash>`.
- **D-09** 3 好问 AI summaries appended inline to the enriched WeChat MD tail; ingested as part of that MD, not as separate docs.
- **D-10** Re-enrichment requires delete-by-id + re-ainsert. Not on Phase-4 happy path but must be feasible → Phase-0 spike mandatory.
- **D-11** Partial failures abandoned, not retried per-question. No per-question retry state table.
- **D-12** `extract_questions` uses **Gemini 2.5 Flash Lite + `google_search` grounding tool**, reusing `GEMINI_API_KEY`. **Supersedes PRD §6.1/§8 `deepseek-v4-flash`.**
- **D-13** Zhihu login wall → skill screenshots QR → sends via Telegram bot → waits `/resume` → retries.
- **D-14** **Mandatory Phase-0 spike**: LightRAG `adelete_by_doc_id` + re-`ainsert` on one real article on remote. Must confirm clean entity removal, no orphans, re-insert produces expected doc.
- **D-15** `image_pipeline.describe_images(paths) → dict[path, description]` is batch. Rate-limit (4s inter-image sleep) lives inside the module.
- **D-16** Image-pipeline refactor regression gate = golden-file diffs **and** pytest unit tests. Both required before merge.

### Claude's Discretion
- Exact CLI shapes for Python helpers
- File names inside `~/.hermes/omonigraph-vault/enrichment/<hash>/<q_idx>/`
- Migration sequencing (one ALTER per commit vs batched)
- Helper module internal structure
- Which 2–3 golden-file articles to select (any with complete cache)
- Where the Telegram QR screenshot code lives (new util vs existing module)

### Deferred Ideas (OUT OF SCOPE)
- Per-question retry state table
- Scheduled nightly re-enrichment
- Sources beyond Zhihu (X/HN/blogs)
- Review UI for enrichments
- Generalized Python↔Hermes bridge
- DeepSeek v4 Pro for question extraction
- Cookie-export-based Zhihu session

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01/D-02 Hermes skill orchestration | Top-level skill owns loop; Python helpers are subprocesses | §1 Hermes Skill Orchestration |
| D-03 stdout-JSON + disk-artifact contract | Hermes 50KB cap enforces this split | §1 cheat-sheet, §7 artifact layout |
| PRD §7 Zhihu 好问 10-step flow | React SPA + Draft.js; selector strategy needed | §2 |
| D-10/D-14 LightRAG delete+re-ainsert | Confirm API surface before planning | §3 |
| D-12 Gemini Flash Lite + grounding | Replaces DeepSeek; need minimal working snippet | §4 |
| D-13 Zhihu login recovery via Telegram | Reuses FR-20 delivery | §5, §6 |
| PRD §5.1/§6.5 image_pipeline refactor | Extract from `ingest_wechat.py` | §7 |
| PRD §4 SQLite migration | `articles.enriched` + `ingestions.enrichment_id` | §8 |
| PRD §8 config keys | Consolidated post-supersession list | §9 |
| Nyquist validation | Unit/Integration/E2E split given D-06 constraint | §10 |

## Executive Summary

1. **Hermes skill-to-skill invocation is agent-native via `skill_view()` + `/skill-name`** (resolved via remote SSH probe 2026-04-27). `~/.hermes/hermes-agent/tools/skills_tool.py:846` registers `skill_view(name, file_path=None)` as an agent tool; `~/.hermes/hermes-agent/agent/skill_commands.py:306,332` resolves `/skill-name` as user-style invocation. D-01/D-02 are viable as specified: top-level `enrich_article` Markdown body instructs Hermes to call `/zhihu-haowen-enrich` per question in a prose loop; child skill writes results to disk at D-03 path; outer skill resumes with Python subprocess calls. See §1 for the full operational model.
2. **LightRAG delete API exists and is well-specified.** `adelete_by_doc_id(doc_id, delete_llm_cache=False) → DeletionResult` at `venv/Lib/site-packages/lightrag/lightrag.py:3223`. Returns `status ∈ {"success","not_found","not_allowed","fail"}`, `status_code`, `doc_id`, `message`, `file_path`. Pipeline concurrency guard included. `ainsert(input, ids=..., file_paths=..., track_id=...)` supports passing deterministic `ids` — this is how D-08 metadata `enriches=<hash>` should be encoded (via `file_paths` or synthetic `ids=f"zhihu_{wechat_hash}_{q_idx}"`). **Phase-0 spike D-14 remains required to confirm orphan handling in practice.**
3. **Gemini 2.5 Flash Lite + `google_search` grounding is trivially callable** from the installed `google-genai` SDK — `types.GoogleSearch()` is a zero-arg tool; wrap in `types.Tool(google_search=...)`, pass via `config=types.GenerateContentConfig(tools=[...])`. Model ID confirmed in repo: `gemini-2.5-flash-lite` (already used in `ingest_wechat.py:130` and `:515`). Grounding metadata (citations, `grounding_chunks`) appears in `response.candidates[0].grounding_metadata`.
4. **Telegram delivery ships with Hermes itself — no new code required for D-13** (resolved via remote SSH probe 2026-04-27). `~/.hermes/.env` has `TELEGRAM_BOT_TOKEN`; `~/.hermes/hermes-agent/tools/send_message_tool.py:143` exposes `send_message` as an agent tool; `MEDIA:<local_path>` in the message body attaches a file natively via `send_photo` (low-level at `gateway/platforms/telegram.py:1796`). Default chat resolves via existing FR-20 delivery target. `zhihu-haowen-enrich` skill body just instructs Hermes: "screenshot QR to `$QR_PATH`, then call `send_message` with `MEDIA:$QR_PATH\n\n<message>`, then wait for `/resume`". See §6.
5. **SQLite migration has pre-existing drift.** `batch_scan_kol.py:87-115` CREATE TABLE for `articles` does **not** include `content_hash` — but the live DB on remote already has the column (confirmed by prior researcher; manual ALTER was run and never backfilled into the CREATE). Phase 4 must (a) add `enriched` and `enrichment_id` columns via runtime ALTER, and (b) backfill `content_hash` into the CREATE TABLE statement for new installs. Recommended approach: inline idempotent migration at `batch_scan_kol.py` startup (matches current codebase convention) rather than a separate `migrations/` dir.
6. **Zhihu 好问 selector strategy must be text/role-based, not CSS.** The PRD §11.3 explicitly calls out Draft.js + React Router + auto-generated class hashes. The skill body should instruct Hermes using semantic prompts ("find the search input field", "click the button labelled '全部来源'") and only fall back to specific selectors when empirical runs prove them stable. Login-wall detection heuristic: redirect to `zhihu.com/signin` OR presence of a QR code element OR presence of text "登录" in a modal.
7. **Image pipeline refactor is mechanical.** The extract is clean: `describe_image()` at lines 125-135, the per-image download+describe loop at 632-657, and the metadata+MD save at 695-706. Four public functions per D-15 and PRD §6.5. Golden-file regression: pick 2–3 articles from `~/.hermes/omonigraph-vault/images/<hash>/` where `final_content.md` and `metadata.json` are both present; re-run `ingest_wechat.py` with cache disabled; diff tolerating 1-line Gemini description drift.
8. **Enrichment is synchronous and slow by design.** 3 questions × (120s 好问 + 60s Zhihu fetch) = up to 9 min per article. This is acceptable per CONTEXT.md reasoning — enrichment is not on the user's query path. But it does mean: **enrichment belongs in `ingest_wechat.py` AFTER scraping and BEFORE LightRAG `ainsert`**, so the existing cache-check logic (lines 532-566) must be updated to distinguish "cached content, not yet enriched" from "cached and enriched" using the new `articles.enriched` column.
9. **Windows-dev / Linux-remote compile asymmetry.** The `scripts/ingest.sh` wrapper already handles both `venv/Scripts/activate` and `venv/bin/activate`. New enrichment wrappers (e.g., `skills/zhihu-haowen-enrich/scripts/*.sh`) must replicate this pattern exactly. Per D-06 there is no local test path — but the scripts must still *parse* cleanly in Git Bash on Windows because that is where commits are prepared.
10. **Nyquist sampling rate** — pytest is the standard framework (per `~/.claude/rules/python/testing.md`) though the repo has no `pytest.ini` or `conftest.py` yet. Wave 0 must scaffold the test framework before implementation tasks begin.

## 1. Hermes Skill Orchestration

### Cheat-sheet (extracted from `skills/omnigraph_ingest/` and `skills/hermes_claude_code_bridge/`)

| Aspect | Pattern observed in repo | Notes for Phase 4 |
|---|---|---|
| Skill directory layout | `SKILL.md` + `scripts/*.sh` + optional `references/*.md` + `README.md` | Use the same layout for `zhihu-haowen-enrich/` and the top-level `enrich_article/`. |
| Frontmatter required fields | `name` (snake_case), `description` (multi-line `|`), `compatibility`, `metadata.openclaw.{os, requires.bins, requires.config}` | Confirmed from both existing skills. D-12 requires `GEMINI_API_KEY` under `requires.config`. |
| Shelling out to Python | `bash` code block in the SKILL body pointing to `scripts/<name>.sh` | Wrapper sources `~/.hermes/.env`, activates venv, `cd` into project root, `python <module>.py "$ARG"`. |
| Env sourcing | `scripts/ingest.sh:17-22` — `set -a; source "$HOME/.hermes/.env"; set +a` | Mandatory in every new wrapper. |
| Venv activation | `scripts/ingest.sh:45-55` — probes Scripts/activate then bin/activate | Mandatory — preserves Windows-dev parseability. |
| Root resolution | `OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}"` | Use the same var name; Hermes sets it via skill metadata. |
| Arg validation | Empty-arg early exit with `⚠️ Usage:` message to stderr | Keep the emoji warning convention. |
| Exit contract | `set -euo pipefail` at top; nonzero on any failure | Matches D-03. |
| Template vars | `${HERMES_SKILL_DIR}` appears in Hermes docs but NOT used in current repo skills | Safe to use if confirmed on remote. |
| Inline `!\`cmd\`` snippets | Documented in Hermes creating-skills docs but **no current repo skill uses them** | Prefer the shell-wrapper pattern — it's battle-tested in this repo. |

### Native skill-chaining — RESOLVED via remote SSH probe 2026-04-27

**Question:** can a Hermes skill's Markdown body say "invoke skill `zhihu-haowen-enrich` with argument `<question>`" and have Hermes natively route into that child skill and collect its output?

**Answer: yes, via the agent's built-in `skill_view()` tool + `/skill-name` command convention. No subprocess, no CLI, no re-entry bridge.**

Direct evidence from remote (`~/.hermes/hermes-agent/` — Hermes agent core, not committed to this repo):

- `tools/skills_tool.py:846` — `def skill_view(name, file_path=None)` is an agent-callable tool that loads SKILL.md content (or a referenced file) into the agent's context.
- `tools/skills_tool.py:1484-1487` — `skill_view` is registered as a native Hermes tool (`name="skill_view"`).
- `tools/skills_tool.py:1441` — `skills_list` is a registered tool (`"List available skills (name + description). Use skill_view(name) to load full content."`).
- `agent/skill_commands.py:4` (comment) — "can invoke skills via /skill-name commands".
- `agent/skill_commands.py:306` — `build_skill_invocation_message(...)` constructs the user-message wrapper that tells the agent a skill was invoked.
- `agent/skill_commands.py:332` — hard-coded template "IMPORTANT: The user has invoked the `{skill_name}` skill, indicating they want..." — this is how one skill's instructions can reference `/zhihu-haowen-enrich` and have the agent treat it as a user-style invocation.

**Operational model for D-01/D-02:**
1. User invokes the top-level `enrich_article` skill.
2. The skill's Markdown body contains a for-loop in prose: "For each question in the JSON emitted by `enrichment/extract_questions.py`, invoke the `/zhihu-haowen-enrich` skill, passing the question text. Then run `enrichment/fetch_zhihu.py` with the resulting URL. Accumulate results on disk at `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/`."
3. The agent reads this instruction, for each iteration calls `skill_view("zhihu-haowen-enrich")` to load that skill's CDP flow, executes it, records results on disk per D-03, then resumes the outer skill.
4. Exit contract: the outer skill's final step is `python enrichment/merge_and_ingest.py $ARTICLE_HASH` which reads the disk artifacts, builds the enriched MD + 3 Zhihu docs, and calls LightRAG.

**Implications for the planner:**
- D-01/D-02 are viable exactly as specified. No redesign.
- There is no programmatic "return value" from a skill — child skills communicate back via disk artifacts (aligns perfectly with D-03).
- The top-level skill body should explicitly reference the child skill by its slash-name (`/zhihu-haowen-enrich`) inside the loop instruction, so the agent's command resolver routes correctly.
- **Phase-0 blocker #1 REMOVED.** No dry-run required.

**Planner caveat:** the top-level skill's for-loop is a natural-language instruction; it relies on the LLM respecting it across `N=1..3` iterations. Hermes's primary model is DeepSeek v4 Pro (`~/.hermes/config.yaml:2`) — a strong instruction-follower, but agent.max_turns is 90 and each iteration consumes multiple turns. Budget: ~15-20 turns per question × 3 questions = ≤60 turns. Fits under 90-turn cap with margin.

## 2. Zhihu 好问 10-Step Flow

Source: PRD §7. Because `zhida.zhihu.com` is CN-gated and cannot be probed from this session, the strategy below is best-effort + explicit probe recommendations.

| Step | Action | Selector strategy (role/text-based preferred) | Wait condition | Failure mode | Recovery |
|---|---|---|---|---|---|
| 1 | `browser_navigate https://zhida.zhihu.com/` | — | `load` event | Network error / CN-block | Telegram notify; abort question |
| 2 | Detect login wall | Check URL redirected to `zhihu.com/signin` OR visible element with text `登录` OR visible QR code image element | 2s stable | Login wall present | **D-13 flow**: screenshot QR, send via Telegram, wait `/resume`, retry |
| 3 | Find search entry | Role-based: element with role=searchbox OR contenteditable div (Draft.js editor) | element visible + enabled | Not found | Probe log DOM structure; abort |
| 4 | Enter question text | Focus editor, send keys; Draft.js may not accept direct `value=` assignment — use `document.execCommand('insertText', false, q)` or simulate keystrokes | Text appears in editor | Editor rejects input | Fallback: click historical-search entry (PRD §7 note), re-try |
| 5 | Submit | Press Enter OR click submit button (text "搜索" / role=button) | URL or panel state change | Submit ignored | Retry once with keystroke simulation |
| 6 | Wait for AI summary generation | Poll for sentinel text `完成回答` visible OR streaming-complete DOM state | ≤120s (D-12 `ENRICHMENT_HAOWEN_TIMEOUT`) | Timeout | Mark question failed; continue |
| 7 | Extract summary | `browser_evaluate`: `document.querySelector('[role=main] article').innerText` or similar role-scoped text dump | — | Empty / error element present | Mark question failed |
| 8 | Expand sources panel | Click element with text matching `/全部来源\s*\d+/` | Source cards render | Button not present (no sources) | Mark question failed |
| 9 | Pick best source card | Heuristic: title contains keyword from question + highest 点赞/关注 count | Cards parsed | No card passes threshold | Mark question failed |
| 10 | Click card → read `location.href` | Click → wait for nav → `window.location.href` | URL is a `zhihu.com/question/.../answer/...` or `zhuanlan.zhihu.com/p/...` | URL is ad/non-zhihu | Mark question failed |

**Probes to run on first remote session (Phase-0):**
1. Does the search entry show immediately on page load, or is it behind a "search" button click?
2. Is the Draft.js editor's contenteditable div reachable via a stable role (`textbox` / `searchbox`)?
3. What exact CSS/DOM pattern marks "AI summary generation complete"?
4. What exact text pattern identifies the sources-panel trigger (`全部来源 N` vs `查看全部来源` vs `展开来源`)?
5. How many seconds typical for AI summary generation? Is 120s cap realistic or too aggressive?

Capture these as skill body comments + README notes; refine selectors iteratively.

**Login wall detection heuristic (D-13):**
```
Login wall detected IF (
    URL contains "/signin" OR "/login"
    OR element with text "登录" visible in top-level modal
    OR QR-code-shaped image visible (aspect ratio ~1:1, has data-url or specific alt text)
)
```

## 3. LightRAG Delete API

**Confirmed from local install** (`venv/Lib/site-packages/lightrag/lightrag.py`):

### `adelete_by_doc_id(doc_id, delete_llm_cache=False) → DeletionResult`
- Location: `lightrag.py:3223`
- Behavior (per docstring): deletes document, chunks, and graph elements. Partially-affected entities/relationships are *rebuilt using LLM cache from remaining documents* — meaning **orphan cleanup is automatic** but is **LLM-cache-dependent**. If `delete_llm_cache=True` is passed, re-derivation must re-query the LLM.
- Pipeline concurrency guard: blocks during busy pipeline unless the current job is itself a batch-delete ("Deleting {N} Documents").
- Returns:
  ```python
  DeletionResult(
      status: "success" | "not_found" | "not_allowed" | "fail",
      doc_id: str,
      message: str,
      status_code: int,  # HTTP-like: 200 / 404 / 403 / 500
      file_path: str | None,
  )
  ```

### `ainsert(input, ids=None, file_paths=None, track_id=None) → str (track_id)`
- Location: `lightrag.py:1237`
- **Critical for D-08:** `ids` parameter accepts a stable, deterministic doc ID — if omitted, LightRAG auto-generates MD5. For enrichment we should pass **synthetic IDs** like `f"zhihu_enrich_{wechat_hash}_{q_idx}"` so that `adelete_by_doc_id` can later target exactly those docs.
- `file_paths` parameter is used for citation — encode the parent relationship here: `f"enriches:{wechat_article_hash}"` (or similar sentinel that downstream queries can filter on).

### Related APIs available
- `adelete_by_entity(entity_name)` at `:4134` — **not needed** for Phase 4 happy path.
- `adelete_by_relation(...)` at `:4164` — **not needed** for Phase 4 happy path.

### Phase-0 D-14 spike — explicit validation checklist
- [ ] Insert one real WeChat article with an explicit `ids=["test_doc_1"]`.
- [ ] Query LightRAG for entities derived from that article; record the list.
- [ ] Call `adelete_by_doc_id("test_doc_1")`. Confirm `status == "success"`.
- [ ] Re-query for those entities. Expected: entities exclusive to this doc are gone; shared entities remain with rebuilt relationships.
- [ ] Re-`ainsert` with the same `ids=["test_doc_1"]` and the updated content. Confirm clean insert.
- [ ] Confirm no residual files in `lightrag_storage/` referencing the deleted `doc_id`.

## 4. Gemini 2.5 Flash Lite + Google Search Grounding

**Model ID:** `gemini-2.5-flash-lite` (confirmed already in use at `ingest_wechat.py:130` and `:515`).

**SDK:** `google-genai` already installed in the venv.

**Minimal working snippet for `extract_questions.py`:**

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=[
        "You are a technical editor reviewing a Chinese AI/Agent engineering article. "
        "Identify 1-3 questions the article raises but does NOT answer in depth. "
        "Use Google Search to avoid suggesting questions that are already well-covered "
        "on the public web — focus on genuine under-documented gaps.\n\n"
        f"Article:\n{article_text}"
    ],
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        # response_mime_type="application/json" — NOT compatible with tools in current SDK;
        # parse response.text with a follow-up call or regex instead.
    ),
)

text_with_questions = response.text
# Grounding citations, if present:
grounding = response.candidates[0].grounding_metadata
```

**Response structure notes:**
- `response.text` — the natural-language completion. Questions extraction should request a numbered list or fenced JSON in the prompt.
- `response.candidates[0].grounding_metadata.grounding_chunks` — list of web sources the model consulted. These can be persisted alongside each question (useful for later audit), but are not *required* by any downstream step.
- **Gotcha:** `response_mime_type="application/json"` cannot be combined with tool use in current SDK. Parse JSON manually from `response.text` (prompt should specify: "Reply with a JSON array of objects with fields `question` and `context`.").

**Cost notes:** Flash Lite free tier is 15 RPM (per CLAUDE.md error-handling notes); grounding calls count as regular generate_content calls. 3 articles per batch × 1 call each = well within quota.

## 5. Remote Edge CDP + Zhihu Session

**Current CDP pattern** (from `CLAUDE.md` "Testing the CDP / MCP Scraping Path" section):

- Local Edge mode: `CDP_URL=http://localhost:9223`, scraper uses `playwright.connect_over_cdp()` to an Edge instance started with `--remote-debugging-port=9223 --user-data-dir=<persistent-path>`.
- Remote testing mode (MCP-over-SSE, `CDP_URL` ending in `/mcp`) is also supported but less relevant here.

**Cookie persistence:**
- Cookies are tied to Edge's `--user-data-dir`. As long as Edge is restarted with the same `--user-data-dir`, Zhihu login state survives.
- The `zhihu-haowen-enrich` skill **shares the same Edge instance** as `ingest_wechat.py`'s CDP fallback — single browser, single user-data-dir, single cookie jar.
- **Assumption flagged for Phase-0 confirmation:** The remote Edge instance is already running with Zhihu cookies present. If not, the first enrichment run triggers D-13 (QR to Telegram).

**Login-wall detection heuristic:** see §2 step 2.

## 6. Telegram QR Delivery Reuse — RESOLVED via remote SSH probe 2026-04-27

**Location confirmed**: Telegram delivery ships inside Hermes itself. The `zhihu-haowen-enrich` skill calls it as a **native Hermes tool** — no Python helper, no subprocess, no new code.

**Evidence from remote `~/.hermes/`:**

- `~/.hermes/.env` contains `TELEGRAM_BOT_TOKEN=<REDACTED>` — credential already provisioned.
- `~/.hermes/hermes-agent/tools/send_message_tool.py:143` — `def send_message_tool(args, **kw)` is registered as an agent tool named `send_message`.
- `send_message_tool.py:135` (tool-schema docstring):
  > "The message text to send. To send an image or file, include `MEDIA:<local_path>` (e.g. `'MEDIA:/tmp/hermes/cache/img_xxx.jpg'`) in the message — the platform will deliver it as a native media attachment."
- Low-level platform impl: `~/.hermes/hermes-agent/gateway/platforms/telegram.py:1796` — `async def send_image_file(chat_id, image_path, caption, reply_to)` uses `self._bot.send_photo(chat_id, photo=<file>, ...)`.
- Text-only path at `send_message_tool.py:486` handles the `MEDIA:` token parsing and dispatches to `_send_telegram` which calls `send_photo`.

**Integration pattern for D-13 (Zhihu login wall recovery):**

Inside `skills/zhihu-haowen-enrich/SKILL.md`, the login-wall branch instructs Hermes to:

1. `browser_evaluate`: screenshot the QR element → save to `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/zhihu_login_qr.png` (local file on remote WSL).
2. Call `send_message(target="telegram:<default_chat>", message="MEDIA:$QR_PATH\n\nZhihu login expired. Scan the QR on your phone to re-authenticate the remote browser, then reply `/resume` to continue enrichment.")`.
3. Pause the skill (enter a wait-for-user-reply state — standard Hermes pattern; no custom polling code needed).
4. On `/resume`, reload the Zhihu page and retry from step 3 of the 10-step flow (§2).

**Default target resolution**: `send_message_tool._get_cron_auto_delivery_target()` at line 386 resolves the delivery target from Hermes config — the same mechanism FR-20 synthesis delivery already uses. The skill doesn't need to know the chat_id; it just says "send to telegram default".

**Phase-0 blocker #3 REMOVED.** No new delivery code to write; D-13 is a prose instruction in the skill body.

## 7. Image Pipeline Refactor

### Extractable functions from `ingest_wechat.py`

| Function | Current lines | Responsibility |
|---|---|---|
| `describe_image(path)` | 125-135 | Single image → Gemini Vision description. **Move and batch per D-15.** |
| Per-image download + describe loop | 632-657 (inside `ingest_article`) | URL → local path, rate-limit sleep (line 651), MD URL rewrite, description append, `processed_images` tracker. **Split into 3 functions.** |
| metadata.json + final_content.md save | 695-706 | **Extract into `save_markdown_with_images(md, dest_dir, metadata)`.** |
| Cache read | 532-556 | Read cached `final_content.md` + `metadata.json`. **Stays in `ingest_wechat.py`** (cache policy is WeChat-specific). |

### Proposed `image_pipeline.py` API

```python
from pathlib import Path

def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]:
    """Download urls → dest_dir/{i}.jpg; return {remote_url: local_path}.
    Skips failures silently (returns only successes in the dict)."""

def localize_markdown(
    md: str,
    url_to_local: dict[str, Path],
    base_url: str = "http://localhost:8765",
    article_hash: str = "",
) -> str:
    """Replace remote URLs in md with http://{base_url}/{article_hash}/{i}.jpg."""

def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe images via Gemini Vision. Rate-limits (4s) inter-image
    sleep INSIDE this function per D-15. Returns {path: description}.
    On failure for a given image, value is 'Error describing image: {e}'."""

def save_markdown_with_images(
    md: str,
    dest_dir: Path,
    metadata: dict,
) -> tuple[Path, Path]:
    """Atomic write of final_content.md + metadata.json (tmp → rename).
    Returns (md_path, metadata_path)."""
```

### Golden-file regression design

Per D-16:

1. **Pick 2–3 articles** from `~/.hermes/omonigraph-vault/images/<hash>/` on the remote host where *both* `final_content.md` and `metadata.json` exist and contain ≥ 3 images. Record the `<hash>` values in `tests/fixtures/golden_articles.txt`.
2. **Baseline capture** (one-time): copy the current `final_content.md` and `metadata.json` to `tests/fixtures/golden/<hash>/`.
3. **Regression run** (`pytest tests/test_image_pipeline_golden.py`):
   - For each golden hash, re-run a stripped-down scraper (no actual WeChat scrape — content taken from the existing MD's raw frontmatter + image URLs re-read from metadata).
   - Pipe through the new `image_pipeline.*` functions in the same order.
   - Compare outputs.
4. **Diff invariants (must match):**
   - Same image count.
   - Same local URL patterns (`http://localhost:8765/<hash>/<i>.jpg`).
   - Identical MD structure (heading levels, image order, `[Image N Reference]` / `[Image N Description]` block shape).
5. **Tolerances:**
   - Each image description may drift by ±1 line OR ±30% character count (Gemini non-determinism).
   - Use a line-by-line diff that skips image-description paragraphs.

### Unit tests (per D-16, one per public function)

- `tests/test_download_images.py` — mock HTTP responses; assert `dict[url, path]` and that 404s are excluded.
- `tests/test_localize_markdown.py` — string in/string out; no network.
- `tests/test_describe_images.py` — mock Gemini client; assert batch call order and sleep is invoked between items.
- `tests/test_save_markdown_with_images.py` — tmp dir fixture; assert atomic `.tmp → rename` pattern + JSON schema.

Both gates (golden-file + unit) must pass before the PR merges.

## 8. SQLite Migrations

### Source-of-truth CREATE TABLEs (`batch_scan_kol.py:87-115`)

```sql
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    digest TEXT,
    update_time INTEGER,
    scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id)
);
```

### Drift finding — `content_hash` is missing

- `ingest_wechat.py:718` does `UPDATE articles SET content_hash = ? WHERE url = ?`.
- `batch_scan_kol.py:87-115` does **not** declare `content_hash` in the CREATE TABLE.
- The live DB on the remote already has the column (prior researcher confirmed a manual ALTER was run).
- **Fix:** Phase 4 must also backfill `content_hash` into the CREATE statement **and** ensure the runtime ALTER is idempotent for fresh installs.

### Proposed migration approach — inline at `batch_scan_kol.py` startup

Matches existing codebase convention (schema-as-code in `init_db`). Add after line 138:

```python
# Idempotent runtime migrations. SQLite ALTER TABLE ADD COLUMN is idempotent
# only if we guard with a PRAGMA check — do it explicitly.
def _ensure_column(conn, table: str, column: str, type_def: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")

_ensure_column(conn, "articles", "content_hash", "TEXT")            # backfill drift
_ensure_column(conn, "articles", "enriched", "INTEGER DEFAULT 0")   # phase 4
_ensure_column(conn, "ingestions", "enrichment_id", "TEXT")         # phase 4
conn.commit()
```

Also update the `CREATE TABLE articles` statement to include `content_hash TEXT` and `enriched INTEGER DEFAULT 0` so fresh installs match post-migration state.

**Rejected alternative:** separate `migrations/` directory with sequenced files. Defer this until there are ≥ 3 migrations to track; current convention is simpler and in-repo.

### Value meanings for `articles.enriched` (from D-07)

```
 0 = pending (default for new articles)
 1 = enrichment in progress
 2 = enrichment success (including partial — ≥1 question succeeded)
-1 = skipped (article < 2000 chars; no questions extracted)
-2 = failed (all 3 questions failed; re-enrichment eligible)
```

## 9. config.py Additions

Post-supersession (D-07 no flag, D-12 Gemini not DeepSeek):

```python
# === Phase 4: Knowledge Enrichment ===

# Master switch. Per D-07 this is always True in production; the key exists
# so that individual invocations (e.g., direct `python ingest_wechat.py` for
# debugging) can set ENRICHMENT_ENABLED=0 via env to bypass.
ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

# Article character threshold below which extraction is skipped (enriched=-1).
ENRICHMENT_MIN_LENGTH = 2000

# Maximum questions per article.
ENRICHMENT_MAX_QUESTIONS = 3

# LLM for extract_questions (D-12 supersedes PRD §8).
ENRICHMENT_LLM_MODEL = "gemini-2.5-flash-lite"

# Enable google_search grounding tool on the extract_questions call (D-12).
ENRICHMENT_GROUNDING_ENABLED = True

# Per-question 好问 search timeout (PRD §8).
ENRICHMENT_HAOWEN_TIMEOUT = 120

# Per-question Zhihu source-article fetch timeout (PRD §8).
ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60

# Artifact root (D-03). Hermes skill writes per-question subdirs here.
ENRICHMENT_BASE_DIR = BASE_DIR / "enrichment"

# Hermes skill name for Zhihu 好问 (referenced by the top-level skill body).
ZHIHAO_SKILL_NAME = "zhihu-haowen-enrich"

# Local image server (reused for Zhihu article images).
IMAGE_SERVER_BASE_URL = "http://localhost:8765"
```

**Removed from PRD §8:** `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"` (superseded by D-12).

## 10. Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | **pytest** (per `~/.claude/rules/python/testing.md`) |
| Config file | **None currently** — Wave 0 must scaffold `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `ssh remote 'cd OmniGraph-Vault && venv/bin/pytest tests/ --tb=short'` |
| Fixtures location | `tests/conftest.py` (Wave 0) |

### Phase Requirements → Test Map

| Req | Behavior | Test type | Command | File exists? |
|---|---|---|---|---|
| D-07 enriched state machine | `ingest_wechat.py` sets enriched ∈ {−1, −2, 2} correctly per path | integration | `pytest tests/test_ingest_enrichment_states.py -x` | ❌ Wave 0 |
| D-08 Zhihu docs ingested with `enriches` link | 3 Zhihu docs have synthetic IDs and `enriches:<hash>` citation | integration (mocks LightRAG) | `pytest tests/test_ingest_enriched.py::test_zhihu_linking -x` | ❌ Wave 0 |
| D-09 merge_md format | 好问 summaries appended under `## 知识增厚` heading | unit | `pytest tests/test_merge_md.py -x` | ❌ Wave 0 |
| D-10/D-14 delete+re-ainsert | LightRAG spike on real article | **manual/remote-only** | `ssh remote 'cd OmniGraph-Vault && venv/bin/python scripts/phase0_delete_spike.py'` | ❌ Phase 0 |
| D-12 extract_questions uses grounding | Request payload has `tools=[Tool(google_search=...)]` | unit (mock SDK) | `pytest tests/test_extract_questions.py::test_grounding_tool_enabled -x` | ❌ Wave 0 |
| D-13 login wall → Telegram QR | Skill path reachable; heuristic triggers | **manual/remote-only** | Hermes manual run with bad cookie | ❌ Phase 0 (after delivery fn located) |
| D-15 describe_images batch | Rate-limit sleep called between images | unit (mock time.sleep) | `pytest tests/test_describe_images.py::test_rate_limit -x` | ❌ Wave 0 |
| D-16 image_pipeline golden | Re-run vs fixtures matches within tolerance | **integration/remote-only** | `ssh remote '...pytest tests/test_image_pipeline_golden.py'` | ❌ Wave 0 (fixtures) |
| PRD §6.2 fetch_zhihu image filter | width<100 images excluded | unit (mock DOM) | `pytest tests/test_fetch_zhihu.py::test_small_image_filter -x` | ❌ Wave 0 |
| Migration idempotency | Running `init_db` twice does not error | unit | `pytest tests/test_migrations.py -x` | ❌ Wave 0 |

### Sampling rate

- **Per task commit:** `pytest tests/test_<just_touched>.py -x` (fast, 1–2 seconds).
- **Per wave merge:** `ssh remote 'pytest tests/ -x --tb=short'` (full suite, 30–60 seconds; includes golden-file regression).
- **Phase gate:** Full suite green + manual D-14/D-13/D-06 remote smoke-test runs before `/gsd:verify-work`.

### Wave 0 gaps (scaffold before any implementation task)

- [ ] `pyproject.toml` — add `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and appropriate markers (`unit`, `integration`, `remote_only`).
- [ ] `tests/conftest.py` — shared fixtures: tmp `BASE_DIR` factory, mock Gemini client, mock LightRAG instance, mock `requests.get` for image downloads.
- [ ] `tests/fixtures/golden/` — copy 2–3 real `<hash>/final_content.md` + `metadata.json` from remote.
- [ ] `tests/fixtures/sample_wechat_article.md` — fixed text for extract_questions unit tests.
- [ ] `tests/fixtures/sample_haowen_response.json` — mock Hermes skill return for orchestrate tests.
- [ ] `scripts/phase0_delete_spike.py` — D-14 spike runner (standalone; runs on remote only).
- [ ] Framework install: `pytest` already present in `requirements.txt`? — verify during Wave 0; if not, add `pytest`, `pytest-mock`, `pytest-asyncio`.

### Phase-0 blockers (must pass before Phase-1 task scheduling)

**Resolved via remote SSH probe 2026-04-27 (no longer blockers):**

- ✅ Hermes native skill-to-skill invocation — confirmed via `skill_view()` tool + `/skill-name` convention (§1).
- ✅ Telegram delivery function located on remote — `send_message` agent tool with `MEDIA:<path>` convention (§6).

**Remaining blocker (implementation-level, D-14):**

1. **LightRAG `adelete_by_doc_id` + re-ainsert spike** — confirms orphan cleanup behavior on a real article. Re-validate that re-insertion with identical `ids` produces a clean doc (no duplicate entities, no stale relationships). See §3 validation checklist.

This is a small-budget probe (<30 min) runnable as a standalone Python script on remote. The planner should schedule it as Wave-0 before any Phase-1 implementation task begins.

## Open Risks / Blockers for Planning

| Risk | Impact | Mitigation |
|---|---|---|
| `adelete_by_doc_id` leaves orphan entities in practice | Re-enrichment path unsafe | D-14 spike + `delete_llm_cache=True` fallback |
| Zhihu 好问 UI changes between research and implementation | Selectors break | Skill uses semantic/role-based instructions, not CSS paths; update on first empirical run |
| Zhihu cookies expire → QR login required every run | UX friction | D-13 reuses `send_message` (§6); no code; user interruption ≤1× per cookie lifetime |
| Hermes agent.max_turns=90 exceeded on a 3-question article | Loop aborts mid-enrichment | Keep per-question body tight; each iteration ≤20 turns (3×20=60 << 90 cap) |
| Gemini grounding quota hit | Extract_questions fails | Existing rate-limiter pattern (`ingest_wechat.py` `llm_model_func`) applies; free-tier 15 RPM is ample for enrichment rate |
| Image description non-determinism fails golden-file diff | Blocks merge | Explicit 1-line / 30%-char tolerance in diff logic |
| Windows-dev / Linux-remote parseability asymmetry | Scripts break on one side | Replicate `scripts/ingest.sh` dual-venv pattern exactly |
| Remote git ahead of local (`dd97626` vs `f7b4293` at probe time) | Planner reads stale local code | Planner pulls on Windows before reading repo; CLAUDE.md already warns of this |

## References

### Primary (HIGH confidence — read directly)

- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — all 16 locked decisions
- `docs/enrichment-prd.md` — PRD v1.0 2026-04-27
- `CLAUDE.md` — project rules, typo'd data dir, CDP modes
- `skills/hermes_claude_code_bridge/SKILL.md` — frontmatter + skill-dir layout reference (NOT a skill-to-skill invocation precedent)
- `skills/omnigraph_ingest/SKILL.md` — decision-tree pattern for new `enrich_article` skill
- `skills/omnigraph_ingest/scripts/ingest.sh` — shell wrapper pattern (env sourcing, venv activation, root resolution)
- `config.py` — load_env pattern, BASE_DIR (typo'd)
- `ingest_wechat.py:125-135,480-506,600-720` — refactor touch-points
- `batch_scan_kol.py:71-138` — CREATE TABLE source-of-truth; migration insertion site
- `venv/Lib/site-packages/lightrag/lightrag.py:1237` — `ainsert` signature (confirms `ids`, `file_paths` params)
- `venv/Lib/site-packages/lightrag/lightrag.py:3223` — `adelete_by_doc_id` signature + DeletionResult schema
- `venv/Lib/site-packages/google/genai/types.py:4241` — `GoogleSearch` tool class (confirms zero-arg construction)
- `specs/PRD_TDD.md:81` — FR-20 Telegram delivery listed as "Implemented" (implementation itself not in repo)

### Secondary (MEDIUM confidence — referenced from CONTEXT.md; not verified live this session)

- `hermes-agent.nousresearch.com/docs/developer-guide/creating-skills` — skill structure, template vars, inline snippets
- `hermes-agent.nousresearch.com/docs/guides/automate-with-cron` — "script stdout becomes agent context" pattern (D-03)
- `hermes-agent.nousresearch.com/docs/user-guide/configuration/` — `tool_output.max_bytes: 50000`
- `hermes-agent.nousresearch.com/docs/user-guide/features/skills` — skill discovery, `skills.external_dirs`

### Remote SSH findings (HIGH confidence — verified on `ohca.ddns.net:49221` 2026-04-27)

- `~/.hermes/hermes-agent/tools/skills_tool.py:846` — `skill_view(name, file_path=None)` native agent tool (resolves §1 open question).
- `~/.hermes/hermes-agent/agent/skill_commands.py:306,332` — `build_skill_invocation_message`; `/skill-name` is the invocation convention.
- `~/.hermes/hermes-agent/tools/send_message_tool.py:143,135` — `send_message` tool with `MEDIA:<path>` attachment protocol (resolves §6).
- `~/.hermes/hermes-agent/gateway/platforms/telegram.py:1796` — `send_image_file(chat_id, image_path, caption, reply_to)` low-level impl.
- `~/.hermes/config.yaml` — Hermes primary `deepseek-v4-pro`, fallback `gemini-3-flash-preview`, `agent.max_turns: 90`, `gateway_timeout: 1800s`, terminal `timeout: 300s`.
- `~/.hermes/.env` — `TELEGRAM_BOT_TOKEN` present (credential confirmed, value not logged).
- Remote LightRAG version: **1.4.15** (`python -c "import lightrag; print(lightrag.__version__)"`). Delete/insert method list confirmed: `adelete_by_doc_id, adelete_by_entity, adelete_by_relation, ainsert, ainsert_custom_chunks, ainsert_custom_kg`.
- Remote repo state: `dd97626 chore: track spider module, fix .gitignore for zip files` (2 commits ahead of local `f7b4293`).

### Tertiary (LOW confidence — still needs empirical confirmation during execution)

- Zhihu 好问 DOM structure and selector stability (first remote skill run; refine iteratively)
- Remote Edge Zhihu cookie freshness at phase kickoff (assumed stale → D-13 likely fires once on first run)
- Precise behavior of `adelete_by_doc_id` orphan rebuild on a real article (D-14 spike covers this)

## Metadata

**Confidence breakdown (post remote SSH probe 2026-04-27):**
- Hermes skill orchestration: **HIGH** — `skill_view()` tool + `/skill-name` convention verified directly in `~/.hermes/hermes-agent/tools/skills_tool.py` and `agent/skill_commands.py` on remote.
- Zhihu 好问 flow: LOW-MEDIUM — PRD §7 is the only source; selectors need empirical tuning on first run.
- LightRAG API: HIGH — read directly from installed library code; version 1.4.15 confirmed on remote.
- Gemini grounding: HIGH — SDK types verified directly.
- CDP / Zhihu session: MEDIUM — reuses existing local-Edge CDP plumbing; cookie freshness is a runtime variable not a code-level unknown.
- Telegram reuse: **HIGH** — delivery tool located at `~/.hermes/hermes-agent/tools/send_message_tool.py:143`; `MEDIA:<path>` attachment protocol documented in-tool-schema.
- Image pipeline refactor: HIGH — all refactor targets located with exact line ranges.
- SQLite migration: HIGH — CREATE TABLE source read directly; drift pattern confirmed by prior researcher.
- config.py additions: HIGH — straightforward consolidation of D-07/D-12 with PRD §8 deltas.
- Validation architecture: MEDIUM — pytest framework ships with project rules; scaffold gaps enumerated but test content is Phase-0/Wave-0 work.

**Research date:** 2026-04-27
**Valid until:** 2026-05-27 (fast-moving: Zhihu UI, Gemini SDK, Hermes docs)

## RESEARCH COMPLETE
