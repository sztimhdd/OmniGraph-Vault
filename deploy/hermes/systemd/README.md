# Hermes systemd unit — daily pull from Aliyun

These two files (`omnigraph-daily-pull.service` and
`omnigraph-daily-pull.timer`) replace the 11 ingest-related Hermes-agent-cron
entries that aim-3 cutover retired (CUTOVER-03). They install the single
new daily-pull job (SYNC-02 "11 → 1" net cron count).

## Schedule

| Local | UTC OnCalendar |
| --- | --- |
| 02:00 ADT | `*-*-* 05:00:00 UTC` |

ADT (Atlantic Daylight Time) = UTC-3. Hermes WSL2 system TZ is
`America/Halifax` (verified `timedatectl` 2026-05-24), so the explicit
`UTC` suffix on the `OnCalendar` value pins the fire time to 05:00 UTC
regardless of host TZ drift / DST changes. Choice rationale: Aliyun
evening-ingest fires at 21:00 ADT (00:00 UTC); 5h budget covers ingest
finishing + buffer. Pulling at 02:00 ADT captures the freshest snapshot.

## Deployment

```bash
# Copy to /etc/systemd/system/
sudo cp deploy/hermes/systemd/omnigraph-daily-pull.service /etc/systemd/system/
sudo cp deploy/hermes/systemd/omnigraph-daily-pull.timer /etc/systemd/system/

# Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable --now omnigraph-daily-pull.timer

# Verify
systemctl list-timers omnigraph-daily-pull.timer --no-pager
systemctl is-enabled omnigraph-daily-pull.timer
systemctl is-active omnigraph-daily-pull.timer
```

## Verification post-deploy

```bash
# Manual fire (skip waiting for next 02:00 ADT)
sudo systemctl start omnigraph-daily-pull.service

# Watch journald output (Ctrl+C to stop)
journalctl -u omnigraph-daily-pull.service -f --no-pager

# Confirm exit success
systemctl status omnigraph-daily-pull.service --no-pager
```

## SYNC-04 retry / marker observability

The retry loop and marker-file logic live IN
`scripts/sync-from-aliyun.sh` (per FINDING 7). The systemd unit captures
all stdout / stderr via `StandardOutput=journal` /
`StandardError=journal`. To inspect:

```bash
# Last 24h of pull logs
journalctl -u omnigraph-daily-pull.service --since "24 hours ago" --no-pager

# Stale failure marker (>48h = §6 Risk row 8 alert)
ls -la /tmp/aliyun-sync-failed-*
```

## References

- `.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md`
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` SYNC-02 + SYNC-04
- `scripts/sync-from-aliyun.sh` (the script this unit calls)
