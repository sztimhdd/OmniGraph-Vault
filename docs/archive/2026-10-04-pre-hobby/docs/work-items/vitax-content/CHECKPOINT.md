# VitaX 内容轨道 checkpoint

2026-10-04 Halifax 19:22。父主控 `01a0d392-693f-72d2-8fba-71b01d0642e4`，本内容主控 `01a1081a-5053-7d72-99d5-7df90eb45f15`。最新状态见文末v7/定点editorial段；原批收费仍冻结，不作为更多请求授权。

STATUS: 下一有界切片完成。30候选分类：verified-original1、derived-only0、unresolved29。494历史捕获原文核心已通过隔离候选API。全K1及K2–K4未完成。业务调用0。

CHANGES: 本轮只读核验远端，新增本地报告/证据和隔离候选SQLite。没有改生产源码、源数据库、current、调度或凭据。预算最小方案只提案，未建账本。详细结果见REPORT.md最新章节。

EVIDENCE: `K-next-provenance.json`逐30项含URL/metadata/文件性质/完整性/修订关系。`K-next-candidate-api.json`记录仅隔离articles:494变更，基准DB hash保持、译文保持，API字节一致。`K-next-cache-accounting.json`记录20份DeepSeek usage副本=9唯一request，缺费用/cache细分。`BUDGET-OWNER-SEAM.md`记录活跃Mac refresh owner和同root/lock的唯一预算建议。定向pytest9 passed，2既有warning。

固定点: Mac HEAD8505dbca4958944fc08b0ea5ebdf88f9051a7bfa。OHPC=OH-Desktop，SSH可用，已装venv具bs4/html2text，venv-aim1无这两依赖。ACK采集机hostname=iZj1imk39yc55iZ，仅只读已知runtime root。当前Mac唯一producer为com.vitax.local-refresh，runtime root为 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/local-automation-20261002`。

产物根: `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-k0-k1-20261004`。私有原文/HTML证据不复制到报告。494候选为verified-original-494-candidate，未promote。

RISKS: 494原文只对应已保存抓取，不证明在线全文或旧译文修订。3182对照有含中文删除差异，其他28项无独立原始捕获。预算首个决策前置是项目主控指定同一refresh owner的唯一落点，随后核价/usage细分/输入上界。不收费探测或通过新producer绕过。

失败: 原远端执行分支failure_count=2保持。本轮源码对照分支新增1次ModuleNotFoundError(bs4)，核已有依赖后同SSH面完成，未安装包或换provider。

额度: 共享账户41%→41%，整数百分比，非独占成本。100元回填未支用，新增模型成本0元。

## 最新预算源码切片（取代上方预算仅提案的当前状态）

STATUS: SOURCE_AND_OFFLINE_ACCEPTANCE_READY。父主控已指定本内容主控为唯一预算工程owner，Mac refresh仍是唯一运行owner，无另一个并行预算实现owner。全K1未完成，29候选unresolved保持，494不promote。

CHANGES: 新增vitax/backfill_budget.py及定向测试。refresh入口显式backfill，K/D同运行根/backfill-budget.json、同refresh.lock共享10000分，daily默认不建账本且标记不变。DeepSeek usage保留cache-hit/miss。未知结果先持久化220分预留并只读原结果恢复，已知request_id结算一次，历史缓存不倒计费。

EVIDENCE: 相关pytest53 passed、2既有warning。BUDGET-verification.json含源码hash、临时真实refresh入口合成usage结算回执、零真实模型/SSH调用、生产账本不存在。日志与本轮起点WIP备份/diff根为 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-budget-source-20261004`。CONTENT-BUDGET-PRICING.md保存官方价目核验、whole-window输入预留及最小启用步骤。费用记录为实际usage的高峰价/整数分上界，不是精确扣款。

RISKS: 未启用真实回填。旧两篇/Wiki/主题业务路径未重做，多主题/长文不在本切片。价格或max_tokens变化需复核snapshot。生产账本和调度未动。

失败: 原分支2、原文对照1保持。计划RED不作执行故障。本轮回执收集glob一次失败，核pytest截短目录名后收集成功，保留count=1。

额度: 本轮42%→42%，业务调用0，实际新增DeepSeek费用0元。没有重置。

NEXT: 父主控立即独立验收源码/零费证据，再协调已授权两篇真实回填，首次启用才初始化生产账本。本内容主控不再等owner确认，不通过用户转达。后续所有回填阶段传同budget身份。保留29候选，不抓取/写回未证实原文，不修CDP、不接管全部B/E。

## 最新：首批真实切片冻结（取代此前等待启用）

STATUS: BLOCKED_CITATION_CLOSURE。按父主控明确指令完成已开始只读浏览器后结束切片。K3/K4不标完成，不新增收费、测试或修复。

CHANGES: 首次启用唯一原运行根/backfill-budget.json，lane K共享10000分。一次批处理微信20294/RSS84952两篇明确Harness合格原文，新增2解读并更新legacy-harness。timer/owner/原文不改，494/29未决不promote。后续停止指令之后未改current。

EVIDENCE: 当前release-local-de432882e10742f7，可恢复前版release-local-cfcea28d442e4823完整包hash有效，均位于原运行根public/releases。3真实Flash回执、3唯一request_id、实际usage/output hash一致，费用上界10分、预留0、余额9990分。daily marker SHA844ed51a03b42652d115a60b564030a5f1643c0af124f9fdead1c961349476ff保持。现用浏览器3知识页与2原文直达已读，无page error。证据根 `/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/content-backfill-first-20261004`：actual-receipt.json、browser-receipt.json、content-contract-assessment.json、final-blocker.json。

首个阻塞: 按正文顺序首个缺失引用evidence-ee30a0a92978511ce97a。全部5缺失ID为ee30a0a92978511ce97a、23500b7ad7f07748a81c、4ae6a641435b0cc867fc、b61c64a8df4e45c02738、c73990f2aee420b34f1a（均带evidence-前缀）。分类全部为前版legacy-harness.body继承的未解析正文引用，两版evidence表均无行，本批新增未知ID0。旧包回切不解决此语义缺口。另4个新增有效引用未入Wiki面板。

微信具体spec缺项: §7.3要求的明确适用条件和局限未建立，只有作者观点/实测摘要及4结构证据。不得降低合同宣布K3完成。

RISKS: 技术生成/发布成功不等于内容通过。全文翻译、清洁/改写、长文、媒体/完整关联及全覆盖未完成。不给缺失引用猜测映射，不删掉引用掩盖问题。

失败: 原执行2、原文对照1、预算回执收集1保持。本轮价目重读2 Timeout停止。只读API verifier envelope错误1、浏览器尾slash断言错误1，按实际合同修正并完成取证，没有重复生成。模型/调用路线本批未失败或更换。

额度: 43%→44%。真实业务调用3，无第4次。保留已发生账本费用上界0.10元，不写为精确账单。未重跑整批验幂等。

NEXT: 已向父主控首阻塞汇报。收尾交付后结束；父主控另行安排源码/内容引用修复与版本决策。本内容主控不继续当前收费分支或新增测试。

## 最新零费切片：隔离引用合同

STATUS: ISOLATED_CITATION_CONTRACT_READY_NOT_DEPLOYED。按新增CONTROLLER授权完成根因及隔离最小RED→GREEN；结束切片，旧收费不恢复。线上K3/K4仍BLOCKED_CITATION_CLOSURE。

CHANGES: 在线入口已核是仓库根refresh，未原位编辑。隔离根 `/Users/hai/Projects/ohpc-migration/VitaX/.superpowers/sdd/vitax-content-citation-contract-20261004`，13 Python依赖副本。仅knowledge.py公开投影校验与refresh.promote_release变更，7项直接相关临时测试。交付citation-contract.patch，SHA c197aa21bb325b389b232798a933b4c6286640fddb94ed6bc411937d39402a6f。

根因: 模型自由正文使用bank-only ID，而结构citations未选中。production只把结构引用持久化，knowledge只查结构evidence_ids，promotion只查文件hash/SQL身份，面板只读knowledge_evidence。现有producer canonical正文ID现在必须在合并后的同版public evidence集合中存在，未知/私有拒绝；合法已公开引用只补面板关联，原正文/旧关联保持。promotion对未持久化面板或未知ID拒绝，临时current保持。

5项来源: 全部重建自旧wechat-20074、rev-85c6f2e34292203b532b、paragraph:1的候选citation bank。quote hash与ID一致，结构选择false，accepted.evidence中无行。经旧Wiki8de993进入自由正文，首批Wiki327d05继承。首个ee30a0a92978511ce97a，其余23500b7ad7f07748a81c、4ae6a641435b0cc867fc、b61c64a8df4e45c02738、c73990f2aee420b34f1a，均evidence-前缀。来源可核不等于准许公开；没有补行或猜映射。

EVIDENCE: red-bounded.txt为7 failed，green.txt为7 passed。模块路径确认隔离，config/LLM未加载。frozen-artifact-guard.json只读拒绝旧版/现版的首个缺失ID。verification.json记录13在线源码hash、4关键runtime hash、6唯一cache文件hash及public/current不变。原固定DB不变，现有自然timer17:55更新library/current，新镜像变化单列，不假称环境完全静止。

未解决: 线上5引用/4面板项尚未修复，微信适用条件与局限仍缺。生成合同的自由body及现有验收未显式建立这些语义要求。本轮只记录根因，不补空栏目或模型修稿。494/29候选仍不promote。

失败/预算: 旧执行2、原文对照1、预算回执1及首批记录保持。本轮隔离patch定位失败1、验证收集定位失败1，均据实际字段修正且保留。计划RED不算收费重试。业务调用0、SSH0、测试连网0；新增费用0，已结10分/预留0保持。共享used45%→46%，非新10%授权。

NEXT: 父主控独立验收隔离patch/红绿证据后另行安排部署和候选公开准入/内容引用处理。当前切片结束，在线源码/current/accepted/原文/账本不改，不恢复收费。

## 最新：必要证据审核与隔离内容候选

STATUS: REVIEWED_ISOLATED_CANDIDATE_READY_NOT_DEPLOYED。父主控已验7项源码合同，本轮继续明确内容审核：5条通过必要摘录准入，仅用于支持既有Wiki中已归因作者的描述，不作独立产品安全/行为保证。线上未接入，微信适用条件/局限未解决，全K3/K4未完成。

CHANGES: 同一隔离根下necessary-evidence-review/admission.json记录5项理由、原文精确quote/hash/上下文/公开范围。独立candidate保存输入projection、规范public-projection.json和public.sqlite。不覆盖旧accepted，不改正文，只加5必要evidence与合法面板关联。

EVIDENCE: 所有5条来自wechat-20074/rev-85c6f2e34292203b532b/paragraph:1，支持动机、凭据位置、云端工作区、共享状态及共享Agent额度的作者描述。231字必要摘录，原文5899字不公开。规范投影SHA956d639b47ee6e9b8618c9fd45b71bab1776219d910caa19572b1c9ab8e68099；SQLite SHAbe7f2ff4930a914d31064c297de7181a9482ae29d46d887c559773a3fb8e810d。候选release-local-citation-reviewed-20261004-c4f23bd8b737。

保持与闭合: 102旧evidence保持，新增5后107；全部18 knowledge正文/标题/kind/visibility相同，documents/entities/relations相同，旧links保持。Wiki面板14→28，全部canonical正文ID同版可解析且在所属面板可达。SQLite重新打开、integrity/FK通过。只做必需确定性检查，未重跑7项套件。在线4源码、4关键runtime、9 cache文件hash及current保持，原source标准化hash不变。

步骤: necessary-evidence-review/ONLINE-INTEGRATION-PLAN.md只写接入计划。先固定点/WIP、唯一owner/refresh.lock和回退；staging核patch，生成完整site/manifest包，验证后提升。当前候选仅projection/SQLite，不可直接替换current。未部署、commit/push或改timer。

RISKS: 内容准入不是全K3质量接受；微信缺项保持。在线de432882版仍有旧引用缺口。所有产品架构描述仅按已归因原文审核，非独立安全/一致性认证。

失败/额度: 历史计数保持；本轮候选校验KeyError(images)1次，既有DTO无此字段，核schema后继续既有候选检查，无重建/模型调用。新增业务调用0、SSH0、费用0，旧10分上界保留。实际共享47%→48%，非新额度授权。

NEXT: 父主控独立接受准入/候选/保持性证据后再单独接线上。本内容主控结束切片，收费保持冻结，旧知识正文/关系/证据与原文不改。

## 最新：本地引用接入完成

STATUS: LOCAL_CITATION_INTEGRATION_AND_BROWSER_PASS，待父主控独立验收。只有引用/本地接入通过，微信条件/局限和完整K3/K4仍未完成。收费继续冻结。

CHANGES: 原运行root/refresh.lock内备份WIP原字节与旧包，staging核patch后原子接入knowledge.py、refresh_vitax_local.py及直接测试。新进程从获准投影构建完整site/SQLite/manifest，gate通过后提升current。未改timer/账本/原文/旧cache/路由，未调用refresh整批、LLM/SSH业务、云部署或commit/push。

固定点: current为release-local-citation-reviewed-20261004-c4f23bd8b737，原de432882e10742f7完整包仍可回退但语义有旧缺口。新知识源码SHA6c92eb4a6576e7499374accc04fa595978b96f2e89aa49f94d3f08d11316c820，refresh源码SHA81096092bc4e3cef4d6f9572baa93241acbb3559be082cb0655e1c8ae9d4ad42。源码回退在source-before，不使用HEAD覆盖WIP。

EVIDENCE: 隔离根/local-integration-20261004内rollback-index.json、integration-result.json、package-data-verification.json、browser-verification.json、final-verification.json。7直接测试通过；完整包22文件，manifest SHA c2ff62293930c2eee8738ddc0898e3fc96a86ac254e7f395c7d59eff3067c1c4，public.sqlite SHA1c7223afb17a81845d5475ff7ae6caa8059aafce0ac5285485418b83aa143117。重建DTO与已验候选完全一致，物理SQLite hash不同已说明。

现用: 8788 Wiki22正文引用同版可解析且在28项面板可达，面板quotes逐项/顺序与SQLite一致。两解读API/DOM同版，两原文hash保持，无page error，wiki截图已看。18知识body/标题/kind/visibility、102旧证据及旧关系保持；仅5条已审必要摘录及面板关联新增。所核私有全文不进入公开包。

预算/失败: 本次业务调用0、费用0，原上界10分/预留0/余额9990分保持，shared48%→49%。接入分支0失败，所有历史计数保持。没有第二producer、自然timer调整或额外UI改造。

RISKS/NEXT: 该接入不接受微信解读缺项或完整backfill。494/29状态不动。结束本切片等待父主控独立验收，收费不恢复，不开其他票。

## 最新：v7一次修订及两处editorial接入

STATUS: EXACT_EDITORIAL_LOCAL_INTEGRATION_PASS，等待主控独立验收。v7原模型稿CONTENT_REVIEW_BLOCKED历史保持；editorial版按主控给定两处纠错另存且本地发布，不宣称全K3/K4。

v7事实: 有意recipe deepseek-v7-semantic-article，单篇微信20294/rev-0aa392aa3bb40d592b88，同knowledge ID。唯一新request08bad6cb-e2b4-417a-806b-cf7233546a03，requested v4-flash/returned deepseek-flash，6331prompt(hit3584/miss2747)+776completion=7107。输出JSON SHA c41ed17ece9cca211d1ea75942a5cf90257167c3fdf4e0b87ec5f0c1d38dacc1。费用上界2分，总账12分/预留0/余9988。无第二次请求。原稿因排他适用范围断言等不通过，不改失败结论。

editorial范围: CONTROLLER精确替换第二段首句和完整末段，其他正文/title/ID/links不变。编辑body SHA3c8f8e86674d312e85bd091411ad0ac96579a72b1b8d1741ad50e926f396b3ec，不作为原Flash hash。旧model-output/usage/cache/候选和失败记录保持。新2证据主控已核准仅作者归因用途。

当前: release-local-wechat20294-editorial-v7-3c8f8e86674d，原c4f23引用修复完整包保留。原refresh.lock内用已有builder/gate构建完整22文件包再提升。公开SQLite SHA910d1cb4ca3cd4a80bb3f427533cea2b775dd0205db8117cd974b577692883d5；manifest SHA5c8f750b90c5342825bb9985210dd95760b58478db361aa2651fedf5593b4b1e。没有在线源码/prompt部署或timer改动。

证据根: 同一隔离根/wechat20294-semantic-v7；editorial子目录含editorial-record.json、editorial.diff、promotion.json、rollback-index.json、browser-verification.json、final-verification.json。现用API/DOM微信正文等于编辑版，Wiki正文保持22正文引用/28面板，两原文可读，RSS不变。其他17知识、107旧证据/旧图保持，仅新增2证据/关联。公开产物无完整私有原文，保护状态hash保持。

失败/用量: v7语义内容失败1保持；editorial分支0失败；历史各计数不清零。v7共享50%→52%，editorial52%→52%，非独占成本/新额度。本次编辑业务调用0、费用0，全部请求4、上界12分保留，不改账本。没有第二次模型调用、大套件测试、业务SSH、云部署、commit/push或子代理。

RISKS/NEXT: 编辑后接受与原模型失败分开记录。该单篇定点纠错不证明新prompt已稳定或完整backfill完成。收费批保持冻结，结束切片等主控独立验收，不开其他票或追加请求。
