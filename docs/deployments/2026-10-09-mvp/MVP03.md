# MVP-03 窄修回执（修订）：正文门 "Sign in" 误判

日期：2026-10-09（America/Halifax）
目录：`/Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX`

## STATUS

已按修订方案重做并离线验证。取消 1000 字符豁免；明确 login/paywall 短语任意长度仍拒绝；
泛化 "Sign in" 只在独立按钮/登录提示行才算墙，正文叙述中的 "sign in with GitHub" 不再误拒。
改动文件仅 `lib/scraper.py` 与 `tests/unit/test_scraper.py`。未触发采集、未调用业务模型、未部署/重启、未 commit/push；本轮未再安装/卸载任何依赖。

## CHANGES

- `lib/scraper.py`
  - 删除上一版的 `_WALL_MARKER_MAX_CHARS` 字数豁免。
  - `_LOGIN_WALL_PATTERNS`（明确阻断，任意长度按词边界拒绝）去掉裸 "Sign in"，加入明确阻断变体 "Sign in to continue" / "Sign in to read" / "Sign in to view"；其余 login/paywall 短语不变。
  - 新增 `_GENERIC_WALL_LINE_MARKERS = ("Sign in",)`：泛化 "Sign in" 仅当某行（去掉前置 `[>*#-•` 与空白后）以 "Sign in" 起头时才算墙（独立按钮/登录提示行），句中出现一律不判。
  - `_passes_quality_gate()`：长度底线 `_MIN_CONTENT_LENGTH=200` 不变；先按明确短语判失败（任意长度），再按行上下文判泛化 "Sign in"。
- `tests/unit/test_scraper.py`
  - 更新模式数断言 16→18。
  - 新增回归：真实叙述（"sign in with GitHub"，长短各一）须通过；长正文+"Sign in to continue"/"Subscribe to read"、长正文+独立 `[Sign in](…)`/`Sign in` 行、短壳、<200 须失败。

## EVIDENCE

- 真实样本定位（只读 HTTP，trafilatura 本地抽取）：`https://simonwillison.net/2026/Sep/4/rogue-agent-wikis/` 精度/召回抽取均 9855 字符，"sign in" 位于普通正文段落（line#10，`starts_with_sign_in=False`，行首为 "The research team also …"），非独立按钮行。
- 红绿（同门对照 before 快照 vs 当前）：
  - 该真实正文：before `False`（误拒）→ 当前 `True`（修复）。
  - 长正文 + "Sign in to continue reading."：before `False` → 当前 `False`（保留）。
  - 短墙 "Sign in to continue reading."：before `False` → 当前 `False`（保留）。
- 门测：长叙述句含 "sign in with GitHub" `True`；长正文+明确阻断 `False`；长正文+独立 `[Sign in](…)` 行 `False`；"x"*199 `False`。
- 相关单测：`.venv/bin/python -m pytest tests/unit/test_scraper.py -q` → `10 passed`。
- 文件哈希：`lib/scraper.py` = `235d7e7a5d6de818f037a3927332f5253fd11554ac9515ad77fc21f83ae9497a`；`tests/unit/test_scraper.py` = `5835d8a8e23cf9a19fb4b61879827ec2a722569c7dbdd6e919a9f8c1a58c4bbe`。
- 只读 SSH `ack-node-2`：`hostname=iZj1imk39yc55iZ`（匹配）；producer 最近失败为 `lib.llm_deepseek` 缺 `assemble_chunks`（MVP-05），非正文门；未读凭据、未改远端。
- 依赖：本轮未安装/卸载；上一轮装入 `.venv` 的 `pytest-mock` 保持原状，交主控收尾。

## RISKS

- 泛化 "Sign in" 若在抽取结果里作为独立行出现（含导航/footer 链接在行首），仍会判墙——本方案按主控要求只消除"正文叙述"误判，不消除"独立按钮行"误判。若后续证实真实误拒来自导航独立行，需要另议（不在本轮范围）。
- 少数以 "Sign in …" 开头的真实叙述段落会被误判为提示行；属行上下文法的已知边界。
- 200–1000 字符真实短文含明确阻断短语仍拒绝；本次只处理把该短语当墙的误判路径。
- `test_ingest_from_db_orchestration.py` / `test_dual_source_dispatch.py` 在本 worktree 因缺 `kol_config.py` 无法导入（改动前后一致），非本次改动引起。

## NEXT

- 交主控复核；本轮不触发采集，自然批次恢复计数由主控观察。
- 若导航独立行仍是主因，另开最小票，用"行+邻近链接/导航簇"语境处理，不恢复字数豁免、不加分类器。

## 改动文件

- `lib/scraper.py`
- `tests/unit/test_scraper.py`
