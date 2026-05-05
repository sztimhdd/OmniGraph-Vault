"""Unit tests for `ingest_wechat._status_is_processed`.

Regression target: pre-fix, `str(DocStatus.PROCESSED).upper() == "PROCESSED"`
returned False on Python 3.10 because `str(member)` produced
``"DocStatus.PROCESSED"`` rather than ``"processed"``. The fix uses
`.value` (always ``"processed"``) so the comparison succeeds regardless of
Python version.
"""
from __future__ import annotations

from enum import Enum

import pytest

from ingest_wechat import _status_is_processed


class _FakeDocStatus(str, Enum):
    """Mirror of `lightrag.base.DocStatus` shape (str, Enum)."""

    PROCESSED = "processed"
    PENDING = "pending"
    FAILED = "failed"


def test_accepts_str_enum_member_processed():
    """Primary regression: enum member should be recognised as PROCESSED."""
    assert _status_is_processed(_FakeDocStatus.PROCESSED) is True


def test_rejects_str_enum_member_pending():
    """Other enum members should NOT be treated as PROCESSED."""
    assert _status_is_processed(_FakeDocStatus.PENDING) is False


def test_accepts_lowercase_string_processed():
    """Backward compat: plain string ``"processed"`` (older serialised form)."""
    assert _status_is_processed("processed") is True


def test_accepts_uppercase_string_processed():
    """Defensive: ``"PROCESSED"`` already-upper string."""
    assert _status_is_processed("PROCESSED") is True


def test_rejects_unrelated_string():
    """A non-status value must not slip through."""
    assert _status_is_processed("something-else") is False


def test_rejects_none():
    """None means status missing — must NOT be treated as PROCESSED."""
    assert _status_is_processed(None) is False


def test_handles_object_without_value_attr():
    """Edge: a non-enum object with no ``.value`` falls back to ``str()``."""

    class _Dummy:
        def __str__(self) -> str:
            return "processed"

    assert _status_is_processed(_Dummy()) is True


def test_handles_empty_string():
    """Empty string is not PROCESSED."""
    assert _status_is_processed("") is False
