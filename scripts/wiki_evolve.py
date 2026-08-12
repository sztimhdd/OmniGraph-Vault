"""W5B Task 4: normal evolution worker — queue scan, source-aware
hydration, strict one-call semantic evaluator, CLI plumbing.

Design §7: the suggestion JSON remains the queue. This script scans
``kb/wiki/_suggestions/*.json`` deterministically, hydrates article
evidence from the local source-aware article index (never the network),
evaluates due suggestions with exactly one DeepSeek call each, and reports
outcomes — it does NOT persist state transitions or write any file
(Task 5 wires APPLY/RETRY/REJECT persistence; Task 6 owns
``--bootstrap-existing`` discovery).

No framework: plain functions, one script, injected ``now``/index/evaluator
seams for tests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Import bootstrap
# ---------------------------------------------------------------------------
# The script is executed directly (``python scripts/wiki_evolve.py``) from
# an arbitrary cwd in the CLI tests, where the repo root is not on
# ``sys.path``. Pin THIS script's fixed repo root (``parents[1]`` of the
# script's own resolved path) onto the path so the ``kb.*`` imports below
# always resolve. Import bootstrap only — never user path resolution.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from kb.wiki_articles import load_article_index, resolve_article
from kb.wiki_compiler.adapters.w3 import engine_wiki_root
from kb.wiki_compiler.engine import _parse_frontmatter, _resolve_target, _split_frontmatter
from kb.wiki_compiler.models import WikiPatch

#: Fixed character caps for hydrated evidence — the ONLY caps. No
#: token-budget framework.
MAX_ARTICLE_CHARS = 12_000
MAX_TOTAL_EVIDENCE_CHARS = 48_000

#: Terminal evolution statuses (design §7): never re-evaluated.
TERMINAL_STATUSES = frozenset({"applied", "rejected", "superseded"})

#: The only accepted semantic decisions.
VALID_DECISIONS = frozenset({"APPLY", "RETRY", "REJECT"})

_FENCE = re.compile(r"^```[A-Za-z]*\s*$")


class SemanticParseError(ValueError):
    """Raised when a raw semantic result is structurally unacceptable."""


def default_evolution_state() -> dict:
    """Return a fresh copy of the design §7 evolution state (pending/0/null)."""
    return {
        "status": "pending",
        "attempts": 0,
        "next_retry_at": None,
        "last_evaluated_at": None,
        "last_decision": None,
        "last_reason": None,
        "applied_patch_id": None,
    }


def _parse_iso_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (``Z`` suffix normalized to UTC); naive
    timestamps are assumed UTC so comparisons stay deterministic."""
    s = str(value).strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def is_due(state: dict | None, now: datetime) -> bool:
    """Decide whether a suggestion's evolution state is due for evaluation.

    - missing/None evolution behaves as pending (due immediately) — the
      worker reads it only and never lazily writes it (Task 4);
    - ``pending`` due immediately;
    - ``retry`` due at/after ``next_retry_at``, skipped before (a retry
      state without a timestamp is treated as due rather than stuck);
    - terminal ``applied``/``rejected``/``superseded`` skipped forever.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    status = state.get("status") if isinstance(state, dict) else "pending"
    if status in TERMINAL_STATUSES:
        return False
    if status == "retry":
        next_retry_at = state.get("next_retry_at") if isinstance(state, dict) else None
        if next_retry_at is None:
            return True
        return _parse_iso_dt(next_retry_at) <= now
    return True


def retry_delay(attempts: int) -> timedelta:
    """Backoff after *attempts* failed evaluations: 1 -> +1 day,
    2 -> +3 days, >=3 -> +7 days."""
    if attempts >= 3:
        return timedelta(days=7)
    if attempts == 2:
        return timedelta(days=3)
    return timedelta(days=1)


# ---------------------------------------------------------------------------
# Queue scan
# ---------------------------------------------------------------------------

def scan_suggestion_paths(wiki_root: Path) -> list[Path]:
    """Return ``kb/wiki/_suggestions/*.json`` paths sorted deterministically
    by filename (the suggestion file itself is the worker identity)."""
    sugg_dir = Path(wiki_root) / "kb" / "wiki" / "_suggestions"
    if not sugg_dir.is_dir():
        return []
    return sorted(sugg_dir.glob("*.json"))


def _load_suggestion(path: Path) -> dict:
    """Read a suggestion payload (full serialized WikiPatch + evolution)."""
    return json.loads(path.read_text(encoding="utf-8"))


def _suggestion_eligible(payload: dict, now: datetime) -> bool:
    """Eligible = due: missing evolution behaves pending; terminal/not-yet
    retry states are skipped. Read-only — never lazily writes state."""
    return is_due(payload.get("evolution"), now)


def run_worker(
    wiki_root: Path,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    index: dict | None = None,
    complete: Callable[..., Any] | None = None,
) -> dict:
    """Scan the suggestion queue and process eligible suggestions.

    Report::

        {
            "scanned": int,
            "eligible": [path, ...],   # due (up to limit in ``attempted``)
            "skipped": [path, ...],    # terminal or retry-before
            "attempted": [path, ...],  # eligible capped by ``limit``
            "outcomes": {path: dict},  # normal mode only
        }

    Task 4 semantics: dry-run scans + classifies ONLY (no DB, no hydration,
    no evaluator call, no writes). Normal mode additionally hydrates and
    evaluates each attempted suggestion but still never writes anything —
    state transitions are Task 5. ``--limit N`` caps eligible attempts, not
    scanned/skipped files.
    """
    now = now if now is not None else datetime.now(UTC)
    paths = scan_suggestion_paths(wiki_root)

    eligible: list[str] = []
    skipped: list[str] = []
    outcomes: dict[str, dict] = {}
    for path in paths:
        try:
            payload = _load_suggestion(path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            outcomes[str(path)] = {
                "status": "integrity",
                "attempt": False,
                "reason": f"malformed suggestion payload: {exc}",
            }
            continue
        if not isinstance(payload, dict):
            outcomes[str(path)] = {
                "status": "integrity",
                "attempt": False,
                "reason": "malformed suggestion payload: not a JSON object",
            }
            continue
        try:
            is_eligible = _suggestion_eligible(payload, now)
        except ValueError as exc:
            # A malformed due-state (e.g. unparseable retry timestamp)
            # is a non-attempt integrity descriptor, never a scan crash.
            outcomes[str(path)] = {
                "status": "integrity",
                "attempt": False,
                "reason": f"malformed suggestion payload: {exc}",
            }
            continue
        if is_eligible:
            eligible.append(str(path))
        else:
            skipped.append(str(path))

    attempted = eligible if limit is None else eligible[: max(limit, 0)]
    if not dry_run:
        for path_str in attempted:
            outcomes[path_str] = _process_suggestion(
                path_str, wiki_root=wiki_root, now=now, index=index, complete=complete
            )

    return {
        "scanned": len(paths),
        "eligible": eligible,
        "skipped": skipped,
        "attempted": attempted,
        "outcomes": outcomes,
    }


def _process_suggestion(
    path_str: str,
    *,
    wiki_root: Path,
    now: datetime,
    index: dict | None,
    complete: Callable[..., Any] | None,
) -> dict:
    """Read the serialized ``patch`` from the suggestion payload, hydrate
    local article evidence, and evaluate.

    Hydration failures (missing/ambiguous local evidence) short-circuit to
    a retryable pre-evaluation outcome — the evaluator call is never made
    and nothing is persisted (Task 5 owns state transitions). A payload
    without a usable ``patch`` object is a non-attempt integrity failure,
    not a crash.
    """
    payload = _load_suggestion(Path(path_str))
    patch_dict = payload.get("patch")
    if not isinstance(patch_dict, dict):
        return {
            "status": "integrity",
            "attempt": False,
            "reason": "malformed suggestion payload: missing patch object",
        }
    try:
        patch = WikiPatch.from_dict(patch_dict)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        # An incomplete/malformed serialized patch object (missing fields,
        # or non-dict items inside operations/evidence tripping the model's
        # post-init invariants) is a non-attempt integrity failure, never a
        # crash: no hydration, no evaluator.
        return {
            "status": "integrity",
            "attempt": False,
            "reason": f"malformed suggestion payload: invalid patch object: {exc}",
        }
    hydration = hydrate_evidence(patch.evidence, index or {})
    if hydration["status"] != "ready":
        return {"status": "retry", "reason": hydration["reason"]}
    # Resolve ``patch.target_path`` against the ACTUAL wiki root (the
    # directory holding ``entities/``), not the repo root: W3-era
    # suggestions carry wiki-relative paths (``entities/<slug>.md``) and
    # the assembler carries repo-relative ones (``kb/wiki/...``); the
    # engine resolver handles both once the root is normalized. The
    # RESOLVED final path must stay inside that wiki root — an outside
    # target path (e.g. ``unrelated.md`` resolving at the repo root, or
    # a symlink escape) is a non-attempt integrity failure, never read.
    wiki_dir = engine_wiki_root(wiki_root)
    page_path = _resolve_target(wiki_dir, patch.target_path).resolve()
    if not page_path.is_relative_to(Path(wiki_dir).resolve()):
        return {
            "status": "integrity",
            "attempt": False,
            "reason": (
                "malformed suggestion payload: target path "
                f"{patch.target_path!r} resolves outside the wiki root"
            ),
        }
    try:
        current_page = page_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "status": "retry",
            "reason": f"cannot read current page {patch.target_path}: {exc}",
        }
    candidate_sections = [
        {"heading": op.section, "content": op.content}
        for op in patch.operations
        if op.op == "UPSERT_SECTION"
    ]
    return asyncio.run(evaluate_suggestion(
        current_page=current_page,
        evidence=hydration["evidence"],
        sections=candidate_sections,
        complete=complete,
    ))


# ---------------------------------------------------------------------------
# Strict semantic result parser
# ---------------------------------------------------------------------------

_FRONTMATTER_KEYS = (
    "title:",
    "created:",
    "last_updated:",
    "sources:",
    "confidence_level:",
)


def _reject_page_material(content: str) -> None:
    """Reject section content that attempts H1/full-page/frontmatter or
    source-YAML material — the model returns H2 section bodies only."""
    first = True
    for ln in content.splitlines():
        stripped = ln.strip()
        if first and stripped:
            if stripped.startswith(_FRONTMATTER_KEYS):
                raise SemanticParseError(
                    "frontmatter/source-YAML is not allowed in section content"
                )
            first = False
        if stripped.startswith("# "):
            raise SemanticParseError(
                "H1 headings are not allowed; H2 section bodies only"
            )
        if stripped == "---":
            raise SemanticParseError("frontmatter is not allowed in section content")
        if re.match(r"^sources:", stripped):
            raise SemanticParseError("source-YAML is not allowed in section content")


def parse_semantic_result(raw: str) -> dict:
    """Strictly parse the evaluator's semantic result.

    Accepts exactly one JSON object whose ``decision`` is in
    {APPLY, RETRY, REJECT} (one outer ``` code fence may be stripped).
    APPLY additionally requires a non-empty ``sections`` list whose entries
    each carry a non-empty string heading and content. Anything else —
    unparseable text, non-object JSON, missing/unknown decision, malformed
    sections, H1/full-page/frontmatter/source-YAML material, duplicate
    headings, numeric confidence/score — raises :class:`SemanticParseError`
    (the evaluator boundary maps that to a retryable outcome).
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip exactly ONE outer code fence (opening + closing lines).
        lines = text.splitlines()
        if lines and _FENCE.match(lines[0]) and lines[-1].strip() == "```":
            lines = lines[1:-1]
            text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SemanticParseError("semantic result must be a JSON object")
    decision = data.get("decision")
    if decision not in VALID_DECISIONS:
        raise SemanticParseError(f"unknown decision {decision!r}")
    for key in ("confidence", "score"):
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            raise SemanticParseError(
                f"numeric {key} is not an accepted policy channel"
            )
    reason = data.get("reason")
    sections = data.get("sections")
    if decision == "APPLY":
        if not isinstance(sections, list) or not sections:
            raise SemanticParseError("APPLY requires a non-empty sections list")
        seen_headings: set[str] = set()
        for sec in sections:
            if not isinstance(sec, dict):
                raise SemanticParseError("section must be an object")
            heading = sec.get("heading")
            content = sec.get("content")
            if not isinstance(heading, str) or not heading.strip():
                raise SemanticParseError("section missing non-empty heading")
            if not isinstance(content, str) or not content.strip():
                raise SemanticParseError("section missing non-empty content")
            if heading.strip().startswith("#"):
                raise SemanticParseError(
                    "H1 headings are not allowed; H2 section bodies only"
                )
            norm = heading.strip().lower()
            if norm in seen_headings:
                raise SemanticParseError(
                    f"duplicate section heading {heading.strip()!r}"
                )
            seen_headings.add(norm)
            _reject_page_material(content)
        sections = [
            {"heading": sec["heading"].strip(), "content": sec["content"]}
            for sec in sections
        ]
    return {"decision": decision, "reason": reason, "sections": sections}


# ---------------------------------------------------------------------------
# Citation mapping + prompt (4.4)
# ---------------------------------------------------------------------------

def _evidence_field(ev, name: str):
    """Read a field from either an :class:`EvidenceRef` or a hydrated
    evidence dict (the worker passes hydrated dicts to the prompt path)."""
    if isinstance(ev, dict):
        return ev.get(name)
    return getattr(ev, name, None)


def build_citation_map(page_text: str, evidence: tuple | list) -> list[dict]:
    """Predict the exact citation token for every evidence item, mirroring
    the W5A compiler's ``_merge_sources`` append rule so ids cannot drift.

    Canonical pages (block-style ``sources[]``): evidence already present
    keeps its existing ``id``; new evidence receives ``len(sources)+i`` for
    its 1-based position *i* among the additions, in evidence order — and,
    exactly like ``_merge_sources``' ``(type, ref)`` dedup, an evidence item
    whose key was ALREADY retained earlier in this same pass is not a
    distinct source and gets NO entry (the compiler appends only the first
    occurrence). Legacy article-only pages map every article ref to its
    ``^[article:<ref>]`` token. Returns one ``{"type", "ref", "title",
    "token", "index"}`` entry per retained evidence item (legacy pages:
    article evidence only); ``index`` is the item's position in *evidence*
    so prompt preparation can pair entries back to their payloads.
    """
    fm_body = _split_frontmatter(page_text)
    if fm_body is None:
        return []
    fm, _ = fm_body
    sources = fm.get("sources")
    if not isinstance(sources, list):
        return []
    legacy_style = bool(sources) and isinstance(sources[0], str)

    existing: list[dict] = []
    for s in sources:
        if isinstance(s, dict):
            key = (s.get("type"), s.get("ref")) if s.get("ref") else (s.get("type"), s.get("title"))
            existing.append({"key": key, "id": s.get("id")})
        elif isinstance(s, str):
            key = tuple(s.split(":", 1)) if ":" in s else (s,)
            existing.append({"key": key, "id": None})

    mapping: list[dict] = []
    next_id = len(sources) + 1
    # Compiler-compatible ``(type, ref)`` projection: a key already retained
    # in THIS pass (an earlier evidence item with the same key — same
    # article arriving under two sources) is skipped, mirroring
    # ``_merge_sources`` which appends exactly one source for it. No
    # tokenizer/source framework — plain set projection.
    added: set = set()
    for i, ev in enumerate(evidence):
        ev_type = _evidence_field(ev, "type")
        ev_ref = _evidence_field(ev, "ref")
        ev_title = _evidence_field(ev, "title")
        key = (ev_type, ev_ref) if ev_ref is not None else (ev_type, ev_title)
        if legacy_style:
            if ev_type == "article":
                mapping.append({
                    "type": ev_type,
                    "ref": ev_ref,
                    "title": ev_title,
                    "token": f"^[article:{ev_ref}]",
                    "index": i,
                })
            continue
        present = next((e for e in existing if e["key"] == key), None)
        if present is not None:
            if present["id"] is not None:
                token = f"[^{present['id']}]"
            else:
                token = f"^[article:{ev_ref}]"
            mapping.append({
                "type": ev_type,
                "ref": ev_ref,
                "title": ev_title,
                "token": token,
                "index": i,
            })
        elif key in added:
            continue  # not retained: same (type, ref) already added above
        else:
            mapping.append({
                "type": ev_type,
                "ref": ev_ref,
                "title": ev_title,
                "token": f"[^{next_id}]",
                "index": i,
            })
            added.add(key)
            next_id += 1
    return mapping


SYSTEM_PROMPT = (
    "You are the semantic evaluator for a wiki entity page update. "
    "You decide whether a proposed H2 section change should be applied, "
    "retried later, or rejected, based ONLY on the supplied evidence and "
    "the current page. Never invent facts, never output frontmatter, "
    "source-YAML, or a full page — H2 section bodies only."
)


def build_prompt(*, current_page: str, evidence: list, sections: list[dict]) -> str:
    """Build the single evaluator prompt.

    Presents (1) the current page read fresh from the wiki (the only
    authority for what the page currently says — never the payload's
    ``suggested_content``), (2) the hydrated local evidence with its exact
    citation tokens from :func:`build_citation_map` (compiler parity), and
    (3) the proposed candidate sections. Asks exactly the four approved
    questions; the model answers with one JSON object.
    """
    mapping = build_citation_map(current_page, evidence)
    by_index = {m["index"]: m for m in mapping}
    # Source-aware citation selection: canonical pages render ONLY the
    # evidence records the compiler's ``(type, ref)`` dedup will retain as
    # distinct sources — an item whose key was already retained earlier in
    # this evidence pass (same article under two sources) must not reach
    # the prompt with a citation id the compiler never assigns (Task 2
    # non-alias contract). Legacy pages keep their exact existing
    # rendering: every evidence item, article items with their
    # ``^[article:<ref>]`` token, others with an empty one. A page with no
    # usable sources map also renders every item unchanged (empty token).
    legacy_style = any(m["token"].startswith("^[article:") for m in mapping)
    lines = [
        "You are evaluating a proposed wiki entity page update.",
        "",
        "## Current page (authoritative, read fresh from the wiki)",
        current_page.strip(),
        "",
        "## Evidence (local articles)",
    ]
    n = 1
    for i, item in enumerate(evidence):
        entry = by_index.get(i)
        if entry is None:
            if not legacy_style and by_index:
                continue  # not retained by the compiler's dedup
            entry = {"ref": item.get("ref"), "token": ""}
        lines.append(f"{n}. [{item['type']}] {item['title']}")
        n += 1
        ref = entry.get("ref")
        if ref is not None:
            token = entry.get("token", "")
            lines.append(f"   ref: {ref} — exact citation token: {token}")
        text = (item.get("text") or "").strip()
        if text:
            lines.append(f"   {text}")
    lines.extend([
        "",
        "## Proposed change (candidate sections)",
    ])
    for sec in sections:
        lines.append(f"- {sec['heading']}:")
        lines.append(f"  {sec['content']}")
    lines.extend([
        "",
        "## Questions — answer only these four",
        "1. Is the proposed change supported by the supplied evidence?",
        "2. Does it avoid unjustified deletion of still-correct important information?",
        "3. Is it materially more accurate, current, or clear than the current page?",
        "4. Does it avoid obvious contradiction with the current page or evidence?",
        "",
        "## Output format",
        'Return exactly one JSON object: {"decision": "APPLY" | "RETRY" | "REJECT", '
        '"reason": "...", "sections": [{"heading": "...", "content": "..."}]}',
        "APPLY requires non-empty sections with H2 headings only (no '# ' prefix, "
        "no frontmatter, no 'sources:' YAML, no full page). Use citation tokens "
        "exactly as given above.",
    ])
    return "\n".join(lines)


async def evaluate_suggestion(
    *,
    current_page: str,
    evidence: list,
    sections: list[dict],
    complete: Callable[..., Any] | None = None,
) -> dict:
    """Evaluate one suggestion with EXACTLY ONE provider call.

    Builds the prompt and awaits ``complete`` exactly once with
    ``system_prompt=SYSTEM_PROMPT``, then strictly parses the result.
    No retries inside the same attempt, no second judge, no fallback.
    Without an injected ``complete`` the real provider is imported lazily
    at call time (the network-capable import stays function-local); any
    provider/import/parse failure is a retryable outcome for a later
    scheduled run — never a crash and never a second call.
    """
    prompt = build_prompt(
        current_page=current_page, evidence=evidence, sections=sections
    )
    try:
        if complete is None:
            from lib.llm_deepseek import deepseek_model_complete  # lazy provider import
            complete = deepseek_model_complete
        raw = await complete(prompt, system_prompt=SYSTEM_PROMPT)
    except Exception as exc:
        return {"status": "retry", "reason": f"evaluator call failed: {exc}"}
    try:
        parsed = parse_semantic_result(raw)
    except SemanticParseError as exc:
        return {"status": "retry", "reason": f"malformed evaluator response: {exc}"}
    return {"status": "evaluated", **parsed}


# ---------------------------------------------------------------------------
# Source-aware hydration (local-only, never the network)
# ---------------------------------------------------------------------------

def hydrate_evidence(
    evidence: tuple | list,
    index: dict,
) -> dict:
    """Hydrate suggestion evidence from the local source-aware article index.

    Article evidence resolves through ``resolve_article(index, ref,
    source=metadata.get("source"))`` — strict per-source lookup; a missing
    ``metadata.source`` (old W3 evidence) resolves source-less only when
    unambiguous. Missing local evidence and ambiguous refs produce an
    explicit retryable pre-evaluation outcome — never a guess. The real
    local title/body replaces the old hash placeholder; the canonical ref
    and the evidence ``metadata`` are preserved unchanged. Local-only:
    no web/Tavily/provider call exists on this path.

    Returns ``{"status": "ready", "evidence": [...]}`` or
    ``{"status": "retry", "reason": str}`` (Task 4 must NOT persist this
    retry state — Task 5 owns persistence).
    """
    hydrated: list[dict] = []
    for ev in evidence:
        # Untrusted input: a serialized EvidenceRef may carry a non-dict
        # ``metadata`` (e.g. a bare string). Normalize ONCE at the shared
        # hydration boundary so both branches and the source lookup below
        # see a dict — malformed metadata fails closed (source-less
        # lookup -> retryable missing/ambiguous outcome), never a crash.
        metadata = ev.metadata if isinstance(ev.metadata, dict) else {}
        if ev.type != "article":
            # Non-article evidence has no local body; keep its own label.
            hydrated.append({
                "evidence_id": ev.evidence_id,
                "type": ev.type,
                "ref": ev.ref,
                "title": ev.title,
                "text": "",
                "metadata": dict(metadata),
            })
            continue
        source = None
        if isinstance(metadata.get("source"), str) and metadata["source"].strip():
            source = metadata["source"].strip()
        try:
            rec = resolve_article(index, ev.ref, source=source)
        except ValueError as exc:
            return {"status": "retry", "reason": f"ambiguous article ref {ev.ref}: {exc}"}
        if rec is None:
            return {
                "status": "retry",
                "reason": f"missing local evidence for article ref {ev.ref}",
            }
        hydrated.append({
            "evidence_id": ev.evidence_id,
            "type": "article",
            "ref": rec["ref"],
            "title": rec["title"],
            "text": rec["text"][:MAX_ARTICLE_CHARS],
            "metadata": dict(metadata),
        })
    # Total evidence budget: greedy in evidence order — earlier evidence
    # keeps its full capped text, later items are trimmed to the remaining
    # budget. These two fixed caps are the only caps (no token-budget
    # framework).
    budget = MAX_TOTAL_EVIDENCE_CHARS
    for item in hydrated:
        if budget <= 0:
            item["text"] = ""
            continue
        item["text"] = item["text"][:budget]
        budget -= len(item["text"])
    return {"status": "ready", "evidence": hydrated}


# ---------------------------------------------------------------------------
# 4.6 CLI shell
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the Task 4 evolution worker slice.

    - ``--dry-run`` scans + classifies the suggestion queue only: prints
      the JSON scan report, never opens the article DB, never calls a
      provider, writes nothing.
    - ``--bootstrap-existing`` PARSES but is explicitly deferred: exits
      nonzero with a stable neutral stderr message before any DB
      open, scan, provider call, or write (Task 6 owns historical
      bootstrap discovery) — never fake success.
    - Normal mode fails closed when ``--db-path`` is missing/not a
      regular file (``database not found: <path>`` on stderr, nonzero
      exit, the DB file is never created). With an existing DB it loads
      the article index through a read-only SQLite connection
      (``mode=ro``) and runs the worker with no injected evaluator:
      eligible, hydration-ready suggestions reach the real provider
      through :func:`evaluate_suggestion`'s lazy import (exactly one
      call per suggestion). Nothing is written — apply/state transitions
      are Task 5; Task 6 owns ``--bootstrap-existing`` discovery.
    """
    parser = argparse.ArgumentParser(
        prog="wiki_evolve.py",
        description=(
            "Scan the wiki suggestion queue and evaluate due suggestions "
            "(W5B Task 4 slice)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scan and classify only; never open the DB or call a provider",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap eligible attempts at N (terminal/skipped files never count)",
    )
    parser.add_argument(
        "--bootstrap-existing",
        action="store_true",
        help="reserved: historical suggestion bootstrap is Task 6 (not implemented)",
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="wiki repository root (default: this repository)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="article index SQLite database (default: <wiki-root>/data/kol_scan.db)",
    )
    args = parser.parse_args(argv)

    if args.bootstrap_existing:
        # Task 4 exposes the explicit deferred/unsupported behavior: the
        # flag PARSES and exits nonzero with a stable neutral message.
        # Task 6 owns historical bootstrap discovery — never fake success.
        print(
            "--bootstrap-existing is not implemented (Task 6 owns historical bootstrap)",
            file=sys.stderr,
        )
        return 2

    wiki_root = args.wiki_root
    db_path = (
        args.db_path
        if args.db_path is not None
        else wiki_root / "data" / "kol_scan.db"
    )

    if args.dry_run:
        report = run_worker(wiki_root, dry_run=True, limit=args.limit)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if not db_path.is_file():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        index = load_article_index(conn)
        report = run_worker(wiki_root, index=index, limit=args.limit)
    finally:
        conn.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
