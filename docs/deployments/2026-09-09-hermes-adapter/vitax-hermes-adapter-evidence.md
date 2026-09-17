# VitaX Hermes adapter evidence

Recorded: 2026-09-09
Scope: local, offline adapter implementation and fake-executable tests only.
No Hermes binary, SSH target, real model, provider request, production setting,
commit, or deployment was used.

## RED -> GREEN

- RED: initial adapter contract tests failed before implementation; subsequent
  child-holds-stdout-pipe test reproduced the process-group cleanup defect.
- RED: strict text-only review cases initially reached the fake executable;
  a lone UTF-8 surrogate surfaced `UnicodeEncodeError`.
- GREEN: `OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest
  tests/unit/test_llm_complete.py tests/unit/test_llm_router.py
  tests/unit/test_llm_hermes.py -q` completed with `34 passed in 1.12s`.
- GREEN: `.venv/bin/python -m py_compile lib/llm_hermes.py
  lib/llm_complete.py` and scoped `git diff --check` passed.
- GREEN: `.venv/bin/python -m pip check` reported `No broken requirements found.`

## Dependency receipts

- Before: `/tmp/vx004-pip-freeze-before.txt` (138 bytes)
- After: `/tmp/vx004-pip-freeze-after.txt` (670 bytes)
- Installed only into project `.venv`: aiolimiter, tenacity, numpy, requests,
  openai, and google-genai plus their resolver dependencies. No torch,
  LightRAG, requirements-file change, or global install.

## Candidate file SHA-256

| File | SHA-256 |
| --- | --- |
| `lib/llm_hermes.py` | `6ec2edd54d095c6350415e2dae78e862a782b15a9394183dfe6168e9fbc30a9d` |
| `lib/llm_complete.py` | `07e75cb7d953496c1b2999beccc5713dc29d221524b628f482de6ee5de1580b7` |
| `tests/unit/test_llm_hermes.py` | `1ed31137bc92710e59a20958538c35843ce755797e99cdde693841e78eb2b283` |

## Timeout parse redaction amendment

`OMNIGRAPH_HERMES_TIMEOUT_SECONDS=SYNTHETIC_NON_NUMERIC` is rejected before
spawn with an exception whose `__cause__` is `None`; its formatted traceback
does not contain the synthetic value.

## Pending boundary

Do not execute the proposed OHPC `/tmp` synthetic real-adapter call until the
controller explicitly authorizes it. This adapter remains experimental and
non-production.
