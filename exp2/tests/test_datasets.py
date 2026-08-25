"""The four converters, against synthetic rows.

Each family is built as real CSV text and read back through the same
``csv.DictReader`` path production uses, so a column-name typo fails here rather than
at fetch time. No network, no fixture files.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from exp2.datasets import (
    FTF_CANARY,
    FTF_COMMIT,
    SUBSETS,
    SentenceAlignmentError,
    convert_subset,
    parse_numbered_sentences,
    parse_sentence_labels,
    provenance,
)

PAIRED_COLUMNS = [
    "problem_id", "problem_text", "correct_final_answer", "correct_solution",
    "flawed_solution", "flawed_final_answer", "step_of_injected_flaw",
    "flaw_explanation", "flag_unreliable_data", "flag_same_final_answer",
    "canary_string",
]
PYTHON_COLUMNS = [
    "problem_id", "problem_text", "proposed_solution", "correct_final_answer",
    "correct_llm_explanation", "flawed_llm_explanation", "flawed_final_answer",
    "flaw_explanation", "flag_unreliable_data", "flag_unreliable_correct_explanation",
    "canary_string",
]
NATURAL_COLUMNS = [
    "problem_id", "problem_text", "correct_final_answer", "llm_final_answer",
    "llm_solution", "comments_on_llm_solution", "flag_unreliable_data", "canary_string",
]


def as_csv(columns: list[str], rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buffer.getvalue()


def paired_row(**kw) -> dict:
    base = dict(
        problem_id="solutions/Catalan_1.txt", problem_text="What is C_3?",
        correct_final_answer="5", correct_solution="Step 1: ...\nStep 2: C_3 = 5.",
        flawed_solution="Step 1: ...\nStep 2: C_3 = 6.", flawed_final_answer="6",
        step_of_injected_flaw=" 2", flaw_explanation="Step 2 miscounts the paths.",
        flag_unreliable_data="False", flag_same_final_answer="False",
        canary_string=FTF_CANARY,
    )
    base.update(kw)
    return base


def python_row(**kw) -> dict:
    base = dict(
        problem_id="p00001", problem_text="Sum two integers.",
        proposed_solution="def f(a,b): return a+b",
        correct_final_answer="Proposed solution is correct",
        correct_llm_explanation="The function adds correctly.",
        flawed_llm_explanation="The function subtracts, so it is wrong.",
        flawed_final_answer="Proposed solution is incorrect",
        flaw_explanation="It does not subtract.", flag_unreliable_data="False",
        flag_unreliable_correct_explanation="False", canary_string=FTF_CANARY,
    )
    base.update(kw)
    return base


def natural_row(**kw) -> dict:
    base = dict(
        problem_id="dev_0041", problem_text="Which is the best next step?",
        correct_final_answer="D", llm_final_answer="D",
        llm_solution="1. The patient is anaemic.\n2. Therefore (D).",
        comments_on_llm_solution="Annotator 1 agrees with LLM's final answer.",
        flag_unreliable_data="False", canary_string=FTF_CANARY,
    )
    base.update(kw)
    return base


def cels_row(**kw) -> dict:
    base = dict(
        problem_id="sur1_gpt3.5_A", problem_text="Which indicates fasciotomy?",
        correct_final_answer="A", llm_final_answer="A",
        llm_solution="1. Consider the severity.\n2. Numbness is not an indication.\n"
                     "3. Compartment syndrome follows.",
        comments_on_llm_solution=(
            "Sentence 1: CORRECT -- Annotator 1 comment: No problem. "
            "-- Annotator 2 comment: No problem.  "
            "Sentence 2: FLAWED -- Annotator 1 comment: Numbness in the first web "
            "space IS an indication. -- Annotator 2 comment: Wrong.  "
            "Sentence 3: AMBIGUOUS -- Annotator 1 comment: Unclear. "
            "-- Annotator 2 comment: No problem."
        ),
        flag_unreliable_data="False", canary_string=FTF_CANARY,
    )
    base.update(kw)
    return base


def by_id(cases):
    return {c.item.item_id: c for c in cases}


# --- family A: paired solutions ------------------------------------------------------


def test_a_paired_row_yields_a_sound_and_a_flawed_item_sharing_a_row_id():
    cases = convert_subset("theoremqa", as_csv(PAIRED_COLUMNS, [paired_row()]))
    assert len(cases) == 2
    cases_by_id = by_id(cases)
    sound = cases_by_id["theoremqa-solutions-Catalan_1-txt-sound"]
    flawed = cases_by_id["theoremqa-solutions-Catalan_1-txt-flawed"]

    assert sound.item.gold_flawed is False and sound.flaw is None
    assert flawed.item.gold_flawed is True and flawed.flaw is not None
    assert sound.item.row_id == flawed.item.row_id  # clusters together in the bootstrap
    assert sound.item.solution != flawed.item.solution
    assert sound.item.problem == flawed.item.problem
    assert sound.item.label_basis == "injected_pair"
    # the upstream leading space on the step pointer is stripped
    assert flawed.flaw.flaw_location == "2"
    assert flawed.flaw.origin == "injected"


def test_gpqas_template_annotation_is_not_stored_as_an_explanation():
    """Upstream's gpqa flaw_explanation is "The first error occurs in Step N" — 9
    distinct strings over 198 rows. Keeping it as an explanation would invite the
    grader to score against a string that explains nothing."""
    row = paired_row(flaw_explanation="The first error occurs in Step 2.")
    flawed = by_id(convert_subset("gpqa", as_csv(PAIRED_COLUMNS, [row])))[
        "gpqa-solutions-Catalan_1-txt-flawed"]
    assert flawed.flaw.annotation == ""
    assert flawed.flaw.annotation_quality == "location_only"
    assert flawed.gradable is False  # so gpqa contributes no validity data
    # theoremqa, with a real explanation, does
    t = by_id(convert_subset("theoremqa", as_csv(PAIRED_COLUMNS, [paired_row()])))[
        "theoremqa-solutions-Catalan_1-txt-flawed"]
    assert t.gradable is True


@pytest.mark.parametrize("row,reason", [
    (paired_row(flag_unreliable_data="True"), "unreliable"),
    (paired_row(flag_same_final_answer="True"), "flagged same answer"),
    (paired_row(flawed_final_answer="5"), "answers coincide"),
    (paired_row(correct_solution=""), "missing solution"),
])
def test_a_rows_that_must_be_dropped(row, reason):
    assert convert_subset("theoremqa", as_csv(PAIRED_COLUMNS, [row])) == [], reason


# --- family B: explanations of a program ---------------------------------------------


def test_b_reviews_the_explanation_and_folds_the_program_into_the_problem():
    cases = by_id(convert_subset("python800", as_csv(PYTHON_COLUMNS, [python_row()])))
    sound = cases["python800-p00001-sound"]
    assert "def f(a,b): return a+b" in sound.item.problem  # the program is context
    assert sound.item.solution == "The function adds correctly."  # the explanation is judged
    assert "text under review" in sound.item.problem


def test_b_drops_only_the_sound_sibling_when_the_correct_explanation_is_unreliable():
    """323 of 648 rows. An item whose gold label may be wrong is worse than no item —
    the same judgment as disregarding the sentences reviewers disagreed about."""
    row = python_row(flag_unreliable_correct_explanation="True")
    cases = convert_subset("python800", as_csv(PYTHON_COLUMNS, [row]))
    assert [c.item.item_id for c in cases] == ["python800-p00001-flawed"]
    assert cases[0].item.gold_flawed is True


# --- family C1: medqa ----------------------------------------------------------------


def test_c1_labels_by_final_answer_agreement_and_says_so():
    sound = convert_subset("medqa", as_csv(NATURAL_COLUMNS, [natural_row()]))
    assert len(sound) == 1
    assert sound[0].item.gold_flawed is False
    assert sound[0].item.label_basis == "final_answer"
    # and the annotator comments are NOT attached to a sound item, even though the
    # column is populated on every row
    assert sound[0].flaw is None

    flawed = convert_subset(
        "medqa", as_csv(NATURAL_COLUMNS, [natural_row(llm_final_answer="B")]))
    assert flawed[0].item.gold_flawed is True
    assert flawed[0].flaw is not None and flawed[0].flaw.origin == "natural"


# --- family C2: CELS sentences -------------------------------------------------------


def test_the_sentence_label_and_argument_parsers_agree_on_a_real_shaped_row():
    row = cels_row()
    labels = parse_sentence_labels(row["comments_on_llm_solution"])
    sentences = parse_numbered_sentences(row["llm_solution"])
    assert set(labels) == set(sentences) == {1, 2, 3}
    assert [labels[i][0] for i in (1, 2, 3)] == ["CORRECT", "FLAWED", "AMBIGUOUS"]
    assert "first web space" in labels[2][1]  # the per-sentence comments are captured


def test_c2_drops_ambiguous_sentences_and_keeps_the_rest():
    """AMBIGUOUS is where the two reviewers did not concur, so it is not a label."""
    cases = convert_subset("surgery", as_csv(NATURAL_COLUMNS, [cels_row()]),
                           sentences_per_argument=99)
    indices = sorted(int(c.item.item_id.rsplit("-s", 1)[1]) for c in cases)
    assert indices == [1, 2]  # sentence 3 was AMBIGUOUS
    cases_by_id = by_id(cases)
    assert cases_by_id["surgery-sur1_gpt3-5_A-s1"].item.gold_flawed is False
    assert cases_by_id["surgery-sur1_gpt3-5_A-s2"].item.gold_flawed is True


def test_c2_shows_the_whole_argument_as_context_and_names_the_sentence():
    """A CELS sentence is meaningless alone, so the argument travels with it."""
    case = convert_subset("surgery", as_csv(NATURAL_COLUMNS, [cels_row()]),
                          sentences_per_argument=99)[1]
    assert case.item.solution == "Numbness is not an indication."
    assert "Numbness is not an indication." in case.item.problem  # in context
    assert "Sentence 2 of that argument is the text under review." in case.item.problem


def test_c2_attaches_annotations_to_flawed_sentences_only():
    cases = by_id(convert_subset("surgery", as_csv(NATURAL_COLUMNS, [cels_row()]),
                                 sentences_per_argument=99))
    assert cases["surgery-sur1_gpt3-5_A-s1"].flaw is None
    flawed = cases["surgery-sur1_gpt3-5_A-s2"]
    assert flawed.flaw.flaw_location == "2"
    assert "first web space" in flawed.flaw.annotation


def test_c2_draws_one_sentence_per_argument_by_default_and_is_reproducible():
    raw = as_csv(NATURAL_COLUMNS, [cels_row()])
    first = convert_subset("surgery", raw)
    assert len(first) == 1
    again = convert_subset("surgery", raw)
    assert first[0].item.item_id == again[0].item.item_id
    # and all sentences of one argument share a row_id, so the bootstrap clusters them
    everything = convert_subset("surgery", raw, sentences_per_argument=99)
    assert {c.item.row_id for c in everything} == {"surgery:sur1_gpt3-5_A"}


def test_a_misaligned_row_raises_rather_than_being_skipped():
    """Verified zero mismatches over 372 real rows, so a mismatch means the upstream
    data changed shape and the labels can no longer be trusted."""
    row = cels_row(llm_solution="1. Only one sentence here.")
    with pytest.raises(SentenceAlignmentError, match="do not match"):
        convert_subset("surgery", as_csv(NATURAL_COLUMNS, [row]))


# --- cross-cutting -------------------------------------------------------------------


def test_the_canary_is_stripped_from_every_converted_field():
    """Rewrites every string field to carry the canary, then asserts on the serialised
    case, so a field added later is covered too."""
    row = {k: (v + FTF_CANARY if isinstance(v, str) and v else v)
           for k, v in paired_row().items()}
    cases = convert_subset("theoremqa", as_csv(PAIRED_COLUMNS, [row]))
    assert cases, "the canary-laden row should still convert"
    for case in cases:
        assert FTF_CANARY not in json.dumps(case.to_dict())


def test_every_subset_declares_a_label_basis_and_annotation_tier():
    for key, subset in SUBSETS.items():
        assert subset.label_basis in ("injected_pair", "sentence_labels", "final_answer")
        assert subset.annotation_quality in ("explanation", "location_only", "none")
        assert subset.member.startswith("datasets/"), key


def test_provenance_pins_a_commit_and_records_the_canary():
    """exp1's provenance claimed to record an upstream commit and did not — its URL was
    a master raw link, so a refresh could change the corpus with only the sha showing."""
    raw = as_csv(PAIRED_COLUMNS, [paired_row()])
    record = provenance(SUBSETS["theoremqa"], raw)
    assert record["commit"] == FTF_COMMIT
    assert FTF_COMMIT in record["url"] and "master" not in record["url"]
    assert record["sha256"] and record["bytes"] == len(raw.encode("utf-8"))
    assert record["canary"] == FTF_CANARY
    assert "not vendored" in record["canary_note"]


def test_an_unknown_subset_is_refused():
    with pytest.raises(KeyError, match="unknown subset"):
        convert_subset("habermas", "")
