"""W5B durable suggestion-evolution state anchors.

Design §7 ("Suggestion JSON remains the queue"): the existing deterministic
suggestion JSON gains only an ``evolution`` object; no new persistence
layer, no repository/queue/history/lock abstraction.

Covers:
* fresh suggestion initializes exactly design §7 state (pending/0/null);
* re-emitting the same patch preserves the exact evolution object
  (including terminal/retry state) at the same deterministic path;
* malformed existing suggestion JSON is an integrity failure — never
  silently overwritten;
* ``update_suggestion_evolution()`` atomically replaces ONLY
  ``payload['evolution']`` and raises for missing/malformed files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb.wiki_compiler.models import (
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    page_digest,
)

_EPOCH = "2026-08-11T00:00:00Z"

#: Design §7 fresh state — the exact object a new suggestion must carry.
FRESH_EVOLUTION = {
    "status": "pending",
    "attempts": 0,
    "next_retry_at": None,
    "last_evaluated_at": None,
    "last_decision": None,
    "last_reason": None,
    "applied_patch_id": None,
}

_EXISTING_PAGE = """---
title: 'Python Debugging'
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
  - id: 1
    type: article
    ref: 'abcdef1234'
    title: 'Src'
    provenance: lightrag-corpus
confidence_level: low
---

# Python Debugging

## Definition / Overview

Old section body [^1]

## References

[^1]: **Src** — abcdef1234 (lightrag-corpus)
"""


def _make_patch(
    *,
    slug: str = "python-debugging",
    ops: tuple | None = None,
    base_digest: str | None = None,
    patch_id: str,
) -> WikiPatch:
    """Build a valid suggestion-bound WikiPatch (UPSERT_SECTION on an
    existing page — suggestion_only under W5A policy)."""
    ops = ops if ops is not None else (
        PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested body [^1]", metadata=None,
        ),
    )
    return WikiPatch(
        patch_schema_version=1,
        patch_id=patch_id,
        target_slug=slug,
        target_path=f"kb/wiki/entities/{slug}.md",
        target_kind="entity",
        base_digest=base_digest,
        trigger="test",
        evidence_pack_id="pack-1",
        operations=ops,
        evidence=(EvidenceRef(
            evidence_id="e1", type="article", ref="abcdef1234",
            title="Src", provenance="lightrag-corpus", metadata={},
        ),),
        policy_hint="suggestion_only",
        reason="test patch",
        created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )


@pytest.fixture
def wiki_root(tmp_path: Path) -> Path:
    """Repo-shaped tmp wiki root (kb/wiki/{entities,_suggestions})."""
    root = tmp_path / "repo"
    (root / "kb" / "wiki" / "entities").mkdir(parents=True)
    (root / "kb" / "wiki" / "_suggestions").mkdir(parents=True)
    return root


def _write_page(wiki_root: Path, slug: str, content: str) -> Path:
    target = wiki_root / "kb" / "wiki" / "entities" / f"{slug}.md"
    target.write_text(content, encoding="utf-8")
    return target


def _suggestion_path(wiki_root: Path, patch_id: str, slug: str = "python-debugging") -> Path:
    return wiki_root / "kb" / "wiki" / "_suggestions" / f"{slug}-{patch_id}.json"


# ---------------------------------------------------------------------------
# 1. Fresh suggestion initializes exactly design §7 state
# ---------------------------------------------------------------------------

def test_fresh_suggestion_initializes_exact_evolution_state(wiki_root: Path):
    """A new suggestion file carries exactly the design §7 evolution object:
    status=pending, attempts=0, every lifecycle field null, no extras."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        patch_id="wpatch-w5b-evo-0001",
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "suggestion"
    payload = json.loads(Path(result["suggestion_path"]).read_text(encoding="utf-8"))
    assert payload["evolution"] == FRESH_EVOLUTION


# ---------------------------------------------------------------------------
# 2. Re-emitting the same patch preserves the exact evolution object
# ---------------------------------------------------------------------------

def test_reemit_preserves_exact_terminal_evolution_state(wiki_root: Path):
    """Re-emitting the same patch (e.g. a W3 rerun) must NOT reset durable
    state: same deterministic path, exact evolution object preserved —
    including a terminal applied state."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        patch_id="wpatch-w5b-evo-0002",
    )

    r1 = apply_patch(patch, wiki_root)
    assert r1["status"] == "suggestion"
    path = Path(r1["suggestion_path"])

    # Simulate Task 4+ progress: a terminal state on the suggestion file.
    terminal = {
        "status": "applied",
        "attempts": 3,
        "next_retry_at": None,
        "last_evaluated_at": "2026-08-12T01:02:03Z",
        "last_decision": "applied",
        "last_reason": "semantic review passed",
        "applied_patch_id": "wpatch-applied-0009",
    }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evolution"] = terminal
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    r2 = apply_patch(patch, wiki_root)
    assert r2["status"] == "suggestion"
    assert Path(r2["suggestion_path"]) == path
    refreshed = json.loads(path.read_text(encoding="utf-8"))
    assert refreshed["evolution"] == terminal


def test_reemit_preserves_retry_state(wiki_root: Path):
    """A mid-flight retry state (attempts/next_retry_at) survives re-emission
    exactly — the W5B retry loop must not be reset by compiler reruns."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        patch_id="wpatch-w5b-evo-0003",
    )

    r1 = apply_patch(patch, wiki_root)
    path = Path(r1["suggestion_path"])

    retry_state = {
        "status": "retry",
        "attempts": 2,
        "next_retry_at": "2026-08-13T06:00:00Z",
        "last_evaluated_at": "2026-08-12T02:00:00Z",
        "last_decision": "retry",
        "last_reason": "transient LLM failure",
        "applied_patch_id": None,
    }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evolution"] = retry_state
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    r2 = apply_patch(patch, wiki_root)
    assert Path(r2["suggestion_path"]) == path
    refreshed = json.loads(path.read_text(encoding="utf-8"))
    assert refreshed["evolution"] == retry_state


# ---------------------------------------------------------------------------
# 3. Malformed existing suggestion JSON is an integrity failure
# ---------------------------------------------------------------------------

def test_malformed_existing_suggestion_is_integrity_failure_not_overwritten(
    wiki_root: Path,
):
    """A suggestion-bound patch whose deterministic file exists but is
    malformed JSON is a compiler-integrity failure: WikiValidationError
    surfaces as ``rejected`` + Error Book entry, and the malformed file is
    never silently overwritten with fresh evolution state."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        patch_id="wpatch-w5b-malformed-0001",
    )
    path = _suggestion_path(wiki_root, "wpatch-w5b-malformed-0001")
    path.write_text("{ this is not valid json !!!", encoding="utf-8")
    before = path.read_bytes()

    calls = []
    recorder = lambda failure: calls.append(failure)  # noqa: E731

    result = apply_patch(patch, wiki_root, error_book=recorder)
    assert result["status"] == "rejected"
    assert "suggestion" in result["error"].lower()
    assert len(calls) == 1, f"expected exactly one Error Book entry: {calls}"
    assert any("suggestion" in f.lower() for f in calls[0]["failures"]), calls
    # The malformed file must remain byte-for-byte untouched.
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# 4. update_suggestion_evolution — atomic, surgical evolution replacement
# ---------------------------------------------------------------------------

def test_update_suggestion_evolution_replaces_only_evolution_key(
    wiki_root: Path, monkeypatch,
):
    """``update_suggestion_evolution`` rewrites ONLY ``payload['evolution']``
    (every other key preserved exactly), goes through the engine's atomic
    write, and raises WikiValidationError for missing/malformed files —
    never creating or clobbering them."""
    from kb.wiki_compiler.engine import (
        WikiValidationError,
        _atomic_write,
        apply_patch,
        update_suggestion_evolution,
    )
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        patch_id="wpatch-w5b-update-0001",
    )
    r = apply_patch(patch, wiki_root)
    path = Path(r["suggestion_path"])
    original = json.loads(path.read_text(encoding="utf-8"))
    assert set(original) >= {
        "patch", "policy_hint", "reason", "suggested_content",
        "patch_id", "target_slug", "operations", "evidence", "evolution",
    }

    new_evolution = {
        "status": "retry",
        "attempts": 1,
        "next_retry_at": "2026-08-13T06:00:00Z",
        "last_evaluated_at": "2026-08-12T03:00:00Z",
        "last_decision": "retry",
        "last_reason": "transient LLM failure",
        "applied_patch_id": None,
    }
    real_atomic_write = _atomic_write
    written = []

    def spy(target_path, content):
        written.append((str(target_path), content))
        real_atomic_write(target_path, content)

    monkeypatch.setattr("kb.wiki_compiler.engine._atomic_write", spy)

    update_suggestion_evolution(path, new_evolution)

    assert len(written) == 1, f"expected exactly one atomic write: {written}"
    assert written[0][0] == str(path)
    refreshed = json.loads(path.read_text(encoding="utf-8"))
    assert refreshed["evolution"] == new_evolution
    for key, value in original.items():
        if key != "evolution":
            assert refreshed[key] == value, f"key changed: {key}"

    # Missing file: integrity failure — never created.
    missing = _suggestion_path(wiki_root, "wpatch-w5b-update-missing")
    with pytest.raises(WikiValidationError):
        update_suggestion_evolution(missing, new_evolution)
    assert not missing.exists()

    # Malformed file: integrity failure — never overwritten.
    malformed = _suggestion_path(wiki_root, "wpatch-w5b-update-malformed")
    malformed.write_text("{ not json", encoding="utf-8")
    before = malformed.read_bytes()
    with pytest.raises(WikiValidationError):
        update_suggestion_evolution(malformed, new_evolution)
    assert malformed.read_bytes() == before
