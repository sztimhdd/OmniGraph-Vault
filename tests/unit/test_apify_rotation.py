"""Quick 260508-ev2 F1a: tests for Apify dual-token rotation.

Verifies scrape_wechat_apify():
  1. primary success → backup never invoked
  2. primary raises  → backup invoked, returns its result
  3. both raise      → propagates the LAST exception

All cases mock _apify_call directly — ZERO live network calls.
"""

import pytest
from unittest.mock import AsyncMock, patch

import ingest_wechat


@pytest.mark.asyncio
async def test_primary_success_skips_backup(monkeypatch):
    """Primary token returns dict → backup helper not called."""
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN", "primary-token")
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN_BACKUP", "backup-token")

    expected = {"title": "T", "markdown": "# md", "url": "u", "method": "apify"}
    mock_call = AsyncMock(return_value=expected)
    with patch.object(ingest_wechat, "_apify_call", mock_call):
        result = await ingest_wechat.scrape_wechat_apify("http://example.com")

    assert result == expected
    assert mock_call.call_count == 1
    args, _ = mock_call.call_args
    assert args[0] == "primary-token", "first call must use primary token"


@pytest.mark.asyncio
async def test_primary_raise_invokes_backup(monkeypatch):
    """Primary raises → backup invoked → returns backup's result."""
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN", "primary-token")
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN_BACKUP", "backup-token")

    backup_result = {"title": "T", "markdown": "from-backup", "url": "u", "method": "apify"}
    mock_call = AsyncMock(side_effect=[Exception("primary fail"), backup_result])
    with patch.object(ingest_wechat, "_apify_call", mock_call):
        result = await ingest_wechat.scrape_wechat_apify("http://example.com")

    assert result == backup_result
    assert mock_call.call_count == 2
    first_args, _ = mock_call.call_args_list[0]
    second_args, _ = mock_call.call_args_list[1]
    assert first_args[0] == "primary-token"
    assert second_args[0] == "backup-token"


@pytest.mark.asyncio
async def test_both_raise_propagates(monkeypatch):
    """Both tokens raise → LAST exception re-raised to caller."""
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN", "primary-token")
    monkeypatch.setattr(ingest_wechat, "APIFY_TOKEN_BACKUP", "backup-token")

    primary_exc = Exception("primary fail")
    backup_exc = Exception("backup fail")
    mock_call = AsyncMock(side_effect=[primary_exc, backup_exc])
    with patch.object(ingest_wechat, "_apify_call", mock_call):
        with pytest.raises(Exception) as excinfo:
            await ingest_wechat.scrape_wechat_apify("http://example.com")

    assert "backup fail" in str(excinfo.value), (
        "should re-raise the LAST exception (backup), not the primary"
    )
    assert mock_call.call_count == 2
