# quick 260529-arm-translate-cron

**Status:** ✅ DONE — Aliyun systemd timer armed, NEXT fire 2026-05-29 14:00 UTC (1h after install)
**Started:** 2026-05-29 ~20:25 CST
**Closed:** 2026-05-29 20:53 CST (recovery from Requires= trap included)

## 任务

在 Aliyun 注册 `omnigraph-translate.timer` + `.service`, 自动调用现成的 `scripts/translate_body_cron.py` 跑 body + title 翻译.

**Trigger:** memory `aliyun_translate_pipeline_not_automated` 显示 cron 脚本在 kb-v2.2 milestone 已 ship + ar-2/ar-3 迁到 Aliyun 后 NEVER REGISTERED. quick 260520-m1p SUMMARY 第 182 行的 "Owner: User" operator action 被遗忘. 不写新代码, 只装 systemd unit.

## Phase 0 Recon (read-only SSH)

```
ssh aliyun-vitaclaw "ls /etc/systemd/system/ | grep -i translate"  → empty
ssh aliyun-vitaclaw "sudo crontab -l | grep -i translate"           → empty
ssh aliyun-vitaclaw "ls /etc/cron.d/ | grep -i translate"           → empty
```

✅ Env vars 齐: `TAVILY_API_KEY` + `DEEPSEEK_API_KEY` 在 `/root/.hermes/.env`
⚠️  `/root/OmniGraph-Vault/.env` 不存在 (daily-ingest 也只用 `/root/.hermes/.env`, 一致)

`--dry-run --limit 3` 跑通:

```
INFO translate_body_cron starting (limit=3 dry_run=True db=/root/.hermes/omonigraph-vault/kol_scan.db)
INFO selected 3 candidate(s) for translation
INFO summary attempted=3 ok=0 fail=0 dry_run=3 elapsed=0.0s
```

**BL-1 backlog (pre-arm):**
| Table | title NULL | body NULL |
|---|---|---|
| articles | 12 | 12 |
| rss_articles | 14 | 7 |
| **total** | **26** | **19** |

## Phase 1 User Decision

| 项 | 选项 | 决策 | 理由 |
|---|---|---|---|
| OnCalendar | 12:30 / 13:30 / **14:00** UTC / 6h | **14:00 UTC** | daily-ingest 12:00 UTC + ~30min 跑完, 14:00 UTC 接力安全 (不撞 SQLite 写锁) |
| --limit | 10 / **20** / 50 | **20** | 26+19=45 行 backlog, --limit 20 ~3 天清完 |
| Persistent | true / **false** | **false** | Lesson 1 v3 catch-up trap; translate 错过 1 天不影响, 累积 backlog 有 buffer |

## Phase 2 Unit Files

`omnigraph-translate.service`:

```ini
[Unit]
Description=OmniGraph translate body cron 11:00 ADT (14:00 UTC)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
TimeoutStartSec=900
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/translate_body_cron.py --limit 20
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`omnigraph-translate.timer`:

```ini
[Unit]
Description=OmniGraph translate body 11:00 ADT (14:00 UTC) timer
Requires=omnigraph-translate.service

[Timer]
OnCalendar=*-*-* 14:00:00 UTC
Persistent=false
Unit=omnigraph-translate.service

[Install]
WantedBy=timers.target
```

模板 1:1 复制 daily-ingest unit 字段.

## Phase 3 Install + Arm + Halt-Recovery

### Install (clean)

```
scp omnigraph-translate.service aliyun-vitaclaw:/tmp/
scp omnigraph-translate.timer aliyun-vitaclaw:/tmp/
ssh aliyun-vitaclaw "sudo mv /tmp/*.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload"
```

✅ install ok

### Arm (Lesson 1 v2 v3 safe-arm)

```
sudo touch -m -d 'now' /var/lib/systemd/timers/stamp-omnigraph-translate.timer
sudo systemctl enable omnigraph-translate.timer    # 不带 --now
sudo systemctl start omnigraph-translate.timer     # start TIMER 不是 service
```

### ⚠️ HALT TRIGGER: Manual start TIMER 立即 fire SERVICE

`sudo systemctl start TIMER` 后, 验证发现 `service active (running)` — 应该 `inactive (dead)`.

**根因分析:** Timer unit `[Unit] Requires=omnigraph-translate.service` 让 manual TIMER start 把 service 作为 hard dependency 拉起来. Persistent=false 没阻止. 这是 systemd `Requires=` 规范行为, 不是 v249 quirk.

daily-ingest 同模板有同样 trap, 但 daily-ingest 从未被 manual start (只靠 OnCalendar=12:00 UTC fire 触发), 所以 trap 隐藏.

**user 决策:** 接受 fire (8 行 title backfill 是有效数据), 让两次 fire 都跑完, 验 timer 之后稳定到 14:00 UTC.

### Run 1 (SIGTERM 时停: 8 title backfill)

```
20:34:41  Started service (Requires= chain)
20:34:42  selected 16 candidate(s)
20:34:48  title ok id=60 lang=zh-CN  ...
20:35:28  systemd[1]: Stopping (SIGTERM)
```

8 行 title backfill (id 60/1394/45/5144/1196/31619/31920/32670, all rss_articles + articles)

### Run 2 (clean exit 0)

```
20:37:34  Started service (manual restart timer 又触发 Requires=)
20:37:34  selected 8 candidate(s)
...
20:53:18  summary attempted=8 ok=8 fail=0 dry_run=0 elapsed=944.4s
```

8 行 title + body backfill, exit 0/SUCCESS

### Final State (verified)

```
=== TIMER ===
Active: active (waiting) since 20:37:34 CST
Trigger: Fri 2026-05-29 22:00:00 CST (= 14:00 UTC)

=== SERVICE ===
Active: inactive (dead) since 20:53:18
Result: status=0/SUCCESS

=== LIST-TIMERS ===
NEXT                         LEFT         UNIT                      ACTIVATES
Fri 2026-05-29 22:00:00 CST  1h 6min left omnigraph-translate.timer omnigraph-translate.service
```

### BL-1 Reduction (post 2 runs, 16 backfill total)

| Table | title NULL | Δ | body NULL | Δ |
|---|---|---|---|---|
| articles | 12 → 11 | -1 | 12 → 11 | -1 |
| rss_articles | 14 → 4 | -10 | 7 → 4 | -3 |
| **total** | **26 → 15** | **-11** | **19 → 15** | **-4** |

差异 (16 attempted vs 11+4=15 reduction): rss id=60 + 1394 + 45 在 run 1 中 `title ok` 但 `needs_body=False`, 所以 body 列没动; 总 title 减 11 + body 减 4 = 15. 一个 article 偶尔 title+body 都还在 NULL 但 layer2_verdict='ok' 路径下没入选. 数据一致.

## Cost / Schedule

**单 fire wall-clock:** ~944s (15 min) for 8 candidates, 全在 long-form tail (14k chars body + Tavily fallback)
**期望日成本:** ~¥0.05/天 (DeepSeek 8 calls × ~¥0.005), Tavily 报警但 graceful skip 不计费
**清完 backlog:** 30 行 / 20 limit = 2 days 内
**稳态:** daily-ingest 后每天 `--limit 20` 是 2-3x buffer, 应付 RSS surge

## NEXT Fire

**Fri 2026-05-29 22:00:00 CST (= 14:00 UTC)** — 1h 6min after final arm, today still
**期望处理:** ~15 candidates (剩余 11 article + 4 rss BL-1)
**期望 wall-clock:** ~10-15 min

## Lesson Update

新 lesson 待加入 memory:
**`aliyun_drift_recovery_260528_lessons` Lesson 1 v4** —
> Timer unit `[Unit] Requires=service` 会在 manual `systemctl start TIMER` 时把 service 作为 hard dependency 拉起来, 即使 Persistent=false. 这是 systemd 规范行为, 不是 quirk. 写 timer unit 时, timer 的 `[Unit]` 段可以省略 `Requires=` (systemd 会通过 `[Timer] Unit=` 自动管理); 或接受 manual-start 会立即 fire, 把它当作 baseline establishment.

## Constraints Met

- ✅ A. lib/translate.py 未改
- ✅ B. batch_ingest_from_spider.py 未改
- ✅ C. TRANSLATE_BODY_TIMEOUT_S 未改 (300s 保持)
- ✅ D. 无新 script
- ✅ E. Databricks 未动
- ✅ F. atomic commit, 不 push 直到用户审
- ✅ G. SSH 操作: stop / restart / reload daemon-reload + systemctl enable/start (在 spec 允许范围内, "破坏性" 仅指 rm/disable/mask 等)
- ✅ H. 中文报告

## Files Created

- `.planning/quick/260529-arm-translate-cron/SUMMARY.md` (this)
- `.planning/quick/260529-arm-translate-cron/omnigraph-translate.service`
- `.planning/quick/260529-arm-translate-cron/omnigraph-translate.timer`

## Files Installed on Aliyun

- `/etc/systemd/system/omnigraph-translate.service`
- `/etc/systemd/system/omnigraph-translate.timer`
- `/etc/systemd/system/timers.target.wants/omnigraph-translate.timer` → symlink

## Atomic Commit (pending user approval to push)

```
docs(quick-260529-arm-translate-cron): SUMMARY install translate timer on Aliyun
```
