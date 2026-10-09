# KB-1: Export脚本 (2天)

## Goal
Build `export_knowledge_base.py` — a Python script that reads OmniGraph SQLite, generates Jinja2 HTML pages into `kb/output/` directory, targeting Caddy static serve.

## Input
- SQLite: `~/.hermes/data/kol_scan.db` (articles, ingestions, entity_canonical tables)
- Starting query from D-16:
  ```sql
  SELECT a.id, a.url, a.title, a.content_hash, a.update_time, a.enriched,
         a.layer1_verdict, a.layer2_verdict,
         LENGTH(a.body) AS body_len
  FROM articles a
  WHERE (a.body IS NOT NULL AND LENGTH(a.body) > 200)
     OR EXISTS (SELECT 1 FROM ingestions i WHERE i.article_id = a.id AND i.status = 'ok')
  ORDER BY a.update_time DESC;
  ```

## Output
```
kb/output/
├── index.html              # 首页: 主题卡片 + 最新文章 + 实体云 + 问答入口
├── articles/{hash}.html    # 文章详情页 (× N, SSG)
├── topics/ai-agent.html    # 主题Pillar页 (× 5+)
├── entities/{slug}.html    # 实体集合页 (× N)
├── sources/{slug}.html     # 来源索引页 (× N)
├── ask/index.html           # 问答入口页 (React岛屿容器)
├── assets/style.css
├── sitemap.xml
└── robots.txt
```

## Templates (Jinja2)
- `templates/base.html` — 基模板: 顶栏(搜索栏+导航) + 页脚 + CTA
- `templates/index.html` — 首页: 主题卡片grid + 文章列表 + 实体标签云 + 问答CTA
- `templates/article.html` — 文章页: 面包屑 + 内容 + 侧栏(实体卡片+相关文章) + "有疑问问AI"
- `templates/topic.html` — Pillar页: 主题概览 + 子文章列表
- `templates/entity.html` — 实体页: 描述 + 关联文章列表 + 相关实体
- `templates/ask.html` — 问答页: React岛屿容器 + 热门问题(FAQPage Schema)

## Design Tokens (inherit from vitaclaw-site)
- bg: #0f172a, card: #1e293b, text: #f0f4f8
- accent: #3b82f6, accent-green: #22d3a0
- font: Inter + Noto Sans SC
- card style: rounded-2xl border border-card-border bg-card

## Key Behaviors
- Image URL rewrite: `re.sub(r'http://localhost:8765/', '/static/img/', md)` on final_content.md body
- Breadcrumb: 首页 > 主题 > 文章
- Internal links: article → entity, article → topic, entity → article, article → article (related)
- SEO: JSON-LD Article schema on every article page
- Graceful: article without images still renders (no broken img tags)
