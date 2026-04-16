"""Tests for provider retries and typed errors."""

from __future__ import annotations

import httpx
import pytest

from core.llm.provider import LLMConfig, LLMProviderNetworkError, OpenAICompatibleProvider


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def post(self, endpoint: str, json: dict):
        self.calls += 1
        raise httpx.ConnectError("network down")


@pytest.mark.asyncio
async def test_provider_raises_typed_network_error_without_leaking_raw_exception():
    provider = OpenAICompatibleProvider(
        LLMConfig(provider="moonshot", max_retries=1)
    )
    client = FakeClient()
    provider._client = client

    with pytest.raises(LLMProviderNetworkError):
        await provider._post_with_retries("/chat/completions", {"model": "x"})

    assert client.calls == 1
