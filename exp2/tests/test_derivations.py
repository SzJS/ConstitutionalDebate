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


def test_the_post_hoc_sensitivity_substitutes_only_where_the_reader_answered(jd):
    """Section (f)'s rule, unit by unit. It is post hoc and descriptive, but it feeds a
    2x2 that a reader will hold beside the endpoint, so the substitution has to be exact.

    `ruling_prose_conclusion` is ALREADY the mapped verdict — the reader answers
    STANDS / CHANGED / NEITHER and `prose_conclusion_for_reading` turns the first two
    into the parent's verdict and its complement before the record is written — so this
    is a straight read of that column, never a second translation.
    """
    def row(**kw):
        base = {"gold_flawed": True, "verdict": "FLAWED", "initially_correct": True,
                "ruling_prompt_form": "materiality", "final_correct": True}
        base.update(kw)
        return base

    # STANDS on a FLAWED parent whose gold is FLAWED -> correct, whatever the line said
    assert jd.prose_after_state(
        row(ruling_prose_conclusion="FLAWED", final_correct=False), True) is True
    # CHANGED on the same parent -> SOUND, and gold is FLAWED, so wrong
    assert jd.prose_after_state(
        row(ruling_prose_conclusion="SOUND", final_correct=True), True) is False
    # the same two against a SOUND gold
    assert jd.prose_after_state(
        row(gold_flawed=False, ruling_prose_conclusion="SOUND"), True) is True
    assert jd.prose_after_state(
        row(gold_flawed=False, ruling_prose_conclusion="FLAWED"), True) is False

    # NEITHER is NOT substituted — the reader settled on nothing, so the line stands
    assert jd.prose_after_state(
        row(ruling_prose_conclusion="NEITHER", final_correct=False), True) is False
    # an object-level ruling is not substituted either, whatever the reader said
    assert jd.prose_after_state(
        row(ruling_prompt_form="object_level", ruling_prose_conclusion="SOUND",
            final_correct=True), True) is True
    # a row with no ruling at all keeps its before-state
    assert jd.prose_after_state({"gold_flawed": True}, False) is False
    # and an unlabelled item stays unlabelled rather than being scored against nothing
    assert jd.prose_after_state(
        row(gold_flawed=None, ruling_prose_conclusion="FLAWED"), True) is None


def test_the_sensitivity_block_prints_the_endpoint_beside_it(tmp_path, capsys, jd):
    """Whatever (f) says, (a) must still be the pre-registered number on the page, and
    (f) must be labelled post hoc everywhere it appears — the log body, the alarm table
    and the summary line."""
    # every cell in the fixture is `gold_flawed` on a FLAWED parent, and every ruled cell
    # gets a reader answer of STANDS — so under the rule every ruled cell is scored
    # against the parent verdict, which is the gold, and comes out CORRECT whatever its
    # line said. A maximal, hand-countable substitution.
    paths = synthetic(tmp_path, fixed=3, broken=2)
    rows = [json.loads(l) for l in paths["procedural"].read_text().splitlines()]
    ruled = 0
    for r in rows:
        if r.get("ruling_form"):
            ruled += 1
            r["ruling_prompt_form"] = "materiality"
            r["ruling_prose_conclusion"] = r["verdict"]      # STANDS
            r["ruling_line_mismatch"] = bool(r["changed_the_decision"])
    _write(paths["procedural"], rows)
    assert ruled == 17          # every cell in the fixture is contested and ruled
    run(jd, paths)
    out = capsys.readouterr().out

    assert "(f) POST-HOC SENSITIVITY — NOT PRE-REGISTERED, descriptive only" in out
    assert "It is post hoc, chosen after the mismatch rate was seen." in out
    assert "SECTION (a) IS THE ENDPOINT." in out
    assert "NOT PRE-REGISTERED" in out.split("SUMMARY")[-1]
    # the pre-registered endpoint is unchanged by the block below it
    assert "primary   BEFORE -> PROCEDURAL   n=17  fixed 3  broken 2  net +1" in out
    # under the rule every ruled cell is correct: the 5 that were wrong before become
    # fixed, plus the 3 the line had already fixed = 8, and nothing is broken
    assert "post hoc  BEFORE -> PROSE         n=17  fixed 8  broken 0  net +8" in out
    # the 5 whose line disagreed with the reader, plus the 2 concordant-wrong cells the
    # line left wrong and the reader calls correct
    assert "cells whose after-state moved under the rule   7" in out
    assert "line said WRONG, prose says correct          7" in out
    assert "line said correct, prose says WRONG          0" in out
    # the alarm table names both the mismatch and the substitution decision
    assert "reader said" in out and "substituted?" in out

    # NEITHER is never substituted, however loudly it disagrees
    for r in rows:
        if r.get("ruling_form"):
            r["ruling_prose_conclusion"] = "NEITHER"
    _write(paths["procedural"], rows)
    run(jd, paths)
    out = capsys.readouterr().out
    assert "cells whose after-state moved under the rule   0" in out
    assert "post hoc  BEFORE -> PROSE         n=17  fixed 3  broken 2  net +1" in out


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


# --- judgment-debate-2: the 3 x 3, P1 / P2 / P3 per judge -----------------------------


_JD2_FLAGS: dict = {}


@pytest.fixture(scope="module")
def jd2():
    module = _load("judgment-debate-2.py")
    _JD2_FLAGS.clear()
    _JD2_FLAGS.update(module.ARM_FLAGS)
    return module


def _jd2_row(i, **kw):
    """One debate row in the shape `build_index` writes for a judgment-family arm."""
    row = {"cell_id": f"c{i}__debate__r1", "item_id": f"i{i}", "row_id": f"r{i}",
           "subset": "theoremqa", "label_basis": "injected_pair", "condition": "debate",
           "gold_flawed": True, "verdict": "FLAWED",
           "initially_correct": True, "initially_incorrect": False}
    row.update(kw)
    return row


def _jd2_only(*args):
    """Arguments that run ONLY the arms named, with every other arm pointed at a path
    that does not exist.

    Without this the defaults pick up the live `outputs/experiments/judgment-debate`
    tree, so the finished run's nano row prints into the same capture and an assertion
    about "the arm under test" quietly reads the published one instead.
    """
    argv = []
    named = set(args[::2])
    for key, (flag, _) in {k: v for k, v in _JD2_FLAGS.items()}.items():
        if flag in named:
            continue
        argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


def _jd2_section(out: str, title: str) -> str:
    """One section of the output, so an assertion cannot match a sentence in another."""
    start = out.index(title)
    rest = out[start + len(title):]
    end = rest.find("\n(")
    return rest[:end] if end != -1 else rest


def _jd2_arm(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _contested(i, *, before, after, **kw):
    """A cell that was objected to and ruled. `final_correct` carries the after-state."""
    return _jd2_row(
        i, initially_correct=before, initially_incorrect=not before,
        challenge_arm="judgment", challenge_raised=True,
        ruling_form="stated_conclusion", ruling_prompt_form="materiality",
        changed_the_decision=before != after, final_correct=after, **kw)


def test_jd2_alphas_are_the_bonferroni_split_the_prereg_names(jd2):
    """The one thing in this script that a refactor could silently undo. Two judges take
    the corrected alpha; nano's P2 is one test and keeps 0.05. A p of 0.03 is significant
    under one and not the other, so a shared constant would be a wrong answer, not a
    tidier one."""
    assert jd2.ALPHA_FAMILY == 0.025
    assert jd2.ALPHA_SINGLE == 0.05
    assert 2 * jd2.ALPHA_FAMILY == jd2.ALPHA_SINGLE
    assert [j for j, _ in jd2.JUDGES] == ["nano", "maverick", "mini"]
    # and the sentence names its own alpha rather than saying "significant"
    assert "alpha=0.025" in jd2.verdict_at(0.01, jd2.ALPHA_FAMILY)
    assert jd2.verdict_at(0.03, jd2.ALPHA_FAMILY).startswith("not significant")
    assert jd2.verdict_at(0.03, jd2.ALPHA_SINGLE).startswith("SIGNIFICANT")


def test_jd2_mcnemar_and_wilson_agree_with_the_other_derivation(jd, jd2):
    """Two scripts will quote p-values side by side in the same write-up. If they drift
    the reader sees two numbers for one test."""
    for b, c in ((10, 3), (0, 0), (7, 7), (173, 128), (30, 2)):
        assert jd2.mcnemar_exact(b, c) == jd.mcnemar_exact(b, c)
    for k, n in ((0, 10), (10, 10), (173, 1644)):
        assert jd2.wilson(k, n) == jd.wilson(k, n)
    with pytest.raises(ValueError):
        jd2.mcnemar_exact(-1, 3)


def test_jd2_after_state_and_prose_substitution(jd2):
    """The after-state rule is shared with every other derivation in this repo, and the
    prose substitution applies ONLY to a materiality ruling the reader actually decided —
    a NEITHER reading, an object-level ruling and an unruled cell all keep the line."""
    assert jd2.after_state({}, True) is True
    assert jd2.after_state({"final_correct": False}, True) is False

    gold_flawed = {"gold_flawed": True}
    # materiality + the reader answered: the prose wins
    assert jd2.prose_after_state(
        {**gold_flawed, "ruling_prompt_form": "materiality",
         "ruling_prose_conclusion": "FLAWED", "final_correct": False}, True) is True
    assert jd2.prose_after_state(
        {**gold_flawed, "ruling_prompt_form": "materiality",
         "ruling_prose_conclusion": "SOUND", "final_correct": True}, True) is False
    # NEITHER, object-level, and no ruling at all: the line stands
    for row in ({**gold_flawed, "ruling_prompt_form": "materiality",
                 "ruling_prose_conclusion": "NEITHER", "final_correct": False},
                {**gold_flawed, "ruling_prompt_form": "object_level",
                 "ruling_prose_conclusion": "FLAWED", "final_correct": False},
                {**gold_flawed, "final_correct": False}):
        assert jd2.prose_after_state(row, True) is False


def test_jd2_p1_counts_fixed_and_broken_over_a_synthetic_arm(tmp_path, capsys, jd2):
    """5 fixed, 2 broken, and concordant cells in both corners so a script that forgot to
    exclude them would be caught. b=5 c=2 -> 2 * (1+7+21) / 128 = 58/128 = 0.453125."""
    rows = ([_contested(i, before=False, after=True) for i in range(5)]
            + [_contested(100 + i, before=True, after=False) for i in range(2)]
            + [_contested(200 + i, before=True, after=True) for i in range(4)]
            + [_contested(300 + i, before=False, after=False) for i in range(3)])
    arm = _jd2_arm(tmp_path / "mav" / "index.jsonl", rows)
    jd2.main(_jd2_only("--real-maverick", str(arm)))
    out = capsys.readouterr().out
    assert "fixed   (BEFORE wrong -> AFTER correct)   b = 5" in out
    assert "broken  (BEFORE correct -> AFTER wrong)   c = 2" in out
    assert "NET                                    +3 cells" in out
    assert "p = 0.453125" in out
    # 0.453 is above BOTH alphas, and the line names the one that applies
    assert "not significant at alpha=0.025" in out
    # the arms that did not run say so rather than printing an empty table
    assert out.count("NOT RUN") >= 2


def test_jd2_p1_uses_the_corrected_alpha_for_a_flash_class_judge(tmp_path, capsys, jd2):
    """The whole point of the Bonferroni split, on a p that lands between the two alphas.

    b=8 c=1: 2 * (1 + 9) / 2^9 = 20/512 = 0.0390625 — significant at 0.05, NOT significant
    at 0.025. A judge in this position must be reported as not significant, and the
    temptation to quote it at 0.05 is exactly why the correction is written down first."""
    rows = ([_contested(i, before=False, after=True) for i in range(8)]
            + [_contested(100, before=True, after=False)]
            + [_contested(200 + i, before=True, after=True) for i in range(3)])
    arm = _jd2_arm(tmp_path / "mini" / "index.jsonl", rows)
    jd2.main(_jd2_only("--real-mini", str(arm)))
    out = capsys.readouterr().out
    assert "p = 0.0390625" in out
    assert "not significant at alpha=0.025" in out
    # and nowhere in the run does this p get quoted at the uncorrected alpha
    assert "SIGNIFICANT at alpha=0.05" not in out


def test_jd2_p2_pairs_the_real_arm_against_the_placeholder(tmp_path, capsys, jd2):
    """The second-look control. The same cells, ruled on a real objection and on a
    content-free one; only the cells BOTH arms carry are paired, and a cell one arm lacks
    is dropped and counted rather than defaulted to a before-state — defaulting would
    compare an arm against itself."""
    real = [_contested(i, before=False, after=True) for i in range(6)] \
        + [_contested(100 + i, before=False, after=False) for i in range(4)]
    placeholder = [_contested(i, before=False, after=False) for i in range(6)] \
        + [_contested(100 + i, before=False, after=False) for i in range(4)]
    # one cell only the real arm has: it must be dropped from the pairing
    real.append(_contested(999, before=False, after=True))
    a = _jd2_arm(tmp_path / "a" / "index.jsonl", real)
    c = _jd2_arm(tmp_path / "c" / "index.jsonl", placeholder)
    jd2.main(_jd2_only("--real-maverick", str(a), "--placeholder-maverick", str(c)))
    out = capsys.readouterr().out
    assert "paired on 10 cells both arms carry" in out
    assert "(1 in one arm only, dropped rather than defaulted)" in out
    # every one of the 6 is fixed by the real arm and not by the placeholder
    assert "fixed   (PLACEHOLDER wrong -> REAL correct)   b = 6" in out
    assert "THE AUDIT DID IT" in out


def test_jd2_p2_says_a_second_look_did_it_when_the_arms_do_not_differ(tmp_path, capsys,
                                                                      jd2):
    """The null this control exists to be able to report. Identical after-states means the
    audit added nothing the placeholder did not, and the script must say so in words
    rather than printing a net of 0 and leaving the reader to infer it."""
    rows = [_contested(i, before=False, after=True) for i in range(6)]
    a = _jd2_arm(tmp_path / "a" / "index.jsonl", rows)
    c = _jd2_arm(tmp_path / "c" / "index.jsonl", list(rows))
    jd2.main(_jd2_only("--real-mini", str(a), "--placeholder-mini", str(c)))
    out = capsys.readouterr().out
    block = _jd2_section(out, "P2 — openai/gpt-4.1-mini")
    assert "NOT SEPARATED at alpha=0.025" in block
    assert "not distinguishable from a second look" in block
    # the verdict sentence, not the legend in the section header
    assert "-> THE AUDIT DID IT" not in block


def test_jd2_p3_is_void_when_the_grader_validates_most_specious_objections(tmp_path,
                                                                           capsys, jd2):
    """The stopping rule PREREG.md states before the arm runs. A specious arm the grader
    largely VALIDATES did not produce specious objections, so it is a failed manipulation
    and not a null result about sycophancy — and no comparison may be printed from it."""
    spec = [_contested(i, before=False, after=True, grade_mode="judgment",
                       grade_valid=True) for i in range(5)] \
        + [_contested(100, before=False, after=False, grade_mode="judgment",
                      grade_valid=False)]
    real = [_contested(i, before=False, after=True) for i in range(6)]
    jd2.main(_jd2_only("--real-nano", str(_jd2_arm(tmp_path / "r" / "index.jsonl", real)),
                       "--specious-nano",
                       str(_jd2_arm(tmp_path / "s" / "index.jsonl", spec))))
    out = capsys.readouterr().out
    assert "graded VALID (the manipulation check) 5/6" in out
    assert "P3 IS VOID" in out
    assert "FAILED" in out and "MANIPULATION" in out
    assert "overturn on SPECIOUS" not in out


def test_jd2_p3_compares_overturn_rates_when_the_manipulation_held(tmp_path, capsys, jd2):
    """The check passes (1 of 6 valid), so the comparison is printed — on the OVERLAP
    only, with the cells the specious arm contested and the real one did not reported
    separately rather than pooled."""
    real = [_contested(i, before=False, after=True) for i in range(4)] \
        + [_contested(100 + i, before=False, after=False) for i in range(4)]
    spec = [_contested(i, before=False, after=True, grade_mode="judgment",
                       grade_valid=(i == 0)) for i in range(4)] \
        + [_contested(100 + i, before=False, after=True, grade_mode="judgment",
                      grade_valid=False) for i in range(4)] \
        + [_contested(500, before=False, after=True, grade_mode="judgment",
                      grade_valid=False)]
    jd2.main(_jd2_only("--real-nano", str(_jd2_arm(tmp_path / "r" / "index.jsonl", real)),
                       "--specious-nano",
                       str(_jd2_arm(tmp_path / "s" / "index.jsonl", spec))))
    out = capsys.readouterr().out
    assert "P3 IS VOID" not in out
    assert "graded VALID (the manipulation check) 1/9" in out
    # the real arm overturned 4 of the 8 shared; the specious arm overturned all 8
    assert "4/8 50.0%" in out and "8/8 100.0%" in out
    assert "+50.0 pts" in out
    assert "1 specious cells outside the overlap" in out


def test_jd2_the_grid_and_the_prose_sensitivity_cover_every_cell(tmp_path, capsys, jd2):
    """(d) prints all nine cells and (g) prints the post-hoc shift per arm, labelled.

    The prose row flips the two rulings whose reader answered against their line, so the
    net moves and the shift column is non-zero — a sensitivity that always printed the
    same number as the endpoint would be measuring nothing."""
    rows = [_contested(i, before=False, after=True) for i in range(4)]
    # two of them read the other way in prose: line says fixed, prose says still wrong
    for row in rows[:2]:
        row["ruling_prose_conclusion"] = "SOUND"
    jd2.main(_jd2_only("--real-maverick",
                       str(_jd2_arm(tmp_path / "m" / "index.jsonl", rows))))
    out = capsys.readouterr().out
    assert "(d) THE 3 x 3 — NET ACCURACY CHANGE IN EVERY CELL" in out
    assert "+4  (4f/0b)" in out
    assert "POST HOC, NOT THE ENDPOINT" in out
    # line net +4, prose net +2, shift -2
    assert "            +4            +2        -2" in out


def test_jd2_reproduces_the_finished_runs_published_endpoint(capsys, jd2):
    """The regression that matters most: the nano row of this script's P1 must reproduce
    `records/experiments/judgment-debate/`'s published 173 / 128 / +45 / p = 0.0110865
    exactly. If it does not, the two derivations disagree about the same cells and the
    write-up would carry two numbers for one result."""
    committed = (Path(__file__).resolve().parent.parent / "records" / "experiments"
                 / "judgment-debate" / "index.jsonl")
    jd2.main(_jd2_only("--real-nano", str(committed)))
    out = capsys.readouterr().out
    assert "b = 173" in out and "c = 128" in out
    assert "NET                                    +45 cells" in out
    assert "p = 0.0110865" in out
    assert "SIGNIFICANT at alpha=0.05" in out
