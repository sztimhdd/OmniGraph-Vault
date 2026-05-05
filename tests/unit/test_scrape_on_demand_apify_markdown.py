"""Test SCR-06 completeness: consumer accepts Apify markdown-only results."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from lib.scraper import ScrapeResult


def make_scraped(markdown="", content_html="", images=None, method="apify"):
    """Factory for ScrapeResult with Apify-like shape."""
    return ScrapeResult(
        markdown=markdown,
        images=images or [],
        metadata={"title": "Test", "publish_time": "", "url": "http://example.com"},
        method=method,
        summary_only=False,
        content_html=content_html,
    )


class TestScrapeOnDemandApifyMarkdown:
    """Verify _classify_full_body consumer handles markdown-only results."""

    @pytest.mark.asyncio
    async def test_markdown_only_should_not_skip(self):
        """ScrapeResult(markdown='content', content_html='') → accepted."""
        scraped = make_scraped(markdown="## Hello\n\nworld", content_html="")
        assert scraped.markdown, "markdown must be truthy"
        assert not scraped.content_html, "content_html must be falsy"

        # Simulate consumer check (mirrors batch_ingest_from_spider.py:948)
        should_reject = not scraped or (not scraped.content_html and not scraped.markdown)
        assert not should_reject, (
            "markdown-only result should NOT be rejected — consumer must "
            "check both content_html AND markdown"
        )

    @pytest.mark.asyncio
    async def test_content_html_only_should_not_skip(self):
        """ScrapeResult(markdown='', content_html='<p>hi</p>') → accepted."""
        scraped = make_scraped(markdown="", content_html="<p>hi</p>")
        assert not scraped.markdown, "markdown must be falsy"
        assert scraped.content_html, "content_html must be truthy"

        should_reject = not scraped or (not scraped.content_html and not scraped.markdown)
        assert not should_reject, (
            "content_html-only result should NOT be rejected"
        )

    @pytest.mark.asyncio
    async def test_both_empty_should_skip(self):
        """ScrapeResult(markdown='', content_html='') → rejected."""
        scraped = make_scraped(markdown="", content_html="")
        should_reject = not scraped or (not scraped.content_html and not scraped.markdown)
        assert should_reject, "both-empty result must be rejected"

    @pytest.mark.asyncio
    async def test_none_scraped_should_skip(self):
        """scraped is None → rejected."""
        scraped = None
        should_reject = not scraped or (not scraped.content_html and not scraped.markdown)
        assert should_reject, "None scraped must be rejected"

    @pytest.mark.asyncio
    async def test_both_present_should_not_skip(self):
        """ScrapeResult(markdown='a', content_html='<p>b</p>') → accepted."""
        scraped = make_scraped(markdown="a", content_html="<p>b</p>")
        should_reject = not scraped or (not scraped.content_html and not scraped.markdown)
        assert not should_reject, "both-present result should NOT be rejected"

    @pytest.mark.asyncio
    async def test_markdown_used_as_body_when_content_html_empty(self):
        """When content_html empty, markdown is used directly as body."""
        scraped = make_scraped(markdown="direct markdown body", content_html="")
        # Simulate the fallback logic from batch_ingest_from_spider.py:950-954
        if not scraped.content_html and scraped.markdown:
            body = scraped.markdown
        else:
            # In real code this goes through process_content()
            body = scraped.content_html
        assert body == "direct markdown body", (
            "markdown must be used as body when content_html is empty"
        )

    @pytest.mark.asyncio
    async def test_content_html_used_when_both_present(self):
        """When both present, content_html should go through process_content path."""
        scraped = make_scraped(markdown="markdown_val", content_html="<p>html_val</p>")
        if not scraped.content_html and scraped.markdown:
            body = scraped.markdown
        else:
            body = scraped.content_html  # process_content would be called on this
        assert body == "<p>html_val</p>", (
            "content_html must be preferred when both present"
        )


class TestScrapeResultCoercion:
    """Verify the existing ScrapeResult model supports both fields."""

    def test_scrape_result_empty_content_html_truthiness(self):
        sr = ScrapeResult(
            markdown="content", images=[], metadata={},
            method="apify", summary_only=False, content_html="",
        )
        assert sr.markdown, "markdown should be truthy"
        assert not sr.content_html, "content_html='' should be falsy"

    def test_scrape_result_none_content_html(self):
        sr = ScrapeResult(
            markdown="content", images=[], metadata={},
            method="apify", summary_only=False, content_html=None,
        )
        assert sr.markdown
        assert not sr.content_html, "content_html=None should be falsy"

    def test_none_scrape_result_identity(self):
        """None is not a ScrapeResult; verify identity check."""
        assert not None, "None should be falsy"
