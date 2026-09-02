"""Count the record defects `fd1` INHERITS from the debates it re-judges.

    cd exp2
    uv run python records/derivations/fd1-source-scan.py 2>&1 | tee outputs/fd1-source-scan.log

READ-ONLY over `outputs/experiments/jd3-main` — the 1,644 stored debate decisions every
fd1 spec re-judges (`transcripts_from`) — plus its `index.jsonl` for the subset of each
cell. Writes exactly one file, `outputs/fd1-source-scan.json`. Nothing under
`outputs/experiments/` is touched.

WHY THIS EXISTS. The findings campaign does not re-run a single debate: the judge, the
challenger, the ruling judge and the grader are all shown transcripts that were generated
in the sweep and re-judged by jd3, and any defect already in those turns is a defect fd1
inherits and cannot fix. Smoke 2's read raised three of them by name. This script says how
common each is across the whole population, so PREREG can state the caveat as a NUMBER
rather than as an impression, and so a reader of the findings lists knows how much of what
the judge is decomposing is scaffolding rather than argument.

IT EXCLUDES NOTHING. Every decided cell is scanned and counted; no cell is dropped,
flagged or repaired on the strength of what is found here. That is the whole point — a
scan that removed the cells it did not like would turn a caveat into a silent filter, and
the arms would no longer be run on the population PREREG names.

WHAT IS COUNTED, per cell, over the PUBLIC arguments of the stored turns
(`transcript.json`'s `turns[*].argument` — the text every fd1 prompt is shown; the private
`thinking` field is never read here, because no fd1 role is ever shown it):

  * GLUED `Argument:` LABELS (`\\S\\s*Argument:`). The debater prompt asks for a
    `Thinking:` block and then an `Argument:` block; a model that writes
    "...my case. Argument: ..." glues the label onto the end of a sentence, and the
    repair path recovers the turn by taking everything after the LAST label — so a glued
    label inside the published argument is text the parser kept and a reader meets as
    part of the argument. `salvaged_no_thinking` in the sweep's parse modes is the same
    behaviour seen from the other side.

  * SCAFFOLDING TAGS (`<thinking>`, `</thinking>`, `<argument>`, `</argument>`). The
    prompts ask for labels, not tags; a turn that carries them is a turn whose model
    answered in a format nobody asked for and whose published text now contains markup a
    findings judge may quote into a `Passage:`.

  * PRIVATE-DELIBERATION MARKERS — four phrases that only appear when a debater's
    private reasoning about its ASSIGNMENT has been published as its argument: "I need to
    respond as", "I am assigned the position", "I must argue otherwise", "My previous
    argument was weak". This is the one defect that changes what a finding MEANS: a
    finding quoting such a sentence is a finding about the harness, not about the text
    under review, and the cells that carry one are listed by id so they can be read.

Matching is case-sensitive and literal for the markers and the tags, which is deliberate:
a loosened match would count paraphrases the phrase list was not chosen for, and the
number is meant to be a floor that a reader can reproduce with `grep`.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
EXP2 = HERE.parents[2]
TREE = EXP2 / "outputs" / "experiments" / "jd3-main"
OUT = EXP2 / "outputs" / "fd1-source-scan.json"

# The glued label. `\S` before it rather than `\w` so "case.Argument:" and "case)Argument:"
# both count; `\s*` so the common form — a space after the full stop — is caught too. A
# label at the START of a line is the format the prompt asked for and is not a defect.
GLUED_ARGUMENT_RE = re.compile(r"\S\s*Argument:")

SCAFFOLDING_TAGS: tuple[str, ...] = (
    "<thinking>", "</thinking>", "<argument>", "</argument>")

PRIVATE_MARKERS: tuple[str, ...] = (
    "I need to respond as",
    "I am assigned the position",
    "I must argue otherwise",
    "My previous argument was weak",
)


def decided_cells(tree: Path) -> list[dict[str, Any]]:
    """The index rows, which ARE the decided cells: one row per cell with a verdict."""
    index = tree / "index.jsonl"
    if not index.is_file():
        raise SystemExit(f"  ! {index} is not on disk")
    rows = [json.loads(line) for line in index.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row.get("verdict")]


def arguments_for(tree: Path, cell_id: str) -> tuple[list[str], str | None]:
    """``(the public arguments of the cell's stored turns, why they are missing)``."""
    runs = tree / "cells" / cell_id / "runs"
    if not runs.is_dir():
        return [], "no runs directory"
    transcripts = sorted(path for path in runs.glob("*/transcript.json"))
    if not transcripts:
        return [], "no transcript.json"
    # The LATEST run, on the same rule the index follows: a cell re-attempted under
    # `--retry-failed` is decided by its last run, and that is the transcript the fd1
    # prompts would be shown.
    stored = json.loads(transcripts[-1].read_text(encoding="utf-8"))
    return [str(turn.get("argument") or "") for turn in stored.get("turns") or []], None


def scan_text(text: str) -> dict[str, Any]:
    """The three counts over one argument."""
    return {
        "glued_argument_n": len(GLUED_ARGUMENT_RE.findall(text)),
        "tags": {tag: text.count(tag) for tag in SCAFFOLDING_TAGS},
        "markers": {marker: text.count(marker) for marker in PRIVATE_MARKERS},
    }


def main(tree: Path = TREE, out: Path = OUT) -> int:
    rows = decided_cells(tree)
    print(f"{tree}: {len(rows)} decided cells (a `verdict` in index.jsonl)")

    per_cell: dict[str, dict[str, Any]] = {}
    totals = Counter()
    tag_totals = Counter()
    marker_totals = Counter()
    by_subset: dict[str, Counter] = defaultdict(Counter)
    subset_cells: Counter = Counter()
    flagged: list[tuple[str, str, list[str]]] = []
    missing: list[str] = []

    for row in rows:
        cell_id = row["cell_id"]
        subset = row.get("subset") or "unknown"
        subset_cells[subset] += 1
        arguments, why = arguments_for(tree, cell_id)
        if why is not None:
            missing.append(f"{cell_id}: {why}")
        glued = 0
        tags = Counter()
        markers = Counter()
        for text in arguments:
            found = scan_text(text)
            glued += found["glued_argument_n"]
            tags.update({k: v for k, v in found["tags"].items() if v})
            markers.update({k: v for k, v in found["markers"].items() if v})
        counts = {
            "subset": subset,
            "turns_n": len(arguments),
            "glued_argument_n": glued,
            "scaffolding_tag_n": sum(tags.values()),
            "tags": dict(tags),
            "private_marker_n": sum(markers.values()),
            "markers": dict(markers),
        }
        per_cell[cell_id] = counts

        totals["cells"] += 1
        totals["turns"] += len(arguments)
        totals["glued_argument_n"] += glued
        totals["scaffolding_tag_n"] += sum(tags.values())
        totals["private_marker_n"] += sum(markers.values())
        totals["cells_with_glued"] += bool(glued)
        totals["cells_with_tags"] += bool(sum(tags.values()))
        totals["cells_with_markers"] += bool(sum(markers.values()))
        tag_totals.update(tags)
        marker_totals.update(markers)
        by_subset[subset]["glued_argument_n"] += glued
        by_subset[subset]["scaffolding_tag_n"] += sum(tags.values())
        by_subset[subset]["private_marker_n"] += sum(markers.values())
        by_subset[subset]["cells_with_glued"] += bool(glued)
        by_subset[subset]["cells_with_tags"] += bool(sum(tags.values()))
        by_subset[subset]["cells_with_markers"] += bool(sum(markers.values()))
        if markers:
            flagged.append((cell_id, subset, sorted(markers)))

    print(f"  turns scanned: {totals['turns']}")
    if missing:
        print(f"  ! {len(missing)} cells had no readable transcript:")
        for line in missing[:20]:
            print(f"      {line}")

    print("\nTOTALS (occurrences, and the cells carrying at least one)")
    print(f"  glued `Argument:` inside an argument : {totals['glued_argument_n']:6d} "
          f"in {totals['cells_with_glued']:5d} of {totals['cells']} cells "
          f"({totals['cells_with_glued'] / max(totals['cells'], 1):.1%})")
    print(f"  scaffolding tags                     : {totals['scaffolding_tag_n']:6d} "
          f"in {totals['cells_with_tags']:5d} of {totals['cells']} cells "
          f"({totals['cells_with_tags'] / max(totals['cells'], 1):.1%})")
    for tag in SCAFFOLDING_TAGS:
        print(f"      {tag:<14} {tag_totals.get(tag, 0):6d}")
    print(f"  private-deliberation markers         : {totals['private_marker_n']:6d} "
          f"in {totals['cells_with_markers']:5d} of {totals['cells']} cells "
          f"({totals['cells_with_markers'] / max(totals['cells'], 1):.1%})")
    for marker in PRIVATE_MARKERS:
        print(f"      {marker!r:<32} {marker_totals.get(marker, 0):6d}")

    print("\nPER SUBSET (cells; occurrences; cells carrying at least one)")
    header = (f"{'subset':<12}{'cells':>7}{'glued':>8}{'w/glued':>9}{'tags':>7}"
              f"{'w/tags':>8}{'private':>9}{'w/private':>11}")
    print(header)
    print("-" * len(header))
    for subset in sorted(by_subset):
        counts = by_subset[subset]
        print(f"{subset:<12}{subset_cells[subset]:>7}"
              f"{counts['glued_argument_n']:>8}{counts['cells_with_glued']:>9}"
              f"{counts['scaffolding_tag_n']:>7}{counts['cells_with_tags']:>8}"
              f"{counts['private_marker_n']:>9}{counts['cells_with_markers']:>11}")

    print(f"\nCELLS WITH ANY PRIVATE-DELIBERATION MARKER ({len(flagged)})")
    if not flagged:
        print("  none")
    for cell_id, subset, markers in sorted(flagged):
        print(f"  {cell_id:<60} {subset:<10} {'; '.join(markers)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(per_cell, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {len(per_cell)} cells -> {out}")
    print("NOTHING IS EXCLUDED on the strength of this scan; it is a PREREG caveat, "
          "and every cell above stays in every table.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, default=TREE,
                        help="the experiment tree to scan (default: jd3-main)")
    parser.add_argument("--out", type=Path, default=OUT,
                        help="the JSON file written "
                             "(default: outputs/fd1-source-scan.json)")
    args = parser.parse_args()
    raise SystemExit(main(tree=args.tree, out=args.out))
