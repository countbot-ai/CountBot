"""Provider 重试策略回归：黑名单分类、指数退避与流式重放边界。"""

import asyncio

import httpx
import openai
import pytest

from backend.modules.providers import base as provider_base
from backend.modules.providers import openai_responses_provider as responses_module
from backend.modules.providers.openai_responses_provider import (
    OpenAIResponsesProvider,
)


class _StatusError(Exception):
    """带 HTTP 状态码的上游异常。"""

    def __init__(self, status_code, message="upstream error", headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = httpx.Response(
            status_code,
            headers=headers or {},
            request=httpx.Request("POST", "https://upstream.example/v1/responses"),
        )


def _bare_api_error(message="Upstream request failed"):
    """SDK 收到 SSE error 事件时抛出的异常：无状态码的 APIError 基类。"""
    request = httpx.Request("POST", "https://upstream.example/v1/responses")
    return openai.APIError(message, request, body=None)


class _Event:
    def __init__(self, event_type, **attrs):
        self.type = event_type
        for key, value in attrs.items():
            setattr(self, key, value)


class _EventStream:
    """按顺序产出事件，随后抛出一次错误。"""

    def __init__(self, events=(), error=None):
        self._events = list(events)
        self._error = error
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index < len(self._events):
            event = self._events[self._index]
            self._index += 1
            return event
        if self._error is not None:
            error, self._error = self._error, None
            raise error
        raise StopAsyncIteration


class _FakeResponses:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        result = self._results.pop(0) if self._results else _bare_api_error()
        if isinstance(result, Exception):
            raise result
        return result


class _FakeClient:
    def __init__(self, results):
        self.responses = _FakeResponses(results)


def _drain(iterator):
    async def _collect():
        return [chunk async for chunk in iterator]

    return asyncio.run(_collect())


def _provider(max_retries=3):
    return OpenAIResponsesProvider(
        api_key="test-placeholder",
        api_base="https://upstream.example/v1",
        default_model="test-model",
        max_retries=max_retries,
    )


def _iterate(provider, client):
    return provider._chat_stream_via_responses(
        client=client,
        messages=[{"role": "user", "content": "ping"}],
        tools=None,
        model="test-model",
        max_tokens=128,
        temperature=0.0,
    )


@pytest.fixture
def fast_backoff(monkeypatch):
    monkeypatch.setattr(
        responses_module, "retry_backoff_seconds", lambda *args, **kwargs: 0.001
    )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 422])
def test_client_errors_are_not_retryable(status):
    assert provider_base.is_retryable_error(_StatusError(status)) is False


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_status_codes_are_retryable(status):
    assert provider_base.is_retryable_error(_StatusError(status)) is True


def test_bare_api_error_from_sse_is_retryable():
    assert provider_base.is_retryable_error(_bare_api_error()) is True


def test_real_upstream_error_text_is_retryable():
    message = (
        "Upstream request failed "
        "(request id: 202611060419434510843348268d9d6gGLTZ8KC)"
    )
    assert provider_base.is_retryable_error(_bare_api_error(message)) is True


def test_transport_errors_are_retryable():
    assert provider_base.is_retryable_error(httpx.ReadError("closed")) is True
    assert provider_base.is_retryable_error(httpx.ConnectTimeout("slow")) is True


def test_auth_hint_without_status_is_not_retryable():
    assert provider_base.is_retryable_error(
        _bare_api_error("invalid api key")
    ) is False


def test_backoff_is_exponential_and_capped():
    samples = [
        [provider_base.retry_backoff_seconds(attempt) for _ in range(20)]
        for attempt in (1, 2, 3, 12)
    ]
    for attempt, values in zip((1, 2, 3, 12), samples):
        expected = min(2 ** attempt, provider_base.RETRY_BACKOFF_CAP_SECONDS)
        assert all(
            expected * 0.8 <= value <= provider_base.RETRY_BACKOFF_CAP_SECONDS
            for value in values
        )
    assert min(samples[0]) < min(samples[1]) < min(samples[2])


def test_jitter_prevents_identical_waits():
    values = {provider_base.retry_backoff_seconds(2) for _ in range(20)}
    assert len(values) > 1


def test_retry_after_takes_precedence_and_is_capped():
    limited = _StatusError(429, headers={"retry-after": "7"})
    excessive = _StatusError(429, headers={"retry-after": "120"})
    assert provider_base.retry_backoff_seconds(1, limited) == 7.0
    assert (
        provider_base.retry_backoff_seconds(1, excessive)
        == provider_base.RETRY_BACKOFF_CAP_SECONDS
    )


def test_stream_retries_when_no_content_was_emitted(fast_backoff):
    ok = _EventStream([_Event("response.output_text.delta", delta="pong")])
    client = _FakeClient([_EventStream(error=_bare_api_error()), ok])

    chunks = _drain(_iterate(_provider(), client))

    assert client.responses.calls == 2
    assert "".join(chunk.content or "" for chunk in chunks) == "pong"
    assert all(chunk.error is None for chunk in chunks)


def test_stream_does_not_replay_after_content(fast_backoff):
    partial = _EventStream(
        [_Event("response.output_text.delta", delta="partial")],
        error=_bare_api_error(),
    )
    client = _FakeClient([partial])

    with pytest.raises(openai.APIError):
        _drain(_iterate(_provider(), client))

    assert client.responses.calls == 1


def test_setup_retries_on_server_error(fast_backoff):
    provider = _provider()
    ok = _EventStream([_Event("response.output_text.delta", delta="pong")])
    client = _FakeClient([_StatusError(502), ok])

    result = asyncio.run(
        provider._create_stream_with_retry(client, {}, "trace")
    )

    assert result is ok
    assert client.responses.calls == 2


def test_setup_does_not_retry_auth_error(fast_backoff):
    provider = _provider()
    client = _FakeClient([_StatusError(401)])

    with pytest.raises(_StatusError):
        asyncio.run(provider._create_stream_with_retry(client, {}, "trace"))

    assert client.responses.calls == 1


def test_retry_budget_is_bounded(fast_backoff):
    streams = [_EventStream(error=_bare_api_error()) for _ in range(4)]
    client = _FakeClient(streams)
    provider = _provider(max_retries=3)

    with pytest.raises(openai.APIError):
        _drain(_iterate(provider, client))

    assert client.responses.calls == 4
