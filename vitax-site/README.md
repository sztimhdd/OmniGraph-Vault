# VitaX 公开知识阅读站

`vitax-site` 是 VX-009A1 的真实读者前端：一个 React + Vite + Tailwind 项目，只读取
`vitax.api` 提供的同源只读接口，没有 mock 数据、评审工具或 API key。

## 命令

```bash
npm install
npm run lint      # tsc --noEmit
npm test          # node --test：路由、release 一致性、prerender 转义
npm run build     # 产出 dist/
npm run dev       # 本地开发，/api 代理到 VITAX_API_TARGET（默认 http://127.0.0.1:8000）
```

## 路由

只支持三条真实路径：`/`（列表与检索，`?q=`、`?kind=article|wiki`）、
`/article/<knowledge_id>`、`/wiki/<knowledge_id>`。历史前进/后退与直接刷新都走
History API；未知标识显示 404 状态，不会回退到第一条记录。

标识可以是 Unicode 与空格（链接按 `encodeURIComponent` 生成，prerender 直接以该标识作为目录名）；
含有 NUL、`/`、`\`、`.` 或 `..` 的标识无法作为单一路径段，会被读取端视为未知路由，prerender 会跳过并报告。

标识本身也可以是 `index.html`：只有三段形式 `/article/<id>/index.html` 里的结尾 `index.html`
才算生成文件的固定后缀；两段形式 `/article/index.html` 表示标识就是 `index.html`，prerender 会写出
`article/index.html/index.html` 并生成 `/article/index.html` 链接，两者往返一致。

## 启动顺序与替换

1. `main.tsx` 先调用 `api.bootstrap()`，即 `GET /api/release`。在这一步完成前，页面里已有的
   prerender HTML 保持原样显示，不会被清空。
2. 确认 release 后，`#root` 被清空并由 React 挂载真实读者界面。这是**有意的替换**，不是复用
   prerender 标记（没有 SSR/水合框架）；未启用 JS 时保留的只是静态内容。
3. bootstrap 失败时只渲染一个全局错误页（重新加载），不挂载读者界面。
4. bootstrap 完成后的任何响应如果 `release_id` 与已确认 release 不一致，客户端抛出
   `ReleaseMismatchError`，整站切换到 fail-closed 全局错误页，之前的列表/详情内容全部撤下。
5. 域请求失败时（例如 404）先确认 release 身份再映射状态码：响应体自带 `release_id` 就直接比对；
   没有元数据时通过专用的 `/api/release` 复读比对。复读本身失败不会递归，只保留原本的有界错误；
   只有确认仍是同一 release 时才返回 404/其他错误状态。

## 数据来源

全部数据来自 `vitax.api` 的同源接口：

| 用途 | 接口 |
| --- | --- |
| release 元数据 | `GET /api/release` |
| 列表/检索 | `GET /api/knowledge?q=&kind=&limit=` |
| 条目正文 | `GET /api/knowledge/{knowledge_id}` |
| 证据与来源 | `GET /api/evidence/{evidence_id}` |
| 实体与关系 | `GET /api/entities`、`GET /api/entities/{entity_id}/related` |

`/api/release` 是唯一权威来源：未确认前其他读取会被直接拒绝（不发请求），确认后每个响应的
`release_id` 都必须与它一致。

## Prerender

```bash
node scripts/prerender.mjs <snapshot.json> <dist-dir> [out-dir]
```

快照格式是已接受的公开 release 投影（`schema_version: 1`、`release_id`、
`published_at`、`documents`、`evidence`、`knowledge`、`entities`、`relations`）。
只有显式 `visibility: "public"` 的记录会被渲染，其余一律丢弃；生成
`index.html`、`article/<id>/index.html`、`wiki/<id>/index.html`，保留构建产物中的
script/style 引用，所有文本与链接都做 HTML 转义，非 http(s) 链接不输出。函数返回
`{written, skipped}`；CLI 会把被跳过的不可用标识打印到 stderr。

## 运行

```bash
python -m vitax.api <public.sqlite> --site-dir vitax-site/dist
```

## 构建完整本地 release

从仓库根执行，输入必须是已接受的公开 schema-v1 projection；输出目录必须不存在：

```bash
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python scripts/build_vitax_release.py projection.json new-release
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m vitax.api new-release/public.sqlite --site-dir new-release/site --port 8788
```

Builder 复用公开读库和当前 Vite/prerender，生成 `public.sqlite`、`site/`、空 `images/` 和带 hash 的 `manifest.json`。静态预渲染只读取新公开 SQLite 的白名单字段；原 projection、私有资料和中间 DTO 不复制进包。已有输出拒绝覆盖，失败清理本次新包。

当前支持零图片 release；不从私有 `selected_images` 推导公开资格。有效详情静态路径返回200，未知路径返回404并显示读者站的未找到页面。

2026-10-01 真实两来源候选与检查证据位于源码外：`/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/reader-release-20261001/`。本地浏览器检查覆盖真实内容、引用、搜索、刷新、404、手机与键盘；503和缺图状态使用受控响应注入。

## 本地 MCP 接入

同一 `python -m vitax.api ...` 进程在 `/mcp/` 提供 Streamable HTTP MCP；裸 `/mcp` 会307到规范路径。当前预览地址：`http://127.0.0.1:8788/mcp/`。

只读工具为 `release_info`、`search`、`read_knowledge`、`read_evidence`、`list_entities`、`related`，共用HTTP的 `KnowledgeReader`、公开数据库和 `release_id`。搜索、实体和关系默认20条，保持现有1–100上限；错误按MCP `isError` 返回，读库不可用不泄露文件路径。不含生成、写入或私有候选工具。

MCP SDK版本在根requirements固定为1.12.0。当前版本在正常结束stateless transport时可能记录 `ClosedResourceError`，并有第三方Settings/AnyIO warning；已验证工具结果、退出及网站路径，不据此声称日志无错误或长期运行已验收。
