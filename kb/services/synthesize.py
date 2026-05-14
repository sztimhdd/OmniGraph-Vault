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
import os
import re
from pathlib import Path

# OmniGraph BASE_DIR — synthesis_output.md is written here by kg_synthesize
# (see kg_synthesize.py main() — output path is config.SYNTHESIS_OUTPUT
# which equals BASE_DIR / "synthesis_output.md"). We re-resolve the path at
# call time (not import time) so tests can monkeypatch config.BASE_DIR.
import config as og_config

from kb.services import job_store

# Directive strings — VERBATIM per I18N-07 / QA-02 REQ wording.
DIRECTIVE_ZH = "请用中文回答。\n\n"
DIRECTIVE_EN = "Please answer in English.\n\n"
_DIRECTIVES: dict[str, str] = {"zh": DIRECTIVE_ZH, "en": DIRECTIVE_EN}

# Match `/article/{10-hex}` references the synthesize markdown emits as source links.
_SOURCE_HASH_PATTERN = re.compile(r"/article/([a-f0-9]{10})")

# QA-04: wall-time budget for C1 before fts5_fallback fires. Read once at
# module-import time (per CONFIG-02 pattern); tests reload the module.
KB_SYNTHESIZE_TIMEOUT: int = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))


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

        rows = fts_query(question, lang=None, limit=3)
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
    """
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
    job_store.update_job(
        job_id,
        status="done",
        result={
            "markdown": markdown,
            "sources": sources,
            # v2.0 minimum-viable; v2.1 may extend via canonicalization.
            "entities": [],
        },
        fallback_used=False,
        confidence="kg",
    )
