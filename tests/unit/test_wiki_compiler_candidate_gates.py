"""W5A GAP 1 behavior anchors: final candidate validation gates in apply_patch.

The shared apply path (``kb.wiki_compiler.engine.apply_patch``) must run
FINAL CANDIDATE VALIDATION on the assembled candidate BEFORE any
authoritative page write (design §7 apply flow: "assemble candidate ->
final validation -> atomic tempfile + replace").

Gate policy (documented decision, design §7 validation order 6-8 + §10):
- BLOCKING (reject, no write, Error Book with patch provenance):
    * candidate frontmatter parse failure (order 6) — malformed YAML cannot
      be written; wiki_health ``check_yaml_validity`` also treats it as
      ERROR.
    * citation integrity failures (order 7) via
      ``kb.wiki_lint.lint_citation_integrity`` — an ``[^N]`` whose id is not
      in frontmatter ``sources[]``, an unknown source type, or an
      article ref not in the known corpus. wiki_health
      ``check_citations`` treats "id not in sources[]" as ERROR; §10
      "candidate health/lint ERROR -> reject".
- WARN (recorded on the result dict, NEVER blocking): broken wikilinks
  (order 8, "wikilink validity under existing policy"). The repo's current
  policy — scripts/wiki_health.py ``check_wikilinks`` — appends broken
  backlinks to ``findings["warns"]`` (exit code 2 = WARNs only; the wiki
  carries ~185 pre-existing such warnings). §10 "candidate WARN only ->
  conservative policy; no silent promotion" therefore means: apply
  proceeds, the warning is recorded. DEVIATION NOTE (master review):
  the master review phrased "CREATE_PAGE with broken wikilink cannot
  apply under current policy"; that contradicts the actual current
  policy above, so this suite asserts the conservative WARN behavior
  (apply + recorded warning), not blocking. Deliberate, documented, and
  matching wiki_health — NOT a silent weakening.
- Contradiction/staleness checks (order 9-10) are not run on auto-apply
  candidates: the candidate is fresh by construction (``last_updated`` is
  being written now), and LLM-semantic contradiction review is deferred
  to W5B (``kb.wiki_lint`` module docstring).

RED/GREEN anchors: tests 1, 2, 4, 5 fail against the no-gate engine
(they prove the gates); tests 3 and 6 are regression guards that must
stay green (prove the gates do not over-block the UAT-good shapes).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.wiki_compiler.models import (
    EvidenceRef,
    PatchOperation,
    WikiPatch,
)

_EPOCH = "2026-08-11T00:00:00Z"

# UAT-good canonical CREATE_PAGE shape: typed sources WITH positional ids
# (SCHEMA.md §1), every [^N] resolvable to a sources[] entry, every article
# ref present in the patch evidence (the known corpus), no broken backlinks.
_CANONICAL_PAGE = """---
title: 'Test Entity'
created: '2026-08-11'
last_updated: '2026-08-11'
sources:
  - id: 1
    type: article
    ref: 'aaaaaaaaaa'
    title: 'Src A'
    provenance: lightrag-corpus
  - id: 2
    type: web
    ref: 'https://example.com/docs'
    title: 'Web Docs'
    provenance: tavily-web
confidence_level: medium
---

# Test Entity

Fresh body paragraph [^1][^2]

## References

[^1]: **Src A** — aaaaaaaaaa (lightrag-corpus)
[^2]: **Web Docs** — https://example.com/docs (tavily-web)
"""

# Same shape, but the cited article ref ('deadbeef00') is NOT in the
# patch's evidence-known hashes -> citation integrity failure (BLOCKING).
_BROKEN_CITATION_PAGE = """---
title: 'Broken Cite'
created: '2026-08-11'
last_updated: '2026-08-11'
sources:
  - id: 1
    type: article
    ref: 'deadbeef00'
    title: 'Unresolved Src'
    provenance: lightrag-corpus
confidence_level: low
---

# Broken Cite

Body cites an article the compiler does not know [^1]

## References

[^1]: **Unresolved Src** — deadbeef00 (lightrag-corpus)
"""

# Valid citations + one broken wikilink -> WARN policy: still applies,
# warning recorded.
_BROKEN_WIKILINK_PAGE = """---
title: 'Linky'
created: '2026-08-11'
last_updated: '2026-08-11'
sources:
  - id: 1
    type: article
    ref: 'aaaaaaaaaa'
    title: 'Src A'
    provenance: lightrag-corpus
confidence_level: low
---

# Linky

Fresh body paragraph [^1]

See [[no-such-entity]] for more.

## References

[^1]: **Src A** — aaaaaaaaaa (lightrag-corpus)
"""


def _make_patch(
    *,
    slug: str,
    content: str,
    evidence: tuple,
    patch_id: str | None = None,
) -> WikiPatch:
    """Build a valid CREATE_PAGE WikiPatch (auto_apply policy)."""
    return WikiPatch(
        patch_schema_version=1,
        patch_id=patch_id or f"wpatch-gate-{slug.replace('/', '-')[:12]}",
        target_slug=slug,
        target_path=f"kb/wiki/entities/{slug}.md",
        target_kind="entity",
        base_digest=None,
        trigger="test",
        evidence_pack_id="pack-1",
        operations=(
            PatchOperation(
                op="CREATE_PAGE", section=None, content=content, metadata={},
            ),
        ),
        evidence=evidence,
        policy_hint="auto_apply",
        reason="candidate gate test",
        created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )


def _article(ref: str, evidence_id: str = "e1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id, type="article", ref=ref,
        title="Src", provenance="lightrag-corpus", metadata={},
    )


@pytest.fixture
def wiki_root(tmp_path: Path) -> Path:
    """Repo-shaped tmp wiki root (kb/wiki/{entities,_suggestions,.locks})."""
    root = tmp_path / "repo"
    (root / "kb" / "wiki" / "entities").mkdir(parents=True)
    (root / "kb" / "wiki" / "_suggestions").mkdir(parents=True)
    return root


def _target(wiki_root: Path, slug: str) -> Path:
    return wiki_root / "kb" / "wiki" / "entities" / f"{slug}.md"


# ---------------------------------------------------------------------------
# 1. BLOCKING: unresolved article citation -> rejected, page never written
# ---------------------------------------------------------------------------

def test_create_page_unresolved_article_citation_rejected(wiki_root: Path):
    """CREATE_PAGE whose [^1] cites an article ref NOT in the evidence-known
    hashes must be REJECTED before any write (design §7 order 7)."""
    from kb.wiki_compiler.engine import apply_patch

    patch = _make_patch(
        slug="broken-cite",
        content=_BROKEN_CITATION_PAGE,
        evidence=(_article("aaaaaaaaaa"),),  # corpus knows aaaaaaaaaa only
        patch_id="wpatch-gate-badcite",
    )
    result = apply_patch(patch, wiki_root)

    assert result["status"] == "rejected", result
    assert result["error"] is not None
    assert "not in corpus" in result["error"]
    # The authoritative write must never have happened.
    assert not _target(wiki_root, "broken-cite").exists()


# ---------------------------------------------------------------------------
# 2. WARN (current policy): broken wikilink -> still applies, warning recorded
# ---------------------------------------------------------------------------

def test_create_page_broken_wikilink_warn_policy_applies(wiki_root: Path):
    """Broken [[wikilink]] is WARN under the repo's current policy
    (scripts/wiki_health.py check_wikilinks -> warns, exit 2; ~185
    pre-existing warnings). Design §7 order 8 "under existing policy" +
    §10 "candidate WARN only -> conservative policy; no silent promotion":
    the page still applies and the warning is recorded on the result.

    DEVIATION NOTE: the master review phrased this as blocking ("CREATE_PAGE
    with broken wikilink cannot apply under current policy"); that does not
    match the repo's actual current policy (wiki_health warns), so the
    conservative WARN behavior is asserted here and documented — blocking
    would contradict existing policy, not enforce it."""
    from kb.wiki_compiler.engine import apply_patch

    patch = _make_patch(
        slug="linky",
        content=_BROKEN_WIKILINK_PAGE,
        evidence=(_article("aaaaaaaaaa"),),
        patch_id="wpatch-gate-wikilink",
    )
    result = apply_patch(patch, wiki_root)

    assert result["status"] == "applied", result
    assert result["error"] is None
    assert _target(wiki_root, "linky").exists()
    # WARN channel: additive "warnings" list on the result dict.
    assert result.get("warnings"), "broken wikilink must be recorded as WARN"
    assert any(
        "no-such-entity" in w and "broken wikilink" in w
        for w in result["warnings"]
    ), result["warnings"]


# ---------------------------------------------------------------------------
# 3. Guard: valid canonical CREATE_PAGE still auto-applies
# ---------------------------------------------------------------------------

def test_create_page_valid_canonical_still_applies(wiki_root: Path):
    """UAT-good canonical CREATE_PAGE (typed sources with ids, [^N] refs all
    in evidence-known hashes, no broken backlinks) must still auto-apply."""
    from kb.wiki_compiler.engine import apply_patch

    patch = _make_patch(
        slug="test-entity",
        content=_CANONICAL_PAGE,
        evidence=(_article("aaaaaaaaaa"),),
        patch_id="wpatch-gate-canonical",
    )
    result = apply_patch(patch, wiki_root)

    assert result["status"] == "applied", result
    assert result["error"] is None
    assert result["warnings"] == []
    assert _target(wiki_root, "test-entity").exists()
    assert _target(wiki_root, "test-entity").read_text(encoding="utf-8") == _CANONICAL_PAGE


# ---------------------------------------------------------------------------
# 4. Blocking failure happens BEFORE the write: no target, no leftovers
# ---------------------------------------------------------------------------

def test_blocking_failure_leaves_no_target_or_temp_leftovers(wiki_root: Path):
    """A rejected candidate must leave the target absent and no temp /
    candidate-check artifacts behind. (The persistent .md.lock file itself
    is a git-ignored runtime artifact and remains by design.)"""
    from kb.wiki_compiler.engine import apply_patch

    patch = _make_patch(
        slug="broken-cite",
        content=_BROKEN_CITATION_PAGE,
        evidence=(_article("aaaaaaaaaa"),),
        patch_id="wpatch-gate-noleftover",
    )
    result = apply_patch(patch, wiki_root)
    assert result["status"] == "rejected"

    assert not _target(wiki_root, "broken-cite").exists()
    entities_dir = wiki_root / "kb" / "wiki" / "entities"
    assert [p.name for p in entities_dir.iterdir()] == []
    # No candidate-check temp dirs anywhere under the wiki root.
    leftovers = [
        p for p in (wiki_root / "kb" / "wiki").rglob("*")
        if p.name.startswith(".candidate-check-") or p.name.endswith(".tmp")
    ]
    assert leftovers == [], f"leftover temp artifacts: {leftovers}"
    # .locks holds only the persistent per-page lock artifact (by design).
    locks = list((wiki_root / "kb" / "wiki" / ".locks").glob("*"))
    assert [p.name for p in locks] == ["broken-cite.md.lock"], locks


# ---------------------------------------------------------------------------
# 5. Error Book receives the integrity failure with patch provenance
# ---------------------------------------------------------------------------

def test_error_book_records_candidate_integrity_failure(wiki_root: Path):
    """A blocking candidate-integrity failure is recorded in the Error Book
    via the existing channel with patch provenance (design §7: "recorded in
    the existing Error Book with patch provenance")."""
    from kb.wiki_compiler.engine import apply_patch

    calls = []
    recorder = lambda failure: calls.append(failure)  # noqa: E731
    patch = _make_patch(
        slug="broken-cite",
        content=_BROKEN_CITATION_PAGE,
        evidence=(_article("aaaaaaaaaa"),),
        patch_id="wpatch-gate-eb",
    )
    result = apply_patch(patch, wiki_root, error_book=recorder)

    assert result["status"] == "rejected"
    assert len(calls) == 1, f"expected exactly one Error Book entry: {calls}"
    entry = calls[0]
    assert entry["lint_name"] == "wiki_compiler:candidate_integrity"
    assert entry["patch_id"] == "wpatch-gate-eb"
    assert entry["page_path"].endswith("broken-cite.md")
    assert any("not in corpus" in f for f in entry["failures"]), entry["failures"]


# ---------------------------------------------------------------------------
# 6. Guard: existing W5A UAT-good fixture shape still passes the gates
# ---------------------------------------------------------------------------

def test_uat_good_engine_fixture_shape_still_applies(wiki_root: Path):
    """The UAT-good CREATE_PAGE shape used by the existing engine suite
    (tests/unit/test_wiki_compiler_engine.py _PAGE_CONTENT, canonical
    typed sources with id, single [^1] resolved in evidence) must still
    auto-apply under the new gates — regression guard for the shared
    auto-apply path."""
    from kb.wiki_compiler.engine import apply_patch

    page = """---
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
    patch = _make_patch(
        slug="python-debugging",
        content=page,
        evidence=(_article("abcdef1234"),),
        patch_id="wpatch-gate-uatgood",
    )
    result = apply_patch(patch, wiki_root)

    assert result["status"] == "applied", result
    assert result["error"] is None
    assert result["warnings"] == []
    assert _target(wiki_root, "python-debugging").exists()
