"""ScriptedMock parity (legacy scriptedMock.ts) + provider response contract."""

import pytest

from safefix.llm.base import LLMResponse
from safefix.llm.mock import ScriptedMock
from safefix.models import Message, TokenUsage

MSGS = [Message(role="user", content="hi")]


async def test_mock_returns_queued_responses_in_order():
    mock = ScriptedMock(["first", "second"])
    assert (await mock.complete(MSGS)).text == "first"
    assert (await mock.complete(MSGS)).text == "second"


async def test_mock_sticky_repeats_last():
    mock = ScriptedMock(["only"], sticky=True)
    assert (await mock.complete(MSGS)).text == "only"
    assert (await mock.complete(MSGS)).text == "only"


async def test_mock_exhausted_raises():
    mock = ScriptedMock(["one"])
    await mock.complete(MSGS)
    with pytest.raises(RuntimeError, match="exhausted"):
        await mock.complete(MSGS)


async def test_mock_empty_non_sticky_raises_immediately():
    with pytest.raises(RuntimeError):
        await ScriptedMock([]).complete(MSGS)


def test_llm_response_defaults():
    r = LLMResponse(text="hello")
    assert r.stop_reason == "ok"
    assert r.usage.total_tokens == 0


def test_llm_response_usage_recorded():
    r = LLMResponse(text="x", usage=TokenUsage(prompt_tokens=3, completion_tokens=4))
    assert r.usage.total_tokens == 7
