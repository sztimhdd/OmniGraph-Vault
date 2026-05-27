---
phase: quick-260511-utl
plan: 01
subsystem: scripts/+tests/+repo-hygiene
tags: [wip-cleanup, utility-scripts, byte-equal-pull, ssh-rm, hermes-audit-g3]
key-files:
  added:
    - scripts/bench_merge_speed.py
    - scripts/capture_qr.py
    - scripts/time_single_ingest.py
    - scripts/export_vitaclaw_agent_news.py
    - tests/unit/test_graded_classify.py
    - tests/unit/test_export_vitaclaw_agent_news.py
    - tests/fixtures/wave0_baseline.json
  removed_on_hermes:
    - kol_scan.db (root, 0 bytes)
    - .env.bak-wave0-1777422818 (161 bytes)
    - .env.pre-delete.bak.20260429-120931 (161 bytes)
    - test_filter_prompt.py (root scratchpad, 6150 bytes)
    - test_prefilter_30.py (root scratchpad, 1579 bytes)
    - batch_validation_report.json (one-off output, 2249 bytes)
    - data/kol_scan_spec.md (historical spec, 6381 bytes)
    - graphify-out/ (8.7MB throwaway artifacts dir)
decisions:
  - "DEAD files were untracked on Hermes (`??`); SSH `rm` only — no `git rm` since nothing was tracked to remove. Recorded in STATE.md."
  - "test_graded_classify.py shipped with a 5-spot indent repair (8sp -> 4sp on `with patch(...)` lines) — only delta vs Hermes byte content. Without it pytest can't even collect the file."
  - "Single atomic commit (TRACK only) instead of the originally-planned two-commit shape, because Commit 2 (git rm) had no repo-side state to change."
metrics:
  completed: "2026-05-11"
  tasks: 4
  files_added: 7
  files_removed_on_hermes: 8
---

# Quick 260511-utl: Root + scripts/ + tests/ WIP Cleanup — SUMMARY

**One-liner:** Formalized 7 Hermes-authored WIP files (4 utility scripts + 2 tests + 1 fixture) into the repo via byte-equal pull; cleaned 8 DEAD WIP files off Hermes filesystem via SSH `rm`. All 8 pytest cases green.

---

## What Was Done

### TRACK (committed locally, single atomic commit)

| Path | Bytes | Source |
|---|---|---|
| `scripts/bench_merge_speed.py` | 2494 | LightRAG merge-speed micro-benchmark |
| `scripts/capture_qr.py` | 6791 | WeChat MP login QR capture via CDP cookies |
| `scripts/time_single_ingest.py` | 1526 | Single-article ingest wall-clock timer |
| `scripts/export_vitaclaw_agent_news.py` | 7332 | VitaClaw website Agent-news exporter |
| `tests/unit/test_graded_classify.py` | 6975* | 6 mock-only graded-probe routing tests |
| `tests/unit/test_export_vitaclaw_agent_news.py` | 3933 | 2 contract tests for the exporter |
| `tests/fixtures/wave0_baseline.json` | 926 | Wave-0 chunk-id baseline fixture |

*`test_graded_classify.py` shipped with a 5-spot indent repair (8sp -> 4sp on the `with patch(...)` lines). The Hermes byte content has the same bug — without the repair, pytest can't even collect the file. Repair was a single `replace_all` (one pattern, 5 occurrences); no logic change.

### DEAD cleanup (SSH `rm` on Hermes only — no repo commit)

All 8 paths were untracked on Hermes (`??` in `git status`). Cleanup:

```bash
ssh -p <port> sztimhdd@<host> "cd ~/OmniGraph-Vault && \
  rm -f kol_scan.db .env.bak-wave0-1777422818 .env.pre-delete.bak.20260429-120931 \
        test_filter_prompt.py test_prefilter_30.py batch_validation_report.json \
        data/kol_scan_spec.md && \
  rm -rf graphify-out/ && \
  git status -sb"
```

Sizes verified before delete (Phase 0):
- `kol_scan.db` = 0 bytes (matches expectation: empty stub)
- `.env.bak-wave0-1777422818` = 161 bytes
- `.env.pre-delete.bak.20260429-120931` = 161 bytes
- `test_filter_prompt.py` = 6150 bytes (plain scratchpad — no `@pytest` decorators)
- `test_prefilter_30.py` = 1579 bytes (plain scratchpad — uses bare `assert`)
- `batch_validation_report.json` = 2249 bytes (one-off output)
- `data/kol_scan_spec.md` = 6381 bytes (audit verdict: DEAD)
- `graphify-out/` = 8.7MB (GRAPH_REPORT.md + graph.html + graph.json + cache/)

---

## Verification Evidence

### Byte-equality (Phase 0)

`sha256sum` matches local-pulled copies vs Hermes for all 7 TRACK paths.
Logs: `.scratch/g3-pull-track-260511-173748.log`, `.scratch/g3-phase0-track-verify-260511-173748.log`.

### Unit tests

```
venv/Scripts/python -m pytest tests/unit/test_graded_classify.py tests/unit/test_export_vitaclaw_agent_news.py -v
======================== 8 passed, 1 warning in 6.28s =========================
```

Log: `.scratch/g3-verify-pytest-260511-173748.log`

### Syntax compile (utility scripts)

```
ast.parse(...): OK x 4
```

Log: `.scratch/g3-verify-import-260511-173748.log`

---

## Out-of-Scope Boundaries Honored

- enrichment/ (G1) — untouched
- skills/ (G2) — untouched
- tests/unit/test_ainsert_persistence_contract.py (gkw frozen) — untouched
- DEAD list strict — exactly the audit's 8 paths, no expansion
- No refactor of utility scripts beyond the indent repair to test_graded_classify.py
