# enrich_article (Hermes skill)

End-to-end Zhihu-enriched ingest of a WeChat article. Orchestrates:
1. Question extraction (Gemini + Google Search grounding)
2. Per-question `/zhihu-haowen-enrich` child skill invocation
3. Per-question `fetch_zhihu.py` deep-fetch
4. `merge_and_ingest.py` → LightRAG + SQLite

Phase 4 of the OmniGraph-Vault knowledge pipeline.

## Install

1. `./deploy.sh` from the repo root (syncs this skill to remote via `git pull`)
2. Hermes discovers the skill via `skills.external_dirs` (already points at
   `/home/<user>/OmniGraph-Vault/skills` on the production remote)
3. Restart: `hermes gateway restart` or `/new` in chat

## Prerequisites

- Python venv at `$OMNIGRAPH_ROOT/venv` with `requirements.txt` installed
- `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `CDP_URL` in `~/.hermes/.env`
- CDP-reachable Edge at `$CDP_URL` (for child skill `/zhihu-haowen-enrich`)
- Child skill `zhihu-haowen-enrich` deployed to the same skills directory

## Usage

Trigger: "enrich this article" + `ARTICLE_URL` / `ARTICLE_PATH`

Runtime: ~10 minutes per article (3 questions × ~3 min each).

## Design Notes

Per D-01, ALL orchestration lives in this Markdown SKILL.md — there is no
Python `orchestrator.py` or `run_enrichment.py`. The Python helpers
(`enrichment/extract_questions.py`, `enrichment/fetch_zhihu.py`,
`enrichment/merge_and_ingest.py`) are pure deterministic subprocesses with
no Hermes awareness.

The per-question for-loop is a natural-language instruction that the
Hermes agent interprets across 3 iterations. Total turn budget ~60 (fits
under max_turns=90).

## Testing

REMOTE-ONLY. There is no unit-test path for the orchestration itself — it
is a Hermes-agent-driven flow. Integration test:

```bash
ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST
cd ~/OmniGraph-Vault
# From Hermes chat:
/enrich_article ARTICLE_URL=https://mp.weixin.qq.com/s/... ARTICLE_PATH=/path/to/final_content.md
```

Then verify in `~/.hermes/omonigraph-vault/enrichment/<hash>/` that
`questions.json` and `<q_idx>/haowen.json` were written, and
`SQLite articles.enriched = 2 or -2`.

## Related

- Child skill: `/zhihu-haowen-enrich` (invoked per question)
- Python helpers: `enrichment/extract_questions.py`, `enrichment/fetch_zhihu.py`, `enrichment/merge_and_ingest.py`
- Alternative: `omnigraph_ingest` (un-enriched; debug-only per D-07)
