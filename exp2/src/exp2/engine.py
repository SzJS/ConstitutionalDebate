"""The call layer every model-facing role goes through.

Split out of ``debate.py`` because it is not about debate. A judge, a challenge
generator, a solo decision agent, an objection grader — each needs the same
three guarantees, and each would otherwise reimplement them slightly
differently:

1. a truncated response is fatal and never retried;
2. a malformed response gets exactly one repair attempt, and no more;
3. every attempt reaches the wire log, whatever happens afterwards.

The third is the client's job, but it only holds if every role calls the model
through here rather than reaching for ``client.complete`` directly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .client import ChatClient, Completion
from .config import DebateConfig
from .prompts import MalformedOutputError, build_repair_messages

log = logging.getLogger(__name__)


class TruncatedOutputError(RuntimeError):
    """A response hit the token ceiling.

    Not retried. At the configured ceiling a truncated response means something
    is structurally wrong — most likely native reasoning consuming the budget —
    and a retry at the same cap fails the same way while costing another call.
    The fix is the ``max_tokens`` lever, so say so and stop.
    """


class DebateFailure(RuntimeError):
    """A run could not be completed. The partial record is still on disk."""


async def _complete_with_repair(
    client: ChatClient,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    config: DebateConfig,
    meta: dict[str, Any],
    parse: Any,
    role: str,
    word_limit: int,
    reasoning_effort: str | None = None,
    unrepaired: Callable[[str], Any] | None = None,
) -> tuple[Any, Completion, int, list[dict[str, str]]]:
    """Call the model, and on a format failure spend exactly one repair attempt.

    One bounded retry converts a class of run-killing hiccups into a logged
    annotation. More would select for compliant outputs and bias the sample.

    Returns the message list **actually sent**, as the fourth element. exp1 did not
    need this — it rebuilt every prompt from scratch. exp2's solo conditions hold a
    real conversation that a contest later replays, so a repair's two extra turns
    have to be part of it or the replay is of a conversation that never happened.

    ``unrepaired`` parses a reply that is still malformed after the repair, for the
    roles whose output does not decide anything: a critique has no decision line, so
    the last resort there is withholding its public section, not failing the run.
    """
    completion = await _complete(
        client, model=model, messages=messages, temperature=temperature,
        config=config, meta=meta, reasoning_effort=reasoning_effort,
    )
    try:
        return parse(completion.content), completion, 0, messages
    except MalformedOutputError as first_error:
        log.warning("%s output malformed (%s); attempting one repair", role, first_error)

    repair_messages = build_repair_messages(
        messages, completion.content, role=role, word_limit=word_limit
    )
    repaired = await _complete(
        client, model=model, messages=repair_messages, temperature=temperature,
        config=config, meta={**meta, "purpose": "repair"},
        reasoning_effort=reasoning_effort,
    )
    try:
        return parse(repaired.content), repaired, 1, repair_messages
    except MalformedOutputError as error:
        if unrepaired is not None:
            return unrepaired(repaired.content), repaired, 1, repair_messages
        raise DebateFailure(
            f"{role} output still malformed after one repair attempt: {error}"
        ) from error


async def _complete(
    client: ChatClient,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    config: DebateConfig,
    meta: dict[str, Any],
    reasoning_effort: str | None = None,
) -> Completion:
    # ``None`` means the run's setting. The override exists for one role: the
    # challenger, whose deliberation is an experimental axis — the same weak
    # model with thinking on and off isolates inference-time compute from
    # capability. Anything else varying it would be a second hidden channel.
    completion = await client.complete(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=config.max_tokens,
        reasoning_effort=reasoning_effort or config.reasoning_effort,
        meta=meta,
        frequency_penalty=config.frequency_penalty,
    )
    if completion.truncated:
        raise TruncatedOutputError(
            f"{meta.get('role')} response stopped on "
            f"finish_reason={completion.finish_reason!r} at max_tokens="
            f"{config.max_tokens}. A truncated argument would enter the public "
            f"transcript as if authored, so this is fatal. Raise max_tokens, or "
            f"check whether native reasoning is consuming the budget."
        )
    return completion
