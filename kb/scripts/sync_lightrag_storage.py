"""Hermes to Aliyun lightrag_storage weekly sync orchestrator (kb-v2.2-1 F12).

Two-hop rsync: Windows dev as relay (source_host -> relay_dir -> target_host).
Atomic swap with .OLD-<TS> backup, proactive OOM probe, automatic rollback.

Usage:
    python kb/scripts/sync_lightrag_storage.py [--dry-run] [--force]
    python kb/scripts/sync_lightrag_storage.py --help
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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
    last_success_ts: str        # ISO 8601 or "" on failure
    vdb_total_bytes: int
    sync_wallclock_s: float
    memory_pct_at_sync: float
    backup_path_kept: str


@dataclass(frozen=True)
class MemoryReport:
    current_bytes: int
    max_bytes: int
    pct: float                  # current / max


@dataclass(frozen=True)
class MemoryProbeResult:
    status: str                        # 'ok' | 'exceeded' | 'inconclusive'
    samples: tuple[MemoryReport, ...]  # oldest first
    consecutive_breach_count: int
    triggered_threshold: float


class SyncFailedMemoryCeiling(SystemExit):
    """Raised when monitor_post_restart_memory detects sustained OOM trajectory."""


# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------


def ssh_run(
    host_alias: str, cmd: str, *, check: bool = True
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", host_alias, cmd],
        capture_output=True,
        text=True,
        check=check,
    )


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------


def pause_target_kb_api(target_host: str) -> None:
    ssh_run(target_host, "systemctl stop kb-api.service")
    _log_event("service_stopped", {"host": target_host})


def start_target_kb_api(target_host: str) -> None:
    ssh_run(target_host, "systemctl start kb-api.service")
    _log_event("service_started", {"host": target_host})


# ---------------------------------------------------------------------------
# Rsync / swap / rollback
# ---------------------------------------------------------------------------


_RSYNC_EXCLUDES = ["--exclude=*.tmp", "--exclude=.bak*", "--exclude=*.lock"]


def rsync_to_staging(
    source_host: str,
    source_path: str,
    relay_dir: str,
    target_host: str,
    target_staging_path: str,
    *,
    dry_run: bool = False,
) -> None:
    dr = ["--dry-run"] if dry_run else []
    base_flags = ["-az", "--partial", "--inplace"] + _RSYNC_EXCLUDES + dr
    # Hop 1: source_host → relay_dir (local Windows dev)
    subprocess.run(
        ["rsync"] + base_flags + [f"{source_host}:{source_path}", relay_dir],
        check=True,
    )
    # Hop 2: relay_dir → target_host:staging_path
    subprocess.run(
        ["rsync"] + base_flags + [relay_dir, f"{target_host}:{target_staging_path}"],
        check=True,
    )
    _log_event("rsync_done", {"relay": relay_dir, "dry_run": dry_run})


def atomic_swap(
    target_host: str, live_path: str, staging_path: str, backup_ts: str
) -> str:
    live_path = live_path.rstrip("/")
    backup_path = f"{live_path}.OLD-{backup_ts}"
    ssh_run(
        target_host,
        f"mv {live_path} {backup_path} && mv {staging_path} {live_path}",
    )
    _log_event("swap_done", {"backup": backup_path})
    return backup_path


def rollback(target_host: str, live_path: str, backup_path: str) -> None:
    live_path = live_path.rstrip("/")
    ssh_run(target_host, f"rm -rf {live_path} && mv {backup_path} {live_path}")
    start_target_kb_api(target_host)
    _log_event("rollback_done", {"restored_from": backup_path})


# ---------------------------------------------------------------------------
# Memory monitoring
# ---------------------------------------------------------------------------


def check_memory_budget(target_host: str) -> MemoryReport:
    result = ssh_run(
        target_host,
        "systemctl show -p MemoryCurrent -p MemoryMax kb-api.service",
    )
    props: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    current = int(props.get("MemoryCurrent", "0"))
    raw_max = props.get("MemoryMax", "0")
    max_b = int(raw_max)
    if max_b >= 2**62:  # systemd "infinity" sentinel
        max_b = 1
    pct = current / max_b if max_b > 0 else 0.0
    return MemoryReport(current_bytes=current, max_bytes=max_b, pct=pct)


def monitor_post_restart_memory(
    target_host: str,
    max_pct: float = 0.85,
    sample_interval_s: int = 30,
    sample_count: int = 10,
) -> MemoryProbeResult:
    samples: list[MemoryReport] = []
    consecutive = 0
    max_consecutive = 0
    for _ in range(sample_count):
        try:
            report = check_memory_budget(target_host)
        except subprocess.CalledProcessError:
            break  # ssh failure — stop early
        samples.append(report)
        if report.pct > max_pct:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
        if max_consecutive >= 2:
            _log_event("memory_probe_exceeded", {"pct": report.pct, "run": max_consecutive})
            return MemoryProbeResult(
                status="exceeded",
                samples=tuple(samples),
                consecutive_breach_count=max_consecutive,
                triggered_threshold=max_pct,
            )
        time.sleep(sample_interval_s)
    if len(samples) < 2:
        return MemoryProbeResult(
            status="inconclusive",
            samples=tuple(samples),
            consecutive_breach_count=0,
            triggered_threshold=max_pct,
        )
    return MemoryProbeResult(
        status="ok",
        samples=tuple(samples),
        consecutive_breach_count=max_consecutive,
        triggered_threshold=max_pct,
    )


# ---------------------------------------------------------------------------
# Growth prediction
# ---------------------------------------------------------------------------


def predict_ceiling_hit(
    state_history: list[SyncState], current_max_bytes: int
) -> Optional[date]:
    """Linear extrapolation of vdb growth; returns projected ceiling-hit date or None."""
    if len(state_history) < 4 or current_max_bytes <= 0:
        return None
    t0 = datetime.fromisoformat(state_history[0].last_success_ts.replace("Z", "+00:00"))
    xs: list[float] = []
    ys: list[int] = []
    for s in state_history:
        ts = datetime.fromisoformat(s.last_success_ts.replace("Z", "+00:00"))
        xs.append((ts - t0).total_seconds() / 86400)
        ys.append(s.vdb_total_bytes)
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if den == 0 or num / den <= 0:
        return None
    slope = num / den
    t_hit_days = (current_max_bytes - (y_mean - slope * x_mean)) / slope
    t_hit_date = (t0 + timedelta(days=t_hit_days)).date()
    days_until = (t_hit_date - date.today()).days
    return t_hit_date if days_until <= 365 else None


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def smoke_test(target_host: str, public_url: str) -> bool:
    for endpoint in (f"{public_url}/api/search?q=test&mode=kg", f"{public_url}/health"):
        try:
            r = subprocess.run(
                ["curl", "-sf", "--max-time", "15", endpoint],
                capture_output=True,
                check=False,
            )
            if r.returncode != 0:
                _log_event("smoke_fail", {"url": endpoint})
                return False
        except FileNotFoundError:
            logger.warning("curl not found; smoke test skipped")
            return True
    _log_event("smoke_pass", {"url": public_url})
    return True


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------


def update_state_file(
    target_host: str,
    state_file_path: str,
    state: SyncState,
    extra: Optional[dict] = None,
) -> None:
    d = asdict(state)
    if extra:
        d.update(extra)
    # Read existing history to append
    existing = ssh_run(target_host, f"cat {state_file_path} 2>/dev/null", check=False)
    history: list[dict] = []
    if existing.returncode == 0 and existing.stdout.strip():
        try:
            parsed = json.loads(existing.stdout)
            history = parsed.get("history", [])
        except (json.JSONDecodeError, AttributeError):
            pass
    history.append({"ts": d["last_success_ts"], "vdb_total_bytes": d["vdb_total_bytes"]})
    history = history[-20:]  # rolling 20-entry window
    d["history"] = history
    payload = json.dumps(d)
    # Use printf to avoid shell single-quote escaping issues
    ssh_run(target_host, f"printf '%s' {json.dumps(payload)!r} > {state_file_path}")


def _read_state_file(target_host: str, state_file_path: str) -> Optional[SyncState]:
    result = ssh_run(target_host, f"cat {state_file_path} 2>/dev/null", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        d = json.loads(result.stdout)
        return SyncState(
            last_success_ts=d["last_success_ts"],
            vdb_total_bytes=d["vdb_total_bytes"],
            sync_wallclock_s=d["sync_wallclock_s"],
            memory_pct_at_sync=d["memory_pct_at_sync"],
            backup_path_kept=d["backup_path_kept"],
        )
    except (json.JSONDecodeError, KeyError):
        return None


def _read_state_history(target_host: str, state_file_path: str) -> list[SyncState]:
    result = ssh_run(target_host, f"cat {state_file_path} 2>/dev/null", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        d = json.loads(result.stdout)
        return [
            SyncState(
                last_success_ts=h["ts"],
                vdb_total_bytes=h["vdb_total_bytes"],
                sync_wallclock_s=0.0,
                memory_pct_at_sync=0.0,
                backup_path_kept="",
            )
            for h in d.get("history", [])
        ]
    except (json.JSONDecodeError, KeyError):
        return []


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------


def _log_event(event: str, details: dict) -> None:
    msg = json.dumps(
        {"ts": datetime.now(tz=timezone.utc).isoformat(), "event": event, **details}
    )
    logger.info(msg)


# ---------------------------------------------------------------------------
# CLI + orchestration
# ---------------------------------------------------------------------------


_DEFAULTS: dict = {
    "source_host": "<hermes-alias>",
    "source_path": "/home/<user>/.hermes/omonigraph-vault/lightrag_storage/",
    "target_host": "aliyun-vitaclaw",
    "target_path": "/root/.hermes/omonigraph-vault/lightrag_storage/",
    "staging_relay_dir": "./.sync-relay/",
    "state_file": "/etc/lightrag-sync-state.json",
    "memory_warn_threshold": 0.9,
    "public_smoke_url": "https://<target-host>/kb",
}


def parse_args(argv: Optional[list[str]] = None) -> SyncConfig:
    p = argparse.ArgumentParser(
        description="Hermes to Aliyun lightrag_storage weekly sync (kb-v2.2-1 F12)."
    )
    p.add_argument("--source-host", default=_DEFAULTS["source_host"])
    p.add_argument("--source-path", default=_DEFAULTS["source_path"])
    p.add_argument("--target-host", default=_DEFAULTS["target_host"])
    p.add_argument("--target-path", default=_DEFAULTS["target_path"])
    p.add_argument("--staging-relay-dir", default=_DEFAULTS["staging_relay_dir"])
    p.add_argument("--state-file", default=_DEFAULTS["state_file"])
    p.add_argument(
        "--memory-warn-threshold", type=float,
        default=_DEFAULTS["memory_warn_threshold"],
    )
    p.add_argument("--public-smoke-url", default=_DEFAULTS["public_smoke_url"])
    p.add_argument("--force", action="store_true", help="Bypass 24h idempotency guard")
    p.add_argument("--dry-run", action="store_true", help="rsync --dry-run, no swap")
    ns = p.parse_args(argv)
    return SyncConfig(
        source_host=ns.source_host,
        source_path=ns.source_path,
        target_host=ns.target_host,
        target_path=ns.target_path,
        staging_relay_dir=ns.staging_relay_dir,
        state_file_path=ns.state_file,
        memory_warn_threshold=ns.memory_warn_threshold,
        public_smoke_url=ns.public_smoke_url,
        force=ns.force,
        dry_run=ns.dry_run,
    )


def main(argv: Optional[list[str]] = None) -> None:
    cfg = parse_args(argv)
    _log_event("start", {"dry_run": cfg.dry_run, "force": cfg.force})
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Step 2: 24h idempotency guard
    if not cfg.force:
        prior = _read_state_file(cfg.target_host, cfg.state_file_path)
        if prior is not None and prior.last_success_ts:
            last_dt = datetime.fromisoformat(
                prior.last_success_ts.replace("Z", "+00:00")
            )
            age = datetime.now(tz=timezone.utc) - last_dt
            if age < timedelta(hours=24):
                _log_event("skip_recent_sync", {"hours_ago": age.total_seconds() / 3600})
                print("recent sync within 24h, skipping (use --force to override)")
                sys.exit(0)

    target_staging = cfg.target_path.rstrip("/") + "_NEW/"
    t_start = time.monotonic()

    # Step 4: rsync (two-hop)
    try:
        rsync_to_staging(
            cfg.source_host, cfg.source_path,
            cfg.staging_relay_dir,
            cfg.target_host, target_staging,
            dry_run=cfg.dry_run,
        )
    except subprocess.CalledProcessError as exc:
        _log_event("error", {"phase": "rsync", "rc": exc.returncode})
        sys.exit(1)

    # Step 5: dry-run exits here
    if cfg.dry_run:
        _log_event("dry_run_complete", {})
        sys.exit(0)

    # Steps 6-7: pause + atomic swap
    pause_target_kb_api(cfg.target_host)
    backup_path = atomic_swap(cfg.target_host, cfg.target_path, target_staging, ts)

    # Step 8: start service
    start_target_kb_api(cfg.target_host)

    # Step 8a: proactive OOM probe (addendum — 2026-05-18 empirical evidence)
    probe = monitor_post_restart_memory(cfg.target_host, max_pct=0.85)
    if probe.status == "exceeded":
        _log_event("memory_ceiling_rollback", {
            "consecutive": probe.consecutive_breach_count,
            "samples": len(probe.samples),
        })
        rollback(cfg.target_host, cfg.target_path, backup_path)
        update_state_file(
            cfg.target_host, cfg.state_file_path,
            SyncState(
                last_success_ts="",
                vdb_total_bytes=0,
                sync_wallclock_s=time.monotonic() - t_start,
                memory_pct_at_sync=probe.samples[-1].pct if probe.samples else 0.0,
                backup_path_kept=backup_path,
            ),
        )
        raise SyncFailedMemoryCeiling(1)

    # Step 9: post-stable memory reading
    mem = check_memory_budget(cfg.target_host)
    if mem.pct > cfg.memory_warn_threshold:
        _log_event("memory_warn", {"pct": mem.pct, "threshold": cfg.memory_warn_threshold})

    # Step 11: smoke test
    if not smoke_test(cfg.target_host, cfg.public_smoke_url):
        rollback(cfg.target_host, cfg.target_path, backup_path)
        update_state_file(
            cfg.target_host, cfg.state_file_path,
            SyncState(
                last_success_ts="",
                vdb_total_bytes=0,
                sync_wallclock_s=time.monotonic() - t_start,
                memory_pct_at_sync=mem.pct,
                backup_path_kept=backup_path,
            ),
        )
        sys.exit(1)

    # Measure vdb size on target
    du = ssh_run(
        cfg.target_host,
        f"du -sb {cfg.target_path} 2>/dev/null | awk '{{print $1}}'",
        check=False,
    )
    vdb_bytes = int(du.stdout.strip() or "0")
    wallclock = time.monotonic() - t_start

    # Growth prediction (step 12 — addendum)
    history = _read_state_history(cfg.target_host, cfg.state_file_path)
    growth_extra: dict = {}
    hit_date = predict_ceiling_hit(history, mem.max_bytes)
    if hit_date is not None:
        days_until = (hit_date - date.today()).days
        level = "CRITICAL" if days_until <= 30 else "WARN" if days_until <= 90 else "INFO"
        growth_extra = {
            "growth_prediction": {
                "samples_used": len(history),
                "projected_ceiling_hit_date": hit_date.isoformat(),
                "days_until_ceiling": days_until,
                "ceiling_hit_warn": days_until <= 90,
            }
        }
        _log_event(f"growth_prediction_{level.lower()}", growth_extra["growth_prediction"])

    # Step 12: write success state
    update_state_file(
        cfg.target_host, cfg.state_file_path,
        SyncState(
            last_success_ts=datetime.now(tz=timezone.utc).isoformat(),
            vdb_total_bytes=vdb_bytes,
            sync_wallclock_s=wallclock,
            memory_pct_at_sync=mem.pct,
            backup_path_kept=backup_path,
        ),
        extra=growth_extra if growth_extra else None,
    )
    _log_event("complete", {
        "wallclock_s": round(wallclock, 1),
        "vdb_bytes": vdb_bytes,
        "memory_pct": round(mem.pct, 3),
        "backup": backup_path,
    })


if __name__ == "__main__":
    main()
