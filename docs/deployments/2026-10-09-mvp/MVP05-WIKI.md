# MVP-05 Wiki 缓存通用格式修复

STATUS: DONE（离线，未提交）

CHANGES
- `vitax/production.py` `accept_model_output`：在已有 `{"type":"json_object","content":{...}}` 解包之后，新增 wiki 阶段扁平对象适配：当 proposal 顶层键含 `knowledge_id`、`kind`、`body`，且不含 `knowledge`/`entities`/`relations` 时，包成 `{"knowledge":[proposal],"entities":[],"relations":[]}`，再走原有覆盖校验。
- 适配只识别单个扁平 knowledge 对象形状；任意 JSON 仍落到原有 `model output must contain knowledge, entities, and relations lists` 拒绝。
- 不改 article 规则，不改 synthesizer/scraper/ingest，不新发模型。

EVIDENCE
- 变更点：`vitax/production.py:346-350`（diff 新增 3 行）。
- 新增回归：`tests/unit/test_vitax_production.py::test_wiki_flat_knowledge_object_is_adapted_and_still_validated`。
  - 合法扁平对象（keys: type,knowledge_id,title,language,kind,image_ids,citations,body；kind=wiki）被接受，产出 knowledge_id=wiki-alpha-beta、kind=wiki，entities/relations 为空列表。
  - 无效 kind（article）→ 拒绝 `wiki stage may only produce wiki knowledge`。
  - 空 body（空白字符串）→ 拒绝（knowledge.body）。
  - 坏 citations（重复源 revision/locator 但 quote 不在原文）→ 拒绝（citation）。
- `OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_vitax_production.py -q` → 37 passed（含新增 1 例，新增用例单独运行 1 passed）。
- 文件 sha256：production.py `e2b52bb87006ce4fbe45c5de0db8b0abb66a428e8dba290be718c24881514ca2`；test_vitax_production.py `3e33706731bd14a8d0426bd8e73bb1a4966045891f835279577a2e6d865c33a9`。

RISKS
- 适配判定以“含 knowledge_id/kind/body 且无三列表键”为界；若真实缓存对象缺 `body` 键（而非空值），仍会走通用拒绝而非 body 错误——属预期拒绝，非静默接受。
- 未验证真实生产缓存文件（离线约束）；未跑批处理，pending 的 9 主题 115 成员未处理，续跑由控制方在真机执行。
- 未提交、未 push；工作树保留既有未提交 WIP。

NEXT
- 控制方在真机对已发布文章的已付 wiki 缓存重跑 wiki 接受路径，确认 115 pending 可续跑。

改动文件
- `/Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX/vitax/production.py`
- `/Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX/tests/unit/test_vitax_production.py`
