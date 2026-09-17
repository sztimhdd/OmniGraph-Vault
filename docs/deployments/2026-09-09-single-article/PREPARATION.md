# VitaX 单篇真实执行准备（VX-001）

**记录时间：** 2026-09-09  
**范围：** 只创建 OHPC 的唯一隔离候选源副本，并验证可关闭的临时 embedding 隧道。未执行 ingest、LLM、业务模块 import、服务修改或生产数据写入。

## STATUS

**PASS — 已为同一 agent 的后续 execute 建立受控候选；临时隧道已关闭。**

## Candidate

- 路径：`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq`
- 权限和所有者：候选根及 `code/`、`runs/`、`logs/` 为 `0700 sztimhdd`。
- 内容：从 `/home/sztimhdd/OmniGraph-Vault` 只读复制根目录 `*.py` 与 `lib/`、`spiders/`、`enrichment/`、`omnigraph_search/`、`kb/` 中的 `*.py`；共 122 个文件。
- 拒绝项：复制前检查了这七个来源路径及其内部 Python 源文件，没有接受 symlink；没有复制 `.env`、runtime 数据、wiki 正文、模型、venv 或 `.git`。
- 清单：`logs/source-sha256.txt`，SHA-256 为 `22c573426f5875ba6fecf994fc0fe4338015e09f35b72a47c8ffd6fca309f3e2`。

## Hash gate

来源为 [`../2026-09-09-second-wave/VX001.md`](../2026-09-09-second-wave/VX001.md)：

| 文件 | 预期 SHA-256 | OHPC 复制前 SHA-256 | 结果 |
| --- | --- | --- | --- |
| `ingest_wechat.py` | `79c8e972283e640b14cfe90fd433e3e6564214a9eda42f214fff9af88b39ee5e` | `79c8e972283e640b14cfe90fd433e3e6564214a9eda42f214fff9af88b39ee5e` | 一致 |
| `batch_ingest_from_spider.py` | `e01b92537eb5ff07529c9ad8227d845f0cdf5b0dd036fa8ddc557d4cbcc73fdf` | `e01b92537eb5ff07529c9ad8227d845f0cdf5b0dd036fa8ddc557d4cbcc73fdf` | 一致 |

任一门禁变化均应停止审阅，不得继续 execute。

## Temporary embedding tunnel

- OHPC SSH 断言：`hostname=OH-Desktop`。
- 旧云确认：经 OHPC 的 `aliyun-old` SSH 连接，`hostname=iZj1imk39yc55iZ`。
- control socket（已移除）：`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/c`
- 历史 tunnel PID：`118127`（已通过 control command 退出）。
- 所有者：`sztimhdd`。
- 转发：`127.0.0.1:17997` → `aliyun-old:127.0.0.1:7997`，以 `BatchMode=yes`、`ExitOnForwardFailure=yes` 启动。
- 合成请求：仅使用生产 venv 的标准库 `urllib`/`json`/`math`，不 import 业务模块；输出为 `status=200 rows=1 dim=1024 finite=true`，未输出向量或响应正文。
- 记录：`logs/tunnel-evidence.txt`。

准确关闭命令（已执行）：

```bash
ssh -S /home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/c -O exit aliyun-old
```

最终只读检查确认 control socket 不存在，且 OHPC `127.0.0.1:17997` 无 listener。

## Boundaries for subsequent execute

后续同一 agent 只能在该 candidate 的 `runs/`、`logs/` 与隔离运行状态路径中工作。不得复用本地正在修的 runner，不得在未重新建立并验证隧道时访问 embedding，也不得据此记录主张正式 E2E、生产健康或部署已通过。
