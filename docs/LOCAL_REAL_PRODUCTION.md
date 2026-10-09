> 历史记录：只供查实现和当时结果；旧审核要求、执行限制和下一步指令已被[当前需求](spec/VITAX_HOBBY_PRD.md)与[批处理计划](superpowers/plans/2026-10-04-vitax-next-stage.md)替代。

# 本地真实知识生产切片

范围是 VX-004 的可运行离线生产切片：它读取已经抓取并保留的 HTML，生成标准文档修订，调用一次有界 Hermes 任务或接收一份实际保存的输出，严格核验引用后调用 `vitax.knowledge.build` 创建全新的公开 SQLite。它不抓取 URL、不安装依赖、不发布、不改现有知识库或运行时数据。

## 当前真实范围

最新状态（主控反馈）：本次完整两源切片已完成两个已接受 article、跨来源 Wiki 合并和新 SQLite 构建，Wiki+DB 技术检查 PASS。release 为 `release20260910t021435z`；独立最终 review 已 PASS，两源内容、Wiki 和 finalDB 无阻断，本轮两源切片 accepted。此结果不代表完整 VX-004、12 样本验证、迁移或 production 已完成；没有生产部署或发布。

证据：
- 第二篇文章：[article-fixed/output](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/article-fixed/output)。
- Wiki 产物：[wiki-output](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/wiki-output)。
- 候选数据库：[wiki-public.sqlite](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/wiki-public.sqlite)。
- 技术验证：[wiki-validation/receipt.json](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/timeout-diagnosis-20260910/wiki-validation/receipt.json)。

历史记录：第一篇来源已有已接受的单源 article artifact，其原始模型输出和 usage 可按下文离线 receipt 路径复用；第二篇此前出现 timeout/failure 并暂停。这些记录属于之前的尝试，不作为本次 article 的执行结果。

## 输入

输入 JSON 的 `documents` 是一到两篇已抓取来源。每项需要稳定的 lowercase `source_id`、`source_url`、本地 `html_path`、`raw_html_sha256` 和带时区的 `fetched_at`；`title`、`source_published_at` 与 `image_context_path` 可选。`image_context_path` 是抓取阶段保留的 JSONL，每行只有来源图片 URL、alt 和附近文本。调用方必须提供 `--capture-root`；HTML 和图 metadata 都以 strict resolve 后限制在该根目录中，越界路径、symlink 逃逸和 hash 不匹配都会拒绝。

`raw_html_sha256` 标识一次原始捕获；`content_hash` 是 trafilatura 抽取并规范化后的段落 JSON 的 SHA-256。两者不能互相代替。发布时间未知则传 `null`，不从抓取日期或页面版本推断。标题选择一个已记录的来源标题，不混合页面可见标题与 metadata 标题。

正文复用 `lib/scraper.py` 已使用的 trafilatura precision→recall 路线。生产环境缺少 trafilatura 或两次提取均无正文会报错；不会回退到整页 HTML、html2text 或手写 DOM 扫描。段落产生 `paragraph:N`，图片产生 `image:N`。图片 URL 用 `urljoin(source_url, image_url)` 解析；logo、头像和 portrait 类候选在进入模型前排除，模型只能从剩余来源候选选择。

图片 caption 优先来自捕获 HTML 的 `img` alt、figure/figcaption 或干净的相邻 DOM 文本。抓取时留下的 `nearby_text` 仅在本身不含 HTML/SVG/属性残片时作为来源文字；没有干净来源文字时，caption 明确标注为该来源文章的图片且说明 captured HTML 未提供 caption。每项始终保留原始 image ID、来源文章 URL、图片 URL、revision 与 `image:N`，不以修 caption 改变模型选择身份。

## 运行

从候选源码根目录执行。以下环境变量仅作用于该命令：stale=360 秒、外层 timeout/run budget=720 秒是本次已验证候选值，不是产品全局默认。输入文件、capture root 和 source ID 按实际捕获替换，输出目录必须尚不存在。续跑只处理未接受来源，已有 accepted 文章直接复用。

```bash
OMNIGRAPH_LOAD_ENV=0 HERMES_API_CALL_STALE_TIMEOUT=360 \
  OMNIGRAPH_HERMES_TIMEOUT_SECONDS=720 \
  OMNIGRAPH_HERMES_PYTHON=/home/sztimhdd/.hermes/hermes-agent/venv/bin/python \
  /home/sztimhdd/OmniGraph-Vault/venv/bin/python -m vitax.production input.json batch-article-beta \
  --capture-root /trusted/captures --stage article --source-id source-beta --run-hermes
```

`--run-hermes` 显式从 `lib/llm_hermes.py` 加载 adapter，不经 `lib` package eager import。它要求调用方提供 Hermes 现有运行环境的 `OMNIGRAPH_HERMES_PYTHON`，由该解释器执行 `lib/hermes_text_runner.py` 的原生 `AIAgent` 单轮入口；固定授权 provider/model、`fallback_model=None`、空工具集和单轮预算。真实 native check-only 和第二篇 article 已通过各自验证；Wiki 与候选 SQLite 已技术通过，独立最终 review 已 PASS，本轮两源切片 accepted；完整 VX-004、12 样本、迁移与 production 仍未完成。已有 `hermes_model_complete()` 保持文本返回兼容；生产调用新的 `hermes_model_complete_with_usage()`。`model-output.json` 保存准确文本，`usage.json` 在模型返回后、JSON/引用校验前立刻保存允许的实际 usage：provider、model、session_id、completed、failed、service_tier、api_calls、input/output/cache-read/cache-write/reasoning/total token，以及 `cost_status`、`cost_source` 和 `estimated_cost_usd`。后者保留 Hermes 的“估算”字段名，不能当作实际收费。Hermes 若提供既有的 duration 或 cost 字段也原样 allowlist；缺失字段不填零。因此模型输出被拒绝时 usage 仍在批次目录中。没有实际模型调用时 usage 是 `null`，不推算任何值。

原生可选字段 `service_tier` 为 `None` 时表示未知，usage 中省略该字段，不补零或推断服务等级。只有这一字段的可空合同已确认；其它字段继续按原有类型校验。

若 Hermes 已返回 final_response/usage，但进程或原生 envelope 失败、usage 类型不合法、`failed` 或路由校验不通过，adapter 仍严格报错。usage 校验失败也保留已返回的 final_response 原文到 `model-output.json`；不合法 usage 不冒充有效计量。`failure.json` 仅保留固定失败码、安全初始化信息，以及 allowlist 内违规字段名和类型，不含字段值、异常全文、stderr 或 config。失败不会写 `accepted.json`、`projection.json` 或 SQLite。缺少路由观测为 unknown；明确观测到不同路由才归为 `route_mismatch`。

`parent_timeout` 仅表示 adapter 等待子进程是否超过外层期限；`parent_timeout=False` 不代表 Hermes 内部 HTTP、首事件或 stale watchdog 未超时。内部超时须依据对应实际证据判断，不能从父进程状态推断。当前 stale=360 秒仅用于本次进程级试验，不是产品全局默认，也不等于 HTTP timeout 或整体 run budget；不据此修改全局配置或推断其它 watchdog 的有效阈值。

输入正文和已接受知识均是不可信数据。文章 prompt 受 Hermes adapter 的 32 KiB UTF-8 上限约束；本模块直接调用 adapter 的 `_render_prompt` 验证最终渲染内容，不复制近似预算。超限会显式报错，不会截掉末尾正文。对超限来源应由人工决定段落任务边界。模型输出必须是 JSON，包含 `knowledge`、`entities` 和 `relations`；文章知识需要 `language: "zh"`，每个引用均为 `{revision_id, locator, quote}`，且 quote 必须逐字是标准段落的子串并至少含一个字母或数字。数字和评测仅能归因给相应原文，不能写成产品保证。

跨来源 Wiki 单独运行，并输入已接受文章而不是重复全文：

```bash
OMNIGRAPH_LOAD_ENV=0 HERMES_API_CALL_STALE_TIMEOUT=360 \
  OMNIGRAPH_HERMES_TIMEOUT_SECONDS=720 \
  OMNIGRAPH_HERMES_PYTHON=/home/sztimhdd/.hermes/hermes-agent/venv/bin/python \
  /home/sztimhdd/OmniGraph-Vault/venv/bin/python -m vitax.production input.json batch-wiki \
  --capture-root /trusted/captures --stage wiki \
  --accepted-article batch-article-alpha/accepted.json \
  --accepted-article batch-article-beta/accepted.json --run-hermes
```

`--stage article` 只接受 `kind="article"`，`--stage wiki` 只接受 `kind="wiki"`。Wiki 必须为当前每个 source revision 提供至少一篇已接受 article，且自身至少引用两个 document revision；同一来源的人工与模型 article 可同时保留，陌生 revision 的 article 会拒绝。prompt 要求说明方法所解决的问题、代价与证据，不把多种方法自动结论为必须同时引入。Wiki 构建会确定性合并 `--accepted-article` 内已有的 documents/evidence/knowledge/entities/relations；同 ID 内容不同直接拒绝，既不重算也不覆盖 article。任何模型 `knowledge_id` 与 `--manual` 中人工知识冲突都会被拒绝，不会覆盖人工版本。

Wiki 模型调用只生成 Wiki 正文和其来源引用，必须返回 `entities: []` 与 `relations: []`。实体和关系由已接受 article projection 原样合并；这样不会为已有图谱重复生成同 ID 但不同标签或引用的记录。新增跨来源关系属于后续有独立证据的切片。

`--sqlite NEW.sqlite` 是可选的最后一步。它只把已接受的白名单投影交给 `vitax.knowledge.build`，因此公开 SQLite 沿用既有 `visibility`、证据边和不可覆盖输出合同。保存同一份 `projection.json` 后，`python -m vitax build projection.json NEW.sqlite` 可重建同一 `release_id` 和公开内容；本切片不额外承诺输出文件的字节相等，也不新增 release 参数或 manifest 引擎。完整 HTML、原始模型输入、raw output、抓取日志与未选图片不进入 SQLite；图片发布本身属于后续 release 切片，但选图结果在私有 accepted artifact 中保留来源、caption 与定位。

若只修正标准化 metadata，使用已保存的实际 `model-output.json` 和 `usage.json` 在新的输出目录离线复建：

```bash
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m vitax.production input.json rebuilt-article \
  --capture-root /trusted/captures --stage article --source-id source-alpha \
  --model-output original/model-output.json --model-receipt original/usage.json
```

该命令不调用 Hermes。新目录的 `model-receipt.json` 记录原始输出和 usage 的绝对路径与 SHA-256；原 artifact 保持不变。

离线 `--model-receipt` 只用于重放已成功的 Hermes 产物。它会通过与在线 Hermes 相同的 adapter usage allowlist 和成功路线校验：`failed` 必须为 `false`，provider/model 必须等于本次授权路线。未知字段不会复制；已知字段类型不符、失败 receipt 或路由不符都会拒绝重建，不写新的 `usage.json`、accepted 或 projection。原始 receipt 只以路径和 hash 记录在 `model-receipt.json`，避免把其未声明字段传播进新 artifact。没有 `--model-receipt` 的显式离线 `--model-output` 保持 usage `null`，不声称它来自 Hermes。
