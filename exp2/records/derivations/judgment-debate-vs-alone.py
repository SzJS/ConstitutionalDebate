"""DEBATE + PROCEDURAL RECOURSE vs DEBATE ALONE — the paired, within-debate endpoint.

Only a debate publishes a judgment that is a document other than the decision itself:
`single`'s record IS its justification and `self_critique`'s is the same model's own
drafts, so auditing the judgment against the record is a procedure that exists in one
condition and is undefined in the other two (`records/pick-auditor/DECISION.md`). The
question is therefore not between conditions. It is PAIRED and WITHIN debate — the same
decided debate cells, their accuracy before recourse and after it — which is what
`DESIGN.md`'s `## Judgment-challenge` asks for: "comparing debate with and without the
judgment-contest."

    uv run python records/derivations/judgment-debate-vs-alone.py \
        --before records/experiments/sweep/index.jsonl \
        --neutral records/experiments/rerule/recontest/index.jsonl \
        --procedural records/experiments/judgment-debate/index.jsonl

Three indexes, three states of the same cells:

  BEFORE       `initially_correct` in the sweep's index — the decision as the debate
               judge left it, contested by nobody.
  NEUTRAL      the neutral decide-last challenger's objections re-ruled under the
               corrected ruling line (`records/experiments/rerule/recontest/`). A
               re-rule tree writes challenge and ruling columns only for the cells that
               were contested, so a row with no `final_correct` is a cell nobody
               objected to and its after-state is its before-state. That substitution is
               counted and printed; it is not silent.
  PROCEDURAL   the judgment audit — this run. Same cells, same third-party recourse
               judge, same corrected ruling line; the challenger reads the judgment
               against the record instead of re-deciding the item.

**It reads the committed indexes and nothing else**, so it runs on a blank machine
straight after `git clone` — no `outputs/` tree, no `calls.jsonl`, no per-cell run
directory, no network, no API key. `--tree <dir>` is an *optional* extra: given a run
tree it opens each contested cell's `challenge.json` and `grade.json` for the ONE table
the index cannot carry — defects alleged and graded valid BY TYPE, since `build_index`
writes the counts (`grade_defects_n`, `grade_defects_valid_n`) and not the three types.
No other table depends on it, and without it that block says so rather than guessing.

THE PRIMARY ENDPOINT is the net accuracy change after recourse — cells fixed (wrong made
right) minus cells broken (right made wrong) — tested with an EXACT TWO-SIDED McNEMAR on
the discordant pairs at alpha = 0.05:

    p = min(1, 2 * sum_{k <= min(b, c)} C(b + c, k) / 2^(b + c))

with b = fixed and c = broken. It is the exact binomial, not the chi-square with or
without a continuity correction: the discordant counts here are tens, where the
asymptotic test is not to be trusted, and the exact test needs no `scipy`. Concordant
pairs — the cells recourse left as it found them — carry no information about the
direction of change and are excluded by construction, which is the whole point of
pairing. The same test is applied a second time to NEUTRAL-after against
PROCEDURAL-after, paired on `cell_id`.

WHAT THIS DOES NOT SHOW, and the numbers must be read with it. A valid procedural
objection does not imply a wrong verdict. If the challenger raises on most cells, the
endpoint is mostly the third-party recourse judge (`openai/gpt-4.1-nano`) re-ruling with
an objection in hand, and the specious-objection control that separates "a second look"
from "the audit" — every cell re-ruled on a placeholder objection — is not in this run.
The challenger is `google/gemini-2.5-flash`, chosen AFTER the auditor probe's
pre-registered rule picked nobody (`records/pick-auditor/RULES.md`, `DECISION.md`), and
that model invents a defect on 15% of controls. And every number that passes through a
ruling inherits the `ruling_line_mismatch` residual, which the run measures rather than
assumes.

Definitions are shared with `records/derivations/sweep-phantom-corrected.py` and
`rerule-compare.py` and must stay identical to them:

    phantom objection   challenge_stance == "contests" and prose_stance == "RIGHT"
    genuine objection   challenge_stance == "contests" and prose_stance == "WRONG"
    final verdict       the ruling's verdict if the contest produced a ruling,
                        else the decision's own verdict  (`final_correct` in the index)
    fixed / broken      not correct before and correct after / the converse
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

CONDITION = "debate"
DEFECT_TYPES = ("contradiction", "misstatement", "omission")
W = 96


# --------------------------------------------------------------------------- #
# small formatting helpers  (kept identical in shape to rerule-compare.py's)
# --------------------------------------------------------------------------- #


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def rate(num, den):
    """`12/62 19.4%` — every rate in this script is printed with its n."""
    return f"{num}/{den} {pct(num, den)}" if den else f"{num}/0 n/a"


def rule(char="-"):
    print(char * W)


def head(title):
    print()
    rule("=")
    print(title)
    rule("=")


# --------------------------------------------------------------------------- #
# the statistics
# --------------------------------------------------------------------------- #


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar on the discordant pairs.

    Under the null the b + c discordant pairs are Binomial(b + c, 1/2), so the two-sided
    p is twice the smaller tail, capped at 1. `math.comb` keeps it exact in integers
    until the final division, so there is no floating-point drift at the tail.

    b = c gives 1 by construction (the two tails together are the whole distribution and
    then some), and b = c = 0 — no cell changed either way — gives 1 as well: no
    discordant pair is no evidence, not a significant null.
    """
    if b < 0 or c < 0:
        raise ValueError(f"discordant counts must be non-negative, got b={b} c={c}")
    n = b + c
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — the one this repo uses everywhere.

    Chosen over the normal approximation because it has width at 0/n and n/n, and 0/n is
    an expected outcome for several of the rates below. `z = 1.96` rather than the exact
    1.959964 to match `exp2.analysis.Rate.interval`, which is what `metrics.json`
    prints: a reader holding the two side by side must not find them disagreeing in the
    third decimal for a reason that is about neither run.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def acc(k: int, n: int) -> str:
    low, high = wilson(k, n)
    return f"{rate(k, n)}  [{100 * low:.1f}, {100 * high:.1f}]"


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #


def load(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["cell_id"]] = row
    return rows


def debate_only(rows: dict[str, dict]) -> dict[str, dict]:
    return {cell: row for cell, row in rows.items() if row.get("condition") == CONDITION}


def before_state(row) -> bool | None:
    return row.get("initially_correct")


def after_state(row, before) -> bool | None:
    """The cell's state once recourse has had its turn.

    `final_correct` where the tree wrote one. A re-rule tree writes the challenge and
    ruling columns ONLY for cells that were contested, so an absent `final_correct` is a
    cell nobody objected to and its after-state is its before-state — the same reading
    `metrics.json` and `sweep-phantom-corrected.py` take, and the reason the neutral arm
    is a fair third arm rather than a 54-cell one.
    """
    final = row.get("final_correct")
    return before if final is None else bool(final)


def phantom(row):
    return row.get("challenge_stance") == "contests" and row.get("prose_stance") == "RIGHT"


def genuine(row):
    return row.get("challenge_stance") == "contests" and row.get("prose_stance") == "WRONG"


def paired_counts(pairs) -> dict[str, int]:
    """The 2x2 of (before, after) over (cell, before, after) triples with a gold label."""
    counts = Counter((before, after) for _, before, after in pairs)
    return {
        "n": sum(counts.values()),
        "rr": counts[(True, True)],     # right before, right after
        "rw": counts[(True, False)],    # broken
        "wr": counts[(False, True)],    # fixed
        "ww": counts[(False, False)],
    }


def paired_block(pairs, left: str, right: str) -> dict[str, float | int]:
    """One 2x2, its fixed/broken/net, its McNemar and both accuracies. Printed here."""
    t = paired_counts(pairs)
    n = t["n"]
    fixed, broken = t["wr"], t["rw"]
    net = fixed - broken
    p = mcnemar_exact(fixed, broken)
    before_correct = t["rr"] + t["rw"]
    after_correct = t["rr"] + t["wr"]

    print(f"{'':<26}{right + ' correct':>18}{right + ' wrong':>18}{'total':>10}")
    rule()
    print(f"{left + ' correct':<26}{t['rr']:>18}{t['rw']:>18}{before_correct:>10}")
    print(f"{left + ' wrong':<26}{t['wr']:>18}{t['ww']:>18}{n - before_correct:>10}")
    rule()
    print(f"{'total':<26}{after_correct:>18}{n - after_correct:>18}{n:>10}")
    print()
    print(f"  fixed   ({left} wrong -> {right} correct)   b = {fixed}")
    print(f"  broken  ({left} correct -> {right} wrong)   c = {broken}")
    print(f"  NET                                    {net:+d} cells")
    print(f"  discordant pairs                       {fixed + broken}"
          f"   (concordant {t['rr'] + t['ww']}, and they carry no direction)")
    print(f"  EXACT TWO-SIDED McNEMAR                p = {p:.6g}"
          f"   {'SIGNIFICANT at alpha=0.05' if p < 0.05 else 'not significant at alpha=0.05'}")
    print()
    print(f"  accuracy {left:<12} {acc(before_correct, n)}   (95% Wilson)")
    print(f"  accuracy {right:<12} {acc(after_correct, n)}   (95% Wilson)")
    return {"n": n, "fixed": fixed, "broken": broken, "net": net, "p": p}


# --------------------------------------------------------------------------- #
# the secondary, descriptive table
# --------------------------------------------------------------------------- #


def secondary(rows: list[dict]) -> None:
    head("(c) SECONDARY, DESCRIPTIVE — what the challenger did, and what held up")
    print("Every rate here is conditional on the step before it, so read the raise rate")
    print("first: a valid-objection rate is over OBJECTIONS, not over cells, and")
    print("multiplying through is what the funnel does. None of these is the endpoint.")
    print()

    raised = [r for r in rows if r.get("challenge_raised")]
    stances = Counter(r.get("challenge_stance") for r in rows)
    print(f"cells                                {len(rows)}")
    print(f"objection raised                     {rate(len(raised), len(rows))}")
    for stance in ("contests", "declined", "agrees", "unclear", None):
        if stances.get(stance):
            print(f"  stance {str(stance):<28}{rate(stances[stance], len(rows))}")
    print(f"phantom (line REVERSE, prose RIGHT)  "
          f"{rate(sum(1 for r in rows if phantom(r)), len(raised))}   of objections")
    print(f"genuine (line REVERSE, prose WRONG)  "
          f"{rate(sum(1 for r in rows if genuine(r)), len(raised))}   of objections")
    unread = [r for r in raised if r.get("prose_stance") is None]
    if unread:
        print(f"objections the agreement stage did not read: {len(unread)}")

    print()
    print("VALID-OBJECTION RATE, per objection, split by whether the decision was right.")
    print("Under the judgment variant this is a PROCESS claim graded against the record —")
    print("`flaw.json` is never opened — so a valid defect on a CORRECT decision is a real")
    print("finding and not a false alarm, and both rows below mean something.")
    print()
    graded = [r for r in raised if r.get("grade_valid") is not None]
    print(f"{'decision was':<22}{'objections':>12}{'graded':>10}{'valid':>22}"
          f"{'defects alleged':>18}{'defects valid':>16}")
    rule()
    for label, sel in (("CORRECT", [r for r in raised if r.get("initially_correct")]),
                       ("wrong", [r for r in raised if r.get("initially_incorrect")]),
                       ("both", raised)):
        g = [r for r in sel if r.get("grade_valid") is not None]
        alleged = sum(r.get("grade_defects_n") or 0 for r in g)
        valid = sum(r.get("grade_defects_valid_n") or 0 for r in g)
        print(f"{label:<22}{len(sel):>12}{len(g):>10}"
              f"{rate(sum(1 for r in g if r['grade_valid']), len(g)):>22}"
              f"{alleged:>18}{rate(valid, alleged):>16}")
    print()
    print(f"objections raised but never graded: {len(raised) - len(graded)}"
          " (a defect whose quotation failed the")
    print("parse-time check is never sent to the grader, and an objection all of whose")
    print("defects failed it gets no grader call at all — that is the design, not a loss.")

    print()
    print("MISATTRIBUTED QUOTES — the parse-time check, over DEFECTS not objections. A")
    print("defect whose `Judgment says:` quotation is not in the judgment is the failure")
    print("mode that made `gpt-4.1-nano` unusable here (34 of 66 quotations, by hand).")
    counted = [r for r in rows if r.get("challenge_defects_n") is not None
               and r.get("challenge_defects_misattributed_n") is not None]
    if counted:
        print(f"  misattributed_quote                "
              f"{rate(sum(r['challenge_defects_misattributed_n'] for r in counted), sum(r['challenge_defects_n'] for r in counted))}"
              f"   of defects over {len(counted)} objections")
    else:
        print("  NOT MEASURED — no `challenge_defects_n` column in this index. The")
        print("  parse-time quote check post-dates it; the objections were never checked.")

    print()
    print("OVERTURN RATE — what the third-party recourse judge did with the objection it")
    print("was handed, split by whether the decision it was ruling on was in fact wrong.")
    print("The difference is the DISCRIMINATION, and it is the one figure here a judge")
    print("cannot raise by overturning everything.")
    print()
    ruled = [r for r in raised if r.get("ruling_form") is not None]
    print(f"{'bucket':<28}{'n':>8}{'overturned':>22}")
    rule()
    buckets = [
        ("decision wrong", [r for r in ruled if r.get("initially_incorrect")]),
        ("decision CORRECT", [r for r in ruled if r.get("initially_correct")]),
        ("  of those, genuine|wrong", [r for r in ruled
                                       if genuine(r) and r.get("initially_incorrect")]),
        ("  of those, genuine|corr", [r for r in ruled
                                      if genuine(r) and r.get("initially_correct")]),
        ("  of those, phantom", [r for r in ruled if phantom(r)]),
    ]
    for label, sel in buckets:
        if not sel:
            continue
        k = sum(1 for r in sel if r.get("changed_the_decision"))
        print(f"{label:<28}{len(sel):>8}{rate(k, len(sel)):>22}")
    rule()
    discrimination(rows)
    print()

    print("RULING LINE vs THE JUDGE'S OWN PROSE — the residual every revision number")
    print("inherits. Haiku reads the judge's reasoning with the conclusion line stripped")
    print("and says what it concludes; a mismatch is a ruling whose line contradicts the")
    print("reasoning that produced it. Measured at ~6% on the full re-rule, concentrated")
    print("in python800.")
    measured = [r for r in ruled if r.get("ruling_line_mismatch") is not None]
    if measured:
        print(f"  ruling_line_mismatch               "
              f"{rate(sum(1 for r in measured if r['ruling_line_mismatch']), len(measured))}"
              f"   of rulings the stage could read")
        for parent in ("FLAWED", "SOUND"):
            sel = [r for r in measured if r.get("verdict") == parent]
            if sel:
                print(f"    on a {parent:<7} parent            "
                      f"{rate(sum(1 for r in sel if r['ruling_line_mismatch']), len(sel))}")
    else:
        print("  NOT MEASURED — the ruling_agreement stage has not run on this tree.")
        print("  Every net-accuracy figure above is unbounded in the way the re-contest's")
        print("  were before the instrument existed. Run the stage before quoting them.")


def discrimination(rows: list[dict]) -> None:
    """Printed separately so the arithmetic is visible rather than inlined."""
    ruled = [r for r in rows if r.get("challenge_raised")
             and r.get("ruling_form") is not None]
    wrong = [r for r in ruled if r.get("initially_incorrect")]
    right = [r for r in ruled if r.get("initially_correct")]
    if not wrong or not right:
        return
    a = sum(1 for r in wrong if r.get("changed_the_decision")) / len(wrong)
    b = sum(1 for r in right if r.get("changed_the_decision")) / len(right)
    print(f"  DISCRIMINATION (overturn on wrong minus on correct)  {100 * (a - b):+.1f} pts")


# --------------------------------------------------------------------------- #
# defects by type — the one table the index cannot carry
# --------------------------------------------------------------------------- #


UNRECORDED = "(type not recorded)"


def defects_by_type(tree: Path, cells: list[str]):
    """Alleged and graded-valid defects by type, read from the run tree.

    `build_index` writes `grade_defects_n` and `grade_defects_valid_n` and not the three
    types, so this is the only block that opens a per-cell record. It is optional, and
    nothing above depends on it.

    Two files, and they say different things. `challenge.json`'s `defects` is the
    challenger's own parsed list and carries `type` and `quote_in_judgment`.
    `grade.json`'s `defects` is the grader's ruling on each of them, joined back to that
    list BY NUMBER — so a grade whose `type` is null is a ruling on a defect the parsed
    list does not contain, which is what a tree written before `parse_defects` stored its
    list looks like. That is reported as `(type not recorded)` rather than dropped, and
    the totals line says when the two files disagree.
    """
    alleged = Counter()
    valid = Counter()
    misattributed = Counter()
    grade_n = grade_valid_n = 0
    opened = missing = 0
    for cell in cells:
        runs = sorted((tree / "cells" / cell / "contests").glob("*/runs/*"), reverse=True)
        run = next((d for d in runs if (d / "challenge.json").is_file()), None)
        if run is None:
            missing += 1
            continue
        opened += 1
        challenge = json.loads((run / "challenge.json").read_text(encoding="utf-8"))
        for defect in challenge.get("defects") or []:
            alleged[defect.get("type") or UNRECORDED] += 1
            if defect.get("quote_in_judgment") is False:
                misattributed[defect.get("type") or UNRECORDED] += 1
        grade_path = run / "grade.json"
        if grade_path.is_file():
            grade = json.loads(grade_path.read_text(encoding="utf-8"))
            rulings = grade.get("defects") or []
            grade_n += len(rulings)
            for defect in rulings:
                if defect.get("valid"):
                    grade_valid_n += 1
                    valid[defect.get("type") or UNRECORDED] += 1

    head("(d) DEFECTS BY TYPE  (read from the run tree; no table above uses it)")
    print(f"tree {tree}")
    print(f"contest records opened {opened}   cells with none {missing}")
    print()
    print(f"{'type':<24}{'alleged':>12}{'misattributed':>18}{'graded valid':>18}"
          f"{'valid / alleged':>18}")
    rule()
    # the three the prompt defines, in the prompt's order, then anything else a reply
    # invented — an unexpected type is a parser finding and must not be swallowed
    seen = [t for t in DEFECT_TYPES if alleged[t] or valid[t]]
    seen += sorted((set(alleged) | set(valid)) - set(seen), key=str)
    for t in seen:
        print(f"{str(t):<24}{alleged[t]:>12}{misattributed[t]:>18}{valid[t]:>18}"
              f"{rate(valid[t], alleged[t]):>18}")
    rule()
    print(f"{'TOTAL':<24}{sum(alleged.values()):>12}{sum(misattributed.values()):>18}"
          f"{sum(valid.values()):>18}"
          f"{rate(sum(valid.values()), sum(alleged.values())):>18}")
    print()
    print(f"the graders' own totals, for comparison: {grade_n} defects ruled on, "
          f"{grade_valid_n} valid")
    if grade_n != sum(alleged.values()):
        print(f"THESE DISAGREE. The grader ruled on {grade_n} defects and the parsed")
        print(f"challenge lists hold {sum(alleged.values())}. On a tree written before")
        print("`parse_defects` stored the list, `challenge.json`'s `defects` is empty and")
        print("the grade's per-defect `type` is null with it — read the by-type split as")
        print("covering only the objections whose list WAS stored, and the (c) table's")
        print("counts, which come from the index, as the authority on how many there were.")
    print()
    print("A defect whose quotation failed the parse-time check is counted as alleged and")
    print("is never sent to the grader, so it can never be valid. `misattributed` is that")
    print("column; the probe measured flash inventing a defect on 15% of controls, and")
    print("this is where that shows up as a rate of this run's own.")


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Debate + procedural recourse vs debate alone, paired within debate.")
    ap.add_argument("--before", type=Path,
                    default=Path("records/experiments/sweep/index.jsonl"),
                    help="index.jsonl carrying the decisions BEFORE recourse "
                         "(default: records/experiments/sweep/index.jsonl)")
    ap.add_argument("--neutral", type=Path,
                    default=Path("records/experiments/rerule/recontest/index.jsonl"),
                    help="index.jsonl of the NEUTRAL recourse arm, re-ruled under the "
                         "corrected line (default: "
                         "records/experiments/rerule/recontest/index.jsonl)")
    ap.add_argument("--procedural", type=Path,
                    default=Path("records/experiments/judgment-debate/index.jsonl"),
                    help="index.jsonl of the judgment-audit run "
                         "(default: records/experiments/judgment-debate/index.jsonl)")
    ap.add_argument("--tree", type=Path, default=None,
                    help="optional: the judgment-audit run tree, for the defects-by-type "
                         "table, which the index cannot carry")
    args = ap.parse_args()

    before_all = debate_only(load(args.before))
    proc_all = debate_only(load(args.procedural))
    neutral_all = debate_only(load(args.neutral))

    population = [c for c in proc_all if c in before_all]
    labelled = [c for c in population if before_state(before_all[c]) is not None]
    rows = [proc_all[c] for c in labelled]

    print("=" * W)
    print("DEBATE + PROCEDURAL RECOURSE vs DEBATE ALONE — paired, within debate")
    print("=" * W)
    print(f"BEFORE      {args.before}")
    print(f"NEUTRAL     {args.neutral}")
    print(f"PROCEDURAL  {args.procedural}")
    if args.tree:
        print(f"run tree    {args.tree}   (defects-by-type only)")
    print()
    print("Restricted to `condition == debate`. The other two conditions are not run and")
    print("not compared: their record IS their judgment, so there is nothing to audit it")
    print("against, and the procedure under test is undefined there.")

    # ------------------------------------------------------------------ join
    head("JOIN")
    print(f"BEFORE debate rows                 {len(before_all)}")
    print(f"PROCEDURAL debate rows             {len(proc_all)}")
    print(f"NEUTRAL debate rows                {len(neutral_all)}")
    print(f"in BEFORE and PROCEDURAL           {len(population)}")
    print(f"  of those, carrying a gold label  {len(labelled)}   <- the population")
    print(f"in BEFORE only                     {len(set(before_all) - set(proc_all))}"
          "   (decided but not contested by this run)")
    print(f"in PROCEDURAL only                 {len(set(proc_all) - set(before_all))}")
    print()
    fails = [f"{c}: verdict {before_all[c].get('verdict')!r} != "
             f"{proc_all[c].get('verdict')!r}"
             for c in population
             if before_all[c].get("verdict") != proc_all[c].get("verdict")
             or before_all[c].get("initially_correct")
             != proc_all[c].get("initially_correct")]
    if fails:
        raise SystemExit(
            "the two trees do not describe the same decisions:\n  "
            + "\n  ".join(fails[:20])
            + (f"\n  ... and {len(fails) - 20} more" if len(fails) > 20 else ""))
    print(f"identity asserted cell by cell on verdict and initially_correct: "
          f"{len(population)}/{len(population)} identical.")
    print("The PROCEDURAL run reads its decisions out of the BEFORE tree through")
    print("`decisions_from` and never writes to it, so this is a check that the join is")
    print("the join it claims to be, not a measurement.")

    # ------------------------------------------------------- (a) the endpoint
    head("(a) PRIMARY ENDPOINT — accuracy BEFORE recourse vs AFTER the judgment audit")
    print("The population is every debate cell the source tree decided and this run")
    print("contested, carrying a dataset label. A cell's after-state is the ruling's")
    print("verdict where the contest produced a ruling and the decision's own otherwise.")
    print()
    primary = paired_block(
        [(c, before_state(before_all[c]), after_state(proc_all[c], before_state(before_all[c])))
         for c in labelled],
        "BEFORE", "AFTER")
    print()
    print("The dataset labels are the outer bound on `correct` and none of this changes")
    print("them: a ruling that agrees with a wrong label counts as wrong.")

    # ----------------------------------------- (b) neutral vs procedural
    paired_cells = [c for c in labelled if c in neutral_all]
    head("(b) THE THIRD PAIRED ARM — neutral recourse vs the judgment audit")
    print("Same cells, same third-party recourse judge (openai/gpt-4.1-nano), same")
    print("corrected ruling line. What differs is the QUESTION the challenger was asked:")
    print("the neutral arm re-decides the item, this one audits the judgment against the")
    print("record. A neutral cell nobody objected to keeps its before-state, which is the")
    print("substitution counted below.")
    print()
    substituted = sum(1 for c in paired_cells if neutral_all[c].get("final_correct") is None)
    print(f"cells paired on cell_id            {len(paired_cells)}")
    print(f"  neutral rows with no ruling      {substituted}   (after-state = before-state)")
    print(f"  neutral rows with a final_correct{len(paired_cells) - substituted:>4}")
    print(f"cells in the population but not in the neutral index: "
          f"{len(labelled) - len(paired_cells)}")
    print()
    print("b1 — BEFORE vs NEUTRAL, the same test on the same cells, for reference")
    print()
    neutral_ref = paired_block(
        [(c, before_state(before_all[c]),
          after_state(neutral_all[c], before_state(before_all[c])))
         for c in paired_cells],
        "BEFORE", "NEUTRAL")
    print()
    print("b2 — NEUTRAL-after vs PROCEDURAL-after, paired on cell_id")
    print()
    arm = paired_block(
        [(c, after_state(neutral_all[c], before_state(before_all[c])),
          after_state(proc_all[c], before_state(before_all[c])))
         for c in paired_cells],
        "NEUTRAL", "PROCEDURAL")
    print()
    print("A significant b2 says the two recourse procedures reach different answers on")
    print("the same decisions. It does not say which is right on its own — read it beside")
    print("b1 and (a), whose accuracies are against the dataset label.")

    # ---------------------------------------------------- (c) the secondary
    secondary(rows)

    # ----------------------------------------------------- (d) by type
    if args.tree:
        defects_by_type(args.tree, labelled)
    else:
        head("(d) DEFECTS BY TYPE")
        print("skipped — `build_index` writes the defect COUNTS (grade_defects_n,")
        print("grade_defects_valid_n) and not the three types, so this table needs the run")
        print("tree. Pass `--tree outputs/experiments/<name>` for it. Nothing above uses")
        print("it, and the counts it would break down are printed in (c).")

    # ---------------------------------------------------- (e) per subset
    head("(e) PER SUBSET — fixed / broken / net, and the endpoint restated")
    print("Seven subsets, three label bases, and `label_basis` is not pooled: injected_pair,")
    print("sentence_labels and final_answer are three different claims about what 'flawed'")
    print("means. A per-subset McNemar on tens of cells is descriptive; the endpoint is the")
    print("pooled test in (a).")
    print()
    print(f"{'subset':<16}{'basis':<18}{'n':>6}{'acc before':>13}{'acc after':>12}"
          f"{'raised':>16}{'fixed':>7}{'broken':>8}{'net':>6}{'McNemar p':>12}")
    rule()
    keys = sorted({(proc_all[c].get("subset"), proc_all[c].get("label_basis"))
                   for c in labelled})
    for subset, basis in keys:
        sel = [c for c in labelled
               if proc_all[c].get("subset") == subset
               and proc_all[c].get("label_basis") == basis]
        triples = [(c, before_state(before_all[c]),
                    after_state(proc_all[c], before_state(before_all[c]))) for c in sel]
        t = paired_counts(triples)
        raised = sum(1 for c in sel if proc_all[c].get("challenge_raised"))
        p = mcnemar_exact(t["wr"], t["rw"])
        print(f"{str(subset):<16}{str(basis):<18}{t['n']:>6}"
              f"{pct(t['rr'] + t['rw'], t['n']):>13}{pct(t['rr'] + t['wr'], t['n']):>12}"
              f"{rate(raised, len(sel)):>16}"
              f"{t['wr']:>7}{t['rw']:>8}{t['wr'] - t['rw']:>+6d}{p:>12.4g}")
    rule()
    print(f"{'POOLED':<16}{'':<18}{primary['n']:>6}"
          f"{'':>13}{'':>12}{'':>16}"
          f"{primary['fixed']:>7}{primary['broken']:>8}{primary['net']:>+6d}"
          f"{primary['p']:>12.4g}")

    print()
    rule("=")
    print("SUMMARY")
    rule("=")
    print(f"primary   BEFORE -> PROCEDURAL   n={primary['n']}  "
          f"fixed {primary['fixed']}  broken {primary['broken']}  "
          f"net {primary['net']:+d}  p = {primary['p']:.6g}")
    print(f"reference BEFORE -> NEUTRAL      n={neutral_ref['n']}  "
          f"fixed {neutral_ref['fixed']}  broken {neutral_ref['broken']}  "
          f"net {neutral_ref['net']:+d}  p = {neutral_ref['p']:.6g}")
    print(f"third arm NEUTRAL -> PROCEDURAL  n={arm['n']}  "
          f"fixed {arm['fixed']}  broken {arm['broken']}  "
          f"net {arm['net']:+d}  p = {arm['p']:.6g}")
    print()
    print("Read the confound in this module's docstring before quoting any of it.")
    rule("=")
    print("end")


if __name__ == "__main__":
    main()
