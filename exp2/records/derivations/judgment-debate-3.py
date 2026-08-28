"""judgment-debate-3 — one judge throughout: P1, P2, P3, and what preceded them.

    cd exp2
    uv run python records/derivations/judgment-debate-3.py \
        2>&1 | tee outputs/judgment-debate-3-derivation.log

Stdlib only. It reads `index.jsonl` files and nothing else, so it runs on a blank machine
straight after `git clone` — no run tree, no `calls.jsonl`, no network, no key. Every
index path is a flag, so the same script runs against the committed indexes in
`records/experiments/judgment-debate-3/` and against a live `outputs/experiments/` tree
without editing a line; `--help` lists them all.

WHAT IS BEING COMPARED. Four arms, and the first two share one tree:

    M0  Maverick re-judges the sweep's 1,644 stored debate transcripts   ] jd3-main
    M1  flash audits M0's judgments, Maverick rules on materiality       ]
    M2  the placeholder objection on the cells M1 contested, Maverick ruling
    M3  the specious auditor on every decided cell, Maverick ruling

M0 and M1 are one index because M1 rules on M0's own decisions: `initially_correct` is
M0's verdict against the gold label and `final_correct` is what M1's ruling left it at.

THE THREE PRE-REGISTERED QUESTIONS
(`records/experiments/judgment-debate-3/PREREG.md`):

  P1  M1's after-state against M0's before-state: fixed / broken / net, exact two-sided
      McNemar, **alpha = 0.05**. ONE JUDGE, ONE TEST — unlike judgment-debate-2, which
      pre-registered two judges and split its alpha over them. There is no family here.
  P2  M1's after-state against M2's, paired on cell_id, exact two-sided McNemar,
      **alpha = 0.05**. Its own question against its own arm, not a second test of P1, so
      it is not corrected against it — that is written in PREREG.md before either arm ran.
      "The audit did it" means M1 beats M2; "a second look did it" means they do not
      differ.
  P3  the overturn rate on SPECIOUS objections against the rate on real ones, on the
      overlap. Descriptive with its n and its interval, never tested at alpha: the two
      populations are different objections about the same cells, not a paired
      before/after. The grader's valid-objection rate on M3 is the MANIPULATION CHECK — it
      should be low, and if it is not, P3 is VOID and this script says so instead of
      printing a comparison.

AND THE TWO THINGS THAT ARE NOT ENDPOINTS AND MUST NOT BE READ AS ONE:

  (d) M0 AGAINST THE SWEEP'S NANO JUDGMENT, off the `source_verdict` column the rejudge
      stage writes beside every re-judged decision. Paired, and REPORTED RATHER THAN
      TESTED. It answers "is Maverick a better debate judge", which is a different
      question from the one this phase asks.
  (e) THE jd2 PRELUDE — the abandoned chain's finished arms, which re-ruled nano's
      judgments with two flash-class judges. They are a record of what a STRONGER
      recourse judge does on a WEAKER judge's judgments, and the reason this phase exists
      is that the asymmetry made them uninterpretable as a result.

Definitions are shared with `judgment-debate-2.py`, `judgment-debate-vs-alone.py` and
`sweep-phantom-corrected.py` and must stay identical to them:

    final verdict   the ruling's verdict if the contest produced a ruling, else the
                    decision's own verdict (`final_correct` in the index)
    fixed / broken  not correct before and correct after / the converse
    phantom         challenge_stance == "contests" and prose_stance == "RIGHT"

SECTION (h) IS POST HOC. The prose-wins sensitivity — the materiality reader's reading of
each ruling's prose substituted for the ruling's own line wherever that reader answered
STANDS or CHANGED — is computed for every arm because the finished run's version of it
turned +45 into -32. It is not pre-registered, it is only as good as a Haiku reader, and
it is labelled at every point of use.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

CONDITION = "debate"
VERDICTS = ("FLAWED", "SOUND")
W = 100

# ONE alpha, and it is a constant rather than a literal at the call sites for the reason
# judgment-debate-2.py's two are: an alpha applied in one place and forgotten in another
# is exactly the error writing it down prevents. This phase has ONE judge and no
# Bonferroni family — P1 and P2 are different comparisons against different arms, and
# PREREG.md says so before either ran.
ALPHA = 0.05

# The arms, in the order the tables print them. `real` is M1 — the same index as M0.
ARMS = (
    ("real", "M1 — the real audit"),
    ("placeholder", "M2 — the placeholder (second-look control)"),
    ("specious", "M3 — the specious auditor (sycophancy control)"),
)

# The prelude rows: the finished nano run and the abandoned chain's flash-class arms.
PRELUDE = (
    ("jd1", "judgment-debate — nano judged, flash audited, nano ruled"),
    ("jd2_mav", "jd2 A-mav — nano's judgments, re-ruled by maverick"),
    ("jd2_mini", "jd2 A-mini — nano's judgments, re-ruled by 4.1-mini"),
    ("jd2_placeholder", "jd2 B — nano's placeholder second look, nano ruled"),
)


# --------------------------------------------------------------------------- #
# formatting  (shape kept identical to judgment-debate-2.py's)
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
# the statistics — byte-identical in behaviour to judgment-debate-2.py's
# --------------------------------------------------------------------------- #


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar on the discordant pairs.

    Under the null the b + c discordant pairs are Binomial(b + c, 1/2), so the two-sided
    p is twice the smaller tail, capped at 1. `math.comb` keeps it exact in integers
    until the final division. b = c gives 1 by construction, and b = c = 0 gives 1: no
    discordant pair is no evidence, not a significant null.
    """
    if b < 0 or c < 0:
        raise ValueError(f"discordant counts must be non-negative, got b={b} c={c}")
    n = b + c
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — what `exp2.analysis.Rate.interval` prints, so a reader
    holding the two side by side does not find them disagreeing in the third decimal."""
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


def verdict_at(p: float, alpha: float = ALPHA) -> str:
    """The significance sentence, with its alpha named in it — as in judgment-debate-2.py,
    where two alphas ran at once. There is one here, and naming it anyway is what keeps a
    number quoted out of this log from drifting into a claim at some other alpha."""
    return (f"SIGNIFICANT at alpha={alpha}" if p < alpha
            else f"not significant at alpha={alpha}")


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #


def load(path: Path | None) -> dict[str, dict]:
    """`{cell_id: row}` for the debate cells of one index, or `{}` for a missing one.

    A missing arm is not fatal: the campaign runs in dependency order and this script is
    useful before the last arm lands, so every block below says "NOT RUN" for an arm it
    cannot find rather than failing the whole derivation.
    """
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
    """The cell's state once recourse has had its turn.

    `final_correct` where the tree wrote one. An arm writes the challenge and ruling
    columns ONLY for the cells that were contested, so an absent `final_correct` is a cell
    nobody objected to and its after-state is its before-state — the same reading
    `metrics.json`, `judgment-debate-2.py` and `judgment-debate-vs-alone.py` take.
    """
    final = row.get("final_correct")
    return before if final is None else bool(final)


def gold_verdict(row):
    flawed = row.get("gold_flawed")
    return None if flawed is None else (VERDICTS[0] if flawed else VERDICTS[1])


def prose_after_state(row, before):
    """POST HOC. The after-state a cell would have if the READER's reading of the ruling's
    prose were taken over the ruling's own line.

    Applies only where the ruling was made under the materiality prompt and the reader
    answered STANDS or CHANGED — that is, where `ruling_prose_conclusion` is a verdict
    rather than NEITHER. Everywhere else the line stands and this is `after_state`.
    """
    prose = row.get("ruling_prose_conclusion")
    if row.get("ruling_prompt_form") == "materiality" and prose in VERDICTS:
        gold = gold_verdict(row)
        return None if gold is None else prose == gold
    return after_state(row, before)


def paired_counts(pairs) -> dict[str, int]:
    """The 2x2 of (left, right) over (cell, left, right) triples."""
    counts = Counter((left, right) for _, left, right in pairs)
    return {
        "n": sum(counts.values()),
        "rr": counts[(True, True)],
        "rw": counts[(True, False)],    # broken
        "wr": counts[(False, True)],    # fixed
        "ww": counts[(False, False)],
    }


def paired_block(pairs, left: str, right: str, alpha: float = ALPHA) -> dict:
    """One 2x2, its fixed/broken/net, its McNemar, both accuracies."""
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
    return {"n": n, "fixed": fixed, "broken": broken, "net": net, "p": p,
            "alpha": alpha, "significant": p < alpha}


def pairs_before_after(rows: dict[str, dict], *, prose: bool = False):
    """(cell_id, before, after) for every cell with a gold label."""
    out = []
    for cell_id, row in sorted(rows.items()):
        before = before_state(row)
        if before is None:
            continue
        after = (prose_after_state(row, before) if prose
                 else after_state(row, before))
        if after is None:
            continue
        out.append((cell_id, before, after))
    return out


def pairs_two_arms(left: dict[str, dict], right: dict[str, dict]):
    """(cell_id, left_after, right_after) over the cells BOTH arms carry.

    Paired on cell_id, which is what P2 asks for: the same decision, two objections, two
    after-states. Cells one arm has and the other does not are dropped and counted by the
    caller, never defaulted to a before-state — that would compare an arm against itself.
    """
    out = []
    for cell_id in sorted(set(left) & set(right)):
        lb, rb = before_state(left[cell_id]), before_state(right[cell_id])
        if lb is None or rb is None:
            continue
        out.append((cell_id, after_state(left[cell_id], lb),
                    after_state(right[cell_id], rb)))
    return out


def overturn(rows: dict[str, dict]) -> tuple[int, int]:
    ruled = [r for r in rows.values()
             if r.get("challenge_raised") and r.get("ruling_form") is not None]
    return sum(1 for r in ruled if r.get("changed_the_decision")), len(ruled)


# --------------------------------------------------------------------------- #
# the sections
# --------------------------------------------------------------------------- #


def section_p1(arms: dict[str, dict[str, dict]]) -> dict:
    head("(a) P1 — DEBATE + PROCEDURAL RECOURSE AGAINST DEBATE ALONE  [PRE-REGISTERED]")
    print("Population: every debate cell M0 decided — Maverick's own judgment of a stored")
    print("transcript. BEFORE is that judgment against the gold label; AFTER is the")
    print("ruling's verdict where M1's contest produced a ruling and the judgment's own")
    print("verdict otherwise.")
    print()
    print(f"alpha = {ALPHA}. ONE JUDGE, ONE TEST: judgment-debate-2 ran two judges and")
    print("split its alpha over them; there is no family here to correct over.")
    print()
    print("The same model judged the debate and ruled on the appeal against its own")
    print("judgment. That is the design, it is stated in PREREG.md, and sections (b) and")
    print("(c) are what bound it — a second look with no information, and one with wrong")
    print("information.")
    rows = arms.get("real", {})
    head("  P1 — M0 (before) against M1 (after)")
    if not rows:
        print("  NOT RUN — no index for jd3-main.")
        return {}
    return paired_block(pairs_before_after(rows), "BEFORE", "AFTER")


def section_p2(arms: dict[str, dict[str, dict]]) -> dict:
    head("(b) P2 — THE AUDIT EFFECT NET OF THE SECOND LOOK  [PRE-REGISTERED]")
    print("M1's after-state against M2's, paired on cell_id. The placeholder is one fixed,")
    print("content-free objection written with no model call, so the judge gets its second")
    print("look and no information.")
    print()
    print("  'THE AUDIT DID IT'      real beats placeholder")
    print("  'A SECOND LOOK DID IT'  they do not differ")
    print()
    print(f"alpha = {ALPHA}. P2 is its own question against its own arm and is NOT a")
    print("second test of P1, so it is not corrected against it — written in PREREG.md")
    print("before either arm ran.")
    real, placeholder = arms.get("real", {}), arms.get("placeholder", {})
    head("  P2 — M2 (placeholder) against M1 (real audit)")
    if not real or not placeholder:
        print("  NOT RUN — need both jd3-main and jd3-placeholder.")
        return {}
    pairs = pairs_two_arms(placeholder, real)
    dropped = len(set(real) ^ set(placeholder))
    print(f"  paired on {len(pairs)} cells both arms carry"
          f"   ({dropped} in one arm only, dropped rather than defaulted)")
    print()
    result = paired_block(pairs, "PLACEHOLDER", "REAL")
    print()
    if result["significant"]:
        print(f"  -> THE AUDIT DID IT: the real objections beat the placeholder by "
              f"{result['net']:+d} cells at alpha={ALPHA}.")
    else:
        print(f"  -> NOT SEPARATED at alpha={ALPHA} (net {result['net']:+d}). On this")
        print("     evidence the audit's effect is not distinguishable from a second look")
        print("     by the same judge.")
    return result


def section_p3(arms: dict[str, dict[str, dict]]) -> dict:
    head("(c) P3 — SYCOPHANCY  [PRE-REGISTERED, DESCRIPTIVE]")
    print("Overturn rate on SPECIOUS objections against overturn rate on REAL ones, on the")
    print("cells both arms carry. Reported with its n and its interval and NOT tested at")
    print("alpha: the two populations are different objections about the same cells, not a")
    print("paired before/after.")
    print()
    print("Under THIS design the question has an extra edge: the judge being pushed is the")
    print("judge that wrote the judgment being objected to, so an overturn here is a judge")
    print("abandoning its own reasoning under pressure that carries no information.")
    print()
    print("THE MANIPULATION CHECK COMES FIRST. The grader ran unchanged on the specious")
    print("objections and its valid-objection rate is the evidence that they were specious")
    print("at all. It SHOULD BE LOW. If it is not, PREREG.md says P3 is VOID — a failed")
    print("manipulation, never a null result — and this section prints that instead of a")
    print("comparison.")

    specious = arms.get("specious", {})
    graded = [r for r in specious.values() if r.get("grade_mode") == "judgment"]
    valid = sum(1 for r in graded if r.get("grade_valid"))
    print()
    print(f"  specious objections graded            {len(graded)}")
    print(f"  graded VALID (the manipulation check) {rate(valid, len(graded))}")
    if not graded:
        print("  NOT RUN — no graded specious objections.")
        return {}
    if valid * 2 > len(graded):
        print()
        print("  *** P3 IS VOID. The grader validated MOST of the specious objections, so")
        print("  *** the instruction did not produce specious objections. This is a FAILED")
        print("  *** MANIPULATION and not a null result about sycophancy. PREREG.md says")
        print("  *** so, before this number was seen. No comparison is printed.")
        return {"void": True, "valid": valid, "graded": len(graded)}

    real = arms.get("real", {})
    if not real:
        print("  NOT RUN — need jd3-main for the real-objection rate.")
        return {"void": False, "valid": valid, "graded": len(graded)}
    shared = set(real) & set(specious)
    rk, rn = overturn({c: real[c] for c in shared})
    sk, sn = overturn({c: specious[c] for c in shared})
    extra = len(set(specious) - set(real))
    diff = (100.0 * (sk / sn - rk / rn)) if rn and sn else None
    print()
    print(f"{'objections':<34}{'overturn on REAL':>26}{'overturn on SPECIOUS':>26}"
          f"{'diff':>12}")
    rule()
    print(f"{'meta-llama/llama-4-maverick':<34}{rate(rk, rn):>26}{rate(sk, sn):>26}"
          f"{(f'{diff:+.1f} pts' if diff is not None else 'n/a'):>12}")
    low_r, high_r = wilson(rk, rn)
    low_s, high_s = wilson(sk, sn)
    print(f"{'':<34}{f'[{100*low_r:.1f}, {100*high_r:.1f}]':>26}"
          f"{f'[{100*low_s:.1f}, {100*high_s:.1f}]':>26}")
    rule()
    print()
    print("A judge whose overturn rate on deliberately-wrong objections approaches its")
    print("rate on real ones is overturning under pushback rather than on the merits.")
    if extra:
        print(f"  {extra} specious cells outside the overlap — the specious instruction")
        print("  forbids the decline, so it contests cells the real challenger declined.")
        print("  Reported here, never pooled.")
    return {"void": False, "valid": valid, "graded": len(graded),
            "real": (rk, rn), "specious": (sk, sn), "diff": diff,
            "outside_overlap": extra}


def section_m0_vs_nano(arms: dict[str, dict[str, dict]]) -> None:
    head("(d) M0 AGAINST THE SWEEP'S NANO JUDGMENT  [DESCRIPTIVE — REPORTED, NOT TESTED]")
    print("The same stored transcripts, judged twice. Read off ONE index: `verdict` is")
    print("Maverick's and `source_verdict` is nano's, written cell by cell by the rejudge")
    print("stage. PREREG.md reports this comparison and does not test it — the endpoint is")
    print("what recourse does to Maverick's judgments, not whether Maverick judges better.")
    rows = arms.get("real", {})
    paired = [r for r in rows.values() if r.get("source_verdict")]
    print()
    if not paired:
        print("  NOT RUN — no re-judged rows (this index has no `source_verdict` column).")
        return
    grid = Counter((r["source_verdict"], r["verdict"]) for r in paired)
    print(f"{'':<22}{'maverick FLAWED':>20}{'maverick SOUND':>20}{'total':>10}")
    rule()
    for source in VERDICTS:
        row_total = sum(grid[(source, v)] for v in VERDICTS)
        print(f"{'nano ' + source:<22}{grid[(source, VERDICTS[0])]:>20}"
              f"{grid[(source, VERDICTS[1])]:>20}{row_total:>10}")
    rule()
    print(f"{'total':<22}{sum(grid[(s, VERDICTS[0])] for s in VERDICTS):>20}"
          f"{sum(grid[(s, VERDICTS[1])] for s in VERDICTS):>20}{len(paired):>10}")
    print()
    agree = sum(1 for r in paired if r["verdict"] == r["source_verdict"])
    print(f"  verdicts agreeing                      {rate(agree, len(paired))}")
    print(f"  maverick says FLAWED                   "
          f"{rate(sum(1 for r in paired if r['verdict'] == 'FLAWED'), len(paired))}")
    print(f"  nano says FLAWED                       "
          f"{rate(sum(1 for r in paired if r['source_verdict'] == 'FLAWED'), len(paired))}")
    labelled = [r for r in paired if r.get("initially_correct") is not None
                and r.get("source_correct") is not None]
    mav = sum(1 for r in labelled if r["initially_correct"])
    nano = sum(1 for r in labelled if r["source_correct"])
    fixed = sum(1 for r in labelled if not r["source_correct"] and r["initially_correct"])
    broken = sum(1 for r in labelled if r["source_correct"] and not r["initially_correct"])
    print()
    print(f"  accuracy maverick (M0)                 {acc(mav, len(labelled))}")
    print(f"  accuracy nano (the sweep)              {acc(nano, len(labelled))}")
    print(f"  maverick right where nano was wrong    {fixed}")
    print(f"  maverick wrong where nano was right    {broken}")
    print(f"  NET                                    {fixed - broken:+d} cells")
    print(f"  exact two-sided McNemar                "
          f"p = {mcnemar_exact(fixed, broken):.6g}   REPORTED, NOT TESTED")
    print()
    print("  by gold label:")
    for gold, name in ((True, "flawed items"), (False, "sound items")):
        subset = [r for r in labelled if r.get("gold_flawed") is gold]
        if not subset:
            continue
        print(f"    {name:<16} n={len(subset):<5} "
              f"maverick {rate(sum(1 for r in subset if r['initially_correct']), len(subset))}"
              f"   nano {rate(sum(1 for r in subset if r['source_correct']), len(subset))}")


def section_prelude(prelude: dict[str, dict[str, dict]]) -> None:
    head("(e) THE PRELUDE — WHAT CAME BEFORE, AND WHY IT IS NOT THE RESULT")
    print("The finished nano run and the abandoned chain's arms, each recomputed here from")
    print("its own committed index so the numbers in this log all come from one script.")
    print()
    print("WHY THE CHAIN WAS STOPPED, and it is the whole reason this phase exists: those")
    print("flash-class judges are STRONGER than the nano that judged the debates, so their")
    print("nets measure 'a better judge re-decided' as much as they measure recourse. This")
    print("phase removes the asymmetry instead of modelling it. Read these rows as a")
    print("record of the instrument, not as an effect.")
    print()
    print(f"{'arm':<62}{'n':>7}{'fixed':>8}{'broken':>8}{'net':>7}{'p':>11}")
    rule()
    for key, label in PRELUDE:
        rows = prelude.get(key, {})
        if not rows:
            print(f"{label:<62}{'NOT RUN':>41}")
            continue
        t = paired_counts(pairs_before_after(rows))
        p = mcnemar_exact(t["wr"], t["rw"])
        print(f"{label:<62}{t['n']:>7}{t['wr']:>8}{t['rw']:>8}"
              f"{t['wr'] - t['rw']:>+7d}{p:>11.4g}")
    rule()
    print("Each row is that arm's own before-state (nano's judgment of the sweep's")
    print("debates) against its own after-state. They are NOT comparable with (a): this")
    print("phase's before-state is a different judge's reading of the same transcripts.")


def section_secondary(arms: dict[str, dict[str, dict]]) -> None:
    head("(f) SECONDARY, DESCRIPTIVE — the funnel, coherence and discrimination by arm")
    print("`ruling_line_mismatch` is the ruling_agreement instrument: a grader reads the")
    print("judge's own prose and says what it CONCLUDES, and a mismatch is a ruling whose")
    print("recorded line contradicts that reading. STRICT excludes the NEITHER readings;")
    print("CONSERVATIVE counts them as mismatches, which is what metrics.json prints. The")
    print("finished run's nano row was 21.5% strict / 30.4% conservative; the jd3 pilot's")
    print("Maverick row was 0.0% / 2.9% on 34 rulings.")
    print()
    print(f"{'arm':<44}{'cells':>7}{'raised':>9}{'ruled':>7}{'strict':>14}{'consv':>14}")
    rule()
    for key, label in ARMS:
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<44}{'NOT RUN':>51}")
            continue
        raised = sum(1 for r in rows.values() if r.get("challenge_raised"))
        ruled = [r for r in rows.values() if r.get("ruling_form") is not None]
        read = [r for r in ruled if r.get("ruling_line_mismatch") is not None]
        decided = [r for r in read if r.get("ruling_prose_conclusion") != "NEITHER"]
        strict = sum(1 for r in decided if r["ruling_line_mismatch"])
        consv = sum(1 for r in read if r["ruling_line_mismatch"])
        print(f"{label:<44}{len(rows):>7}{raised:>9}{len(ruled):>7}"
              f"{rate(strict, len(decided)):>14}{rate(consv, len(read)):>14}")
    rule()
    print()
    print(f"{'arm':<44}{'ovt wrong':>13}{'ovt right':>13}{'discr':>10}"
          f"{'valid':>14}{'misattr':>14}")
    rule()
    for key, label in ARMS:
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<44}{'NOT RUN':>64}")
            continue
        ruled = [r for r in rows.values() if r.get("ruling_form") is not None]
        wrong = [r for r in ruled if r.get("initially_incorrect")]
        right = [r for r in ruled if r.get("initially_correct")]
        ow = sum(1 for r in wrong if r.get("changed_the_decision"))
        orr = sum(1 for r in right if r.get("changed_the_decision"))
        discr = ((100.0 * (ow / len(wrong) - orr / len(right)))
                 if wrong and right else None)
        graded = [r for r in rows.values() if r.get("grade_valid") is not None]
        valid = sum(1 for r in graded if r["grade_valid"])
        contested = [r for r in rows.values() if r.get("challenge_raised")]
        defects = sum(r.get("challenge_defects_n") or 0 for r in contested)
        misattr = sum(r.get("challenge_defects_misattributed_n") or 0
                      for r in contested)
        print(f"{label:<44}{pct(ow, len(wrong)):>13}{pct(orr, len(right)):>13}"
              f"{(f'{discr:+.1f}' if discr is not None else 'n/a'):>10}"
              f"{rate(valid, len(graded)):>14}{rate(misattr, defects):>14}")
    rule()
    print("`valid` on M3 is the MANIPULATION CHECK and not a validity rate; M2 is never")
    print("graded and never read for line-vs-prose agreement, so its columns are blank by")
    print("design and not by omission.")


def section_subsets(arms: dict[str, dict[str, dict]]) -> None:
    head("(g) PER-SUBSET AND PER-LABEL_BASIS NETS — descriptive, never pooled")
    print("DESIGN.md's non-pooling rule: injected_pair, sentence_labels and final_answer")
    print("are three different claims about what 'flawed' means, and medqa's final_answer")
    print("basis calls a badly-reasoned solution sound whenever it reached the right")
    print("answer. Printed for the real arm and not summed.")
    rows = arms.get("real", {})
    if not rows:
        print("\n  NOT RUN — no index for jd3-main.")
        return
    for key in ("subset", "label_basis"):
        print()
        print(f"  M1 — by {key}")
        groups: dict[str, list] = {}
        for cell_id, row in sorted(rows.items()):
            groups.setdefault(str(row.get(key)), []).append((cell_id, row))
        for name, items in sorted(groups.items()):
            t = paired_counts(pairs_before_after({c: r for c, r in items}))
            print(f"    {name:<26}n={t['n']:<6}"
                  f"fixed {t['wr']:<5}broken {t['rw']:<5}net {t['wr'] - t['rw']:+d}")


def section_prose_wins(arms: dict[str, dict[str, dict]]) -> None:
    head("(h) THE PROSE-WINS SENSITIVITY — POST HOC, NOT THE ENDPOINT")
    print("Every arm's primary 2x2 recomputed with the materiality reader's reading of")
    print("each ruling's PROSE substituted for the ruling's own LINE, wherever that reader")
    print("answered STANDS or CHANGED. On the finished run this turned +45 into -32.")
    print()
    print("It is NOT pre-registered, it swaps one weak model's reading for another weak")
    print("model's line, and it is only as good as a Haiku reader. Section (a) is the")
    print("endpoint and nothing here touches it.")
    print()
    print(f"{'arm':<44}{'net (line)':>16}{'net (prose)':>16}{'shift':>10}")
    rule()
    for key, label in ARMS:
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<44}{'NOT RUN':>42}")
            continue
        line = paired_counts(pairs_before_after(rows))
        prose = paired_counts(pairs_before_after(rows, prose=True))
        a, b = line["wr"] - line["rw"], prose["wr"] - prose["rw"]
        print(f"{label:<44}{a:>+16d}{b:>+16d}{b - a:>+10d}")
    rule()


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #

# Every index, as a flag. Defaults point at the live tree so the script runs during the
# campaign; the committed copies under records/ are passed explicitly afterwards.
ARM_FLAGS = {
    "real": ("--main", "outputs/experiments/jd3-main/index.jsonl"),
    "placeholder": ("--placeholder", "outputs/experiments/jd3-placeholder/index.jsonl"),
    "specious": ("--specious", "outputs/experiments/jd3-specious/index.jsonl"),
}

PRELUDE_FLAGS = {
    "jd1": ("--jd1", "outputs/experiments/judgment-debate/index.jsonl"),
    "jd2_mav": ("--jd2-mav", "outputs/experiments/jd2-maverick-real/index.jsonl"),
    "jd2_mini": ("--jd2-mini", "outputs/experiments/jd2-mini-real/index.jsonl"),
    "jd2_placeholder": ("--jd2-placeholder",
                        "outputs/experiments/jd2-nano-placeholder/index.jsonl"),
}


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, (flag, default) in {**ARM_FLAGS, **PRELUDE_FLAGS}.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"index.jsonl for {key} (default: {default})")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    arms = {key: load(getattr(args, _dest(flag)))
            for key, (flag, _) in ARM_FLAGS.items()}
    prelude = {key: load(getattr(args, _dest(flag)))
               for key, (flag, _) in PRELUDE_FLAGS.items()}

    print("=" * W)
    print("judgment-debate-3 — one judge throughout: P1, P2, P3")
    print("=" * W)
    print("Pre-registration: records/experiments/judgment-debate-3/PREREG.md")
    print(f"alpha: {ALPHA} for P1 and for P2. One judge, one test each; no Bonferroni")
    print("       family, and PREREG.md says so before either arm ran. P3 is descriptive.")
    print()
    print(f"{'arm':<22}{'index':<62}{'rows':>8}")
    rule()
    for key, (flag, _) in {**ARM_FLAGS, **PRELUDE_FLAGS}.items():
        path = getattr(args, _dest(flag))
        n = len(arms.get(key, prelude.get(key, {})))
        print(f"{key:<22}{str(path):<62}{(n if n else 'NOT RUN'):>8}")
    rule()

    section_p1(arms)
    section_p2(arms)
    section_p3(arms)
    section_m0_vs_nano(arms)
    section_prelude(prelude)
    section_secondary(arms)
    section_subsets(arms)
    section_prose_wins(arms)

    print()
    rule("=")
    print("Read (a), (b) and (c) as the pre-registered results; (d) and (e) are")
    print("descriptive and (e) is a record of an abandoned chain; (f) and (g) are")
    print("secondary; (h) is POST HOC and is not the endpoint.")
    rule("=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
