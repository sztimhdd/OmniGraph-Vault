# W1 Entity Selection — Locked 14

**Date:** 2026-05-20
**Source:** `.scratch/llm-wiki-50-candidates-260519-cleaned.md` (cleaned + clustered ranking from `.scratch/llm-wiki-50-candidates-260519.md`)

## Final pick (14)

```
Hermes
OpenClaw
Superpowers
Agent
Harness
Claude Code
Skills
Context Engineering
Anthropic
Memory System
SOUL.md
Gateway
LangChain
MemoryProvider
```

## Slug mapping (file names)

| Canonical entity name | Page slug | Wiki path |
|----------------------|-----------|-----------|
| Hermes | hermes | kb/wiki/entities/hermes.md |
| OpenClaw | openclaw | kb/wiki/entities/openclaw.md (overwrites W0 placeholder) |
| Superpowers | superpowers | kb/wiki/entities/superpowers.md |
| Agent | agent | kb/wiki/entities/agent.md |
| Harness | harness | kb/wiki/entities/harness.md |
| Claude Code | claude-code | kb/wiki/entities/claude-code.md |
| Skills | skills | kb/wiki/entities/skills.md |
| Context Engineering | context-engineering | kb/wiki/entities/context-engineering.md |
| Anthropic | anthropic | kb/wiki/entities/anthropic.md |
| Memory System | memory-system | kb/wiki/entities/memory-system.md |
| SOUL.md | soul-md | kb/wiki/entities/soul-md.md |
| Gateway | gateway | kb/wiki/entities/gateway.md |
| LangChain | langchain | kb/wiki/entities/langchain.md |
| MemoryProvider | memory-provider | kb/wiki/entities/memory-provider.md |

## Rejected (documented for transparency)

- **Mem0 / Codex / Andrei Karpathy / A2A** — dropped because corpus has 0–1 chunks each; pure Karpathy citation contract (D1 locked) cannot be satisfied
- **MCP** — dropped per user `C 不加`; design doc named it as priority but corpus has only 4 fragmented chunks; revisit when corpus density improves
- **Lin trio (Xiaomo / Xiaoguan / Xiaotan), Honcho, Ye Xiaochai, Hv-analysis, Pi Agent** — not picked this round; available for v2 batch

## Resume command

After this file is in place + `llm-wiki-02-COST-ESTIMATE.md` has `approved: yes`:

```bash
venv/Scripts/python.exe scripts/wiki_generate_pages.py \
  --entities .planning/phases/llm-wiki-integration/llm-wiki-w1-selection-260520.md \
  --cost-gate .planning/phases/llm-wiki-integration/llm-wiki-02-COST-ESTIMATE.md \
  --output-dir kb/wiki/entities/
```
