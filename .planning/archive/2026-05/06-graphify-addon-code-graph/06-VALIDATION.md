---
phase: 6
slug: graphify-addon-code-graph
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `.planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `skill_runner.py` (in-repo, Gemini-backed) — pytest available but not used for skills |
| **Config file** | none — `skill_runner.py` reads `tests/skills/test_<skill>.json` by convention |
| **Quick run command** | `python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` |
| **Full suite command** | `python skill_runner.py skills/ --test-all` |
| **Graphify smoke** | `venv/Scripts/python -m graphify --version` (local), `ssh remote "graphify --version"` (remote) |
| **Estimated runtime** | ~30s per skill test; ~5s shell-syntax checks |

---

## Sampling Rate

- **After every task commit:** `bash -n <changed .sh file>` OR `python skill_runner.py skills/omnigraph_search --validate` (if skill touched)
- **After every plan wave:** Full `skill_runner.py` run on `omnigraph_search` + remote SSH smoke tests for installed skills
- **Before `/gsd:verify-work`:** Full suite green + Demo 1 & Demo 2 transcripts captured
- **Max feedback latency:** ~30 seconds (skill_runner) / ~10 seconds (remote SSH checks)

---

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| REQ-01 | `graphify` skill installed on Hermes | smoke | `ssh remote "test -f ~/.hermes/skills/graphify/SKILL.md && hermes skills list \| grep -q graphify"` | ❌ Wave 0 | ⬜ pending |
| REQ-02 | `graphify` skill installed on OpenClaw | smoke | `ssh remote "test -f ~/.openclaw/skills/graphify/SKILL.md"` (conditional on `command -v claw`) | ❌ Wave 0 | ⬜ pending |
| REQ-03 | `omnigraph_search` SKILL.md discoverable | unit | `python skill_runner.py skills/omnigraph_search --validate` | ❌ Wave 0 | ⬜ pending |
| REQ-04 | `omnigraph_search` returns LightRAG results | integration | `python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` + live: `venv/Scripts/python -m omnigraph_search.query "test"` | ❌ Wave 0 | ⬜ pending |
| REQ-05 | Demo 1 (streaming output) — agent routes to both skills | **manual-only** | Hermes session transcript; orchestrator saves to `docs/testing/06-demo1-transcript.md` and asserts both `graphify` and `omnigraph_search` appear in tool-use log | N/A | ⬜ pending |
| REQ-06 | Demo 2 (self-evolution) — agent combines both skills | **manual-only** | Same as REQ-05 → `docs/testing/06-demo2-transcript.md` | N/A | ⬜ pending |
| REQ-07 | Code output architecturally consistent | **manual-only** (qualitative) | Human review of Hermes session output vs OpenClaw reference | N/A | ⬜ pending |
| REQ-08 | Weekly cron rebuilds graph atomically | smoke + integration | `bash -n scripts/graphify-refresh.sh` + `ssh remote "crontab -l \| grep graphify-refresh"` + `ssh remote "bash ~/OmniGraph-Vault/scripts/graphify-refresh.sh && stat -c %Y ~/.hermes/omonigraph-vault/graphify/graphify-out/graph.json"` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/skills/test_omnigraph_search.json` — covers REQ-03, REQ-04, disambiguation vs `omnigraph_query`/`graphify`
- [ ] `skills/omnigraph_search/SKILL.md` + `scripts/query.sh` + `references/api-surface.md`
- [ ] `omnigraph_search/__init__.py` + `omnigraph_search/query.py` (new top-level module wrapping LightRAG)
- [ ] `scripts/graphify-refresh.sh` (POSIX shell, bash -n clean)
- [ ] `graphifyy` pip-installed into venv (one-time, `pip install graphifyy`)
- [ ] `docs/testing/06-demo1-transcript.md` + `06-demo2-transcript.md` (empty placeholders; filled in Wave 5)
- [ ] No pytest framework install needed — `skill_runner.py` already in repo

*Wave 0 is the skills/scripts/tests scaffold — all files created empty or stub-first so later waves drop in implementations.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Demo 1: Streaming tool output | REQ-05 | No Hermes scripting API — agent's autonomous tool-routing can only be observed in a live session | Orchestrator opens Hermes session, prompts "implement OpenClaw-style streaming tool output in the Rust fork", captures transcript, confirms tool-use log includes both `graphify` and `omnigraph_search` calls, saves to `docs/testing/06-demo1-transcript.md` |
| Demo 2: Self-evolution | REQ-06 | Same — live session required | Prompt "add Hermes-style self-evolution to the Rust fork", capture transcript to `docs/testing/06-demo2-transcript.md`, confirm both skills used |
| Architectural quality | REQ-07 | Qualitative judgment — "code mirrors OpenClaw design" is not grep-verifiable | Human review of Demo 1/2 output; compare to OpenClaw reference implementation; sign off in transcript footer |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (all scaffolded tasks have bash/shell/skill_runner checks; manual-only is concentrated in Wave 5)
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for automated, ~human minutes for manual
- [ ] `nyquist_compliant: true` set in frontmatter (after planner confirms every plan has a validation hook)

**Approval:** pending
