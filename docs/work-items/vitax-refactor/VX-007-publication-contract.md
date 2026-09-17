# VX-007 — 公开知识构建与完整发布合同

**What to build:** 已接受的知识投影构建为全新只读 SQLite，文章/Wiki可搜、关系可查、证据可读；后续与图片、页面和选定索引组成一致release。
**Blocked by:** 首个离线读库子切片无依赖；完整包依赖 VX-004 真实内容与 VX-009 站点产物。云端提升归 VX-008。
**Status:** partial — 首个公开读库local slice accepted；25项针对测试及独立审阅通过；完整发布包/生产未验收。

## 当前子切片验收

- [x] 显式公开投影中保留多文章revision、多来源Wiki及关系证据，响应固定release_id。
- [x] 新数据库重新打开后，article/wiki可搜索和读取、证据带source/revision/locator、related带引用。
- [x] 私有记录和未知附加字段不进入公开字节；公开内容指向私有/缺失证据拒绝构建。
- [x] 重复ID/非法输入拒绝；失败不覆盖现存目标；只读查询不创建不存在的库。
- [x] CLI可重放构建与读取，不加载旧config、模型、凭据或运行数据；SQLite实际行为通过测试。

## 后续完整包验收

- [ ] 替代旧六组件强制清单：仅包含本release实际使用的公开组件，私有备份独立。
- [ ] 页面/图片/索引引用、文件hash、版本一致性与安全路径检查完成。
- [ ] 当前请求固定release；坏包/不完整包拒绝；撤下内容不经旧公开版本泄露。
- [ ] 不把本次SQLite构建通过当作原子云发布、备份恢复、语义质量或中文检索验收。

**执行边界：** 只写主控派工的互斥路径；保护原始数据与无关 WIP，不自动 commit/push。远端写入须绑定具体候选/生产任务、当前主机与源码验证，ADR 0002 四类例外始终有效。

## 历史记录（保留原验收范围，不作为新前置）

**What to build:** 合同覆盖 SQLite、向量、graphml/KV、图片和公开内容。

**Blocked by:** None for offline contract/fixtures. 候选部署属于 VX-008，须另过源码漂移、样本、一致快照和环境验收门。  
**Responsibility:** coder + reviewer. **Status:** partial (offline file contract; runtime consistency pending).

**Allowed scope:** 合同源码、离线 fixtures、evidence/VX-007/.  
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [ ] 合同覆盖 SQLite、向量、graphml/KV、图片和公开内容。
- [ ] 版本、校验、原子可见性、回滚和不一致失败明确。
- [ ] 补缺失向量 ID 不算完整同步。

## 执行附件

```bash
rg -n 'sync_kq_to_new|graphml|kv_store|images' deploy scripts docs/deployments/VITAX_DEPLOYMENT_BASELINE.md
git diff --check -- deploy scripts tests
```

**Tests:** 离线合同和缺项拒绝测试。  
**Evidence:** 版本清单、校验、拒绝样本、恢复步骤。


## 第二阶段执行

离线文件级合同已交付；实际快照、包内语义和公开查询隔离仍未验收。见[第二阶段报告](../../deployments/2026-09-09-second-wave/SECOND-WAVE.md)。