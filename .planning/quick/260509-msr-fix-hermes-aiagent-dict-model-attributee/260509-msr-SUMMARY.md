---
quick_id: 260509-msr
description: fix Hermes AIAgent dict-model AttributeError blocking daily-ingest cron
date: 2026-05-09
status: applied (Priority B vendor patch); cron remains PAUSED per STOP gate
---

# Quick Task 260509-msr: Summary

## What changed

**On Hermes (`~/.hermes/hermes-agent/`) — NOT in OmniGraph-Vault repo:**

1. **Patched `run_agent.py`** at `_anthropic_prompt_cache_policy` (~line 2992): added 4-line `isinstance(eff_model, dict)` guard that coerces to `eff_model.get("model") or eff_model.get("default") or ""`. Sentinel comment `[PATCH-260509-msr]` marks the change.
2. **Created `~/.hermes/hermes-agent/PATCHES/`** containing `README.md` + `260509-msr-apply.py` + `260509-msr-verify.py`. The README explains: what the patch does, the unisolated root cause, the diagnosis evidence trail, and instructions to re-apply after `hermes update`.

**No changes to OmniGraph-Vault repo source code.** Only `.planning/quick/260509-msr-*/` planning artifacts (this file + PLAN.md) and `.scratch/hermes-msr-260509-*.log` evidence files (gitignored).

## Root cause

**Not isolated.** Diagnosis status:

- 2026-05-09 09:00:31 ADT cron tick crashed with `AttributeError: 'dict' object has no attribute 'lower'` at `run_agent.py:2992` — raw evidence in `~/.hermes/cron/output/2b7a8bee53e0/2026-05-09_09-00-31.md` and `~/.hermes/logs/errors.log` (see `.scratch/hermes-msr-260509-49-0900-context.log`).
- 2026-05-09 16:32:13 ADT cron tick (same `config.yaml` + `jobs.json`, no source changes between the two ticks) succeeded — see `.scratch/hermes-msr-260509-46-1632-output.log`. Daily ingest reported 2/1548 fresh OK + 1544 Layer-1 rejects.
- Direct `cron.scheduler.run_job(job)` REPL invocation succeeded both before and after the patch — see `.scratch/hermes-msr-260509-58-postfix2.log` (`run_job returned without exception`).
- Bug appears intermittent; suspected cause: stale state in long-running gateway daemon process (a 16:26 daemon-warmup log line in `agent.log` suggests a fresh module-state reset between the two ticks). Confirming this would require attaching to the live daemon mid-crash, which we did not do.

The traceback unambiguously points to `eff_model = (model if model is not None else self.model) or ""` then `eff_model.lower()` — meaning `self.model` was a dict at the moment of the cron-tick crash. Since `cron/scheduler.py:1208-1224` already accepts `config.yaml`'s `model: {model:..., provider:...}` shape AND scheduler's local `model` var stays string for daily-ingest's job (because `job.get("model") = "deepseek-v4-flash"`), the dict must enter `self.model` somewhere inside `AIAgent.__init__` (lines 1021-1235). All `self.model = ...` assignments in that range either pass through string args or call `normalize_model_for_provider` (signature returns `str`). The dict-injection code path was NOT pinned to a specific line.

## Why Priority B (vendor patch), not Priority A (config flatten)

User spec'd Priority A first IF safe:
> 优先 A:修 config.yaml 的格式 ... 但需先验证 scheduler.py 的 provider routing 不依赖于 nested dict 形式

Verification of Priority A safety would require reading every code path that consumes `_cfg.get("model")` across `cron/scheduler.py`, `cli.py`, `gateway/run.py`, and config-load helpers. That's a broader audit than a quick task warrants for an intermittent bug. Priority B is surgical, idempotent, behavior-preserving on the happy path, and was explicitly listed as acceptable in the user's spec.

## Verification

| Test | Evidence | Result |
|---|---|---|
| Syntax check post-patch | `.scratch/hermes-msr-260509-52-apply-fix.log` | `syntax OK` |
| `hermes --version` post-patch | `.scratch/hermes-msr-260509-64-version-check.log` | imports cleanly |
| Unit harness: dict→str coerce (4 cases) | `.scratch/hermes-msr-260509-54-verify.log` | TEST 1 (False, False); TEST 2 (True, True); TEST 3 graceful degrade; TEST 4 (False, False) — no AttributeError |
| Direct `run_job(job)` invocation post-patch | `.scratch/hermes-msr-260509-58-postfix2.log` | `run_job returned without exception` |
| `hermes cron run 2b7a8bee53e0` trigger post-patch | `.scratch/hermes-msr-260509-59-trigger.log`, errors.log unchanged | no new AttributeError in `~/.hermes/logs/errors.log` |

Note: the scheduler tick I triggered at 16:48:59 didn't visibly fire (last_run_at stayed at 16:32:13) — likely the gateway scheduler was idle. The patch path was verified via the unit-style harness + direct run_job; no live-scheduler-tick evidence post-patch was captured. This is a known limitation of the verification.

## STOP gate honored

`hermes cron pause 2b7a8bee53e0` re-applied at 2026-05-09 16:50:59 ADT (the trigger had auto-enabled the job).

Current state (`.scratch/hermes-msr-260509-63-paused-confirm.log`):

```
state: paused enabled: False paused_at: 2026-05-09T16:50:59.175480-03:00
last_run_at: 2026-05-09T16:32:13.661194-03:00 last_status: ok last_error: None
```

User decides when to resume.

## Files (Hermes side)

| Path | Status |
|---|---|
| `~/.hermes/hermes-agent/run_agent.py` | patched (sentinel `[PATCH-260509-msr]`) |
| `~/.hermes/hermes-agent/PATCHES/README.md` | new — re-apply guide |
| `~/.hermes/hermes-agent/PATCHES/260509-msr-apply.py` | new — idempotent re-apply script |
| `~/.hermes/hermes-agent/PATCHES/260509-msr-verify.py` | new — verification harness |
| `/tmp/run_agent.py.bak.260509-msr` | unchanged baseline backup |

## Files (OmniGraph-Vault repo)

| Path | Status |
|---|---|
| `.planning/quick/260509-msr-.../260509-msr-PLAN.md` | new |
| `.planning/quick/260509-msr-.../260509-msr-SUMMARY.md` | new (this file) |
| `.scratch/hermes-msr-260509-*.log` | new — gitignored evidence trail |
| `.scratch/hermes-msr-260509-{instrument,fix,verify,runjob,PATCHES-README}.{py,md}` | new — gitignored scripts |

## What still needs human attention

1. **Re-apply after `hermes update`.** v0.13.0 is 173 commits behind; whenever the user updates, run `python3 ~/.hermes/hermes-agent/PATCHES/260509-msr-apply.py` again.
2. **Watch for upstream fix.** After update, `git log run_agent.py | grep -i 'cache_policy\|prompt_cache'` to see if upstream fixed it natively — if so, remove the local patch.
3. **Resume cron when ready.** `hermes cron resume 2b7a8bee53e0` whenever the user is satisfied with the fix. Next cron fire: 2026-05-10 09:00 ADT (or `hermes cron run` to force-execute earlier).
4. **Consider deeper RCA.** If the bug recurs after the patch (the patch silences it but the dict-injection code path is still alive), capture daemon state at crash time — likely needs `gdb`/`py-spy` attach to the gateway PID.
