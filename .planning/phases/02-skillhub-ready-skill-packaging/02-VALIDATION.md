---
phase: 2
slug: skillhub-ready-skill-packaging
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Manual verification scripts + skill_runner.py |
| **Config file** | none — skill_runner.py is the test harness |
| **Quick run command** | `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` |
| **Full suite command** | `python skill_runner.py --test-all` |
| **Estimated runtime** | ~30 seconds (depends on API latency) |

---

## Sampling Rate

- **After every task commit:** Run quick skill_runner command for affected skill
- **After every plan wave:** Run `python skill_runner.py --test-all`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TEST-01 | integration | `python skill_runner.py --test-all` | ✅ | ⬜ pending |
| 02-01-02 | 01 | 1 | PKG-03 | manual | `bash scripts/install-for-hermes.sh` | ✅ | ⬜ pending |
| 02-01-03 | 01 | 1 | PKG-01 | manual | `bash scripts/ingest.sh --help` from /tmp | ✅ | ⬜ pending |
| 02-02-01 | 02 | 1 | SKILL-11 | experiment | `python tests/embedding_experiment.py` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | SKILL-01 | manual | word count on SKILL.md description | ✅ | ⬜ pending |
| 02-03-02 | 03 | 2 | EVAL-01 | integration | `python skill_runner.py --test-all` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements (skill_runner.py + shell wrappers already exist)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SKILL.md word count 100-200 | SKILL-01 | Word count check, no automated harness | `wc -w` on description section of each SKILL.md |
| install-for-hermes.sh on clean machine | PKG-03 | Requires clean environment | Run in fresh Docker container or clean venv |
| Shell wrappers from foreign CWD | PKG-01 | Requires changing CWD | `cd /tmp && bash /path/to/scripts/ingest.sh` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
