"""OpenAI-compatible provider parity (legacy openaiCompat.ts) + native tool calling."""

import httpx
import pytest

from safefix.llm.openai_compatible import (
    AuthError,
    OpenAICompatProvider,
    ProviderError,
    adapt_messages,
    normalize_base_url,
)
from safefix.models import Message


def make_provider(handler, **kw):
    """Inject a MockTransport + a recording sleep so tests are offline & deterministic."""
    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(
        base_url=kw.pop("base_url", "https://api.test"),
        api_key=kw.pop("api_key", "sk-test"),
        client=client,
        sleep=fake_sleep,
        **kw,
    )
    return provider, delays


def ok_body(text="hello", finish="stop", usage=None):
    body = {"choices": [{"message": {"content": text}, "finish_reason": finish}]}
    if usage:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def test_normalize_base_url_four_forms():
    assert normalize_base_url("https://x/v1") == "https://x"
    assert normalize_base_url("https://x/v1/") == "https://x"
    assert normalize_base_url("https://x/") == "https://x"
    assert normalize_base_url("https://x") == "https://x"
    assert normalize_base_url("https://x/v1//") == "https://x"


def test_adapt_messages_downgrades_observation_role():
    msgs = [
        Message(role="system", content="s"),
        Message(role="observation", content="o"),
        Message(role="assistant", content="a"),
    ]
    out = adapt_messages(msgs)
    assert out[1] == {"role": "user", "content": "Observation: o"}
    assert out[0]["role"] == "system" and out[2]["role"] == "assistant"


async def test_success_text_usage_and_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return ok_body("hi", usage={"prompt_tokens": 11, "completion_tokens": 7})

    provider, _ = make_provider(handler, base_url="https://api.test/v1/")
    resp = await provider.complete([Message(role="user", content="q")])
    assert resp.text == "hi" and resp.stop_reason == "stop"
    assert resp.usage.total_tokens == 18
    assert seen["url"] == "https://api.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"


async def test_429_retried_with_backoff_range():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return ok_body("ok")

    provider, delays = make_provider(handler, max_retries=3, base_delay=0.5)
    resp = await provider.complete([Message(role="user", content="q")])
    assert resp.text == "ok" and calls["n"] == 2
    assert len(delays) == 1 and 0.25 <= delays[0] < 0.5


async def test_retry_after_header_wins():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")
        return ok_body()

    provider, delays = make_provider(handler)
    await provider.complete([Message(role="user", content="q")])
    assert delays == [2.0]


async def test_5xx_retries_exhausted_raises():
    def handler(request):
        return httpx.Response(503, text="down")

    provider, delays = make_provider(handler, max_retries=2)
    with pytest.raises(ProviderError, match="retries exhausted"):
        await provider.complete([Message(role="user", content="q")])
    assert len(delays) == 2


async def test_401_auth_error_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    provider, delays = make_provider(handler)
    with pytest.raises(AuthError):
        await provider.complete([Message(role="user", content="q")])
    assert calls["n"] == 1 and delays == []


async def test_network_error_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return ok_body("recovered")

    provider, _ = make_provider(handler)
    resp = await provider.complete([Message(role="user", content="q")])
    assert resp.text == "recovered" and calls["n"] == 2


async def test_timeout_retried_then_exhausted():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    provider, delays = make_provider(handler, max_retries=1, timeout=5.0)
    with pytest.raises(ProviderError):
        await provider.complete([Message(role="user", content="q")])
    assert len(delays) == 1


async def test_native_tool_calls_parsed():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path": "a.py"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    provider, _ = make_provider(handler)
    resp = await provider.complete([Message(role="user", content="q")])
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.name == "read_file" and tc.arguments == {"path": "a.py"} and tc.id == "call_1"


async def test_malformed_native_tool_arguments_skipped():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "fallback text",
                            "tool_calls": [
                                {"id": "c", "type": "function", "function": {"name": "read_file", "arguments": "{bad"}}
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    provider, _ = make_provider(handler)
    resp = await provider.complete([Message(role="user", content="q")])
    assert resp.tool_calls == [] and resp.text == "fallback text"


def test_empty_api_key_rejected_at_construction():
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatProvider(base_url="https://x", api_key="")