"""kb.wiki_compiler.models — Typed patch compiler models.

Frozen dataclasses for representing evidence references, evidence packs,
patch operations, and wiki patches. Each model validates its invariants
in ``__post_init__``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TARGET_KINDS = frozenset({"entity", "concept", "comparison", "query"})
VALID_OPERATIONS = frozenset(
    {"CREATE_PAGE", "UPSERT_SECTION", "MERGE_SOURCES", "SET_METADATA"}
)
VALID_POLICY_HINTS = frozenset({"auto_apply", "suggestion_only"})
VALID_EVIDENCE_TYPES = frozenset({"article", "web", "builtin"})
SCHEMA_VERSION = 1
PATCH_ID_PREFIX = "wpatch-"
ARTICLE_REF_PATTERN = r"^[a-f0-9]{10}$"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def page_digest(text: str) -> str:
    """Return SHA-256 hex digest over UTF-8 bytes of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_patch_id(*, target_slug: str, evidence_pack_id: str, operations: tuple) -> str:
    """Deterministic canonical ID for a set of patch inputs.

    Produces ``wpatch-`` + 16 hex chars from SHA-256 of a canonical
    JSON representation with sorted keys and compact separators.
    """
    ops_json = json.dumps(
        [{"op": o.op, "section": o.section, "content": o.content, "metadata": o.metadata} for o in operations],
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = {
        "evidence_pack_id": evidence_pack_id,
        "operations": ops_json,
        "target_slug": target_slug,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return PATCH_ID_PREFIX + h[:16]


# ---------------------------------------------------------------------------
# EvidenceRef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRef:
    """A single piece of evidence referenced by a patch.

    Attributes:
        evidence_id: Unique identifier for this evidence entry.
        type: One of ``article``, ``web``, or ``builtin``.
        ref: Source reference string.  Must be a 10-char lowercase-hex
             string when ``type == "article"``; may be ``None`` for other
             types.
        title: Human-readable label.
        provenance: Where this evidence came from.
        metadata: Arbitrary key-value pairs attached to the evidence.
    """

    evidence_id: str
    type: str
    ref: Optional[str]
    title: str
    provenance: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate type
        if self.type not in VALID_EVIDENCE_TYPES:
            raise ValueError(
                f"EvidenceRef type must be one of {VALID_EVIDENCE_TYPES}, got {self.type!r}"
            )
        # Validate ref
        if self.type == "article":
            if not isinstance(self.ref, str):
                raise ValueError(
                    f"EvidenceRef of type 'article' requires ref='string', got {self.ref!r}"
                )
            import re
            if not re.match(ARTICLE_REF_PATTERN, self.ref):
                raise ValueError(
                    f"Article EvidenceRef ref must match [a-f0-9]{{10}}, got {self.ref!r}"
                )


# ---------------------------------------------------------------------------
# EvidencePack
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidencePack:
    """An immutable collection of evidence and context bundled together.

    Attributes:
        pack_id: Unique identifier for this evidence pack.
        subject_slug: Slug identifying the wiki page / concept being compiled.
        subject_title: Human-readable title.
        trigger: What triggered this compilation.
        article_hashes: Immutable sequence of article hash strings.
        evidence: Immutable sequence of :class:`EvidenceRef`.
        context_blocks: Immutable sequence of raw text context blocks.
        existing_page_path: Path to an existing page being updated, or ``None``.
        existing_page_digest: SHA-256 digest of existing page, or ``None``.
        created_at: ISO-8601 timestamp.
        compiler_version: Version string of the compiler that produced this.
    """

    pack_id: str
    subject_slug: str
    subject_title: str
    trigger: str
    article_hashes: Tuple[str, ...]
    evidence: Tuple[EvidenceRef, ...]
    context_blocks: Tuple[str, ...]
    existing_page_path: Optional[str]
    existing_page_digest: Optional[str]
    created_at: str
    compiler_version: str


# ---------------------------------------------------------------------------
# PatchOperation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatchOperation:
    """A single atomic operation within a :class:`WikiPatch`.

    Attributes:
        op: The kind of patch operation.
        section: Target section name (for UPSERT_SECTION).
        content: New content string.
        metadata: Operation-specific metadata override dict.
    """

    op: str
    section: Optional[str]
    content: Optional[str]
    metadata: Optional[Dict[str, Any]]

    def __post_init__(self) -> None:
        if self.op not in VALID_OPERATIONS:
            raise ValueError(
                f"PatchOperation op must be one of {VALID_OPERATIONS}, got {self.op!r}"
            )


# ---------------------------------------------------------------------------
# WikiPatch
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WikiPatch:
    """A typed description of changes to apply to a wiki page.

    Attributes:
        patch_schema_version: Schema version number (currently always ``1``).
        patch_id: Deterministic identity generated via :func:`stable_patch_id`.
        target_slug: Wiki URL slug of the affected entity/page.
        target_path: On-disk path where the resulting markdown will live.
        target_kind: Category of the target entity.
        base_digest: SHA-256 of the current page content (``None`` for creates).
        trigger: What triggered this patch creation.
        evidence_pack_id: Reference to the :class:`EvidencePack` backing this patch.
        operations: Ordered list of :class:`PatchOperation` instances.
        evidence: Flattened evidence references used during compilation.
        policy_hint: How downstream agents should handle this patch.
        reason: Human-readable explanation of why this patch was created.
        created_at: ISO-8601 timestamp.
        compiler_version: Version of the compiler that produced this patch.
    """

    patch_schema_version: int
    patch_id: str
    target_slug: str
    target_path: str
    target_kind: str
    base_digest: Optional[str]
    trigger: str
    evidence_pack_id: str
    operations: Tuple[PatchOperation, ...]
    evidence: Tuple[EvidenceRef, ...]
    policy_hint: str
    reason: str
    created_at: str
    compiler_version: str

    def __post_init__(self) -> None:
        # 1. Schema version must be exactly 1
        if self.patch_schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"patch_schema_version must be {SCHEMA_VERSION}, got {self.patch_schema_version}"
            )

        # 2. target_path validations
        if ".." in self.target_path:
            raise ValueError(f"target_path must not contain '..': {self.target_path!r}")
        if self.target_path.startswith("/"):
            raise ValueError(f"target_path must not be absolute: {self.target_path!r}")
        if not self.target_path.endswith(".md"):
            raise ValueError(
                f"target_path must end with '.md': {self.target_path!r}"
            )

        # 3. target_kind validation
        if self.target_kind not in VALID_TARGET_KINDS:
            raise ValueError(
                f"target_kind must be one of {VALID_TARGET_KINDS}, got {self.target_kind!r}"
            )

        # 4. Operation validation
        for i, op in enumerate(self.operations):
            if op.op not in VALID_OPERATIONS:
                raise ValueError(
                    f"operations[{i}] op must be one of {VALID_OPERATIONS}, got {op.op!r}"
                )

        # 5. Article EvidenceRef ref validation (already validated in EvidenceRef,
        #    but we re-validate here for extra safety)
        for ev in self.evidence:
            if ev.type == "article" and ev.ref is not None:
                import re
                if not re.match(ARTICLE_REF_PATTERN, ev.ref):
                    raise ValueError(
                        f"EvidenceRef in article type must have ref matching [a-f0-9]{{10}}, got {ev.ref!r}"
                    )

        # 6. CREATE_PAGE must have null base_digest
        first_op = self.operations[0] if self.operations else None
        if first_op is not None and first_op.op == "CREATE_PAGE":
            if self.base_digest is not None:
                raise ValueError(
                    "CREATE_PAGE operation must have base_digest=None"
                )
        elif self.base_digest is None and self.operations:
            # Non-CREATE_PAGE (update) must have non-null base_digest
            op_label = first_op.op if first_op else "no operations"
            raise ValueError(
                f"Non-CREATE_PAGE patch ({op_label!r}) must have non-null base_digest"
            )

    # -----------------------------------------------------------------------
    # Serialization helpers
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this WikiPatch to a plain dict (JSON-safe)."""
        d = asdict(self)
        # Convert tuples to lists for JSON compatibility
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> WikiPatch:
        """Deserialize a WikiPatch from a plain dict.

        Handles both JSON-deserialized dicts (all nested objects are dicts/lists)
        and partial conversions (some fields may already be objects).
        """
        def _to_tuple_of_ops(v):
            if isinstance(v, list):
                return tuple(_make_op(o) for o in v)
            elif isinstance(v, tuple):
                return tuple(_make_op(o) for o in v)
            return v

        def _make_op(o):
            """Convert a dict or existing PatchOperation to PatchOperation."""
            if isinstance(o, dict):
                md = o.get("metadata")
                if md is None and o.get("op") in ("CREATE_PAGE", "UPSERT_SECTION"):
                    md = {}
                return PatchOperation(
                    op=o["op"],
                    section=o.get("section"),
                    content=o.get("content"),
                    metadata=md,
                )
            # Already a PatchOperation
            return o

        def _make_ev(e):
            """Convert a dict or existing EvidenceRef to EvidenceRef."""
            if isinstance(e, dict):
                return EvidenceRef(
                    evidence_id=e["evidence_id"],
                    type=e["type"],
                    ref=e.get("ref"),
                    title=e["title"],
                    provenance=e["provenance"],
                    metadata=e.get("metadata", {}),
                )
            # Already an EvidenceRef
            return e

        obj_d = {}
        for key, value in d.items():
            if key == "operations":
                obj_d[key] = _to_tuple_of_ops(value)
            elif key == "evidence":
                if isinstance(value, (list, tuple)):
                    obj_d[key] = tuple(_make_ev(e) for e in value)
                else:
                    obj_d[key] = value
            elif key in ("article_hashes", "context_blocks"):
                if isinstance(value, (list, tuple)):
                    obj_d[key] = tuple(value)
                else:
                    obj_d[key] = value
            else:
                obj_d[key] = value
        return cls(**obj_d)
