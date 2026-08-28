"""Pick the six debate cells the judgment-debate smoke runs on, and write the cases file.

    uv run python records/derivations/judgment-debate-smoke-pick.py \
        2>&1 | tee outputs/judgment-debate-smoke-pick.log

Read-only over `outputs/experiments/judgment-debate-pilot/` (its `index.jsonl` and each
cell's `challenge.json`) and `data/cases/ftf-all.jsonl`; writes exactly one file,
`data/cases/judgment-debate-smoke.jsonl`. It touches nothing under
`outputs/experiments/`.

**Why a hand-picked six rather than a random six.** The smoke is a PROMPT check of two
changes at once, not a measurement, and six cells cannot measure a rate of anything. The
two questions are:

  * does `google/gemini-2.5-flash` now put `Argument:` on a line of its own — it needed a
    format repair on 59 of the pilot's 60 objections; and
  * does the recourse judge, under `RECOURSE_JUDGE_USER_JUDGMENT`, verify each alleged
    defect against the record and then ask whether it is material — where under the
    object-level prompt it re-solved the problem and overturned 35% of CORRECT decisions.

A random six would answer neither reliably. So the six carry the shapes the answers
depend on, two of each:

  * **2 omission-only objections** — the defect type the materiality step is hardest on,
    because "the judgment never addressed this" is real far more often than it is
    material, and an object-level judge has nothing to check it against;
  * **2 misstatement objections** — one of them the party misattribution (`gpqa-127-sound`,
    the judgment credits Bob's examples to Alice) that is real, checkable in one line of
    the record, and says nothing at all about whether the solution is flawed;
  * **2 declines** — the control. A prompt change that turned declines into objections
    would be as bad as one that did the reverse, and both of these are substantive prose
    (452 and 734 characters) rather than the 16-character stub shape, so the boundary the
    format fix moves is actually exercised.

Every one of the six is a `debate` cell (the only condition the run has), every one was
decided by the sweep, and **every one needed exactly one format repair in the pilot** —
so the before figure is a clean 6/6 and any number below it is the change. Four are
decisions the sweep got WRONG and two are decisions it got right, which is the split the
materiality question turns on: the failure being fixed is overturning correct decisions.

The pilot's own outcome for each is printed, so the smoke's rulings can be read against
what the object-level prompt did with the same objection.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PILOT = REPO / "outputs" / "experiments" / "judgment-debate-pilot"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "judgment-debate-smoke.jsonl"

# (item_id, the shape it carries, why it is in the six)
PICKS = [
    ("gpqa-161-flawed", "omission-only",
     "one omission, graded valid, on a decision the sweep got WRONG — the case where a "
     "material defect should overturn"),
    ("law-evi4_gpt3-5_B-s11", "omission-only",
     "one omission, graded valid, on a decision that was CORRECT — the case the "
     "materiality step exists for: a real defect that must not disturb the decision"),
    ("gpqa-127-sound", "misstatement",
     "the party misattribution: the judgment credits Bob's codon examples to Alice. "
     "Real, checkable in one line of the record, and silent about whether the solution "
     "is flawed. Decision was WRONG"),
    ("python800-p03672-sound", "misstatement x2",
     "two misstatements on a WRONG decision in python800 — the subset carrying 51 of "
     "the re-rule's 68 ruling-line mismatches, and the one where 'the text says the "
     "program has a bug' is most easily misread"),
    ("medqa-train_3754", "decline",
     "a substantive decline (452 chars) on a CORRECT decision — the false-alarm "
     "control for the format change"),
    ("theoremqa-solutions-rate_distortion_function_2-png-sound", "decline",
     "a substantive decline (734 chars) on a WRONG decision — declining is the right "
     "answer to 'is the judgment faithful' even where the verdict is not"),
]


def load(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def contest_run(cell_id: str):
    runs = sorted((PILOT / "cells" / cell_id / "contests").glob("*/runs/*"), reverse=True)
    return next((d for d in runs if (d / "challenge.json").is_file()), None)


def repairs(run: Path) -> int:
    """Challenger calls minus one. The pilot's format-repair count for this cell."""
    calls = [json.loads(line) for line in
             (run / "calls.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    return sum(1 for c in calls if c.get("role") == "challenger") - 1


def main() -> int:
    index = {row["cell_id"]: row for row in load(PILOT / "index.jsonl")}
    print(f"pilot index rows {len(index)}   (all condition=debate)")
    print()

    ok = True
    print(f"{'item':<58}{'shape':<16}{'gold':<7}{'decision':<10}"
          f"{'stance':<10}{'repairs':>8}{'pilot ruling':>14}")
    print("-" * 124)
    for item_id, shape, _why in PICKS:
        cell = f"{item_id}__debate__r1"
        row = index.get(cell)
        if row is None:
            print(f"  ! {cell} is not in the pilot index")
            ok = False
            continue
        run = contest_run(cell)
        if run is None:
            print(f"  ! {cell} has no contest record in the pilot tree")
            ok = False
            continue
        n = repairs(run)
        if n != 1:
            # Not fatal — but the before figure stops being a clean 6/6 and the report
            # has to say so rather than quietly comparing against a different baseline.
            print(f"  ! {cell} needed {n} repairs in the pilot, not 1")
        ruled = ("OVERTURN" if row.get("changed_the_decision") else "UPHOLD")
        print(f"{item_id:<58}{shape:<16}"
              f"{('FLAWED' if row['gold_flawed'] else 'SOUND'):<7}"
              f"{('CORRECT' if row['initially_correct'] else 'WRONG'):<10}"
              f"{str(row.get('challenge_stance')):<10}{n:>8}"
              f"{(ruled if row.get('ruling_form') else '-'):>14}")
    print()
    for item_id, _shape, why in PICKS:
        print(f"  {item_id}\n      {why}")
    print()

    wrong = sum(1 for i, _, _ in PICKS
                if index.get(f"{i}__debate__r1", {}).get("initially_correct") is False)
    subsets = {index[f"{i}__debate__r1"]["subset"] for i, _, _ in PICKS
               if f"{i}__debate__r1" in index}
    print(f"decisions that were WRONG: {wrong} of {len(PICKS)}   "
          f"subsets spanned: {len(subsets)} {sorted(subsets)}")
    if len(subsets) < 4:
        print("  ! fewer than four subsets; the smoke would not span the corpus")
    if not ok:
        return 1

    # The case lines are copied VERBATIM out of the corpus rather than rebuilt, so what
    # `load_cases` reads here is byte-identical to what the sweep decided on.
    wanted = {item_id for item_id, _, _ in PICKS}
    lines = [line for line in CORPUS.read_text(encoding="utf-8").splitlines()
             if line.strip() and json.loads(line)["item"]["item_id"] in wanted]
    found = {json.loads(line)["item"]["item_id"] for line in lines}
    if found != wanted:
        print(f"\n  ! not in {CORPUS}: {sorted(wanted - found)}")
        return 1
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {len(lines)} cases -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
