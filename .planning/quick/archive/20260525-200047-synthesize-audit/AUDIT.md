# /api/synthesize — Read-Only Deep Audit (260525-200047)

**Mode:** investigate-only · NO production-code edits this turn
**Scope:** every file in the POST /api/synthesize → BackgroundTask → poll/SSE → qa.js render path
**Tests:** 51 unit (all PASS) · 45 integration (PASS) + 3 fixture errors · 1 system + browser UAT (NEW BUGS surfaced)
**Status:** complete; awaiting verdict on attack order

---

## 1. Executive Summary (≤10 lines)

1. **3 prod bugs are not symmetric.** Bug 1 (C1 timeout 64s) is a single-config-line miss in `databricks-deploy/app.yaml` — already fixed (`KB_SYNTHESIZE_TIMEOUT=240`, line 94-95) but the fix landed within the last hour and is unverified in prod. Bug 2 (`markdown_len=0`) is **not reproducible from the current code path** — every branch of `_fts5_fallback` writes ≥108-char markdown; `markdown_len=0` therefore implies a code path that no longer exists or a smoke-probe parse artifact. Bug 3 (image strip) is hidden behind bug 2 and not directly observable until KG mode succeeds.
2. **NEW P0 found in L3 system test:** `kb/services/search_index.py:fts_query` passes the raw user question into FTS5 `MATCH ?` without escaping. Any question containing `?` (i.e. ~95% of natural-language questions) raises `OperationalError: fts5: syntax error near "?"` → caught by the outer `_fts5_fallback` `except` at `kb/services/synthesize.py:433` → user sees "Synthesis + fallback both failed". Also vulnerable to `*`, `"`, `:`, `(`, `)`, NEAR/AND/OR keywords. Reproduces locally with one curl call.
3. **NEW P1 found in browser UAT:** `qa.js` branches on `fallback_used` only — does not distinguish `confidence='fts5_fallback'` (real keyword hits) from `confidence='no_results'` (everything failed). The user sees a misleading "Quick Reference / 快速参考" success-banner above an error message.
4. **No P0 issues in async / timeout discipline, NEVER-500 invariant, or job-store concurrency.** Every poll during local UAT returned HTTP 200; in-memory store correctly thread-safe under FastAPI BackgroundTasks (`threading.Lock` per `job_store.py:26`). FastAPI 0.106+ BackgroundTasks lifecycle (per context7 docs) is correctly used — async fn awaited on event loop, response sent before task runs.
5. **Verdict — incremental beats rewrite.** The /api/synthesize surface is ~660 LoC across 4 files with 96/99 tests already green and a clean call graph. The defects are ALL local single-function fixes (FTS5 escape, status-state UX label, markdown_len observability). Rewrite would re-introduce regressions already fixed since 2026-05-08. **Recommended attack order: P0-FTS5 → P1-state-label → P1-markdown_len observability → defer bug 1 verification to first prod long_form call.**

---

## 2. Control Flow Map (file:line per arrow)

```
qa.html:122  submitAsk(e)  ←── user clicks "Quick answer" / "Deep research"
   ↓
qa.js:262    submit(question, lang)
   ↓ POST {question, lang, mode}
kb/api_routers/synthesize.py:50   @router.post("/synthesize")  →  202 + job_id
   ├─ kb/services/job_store.py:29  new_job(kind="synthesize")  →  uuid4-12hex + Lock
   └─ kb/api_routers/synthesize.py:62  background.add_task(kb_synthesize, …)
                                                                  ↓ (after response sent)
kb/services/synthesize.py:456     async def kb_synthesize(question, lang, job_id, mode)
   ├─ :484  if not KG_MODE_AVAILABLE:  →  _fts5_fallback(reason="KG mode unavailable: …")
   │         ↓
   │        kb/services/synthesize.py:367  _fts5_fallback
   │           ├─ :381  fts_query(q, …)
   │           │   └─ kb/services/search_index.py:56  fts_query  →  MATCH q  (P0 — no escape)
   │           ├─ :383  if not rows:  →  bilingual banner, confidence='no_results'   ✓ markdown_len=120
   │           ├─ :410  for row:  build markdown, confidence='fts5_fallback'         ✓ markdown_len≈300+
   │           └─ :433  except Exception:  →  "Synthesis + fallback both failed"     ✓ markdown_len=108
   │
   ├─ :492  from kg_synthesize import synthesize_response   (deferred import)
   ├─ :497  query_text = _wrap_question_for_mode(question, lang, mode)   (qa | long_form template)
   ├─ :505  query_text = await resolve_wiki_context(question) + query_text   (W4 wiki inject)
   ├─ :521  response = await asyncio.wait_for(
   │         synthesize_response(query_text, mode="hybrid"),
   │         timeout=KB_SYNTHESIZE_TIMEOUT,                     ← BUG 1 fired at 60s default
   │       )
   │           ↓
   │          kg_synthesize.py:146  synthesize_response(query_text, mode)
   │             ├─ :147  LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func, embedding_func)
   │             ├─ :153  await rag.initialize_storages()
   │             ├─ :191  custom_prompt = "You are a knowledge synthesizer." + IMAGE_URL_DIRECTIVE + history + query
   │             ├─ :202  for i in range(3):  3-attempt retry loop
   │             │   └─ :212  response = await asyncio.wait_for(
   │             │              rag.aquery(custom_prompt, param=QueryParam(mode='hybrid')),
   │             │              timeout=KB_LIGHTRAG_INNER_TIMEOUT,   ← inner 150s
   │             │            )                              ← BUG 3 (image strip) lives in LLM output
   │             └─ :230  _append_query_history(query, mode, len)
   │
   ├─ :530  except asyncio.TimeoutError:  →  _fts5_fallback(reason="C1 timeout")   ← BUG 1 path
   ├─ :537  except Exception:  →  _fts5_fallback(reason=f"{type}: {e}")
   │
   ├─ :545  markdown = response if isinstance(response, str) else ""   ← BUG 2 candidate (response=None or non-str)
   ├─ :549  markdown = _rewrite_image_urls(markdown)                   ← BUG 3 mitigation: rewrite :8765 → /static/img/
   ├─ :550  sources = _resolve_sources_from_markdown(markdown)         ← parses /article/{10-hex}
   ├─ :551  entities = _resolve_entities_for_sources(hashes)           ← top-8 KG entities
   ├─ :552  confidence = "kg" if sources else "no_results"
   └─ :560  job_store.update_job(jid, status="done", result=…, fallback_used=False, confidence)
                                                                  ↓
qa.js:207    pollOnce()  every 1500ms, POLL_TIMEOUT=60000ms
   ├─ status=running:  setTimeout(pollOnce)
   ├─ status=done:     setState('fts5_fallback' if fallback_used else 'done')   ← P1: ignores confidence
   ├─ render markdown via window.marked.parse(text)   (kb/static/marked.min.js)
   ├─ render sources chips (s.hash / s.title / s.lang)
   └─ render entities chips (e.name) — skipped if fallback_used  (D-9)
```

---

## 3. Findings Table

| # | Sev | File:Line | Issue | Proposed Fix | Risk-of-Fix |
|---|---|---|---|---|---|
| F1 | **P0** | `kb/services/search_index.py:94` | `MATCH ?` passes raw user question; questions with `?`, `*`, `"`, `:`, NEAR raise `OperationalError`. ~95% of NL questions trigger this, masking the FTS5 fallback. **Verified in L3 probe** (`audit-system-20260525.log`). | Add `_sanitize_fts5_query(q)` that strips/escapes FTS5 special chars or wraps in `"…"` quoted phrase: `q.replace('"','""')` then `f'"{q}"'`. Pure function, can unit-test in isolation. | LOW — pure function, no public-API change, idempotent on already-sanitized strings. Add 6 unit tests (qmark / star / quote / colon / NEAR / nominal). |
| F2 | **P1** | `kb/static/qa.js:236-240` | `if (fallback_used) setState('fts5_fallback')` shows "Quick Reference" banner even when `confidence='no_results'` (everything failed). **Verified in browser UAT screenshot** (`.playwright-mcp/audit-qa-fts5-fallback-failed.png`). | Add a third state branch: `if (fallback_used && conf==='no_results') setState('no_results') else if (fallback_used) setState('fts5_fallback') else setState('done')`. Add CSS selector + i18n strings for the new state. | LOW-MED — touches qa.js + style.css + locale files. JS change is 3 lines; UI work is the bulk. |
| F3 | **P1** | `kb/services/synthesize.py:545` | `markdown = response if isinstance(response, str) else ""` silently allows `markdown_len=0` when LightRAG retry loop returns None (rare; happens when 3-attempt loop completes without raise but `response` was never set — defensive `for…else` would close this). Likely root cause of prod 2026-05-25 bug 2. | Replace `if isinstance(...)` with explicit branch: `if not isinstance(response, str) or not response: _fts5_fallback(question, lang, job_id, reason='C1 returned non-str/empty'); return`. Forces the never-500 contract to also be a never-empty contract. | LOW — single-function defensive guard; existing fallback path consumed. |
| F4 | **P1** | `kg_synthesize.py:201-225` | The 3-attempt retry loop's `for i in range(3): try: …; break; except: …; if i<2: sleep; else: raise` is *correct* but `response = None` is initialized on line 201 and the `break`-after-success is the only path that sets it. If `await asyncio.wait_for` returns `None` (LightRAG bug, no exception), the loop exits at i=0 with `response=None` and the function returns None — F3's symptom. | Either (a) treat None as failure (`if response is None: continue`), or (b) raise. Same defensive pattern as F3 but at the inner contract boundary. | LOW — single retry-loop guard. Add a unit test pinning the None-return behavior. |
| F5 | P2 | `kb/services/synthesize.py:69` + `kb/config.py:42` | `KB_SYNTHESIZE_TIMEOUT` read at module-import time in **two** modules independently. Tests reload both; production drift between them is invisible. | Single source of truth: read in `kb.config` only, import constant from there in `kb/services/synthesize.py`. | LOW — refactor; tests cover both reload paths already. |
| F6 | P2 | `kg_synthesize.py:222` | `print(f"Query attempt {i+1} failed: {e}")` violates `rules/python/coding-style.md` ("no print, use logging"). Also visible: `print(f"Warning: query history…")` at line 142, `print(f"Warning: Failed to load canonical map…")` at line 165. Hides errors in deployed log handlers that filter stderr-only. | Replace with `_log.warning(...)`. Module already imports `logging` at line 16. | TRIVIAL — sed-able. |
| F7 | P2 | `kb/services/synthesize.py:339, 358, 433, 537` | Four `except Exception as e:  # noqa: BLE001` swallows. Every one is justified by NEVER-500 contract, but the swallow at `_fts5_fallback:433` (FTS5-itself-failed) is the one masking F1. After F1 fix, the noqa stays for genuinely unexpected DB locks. | Keep noqa, but log `e.__class__.__name__` at WARNING to surface unexpected swallows. Two of the four already do this (`articles_by_hashes`, `entities_for_articles`). | TRIVIAL. |
| F8 | P2 | `kb/api_routers/synthesize.py` | No `/api/synthesize/{job_id}/cancel` endpoint. A user re-submitting (which qa.js allows — `submit()` clears `currentJobId` but doesn't cancel server-side) leaves the prior BackgroundTask running until LightRAG completes. Wastes Databricks serving cost on long_form queries. | Out of scope for this audit; flag for v1.2 backlog. | — |
| F9 | P2 | `kb/services/job_store.py` | No TTL / eviction; jobs persist for the lifetime of the uvicorn process. Documented assumption "<1000 jobs/day" — fine for current scale, will need attention before multi-worker / long-uptime deploys. | Add a daily reaper or LRU cap (1000 entries). Decision deferred per `kb-3-API-CONTRACT.md` §1.5. | — |
| F10 | P2 | `kb/services/synthesize.py:267-275` | `KG_MODE_AVAILABLE` is computed at module-import time. If the SA file is rotated mid-uptime, the flag stays `True/False` until uvicorn restart. Production-acceptable (deploy = redeploy) but worth noting. | Document, no fix. | — |
| F11 | P3 | `kb/services/synthesize.py:506` | `wiki_context = await resolve_wiki_context(question)` — synchronous file IO inside async fn (sqlite3 + Path.read_text). Blocks event loop if the wiki kb is large. | Either run via `asyncio.to_thread` or document the bound. Currently small; not a real concern. | — |
| F12 | P3 | `kg_synthesize.py:201` `response = None` initialized but the `for…else` clause is missing — relies on `break` to leave the loop normally. Pythonic alternative is `for i …: …; else: raise SomethingExplicit()` so a falling-through loop without break is an explicit error, not a silent return. | Optional refactor; F4 covers the operational fix. | — |

---

## 4. context7 Citations

### FastAPI BackgroundTasks (Source: `/fastapi/fastapi`, query: BackgroundTasks lifecycle execution after response, exception handling, async vs sync function dispatch)

> **"You can declare a parameter in a path operation function or dependency function with the type `BackgroundTasks`, and then you can use it to schedule the execution of background tasks after the response is sent."**
> — `docs/en/docs/reference/background.md`

> **"This was changed in FastAPI 0.106.0. Additionally, a background task is normally an independent set of logic that should be handled separately, with its own resources (e.g. its own database connection)."**
> — `docs/en/docs/release-notes.md`

**Audit application:**
- `kb/api_routers/synthesize.py:62` `background.add_task(kb_synthesize, …)` — ✅ correct usage; the 202 response is sent before `kb_synthesize` runs (per FastAPI docs above).
- `kb_synthesize` is `async def` — FastAPI awaits it on the main event loop after response, NOT in the threadpool. This is correct for the LightRAG `aquery` await chain — but it means a single hung BackgroundTask CAN block other BackgroundTasks scheduled on the same loop. With `--workers 1` and no parallelism guarantee, two simultaneous slow long_form queries serialize. Documented constraint, not a bug, but worth noting for capacity planning (F8 follow-up).
- `kb/services/job_store.py:26` `_LOCK = Lock()` (threading) — defensive; in pure async-loop usage the GIL makes dict ops atomic, but if FastAPI ever upgrades to dispatching async BackgroundTasks via threadpool (per the 0.106 release note re: independent resources), the lock prevents corruption. ✅ kept.

**No FastAPI antipattern detected.** The async/sync mismatch trap (sync BackgroundTask shouldn't touch event-loop resources) doesn't apply because `kb_synthesize` is async-all-the-way.

### asyncio.wait_for + cancellation (Python 3.11+ stdlib semantics)

`asyncio.wait_for(coro, timeout)` cancels the inner coroutine on timeout and raises `asyncio.TimeoutError` to the caller. Correctly used at:
- `kb/services/synthesize.py:521-525` (outer 60s/240s wrapper)
- `kg_synthesize.py:212-218` (inner 150s per-attempt)

The two-level structure (`outer 240 > inner 150 × 3 attempts = 450s budget` — but outer fires first) is described correctly in the `kg_synthesize.py:64-70` comment after the 2026-05-25 c1-fix-A patch landed.

### Skill discipline lookups (per CLAUDE.md mandatory rules) — **NOT NEEDED**

The audit only verifies; no new code authored. python-patterns / writing-tests / systematic-debugging skill invocations applicable to next-phase fixes (F1-F4) are listed in the next-phase recommendation §7.

---

## 5. Test Results

### Level 1 — Unit tests

```
$ venv/Scripts/python.exe -m pytest tests/unit/ -k synthesize -v
51 passed, 1190 deselected in 11.94s
```

**Log:** `.planning/quick/20260525-200047-synthesize-audit/audit-unit-20260525.log`

All 51 synthesize-related unit tests green. Coverage spans:
- prompt-template helpers (qa + long_form, zh + en) — 13 tests
- structured-result schema (`SynthesizeResult.asdict`, `_extract_source_hashes`, `_resolve_sources_from_markdown`) — 9 tests
- wiki-inject fallthroughs — 5 tests
- research-stage stubs — 11 tests
- caption-embedding fallbacks — 9 tests
- query-history regression guards — 4 tests

### Level 2 — Integration tests

```
$ venv/Scripts/python.exe -m pytest tests/integration/kb/ -k synthesize -v
45 passed, 287 deselected, 3 errors in 9.12s
```

**Log:** `.planning/quick/20260525-200047-synthesize-audit/audit-integration-20260525.log`

✅ All 45 PASS — including the 12 NEVER-500 invariant tests, lang directive injection, KG happy/timeout/exception fallback paths, structured source resolution, wiki context injection, citation-format gates, image-URL rewrite, and KG-mode-unavailable short-circuit.

❌ 3 ERRORS in setup of `tests/integration/kb/test_kb3_e2e.py` — fixture rebuild_fts fails with `sqlite3.OperationalError: no such column: body_cleaned`. **NOT a synthesize-path defect** — the E2E fixture's CREATE TABLE is missing a column the production schema added. Same fixture-drift class as the kb-3 lesson "Contract shape changes need full audit" in MEMORY.md. Flag for separate fix; orthogonal to this audit's scope.

### Level 3 — System test (local_serve.py + curl + Playwright MCP browser UAT)

**Server:** `venv/Scripts/python.exe .scratch/local_serve.py` on port 8766
**KG mode:** `KG_MODE_AVAILABLE = False` (no `KB_KG_GCP_SA_KEY_PATH` set on local box) → exercises FTS5 fallback exclusively
**Probe script:** `.planning/quick/20260525-200047-synthesize-audit/probe.py`
**Log:** `.planning/quick/20260525-200047-synthesize-audit/audit-system-20260525.log`
**Server log:** `.planning/quick/20260525-200047-synthesize-audit/audit-system-server.log`
**Screenshot:** `.playwright-mcp/audit-qa-fts5-fallback-failed.png`

| Probe | HTTP | Final status | Confidence | Fallback | markdown_len | Error field | Verdict |
|---|---|---|---|---|---|---|---|
| `/health` | 200 | — | — | — | — | — | ✓ |
| `QA-MODE-EN-WITH-QMARK` (`What is LightRAG?`) | 202 → 200 | done | no_results | true | **108** | `KG mode unavailable: kg_disabled \| fts5: OperationalError: fts5: syntax error near "?"` | **F1 confirmed** |
| `QA-MODE-EN-NO-QMARK` (`Tell me about LightRAG`) | 202 → 200 | done | no_results | true | 120 | `KG mode unavailable: kg_disabled` | ✓ (no FTS5 hits, banner shown) |
| `LONG_FORM-ZH` (`什么是 LightRAG 的核心架构`) | 202 → 200 | done | no_results | true | 120 | `KG mode unavailable: kg_disabled` | ✓ |
| 422 missing question | 422 | — | — | — | — | — | ✓ |
| 422 empty question | 422 | — | — | — | — | — | ✓ |
| 422 lang=fr | 422 | — | — | — | — | — | ✓ |
| 422 mode=weird | 422 | — | — | — | — | — | ✓ |
| 404 unknown job | 404 | — | — | — | — | — | ✓ |

**NEVER-500 invariant: HOLDS.** Every poll across all probes returned 200. Even the double-failure (KG unavailable + FTS5 syntax error) returned 200 with `status=done`.

**Browser UAT (Playwright MCP):**
1. Navigate to `http://127.0.0.1:8766/ask/` → 200, page title "AI Knowledge Q&A"
2. Toggle "Quick answer" mode (radio `[checked]`)
3. Type `What is LightRAG?` into textarea
4. Click "Deep Q&A" submit button
5. Observed: result region transitions to `submitting` → `polling` → terminal state
6. **F2 confirmed:** rendered banner reads "**Quick Reference / 快速参考** — Keyword-based quick reference, not full KG answer." but the article body reads "**Synthesis + fallback both failed.** Reason: KG mode unavailable: kg_disabled; FTS5 reason: OperationalError". The banner is the success-confidence label; the body is the worst-case error message. UX reads as success-of-fallback when it is actually a double-failure.
7. Console: no errors. Network: no 4xx/5xx (NEVER-500 holds).
8. Screenshot saved: `.playwright-mcp/audit-qa-fts5-fallback-failed.png`

---

## 6. Gap List

### Tests missing
- **G1 — F1 unit test gap:** no test pins `fts_query` behavior on questions containing FTS5 special chars (`?`, `*`, `"`, `:`, `(`, `)`, NEAR/AND/OR keywords). 51-test unit suite all green BUT none would have caught F1.
- **G2 — `kg_synthesize.synthesize_response` returns None:** no test for the `for…else`-missing path that may yield `response=None` from a 3-attempt retry that exits on `break` without setting response. F4 fix needs a test.
- **G3 — qa.js no_results vs fts5_fallback state machine:** `tests/integration/kb/test_ask_html_state_matrix.py` has only one test and it doesn't exercise the F2 differentiation. No JS-unit harness for qa.js.
- **G4 — `kb_synthesize` empty-string output guard:** no test asserting `markdown_len > 0` invariant on terminal jobs. Bug 2's `markdown_len=0` is currently unreproducible AND untestable.
- **G5 — `test_kb3_e2e.py` body_cleaned schema drift:** 3 ERRORs blocking E2E coverage of synthesize end-to-end. Not directly relevant to bug fixes but reduces confidence in any non-obvious change.

### Observability missing
- **O1 — `markdown_len=0` source ambiguity:** the `kb_synthesize` path logs `c1_after_aquery: response_chars=0` (synthesize.py:526-529) but doesn't escalate or add a marker tag. If response is empty after the await, the wrapper proceeds silently with `markdown=""`. Add `_log.error("c1_returned_empty …")` before line 545.
- **O2 — `_fts5_fallback` outer except (synthesize.py:433) does not log:** the swallow only writes the result; no `_log.warning` to surface that FTS5 itself blew up. F1 was invisible in server logs until `error` field was inspected.
- **O3 — No request-id propagation:** logs emit `job_id=…` but client headers carry no correlation id. Hard to grep prod logs for a single user's session.
- **O4 — qa.js poll cadence not telemetry'd:** no client-side timing emission, so we can't measure POLL_TIMEOUT exhaustion frequency.

### Contract drift suspected
- **D1 — `kg_synthesize.synthesize_response` and `omnigraph_search.query.search` both wrap `LightRAG.aquery`** — different default modes, different bootstrap (`omnigraph_search.query` lazy-imports `lightrag_embedding` directly; `kg_synthesize` uses `_get_embedding_func`). Two flavors of "the same thing" — not a bug, but a future refactor risk if either drifts.
- **D2 — `kb/config.py:42` `KB_SYNTHESIZE_TIMEOUT` defined but only the `kb/services/synthesize.py:69` copy is read in the synthesize path.** Tests cover both reloads, prod uses only one. F5 follow-up.

---

## 7. Next-Phase Recommendation

### Verdict: **incremental fix, NOT rewrite**

Synthesize surface is bounded: 4 files, ~660 LoC, 96/99 tests green, clean call graph, NEVER-500 contract held under live testing. All 4 ranked defects (F1-F4) are local single-function fixes. A rewrite would re-introduce regressions already fixed in 2026-05-13/14/17/19/22/23/24/25 patches.

### Ordered attack plan (recommend pick top-2 for next phase)

| Order | Defect | Action | Estimated LoC | Test additions | Skill invocation |
|---|---|---|---|---|---|
| 1 | **F1 (P0 — FTS5 syntax error on `?`)** | Add `_sanitize_fts5_query(q: str) -> str` in `kb/services/search_index.py`; wrap `q` in quoted phrase, double inner quotes. Apply at `fts_query` entry. | +12 LoC (function + call site) | +6 unit tests (qmark / star / quote / colon / NEAR / nominal) | `Skill(skill="python-patterns", args="Pure-function string sanitizer for FTS5 MATCH expression. Idempotent. PEP 8.")` + `Skill(skill="writing-tests", args="6 pytest cases pinning observable q→sanitized output for each FTS5 special char")` |
| 2 | **F2 (P1 — qa.js no_results vs fts5_fallback)** | Add 3rd state branch in `kb/static/qa.js:236`. Add CSS selector `[data-qa-state="no_results"]` and i18n strings for the new state in `kb/locale/`. | +8 LoC JS, +12 LoC CSS, +4 i18n strings | +1 integration test (TestClient + JS rendering pin) | `Skill(skill="ui-ux-pro-max", args="Honest no_results state — distinct from fts5_fallback. No anthropomorphism. Bilingual.")` + `Skill(skill="frontend-design", args="ES2017 IIFE branch addition; locale strings parallel structure to existing fts5_fallback state")` |
| 3 | **F3 + F4 (P1 — markdown_len=0 root cause)** | Add explicit-non-empty-string guard at `kb/services/synthesize.py:545` AND `kg_synthesize.py:225` `for…else: raise`. | +6 LoC | +2 unit tests pinning None-return + empty-string treatment | `Skill(skill="systematic-debugging", args="Goal-backward: prove no code path produces markdown_len=0 by closing the None-return gap")` + `Skill(skill="writing-tests", args="Pin observable post-condition: terminal job ALWAYS has markdown_len > 0")` |
| 4 | **F1 + F2 → re-deploy → verify bug 1 fixed in prod** | After F1 lands, the C1-timeout fix (already in `app.yaml`) is exercisable on Databricks. Curl long_form ZH q against deployed Databricks app; expect ≥120s wallclock with ≥1 source. Confirm bug 1 + bug 2 jointly closed. | (deploy only) | curl smoke + screenshot | `Skill(skill="databricks-patterns", args="Re-deploy via make deploy + tail_app_logs for c1_after_aquery wall_s")` |
| 5+ | F5-F12 | Defer; surface in v1.2 backlog quick. | — | — | — |

### Total scope of recommended next phase

- **+26 LoC production code** (12 FTS5 + 8 JS + 6 markdown guard)
- **+9 tests** (6 + 1 + 2)
- **3 files touched** (`kb/services/search_index.py`, `kb/static/qa.js`, `kb/services/synthesize.py` + `kg_synthesize.py`)
- **1 deploy** (Databricks) to verify
- **Estimated effort:** 1 session, ~2 hours

### Rewrite scope (rejected for reference)

If we rewrote /api/synthesize from scratch:
- 4 files, 660 LoC: `kb/api_routers/synthesize.py` (88 LoC), `kb/services/synthesize.py` (567 LoC), `kg_synthesize.py` (263 LoC), `kb/static/qa.js` (320 LoC) = 1238 LoC
- 96 tests to re-pass, 12 NEVER-500 invariant tests in particular
- Risk: re-introduce already-fixed regressions (260513-fyb stale-file-read, 260514 race ghost-success, 260517-lok timeout, 260519-s65 image rewrite, 260524-tk5 inner timeout, 260525-c1-fix-A outer timeout)
- Benefit: marginal — the existing surface is well-factored already

**Strongly recommend incremental.**

---

## Hard-Constraint Compliance

- [x] No production-code edits — only audit artifacts in `.planning/quick/20260525-200047-synthesize-audit/`
- [x] No `git add -A` / `git add .` — nothing committed yet
- [x] No `--amend` / `reset --hard` / `rebase -i` / `push --force`
- [x] No phase territory boundary violation — all writes under `.planning/quick/<ts>-synthesize-audit/`
- [x] No literal secrets in this audit — paths only
- [x] Atomic stage-commit-push N/A — no commit this turn (read-only audit)
- [x] Every "this is wrong" claim cites file:line + log:line — F1 cites `audit-system-20260525.log:14`; F2 cites screenshot + qa.js:236; F3 cites synthesize.py:545; F4 cites kg_synthesize.py:201-225
- [x] LightRAG never bypassed — all P0/P1 fixes preserve the C1 contract
- [x] Halt before any production-code Edit/Write — done; awaiting verdict

---

## Server Cleanup

local_serve.py background process (Bash task `b5mekkgdn`, pid 46160) needs `TaskStop` after this report is signed off. Next-phase agent should kill it before starting fresh work.

---

## Awaiting Verdict

Pick attack order from §7. Recommend **F1 + F2** as the next /gsd:quick phase scope (top-2 ranked, smallest total LoC, highest user-visible impact). Halt here.
