"""Write the two cases files the FABRICATED arm runs on — the 896-cell population and
the six-cell smoke drawn from it.

    cd exp2
    uv run python records/derivations/jd4-pick.py \
        2>&1 | tee outputs/jd4-pick.log

Read-only over `outputs/experiments/jd3-main/index.jsonl` and `data/cases/ftf-all.jsonl`;
writes exactly two files, `data/cases/jd4-fabricated.jsonl` and
`data/cases/jd4-smoke.jsonl`. It touches nothing under `outputs/experiments/`.

WHY THE POPULATION IS 896 AND NOT 1,644. `judgment-debate-4`'s arm exists to be read
BESIDE `judgment-debate-3`'s M1 (the real audit), M2 (the placeholder) and M4 (the gate),
and all three of those stand on exactly the cells M1 contested. `judgment-debate-3`'s M3
did not — its instruction forbids the decline, so it contested all 1,642 decided cells and
its rows can only be compared with M1's on an overlap that has to be taken afterwards.
This arm's instruction forbids the decline too, so the restriction has to be made in the
POPULATION instead: the cases file holds the 896 items M1 objected to and no others, and
every arm of the campaign is then paired cell for cell without an overlap step.

The count is ASSERTED rather than reported. 896 is what `jd3-main`'s index says today
(`challenge_raised == true`), it is the number `PREREG.md` writes down, and a cases file
that quietly held 894 or 1,644 would be a different experiment carrying the same name.

ITEMS, NOT CELLS, because a cases file is a list of items — and on a debate-only grid of
one repeat each item is exactly one cell, which the script checks rather than assumes.

SMOKE 1's SIX CELLS are one per subset in cell_id order, deliberately not a random draw:
the house rule (`HANDOFF.md` §2.8) is that a new prompt is read on about six chosen
examples before any slice or sweep, and what the reader has to see is whether the
challenger invents a judgment quotation on SIX DIFFERENT KINDS of judgment rather than on
six python800 ones. Nothing downstream depends on the order, and the smoke is not a
validation set: the gate it feeds is `outputs/jd4-smoke-read.txt`, which recomputes every
quotation check by hand.

SMOKE 2's SIX CELLS ARE DIFFERENT CELLS, and that is the point of them. The clause was
revised on 2026-08-28 after smoke 1 (the record side: 3 of 10 `Record says:` quotations
were verbatim in the record, and 4 were sentences of the JUDGMENT quoted under the
record's label), and re-reading the revision on the same six cells would confuse "the
clause is fixed" with "the clause is fixed on these six". So the second draw is
`random.Random(2)` over the 896 — a stated seed, reproducible by re-running this file —
one cell per subset, EXCLUDING every item smoke 1 used. Both cases files stay on disk and
both smokes are reported side by side in `outputs/jd4-smoke-read.txt`.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "outputs" / "experiments" / "jd3-main" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT_ARM = REPO / "data" / "cases" / "jd4-fabricated.jsonl"
OUT_SMOKE = REPO / "data" / "cases" / "jd4-smoke.jsonl"
OUT_SMOKE_2 = REPO / "data" / "cases" / "jd4-smoke-2.jsonl"
# The seed of the second draw, written down rather than left to the shuffle: a smoke
# whose cells cannot be re-derived is a smoke nobody can check.
SMOKE_2_SEED = 2

# What M1 contested, written down before the file is opened. `PREREG.md` carries the same
# number; if the tree ever disagrees with it the script stops rather than writing a
# population nobody agreed to.
EXPECTED_CONTESTED = 896
SMOKE_N = 6


def contested_rows() -> list[dict]:
    rows = [json.loads(line) for line in
            INDEX.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"{INDEX}: {len(rows)} rows")
    arms = Counter(row.get("challenge_arm") for row in rows)
    print(f"  challenge_arm: {dict(arms)}")
    contested = [row for row in rows if row.get("challenge_raised")]
    print(f"  contested by M1 (challenge_raised): {len(contested)}")
    return contested


def write_smoke(path: Path, rows: list[dict], by_id: dict[str, str],
                label: str) -> None:
    """Write one smoke's cases file and print the cells it holds."""
    path.write_text("\n".join(by_id[row["item_id"]] for row in rows) + "\n",
                    encoding="utf-8")
    print(f"\nwrote {len(rows)} items -> {path}")
    print(f"  {label}")
    print(f"{'cell_id':<44}{'subset':>12}{'M0 right':>10}{'M1 defects':>12}")
    print("-" * 78)
    for row in rows:
        print(f"{row['cell_id']:<44}{row['subset']:>12}"
              f"{str(row['initially_correct']):>10}"
              f"{row.get('challenge_defects_n', 0):>12}")
    print("-" * 78)


def main() -> int:
    contested = contested_rows()
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

    by_id = {}
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_id[json.loads(line)["item"]["item_id"]] = line
    missing = [item for item in items if item not in by_id]
    if missing:
        print(f"  ! {len(missing)} contested items are not in {CORPUS}: {missing[:5]}")
        return 1

    OUT_ARM.write_text("\n".join(by_id[item] for item in sorted(items)) + "\n",
                       encoding="utf-8")
    print(f"\nwrote {len(items)} items -> {OUT_ARM}")
    print(f"  subsets: {dict(Counter(r['subset'] for r in contested))}")
    print(f"  M0 was right on {sum(1 for r in contested if r['initially_correct'])} of "
          f"{len(contested)}, wrong on "
          f"{sum(1 for r in contested if not r['initially_correct'])}")

    # SMOKE 1 — one per subset, in cell_id order: six different kinds of judgment to read
    chosen: list[dict] = []
    seen: set[str] = set()
    for row in sorted(contested, key=lambda r: (r["subset"] or "", r["cell_id"])):
        if len(chosen) >= SMOKE_N:
            break
        if row["subset"] in seen:
            continue
        seen.add(row["subset"])
        chosen.append(row)
    write_smoke(OUT_SMOKE, chosen, by_id, "SMOKE 1 (the clause before the record-side "
                                          "fix of 2026-08-28)")

    # SMOKE 2 — a seeded draw over the same 896, one per subset, and NONE of smoke 1's
    # items: the revision has to be read on judgments it has not already been read on.
    used = {row["item_id"] for row in chosen}
    pool = [row for row in contested if row["item_id"] not in used]
    random.Random(SMOKE_2_SEED).shuffle(pool)
    second: list[dict] = []
    seen = set()
    for row in pool:
        if len(second) >= SMOKE_N:
            break
        if row["subset"] in seen:
            continue
        seen.add(row["subset"])
        second.append(row)
    second.sort(key=lambda r: (r["subset"] or "", r["cell_id"]))
    write_smoke(OUT_SMOKE_2, second, by_id,
                f"SMOKE 2 (the revised clause; random.Random({SMOKE_2_SEED}) over the "
                f"{len(pool)} cells smoke 1 did not use)")
    if used & {row["item_id"] for row in second}:
        print("  ! the two smokes share a cell — the second draw did not exclude the "
              "first")
        return 1
    print("EACH SMOKE MAKES ONE CHALLENGER CALL PER CELL (six), plus one comprehension "
          "probe and one ruling each; `exp2-experiment --dry-run` prices it "
          "independently and the two are expected to agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
