"""The MECHANICAL gate — gate 1.b of the judgment-debate-3 additions. No model at all.

    cd exp2
    uv run python records/derivations/jd3-gates.py \
        --tree outputs/experiments/jd3-main \
        --out outputs/jd3-main-gates.jsonl 2>&1 | tee outputs/jd3-main-gates.log

POST HOC. Decided on 2026-08-28, AFTER M1's preliminary numbers were seen, and labelled
as such wherever it appears. `records/derivations/judgment-debate-3.py` reads the file
this writes and prints it as one of three gate rows, each carrying the same label.

WHAT IT DECIDES. An objection is ADMITTED iff **every quotation in it is verbatim in the
document it is attributed to** — every `Judgment says:` quote in the judgment, and every
`Record says:` quote in the record the challenger was shown. Nothing else. No model reads
anything, the answer is a string comparison a reader can redo by hand, and the whole
gate costs nothing to recompute over a finished tree.

WHY IT IS WORTH A ROW. M1's preliminary read showed that a 74%-accurate judge meets a
CORRECT decision three times as often as a wrong one, so an audit that contests
indiscriminately loses more than it fixes. The three gate rows ask what a filter buys,
and they bracket the answer:

    the MECHANICAL gate (this)  the weakest possible filter: no judgement, no reading,
                                only whether the evidence exists. A LOWER bound on what
                                gatekeeping can do.
    M4, the same-class gate     `openai/gpt-4.1-mini` asked whether at least one alleged
                                defect is REAL. The only one of the three a real process
                                could actually run.
    the Haiku-valid bound       count only the objections the GRADER marked valid. The
                                grader is stronger than the judge, so this imports a
                                better reader into the decision path — an UPPER bound,
                                and not a process.

THE TWO HALVES OF THE CHECK ARE NOT THE SAME AGE, and the file says so per defect:

  * the JUDGMENT half already ran, at parse time, on the decision path — it is
    `prompts.defect_quote_in_judgment`, it was pre-registered before the run, and a
    defect that fails it is never sent to the grader. It is RECOMPUTED here from the
    texts rather than read off `challenge.json`, so the gate is one comparison made once
    by one rule; `judgment_flag_stored` carries what the harness recorded, and any
    disagreement between the two is printed rather than absorbed.
  * the RECORD half is new (`prompts.record_quotes_in_record`, 2026-08-28) and is wired
    into NOTHING. Adding it to the decision path would change what the grader was asked
    about objections already written and paid for, which is a rewrite of a finished
    measurement rather than an addition to it.

AND THE OMISSION CARVE-OUT DOES NOT APPLY TO THE RECORD HALF. An omission is excused
from quoting the judgment — there is nothing there to quote, and the prompt asks for the
`(the judgment does not address this)` placeholder by name — but it is NOT excused from
quoting the record: the prompt tells it to quote the point the judgment does not address.
So an omission's record quote is checkable, and it is checked.

NONE IS NOT FALSE, on the rule every column in this repository follows: "not measured"
and "measured and failed" are different facts. A defect that quoted nothing under a label
is None there and does not fail the gate on that half — the grader is what rules on an
objection with no evidence, and counting it here would report the same fact twice under
two names.

AN OBJECTION THAT ALLEGES NO NUMBERED DEFECT IS NOT ADMITTED. Every quotation in it is
vacuously verbatim, because there are none; admitting it would let an objection be heard
on no evidence at all, which is the opposite of what a gate is. `defects_n` is written
beside the flag so a reader can recompute either reading, and the count of cells refused
for that reason alone is printed.

Reads one tree and writes one file. Nothing under the tree is opened for writing, and no
network call is made.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from exp2.persistence import load_run_record
from exp2.prompts import defect_quote_in_judgment, defect_quotes_in_record

W = 100


def rate(num: int, den: int) -> str:
    return f"{num}/{den} {100.0 * num / den:.1f}%" if den else f"{num}/0 n/a"


def contest_runs(tree: Path):
    """Every contest run directory in the tree that holds a `challenge.json`.

    Walked off the filesystem rather than off `index.jsonl`, so this runs on a tree whose
    `analyse` stage has not been reached — which is the state a live campaign is in when
    the question is asked.
    """
    for path in sorted(tree.glob("cells/*/contests/*/runs/*/challenge.json")):
        yield path.parent


def gate_one(directory: Path) -> dict | None:
    """One contest directory's row, or ``None`` if there is nothing to gate.

    ``None`` for a decline (nothing was put to a judge, so there is no ruling to admit)
    and for a directory whose copied decision cannot be read (no record to check the
    quotations against — and a gate that admitted an objection because it could not read
    the document would be the failure this whole check exists to catch).
    """
    try:
        challenge = json.loads((directory / "challenge.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if challenge.get("stance") != "contests":
        return None
    parent = directory / "parent"
    if not parent.is_dir():
        return None
    try:
        record = load_run_record(parent)
    except Exception:
        return None
    judgment = record.decision_grounds
    body = record.challenger_view().body
    manifest = {}
    try:
        manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass

    defects = challenge.get("defects") or []
    flags = []
    for index, defect in enumerate(defects, 1):
        judgment_ok = defect_quote_in_judgment(defect, judgment)
        record_ok = defect_quotes_in_record(defect, body)
        flags.append({
            "index": index,
            "type": defect.get("type"),
            # Recomputed here, and the harness's own answer beside it. They should agree
            # on every defect; a disagreement means the stored flag was written by a
            # different rule and is reported rather than silently preferred.
            "judgment_quotes_ok": judgment_ok,
            "judgment_flag_stored": defect.get("quote_in_judgment"),
            "record_quotes_ok": record_ok,
            "n_judgment_quotes": len(defect.get("judgment_says") or []),
            "n_record_quotes": len(defect.get("record_says") or []),
        })
    # EVERY quotation, on BOTH halves. False fails; None does not — see the docstring.
    failed_judgment = sum(1 for f in flags if f["judgment_quotes_ok"] is False)
    failed_record = sum(1 for f in flags if f["record_quotes_ok"] is False)
    return {
        "cell_id": manifest.get("cell_id") or directory.parents[2].parent.name,
        "item_id": manifest.get("item_id"),
        "subset": manifest.get("subset"),
        "condition": manifest.get("condition"),
        "contest_dir": str(directory),
        "defects_n": len(defects),
        "defects_failing_judgment_quotes": failed_judgment,
        "defects_failing_record_quotes": failed_record,
        "mech_admitted": bool(defects) and not failed_judgment and not failed_record,
        # The two readings of an empty defect list, so a reader can take either without
        # re-running this script. See the docstring: an objection that alleges nothing is
        # refused here.
        "no_defects": not defects,
        "defects": flags,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", type=Path,
                        default=Path("outputs/experiments/jd3-main"),
                        help="the run tree to gate (read-only)")
    parser.add_argument("--out", type=Path,
                        default=Path("outputs/jd3-main-gates.jsonl"),
                        help="where to write one row per contested cell")
    args = parser.parse_args(argv)

    print("=" * W)
    print("THE MECHANICAL GATE — every quotation verbatim, no model  [POST HOC, "
          "added after M1 was seen]")
    print("=" * W)
    print(f"tree: {args.tree}   (read-only)")
    print(f"out:  {args.out}")

    if not args.tree.is_dir():
        print(f"\n  NOT RUN — no tree at {args.tree}.")
        return 1

    rows = []
    skipped = 0
    for directory in contest_runs(args.tree):
        row = gate_one(directory)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    admitted = sum(1 for r in rows if r["mech_admitted"])
    empty = sum(1 for r in rows if r["no_defects"])
    defects = sum(r["defects_n"] for r in rows)
    bad_judgment = sum(r["defects_failing_judgment_quotes"] for r in rows)
    bad_record = sum(r["defects_failing_record_quotes"] for r in rows)
    print()
    print(f"contested objections gated              {len(rows)}")
    print(f"  contests skipped (declined/unreadable) {skipped}")
    print(f"ADMITTED (every quotation verbatim)     {rate(admitted, len(rows))}")
    print(f"  refused for alleging NO defect at all  {rate(empty, len(rows))}")
    print()
    print(f"defects alleged                         {defects}")
    print(f"  failing the JUDGMENT-side check       {rate(bad_judgment, defects)}"
          "   (pre-registered; on the decision path)")
    print(f"  failing the RECORD-side check         {rate(bad_record, defects)}"
          "   (POST HOC; wired into nothing)")

    # The record half is the new one, so what it adds over the half that already ran is
    # the number worth printing: objections that survived the pre-registered check and
    # are refused only because a quotation attributed to the record is not in it.
    only_record = sum(1 for r in rows
                      if r["defects_n"] and not r["defects_failing_judgment_quotes"]
                      and r["defects_failing_record_quotes"])
    print(f"  objections refused by the RECORD half alone   {rate(only_record, len(rows))}")

    # And the two answers to the same question, which must agree.
    disagreements = [f for r in rows for f in r["defects"]
                     if f["judgment_quotes_ok"] != f["judgment_flag_stored"]]
    print(f"\nrecomputed judgment flag vs the one the harness stored: "
          f"{len(disagreements)} disagreement(s) over {defects} defects")
    if disagreements:
        print("  ! the stored flag was written by a different rule. The recomputed one "
              "is what this file carries; investigate before quoting either.")

    by_type: Counter = Counter()
    bad_by_type: Counter = Counter()
    for row in rows:
        for flag in row["defects"]:
            by_type[flag["type"]] += 1
            if flag["record_quotes_ok"] is False:
                bad_by_type[flag["type"]] += 1
    print("\nrecord-side failures by defect type — an OMISSION is excused from quoting")
    print("the judgment and is NOT excused from quoting the record, so this is where the")
    print("unchecked half had the most room:")
    for kind, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"    {str(kind):<16} {rate(bad_by_type[kind], n)}")

    print()
    print("=" * W)
    print("This is a DESCRIPTIVE row and a POST HOC one. It is not an endpoint, it was")
    print("decided after M1's preliminary numbers were seen, and it is the LOWER bound of")
    print("the three gate rows: no model reads anything, so nothing but the existence of")
    print("the evidence is being asked.")
    print("=" * W)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
