# MVP-06 窄修回执

- Worktree: /Users/hai/.codex/worktrees/vitax-mvp-epic/VitaX
- 固定点: execution/before/ + baseline.json（改动即相对该基线）
- 未提交 / 无 commit / 无 push；未安装依赖；未改环境；未碰 lib/scraper.py。

## STATUS
DONE（两处已定位接缝的窄修 + 对应回归，相关测试通过）。
lib/scraper.py 哈希已因 03 并发改动变化，非本席改动，原样保留。

## CHANGES（改动文件）
1. ingest_wechat.py
   - `ingest_article` 抓取失败：裸 `return`（None）→ `raise RuntimeError`。真实失败不再与“成功但无视觉任务”的 None 混淆。
   - 缓存分支：插入后新增 `await _verify_doc_processed_or_raise(rag, doc_id)`，使返回 None 真实表示“文档已 PROCESSED、无视觉任务”；`doc_id` 上移到 try 之前以便引用。
   - `Returns` 文档串更新为“成功 None=已核验无视觉任务；真实失败 RAISE”。
2. batch_ingest_from_spider.py
   - 外层 `ingest_article`：删除 `if result is None: return False, wall, False`；非异常返回即文档成功 → `(True, wall, True)`。inner 抓取/验证失败 RAISE → except → `(False, wall, False)`。返回 Vision handle 改存局部引用（fire-and-forget）。
   - 3 元组签名/语义不变（ingest_from_db 编排不受影响）。
3. lib/research/stages/synthesizer.py
   - sources 除 KG chunks / reasoner.additional_chunks 外，确定性合并 `state.web_baseline.snippets`（status=="ok"）与 `state.verified.external_citations`（status=="ok"）；复用既有 Source dataclass，无新 schema、不造证据；顺序=流水线阶段序。
4. tests/integration/kb/test_api_search.py
   - 修正 `test_search_default_mode_is_kg` 与 `test_search_kg_returns_job_id`：误 mock `omnigraph_search.query.search` → 改为 mock 真实入口 `kg_synthesize.synthesize_response`（签名加 `**_kw`），杜绝真实模型。
   - 新增仅离线生效的 lightrag import double（含 `LightRAG` + `QueryParam`），full env 不生效。
5. tests/unit/research/test_synthesizer_llm.py
   - 新增 `test_synthesizer_merges_web_baseline_and_verifier_sources`：仅外部来源（无 KG chunks）时 sources 含 WebBaseline/Verifier，且进入 [n] 提示块。
6. tests/unit/test_mvp06_ingest_doc_seam.py（新）
   - 4 例：外层 None→success；外层 raise→failure；抓取失败 RAISE（非 None）；缓存路径返回 None 且核验 PROCESSED。

## EVIDENCE（实跑命令与结果）
命令前缀：`OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest ...`（pytest-9.1.1 / py3.12.13）
- tests/unit/test_mvp06_ingest_doc_seam.py → 4 passed
- tests/unit/research/test_synthesizer_llm.py + test_synthesizer_caption_embeds.py → 14 passed
- tests/integration/kb/test_api_search.py → 32 passed（含两个修好的 KG mock 测试）
- tests/unit/test_ingest_from_db_orchestration.py → 19 passed
- tests/unit/test_ingest_article_processed_gate.py → 11 passed
- `python -m py_compile` 6 个文件 → OK

RED→GREEN 证据：
- 用 execution/before/ 覆盖 ingest_wechat.py + batch_ingest_from_spider.py 后，test_mvp06_ingest_doc_seam.py → 3 failed / 1 passed（失败=外层 None、抓取失败、缓存核验；通过=既有的验证失败分支）。恢复后 4 passed。
- 用 HEAD 版 synthesizer.py 覆盖后，新 research 回归 → 1 failed（sources 空）。恢复后 14 passed。

改动文件 sha256（本席当前）：
- ingest_wechat.py bd9ea4717ea10f4efbeb0cc5fa66ccc3f7621d0b703c92dba3d37154d033419a
- batch_ingest_from_spider.py 3b7460d5b3ff198452bf03b64bbc269971274cac275986a17911cb64214feb89
- lib/research/stages/synthesizer.py ba9fa76a7b62824986ddec9a6909d30f007b85ddd2685eb1591783f708613e6b
- tests/integration/kb/test_api_search.py 23a42f7f0f58e27fae5e1c5ea28e256108fb271f518102556fdbbed4b710102e
- tests/unit/research/test_synthesizer_llm.py 6f27e2d6dd2de965e15a71bb464f119e7cdc6ee44bb2b8cae8f780ee004740a8
- tests/unit/test_mvp06_ingest_doc_seam.py b750140427cd69f6fdfe585d1472d2b978bb0495ad5634586754759ec01ee183

CRLF：ingest_wechat.py / batch_ingest_from_spider.py 全文件保持 CRLF（diff 无行尾噪声）。

## RISKS（缺依赖限制）
- 本机 venv 缺：lightrag / nest_asyncio / fitz(PyMuPDF) / bs4 / html2text / playwright / apify_client / PIL。
- 因此 test_ingest_from_db_orchestration.py 与 test_ingest_article_processed_gate.py 仅能在“临时离线 import double + 进程内 pytest.main”下运行（未安装依赖、未改环境、未加仓库 conftest）。
- tests/unit/test_text_first_ingest.py 本机不可运行：首错 `ModuleNotFoundError: No module named 'nest_asyncio'`；注入 double 后次错 `TypeError: object() takes no arguments`（ingest_wechat.py:1314 BeautifulSoup / 缺 PIL 路径）。按“两次失败即停”保留首错，停止该分支，不再追。
- 需要真实 LightRAG 的完整图谱/API 测试本机未运行——不能声称通过。
- 语义变化：缓存分支多一次 `aget_docs_by_ids` 核验；若缓存文档不在当前 rag（换库/replay），该路径会 raise→外层标失败（与 fresh 路径一致，属预期）。
- 未做：真实模型/网络/SSH/部署/commit/push；未碰 lib/scraper.py（03 并发改动保留）。

## NEXT
- 主控在完整 LightRAG env 复跑 test_text_first_ingest.py 与 KB 图谱/API 套件（本席未做）。
- 03 收口 lib/scraper.py 后统一集成；本席不再发起新分支。

---

## 跟进：Sol P1 修复（2026-10-09 复盘）

依据 execution/REVIEW.md 的 P1：缓存分支 `except Exception` 只打印吞掉 ainsert 异常；旧 PROCESSED 文档使核验通过，inner 返回 None，被 outer 标成功。

### CHANGES
- ingest_wechat.py（唯一生产改动）：缓存分支 `except Exception as e:` 打印后**继续 `raise`**，非402插入失败不再被旧 PROCESSED 掩盖。402 降级仍由 `_ainsert_with_402_fallback` 内部处理（返回、不抛），本 except 不受影响。
- tests/unit/test_mvp06_ingest_doc_seam.py：新增第5例 `test_cached_insert_failure_not_masked_by_old_processed`（ainsert 抛非402异常 + 旧 PROCESSED → 断言 inner raise、outer 两个 False）；新增 autouse `_isolate_runtime` fixture，用 `tmp_path` 设 `OMNIGRAPH_BASE_DIR`（并补 `OMNIGRAPH_CHECKPOINT_BASE_DIR`，再 patch 已导入的 `config.BASE_DIR` / `lib.checkpoint.BASE_DIR` / `ingest_wechat.BASE_IMAGE_DIR|ENTITY_BUFFER_DIR|DB_PATH`），测试不再写默认 runtime。

### EVIDENCE
- `OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest`
  - tests/unit/test_mvp06_ingest_doc_seam.py → **5 passed**
  - tests/unit/research/test_synthesizer_llm.py + test_synthesizer_caption_embeds.py → **14 passed**
  - tests/integration/kb/test_api_search.py → **32 passed**
  - tests/unit/test_ingest_from_db_orchestration.py → **19 passed**（离线 double 注入）
  - tests/unit/test_ingest_article_processed_gate.py → **11 passed**（同上）
  - `python -m py_compile` ingest_wechat.py、batch_ingest_from_spider.py、synthesizer.py、seam 测试 → OK
- RED：临时移除该 `raise` 后，P1 回归 → `Failed: DID NOT RAISE RuntimeError`（1 failed）；恢复后 5 passed。
- 隔离验证：seam 测试的 5 个 ckpt hash 中，仅 REVIEW 记录的 69da4818b3436d27 / 792f812a84edcd49 在真实 runtime 存在（mtime 10:44:03，为本席上一轮未隔离运行所致）；本轮隔离运行未新建/未刷新（新增 hash a2283e28088ca0d3 在真实 runtime 不存在）。
- 未删除、未清理上述两个合成 metadata（REVIEW 要求由主控恢复）。
- CRLF：ingest_wechat.py（1765 CRLF / 0 lone）、batch_ingest_from_spider.py（2660 / 0）保持。

### 文件 sha256（本轮后）
- ingest_wechat.py 9ae40047d77633f6f477e8198c3478d432e5b79e753852ae4ef3ec425d950312
- batch_ingest_from_spider.py 3b7460d5b3ff198452bf03b64bbc269971274cac275986a17911cb64214feb89
- lib/research/stages/synthesizer.py ba9fa76a7b62824986ddec9a6909d30f007b85ddd2685eb1591783f708613e6b
- tests/integration/kb/test_api_search.py 23a42f7f0f58e27fae5e1c5ea28e256108fb271f518102556fdbbed4b710102e
- tests/unit/research/test_synthesizer_llm.py 6f27e2d6dd2de965e15a71bb464f119e7cdc6ee44bb2b8cae8f780ee004740a8
- tests/unit/test_mvp06_ingest_doc_seam.py d080c1aadde6bdf6147e51e48f54453f04b1764d24f595f887e17243befef2ba
- lib/scraper.py 235d7e7a5d6de818f037a3927332f5253fd11554ac9515ad77fc21f83ae9497a（未改，与 REVIEW 记录一致）

### RISKS
- 依赖限制同前：本机缺 lightrag/nest_asyncio/fitz/bs4/html2text/playwright/apify_client/PIL；需真实 LightRAG 的图谱/API 套件未运行，不声称通过。test_text_first_ingest.py 仍不可运行（首错 nest_asyncio；注入 double 后 BeautifulSoup 分支 TypeError），按“两次失败即停”保留。
- 未安装依赖、未扩分支、未 SSH/部署/commit/push、未改 lib/scraper.py。

### NEXT
- 主控恢复 69da4818b3436d27 / 792f812a84edcd49 两个合成 metadata；在完整 LightRAG env 复跑图谱/API 套件后裁决包含 MVP06 的部署。
