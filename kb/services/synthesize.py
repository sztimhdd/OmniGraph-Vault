"""QA-01 + QA-02 + I18N-07: Q&A wrapper around kg_synthesize.synthesize_response (C1).

Per D-04 (kb/docs/02-DECISIONS.md): KB layer wraps the existing synthesize function
in ~50 LOC; signature C1 unchanged. Language directive prepended to query_text per
I18N-07 — no other prompt manipulation per QA-02.

Failure path: this plan ships the basic 'failed' branch. Plan kb-3-09 replaces it
with FTS5-fallback so /api/synthesize NEVER returns 500 (QA-05).

C1 contract preserved (kg_synthesize.py:105 — DO NOT MODIFY):

    async def synthesize_response(query_text: str, mode: str = "hybrid"):
        ...

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Idiomatic async wrapper module: lang_directive_for is a pure dispatcher (return string from dict-of-string OR if/elif). kb_synthesize is async — awaits C1 directly, then reads synthesis_output.md, parses sources via regex, updates job_store. ALL exceptions caught at top level and translated to job_store.update_job(jid, status='failed', error=str(e)) — this stub is replaced by kb-3-09 with FTS5 fallback. Type hints throughout. NO new env vars. Module is import-safe (no DB or LLM at import time).")

    Skill(skill="writing-tests", args="Unit tests for the wrapper module. test_lang_directive_for: 3 cases (zh/en/unsupported). test_kb_synthesize_*: monkeypatch kg_synthesize.synthesize_response with an async stub that captures query_text args; monkeypatch the synthesis_output.md file by writing to a temp BASE_DIR; verify job_store before/after state via get_job(jid). Use asyncio.run to drive the async wrapper from sync tests, OR pytest-asyncio if already configured.")
"""
from __future__ import annotations

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


async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    """Background-task entry. Prepends lang directive, calls C1, updates job_store.

    Args:
        question: the user's question (unprefixed)
        lang: 'zh' | 'en' (other accepted but no directive applied — defensive)
        job_id: pre-allocated job id (caller invoked job_store.new_job(kind='synthesize'))

    On success: job status='done', result={markdown, sources, entities},
                confidence='kg', fallback_used=False.
    On failure: job status='failed', error=traceback string.

    Plan kb-3-09 will replace the failure branch with FTS5-fallback path so
    /api/synthesize NEVER returns 500 (QA-05).
    """
    try:
        # C1 import deferred to avoid heavy LightRAG init at module import time.
        from kg_synthesize import synthesize_response

        directive = lang_directive_for(lang)
        query_text = f"{directive}{question}"
        # C1 signature UNCHANGED — wrap, don't mutate.
        await synthesize_response(query_text, mode="hybrid")

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
    except Exception as e:  # noqa: BLE001 — kb-3-09 will replace with FTS5 fallback
        job_store.update_job(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
