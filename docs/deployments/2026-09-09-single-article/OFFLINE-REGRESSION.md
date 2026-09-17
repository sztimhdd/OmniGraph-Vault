# Single-article offline regression

Date: 2026-09-09

## Command and result

```bash
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest -q \
  tests/unit/test_sync_from_aliyun_exit_status.py \
  tests/unit/test_config_env_loading.py \
  tests/unit/test_ingest_prestart_read_only.py \
  tests/unit/test_cleanup_stuck_docs.py \
  tests/unit/test_llm_complete.py \
  tests/unit/test_llm_router.py \
  tests/unit/test_llm_hermes.py \
  tests/unit/test_vitax_isolated_ingest.py \
  tests/unit/test_publication_manifest.py \
  tests/unit/test_vitax_single_article_probe.py
```

Exit: 0. Result: 84 passed in 1.39s.

```bash
git -c core.whitespace=cr-at-eol diff --check
```

Exit: 0.

## Candidate SHA-256

| File | SHA-256 |
| --- | --- |
| `scripts/vitax_single_article_probe.py` | `14514de3d51d81a943d88f2765f6cd0691e292ddecc39c395938dc95cc0c1a73` |
| `tests/unit/test_vitax_single_article_probe.py` | `37c5462c07262e1ad555c017734cade7d14f7691f8f792f9527f8e5bc66c2693` |
| `docs/deployments/2026-09-09-single-article/README.md` | `8be45e132a5b3f64975711f723fb87ed00728a516c5fa3c99402fd0bfa687640` |

This run used only offline unit tests. It did not install dependencies, invoke
Hermes or embedding services, start a tunnel, perform SSH, or run a real
ingestion.
