---
quick_id: 260509-msr
description: fix Hermes AIAgent dict-model AttributeError blocking daily-ingest cron
created: 2026-05-09
mode: quick
---

# Quick Task 260509-msr: Plan

## Goal

Hermes daily-ingest cron (id `2b7a8bee53e0`) crashed at 2026-05-09 09:00:31 ADT during AIAgent init:

```
AttributeError: 'dict' object has no attribute 'lower'
  run_agent.py:2992 in _anthropic_prompt_cache_policy
    model_lower = eff_model.lower()
```

Goal: stop the crash so the next 06:00/09:00 ADT cron tick can complete AIAgent init and run the daily-ingest workflow. Scope: ONLY in `~/.hermes/hermes-agent/` on Hermes — not OmniGraph-Vault code.

## Scope boundary

| Location | Allowed? |
|---|---|
| `~/.hermes/hermes-agent/run_agent.py` (vendor patch) | YES |
| `~/.hermes/config.yaml` (user config flatten) | YES (Priority A if validated) |
| `~/OmniGraph-Vault/**/*.py` | NO |
| `.planning/quick/260509-msr-*` (this dir) | YES (planning artifacts only) |

## Tasks

### Task 1: Reproduce + locate

- SSH to Hermes (per `~/.claude/projects/.../memory/hermes_ssh.md`)
- Try `AIAgent(model="deepseek-v4-flash", provider="deepseek")` directly — verify if `self.model` is dict
- Read scheduler.py:1208-1347 (cron path) + run_agent.py around 1021/1235/2992 (AIAgent init + cache policy)
- Trigger actual scheduler cron tick to capture full traceback

**Verify:** raw log from `~/.hermes/cron/output/.../...md` or `errors.log` with the AttributeError stack pinned to a specific code path.

**Done when:** root cause is named OR, if intermittent and unisolatable, that observation is itself documented with evidence.

### Task 2: Apply minimal fix

Pick A or B based on Task 1 evidence:

- **Priority A** — flatten `~/.hermes/config.yaml` from `model: {model: ..., provider: ...}` to top-level `model:` + `provider:`. Only safe if scheduler.py and AIAgent paths don't require nested dict.
- **Priority B** — defensive coerce in `_anthropic_prompt_cache_policy`: when `eff_model` is dict, fall back to `eff_model.get("model") or eff_model.get("default") or ""`. Mirrors scheduler.py:1208-1224.

Patch must be surgical (3-5 lines) and idempotent (sentinel comment so re-apply is no-op).

**Verify:** `python3 -c 'import ast; ast.parse(open(".../run_agent.py").read())'` syntax check; `hermes --version` imports cleanly.

**Done when:** patch file applied + sentinel present + syntax check passes.

### Task 3: Verify

- Run a unit-style harness that forces `self.model = {"model": "deepseek-v4-pro", "provider": "deepseek"}` and calls `_anthropic_prompt_cache_policy()` — must NOT raise.
- Trigger `hermes cron run 2b7a8bee53e0` and observe scheduler tick (or fall back to direct `cron.scheduler.run_job(job)` if scheduler is idle).
- Per STOP gate, **re-pause cron** (`hermes cron pause 2b7a8bee53e0`) before reporting — do NOT leave the daily-ingest cron enabled.

**Verify:** `~/.hermes/logs/errors.log` has no new `AttributeError: 'dict' object has no attribute 'lower'` after the trigger; harness prints all 4 test results without crash.

**Done when:** evidence chain in `.scratch/hermes-msr-260509-*.log` shows pre-fix crash + post-fix pass.

### Task 4: Document

- Write `~/.hermes/hermes-agent/PATCHES/README.md` describing the patch + when to remove + how to re-apply after `hermes update`.
- Save apply + verify scripts to `~/.hermes/hermes-agent/PATCHES/260509-msr-{apply,verify}.py`.

**Done when:** `~/.hermes/hermes-agent/PATCHES/` populated with 3 files (README + apply + verify).

## STOP gate

Daily-ingest cron MUST remain paused after fix. Report to user; user decides when to resume.

## Anti-fabrication

- Every "I ran X / verified Y" claim must cite a real `.scratch/hermes-msr-260509-NN-*.log` path.
- No vendor-patch commit message virtue ("已验证可用") — only what changed + why.
