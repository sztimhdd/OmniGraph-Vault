# VitaX（原 OmniGraph-Vault）

个人知识库项目：文章采集、知识图谱检索、研究报告、知识库 Web 页面与 MCP 接口。
此目录是唯一源码根目录；不再通过历史目录或快捷链接进入代码。

## 开始工作

先读 [AGENTS.md](AGENTS.md)，再查 [文档索引](docs/README.md) 与 [已知问题](.planning/ISSUES.md)。
本次基线为 GitHub main `dca7c772a8c95125d275ec50b2944ff00713667a`（2026-09-03）。
这是源码基线，不代表本机或远程服务已经部署、健康或通过 UAT。

## 目录

| 路径 | 用途 |
| --- | --- |
| 根目录 Python 脚本 | 采集、批处理、查询、API / MCP 入口 |
| `lib/`、`enrichment/`、`spiders/` | 共享客户端、研究、增强、抓取 |
| `kb/`、`omnigraph_search/` | 知识库网站、搜索与数据接口 |
| `tests/`、`test/fixtures/` | 单元／集成测试与基准素材，两者均有调用方 |
| `scripts/`、`migrations/` | 运维工具、验证工具、版本迁移 |
| `deploy/`、`databricks-deploy/` | 部署源码；执行前确认目标环境 |
| `skills/` | 项目提供的 Agent 技能 |
| `config/`、`data/` | 已跟踪配置、订阅种子和测试基线 |
| `docs/`、`specs/` | 开发、接口、运维和设计文档 |

## Python 环境

项目声明 Python >=3.11，建议使用 Python 3.12 创建全新的环境。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
# 涉及 KB 时，另装其依赖：
.venv/bin/python -m pip install -r requirements-kb.txt
```

上面是安装说明；整理过程不自动安装整套模型、启动服务或执行采集。
依赖与模型名称以当前源码为准；例如 `lib/models.py` 的 embedding 为 BGE-M3 / 1024 维。

## 数据与配置

`config.py` 默认读取 `~/.hermes/.env`，运行数据默认为 `~/.hermes/omonigraph-vault`。
`omonigraph` 拼写是现有路径契约，不要顺手纠正。
源码目录不保存真实密钥、数据库、知识图谱副本、模型缓存或旧虚拟环境。
隔离实验可在启动 Python **之前**设置 `OMNIGRAPH_BASE_DIR` 和 `RAG_WORKING_DIR`；
这两个变量不会阻止 `config.py` 读取用户的 Hermes 环境文件。
请按 [本地开发说明](docs/LOCAL_DEV_SETUP.md) 核对配置后再执行会访问服务的命令。

## 验证

```bash
# 无需导入运行客户端的源码级回归：
.venv/bin/python -m pytest tests/unit/test_mcp_healthcheck_alert_label.py -q
# 配齐依赖并完成数据、凭据与网络隔离后运行完整单元层：
.venv/bin/python -m pytest tests/unit -m 'not integration and not remote and not slow and not eval'
```

技能评测、集成测试和 E2E 可能调用真实服务；按文档单独执行。
上游已知测试漂移记录在 `.planning/ISSUES.md`，不要将局部测试成功等同于全套通过。

## 本次整理

见 [整理与恢复记录](docs/PROJECT_CLEANUP.md)。旧版本与历史文档保留在目录外备份和 Git 历史中。

## 部署环境

当前三环境基线见 [VitaX 部署档案](docs/deployments/VITAX_DEPLOYMENT_BASELINE.md)。GitHub main 是源码基线；生产存在已核实的部署漂移，不能直接整目录覆盖。
