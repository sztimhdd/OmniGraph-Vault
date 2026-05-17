---
phase: kb-v2.2-1-lightrag-storage-sync
requirements: [SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05, SYNC-06, SYNC-07]
priority: P0
skills_required: [python-patterns, writing-tests, search-first]
wave: 1
depends_on: []
estimated_loc: 200-350
estimated_time: 1-1.5d
authored_by: orchestrator from kb-v2.2 INPUT.md + 2026-05-17 evening 7-decision lock-in + tonight's manual Hermes-Agent atomic-swap operational shape
---

# Phase kb-v2.2-1 — Hermes → Aliyun lightrag_storage Sync Mechanism

## Goal

Ship a **user-triggered weekly** sync script + standalone memory probe + runbook
that periodically refreshes Aliyun production's `/root/.hermes/omonigraph-vault/lightrag_storage/`
from Hermes's authoritative `~/.hermes/omonigraph-vault/lightrag_storage/`, with
atomic swap, automatic rollback on smoke failure, and cgroup memory budget
monitoring.

**This phase does NOT cover tonight's one-shot manual catch-up sync** (user is
running that via Hermes-Agent prompt as we plan). This phase formalizes that
operational shape into reusable infrastructure so future syncs don't require
re-deriving the SSH/rsync dance.

## Why this is P0 (Wave 1 prereq)

Aliyun's `lightrag_storage` is a **2026-05-08 stale snapshot**; Hermes current
data is ~3.9× larger (4603 vs 1189 image URLs; 172 vs 44 articles with images;
1789 vs 460 sub-doc descriptions). Until F12 ships:

- **F8' (kb-v2.2-3)** KG search results bounded by ~25% Hermes content
- **FU-1 (kb-v2.2-4)** image-rich answers limited to old chunks
- Both Wave 2 phases blocked on stale data quality

A weekly cadence keeps Aliyun within ≤7d of Hermes truth, which is acceptable
for a read-mostly knowledge surface where ingest happens daily on Hermes.

## Pre-locked decisions (NOT to re-litigate)

These were locked in the 2026-05-17 evening user-orchestrator session (see
`.planning/phases/kb-v2.2-translation-and-kg-search/INPUT.md` § "Architectural
choices"). Bake into plan body, do not re-debate during execute:

| # | Decision | Locked value |
|---|---|---|
| D1 | Sync direction | Windows dev 中继(双跳):Hermes → Windows dev → Aliyun |
| D2 | Frequency | Weekly,manual user trigger (NOT cron — Windows dev not always on) |
| D3 | Failure alerting | Log only;user reads log periodically |
| D4 | kb-api during sync | Stop → rsync → start (seconds-minutes downtime acceptable) |
| D5 | Memory monitoring | Log MemoryCurrent/MemoryMax %;>90% prints WARN; no auto-raise |
| D6 | State persistence | `/var/log/lightrag-sync.log` append-only + `/etc/lightrag-sync-state.json` on Aliyun |
| D7 | Testing | All `subprocess.run` mocked;NO real cross-border integration in CI |

If any pre-locked decision proves genuinely unworkable during execute, STOP +
escalate to orchestrator with concrete alternative — do NOT silently override.

## Files affected

| File | Action |
|---|---|
| `kb/scripts/sync_lightrag_storage.py` | **NEW** — main sync orchestrator with atomic swap + rollback + state file + memory monitoring |
| `kb/scripts/check_aliyun_kg_memory.py` | **NEW** — standalone memory budget probe (independent of sync) |
| `tests/unit/kb/test_sync_lightrag_storage.py` | **NEW** — 9 unit cases mocking subprocess (rsync + ssh + systemctl) |
| `tests/integration/kb/test_sync_state_lifecycle.py` | **NEW** — 2 integration cases on local fixture dirs (no real network) |
| `kb/docs/RUNBOOK-lightrag-storage-sync.md` | **NEW** — user-facing weekly procedure + recovery + escalation |
| `.planning/STATE-KB-v2.md` | **UPDATE** — last_activity row for kb-v2.2-1 only (no other rows touched) |

**Out of scope for this phase** (do NOT touch):
- `kb/{services,data,api,templates}` — sync is pure ops; nothing user-facing changes
- `kb/deploy/kb-api.service` — locked decision D4 just calls `systemctl stop/start` via SSH; no unit-file mutation
- Aliyun production directly — phase output is script + RUNBOOK; user runs it
- Hermes ingest cron pause/resume — locked decision: per-file LightRAG atomic write makes drift acceptable
- F11 Path B / DeepSeek-only long_form / any LightRAG bypass

## Read first (mandatory before authoring code)

1. `.planning/phases/kb-v2.2-translation-and-kg-search/INPUT.md` — full v2.2 scope
2. `.planning/PROJECT-KB-v2.md` § "KB v2.2 (in progress 2026-05-17+)" — feature scope
3. `.planning/phases/kb-v2.1-stabilization/DEFERRED.md` — F11 CUT-FINAL (no bypass)
4. `.planning/phases/kb-v2.1-stabilization/kb-v2.1-1-kg-mode-hardening-PLAN.md` — phase format reference + `KG_MODE_AVAILABLE` flag pattern (memory probe emits similar warning)
5. `kb/scripts/` directory listing — match existing 1-shot script style
6. Memory entries (consult to verify SSH/path facts before authoring; do NOT inline secrets):
   - `aliyun_vitaclaw_ssh.md` — SSH alias `aliyun-vitaclaw`,key path,Aliyun runtime paths
   - `hermes_ssh.md` — Hermes SSH endpoint (host/port/user MUST stay out of committed files; repo is public)
   - `aliyun_oauth_pin.md` — `/etc/hosts` pin requirement (RUNBOOK § Cross-ref must mention)
   - `feedback_lightrag_is_core_asset_no_bypass.md` — anti-bypass principle baked into plan body
7. Tonight's Hermes-Agent manual sync prompt operational shape:
   - rsync to `_NEW` staging dir
   - stop kb-api
   - backup current `lightrag_storage` to `lightrag_storage.OLD-<TS>`
   - mv `_NEW` → live name
   - start kb-api
   - smoke test
   - if smoke fails: restore from `.OLD-<TS>`

## Action

### Task 1 — Author `kb/scripts/sync_lightrag_storage.py`

Skill invocation (literal, must appear in SUMMARY.md as grep-verifiable substring):

`Skill(skill="python-patterns", args="Author kb/scripts/sync_lightrag_storage.py with frozen Config + State dataclasses, type-annotated functions for atomic_swap / rsync_to_staging / pause_kb_api / smoke_test / update_state_file / rollback / check_memory_budget. Idiomatic subprocess.run usage with capture_output=True + check=True semantics. Structured JSON-line logging via logging module to /var/log/lightrag-sync.log. Idempotent: re-running on already-synced state where last_success_ts is within 24h is a no-op (prints 'recent sync within 24h, skipping' and exits 0). All SSH operations route through ssh_run() helper that takes (host_alias, command) — host_alias='aliyun-vitaclaw' or '<hermes-alias-from-user-ssh-config>', NEVER literal hostnames in source.")`

#### CLI surface

```
python kb/scripts/sync_lightrag_storage.py \
  --source-host <hermes-alias> \
  --source-path /home/<user>/.hermes/omonigraph-vault/lightrag_storage/ \
  --target-host aliyun-vitaclaw \
  --target-path /root/.hermes/omonigraph-vault/lightrag_storage/ \
  --staging-relay-dir ./.sync-relay/ \
  --state-file /etc/lightrag-sync-state.json \
  --memory-warn-threshold 0.9 \
  [--force]   # bypass 24h idempotency guard
  [--dry-run] # rsync --dry-run, no kb-api stop, no swap
```

Defaults match production for unflagged invocation: `python kb/scripts/sync_lightrag_storage.py` runs the live sync without arguments.

#### Required functions

| Function | Signature | Behavior |
|---|---|---|
| `ssh_run(host_alias, cmd, *, check=True)` | `(str, str) -> CompletedProcess` | Wraps `subprocess.run(["ssh", host_alias, cmd], capture_output=True, check=check)` |
| `pause_target_kb_api(target_host)` | `(str) -> None` | `ssh_run(target, "systemctl stop kb-api.service")` |
| `start_target_kb_api(target_host)` | `(str) -> None` | `ssh_run(target, "systemctl start kb-api.service")` |
| `rsync_to_staging(source_host, source_path, relay_dir, target_host, target_staging_path)` | full signature in docstring | Two-hop: rsync `source_host:source_path` → `relay_dir/`, then rsync `relay_dir/` → `target_host:target_staging_path`. Excludes: `--exclude='*.tmp' --exclude='.bak*' --exclude='*.lock'` |
| `atomic_swap(target_host, live_path, staging_path, backup_ts)` | `(str, str, str, str) -> str` | `ssh_run(target, f"mv {live_path} {live_path}.OLD-{backup_ts} && mv {staging_path} {live_path}")`. Returns `f"{live_path}.OLD-{backup_ts}"` |
| `smoke_test(target_host, public_url)` | `(str, str) -> bool` | curl `${public_url}/api/search?q=test&mode=kg` + curl `/api/synthesize` health probe;return True if both 2xx |
| `check_memory_budget(target_host)` | `(str) -> MemoryReport` | `ssh_run(target, "systemctl show -p MemoryCurrent -p MemoryMax kb-api.service")`,parse,return `MemoryReport(current_bytes, max_bytes, pct)` |
| `update_state_file(target_host, state_file_path, state)` | `(str, str, SyncState) -> None` | Write JSON via `ssh_run(target, f"cat > {state_file} <<EOF\n{json}\nEOF")` |
| `rollback(target_host, live_path, backup_path)` | `(str, str, str) -> None` | `ssh_run(target, f"rm -rf {live_path} && mv {backup_path} {live_path}")` then start kb-api |

#### Frozen dataclasses

```python
@dataclass(frozen=True)
class SyncConfig:
    source_host: str
    source_path: str
    target_host: str
    target_path: str
    staging_relay_dir: str
    state_file_path: str
    memory_warn_threshold: float
    public_smoke_url: str
    force: bool
    dry_run: bool

@dataclass(frozen=True)
class SyncState:
    last_success_ts: str        # ISO 8601
    vdb_total_bytes: int
    sync_wallclock_s: float
    memory_pct_at_sync: float
    backup_path_kept: str       # last .OLD-<TS> directory not yet pruned

@dataclass(frozen=True)
class MemoryReport:
    current_bytes: int
    max_bytes: int
    pct: float                  # current / max
```

#### Top-level orchestration sequence

```
1. Parse args → SyncConfig
2. Read existing state file via ssh_run; if last_success_ts within 24h and not --force: log + exit 0
3. Generate timestamp (TS = UTC ISO compact, e.g. 20260518T120000Z)
4. rsync_to_staging(source → relay → target_staging)  [if --dry-run, --dry-run flag added to rsync]
5. If --dry-run: log diff size + exit 0
6. pause_target_kb_api(target)
7. backup_path = atomic_swap(target, live_path, staging_path, TS)
8. start_target_kb_api(target)
9. memory_report = check_memory_budget(target)
10. If memory_report.pct > config.memory_warn_threshold: log WARN
11. If smoke_test(target, public_url) is False:
       rollback(target, live_path, backup_path)
       update_state_file with last_failure metadata
       raise SystemExit(1)
12. update_state_file(state with success metadata)
13. log JSON summary line
14. exit 0
```

#### Addendum (2026-05-18 OOM evidence): proactive post-restart memory probe

**Empirical basis** — 2026-05-18 凌晨 Hermes manual sync ~10 min completed
1.5GB transfer, atomic swap success, kb-api start → **OOM-kill on graph load**
(22412 nodes / 31566 edges / 1.3GB vdb on 2.5G `MemoryMax` cap + Python overhead
exceeded ceiling). Reactive rollback wasted ~30s downtime + 1 systemd
restart-loop attempt before kernel OOM-killer fired. Rolled back to 5524-node /
348MB previous storage, stable. Evidence: `journalctl -u kb-api.service` showed
`oom-kill` exit code seconds after `Loaded graph` log line.

This addendum inserts a **proactive 5-min × 30s sampling step** between
`start_target_kb_api()` and `smoke_test()` to catch OOM trajectory and rollback
BEFORE the kernel kills the process — saves the downtime + restart-loop noise.

**New function (extends Required functions table above):**

| Function | Signature | Behavior |
|---|---|---|
| `monitor_post_restart_memory(target_host, max_pct=0.85, sample_interval_s=30, sample_count=10)` | `(str, float, int, int) -> MemoryProbeResult` | Sample `MemoryCurrent / MemoryMax` every 30s × 5 min post-restart. If pct > `max_pct` sustained for 2+ consecutive samples, return `MemoryProbeResult(status='exceeded', samples=[...])` so the caller can rollback proactively rather than waiting for kernel OOM-kill. Default thresholds: `max_pct=0.85`, `sample_interval_s=30`, `sample_count=10` (5 minutes total). |

**New frozen dataclass (extends frozen dataclasses block above):**

```python
@dataclass(frozen=True)
class MemoryProbeResult:
    status: str                       # 'ok' | 'exceeded' | 'inconclusive'
    samples: tuple[MemoryReport, ...] # all samples taken, oldest first
    consecutive_breach_count: int     # max run of samples > max_pct
    triggered_threshold: float        # max_pct used at probe time
```

**New exception class:**

```python
class SyncFailedMemoryCeiling(SystemExit):
    """Raised when monitor_post_restart_memory() returns status='exceeded'
    so that orchestrator triggers proactive rollback before kernel OOM."""
```

**Revised orchestration sequence** (steps 8a + 8b inserted between existing
steps 8 and 11; existing steps 9, 10, 11, 12, 13, 14 remain unchanged):

```
8.  start_target_kb_api(target)
8a. probe_result = monitor_post_restart_memory(target, max_pct=0.85)   # NEW
8b. If probe_result.status == 'exceeded':                               # NEW
        log JSON event=memory_ceiling_exceeded with samples
        rollback(target, live_path, backup_path)
        update_state_file with last_failure metadata + probe samples
        raise SyncFailedMemoryCeiling(1)
9.  memory_report = check_memory_budget(target)   # one final post-stable reading
10. If memory_report.pct > config.memory_warn_threshold: log WARN
11. If smoke_test(target, public_url) is False: ...
```

**Skill invocation extension** (existing `Skill(skill="python-patterns"` call
at top of Task 1 stays as-is; this addendum's args appended on execute):

`Skill(skill="python-patterns", args="...also implement monitor_post_restart_memory() with frozen MemoryProbeResult dataclass + SyncFailedMemoryCeiling exception. Sampling loop uses time.sleep(sample_interval_s) between ssh_run() calls; consecutive_breach_count tracking via running counter that resets on any sample <= max_pct. Sustained 2+ consecutive breaches triggers status='exceeded'. If sample_count completes with no sustained breach, status='ok'. If <2 samples obtained (e.g. ssh failures), status='inconclusive' — caller treats as ok-but-warn (not auto-rollback, since no evidence either way).")`

#### Logging

- Log file: `/var/log/lightrag-sync.log` (append-only) — writes via `ssh_run(target, "tee -a /var/log/lightrag-sync.log")` since log lives on Aliyun
- Each line: JSON object with `ts`, `event` (one of `start|rsync_done|swap_done|smoke_pass|smoke_fail|rollback_done|memory_warn|complete|error`), `phase`, `details`
- Stdout mirror for interactive runs (so user sees progress without tailing remote log)

### Task 2 — Tests

Skill invocation:

`Skill(skill="writing-tests", args="Testing Trophy: unit > integration > E2E. Mock subprocess.run for ssh + rsync in unit tests. Cover happy path + rollback path + state-file lifecycle + memory threshold + idempotency guard + dry-run. Use monkeypatch for environment vars. NO real network in CI — all subprocess interactions mocked. Integration tests use local-cp simulation: monkeypatch ssh_run() to perform local cp/mv on tmp_path fixtures.")`

#### `tests/unit/kb/test_sync_lightrag_storage.py` — 9 cases

| Test | Validates |
|---|---|
| `test_atomic_swap_happy_path` | mv chain executed in correct order; backup path returned |
| `test_atomic_swap_rollback_on_smoke_fail` | smoke_test returns False → rollback() called → kb-api restarted |
| `test_state_file_roundtrip` | SyncState → JSON → parse → equal SyncState (frozen-dataclass equality) |
| `test_memory_threshold_warn_triggers` | MemoryReport.pct=0.95 with threshold=0.9 → WARN log emitted |
| `test_memory_threshold_warn_silent_below` | MemoryReport.pct=0.5 with threshold=0.9 → no WARN |
| `test_rsync_excludes_correct` | rsync command line includes all 3 `--exclude=` flags (`*.tmp`, `.bak*`, `*.lock`) |
| `test_rsync_partial_failure_returns_error` | subprocess.CalledProcessError → SystemExit(1) before any swap attempted |
| `test_state_file_first_run_no_prior_state` | state_file_path doesn't exist → run proceeds without idempotency-skip |
| `test_idempotency_guard_skips_within_24h` | last_success_ts 1h ago + no --force → exit 0 with "skipping" log; subprocess.run for rsync NEVER called |

All 9 tests mock `subprocess.run` via `unittest.mock.patch` or `monkeypatch.setattr`.

#### `tests/integration/kb/test_sync_state_lifecycle.py` — 2 cases

Integration via local-cp simulation: `monkeypatch.setattr(sync_lightrag_storage, "ssh_run", local_cp_ssh_run)` where `local_cp_ssh_run` translates ssh+mv/rsync calls into local `shutil.copytree` / `shutil.move` against `tmp_path` fixtures.

| Test | Validates |
|---|---|
| `test_full_sync_cycle_writes_state_file` | Full happy path: pre-state file (or absent) → run sync → state file post-state has updated `last_success_ts` + sane `vdb_total_bytes` + sane `sync_wallclock_s` |
| `test_smoke_failure_triggers_rollback_path` | monkeypatch smoke_test → False → state file post-state shows failure metadata + live dir restored byte-for-byte from .OLD backup |

**Acceptance for tests:** all 11 cases PASS in `pytest tests/unit/kb/test_sync_lightrag_storage.py tests/integration/kb/test_sync_state_lifecycle.py -v`.

### Task 3 — RUNBOOK + memory probe + STATE update + commit

Skill invocation:

`Skill(skill="search-first", args="Verify rsync flags (--inplace + --partial + --exclude semantics in rsync 3.x) before authoring script. Verify systemd 'mv on running service file' atomicity (kb-api uses mmap on vdb, must stop service first per locked decision D4). Cross-check POSIX mv atomicity guarantees on same filesystem. Confirm 'systemctl show -p MemoryCurrent -p MemoryMax' output format for parsing.")`

#### Author `kb/scripts/check_aliyun_kg_memory.py` (standalone)

Reuses `check_memory_budget()` from sync script via `from kb.scripts.sync_lightrag_storage import check_memory_budget`.

```
python kb/scripts/check_aliyun_kg_memory.py --target aliyun-vitaclaw [--json]
```

Output (default human-readable):
```
kb-api.service memory:
  MemoryCurrent: 1.42 GiB
  MemoryMax:     2.50 GiB
  Usage:         57.0%
  Status:        OK (below 90% warn threshold)
```

`--json` mode: `{"current_bytes": 1524713472, "max_bytes": 2684354560, "pct": 0.5680, "status": "ok"}`.

Exit code: 0 if pct < 0.9; 1 if ≥ 0.9 (so the user can `cron`-wrap independently if desired).

#### Author `kb/docs/RUNBOOK-lightrag-storage-sync.md` (5 mandatory sections)

| Section | Content |
|---|---|
| **§1 Weekly checklist** | 6-step procedure: (a) `git pull` on Windows dev to ensure latest sync script; (b) `python kb/scripts/check_aliyun_kg_memory.py --target aliyun-vitaclaw` pre-flight; (c) `python kb/scripts/sync_lightrag_storage.py` (or with `--dry-run` first); (d) tail log: `ssh aliyun-vitaclaw 'tail -f /var/log/lightrag-sync.log'`; (e) post-sync smoke: open https://101.133.154.49/kb/ in browser, run a KG-mode search; (f) record success in personal weekly log |
| **§2 Recovery (smoke fail)** | Script auto-rollback covers most cases. Manual recovery if script crashed mid-swap: `ssh aliyun-vitaclaw 'ls /root/.hermes/omonigraph-vault/lightrag_storage*'` to find `.OLD-<TS>` backup → manual rollback steps with explicit mv commands |
| **§3 Escalation (memory ceiling)** | If MemoryCurrent/MemoryMax > 95% post-sync: vdb is hitting cgroup ceiling. Don't auto-raise — first decide if this is steady growth or a one-time spike (check trend in `/var/log/lightrag-sync.log` JSON `memory_pct_at_sync` field across 3+ syncs) |
| **§4 When to raise MemoryMax** | If trend is steady growth: edit `/etc/systemd/system/kb-api.service` `MemoryMax=` directive (current 2.5G → next step 3.5G), `systemctl daemon-reload`, `systemctl restart kb-api.service`, verify with check_aliyun_kg_memory.py. Aliyun ECS has 3.4Gi total RAM (per `aliyun_vitaclaw_ssh.md`) — ceiling on raises is ~3G to leave headroom for vitaclaw-site Node and OS |
| **§5 Cross-references** | (a) `aliyun_oauth_pin.md` memory entry: `/etc/hosts` pin for `oauth2.googleapis.com` + `us-central1-aiplatform.googleapis.com` is REQUIRED for kb-api KG mode post-sync; if missing, KG queries silently return empty markdown — never delete hosts entries during sync. (b) `aliyun_vitaclaw_ssh.md` for SSH alias setup. (c) `feedback_lightrag_is_core_asset_no_bypass.md` for why F12 sync (not F11 bypass). (d) Phase plan kb-v2.2-3 (F8') for downstream KG search consumer of synced data |

#### Addendum (2026-05-18 OOM evidence): RUNBOOK §6 — OOM Recovery Playbook

Append a new `## §6 OOM Recovery Playbook` section to the RUNBOOK after §5
Cross-references. Anchored to 2026-05-18 现场 evidence.

````markdown
## §6 OOM Recovery Playbook

**Empirical anchor:** 2026-05-18 manual sync 1.5GB Hermes → 2.5G Aliyun cap →
kb-api OOM-kill on graph load (22412 nodes / 31566 edges / 1.3GB vdb +
Python overhead exceeded `MemoryMax=2.5G`). Rollback path verified live:
`lightrag_storage.OLD-20260518-065245` restored cleanly,kb-api stable on
prior 5524-node / 348MB storage.

**Manual rollback (when script auto-rollback didn't fire / crashed mid-swap):**

```bash
ssh aliyun-vitaclaw 'systemctl stop kb-api.service'         # force; may already be in restart-loop
ssh aliyun-vitaclaw 'cd /root/.hermes/omonigraph-vault \
  && mv lightrag_storage lightrag_storage.FAILED-$(date -u +%Y%m%dT%H%M%SZ) \
  && mv lightrag_storage.OLD-<TS> lightrag_storage'         # use latest .OLD-<TS> from `ls`
ssh aliyun-vitaclaw 'systemctl start kb-api.service && systemctl status kb-api.service --no-pager'
ssh aliyun-vitaclaw 'journalctl -u kb-api.service --since "30 seconds ago" --no-pager | grep -E "Loaded graph|oom-kill"'
```

Preserve the `.FAILED-<TS>` directory for postmortem analysis (do NOT
auto-prune). Tag in state file `last_failure.failed_storage_path`.

**Escalation triggers:**

| Signal | Severity | Action |
|---|---|---|
| 1 OOM within `StartLimitBurst=5/IntervalSec=60` window self-healed by systemd | INFO | Log only; alert Hai async |
| Sync auto-rollback fired (proactive probe caught it pre-OOM) | WARN | Hai inspects probe samples + memory trend; decide whether to defer next sync |
| ≥3 OOM-kills in 1 hour | **CRITICAL** | **STOP sync cadence** + escalate Aliyun ECS upgrade (4GB → 8GB ¥100/mo) — track as v2.3 candidate |
| Manual rollback required (script crashed mid-swap) | **CRITICAL** | File postmortem; investigate before next sync attempt |

**ECS upgrade trigger** (v2.3 candidate, NOT in F12 scope):

- 4GB → 8GB ¥100/mo incremental
- F12 ships ONLY the documented trigger condition + RUNBOOK note;
  actual upgrade is operator decision based on sustained ≥3 OOM/hr or
  growth-prediction §7 90-day warning

**Hard don'ts:**

- ❌ Do **NOT** retry sync immediately after OOM — same data → same OOM, wastes cross-border bandwidth
- ❌ Do **NOT** raise `MemoryMax` above `(total_RAM - 0.7GB)` — kernel system-OOM-killer will pick random processes (potentially `vitaclaw-site` Node, ssh, systemd-journald)
- ❌ Do **NOT** delete `.OLD-<TS>` or `.FAILED-<TS>` backups during recovery — they're the only verified-stable snapshot until the next sync succeeds
````

#### Addendum (2026-05-18 OOM evidence): RUNBOOK §7 — vdb Size Growth Prediction

Append a new `## §7 vdb Size Growth Prediction` section to the RUNBOOK after
§6. Converts "passive ceiling-hit" into "90-day advance warning".

````markdown
## §7 vdb Size Growth Prediction

State file records `(sync_ts, vdb_total_bytes, memory_current_post_load,
memory_max_at_time)` per sync. After 4+ syncs, linear extrapolation projects
when vdb growth will hit current `MemoryMax`:

```python
def predict_ceiling_hit(state_history: list[SyncState],
                        current_max_bytes: int) -> Optional[date]:
    """Extrapolate linear vdb growth, return projected date hitting current cap.

    Returns None if <4 history points (insufficient data) or growth rate <= 0
    (storage shrinking / steady — no concern). Returns date if projected hit
    within next 365 days.

    Linear fit: bytes(t) = m * t + b, where t = days since first sample.
    Solve bytes(t_hit) = current_max_bytes for t_hit, return calendar date.
    """
```

**Warn threshold:** projected ceiling-hit within 90 days → log WARN line +
set `state.growth_prediction.ceiling_hit_warn = True`. Hai's weekly log scan
sees the flag → triggers Aliyun ECS upgrade decision **before** the wall is hit.

**State file extension** (additive non-breaking — existing fields unchanged):

```json
{
  "growth_prediction": {
    "samples_used": 6,
    "linear_growth_bytes_per_day": 18345670,
    "projected_ceiling_hit_date": "2026-08-12",
    "days_until_ceiling": 87,
    "ceiling_hit_warn": true
  }
}
```

**Behavior matrix:**

| State | Action |
|---|---|
| `<4 syncs in history` | No prediction emitted; log INFO `insufficient_data` |
| Growth rate ≤ 0 (shrinking / flat) | No warning; log INFO `no_growth_concern` |
| Projected hit > 90 days out | Log INFO with date + days remaining |
| Projected hit ≤ 90 days out | Log **WARN** with date + days remaining + `ceiling_hit_warn=true` flag |
| Projected hit ≤ 30 days out | Log **CRITICAL** + recommend immediate ECS upgrade or sync pause |

**Why linear (not exponential):** vdb grows with ingested article count;
Hermes ingest cadence is roughly daily-cron with stable article rate, so
linear is empirically the right model. If growth becomes super-linear
(which would indicate a bug — duplicated entities / runaway re-embedding),
the 90-day warning still fires conservatively and Hai investigates before cap.
````

#### Update `.planning/STATE-KB-v2.md`

Append a new line under "Current Position" `Last activity:` describing kb-v2.2-1 completion.

**ONLY this row.** Do NOT touch other STATE rows during this phase's commit (concurrent quicks may write sibling rows).

#### Commit

Forward-only, explicit file list:

```
git add \
  kb/scripts/sync_lightrag_storage.py \
  kb/scripts/check_aliyun_kg_memory.py \
  tests/unit/kb/test_sync_lightrag_storage.py \
  tests/integration/kb/test_sync_state_lifecycle.py \
  kb/docs/RUNBOOK-lightrag-storage-sync.md \
  .planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-1-lightrag-storage-sync-PLAN.md \
  .planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-1-lightrag-storage-sync-SUMMARY.md \
  .planning/STATE-KB-v2.md
git status --short    # verify only listed files
git commit -m "..."   # via HEREDOC; mention SYNC-01..07 + Skill usage + locked decisions
git push origin main || { git fetch origin main; git merge --ff-only origin/main; git push origin main; }
```

### Task 4 — User UAT (Rule 3 mandatory; live cross-border sync)

Per `feedback_kb_local_uat_mandatory.md` and project CLAUDE.md Rule 3, this
phase MUST end with a real cross-border sync run (NOT just unit tests).

UAT procedure:

1. User runs `python kb/scripts/sync_lightrag_storage.py --dry-run` from Windows dev
2. Verify dry-run output shows non-zero diff size (Aliyun stale by 9 days; Hermes is ~3.9× larger)
3. User runs `python kb/scripts/sync_lightrag_storage.py` (live mode)
4. Verify: kb-api stops, rsync transfers, atomic swap completes, kb-api restarts, smoke passes, state file updated
5. Verify post-sync: `curl https://101.133.154.49/kb/api/search?q=anthropic&mode=kg` returns >25% more results than pre-sync (more articles in KG)
6. Verify post-sync `check_aliyun_kg_memory.py` reports memory pct
7. Capture transcript into `kb-v2.2-1-SUMMARY.md` § "User UAT" with state file content + memory report

If UAT fails (smoke regression, memory ceiling exceeded, etc.):
- Auto-rollback should restore service
- File issue in SUMMARY § "Defects found" with concrete next-step
- Do NOT mark phase complete until UAT passes

## Acceptance criteria (grep-verifiable)

- [ ] `kb/scripts/sync_lightrag_storage.py` exists; `python kb/scripts/sync_lightrag_storage.py --help` returns flag list
- [ ] `kb/scripts/check_aliyun_kg_memory.py` exists; `python kb/scripts/check_aliyun_kg_memory.py --target aliyun-vitaclaw` returns parseable output
- [ ] `kb/docs/RUNBOOK-lightrag-storage-sync.md` exists with all 5 sections (Weekly / Recovery / Escalation / Memory raise / Cross-ref) — verify with `grep -E "^## §[1-5]" kb/docs/RUNBOOK-lightrag-storage-sync.md` → 5 matches
- [ ] `tests/unit/kb/test_sync_lightrag_storage.py` exists with **9 test cases** (test_atomic_swap_happy_path / test_atomic_swap_rollback_on_smoke_fail / test_state_file_roundtrip / test_memory_threshold_warn_triggers / test_memory_threshold_warn_silent_below / test_rsync_excludes_correct / test_rsync_partial_failure_returns_error / test_state_file_first_run_no_prior_state / test_idempotency_guard_skips_within_24h) — all PASS
- [ ] `tests/integration/kb/test_sync_state_lifecycle.py` exists with **2 test cases** (test_full_sync_cycle_writes_state_file / test_smoke_failure_triggers_rollback_path) — all PASS
- [ ] `pytest tests/unit/kb/ tests/integration/kb/ -v` no regression on existing kb tests
- [ ] No literal Hermes hostname/port/user in any committed file: `grep -rE "ohca|49221|sztimhdd" kb/ tests/ .planning/phases/kb-v2.2-translation-and-kg-search/` → 0 matches
- [ ] No hardcoded SSH passwords / private keys: `grep -rE "Hzyc|BEGIN OPENSSH|password=" kb/scripts/` → 0 matches
- [ ] Skill regex (per `feedback_skill_invocation_not_reference.md`): SUMMARY.md MUST contain literal substrings `Skill(skill="python-patterns"`, `Skill(skill="writing-tests"`, `Skill(skill="search-first"` — verify with `grep -c 'Skill(skill="' kb-v2.2-1-lightrag-storage-sync-SUMMARY.md` → ≥3
- [ ] User UAT performed against real cross-border path; transcript + state file content + memory report captured in SUMMARY § "User UAT"
- [ ] All 7 SYNC-* requirements traced in SUMMARY.md § "Requirement coverage"

## Acceptance criteria addenda (2026-05-18 OOM evidence)

Extends SYNC-04 (memory budget monitoring) with proactive probe + growth
prediction. ADD-only — does not replace any existing acceptance criterion.

- [ ] **SYNC-04 addendum (proactive probe):** `monitor_post_restart_memory()` rolls back proactively when sustained > 85% `MemoryMax` for 2+ consecutive samples within 5 min post-restart — validated by new unit test `test_monitor_post_restart_memory_triggers_rollback_on_sustained_breach`
- [ ] **SYNC-04 addendum (probe inconclusive path):** when fewer than 2 samples obtainable (e.g. ssh failures during probe window), `MemoryProbeResult.status == 'inconclusive'` and orchestrator does NOT rollback (warns + proceeds to smoke test) — validated by new unit test `test_monitor_post_restart_memory_inconclusive_does_not_rollback`
- [ ] **SYNC-04 addendum (growth prediction):** state-file `growth_prediction` field populated from sync 4+ onwards; `predict_ceiling_hit()` logs WARN if projected ceiling within 90 days; logs CRITICAL if within 30 days — validated by new unit test `test_predict_ceiling_hit_warn_at_90_days` + `test_predict_ceiling_hit_returns_none_below_4_samples`
- [ ] **RUNBOOK addendum:** `## §6 OOM Recovery Playbook` + `## §7 vdb Size Growth Prediction` sections appended to RUNBOOK — verify with `grep -E "^## §[6-7]" kb/docs/RUNBOOK-lightrag-storage-sync.md` → 2 matches
- [ ] **RUNBOOK §6 anchored to 2026-05-18 evidence:** contains literal references to "22412 nodes", "1.3GB vdb", "MemoryMax=2.5G", "lightrag_storage.OLD-20260518-065245" — verifies the playbook is empirically grounded, not speculative

## must_haves (goal-backward verification anchors)

1. **Script callable end-to-end:** stop → rsync (two-hop) → swap → start → smoke → state-file-write — exercised by integration test `test_full_sync_cycle_writes_state_file`
2. **State file schema documented in RUNBOOK §1 + §3:** all 5 fields (last_success_ts / vdb_total_bytes / sync_wallclock_s / memory_pct_at_sync / backup_path_kept) appear in RUNBOOK with example JSON
3. **Memory threshold WARN actually triggers:** validated by `test_memory_threshold_warn_triggers` (pct=0.95 + threshold=0.9 → WARN log line emitted)
4. **Rollback path tested:** validated by `test_atomic_swap_rollback_on_smoke_fail` (mocked smoke=False) AND by `test_smoke_failure_triggers_rollback_path` (integration with byte-equality check on restored live dir)
5. **9 unit tests cover happy + rollback + state-file + memory-warn + idempotency + dry-run paths** (per Task 2 table)
6. **Skill discipline:** all 3 declared skills invoked as literal `Skill(skill="..."` calls, grep-verifiable
7. **No bypass:** RUNBOOK §5 explicitly references `feedback_lightrag_is_core_asset_no_bypass.md` to prevent future "let's just skip LightRAG" detours

## Skill discipline (regex check)

After execution, SUMMARY.md MUST contain:
- `Skill(skill="python-patterns"` — Task 1 sync script
- `Skill(skill="writing-tests"` — Task 2 test suite
- `Skill(skill="search-first"` — Task 3 rsync/POSIX-mv/systemd-show verification

Per `feedback_skill_invocation_not_reference.md`: these are tool-call invocations, not `<read_first>` references. The executor MUST emit each as an actual `Skill` tool call during execution.

## Concurrent agent safety

- NO `git commit --amend` (per `feedback_no_amend_in_concurrent_quicks.md`)
- NO `git reset --hard` / `--soft` / `--mixed`
- NO `git rebase -i`
- NO `git push --force` / `--force-with-lease`
- NO `git add -A` / `git add .` (per `feedback_git_add_explicit_in_parallel_quicks.md`)
- ONLY explicit-file `git add` per Task 3 commit block

Possible concurrent territories during this phase's execute window:
- kdb-2 Wave 3 deploy + UAT (different files: `databricks-deploy/*`, `.planning/phases/kdb-*`)
- kdb-2.5 re-index Job (executing in parallel; different Volume + different host)
- Sibling Wave 1 phases: kb-v2.2-5 (F5 test-isolation; touches `tests/conftest.py` and friends) and kb-v2.2-6 (F6 data-lang; touches SSG templates) — territory disjoint from kb/scripts/

## Anti-patterns (planner forbids these in execute)

- ❌ DO NOT modify `kb/{services,data,api,templates}` — sync is a `kb/scripts/` ops script
- ❌ DO NOT embed Aliyun root password / SSH private keys / hostnames in script — SSH key auth via `~/.ssh/aliyun_orchestrator_ed25519` + `~/.ssh/config` alias only
- ❌ DO NOT bake the Hermes literal hostname / port / user into committed files — repo is public per `hermes_ssh.md`. Use config flag (`--source-host`) with a placeholder default the user fills in
- ❌ DO NOT propose F11 Path B (DeepSeek-only long_form skip vdb) — explicitly CUT-FINAL per `DEFERRED.md`
- ❌ DO NOT propose cron on Hermes / Aliyun — locked decision D2: manual user-triggered weekly
- ❌ DO NOT propose Hermes ingest cron pause/resume — locked decision: per-file LightRAG atomic write makes drift acceptable
- ❌ DO NOT propose service hot-swap — locked decision D4: stop → swap → start
- ❌ DO NOT propose real cross-border integration test in CI — locked decision D7: fully mocked (real cross-border is User UAT only, NOT CI)
- ❌ DO NOT modify `kb/deploy/kb-api.service` — script just calls `systemctl stop/start` via SSH
- ❌ DO NOT add `:root` CSS vars / template changes — N/A this phase is pure ops
- ❌ DO NOT touch Aliyun production code paths (`/var/www/kb`, `/etc/caddy/Caddyfile`, FastAPI source) — sync only touches `lightrag_storage/`
- ❌ DO NOT scope-creep into F8' / FU-1 / F1' — those are downstream Wave 2 phases
- ❌ DO NOT use `git add -A` / `--amend` / `git reset --hard` / `git rebase -i` / `git push --force`
- ❌ DO NOT delete or modify existing `.OLD-<TS>` backup directories on Aliyun — leave for human pruning (state file tracks `backup_path_kept`)

## Return signal

```
## kb-v2.2-1 LIGHTRAG-STORAGE-SYNC COMPLETE
- script: kb/scripts/sync_lightrag_storage.py (~<N> LOC)
- memory probe: kb/scripts/check_aliyun_kg_memory.py
- runbook: kb/docs/RUNBOOK-lightrag-storage-sync.md (5 sections)
- tests: 9 unit + 2 integration = 11/11 PASS
- no regression: pytest <X>/<X>
- Skill regex: python-patterns / writing-tests / search-first all in SUMMARY
- User UAT: <pass/fail>; state file content captured; memory pct: <X>%
- pre-locked decisions: all 7 honored (D1-D7)
- SYNC-01..07 traced in SUMMARY § Requirement coverage
- commit: <hash>; pushed origin/main forward-only (ff-merge: yes/no)
- Next: /gsd:plan-phase kb-v2.2-2 (F1' bidirectional translation, Wave 2)
   OR: /gsd:plan-phase kb-v2.2-5 (F5 test-isolation, Wave 1 sibling)
   OR: /gsd:plan-phase kb-v2.2-6 (F6 data-lang, Wave 1 sibling)
```

If BLOCKED → `## kb-v2.2-1 EXECUTE BLOCKED` + cause + escalate (especially if any pre-locked decision D1-D7 proves unworkable).
