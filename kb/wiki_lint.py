"""Wiki lint guards for the LLM-wiki W3 hook (CONTEXT.md Decision 5; LLM-based contradiction deferred to v2)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Iterable

import frontmatter

# Legacy single-type citation: ^[article:<hex>]
LEGACY_CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")
# New GFM-footnote citation: [^N] (numbered, references frontmatter sources[].id)
FOOTNOTE_CITATION_RE = re.compile(r"\[\^(\d+)\]")
# Combined alias for back-compat with callers that imported CITATION_RE
CITATION_RE = LEGACY_CITATION_RE
BACKLINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
CAP_WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

JSONL_LOG_PATH = Path(
    ".planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl"
)


def lint_citation_integrity(page_path: Path, known_article_hashes: Iterable[str]) -> list[str]:
    """Validate citations against SCHEMA §6 §1.

    Two formats accepted:
    - Legacy `^[article:<10-char-hex>]` — hash MUST be in known_article_hashes
    - New `[^N]` — N MUST be the `id` of a frontmatter sources[] entry; for
      type=article entries, ref MUST be in known_article_hashes; type=web/builtin
      ref is not validated against the corpus.

    Returns a list of failure strings (empty list = pass).
    """
    post = frontmatter.load(str(page_path))
    text = post.content
    known = set(known_article_hashes)
    failures: list[str] = []

    # Legacy form: every hash must resolve in corpus
    for m in LEGACY_CITATION_RE.finditer(text):
        if m.group(1) not in known:
            failures.append(m.group(0))

    # New form: build sources[] index from frontmatter, validate each [^N]
    sources_list = post.metadata.get("sources") or []
    source_by_id: dict[str, dict] = {}
    for s in sources_list:
        if isinstance(s, dict) and "id" in s:
            source_by_id[str(s["id"])] = s

    for m in FOOTNOTE_CITATION_RE.finditer(text):
        sid = m.group(1)
        src = source_by_id.get(sid)
        if src is None:
            failures.append(f"[^{sid}]: id not in frontmatter sources[]")
            continue
        stype = (src.get("type") or "").lower()
        if stype == "article":
            ref = str(src.get("ref") or "")
            if ref and known and ref not in known:
                failures.append(f"[^{sid}]: type=article ref={ref!r} not in corpus")
        elif stype in ("web", "builtin"):
            # web ref is a URL (not validated against corpus); builtin has no ref.
            continue
        else:
            failures.append(f"[^{sid}]: unknown source type {stype!r}")

    return failures


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]


def lint_contradicts_existing(suggestion_text: str, existing_page_path: Path) -> list[str]:
    existing_text = Path(existing_page_path).read_text(encoding="utf-8")
    failures: list[str] = []
    sug_sents = _sentences(suggestion_text)
    ex_sents = _sentences(existing_text)
    for sug in sug_sents:
        sug_years = set(YEAR_RE.findall(sug))
        if not sug_years:
            continue
        sug_caps = set(CAP_WORD_RE.findall(sug))
        for ex in ex_sents:
            ex_years = set(YEAR_RE.findall(ex))
            if not ex_years or ex_years == sug_years:
                continue
            shared = sug_caps & set(CAP_WORD_RE.findall(ex))
            if len(shared) >= 2:
                failures.append(
                    f"contradiction: existing={ex_years} suggestion={sug_years} shared={sorted(shared)}"
                )
                break
    return failures


def lint_backlink_validity(suggestion_text: str, wiki_root_path: Path) -> list[str]:
    root = Path(wiki_root_path)
    failures: list[str] = []
    for m in BACKLINK_RE.finditer(suggestion_text):
        slug = m.group(1)
        if not (root / "entities" / f"{slug}.md").exists():
            failures.append(slug)
    return failures


def lint_staleness(page_path: Path, max_days: int = 180, today: date | None = None) -> list[str]:
    post = frontmatter.load(str(page_path))
    raw = post.metadata.get("last_updated")
    if raw is None:
        return [f"stale: last_updated missing in {page_path}"]
    if isinstance(raw, date):
        last = raw
    else:
        last = datetime.strptime(str(raw), "%Y-%m-%d").date()
    ref = today or date.today()
    age = (ref - last).days
    if age > max_days:
        return [f"stale: last_updated={last.isoformat()}, age={age}d"]
    return []


def log_lint_failure(failure_dict: dict) -> None:
    JSONL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": datetime.now(UTC).isoformat(), **failure_dict}, ensure_ascii=False)
    with open(JSONL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
