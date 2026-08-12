"""kb.wiki_compiler.engine — Shared validation, policy, and atomic apply engine.

Task 3 of the W5A patch compiler: deterministic policy classification,
optimistic concurrency with per-page advisory locks, atomic page writes,
deterministic suggestion files, and Error Book integration for true
compiler-integrity failures only.

Contract
--------
* **validate_evidence()** — schema-level validation of an evidence pack.
  Returns a list of error strings (empty when valid). Raises
  :class:`WikiValidationError` only for structurally unusable input.

* **classify_patch()** — deterministic policy, no randomness, no wall
  clock. Decisions (W5A properties):
    - ``CREATE_PAGE`` on a page that does not exist -> ``auto_apply``
    - ``CREATE_PAGE`` on an existing page -> ``suggestion_only`` (never
      clobber an existing page)
    - ``UPSERT_SECTION`` on an existing page -> ``suggestion_only``
      (substantive body mutation is blocked, W5A property 5)
    - ``MERGE_SOURCES`` on a legacy page with web/builtin evidence ->
      ``suggestion_only`` (legacy provenance incompatibility: the old
      ``- article:<hex>`` format cannot represent web/builtin sources)
    - ``MERGE_SOURCES`` otherwise (canonical page, or article-only into
      legacy) -> ``auto_apply`` (frontmatter-only, body untouched)
    - ``SET_METADATA`` on non-critical fields (``last_updated``,
      ``confidence_level``) -> ``auto_apply``; any critical key -> ``suggestion_only``
    - any ``DELETE_PAGE`` operation -> ``rejected`` (W5A property 7)

* **apply_patch()** — applies a patch with per-page ``fcntl.flock``
  advisory locking and optimistic concurrency:

    1. validate evidence (failures -> Error Book + ``rejected``)
    2. classify policy
    3. ``suggestion_only`` -> write deterministic suggestion JSON under
       ``kb/wiki/_suggestions/<slug>-<patch-id>.json`` (atomic write);
       the page itself is never touched
    4. ``auto_apply`` -> acquire ``kb/wiki/.locks/<slug>.md.lock``,
       re-read the page, compare its digest against ``patch.base_digest``
       (mismatch or unexpected existence/missing -> ``conflict``, never
       overwrite), render the candidate, run FINAL CANDIDATE VALIDATION
       (design §7 order 6-8), ``os.replace`` atomically, release the lock

Final candidate validation gates (design §7 order 6-8; GAP 1)
--------------------------------------------------------------
Run on the assembled candidate BEFORE any authoritative write, reusing
the existing ``kb.wiki_lint`` primitives — never a second lint
implementation. Candidate is staged to a throwaway temp file under the
target kind dir so the lint functions see it exactly as it will be
written (full page: frontmatter + body).

* BLOCKING (status ``rejected``, NO write, Error Book with patch
  provenance via ``lint_name=wiki_compiler:candidate_integrity``):
    - candidate frontmatter parse failure (order 6) — malformed YAML
      cannot be written (mirrors wiki_health ``check_yaml_validity``
      ERROR);
    - citation integrity failures (order 7) from
      ``kb.wiki_lint.lint_citation_integrity`` — ``[^N]`` id not in
      frontmatter ``sources[]``, unknown source type, or article ref
      not in the known corpus (mirrors wiki_health ``check_citations``
      ERROR for the structural cases; §10 "candidate health/lint ERROR
      -> reject").
* WARN (recorded on the result dict under ``warnings``, NEVER blocking):
    - broken wikilinks (order 8, "under existing policy"). The repo's
      existing policy is WARN-only: scripts/wiki_health.py
      ``check_wikilinks`` appends broken backlinks to ``findings["warns"]``
      (exit code 2 = WARNs only; ~185 pre-existing warnings). §10
      "candidate WARN only -> conservative policy; no silent promotion"
      therefore means apply proceeds with the warning recorded.
* Contradiction/staleness checks (order 9-10) are intentionally not run
  on auto-apply candidates: the candidate is fresh by construction
  (``last_updated`` is being written now), and LLM-semantic contradiction
  review is deferred to W5B (``kb.wiki_lint`` module docstring).

The known article corpus for citation integrity = article refs from
``patch.evidence`` plus article refs already present in the current page
frontmatter sources (update candidates retain those sources; evidence
alone only covers the new additions).

* **Error Book** — the existing ``kb.error_book.log_lint_failure`` API is
  used, with the plan's payload keys (``lint_name`` prefix
  ``wiki_compiler:``, ``patch_id``, ``trigger``, ``compiler_version``).
  Only true integrity failures are logged: evidence corruption, candidate
  parse/render errors, and disk I/O failures. Normal ``suggestion_only``
  outcomes and digest conflicts are **never** logged.

Lock layout: ``kb/wiki/.locks/<slug>.md.lock`` (POSIX advisory via
``fcntl.flock``). Lock files are runtime artifacts; ``kb/wiki/.locks/`` is
Git-ignored.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import frontmatter

from kb.wiki_compiler.assembler import TYPE_PROVENANCE
from kb.wiki_compiler.models import (
    ARTICLE_REF_PATTERN,
    VALID_EVIDENCE_TYPES,
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    page_digest,
)
from kb.wiki_lint import lint_backlink_validity, lint_citation_integrity

#: Metadata keys considered non-critical (safe to auto-apply). Design §5.3:
#: ``SET_METADATA`` may change only compiler-approved fields such as
#: ``last_updated`` and ``confidence_level``; critical keys (``created``,
#: ``title``, ``sources``, ...) must always be preserved.
NON_CRITICAL_METADATA_KEYS = frozenset({"last_updated", "confidence_level"})

#: Design §7 fresh suggestion-evolution state. Copied per write (never
#: shared/mutated): status=pending, attempts=0, all lifecycle fields null.
_FRESH_EVOLUTION_STATE: Dict[str, Any] = {
    "status": "pending",
    "attempts": 0,
    "next_retry_at": None,
    "last_evaluated_at": None,
    "last_decision": None,
    "last_reason": None,
    "applied_patch_id": None,
}

#: Operations allowed to ride the W5B semantic-approval promotion: the
#: non-destructive update ops only. A raw/unknown op mixed into an
#: UPSERT_SECTION patch must never be auto-applied (or silently dropped
#: by the renderer) — it stays suggestion_only.
_W5B_PROMOTABLE_OPS = frozenset(
    {"UPSERT_SECTION", "MERGE_SOURCES", "SET_METADATA"}
)

#: Default H2 section for UPSERT_SECTION when the op omits one.
DEFAULT_SECTION = "Definition / Overview"

#: Legacy inline citation ``^[article:<hex>]`` (old format, still lint-valid).
_LEGACY_INLINE_CITATION = re.compile(r"\^\[(?:article|web|builtin):")

#: Legacy frontmatter source entry ``- article:<hex>``.
_LEGACY_SOURCE_LINE = re.compile(r"^-\s*(?:article|web|builtin):", re.MULTILINE)

#: Frontmatter scalar line ``key: value`` at column 0.
_FM_SCALAR_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")

#: Canonical block-style source continuation line (indented ``key: value``).
_FM_BLOCK_KEY = re.compile(r"^(\s+)([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")

#: Any H1/H2 heading (section boundary for UPSERT_SECTION).
_HEADING = re.compile(r"^#{1,2}\s")

_LOCK_TIMEOUT_S = 5.0


class WikiValidationError(Exception):
    """Raised when evidence fails schema-level validation."""


# ---------------------------------------------------------------------------
# Evidence validation
# ---------------------------------------------------------------------------

def validate_evidence(evidence: Tuple[EvidenceRef, ...]) -> List[str]:
    """Validate all EvidenceRefs in a pack. Returns list of errors.

    Structural misuse (non-tuple input, non-EvidenceRef members) raises
    :class:`WikiValidationError`; per-member violations are returned as
    human-readable error strings (empty list when the pack is valid).
    """
    if not isinstance(evidence, (tuple, list)):
        raise WikiValidationError(
            f"evidence must be a tuple of EvidenceRef, got {type(evidence).__name__}"
        )
    errors: List[str] = []
    for i, ev in enumerate(evidence):
        if not isinstance(ev, EvidenceRef):
            errors.append(f"evidence[{i}] is not an EvidenceRef: {type(ev).__name__}")
            continue
        if ev.type not in VALID_EVIDENCE_TYPES:
            errors.append(
                f"evidence[{i}] type {ev.type!r} not in "
                f"{sorted(VALID_EVIDENCE_TYPES)}"
            )
        if ev.type == "article":
            if not isinstance(ev.ref, str) or not re.match(ARTICLE_REF_PATTERN, ev.ref):
                errors.append(
                    f"evidence[{i}] article ref must match [a-f0-9]{{10}}, "
                    f"got {ev.ref!r}"
                )
        elif ev.type == "web":
            if not isinstance(ev.ref, str) or not ev.ref.strip():
                errors.append(
                    f"evidence[{i}] web ref must be a non-empty URL string, "
                    f"got {ev.ref!r}"
                )
        if not ev.evidence_id or not str(ev.evidence_id).strip():
            errors.append(f"evidence[{i}] evidence_id must be non-empty")
        if not ev.title or not str(ev.title).strip():
            errors.append(f"evidence[{i}] title must be non-empty")
    return errors


# ---------------------------------------------------------------------------
# Deterministic policy
# ---------------------------------------------------------------------------

def classify_patch(
    patch: WikiPatch,
    wiki_root: Path,
    page_registry: Optional[dict] = None,
    *,
    semantic_approved: bool = False,
) -> str:
    """Deterministic policy: ``auto_apply``, ``suggestion_only``, or ``rejected``.

    ``page_registry`` optionally maps ``target_slug`` to
    ``{"exists": bool, "legacy": bool}`` (or a bare bool for ``exists``);
    when a slug is absent, existence/legacy are read from ``wiki_root``.

    ``semantic_approved`` (W5B seam) is keyword-only and defaults to
    ``False``: with the flag, an existing-page patch containing
    ``UPSERT_SECTION`` may be promoted to ``auto_apply`` — but only after
    every pre-existing gate (DELETE_PAGE, critical metadata, missing page,
    legacy provenance) has been passed. Default behavior is byte-for-byte
    W5A-compatible.
    """
    ops = patch.operations or ()

    # W5A property 7: deletes are never accepted by the compiler.
    if any(getattr(o, "op", None) == "DELETE_PAGE" for o in ops):
        return "rejected"

    # Design §5.3: SET_METADATA may change only compiler-approved fields
    # (NON_CRITICAL_METADATA_KEYS). Any critical key — created, title,
    # sources, ... — forces suggestion_only, even as a sibling of
    # MERGE_SOURCES (which previously auto-applied without inspecting
    # SET_METADATA keys and could rewrite `created`).
    metadata_keys: set = set()
    for o in ops:
        if getattr(o, "op", None) == "SET_METADATA":
            md = getattr(o, "metadata", None)
            if isinstance(md, dict):
                metadata_keys.update(md.keys())
    if metadata_keys and not metadata_keys <= NON_CRITICAL_METADATA_KEYS:
        return "suggestion_only"

    exists, legacy = _page_state(patch, wiki_root, page_registry)

    if any(o.op == "CREATE_PAGE" for o in ops):
        # Fresh page -> safe to create. Existing page -> never clobber.
        return "auto_apply" if not exists else "suggestion_only"

    if any(o.op == "UPSERT_SECTION" for o in ops):
        # W5A property 5: substantive body mutation on existing pages is
        # blocked from auto-apply. W5B seam: semantic_approved=True may
        # promote an existing-page UPSERT_SECTION patch, but a missing
        # page stays suggestion_only (nothing to merge into), a legacy
        # page with web/builtin evidence stays suggestion_only (old
        # `- article:<hex>` provenance cannot represent those), and a
        # patch mixing in any operation outside the allowed non-destructive
        # update set stays suggestion_only (a raw/unknown op must never be
        # auto-applied or silently dropped by the renderer).
        if not semantic_approved:
            return "suggestion_only"
        if not exists:
            return "suggestion_only"
        if legacy and _has_non_article_evidence(patch.evidence):
            return "suggestion_only"
        if any(getattr(o, "op", None) not in _W5B_PROMOTABLE_OPS for o in ops):
            return "suggestion_only"
        return "auto_apply"

    if any(o.op == "MERGE_SOURCES" for o in ops):
        if not exists:
            return "suggestion_only"
        if legacy and _has_non_article_evidence(patch.evidence):
            # Old `- article:<hex>` provenance cannot represent web/builtin
            # sources; merging them would corrupt the page's citation model.
            return "suggestion_only"
        return "auto_apply"

    if ops and all(o.op == "SET_METADATA" for o in ops):
        if exists and metadata_keys and metadata_keys <= NON_CRITICAL_METADATA_KEYS:
            return "auto_apply"
        return "suggestion_only"

    # Unknown or mixed operation sets: never auto-apply.
    return "suggestion_only"


def _page_state(
    patch: WikiPatch,
    wiki_root: Path,
    page_registry: Optional[dict],
) -> Tuple[bool, bool]:
    """Return ``(exists, legacy)`` for the patch target."""
    if page_registry is not None and patch.target_slug in page_registry:
        info = page_registry[patch.target_slug]
        if isinstance(info, dict):
            return bool(info.get("exists")), bool(info.get("legacy"))
        return bool(info), False
    target = _resolve_target(wiki_root, patch.target_path)
    if not target.exists():
        return False, False
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return True, False
    return True, _is_legacy(text)


def _is_legacy(text: str) -> bool:
    """Legacy pages use old inline citations and/or ``- article:<hex>`` lists."""
    return bool(
        _LEGACY_SOURCE_LINE.search(text[:3000])
        or _LEGACY_INLINE_CITATION.search(text[:20000])
    )


def _has_non_article_evidence(evidence: Tuple[EvidenceRef, ...]) -> bool:
    return any(getattr(ev, "type", None) != "article" for ev in (evidence or ()))


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_patch(
    patch: WikiPatch,
    wiki_root: Path,
    wiki_update: Optional[Callable[[dict], None]] = None,
    error_book: Optional[Callable[[dict], None]] = None,
    *,
    semantic_approved: bool = False,
) -> dict:
    """Apply *patch* atomically with per-page locking and optimistic
    concurrency.

    Returns::

        {
            "status": "applied" | "conflict" | "suggestion" | "rejected",
            "patch_id": str,
            "error": str | None,
            "suggestion_path": str | None,   # set when status == "suggestion"
            "warnings": [str, ...],          # WARN-only findings (never block)
        }

    * ``applied`` — page written atomically under the page lock after the
      final candidate validation gates passed (design §7 order 6-8; see
      the module docstring for the BLOCKING vs WARN policy). WARN-only
      findings (broken wikilinks) are recorded in ``warnings`` and do not
      block the write.
    * ``conflict`` — the page changed since *patch* was assembled (digest
      mismatch, target vanished, or create-target already exists). The
      on-disk content is never overwritten. Not logged to the Error Book.
    * ``suggestion`` — policy said ``suggestion_only``; a deterministic
      suggestion JSON was written, the page is untouched. Candidate
      validation gates do not run on this path (the page is never
      written).
    * ``rejected`` — evidence or candidate failed integrity checks; the
      failure is logged to the Error Book and the page is never written.

    ``wiki_update``, when callable, is invoked with the result dict after a
    successful apply (post-commit, outside the lock); a hook failure is
    surfaced in ``result["error"]`` without rolling back the write.

    ``error_book`` defaults to ``kb.error_book.log_lint_failure``; pass a
    callable to intercept (tests) or a module exposing ``log_lint_failure``.

    ``semantic_approved`` (W5B seam, keyword-only, default ``False``) is
    passed through to :func:`classify_patch` only — every later step
    (digest check, lock, render, candidate validation, atomic write) is
    unchanged.
    """
    result: Dict[str, Any] = {
        "status": None,
        "patch_id": patch.patch_id,
        "error": None,
        "suggestion_path": None,
        "warnings": [],
    }

    # 0. Schema-level validation. True integrity failures go to Error Book.
    errors = validate_evidence(patch.evidence)
    if errors:
        _report_error_book(error_book, patch, wiki_root, errors)
        result["status"] = "rejected"
        result["error"] = "; ".join(errors)
        return result

    # 1. Deterministic policy. The W5B semantic-approval flag only feeds
    # the classifier; every later gate (digest, lock, render, candidate
    # lint, atomic write) is identical for flagged and unflagged patches.
    # The default path keeps the exact W5A call shape (no extra keyword),
    # so existing W5A-era classify_patch stand-ins stay compatible.
    if semantic_approved:
        policy = classify_patch(patch, wiki_root, semantic_approved=True)
    else:
        policy = classify_patch(patch, wiki_root)
    if policy == "rejected":
        result["status"] = "rejected"
        result["error"] = (
            "patch rejected by policy: DELETE_PAGE is not allowed (W5A property 7)"
        )
        return result

    if policy == "suggestion_only":
        try:
            result["suggestion_path"] = str(_write_suggestion(patch, wiki_root))
        except WikiValidationError as exc:
            _report_error_book(error_book, patch, wiki_root, [str(exc)])
            result["status"] = "rejected"
            result["error"] = str(exc)
            return result
        result["status"] = "suggestion"
        return result

    # 2. auto_apply: per-page lock, re-read, digest check, atomic write.
    wiki_dir = _wiki_dir(wiki_root)
    lock_path = wiki_dir / ".locks" / _lock_name(patch)
    fd = _acquire_lock(lock_path)
    try:
        target = _resolve_target(wiki_root, patch.target_path)
        current_text: Optional[str] = None
        if target.exists():
            try:
                current_text = target.read_text(encoding="utf-8")
            except OSError as exc:
                _report_error_book(error_book, patch, wiki_root,
                                   [f"cannot read target page: {exc}"])
                result["status"] = "rejected"
                result["error"] = f"cannot read target page: {exc}"
                return result

        # Optimistic concurrency: the base digest must match what is on disk.
        if patch.base_digest is None:
            if current_text is not None:
                result["status"] = "conflict"
                result["error"] = (
                    f"target page already exists ({patch.target_path}); "
                    "refusing to overwrite"
                )
                return result
        else:
            if current_text is None:
                result["status"] = "conflict"
                result["error"] = (
                    f"target page missing ({patch.target_path}); "
                    "base digest cannot match"
                )
                return result
            current_digest = page_digest(current_text)
            if current_digest != patch.base_digest:
                result["status"] = "conflict"
                result["error"] = (
                    "base digest mismatch: page changed since patch was "
                    f"assembled (expected {patch.base_digest[:12]}..., "
                    f"found {current_digest[:12]}...)"
                )
                return result

        # Render and write the candidate atomically under the lock.
        try:
            candidate = _render_candidate(patch, current_text)
        except WikiValidationError as exc:
            _report_error_book(error_book, patch, wiki_root, [str(exc)])
            result["status"] = "rejected"
            result["error"] = str(exc)
            return result

        # GAP 1 (design §7 order 6-8): FINAL CANDIDATE VALIDATION on the
        # assembled candidate BEFORE any authoritative write. Blocking
        # failures (frontmatter parse, citation integrity) reject with an
        # Error Book entry and NO write; WARN findings (broken wikilinks)
        # are recorded and never block.
        blocking, warnings = _validate_candidate(
            patch, candidate, wiki_root, current_text
        )
        if blocking:
            _report_error_book(
                error_book, patch, wiki_root, blocking,
                lint_name="wiki_compiler:candidate_integrity",
            )
            result["status"] = "rejected"
            result["error"] = "; ".join(blocking)
            return result
        result["warnings"] = warnings

        _atomic_write(target, candidate)
        result["status"] = "applied"
    finally:
        _release_lock(fd)

    # Post-commit hook (index/log refresh). Failures must not roll back.
    if wiki_update is not None and callable(wiki_update):
        try:
            wiki_update(result)
        except Exception as exc:  # noqa: BLE001 - hook is best-effort
            result["error"] = f"wiki_update hook failed: {exc}"
    return result


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------

def _lock_name(patch: WikiPatch) -> str:
    """Deterministic per-page lock file name: ``<slug>.md.lock``."""
    return f"{_safe_slug(patch.target_slug)}.md.lock"


def _safe_slug(slug: str) -> str:
    """Filesystem-safe slug (nested slugs keep their separators distinct)."""
    return slug.replace("/", "--").replace("\\", "--")


def _acquire_lock(lock_path: Path, timeout_s: float = 5.0) -> int:
    """Acquire an advisory file lock using ``fcntl.flock``.

    Returns the file descriptor on success. Raises :class:`TimeoutError`
    after *timeout_s* seconds. Must be released with :func:`_release_lock`.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            fd = None
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                os.close(fd)
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"could not acquire lock {lock_path} within {timeout_s}s"
            )
        time.sleep(0.05)


def _release_lock(fd: int) -> None:
    """Release advisory file lock."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _atomic_write(target_path: Path, content: str) -> None:
    """Write *content* atomically: write to a sibling temp file, then
    ``os.replace()``.

    The temp file name is unique per call (``tempfile.mkstemp``), so
    same-process threads writing the same target never collide on the
    temp path; last ``os.replace`` wins with complete content.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target_path.parent),
        prefix=f".{target_path.name}.",
        suffix=".tmp",
    )
    try:
        data = content.encode("utf-8") if isinstance(content, str) else content
        with os.fdopen(fd, "wb") as fh:
            fd = None  # ownership transferred to fh
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target_path)
    finally:
        if fd is not None:
            os.close(fd)
        # Never leave a temp file behind on failure.
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Suggestion files
# ---------------------------------------------------------------------------

def _carried_evolution(path: Path) -> Dict[str, Any]:
    """Return the existing suggestion file's ``evolution`` object EXACTLY,
    or a copy of the design §7 fresh state when no file exists yet — or
    when the existing file is a valid W5A-era payload (deterministic JSON
    WITHOUT the ``evolution`` key, which the W5A writer never emitted).

    Re-emitting the same deterministic patch must never reset durable
    evolution state (design §7: the suggestion JSON remains the queue);
    a W5A-era payload is valid and is lazily initialized to fresh §7 state.
    An existing file that is malformed JSON, a non-dict payload, or a
    payload whose ``evolution`` value is not a dict is a compiler-integrity
    failure: :class:`WikiValidationError` is raised and the file is never
    silently overwritten.
    """
    if not path.exists():
        return dict(_FRESH_EVOLUTION_STATE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WikiValidationError(
            f"malformed suggestion JSON at {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise WikiValidationError(
            f"malformed suggestion payload at {path}: "
            "payload must be a JSON object"
        )
    if "evolution" not in payload:
        # Valid W5A-era payload (pre-W5B writer): lazily initialize fresh
        # design §7 state rather than treating the file as corrupted.
        return dict(_FRESH_EVOLUTION_STATE)
    if not isinstance(payload["evolution"], dict):
        raise WikiValidationError(
            f"malformed suggestion payload at {path}: "
            "'evolution' object invalid"
        )
    return payload["evolution"]


def _write_suggestion(patch: WikiPatch, wiki_root: Path) -> Path:
    """Write a deterministic suggestion JSON (atomic), return its path.

    Filename ``<slug>-<patch-id>.json`` — no timestamps, so re-writing the
    same patch addresses the same path.
    """
    wiki_dir = _wiki_dir(wiki_root)
    sugg_dir = wiki_dir / "_suggestions"
    target = _resolve_target(wiki_root, patch.target_path)
    current_text: Optional[str] = None
    if target.exists():
        try:
            current_text = target.read_text(encoding="utf-8")
        except OSError:
            current_text = None
    path = sugg_dir / f"{_safe_slug(patch.target_slug)}-{patch.patch_id}.json"
    payload = {
        # Design §5.4: the suggestion file stores the FULL serialized
        # WikiPatch (re-deserializable via WikiPatch.from_dict) plus the
        # validation/policy outcome — not a reduced field subset.
        "patch": patch.to_dict(),
        "policy_hint": "suggestion_only",
        "reason": patch.reason,
        "suggested_content": _render_candidate(patch, current_text),
        # Design §7: durable evolution state. Fresh on first write; on a
        # re-emission of the same patch the existing deterministic file's
        # evolution object is carried forward EXACTLY (terminal/retry state
        # must never be reset by compiler reruns).
        "evolution": _carried_evolution(path),
        # Flat convenience mirrors (kept for existing readers/tests).
        "patch_id": patch.patch_id,
        "target_slug": patch.target_slug,
        "operations": [asdict(o) for o in patch.operations],
        "evidence": [asdict(ev) for ev in patch.evidence],
    }
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def update_suggestion_evolution(path: Path, evolution: dict) -> None:
    """Atomically replace ONLY ``payload['evolution']`` in an existing
    suggestion JSON file (design §7 worker transitions: retry/reject/apply).

    Every other payload key is preserved exactly. A valid W5A-era payload
    (no ``evolution`` key) simply gains the key — the file is never
    rejected or clobbered. A missing file, malformed JSON, non-dict payload,
    or an existing non-dict ``evolution`` value is a compiler-integrity
    failure (:class:`WikiValidationError`) — never created or overwritten.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WikiValidationError(
            f"cannot read suggestion JSON at {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise WikiValidationError(
            f"malformed suggestion payload at {path}: "
            "payload must be a JSON object"
        )
    if "evolution" in payload and not isinstance(payload["evolution"], dict):
        raise WikiValidationError(
            f"malformed suggestion payload at {path}: "
            "'evolution' object invalid"
        )
    payload["evolution"] = evolution
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Candidate rendering (frontmatter/body surgery, never wholesale rewrite)
# ---------------------------------------------------------------------------

def _render_candidate(patch: WikiPatch, current_text: Optional[str]) -> str:
    """Render the resulting page text for *patch*.

    ``CREATE_PAGE`` uses the operation's full canonical content. Update
    operations are applied as scoped surgery on the existing page:
    ``UPSERT_SECTION`` replaces exactly one named H2 section,
    ``MERGE_SOURCES`` appends deduplicated sources to frontmatter only,
    ``SET_METADATA`` rewrites allowlisted scalar frontmatter keys.
    """
    ops = patch.operations or ()
    if not ops:
        raise WikiValidationError("patch has no operations")

    if ops[0].op == "CREATE_PAGE":
        content = ops[0].content or ""
        if not content.strip():
            raise WikiValidationError("CREATE_PAGE operation has empty content")
        return content

    if current_text is None:
        raise WikiValidationError(
            "cannot render update operations without existing page content"
        )
    text = current_text
    for op in ops:
        if op.op == "UPSERT_SECTION":
            text = _upsert_section(text, op.section, op.content or "")
        elif op.op == "MERGE_SOURCES":
            text = _merge_sources(text, patch.evidence)
        elif op.op == "SET_METADATA":
            text = _set_metadata(text, op.metadata or {})
    return text


def _upsert_section(text: str, section: Optional[str], content: str) -> str:
    """Replace exactly one named H2 section (or append when absent)."""
    heading = f"## {section or DEFAULT_SECTION}"
    lines = text.split("\n")
    idx = None
    for i, ln in enumerate(lines):
        if ln.rstrip() == heading or ln.strip() == heading:
            idx = i
            break
    new_block = heading + "\n\n" + content.strip() + "\n"
    if idx is None:
        return text.rstrip("\n") + "\n\n" + new_block
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        if _HEADING.match(lines[j]):
            end = j
            break
    head = "\n".join(lines[:idx]).rstrip("\n")
    tail = "\n".join(lines[end:]).rstrip("\n")
    rebuilt = head + "\n\n" + new_block.rstrip("\n")
    if tail:
        rebuilt += "\n\n" + tail
    return rebuilt + "\n"


def _merge_sources(text: str, evidence: Tuple[EvidenceRef, ...]) -> str:
    """Append deduplicated sources to the frontmatter ``sources`` list.

    Canonical (typed dict) pages get block-style entries; legacy
    (``- article:<hex>``) pages get string entries — only for article
    evidence, since legacy format cannot express web/builtin sources
    (such patches are policy-classified ``suggestion_only`` and never
    reach this branch in auto-apply mode).
    """
    fm_body = _split_frontmatter(text)
    if fm_body is None:
        raise WikiValidationError(
            "page has no YAML frontmatter; cannot merge sources"
        )
    fm, body = fm_body
    sources = fm.get("sources")
    if not isinstance(sources, list):
        raise WikiValidationError(
            "frontmatter has no sources array; cannot merge sources"
        )
    existing: set = set()
    for s in sources:
        if isinstance(s, dict):
            key = (s.get("type"), s.get("ref")) if s.get("ref") else (s.get("type"), s.get("title"))
        elif isinstance(s, str):
            key = tuple(s.split(":", 1)) if ":" in s else (s,)
        else:
            continue
        existing.add(key)
    additions: List[Dict[str, Any]] = []
    for ev in evidence:
        key = (ev.type, ev.ref) if ev.ref is not None else (ev.type, ev.title)
        if key in existing:
            continue
        existing.add(key)
        additions.append({
            "type": ev.type,
            "ref": ev.ref,
            "title": ev.title,
            "provenance": (ev.provenance or "").strip() or TYPE_PROVENANCE.get(ev.type, ""),
        })
    if not additions:
        return text

    lines = text.split("\n")
    src_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "sources:" and i < len(lines) - 1:
            src_idx = i
            break
    if src_idx is None:
        raise WikiValidationError(
            "frontmatter has no sources array; cannot merge sources"
        )
    legacy_style = isinstance(sources[0], str) if sources else False
    if legacy_style and any(a["type"] != "article" for a in additions):
        # Cannot represent web/builtin in legacy format; leave unchanged.
        return text
    indent = ""
    if src_idx + 1 < len(lines) and lines[src_idx + 1].startswith("  - "):
        indent = "  "
    insert_at = src_idx + 1
    if indent:
        # Canonical block entries: a source entry is the `- ` list item plus
        # its indented continuation lines (`    ref:`, `    title:`, ...).
        # Skip the ENTIRE sources block so the new entry lands after the
        # last complete entry — stopping at the first continuation line
        # would insert mid-entry and corrupt every entry after the first
        # (adversarial review MAJOR finding).
        list_prefix = indent + "- "
        cont_prefix = indent + "  "
        while insert_at < len(lines):
            ln = lines[insert_at]
            if ln.startswith(list_prefix) or ln.startswith(cont_prefix):
                insert_at += 1
                continue
            break
    else:
        # Legacy `- article:<hex>` entries are single lines.
        while insert_at < len(lines) and lines[insert_at].startswith("- "):
            insert_at += 1
    new_lines: List[str] = []
    if legacy_style:
        for a in additions:
            new_lines.append(f"{indent}- article:{a['ref']}")
    else:
        for i, a in enumerate(additions, start=1):
            # Canonical entries carry SCHEMA.md's positional id: the count of
            # existing entries plus the 1-based position among the additions.
            new_lines.append(f"{indent}- id: {len(sources) + i}")
            new_lines.append(f"{indent}  type: {a['type']}")
            if a["ref"] is not None:
                new_lines.append(f"{indent}  ref: {_yaml_str(a['ref'])}")
            new_lines.append(f"{indent}  title: {_yaml_str(a['title'])}")
            new_lines.append(f"{indent}  provenance: {_yaml_value(a['provenance'])}")
    body_lines = "\n".join(lines[insert_at:])
    head_lines = "\n".join(lines[:insert_at])
    if body_lines.strip():
        return head_lines + "\n" + "\n".join(new_lines) + "\n" + body_lines
    return head_lines + "\n" + "\n".join(new_lines) + "\n"


def _set_metadata(text: str, metadata: Dict[str, Any]) -> str:
    """Rewrite allowlisted scalar frontmatter keys (surgical line replace).

    Only compiler-approved keys (NON_CRITICAL_METADATA_KEYS, design §5.3)
    are written; any other key is ignored, so critical fields such as
    ``created`` are always preserved even in hand-crafted ops.
    """
    allowed = {
        k: v for k, v in (metadata or {}).items()
        if k in NON_CRITICAL_METADATA_KEYS
    }
    if not allowed:
        return text
    fm, _ = _split_frontmatter(text)
    if fm is None:
        raise WikiValidationError(
            "page has no YAML frontmatter; cannot set metadata"
        )
    lines = text.split("\n")
    in_frontmatter = False
    for i, ln in enumerate(lines):
        if i == 0 and ln.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and ln.strip() == "---":
            break
        if not in_frontmatter:
            continue
        m = _FM_SCALAR_LINE.match(ln)
        if m and m.group(1) in allowed:
            lines[i] = f"{m.group(1)}: {_yaml_value(allowed[m.group(1)])}"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Final candidate validation gates (design §7 order 6-8; GAP 1)
# ---------------------------------------------------------------------------

def _validate_candidate(
    patch: WikiPatch,
    candidate: str,
    wiki_root: Path,
    current_text: Optional[str],
) -> Tuple[List[str], List[str]]:
    """Run the final candidate-level integrity gates on the assembled
    candidate BEFORE any authoritative write.

    Returns ``(blocking_failures, warnings)``. The candidate is staged to
    a throwaway temp file under the target kind dir so the shared
    ``kb.wiki_lint`` primitives see it exactly as it will be written (a
    full page: frontmatter + body).

    BLOCKING (design §7 order 6-7): frontmatter parse failure and citation
    integrity failures (``kb.wiki_lint.lint_citation_integrity``).
    WARN (order 8, under existing wiki_health policy): broken wikilinks
    (``kb.wiki_lint.lint_backlink_validity``). Contradiction/staleness
    (order 9-10) are intentionally not run — the candidate is fresh by
    construction and LLM-semantic contradiction review is W5B scope.
    """
    target = _resolve_target(wiki_root, patch.target_path)
    # _atomic_write creates this dir anyway; create it now so the temp
    # staging dir below can live next to the target (same kind dir).
    target.parent.mkdir(parents=True, exist_ok=True)

    known_hashes = _known_article_hashes(patch, current_text)
    blocking: List[str] = []
    warnings: List[str] = []
    tmp_dir: Optional[str] = None
    try:
        tmp_dir = tempfile.mkdtemp(
            prefix=".candidate-check-", dir=str(target.parent)
        )
        tmp_page = Path(tmp_dir) / f"{_safe_slug(patch.target_slug)}.md"
        tmp_page.write_text(candidate, encoding="utf-8")

        # Order 6: candidate frontmatter/schema parse. Malformed frontmatter
        # can never be written (wiki_health check_yaml_validity ERROR).
        try:
            frontmatter.load(str(tmp_page))
        except Exception as exc:  # noqa: BLE001 - any parse failure blocks
            blocking.append(f"candidate frontmatter parse failed: {exc}")
            return blocking, warnings

        # Order 7: citation integrity (BLOCKING). Reuses the shared lint
        # primitive — the known corpus is the evidence article refs plus
        # article refs already present on the current page.
        try:
            blocking.extend(lint_citation_integrity(tmp_page, known_hashes))
        except Exception as exc:  # noqa: BLE001 - lint failure blocks
            blocking.append(f"candidate citation integrity check failed: {exc}")
            return blocking, warnings

        # Order 8: wikilink validity under existing policy (WARN only —
        # scripts/wiki_health.py check_wikilinks records broken backlinks
        # as warns; see module docstring).
        try:
            for slug in lint_backlink_validity(candidate, _wiki_dir(wiki_root)):
                warnings.append(f"broken wikilink [[{slug}]] — target not found")
        except Exception as exc:  # noqa: BLE001 - lint failure is WARN
            warnings.append(f"wikilink check failed: {exc}")
        return blocking, warnings
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _known_article_hashes(
    patch: WikiPatch, current_text: Optional[str]
) -> set:
    """Known article corpus for citation integrity on the candidate.

    Article refs from ``patch.evidence`` plus article refs already present
    in the current page's frontmatter ``sources`` (canonical dict entries
    and legacy ``article:<hex>`` strings). Update candidates retain the
    existing page's sources, so those hashes are part of the page's known
    corpus even though the evidence only covers new additions.
    """
    known = {
        ev.ref
        for ev in (patch.evidence or ())
        if ev.type == "article" and ev.ref
    }
    if current_text is None:
        return known
    fm, _ = _split_frontmatter(current_text)
    if fm is None or not isinstance(fm.get("sources"), list):
        return known
    for s in fm["sources"]:
        if isinstance(s, dict):
            if str(s.get("type", "")).lower() == "article" and s.get("ref"):
                known.add(str(s["ref"]))
        elif isinstance(s, str) and s.startswith("article:"):
            known.add(s.split(":", 1)[1])
    return known


# ---------------------------------------------------------------------------
# Minimal frontmatter parsing/rendering helpers (no external YAML dependency)
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Split ``---``-fenced frontmatter into ``(dict, body)`` or ``None``."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    return _parse_frontmatter(fm_text), body


def _parse_frontmatter(fm_text: str) -> Dict[str, Any]:
    """Parse the restricted YAML subset used by wiki pages.

    Handles ``key: value`` scalars, legacy ``- article:<hex>`` list items,
    and canonical block-style ``- type: ...`` / ``  ref: ...`` entries.
    Unknown lines are skipped; the result is used for sources detection
    and policy, not for byte-preserving round-trips.
    """
    fm: Dict[str, Any] = {}
    lines = fm_text.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _FM_SCALAR_LINE.match(ln)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "sources":
            items: List[Any] = []
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    i += 1
                    continue
                if s.startswith("- "):
                    entry = s[2:].strip()
                    em = _FM_SCALAR_LINE.match(entry)
                    if em and em.group(1) in ("article", "web", "builtin"):
                        # legacy string entry
                        items.append(entry)
                        i += 1
                        continue
                    if em:
                        d: Dict[str, Any] = {em.group(1): _yaml_unquote(em.group(2))}
                        i += 1
                        while i < len(lines):
                            cm = _FM_BLOCK_KEY.match(lines[i])
                            if cm and cm.group(2) != "sources":
                                d[cm.group(2)] = _yaml_unquote(cm.group(3))
                                i += 1
                                continue
                            break
                        items.append(d)
                        continue
                    items.append(entry)
                    i += 1
                    continue
                break
            fm["sources"] = items
            continue
        fm[key] = _yaml_unquote(val)
        i += 1
    return fm


def _yaml_unquote(value: str) -> Any:
    """Strip surrounding single/double quotes from a YAML scalar."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _yaml_value(value: Any) -> str:
    """YAML scalar: unquoted for safe tokens, quoted otherwise."""
    s = str(value)
    if re.fullmatch(r"[A-Za-z0-9_.-]+", s):
        return s
    return _yaml_str(s)


def _yaml_str(value: Any) -> str:
    """Double-quoted YAML scalar (deterministic, safe for dates/URLs/hex)."""
    s = str(value)
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Paths / Error Book integration
# ---------------------------------------------------------------------------

def _wiki_dir(wiki_root: Path) -> Path:
    """Resolve the ``kb/wiki`` directory from *wiki_root*.

    *wiki_root* is normally the repository root (patches carry
    ``kb/wiki/...`` target paths); if *wiki_root* itself is ``kb/wiki`` it
    is used directly.
    """
    root = Path(wiki_root)
    candidate = root / "kb" / "wiki"
    if candidate.is_dir() or (root / "kb").is_dir():
        return candidate
    return root


def _resolve_target(wiki_root: Path, target_path: str) -> Path:
    """Resolve ``patch.target_path`` against *wiki_root*."""
    root = Path(wiki_root)
    direct = root / target_path
    if (root / "kb" / "wiki").is_dir() or direct.parent.exists():
        return direct
    return root.parent / target_path


def _report_error_book(
    error_book: Optional[Any],
    patch: WikiPatch,
    wiki_root: Path,
    failures: List[str],
    lint_name: str = "wiki_compiler:evidence_validation",
) -> None:
    """Log a true compiler-integrity failure to the existing Error Book.

    ``lint_name`` distinguishes the failure channel: evidence schema
    validation vs. final candidate integrity gates (GAP 1). The Error Book
    must never break the apply path — failures to log are swallowed.
    """
    log: Optional[Callable[[dict], None]] = None
    if error_book is None:
        log = _default_log_lint_failure
    elif callable(error_book):
        log = error_book
    else:
        log = getattr(error_book, "log_lint_failure", _default_log_lint_failure)
    if log is None:
        return
    target = _resolve_target(wiki_root, patch.target_path)
    try:
        log({
            "lint_name": lint_name,
            "page_path": str(target),
            "failures": failures,
            "suggestion_excerpt": patch.patch_id,
            "patch_id": patch.patch_id,
            "trigger": patch.trigger,
            "compiler_version": patch.compiler_version,
            "ts": datetime.now(UTC).isoformat(),
        })
    except Exception:  # noqa: BLE001 - logging is best-effort
        pass


def _default_log_lint_failure(failure_dict: dict) -> None:
    """Lazy import of the existing Error Book API (keeps engine import light)."""
    from kb.error_book import log_lint_failure
    log_lint_failure(failure_dict)
