"""OpenAI-compatible chat provider — port of legacy ``openaiCompat.ts`` to httpx.

Preserved semantics:
- ``normalize_base_url`` prevents ``/v1/v1`` double paths (four input forms);
- ``observation`` role downgraded to ``user`` with an ``Observation:`` prefix
  (standard endpoints reject unknown roles);
- 429 / 5xx / network / timeout are retryable with exponential backoff + half jitter;
  ``Retry-After`` (integer seconds) wins over computed backoff;
- other 4xx raise ``AuthError`` immediately (credentials never self-heal by retry);
- per-request hard timeout when ``timeout > 0``.

Upgrades: token usage recording and native tool-calling support. Providers that
do not support native tools still work through the fenced-action fallback in the
agent loop — never assume identical feature support across compatible endpoints.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import Awaitable, Callable

import httpx

from safefix.llm.base import LLMResponse
from safefix.models import Message, TokenUsage, ToolCall


class ProviderError(Exception):
    """Transient or exhausted provider failure."""


class AuthError(ProviderError):
    """Non-retryable credential / client error (4xx except 429)."""


def normalize_base_url(base_url: str) -> str:
    # Order matters: strip trailing slashes first, then a trailing /v1 (handles /v1//).
    return re.sub(r"/v1$", "", re.sub(r"/+$", "", base_url))


def adapt_messages(messages: list[Message]) -> list[dict]:
    return [
        {"role": "user", "content": "Observation: " + m.content} if m.role == "observation"
        else {"role": m.role, "content": m.content}
        for m in messages
    ]


def _retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def _parse_retry_after(response: httpx.Response) -> float | None:
    v = response.headers.get("retry-after")
    if not v:
        return None
    try:
        sec = float(v)
    except ValueError:
        return None  # HTTP-date form unsupported -> fall back to exponential backoff
    return sec if sec >= 0 else None


def _parse_tool_calls(message: dict) -> list[ToolCall]:
    out: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name")
        if not isinstance(name, str):
            continue
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue  # malformed arguments: skip; the loop re-prompts instead of executing
        if isinstance(args, dict):
            out.append(ToolCall(id=tc.get("id") or "", name=name, arguments=args))
    return out


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o-mini",
        *,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        backoff_factor: float = 2.0,
        timeout: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not api_key:
            raise ValueError("api_key is required for the real provider (set API_KEY or use the encrypted store)")
        self._url = f"{normalize_base_url(base_url)}/v1/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client
        self._owns_client = client is None
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._backoff_factor = backoff_factor
        self._timeout = timeout
        self._sleep = sleep

    def _backoff_delay(self, attempt: int) -> float:
        base = self._base_delay * (self._backoff_factor ** attempt)
        return base * (0.5 + random.random() * 0.5)  # half jitter avoids retry thundering herd

    async def complete(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        body: dict = {"model": self._model, "messages": adapt_messages(messages), "temperature": 0}
        if tools:
            body["tools"] = tools
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        request_timeout = httpx.Timeout(self._timeout) if self._timeout > 0 else httpx.Timeout(60.0)

        client = self._client or httpx.AsyncClient()
        try:
            last_err: Exception | None = None
            for attempt in range(self._max_retries + 1):
                try:
                    res = await client.post(self._url, json=body, headers=headers, timeout=request_timeout)
                    if res.status_code >= 400:
                        text = res.text
                        if _retryable_status(res.status_code) and attempt < self._max_retries:
                            last_err = ProviderError(f"provider http {res.status_code}: {text}")
                            await self._sleep(_parse_retry_after(res) or self._backoff_delay(attempt))
                            continue
                        if _retryable_status(res.status_code):
                            raise ProviderError(f"provider http {res.status_code} (retries exhausted): {text}")
                        if 400 <= res.status_code < 500:
                            raise AuthError(f"auth/http {res.status_code}: {text}")
                        raise ProviderError(f"provider http {res.status_code}: {text}")

                    data = res.json()
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message") or {}
                    usage = data.get("usage") or {}
                    return LLMResponse(
                        text=message.get("content") or "",
                        stop_reason=choice.get("finish_reason") or "ok",
                        usage=TokenUsage(
                            prompt_tokens=usage.get("prompt_tokens") or 0,
                            completion_tokens=usage.get("completion_tokens") or 0,
                        ),
                        tool_calls=_parse_tool_calls(message),
                    )
                except AuthError:
                    raise
                except (httpx.HTTPError, ProviderError) as e:
                    if isinstance(e, ProviderError) and "retries exhausted" in str(e):
                        raise
                    last_err = e
                    if attempt < self._max_retries:
                        await self._sleep(self._backoff_delay(attempt))
                        continue
                    raise ProviderError(f"provider request failed after retries: {e}") from e
            raise last_err or ProviderError("provider: retries exhausted")
        finally:
            if self._owns_client:
                await client.aclose()