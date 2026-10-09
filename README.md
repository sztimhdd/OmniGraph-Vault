# VitaX

个人维护的 AI 内容站：收纳优质 RSS 和微信公众号文章，自动整理、翻译、更新 Wiki，方便阅读与搜索。
重点是内容、自动运营和低成本。

## 开始工作

[项目说明](AGENTS.md) · [需求](docs/spec/VITAX_HOBBY_PRD.md) · [技术方案](docs/spec/VITAX_HOBBY_TDD.md) · [下一步计划](docs/superpowers/plans/2026-10-04-vitax-next-stage.md) · [问题列表](.planning/ISSUES.md)

## 代码位置

| 目录 | 用途 |
|---|---|
| `enrichment/`、`spiders/`、根目录脚本 | 微信/RSS采集、筛选、入库 |
| `lib/` | 模型客户端、翻译和公共工具 |
| `vitax/`、`scripts/refresh_vitax_local.py` | 文章读取、内容生产、批处理与发布 |
| `vitax-site/` | 新网页 |
| `kb/`、`omnigraph_search/` | 旧网站和检索代码，按需要复用 |
| `tests/`、`test/fixtures/` | 测试与已有样本 |

使用 `.venv/bin/python`，新环境按 [本地开发](docs/LOCAL_DEV_SETUP.md) 安装。原始项目为 sztimhdd/OmniGraph-Vault。
运行数据路径为 `~/.hermes/omonigraph-vault`，密钥与真实数据库不放入源码目录。
远端位置见 [部署档案](docs/deployments/VITAX_DEPLOYMENT_BASELINE.md)。其快照时间不代表当前健康状态。
其余文档见 [索引](docs/README.md)。

## 当前交付

[公网阅读站](http://47.103.73.20:8767/) · [运维入口](docs/OPERATIONS.md) · [10/9执行总结](docs/deployments/2026-10-09-mvp/REPORT.md)

这是Hobbyist MVP快照。源码含已实现的阅读、批处理与部署；自然全批稳定性和余留问题以工单为准，不把快照提交当全部验收完成。
