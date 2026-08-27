"""Pick the items the re-rule smoke runs on, and write them as a cases file.

    uv run python records/derivations/rerule-smoke-pick.py \
        2>&1 | tee outputs/rerule-smoke-pick.log

Read-only over `records/experiments/recontest/index.jsonl` and `data/cases/ftf-all.jsonl`;
writes exactly one file, `data/cases/rerule-smoke.jsonl`. It touches nothing under
`outputs/experiments/`.

**Why these and not a random draw.** The smoke is a PROMPT check, and the user's standing
rule for a new prompt is a smoke on chosen examples first. Here the examples choose
themselves: the defect being fixed is *defined* on the 62 **phantom** cells of the
re-contest — cells whose challenge stance is `contests` and whose prose the grader read
as RIGHT, i.e. an objection that asks for a reversal over reasoning that endorses the
verdict. All 62 sit on FLAWED parents, and the recourse judge overturned **52 of them**
(83.9%), reversing verdicts that the objections themselves agreed with
(`outputs/recontest-ruling-handcheck.md`, Evidence 1). Those are the known failures, and
a prompt that has not fixed them has not fixed anything.

**Items, not cells, because a cases file is a list of items.** The 62 phantom cells belong
to 61 distinct items (one item carries two), and the harness rules a whole grid: every
CONTESTED cell of a chosen item gets a new ruling, phantom or not. That is not waste —
the non-phantom siblings are the control. A prompt that merely made the judge agreeable,
or that flipped everything on FLAWED parents regardless of the objection, would show up
there and not in the phantoms. The count of those cells is printed, because it is the
number of rulings the smoke will make and therefore the number the spend is approved
from; `exp2-experiment --dry-run` computes the same figure independently off the contest
tree, and the two are expected to agree.

Nothing here decides which cells are re-ruled: the `rerule` stage reads each source
contest's own `challenge.json` and skips any whose stance is not `contests`. This script
only chooses the ITEMS, and prints what it expects to follow from that choice.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "records" / "experiments" / "recontest" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT = REPO / "data" / "cases" / "rerule-smoke.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def is_phantom(row: dict) -> bool:
    """The re-contest's own reading: a contesting stance over prose read as RIGHT.

    Read off the two columns rather than off `phantom_contest`, which is computed from
    the challenger's *line word* — the same fact by a different route, and stating the
    predicate here means the selection says in the file what it selected on.
    """
    return (row.get("challenge_stance") == "contests"
            and row.get("prose_stance") == "RIGHT")


def main() -> int:
    rows = load(INDEX)
    phantoms = [r for r in rows if is_phantom(r)]
    items = sorted({r["item_id"] for r in phantoms})
    print(f"index rows {len(rows)}   phantom cells {len(phantoms)}   "
          f"distinct items {len(items)}")

    # What the smoke will actually rule: every CONTESTED cell of those items. The
    # phantoms are the failures under test and the rest are the control.
    wanted = set(items)
    contested = [r for r in rows
                 if r["item_id"] in wanted and r.get("challenge_stance") == "contests"]
    controls = [r for r in contested if not is_phantom(r)]
    print(f"\ncontested cells of those items: {len(contested)}  "
          f"= {len(phantoms)} phantoms + {len(controls)} non-phantom controls")
    print(f"THE SMOKE WILL MAKE {len(contested)} RULINGS "
          f"(and as many ruling-agreement readings).")

    by_condition = Counter(r["condition"] for r in contested)
    by_subset = Counter(r["subset"] for r in contested)
    by_parent = Counter(r["verdict"] for r in contested)
    overturned = sum(1 for r in phantoms if r.get("changed_the_decision"))
    print(f"\nconditions:      {dict(sorted(by_condition.items()))}")
    print(f"parent verdicts: {dict(sorted(by_parent.items()))}")
    print(f"subsets ({len(by_subset)}): {dict(sorted(by_subset.items()))}")
    print(f"phantoms the OLD line overturned: {overturned}/{len(phantoms)} "
          f"({overturned / len(phantoms):.1%}) — the number the new line has to move")

    per_item: dict[str, int] = defaultdict(int)
    for row in phantoms:
        per_item[row["item_id"]] += 1
    doubled = sorted(i for i, n in per_item.items() if n > 1)
    if doubled:
        print(f"items carrying more than one phantom: {doubled}")

    if not items:
        print("\n  ! the index carries no phantom cells; nothing to smoke on")
        return 1

    # The case lines are copied VERBATIM out of the corpus rather than rebuilt from the
    # index, so what `load_cases` reads here is byte-identical to what the sweep decided
    # on and the re-contest objected to — flaw annotation, label basis and all.
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
