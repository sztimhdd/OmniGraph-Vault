"""Tests for kb/wiki_compiler/assembler.py — pure patch assembler.

Covers canonical CREATE_PAGE assembly (typed sources + GFM citations),
existing-page update semantics (preserve format, no bulk migration),
source deduplication, deterministic output, and operation selection.
"""

from datetime import date
from pathlib import Path

import pytest

from kb.wiki_compiler.assembler import (
    _build_canonical_frontmatter,
    _build_gfm_body,
    _build_references_section,
    _slugify,
    assemble_patch,
)
from kb.wiki_compiler.models import EvidenceRef, EvidencePack


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_TODAY = date(2026, 8, 11)


def _article(evidence_id, ref, title, provenance="lightrag-corpus", metadata=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        type="article",
        ref=ref,
        title=title,
        provenance=provenance,
        metadata=metadata or {},
    )


def _web(evidence_id, ref, title, provenance="tavily-web", metadata=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        type="web",
        ref=ref,
        title=title,
        provenance=provenance,
        metadata=metadata or {},
    )


def _builtin(evidence_id, title, provenance="", metadata=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        type="builtin",
        ref=None,
        title=title,
        provenance=provenance,
        metadata=metadata or {},
    )


def _pack(
    *,
    subject_slug="test-subject",
    subject_title="Test Subject",
    evidence=(),
    context_blocks=(),
    existing_page_path=None,
    existing_page_digest=None,
    pack_id="pack-1",
):
    return EvidencePack(
        pack_id=pack_id,
        subject_slug=subject_slug,
        subject_title=subject_title,
        trigger="manual_test",
        article_hashes=tuple(
            ev.ref for ev in evidence if ev.type == "article"
        ),
        evidence=tuple(evidence),
        context_blocks=tuple(context_blocks),
        existing_page_path=existing_page_path,
        existing_page_digest=existing_page_digest,
        created_at="2026-08-11T00:00:00Z",
        compiler_version="v2.0-w5a",
    )


# ---------------------------------------------------------------------------
# 1. CREATE_PAGE assembly
# ---------------------------------------------------------------------------

def test_create_page_assembles_valid_patch():
    """EP with article+web sources produces CREATE_PAGE with canonical
    frontmatter (typed sources), GFM [^N] citations, and references."""
    ev_article = _article(
        "ev1", "0123456789", "Article A", metadata={"context_blocks": [0]}
    )
    ev_web = _web(
        "ev2", "https://example.com/source", "Web Source",
        metadata={"context_blocks": [1]},
    )
    pack = _pack(
        evidence=(ev_article, ev_web),
        context_blocks=("Article paragraph.", "Web paragraph."),
    )

    patch = assemble_patch(pack, "entity", today=_TODAY)

    assert patch.patch_schema_version == 1
    assert patch.target_kind == "entity"
    assert patch.base_digest is None
    assert patch.evidence_pack_id == "pack-1"
    assert patch.policy_hint == "auto_apply"

    assert len(patch.operations) == 1
    op = patch.operations[0]
    assert op.op == "CREATE_PAGE"
    assert op.content is not None
    assert op.metadata["title"] == "Test Subject"
    assert op.metadata["created"] == "2026-08-11"
    assert op.metadata["last_updated"] == "2026-08-11"

    content = op.content
    frontmatter = content.split("---", 2)[1]
    assert content.startswith("---\n")
    assert 'title: "Test Subject"' in frontmatter
    assert 'created: "2026-08-11"' in frontmatter
    assert 'last_updated: "2026-08-11"' in frontmatter
    assert "type: article" in frontmatter
    assert "type: web" in frontmatter
    assert 'ref: "0123456789"' in frontmatter
    assert 'ref: "https://example.com/source"' in frontmatter
    assert "provenance: lightrag-corpus" in frontmatter
    assert "provenance: tavily-web" in frontmatter

    # GFM body citations, numbered by catalog order
    assert "Article paragraph. [^1]" in content
    assert "Web paragraph. [^2]" in content
    # References section lists each citation
    assert "## References" in content
    assert "[^1]:" in content
    assert "[^2]:" in content
    # No legacy inline citations on new pages
    assert "^[article:" not in content


# ---------------------------------------------------------------------------
# 2. created date semantics (create vs update)
# ---------------------------------------------------------------------------

def test_create_preserves_created_date():
    """A pack targeting an existing page is an UPDATE: no CREATE_PAGE op and
    no op may touch `created`. A fresh pack (no existing_page_path) sets
    created to today."""
    today = _TODAY
    digest = "d" * 64

    # UPDATE case: existing page with `created` preserved (not rewritten)
    ev = _article("ev1", "0123456789", "Article A",
                  metadata={"context_blocks": [0]})
    update_pack = _pack(
        evidence=(ev,),
        context_blocks=("New section text.",),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest=digest,
    )
    update_patch = assemble_patch(update_pack, "entity", today=today)
    assert update_patch.base_digest == digest
    assert all(op.op != "CREATE_PAGE" for op in update_patch.operations)
    for op in update_patch.operations:
        md = op.metadata or {}
        assert "created" not in md, (
            f"op {op.op} must not rewrite `created`"
        )

    # CREATE case: created == today
    create_pack = _pack(
        evidence=(ev,), context_blocks=("New section text.",)
    )
    create_patch = assemble_patch(create_pack, "entity", today=today)
    assert create_patch.operations[0].op == "CREATE_PAGE"
    assert create_patch.operations[0].metadata["created"] == today.isoformat()


# ---------------------------------------------------------------------------
# 3. Source deduplication
# ---------------------------------------------------------------------------

def test_source_deduplication():
    """Duplicate article refs appear exactly once in sources[] and [^N]."""
    dup1 = _article("e1", "0123456789", "Dup Article",
                    metadata={"context_blocks": [0]})
    dup2 = _article("e2", "0123456789", "Dup Article",
                    metadata={"context_blocks": [0]})
    other = _article("e3", "abcdef1234", "Other Article",
                     metadata={"context_blocks": [1]})
    pack = _pack(
        evidence=(dup1, dup2, other),
        context_blocks=("First block.", "Second block."),
    )

    patch = assemble_patch(pack, "entity", today=_TODAY)
    # Deduplicated evidence catalog
    assert len(patch.evidence) == 2
    assert [e.ref for e in patch.evidence] == ["0123456789", "abcdef1234"]

    content = patch.operations[0].content
    frontmatter = content.split("---", 2)[1]
    assert frontmatter.count("type: article") == 2
    assert frontmatter.count("0123456789") == 1
    assert frontmatter.count("abcdef1234") == 1
    # One footnote per unique source, numbered by catalog order
    assert "First block. [^1]" in content
    assert "Second block. [^2]" in content
    assert content.count("[^1]:") == 1


# ---------------------------------------------------------------------------
# 4. Canonical-only for new pages
# ---------------------------------------------------------------------------

def test_legacy_format_not_applied_to_new_pages():
    """New pages never use legacy string sources or ^[article:...] markers."""
    ev = _article("ev1", "0123456789", "Article A",
                  metadata={"context_blocks": [0]})
    pack = _pack(evidence=(ev,), context_blocks=("Body text.",))

    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content

    assert "^[article:" not in content
    assert "article:0123456789" not in content
    assert "type: article" in content
    assert "provenance:" in content
    assert "[^1]" in content


# ---------------------------------------------------------------------------
# 5. Web sources
# ---------------------------------------------------------------------------

def test_web_sources_included_in_canonical():
    """Web evidence becomes a typed web source with provenance tavily-web."""
    ev = _web("ev1", "https://example.com/repo", "Example README",
              metadata={"context_blocks": [0]})
    pack = _pack(evidence=(ev,), context_blocks=("Web body.",))

    sources = _build_canonical_frontmatter(pack, None, today=_TODAY)["sources"]
    assert len(sources) == 1
    entry = sources[0]
    assert entry["type"] == "web"
    assert entry["ref"] == "https://example.com/repo"
    assert entry["title"] == "Example README"
    assert entry["provenance"] == "tavily-web"

    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content
    assert 'ref: "https://example.com/repo"' in content
    assert "provenance: tavily-web" in content


# ---------------------------------------------------------------------------
# 6. Builtin source mapping
# ---------------------------------------------------------------------------

def test_builtin_source_mapping():
    """Builtin evidence maps to provenance=training-knowledge and omits ref."""
    ev = _builtin("ev1", "Opus 4.7 training corpus",
                  metadata={"context_blocks": [0]})
    pack = _pack(evidence=(ev,), context_blocks=("Builtin body.",))

    sources = _build_canonical_frontmatter(pack, None, today=_TODAY)["sources"]
    assert len(sources) == 1
    entry = sources[0]
    assert entry["type"] == "builtin"
    assert entry["provenance"] == "training-knowledge"
    assert "ref" not in entry
    assert entry["title"] == "Opus 4.7 training corpus"

    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content
    assert "type: builtin" in content
    assert "provenance: training-knowledge" in content


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------

def test_assemble_patch_deterministic():
    """Same inputs (including today) produce an identical WikiPatch."""
    ev1 = _article("ev1", "0123456789", "Article A",
                   metadata={"context_blocks": [0]})
    ev2 = _web("ev2", "https://example.com/x", "Web X",
               metadata={"context_blocks": [1]})
    pack = _pack(
        evidence=(ev1, ev2),
        context_blocks=("Block one.", "Block two."),
    )

    p1 = assemble_patch(pack, "concept", today=_TODAY)
    p2 = assemble_patch(pack, "concept", today=_TODAY)

    assert p1 == p2
    assert p1.patch_id == p2.patch_id
    assert p1.operations[0].content == p2.operations[0].content
    assert p1.created_at == p2.created_at


# ---------------------------------------------------------------------------
# 8. Operation selection
# ---------------------------------------------------------------------------

def test_create_vs_update_operation_selection():
    """No existing_page_path -> CREATE_PAGE; existing page -> UPSERT_SECTION
    (plus MERGE_SOURCES/SET_METADATA), never CREATE_PAGE."""
    ev = _article("ev1", "0123456789", "Article A",
                  metadata={"context_blocks": [0]})
    create_pack = _pack(evidence=(ev,), context_blocks=("Text.",))
    create_patch = assemble_patch(create_pack, "entity", today=_TODAY)
    assert [op.op for op in create_patch.operations] == ["CREATE_PAGE"]
    assert create_patch.base_digest is None

    update_pack = _pack(
        evidence=(ev,),
        context_blocks=("Text.",),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest="d" * 64,
    )
    update_patch = assemble_patch(update_pack, "entity", today=_TODAY)
    ops = {op.op for op in update_patch.operations}
    assert "CREATE_PAGE" not in ops
    assert "UPSERT_SECTION" in ops
    assert "MERGE_SOURCES" in ops
    assert "SET_METADATA" in ops
    assert update_patch.base_digest == "d" * 64
    assert update_patch.policy_hint == "suggestion_only"


# ---------------------------------------------------------------------------
# 9. confidence_level derivation
# ---------------------------------------------------------------------------

def test_confidence_level_derivation():
    """high = >=2 types; medium = single type, >=2 sources; low = sparse."""
    # high: two types
    mixed = _pack(
        evidence=(
            _article("e1", "0123456789", "A"),
            _web("e2", "https://example.com", "W"),
        ),
        context_blocks=("x",),
    )
    assert (
        assemble_patch(mixed, "entity", today=_TODAY)
        .operations[0].metadata["confidence_level"]
        == "high"
    )

    # medium: single type, two sources
    two_articles = _pack(
        evidence=(
            _article("e1", "0123456789", "A"),
            _article("e2", "abcdef1234", "B"),
        ),
        context_blocks=("x",),
    )
    assert (
        assemble_patch(two_articles, "entity", today=_TODAY)
        .operations[0].metadata["confidence_level"]
        == "medium"
    )

    # low: single source
    single = _pack(
        evidence=(_article("e1", "0123456789", "A"),),
        context_blocks=("x",),
    )
    assert (
        assemble_patch(single, "entity", today=_TODAY)
        .operations[0].metadata["confidence_level"]
        == "low"
    )

    # low: no sources at all
    empty = _pack(evidence=(), context_blocks=("x",))
    assert (
        assemble_patch(empty, "entity", today=_TODAY)
        .operations[0].metadata["confidence_level"]
        == "low"
    )


# ---------------------------------------------------------------------------
# 10. target path / slug mapping
# ---------------------------------------------------------------------------

def test_target_path_mapping_by_kind():
    """target_path follows kb/wiki/<subdir>/<slug>.md per target_kind."""
    ev = _article("e1", "0123456789", "A", metadata={"context_blocks": [0]})
    expected = {
        "entity": "kb/wiki/entities/",
        "concept": "kb/wiki/concepts/",
        "comparison": "kb/wiki/comparisons/",
        "query": "kb/wiki/queries/",
    }
    for kind, prefix in expected.items():
        patch = assemble_patch(
            _pack(evidence=(ev,), context_blocks=("t",)),
            kind,
            today=_TODAY,
        )
        assert patch.target_path == f"{prefix}test-subject.md"
        assert patch.target_slug == "test-subject"


def test_slugify_normalizes_names():
    assert _slugify("Some Subject!!") == "some-subject"
    assert _slugify("python/debugging") == "python-debugging"
    assert _slugify("  Agent  ") == "agent"
    assert _slugify("!!!") == "untitled"


# ---------------------------------------------------------------------------
# 11. Update ops: section targeting + metadata allowlist
# ---------------------------------------------------------------------------

def test_update_section_target_and_metadata_allowlist():
    """UPSERT_SECTION targets a named H2 (evidence override or default);
    SET_METADATA only touches last_updated/confidence_level."""
    ev = _article(
        "e1", "0123456789", "A",
        metadata={"context_blocks": [0], "section": "Architecture / Design"},
    )
    pack = _pack(
        evidence=(ev,),
        context_blocks=("New section body.",),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest="d" * 64,
    )
    patch = assemble_patch(pack, "entity", today=_TODAY)

    upsert = next(op for op in patch.operations if op.op == "UPSERT_SECTION")
    assert upsert.section == "Architecture / Design"
    assert upsert.content == "New section body. [^1]"

    set_meta = next(op for op in patch.operations if op.op == "SET_METADATA")
    assert set(set_meta.metadata.keys()) == {"last_updated", "confidence_level"}
    assert set_meta.metadata["last_updated"] == "2026-08-11"

    # default section when no override is supplied
    ev2 = _article("e2", "abcdef1234", "B", metadata={"context_blocks": [0]})
    pack2 = _pack(
        evidence=(ev2,),
        context_blocks=("Body.",),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest="d" * 64,
    )
    patch2 = assemble_patch(pack2, "entity", today=_TODAY)
    upsert2 = next(op for op in patch2.operations if op.op == "UPSERT_SECTION")
    assert upsert2.section == "Definition / Overview"

    # MERGE_SOURCES carries no inline content; sources ride on patch.evidence
    merge = next(op for op in patch.operations if op.op == "MERGE_SOURCES")
    assert merge.section is None
    assert merge.content is None
    assert patch.evidence == (ev,)


def test_update_without_blocks_has_no_upsert():
    """An update with no context blocks must not emit UPSERT_SECTION
    (no section deletion by empty replacement)."""
    ev = _article("e1", "0123456789", "A")
    pack = _pack(
        evidence=(ev,),
        context_blocks=(),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest="d" * 64,
    )
    patch = assemble_patch(pack, "entity", today=_TODAY)
    ops = {op.op for op in patch.operations}
    assert "UPSERT_SECTION" not in ops
    assert "MERGE_SOURCES" in ops
    assert "SET_METADATA" in ops


def test_update_requires_digest():
    """An update pack without a base digest is rejected, as are
    packs with a digest but no existing page path."""
    ev = _article("e1", "0123456789", "A", metadata={"context_blocks": [0]})
    bad1 = _pack(
        evidence=(ev,),
        context_blocks=("t",),
        existing_page_path="kb/wiki/entities/test-subject.md",
        existing_page_digest=None,
    )
    with pytest.raises(ValueError):
        assemble_patch(bad1, "entity", today=_TODAY)

    bad2 = _pack(
        evidence=(ev,),
        context_blocks=("t",),
        existing_page_path=None,
        existing_page_digest="d" * 64,
    )
    with pytest.raises(ValueError):
        assemble_patch(bad2, "entity", today=_TODAY)


# ---------------------------------------------------------------------------
# 12. dry_run / policy hint
# ---------------------------------------------------------------------------

def test_dry_run_marks_suggestion_only():
    ev = _article("e1", "0123456789", "A", metadata={"context_blocks": [0]})
    pack = _pack(evidence=(ev,), context_blocks=("t",))

    patch = assemble_patch(pack, "entity", today=_TODAY, dry_run=True)
    assert patch.policy_hint == "suggestion_only"
    assert "[dry run]" in patch.reason.lower()

    patch = assemble_patch(pack, "entity", today=_TODAY, dry_run=False)
    assert patch.policy_hint == "auto_apply"


# ---------------------------------------------------------------------------
# 13. positional citation fallback + references helper
# ---------------------------------------------------------------------------

def test_positional_citation_fallback():
    """Without context_blocks metadata, block i cites source i; blocks beyond
    the catalog carry no citation."""
    ev = _article("e1", "0123456789", "A")
    pack = _pack(evidence=(ev,), context_blocks=("One.", "Two."))
    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content

    assert "One. [^1]" in content
    assert "Two." in content
    assert "Two. [^" not in content


def test_references_section_lists_all_sources():
    sources = [
        {"type": "article", "ref": "0123456789", "title": "Article A",
         "provenance": "lightrag-corpus"},
        {"type": "builtin", "title": "Builtin B",
         "provenance": "training-knowledge"},
    ]
    refs = _build_references_section(sources)
    assert refs.startswith("## References")
    assert "[^1]:" in refs and "Article A" in refs and "0123456789" in refs
    assert "[^2]:" in refs and "Builtin B" in refs


# ---------------------------------------------------------------------------
# 14. SCHEMA.md `id` emission (adversarial review MAJOR finding)
# ---------------------------------------------------------------------------

def test_sources_entries_emit_positional_id():
    """SCHEMA.md §1 requires each sources[] item to carry an integer `id`
    (>=1, unique per page, referenced inline as [^id]). The rendered
    frontmatter must put `id` FIRST in every entry, matching the footnote
    number."""
    import frontmatter

    ev_article = _article("ev1", "0123456789", "Article A")
    ev_web = _web("ev2", "https://example.com/source", "Web Source")
    pack = _pack(evidence=(ev_article, ev_web), context_blocks=("a", "b"))
    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content

    frontmatter_text = content.split("---", 2)[1]
    assert "  - id: 1" in frontmatter_text
    assert "  - id: 2" in frontmatter_text
    # id is the FIRST key of each entry (before type)
    assert frontmatter_text.index("  - id: 1") < frontmatter_text.index("    type: article")
    assert frontmatter_text.index("  - id: 2") < frontmatter_text.index("    type: web")

    post = frontmatter.loads(content)
    sources = post.metadata["sources"]
    assert [s["id"] for s in sources] == [1, 2]
    assert [s["type"] for s in sources] == ["article", "web"]
    assert [s["ref"] for s in sources] == ["0123456789", "https://example.com/source"]


def test_rendered_page_passes_lint_citation_integrity(tmp_path: Path):
    """A W5A-rendered canonical page must satisfy the surviving W3 lint:
    every [^N] citation resolves to a frontmatter sources[].id, and
    type=article refs resolve in the corpus. Regression for the adversarial
    review MAJOR finding (id-less pages fail every citation)."""
    from kb.wiki_lint import lint_citation_integrity

    ev = _article("ev1", "0123456789", "Article A",
                  metadata={"context_blocks": [0]})
    pack = _pack(evidence=(ev,), context_blocks=("Article paragraph.",))
    content = assemble_patch(pack, "entity", today=_TODAY).operations[0].content

    page = tmp_path / "page.md"
    page.write_text(content, encoding="utf-8")
    failures = lint_citation_integrity(page, known_article_hashes={"0123456789"})
    assert failures == [], (
        f"rendered canonical page must pass citation lint: {failures}"
    )
