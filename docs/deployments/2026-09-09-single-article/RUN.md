# VitaX 单篇 fixed trusted probe（VX-001）

**执行时间：** 2026-09-09  
**执行范围：** 已授权的固定合成文本 probe。未变更 OHPC 生产目录、生产 runtime 数据或服务；未安装依赖、修改代码、重试模型请求或输出认证信息。

## STATUS

**[COMPUTED] READY_FOR_REVIEW — runner 退出码为 `0`，receipt 状态为 `READY_FOR_REVIEW`。**

## Execution evidence

- [COMPUTED] Candidate：`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq`。
- [COMPUTED] Run：`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-single-article-lao1z1rb`。
- [COMPUTED] 4 个覆盖文件在 OHPC 逐项 SHA-256 匹配授权值：runner、`config.py`、`lib/llm_complete.py`、`lib/llm_hermes.py`。
- [COMPUTED] OHPC 为 `OH-Desktop`，旧云为 `iZj1imk39yc55iZ`；临时 loopback `127.0.0.1:17997` 隧道以 `BatchMode=yes` 和 `ExitOnForwardFailure=yes` 建立。
- [COMPUTED] fixed runner 在 candidate `code/` cwd，以 `/home/sztimhdd/OmniGraph-Vault/venv/bin/python`、`env -i PATH=/usr/bin:/bin LANG=C.UTF-8` 和外层 1200 秒 timeout 执行。
- [COMPUTED] 两次入库后的 fresh reader 均为 PASS：`processed=true`、`error_free=true`、`degraded=false`、`target_chunk_count=1`、`graph_entities=8`、`graph_relationships=8`、正文和 context marker 均存在。
- [COMPUTED] 两个 fresh reader 的 `fresh_reader_llm_calls=0`；实际 completion 为 canonicalization `2` 加 extraction `2`，低于最大值 `12`。
- [COMPUTED] stdout/stderr 仅保留在 candidate `logs/probe-exec.stdout.log` 与 `logs/probe-exec.stderr.log`；本记录未复制其原始内容。
- [COMPUTED] control socket 与 `127.0.0.1:17997` listener 均已释放。

字段级脱敏 receipt 见 [RECEIPT_REDACTED.json](RECEIPT_REDACTED.json)。原始 receipt 与运行日志仍仅位于 candidate 的受控目录。

## Boundaries

- [KNOWN] 本结果只证明已授权的固定合成 trusted probe；不构成生产部署、生产健康或正式 UAT 结论。
- [KNOWN] 后续动作须由主控根据该 receipt 另行决定；不得自动重跑或复用已关闭的 embedding 隧道。

## Controller acceptance

[KNOWN] 主控接受固定合成缓存文本的图入库、持久化、重新打开检索与目标图规模不增生证据。独立复核见 [ACCEPTANCE.md](ACCEPTANCE.md)，离线84项回归见 [OFFLINE-REGRESSION.md](OFFLINE-REGRESSION.md)。额外 dup-* failed 状态是已装 LightRAG 对重复提交的诊断，原始唯一文档仍为 processed；不宣称状态库全干净，也不删除该证据。临时embedding路径复用旧云，尚非PC独立生产链路。
