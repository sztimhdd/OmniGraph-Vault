---
name: omnigraph_research
description: |
  Deep multi-stage research over the OmniGraph knowledge graph. Triggers on
  "research X", "deep dive on Y", "synthesize a report on Z", "深度解析", or
  "深度研究". Combines KG retrieval, web baseline, vision analysis, and
  verifier fact-checking to produce a long-form Markdown answer with
  embedded images. ar-1 ships a contract-shape stub (web_baseline,
  reasoner, verifier are skipped); ar-2 / ar-3 / ar-4 land the deep
  agent loops. Output language follows the query language (CJK ratio
  heuristic in ar-1; LLM-driven detection in ar-2+).

  Do NOT use this skill when: the user wants to add or ingest new content
  — use `omnigraph_ingest` instead. Do NOT use for raw entity-attributed
  retrieval without synthesis — use `omnigraph_search`. Do NOT use for
  KG-only single-source synthesis (cheaper, faster) — use `omnigraph_query`.
  Do NOT call internal stages (web_baseline / retriever / reasoner /
  verifier / synthesizer) directly — they are NOT exposed as separate
  skills (design § Skill exposure principle: one milestone deliverable =
  one new skill).
compatibility: |
  Requires: GEMINI_API_KEY (or OMNIGRAPH_GEMINI_KEY) in ~/.hermes/.env;
  Python venv at $OMNIGRAPH_ROOT/venv with `pip install -e .` so the
  `omnigraph.research` namespace resolves to `lib/research/`.
  Optional (for ar-3+): TAVILY_API_KEY (web baseline primary),
  BRAVE_SEARCH_API_KEY (web baseline fallback). With both unset, the
  WebBaseline stage degrades to status="skipped" with a clear reason.
required_environment_variables:
  - name: GEMINI_API_KEY
    prompt: "Gemini API key for OmniGraph-Vault (get from https://aistudio.google.com/apikey)"
    help: "Required for embedding + LLM calls in retriever/reasoner/synthesizer."
    required_for: full functionality
metadata:
  openclaw:
    skillKey: omnigraph-vault
    primaryEnv: GEMINI_API_KEY
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["bash", "python"]
      config: ["GEMINI_API_KEY"]
      optional_config: ["TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY"]
triggers:
  - "research"
  - "deep dive"
  - "synthesize a report on"
  - "what do I know about (synthesized)"
  - "深度解析"
  - "深度研究"
---

# omnigraph_research

## Quick Reference

| Task | Input | Command |
|------|-------|---------|
| Deep research over KB + web | natural-language query | `scripts/research.sh "<query>"` |
| Chinese deep-dive | 中文 query | `scripts/research.sh "深度解析 <topic>"` |
| Empty query | no question given | Ask the user — do not run |

## When to Use

- User says "research X", "deep dive on X", "synthesize a report on X"
- User says "深度解析 X" or "深度研究 X"
- User asks "what do I know about X synthesized" — long-form answer with citations expected
- The expected answer is a multi-paragraph Markdown report with embedded images and source citations, not a single-paragraph KG-only summary

## When NOT to Use

- User wants to add or ingest new content → use `omnigraph_ingest` instead
- User wants raw entity-attributed retrieval (no synthesis, no web) → use `omnigraph_search` instead — cheaper and faster
- User wants a KG-only single-source synthesis (no web baseline, no verifier) → use `omnigraph_query` instead — cheaper and lower latency
- User asks about graph health or node counts → use `omnigraph_status` instead
- User wants to delete or manage entities → use `omnigraph_manage` instead
- User wants general web search not grounded in personal KB → leave to the host agent's default search capability

## Decision Tree

### Case 1: Standard natural-language research query

Announce: "Running deep research — ar-1 stub mode emits a contract-shape answer in <2s; full agent loops land in ar-2 / ar-3 / ar-4."

Run:

```bash
scripts/research.sh "<user query>"
```

The wrapper invokes `python -m omnigraph.research "<query>"` from the repo
root. Output is Markdown to stdout. In ar-1 stub mode the output contains
the query echo, an `## Knowledge Graph Retrieval` section, and a
horizontal rule followed by `> ℹ️ ... skipped: ...` degradation notes for
WebBaseline, Reasoner, and Verifier.

### Case 2: User explicitly asks to bypass the wrapper

Do NOT bypass. Always invoke `scripts/research.sh "<query>"`. Future
telemetry, key rotation, and env-source helpers will land in the wrapper —
keeping the skill as the single entrypoint preserves that landing site.

### Case 3: User asks for the retriever output directly, or for the
web-baseline snippets, or for the verifier confidence in isolation

Do NOT expose internal stages as separate skills (design § Skill exposure
principle: one milestone deliverable = one new skill). The internal
stages (web_baseline, retriever, reasoner, verifier, synthesizer) are
implementation details of `omnigraph_research`. If the user wants a
different cost/quality point, redirect:

- Raw KG chunks only → `omnigraph_search`
- KG-only synthesis → `omnigraph_query`

### Case 4: GEMINI_API_KEY not set

Respond: "⚠️ Configuration error: `GEMINI_API_KEY` is not set in `~/.hermes/.env`. Add it and retry. (ar-1 stubs may still emit non-empty markdown without it, but the retriever embedding step will fail and the answer will be content-free.)"

### Case 5: Empty query

Respond: "Please provide a research query, e.g. 'research Hermes Harness architecture' or '深度解析 LightRAG 是什么'."

## Output Format

- Markdown to stdout — multi-section: title, `## Knowledge Graph Retrieval`, `---`, then degradation notes
- ar-1 stub: ≥ 1 degradation note line starting `> ℹ️` or `> ❌` (one per skipped/failed stage)
- ar-4 final: long-form synthesis with embedded `![alt](http://localhost:8765/<hash>/<N>.jpg)` image URLs, ≥ 3 images for image-rich KG topics, verifier confidence ≥ 60
- Image URLs always use the local image server at `http://localhost:8765/...` — `scripts/research.sh` does NOT bring up the server itself; the Python module brings it up on first use via `lib.research.image_server.ensure_image_server`

## Error Handling

| Error | Response |
|-------|----------|
| `GEMINI_API_KEY` not set | "⚠️ Configuration error: GEMINI_API_KEY is not set in `~/.hermes/.env`" |
| venv missing | "⚠️ Setup error: venv not found at `$OMNIGRAPH_ROOT/venv`. Run `python -m venv venv && pip install -e .`" |
| Empty query argument | "⚠️ Usage: research.sh '<query>' — query argument required" |
| Image server port 8765 already in use | Silently reuses existing server (no error surfaced) |
| Retriever embedding-dim mismatch | Surfaces in stdout as `> ❌ Retriever failed: ...` — do not retry; report to user and continue |

## Trigger Phrases

The host agent (Hermes / OpenClaw / Claude Code) routes to this skill on:

- "research <topic>"
- "deep dive on <topic>"
- "synthesize a report on <topic>"
- "what do I know about <topic> (synthesized)"
- "深度解析 <topic>"
- "深度研究 <topic>"

Prefer this skill over `omnigraph_query` when the query implies a long-form answer with citations and possibly embedded images.

## What NOT to Do

- DO NOT call internal stages directly (`web_baseline`, `retriever`, `reasoner`, `verifier`, `synthesizer`) — they are NOT exposed as skills (design § Skill exposure: one milestone deliverable = one new skill; counter-pattern: `omnigraph_kg_retrieve` / `omnigraph_kg_reason` / `omnigraph_kg_verify` / `omnigraph_kg_synthesize` would force every host agent to re-implement orchestration)
- DO NOT bypass `scripts/research.sh` to call `python -m omnigraph.research` directly — keep the skill as the single entrypoint so future telemetry / key-rotation / env-source helpers land in one place
- DO NOT pass mode flags (`naive` / `local` / `global` / `hybrid`) — those belong to `omnigraph_query`. `omnigraph_research` is always full-pipeline
- DO NOT translate the query before passing it in — the synthesizer's language heuristic (CJK ratio ≥ 0.3 → Chinese; else English) handles output language matching automatically (Axis 10)

## Privacy Note

Query and intermediate state stay local in `~/.hermes/omonigraph-vault/`. The retriever calls Google Gemini for embedding (KG vector lookup); ar-3+ also calls Tavily / Brave for web baseline. No raw KB content leaves the host except as embedding input (text snippets up to ~8K tokens per call) and as web-search query strings.

## Related Skills

- `omnigraph_ingest` — add a WeChat URL or PDF to the knowledge graph
- `omnigraph_search` — raw entity-attributed retrieval, no synthesis (cheapest)
- `omnigraph_query` — KG-only synthesis, single-source (mid)
- `omnigraph_status` — graph health and statistics
- `omnigraph_manage` — delete or reindex entities

## References

- Design doc: `docs/design/agentic_rag_internal_api.md` § Skill exposure principle
- Phase context: `.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md`
- Module source: `lib/research/` (physical) — importable as `omnigraph.research` (namespace mapping in `pyproject.toml`)
