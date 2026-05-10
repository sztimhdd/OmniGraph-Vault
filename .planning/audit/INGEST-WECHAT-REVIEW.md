# INGEST-WECHAT-REVIEW — Deep audit of ingest_wechat.py
Generated: 2026-05-10 19:43 ADT
Scope: ingest_wechat.py (1406 LOC, drift -2 from POLLUTION-AUDIT's 1408) — architecture, lib↔app inversion, ingest_article internals
Excludes: T1 / T1.5 closed boot pollution (b181edc, ece74fe, 14f1136, 03eee42, 3afc042); 7 already-audited surfaces enumerated in POLLUTION-AUDIT.md "Already-audited exclusions"

## TL;DR

1. **The lib↔app inversion is real and load-bearing.** `lib/scraper.py:212-238` does `import ingest_wechat` + `getattr(ingest_wechat, fn_name)` to dispatch into 4 scrape functions defined at `ingest_wechat.py:532-883`. 5 unit tests pin those exact names via `monkeypatch.setattr(ingest_wechat, "scrape_wechat_*")`. Relocating the functions is the architecturally-correct fix but is medium-blast-radius (lib/scraper rewrite + test rewrites). MEDIUM.
2. **`ingest_article` is a 405-LOC god-function** (lines 918-1322). Cached-vs-fresh branch at L952-999 + 5 ordered checkpoint stages at L1003-1264 + Vision worker spawn at L1245 + dual hash schemes at L943/L946 + pending-doc registry + post-ingest verification + DB content_hash gate. Three clean extractions are achievable without behavior change (cache-hit path, image-cap helper already extracted, manifest builder). HIGH.
3. **Duplicate `get_llm_func` import** at L146 and L163 — bare orphan from Phase 9 / LDEV-04 layering. Trivial cleanup. LOW.
4. **`llm_model_name="deepseek-v4-flash"` at L318** is the last residual from POLLUTION-AUDIT issue #2. The kwarg is wrong when `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` — but `get_llm_func()` at L316 already routes the actual call. Fix is one-line delete; T1.5 explicitly carved this out as T2 territory. LOW.
5. **76→64 marker drift**: actual marker count is 61-64 not 76 (audit's "raw count 41 / broader 76"). Even at 64 they remain in dense pockets — 32 distinct "Phase N" tags + 14 "D-XX" tags coexist; reading the file requires holding three migration dictionaries (Phase 5/7/8/10/11/12/13/17/18/19/20, D-09/10/11/15/16, plus Quick 260508/260509/260510 hot-fixes).

## Methodology

Six review dimensions. Each section cites raw evidence (file:line, grep count). No fix code proposed — categorize + scope only.

- **A — Module map**: every top-level def + module-level constant. Where would each go in clean architecture?
- **B — Lib↔app inversion**: exact dispatch mechanism + transitive lock-points (tests + production callers).
- **C — `ingest_article` deep-dive**: line-by-line decomposition, identify safe extraction slices.
- **D — Migration markers**: triage to load-bearing vs decorative.
- **E — Test coverage**: 15 scattered files (3494 LOC) — what does each pin? What is uncovered?
- **F — Refactor blast radius**: per finding, the transitive surface a fix would touch.

**Drift note**: POLLUTION-AUDIT.md cites 1408 LOC; current `wc -l` returns 1406. Line numbers in this review are CURRENT (post-T1/T1.5 commits). Audit's L529/L664/L704/L838/L915/L1327 cites map to current L532/L667/L707/L841/L918/L1325. The 2-line shift came from T1's ingest_wechat.py edits (no major restructuring; T1/T1.5 did not touch ingest_wechat.py — both quicks explicitly carved it out as T2 territory). Drift was likely from `260510-h09` (`949e3f4`).

**Anti-fabrication**: marker count claim "61-64" derives from `grep -cE "^[[:space:]]*#.*(Phase|D-|Wave|Plan|Quick|HYG-|SCH-|ARCH-|CKPT-|D-SUBDOC|IMG-0|hot-fix|...)" ingest_wechat.py = 61` and broader-pattern count = 64 — neither matches POLLUTION-AUDIT's "raw 41 / broader 76". Audit may have used a different pattern; reporting both numbers, treating as "high marker density" rather than fighting over the exact count.

## Module map (Signal A — function inventory)

Top-level defs and key module-level constants in `ingest_wechat.py`:

| line | symbol | LOC | top-level? | callers | role | tests |
|---|---|---|---|---|---|---|
| L7 | `os.environ.setdefault("LLM_TIMEOUT", "600")` | 1 | constant | (LightRAG dataclass) | D-09.01 boot ordering | none direct |
| L11 | `os.environ.setdefault("LOG_LEVEL", "ERROR")` | 1 | constant | (structlog) | log noise suppression | none |
| L29 | `_status_is_processed(status_val)` | 17 | yes | L108 | DocStatus.PROCESSED detect | `test_status_is_processed.py` (68 LOC) |
| L55 | `PROCESSED_VERIFY_MAX_RETRIES`, `PROCESSED_VERIFY_BACKOFF_S` | 2 | constants | L67 | quick 260510-h09b retry budget | none direct |
| L63 | `_verify_doc_processed_or_raise(rag, doc_id, ...)` | 60 | yes | L1297 | hot-fix gate (260510-h09) | `test_ingest_article_processed_gate.py` (204 LOC) |
| L183 | `_is_mcp_endpoint(url)` | 2 | yes | L1044 | URL suffix detect for MCP vs CDP | none |
| L186 | `APIFY_TOKEN`, `APIFY_TOKEN_BACKUP`, `DB_PATH`, `MAX_IMAGES_PER_ARTICLE` | 4 | constants | various | env-derived module state | `test_image_cap.py` pins MAX_IMAGES |
| L198 | (auto-init `init_db()` block at module import) | 9 | side-effect | (boot) | Phase 4 SQLite migrate | none |
| L209 | `_persist_entities_to_sqlite(url, entities)` | 18 | yes | L975, L1212, L1399 | secondary entity persist (primary = entity_buffer) | none direct |
| L237 | `_apply_image_cap(url_to_path, max_images)` | 27 | yes | L1159 | HYG-02 truncation helper | `test_image_cap.py` (105 LOC) |
| L267 | `os.makedirs(BASE_IMAGE_DIR), os.makedirs(RAG_WORKING_DIR)` | 2 | side-effect | (boot) | runtime dir bootstrap | none |
| L276 | `if not GOOGLE_APPLICATION_CREDENTIALS: GOOGLE_GENAI_USE_VERTEXAI=false` | 2 | side-effect | (boot) | Phase 11 D-11.08 Vertex guard (POLLUTION-AUDIT issue #1, ALREADY CORRECTLY GUARDED) | none |
| L291 | `get_rag(flush=True)` | 49 | yes | L980 (cache branch), L1202 (fresh branch), batch_ingest_from_spider:759/1594 | LightRAG factory | `test_get_rag_contract.py` (122 LOC) |
| L346 | `_PENDING_DOC_IDS` (module global dict) | 1 | constant | L351, L356, L361 | rollback registry | `test_rollback_on_timeout.py` (178 LOC) |
| L349 | `_register_pending_doc_id(article_hash, doc_id)` | 2 | yes | L987, L1226 | rollback registry write | (above) |
| L354 | `_clear_pending_doc_id(article_hash)` | 2 | yes | L992, L1233; batch_ingest_from_spider:307 | rollback registry clear | (above) |
| L359 | `get_pending_doc_id(article_hash)` | 2 | yes | batch_ingest_from_spider:294 | rollback registry read | (above) |
| L371 | `_vision_worker_impl(rag, article_hash, ...)` | 112 | yes | L1245 (spawn) | async sub-doc image worker (D-10.06) | `test_vision_worker.py` (566 LOC), `test_checkpoint_ingest_integration.py` (525 LOC) |
| L488 | `_UA_POOL`, `_ua_index`, `_last_ua_request`, `_UA_*` | 7 | constants | L498, L513 | UA rotation state | none direct (covered via scrape tests) |
| L498 | `_next_ua()` | 5 | yes | L544 | UA round-robin | none |
| L513 | `_ua_cooldown()` | 16 | yes | L543 | UA throttle | none |
| L532 | `scrape_wechat_ua(url)` | 91 | yes | L1026, lib/scraper:228 (getattr) | UA-based WeChat scrape (Tier 1) | `test_scraper_ua_img_merge.py` (192 LOC) |
| L626 | `_apify_call(token, url)` | 39 | yes | L686, L696 | single Apify invocation (extracted by 260508-ev2 F1a) | `test_apify_rotation.py`, `test_apify_run_input.py` |
| L667 | `scrape_wechat_apify(url)` | 39 | yes | L1030, lib/scraper:228 (getattr) | Apify WeChat scrape (Tier 2) — dual-token rotation | `test_apify_rotation.py` (69 LOC), `test_apify_run_input.py` (134 LOC) |
| L707 | `scrape_wechat_mcp(url)` | 131 | yes | L1049, lib/scraper:228 (getattr) | Remote MCP scrape (Tier 4) | `test_mcp_scraper_tool_name.py` (47 LOC) |
| L841 | `scrape_wechat_cdp(url)` | 43 | yes | L1046, lib/scraper:228 (getattr) | Local Edge CDP scrape (Tier 3) | none direct |
| L885 | `process_content(html)` | 12 | yes | L1083, L1089, lib/scraper:253; batch_ingest_from_spider:1047 | HTML→markdown helper | `test_batch_ingest_hash.py:31` mocks it |
| L900 | `extract_entities(text)` | 15 | yes | L969, L1206, L1393; `test_checkpoint_ingest_integration.py:135` mocks | DeepSeek entity extract (Phase 5-00b R4) | indirect via integration tests |
| L918 | `ingest_article(url, rag=None)` | 405 | yes | `__main__:1406`, batch_ingest_from_spider:286, integration tests | god-function — see Section C | 6 unit tests + 2 integration files |
| L1325 | `ingest_pdf(file_path, rag=None)` | 78 | yes | (no in-process callers found) | PDF ingest path | none |
| L1403 | `if __name__ == "__main__": asyncio.run(ingest_article(url))` | 4 | side-effect | CLI | single-URL entry-point | none |

**21 top-level defs + 4 module-level config blocks + 1 CLI entry point.** By role they cleanly partition into **5 logical jobs**:

| logical job | members | could-live-in |
|---|---|---|
| **A. Hot-fix gate** (added 2026-05-10) | `_status_is_processed`, `_verify_doc_processed_or_raise`, `PROCESSED_VERIFY_*` constants | new `lib/processed_gate.py` (small but semantically distinct) |
| **B. Pending-doc registry** | `_PENDING_DOC_IDS`, `_register_pending_doc_id`, `_clear_pending_doc_id`, `get_pending_doc_id` | new `lib/pending_doc_registry.py` (already module-global state pretending to be local) |
| **C. RAG factory** | `get_rag` | already importable via `from ingest_wechat import get_rag`; could move to `lib/rag_factory.py` |
| **D. WeChat scrapers** | `scrape_wechat_ua`, `scrape_wechat_apify`, `_apify_call`, `scrape_wechat_mcp`, `scrape_wechat_cdp`, `process_content`, `_next_ua`, `_ua_cooldown`, `_is_mcp_endpoint`, `_UA_*` state | `lib/scraper_wechat.py` (closes the inversion in Section B) |
| **E. Article orchestration** | `ingest_article`, `ingest_pdf`, `_vision_worker_impl`, `extract_entities`, `_persist_entities_to_sqlite`, `_apply_image_cap`, `MAX_IMAGES_PER_ARTICLE` | stays at root (this IS the application layer) |

The audit's "5 jobs in one module" claim is correct in spirit but undercounts. The actual partition is 5 logical jobs + 1 hot-fix layer that has accumulated post-audit (260510-h09).

## Lib↔app inversion (Signal B — extraction blueprint)

### Mechanism (verified at file:line)

`lib/scraper.py:212-238` defines `_scrape_wechat()`:

```
L224:    import ingest_wechat                                  # late import to break circle
L226:    cascade_order = _resolve_cascade_order()              # default: ua, apify, cdp, mcp
L227:    for fn_name in cascade_order:
L228:        fn = getattr(ingest_wechat, fn_name, None)        # ← the inversion
L229:        if fn is None:
L230:            continue
L232:            result = await fn(url)                         # call ingest_wechat's function from "library"
```

The default cascade order at `lib/scraper.py:173-178` is hard-coded:
```
("scrape_wechat_ua", "scrape_wechat_apify", "scrape_wechat_cdp", "scrape_wechat_mcp")
```

These four names MUST exist as `getattr`-discoverable attributes on the `ingest_wechat` module for `lib/scraper.py:_scrape_wechat()` to work. If they move, `lib/scraper.py:228` returns `None` for every cascade tier and falls through to the `summary_only=True` failure path at `lib/scraper.py:276` — silent cascade collapse, the production cron breaks for every WeChat URL.

### Where the names are pinned (transitive lock-points)

**Production callers** (must be re-pointed atomically with any rename/move):
- `lib/scraper.py:162-165` (`_CASCADE_TOKEN_MAP` dict literal — all four names as values)
- `lib/scraper.py:174-177` (`_DEFAULT_CASCADE_ORDER` tuple literal)
- `lib/scraper.py:228` (`getattr(ingest_wechat, fn_name, None)`)
- `ingest_wechat.py:1026, 1030, 1046, 1049` — internal cascade in `ingest_article` cache-miss branch (these are LOCAL calls, not the scraper.py path; both paths exist in parallel — see Section C #4 finding)

**Test pins** (must be updated atomically with any rename):
- `tests/unit/test_apify_rotation.py:26, 43, 64` — `await ingest_wechat.scrape_wechat_apify(...)`
- `tests/unit/test_scrape_cascade_order.py:37, 39, 41, 43` — `monkeypatch.setattr(ingest_wechat, "scrape_wechat_*", ...)` for all 4
- `tests/unit/test_scraper_ua_img_merge.py:48, 51, 54, 57` — same pattern, all 4
- `tests/unit/test_apify_run_input.py:23` — `import ingest_wechat`, then `ingest_wechat.scrape_wechat_apify`
- `tests/unit/test_mcp_scraper_tool_name.py:26-29` — string match on "scrape_wechat_mcp" in docstring + assertion message

**Total transitive surface**: 5 production sites in 2 files (lib/scraper.py + ingest_wechat.py) + ~12 test attribute references in 5 test files.

### Where each scraper SHOULD live in clean architecture

In a clean cascade architecture, all 4 scrape implementations live next to the orchestrator:
- `lib/scraper.py` already owns `_scrape_wechat()` (the orchestrator) + cascade resolution
- The 4 implementations physically inside `ingest_wechat.py` are an accident of git history (Phase 19 SCR-01..05 fixed the orchestrator wrapper but did not pull the impls down — POLLUTION-AUDIT.md is correct)

**Target shape (no fix code proposed, just the architecture)**:
- `lib/scraper.py` (existing): cascade resolution + orchestration (unchanged)
- `lib/scraper_wechat.py` (NEW): `scrape_wechat_{ua,apify,cdp,mcp}` + `_apify_call` + `_next_ua` + `_ua_cooldown` + `_is_mcp_endpoint` + `_UA_POOL` + `process_content`
- `ingest_wechat.py` (LIGHTER): just orchestration (`ingest_article`, `ingest_pdf`, `_vision_worker_impl`, registries, `extract_entities`)
- `lib/scraper.py:228` would become `from lib.scraper_wechat import scrape_wechat_*` + a dict-of-funcs lookup, eliminating the `getattr` pattern

### What must change in lib/scraper.py if the names move

1. `_CASCADE_TOKEN_MAP` (L162-166) values become the new full module path (or, better, callable references — eliminates the `getattr` runtime lookup entirely).
2. `_DEFAULT_CASCADE_ORDER` (L173-178) tokens unchanged (they're already abstract names like "ua"/"apify").
3. `_scrape_wechat()` (L212): drop `import ingest_wechat`; replace `getattr(ingest_wechat, fn_name, None)` with a dict lookup `_FUNCS[fn_name]`.
4. `_scrape_wechat()` L253: `ingest_wechat.process_content(content_html)` → `from lib.scraper_wechat import process_content` (or pass it in).

### Why this is a MEDIUM, not HIGH, severity finding

- The inversion is structurally wrong but production-stable (UA-first cascade + `getattr` indirection both verified working in 2026-05-08 cron postmortem).
- The cost is paid every time someone reads either file: "where does scrape_wechat_apify live?" — every contributor has to learn the pattern. But it does not crash production.
- Extraction is a behavior-preserving refactor (move funcs + rewire 5 prod sites + 12 test refs). MEDIUM blast radius, large diff, low semantic risk.

## ingest_article god-function deep-dive (Signal C)

`ingest_article` spans **L918 → L1322 (405 LOC)**. Decomposition:

| stage | line range | role | persistent state | extraction-safe? |
|---|---|---|---|---|
| **0. preamble** | L918-944 | docstring, log start, compute `ckpt_hash` (SHA-256[:16]) + `article_hash` (MD5[:10]), bootstrap metadata | `metadata.json` written | YES — already trivial |
| **1. cache-hit branch** | L946-999 | check `final_content.md`, reuse cached body, run entity extract, ainsert, RETURN `None` (no Vision spawn) | LightRAG ainsert + `articles.content_hash` NOT written here | **YES — extract as `_ingest_cached(url, article_dir, rag, ckpt_hash)`** |
| **2. scrape (Stage 1)** | L1003-1070 | check `has_stage("scrape")`, else cascade UA→Apify→CDP/MCP (note: PARALLEL to lib/scraper.py cascade — see #4 below), persist `01_scrape` checkpoint | `01_scrape` marker | YES with care — the parallel cascade is the load-bearing part (see lock-points) |
| **3. method-switch + markdown extract** | L1072-1095 | `if method == "apify"... elif "ua"... else (cdp/mcp/resumed)`, build `full_content` markdown, recompute `article_hash` (DUPLICATE — see #5) | none | YES — small `_extract_markdown_by_method` helper |
| **4. classify (Stage 2 — placeholder)** | L1097-1112 | check `has_stage("classify")`, else write empty placeholder dict | `02_classify` marker | YES |
| **5. image_download (Stage 3)** | L1114-1182 | check `has_stage("image_download")`, else `download_images` + `filter_small_images` + `_apply_image_cap` + manifest builder | `03_manifest` marker | YES — manifest builder slice is ~40 LOC |
| **6. localize markdown + image refs** | L1184-1196 | rewrite img URLs to local paths, append "Image N from article ..." lines | none | YES — `_inline_image_refs` helper |
| **7. RAG init (lazy)** | L1198-1202 | `if rag is None: rag = await get_rag(flush=True)` | none | YES — already trivial |
| **8. entity buffering** | L1204-1215 | `extract_entities(full_content)` + write `entity_buffer/{hash}_entities.json` + sqlite | entity buffer + sqlite | YES — `_buffer_entities` helper |
| **9. text_ingest (Stage 4)** | L1217-1235 | register pending doc_id, `await rag.ainsert(full_content, ids=[doc_id])`, clear pending, write `04_text_ingest` marker | LightRAG state + `04_text_ingest` marker + `_PENDING_DOC_IDS` global | NO without care — see lock-points: registry contract is observed externally by batch_ingest_from_spider |
| **10. vision worker spawn (Stage 5+6)** | L1237-1264 | spawn `_vision_worker_impl` if images, else write terminal `sub_doc_ingest` marker | `track_vision_task` registry + `06_sub_doc_ingest` marker | NO without care — fire-and-forget contract is in production |
| **11. local file save** | L1266-1277 | `save_markdown_with_images(article_dir, ...)` | `final_content.md` + `metadata.json` | YES — already a thin wrapper |
| **12. PROCESSED verify (hot-fix)** | L1285-1297 | `await _verify_doc_processed_or_raise(rag, doc_id)` — RAISES on failure | none | NO — this is load-bearing — see #6 below |
| **13. DB content_hash gate** | L1300-1317 | gated on `doc_confirmed=True`, write `articles.content_hash` + `enriched=-1` if short | sqlite `articles` row | YES — `_persist_content_hash` helper |
| **14. return** | L1319-1322 | return `vision_task` for tests / None for fire-and-forget | none | trivial |

### #1 — Cached-vs-fresh branch (L946-999 vs L1001-1322)

The branch boundary is at `L952: if os.path.exists(cache_content):`. The cached path mirrors stages 8 (entity buffer), 9 (text_ingest), and explicitly returns `None` (no Vision spawn). The fresh path runs all 14 stages. This is a clean extract candidate: `_ingest_cached_article(url, article_dir, rag, ckpt_hash)` would be ~50 LOC and remove a deep nested branch from `ingest_article`. **MEDIUM concern, easy extract.**

### #2 — 5-stage checkpoint contract

| stage marker | written at | content | resume reads at |
|---|---|---|---|
| `01_scrape` | L1066 | raw HTML blob (or wrapped Apify markdown) | L1006 (`read_stage("scrape")`) |
| `02_classify` | L1111 | placeholder dict (Phase 12 stub; Phase 13 will replace) | L1102 (`read_stage("classify")`) |
| `03_manifest` (= `image_download`) | L1181 | manifest list with `local_path` + `filter_reason` per URL | L1120 (`read_stage("image_download")`) |
| `04_text_ingest` | L1234 | empty marker only | L1223 (`has_stage`) |
| `05_vision/{image_id}.json` | inside `_vision_worker_impl` L424 | per-image description | (worker reads `list_vision_markers` for resume) |
| `06_sub_doc_ingest` | inside `_vision_worker_impl` L445/458 + L1261 (no-images branch) | terminal marker | (resume gates against this; never re-spawns worker on hit) |

**Atomicity contract** is at the `lib/checkpoint` library level (`.tmp` → `os.rename`). `ingest_article` does not enforce atomicity itself; it just calls `write_stage(ckpt_hash, "...", payload)`. Extraction risk: if the 5 stages were split into 5 separate functions, the reader of `ingest_article` would lose the linear "scrape → classify → image_download → text_ingest → vision" narrative, which is the file's main pedagogical structure. **Recommend: extract individual stage helpers but keep `ingest_article` as the linear orchestrator.**

### #3 — Vision worker spawn (L1245)

```
L1245:    vision_task = track_vision_task(asyncio.create_task(_vision_worker_impl(...)))
```

Already audited: quick `260509-p1n` (`f715f06`) added `lib/vision_tracking.track_vision_task` to fix the D-10.09 drain hang. The worker fires-and-forgets in production (`batch_ingest_from_spider` does NOT await), but tests await it. The contract is already pinned by tests at `test_text_first_ingest.py` and `test_vision_worker.py`. **Not a finding — already audited.** Lock-point note: any extraction MUST keep the spawn at the call site; extracting the spawn into a helper would re-open the audited drain hang.

### #4 — Parallel cascade with lib/scraper.py (HIDDEN inversion artifact)

The cache-miss branch at L1024-1049 contains its OWN cascade — UA → Apify → CDP/MCP — independent of `lib/scraper.py:_scrape_wechat()`. They have different shapes:

| concern | `ingest_article` L1024-1049 | `lib/scraper.py:_scrape_wechat` |
|---|---|---|
| order | UA → Apify → CDP/MCP | UA → Apify → CDP → MCP (4-tier, MCP separate) |
| MCP/CDP gate | `_is_mcp_endpoint(CDP_URL)` switches to MCP | both probed in cascade |
| env override | none | `SCRAPE_CASCADE` env var |
| Apify-block detection | YES (L1033-1039 — checks for "环境异常"/"请完成验证"/"请登录" + `<500 chars`) | NO — accepts any non-None markdown |
| caller path | direct CLI → `python ingest_wechat.py <url>` | batch cron → `batch_ingest_from_spider` → `lib.scraper.scrape_url` |

**This is the 2026-05-08 lesson learned (CLAUDE.md "Cascade order divergence between `lib/scraper.py` and `ingest_wechat.py`") repeating in disguise**. The 2026-05-08 fix (`fab60e0`) reordered `lib/scraper.py` to UA-first, but the parallel cascade in `ingest_article:1024-1049` was NOT touched in `fab60e0` and still exists. The `_is_mcp_endpoint` gate at L1044 is also asymmetric — `lib/scraper.py` would call MCP via `getattr(ingest_wechat, "scrape_wechat_mcp")` regardless of CDP_URL suffix, while `ingest_article` here would route to CDP if URL is not `/mcp`-suffixed. **HIGH-priority finding** — not just style; this is a latent regression-prone divergence mirroring the bug class CLAUDE.md "Lessons Learned 2026-05-08 #1" was supposed to close.

When `python ingest_wechat.py <url>` is run directly (CLI / `__main__`), it goes through this parallel path — NOT through `lib/scraper.py`. When `batch_ingest_from_spider` calls `ingest_wechat.ingest_article`, it ALSO uses this parallel path (the lib/scraper.py cascade only runs for `batch_ingest_from_spider`'s OTHER scrape sites at L1032 + L1047 + L759 — see Signal F).

### #5 — Dual hash schemes

L943: `ckpt_hash = _ckpt_hash_fn(url)` → `lib.checkpoint.get_article_hash` returns SHA-256 first 16 hex chars.
L946: `article_hash = hashlib.md5(url.encode()).hexdigest()[:10]` → MD5 first 10 hex chars.
L1093: `article_hash = hashlib.md5(url.encode()).hexdigest()[:10]` ← **RECOMPUTED** identically (same inputs, identical algorithm).

**`article_hash` is computed twice with identical input → identical output.** L1093 is a vestigial assignment from the pre-cache-branch refactor (when the function had separate code paths). Safe to delete L1093-1095 entirely — small cleanup. But the deeper question: why two hash schemes?

- `article_hash` (MD5[:10]) is the **image-directory namespace** (`BASE_IMAGE_DIR/{article_hash}/img_0.jpg`) and the **LightRAG doc_id** (`f"wechat_{article_hash}"`). Changing this format would orphan thousands of existing image dirs and break LightRAG-stored doc_id references.
- `ckpt_hash` (SHA-256[:16]) is the **checkpoint registry namespace** (`checkpoints/{ckpt_hash}/01_scrape.html`) and the **`_PENDING_DOC_IDS` registry key**.

The Phase 19 SCH-02 comment at L982-985 + L1219-1221 explicitly notes: "doc_id value still uses article_hash (MD5[:10])". So Phase 19 unified the **registry key** to ckpt_hash but kept the **doc_id value** at article_hash to preserve backward compatibility. This is intentional. **Collision risk**: SHA-256[:16] = 64 bits of entropy → birthday collision at ~2^32 articles (4 billion). MD5[:10] = 40 bits → birthday collision at ~2^20 (1 million). Production volume is ~25k articles total, well below either ceiling. **Not a real risk — but the dual scheme adds cognitive load.** Move to a single canonical hash in a future v3.x migration; not a quick.

### #6 — `_verify_doc_processed_or_raise` (L60-L121, called at L1297)

Audit asks: "is it temporary scaffolding or load-bearing?" Answer: **LOAD-BEARING and recently bumped.**

- Quick `260510-h09` (commit `949e3f4`, the file's most-recent commit) added it as an emergency hot-fix for the 2026-05-09/10 ainsert-async-pipeline race.
- Quick `260510-h09b` bumped the budget envelope from 6s → 60s (env-overridable via `OMNIGRAPH_PROCESSED_RETRY` / `OMNIGRAPH_PROCESSED_BACKOFF`).
- The CLAUDE.md "Lessons Learned 2026-05-09/10" entry exists — confirmed via `recent commits` git log: `949e3f4 fix(ingest-260510-h09): inner ingest_article raise on PROCESSED verification failure to close ainsert async-pipeline race`.
- It's actively reachable in production cron (every WeChat ingest hits L1297).
- Removing it re-opens silent ghost-doc bug class (commit msg: "57 DB rows marked ingested while LightRAG only had 8 ghost-free docs").
- 6 integration tests in `tests/integration/test_checkpoint_resume_e2e.py` are currently failing on bare HEAD due to this same race (per T1.5 SUMMARY's "Pytest result vs T1 baseline"). The hot-fix WAS applied to the inner `ingest_article` but the failing integration tests' setup paths bypass it.

**DO NOT touch `_verify_doc_processed_or_raise` in any T2 quick.** It's pre-test-stabilization scaffolding; until the underlying race is properly closed (post-T2 milestone work), this stays.

### #7 — Pending-doc rollback registry

`_PENDING_DOC_IDS: dict[str, str]` at L346 is module-global mutable state. Three operations: register at L987 + L1226, clear at L992 + L1233, read at `batch_ingest_from_spider:294` via `get_pending_doc_id`.

Ordering hazards:
- The cache-hit branch (L987) registers under `ckpt_hash`, calls `ainsert`, clears at L992 — but the surrounding `try/except` at L977-994 swallows exceptions silently. If `ainsert` raises, `_clear_pending_doc_id` is NOT called → STALE entry → next run for same URL sees the registry think the doc is still pending → no rollback would actually fire because `batch_ingest_from_spider` only checks the registry on `asyncio.TimeoutError`, not generic exception.
- The fresh branch (L1226-1233) uses `try/finally` so `_clear_pending_doc_id` always fires. This asymmetry is observable.

**Severity LOW** — the cache-hit `except` is for `ainsert` failures the caller already saw, but worth flagging as a code consistency issue. Aligning the cache-hit branch to use `try/finally` + matching fresh-branch semantics would be a 2-line cleanup with no behavior change.

### Proposed split candidates (no fix code, just slices)

| slice | lines | LOC | extraction confidence | notes |
|---|---|---|---|---|
| `_ingest_cached_article(url, ...)` | L946-999 | ~54 | HIGH | Mirror the existing structure; use try/finally to fix #7 asymmetry |
| `_extract_markdown_by_method(article_data)` | L1075-1089 | ~15 | HIGH | Pure function, no I/O |
| `_build_image_manifest(unique_img_urls, url_to_path, dropped_by_cap)` | L1163-1180 | ~18 | HIGH | Pure mapping helper |
| `_buffer_entities(url, content, article_hash, article_dir)` | L1204-1215 | ~12 | HIGH | I/O contained |
| `_persist_content_hash_if_confirmed(url, full_content, article_hash)` | L1300-1317 | ~18 | HIGH | I/O contained |
| `_compose_full_content(title, url, publish_time, markdown, url_to_path, article_hash)` | L1091, L1184-1196 | ~14 | MEDIUM | "compose markdown body" is conceptually one operation; would need careful threading |

Total ~131 LOC pulled out of `ingest_article` → ingest_article shrinks from 405 → ~280 LOC, all extracts behavior-preserving (each is a contiguous slice with clean inputs/outputs). The 5-stage checkpoint structure stays linear; the cached-vs-fresh branching becomes a single `if cache_hit: return await _ingest_cached_article(...)` early-return. **MEDIUM-sized quick — the most surgical wins for the smallest semantic risk.**

## Migration marker triage (Signal D — archaeology vs load-bearing)

Total markers in current file: 61-64 (per my `grep -cE` count; audit's "76" is broader-pattern count and may be over-counting empty matches or strings). Categorization sample of distinct identifiers found:

| marker | first appears at | semantic role | category |
|---|---|---|---|
| `D-09.01 (TIMEOUT-01)` | L3 | "must be set BEFORE `from lightrag import`" — encodes a load-order constraint | **load-bearing** (any future move of `os.environ.setdefault("LLM_TIMEOUT")` breaks LightRAG's dataclass init) |
| `Phase 7 D-09: embedding_func now lives in lib/` | L139 | explains why the import points to `lib` not `lightrag_embedding` | **decorative** (the import line itself is the truth; comment is archaeology) |
| `Quick 260509-s29 Wave 3` | L141 | LLM dispatcher migration | **decorative** — the import line tells the truth; comment explains "why" but adds no constraint |
| `Phase 5-00b R4 fix` | L150-153, L901-906 | DeepSeek extract entities migration | **decorative** — the function body is the truth |
| `HYG-02 (Phase 18-01): hard cap on kept images` | L230-232 | explains the 60-image cap rationale | **load-bearing** (anyone considering raising the cap needs to know the 14-min hang from "Wave 0 Close-Out § F") |
| `Phase 11 D-11.08 / Plan 11-02` | L274 | Vertex guard rationale | **load-bearing** (audit issue #1 root cause; deletion of guard reopens Vertex contradiction) |
| `D-09.07 (STATE-04) — breaking change` | L294 | get_rag fresh-per-call contract | **load-bearing** (test contract; `test_get_rag_contract.py` enforces) |
| `D-09.05 (STATE-02) — pending doc_id tracker` | L342 | rollback registry contract | **load-bearing** (batch_ingest_from_spider:294 reads via get_pending_doc_id) |
| `Phase 8 IMG-04 aggregate log` | L471 | emit_batch_complete preservation | **load-bearing** (image_pipeline observability contract) |
| `Quick 260508-ev2 F1a: Apify dual-token rotation` | L189-190, L629-633, L670-675 | dual-token implementation | **load-bearing** (production cron uses APIFY_TOKEN_BACKUP per CLAUDE.md 2026-05-08 #1) |
| `Phase 12 CKPT-01: per-image Vision checkpoint` | L419 | per-image checkpoint write | **load-bearing** (resume contract) |
| `Phase 12 D-SUBDOC` | L441, L454, L1257 | terminal marker contract for no-image / no-success branches | **load-bearing** (resume gates against this) |
| `2026-05-10 hot-fix (quick 260510-h09)` | L47-54 + L82-83 + L1293-1296 | PROCESSED verification gate | **load-bearing** (see Section C #6) |
| `Phase 19 SCH-02 (Rule 1 auto-fix): tracker key is ckpt_hash` | L982-985, L1219-1221 | dual-hash unification rationale | **load-bearing** (registry-key contract) |
| `Phase 5-00b: extract_entities now on DeepSeek` | L153-155, L901-906 | DeepSeek migration explainer | **decorative** (function body shows current state; comment is git archaeology) |
| `Plan 05-00c Task 0c.3` | L143, L280, L283 | LightRAG LLM_func dispatcher rationale | **decorative** |
| `LDEV-04 (quick task 260504-g7a)` | L158-162 | local dev provider dispatch | **decorative** (the `from lib.llm_complete import get_llm_func` line at L163 already encodes the truth — and there's a duplicate of the same import at L146 from a different migration phase, see TL;DR #3) |
| `2026-05-05: suppress structlog INFO/WARNING noise` | L9-10 | log-level suppression rationale | **decorative** (operational note) |
| Various `Phase N` standalone refs | scattered | minor patches | mostly **decorative** |

### Triage summary

- **Load-bearing markers** (≈ 25-30 of 61-64): encode contracts, ordering constraints, env-var semantics, or test pins. **DO NOT TOUCH.** Moving them detaches a contract from its rationale.
- **Decorative markers** (≈ 30-35): describe past migrations whose result is now the canonical code. Could be moved to the function/module docstring, deleted entirely, or stripped to a single line ("Phase X 2026-NN-NN: refactored extract_entities to DeepSeek").
- **Possible doc-only sweep**: if `.planning/` already documents Phase 5/7/8/10/11/12/13/17/18/19, a 30-line cleanup quick could remove ~25 decorative markers. **LOW-priority cleanup quick** — does not fix any production issue, just helps readers. Risk: removing a marker that was actually load-bearing turns it into invisible debt (the current explicit form is at least flagged for the reader). Recommended ONLY paired with a one-time docstring index in CLAUDE.md or `.planning/INDEX.md` so the migration history is preserved at a single discoverable location.

## Test coverage analysis (Signal E)

15 test files import or reference `ingest_wechat`, totaling **3494 LOC** (vs source 1406 LOC, ratio 2.48 — but no exact-match `tests/unit/test_ingest_wechat.py` file exists; coverage is fragmented).

| test file | LOC | what it pins | gap risk if file moves |
|---|---|---|---|
| `tests/unit/test_status_is_processed.py` | 68 | `_status_is_processed` private helper (post-260510-h09) | LOW — single function, easy to relocate |
| `tests/unit/test_ingest_article_processed_gate.py` | 204 | `_verify_doc_processed_or_raise` retry+raise contract | LOW |
| `tests/unit/test_apify_rotation.py` | 69 | `scrape_wechat_apify` dual-token rotation | **HIGH** — pinned to function name; would break on relocation without coordinated test rewrite |
| `tests/unit/test_apify_run_input.py` | 134 | `scrape_wechat_apify` run_input shape (Apify SDK call) | **HIGH** — same pinning |
| `tests/unit/test_scrape_cascade_order.py` | 125 | All 4 `scrape_wechat_*` functions via `monkeypatch.setattr(ingest_wechat, "scrape_wechat_*", ...)` | **HIGH** — directly pins all 4 names |
| `tests/unit/test_scraper_ua_img_merge.py` | 192 | All 4 `scrape_wechat_*` functions same pattern + `process_content` | **HIGH** |
| `tests/unit/test_mcp_scraper_tool_name.py` | 47 | `scrape_wechat_mcp` tool name string assertion | **HIGH** |
| `tests/unit/test_image_cap.py` | 105 | `_apply_image_cap` + `MAX_IMAGES_PER_ARTICLE` | LOW |
| `tests/unit/test_get_rag_contract.py` | 122 | `get_rag(flush=...)` signature + fresh-per-call contract + production-callers grep | MEDIUM — also greps **other production files** for `get_rag(flush=True)` literal |
| `tests/unit/test_rollback_on_timeout.py` | 178 | `_PENDING_DOC_IDS` registry contract via `_register/_clear/get_pending_doc_id` | LOW (3 small helpers) |
| `tests/unit/test_text_first_ingest.py` | 533 | end-to-end ingest_article with mocked rag + scrape; pins Vision spawn return shape | MEDIUM — large + many internals mocked |
| `tests/unit/test_vision_worker.py` | 566 | `_vision_worker_impl` directly | LOW |
| `tests/unit/test_checkpoint_ingest_integration.py` | 525 | ingest_article + _vision_worker_impl + checkpoint stages 1-6 | MEDIUM |
| `tests/unit/test_scrape_first_classify.py` | 403 | imports `ingest_wechat` to call `process_content` | LOW (only one helper used) |
| `tests/integration/test_checkpoint_resume_e2e.py` | 223 | `import ingest_wechat as iw` + full pipeline | MEDIUM |

### Behavior coverage gaps (uncovered or under-covered)

- `ingest_pdf` — **0 tests, 0 in-process callers found**. The PDF path appears live in the audit (CLAUDE.md "Common Commands" mentions `python multimodal_ingest.py`), but `multimodal_ingest.py` was deleted in T1 W3. `ingest_pdf` is now the ONLY PDF-ingest path — and it has no unit tests. **MEDIUM candidate to either delete OR cover.** Specifically: `ingest_pdf` shares ~60% of its body with `ingest_article` (entity buffer, sqlite persist, rag init) but did NOT receive Phase 12 checkpoint integration, nor `_verify_doc_processed_or_raise`, nor pending-doc registry.
- The cache-hit branch (L946-999) is partially covered by integration tests but no unit test specifically asserts the "Vision worker is NOT spawned on cache-hit, returns None" contract. The contract is documented in the docstring (L935-936) but not test-pinned.
- `_persist_entities_to_sqlite` (L209-227) — 0 direct tests. Silent `except: pass` swallows errors; if the schema drifts, the code won't notice.
- The PARALLEL CASCADE at L1024-1049 — covered by `test_scrape_cascade_order.py` and `test_scraper_ua_img_merge.py`, but those tests run against `ingest_wechat`'s functions in isolation. There's no test that verifies the `ingest_article` cache-miss cascade produces SAME RESULTS as `lib/scraper.py:_scrape_wechat()` on the same input. This is the gap that mirrors the 2026-05-08 lessons-learned — see Section C #4.

## Refactor blast radius (Signal F)

Per proposed quick scope:

### Quick A: Extract scrape_wechat_* into lib/scraper_wechat.py (closes lib↔app inversion)

| transitive surface | sites |
|---|---|
| Production code | `lib/scraper.py:162-228` (4 sites: token map, default order, getattr, process_content call) |
| Production code | `ingest_wechat.py:1024-1049` (parallel cascade — would change to `from lib.scraper_wechat import scrape_wechat_*` or stay as fallback) |
| Production code | `batch_ingest_from_spider.py:1032 + 1047` (`import ingest_wechat` + `ingest_wechat.process_content`) |
| Tests | 5 files pinning by name (test_apify_rotation, test_apify_run_input, test_scrape_cascade_order, test_scraper_ua_img_merge, test_mcp_scraper_tool_name) |
| `__main__` block | L1403-1406 — entry-point unaffected (only calls `ingest_article`) |
| Integration tests | `test_checkpoint_resume_e2e.py:52` — imports `ingest_wechat as iw`; would only break if it referenced `iw.scrape_wechat_*` directly (verified: it does not) |

**Risk** — coordinated test + production rewrite; large diff; no behavior change. **MEDIUM blast radius, LOW semantic risk.**

### Quick B: Extract `_ingest_cached_article` slice (in-file refactor of ingest_article)

| transitive surface | sites |
|---|---|
| Production code | `ingest_wechat.py:946-999` (becomes `if cache_hit: return await _ingest_cached_article(...)`) |
| Tests | None broken — no test currently pins the in-line cache-hit body; all tests use `await ingest_article(url)` shape |

**Risk** — single-file diff, ~50 LOC moved; no exported symbol changes. **LOW blast radius, LOW semantic risk.**

### Quick C: Resolve parallel cascade divergence (Section C #4)

Two options, both have radius:
- **Option C-thin**: have `ingest_article:1024-1049` delegate to `lib.scraper.scrape_url(url, type="wechat")`. Risk: the Apify-block detection at L1033-1039 (checks for "环境异常" keywords, drops to None on short content) does NOT exist in `lib/scraper.py` — would need to relocate that detection to lib/scraper, otherwise CLI behavior regresses.
- **Option C-fat**: keep both cascades, but document the divergence in CLAUDE.md "Lessons Learned" so future cron-cascade-tweak quicks get the heads-up. Risk: doesn't fix anything, just flags the regression-prone shape.

**Risk** — Option C-thin is medium-large surface; C-fat is doc-only. **Recommend C-thin only after Quick A lands** (which makes the move easier).

### Quick D: Trivial cleanup — duplicate `get_llm_func` import + L1093 vestigial recompute + L318 hardcoded model

| transitive surface | sites |
|---|---|
| `ingest_wechat.py:146` (delete duplicate) + L163 (keep) | 2 lines |
| `ingest_wechat.py:1093-1095` (delete vestigial recompute of `article_hash`) | 3 lines |
| `ingest_wechat.py:318` (delete `llm_model_name="deepseek-v4-flash"`) | 1 line |
| Tests | None broken — none pin to L318 kwarg shape; `test_get_rag_contract.py` only inspects `flush` parameter |

**Risk** — single-file ~6-line diff; no behavior change. **LOWEST blast radius.**

### Quick E: Decorative-marker sweep

| transitive surface | sites |
|---|---|
| `ingest_wechat.py` | ~25-30 comment-only deletions |
| Tests | None |

**Risk** — pure documentation churn; no behavior change. **Recommend ONLY paired with a one-time `.planning/INDEX.md` of historic Phase/D-XX/Wave IDs** so the archaeology survives. **LOWEST blast radius**, but lowest impact too.

## Findings — fixable as quick(s)

### F-1: Cascade divergence between `ingest_article:1024-1049` and `lib/scraper.py:_scrape_wechat`

- **Severity**: HIGH (mirrors CLAUDE.md "Lessons Learned 2026-05-08 #1" bug class)
- **Surface area**: `ingest_wechat.py:1024-1049` + `lib/scraper.py:212-271`
- **Proposed quick scope**: write a docs/research note inventorying both cascades' order, gates, and short-content detection, THEN unify (Option C-thin above) by relocating Apify-block detection into `lib/scraper.py` and routing `ingest_article`'s cache-miss branch through `lib.scraper.scrape_url(url, type="wechat")`.
- **Risk if attempted**: CLI ingest behavior change if Apify-block detection moves incorrectly; production cron behavior change if `SCRAPE_CASCADE` env var routing diverges between paths.
- **Test coverage required**: new integration test asserting `ingest_article(verification_url)` returns None (matches current behavior); existing `test_scrape_cascade_order.py` + `test_scraper_ua_img_merge.py` must remain green.
- **Estimated quick size**: medium (2-4h)

### F-2: Extract `scrape_wechat_*` into `lib/scraper_wechat.py` (closes lib↔app inversion)

- **Severity**: MEDIUM (architectural correctness; production-stable today)
- **Surface area**: 4 functions + 5 helpers + `_UA_*` state from `ingest_wechat.py:488-883` → new file; `lib/scraper.py:162-271` rewire
- **Proposed quick scope**: create `lib/scraper_wechat.py`; move all WeChat-scrape functions + UA helpers + `_apify_call` + `process_content` + `_is_mcp_endpoint`; drop `getattr` indirection in `lib/scraper.py:228` in favor of dict-of-funcs; rewire 5 test files' monkeypatch targets to `lib.scraper_wechat`.
- **Risk if attempted**: 5 test files would break atomically with the move (mitigation: surgical patch in same commit); CLI single-URL path unaffected; production cron path unaffected.
- **Test coverage required**: existing test suite (15 files) must remain green; integration test `test_checkpoint_resume_e2e.py` must remain green.
- **Estimated quick size**: medium (2-4h)

### F-3: Extract `_ingest_cached_article` from `ingest_article`

- **Severity**: MEDIUM (god-function reduction; in-file refactor)
- **Surface area**: `ingest_wechat.py:946-999`
- **Proposed quick scope**: move L946-999 into private `_ingest_cached_article(url, article_dir, ckpt_hash, rag) -> None`; replace inline body with `if os.path.exists(cache_content): return await _ingest_cached_article(...)`; align `try/except` to `try/finally` for `_clear_pending_doc_id` symmetry with fresh branch (Section C #7).
- **Risk if attempted**: cache-hit semantics change if `try/finally` replaces `try/except` (registry-key clear now fires on exception too — which is the intended fix, but worth flagging in commit message).
- **Test coverage required**: add unit test for cache-hit return-None contract; existing `test_text_first_ingest.py` and `test_checkpoint_ingest_integration.py` must remain green.
- **Estimated quick size**: small (<2h)

### F-4: Trivial cleanups (3 separate small fixes, ship as one quick)

- **Severity**: LOW
- **Surface area**: `ingest_wechat.py` 3 sites: (a) L146 duplicate `from lib.llm_complete import get_llm_func` (delete); (b) L318 `llm_model_name="deepseek-v4-flash"` kwarg (delete — POLLUTION-AUDIT issue #2 final residual); (c) L1093-1095 vestigial `article_hash` recompute + recreate (delete — value already set at L946).
- **Proposed quick scope**: 3 mechanical deletions, one atomic commit; mirror T1.5 quick `260510-onk` pattern.
- **Risk if attempted**: none observed — duplicate import is dead code; recomputed `article_hash` is identical; `llm_model_name` is overridden by `get_llm_func()` dispatcher anyway.
- **Test coverage required**: full pytest baseline must remain identical (no regressions, no new failures).
- **Estimated quick size**: small (<2h)

### F-5: Decide on `ingest_pdf` — cover-with-tests OR delete

- **Severity**: LOW (orphan-candidate)
- **Surface area**: `ingest_wechat.py:1325-1402` (78 LOC) — no in-process callers found; `multimodal_ingest.py` (the supposed PDF entry point) was deleted in T1 W3.
- **Proposed quick scope**: investigate whether `ingest_pdf` is reachable via any skill (`omnigraph_ingest`?) or external script; if not, delete (POLLUTION-AUDIT issue #5 sibling pattern); if yes, add a single integration test pinning the contract + add Phase 12 checkpoint integration to bring it in line with `ingest_article`.
- **Risk if attempted**: deletion risk if any user-side workflow depends on `python ingest_wechat.py <pdf-path>` (the CLI dispatch at L1403-1406 calls `ingest_article`, not `ingest_pdf`, so PDF path requires direct import — likely 0 callers, but verify with a wider grep including notebooks + scripts).
- **Test coverage required**: pre-delete grep verifying 0 callers (T1 W3 pattern); post-delete pytest baseline.
- **Estimated quick size**: small (<2h investigation; 30min delete or 2-3h test+integrate)

### F-6: Decorative-marker sweep + `.planning/INDEX.md`

- **Severity**: LOW (readability only)
- **Surface area**: `ingest_wechat.py` ~25-30 comment-only deletions; new `.planning/INDEX.md` (~80 LOC mapping Phase/D-XX/Wave IDs to dates + commit SHAs)
- **Proposed quick scope**: do the sweep ONLY paired with the index; otherwise the archaeology vanishes.
- **Risk if attempted**: removing a marker mistakenly classified as "decorative" turns it into invisible load-bearing debt. Mitigation: every removal must be reviewed manually against the categorization above.
- **Test coverage required**: none (comment-only changes); diff manual review only.
- **Estimated quick size**: medium (2-4h)

## Findings — milestone-scale (defer beyond quick)

### M-1: Unify `article_hash` and `ckpt_hash` into one canonical hash scheme

The dual-hash scheme (Section C #5) is a v3.x migration: requires re-keying all existing `~/.hermes/omonigraph-vault/images/{md5}` directories AND all existing `_PENDING_DOC_IDS` registry semantics AND all existing `wechat_{md5}_images` LightRAG sub-doc IDs. Cannot be done in a quick — production data migration needed. **Defer to v3.5 / v3.6 milestone**.

### M-2: Replace 5-stage checkpoint contract with declarative pipeline

The 5 ordered stages (`scrape → classify → image_download → text_ingest → vision`) are linearly hard-coded in `ingest_article`. Adding a new stage today requires editing the orchestrator + lib/checkpoint markers + manifest schema. A milestone-scale extraction would model stages as `ProtocolPipeline` with each stage declaring `name`, `read_inputs`, `write_outputs`, `idempotent`, allowing reordering / skipping by configuration. Out of T2 scope.

### M-3: Move `_PENDING_DOC_IDS` to a structured store

Module-global mutable dict for cross-process registry is fragile (each process restart loses the registry; rollbacks then can't fire). Production OK because cron is single-process per run, but a multi-worker future needs a SQLite-backed registry. Out of T2 scope.

### M-4: True async-pipeline race fix vs `_verify_doc_processed_or_raise` hot-fix

The 60s retry budget is a band-aid on a LightRAG internal-enqueue race. The 6 currently-failing integration tests in `tests/integration/test_checkpoint_resume_e2e.py` are the symptom. Fixing the race properly (vs increasing timeouts) is post-T2 milestone work — likely involves LightRAG SDK changes or a wrapper around `ainsert` that subscribes to LightRAG's internal queue instead of polling `aget_docs_by_ids`. Already cataloged in CLAUDE.md "Lessons Learned" pending follow-up.

## Lock-points and constraints

Hard constraints any future fix MUST respect:

1. **`getattr`-discoverable function names**: `lib/scraper.py:228` looks up `scrape_wechat_{ua,apify,cdp,mcp}` by string. Renames break production cron.
2. **5-stage checkpoint contract**: per-stage atomic write contract is at `lib.checkpoint` — must remain `.tmp` → `os.rename`. Resume logic depends on stage-marker presence/absence; reordering stages would break resume.
3. **Vision worker spawn semantics**: production fires-and-forgets via `track_vision_task(asyncio.create_task(...))`; tests await the returned task. The contract MUST remain "L1245 returns the task handle" — quick `260509-p1n` already audited and pinned this.
4. **`_verify_doc_processed_or_raise` PROCESSED gate** (260510-h09): MUST raise on failure (NOT silently log). Integration tests currently flaky on bare HEAD due to underlying race; do NOT touch the helper — its presence prevents silent ghost-doc bug class.
5. **Hermes deploy path**: production cron runs `batch_ingest_from_spider.py` which imports `ingest_wechat` at module top. Any breaking change to `ingest_wechat`'s public-by-convention symbols (`ingest_article`, `get_rag`, `get_pending_doc_id`, `_clear_pending_doc_id`, `process_content`) breaks production overnight. **Convention audit needed before any move**: `_clear_pending_doc_id` is private-by-name (leading underscore) but called externally by `batch_ingest_from_spider:307`. If extracted, the new module's `_clear_pending_doc_id` symbol must remain importable.
6. **Phase 12 checkpoint dual-hash contract** (Phase 19 SCH-02): registry key = `ckpt_hash` (SHA-256[:16]); doc_id = `article_hash` (MD5[:10]). Phase 19 explicitly preserved this asymmetry; M-1 above unifies it but only at milestone scale.
7. **Cascade default order**: `lib/scraper.py:173-178` has UA-first ordering per CLAUDE.md "Lessons Learned 2026-05-08 #1". The PARALLEL cascade at `ingest_article:1024-1049` IS NOT identical (Section C #4); F-1 finding addresses this.
8. **`OMNIGRAPH_PROCESSED_RETRY` / `OMNIGRAPH_PROCESSED_BACKOFF` env vars** (added 260510-h09b) — production cron may set these. Renaming would break the override path.

## Cross-quick coordination

- **F-2 (extract `scrape_wechat_*` to lib/scraper_wechat.py) <-> T3 (`batch_ingest_from_spider.py` refactor)**: T3 currently does `import ingest_wechat` + `ingest_wechat.process_content(...)` at L1032 + L1047. After F-2, those would become `from lib.scraper_wechat import process_content` (T3 import paths shift). Must coordinate: F-2 first OR T3 absorb the import shift in its surface map.
- **F-1 (cascade divergence resolution) <-> T3**: T3 owns `lib.scraper.scrape_url(url, type="wechat")` orchestration. If F-1 unifies the parallel cascade by routing through `lib.scraper`, T3 sees one fewer `ingest_wechat.process_content` call site at L1047 (the `_persist_scraped_body` path). Coordinate.
- **F-3 (extract `_ingest_cached_article`) <-> none**: in-file refactor; no cross-quick coupling.
- **F-4 (trivial cleanups) <-> none**: 3 mechanical deletions, no cross-quick coupling. Ship anytime.
- **F-5 (`ingest_pdf` decision) <-> none in T2 territory**: but if any skill or PROJECT.md references `ingest_pdf` as part of `omnigraph_ingest` skill, that would gate the deletion path. Verify before shipping.
- **F-6 (marker sweep) <-> all other Fs**: if any other quick lands first, the post-quick file's markers may shift; F-6 should be LAST in any coordinated wave.

## Already-fixed (excluded from concerns)

T1 + T1.5 closed defects relevant to this file:
- POLLUTION-A (Vertex env clobber across CLI scripts) — **CLOSED via `lib/cli_bootstrap.py`**; `ingest_wechat.py:276` is the one remaining production site BUT it's already correctly guarded (Phase 11 D-11.08 conditional).
- POLLUTION-B (`llm_model_name="deepseek-v4-flash"`) — **PARTIAL**; `ingest_wechat.py:318` is the last residual, T2 territory (now F-4 above).
- POLLUTION-C (`load_env` duplicates) — **CLOSED for `ingest_wechat.py`**: T1 SUMMARY lines 99-107 confirm `ingest_wechat.py:150-151` already uses `from config import load_env; load_env()`.
- POLLUTION-D (`lib/llm_deepseek.py:87` eager import-time check) — **CLOSED**.
- POLLUTION-E (orphans `multimodal_ingest.py`, `scripts/cognee_diag/`) — **CLOSED via deletion**.

Already-audited surfaces NOT touched by this review:
- LightRAG SDK / RAG wrapping (260510-gqu)
- Cognee 422 routing (260509-syd) — note: Cognee paths fully retired in 260510-gfg; `ingest_wechat.py` no longer imports `cognee_wrapper`
- Vision drain hang (`lib/vision_tracking.py` + `ingest_wechat.py:1245` track_vision_task wrapper) (260509-p1n)
- LLM dispatcher migration (`lib/llm_complete.py`) (260509-s29 W3) — `get_llm_func` import at L146/L163 is observed product of this; the duplicate at L146 is a residual oversight (F-4)
- skip_reason_version cohort gate (260509-s29 W2)
- ainsert persistence contract test (260509-t4i)
- Hermes vendor patch (260509-msr)

## Review Complete

- Doc: .planning/audit/INGEST-WECHAT-REVIEW.md (~485 lines)
- Top fixable concerns: 6 — F-1 cascade divergence (HIGH), F-2 lib↔app inversion (MEDIUM), F-3 cache-hit extract (MEDIUM), F-4 trivial cleanups (LOW), F-5 ingest_pdf orphan/cover (LOW), F-6 marker sweep (LOW)
- Milestone-scale issues: 4 — M-1 dual-hash unification, M-2 declarative checkpoint pipeline, M-3 pending-doc registry to structured store, M-4 ainsert race proper fix
- Lock-points identified: 8
- Time elapsed: ~35 min
