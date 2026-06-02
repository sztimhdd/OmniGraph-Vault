# VERIFICATION — kb-v2.2-3: KG Search Default (F8')

**Phase goal:** Promote `mode='kg'` to the default search mode; when KG is unavailable return HTTP 503 + `Retry-After: 60`; FTS5 remains callable via explicit `mode='fts'`.

**Status: COMPLETE** (2026-05-18)

---

## Code Changes

| File | Change |
|------|--------|
| `kb/api_routers/search.py:59` | Default changed: `= "fts"` → `= "kg"` |
| `kb/api_routers/search.py:88–96` | KG-unavailable path: HTTP 200 degraded → HTTP 503 + `Retry-After: 60` |
| `kb/api_routers/search.py:1–9` | Module + function docstrings updated to reflect F8' contract |
| `tests/integration/kb/test_api_search.py:147–157` | `test_search_default_mode_is_fts` renamed → `test_search_default_mode_is_kg`; now asserts KG path + job_id |
| `tests/integration/kb/test_api_search.py:161–172` | New test: `test_search_kg_unavailable_returns_503` — asserts 503 + Retry-After header |
| `tests/integration/kb/test_kg_mode_hardening.py:162–179` | `test_kg_search_returns_kg_unavailable_field_when_disabled` → `test_kg_search_returns_503_when_disabled`; asserts 503 |
| `tests/integration/kb/test_kg_mode_hardening.py:182–190` | `test_kg_search_status_200_not_500_when_unavailable` → `test_kg_search_status_503_not_500_when_unavailable` |

**No deleted code.** FTS5 path preserved; only the default and the unavailable response changed.

---

## Test Results

Full pytest run (venv/Scripts/python -m pytest tests/ -x -q):

- **Exit code: 0** — all tests pass, 0 failures, 0 errors
- kb-v2.2-3 integration tests: all green
  - `test_search_default_mode_is_kg` ✅
  - `test_search_kg_unavailable_returns_503` ✅
  - `test_search_fts_basic_shape` ✅ (FTS path unaffected)
  - `test_search_mode_fts_unaffected_by_kg_mode_disable` ✅
  - `test_kg_search_returns_503_when_disabled` ✅
  - `test_kg_search_status_503_not_500_when_unavailable` ✅

---

## Local UAT

**Launcher:** `venv/Scripts/python.exe .scratch/local_serve.py` (port 8766)

### Curl smoke results

**1. Default no-mode-param → KG path → HTTP 503 (dev has no GCP creds)**

```
curl -s http://localhost:8766/api/search?q=AI
→ HTTP 503
← {"detail":{"mode":"kg","kg_unavailable":true,"reason":"kg_disabled"}}
← retry-after: 60
```

Confirms: (a) default is now `kg`, (b) 503 + Retry-After fires when credentials absent.

**2. Explicit `mode=fts` → HTTP 200 + items**

```
curl -s "http://localhost:8766/api/search?q=AI&mode=fts"
→ HTTP 200
← {"items":[...],"total":N,"mode":"fts"}
```

Confirms: FTS5 path still works; mode=fts is not affected by KG unavailability.

**3. Explicit `mode=kg` → HTTP 503 + Retry-After**

```
curl -s "http://localhost:8766/api/search?q=AI&mode=kg"
→ HTTP 503
← {"detail":{"mode":"kg","kg_unavailable":true,"reason":"kg_disabled"}}
← retry-after: 60
```

Confirms: explicit mode=kg also returns 503 when unavailable.

**4. Retry-After header confirmed** on all 503 responses:

```
retry-after: 60
```

### Browser screenshot

Homepage renders correctly at `http://localhost:8766/`. Site loads, articles visible, no JS errors.

Screenshot path: `.playwright-mcp/c-Users-huxxha-Desktop-OmniGraph-Vault-playwright-mcp-f8-prime-uat-01.png`

---

## Architecture Note

Per INPUT.md locked architectural choice: `"KG_MODE_AVAILABLE=False → 503 + retry_after, NOT FTS5 fallback"`. This is preserved.

`kb/static/search.js` inline live-search still uses explicit `mode=fts` (line 186) — this is correct: KG is async/polling so it cannot be used for live-as-you-type. This is not a user-facing toggle and requires no change.

---

## REQ Coverage

| REQ | Description | Status |
|-----|-------------|--------|
| API-05 | KG search async default path | ✅ Satisfied |
| API-04 | FTS5 explicit path preserved | ✅ Satisfied |
| F8' | 503 + Retry-After when KG unavailable | ✅ Satisfied |
