"""Fixture constructors for the outcome-controlled arms.

Not decision procedures — ``arms.py`` holds those. These build the *record* an
arm publishes when ``config.outcome_control`` is on, and they own exactly one
invariant:

    **the decisive bytes are FindTheFlaws', unaltered.**

Under seed-and-hope, each arm was handed the flawed reasoning and left to reach
its own conclusion, so the three arms carried three differently-worded versions
of "the same" flaw and a cross-arm detection rate compared three different
detection problems. Here the ``single`` arm's whole output, the
``self_critique`` arm's revision, and the ``debate`` arm's round-1 arguments are
the dataset's own text, so a challenger meets the identical flaw in every arm
and one annotation grades all three.

What is still generated is what makes each arm the shape it is: the
self-critique's draft and critique, and the debate's later rounds and judgment.

Nothing here may show a model ``ErrorSpec.annotation`` or
``ErrorSpec.flaw_location``. Those are the grader's ground truth. The injector
is told which step to *target*, never where the case's own flaw is, so nothing
it writes can be conditioned on the answer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any

from .client import ChatClient
from .config import DebateConfig, GradingConfig
from .engine import DebateFailure, _complete, _complete_with_repair
from .persistence import RunWriter
from .prompts import (
    CRITIQUE_STEER,
    INJECTOR_SYSTEM,
    INJECTOR_USER,
    TaskProfile,
    build_solo_messages,
    parse_injection_output,
    select_profile,
)
from .types import (
    ErrorSpec,
    Seating,
    Step,
    Task,
    Trace,
    Verdict,
    Context,
    count_words,
    neutralise_tags,
    render_trace,
)

log = logging.getLogger(__name__)

# What a step's ``parse_mode`` says when there was nothing to parse. The
# existing values both describe an outcome of reading a model's reply;
# ``salvaged_no_thinking`` in particular would claim a reply was recovered.
# Constructed text was never a reply at all, and the record should say so.
CONSTRUCTED = "constructed"

# ``mechanism`` values. ``genuine`` and ``manufactured`` are ErrorSpec's own;
# ``constructed`` is added here for a decision no procedure ever made.
GENUINE = "genuine"
MANUFACTURED = "manufactured"

# How far the injected draft may drift from the solution it was built from
# before it stops being that solution with one error added. A model that
# rewrites wholesale destroys the FindTheFlaws flaw without saying so, and the
# record would then carry a flaw nothing annotates.
_LENGTH_TOLERANCE = 0.40

# Steps are numbered lines: "Step 3: ..." in TheoremQA, "3. ..." in GPQA.
_STEP_RE = re.compile(r"(?im)^\s*Step\s*(\d+)")
_BARE_STEP_RE = re.compile(r"(?im)^\s*(\d+)[:.)]")


class ConstructionError(DebateFailure):
    """A fixture that did not come out as specified.

    A ``DebateFailure``, so ``experiment.CELL_FATAL`` already covers it: the
    attempt is written to disk marked failed, the reason is classified and
    counted, and the cell is retried. A construction that cannot be made
    correctly must never be published as though it had been.
    """


def solution_steps(text: str) -> list[int]:
    """The step numbers a solution is written in, in ascending order."""
    found = {int(m.group(1)) for m in _STEP_RE.finditer(text)}
    if not found:
        found = {int(m.group(1)) for m in _BARE_STEP_RE.finditer(text)}
    return sorted(found)


def target_step_for(error: ErrorSpec) -> int:
    """Which step the injected error goes at: any step but the case's own.

    Keeping the two flaws on different steps is what makes the construction
    checkable on a subset whose annotation is a step number and nothing else
    (FindTheFlaws' GPQA carries ``annotation_quality="location_only"`` with an
    empty annotation). With the flaws disjoint, *localisation alone* tells them
    apart, and the missing description stops mattering.

    Raises when the solution has no second step to use. That is 1 case in 282
    across the two subsets in play, and dropping it loudly is better than
    quietly injecting on top of the flaw the case is about.
    """
    steps = solution_steps(error.seed)
    flaw = error.flaw_location.strip()
    candidates = [s for s in steps if str(s) != flaw]
    if not candidates:
        raise ConstructionError(
            f"case {error.error_id} has no step to inject into that is not the "
            f"flaw step ({flaw or 'unrecorded'}); steps found: {steps or 'none'}"
        )
    # The last available step, so the injected error sits downstream of the
    # case's own wherever possible and the critique has the whole solution in
    # view before reaching it.
    return candidates[-1]


def flawed_solution_text(task: Task, seating: Seating, error: ErrorSpec) -> str:
    """The dataset's flawed reasoning, plus the decision it implies.

    The ``single`` arm's entire output and the ``self_critique`` arm's revision,
    byte for byte. One function because "byte-identical across arms" is the
    whole design, and a second copy of this string would be one edit away from
    being a claim the records do not support.

    The answer line is a **choice number**, resolved through this run's seating.
    ``choice_order`` is drawn per run precisely so position carries no
    information, so a literal ``Answer: 2`` here would be correct on half the
    corpus and wrong on the other half — with every run still completing.
    """
    if task.gold_index is None:
        raise ConstructionError(
            f"outcome control needs a gold answer to know which side is flawed; "
            f"task {task.task_id} has none"
        )
    if not error.seed.strip():
        raise ConstructionError(f"case {error.error_id} carries no flawed reasoning")
    flawed_index = 1 - task.gold_index
    return f"{error.seed.strip()}\n\nAnswer: {seating.choice_for_answer(flawed_index)}"


def _constructed_step(index: int, stage: str, text: str) -> Step:
    """A step nothing generated.

    ``thinking`` is empty because nothing was thought. Writing a plausible
    private section here would put a fabricated statement into the one document
    the project's transparency claim rests on; ``render_solo_record`` already
    prints ``_(none recorded)_`` for it.
    """
    return Step(
        index=index,
        stage=stage,
        thinking="",
        text=text,
        word_count=count_words(text),
        parse_mode=CONSTRUCTED,
        repair_attempts=0,
        finish_reason=None,
        has_native_reasoning=False,
        call_id="",
        # No completion existed, so the honest ``raw`` is the text itself.
        # ``raw == text`` also reads, in the record, as "nothing was stripped".
        raw=text,
    )


def _verdict_from(trace: Trace, task: Task, seating: Seating) -> Verdict:
    """The decision a constructed trace records: always the flawed answer."""
    last = trace.all_steps()[-1]
    flawed_index = 1 - task.gold_index
    return Verdict(
        choice=seating.choice_for_answer(flawed_index),
        answer_index=flawed_index,
        parse_mode=CONSTRUCTED,
        raw=last.raw,
        call_id=last.call_id,
        finish_reason=last.finish_reason,
        correct=False,  # by construction: this is the error stratum
        repair_attempts=sum(s.repair_attempts for s in trace.all_steps()),
        reasoning=last.text,
        native_reasoning="",
        reasoning_withheld=False,
    )


async def construct_single(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    writer: RunWriter | None = None,
    profile: TaskProfile | None = None,
    error: ErrorSpec | None = None,
    grading: GradingConfig | None = None,
) -> Any:
    """The ``single`` arm under outcome control: one step, no calls at all.

    Signature matches the ``DECIDERS`` contract so ``decide_cell`` dispatches to
    it unchanged, but nothing is awaited and ``client`` is never touched. The
    published record is the case's flawed reasoning and the decision it implies,
    which is what makes it byte-identical to the ``self_critique`` revision and
    to the flawed side of the debate's round 1.
    """
    from .arms import SoloResult

    if error is None:
        raise ConstructionError(
            "outcome control constructs the record from the case's error spec; "
            f"task {task.task_id} was dispatched without one"
        )
    profile = profile or select_profile(task, context)
    trace = Trace()
    trace.add(_constructed_step(1, "answer", flawed_solution_text(task, seating, error)))
    verdict = _verdict_from(trace, task, seating)
    if writer is not None:
        writer.record_step(trace)
        writer.record_verdict(verdict, trace)
        # No procedure ran, so neither "fell for it" nor "had to be pushed"
        # describes this. Saying so is what keeps the genuine/manufactured
        # split meaning what it says for the arms that did run one.
        writer.record_mechanism(CONSTRUCTED)
    return SoloResult(
        run_id=getattr(writer, "run_id", ""),
        arm="single",
        task=task,
        seating=seating,
        trace=trace,
        verdict=verdict,
    )


async def _inject_error(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    client: ChatClient,
    *,
    error: ErrorSpec,
    target_step: int,
    profile: TaskProfile,
) -> tuple[Step, str]:
    """Build the draft: the case's flawed solution plus one more error.

    Backward construction. Read forward — "write a draft with two errors, then
    critique one away" — the revision would have to *land on* FindTheFlaws'
    text, which was written independently and will not resemble the draft minus
    an error. Built this way the revision is simply the original, restored.

    Returns the draft step and the injector's description of what it added. That
    description is the annotation the critique is graded against, and it is
    ground truth: it goes to ``construction.json``, never to a prompt.
    """
    messages = [
        {"role": "system", "content": INJECTOR_SYSTEM},
        {
            "role": "user",
            "content": INJECTOR_USER.format(
                question=task.question,
                # The seed only. Not ``annotation``, not ``flaw_location``: the
                # injector is told which step to target and nothing about where
                # the case's own flaw lives.
                solution=neutralise_tags(error.seed.strip()),
                target_step=target_step,
            ),
        },
    ]
    parsed, completion, repairs = await _complete_with_repair(
        client,
        model=config.debater_model,
        messages=messages,
        temperature=config.debater_temperature,
        config=config,
        meta={"role": "injector", "purpose": "inject"},
        parse=parse_injection_output,
        role="injector",
        word_limit=config.word_limit_for(profile.key),
    )
    thinking, draft, injected_error, parse_mode = parsed

    original = error.seed.strip()
    if draft.strip() == original:
        raise ConstructionError(
            f"injector returned the solution unchanged for {error.error_id}"
        )
    drift = abs(len(draft) - len(original)) / max(len(original), 1)
    if drift > _LENGTH_TOLERANCE:
        raise ConstructionError(
            f"injector rewrote the solution for {error.error_id} "
            f"({drift:.0%} length change, tolerance {_LENGTH_TOLERANCE:.0%}); "
            f"the case's own flaw may not have survived"
        )

    step = Step(
        index=1,
        stage="draft",
        thinking=thinking,
        text=draft,
        word_count=count_words(draft),
        parse_mode=parse_mode,
        repair_attempts=repairs,
        finish_reason=completion.finish_reason,
        has_native_reasoning=completion.has_native_reasoning,
        call_id=completion.call_id,
        raw=completion.content,
        native_reasoning=completion.reasoning or "",
        reasoning_withheld=completion.reasoning_withheld,
    )
    return step, injected_error


async def _critique(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    trace: Trace,
    profile: TaskProfile,
    steer_to: int | None = None,
) -> Step:
    """The critique step, prompted exactly as the generative arm prompts it.

    ``steer_to`` appends the constraint that confines the critique to one step.
    It is applied only on a second attempt, after an unsteered one has been made
    and its outcome recorded, so how often the steer is needed stays a
    measurement rather than a setting.
    """
    messages = build_solo_messages(
        task, context, seating, config, render_trace(trace.visible_to(2)),
        stage="critique", profile=profile,
    )
    if steer_to is not None:
        messages[-1]["content"] += CRITIQUE_STEER.format(target_step=steer_to)
    completion = await _complete(
        client,
        model=config.debater_model,
        messages=messages,
        temperature=config.debater_temperature,
        config=config,
        meta={"role": "critic", "purpose": "critique"},
    )
    text = completion.content.strip()
    return Step(
        index=2,
        stage="critique",
        # The critique has no format contract and spends no repair attempt,
        # exactly as in the generative arm: it produces no answer, so there is
        # nothing a malformed reply could corrupt.
        thinking="",
        text=text,
        word_count=count_words(text),
        parse_mode="none",
        repair_attempts=0,
        finish_reason=completion.finish_reason,
        has_native_reasoning=completion.has_native_reasoning,
        call_id=completion.call_id,
        raw=completion.content,
        native_reasoning=completion.reasoning or "",
        reasoning_withheld=completion.reasoning_withheld,
    )


async def _critique_verdict(
    task: Task,
    seating: Seating,
    client: ChatClient,
    *,
    critique_text: str,
    error: ErrorSpec,
    injected_error: str,
    target_step: int,
    config: DebateConfig,
    grading: GradingConfig,
) -> tuple[bool, bool]:
    """``(caught_the_seeded_flaw, caught_the_injected_one)``.

    Two independent gradings, both off the decision path (``role="grader"``, so
    ``accounting.OFF_PATH_ROLES`` keeps them out of decision totals — they are
    construction QC, not decision compute).

    The seeded check grades against ``flaw_location`` and is deliberately
    **strict**: anything pointing at the flaw's step counts as having caught it.
    That is exactly ``ObjectionGrade.found_the_flaw``. Being strict is what lets
    the check work on a subset with no flaw description at all, given the two
    flaws are on different steps by construction.

    The injected check grades against an annotation we authored, so it carries a
    real explanation on every subset regardless of what upstream supplied.
    """
    from .grading import grade_objection

    seeded = await grade_objection(
        task=task, seating=seating,
        subject_text=critique_text, subject_kind="critique",
        error=error,
        decision_answer_index=1 - task.gold_index,
        config=config, grading=grading, client=client,
    )
    decoy = await grade_objection(
        task=task, seating=seating,
        subject_text=critique_text, subject_kind="critique",
        # Our own annotation: an explanation, whatever the subset supplies.
        error=replace(
            error,
            error_id=f"{error.error_id}-injected",
            annotation=injected_error,
            annotation_quality="explanation",
            flaw_location=str(target_step),
        ),
        decision_answer_index=1 - task.gold_index,
        config=config, grading=grading, client=client,
    )
    return seeded.found_the_flaw, decoy.found_the_flaw


async def construct_self_critique(
    task: Task,
    context: Context | None,
    config: DebateConfig,
    seating: Seating,
    client: ChatClient,
    *,
    writer: RunWriter | None = None,
    profile: TaskProfile | None = None,
    error: ErrorSpec | None = None,
    grading: GradingConfig | None = None,
) -> Any:
    """The ``self_critique`` arm under outcome control.

    draft -> critique -> revision, where the revision is the case's flawed text
    restored, byte-identical to the ``single`` arm's output. The draft is that
    same text with one *additional* error injected at a step the case's own flaw
    is not on, and the critique's job is to find that added error and leave the
    case's own standing.

    A critique that catches the case's own flaw is self-critique working, and it
    is also a record that criticises a step the revision then keeps. So the
    unsteered attempt runs first and its outcome is recorded — how often it
    happens is a finding — and only then is a steered attempt made.
    """
    from .arms import SoloResult
    from .config import load_grading_config
    from .grading import references_the_steer

    if error is None:
        raise ConstructionError(
            "outcome control constructs the record from the case's error spec; "
            f"task {task.task_id} was dispatched without one"
        )
    profile = profile or select_profile(task, context)
    grading = grading or load_grading_config()
    target_step = target_step_for(error)

    trace = Trace()
    draft, injected_error = await _inject_error(
        task, context, config, client,
        error=error, target_step=target_step, profile=profile,
    )
    trace.add(draft)
    if writer is not None:
        writer.record_step(trace)

    async def attempt(steer_to: int | None) -> tuple[Step, bool, bool]:
        """One critique and its two gradings."""
        candidate = await _critique(
            task, context, config, seating, client,
            trace=trace, profile=profile, steer_to=steer_to,
        )
        caught_seeded, caught_injected = await _critique_verdict(
            task, seating, client,
            critique_text=candidate.text, error=error,
            injected_error=injected_error, target_step=target_step,
            config=config, grading=grading,
        )
        if caught_seeded or not caught_injected:
            log.info(
                "%s critique rejected (seeded=%s injected=%s, steered=%s)",
                error.error_id, caught_seeded, caught_injected, steer_to is not None,
            )
        return candidate, caught_seeded, caught_injected

    def refuse(caught_seeded: bool) -> ConstructionError:
        return ConstructionError(
            "critique_caught_the_seeded_flaw"
            if caught_seeded
            else "critique_missed_the_injected_error"
        )

    # Unsteered first, always. A critique that catches the case's own flaw is
    # self-critique working, and how often that happens is a finding — so it is
    # measured before it is suppressed. No containment check here: there was no
    # steer to reference, so it would cost a call to learn nothing.
    critique, caught_natural, caught_injected = await attempt(None)
    steered = False
    leak_retries = 0

    if caught_natural or not caught_injected:
        critique = None
        # Two steered attempts. Each must pass the gradings *and* say nothing
        # about having been steered.
        for index in range(2):
            candidate, caught_seeded, caught_injected = await attempt(target_step)
            if caught_seeded or not caught_injected:
                raise refuse(caught_seeded)
            leak = await references_the_steer(
                steer_text=CRITIQUE_STEER.format(target_step=target_step),
                # The provider channel as well as the text: for a critique step
                # ``_solo_steps`` publishes the provider reasoning verbatim, so
                # a narration of the steer there is as public as the critique.
                output_text=f"{candidate.raw}\n\n{candidate.native_reasoning}",
                config=config, grading=grading, client=client,
            )
            if not leak.leaked:
                critique, steered = candidate, True
                break
            leak_retries = index + 1
            log.warning(
                "%s steered critique referenced the steer (%s); attempt %d of 2",
                error.error_id, leak.note[:120], index + 1,
            )
        if critique is None:
            raise ConstructionError("steered_critique_referenced_the_steer")
    trace.add(critique)
    if writer is not None:
        writer.record_step(trace)

    trace.add(_constructed_step(3, "revision", flawed_solution_text(task, seating, error)))
    verdict = _verdict_from(trace, task, seating)
    if writer is not None:
        writer.record_step(trace)
        writer.record_verdict(verdict, trace)
        writer.record_construction({
            "arm": "self_critique",
            "target_step": target_step,
            "flaw_step": error.flaw_location,
            "injected_error": injected_error,
            "critique_steered": steered,
            "critique_caught_the_seeded_flaw_unsteered": caught_natural,
            "critique_steer_leaked": False,
            "critique_steer_leak_retries": leak_retries,
        })
        # Steering was needed exactly when the unsteered critique caught the
        # case's own flaw. That is the manufactured/genuine distinction for this
        # arm: manufactured means the record only holds together because the
        # critique was constrained.
        writer.record_mechanism(MANUFACTURED if steered else GENUINE)

    return SoloResult(
        run_id=getattr(writer, "run_id", ""),
        arm="self_critique",
        task=task,
        seating=seating,
        trace=trace,
        verdict=verdict,
    )


def opening_turns(task: Task, seating: Seating, error: ErrorSpec) -> list[Any]:
    """Round 1 as the two FindTheFlaws solutions, verbatim.

    ``seeded_case_for`` already routes ``sound_seed`` to whoever defends the
    gold answer and ``seed`` to its opponent, keyed on ``task.gold_index``.
    Under outcome control that text *is* the argument rather than the private
    case behind one, so the flaw the judge and the challenger read is the
    dataset's own bytes and not a debater's paraphrase of them.

    Written the wrong way round this hands the correct solution to the debater
    arguing the wrong answer on half the corpus, and every run still completes —
    hence the keying on ``gold_index`` and the test that covers both values.
    """
    from .types import ORDER, Turn, seeded_case_for

    if task.gold_index is None:
        raise ConstructionError(
            f"outcome control needs a gold answer; task {task.task_id} has none"
        )
    turns = []
    for speaker in ORDER:
        argument = seeded_case_for(
            speaker=speaker, seating=seating, task=task, error=error
        )
        if not argument.strip():
            raise ConstructionError(
                f"case {error.error_id} has no reasoning for {speaker} to open with"
            )
        turns.append(
            Turn(
                round=1,
                speaker=speaker,
                answer_index=seating.answer_for(speaker),
                thinking="",
                argument=argument.strip(),
                word_count=count_words(argument),
                parse_mode=CONSTRUCTED,
                repair_attempts=0,
                finish_reason=None,
                has_native_reasoning=False,
                call_id="",
                raw=argument.strip(),
            )
        )
    return turns
