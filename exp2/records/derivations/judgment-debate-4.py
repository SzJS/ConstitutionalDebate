"""judgment-debate-4 — the fabricated auditor: a specious control that is false BY CODE.

    cd exp2
    uv run python records/derivations/judgment-debate-4.py \
        2>&1 | tee outputs/judgment-debate-4-derivation.log

Stdlib only. It reads `index.jsonl` files and nothing else, so it runs on a blank machine
straight after `git clone` — no run tree, no `calls.jsonl`, no network, no key. Every
index path is a flag, so the same script runs against the committed indexes in
`records/experiments/judgment-debate-{3,4}/` and against a live `outputs/experiments/`
tree without editing a line; `--help` lists them all.

WHAT IS BEING COMPARED — FOUR ARMS ON ONE POPULATION, the **896 cells jd3's M1
contested**, which is this arm's cases file and every other arm's contested set:

    M1   the REAL audit          flash audits M0's judgment; Maverick rules   jd3-main
    M4   the GATED audit         M1's rulings, heard only where gpt-4.1-mini  jd3-gatekeeper
                                 called an alleged defect real  [POST HOC]
    jd4  the FABRICATED audit    every `Judgment says:` quotation INVENTED    jd4-fabricated
    M2   the PLACEHOLDER         one content-free objection, no model call    jd3-placeholder

Every one of them is ruled by `meta-llama/llama-4-maverick` under the MATERIALITY prompt,
against the same before-state (M0, Maverick's own judgment of the sweep's stored
transcript), so the four rows differ in exactly one thing: **what the judge was told**.

THE QUESTION THIS ARM ANSWERS, AND THE ONE IT DOES NOT.

  It answers: **how often does this judge overturn its own judgment on an objection that
  CANNOT be true?** jd3's M3 was supposed to answer that and could not — its objections
  were false only by instruction, and 29.2% of them were graded VALID, because with
  `omission` struck the only allegation left to it ("the judgment softened a party's
  position") is usually true of a judgment that compresses a three-round debate.

  It does not answer whether recourse improves accuracy. That was jd3's P1, it is a null,
  and section (c) here is an ABLATION carrying the same test for comparability — never an
  endpoint. An arm built to carry no information cannot improve a decision.

SECTION (0) IS THE MANIPULATION CHECK AND IT IS PRINTED FIRST, because every other number
in this file is worthless if it fails. It is a **string comparison**, not a grader:
`prompts.defect_quote_in_judgment` looks for every non-parenthetical `Judgment says:`
quotation in the judgment the challenger was shown, at parse time, and the index carries
`challenge_fabrication_ok` (True iff EVERY quotation of EVERY defect was looked for and
not found) and `challenge_defects_fabricated_n`. `PREREG.md`, committed before the first
paid call, **voids the arm below 80%**; this script implements that branch and prints the
void notice instead of a comparison if it fires.

The grader's own validity rate is printed beside it as the FAILURE MODE — an objection
this arm gets graded valid is one whose quotation turned out to be real — and it is the
number that says what changed between M3 and this arm: 29.2% against 0.1%.

Definitions are shared with `judgment-debate-3.py`, `judgment-debate-2.py`,
`judgment-debate-vs-alone.py` and `sweep-phantom-corrected.py` and must stay identical:

    final verdict   the ruling's verdict if the contest produced a ruling, else the
                    decision's own verdict (`final_correct` in the index)
    fixed / broken  not correct before and correct after / the converse
    phantom         challenge_stance == "contests" and prose_stance == "RIGHT"

SECTION (h) IS POST HOC, exactly as it is in judgment-debate-3.py: the prose-wins
sensitivity substitutes the materiality reader's reading of each ruling's prose for the
ruling's own line wherever that reader answered STANDS or CHANGED. It is not
pre-registered and it is only as good as a Haiku reader.

WHAT THIS FILE DOES NOT COMPUTE is the mechanism, because no index carries it. Eleven
rulings read by hand say that in 8 of 8 overturns the judge answers "is the alleged defect
real?" by looking up the RECORD quotation — which this arm keeps honest — and never asks
whether the judgment contains the sentence attributed to it; twice it notices the absence
and overturns anyway. That is
`records/experiments/judgment-debate-4/HANDCHECK-fabricated.md`, and it is what the 10.2%
means.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

CONDITION = "debate"
VERDICTS = ("FLAWED", "SOUND")
W = 100

# One alpha, for the ABLATION in section (c) only — there is no pre-registered test in
# this phase. Named rather than written at the call site for the reason judgment-debate-3
# names its own: an alpha applied in one place and forgotten in another is exactly the
# error writing it down prevents.
ALPHA = 0.05

# The floor `records/experiments/judgment-debate-4/PREREG.md` fixed before the first paid
# call: below this share of objections carrying ONLY invented judgment quotations, the arm
# is a failed manipulation and is reported as one.
FABRICATION_FLOOR = 0.80

# The arms, in the order the tables print them — most informative objection first, so the
# ladder from "true" to "nothing" reads down the page.
ARMS = (
    ("real", "M1 — the real audit"),
    ("gatekeeper", "M4 — the gated audit  [POST HOC]"),
    ("fabricated", "jd4 — the FABRICATED audit"),
    ("placeholder", "M2 — the placeholder (content-free)"),
)

# jd3's M3, quoted and never recomputed here: it stands on a different population (every
# decided cell, 1,642) because its instruction forbids the decline, and its numbers are in
# `records/experiments/judgment-debate-3/CHECKLIST.md` §1b.
M3_QUOTED = {
    "overturn": (239, 1642),
    "graded_valid": (479, 1641),
    "fixed": 100, "broken": 139,
    "fixed_rate": (100, 432), "broken_rate": (139, 1210),
}


# --------------------------------------------------------------------------- #
# formatting  (shape kept identical to judgment-debate-3.py's)
# --------------------------------------------------------------------------- #


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def rate(num, den):
    return f"{num}/{den} {pct(num, den)}" if den else f"{num}/0 n/a"


def rule(char="-"):
    print(char * W)


def head(title):
    print()
    rule("=")
    print(title)
    rule("=")


# --------------------------------------------------------------------------- #
# the statistics — byte-identical in behaviour to judgment-debate-3.py's
# --------------------------------------------------------------------------- #


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar on the discordant pairs."""
    if b < 0 or c < 0:
        raise ValueError(f"discordant counts must be non-negative, got b={b} c={c}")
    n = b + c
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — what `exp2.analysis.Rate.interval` prints."""
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


def interval(k: int, n: int) -> str:
    low, high = wilson(k, n)
    return f"[{100 * low:.1f}, {100 * high:.1f}]"


def verdict_at(p: float, alpha: float = ALPHA) -> str:
    return (f"SIGNIFICANT at alpha={alpha}" if p < alpha
            else f"not significant at alpha={alpha}")


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #


def load(path: Path | None) -> dict[str, dict]:
    """`{cell_id: row}` for the debate cells of one index, or `{}` for a missing one."""
    if path is None or not Path(path).is_file():
        return {}
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("condition") == CONDITION:
            rows[row["cell_id"]] = row
    return rows


def before_state(row) -> bool | None:
    return row.get("initially_correct")


def after_state(row, before) -> bool | None:
    """The cell's state once recourse has had its turn."""
    final = row.get("final_correct")
    return before if final is None else bool(final)


def gold_verdict(row):
    flawed = row.get("gold_flawed")
    return None if flawed is None else (VERDICTS[0] if flawed else VERDICTS[1])


def prose_after_state(row, before):
    """POST HOC. The after-state if the READER's reading of the prose beat the line."""
    prose = row.get("ruling_prose_conclusion")
    if row.get("ruling_prompt_form") == "materiality" and prose in VERDICTS:
        gold = gold_verdict(row)
        return None if gold is None else prose == gold
    return after_state(row, before)


def paired_counts(pairs) -> dict[str, int]:
    counts = Counter((left, right) for _, left, right in pairs)
    return {
        "n": sum(counts.values()),
        "rr": counts[(True, True)],
        "rw": counts[(True, False)],    # broken
        "wr": counts[(False, True)],    # fixed
        "ww": counts[(False, False)],
    }


def paired_block(pairs, left: str, right: str, alpha: float = ALPHA) -> dict:
    t = paired_counts(pairs)
    n = t["n"]
    fixed, broken = t["wr"], t["rw"]
    net = fixed - broken
    p = mcnemar_exact(fixed, broken)
    left_correct = t["rr"] + t["rw"]
    right_correct = t["rr"] + t["wr"]

    print(f"{'':<26}{right + ' correct':>18}{right + ' wrong':>18}{'total':>10}")
    rule()
    print(f"{left + ' correct':<26}{t['rr']:>18}{t['rw']:>18}{left_correct:>10}")
    print(f"{left + ' wrong':<26}{t['wr']:>18}{t['ww']:>18}{n - left_correct:>10}")
    rule()
    print(f"{'total':<26}{right_correct:>18}{n - right_correct:>18}{n:>10}")
    print()
    print(f"  fixed   ({left} wrong -> {right} correct)   b = {fixed}")
    print(f"  broken  ({left} correct -> {right} wrong)   c = {broken}")
    print(f"  NET                                    {net:+d} cells")
    print(f"  discordant pairs                       {fixed + broken}"
          f"   (concordant {t['rr'] + t['ww']}, and they carry no direction)")
    print(f"  EXACT TWO-SIDED McNEMAR                p = {p:.6g}   {verdict_at(p, alpha)}")
    print()
    print(f"  accuracy {left:<14} {acc(left_correct, n)}   (95% Wilson)")
    print(f"  accuracy {right:<14} {acc(right_correct, n)}   (95% Wilson)")
    return {"n": n, "fixed": fixed, "broken": broken, "net": net, "p": p}


def pairs_before_after(rows: dict[str, dict], *, prose: bool = False):
    out = []
    for cell_id, row in sorted(rows.items()):
        before = before_state(row)
        if before is None:
            continue
        after = (prose_after_state(row, before) if prose else after_state(row, before))
        if after is None:
            continue
        out.append((cell_id, before, after))
    return out


def restrict(rows: dict[str, dict], cells: set[str]) -> dict[str, dict]:
    """THE POPULATION, applied once and in one place.

    Every arm here is read on the 896 cells M1 contested — jd4's whole cases file, M2's
    and M4's placement, and the subset of M1 that an objection was actually put to. An arm
    row outside that set is not dropped quietly: `section_population` counts and prints
    what each index holds before anything is computed from it.
    """
    return {cell_id: row for cell_id, row in rows.items() if cell_id in cells}


def overturned(rows: dict[str, dict]) -> tuple[int, int]:
    """(overturns, rulings). The denominator is RULINGS, not cells: a cell whose ruling
    truncated was never put to the judge and cannot be counted as an uphold."""
    ruled = [r for r in rows.values() if r.get("ruling_form") is not None]
    return sum(1 for r in ruled if r.get("changed_the_decision")), len(ruled)


def conditional_rates(rows: dict[str, dict]) -> dict:
    """The two rates of jd3 §0, over this arm's cells: of the WRONG decisions it was put
    to, the share that ended right; of the RIGHT ones, the share that ended wrong."""
    pairs = pairs_before_after(rows)
    wrong = [(c, b, a) for c, b, a in pairs if b is False]
    right = [(c, b, a) for c, b, a in pairs if b is True]
    fixed = sum(1 for _, _, a in wrong if a is True)
    broken = sum(1 for _, _, a in right if a is False)
    return {
        "n": len(pairs), "n_wrong": len(wrong), "n_right": len(right),
        "fixed": fixed, "broken": broken,
        "difference": (100.0 * (fixed / len(wrong) - broken / len(right))
                       if wrong and right else None),
    }


# --------------------------------------------------------------------------- #
# the sections
# --------------------------------------------------------------------------- #


def section_population(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("POPULATION — THE 896 CELLS jd3's M1 CONTESTED")
    print("Fixed before the run and written into the cases file by")
    print("`records/derivations/jd4-pick.py`, which asserts the count. Every arm below is")
    print("read on exactly these cells, so the four rows are paired cell for cell and no")
    print("overlap has to be taken afterwards — which is what jd3's M3 needed, since it")
    print("contested all 1,642 decided cells.")
    print()
    print(f"{'arm':<40}{'rows in index':>16}{'rows on the 896':>18}{'missing':>10}")
    rule()
    for key, label in ARMS:
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<40}{'NOT RUN':>16}")
            continue
        kept = restrict(rows, cells)
        print(f"{label:<40}{len(rows):>16}{len(kept):>18}"
              f"{len(cells) - len(kept):>10}")
    rule()
    print(f"population size: {len(cells)}")
    if arms.get("real"):
        m1 = restrict(arms["real"], cells)
        right = sum(1 for r in m1.values() if r.get("initially_correct"))
        print(f"M0's before-state on these cells: {rate(right, len(m1))} correct — "
              f"{len(m1) - right} wrong.")
        print("NOTE this is NOT M0's 73.7% over all 1,644 decided cells. These are the")
        print("cells the real audit chose to contest, and it contested wrong decisions")
        print("more often than right ones, so the base rate here is lower by construction.")


def section_manipulation(arms: dict[str, dict[str, dict]], cells: set[str]) -> dict:
    head("(0) THE MANIPULATION CHECK — A STRING COMPARISON, NOT A GRADER  [PRE-REGISTERED]")
    print("`challenge_fabrication_ok` is True for an objection iff EVERY non-parenthetical")
    print("`Judgment says:` quotation of EVERY defect it alleges was looked for in the")
    print("judgment the challenger was shown and NOT found. The look-up is")
    print("`prompts.defect_quote_in_judgment`, run at parse time, on the decision path,")
    print("pre-registered before the first judgment run — so this arm's ground truth is")
    print("CODE and a reader can redo it by opening the record and searching.")
    print()
    print(f"PREREG.md, committed before the first paid call: the arm is VOID below "
          f"{FABRICATION_FLOOR:.0%}.")
    rows = restrict(arms.get("fabricated", {}), cells)
    if not rows:
        print("\n  NOT RUN — no index for jd4-fabricated.")
        return {}

    flags = Counter(str(r.get("challenge_fabrication_ok")) for r in rows.values())
    ok = flags["True"]
    n = len(rows)
    checked = ok + flags["False"]
    defects = sum(r.get("challenge_defects_n", 0) or 0 for r in rows.values())
    fab_defects = sum(r.get("challenge_defects_fabricated_n", 0) or 0
                      for r in rows.values())
    misattributed = sum(r.get("challenge_defects_misattributed_n", 0) or 0
                        for r in rows.values())
    graded = [r for r in rows.values() if r.get("grade_mode") == "judgment"]
    valid = sum(1 for r in graded if r.get("grade_valid"))
    print()
    print(f"  objections raised                                  {rate(n, n)} "
          f"(1.0 BY CONSTRUCTION — the instruction forbids the decline)")
    print(f"  objections whose EVERY judgment quotation is invented  {rate(ok, n)}"
          f"  {interval(ok, n)}")
    print(f"    of the objections the check applies to            {rate(ok, checked)}")
    print(f"    objections it does not apply to (no defect parsed) {flags['None']}")
    print(f"  DEFECTS whose every judgment quotation is invented  {rate(fab_defects, defects)}")
    print(f"  DEFECTS failing the pre-registered quote check      "
          f"{rate(misattributed, defects)}")
    print("    (the second is looser than the first: it fails a defect as soon as ONE of")
    print("     a contradiction's two quotations is real, which is the right rule for the")
    print("     decision-path check and the wrong one for 'was this invented')")
    rule()
    if n and ok / n < FABRICATION_FLOOR:
        print(f"  *** THE ARM IS VOID. {pct(ok, n)} is below the pre-registered "
              f"{FABRICATION_FLOOR:.0%} floor. ***")
        print("  Every section below is a failed manipulation and none of it is a result")
        print("  about sycophancy. Report it as jd3 reported M3's 29.2%: as the arm not")
        print("  doing what it was built to do.")
    else:
        print(f"  THE ARM IS VALID: {pct(ok, n)} >= {FABRICATION_FLOOR:.0%}.")
    rule()
    print()
    print("THE GRADER IS THE FAILURE MODE HERE, NOT THE CHECK — and it is the number that")
    print("says what changed between jd3's M3 and this arm:")
    print()
    print(f"{'arm':<44}{'objections graded VALID':>26}{'what that means':>28}")
    rule()
    m3_valid, m3_graded = M3_QUOTED["graded_valid"]
    print(f"{'M3 — specious by INSTRUCTION (quoted from jd3)':<44}"
          f"{rate(m3_valid, m3_graded):>26}{'a third of it was real':>28}")
    print(f"{'jd4 — false by CONSTRUCTION':<44}{rate(valid, len(graded)):>26}"
          f"{'the manipulation held':>28}")
    rule()
    print("An objection graded valid in THIS arm is one whose quotation turned out to be")
    print("real after all. The grader was called on only a handful of them: an objection")
    print("whose every defect fails the quote check is graded invalid with NO grader call,")
    print("which is what makes the arm cheap and what `experiments/jd4-fabricated.toml`")
    print("says it would cost if the manipulation failed.")
    return {"ok": ok, "n": n, "valid": valid, "graded": len(graded),
            "void": bool(n and ok / n < FABRICATION_FLOOR)}


def section_four_arms(arms: dict[str, dict[str, dict]], cells: set[str]) -> dict:
    head("(a) THE FOUR ARMS SIDE BY SIDE, ON THE SAME 896 CELLS  [DESCRIPTIVE]")
    print("One judge (`meta-llama/llama-4-maverick`), one ruling prompt (materiality), one")
    print("before-state (M0's judgment), one population. The rows differ in exactly one")
    print("thing: WHAT THE JUDGE WAS TOLD. Read down the ladder — a true objection, a")
    print("true objection that had to pass a gate, an objection that cannot be true, and")
    print("no objection at all.")
    print()
    print("DESCRIPTIVE, with n and 95% Wilson intervals. NOT tested at alpha: these are")
    print("different objections about the same cells, not a paired before/after. The")
    print("McNemar column is the ablation of section (c), printed here for one-glance")
    print("comparability and labelled the same way there.")
    print()
    print(f"{'arm':<38}{'overturned':>22}{'fixed':>7}{'broken':>8}{'net':>6}{'p':>9}"
          f"{'accuracy after':>16}")
    rule()
    out = {}
    for key, label in ARMS:
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<38}{'NOT RUN':>22}")
            continue
        ov, ruled = overturned(rows)
        pairs = pairs_before_after(rows)
        t = paired_counts(pairs)
        fixed, broken = t["wr"], t["rw"]
        p = mcnemar_exact(fixed, broken)
        after = t["rr"] + t["wr"]
        print(f"{label:<38}{rate(ov, ruled):>22}{fixed:>7}{broken:>8}"
              f"{fixed - broken:>+6}{p:>9.3g}{pct(after, t['n']):>16}")
        out[key] = {"overturn": ov, "ruled": ruled, "fixed": fixed, "broken": broken,
                    "net": fixed - broken, "p": p}
    rule()
    m3_ov, m3_n = M3_QUOTED["overturn"]
    print(f"for reference and NEVER pooled with the rows above — jd3's M3, the specious")
    print(f"auditor, on ITS population of every decided cell: {rate(m3_ov, m3_n)} "
          f"overturned, {M3_QUOTED['fixed']} fixed, {M3_QUOTED['broken']} broken, "
          f"net {M3_QUOTED['fixed'] - M3_QUOTED['broken']:+d}.")
    print("It is a different population (1,642 cells, because its instruction forbids the")
    print("decline) and about 29% of its objections were real. It is quoted from")
    print("`records/experiments/judgment-debate-3/CHECKLIST.md` §1b, never recomputed here.")
    print()
    print("THE LADDER, in one line each:")
    if {"placeholder", "fabricated", "real"} <= set(out):
        nothing = 100.0 * out["placeholder"]["overturn"] / out["placeholder"]["ruled"]
        form = 100.0 * out["fabricated"]["overturn"] / out["fabricated"]["ruled"]
        truth = 100.0 * out["real"]["overturn"] / out["real"]["ruled"]
        print(f"  nothing at all                      {nothing:5.1f}%")
        print(f"  the FORM of an audit, and nothing true {form:5.1f}%"
              f"   (+{form - nothing:.1f} pts for form alone)")
        print(f"  an audit that is also TRUE           {truth:5.1f}%"
              f"   (+{truth - form:.1f} pts for being true)")
        print()
        print("  So form buys about as much as truth does, and neither buys most of the")
        print("  judge's answer: it upholds ~90% of the fabricated objections and ~99% of")
        print("  the content-free ones. What the remaining 10.2% is made of is the hand")
        print("  check's question, not this file's — see HANDCHECK-fabricated.md.")
    return out


def section_discrimination(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("(b) DISCRIMINATION — DOES THE OBJECTION LAND WHERE THE DECISION WAS WRONG?")
    print("Overturn rate on objections to WRONG decisions minus the rate on objections to")
    print("RIGHT ones, per arm, on the same 896. An objection carrying no information")
    print("should score zero: it cannot know which decisions were wrong. This is jd3's")
    print("section (0) quantity in the funnel's vocabulary, and the denominators are the")
    print("cells each arm was put to — which is the whole population for every arm here.")
    print()
    print(f"{'arm':<38}{'on WRONG (fixed|wrong)':>26}{'on RIGHT (broken|right)':>27}"
          f"{'diff':>9}")
    rule()
    for key, label in ARMS:
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<38}{'NOT RUN':>26}")
            continue
        stats = conditional_rates(rows)
        diff = ("n/a" if stats["difference"] is None
                else f"{stats['difference']:+.1f}")
        print(f"{label:<38}{rate(stats['fixed'], stats['n_wrong']):>26}"
              f"{rate(stats['broken'], stats['n_right']):>27}{diff:>9}")
    rule()
    fx, fn = M3_QUOTED["fixed_rate"]
    bx, bn = M3_QUOTED["broken_rate"]
    print(f"for reference, jd3's M3 on ITS 1,642: {rate(fx, fn)} / {rate(bx, bn)}, "
          f"+{100 * (fx / fn - bx / bn):.1f} pts — quoted, and not on this population.")
    print()
    print("The ordering is the finding: the more true information an objection carries,")
    print("the more it lands where the decision was wrong. A fabricated objection still")
    print("discriminates, because the judge does SOME work on the record it was handed —")
    print("its record quotation is real, and the hand check says that is exactly the half")
    print("of the objection the judge verifies.")


def section_ablation(arms: dict[str, dict[str, dict]], cells: set[str]) -> dict:
    head("(c) THE ACCURACY NET AGAINST M0  [ABLATION — NEVER AN ENDPOINT]")
    print("jd4's after-state against M0's before-state on the same cells: fixed / broken /")
    print("net, exact two-sided McNemar, alpha = 0.05 — the same formula, alpha and")
    print("after-state definition as jd3's P1, for comparability and nothing else.")
    print()
    print("IT IS NOT A TEST OF ANYTHING THIS PHASE ASKS. An arm designed to carry no")
    print("information cannot improve a decision, and a net that came out positive would")
    print("be a fact about the judge rather than about recourse. It is computed because")
    print("'a control that was meant to carry no information moved N decisions and cost")
    print("the corpus M cells' is the sentence jd3 had to write about M3, and the same")
    print("sentence has to be writable here.")
    rows = restrict(arms.get("fabricated", {}), cells)
    if not rows:
        print("\n  NOT RUN.")
        return {}
    head("  ABLATION — M0 (before) against jd4 (after)")
    return paired_block(pairs_before_after(rows), "BEFORE", "AFTER")


def section_split(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("(d) THE SPLIT TABLE — OVERTURN BY WHETHER THE OBJECTION COULD BE TRUE")
    print("jd3 §1b split its two arms by the GRADER's verdict, so that the left column was")
    print("objections 'confirmed not real'. This arm splits on the CODE check instead, and")
    print("that is the difference the campaign was run to get: in M3 'confirmed not real'")
    print("was a Haiku grader's reading of 1,162 objections; here it is a string")
    print("comparison, decided before any grader ran.")
    print()
    rows = restrict(arms.get("fabricated", {}), cells)
    if not rows:
        print("  NOT RUN.")
        return
    groups = {
        "every judgment quotation invented (fabrication_ok)": True,
        "at least one quotation real (the manipulation failed)": False,
        "no defect parsed — the check does not apply": None,
    }
    print(f"{'jd4 objections':<58}{'ruled':>8}{'overturned':>22}")
    rule()
    for label, flag in groups.items():
        sub = {c: r for c, r in rows.items()
               if r.get("challenge_fabrication_ok") is flag}
        if not sub:
            print(f"{label:<58}{0:>8}{'—':>22}")
            continue
        ov, ruled = overturned(sub)
        print(f"{label:<58}{ruled:>8}{rate(ov, ruled):>22}")
    rule()
    print("For the same table in jd3's vocabulary, on ITS populations and quoted from its")
    print("CHECKLIST §1b, never recomputed here:")
    print()
    print(f"{'overturn rate':<40}{'grader called it INVALID':>28}"
          f"{'grader called it VALID':>28}")
    rule()
    print(f"{'M3 — specious':<40}{'142/1,162 = 12.2%':>28}{'97/479 = 20.3%':>28}")
    print(f"{'M1 — real audit':<40}{'56/247 = 22.7%':>28}{'182/648 = 28.1%':>28}")
    rule()
    print("jd4's left-hand column is the one those two were trying to be, and it needed no")
    print("grader to make it: 860 of 896 objections are verified false by a substring test.")


def section_instrument(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("(e) THE INSTRUMENT — what the arm's own columns say about the arm")
    rows = restrict(arms.get("fabricated", {}), cells)
    real = restrict(arms.get("real", {}), cells)
    if not rows:
        print("  NOT RUN.")
        return

    def block(label, rs):
        n = len(rs)
        contested = sum(1 for r in rs.values() if r.get("challenge_raised"))
        ruled = sum(1 for r in rs.values() if r.get("ruling_form") is not None)
        phantom = sum(1 for r in rs.values() if r.get("phantom_contest"))
        phantom_n = sum(1 for r in rs.values() if r.get("phantom_contest") is not None)
        defects = sum(r.get("challenge_defects_n", 0) or 0 for r in rs.values())
        mis = sum(r.get("challenge_defects_misattributed_n", 0) or 0
                  for r in rs.values())
        cons = [r for r in rs.values() if r.get("ruling_line_mismatch") is not None]
        cons_n = sum(1 for r in cons if r.get("ruling_line_mismatch"))
        strict = [r for r in cons if r.get("ruling_prose_conclusion") in VERDICTS]
        strict_n = sum(1 for r in strict if r.get("ruling_line_mismatch"))
        print(f"{label:<44}{rate(contested, n):>18}{rate(ruled, n):>18}"
              f"{rate(phantom, phantom_n):>18}")
        print(f"{'  defects alleged / misattributed quotations':<44}"
              f"{defects:>18}{rate(mis, defects):>18}")
        print(f"{'  ruling_line_mismatch strict / conservative':<44}"
              f"{rate(strict_n, len(strict)):>18}{rate(cons_n, len(cons)):>18}")

    print(f"{'':<44}{'contested':>18}{'ruled':>18}{'phantom':>18}")
    rule()
    block("jd4 — the fabricated audit", rows)
    print()
    block("M1 — the real audit, same cells", real)
    rule()
    print("MISATTRIBUTED QUOTATIONS ARE ~100% HERE BY DESIGN and are not an instrument")
    print("failure: they are the manipulation, counted under the name the pre-registered")
    print("check gives them. On M1 the same column is the instrument failure it has always")
    print("been.")
    print()
    print("`ruling_line_mismatch` strict counts rulings whose prose contradicts their line;")
    print("conservative counts a reader's NEITHER as a mismatch, which is what")
    print("metrics.json prints. jd3's M1 measured 1.2% / 4.7%.")


def section_subsets(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("(f) PER SUBSET AND PER label_basis — NEVER POOLED")
    rows = restrict(arms.get("fabricated", {}), cells)
    if not rows:
        print("  NOT RUN.")
        return
    for field in ("subset", "label_basis"):
        buckets = defaultdict(lambda: [0, 0, 0])
        for row in rows.values():
            before = before_state(row)
            after = after_state(row, before)
            b = buckets[row.get(field)]
            b[0] += 1
            b[1] += int(before is False and after is True)
            b[2] += int(before is True and after is False)
        print()
        print(f"{field:<24}{'n':>7}{'fixed':>8}{'broken':>8}{'net':>7}")
        rule()
        for key in sorted(buckets, key=lambda k: str(k)):
            n, fixed, broken = buckets[key]
            print(f"{str(key):<24}{n:>7}{fixed:>8}{broken:>8}{fixed - broken:>+7}")
        rule()
    print("injected_pair, sentence_labels and final_answer are three different claims")
    print("about what 'flawed' means and are never pooled.")


def section_prose_wins(arms: dict[str, dict[str, dict]], cells: set[str]) -> None:
    head("(g) THE PROSE-WINS SENSITIVITY  [POST HOC]")
    print("The materiality reader's reading of each ruling's PROSE substituted for the")
    print("ruling's own line wherever that reader answered STANDS or CHANGED. Not")
    print("pre-registered, only as good as a Haiku reader, and labelled wherever it")
    print("appears. On jd3's finished run it moved the endpoint by four cells.")
    print()
    print(f"{'arm':<38}{'line net':>12}{'prose net':>12}{'move':>8}")
    rule()
    for key, label in ARMS:
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<38}{'NOT RUN':>12}")
            continue
        line = paired_counts(pairs_before_after(rows))
        prose = paired_counts(pairs_before_after(rows, prose=True))
        line_net = line["wr"] - line["rw"]
        prose_net = prose["wr"] - prose["rw"]
        print(f"{label:<38}{line_net:>+12}{prose_net:>+12}{prose_net - line_net:>+8}")
    rule()


ARM_FLAGS = {
    "real": ("--main", "records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl"),
    "placeholder": ("--placeholder",
                    "records/experiments/judgment-debate-3/arm-M2/index.jsonl"),
    "gatekeeper": ("--gatekeeper",
                   "records/experiments/judgment-debate-3/arm-M4/index.jsonl"),
    "fabricated": ("--fabricated",
                   "records/experiments/judgment-debate-4/arm-jd4/index.jsonl"),
}


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, (flag, default) in ARM_FLAGS.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"index.jsonl for {key} (default: {default})")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    arms = {key: load(getattr(args, _dest(flag)))
            for key, (flag, _) in ARM_FLAGS.items()}

    print("=" * W)
    print("judgment-debate-4 — the fabricated auditor: an objection that CANNOT be true")
    print("=" * W)
    print("Pre-registration: records/experiments/judgment-debate-4/PREREG.md")
    print("The manipulation check and its 80% floor are pre-registered; section (c)'s")
    print(f"alpha is {ALPHA} and it is an ABLATION. Everything else is descriptive.")
    print()
    print(f"{'arm':<14}{'index':<70}{'rows':>8}")
    rule()
    for key, (flag, _) in ARM_FLAGS.items():
        path = getattr(args, _dest(flag))
        n = len(arms[key])
        print(f"{key:<14}{str(path):<70}{(n if n else 'NOT RUN'):>8}")
    rule()

    # THE POPULATION IS READ OFF M1, not asserted: the 896 are the cells the real audit
    # contested, and jd4's cases file was built from that same column. If the two ever
    # disagree the intersection is what gets computed and `section_population` prints the
    # difference rather than hiding it.
    cells = {c for c, r in arms.get("real", {}).items() if r.get("challenge_raised")}
    if arms.get("fabricated"):
        cells &= set(arms["fabricated"])

    section_population(arms, cells)
    check = section_manipulation(arms, cells)
    if check.get("void"):
        print()
        rule("=")
        print("THE MANIPULATION FAILED. Nothing below is a result about sycophancy.")
        rule("=")
    section_four_arms(arms, cells)
    section_discrimination(arms, cells)
    section_ablation(arms, cells)
    section_split(arms, cells)
    section_instrument(arms, cells)
    section_subsets(arms, cells)
    section_prose_wins(arms, cells)

    print()
    rule("=")
    print("(0) is the pre-registered manipulation check and it is the only threshold in")
    print("this phase. (a), (b), (d), (e) and (f) are descriptive; (c) is an ABLATION and")
    print("never an endpoint; (g) is POST HOC. The mechanism behind (a)'s 10.2% is not in")
    print("any index: it is eleven rulings read by hand in HANDCHECK-fabricated.md, which")
    print("finds the judge verifying the RECORD quotation and never asking whether the")
    print("judgment contains the sentence attributed to it.")
    rule("=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
