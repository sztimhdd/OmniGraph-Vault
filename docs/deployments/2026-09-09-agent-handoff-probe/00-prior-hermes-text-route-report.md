# VitaX Hermes subscription-route check — 2026-09-09

## Scope

One fresh, synthetic, text-only route probe on Hermes (`OH-Desktop`). No login
refresh, config mutation, service restart, production-session resume, or
production data access.

## Command shape (sanitized)

```text
timeout 60 hermes -z "Reply with exactly: VITAX_HERMES_SUB_ROUTE_20260909"
  --provider openai-codex --model gpt-6-astra --toolsets bot_room
  --ignore-rules --in /tmp --usage-file <temporary-file>
```

`bot_room` is defined by `toolsets.py` as a text-only group with no tool
definitions. The temporary usage file was allowlist-parsed and removed.

## Result

| Field | Observed value |
| --- | --- |
| Remote host | `OH-Desktop` |
| Hermes CLI | `0.21.1` (upstream `ead7e91d`) |
| Exit | `0` |
| Output marker | `VITAX_HERMES_SUB_ROUTE_20260909` |
| Resolved provider | `openai-codex` |
| Resolved model | `gpt-6-astra` |
| API calls | `1` |
| Session ID | `20260909_110859_9d4db4` |
| Tool proof | Not exercised; text-only toolset |

## Interpretation

This proves one fresh text-only request over the configured Codex subscription
route with resolved runtime metadata. It does not prove an agentic tool call,
long-running unattended reliability, quota availability over time, or the
VitaX production pipeline.

## Source support

- `agent/usage_pricing.py:344-345` labels `openai-codex` as
  `subscription_included`.
- `agent/model_metadata.py:1441,1455` includes `gpt-6-astra` in Codex OAuth
  metadata.
