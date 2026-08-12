"""Debate orchestration.

``turn_style`` drives two things, not one: a visibility predicate (in
``Transcript.visible_to``) and the scheduler branch below. Under
``asyncio.gather`` both debaters' requests are issued before either turn exists,
so sequential behaviour cannot be produced by the visibility rule alone.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .client import ChatClient, Completion
from .config import DebateConfig
from .persistence import RunRecord, RunWriter
from .prompts import (
    PROFILES,
    MalformedOutputError,
    RecourseFrame,
    TaskProfile,
    build_challenger_messages,
    build_debater_messages,
    build_judge_messages,
    build_repair_messages,
    parse_debater_output,
    parse_judge_output,
    parse_ruling_output,
    select_profile,
)
from .types import (
    ORDER,
    Challenge,
    Context,
    DebateResult,
    RecourseResult,
    Ruling,
    Seating,
    Speaker,
    Task,
    Transcript,
    Turn,
    Verdict,
    compose_transcript,
    count_words,
    resolve_ruling,
)

log = logging.getLogger(__name__)


class TruncatedOutputError(RuntimeError):
    """A response hit the token ceiling.

    Not retried. At the configured ceiling a truncated response means something
    is structurally wrong — most likely native reasoning consuming the budget —
    and a retry at the same cap fails the same way while costing another call.
    The fix is the ``max_tokens`` lever, so say so and stop.
    """


class DebateFailure(RuntimeError):
    """A debate could not be completed. The partial record is still on disk."""


async def run_debate(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    writer: RunWriter | None = None,
    profile: TaskProfile | None = None,
) -> DebateResult:
    """Run one debate to a verdict."""
    profile = profile or select_profile(task, context)
    transcript = Transcript()

    for round_number in range(1, config.n_rounds + 1):
        await _run_round(
            task, context, config, seating, client, transcript,
            round_number=round_number, profile=profile, writer=writer,
        )

    verdict = await _judge(
        task, context, config, seating, client, transcript,
        profile=profile, writer=writer,
    )
    return DebateResult(
        run_id=writer.run_id if writer else "unrecorded",
        task=task,
        seating=seating,
        transcript=transcript,
        verdict=verdict,
    )


async def _run_round(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    transcript: Transcript,
    *,
    round_number: int,
    profile: TaskProfile,
    writer: RunWriter | None,
    recourse: RecourseFrame | None = None,
) -> None:
    async def turn_for(speaker: Speaker) -> Turn:
        return await _debater_turn(
            task, context, config, seating, client, transcript,
            speaker=speaker, round_number=round_number, profile=profile,
            recourse=recourse,
        )

    if config.turn_style == "simultaneous":
        # Both requests are in flight before either is awaited, and neither
        # debater can see the other's current-round argument.
        results = await asyncio.gather(
            *(turn_for(speaker) for speaker in ORDER), return_exceptions=True
        )
        # Persist every turn that did complete *before* raising: losing a paid
        # generation because the other debater failed would be an own goal.
        failures = [r for r in results if isinstance(r, BaseException)]
        for result in results:
            if isinstance(result, Turn):
                _commit(transcript, result, writer)
        for failure in failures:
            # Both debaters can fail; log every cause, not just the first.
            log.error("round %d: %r", round_number, failure)
        for failure in failures:
            # Cancellation (e.g. the run timeout) must stay cancellation:
            # return_exceptions=True captures BaseException, and rewrapping it
            # would stop asyncio.timeout recognising its own cancellation.
            if isinstance(failure, asyncio.CancelledError):
                raise failure
        if failures:
            raise DebateFailure(
                f"round {round_number} failed: {failures[0]}"
            ) from failures[0]
    else:
        # Sequential: Alice's turn must exist before Bob's request is built, so
        # these are awaited in order rather than gathered.
        for speaker in ORDER:
            _commit(transcript, await turn_for(speaker), writer)


def _commit(transcript: Transcript, turn: Turn, writer: RunWriter | None) -> None:
    transcript.add(turn)
    if writer is not None:
        writer.record_turn(transcript)
    log.debug(
        "round %d %s: %d words (%s)",
        turn.round, turn.speaker, turn.word_count, turn.parse_mode,
    )
    if turn.parse_mode != "strict":
        # Salvaged or trailing-dropped output is a fact about the run, not an
        # implementation detail — surface it rather than burying it in JSON.
        log.warning(
            "round %d %s parsed as %s", turn.round, turn.speaker, turn.parse_mode
        )


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
) -> tuple[Any, Completion, int]:
    """Call the model, and on a format failure spend exactly one repair attempt.

    One bounded retry converts a class of run-killing hiccups into a logged
    annotation. More would select for compliant outputs and bias the sample.
    """
    completion = await _complete(
        client, model=model, messages=messages, temperature=temperature,
        config=config, meta=meta,
    )
    try:
        return parse(completion.content), completion, 0
    except MalformedOutputError as first_error:
        log.warning("%s output malformed (%s); attempting one repair", role, first_error)

    repair_messages = build_repair_messages(
        messages, completion.content, role=role, word_limit=word_limit
    )
    repaired = await _complete(
        client, model=model, messages=repair_messages, temperature=temperature,
        config=config, meta={**meta, "purpose": "repair"},
    )
    try:
        return parse(repaired.content), repaired, 1
    except MalformedOutputError as error:
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
) -> Completion:
    completion = await client.complete(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=config.max_tokens,
        reasoning_effort=config.reasoning_effort,
        meta=meta,
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


async def _debater_turn(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    transcript: Transcript,
    *,
    speaker: Speaker,
    round_number: int,
    profile: TaskProfile,
    recourse: RecourseFrame | None = None,
) -> Turn:
    messages = build_debater_messages(
        task, context, seating, config, transcript,
        speaker=speaker, round=round_number, profile=profile, recourse=recourse,
    )
    word_limit = config.word_limit_for(profile.key)
    (thinking, argument, parse_mode), completion, repairs = await _complete_with_repair(
        client,
        model=config.debater_model,
        messages=messages,
        temperature=config.debater_temperature,
        config=config,
        meta={
            "role": "debater",
            "speaker": str(speaker),
            "round": round_number,
            "purpose": "turn" if recourse is None else "recourse_turn",
        },
        parse=parse_debater_output,
        role="debater",
        word_limit=word_limit,
    )

    words = count_words(argument)
    if words > word_limit:
        # Recorded and warned, never truncated: cutting the text would inject an
        # edit the model did not author, applied unevenly between debaters.
        log.warning(
            "round %d %s ran to %d words against a %d-word limit",
            round_number, speaker, words, word_limit,
        )

    return Turn(
        round=round_number,
        speaker=speaker,
        answer_index=seating.answer_for(speaker),
        thinking=thinking,
        argument=argument,
        word_count=words,
        parse_mode=parse_mode,
        repair_attempts=repairs,
        finish_reason=completion.finish_reason,
        has_native_reasoning=completion.has_native_reasoning,
        call_id=completion.call_id,
        raw=completion.content,
    )


async def _judge(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    transcript: Transcript,
    *,
    profile: TaskProfile,
    writer: RunWriter | None,
) -> Verdict:
    messages = build_judge_messages(
        task, context, seating, config, transcript, profile=profile
    )
    (choice, reasoning, parse_mode), completion, repairs = await _complete_with_repair(
        client,
        model=config.judge_model,
        messages=messages,
        temperature=config.judge_temperature,
        config=config,
        meta={"role": "judge", "speaker": None, "round": None, "purpose": "judge"},
        parse=parse_judge_output,
        role="judge",
        word_limit=config.word_limit_for(profile.key),
    )

    answer_index = seating.answer_index_for_choice(choice)
    verdict = Verdict(
        choice=choice,
        answer_index=answer_index,
        parse_mode=parse_mode if repairs == 0 else f"{parse_mode}_after_repair",
        raw=completion.content,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(
            None if task.gold_index is None else answer_index == task.gold_index
        ),
        repair_attempts=repairs,
        reasoning=reasoning,
    )
    if writer is not None:
        writer.record_verdict(verdict, transcript)
    return verdict


# --------------------------------------------------------------------------- #
# recourse
# --------------------------------------------------------------------------- #


async def run_recourse(
    parent: RunRecord,
    challenge: Challenge,
    config: DebateConfig,
    client: ChatClient,
    *,
    writer: RunWriter,
    profile: TaskProfile | None = None,
) -> RecourseResult:
    """Contest one completed decision, to a ruling.

    The two protocols are one code path. ``recourse_rounds = 0`` — the
    judge-only protocol — simply runs the loop below zero times, so there is no
    branch anywhere that could let the two drift apart in anything but the
    number of exchanges.

    ``challenge`` arrives either already carrying its text (supplied from a
    file) or as a specification to generate one, in which case the first call of
    the run writes it.
    """
    profile = profile or PROFILES[parent.profile_key]
    # One transcript for the whole run, carrying the parent's turns and this
    # run's. The writer is what knows which of them are its own to record.
    transcript = compose_transcript(parent.transcript, Transcript())

    if challenge.origin == "generated":
        challenge = await _generate_challenge(
            parent, config, client, transcript, challenge=challenge, profile=profile
        )
    # Recorded before any round runs, so a recourse that fails halfway still
    # says on disk what was being contested.
    writer.record_challenge(challenge, transcript)

    frame = RecourseFrame.from_record(
        challenge_text=challenge.text,
        parent_answer_index=parent.verdict.answer_index,
        parent_verdict_raw=parent.verdict.raw,
        parent_rounds=parent.config.n_rounds,
        n_recourse_rounds=config.recourse_rounds,
    )

    for offset in range(1, config.recourse_rounds + 1):
        await _run_round(
            parent.task, parent.context, config, parent.seating, client, transcript,
            round_number=parent.config.n_rounds + offset,
            profile=profile, writer=writer, recourse=frame,
        )

    ruling = await _recourse_judge(
        parent, config, client, transcript, frame=frame, profile=profile, writer=writer
    )
    _, own = transcript.split_at(parent.config.n_rounds)
    return RecourseResult(
        run_id=writer.run_id,
        parent_run_id=parent.run_id,
        task=parent.task,
        seating=parent.seating,
        challenge=challenge,
        transcript=own,
        ruling=ruling,
    )


async def _generate_challenge(
    parent: RunRecord,
    config: DebateConfig,
    client: ChatClient,
    transcript: Transcript,
    *,
    challenge: Challenge,
    profile: TaskProfile,
) -> Challenge:
    """Write a challenge to the parent's decision, and record how.

    Reuses the debater's ``Thinking:`` / ``Argument:`` output format, so the
    generator gets a private scratchpad, and the existing parser, repair path,
    response re-parse and private-reasoning containment scan all apply to it
    without a line of new machinery.
    """
    messages = build_challenger_messages(
        parent.task, parent.context, parent.seating, config, transcript,
        arm=challenge.arm,
        visibility=challenge.visibility,
        decision_answer_index=parent.verdict.answer_index,
        decision_grounds=parent.verdict.raw,
        profile=profile,
    )
    model = config.challenger_model_for()
    word_limit = config.challenge_word_limit_for(profile.key)
    (thinking, text, parse_mode), completion, repairs = await _complete_with_repair(
        client,
        model=model,
        messages=messages,
        temperature=config.debater_temperature,
        config=config,
        meta={
            "role": "challenger",
            "speaker": None,
            "round": None,
            "purpose": "challenge",
        },
        parse=parse_debater_output,
        role="challenger",
        word_limit=word_limit,
    )
    words = count_words(text)
    if words > word_limit:
        log.warning(
            "the generated challenge ran to %d words against a %d-word limit",
            words, word_limit,
        )
    log.info("generated a %s challenge (%d words)", challenge.arm, words)
    return Challenge(
        text=text,
        origin="generated",
        source=None,
        arm=challenge.arm,
        visibility=challenge.visibility,
        model=model,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        parse_mode=parse_mode,
        repair_attempts=repairs,
        thinking=thinking,
        raw=completion.content,
    )


async def _recourse_judge(
    parent: RunRecord,
    config: DebateConfig,
    client: ChatClient,
    transcript: Transcript,
    *,
    frame: RecourseFrame,
    profile: TaskProfile,
    writer: RunWriter | None,
) -> Ruling:
    messages = build_judge_messages(
        parent.task, parent.context, parent.seating, config, transcript,
        profile=profile, recourse=frame,
    )
    (word, reasoning, parse_mode), completion, repairs = await _complete_with_repair(
        client,
        model=config.judge_model,
        messages=messages,
        temperature=config.judge_temperature,
        config=config,
        meta={
            "role": "recourse_judge",
            "speaker": None,
            "round": None,
            "purpose": "rule",
        },
        parse=parse_ruling_output,
        role="recourse_judge",
        word_limit=config.word_limit_for(profile.key),
    )

    # Derived, never parsed: the judge rules on the challenge, and which answer
    # that leaves standing follows from the ruling and the original decision.
    answer_index = resolve_ruling(word, parent.verdict.answer_index)
    gold = parent.task.gold_index
    ruling = Ruling(
        ruling=word,
        upheld=word == "UPHOLD",
        protocol=frame.protocol,
        parent_answer_index=parent.verdict.answer_index,
        parent_choice=parent.verdict.choice,
        answer_index=answer_index,
        choice=parent.seating.choice_for_answer(answer_index),
        parse_mode=parse_mode if repairs == 0 else f"{parse_mode}_after_repair",
        raw=completion.content,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=None if gold is None else answer_index == gold,
        repair_attempts=repairs,
        reasoning=reasoning,
    )
    if writer is not None:
        writer.record_ruling(ruling, transcript)
    return ruling
