# VitaX 阿里云部署调研与决策

日期：2026-10-04（America/Halifax）。范围：只读调查和方案留档；未部署、重启、改DNS/安全组、触发采集或付费生成。

## 结论

**关键补充：微信全文采集仍依赖Hermes PC浏览器，本方案不是全云无PC。**

建议使用现有两台ECS：ack-node-2作为唯一采集/处理/知识生产端，ack-node-1承载VitaX公开主站和只读API。Mac保留完整私有文章阅读与开发能力，退出云站必需的每日生产调度。单机技术上可行，但当前合并既有生产职责的风险大于少一条发布包传输任务的收益；不购买新服务器，也不将双机称为高可用。

## 实测与证据边界

[机器回执](inventory.json)时间为Halifax 10:23（UTC13:23）。两机都先核hostname，随后仅读取系统资源、监听端口和相关活动服务。

| 角色 | SSH别名 / 主机名 | CPU / 总内存 | 可用内存 / 根盘可用 | 现场情况 |
|---|---|---|---|---|
| 生产 | ack-node-2 / iZj1imk39yc55iZ | 8核 / 14.74GiB | 7.06GiB / 26.86GiB | embed-server、kb-api、Docker在运行；80与2019有监听，代理归属未本轮核实 |
| 查询 | ack-node-1 / ack-node-2-kg | 8核 / 14.73GiB | 4.19GiB / 43.95GiB | omni-kb-api、omni-mcp、embedding及Qdrant相关端口存在；未见80/443监听 |

资源是瞬时值，不能当峰值容量承诺。既有ACK/容器相关进程不代表VitaX必须上Kubernetes，不能接管其他项目。未查询控制台费用、VPC、安全组和带宽，不能承诺新增流量零费用；未确认域名和备案。主机間授权与传输吞吐尚待部署预检，不因为Mac可SSH两机就推定两机互信。

源码依据：`scripts/refresh_vitax_local.py`当前由Mac通过SSH导出原文快照、调用生产机DeepSeek并在Mac构建发布；`vitax/api.py`可只加载public.sqlite，也能配置私有全文库；后者的loopback检查在反向代理后不足以代表终端用户身份。因此公网实例必须完全不配置私有全文库，不能只依赖来源IP判断。当前app还会挂载MCP；新增站点应默认关闭MCP挂载，避免随主站公开超出本轮范围的接口。

## 方案比较

| 方案 | 好处 | 当前代价 | 决定 |
|---|---|---|---|
| 双机生产/服务分离 | 保留生产数据原位，网页不加载图谱和模型，写侧异常时旧发布版仍可服务 | 一条发布包传输和校验链；不是主备 | 采用 |
| 全部放采集机 | 不必跨机传发布包 | 与建图竞争；80已有其他用途；同一故障影响生产与网页 | 暂不采用 |
| 全部迁查询机 | 读写同机 | 搬迁写库、图/向量、凭据与调度，当前内存余量较小；仍不能擅停旧服务 | 不采用 |

不增加RDS、Redis、队列、共享网络SQLite、负载均衡或新图数据库。普通站点只查已接受知识SQLite；旧LightRAG/Qdrant继续承担原有职责，其同步问题独立保留，不能为网页发布顺手迁移。

## 外部一手资料

- [SQLite Online Backup API](https://www.sqlite.org/backup.html)：活动数据库导出使用一致性备份，而不是直接复制正在写入的主文件。
- [SQLite WAL](https://www.sqlite.org/wal.html)：跨机器网络文件系统不适合WAL共享；每机使用独立本地快照。
- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)：域名、DNS、端口可达与持久证书目录是HTTPS部署条件。采用一层反向代理即可。
- [阿里云网站部署流程](https://help.aliyun.com/en/dws/getting-started/the-whole-process-of-website-building/)及[备案适用范围](https://www.alibabacloud.com/help/en/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website)：中国内地服务器对外网站需要满足域名备案条件。现场地域与域名备案尚未验证，先完成隧道内候选验收，不猜域名或宣称公网已就绪。

systemd在线man页面本轮返回403，未将其作为成功获取的依据；实施时以目标机已安装版本的本地man核对timer语义。

完整架构、发布协议、迁移顺序、回滚和验收见[主计划第6章](../../superpowers/plans/2026-10-04-vitax-next-stage.md#6-阿里云主站与后台部署独立规划章节)。

## CDP与登录依赖复核（用户纠正后）

已确认生产CDP localhost:58933及MCP 127.0.0.1:58931依赖Hermes既有隧道；默认正文路径CDP→MCP，不能当独立容灾。生产CDP版本端点TimeoutError，Hermes本机9223 URLError；相关user services active不代表浏览器可用。极致了负责列表发现，不使用个人MP会话；全文浏览器路径仍依赖Hermes。

保存的MP凭据一次首页HTTP检查返回200、登录页特征true、dashboard特征false、token标记true，不能确认有效登录，也不能据此断定Edge profile失效。未调用列表API、未访问文章、未触发扫码或凭据写回。真实浏览器登录态因通道不可用保持UNKNOWN。人工首次登录/扫码/安全验证仍是明确依赖，不能承诺自动续期。完整修正及G0验收见主计划6.6。
