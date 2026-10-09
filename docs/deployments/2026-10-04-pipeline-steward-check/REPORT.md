# 管家告警核对与只读进度入口

核查窗口：2026-10-04 Halifax 19:34–19:38（UTC 22:34–22:38）。只读使用既有 `ack-node-2` SSH，hostname核为 `iZj1imk39yc55iZ`。没有重跑、重启、改配置、抓取文章或调用业务模型。本报告是时间点证据，不是实时健康承诺。

## 告警裁决

| 对象 | 实测业务结果 | 裁决 |
|---|---|---|
| 微信周扫描 | 12:04–12:05 Halifax运行；attempted=20，failed=5，new=288，status=partial；失败account_id为1/4/7/9/12，首个错误仅记录request_failed | exit 2代表部分失败，不能解释为全停或仅凭systemd的INVALIDARGUMENT标签认定参数错误。具体HTTP/平台原因未在现有摘要中披露，不能猜成登录过期 |
| RSS抓取 | 06:00–06:11 Halifax运行；feeds_ok=71、feeds_fail=20、articles_inserted=12、articles_failed=0，status=partial | 同样部分失败。首个完整源错误为lcamtuf.substack.com的URLError(OSError(101, Network is unreachable))；随后还有TLS超时、XML解析和DNS错误，不能归为一个故障 |
| 日入库 | 19:00:02系统日志Service reached runtime time limit，Result=timeout；RuntimeMaxUSec=4h。19:01:10新进程运行；InvocationID=edbe1a45ed9649f1ba7e8b7583ca9743，52个候选 | 是运行上限，不是5分钟启动门限。重启后有处理活动，但不能宣告本批完成 |
| 日入库落库 | 截至19:36，按本轮开始时间过滤ingestions：wechat failed=1、skipped=3、ok=0。失败article_id=20328，19:30:39；筛除20329/20330/20332，19:30:44 | 本批暂无已确认成功入库。图层有persist/Completed processing消息仍不足以覆盖外层failed结果。该失败行没有错误详情列，所读日志邻域也未给出具体失败异常，根因仍未知 |
| 改写 | 18:55:55退出0；摘要attempted=150、ok=56、fail=48、skipped_oversize=46 | 进程正常退出，业务部分成功，不能按exit0全绿 |
| VitaX本地引用 | 主控此前独立接受已发布引用修复：Wiki22正文引用同版可解析、28面板，后续单篇editorial保持它们 | 管家单个引用恢复是较窄的有效证据；不等于全内容或完整backfill验收 |

入库当次MemoryCurrent=3270627328 bytes（约3.05 GiB）、MemoryHigh=5 GiB、MemoryMax=6 GiB。该采样不支持“此时再次触及内存软上限”，也不排除其他时刻压力。Result=success在active期间不是批次最终成功。

## 管家复用的现成回执

这些命令在已授权采集机执行。先核hostname，不因别名名称猜角色。

### 1. 扫描和改写的业务摘要

读取systemd journal，不执行脚本本身：

```bash
journalctl -u omnigraph-dajiala-scan.service --since '2026-10-04 00:00:00 UTC' --no-pager -o short-iso
journalctl -u omnigraph-rss-fetch.service --since '2026-10-04 00:00:00 UTC' --no-pager -o short-iso
journalctl -u omnigraph-rewrite.service --since '2026-10-04 00:00:00 UTC' --no-pager -o short-iso
```

实际巡检将时间窗换成上次检查到现在，只解析最终JSON摘要/summary和首个真实错误。保存计数与时间，不转发整段日志、正文、URL参数或密钥。微信摘要的288是新列表记录，不是288篇正文已抓取、翻译或建图。

### 2. 入库当前调用与最终批次回执

```bash
systemctl show omnigraph-daily-ingest.service -p InvocationID -p ExecMainStartTimestamp -p ActiveState -p SubState -p Result -p ExecMainStatus -p RuntimeMaxUSec
journalctl _SYSTEMD_INVOCATION_ID=edbe1a45ed9649f1ba7e8b7583ca9743 --no-pager -o short-iso
```

InvocationID每次启动变化，先读第一条再用实际值查询。不要永远查询本文旧ID。系统级超时原因可用 `journalctl _PID=1` 配合同一时间窗与unit名过滤。

既有批次文件为 `/root/OmniGraph-Vault/data/batch_timeout_metrics_*.json`。它包含completed_articles、timed_out_articles、not_started_articles和预算使用，不含全部跨存储完成证明。**必须把文件所属启动时间与当前调用对应，mtime最新也可能属于上一批。**

本次最新文件是 `batch_timeout_metrics_20261005_020004.json`，mtime为Oct4 16:46 Halifax，早于19:01当前启动。该文件completed=1、timed_out=1、not_started=60；不是当前52候选批次回执。本轮尚未见对应最终metrics，状态保持RUNNING/完成未知。

### 3. 确实成功入库的记录

只读打开 `/root/OmniGraph-Vault/data/kol_scan.db`，查询 `ingestions`，不执行ingest脚本。可用Python sqlite3的 `file:/root/OmniGraph-Vault/data/kol_scan.db?mode=ro` URI。先核schema与时区。

本机默认列是 `ingested_at DEFAULT datetime('now','localtime')`，实测DB localtime为UTC+8（北京时间）。因此本次Halifax Oct4 19:01:10对应数据库Oct5 06:01:10：

```sql
SELECT source, status, COUNT(*) AS n,
       MIN(ingested_at) AS first_at, MAX(ingested_at) AS last_at
FROM ingestions
WHERE ingested_at >= '2026-10-05 06:01:10'
GROUP BY source, status;
```

每次替换为该调用的真实开始时间，不能复制一个永不过期的起点。表是状态记录而非完整事件流水；若后续处理替换记录，不能用它重建所有历史尝试。新增status=ok可确认至少有对应成功记录；整批完成仍需同调用终态与批次回执。图/SQL不一致时保留两份证据，不以某个Completed日志覆盖failed行。

## 负责人及下一动作

上述扫描和入库问题属于已批准总计划的Ingestion轨道，尚未关闭。当前内容子主控只在执行K2忠实译稿接缝，不负责这些生产故障；不能说它正在修扫描或超时。

下一只读动作：对齐当前Invocation的最终metrics和ingestions结果，随后针对首个failed行定位业务返回值/错误记录；微信取得5个request_failed的更细错误来源，RSS按已有失败类型定位源配置或网络。不要为获取证据重跑收费任务、恢复disabled服务或扩大扫描预算。此报告没有授权新的修复或代替原工单验收。

主控已收到这次告警。主控本地任务ID为 `01a0d392-693f-72d2-8fba-71b01d0642e4`，内容子主控为 `01a1081a-5053-7d72-99d5-7df90eb45f15`。若Dot有已授权线程访问工具，可使用原生线程读取/发消息；缺少Codex CLI不等于不能巡检，也不应触发安装CLI或复制凭据。若Dot的线程工具/权限确实不可用，应报告“协调通道不可用”，不要声称已通知主控。
