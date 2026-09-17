# Second-wave integrated offline regression

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
  tests/unit/test_publication_manifest.py
```

Exit: 0. Result: 75 passed in 1.70s.

```bash
git -c core.whitespace=cr-at-eol diff --check
```

Exit: 0.

```bash
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -c 'from pathlib import Path; [compile(path.read_text(encoding="utf-8"), str(path), "exec") for path in (Path("scripts/cleanup_stuck_docs.py"), Path("scripts/vitax_isolated_ingest.py"))]'
zsh -n scripts/sync-from-aliyun.sh
```

Exit: 0. These syntax checks compile Python source in memory and do not create
bytecode artifacts.

## SHA-256: three script/test pairs

| Kind | File | SHA-256 |
| --- | --- | --- |
| implementation | `scripts/sync-from-aliyun.sh` | `ce7148702119e2cf9c30f4ac032c3d390b8eb4160bfc544db37d609ba7dd4e1d` |
| implementation | `scripts/cleanup_stuck_docs.py` | `53c168bdff9044438ca33bc8e59f0b85b65ec99c115b1d6f41eb94ff22db3828` |
| implementation | `scripts/vitax_isolated_ingest.py` | `c9b36c4b85f27cd7337554656472d13fd900e45c1567b5a2cc16d9f457e91cd6` |
| test | `tests/unit/test_sync_from_aliyun_exit_status.py` | `765e4120f4f0529cb8e6b6616b0f4178b17e46addbe2ee606e5b33b60a66db56` |
| test | `tests/unit/test_cleanup_stuck_docs.py` | `dbfce4b9d4367f2ec34ccb26a52092acf1e6ac56ef09caac238e0b40d9ef796d` |
| test | `tests/unit/test_vitax_isolated_ingest.py` | `0770a8ce4f1ae9261ba6f19e7d2d7250a81372980fedc266dfd860936ccbd4e2` |

No production action, network/model invocation, deployment, installation, or
SSH operation was run. The full unit suite was not run.

## Controller completion of second-wave fingerprints

- `lib/publication_manifest.py`: `f09c6da3c606837849884b0fdb6f31af93225f74ef4bcdff83d86e21f885b4e5`
- `tests/unit/test_publication_manifest.py`: `dfcea10199c199869897829ac0f5d2f844c6a3399cc22ea09d7f9e949c13a302`
