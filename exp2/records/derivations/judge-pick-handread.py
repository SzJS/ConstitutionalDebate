"""Rulings from the judge pick, rendered in full for a human to read.

    cd exp2
    uv run python records/derivations/judge-pick-handread.py <pick-slug> [runner-up-slug] \
        > outputs/judge-pick-handread.txt

Six from the pick — three that OVERTURNED and three that UPHELD — and three from the
runner-up, over the same 82 objections. Read-only; it touches nothing.

**What a reader is checking, and it is not the arithmetic.** The table says the pick is
more coherent under the materiality rule than nano and at least as discriminating. Those
are counts of a reader's classification. This is where a person looks at the thing itself
and asks the three questions the counts cannot answer:

  1. Does the ruling actually do the TWO STEPS — is each alleged defect real against the
     record, and if so is it material — or does it re-solve the problem on object-level
     grounds and let its line follow that? The second is the failure `CHECKLIST.md` §0
     found nano committing 79 times: the judge setting aside the rule it was given.
  2. Does the final line follow from the reasoning above it? A ruling whose prose finds a
     defect real and material and then copies the parent's line is the OTHER half of
     nano's 30% residual, and it is invisible in a net figure.
  3. Is the ruling about the JUDGMENT — the reasoning given for the decision — or has it
     drifted onto the solution? The materiality prompt exists because the object-level one
     told the judge to disregard the very thing these objections are about.

Everything needed to answer them is printed together: the objection's defect list as
`parse_defects` read it, the ruling's prose in full, the line it ended on, the parent
verdict it was ruling against, and the dataset's gold label — so a reader can see whether
a ruling that came out RIGHT came out right for the reason it gives.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUTPUTS = REPO / "outputs" / "experiments"
SOURCES = ("pilot1", "pilot2")
W = 100


def trees(slug: str):
    for source in SOURCES:
        tree = OUTPUTS / f"judge-pick-{slug}-{source}"
        if tree.is_dir():
            yield source, tree


def rows(slug: str) -> dict[tuple[str, str], dict]:
    out = {}
    for source, tree in trees(slug):
        index = tree / "index.jsonl"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[(source, row["cell_id"])] = row
    return out


def contest_dir(slug: str, source: str, cell_id: str) -> Path | None:
    base = OUTPUTS / f"judge-pick-{slug}-{source}" / "cells" / cell_id / "contests"
    runs = sorted(base.glob("*/runs/*"), reverse=True)
    for directory in runs:
        if (directory / "ruling.json").is_file():
            return directory
    return None


def render(slug: str, source: str, cell_id: str, row: dict, n: int) -> None:
    directory = contest_dir(slug, source, cell_id)
    if directory is None:
        print(f"  ! no contest directory for {cell_id}")
        return
    challenge = json.loads((directory / "challenge.json").read_text(encoding="utf-8"))
    ruling = json.loads((directory / "ruling.json").read_text(encoding="utf-8"))
    reading_path = directory / "ruling_agreement.json"
    reading = (json.loads(reading_path.read_text(encoding="utf-8"))
               if reading_path.is_file() else None)

    print()
    print("=" * W)
    print(f"[{n}] {slug}   {source}   {cell_id}")
    print("=" * W)
    print(f"  subset            {row.get('subset')}    label_basis "
          f"{row.get('label_basis')}    gradable {row.get('gradable')}")
    print(f"  GOLD              {'FLAWED' if row.get('gold_flawed') else 'SOUND'}"
          f"   (the dataset's label; no prompt ever saw it)")
    print(f"  PARENT VERDICT    {ruling.get('parent_verdict')}"
          f"   decided {'CORRECTLY' if row.get('initially_correct') else 'WRONGLY'}")
    print(f"  RULING            {ruling.get('ruling')}  ->  verdict "
          f"{ruling.get('verdict')}   "
          f"{'CORRECT' if ruling.get('correct') else 'WRONG'} after recourse")
    print(f"  prompt form       {ruling.get('prompt_form')}   "
          f"ruling form {ruling.get('form')}   parse {ruling.get('parse_mode')}")
    if reading:
        print(f"  READER            prose says {reading.get('prose_conclusion')}   "
              f"line says {reading.get('line_conclusion')}   "
              f"mismatch {reading.get('mismatch')}")
    print()
    print("-" * W)
    print("  THE OBJECTION — the defect list as `parse_defects` read it")
    print("-" * W)
    defects = challenge.get("defects") or []
    if not defects:
        print("  (no defect list parsed)")
    for i, defect in enumerate(defects, 1):
        print(f"  {i}. type: {defect.get('type')}    "
              f"quote_in_judgment: {defect.get('quote_in_judgment')}")
        for quote in defect.get("judgment_says") or []:
            print(f"       Judgment says: {quote}")
        for quote in defect.get("record_says") or []:
            print(f"       Record says:   {quote}")
        if defect.get("why"):
            print(f"       Why:           {defect['why']}")
    print()
    print("  the objection as the judge was handed it:")
    for line in (challenge.get("text") or "").splitlines():
        print(f"    | {line}")
    print()
    print("-" * W)
    print("  THE RULING — the judge's reasoning, in full")
    print("-" * W)
    for line in (ruling.get("reasoning") or "").splitlines():
        print(f"    | {line}")
    print()
    print(f"  the line it ended on: {ruling.get('conclusion_line')!r}")


def pick_six(slug: str) -> list[tuple[str, str, dict]]:
    """Three overturns and three upholds, taken in cell order so the choice is not
    made after reading them."""
    everything = rows(slug)
    over, up = [], []
    for (source, cell_id), row in sorted(everything.items()):
        if row.get("ruling_form") is None:
            continue
        (over if row.get("changed_the_decision") else up).append(
            (source, cell_id, row))
    return over[:3] + up[:3]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print("usage: judge-pick-handread.py <pick-slug> [runner-up-slug]")
        return 64
    pick, runner = argv[0], (argv[1] if len(argv) > 1 else None)
    print("#" * W)
    print("# THE JUDGE PICK — rulings read by hand")
    print("#" * W)
    print("# Six from the pick (three overturns, three upholds) and three from the")
    print("# runner-up, over the same 82 stored objections of pilot 1 and pilot 2.")
    print("# Read the module docstring for the three questions this exists to answer.")
    print("#" * W)

    n = 0
    print(f"\n\n{'#' * W}\n# THE PICK: {pick}\n{'#' * W}")
    for source, cell_id, row in pick_six(pick):
        n += 1
        render(pick, source, cell_id, row, n)
    if runner:
        print(f"\n\n{'#' * W}\n# THE RUNNER-UP: {runner}\n{'#' * W}")
        for source, cell_id, row in pick_six(runner)[:3]:
            n += 1
            render(runner, source, cell_id, row, n)
    print()
    print("#" * W)
    print(f"# {n} rulings rendered.")
    print("#" * W)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
