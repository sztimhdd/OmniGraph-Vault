"""Quick mock-data test for the batch classification algorithm."""
import sys
import os
import json
from pathlib import Path

# --- Load env from WSL hermes path ---
dotenv = Path("//wsl.localhost/Ubuntu-24.04/home/sztimhdd/.hermes/.env")
if dotenv.exists():
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key and val and key not in os.environ:
            os.environ[key] = val

sys.path.insert(0, str(Path(__file__).parent))
from batch_ingest_from_spider import batch_classify_articles, print_filter_summary

# --- Mock articles: mix of AI, tech, non-tech, and shallow content ---
mock_articles = [
    {
        "title": "DeepSeek-V3 技术架构深度解析：MoE 与 Multi-Head Latent Attention",
        "digest": "本文从论文出发详细拆解 DeepSeek-V3 的 Mixture of Experts 架构设计..."
    },
    {
        "title": "LLM Agent 记忆系统设计：从短期记忆到持久化知识图谱",
        "digest": "探讨 AI Agent 如何构建层次化记忆体系，包括工作记忆、情景记忆和语义记忆..."
    },
    {
        "title": "【活动通知】本周六线下 AI 茶话会报名开启",
        "digest": "欢迎大家参加本周六下午的线下交流活动，地点在深圳南山..."
    },
    {
        "title": "LangChain vs LlamaIndex: RAG 框架选型对比 2026",
        "digest": "全面对比两大 RAG 框架在文档解析、检索策略、Agent 集成等方面的差异..."
    },
    {
        "title": "公司年会精彩回顾：感恩有你，共创未来",
        "digest": "上周末公司年会在三亚举行，精彩节目和抽奖环节让大家难忘..."
    },
    {
        "title": "用 100 行代码实现一个 Multi-Agent 协作系统",
        "digest": "手把手教你从零搭建多 Agent 协作框架，基于 OpenAI Agents SDK..."
    },
    {
        "title": "突发！某大厂宣布开源万亿参数 MoE 模型",
        "digest": "今日凌晨，XX 公司宣布将旗下万亿参数 MoE 大模型完全开源..."
    },
    {
        "title": "【招聘】后端工程师 / 前端工程师 / AI 研究员",
        "digest": "我们正在寻找有激情的工程师加入团队，工作地点北京/上海/远程..."
    },
    {
        "title": "Python 3.13 无 GIL 模式实战：性能提升与兼容性踩坑",
        "digest": "Python 3.13 正式支持无 GIL 模式，本文在一台 64 核机器上实测..."
    },
    {
        "title": "AI Agent 自主编程能力评估：SWE-Bench Verified 最新排名",
        "digest": "最新的 SWE-Bench Verified 榜单显示 AI Agent 编程能力大幅提升..."
    },
    {
        "title": "周末去哪儿：深圳周边 5 个绝美露营地推荐",
        "digest": "深圳周边有许多适合露营的好地方，本文整理了 5 个交通便利的营地..."
    },
    {
        "title": "RAG 检索增强生成最新进展：Graph RAG 与 Hybrid Search",
        "digest": "传统 RAG 面临检索精度瓶颈，Graph RAG 和混合检索成为新的突破方向..."
    },
]

print(f"=== Testing Gemini Classifier ===")
print(f"Input: {len(mock_articles)} mock articles")
print(f"Topic filter: 'AI Agent'")
print(f"Min depth: 2\n")

passed, filtered = batch_classify_articles(
    mock_articles, topic_filter="AI Agent", exclude_topics=None, min_depth=2, classifier="gemini"
)

print_filter_summary(passed, filtered)
print()

if passed:
    print("Passed articles:")
    for a in passed:
        print(f"  [depth={a.get('depth_score')}] {a['title']}")
if filtered:
    print("\nFiltered out:")
    for a in filtered:
        reason = a.get("filter_reason", "?")
        print(f"  [{reason}] {a['title']}")

# --- Also test with DeepSeek ---
print(f"\n\n=== Testing DeepSeek Classifier ===")
passed2, filtered2 = batch_classify_articles(
    mock_articles, topic_filter="AI Agent", exclude_topics=None, min_depth=2, classifier="deepseek"
)

print_filter_summary(passed2, filtered2)
print()

if passed2:
    print("Passed articles:")
    for a in passed2:
        print(f"  [depth={a.get('depth_score')}] {a['title']}")
if filtered2:
    print("\nFiltered out:")
    for a in filtered2:
        reason = a.get("filter_reason", "?")
        print(f"  [{reason}] {a['title']}")
