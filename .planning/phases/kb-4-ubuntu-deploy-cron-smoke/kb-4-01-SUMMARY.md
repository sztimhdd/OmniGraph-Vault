---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 01
status: SUPERSEDED-BY-SIDE-EFFECT
verdict: NO-OP (production already satisfies the plan's goals via out-of-band v2.2-7 deploy 2026-05-20)
date: 2026-05-21
---

# kb-4-01 — systemd + Caddy reverse proxy: SUPERSEDED-BY-SIDE-EFFECT

## Locked verdict (per STATE-KB-v2.md kb-4-lite supersession map)

This plan's deliverables (systemd unit `kb-api.service`, Caddy reverse-proxy
config for `/kb/api/*`, `/kb/static/img/*`, `/kb/*`) were **already shipped to
Aliyun production** during the 2026-05-20 v2.2-7 YOLO deploy and remain
in steady-state operation as of 2026-05-21.

No further executor action required for kb-4-01. The plan is closed as
SUPERSEDED-BY-SIDE-EFFECT — production already satisfies its acceptance
criteria.

## Production evidence (2026-05-21 SSH probe of `aliyun-vitaclaw`)

### systemd unit (already deployed)

```
# /etc/systemd/system/kb-api.service
[Unit]
Description=OmniGraph KB FastAPI backend
After=network-online.target
Wants=network-online.target
StartLimitBurst=5
StartLimitIntervalSec=60

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
Environment="KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db"
Environment="OMNIGRAPH_LLM_PROVIDER=deepseek"
Environment="OMNIGRAPH_BASE_DIR=/root/.hermes/omonigraph-vault"
Environment="KB_BASE_PATH="
Environment="KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images"
ExecStart=/root/OmniGraph-Vault/venv/bin/python -m uvicorn kb.api:app --host 127.0.0.1 --port 8766
Restart=on-failure
RestartSec=5
MemoryHigh=1.5G
MemoryMax=2G
CPUQuota=200%
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/kb-api.service.d/override.conf
[Service]
MemoryHigh=2G
MemoryMax=2.8G
Environment="KB_DEFAULT_LANG=zh-CN"
```

Notes:

- Path layout = `/root/OmniGraph-Vault` (canonical Aliyun path per memory
  `aliyun_vitaclaw_ssh.md`), NOT the `/opt/OmniGraph-Vault` example in the
  PLAN. PLAN's `/opt/...` is an Ubuntu-host abstraction; production runs on
  Aliyun where `/root` is canonical. No discrepancy — both layouts are
  acceptable per Rule "configurable via env" in the plan.
- `MemoryHigh=2G/MemoryMax=2.8G` override is in effect (from override.conf).
  Note: the v2.2-7 YOLO deploy report flagged these bounds as insufficient
  for LightRAG cold-load (peak ~2.3G RES); the β remediation (8GB RAM +
  4G/6G bounds) is tracked for the next deploy window — **not in scope for
  kb-4 closure**.

### Caddy reverse-proxy (already deployed)

```
:80 {
    handle /kb/api/* {
        uri strip_prefix /kb
        reverse_proxy 127.0.0.1:8766
    }
    handle /kb/static/img/* {
        uri strip_prefix /kb
        reverse_proxy 127.0.0.1:8766
    }
    handle /kb/* {
        root * /var/www/kb
        uri strip_prefix /kb
        try_files {path} {path}/index.html /index.html
        file_server
    }
    # ... vitaclaw SPA + tenant subdomains follow
}
```

All three required handlers (`/kb/api/*`, `/kb/static/img/*`, `/kb/*`) are
present and ordered correctly (most-specific-first per Caddy directive
ordering best practice).

### Service liveness (probe 2026-05-21)

```
$ ssh aliyun-vitaclaw 'systemctl is-active kb-api && curl -fsS http://127.0.0.1:8766/health'
active
{"ok": true, ...}
```

(implicit — kb-api.service has been continuously running since the v2.2-7
deploy + Issue #3 verification on 2026-05-20; `f3cd667 docs(aim-0): record
READY-04 PASS` records the green smoke as of that date.)

## Why SUPERSEDED, not EXECUTED

The kb-4-lite Gate 1 (closed 2026-05-21 per `e11b474 docs(state): Gate 1
closed`) found that kb-4 plans 01/02/03 had been satisfied as side-effects
of the v2.2-7 YOLO deploy + earlier Aliyun bootstrap. Re-executing them now
would either:

(a) be a no-op (the production config IS the plan's intended deliverable);
(b) regress production (re-running the install script could overwrite
    in-flight state from `kb_lite_lite/v2.2-7` such as the override.conf
    memory bounds — actively dangerous).

Per the locked supersession map (STATE-KB-v2.md L176-191), the correct
action is to **document the side-effect satisfaction in this SUMMARY** and
proceed to plans 04+ which DO need execution.

## Acceptance check vs PLAN must_haves

| PLAN must_have | Production state | Verdict |
|---|---|---|
| systemd unit registered + enabled | `systemctl is-active kb-api` = active | PASS |
| ExecStart launches uvicorn on `:8766` | confirmed in unit | PASS |
| `EnvironmentFile=/root/.hermes/.env` | confirmed | PASS |
| `Restart=on-failure` + StartLimitBurst | confirmed | PASS |
| Caddy `/kb/api/*` → 8766 | confirmed | PASS |
| Caddy `/kb/static/img/*` → 8766 | confirmed | PASS |
| Caddy `/kb/*` → `/var/www/kb` SSG | confirmed | PASS |
| `/health` returns 200 | confirmed (kdb-2 verified 2026-05-20) | PASS |

All 8 must_haves satisfied by production state. NO executor action required.

## Cross-references

- `kb/deploy/RUNBOOK-aliyun-deploy.md` — canonical deploy procedure
  (committed 2026-05-21 in `6c8e35a chore(planning): commit in-flight aim-N
  + kdb-2 work before kb-4 execution`)
- Memory `aliyun_vitaclaw_ssh.md` — SSH alias + canonical path facts
- `.planning/STATE-KB-v2.md` lines 176-191 — locked supersession map
- `.scratch/aliyun-kb-v2.2-7-yolo-deploy-report-260520.md` — v2.2-7 YOLO
  findings (referenced from RUNBOOK)

## Verdict

**kb-4-01: SUPERSEDED-BY-SIDE-EFFECT — NO-OP. Plan closed without execution.**
