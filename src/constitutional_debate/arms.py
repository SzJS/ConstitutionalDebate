"""The decision procedures debate is compared against.

Three arms produce the same thing — a ``Verdict`` — by different means:

- ``debate``        two assigned advocates and a judge (in ``debate.py``)
- ``single``        one agent, one pass
- ``self_critique`` one agent: draft -> critique -> revision

Keeping ``Verdict`` universal is what makes every downstream metric
arm-independent. What varies is the *body* of the decision: a ``Transcript`` of
``Turn``s for debate, a ``Trace`` of ``Step``s for the solo arms.

**The critique is published.** If only the revision were recorded, a challenger
reading a self-critique record would never see the adversarial work, and the arm
would be unmatched against debate by construction — it would look like a single
agent that happened to be more careful. Publishing draft, critique and revision
makes the two arms differ in dialogue *structure* rather than in how much of the
reasoning survives into the record, which is the comparison worth running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .client import ChatClient
from .config import DebateConfig
from .engine import _complete, _complete_with_repair
from .persistence import RunWriter
from .prompts import (
    PROFILES,
    TaskProfile,
    build_solo_messages,
    parse_solo_output,
    select_profile,
)
from .types import (
    Context,
    ErrorSpec,
    Seating,
    Step,
    Task,
    Trace,
    Verdict,
    count_words,
    render_trace,
    seeded_case_for_solo,
)

log = logging.getLogger(__name__)


@dataclass
class SoloResult:
    """A decision reached without a debate."""

    run_id: str
    arm: str
    task: Task
    seating: Seating
    trace: Trace
    verdict: Verdict


async def run_single_agent(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    writer: RunWriter | None = None,
    profile: TaskProfile | None = None,
    error: ErrorSpec | None = None,
) -> SoloResult:
    """One agent, one pass: the baseline `DESIGN.md` §0 names first.

    Under ``outcome_control`` the pass is not made: the record is constructed
    from the case's own flawed reasoning, so the flaw a challenger reads here is
    byte-identical to the one it reads in the other two arms. See
    ``construct.construct_single``.
    """
    if config.outcome_control:
        # Deferred: ``construct`` imports this module for ``SoloResult``.
        from .construct import construct_single

        return await construct_single(
            task, context, config, seating, client,
            writer=writer, profile=profile, error=error,
        )
    return await _run_solo(
        task, context, config, seating, client,
        stages=("answer",), arm="single", writer=writer, profile=profile, error=error,
    )


async def run_self_critique(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    writer: RunWriter | None = None,
    profile: TaskProfile | None = None,
    error: ErrorSpec | None = None,
) -> SoloResult:
    """Draft, then criticise the draft, then revise — all three published.

    ``n_critique_rounds`` repeats the critique/revision pair. The critique step
    is deliberately left honest: if it catches the seeded flaw, that is a result
    about self-critique, not a bug to suppress.

    Under ``outcome_control`` the revision is the case's flawed text restored
    and the draft is that text with one error injected elsewhere, so the
    critique has something to find that is not the case's own flaw. See
    ``construct.construct_self_critique``.
    """
    if config.outcome_control:
        from .construct import construct_self_critique

        return await construct_self_critique(
            task, context, config, seating, client,
            writer=writer, profile=profile, error=error,
        )
    stages: list[str] = ["draft"]
    for _ in range(max(1, config.n_critique_rounds)):
        stages += ["critique", "revision"]
    return await _run_solo(
        task, context, config, seating, client,
        stages=tuple(stages), arm="self_critique",
        writer=writer, profile=profile, error=error,
    )


async def _run_solo(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    stages: tuple[str, ...],
    arm: str,
    writer: RunWriter | None,
    profile: TaskProfile | None,
    error: ErrorSpec | None,
) -> SoloResult:
    profile = profile or select_profile(task, context)
    trace = Trace()
    choice: int | None = None

    for index, stage in enumerate(stages, start=1):
        # Seeded only on the first step, as in the debate arm: after that the
        # case is in the trace, and repeating it would let the agent re-read its
        # script rather than engage with its own critique.
        seeded = (
            seeded_case_for_solo(task=task, error=error) if index == 1 else ""
        )
        messages = build_solo_messages(
            task, context, seating, config, render_trace(trace.visible_to(index)),
            stage=stage, seeded_case=seeded, profile=profile,
        )
        meta = {
            "role": "critic" if stage == "critique" else "solo",
            "speaker": None,
            "round": None,
            "purpose": stage,
        }

        if stage == "critique":
            # No format contract: a critique produces no decision, so there is
            # nothing to parse and nothing a malformed reply could corrupt. It
            # therefore spends no repair attempt.
            completion = await _complete(
                # The critic's model, which defaults to the debater's. Set it
                # weaker and this arm adjudicates weakly while still drafting
                # strongly — the self-critique analogue of a weak judge.
                client, model=config.critic_model_for(), messages=messages,
                temperature=config.debater_temperature, config=config, meta=meta,
            )
            thinking, text, parse_mode, repairs = "", completion.content.strip(), "none", 0
        else:
            parsed, completion, repairs = await _complete_with_repair(
                client, model=config.debater_model, messages=messages,
                temperature=config.debater_temperature, config=config, meta=meta,
                parse=parse_solo_output, role="solo",
                word_limit=config.word_limit_for(profile.key),
            )
            thinking, text, choice, parse_mode = parsed

        step = Step(
            index=index, stage=stage, thinking=thinking, text=text,
            word_count=count_words(text), parse_mode=parse_mode,
            repair_attempts=repairs, finish_reason=completion.finish_reason,
            has_native_reasoning=completion.has_native_reasoning,
            call_id=completion.call_id, raw=completion.content,
            native_reasoning=completion.reasoning or "",
            reasoning_withheld=completion.reasoning_withheld,
        )
        trace.add(step)
        if writer is not None:
            writer.record_step(trace)
        log.debug("%s step %d (%s): %d words", arm, index, stage, step.word_count)

    if choice is None:  # unreachable: every stage tuple ends in a deciding stage
        raise RuntimeError(f"{arm} produced no decision")

    # The same resolution as the judge's, deliberately: "which answer did this
    # choice mean" is one rule, and two copies of it would be one ``1 -`` away
    # from silently inverting an arm.
    answer_index = seating.answer_index_for_choice(choice)
    verdict = Verdict(
        choice=choice,
        answer_index=answer_index,
        parse_mode=trace.all_steps()[-1].parse_mode,
        raw=trace.all_steps()[-1].raw,
        call_id=trace.all_steps()[-1].call_id,
        finish_reason=trace.all_steps()[-1].finish_reason,
        correct=None if task.gold_index is None else answer_index == task.gold_index,
        repair_attempts=sum(s.repair_attempts for s in trace.all_steps()),
        reasoning=trace.all_steps()[-1].text,
        native_reasoning=trace.all_steps()[-1].native_reasoning,
        reasoning_withheld=any(s.reasoning_withheld for s in trace.all_steps()),
    )
    if writer is not None:
        writer.record_verdict(verdict, trace)
    return SoloResult(
        run_id=writer.run_id if writer else "unrecorded",
        arm=arm, task=task, seating=seating, trace=trace, verdict=verdict,
    )


async def _run_debate_adapter(
    task, context, config, seating, client, *, writer=None, profile=None, error=None
):
    """``run_debate`` behind the same signature as the solo arms."""
    from .debate import run_debate

    return await run_debate(
        task, context, config, seating, client,
        writer=writer, profile=profile, error=error,
    )


# The one place an arm name maps to a procedure. A runner that dispatches
# through this cannot silently run a debate for an arm it does not implement —
# the failure that made ``arm`` a decorative manifest field.
DECIDERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "debate": _run_debate_adapter,
    "single": run_single_agent,
    "self_critique": run_self_critique,
}
