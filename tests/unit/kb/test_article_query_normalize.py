"""Unit tests for _normalize_rss_update_time — quick task 260514-av8.

Closes the cross-source merge-sort bug where RSS published_at in RFC 822 form
('Wed, 02 May 2026 ...') sorted lexically ahead of KOL ISO-8601 timestamps,
pushing KOL articles past list_articles() limit. The helper normalizes published_at
to ISO-8601 (pass-through or RFC 822 → ISO) with fetched_at fallback.
"""
from __future__ import annotations

import pytest

from kb.data.article_query import _normalize_rss_update_time


class TestNormalizeRssUpdateTime:
    """Coverage for the four input branches + sort-correctness invariant."""

    def test_iso_8601_pass_through(self):
        """published_at already ISO → returned verbatim."""
        result = _normalize_rss_update_time(
            "2026-05-02T17:26:40+00:00", "2026-05-03 00:11:59"
        )
        assert result == "2026-05-02T17:26:40+00:00"

    def test_rfc_822_parsed_to_iso(self):
        """published_at RFC 822 → ISO-8601 string."""
        result = _normalize_rss_update_time(
            "Wed, 02 May 2026 17:26:40 +0000", "2026-05-03 00:11:59"
        )
        assert result.startswith("2026-05-02")
        assert "T" in result  # ISO marker
        assert result[:1].isdigit()  # critical sort-correctness invariant

    def test_rfc_822_various_weekdays(self):
        """All RFC 822 weekday prefixes parse correctly (regression: lex-sort bias)."""
        for weekday in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            raw = f"{weekday}, 02 May 2026 17:26:40 +0000"
            result = _normalize_rss_update_time(raw, "fallback")
            assert result.startswith("2026-05-02"), f"{weekday} failed: {result!r}"
            assert result[:1].isdigit()

    def test_rfc_822_no_weekday_prefix(self):
        """RFC 822 without optional day-of-week (digit-leading) parses, not pass-through.

        Regression guard: the looser `published_at[:1].isdigit()` heuristic let strings
        like '7 Aug 2017 01:08:45 +0000' through as ISO, breaking the merge sort.
        """
        result = _normalize_rss_update_time("7 Aug 2017 01:08:45 +0000", "fallback")
        assert result.startswith("2017-08-07"), f"unexpected: {result!r}"
        assert "T" in result

    def test_rfc_822_uppercase_uniform_time(self):
        """RFC 822 with 'UT' zone designator (legacy, found in some feeds)."""
        result = _normalize_rss_update_time("29 Mar 2026 00:00:00 UT", "fallback")
        assert result.startswith("2026-03-29"), f"unexpected: {result!r}"

    def test_unparseable_published_at_falls_back_to_fetched_at(self):
        """Garbage published_at → fetched_at returned."""
        result = _normalize_rss_update_time("not a date", "2026-05-03 00:11:59")
        assert result == "2026-05-03 00:11:59"

    def test_empty_published_at_falls_back_to_fetched_at(self):
        result = _normalize_rss_update_time("", "2026-05-03 00:11:59")
        assert result == "2026-05-03 00:11:59"

    def test_none_published_at_falls_back_to_fetched_at(self):
        result = _normalize_rss_update_time(None, "2026-05-03 00:11:59")
        assert result == "2026-05-03 00:11:59"

    def test_both_empty_returns_empty_string(self):
        assert _normalize_rss_update_time(None, None) == ""
        assert _normalize_rss_update_time("", "") == ""
        assert _normalize_rss_update_time(None, "") == ""

    def test_unparseable_published_at_with_no_fetched_at_returns_empty(self):
        assert _normalize_rss_update_time("garbage", None) == ""
        assert _normalize_rss_update_time("garbage", "") == ""

    def test_sort_correctness_against_kol_iso(self):
        """Sort invariant: a KOL ISO timestamp interleaves correctly with RSS RFC 822."""
        kol_iso = "2026-05-02T18:00:00+00:00"
        rss_normalized = _normalize_rss_update_time(
            "Wed, 02 May 2026 17:26:40 +0000", None
        )
        # DESC lex-sort (used by list_articles line 186): kol_iso > rss_normalized
        assert kol_iso > rss_normalized, (
            f"KOL {kol_iso!r} should sort ahead of RSS {rss_normalized!r} in DESC, "
            "but failed — merge-sort regression!"
        )

    def test_sort_correctness_rss_iso_pass_through(self):
        """When published_at is already ISO, sort comparison stays correct."""
        kol_iso = "2026-05-02T18:00:00+00:00"
        rss_iso = _normalize_rss_update_time("2026-05-02T17:26:40+00:00", None)
        assert kol_iso > rss_iso  # 18:00 after 17:26


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
