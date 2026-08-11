"""Tests for kb.wiki_compiler.engine — shared validation/policy/apply engine.

Covers: evidence schema validation, deterministic policy classification,
per-page advisory locking, optimistic concurrency (base-digest check),
atomic writes, deterministic suggestion files, and Error Book integration
(true integrity failures only — never normal suggestion/conflict outcomes).
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from kb.wiki_compiler.models import (
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    page_digest,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_EPOCH = "2026-08-11T00:00:00Z"


def _raw_evidence_ref(**over) -> EvidenceRef:
    """Build an EvidenceRef bypassing __post_init__ (for corruption tests)."""
    ev = EvidenceRef.__new__(EvidenceRef)
    defaults = dict(
        evidence_id="e1", type="article", ref="abcdef1234",
        title="Src", provenance="lightrag-corpus", metadata={},
    )
    defaults.update(over)
    for k, v in defaults.items():
        object.__setattr__(ev, k, v)
    return ev


def _make_op(**over) -> PatchOperation:
    op = PatchOperation.__new__(PatchOperation)
    defaults = dict(op="CREATE_PAGE", section=None, content=None, metadata=None)
    defaults.update(over)
    for k, v in defaults.items():
        object.__setattr__(op, k, v)
    return op


def _make_patch(
    *,
    slug: str = "python-debugging",
    ops: tuple | None = None,
    base_digest: str | None = None,
    evidence: tuple | None = None,
    policy_hint: str = "auto_apply",
    patch_id: str | None = None,
    target_kind: str = "entity",
    reason: str = "test patch",
) -> WikiPatch:
    """Build a valid WikiPatch via the real constructor."""
    ops = ops if ops is not None else (
        PatchOperation(
            op="CREATE_PAGE",
            section=None,
            content=_PAGE_CONTENT,
            metadata={"title": "Python Debugging"},
        ),
    )
    evidence = evidence if evidence is not None else (
        EvidenceRef(
            evidence_id="e1", type="article", ref="abcdef1234",
            title="Src", provenance="lightrag-corpus", metadata={},
        ),
    )
    return WikiPatch(
        patch_schema_version=1,
        patch_id=patch_id or f"wpatch-{slug.replace('/', '-')[:12]}",
        target_slug=slug,
        target_path=f"kb/wiki/entities/{slug}.md",
        target_kind=target_kind,
        base_digest=base_digest,
        trigger="test",
        evidence_pack_id="pack-1",
        operations=ops,
        evidence=evidence,
        policy_hint=policy_hint,
        reason=reason,
        created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )


def _raw_patch(**over) -> WikiPatch:
    """Build a WikiPatch bypassing __post_init__ (for policy corruption tests)."""
    p = WikiPatch.__new__(WikiPatch)
    defaults = dict(
        patch_schema_version=1, patch_id="wpatch-raw", target_slug="x",
        target_path="kb/wiki/entities/x.md", target_kind="entity",
        base_digest=None, trigger="test", evidence_pack_id="pack-1",
        operations=(), evidence=(), policy_hint="auto_apply", reason="r",
        created_at=_EPOCH, compiler_version="v2.0-w5a",
    )
    defaults.update(over)
    for k, v in defaults.items():
        object.__setattr__(p, k, v)
    return p


_PAGE_CONTENT = """---
title: 'Python Debugging'
created: '2026-08-11'
last_updated: '2026-08-11'
sources:
  - id: 1
    type: article
    ref: 'abcdef1234'
    title: 'Src'
    provenance: lightrag-corpus
confidence_level: low
---

# Python Debugging

Fresh body paragraph [^1]

## References

[^1]: **Src** — abcdef1234 (lightrag-corpus)
"""

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

_LEGACY_PAGE = """---
title: Agent
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:5a362bf61e
confidence_level: high
---

# Agent

## Definition / Overview

Old text ^[article:5a362bf61e]
"""

# Canonical page with TWO complete multi-line source entries — the shape the
# W5A assembler/W1 emit. Regression fixture for the adversarial review MAJOR:
# _merge_sources used to stop its insertion scan at the first continuation
# line, corrupting every entry after the first.
_CANONICAL_2_ENTRY_PAGE = """---
title: 'Python Debugging'
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
  - id: 1
    type: article
    ref: 'abcdef1234'
    title: 'Src'
    provenance: lightrag-corpus
  - id: 2
    type: web
    ref: 'https://example.com/docs'
    title: 'Web Docs'
    provenance: tavily-web
confidence_level: high
---

# Python Debugging

## Definition / Overview

Old section body [^1][^2]

## References

[^1]: **Src** — abcdef1234 (lightrag-corpus)
[^2]: **Web Docs** — https://example.com/docs (tavily-web)
"""

_NO_FRONTMATTER_PAGE = "# No Frontmatter\n\nPlain body without YAML block.\n"


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


# ---------------------------------------------------------------------------
# 1. validate_evidence
# ---------------------------------------------------------------------------

def test_validate_evidence_empty_pack_ok():
    """Empty evidence tuple passes validation with zero errors."""
    from kb.wiki_compiler.engine import validate_evidence
    assert validate_evidence(()) == []


def test_validate_evidence_bad_ref_rejected():
    """Article ref not matching the 10-char hex pattern is rejected."""
    from kb.wiki_compiler.engine import validate_evidence
    bad = _raw_evidence_ref(ref="NOT_HEX_REF")
    errors = validate_evidence((bad,))
    assert len(errors) == 1
    assert "ref" in errors[0] and "a-f0-9" in errors[0]


def test_validate_evidence_web_ref_required():
    """Web evidence without a ref string is rejected."""
    from kb.wiki_compiler.engine import validate_evidence
    bad = _raw_evidence_ref(type="web", ref=None)
    errors = validate_evidence((bad,))
    assert len(errors) == 1
    assert "web" in errors[0]


def test_validate_evidence_unknown_type_rejected():
    """Unknown evidence type is rejected."""
    from kb.wiki_compiler.engine import validate_evidence
    bad = _raw_evidence_ref(type="gossip")
    errors = validate_evidence((bad,))
    assert any("type" in e for e in errors)


def test_validate_evidence_raises_on_non_tuple():
    """Structurally invalid input raises WikiValidationError, not list."""
    from kb.wiki_compiler.engine import WikiValidationError, validate_evidence
    with pytest.raises(WikiValidationError):
        validate_evidence("not-evidence")


# ---------------------------------------------------------------------------
# 2. classify_patch (deterministic policy)
# ---------------------------------------------------------------------------

def test_classify_create_page_auto_apply(wiki_root: Path):
    """CREATE_PAGE on a page that does not exist yet -> auto_apply."""
    from kb.wiki_compiler.engine import classify_patch
    patch = _make_patch()
    assert classify_patch(patch, wiki_root) == "auto_apply"


def test_classify_create_page_existing_is_suggestion(wiki_root: Path):
    """CREATE_PAGE targeting an existing page must never clobber -> suggestion_only."""
    from kb.wiki_compiler.engine import classify_patch
    _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch()
    assert classify_patch(patch, wiki_root) == "suggestion_only"


def test_classify_upsert_section_suggestion_only(wiki_root: Path):
    """UPSERT_SECTION on an existing page -> suggestion_only (W5A property 5)."""
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="New body [^1]", metadata=None,
        ),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        policy_hint="suggestion_only",
    )
    assert classify_patch(patch, wiki_root) == "suggestion_only"


def test_classify_set_metadata_last_updated_auto_apply(wiki_root: Path):
    """SET_METADATA on non-critical field (last_updated) -> auto_apply."""
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(PatchOperation(
            op="SET_METADATA", section=None, content=None,
            metadata={"last_updated": "2026-08-11"},
        ),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
    )
    assert classify_patch(patch, wiki_root) == "auto_apply"


def test_classify_set_metadata_critical_key_suggestion_only(wiki_root: Path):
    """SET_METADATA touching critical fields (created/title/sources) -> suggestion_only.

    Design §5.3: ``SET_METADATA`` must preserve ``created``; ``created`` is
    not on the compiler-approved allowlist.
    """
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(PatchOperation(
            op="SET_METADATA", section=None, content=None,
            metadata={"created": "1999-01-01"},
        ),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
    )
    assert classify_patch(patch, wiki_root) == "suggestion_only"


def test_classify_set_metadata_confidence_level_auto_apply(wiki_root: Path):
    """SET_METADATA on compiler-approved confidence_level -> auto_apply (design §5.3)."""
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(PatchOperation(
            op="SET_METADATA", section=None, content=None,
            metadata={"confidence_level": "high"},
        ),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
    )
    assert classify_patch(patch, wiki_root) == "auto_apply"


def test_classify_merge_plus_critical_set_metadata_suggestion_only(wiki_root: Path):
    """MERGE_SOURCES with a sibling SET_METADATA on a critical key -> suggestion_only.

    Adversarial MINOR-5: the MERGE branch used to auto-apply without
    inspecting sibling SET_METADATA keys, so a hand-crafted
    (MERGE_SOURCES, SET_METADATA{created}) patch could rewrite ``created``.
    """
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(
            PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),
            PatchOperation(
                op="SET_METADATA", section=None, content=None,
                metadata={"created": "1999-01-01"},
            ),
        ),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
    )
    assert classify_patch(patch, wiki_root) == "suggestion_only"


def test_classify_merge_sources_legacy_incompatible_suggestion_only(wiki_root: Path):
    """MERGE_SOURCES with web/builtin evidence into a legacy page -> suggestion_only."""
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "agent", _LEGACY_PAGE)
    web_ev = EvidenceRef(
        evidence_id="e2", type="web", ref="https://example.com/doc",
        title="Web Doc", provenance="tavily-web", metadata={},
    )
    patch = _make_patch(
        slug="agent",
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        evidence=(web_ev,),
    )
    assert classify_patch(patch, wiki_root) == "suggestion_only"


def test_classify_merge_sources_canonical_auto_apply(wiki_root: Path):
    """MERGE_SOURCES into a canonical (typed) page is provenance-compatible -> auto_apply."""
    from kb.wiki_compiler.engine import classify_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    new_ev = EvidenceRef(
        evidence_id="e2", type="article", ref="0123456789",
        title="Second Src", provenance="lightrag-corpus", metadata={},
    )
    patch = _make_patch(
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(target.read_text(encoding="utf-8")),
        evidence=(new_ev,),
    )
    assert classify_patch(patch, wiki_root) == "auto_apply"


def test_classify_delete_page_rejected(wiki_root: Path):
    """Any DELETE_PAGE operation is rejected (W5A property 7)."""
    from kb.wiki_compiler.engine import classify_patch
    patch = _raw_patch(operations=(_make_op(op="DELETE_PAGE"),))
    assert classify_patch(patch, wiki_root) == "rejected"


def test_classify_page_registry_override(wiki_root: Path):
    """page_registry can answer existence without touching the filesystem."""
    from kb.wiki_compiler.engine import classify_patch
    patch = _make_patch()
    registry = {"python-debugging": {"exists": True, "legacy": False}}
    assert classify_patch(patch, wiki_root, page_registry=registry) == "suggestion_only"
    registry = {"python-debugging": {"exists": False, "legacy": False}}
    assert classify_patch(patch, wiki_root, page_registry=registry) == "auto_apply"


# ---------------------------------------------------------------------------
# 3. apply_patch — atomicity, concurrency, suggestions, error book
# ---------------------------------------------------------------------------

def test_apply_patch_atomic_write(wiki_root: Path, monkeypatch):
    """Write happens atomically: os.replace used, no .tmp residue, full content."""
    import os as _os
    import kb.wiki_compiler.engine as engine
    from kb.wiki_compiler.engine import apply_patch

    replaced: list[tuple] = []
    real_replace = _os.replace

    def fake_replace(src, dst):
        replaced.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(engine.os, "replace", fake_replace)

    patch = _make_patch()
    result = apply_patch(patch, wiki_root)

    target = wiki_root / "kb" / "wiki" / "entities" / "python-debugging.md"
    assert result["status"] == "applied"
    assert result["error"] is None
    assert target.read_text(encoding="utf-8") == _PAGE_CONTENT
    # Exactly one temp -> target replace
    assert len(replaced) == 1
    tmp_path, dst_path = replaced[0]
    assert tmp_path.endswith(".tmp")
    assert Path(dst_path) == target
    # No leftover temp files anywhere in the page directory
    leftovers = [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_apply_patch_success_no_conflict(wiki_root: Path):
    """Matching base_digest -> applied, page content updated."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(
            PatchOperation(
                op="MERGE_SOURCES", section=None, content=None, metadata=None,
            ),
            PatchOperation(
                op="SET_METADATA", section=None, content=None,
                metadata={"last_updated": "2026-08-11"},
            ),
        ),
        base_digest=page_digest(before),
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref="abcdef1234",
                title="Src", provenance="lightrag-corpus", metadata={},
            ),
            EvidenceRef(
                evidence_id="e2", type="article", ref="0123456789",
                title="Second Src", provenance="lightrag-corpus", metadata={},
            ),
        ),
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "applied"
    assert result["error"] is None
    after = target.read_text(encoding="utf-8")
    # SET_METADATA updated the scalar frontmatter key
    assert "last_updated: 2026-08-11" in after
    # MERGE_SOURCES appended the new typed source
    assert 'ref: "0123456789"' in after
    # Body untouched by metadata/source-only operations
    assert "Old section body [^1]" in after
    assert page_digest(after) != page_digest(before)


def test_apply_patch_merge_plus_critical_metadata_suggestion_only(wiki_root: Path):
    """Mixed MERGE_SOURCES + SET_METADATA{created} -> suggestion, page untouched.

    End-to-end MINOR-5 guard: the patch classifies suggestion_only, the page
    is never written, and the rendered candidate preserves ``created`` while
    still showing the (non-applied) source merge.
    """
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(
            PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),
            PatchOperation(
                op="SET_METADATA", section=None, content=None,
                metadata={"created": "1999-01-01"},
            ),
        ),
        base_digest=page_digest(before),
        evidence=(
            EvidenceRef(
                evidence_id="e2", type="article", ref="0123456789",
                title="Second Src", provenance="lightrag-corpus", metadata={},
            ),
        ),
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "suggestion"
    # The page itself is never touched.
    assert target.read_text(encoding="utf-8") == before
    payload = json.loads(Path(result["suggestion_path"]).read_text(encoding="utf-8"))
    # `created` survives; the merge is visible only in the candidate.
    assert "created: '2026-05-20'" in payload["suggested_content"]
    assert "created: '1999-01-01'" not in payload["suggested_content"]
    assert 'ref: "0123456789"' in payload["suggested_content"]


def test_set_metadata_render_skips_critical_keys():
    """_render_candidate SET_METADATA rewrites only allowlisted keys (design §5.3).

    Defense-in-depth: even if a critical key is hand-crafted into a
    SET_METADATA op, the renderer ignores it — ``created`` is preserved.
    """
    from kb.wiki_compiler.engine import _render_candidate
    patch = _make_patch(
        ops=(PatchOperation(
            op="SET_METADATA", section=None, content=None,
            metadata={"created": "1999-01-01", "last_updated": "2026-08-11"},
        ),),
        base_digest="f" * 64,
    )
    rendered = _render_candidate(patch, _EXISTING_PAGE)
    assert "created: '2026-05-20'" in rendered
    assert "created: '1999-01-01'" not in rendered
    assert "last_updated: 2026-08-11" in rendered


def test_apply_patch_merge_sources_preserves_multi_entry_blocks(wiki_root: Path):
    """MERGE_SOURCES into a canonical page with >=2 multi-line entries must
    keep EVERY original entry intact (own ref/title/provenance) and append
    the new entry LAST. Regression for the adversarial review MAJOR finding:
    the insertion scan previously stopped at the first continuation line,
    landing mid-entry and corrupting the block."""
    import frontmatter
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _CANONICAL_2_ENTRY_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(PatchOperation(
            op="MERGE_SOURCES", section=None, content=None, metadata=None,
        ),),
        base_digest=page_digest(before),
        evidence=(
            EvidenceRef(
                evidence_id="e3", type="article", ref="0123456789",
                title="New Src", provenance="lightrag-corpus", metadata={},
            ),
        ),
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "applied", result["error"]

    post = frontmatter.load(str(target))
    sources = post.metadata["sources"]
    assert [s["type"] for s in sources] == ["article", "web", "article"]
    # Every original entry keeps its own keys — nothing absorbed or mangled
    assert sources[0] == {
        "id": 1, "type": "article", "ref": "abcdef1234",
        "title": "Src", "provenance": "lightrag-corpus",
    }, f"entry 1 corrupted: {sources[0]}"
    assert sources[1] == {
        "id": 2, "type": "web", "ref": "https://example.com/docs",
        "title": "Web Docs", "provenance": "tavily-web",
    }, f"entry 2 corrupted: {sources[1]}"
    # New entry appended LAST, complete with all its keys
    assert sources[2] == {
        "id": 3, "type": "article", "ref": "0123456789",
        "title": "New Src", "provenance": "lightrag-corpus",
    }, f"new entry malformed: {sources[2]}"
    # Body untouched
    assert "Old section body [^1][^2]" in target.read_text(encoding="utf-8")


def test_merge_sources_suggestion_render_preserves_multi_entry_blocks():
    """The suggestion path (_render_candidate -> _merge_sources) must also
    preserve multi-entry canonical blocks — every existing-page suggestion
    for a canonical page renders through this path."""
    import frontmatter
    from kb.wiki_compiler.engine import _render_candidate
    patch = _make_patch(
        ops=(PatchOperation(
            op="MERGE_SOURCES", section=None, content=None, metadata=None,
        ),),
        base_digest=page_digest(_CANONICAL_2_ENTRY_PAGE),
        evidence=(
            EvidenceRef(
                evidence_id="e3", type="article", ref="0123456789",
                title="New Src", provenance="lightrag-corpus", metadata={},
            ),
        ),
    )
    out = _render_candidate(patch, _CANONICAL_2_ENTRY_PAGE)
    post = frontmatter.loads(out)
    sources = post.metadata["sources"]
    assert len(sources) == 3
    assert sources[0] == {
        "id": 1, "type": "article", "ref": "abcdef1234",
        "title": "Src", "provenance": "lightrag-corpus",
    }
    assert sources[1] == {
        "id": 2, "type": "web", "ref": "https://example.com/docs",
        "title": "Web Docs", "provenance": "tavily-web",
    }
    assert sources[2]["type"] == "article"
    assert sources[2]["ref"] == "0123456789"
    assert sources[2]["title"] == "New Src"


def test_apply_patch_conflict_on_digest_mismatch(wiki_root: Path):
    """Wrong base_digest -> conflict; external mutation is never overwritten."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    original = target.read_text(encoding="utf-8")
    # Build patch against the ORIGINAL digest, then mutate the page externally.
    patch = _make_patch(
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(original),
    )
    external_mutation = original + "\n\nExternal edit landed.\n"
    target.write_text(external_mutation, encoding="utf-8")

    result = apply_patch(patch, wiki_root)
    assert result["status"] == "conflict"
    assert result["error"] is not None
    assert "digest" in result["error"].lower()
    # The externally-mutated version is preserved byte-for-byte.
    assert target.read_text(encoding="utf-8") == external_mutation


def test_apply_patch_conflict_when_create_target_exists(wiki_root: Path, monkeypatch):
    """CREATE_PAGE with base_digest=None must conflict if the page exists."""
    import kb.wiki_compiler.engine as engine
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch()
    # Policy would classify this suggestion_only; force auto_apply to exercise
    # the optimistic-concurrency guard (create-vs-existing race).
    monkeypatch.setattr(engine, "classify_patch", lambda *a, **k: "auto_apply")
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "conflict"
    assert target.read_text(encoding="utf-8") == _EXISTING_PAGE


def test_apply_patch_conflict_when_update_target_missing(wiki_root: Path, monkeypatch):
    """UPDATE patch whose target page vanished -> conflict, never re-created."""
    import kb.wiki_compiler.engine as engine
    from kb.wiki_compiler.engine import apply_patch
    patch = _make_patch(
        ops=(PatchOperation(op="SET_METADATA", section=None, content=None,
                            metadata={"last_updated": "2026-08-11"}),),
        base_digest=page_digest(_EXISTING_PAGE),
    )
    # Force auto_apply to exercise the vanished-target race guard.
    monkeypatch.setattr(engine, "classify_patch", lambda *a, **k: "auto_apply")
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "conflict"
    assert not (wiki_root / "kb" / "wiki" / "entities" / "python-debugging.md").exists()


def test_apply_patch_merge_sources_canonical(wiki_root: Path):
    """MERGE_SOURCES on a canonical page adds typed entries, keeps body intact."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    new_ev = EvidenceRef(
        evidence_id="e2", type="article", ref="0123456789",
        title="Second Src", provenance="lightrag-corpus", metadata={},
    )
    patch = _make_patch(
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(before),
        evidence=(new_ev,),
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "applied"
    after = target.read_text(encoding="utf-8")
    assert 'ref: "0123456789"' in after
    assert "Old section body [^1]" in after  # body untouched


def test_suggestion_written_for_suggestion_only(wiki_root: Path):
    """suggestion_only outcome writes deterministic JSON, never mutates the page."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested body [^1]", metadata=None,
        ),),
        base_digest=page_digest(before),
        policy_hint="suggestion_only",
        patch_id="wpatch-sugg-0001",
    )
    result = apply_patch(patch, wiki_root)

    assert result["status"] == "suggestion"
    assert result["error"] is None
    assert result["suggestion_path"] is not None
    # Page untouched
    assert target.read_text(encoding="utf-8") == before

    sugg_path = Path(result["suggestion_path"])
    assert sugg_path.exists()
    assert sugg_path.name == "python-debugging-wpatch-sugg-0001.json"
    assert sugg_path.parent.name == "_suggestions"

    payload = json.loads(sugg_path.read_text(encoding="utf-8"))
    assert payload["patch_id"] == "wpatch-sugg-0001"
    assert payload["target_slug"] == "python-debugging"
    assert payload["policy_hint"] == "suggestion_only"
    assert payload["reason"] == "test patch"
    assert isinstance(payload["operations"], list) and payload["operations"]
    assert isinstance(payload["evidence"], list) and payload["evidence"]
    assert "Suggested body [^1]" in payload["suggested_content"]


def test_suggestion_payload_contains_full_serialized_wikipatch(wiki_root: Path):
    """Design §5.4: the suggestion JSON stores the FULL serialized WikiPatch
    (round-trips through WikiPatch.from_dict) plus the policy outcome.

    Adversarial MINOR-6: the payload used to omit target_path/target_kind/
    base_digest/trigger/evidence_pack_id/created_at/compiler_version/
    patch_schema_version, so a persisted suggestion was not a serialized
    WikiPatch and could not be re-applied.
    """
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested body [^1]", metadata=None,
        ),),
        base_digest=page_digest(before),
        policy_hint="suggestion_only",
        patch_id="wpatch-sugg-0003",
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "suggestion"
    payload = json.loads(Path(result["suggestion_path"]).read_text(encoding="utf-8"))

    serialized = payload["patch"]
    for field in (
        "patch_schema_version", "patch_id", "target_slug", "target_path",
        "target_kind", "base_digest", "trigger", "evidence_pack_id",
        "operations", "evidence", "policy_hint", "reason", "created_at",
        "compiler_version",
    ):
        assert field in serialized, f"serialized WikiPatch missing {field!r}"
    # The embedded patch re-deserializes to the original. models.from_dict
    # normalizes metadata=None -> {} for CREATE_PAGE/UPSERT_SECTION ops
    # (documented models behavior, not a serialization loss), so the
    # expected value carries that normalization.
    rt = WikiPatch.from_dict(serialized)
    expected = replace(
        patch,
        operations=tuple(
            replace(o, metadata={})
            if o.metadata is None and o.op in ("CREATE_PAGE", "UPSERT_SECTION")
            else o
            for o in patch.operations
        ),
    )
    assert rt == expected

    # Flat convenience mirrors remain for existing readers.
    assert payload["patch_id"] == patch.patch_id
    assert payload["target_slug"] == patch.target_slug
    assert payload["policy_hint"] == "suggestion_only"
    assert payload["reason"] == patch.reason
    assert "Suggested body [^1]" in payload["suggested_content"]


def test_suggestion_filename_deterministic_no_duplicates(wiki_root: Path):
    """Same patch written twice -> same path, exactly one file, no timestamps."""
    from kb.wiki_compiler.engine import apply_patch
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    patch = _make_patch(
        ops=(PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested body [^1]", metadata=None,
        ),),
        base_digest=page_digest(before),
        policy_hint="suggestion_only",
        patch_id="wpatch-sugg-0002",
    )
    r1 = apply_patch(patch, wiki_root)
    r2 = apply_patch(patch, wiki_root)
    assert r1["suggestion_path"] == r2["suggestion_path"]
    sugg_dir = wiki_root / "kb" / "wiki" / "_suggestions"
    assert [p.name for p in sugg_dir.iterdir()] == ["python-debugging-wpatch-sugg-0002.json"]


def test_error_book_not_used_for_normal_outcomes(wiki_root: Path):
    """No Error Book entries for applied / suggestion / conflict outcomes."""
    from kb.wiki_compiler.engine import apply_patch

    calls = []
    recorder = lambda failure: calls.append(failure)

    # applied (create)
    assert apply_patch(_make_patch(patch_id="wpatch-eb-0001"), wiki_root,
                       error_book=recorder)["status"] == "applied"

    # suggestion (UPSERT_SECTION on existing page)
    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    before = target.read_text(encoding="utf-8")
    sugg_patch = _make_patch(
        ops=(PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested [^1]", metadata=None,
        ),),
        base_digest=page_digest(before),
        policy_hint="suggestion_only",
        patch_id="wpatch-eb-0002",
    )
    assert apply_patch(sugg_patch, wiki_root, error_book=recorder)["status"] == "suggestion"

    # conflict (digest mismatch on an auto_apply op: MERGE_SOURCES)
    target.write_text(before + "\n\nExternal edit.\n", encoding="utf-8")
    merge_patch = _make_patch(
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(before),
        patch_id="wpatch-eb-0002b",
    )
    assert apply_patch(merge_patch, wiki_root, error_book=recorder)["status"] == "conflict"

    assert calls == []


def test_error_book_called_on_validation_failure(wiki_root: Path):
    """Evidence corruption -> rejected + exactly one Error Book entry."""
    from kb.wiki_compiler.engine import apply_patch

    calls = []
    recorder = lambda failure: calls.append(failure)
    corrupt = _raw_evidence_ref(ref="BADREF0000")
    # Corrupt evidence cannot pass the WikiPatch constructor (it re-validates
    # refs), so build the patch raw — exactly what the engine must catch.
    patch = _raw_patch(
        evidence=(corrupt,),
        patch_id="wpatch-eb-0003",
        target_slug="python-debugging",
        target_path="kb/wiki/entities/python-debugging.md",
    )

    result = apply_patch(patch, wiki_root, error_book=recorder)
    assert result["status"] == "rejected"
    assert result["error"] is not None
    assert len(calls) == 1
    entry = calls[0]
    assert entry["lint_name"] == "wiki_compiler:evidence_validation"
    assert entry["patch_id"] == "wpatch-eb-0003"
    assert entry["page_path"].endswith("python-debugging.md")
    assert entry["failures"] and "ref" in entry["failures"][0]
    # Nothing was written for the rejected patch
    assert not (wiki_root / "kb" / "wiki" / "entities" / "python-debugging.md").exists()


def test_error_book_called_on_parse_failure(wiki_root: Path):
    """MERGE_SOURCES into a page without frontmatter -> rejected + Error Book."""
    from kb.wiki_compiler.engine import apply_patch

    calls = []
    recorder = lambda failure: calls.append(failure)
    target = _write_page(wiki_root, "no-frontmatter", _NO_FRONTMATTER_PAGE)
    patch = _make_patch(
        slug="no-frontmatter",
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest(_NO_FRONTMATTER_PAGE),
        patch_id="wpatch-eb-0004",
    )
    result = apply_patch(patch, wiki_root, error_book=recorder)
    assert result["status"] == "rejected"
    assert len(calls) == 1
    assert calls[0]["lint_name"].startswith("wiki_compiler:")
    # Page unchanged
    assert target.read_text(encoding="utf-8") == _NO_FRONTMATTER_PAGE


def test_wiki_update_hook_called_on_applied_only(wiki_root: Path):
    """wiki_update hook fires after applied, never for conflict/suggestion."""
    from kb.wiki_compiler.engine import apply_patch

    hook_calls = []
    hook = lambda result: hook_calls.append(result["status"])

    assert apply_patch(_make_patch(patch_id="wpatch-hook-1"), wiki_root,
                       wiki_update=hook)["status"] == "applied"
    assert hook_calls == ["applied"]

    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    patch = _make_patch(
        ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
        base_digest=page_digest("stale-content-that-never-existed"),
        patch_id="wpatch-hook-2",
    )
    assert apply_patch(patch, wiki_root, wiki_update=hook)["status"] == "conflict"
    assert hook_calls == ["applied"]


def test_concurrent_same_base_at_most_one_applied(wiki_root: Path):
    """Two patches derived from the same old base: at most one wins."""
    from kb.wiki_compiler.engine import apply_patch

    target = _write_page(wiki_root, "python-debugging", _EXISTING_PAGE)
    base = page_digest(target.read_text(encoding="utf-8"))

    def worker(results, barrier):
        patch = _make_patch(
            ops=(PatchOperation(op="MERGE_SOURCES", section=None, content=None, metadata=None),),
            base_digest=base,
            evidence=(EvidenceRef(
                evidence_id="e2", type="article", ref="0123456789",
                title="Second Src", provenance="lightrag-corpus", metadata={},
            ),),
        )
        barrier.wait()
        results.append(apply_patch(patch, wiki_root))

    results: list[dict] = []
    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=worker, args=(results, barrier)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    statuses = sorted(r["status"] for r in results)
    assert statuses == ["applied", "conflict"], f"unexpected statuses: {statuses}"
    # The winner's content is present exactly once, fully rendered.
    assert target.read_text(encoding="utf-8").count('ref: "0123456789"') == 1
