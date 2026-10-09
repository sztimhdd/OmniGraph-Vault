# VitaX 采集机 producer（MVP-05）

一个 systemd oneshot + timer：在采集机上就地跑一次有界 refresh，再把新版本发布到网站机。
取代旧 Mac 调度；同一套 producer 代码、缓存、锁和 100 元账本，不造第二套。
每轮使用 `--backfill --backfill-lane D --queue 50`，按现有队列新增优先推进历史缺口，不受每日 marker 限制。

## 文件与安装位置

| 文件 | 安装到 |
|---|---|
| `producer` | `/root/.vitax-local-automation/producer`（0700） |
| `vitax-producer.service` | `/etc/systemd/system/vitax-producer.service` |
| `vitax-producer.timer` | `/etc/systemd/system/vitax-producer.timer` |

运行用户 `root`。安装、启 timer、搬账本/缓存/服务由主控执行；本目录只提供隔离代码。

## 凭据

业务密钥只在采集机自己的 `/root/.hermes/.env`。`config.py` 默认会加载它。
**不要设置 `OMNIGRAPH_LOAD_ENV=0`**：那会让 `load_env()` 直接返回，producer 拿不到密钥
（读端 `vitax-reader` 才用 `OMNIGRAPH_LOAD_ENV=0`，因为读端不需要密钥）。

## collector 本地接缝

`scripts/refresh_vitax_local.py` 在 hostname `iZj1imk39yc55iZ` 时把原本的 SSH/scp
改为本机执行：同一段 stdlib 程序用 `/root/OmniGraph-Vault/venv-aim1/bin/python` 跑，
原库导出直接落到本地快照目录；Mac 上仍是原来的 `ssh ack-node-2` + `scp` 路径。

## 预构建 SPA

`builder` 支持受信任的显式预构建站点目录：设置 `VITAX_PREBUILT_SITE`（wrapper 默认指向
`$CODE/vitax-site/dist`，存在才用）时复制该目录，不跑 npm/prerender；不设置时保持原
build+prerender 行为。新 SPA 运行时读现有 HTTP API（`/api/release` 等），不需要 prerender。

## publish

`scripts/publish_vitax_release.py` 把 `<root>/public/current`（release）和
`<root>/library/current`（library 快照）合成一个包，经已验证的
`root@172.18.12.150`（`HostKeyAlias=47.103.73.20`、`StrictHostKeyChecking=yes`）
传到 `/root/vitax-mvp/releases/<release_id>-<articles.sqlite哈希前16位>`，在远端校验哈希与原知识 `release_id` 后原子切
`current`，只 `systemctl restart vitax-reader`；旧版本保留；stdout 一行 JSON 结果。
相同知识ID及文章库数据重复发布不重启（`changed:false`）；正文或译文更新形成新站版。
切换后检查 `/api/release` 与 `/api/library/status`；重启或 API 烟测失败时原子恢复
`previous_current`，仅重启 `vitax-reader` 并检查恢复结果。恢复失败明确报错，旧版本保留。

不复制：凭据、原库、SQLite WAL、图谱文件、整个 repo。包内只含
`public.sqlite`、`site/`、`manifest.json`、`articles.sqlite`、`receipt.json`
和可选的 `code/`（读端 `vitax` 包）。

## 部署包与离线导入检查

复用venv有 `zz_omnigraph_atomic_write.pth` 启动钩子，会在脚本运行前导入 `lib`。wrapper必须先设置 `OMNIGRAPH_REPO_ROOT="$CODE"`，否则旧仓库包会先加载，脚本调整sys.path也无效。
producer的 `lib/` 需有 `__init__.py`、`llm_deepseek.py`、`models.py`、`api_keys.py`、`rate_limit.py`、`llm_client.py`、`lightrag_embedding.py`、`llm_cache_embedding_global.py`、`lightrag_atomic_write_patch.py`。共享依赖沿用采集机已有版本，DeepSeek客户端使用本次选定版本，不替换旧仓库或凭据。

```sh
cd /root/.vitax-local-automation/producer-code
OMNIGRAPH_REPO_ROOT="$PWD" OMNIGRAPH_LOAD_ENV=0 /root/OmniGraph-Vault/venv-aim1/bin/python -c 'from pathlib import Path; import lib.llm_deepseek as m; assert Path(m.__file__).resolve() == Path.cwd()/"lib/llm_deepseek.py"; text="测试\n"*10000; assert m.assemble_chunks(m.chunk_text(text,max_chars=24000)) == text; print("import/chunks PASS")'
```

不要将运行wrapper称为干跑：它会发起业务模型调用。只检查导入、函数和自然批次摘要即可。

## 运行检查

```sh
# 只读：确认本机就路由到本地 venv（应打印 True）
/root/OmniGraph-Vault/venv-aim1/bin/python -c \
  "import sys;sys.path.insert(0,'/root/OmniGraph-Vault');from scripts.refresh_vitax_local import on_producer_host;print(on_producer_host())"
```

查看：`systemctl status vitax-producer.service vitax-producer.timer`；
`journalctl -u vitax-producer -n 50`。回退：停 timer，恢复旧 Mac 调度；读端 `current` 切回旧版本目录。

## 10/9接续

同一wrapper在refresh后调用现有免费FTS重建并用rsync增量同步采集images到reader媒体，再发布；复制失败保留错误退出码，不删除目标旧媒体，不再人工全量传包。旧omnigraph-translate.timer已禁用，正文翻译由同一Flash队列处理，已有标题译稿保留。03正文误拒与06入图成功状态窄补丁已保存备份，API源码变化须仅重载原kb-api，不改旧MCP。

## Qdrant写等待

采集机LightRAG安装包未透传client timeout，默认HTTPX读期限5秒；10/9实测服务器6–16秒后200。已用deploy/lightrag-qdrant-timeout.patch给QdrantClient增加timeout=30，upsert wait=True不变。重新安装依赖后需重应用该补丁，先备份并检查仅一参数变化；新客户端HTTPX读期限实测30，旧在途实例仍5，不重跑/杀掉旧图任务。

公网入口现为http://47.103.73.20:8767/，原生port oneshot将已放行旧MCP端口转到内部8788。旧omni-mcp disabled/inactive，旧健康8768关闭。停止vitax-reader-port.service可撤回此一条NAT规则，reader数据/服务不变。
