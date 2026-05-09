"""Quick 260509-elc: test that _apify_call passes max_items=1 to ApifyClient.

The 2026-05-08 09:00 ADT daily-ingest cron failed 5/5 articles with
"Maximum charged results must be greater than zero" because the pay-per-result
actor zOQWQaziNeBNFWN1O rejects runs without a non-zero max_items run-option.

This test mocks at the ApifyClient class level (one layer deeper than
test_apify_rotation.py which mocks _apify_call directly) so it can capture and
assert on the kwargs actually passed to ApifyClient.actor(...).call(). Zero
live network calls.

Reference: apify_client/clients/resource_clients/actor.py:322 declares
``max_items: int | None = None`` as a kwarg on .call(); line 371-372 maps it
to the API field ``maxItems``.
"""

from __future__ import annotations

from typing import Any

import pytest

import ingest_wechat


class _FakeActorClient:
    """Captures kwargs passed to .call() and returns a synthetic run dict."""

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def call(self, **kwargs: Any) -> dict[str, Any]:
        self._captured["call_count"] = self._captured.get("call_count", 0) + 1
        self._captured["kwargs"] = kwargs
        return {"defaultDatasetId": "ds-fake"}


class _FakeDatasetClient:
    """Returns one minimal item so _apify_call's post-processing succeeds."""

    def iterate_items(self):
        yield {
            "title": "fake-title",
            "markdown": "# fake markdown",
            "publish_time": "2026-05-09",
        }


class _FakeApifyClient:
    """Replacement for apify_client.ApifyClient.

    Records the actor_id passed to .actor() and routes .call() to a fake that
    captures kwargs. .dataset() returns a fake whose iterate_items yields one
    minimal item.
    """

    def __init__(self, token: str) -> None:
        self.token = token
        # Shared captured-state holder, populated by .actor().call().
        self.captured: dict[str, Any] = {}

    def actor(self, actor_id: str) -> _FakeActorClient:
        self.captured["actor_id"] = actor_id
        return _FakeActorClient(self.captured)

    def dataset(self, dataset_id: str) -> _FakeDatasetClient:
        self.captured["dataset_id"] = dataset_id
        return _FakeDatasetClient()


@pytest.mark.asyncio
async def test_apify_call_passes_max_items_1(monkeypatch):
    """_apify_call must pass max_items=1 as a kwarg to ApifyClient.actor(...).call().

    Pay-per-result actor zOQWQaziNeBNFWN1O rejects runs without a non-zero
    max_items run-option. WeChat URL = 1 article expected, so max_items=1 is
    the correct value. max_items is a RUN-LEVEL option (kwarg on .call()), NOT
    a key inside run_input.
    """
    # Capture the FakeApifyClient instance so we can read its captured dict
    # after _apify_call runs.
    instances: list[_FakeApifyClient] = []

    def _factory(token: str) -> _FakeApifyClient:
        client = _FakeApifyClient(token)
        instances.append(client)
        return client

    monkeypatch.setattr(ingest_wechat, "ApifyClient", _factory)

    result = await ingest_wechat._apify_call(
        token="t-test", url="https://mp.weixin.qq.com/s/fake"
    )

    # _apify_call must have constructed exactly one ApifyClient.
    assert len(instances) == 1, "expected exactly one ApifyClient instance"
    captured = instances[0].captured

    # 1. .call() was invoked exactly once
    assert captured.get("call_count") == 1, ".call() should be invoked once"

    # 2. max_items kwarg was present on that call
    kwargs = captured.get("kwargs", {})
    assert "max_items" in kwargs, (
        "max_items kwarg missing from .call() — pay-per-result actor will reject"
    )

    # 3. max_items == 1 (NOT 0, NOT None)
    assert kwargs["max_items"] == 1, (
        f"max_items must be 1 for WeChat single-URL call, got {kwargs['max_items']!r}"
    )

    # 4. run_input shape unchanged — startUrls + crawlerConfig still present,
    #    and max_items did NOT leak INTO run_input.
    run_input = kwargs.get("run_input")
    assert run_input is not None, "run_input kwarg must be passed"
    assert "startUrls" in run_input, "run_input must still contain startUrls"
    assert "crawlerConfig" in run_input, "run_input must still contain crawlerConfig"
    assert "max_items" not in run_input, (
        "max_items must NOT be a key inside run_input — it is a run-level kwarg"
    )
    assert "maxItems" not in run_input, (
        "maxItems must NOT be a key inside run_input — it is a run-level kwarg"
    )

    # 5. actor() called with the expected pay-per-result actor ID
    assert captured.get("actor_id") == "zOQWQaziNeBNFWN1O", (
        "actor ID drift — expected zOQWQaziNeBNFWN1O"
    )

    # Sanity: post-processing returned a non-None dict (proves the fake dataset
    # iterate_items path was exercised).
    assert result is not None
    assert result["method"] == "apify"
