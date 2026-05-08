---
name: omnigraph_cloud_synthesize
description: |
  Use this skill on cloud servers when the user wants to synthesize an answer
  from already-ingested OmniGraph-Vault articles but Gemini is unavailable or
  should not be used. It reads persisted LightRAG full documents, performs local
  lexical retrieval, and calls DeepSeek for final Markdown synthesis.

  This skill is intentionally a fallback path. It does not scan, ingest,
  re-embed, update LightRAG, traverse LightRAG graph mode, or use Gemini. Use
  omnigraph_query for the full LightRAG hybrid path when Gemini embedding is
  available.
compatibility: |
  Requires: DEEPSEEK_API_KEY in ~/.hermes/.env; Python venv at
  $OMNIGRAPH_ROOT/venv with requests installed; populated
  ~/.hermes/omonigraph-vault/lightrag_storage/kv_store_full_docs.json.
metadata:
  openclaw:
    os: ["linux"]
    requires:
      bins: ["bash", "python"]
      config: ["DEEPSEEK_API_KEY"]
---

# omnigraph_cloud_synthesize

## Quick Reference

Run:

```bash
scripts/query.sh "<question>"
```

The skill writes:

- `~/.hermes/omonigraph-vault/synthesis_output.md`
- `~/.hermes/omonigraph-vault/synthesis_archive/<timestamp>_<query>.md`

## When to Use

- The cloud server cannot reach Gemini.
- The task only needs already-ingested articles.
- The user wants a source-grounded Markdown synthesis, not graph mutation.
- Hermes/OpenClaw needs a thin skill wrapper around OmniGraph knowledge.

## When Not to Use

- New article scanning or ingestion is required.
- Entity graph traversal, vector search, or LightRAG hybrid query is required.
- The question depends on code structure from OpenClaw, Hermes, or VitaClaw
  source graphs. Use graphify/code graph tooling alongside this skill.

## Behavior

This fallback reads `kv_store_full_docs.json`, ranks documents locally by
question terms, sends the top documents to DeepSeek, and asks for an
evidence-grounded technical answer. It never calls Gemini.

If retrieval is weak, the answer should say the evidence is thin rather than
inventing support.
