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
from .prompts import (
    build_debater_messages,
    build_judge_messages,
    parse_debater_output,
    findings_passage_counts,
    findings_passage_strict_counts,
    findings_trim_counts,
    parse_findings_output,
    parse_verdict_output,
)
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
    (thinking, argument, parse_mode), completion, repairs, _, repair_kind = await _complete_with_repair(
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
        max_tokens=config.generation_max_tokens,
        public_label="Argument",
    )
    return _turn_from_completion(
        thinking, argument, parse_mode, completion,
        repairs=repairs, repair_kind=repair_kind,
        round_number=round_number, speaker=speaker, side=sides.side_for(speaker),
        word_limit=config.word_limit,
    )


def _turn_from_completion(
    thinking: str,
    argument: str,
    parse_mode: str,
    completion: Any,
    *,
    repairs: int,
    repair_kind: str | None,
    round_number: int,
    speaker: Speaker,
    side: str,
    word_limit: int,
) -> Turn:
    """One parsed debater reply as a ``Turn``.

    Extracted so the contestability debate round (`recourse.hear_exchange`) builds its
    round-4 turns through the same code an ordinary round does. Two hand-rolled copies
    would be two chances to forget the budget-repair marking below, and a round-4 turn
    whose `parse_mode` under-reported a repair would put a repaired generation into a
    comparison of parse modes across the two arms.
    """
    words = count_words(argument)
    if word_limit and words > word_limit:
        # Recorded, never truncated: cutting the text would inject an edit the model
        # did not author into a document whose whole claim is that it is what was said.
        log.warning(
            "round %d %s wrote %d words over a %d-word limit",
            round_number, speaker.value, words, word_limit,
        )
    return Turn(
        round=round_number, speaker=speaker, side=side,
        thinking=thinking, argument=argument, word_count=words,
        # The budget repair is marked in ``parse_mode`` because it is not a format
        # failure and must not be counted as one: the model wrote nothing wrong, it ran
        # out of room before it wrote anything at all. ``repair_attempts`` counts both.
        parse_mode=(f"{parse_mode}_after_budget_repair"
                    if repair_kind == "budget" else parse_mode),
        repair_attempts=repairs,
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
    findings: list[dict[str, Any]] | None = None
    if config.judge_form == "findings":
        # THE SAME WIRE ROLE, a different repair role, and a four-element parse. The wire
        # role is what `accounting` reads and what `artifacts_full` looks a call up by,
        # and a findings judgment is the same decision-path judge call a verdict
        # judgment is — so it stays `judge` and every cost table is untouched. Only the
        # REPAIR differs, because `JUDGE_REPAIR` asks for "Verdict: FLAWED" and a
        # findings judge sent that would be asked for a format its parser refuses,
        # burning the one repair on a prompt that could not have succeeded.
        #
        # No `public_label`, exactly as the verdict form has none: truncation stays fatal
        # here (the loss rule), because a half-written findings list is a judgment whose
        # missing entries are indistinguishable from findings the judge did not make.
        (verdict_word, findings, reasoning, parse_mode), completion, repairs, _, _ = (
            await _complete_with_repair(
                client,
                model=config.judge_model,
                messages=messages,
                temperature=config.judge_temperature,
                config=config,
                meta={"role": "judge", "speaker": None, "round": None,
                      "purpose": "judge"},
                parse=parse_findings_output,
                role="judge_findings",
                word_limit=config.word_limit,
            )
        )
    else:
        (verdict_word, reasoning, parse_mode), completion, repairs, _, _ = await _complete_with_repair(
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
        # `findings.json` FIRST, then `verdict.json` — the verdict is derived from the
        # list, so a crash between the two writes must leave a run with no verdict (which
        # `load_run_record` refuses as incomplete) rather than a verdict whose derivation
        # is missing.
        if findings is not None:
            # The two format measurements are taken HERE, where the item's own text and
            # the judge's own reply are both in hand, rather than re-derived later from a
            # tree: `findings_passage_counts` needs the solution the passages were
            # supposed to be copied from, and `findings_trim_counts` needs the untrimmed
            # reply. Report-only, both of them — see `record_findings`.
            passage_exact_n, duplicate_passage_n = findings_passage_counts(
                findings, item.solution)
            # The STRICT pair beside the lenient one (R11b, after smoke 2): a
            # case-sensitive substring test and an ellipsis-join count, taken from the
            # same two objects and reported the same way.
            passage_verbatim_n, passage_ellipsis_n = findings_passage_strict_counts(
                findings, item.solution)
            preamble_chars, trailing_chars = findings_trim_counts(
                completion.content, reasoning)
            writer.record_findings(findings, verdict=verdict_word,
                                   parse_mode=verdict.parse_mode,
                                   passage_exact_n=passage_exact_n,
                                   duplicate_passage_n=duplicate_passage_n,
                                   passage_verbatim_n=passage_verbatim_n,
                                   passage_ellipsis_n=passage_ellipsis_n,
                                   preamble_chars=preamble_chars,
                                   trailing_chars=trailing_chars)
        writer.record_verdict(verdict, transcript)
    return verdict
