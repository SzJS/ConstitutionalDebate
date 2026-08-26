"""The phantom-corrected funnel, re-derived from the committed `index.jsonl`.

Every funnel in `records/experiments/sweep/CHECKLIST.md` above its phantom section
counts a contest whenever the challenger's `Decision:` line said REVERSE. 585 of the
sweep's 1,129 contests (51.8%) are **phantom**: the line says REVERSE and the prose
argues the decision was right. This script recomputes the funnel with a contest counted
as a genuine detection only when

    challenge_stance == "contests"   (the line word was REVERSE)
  AND prose_stance    == "WRONG"     (the `agreement` stage read the prose as arguing
                                      the verdict was wrong)

and joins that with `changed_the_decision` for the revision half. It prints, in order:
the phantom-corrected detection table, the overall per-condition phantom share, the
false-alarm table, revision given a genuine contest, the end-to-end line, and the net
effect of the whole contest process on accuracy.

    uv run python records/derivations/sweep-phantom-corrected.py [index.jsonl]
    # default: records/experiments/sweep/index.jsonl

**It reads the committed index and nothing else.** No `outputs/` tree, no `calls.jsonl`,
no per-cell run directory, no network, no API key — so it runs on a blank machine
immediately after `git clone`, which is the whole point of it existing beside the log it
reproduces (`records/experiments/sweep/phantom-corrected.log`, quoted verbatim in
`CHECKLIST.md`'s "THE PHANTOM-CORRECTED FUNNEL" and in `LLM_NOTES.md` §3s(b)).

**Why the correction is legitimate.** It uses only the **REVERSE half** of the
`agreement` instrument. The 20-reply hand check (`records/experiments/sweep/
HANDCHECK-agreement.md`) found agreement 14/20, and all six misreads were on **STANDS**
lines whose prose in fact endorsed the verdict — not one misread was on a REVERSE line,
and every REVERSE reply in the sample was read correctly or defensibly. The half of the
instrument this correction stands on is the half that audited clean. The STANDS half,
which the same audit found faulty and always in the direction of over-calling
disagreement, is **not** used: no decline is promoted into a detection here.

**The caveat this recomputation inherits.** Seven contest runs failed with a challenge
written and no ruling — the re-decider truncated at `max_tokens=16384` — so they carry
no `ruling_form` and `changed_the_decision: false` into `index.jsonl`. Both
`metrics.json` and this script therefore count them as **not revised**: an absent ruling
read as a ruling that the decision stood. It is 7 of 5,724 and it moves no rate in any
table below, but it is a silent default rather than a measured False. Five of the seven
are genuine contests (prose WRONG), one of those on an incorrect decision.

**Two denominators for "phantom share", and they differ on purpose.** The share in the
first table is computed **on incorrect decisions only** — (raw − true) / raw within that
condition's incorrect cell — because that is the cell the detection rate is about. The
separate small table after it gives the share over **all** of a condition's contests
(55.2% / 42.9% / 56.4%), which is the figure `LLM_NOTES.md` §3s reports earlier. Both are
correct; they differ because phantoms are far commoner when the decision was CORRECT.
Label the denominator every time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

INDEX = Path(sys.argv[1] if len(sys.argv) > 1 else "records/experiments/sweep/index.jsonl")
CONDS = ("single", "self_critique", "debate")


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def pct0(num, den):
    return f"{100.0 * num / den:.0f}%" if den else "n/a"


rows = [json.loads(line) for line in INDEX.read_text().splitlines() if line.strip()]
by_cond = {c: [r for r in rows if r["condition"] == c] for c in CONDS}


def contests(rs):
    """The RAW contests: the `Decision:` line said REVERSE."""
    return [r for r in rs if r["challenge_stance"] == "contests"]


def genuine(rs):
    """The TRUE contests: line REVERSE *and* the agreement stage read the prose as WRONG."""
    return [r for r in contests(rs) if r["prose_stance"] == "WRONG"]


print("PHANTOM-CORRECTED FUNNEL — a contest counts only if the LINE says REVERSE *and*")
print("the agreement stage reads the PROSE as arguing the verdict was WRONG.")
print("(My 20-reply hand check found REVERSE lines read correctly in every sampled case,")
print(" so this correction rests on the part of the instrument that audited clean.)")
print()
print("The 'phantom share' column below is ON INCORRECT DECISIONS ONLY: (raw-true)/raw")
print("within the incorrect cell. The share over ALL contests is the table after it.")
print("condition           n            errors    RAW detect|inc   TRUE detect|inc   phantom share")
print("-" * 91)
for c in CONDS:
    rs = by_cond[c]
    inc = [r for r in rs if r["initially_incorrect"]]
    raw, tru = contests(inc), genuine(inc)
    share = pct(len(raw) - len(tru), len(raw))
    print(
        f"{c:<13}{len(rs):>8}{f'{len(inc)}/{len(rs)}':>11}{pct(len(inc), len(rs)):>8}"
        f"{f'{len(raw)}/{len(inc)}':>10}{pct(len(raw), len(inc)):>9}"
        f"{f'{len(tru)}/{len(inc)}':>10}{pct(len(tru), len(inc)):>9}{share:>16}"
    )

print()
print("PHANTOM SHARE OVER **ALL** CONTESTS (the denominator LLM_NOTES §3s reports first):")
print("condition        phantom/contests   share")
print("-" * 42)
for c in CONDS:
    raw = contests(by_cond[c])
    # `phantom_contest` in the index is prose_stance == RIGHT specifically, so the 7
    # contests whose prose read NEITHER count as neither phantom nor genuine in THIS
    # table. The first table's share is (raw - true)/raw, which does put NEITHER on the
    # non-genuine side; on the incorrect cell that is 0 NEITHER rows for single and 1
    # each for self_critique and debate, which is why the two are not the same arithmetic
    # even before the denominators differ.
    ph = [r for r in raw if r["phantom_contest"]]
    print(f"{c:<14}{f'{len(ph)}/{len(raw)}':>16}{pct(len(ph), len(raw)):>10}")
print("The two denominators differ because phantoms are far commoner on CORRECT decisions —")
print("a challenger with nothing real to say is the one most likely to write REVERSE over")
print("prose that endorses the verdict — so the all-contests share is the higher of the two")
print("wherever a condition gets most of its decisions right.")

print()
print("FALSE ALARMS on CORRECT decisions (the specious-objection side):")
print("condition        correct n        RAW raised  TRUE (prose WRONG)")
print("-" * 64)
for c in CONDS:
    cor = [r for r in by_cond[c] if r["initially_correct"]]
    raw, tru = contests(cor), genuine(cor)
    print(
        f"{c:<14}{len(cor):>12}   {f'{len(raw)}/{len(cor)}':<11}{pct(len(raw), len(cor)):>5}"
        f"   {f'{len(tru)}/{len(cor)}':<11}{pct(len(tru), len(cor)):>5}"
    )

print()
print("REVISION, restricted to GENUINE contests (line REVERSE + prose WRONG):")
print("condition         genuine|inc   revised    rate     genuine|cor   broken    rate")
print("-" * 80)
end_to_end = {}
for c in CONDS:
    rs = by_cond[c]
    inc = [r for r in rs if r["initially_incorrect"]]
    cor = [r for r in rs if r["initially_correct"]]
    gi, gc = genuine(inc), genuine(cor)
    # the 7 null-ruling cells carry changed_the_decision=false: counted as NOT revised
    revised = [r for r in gi if r["changed_the_decision"]]
    broken = [r for r in gc if r["changed_the_decision"]]
    end_to_end[c] = (len(revised), len(inc))
    print(
        f"{c:<13}{len(gi):>16}{len(revised):>10}{pct0(len(revised), len(gi)):>8}"
        f"{len(gc):>16}{len(broken):>9}{pct0(len(broken), len(gc)):>8}"
    )

print()
print("END-TO-END: of a condition's OWN wrong decisions, what fraction were genuinely")
print("contested AND actually overturned?  (detection x revision, unconditional)")
for c in CONDS:
    num, den = end_to_end[c]
    print(f"  {c:<14}{f'{num}/{den}':>10}{pct(num, den):>9}")

print()
print("NET EFFECT OF THE WHOLE CONTEST PROCESS ON ACCURACY")
print("(a cell's final verdict = the ruling if the contest produced one, else the decision)")
print("condition           n  acc before  acc after   change    fixed  broken  net cells")
print("-" * 81)
for c in CONDS:
    rs = by_cond[c]
    before = sum(1 for r in rs if r["initially_correct"])
    after = sum(1 for r in rs if r["final_correct"])
    fixed = sum(1 for r in rs if not r["initially_correct"] and r["final_correct"])
    broke = sum(1 for r in rs if r["initially_correct"] and not r["final_correct"])
    change = 100.0 * after / len(rs) - 100.0 * before / len(rs)
    print(
        f"{c:<13}{len(rs):>8}{pct(before, len(rs)):>12}{pct(after, len(rs)):>11}"
        f"{f'{change:+.1f}%':>9}{fixed:>9}{broke:>8}{f'{fixed - broke:+d}':>11}"
    )
