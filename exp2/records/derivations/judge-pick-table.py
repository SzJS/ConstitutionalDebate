"""THE JUDGE PICK — one table, nine candidates, 82 stored objections each.

    cd exp2
    uv run python records/derivations/judge-pick-table.py \
        2>&1 | tee outputs/judge-pick-table.log

Stdlib only, and it reads only committed-shape artifacts: each candidate's two
`index.jsonl` files (one per source pilot) for the outcome columns, and each tree's
`calls.jsonl` for the two operational ones ($/ruling on the wire and p95 latency), which
the index does not carry.

WHAT IS BEING COMPARED, AND WHAT IS HELD CONSTANT. Every row is the SAME 82 objections —
45 from `judgment-debate-pilot`, 37 from `judgment-debate-pilot-2`, over the same 60
pilot-3 debate cells — re-ruled under the SAME materiality prompt against the SAME sweep
decisions. The only thing that varies down the table is `recourse_judge_model`. That is
what makes the columns comparable at all; `ruling_prompt_form` is asserted to be
`materiality` on every ruling and the script refuses a tree where it is not.

THE MECHANICAL RULE, from `records/experiments/judgment-debate-2/PREREG.md` and written
before any candidate was called:

    eligible  = strict ruling-line mismatch LOWER than nano's
                AND discrimination GREATER THAN OR EQUAL TO nano's
    pick      = among eligible, the highest net; ties broken by the cheaper measured
                $/ruling
    no pick   = nobody eligible, reported as such, and arms A/C/E do not run

`openai/gpt-4.1-nano` is the floor and `openai/gpt-4.1` the ceiling; NEITHER is eligible.
Nano is in the table because it is the comparator the rule is written against — the same
82 objections under the same prompt, so "lower than nano's" is a difference between two
measurements and not between a measurement and a memory. gpt-4.1 is in it to say what the
numbers look like when the judge is not the weak link.

THE TWO MISMATCH COLUMNS, and why both. `ruling_line_mismatch` is the `ruling_agreement`
instrument: a grader reads the judge's own prose and says what it CONCLUDES (STANDS /
CHANGED / NEITHER), and a mismatch is a ruling whose recorded line contradicts that
reading. NEITHER — the reader settled on nothing — has always counted as a mismatch here,
which is conservative and is the number `metrics.json` prints. The STRICT rate excludes
NEITHER and counts only rulings whose prose actually contradicts their line. The rule uses
the STRICT one, because a reader that could not decide is evidence about the reader, and
the conservative rate is printed beside it so a reader can see how much of the gap is
which.

n = 82. That is small, and the rule is written so that the choice is not made after the
numbers.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path

OUTPUTS = Path("outputs/experiments")
W = 132

# (slug, model id, role). Order is the table's order: the two reference rows first.
CANDIDATES = [
    ("gpt-4.1-nano", "openai/gpt-4.1-nano", "FLOOR (ref, not eligible)"),
    ("gpt-4.1", "openai/gpt-4.1", "CEILING (ref, not eligible)"),
    ("gpt-4.1-mini", "openai/gpt-4.1-mini", "candidate"),
    ("gpt-5.6-luna", "openai/gpt-5.6-luna", "candidate"),
    ("qwen3.8-27b", "qwen/qwen3.8-27b", "candidate"),
    ("kimi-k2.6", "moonshotai/kimi-k2.6", "candidate"),
    ("llama-4-maverick", "meta-llama/llama-4-maverick", "candidate"),
    ("nemotron-3-nano", "nvidia/nemotron-3-nano-30b-a3b", "candidate"),
    ("mistral-small-4", "mistralai/mistral-small-2603", "candidate"),
]
SOURCES = ("pilot1", "pilot2")
FLOOR = "gpt-4.1-nano"
NOT_ELIGIBLE = {"gpt-4.1-nano", "gpt-4.1"}

# The intelligence index each model carries on artificialanalysis.ai, read on 2026-08-28,
# and the delta from the CHALLENGER's own — `google/gemini-2.5-flash` NON-REASONING, which
# is the row that describes how this experiment runs it (`reasoning_effort = "off"`). The
# reasoning row is 20 and is not the one that applies. UNKNOWN where the site has no
# figure; a blank cost-per-task cell is what a deprecated row looks like there.
FLASH_INDEX = 14
INDEX = {
    "gpt-4.1-nano": (10, "UNKNOWN"),
    "gpt-4.1": (20, "UNKNOWN"),
    "gpt-4.1-mini": (15, "$0.05"),
    "gpt-5.6-luna": (27, "$0.01"),
    "qwen3.8-27b": (35, "$0.43"),
    "kimi-k2.6": (35, "UNKNOWN"),
    "llama-4-maverick": (14, "UNKNOWN"),
    "nemotron-3-nano": (15, "UNKNOWN"),
    "mistral-small-4": (12, "UNKNOWN"),
}


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar — the same function as
    `records/derivations/judgment-debate-vs-alone.py`, kept identical so the two scripts
    cannot disagree about a p-value in the third decimal."""
    n = b + c
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def load_rows(slug: str) -> list[dict]:
    """The candidate's 82 rows, both sources, tagged with which pilot each came from.

    The two pilots re-rule the same 60 CELLS, so the cell ids collide across them and the
    rows may not be keyed on cell_id alone — they are two different objections about the
    same decision and both belong in the denominator.
    """
    rows = []
    for source in SOURCES:
        path = OUTPUTS / f"judge-pick-{slug}-{source}" / "index.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["_source"] = source
            rows.append(row)
    return rows


def wire(slug: str) -> dict:
    """$/ruling and latency, off each tree's own `calls.jsonl`.

    The ruling calls only — `role == "recourse_judge"`. The `ruling_reader` calls are
    Haiku's and are identical across every row of the table, so charging them to a
    candidate would add the same constant to every row and make the cheap ones look
    dearer than they are. Every ATTEMPT counts, including a format repair: the question
    is what a ruling costs, and a model that needs two calls to produce one costs two.
    """
    costs, latencies, statuses = [], [], Counter()
    for source in SOURCES:
        tree = OUTPUTS / f"judge-pick-{slug}-{source}"
        for path in tree.glob("cells/*/contests/*/runs/*/calls.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                call = json.loads(line)
                if call.get("role") != "recourse_judge":
                    continue
                statuses[call.get("status")] += 1
                costs.append((call.get("usage") or {}).get("cost") or 0.0)
                if call.get("latency_ms") is not None:
                    latencies.append(call["latency_ms"])
    latencies.sort()
    p95 = (latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))] / 1000.0
           if latencies else None)
    return {"calls": sum(statuses.values()), "cost": sum(costs), "p95_s": p95,
            "non_2xx": sum(n for s, n in statuses.items()
                           if not (s and 200 <= s < 300))}


def measure(slug: str) -> dict | None:
    rows = load_rows(slug)
    if not rows:
        return None
    ruled = [r for r in rows if r.get("ruling_form") is not None]
    forms = {r.get("ruling_prompt_form") for r in ruled}
    if ruled and forms != {"materiality"}:
        raise SystemExit(
            f"{slug}: rulings under {forms} — every row of this table must be the "
            "materiality prompt or the columns are not comparable")

    wrong = [r for r in ruled if r.get("initially_incorrect")]
    right = [r for r in ruled if r.get("initially_correct")]
    ow = sum(1 for r in wrong if r.get("changed_the_decision"))
    orr = sum(1 for r in right if r.get("changed_the_decision"))
    overturn_wrong = ow / len(wrong) if wrong else None
    overturn_right = orr / len(right) if right else None
    discrimination = (None if overturn_wrong is None or overturn_right is None
                      else 100.0 * (overturn_wrong - overturn_right))

    # The two mismatch rates. Conservative counts NEITHER as a mismatch (what
    # `metrics.json` prints); strict excludes the rows the reader could not settle.
    read = [r for r in ruled if r.get("ruling_line_mismatch") is not None]
    conservative = sum(1 for r in read if r["ruling_line_mismatch"])
    decided = [r for r in read if r.get("ruling_prose_conclusion") != "NEITHER"]
    strict = sum(1 for r in decided if r["ruling_line_mismatch"])
    neither = len(read) - len(decided)

    # fixed / broken / net over EVERY row with a gold label, contested or not: a cell
    # nobody objected to keeps its before-state, which is the reading `metrics.json` and
    # `sweep-phantom-corrected.py` both take.
    fixed = broken = 0
    for row in rows:
        before = row.get("initially_correct")
        if before is None:
            continue
        final = row.get("final_correct")
        after = before if final is None else bool(final)
        if before and not after:
            broken += 1
        elif after and not before:
            fixed += 1

    w = wire(slug)
    return {
        "slug": slug, "rows": len(rows), "ruled": len(ruled),
        "overturn_wrong": overturn_wrong, "n_wrong": len(wrong), "k_wrong": ow,
        "overturn_right": overturn_right, "n_right": len(right), "k_right": orr,
        "discrimination": discrimination,
        "strict": strict, "n_strict": len(decided),
        "conservative": conservative, "n_conservative": len(read), "neither": neither,
        "fixed": fixed, "broken": broken, "net": fixed - broken,
        "p": mcnemar_exact(fixed, broken),
        **{f"wire_{k}": v for k, v in w.items()},
        "per_ruling": (w["cost"] / w["calls"]) if w["calls"] else None,
    }


def main() -> int:
    print("=" * W)
    print("THE JUDGE PICK — nine candidates, the same 82 stored objections, the same "
          "materiality prompt")
    print("=" * W)
    print("Population: 45 objections from `judgment-debate-pilot` + 37 from "
          "`judgment-debate-pilot-2`, over the same 60 pilot-3 debate cells.")
    print("Decisions read from `outputs/experiments/sweep`; nothing decided, nothing "
          "re-contested, only the ruling re-made.")
    print("Intelligence index is artificialanalysis.ai, read 2026-08-28; the delta is "
          f"from `google/gemini-2.5-flash` NON-REASONING = {FLASH_INDEX},")
    print("which is the row that describes how this experiment runs it "
          "(`reasoning_effort = \"off\"`). Its reasoning row is 20.")
    print()

    measured = {}
    for slug, model, role in CANDIDATES:
        result = measure(slug)
        if result is None:
            print(f"  ! {slug}: no index.jsonl — the run did not produce a tree")
            continue
        result["model"], result["role"] = model, role
        measured[slug] = result

    floor = measured.get(FLOOR)

    header = (f"{'model':<32}{'idx':>4}{'d':>4}{'$/task':>8}"
              f"{'ovt wrong':>12}{'ovt right':>12}{'discr':>8}"
              f"{'strict':>13}{'consv':>13}{'fix':>5}{'brk':>5}{'net':>5}"
              f"{'$/ruling':>10}{'p95 s':>8}{'verdict':>10}")
    print(header)
    print("-" * W)
    for slug, model, role in CANDIDATES:
        r = measured.get(slug)
        if r is None:
            continue
        index, per_task = INDEX[slug]
        eligible = None
        if slug not in NOT_ELIGIBLE and floor:
            lower = (r["strict"] / r["n_strict"] if r["n_strict"] else 1.0) < (
                floor["strict"] / floor["n_strict"] if floor["n_strict"] else 1.0)
            keeps = (r["discrimination"] is not None
                     and floor["discrimination"] is not None
                     and r["discrimination"] >= floor["discrimination"])
            eligible = lower and keeps
        verdict = ("ref" if slug in NOT_ELIGIBLE
                   else "PASS" if eligible else "FAIL")
        # Formatted into locals first: the columns are wide and an f-string that reached
        # into the dict inside its own width spec is a line nobody can check.
        discr = ("n/a" if r["discrimination"] is None
                 else f"{r['discrimination']:+.1f}")
        strict = f"{r['strict']}/{r['n_strict']} " + pct(r["strict"], r["n_strict"])
        consv = (f"{r['conservative']}/{r['n_conservative']} "
                 + pct(r["conservative"], r["n_conservative"]))
        per = "n/a" if not r["per_ruling"] else f"${r['per_ruling']:.5f}"
        p95 = "n/a" if not r["wire_p95_s"] else f"{r['wire_p95_s']:.1f}"
        print(f"{model:<32}{index:>4}{index - FLASH_INDEX:>+4}{per_task:>8}"
              f"{pct(r['k_wrong'], r['n_wrong']):>12}"
              f"{pct(r['k_right'], r['n_right']):>12}"
              f"{discr:>8}{strict:>13}{consv:>13}"
              f"{r['fixed']:>5}{r['broken']:>5}{r['net']:>+5}"
              f"{per:>10}{p95:>8}{verdict:>10}")
    print("-" * W)
    print()

    # per-row detail the table cannot hold
    print("Per row, in full:")
    for slug, model, role in CANDIDATES:
        r = measured.get(slug)
        if r is None:
            continue
        print(f"  {model:<32} {role:<28} rows {r['rows']}  ruled {r['ruled']}  "
              f"read {r['n_conservative']} (NEITHER {r['neither']})  "
              f"calls {r['wire_calls']} (non-2xx {r['wire_non_2xx']})  "
              f"spend ${r['wire_cost']:.4f}  McNemar p = {r['p']:.4g}")
    print()

    if floor is None:
        print("NO FLOOR ROW — nano did not run, so the rule cannot be applied.")
        return 1

    floor_strict = floor["strict"] / floor["n_strict"] if floor["n_strict"] else 1.0
    print("THE RULE, applied:")
    print(f"  nano's strict mismatch   {floor['strict']}/{floor['n_strict']} "
          f"{pct(floor['strict'], floor['n_strict'])}   — a candidate must be BELOW this")
    print(f"  nano's discrimination    {floor['discrimination']:+.1f} pts"
          if floor["discrimination"] is not None else
          "  nano's discrimination    n/a")
    print("       — a candidate must be at or above this")
    print()

    eligible = []
    for slug, model, role in CANDIDATES:
        if slug in NOT_ELIGIBLE:
            continue
        r = measured.get(slug)
        if r is None:
            continue
        s = r["strict"] / r["n_strict"] if r["n_strict"] else 1.0
        lower = s < floor_strict
        keeps = (r["discrimination"] is not None
                 and floor["discrimination"] is not None
                 and r["discrimination"] >= floor["discrimination"])
        print(f"  {model:<32} strict {pct(r['strict'], r['n_strict']):>7} "
              f"{'<' if lower else '>='} nano  |  discr "
              f"{r['discrimination']:+.1f} {'>=' if keeps else '<'} nano  ->  "
              f"{'ELIGIBLE' if lower and keeps else 'not eligible'}")
        if lower and keeps:
            eligible.append(r)
    print()
    if not eligible:
        print("NO PICK. No candidate is both more coherent under the materiality rule "
              "than nano and at least as")
        print("discriminating. Arms A, C and E of the 2x3 do not run; arms B and D "
              "(nano) still can, and the")
        print("second-look control is still answerable with the judge the finished run "
              "used.")
        return 0

    # THE LATENCY FILTER, which the plan pre-registers without a number: "a candidate
    # far slower than the rest is dropped and said so". It is an OPERATIONAL filter and
    # it is applied to the whole eligible set, not to a row someone dislikes — but "far
    # slower than the rest" has no threshold, so this script REPORTS both readings and
    # picks neither. Choosing a threshold after seeing which candidate it excludes is
    # exactly the failure `MIN_JUDGE_ACCURACY` is the precedent for.
    p95s = sorted(r["wire_p95_s"] for r in eligible if r["wire_p95_s"])
    median_p95 = statistics.median(p95s) if p95s else 0.0
    slow = [r for r in eligible
            if r["wire_p95_s"] and r["wire_p95_s"] > 3 * median_p95]
    print("LATENCY, measured on these 82 rulings (p95, seconds):")
    for r in sorted(eligible, key=lambda r: r["wire_p95_s"] or 0):
        print(f"  {r['model']:<32} {r['wire_p95_s']:6.1f} s"
              f"    1,148 rulings at 16 concurrent ~ "
              f"{1148 * r['wire_p95_s'] / 16 / 60:5.0f} min per arm")
    print(f"  median of the eligible: {median_p95:.1f} s")
    if slow:
        print(f"  FAR SLOWER THAN THE REST (over 3x the median): "
              f"{', '.join(r['model'] for r in slow)}")
        print("  The plan pre-registers dropping these and saying so, but attaches NO")
        print("  threshold. Both readings are printed below and this script picks")
        print("  neither: a threshold chosen after seeing which row it excludes is not a")
        print("  rule. THE PLANNER DECIDES.")
    print()

    def rank(pool, label):
        pool = sorted(pool, key=lambda r: (-r["net"], r["per_ruling"] or 0.0))
        if not pool:
            print(f"{label}: NO PICK — nobody left after the filter.")
            return None
        best = pool[0]
        tied = [r for r in pool if r["net"] == best["net"]]
        print(f"{label}: {best['model']}")
        print(f"  net {best['net']:+d} ({best['fixed']} fixed / {best['broken']} "
              f"broken), strict mismatch {pct(best['strict'], best['n_strict'])}, "
              f"discrimination {best['discrimination']:+.1f} pts, "
              f"${best['per_ruling']:.5f} per ruling, p95 {best['wire_p95_s']:.1f}s")
        if len(tied) > 1:
            print(f"  tie on net with {', '.join(r['model'] for r in tied[1:])} — "
                  "broken by the cheaper measured $/ruling, which is this one")
        if len(pool) > 1:
            second = pool[1]
            print(f"  runner-up: {second['model']} (net {second['net']:+d}, strict "
                  f"{pct(second['strict'], second['n_strict'])}, "
                  f"${second['per_ruling']:.5f} per ruling, p95 "
                  f"{second['wire_p95_s']:.1f}s)")
        print("  PROJECTED COST OF THE THREE ARMS, from its measured $/ruling:")
        for name, n in (("A  flash-class judge x 1,148 real objections", 1148),
                        ("C  flash-class judge x 1,148 placeholders", 1148),
                        ("E  flash-class judge x 1,148 specious rulings", 1148)):
            print(f"    {name:<48} {n} x ${best['per_ruling']:.5f} = "
                  f"${n * best['per_ruling']:.2f}")
        print(f"    {'the three together':<48} "
              f"${3 * 1148 * best['per_ruling']:.2f} of rulings, plus ~$2.53 each of "
              "Haiku reading")
        print()
        return best

    rank(eligible, "THE PICK, mechanical rule alone")
    if slow:
        rank([r for r in eligible if r not in slow],
             "THE PICK, with the pre-registered latency filter applied first")

    eligible.sort(key=lambda r: (-r["net"], r["per_ruling"] or 0.0))
    best = eligible[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
