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
from .prompts import (
    MalformedOutputError,
    build_budget_repair_messages,
    build_repair_messages,
    has_public_label,
)

log = logging.getLogger(__name__)


class TruncatedOutputError(RuntimeError):
    """A response hit the token ceiling.

    Not retried *blindly*. At the configured ceiling a truncated response means
    something is structurally wrong, and a retry at the same cap fails the same way
    while costing another call — unless the reason is known, which since 2026-08-25 it
    sometimes is: see the budget route in ``_complete_with_repair``.

    ``completion`` carries the truncated reply, because deciding whether the truncation
    cost anything public means reading what did arrive.
    """

    def __init__(self, message: str, completion: Completion | None = None) -> None:
        super().__init__(message)
        self.completion = completion


class DebateFailure(RuntimeError):
    """A run could not be completed. The partial record is still on disk."""


# What the one repair attempt was spent on. Returned as the fifth element so that the
# caller can put it in ``parse_mode`` — the carrier a report counts. A budget repair is
# not a format failure and must not be reported as one: the model wrote nothing wrong,
# it ran out of room before it wrote anything at all.
REPAIR_KINDS: tuple[str, ...] = ("none", "format", "budget")


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
    max_tokens: int | None = None,
    public_label: str | None = None,
    unrepaired: Callable[[str], Any] | None = None,
) -> tuple[Any, Completion, int, list[dict[str, str]], str]:
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

    ``public_label`` opens the **budget route**, and it is given only to the roles that
    produce record text ("Argument" for a debater, "Reasoning" for a solo stage). If the
    first call is truncated and the reply never reached that label on a line of its own,
    then nothing public was cut: the model spent the whole cap deliberating. That is a
    known cause, so the one repair is spent on it — "you ran out of budget, stop
    deliberating, write the section now" — instead of the run dying. If the label **is**
    present, something public may have been cut and truncation stays fatal, because a
    half-written argument entering the transcript as if authored is the failure the rule
    was written for. Roles with no ``public_label`` are unchanged.

    Returns ``(parsed, completion, repair_attempts, messages_sent, repair_kind)``.
    """
    budget_repair = False
    try:
        completion = await _complete(
            client, model=model, messages=messages, temperature=temperature,
            config=config, meta=meta, reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
        )
    except TruncatedOutputError as truncation:
        reply = truncation.completion
        if (public_label is None or reply is None
                or has_public_label(reply.content, public_label)):
            raise
        log.warning(
            "%s ran out of budget before reaching '%s:' (%d chars of deliberation); "
            "spending the repair on the budget rather than on the format",
            role, public_label, len(reply.content),
        )
        budget_repair, completion = True, reply

    shape: str | None = None
    if not budget_repair:
        try:
            return parse(completion.content), completion, 0, messages, "none"
        except MalformedOutputError as first_error:
            # The shape the parser refused it for, so the one repair can be aimed at
            # that shape rather than restating the format at a model that has already
            # restated the format back (LLM_NOTES §3m).
            shape = first_error.kind
            log.warning("%s output malformed (%s: %s); attempting one repair",
                        role, shape, first_error)

    kind = "budget" if budget_repair else "format"
    repair_messages = (
        build_budget_repair_messages(messages, completion.content,
                                     label=public_label or "", word_limit=word_limit)
        if budget_repair else
        build_repair_messages(messages, completion.content, role=role,
                              word_limit=word_limit, kind=shape)
    )
    try:
        repaired = await _complete(
            client, model=model, messages=repair_messages, temperature=temperature,
            config=config, meta={**meta, "purpose": "repair"},
            reasoning_effort=reasoning_effort, max_tokens=max_tokens,
        )
    except TruncatedOutputError as truncation:
        # Twice truncated. Fatal, except for the roles that have a last resort: a
        # critique withheld costs a step of the record, and killing an otherwise
        # complete decision over it costs the whole cell.
        reply = truncation.completion
        if unrepaired is not None and reply is not None:
            log.warning("%s truncated again after a %s repair; falling back",
                        role, kind)
            return unrepaired(reply.content), reply, 1, repair_messages, kind
        raise DebateFailure(
            f"{role} response truncated again after a {kind} repair: {truncation}"
        ) from truncation
    try:
        return parse(repaired.content), repaired, 1, repair_messages, kind
    except MalformedOutputError as error:
        if unrepaired is not None:
            return unrepaired(repaired.content), repaired, 1, repair_messages, kind
        raise DebateFailure(
            f"{role} output still malformed after one {kind} repair attempt: {error}"
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
    max_tokens: int | None = None,
) -> Completion:
    # ``reasoning_effort=None`` means the run's setting. The override exists for one
    # role: the challenger, whose deliberation is an experimental axis — the same weak
    # model with thinking on and off isolates inference-time compute from
    # capability. Anything else varying it would be a second hidden channel.
    #
    # ``max_tokens=None`` likewise means ``config.max_tokens``. The override exists for
    # the roles that produce record text (``config.generation_max_tokens``), which is
    # where the runaway private deliberation lives: every one of the pilot's 16
    # truncations was a debater's or reviewer's own Thinking block, and none was a judge,
    # challenger or recourse ruling.
    cap = config.max_tokens if max_tokens is None else max_tokens
    completion = await client.complete(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=cap,
        reasoning_effort=reasoning_effort or config.reasoning_effort,
        meta=meta,
        frequency_penalty=config.frequency_penalty,
    )
    if completion.truncated:
        raise TruncatedOutputError(
            f"{meta.get('role')} response stopped on "
            f"finish_reason={completion.finish_reason!r} at max_tokens="
            f"{cap}. A truncated argument would enter the public "
            f"transcript as if authored, so this is fatal. Raise max_tokens, or "
            f"check whether native reasoning is consuming the budget.",
            completion,
        )
    return completion
