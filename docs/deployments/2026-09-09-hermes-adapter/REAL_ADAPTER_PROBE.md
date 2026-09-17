# Hermes experimental text-adapter probe

Date: 2026-09-09
Scope: one authorized, non-production synthetic callback invocation on OHPC.

## Preconditions

- SSH alias `OHPC` reported hostname `OH-Desktop`.
- `/home/sztimhdd/.local/bin/hermes --version` reported Hermes Agent `v0.21.1`.
- Read-only inspection of `~/.hermes/hermes-agent/toolsets.py` found static
  `bot_room` defined as `_ts("Verified text-only Group Chat turn capabilities")`.
  `_ts` defaults `tools` and `includes` to empty tuples, so this static entry
  has no tools or includes.
- Remote copied adapter SHA-256 matched local accepted candidate:
  `6ec2edd54d095c6350415e2dae78e862a782b15a9394183dfe6168e9fbc30a9d`.

## One-shot result

The copied adapter ran only from
`/tmp/vitax-hermes-adapter-probe-8GcdY9/` via stdlib `importlib`, outside the
production repository. Outer timeout was 120 seconds; adapter timeout was 90
seconds. Environment set `OMNIGRAPH_LOAD_ENV=0` and the explicit Hermes binary.

| Check | Result |
| --- | --- |
| Outer process exit | `0` |
| Adapter duration | `30.775` seconds |
| Returned lines | `VITAX_ADAPTER_PROBE_OK`; `17*19=323` |
| Exact two-line assertion | pass |
| Usage load status | `ok` |
| Usage allowlist | provider `openai-codex`; model `gpt-6-astra`; failed `false`; api_calls `1`; session_id `20260909_123924_1b45af` |

The harness wrapped the original `_load_usage` only to observe the listed
fields, returning its original tuple unchanged. It did not record `failure`,
raw stdout/stderr beyond the synthetic expected text, auth material, or config.
No retry, fallback, login, or configuration change was performed.

## Local regression after probe

With `OMNIGRAPH_LOAD_ENV=0`, the following seven files completed with
`56 passed in 1.53s`:

- `tests/unit/test_sync_from_aliyun_exit_status.py`
- `tests/unit/test_config_env_loading.py`
- `tests/unit/test_ingest_prestart_read_only.py`
- `tests/unit/test_cleanup_stuck_docs.py`
- `tests/unit/test_llm_complete.py`
- `tests/unit/test_llm_router.py`
- `tests/unit/test_llm_hermes.py`

The project `.venv` reported `No broken requirements found.` from `pip check`.

## Boundary

This is a PASS for one real Hermes text-adapter call using the experimental
isolated file. It is not an ingest, KG, content-quality, production-routing,
or production-readiness PASS.
