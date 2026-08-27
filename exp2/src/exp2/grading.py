"""Grading an objection against the flaw the dataset records.

This module is the **only** door to the ground-truth annotation. ``load_run_record``
does not read ``flaw.json``; ``persistence.load_flaw`` does, and only this module calls
it. The containment is structural rather than conventional so that no decision-path or
contest-path code can reach the answer even by accident.

Every call here carries ``role="grader"`` — or ``role="judgment_grader"``, the judgment
variant's — both of which ``accounting.OFF_PATH_ROLES`` excludes from decision-path
totals, so grading a run can never inflate the condition it grades, and in particular can
never disturb the token-balance check that guards against "debate only won because it
generated more text".

**Two instruments live here.** ``grade_objection(mode="flaw")`` is the original: an
objection scored against the recorded annotation, and the only reader of ``flaw.json``
in the codebase. ``grade_objection(mode="judgment")`` is the judgment variant's: alleged
defects in the decision's own reasoning, checked against the published record, with the
annotation never loaded at all. The second is why validity is definable on sound items
and on correct decisions, and why it is graded on every contested cell.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from .client import ChatClient
from .config import DebateConfig, GradingConfig
from .engine import _complete_with_repair
from .prompts import (
    build_grader_messages,
    build_judgment_grader_messages,
    parse_grade_output,
    parse_judgment_grade_output,
)
from .types import FLAWED, Case, Item

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectionGrade:
    """Two bars, graded separately, and their conjunction.

    DESIGN.md defines a valid objection as identifying the flaw *and* explaining why
    overturning it changes the overall decision. That second clause was load-bearing
    under a two-answer task — a challenger could find a real error and still fail to
    connect it to which answer wins. Under exp2's yes/no task it is vacuous: the
    decision *is* whether a flaw exists, so pointing at one already argues the verdict
    should flip. Graded literally, the two bars would be one number.

    So the bars are **where** and **what**: did the objection point at the right place,
    and did it say what is actually wrong there. See `LLM_NOTES.md` §3.
    """

    identified_flaw: bool
    characterises_the_flaw: bool
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0
    reasoning: str = ""
    native_reasoning: str = ""
    reasoning_withheld: bool = False
    # True when the subset's annotation records only *where* the flaw is, so the second
    # bar could not be graded and was forced to False rather than guessed.
    characterisation_ungradable: bool = False
    # Which instrument wrote this file. "flaw" is the grade above — an objection scored
    # against the recorded annotation; "judgment" is `JudgmentGrade` below, which scores
    # alleged defects against the record and never opens `flaw.json`. Stated in the file
    # rather than inferred from which keys are present, because `build_index` and the
    # analysis mean different things by `grade_valid` under the two, and a tree that
    # mixed them silently would report one as the other.
    mode: str = "flaw"

    @property
    def valid(self) -> bool:
        return self.identified_flaw and self.characterises_the_flaw

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # A property, so asdict drops it. Serialised explicitly for the same reason
        # Ruling.changed_the_decision is: the index reads it straight out of the file.
        data["valid"] = self.valid
        return data


@dataclass(frozen=True)
class JudgmentGrade:
    """One judgment objection, defect by defect, against the record.

    A different instrument from ``ObjectionGrade`` and not a variant of it. That one
    asks "did this objection find the flaw the dataset recorded"; this one asks "is the
    defect this objection alleges really in the record" — a question about the process,
    answerable from the record alone. Three consequences, all of them the point of the
    variant (DESIGN.md, `## Judgment-challenge`):

      * no ``flaw.json``, so nothing here is gated on the annotation and gpqa's
        location-only items grade like any other;
      * validity is defined on CORRECT decisions, so a valid defect on a decision that
        got the right answer is a real finding rather than a false alarm;
      * it is hand-checkable — every judgement it makes is "is this quote in that text".

    ``valid`` is ``any(defect valid)`` and is taken from the per-defect lines, not from
    the grader's summary line. ``line_mismatch`` records the case where the two
    disagree: a grader that marked every defect INVALID and then wrote `Valid objection:
    YES` has contradicted itself, and a column that reads 0 is what says the instrument
    is behaving. When no per-defect line arrived at all (``parse_mode ==
    "summary_line_only"``) there is nothing to conjoin and the summary line is used;
    that is stated in ``parse_mode`` so the fallback is never invisible.
    """

    defects: list[dict[str, Any]]
    line_valid: bool
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0
    reasoning: str = ""
    native_reasoning: str = ""
    reasoning_withheld: bool = False
    mode: str = "judgment"

    @property
    def valid(self) -> bool:
        if not self.defects:
            return self.line_valid
        return any(bool(defect.get("valid")) for defect in self.defects)

    @property
    def line_mismatch(self) -> bool:
        """The grader's summary line against its own per-defect lines."""
        return bool(self.defects) and self.valid != self.line_valid

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Properties, so asdict drops them; written explicitly because the index reads
        # them straight out of the file, exactly as ObjectionGrade.valid is.
        data["valid"] = self.valid
        data["line_mismatch"] = self.line_mismatch
        data["defects_n"] = len(self.defects)
        data["defects_valid_n"] = sum(
            1 for defect in self.defects if defect.get("valid"))
        return data


class NotGradable(ValueError):
    """Raised when a caller asks for a grade that cannot mean anything."""


async def grade_objection(
    case: Case,
    objection: str,
    *,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
    mode: str = "flaw",
    record: str = "",
    judgment: str = "",
    decision_verdict: str = "",
    defects: list[dict[str, Any]] | None = None,
) -> ObjectionGrade | JudgmentGrade:
    """Grade one objection: against the recorded flaw, or against the record.

    ``mode="flaw"`` is the original instrument and the default, so every existing caller
    means what it meant. ``mode="judgment"`` grades the judgment variant's alleged
    defects against the record and needs ``record``, ``judgment`` and
    ``decision_verdict``; it never touches ``case.flaw``, which is what makes it
    definable on sound items and on correct decisions.

    Raises on a sound item **in flaw mode** rather than returning a null grade. No
    objection can be valid when the solution is sound — there is no recorded flaw to
    grade against — so reaching this function with one means a caller bug, and returning
    a polite False would let that bug reach the analysis as a real measurement.
    """
    if mode not in ("flaw", "judgment"):
        raise ValueError(f"unknown grading mode {mode!r}")
    if mode == "judgment":
        return await _grade_judgment(
            case, objection, config=config, grading=grading, client=client,
            record=record, judgment=judgment, decision_verdict=decision_verdict,
            defects=defects or [],
        )
    if not case.item.gold_flawed or case.flaw is None:
        raise NotGradable(
            f"{case.item.item_id}: cannot grade an objection on a sound item — there is "
            "no recorded flaw to grade against, and no objection is valid when the "
            "solution is sound"
        )

    flaw = case.flaw
    messages = build_grader_messages(
        case.item,
        flaw_location=flaw.flaw_location,
        annotation=flaw.annotation,
        grades_characterisation=flaw.grades_characterisation,
        objection=objection,
    )
    (identified, characterised, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=grading.grader_model, messages=messages,
            temperature=grading.grader_temperature, config=config,
            meta={"role": "grader", "speaker": None, "round": None,
                  "purpose": "grade_objection"},
            parse=parse_grade_output, role="grader", word_limit=0,
        )
    )

    ungradable = not flaw.grades_characterisation
    if ungradable and characterised:
        # The prompt already says the second bar cannot be graded on this subset. A
        # grader that answers YES anyway is scoring against a string that characterises
        # nothing, so the answer is discarded rather than trusted.
        log.warning(
            "%s: grader characterised a flaw on a %s annotation; clamping to False",
            case.item.item_id, flaw.annotation_quality,
        )
        characterised = False

    return ObjectionGrade(
        identified_flaw=identified, characterises_the_flaw=characterised,
        model=grading.grader_model, parse_mode=parse_mode, raw=completion.content,
        call_id=completion.call_id, finish_reason=completion.finish_reason,
        repair_attempts=repairs, reasoning=reasoning,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
        characterisation_ungradable=ungradable,
    )


async def _grade_judgment(
    case: Case,
    objection: str,
    *,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
    record: str,
    judgment: str,
    decision_verdict: str,
    defects: list[dict[str, Any]],
) -> JudgmentGrade:
    """The judgment variant's grade: each alleged defect checked against the record.

    ``record`` must be the challenger-view body — the same text the challenger was shown
    — or a quote the challenger copied accurately becomes unfindable and every alleged
    misstatement grades VALID. ``judgment`` is ``RunRecord.decision_grounds``, which is
    the text the challenger was handed inside ``<judgment>``.

    No gate on ``case.flaw``. That absence is the design: validity here does not depend
    on there being a recorded flaw, which is what makes every subset gradable and what
    makes a valid defect on a *correct* decision a real finding rather than a false
    alarm.

    The defect TYPES come from the challenge, not from the grader: the grader is asked
    whether defect N holds, and what defect N claimed to be was fixed when the
    challenger wrote it. A grader that renamed a type would be regrading the objection
    it was given.
    """
    if not record.strip():
        raise NotGradable(
            f"{case.item.item_id}: cannot grade a judgment objection with no record to "
            "check its quotes against"
        )
    messages = build_judgment_grader_messages(
        case.item, record=record, judgment=judgment,
        decision_verdict=decision_verdict or FLAWED, objection=objection,
        n_defects=len(defects),
    )
    (defect_grades, line_valid, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=grading.grader_model, messages=messages,
            temperature=grading.grader_temperature, config=config,
            meta={"role": "judgment_grader", "speaker": None, "round": None,
                  "purpose": "grade_judgment"},
            parse=parse_judgment_grade_output, role="judgment_grader", word_limit=0,
            max_tokens=grading.max_tokens,
        )
    )

    # The grader's per-defect lines joined to the challenger's own defect list, by the
    # number both of them used. A grade for a defect nobody alleged is kept (index out of
    # range, type None) rather than dropped: it is evidence about the grader, and hiding
    # it would make `defects_n` disagree with the file it came from for no visible
    # reason.
    graded: list[dict[str, Any]] = []
    for grade in defect_grades:
        alleged = (defects[grade["index"] - 1]
                   if 1 <= grade["index"] <= len(defects) else {})
        graded.append({
            "index": grade["index"],
            "type": alleged.get("type"),
            "valid": grade["valid"],
            "reason": grade["reason"],
            "alleged": bool(alleged),
        })
    if len(graded) != len(defects):
        log.info(
            "%s: judgment grader ruled on %d defects; the objection alleged %d",
            case.item.item_id, len(graded), len(defects),
        )

    result = JudgmentGrade(
        defects=graded, line_valid=line_valid, model=grading.grader_model,
        parse_mode=parse_mode, raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if result.line_mismatch:
        # Not repaired and not clamped: `valid` is the conjunction of the per-defect
        # rulings, which are the judgements a reader can check, and the flag is what
        # bounds how often the grader's own summary disagreed with them.
        log.warning(
            "%s: judgment grader's summary line says %s and its per-defect lines say %s",
            case.item.item_id, "YES" if line_valid else "NO",
            "YES" if result.valid else "NO",
        )
    return result
