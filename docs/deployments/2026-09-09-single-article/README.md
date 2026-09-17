# VitaX 单篇合成文本图入库候选

## 当前状态

2026-09-09 更新：已在 OHPC 候选实际执行，固定合成文本双入库与新进程读取均通过，详见 [RUN.md](RUN.md)。下方保留实跑前候选说明；离线状态段为历史记录。

**OFFLINE TDD ONLY.** 本目录和 `scripts/vitax_single_article_probe.py` 只构成主控审核候选。当前轮未 SSH、未调用 Hermes、未调用 embedding、未创建隧道、未读取凭据、未写入 OHPC。

离线入口默认不导入 `ingest_wechat`，不执行模型或网络调用。只有明确给出 `--execute` 才会进入真实路径；该参数留待主控复核并另行授权。

## 最小隔离合同

每次运行在一个已有、非 symlink 的受控父目录下创建唯一 `vitax-single-article-*` 目录。四项路径全部位于该目录：

| 用途 | 变量 | 路径 |
| --- | --- | --- |
| 基础文件、图片、entity buffer | `OMNIGRAPH_BASE_DIR` | `run/base` |
| LightRAG 状态 | `RAG_WORKING_DIR` | `run/rag` |
| checkpoint | `OMNIGRAPH_CHECKPOINT_BASE_DIR` | `run/base` |
| SQLite | `KOL_SCAN_DB_PATH` | `run/base/kol_scan.db` |

运行环境不是继承环境。实际执行进程仅设置 `PATH=/usr/bin:/bin`、`LANG=C.UTF-8` 与下列业务 allowlist：`OMNIGRAPH_LOAD_ENV=0`、四项路径、`OMNIGRAPH_VECTOR_STORAGE=nanovectordb`、`OMNIGRAPH_LLM_PROVIDER=hermes`、显式 `OMNIGRAPH_HERMES_BIN`、`OMNIGRAPH_LOCAL_EMBED=1`、显式 `OMNIGRAPH_LOCAL_EMBED_URL`、`ENRICHMENT_ENABLED=0`。

这是代码级路径和环境边界，不是 sandbox、容器、网络命名空间或内核隔离。runner 仅避免自己的业务写入默认 runtime 路径，并以缓存正文避开抓取、图片和 async vision 分支。它不拦截 Python 依赖的任意网络行为，也不约束已审 Hermes binary：adapter 会按现有实现创建临时 `fresh` 工作目录和 usage 文件，并调用 Hermes 的既有 session/config 行为；这些写入不属于 runner 的隔离保证。

embedding URL 必须由主控显式传入一个受控 loopback `/embeddings` 端点。现场已确认旧云 `:7997` 正在监听，且 OHPC 可使用 BatchMode 访问 `aliyun-old`；后续授权时可建立临时转发并传入 `http://127.0.0.1:17997/embeddings`。runner 不使用默认 `:7997`，不启动 embedding 服务，也不建立隧道。

合成正文写成隔离图片目录中的 `final_content.md`，因此复用 `ingest_wechat.ingest_article()` 的缓存路径：无抓取、无图片、无分类调用、无翻译和无 async vision。该路径仍会真实调用 `extract_entities()`；当前源码经 `get_llm_func()` 获取 callback。LightRAG 抽取也经同一个显式 Hermes callback。runner 只包装 callback 计数，不替换或 fake 真实调用。

## 真实执行前的复制白名单

候选根固定为用户可写的 `/home/sztimhdd/.local/share/vitax-probes/<unique>/`，其中 `<unique>` 是本轮新建的随机目录名；不使用 `/srv`、sudo 或生产 runtime。候选根是独立的 Python import root：命令从该目录运行，并设置 `PYTHONPATH` 为该候选根。runner 会在真实执行前拒绝 `config`、`ingest_wechat`、`image_pipeline` 或 `lib.*` 已存在于长寿命进程的 `sys.modules`，且导入后逐一断言这些项目模块位于候选根；缺少文件而回退到生产 checkout 会失败。

以下是从 OHPC 只读复制到候选根的最小已核源码范围。不得复制 `.env`、数据库、图片、浏览器 profile、模型、运行时 state 或整个工作树：

1. `scripts/vitax_single_article_probe.py`
2. `config.py`、`ingest_wechat.py`、`image_pipeline.py`
3. `lib/__init__.py`、`lib/models.py`、`lib/api_keys.py`、`lib/rate_limit.py`、`lib/llm_client.py`
4. `lib/lightrag_embedding.py`、`lib/llm_cache_embedding_global.py`、`lib/lightrag_queue_probe.py`、`lib/checkpoint.py`、`lib/vision_tracking.py`、`lib/vision_cascade.py`
5. 已审 overlay：`lib/llm_complete.py`（含 Hermes dispatcher 分支）和 `lib/llm_hermes.py`

执行前主控应重新比较 VX-001 中记录的 `ingest_wechat.py` SHA-256；不相同则停止并审阅漂移。该清单是候选 import 闭包，不构成整树覆盖许可。

## 候选命令（不得在本轮执行）

以下命令是供主控审核、逐项替换绝对路径后使用的精确候选。`/srv/vitax-single-article` 必须是新建的受控目录，不得是 `/tmp`、home、生产 runtime 或 symlink；`17997` 必须在执行前由主控验证为既有、受控的 loopback BGE-M3 隧道。

```bash
cd /home/sztimhdd/.local/share/vitax-probes/<unique> && \
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONPATH="$PWD" \
  /home/sztimhdd/OmniGraph-Vault/venv/bin/python \
  scripts/vitax_single_article_probe.py \
  --parent "$PWD/runs" \
  --hermes-bin /absolute/path/to/hermes \
  --embedding-url http://127.0.0.1:17997/embeddings \
  --execute
```

`--execute` 的完整运行预算是最多 12 次 Hermes completion；单次 callback timeout 是 adapter 的 180 秒，外层 fresh-reader timeout 是 20 分钟。它们是 fail-closed 上限，不是耗时保证。reader 预置非空 `hl_keywords` 和 `ll_keywords`，并把 reader 的 LLM callback 设为一调用即失败的 guard；因此 reader 不能消耗 Hermes 预算。超出、adapter 路由不匹配、embedding 不可达、任一次实际 `rag.ainsert` 异常或任何持久化断言失败都应保留 receipt 后返回失败，不扩大预算或改 provider。

## 接受证据

每次 `finalize_storages()` 后，runner 以新的 Python 进程重新打开 `get_rag(flush=True)`，并只在以下事实同时满足时给出 `READY_FOR_REVIEW`：

1. 目标 doc ID 的持久状态为 `processed`，且没有 `error_msg`。
2. 隔离 checkpoint 不存在 `degraded.json`。
3. 目标 full-doc 对应至少一个 chunk；`graph_chunk_entity_relation.graphml` 的实体节点和关系边各自的 `source_id` 都包含其中一个目标 chunk ID。
4. `kv_store_full_docs.json` 含合成正文 marker。
5. fresh reader 的 `aquery(..., QueryParam(mode="local", only_need_context=True, hl_keywords=..., ll_keywords=...))` 上下文含同一 marker，且 guard 未发生调用。
6. 第二次缓存路径重跑后的 graph 节点数和边数与第一次相同。

缓存入口打印的成功文字及其 `None` 返回值不构成任何验收证据。

## 离线验证

```bash
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_vitax_single_article_probe.py -q
```
