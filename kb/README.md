# 旧 KB 代码

`kb/`是可复用的旧网站与检索实现。新VitaX页面在 `vitax-site/`。
产品需求使用 [当前PRD](../docs/spec/VITAX_HOBBY_PRD.md)，技术方案使用 [当前TDD](../docs/spec/VITAX_HOBBY_TDD.md)。
不再执行旧KB阶段、强制技能调用清单、固定视口全套UAT或特殊提交格式。
修改接口时检查调用方，页面改动实际打开看相关操作。保留已有可用功能，不为保持旧方案额外造兼容层。
旧SSG部署仍要读 `databricks-deploy/Makefile` 的构建步骤，避免只同步模板而服务旧页面。
`kb/docs/`其余技术文件用于理解旧代码，不作为新需求或派工指令。
