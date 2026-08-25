"""The debate protocol: rounds of simultaneous argument, then one judgement.

Ported from exp1 with the outcome-control machinery removed — nothing here steers a
judge, injects an error, or inserts a fixture round. The round scheduler and its error
handling are unchanged, because both encode things that cost real runs to learn.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .client import ChatClient
from .config import DebateConfig
from .engine import DebateFailure, _complete_with_repair
from .prompts import build_debater_messages, build_judge_messages, parse_debater_output, parse_verdict_output
from .types import (
    ORDER,
    DebateResult,
    Item,
    Sides,
    Speaker,
    Transcript,
    Turn,
    Verdict,
    count_words,
)

log = logging.getLogger(__name__)


async def run_debate(
    item: Item,
    config: DebateConfig,
    sides: Sides,
    client: ChatClient,
    *,
    writer: Any | None = None,
) -> DebateResult:
    """Run the rounds, then judge once over the whole transcript."""
    transcript = Transcript()
    for round_number in range(1, config.n_rounds + 1):
        await _run_round(
            item, config, sides, client, transcript,
            round_number=round_number, writer=writer,
        )
    verdict = await _judge(item, config, sides, client, transcript, writer=writer)
    return DebateResult(
        run_id=getattr(writer, "run_id", "unrecorded"),
        item=item, sides=sides, transcript=transcript, verdict=verdict,
    )


async def _run_round(
    item: Item,
    config: DebateConfig,
    sides: Sides,
    client: ChatClient,
    transcript: Transcript,
    *,
    round_number: int,
    writer: Any | None,
) -> None:
    async def turn_for(speaker: Speaker) -> Turn:
        return await _debater_turn(
            item, config, sides, client, transcript,
            speaker=speaker, round_number=round_number,
        )

    if config.turn_style == "simultaneous":
        results = await asyncio.gather(
            *(turn_for(speaker) for speaker in ORDER), return_exceptions=True
        )
        # Commit every turn that completed *before* raising. Losing a paid generation
        # because the other debater failed would be an own goal, and the partial
        # transcript is still a true record of what was said.
        for result in results:
            if isinstance(result, Turn):
                _commit(transcript, result, writer)
        for result in results:
            if isinstance(result, BaseException):
                # Unwrapped, so an enclosing asyncio.timeout still recognises its own
                # cancellation rather than seeing a DebateFailure it cannot attribute.
                if isinstance(result, asyncio.CancelledError):
                    raise result
                raise DebateFailure(
                    f"round {round_number} failed: {result}"
                ) from result
    else:
        for speaker in ORDER:
            _commit(transcript, await turn_for(speaker), writer)


def _commit(transcript: Transcript, turn: Turn, writer: Any | None) -> None:
    transcript.add(turn)
    if writer is not None:
        writer.record_turn(transcript)
    if turn.parse_mode != "strict":
        log.warning(
            "round %d %s parsed as %s", turn.round, turn.speaker.value, turn.parse_mode
        )


async def _debater_turn(
    item: Item,
    config: DebateConfig,
    sides: Sides,
    client: ChatClient,
    transcript: Transcript,
    *,
    speaker: Speaker,
    round_number: int,
) -> Turn:
    messages = build_debater_messages(
        item, sides, config, transcript, speaker=speaker, round_number=round_number
    )
    model = sides.model_for(speaker, config.debater_model, config.debater_model_b)
    (thinking, argument, parse_mode), completion, repairs, _ = await _complete_with_repair(
        client,
        model=model,
        messages=messages,
        temperature=config.debater_temperature,
        config=config,
        meta={
            "role": "debater", "speaker": speaker.value, "round": round_number,
            "purpose": "turn",
            "model_side": "b" if model == config.debater_model_b else "a",
        },
        parse=parse_debater_output,
        role="debater",
        word_limit=config.word_limit,
    )
    words = count_words(argument)
    if config.word_limit and words > config.word_limit:
        # Recorded, never truncated: cutting the text would inject an edit the model
        # did not author into a document whose whole claim is that it is what was said.
        log.warning(
            "round %d %s wrote %d words over a %d-word limit",
            round_number, speaker.value, words, config.word_limit,
        )
    return Turn(
        round=round_number, speaker=speaker, side=sides.side_for(speaker),
        thinking=thinking, argument=argument, word_count=words,
        parse_mode=parse_mode, repair_attempts=repairs,
        finish_reason=completion.finish_reason,
        has_native_reasoning=completion.has_native_reasoning,
        call_id=completion.call_id, raw=completion.content,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


async def _judge(
    item: Item,
    config: DebateConfig,
    sides: Sides,
    client: ChatClient,
    transcript: Transcript,
    *,
    writer: Any | None,
) -> Verdict:
    messages = build_judge_messages(item, sides, config, transcript)
    (verdict_word, reasoning, parse_mode), completion, repairs, _ = await _complete_with_repair(
        client,
        model=config.judge_model,
        messages=messages,
        temperature=config.judge_temperature,
        config=config,
        meta={"role": "judge", "speaker": None, "round": None, "purpose": "judge"},
        parse=parse_verdict_output,
        role="judge",
        word_limit=config.word_limit,
    )
    verdict = Verdict(
        verdict=verdict_word,
        parse_mode=f"{parse_mode}_after_repair" if repairs else parse_mode,
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(verdict_word == item.gold_verdict),
        repair_attempts=repairs, reasoning=reasoning,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if writer is not None:
        writer.record_verdict(verdict, transcript)
    return verdict
