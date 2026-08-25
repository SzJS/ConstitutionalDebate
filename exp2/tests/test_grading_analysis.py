"""Grading, and the rates computed from it."""

from __future__ import annotations

import json

import pytest
from conftest import FakeClient
from helpers import make_config, make_item

from exp2.analysis import Rate, analyse, bootstrap_difference, caveats, error_type, funnel
from exp2.config import GradingConfig
from exp2.grading import NotGradable, grade_objection
from exp2.types import Case, FlawAnnotation


def case(*, gold_flawed=True, quality="explanation") -> Case:
    item = make_item(gold_flawed=gold_flawed,
                     item_id="theoremqa-p1-" + ("flawed" if gold_flawed else "sound"))
    flaw = FlawAnnotation(annotation_id="a", flaw_location="2",
                          annotation="Step 2 miscounts.", annotation_quality=quality)
    return Case(item=item, flaw=flaw if gold_flawed else None)


async def grade(objection="Step 2 miscounts the paths.", *, quality="explanation",
                client=None):
    return await grade_objection(
        case(quality=quality), objection, config=make_config(),
        grading=GradingConfig(), client=client or FakeClient(),
    )


# --- grading -------------------------------------------------------------------------


async def test_the_two_bars_are_graded_separately():
    grade_result = await grade()
    assert grade_result.identified_flaw is True
    assert grade_result.characterises_the_flaw is True
    assert grade_result.valid is True


async def test_valid_is_the_conjunction_and_survives_serialisation():
    client = FakeClient(replies={("grader", "grade_objection"):
                                 "Identified the flaw: YES\nCharacterised the flaw: NO"})
    result = await grade(client=client)
    assert result.valid is False
    assert json.loads(json.dumps(result.to_dict()))["valid"] is False


async def test_a_location_only_annotation_clamps_the_second_bar():
    """gpqa records where the flaw is, not what it is. A grader that answers YES anyway
    is scoring against a string that characterises nothing."""
    result = await grade(quality="location_only")   # the fake grader says YES to both
    assert result.identified_flaw is True
    assert result.characterises_the_flaw is False
    assert result.characterisation_ungradable is True
    assert result.valid is False


async def test_grading_a_sound_item_raises_rather_than_returning_false():
    """No objection can be valid when the solution is sound, so reaching here with one
    is a caller bug — and a polite False would enter the analysis as a measurement."""
    with pytest.raises(NotGradable, match="sound item"):
        await grade_objection(case(gold_flawed=False), "obj", config=make_config(),
                              grading=GradingConfig(), client=FakeClient())


async def test_the_grader_is_off_the_decision_path():
    from exp2.accounting import OFF_PATH_ROLES
    client = FakeClient()
    await grade(client=client)
    assert client.calls[0]["meta"]["role"] == "grader"
    assert "grader" in OFF_PATH_ROLES


# --- rates ---------------------------------------------------------------------------


def row(**kw):
    base = dict(item_id="i1", row_id="r1", condition="debate", subset="theoremqa",
                label_basis="injected_pair", gold_flawed=True, initially_correct=False,
                initially_incorrect=True, gradable=True, challenge_raised=True,
                challenge_declined=False, identified_flaw=True, grade_valid=True,
                changed_the_decision=True, comprehension=4)
    base.update(kw)
    return base


def test_wilson_intervals_have_width_at_the_extremes():
    """A normal interval collapses to zero width at 0/n, reporting certainty there is
    none — and 0/n is an expected outcome here."""
    low, high = Rate("r", 0, 10).interval()
    assert low == 0.0 and high > 0.05
    low, high = Rate("r", 10, 10).interval()
    assert high == 1.0 and low < 0.95
    assert Rate("r", 0, 0).interval() is None


def test_the_error_types_are_kept_apart():
    assert error_type(row(gold_flawed=True, initially_correct=False)) == "false_negative"
    assert error_type(row(gold_flawed=False, initially_correct=False)) == "false_positive"
    assert error_type(row(initially_correct=True)) is None


def test_ungraded_rows_are_excluded_rather_than_counted_as_misses():
    """exp1's bug: analysing before grading reported 0/N with a tight interval."""
    rows = [row(), row(item_id="i2", grade_valid=None, identified_flaw=None)]
    rates = funnel(rows)["rates"]
    assert rates["valid_objection"]["k"] == 1
    assert rates["valid_objection"]["n"] == 1              # measured, not 2
    assert rates["valid_objection"]["coverage"] == {"measured": 1, "eligible": 2}


def test_detection_and_validity_have_different_denominators():
    """gpqa records where the flaw is but not what it is. That is exactly what the
    where-bar asks, so its 382 items belong in the detection row — but not in the
    validity row, where a clamped False would read as a failure rather than as
    something that could not be measured."""
    rows = [
        row(item_id="fn", gold_flawed=True, gradable=True),
        row(item_id="fp", gold_flawed=False),          # false positive: no valid objection
        # gpqa: graded for detection, clamped on characterisation
        row(item_id="ng", gold_flawed=True, gradable=False,
            identified_flaw=True, grade_valid=False),
    ]
    summary = funnel(rows)
    assert summary["n_detectable_false_negative"] == 2
    assert summary["n_characterisable_false_negative"] == 1
    assert summary["rates"]["identified_flaw"]["n"] == 2      # gpqa counts here
    assert summary["rates"]["valid_objection"]["n"] == 1      # and not here
    assert summary["n_false_positive"] == 1
    # but the false-positive cell still gets a revision rate
    assert summary["rates"]["revised_given_false_positive"]["n"] == 1


def test_a_frame_missing_every_optional_column_does_not_raise():
    """exp1's bug: frame.get(col) returns None, None == False is a scalar, and
    frame[False] raises KeyError."""
    bare = [{"item_id": "i1", "condition": "debate"}]
    summary = funnel(bare)
    assert summary["n"] == 1
    assert summary["rates"]["valid_objection"]["n"] == 0


def test_comprehension_is_reported_as_a_distribution_not_only_a_mean():
    """A flat 4-5 is the expected outcome and a mean would hide it."""
    rows = [row(comprehension=4), row(item_id="i2", comprehension=5),
            row(item_id="i3", comprehension=4)]
    summary = funnel(rows)["comprehension"]
    assert summary["distribution"]["4"] == 2 and summary["distribution"]["5"] == 1
    assert summary["mean"] == pytest.approx(13 / 3)


def test_the_bootstrap_clusters_on_the_upstream_row():
    """Two items from one row are anything but independent — for the paired subsets
    they differ by a single edit."""
    # Both items of a row behave alike, which is the realistic case: for the paired
    # subsets the two solutions differ by a single edit.
    paired = [row(item_id=f"i{n}", row_id=f"r{n // 2}",
                  changed_the_decision=((n // 2) % 2 == 0)) for n in range(20)]
    independent = [row(item_id=f"i{n}", row_id=f"r{n}",
                       changed_the_decision=((n // 2) % 2 == 0)) for n in range(20)]
    other = [row(item_id=f"o{n}", row_id=f"q{n}", changed_the_decision=False)
             for n in range(20)]
    clustered = bootstrap_difference(paired, other, "changed_the_decision")
    unclustered = bootstrap_difference(independent, other, "changed_the_decision")
    assert clustered["checked"] and unclustered["checked"]
    clustered_width = clustered["ci_high"] - clustered["ci_low"]
    unclustered_width = unclustered["ci_high"] - unclustered["ci_low"]
    assert clustered_width > unclustered_width


# --- the caveats -----------------------------------------------------------------------


def test_the_caveats_name_every_accepted_limitation():
    rows = [row(condition="debate"), row(condition="single", initially_correct=True,
                                         initially_incorrect=False)]
    text = " ".join(caveats(rows, ["debate", "single", "self_critique"]))
    assert "NOT INTERSECTED" in text
    assert "weak_alone" in text
    assert "specious" in text
    assert "label_basis" in text
    assert "understates debate" in text


def test_analyse_puts_the_caveats_and_the_overlaps_in_the_output(tmp_path):
    index = tmp_path / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in [
        row(item_id="i1", condition="debate"),
        row(item_id="i1", condition="single", initially_correct=True,
            initially_incorrect=False),
        row(item_id="i2", condition="debate"),
    ]), encoding="utf-8")
    metrics = analyse(index, ["debate", "single"])
    assert metrics["caveats"] and metrics["caveats"][0].startswith("NOT INTERSECTED")
    assert metrics["matching"]["per_condition"] == {"debate": 2, "single": 0}
    assert metrics["matching"]["in_every_condition"] == 0
    assert "debate" in metrics["by_condition"]
    assert metrics["small_cells"]  # n < 20 is flagged, not silently reported
