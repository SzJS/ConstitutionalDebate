"""Measurement, off the decision path.

Three passes, all of which run *after* every decision is final:

- ``grade_objection`` — how close did a challenge come to the real flaw?
- ``validate_case``   — did the constructed error come out as intended?
- ``check_independence`` — did the recourse judge rule on the challenge, or
  quietly re-derive the answer and rule on that?

**This module is the only door to the error annotation.** ``load_run_record``
deliberately does not read ``error.json``; ``persistence.load_error_spec`` does,
and the functions below are its only callers. That containment is structural
rather than conventional: a decision procedure that could reach the annotation
would be reciting the flaw instead of finding it, and every rate measured
downstream would be measuring that.

Being off-path buys three things beyond correctness. These passes are
re-runnable over finished directories without re-spending a decision; their
calls carry roles that ``accounting.OFF_PATH_ROLES`` excludes, so grading can
never inflate the arm it grades; and a grader failure costs a measurement rather
than a run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .client import ChatClient
from .config import DebateConfig, GradingConfig
from .engine import _complete_with_repair
from .prompts import (
    GRADER_CLOSING_FULL,
    GRADER_CLOSING_LOCATION_ONLY,
    GRADER_SYSTEM,
    GRADER_USER,
    RULING_INDEPENDENCE_SYSTEM,
    VALIDATOR_SYSTEM,
    parse_grade_output,
    parse_independence_output,
    parse_validation_output,
)
from .types import ErrorSpec, Seating, Task, neutralise_tags

log = logging.getLogger(__name__)

# Enumerated so a third reader has to justify itself by failing a test. The
# invariant is not "the annotation is secret" — it is published in the case file
# — but "nothing on the decision path can reach it".
ERROR_SPEC_READERS: frozenset[str] = frozenset(
    {"grading.grade_objection", "grading.validate_case"}
)

SUBJECT_KINDS: tuple[str, ...] = ("challenge", "pro_argument")


@dataclass(frozen=True)
class ObjectionGrade:
    """How close an objection came to the flaw that was actually there.

    ``localisation`` is a three-level scale rather than a boolean because an
    objection that points at the right lines without saying what is wrong with
    them has genuinely detected the flaw. Scoring that as a miss would discard
    the single most interesting case — detection without articulation — which is
    precisely what a further round of debate might complete.
    """

    subject_kind: str
    localisation: int  # 0 | 1 | 2
    states_the_consequence: bool
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0
    reasoning: str = ""
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    @property
    def valid(self) -> bool:
        """The strict bar: characterised the error *and* carried it to the decision."""
        return self.localisation == 2 and self.states_the_consequence

    @property
    def found_the_flaw(self) -> bool:
        """The lenient bar, and the one the detection rate uses."""
        return self.localisation >= 1

    @property
    def underspecified(self) -> bool:
        """Reached something real and stalled short of the decision.

        Two distinct ways to stall — localised but not characterised, or
        characterised without the consequence — which the analysis reports
        separately because they say different things about where the funnel
        leaks.
        """
        return self.found_the_flaw and not self.valid

    def to_dict(self) -> dict[str, Any]:
        data = {f: getattr(self, f) for f in self.__dataclass_fields__}
        data.update(
            valid=self.valid,
            found_the_flaw=self.found_the_flaw,
            underspecified=self.underspecified,
        )
        return data


@dataclass(frozen=True)
class CaseValidation:
    """Whether a constructed error case came out as designed."""

    case_id: str
    fidelity: bool  # the realised flaw is the intended one
    survived: bool  # it is what drove the decision
    cross_arm_match: bool | None  # None when only one arm was shown
    note: str
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0

    @property
    def usable(self) -> bool:
        """Fit for the headline funnel.

        ``survived`` is the load-bearing half. A self-critique arm is *designed*
        to remove flaws; if its critique strips the intended one and the revision
        then lands wrong through some other slip, ``verdict.correct is False``
        is true and the case looks clean. Nothing else in the pipeline catches
        that.
        """
        return self.fidelity and self.survived and self.cross_arm_match is not False

    def to_dict(self) -> dict[str, Any]:
        data = {f: getattr(self, f) for f in self.__dataclass_fields__}
        data["usable"] = self.usable
        return data


@dataclass(frozen=True)
class RulingIndependence:
    """Whether the recourse judge answered the question it was asked."""

    re_derived: bool
    note: str
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


async def grade_objection(
    *,
    task: Task,
    seating: Seating,
    subject_text: str,
    subject_kind: str,
    error: ErrorSpec,
    decision_answer_index: int,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> ObjectionGrade:
    """Grade one objection against the known flaw.

    ``subject_kind`` is ``"challenge"`` for the challenger's own objection and
    ``"pro_argument"`` for the recourse debater's final argument. Grading both
    against the same annotation is what measures *specification lift*: given the
    challenge was underspecified, did the debate round carry it to valid?
    """
    if subject_kind not in SUBJECT_KINDS:
        raise ValueError(
            f"unknown subject_kind {subject_kind!r}; expected {SUBJECT_KINDS}"
        )

    # A location-only annotation cannot support level 2 — there is nothing to
    # check a characterisation against, so scoring one would be scoring the
    # grader's imagination. The prompt says so rather than the analysis
    # silently discarding the result later.
    graded_closing = (
        GRADER_CLOSING_FULL
        if error.grades_characterisation
        else GRADER_CLOSING_LOCATION_ONLY
    )
    messages = [
        {"role": "system", "content": GRADER_SYSTEM},
        {
            "role": "user",
            "content": GRADER_USER.format(
                question=task.question,
                decision_answer=task.answers[decision_answer_index],
                flaw_location=error.flaw_location or "[not recorded]",
                flaw_annotation=error.annotation or "[not recorded]",
                subject_kind=subject_kind,
                # Model-authored text into a tagged block, same as anywhere else.
                subject_text=neutralise_tags(subject_text),
                closing=graded_closing,
            ),
        },
    ]
    model = grading.grader_model_for(config.judge_model)
    (localisation, consequence, reasoning, parse_mode), completion, repairs = (
        await _complete_with_repair(
            client,
            model=model,
            messages=messages,
            temperature=grading.grader_temperature,
            config=config,
            meta={
                "role": "grader",
                "speaker": None,
                "round": None,
                "purpose": f"grade_{subject_kind}",
            },
            parse=parse_grade_output,
            role="grader",
            word_limit=0,
        )
    )
    if not error.grades_characterisation and localisation > 1:
        # The grader was told level 2 was unavailable and used it anyway. Clamp
        # rather than trust: the annotation genuinely does not support it.
        log.warning(
            "grader returned localisation 2 on a location-only annotation; clamping"
        )
        localisation = 1
    return ObjectionGrade(
        subject_kind=subject_kind,
        localisation=localisation,
        states_the_consequence=consequence,
        model=model,
        parse_mode=parse_mode if repairs == 0 else f"{parse_mode}_after_repair",
        raw=completion.content,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        repair_attempts=repairs,
        reasoning=reasoning,
        native_reasoning=completion.reasoning or "",
        reasoning_withheld=completion.reasoning_withheld,
    )


async def validate_case(
    *,
    case_id: str,
    task: Task,
    records: dict[str, str],
    error: ErrorSpec,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> CaseValidation:
    """Check that a constructed error case came out as designed.

    ``records`` maps arm name to that arm's rendered record. All arms go in
    **one** call rather than one call each: the cross-arm question can only be
    answered by seeing them together, and it is also three times cheaper.
    """
    rendered = "\n\n".join(
        f"<record arm=\"{arm}\">\n{neutralise_tags(text)}\n</record>"
        for arm, text in sorted(records.items())
    )
    user = (
        f"Question: {task.question}\n\n"
        f"**The intended flaw**\n"
        f"Where: {error.flaw_location or '[not recorded]'}\n"
        f"What: {error.annotation or '[not recorded]'}\n\n"
        f"**The records** ({len(records)} arm(s))\n{rendered}\n\n"
        + (
            "Only one record is shown, so answer NA for cross-arm match."
            if len(records) < 2
            else "Judge all three scales."
        )
    )
    (fidelity, survived, cross, note, parse_mode), completion, repairs = (
        await _complete_with_repair(
            client,
            model=grading.validator_model,
            messages=[
                {"role": "system", "content": VALIDATOR_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=grading.validator_temperature,
            config=config,
            meta={
                "role": "validator",
                "speaker": None,
                "round": None,
                "purpose": "validate_case",
            },
            parse=parse_validation_output,
            role="validator",
            word_limit=0,
        )
    )
    return CaseValidation(
        case_id=case_id,
        fidelity=fidelity,
        survived=survived,
        cross_arm_match=cross,
        note=note,
        model=grading.validator_model,
        parse_mode=parse_mode,
        raw=completion.content,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        repair_attempts=repairs,
    )


async def check_independence(
    *,
    ruling_reasoning: str,
    challenge_text: str,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> RulingIndependence:
    """Did the recourse judge rule on the challenge, or re-derive the answer?

    The second detector for a failure the ``specious`` arm catches only in
    aggregate. A strong recourse judge can work the answer out for itself and
    rule on whether the original decision matches its own conclusion — at which
    point a vague challenge succeeds whenever the decision happened to be wrong,
    and the correction rate stops measuring challenge quality entirely.

    Two independent detectors because the population-level one (specious
    challenges succeeding as often as grounded ones) needs a whole arm to see,
    while this one flags individual rulings and can be read by hand.
    """
    user = (
        f"**The challenge the judge was asked to rule on**\n"
        f"<challenge>\n{neutralise_tags(challenge_text)}\n</challenge>\n\n"
        f"**The judge's stated reasoning**\n"
        f"<reasoning>\n{neutralise_tags(ruling_reasoning)}\n</reasoning>"
    )
    (re_derived, note, parse_mode), completion, repairs = await _complete_with_repair(
        client,
        model=grading.validator_model,
        messages=[
            {"role": "system", "content": RULING_INDEPENDENCE_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=grading.validator_temperature,
        config=config,
        meta={
            "role": "validator",
            "speaker": None,
            "round": None,
            "purpose": "check_independence",
        },
        parse=parse_independence_output,
        role="validator",
        word_limit=0,
    )
    return RulingIndependence(
        re_derived=re_derived,
        note=note,
        model=grading.validator_model,
        parse_mode=parse_mode,
        raw=completion.content,
        call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        repair_attempts=repairs,
    )
