# RUNBOOK — lightrag_storage Sync (kb-v2.2-1 F12)

Hermes-to-Aliyun two-hop rsync of `lightrag_storage/`. Atomic swap with backup,
proactive OOM probe, automatic rollback, and weekly growth prediction.

---

## §1 Weekly Sync Checklist

Run manually every **Sunday ~22:00 ADT** before any Wave 2 KB content updates.

### Pre-flight

1. Confirm Hermes agent and aliyun-vitaclaw SSH connectivity:

   ```bash
   ssh aliyun-vitaclaw "systemctl is-active kb-api.service"
   ```

   Expected: `active`. If not, investigate before proceeding.

2. Check current Aliyun memory usage:

   ```bash
   python kb/scripts/check_aliyun_kg_memory.py
   ```

   Expected: `[OK] aliyun-vitaclaw memory: XX.X% (NNN MB / 2441 MB)`. If already
   >85%, consult §4 before syncing.

3. Check local relay disk space (`>5 GB free`):

   ```powershell
   Get-PSDrive C | Select-Object Used, Free
   ```

### Execute sync

```bash
python kb/scripts/sync_lightrag_storage.py --source-host <hermes-alias> --force
```

Replace `<hermes-alias>` with the SSH config alias for the Hermes host
(see `~/.ssh/config`). Do **not** paste the literal hostname — the repo is public.

Add `--dry-run` first if this is your first run after a multi-week gap:

```bash
python kb/scripts/sync_lightrag_storage.py --source-host <hermes-alias> --dry-run
```

### Expected output sequence

```
{"event": "start", ...}
{"event": "rsync_done", ...}
{"event": "service_stopped", ...}
{"event": "swap_done", "backup": "/root/.hermes/.../lightrag_storage.OLD-YYYYMMDDTHHMMSSZ"}
{"event": "service_started", ...}
{"event": "smoke_pass", ...}
{"event": "complete", "wallclock_s": NNN, "vdb_bytes": NNNN, "memory_pct": 0.NNN}
```

Typical wall-clock: **8-15 min** for a 500 MB - 2 GB rsync delta.

### Post-sync verification

```bash
python kb/scripts/check_aliyun_kg_memory.py --json | python -m json.tool
```

Visit `https://<aliyun-host>/kb/health` — expect HTTP 200.

---

## §2 Recovery Procedures

### 2a — Manual rollback (backup preserved)

If you need to rollback after the script exits successfully but you observe
post-sync issues, use the `backup_path_kept` from the state file:

```bash
BACKUP=$(ssh aliyun-vitaclaw "cat /etc/lightrag-sync-state.json" | python -c "import sys,json; print(json.load(sys.stdin)['backup_path_kept'])")
ssh aliyun-vitaclaw "systemctl stop kb-api.service && rm -rf /root/.hermes/omonigraph-vault/lightrag_storage && mv $BACKUP /root/.hermes/omonigraph-vault/lightrag_storage && systemctl start kb-api.service"
```

### 2b — Re-run after idempotency skip

If the sync ran within the last 24 h and you need to run again:

```bash
python kb/scripts/sync_lightrag_storage.py --source-host <hermes-alias> --force
```

### 2c — Partial rsync failure

If rsync exits with a non-zero code, the script exits before any swap occurs —
no rollback needed. Fix the relay connectivity issue and re-run.

### 2d — Script killed mid-swap (worst case)

If the script is killed during the `atomic_swap` SSH command:

1. SSH into Aliyun and check directory state:

   ```bash
   ls -la /root/.hermes/omonigraph-vault/ | grep -E "lightrag_storage"
   ```

2. If both `lightrag_storage` and `lightrag_storage_NEW` exist: swap interrupted
   before first `mv` completed — re-run the swap manually.
3. If `lightrag_storage.OLD-TS` and `lightrag_storage_NEW` exist but `lightrag_storage`
   is absent: first `mv` completed; second `mv` interrupted. Restore:

   ```bash
   mv /root/.hermes/omonigraph-vault/lightrag_storage_NEW /root/.hermes/omonigraph-vault/lightrag_storage
   systemctl start kb-api.service
   ```

---

## §3 Escalation Policy

| Symptom | Immediate action | Escalate if... |
|---------|-----------------|----------------|
| OOM probe `status='exceeded'` — script auto-rolled back | Check `check_aliyun_kg_memory.py`; if >90%, do NOT re-sync | Memory stays >85% after 30 min. See §4 + §6 |
| Smoke test failure — script auto-rolled back | Check `curl -sf https://<host>/kb/health` | Still failing after rollback restarts service |
| rsync fails repeatedly (CalledProcessError) | Check SSH tunnel + Hermes disk space | Connectivity issue persists >1 h |
| State file JSON corrupt | `ssh aliyun-vitaclaw "rm /etc/lightrag-sync-state.json"` then re-run with `--force` | — |
| `inconclusive` probe (SSH flap during probe) | Re-run `check_aliyun_kg_memory.py` manually; if OK, accept as-is | Repeated SSH failures suggest host resource pressure |

---

## §4 When to Raise MemoryMax

**Current config:** `MemoryMax=2560M` (2.5 GB) in `/etc/systemd/system/kb-api.service`
**Empirical high-water mark (2026-05-18):** 1.3 GB vdb → OOM-kill at graph load
**Safe sync ceiling (empirical):** ~1.5 GB vdb with 2.5 GB MemoryMax

### Trigger: raise MemoryMax when

- `check_aliyun_kg_memory.py` consistently returns >70% post-sync AND
- growth prediction reports ceiling hit within 90 days (see §7)

### Procedure to raise MemoryMax

```bash
ssh aliyun-vitaclaw "systemctl show kb-api.service -p MemoryMax"
# Then edit unit file:
ssh aliyun-vitaclaw "sed -i 's/MemoryMax=.*/MemoryMax=4096M/' /etc/systemd/system/kb-api.service && systemctl daemon-reload && systemctl restart kb-api.service"
```

Verify with `check_aliyun_kg_memory.py` after restart.

**Note:** Aliyun ECS t6/c6 instances may have a hard DRAM ceiling. If the server
has only 2 GB physical RAM, MemoryMax cannot exceed physical RAM minus OS overhead
(~300 MB). In that case, the only options are instance resize or pruning the vdb.

---

## §5 Cross-References

| Resource | Path/URL |
|----------|----------|
| Sync script | `kb/scripts/sync_lightrag_storage.py` |
| Memory probe | `kb/scripts/check_aliyun_kg_memory.py` |
| State file (Aliyun) | `/etc/lightrag-sync-state.json` |
| Log events (Aliyun) | `journalctl -u kb-api.service -n 100` |
| F12 PLAN | `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-1-lightrag-storage-sync-PLAN.md` |
| F12 unit tests | `tests/unit/kb/test_sync_lightrag_storage.py` |
| F12 integration tests | `tests/integration/kb/test_sync_state_lifecycle.py` |
| SSH config alias | `~/.ssh/config` → `aliyun-vitaclaw` block |
| Hermes SSH | `~/.claude/projects/.../memory/hermes_ssh.md` |
| Aliyun SSH | `~/.claude/projects/.../memory/aliyun_vitaclaw_ssh.md` |

---

## §6 OOM Recovery Playbook

### Background — 2026-05-18 empirical evidence

On 2026-05-18, a manual test sync of **1.5 GB lightrag_storage** (22,412 nodes /
1.3 GB vdb) to Aliyun with `MemoryMax=2560M` resulted in **OOM-kill during graph
load**. The service crashed immediately on startup after the swap.

The backup was preserved at:
`/root/.hermes/omonigraph-vault/lightrag_storage.OLD-20260518-065245`

Manual rollback was performed by:

```bash
ssh aliyun-vitaclaw "systemctl stop kb-api.service"
ssh aliyun-vitaclaw "rm -rf /root/.hermes/omonigraph-vault/lightrag_storage && mv /root/.hermes/omonigraph-vault/lightrag_storage.OLD-20260518-065245 /root/.hermes/omonigraph-vault/lightrag_storage"
ssh aliyun-vitaclaw "systemctl start kb-api.service"
```

Service recovered successfully after restoring the 2026-05-08 snapshot.

### Automated OOM protection (post-2026-05-18)

The `sync_lightrag_storage.py` script now runs a **proactive OOM probe**
(`monitor_post_restart_memory`) after every restart:

- Samples `MemoryCurrent` / `MemoryMax` every 30 s for up to 5 minutes
- If 2+ consecutive samples exceed **85% of MemoryMax**, triggers automatic rollback
- Log event: `memory_ceiling_rollback`

### Manual OOM diagnosis steps

1. Check if kb-api is running:

   ```bash
   ssh aliyun-vitaclaw "systemctl status kb-api.service"
   ```

2. Check system journal for OOM kills:

   ```bash
   ssh aliyun-vitaclaw "journalctl -k | grep -i 'oom\|killed process'"
   ```

3. Confirm vdb size:

   ```bash
   ssh aliyun-vitaclaw "du -sh /root/.hermes/omonigraph-vault/lightrag_storage/"
   ```

4. If OOM confirmed, check backup path from state file (§2a) and rollback.

5. After rollback, check §4 — evaluate whether MemoryMax needs raising before
   the next sync attempt.

---

## §7 vdb Size Growth Prediction

The `sync_lightrag_storage.py` script computes a **linear growth projection** after
each successful sync (requires 4+ history entries in the state file).

### Reading the prediction

Check the state file after a sync:

```bash
ssh aliyun-vitaclaw "cat /etc/lightrag-sync-state.json" | python -m json.tool | grep -A10 growth_prediction
```

Example output:

```json
"growth_prediction": {
  "samples_used": 8,
  "projected_ceiling_hit_date": "2026-09-14",
  "days_until_ceiling": 119,
  "ceiling_hit_warn": false
}
```

### Alert levels

| Level | Condition | Action |
|-------|-----------|--------|
| INFO | >90 days to ceiling | Monitor; no action needed |
| WARN | 31-90 days to ceiling | Plan MemoryMax upgrade or vdb pruning |
| CRITICAL | <=30 days to ceiling | **Immediate action required** — raise MemoryMax or prune vdb before next sync |

A `growth_prediction_warn` or `growth_prediction_critical` JSON log line is emitted
on each sync run that breaches the respective threshold.

### Projection caveats

- Uses linear regression on `vdb_total_bytes` vs. `last_success_ts` from the rolling
  20-entry state file history.
- Requires ≥4 history samples (approx. 4 weekly syncs) to generate a projection.
- Linear model underestimates growth during onboarding bursts and overestimates
  during quiet periods — treat as an early-warning signal, not a precise date.
- `ceiling` is `MemoryMax` as reported by `systemctl show`; if you raise MemoryMax,
  the projection resets to the new ceiling on the next sync.
