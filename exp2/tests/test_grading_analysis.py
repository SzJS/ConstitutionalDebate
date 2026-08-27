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
                initially_incorrect=True, gradable=True, challenge_stance="contests",
                challenge_raised=True, challenge_agreed=False, challenge_declined=False,
                challenge_unclear=False, identified_flaw=True, grade_valid=True,
                changed_the_decision=True, comprehension=4)
    base.update(kw)
    return base


def stance_row(stance, **kw):
    """A contested cell in one of the four stances, with the columns build_index writes."""
    flags = {f"challenge_{name}": stance == key for name, key in
             (("raised", "contests"), ("agreed", "agrees"),
              ("declined", "declined"), ("unclear", "unclear"))}
    return row(challenge_stance=stance, **flags, **kw)


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


def test_the_stances_partition_the_contests_and_never_double_count():
    """`challenge_raised` is the CONTESTING stance, not the word the model wrote.
    `agreed_with_decision` is structurally 0 since the challenger's line became one
    relative token, and it is still reported: a column that reads 0 says the shape did
    not occur, a column that is absent says nobody looked. A synthetic `agrees` row is
    used here precisely because the live pipeline can no longer produce one."""
    rows = [stance_row("contests", item_id="a"), stance_row("agrees", item_id="b"),
            stance_row("declined", item_id="c"), stance_row("unclear", item_id="d")]
    summary = funnel(rows)
    assert summary["stances"] == {
        "n_contests": 4,
        "counts": {"contests": 1, "agrees": 1, "declined": 1, "unclear": 1},
    }
    rates = summary["rates"]
    assert rates["objection_raised_given_incorrect"]["k"] == 1   # contests only
    assert rates["agreed_with_decision"]["k"] == 1
    assert rates["declined"]["k"] == 1
    assert rates["unclear_stance"]["k"] == 1
    # they add up to the four rows, with nothing counted twice
    assert (rates["objection_raised_given_incorrect"]["k"] + rates["agreed_with_decision"]["k"]
            + rates["declined"]["k"] + rates["unclear_stance"]["k"]) == 4


def test_the_line_and_the_prose_are_tabulated_against_each_other():
    """The instrument that keeps `contests` falsifiable. With one relative line there is
    no second answer for a reply to contradict, so nothing mechanical stops a challenger
    writing REVERSE and then agreeing with the verdict in prose — the phantom contest."""
    rows = [
        stance_row("contests", item_id="a", prose_stance="WRONG",
                   line_prose_agree=True, phantom_contest=False),
        stance_row("contests", item_id="b", prose_stance="RIGHT",
                   line_prose_agree=False, phantom_contest=True),
        stance_row("contests", item_id="c", prose_stance="NEITHER",
                   line_prose_agree=None, phantom_contest=False),
        stance_row("declined", item_id="d", prose_stance="RIGHT",
                   line_prose_agree=True, phantom_contest=False),
        stance_row("declined", item_id="e", prose_stance="WRONG",
                   line_prose_agree=False, phantom_contest=False),
        # contested but never measured: it must not be counted as agreement
        stance_row("contests", item_id="f"),
    ]
    table = funnel(rows)["line_vs_prose"]
    assert table["measured"] == 5 and table["eligible"] == 6
    assert table["table"]["REVERSE"] == {"RIGHT": 1, "WRONG": 1, "NEITHER": 1}
    assert table["table"]["STANDS"] == {"RIGHT": 1, "WRONG": 1, "NEITHER": 0}
    assert table["agree"] == 2 and table["disagree"] == 2
    # NEITHER is its own column: prose that takes no side has not contradicted its
    # label, it has failed to support it
    assert table["no_direction"] == 1
    assert table["phantom_contests"] == 1 and table["n_contests_measured"] == 3
    assert table["declines_arguing_for_reversal"] == 1
    # and the headline rate is over the contests that were actually read
    phantom = funnel(rows)["rates"]["phantom_contest"]
    assert phantom["k"] == 1 and phantom["n"] == 3


def test_an_unmeasured_contest_is_absent_from_the_cross_tab_not_counted_as_agreeing():
    """The same rule the graded columns follow: "not measured" and "measured and
    agreed" are different facts, and exp1 shipped the bug of conflating them."""
    table = funnel([stance_row("contests", item_id="a")])["line_vs_prose"]
    assert table["measured"] == 0 and table["eligible"] == 1
    assert table["agree"] == 0 and table["disagree"] == 0


def test_the_false_alarm_rate_is_split_by_gold_label():
    """Objecting to a correct SOUND verdict is inventing a flaw; objecting to a correct
    FLAWED verdict is denying a real one. A rise concentrated on the sound items is the
    signature of a prompt that invites the challenger to go looking, and the pooled rate
    cannot show it."""
    rows = [
        stance_row("contests", item_id="s1", gold_flawed=False, initially_correct=True,
                   initially_incorrect=False),
        stance_row("declined", item_id="s2", gold_flawed=False, initially_correct=True,
                   initially_incorrect=False),
        stance_row("declined", item_id="f1", gold_flawed=True, initially_correct=True,
                   initially_incorrect=False),
    ]
    rates = funnel(rows)["rates"]
    assert rates["false_alarm_given_correct"]["k"] == 1
    assert rates["false_alarm_given_correct"]["n"] == 3
    assert rates["false_alarm_given_correct_sound_item"]["k"] == 1
    assert rates["false_alarm_given_correct_sound_item"]["n"] == 2
    assert rates["false_alarm_given_correct_flawed_item"]["k"] == 0
    assert rates["false_alarm_given_correct_flawed_item"]["n"] == 1


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
    # the instrument that replaced the `agrees` stance has to be named where the rate
    # it replaced is reported, or a reader meets a structural 0 and reads it as a result
    assert "agreed_with_decision" in text and "phantom_contest" in text


def test_the_specious_objection_caveat_is_read_off_the_rulings_that_happened():
    """Under the historical routing the solo conditions re-decide their own appeal, and
    the caveat says so. Under `recourse_form="third_party"` nothing does, so that
    sentence would be false — and the residual asymmetry (the recourse judge also
    DECIDED the debate condition) is the one that is true instead."""
    historical = " ".join(caveats(
        [row(ruling_form="uphold_overturn"), row(ruling_form="restated_verdict")],
        ["debate", "single"]))
    assert "contradict itself in its own conversation" in historical

    third_party = " ".join(caveats(
        [row(ruling_form="uphold_overturn"), row(ruling_form="uphold_overturn")],
        ["debate", "single"]))
    assert "contradict itself in its own conversation" not in third_party
    assert "no condition adjudicates its own appeal" in third_party
    assert "DECIDED the debate condition" in third_party

    # an index with no rulings at all keeps the historical text: no evidence that every
    # appeal went to a third party is not evidence that it did
    assert "contradict itself in its own conversation" in " ".join(
        caveats([row(), row()], ["debate", "single"]))


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


# --- the ruling's line-vs-prose instrument -------------------------------------------


def ruled_row(**kw):
    """A row with a ruling and a reading of the judge's own prose."""
    base = dict(verdict="FLAWED", ruling_form="stated_conclusion",
                changed_the_decision=True, ruling_prose_conclusion="SOUND",
                ruling_line_mismatch=False)
    base.update(kw)
    return row(**base)


def test_the_ruling_line_mismatch_rate_is_split_by_parent_verdict():
    """That is where the failure lived: the re-contest's hand check found the old
    `Ruling:` line contradicting the judge's reasoning in 8 of 12 rulings on FLAWED
    decisions, because "the objection is valid" and "the text is flawed" collide only
    when the decision already said FLAWED. A pooled rate would halve it."""
    rows = [
        ruled_row(verdict="FLAWED", ruling_line_mismatch=True),
        ruled_row(verdict="FLAWED", ruling_line_mismatch=True),
        ruled_row(verdict="FLAWED", ruling_line_mismatch=False),
        ruled_row(verdict="SOUND", ruling_line_mismatch=False),
        ruled_row(verdict="SOUND", ruling_line_mismatch=False),
    ]
    rates = funnel(rows)["rates"]
    assert (rates["ruling_line_mismatch"]["k"], rates["ruling_line_mismatch"]["n"]) == (2, 5)
    flawed = rates["ruling_line_mismatch_on_flawed_parent"]
    assert (flawed["k"], flawed["n"]) == (2, 3)
    sound = rates["ruling_line_mismatch_on_sound_parent"]
    assert (sound["k"], sound["n"]) == (0, 2)
    # a cell that was never objected to has no line to check, and is not a pass
    with_decline = rows + [row(ruling_form=None, challenge_stance="declined")]
    assert funnel(with_decline)["rates"]["ruling_line_mismatch"]["n"] == 5
    assert funnel(with_decline)["n_ruled"] == 5


def test_the_ruling_cross_tab_reconstructs_the_line_from_the_record():
    """The index carries the PARENT verdict and whether the decision changed; the line's
    own conclusion is what those two imply. Same arithmetic as `resolve_ruling`, and the
    reason the ruling record states both halves."""
    table = funnel([
        # FLAWED parent, overturned -> the line said SOUND; the prose says FLAWED
        ruled_row(verdict="FLAWED", changed_the_decision=True,
                  ruling_prose_conclusion="FLAWED", ruling_line_mismatch=True),
        # FLAWED parent, upheld -> the line said FLAWED, and so does the prose
        ruled_row(verdict="FLAWED", changed_the_decision=False,
                  ruling_prose_conclusion="FLAWED", ruling_line_mismatch=False),
        # reasoning that settles on nothing is its own column, not a contradiction
        ruled_row(verdict="SOUND", changed_the_decision=False,
                  ruling_prose_conclusion="NEITHER", ruling_line_mismatch=True),
    ])["ruling_line_vs_prose"]
    assert table["measured"] == 3
    assert table["table"]["SOUND"]["FLAWED"] == 1
    assert table["table"]["FLAWED"]["FLAWED"] == 1
    assert table["line_sound_prose_flawed"] == 1
    assert table["no_direction"] == 1
    assert table["by_ruling_form"]["stated_conclusion"] == {"measured": 3, "mismatch": 2}


def test_the_ruling_line_caveat_says_measured_or_says_it_was_not_measured():
    """"we did not look" and "we looked and it was 5%" are the two facts a reader most
    needs kept apart. The generic version of this warning is what let the sweep's
    recourse numbers be quoted for a day before the hand check."""
    unmeasured = " ".join(caveats(
        [row(ruling_form="uphold_overturn"), row(ruling_form="uphold_overturn")],
        ["debate", "single"]))
    assert "has NOT been run" in unmeasured
    assert "8 of 12" in unmeasured

    measured = " ".join(caveats(
        [ruled_row(ruling_line_mismatch=True), ruled_row(ruling_line_mismatch=False)],
        ["debate", "single"]))
    assert "Measured here at 1/2 (50.0%)" in measured
    assert "ruling_line_mismatch_on_flawed_parent" in measured
    assert "bounded by the rate at which a ruling" in measured

    none_at_all = " ".join(caveats([row(ruling_form=None)], ["debate", "single"]))
    assert "No rulings are in this index" in none_at_all
