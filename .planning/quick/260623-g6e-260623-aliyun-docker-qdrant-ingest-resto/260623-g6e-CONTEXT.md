# Quick Task 260623-g6e: Aliyun Docker+Qdrant ingest restore - Context

**Gathered:** 2026-06-23 (22:40 CST)
**Status:** Ready for planning
**Mode:** --discuss --full (operator = agent, SSH alias `aliyun-vitaclaw`, Principle #5)

<domain>
## Task Boundary

修复阿里云实例 `iZj1imk39yc55iZ`(EIP 47.117.244.253,cn-shanghai)的知识图谱 ingest 7-天 restart-loop。
根因:6/17 重建实例时 Docker engine 漏装 → Qdrant 向量库从未启动 → 所有 ingest 在
`ainsert` 阶段以 `httpx.ConnectError: [Errno 111] Connection refused` 失败。

**In scope:** 装 docker-ce engine → 启动 Qdrant 容器(复用现存数据,`--restart=unless-stopped`)
→ stop restart-loop → 端到端验证(curl/collection count/ingest 1+ 篇/long_form 烟测)→ prune 死镜像层。

**Out of scope (勿碰):** cookie 自愈链(已验证有效 6/22死→6/23恢复20账号);KOL 扫描/采集
(不受影响,文章照常进 SQLite);从 SQLite 全量重建图谱(决策 = 复用)。
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not revisit)

### Docker 恢复路径 (resolved by diagnostic, NOT a wipe)
**诊断已定论:这是 half-install,不是装坏。** 证据:
- `dpkg -l`: `containerd.io` (官方) = **`ii` 已装**;`containerd.service` **active/running since 6/18**
- `docker.io` (Ubuntu pkg) = `rc`(removed,configs 残留);`docker-ce`/`docker-ce-cli` = **从未安装**
- `/etc/apt/sources.list.d/docker.list` 存在(6/18),官方源 `mirrors.aliyun.com/docker-ce` 已配
- `apt-cache policy docker-ce`: Candidate `5:29.6.0-1~ubuntu.22.04~jammy` available

**决策:** 干净 `apt-get install docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin`。
**不 wipe** `/var/lib/docker` 或 `/var/lib/containerd`(containerd 在跑,wipe 会破坏)。
docker-ce 会接管现有 containerd.io 作为 runtime。装后 `systemctl enable --now docker`。

### Qdrant 数据:复用 6/16 现存 collection ✅
- `/var/lib/qdrant/collections/` 有 3 个 collection,**最后写入 6/16 08:00**(非报告说的 6/2):
  - `lightrag_vdb_chunks_gemini_embedding_2_3072d`
  - `lightrag_vdb_entities_gemini_embedding_2_3072d`
  - `lightrag_vdb_relationships_gemini_embedding_2_3072d`
- collection 命名后缀 `_gemini_embedding_2_3072d` 符合约定(memory `omnigraph_qdrant_collection_naming`)
- 1.9G 总量 + `raft_state.json` + `aliases/`
- **决策:启动容器挂载现存 `/var/lib/qdrant`,不 wipe、不 reingest。** 只缺 6/17→今 ~1 周新文章,走 cron 自然补。
- 全量重建被否决理由:重嵌 ~60K 实体,2 个 embedding key × 1000 RPD ≈ 30 天配额,短期不可行 + 丢现有图谱。

### Qdrant 容器启动recipe (来自 INVENTORY.md:179-182,权威)
```bash
docker run -d --name qdrant --restart=unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v /var/lib/qdrant:/qdrant/storage \
  qdrant/qdrant:v1.11.0
```
- **必须 `--restart=unless-stopped`**(memory `qdrant_docker_no_restart_policy_trap` + INVENTORY.md:337
  "6/7 outage 35h Qdrant down 因为没 restart policy")
- **DO NOT** wipe `/var/lib/qdrant`(那是 Section-0 全量重建路径,本次复用故跳过)
- 镜像 `qdrant/qdrant:v1.11.0`:本地可能无,需 `docker pull`(阿里云能访问 docker hub 镜像源)。
  INVENTORY.md:350 注:tag 未存于 backup,默认 v1.11.0;若 collection config.json version 不匹配再问 user。
  执行时先 `grep version /var/lib/qdrant/collections/*/config.json` 确认兼容。

### 积压 197 篇:只靠 cron 自然消化 ✅
- daily-ingest 日志显示 **197 articles to process**;restart 计数器 = **351**(每 10min 烧一次)
- **决策:不做大 catch-up 批。** 验证用的「手动跑一次 ingest」= 跑现有 `omnigraph-daily-ingest`
  单元一次(它 `--max-articles 5` 上限),这 5 篇算进自然 drain,之后 cron(5篇×3次/天)继续消化 197。
- ~13 天自然 drain 完。long_form 最近一周内容补得慢但可接受。

### 磁盘清理:docker 起来后 prune 死层 ✅
- `df -h /`: 99G / 80G used / **15G avail / 85%**
- `/var/lib/containerd`: **23G**(`io.containerd.snapshotter.v1.overlayfs` = 19G 孤儿镜像层
  + `content.v1.content` = 4.5G)。这是旧 k8s/containerd 镜像残留,docker 不会自动接管复用。
- **决策:装好 docker + Qdrant 跑起来验证通过后,跑 `docker system prune -a -f`** 回收孤儿层。
  目标 85% → ~65%。不影响 Qdrant(独立卷 `/var/lib/qdrant`)。
- ⚠️ 顺序:**prune 放在验证 PASS 之后**,避免清到正在用的层。先确认 Qdrant 容器健康再清。

### restart-loop 处理(动手前第一步)
- `omnigraph-daily-ingest.service` 当前 `activating (auto-restart)`,`Restart=on-failure RestartSec=10min`
- **决策:改动前先 `systemctl stop omnigraph-daily-ingest`** 停止烧 CPU + 避免修复期间干扰。
- afternoon/evening-ingest 当前 `dead`(timer 触发型,Conflicts= 互斥),无需单独 stop,但确认不会在修复窗口触发
  (下次 evening 20:00 CST,afternoon 14:00 CST — 修复窗口外,但稳妥可临时 stop timer 或快速完成)。

### Claude's Discretion
- docker-ce 具体版本:用 apt candidate(5:29.6.0),不 pin。
- Qdrant 镜像拉取源:用阿里云默认 docker daemon 配置;若 docker hub 不通,fallback `registry.cn-hangzhou.aliyuncs.com` 镜像或离线 load(INVENTORY.md:312 有 save/load 路径)。
- 验证 long_form 烟测的具体 query 措辞:agent 自选一个能命中最近文章的查询。
</decisions>

<specifics>
## Specific Ideas / 关键路径

- SSH: alias `aliyun-vitaclaw`(已指向新 EIP);env 加载 `set -a; source /root/.hermes/.env; set +a`
  (memory `aliyun_ssh_manual_trigger_env`:手动触发不继承 systemd EnvironmentFile,否则 DEEPSEEK_API_KEY=dummy 静默 401)
- 时区:**CST 标注**(memory `timezone_drift_adt_vs_cst`:Aliyun=CST UTC+8,user local=ADT UTC-3,11h delta)
- 权威 recipe 文件:`/root/OmniGraph-Vault/INVENTORY.md` Section(docker run line 179-182)
- ingest 入口:`venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 5`(daily-ingest unit ExecStart)
- env: `OMNIGRAPH_VECTOR_STORAGE=qdrant`, `QDRANT_URL=http://127.0.0.1:6333`, `EMBEDDING_MODEL=gemini-embedding-2`
- qdrant-snapshot.service (oneshot) 有 `Requires=docker.service` — docker 装好后这个也会恢复可用
</specifics>

<canonical_refs>
## Canonical References

- `/root/OmniGraph-Vault/INVENTORY.md` (line 179-182 docker run recipe; 337/350/352 caveats + rollback)
- memory `qdrant_docker_no_restart_policy_trap` — 必须 --restart=unless-stopped
- memory `omnigraph_qdrant_collection_naming` — collection 后缀 `_<embed_model>_<dim>d`
- memory `aliyun_vitaclaw_ssh` — SSH alias + env source 法
- memory `aliyun_ssh_manual_trigger_env` — 手动触发需 source .env
- memory `timezone_drift_adt_vs_cst` — CST 标注
- `/root/.hermes/omonigraph-vault/README.qdrant-migration.txt` — L1 rollback path (env-flip nanovectordb)
</canonical_refs>

<verification>
## 验证标准 (Principle #6,端到端真实 — planner 转为 must_haves)

1. `docker version` + `systemctl is-active docker` = active;`docker ps` 显示 qdrant 容器 Up
2. `curl -sf localhost:6333/healthz` 通(或 `/readyz`)
3. `curl localhost:6333/collections` 列出 3 个 collection;`/collections/<chunks>` count 合理(>0,匹配 6/16 数据)
4. Qdrant 容器 `docker inspect` RestartPolicy = `unless-stopped`
5. 手动跑 `systemctl start omnigraph-daily-ingest` 一次 → journalctl **无 Connection refused** → 实际灌进 ≥1 篇 → chunks count 增加(前后对比)
6. restart-loop 停止:`systemctl status omnigraph-daily-ingest` 不再 `activating/auto-restart`,restart 计数器不再增长
7. long_form RAG 烟测:一个查询命中最近文章(证明图谱真的能检索)
8. 磁盘 prune 后 `df -h /` 使用率下降(85% → 目标 <70%)
</verification>
