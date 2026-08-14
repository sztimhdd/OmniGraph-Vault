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

from kb.wiki_articles import (
    build_chunk_article_map,
    load_article_index,
    processed_ingestions,
    resolve_article,
)
from kb.wiki_compiler.adapters.w3 import (
    build_w3_pack_from_records,
    engine_ready_patch,
    engine_wiki_root,
    propose_w3_patch,
)
from kb.wiki_update import DEFAULT_BUFFER_DIRS
from kb.wiki_compiler.engine import (
    WikiValidationError,
    _parse_frontmatter,
    _resolve_target,
    _split_frontmatter,
    apply_patch,
    update_suggestion_evolution,
)
from kb.wiki_compiler.models import (
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    page_digest,
    stable_patch_id,
)

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


def _fmt_iso(dt: datetime) -> str:
    """Format a datetime as UTC ISO-8601 with the ``Z`` suffix — the
    queue's stored-timestamp convention (``_parse_iso_dt`` round-trips
    it exactly)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _next_attempt(prior: dict | None) -> int:
    """Attempt counter for the transition being recorded: exactly one
    increment over the prior state (a fresh/missing evolution counts as
    attempt 1). Malformed prior counters fail closed to 1, never crash."""
    if isinstance(prior, dict):
        try:
            return int(prior.get("attempts") or 0) + 1
        except (TypeError, ValueError):
            return 1
    return 1


def _transition(
    path: Path,
    prior: dict | None,
    *,
    now: datetime,
    status: str,
    decision: str,
    reason: str,
    applied_patch_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Record a design §7 state transition for one suggestion.

    Builds the next evolution state (one attempt increment, timestamps
    from *now*, ``next_retry_at`` scheduled only for ``retry`` via
    :func:`retry_delay`) and persists it atomically — replacing ONLY
    ``payload['evolution']`` via the engine helper, never any other
    payload key. A persistence integrity failure (e.g. the file became
    unreadable between scan and write) degrades to a non-attempt
    integrity descriptor, never a queue crash.

    With ``dry_run`` the transition is only REPORTED (``would_<status>``
    outcome) — nothing is persisted (Task 5 dry-run contract).
    """
    outcome_status = f"would_{status}" if dry_run else status
    outcome: dict = {"status": outcome_status, "attempt": True, "reason": reason}
    if status == "applied":
        outcome["applied_patch_id"] = applied_patch_id
    if dry_run:
        return outcome
    attempts = _next_attempt(prior)
    state = default_evolution_state() if not isinstance(prior, dict) else dict(prior)
    state["status"] = status
    state["attempts"] = attempts
    state["next_retry_at"] = (
        _fmt_iso(now + retry_delay(attempts)) if status == "retry" else None
    )
    state["last_evaluated_at"] = _fmt_iso(now)
    state["last_decision"] = decision
    state["last_reason"] = reason
    if status == "applied":
        state["applied_patch_id"] = applied_patch_id
    try:
        update_suggestion_evolution(path, state)
    except WikiValidationError as exc:
        return {
            "status": "integrity",
            "attempt": False,
            "reason": f"cannot persist evolution state: {exc}",
        }
    return outcome


# ---------------------------------------------------------------------------
# Promoted patch builder (design §7 promote step)
# ---------------------------------------------------------------------------

def build_promoted_patch(
    *,
    patch: WikiPatch,
    current_page: str,
    sections: list[dict],
    hydrated_evidence: list[dict],
    now: datetime,
) -> WikiPatch:
    """Rebuild *patch* as a FRESH auto-apply candidate bound to the page
    currently on disk (design §7 promote step).

    The promoted operations are EXACTLY ``MERGE_SOURCES``, one
    ``UPSERT_SECTION`` per model section (in order), then
    ``SET_METADATA(last_updated=now.date())`` — never CREATE_PAGE,
    REPLACE_PAGE, or any delete/whole-page op. ``base_digest`` pins the
    current page text and the promoted ``evidence_pack_id`` embeds the
    current page digest, so the deterministic ``patch_id`` changes when
    the on-disk page drifts but stays stable across re-evaluations of
    the same page (``created_at`` is the only time-dependent field).
    Evidence is rebuilt from the hydrated dicts (real local titles),
    carrying provenance from the ORIGINAL evidence by ``evidence_id``
    match; every other identity field (target, schema, reason, compiler
    version) is carried from the original patch with ``policy_hint``
    promoted to ``auto_apply``.
    """
    digest = page_digest(current_page)
    promoted_pack_id = f"{patch.evidence_pack_id}:w5b:{digest[:16]}"
    operations = (
        PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),
        *(
            PatchOperation(
                op="UPSERT_SECTION", section=s["heading"], content=s["content"],
                metadata=None,
            )
            for s in sections
        ),
        PatchOperation(
            op="SET_METADATA", section=None, content=None,
            metadata={"last_updated": now.date().isoformat()},
        ),
    )
    original_by_id = {ev.evidence_id: ev for ev in patch.evidence}
    rebuilt_evidence = []
    for item in hydrated_evidence:
        original = original_by_id.get(item["evidence_id"])
        rebuilt_evidence.append(
            EvidenceRef(
                evidence_id=item["evidence_id"],
                type=item["type"],
                ref=item["ref"],
                title=item["title"],
                provenance=(
                    original.provenance if original is not None else "lightrag-corpus"
                ),
                metadata=(
                    item["metadata"] if isinstance(item.get("metadata"), dict) else {}
                ),
            )
        )
    return WikiPatch(
        patch_schema_version=patch.patch_schema_version,
        patch_id=stable_patch_id(
            target_slug=patch.target_slug,
            evidence_pack_id=promoted_pack_id,
            operations=operations,
        ),
        target_slug=patch.target_slug,
        target_path=patch.target_path,
        target_kind=patch.target_kind,
        base_digest=digest,
        trigger=f"{patch.trigger}:w5b",
        evidence_pack_id=promoted_pack_id,
        operations=operations,
        evidence=tuple(rebuilt_evidence),
        policy_hint="auto_apply",
        reason=patch.reason,
        created_at=_fmt_iso(now),
        compiler_version=patch.compiler_version,
    )


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
    error_book: Callable[..., Any] | None = None,
) -> dict:
    """Scan the suggestion queue and process eligible suggestions.

    Report::

        {
            "scanned": int,
            "eligible": [path, ...],   # due (up to limit in ``attempted``)
            "skipped": [path, ...],    # terminal or retry-before
            "attempted": [path, ...],  # eligible capped by ``limit``
            "outcomes": {path: dict},  # attempted suggestions only
        }

    Every attempted suggestion is hydrated and evaluated (Task 5 state
    transitions); ``dry_run`` reports ``would_<status>`` outcomes and
    never persists or applies anything (Task 5 S8 dry-run contract). An
    attempted suggestion without an index (or with unresolved evidence)
    short-circuits to a ``would_retry`` outcome BEFORE any evaluator
    call. ``--limit N`` caps eligible attempts, not scanned/skipped
    files.
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
    for path_str in attempted:
        outcomes[path_str] = _process_suggestion(
            path_str, wiki_root=wiki_root, now=now, index=index,
            complete=complete, error_book=error_book, dry_run=dry_run,
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
    error_book: Callable[..., Any] | None = None,
    dry_run: bool = False,
) -> dict:
    """Read the serialized ``patch`` from the suggestion payload, hydrate
    local article evidence, and evaluate.

    Hydration failures (missing/ambiguous local evidence) short-circuit to
    a retryable pre-evaluation outcome — the evaluator call is never made
    and nothing is persisted (Task 5 owns state transitions). A payload
    without a usable ``patch`` object is a non-attempt integrity failure,
    not a crash.

    Task 5 transitions: ``RETRY`` (and provider/parse failures) persist a
    retry state with backoff, ``REJECT`` is a TERMINAL ``rejected``
    transition (the engine is never reached, so the Error Book stays
    untouched), and ``APPLY`` rebuilds a FRESH promoted patch bound to the
    on-disk page and applies it through the engine with
    ``semantic_approved=True``. With ``dry_run`` the one evaluator call
    MAY happen but every transition is only REPORTED as ``would_<status>``
    — never persisted, never applied (Task 5 S8 dry-run contract).
    """
    path = Path(path_str)
    payload = _load_suggestion(path)
    # The prior evolution state (missing/legacy payloads have none — the
    # first transition then counts as attempt 1). A present-but-non-dict
    # evolution is never trusted as state; the persist layer refuses to
    # overwrite it (engine integrity failure), never silently clobbers it.
    prior = payload.get("evolution") if isinstance(payload.get("evolution"), dict) else None
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
        # An evidence condition requiring a scheduled retry (missing or
        # ambiguous local evidence) counts as one attempt: the retry
        # transition is persisted with the backoff schedule.
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=hydration["reason"], dry_run=dry_run,
        )
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
    # Missing is NOT unreadable: a target page that no longer exists on
    # disk makes the suggestion meaningless — a terminal ``superseded``
    # transition (one attempt, never re-evaluated). Present-but-corrupt
    # stays a retryable read failure below.
    if not page_path.exists():
        return _transition(
            path, prior, now=now, status="superseded", decision="SUPERSEDE",
            reason=(
                f"target page {patch.target_path} no longer exists; "
                "suggestion superseded"
            ),
            dry_run=dry_run,
        )
    try:
        current_page = page_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=f"cannot read current page {patch.target_path}: {exc}",
            dry_run=dry_run,
        )
    candidate_sections = [
        {"heading": op.section, "content": op.content}
        for op in patch.operations
        if op.op == "UPSERT_SECTION"
    ]
    evaluated = asyncio.run(evaluate_suggestion(
        current_page=current_page,
        evidence=hydration["evidence"],
        sections=candidate_sections,
        complete=complete,
    ))
    if evaluated["status"] != "evaluated":
        # Provider/import/parse failure: the single call was already made;
        # the retry transition is persisted with the backoff schedule.
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=evaluated["reason"], dry_run=dry_run,
        )
    if evaluated["decision"] == "RETRY":
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=evaluated.get("reason") or "semantic evaluator requested retry",
            dry_run=dry_run,
        )
    if evaluated["decision"] == "REJECT":
        # A semantic REJECT is TERMINAL: exactly one attempt, the model's
        # reason, and the engine is never reached — so the injected Error
        # Book recorder stays empty and the page is never touched. A later
        # scan skips the file forever (rejected is a terminal status).
        return _transition(
            path, prior, now=now, status="rejected", decision="REJECT",
            reason=evaluated.get("reason") or "semantic evaluator rejected the update",
            dry_run=dry_run,
        )
    # APPLY: promote the suggestion to a FRESH patch bound to the page
    # currently on disk (design §7 promote step) and apply it through the
    # engine with semantic approval. The promoted patch carries a new
    # deterministic patch_id (digest-pinned base, w5b pack id), so the
    # engine sees a candidate that exactly matches what the evaluator
    # approved.
    fresh = build_promoted_patch(
        patch=patch,
        current_page=current_page,
        sections=evaluated["sections"],
        hydrated_evidence=hydration["evidence"],
        now=now,
    )
    if dry_run:
        # Dry-run contract: report the would-be applied transition; the
        # engine is never reached and nothing is persisted.
        return _transition(
            path, prior, now=now, status="applied", decision="APPLY",
            reason=evaluated.get("reason") or "semantic evaluator approved the update",
            applied_patch_id=fresh.patch_id, dry_run=True,
        )
    result = apply_patch(
        fresh, wiki_dir, error_book=error_book, semantic_approved=True
    )
    if result["status"] == "applied":
        return _transition(
            path, prior, now=now, status="applied", decision="APPLY",
            reason=result.get("error") or "applied",
            applied_patch_id=fresh.patch_id,
        )
    if result["status"] == "conflict":
        # The page drifted between the worker's read and the engine's
        # optimistic-concurrency digest gate (design §7 apply order): a
        # retryable race, NEVER an overwrite of the concurrent writer's
        # content, and no Error Book entry (not a candidate-integrity
        # failure).
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=result.get("error") or "base digest mismatch",
        )
    if result["status"] == "rejected":
        # The engine rejected the candidate at its final candidate-
        # integrity gates (design §7 order 6-8) and ALREADY logged the
        # Error Book entry — the worker maps the rejection to a retry
        # transition with backoff, never an apply, and never writes a
        # second Error Book entry.
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=result.get("error") or "candidate rejected by compiler",
        )
    if result["status"] == "suggestion":
        # Policy re-check race (the target vanished or became ineligible
        # between the worker's read and the engine's classify): a
        # transient anomaly — retry with backoff, never applied.
        return _transition(
            path, prior, now=now, status="retry", decision="RETRY",
            reason=result.get("error") or "apply returned suggestion",
        )
    # Unknown apply status: keep the safe retry fallback — never the stale
    # ``evaluated`` pass-through.
    return _transition(
        path, prior, now=now, status="retry", decision="RETRY",
        reason=f"apply_patch returned unexpected status {result['status']!r}",
    )


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
# 6. Historical bootstrap discovery + exact coverage accounting (W5B Task 6)
# ---------------------------------------------------------------------------

class BootstrapAccountingError(ValueError):
    """Raised when final bootstrap accounting does not reconcile.

    Every eligible article key must end in exactly one terminal class
    (represented / no_wiki_entity / retry_unresolved); a mismatch is a
    process-integrity failure, never a silent drop.
    """


def _slugify_entity(name: str) -> str:
    """Canonical entity slug — byte-identical to the W3 adapter slugify."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def _load_entity_buffer(
    article_key: tuple[str, str], buffer_dirs: list[Path]
) -> list[str]:
    """Resolve canonical ``<ref>_entities.json`` entities (first dir wins).

    Returns slugified, deduped entity names for one article. Malformed
    buffers (bad JSON, non-dict document, missing/non-list ``raw_entities``,
    junk list items) fail safe: they resolve to no entities — never a crash,
    never a silent mapping, and the article stays for graph/fallback.
    """
    _source, ref = article_key
    for buf_dir in buffer_dirs:
        path = Path(buf_dir) / f"{ref}_entities.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        raw = data.get("raw_entities")
        if not isinstance(raw, list):
            continue
        names: list[str] = []
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                names.append(item["name"].strip())
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        slugs: list[str] = []
        seen: set[str] = set()
        for name in names:
            slug = _slugify_entity(name)
            if slug and slug not in seen:
                seen.add(slug)
                slugs.append(slug)
        return slugs
    return []


def _split_source_chunks(source_id: object) -> list[str]:
    """W1 ``source_id`` split semantics — ``re.split(r\"[<>|\\s]+\", ...)``,
    ``chunk-*`` tokens only."""
    if not isinstance(source_id, str):
        return []
    return [
        token.strip()
        for token in re.split(r"[<>|\s]+", source_id)
        if token.strip().startswith("chunk-")
    ]


def _load_graph_entity_map(
    lightrag_dir: Path,
    conn: sqlite3.Connection,
) -> dict[str, set[tuple[str, str]]]:
    """Map entity slug -> article keys via vdb files + chunk->article map.

    Scans EVERY row of ``vdb_entities.json`` / ``vdb_relationships.json``
    — no top-N cutoff. Entity rows attach their ``source_id`` chunks; each
    relationship row attaches its ``source_id`` chunks to BOTH ``src_id``
    and ``tgt_id`` entity names. Chunks resolve to source-aware articles
    through ``build_chunk_article_map`` (Task 1 helper). Eligibility is the
    caller's job: returned key sets may include non-eligible articles.
    Malformed/missing vdb files fail safe: no mapping, never a crash.
    """
    chunk_map = build_chunk_article_map(lightrag_dir, conn)
    if not chunk_map:
        return {}
    entity_chunks: dict[str, set[str]] = {}

    def _scan(path_name: str, extract_row: Callable[[dict], None]) -> None:
        path = Path(lightrag_dir) / path_name
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        rows = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return
        for row in rows:
            if isinstance(row, dict):
                extract_row(row)

    def _entity_row(row: dict) -> None:
        name = row.get("entity_name")
        if not (isinstance(name, str) and name.strip()):
            return
        chunks = _split_source_chunks(row.get("source_id"))
        if chunks:
            entity_chunks.setdefault(name.strip(), set()).update(chunks)

    def _relationship_row(row: dict) -> None:
        names: list[str] = []
        for key in ("src_id", "tgt_id"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
        chunks = _split_source_chunks(row.get("source_id"))
        if not names or not chunks:
            return
        for name in names:
            entity_chunks.setdefault(name, set()).update(chunks)

    _scan("vdb_entities.json", _entity_row)
    _scan("vdb_relationships.json", _relationship_row)

    result: dict[str, set[tuple[str, str]]] = {}
    for name, chunks in entity_chunks.items():
        slug = _slugify_entity(name)
        if not slug or slug in result:
            continue
        keys: set[tuple[str, str]] = set()
        for chunk_id in chunks:
            rec = chunk_map.get(chunk_id)
            if rec is not None:
                keys.add((rec["source"], rec["ref"]))
        if keys:
            result[slug] = keys
    return result


def _build_fallback_prompt(record: dict) -> str:
    """Local title + text only — never wiki answers, Tavily, or web content."""
    return (
        "From the local article below, extract up to 3 entity names that "
        "deserve their own Wiki entity page (people, projects, tools, "
        "companies, techniques).\n"
        'Return STRICT JSON only: {"entities": ["name1", "name2", "name3"]} '
        'or {"entities": []}.\n'
        f"Title: {record.get('title') or ''}\n"
        f"Text:\n{record.get('text') or ''}"
    )


def parse_fallback_entities(raw: str) -> list[str] | None:
    """Parse a strict ``{"entities": [...]}`` fallback payload.

    Returns slugified, deduped entity names, or ``None`` when the payload is
    structurally invalid (malformed JSON, non-dict, missing/non-list
    ``entities``). Strict contract: 0-3 names are valid; MORE than 3 names
    invalidates the payload (callers map ``None`` to ``retry_unresolved``) —
    the model contract is never silently truncated.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    ents = data.get("entities")
    if not isinstance(ents, list):
        return None
    names: list[str] = []
    for item in ents:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
    if len(names) > 3:
        return None
    slugs: list[str] = []
    seen: set[str] = set()
    for name in names:
        slug = _slugify_entity(name)
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def _check_accounting(
    eligible: int, represented: int, no_wiki_entity: int, retry_unresolved: int
) -> None:
    """Raise ``BootstrapAccountingError`` when the invariant does not hold."""
    total = represented + no_wiki_entity + retry_unresolved
    if total != eligible:
        raise BootstrapAccountingError(
            f"eligible {eligible} != represented {represented} + "
            f"no_wiki_entity {no_wiki_entity} + retry_unresolved {retry_unresolved}"
        )


def _seed_historical_job(slug: str, records: list[dict], wiki_root: Path) -> dict:
    """Seed one historical job through the shared W5A/W3 compiler path.

    ``build_w3_pack_from_records`` (historical trigger) -> ``propose_w3_patch``
    -> the shared engine's ``apply_patch`` with the DEFAULT policy
    (``semantic_approved`` stays False): existing pages produce the
    deterministic structured suggestion JSON, missing pages auto-create.
    Returns the engine apply result dict (status/suggestion_path/error).

    Create-then-evolve: when the first apply lands a CREATE_PAGE, the fresh
    page is re-read and a second proposal + apply runs so the job ALSO
    produces the follow-up existing-page suggestion. A create without a
    follow-up suggestion is NOT a successful seeding (the returned result
    is whatever the follow-up apply reported).
    """
    pack = build_w3_pack_from_records(slug, records, wiki_root)
    patch = propose_w3_patch(pack, wiki_root=wiki_root)
    result = apply_patch(engine_ready_patch(patch), engine_wiki_root(wiki_root))
    if result["status"] == "applied":
        # Fresh page: evolve it. Rebuild the pack so the existing-page
        # path/digest are captured, then propose + apply again.
        pack = build_w3_pack_from_records(slug, records, wiki_root)
        patch = propose_w3_patch(pack, wiki_root=wiki_root)
        result = apply_patch(engine_ready_patch(patch), engine_wiki_root(wiki_root))
    return result


async def bootstrap_existing_discovery(
    conn: sqlite3.Connection,
    *,
    lightrag_dir: Path,
    buffer_dirs: list[Path] | None = None,
    complete: Callable[..., Any] | None = None,
    dry_run: bool = False,
    wiki_root: Path | None = None,
) -> dict:
    """Run historical bootstrap discovery and return the exact accounting report.

    Denominator: ``processed_ingestions`` (ok + LightRAG-processed), keyed by
    the canonical ``(source, ref)`` article key. Resolution pipeline: buffer
    mapping first, then LightRAG graph fallback (no top-N cutoff), then
    repeated-entity grouping (only >=2-key entities seed; articles in no
    seedable group stay uncovered), then the bootstrap-only fallback for
    every remaining uncovered article. Every eligible key ends in exactly one
    terminal class (represented / no_wiki_entity / retry_unresolved).
    ``dry_run`` resolves nothing (no provider calls, no writes) and reports
    ``would_need_llm_fallback``.

    Task 7 (``wiki_root`` given, non-dry-run): after discovery + fallback,
    every discovered job (``job_sources``: seedable groups AND fallback
    singletons) is seeded through the shared W5A/W3 compiler path
    (:func:`_seed_historical_job`) and the per-job engine result is reported
    under ``seeding``. ``wiki_root=None`` keeps the pure Task 6 discovery
    report (no seeding, no writes).
    """
    eligible_rows = processed_ingestions(conn, lightrag_dir)
    keys: list[tuple[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in eligible_rows:
        key = (row["source"], row["ref"])
        if key not in seen_keys:
            seen_keys.add(key)
            keys.append(key)
    index = load_article_index(conn)

    # Phase 1: entity-buffer mapping (canonical-first dir list). Buffer-mapped
    # articles skip the graph phase; their entities join the same group table
    # as graph entities, and a buffer-mapped singleton still reaches fallback
    # (S4 coverage decides seedability, not this phase).
    effective_buffer_dirs = (
        list(buffer_dirs) if buffer_dirs is not None else DEFAULT_BUFFER_DIRS
    )
    groups: dict[str, set[tuple[str, str]]] = {}
    buffer_mapped: set[tuple[str, str]] = set()
    for key in keys:
        slugs = _load_entity_buffer(key, effective_buffer_dirs)
        if slugs:
            buffer_mapped.add(key)
            for slug in slugs:
                groups.setdefault(slug, set()).add(key)

    uncovered = [key for key in keys if key not in buffer_mapped]

    # Phase 2: LightRAG graph fallback — no top-N cutoff, W1 ``source_id``
    # split semantics; runs only for eligible articles with no usable
    # buffer mapping (S3).
    graph_entity_map = _load_graph_entity_map(lightrag_dir, conn)
    graph_mapped: set[tuple[str, str]] = set()
    uncovered_set = set(uncovered)
    for slug, key_set in graph_entity_map.items():
        mapped = key_set & uncovered_set
        if mapped:
            graph_mapped.update(mapped)
            groups.setdefault(slug, set()).update(mapped)

    articles: dict[str, str] = {
        f"{source}/{ref}": "uncovered" for (source, ref) in keys
    }
    # Phase 3: repeated-entity grouping (S4) — an entity seen in >=2
    # distinct eligible article keys becomes a seedable historical job;
    # article coverage comes from those groups, so articles with only
    # singleton local entities stay uncovered and reach the fallback
    # (mapped != represented).
    seedable_groups = {
        slug: key_set for slug, key_set in groups.items() if len(key_set) >= 2
    }
    seeded: set[str] = set(seedable_groups)
    # Task 7: every discovered job keeps its article-key association —
    # seedable groups here, fallback-selected singletons below — so the
    # seeding phase can resolve records and recompute coverage per job.
    job_sources: dict[str, set[tuple[str, str]]] = {
        slug: set(key_set) for slug, key_set in seedable_groups.items()
    }
    represented_keys: set[tuple[str, str]] = set()
    for key_set in seedable_groups.values():
        represented_keys.update(key_set)
    for source, ref in represented_keys:
        articles[f"{source}/{ref}"] = "represented"
    uncovered = [key for key in keys if key not in represented_keys]
    no_wiki_entity = 0
    retry_unresolved = 0
    if not dry_run:
        for source, ref in uncovered:
            record = index.get((source, ref)) or {
                "source": source, "ref": ref, "title": ref, "text": "",
            }
            prompt = _build_fallback_prompt(record)
            try:
                if complete is None:
                    # lazy provider import — the only network seam
                    from lib.llm_deepseek import deepseek_model_complete
                    fn = deepseek_model_complete
                else:
                    fn = complete
                raw = await fn(prompt)
            except Exception as exc:
                retry_unresolved += 1
                articles[f"{source}/{ref}"] = "retry_unresolved"
                continue
            slugs = parse_fallback_entities(raw)
            if slugs is None:
                retry_unresolved += 1
                articles[f"{source}/{ref}"] = "retry_unresolved"
            elif not slugs:
                no_wiki_entity += 1
                articles[f"{source}/{ref}"] = "no_wiki_entity"
            else:
                articles[f"{source}/{ref}"] = "represented"
                seeded.update(slugs)
                for slug in slugs:
                    job_sources.setdefault(slug, set()).add((source, ref))

    report = {
        "eligible_processed_ingestions": len(keys),
        "mapped_via_entity_buffer": len(buffer_mapped),
        "mapped_via_lightrag_graph": len(graph_mapped),
        "unmapped_needing_llm_fallback": len(uncovered),
        "seeded_entity_jobs": sorted(seeded),
        "job_sources": {
            slug: sorted(assoc) for slug, assoc in sorted(job_sources.items())
        },
        "no_wiki_entity": no_wiki_entity,
        "retry_unresolved": retry_unresolved,
        "articles": articles,
    }
    if not dry_run and wiki_root is not None:
        # Task 7 seeding phase: one compiler round-trip per job. Failures
        # are contained per job (plain result dict, never an exception out
        # of the discovery run); coverage recompute follows the persistence
        # attempt so only actually-seeded jobs represent their articles.
        seeding: dict[str, dict] = {}
        for slug in sorted(job_sources):
            # NOTE: this local MUST NOT be named ``keys`` — it would shadow
            # the outer eligible-keys list the recompute + accounting use.
            job_keys = sorted(job_sources[slug])
            missing = [k for k in job_keys if index.get(k) is None]
            if missing:
                seeding[slug] = {
                    "status": "failed",
                    "patch_id": None,
                    "error": f"unresolved article record(s): {missing}",
                    "suggestion_path": None,
                    "warnings": [],
                }
                continue
            records = [index[k] for k in job_keys]
            try:
                seeding[slug] = _seed_historical_job(slug, records, wiki_root)
            except Exception as exc:  # noqa: BLE001 - fail closed per job
                seeding[slug] = {
                    "status": "failed",
                    "patch_id": None,
                    "error": str(exc),
                    "suggestion_path": None,
                    "warnings": [],
                }
        report["seeding"] = seeding
        # S5: coverage recompute AFTER the persistence attempt. A job counts
        # as seeded only when its final engine result is a persisted
        # structured suggestion; an article is represented iff >=1 of its
        # associated jobs seeded (all failed -> retry_unresolved).
        # ``no_wiki_entity`` stays terminal only for fallback {"entities":[]}
        # (no job exists for those articles). The accounting invariant below
        # therefore reflects the POST-persistence state.
        successful_jobs = {
            slug for slug, res in seeding.items()
            if res.get("status") == "suggestion"
        }
        represented_keys: set[tuple[str, str]] = set()
        for slug in successful_jobs:
            represented_keys.update(job_sources[slug])
        for source, ref in keys:
            label = f"{source}/{ref}"
            if (source, ref) in represented_keys:
                articles[label] = "represented"
            elif articles.get(label) != "no_wiki_entity":
                articles[label] = "retry_unresolved"
        no_wiki_entity = sum(
            1 for v in articles.values() if v == "no_wiki_entity"
        )
        retry_unresolved = sum(
            1 for v in articles.values() if v == "retry_unresolved"
        )
        report["no_wiki_entity"] = no_wiki_entity
        report["retry_unresolved"] = retry_unresolved
    if dry_run:
        report["would_need_llm_fallback"] = len(uncovered)
    else:
        represented = sum(1 for v in articles.values() if v == "represented")
        _check_accounting(len(keys), represented, no_wiki_entity, retry_unresolved)
    return report


# ---------------------------------------------------------------------------
# 4.6 CLI shell
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the Task 4 evolution worker slice.

    - ``--dry-run`` scans + classifies the suggestion queue only: prints
      the JSON scan report, never opens the article DB, never calls a
      provider, writes nothing.
    - ``--bootstrap-existing`` runs historical bootstrap discovery
      (Task 6): denominator, buffer mapping, LightRAG graph mapping,
      >=2-entity grouping, then the bootstrap-only fallback for every
      uncovered article. Normal exit codes: 0 = exact accounting and
      retry_unresolved == 0; 2 = retry_unresolved > 0; 1 = integrity/
      runtime failure or accounting mismatch. With ``--dry-run`` only
      denominator/buffer/graph/uncovered run — no fallback calls, no
      writes — reporting ``would_need_llm_fallback`` (0 completed /
      1 failure). The DB is opened READ-ONLY and never created. Normal
      (non-dry-run) bootstrap threads ``--wiki-root`` into the Task 7
      seeding phase (create-then-evolve + structured suggestions).
    - Normal worker mode fails closed when ``--db-path`` is missing/not a
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
            "(W5B Task 4 slice), or run historical bootstrap discovery "
            "(--bootstrap-existing)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "evaluate and report would_* outcomes; never writes pages, "
            "suggestions, or evolution state"
        ),
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
        help=(
            "run historical bootstrap discovery (with --dry-run: mapping "
            "only — no fallback calls, no writes)"
        ),
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
    parser.add_argument(
        "--lightrag-dir",
        type=Path,
        default=None,
        help=(
            "LightRAG storage dir for doc-status + entity discovery "
            "(default: <wiki-root>/.dev-runtime/lightrag_storage)"
        ),
    )
    args = parser.parse_args(argv)

    wiki_root = args.wiki_root
    db_path = (
        args.db_path
        if args.db_path is not None
        else wiki_root / "data" / "kol_scan.db"
    )

    if args.bootstrap_existing:
        # Task 6: historical bootstrap discovery — a mode of this script.
        # The DB is opened READ-ONLY and never created; the JSON report goes
        # to stdout. Normal exit codes: 0 = exact accounting and
        # retry_unresolved == 0; 2 = retry_unresolved > 0 (retryable/
        # incomplete coverage); 1 = integrity/runtime failure or accounting
        # mismatch. With --dry-run only denominator/buffer/graph/uncovered
        # run — no fallback calls, no writes — reporting
        # would_need_llm_fallback (0 completed / 1 failure).
        lightrag_dir = (
            args.lightrag_dir
            if args.lightrag_dir is not None
            else wiki_root / ".dev-runtime" / "lightrag_storage"
        )
        if not db_path.is_file():
            print(f"database not found: {db_path}", file=sys.stderr)
            return 1
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            report = asyncio.run(
                bootstrap_existing_discovery(
                    conn,
                    lightrag_dir=lightrag_dir,
                    dry_run=args.dry_run,
                    wiki_root=wiki_root,
                )
            )
        except BootstrapAccountingError as exc:
            print(f"bootstrap accounting mismatch: {exc}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.dry_run:
            return 0
        return 2 if report["retry_unresolved"] > 0 else 0

    if args.dry_run:
        # S8: dry-run MAY evaluate — an existing DB is opened READ-ONLY
        # and used for hydration (so outcomes reflect real would_*
        # decisions); a missing DB keeps scan-only classification (every
        # eligible suggestion reports a hydration-missing would_retry) and
        # is NEVER created.
        index = None
        if db_path.is_file():
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                index = load_article_index(conn)
            finally:
                conn.close()
        report = run_worker(
            wiki_root, dry_run=True, limit=args.limit, index=index,
        )
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
