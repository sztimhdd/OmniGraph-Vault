"""QA-01 + QA-02 + I18N-07 + QA-04 + QA-05: Q&A wrapper around kg_synthesize.synthesize_response (C1).

Per D-04 (kb/docs/02-DECISIONS.md): KB layer wraps the existing synthesize function
in ~50 LOC; signature C1 unchanged. Language directive prepended to query_text per
I18N-07 — no other prompt manipulation per QA-02.

Failure path (kb-3-09):
    - QA-04: ``await synthesize_response(...)`` is wrapped in
      ``asyncio.wait_for(timeout=KB_SYNTHESIZE_TIMEOUT)``. On timeout the wrapper
      falls through to the FTS5 path.
    - QA-05: any exception from C1 (LightRAG down, embedding 429, network error,
      timeout) triggers ``_fts5_fallback`` which queries ``articles_fts`` for the
      top-3 hits and stitches them into ``result.markdown`` with a bilingual
      banner. The job is marked ``status='done'`` with
      ``confidence='fts5_fallback'`` + ``fallback_used=True``.
    - Last-resort: if FTS5 itself is unavailable (catastrophic), the job is
      still ``status='done'`` with ``confidence='no_results'`` — the
      polling endpoint MUST NEVER return 500.

C1 contract preserved (kg_synthesize.py:105 — DO NOT MODIFY):

    async def synthesize_response(query_text: str, mode: str = "hybrid"):
        ...

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Idiomatic async wrapper module: lang_directive_for is a pure dispatcher (return string from dict-of-string OR if/elif). kb_synthesize is async — awaits C1 directly, then reads synthesis_output.md, parses sources via regex, updates job_store. ALL exceptions caught at top level and translated to job_store.update_job(jid, status='failed', error=str(e)) — this stub is replaced by kb-3-09 with FTS5 fallback. Type hints throughout. NO new env vars. Module is import-safe (no DB or LLM at import time).")

    Skill(skill="writing-tests", args="Unit tests for the wrapper module. test_lang_directive_for: 3 cases (zh/en/unsupported). test_kb_synthesize_*: monkeypatch kg_synthesize.synthesize_response with an async stub that captures query_text args; monkeypatch the synthesis_output.md file by writing to a temp BASE_DIR; verify job_store before/after state via get_job(jid). Use asyncio.run to drive the async wrapper from sync tests, OR pytest-asyncio if already configured.")

    Skill(skill="python-patterns", args="Replace the broad except branch in kb_synthesize with two-stage handling: (1) wrap synthesize_response in asyncio.wait_for(..., timeout=KB_SYNTHESIZE_TIMEOUT) — TimeoutError caught explicitly; (2) general Exception catches everything else. Both call the same _fts5_fallback helper with a `reason` arg. _fts5_fallback queries fts_query(question, limit=3) — cross-lang for graceful degradation — concats top-3 (title + snippet) into markdown with a banner. The banner copy uses the SAME locale key concept as qa.fallback.explainer (kb-3-03) but is hard-coded bilingual in the markdown for non-i18n contexts (Hermes agent skill consumers). Last-resort: if fts_query itself raises (DB unavailable), still set job status='done' with confidence='no_results' — /api/synthesize MUST NEVER 500. Type hints throughout.")

    Skill(skill="writing-tests", args="Extend test_synthesize_wrapper.py with 5 fallback-path tests. Cover: exception path → fts5_fallback, timeout path → fts5_fallback (use sleep > timeout), top-3 hits in result, sources list populated, FTS5-also-fails → no_results last-resort. For the timeout test, set KB_SYNTHESIZE_TIMEOUT=1 and patch synthesize_response with `await asyncio.sleep(2)` — must time out within 2s wall-time. Extend test_api_synthesize.py with 3 API-level integration tests verifying /api/synthesize returns 202 + eventually 200/done with confidence='fts5_fallback' (never 500). Reuse the populated articles_fts fixture pattern from test_api_search.py.")
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

# OmniGraph BASE_DIR — synthesis_output.md is written here by kg_synthesize
# (see kg_synthesize.py main() — output path is config.SYNTHESIS_OUTPUT
# which equals BASE_DIR / "synthesis_output.md"). We re-resolve the path at
# call time (not import time) so tests can monkeypatch config.BASE_DIR.
import config as og_config

from kb import config as kb_config
from kb.services import job_store

_log = logging.getLogger(__name__)

# Directive strings — VERBATIM per I18N-07 / QA-02 REQ wording.
DIRECTIVE_ZH = "请用中文回答。\n\n"
DIRECTIVE_EN = "Please answer in English.\n\n"
_DIRECTIVES: dict[str, str] = {"zh": DIRECTIVE_ZH, "en": DIRECTIVE_EN}

# Match `/article/{10-hex}` references the synthesize markdown emits as source links.
_SOURCE_HASH_PATTERN = re.compile(r"/article/([a-f0-9]{10})")

# QA-04: wall-time budget for C1 before fts5_fallback fires. Read once at
# module-import time (per CONFIG-02 pattern); tests reload the module.
KB_SYNTHESIZE_TIMEOUT: int = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))


# kb-v2.1-1 KG-mode hardening: proactive credential file existence check at
# module import time. Production observation 2026-05-14 (Aliyun): KG search
# triggered LightRAG embedding init which logged a missing local credential
# path AND caused an OOM kill. The flag below gates /api/search?mode=kg + the
# synthesize wrapper short-circuit so the api stays in controlled-degraded
# mode when credentials are absent OR unreadable.
#
# Reasons surfaced to clients (HTTP 200, no path leakage):
#   kg_disabled — neither KB_KG_GCP_SA_KEY_PATH nor GOOGLE_APPLICATION_CREDENTIALS set
#   kg_credentials_missing — env var set but file does not exist
#   kg_credentials_unreadable — file exists but cannot be opened (permissions, etc.)
def _check_kg_mode_available() -> tuple[bool, str]:
    """Return (available, reason) — reason is empty string when available."""
    p = kb_config.KB_KG_GCP_SA_KEY_PATH
    if p is None:
        return False, "kg_disabled"
    try:
        with p.open("rb") as fp:
            fp.read(1)
    except FileNotFoundError:
        return False, "kg_credentials_missing"
    except OSError:
        return False, "kg_credentials_unreadable"
    return True, ""


KG_MODE_AVAILABLE: bool
KG_MODE_UNAVAILABLE_REASON: str
KG_MODE_AVAILABLE, KG_MODE_UNAVAILABLE_REASON = _check_kg_mode_available()
if not KG_MODE_AVAILABLE:
    _log.warning(
        "KG mode unavailable (reason=%s) — /api/search?mode=kg will return "
        "controlled-degraded response; /api/synthesize will fall back to FTS5. "
        "Set KB_KG_GCP_SA_KEY_PATH or GOOGLE_APPLICATION_CREDENTIALS to a "
        "readable GCP service-account JSON to enable KG mode.",
        KG_MODE_UNAVAILABLE_REASON,
    )

KG_FALLBACK_SUGGESTION = (
    "Use mode=fts for keyword search or /api/synthesize for Q&A."
)


def lang_directive_for(lang: str) -> str:
    """Return the language directive string for the given lang code.

    Per I18N-07 + QA-02:
        'zh' -> '请用中文回答。\\n\\n'
        'en' -> 'Please answer in English.\\n\\n'
        other -> ''  (defensive — empty so query passes through unchanged)
    """
    return _DIRECTIVES.get(lang, "")


def _read_synthesis_output() -> str:
    """Read kg_synthesize's canonical output file (config.BASE_DIR/synthesis_output.md).

    Returns empty string if the file doesn't exist (treat as 'C1 produced no output').
    EAFP per python-patterns SKILL: try to read, return '' on OSError.
    """
    p = Path(og_config.BASE_DIR) / "synthesis_output.md"
    try:
        return p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def _extract_source_hashes(markdown: str) -> list[str]:
    """Extract distinct /article/{hash} references from synthesis markdown."""
    return sorted({m for m in _SOURCE_HASH_PATTERN.findall(markdown)})


# v2.0 minimum-viable hardcoded list — covers most-asked entities for UI chip surface.
# v2.1 backlog: replace with systematic entity source resolution from
# extracted_entities table joined to KG result articles, OR from LightRAG
# entity_canonical lookup. C1 contract is read-only; resolution stays in this
# wrapper.
_ENTITY_HINTS: tuple[str, ...] = (
    "AI Agent",
    "LangGraph",
    "LangChain",
    "CrewAI",
    "RAG",
    "MCP",
    "OpenAI",
    "Claude Code",
    "Claude",
    "DeepSeek",
    "LightRAG",
    "Agent",
)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _fallback_search_terms(question: str) -> list[str]:
    """Return broad FTS terms for source chips when the KG markdown has no links."""
    q = (question or "").strip()
    lower = q.lower()
    terms: list[str] = []
    if q:
        terms.append(q)
    if "ai" in lower and "agent" in lower:
        terms.append("AI Agent")
    if "agent" in lower:
        terms.append("Agent")
    for hint in _ENTITY_HINTS:
        if hint.lower() in lower:
            terms.append(hint)
    return _dedupe(terms)


def _source_hashes_from_fts(question: str, limit: int = 3) -> list[str]:
    """Best-effort source chips for KG answers that omit explicit source links.

    KG synthesis (C1) occasionally produces an answer without /article/{hash}
    back-references in its markdown — typically when it draws on implicit graph
    relationships rather than verbatim passages. This function runs a lightweight
    FTS5 probe to surface the most relevant articles anyway, so the UI source-chip
    row is never empty on a valid KG answer.

    Strategy: try each term from _fallback_search_terms(question) in order, return
    the first non-empty FTS5 result set. Falls back gracefully to [] on any DB or
    import error — NEVER raises.

    Args:
        question: the user's original question (no lang directive prefix).
        limit: max chips to return (default 3, matching the FTS5 fallback cap).

    Returns:
        List of article hash strings (may be empty if no FTS match found or DB error).
    """
    try:
        from kb.services.search_index import fts_query

        for term in _fallback_search_terms(question):
            rows = fts_query(term, lang=None, limit=limit)
            if rows:
                return [h for h, _title, _snippet, _lg, _source in rows]
    except Exception:
        return []
    return []


def _entity_candidates(question: str, markdown: str) -> list[str]:
    """Small visible entity list for the UI chip surface; not a KG canonicalizer."""
    haystack = ((question or "") + "\n" + (markdown or "")).lower()
    return [hint for hint in _ENTITY_HINTS if hint.lower() in haystack][:8]


def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
    """QA-05: FTS5 top-3 fallback when LightRAG synthesis fails or times out.

    NEVER raises (worst case: status='done' with confidence='no_results').
    See kb-3-UI-SPEC §3.1 fts5_fallback state for the UI consumer of confidence.

    Args:
        question: the user's question (verbatim, no directive prepend — FTS5
            tokenizer does not need the lang directive)
        lang: 'zh' | 'en' — passed for symmetry but FTS5 query is cross-lang
            (lang=None to fts_query) for graceful degradation
        job_id: pre-allocated job id whose state will be updated
        reason: human-readable string describing why C1 failed (e.g.
            'C1 timeout', 'RuntimeError: LightRAG unavailable')
    """
    try:
        # Lazy import — keeps module-import cheap and lets tests monkeypatch.
        from kb.services.search_index import fts_query

        rows = []
        for term in _fallback_search_terms(question):
            rows = fts_query(term, lang=None, limit=3)
            if rows:
                break
        if not rows:
            markdown = (
                "> Note: 暂时无法生成完整回答 / Synthesis temporarily unavailable.\n\n"
                "未找到与你问题匹配的内容 / No matching content found in the knowledge base."
            )
            job_store.update_job(
                job_id,
                status="done",
                result={"markdown": markdown, "sources": [], "entities": []},
                fallback_used=True,
                confidence="no_results",
                error=reason,
            )
            return
        parts: list[str] = [
            "> Note: KG synthesis unavailable — keyword-based fallback. "
            "/ 知识图谱不可用 — 关键词检索快速参考。\n",
        ]
        sources: list[str] = []
        for h, title, snippet, _lg, _source in rows:
            parts.append(
                f"### {title}\n\n{snippet}\n\n[/article/{h}](/article/{h})\n"
            )
            sources.append(h)
        markdown = "\n".join(parts)
        job_store.update_job(
            job_id,
            status="done",
            result={"markdown": markdown, "sources": sources, "entities": []},
            fallback_used=True,
            confidence="fts5_fallback",
            error=reason,
        )
    except Exception as e:  # noqa: BLE001 — last-resort: NEVER raise out of fallback
        # FTS5 itself failed (DB locked, table dropped, etc.). Still mark done.
        job_store.update_job(
            job_id,
            status="done",
            result={
                "markdown": (
                    f"> Synthesis + fallback both failed.\n\n"
                    f"Reason: {reason}; FTS5 reason: {type(e).__name__}"
                ),
                "sources": [],
                "entities": [],
            },
            fallback_used=True,
            confidence="no_results",
            error=f"{reason} | fts5: {type(e).__name__}: {e}",
        )


async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    """Background-task entry. Prepends lang directive, calls C1, updates job_store.

    Args:
        question: the user's question (unprefixed)
        lang: 'zh' | 'en' (other accepted but no directive applied — defensive)
        job_id: pre-allocated job id (caller invoked job_store.new_job(kind='synthesize'))

    On C1 success: job status='done', result={markdown, sources, entities},
                   confidence='kg', fallback_used=False.
    On C1 timeout (KB_SYNTHESIZE_TIMEOUT): _fts5_fallback fires; job status='done'
                   with confidence='fts5_fallback' OR 'no_results' (NEVER-500).
    On C1 exception: same fallback path.
    On KG mode unavailable (kb-v2.1-1): _fts5_fallback fires WITHOUT attempting
                   C1 — avoids LightRAG init / potential OOM / credential leak.
    """
    # kb-v2.1-1 KG-mode hardening: short-circuit before LightRAG init when the
    # credential probe at import time told us KG mode is unavailable. Same
    # never-500 contract; same FTS5 fallback path.
    if not KG_MODE_AVAILABLE:
        _fts5_fallback(
            question, lang, job_id,
            reason=f"KG mode unavailable: {KG_MODE_UNAVAILABLE_REASON}",
        )
        return

    # C1 import deferred to avoid heavy LightRAG init at module import time.
    from kg_synthesize import synthesize_response

    directive = lang_directive_for(lang)
    query_text = f"{directive}{question}"
    try:
        # QA-04: bound C1 wall-time. asyncio.wait_for raises TimeoutError on
        # exceedance; the inner coroutine is cancelled.
        await asyncio.wait_for(
            synthesize_response(query_text, mode="hybrid"),
            timeout=KB_SYNTHESIZE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _fts5_fallback(question, lang, job_id, reason="C1 timeout")
        return
    except Exception as e:  # noqa: BLE001 — QA-05: NEVER 500; route to fallback
        _fts5_fallback(question, lang, job_id, reason=f"{type(e).__name__}: {e}")
        return

    # Happy path: C1 wrote synthesis_output.md; read it back.
    markdown = _read_synthesis_output()
    sources = _extract_source_hashes(markdown)
    if not sources:
        sources = _source_hashes_from_fts(question)
    job_store.update_job(
        job_id,
        status="done",
        result={
            "markdown": markdown,
            "sources": sources,
            # v2.0 minimum-viable; v2.1 may extend via canonicalization.
            "entities": _entity_candidates(question, markdown),
        },
        fallback_used=False,
        confidence="kg",
    )
