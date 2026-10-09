# VX-009A — ZIP站点读取真实文章、Wiki和证据

**Parent:** VX-009。
**Blocked by:** None；已接受的VX-004两源release可立即联调，不等旧库导入。
**Status:** split for implementation（2026-09-20）。

[INFERRED] 本票按ponytail拆成两个最小交付：[VX-009A1](VX-009A1-real-reader-site.md)负责真实站点，[VX-009A2](VX-009A2-local-release-uat.md)负责与安全公开切片汇合后的本地release和浏览器验收。以下原始验收继续适用，但不再由单一代理整包实现。

**What to build:** 读者在本地站点能从真实内容列表进入文章/Wiki并打开原文证据，刷新详情URL仍可用。

- [ ] 审阅ZIP源码后复用UI，移除入口中的假统计/mock回退和未实现操作，不重新设计整站。
- [ ] 复用KnowledgeReader与已有HTTP能力，只补列表/详情实际需要的最小接口；页面与响应固定release_id。
- [ ] 真实文章、Wiki、引用和选图caption可读；图片仅来自公开白名单，资源失败显示真实状态，不用占位图伪装。
- [ ] 浏览器实测列表→详情→证据、Wiki→两来源及刷新直达；键盘、移动端、空/错状态可用。
- [ ] 正文、标题和来源链接可从构建或服务HTML读取，不仅输出空SPA壳；HTTP未知ID真实404，危险渲染及私有字段被拒绝。

**Scope:** 本地127.0.0.1，复用ZIP/读库/现有框架；不加第二后端服务或mock成功接口。代码按主控明确的互斥前后端范围实施。
**Verification:** 实际两源release的HTTP契约及确定性浏览器UAT，不重跑模型。最终旧内容综合验收留给VX-009B。
