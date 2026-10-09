> 历史记录：只供查实现和当时结果；旧审核要求、执行限制和下一步指令已被[当前需求](../../spec/VITAX_HOBBY_PRD.md)与[批处理计划](../../superpowers/plans/2026-10-04-vitax-next-stage.md)替代。

# VitaX 内容补全执行报告

## 2026-10-04 首次 checkpoint

STATUS: RUNNING — K0/K1 首切片；K2–K4 尚未开始。

CHANGES: 新建本报告。暂未修改业务源码、运行数据或远端文件。复用现有 mirror/API；不新增 producer、费用账本或回填额度。

EVIDENCE:
- 本机 repo/shell 可用：`/Users/hai/Projects/ohpc-migration/VitaX`，zsh，HEAD `8505dbca4958944fc08b0ea5ebdf88f9051a7bfa`；大量既有 WIP 保留。
- 本机 `.venv/bin/python` 实测 Python 3.12.13。
- 首次实际动作：经既有 `ssh -o BatchMode=yes -o ConnectTimeout=10 OHPC` 只读核身份、Python、HEAD、WIP、解释器目录。退出 0，hostname `OH-Desktop`，Python 3.12.3，HEAD `dca7c772a8c95125d275ec50b2944ff00713667a`。
- 远端 WIP：`scripts/sync-from-aliyun.sh`、`scripts/wiki_evolve.py`、`tests/unit/test_wiki_w5b_bootstrap.py`，另有四份未跟踪历史文档。未修改。
- 远端 `venv`、`venv-aim1`、`.venv` 目录均存在；执行包关于 `.venv` 缺失的陈述已过时，目录存在不等于解释器可用。
- 共享 Codex 用量初检 38%；无新增数字额度、未重置。业务 LLM 调用 0，新增 DeepSeek 成本 0 元；100 元共享回填账本状态待核，不把未核余额当可支用额度。

RISKS: 已有改写稿是否匹配当前来源修订、是否完整、资源是否可用尚未核；CDP 与付费入口未验收。不得从目录或配置推断通过。现有 API 对译文已有支持，旧改写接缝须追源后裁决。

NEXT: 在 WSL 对指定 vault 与原仓数据做只读 SQLite/文件盘点，输出无正文/秘密的逐修订差额；核本地镜像和真实 API，优先一篇微信、一篇 RSS 的有效已有稿件。保持原文 hash，缺 provenance 的改写排除。K0 不等待 CDP。

## K0 执行分支重评

STATUS: 初始远端执行分支两次失败后停止；未重置失败次数、未换 worker/provider。

CHANGES: 新增标准库只读盘点 `scripts/audit_vitax_content.py` 及定向测试。第1次 stdin 包装器将 hostname 断言置于 future import 前，SyntaxError；第2次改为独立 compile 后进入盘点，真实 Markdown 图片 URL 紧接中文正文被过宽 regex 吞入路径，触发 ENAMETOOLONG。保存完整错误于隔离私有目录，报告只记录错误类别，不复制正文。

EVIDENCE: 本地合成样本准确复现第2次 OSError 的 RED；修正 URL 的 Markdown 结束边界，无法 stat 的旧资产记 uncheckable，不能误写存在或缺失。新版本含原先镜像/API 回归共 9 passed。新验证以该具体代码差异和复现证据为前置，失败历史保留。

RISKS: 资产核查仅覆盖已有 localhost:8765 引用；外部 URL 可用性尚未核。不存在以图片目录数当可读性通过的判断。

NEXT: 新版本只读运行一次；完成逐修订清单及真实译稿复用验证。

## 2026-10-04 首个 K0/K1 切片结果（Halifax 15:16 之后）

STATUS: 首个有界切片完成。K0 当前 WSL/Mac 快照盘点已执行；K1 一篇微信、一篇 RSS 的已有译稿通过既有镜像/API/浏览器实读。K1 全面排版、旧改写与媒体展示仍未完成；K2–K4 未实施。

CHANGES:
- 新增标准库盘点命令 `scripts/audit_vitax_content.py --source <database> [--assets <image-root>]` 及三项定向测试。SQLite 只读事务，不导入 config、不调用模型、不修改源库、不写远端脚本。
- K0 的逐记录/来源修订差额存在隔离目录 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-k0-k1-20261004/{WSL,Mac}-inventory.json`；只含 hash、ID、存在性/语言/缺口，无正文和凭据。摘要见 [K0-summary.json](K0-summary.json)，44 条缺原文的已有文件候选见 [K0-original-candidates.json](K0-original-candidates.json)。这不是费用账本或生产队列。
- Ponytail 裁决：原文/译文切换已经端到端存在，首切片直接复用，未新增同义 API、重生成译稿或改写原文。旧改写没有来源修订/recipe receipt，全部列为 unverified，不为凑样本强行展示。

EVIDENCE:

| 当前快照 | 原始记录 | 来源修订去重分母 | 原文字节存在（记录 / 修订） | 译文字节存在（记录 / 修订） |
|---|---:|---:|---:|---:|
| WSL vault | 10130 | 10125 | 2960 / 2955 | 1753 / 1749 |
| Mac mirror | 10430 | 10425 | 2975 / 2970 | 1803 / 1799 |

- WSL 观测 `2026-10-04T18:16:10Z`（Halifax 15:16），Mac 事务随即执行；不是同一跨机事务，也不是生产实时总量。共同来源修订 10122，WSL-only 3，Mac-only 303。按修订分母单列各覆盖项，不混加形成总体完成率；字节存在不等于全文完整或翻译忠实。
- 两快照均有 44 条译文无原文；其中 WSL 30 条在既有 images 目录发现 `final_content*.md` 候选，14 条在这两个已核路径未找到。30 条尚待源修订与完整性确认，未回写 DB、未标原文恢复；未从译文反推原文，未重抓。
- 合格且明确英文的原文修订 125，其中中文译稿字节存在 122；3 条合格英文 RSS 中文译稿缺口仍在。语言未知不纳入英文适用分母。合格超过 25000 UTF-8 bytes 原文为 WSL 200 条、Mac 202 条（记录口径）。
- WSL 旧改写当前 1682 条（微信1441/RSS241）；计划旧快照1387/241已被此次观察更新。Mac mirror 没有导出改写列；不得把其0当作原库无改写。旧改写复用通过数0。
- WSL 逐记录去重的旧图片引用 7538，已存文件7538、缺失0、越界0、uncheckable0。仅证明所核 localhost:8765 文件存在；未证明 Mac 8788 媒体路由、外部资源或论点资产完整。
- [K1-api.json](K1-api.json)：微信15287（中文→英文）和RSS80286（英文→中文）；API原文/译文均与固定镜像、WSL同来源记录的字节hash一致。数字token分别10/1，RSS6个代码块在原文/译文间一致。原始Mac镜像SHA前后均为 `5cf4d35dc32b697f850fbf3c19734b77bfe975116b0486fa366d185cd6662549`。
- [K1-browser.json](K1-browser.json)：桌面1280×900、手机390×844，共4次真实Chrome详情读取；原文→译文→原文DOM hash一致，切换可用，无横向溢出、无page error。已目视核手机RSS截图。当前接受的是已有纯文本阅读；Markdown列表/表格/代码的富排版不在该通过结论中。
- 定向 pytest 9 passed（盘点3 + 镜像/API6），两条既有依赖warning。新文件空白检查通过；全工作树 `git diff --check` exit2，只报既有 `batch_ingest_from_spider.py` CRLF/尾空白，未触及该WIP。[验证回执](verification.json)。
- 远端执行脚本SHA与本机脚本一致。两次初始失败后停止、复现、修复，再评后的一次验证退出0；初始failure_count=2保留。
- 业务模型调用0，新增DeepSeek成本0元。未发现已检查的现有Mac automation目录内有100元共享回填账本，未新建账本、未动凭据、未支用未知余额。Codex账户共享用量38%→39%，不是本任务独占用量。最近300条OCX usage未找到本线程关联行，主控实际provider/model路由保持UNKNOWN，不能以创建参数证明Sol运行路由。

RISKS:
- K1旧改写接入受来源修订/recipe provenance缺失限制；已有译稿的完整语义忠实度未认证。原文完整率也需来源级完整性证据，不能用正文非空代替。
- 44条原文缺口中30条已存候选值得下一步核，但不授权把不明来源文件覆盖原库。尚有3条译稿缺口和长文覆盖缺口；不得整体绕过筛选。
- CDP本轮未重试：K0/K1不依赖它，旧不可达证据不在此轮更新为可用。需新补抓的分支仍依赖部署G0既有通道验收。
- 付费K2/K3的首个明确前置是共享账本/预留与结算接口未核，不启动收费试调用验证配置。云发布、owner迁移、凭据、全库重建、自动commit/push仍未执行。

NEXT:
1. 沿现有生产owner核唯一100元预算与成功缓存接缝；parent读取本报告协调，不发送跨任务消息。没有账本前不发付费请求。
2. 从30条已有原文候选中核来源URL/修订、段落完整性和recipe；可证实后走既有mirror接入，保留源数据库原值和hash。44/3/长文逐记录清单保存在上述inventory，不重复抓取已有全文。
3. 由主计划B/E对应owner补富排版、语言标签、旧改写及可用媒体路径，再接受K1剩余范围。K2–K4按原依赖与同一100元额度推进，不能因本切片通过标全内容补全完成。

## 2026-10-04 第二有界切片（Halifax 16:44）

STATUS: 30条final_content候选只读核验及预算owner追踪完成。分类为 **verified-original 1 / derived-only 0 / unresolved 29**。494的一份历史捕获原文已通过隔离候选镜像API读取。本轮没有提升current或回写生产源库。全K1仍未完成，付费K2/K3仍未启动。

CHANGES:
- 新增[逐项来源核验](K-next-provenance.json)、[隔离候选API回执](K-next-candidate-api.json)、[缓存去重计数](K-next-cache-accounting.json)及[预算owner/最小接缝建议](BUDGET-OWNER-SEAM.md)。没有修改生产源码或部署配置，没有创建费用账本。
- 隔离候选目录为 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-k0-k1-20261004/verified-original-494-candidate`。复用现有export_library、receipt验证和私有API，只在该隔离SQLite中补494正文。与固定基准镜像逐行对照，唯一变化是articles:494的body，原译文保持。
- 30条的逐项证据存于同一隔离根：`K-next-folder-inventory.json`、`K-next-metadata-comparison.json`、`K-next-structure.json`、`K-next-checkpoints.json`、`K-next-repo-original-check.json`、`K-next-archived-source-comparison.json`和`K-next-3182-diffs.json`。正文只保存在私有运行产物，公开报告只含ID/hash/检查结论。

EVIDENCE:
- WSL再次实测hostname=OH-Desktop，三个tracked WIP和四份untracked历史文档保持。30个目录都有metadata.json，metadata URL与DB URL、文件内URL头分别全部一致。记录method为ua5、apify17、mcp7、resumed1。方法字段、目录hash和文件名只提供来源关联，不单独证明原文完整。
- 文件生成链为 `lib/ingest_wechat.py:1395` 拼接标题/URL/Time与抓取Markdown，1507–1512本地化图片并附引用，1600–1610将内容和metadata交给 `image_pipeline.py:474–489` 原子保存。WSL同期脚本SHA为 `83530fa407bdf463911cca14aa2d5f39bf8a91ab382e2fce81b51da719f7c022`，image_pipeline为 `8f904cd6ddfccbf7365075ca2b1502c7649a880386d6addfb0e3d0c3d10b9be5`。既有sync将ACK的images目录镜像到WSL。该链提供文件性质证据：final_content是抓取正文加管线头和图片引用/可能的注释的容器，不能把整个容器直接标忠实原文。
- WSL vault和repo旧SQLite这30条body均为空。28条另有body_rewritten，30条另有body_translated。它们属于派生字段，未作为原文对照或反推来源。没有证据证明任一final_content**只**含派生稿，因此derived-only=0。其余候选保留，不因缺历史recipe自动废弃。
- 仅494和3182有带URL关联metadata的 `01_scrape.html`。核验只提取已读源码中的process_content函数AST，注入已装bs4/html2text，不导入带config/客户端/写checkpoint副作用的ingester模块，不调用抓取或模型。
- **494 verified-original**：从已存HTML确定性重建全文Markdown。候选核心在去固定管线头、附加图片引用尾、仅规范图片URL并折叠空白之后，与捕获转换结果全串一致。保留图片alt文字，不截断正文。两边规范化hash均为 `8ec7f8e1899fa8b7bc58365a8c8dc1abd6f757af34b55f6561af6b26d5f14165`。HTML SHA为 `1aa9b4c1acea3f0628ec5b6406c9c2af7fcf0f8292e22a3ddd7c00b9a0ff319b`，重建原文SHA为 `de108cddda4792fe893b726675c2763cf9078ad9abb71de488256409d92be75b`。verified-original仅指该**已存捕获的原文核心**，不是整个final_content、当前在线全文或旧译文修订关系。
- **3182 unresolved**：对照不是全串一致。差异分析有一段115字符删除，其中有中文，以及9处各5字符插入。不能将该候选标为原文完整恢复。剩余28条有URL/抓取方法/容器来源关联，但未找到独立原始捕获或DB原文，完整性仍未知。每条理由及证据在K-next-provenance.json。
- 494隔离候选API为FastAPI TestClient，不是8788现用站点的浏览器验收。候选读取正文与重建捕获字节一致，原译文保持，私有snapshot hash验证通过。原基准镜像SHA前后均为 `5cf4d35dc32b697f850fbf3c19734b77bfe975116b0486fa366d185cd6662549`，基准API仍显示494缺正文。未替换自动mirror或current。
- 预算owner实测是Mac `com.vitax.local-refresh`，现用入口 `scripts/refresh_vitax_local.py`，run interval=3600秒，现用root=`/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/local-automation-20261002`。取样时job exited、runs26、last exit0。现有refresh.lock包围选稿、缓存、调用和发布；native_turn通过ACK既有SSH入口调用凭据owner。ACK hostname再次核为iZj1imk39yc55iZ。
- 现有native/accepted的27份usage文件包含20份DeepSeek副本，仅对应9个唯一request_id，另7份历史openai-codex。副本不能逐文件计费，历史异provider回执不等于本轮换provider。20份DeepSeek回执都未保留cache-hit/miss和人民币cost字段。当前receipt只证明调用与tokens，不能直接生成精确人民币账单。没有读取密钥或执行收费probe。
- 已核本机runtime root top-level/native/accepted和ACK准确运行根top-level/deepseek-turns，不存在已识别的backfill预算文件。建议由当前refresh owner在**同一运行根、同一refresh.lock**下落唯一backfill-budget.json，K/D共用。先复用accepted/成功native缓存，再预留；unknown结果保留预留，按request_id只结算一次。方案尚未实施，不能把日标记当现有预算账本。
- 本轮定向pytest重新执行9 passed，2条既有依赖warning。原分支failure_count=2保留。本轮对照分支新增1次环境错误：venv-aim1缺bs4/html2text。只读检查发现既有venv已具备两依赖后，沿同一SSH面使用该解释器完成对照，没有安装包、换provider或重置失败次数。
- 业务模型调用0、新增DeepSeek费用0元。共享Codex用量本轮41%→41%，计量为账户整数百分比，不是独占成本。没有重置额度、自动commit/push、云部署、CDP修复、生产owner迁移或外部通知。

RISKS:
- 29条候选的完整性仍未证实。494只证明历史保存捕获的完整转换，在线版本和旧译文来源修订仍UNKNOWN。未授权把不明稿件批量写回原库。
- 100元账本尚不存在于已核路径。首个决策前置是确认唯一实现owner与落点，并检查并行owner没有另建同义账本。随后核官方价目、usage缓存细分和可靠输入token上界。未经这些检查不发回填收费请求。
- 目前native_turn失败缓存可进入按日期retry目录。未来回填预算路径必须先核unknown预留/远端缓存与原失败次数，避免日期变化导致盲目重发。本轮未改该逻辑。

NEXT:
1. 项目主控读取本报告、K-next-provenance.json和K-next-candidate-api.json，接受或复核“494历史原文核心＋隔离API”的有限结论，不标全K1完成。
2. 项目主控将唯一100元预算接缝交给现有refresh owner，按BUDGET-OWNER-SEAM.md最小方案实施零收费回归。内容主控不另建账本或producer。
3. 保留29条未决候选。优先根据已有来源捕获/资产/历史合法产物补独立完整性证据，3182优先查明已核差异，不用重抓或模型替代证据。若后续提升494候选，须把来源捕获/provenance纳入镜像接缝，避免下一次自动mirror覆盖或丢失恢复关联。

## 2026-10-04 共享回填预算源码切片（Halifax 17:12）

STATUS: SOURCE_AND_OFFLINE_ACCEPTANCE_READY。项目主控明确指定本内容主控为唯一预算工程owner，运行owner仍是Mac com.vitax.local-refresh，落点固定为原运行根/backfill-budget.json。源码和零费用验收完成，尚未启用真实回填，生产账本尚未创建。全K1未完成，29条unresolved保持，494不promote。

CHANGES:
- 新增 `vitax/backfill_budget.py`：K/D共享10000分，复用同一refresh.lock，单文件原子保存并fsync。按来源修订/stage/recipe/prompt SHA绑定调用，lane不进入去重键。request_id独立去重结算。所有状态只存在已批准运行根，不新增队列、数据库或财务框架。
- 扩展 `scripts/refresh_vitax_local.py` 的显式 `--backfill --backfill-lane K|D` 接缝。默认daily不实例化预算、不创建账本、不改现有调度。回填需要显式两条select；沿用旧produce/Wiki业务，不接管C/D多主题或长文实现。回填不覆盖production-day.json。
- native_turn先查本地和原ACK缓存。未进入本轮账本的历史成功/失败结果不倒计费。余额不足不提交生成。新请求前持久化unknown预留；重启只读原结果，不创建retry目录或盲目重发。相同未决来源/stage/recipe不能通过换prompt、K/D或调换来源顺序规避预留。
- 在产品校验之前按实际usage结算。生成成功但JSON/产品校验失败仍保留已结费用。已知截断且usage可核也计费，不从失败缓存重发。未知结果保留预留。扩展DeepSeek成功回执白名单保留cache-hit/miss整数及和的校验，旧无细分回执仍兼容。
- scoped源码修改前备份及相对本轮起点的diff保存在 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-budget-source-20261004/`，保留原有lib/llm_deepseek.py及其他WIP，没有commit/push或调度/凭据改动。

EVIDENCE:
- [官方价目与预留推导](CONTENT-BUDGET-PRICING.md)：本轮核官方Flash适用模型和人民币单价。用整个上下文窗口、最坏输入未命中、高峰价和现有12000输出上限，取每请求220分预留，不用字符/4猜tokens。结算按实际usage/缓存细分、高峰价、整数分上取整，明确为**费用上界**，不是提供方精确扣款。旧回执缺缓存细分按全输入未命中上界，标cache_usage_observed=false。
- RED：预算功能缺失与回执缺缓存细分共7项失败。补实现后16项通过。继续对未知阶段换prompt/调换来源绕过，以及仅远端有历史缓存的倒计费缺口分别写RED并修到GREEN。完整本轮相关回归：**53 passed，2条既有依赖warning**。
- 命令：`OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_backfill_budget.py tests/unit/test_deepseek_completion_receipt.py tests/unit/test_refresh_vitax_local.py tests/unit/test_vitax_production.py tests/unit/test_build_vitax_source_packet.py -q`。没有跑网络/全套integration或新增正式UAT。
- 临时根通过真实refresh(backfill=True)→source packet→prompt→native_turn→budget→产品校验入口。只在外部SSH/模型传输边界替换合成回执，未替换预算或产品校验实现。生成成功后故意返回无效产品，实际产品校验失败；临时账本仍结算11分上界，预留0，daily marker原字节保持。该11分是合成usage，不是真实消费。持久回执 `content-budget-source-20261004/offline-refresh-ledger.json`，测试日志regression.txt。
- 定向测试覆盖余额不足零生成、成功本地/远端历史缓存零生成零倒计费、request_id副本只结算一次、未知结果留预留不重发、原结果重启恢复、K/D同账本、已知截断计费、产品失败仍计费以及daily无账本副作用。[源hash和零费验证](BUDGET-verification.json)。
- 生产运行根/backfill-budget.json末检仍不存在。真实业务模型调用0、验证中真实SSH调用0、新增DeepSeek费用0元。共享Codex账户42%→42%，不是独占成本。未初始化生产账本、未更改LaunchAgent、未移凭据、未部署、未promote。
- 原执行分支failure_count=2、上一原文对照分支failure_count=1保持。本轮源码执行没有非预期失败，RED为计划内验收。回执收集分支1次路径断言失败：pytest目录截短测试名，初始glob无匹配；只读列出该临时目录后修正定位并收集成功，没有重跑生产或清零该失败。

RISKS:
- 源码通过和合成usage不证明真实Flash计费或正式回填已执行。实际启用前仍需项目主控独立验收，随后沿已授权入口协调一批真实业务回执。
- 费用上界偏保守，未知结果保留预留会占额度。它限制本轮支用，不冒充账户余额/发票。官方价格或客户端输出上限变化时需按价目文档复核snapshot，不能改旧账或自动重置。
- 本切片保持旧两篇/Wiki/主题业务路径，未实现单篇、多主题、长文或日常/回填吞吐调度。后续新增的翻译、分块和Wiki路径须传同一budget身份，不得另立账本绕过。

NEXT:
1. 项目主控独立读取BUDGET-verification.json、相对起点diff和源码，复跑上述零费命令。owner与账本落点已明确，无需再确认owner。
2. 按CONTENT-BUDGET-PRICING.md最小步骤，选择两条已核合格原文/修订，保持运行根与锁，显式进入backfill模式。首次真实启用才创建唯一10000分账本，本切片未执行。
3. 核真实回执的模型、usage、request_id、预留/结算、accepted缓存和阅读发布结果。遇unknown仅原结果恢复，保留预留与失败历史。29未决候选不进入原文回写或强制生成。

## 首批真实回填启动（2026-10-04 Halifax 17:20之后）

STATUS: PREFLIGHT_PASS，准备单批执行，尚无本批收费结果。

CHANGES: 仅保存前置证据到 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-backfill-first-20261004`。不迁owner、不改timer，原运行根/refresh.lock。按主控授权首次启用唯一10000分账本，本批lane K，最多2篇解读+1次Wiki，最多3次真实调用/660分预留。

EVIDENCE: selected-sources.json核微信20294/RSS84952，不同URL，layer2=ok、完整已存文本检查、明确Harness主题、当前recipe未accepted、失败0。已核固定镜像/current/daily marker与现用API，ACK hostname=iZj1imk39yc55iZ。源码hash与主控已验回执一致。daily marker前SHA为844ed51a03b42652d115a60b564030a5f1643c0af124f9fdead1c961349476ff。此前本对话成功读到的2026-10-04官方价目及已保存文档仍能与请求Flash/12000输出上限绑定；本轮中文/英文网页重开均Timeout，重读分支两次失败后停止，不据超时推断价格。价目证据hash和参数记录于selected-sources.json。

RISKS: 仅已有完整存储文本审核，没有独立新抓在线全文。新收费过程尚未验收。任何首个产品/协议/未知结果阻塞即停，已发生费用或预留保持，不重发整批。

NEXT: 一次显式backfill/use-existing-snapshot/select/wiki-id执行，读取实际usage/request/output哈希/账本与发布结果。共享额度起点43%。494和29未决保持原状。

## 首批真实结果与首个内容阻塞

STATUS: 3次真实调用及现有发布器执行完成，但**内容验收BLOCKED_CITATION_CLOSURE**。不接受完整K3/K4通过，不重发本批。

CHANGES: K3实际新增微信20294/RSS84952两篇解读，并更新同一legacy-harness Wiki。release-local-de432882e10742f7已由既有入口提升，现用API读取新版本。共享账本首次初始化，K/D同10000分。未改timer/owner/原文库，494和29未决保持。

EVIDENCE: 私有根 `content-backfill-first-20261004/actual-receipt.json` 有3个唯一request_id，requested_model=deepseek-v4-flash、returned_model=deepseek-flash，实际usage/output hash一致，费用上界分别3/3/4分，共10分，预留0，余额9990分。daily marker SHA保持844ed51a03b42652d115a60b564030a5f1643c0af124f9fdead1c961349476ff，原文快照hash保持。manifest全部文件hash正确，结构字段evidence引用可读取。

RISKS: 进一步按spec核Wiki自由正文时发现5个 `evidence-*` 字符串在同版evidence表中不存在，另有正文引用未进入该Wiki证据面板。结构evidence_ids通过不能替代正文引用闭合。具体ID及前后差异见 `content-contract-assessment.json`。微信新解读主要为摘要，明确适用条件/局限也需项目主控裁决。没有用额外模型“修到通过”，没有静默缩减合同。

NEXT: 立即向项目主控报该首个具体阻塞，保留已发生费用/产物/前版。只读完成现用站点读取取证，不发第4次调用，不自行改提示、映射/删除引用或扩大B/E。由项目主控裁决引用合同与修复/版本选择。

## 首批切片冻结 checkpoint（Halifax 17:32）

STATUS: **BLOCKED_CITATION_CLOSURE，按项目主控指令结束本切片。** 已完成正在进行的只读浏览器取证。没有第4次模型调用，没有新pytest或新业务实现，不改timer/current/原文，不删除或猜测映射引用。K3/K4不标完成。

CHANGES:
- 本批唯一实际业务变更：K3新增2篇文章解读，更新1个已有Harness Wiki；通过既有发布器得到当前版本。没有另建Wiki占位页、第二producer或账本，没有新译稿/清洁稿/旧改写/长文分块/媒体恢复。中文解读不计为忠实中文译文补全。
- 用户可见：[微信解读](http://127.0.0.1:8788/article/article-wechat-20294-3bb40d592b88/)、[RSS解读](http://127.0.0.1:8788/article/article-rss-84952-114b03ad2ee6/)、[更新的Harness Wiki](http://127.0.0.1:8788/wiki/legacy-harness/)。原文入口为 `/library/wechat/20294`、`/library/rss/84952`。引用闭合问题保留并报告，未以页面能读替代内容通过。

EVIDENCE:
- 当前：`release-local-de432882e10742f7`，目录 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/local-automation-20261002/public/releases/release-local-de432882e10742f7`。
- 可恢复前版：`release-local-cfcea28d442e4823`，同根public/releases下对应目录。前版完整包仍在，manifest文件hash均有效。**前版Wiki也含同样5个未解析引用，恢复旧包不能自动解决内容闭合。** 未执行回切。
- 全部实际回执在 `content-backfill-first-20261004/actual-receipt.json`：3唯一request_id，Flash实际requested/returned及output hash通过。已结费用上界10分（0.10元），余额9990分（99.90元），未知预留0。账本保留真实调用，不撤销费用。daily marker和原文快照hash保持。本批没有重跑来证明幂等。
- 公开投影前→后：documents11→13，knowledge16→18，evidence94→102，entities44→54，relations33→41。实际新增2解读、8证据、10实体、8关系；Wiki为更新而非新增，旧10个证据ID全部保留。Wiki accepted投影重复合并两篇article对象，不将其计成额外生成。
- K4技术读取：`browser-receipt.json`证明2解读+Wiki在现用8788同一新release可读，DOM正文与API一致，证据面板分别4/4/14条，无page error/横向溢出；两篇原文DOM hash保持。已目视Wiki截图。该结论不接受正文未解析引用或内容质量缺项。
- 首个按正文顺序缺失引用：`evidence-ee30a0a92978511ce97a`。5个全部来自前版legacy-harness.body，当前库和前版库均无对应evidence行，本批新增未知ID=0。具体来源分類如下，原始历史生成起点本轮未查明，不猜测：

| 缺失ID | 本批来源分类 | 已核来源 |
|---|---|---|
| evidence-ee30a0a92978511ce97a | 继承的未解析正文引用 | 前版public.sqlite，legacy-harness.body；两版evidence表均无行 |
| evidence-23500b7ad7f07748a81c | 继承的未解析正文引用 | 同上 |
| evidence-4ae6a641435b0cc867fc | 继承的未解析正文引用 | 同上 |
| evidence-b61c64a8df4e45c02738 | 继承的未解析正文引用 | 同上 |
| evidence-c73990f2aee420b34f1a | 继承的未解析正文引用 | 同上 |

- 另有4个本批正文引用在release中存在，但未列入Wiki证据面板：evidence-0d066185c846ca89ef55、evidence-847e4e2238c637c0e789、evidence-d652c9e2e3f7880ba1a5、evidence-f840633517221acd1e1f。不能把结构evidence_ids合法代替所有正文引用闭合。详见 `content-contract-assessment.json`、`final-blocker.json`。
- 微信解读相对主计划§7.3：观点和作者实测依据存在，4个结构证据可读；**缺明确适用条件**（没有说明何种开发/集成场景和前提下适用其收益判断），**缺明确局限**（没有限定单作者实测、任务覆盖及泛化边界）。内容主要为复述/摘要，不能把趋势结论当已给出这些边界。RSS已描述复现上下文和训练假说不确定性，但本轮不作全套质量评测。
- 本轮验证脚本有两次已纠正的非产品错误：API读取把knowledge envelope当平铺字段（1次）；浏览器URL断言未接受既有目录尾slash重定向（1次）。根据实际schema/router纠正后，仅只读验证一次成功。没有重跑模型或修产品代码。官方价目重读分支2次Timeout后停止。原执行2、原文对照1、预算回执定位1等历史失败保留。
- 共享Codex用量43%→44%，账户计量非独占成本；业务调用总数3，后续追加0。模型费用为账本上界，非精确提供方发票。

RISKS: 当前版和前版均存在既有Wiki正文未解析引用。当前微信解读有适用条件/局限缺项。K1全面阅读格式、K2译稿/原文缺口与长文、K3全覆盖及K4完整阅读关联/媒体未完成。494和29未决继续保留、不promote，不把首批Harness样本写成完整backfill。

NEXT: 项目主控按已裁决的“正文引用同版可解析”合同另行承接修复/版本选择。本内容主控结束当前切片，保留账本、三个已付费产物、原版与前版及checkpoint，不追加调用、测试或修复。

## 下一有界切片：隔离引用合同（2026-10-04 Halifax 18:00前后）

STATUS: **ISOLATED_CITATION_CONTRACT_READY_NOT_DEPLOYED。** 零业务费用的根因定位及离线RED→GREEN完成。旧收费分支仍冻结，在线当前内容仍有5个未解析引用；未将代码合同修复声明为线上K3/K4通过。

CHANGES:
- 核live launchctl及安装plist，在线入口确实为仓库根 `scripts/refresh_vitax_local.py`，不能原位编辑。本次建立最小13文件Python依赖副本 `.superpowers/sdd/vitax-content-citation-contract-20261004`，模块__file__确认全部来自隔离目录，config/LLM模块未加载。没有创建新运行producer或搬移环境。
- 只改隔离副本的 `vitax/knowledge.py` 与 `scripts/refresh_vitax_local.py`，新增隔离 `tests/unit/test_citation_contract.py`。交付diff：[citation-contract.patch](../../../.superpowers/sdd/vitax-content-citation-contract-20261004/citation-contract.patch)，SHA `c197aa21bb325b389b232798a933b4c6286640fddb94ed6bc411937d39402a6f`。这是相对本次在线WIP快照的diff，未应用到在线路径。
- 复用现有公开投影validator：解析已有producer的canonical `evidence-<20位小写hex>` 正文ID，只能引用同版 `visibility=public` 的证据。未知/私有ID拒绝构建；已公开且有效的正文引用追加至该条目的面板关联，去重并保留旧关联顺序，正文及原输入不变。不从bank补造证据，不改变private为public。
- 复用同一validator做promote前检查：旧格式包若正文引用未知或虽在公开库却没持久化到自己的面板，拒绝切换current。没有另一套validator框架、队列或UI重写。

EVIDENCE:
- **首个失配边界**：旧Wiki模型自由body使用候选bank ID，但其结构化citations没有选中这些ID。`vitax/production.py:263–299`只从结构引用落证据，`accept_model_output`只验证这些引用，不交叉检查body。原 `vitax/knowledge.py:159–168`只查evidence_ids列表。原promote只查manifest hash、SQLite形状及release身份。前端EvidencePanel只读取持久化knowledge_evidence返回的evidence_ids，因此未关联的有效引用也不可从Wiki面板到达。
- 所有5个ID均准确重建自旧 `accepted/deepseek-v6-article-wechat-20074-4292203b532b/standardized.json` 的citation bank：来源wechat-20074，revision `rev-85c6f2e34292203b532b`，locator paragraph:1。ID与候选quote/revision/locator的hash完全一致；这些quote从未在结构化citations被选中，也不存在于accepted.evidence。它们出现在旧Wiki `deepseek-v6-wiki-8de99323e1d83823ca77` 的自由正文中，再被首批 `deepseek-v6-wiki-327d05e15d1489b43088` 继承。分类从“历史起点未决”推进为**有原文依据的bank-only候选引用，未获持久化公开证据准入**。这不授权将它们自动公开或猜映射。

| ID（均为evidence-前缀） | 现已证实的来源分类 |
|---|---|
| ee30a0a92978511ce97a（首个） | wechat-20074原文候选bank；未结构选中/未公开持久化；旧Wiki自由正文继承 |
| 23500b7ad7f07748a81c | 同一source revision与locator，另一候选quote，未公开持久化 |
| 4ae6a641435b0cc867fc | 同上 |
| b61c64a8df4e45c02738 | 同上 |
| c73990f2aee420b34f1a | 同上 |

- 逐ID原文quote SHA、原始/标准化回执hash及选择/持久化标志见隔离 `trace-citation-bank.json`、`trace-occurrences.json`、`verification.json`，没有把原文quote或私有证据复制到报告。
- 新最小合同在隔离知识模块131–134及168–179、隔离promote 46–50。基于完整已获准公开的合并投影查引用，不能只看本次Wiki结构citations子集，因此4个本批已公开有效引用的面板缺项由同一接缝解决。7项临时数据测试验证unknown/private拒绝、4有效引用到达面板且旧关联/正文不变、合并文章已有公开引用可用、旧包绕过builder仍不能提升、漏面板包不能提升、publisher在site-build前拒绝。
- RED：有界测试记录7 failed；GREEN：**7 passed，0 warning**。命令在隔离cwd：`OMNIGRAPH_LOAD_ENV=0 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/hai/Projects/ohpc-migration/VitaX/.venv/bin/python -m pytest -c /dev/null --rootdir=. --confcutdir=. tests/unit/test_citation_contract.py -q`。只运行变化合同，临时数据，无LLM/SSH/网络。日志为red-bounded.txt和green.txt。
- 用隔离gate只读检查冻结前版及当前版，二者均在首个 `evidence-ee30a0a92978511ce97a` 拒绝；文件hash保持。没有删除ID以制造GREEN，没有公开bank候选补行，没有修线上内容。
- **在线保护证据**：13个在线Python文件hash与基线完全相同；预算、daily marker、当前manifest及当前public.sqlite这4个hash相同，6个唯一已读standardized/model回执文件hash相同；public/current仍指向release-local-de432882e10742f7。冻结批次原文固定DB hash保持。详见隔离verification.json。
- 不能宣称所有环境完全静止：现有自然refresh于17:55推进library/current，从93d705b0快照到7510284a快照；receipt及既有refresh日志支持该观察。本切片未执行refresh，未修改其在线源码，原固定DB不变。未阻断或重启自然timer。
- 本轮额外费用0、业务调用0、SSH0、测试连网0，已结10分/预留0不变；共享用量45%→46%，未获新增10%且未重置。
- 历史失败计数保持。本轮隔离patch有1次预期行定位错误（return values vs list(values)），读实际行后应用成功；收集验证有1次路径子串StopIteration，按已观察basename修正；未换worker/harness。初次RED publisher触及缺失site目录后，改为禁止frontend执行的测试stub，重新记录有界RED，未运行联网构建。

RISKS:
- 5个原文候选虽然现在有可核hash来源，仍不是当前已获准公开证据行；数据问题未解决。线上current仍是de432882版，前版cfcea28版同样不闭合。隔离patch未部署，不改变用户看到的现状。
- 微信适用条件/局限继续不接受。已核生成合同根因：`production._prompt:479–480`只写自由“Chinese interpretation”与引用要求，adapter system只约束格式/长度/引用；accept_model_output仅查中文body/结构引用，没有明确要求或验收§7.3的适用条件和局限。本轮不加空字段、不改标题/正文、不请求模型补稿。
- 新gate覆盖现有producer生成的canonical证据ID形式，未引入一般Markdown引用解析平台。假如后续新增其他引用协议，需先有实际输入/合同再扩，不提前造框架。

NEXT: 项目主控独立验收隔离diff及7项红绿证据，然后另行安排在线接入和历史数据准入/引用修复。最小后续为对5个已溯源但未公开候选作明确准入裁决，保持正文/旧证据，不猜映射；或合法的后续内容更新。微信问题另行对齐既有§7.3生成要求并做来源约束审查。本内容主控结束该零費切片，旧收费分支不恢复。

## 必要证据逐条审核与隔离候选（2026-10-04 Halifax 18:20前后）

STATUS: **REVIEWED_ISOLATED_CANDIDATE_READY_NOT_DEPLOYED。** 按新增授权审核5条必要引用，5条均通过限定用途审核；隔离投影/SQLite可重新打开，正文ID与自身面板闭合。此处接受的是引用证据候选，未接受线上修复或完整K3/K4，旧收费分支仍冻结。

CHANGES:
- 复用同一隔离目录，在 `necessary-evidence-review/admission.json` 写5条显式准入记录，记录原文quote/revision/locator/hash、上下文支持、必要性、隐私检查及用途限制。审核依据不是“hash一致自动通过”；核了原文相邻叙述、Wiki对应论点及其作者归因/不作产品保证边界。
- 新证据只用于已存在且已accepted的legacy-harness Wiki的必要引用。5条摘录总计231字，原文5899字继续留在原私有来源；未公开整篇、未从译文全段生成证据。源码patch保持原已验SHA不变，没有建立通用审核系统。
- 独立候选目录：[candidate](../../../.superpowers/sdd/vitax-content-citation-contract-20261004/necessary-evidence-review/candidate)。原accepted/native缓存不覆盖，知识正文/标题/kind和旧证据/关系保持。仅追加审核通过的5个evidence行，复用已验validator补全部合法正文引用的面板关联。

EVIDENCE:

| 必要引用（evidence-前缀） | 审核结论与具体理由 |
|---|---|
| ee30a0a92978511ce97a | APPROVED：原文前段明确互借Claude Code/Codex后担心封号、转向协作工具。支持Wiki对作者动机的归因；不是平台封号政策认证或账号共享建议。 |
| 4ae6a641435b0cc867fc | APPROVED：相邻原文明确身份/执行/共享分离，该句直接支持作者所述凭据留本地。Wiki整节明确作者个人理解与“不构成产品保证”，不升级为独立安全审计；API key只是泛指，无密钥值。 |
| 23500b7ad7f07748a81c | APPROVED：该句支持作者描述的云端工作区及数据角色，紧邻后句支持产出时序转述。只作来源描述，不保证实际部署、一致性或安全。 |
| b61c64a8df4e45c02738 | APPROVED：共享电脑前后文及文件/依赖/服务同状态原句支持Wiki论点。用于区别手工复制与共享环境，不把作者转述当独立官方认证或实测一致性指标。 |
| c73990f2aee420b34f1a | APPROVED：原句和下文支持共享Agent能力/额度；上下文明确不是转交账号、登录状态不转手且可取消。必要摘录支撑协作描述，不鼓励移交凭据。 |

- 5条都来自wechat-20074、revision rev-85c6f2e34292203b532b、paragraph:1，精确quote为原文子串，ID由原quote/revision/locator重建一致。来源doc已在原公开投影中，URL与已有standardized记录一致；没有假映射或重造ID。已对隐私和必要摘录范围审核，仅批准这些具体摘录支撑已归因的作者叙述，没有认证产品当前行为。
- 候选release：`release-local-citation-reviewed-20261004-c4f23bd8b737`。SQLite SHA：`be7f2ff4930a914d31064c297de7181a9482ae29d46d887c559773a3fb8e810d`。规范投影 `candidate/public-projection.json` SHA：`956d639b47ee6e9b8618c9fd45b71bab1776219d910caa19572b1c9ab8e68099`。原输入projection.json单独保留以追踪validator标准化过程，不改旧缓存。
- 102条旧evidence逐字段保持，新增5条后107。全部18条knowledge正文/标题/kind/visibility逐字段相同，旧关联保留；documents/entities/relations相同。Wiki面板14→28：包含5条新准入摘录和9条已在旧公开库中的合法引用，其中4条正是首批新有效引用缺项。没有删正文或旧引用造通过。
- 重新打开候选SQLite，现有KnowledgeReader逐知识条目证明全部canonical正文ID同版可解析且在自身evidence_ids中；引用读取可达。integrity_check=ok、foreign_key_check为空。decoded body/quote字段无完整私有原文。候选只含投影/SQLite，尚非可直接提升的完整site/manifest发布包。
- 所需最小确定性检查完成，没有重跑7项套件或整批生成。校验脚本有1次KeyError(images)：既有DTO没有该字段。候选此前已构建，核实际schema后继续只读检查，无重新构建/模型调用。记录在candidate-verification.json，历史失败计数保持。
- 在线4个相关源码hash、budget/daily/current DB/manifest这4个runtime hash、9个已读原cache文件hash及public/current指向全部保持；原standardized来源hash保持。见 `necessary-evidence-review/protected-state-verification.json`。新增业务调用0、SSH0、费用0，已结10分上界保留。共享用量实际47%→48%；父主控46%只是较早共享快照，无新增额度或重置。
- 最小接入步骤见 [ONLINE-INTEGRATION-PLAN.md](../../../.superpowers/sdd/vitax-content-citation-contract-20261004/necessary-evidence-review/ONLINE-INTEGRATION-PLAN.md)：先固定点/WIP与独立审核，持有唯一refresh.lock，保存旧包及源码WIP回退，在staging核已验patch后才原子接入；以现有builder构造完整新包、同版验证后提升，最后现用读取验证。**全部只写计划，未执行接入。**

RISKS: 当前在线de432882版仍未修，前版同样有5个旧缺口。微信20294适用条件/局限继续未完成，不重写。本候选关闭引用与面板，不代表完整内容质量或全量backfill通过。来源产品行为只按作者归因描述审核，没有独立安全/一致性验证。

NEXT: 项目主控独立审查5条准入记录、规范投影/SQLite及保持性回执；接受后另行授权/执行已写的最小线上接入，不直接拿仅SQLite目录替换current。本内容主控结束该审核切片，收费继续冻结，正文/旧数据不改。

## 本地接入：包已提升，现用读取待验（2026-10-04 Halifax 18:30之后）

STATUS: LOCAL_PACKAGE_PROMOTED_AWAITING_BROWSER。项目主控已独立接受5项准入及候选，按新授权完成锁内接入。尚未把门禁/包检查当浏览器通过。

CHANGES: 在原refresh.lock下备份两份在线源码原字节和旧current索引，staging编译/比对已验patch后原子接入knowledge.py、refresh_vitax_local.py及直接相关测试。不用HEAD覆盖WIP。新进程用现有builder从获准投影构建完整site/SQLite/manifest包，经新gate提升为release-local-citation-reviewed-20261004-c4f23bd8b737。

EVIDENCE: 同一隔离根 `local-integration-20261004/rollback-index.json` 记录锁PID/时间、原文件hash/回退位置、旧包与保护数据。installed-contract-tests.log为7 passed，build-full-package.log和gate-and-promotion.log证明新进程加载在线gate、22正文引用/28面板、manifest/integrity/FK通过。package-data-verification.json证明完整新包与已验候选投影一致、102旧证据/18知识正文及documents/entities/relations保持、3份私有原文未进入公开body/quote/HTML/JS/JSON。账本/daily/原文及原cache hash保持。

RISKS: 微信适用条件/局限未解决，完整K3/K4不标完成。没有模型调用/收费或第二producer，不改timer/路由/旧cache；接入失败恢复范围只限已备份本切片源码/current，旧版本来有5个引用缺口，不能称其修复。

NEXT: 现用8788真实API/浏览器核同版、22引用/28面板、两篇解读和两篇原文；完成后交付最终checkpoint并结束切片，收费继续冻结。

## 本地引用接入最终结果（2026-10-04 Halifax 18:45）

STATUS: **LOCAL_CITATION_INTEGRATION_AND_BROWSER_PASS。** 本地引用合同和必要证据已接入并完成现用站点验证，等待项目主控独立验收。只接受本次引用/本地接入切片，微信质量及完整K3/K4仍未完成，收费回填保持冻结。

CHANGES:
- 取得原运行根refresh.lock后，保存源码原字节、旧完整包位置、候选及回退索引。在staging核已验patch、编译并比对固定点，锁内原子接入仅 `vitax/knowledge.py`、`scripts/refresh_vitax_local.py` 和 `tests/unit/test_citation_contract.py`。原WIP保留，没有HEAD覆盖、commit/push。
- 新进程加载在线gate，以现有builder由获准规范投影构建完整新site/SQLite/manifest，再经门禁验证提升。没有把仅SQLite候选切current，没有调用整批refresh，没有第二producer、模型、SSH业务、云部署或timer/路由/账本修改。
- 用户入口不变：[Wiki](http://127.0.0.1:8788/wiki/legacy-harness/)、[微信解读](http://127.0.0.1:8788/article/article-wechat-20294-3bb40d592b88/)、[RSS解读](http://127.0.0.1:8788/article/article-rss-84952-114b03ad2ee6/)及两篇 `/library/...` 原文。当前版本 `release-local-citation-reviewed-20261004-c4f23bd8b737`；5条必要摘录准入及全部合法正文引用面板关联生效。

EVIDENCE:
- 根：[local-integration-20261004](../../../.superpowers/sdd/vitax-content-citation-contract-20261004/local-integration-20261004)。rollback-index.json记录实际锁PID/时间与等待、source-before原字节/原hash、旧current和完整包manifest hash、候选与保护文件。旧 `release-local-de432882e10742f7` 包仍在且hash均正确；未删除旧包。旧包有引用缺口，仍只作为运行回退，不称语义修复。
- 接入后直接合同测试7 passed in 0.10s；没有跑更大套件。新进程gate日志确认module路径是在线仓库而非隔离副本，LLM/config模块未加载，22个正文引用和28个面板项通过，manifest22文件全部hash有效，integrity/FK通过，锁持有至提升结束。
- 在线新源码SHA：knowledge.py=`6c92eb4a6576e7499374accc04fa595978b96f2e89aa49f94d3f08d11316c820`；refresh_vitax_local.py=`81096092bc4e3cef4d6f9572baa93241acbb3559be082cb0655e1c8ae9d4ad42`；相关测试=`323223b9477e57e04ab56d6d12b4dde64039213f9429f057c5bc31e71025eff2`。production.py和模型adapter源码保持。
- 完整包manifest SHA `c2ff62293930c2eee8738ddc0898e3fc96a86ac254e7f395c7d59eff3067c1c4`，公开SQLite SHA `1c7223afb17a81845d5475ff7ae6caa8059aafce0ac5285485418b83aa143117`。重建数据库字节hash与离线candidate不同，但逐对象DTO完全相同于独立验收候选，不把不同物理文件说成字节相同。
- package-data-verification.json：18知识正文/标题/kind/visibility保持，102旧证据逐字段保持，新增5后107；documents/entities/relations保持。所核3份完整私有原文不在公开body/quote，公开HTML/JS/JSON（含转义形式）扫描无完整原文。site/SQLite/manifest同版完整包，不是裸DB。
- browser-verification.json：现用8788新release API/DOM与获准SQLite一致；Wiki22个canonical正文ID逐项API200、同release、面板可达，28项quote按顺序与SQLite相同。两篇解读同版可读、各4证据；两篇私有原文DOM hash保持。无page error，已目视wiki-live.png。源门禁未代替浏览器证据。
- final-verification.json：账本、daily marker、固定原文DB、旧accepted/native缓存hash保持；当前指向新完整包，旧包保留。新增业务模型0、费用0、SSH业务0。账本已结上界10分、预留0、余额9990分仍保持。共享账户48%→49%，不认领新增10%或重置。
- 本次接入分支失败0，没有执行恢复。保留历史各分支失败计数与此前回执，未通过换harness/model清零。失败保存/恢复逻辑限定本切片原字节/current，并保留失败包，不放宽candidate门禁。

RISKS: 5条准入仅支持来源作者归因描述，不是产品安全或行为认证。微信20294适用条件/局限继续缺，不重写、不宣布全K3完成。原文、清洁稿/译稿/改写、长文、媒体及完整阅读关联的剩余backfill未完成。494/29候选仍保持原状态，本次未promote。新源码以后会拒绝不闭合候选，这是合同效果，不自动补私有证据或重发模型请求。

NEXT: 项目主控独立验收锁/备份、源码/完整包hash、promotion和现用API/浏览器回执后安排下一有界内容工作。本内容主控结束本接入切片；收费分支继续冻结，不启动其他票或追加模型调用。

## 微信20294单次Flash v7修订收尾（Halifax 19:12）

STATUS: CONTENT_REVIEW_BLOCKED_CANDIDATE_ONLY。一次有意修订已完成，源约束内容审核未通过，不发第二次调用。随后主控已认可该问题，并另给两处精确编辑授权；以下保留原v7模型失败结论，不由编辑结果覆盖。

CHANGES: 仅隔离 `wechat20294-semantic-v7/prompt_revision.py` 对齐§7.2/7.3的观点/依据/适用条件/局限；JSON接口、knowledge ID/title保持。新recipe=deepseek-v7-semantic-article，独立prompt SHA/cache，未部署prompt、未覆盖v6稿或清历史失败。只单篇native_turn，不调用两篇+Wiki的produce/refresh；entities/relations输出空，候选保留既有图谱。

EVIDENCE: 同一隔离根wechat20294-semantic-v7下prompt-diff.txt、intent.json、actual-call.json、candidate-delta.json、content-review.json、final-verification.json。新request_id=08bad6cb-e2b4-417a-806b-cf7233546a03，requested=deepseek-v4-flash/returned=deepseek-flash，prompt6331（hit3584/miss2747）+completion776=7107 tokens，finish=stop，output SHA c41ed17ece9cca211d1ea75942a5cf90257167c3fdf4e0b87ec5f0c1d38dacc1。原root/refresh.lock和共享账本预留220分后结上界2分；4请求累计12分、预留0、余额9988分。原3请求条目保持。

原v7候选SQLite SHA9bb09005644f5564cf16dd76ff4acc4be6f16b34bdda6a1fa8a456d5d3b6cd9d，投影SHA26e2617a0908ec495e8521dad5300001a890a0c5b84219f33cc80ea44bc28616。相同knowledge身份与旧4links保留，新增2证据，entities/relations及Wiki不变，全部候选引用闭合。39项保护文件hash保持，current/daily/Wiki/原文/旧缓存未改。

RISKS: 首个问题是“以上产品效果仅适用于作者列举的调研、播客和图文任务类型”：原文只有这些演示的证据覆盖，不支持排他性的产品适用范围，也未标推论。主控另确认原文未明说目标人群，未核图片也不能断言整份资料没有价格/配额等信息。已有条件/局限段落和数字核对不替代该源约束验收。原模型稿失败状态保持。

NEXT: 按主控新增窄授权严格做第二段首句/完整末段两处定点编辑，独立editorial候选、前后hash/diff，零模型追加。格式检查仅1项RED→GREEN（未重跑7引用测试）；曾有pytest rootdir/cache路径warning，纠正隔离rootdir后1 passed。共享50%→52%，未重置或新额度。此次语义内容失败count=1，历史计数保持。

## 主控精确editorial纠错与本地接入（Halifax 19:22）

STATUS: **EXACT_EDITORIAL_LOCAL_INTEGRATION_PASS，待父主控独立验收。** v7原Flash稿的CONTENT_REVIEW_BLOCKED记录保持；只接入主控给定两处编辑和已核2条必要证据。不是第二次模型生成，不把编辑字节冒充Flash输出，不声明完整backfill通过。

CHANGES:
- 直接从CONTROLLER.md“微信v7内容问题裁决与定点编辑”提取两处授权文本。只替换第二段首句与完整末段。其他第一/第三段、第二段余文、title、knowledge_id/URI、引用保持，不自由发挥。独立目录 `wechat20294-semantic-v7/editorial` 保存editorial-record.json、editorial.diff、输入/规范投影和SQLite，保留原v7候选及全部原模型回执。
- 主控认可的两处文本区分演示覆盖与排他适用断言，消除原文未明说的目标人群归因，并限定已核文字/未核图片的缺项判断。纠错依据来自主控精确裁决及原文，不由工程代理重写整篇。
- 原root/refresh.lock内核base c4f23引用修复版、保存旧完整包与rollback-index。现有builder构造完整site/SQLite/manifest，新gate通过后提升为 `release-local-wechat20294-editorial-v7-3c8f8e86674d`。没有部署隔离prompt/在线源码或改timer，没有调用produce/refresh整批、业务LLM/SSH、换provider或commit/push。

EVIDENCE:
- 原v7模型输出JSON SHA **c41ed17ece9cca211d1ea75942a5cf90257167c3fdf4e0b87ec5f0c1d38dacc1** 保持。原v7 body SHA572860bcc5e8f6e9d6d492ee91be9e69e39aea0d8dbd3439dd2395a67cf78ab6；editorial body SHA **3c8f8e86674d312e85bd091411ad0ac96579a72b1b8d1741ad50e926f396b3ec**。两类来源及失败/编辑后接入结论分开保存，原usage、v7 paid cache、原candidate和content-review不覆盖。
- 锁内只做候选提升，原c4f23完整包仍保留。新公开SQLite SHA **910d1cb4ca3cd4a80bb3f427533cea2b775dd0205db8117cd974b577692883d5**，manifest SHA **5c8f750b90c5342825bb9985210dd95760b58478db361aa2651fedf5593b4b1e**，22完整文件hash正确，引用/FK/integrity通过。
- 其他17 knowledge全字段不变，107旧evidence逐字段保持，仅新增v7已核2短摘录后109；旧entities/relations/documents不变，Wiki正文和28面板不变，微信旧4links保留，候选/现用合并新2后6。私有原文不在公开body/quote及HTML/JS/JSON；原文/账本/daily/source/原缓存hash保持。
- [微信现用解读](http://127.0.0.1:8788/article/article-wechat-20294-3bb40d592b88/) API/DOM正文精确等于editorial，title与身份保持；[Wiki](http://127.0.0.1:8788/wiki/legacy-harness/)正文不变，22正文ID同版可解析、28项面板与SQLite逐项一致，RSS解读不变，两原文DOM hash保持，无page error。复用已有浏览器断言并存browser-verification.json/wiki-live.png，没有新业务代码或大套件测试。
- 全部证据在同一隔离根wechat20294-semantic-v7/editorial：editorial-record.json、editorial.diff、promotion.json、rollback-index.json、browser-verification.json、final-verification.json。精确差额检查证明只有获准两处正文改动，新增2证据及相应关联；没有删其他引用来过门禁。
- 本次editorial新调用0、新费用0；账本4请求、累计上界12分、预留0、余额9988分。原v7那1次调用及2分费用保持，不取消或改账。原批仍冻结。v7语义失败count=1保持，editorial接入分支0失败，其他历史计数保持。editorial共享52%→52%（前一v7切片50%→52%），不是新额度或独占成本。

RISKS: v7原模型输出仍不通过，编辑版只是按主控裁决纠正该单篇两处已定位问题。公开内容中的产品陈述仍按作者归因，不是独立性能/安全认证。本轮不能代表完整K3/K4、其他来源的语义生成稳定性或全部backfill完成。新prompt未部署到daily，未来产物的同类语义约束需另行有界处理。

NEXT: 父主控独立验收两处精确diff、raw输出保护、完整包及现用API/浏览器，再安排下一切片。本内容主控结束该editorial纠错与接入，禁止第二次请求/批量收费，不开其他票。
