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

    Skill(skill="python-patterns", args="kb-v2.1-5 long-form prompt templates: define _LONG_FORM_PROMPT_TEMPLATE_ZH / _EN as module-level multi-line string constants parameterized by user question. Output target 1500-3000 字 / 800-1500 words, ## headings × 3-5 sections, /article/{hash} citations, bold entities, ![alt](URL) images, no-fabrication clause. kb_synthesize accepts mode='qa'|'long_form' default 'qa' for backward compat.")

    Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + real FastAPI TestClient + MOCKED kg_synthesize.synthesize_response (because real LightRAG is slow + non-deterministic). Test: KG success with markdown containing 3 /article/{hash}.html refs returns SynthesizeResult.sources with title+lang from DB. Test: KG success with markdown lacking refs returns sources=[], confidence='no_results'. Test: KG exception falls back to FTS5 path. Test: KG timeout falls back to FTS5 path. Test: FTS5 fallback returns valid SynthesizeResult shape. Test: entities_for_articles populated when sources present. Test: DATA-07 reject articles never surface as sources.")
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from kb import config as kb_config
from kb.data import article_query
from kb.services import job_store
from kb.services.wiki_inject import resolve_wiki_context
from lightrag.lightrag import LightRAG

_log = logging.getLogger(__name__)

# Directive strings — VERBATIM per I18N-07 / QA-02 REQ wording.
DIRECTIVE_ZH = "请用中文回答。\n\n"
DIRECTIVE_EN = "Please answer in English.\n\n"
_DIRECTIVES: dict[str, str] = {"zh": DIRECTIVE_ZH, "en": DIRECTIVE_EN}

# Match article-hash references the synthesize markdown emits as source links.
# Accepts both legacy `/article/{hash}` (pre-260601-link-fix, broken) and the
# current relative `articles/{hash}.html` (post-fix — works on /kb/ subpath
# Aliyun + root-path Databricks).
_SOURCE_HASH_PATTERN = re.compile(r"articles?/([a-f0-9]{10})")

# 260519-s65 belt-and-suspenders: rewrite legacy `http(s)://host:8765/` image
# URLs (kg_synthesize.py:33 IMAGE_URL_DIRECTIVE injects this prefix) to the
# kb-served `/static/img/` mount. Applied to long_form / qa LLM output before
# storing markdown so even if the prompt template instruction is overridden,
# the browser still sees servable paths. Matches `http://localhost:8765/`,
# `https://1.2.3.4:8765/`, etc.
_LEGACY_IMAGE_URL_PATTERN = re.compile(r"https?://[^/\s)]+:8765/")

# ISSUES #29: server-side citation normalizer. Despite the prompt asking for
# [label](articles/<hash>.html), the LLM (both DeepSeek + Claude) emits ~7
# orphan shapes. qa.js sweeps these client-side, but non-browser consumers
# (Hermes skill, /api/synthesize JSON consumers, CLI scripts) never run qa.js,
# so we also normalize here before the markdown is stored / returned. Mirrors
# qa.js rewriteOrphanCitations Pass 1 (bracketed article refs, 6 separators) +
# Pass 2 (bare 10-hex hash) and the References-section dedupe.
#   Pass 1 covers: [/article/<h>] [/article:<h>] [article/<h>] [article:<h>]
#                  [article-<h>] [article <h>]
#   Pass 2 covers: [<h>]   (bare 10-hex, no following '(' so real links survive)
_ORPHAN_ARTICLE_CITATION = re.compile(r"\[/?article[\s/:_-]([a-f0-9]{10})\]")
_BARE_HASH_CITATION = re.compile(r"\[([a-f0-9]{10})\](?!\()")
_REFERENCE_KEYWORDS = (
    "references", "reference", "参考文献", "参考来源", "参考资料", "引用",
)

# QA-04: wall-time budget for C1 before fts5_fallback fires. Read once at
# module-import time (per CONFIG-02 pattern); tests reload the module.
KB_SYNTHESIZE_TIMEOUT: int = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# kb-v2.1-5: long-form research prompt templates
# ---------------------------------------------------------------------------
# When mode='long_form', kb_synthesize wraps the user question in one of these
# templates before passing to C1 (kg_synthesize.synthesize_response). The C1
# contract is unchanged — same str-arg → str-output signature; we just send a
# longer, more directive query_text. The resulting markdown reuses the v2.1-4
# /article/{hash} regex resolution + image-path rewriting + UI 8-state matrix
# unchanged.
#
# Skill(skill="python-patterns", args="Module-level multi-line string constants
# parameterized by user question via .format(question=...). Note the doubled
# braces around {{hash}} so str.format leaves the literal `{hash}` for the LLM
# to fill in when emitting /article/{hash}.html refs.")

_LONG_FORM_PROMPT_TEMPLATE_ZH = """请基于知识图谱中的真实内容,写一篇深度研究文章。

主题:{question}

要求:
1. 结构化:使用 markdown ## 标题分 3-5 个章节
2. 字数:1500-3000 字
3. 引用:正文每个论点用 markdown 行内链接格式 [短标签](articles/{{hash}}.html)
   (hash 是文章在知识库中的 10 字符哈希)
   末尾如果列 References / 参考文献 章节,**必须**用 markdown link 格式:
   - [完整文章标题](articles/{{hash}}.html)
   严禁裸文本 [1] [2] 列表 — 那不会渲染成可点击链接,用户点不了。
4. 实体:关键技术 / 产品 / 人物用 **粗体** 标注
5. 图片:如果源文章中有相关图片,使用相对路径格式 ![alt](/static/img/{{hash}}/{{n}}.jpg)
   (hash 是 10 字符文章哈希,n 是图片序号)
   严禁使用 http://localhost:8765/ 或任何绝对 URL — 浏览器无法访问该端口,会全部 404。
6. 不要编造任何信息 — 严格基于检索到的文章内容

请用中文回答。
"""

_LONG_FORM_PROMPT_TEMPLATE_EN = """Based on real content from the knowledge graph, write a deep research article.

Topic: {question}

Requirements:
1. Structure: use markdown ## headings with 3-5 sections
2. Length: 800-1500 words
3. Citations: cite EVERY claim using markdown inline link format [short label](articles/{{hash}}.html)
   (hash is the 10-char article hash in the knowledge base).
   If a References section is included at the end, it **MUST** use markdown link format:
   - [Full article title](articles/{{hash}}.html)
   Do NOT use bare-text [1] [2] lists — those do not render as clickable links and the user cannot open them.
4. Entities: bold **key technologies / products / people**
5. Images: when source articles have relevant images, use the relative path format
   ![alt](/static/img/{{hash}}/{{n}}.jpg) (hash is the 10-char article hash, n is the image index).
   Do NOT use http://localhost:8765/ or any absolute URL — that port is not exposed to the
   browser and every such URL will 404.
6. Do not fabricate anything — strictly base on retrieved article content

Please answer in English.
"""


# ---------------------------------------------------------------------------
# kb-v2.2-4: QA prompt templates (FU-1 citation enforcement)
# ---------------------------------------------------------------------------
# Root cause: QA mode was sending the bare question (+ directive) to C1,
# which returned Chinese "(来源:Entity X)" citations that _SOURCE_HASH_PATTERN
# cannot extract → sources=[] → confidence='no_results' even with real content.
#
# Fix: wrap QA queries in a template that explicitly instructs C1 to emit
# /article/{hash}.html URL citations. Same doubled-brace {{hash}} trick as
# long_form: str.format() leaves the literal {hash} for the LLM to fill.

_QA_PROMPT_TEMPLATE_ZH = """请基于知识库中检索到的内容,简洁回答以下问题。

问题:{question}

要求:
1. 回答简洁,200-400 字
2. 每个关键结论用 markdown 行内链接格式 [短标签](articles/{{hash}}.html) 引用具体来源
   (hash 是文章在知识库中的 10 字符哈希)
   严禁裸文本 [1] [2] 引用 — 那不会渲染成可点击链接。
3. 如果源文章中有相关图片,用 ![alt](URL) 引用
4. 不要编造任何信息 — 严格基于检索到的文章内容

请用中文回答。
"""

_QA_PROMPT_TEMPLATE_EN = """Based on content retrieved from the knowledge base, concisely answer the following question.

Question: {question}

Requirements:
1. Keep the answer concise, 200-400 words
2. Cite key claims using markdown inline link format [short label](articles/{{hash}}.html)
   (hash is the 10-char article hash in the knowledge base).
   Do NOT use bare-text [1] [2] citations — those do not render as clickable links.
3. Include ![alt](URL) references if source articles have relevant images
4. Do not fabricate anything — strictly base on retrieved article content

Please answer in English.
"""


def _wrap_question_for_mode(question: str, lang: str, mode: str) -> str:
    """Return the query text passed to C1 depending on synthesis mode.

    mode='qa' (default, kb-v2.2-4): wraps question in QA prompt template that
    instructs C1 to emit /article/{hash}.html citations. Template carries the
    lang directive so kb_synthesize must NOT prepend a second one.

    mode='long_form': wraps question in deep-research template (unchanged from
    kb-v2.1-5). Template carries its own trailing lang directive.

    Other modes: returns question unchanged (caller prepends directive).
    """
    if mode == "long_form":
        template = (
            _LONG_FORM_PROMPT_TEMPLATE_ZH if lang == "zh"
            else _LONG_FORM_PROMPT_TEMPLATE_EN
        )
        return template.format(question=question)
    if mode == "qa":
        template = (
            _QA_PROMPT_TEMPLATE_ZH if lang == "zh"
            else _QA_PROMPT_TEMPLATE_EN
        )
        return template.format(question=question)
    return question


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
    # arx-2: All deployments use the Vertex AI embedding path
    # (lib.lightrag_embedding, 3072-dim) regardless of OMNIGRAPH_LLM_PROVIDER.
    # The LLM provider may differ (DeepSeek / Vertex Gemini / Databricks
    # serving), but the embedding side always needs a GCP service-account
    # JSON, so the SA file existence is the universal KG-mode gate.
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


def _rewrite_image_urls(markdown: str) -> str:
    """260519-s65 belt-and-suspenders: rewrite legacy `:8765` image URLs.

    `kg_synthesize.py` IMAGE_URL_DIRECTIVE (legacy Hermes path, off-limits)
    instructs the LLM to emit `http://localhost:8765/{hash}/{n}.jpg`. The KB
    serves images at `/static/img/{hash}/{n}.jpg`. Even with the long_form /
    qa prompt template explicitly forbidding `localhost:8765`, the LLM may
    still echo URLs verbatim from retrieved context. This pure-function
    rewrite is the safety net so the browser never 404s.

    Idempotent — applying twice yields the same string. Only the host:port
    prefix is rewritten; path components are preserved verbatim.
    """
    return _LEGACY_IMAGE_URL_PATTERN.sub("/static/img/", markdown)


def _dedupe_reference_sections(markdown: str) -> str:
    """Collapse duplicate ``## References`` sections, keeping the richest one.

    The LLM frequently emits two References sections (one disclaimer + one real
    link list, or two duplicate lists). qa.js keeps the highest-``<a>``-count
    section client-side; we do the same server-side by counting markdown links
    ``](`` in each References block and keeping only the densest, dropping the
    rest in place. Pure function; idempotent on already-clean input.
    """
    lines = markdown.split("\n")
    # Identify the line index of each References heading (markdown # heading or
    # bold-as-heading **References**) and the span until the next heading.
    heading_idxs: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        text = stripped.lstrip("#").strip().strip("*").strip()
        is_heading = stripped.startswith("#") or (
            stripped.startswith("**") and stripped.endswith("**")
        )
        if is_heading and text and any(text == kw or text.startswith(kw) for kw in _REFERENCE_KEYWORDS):
            heading_idxs.append(i)

    if len(heading_idxs) < 2:
        return markdown  # 0 or 1 References section — nothing to dedupe

    # Compute each section's span [start, end) and its link density.
    def _next_heading_after(start: int) -> int:
        for j in range(start + 1, len(lines)):
            s = lines[j].strip()
            if s.startswith("#") or (s.startswith("**") and s.endswith("**") and len(s) > 4):
                return j
        return len(lines)

    sections = []  # (start, end, link_count)
    for idx in heading_idxs:
        end = _next_heading_after(idx)
        link_count = sum(line.count("](") for line in lines[idx:end])
        sections.append((idx, end, link_count))

    # Keep the section with the most links (ties → first); drop the others.
    keep = max(sections, key=lambda s: s[2])
    drop_ranges = [(s[0], s[1]) for s in sections if s is not keep]
    drop_line_idxs: set[int] = set()
    for start, end in drop_ranges:
        drop_line_idxs.update(range(start, end))

    kept_lines = [ln for i, ln in enumerate(lines) if i not in drop_line_idxs]
    return "\n".join(kept_lines)


def _normalize_citations(markdown: str) -> str:
    """ISSUES #29: normalize LLM-emitted orphan citations to real markdown links.

    All 7 orphan shapes collapse to ``[<hash6>](articles/<hash>.html)`` so that
    non-browser consumers (Hermes skill, /api/synthesize JSON, CLI) get clean,
    clickable markdown without depending on qa.js. The link label is the 6-char
    short hash (qa.js uses the article title when available, but server-side we
    avoid a DB round-trip in this pure function — source titles already render
    as SOURCES chips downstream). Then duplicate References sections are deduped.

    Pure + idempotent: applying twice yields the same string (Pass 2's negative
    look-ahead ``(?!\\()`` skips already-linked ``[hash](...)``).
    """
    def _link(match: "re.Match[str]") -> str:
        h = match.group(1)
        return f"[{h[:6]}](articles/{h}.html)"

    markdown = _ORPHAN_ARTICLE_CITATION.sub(_link, markdown)
    markdown = _BARE_HASH_CITATION.sub(_link, markdown)
    markdown = _dedupe_reference_sections(markdown)
    return markdown


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


# #75 fallback-quality fix (2026-06-29): the fallback receives a full natural-
# language QUESTION ("什么是AI Agent" / "What is an AI agent?"), but
# search_index._sanitize_fts5_query wraps the whole string as a single FTS5
# phrase literal — so a full question rarely matches (the trigram phrase
# "什么是AI Agent" finds 0 rows even though "AI Agent" finds 3). The search BOX
# is fine (users type keywords); only the QA fallback feeds a full sentence.
# Fix: extract content keywords and OR-union per-keyword FTS hits. Zero external
# deps (no jieba), no embedding/network — works while Vertex egress is down (#75).
_QA_STOPWORDS_ZH: frozenset[str] = frozenset({
    "什么", "是", "的", "了", "吗", "呢", "如何", "怎么", "怎样", "为什么",
    "哪些", "哪个", "和", "与", "及", "在", "有", "会", "区别", "介绍",
    "请问", "可以", "需要", "关于", "一下", "这个", "那个",
})
_QA_STOPWORDS_EN: frozenset[str] = frozenset({
    "what", "is", "are", "the", "a", "an", "how", "why", "of", "to", "do",
    "does", "did", "in", "on", "for", "and", "or", "with", "about", "explain",
    "tell", "me", "can", "you", "please", "between", "vs",
})
# Token = a run of ASCII alphanumerics OR a run of CJK ideographs.
_QA_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]+")


def _extract_fts_keywords(question: str) -> list[str]:
    """Split a QA question into FTS-friendly content keywords (#75).

    Drops EN/ZH stopwords and strips leading ZH stop-prefixes from CJK runs
    (so "什么是AI" → keeps "AI"; a pure-stopword CJK run like "什么是" drops).
    Pure function. Returns [] only when the question is all stopwords/empty,
    in which case the caller falls back to the raw question.
    """
    out: list[str] = []
    for tok in _QA_TOKEN_RE.findall(question or ""):
        if tok.lower() in _QA_STOPWORDS_EN:
            continue
        if "一" <= tok[0] <= "鿿":
            for stop in sorted(_QA_STOPWORDS_ZH, key=len, reverse=True):
                while tok.startswith(stop) and len(tok) > len(stop):
                    tok = tok[len(stop):]
            if tok in _QA_STOPWORDS_ZH:
                continue
        if tok:
            out.append(tok)
    return out


def _fts5_keyword_union(question: str, limit: int) -> list:
    """Run FTS per extracted keyword and union the hits in first-seen order (#75).

    Falls back to a single whole-question query when no keywords survive
    extraction (preserves prior behavior for stopword-only inputs).
    """
    from kb.services.search_index import fts_query

    keywords = _extract_fts_keywords(question)
    if not keywords:
        return fts_query(question, lang=None, limit=limit)
    seen: set[str] = set()
    union: list = []
    for kw in keywords:
        for row in fts_query(kw, lang=None, limit=limit):
            if row[0] in seen:
                continue
            seen.add(row[0])
            union.append(row)
            if len(union) >= limit:
                return union
    return union


def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
    """QA-05: FTS5 top-3 fallback when LightRAG synthesis fails or times out.

    NEVER raises (worst case: status='done' with confidence='no_results').
    See kb-3-UI-SPEC §3.1 fts5_fallback state for the UI consumer of confidence.

    kb-v2.1-4: result is now ``SynthesizeResult.asdict()`` rather than a
    bespoke dict; sources are full ArticleSource objects (hash+title+lang)
    instead of plain hash strings, so qa.js renders the same chip surface
    as the KG happy path. Entities stay [] on fallback (qa.js skips entity
    rendering when fallback_used per kb-3 UI-SPEC §3.1 D-9).

    #75 (2026-06-29): query by extracted keywords (OR-union) instead of the raw
    full question, so a natural-language question reliably matches the trigram
    index even when the upstream KG/embedding path is down.
    """
    try:
        rows = _fts5_keyword_union(question, limit=3)
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


async def kb_synthesize(
    question: str,
    lang: str,
    job_id: str,
    mode: str = "qa",
    rag: LightRAG | None = None,
    lightrag_lock: asyncio.Lock | None = None,
    rerank_disabled: bool = False,
) -> None:
    """Background-task entry. Prepends lang directive, calls C1, updates job_store.

    Args:
        question: the user's question (unprefixed)
        lang: 'zh' | 'en' (other accepted but no directive applied — defensive)
        job_id: pre-allocated job id (caller invoked job_store.new_job(kind='synthesize'))
        mode: 'qa' (default — short Q&A answer; backward-compat) | 'long_form'
            (kb-v2.1-5 — wraps question in deep-research template before C1).
            Both modes return the identical SynthesizeResult schema; the UI
            8-state matrix renders both with no branching.

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

    # kb-v2.2-4 + kb-v2.1-5: both qa and long_form use prompt templates that
    # carry their own lang directive (enforces /article/{hash}.html citations).
    # Unrecognized modes fall back to the bare directive+question pattern.
    if mode in ("long_form", "qa"):
        query_text = _wrap_question_for_mode(question, lang, mode)
    else:
        directive = lang_directive_for(lang)
        query_text = f"{directive}{question}"

    # W4 wiki context injection (llm-wiki-integration phase).
    # Per Decision 4: read-only — synthesize NEVER writes back to kb/wiki/.
    wiki_context = await resolve_wiki_context(question)
    query_text = wiki_context + query_text
    # 260524-tk5: monotonic clock for C1 wall-time observability.
    t0 = time.monotonic()
    _log.info(
        "c1_before_aquery: job_id=%s mode=%s prompt_chars=%d",
        job_id, mode, len(query_text),
    )
    try:
        # QA-04: bound C1 wall-time. asyncio.wait_for raises TimeoutError on
        # exceedance; the inner coroutine is cancelled.
        # 260517-fyb: capture the LLM markdown from the await return value.
        # Pre-fix this discarded the return and read a stale BASE_DIR file
        # written only by the kg_synthesize CLI main(), causing 3 different
        # POST /api/synthesize requests on Aliyun (2026-05-17) to return the
        # same byte-identical markdown from a 2026-05-08 rsync'd file.
        effective_mode = "mix" if not rerank_disabled else "hybrid"
        response = await asyncio.wait_for(
            synthesize_response(
                query_text,
                mode=effective_mode,
                rag=rag,
                lightrag_lock=lightrag_lock,
            ),
            timeout=KB_SYNTHESIZE_TIMEOUT,
        )
        _log.info(
            "c1_after_aquery: job_id=%s wall_s=%.2f response_chars=%d",
            job_id, time.monotonic() - t0,
            len(response) if isinstance(response, str) else 0,
        )
    except asyncio.TimeoutError:
        _log.warning(
            "c1_timeout: job_id=%s wall_s=%.2f",
            job_id, time.monotonic() - t0,
        )
        _fts5_fallback(question, lang, job_id, reason="C1 timeout")
        return
    except Exception as e:  # noqa: BLE001 — QA-05: NEVER 500; route to fallback
        _fts5_fallback(question, lang, job_id, reason=f"{type(e).__name__}: {e}")
        return

    # kb-v2.1-4 happy path: structured resolution from real DB joins.
    # 260517-fyb: markdown comes from the synthesize_response return value
    # (LLM response str). Defensive isinstance() handles the rare case
    # where the 3-attempt retry exhausted without raising — return None.
    markdown = response if isinstance(response, str) else ""
    # 260519-s65: rewrite legacy `:8765` image URLs to kb-served `/static/img/`
    # before any downstream consumer (source resolution, job_store, qa.js)
    # sees the markdown. See _rewrite_image_urls docstring.
    markdown = _rewrite_image_urls(markdown)
    # ISSUES #29: server-side citation normalization so non-browser consumers
    # (Hermes skill, /api/synthesize JSON, CLI) get clean clickable links and
    # deduped References without relying on the client-side qa.js sweep. Runs
    # BEFORE source resolution so _extract_source_hashes sees the normalized
    # articles/<hash>.html refs. qa.js stays in place (defense-in-depth + it
    # handles cached pre-fix responses).
    markdown = _normalize_citations(markdown)
    # #75 (2026-06-29): C1 can return an EMPTY string WITHOUT raising — when the
    # embedding backend is down (e.g. cross-border Vertex egress dead), LightRAG
    # catches its own internal error ("Query failed: 'list' object has no
    # attribute 'get'") and yields no text. That bypassed both the timeout and
    # except branches, landing here with markdown="" → a dead-end no_results.
    # Route empty-KG to the keyword-FTS fallback so QA still answers from the
    # corpus instead of returning nothing.
    if not markdown.strip():
        _fts5_fallback(question, lang, job_id, reason="C1 returned empty (KG/embedding unavailable)")
        return
    sources = _resolve_sources_from_markdown(markdown)
    entities = _resolve_entities_for_sources([s.hash for s in sources])
    result = SynthesizeResult(
        markdown=markdown,
        confidence="kg",
        fallback_used=False,
        sources=sources,
        entities=entities,
    )
    job_store.update_job(
        job_id,
        status="done",
        result=result.asdict(),
        fallback_used=False,
        confidence="kg",
    )
