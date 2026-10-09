# 独立技术 review 回执

日期：2026-10-09。中文表述按 asd-ste100 Strict 清晰原则整理，不声明正式 STE 合规。Sol 负责工程裁决。

## STATUS

MVP03、MVP05 和 producer wrapper 新增 FTS/media 步骤，在本次检查范围内无阻塞缺陷。该结论不等于整批变更或远端部署验收通过。

MVP06 的 P1 已修复并通过窄复核。03、05、06 和 wrapper 在本次检查范围内均无未关闭的阻塞缺陷。Sol 负责部署工程裁决。

## CHANGES

本 review 只读检查代码，并按主控请求写入本回执。未改代码、安装依赖、执行 SSH、启动服务、调用业务模型或派生子代理。首轮 seam 测试的两个合成 checkpoint 副作用已由主控归档；最终五例 seam 使用隔离的临时根，详见 RISKS。

检查版本：

| 范围 | 文件 | SHA-256 |
|---|---|---|
| wrapper | `/Users/hai/Projects/ohpc-migration/VitaX/deploy/vitax-producer/producer` | `7f18ba113bf7d02dbd9382eb338dbf47437c4785e2ccef887c188f91cee6cf06` |
| MVP03 | `/Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX/lib/scraper.py` | `235d7e7a5d6de818f037a3927332f5253fd11554ac9515ad77fc21f83ae9497a` |
| MVP05 | `/Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX/vitax/production.py` | `e2b52bb87006ce4fbe45c5de0db8b0abb66a428e8dba290be718c24881514ca2` |

各文件均与本目录 `before/` 下的对应文件比较。wrapper 位于原 repo；03/05 位于指定 worktree。

## EVIDENCE

### wrapper：路径、顺序、错误和付费入口

- `deploy/vitax-producer/producer:22-27`：顺序为一次 refresh、FTS、增量媒体同步、publish。新增步骤没有启动另一 producer。
- `producer:24`：FTS 进程显式设置 `OMNIGRAPH_REPO_ROOT=/root/OmniGraph-Vault`，并指定 `--db /root/OmniGraph-Vault/data/kol_scan.db`。旧 root 与现有原子写启动脚本的 `.pth` 路径选择一致。该覆盖仅作用于 FTS 子进程，不改变后续 publish 的 root。
- `kb/scripts/rebuild_fts.py:36-85`：复用 SQLite 查询和 FTS 写入，不调用业务模型。异常继续抛出，由进程返回非零退出码。
- `producer:25`：源为 `/root/.hermes/omonigraph-vault/images/`。尾部斜杠表示复制目录内容，目标为 `root@172.18.12.150:/root/vitax-mvp/media/`。目标与 worktree 中 `deploy/vitax-reader/vitax-reader.service:8` 的 `--images-dir` 一致。保留主机密钥检查；未使用 `--delete`。
- `producer:22-27`：失败状态不会被后续成功步骤清零。各命令的错误输出未重定向丢弃。多步骤失败时，最终退出码代表最后一次失败，各次错误仍留在日志。
- `scripts/publish_vitax_release.py:169-204`：发布路径只重启 reader；失败恢复仍只操作 reader，不调用生成入口。
- 独立离线测试：`test_publish_vitax_release.py` 与 `kb/test_rebuild_fts.py`，共 **20 passed**。
- 外部可执行替身检查：**6 种组合通过**。覆盖全成功、各步骤单独失败及连续失败。确认顺序、root 作用域、日志、非零退出码和一次 refresh。替身没有执行实际 Python 业务程序、rsync 或 SSH。
- `sh -n deploy/vitax-producer/producer` 通过。

主控提供的补充证据：FTS/publisher 相关测试 **32 PASS**；collector FTS **1816 条**并有 Codemode 命中；reader 媒体 **15512 文件**，其中新增 **7851 文件**。这些是主控报告的实测，本 reviewer 未独立复跑。本目录未找到对应原始输出，不能将其表述为本 reviewer 的独立运行证据。20 与 32 的测试范围可能重叠，不相加。

### MVP03：Sign in 正文误拒

- `lib/scraper.py:39-58`：仅移除旧列表中的裸 `Sign in`，新增 `Sign in to continue/read/view`。其余旧 marker 保留。
- `lib/scraper.py:126-142`：200 字符底线不变。没有 >=1000 字符豁免。明确 marker 不受正文长度影响。泛化 `Sign in` 仅匹配行首提示，保留 Markdown 按钮、列表、引用和标题提示检查。
- 独立离线测试：`test_scraper.py`，**10 passed**。
- 另有 **78 项离线断言通过**。覆盖 200/1000/10000 字符正文、全部明确 marker、七种行首格式，以及正文叙述从 before 的 False 变为当前 True。
- 真实博客 9855 字符样本的 False→True 来自 `MVP03.md` 实现回执；本 reviewer 未重抓该博客。

### MVP05：扁平 Wiki 适配

- `vitax/production.py:348-351`：仅新增四行适配，只在 wiki stage 生效。扁平对象继续经过原有 kind、中文正文、引用和图片检查。
- `scripts/refresh_vitax_local.py:616-638`：Wiki 失败单独捕获，成功文章仍可发布。
- 正文沿 `vitax/api.py:128` 的 `render_body()` 进入已有安全渲染路径。
- 独立离线测试：生产测试 **37 passed**；失败隔离、续跑、合并和正文安全检查 **5 passed**，有一个弃用警告。
- 内存断言：两种有效形态通过；九种跨 stage、空正文、错误引用、未知图片或夹带图谱形态被拒绝。

### MVP06：P1 已关闭

**原 P1：缓存插入失败被旧 PROCESSED 状态掩盖。最终复核通过。**

- 原触发条件：缓存重插入抛出非402异常，旧 doc_id 仍为 PROCESSED。首轮独立局部复现观察到 inner 返回 None、outer 两个成功标志均为 True。
- 最终修复：worktree `ingest_wechat.py:1290-1297` 记录缓存插入错误后立即 `raise`，不再继续读取旧状态。既有402降级 helper 未改动。
- 新回归：`tests/unit/test_mvp06_ingest_doc_seam.py:236` 覆盖“插入异常 + 旧 PROCESSED”。断言 inner 抛出原异常，outer 的 success 与 doc_confirmed 均为 False。
- 隔离复核：同文件 `:89` 的 autouse fixture 设置临时根，并覆盖已导入的 config、checkpoint、图片、实体和 DB 路径。
- 最终独立运行仅上述 seam 文件：**5 passed in 5.69s**。启动前额外设置临时 `OMNIGRAPH_BASE_DIR`、视觉 checkpoint 根和 pytest basetemp；禁用 bytecode 与 pytest cache。未扩大测试范围。
- 最终版本哈希：ingest `9ae40047d77633f6f477e8198c3478d432e5b79e753852ae4ef3ec425d950312`；seam `d080c1aadde6bdf6147e51e48f54453f04b1764d24f595f887e17243befef2ba`。

前轮已核对事项，本次未重复检查：

- inner 主函数仅两个正常返回出口：缓存分支 `:1303` 的 None，以及 fresh 分支 `:1675` 的 vision_task。抓取失败现在抛出异常。fresh 插入异常通过 finally 继续传播，未发现另一处失败 early return。
- `lib/research/stages/synthesizer.py:73-84` 仅合入 status 为 ok 的已有 WebBaseline/Verifier Source 对象。独立局部检查覆盖 ok、failed、skipped 三种状态；对象身份、URI、snippet 和提示编号保留，不创建新来源。未发现该改动虚构来源。
- `kb/api_routers/search.py:69-75` 确实调用 `kg_synthesize.synthesize_response`；两个修改后的 KG 测试 mock 对准实际入口。
- 首轮独立选择四个 seam 测试和一个新增来源测试：**5 passed**。最终复核另运行全部五例 seam，如上。
- 主控最终报告：5 seam、14 research、32 API、19 编排、11 processed_gate 通过。本 reviewer 未重跑已验证的大范围套件；19/11 使用临时 offline doubles，不是真 LightRAG 运行证据。
- 前轮核对六个文件 diff 及哈希，与当时的 `MVP06.md` 一致。outer 哈希为 `3b7460d5b3ff198452bf03b64bbc269971274cac275986a17911cb64214feb89`；synthesizer 哈希为 `ba9fa76a7b62824986ddec9a6909d30f007b85ddd2685eb1591783f708613e6b`。ingest 与 seam 的最终哈希见上。

## RISKS

- MVP03 的行首规则仍可能误拒以 `Sign in` 开头的正常叙述。这是指定规则的已知边界，不阻塞本次修复。
- 未独立检查远端当前 `.pth`、数据库、媒体、服务或部署运行状态。路径结论基于本地代码、部署配置和主控提供的证据。
- full textfirst 分支因缺依赖两次失败后已停止，本 reviewer 未重试、安装依赖或把 doubles 结果表述为真实运行。
- 首轮 seam fixture 未隔离 checkpoint 根，本 reviewer 漏查该边界，测试刷新了两个合成 metadata。主控确认已将两目录移至本目录 `test-side-effects/69da4818b3436d27/` 与 `test-side-effects/792f812a84edcd49/`，未删除用户数据。本 reviewer 只读核对归档 metadata 存在。最终 fixture 已隔离 checkpoint 根。

## NEXT

本次独立 review 完成。P1 已关闭，无需追加检查。Sol 可依据本回执裁决已检查范围的部署。

未扩大到 full textfirst、真实 LightRAG、SSH、业务模型或部署运行。无需另派 review。
