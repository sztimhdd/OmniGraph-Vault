# 知识库 v2 设计决策记录

> 2026-05-11 讨论纪要。所有架构决策记录于此，后续执行以本文档为锚点。

---

## D-01: 知识库规模策略

**决策:** 极简极轻MVP，假设根本没人用

**理由:**
- 不假设流量，不预建复杂架构
- 验证假设后再升级路线，不影响初期交付

**后果:**
- 不用Astro/Next.js，只用Python+Jinja2
- 1周内上线，亏也只亏1周

---

## D-02: 内容范围

**决策:** 仅展示 Layer1/Layer2 `curationStatus: passed` 的文章

**理由:**
- 质量优先，SEO惩罚不可逆
- 来源文章必须可追溯

**后果:**
- 初始文章量有限（~50-100篇），但质量有保证
- 后续可扩展分类标准

---

## D-03: 内容形式

**决策:** AI摘要 + 原文链接（非全文转载）

**理由:**
- 版权安全，不侵权
- 不替代原文阅读流量
- 搜索引擎青睐原创摘要

**后果:**
- 文章页内容较薄，依赖内部链接网络补偿
- 用户需要点击原文获取完整信息

---

## D-04: 问答引擎 v1 后端

**决策:** 直接复用 `kg_synthesize.synthesize_response()` — 不是新写RAG引擎

**理由:**
- `kg_synthesize.py` 已生产验证，含完整的 LightRAG 检索 + 实体归一化 + 历史注入 + 图片保持
- 只需要 ~50 行 Python 包装成 HTTP API
- 不等 Agentic-RAG v1（还没实现）

**后果:**
- 知识库问答 = 整个 LightRAG 图谱检索（~700MB），不是37个文档块
- 答案图文并茂（Markdown + 内嵌图片）
- 依赖图片服务器运行（`localhost:8765`）

---

## D-05: 项目结构

**决策:** 独立Python项目（非扩展现有Vite SPA），与 `vitaclaw-site/` 并列

**结构:**
```
vitaclaw-site/
├── kb/                    # 知识库 Python 项目
│   ├── export/           # 导出脚本
│   ├── templates/        # Jinja2 模板
│   └── output/           # 构建产出 (Caddy直接serve)
├── server/               # Express (共享)
│   └── kb_api.py         # kg_synthesize HTTP包装 (新增)
└── .planning/            # GSD规划
    └── v2-knowledgebase/ # v2阶段计划
```

**不是独立仓库。** 与 vitaclaw-site 同仓库，共享设计语言、域名、部署流程。

---

## D-06: 图片服务

**决策:** 本地图片服务器 + Caddy反向代理

**实现:**
```
~/.hermes/omonigraph-vault/images/  →  python -m http.server 8765  →  Caddy /images/*  →  公网
```

**理由:** 不复制图片，不嵌入base64。运行时引用但不增加构建体积。

---

## D-07: 问答无需登录

**决策:** 完全公开，零门槛

**理由:** 降低使用门槛，SEO友好，搜索引擎可索引问答内容

---

## D-08: 域名策略

**决策（待定）:** `kb.qixiaoqin.com` 或 `qixiaoqin.com/knowledge/`

**建议:** 子域名。但初期 `knowledge/` 子目录也可接受。

---

## D-09: 内容更新频率

**决策:** 每日自动重建（cron触发 `export_knowledge_base.py` → SSG重建 → Caddy reload）

**实现:** 与现有 OmniGraph cron pipeline 耦合。

---

## D-10: ui-ux-pro-max 设计指引

**推荐:**
- 模式: FAQ/Documentation Landing（文档知识库正匹配）
- 风格: Minimalism & Swiss Style
- 首屏: 搜索栏突出 + 热门分类 + FAQ
- 拒绝: 浅色主题 #F8FAFC（与品牌暗色不匹配，保留 #0f172a）

---

## 待定项

- [ ] D-08: 域名确认 `kb.qixiaoqin.com` vs `qixiaoqin.com/knowledge/`

---
## 交互设计决策

### D-11: 双搜索/问答入口

**决策:** 两个独立入口，分场景使用，不合并

| 入口 | 名称 | 用户意图 | 后端 | 速度 | LLM |
|------|------|---------|------|------|-----|
| 入口1 | 快速检索过滤 | "查资料" — 知道要找什么文章/实体 | 客户端JS过滤预索引数据 | <100ms | ❌ 不需要 |
| 入口2 | 深度图文问答 | "问问题" — 有具体疑问需要解答 | kg_synthesize.synthesize_response() (LightRAG+DeepSeek) | 3-10s | ✅ DeepSeek+Gemini |

**入口1 交互方式:**
- 全局搜索栏（首页顶栏 + 全站导航区域）
- 主题导航卡片
- 实体标签云
- 点击实体标签 → 实体集合页（显示所有关联文章）
- 点击主题 → Pillar页（显示所有子文章）
- 搜索框 → 前端JS即时过滤（标题+标签+实体名）

**入口2 交互方式:**
- 独立 /ask/ 页面（URL: kb.qixiaoqin.com/ask/）
- 各页面底部"有疑问？问AI →" CTA链接
- 自然语言问题输入框
- 回答以Markdown渲染（含图片）
- 来源文章链接（链接到知识库文章页，内部链接SEO）
- 相关实体标签（链接到实体页）
- 回答底部: "有帮助/没帮助" 反馈

**两个入口的页面协作:**
- 文章详情页侧边栏: 实体卡片 → 点击 → 实体页
- 实体页面: 关联文章列表 → 点击 → 文章页
- 问答回答: 来源文章链接 → 点击 → 文章页
- 问答回答: 实体标签 → 点击 → 实体页
- 不要: 在同一页面合并搜索栏和问答框（用户场景不同）

### D-12: 设计语言（继承vitaclaw-site暗色主题）

| 属性 | 值 | 来源 |
|------|-----|------|
| 背景 | #0f172a | vitaclaw-site token |
| 卡片区 | #1e293b | vitaclaw-site token |
| 文字 | #f0f4f8 | vitaclaw-site token |
| 次级文字 | #94a3b8 | vitaclaw-site token |
| 强调蓝 | #3b82f6 | vitaclaw-site token |
| 强调绿 | #22d3a0 | vitaclaw-site token |
| 边框 | rgba(255,255,255,0.08) | vitaclaw-site token |
| 卡片悬浮 | #2a3a4a | 新增（知识库需要） |
| 字体 | Inter + Noto Sans SC | vitaclaw-site font stack |
| 卡片 | rounded-2xl border border-card-border bg-card | vitaclaw-site pattern |
| CTA按钮 | .glow 类 | vitaclaw-site utility |

**抗拒绝:**
- ui-ux-pro-max 推荐的浅色主题 (#F8FAFC) — 不采用，保持品牌一致
- ui-ux-pro-max 推荐的 Plus Jakarta Sans — 不采用，保持 Inter + Noto Sans SC

**ui-ux-pro-max 推荐的模式（采用）:**
- 模式: FAQ/Documentation Landing
- 首屏: 搜索栏突出 + 热门分类
- 转化: 未解决提问转联系CTA
- 风格方向: Minimalism & Swiss Style（暗色版）

---
## OmniGraph集成决策 (2026-05-12 编码Agent确认)

### D-13: 知识库Web服务部署位置

**决策:** 跑在Hermes服务器上（选项A）

**理由**（按重要性排列）:
1. 数据已经在目标机 —— `~/.hermes/omonigraph-vault/images/` + `~/.hermes/data/kol_scan.db`，零数据传输
2. 资源抢占是伪命题 —— daily-ingest cron (08:00-10:00 ADT) 是IO+网络bound，FastAPI idle ~30MB RAM / 0% CPU
3. 同机已有image server (:8765)，加:8766是同一模式延伸，运维心智零增量
4. rsync方案(B)是反模式 —— 两份数据源极易"前端vs真实库不一致"
5. HTTP暴露方案(C)是A的子集

**执行形态:** Hermes上`uvicorn app:app --port 8766`，Caddy反代 + `ohca.ddns.net` DDNS暴露HTTPS
**开发期:** SSH端口转发 `-L 8766:localhost:8766`

---

### D-14: 文章内容展示策略

**决策:** 混合模式 —— 列表/索引走SQLite，详情页优先final_content.md，fallback articles.body

**详情页路由逻辑:**
```python
def get_article_body(article_hash, article_id):
    md_path = IMAGES_DIR / article_hash / "final_content.enriched.md"
    if not md_path.exists():
        md_path = IMAGES_DIR / article_hash / "final_content.md"
    if md_path.exists():
        return md_path.read_text(), "vision_enriched"
    body = db.execute("SELECT body FROM articles WHERE id=?", [article_id]).fetchone()
    return body[0], "raw_markdown"
```

**前端约束:**
- 返回source字段: `"vision_enriched"` 或 `"raw_markdown"`
- UI明确标注"本篇含图片描述"或"本篇仅文本"
- 不要两个同时展示（enriched.md已包含原文）

**图片URL重写:** `re.sub(r'http://localhost:8765/', '/static/img/', md)`

---

### D-15: HTTP API设计 (FastAPI on Hermes)

**决策:** Hermes同机FastAPI :8766，4个端点，Caddy反代

| 端点 | 实现 | 约束 |
|------|------|------|
| `GET /articles` | SQLite查询 | 不走文件系统stat；支持`?source=wechat|rss` / `?enriched=2` / `?layer1=candidate` |
| `GET /article/{hash}` | 查文件系统 | 用content_hash (md5[:10])不是DB id。URL stability——hash不会因DB reseed漂移 |
| `GET /search?q=` | 默认SQLite FTS5 | FTS5 <10ms；`?mode=kg`才走LightRAG (5-30s异步)。不要默认LightRAG |
| `POST /synthesize` | 异步BackgroundTasks | synthesize_response() 30s+。MVP:轮询GET /synthesize/{job_id}。未来:SSE |

**额外:** FastAPI接管图片服务 —— `app.mount("/static/img", StaticFiles(directory=IMAGES_DIR))`。从此一个端口、一个反代规则。`python -m http.server 8765`可下线。

---

### D-16: 起始数据量

**决策:** 立即启动，不等数据积累

| 数据项 | 数量 |
|--------|------|
| KOL文章总数 | 653 |
| KOL有body | 289 |
| KOL enriched=2 | 1 |
| 完整目录(final_content.md+图片) | 15 |
| RSS文章总数 | 1600 |
| ingest status=ok | 122 |
| **MVP起手查询** | **≥290行 (见D-16 SQL)** |

**SQL query:**
```sql
SELECT a.id, a.url, a.title, a.content_hash, a.update_time, a.enriched,
       a.layer1_verdict, a.layer2_verdict,
       LENGTH(a.body) AS body_len
FROM articles a
WHERE (a.body IS NOT NULL AND LENGTH(a.body) > 200)
   OR EXISTS (SELECT 1 FROM ingestions i WHERE i.article_id = a.id AND i.status = 'ok')
ORDER BY a.update_time DESC;
```

**理由:** MVP验证的是结构不是规模。30篇文章就足以暴露全部视觉/布局问题。数据每天增长20-50篇。

---

### D-17: 图片URL策略

**决策:** 运行时正则重写 final_content.md 中的图片URL

```python
# 将硬编码的localhost:8765替换为FastAPI静态路径
md = re.sub(r'http://localhost:8765/', '/static/img/', md)
```

**理由:** final_content.md写入时硬编码了`http://localhost:8765/{hash}/{N}.jpg`，部署到非本机就全坏。重写是零回填的修复方案。

---

### D-18: 搜索架构

**决策:** 默认SQLite FTS5，可选LightRAG

| 模式 | 后端 | 延迟 | 适用场景 |
|------|------|------|---------|
| 默认 | SQLite FTS5虚表 (articles.title + articles.body) | <10ms | 95%的关键词搜索 |
| `?mode=kg` | LightRAG hybrid query | 5-30s (异步) | 语义搜索/深度查询 |

**实现:** SQLite建FTS5虚表，定时重建索引。

---

### D-19: 合成回答异步模式

**决策:** MVP用BackgroundTasks + 轮询，架构预留SSE路径

```
POST /synthesize { question } → 202 { job_id }
    ↓ 后台: kg_synthesize.synthesize_response() 30s+
    ↓
GET /synthesize/{job_id} → { status: "running" | "done" | "failed", result: "..." }
```

**改SSE时的接口不变:** POST返回相同job_id，只是推流方式从轮询变SSE。

---

### D-20: URL标识符

**决策:** 用 content_hash (md5[:10]) 作为文章URL主键

```
/articles/{hash}  而非  /articles/{db_id}
```

**理由:** DB id可能因reseed漂移，content_hash是内容散列值，稳定不变。

### 已知间隙 (需进一步clarify)

- [ ] SQLite FTS5虚表同步策略（构建时重建 vs 实时增量）
- [ ] Caddy反代具体端口路径映射
- [ ] Hermes上systemd服务定义
- [ ] ohca.ddns.net DDNS更新机制
