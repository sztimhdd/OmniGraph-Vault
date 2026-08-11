# W5A Production UAT — vitaclaw-aliyun (47.117.244.253)

- **Date (remote)**: 2026-08-12, ~02:16–02:55 CST
- **Deployed commit**: `c8ec5227` (local `main`; "fix(wiki-v2-w5a): repair W1 engine seam, canonical merge insertion, and sources id emission")
- **Deploy method**: SCP exact committed files (GitHub→Aliyun `git pull` times out — known quirk). No git operations performed on the remote tree.
- **Operator**: Hermes subagent (production ops), via `ssh vitaclaw-aliyun` (user root, ed25519 IdentityFile)

---

## 1. PHASE 0 — Recon evidence (pre-deploy baseline)

| Item | Value |
|---|---|
| Remote git HEAD | `a5d3694` (behind local `c8ec5227`; expected — remote runs W5-0 era) |
| Remote tree state | **Dirty** — many uncommitted production hotfixes (`M .gitignore`, `M kb/wiki_update.py`, `M kb/wiki_lint.py`, `M batch_ingest_from_spider.py`, …) |
| Live `kb/wiki_update.py` (working copy) | md5 `07ab054a38033bf3ee74fff1fd2f2666` — W5-0 Gate G/I hotfixes (+57/−2 vs HEAD) — **last-known-good baseline, backed up** |
| Service | `omnigraph-daily-ingest.service` **active (running)** since 2026-08-12 02:16:43 CST; Main PID 3717020 |
| Running process | `/root/OmniGraph-Vault/venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 10` (1.6G RAM, mid-run at recon) |
| Python venv | `/root/OmniGraph-Vault/venv-aim1/bin/python` (**not** `venv/` — recon assumption corrected) |
| `kb/wiki_compiler` | `NO_COMPILER_DIR` — W5A not deployed (confirmed) |
| Entity buffer | `/root/.hermes/omonigraph-vault/entity_buffer/` — **875** files (`0025496582_entities.json`, …) |
| Production wiki | `kb/wiki/entities/` 26 pages; `_suggestions/` 5 files (W5-0 era); **no** `.locks/` dir |
| Production articles DB | `/root/OmniGraph-Vault/data/kol_scan.db` (`KOL_SCAN_DB_PATH` default in batch_ingest; 3581 article hashes) |
| Tooling present | `scripts/wiki_health.py` (CLI: `--wiki-root`, `--db-path`, `--json`), `kb/wiki_lint.py`, `kol_config.py` |

## 2. PHASE 1 — Deploy mapping + verification

Backup (pre-deploy, on remote): `/root/w5a-rollback/`
- `wiki_update.py.bak` — md5 `07ab054a…` == live baseline ✓ (verified identical to working copy)
- `wiki_generate_pages.py.bak`, `.gitignore.bak` — same source copies

| File | Local md5 | Remote md5 | Match |
|---|---|---|---|
| `kb/wiki_update.py` | `fd59d3e981fbbfffd0ee1fd8b74b5e6f` | `fd59d3e981fbbfffd0ee1fd8b74b5e6f` | ✅ |
| `scripts/wiki_generate_pages.py` | `15dd67c56a3394d10acc804a73c6ce2e` | `15dd67c56a3394d10acc804a73c6ce2e` | ✅ |
| `.gitignore` | `d2d9c8b070c4f991bbd554c2e791af11` | `d2d9c8b070c4f991bbd554c2e791af11` | ✅ |
| `kb/wiki_compiler/__init__.py` | `91f5af87261f0f595fc04e066a56711d` | `91f5af87261f0f595fc04e066a56711d` | ✅ |
| `kb/wiki_compiler/models.py` | `3a2ff7c2a53479ffc87c2d46e45bda5b` | `3a2ff7c2a53479ffc87c2d46e45bda5b` | ✅ |
| `kb/wiki_compiler/assembler.py` | `eb2eff892a3239a50349fedeb262cbad` | `eb2eff892a3239a50349fedeb262cbad` | ✅ |
| `kb/wiki_compiler/engine.py` | `819d5259ef8020b44a8e3322242d73f1` | `819d5259ef8020b44a8e3322242d73f1` | ✅ |
| `kb/wiki_compiler/adapters/__init__.py` | `4fb58f7221f6b7eff4ee157d5b7c650d` | `4fb58f7221f6b7eff4ee157d5b7c650d` | ✅ |
| `kb/wiki_compiler/adapters/w3.py` | `a3388e2dffbf5660268d95c3aa7755bf` | `a3388e2dffbf5660268d95c3aa7755bf` | ✅ |

**9/9 md5 MATCH.** `.gitignore` note: local `c8ec5227` version is a strict semantic superset of the remote working copy (diff showed only the W5A tail rules `kb/wiki/.locks/`, `kb/wiki/_suggestions/*.json` + a CRLF normalization) → deployed verbatim, preserving all production ignore rules.

**Import verification** (remote, venv-aim1):
```
IMPORTS_OK
wiki_update routes: ['apply_patch', 'generate_wiki_suggestions', 'run_wiki_update_pipeline', 'w3']
```
W5A import closure has **no `kol_config` dependency** (the local-dev-only module) and no third-party imports beyond stdlib (`fcntl`, `json`, `re`, `tempfile`, …).

## 3. PHASE 2 — UAT A: existing rich page → suggestion_only → JSON, digest unchanged — **PASS**

Real production evidence: hash `0025496582` (entity `weixin`). Existing rich page: copy of production `kb/wiki/entities/agent.md` (14,119 B) into isolated root `/tmp/w5a-uat-a-epm_ck3k/entities/weixin.md`.

```
PATCH_OPS: ['MERGE_SOURCES', 'UPSERT_SECTION', 'SET_METADATA']
CLASSIFY: suggestion_only
APPLY1: {"status": "suggestion", "patch_id": "wpatch-728113e0b47be743",
         "suggestion_path": "/tmp/w5a-uat-a-epm_ck3k/_suggestions/weixin-wpatch-728113e0b47be743.json"}
DIGEST_AFTER: 7452ca05a5f8f1ab… == DIGEST_BEFORE 7452ca05a5f8f1ab… | UNCHANGED: True
APPLY2 (same input again): same patch_id, same suggestion_path
SUGGESTION_FILES: ['weixin-wpatch-728113e0b47be743.json']   (exactly 1 — no duplicate)
SUGGESTION_OPS: ['MERGE_SOURCES', 'UPSERT_SECTION', 'SET_METADATA']
```
Assertions: classify `suggestion_only` ✓; apply status `suggestion` ✓; page digest **unchanged** ✓; deterministic patch_id + suggestion filename, no timestamp-spam duplicates ✓; `validate_evidence` errors `[]` ✓.

## 4. PHASE 3 — UAT B: CREATE_PAGE → canonical page → lint/health PASS — **PASS**

3 **DB-validated** real hashes (`0025496582`, `00258cb49d`, `009e6057eb`; production filter = buffer ∩ `kol_scan.db`) → isolated root `/tmp/w5a-uat-b-2r5l91qb`.

```
OPS: ['CREATE_PAGE']  CLASSIFY: auto_apply
APPLY: {"status": "applied", "patch_id": "wpatch-23d4710c8747452c", "error": null}
```
Generated page (677 B) verified structurally:
- `sources[]` positional `id: 1,2,3` with `type: article` / `ref: "<hex10>"` / `title:` / `provenance:` — ids `== range(1,4)` ✓
- GFM citations `[^1][^2][^3]` in body ✓; `## References` section with `[^N]:` defs for all 3 ✓

**Lint**: `lint_citation_integrity(page, known_hashes)` → `LINT_ISSUES: []` ✓
**Health**: `scripts/wiki_health.py --wiki-root /tmp/w5a-uat-b-2r5l91qb --db-path /root/OmniGraph-Vault/data/kol_scan.db`
```
Wiki Health Report — 2026-08-12   Root: /tmp/w5a-uat-b-2r5l91qb
  Pages: 1   DB hashes: 318
WARNINGS (1): ⚠️  index.md missing      → Exit: WARN
```
Only warning = `index.md missing`, an expected artifact of a single-page isolated root (no page/citation errors). **PASS** with documented caveat.

> **Real finding during UAT B (first attempt):** picked hashes from the buffer only; hash `009332e5e2` exists in the buffer (875 files) but **not** in the DB corpus (318 hashes). Health check flagged `weixin.md: [^3] — article ref '009332e5e2' not in DB corpus`. Production W3 flow filters article hashes through the DB first (`build_w3_evidence_packs` drops unknown hashes), so this is safe in production — but it confirms buffer ⊋ DB drift (875 buffer files vs 234 buffer files whose hash is also in the DB). Re-ran UAT B with DB-validated hashes → clean health output.

## 5. PHASE 4 — UAT C: same-base concurrency → max one winner — **PASS**

Isolated root `/tmp/w5a-uat-c-kxatc5yl`. Seeded a canonical page through the real engine (`CREATE_PAGE`, status `applied`); base digest `b07e6516683b58f2…`. Two **same-base MERGE_SOURCES-only** patches with distinct new evidence (`00258cb49d` vs `009332e5e2`), both classify `auto_apply` (MERGE_SOURCES on canonical page with article evidence). Barrier-synchronized threads.

```
SAME_BASE: True        A_CLS: auto_apply  B_CLS: auto_apply
STATUSES: ['applied', 'conflict']   == expected ['applied','conflict']  ✓
FINAL_HAS_A_REF: False | FINAL_HAS_B_REF: True  → WINNER: B
EXACTLY_ONE_WINNER: True
MERGE_CONFLICT_MARKERS: 0   FRONTMATTER_CLOSED: True   SOURCE_ENTRY_COUNT: 2 (seed + winner)
STRAY_TEMP_FILES: []        LOCK_DIR: ['weixin.md.lock']   (no leftover temp files)
```
Notes: UPSERT_SECTION/SET_METADATA were stripped from the racing patches (documented engine pitfall — UPSERT_SECTION classifies `suggestion_only` and never reaches the digest race); the digest check is exercised by MERGE_SOURCES, which is auto_apply-eligible here. Locking (`fcntl.flock`, 5s blocking acquire) + optimistic concurrency produced exactly one winner with no interleaved/corrupt content.

## 6. PHASE 5 — UAT D: W3 no-network + ingest service healthy — **PASS**

1. `systemctl is-active omnigraph-daily-ingest.service` → **`active`** (since 02:16:43 CST; 1 batch_ingest process running)
2. Network-import grep over `kb/wiki_update.py` + `kb/wiki_compiler/` for `requests|httpx|aiohttp|openai|genai|tavily|databricks|subprocess`:
   - Only matches: provenance **label strings** `tavily-web` (data values in assembler.py, lines 41/78) — **no network imports anywhere in the W3 path** ✓
3. Journal (24h): W3 hook fires per ingest run — W5-0 accounting format from yesterday:
   ```
   Aug 11 19:10:52 … W3 wiki hook: {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}
   Aug 11 21:50:41 … W3 wiki hook: {'suggestions_generated': 6, 'applied': 4, 'dropped': 2}
   Aug 11 23:50:22 … W3 wiki hook: {'suggestions_generated': 8, 'applied': 5, 'dropped': 3}
   ```
   Current run (PID 3717020, started 02:16 pre-deploy) still in LightRAG merge phase at report time — hook line pending.
4. `_wiki_update_check` imports `kb.wiki_update` **lazily at hook time** (`batch_ingest_from_spider.py:1592`) → the running process will load the deployed W5A code when its hook fires; no restart required for the new code to go live.

## 7. Bonus — UAT E: full production seam (generate_wiki_suggestions → apply_suggestion_atomic) — **PASS**

Exact production call path, isolated wiki root only: read-only sqlite conn to `kol_scan.db` (`mode=ro`), production entity-buffer dir, 8 real DB∩buffer hashes, `min_frequency=1`:
```
DB_HASHES: 3581 | WITH_BUFFER_FILE: 234
SUGGESTIONS_GENERATED: 127
RESULTS: 127/127 {applied: true, ops: [CREATE_PAGE]}
ISOLATED_PAGES: 127  (e.g. mcp, openclaw, anthropic, claude-code, deepseek, …)
```
**Production zero-write proof** (before → after): `kb/wiki/entities/` 26 → 26; `_suggestions/` 5 → 5; `.locks/` absent → absent. No production DB/Qdrant/LightRAG touched; DB opened read-only.

## 8. PHASE 6 — Restart decision + final state

- **No restart performed.** The ingest batch (PID 3717020) was mid-run before the deploy; never kill a running ingest mid-batch.
- The lazy `kb.wiki_update` import means this run already executes the deployed W5A code at its W3 hook; subsequent timer runs run W5A end-to-end from process start. **Deferred restart is safe and recorded as evidence.**
- Final state: service `active (running)`, 1 batch_ingest process, W5A files on disk verified (9/9 md5 match), imports OK.

**Rollback path**: `/root/w5a-rollback/` — restore `wiki_update.py.bak` / `wiki_generate_pages.py.bak` / `.gitignore.bak` over the repo files; `rm -rf kb/wiki_compiler` (did not exist pre-deploy).

## 9. Issues / deviations found

1. **Remote tree is dirty** with uncommitted production hotfixes (incl. W5-0 Gate G/I in `kb/wiki_update.py`, +57/−2 vs HEAD). Deploy-by-SCP intentionally bypasses git; the live working-copy state is preserved in `/root/w5a-rollback/`.
2. **venv is `venv-aim1/`**, not `venv/` (task-memory assumption corrected at recon).
3. **Buffer ⊋ DB drift**: 875 buffer files; only 234 buffer hashes are present in `kol_scan.db`. UAT B's first run surfaced a ref that exists in the buffer but not the DB corpus. Production is safe (DB-first filter), but a future cleanup/consistency task may want to reconcile.
4. `.gitignore` line-ending nuance (CRLF on the `error_book.db` line in remote working copy) — cosmetic; deployed file is the semantic superset.
5. Health check on an isolated root warns `index.md missing` — expected; not a page defect.

## 10. Scope compliance

- ✅ No production DB / Qdrant / LightRAG modified (DB opened read-only in UAT E)
- ✅ No writes to `/root/OmniGraph-Vault/kb/wiki/` pages — all UAT roots are `/tmp/w5a-uat-*` isolated dirs
- ✅ No production data deleted; backups in `/root/w5a-rollback/`
- ✅ No force-push, no commits made anywhere
- ✅ No secrets in this report
