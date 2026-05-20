# Wiki Operation Log

Reverse-chronological. Newest entries on top.

- 2026-05-19 — W4 synthesize wiki context injection shipped (kb/services/wiki_inject.py + kb/services/synthesize.py modification): Case A inline prepend of `<wiki_context>...</wiki_context>` to query_text before `synthesize_response`; read-only per Decision 4 (synthesize never writes back); 4 integration tests + 5 fallthrough unit tests pin observable behavior
- 2026-05-19 — W3 ingest hook + lint guard shipped: `_wiki_update_check` fires after final layer2 drain in `batch_ingest_from_spider.ingest_from_db`; behavior-anchor test pins call-once + exception-suppression + 16-char SHA256 hash contract (`lib.checkpoint.get_article_hash`); fixture schema extended with `articles.content_hash + enriched`
- 2026-05-19 — W2 Hermes operator prompt generated at `.planning/phases/llm-wiki-integration/HERMES-PROMPT-W2.md` (awaiting user forward)
- 2026-05-19 — W0 scaffold created (port from `~/wiki-omnigraph/`)
