# VitaX 单篇隔离前置（VX-001）

**记录时间：** 2026-09-09（本地只读检查与 OHPC SSH 实测）  
**范围：** `/Users/hai/Projects/ohpc-migration/VitaX`；仅 embedding `:7997`、运行边界候选及 Hermes/OHPC Python 路径。  
**未执行：** LLM、Qdrant、采集、数据库读取、`.env`/凭据读取、服务操作、远端写入、容器启动或安装。

## STATUS

**PARTIAL — OHPC 无本地 embedding 服务；旧云存在可复用的受管 embedding 服务。shape/finite 尚未获得有效证据。**

- 每次 SSH 均先断言 `hostname=OH-Desktop`；本次两次检查都通过。
- 本机（Mac）与 OHPC 都没有 TCP `:7997` listener；OHPC 因此没有发送 HTTP embedding 请求，避免对已知未监听端口进行无效重试。
- OHPC 未找到 `embed-server.service`（user 与 system scope 均为 `LoadState=not-found`）、命名为 embedding/BGE/uvicorn/gunicorn 的进程，或 `:7997/:8000/:8001/:8080/:8766` 的候选监听。故不存在 OHPC 本地的 embedding 进程归属或替代监听端口。

## EVIDENCE

### 代码合同

- [`lib/models.py`](../../../lib/models.py) `EMBEDDING_MODEL = "bge-m3"`、`EMBEDDING_DIM = 1024`（17–19）。
- [`lib/lightrag_embedding.py`](../../../lib/lightrag_embedding.py) `_embed_local()`（222–246）在 `OMNIGRAPH_LOCAL_EMBED=1` 时，POST `OMNIGRAPH_LOCAL_EMBED_URL`，默认 `http://localhost:7997/embeddings`，请求模型为 `BAAI/bge-m3`；`_embed()`（249–257）由该标志选择本地路径。
- [`deploy/aliyun/systemd/omni-kb-api.service.d/embed.conf`](../../../deploy/aliyun/systemd/omni-kb-api.service.d/embed.conf) 是阿里云部署合同：设置 `OMNIGRAPH_LOCAL_EMBED=1` 与 `http://localhost:7997/embeddings`。它不证明 OHPC 当前存在该服务。
- [`docs/deployments/2026-09-09-second-wave/VX001.md`](../2026-09-09-second-wave/VX001.md) 规定单篇 E2E 使用显式 `nanovectordb`，并明确说明 `OMNIGRAPH_LOAD_ENV=0` 不会清除继承凭据或阻断网络出口。

### 当次现场

| 检查 | 结果 |
| --- | --- |
| Mac `lsof -iTCP:7997 -sTCP:LISTEN` | 无 listener；无 VitaX embedding 进程归属。 |
| OHPC 主机身份 | `OH-Desktop`，两次 SSH 均先验证。 |
| OHPC `lsof -iTCP:7997 -sTCP:LISTEN` | 无 listener。 |
| OHPC `embed-server.service` | user/system 均 `LoadState=not-found`、`MainPID=0`。 |
| OHPC 命名进程及候选端口 | 无 embedding/BGE/uvicorn/gunicorn 进程；候选端口无监听。 |
| HTTP shape/finite probe | **未发送**：监听缺失是首个决定性事实；不重试。若服务后续可用，唯一允许的短句请求应只断言 `data` 为 1 项、`embedding` 长度为 1024、元素均为 finite，且不得输出向量。 |
| OHPC Python 入口 | `/home/sztimhdd/OmniGraph-Vault/venv/bin/python` 存在，`Python 3.12.3`；其解释器链接为 `/usr/bin/python3.12`。 |

### 旧云服务复用（本次扩展）

- OHPC 使用现有 SSH 配置 `aliyun-old`（同义别名 `vitaclaw-aliyun`）：`HostName 47.117.244.253`、`User root`、`IdentityFile ~/.ssh/vitaclaw_aliyun_ed25519`。未读取私钥内容。
- OHPC 以 `BatchMode=yes` 连接后确认旧云 `hostname=iZj1imk39yc55iZ`。
- 旧云 `:7997` 当前为 `python` PID `2002587`、PPID `1`、用户 `root`，监听 `*:7997`；可执行文件 `/usr/bin/python3.10`，cwd `/root/OmniGraph-Vault`，cgroup `system.slice/embed-server.service`。
- 首次短合成句 POST 已发往旧云回环 `http://127.0.0.1:7997/embeddings`。嵌套远端 shell 的引号错误使本地 JSON parser 在读取响应前报 `SyntaxError`，curl 随后报写入 destination 失败。没有输出向量、凭据或响应正文，也没有重试；该首次结果不能证明 `1×1024` 或 finite。
- 经本次明确授权纠正后，使用本地编译的纯 Python `urllib`/`json`/`math` 探测脚本，经 `subprocess` argv 和 SSH stdin 在旧云执行一次 POST；OHPC 与旧云均先断言 hostname。唯一输出为 `status=200 rows=1 dim=1024 finite=true`。未写入远端文件，未输出向量、响应正文或凭据。

若后续主控授权临时 loopback tunnel，可在 **OHPC** 上使用下列可审计命令（本次未执行）：

```bash
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:17997:127.0.0.1:7997 aliyun-old
```

该命令复用旧云既有服务，仅绑定 OHPC loopback；调用端应显式使用 `http://127.0.0.1:17997/embeddings`，避免未来 OHPC 本地 `:7997` 冲突。它不是 sandbox，也不会替代实际文件系统和网络隔离。

### 原生隔离候选

| 主机 | `bwrap` | `unshare` | 容器 CLI | 结论 |
| --- | --- | --- | --- | --- |
| Mac | absent | absent | `/opt/homebrew/bin/docker` | 没有已验证的原生进程/网络隔离器。 |
| OHPC | absent | `/usr/bin/unshare`（仅 `--help`） | `/usr/bin/docker`（仅 `--help`） | 有候选二进制，但未验证权限、namespace/mount/network 效果，不能称为 sandbox。 |

未启动容器、未调用容器状态，也未运行 `unshare`；以上仅为 `command -v` / `--help` 证据。

## 最小可行运行边界

在当前事实下，OHPC 本地 embedding 缺失；旧云已通过一次有效的 `1×1024` finite 探测。若将该服务以经授权的临时 loopback tunnel 提供给 OHPC，运行边界至少应同时满足：

1. 使用新建且经路径与 symlink 检查的受控目录；将 `OMNIGRAPH_BASE_DIR`、`RAG_WORKING_DIR`、`OMNIGRAPH_CHECKPOINT_BASE_DIR`、`KOL_SCAN_DB_PATH` 指向该目录。
2. 显式 `OMNIGRAPH_LOAD_ENV=0`、`OMNIGRAPH_VECTOR_STORAGE=nanovectordb`，并在启动前清理不需要的继承凭据；这些变量只参与应用路径选择，**不构成文件系统或网络 sandbox**。
3. **尚未实现且本轮不主张**由隔离运行时强制限制文件系统或网络；OHPC 的 `unshare`/Docker 目前仅是候选，尚无可复用的隔离证明，也不是此 trusted probe 的前置条件。
4. 提供独立或经批准的 BGE-M3 服务后，先执行一次不输出向量的 1×1024 finite 探测，再允许单篇流程。本次纠正探测证明旧云端点的输出合同，不证明 tunnel、隔离目录或单篇流程已通过。

### 本轮主控选择的代码级边界

本轮主控选择经过审阅的固定合成 runner、候选代码目录及启动前的继承环境清理，作为**限定授权的 trusted probe** 边界。该选择不要求构建通用内核 sandbox。

- runner 仅处理固定合成输入，并使用受控候选代码目录；不把运行时默认目录当作可写目标。
- 代码在导入业务模块前显式设置隔离路径变量、`OMNIGRAPH_LOAD_ENV=0`，并清理本次不需要的继承环境项。
- 这不是文件系统或网络的内核强制隔离：该 probe 仍依赖网络（旧云 embedding）和文件写入。环境变量、候选目录与进程约定不构成 sandbox。
- `bwrap` 缺失，`unshare`/Docker 仅发现候选二进制且未验证；本轮不主张、更不声称存在可用隔离运行时。

### LightRAG 1.4.15 与 Hermes CLI 静态证据

以下为 OHPC 已安装源码的只读检查；未 import 业务模块或发起模型请求。

- `lightrag-hku` 的 `METADATA:3` 为 `Version: 1.4.15`。
- `/home/sztimhdd/OmniGraph-Vault/venv/lib/python3.12/site-packages/lightrag/base.py:132-136` 的 `QueryParam` 有 `hl_keywords` 与 `ll_keywords`。
- `.../lightrag/operate.py:3374-3396` 的 `get_keywords_from_query()` 在任一预设关键词非空时直接返回；`.../operate.py:3253-3257` 的 `only_need_context=True` 在最终 LLM 调用前返回 context。因此 local probe 要避免关键词与最终回答 LLM，应同时传非空 `ll_keywords` 与 `only_need_context=True`。
- `.../lightrag/lightrag.py:3159-3221` 的 `aget_docs_by_ids()` 返回 `{doc_id: DocProcessingStatus}`，省略未找到的 ID；`.../lightrag/base.py:763-805` 的 `DocProcessingStatus` 是包含 `status`、摘要、长度、路径、时间、chunk、error 与 metadata 的 dataclass。
- `/home/sztimhdd/OmniGraph-Vault/ingest_wechat.py:440` 调用 `await rag.initialize_storages()`；`.../lightrag/lightrag.py:757` 的初始化函数定向扫描没有 stdout `print()`，仅使用 logger。
- OHPC 与本机的 `~/.hermes/hermes-agent/toolsets.py` 均在 `:128` 定义 `bot_room = _ts(...)`；`_ts` 在 `:49-51` 默认 `tools=()`、`includes=()` 并转换为列表。因此当前静态值为 `tools=[]`、`includes=[]`，不是 `includes=["source"]`。

## RISKS

- 历史部署档案记录过其它环境的 `:7997` 服务和 1×1024 输出；这不是 OHPC 当前服务存在的证据。旧云实时 listener 也不等于 OHPC 已拥有 tunnel 或隔离边界。
- 仅设置环境变量不能隔离 inherited credentials、网络出口或共享运行时数据。
- 将 OHPC Docker 或 `unshare` 直接用于执行，可能需要创建 namespace/container 或挂载，超出本次“只 help/command-v、不启动/不改服务”范围；本轮 trusted probe 不将它们列为前置条件或已实现防护。

## NEXT

在主控后续授权临时 tunnel 后，独立验证 tunnel 的回环绑定、固定 runner 的路径落点和实际写入范围。不得从本文件推断单篇 E2E、生产服务或正式 UAT 已通过。
