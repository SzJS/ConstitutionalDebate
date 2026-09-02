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


# --- judgment-debate-3: one judge throughout, P1 / P2 / P3 ----------------------------


_JD3_FLAGS: dict = {}


@pytest.fixture(scope="module")
def jd3():
    module = _load("judgment-debate-3.py")
    _JD3_FLAGS.clear()
    # GATE_FLAGS too, or `_jd3_only` leaves the two POST HOC inputs pointed at their live
    # defaults and a gate row prints real numbers into a synthetic test's capture.
    _JD3_FLAGS.update({**module.ARM_FLAGS, **module.PRELUDE_FLAGS, **module.GATE_FLAGS})
    return module


def _jd3_only(*args):
    """Arguments that run ONLY the indexes named, with every other one pointed at a path
    that does not exist — the prelude flags included.

    Without this the defaults pick up the live `judgment-debate` and `jd2-*-real` trees,
    so the published +45 and the abandoned chain's +124 print into the same capture and
    an assertion about the arm under test quietly matches one of those instead.
    """
    argv = []
    named = set(args[::2])
    for _, (flag, _default) in _JD3_FLAGS.items():
        if flag not in named:
            argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


def _jd3_arm(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


def _rejudged(i, *, before, after, source_correct=None, **kw):
    """A re-judged cell that was objected to and ruled.

    Shaped as `build_index` writes a jd3 row: the rejudge columns (`rejudged_from`,
    `source_verdict`, `source_correct`) beside the ordinary judgment-arm ones.
    """
    row = _contested(i, before=before, after=after, **kw)
    row["rejudged_from"] = "outputs/experiments/sweep"
    row["verdict"] = "FLAWED" if before == row["gold_flawed"] else "SOUND"
    if source_correct is not None:
        row["source_correct"] = source_correct
        row["source_verdict"] = ("FLAWED" if source_correct == row["gold_flawed"]
                                 else "SOUND")
    return row


def test_jd3_has_one_alpha_and_no_bonferroni_family(jd3):
    """The one thing about this script that a copy from judgment-debate-2.py could get
    silently wrong. That phase ran TWO judges and split 0.05 over them; this one runs one
    judge, and P1 and P2 are different comparisons against different arms rather than a
    family of two — PREREG.md says so before either arm ran. A 0.025 inherited from the
    older script would report a true result as not significant."""
    assert jd3.ALPHA == 0.05
    assert not hasattr(jd3, "ALPHA_FAMILY")
    assert "alpha=0.05" in jd3.verdict_at(0.01)
    assert jd3.verdict_at(0.03).startswith("SIGNIFICANT")
    assert jd3.verdict_at(0.30).startswith("not significant")


def test_jd3_mcnemar_and_wilson_agree_with_the_other_derivations(jd, jd2, jd3):
    """Three scripts will quote p-values side by side in the same write-up. If they drift
    the reader sees two numbers for one test."""
    for b, c in ((10, 3), (0, 0), (7, 7), (173, 128), (5, 3), (237, 113)):
        assert jd3.mcnemar_exact(b, c) == jd.mcnemar_exact(b, c)
        assert jd3.mcnemar_exact(b, c) == jd2.mcnemar_exact(b, c)
    for k, n in ((0, 10), (10, 10), (41, 60), (173, 1644)):
        assert jd3.wilson(k, n) == jd.wilson(k, n)
    with pytest.raises(ValueError):
        jd3.mcnemar_exact(-1, 3)


def test_jd3_p1_counts_fixed_and_broken_over_a_synthetic_arm(tmp_path, capsys, jd3):
    """M0 before, M1 after, in ONE index — which is the shape that differs from jd2, where
    before and after came from two trees. 5 fixed, 2 broken, and concordant cells in both
    corners so a script that forgot to exclude them would be caught.
    b=5 c=2 -> 2 * (1+7+21) / 128 = 58/128 = 0.453125."""
    rows = ([_rejudged(i, before=False, after=True) for i in range(5)]
            + [_rejudged(100 + i, before=True, after=False) for i in range(2)]
            + [_rejudged(200 + i, before=True, after=True) for i in range(4)]
            + [_rejudged(300 + i, before=False, after=False) for i in range(3)])
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    assert "fixed   (BEFORE wrong -> AFTER correct)   b = 5" in out
    assert "broken  (BEFORE correct -> AFTER wrong)   c = 2" in out
    assert "NET                                    +3 cells" in out
    assert "p = 0.453125" in out
    assert "not significant at alpha=0.05" in out
    # the arms that did not run say so rather than printing an empty table
    assert out.count("NOT RUN") >= 2


def test_jd3_p2_pairs_the_real_arm_against_the_placeholder(tmp_path, capsys, jd3):
    """The second-look control, and it matters more here than under nano: the judge that
    rules IS the judge that wrote the judgment being audited, so "it reconsidered" is an
    even more available explanation. Only the cells BOTH arms carry are paired; a cell one
    arm lacks is dropped and counted rather than defaulted to a before-state."""
    real = ([_rejudged(i, before=False, after=True) for i in range(6)]
            + [_rejudged(100 + i, before=False, after=False) for i in range(4)])
    placeholder = ([_rejudged(i, before=False, after=False) for i in range(6)]
                   + [_rejudged(100 + i, before=False, after=False) for i in range(4)])
    real.append(_rejudged(999, before=False, after=True))
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "a" / "index.jsonl", real),
                       "--placeholder",
                       _jd3_arm(tmp_path / "c" / "index.jsonl", placeholder)))
    out = capsys.readouterr().out
    assert "paired on 10 cells both arms carry" in out
    assert "(1 in one arm only, dropped rather than defaulted)" in out
    assert "fixed   (PLACEHOLDER wrong -> REAL correct)   b = 6" in out
    assert "-> THE AUDIT DID IT" in out


def test_jd3_p2_says_a_second_look_did_it_when_the_arms_do_not_differ(tmp_path, capsys,
                                                                      jd3):
    """The null this control exists to be able to report, in words rather than as a net of
    0 the reader has to interpret."""
    rows = [_rejudged(i, before=False, after=True) for i in range(6)]
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "a" / "index.jsonl", rows),
                       "--placeholder",
                       _jd3_arm(tmp_path / "c" / "index.jsonl", list(rows))))
    out = capsys.readouterr().out
    assert "NOT SEPARATED at alpha=0.05" in out
    assert "not distinguishable from a second look" in out
    assert "-> THE AUDIT DID IT" not in out


def test_jd3_p3_is_void_when_the_grader_validates_most_specious_objections(tmp_path,
                                                                           capsys, jd3):
    """The stopping rule PREREG.md states before the arm runs. A specious arm the grader
    largely VALIDATES did not produce specious objections, so it is a failed manipulation
    and not a null result about sycophancy — and no comparison may be printed from it."""
    spec = ([_rejudged(i, before=False, after=True, grade_mode="judgment",
                       grade_valid=True) for i in range(5)]
            + [_rejudged(100, before=False, after=False, grade_mode="judgment",
                         grade_valid=False)])
    real = [_rejudged(i, before=False, after=True) for i in range(6)]
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "r" / "index.jsonl", real),
                       "--specious", _jd3_arm(tmp_path / "s" / "index.jsonl", spec)))
    out = capsys.readouterr().out
    assert "graded VALID (the manipulation check) 5/6" in out
    assert "P3 IS VOID" in out
    assert "FAILED" in out and "MANIPULATION" in out
    assert "overturn on SPECIOUS" not in out


def test_jd3_p3_compares_overturn_rates_when_the_manipulation_held(tmp_path, capsys, jd3):
    """The check passes (1 of 9 valid), so the comparison is printed — on the OVERLAP
    only, with the cells the specious arm contested and the real one did not reported
    separately rather than pooled, because the specious instruction forbids the decline."""
    real = ([_rejudged(i, before=False, after=True) for i in range(4)]
            + [_rejudged(100 + i, before=False, after=False) for i in range(4)])
    spec = ([_rejudged(i, before=False, after=True, grade_mode="judgment",
                       grade_valid=(i == 0)) for i in range(4)]
            + [_rejudged(100 + i, before=False, after=True, grade_mode="judgment",
                         grade_valid=False) for i in range(4)]
            + [_rejudged(500, before=False, after=True, grade_mode="judgment",
                         grade_valid=False)])
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "r" / "index.jsonl", real),
                       "--specious", _jd3_arm(tmp_path / "s" / "index.jsonl", spec)))
    out = capsys.readouterr().out
    assert "P3 IS VOID" not in out
    assert "graded VALID (the manipulation check) 1/9" in out
    assert "4/8 50.0%" in out and "8/8 100.0%" in out
    assert "+50.0 pts" in out
    assert "1 specious cells outside the overlap" in out


def test_jd3_m0_against_nano_reads_the_source_column_and_is_never_tested(tmp_path, capsys,
                                                                         jd3):
    """The descriptive that must not be read as the endpoint. It joins on the
    `source_verdict` / `source_correct` columns the rejudge stage writes beside every
    re-judged decision, and it prints a p that is explicitly REPORTED, NOT TESTED — the
    phase tests what recourse does to Maverick's judgments, not whether Maverick judges
    better than nano."""
    rows = ([_rejudged(i, before=True, after=True, source_correct=False)
             for i in range(7)]
            + [_rejudged(100 + i, before=False, after=False, source_correct=True)
               for i in range(2)]
            + [_rejudged(200 + i, before=True, after=True, source_correct=True)
               for i in range(3)])
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    block = out[out.index("(d) M0 AGAINST"):out.index("(e) THE PRELUDE")]
    assert "maverick right where nano was wrong    7" in block
    assert "maverick wrong where nano was right    2" in block
    assert "NET                                    +5 cells" in block
    assert "REPORTED, NOT TESTED" in block
    # never the significance sentence: this comparison has no alpha at all
    assert "SIGNIFICANT" not in block and "not significant" not in block
    assert "accuracy maverick (M0)                 10/12" in block
    assert "accuracy nano (the sweep)              5/12" in block


def test_jd3_the_prelude_is_labelled_a_record_and_not_an_effect(tmp_path, capsys, jd3):
    """The abandoned chain's arms print with their nets, and the paragraph above them says
    why they are not the result: those judges are stronger than the one that judged the
    debates. A table of +124 with no such sentence is the misreading this phase exists to
    prevent."""
    prelude = ([_contested(i, before=False, after=True) for i in range(9)]
               + [_contested(100 + i, before=True, after=False) for i in range(2)])
    jd3.main(_jd3_only("--jd2-mav", _jd3_arm(tmp_path / "p" / "index.jsonl", prelude)))
    out = capsys.readouterr().out
    block = out[out.index("(e) THE PRELUDE"):out.index("(f) SECONDARY")]
    assert "re-ruled by maverick" in block
    assert "+7" in block
    assert "STRONGER than the nano that judged the debates" in block
    assert "not as an effect" in block
    assert "NOT comparable with (a)" in block
    # and the arms with no index say NOT RUN rather than printing a row of zeros
    assert block.count("NOT RUN") == 3


def test_jd3_prose_wins_is_post_hoc_and_actually_moves(tmp_path, capsys, jd3):
    """(h) recomputes every arm with the reader's reading of the prose over the ruling's
    own line. Two of the four rulings here read the other way, so the net moves — a
    sensitivity that always printed the endpoint again would be measuring nothing."""
    rows = [_rejudged(i, before=False, after=True) for i in range(4)]
    for row in rows[:2]:
        row["ruling_prose_conclusion"] = "SOUND"
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    assert "POST HOC, NOT THE ENDPOINT" in out
    block = out[out.index("(h) THE PROSE-WINS"):]
    assert "+4" in block and "+2" in block and "-2" in block


def _declined(i, *, correct: bool):
    """A cell the challenger DECLINED: no objection, no ruling, no after-state of its own.

    It is in the arm's population and in P1's 2x2 — it kept its before-state, which is a
    fact about the arm — and it must be in NEITHER conditional rate, because a cell nobody
    objected to cannot be fixed or broken by an objection.
    """
    return _jd2_row(i, initially_correct=correct, initially_incorrect=not correct,
                    challenge_arm="judgment", challenge_raised=False,
                    challenge_stance="declined", changed_the_decision=False,
                    final_correct=correct, rejudged_from="outputs/experiments/sweep")


def _gates_file(path: Path, admitted: dict[str, bool]) -> str:
    """`records/derivations/jd3-gates.py`'s output, in the shape the derivation reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(
        json.dumps({"cell_id": cell_id, "mech_admitted": flag, "defects_n": 1})
        for cell_id, flag in admitted.items()) + "\n", encoding="utf-8")
    return str(path)


def test_jd3_the_two_conditional_rates_are_the_first_table(tmp_path, capsys, jd3):
    """POST HOC in its placement, not in its arithmetic: the quantity is the
    discrimination section (f) has always printed, promoted to the top on 2026-08-28
    because the net alone hides the mechanism.

    13 wrong contested of which 5 end right (38.5%); 20 right contested of which 4 end
    wrong (20.0%); difference +18.5 pts. And the DENOMINATOR IS THE CONTESTED CELLS —
    the ten declines below are in the arm's population and in P1's 2x2, and must not be
    in either rate, or an arm that declines more would look better at nothing.
    """
    rows = ([_rejudged(i, before=False, after=True) for i in range(5)]
            + [_rejudged(50 + i, before=False, after=False) for i in range(8)]
            + [_rejudged(100 + i, before=True, after=False) for i in range(4)]
            + [_rejudged(200 + i, before=True, after=True) for i in range(16)]
            + [_declined(300 + i, correct=False) for i in range(10)])
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    block = out[out.index("(0) THE TWO CONDITIONAL RATES"):out.index("(a) P1")]
    assert "DESCRIPTIVE" in block and "No alpha and no test" in block
    assert "5/13 38.5%" in block          # fixed | wrong and contested
    assert "4/20 20.0%" in block          # broken | right and contested
    assert "+18.5 pts" in block
    # the declines are in the population but in neither rate: n is 33, not 43
    row = next(line for line in block.splitlines()
               if line.startswith("M1 — the real audit"))
    assert row.split()[5] == "33"      # n, after the five words of the label
    # and it really is FIRST: before P1, in the output
    assert out.index("(0) THE TWO CONDITIONAL RATES") < out.index("(a) P1")


def test_jd3_the_three_gate_rows_are_each_labelled_post_hoc(tmp_path, capsys, jd3):
    """The label is the point of the section. These rows were decided after M1's
    preliminary numbers were seen, none of them is in PREREG.md as committed, and a row
    that lost the label would read as a pre-registered result — which is the one
    misreading they can produce."""
    rows = [_rejudged(i, before=False, after=True, grade_valid=True,
                      grade_mode="judgment") for i in range(4)]
    gates = _gates_file(tmp_path / "g.jsonl", {r["cell_id"]: True for r in rows})
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows),
                       "--gates", gates,
                       "--gatekeeper", _jd3_arm(tmp_path / "k" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    block = out[out.index("(i) THREE GATES"):]
    assert block.count("POST HOC — added after M1 was seen") >= 4
    for name in ("THE MECHANICAL GATE", "M4 — THE SAME-CLASS GATEKEEPER",
                 "THE HAIKU-VALID BOUND"):
        assert name in block
    # the bound says it is a bound and says why, in the row itself
    assert "NOT A PROCESS" in block
    assert "stronger than the judge" in block
    assert "UPPER bound" in block
    # and the closing line still points at (a)
    assert "(a) is the endpoint" in block


def test_jd3_a_gate_counts_the_ruling_only_where_it_admitted(tmp_path, capsys, jd3):
    """The one arithmetic every gate row shares. Four cells whose ruling fixed a wrong
    decision and four whose ruling broke a right one; the gate admits the four fixes and
    refuses the four breaks, so the net goes from 0 to +4 with NO ruling re-made.

    That is the whole claim of the section: the same rulings, counted differently.
    """
    fixes = [_rejudged(i, before=False, after=True) for i in range(4)]
    breaks = [_rejudged(100 + i, before=True, after=False) for i in range(4)]
    rows = fixes + breaks
    admitted = {r["cell_id"]: True for r in fixes}
    admitted.update({r["cell_id"]: False for r in breaks})
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows),
                       "--gates", _gates_file(tmp_path / "g.jsonl", admitted)))
    out = capsys.readouterr().out
    ungated = out[out.index("(a) P1"):out.index("(b) P2")]
    assert "NET                                    +0 cells" in ungated

    block = out[out.index("THE MECHANICAL GATE"):out.index("M4 — THE SAME-CLASS")]
    assert "b = 4" in block and "c = 0" in block
    assert "NET                                    +4 cells" in block
    # the gate's own discrimination: it admitted every objection to a wrong decision and
    # none to a right one
    assert "admitted, decision was WRONG         4/4 100.0%" in block
    assert "admitted, decision was RIGHT         0/4 0.0%" in block
    assert "difference                           +100.0 pts" in block
    # and the two conditional rates travel with it
    assert "4/4 100.0%" in block and "0/4 0.0%" in block


def test_jd3_a_short_gate_file_is_refused_loudly_and_never_invented(tmp_path, capsys,
                                                                    jd3):
    """A contested cell the gate file does not carry counts as REFUSED, so a stale file
    understates the row rather than inventing admissions — and the coverage is printed
    with a warning, because a row quietly computed over half its cells is worse than one
    that says so."""
    rows = [_rejudged(i, before=False, after=True) for i in range(6)]
    partial = {rows[0]["cell_id"]: True, rows[1]["cell_id"]: True}
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows),
                       "--gates", _gates_file(tmp_path / "g.jsonl", partial)))
    out = capsys.readouterr().out
    block = out[out.index("THE MECHANICAL GATE"):out.index("M4 — THE SAME-CLASS")]
    assert "Gate file covers 2 of this arm's 6 contested cells" in block
    assert "the gate file is SHORT by 4 contested cells" in block
    assert "lower bound on a lower bound" in block
    assert "b = 2" in block          # only the two admitted cells count their ruling


def test_jd3_m4_reads_its_own_index_and_is_tested_against_m0(tmp_path, capsys, jd3):
    """M4 is an ARM, not a recomputation: its own tree, its own `gate_admitted` column,
    and its own exact McNemar against M0 at alpha = 0.05 — reported beside P1 as an
    ablation added after M1 was seen, never as P1.

    Its index already carries the gated `final_correct` that `build_index` wrote, and the
    derivation applies the same rule again on top; the two must agree, which is what
    running all three rows through one function buys.
    """
    rows = ([_rejudged(i, before=False, after=True, gate_admitted=True)
             for i in range(6)]
            + [_rejudged(100 + i, before=True, after=True, gate_admitted=False)
               for i in range(2)])
    jd3.main(_jd3_only("--gatekeeper", _jd3_arm(tmp_path / "k" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    block = out[out.index("M4 — THE SAME-CLASS"):out.index("THE HAIKU-VALID BOUND")]
    assert "b = 6" in block and "c = 0" in block
    assert "NET                                    +6 cells" in block
    assert "EXACT McNEMAR AGAINST M0 AT alpha = 0.05" in block
    assert "never as P1" in block
    assert "p = 0.03125" in block and "SIGNIFICANT at alpha=0.05" in block
    # the arms it does not have still say NOT RUN rather than printing zeros
    assert "MECHANICAL — every quotation verbatim" in out


def test_jd3_the_haiku_bound_counts_only_the_grader_s_valid_objections(tmp_path, capsys,
                                                                       jd3):
    """`outputs/leave-to-appeal.py`'s logic, folded in and labelled. Three fixes the
    grader called valid and three breaks it called invalid: counting only the valid ones
    turns a net of 0 into +3, which is exactly why it is a BOUND and not a result — the
    grader is Haiku, stronger than the judge it would be gating."""
    rows = ([_rejudged(i, before=False, after=True, grade_mode="judgment",
                       grade_valid=True) for i in range(3)]
            + [_rejudged(100 + i, before=True, after=False, grade_mode="judgment",
                         grade_valid=False) for i in range(3)])
    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out
    ungated = out[out.index("(a) P1"):out.index("(b) P2")]
    assert "NET                                    +0 cells" in ungated
    block = out[out.index("THE HAIKU-VALID BOUND"):]
    assert "b = 3" in block and "c = 0" in block
    assert "NET                                    +3 cells" in block
    assert "admitted, decision was WRONG         3/3 100.0%" in block
    assert "admitted, decision was RIGHT         0/3 0.0%" in block


def test_jd3_prints_the_two_rates_once_over_the_CONTESTED_cells(tmp_path, capsys, jd3):
    """ONE number, over one denominator, printed in two places that must agree.

    Until 2026-08-28 section (f) divided by the cells that produced a RULING while section
    (0) divided by the cells that were CONTESTED, and on the real arm that printed +19.5
    beside +19.6 for the same quantity — a reader holding the two side by side would think
    the script disagreed with itself. The contested denominator is the one kept: the
    question is what an OBJECTION does to a decision, so a cell that was objected to
    belongs in it whether or not its ruling survived, and a cell nobody objected to does
    not belong in it at all.

    The fixture is built so the two denominators would DIFFER if they were ever separated
    again: 4 wrong and 5 right cells contested, of which one wrong and one right lost their
    ruling (`ruling_form` absent, after-state = before-state), plus 6 declines that belong
    in neither. Ruled denominators would be 3 and 4; contested are 4 and 5.
    """
    contested = ([_rejudged(i, before=False, after=True) for i in range(2)]
                 + [_rejudged(10 + i, before=False, after=False) for i in range(2)]
                 + [_rejudged(100 + i, before=True, after=False) for i in range(2)]
                 + [_rejudged(110 + i, before=True, after=True) for i in range(3)])
    # two cells whose ruling was lost to a truncation: still contested, no ruling, and the
    # after-state is the before-state — exactly the shape M1 and M2 each carry
    for row in (contested[3], contested[8]):
        row.pop("ruling_form")
        row.pop("ruling_prompt_form")
        row["changed_the_decision"] = False
        row["final_correct"] = row["initially_correct"]
    rows = contested + [_declined(300 + i, correct=False) for i in range(6)]

    jd3.main(_jd3_only("--main", _jd3_arm(tmp_path / "m" / "index.jsonl", rows)))
    out = capsys.readouterr().out

    # 2 of 4 wrong cells fixed = 50.0%; 2 of 5 right cells broken = 40.0%; +10.0 pts.
    # Over the RULED cells it would be 2/3 = 66.7% and 2/4 = 50.0%, +16.7 pts — so a
    # regression that put the ruled denominator back cannot pass this test.
    headline = out[out.index("(0) THE TWO CONDITIONAL RATES"):out.index("(a) P1")]
    secondary = out[out.index("(f) SECONDARY"):out.index("(g) PER-SUBSET")]
    for block in (headline, secondary):
        assert "2/4 50.0%" in block
        assert "2/5 40.0%" in block
        assert "+10.0 pts" in block
        assert "66.7%" not in block and "+16.7 pts" not in block

    # and section (f) says whose numbers they are and what the denominator is, so the two
    # tables cannot be read as two measurements
    assert "REPEATS SECTION (0)'s TWO RATES AND DOES NOT RECOMPUTE THEM" in secondary
    assert "denominator is the CONTESTED cells" in secondary
    # the old column headings are gone with the old computation ("discr" on its own is
    # not searchable — "indiscriminately" contains it — so the heading is matched whole)
    assert "ovt wrong" not in out
    assert "ovt right" not in out
    assert "'discr':>10" not in (DERIVATIONS / "judgment-debate-3.py").read_text(
        encoding="utf-8")


def test_jd3_never_frames_a_challenge_as_a_diagnostic_instrument(jd3):
    """The user's call of 2026-08-28: the write-up uses the two conditional rates and
    their difference, and not the family of statistics that treats an objection as a test
    with a prior behind it. Enforced here because a helpful refactor would reintroduce it
    in a docstring, and once it is in one derivation it is in the write-up."""
    source = (DERIVATIONS / "judgment-debate-3.py").read_text(encoding="utf-8").lower()
    for banned in ("likelihood ratio", "likelihood-ratio", "lr+", "lr-",
                   "posterior odds", "prior odds", "bayes factor", "bayes' factor",
                   "sensitivity and specificity", "positive predictive"):
        assert banned not in source, banned
    # and the framing that IS used is named
    assert "the two conditional rates" in source


def test_jd3_is_stdlib_only_like_every_other_derivation(jd3):
    """It has to run on a bare clone with nothing installed — that is what makes a
    committed index a checkable number rather than a claim about a tree nobody has."""
    source = (DERIVATIONS / "judgment-debate-3.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned


# --- judgment-debate-4: the fabricated auditor, false by CODE -------------------------


_JD4_FLAGS: dict = {}


@pytest.fixture(scope="module")
def jd4():
    module = _load("judgment-debate-4.py")
    _JD4_FLAGS.clear()
    _JD4_FLAGS.update(module.ARM_FLAGS)
    return module


def _jd4_only(*args):
    """Arguments that run ONLY the indexes named, every other flag pointed at a path that
    does not exist.

    This script's defaults point at the COMMITTED records rather than at a live tree, so
    without this a synthetic test prints the real 896-cell arm into its own capture and an
    assertion about six fake cells quietly matches the published run instead."""
    argv = []
    named = set(args[::2])
    for _, (flag, _default) in _JD4_FLAGS.items():
        if flag not in named:
            argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


def _fabricated(i, *, before, after, fabrication_ok=True, defects=1, **kw):
    """A jd4 row: contested, ruled under materiality, with the manipulation check's own
    columns beside it."""
    row = _contested(i, before=before, after=after, **kw)
    row["challenge_arm"] = "judgment_fabricated"
    row["challenge_fabricated"] = True
    row["challenge_fabrication_ok"] = fabrication_ok
    row["challenge_defects_n"] = defects
    row["challenge_defects_fabricated_n"] = defects if fabrication_ok else 0
    row["challenge_defects_misattributed_n"] = defects
    row.setdefault("grade_mode", "judgment")
    row.setdefault("grade_valid", False)
    return row


def test_jd4_shares_its_statistics_with_every_other_derivation(jd, jd3, jd4):
    """Four scripts now quote p-values and intervals side by side in one write-up."""
    for b, c in ((10, 3), (0, 0), (42, 49), (110, 128), (173, 128)):
        assert jd4.mcnemar_exact(b, c) == jd3.mcnemar_exact(b, c) == jd.mcnemar_exact(b, c)
    for k, n in ((0, 10), (860, 896), (91, 894)):
        assert jd4.wilson(k, n) == jd3.wilson(k, n)
    with pytest.raises(ValueError):
        jd4.mcnemar_exact(3, -1)


def test_jd4_voids_the_arm_below_the_pre_registered_floor(tmp_path, capsys, jd4):
    """THE STOPPING RULE, and the only threshold in this phase. PREREG.md voids the arm
    if fewer than 80% of its objections carry only invented judgment quotations — the
    check is a string comparison the harness already made, so a script that printed a
    sycophancy comparison off a failed manipulation would be reporting M3's mistake with
    a different clause. 3 of 6 is 50%."""
    real = [_contested(i, before=True, after=True) for i in range(6)]
    fab = [_fabricated(i, before=True, after=(i % 2 == 0), fabrication_ok=(i < 3))
           for i in range(6)]
    jd4.main(_jd4_only("--main", _jd3_arm(tmp_path / "r" / "index.jsonl", real),
                       "--fabricated", _jd3_arm(tmp_path / "f" / "index.jsonl", fab)))
    out = capsys.readouterr().out
    assert jd4.FABRICATION_FLOOR == 0.80
    assert "3/6 50.0%" in out
    assert "THE ARM IS VOID" in out
    assert "THE MANIPULATION FAILED" in out
    assert "THE ARM IS VALID" not in out


def test_jd4_reads_every_arm_on_the_cells_the_real_audit_contested(tmp_path, capsys, jd4):
    """The population is not asserted, it is READ — off `challenge_raised` in M1's index,
    which is what the cases file was built from. A cell the real audit declined must not
    reach any row here, or the four arms stop being paired cell for cell."""
    real = ([_contested(i, before=False, after=True) for i in range(4)]
            + [_jd2_row(90, initially_correct=True, initially_incorrect=False,
                        challenge_arm="judgment", challenge_raised=False)])
    fab = [_fabricated(i, before=False, after=False) for i in range(4)]
    place = [_contested(i, before=False, after=False) for i in range(4)] + [
        _contested(90, before=True, after=False)]
    for row in place:
        row["challenge_arm"] = "placeholder"     # `_contested` writes the real audit's
    jd4.main(_jd4_only("--main", _jd3_arm(tmp_path / "r" / "index.jsonl", real),
                       "--fabricated", _jd3_arm(tmp_path / "f" / "index.jsonl", fab),
                       "--placeholder", _jd3_arm(tmp_path / "p" / "index.jsonl", place)))
    out = capsys.readouterr().out
    assert "population size: 4" in out
    # the declined cell is in the placeholder index and is NOT counted anywhere
    assert "5" not in out.split("population size: 4")[1].split("\n")[0]
    assert "THE ARM IS VALID" in out
    # the real audit fixed all four; the placeholder moved nothing
    assert "4/4 100.0%" in out


def test_jd4_reproduces_the_published_manipulation_check_and_ladder(capsys, jd4):
    """The regression that matters most here: run over the COMMITTED indexes with no
    arguments — which is the command README.md gives — this script must reproduce the
    numbers `LLM_NOTES.md` §3z and `CHECKLIST.md` quote. If it drifts, the write-up and
    the evidence disagree about the same 896 cells."""
    jd4.main([])
    out = capsys.readouterr().out
    assert "population size: 896" in out
    assert "860/896 96.0%" in out and "THE ARM IS VALID" in out
    assert "1/896 0.1%" in out                       # the grader, as the failure mode
    assert "238/895 26.6%" in out                    # M1
    assert "91/894 10.2%" in out                     # jd4
    assert "12/894 1.3%" in out                      # M2
    assert "b = 42" in out and "c = 49" in out
    assert "NET                                    -7 cells" in out
    assert "p = 0.529602" in out
    assert "86/858 10.0%" in out                     # the split on the code check
    assert "ABLATION" in out and "never an endpoint" in out.lower()


def test_jd4_is_stdlib_only_like_every_other_derivation(jd4):
    source = (DERIVATIONS / "judgment-debate-4.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned


# --- judgment-debate-5: one paragraph of Step 1, put to the same judge twice ----------


_JD5_FLAGS: dict = {}


@pytest.fixture(scope="module")
def jd5():
    module = _load("judgment-debate-5.py")
    _JD5_FLAGS.clear()
    _JD5_FLAGS.update(module.ARM_FLAGS)
    _JD5_FLAGS.update(module.LANGUAGE_FLAGS)
    return module


def _jd5_only(*args):
    """Arguments that run ONLY the indexes named. Same reason as `_jd4_only`: this
    script's defaults point at the COMMITTED records, so without this a synthetic
    assertion about six fake cells quietly matches the published 896-cell arms."""
    argv = []
    named = set(args[::2])
    for _, (flag, _default) in _JD5_FLAGS.items():
        if flag not in named:
            argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


def test_jd5_imports_its_statistics_from_jd4_rather_than_copying_them(jd, jd3, jd4, jd5):
    """jd4 and jd5 print rates about the SAME 896 cells side by side in one write-up, so
    a definition that drifted between them would be invisible. jd5 does not define its
    own — it re-exports the objects of the jd4 module it loaded, and this asserts
    IDENTITY against that module and not merely equality of results. (The `jd4` fixture
    is a second, independent load of the same file, so it is compared by behaviour.)"""
    assert jd5.mcnemar_exact is jd5.jd4.mcnemar_exact
    assert jd5.wilson is jd5.jd4.wilson
    assert jd5.load is jd5.jd4.load
    assert jd5.restrict is jd5.jd4.restrict
    assert jd5.overturned is jd5.jd4.overturned
    assert jd5.pairs_before_after is jd5.jd4.pairs_before_after
    assert jd5.paired_block is jd5.jd4.paired_block
    assert jd5.conditional_rates is jd5.jd4.conditional_rates
    assert jd5.jd4.__file__ == jd4.__file__
    assert jd5.ALPHA == jd4.ALPHA == 0.05
    for b, c in ((65, 23), (49, 122), (29, 20), (144, 167)):
        assert jd5.mcnemar_exact(b, c) == jd3.mcnemar_exact(b, c) == jd.mcnemar_exact(b, c)


def test_jd5_pairs_only_the_cells_both_arms_actually_ruled(tmp_path, jd5):
    """jd4 lost two rulings to truncation and M1 lost one; jd5 ruled 896/896 in both
    arms. A cell that was never put to one of the two judges cannot be counted as an
    uphold on that side, so it leaves the paired table rather than entering it as a
    concordant pair — which would dilute every rate in section (0)."""
    old = {f"c{i}": {"ruling_form": "stated_conclusion", "changed_the_decision": i < 2}
           for i in range(4)}
    old["c3"]["ruling_form"] = None                      # truncated in the old arm
    new = {f"c{i}": {"ruling_form": "stated_conclusion", "changed_the_decision": False}
           for i in range(4)}
    pairs = jd5.ruling_pairs(old, new, set(old))
    assert [c for c, _, _ in pairs] == ["c0", "c1", "c2"]
    assert [(a, b) for _, a, b in pairs] == [(True, False), (True, False), (False, False)]


def test_jd5_ruling_language_reads_the_prose_and_says_which_reading_it_used(jd5):
    """Section (d) is a KEYWORD INSTRUMENT and the only thing in this file that is not an
    index column. The verdict vocabulary collides with the absence vocabulary — "the text
    does not contain a flaw" is this judge's CONCLUSION, not a lookup — and a broad reading
    that counted it would have put arm B's absence rate near 60%."""
    found = jd5.ruling_language(
        'Upon reviewing the judgment, the sentence "X" is not found.')
    assert found["names_missing_strict"] and found["names_missing_broad"]
    assert not found["confirms_present"] and not found["essence"]
    verdict = jd5.ruling_language(
        "Conclusion: the original text in <solution> does not contain a flaw")
    assert not verdict["names_missing_strict"] and not verdict["names_missing_broad"]
    present = jd5.ruling_language('This sentence is present in the judgment.')
    assert present["confirms_present"] and not present["names_missing_broad"]
    repaired = jd5.ruling_language(
        'The quoted sentence is not found. However, the essence of the objection is real.')
    assert repaired["names_missing_strict"] and repaired["essence"]


def test_jd5_reproduces_the_published_paired_tables(capsys, jd5):
    """THE REGRESSION THAT MATTERS. Run over the COMMITTED indexes with no arguments —
    which is the command README.md gives — this script must reproduce what `LLM_NOTES.md`
    §3aa and `CHECKLIST.md` quote about the same 896 cells. If it drifts, the write-up and
    the evidence disagree."""
    jd5.main([])
    out = capsys.readouterr().out
    assert "population size: 896" in out
    # arm A — the fabricated objections, ruled twice
    assert "91/894 10.2%" in out and "49/894 5.5%" in out
    assert "49/896 5.5%" in out                       # its own ruled denominator
    assert "p = 8.50111e-06" in out
    # arm B — the real audit's objections, ruled twice
    assert "238/895 26.6%" in out and "311/895 34.7%" in out
    assert "311/896 34.7%" in out
    assert "p = 2.26826e-08" in out
    # the two nets, both ABLATIONS
    assert "NET                                    +9 cells" in out
    assert "NET                                    -23 cells" in out
    assert "ABLATION" in out and "never an endpoint" in out.lower()
    # the instrument, in both readings
    assert "834/896 93.1%" in out and "27/896 3.0%" in out
    assert "11/49 22.4%" in out
    # the pre-registered floor, met and uninformative
    assert "THE FLOOR WAS WRITTEN AGAINST THE WRONG RISK" in out
    assert "cannot be told apart" in out


def test_jd5_carries_both_explanations_and_picks_neither(jd5):
    """The user's call, and the reason this phase is reported rather than concluded: the
    two arms cannot separate 'verification licenses conviction' from 'the added paragraph
    changed the ruling's shape', and a script that named only one would be choosing."""
    source = (DERIVATIONS / "judgment-debate-5.py").read_text(encoding="utf-8")
    assert "VERIFICATION LICENSES CONVICTION" in source
    assert "THE PARAGRAPH CHANGED THE RULING'S SHAPE" in source
    assert "MECHANICALLY" in source


def test_jd5_is_stdlib_only_like_every_other_derivation(jd5):
    source = (DERIVATIONS / "judgment-debate-5.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned


# --- judgment-debate-6: an argued objection against an un-argued extra round -----------


@pytest.fixture(scope="module")
def jd6():
    return _load("judgment-debate-6.py")


def _jd6_only(*args):
    """Arguments that run ONLY the indexes named. Same reason as `_jd5_only`: this
    script's defaults point at the COMMITTED records, so without this a synthetic
    assertion about six fake cells quietly matches a published arm."""
    named = set(args[::2])
    argv = []
    for _key, (flag, _default) in _JD6_FLAGS.items():
        if flag not in named:
            argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


_JD6_FLAGS: dict = {}


def test_jd6_imports_its_statistics_rather_than_copying_them(jd4, jd5, jd6):
    """jd5 and jd6 print rates about the SAME 896 cells in one write-up, so a definition
    that drifted between them would be invisible. jd6 re-exports jd5's objects — which
    are themselves jd4's — and this asserts IDENTITY, not equality of results."""
    _JD6_FLAGS.clear()
    _JD6_FLAGS.update(jd6.ARM_FLAGS)
    assert jd6.mcnemar_exact is jd6.jd5.mcnemar_exact
    assert jd6.paired_block is jd6.jd5.paired_block
    assert jd6.ruling_pairs is jd6.jd5.ruling_pairs
    assert jd6.paired_ruling_block is jd6.jd5.paired_ruling_block
    assert jd6.load is jd6.jd5.load
    assert jd6.restrict is jd6.jd5.restrict
    assert jd6.ALPHA == jd5.ALPHA == jd4.ALPHA == 0.05


def test_jd6_reads_each_arms_before_and_after_out_of_its_own_columns(jd6):
    """THE ONE THING IN THIS FILE THAT COULD SILENTLY INVERT THE RESULT.

    Arm R is a RERULE — it decides nothing, so its row's `initially_correct` is M0's
    decision and `final_correct` is the ruling's. Arm B is a REJUDGE — it MAKES a
    decision, so its `initially_correct` is the AFTER-state and M0's is `source_correct`.
    Reading either with the other's accessor swaps before for after and reports the exact
    opposite of what happened, with every table still well formed.
    """
    rerule = {"initially_correct": True, "final_correct": False,
              "ruling_form": "stated_conclusion", "changed_the_decision": True}
    assert jd6.before_of(rerule, "R") is True
    assert jd6.after_of(rerule, "R") is False
    assert jd6.overturned_of(rerule, "R") is True

    rejudge = {"initially_correct": False, "source_correct": True,
               "verdict": "SOUND", "source_verdict": "FLAWED"}
    assert jd6.before_of(rejudge, "B") is True
    assert jd6.after_of(rejudge, "B") is False
    assert jd6.overturned_of(rejudge, "B") is True

    # a cell whose ruling or judgment never happened is not counted as an uphold
    assert jd6.overturned_of({"ruling_form": None}, "R") is None
    assert jd6.overturned_of({"verdict": None, "source_verdict": "SOUND"}, "B") is None
    # and a rerule with no ruling keeps the decision's own state
    assert jd6.after_of({"initially_correct": True, "final_correct": None}, "R") is True


def test_jd6_pairs_only_the_cells_both_arms_decided_and_splits_on_the_before_state(jd6):
    """P1 and P2 are two tests over one pairing, and what makes them two is the
    restriction to the cells M0 got right and the cells it got wrong. A cell one arm
    never decided leaves the table rather than entering it as a concordant pair."""
    a = {f"c{i}": {"initially_correct": i < 2, "final_correct": i % 2 == 0,
                   "ruling_form": "stated_conclusion"} for i in range(4)}
    b = {f"c{i}": {"initially_correct": True, "source_correct": i < 2,
                   "verdict": "SOUND", "source_verdict": "SOUND"} for i in range(4)}
    a["c3"]["ruling_form"] = None                     # never ruled in R
    a["c3"]["final_correct"] = None
    cells = set(a)

    every, disagreed = jd6.paired_states(a, b, cells)
    assert disagreed == 0
    assert [c for c, _, _ in every] == ["c0", "c1", "c2"]
    right, _ = jd6.paired_states(a, b, cells, only="right")
    wrong, _ = jd6.paired_states(a, b, cells, only="wrong")
    assert [c for c, _, _ in right] == ["c0", "c1"]
    assert [c for c, _, _ in wrong] == ["c2"]
    assert right + wrong == [p for p in every]

    # and a cell the two arms disagree about M0 on is DROPPED and counted, not paired:
    # it would mean they are not standing on the same decision
    b["c0"] = {**b["c0"], "source_correct": False}
    _, disagreed = jd6.paired_states(a, b, cells)
    assert disagreed == 1


def test_jd6_runs_on_missing_indexes_and_says_not_run(capsys, jd6):
    """It is written before either arm exists and has to be runnable then — that is how a
    derivation gets reviewed before it can be tuned to the numbers it will produce."""
    _JD6_FLAGS.clear()
    _JD6_FLAGS.update(jd6.ARM_FLAGS)
    assert jd6.main(_jd6_only()) == 0
    out = capsys.readouterr().out
    assert "NOT RUN" in out
    assert "NOTHING TO DERIVE" in out
    assert "is not an error" in out


def test_jd6_names_its_endpoint_and_labels_everything_else(jd6):
    """jd5's lesson, written into the file: the four outcomes are named BEFORE the table
    so no rule is invented after it, the net is demoted to an ablation, and the
    jd5-B comparison carries the provider caveat that makes it descriptive."""
    source = (DERIVATIONS / "judgment-debate-6.py").read_text(encoding="utf-8")
    assert "[PRIMARY]" in source
    assert "[ABLATION — NOT AN ENDPOINT]" in source
    assert "[KEYWORD INSTRUMENT — NOT A MEASUREMENT]" in source
    assert "THE PROVIDER CAVEAT" in source
    for outcome in ("(A) P1 and P2 hold", "(B) R breaks fewer", "(C) B beats R on both",
                    "(D) no separation"):
        assert outcome in source, outcome
    # the caveat the pre-registration requires to travel with every absolute rate
    assert "RE-DRAW DISAGREEMENT WITH" in source


def test_jd6_is_stdlib_only_like_every_other_derivation(jd6):
    source = (DERIVATIONS / "judgment-debate-6.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned


def test_jd6_counts_the_glued_argument_label_and_the_truncations(tmp_path, jd6):
    """Section (6)'s two FORMAT instruments, and the reason each is a count over turns.

    THE GLUED LABEL: `parse_debater_output` takes the last `Argument:` at a LINE START, so
    a model that writes the label mid-sentence after some planning text publishes the
    planning text as part of its public argument. The parser cannot catch it and a reader
    of the record can see it, so what the write-up needs is not the rate but whether the
    contest round RAISED it — hence the same count over the PARENT rounds of the same
    cells, read out of each arm's own copy of them so nothing opens `jd3-main`.

    THE TRUNCATIONS: `finish_reason == "length"` is the cell-loss mechanism, and it is the
    sweep's own (a restart loop in the private Thinking block), not a new one.
    """
    assert jd6.glued_argument_label("plan first.  Argument: the real one") is True
    assert jd6.glued_argument_label("no label at all here") is False
    assert jd6.glued_argument_label("") is False
    assert jd6.glued_argument_label(None) is False

    flags = jd6.turn_flags({"argument": "x Argument: y", "finish_reason": "length",
                            "word_count": 12, "parse_mode": "strict",
                            "repair_attempts": 1})
    assert flags == {"glued_label": True, "finish_reason": "length", "truncated": True,
                     "words": 12, "parse_mode": "strict", "repairs": 1}

    # the parent count is over the rounds the stored debate already had, and `boundary`
    # is what keeps the added round out of it
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps({"turns": [
        {"round": 1, "argument": "clean"},
        {"round": 2, "argument": "plan.  Argument: real"},
        {"round": 3, "argument": "clean"},
        {"round": 4, "argument": "also Argument: glued"},
    ]}), encoding="utf-8")
    assert jd6.parent_glued(path, 3) == (3, 1)
    assert jd6.parent_glued(path) == (4, 2)
    assert jd6.parent_glued(tmp_path / "missing.json") == (0, 0)


def test_jd6_scans_arm_b_off_one_transcript_and_skips_the_cells_it_lost(tmp_path, jd6):
    """Arm B keeps the parent rounds and the added round in ONE `transcript.json`, told
    apart by `extended_from_rounds`; and a cell whose round-4 turn truncated has no
    `verdict.json`, so it never reaches the scan — which is why the truncation count in
    section (6) is over SURVIVING turns and the section says so."""
    def cell(name, *, rounds, boundary, verdict=True, glue=()):
        directory = tmp_path / "cells" / name / "runs" / "r0"
        directory.mkdir(parents=True)
        (directory / "transcript.json").write_text(json.dumps({"turns": [
            {"round": r, "argument": ("a Argument: b" if r in glue else "clean"),
             "finish_reason": "stop", "word_count": 3, "parse_mode": "strict",
             "repair_attempts": 0}
            for r in rounds]}), encoding="utf-8")
        (directory / "run.json").write_text(
            json.dumps({"extended_from_rounds": boundary, "rounds_n": 4}),
            encoding="utf-8")
        if verdict:
            (directory / "verdict.json").write_text("{}", encoding="utf-8")

    cell("ok", rounds=[1, 2, 3, 4], boundary=3, glue={2, 4})
    # a cell whose round-4 turn truncated: the completed turn was committed, so its
    # transcript reaches round 4, and the run holds no verdict
    cell("lost", rounds=[1, 2, 3, 4], boundary=3, verdict=False)
    rows = {r["cell_id"]: r for r in jd6.scan_plain_tree(tmp_path)}
    assert set(rows) == {"ok"}
    assert rows["ok"] == {"cell_id": "ok", "extended_from_rounds": 3, "turns_n": 1,
                          "parent_turns_n": 3, "parent_glued_n": 1, "glued_n": 1,
                          "truncated_n": 0}


def test_jd6_splits_the_round_4_instruments_by_stance(tmp_path, jd6):
    """PRO and ANTI are different tasks with different amounts to say, and a systematic
    difference between them is a difference in what the judge reads on each side of the
    objection. Smoke 1's two heavy word overruns were BOTH PRO turns and smoke 2's longest
    turn (726 words, a whole argument written twice around a glued label) was PRO too, so
    the split is pre-registered rather than looked at afterwards.

    The scan is walked by `run.json` and not by `ruling.json` on purpose: a cell whose
    round-4 turn truncated has no ruling but DOES have the turn that completed, and a
    truncation instrument that could not see a truncated cell would read 0 on every one.
    """
    def contest(name, *, ruled=True, turns=(("Alice", "pro"), ("Bob", "anti"))):
        directory = (tmp_path / "cells" / name / "contests" / "c" / "runs" / "r0")
        (directory / "parent").mkdir(parents=True)
        (directory / "run.json").write_text(json.dumps({"cell_id": name}),
                                            encoding="utf-8")
        (directory / "sides.json").write_text(
            json.dumps({"alice_side": "FLAWED", "bob_side": "SOUND"}), encoding="utf-8")
        (directory / "parent" / "verdict.json").write_text(
            json.dumps({"verdict": "SOUND"}), encoding="utf-8")   # -> Alice is PRO
        (directory / "recourse_transcript.json").write_text(json.dumps({"turns": [
            {"round": 4, "speaker": speaker,
             "argument": ("long " * 500 if stance == "pro" else "short one"),
             "finish_reason": "stop", "word_count": 500 if stance == "pro" else 2,
             "parse_mode": "strict", "repair_attempts": 0}
            for speaker, stance in turns]}), encoding="utf-8")
        if ruled:
            (directory / "ruling.json").write_text(json.dumps({
                "recourse_rounds": 1, "recourse_pro_speaker": "Alice",
                "raw": "the ruling"}), encoding="utf-8")

    contest("ok")
    # a cell whose second turn was lost: no ruling, one committed turn
    contest("lost", ruled=False, turns=(("Bob", "anti"),))
    rows = {r["cell_id"]: r for r in jd6.scan_round_tree(tmp_path)}

    assert set(rows) == {"ok", "lost"}, "a failed cell must still be scanned"
    assert rows["ok"]["pro_words"] == 500 and rows["ok"]["anti_words"] == 2
    assert rows["ok"]["pro_over_limit"] is True
    assert rows["ok"]["anti_over_limit"] is False
    assert rows["ok"]["ruled"] is True
    # the lost cell has no ruling, so its PRO speaker is DERIVED from the seating and the
    # parent verdict — the decision went SOUND, which is Bob's side, so Alice argues PRO
    assert rows["lost"]["ruled"] is False
    assert rows["lost"]["pro_speaker"] == "Alice"
    assert rows["lost"]["turns_n"] == 1
    assert "anti_words" in rows["lost"] and "pro_words" not in rows["lost"]


def test_jd6_flags_a_ruling_that_adopts_one_reply_without_answering_the_other(jd6):
    """The failure mode both smokes produced and neither keyword caught.

    On `lojban-stim169` (smoke 1) and `python800-p03214` (smoke 2) the ruling reproduced
    the PRO reply's structure and phrases and never engaged ANTI's counter — and in the
    second it named no debater at all, so `CITES_EXCHANGE` scored it as not citing the
    exchange while it was reciting one half of it. A judge that adopts one advocate is the
    weak-vs-strong failure this arm exists to detect.

    It is lexical and it CANNOT tell adoption from agreement, which is why it is labelled
    as directing a hand read; what is asserted here is only that it separates a ruling
    that tracks one reply from one that tracks both.
    """
    pro = ("the judgment mischaracterises the record and the defect is real and material "
           "because the text makes a positive unconditional claim")
    anti = ("the label is a loose summary and the holding does not depend on it so the "
            "defect is immaterial and the decision stands")

    assert jd6.overlap(pro, pro) == 1.0
    assert jd6.overlap("", pro) == 0.0
    assert jd6.overlap(pro, "") == 0.0

    # a ruling that recites PRO and never answers ANTI
    one = "PREAMBLE. " + pro + " CONCLUSION."
    assert jd6.overlap(one, pro) > jd6.overlap(one, anti)
    assert jd6.one_sided(jd6.overlap(one, pro), jd6.overlap(one, anti)) is True

    # a ruling that engages both is not flagged
    both = "PREAMBLE. " + pro + " However, " + anti + " CONCLUSION."
    assert jd6.one_sided(jd6.overlap(both, pro), jd6.overlap(both, anti)) is False

    # and the floor keeps two near-zero overlaps from being called one-sided
    assert jd6.one_sided(0.001, 0.0) is False
    assert jd6.one_sided(0.0, 0.0) is False


def test_jd6_reports_the_primary_table_in_the_words_of_two_after_states(capsys, jd6):
    """Section (1) pairs two AFTER-states, so jd4's before/after vocabulary is wrong in it.

    `jd4.paired_block` calls its discordant cells "fixed" and "broken" and prints their
    difference as a NET, which is right for a BEFORE against an AFTER and wrong for R's
    ruling against B's judgment: "fixed" would name a cell one arm got right and the other
    did not, which is nobody's fix, and the NET would be the margin between two arms rather
    than a gain over M0. On the real run that mislabelled net read +114 on the very table
    whose finding is that R breaks 176 where B breaks 62 — the opposite sign to the result.
    Same counts, same exact test, correct words.
    """
    # 3 cells R broke alone, 1 B broke alone, 1 both, 2 neither
    pairs = ([(f"a{i}", False, True) for i in range(3)]
             + [("b0", True, False)]
             + [("c0", False, False)]
             + [(f"d{i}", True, True) for i in range(2)])
    out = jd6.paired_after_block(pairs, "right")
    printed = capsys.readouterr().out
    assert out["r_only"] == 3 and out["b_only"] == 1
    assert out["n"] == 7 and out["r_right"] == 3 and out["b_right"] == 5
    assert "broken by R ALONE   (R wrong, B right)   3" in printed
    assert "broken by B ALONE   (R right, B wrong)   1" in printed
    assert "P1 asks whether the FIRST is smaller than the second. 3 vs 1." in printed
    # the two words that must NOT appear on a table of two after-states
    assert "NET" not in printed.replace("there is no NET", "")
    assert "fixed" not in printed

    # and on the wrong cells the same 2x2 is read the other way round
    out2 = jd6.paired_after_block(pairs, "wrong")
    printed2 = capsys.readouterr().out
    assert out2["r_only"] == 1 and out2["b_only"] == 3
    assert "fixed by R ALONE    (R right, B wrong)   1" in printed2
    assert "P2 asks whether the FIRST is at least the second. 1 vs 3." in printed2
    assert "broken" not in printed2
    # the exact test does not depend on which way the table is read
    assert out["p"] == out2["p"] == jd6.mcnemar_exact(1, 3)


# --- findings-1: the decomposed judgment, and the local contest -------------------------


@pytest.fixture(scope="module")
def fd1():
    return _load("findings-1.py")


_FD1_FLAGS: dict = {}


def _fd1_only(*args):
    """Arguments that run ONLY the indexes named.

    Same reason as `_jd5_only` and `_jd6_only`, and it matters more here: two of this
    script's four defaults (`--m0`, `--jd5b`) point at COMMITTED indexes that DO exist, so
    without this a synthetic assertion about twenty fake cells would quietly be joined
    against jd3's 1,644 real ones.
    """
    named = set(args[::2])
    argv = []
    for _key, (flag, _default) in _FD1_FLAGS.items():
        if flag not in named:
            argv += [flag, "/nonexistent/index.jsonl"]
    return list(args) + argv


def _fd1_row(cell, *, before, after=None, subset="theoremqa",
             label_basis="injected_pair", verdict="SOUND", **kw):
    """One fd1 index row. Every fd1 arm is a REJUDGE, so `initially_correct` is the
    findings judge's OWN derived verdict and `final_correct` is the state after recourse —
    absent where nothing was ruled, which is the rule `after_of` implements."""
    row = {"cell_id": cell, "item_id": cell.split("__")[0], "row_id": cell,
           "subset": subset, "label_basis": label_basis, "condition": "debate",
           "gold_flawed": verdict == "FLAWED", "verdict": verdict,
           "judge_form": "findings", "findings_parse_mode": "strict",
           "findings_n": 2, "findings_flaw_n": 1 if verdict == "FLAWED" else 0,
           "initially_correct": before, "initially_incorrect": not before}
    if after is not None:
        row.update({"challenge_arm": "findings", "challenge_stance": "contests",
                    "challenge_raised": True, "challenge_contests_n": 1,
                    "challenge_contests_finding_n": 1, "challenge_contests_omission_n": 0,
                    "challenge_contests_contradiction_n": 0,
                    "challenge_contests_void_n": 0, "challenge_void_only": False,
                    "challenge_seeks_reversal": True, "phantom_contest": False,
                    "comprehension": 4, "ruling_form": "derived_findings",
                    "ruling_prompt_form": "findings", "ruling_prose_empty": False,
                    "ruling_line_mismatch": False, "ruling_leadin_stripped": False,
                    "findings_after_n": 2, "findings_after_flaw_n": 1,
                    "findings_added_n": 0,
                    "changed_the_decision": before != after, "final_correct": after,
                    "grade_mode": "findings", "grade_valid": True,
                    "grade_contests_n": 1, "grade_contests_valid_n": 1,
                    "grade_contests_mechanical_n": 0, "grade_line_mismatch": False})
    row.update(kw)
    return row


def _fd1_jd5b_row(cell, *, before, after):
    """A jd5-B row: a RERULE, so `initially_correct` is M0's and `final_correct` the
    ruling's. Its contested set is its own, never fd1's."""
    return {"cell_id": cell, "item_id": cell, "row_id": cell, "subset": "theoremqa",
            "label_basis": "injected_pair", "condition": "debate", "gold_flawed": True,
            "verdict": "SOUND", "initially_correct": before,
            "initially_incorrect": not before, "challenge_stance": "contests",
            "challenge_raised": True, "ruling_form": "stated_conclusion",
            "ruling_prompt_form": "materiality",
            "changed_the_decision": before != after, "final_correct": after}


def _fd1_fixture(tmp_path: Path):
    """A four-index fixture with a KNOWN P1 and a KNOWN P2.

    F-weak: 20 cells right before, 1 of them broken; 10 wrong before, 6 of them fixed.
        P1 -> McNemar(6, 1) = 0.125, a NULL with a positive net.
        P2 -> Fisher one-sided on [[1, 19], [20, 40]] = 0.00909, which HOLDS.
    That combination is PREREG §4's outcome (B) — the break side moved and the endpoint
    did not — and it is chosen here because it is the one that a careless reader would
    round to (A) or to (D).

    F-strong is deliberately flat (nothing moves) so the two arms' readings differ and the
    cross-arm disagreement line has something to say.
    """
    weak, strong, m0, jd5b = [], [], [], []
    for i in range(20):
        weak.append(_fd1_row(f"w{i:02d}__debate__r1", before=True,
                             after=(i != 0)))
    for i in range(10):
        weak.append(_fd1_row(f"x{i:02d}__debate__r1", before=False,
                             after=(i < 6), verdict="FLAWED"))
    for i in range(30):
        strong.append(_fd1_row(f"{'w' if i < 20 else 'x'}{i % 20:02d}__debate__r1",
                               before=i < 20, after=i < 20))
    for row in weak:
        m0.append({"cell_id": row["cell_id"], "item_id": row["item_id"],
                   "row_id": row["cell_id"], "subset": row["subset"],
                   "label_basis": row["label_basis"], "condition": "debate",
                   "gold_flawed": True, "verdict": "SOUND",
                   "initially_correct": True, "initially_incorrect": False,
                   "challenge_raised": True})
    for i in range(60):
        jd5b.append(_fd1_jd5b_row(f"j{i:02d}__debate__r1", before=True, after=i >= 20))
    for i in range(20):
        jd5b.append(_fd1_jd5b_row(f"k{i:02d}__debate__r1", before=False, after=i < 10))

    paths = {}
    for name, rows in (("weak", weak), ("strong", strong), ("m0", m0), ("jd5b", jd5b)):
        paths[name] = tmp_path / f"{name}.jsonl"
        _write(paths[name], rows)
    return paths


def _fd1_argv(paths, *extra):
    return _fd1_only("--weak", str(paths["weak"]), "--strong", str(paths["strong"]),
                     "--m0", str(paths["m0"]), "--jd5b", str(paths["jd5b"]), *extra)


def test_fd1_imports_its_statistics_rather_than_copying_them(jd4, jd5, jd6, fd1):
    """`findings-1.py` prints `fixed | wrong` and `broken | right` BESIDE jd5-B's, in one
    write-up, on populations that overlap cell for cell. A definition that drifted between
    the two files would be invisible, so it re-exports jd6's objects — which are jd5's,
    which are jd4's — and this asserts IDENTITY, not equality of results."""
    _FD1_FLAGS.clear()
    _FD1_FLAGS.update(fd1.ARM_FLAGS)
    assert fd1.mcnemar_exact is fd1.jd6.mcnemar_exact
    assert fd1.wilson is fd1.jd6.wilson
    assert fd1.paired_block is fd1.jd6.paired_block
    assert fd1.load is fd1.jd6.load
    assert fd1.restrict is fd1.jd6.restrict
    assert fd1.conditional_rates is fd1.jd6.jd5.conditional_rates
    assert fd1.jd6.jd5.jd4.__file__ == jd4.__file__, "the same file, one chain up"
    assert fd1.ALPHA == jd6.ALPHA == jd5.ALPHA == jd4.ALPHA == 0.05
    for b, c in ((0, 0), (1, 0), (3, 10), (7, 7)):
        assert fd1.mcnemar_exact(b, c) == jd4.mcnemar_exact(b, c)


def test_fd1_fisher_one_sided_matches_the_hand_computation(fd1):
    """The 2x2 `[[3, 7], [6, 4]]`. Conditioning on both margins, the count in the top-left
    cell is Hypergeometric(n=20, K=9, N=10) and the LOWER tail is

        P(X <= 3) = [ C(10,0)C(10,9) + C(10,1)C(10,8) + C(10,2)C(10,7) + C(10,3)C(10,6) ]
                    / C(20,9)
                  = [ 1*10 + 10*45 + 45*120 + 120*210 ] / 167960
                  = [ 10 + 450 + 5400 + 25200 ] / 167960
                  = 31060 / 167960
                  = 0.1849249821386...

    Written out here rather than delegated to the function under test, which is the whole
    point of the check. There is NO scipy in this repo and this is the arithmetic that
    would otherwise be taken on trust.
    """
    assert fd1.fisher_one_sided(3, 7, 6, 4) == pytest.approx(31060 / 167960)
    assert fd1.fisher_one_sided(3, 7, 6, 4) == pytest.approx(0.18492498213860442,
                                                             abs=1e-12)
    # the two tails OVERLAP at k = a (both include it), so they sum to more than 1 — which
    # is what makes this a one-sided test and not half of a two-sided one
    upper = fd1.fisher_one_sided(3, 7, 6, 4, alternative="greater")
    assert upper == pytest.approx(0.9651107406525363, abs=1e-12)
    assert upper + fd1.fisher_one_sided(3, 7, 6, 4) > 1.0
    # a table with no signal at all: the lower tail cannot be small
    assert fd1.fisher_one_sided(5, 5, 5, 5) > 0.5
    # and the direction is the one P2 asks about: fewer in the top-left is a SMALLER p
    assert fd1.fisher_one_sided(1, 9, 6, 4) < fd1.fisher_one_sided(3, 7, 6, 4)


def test_fd1_fisher_refuses_what_it_cannot_compute(fd1):
    with pytest.raises(ValueError):
        fd1.fisher_one_sided(-1, 1, 1, 1)
    with pytest.raises(ValueError):
        fd1.fisher_one_sided(1, 1, 1, 1, alternative="two-sided")
    # an empty table is 1.0 and not a crash: an arm with no before-RIGHT cells has to
    # print NOT RUN, not raise inside a table
    assert fd1.fisher_one_sided(0, 0, 0, 0) == 1.0


def test_fd1_newcombe_matches_the_hand_computation(fd1):
    """Newcombe's method 10 on 56/70 against 48/80, worked through by hand.

        p1 = 0.8   Wilson [0.691830, 0.876952]
        p2 = 0.6   Wilson [0.490453, 0.700383]
        d  = 0.2
        lower = 0.2 - sqrt((0.8 - 0.691830)^2 + (0.700383 - 0.6)^2) = 0.052429
        upper = 0.2 + sqrt((0.876952 - 0.8)^2 + (0.6 - 0.490453)^2) = 0.333875

    The interval is asymmetric about the difference, which is the whole reason it is used
    instead of a Wald interval: at the small counts P2's second denominator can reach, a
    Wald interval runs off the end of [-1, 1] and its coverage collapses.
    """
    low, high = fd1.newcombe_diff(56, 70, 48, 80)
    assert low == pytest.approx(0.0524287, abs=1e-6)
    assert high == pytest.approx(0.3338749, abs=1e-6)
    assert high - 0.2 != pytest.approx(0.2 - low, abs=1e-3), "it is not symmetric"

    # it is built out of the SAME Wilson every other rate in the campaign is printed with
    l1, u1 = fd1.wilson(56, 70)
    l2, u2 = fd1.wilson(48, 80)
    assert low == pytest.approx(0.8 - 0.6 - math.sqrt((0.8 - l1) ** 2 + (u2 - 0.6) ** 2))
    assert high == pytest.approx(0.8 - 0.6 + math.sqrt((u1 - 0.8) ** 2 + (0.6 - l2) ** 2))

    # equal rates put 0 inside, and the interval is clamped to [-1, 1]
    low, high = fd1.newcombe_diff(10, 20, 10, 20)
    assert low < 0 < high
    assert fd1.newcombe_diff(0, 1, 1, 1)[0] >= -1.0
    assert fd1.newcombe_diff(1, 1, 0, 1)[1] <= 1.0


def test_fd1_reads_the_before_and_after_states_out_of_the_right_columns(fd1):
    """EVERY fd1 ARM IS A REJUDGE, which is what makes this file's accessors simpler than
    jd6's and no less load-bearing: `initially_correct` is the FINDINGS JUDGE's own derived
    verdict, `final_correct` is the state after recourse, and `source_correct` — jd3-M0's
    decision — is never read here. M0 comes from its OWN index, where `initially_correct`
    is M0's decision and `final_correct` is what jd3's M1 audit did to it.
    """
    row = {"initially_correct": True, "final_correct": False,
           "source_correct": False, "ruling_form": "derived_findings"}
    assert fd1.before_of(row) is True
    assert fd1.after_of(row) is False
    assert fd1.was_ruled(row) is True

    # a cell nobody ruled on keeps the decision it had, and is not "ruled"
    assert fd1.after_of({"initially_correct": True, "final_correct": None}) is True
    assert fd1.was_ruled({"initially_correct": True}) is False

    # M0's own index: the DECISION, never the audited state
    m0 = {"verdict": "SOUND", "initially_correct": True, "final_correct": False}
    assert fd1.m0_of(m0) is True
    assert fd1.m0_verdict_of(m0) == "SOUND"


def test_fd1_void_only_is_the_second_denominator_and_has_a_fallback(fd1):
    """PREREG §2's second denominator. An objection made ENTIRELY of mechanically void
    contests cannot break anything by construction — `apply_contest_lines` ignores its
    ruling lines — so the break rate is reported over both denominators and neither can be
    chosen after the table.

    `challenge_void_only` is the column, added 2026-09-02; an index written before it
    existed carries the same fact in two counts, and the fallback is asserted here because
    the smoke indexes on disk are exactly such indexes.
    """
    assert fd1.void_only({"challenge_void_only": True}) is True
    assert fd1.void_only({"challenge_void_only": False}) is False
    # the fallback, off the two counts
    assert fd1.void_only({"challenge_contests_n": 2, "challenge_contests_void_n": 2}) is True
    assert fd1.void_only({"challenge_contests_n": 2, "challenge_contests_void_n": 1}) is False
    assert fd1.void_only({"challenge_contests_n": 0, "challenge_contests_void_n": 0}) is False
    # no list at all is a DIFFERENT fact from "all of them were void"
    assert fd1.void_only({}) is None

    contested = {"challenge_raised": True}
    assert fd1.well_formed({**contested, "challenge_void_only": False}) is True
    assert fd1.well_formed({**contested, "challenge_void_only": True}) is False
    assert fd1.well_formed({**contested}) is True, "unknown is not void"
    assert fd1.well_formed({"challenge_raised": False}) is False


def test_fd1_arm_rates_agree_with_the_shared_conditional_rates(fd1, tmp_path):
    """`arm_rates` is `jd4.conditional_rates` with a filter, and it must stay that way:
    these two numbers are printed side by side with jd5-B's in one table."""
    rows = {f"c{i}": _fd1_row(f"c{i}", before=i < 6, after=(i in (0, 6, 7)))
            for i in range(10)}
    mine = fd1.arm_rates(rows)
    theirs = fd1.conditional_rates(rows)
    for key in ("fixed", "n_wrong", "broken", "n_right"):
        assert mine[key] == theirs[key], key
    assert mine["n"] == theirs["n"]

    # and the filter is what makes one function serve all three denominators
    only_one = fd1.arm_rates(rows, only=lambda r: r["cell_id"] == "c0")
    assert only_one["n"] == 1 and only_one["n_right"] == 1


def test_fd1_the_comparator_is_recomputed_and_asserted_in_one_place(fd1):
    """PREREG §0's comparator, recomputed from the COMMITTED jd5-B index rather than typed
    in — and then asserted, so a drift is loud. 167/622 = 26.8% and 144/274 = 52.6% are
    what §3ac's table, jd5's CHECKLIST and this campaign's PREREG all quote."""
    rows = fd1.load(DERIVATIONS.parent.parent / "records" / "experiments" /
                    "judgment-debate-5" / "arm-real" / "index.jsonl")
    assert len(rows) == 1644
    cells = {c for c, r in rows.items() if fd1.contested(r)}
    assert len(cells) == 896
    stats = fd1.jd5b_rates(rows, cells)
    assert stats == {"fixed": 144, "n_wrong": 274, "broken": 167, "n_right": 622,
                     "n": 896}
    assert fd1.JD5B_EXPECTED == {"broken": 167, "n_right": 622, "fixed": 144,
                                 "n_wrong": 274}
    note = fd1.check_jd5b(stats, len(rows))
    assert "matches the published" in note

    # a drift is an ERROR and not a footnote
    with pytest.raises(AssertionError) as caught:
        fd1.check_jd5b({**stats, "broken": 168}, len(rows))
    assert "DRIFTED" in str(caught.value)

    # a fixture or a slice SKIPS the assertion, loudly, rather than failing
    skipped = fd1.check_jd5b({"broken": 1, "n_right": 2, "fixed": 1, "n_wrong": 2}, 12)
    assert "SKIPPED" in skipped


def test_fd1_the_identity_row_is_the_one_from_LLM_NOTES(fd1):
    """§3ac: recourse does not lower accuracy iff `f / b >= a / (1 - a)`, and the
    break-even accuracy is `a* = f / (f + b)` where f and b are RATES.

    jd5-B's published row is f 52.6%, b 26.8%, f/b 1.96, a* 66%, on cells whose accuracy
    is 622/896 = 69%. That row is reproduced here from the counts, because the one way to
    get this table wrong is to put COUNTS where the identity wants rates.
    """
    row = fd1.identity_row({"fixed": 144, "n_wrong": 274, "broken": 167, "n_right": 622,
                            "n": 896})
    assert row["n"] == 896
    assert row["a"] == pytest.approx(622 / 896, abs=1e-6)
    assert row["f"] == pytest.approx(0.5255, abs=1e-3)
    assert row["b"] == pytest.approx(0.2685, abs=1e-3)
    assert row["f_over_b"] == pytest.approx(1.96, abs=0.01)
    assert row["a_star"] == pytest.approx(0.662, abs=0.01)
    assert row["net"] == 144 - 167 == -23
    # the mechanism hurts because a (69%) sits ABOVE its own break-even (66%)
    assert row["a"] > row["a_star"]
    assert row["f_over_b"] < row["odds"]

    # an empty denominator is n/a and never a crash or a zero
    empty = fd1.identity_row({"fixed": 0, "n_wrong": 0, "broken": 0, "n_right": 0, "n": 0})
    assert empty["a"] is None and empty["f"] is None and empty["b"] is None


def test_fd1_names_the_outcome_by_prereg_rule_and_never_rounds(fd1):
    """PREREG §4's four names, and the rule that governs all four.

    "POSITIVE" is a SIGNIFICANT gain and not a positive net: an arm that fixes three more
    than it breaks at p = 0.6 has shown nothing, and calling that positive is exactly the
    rounding §4's last sentence forbids.
    """
    assert fd1.p1_reading(+9, 0.01) == "POSITIVE"
    assert fd1.p1_reading(-9, 0.01) == "NEGATIVE"
    assert fd1.p1_reading(+9, 0.60) == "NULL"
    assert fd1.p1_reading(+9, 0.05) == "NULL", "alpha is a strict inequality"
    assert fd1.p1_reading(0, 1.0) == "NULL"

    assert fd1.named_outcome("POSITIVE", True)[0] == "(A)"
    assert fd1.named_outcome("NULL", True)[0] == "(B)"
    assert fd1.named_outcome("NEGATIVE", True)[0] == "(B)"
    assert fd1.named_outcome("POSITIVE", False)[0] == "(C)"
    assert fd1.named_outcome("NULL", False)[0] == "(D)"
    assert fd1.named_outcome("NEGATIVE", False)[0] == "(D)"
    # before the arm has run there is no outcome, and that is not an error
    assert fd1.named_outcome("NULL", None)[0] == "(not computable)"

    source = (DERIVATIONS / "findings-1.py").read_text(encoding="utf-8")
    assert "SPLITS ARE REPORTED AS SPLITS" in source
    assert "[PRIMARY]" in source and "[CO-PRIMARY]" in source
    assert "[ABLATION — NOT AN ENDPOINT]" in source
    assert "[REPORTED, NOT TESTED]" in source
    assert "UNPAIRED" in source


def test_fd1_runs_end_to_end_and_prints_every_section(tmp_path, capsys, fd1):
    """The whole file over a synthetic pair of arms with a KNOWN P1 and a KNOWN P2.

    F-weak breaks 1 of 20 right cells and fixes 6 of 10 wrong ones, so P1 is
    McNemar(6, 1) = 0.125 — a NULL with a positive net — and P2 is Fisher one-sided on
    [[1, 19], [20, 40]] = 0.00909, which HOLDS. That is PREREG §4's outcome (B), the one a
    careless reader would round to (A) or to (D), and the assertion is that the file names
    it (B) and says why.
    """
    _FD1_FLAGS.clear()
    _FD1_FLAGS.update(fd1.ARM_FLAGS)
    paths = _fd1_fixture(tmp_path)
    assert fd1.main(_fd1_argv(paths)) == 0
    out = capsys.readouterr().out

    for header in ("(0) THE LOSSES, THE PARSE AND THE FORMAT",
                   "(1) P1 — DOES RECOURSE ON A DECOMPOSED JUDGMENT RAISE ACCURACY?",
                   "(2) P2 — DOES THE LOCAL CONTEST BREAK FEWER RIGHT DECISIONS?",
                   "THE PAIRED 2x2 ON THE INTERSECTION",
                   "(3) P3 — THE FIX SIDE",
                   "(4) RECORDED, NOT TESTED",
                   "(4a) THE FINDINGS JUDGE AGAINST jd3-M0",
                   "(4b) ACCURACY AFTER RECOURSE AGAINST M0",
                   "(4c) §3ac's IDENTITY, PER MECHANISM",
                   "(4d) THE TWO RATES SPLIT BY BEFORE-VERDICT",
                   "(4e) THE OBJECTION ITSELF",
                   "(4f) VALIDITY, BY KIND AND BY `label_basis`",
                   "(4g) THE RULING",
                   "(5) THE PRE-REGISTERED READING"):
        assert header in out, header

    # P1: the 2x2 and the exact p, as `paired_block` prints them
    assert "b = 6" in out and "c = 1" in out
    assert "NET                                    +5 cells" in out
    assert f"p = {0.125:.6g}" in out
    # P2: the Fisher p, both denominators, and the Newcombe interval beside it
    assert f"p = {0.00909041037682113:.6g}" in out
    assert "P2 HOLDS" in out
    assert out.count("DENOMINATOR:") == 2
    assert "Newcombe 95%" in out
    # the comparator is a fixture here, so the published-number assertion is SKIPPED
    assert "SKIPPED" in out
    # and the outcome is named, not rounded
    assert "NAMED OUTCOME FOR F-WEAK: (B)" in out
    assert "SPLITS ARE REPORTED AS SPLITS" in out
    # the two arms read differently, and that is reported rather than resolved
    assert "P1 is NULL" in out


def test_fd1_prints_the_direction_table_and_says_when_it_cannot(tmp_path, capsys, fd1):
    """R12e. The two directions of a finding contest are graded against DIFFERENT bounds
    (PREREG §5a), so the mix has to be visible or the validity rate above it cannot be
    read. And a tree written before the columns existed gets a note, never a zero — the
    rule this whole file follows: a missing measurement is said out loud.

    `flaw_location_missing` is here for the same reason. A finding contest on a flawed
    item is graded by asking whether the finding IS the annotated flaw; where the
    annotation records no location, that question is answered from prose alone.
    """
    _FD1_FLAGS.clear()
    _FD1_FLAGS.update(fd1.ARM_FLAGS)
    paths = _fd1_fixture(tmp_path)

    # 1. WITHOUT the columns — the fixture's own rows, which predate them
    assert fd1.main(_fd1_argv(paths)) == 0
    out = capsys.readouterr().out
    assert "DIRECTION of the finding contests: NOT IN THE INDEX" in out
    assert "record quote unverified: NOT IN THE INDEX" in out
    assert "annotation with NO location: NOT IN THE INDEX" in out

    # 2. WITH them
    for arm in ("weak", "strong"):
        rows = [json.loads(line) for line in paths[arm].read_text().splitlines()]
        for i, row in enumerate(rows):
            if row.get("challenge_contests_n") is None:
                continue
            to_flaw = i % 2 == 0
            row["challenge_contests_to_flaw_n"] = 1 if to_flaw else 0
            row["challenge_contests_to_not_a_flaw_n"] = 0 if to_flaw else 1
            row["challenge_contests_record_unverified_n"] = 1 if i % 5 == 0 else 0
            row["flaw_location_missing"] = i % 3 == 0
        _write(paths[arm], rows)

    assert fd1.main(_fd1_argv(paths)) == 0
    out = capsys.readouterr().out
    assert "DIRECTION of the finding contests" in out
    assert "NOT A FLAW -> FLAW" in out and "FLAW -> NOT A FLAW" in out
    assert "validity is a LOWER bound (§5a)" in out
    assert "validity is an UPPER bound (§5a)" in out
    assert "record quote unverified" in out and "RECORDED, not voiding" in out
    assert "annotation with NO location" in out
    objection_block = out.split("(4e) THE OBJECTION ITSELF")[1].split("(4f)")[0]
    assert "NOT IN THE INDEX" not in objection_block


def test_fd1_the_two_denominators_are_both_printed_and_differ(tmp_path, capsys, fd1):
    """A void-only objection cannot break anything by construction, so it belongs in one
    denominator and not the other. Both are printed, ALWAYS, because dropping the void
    cells silently makes the mechanism look worse and keeping them silently makes it look
    safer."""
    _FD1_FLAGS.clear()
    _FD1_FLAGS.update(fd1.ARM_FLAGS)
    paths = _fd1_fixture(tmp_path)
    # turn ten of F-weak's right cells into void-only objections that broke nothing
    rows = [json.loads(line) for line in paths["weak"].read_text().splitlines()]
    for row in rows:
        if row["cell_id"].startswith("w") and row["cell_id"] < "w10__":
            row["challenge_void_only"] = True
            row["challenge_contests_void_n"] = row["challenge_contests_n"]
    _write(paths["weak"], rows)

    assert fd1.main(_fd1_argv(paths)) == 0
    out = capsys.readouterr().out
    section = out.split("(2) P2 —")[1].split("THE PAIRED 2x2")[0]
    blocks = section.split("DENOMINATOR:")
    assert len(blocks) == 3
    # the first denominator keeps all 20 right cells, the second only the 10 well-formed
    assert "        20" in blocks[1]
    assert "        10" in blocks[2]


def test_fd1_runs_on_missing_indexes_and_says_not_run(capsys, fd1):
    """It is written before either arm exists and has to be runnable then — that is how a
    derivation gets reviewed before it can be tuned to the numbers it will produce."""
    _FD1_FLAGS.clear()
    _FD1_FLAGS.update(fd1.ARM_FLAGS)
    assert fd1.main(_fd1_only()) == 0
    out = capsys.readouterr().out
    assert "NOT RUN" in out
    assert "NOTHING TO DERIVE" in out
    assert "is not an error" in out


def test_fd1_is_stdlib_only_like_every_other_derivation(fd1):
    source = (DERIVATIONS / "findings-1.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas",
                   "from scipy", "import statsmodels", "from exp2"):
        assert banned not in source, banned


def test_fd1_the_defaults_name_the_committed_indexes(fd1):
    """Two of the four defaults are committed files that DO exist, which is why every
    synthetic test in this module overrides all four."""
    assert fd1.ARM_FLAGS["m0"][1] == (
        "records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl")
    assert fd1.ARM_FLAGS["jd5b"][1] == (
        "records/experiments/judgment-debate-5/arm-real/index.jsonl")
    for key in ("m0", "jd5b"):
        assert (DERIVATIONS.parent.parent / fd1.ARM_FLAGS[key][1]).is_file(), key
    for key in ("weak", "strong"):
        assert fd1.ARM_FLAGS[key][1].startswith("records/experiments/findings-1/")


def test_fd1_scan_reads_the_repairs_and_the_per_contest_grades(tmp_path, fd1):
    """The two facts PREREG §3 wants that no index column carries: the format repairs at
    each call site, and validity PER CONTEST with its kind (`grade_contests_valid_n` is an
    objection-level count and cannot be split afterwards).

    The scan is walked by the DECISION run, not by `grade.json`, so a cell that was decided
    and then lost its contest still appears with its judge columns — "the judge wrote a
    list and the challenger call failed" is a fact PREREG §6's loss rule needs.
    """
    def cell(name, *, contest=True):
        decision = tmp_path / "cells" / name / "runs" / "r0"
        decision.mkdir(parents=True)
        (decision / "verdict.json").write_text(json.dumps({
            "verdict": "SOUND", "parse_mode": "strict", "repair_attempts": 1,
            "finish_reason": "stop"}), encoding="utf-8")
        (decision / "findings.json").write_text(json.dumps({
            "parse_mode": "strict", "n_findings": 3}), encoding="utf-8")
        if not contest:
            return
        run = tmp_path / "cells" / name / "contests" / "flash" / "runs" / "r0"
        run.mkdir(parents=True)
        (run / "challenge.json").write_text(json.dumps({
            "parse_mode": "salvaged", "repair_attempts": 2}), encoding="utf-8")
        (run / "ruling.json").write_text(json.dumps({
            "parse_mode": "strict", "repair_attempts": 0}), encoding="utf-8")
        (run / "grade.json").write_text(json.dumps({"parse_mode": "strict", "contests": [
            {"index": 1, "kind": "finding", "valid": True, "mechanical": False},
            {"index": 2, "kind": "omission", "valid": False, "mechanical": True}]}),
            encoding="utf-8")

    cell("decided-and-contested")
    cell("lost-its-contest", contest=False)
    rows = {r["cell_id"]: r for r in fd1.scan_tree(tmp_path)}

    assert set(rows) == {"decided-and-contested", "lost-its-contest"}
    got = rows["decided-and-contested"]
    assert got["judge_repairs"] == 1 and got["challenge_repairs"] == 2
    assert got["ruling_repairs"] == 0
    assert got["grade_contests"] == [
        {"kind": "finding", "valid": True, "mechanical": False},
        {"kind": "omission", "valid": False, "mechanical": True}]
    lost = rows["lost-its-contest"]
    assert lost["judge_parse_mode"] == "strict"
    assert "grade_contests" not in lost, "a lost contest is absent, not empty"


# --- fd1-handcheck-pick: the cells a person reads --------------------------------------


@pytest.fixture(scope="module")
def fd1_pick():
    return _load("fd1-handcheck-pick.py")


def _pick_tree(root: Path, rows):
    """A run tree with an index and one decision + contest directory per cell."""
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "index.jsonl", rows)
    for row in rows:
        cell = row["cell_id"]
        decision = root / "cells" / cell / "runs" / "r0"
        decision.mkdir(parents=True)
        (decision / "transcript.md").write_text("decision", encoding="utf-8")
        contest = root / "cells" / cell / "contests" / "flash" / "runs" / "r0"
        contest.mkdir(parents=True)
        (contest / "transcript.md").write_text("contest", encoding="utf-8")
        (contest / "challenge.json").write_text(
            json.dumps({"text": row.pop("_argument", "")}), encoding="utf-8")


def test_fd1_pick_draws_the_five_groups_and_writes_a_parseable_file(tmp_path, capsys,
                                                                    fd1_pick, fd1):
    """The pick file is READ BY `fd1-collect-records.py`, so its format is load-bearing:
    `## (x)` headings and ``- **`cell`** [arm]`` lines. It scores nothing — a person reads
    the documents — so what is asserted here is the SELECTION and the FORMAT."""
    weak = [
        # broke a right decision, and fixed a wrong one
        _fd1_row("broke__debate__r1", before=True, after=False),
        _fd1_row("fixed__debate__r1", before=False, after=True, verdict="FLAWED"),
        # an appended finding, and an empty list
        _fd1_row("appended__debate__r1", before=True, after=True, findings_added_n=1),
        _fd1_row("empty__debate__r1", before=True, after=None, findings_n=0,
                 findings_flaw_n=0, challenge_stance="agrees", challenge_raised=False),
        # a STANDS with a real Argument — group (e)'s second blind spot
        _fd1_row("stands__debate__r1", before=True, after=None,
                 challenge_stance="declined", challenge_raised=False),
    ]
    strong = [_fd1_row(row["cell_id"], before=True, after=None,
                       verdict="FLAWED" if row["cell_id"].startswith("broke") else "SOUND")
              for row in weak]
    for row in weak:
        row["_argument"] = "the findings miss the point about finding 2 entirely"
    _pick_tree(tmp_path / "weak", weak)
    _pick_tree(tmp_path / "strong", strong)

    assert fd1_pick.main(["--weak", str(tmp_path / "weak"),
                          "--strong", str(tmp_path / "strong")]) == 0
    out = capsys.readouterr().out

    for group in ("## (a)", "## (b)", "## (c)", "## (d)", "## (e1)", "## (e2)"):
        assert group in out, group
    assert "- **`broke__debate__r1`** [weak]" in out
    assert "- **`fixed__debate__r1`** [weak]" in out
    assert "- **`appended__debate__r1`** [weak]" in out
    assert "- **`empty__debate__r1`** [weak]" in out
    # (d) is the ONLY group that names both arms on one cell
    assert "- **`broke__debate__r1`** [both]" in out
    # the STANDS half of the phantom read reads the challenge text, which no column carries
    assert "Argument 52 chars" in out
    # it scores nothing and says so
    assert "it scores nothing" in out
    assert "for READING, never for counting" in out


def test_fd1_pick_says_an_empty_pool_is_a_reading(tmp_path, capsys, fd1_pick):
    """A group with nothing in it is a finding — "recourse broke no right decision" — and
    it is printed as one rather than left as a silent gap."""
    _pick_tree(tmp_path / "weak", [_fd1_row("only__debate__r1", before=True, after=True)])
    _pick_tree(tmp_path / "strong", [_fd1_row("only__debate__r1", before=True, after=True)])
    assert fd1_pick.main(["--weak", str(tmp_path / "weak"),
                          "--strong", str(tmp_path / "strong")]) == 0
    out = capsys.readouterr().out
    assert "*The pool is empty.*" in out
    assert "That is itself a reading" in out


def test_fd1_pick_runs_before_either_arm_exists(tmp_path, capsys, fd1_pick):
    assert fd1_pick.main(["--weak", str(tmp_path / "none"),
                          "--strong", str(tmp_path / "none")]) == 0
    out = capsys.readouterr().out
    assert "NOTHING TO PICK" in out
    assert "is not an error" in out


def test_fd1_pick_is_seeded_per_group_and_reproducible(fd1_pick):
    """Per-group seeds, so a re-draw of one group does not move the others. A shared seed
    would make re-picking (a) silently change which twenty cells were read for (e)."""
    assert set(fd1_pick.SEEDS) == {"a", "b", "c", "d", "e-reverse", "e-stands"}
    assert len(set(fd1_pick.SEEDS.values())) == len(fd1_pick.SEEDS)
    pool = [f"c{i:03d}" for i in range(200)]
    first = fd1_pick.sample(pool, fd1_pick.SEEDS["a"], 5)
    assert first == fd1_pick.sample(pool, fd1_pick.SEEDS["a"], 5)
    assert first != fd1_pick.sample(pool, fd1_pick.SEEDS["b"], 5)
    assert first == sorted(first) and len(first) == 5
    # a pool no bigger than the draw comes back whole, in order
    assert fd1_pick.sample(["b", "a"], 1, 5) == ["a", "b"]


# --- fd1-collect-records: what carries the evidence into git ---------------------------


@pytest.fixture(scope="module")
def fd1_collect():
    return _load("fd1-collect-records.py")


def test_fd1_collect_parses_the_pick_file_the_pick_script_writes(tmp_path, fd1_collect):
    """The two files are coupled by ONE format, and it is the coupling most likely to rot:
    the pick script writes `## (x)` headings and ``- **`cell`** [arm]`` lines, and this
    script has to find every cell in them. Group (e) is written as `(e1)` and `(e2)` — the
    two blind spots of PREREG §7's phantom instrument — and both belong under `e`."""
    pick = tmp_path / "pick.md"
    pick.write_text("\n".join([
        "# findings-1 — the cells to read by hand",
        "",
        "## (a) recourse BROKE a right decision",
        "",
        "- **`alpha__debate__r1`** [weak] — a note",
        "  - weak decision: `somewhere`",
        "## (d) F-weak and F-strong DISAGREE on the before-verdict",
        "- **`delta__debate__r1`** [both] — another note",
        "## (e1) ten REVERSE objections",
        "- **`echo__debate__r1`** [strong]",
        "## (e2) ten STANDS with a non-empty Argument",
        "- **`foxtrot__debate__r1`** [weak]",
    ]), encoding="utf-8")

    got = fd1_collect.wanted_cells(pick)
    assert ("a", "weak", "alpha__debate__r1") in got
    # [both] becomes ONE triple per arm, because each arm has its own documents
    assert ("d", "weak", "delta__debate__r1") in got
    assert ("d", "strong", "delta__debate__r1") in got
    # (e1) and (e2) both land under (e)
    assert ("e", "strong", "echo__debate__r1") in got
    assert ("e", "weak", "foxtrot__debate__r1") in got
    assert len(got) == 5


def test_fd1_collect_copies_both_documents_for_every_hand_checked_cell(tmp_path,
                                                                      capsys,
                                                                      fd1_collect):
    """This campaign's DECISION document is the one that carries the findings list, so a
    hand check that saw only the contest would be reading the objection without the thing
    it objects to. Both runs come across, named apart."""
    out = tmp_path / "outputs"
    tree = out / "experiments" / "fd1-weak"
    (tree).mkdir(parents=True)
    (tree / "index.jsonl").write_text("{}\n", encoding="utf-8")
    (tree / "metrics.json").write_text("{}", encoding="utf-8")
    decision = tree / "cells" / "alpha__debate__r1" / "runs" / "r0"
    decision.mkdir(parents=True)
    for name in ("transcript.md", "transcript_full.md", "verdict.json", "findings.json"):
        (decision / name).write_text("x", encoding="utf-8")
    contest = (tree / "cells" / "alpha__debate__r1" / "contests" / "flash" / "runs" / "r0")
    contest.mkdir(parents=True)
    for name in ("transcript.md", "ruling.json", "findings.after.json", "grade.json"):
        (contest / name).write_text("y", encoding="utf-8")
    (out / "fd1-handcheck-pick.md").write_text(
        "## (a) broke\n- **`alpha__debate__r1`** [weak]\n", encoding="utf-8")
    records = tmp_path / "records"

    assert fd1_collect.main(["--out", str(out), "--records", str(records),
                             "--weak-tree", "fd1-weak", "--strong-tree", "fd1-strong",
                             "--create"]) == 0
    printed = capsys.readouterr().out
    names = {p.name for p in (records / "transcripts").glob("*")}
    assert "a__weak__alpha__debate__r1__decision__transcript.md" in names
    assert "a__weak__alpha__debate__r1__decision__findings.json" in names
    assert "a__weak__alpha__debate__r1__contest__transcript.md" in names
    assert "a__weak__alpha__debate__r1__contest__findings.after.json" in names
    assert (records / "arm-weak" / "index.jsonl").is_file()
    # PREREG.md and run-all.sh were committed before the first paid call, and this script
    # says so rather than quietly leaving them out
    assert "PREREG.md and run-all.sh" in printed
    assert not (records / "PREREG.md").exists()
    assert not (records / "run-all.sh").exists()


def test_fd1_collect_refuses_a_records_directory_that_does_not_exist(tmp_path,
                                                                     capsys,
                                                                     fd1_collect):
    """A typo in `--records` must not silently make a new tree beside the real one."""
    assert fd1_collect.main(["--out", str(tmp_path), "--records",
                             str(tmp_path / "typo")]) == 1
    assert "does not exist" in capsys.readouterr().out
    assert not (tmp_path / "typo").exists()
