# Hermes text-completion contract for a LightRAG callback

Scope: read-only inspection on 2026-09-09 of Hermes Agent `0.21.1` installed on `OH-Desktop`. No model request, login, configuration change, or credential read was made.

## Decision

**CLI subprocess adapter: conditionally implementable, but only as a narrow text-completion boundary.**

[KNOWN / HIGH] The supported non-interactive interface is `hermes -z` / `--oneshot`. Its implementation suppresses all internal stdout/stderr, then writes exactly the final response to real stdout and appends one newline if necessary. It writes diagnostics to stderr on failure. A caller must capture the **entire stdout**, never its final line.

[KNOWN / HIGH] For text-only completion, pass `--toolsets bot_room` only after verifying that `bot_room` remains a no-tool group. The prior route evidence documents that property for this installed version. Do not omit `--toolsets`: without an explicit list, configured toolsets can be loaded.

[KNOWN / HIGH] `-z` has no CLI argument for an independent system prompt or supplied history. The prompt is one user string. `--resume` reloads a persistent Hermes session and its history, so it is not an acceptable per-LightRAG-call history transport: it introduces cross-call state and session writes.

## Safe subprocess contract

Use a temporary directory for the usage artifact and process isolation; do not use shell interpolation:

1. Deterministically render a single user prompt. Pass it as the argument after `-z` using `asyncio.create_subprocess_exec` (an argv list, never `shell=True`); this preserves shell metacharacters without interpolation.
2. Invoke `hermes -z <rendered-prompt> --toolsets bot_room --usage-file <temp>/usage.json --in <fresh-temp-dir>` and apply an outer `asyncio.wait_for`.
3. Capture stdout and stderr separately.
4. Return stdout only if: process exit is `0`, usage JSON is parseable, `failed` is false, and stdout after stripping is nonempty. Return the whole resulting string, retaining internal newlines.
5. Otherwise raise a typed adapter exception carrying only redacted status: process exit, timeout flag, and usage fields `failed`/`failure`/`api_calls`. Do not turn an error string into a LightRAG completion.

[KNOWN / HIGH] `hermes chat --query-file` safely accepts arbitrary text from a file, but the inspected help does not give it the `-z` final-text-only stdout contract; `-Q` says it also emits session information. Do not substitute it for `-z` in a completion adapter without a separate source-level output verification.

[INFERRED / HIGH] The `-z` argv route is bounded by the operating system's argument-size limit. It is therefore an acceptable controlled experiment only for explicitly capped LightRAG prompts. A callback that may receive larger extracted context is **BLOCKED** pending a stable Hermes file/stdin completion interface or a separately validated Python adapter.

[KNOWN / HIGH] CLI exit meanings from `hermes_cli/oneshot.py` are: `0` for nonempty final response; `1` for an uncaught agent failure or no response without a marked partial/failure; `2` for invalid explicit options or a marked failed/partial result without text. `timeout` command exit `124` is an outer-process timeout, not a Hermes provider category.

[KNOWN / HIGH] `--usage-file` is best-effort and is written even when the agent fails. It includes a `failed` boolean and `failure` string when the wrapper catches an exception, plus usage/model/provider fields. It does **not** establish a stable machine taxonomy for quota exhaustion, provider timeout, transport failure, or fallback. The adapter must classify only its own timeout versus generic Hermes failure unless Hermes source supplies a version-pinned structured reason later.

## System and history handling

[INFERRED / HIGH] LightRAG's `system_prompt` and `history_messages` must be deterministically rendered into the one user prompt with unambiguous delimiters and a statement that the content is context, before invoking the CLI. This changes role semantics compared with provider-native system/history messages; validate output quality before adoption.

[KNOWN / HIGH] The installed internal Python entry `agent.oneshot.run_oneshot` accepts `instructions`, `user_input`, token limit, temperature, timeout, and optional runtime data, constructs system+user messages, and returns a plain string or raises. It accepts no supplied conversation history and is synchronous. It is an internal source module, not a documented stable integration API; using it through `asyncio.to_thread` would avoid shell parsing but requires a separately authorized source-level adapter and direct validation of its configured route.

[KNOWN / HIGH] `hermes_cli.oneshot.run_oneshot` is also internal and returns an exit code after printing; it is the CLI implementation, not a Python text-completion client. It should not be imported as an async LightRAG provider.

## Recommended route

[INFERRED / HIGH] Do not implement a generic shell adapter that treats the last output line as an answer. If an adapter is approved, implement a small, single-purpose async subprocess bridge around `hermes -z` using an argv list, with the complete-stdout and exit/usage gates above, an explicit `bot_room` no-tool verification test, concurrency limit one, an explicit prompt-size cap, and generic failure propagation.

[KNOWN / HIGH] No current evidence supports using Hermes as an HTTP LLM endpoint for `lib.llm_complete.get_llm_func`; it is not an HTTP LLM endpoint in this deployment.

## Sources

- `13-text-completion-cli-source-discovery.redacted.log`: current CLI help, `chat --help`, and source search.
- `14-text-completion-oneshot-source.redacted.log`: `-z` usage/error/output handling.
- `15-text-completion-api-source.redacted.log`: CLI and internal `run_oneshot` signatures.
- `lib/llm_complete.py`, `lib/llm_deepseek.py`, and `lib/vertex_gemini_complete.py`: current LightRAG callback shape: async `(prompt, system_prompt, history_messages, **kwargs) -> str`.
