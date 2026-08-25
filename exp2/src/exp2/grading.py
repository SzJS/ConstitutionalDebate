"""Grading an objection against the flaw the dataset records.

This module is the **only** door to the ground-truth annotation. ``load_run_record``
does not read ``flaw.json``; ``persistence.load_flaw`` does, and only this module calls
it. The containment is structural rather than conventional so that no decision-path or
contest-path code can reach the answer even by accident.

Every call here carries ``role="grader"``, which ``accounting.OFF_PATH_ROLES`` excludes
from decision-path totals — so grading a run can never inflate the condition it grades,
and in particular can never disturb the token-balance check that guards against
"debate only won because it generated more text".
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from .client import ChatClient
from .config import DebateConfig, GradingConfig
from .engine import _complete_with_repair
from .prompts import build_grader_messages, parse_grade_output
from .types import Case, Item

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

    @property
    def valid(self) -> bool:
        return self.identified_flaw and self.characterises_the_flaw

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # A property, so asdict drops it. Serialised explicitly for the same reason
        # Ruling.changed_the_decision is: the index reads it straight out of the file.
        data["valid"] = self.valid
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
) -> ObjectionGrade:
    """Grade one objection against the recorded flaw.

    Raises on a sound item rather than returning a null grade. No objection can be valid
    when the solution is sound — there is no recorded flaw to grade against — so
    reaching this function with one means a caller bug, and returning a polite False
    would let that bug reach the analysis as a real measurement.
    """
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
    (identified, characterised, reasoning, parse_mode), completion, repairs, _ = (
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
