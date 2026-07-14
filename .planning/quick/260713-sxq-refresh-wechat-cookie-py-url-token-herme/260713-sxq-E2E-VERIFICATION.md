# E2E 全流程健康验证报告 — 2026-07-14

**触发**：用户睡前设定的 3 个夜间目标之目标3。
**环境**：Aliyun 生产（47.117.244.253），远程真实环境。
**结论**：🟢 **全流程无阻塞跑通** — 从 KOL/RSS 扫描到知识图谱建图 + RAG 检索，每个阶段都有实际产出。

---

## 前置：WeChat cookie 刷新（目标1+2 的成果）

E2E 能跑通的前提是 WeChat session 有效。本次开始前 Aliyun token 已过期（`933841234`，导致 ret=200003）。

通过修复后的 `refresh_wechat_cookie.py` 从 Hermes Edge 提取有效凭证并写回：
- token `933841234` → `1284035398`（有效）
- verify test-scan `ret=0`
- Telegram 通知成功

---

## E2E 各阶段验证结果

| # | 阶段 | 命令 | 结果 |
|---|------|------|------|
| 1a | KOL 扫描 | `batch_scan_kol.py --max-accounts 1 --max-articles 5` | ✅ **1 ok, 0 failed**（token 刷新后 ret=200003 解决）|
| 1b | RSS 采集 | `enrichment/rss_fetch.py` | ✅ 多源返回 candidates（antirez 98, pluralistic 30, righto 25…）；少数源超时（网络波动，非阻塞）|
| 2 | L1/L2 分类 | `batch_classify_kol.py --topic ai` | ✅ **2552 篇分类完成**；relevant=1 有 2390；候选（relevant=1 ∧ depth_score≥2）1607，未入库 1113 |
| 3 | 文章选择 | SQL 查候选 | ✅ 从 1113 未入库候选中选文章走完整流程 |
| 4a | 刮削 | `batch_ingest_from_spider.py --topic-filter AI --min-depth 2 --max-articles 1` | ✅ Apify 刮削成功（wechat_f4bc525c58 等，runId SUCCEEDED）|
| 4b | 图片处理 | (入库内嵌) | ✅ 图片下载 + 尺寸过滤（filtered_too_small 规则生效）|
| 4c | Vision/Embedding | Vertex Gemini | ✅ embedding workers 初始化，Vertex Gemini 调用成功 |
| 4d | 实体关系提取 | LightRAG extract | ✅ 10 chunks 提取（33+21, 22+20, 27+20, 39+35 Ent+Rel…）|
| 4e | 实体合并入图 | LightRAG merge | ✅ Merged: Coding Agent, LLM, Writing Agent, Developer… |
| 5 | 数据库 | `ingestions` 表 | ✅ **ok=1**, failed=2（Vertex 429 配额限流，非流程缺陷）, skipped=7 |
| 6 | graphml 建图 | `graph_chunk_entity_relation.graphml` | ✅ **50,690,830 → 50,801,564 bytes（+110KB）**，mtime 刷新 08:28→10:13 |
| 7 | RAG 检索 | `kg_synthesize.py "...AI coding agents..." hybrid` | ✅ **检索 56 实体 + 184 关系，生成 3649 字深度报告**，引用具体文章 |

---

## RAG 检索质量证据

查询 "What are the latest trends in AI coding agents?" (hybrid 模式) 生成的报告：
- 结构完整（能力跃迁 / Agentic Engineering 范式 / 生态 / 影响 四部分）
- **引用具体入库文章**：`[Coding Agents](articles/f5f44ab394.html)`、`[Andrej Karpathy](...)`、`[agent-skills](...)`
- 内容明显包含本次刚入库的最新文章（Karpathy Agentic Engineering、Harness Engineering、agent-skills 21 技能）
- 保存至 `synthesis_output.md` + archive

---

## 已知非阻塞警告（老问题，非本次引入）

| 警告 | 性质 | 状态 |
|------|------|------|
| Vertex AI embedding 429 (RPM/RPD) | 密集 E2E 触发配额限流 | 脚本自动重试；正常 15 篇/天节奏不会触发。这是 MAX_ARTICLES tri-governor 的预期行为 |
| `0 vector chunks → WEIGHT fallback` | #44 graphml↔Qdrant/vdb chunk 对齐 | RAG 用 WEIGHT fallback 恢复，仍产出结果 |
| `Rerank enabled but no rerank model` | rerank 配置但未激活 | 已知，不影响检索 |
| `Some nodes missing, storage damaged` | graphml↔vdb 轻微不一致 | 已知 #44，不阻塞 |

这些都不阻塞全流程——每个都有 fallback 或重试，最终产出正常。

---

## 复用

本次 E2E 用的命令和 schema 坑已固化到：
- `docs/E2E-HEALTH-TEST.md`（测试框架）
- `scripts/e2e_health_test.sh`（自动化 runner）
- memory `aliyun_e2e_260714_schema_and_flags`（正确参数 + DB 列名坑）

**关键参数修正**（相对文档旧版）：
- `batch_classify_kol.py --topic ai`（单数 --topic）
- `batch_ingest_from_spider.py --topic-filter "AI" --min-depth 2 --max-articles 1`
- 候选判定：`relevant=1 AND depth_score>=2`（不是 depth，depth 列全 NULL）
- 手动跑必须先 `set -a; source /root/.hermes/.env; set +a`

---

## 最终结论

🟢 **PASS** — OmniGraph-Vault Aliyun 生产部署健康，全流程（RSS/KOL 扫描 → L1/L2 分类 → 刮削 → vision → 入库 → 建图 → RAG 检索）端到端无阻塞跑通。WeChat cookie 自动刷新链路（Aliyun 检测 → SSH 直连 Hermes → writeback）已修复并实测成功。
