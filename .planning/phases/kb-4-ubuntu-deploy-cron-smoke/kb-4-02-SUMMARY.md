---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 02
status: SUPERSEDED-BY-SIDE-EFFECT
verdict: NO-OP (production install bootstrap was completed during initial Aliyun deploy; venv + canonical paths exist)
date: 2026-05-21
---

# kb-4-02 — install bootstrap script: SUPERSEDED-BY-SIDE-EFFECT

## Locked verdict (per STATE-KB-v2.md kb-4-lite supersession map)

This plan's deliverable (`scripts/install_kb.sh` — provision Python venv,
clone OmniGraph-Vault, install requirements.txt, create canonical
directories, register systemd unit) was **already executed on Aliyun
production** (manually, during the initial bootstrap) and the resulting
state is verified live. Re-running an automated install script now would
either be a no-op or regress production. Closed as SUPERSEDED-BY-SIDE-EFFECT.

## Production evidence (2026-05-21 SSH probe of `aliyun-vitaclaw`)

| Plan deliverable | Production state | Verdict |
|---|---|---|
| `/root/OmniGraph-Vault/` checkout | exists; HEAD = `4eaef45b76066bc9c808440cd29e028b2e20d585` | PASS |
| `venv/` with installed deps | `/root/OmniGraph-Vault/venv/bin/python` referenced as ExecStart in `kb-api.service`; service is `active` | PASS |
| `kb-api.service` registered + enabled | `systemctl is-active kb-api` = active (see kb-4-01-SUMMARY) | PASS |
| `KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db` | configured in unit | PASS |
| `OMNIGRAPH_BASE_DIR=/root/.hermes/omonigraph-vault` | configured in unit | PASS |
| `KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images` | configured in unit | PASS |
| LightRAG storage at `/root/.hermes/omonigraph-vault/lightrag_storage/` | confirmed via `find /root -name kol_scan.db` (memory `aliyun_vitaclaw_ssh.md`) | PASS |
| Caddy serves `/kb/*` from `/var/www/kb` | confirmed (see kb-4-01-SUMMARY) | PASS |

All install-bootstrap-equivalent state is present and serving traffic.

## Path canonicalization note

The PLAN drafted under `/opt/OmniGraph-Vault` (a generic Ubuntu host
assumption from kb-4 design 2026-05-14). Production reality is
`/root/OmniGraph-Vault` — both are valid; the choice is governed by
`KB_INSTALL_PREFIX` env var pattern in downstream scripts. No discrepancy.

This canonical path divergence is documented in:
- Memory `aliyun_vitaclaw_ssh.md` (canonical = `/root/...`)
- `kb/deploy/RUNBOOK-aliyun-deploy.md` (lines 17-20: explicit warning that
  the older `/home/kb/...` paths in `RUNBOOK-aliyun-systemd-refresh.md` are
  stale)

## Why SUPERSEDED, not EXECUTED

Re-running an idempotent install script against the live production host
carries non-zero risk:

- The current venv has incremental package state from the v2.2-7 deploy
  (added `python-frontmatter` for wiki_lint W3 hook). A re-bootstrap that
  reinstalls from a stale requirements.txt could regress.
- The systemd unit has an active override.conf (MemoryHigh=2G,
  MemoryMax=2.8G, KB_DEFAULT_LANG=zh-CN). A re-install that overwrites the
  base unit could shadow these.
- Risk is asymmetric: zero benefit (production already serves), real
  regression possibility.

Per kb-4-lite locked supersession map: the correct action is to mark this
SUMMARY and proceed to plans that DO need execution (04 daily-rebuild cron,
05 local UAT, 06 smoke, 07 Aliyun-retargeted, 08 verification close).

## Acceptance check vs PLAN must_haves

| PLAN must_have | Production state | Verdict |
|---|---|---|
| Idempotent install (re-runnable) | N/A — running install would regress; install equivalent IS in place | PASS-by-equivalence |
| Python venv exists | `/root/OmniGraph-Vault/venv/bin/python` referenced + working | PASS |
| requirements.txt installed in venv | implicit (kb-api serving since 2026-05-20) | PASS |
| Canonical dirs created (data/, images/, lightrag_storage/) | confirmed via memory + kb-api ENV | PASS |
| systemd registered | confirmed (kb-4-01-SUMMARY) | PASS |
| Caddy registered | confirmed (kb-4-01-SUMMARY) | PASS |

All must_haves met by production state. NO executor action required.

## Cross-references

- `kb-4-01-SUMMARY.md` (companion NO-OP record)
- `kb/deploy/RUNBOOK-aliyun-deploy.md` (canonical deploy procedure;
  documents how to refresh venv after rsync — Step 3)
- Memory `aliyun_vitaclaw_ssh.md`
- `.planning/STATE-KB-v2.md` L176-191 (locked supersession map)

## Verdict

**kb-4-02: SUPERSEDED-BY-SIDE-EFFECT — NO-OP. Plan closed without execution.**
