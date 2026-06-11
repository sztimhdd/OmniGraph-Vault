# 260610-rgm Real-Data Verification — 4-Issue Cluster (#45 #47 #48 #29)

**Date:** 2026-06-11
**Mandate:** user directive — *"本地测试不了的可以去阿里云环境拿真实文章和API测试 但是必须全部进行真实测试才能验收"* (real-article + real-API test of every fix; local where possible, Aliyun for the rest; acceptance requires ALL FOUR real-tested).
**Verifier:** main session (inline orchestrator).

This supplements the unit-test green (17/17 at ship time, now 18/18 after the #47
forward-fix added a regression guard) with **live real-data + real-API evidence**.
Unit tests are necessary but per Principle #6 NOT sufficient — every fix exercised
against real LightRAG / real LLM provider / real prod service state below.

---

## Summary verdict

| Fix | Local real test | Aliyun real test | Verdict |
|-----|-----------------|------------------|---------|
| **#47** atomic-write .pth | apply() on vanilla lightrag 1.4.15 wraps write_nx_graph (os.replace+fsync) | **.pth fires at bare startup both venvs, flag=True** | ✅ **REAL PASS** (+ caught + fixed a real deploy bug) |
| **#29** server citation sweep | real 17.6s Vertex synth, normalize idempotent | **live deployed fn: 10 orphans→0, all 7 prod shapes, idempotent; e2e long_form 9252B clean** | ✅ **REAL PASS** |
| **#48** backup quiesce gate | 3/3 unit (bash subprocess) | **3 gate conditions vs real 31263-node graphml: quiesced→0, busy→1, missing→1** | ✅ **REAL PASS** |
| **#45** os._exit hard-exit | finalize→metrics→exit ~2s w/ genai+LightRAG C-threads alive (DeepSeek-gated, partial) | **full real ainsert via DeepSeek: Metrics→exit gap = 0.62s (not 50min hang)** | ✅ **REAL PASS** |

---

## #47 — LightRAG atomic-write `.pth` delivery — REAL PASS (+ real bug caught)

### Local (corp Windows, vanilla lightrag 1.4.15 = Aliyun prod version)
- `apply()` against the real installed package returned True.
- `write_nx_graph` source BEFORE: `os.replace=False os.fsync=False` → AFTER: `os.replace=True os.fsync=True tmp=True ISSUES#47=True`.
- Signature `(graph, file_name, workspace='_')` matches; real call-site `NetworkXStorage.index_done_callback` confirmed to call `write_nx_graph`.
- 3/3 unit tests green (incl. new `test_delivery_uses_pth_not_sitecustomize` regression guard).

### Aliyun (prod, both venvs) — **a real shipped-fix defect was found and fixed**
- **Bug:** the original 260610-rgm `#47` delivered the patch via `sitecustomize.py`. On Aliyun this **silently never fired**: Debian ships `/usr/lib/python3.11/sitecustomize.py` (apport hook) at `sys.path` index 2, BEFORE venv site-packages at index 4. CPython imports only the FIRST `sitecustomize` on the path → the venv-local one never loaded → `patch_flag=False` at bare startup on BOTH venvs.
- **Real-test caught it** — unit test (which calls `apply()` directly) was green, but the *delivery mechanism* was broken in prod. Exactly the class of runtime issue Principle #6 exists to catch.
- **Forward-fix `ba1121c`:** switched delivery to a `.pth` file (`zz_omnigraph_atomic_write.pth`). The `site` module exec()s the `import`-prefixed line of EVERY `.pth` at startup — immune to the system-file shadow. Script also `rm -f`s the superseded sitecustomize.py. Added static regression guard test.
- **Aliyun verify after re-deploy:** bare `venv-aim1/bin/python -c "import lightrag..."` AND `venv/bin/python` BOTH show `flag=True ISSUES47=True os.replace=True` with NO explicit apply() — the patch now fires automatically and survives `pip --force-reinstall`. Reinstall-survival goal met.

---

## #29 — server-side citation normalization — REAL PASS

### Local (Vertex gemini-flash-lite)
- Real synthesize via C1 `synthesize_response("AI Agent 架构与记忆机制", mode=hybrid)`: 17.64s, real KG retrieval (35 entities / 178 relations / 13 chunks), 1771-char real LLM markdown.
- `_normalize_citations` idempotent on the live output; left `![alt](url)` images untouched.
- This run emitted 0 article citations (flash-lite did not emit orphans) → conversion path not exercised locally.

### Aliyun (DeepSeek — the provider that historically emits the orphans)
- **End-to-end real API:** `POST /api/synthesize {mode:long_form}` via kb-api (DeepSeek) → polled to `status=done confidence=kg` in ~60s, 9252-byte result, 27 `articles/<hash>.html` links, 0 orphan citations, 1 References section, 9 resolved sources. The deployed pipeline produces clean output.
- **Live deployed-function conversion proof:** fed the 7 real prod-observed orphan shapes (`/article/<hash>`, `/article:<hash>`, `article/<hash>`, `article:<hash>`, `article-<hash>`, `article <hash>`, bare `<hash>`) through the **deployed** `kb.services.synthesize._normalize_citations` on Aliyun:
  - BEFORE: `orphans=10 good=0`
  - AFTER: `orphans=0 good=10` — every shape converted to `[<hash6>](articles/<hash>.html)`
  - idempotent=True; English `## References` dedupe works.
- Non-browser consumers (Hermes skill / CLI / JSON) now get clean clickable markdown without depending on qa.js. The client-side qa.js sweep stays in place (defense-in-depth + cached pre-fix responses).

**Known edge (pre-existing, NOT a regression — filed to ISSUES):** bare Chinese `## 参考` / `## 来源` headers are not in `_REFERENCE_KEYWORDS` (`参考文献/参考来源/参考资料/引用` are), so a ZH-headed duplicate References section is not deduped. Real prod LLM headers observed so far are `References` / `参考文献` (covered). Tracking only.

---

## #48 — backup PHASE 0 quiesce gate — REAL PASS

Ran the deployed `scripts/aliyun-backup-260610.sh __quiesce_probe` test-seam against the **real** Aliyun storage dir (`/root/.hermes/omonigraph-vault/lightrag_storage`, graphml live-parsed = 31263 nodes / 45227 edges, 0 `.tmp` orphans):

| Test | Conditions | Expected | Actual |
|------|-----------|----------|--------|
| 1 | empty fd dir + real parseable graphml | exit 0 (quiesced → proceed) | **exit 0** ✓ |
| 2 | fd dir w/ real open-file fd + real graphml | exit 1 (busy → wait) | **exit 1** ✓ |
| 3 | empty fd dir + missing graphml path | exit 1 (unsafe → wait) | **exit 1** ✓ |

All three gate conditions (0 real-file fds AND 0 `.tmp` AND graphml parseable) behave correctly against real prod state. The gate will correctly distinguish a #45-hung-but-quiesced ingest (proceed) from a genuinely-writing ingest (wait).

---

## #45 — os._exit(0) hard-exit — _(verification in progress)_

### Local (corp, partial — DeepSeek-gated)
- Real 1-article ingest via Vertex: Layer1 ran 55 real Gemini calls → 55 candidates (genai HTTP/2 C-threads spawned); real LightRAG init loaded 24022-node graph + 3 vdbs (3072d) + 8 KV stores + embedding model; article queued [1/55].
- Layer2 → DeepSeek `APIConnectionError` (corp blocks DeepSeek — expected) → 0 fully processed.
- **`Successfully finalized 12 storages` → `Metrics written` → process returned ~2s later** — even with genai + LightRAG embedding C-threads ALIVE, the finalize→metrics→exit path that #45 targets took ~2s, NOT 50min.
- **Caveat:** corp DeepSeek block prevented the FULL entity-extract ainsert C-thread set. Aliyun (DeepSeek reachable) is the airtight full-path confirm — below.

### Aliyun (DeepSeek reachable — full ainsert path) — **REAL PASS**
- Manual 1-article fire via `venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 1`, env sourced from `/root/.hermes/.env` (DeepSeek reachable on Aliyun home-network-equivalent egress).
- **Full real ainsert exercised** (the exact path corp blocks): `Done — 1 candidates processed (of 180 total inputs)`; Qdrant `entities` / `relationships` / `chunks` collections initialized; `8 entities Buffered for async processing` — real entity-extract + relation-build + embedding C-thread set was live.
- Note: layer1 hit some Vertex `429 RESOURCE_EXHAUSTED` + `partial_json` on a few batches (the known ISSUES #2 burst pattern) but 120/180 candidates passed and 1 fully ingested — the ainsert path ran for real.
- **Decisive measurement — `Metrics written` → process exit gap = 0.62s** (metrics file mtime 1781182114 → wrapper process-returned 1781182114.62, `rc=0`). Total wall 84s.
- **This is the #45 proof:** the 50min+ post-completion `S`-state hang (3 prior cross-platform recurrences) is gone. `os._exit(0)` after `logging.shutdown()` exits via the `_exit(2)` syscall, bypassing `Py_Finalize`'s join on the third-party C-level threads (Vertex/genai HTTP/2, Qdrant gRPC pool, LightRAG embedding workers) that previously blocked clean shutdown. Process death now ≈ metrics-write time.

---

## Acceptance gate — **ACCEPTED**

Per user mandate, the cluster is accepted **only if all four fixes pass real testing**.

| Fix | Real-test verdict |
|-----|-------------------|
| #45 os._exit | ✅ REAL PASS (Aliyun full ainsert, Metrics→exit 0.62s) |
| #47 .pth atomic-write | ✅ REAL PASS (both venvs bare-startup flag=True; deploy bug found+fixed `ba1121c`) |
| #48 quiesce gate | ✅ REAL PASS (3 conditions vs real 31263-node graphml) |
| #29 citation sweep | ✅ REAL PASS (live deployed fn 10 orphans→0, 7 shapes; e2e long_form clean) |

**All four real-tested and passing. Cluster ACCEPTED.**

### Bonus value of real-testing (Principle #6 vindicated)

The real-deploy pass caught a **shipped #47 defect invisible to the green unit suite**: the
sitecustomize delivery was shadowed by Debian's system sitecustomize and never fired in prod.
A green `apply()` unit test + 17/17 suite said "done"; the actual durability mechanism was broken.
Forward-fixed to `.pth` (`ba1121c`) and re-verified on real Aliyun venvs. This is exactly the
"green tests necessary but not sufficient" failure mode the project's KB/local-UAT discipline exists to close.
