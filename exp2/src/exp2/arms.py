"""The three conditions, behind one dispatch table.

All three produce a ``Verdict``; what varies is the body that produced it. ``debate``
yields a ``Transcript`` of ``Turn``s; ``single`` and ``self_critique`` yield a
**conversation** — a real growing message list, not a sequence of independent calls.

That last point is the substantive difference from exp1, which rebuilt a two-message
prompt at every stage and pasted the prior steps into a ``<record>`` block. DESIGN.md
says a contest in the baseline conditions is "the user raising an objection during
chat", i.e. a new prompt *in the same conversation*, and exp1's shape cannot honestly
provide that: there was no conversation to append to. Here the conversation is the
artifact, ``conversation.json``, and the contest appends one user turn to it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .client import ChatClient
from .config import DebateConfig
from .engine import _complete_with_repair
from .prompts import (
    REPAIR_CARRYOVER_PREFIX,
    build_solo_opening,
    parse_debater_output,
    parse_verdict_output,
    solo_stage_instruction,
)
from .types import Item, Sides, Step, Trace, Verdict, count_words

log = logging.getLogger(__name__)


@dataclass
class SoloResult:
    run_id: str
    condition: str
    item: Item
    sides: Sides
    trace: Trace
    # The conversation exactly as it was sent and received, ending on an assistant turn.
    # A contest replays this and appends to it, so it has to be what actually happened —
    # including the two extra turns a format repair adds.
    messages: list[dict[str, str]]
    verdict: Verdict


def _solo_stages(condition: str, config: DebateConfig) -> tuple[str, ...]:
    if condition == "single":
        return ("answer",)
    # draft, then (critique, revision) * n. With n == n_rounds this is 1 + 2n calls
    # against debate's 2n + 1, which is what makes the conditions comparable on volume
    # rather than only on procedure.
    return ("draft", *(("critique", "revision") * config.n_critique_rounds))


# Published in place of a critique whose public section could not be located. The raw
# generation is still in the record files and in calls.jsonl; what is withheld is the
# claim that any particular part of it was the author's public text.
WITHHELD = "[this step's public section could not be identified and is withheld]"


def _split_solo(text: str) -> tuple[str, str, str]:
    """``(thinking, public, parse_mode)`` for any solo stage.

    The solo format labels its public half ``Reasoning:`` rather than ``Argument:``, so
    the debater parser is reused by relabelling rather than by a second implementation —
    the leak containment rules are the same and must not be allowed to drift apart.
    """
    thinking, public, parse_mode = parse_debater_output(
        text.replace("Reasoning:", "Argument:")
    )
    return thinking, public, parse_mode


def _parse_solo(text: str) -> tuple[str, str, str, str]:
    """``(thinking, reasoning, verdict, parse_mode)`` for a stage that decides."""
    thinking, reasoning, parse_mode = _split_solo(text)
    verdict, _, _ = parse_verdict_output(reasoning)
    return thinking, reasoning, verdict, parse_mode


def _withhold_critique(text: str) -> tuple[str, str, str]:
    """``(thinking, public, parse_mode)`` for a critique still unsplittable after repair.

    A critique has a private section and **is** published to the challenger as part of a
    self_critique record. Storing the raw generation would publish the model's own
    ``Thinking:`` block, which is precisely the leak the protocol exists to prevent — so
    when the split cannot be made the public text is withheld rather than guessed.
    Publishing everything would leak; guessing where the private part ends is worse than
    either. Unlike a verdict, a missing critique does not stop the run, so this is the
    last resort in place of the failure the deciding stages raise.
    """
    return "", WITHHELD, "unparsed_withheld"


async def _run_solo(
    item: Item,
    config: DebateConfig,
    sides: Sides,
    client: ChatClient,
    *,
    condition: str,
    writer: Any | None = None,
) -> SoloResult:
    stages = _solo_stages(condition, config)
    messages = build_solo_opening(item, sides, config, stage=stages[0])
    trace = Trace()
    last_verdict: str | None = None
    last: Step | None = None
    # Whether any earlier stage of THIS conversation spent a repair. A repair's
    # correction stays in context — the conversation carries every turn forward — and
    # pilot 2 measured the model obeying "do not write a Thinking section" for the rest
    # of the run: `salvaged_no_thinking` at 4.8% in the original pass and 51.0% in the
    # retry pass. The instruction now scopes itself ("For this reply only"); this is the
    # belt to that brace, and it is conditional so that an unrepaired run's prompts are
    # byte-identical to what they were.
    spent_a_repair = False

    for index, stage in enumerate(stages, start=1):
        if index > 1:
            prefix = REPAIR_CARRYOVER_PREFIX if spent_a_repair else ""
            messages = [*messages,
                        {"role": "user",
                         "content": prefix + solo_stage_instruction(stage, sides)}]

        if stage == "critique":
            # A critique has no decision line, but it does have a published section, and
            # a model that files the whole critique under ``Thinking:`` leaves the record
            # with a placeholder. So it gets the same one repair the deciding stages get,
            # and withholding is what happens only after that repair also fails.
            (thinking, text, parse_mode), completion, repairs, sent, repair_kind = (
                await _complete_with_repair(
                    client, model=config.critic_model_for(), messages=messages,
                    temperature=config.debater_temperature, config=config,
                    meta={"role": "critic", "speaker": None, "round": None,
                          "purpose": stage},
                    parse=_split_solo, role="critic", word_limit=config.word_limit,
                    max_tokens=config.generation_max_tokens,
                    public_label="Reasoning", unrepaired=_withhold_critique,
                )
            )
        else:
            (thinking, text, verdict_word, parse_mode), completion, repairs, sent, repair_kind = (
                await _complete_with_repair(
                    client, model=config.debater_model, messages=messages,
                    temperature=config.debater_temperature, config=config,
                    meta={"role": "solo", "speaker": None, "round": None,
                          "purpose": stage},
                    parse=_parse_solo, role="solo", word_limit=config.word_limit,
                    max_tokens=config.generation_max_tokens,
                    public_label="Reasoning",
                )
            )
            last_verdict = verdict_word
        # ``sent`` differs from ``messages`` exactly when a repair happened: it carries
        # the malformed reply and the correction. Taking it rather than ``messages`` is
        # what keeps the conversation a true record.
        messages = sent
        spent_a_repair = spent_a_repair or repairs > 0

        messages = [*messages, {"role": "assistant", "content": completion.content}]
        last = Step(
            index=index, stage=stage, thinking=thinking, text=text,
            word_count=count_words(text),
            # A budget repair is marked apart from a format repair: nothing was written
            # wrongly, the cap ran out before anything public was written at all.
            parse_mode=(f"{parse_mode}_after_budget_repair"
                        if repair_kind == "budget" else parse_mode),
            repair_attempts=repairs, finish_reason=completion.finish_reason,
            has_native_reasoning=completion.has_native_reasoning,
            call_id=completion.call_id, raw=completion.content,
            native_reasoning=completion.reasoning,
            reasoning_withheld=completion.reasoning_withheld,
        )
        trace.add(last)
        if writer is not None:
            writer.record_step(trace)
            writer.record_messages(messages)

    assert last is not None and last_verdict is not None
    verdict = Verdict(
        verdict=last_verdict, parse_mode=last.parse_mode, raw=last.raw,
        call_id=last.call_id, finish_reason=last.finish_reason,
        correct=(last_verdict == item.gold_verdict),
        repair_attempts=sum(s.repair_attempts for s in trace.all_steps()),
        reasoning=last.text, native_reasoning=last.native_reasoning,
        reasoning_withheld=any(s.reasoning_withheld for s in trace.all_steps()),
    )
    if writer is not None:
        writer.record_verdict(verdict, trace)
    return SoloResult(
        run_id=getattr(writer, "run_id", "unrecorded"), condition=condition,
        item=item, sides=sides, trace=trace, messages=messages, verdict=verdict,
    )


async def run_single(item, config, sides, client, *, writer=None) -> SoloResult:
    return await _run_solo(item, config, sides, client, condition="single", writer=writer)


async def run_self_critique(item, config, sides, client, *, writer=None) -> SoloResult:
    return await _run_solo(
        item, config, sides, client, condition="self_critique", writer=writer
    )


async def _run_debate_adapter(item, config, sides, client, *, writer=None):
    from .debate import run_debate  # deferred: debate imports nothing from arms

    return await run_debate(item, config, sides, client, writer=writer)


# The one dispatch table. Adding a condition means adding it here and nowhere else.
DECIDERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "single": run_single,
    "self_critique": run_self_critique,
    "debate": _run_debate_adapter,
}
CONDITIONS: tuple[str, ...] = tuple(DECIDERS)
