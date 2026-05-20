"""Wiki lint guards for the LLM-wiki W3 hook (CONTEXT.md Decision 5; LLM-based contradiction deferred to v2)."""
from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable

import frontmatter

CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")
BACKLINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
CAP_WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

JSONL_LOG_PATH = Path(
    ".planning/phases/llm-wiki-integration/wiki-lint-failures.jsonl"
)


def lint_citation_integrity(page_path: Path, known_article_hashes: Iterable[str]) -> list[str]:
    text = Path(page_path).read_text(encoding="utf-8")
    known = set(known_article_hashes)
    failures: list[str] = []
    for m in CITATION_RE.finditer(text):
        if m.group(1) not in known:
            failures.append(m.group(0))
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
