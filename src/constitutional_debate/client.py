"""Async OpenRouter chat client.

Written against raw ``httpx`` rather than a vendor SDK because the audit needs
the byte-exact wire request, and an SDK hides it.

The retry classification is the load-bearing part. In particular OpenRouter
reports upstream provider failures as **HTTP 200 with an ``error`` key in the
body**: a client built on ``raise_for_status()`` sails past that into a
``KeyError`` deep inside parsing, and never backs off.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

import httpx

from .config import ClientConfig

# Transport-level failures worth another attempt.
RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
# Client errors that another attempt cannot fix: a bad key or model id should
# fail in one second naming the problem, not after five backoffs.
FATAL_STATUSES = frozenset({400, 401, 402, 403, 404})
# Blank completions are usually deterministic, so they get a tighter cap than
# genuine transport failures.
MAX_BLANK_ATTEMPTS = 2

NORMAL_FINISH_REASONS = frozenset({"stop", "end_turn", "eos"})

CallSink = Callable[[dict[str, Any]], Awaitable[None]]


class OpenRouterError(RuntimeError):
    """Base class for client failures."""


class RetryableError(OpenRouterError):
    pass


class FatalError(OpenRouterError):
    pass


@dataclass(frozen=True)
class Completion:
    call_id: str
    content: str
    finish_reason: str | None
    model: str | None  # resolved model, which can differ from the one requested
    provider: str | None
    reasoning: str | None
    usage: dict[str, Any]

    @property
    def has_native_reasoning(self) -> bool:
        return bool(self.reasoning)

    @property
    def truncated(self) -> bool:
        return (
            self.finish_reason is not None
            and self.finish_reason not in NORMAL_FINISH_REASONS
        )


class ChatClient(Protocol):
    """The narrow seam ``debate.py`` depends on, so tests can substitute a fake."""

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        reasoning_effort: str,
        meta: dict[str, Any],
    ) -> Completion: ...


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None  # HTTP-date form; fall back to computed backoff


class OpenRouterClient:
    """Bounded-concurrency client that records every attempt it makes."""

    def __init__(
        self,
        api_key: str,
        config: ClientConfig,
        *,
        sink: CallSink | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._sink = sink
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "ConstitutionalDebate",
            },
            timeout=httpx.Timeout(
                connect=config.connect_timeout_s,
                read=config.read_timeout_s,
                write=config.connect_timeout_s,
                pool=config.connect_timeout_s,
            ),
            transport=transport,
        )

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _build_body(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        }
        # The protocol's private channel is the "Thinking:" block, which we
        # persist and audit. Native reasoning is a second private channel
        # outside the protocol, so it is set deliberately rather than left to a
        # provider default.
        if reasoning_effort == "off":
            body["reasoning"] = {"enabled": False}
        else:
            body["reasoning"] = {"effort": reasoning_effort}
        return body

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        reasoning_effort: str,
        meta: dict[str, Any],
    ) -> Completion:
        body = self._build_body(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        blank_attempts = 0
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                async with self._semaphore:
                    return await self._attempt(body, meta=meta, attempt=attempt)
            except FatalError:
                raise
            except RetryableError as error:
                last_error = error
                if getattr(error, "blank", False):
                    blank_attempts += 1
                    if blank_attempts >= MAX_BLANK_ATTEMPTS:
                        raise
                delay = getattr(error, "retry_after", None)
                if delay is None:
                    delay = random.uniform(  # full jitter
                        0,
                        min(
                            self._config.backoff_cap_s,
                            self._config.backoff_base_s * 2 ** (attempt - 1),
                        ),
                    )
                # Clamp Retry-After too: a provider answering "3600" would
                # otherwise stall the debate until the run timeout fires.
                delay = min(delay, self._config.backoff_cap_s)
                if attempt < self._config.max_attempts:
                    await asyncio.sleep(delay)

        raise OpenRouterError(
            f"giving up after {self._config.max_attempts} attempts: {last_error}"
        ) from last_error

    async def _attempt(
        self, body: dict[str, Any], *, meta: dict[str, Any], attempt: int
    ) -> Completion:
        call_id = uuid.uuid4().hex[:12]
        started = asyncio.get_running_loop().time()

        record: dict[str, Any] = {
            "call_id": call_id,
            "attempt": attempt,
            "request_body": body,
            **meta,
        }

        try:
            response = await self._client.post("/chat/completions", json=body)
        except httpx.TransportError as error:
            record.update(status=None, error=f"{type(error).__name__}: {error}")
            await self._record(record)
            raise RetryableError(f"transport error: {error}") from error

        record["status"] = response.status_code
        record["latency_ms"] = round(
            (asyncio.get_running_loop().time() - started) * 1000
        )

        try:
            payload = response.json()
        except ValueError:
            payload = {"_unparseable_body": response.text[:2000]}
        record["response_body"] = payload

        # From here the response — and any generation we have paid for — exists.
        # The record is written on every exit path, including an unexpected
        # payload shape, so no model output can end up living only in a
        # traceback.
        try:
            return self._interpret(payload, response, record, call_id, body)
        finally:
            await self._record(record)

    def _interpret(
        self,
        payload: Any,
        response: httpx.Response,
        record: dict[str, Any],
        call_id: str,
        body: dict[str, Any],
    ) -> Completion:
        """Classify one response. Raises Retryable/Fatal; never writes records."""
        if response.status_code in FATAL_STATUSES:
            raise FatalError(
                f"HTTP {response.status_code} from OpenRouter "
                f"(model={body['model']!r}): {_error_message(payload)}. "
                f"Check OPENROUTER_KEY and the model id; retrying will not help."
            )

        if response.status_code in RETRY_STATUSES or response.status_code >= 500:
            error = RetryableError(
                f"HTTP {response.status_code}: {_error_message(payload)}"
            )
            error.retry_after = _retry_after_seconds(response)  # type: ignore[attr-defined]
            raise error

        if response.status_code != 200:
            raise FatalError(
                f"unexpected HTTP {response.status_code}: {_error_message(payload)}"
            )

        # OpenRouter signals upstream provider failures inside a 200 body.
        if not isinstance(payload, dict):
            raise RetryableError(f"unexpected response shape: {type(payload).__name__}")
        if payload.get("error"):
            raise RetryableError(f"upstream error in 200 body: {payload['error']}")

        choices = payload.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            error = RetryableError("response carried no usable choices")
            error.blank = True  # type: ignore[attr-defined]
            raise error

        message = choices[0].get("message")
        if not isinstance(message, dict):
            error = RetryableError("response choice carried no message object")
            error.blank = True  # type: ignore[attr-defined]
            raise error

        content = (message.get("content") or "").strip()
        reasoning = message.get("reasoning") or None
        finish_reason = choices[0].get("finish_reason")

        record.update(
            provider=payload.get("provider"),
            response_model=payload.get("model"),
            finish_reason=finish_reason,
            has_native_reasoning=bool(reasoning),
            usage=payload.get("usage") or {},
        )

        # A reasoning-bearing response with empty content is a real (if useless)
        # completion, not a transport failure -- retrying it burns paid calls.
        if not content and not reasoning:
            error = RetryableError("response carried empty content")
            error.blank = True  # type: ignore[attr-defined]
            raise error

        return Completion(
            call_id=call_id,
            content=content,
            finish_reason=finish_reason,
            model=payload.get("model"),
            provider=payload.get("provider"),
            reasoning=reasoning,
            usage=payload.get("usage") or {},
        )

    async def _record(self, record: dict[str, Any]) -> None:
        if self._sink is not None:
            await self._sink(record)


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    return str(payload)[:300]
