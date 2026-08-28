"""The committed derivation scripts, which are what the write-up's numbers come from.

`records/derivations/*.py` are stdlib-only scripts that re-derive a published number
from committed `index.jsonl` files on a bare clone. They are not importable as a package
— the filenames carry hyphens on purpose, because they are run and not imported by the
harness — so this module loads them by path.

Only `judgment-debate-vs-alone.py` is covered here, and only its arithmetic and its
join: it is the one whose headline is a SIGNIFICANCE TEST rather than a rate, and a
p-value nobody checked against a hand computation is the kind of number that survives
review because it looks like one.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

DERIVATIONS = Path(__file__).resolve().parent.parent / "records" / "derivations"


def _load(name: str):
    path = DERIVATIONS / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def jd():
    return _load("judgment-debate-vs-alone.py")


# --- the exact test -------------------------------------------------------------------


def test_mcnemar_matches_the_hand_computation(jd):
    """b=10, c=3. The two-sided exact p is twice the smaller tail of Binomial(13, 1/2):

        sum_{k<=3} C(13,k) = 1 + 13 + 78 + 286 = 378
        p = 2 * 378 / 2^13 = 756 / 8192 = 0.0922851562500

    Written out here rather than delegated to the function under test, which is the
    whole point of the check.
    """
    assert jd.mcnemar_exact(10, 3) == pytest.approx(756 / 8192)
    assert jd.mcnemar_exact(10, 3) == pytest.approx(0.09228515625, abs=1e-12)
    # and it is symmetric: which arm is called "fixed" cannot move a two-sided p
    assert jd.mcnemar_exact(3, 10) == jd.mcnemar_exact(10, 3)
    # not significant at 0.05, which is what this run's alpha would say about it
    assert jd.mcnemar_exact(10, 3) > 0.05


def test_an_even_split_is_p_equals_one(jd):
    """b = c is the null exactly: the two tails together are the whole distribution and
    then some, and the cap at 1 is what keeps it a probability."""
    for b in (0, 1, 3, 5, 20, 100):
        assert jd.mcnemar_exact(b, b) == 1.0
    # no discordant pair at all is no evidence, not a significant null
    assert jd.mcnemar_exact(0, 0) == 1.0


def test_a_lopsided_split_is_significant(jd):
    """13 fixed and 0 broken: 2 / 2^13. The direction the endpoint is looking for."""
    assert jd.mcnemar_exact(13, 0) == pytest.approx(2 / 8192)
    assert jd.mcnemar_exact(13, 0) < 0.05
    # a well-known small case, computed by hand: b=6, c=1 -> 2*(1+7)/2^7 = 0.125
    assert jd.mcnemar_exact(6, 1) == pytest.approx(0.125)


def test_negative_discordant_counts_are_refused(jd):
    with pytest.raises(ValueError):
        jd.mcnemar_exact(-1, 3)


def test_wilson_has_width_at_the_extremes(jd):
    """The reason this repo uses Wilson and not the normal approximation: 0/n is an
    expected outcome for several of the rates, and a zero-width interval there reports a
    certainty there is none."""
    low, high = jd.wilson(0, 10)
    assert low == 0.0 and high > 0.05
    low, high = jd.wilson(10, 10)
    assert high == 1.0 and low < 0.95
    low, high = jd.wilson(5, 10)
    assert low < 0.5 < high
    # an empty denominator is the whole interval, not a crash
    assert jd.wilson(0, 0) == (0.0, 1.0)


# --- the after-state rule -------------------------------------------------------------


def test_a_row_with_no_ruling_keeps_its_before_state(jd):
    """A re-rule tree writes the challenge and ruling columns only for cells that were
    contested. An absent `final_correct` is a cell nobody objected to — not a missing
    measurement — and reading it as anything else would make the neutral arm a 54-cell
    comparison instead of a 1,644-cell one."""
    assert jd.after_state({}, True) is True
    assert jd.after_state({}, False) is False
    assert jd.after_state({"final_correct": None}, True) is True
    assert jd.after_state({"final_correct": False}, True) is False
    assert jd.after_state({"final_correct": True}, False) is True


# --- end to end on a synthetic index --------------------------------------------------


def _write(path: Path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _cell(i, condition="debate", **kw):
    row = {"cell_id": f"c{i}__{condition}__r1", "item_id": f"i{i}", "row_id": f"r{i}",
           "subset": "theoremqa", "label_basis": "injected_pair", "condition": condition,
           "gold_flawed": True, "verdict": "FLAWED", "initially_correct": True,
           "initially_incorrect": False}
    row.update(kw)
    return row


def synthetic(tmp_path: Path, *, fixed: int, broken: int, condition="debate"):
    """A three-index fixture with exactly `fixed` and `broken` discordant pairs.

    Concordant cells are added on both sides so the 2x2 has all four corners: a table
    where every pair is discordant would not catch a script that forgot to exclude the
    concordant ones, which is the one thing McNemar is FOR.
    """
    before, procedural, neutral = [], [], []
    i = 0
    def add(was_right, is_right):
        nonlocal i
        i += 1
        before.append(_cell(i, condition, initially_correct=was_right,
                            initially_incorrect=not was_right))
        procedural.append(_cell(i, condition, initially_correct=was_right,
                                initially_incorrect=not was_right,
                                challenge_stance="contests", challenge_raised=True,
                                ruling_form="stated_conclusion",
                                changed_the_decision=was_right != is_right,
                                final_correct=is_right))
        # the neutral arm objected to nothing, so every cell keeps its before-state and
        # the columns a re-rule tree would not have written are simply absent
        neutral.append(_cell(i, condition, initially_correct=was_right,
                             initially_incorrect=not was_right))
    for _ in range(fixed):
        add(False, True)
    for _ in range(broken):
        add(True, False)
    for _ in range(7):
        add(True, True)
    for _ in range(5):
        add(False, False)

    paths = {}
    for name, rows in (("before", before), ("procedural", procedural),
                       ("neutral", neutral)):
        paths[name] = tmp_path / f"{name}.jsonl"
        _write(paths[name], rows)
    return paths


def run(jd, paths, *extra):
    """`main()` reads `sys.argv`, which is how it is run for real."""
    argv = sys.argv
    sys.argv = ["judgment-debate-vs-alone.py",
                "--before", str(paths["before"]),
                "--neutral", str(paths["neutral"]),
                "--procedural", str(paths["procedural"]), *extra]
    try:
        jd.main()
    finally:
        sys.argv = argv


def test_the_script_reproduces_the_hand_computed_p(tmp_path, capsys, jd):
    """b = 10, c = 3 end to end: the join, the 2x2, fixed/broken/net and the p."""
    paths = synthetic(tmp_path, fixed=10, broken=3)
    run(jd, paths)
    out = capsys.readouterr().out

    assert "b = 10" in out and "c = 3" in out
    assert "NET                                    +7 cells" in out
    assert f"p = {0.09228515625:.6g}" in out
    assert "not significant at alpha=0.05" in out
    assert "discordant pairs                       13" in out
    assert "concordant 12" in out
    # accuracy before = 10 correct of 25, after = 17 of 25
    assert "10/25 40.0%" in out and "17/25 68.0%" in out
    # the neutral arm objected to nothing, so it is the before-state exactly
    assert "third arm NEUTRAL -> PROCEDURAL  n=25  fixed 10  broken 3  net +7" in out


def test_an_even_split_end_to_end_is_p_equals_one(tmp_path, capsys, jd):
    paths = synthetic(tmp_path, fixed=4, broken=4)
    run(jd, paths)
    out = capsys.readouterr().out
    assert "NET                                    +0 cells" in out
    assert "p = 1 " in out or "p = 1\n" in out
    assert "primary   BEFORE -> PROCEDURAL   n=20  fixed 4  broken 4  net +0  p = 1" in out


def test_the_other_two_conditions_are_excluded(tmp_path, capsys, jd):
    """The procedure is defined only where the record is a document other than the
    judgment, so a stray `single` row in any of the three indexes must not reach a
    table — silently pooling one would put a condition in the endpoint that has no
    judgment to audit."""
    paths = synthetic(tmp_path, fixed=2, broken=1)
    for name in ("before", "procedural", "neutral"):
        rows = [json.loads(l) for l in paths[name].read_text().splitlines()]
        rows.append(_cell(99, "single", initially_correct=False,
                          initially_incorrect=True, final_correct=True))
        _write(paths[name], rows)

    run(jd, paths)
    out = capsys.readouterr().out
    assert "BEFORE debate rows                 15" in out
    assert "primary   BEFORE -> PROCEDURAL   n=15  fixed 2  broken 1  net +1" in out


def test_a_join_over_different_decisions_is_refused(tmp_path, capsys, jd):
    """The procedural run reads its decisions out of the before tree through
    `decisions_from`, so the two indexes describe the SAME decisions by construction. If
    they do not, the join is against a tree that was re-decided under the same name and
    every paired number is meaningless — so it stops rather than printing."""
    paths = synthetic(tmp_path, fixed=2, broken=1)
    rows = [json.loads(l) for l in paths["procedural"].read_text().splitlines()]
    rows[0]["initially_correct"] = not rows[0]["initially_correct"]
    _write(paths["procedural"], rows)

    with pytest.raises(SystemExit, match="do not describe the same decisions"):
        run(jd, paths)


def test_the_committed_indexes_are_what_the_defaults_name(jd):
    """The two committed inputs must exist on a bare clone, or the script's defaults
    are a promise the repository does not keep."""
    repo = DERIVATIONS.parent.parent
    assert (repo / "records/experiments/sweep/index.jsonl").is_file()
    assert (repo / "records/experiments/rerule/recontest/index.jsonl").is_file()


def test_the_math_needs_nothing_outside_the_standard_library(jd):
    """Every derivation runs on a bare clone with no venv beyond python itself."""
    source = (DERIVATIONS / "judgment-debate-vs-alone.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned
    assert math  # the one maths import it does make
