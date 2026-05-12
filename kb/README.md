# 企小勤知识库 (Knowledge Base)

> SEO吸铁石文集 + RAG问答引擎 — 极简MVP

## 快速开始

1. 阅读 `docs/00-KB-KICKOFF-PROMPT.md` — 完整开发启动指令
2. 按KB-1→KB-2→KB-3→KB-4顺序实现
3. 每个里程碑完成后验证再继续

## 文档

| 文件 | 说明 |
|------|------|
| `docs/00-KB-KICKOFF-PROMPT.md` | 开发启动提示词 |
| `docs/01-PRD.md` | 产品需求文档 |
| `docs/02-DECISIONS.md` | 架构决策记录 (D-01~D-20) |
| `docs/03-ARCHITECTURE.md` | 系统架构设计 |
| `docs/04-KB1-EXPORT-SSG.md` | Phase 1: SSG导出脚本 |
| `docs/05-KB2-ENTITY-SEO.md` | Phase 2: 实体索引+SEO |
| `docs/06-KB3-API-QA.md` | Phase 3: FastAPI+问答UI |
| `docs/07-KB4-DEPLOY.md` | Phase 4: 部署上线 |
| `docs/08-SESSION-NOTES.md` | 讨论纪要 |

## 核心决策

- **D-01:** 极简MVP，假设零流量
- **D-04:** 复用 `kg_synthesize.synthesize_response()`
- **D-05:** kb/ 在 OmniGraph-Vault 仓库内
- **D-08:** Python Jinja2 SSG（不用Astro/Next.js）
- **D-11:** 双入口：快速检索(FTS5) + 深度问答(kg_synthesize)
- **D-13:** 部署在Hermes ECS :8766
- **D-14:** 混合内容：final_content.md优先，articles.body fallback
- **D-15:** FastAPI :8766
- **D-18:** 默认FTS5搜索，?mode=kg走LightRAG
- **D-20:** URL用content_hash md5[:10]

## 契约（不可单方面修改）

1. `kg_synthesize.synthesize_response(query_text, mode)` 签名
2. `omnigraph_search.query.search(query_text, mode)` 签名
3. `kol_scan.db` 表结构 (articles, classifications, extracted_entities, entity_canonical, ingestions)
4. `images/{hash}/final_content.md` + `metadata.json` 路径与命名

如需修改契约，commit message必须包含 `BREAKING: kb-contract-X`。

## 技术

- Python 3.11+ / FastAPI / Jinja2 / SQLite FTS5
- 暗色主题 (#0f172a) / Inter + Noto Sans SC
- Caddy反向代理 / systemd / uvicorn :8766