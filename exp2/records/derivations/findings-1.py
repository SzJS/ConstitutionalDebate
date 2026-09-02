"""findings-1 — the DECOMPOSED judgment, and whether a local contest breaks fewer right
decisions than a whole-job objection.

    cd exp2
    uv run python records/derivations/findings-1.py \
        2>&1 | tee outputs/findings-1-derivation.log

Stdlib only. It reads `index.jsonl` files and two optional scan files and nothing else, so
it runs on a blank machine straight after `git clone` — no run tree, no `calls.jsonl`, no
network, no key. Every path is a flag, so the same script runs against the committed
indexes in `records/experiments/findings-1/` and against a live `outputs/experiments/`
tree without editing a line; `--help` lists them all. An index that is missing loads as
`{}` and its section prints NOT RUN rather than crashing.

The exact McNemar, the Wilson interval, the paired block, the conditional rates, the
population restriction and the loaders are IMPORTED from `judgment-debate-4.py` (through
`judgment-debate-5.py` and `judgment-debate-6.py`) rather than copied. This file prints
`fixed | wrong` and `broken | right` beside jd5-B's, in one write-up, on populations that
overlap cell for cell; a definition that drifted between the two files would be invisible.
Two statistics are NEW here and defined below because no earlier derivation needed them:
an exact ONE-SIDED Fisher test and a Newcombe (score) interval on a difference of two
independent proportions.

THE QUESTION. Every recourse arm so far (sweep, jd3, jd5, jd6) DISCRIMINATES — it fixes
40-54% of the wrong decisions it sees and breaks 20-36% of the right ones — and still nets
NEGATIVE, because the fix-to-break ratio never beats the prior odds that the decision was
right (`LLM_NOTES.md` §3ac: recourse does not lower accuracy iff `f / b >= a / (1 - a)`).
The user's hypothesis is that the challenger has to redo the judge's whole job. So the
judge DECOMPOSES its judgment into numbered FINDINGS — one per purported flaw the
FLAWED-side debater raised, each ruled FLAW / NOT A FLAW — and the verdict is derived by
code (FLAWED iff any finding is FLAW; an empty list is SOUND). Contesting then means
contesting a FINDING, an OMISSION or a CONTRADICTION: local, quoted, checkable.

    F-weak    findings judge = recourse judge = `meta-llama/llama-4-maverick`
    F-strong  findings judge = recourse judge = gpt-5.6-luna

THE ENDPOINTS, and they are `records/experiments/findings-1/PREREG.md`'s, fixed before the
first full-run call:

    P1  (per arm, alpha 0.05, two-sided) exact McNemar on before/after correctness.
    P2  (co-primary, F-weak only, ONE-SIDED alpha 0.05) among F-weak's contested, ruled,
        before-RIGHT cells, `broken | right` is BELOW jd5-B's 167/622 = 26.8%.
    P3  (reported, not tested) `fixed | wrong` at least jd5-B's 144/274 = 52.6%.

The registered claim for F-weak is the CONJUNCTION P1 and P2 (intersection-union, no
correction). F-strong's P1 is a separate family at its own alpha and is never pooled.

THE COMPARATOR IS THE EXISTENCE-CHECK ARM AND NOTHING ELSE. "jd5-B" throughout means
`jd5-recheck-real` (`records/experiments/judgment-debate-5/arm-real/`): M1's 896 real
objections re-ruled by Maverick under the ruling prompt WITH the existence check. jd3-M1's
40.1% / 20.6% — the same objections ruled WITHOUT the check — is not a comparator anywhere
in this campaign, because the findings ruling prompt carries that check. Its two rates are
RECOMPUTED from the committed index here rather than typed in, and then asserted against
167/622 and 144/274 in ONE place (`check_jd5b`), so a drift is loud instead of silent.

P2 IS UNPAIRED AND THE FILE SAYS SO EVERYWHERE. F-weak and jd5-B differ in the contest
object (a finding vs the whole judgment), the ruling prompt, the before-state (the findings
judge's own derived verdict vs M0's) and the routing. Fisher's exact test on the 2x2 is the
right shape — jd5-B's 622 are data with their own sampling error, not a fixed constant, and
a one-sample binomial against 26.8% would call a four-point drop significant that a fair
test calls borderline — but it compares two MECHANISMS and not two treatments of one cell.
The paired 2x2 on the intersection (right under both before-states, contested by both) is
printed beside it with its n and is DESCRIPTIVE.

THE ONE COLUMN THAT COULD SILENTLY INVERT A RESULT, and unlike jd6 it is the same in both
arms: every fd1 arm is a REJUDGE, so its row's `initially_correct` is THE FINDINGS JUDGE'S
OWN derived verdict — the before-state — and `source_correct` is jd3-M0's, carried in the
manifest. `final_correct` is the state after recourse, absent where nothing was ruled. M0
is read from ITS OWN index (`--m0`), where `verdict` / `initially_correct` are M0's
decision and `final_correct` is what jd3's M1 audit did to it — a column this file never
touches. `before_of` / `after_of` / `m0_of` below are the only three places that is handled.

Definitions shared with `judgment-debate-{3,4,5,6}.py` and they must stay identical:

    fixed / broken  not correct before and correct after / the converse
    overturn        the after-state verdict differs from the decision the arm was put to
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path

_JD6_PATH = Path(__file__).resolve().with_name("judgment-debate-6.py")
_spec = importlib.util.spec_from_file_location("judgment_debate_6", _JD6_PATH)
jd6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jd6)

# Re-exported so this module's readers do not have to know where they came from. They are
# the SAME objects, which is the point.
load = jd6.load
restrict = jd6.restrict
mcnemar_exact = jd6.mcnemar_exact
wilson = jd6.wilson
pct = jd6.pct
rate = jd6.rate
interval = jd6.interval
acc = jd6.acc
head = jd6.head
rule = jd6.rule
verdict_at = jd6.verdict_at
paired_block = jd6.paired_block
paired_counts = jd6.paired_counts
conditional_rates = jd6.jd5.conditional_rates
load_rows = jd6.load_rows
scan_attempts = jd6.scan_attempts
ALPHA = jd6.ALPHA
W = jd6.W
VERDICTS = jd6.VERDICTS

# THE COMPARATOR, and the only numbers in this file that are written down rather than
# computed. They are RECOMPUTED from `--jd5b` on every run and compared against these, so
# this dict is an assertion and not a source: if the committed index ever moves, the run
# stops with the old and the new numbers side by side instead of printing a table nobody
# can reconcile with §3aa. See `check_jd5b`.
JD5B_EXPECTED = {"broken": 167, "n_right": 622, "fixed": 144, "n_wrong": 274}
# Below this many rows the `--jd5b` index is not the committed 1,644-row arm — a test
# fixture, or a slice — and the assertion is SKIPPED with a printed note rather than
# failing. The published arm has 1,644 rows and 896 contested.
JD5B_COMMITTED_ROWS = 1000


# --------------------------------------------------------------------------- #
# the two statistics that are new here
# --------------------------------------------------------------------------- #


def fisher_one_sided(a: int, b: int, c: int, d: int, *, alternative: str = "less") -> float:
    """Exact ONE-SIDED Fisher test on the 2x2 `[[a, b], [c, d]]`, by the hypergeometric
    tail, with `math.comb` and nothing else.

        row 1   a   b      (F-weak:  broken, kept)
        row 2   c   d      (jd5-B:   broken, kept)

    Conditioning on both margins, the count in cell `a` is Hypergeometric(n = a+b+c+d,
    K = a+c, N = a+b), and

        P(X = k) = C(a+b, k) C(c+d, a+c-k) / C(n, a+c)

    ``alternative="less"`` returns `P(X <= a)` — the tail that answers "is row 1's share
    SMALLER than row 2's", which is P2's direction and the reason this file needs a
    one-sided test at all. ``"greater"`` returns `P(X >= a)`.

    WHY NOT THE ONE-SAMPLE BINOMIAL the questionnaire defaulted to: it treats jd5-B's
    26.8% as a known constant. It is 167 of 622 cells with its own sampling error, and
    pretending otherwise makes the test anti-conservative — a four-point drop comes back
    significant that a fair test calls borderline. `PREREG.md` §2 records the replacement.
    """
    if min(a, b, c, d) < 0:
        raise ValueError(f"cell counts must be non-negative, got {a} {b} {c} {d}")
    if alternative not in ("less", "greater"):
        raise ValueError(f"alternative must be 'less' or 'greater', got {alternative!r}")
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, col1 = a + b, a + c
    row2 = c + d
    total = math.comb(n, col1)
    if total == 0:
        return 1.0
    low = max(0, col1 - row2)
    high = min(row1, col1)
    span = range(low, a + 1) if alternative == "less" else range(a, high + 1)
    tail = sum(math.comb(row1, k) * math.comb(row2, col1 - k) for k in span)
    return min(1.0, tail / total)


def newcombe_diff(k1: int, n1: int, k2: int, n2: int,
                  z: float = 1.96) -> tuple[float, float]:
    """Newcombe's method-10 (score) interval for `p1 - p2`, two INDEPENDENT proportions.

    Wilson bounds `(l1, u1)` and `(l2, u2)` are taken on each proportion separately — the
    same `wilson` every other rate in this campaign is printed with — and

        lower = (p1 - p2) - sqrt( (p1 - l1)^2 + (u2 - p2)^2 )
        upper = (p1 - p2) + sqrt( (u1 - p1)^2 + (p2 - l2)^2 )

    It is used instead of a Wald interval for the same reason Wilson is used instead of
    Wald on a single rate: at the small counts P2's second denominator can reach, the Wald
    interval runs off the end of [-1, 1] and its coverage collapses. It is the interval
    that BELONGS beside a Fisher test on the same 2x2 — both condition on nothing about
    the true rates — and it is NOT a test: the Fisher p is the endpoint, this is the
    magnitude PREREG §2 asks to be reported with it.
    """
    p1 = k1 / n1 if n1 else 0.0
    p2 = k2 / n2 if n2 else 0.0
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    difference = p1 - p2
    lower = difference - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = difference + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def difference_interval(k1: int, n1: int, k2: int, n2: int) -> str:
    low, high = newcombe_diff(k1, n1, k2, n2)
    return f"[{100 * low:+.1f}, {100 * high:+.1f}]"


def rate_ci(k: int, n: int) -> str:
    """`k/n pct [low, high]`, and `k/0 n/a` with NO interval on an empty denominator.

    `wilson(0, 0)` returns the vacuous `(0, 1)` — correct, and unreadable printed as
    `[0.0, 100.0]` beside `0/0 n/a`, which reads as a measurement of nothing. The splits
    of section (4d) put several empty cells in one table, so the suppression lives here
    rather than at each call site.
    """
    return rate(k, n) if n == 0 else f"{rate(k, n)} {interval(k, n)}"


# --------------------------------------------------------------------------- #
# the columns, read in one place each
# --------------------------------------------------------------------------- #


def before_of(row: dict) -> bool | None:
    """The findings judge's OWN derived verdict, as correctness. Every fd1 arm is a
    rejudge, so this is the row's own `initially_correct` in both arms — unlike jd6, where
    the two arms kept their before-states in different columns."""
    return row.get("initially_correct")


def after_of(row: dict) -> bool | None:
    """The cell's state once recourse has had its turn. A cell nobody ruled on keeps the
    decision it had, which is `judgment-debate-4.py`'s `after_state` rule unchanged."""
    before = row.get("initially_correct")
    final = row.get("final_correct")
    return before if final is None else bool(final)


def m0_of(row: dict) -> bool | None:
    """jd3-M0's own decision on this cell, read off M0's OWN index row.

    In `records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl` the decision is M0's
    (`verdict`, `initially_correct`) and `final_correct` is what jd3's M1 audit did to it.
    This file wants the DECISION and never the audited state, so it reads
    `initially_correct` and nothing else out of that index. Reading `final_correct` there
    would compare the findings judge against M0-after-recourse, which is not a baseline
    anybody registered.
    """
    return row.get("initially_correct")


def m0_verdict_of(row: dict) -> str | None:
    return row.get("verdict")


def contested(row: dict) -> bool:
    return bool(row.get("challenge_raised"))


def was_ruled(row: dict) -> bool:
    """Whether a recourse judge actually ruled. A cell whose ruling truncated was never
    put to that judge and cannot be counted as an uphold — jd4's rule."""
    return row.get("ruling_form") is not None


def void_only(row: dict) -> bool | None:
    """Whether every contest in this objection was mechanically void.

    `challenge_void_only` is the column, added 2026-09-02. On an index written before it
    existed the same fact is derivable from the two counts, and that fallback is here
    rather than at three call sites. `None` means the objection carries no contest list at
    all, which is a different fact from "all of them were void".
    """
    explicit = row.get("challenge_void_only")
    if explicit is not None:
        return bool(explicit)
    total, void = row.get("challenge_contests_n"), row.get("challenge_contests_void_n")
    if total is None or void is None:
        return None
    return bool(total) and void == total


def well_formed(row: dict) -> bool:
    """Contested, and at least one contest survived the mechanical checks.

    PREREG §2's SECOND denominator. An objection made only of void contests — a quote that
    is in neither document, a "should be" equal to the ruling it contests, a contradiction
    alleged between a finding and itself — cannot break anything by construction, because
    `apply_contest_lines` ignores its ruling lines. Leaving such cells in the break-rate
    denominator makes the mechanism look safer than it is; dropping them silently makes it
    look worse. Both denominators are printed, always.
    """
    return contested(row) and void_only(row) is not True


def graded(row: dict) -> bool:
    return row.get("grade_mode") is not None


def stance_recorded(row: dict) -> bool:
    return row.get("challenge_stance") is not None


# --------------------------------------------------------------------------- #
# the comparator, recomputed and then asserted
# --------------------------------------------------------------------------- #


def arm_rates(rows: dict[str, dict], *, only=None) -> dict:
    """`fixed | wrong` and `broken | right` over these rows, on before/after correctness.

    ``only`` is a predicate on the row, applied BEFORE the split, so the same function
    serves the whole arm, the contested-and-ruled subset and the well-formed subset. It is
    `jd4.conditional_rates`' arithmetic with a filter — and it is asserted against that
    function in the tests, so the two cannot drift.
    """
    fixed = broken = n_wrong = n_right = 0
    for row in rows.values():
        if only is not None and not only(row):
            continue
        before, after = before_of(row), after_of(row)
        if before is None or after is None:
            continue
        if before:
            n_right += 1
            broken += not after
        else:
            n_wrong += 1
            fixed += after
    return {"fixed": fixed, "n_wrong": n_wrong, "broken": broken, "n_right": n_right,
            "n": n_wrong + n_right}


def jd5b_rates(rows: dict[str, dict], cells: set[str]) -> dict:
    """jd5-B's two rates over the cells IT was put to — its own contested set.

    Not the fd1 population: jd5-B ruled M1's 896 objections and its denominators are those
    896 cells' before-states. Restricting it to fd1's cells would silently change the
    comparator PREREG §0 names.
    """
    kept = {c: r for c, r in rows.items() if c in cells and contested(r) and was_ruled(r)}
    return arm_rates(kept)


def check_jd5b(stats: dict, n_rows: int) -> str:
    """ONE place where the comparator's published numbers are asserted.

    §3ac's table, `records/experiments/judgment-debate-5/CHECKLIST.md` and PREREG §0 all
    quote 52.6% and 26.8%. They are recomputed above from the committed index; if the
    recomputation ever stops matching, this raises with both sets of numbers rather than
    letting a write-up carry a rate nobody can reproduce. Skipped, loudly, when `--jd5b`
    points at something that is not the committed 1,644-row arm — a fixture, or a slice.
    """
    if n_rows < JD5B_COMMITTED_ROWS:
        return (f"NOTE: --jd5b holds {n_rows} rows, fewer than the committed arm's 1,644, "
                "so the 167/622 and 144/274 assertion is SKIPPED. Every jd5-B number "
                "below comes from the file that was given, not from the published arm.")
    got = {k: stats[k] for k in JD5B_EXPECTED}
    if got != JD5B_EXPECTED:
        raise AssertionError(
            "the jd5-B comparator has DRIFTED. PREREG.md §0, LLM_NOTES §3ac and "
            f"judgment-debate-5's CHECKLIST all quote {JD5B_EXPECTED}; this index gives "
            f"{got}. Nothing below is comparable to the published campaign until that is "
            "explained.")
    return (f"jd5-B recomputed from its index: broken {rate(stats['broken'], stats['n_right'])}"
            f", fixed {rate(stats['fixed'], stats['n_wrong'])} — matches the published "
            "26.8% and 52.6%.")


# --------------------------------------------------------------------------- #
# the identity of LLM_NOTES §3ac, as a row
# --------------------------------------------------------------------------- #


def identity_row(stats: dict) -> dict:
    """`a`, `f`, `b`, `f/b` and the break-even accuracy `a* = f / (f + b)`.

    §3ac's identity: recourse does not lower accuracy iff `f / b >= a / (1 - a)`, where
    `a` is the accuracy of the decisions the mechanism actually SEES, `f = P(fix | wrong)`
    and `b = P(break | right)`. Equivalently the mechanism hurts above the break-even
    accuracy `a* = f / (f + b)` — and `f` and `b` there are RATES, not counts, which is
    the one place this table is easy to get wrong.

    The derived verdict changes the base rate `a` and therefore moves P1's bar, which is
    why this row is printed for every arm beside jd5-B's rather than left to the write-up.
    """
    n_right, n_wrong = stats["n_right"], stats["n_wrong"]
    n = n_right + n_wrong
    a = n_right / n if n else None
    f = stats["fixed"] / n_wrong if n_wrong else None
    b = stats["broken"] / n_right if n_right else None
    ratio = (f / b) if (f is not None and b) else None
    breakeven = (f / (f + b)) if (f is not None and b is not None and (f + b)) else None
    odds = (a / (1 - a)) if (a is not None and a < 1) else None
    return {"n": n, "a": a, "f": f, "b": b, "f_over_b": ratio, "a_star": breakeven,
            "odds": odds, "net": stats["fixed"] - stats["broken"]}


def print_identity_header() -> None:
    print(f"{'mechanism':<40}{'n':>7}{'a':>9}{'f = fix|wrong':>16}"
          f"{'b = break|right':>18}{'f / b':>9}{'a* = f/(f+b)':>15}{'net':>8}")
    rule()


def print_identity_row(label: str, stats: dict) -> None:
    row = identity_row(stats)
    def show(value, suffix="%"):
        return "n/a" if value is None else f"{100 * value:.1f}{suffix}"
    ratio = "n/a" if row["f_over_b"] is None else f"{row['f_over_b']:.2f}"
    print(f"{label:<40}{row['n']:>7}{show(row['a']):>9}{show(row['f']):>16}"
          f"{show(row['b']):>18}{ratio:>9}"
          f"{show(row['a_star']):>15}{row['net']:>+8d}")


# --------------------------------------------------------------------------- #
# the named outcomes of PREREG §4
# --------------------------------------------------------------------------- #


def p1_reading(net: int, p: float, alpha: float = ALPHA) -> str:
    """POSITIVE / NEGATIVE / NULL, in PREREG §4's vocabulary and nobody else's.

    "POSITIVE" is a SIGNIFICANT gain, not a positive net: an arm that fixes three more
    than it breaks at p = 0.6 has shown nothing, and calling it positive is exactly the
    rounding PREREG §4's last sentence forbids.
    """
    if p >= alpha:
        return "NULL"
    return "POSITIVE" if net > 0 else "NEGATIVE"


def named_outcome(p1: str, p2_holds: bool | None) -> tuple[str, str]:
    """PREREG §4's four names, computed from P1's reading and P2's result.

    (A) P1 POSITIVE and P2 HOLDS       the first arm to net positive, by the hypothesised
                                       route: fewer right decisions broken
    (B) P2 HOLDS, P1 NULL or NEGATIVE  fewer broken and still not enough — `f/b` below
                                       `a/(1-a)`, reported with §3ac's identity
    (C) P1 POSITIVE, P2 NOT SHOWN      nets positive by the FIX side (P3), not the break
                                       side; the hypothesis is not what did it
    (D) neither

    A result that is none of these — and jd6 produced one — is REPORTED AS THE SPLIT IT IS
    and never rounded to the nearest name. That rule is PREREG §4's and is printed with
    the answer.
    """
    if p2_holds is None:
        return ("(not computable)",
                "P2 has no result, so no named outcome applies. This is what the file "
                "prints before F-weak has run, and it is not an error.")
    if p1 == "POSITIVE" and p2_holds:
        return ("(A)", "P1 POSITIVE and P2 HOLDS — the first arm to net positive, and by "
                       "the hypothesised route: the local contest breaks fewer right "
                       "decisions than the whole-job objection did.")
    if p2_holds:
        return ("(B)", f"P2 HOLDS and P1 is {p1} — fewer right decisions broken, and "
                       "still not enough: f/b stays below a/(1-a). Reported with the "
                       "identity, never as a win.")
    if p1 == "POSITIVE":
        return ("(C)", "P1 POSITIVE and P2 NOT SHOWN — the arm nets positive by the FIX "
                       "side (P3), not the break side. The decomposition helped; the "
                       "hypothesised mechanism is not what did it.")
    return ("(D)", f"NEITHER — P1 is {p1} and P2 is not shown. The decomposition did not "
                   "move the endpoint.")


# --------------------------------------------------------------------------- #
# the tree scan — the only thing here that needs a run tree
# --------------------------------------------------------------------------- #
#
# READ THIS BEFORE QUOTING THE SCAN. Two facts the index does not carry are needed by
# PREREG §3: the FORMAT REPAIRS at each of the four call sites, and per-contest VALIDITY
# BY KIND (the index carries only `grade_contests_valid_n`, an objection-level count).
# Both are read straight out of the stored artifacts — no regex, no model — and the scan
# is committed as `arm-<arm>/format-scan.jsonl` so the default invocation stays index-only
# and reproduces on a bare clone.


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scan_tree(tree: Path) -> list[dict]:
    """Per-cell repairs, parse modes and per-contest grades, off a finished arm tree.

    Walked by the DECISION run directory, so a cell that was decided and then lost its
    contest still appears with its judge columns — "the judge wrote a list and the
    challenger call failed" is a fact PREREG §6's loss rule needs, and a walk of
    `grade.json` would drop it.
    """
    rows = []
    for path in sorted(Path(tree).glob("cells/*/runs/*/verdict.json")):
        directory = path.parent
        if "parent" in path.parts:
            continue
        cell_id = str(path).split("/cells/")[1].split("/")[0]
        verdict = _read_json(path)
        findings = _read_json(directory / "findings.json")
        row = {
            "cell_id": cell_id,
            "judge_parse_mode": findings.get("parse_mode") or verdict.get("parse_mode"),
            "judge_repairs": verdict.get("repair_attempts"),
            "judge_finish_reason": verdict.get("finish_reason"),
            "findings_n": findings.get("n_findings"),
        }
        contests = sorted(Path(tree).glob(
            f"cells/{cell_id}/contests/*/runs/*/challenge.json"))
        if contests:
            contest = contests[-1].parent
            challenge = _read_json(contest / "challenge.json")
            ruling = _read_json(contest / "ruling.json")
            grade = _read_json(contest / "grade.json")
            row["challenge_parse_mode"] = challenge.get("parse_mode")
            row["challenge_repairs"] = challenge.get("repair_attempts")
            row["ruling_parse_mode"] = ruling.get("parse_mode") or None
            row["ruling_repairs"] = ruling.get("repair_attempts")
            row["grade_parse_mode"] = grade.get("parse_mode") or None
            # THE ONE THING ONLY THE SCAN HAS: validity per contest, with its kind and
            # whether the grade was mechanical. `grade_contests_valid_n` in the index is
            # an objection-level count and cannot be split by kind afterwards.
            row["grade_contests"] = [
                {"kind": entry.get("kind"), "valid": entry.get("valid"),
                 "mechanical": entry.get("mechanical")}
                for entry in (grade.get("contests") or [])]
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# (0) the losses and the format
# --------------------------------------------------------------------------- #


ARM_LABELS = {"weak": "F-weak  (Maverick, both roles)",
              "strong": "F-strong (luna, both roles)"}


def stage_counts(rows: dict[str, dict], population: set[str]) -> dict:
    """Attempted / decided / stance recorded / raised / ruled / graded, per PREREG §6.

    "Attempted" is the population — every cell jd3-M0 decided — because rejudge is offered
    every one of them and a cell that never reached the index was LOST at rejudge. That is
    the one count here that cannot be read off this arm's own index, which is why `--m0`
    is not optional in practice.
    """
    kept = restrict(rows, population)
    return {
        "attempted": len(population),
        "decided": len(kept),
        "stance": sum(1 for r in kept.values() if stance_recorded(r)),
        "raised": sum(1 for r in kept.values() if contested(r)),
        "agreed": sum(1 for r in kept.values() if r.get("challenge_agreed")),
        "declined": sum(1 for r in kept.values() if r.get("challenge_declined")),
        "unclear": sum(1 for r in kept.values() if r.get("challenge_unclear")),
        "ruled": sum(1 for r in kept.values() if contested(r) and was_ruled(r)),
        "graded": sum(1 for r in kept.values()
                      if contested(r) and was_ruled(r) and graded(r)),
        "well_formed": sum(1 for r in kept.values()
                           if contested(r) and was_ruled(r) and well_formed(r)),
    }


def _distribution(values: list[int]) -> str:
    if not values:
        return "no cell carries the column"
    values = sorted(values)
    return (f"min {values[0]}  median {values[len(values) // 2]}  max {values[-1]}  "
            f"mean {sum(values) / len(values):.2f}")


def section_losses(arms, population, m0, scans) -> None:
    head("(0) THE LOSSES, THE PARSE AND THE FORMAT  [DESCRIPTIVE — and PREREG §6's rule]")
    print("PREREG §6's missing-cell rule, applied stage by stage. A cell lost at REJUDGE has")
    print("no before-state and leaves every table (it is the numerator of the feasibility")
    print("rate, and it is NOT a SOUND verdict with an empty list); lost at CONTEST it has an")
    print("unknown stance and is not a decline; lost at RULING it was contested and has no")
    print("after-state, and it is never counted as an uphold; lost at GRADE or at the")
    print("instrument it stays in P1-P3 and leaves that table alone. A retried cell is a")
    print("DIFFERENT DRAW and is never folded into a denominator.")
    print()
    print(f"{'arm':<34}{'attempted':>11}{'decided':>9}{'stance':>8}{'raised':>8}"
          f"{'ruled':>7}{'graded':>8}{'well-formed':>13}")
    rule()
    for key in ("weak", "strong"):
        rows = arms.get(key, {})
        if not rows:
            print(f"{ARM_LABELS[key]:<34}{'NOT RUN':>11}")
            continue
        got = stage_counts(rows, population)
        print(f"{ARM_LABELS[key]:<34}{got['attempted']:>11}{got['decided']:>9}"
              f"{got['stance']:>8}{got['raised']:>8}{got['ruled']:>7}"
              f"{got['graded']:>8}{got['well_formed']:>13}")
    rule()
    print(f"population: {len(population)} cells "
          + ("(jd3-M0's decided debate cells, read from --m0)" if m0
             else "(taken from the arms themselves — --m0 is missing)"))
    print()
    for key in ("weak", "strong"):
        rows = arms.get(key, {})
        if not rows:
            continue
        got = stage_counts(rows, population)
        kept = restrict(rows, population)
        print(f"  {ARM_LABELS[key]}")
        print(f"    lost at rejudge   {got['attempted'] - got['decided']:>5}"
              "   (no before-state; leaves every table)")
        print(f"    lost at contest   {got['decided'] - got['stance']:>5}"
              "   (unknown stance, and NOT a decline)")
        print(f"    lost at ruling    {got['raised'] - got['ruled']:>5}"
              "   (contested, no after-state; never an uphold)")
        print(f"    lost at grade     {got['ruled'] - got['graded']:>5}"
              "   (stays in P1-P3, leaves the validity table)")
        print(f"    stances           contests {got['raised']}, agrees {got['agreed']}, "
              f"declines {got['declined']}, unclear {got['unclear']}")
        missing = sorted(population - set(kept))
        if missing and m0:
            by_subset = Counter(m0[c].get("subset") for c in missing if c in m0)
            print(f"    REJUDGE LOSSES BY SUBSET  {dict(by_subset)}")
            print("      (the feasibility rate's numerator; a subset that loses "
                  "disproportionately is a fact about the format, not the sample)")
        elif not missing:
            print("    REJUDGE LOSSES BY SUBSET  none — every cell in the population "
                  "reached the index")
        print()

    head("  THE PARSE AND THE FORMAT, PER ARM  [the feasibility gate's own columns]")
    print("`findings_parse_mode` is the JUDGE's, copied into the index so the feasibility")
    print("gate is a column rather than a walk of the tree. The four format columns beside")
    print("it are REPORTED AND NEVER ENFORCED (the smoke of 2026-09-02: one claim listed as")
    print("four findings, a quarter of the passages not verbatim) — a judge that writes a")
    print("page of commentary around every list, or quotes loosely, is visible here rather")
    print("than only in the published document.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"  {ARM_LABELS[key]}")
        if not rows:
            print("  NOT RUN.")
            continue
        values = list(rows.values())
        modes = Counter(r.get("findings_parse_mode") for r in values)
        print(f"    parse modes                      {dict(modes)}")
        counts = [r["findings_n"] for r in values if r.get("findings_n") is not None]
        print(f"    findings per list                {_distribution(counts)}")
        spread = Counter(min(c, 5) for c in counts)
        print("    distribution                     "
              + "  ".join(f"{'5+' if k == 5 else k}:{spread[k]}"
                          for k in sorted(spread)))
        empty = sum(1 for c in counts if c == 0)
        print(f"    EMPTY LIST (verdict SOUND)       {rate(empty, len(counts))}"
              "   — contestable by omission, and not a loss")
        normalised = [r.get("findings_ruling_normalised_n") or 0 for r in values]
        print(f"    rulings normalised FLAWED/SOUND  {sum(normalised)} over "
              f"{sum(1 for n in normalised if n)} lists"
              "   (the one parser tolerance, counted so it is visible)")
        exact = [r.get("findings_passage_exact_n") for r in values
                 if r.get("findings_passage_exact_n") is not None]
        if exact:
            total_findings = sum(r.get("findings_n") or 0 for r in values
                                 if r.get("findings_passage_exact_n") is not None)
            duplicate = sum(r.get("findings_duplicate_passage_n") or 0 for r in values)
            print(f"    passages found verbatim          "
                  f"{rate(sum(exact), total_findings)}   (of findings, not of cells)")
            print(f"    passages repeating an earlier one "
                  f"{rate(duplicate, total_findings)}")
        else:
            print("    passages found verbatim          NOT IN THIS INDEX — written from "
                  "2026-09-02; an older index has no such column")
        preamble = [r.get("findings_preamble_chars") for r in values
                    if r.get("findings_preamble_chars") is not None]
        trailing = [r.get("findings_trailing_chars") for r in values
                    if r.get("findings_trailing_chars") is not None]
        if preamble or trailing:
            print(f"    preamble chars trimmed           {_distribution(preamble)}")
            print(f"    trailing chars trimmed           {_distribution(trailing)}")
        else:
            print("    preamble / trailing chars        NOT IN THIS INDEX")
        scan = scans.get(key) or {}
        if not scan:
            print("    FORMAT REPAIRS                   NOT IN THE INDEX — re-run with "
                  f"--scan-{key}-tree, or read arm-{key}/format-scan.jsonl")
            continue
        for label, column in (("judge", "judge_repairs"),
                              ("challenger", "challenge_repairs"),
                              ("recourse judge", "ruling_repairs")):
            got = [r.get(column) for r in scan.values() if r.get(column) is not None]
            print(f"    repairs, {label:<24}{sum(got)} over {sum(1 for g in got if g)} "
                  f"of {len(got)} calls")


# --------------------------------------------------------------------------- #
# (1) P1
# --------------------------------------------------------------------------- #


def section_p1(arms, population) -> dict:
    head("(1) P1 — DOES RECOURSE ON A DECOMPOSED JUDGMENT RAISE ACCURACY?  [PRIMARY]")
    print("Exact two-sided McNemar on before/after correctness, alpha = 0.05, PER ARM and")
    print("never pooled: F-weak's P1 and P2 are one intersection-union claim, and F-strong's")
    print("P1 is a separate family at its own alpha (PREREG §2's alpha policy).")
    print()
    print("BEFORE is the findings judge's OWN derived verdict (`initially_correct`) and not")
    print("jd3-M0's. Every fd1 arm is a rejudge, so the arm made its own decision; M0 is a")
    print("recorded comparator in section (4) and never P1's baseline. AFTER is")
    print("`final_correct`, and a cell nobody ruled on keeps the decision it had.")
    out: dict[str, dict] = {}
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"  {ARM_LABELS[key]} — every decided cell")
        if not rows:
            print("  NOT RUN — this arm has no index.")
            continue
        pairs = []
        for cell_id, row in sorted(rows.items()):
            before, after = before_of(row), after_of(row)
            if before is None or after is None:
                continue
            pairs.append((cell_id, bool(before), bool(after)))
        if not pairs:
            print("  NOT RUN — no cell carries both states.")
            continue
        out[key] = paired_block(pairs, "before", "after")
        print()
        print("  THE TWO DENOMINATORS PREREG §2 REQUIRES, on the same cells. A decision")
        print("  nobody contested cannot move, so the whole-arm net above is diluted by")
        print("  every uncontested cell; and an objection made ENTIRELY of mechanically")
        print("  void contests cannot move one either, by construction.")
        for label, predicate in (
                ("contested and ruled",
                 lambda r: contested(r) and was_ruled(r)),
                (">= 1 well-formed contest",
                 lambda r: contested(r) and was_ruled(r) and well_formed(r))):
            stats = arm_rates(rows, only=predicate)
            net = stats["fixed"] - stats["broken"]
            p = mcnemar_exact(stats["fixed"], stats["broken"])
            print(f"    {label:<28}n {stats['n']:>5}   fixed {stats['fixed']:>4}   "
                  f"broken {stats['broken']:>4}   net {net:>+5d}   "
                  f"p = {p:.4g}  {verdict_at(p)}")
            out.setdefault(f"{key}_{label}", {**stats, "net": net, "p": p})
    return out


# --------------------------------------------------------------------------- #
# (2) P2
# --------------------------------------------------------------------------- #


def _p2_block(label: str, stats: dict, jd5b: dict) -> dict:
    """One row of P2: F-weak's break rate against jd5-B's, Fisher one-sided + Newcombe."""
    broken, kept = stats["broken"], stats["n_right"] - stats["broken"]
    b_broken, b_kept = jd5b["broken"], jd5b["n_right"] - jd5b["broken"]
    p = fisher_one_sided(broken, kept, b_broken, b_kept, alternative="less")
    print()
    print(f"  DENOMINATOR: {label}")
    print(f"{'':<28}{'broken':>10}{'kept':>10}{'total':>10}{'rate':>30}")
    rule()
    print(f"{'F-weak':<28}{broken:>10}{kept:>10}{stats['n_right']:>10}"
          f"{rate_ci(broken, stats['n_right']):>30}")
    print(f"{'jd5-B (the check arm)':<28}{b_broken:>10}{b_kept:>10}{jd5b['n_right']:>10}"
          f"{rate_ci(b_broken, jd5b['n_right']):>30}")
    rule()
    difference = ((100.0 * broken / stats["n_right"] if stats["n_right"] else float("nan"))
                  - 100.0 * b_broken / jd5b["n_right"])
    print(f"  difference (F-weak - jd5-B)          {difference:+.1f} pts   "
          f"Newcombe 95% {difference_interval(broken, stats['n_right'], b_broken, jd5b['n_right'])}")
    print(f"  FISHER'S EXACT, ONE-SIDED (less)     p = {p:.6g}   "
          f"{'P2 HOLDS' if p < ALPHA else 'P2 NOT SHOWN'} at alpha = {ALPHA}")
    return {"broken": broken, "n_right": stats["n_right"], "p": p,
            "holds": p < ALPHA, "difference": difference}


def section_p2(arms, population, jd5b_stats, jd5b_note) -> dict:
    head("(2) P2 — DOES THE LOCAL CONTEST BREAK FEWER RIGHT DECISIONS?  [CO-PRIMARY]")
    print("F-weak only, ONE-SIDED at alpha = 0.05. Among F-weak's contested, ruled,")
    print("before-RIGHT cells, is `broken | right` BELOW jd5-B's 167/622 = 26.8%?")
    print()
    print(jd5b_note)
    print()
    print("THIS COMPARISON IS UNPAIRED AND IT COMPARES TWO MECHANISMS. The contest object")
    print("(a finding vs the whole judgment), the ruling prompt, the before-state (the")
    print("findings judge's own derived verdict vs M0's) and the routing all moved between")
    print("the two rows. Fisher's exact test is the right SHAPE — jd5-B's 622 are data with")
    print("their own sampling error, and the one-sample binomial the questionnaire defaulted")
    print("to would call a four-point drop significant that a fair test calls borderline —")
    print("but no test here can attribute the difference to the decomposition alone. The")
    print("paired table at the end of this section is the one that holds the cell fixed, and")
    print("it is DESCRIPTIVE with its n.")
    rows = restrict(arms.get("weak", {}), population)
    if not rows or not jd5b_stats["n_right"]:
        print("\nNOT RUN — F-weak's index or the jd5-B comparator is missing.")
        return {}
    out = {}
    out["all"] = _p2_block("all contested-and-ruled cells that were RIGHT before",
                           arm_rates(rows, only=lambda r: (contested(r) and was_ruled(r))),
                           jd5b_stats)
    out["well_formed"] = _p2_block(
        ">= 1 well-formed contest (not void-only), RIGHT before",
        arm_rates(rows, only=lambda r: (contested(r) and was_ruled(r)
                                        and well_formed(r))),
        jd5b_stats)
    print()
    print("  The registered P2 is the FIRST denominator; the second is reported beside it")
    print("  because an objection made only of void contests cannot break anything by")
    print("  construction, and PREREG §2 fixed both before the run so neither can be chosen")
    print("  after the table.")
    return out


def section_p2_paired(arms, jd5b_rows, population) -> dict:
    head("  THE PAIRED 2x2 ON THE INTERSECTION  [DESCRIPTIVE — not the endpoint]")
    print("The cells that were RIGHT under BOTH before-states — the findings judge's own")
    print("derived verdict and jd3-M0's decision — and that BOTH challengers contested. It")
    print("is the only table here that holds the cell fixed, and it is small by construction:")
    print("the two before-states are different judgments about the same debate, so a cell")
    print("only qualifies where they agree.")
    weak = restrict(arms.get("weak", {}), population)
    if not weak or not jd5b_rows:
        print("\nNOT RUN — F-weak's index or jd5-B's is missing.")
        return {}
    pairs = []
    for cell_id in sorted(set(weak) & set(jd5b_rows)):
        left, right = weak[cell_id], jd5b_rows[cell_id]
        if not (contested(left) and was_ruled(left)):
            continue
        if not (contested(right) and was_ruled(right)):
            continue
        if before_of(left) is not True or before_of(right) is not True:
            continue
        after_left, after_right = after_of(left), after_of(right)
        if after_left is None or after_right is None:
            continue
        pairs.append((cell_id, bool(after_left), bool(after_right)))
    if not pairs:
        print("\nNOT RUN — no cell is right under both before-states and contested by both.")
        return {}
    counts = Counter((a, b) for _, a, b in pairs)
    kk = counts[(True, True)]
    kb = counts[(True, False)]
    bk = counts[(False, True)]
    bb = counts[(False, False)]
    n = kk + kb + bk + bb
    p = mcnemar_exact(kb, bk)
    print()
    print(f"{'':<28}{'jd5-B kept':>16}{'jd5-B broke':>16}{'total':>10}")
    rule()
    print(f"{'F-weak kept':<28}{kk:>16}{kb:>16}{kk + kb:>10}")
    print(f"{'F-weak broke':<28}{bk:>16}{bb:>16}{bk + bb:>10}")
    rule()
    print(f"{'total':<28}{kk + bk:>16}{kb + bb:>16}{n:>10}")
    print()
    print(f"  broken by F-weak ALONE                {bk}")
    print(f"  broken by jd5-B ALONE                 {kb}")
    print(f"  broken by BOTH                        {bb}")
    print(f"  broken by NEITHER                     {kk}")
    print(f"  discordant pairs                      {bk + kb}"
          f"   (concordant {kk + bb}, and they carry no direction)")
    print(f"  EXACT TWO-SIDED McNEMAR               p = {p:.6g}   {verdict_at(p)}")
    print()
    print("  DESCRIPTIVE. The two rows are different mechanisms on the same cell, not two")
    print("  treatments of one; the pairing removes the cell's difficulty and nothing else.")
    return {"n": n, "weak_only": bk, "jd5b_only": kb, "both": bb, "neither": kk, "p": p}


# --------------------------------------------------------------------------- #
# (3) P3
# --------------------------------------------------------------------------- #


def section_p3(arms, population, jd5b_stats) -> dict:
    head("(3) P3 — THE FIX SIDE  [REPORTED, NOT TESTED]")
    print("`fixed | wrong` among the contested, ruled, before-WRONG cells, with a Wilson")
    print("interval, beside jd5-B's 144/274 = 52.6%. PREREG §2 registers this as REPORTED:")
    print("there is no test and no alpha, because P2 is the break side and the conjunction")
    print("P1-and-P2 is the claim. A fix rate that fell would explain a P1 failure that P2")
    print("could not, which is why it is printed rather than left out.")
    print()
    print(f"{'mechanism':<40}{'n wrong':>10}{'fixed | wrong':>28}")
    rule()
    out = {}
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        if not rows:
            print(f"{ARM_LABELS[key]:<40}{'NOT RUN':>10}")
            continue
        stats = arm_rates(rows, only=lambda r: contested(r) and was_ruled(r))
        out[key] = stats
        print(f"{ARM_LABELS[key]:<40}{stats['n_wrong']:>10}"
              f"{rate_ci(stats['fixed'], stats['n_wrong']):>28}")
    if jd5b_stats["n_wrong"]:
        print(f"{'jd5-B (the check arm)':<40}{jd5b_stats['n_wrong']:>10}"
              f"{rate_ci(jd5b_stats['fixed'], jd5b_stats['n_wrong']):>28}")
    rule()
    print("F-strong's row is DESCRIPTIVE beside F-weak's: P2 and P3 are F-weak's, because")
    print("jd5-B's judge is Maverick and only F-weak shares it.")
    return out


# --------------------------------------------------------------------------- #
# (4) the recorded quantities
# --------------------------------------------------------------------------- #


def _paired_two_columns(rows, other, left_of, right_of, left: str, right: str,
                        *, only=None) -> dict | None:
    pairs = []
    for cell_id in sorted(set(rows) & set(other)):
        if only is not None and not only(rows[cell_id]):
            continue
        a, b = left_of(other[cell_id]), right_of(rows[cell_id])
        if a is None or b is None:
            continue
        pairs.append((cell_id, bool(a), bool(b)))
    if not pairs:
        return None
    return paired_block(pairs, left, right)


def section_recorded(arms, population, m0, jd5b_stats, scans) -> dict:
    head("(4) RECORDED, NOT TESTED  [every number here is DESCRIPTIVE]")
    print("PREREG §3's list. None of it carries an alpha and none of it is an endpoint; the")
    print("two McNemar p-values printed below are labelled DESCRIPTIVE where they appear and")
    print("are there so a reader can see the size of a difference, not to test it.")

    head("  (4a) THE FINDINGS JUDGE AGAINST jd3-M0  [DESCRIPTIVE — p is not a test]")
    print("M0 decided these same debates under the ORDINARY verdict prompt. The difference")
    print("below contains, inseparably: Maverick's own disagreement with itself on a re-draw,")
    print("the findings FORMAT, the DERIVATION rule (FLAWED iff any finding is FLAW) and a")
    print("routing change. NO FLOOR ARM PRICES THE RE-DRAW, so none of it is attributed.")
    out: dict[str, dict] = {}
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]} — decision vs M0's decision")
        if not rows or not m0:
            print("    NOT RUN.")
            continue
        got = _paired_two_columns(rows, m0, m0_of, before_of, "M0", f"F-{key}")
        if got is None:
            print("    NOT RUN — no cell carries both decisions.")
            continue
        out[f"{key}_vs_m0"] = got

    head("  (4b) ACCURACY AFTER RECOURSE AGAINST M0  [ABLATION — NOT AN ENDPOINT]")
    print("The same caveat, plus the recourse stage. It is the quantity jd3-jd5 reported as")
    print("P1 and it is demoted here for the reason §3ac gives: it is dominated by the base")
    print("rate of wrong decisions, so a mechanism that breaks and fixes at equal RATES still")
    print("nets negative. P1 of section (1) is the endpoint; this is the ablation.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]} — after recourse vs M0's decision")
        if not rows or not m0:
            print("    NOT RUN.")
            continue
        got = _paired_two_columns(rows, m0, m0_of, after_of, "M0", "recourse")
        if got is None:
            print("    NOT RUN — no cell carries both states.")
            continue
        out[f"{key}_after_vs_m0"] = got

    head("  (4c) §3ac's IDENTITY, PER MECHANISM  [the bar P1 has to clear]")
    print("Recourse does not lower accuracy iff `f / b >= a / (1 - a)`, where `a` is the")
    print("accuracy of the decisions the mechanism SEES. Equivalently it hurts above the")
    print("break-even accuracy `a* = f / (f + b)` — and `f` and `b` there are RATES. The")
    print("derived verdict changes `a`, and therefore moves the bar, which is exactly why")
    print("this row is printed for every arm rather than left to the write-up.")
    print()
    print_identity_header()
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        if not rows:
            print(f"{ARM_LABELS[key]:<40}{'NOT RUN':>7}")
            continue
        stats = arm_rates(rows, only=lambda r: contested(r) and was_ruled(r))
        out[f"{key}_identity"] = identity_row(stats)
        print_identity_row(ARM_LABELS[key], stats)
    if jd5b_stats["n"]:
        print_identity_row("jd5-B (the check arm)", jd5b_stats)
    rule()
    print("Read `f / b` against `a / (1 - a)` in the same row: the mechanism nets positive")
    print("only where the first exceeds the second. `a*` says the same thing as a threshold")
    print("on the first-instance accuracy.")

    head("  (4d) THE TWO RATES SPLIT BY BEFORE-VERDICT AND BY `findings_flaw_n`")
    print("PREREG §3 registers this split because the two directions are NOT symmetric under")
    print("a derived verdict, and jd5-B has no such asymmetry to compare against: breaking a")
    print("right SOUND verdict takes ONE upheld contest, and breaking a right FLAWED verdict")
    print("takes EVERY FLAW finding flipped. A break rate that is high on SOUND and near zero")
    print("on FLAWED is the derivation rule showing through, not the judge.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]}")
        if not rows:
            print("    NOT RUN.")
            continue
        base = {c: r for c, r in rows.items() if contested(r) and was_ruled(r)}
        print(f"    {'split':<28}{'n':>6}{'fixed | wrong':>26}{'broken | right':>26}")
        rule()
        for verdict in VERDICTS:
            stats = arm_rates(base, only=lambda r, v=verdict: r.get("verdict") == v)
            print(f"    {('before-verdict ' + verdict):<28}{stats['n']:>6}"
                  f"{rate_ci(stats['fixed'], stats['n_wrong']):>26}"
                  f"{rate_ci(stats['broken'], stats['n_right']):>26}")
        for label, predicate in (("findings_flaw_n = 0", lambda n: n == 0),
                                 ("findings_flaw_n = 1", lambda n: n == 1),
                                 ("findings_flaw_n >= 2", lambda n: n >= 2)):
            stats = arm_rates(base, only=lambda r, f=predicate: (
                r.get("findings_flaw_n") is not None and f(r["findings_flaw_n"])))
            print(f"    {label:<28}{stats['n']:>6}"
                  f"{rate_ci(stats['fixed'], stats['n_wrong']):>26}"
                  f"{rate_ci(stats['broken'], stats['n_right']):>26}")
        rule()

    head("  (4e) THE OBJECTION ITSELF — CONTESTS PER OBJECTION, BY KIND")
    print("Three kinds, and they are three different claims: a FINDING contest asks for the")
    print("opposite ruling on a numbered finding, an OMISSION says the list missed a flaw the")
    print("record raised, a CONTRADICTION says two findings say the same thing and were ruled")
    print("differently. The mix is what the decomposition bought, and it has no counterpart")
    print("in jd3-jd6, where the objection was the whole judgment.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]}")
        if not rows:
            print("    NOT RUN.")
            continue
        raised = [r for r in rows.values() if contested(r)]
        if not raised:
            print("    no objection was raised on any cell.")
            continue
        total = sum(r.get("challenge_contests_n") or 0 for r in raised)
        print(f"    objections raised                {len(raised)}")
        print(f"    contests per objection           {total} total, "
              f"{total / len(raised):.2f} mean")
        for kind in ("finding", "omission", "contradiction"):
            n = sum(r.get(f"challenge_contests_{kind}_n") or 0 for r in raised)
            cells = sum(1 for r in raised if (r.get(f"challenge_contests_{kind}_n") or 0))
            print(f"      {kind:<28}{n:>6} contests over {cells} objections "
                  f"({pct(n, total)} of contests)")
        void = sum(r.get("challenge_contests_void_n") or 0 for r in raised)
        print(f"      {'mechanically VOID':<28}{void:>6} contests  "
              f"({pct(void, total)} of contests)")
        # THE DIRECTION OF A FINDING CONTEST, printed as its own table and never pooled
        # with the kind mix or with the validity rate. PREREG §5(a): the two directions
        # are graded against DIFFERENT bounds — NOT A FLAW -> FLAW is valid only if the
        # finding is the annotated flaw (a LOWER bound), FLAW -> NOT A FLAW is valid by
        # rule on every sound item (an UPPER bound) — so a validity number over the two
        # together moves with the mix rather than with the challenger. This table is what
        # says which mix it moved with. `Should be:` is not a field an omission or a
        # contradiction has, so the two rows count FINDING contests only and need not sum
        # to the finding row above: a contest that named no direction is in neither.
        to_flaw = sum(r.get("challenge_contests_to_flaw_n") or 0 for r in raised)
        to_not = sum(r.get("challenge_contests_to_not_a_flaw_n") or 0 for r in raised)
        finding_n = sum(r.get("challenge_contests_finding_n") or 0 for r in raised)
        if any(r.get("challenge_contests_to_flaw_n") is not None for r in raised):
            print(f"    DIRECTION of the finding contests   "
                  f"({finding_n} finding contests)")
            print(f"      {'NOT A FLAW -> FLAW':<28}{to_flaw:>6}  "
                  f"({pct(to_flaw, finding_n)})  validity is a LOWER bound (§5a)")
            print(f"      {'FLAW -> NOT A FLAW':<28}{to_not:>6}  "
                  f"({pct(to_not, finding_n)})  validity is an UPPER bound (§5a)")
            missing = finding_n - to_flaw - to_not
            if missing:
                print(f"      {'no direction read':<28}{missing:>6}  "
                      "— void by `direction_ok`, and kept in the list")
        else:
            print("    DIRECTION of the finding contests: NOT IN THE INDEX — this tree")
            print("      predates `challenge_contests_to_flaw_n` (R12e, 2026-09-02).")
        # A `Record says:` GIVEN AND NOT FOUND on a contest of a FINDING. Since R12a that
        # does NOT void the contest — the field is optional for this kind and the anchor
        # is `Text says:` — so it is reported here and never inside the void count. It is
        # the rate at which this challenger attributes words to a document that does not
        # carry them, which is a fact about the challenger and not about the contest.
        if any(r.get("challenge_contests_record_unverified_n") is not None
               for r in raised):
            unverified = sum(
                r.get("challenge_contests_record_unverified_n") or 0 for r in raised)
            print(f"      {'record quote unverified':<28}{unverified:>6}  "
                  f"({pct(unverified, finding_n)} of finding contests) — RECORDED, "
                  "not voiding")
        else:
            print("      record quote unverified: NOT IN THE INDEX (R12a, 2026-09-02).")
        only_void = sum(1 for r in raised if void_only(r) is True)
        print(f"    VOID-ONLY objections             {rate(only_void, len(raised))}"
              "   — cannot break anything by construction, and NOT a phantom")
        seeks = sum(1 for r in raised if r.get("challenge_seeks_reversal"))
        print(f"    seeking a reversal               {rate(seeks, len(raised))}"
              "   — a contest can be local and unable to move the verdict")
        phantom = [r.get("phantom_contest") for r in rows.values()
                   if r.get("phantom_contest") is not None]
        print(f"    MECHANICAL phantom rate          "
              f"{rate(sum(1 for p in phantom if p), len(phantom))}")
        print("      `phantom = (stance == contests) != (n_well_formed > 0)`, computed and")
        print("      NOT read by a model. NEVER pooled with jd3-jd6's Haiku phantom column.")
        print("      Its two blind spots — a well-formed contest whose `Why` argues the")
        print("      finding is RIGHT, and a STANDS whose prose attacks a finding without an")
        print("      entry — are scored by the 20-cell hand read in HANDCHECK.md.")
        comprehension = [r.get("comprehension") for r in rows.values()
                         if r.get("comprehension") is not None]
        if comprehension:
            print(f"    comprehension mean               "
                  f"{sum(comprehension) / len(comprehension):.2f} over "
                  f"{len(comprehension)} cells")

    head("  (4f) VALIDITY, BY KIND AND BY `label_basis`  [NEVER POOLED ACROSS THE TWO]")
    print("PREREG §5(a): on FLAWED items 'a real flaw' is operationalised as THE ANNOTATED")
    print("flaw, so a NOT A FLAW -> FLAW contest on a genuine but unannotated error is")
    print("INVALID BY RULE — validity on flawed items is a LOWER BOUND — while its mirror")
    print("FLAW -> NOT A FLAW is VALID by rule, an UPPER bound. The two are never averaged")
    print("together, and `label_basis` is where that split lives.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]}")
        if not rows:
            print("    NOT RUN.")
            continue
        graded_rows = [r for r in rows.values() if graded(r)]
        if not graded_rows:
            print("    no cell was graded.")
            continue
        print(f"    {'label_basis':<28}{'objections':>12}{'valid objection':>26}")
        rule()
        for basis in sorted({r.get("label_basis") for r in graded_rows}, key=str):
            group = [r for r in graded_rows if r.get("label_basis") == basis]
            valid = sum(1 for r in group if r.get("grade_valid"))
            print(f"    {str(basis):<28}{len(group):>12}"
                  f"{rate_ci(valid, len(group)):>26}")
        rule()
        # ITEMS WHOSE ANNOTATION RECORDS NO LOCATION. `label_basis` says how the label
        # was arrived at; this says whether the grader had a place to point at. A finding
        # contest on a flawed item is graded by asking whether the finding IS the
        # annotated flaw, and where `flaw.json` carries an empty `flaw_location` that
        # question is answered from the annotation prose alone — a different instrument
        # on the same row. Counted, not corrected, and printed here so the validity rate
        # above is read with it. Read from the index if it is there; a tree written
        # before the column existed gets the note and no number, on this file's rule that
        # a missing measurement is said out loud rather than defaulted to zero.
        if any(r.get("flaw_location_missing") is not None for r in graded_rows):
            missing_loc = sum(1 for r in graded_rows if r.get("flaw_location_missing"))
            flawed = [r for r in graded_rows if r.get("gold_flawed")]
            missing_flawed = sum(1 for r in flawed if r.get("flaw_location_missing"))
            print(f"    annotation with NO location      "
                  f"{rate(missing_loc, len(graded_rows))} of graded cells, "
                  f"{rate(missing_flawed, len(flawed))} of the FLAWED ones")
        else:
            print("    annotation with NO location: NOT IN THE INDEX — `flaw.json`'s")
            print("      `flaw_location` is not carried as `flaw_location_missing` on")
            print("      these rows, so how many finding contests were graded without a")
            print("      place to point at is not derivable here.")
        contests_n = sum(r.get("grade_contests_n") or 0 for r in graded_rows)
        contests_valid = sum(r.get("grade_contests_valid_n") or 0 for r in graded_rows)
        mechanical = sum(r.get("grade_contests_mechanical_n") or 0 for r in graded_rows)
        print(f"    contests graded                  {contests_n}")
        print(f"    contests VALID                   {rate(contests_valid, contests_n)}")
        print(f"    graded MECHANICALLY (no call)    {rate(mechanical, contests_n)}"
              "   — a void flag, or the sound-item rules of D1.4")
        scan = scans.get(key) or {}
        by_kind: dict[str, list[bool]] = {}
        for row in scan.values():
            for entry in row.get("grade_contests") or []:
                by_kind.setdefault(str(entry.get("kind")), []).append(
                    bool(entry.get("valid")))
        if by_kind:
            print()
            print(f"    {'kind':<28}{'contests':>12}{'valid':>26}")
            rule()
            for kind in sorted(by_kind):
                got = by_kind[kind]
                valid = sum(1 for v in got if v)
                print(f"    {kind:<28}{len(got):>12}"
                      f"{rate_ci(valid, len(got)):>26}")
            rule()
        else:
            print()
            print("    VALIDITY BY KIND: NOT IN THE INDEX — `grade_contests_valid_n` is an")
            print(f"    objection-level count. Re-run with --scan-{key}-tree, or read")
            print(f"    arm-{key}/format-scan.jsonl. The single-kind approximation below")
            print("    uses only the objections whose every contest was of ONE kind, and it")
            print("    is a BIASED subset (a mixed objection is a different objection).")
            single: dict[str, list[bool]] = {}
            for row in graded_rows:
                kinds = [k for k in ("finding", "omission", "contradiction")
                         if (row.get(f"challenge_contests_{k}_n") or 0)]
                if len(kinds) == 1:
                    single.setdefault(kinds[0], []).append(bool(row.get("grade_valid")))
            for kind in sorted(single):
                got = single[kind]
                print(f"      {kind:<26}{len(got):>12} single-kind objections, "
                      f"{rate(sum(1 for v in got if v), len(got))} valid")

    head("  (4g) THE RULING — LINE/PROSE MISMATCH, EMPTY PROSE, AND THE APPENDED FINDINGS")
    print("`ruling_line_mismatch` is the instrument that keeps `changed_the_decision`")
    print("falsifiable: Haiku reads the ruling's PROSE and says whether it supports every")
    print("line. `ruling_leadin_stripped` is a fact about the RULING PROMPT and not the")
    print("reader — two of three findings-reader mismatches in the smoke were a dangling")
    print("lead-in ('The final ruling for Contest 1 is:') that the strip dropped — so the")
    print("two are printed together and the mismatch rate is read with the lead-in count.")
    for key in ("weak", "strong"):
        rows = restrict(arms.get(key, {}), population)
        head(f"    {ARM_LABELS[key]}")
        if not rows:
            print("    NOT RUN.")
            continue
        ruled_rows = [r for r in rows.values() if contested(r) and was_ruled(r)]
        if not ruled_rows:
            print("    no cell was ruled.")
            continue
        read = [r for r in ruled_rows if r.get("ruling_line_mismatch") is not None]
        mismatch = sum(1 for r in read if r.get("ruling_line_mismatch"))
        leadin = sum(1 for r in read if r.get("ruling_leadin_stripped"))
        print(f"    rulings                          {len(ruled_rows)}")
        print(f"    read by the ruling reader        {len(read)}")
        print(f"    line / prose MISMATCH            {rate(mismatch, len(read))}")
        print(f"    of which a lead-in was stripped  {leadin}"
              + ("   (a prompt fact, not a reader fact)" if leadin else ""))
        empty = [r for r in ruled_rows if r.get("ruling_prose_empty") is not None]
        print(f"    ruling with NO prose at all      "
              f"{rate(sum(1 for r in empty if r.get('ruling_prose_empty')), len(empty))}"
              "   — the reader cannot read it; counted, not silently unmeasured")
        added = [r.get("findings_added_n") or 0 for r in ruled_rows]
        with_added = [r for r in ruled_rows if (r.get("findings_added_n") or 0)]
        print(f"    findings APPENDED at recourse    {sum(added)} over "
              f"{len(with_added)} rulings   (an upheld omission, built from the contest's")
        print("                                     own quotes and marked "
              "`added_at_recourse`)")
        # AN APPENDED FINDING THAT MOVED A VERDICT: the decision was SOUND (so the list
        # held no FLAW), an omission was upheld as a FLAW and appended, and the verdict
        # was re-derived to FLAWED. It is the ONE route by which an omission can overturn,
        # and PREREG §3 asks for it by name.
        moved = [r for r in with_added
                 if r.get("verdict") == "SOUND" and r.get("changed_the_decision")
                 and (r.get("findings_after_flaw_n") or 0) > 0]
        print(f"    appended findings that MOVED a verdict   {len(moved)} of "
              f"{len(with_added)}")
        print("      (a before-SOUND cell whose appended FLAW re-derived the verdict to")
        print("       FLAWED — the only route by which an omission overturns a decision)")
        out[f"{key}_appended_moved"] = {"moved": len(moved), "with_added": len(with_added)}
    return out


# --------------------------------------------------------------------------- #
# (5) the named outcome
# --------------------------------------------------------------------------- #


def section_outcome(primary, p2, paired) -> None:
    head("(5) THE PRE-REGISTERED READING")
    print("PREREG §4's four names were written down before either arm ran, so that no rule")
    print("is invented after the table:")
    print("  (A) P1 POSITIVE and P2 HOLDS       the first arm to net positive, by the")
    print("                                     hypothesised route")
    print("  (B) P2 HOLDS, P1 NULL or NEGATIVE  fewer right decisions broken and STILL not")
    print("                                     enough: f/b below a/(1-a)")
    print("  (C) P1 POSITIVE, P2 NOT SHOWN      nets positive by the FIX side, not the break")
    print("                                     side")
    print("  (D) neither")
    print()
    print("AND THE RULE THAT GOVERNS ALL FOUR: SPLITS ARE REPORTED AS SPLITS. A result that")
    print("is none of the four names — jd6 produced exactly one — is written down as the")
    print("split it is, with both tests' numbers, and is NOT rounded to whichever name it is")
    print("nearest. Nothing below is rounded.")
    weak = primary.get("weak")
    strong = primary.get("strong")
    p2_all = (p2 or {}).get("all")
    print()
    if not weak:
        print("F-weak: NOT RUN — no P1 table, so no named outcome. This is what the file")
        print("prints before the arm has run, and it is not an error.")
    else:
        reading = p1_reading(weak["net"], weak["p"])
        print(f"P1  F-weak: fixed {weak['fixed']}, broken {weak['broken']}, net "
              f"{weak['net']:+d} on {weak['n']} cells, p = {weak['p']:.4g} "
              f"-> P1 is {reading}")
        if p2_all:
            print(f"P2  F-weak: broken | right {rate(p2_all['broken'], p2_all['n_right'])} "
                  f"against jd5-B's 167/622 = 26.8%, {p2_all['difference']:+.1f} pts, "
                  f"one-sided Fisher p = {p2_all['p']:.4g} -> P2 "
                  f"{'HOLDS' if p2_all['holds'] else 'is NOT SHOWN'}")
        else:
            print("P2  F-weak: NOT RUN — no comparator or no before-RIGHT contested cells.")
        letter, sentence = named_outcome(reading,
                                         p2_all["holds"] if p2_all else None)
        print()
        print(f"NAMED OUTCOME FOR F-WEAK: {letter}")
        print(f"  {sentence}")
        if p2_all and reading == "NULL" and p2_all["holds"]:
            print("  Note the shape of (B): the break side moved and the endpoint did not.")
            print("  Section (4c)'s identity is where that is explained, not here.")
    print()
    if not strong:
        print("F-strong: NOT RUN.")
    else:
        reading = p1_reading(strong["net"], strong["p"])
        print(f"P1  F-strong: fixed {strong['fixed']}, broken {strong['broken']}, net "
              f"{strong['net']:+d} on {strong['n']} cells, p = {strong['p']:.4g} "
              f"-> P1 is {reading}")
        print("  F-strong has NO P2: jd5-B's judge is Maverick, so only F-weak shares the")
        print("  comparator's model. Its P1 is a SEPARATE FAMILY at its own alpha = 0.05 and")
        print("  is never pooled with F-weak's; its rates sit beside F-weak's as descriptive.")
    if weak and strong:
        left, right = p1_reading(weak["net"], weak["p"]), p1_reading(strong["net"],
                                                                    strong["p"])
        print()
        if left != right:
            print(f"THE TWO ARMS DISAGREE — F-weak's P1 is {left} and F-strong's is {right}.")
            print("A cross-arm disagreement is REPORTED AS ONE (PREREG §4) and is not")
            print("resolved by preferring the stronger judge or the larger n.")
        else:
            print(f"Both arms' P1 read {left}. That is agreement about the endpoint and not")
            print("about the mechanism: the two judges differ in what they find, and section")
            print("(4d)'s splits are where that shows.")
    if paired:
        print()
        print(f"The descriptive paired table stands at n = {paired['n']}: F-weak broke "
              f"{paired['weak_only']} that jd5-B kept and kept {paired['jd5b_only']} that "
              f"jd5-B broke, p = {paired['p']:.4g}. It is not P2 and does not decide it.")
    print()
    print("WHAT THIS FILE DOES NOT CLAIM: nothing about jd3's P1, `single`/`self_critique`,")
    print("natural-error selection, or the same-model property (the findings judge also")
    print("rules on the appeals in both arms — accepted and disclosed, as jd3-jd6). No number")
    print("here is pooled with jd3-jd6's: the judgment form, the contest object and the")
    print("ruling prompt all differ.")


# --------------------------------------------------------------------------- #
# the CLI
# --------------------------------------------------------------------------- #


ARM_FLAGS = {
    "weak": ("--weak", "records/experiments/findings-1/arm-weak/index.jsonl"),
    "strong": ("--strong", "records/experiments/findings-1/arm-strong/index.jsonl"),
    "m0": ("--m0", "records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl"),
    "jd5b": ("--jd5b", "records/experiments/judgment-debate-5/arm-real/index.jsonl"),
}

SCAN_DEFAULTS = {
    "weak": "records/experiments/findings-1/arm-weak/format-scan.jsonl",
    "strong": "records/experiments/findings-1/arm-strong/format-scan.jsonl",
}
ATTEMPTS_DEFAULT = "records/experiments/findings-1/attempts.json"


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, (flag, default) in ARM_FLAGS.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"index.jsonl for {key} (default: {default})")
    for key, default in SCAN_DEFAULTS.items():
        parser.add_argument(f"--{key}-scan", type=Path, default=Path(default),
                            help=f"the {key} arm's format scan (default: {default})")
    parser.add_argument("--attempts", type=Path, default=Path(ATTEMPTS_DEFAULT),
                        help=f"attempted/completed/failed per arm "
                             f"(default: {ATTEMPTS_DEFAULT})")
    for key in ARM_LABELS:
        parser.add_argument(f"--scan-{key}-tree", type=Path, default=None,
                            help=f"re-derive the {key} arm's format scan and attempts "
                                 "from a finished run tree")
    parser.add_argument("--write-scans", type=Path, default=None,
                        help="with --scan-*-tree: write the scans into this directory "
                             "and exit")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    scans: dict[str, dict[str, dict]] = {}
    attempts: dict[str, dict] = {}
    for key in ARM_LABELS:
        tree = getattr(args, f"scan_{key}_tree")
        if tree is None:
            continue
        scans[key] = {r["cell_id"]: r for r in scan_tree(tree)}
        attempts[key] = scan_attempts(tree, "cells/*/runs/*/run.json")
        attempts[f"{key}-contest"] = scan_attempts(
            tree, "cells/*/contests/*/runs/*/run.json")
    if args.write_scans is not None:
        out = Path(args.write_scans)
        for key in ARM_LABELS:
            (out / f"arm-{key}").mkdir(parents=True, exist_ok=True)
            (out / f"arm-{key}" / "format-scan.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in (scans.get(key) or {}).values()),
                encoding="utf-8")
        (out / "attempts.json").write_text(json.dumps(attempts, indent=2),
                                           encoding="utf-8")
        print(f"wrote {sum(len(s) for s in scans.values())} scan rows and "
              f"{len(attempts)} attempt tables -> {out}")
        return 0
    for key in ARM_LABELS:
        if not scans.get(key):
            got = load_rows(getattr(args, f"{key}_scan"))
            if got:
                scans[key] = got
    if not attempts and Path(args.attempts).is_file():
        attempts = json.loads(Path(args.attempts).read_text(encoding="utf-8"))

    arms = {key: load(getattr(args, _dest(flag))) for key, (flag, _) in ARM_FLAGS.items()}

    print("=" * W)
    print("findings-1 — the decomposed judgment, and whether a local contest breaks fewer")
    print("=" * W)
    print("Pre-registration: records/experiments/findings-1/PREREG.md")
    print("Section (1) is P1 and (2) is P2; the registered claim for F-weak is the")
    print("CONJUNCTION of the two. (3) is REPORTED. (4) is DESCRIPTIVE throughout and its")
    print("(4b) is an ABLATION. (5) names the outcome and reports a split as a split.")
    print()
    print(f"{'arm':<12}{'index':<76}{'rows':>8}")
    rule()
    for key, (flag, _) in ARM_FLAGS.items():
        n = len(arms[key])
        print(f"{key:<12}{str(getattr(args, _dest(flag))):<76}"
              f"{(n if n else 'NOT RUN'):>8}")
    for key in ARM_LABELS:
        n = len(scans.get(key) or {})
        print(f"{(key + ' scan'):<12}{str(getattr(args, f'{key}_scan')):<76}"
              f"{(n if n else 'NOT AVAILABLE'):>8}")
    rule()

    # THE POPULATION, defined once: the cells jd3-M0 decided, which is what every fd1 spec
    # is offered (`transcripts_from = outputs/experiments/jd3-main`). Taken from M0's index
    # where it is available and from the arms themselves otherwise, so the file still runs
    # on a machine that holds only fd1's records.
    m0 = arms.get("m0") or {}
    if m0:
        population = set(m0)
    else:
        population = set(arms.get("weak", {})) | set(arms.get("strong", {}))
        if population:
            print("note: M0's index is not present, so the population is taken from the fd1")
            print("arms themselves. Every loss at REJUDGE is then invisible, because a cell")
            print("that never reached an index is not in the population either.")

    if not population:
        print("\nNOTHING TO DERIVE — no index is present. This is what the file prints")
        print("before the run, and it is not an error.")
        return 0

    # THE COMPARATOR, recomputed and then asserted in ONE place.
    jd5b_rows = arms.get("jd5b") or {}
    jd5b_cells = {c for c, r in jd5b_rows.items() if contested(r)}
    jd5b_stats = jd5b_rates(jd5b_rows, jd5b_cells) if jd5b_rows else {
        "fixed": 0, "n_wrong": 0, "broken": 0, "n_right": 0, "n": 0}
    jd5b_note = (check_jd5b(jd5b_stats, len(jd5b_rows)) if jd5b_rows
                 else "NOT RUN — the jd5-B comparator index is missing, so P2 has no "
                      "second row and prints NOT RUN.")

    section_losses(arms, population, m0, scans)
    if attempts:
        head("  ATTEMPTED / COMPLETED / FAILED, FROM THE TREE  [needs a --scan-*-tree]")
        print(f"{'tree':<32}{'attempted':>12}{'completed':>12}{'failed':>10}")
        rule()
        for name, got in sorted(attempts.items()):
            print(f"{name:<32}{got['attempted']:>12}{got['completed']:>12}"
                  f"{got['failed']:>10}")
        rule()
        for name, got in sorted(attempts.items()):
            for failure in got.get("failures", []):
                print(f"  {name} LOST {failure['cell_id']}")
                print(f"    {failure['error']}")
    primary = section_p1(arms, population)
    p2 = section_p2(arms, population, jd5b_stats, jd5b_note)
    paired = section_p2_paired(arms, jd5b_rows, population)
    section_p3(arms, population, jd5b_stats)
    section_recorded(arms, population, m0, jd5b_stats, scans)
    section_outcome(primary, p2, paired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
