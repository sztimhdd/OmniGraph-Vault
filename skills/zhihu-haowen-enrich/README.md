# zhihu-haowen-enrich (Hermes skill)

Drives zhida.zhihu.com's AI-search UI per question and writes the result
(AI summary + best-source Zhihu URL) to disk.

Used by the `enrich_article` orchestration skill (Phase 4 knowledge
enrichment).

## Install

1. Copy this directory to a Hermes-discoverable location (remote WSL):
   ```
   /home/<user>/OmniGraph-Vault/skills/zhihu-haowen-enrich/
   ```
2. Ensure Hermes `skills.external_dirs` includes
   `/home/<user>/OmniGraph-Vault/skills` (already configured on the
   production remote).
3. Restart Hermes gateway: `hermes gateway restart` (or `/new` in chat).

## Prerequisites

- CDP-reachable Edge at `CDP_URL` (default `http://localhost:9223`)
- Zhihu session cookies in that Edge user-data-dir (or reply `/resume` to the
  QR prompt)
- Hermes `send_message` tool configured with a Telegram target (FR-20 default)
- Env vars: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` in `~/.hermes/.env`

## Testing

The skill is REMOTE-ONLY and MANUAL (per Phase 4 VALIDATION.md §Manual-Only
Verifications). To smoke-test:

```bash
ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST
cd ~/OmniGraph-Vault
# From Hermes CLI or chat:
#   /zhihu-haowen-enrich  ARTICLE_HASH=test Q_IDX=0 QUESTION="LightRAG 的多跳实体消歧怎么做?"
# Then inspect:
ls ~/.hermes/omonigraph-vault/enrichment/test/0/haowen.json
cat ~/.hermes/omonigraph-vault/enrichment/test/0/haowen.json
```

Expect either `{question, summary, best_source_url, timestamp}` (success)
or `{question, error, timestamp}` (graceful failure).

## Related

- Orchestrator: `enrich_article` (calls this skill once per question)
- Follow-on: `python enrichment/fetch_zhihu.py` (runs on the URL this skill returns)
