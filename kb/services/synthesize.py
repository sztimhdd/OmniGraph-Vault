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

    Skill(skill="python-patterns", args="Define SynthesizeResult dataclass with frozen=True. Fields: markdown (str), sources (list[ArticleSource]), entities (list[EntityMention]), confidence (Literal['kg', 'fts5_fallback', 'kg_unavailable', 'no_results']), fallback_used (bool), error (Optional[str]). ArticleSource has hash + title + lang. EntityMention has name + article_count. Idiomatic Python — no breaking changes to existing job_store update contract. Place at module top of kb/services/synthesize.py after imports. Helper to serialize to dict via dataclasses.asdict for job_store payload.")

    Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + real FastAPI TestClient + MOCKED kg_synthesize.synthesize_response (because real LightRAG is slow + non-deterministic). Test: KG success with markdown containing 3 /article/{hash}.html refs returns SynthesizeResult.sources with title+lang from DB. Test: KG success with markdown lacking refs returns sources=[], confidence='no_results'. Test: KG exception falls back to FTS5 path. Test: KG timeout falls back to FTS5 path. Test: FTS5 fallback returns valid SynthesizeResult shape. Test: entities_for_articles populated when sources present. Test: DATA-07 reject articles never surface as sources.")
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

# OmniGraph BASE_DIR — synthesis_output.md is written here by kg_synthesize
# (see kg_synthesize.py main() — output path is config.SYNTHESIS_OUTPUT
# which equals BASE_DIR / "synthesis_output.md"). We re-resolve the path at
# call time (not import time) so tests can monkeypatch config.BASE_DIR.
import config as og_config

from kb import config as kb_config
from kb.data import article_query
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


# ---------------------------------------------------------------------------
# kb-v2.1-4: structured result schema
# ---------------------------------------------------------------------------
# Replaces the v2.0 hardcoded _ENTITY_HINTS list + heuristic backfill with a
# typed dataclass surface. ``SynthesizeResult.asdict()`` produces a plain
# dict that ``job_store.update_job(result=...)`` stores; qa.js (kb/static)
# reads ``s.hash``/``s.title``/``s.lang`` from sources[] and ``e.name`` from
# entities[] — both compatible with these field names verbatim.

ConfidenceLevel = Literal["kg", "fts5_fallback", "kg_unavailable", "no_results"]


@dataclass(frozen=True)
class ArticleSource:
    """One source-article chip rendered next to the synthesized answer."""
    hash: str
    title: str
    lang: Optional[str]  # 'zh-CN' / 'en' / 'unknown' / None


@dataclass(frozen=True)
class EntityMention:
    """One entity chip — KOL-only (extracted_entities is KOL-only per prod)."""
    name: str
    article_count: int


@dataclass(frozen=True)
class SynthesizeResult:
    """Structured payload stored on a /api/synthesize job at terminal state."""
    markdown: str
    confidence: ConfidenceLevel
    fallback_used: bool
    sources: list[ArticleSource] = field(default_factory=list)
    entities: list[EntityMention] = field(default_factory=list)
    error: Optional[str] = None

    def asdict(self) -> dict:
        """Serialize to the dict shape job_store stores + qa.js consumes."""
        return dataclasses.asdict(self)


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
    """Extract distinct /article/{hash} references from synthesis markdown.

    Order is the first-occurrence order in the markdown — preserves the
    LLM's own source-prominence ordering. Pure function.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _SOURCE_HASH_PATTERN.findall(markdown):
        if match in seen:
            continue
        seen.add(match)
        out.append(match)
    return out


def _resolve_sources_from_markdown(markdown: str) -> list[ArticleSource]:
    """kb-v2.1-4: parse ``/article/{hash}`` refs from markdown and join DB.

    Returns ArticleSource entries in markdown-order for hashes that resolve
    through DATA-07; silently skips hashes that fail the quality filter or
    don't exist. Returns [] on any DB failure — the markdown answer is the
    primary product, source-chip resolution is decorative and MUST NOT
    poison the never-500 contract of /api/synthesize.
    """
    hashes = _extract_source_hashes(markdown)
    if not hashes:
        return []
    try:
        rows = article_query.articles_by_hashes(hashes)
    except Exception as e:  # noqa: BLE001 — never-500 contract: log + degrade
        _log.warning("articles_by_hashes failed (%s): %s; sources=[]", type(e).__name__, e)
        return []
    return [
        ArticleSource(hash=r["hash"], title=r["title"], lang=r["lang"])
        for r in rows
    ]


def _resolve_entities_for_sources(source_hashes: list[str]) -> list[EntityMention]:
    """kb-v2.1-4: top entities mentioned across resolved source articles.

    Returns [] on any DB failure (same never-500 rationale as
    _resolve_sources_from_markdown).
    """
    if not source_hashes:
        return []
    try:
        rows = article_query.entities_for_articles(source_hashes, limit=8)
    except Exception as e:  # noqa: BLE001 — never-500 contract: log + degrade
        _log.warning("entities_for_articles failed (%s): %s; entities=[]", type(e).__name__, e)
        return []
    return [
        EntityMention(name=r["name"], article_count=r["article_count"])
        for r in rows
    ]


def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
    """QA-05: FTS5 top-3 fallback when LightRAG synthesis fails or times out.

    NEVER raises (worst case: status='done' with confidence='no_results').
    See kb-3-UI-SPEC §3.1 fts5_fallback state for the UI consumer of confidence.

    kb-v2.1-4: result is now ``SynthesizeResult.asdict()`` rather than a
    bespoke dict; sources are full ArticleSource objects (hash+title+lang)
    instead of plain hash strings, so qa.js renders the same chip surface
    as the KG happy path. Entities stay [] on fallback (qa.js skips entity
    rendering when fallback_used per kb-3 UI-SPEC §3.1 D-9).
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
            result = SynthesizeResult(
                markdown=markdown,
                confidence="no_results",
                fallback_used=True,
                sources=[],
                entities=[],
                error=reason,
            )
            job_store.update_job(
                job_id,
                status="done",
                result=result.asdict(),
                fallback_used=True,
                confidence="no_results",
                error=reason,
            )
            return
        parts: list[str] = [
            "> Note: KG synthesis unavailable — keyword-based fallback. "
            "/ 知识图谱不可用 — 关键词检索快速参考。\n",
        ]
        sources: list[ArticleSource] = []
        for h, title, snippet, lg, _source in rows:
            parts.append(
                f"### {title}\n\n{snippet}\n\n[/article/{h}](/article/{h})\n"
            )
            sources.append(ArticleSource(hash=h, title=title or "", lang=lg))
        markdown = "\n".join(parts)
        result = SynthesizeResult(
            markdown=markdown,
            confidence="fts5_fallback",
            fallback_used=True,
            sources=sources,
            entities=[],
            error=reason,
        )
        job_store.update_job(
            job_id,
            status="done",
            result=result.asdict(),
            fallback_used=True,
            confidence="fts5_fallback",
            error=reason,
        )
    except Exception as e:  # noqa: BLE001 — last-resort: NEVER raise out of fallback
        # FTS5 itself failed (DB locked, table dropped, etc.). Still mark done.
        result = SynthesizeResult(
            markdown=(
                f"> Synthesis + fallback both failed.\n\n"
                f"Reason: {reason}; FTS5 reason: {type(e).__name__}"
            ),
            confidence="no_results",
            fallback_used=True,
            sources=[],
            entities=[],
            error=f"{reason} | fts5: {type(e).__name__}: {e}",
        )
        job_store.update_job(
            job_id,
            status="done",
            result=result.asdict(),
            fallback_used=True,
            confidence="no_results",
            error=result.error,
        )


async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    """Background-task entry. Prepends lang directive, calls C1, updates job_store.

    Args:
        question: the user's question (unprefixed)
        lang: 'zh' | 'en' (other accepted but no directive applied — defensive)
        job_id: pre-allocated job id (caller invoked job_store.new_job(kind='synthesize'))

    On C1 success (kb-v2.1-4):
        Markdown is parsed for /article/{hash} refs; each hash resolves to
        ArticleSource via DB join (DATA-07 filtered). Top entities for the
        resulting article cohort populate result.entities. confidence='kg'
        when sources>0, 'no_results' when sources==[]. fallback_used=False.
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

    # kb-v2.1-4 happy path: structured resolution from real DB joins.
    markdown = _read_synthesis_output()
    sources = _resolve_sources_from_markdown(markdown)
    entities = _resolve_entities_for_sources([s.hash for s in sources])
    confidence: ConfidenceLevel = "kg" if sources else "no_results"
    result = SynthesizeResult(
        markdown=markdown,
        confidence=confidence,
        fallback_used=False,
        sources=sources,
        entities=entities,
    )
    job_store.update_job(
        job_id,
        status="done",
        result=result.asdict(),
        fallback_used=False,
        confidence=confidence,
    )
