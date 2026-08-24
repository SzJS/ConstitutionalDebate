"""FindTheFlaws conversion, against synthetic rows in the real schemas.

The two subsets do not share a schema, despite the upstream README describing
them as if they did. Both differences are load-bearing and both are asserted
here: the filter column differs, and GPQA's ``flaw_explanation`` is a template
pointing at a step rather than an account of the error.
"""

from __future__ import annotations

import collections
import csv
import io
import json

import pytest

from constitutional_debate.datasets import (
    FTF_CANARY,
    convert_cases,
    convert_ftf_gpqa,
    convert_ftf_theoremqa,
)

THEOREMQA_COLUMNS = [
    "problem_id", "problem_text", "correct_final_answer", "correct_solution",
    "flawed_solution", "flawed_final_answer", "step_of_injected_flaw",
    "flaw_explanation", "flag_same_final_answer", "canary_string",
]
GPQA_COLUMNS = [
    "problem_id", "problem_text", "correct_final_answer", "correct_solution",
    "flawed_solution", "flawed_final_answer", "step_of_injected_flaw",
    "flaw_explanation", "first_misleading_step", "flag_unreliable_data",
    "canary_string",
]


def as_csv(columns: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue()


def theoremqa_row(**kw) -> dict:
    base = dict(
        problem_id="solutions/math_algebra_3_6.txt",
        problem_text="Find the B-coordinate vector of x",
        correct_final_answer="[4, 2]",
        correct_solution="Step 1: solve. Step 2: a = 4, b = 2.",
        flawed_solution="Step 1: solve. Step 2: a = 2, b = 4.",
        flawed_final_answer="[2, 4]",
        step_of_injected_flaw=" 2",
        flaw_explanation="The correct solution gives a = 4 and b = 2.",
        flag_same_final_answer="False",
        canary_string=FTF_CANARY,
    )
    return {**base, **kw}


def gpqa_row(**kw) -> dict:
    base = dict(
        problem_id="157",
        problem_text="In an inactive state, a transcription factor...",
        correct_final_answer="Choice 2: protein aggregation",
        correct_solution="1. Mutation Y is dominant-negative. 2. Therefore.",
        flawed_solution="1. Mutation Y is dominant-negative. 2. Therefore not.",
        flawed_final_answer="Choice 3: loss of dimerization",
        step_of_injected_flaw="3",
        flaw_explanation="The first error occurs in Step 3.",
        first_misleading_step="2",
        flag_unreliable_data="False",
        canary_string=FTF_CANARY,
    )
    return {**base, **kw}


# --------------------------------------------------------------------------- #
# the mapping
# --------------------------------------------------------------------------- #


def test_the_gold_answer_is_the_correct_final_answer():
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [theoremqa_row()]))
    assert case.task.answers[case.task.gold_index] == "[4, 2]"
    assert case.task.answers[1 - case.task.gold_index] == "[2, 4]"
    assert case.error.corrected_answer_index == case.task.gold_index


def test_the_solutions_land_on_the_matching_sides():
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [theoremqa_row()]))
    assert "a = 2, b = 4" in case.error.seed, "seed is the flawed reasoning"
    assert "a = 4, b = 2" in case.error.sound_seed, "sound_seed is the correct one"


def test_gold_index_is_drawn_not_pinned_and_is_stable():
    rows = [theoremqa_row(problem_id=f"p{i}") for i in range(60)]
    cases = list(convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, rows)))
    counts = collections.Counter(c.task.gold_index for c in cases)
    assert set(counts) == {0, 1}, "gold must not be constant across the corpus"
    assert 15 <= counts[0] <= 45, counts  # ~binomial(60, .5); a fixed seed, so not flaky
    again = list(convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, rows)))
    assert [c.task.gold_index for c in again] == [c.task.gold_index for c in cases]


def test_the_canary_string_is_stripped_from_every_field():
    """Every field, as the name says — not the two it used to plant it in.

    The narrow version passed while `correct_final_answer`, `flawed_final_answer`
    and `problem_id` were read with a bare `.strip()`. Those become
    `Task.answers` and `task_id`, and the answers go straight into prompts, so
    the one path that actually mattered was the one not covered.
    """
    row = {k: (f"{v} {FTF_CANARY}" if isinstance(v, str) and v else v)
           for k, v in theoremqa_row().items()}
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [row]))
    fields = {
        "question": case.task.question,
        "answers[0]": case.task.answers[0],
        "answers[1]": case.task.answers[1],
        "task_id": case.task.task_id,
        "source": case.task.source or "",
        "seed": case.error.seed,
        "sound_seed": case.error.sound_seed,
        "annotation": case.error.annotation,
        "flaw_location": case.error.flaw_location,
        "error_id": case.error.error_id,
    }
    leaked = sorted(name for name, value in fields.items() if FTF_CANARY in value)
    assert not leaked, f"canary reached: {leaked}"
    # and the whole serialised case, so a field added later is covered too
    assert FTF_CANARY not in json.dumps(case.to_dict())


def test_the_canary_is_recorded_in_provenance_rather_than_laundered():
    """Stripped from the cases, but the record says the source carried it."""
    from constitutional_debate.datasets import SOURCES, provenance

    raw = as_csv(THEOREMQA_COLUMNS, [theoremqa_row()])
    meta = provenance(SOURCES["ftf-theoremqa"], raw)
    assert meta["canary"] == FTF_CANARY
    assert "not vendored" in meta["canary_note"]
    # a source without one gains no canary key
    clean = as_csv(THEOREMQA_COLUMNS, [theoremqa_row(canary_string="")])
    assert "canary" not in provenance(SOURCES["ftf-theoremqa"], clean)


def test_the_flaw_location_is_stripped_of_its_leading_space():
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [theoremqa_row()]))
    assert case.error.flaw_location == "2"


def test_a_problem_id_with_slashes_becomes_a_usable_task_id():
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [theoremqa_row()]))
    assert "/" not in case.task.task_id
    assert case.task.task_id.startswith("ftf-theoremqa-")


# --------------------------------------------------------------------------- #
# the rows that must be dropped
# --------------------------------------------------------------------------- #


def test_a_flawed_path_landing_on_the_correct_answer_is_dropped():
    """No wrong decision is available on such a row, so it cannot be a case."""
    rows = [
        theoremqa_row(problem_id="same", flawed_final_answer="[4, 2]",
                      flag_same_final_answer="True"),
        theoremqa_row(problem_id="ok"),
    ]
    cases = list(convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, rows)))
    assert [c.task.task_id for c in cases] == ["ftf-theoremqa-ok"]


def test_the_flag_is_believed_and_so_is_the_comparison():
    """Either signal alone is enough to drop the row."""
    flagged_only = theoremqa_row(problem_id="a", flag_same_final_answer="True")
    equal_only = theoremqa_row(problem_id="b", flawed_final_answer="[4, 2]",
                               flag_same_final_answer="False")
    assert convert_cases(
        "ftf-theoremqa", as_csv(THEOREMQA_COLUMNS, [flagged_only, equal_only])
    ) == []


def test_gpqa_filters_on_unreliable_data_not_on_the_theoremqa_flag():
    rows = [gpqa_row(problem_id="1", flag_unreliable_data="True"),
            gpqa_row(problem_id="2", flag_unreliable_data="False")]
    cases = list(convert_ftf_gpqa(as_csv(GPQA_COLUMNS, rows)))
    assert [c.task.task_id for c in cases] == ["ftf-gpqa-2"]


# --------------------------------------------------------------------------- #
# what each subset's annotation can support
# --------------------------------------------------------------------------- #


def test_theoremqa_annotations_can_grade_characterisation():
    (case,) = convert_ftf_theoremqa(as_csv(THEOREMQA_COLUMNS, [theoremqa_row()]))
    assert case.error.annotation_quality == "explanation"
    assert case.error.grades_characterisation
    assert "a = 4 and b = 2" in case.error.annotation


def test_gpqa_annotations_cannot_and_the_template_is_not_stored_as_one():
    """GPQA's flaw_explanation is 9 distinct strings across 198 rows.

    It restates step_of_injected_flaw and says nothing about what the error is.
    Storing it as an ``annotation`` would invite the grader to score a
    challenge's characterisation of the error against a string that
    characterises nothing.
    """
    (case,) = convert_ftf_gpqa(as_csv(GPQA_COLUMNS, [gpqa_row()]))
    assert case.error.annotation_quality == "location_only"
    assert not case.error.grades_characterisation
    assert case.error.annotation == ""
    assert case.error.flaw_location == "3"


def test_an_unknown_case_source_is_refused():
    with pytest.raises(KeyError, match="unknown case source"):
        convert_cases("ftf-lojban", "")


# --------------------------------------------------------------------------- #
# Python650 — the largest usable subset, and the only one with a third schema
# --------------------------------------------------------------------------- #

PYTHON650_COLUMNS = [
    "problem_id", "problem_text", "proposed_solution", "correct_final_answer",
    "correct_llm_explanation", "flawed_llm_explanation", "flawed_final_answer",
    "flaw_explanation", "correct_explanation_comments", "canary_string",
    "flag_unreliable_correct_explanation", "flag_unreliable_data",
]


def python650_row(**kw) -> dict:
    base = dict(
        problem_id="p00001",
        problem_text="Print the top three heights in descending order.",
        proposed_solution="def main():\n    pass",
        correct_final_answer="Proposed solution is incorrect",
        correct_llm_explanation="1. It skips duplicates, so it prints only two.",
        flawed_llm_explanation="1. It prints three heights. The solution is fine.",
        flawed_final_answer="Proposed solution is correct",
        flaw_explanation="Step 1 is wrong: the continue statement drops a height.",
        correct_explanation_comments="Annotator 2: should be more specific.",
        canary_string=FTF_CANARY,
        flag_unreliable_correct_explanation="False",
        flag_unreliable_data="False",
    )
    return {**base, **kw}


def test_python650_seeds_both_sides():
    """The property that makes this subset usable where MedQA and CELS are not."""
    from constitutional_debate.datasets import convert_ftf_python650

    (case,) = convert_ftf_python650(as_csv(PYTHON650_COLUMNS, [python650_row()]))
    assert "prints only two" in case.error.sound_seed
    assert "The solution is fine" in case.error.seed
    assert case.task.answers[case.task.gold_index] == "Proposed solution is incorrect"


def test_python650_puts_the_program_in_the_question():
    """The answers are verdicts *about a program*, so it has to be shown one."""
    from constitutional_debate.datasets import convert_ftf_python650

    (case,) = convert_ftf_python650(as_csv(PYTHON650_COLUMNS, [python650_row()]))
    assert "def main():" in case.task.question
    assert case.task.question.rstrip().endswith("Is the proposed solution correct?")


def test_python650_keeps_and_marks_an_unreliable_sound_seed():
    """Kept, not dropped — it is half the corpus and only the control is shaky."""
    from constitutional_debate.datasets import convert_ftf_python650

    rows = [python650_row(problem_id="a", flag_unreliable_correct_explanation="True"),
            python650_row(problem_id="b", flag_unreliable_correct_explanation="False")]
    cases = list(convert_ftf_python650(as_csv(PYTHON650_COLUMNS, rows)))
    assert [c.error.sound_seed_reliable for c in cases] == [False, True]
    assert len(cases) == 2, "an unreliable sound seed must not drop the row"


def test_python650_drops_unreliable_data_and_rows_missing_a_seed():
    from constitutional_debate.datasets import convert_ftf_python650

    rows = [
        python650_row(problem_id="a", flag_unreliable_data="True"),
        python650_row(problem_id="b", flawed_llm_explanation=""),
        python650_row(problem_id="c"),
    ]
    cases = list(convert_ftf_python650(as_csv(PYTHON650_COLUMNS, rows)))
    assert [c.task.task_id for c in cases] == ["ftf-python650-c"]


def test_python650_annotations_grade_characterisation():
    from constitutional_debate.datasets import convert_ftf_python650

    (case,) = convert_ftf_python650(as_csv(PYTHON650_COLUMNS, [python650_row()]))
    assert case.error.grades_characterisation
    # No step pointer upstream for this subset; the explanation carries it.
    assert case.error.flaw_location == ""
