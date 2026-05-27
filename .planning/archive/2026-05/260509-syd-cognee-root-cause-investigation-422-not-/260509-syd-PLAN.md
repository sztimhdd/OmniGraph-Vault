---
type: quick
id: 260509-syd
title: Cognee root-cause investigation — 422 NOT_FOUND
created: 2026-05-09
status: in_progress
requirements: [COG-01, COG-02, COG-03]
autonomous: true
investigation_only: true
---

# Quick Task 260509-syd — Cognee 422 NOT_FOUND root-cause investigation

## Objective

Investigate why `cognee.remember_article` (called inline from `ingest_wechat.py` when
`OMNIGRAPH_COGNEE_INLINE=1`) blocks the KOL ingest fast-path with a 422 NOT_FOUND
retry loop. Produce a recommended fix path (A / B / C) backed by raw HTTP / SDK evidence.

**This is INVESTIGATION-ONLY.** No production-code edits. No SSH to Hermes. Output is
diagnostic scripts + 2 markdown documents + evidence logs + a single doc-only commit.

## Tasks

### Task 1 — Diagnostic scripts (`scripts/cognee_diag/`)

Create three scripts under `scripts/cognee_diag/`. Each script:
- starts with a banner that prints the script name + start timestamp
- routes all stdout+stderr to `.scratch/cognee-diag-<name>-<YYYYMMDD-HHMMSS>.log`
  (the script writes the log path to stdout so the operator can `tail -f`)
- uses `DEEPSEEK_API_KEY=dummy` as Phase 5 import-time defense
- sets `OMNIGRAPH_COGNEE_INLINE=1` only for the inline-probe scripts
- redacts API keys in any logged HTTP body
- is type-annotated, PEP-8, no `print()` statements in the body — use `logging`
  per Python rules (banner + log-path summary at __main__ are exceptions)

Scripts:

1. `inspect_cognee_routing.py` — pure-import probe. Prints:
   - cognee version + litellm version (via `importlib.metadata`)
   - `EmbeddingConfig` snapshot after `cognee_wrapper` imports — what
     `embedding_provider`, `embedding_model`, `embedding_dimensions`,
     `embedding_endpoint`, `embedding_api_key` actually resolve to
   - `LLMConfig` snapshot — what `llm_provider`, `llm_model` actually resolve to
   - LiteLLM model registry lookup: does
     `gemini-embedding-2`, `gemini/gemini-embedding-2`,
     `vertex_ai/gemini-embedding-2`, `vertex_ai/gemini-embedding-2-preview`
     each appear in `litellm.model_cost`? Pretty-print provider classification.

2. `probe_cognee_inline_baseline.py` — exercises the actual failing code path with
   minimum dependencies. Loads `cognee_wrapper`, calls
   `await cognee.remember("hello world", dataset_name="diag", self_improvement=False)`
   in a freshly-running asyncio loop. Captures full traceback (incl. LiteLLM HTTP
   response body) + wall-clock duration. Wraps in `asyncio.wait_for(..., timeout=60)`
   so the script terminates even if Cognee retry-loops.

3. `probe_litellm_direct.py` — bypasses Cognee entirely. Drives `litellm.aembedding`
   directly with each candidate model string:
   - `gemini/gemini-embedding-2` (the broken cognee_wrapper config)
   - `gemini/gemini-embedding-2-preview` (registry-known AI Studio name)
   - `gemini/gemini-embedding-001` (legacy AI Studio name)
   - `vertex_ai/gemini-embedding-2-preview` (registry-known Vertex name, requires SA)
   For each candidate: log the request URL (from LiteLLM verbose mode if
   available), HTTP status, response body excerpt (redact `key=`), exception type +
   message. This isolates whether the 422 comes from AI Studio (model name) or
   from LiteLLM routing.

**Done criteria for Task 1:**
- Three scripts exist, executable via `.venv/Scripts/python scripts/cognee_diag/<name>.py`
- Each script writes a log file path to stdout on start
- Each script handles the case where the network is blocked (Vertex/AI Studio
  unreachable) by capturing the exception verbatim — failure is evidence
- A 4th file `scripts/cognee_diag/README.md` documents what each script proves /
  does not prove

### Task 2 — Investigation report + Summary doc + final commit/push

1. Run all three diagnostic scripts. Capture logs to `.scratch/cognee-diag-*.log`.
   Some probes WILL fail (corp net blocks AI Studio + LiteLLM may not have a
   matching registry entry). Failures ARE evidence — paste raw stack traces /
   HTTP bodies into INVESTIGATION.md verbatim.

2. Write `.planning/quick/260509-syd-.../INVESTIGATION.md` containing:
   - **TL;DR (≤4 lines)** — root cause statement + confidence level. If corp net
     blocks Vertex/AI Studio so the smoke is incomplete, TL;DR MUST say so:
     "root cause unconfirmed locally; <inferred>; needs Hermes verification."
   - **Evidence ledger** — for every "X works / Y broken" claim, cite the log
     file + line range
   - **Routing trace** — annotated flow from `cognee_wrapper` env-mutation lines
     through `EmbeddingConfig` → `LiteLLMEmbeddingEngine` → `litellm.aembedding`
     → `_get_gemini_url` → AI Studio URL. Cite verbatim source-code line numbers.
   - **Three fix paths** with t-shirt sizes (LOC/files cited via `git grep`):
     - **Path A — Rename** `EMBEDDING_MODEL` in `cognee_wrapper.py` from
       `gemini/gemini-embedding-2` to `gemini/gemini-embedding-2-preview` (AI
       Studio registry-known name). Smallest blast radius.
     - **Path B — Switch to Vertex** by setting
       `LLM_PROVIDER=vertex_ai` + `EMBEDDING_PROVIDER=vertex_ai` +
       `EMBEDDING_MODEL=vertex_ai/gemini-embedding-2-preview` and supplying SA
       JSON via `GOOGLE_APPLICATION_CREDENTIALS`. Pros: parity with production
       LightRAG embedding; cons: requires SA on both dev + Hermes prod.
     - **Path C — Replace Cognee LiteLLM with direct google-genai SDK** —
       monkey-patch the embedding engine to use `google.genai.Client` like
       `lib/lightrag_embedding.py` does. Highest LOC, removes LiteLLM dependency
       on the embedding hot path entirely.
   - **Recommended path** with rationale (1 paragraph)
   - **Open questions for the fix quick** — anything the investigation could not
     answer locally (likely: Vertex live response shape; AI Studio gemini-
     embedding-2-preview live behavior; whether Cognee's
     `LiteLLMEmbeddingEngine.endpoint` field can be hijacked safely).

3. Write `.planning/quick/260509-syd-.../260509-syd-SUMMARY.md` containing:
   - 1-paragraph synopsis
   - Recommended fix (A / B / C)
   - Pointer to INVESTIGATION.md
   - Log file paths (relative paths under `.scratch/`)
   - Open questions
   - Final commit SHA (filled in after commit)

4. **Stop-gate verification before commit:**
   ```bash
   git status --short
   # Only paths under scripts/cognee_diag/ + .planning/quick/260509-syd-*/ allowed.
   ```
   If any other path is modified, ABORT, undo, investigate.

5. `git pull --ff-only origin main` (race protection).

6. Commit (canonical via gsd-tools):
   ```bash
   node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit \
     "docs(quick-260509-syd): root-cause investigation for Cognee 422 NOT_FOUND" \
     --files <listed file paths>
   ```

7. `git push origin main`.

**Done criteria for Task 2:**
- Stop-gate diff is empty (only `scripts/cognee_diag/` + `.planning/quick/260509-syd-*/`)
- INVESTIGATION.md and 260509-syd-SUMMARY.md exist and pass anti-fabrication contract
- Final commit SHA recorded in 260509-syd-SUMMARY.md
- `git push` succeeds

## Anti-fabrication contract

- Every "X works / Y broken" claim in INVESTIGATION.md MUST cite a real
  `.scratch/cognee-diag-*.log` path + line range
- Raw HTTP body / stack-trace excerpts MUST be pasted verbatim from captured logs
  (key redaction OK), NOT paraphrased
- TL;DR must match what the logs actually show. If corp-net blocks AI Studio,
  TL;DR must say "root cause unconfirmed locally; <inferred>; needs Hermes
  verification."
- T-shirt estimates must cite counted LOC / files via `git grep`
- If a diag script fails to capture evidence (network blocked, dependency
  missing, etc.), that failure stack IS evidence — capture it verbatim, do NOT
  fabricate substitute output

## Forbidden edits

- `cognee_wrapper.py`
- `cognee_batch_processor.py`
- `ingest_wechat.py`
- `lib/api_keys.py`
- `kg_synthesize.py`
- `CLAUDE.md`
- `.planning/STATE.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`

ANY edit outside `scripts/cognee_diag/` and `.planning/quick/260509-syd-*/`
violates the stop-gate. Detection: stop-gate diff at each commit.

## Success criteria

- [ ] Three diagnostic scripts under `scripts/cognee_diag/` + a README
- [ ] Each script run produced a log file under `.scratch/`
- [ ] INVESTIGATION.md + 260509-syd-SUMMARY.md exist with anti-fabrication
      compliance
- [ ] Recommended fix path (A / B / C) selected with reasoning
- [ ] Single doc-only commit on origin/main
- [ ] Open questions documented for the follow-up fix quick
