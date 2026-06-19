# RUNBOOK — Aliyun KB full deploy (rsync-based)

**Audience:** vitaclaw-site go-live agent OR human operator on Aliyun ECS
**Goal:** Ship a code update from local Windows checkout → Aliyun production with
zero-drift between declared dependencies and the running venv.

**Why this exists:** The 2026-05-20 v2.2-7 YOLO deploy surfaced two production
bugs that one shared root cause: rsync moves *files* but does not refresh the
production venv. New `requirements.txt` entries silently miss the running
process until the first import fails (Finding 2 in
`.scratch/aliyun-kb-v2.2-7-yolo-deploy-report-260520.md`). This runbook closes
that gap by making the venv refresh a **mandatory, named step** — not an
afterthought.

**Scope:** General-form deploy procedure for `kb/` updates to Aliyun. For
systemd unit refresh specifically (memory bounds, env vars), see
`kb/deploy/RUNBOOK-aliyun-systemd-refresh.md` — note the latter has stale
`/home/kb/...` paths from its 2026-05-15 draft; the canonical location is
`/root/OmniGraph-Vault` (verified 2026-05-15 via `find /root -name kol_scan.db`,
recorded in memory `aliyun_vitaclaw_ssh.md`).

---

## Pre-flight

```bash
# 1. confirm SSH alias works
ssh aliyun-vitaclaw 'whoami && hostname && pwd'
# expect: root @ iZuf65iclmdqtv2ol6cazcZ in /root

# 2. confirm production layout matches expectations
ssh aliyun-vitaclaw 'ls -d /root/OmniGraph-Vault /root/OmniGraph-Vault/venv /root/.hermes/omonigraph-vault/lightrag_storage /var/www/kb /etc/systemd/system/kb-api.service'
# all 5 paths must exist; if any missing, STOP

# 3. capture pre-deploy git state on Aliyun (for the deploy report)
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && git rev-parse HEAD && git status --short | head -20'
```

**Do NOT** run `git pull` on Aliyun — HTTPS PAT prompt deadlocks the
non-interactive SSH session (verified 2026-05-15, memory
`aliyun_vitaclaw_ssh.md`). Use `rsync` instead.

---

## Step 1 — back up production state

```bash
TS=$(date +%Y%m%d-%H%M%S)

# 1a. back up systemd unit (only if you intend to touch systemd this deploy)
ssh aliyun-vitaclaw "cp /etc/systemd/system/kb-api.service /etc/systemd/system/kb-api.service.bak.$TS"

# 1b. back up DB (mandatory if migrations run)
ssh aliyun-vitaclaw "cp /root/OmniGraph-Vault/data/kol_scan.db /root/OmniGraph-Vault/data/kol_scan.db.bak.$TS"

# 1c. stash the existing kb/ tree (cheap insurance for fast rollback)
ssh aliyun-vitaclaw "cp -a /root/OmniGraph-Vault/kb /root/OmniGraph-Vault/kb.stash-pre-deploy-$TS"
```

Record `$TS` value in your deploy report — you will need it for rollback.

---

## Step 2 — rsync code changes

Identify exactly which paths the deploy needs. The minimal v2.2-7 set was:

```
kb/templates/      (Jinja2 templates)
kb/static/         (lang.js, CSS, etc.)
kb/locale/         (en + zh-CN message bundles)
kb/scripts/        (export_ssg.py + SSG drivers)
kb/api/            (FastAPI routes)
kb/services/       (DB / search / synthesize)
kb/wiki_lint.py    (W3 hook — Py3.10 compat shim required, see Notes)
requirements.txt   (declared deps — MUST sync if changed, see Step 3)
```

```bash
# rsync from local checkout (run from repo root on Windows)
rsync -avz --delete \
  kb/templates/ kb/static/ kb/locale/ kb/scripts/ kb/api/ kb/services/ kb/wiki_lint.py \
  requirements.txt \
  aliyun-vitaclaw:/root/OmniGraph-Vault/

# verify on remote
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && ls -la kb/templates kb/static kb/locale kb/scripts kb/api kb/services kb/wiki_lint.py requirements.txt | head -20'
```

**Do NOT rsync** these (red lines):

- `data/kol_scan.db` — production DB; only mutate via additive migrations (Step 4)
- `/root/.hermes/omonigraph-vault/lightrag_storage/` — KG state; not deploy concern
- `/etc/hosts` — has Vertex AI host pins; out of deploy scope
- Any `.py` under `kb/` with logic changes that haven't been merged to `origin/main`

---

## Step 3 — refresh the venv (MANDATORY — closes Finding 2)

This step is **the entire reason this runbook exists.** Skipping it means new
declared dependencies never reach the running process.

```bash
ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv/bin/pip install -r /root/OmniGraph-Vault/requirements.txt'
```

**Why plain `pip install` (no `--no-deps`):** A `--no-deps` install installs
only the listed packages. If a new package brings new transitive dependencies
that aren't already in the venv, `--no-deps` silently leaves the venv broken
(import-time `ModuleNotFoundError` at first use). Plain install resolves
transitives and is idempotent — already-installed packages are a no-op,
already-correct version constraints are skipped. The cost (resolution work) is
seconds. The benefit (catching transitive drift) is consequential.

**Verify after install:**

```bash
# 3a. confirm the imports the new code path needs are reachable
ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv/bin/python -c "import frontmatter, yaml, fastapi, lightrag; print(frontmatter.__version__, yaml.__version__, fastapi.__version__)"'

# 3b. spot-check any newly-declared package from this deploy
# (substitute the new package name from the requirements.txt diff)
ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv/bin/pip show <new-package> | head -3'
```

If any import fails: **STOP**, do not proceed to Step 4. Resolve the missing
dep before touching DB or systemd.

---

## Step 4 — DB migrations (only if pending)

```bash
# 4a. enumerate pending migrations
ssh aliyun-vitaclaw 'ls -1 /root/OmniGraph-Vault/kb/migrations/*.sql | sort'

# 4b. apply each in order (example — adapt to actual files)
ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv/bin/python /root/OmniGraph-Vault/kb/scripts/run_migrations.py'

# 4c. verify schema version
ssh aliyun-vitaclaw 'sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"'
```

Migrations must be **additive** (new columns / tables / indexes). Destructive
operations (DROP, type-narrowing ALTER) require a separate plan with the
operator.

---

## Step 5 — re-export SSG

```bash
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
  KB_BASE_PATH=/kb \
  KB_DEFAULT_LANG=zh-CN \
  KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images \
  /root/OmniGraph-Vault/venv/bin/python /root/OmniGraph-Vault/kb/scripts/export_ssg.py'

# verify article + entity + topic counts match expected
ssh aliyun-vitaclaw 'find /var/www/kb/articles -name "*.html" | wc -l; find /var/www/kb/entities -name "*.html" | wc -l; find /var/www/kb/topics -name "*.html" | wc -l'
```

**`KB_BASE_PATH=/kb` is mandatory** for Aliyun — Caddy serves SSG at `/kb/*`,
so all internal asset URLs need the `/kb` prefix. Forgetting it produces a
visually-broken site (404s on `/static/main.css`) — see Finding 4 in the
v2.2-7 YOLO report.

---

## Step 6 — restart kb-api

```bash
ssh aliyun-vitaclaw 'systemctl daemon-reload && systemctl restart kb-api && sleep 8 && systemctl is-active kb-api'
# expect: active

# verify ≥30s clean
ssh aliyun-vitaclaw 'journalctl -u kb-api --since "1 minute ago" --no-pager | tail -40'
# look for: clean startup, no Python tracebacks, no OOM, no restart loop
```

If kb-api fails to start: **STOP**, run `journalctl -u kb-api --since "5 minutes
ago"` and diagnose before retrying. Typical first-look causes:

- Missing dep → Step 3 was skipped or failed → re-run Step 3
- Python version mismatch (e.g. `from datetime import UTC` on Py3.10) → apply
  the compat shim and re-rsync (the v2.2-7 deploy hit this in `kb/wiki_lint.py`)
- DB schema drift → migration didn't run or rolled back → check Step 4

---

## Step 7 — smoke

```bash
# 7a. health
ssh aliyun-vitaclaw 'curl -fsS http://127.0.0.1:8766/health'

# 7b. articles list
ssh aliyun-vitaclaw 'curl -fsS http://127.0.0.1:8766/api/articles | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get(\"items\",[])))"'

# 7c. FTS search (free of LightRAG cold-load — should be < 100ms)
ssh aliyun-vitaclaw 'curl -fsS "http://127.0.0.1:8766/api/search?q=Hermes&mode=fts" | head -c 400; echo'

# 7d. public site (via Caddy)
curl -fsS -o /dev/null -w '%{http_code}\n' http://47.117.244.253/kb/
# expect: 200

# 7e. KG-mode + synthesize smokes — see kb/deploy/RUNBOOK-aliyun-kg-smoke.md
# (deferred when MemoryHigh is provisioned for LightRAG cold-load — at the time
# of writing the v2.2-7 YOLO deploy, KG smoke was BLOCKED on MemoryHigh=2G;
# β upgrade to 8GB RAM + MemoryHigh=4G is the unblock path.)
```

---

## Rollback

If Step 6 or Step 7 fails and the cause is not a fixable forward step:

```bash
# revert rsync'd files (Step 1c stashed the previous tree)
ssh aliyun-vitaclaw "rm -rf /root/OmniGraph-Vault/kb && mv /root/OmniGraph-Vault/kb.stash-pre-deploy-$TS /root/OmniGraph-Vault/kb"

# revert DB (only if Step 4 ran and the migration is the suspected cause)
ssh aliyun-vitaclaw "cp /root/OmniGraph-Vault/data/kol_scan.db.bak.$TS /root/OmniGraph-Vault/data/kol_scan.db"

# the venv stays as-is — extra packages from Step 3 are harmless idle weight,
# downgrading them risks breaking other consumers on the host

# restart
ssh aliyun-vitaclaw 'systemctl daemon-reload && systemctl restart kb-api && sleep 8 && systemctl is-active kb-api'
```

---

## Notes

- **Py3.10 compat shim**: Aliyun runs Python 3.10.12. Any new code using
  `from datetime import UTC` (Py3.11+) must use the shim:
  ```python
  from datetime import datetime, timezone
  UTC = timezone.utc
  ```
  Already applied to `kb/wiki_lint.py` (v2.2-7 Finding 1). Future modules
  must follow the same pattern until Aliyun upgrades to Py3.11+.

- **Sync `requirements.txt` even if your deploy "doesn't change deps"**: A
  teammate's PR may have added a dep since your last deploy. Step 3 is cheap
  insurance — always run it.

- **The systemd RUNBOOK at `kb/deploy/RUNBOOK-aliyun-systemd-refresh.md` has
  stale `/home/kb/...` paths** from its 2026-05-15 draft. The canonical
  location is `/root/OmniGraph-Vault` (memory `aliyun_vitaclaw_ssh.md`). Fix
  is out of scope for this runbook; flag for a future quick.

- **Memory bounds**: as of 2026-05-20, `MemoryHigh=2G` / `MemoryMax=2.8G` is
  insufficient for LightRAG cold-load (peak ~2.3G RES, see v2.2-7 YOLO report
  Finding 3). β remediation (8GB RAM + 4G/6G bounds) is in flight; until that
  lands, KG-mode and synthesize smokes will wedge. Use FTS-mode for any
  pre-β verification.

- **Production-mutation principles** (from memory `aliyun_vitaclaw_ssh.md`):
  always `daemon-reload` before `restart`; watch `journalctl -u kb-api -f`
  for ≥1 minute after restart; if `MemoryMax` is in effect, OOM kills
  auto-restart inside the `StartLimitBurst` window before systemd gives up
  — verify by checking `journalctl` for `Failed with result 'oom-kill'`.
