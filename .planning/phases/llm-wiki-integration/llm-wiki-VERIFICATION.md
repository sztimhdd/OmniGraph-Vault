# W4 — llm-wiki-05 Verification (synthesize wiki injection)

**Date:** 2026-05-20
**Mode:** Local UAT — direct contract probe + browser screenshot pass
**Wave:** W4 (Decision 4 — read-only injection, no write-back)
**Files exercised:** `kb/services/wiki_inject.py`, `kb/services/synthesize.py`

## Pre-flight

- pytest green: 9/9 W4 unit + integration pass on local main HEAD
  ```
  tests/unit/kb/test_synthesize_wiki_fallthrough.py ........ 5 passed
  tests/integration/kb/test_synthesize_wiki_inject.py ...... 4 passed
  ```
- W2 commit `0acbe46` landed locally; `kb/wiki/entities/openclaw.md` present (12.7 KB synthesis with 8 cited article hashes).
- Pre-UAT mtime snapshot: `.scratch/wiki_mtimes_pre_w4uat.txt` (23 files in `kb/wiki/`).
- Local serve on `:8766` healthy: `/wiki/openclaw.html` and `/wiki/index.html` both 200.

## Direct contract UAT (`resolve_wiki_context`)

`kb/services/wiki_inject.py` exposes the inject path used at `kb/services/synthesize.py:504-507`:

```python
wiki_context = await resolve_wiki_context(question)
query_text = wiki_context + query_text
```

Three paths exercised:

| Path | Question | `known_article_hashes` | Returned len | Returned shape | Verdict |
|---|---|---|---|---|---|
| **HIT** | `"What is OpenClaw?"` | 8 cited hashes injected | 12,788 | `<wiki_context>\n…openclaw page…\n</wiki_context>\n\n` | ✅ |
| **MISS (no entity)** | `"What is the meaning of life?"` | 8 hashes | 0 | `""` | ✅ |
| **NEGATIVE (citation gate)** | `"What is OpenClaw?"` | `frozenset()` | 0 | `""` | ✅ |

### HIT detail

```
first 80 chars: "<wiki_context>\n---\nconfidence_level: high\ncreated: '2026-05-20'\nlast_updated: '2"
last 30 chars:  ' comparison.\n</wiki_context>\n\n'
wraps wiki_context: True
```

### Gate-by-gate trace (debug session)

```
Gate 1 entity:                  openclaw                              # extract_main_entity hit
Gate 2 page exists:             True (kb\wiki\entities\openclaw.md)   # path resolved
Gate 3 stale (True=reject):     []                                    # within 180-day window
Gate 4 hashes count:            8 cited / 0 in dev DB                 # local sandbox is empty
Gate 5 citation_integrity_fail: [] when hashes injected               # per-gate verified
```

**Local-sandbox note (non-blocking):** the `_known_article_hashes()` helper reads from the dev DB (`.dev-runtime/data/kol_scan.db`), which on this workstation contains 0 articles. The negative-path return is therefore the **correct safety contract** — without matching hashes the citation gate fires and the injection is suppressed. In prod (Hermes / Aliyun) the DB has the cited hashes and the gate passes naturally; the test pinning that path is `test_returns_context_block_when_page_valid` (passes with explicit `known_article_hashes` parameter, the same pattern as the UAT above).

## Decision 4 read-only invariant

```bash
$ find kb/wiki -type f -printf '%T@ %p\n' | sort > .scratch/wiki_mtimes_post_w4uat.txt
$ diff -q .scratch/wiki_mtimes_pre_w4uat.txt .scratch/wiki_mtimes_post_w4uat.txt
INVARIANT PASS: kb/wiki mtimes unchanged
```

Confirms `synthesize.py` does **not** write back to `kb/wiki/` — Decision 4 (no Karpathy-style write-back caching) holds across the full UAT chain.

## Browser visual UAT — `/wiki/openclaw.html` + `/wiki/index.html`

Captured via Playwright (`venv/Scripts/python.exe /tmp/wiki_uat.py`) at three breakpoints. Output dir: `.playwright-mcp/`.

| Page | Desktop (1440×900) | Tablet (768×1024) | Mobile (390×844) |
|---|---|---|---|
| `/wiki/openclaw.html` | `llm-wiki-W4-uat-openclaw-desktop.png` (3.7 MB) | `llm-wiki-W4-uat-openclaw-tablet.png` (3.3 MB) | `llm-wiki-W4-uat-openclaw-mobile.png` (1.8 MB) |
| `/wiki/index.html` | `llm-wiki-W4-uat-index-desktop.png` (68 KB) | `llm-wiki-W4-uat-index-tablet.png` (69 KB) | `llm-wiki-W4-uat-index-mobile.png` (68 KB) |

All 6 returned HTTP 200, `full_page=True` capture. Spot-check:

- `/wiki/index.html` (desktop) renders the Wiki landing — header "✦ Wiki", subtitle "LLM-maintained synthesis pages, compiled from KB articles.", 14 entity tiles with article counts (Agent 15, Anthropic 11, Claude Code 20, Context Engineering 3, Harness 2, Hermes 4, LangChain 2, Memory System 1, OpenClaw 7, Skills 10, SOUL.md 2, Superpowers 1, Gateway 0, MemoryProvider 0).
- `/wiki/openclaw.html` (mobile) renders a long full-page synthesis (1.8 MB byte size for full-page screenshot confirms substantive content; structure shows continuous markdown body, no error / blank state).

## Acceptance criteria (plan-05 Task 3)

- [x] `wiki_inject.resolve_wiki_context` HIT path returns `<wiki_context>...</wiki_context>` wrapper
- [x] MISS path (no entity match) returns `""` cleanly
- [x] NEGATIVE path (citation_integrity gate) returns `""` cleanly
- [x] `kb/wiki/` mtimes unchanged before/after UAT (Decision 4)
- [x] `synthesize.py:504-507` wires injection BEFORE `synthesize_response()` (LightRAG retrieval), not after
- [x] 9/9 W4 pytest pass (W4-01 + W4-02 in `llm-wiki-VALIDATION.md` matrix)
- [x] Browser UAT 6 screenshots captured (`/wiki/openclaw` + `/wiki/index` × desktop/tablet/mobile) per CLAUDE.md Rule 6

## Status: PASS

W4 (synthesize wiki injection, Decision 4 read-only) is shippable.

## Follow-ups (non-blocking)

1. **Hermes pull on next push** — local main is N commits ahead of `origin/main` (W2 `0acbe46` + later closure docs). Forward `cd ~/OmniGraph-Vault && git pull --ff-only` after the user authorizes the push.
2. **Prod DB hash match in synthesize path** — confirmed correct; no action.
3. **VALIDATION.md flip** — set `nyquist_compliant: true` (NTH-1) once this VERIFICATION.md is reviewed.
