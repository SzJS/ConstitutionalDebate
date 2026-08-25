"""The per-subset and per-label_basis funnel, from `metrics.json`.

sweep-1 is the first run drawn from every subset, so it is the first that can be asked
whether debate's contestability differs across domains. This prints the five numbers
that question turns on, per condition per stratum:

    accuracy                 n_correct / n            (the judge, not the challenger)
    contest rate             contests / n
    phantom rate             phantom contests / contests   (the A4 instrument)
    revised | incorrect      the contestability claim's numerator
    revised | correct        its cost

**Read the n before the rate.** These cells are small by construction -- 241 items over
seven subsets and three conditions -- so a subset cell here is a few dozen decisions.
A cross-subset difference at n=15 is a hypothesis; nothing here is powered to be a
finding.

Also: `revised_given_incorrect` is NOT comparable across conditions, because the
conditions do not err on the same items or at the same rate. `metrics.json`'s own
`caveats` block says so; this table inherits the caveat.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/experiments/sweep-1")
m = json.loads((ROOT / "metrics.json").read_text())
index = [json.loads(l) for l in (ROOT / "index.jsonl").open() if l.strip()]
CONDS = ("single", "self_critique", "debate")


def frac(rate):
    """k/n pct, or 'k/0 --' where the denominator is empty."""
    if rate is None or rate["n"] == 0:
        return f"{0 if rate is None else rate['k']}/0 --"
    return f"{rate['k']}/{rate['n']} {rate['rate']:.0%}"


def contests_of(block):
    """n minus the other stances. `agrees` is structurally 0 under the one-line
    instrument (LLM_NOTES 3n); it is subtracted rather than assumed away."""
    r = block["rates"]
    return (block["n"] - r["declined"]["k"] - r["unclear_stance"]["k"]
            - r["agreed_with_decision"]["k"])


HEAD = (f"{'condition':<15}{'stratum':<18}{'n':>4}{'acc':>7}{'errs':>6}"
        f"{'contest':>14}{'phantom':>13}{'rev|incorr':>14}{'rev|corr':>14}")


def line(cond, stratum, b):
    r = b["rates"]
    n = b["n"]
    c = contests_of(b)
    acc = b["n_correct"] / n if n else 0.0
    return (f"{cond:<15}{stratum:<18}{n:>4}{acc:>6.0%}{b['n_incorrect']:>6}"
            f"{f'{c}/{n} {c / n:.0%}':>14}"
            f"{frac(r['phantom_contest']):>13}"
            f"{frac(r['revised_given_incorrect']):>14}"
            f"{frac(r['revised_given_correct']):>14}")


def table(title, key, order):
    print(f"\n{'=' * 106}\n{title}\n{'=' * 106}")
    print(HEAD)
    print("-" * 106)
    for cond in CONDS:
        blocks = m[key].get(cond, {})
        for stratum in order:
            b = blocks.get(stratum)
            if b:
                print(line(cond, stratum, b))
        print("-" * 106)


subsets = sorted({r["subset"] for r in index})
bases = sorted({r["label_basis"] for r in index})

print(f"root: {ROOT}   rows indexed: {len(index)}")
print(f"subsets: {subsets}")
print(f"label bases: {bases}")

print("\ndecided cells per subset per condition, and items behind them:")
per = Counter((r["subset"], r["condition"]) for r in index)
print(f"{'subset':<14}" + "".join(f"{c:>16}" for c in CONDS) + f"{'items':>8}")
for s in subsets:
    items = len({r["item_id"] for r in index if r["subset"] == s})
    print(f"{s:<14}" + "".join(f"{per[(s, c)]:>16}" for c in CONDS) + f"{items:>8}")

table("BY CONDITION x SUBSET", "by_condition_and_subset", subsets)
table("BY CONDITION x LABEL_BASIS", "by_condition_and_label_basis", bases)

print(f"\n{'=' * 106}\nPOOLED per condition, the same columns\n{'=' * 106}")
print(HEAD)
print("-" * 106)
for cond in CONDS:
    print(line(cond, "(all)", m["by_condition"][cond]))
print(line("ALL", "(all)", m["overall"]))

print("\nCAVEATS carried from metrics.json:")
for c in m.get("caveats", []):
    print(f"  - {c}")
small = m.get("small_cells")
if small:
    print("\nsmall cells flagged by analysis:")
    print(json.dumps(small, indent=1)[:2000])
