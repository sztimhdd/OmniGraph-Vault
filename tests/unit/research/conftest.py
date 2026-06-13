"""Autouse get_llm_func mock for the research unit-test directory (arx-2-finish W0).

After arx-2-finish Wave 1, ``synthesizer.run()`` lazy-imports and calls
``get_llm_func()`` directly (RESEARCH §Risk A Option (b)). Without this fixture,
the 10 existing ``test_synthesizer_caption_embeds.py`` tests — which only mock
``cfg.llm_complete`` — would hit the real provider dispatcher (default DeepSeek,
needs ``DEEPSEEK_API_KEY``) the moment they run after the Wave 1 change.

This autouse fixture patches the name AS REBOUND INTO the synthesizer module
(``lib.research.stages.synthesizer.get_llm_func``) to a no-op async provider so
those caption tests survive. Tests in ``test_synthesizer_llm.py`` install their
own ``mock.patch`` on the SAME dotted path inside the test body; that per-test
patch takes precedence (mock resolves the attribute at call time on the module
object), so the baseline here does not interfere with the GAP-A behavioral tests.
"""
from __future__ import annotations

import pytest
from unittest import mock


@pytest.fixture(autouse=True)
def _mock_get_llm_func():
    async def noop_llm(prompt, **kw):
        return "# Stub\n\nStub body."

    with mock.patch(
        "lib.research.stages.synthesizer.get_llm_func",
        return_value=noop_llm,
        create=True,
    ):
        yield
