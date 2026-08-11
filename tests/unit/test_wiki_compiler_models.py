"""Tests for kb/wiki_compiler.models — frozen-dataclass typed compiler models."""

import json

import pytest


# ---------------------------------------------------------------------------
# Test helpers (used by multiple tests)
# ---------------------------------------------------------------------------

_EPOCH = "2026-08-11T00:00:00Z"


def _make_minimal():
    """Return minimal valid instances for reuse in tests."""
    from kb.wiki_compiler.models import (
        EvidenceRef,
        EvidencePack,
        PatchOperation,
        WikiPatch,
    )
    ev = EvidenceRef(
        evidence_id="ev1", type="article", ref="abcdef1234",
        title="Example Page", provenance="kb-ingest", metadata={},
    )
    pack = EvidencePack(
        pack_id="pack-1", subject_slug="python/debugging",
        subject_title="Debugging Python", trigger="manual",
        article_hashes=("sha256hex00000000000000000000000000000000000000000000000000000000000abcd",),
        evidence=(ev,), context_blocks=("ctx1",),
        existing_page_path="pages/python/debugging.md",
        existing_page_digest="existing-digest-here", created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )
    return EvidenceRef, EvidencePack, WikiPatch, PackType, ev, pack


# ---------------------------------------------------------------------------
# Test 1 — json_round_trip
# ---------------------------------------------------------------------------
def test_wikipatch_json_round_trip():
    """Create a full WikiPatch, serialize/deserialize, assert equality."""
    from kb.wiki_compiler.models import (
        EvidenceRef,
        EvidencePack,
        PatchOperation,
        WikiPatch,
    )

    ev = EvidenceRef(
        evidence_id="ev1", type="article", ref="abcdef1234",
        title="Example Page", provenance="kb-ingest", metadata={},
    )
    pack = EvidencePack(
        pack_id="pack-1", subject_slug="python/debugging",
        subject_title="Debugging Python", trigger="manual",
        article_hashes=("sha256hex" + "0" * 118, ),
        evidence=(ev,), context_blocks=("ctx1",),
        existing_page_path="pages/python/debugging.md",
        existing_page_digest="existing-digest-here", created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )
    ops = (
        PatchOperation(op="UPSERT_SECTION", section="Installation",
                       content="Install python", metadata={}),
    )
    patch = WikiPatch(
        patch_schema_version=1,
        patch_id="wpatch-test001",
        target_slug="python/debugging",
        target_path="pages/python/debugging.md",
        target_kind="entity",
        base_digest="existing-digest-here",
        trigger="manual",
        evidence_pack_id="pack-1",
        operations=ops,
        evidence=(ev,),
        policy_hint="auto_apply",
        reason="Update installation section",
        created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )

    d = patch.to_dict()
    restored = WikiPatch.from_dict(d)
    assert restored.patch_schema_version == 1
    assert restored.patch_id == patch.patch_id
    assert restored.target_slug == patch.target_slug
    assert restored.target_path == patch.target_path
    assert restored.target_kind == patch.target_kind
    assert restored.base_digest == patch.base_digest
    assert len(restored.operations) == len(patch.operations)
    assert restored.operations[0].op == patch.operations[0].op
    assert restored.evidence[0].evidence_id == patch.evidence[0].evidence_id
    # JSON round-trip must be serializable
    json.dumps(d, sort_keys=True)


# ---------------------------------------------------------------------------
# Test 2 — unknown schema version rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("version", [0, 2, 3, -1])
def test_unknown_schema_version_rejected(version):
    """v0 or v2+ should raise ValueError on construction."""
    from kb.wiki_compiler.models import WikiPatch

    with pytest.raises(ValueError, match="patch_schema_version"):
        WikiPatch(
            patch_schema_version=version,
            patch_id="wpatch-x",
            target_slug="slug",
            target_path="slug.md",
            target_kind="entity",
            base_digest=None,
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(),
            evidence=(),
            policy_hint="suggestion_only",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 3 — target path escaping / format rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_path", [
    "../something.md",
    "../../foo.md",
    "/etc/passwd.md",
    "not-a-markdown.txt",
    "",
    "normal.md.bak",
])
def test_target_path_escaping_rejected(bad_path):
    """Path with .., absolute, or non-.md suffix should raise ValueError."""
    from kb.wiki_compiler.models import WikiPatch

    with pytest.raises(ValueError, match="target_path"):
        WikiPatch(
            patch_schema_version=1,
            patch_id="wpatch-x",
            target_slug="slug",
            target_path=bad_path,
            target_kind="entity",
            base_digest=None,
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(),
            evidence=(),
            policy_hint="suggestion_only",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 4 — invalid target_kind rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["unknown", "", "page", "SECTION"])
def test_target_kind_invalid_rejected(kind):
    """Unknown or empty target_kind must raise ValueError."""
    from kb.wiki_compiler.models import WikiPatch

    with pytest.raises(ValueError, match="target_kind"):
        WikiPatch(
            patch_schema_version=1,
            patch_id="wpatch-x",
            target_slug="slug",
            target_path="slug.md",
            target_kind=kind,
            base_digest=None,
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(),
            evidence=(),
            policy_hint="suggestion_only",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 5 — invalid operation rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_op", ["DELETE_PAGE", "REPLACE_PAGE", "REMOVE_SECTION", ""])
def test_invalid_operation_rejected(bad_op):
    """Non-CREATE_PAGE|UPSERT_SECTION|MERGE_SOURCES|SET_METADATA must raise."""
    from kb.wiki_compiler.models import PatchOperation, WikiPatch

    with pytest.raises(ValueError, match="op"):
        WikiPatch(
            patch_schema_version=1,
            patch_id="wpatch-x",
            target_slug="slug",
            target_path="slug.md",
            target_kind="entity",
            base_digest=None,
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(PatchOperation(op=bad_op, section=None, content=None, metadata=None),),
            evidence=(),
            policy_hint="suggestion_only",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 6 — article EvidenceRef ref validation
# ---------------------------------------------------------------------------
def test_article_ref_validation_invalid():
    """Invalid hex or wrong length refs must raise for type='article'."""
    from kb.wiki_compiler.models import EvidenceRef

    for bad in ["xyz", "ZZZZZZZZZZ", "abc", "abcdef12345"]:
        with pytest.raises(ValueError, match="ref"):
            EvidenceRef(
                evidence_id="ev-x", type="article", ref=bad,
                title="T", provenance="test", metadata={},
            )


def test_article_ref_validation_valid():
    """Exactly 10-char lowercase hex must pass."""
    from kb.wiki_compiler.models import EvidenceRef

    ev = EvidenceRef(
        evidence_id="ev-ok", type="article", ref="abcdef1234",
        title="T", provenance="test", metadata={},
    )
    assert ev.ref == "abcdef1234"


def test_non_article_ref_null_allowed():
    """Non-article types should allow ref=None."""
    from kb.wiki_compiler.models import EvidenceRef

    ev = EvidenceRef(
        evidence_id="ev-web", type="web", ref=None,
        title="T", provenance="test", metadata={},
    )
    assert ev.ref is None


# ---------------------------------------------------------------------------
# Test 7 — CREATE_PAGE must have null base_digest
# ---------------------------------------------------------------------------
def test_create_page_with_base_digest_rejected():
    """CREATE_PAGE with non-null base_digest raises ValueError."""
    from kb.wiki_compiler.models import PatchOperation, WikiPatch

    with pytest.raises(ValueError, match="base_digest"):
        WikiPatch(
            patch_schema_version=1,
            patch_id="wpatch-x",
            target_slug="new-page",
            target_path="new-page.md",
            target_kind="entity",
            base_digest="some-digest",
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(PatchOperation(op="CREATE_PAGE", section=None, content="body", metadata=None),),
            evidence=(),
            policy_hint="auto_apply",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 8 — non-CREATE_PAGE must have non-null base_digest
# ---------------------------------------------------------------------------
def test_update_without_base_digest_rejected():
    """UPSERT_SECTION with base_digest=None raises ValueError."""
    from kb.wiki_compiler.models import PatchOperation, WikiPatch

    with pytest.raises(ValueError, match="base_digest"):
        WikiPatch(
            patch_schema_version=1,
            patch_id="wpatch-x",
            target_slug="existing",
            target_path="existing.md",
            target_kind="entity",
            base_digest=None,
            trigger="manual",
            evidence_pack_id="pack-1",
            operations=(PatchOperation(op="UPSERT_SECTION", section="Foo", content="bar", metadata=None),),
            evidence=(),
            policy_hint="auto_apply",
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )


# ---------------------------------------------------------------------------
# Test 9 — stable_patch_id deterministic
# ---------------------------------------------------------------------------
def test_stable_patch_id_deterministic():
    """Same inputs → same patch id."""
    from kb.wiki_compiler.models import (
        PatchOperation,
        stable_patch_id,
    )

    ops = (
        PatchOperation(op="UPSERT_SECTION", section="Foo", content="bar", metadata=None),
    )
    id1 = stable_patch_id(target_slug="x/y", evidence_pack_id="p1", operations=ops)
    id2 = stable_patch_id(target_slug="x/y", evidence_pack_id="p1", operations=ops)
    assert id1 == id2
    assert id1.startswith("wpatch-")
    assert len(id1) == 23  # 'wpatch-' (7) + 16 hex chars


# ---------------------------------------------------------------------------
# Test 10 — page_digest deterministic
# ---------------------------------------------------------------------------
def test_page_digest_deterministic():
    """Same text → same SHA-256 digest."""
    from kb.wiki_compiler.models import page_digest

    t = "# Hello World\nSome body text."
    d1 = page_digest(t)
    d2 = page_digest(t)
    assert d1 == d2
    assert isinstance(d1, str)
    assert len(d1) == 64  # full SHA-256 hex


def test_page_digest_different_text():
    """Different text → different digest."""
    from kb.wiki_compiler.models import page_digest

    assert page_digest("aaa") != page_digest("bbb")


# ---------------------------------------------------------------------------
# Test 11 — builtin EvidenceRef ref=None allowed
# ---------------------------------------------------------------------------
def test_evidence_ref_builtin_null_ref_allowed():
    """type='builtin' with ref=None must pass validation."""
    from kb.wiki_compiler.models import EvidenceRef

    ev = EvidenceRef(
        evidence_id="ev-builtin-1", type="builtin", ref=None,
        title="Built-in Concept", provenance="internal", metadata={"key": "val"},
    )
    assert ev.type == "builtin"
    assert ev.ref is None


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------
def test_policy_hint_accepted_values():
    """Both auto_apply and suggestion_only are accepted values."""
    from kb.wiki_compiler.models import WikiPatch

    for hint in ("auto_apply", "suggestion_only"):
        p = WikiPatch(
            patch_schema_version=1,
            patch_id=f"wpatch-{hint}",
            target_slug="s",
            target_path="s.md",
            target_kind="entity",
            base_digest=None,
            trigger="manual",
            evidence_pack_id="p1",
            operations=(),
            evidence=(),
            policy_hint=hint,
            reason="test",
            created_at=_EPOCH,
            compiler_version="v2.0",
        )
        assert p.policy_hint == hint
