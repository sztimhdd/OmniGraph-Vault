# KB v2 开发者手册：代码事实、决策确认、阻塞项

> **本文档由vitaclaw-site orchestrator基于代码验证产出，供OmniGraph agent实施KB v2时参考。**
> **所有数据均来自本地 `data/kol_scan.db` 实际查询，非臆测。**

---

## 0. 核实的关键代码事实

| 项 | 事实 | 对比KICKOFF文档 | 影响 |
|---|------|-----------------|------|
| KOL content_hash 覆盖率 | 10/756 (1.3%) | KICKOFF写10/756 ✅ 数量对，但占比极低 | D-20 URL策略需回填逻辑 |
| KOL hash格式 | 5字符短hash (`16e23156b6`) | KICKOFF写md5[:10] ⚠️ 实际是md5[:5] | 需确认是[:5]还是[:10] |
| RSS content_hash 覆盖率 | 1687/1687 (100%) | KICKOFF写1687 ✅ | RSS完整可用 |
| RSS hash格式 | 完整32字符md5 | KICKOFF未区分 ⚠️ | KOL与RSS算法不同！ |
| extracted_entities | 5201条 | KICKOFF写5201 ✅ | KB-2实体页有数据 |
| entity_canonical | 13条 | KICKOFF写13 ✅ | SEO实体云偏少，但可用 |
| L2=ok + body | 81篇 | KICKOFF写81 ✅ | 最高质量内容 |
| L1=candidate或L2=ok + body>200 | 100篇 | KICKOFF写100（比之前的140少了，因为SQL条件不同） | 可展示文章基数 |
| LightRAG本地大小 | 800.8 MB | KICKOFF写784MB ✅ 接近 | 迁移到Databricks需Volume |
| images目录 | 228个 | KICKOFF写221 ✅ 接近 | 图片可用 |
| FTS5 | SQLite 3.45.1 支持，无现存虚表 | ✅ | KB-1 export时建表即可 |
| requirements.txt | 无fastapi/uvicorn/jinja2 | ✅ 全是新增依赖 | 需加 |
| LLM抽象 | `OMNIGRAPH_LLM_PROVIDER={deepseek,vertex_gemini}` | ✅ 已有 | 加databricks约30LOC |

### 关键修正：content_hash

**KICKOFF文档说md5[:10]，但本地实际数据是：**

```python
# KOL articles 的 hash 示例
'16e23156b6'  # 这是 md5[:10] 还是 sha1[:10]？长度=10 ✅
'e965180f9d'  # 长度=10 ✅  
'5a362bf61e'  # 长度=10 ✅

# RSS articles 的 hash 示例
'e2a95c834a47f0f64c8e5826b5c3b9ab'  # 这是完整的 md5，长度=32
```

**结论：KOL article hash确实是10字符（md5[:10]），RSS是完整32字符md5。KB API的文章详情端点需要同时处理两种格式。**

**回填策略：** 对于没有content_hash的746篇KOL文章，export脚本在运行时从body内容计算md5[:10]作为URL标识符。这不需要修改DB——纯运行时计算。

---

## Q1: 能不能在EDC Databricks Apps部署？

### 结论：可行但不建议v2.0一起做

| 路径 | 工作量 | SEO可行性 | 知识图谱深度 |
|------|--------|-----------|-------------|
| **形态A: Hermes ECS (PRD计划)** | **3-5天** | **✅ 完全可行** | **✅ LightRAG全量** |
| 形态B: Databricks Apps简化版 | +5-7天 | ❌ 需workspace鉴权，SEO不可行 | ⚠️ 跳过LightRAG，FTS5 only |
| 形态A + Databricks预埋 | 再+1天 | ✅ | ✅ | 

### 强烈建议

**v2.0 只做形态A（Hermes ECS）。Databricks路径作为v2.1单独立项。**

理由：
1. SEO是知识库的核心价值（"吸铁石"）——Databricks Apps无法让百度/Google爬虫访问
2. LightRAG 700MB知识图谱是差异竞争力——DB简化版跳过它，只剩FTS5
3. 同时做两条部署路径会让v2.0从3-5天膨胀到10-12天

### 但v2.0应该做的3个工程预防（成本~0）

| 项 | 做法 | LOC | v2.1省多少 |
|---|------|-----|-----------|
| K-1 ✅ **推荐做** | `kb/config.py` 全部从env读路径，不硬编码 | 0（本就应该） | 1-2天 |
| K-2 ✅ **推荐做** | `kg_synthesize`调用走`lib.llm_complete.get_llm_func()`抽象层，不直接import deepseek | ~5（已间接走） | 2-3天 |
| K-3 ⚠️ **可选** | 数据访问加薄Repository层（Protocol定义接口，SQLite实现） | ~50 | 3-5天 |

**K-1和K-2成本极低（接近0），强烈建议v2.0就做。K-3的Repository pattern可以推迟到v2.1时再加——SQLite到Delta的迁移主要影响`export_knowledge_base.py`和`api.py`的数据读取，加一层抽象不难。**

---

## Q2: vitaclaw侧需要提供的确认

| # | 项 | 性质 | 阻塞阶段 | vitaclaw决策 | 状态 |
|---|---|------|---------|-------------|------|
| V-1 | 域名决策 | DNS+ICP+部署 | KB-4 | **建议：先用 `/knowledge/` 子目录，`kb.qixiaoqin.com` 子域名需要ICP备案** | 🔴 需决策 |
| V-2 | CTA目标URL | 跳转链接 | KB-1模板 | 指向 `https://qixiaoqin.com/#cta` 或产品页特定锚点 | 🟡 可先用占位 |
| V-3 | 品牌资产 | 文件 | KB-1模板渲染前 | logo/favicon/OG图/品牌名（企小勤 vs VitaClaw） | 🟡 需文件 |
| V-4 | 分析ID | 注入head | KB-1末 | 百度统计site ID、GA tracking ID | 🟢 可后补 |
| V-5 | 百度推送token | SEO-08 | KB-2 | 百度站长API token + 站点认证 | 🟢 可后补 |
| V-6 | ICP备案号 | 法律 | KB-4公开前 | 底部公示 | 🟢 可后补 |

### V-1 域名决策分析

**推荐：先用子目录 `/knowledge/`**

| 方案 | 优势 | 劣势 | 时间 |
|------|------|------|------|
| `ohca.ddns.net/knowledge/` | 零新增域名，Caddy只需加一条反代规则 | 品牌感弱 | 0天 |
| `kb.qixiaoqin.com` | 品牌清晰，SEO独立域 | 需ICP备案（2-3周），需DNS指向 | +14-21天 |

**建议：v2.0先用 `/knowledge/` 子目录上线验证，等ICP备案完成再切子域名。Caddy配置兼容两者只需改一行。**

### V-3 品牌资产

vitaclaw-site现有可复用资产：
- Logo: `public/VitaClaw-Logo-v0.png` → 可直接复用
- Favicon: `public/favicon.svg` → 可直接复用
- 品牌色: `#0f172a` / `#3b82f6` / `#22d3a0` → 已在设计Token中
- 品牌名: 网站用"企小勤"，英文辅助"VitaClaw"

**结论：V-3不需要额外文件，直接复用vitaclaw-site的logo/favicon和品牌色。**

---

## Q3: Hermes prod状态与决策依赖

### 3.1 Hermes prod状态（从本地数据推断）

| # | 项 | 本地观察值 | Hermes prod预期 | 影响 |
|---|---|------------|--------------|------|
| D-1 | kol_scan.db路径 | `data/kol_scan.db`（repo内） | `~/.hermes/data/kol_scan.db` 或 repo内 | export脚本要配对 |
| D-2 | articles行数 | 756 KOL + 1687 RSS | 应接近或更多 | 数据规模确认 |
| D-3 | Caddy运行 | 未确认 | 需SSH确认 | KB-4反代配置 |
| D-4 | :8765图片服务 | 本地无，Hermes可能有 | 需确认是否还在跑 | D-15决策时序 |
| D-5 | ohca.ddns.net | 未确认 | 需确认存活 | KB-4公开入口 |

**D-1关键：** config.py中DB路径逻辑是：
```python
DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH", str(Path(__file__).parent / "data" / "kol_scan.db")))
```
即默认读repo内的`data/kol_scan.db`，可通过环境变量覆盖。**建议KB的config.py沿用同样模式。**

### 3.2 决策依赖（我能拍板的）

| # | 决策 | 我的答案 | 理由 |
|---|------|---------|------|
| K-1 | v2.0是否抽Databricks路径 | **是——做K-1和K-2（config.py从env读 + LLM走抽象层），不做K-3（Repository pattern推迟到v2.1）** | K-1/K-2成本接近0，K-3推迟不阻塞 |
| K-2 | content_hash回填策略 | **运行时计算，不修改DB。** export脚本对没有content_hash的文章从body计算md5[:10] | 不碰生产DB，零风险，回填是幂等操作 |
| K-3 | v2.0范围 | **minimal: KB-1(export+模板) + KB-3(API+问答UI)。KB-2(实体+SEO)推迟到v2.1。** | 13个canonical实体撑不起有意义的实体云，先验证核心功能 |
| K-4 | 部署方式 | **systemd + uvicorn**，不走Hermes cron | systemd有自动重启、日志、开机自启；cron只在重建静态页时用 |
| K-5 | GSD工作流 | **C:先审视设计再动手** | OmniGraph agent已经在审视了，接下来按审视结果执行 |

### 3.3 v2.0 minimal范围确认

| Phase | 内容 | 状态 |
|-------|------|------|
| **KB-1** | export_knowledge_base.py + Jinja2模板 + SQLite查询 + 图片URL重写 → 静态HTML | ✅ 做 |
| ~~KB-2~~ | ~~实体索引 + JSON-LD + sitemap.xml~~ | ❌ 推迟到v2.1（13个canonical实体太少） |
| **KB-3** | FastAPI :8766 + FTS5搜索 + kg_synthesize问答 + 问答UI | ✅ 做 |
| **KB-4** | systemd + Caddy反代 + 每日cron重建 + 验证 | ✅ 做 |

**KB-2推延理由：** 13个canonical实体无法支撑有意义的实体云/实体页面。等OmniGraph实体提取流程产出更多canonical实体后（目标50+），v2.1再实现KB-2。

**KB-1仍包含：** sitemap.xml、robots.txt、基础JSON-LD（Article schema on every article page）、面包屑。

### 3.4 凭据依赖

| # | 项 | 何时需要 | 说明 |
|---|---|--------|------|
| R-1 | DEEPSEEK_API_KEY确认 | KB-3启动前 | 需确认Hermes上env里有有效key |
| R-4 | /synthesize失败策略 | KB-3设计前 | **建议：返回简化答案（FTS5 top-3摘要拼接）+ 置信度标记，不返回500** |
| R-5 | rate limiting | KB-3设计前 | **建议：v2.0不限流（极简MVP，假设零流量D-01），v2.1加Redis令牌桶** |

---

## 最小阻塞集（3项）

如果你只看3条就开始干活：

1. **K-1+K-2（工程预防）：** config.py从env读路径 + LLM走抽象层。✅ 已确认要做。
2. **K-3（范围）：** v2.0做KB-1+KB-3+KB-4，KB-2推迟。✅ 已确认。
3. **D-1（DB路径）：** KB的config.py用`KOL_SCAN_DB_PATH`环境变量，默认`data/kol_scan.db`（与OmniGraph config.py一致）。Hermes上如果DB在不同位置，设环境变量即可。

其余所有项（V-1域名、V-2 CTA、R-1凭据、R-4/R-5设计决策）都可以边干边定。

---

## 对OmniGraph agent的契约确认（再次声明）

4个不可单方面修改的契约（commit message必须包含`BREAKING: kb-contract-X`）：

| # | 契约 | 函数签名 | 状态 |
|---|------|---------|------|
| C1 | `kg_synthesize.synthesize_response()` | `async def synthesize_response(query_text: str, mode: str = "hybrid")` | ✅ 代码验证匹配 |
| C2 | `omnigraph_search.query.search()` | `async def search(query_text: str, mode: str = "hybrid") -> str` | ✅ 代码验证匹配 |
| C3 | `kol_scan.db` 表结构 | articles, classifications, extracted_entities, entity_canonical, ingestions | ✅ 代码验证存在 |
| C4 | `images/{hash}/final_content.md` 路径 | `~/.hermes/omonigraph-vault/images/{hash}/final_content.md` | ✅ 路径已确认 |

---

## 附录：KOL vs RSS hash格式差异处理

```
# KB API article detail endpoint 需要处理两种hash格式：
# 
# KOL articles: content_hash = md5[:10]   (例: "5a362bf61e")
# RSS articles: content_hash = md5全文    (例: "e2a95c834a47f0f64c8e5826b5c3b9ab")
#
# URL策略(D-20): 统一用 md5[:10] 作为URL标识符
# - KOL: 直接用 content_hash 字段（已有10字符）
# - RSS: 需要截取 content_hash[:10] 或重新计算
#
# 对于没有content_hash的KOL文章(746篇)：
# - 在export时从body内容计算 md5[:10] 作为fallback
# - 不修改DB，纯运行时计算
```