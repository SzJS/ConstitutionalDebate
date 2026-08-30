"""Write the 896-cell cases file `judgment-debate-6`'s PLAIN-ROUND arm runs on.

    cd exp2
    uv run python records/derivations/jd6-pick.py 2>&1 | tee outputs/jd6-pick.log

Read-only over `outputs/experiments/jd3-main/index.jsonl` and `data/cases/ftf-all.jsonl`;
writes exactly one file, `data/cases/jd6-contested.jsonl`. It touches nothing under
`outputs/experiments/`.

WHY ARM B NEEDS A CASES FILE AND ARM R DOES NOT. `jd6-round.toml` re-rules M1's stored
objections, and the `rerule` stage already skips every cell with no source objection — so
that arm can take the whole corpus and land on exactly the 896 cells that carry one. A
`rejudge` has no objection to gate on: pointed at the corpus it would extend and re-judge
all 1,644 of M0's decisions, the arms would not be paired cell for cell, and 748 cells of
strong-model round-4 turns would be bought for a comparison nothing uses. So the
restriction is made in the POPULATION, exactly as `records/derivations/jd4-pick.py` made
it for the fabricated arm and for the same reason.

The count is ASSERTED rather than reported. 896 is what `jd3-main`'s index says today
(`challenge_raised == true`), it is the number `PREREG.md` writes down, and a cases file
that quietly held 894 or 1,644 would be a different experiment carrying the same name.

ITEMS, NOT CELLS, because a cases file is a list of items — and on a debate-only grid of
one repeat each item is exactly one cell, which the script checks rather than assumes.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "outputs" / "experiments" / "jd3-main" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "jd6-contested.jsonl"

# What M1 contested, written down before the file is opened. `PREREG.md` carries the same
# number; if the tree ever disagrees with it the script stops rather than writing a
# population nobody agreed to.
EXPECTED_CONTESTED = 896


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    index = rows(INDEX)
    print(f"{INDEX}: {len(index)} rows")
    arms = Counter(row.get("challenge_arm") for row in index)
    print(f"  challenge_arm: {dict(arms)}")
    contested = [row for row in index if row.get("challenge_raised")]
    print(f"  contested by M1 (challenge_raised): {len(contested)}")
    if len(contested) != EXPECTED_CONTESTED:
        print(f"  ! expected {EXPECTED_CONTESTED} contested cells, found "
              f"{len(contested)}. NOT WRITING — the population in `PREREG.md` and the "
              "population on disk must be the same set.")
        return 1

    items = [row["item_id"] for row in contested]
    if len(set(items)) != len(items):
        # One repeat and one condition, so an item that appeared twice would mean two
        # cells of one item — and a cases file cannot express "one of those two".
        print("  ! the contested cells do not map one-to-one onto items")
        return 1

    by_id: dict[str, str] = {}
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_id[json.loads(line)["item"]["item_id"]] = line
    missing = [item for item in items if item not in by_id]
    if missing:
        print(f"  ! {len(missing)} contested items are not in {CORPUS}: {missing[:5]}")
        return 1

    OUT.write_text("\n".join(by_id[item] for item in sorted(items)) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {len(items)} items -> {OUT}")
    print(f"  subsets: {dict(Counter(r['subset'] for r in contested))}")
    right = sum(1 for r in contested if r["initially_correct"])
    print(f"  M0 was right on {right} of {len(contested)}, wrong on "
          f"{len(contested) - right}")
    print("  P1 is tested on the right ones and P2 on the wrong ones; both counts are "
          "written into PREREG.md before either arm runs.")
    print("\nARM B BUYS 2 DEBATER CALLS + 1 JUDGE CALL PER CELL ON THIS FILE. "
          "`exp2-experiment --dry-run --spec experiments/jd6-plain.toml` prices it "
          "independently and the two are expected to agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
