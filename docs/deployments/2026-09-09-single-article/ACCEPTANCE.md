# VitaX VX001 single-article independent evidence review

Review date: 2026-09-09. Scope is limited to the already-produced candidate,
`RUN.md`, and `RECEIPT_REDACTED.json` in this directory. This review did not
import business modules, run an ingest, query a model, make a tunnel, or read
production, Qdrant, Wiki, scraper, authentication, or raw-log data.

## Source and host

- [COMPUTED] The read-only `ssh OHPC hostname` result was `OH-Desktop`.
- [COMPUTED] Candidate root: `/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq`.
- [COMPUTED] The candidate runner SHA-256 is `14514de3d51d81a943d88f2765f6cd0691e292ddecc39c395938dc95cc0c1a73`, matching the authorized `14514de...1a73` value.
- [COMPUTED] The four authorized review files are the runner, `config.py`, `lib/llm_complete.py`, and `lib/llm_hermes.py`. Their candidate SHA-256 values are respectively `14514de3d51d81a943d88f2765f6cd0691e292ddecc39c395938dc95cc0c1a73`, `b4291a4fe7de055819be140622e5091693163c2803c6b1aec125286e14481a24`, `07e75cb7d953496c1b2999beccc5713dc29d221524b628f482de6ee5de1580b7`, and `6ec2edd54d095c6350415e2dae78e862a782b15a9394183dfe6168e9fbc30a9d`.
- [COMPUTED] The runner and the two supplied dispatcher/adapter authorization values match exactly. `RUN.md` independently records that all four files, including `config.py`, matched the authorized set; the `config.py` expected digest is not reproduced in the allowed local receipt.
- [COMPUTED] Static runner inspection found its `--execute` gate, delayed runtime import, budget wrapper, `OMNIGRAPH_LOAD_ENV=0` isolation setting, and fresh-reader LLM-forbidden branch. It was parsed only; no business module was imported.

## Receipt and persisted lineage

- [COMPUTED] `runs/vitax-single-article-lao1z1rb/VITAX_SINGLE_ARTICLE_PROBE.json` reports `READY_FOR_REVIEW`, `nanovectordb`, and `network_or_model_execution=attempted`.
- [COMPUTED] Both `first` and `rerun` report `PASS`, `processed=true`, `error_free=true`, `degraded=false`, 1 target chunk, 8 graph entities, 8 graph relationships, and `fresh_reader_llm_calls=0`.
- [COMPUTED] The receipt budget is `lightrag_extraction=2` plus `entity_canonicalization=2`, below `request_budget_limit=12`.
- [COMPUTED] The receipt records `OMNIGRAPH_LLM_PROVIDER=hermes`, `OMNIGRAPH_LOAD_ENV=0`, `OMNIGRAPH_VECTOR_STORAGE=nanovectordb`, `OMNIGRAPH_LOCAL_EMBED=1`, and `ENRICHMENT_ENABLED=0`.
- [COMPUTED] The original candidate receipt and local `RECEIPT_REDACTED.json` agree on all 26 comparable fields: both phase objects, receipt status, execution state, run directory, request limit, and two request-budget fields. `runner_exit_code`, `control_socket_absent`, and `embedding_port_17997_free` are local receipt additions and have no original-receipt counterpart.
- [COMPUTED] In `rag/kv_store_doc_status.json`, the single full-document key has a `processed` status. The single text chunk has exactly one document reference, and that reference resolves to the same processed document. The redacted key-set digest for document, processed-status, and chunk-document reference is `5a72abae1a5c183e0fc705e7fbcea9c0bd258ef453a652b3d4d0b3c4251ff1e7`.
- [COMPUTED] `rag/graph_chunk_entity_relation.graphml` has 8 nodes and 8 edges. Its 8 `source_id` references have one distinct value; it is the sole text-chunk key, therefore resolves to the processed document. The GraphML SHA-256 is `c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768`.
- [COMPUTED] The entity-chunk and relation-chunk maps each contain 8 entries, consistent with the GraphML node and edge counts. No synthetic document body, entity label, relation label, or raw source identifier is reproduced here.

## Acceptance boundary

- [INFERRED, HIGH] The inspected artifacts support this narrow conclusion: the existing candidate run persisted one processed synthetic document, one linked chunk, and an 8-node/8-edge GraphML whose `source_id` lineage resolves through that chunk to the processed document; the two recorded run phases meet the receipt's stated fresh-reader and request-budget fields.
- [COMPUTED] `kv_store_doc_status.json` contains one separate `failed` record: `docid=dup-fed5318dbace3179999af5d767437094`, `status=failed`, with an error field identifying already-existing content whose original document is `PROCESSED`. No document body is included in this record.
- [COMPUTED] The installed LightRAG source at `/home/sztimhdd/OmniGraph-Vault/venv/lib/python3.12/site-packages/lightrag/lightrag.py` creates a unique `dup-*` record for already-processed content and assigns it `DocStatus.FAILED`. The observed record is therefore a duplicate-insert diagnostic from the re-run, not a failed ingest of the verified unique synthetic document.
- [COMPUTED] This duplicate diagnostic remains a failed status entry. The candidate store is not status-clean, and this review does not recast it as a completely failure-free store.
- [COMPUTED] No query was rerun in this review. Any query result is pre-existing run evidence only; this review does not independently establish query correctness, semantic entity/relation correctness, model behavior, production readiness, Qdrant persistence, Wiki publication, or scraping behavior.
