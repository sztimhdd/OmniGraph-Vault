# 自然建图运行诊断（Sol只读）

10/9 11:30 Halifax，主机iZj1imk39yc55iZ，PID3923373仍在运行。初始化已完成，当前不能认定死锁。

- 11:01:31已加载cache18458/docstatus2638；11:06:41完成正文3 chunks抽取并进入78实体合并；11:29:52仍记录Merged: Desktop。
- 首个采集错误：11:02:02 WSJ [Errno101]Network is unreachable，11:02:17无正文跳过。
- 首个建图错误：11:08:55 entity_upsert attempt1 timeout；11:14:31三次写尝试失败。异常链httpcore.ReadTimeout→httpx.ReadTimeout→ResponseHandlingException，installed lightrag/kg/qdrant_impl.py:689 upsert(wait=True)。
- epoll_wait业务FD10/18连接本地7997 embed-server，两次端口有变化且日志推进。未见跨进程文件锁等待；内存/I/O有压力但OOM0，memory.high计数未增，不能据此扩容。

下一动作：同一Sol只读对齐Qdrant与embedding已有请求耗时日志，找因果后最小修复；不追加模型、重跑或重启。
