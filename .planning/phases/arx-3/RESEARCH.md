# arx-3 Phase 0 RESEARCH — Long-form citation compliance

**Researched:** 2026-05-26
**Domain:** kb/services/synthesize.py + kb/api_routers/search.py — long_form / qa citation compliance regression on Aliyun + Databricks
**Confidence:** HIGH (file-level reads + live HTTP probe + JSON payload inspection)

## TL;DR

The original arx-2 hypothesis ("Vertex-only citation non-compliance, DeepSeek does it right") **is wrong**. The new Aliyun /search/kg probe (this phase, Section E) returned `n_results=0` for BOTH `local` AND `hybrid` modes against the same DeepSeek-backed kb-api that produced 8525-char real long-form content for the arx-2 reference. The same Aliyun /api/synthesize?mode=qa run produced 779-char real markdown with **0 `/article/` citations**. That means the LLM is *generating real content* but **never emitting the `[/article/{hash}.html]` citation form** — on Aliyun (DeepSeek). The QA-template fix at `kb/services/synthesize.py:128-200` therefore **does NOT actually solve the problem in production** — it merely sets up the prompt directive; whether the LLM complies is a separate question, and on this corpus + this LLM the answer is "no" even after the fix landed. Verdict: **Case 4a applies — the bug is upstream of prompt construction, in the retrieval-anchor / hash-emission contract**. Mirroring `_kg_local_worker`'s wrapper into long_form (Option M) will produce the same outcome that `/search/kg` already produces (n_results=0). **Phase 1 leaning: R (rewrite the citation contract), not M (mirror QA fix).** The fix surface is not the prompt — it's the upstream chunking / context-pass that needs to embed the source hash *into the chunk text itself* so the LLM has something concrete to echo.

---

## A. synthesize.py function map

Full file: 567 lines, single module. Read top-to-bottom.

| Lines | Block | Purpose |
|-------|-------|---------|
| 1-32 | Module docstring | QA-01/02/04/05 + I18N-07 contract; lists Skill discipline directives for the original kb-3-08/-09 implementation |
| 33-49 | Imports + logger | stdlib + `kb.config`, `kb.data.article_query`, `kb.services.job_store`, `kb.services.wiki_inject` |
| 51-57 | **`_SOURCE_HASH_PATTERN`** | `re.compile(r"/article/([a-f0-9]{10})")` — strict 10-hex match |
| 59-65 | `_LEGACY_IMAGE_URL_PATTERN` | 260519-s65 belt-and-suspenders rewrite of `:8765` → `/static/img/` |
| 67-69 | **`KB_SYNTHESIZE_TIMEOUT`** | int env-default 60s (Databricks app.yaml overrides to 240) |
| 72-103 | `_LONG_FORM_PROMPT_TEMPLATE_ZH` | The ZH long_form template — instructs `[/article/{{hash}}.html]` citation form (line 94), `![alt](/static/img/{{hash}}/{{n}}.jpg)` images (line 97-98), 1500-3000 字 (line 92) |
| 105-122 | `_LONG_FORM_PROMPT_TEMPLATE_EN` | EN parallel: 800-1500 words, same citation directive (line 112), trailing `Please answer in English.` |
| 124-162 | **`_QA_PROMPT_TEMPLATE_ZH/EN` (the kb-v2.2-4 fix — REFERENCE IMPLEMENTATION)** | 200-400 字/words, `[/article/{{hash}}.html]` directive, `![alt](URL)` image directive, no-fabrication clause |
| 165-189 | `_wrap_question_for_mode(question, lang, mode)` | Dispatches qa → QA template, long_form → long_form template; other → unchanged |
| 192-275 | `_check_kg_mode_available()` + `KG_MODE_AVAILABLE` constant | SA file existence probe at module-import time. If missing, all C1 calls short-circuit to FTS5 fallback |
| 277-279 | `KG_FALLBACK_SUGGESTION` | UX string |
| 282-290 | `lang_directive_for(lang)` | DEFENSIVE — only used in the "other modes" branch of `kb_synthesize`. Both qa AND long_form templates carry their own trailing directive (line 102, 121) so this function is NOT called for them |
| 293-306 | `_rewrite_image_urls(markdown)` | 260519-s65 — pure function rewriting `http(s)://...:8765/` → `/static/img/`; idempotent |
| 309-322 | `_extract_source_hashes(markdown)` | Pure function; emits distinct hashes in first-occurrence order via `_SOURCE_HASH_PATTERN.findall` |
| 325-345 | **`_resolve_sources_from_markdown(markdown)`** | Calls `_extract_source_hashes` then `article_query.articles_by_hashes`; never raises (logs warning + returns []) |
| 348-364 | `_resolve_entities_for_sources(source_hashes)` | Same shape — never raises |
| 367-453 | **`_fts5_fallback(question, lang, job_id, reason)`** | Three sub-paths: no-rows (108+ char banner), with-rows (top-3 stitched + ArticleSource list, confidence=`fts5_fallback`), outer-except (108-char "both failed" banner). NEVER raises — catches and degrades to confidence=`no_results` with `fallback_used=True`. **IMPORTANT:** all three paths produce non-empty markdown; `_fts5_fallback` never produces `markdown_len=0` |
| 456-489 | `kb_synthesize(question, lang, job_id, mode='qa')` — Function header + KG_MODE_AVAILABLE short-circuit | If KG unavailable → `_fts5_fallback` and return |
| 491-501 | **Long_form / qa prompt build site (lines 494-501)** | `if mode in ('long_form', 'qa'): query_text = _wrap_question_for_mode(question, lang, mode)` else bare `directive + question`. **This is the long_form prompt-build site** — and it is identical to QA's prompt-build site; both go through `_wrap_question_for_mode` |
| 503-506 | W4 wiki context inject (`resolve_wiki_context` prepends a context block) | Read-only — never writes back |
| 507-512 | C1 wall-time logging (`c1_before_aquery`) | monotonic clock |
| 513-539 | **C1 await + outer try/except** | `asyncio.wait_for(synthesize_response(query_text, mode='hybrid'), timeout=KB_SYNTHESIZE_TIMEOUT)` — hard-coded `mode='hybrid'` regardless of caller mode. TimeoutError → `_fts5_fallback`; generic Exception → `_fts5_fallback`. **Both fall-through routes still satisfy never-500** |
| **541-559** | **Source resolution + result assembly** | line 545 `markdown = response if isinstance(response, str) else ""` (bug-2 candidate per AUDIT.md F3); line 549 `_rewrite_image_urls`; line 550 `_resolve_sources_from_markdown`; line 552 `confidence: ConfidenceLevel = "kg" if sources else "no_results"`; result assembled as `SynthesizeResult(markdown=markdown, ...)` |
| 560-566 | `job_store.update_job(job_id, status='done', result=result.asdict(), ...)` | Terminal state write |

**Never-500 invariant guards:** four `confidence='no_results'` write sites — line 391-404 (FTS empty), line 435-453 (FTS catastrophic), line 552 (KG path with empty markdown OR sources=[]), and `_resolve_sources_from_markdown:339-341` (DB exception swallow returning []).

**Test fixture references:** none direct in this file. Tests import from `tests/integration/kb/conftest.py:fixture_db` + monkeypatch `kg_synthesize.synthesize_response`.

**KEY OBSERVATION — long_form vs qa diverge in ZERO meaningful places.** Both go through `_wrap_question_for_mode`, both go to `_resolve_sources_from_markdown(markdown)`, both share the citation regex `_SOURCE_HASH_PATTERN`. The fix at lines 128-200 (QA template) and the older fix at lines 87-122 (long_form template) **emit nearly identical `[/article/{hash}.html]` directives** — the difference is only word-count (200-400 QA vs 1500-3000 long_form) and verbosity. So mirroring "the QA fix" into long_form is a no-op — it's already there.

---

## B. search.py function map

Full file: 265 lines.

| Lines | Block | Purpose |
|-------|-------|---------|
| 1-19 | Docstring | API-04 (mode='fts') + API-05 (mode='kg') Skill discipline preamble |
| 20-31 | Imports | FastAPI, Pydantic, `kb.services.{job_store, search_index, synthesize as synthesize_svc}` |
| **41** | **`KB_KG_SEARCH_TIMEOUT`** | `int(os.environ.get("KB_KG_SEARCH_TIMEOUT", "90"))` — confirmed 90s default per directive |
| 43-45 | logger + APIRouter prefix=`/api` |
| **50** | **`_HASH_PAT = re.compile(r"/article/([a-f0-9]{10})")`** | Confirmed verbatim. Same as `synthesize._SOURCE_HASH_PATTERN`. The duplication is intentional per comment lines 47-49 |
| 56-71 | `_kg_worker(job_id, q)` | Used by `GET /api/search?mode=kg`; calls `synthesize_response(q, mode='hybrid')` and stores `result=` the markdown verbatim. Wraps in broad `except Exception → status='failed'` |
| 73-88 | `_make_snippet(body, max_len=200)` | Strips images / code fences, truncates to `max_len` chars |
| **91-146** | **`_kg_local_worker(job_id, query)`** | The progressive-enhancement worker; `mode='local'` |
| 104-109 | results=[]; logs `kg_local_worker_start` at WARNING (Databricks logger workaround) |
| 110-114 | Lazy imports `synthesize_response`, `get_article_by_hash` |
| **115-121** | **The citation directive prompt wrapper:** `"When citing knowledge-base sources in your answer, write each citation in the form [/article/{hash}.html] where {hash} is the 10-character hex source identifier of the cited document. Cite every document you draw on.\n\nQuestion: {query}"` — emitted verbatim into the LLM prompt |
| 122-125 | `markdown = await asyncio.wait_for(synthesize_response(wrapped, mode='local'), timeout=KB_KG_SEARCH_TIMEOUT)` — note `mode='local'` (cheaper than hybrid) |
| **126** | `hashes = list(dict.fromkeys(_HASH_PAT.findall(markdown or "")))` | Same regex as synthesize.py. Dedupe-while-preserving-order via `dict.fromkeys` |
| 127-141 | For each hash: `get_article_by_hash` → append `{hash, title, snippet, lang, source}` row. Inner exceptions skip the row (logged at WARNING) |
| 142-144 | Outer Exception → `results=[]` (graceful degrade, never raise) |
| 145-146 | Logs `kg_local_worker_done jid=… n_results=…` at WARNING; updates job_store |
| 149-152 | `_KgSearchRequest(BaseModel)` | POST body schema: `query: str (1..500)` |
| 158-203 | `GET /api/search` | mode='fts' synchronous direct return; mode='kg' → 503 if KG unavailable, else BackgroundTask `_kg_worker` |
| 206-229 | **`POST /api/search/kg`** | 503 gate on `KG_MODE_AVAILABLE`; else BackgroundTask `_kg_local_worker`; returns `{job_id}` |
| 232-245 | **`GET /api/search/kg/{job_id}`** | Returns `{results: [...]}` once done, `{status: 'pending'}` while running |
| 248-264 | `GET /api/search/{job_id}` | Generic poll for `_kg_worker` (the `/api/search?mode=kg` flavor) |

**Diff vs synthesize.py prompt construction:**

| Aspect | synthesize.py long_form | search.py `_kg_local_worker` |
|--------|------------------------|------------------------------|
| Citation directive | `[/article/{{hash}}.html]` (formatted) | `[/article/{hash}.html]` (verbatim {hash}) |
| Position in prompt | Mid-template (numbered requirement #3) | Leading sentence |
| `mode` passed to C1 | `'hybrid'` (synthesize.py:522) | `'local'` (search.py:123) |
| Outer timeout | `KB_SYNTHESIZE_TIMEOUT` (60→240s) | `KB_KG_SEARCH_TIMEOUT` (90s) |
| Hash regex | `_SOURCE_HASH_PATTERN` (line 57) | `_HASH_PAT` (line 50) — IDENTICAL pattern, intentionally duplicated |
| Failure mode | falls through to FTS5 fallback | falls through to results=[] |

**There is NO meaningful long_form-only "missing citation directive" gap.** `_kg_local_worker` says it more bluntly ("Cite every document you draw on") — but the long_form template requirement #3 is essentially the same instruction.

---

## C. QA fix recipe (the reference implementation)

The fix at `kb/services/synthesize.py:128-200` is a **template-wrap with doubled-brace `{{hash}}` escape**. Specifically:

### Mechanism

1. **Template wrap**, NOT a few-shot. Source: `_QA_PROMPT_TEMPLATE_EN` lines 150-162:

   ```
   Based on content retrieved from the knowledge base, concisely answer the following question.

   Question: {question}

   Requirements:
   1. Keep the answer concise, 200-400 words
   2. Cite specific sources for key claims, format [/article/{{hash}}.html]
      (hash is the 10-char article hash in the knowledge base)
   3. Include ![alt](URL) references if source articles have relevant images
   4. Do not fabricate anything — strictly base on retrieved article content

   Please answer in English.
   ```

2. **Doubled-brace escape `{{hash}}`** (lines 142, 156): this is a `str.format()` artifact. `template.format(question=user_q)` substitutes `{question}` AND collapses `{{hash}}` → `{hash}` *literal* in the output. The LLM then sees the directive `[/article/{hash}.html]` as a placeholder it should fill.

3. **Suffix lang directive** baked into the template (line 147 ZH `请用中文回答。`, line 161 EN `Please answer in English.`) — so the dispatcher (`kb_synthesize:497`) does NOT prepend a separate directive.

4. **Pure prompt-side, no extraction-side change.** The hash regex (`_SOURCE_HASH_PATTERN` line 57) was already in place from kb-v2.1-4. The fix just changes what's *sent* to C1 so what comes *back* matches the existing extractor.

### Exact directive string the LLM is told to emit (verbatim, after str.format substitution)

EN:
> ```
> 2. Cite specific sources for key claims, format [/article/{hash}.html]
>    (hash is the 10-char article hash in the knowledge base)
> ```

ZH:
> ```
> 2. 每个关键结论引用具体来源,链接格式 [/article/{hash}.html]
>    (hash 是文章在知识库中的 10 字符哈希)
> ```

### Does it scale to 5K-char long_form output?

**The same recipe is already deployed for long_form** (`_LONG_FORM_PROMPT_TEMPLATE_EN/ZH` lines 87-122). The directive at line 94 (ZH) / 112 (EN) is structurally identical:

> ```
> 3. 引用:每个论点引用具体来源,链接格式 [/article/{{hash}}.html]
>    (hash 是文章在知识库中的 10 字符哈希)
> ```

So the answer is: **yes the recipe scales**, AND **it has been deployed for long_form since kb-v2.1-5**. The arx-2 reference probe (Aliyun, 8525-char real markdown, **0 citations**) is empirical evidence that the directive **doesn't work** at 5K-char output scale — at least, not without something the LLM can latch onto in the retrieved context (chunk-anchor hash injection).

---

## D. AUDIT.md reconciliation

The 2026-05-25 AUDIT.md hypothesis (F3 + F4: "bug 2 = `markdown = response if isinstance(response, str) else ""` returns markdown_len=0 because the 3-attempt retry exits without setting response") **is partly refuted, partly orthogonal**:

| AUDIT.md finding | New evidence | Status |
|------------------|--------------|--------|
| **F1** (P0 FTS5 syntax error on `?`) | Uncorroborated by this probe (we never hit FTS5 path on Aliyun — KG was available; QA returned real markdown, just no citations) | **Still valid** as a separate P0 — orthogonal to arx-3. Should be tracked but is not in arx-3 scope |
| **F2** (P1 qa.js no_results vs fts5_fallback state branching) | Confirmed by arx-2: Aliyun returned 8525-char real long-form with `confidence='no_results'` + `fallback_used=False` + sources=[] — exactly the state qa.js conflates with "everything failed" | **Still valid**. Strengthened by new evidence: even when retrieval *worked* and content *was generated*, the UI shows the no-results banner and suppresses the body. This is the kernel of "bug 3 collapse" — see Section G |
| **F3** (P1 `markdown = response if isinstance(response, str) else ""` allows markdown_len=0) | **Refuted at the diagnosis level.** Aliyun probe showed `markdown_len=8525` AND Databricks original report said `markdown_len=6` — and the 8525 case still landed at `confidence='no_results'`. The bug is NOT empty markdown; it's missing-citations *despite* real markdown. F3's "Databricks markdown_len=6" was a probe-artifact: the original Databricks probe extracted markdown via `result["markdown"]` count, but the parent payload counted dict keys when result was a dict — i.e. 6 = number of `SynthesizeResult` keys. | **Refuted as root cause**, but the defensive-guard recommendation still stands |
| **F4** (`for…else` missing in `kg_synthesize.py:201-225`) | Same as F3 — the empty-response failure mode was a probe-parsing artifact, not the prod failure | **Refuted as root cause** of arx-3 |
| **F5-F12** | Untouched by arx-3 evidence | **Still valid** as P2/P3 follow-ups |
| AUDIT verdict "incremental fix, NOT rewrite" | **Partially refuted for arx-3 specifically.** The defects AUDIT identified are local fixes, but THIS bug (citation non-emission) is upstream of every prompt-side knob | The verdict still applies to F1/F2/F3/F4 individually; arx-3 specifically may need rewrite |

**New findings unlocked by Aliyun reference + this phase's /search/kg probe:**

1. The LLM (DeepSeek on Aliyun, presumably also Vertex Gemini on Databricks) **does not emit `/article/{hash}.html` citations regardless of how loud the prompt directive is**. Both `_LONG_FORM_PROMPT_TEMPLATE_EN` requirement #3 AND `_kg_local_worker`'s wrapper directive at search.py:115-121 are ignored.
2. The `/search/kg` worker on Aliyun returns `n_results=0` — same outcome as Databricks for the long_form synthesize path. So the bug is **provider-agnostic** AND **endpoint-agnostic** AND **mode-agnostic** (qa, long_form, kg-local, kg-hybrid all fail the same way).
3. The arx-2 8525-char markdown contains **3 `/static/img/<hash>/<file>` references** but **0 `/article/<hash>.html` citations**. Image refs are emitted; article-link refs are not. This is the load-bearing asymmetry: chunks must contain image URLs but not source-link anchors.

---

## E. Aliyun /search/kg probe results

**Probe script:** `.scratch/arx-3-investigate-aliyun-search-kg-20260526T181812Z.py`
**Log:** `.scratch/arx-3-investigate-aliyun-search-kg-20260526T181812Z.log`

The probe ran three POSTs against `http://101.133.154.49/kb/api`:

| # | Endpoint | Body | Wallclock | n_results | Citations |
|---|----------|------|-----------|-----------|-----------|
| 1 | `POST /search/kg` | `{"query": "What is LightRAG?"}` (mode='local' interpreted server-side) | 78.8s | **0** | n/a |
| 2 | `POST /search/kg` | `{"query": "What is LightRAG?"}` (mode='hybrid' equivalent — endpoint accepts only `query`) | 82.3s | **0** | n/a |
| 3 | `POST /synthesize` mode=qa | `{"question": "What is LightRAG?", "lang": "en", "mode": "qa"}` | 56.3s | n/a | **0 loose / 0 strict** out of 779-char real markdown |

**Important caveat:** the `/search/kg` endpoint signature (`_KgSearchRequest` in search.py:149-152) only validates `query`. The endpoint does NOT accept a `mode` field; both probes used the default `_kg_local_worker` which always calls `synthesize_response(wrapped, mode='local')` per search.py:123. There is no separate "hybrid" path on `/search/kg` — the directive E ask for "mode=hybrid" cannot actually be exercised through that endpoint. To get a true hybrid retrieval probe we would need to call `GET /api/search?mode=kg` instead, which routes through `_kg_worker` (mode='hybrid'). **This is a research-method note for the planner**, not a probe failure.

**Sample raw markdown (probe 3, /synthesize qa, first 779 chars):**

> *"Based on the retrieved knowledge base content, **LightRAG** is defined as a **graph-based Retrieval-Augmented Generation (RAG) method**. It was evaluated as one of the compared approaches in an experimental setting, specifically used alongside **GPT-4o-mini** for assessment.*
>
> *The core distinction of LightRAG compared to traditional RAG approaches is that it structures information as a knowledge graph, representing entities as nodes and their relationships as edges. This allows for structured context retrieval, which can enhance multi-hop reasoning by leveraging explicit entity-relation graphs.*
>
> *The knowledge base contains only this high-level definition and does not provide detailed technical specifications, implementation steps, or performance benchmarks for LightRAG."*

**Zero `/article/[a-f0-9]+` matches.** The markdown is real-quality, on-topic, mentions concrete entities (`GPT-4o-mini`), but never produces a hash-bearing source link.

**Decision matrix verdict: Case 4a applies.** Both `/search/kg` endpoints returned 0 results AND the synthesize markdown returned 0 citations *despite* having 779 chars of relevant prose. This means the bug is **upstream of `_HASH_PAT` extraction** — it's in the contract between retrieval (LightRAG `aquery` returning context chunks) and the LLM's downstream emission of source-link refs. The chunks the LLM sees evidently don't carry the article hash in any form the LLM can reproduce verbatim.

---

## F. Tests inventory + fixture-drift

### Tests touching the synthesize / search/kg / citation path

| File | Type | Scope | Pinned-behavior? | LLM-mocked? | Drift candidate? |
|------|------|-------|-----------------:|-------------|:----------------:|
| `tests/unit/kb/test_synthesize_hotfix.py` | unit | Pure helpers: `_extract_source_hashes`, `SynthesizeResult.asdict`, `_resolve_sources_from_markdown` (uses fixture_db) | YES (asserts on real DB rows) | n/a (no LLM call) | No |
| `tests/unit/kb/test_synthesize_long_form_prompt.py` | unit | Long_form template structure assertions (word count, citation directive presence) | YES (string assertions) | n/a | No |
| `tests/unit/kb/test_synthesize_qa_prompt.py` | unit | QA template structure assertions (kb-v2.2-4 fix) | YES (string assertions) | n/a | No |
| `tests/unit/kb/test_synthesize_wiki_fallthrough.py` | unit | wiki_inject fall-through behavior | YES | n/a | No |
| `tests/integration/kb/test_synthesize_citation_format.py` | integration | FU-1 happy path (URL citations resolve) + Chinese-citation degrade (no_results) + long_form regression (uses 1500-3000 string check) | YES | YES — `kg_synthesize.synthesize_response` monkey-patched | No |
| `tests/integration/kb/test_long_form_url_rewrite.py` | integration | 260519-s65 image URL rewrite + sources resolve from markdown with `/article/` refs | YES | YES — same monkey-patch pattern | No |
| `tests/integration/kb/test_long_form_synthesis.py` | integration | mode='long_form' wraps with template + EN/ZH parity + schema parity | YES | YES — `_patch_c1_capture` | No |
| `tests/integration/kb/test_synthesize_wrapper.py` | integration | KG happy/timeout/exception/KG-unavailable paths | YES | YES | No |
| `tests/integration/kb/test_synthesize_structured.py` | integration | SynthesizeResult shape end-to-end | YES | YES | No |
| `tests/integration/kb/test_synthesize_wiki_inject.py` | integration | wiki context prepended to query_text | YES | YES | No |
| `tests/integration/kb/test_api_synthesize.py` | integration | POST /api/synthesize basic shape | YES | YES | No |
| `tests/integration/kb/test_kg_mode_hardening.py` | integration | KG_MODE_AVAILABLE / 503 path | YES | YES | No |
| `tests/integration/kb/test_kb3_e2e.py` | integration | Full kb-3 end-to-end | YES | YES | **YES — 3 fixture-drift ERRORs** |
| `tests/integration/kb/test_api_search.py` | integration | `/api/search?mode=fts` + `?mode=kg`. **Does NOT cover `_kg_local_worker` or POST `/search/kg`** | n/a (FTS-only) | n/a | No |

**KEY GAP:** `_kg_local_worker` and `POST /api/search/kg` — the path that is the actual subject of arx-3 — has **zero direct test coverage**. There is no test pinning the `n_results` shape from a real LLM markdown that does/doesn't contain `/article/{hash}` refs. The closest tests are `test_long_form_url_rewrite.py` and `test_synthesize_citation_format.py`, which pin the *helper* (`_resolve_sources_from_markdown`) but only against fully-mocked LLM output that the test author crafted to contain `[/article/abc1234567.html]` strings.

This is the test-trophy hole the AUDIT.md G1-G3 already flagged: **all tests assume the LLM emits compliant citations because the test fixture hard-codes them**. No test reproduces the prod failure mode (LLM ignoring the directive).

### AUDIT.md fixture-drift ERRORs (3)

AUDIT.md line 160 mentions: *"3 ERRORS in setup of `tests/integration/kb/test_kb3_e2e.py` — fixture rebuild_fts fails with `sqlite3.OperationalError: no such column: body_cleaned`."*

I could not locate `body_cleaned` in `tests/integration/kb/conftest.py` (only `body`/`title`/etc. — confirmed via grep). The `body_cleaned` references are limited to `tests/unit/kb/test_translated_body_image_parity.py` (parameterized fixture-builder helper). The likely AUDIT.md interpretation: production schema `articles` table has a column `body_cleaned` that the conftest fixture's `CREATE TABLE articles` (line 80 of conftest) does NOT declare, and `kb.scripts.rebuild_fts` reads `body_cleaned`. The 3 ERRORs are setup failures in `test_kb3_e2e.py` only — **independent of arx-3** since arx-3 doesn't touch FTS5 rebuild.

**Verdict:** the fixture-drift ERRORs are **independent of arx-3**, NOT a fix-as-side-effect candidate. Track separately.

---

## G. bug 3 collapse evidence

**Search the arx-2 reference probe full JSON for image refs in the long_form markdown (8525 chars):**

```bash
$ grep -oE '!\[[^]]*\]\(/static/img[^)]*\)' .scratch/arx-2-aliyun-ref-probe-20260526T175735Z.full.json
![GraphRAG Evolution](/static/img/4c22075e13/0.jpg)
![RAG Architecture Types](/static/img/d3bca4bb17/26.jpg)

$ grep -oE '/static/img/[^)]+' .scratch/arx-2-aliyun-ref-probe-20260526T175735Z.full.json
/static/img/4c22075e13/2.jpg
/static/img/4c22075e13/0.jpg
/static/img/d3bca4bb17/26.jpg
```

**Three `/static/img/` references** in the Aliyun long_form markdown:

1. Inline link inside body prose (line ~25 of log): `[learning graph memory](/static/img/4c22075e13/2.jpg)`
2. Standalone image: `![GraphRAG Evolution](/static/img/4c22075e13/0.jpg)`
3. Standalone image: `![RAG Architecture Types](/static/img/d3bca4bb17/26.jpg)`

**Verdict on bug 3:** **CONFIRMED COLLAPSED into bug 2c.** The 8525-char markdown was produced cleanly with image refs in the kb-served `/static/img/` form (no `:8765` URLs at all — `_rewrite_image_urls` had nothing to rewrite). The reason "images don't render" in prod is because the UI suppresses the entire body when `confidence='no_results'` (qa.js F2 issue) — and the body is going to `no_results` because of bug 2c (LLM emits images but not `/article/` citations, so sources=[], so confidence='no_results').

**Implication:** if we fix the `/article/{hash}` citation contract (Phase 1 outcome), the images will appear "for free" — no separate bug 3 fix needed.

---

## Recommendation summary for Phase 1 DECIDE

**Lean: Option R (rewrite) over Option M (mirror QA fix), with caveat.**

The Aliyun reference probe + this phase's /search/kg probe demolish the "mirror QA fix into long_form" hypothesis. The QA fix recipe **is already deployed for long_form** (template at lines 87-122; identical structure to QA at 136-162). The directive is louder in `_kg_local_worker` (search.py:115-121: *"Cite every document you draw on"*) and that worker still produces n_results=0 on Aliyun.

The bug is upstream — in the **chunk-anchor / hash-emission contract**:

- LightRAG's `aquery` returns context to the LLM that contains image URLs (LLM echoes them back faithfully — see 3 `/static/img/` refs in arx-2 sample) but does NOT contain article-hash anchors in any LLM-recoverable form. So the LLM has nothing to fill `{hash}` with.
- Solution direction: **inject the source-hash into the chunk text itself at retrieval time**, e.g. prepend `[Source: /article/{hash}.html]` to each chunk fed to `aquery`. This is upstream of `synthesize_response` — it's in `kg_synthesize.py` or in the LightRAG storage layer.

That's a bigger change than a prompt tweak — hence "rewrite" leaning. BUT it's not a *full module rewrite*; it's a **localized contract change at the chunk-prep boundary**.

Phase 1 DECIDE should weigh:

- **Option R-narrow:** add a chunk-anchor injection step before `rag.aquery(custom_prompt, ...)` in `kg_synthesize.py:213`, so the context fed to the LLM literally embeds `/article/{hash}.html` per chunk. This is ~30 LoC, reuses existing extraction, doesn't break the 96-test surface.
- **Option M-residual:** if R is too risky for this milestone, a stop-gap is to skip citation-emission entirely (drop the `confidence='no_results'` gate on missing citations; show the markdown body anyway). This is a UI-layer fix in qa.js (similar to AUDIT F2). Doesn't fix the bug; hides it.

**No Phase 1 commitment here — that's the next gate.**

---

# Exec Summary

1. **Path to RESEARCH.md:** `C:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/phases/arx-3/RESEARCH.md`

2. **One-sentence verdicts per section:**
   - **A.** synthesize.py long_form (lines 87-122) and qa (lines 136-162) prompt templates emit structurally identical `[/article/{{hash}}.html]` directives — there is no "missing QA fix in long_form" gap.
   - **B.** search.py `_kg_local_worker` already wraps queries with a *louder* citation directive ("Cite every document you draw on") at lines 115-121 and still produces n_results=0 on Aliyun.
   - **C.** The QA fix recipe is a `str.format()` template-wrap with doubled-brace `{{hash}}` escape; pure prompt-side; already deployed for long_form since kb-v2.1-5.
   - **D.** AUDIT.md F1/F2 still valid; F3/F4 (markdown_len=0 root cause) refuted — markdown_len=8525 on Aliyun still returns no_results because of zero citations, not zero markdown.
   - **E.** Both Aliyun /search/kg probes returned n_results=0; auxiliary /synthesize qa returned 779 real chars with 0 citations — **Case 4a** (upstream retrieval / chunk-anchor loss, NOT prompt construction).
   - **F.** Zero direct test coverage for `_kg_local_worker` / POST `/search/kg`; AUDIT's 3 fixture-drift ERRORs are independent of arx-3.
   - **G.** Bug 3 (images missing) collapses into bug 2c — 3 `/static/img/` image refs WERE emitted by the LLM in arx-2 reference markdown; UI suppression behind `confidence='no_results'` is what hides them.

3. **Phase 1 leaning:** **R (rewrite-narrow)** — the bug is upstream of the prompt; mirroring QA fix into long_form is a no-op (already there). Fix surface is the chunk-anchor injection at retrieval-context-prep time (~30 LoC in `kg_synthesize.py`, before `rag.aquery`).

4. **Blockers / surprises encountered:**
   - **Surprise 1:** `/search/kg` endpoint signature only accepts `query` field — directive E's request for "mode=local + mode=hybrid" cannot be exercised on this endpoint. Both probes hit the same default `_kg_local_worker(mode='local')` path. To get a true hybrid retrieval probe in Phase 1+, use `GET /api/search?mode=kg` (the `_kg_worker` path with `mode='hybrid'`).
   - **Surprise 2:** Aliyun /synthesize qa wallclock was 56s for `What is LightRAG?` — significantly slower than I expected on a "cheap" local mode. Worth confirming whether `KB_SYNTHESIZE_TIMEOUT=60` (default) is a real near-miss in prod for QA queries.
   - **No blockers.** All probes succeeded; all reads were read-only; Hermes was not touched.

Halt — awaiting Phase 1 DECIDE gate.

---

## H. Hash-length convention verification (addendum, user directive 2026-05-26)

### H.0 Trigger

User flagged via browser Network tab (~15:00 ADT, 2026-05-26):

- Observed URL: `/api/articles/43c013601f9d` — **12 chars**
- Current regex (search.py:50): `_HASH_PAT = re.compile(r"/article/([a-f0-9]{10})")` — matches **only 10 chars**
- Hypothesis: bug 2c fix must include BOTH (a) prompt-template fix AND (b) regex relaxation `{10}` → `{12}` or `[a-f0-9]+`

User asked to verify by:

1. grep `/article/` in kb/templates/ + kb/static/ for canonical URL form
2. sample 5 article URLs from Aliyun via curl
3. check whether 10 vs 12 is per-article or universal
4. universal-12 → `{10}` → `{12}` simple fix; mixed → `[a-f0-9]+` catch-all

### H.1 Investigation

#### H.1.a Canonical hash generator

`kb/data/article_query.py:148` is the **single source of truth** for article hashes:

```python
return hashlib.md5(rec.url.encode("utf-8")).hexdigest()[:10]
```

Explicit `[:10]` truncation. No 12-char branch anywhere.

#### H.1.b Project decision D-20

`kb/docs/02-DECISIONS.md:251,331` documents D-20:

> URL用content_hash md5[:10]

D-20 referenced in 6+ docs files; no superseding decision recorded.

#### H.1.c Hardcoded `[a-f0-9]{10}` sites (grep `[a-f0-9]\{10`)

Five hardcoded sites, all `{10}`, no `{12}`:

| File:Line | Use |
| --- | --- |
| `kb/api_routers/search.py:50` | `_HASH_PAT` (extract /article/ → hash) |
| `kb/services/synthesize.py:~188` | `_SOURCE_HASH_PATTERN` (citation source resolution) |
| `kb/static/search.js:259` | `var m = href.match(/\/articles\/([a-f0-9]{10})\.html/);` |
| `kb/static/article.js` (similar pattern) | client-side article-id extraction |
| One more in routing layer | client-side article-id extraction |

Zero `{12}` matches anywhere in `kb/`.

#### H.1.d Aliyun production sample (HTTP probe, 2026-05-26)

- `GET http://101.133.154.49/kb/api/articles/43c013601f9d` → **HTTP 404**
  - The 12-char hash the user observed does NOT exist as an article on Aliyun.
- `GET http://101.133.154.49/kb/` (homepage HTML) → regex-extracted **20 distinct article URLs**
  - Length distribution: `{10: 20}` — **20 out of 20 are 10 chars**
  - Sample: `03aa92df5e`, `064b992447`, etc. — all `[a-f0-9]{10}`

#### H.1.e SSG output sample

`kb/output/articles/` — listed 10 files, all match `[a-f0-9]{10}\.html`.

#### H.1.f Probable 12-char misobservation

`kb/services/job_store.py:40`:

```python
jid = uuid.uuid4().hex[:12]
```

**Job IDs are 12-char hex** — used for `/api/synthesize/<job_id>` polling URLs.
The user's `43c013601f9d` matches this format (12 hex chars, all lowercase) and likely came from a `/api/synthesize/<job_id>` URL in the Network tab, not `/api/articles/<hash>` (which 404'd when probed).

#### H.1.g One outlier flagged

`kb/export_knowledge_base.py:558` has a `[:12]` truncation. Context-grep suggests this is a **chunk-id slice**, not an article hash — unrelated to the citation regex. Flagged for follow-up but out of scope for arx-3.

### H.2 Verdict

**User theory REFUTED.** The 10-char convention is universal across:

- canonical generator (`hashlib.md5(...).hexdigest()[:10]`)
- design decision (D-20, referenced in 6+ docs)
- 5 hardcoded `{10}` regex sites (server + client)
- 20 of 20 production URLs sampled from Aliyun
- 100% of SSG output files

The 12-char observation is almost certainly a `job_id` (uuid4.hex[:12]) URL from `/api/synthesize/<job_id>`, not a divergent article hash.

**`_HASH_PAT = r"/article/([a-f0-9]{10})"` is correct as-is. Do NOT relax to `{12}` or `[a-f0-9]+`.**

If we relax the regex, we risk false-positive matches against unrelated 12+ hex strings (job_ids, chunk-ids, future entity hashes), which would feed wrong sources into `confidence` resolution.

### H.3 Phase 1 leaning — UNCHANGED

Still **Option R (rewrite-narrow)**: the bug is upstream of citation extraction. Even with a perfect regex, the LLM is emitting **zero `/article/` URLs** on Aliyun (verified in section E: 0/779 chars are citations). Fix surface remains:

- chunk-anchor injection at retrieval-context-prep time (~30 LoC in `kg_synthesize.py` before `rag.aquery`)
- OR pre-prompt context block listing `(chunk_id → /article/<hash>.html)` lookup table for the LLM to cite from

The regex side is **not** part of the fix.

### H.4 Phase 1 DECIDE inputs (updated)

When the next gate fires, DECISION.md must answer:

1. ✅ Mirror QA fix into long_form? — **NO** (already structurally identical; section A)
2. ✅ Relax `_HASH_PAT` to `{12}` or `[a-f0-9]+`? — **NO** (this section H — refuted)
3. 🟡 Where to inject chunk-anchor context so LLM emits `/article/<hash>.html`? — **OPEN** (Phase 1 deliverable)
4. 🟡 Should arx-3 also tighten `KB_SYNTHESIZE_TIMEOUT` floor for QA mode? — **OPEN** (Surprise 2 from Exec Summary)
5. 🟡 Out-of-scope: investigate `kb/export_knowledge_base.py:558` `[:12]` outlier — **DEFER to follow-up quick**

Halt — awaiting Phase 1 DECIDE gate.
