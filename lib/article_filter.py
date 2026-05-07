"""v3.5 Ingest Refactor — Layer 1/2 placeholder filter interface.

Quick: 260507-lai (V35-FOUND-01)

This module is the foundation for the v3.5 candidate-filtering refactor.
It exposes a stable two-layer filter API used by the ingest loop in
``batch_ingest_from_spider.py``:

    - ``layer1_pre_filter`` runs BEFORE the (expensive) scrape, on
      cheap signals only: title + summary/digest + content_length.
      It is meant to reject obvious non-candidates without spending
      Apify / CDP / MCP scraping budget.

    - ``layer2_full_body_score`` runs AFTER the scrape, on the full
      article body. It is meant to score real candidates against the
      target topics and produce a final pass/skip decision before
      LightRAG ingestion.

Both functions currently return ``FilterResult(passed=True, ...)`` —
they are deliberate **placeholders** that always pass. The real filter
logic ships in follow-up quicks per
``.planning/PROJECT-Ingest-Refactor-v3.5.md`` Phase B+C.

The reason for shipping the placeholder API now (V35-FOUND-01) is to
**permanently bypass the broken** ``_classify_full_body`` **gate** that
caused the 2026-05-07 cron mass-classify CV disaster (fix `428b16f`,
revert of Quick `260506-se5`). With the layer interface in place, the
ingest loop's control flow no longer routes through the classifications
table or the multi-topic UPSERT pattern that triggered the disaster.
Future filter logic plugs into ``layer1_pre_filter`` and
``layer2_full_body_score`` without touching the ingest loop again.

Locked design decisions (do NOT redesign in this quick):
    - ``FilterResult`` is a frozen dataclass with two fields: ``passed``
      and ``reason``. No additional fields, no sub-types, no
      configurability via kwargs.
    - Both filter functions are synchronous. If a future real
      implementation needs async (e.g. an LLM probe), introduce a new
      function name; do not change these signatures.
    - Both functions always return ``passed=True`` in this quick. Any
      caller that branches on ``not result.passed`` is dead-code in
      this revision but the branch must stay so the wiring is correct
      for the next quick that lands real logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterResult:
    """Outcome of a Layer 1 or Layer 2 filter call.

    Attributes:
        passed: ``True`` if the article should proceed to the next
            stage; ``False`` if the ingest loop should record a
            ``skipped`` ingestion row and continue to the next article.
        reason: Human-readable explanation of the decision. For
            placeholder runs the string contains the literal token
            ``"placeholder"`` so log greps and tests can assert the
            non-final state.
    """

    passed: bool
    reason: str


def layer1_pre_filter(
    title: str,
    summary: str,
    content_length: int | None,
) -> FilterResult:
    """Cheap pre-scrape filter on title + summary + estimated length.

    Args:
        title: Article title as captured at scan time.
        summary: 50–200 char digest captured at scan time
            (WeChat: ``articles.digest``; RSS: feed-provided summary).
        content_length: Estimated content length when known
            (RSS: ``content_length`` from feed); ``None`` for sources
            where the length isn't available pre-scrape (most WeChat
            articles).

    Returns:
        ``FilterResult(passed=True, reason="placeholder: layer1 always-pass")``.
        Real filter logic ships in a follow-up quick.
    """
    return FilterResult(
        passed=True,
        reason="placeholder: layer1 always-pass",
    )


def layer2_full_body_score(
    article_id: int,
    title: str,
    body: str,
) -> FilterResult:
    """Post-scrape full-body filter / scoring.

    Args:
        article_id: ``articles.id`` row identifier — included for
            future logic that wants to persist a per-article score.
        title: Article title (same as Layer 1).
        body: Scraped article body (markdown). Pass ``""`` if the
            scrape produced no body — real implementations are
            expected to fail-closed in that case.

    Returns:
        ``FilterResult(passed=True, reason="placeholder: layer2 always-pass")``.
        Real filter logic ships in a follow-up quick.
    """
    return FilterResult(
        passed=True,
        reason="placeholder: layer2 always-pass",
    )
