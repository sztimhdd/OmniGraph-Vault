# 旧 ingest pipeline 恢复证据（2026-09-24）

状态：本轮单篇真实 ingest 恢复已验证；完整批次退出、下一轮定时触发和全部图片后台任务未验收。

## 范围与前态

用户授权修复现有 pipeline。Mac 原地工作区 `VitaX`，分支 `vitax-refactor-snapshot`；保留原有 WIP，不新建 worktree、不提交或推送。仅操作 `ack-node-2`（47.117.244.253）；每次 SSH 先验证 hostname=`iZj1imk39yc55iZ`。远端 HEAD=`a5d3694`，没有覆盖生产源码。

交接中的 `ExecStartPre --dry-run` 是本地合同；线上实际是 `cleanup_stuck_docs.py --all-failed`。远端脚本会加载 LightRAG 并删除 failed/processing 文档，本轮未运行它，也未把本地脚本覆盖过去。

## 只读取证

- 2026-09-24 06:00、08:00、10:00 UTC 三次完整启动日志均在 Qdrant 初始化后停住，300 秒后 `start-pre operation timed out`，主阶段没有启动。
- 12:00 UTC 启动前报告 `docs_identified=0`；主进程 PID 258238 于 12:00:02 启动。识别 336 条输入、324 候选，12 条写入 skipped；12:00:23 后停在初始化，无文章处理日志。
- 修复前最新成功：id=66326，article_id=18944，source=wechat，status=ok，时间原值 `2026-09-13 03:50:56`（SQLite localtime / CST）。最新任意记录 id=66987，status=skipped。
- 主线程状态 `Dsl`，wchan=`mem_cgroup_handle_over_high`，约 81 分钟墙钟仅 27 秒 CPU；没有完成后退出挂起的日志特征。
- cgroup memory.current=3465822208，memory.high=3221225472，memory.max=5368709120；memory.events high=358723、max=0、oom=0、oom_kill=0。memory.pressure full avg10=38.70；匿名页约 3.46 GB，file=0。
- 主机 total=15097 MiB，available=4231 MiB，swap used=0。不是已经发生的 OOM；是超过软上限后持续直接回收/限流。

## 最小修复与回滚

13:21:59 UTC，先备份到远端 `/root/vitax-ingest-repair-20260924T132159Z`（0700），保留 unit/drop-ins、before-properties 和 rollback 描述。备份可能含配置，留在服务器，不复制进仓库。

通过 owner-native 命令持久化：

```sh
systemctl set-property omnigraph-daily-ingest.service MemoryHigh=4G
```

回读 MemoryHigh=4294967296，MemoryMax=5368709120；PID 仍是 258238。没有重启、停止或额外发起 ingest；未修改硬上限、TimeoutStartSec、batch budget、timer、provider、凭据或其他服务。systemd 负责生成和解析 property drop-in。

必要时回滚软限制：`systemctl set-property omnigraph-daily-ingest.service MemoryHigh=3G`。这会重新引入本次限流风险，不应在无理由时执行。

本地只把 `deploy/aliyun/systemd/omnigraph-daily-ingest.service` 的 MemoryHigh 3G 改为 4G，保留既有 dry-run 合同；该文件没有作为整体部署到线上。

## 修复后的执行证据

- 13:22:00 UTC，同一 PID 加载 llm_response_cache=8874 条、doc_status=2181 条，立即进入文章循环。
- 13:22:12 UTC，Layer2 n=5，ok=2、reject=3、null=0；开始第一篇真实文章。
- 13:22:27 UTC，LightRAG `Processing 1 document(s)`；13:22:51 UTC 初始化 LLM workers。
- 修复后 memory.current=2346414080，主线程转为 `Ssl/ep_poll`，high 计数停止于 360202；尚需后续快照确认。
- 3 GiB→4 GiB 单变量即时解阻支持主阶段根因；先前三次 prestart 未采集实时 cgroup，不能声称其根因已逐次证明相同。

## 本地检查与限制

`OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_ingest_prestart_read_only.py tests/unit/test_mcp_healthcheck_alert_label.py -q`：3 passed。

没有改 ingest_from_db、KB、模型依赖或运行数据，没有手动运行带隐式重启的 mcp-healthcheck.py。Qdrant client/server 版本警告保留，未无证据升级依赖。

原 WIP 的 47 文件 SHA 清单保存在本机临时目录 `/var/folders/y4/b7fx08tj715gknw6fdvt0vr80000gn/T/vitax-repair-wip-z7p849mj/sha256.json`；临时清单不是长期备份。

## 最终验收（13:36:38 UTC 只读 SQL）

原生服务 PID 258238 未重启，新增数据库记录：

| id | article_id | source | status | ingested_at（数据库原值，CST） |
| --- | --- | --- | --- | --- |
| 66988 | 18946 | wechat | ok | 2026-09-24 21:36:14 |

对应 UTC 为 13:36:14。成功记录在改变内存软限制后约14分钟产生，原成功记录停在9月13日。观察程序只读 SQL 和服务元数据，未插入或修改结果；它发现新 ok 后自行退出。

13:34:21 UTC：完成173实体、295关系合并；13:34:33：持久化并完成父文档。随后实际 Vision 路线仍为 deepseek，13:36:04启动图片子文档，13:36:14外层已进入成功后的等待，13:36:19继续下一候选。未改模型/供应商。

[机器可读观察记录](verification.jsonl)覆盖13:31:37–13:36:38 UTC。末态 MemoryCurrent=2674819072；MemoryHigh=4294967296；MemoryMax=5368709120；high=360202 未增长，oom=0、oom_kill=0。

**验收结论：** 当前主阶段因3 GiB软限制持续回收而阻塞，提升到4 GiB后同一进程即时解阻，并真实产生新增ok。此次最小修复达到用户指定的单次恢复条件，不扩展为全批次、全部图片、Wiki、同步、检索或下一次prestart的PASS。

**残余风险：** 图/缓存继续增长可能再次越过4 GiB；5 GiB硬上限仍有效。线上仍有删除式 `--all-failed` prestart，与本地只读合同不同；未来若需同步该合同，应单独备份/验证，不整树部署。历史prestart超时只建立了同阶段相似性，未逐次证明cgroup原因。Qdrant版本警告及新旧查询数据一致性未在本轮解决。

**检查：** 相关3项离线测试通过；最终 `git diff --check` 通过；原47个WIP文件中仅`.planning/ISSUES.md`增加当前优先级入口，另外46个字节不变。没有提交、推送或新建worktree。核心计划复用原文档，新增两张后续决策票；没有恢复旧goal或实施新产品。
