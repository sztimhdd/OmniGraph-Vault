# VitaX 稳定闭环执行报告

2026-10-03。STATUS：核心实施及本地发布完成，整体目标仍PARTIAL。周额度规划23%→最新28%，共享账户变化保守计入；33%停止线不变。

## 当前结果

| 工单 | 结果 | 证据 |
|---|---|---|
| T1 VX-004G | 共享预算、过期不启动、单调时钟、异步标题查询已修复；3文件哈希核对/备份部署ACK，无生产重启；共享DeepSeek完成度guard另行备份部署。自然两批WAITING，21源网络阻塞 | T1-deploy.json、T1-eol-preservation.json、T1-natural-batches.json |
| T2 VX-009F | 实际DeepSeek两篇+Wiki生成、构建、原子发布通过；小时镜像/每日有界生成恢复，首个owner-native执行exit0 | T2-T3-candidate.json、T2-promotion.json、T2-launchd.json |
| T3 VX-004H | 已有Harness Wiki实际更新，旧2条引用保留并增至6条；9实体/8关系新增，版本选源、阶段失败隔离、引用ID与碰撞门禁落实 | T2-T3-candidate.json、T4-public-links.json |
| T4 VX-011B | 所有2960正文逐篇SHA一致；正常文章默认入口、译文、手机、刷新、14页面/80证据/32实体入口通过 | T4-full-body-api.json、T4-browser.json、T4-public-links.json |

当前reader：http://127.0.0.1:8788/library。全来源10130记录，有正文2960、已有译文1753。release-local-ui-bc3213253a9f；知识发布来源release-local-4fadeaed1211445f。UI包重建没有增加模型调用，知识数据保持。

当前自动公开生成是明确的Harness主题切片，daily默认最多2篇/3次新请求，使用现有ACK凭据与DeepSeek直连API，不走OCX。公众号仍维持既定每周20号×2页轮转预算。

## 子代理与验证

Ampere只读追调用链。Chandrasekhar独立审查T1，发现同步查询阻塞、扫描未限时和墙钟回拨。Sartre独立审查T2/T3，发现版本哈希不一致、空模型、失败缓存、关系ID碰撞、短行及前导空白引用问题。主控分别修复并复现验证，所有子代理已关闭，无孙代理。当前可写主控承担代码，固定coder/debugger既有故障路线未重试，无全局模型配置修改。最近ledger未关联本线程，不以badge宣称新provider路由验收。

- 管线定向80项通过。历史timeout公式测试显式1200秒环境；生产默认3600秒未更改。
- 生产/发布41项通过，读库/API/发布29项通过（存在重合，不能相加为唯一总数）。
- 通用DeepSeek wrapper现在拒绝length/content_filter/resource截断，10项client与16项翻译改写回归通过。lazy-import测试清理sys.modules，会影响同进程其他模块属性解析，因此两组使用独立进程；没有隐藏该混合运行失败。
- 前端tsc通过；真实Chrome桌面/390px手机和全部公开内部路径通过，pageErrors为空。Browser插件不可用，使用已有Playwright路径。
- git以cr-at-eol规则检查通过，保留原CRLF；没有新增依赖、commit、push或全树部署。

实验共记录8次业务DeepSeek请求/84329tokens，另有1次路由探针/51tokens。最后有效三次26603tokens；失败实验、pre-API启动错误和日常调用上限分别记录，未把所有实验伪称为三次。

## 尚未验收 / 阻塞

1. 自然两批结束只读观察正在执行（observer session32590，最长9小时），结果自动写T1-natural-batches.json。17:25之前启动的旧PID3307186被排除。没有改timer或强杀writer来制造通过。
2. RSS最新70源成功、21源失败、27条新增；失败是网络不可达、TLS握手超时和DNS。对tedunangst非www原站的既有fetch路径探针也DNS失败，不进行无证据URL改写、关TLS或改用新代理。该出口分支BLOCKED。
3. 旧显示改写有微信1387/RSS241篇，其中837篇引用旧localhost:8765图片地址；本轮没有把该旧显示层伪装成本地已可用。长文分段改写与这些资产路径接入仍待实现，原文完整保留。
4. 默认公开生产暂为一个明确主题；其他主题的稳定Wiki路由仍待覆盖。深问API/MCP生产化继续排除。
5. 扫描旧入口的同步网络任务转入线程，取消await不等于取消底层请求。实际生产DB入口已使用同一预算，但硬截止还必须由自然运行证明。必要存储flush保留。

18:00 UTC实际资源检查：旧进程MemoryCurrent约3.38GiB，high/max/oom/oom_kill均0，pressure avg10/60/300为0，维持5/6GiB配置。旧PID3307186最终7769.39秒结束（6300预算，补丁前），新PID3390914已经启动；旧结果不计入新版本验收。

## 下一步

先检查自然观察结果与下一自然daily发布；不得从scheduler配置或本轮手工发布推断长期稳定。继续任务应从这份checkpoint读取WIP，保留备份/失败原始结果，针对旧图片与长文另开有界工单，先核对源路径与体量。RSS出口不使用未经授权的新访问路径。
