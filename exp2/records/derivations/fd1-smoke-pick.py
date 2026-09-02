"""Write the six-cell cases file the `fd1` (FINDINGS) prompt smoke runs on.

    cd exp2
    uv run python records/derivations/fd1-smoke-pick.py 2>&1 | tee outputs/fd1-smoke-pick.log

Read-only over `outputs/experiments/jd3-main/index.jsonl` (the 1,644 stored debate
decisions this campaign re-judges — `transcripts_from` in every fd1 spec) and
`data/cases/ftf-all.jsonl`; writes exactly one file, `data/cases/fd1-smoke.jsonl`. It
touches nothing under `outputs/experiments/`.

WHY SIX CELLS. The house rule (`HANDOFF.md` §2.8, and MEMORY's "smoke first") is that a
new or changed prompt is read on about six chosen examples before any slice or paid arm.
fd1 adds FOUR new prompt families at once — the findings judgment, the findings contest,
the findings ruling and the findings grader — and the reading is of both arms, so twelve
`transcript.md` are read on these six cells.

WHY THESE SIX. A findings list is a decomposition of a judgment, so the read has to cover
the four states the decomposition can be in and the two places its FORM is under most
strain:

  1. `m0_false_negative` — M0 was wrong on a FLAWED item (it said SOUND). The list should
     be empty or should rule the real flaw NOT A FLAW; this is where an omission contest
     has something true to say, and P3 (`fixed|wrong`) lives here.
  2. `m0_false_positive` — M0 was wrong on a SOUND item (it said FLAWED). Here a
     FLAW→NOT A FLAW contest is VALID by rule, and the reader checks the grader agrees.
  3. `m0_right_flawed` — right on a flawed item. Breaking THIS verdict takes every FLAW
     finding flipped; the verdict-side asymmetry PREREG §3 records is read here.
  4. `m0_right_sound` — right on a sound item. Breaking this takes ONE upheld contest, so
     it is the cheapest break the design allows and the one P2 is most exposed to.
  5. `long_python800` — the LONGEST decision record in the corpus's largest subset. The
     findings judge must decompose a long transcript into a numbered list under a
     16,384-token cap; if the format breaks anywhere it breaks here, and the feasibility
     gate (85% parse rate) is what that would cost.
  6. `gpqa_location_only` — a flawed gpqa item. gpqa's 191 flaw annotations are ALL
     `location_only` (`data/cases/ftf-all.jsonl`), so this is where the grader must judge
     a finding contest by location alone (`GRADER_CLOSING_LOCATION_ONLY`) and where the
     validity clamp of PREREG §5(a) applies. Not reading one before the pilot would leave
     the clamp untested on a fifth of the flawed corpus.

ONE PER SUBSET WHERE THE POOL ALLOWS, and the two forced subsets are RESERVED. Types 5 and
6 are subsets by definition (python800, gpqa), so types 1-4 avoid those two as well as each
other; with seven subsets in the corpus that leaves four to fill and the draw always
succeeds, but the preference is a preference — if a pool ever holds only reserved subsets
the draw fills from what is left rather than returning short, exactly as `jd6-smoke-pick.py`
does.

SEEDED PER TYPE, `random.Random(f"{SEED}:{label}")`. One seed for all four correctness
types would run the same shuffle order down four overlapping pools and the first subset in
it would win every time — the bug `jd6-smoke-pick.py` records having made once. Type 5 is
not a draw at all: it is the maximum of `decision_record_words`, tie-broken by `cell_id`,
because "the longest" is a fact about the corpus and a seed cannot improve on it.

EXCLUDED: every cell already read by hand or already smoked. That is the twenty cells of
`records/experiments/judgment-debate-6/HANDCHECK.md` (matched on the item stem, which is
how that document names its cells) and the union of the item ids in `data/cases/`'s
jd6-, jd5-, jd4- and judgment-debate- smoke files. Reading a fourth new prompt family on
cells whose text has already been read twice would confuse "the findings form works" with
"the findings form works on the cells we know". Which exclusion files were found is
printed, not assumed.

A RE-SMOKE DRAWS FRESH CELLS UNDER A NEW STATED SEED (plan D3), as jd6's smoke 2 did.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # exp2/
INDEX = REPO / "outputs" / "experiments" / "jd3-main" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "fd1-smoke.jsonl"
HANDCHECK = REPO / "records" / "experiments" / "judgment-debate-6" / "HANDCHECK.md"
SMOKE_GLOBS = ("jd6-smoke*.jsonl", "jd5-smoke*.jsonl", "jd4-smoke*.jsonl",
               "judgment-debate-smoke*.jsonl")

SEED = 1
N_WANTED = 6
# Types 5 and 6 ARE their subsets, so types 1-4 leave those two alone where they can.
RESERVED_SUBSETS = {"python800", "gpqa"}

# The four correctness types, as predicates over one jd3-main index row. Named here
# rather than written inline at the draw, because the argument for the draw is in the
# names. `initially_correct` is M0's own correctness on the stored decision; fd1's
# findings judge re-judges the same transcript, so these are the states the findings
# list is being read against, not the states it will produce.
CORRECTNESS_TYPES = (
    ("m0_false_negative", lambda r: r["initially_correct"] is False and r["gold_flawed"]),
    ("m0_false_positive",
     lambda r: r["initially_correct"] is False and not r["gold_flawed"]),
    ("m0_right_flawed", lambda r: r["initially_correct"] is True and r["gold_flawed"]),
    ("m0_right_sound",
     lambda r: r["initially_correct"] is True and not r["gold_flawed"]),
)

# The subsets, used only to pull item stems out of HANDCHECK.md's prose and tables.
SUBSET_PREFIXES = ("gpqa", "medqa", "python800", "surgery", "law", "lojban", "theoremqa")
STEM_RE = re.compile(r"\b(?:" + "|".join(SUBSET_PREFIXES) + r")[A-Za-z0-9_.-]*")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def item_stem(item_id: str) -> str:
    """`gpqa-63-flawed` -> `gpqa-63`, which is how the hand check names its cells."""
    for suffix in ("-flawed", "-sound"):
        if item_id.endswith(suffix):
            return item_id[: -len(suffix)]
    return item_id


def handchecked_stems() -> set[str]:
    """The cells jd6's hand check read, matched on the stem it names them by.

    HANDCHECK.md is a document, not an index, so the ids are pulled out of it with a
    word-bounded regex over the known subset prefixes. Matching on whole tokens rather
    than on substrings matters: `gpqa-13` is a substring of `gpqa-139` and excluding the
    wrong cell would be invisible.
    """
    if not HANDCHECK.is_file():
        return set()
    return set(STEM_RE.findall(HANDCHECK.read_text(encoding="utf-8")))


def smoked_items() -> tuple[set[str], list[str]]:
    """Item ids already used by an earlier smoke, and which files were found."""
    found: list[str] = []
    items: set[str] = set()
    for pattern in SMOKE_GLOBS:
        for path in sorted((REPO / "data" / "cases").glob(pattern)):
            found.append(path.name)
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    items.add(json.loads(line)["item"]["item_id"])
    return items, found


def draw(pool: list[dict], label: str, taken: set[str],
         used_subsets: set[str]) -> dict | None:
    """One seeded pick, preferring a subset nothing has taken yet."""
    shuffled = [r for r in pool if r["item_id"] not in taken]
    if not shuffled:
        return None
    random.Random(f"{SEED}:{label}").shuffle(shuffled)
    for row in shuffled:
        if row["subset"] not in used_subsets:
            return row
    # Subset diversity is a preference, not a requirement: a pool holding only subsets
    # already used still yields a cell rather than a short file.
    return shuffled[0]


def main() -> int:
    if not INDEX.is_file():
        print(f"  ! {INDEX} is not on disk; it is the population every fd1 spec "
              "re-judges (`transcripts_from`)")
        return 1
    index = rows(INDEX)
    decided = [r for r in index if r.get("verdict")]
    print(f"{INDEX}: {len(index)} rows, {len(decided)} decided (a `verdict`)")
    print(f"  subsets: {dict(Counter(r['subset'] for r in decided))}")

    stems = handchecked_stems()
    smoked, smoke_files = smoked_items()
    print(f"\nexclusion sources")
    print(f"  {HANDCHECK}: "
          f"{'FOUND' if HANDCHECK.is_file() else 'NOT FOUND'} — {len(stems)} item stems")
    print(f"  data/cases/ smoke files found ({len(smoke_files)}): "
          f"{', '.join(smoke_files) if smoke_files else '(none)'} — "
          f"{len(smoked)} item ids")

    eligible = [r for r in decided
                if item_stem(r["item_id"]) not in stems
                and r["item_id"] not in stems
                and r["item_id"] not in smoked]
    print(f"  eligible (decided, never hand-read, never smoked): {len(eligible)} of "
          f"{len(decided)}")

    chosen: list[tuple[str, dict]] = []
    taken: set[str] = set()
    used_subsets: set[str] = set(RESERVED_SUBSETS)
    print(f"\nreserved for types 5 and 6, so types 1-4 avoid them: "
          f"{sorted(RESERVED_SUBSETS)}")

    for label, predicate in CORRECTNESS_TYPES:
        pool = [r for r in eligible if predicate(r)]
        print(f"\n{label}: {len(pool)} eligible, subsets "
              f"{dict(Counter(r['subset'] for r in pool))}")
        row = draw(pool, label, taken, used_subsets)
        if row is None:
            print(f"  ! no eligible cell of this type; NOT WRITING")
            return 1
        print(f"  -> {row['cell_id']} ({row['subset']})")
        chosen.append((label, row))
        taken.add(row["item_id"])
        used_subsets.add(row["subset"])

    # 5. the longest python800 decision record. Not a draw: the maximum of the index's
    # own `decision_record_words`, tie-broken by cell_id so it is re-derivable.
    label = "long_python800"
    pool = [r for r in eligible
            if r["subset"] == "python800" and r["item_id"] not in taken]
    print(f"\n{label}: {len(pool)} eligible python800 cells, "
          f"decision_record_words max {max((r.get('decision_record_words') or 0) for r in pool) if pool else 0}")
    if not pool:
        print("  ! no eligible python800 cell; NOT WRITING")
        return 1
    row = sorted(pool, key=lambda r: (-(r.get("decision_record_words") or 0),
                                      r["cell_id"]))[0]
    print(f"  -> {row['cell_id']} ({row.get('decision_record_words')} words)")
    chosen.append((label, row))
    taken.add(row["item_id"])

    # 6. a FLAWED gpqa cell: gpqa's annotations are location_only, so this is the one
    # place the grader's location-only clamp is exercised before the pilot.
    label = "gpqa_location_only"
    pool = [r for r in eligible
            if r["subset"] == "gpqa" and r["gold_flawed"] and r["item_id"] not in taken]
    print(f"\n{label}: {len(pool)} eligible flawed gpqa cells")
    row = draw(pool, label, taken, set())
    if row is None:
        print("  ! no eligible flawed gpqa cell; NOT WRITING")
        return 1
    print(f"  -> {row['cell_id']}")
    chosen.append((label, row))
    taken.add(row["item_id"])

    # --- the asserts, before anything is written ---------------------------------------
    if len(chosen) != N_WANTED:
        print(f"  ! drew {len(chosen)} cells, wanted {N_WANTED}; NOT WRITING")
        return 1
    item_ids = [row["item_id"] for _, row in chosen]
    if len(set(item_ids)) != N_WANTED:
        dupes = [i for i, n in Counter(item_ids).items() if n > 1]
        print(f"  ! two types drew the same item {dupes}; NOT WRITING")
        return 1
    # A cases file is a list of ITEMS; on this grid (debate only, one repeat) each item is
    # exactly one cell, which is checked rather than assumed — a cases file cannot express
    # "one of the two cells of this item".
    per_item = Counter(r["item_id"] for r in index)
    multi = [i for i in item_ids if per_item[i] != 1]
    if multi:
        print(f"  ! {multi} map to more than one cell in {INDEX}; a cases file cannot "
              "pick one of them. NOT WRITING")
        return 1

    by_id: dict[str, str] = {}
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_id[json.loads(line)["item"]["item_id"]] = line
    missing = [i for i in item_ids if i not in by_id]
    if missing:
        print(f"  ! {len(missing)} chosen items are not in {CORPUS}: {missing}; "
              "NOT WRITING")
        return 1

    OUT.write_text("\n".join(by_id[i] for i in sorted(item_ids)) + "\n",
                   encoding="utf-8")
    written = [l for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(written) != N_WANTED:
        print(f"  ! wrote {len(written)} lines, wanted {N_WANTED}")
        return 1

    print(f"\nwrote {len(written)} items -> {OUT}")
    print(f"  seeded random.Random('{SEED}:<type>'), one per subset where the pool "
          f"allowed; python800 and gpqa reserved for types 5 and 6")
    print(f"\n{'type':22s}{'cell_id':<74}{'subset':>10}{'gold_flawed':>13}"
          f"{'M0 verdict':>12}{'M0 right':>10}{'rec_words':>11}")
    print("-" * 152)
    for label, row in chosen:
        print(f"{label:22s}{row['cell_id']:<74}{row['subset']:>10}"
              f"{str(row['gold_flawed']):>13}{str(row['verdict']):>12}"
              f"{str(row['initially_correct']):>10}"
              f"{str(row.get('decision_record_words')):>11}")
    print("-" * 152)
    print(f"  subsets drawn: {dict(Counter(row['subset'] for _, row in chosen))}")

    print("\nEACH ARM BUYS 1 FINDINGS JUDGMENT + 1 CONTEST + 1 COMPREHENSION + "
          "(<=1) RULING + (<=1) RULING READING + (<=1) GRADE PER CELL ON THIS FILE, and "
          "no debater calls (the transcripts are jd3-main's). "
          "`exp2-experiment --dry-run --spec experiments/fd1-smoke-{weak,strong}.toml` "
          "prices the two arms independently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
