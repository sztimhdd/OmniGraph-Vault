# 10/9 producer导入故障与最小修复

STATUS: 导入/部署修复通过；后续自然业务成功待核。

- 采集机核对hostname iZj1imk39yc55iZ。日志已见三次自然批次在长文翻译导入处失败，Halifax 05:03、07:00、09:02；加载的是/root/OmniGraph-Vault/lib/llm_deepseek.py。此前23:01、01:02、03:03自然批次完成并发布，不能称切换后完全无产出。部分文章/Wiki仍失败。
- 新producer-code/lib/llm_deepseek.py与本地SHA相同，含assemble_chunks。部署漏lib包入口；复用venv的zz_omnigraph_atomic_write.pth又在脚本启动前预加载旧lib。因此只改脚本sys.path或补文件均不够。
- 最小修复：wrapper在启动Python前export OMNIGRAPH_REPO_ROOT="$CODE"，沿用启动钩子的现有配置；独立producer包补__init__及7个共享依赖（包括lightrag_atomic_write_patch），共享代码取采集机已运行版本。旧/root/OmniGraph-Vault未改，凭据/账本/缓存未改。第一次仅补包文件的检查失败；启动钩子新证据后配置修复通过。
- 备份：collector /root/.vitax-local-automation/deployment-mvp05/import-fix-20261009/producer.before。producer原子替换，sh-n通过；无需重启timer或手动reset-failed。旧failed状态保留到下一自然触发。
- 离线检查：socket.connect禁止网络，实际refresh模块导入，新客户端路径精确匹配producer-code，>24KB文本分块后无损拼回。相关本地17tests通过，指定diff检查通过。
- timer active/waiting，下一自然触发10/9 11:04:36 Halifax（远端22:04:36 CST）。没有手动运行producer、重跑付费队列或重启常驻服务。

NEXT: 查看下一自然批次退出码、accepted/failed/remaining/Wiki错误及发布版本；不以导入PASS或已有252条知识替代整批业务结果。用户本轮授权取消原40%停止线，仅继续本次采集机故障排查，未重置额度。
