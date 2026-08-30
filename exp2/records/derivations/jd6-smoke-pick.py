"""Write the cases files the `judgment-debate-6` prompt smoke runs on.

    cd exp2
    uv run python records/derivations/jd6-smoke-pick.py 2>&1 | tee outputs/jd6-smoke-pick.log

Read-only over `records/experiments/judgment-debate-5/arm-real/index.jsonl` (the committed
index of jd5's arm B — the same 896 objections, ruled with no round) and
`data/cases/ftf-all.jsonl`; writes exactly two files, `data/cases/jd6-smoke.jsonl` (six
cells, the contest-round half) and `data/cases/jd6-smoke-plain.jsonl` (three of those six,
the plain-round half). It touches nothing under `outputs/experiments/`.

WHY SIX CELLS. The house rule (`HANDOFF.md` §2.8) is that a new or changed prompt is read
on about six chosen examples before any slice or paid arm. This campaign adds FOUR new
prompts at once — the recourse debater's system clause, its user template, the two round
instructions (PRO and ANTI) — plus one inserted block in the recourse judge's materiality
template, so there is more to read here than in any smoke since `judgment-debate`.

WHY THESE SIX, and the answer is that the round has to be read where it can do harm as
well as where it can help. Each cell is one of jd5-B's own rulings, and the three types
are two apiece:

  * BROKE — jd5-B overturned a decision that was RIGHT (`changed_the_decision` and
    `initially_correct`). This is the failure the contest round is supposed to reduce:
    the ANTI debater is the one with something true to say, and the reader is checking
    that it says it.
  * FIXED — jd5-B overturned a decision that was WRONG. The round must not cost these;
    P2 is the endpoint that says so.
  * UPHELD-ON-WRONG — jd5-B let a wrong decision stand. Here the PRO debater is the one
    with something true to say, and the reader is checking whether an argued objection
    reaches a judge that was not moved by the objection alone.

ONE PER SUBSET where the pool allows and a stated seed, so the six can be re-derived by
re-running this file and so the reader is not shown six python800 judgments.

EXCLUDED: the nine cells of `outputs/jd4-handcheck.md` and the six cells of jd5's own two
smokes. Reading a new prompt on cells whose text has already been read by hand twice would
confuse "the round works" with "the round works on the cells we know".

THE PLAIN HALF takes three of the six — one of each type — so the two halves can be read
side by side on the same judgments: what the contest round did with the objection, and
what an un-steered round did with nothing.

SMOKE 2's SIX CELLS ARE DIFFERENT CELLS, AND ITS COMPOSITION IS DIFFERENT TOO. Two
sentences of the new prompts were rewritten after smoke 1 was read — the exchange block's
"arguments, not evidence" discount was one-directional, and the ANTI round instruction
presupposed that each defect fails — so the house rule says the revision is read on cells
it has not already been read on, which is the rule `records/derivations/jd4-pick.py`
applied to its own second draw. A new seed, and NONE of smoke 1's items.

It is also **weighted toward the primary endpoint's population**. Smoke 1 drew two cells
of each of three outcome types, which put only two initially-CORRECT cells in front of the
reader; P1 — the primary — is tested on the 622 cells M0 got RIGHT, and the failure the
contest round is supposed to reduce is breaking one of them. So smoke 2 is **four
initially-correct cells** (two jd5-B overturned, two upheld) **and two initially-wrong**
(one each), which puts the reader in front of the case that matters and in front of the
one where a round could do harm by moving a cell that was already right and already left
alone.

BOTH SMOKES STAY ON DISK and both are re-derivable by re-running this file. Smoke 1's
trees, its read (`outputs/jd6-smoke-read.txt`) and its specs are kept as the record of what
the two sentences were changed FOR.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JD5_REAL = (REPO / "records" / "experiments" / "judgment-debate-5" / "arm-real"
            / "index.jsonl")
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "jd6-smoke.jsonl"
OUT_PLAIN = REPO / "data" / "cases" / "jd6-smoke-plain.jsonl"
OUT_2 = REPO / "data" / "cases" / "jd6-smoke-2.jsonl"
OUT_2_PLAIN = REPO / "data" / "cases" / "jd6-smoke-2-plain.jsonl"

SEED = 6
PER_TYPE = 2
PLAIN_PER_TYPE = 1

# Smoke 2's own seed, written down rather than left to the shuffle: a smoke whose cells
# cannot be re-derived is a smoke nobody can check.
SEED_2 = 62
# Smoke 2's plain half: three of its six, and TWO of them initially-correct, because that
# is the population P1 is tested on.
PLAIN_2_N = 3

# The nine cells of `outputs/jd4-handcheck.md`, read in full by hand when the existence
# check was found missing.
HANDCHECKED = {
    "medqa-dev_0043", "python800-p03673", "python800-p03698", "python800-p03011",
    "python800-p02690", "python800-p03338", "python800-p03838", "gpqa-63",
    "python800-p03803",
}
# jd5's own smoke cells, read when the existence check was written. Loaded from the cases
# files rather than restated, so a re-drawn jd5 smoke cannot silently overlap with this
# one.
JD5_SMOKES = ("jd5-smoke-real.jsonl", "jd5-smoke-fabricated.jsonl")

# The three outcome types, as predicates over one jd5-B row. Named here rather than
# written inline at the draw, because the whole argument for the draw is in the names.
TYPES = (
    ("BROKE  — jd5-B overturned a decision that was RIGHT",
     lambda r: r.get("changed_the_decision") and r.get("initially_correct")),
    ("FIXED  — jd5-B overturned a decision that was WRONG",
     lambda r: r.get("changed_the_decision") and r.get("initially_correct") is False),
    ("UPHELD — jd5-B let a WRONG decision stand",
     lambda r: not r.get("changed_the_decision")
     and r.get("initially_correct") is False),
)


# Smoke 2's four types and how many of each, weighted toward P1's population: FOUR
# initially-correct cells against two initially-wrong. `UPHELD-ON-RIGHT` is the type smoke
# 1 had none of, and it is the one where a round can only do harm — the decision was right
# and the judge already left it alone, so any movement is a break.
TYPES_2 = (
    ("BROKE   — M0 RIGHT, jd5-B overturned it", 2,
     lambda r: r.get("initially_correct") and r.get("changed_the_decision")),
    ("HELD    — M0 RIGHT, jd5-B upheld it (a round can only do harm here)", 2,
     lambda r: r.get("initially_correct") and not r.get("changed_the_decision")),
    ("FIXED   — M0 WRONG, jd5-B overturned it", 1,
     lambda r: r.get("initially_correct") is False and r.get("changed_the_decision")),
    ("MISSED  — M0 WRONG, jd5-B upheld it", 1,
     lambda r: r.get("initially_correct") is False and not r.get("changed_the_decision")),
)


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def item_stem(item_id: str) -> str:
    """`gpqa-63-flawed` -> `gpqa-63`, which is how the hand check names its cells."""
    for suffix in ("-flawed", "-sound"):
        if item_id.endswith(suffix):
            return item_id[: -len(suffix)]
    return item_id


def excluded_items() -> set[str]:
    out = set()
    for name in JD5_SMOKES:
        path = REPO / "data" / "cases" / name
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.add(json.loads(line)["item"]["item_id"])
    return out


def draw(pool: list[dict], n: int, taken: set[str], label: str,
         seed: int = SEED) -> list[dict]:
    """A seeded draw, one per subset where the pool allows, skipping items already used.

    Seeded on `SEED:label` rather than on `SEED` alone: with one seed for all three types
    the same shuffle order runs down three overlapping pools and the first subset in it
    wins every time, which is how the first draft of this file produced four gpqa cells
    out of six.
    """
    shuffled = [r for r in pool if r["item_id"] not in taken]
    random.Random(f"{seed}:{label}").shuffle(shuffled)
    chosen: list[dict] = []
    seen: set[str] = set()
    for row in shuffled:
        if len(chosen) >= n:
            break
        if row["subset"] in seen:
            continue
        seen.add(row["subset"])
        chosen.append(row)
    # A subset-diverse draw is a preference, not a requirement: if the pool holds fewer
    # subsets than cells wanted, fill from what is left rather than returning short.
    for row in shuffled:
        if len(chosen) >= n:
            break
        if row not in chosen:
            chosen.append(row)
    return chosen


def write(path: Path, chosen: list[tuple[str, dict]], by_id: dict[str, str],
          label: str) -> None:
    path.write_text("\n".join(by_id[row["item_id"]] for _, row in chosen) + "\n",
                    encoding="utf-8")
    print(f"\nwrote {len(chosen)} items -> {path}")
    print(f"  {label}")
    print(f"{'cell_id':<44}{'subset':>11}{'M0':>7}{'right':>7}"
          f"{'jd5-B':>9}{'defects':>9}{'valid':>7}")
    print("-" * 96)
    for kind, row in chosen:
        print(f"{row['cell_id']:<44}{row['subset']:>11}{str(row['verdict']):>7}"
              f"{str(row['initially_correct']):>7}"
              f"{('OVERTURN' if row['changed_the_decision'] else 'UPHOLD'):>9}"
              f"{row.get('challenge_defects_n', 0):>9}"
              f"{str(row.get('grade_valid')):>7}    {kind.split(' ')[0]}")
    print("-" * 96)


def main() -> int:
    if not JD5_REAL.is_file():
        print(f"  ! {JD5_REAL} is not on disk; jd5's arm-real index is what the three "
              "outcome types are read off")
        return 1
    index = rows(JD5_REAL)
    print(f"{JD5_REAL}: {len(index)} rows")
    excluded = excluded_items()
    print(f"excluded: {len(HANDCHECKED)} hand-checked stems, {len(excluded)} jd5 smoke "
          f"items")

    eligible = [r for r in index
                if r.get("ruling_form")
                and item_stem(r["item_id"]) not in HANDCHECKED
                and r["item_id"] not in excluded]
    print(f"eligible (ruled, not already read by hand): {len(eligible)}")

    chosen: list[tuple[str, dict]] = []
    taken: set[str] = set()
    for label, predicate in TYPES:
        pool = [r for r in eligible if predicate(r)]
        print(f"\n{label}: {len(pool)} eligible, subsets "
              f"{dict(Counter(r['subset'] for r in pool))}")
        if len(pool) < PER_TYPE:
            print(f"  ! fewer than {PER_TYPE} cells of this type; NOT WRITING")
            return 1
        for row in draw(pool, PER_TYPE, taken, label):
            chosen.append((label, row))
            taken.add(row["item_id"])

    by_id: dict[str, str] = {}
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_id[json.loads(line)["item"]["item_id"]] = line
    missing = [row["item_id"] for _, row in chosen if row["item_id"] not in by_id]
    if missing:
        print(f"  ! {len(missing)} chosen items are not in {CORPUS}: {missing}")
        return 1

    chosen.sort(key=lambda pair: (pair[0], pair[1]["cell_id"]))
    write(OUT, chosen, by_id,
          f"the CONTEST ROUND half (random.Random({SEED}), {PER_TYPE} per outcome type, "
          "one per subset where the pool allowed)")

    # One of each type for the plain half, so the three can be read against their own
    # contest-round twins rather than against three other cells — and, where the pair
    # allows it, three DIFFERENT subsets, for the reason the draw above is per-type
    # seeded: three gpqa judgments would be a narrower read than the six were.
    plain: list[tuple[str, dict]] = []
    seen_subsets: set[str] = set()
    for kind, _ in TYPES and [(k, None) for k, _ in TYPES]:
        pair = [(k, r) for k, r in chosen if k == kind]
        pick = next((p for p in pair if p[1]["subset"] not in seen_subsets), pair[0])
        seen_subsets.add(pick[1]["subset"])
        plain.append(pick)
    write(OUT_PLAIN, plain, by_id,
          "the PLAIN ROUND half — three of the same six, one per outcome type")

    # --- SMOKE 2 — fresh cells, and weighted toward P1's population ------------------
    print()
    print("=" * 96)
    print("SMOKE 2 — the revised exchange block and ANTI round instruction, on cells the")
    print("first read did not use. FOUR initially-CORRECT cells and TWO initially-wrong,")
    print(f"random.Random({SEED_2}:<type>), one per subset where the pool allowed.")
    print("=" * 96)
    used = {row["item_id"] for _, row in chosen}
    second: list[tuple[str, dict]] = []
    taken_2 = set(used)
    for label, want, predicate in TYPES_2:
        pool = [r for r in eligible if predicate(r) and r["item_id"] not in used]
        print(f"\n{label}: {len(pool)} eligible, subsets "
              f"{dict(Counter(r['subset'] for r in pool))}")
        if len(pool) < want:
            print(f"  ! fewer than {want} cells of this type; NOT WRITING")
            return 1
        for row in draw(pool, want, taken_2, label, seed=SEED_2):
            second.append((label, row))
            taken_2.add(row["item_id"])

    overlap = used & {row["item_id"] for _, row in second}
    if overlap:
        print(f"  ! smoke 2 drew {len(overlap)} of smoke 1's cells: {sorted(overlap)}")
        return 1
    second.sort(key=lambda pair: (pair[0], pair[1]["cell_id"]))
    write(OUT_2, second, by_id,
          f"the CONTEST ROUND half of SMOKE 2 (random.Random({SEED_2}), 4 cells M0 got "
          "RIGHT and 2 it got wrong)")

    # The plain half of smoke 2 keeps TWO of the four initially-correct cells, because
    # P1 is tested on that population and the baseline has to be read there too.
    plain_2: list[tuple[str, dict]] = []
    for want_right in (True, False):
        for kind, row in second:
            if len(plain_2) >= PLAIN_2_N:
                break
            if bool(row.get("initially_correct")) is not want_right:
                continue
            if (kind, row) in plain_2:
                continue
            if want_right and sum(1 for _, r in plain_2
                                  if r.get("initially_correct")) >= 2:
                continue
            plain_2.append((kind, row))
    write(OUT_2_PLAIN, plain_2, by_id,
          "the PLAIN ROUND half of SMOKE 2 — three of the same six, TWO of them cells M0 "
          "got RIGHT")

    print("\nEACH ROUND HALF MAKES 2 DEBATER CALLS + 1 RULING PER CELL (18 calls); "
          "each plain half 2 DEBATER CALLS + 1 JUDGMENT PER CELL (9). "
          "`exp2-experiment --dry-run` prices them independently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
