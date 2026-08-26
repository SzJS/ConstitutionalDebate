"""Pick the six items the re-contest smoke runs on, and write them as a cases file.

    uv run python records/derivations/recontest-smoke-pick.py \
        2>&1 | tee outputs/recontest-smoke-pick.log

Read-only over `records/experiments/sweep/index.jsonl` and `data/cases/ftf-all.jsonl`;
writes exactly one file, `data/cases/recontest-smoke.jsonl`. It touches nothing under
`outputs/experiments/sweep/`.

**Why a hand-picked six rather than a random six.** The smoke is a PROMPT check, not a
measurement. The question is whether a challenger that now decides last stops writing
`Decision: REVERSE` over prose that argues the verdict was right, and a random draw of
six items would answer it with two or three phantoms and no controls. So the six are
chosen to carry the shapes the answer depends on:

  * **4 phantoms** — the defect itself, four cells the sweep recorded as REVERSE lines
    over verdict-endorsing prose. Four of them are named in the plan because Fable read
    the replies by hand (`records/experiments/sweep/HANDCHECK-agreement.md`) and called
    them textbook phantoms, so their prose is not in dispute and any change in the
    label is the prompt's doing.
  * **1 genuine REVERSE on a wrong decision** — the case the experiment is FOR. If the
    new prompt merely made the challenger agreeable it would show up here, as a
    detection that was there before and is not any more.
  * **1 STANDS** — the false-alarm control. A prompt that turned declines into
    objections would be as bad as one that did the reverse.

Each item contributes 3 cells (one per condition), so 6 items are 18 cells. Every item
is required to have all three conditions decided in the sweep, or the smoke would run a
condition short and the comparison would be uneven. The six span five subsets, and the
evidence cells cover both a solo condition and debate — the two recourse routings the
sweep ran, which is what `recourse_form = "third_party"` collapses into one.

**On the two ambiguous names.** The hand check writes `theoremqa CRT_1` and
`theoremqa CRT_3` for items whose real ids end `-flawed` or `-sound`, and both variants
of CRT_1 carry a phantom in `single`. The sample was stratified 3 per (line x parent
verdict x prose) cell, and rows 5, 7 and 10 of that table are exactly three REVERSE /
RIGHT replies — so row 7's CRT_1 is the one whose parent verdict matches rows 5 and 10,
i.e. `-sound`. Resolved here rather than left to a prefix match, because a prefix match
would silently pick the other one.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "records" / "experiments" / "sweep" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "recontest-smoke.jsonl"
CONDITIONS = ("single", "self_critique", "debate")
N_PHANTOMS = 4

# The four the plan names, with the reason each is named. Order matters: it is the order
# they are tried in, and a name that is absent from the index — or whose item was not
# decided in all three conditions — is reported and replaced from the general pool
# rather than silently dropped.
PREFERRED_PHANTOMS = [
    ("medqa-train_3412",
     "phantom in `debate` on a CORRECT FLAWED verdict; medqa's final_answer basis, "
     "where a badly-reasoned solution that reached the right answer is labelled sound"),
    ("theoremqa-solutions-Chinese_Remainder_Theorem_1-txt-sound",
     "hand check row 7 — Fable read the reply and called it a textbook phantom: it asks "
     "for a reversal, then verifies the arithmetic and concludes the verdict was right"),
    ("theoremqa-solutions-Chinese_Remainder_Theorem_3-txt-sound",
     "hand check rows 5 and 10 — the same shape twice, in `single` and in "
     "`self_critique`, so one item shows both solo routings"),
    ("gpqa-152-sound",
     "hand check row 8 — a phantom in `debate`, and on a SOUND item wrongly decided "
     "FLAWED, so the objection had a real error to find and did not find it"),
]


def load(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def is_phantom(row):
    """The sweep's own reading: a REVERSE line over prose the grader read as RIGHT."""
    return row.get("phantom_contest") is True


def is_genuine_reverse_on_a_wrong_decision(row):
    return (row.get("challenge_stance") == "contests"
            and row.get("line_prose_agree") is True
            and row.get("initially_correct") is False)


def is_stands(row):
    return (row.get("challenge_stance") == "declined"
            and row.get("line_prose_agree") is True)


def describe(row):
    return (f"{row['cell_id']}  subset={row['subset']} verdict={row['verdict']} "
            f"correct={row['initially_correct']} stance={row.get('challenge_stance')} "
            f"prose={row.get('prose_stance')}")


def main() -> int:
    rows = load(INDEX)
    by_item: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_item[row["item_id"]][row["condition"]] = row
    # Only items the sweep decided in ALL THREE conditions: a smoke that ran 17 cells
    # would compare conditions over different items, which is the confound the whole
    # design spends its randomisation avoiding.
    complete = {item: cells for item, cells in by_item.items()
                if set(cells) == set(CONDITIONS)}
    print(f"index rows {len(rows)}   items {len(by_item)}   "
          f"items decided in all three conditions {len(complete)}")

    picks: list[tuple[str, dict, str]] = []   # (item_id, evidence row, why)
    chosen: set[str] = set()
    subsets: set[str] = set()

    def take(item_id, row, why):
        picks.append((item_id, row, why))
        chosen.add(item_id)
        subsets.add(row["subset"])

    # --- the four phantoms ------------------------------------------------------------
    for item_id, why in PREFERRED_PHANTOMS:
        cells = complete.get(item_id)
        if cells is None:
            print(f"  ! named phantom {item_id} is not an item decided in all three "
                  "conditions; it will be replaced from the pool")
            continue
        phantom_cells = [c for c in cells.values() if is_phantom(c)]
        if not phantom_cells:
            print(f"  ! named phantom {item_id} has no phantom cell in the index; it "
                  "will be replaced from the pool")
            continue
        take(item_id, sorted(phantom_cells, key=lambda r: r["cell_id"])[0], why)

    # Any shortfall is filled from the pool, newest-subset-first so the six keep their
    # spread, and by cell_id inside that so the choice is reproducible.
    pool = sorted((c for cells in complete.values() for c in cells.values()
                   if is_phantom(c)), key=lambda r: r["cell_id"])
    for row in pool:
        if len(picks) >= N_PHANTOMS:
            break
        if row["item_id"] in chosen or row["subset"] in subsets:
            continue
        take(row["item_id"], row, "phantom drawn from the pool, to replace a named one "
                                  "that the index does not carry")
    for row in pool:                      # subset spread exhausted; take any phantom
        if len(picks) >= N_PHANTOMS:
            break
        if row["item_id"] not in chosen:
            take(row["item_id"], row, "phantom drawn from the pool")

    # --- the genuine contest and the decline ------------------------------------------
    # Both are taken from a subset none of the phantoms used, so the six spread as
    # widely as the corpus allows; sorted by cell_id, so the draw is reproducible and
    # not a sample.
    for predicate, why in (
        (is_genuine_reverse_on_a_wrong_decision,
         "genuine REVERSE on a decision that was WRONG — the case the experiment is "
         "for, and the control against a prompt that merely made the challenger "
         "agreeable"),
        (is_stands,
         "STANDS, line and prose agreeing — the false-alarm control, against a prompt "
         "that turned declines into objections"),
    ):
        candidates = sorted((c for cells in complete.values() for c in cells.values()
                             if predicate(c)), key=lambda r: r["cell_id"])
        fresh = [c for c in candidates
                 if c["item_id"] not in chosen and c["subset"] not in subsets]
        if not fresh:
            fresh = [c for c in candidates if c["item_id"] not in chosen]
        if not fresh:
            print(f"  ! nothing in the index satisfies: {why}")
            continue
        take(fresh[0]["item_id"], fresh[0], why)

    # --- report ----------------------------------------------------------------------
    print(f"\npicked {len(picks)} items -> {len(picks) * len(CONDITIONS)} cells")
    for item_id, row, why in picks:
        print(f"\n  {item_id}")
        print(f"    evidence  {describe(row)}")
        print(f"    why       {why}")
    print(f"\nsubsets covered: {sorted(subsets)}")
    conditions_used = sorted({row["condition"] for _, row, _ in picks})
    print(f"conditions the evidence cells come from: {conditions_used}")
    if len(subsets) < 3:
        print("  ! fewer than three subsets; the smoke would not span the corpus")
    if not ({"single", "self_critique"} & set(conditions_used)) or (
            "debate" not in conditions_used):
        print("  ! the evidence cells do not cover both a solo condition and debate")

    # --- write the cases file ---------------------------------------------------------
    # The case lines are copied VERBATIM out of the corpus rather than rebuilt from the
    # index, so what `load_cases` reads here is byte-identical to what the sweep decided
    # on — flaw annotation, label basis and all.
    wanted = {item_id for item_id, _, _ in picks}
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
