"""The funnel and its uncertainty.

Two properties matter more than the arithmetic:

1. **Wilson intervals stay usable at the endpoints.** A weak challenger scoring
   0/20 is an expected outcome here, and the normal approximation reports zero
   width for it — certainty from twenty trials.
2. **The bootstrap resamples by task, not by row.** The same task appears in
   every arm, so its rows move together; resampling rows would treat correlated
   observations as independent and narrow the interval below what the data
   supports.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from constitutional_debate.analysis import (
    Rate,
    analyse,
    bootstrap_difference,
    by_cell,
    funnel,
    read_index,
    token_balance,
)


def row(**kw) -> dict:
    base = dict(
        task_id="t1", decision_arm="debate", challenger_model="qwen3-8b",
        condition="matched", mechanism="unaided", initially_correct=False,
        challenge_raised=True, found_the_flaw=True, grade_valid=True,
        underspecified=False, changed=True, final_correct=True, gradable=True,
        decision_completion_tokens=2000, decision_record_words=1600,
    )
    return {**base, **kw}


def frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# intervals
# --------------------------------------------------------------------------- #


def test_a_zero_rate_gets_a_non_degenerate_interval():
    """The reason Wilson is used at all.

    p +/- 1.96*sqrt(p(1-p)/n) is exactly 0 wide at 0/20 — it would claim
    certainty from twenty trials, in the regime where this experiment expects
    to sit most often.
    """
    r = Rate("detection", 0, 20)
    lo, hi = r.interval
    assert r.value == 0.0
    assert lo == 0.0
    assert hi > 0.10, "an interval of zero width at 0/20 would be a lie"


def test_a_perfect_rate_also_gets_one():
    lo, hi = Rate("detection", 20, 20).interval
    assert hi == pytest.approx(1.0)  # floating point, not exactly 1.0
    assert lo < 0.90, "20/20 is not certainty either"


def test_intervals_stay_inside_the_unit_interval():
    for k, n in ((0, 5), (1, 5), (5, 5), (1, 100), (99, 100)):
        lo, hi = Rate("x", k, n).interval
        assert 0.0 <= lo <= hi <= 1.0, (k, n)


def test_an_empty_denominator_has_no_rate_rather_than_a_zero():
    r = Rate("detection", 0, 0)
    assert r.value is None and r.interval is None
    assert r.to_dict()["rate"] is None


# --------------------------------------------------------------------------- #
# denominators
# --------------------------------------------------------------------------- #


def test_each_rate_uses_its_own_denominator():
    """Detection is over incorrect decisions; false alarm over correct ones.

    Sharing a denominator would quietly answer a different question, and the
    numbers would still look plausible.
    """
    f = frame([
        row(initially_correct=False, challenge_raised=True),
        row(initially_correct=False, challenge_raised=False),
        row(initially_correct=True, challenge_raised=True),
        row(initially_correct=True, challenge_raised=False),
        row(initially_correct=True, challenge_raised=False),
    ])
    rates = funnel(f)["rates"]
    assert rates["detection"] == {"name": "detection", "n": 2, "k": 1, **{
        k: rates["detection"][k] for k in ("rate", "ci_low", "ci_high")}}
    assert rates["detection"]["n"] == 2, "over incorrect decisions only"
    assert rates["false_alarm"]["n"] == 3, "over correct decisions only"
    assert rates["detection"]["rate"] == 0.5


def test_correction_is_measured_over_valid_objections():
    f = frame([
        row(grade_valid=True, final_correct=True),
        row(grade_valid=True, final_correct=False),
        row(grade_valid=False, final_correct=True),
    ])
    assert funnel(f)["rates"]["correction"]["n"] == 2
    assert funnel(f)["rates"]["correction"]["k"] == 1


def test_ungradable_cases_are_excluded_from_the_graded_rates():
    """GPQA can support detection but not characterisation; it must not dilute it."""
    f = frame([
        row(gradable=True, grade_valid=True),
        row(gradable=False, grade_valid=False),
    ])
    assert funnel(f)["rates"]["valid_objection"]["n"] == 1


def test_an_empty_frame_produces_no_rates_rather_than_crashing():
    assert funnel(pd.DataFrame())["n"] == 0


# --------------------------------------------------------------------------- #
# grouping
# --------------------------------------------------------------------------- #


def test_the_funnel_is_reported_per_arm_and_split_by_mechanism():
    """The two error routes are biased in opposite directions.

    Natural errors select the debates where debate surfaced the flaw worst;
    forced errors include the ones where it was well exposed. A combined number
    hides which way the estimate leans.
    """
    f = frame([
        row(decision_arm="debate", mechanism="unaided"),
        row(decision_arm="debate", mechanism="steered"),
        row(decision_arm="single", mechanism="unaided"),
    ])
    out = by_cell(f, keys=("decision_arm",))
    assert set(out) >= {"overall", "debate", "single"}
    assert set(out["debate"]["by_mechanism"]) == {"unaided", "steered"}


# --------------------------------------------------------------------------- #
# the bootstrap
# --------------------------------------------------------------------------- #


def test_the_bootstrap_clusters_by_task_not_by_row():
    """Resampling rows would understate the interval on paired data.

    Constructed so every task is internally consistent and the arms differ:
    clustering by task must keep whole tasks together, so the resampled
    difference is far less variable than row resampling would suggest.
    """
    rows = []
    for i in range(30):
        rows.append(row(task_id=f"t{i}", decision_arm="debate", changed=True))
        rows.append(row(task_id=f"t{i}", decision_arm="single", changed=False))
    result = bootstrap_difference(
        frame(rows), column="changed", arm_a="debate", arm_b="single", draws=200,
    )
    assert result["difference"] == pytest.approx(1.0)
    assert result["clustered_by"] == "task_id"
    # every resample yields the same difference, because each task carries both
    # arms and both are constant — an interval of ~0 is correct here
    assert result["ci_low"] == pytest.approx(1.0)
    assert result["ci_high"] == pytest.approx(1.0)


def test_the_bootstrap_is_seeded_and_reproducible():
    rows = [
        row(task_id=f"t{i}", decision_arm=arm, changed=(i + (arm == "single")) % 2 == 0)
        for i in range(20) for arm in ("debate", "single")
    ]
    a = bootstrap_difference(frame(rows), column="changed", arm_a="debate",
                             arm_b="single", draws=100, seed=7)
    b = bootstrap_difference(frame(rows), column="changed", arm_a="debate",
                             arm_b="single", draws=100, seed=7)
    assert a == b


def test_the_bootstrap_declines_rather_than_inventing_a_number():
    empty = bootstrap_difference(pd.DataFrame(), column="changed", arm_a="a", arm_b="b")
    assert empty["difference"] is None and empty["draws"] == 0


# --------------------------------------------------------------------------- #
# the compute-matching check
# --------------------------------------------------------------------------- #


def test_an_arm_outside_the_record_band_is_flagged_not_dropped():
    """The confound the design controls for is checked, not assumed."""
    f = frame(
        [row(decision_arm="debate", decision_record_words=4000)] * 5
        + [row(decision_arm="single", decision_record_words=500)] * 5
    )
    result = token_balance(f, tolerance=0.25)
    assert result["checked"]
    assert set(result["outside_band"]) == {"debate", "single"}


def test_balanced_arms_are_not_flagged():
    f = frame(
        [row(decision_arm="debate", decision_record_words=2000)] * 5
        + [row(decision_arm="single", decision_record_words=2100)] * 5
    )
    assert token_balance(f)["outside_band"] == {}


def test_a_constructed_arm_is_judged_on_its_record_not_its_wire_tokens():
    """The case that motivated the switch.

    A constructed `single` cell makes zero calls, so its completion-token count
    is 0 by construction. Balancing on that reports a gulf that says nothing
    about how much text a challenger has to attack — and would hide the real
    ~8:1 gap in the records themselves behind a number meaning something else.
    """
    f = frame(
        [row(decision_arm="debate",
             decision_completion_tokens=2400, decision_record_words=1600)] * 5
        + [row(decision_arm="single",
               decision_completion_tokens=0, decision_record_words=200)] * 5
    )
    result = token_balance(f, tolerance=0.25)
    assert result["mean_by_arm"] == {"debate": 1600.0, "single": 200.0}
    assert set(result["outside_band"]) == {"debate", "single"}


def test_arms_matched_on_record_are_not_flagged_for_spending_differently():
    """The converse: `single` generates nothing and still reads the same length.

    Under outcome control that is the *intended* state, and a balance check that
    flagged it would be reporting the construction rather than a confound.
    """
    f = frame(
        [row(decision_arm="debate",
             decision_completion_tokens=2400, decision_record_words=1000)] * 5
        + [row(decision_arm="single",
               decision_completion_tokens=0, decision_record_words=1000)] * 5
    )
    assert token_balance(f)["outside_band"] == {}


def test_an_index_without_the_record_column_declines_rather_than_guessing():
    """An index built before the column existed must not be scored on a
    different quantity that happens to be present."""
    f = frame([{k: v for k, v in row().items() if k != "decision_record_words"}] * 4)
    assert token_balance(f) == {"checked": False}


# --------------------------------------------------------------------------- #
# end to end
# --------------------------------------------------------------------------- #


def test_analyse_reads_an_index_and_produces_metrics(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text(
        "".join(json.dumps(row(task_id=f"t{i}")) + "\n" for i in range(4)),
        encoding="utf-8",
    )
    out = analyse(path)
    assert out["rows"] == 4
    assert out["funnel"]["overall"]["rates"]["detection"]["n"] == 4
    assert out["token_balance"]["checked"]


def test_a_missing_index_is_an_empty_frame_not_an_error(tmp_path):
    assert read_index(tmp_path / "nope.jsonl").empty
    assert analyse(tmp_path / "nope.jsonl")["rows"] == 0
