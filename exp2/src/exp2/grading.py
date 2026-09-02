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
    build_findings_grader_messages,
    build_grader_messages,
    build_judgment_grader_messages,
    parse_findings_grade_output,
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


@dataclass(frozen=True)
class FindingsGrade:
    """One findings objection, contest by contest. Campaign `fd1`, 2026-09-02.

    Modelled on ``JudgmentGrade`` — same `valid` conjunction, same `line_mismatch`
    instrument, same "every alleged item is ruled on and a reader can see which
    instrument ruled" property — and different from it in the one way the design
    requires: this grader IS a door to the annotation, because a contest of a finding is
    an object-level claim about the text under review and there is nothing else to score
    it against.

    So the contests split three ways and the file says which ruled each one:

      * **mechanical** — a void contest (a quotation that is not in the document it is
        attributed to, a `Should be:` that agrees with the finding it contests, a
        contradiction between a finding and itself), and both directions on a SOUND item,
        where the answer follows from the label with no reading at all. `parse_mode`
        `mechanical_only` when they are ALL of them and no call was made.
      * **the grader** — everything else, one call per objection.
      * neither, if the grader skipped a contest it was asked about; that shows up as a
        count in the log and a gap a reader can see.

    ``valid`` is ``any(contest valid)`` over the per-contest rulings and NOT the grader's
    summary line; ``line_mismatch`` records where the two disagree, which is the bound on
    every rate computed from this instrument.
    """

    contests: list[dict[str, Any]]
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
    mode: str = "findings"

    @property
    def valid(self) -> bool:
        if not self.contests:
            return self.line_valid
        return any(bool(contest.get("valid")) for contest in self.contests)

    @property
    def line_mismatch(self) -> bool:
        """The grader's summary line against the per-contest rulings.

        False when no call was made: there is no summary line to disagree with, and a
        True here would report a contradiction between a model and itself where no model
        spoke.
        """
        if self.parse_mode == MECHANICAL_ONLY:
            return False
        return bool(self.contests) and self.valid != self.line_valid

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Properties, so asdict drops them; written explicitly because the index reads
        # them straight out of the file, exactly as ObjectionGrade.valid is.
        data["valid"] = self.valid
        data["line_mismatch"] = self.line_mismatch
        data["contests_n"] = len(self.contests)
        data["contests_valid_n"] = sum(
            1 for contest in self.contests if contest.get("valid"))
        data["contests_mechanical_n"] = sum(
            1 for contest in self.contests if contest.get("mechanical"))
        return data


class NotGradable(ValueError):
    """Raised when a caller asks for a grade that cannot mean anything."""


# The two markers of a ruling that no model made. `QUOTE_NOT_IN_JUDGMENT` is the reason
# on a single defect the quote check settled; `QUOTE_CHECK_ONLY` is the parse_mode of a
# whole grade that was reached without a call because every defect failed it. Both are
# strings a reader of `grade.json` meets rather than has to infer, and both are what an
# analysis counts on when it separates "the grader rejected this" from "this never
# reached the grader".
QUOTE_NOT_IN_JUDGMENT = "quote not in judgment"
QUOTE_CHECK_ONLY = "quote_check_only"

# The findings arm's equivalents. Three reasons rather than one, because three different
# mechanical facts settle a contest there and a reader of `grade.json` is entitled to
# know which — a void quotation is an instrument failure by the challenger, while a
# `Should be: FLAW` on a sound item is a substantive claim that the label refutes.
CONTEST_VOID = "void at parse time: a quotation, an index or a direction did not check out"
FLAW_ON_SOUND_ITEM = "the item is sound, so no finding can have missed a flaw"
NOT_A_FLAW_ON_SOUND_ITEM = "the item is sound, so no finding can be a real flaw"
# The whole grade reached with no call, because every contest was settled mechanically.
MECHANICAL_ONLY = "mechanical_only"


def _quote_check_ruling(index: int, defect: dict[str, Any]) -> dict[str, Any]:
    """The ruling the quote check makes on one defect, in the grader's own shape.

    Shaped exactly like a grader's ruling — same keys, same types — so that
    `defects_n`, `defects_valid_n` and every hand check read one list and not two, and
    so that the count in `grade.json` still equals the count in `challenge.json`. What
    tells the two apart is the reason.
    """
    return {"index": index, "type": defect.get("type"), "valid": False,
            "reason": QUOTE_NOT_IN_JUDGMENT, "alleged": True}


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
    if mode not in ("flaw", "judgment", "findings"):
        raise ValueError(f"unknown grading mode {mode!r}")
    if mode == "findings":
        return await _grade_findings(
            case, objection, config=config, grading=grading, client=client,
            record=record, findings=judgment, decision_verdict=decision_verdict,
            contests=defects or [],
        )
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
    # The quote check has already ruled on some of these, deterministically and for
    # free (`prompts.defect_quote_in_judgment`, run at parse time). Only `False` skips:
    # `None` means the check did not apply — an omission, a defect that quoted nothing,
    # or a challenge written before the check existed — and every one of those goes to
    # the grader exactly as it did before.
    skipped = [index for index, defect in enumerate(defects, 1)
               if defect.get("quote_in_judgment") is False]
    surviving = len(defects) - len(skipped)
    if defects and not surviving:
        # NO CALL. Every defect this objection alleged quotes a judgment that does not
        # say it, so there is nothing left for a grader to rule on and nothing a grader
        # could rule that would change the answer. Written as a grade rather than as a
        # skip, because "graded invalid" and "not graded" are different facts and the
        # analysis counts them differently.
        log.info("%s: every alleged defect failed the quote check; not calling the "
                 "grader", case.item.item_id)
        return JudgmentGrade(
            defects=[_quote_check_ruling(index, defects[index - 1])
                     for index in skipped],
            line_valid=False, model="", parse_mode=QUOTE_CHECK_ONLY, raw="",
            call_id="", finish_reason=None,
        )
    messages = build_judgment_grader_messages(
        case.item, record=record, judgment=judgment,
        decision_verdict=decision_verdict or FLAWED, objection=objection,
        n_defects=len(defects), skipped=skipped,
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
        if grade["index"] in skipped:
            # The grader ruled on a defect it was told not to rule on. Its ruling is
            # DISCARDED rather than merged: the quote check is a string comparison a
            # reader can redo, and a model's opinion does not overturn one. Logged, not
            # silent — how often the grader ignores the instruction is a fact about the
            # grader.
            log.info("%s: judgment grader ruled on defect %d, which the quote check "
                     "had already settled; discarding its ruling",
                     case.item.item_id, grade["index"])
            continue
        alleged = (defects[grade["index"] - 1]
                   if 1 <= grade["index"] <= len(defects) else {})
        graded.append({
            "index": grade["index"],
            "type": alleged.get("type"),
            "valid": grade["valid"],
            "reason": grade["reason"],
            "alleged": bool(alleged),
        })
    if len(graded) != surviving:
        log.info(
            "%s: judgment grader ruled on %d defects; the objection alleged %d, of "
            "which %d survived the quote check",
            case.item.item_id, len(graded), len(defects), surviving,
        )
    # The deterministic rulings take their places by number, so `grade.json` rules on
    # every defect the objection alleged and a reader can see which instrument ruled on
    # which.
    graded += [_quote_check_ruling(index, defects[index - 1]) for index in skipped]
    graded.sort(key=lambda ruling: ruling["index"])

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


async def _grade_findings(
    case: Case,
    objection: str,
    *,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
    record: str,
    findings: str,
    decision_verdict: str,
    contests: list[dict[str, Any]],
) -> FindingsGrade:
    """The findings variant's grade: each contest against the annotation or the record.

    ``record`` must be the challenger-view body and ``findings`` the judge's own reply —
    the SAME two documents the challenger was shown — or a quotation it copied accurately
    becomes unfindable and every alleged omission grades VALID.

    THREE RULES ARE SETTLED HERE AND NEVER REACH A MODEL, on the same principle as the
    judgment arm's quote check: what a string comparison or the dataset label decides, a
    grader does not get to revisit.

      * a VOID contest is INVALID. Its quotation is not in the document it named, or the
        finding it contests does not exist, or its `Should be:` agrees with the ruling it
        contests, or it alleges a contradiction between a finding and itself. Each of
        those was computed at parse time by `parse_finding_contests`.
      * on a SOUND item, `Should be: FLAW` is INVALID — there is no flaw for a finding to
        have missed — and `Should be: NOT A FLAW` is VALID, because no finding on a sound
        item is a real flaw. Both follow from `gold_flawed` alone and neither is a
        judgement call. PREREG §5a records that the second makes the FLAW→NOT A FLAW rate
        an UPPER bound and the first makes the mirror a LOWER one, and that the two are
        never pooled.

    The rest go to the grader in ONE call, with the objection shown whole and the
    numbering held fixed around the settled ones — the `GRADER_SKIPPED_JUDGMENT` lesson:
    a grader left to rediscover a ruling already made would either duplicate it or
    contradict it.
    """
    if not record.strip():
        raise NotGradable(
            f"{case.item.item_id}: cannot grade a findings objection with no record to "
            "check its quotes against"
        )
    mechanical: dict[int, dict[str, Any]] = {}
    for contest in contests:
        index = int(contest["index"])
        kind = contest.get("kind")
        if contest.get("void"):
            mechanical[index] = _contest_ruling(
                index, kind, False, CONTEST_VOID, contest.get("should_be"))
        elif kind == "finding" and not case.item.gold_flawed:
            valid = contest.get("should_be") != "FLAW"
            mechanical[index] = _contest_ruling(
                index, kind, valid,
                NOT_A_FLAW_ON_SOUND_ITEM if valid else FLAW_ON_SOUND_ITEM,
                contest.get("should_be"))
    surviving = [c for c in contests if int(c["index"]) not in mechanical]
    if contests and not surviving:
        # NO CALL. Every contest was settled by a string comparison or by the dataset
        # label, so there is nothing left for a grader to rule on and nothing it could
        # rule that would change the answer. Written as a grade rather than as a skip,
        # because "graded invalid" and "not graded" are different facts and the analysis
        # counts them differently.
        log.info("%s: every contest was settled mechanically; not calling the grader",
                 case.item.item_id)
        return FindingsGrade(
            contests=[mechanical[key] for key in sorted(mechanical)],
            line_valid=any(r["valid"] for r in mechanical.values()),
            model="", parse_mode=MECHANICAL_ONLY, raw="", call_id="",
            finish_reason=None,
        )
    # The annotation is shown ONLY where a surviving contest is graded against it — a
    # finding contest on a flawed item. An objection of nothing but omissions and
    # contradictions is graded against the record alone and the recorded flaw is never
    # put in front of the grader, which keeps this door as narrow as the flaw grader's.
    needs_annotation = case.item.gold_flawed and any(
        c.get("kind") == "finding" for c in surviving)
    if needs_annotation and case.flaw is None:
        raise NotGradable(
            f"{case.item.item_id}: a finding contest on a flawed item is graded against "
            "the recorded flaw, and this item records none"
        )
    flaw = case.flaw
    messages = build_findings_grader_messages(
        case.item, record=record, findings=findings,
        decision_verdict=decision_verdict or FLAWED, objection=objection,
        n_contests=len(contests), gold_flawed=case.item.gold_flawed,
        flaw_location=(flaw.flaw_location if flaw and needs_annotation else ""),
        annotation=(flaw.annotation if flaw and needs_annotation else ""),
        grades_characterisation=(flaw.grades_characterisation if flaw else True),
        show_annotation=needs_annotation,
        skipped=[(key, ruling["reason"]) for key, ruling in sorted(mechanical.items())],
    )
    (contest_grades, line_valid, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=grading.grader_model, messages=messages,
            temperature=grading.grader_temperature, config=config,
            meta={"role": "findings_grader", "speaker": None, "round": None,
                  "purpose": "grade_findings"},
            parse=parse_findings_grade_output, role="findings_grader", word_limit=0,
            max_tokens=grading.max_tokens,
        )
    )

    # The grader's per-contest lines joined to the challenger's own list, by the number
    # both of them used. A grade for a contest nobody raised is kept (index out of range,
    # kind None) rather than dropped: it is evidence about the grader, and hiding it would
    # make `contests_n` disagree with the file it came from for no visible reason.
    by_index = {int(c["index"]): c for c in contests}
    graded: list[dict[str, Any]] = []
    for grade in contest_grades:
        if grade["index"] in mechanical:
            # The grader ruled on a contest it was told not to rule on. Its ruling is
            # DISCARDED rather than merged: a string comparison and a dataset label are
            # not overturned by a model's opinion. Logged, not silent — how often the
            # grader ignores the instruction is a fact about the grader.
            log.info("%s: findings grader ruled on contest %d, which was already "
                     "settled mechanically; discarding its ruling",
                     case.item.item_id, grade["index"])
            continue
        alleged = by_index.get(grade["index"], {})
        graded.append({
            "index": grade["index"],
            "kind": alleged.get("kind"),
            "should_be": alleged.get("should_be"),
            "valid": grade["valid"],
            "reason": grade["reason"],
            "mechanical": False,
            "alleged": bool(alleged),
        })
    if len(graded) != len(surviving):
        log.info(
            "%s: findings grader ruled on %d contests; the objection raised %d, of "
            "which %d were settled mechanically",
            case.item.item_id, len(graded), len(contests), len(mechanical),
        )
    graded += [mechanical[key] for key in sorted(mechanical)]
    graded.sort(key=lambda ruling: ruling["index"])

    result = FindingsGrade(
        contests=graded, line_valid=line_valid, model=grading.grader_model,
        parse_mode=parse_mode, raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if result.line_mismatch:
        # Not repaired and not clamped, exactly as the judgment grader's is: `valid` is
        # the conjunction of the per-contest rulings, which are the judgements a reader
        # can check, and the flag is what bounds how often the grader's own summary
        # disagreed with them.
        log.warning(
            "%s: findings grader's summary line says %s and its per-contest lines say "
            "%s", case.item.item_id, "YES" if line_valid else "NO",
            "YES" if result.valid else "NO",
        )
    return result


def _contest_ruling(index: int, kind: str | None, valid: bool, reason: str,
                    should_be: str | None = None) -> dict[str, Any]:
    """A mechanically settled contest, in the grader's own shape.

    Same keys, same types as a grader's ruling — so `contests_n`, `contests_valid_n` and
    every hand check read one list and not two, and the count in `grade.json` still
    equals the count in `challenge.json`. What tells the two apart is `mechanical` and
    the reason.
    """
    return {"index": index, "kind": kind, "should_be": should_be, "valid": valid,
            "reason": reason, "mechanical": True, "alleged": True}
