# omnigraph_research

Deep multi-stage research over the OmniGraph knowledge graph. Combines KG
retrieval, web baseline, vision analysis, and verifier fact-checking to
produce a long-form Markdown answer with embedded images.

This is the milestone deliverable of **Agentic-RAG-v1**. ar-1 ships the
contract-shape skeleton (web_baseline / reasoner / verifier are stubs);
ar-2 / ar-3 / ar-4 land the real agent loops.

## What this skill does

- Routes "research X" / "deep dive on X" / "深度解析 X" natural-language
  triggers to a single CLI invocation: `python -m omnigraph.research "<query>"`
- Walks 5 internal stages in strict order: WebBaseline → Retriever →
  Reasoner → Verifier → Synthesizer
- Returns a Markdown report to stdout with the query echoed at the top, a
  `## Knowledge Graph Retrieval` section, and (in stub mode)
  `> ℹ️ ... skipped: ...` degradation notes for the unfinished stages
- Brings up the local image HTTP server on port 8765 on first invocation
  so embedded `![alt](http://localhost:8765/...)` URLs render

The orchestration logic IS the value. Internal stages are NEVER exposed
as separate skills (design § Skill exposure principle).

## Install

This skill ships in-tree under `skills/omnigraph_research/`. To make it
discoverable by the Hermes / OpenClaw skill loader:

1. **Symlink or copy the skill directory** into the host agent's skill
   directory (typically `~/.hermes/skills/` or `~/.openclaw/skills/`):

   ```bash
   ln -s "$(pwd)/skills/omnigraph_research" ~/.hermes/skills/omnigraph_research
   # or copy
   cp -r skills/omnigraph_research ~/.hermes/skills/
   ```

2. **Set required env vars** in `~/.hermes/.env`:

   ```bash
   GEMINI_API_KEY=<your-key>          # required
   TAVILY_API_KEY=<your-key>          # optional — enables WebBaseline (ar-3+)
   BRAVE_SEARCH_API_KEY=<your-key>    # optional — WebBaseline fallback (ar-3+)
   ```

3. **Create the venv and install the package** so the `omnigraph.research`
   namespace resolves to `lib/research/`:

   ```bash
   cd /path/to/OmniGraph-Vault
   python -m venv venv
   venv/Scripts/pip install -e .       # Windows
   # or
   venv/bin/pip install -e .           # POSIX
   ```

4. **Reload the host agent** (`/new` in chat or `openclaw gateway restart`).

## Trigger Examples

The host agent routes to this skill on phrases like:

- "research Hermes Harness architecture"
- "deep dive on LightRAG vs Cognee"
- "synthesize a report on AI agent skills"
- "what do I know about RAG (synthesized)"
- "深度解析 LightRAG 是什么"
- "深度研究 Vision Cascade 设计"

Once invoked, the skill calls `bash scripts/research.sh "<query>"` which
forwards to `python -m omnigraph.research "<query>"`.

## Cost / Quality / Latency

| Metric | ar-1 (current — stub mode) | ar-4 (target — full agentic) |
|---|---|---|
| Cost per query | ~$0 (only embedding call hits API) | ~$0.10-0.30 (Tavily web baseline + Vertex Gemini grounding + DeepSeek synthesis + Vision cascade) |
| Quality | Stub markdown with degradation notes — query echo + KG retrieval section + per-stage skipped notes | Full deep synthesis: multi-paragraph long-form, image embeds, source citations, verifier confidence ≥ 60 |
| Latency | < 2s | ≤ 120s for a typical "深度解析" query |
| Image embeds | None — retriever currently surfaces an embedding-dim mismatch in stub mode | ≥ 3 images for image-rich KG topics, served from `http://localhost:8765/<hash>/<N>.jpg` |
| Verifier confidence | n/a — verifier is stubbed `status="skipped"` | Confidence float ∈ [0.0, 1.0]; ≥ 0.60 expected on grounded queries |

## What's Deferred to Later Phases

| Item | Phase |
|---|---|
| Real Reasoner agent loop with `kg_search` + `vision_analyze` tools | ar-2 |
| `lib/vision_cascade.py` integration as the `vision_analyze` tool | ar-2 |
| Synthesizer prompt engineering with image embeds + degradation appending | ar-2 (initial) / ar-4 (final tuning) |
| `--max-iter-reasoner` / `--max-iter-verifier` / `--no-grounding` CLI flags | ar-2 |
| Tavily REST primary + Brave REST fallback live integration | ar-3 |
| Vertex Gemini `google_search_grounding` opt-in | ar-3 |
| `--dump-state` CLI flag | ar-4 |
| `research_stream()` body + telemetry JSONL writes | ar-4 |
| Smoke test on `"Hermes Harness 深度解析"` with all conditions (≥3 imgs, conf≥60, ≤120s, lang=zh) | ar-4 |
| Side-by-side review vs ground-truth Telegram session | ar-4 (manual review) |
| HTTP endpoint pre-build | post-milestone |

## Troubleshooting

### Port 8765 already in use

The local image HTTP server is brought up by
`lib.research.image_server.ensure_image_server` on first invocation. If
port 8765 is already bound (e.g., by a previous synthesis run, by the
`omnigraph_query` skill's image server, or by an unrelated process),
`ensure_image_server` returns `None` silently and reuses the existing
server. No error is surfaced to the user. To verify:

```bash
curl -sI http://localhost:8765/ | head -1
# expected: HTTP/1.0 200 OK (or 404 — both indicate the server is up)
```

If a different process is on port 8765, kill it before rerunning.

### `GEMINI_API_KEY` is not set

ar-2 onward will fail fast with a clear message. ar-1 stub mode may still
produce non-empty Markdown, but the retriever's embedding step will fail
(`Embedding dim mismatch` or auth error) and the answer will contain only
the query echo + degradation notes.

Fix: add `GEMINI_API_KEY=<your-key>` to `~/.hermes/.env` and reload.

### Output contains "skipped" notes

Expected in ar-1 stub mode. Three stages are stubbed:

- `> ℹ️ WebBaseline skipped: web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)`
- `> ℹ️ Reasoner skipped: ar-1 stub — agent loop lands in ar-2`
- `> ℹ️ Verifier skipped: ar-1 stub — verifier loop lands in ar-3`

These are by design. Real agent loops land in ar-2 (Reasoner) / ar-3
(WebBaseline + Verifier).

### Retriever fails with `Embedding dim mismatch`

Local KG was built with a 768-dim embedding (Gemini embedding-2 default
on the dev box) but `omnigraph_search.query.search` may request 3072-dim.
This is an environment-specific issue surfaced during ar-1 stub testing
on the local Windows dev. It does NOT block the contract-shape smoke
test (the failure is captured as a `> ❌` note line and the orchestrator
continues). On Hermes / Aliyun production with matching embedding-dim,
the retriever returns real chunks.

### Skill not discovered by Hermes

Verify with `hermes skills list | grep omnigraph_research`. If missing,
re-symlink the directory and reload the gateway:

```bash
ln -sfn "$(pwd)/skills/omnigraph_research" ~/.hermes/skills/omnigraph_research
hermes gateway restart
```

## Internal Stages (NOT exposed as skills)

The skill orchestrates 5 internal stages defined in `lib/research/stages/`:

```
WebBaseline → Retriever → Reasoner → Verifier → Synthesizer
```

Per design § Skill exposure principle, these are **never** exposed as
separate skills. A host agent installing this skill sees ONE new entry
(`omnigraph_research`); the orchestration is the encapsulated value.

## Related

- `omnigraph_search` — raw KG chunks, no synthesis (~$0.01, 10-20s)
- `omnigraph_query` — KG-only synthesis, single-source (~$0.01, 30-60s)
- `omnigraph_research` — full hybrid agentic, image-rich (~$0.05, 30-60s) ← **this skill**

Pick by cost/quality target. Choosing among skills is host-agent work;
orchestrating internal stages of one skill is NOT.

## References

- Design doc: `docs/design/agentic_rag_internal_api.md` (locked 2026-05-06)
- Phase context: `.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md`
- Module source: `lib/research/`
