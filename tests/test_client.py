"""Client retry classification, exercised against the real client.

``httpx.MockTransport`` is used rather than a mock of ``OpenRouterClient`` so the
actual classification code runs — a mocked client would test nothing.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from constitutional_debate.client import (
    FatalError,
    OpenRouterClient,
    OpenRouterError,
    RetryableError,
)
from constitutional_debate.config import ClientConfig

MESSAGES = [{"role": "user", "content": "hello"}]


def client_config(**kwargs) -> ClientConfig:
    base = dict(
        base_url="https://openrouter.test/api/v1",
        max_concurrency=4,
        max_attempts=4,
        backoff_base_s=0.0,  # keep tests instant; jitter over [0, 0] is 0
        backoff_cap_s=30.0,  # the ceiling Retry-After is clamped to
        connect_timeout_s=1.0,
        read_timeout_s=1.0,
        run_timeout_s=10.0,
    )
    return ClientConfig(**{**base, **kwargs})


def ok_body(content: str = "Answer: 1", **extra):
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "model": "deepseek/deepseek-v4-flash",
        "provider": "DeepSeek",
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        **extra,
    }


async def run(handler, *, calls=None, **config_kwargs):
    async def sink(record):
        calls.append(record)

    async with OpenRouterClient(
        "test-key",
        client_config(**config_kwargs),
        sink=sink if calls is not None else None,
        transport=httpx.MockTransport(handler),
    ) as client:
        return await client.complete(
            model="deepseek/deepseek-v4-flash",
            messages=MESSAGES,
            temperature=0.7,
            max_tokens=8192,
            reasoning_effort="off",
            meta={"role": "judge", "round": 0, "speaker": None, "purpose": "judge"},
        )


# --------------------------------------------------------------------------- #


async def test_success_captures_provider_and_resolved_model():
    completion = await run(lambda request: httpx.Response(200, json=ok_body()))
    assert completion.content == "Answer: 1"
    assert completion.provider == "DeepSeek"
    assert completion.model == "deepseek/deepseek-v4-flash"
    assert completion.finish_reason == "stop"
    assert not completion.truncated


async def test_429_then_200_succeeds():
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=ok_body())

    completion = await run(handler)
    assert completion.content == "Answer: 1"
    assert len(seen) == 2


async def test_http_200_with_error_body_is_retried():
    """OpenRouter reports upstream failures this way; raise_for_status misses it."""
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                200, json={"error": {"code": 502, "message": "upstream is down"}}
            )
        return httpx.Response(200, json=ok_body())

    completion = await run(handler)
    assert completion.content == "Answer: 1"
    assert len(seen) == 2


async def test_401_fails_immediately_naming_the_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(401, json={"error": {"message": "no auth"}})

    with pytest.raises(FatalError, match="OPENROUTER_KEY"):
        await run(handler)
    assert len(seen) == 1, "a bad key must not be retried"


async def test_404_on_bad_model_fails_immediately():
    with pytest.raises(FatalError, match="model="):
        await run(lambda request: httpx.Response(404, json={"error": "no such model"}))


async def test_retry_after_header_is_honoured(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("constitutional_debate.client.asyncio.sleep", fake_sleep)

    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json=ok_body())

    await run(handler)
    assert slept == [7.0]


async def test_retry_after_is_clamped_to_the_backoff_cap(monkeypatch):
    """A provider answering 3600 must not stall the run for an hour."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("constitutional_debate.client.asyncio.sleep", fake_sleep)

    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "3600"}, json={})
        return httpx.Response(200, json=ok_body())

    await run(handler)
    assert slept == [30.0], "clamped to backoff_cap_s"


async def test_402_is_fatal():
    with pytest.raises(FatalError):
        await run(
            lambda request: httpx.Response(
                402, json={"error": {"message": "insufficient credits"}}
            )
        )


async def test_an_unparseable_body_is_still_recorded():
    """A paid response must never exist only in a traceback."""
    calls: list[dict] = []
    with pytest.raises(RetryableError):
        await run(
            lambda request: httpx.Response(200, text="<html>gateway error</html>"),
            calls=calls,
            max_attempts=2,
        )
    assert calls, "the attempt was not recorded"
    assert "_unparseable_body" in calls[0]["response_body"]


async def test_an_unexpected_payload_shape_is_recorded_not_lost():
    calls: list[dict] = []
    # Retried to exhaustion (not blank-flagged), so the wrapper error surfaces.
    with pytest.raises(OpenRouterError):
        await run(
            lambda request: httpx.Response(200, json=["not", "an", "object"]),
            calls=calls,
            max_attempts=2,
        )
    assert calls
    assert calls[0]["response_body"] == ["not", "an", "object"]


async def test_blank_content_is_capped_below_max_attempts():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "   "}, "finish_reason": "stop"}]
            },
        )

    with pytest.raises(RetryableError, match="empty content"):
        await run(handler, max_attempts=5)
    assert len(seen) == 2, "blank completions get a tighter cap than transport errors"


async def test_reasoning_only_response_is_not_treated_as_blank():
    """A reasoning-capable model can return reasoning with empty content."""
    completion = await run(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "", "reasoning": "internal chain"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )
    )
    assert completion.has_native_reasoning
    assert completion.content == ""


async def test_truncation_is_surfaced_not_hidden():
    completion = await run(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "half a sen"}, "finish_reason": "length"}
                ]
            },
        )
    )
    assert completion.truncated
    assert completion.finish_reason == "length"


async def test_transport_errors_are_retried_then_give_up():
    seen = []

    def handler(request):
        seen.append(request)
        raise httpx.ConnectError("connection refused")

    with pytest.raises(OpenRouterError, match="giving up after 3"):
        await run(handler, max_attempts=3)
    assert len(seen) == 3


async def test_every_attempt_is_recorded_with_join_keys():
    calls: list[dict] = []
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, json=ok_body())

    completion = await run(handler, calls=calls)

    assert len(calls) == 2, "failed attempts are part of the record too"
    assert [c["attempt"] for c in calls] == [1, 2]
    for record in calls:
        assert record["role"] == "judge"
        assert record["purpose"] == "judge"
        assert record["request_body"]["messages"] == MESSAGES
        assert "call_id" in record
    assert calls[-1]["call_id"] == completion.call_id


async def test_reasoning_effort_off_disables_it_in_the_body():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body())

    await run(handler)
    assert captured["body"]["reasoning"] == {"enabled": False}
    assert captured["body"]["usage"] == {"include": True}
    assert captured["body"]["max_tokens"] == 8192


async def test_a_shared_semaphore_bounds_concurrency_across_clients():
    """A batch harness builds one client per run; the fleet still needs a bound.

    Each run needs its own client so ``sink`` stays per-run and the call logs do
    not interleave, but that would otherwise put ``max_concurrency`` requests in
    flight *per run*. Passing one semaphore to every client is what bounds the
    whole fleet, and this is the assertion that it does.
    """
    in_flight = 0
    peak = 0

    async def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.01)
            return httpx.Response(200, json=ok_body())
        finally:
            in_flight -= 1

    shared = asyncio.Semaphore(2)
    clients = [
        OpenRouterClient(
            "test-key",
            # max_concurrency=8 each: without the shared semaphore, six clients
            # would admit far more than two at once.
            client_config(max_concurrency=8),
            transport=httpx.MockTransport(handler),
            semaphore=shared,
        )
        for _ in range(6)
    ]
    try:
        await asyncio.gather(
            *(
                client.complete(
                    model="deepseek/deepseek-v4-flash",
                    messages=MESSAGES,
                    temperature=0.0,
                    max_tokens=8192,
                    reasoning_effort="off",
                    meta={"role": "judge", "purpose": "judge"},
                )
                for client in clients
            )
        )
    finally:
        for client in clients:
            await client.aclose()

    assert peak == 2, f"the shared semaphore should cap the fleet at 2, saw {peak}"


async def test_without_a_shared_semaphore_each_client_bounds_only_itself():
    """The default is unchanged: one client, its own bound. Guards the `or`."""
    async def handler(request):
        await asyncio.sleep(0.005)
        return httpx.Response(200, json=ok_body())

    client = OpenRouterClient(
        "test-key",
        client_config(max_concurrency=3),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client._semaphore._value == 3
    finally:
        await client.aclose()


async def test_a_no_endpoints_404_is_retried_but_a_bad_model_id_is_not():
    """OpenRouter uses 404 for two unrelated things, told apart only by text.

    A model whose providers are all momentarily unavailable is transient; a
    model id that does not exist is not. Treating both as fatal cost a real
    experiment: deepseek-v4-pro-0813 has two providers, both blipped, and the
    run recorded the model as unusable when it worked again minutes later. The
    models with the fewest providers are the capable ones, so the failure falls
    exactly where it hurts.
    """
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(404, json={"error": {
                "message": "No endpoints available matching your guardrail "
                           "restrictions and data policy. Configure: "
                           "https://openrouter.ai/settings/privacy",
                "code": 404}})
        return httpx.Response(200, json=ok_body())

    completion = await run(handler)
    assert completion.content == "Answer: 1"
    assert len(seen) == 2, "the transient 404 should have been retried"


async def test_a_genuine_404_still_fails_immediately():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(404, json={"error": {
            "message": "No allowed providers are available for the selected model.",
            "code": 404}})

    with pytest.raises(FatalError, match="retrying will not help"):
        await run(handler)
    assert len(seen) == 1, "a bad model id must not be retried"
