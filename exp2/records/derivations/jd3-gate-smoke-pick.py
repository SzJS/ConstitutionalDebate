"""Pick the six cells the ADMISSIBILITY-PROMPT smoke runs on, and write them as a cases
file.

    cd exp2
    uv run python records/derivations/jd3-gate-smoke-pick.py \
        2>&1 | tee outputs/jd3-gate-smoke-pick.log

Read-only over `outputs/experiments/jd3-main` and `data/cases/ftf-all.jsonl`; writes
exactly one file, `data/cases/jd3-gate-smoke.jsonl`. It touches nothing under
`outputs/experiments/`.

WHY A SMOKE AT ALL. The house rule (`HANDOFF.md` §2.8, and MEMORY): any new or changed
prompt is tried on about six chosen examples and READ before a slice or a sweep. The
admissibility prompt of M4 is new, so it is read first.

WHY THESE SIX AND NOT A RANDOM DRAW. The gate's whole job is to separate objections worth
hearing from objections not worth hearing, and the only signal on the tree at the time of
the pick is what the recourse judge did with each: three objections Maverick OVERTURNED
the decision on and three it UPHELD. That is the contrast the reader needs — a gate that
admits all six, or refuses all six, has told us nothing, and one whose admissions line up
with the overturns is at least reading the same documents the judge read.

It is NOT a validation set and the alignment is not a score. The judge's ruling is about
MATERIALITY and the gate's answer is about whether the alleged defect is REAL, which are
different questions on purpose; an objection can be perfectly real and immaterial, and a
specious one can move a judge. What the six are for is reading the gate's per-defect
findings against the two documents by hand.

WHEN THE GRADES EXIST, PICK ON THEM INSTEAD. The grader's per-defect verdict is the
nearest thing on this tree to an independent answer to the gate's own question, so once
`jd3-main`'s `grade` stage has run the better draw is three objections graded VALID and
three graded INVALID. This script prefers that split automatically and says which basis
it used; at the time it was first run the grade stage had not started.

Items, not cells, because a cases file is a list of items — and every CONTESTED cell of a
chosen item is gated, which on a debate-only grid of one repeat is the one cell.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TREE = REPO / "outputs" / "experiments" / "jd3-main"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "jd3-gate-smoke.jsonl"
PER_SIDE = 3


def contested_cells() -> list[dict]:
    """One row per contested cell of the tree, read off the run directories.

    Off the filesystem rather than off `index.jsonl`, because the arm is still running
    when this is asked and the index is written by the LAST stage.
    """
    rows = []
    for challenge_path in sorted(TREE.glob("cells/*/contests/*/runs/*/challenge.json")):
        directory = challenge_path.parent
        try:
            challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if challenge.get("stance") != "contests":
            continue
        ruling_path = directory / "ruling.json"
        if not ruling_path.is_file():
            continue
        try:
            ruling = json.loads(ruling_path.read_text(encoding="utf-8"))
            manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
            parent = json.loads(
                (directory / "parent" / "verdict.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        grade = None
        grade_path = directory / "grade.json"
        if grade_path.is_file():
            try:
                grade = json.loads(grade_path.read_text(encoding="utf-8")).get("valid")
            except (OSError, ValueError):
                grade = None
        rows.append({
            "cell_id": manifest.get("cell_id", directory.parents[2].parent.name),
            "item_id": manifest.get("item_id"),
            "subset": manifest.get("subset"),
            "defects_n": len(challenge.get("defects") or []),
            "overturned": bool(ruling.get("changed_the_decision")),
            "initially_correct": parent.get("correct"),
            "grade_valid": grade,
            "dir": str(directory),
        })
    return rows


def spread(rows: list[dict], n: int) -> list[dict]:
    """Up to ``n`` rows, one subset at a time, so six cells are not six python800 cells.

    The smoke is read by a person and the point of the spread is that the six records do
    not all look alike; nothing downstream depends on the order.
    """
    chosen: list[dict] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda r: (r["subset"] or "", r["cell_id"])):
        if len(chosen) >= n:
            break
        if row["subset"] in seen:
            continue
        seen.add(row["subset"])
        chosen.append(row)
    for row in sorted(rows, key=lambda r: (r["subset"] or "", r["cell_id"])):
        if len(chosen) >= n:
            break
        if row not in chosen:
            chosen.append(row)
    return chosen[:n]


def main() -> int:
    rows = contested_cells()
    print(f"contested cells with a ruling in {TREE}: {len(rows)}")
    if not rows:
        print("  NOT RUN — nothing to pick from.")
        return 1

    graded = [r for r in rows if r["grade_valid"] is not None]
    print(f"of those, graded so far: {len(graded)}")
    if len(graded) >= 2 * PER_SIDE:
        basis = "the GRADER's verdict (valid / invalid)"
        left = [r for r in graded if r["grade_valid"]]
        right = [r for r in graded if not r["grade_valid"]]
        names = ("graded VALID", "graded INVALID")
    else:
        basis = "the RECOURSE JUDGE's ruling (overturned / upheld)"
        left = [r for r in rows if r["overturned"]]
        right = [r for r in rows if not r["overturned"]]
        names = ("OVERTURNED", "UPHELD")
    print(f"picking on: {basis}")
    print(f"  {names[0]:<16} {len(left)} available")
    print(f"  {names[1]:<16} {len(right)} available")

    chosen = spread(left, PER_SIDE) + spread(right, PER_SIDE)
    if len(chosen) < 2 * PER_SIDE:
        print(f"  ! only {len(chosen)} cells available; the smoke will be smaller.")

    print()
    print(f"{'cell_id':<52}{'side':>12}{'defects':>9}{'M0 right':>10}")
    print("-" * 100)
    for row, side in zip(chosen, [names[0]] * PER_SIDE + [names[1]] * PER_SIDE):
        print(f"{row['cell_id']:<52}{side:>12}{row['defects_n']:>9}"
              f"{str(row['initially_correct']):>10}")
    print("-" * 100)
    print(f"subsets: {dict(Counter(r['subset'] for r in chosen))}")

    wanted = {r["item_id"] for r in chosen}
    cases = [line for line in CORPUS.read_text(encoding="utf-8").splitlines()
             if line.strip() and json.loads(line)["item"]["item_id"] in wanted]
    if len(cases) != len(wanted):
        print(f"  ! {len(wanted)} items wanted, {len(cases)} found in {CORPUS}")
        return 1
    OUT.write_text("\n".join(cases) + "\n", encoding="utf-8")
    print(f"\nwrote {len(cases)} items -> {OUT}")
    print("THE SMOKE WILL MAKE ONE ADMISSIBILITY CALL PER CONTESTED CELL OF THOSE ITEMS "
          f"({len(chosen)} expected); `exp2-experiment --dry-run` computes the same "
          "figure independently off the source tree and the two are expected to agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
