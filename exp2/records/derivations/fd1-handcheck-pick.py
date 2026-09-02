"""Pick the cells Fable reads by hand, and write the paths to each one's record.

    cd exp2
    uv run python records/derivations/fd1-handcheck-pick.py > outputs/fd1-handcheck-pick.md

Read-only over `outputs/experiments/fd1-weak/` and `outputs/experiments/fd1-strong/`. It
writes nothing under `outputs/experiments/` and it does NOT score anything: the whole point
of a hand check is that a person reads the documents and writes the verdicts, so this file
chooses the cells and prints where they are, and stops.

WHY THESE FIVE GROUPS. `PREREG.md`'s endpoints are P1 (does recourse on a decomposed
judgment raise accuracy) and P2 (does the LOCAL contest break fewer right decisions than
jd5-B's whole-job objection), so the cells worth a person's time are the ones where
recourse actually MOVED a verdict, in each direction; the two shapes only this arm can
produce — an appended finding and an empty list; the cells where the weak and the strong
findings judge disagree about the decision itself; and the twenty that score the
mechanical phantom instrument, which PREREG §7 says has two blind spots no column can see.

  (a) recourse BROKE a right decision      the failure P2 says should be rarer here
  (b) recourse FIXED a wrong one           the success P3 reports
  (c) an appended finding, or an EMPTY list the two shapes only the findings form has
  (d) F-weak and F-strong disagree on the   the judge, isolated from the recourse
      before-verdict
  (e) the phantom read (20 cells)          PREREG §7's two blind spots, scored by hand

Group (e) is the instrument check and it is the reason this file draws twenty rather than
five: `phantom = (stance == contests) != (n_well_formed > 0)` is mechanical and cannot see
a well-formed contest whose `Why` argues the finding is RIGHT, nor a STANDS whose prose
attacks a finding without writing an entry. Ten REVERSE objections and ten STANDS with a
non-empty `Argument` are drawn so both blind spots get read.

SEEDED PER GROUP, so a re-draw of one group does not move the others, and sorted by
`cell_id` inside each group so the order carries no information about the outcome. The
format is the one `fd1-collect-records.py` parses: a `## (x)` heading per group and one
``- **`cell_id`** [arm]`` line per cell.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# One seed per group. A group re-drawn under a new seed is a NEW sample and the write-up
# says which seed produced the cells it quotes; sharing one seed across groups would make
# a re-draw of (a) silently move (e).
SEEDS = {"a": 101, "b": 102, "c": 103, "d": 104, "e-reverse": 105, "e-stands": 106}
N_SMALL = 5
N_PHANTOM_HALF = 10

ARMS = ("weak", "strong")


# --------------------------------------------------------------------------- #
# the tree
# --------------------------------------------------------------------------- #


def rows(path: Path) -> dict[str, dict]:
    if not Path(path).is_file():
        return {}
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["cell_id"]] = row
    return out


def decision_path(tree: Path, cell_id: str) -> str:
    hits = sorted(Path(tree).glob(f"cells/{cell_id}/runs/*/transcript.md"))
    return _relative(hits[-1]) if hits else "(not found)"


def contest_path(tree: Path, cell_id: str) -> str:
    hits = sorted(Path(tree).glob(f"cells/{cell_id}/contests/*/runs/*/transcript.md"))
    return _relative(hits[-1]) if hits else "(not found)"


def _relative(path: Path) -> str:
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)


def challenge_text(tree: Path, cell_id: str) -> str | None:
    """The published `Argument:` body of this cell's objection, or None.

    Group (e)'s STANDS half needs it and no index column carries it: a STANDS objection has
    no contests, so `challenge_contests_n` is 0 whether the challenger wrote a paragraph
    attacking finding 3 or the one template sentence. The blind spot PREREG §7 names is
    exactly the first of those, so the text has to be read.
    """
    hits = sorted(Path(tree).glob(f"cells/{cell_id}/contests/*/runs/*/challenge.json"))
    if not hits:
        return None
    try:
        return json.loads(hits[-1].read_text(encoding="utf-8")).get("text") or ""
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# the states, read out of the columns and nowhere else
# --------------------------------------------------------------------------- #


def before_of(row: dict) -> bool | None:
    return row.get("initially_correct")


def after_of(row: dict) -> bool | None:
    before = row.get("initially_correct")
    final = row.get("final_correct")
    return before if final is None else bool(final)


def moved(row: dict) -> tuple[bool, bool] | None:
    """(before, after) where both are known and the cell was actually ruled on."""
    if row.get("ruling_form") is None:
        return None
    before, after = before_of(row), after_of(row)
    if before is None or after is None:
        return None
    return bool(before), bool(after)


def sample(pool: list, seed: int, n: int) -> list:
    pool = sorted(pool)
    if len(pool) <= n:
        return pool
    return sorted(random.Random(seed).sample(pool, n))


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #


def block(group: str, title: str, why: str, drawn: list[tuple[str, str, str]],
          pool_n: int, seed: int, n: int, trees: dict[str, Path]) -> None:
    """One group. `drawn` is `(cell_id, arm, note)`; `arm` is "weak", "strong" or "both"."""
    print()
    print(f"## ({group}) {title}")
    print()
    print(why)
    print()
    print(f"{len(drawn)} drawn from a pool of {pool_n}"
          + (f", `random.Random({seed})`" if pool_n > n else " (the whole pool)") + ".")
    print()
    if not drawn:
        print("*The pool is empty.* That is itself a reading, and it is reported as one.")
        return
    for cell_id, arm, note in drawn:
        print(f"- **`{cell_id}`** [{arm}]{note}")
        for one in (ARMS if arm == "both" else (arm,)):
            tree = trees[one]
            print(f"  - {one} decision: `{decision_path(tree, cell_id)}`")
            contest = contest_path(tree, cell_id)
            if contest != "(not found)":
                print(f"  - {one} contest:  `{contest}`")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weak", type=Path,
                        default=REPO / "outputs" / "experiments" / "fd1-weak",
                        help="the F-weak run tree")
    parser.add_argument("--strong", type=Path,
                        default=REPO / "outputs" / "experiments" / "fd1-strong",
                        help="the F-strong run tree")
    args = parser.parse_args(argv)

    trees = {"weak": args.weak, "strong": args.strong}
    index = {arm: rows(trees[arm] / "index.jsonl") for arm in ARMS}

    print("# findings-1 — the cells to read by hand")
    print()
    print("**Fable reads these and writes the verdicts.** This file chooses the cells and")
    print("prints their paths; it scores nothing. Every path is `transcript.md`, the")
    print("readable record; `transcript_full.md` beside it is the same run verbatim, every")
    print("prompt and every reply, and is where the private `Thinking:` sections are. The")
    print("decision document carries the FINDINGS LIST and the contest document carries the")
    print("objection, the ruling lines and the re-derived verdict.")
    print()
    print("Seeded per group, so a re-draw of one group does not move the others. Sorted by")
    print("`cell_id` inside each group, so the order carries no information.")
    print()
    for arm in ARMS:
        print(f"Index: F-{arm} {len(index[arm])} rows "
              f"(`{_relative(trees[arm] / 'index.jsonl')}`).")
    if not any(index.values()):
        print()
        print("**NOTHING TO PICK — neither arm has an index.** This is what the file prints")
        print("before the run, and it is not an error.")
        return 0

    # (a) and (b): recourse moved a verdict, in each direction. Pooled over the two arms
    # and TAGGED with the arm it happened in, because "F-weak broke it" and "F-strong broke
    # it" are different readings of the same cell and the reader must not have to guess.
    broke: list[tuple[str, str, str]] = []
    fixed: list[tuple[str, str, str]] = []
    for arm in ARMS:
        for cell_id, row in sorted(index[arm].items()):
            states = moved(row)
            if states is None:
                continue
            before, after = states
            note = (f" — {row.get('verdict')} before, "
                    f"{row.get('findings_n')} findings "
                    f"({row.get('findings_flaw_n')} FLAW), "
                    f"{row.get('challenge_contests_n')} contests")
            if before and not after:
                broke.append((cell_id, arm, note))
            if not before and after:
                fixed.append((cell_id, arm, note))

    # (c) the two shapes only this form produces.
    shapes: list[tuple[str, str, str]] = []
    for arm in ARMS:
        for cell_id, row in sorted(index[arm].items()):
            added = row.get("findings_added_n") or 0
            empty = row.get("findings_n") == 0
            if not added and not empty:
                continue
            what = []
            if added:
                what.append(f"{added} finding(s) APPENDED at recourse")
            if empty:
                what.append("EMPTY list (verdict SOUND by derivation)")
            shapes.append((cell_id, arm, " — " + "; ".join(what)))

    # (d) the two judges disagree about the decision itself, with recourse held out. It
    # isolates the judge from the recourse stage, which no other group does.
    disagree: list[tuple[str, str, str]] = []
    for cell_id in sorted(set(index["weak"]) & set(index["strong"])):
        left, right = index["weak"][cell_id], index["strong"][cell_id]
        if left.get("verdict") is None or right.get("verdict") is None:
            continue
        if left["verdict"] == right["verdict"]:
            continue
        disagree.append((cell_id, "both",
                         f" — F-weak {left['verdict']} ({left.get('findings_n')} findings,"
                         f" {left.get('findings_flaw_n')} FLAW), F-strong"
                         f" {right['verdict']} ({right.get('findings_n')} findings,"
                         f" {right.get('findings_flaw_n')} FLAW)"))

    # (e) the phantom read. Ten REVERSE and ten STANDS-with-an-argument, drawn under two
    # seeds so the halves are independent samples of two different blind spots.
    reverse: list[tuple[str, str, str]] = []
    stands: list[tuple[str, str, str]] = []
    stands_pool_reason = ""
    for arm in ARMS:
        for cell_id, row in sorted(index[arm].items()):
            if row.get("challenge_raised"):
                reverse.append((cell_id, arm,
                                f" — {row.get('challenge_contests_n')} contests, "
                                f"{row.get('challenge_contests_void_n')} void, "
                                f"mechanical phantom "
                                f"{row.get('phantom_contest')}"))
                continue
            if row.get("challenge_stance") not in ("agrees", "declined"):
                continue
            text = challenge_text(trees[arm], cell_id)
            if text is None:
                stands_pool_reason = (
                    " The run tree was not reachable for at least one cell, so the STANDS "
                    "pool is every STANDS objection rather than the non-empty ones.")
            elif not text.strip():
                continue
            stands.append((cell_id, arm,
                           f" — stance `{row.get('challenge_stance')}`, "
                           f"Argument {len(text.strip()) if text else '?'} chars"))

    block("a", "recourse BROKE a right decision",
          "The findings judge's own derived verdict was RIGHT and the re-derived verdict\n"
          "after recourse is WRONG. **This is the failure P2 says the LOCAL contest should\n"
          "produce less of than jd5-B's whole-job objection did**, so the read should say\n"
          "which contest did it, whether the ruling's prose supports the line it wrote, and\n"
          "whether the flipped finding was in fact the annotated flaw.",
          sample(broke, SEEDS["a"], N_SMALL), len(broke), SEEDS["a"], N_SMALL, trees)

    block("b", "recourse FIXED a wrong decision",
          "The converse: the derived verdict was WRONG and recourse re-derived it RIGHT.\n"
          "**This is the success P3 reports.** The read should say whether the contest that\n"
          "did it was a finding flip, an upheld omission or a resolved contradiction — the\n"
          "three routes are different claims and only the first has a jd5-B counterpart.",
          sample(fixed, SEEDS["b"], N_SMALL), len(fixed), SEEDS["b"], N_SMALL, trees)

    block("c", "an APPENDED finding, or an EMPTY list",
          "The two shapes only the findings form can produce. An APPENDED finding is an\n"
          "upheld omission written from the CONTEST's own quotes and marked\n"
          "`added_at_recourse` — the read has to say whether the appended text is the\n"
          "challenger's quotation or a judge invention. An EMPTY list is a SOUND verdict\n"
          "reached by finding nothing, and it is contestable by omission alone; the read has\n"
          "to say whether the FLAWED-side debater really raised nothing.",
          sample(shapes, SEEDS["c"], N_SMALL), len(shapes), SEEDS["c"], N_SMALL, trees)

    block("d", "F-weak and F-strong DISAGREE on the before-verdict",
          "The same debate, the same format, two judges, two derived verdicts — and no\n"
          "recourse anywhere in the comparison. It is the one group that isolates the JUDGE.\n"
          "The read should say whether the disagreement is about a FINDING (one judge saw a\n"
          "flaw the other did not) or about a RULING on the same finding, because those are\n"
          "different failures and the derivation rule turns both into one verdict.",
          sample(disagree, SEEDS["d"], N_SMALL), len(disagree), SEEDS["d"], N_SMALL, trees)

    print()
    print("## (e) the PHANTOM read — 20 cells, PREREG §7's two blind spots")
    print()
    print("`phantom = (stance == contests) != (n_well_formed > 0)` is MECHANICAL: it is a")
    print("string comparison, not a model's reading, and it is never pooled with jd3-jd6's")
    print("Haiku phantom column. It has exactly two blind spots and neither is visible in any")
    print("column, so twenty cells are read by hand:")
    print()
    print("  1. a REVERSE with a well-formed contest whose `Why` in fact argues the finding")
    print("     is RIGHT — mechanically not a phantom, substantively one;")
    print("  2. a STANDS whose `Argument` attacks a finding without writing an entry for it")
    print("     — mechanically not a phantom, and a contest the harness never ruled on.")
    print()
    print("Ten of each, under two seeds, so the halves are independent samples." +
          stands_pool_reason)

    block("e1", "ten REVERSE objections  [blind spot 1]",
          "Read the `Why` of every contest. Does it argue the finding is WRONG, or does it\n"
          "agree with the finding and object to something else? A REVERSE whose every `Why`\n"
          "endorses the finding it contests is a phantom the mechanical column cannot see.",
          sample(reverse, SEEDS["e-reverse"], N_PHANTOM_HALF), len(reverse),
          SEEDS["e-reverse"], N_PHANTOM_HALF, trees)

    block("e2", "ten STANDS with a non-empty Argument  [blind spot 2]",
          "Read the `Argument`. Does it accept the findings, or does it attack one without\n"
          "writing a numbered contest for it? The second is an objection the harness never\n"
          "put to a judge, and it is the failure this half exists to count.",
          sample(stands, SEEDS["e-stands"], N_PHANTOM_HALF), len(stands),
          SEEDS["e-stands"], N_PHANTOM_HALF, trees)

    print()
    print("---")
    print()
    print("Groups (a) and (b) are the two halves of P1's discordant pairs, so their POOL")
    print("sizes are the counts `findings-1.py`'s section (1) prints as `b` and `c`. The")
    print("samples here are for READING, never for counting, and no rate is computed from")
    print("them. Group (e)'s hand count IS a number the write-up quotes, and it is quoted as")
    print("a hand count of 20 cells with its two seeds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
