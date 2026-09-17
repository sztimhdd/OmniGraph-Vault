# Task D corrected independent experiment

Probe date: 2026-09-09 UTC. This addendum preserves the original two-attempt Codex-route failure record in `REPORT.md`; it records the separately authorized corrected experiment.

## Functional result

**STATUS: PASS (bounded synthetic capability only)**

[KNOWN / HIGH] Fresh Codex and Hermes synthetic scripts each directly exited `0` and emitted `VITAX_AGENT_TOOL_ASSERT_323` before the model calls.

[KNOWN / HIGH] The corrected Codex request created thread `01a086b3-6ae6-7d91-8927-cbf16446ee15`. Its JSONL event records the terminal command `python3 /tmp/vitax-agent-probe-i445f8/probe.py`, exit `0`, and the assertion marker.

[KNOWN / HIGH] The independent Hermes terminal-only request exited `0`, emitted the assertion marker, and its temporary usage record identified `openai-codex` / `gpt-6-astra`, `api_calls=2`, session `20260909_120512_38b869`.

[KNOWN / HIGH] The single Hermes-to-installed-Codex handoff exited `0` within 120 seconds. Its wrapper independently checked Codex process exit `0`, nested Codex terminal-event assertion `0`, and final-marker assertion `0`; Hermes emitted `VITAX_HERMES_CODEX_HANDOFF_PASS`.

[KNOWN / HIGH] The nested Codex handoff request created thread `01a086b8-0011-7461-a935-8bd0f811e758`, whose JSONL directly records `python3 /tmp/vitax-agent-probe-a685Up/probe.py`, exit `0`, and marker output. Hermes session `20260909_120944_b50298` is associated by its exact temporary workspace.

## Routing result

**STATUS: UNKNOWN (Codex resolved model and fallback)**

[KNOWN / HIGH] Hermes's per-run temporary usage metadata reported provider `openai-codex` and model `gpt-6-astra` for its two requests. It does not prove absence of fallback.

[KNOWN / HIGH] The two persisted Codex session metadata rows reported `model_provider: openai` but `model: null`. OHPC's `/home/sztimhdd/.opencodex/usage.jsonl` was unavailable. The evidence therefore does not prove Codex's resolved model, physical attempts, or absence of fallback.

## Boundaries

- [KNOWN / HIGH] All synthetic files were in newly-created `/tmp/vitax-agent-probe-*` directories on `OH-Desktop`.
- [KNOWN / HIGH] Hermes received only `--toolsets terminal`; no network, browser, file, delegation, login, installation, configuration, service, production, or credential operation was requested.
- [KNOWN / HIGH] Codex session persistence under `~/.codex/sessions` was an automatic metadata side effect used for request correlation. No production-source or runtime-data file was written.
- [KNOWN / HIGH] The initial handoff-wrapper construction failed locally before either model request because of SSH quoting. `09-hermes-to-codex-handoff.redacted.log` preserves that failure. `11-handoff-wrapper-write-and-syntax.redacted.log` is empty; it records no diagnostic output and does not prove that a syntax check ran or passed. The corrected handoff's functional evidence is the actual nested Codex terminal event and exit `0` in `12-hermes-to-codex-handoff-corrected.redacted.log`.

## Evidence files

- `07-independent-tool-probes.redacted.log`: direct script exits, Codex terminal event, Hermes usage metadata, and workspace-scoped Hermes session.
- `09-hermes-to-codex-handoff.redacted.log`: pre-request wrapper-construction failure.
- `10-handoff-corrected-setup.redacted.log`: fresh script direct exit.
- `11-handoff-wrapper-write-and-syntax.redacted.log`: empty output; syntax-gate status is **UNKNOWN**.
- `12-hermes-to-codex-handoff-corrected.redacted.log`: Hermes exit, nested Codex thread/event, wrapper assertions, and metadata allowlist.
