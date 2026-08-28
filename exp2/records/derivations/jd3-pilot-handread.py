"""jd3 PILOT — twenty things rendered in full for a human to read.

    cd exp2
    uv run python records/derivations/jd3-pilot-handread.py \
        > outputs/jd3-pilot-handread.txt

Read-only; it touches nothing. Two halves, and they answer different questions.

PART 1 — TEN MAVERICK JUDGMENTS, each beside the LAST ROUND of the debate it judged.
The whole campaign turns on Maverick being a judge of the debate rather than a solver of
the problem, because the audit that follows is an audit of the JUDGMENT and there has to
be a judgment there to audit. What a reader is checking:

  1. Does it weigh the two sides — quoting or naming what each argued and saying which
     answered the other — or does it re-derive the answer from the problem and mention
     the debate only in passing? A strong judge re-solving from scratch is exactly what
     `DESIGN.md`'s `## Recourse judge strength` warns about, one seat over.
  2. Does it state grounds BEFORE the verdict line? A judgment that answers and then
     explains, or that states no grounds at all, leaves the auditor nothing.
  3. Is it about the text under review, or has it drifted onto the debaters' conduct?

The last round is printed rather than the whole transcript because it is what the
judgment most often echoes, and printing six rounds per cell would make ten judgments
unreadable. The full record is one file away: `transcript.md` in the run directory named
at the head of each block.

PART 2 — TEN OBJECTION + GRADE + RULING TRIPLES, five overturns and five upholds. The
same three questions `judge-pick-handread.py` asks, now on Maverick's own judgments and
with the grader's per-defect verdicts printed beside them:

  1. Does the ruling do the TWO STEPS the materiality prompt asks — is each alleged
     defect real against the record, and if so is it material — or does it re-solve the
     object level and let its line follow that?
  2. Does the final line follow from the reasoning above it? A ruling whose prose finds a
     defect real and material and then copies the parent's line is the residual
     `ruling_line_mismatch` counts, and it is invisible in a net figure.
  3. Does the GRADER's per-defect reasoning hold up against the record — and does its
     summary line agree with its own per-defect verdicts?

Both halves are selected in CELL ORDER within their strata, so the choice is not made
after reading them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

W = 100


def load_index(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["cell_id"]] = row
    return rows


def decision_dir(tree: Path, cell_id: str) -> Path | None:
    for directory in sorted((tree / "cells" / cell_id / "runs").glob("*"), reverse=True):
        if (directory / "verdict.json").is_file():
            return directory
    return None


def contest_dir(tree: Path, cell_id: str) -> Path | None:
    base = tree / "cells" / cell_id / "contests"
    for directory in sorted(base.glob("*/runs/*"), reverse=True):
        if (directory / "challenge.json").is_file():
            return directory
    return None


def quote(text: str, prefix: str = "    | ") -> None:
    for line in (text or "").splitlines() or [""]:
        print(f"{prefix}{line}")


def gold_of(row) -> str:
    return "FLAWED" if row.get("gold_flawed") else "SOUND"


# --------------------------------------------------------------------------- #
# part 1 — the judgments
# --------------------------------------------------------------------------- #


def render_judgment(tree: Path, cell_id: str, row: dict, n: int) -> None:
    directory = decision_dir(tree, cell_id)
    if directory is None:
        print(f"  ! no decision directory for {cell_id}")
        return
    verdict = json.loads((directory / "verdict.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    transcript = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
    sides = json.loads((directory / "sides.json").read_text(encoding="utf-8"))
    item = json.loads((directory / "item.json").read_text(encoding="utf-8"))
    turns = transcript["turns"]
    last_round = max(t["round"] for t in turns) if turns else 0

    print()
    print("=" * W)
    print(f"[J{n}] {cell_id}")
    print("=" * W)
    print(f"  record            {directory}")
    print(f"  subset            {row.get('subset')}    label_basis "
          f"{row.get('label_basis')}")
    print(f"  GOLD              {gold_of(row)}   (the dataset's label; no prompt saw it)")
    print(f"  NANO (the sweep)  {manifest.get('source_verdict')}   "
          f"{'CORRECT' if manifest.get('source_correct') else 'WRONG'}")
    print(f"  MAVERICK (M0)     {verdict.get('verdict')}   "
          f"{'CORRECT' if verdict.get('correct') else 'WRONG'}"
          f"   {'— THE TWO JUDGES DISAGREE' if verdict.get('verdict') != manifest.get('source_verdict') else ''}")
    print(f"  parse             {verdict.get('parse_mode')}   repairs "
          f"{verdict.get('repair_attempts')}   finish {verdict.get('finish_reason')}")
    print(f"  sides             Alice argued {sides['alice_side']}, Bob argued "
          f"{sides['bob_side']}; the template listed "
          f"{sides['verdict_order'][0]} first")
    print()
    print("-" * W)
    print(f"  THE PROBLEM (opening, for orientation only)")
    print("-" * W)
    problem = (item.get("problem") or "").strip().splitlines()
    quote("\n".join(problem[:6]) + ("\n    [...]" if len(problem) > 6 else ""))
    print()
    print("-" * W)
    print(f"  THE LAST ROUND OF THE DEBATE (round {last_round} of {last_round})")
    print("-" * W)
    for turn in sorted((t for t in turns if t["round"] == last_round),
                       key=lambda t: t["speaker"]):
        print(f"  {turn['speaker'].upper()} — arguing {turn['side']} "
              f"({turn['word_count']} words)")
        quote(turn["argument"])
        print()
    print("-" * W)
    print("  THE JUDGMENT, IN FULL — this is the document the auditor audits")
    print("-" * W)
    quote(verdict.get("raw") or "")
    print()


# --------------------------------------------------------------------------- #
# part 2 — objection, grade, ruling
# --------------------------------------------------------------------------- #


def render_triple(tree: Path, cell_id: str, row: dict, n: int) -> None:
    directory = contest_dir(tree, cell_id)
    if directory is None:
        print(f"  ! no contest directory for {cell_id}")
        return
    challenge = json.loads((directory / "challenge.json").read_text(encoding="utf-8"))
    ruling_path = directory / "ruling.json"
    ruling = (json.loads(ruling_path.read_text(encoding="utf-8"))
              if ruling_path.is_file() else {})
    grade_path = directory / "grade.json"
    grade = (json.loads(grade_path.read_text(encoding="utf-8"))
             if grade_path.is_file() else {})
    reading_path = directory / "ruling_agreement.json"
    reading = (json.loads(reading_path.read_text(encoding="utf-8"))
               if reading_path.is_file() else None)
    agreement_path = directory / "agreement.json"
    agreement = (json.loads(agreement_path.read_text(encoding="utf-8"))
                 if agreement_path.is_file() else None)

    print()
    print("=" * W)
    print(f"[T{n}] {cell_id}   "
          f"{'OVERTURN' if row.get('changed_the_decision') else 'UPHOLD'}")
    print("=" * W)
    print(f"  record            {directory}")
    print(f"  subset            {row.get('subset')}    label_basis "
          f"{row.get('label_basis')}")
    print(f"  GOLD              {gold_of(row)}")
    print(f"  M0 VERDICT        {row.get('verdict')}   "
          f"{'CORRECT' if row.get('initially_correct') else 'WRONG'}"
          f"   (nano said {row.get('source_verdict')})")
    print(f"  RULING            {ruling.get('ruling')}  ->  verdict "
          f"{ruling.get('verdict')}   "
          f"{'CORRECT' if ruling.get('correct') else 'WRONG'} after recourse")
    print(f"  prompt form       {ruling.get('prompt_form')}   form "
          f"{ruling.get('form')}   parse {ruling.get('parse_mode')}")
    if reading:
        print(f"  RULING READER     prose says {reading.get('prose_conclusion')}   "
              f"line says {reading.get('line_conclusion')}   "
              f"mismatch {reading.get('mismatch')}")
    if agreement:
        print(f"  OBJECTION READER  line {agreement.get('line_word')}   prose "
              f"{agreement.get('prose_stance')}   agrees {agreement.get('agrees')}   "
              f"phantom {agreement.get('phantom_contest')}")
    print(f"  GRADE             valid={grade.get('valid')}   "
          f"defects {grade.get('defects_valid_n')}/{grade.get('defects_n')} verified"
          f"   line_mismatch {grade.get('line_mismatch')}")
    print()
    print("-" * W)
    print("  THE OBJECTION — the defect list as `parse_defects` read it")
    print("-" * W)
    for i, defect in enumerate(challenge.get("defects") or [], 1):
        print(f"  {i}. type: {defect.get('type')}    "
              f"quote_in_judgment: {defect.get('quote_in_judgment')}")
        for text in defect.get("judgment_says") or []:
            print(f"       Judgment says: {text}")
        for text in defect.get("record_says") or []:
            print(f"       Record says:   {text}")
        if defect.get("why"):
            print(f"       Why:           {defect['why']}")
    print()
    print("  the objection as the grader and the judge were handed it:")
    quote(challenge.get("text") or "")
    print()
    print("-" * W)
    print("  THE GRADE — per defect, then the summary line")
    print("-" * W)
    for defect in grade.get("defects") or []:
        verdict = ("VALID" if defect.get("valid") else "INVALID")
        print(f"  defect {defect.get('index')} ({defect.get('type')}): {verdict}"
              f"   alleged={defect.get('alleged')}")
        print(f"      {defect.get('reason')}")
    if grade.get("reasoning"):
        print("  the grader's reasoning, in full:")
        quote(grade.get("reasoning"))
    print()
    print("-" * W)
    print("  THE RULING — the judge's reasoning, in full")
    print("-" * W)
    quote(ruling.get("reasoning") or "")
    print()
    print(f"  the line it ended on: {ruling.get('conclusion_line')!r}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path,
                        default=Path("outputs/experiments/jd3-pilot"))
    parser.add_argument("--judgments", type=int, default=10)
    parser.add_argument("--triples", type=int, default=10)
    args = parser.parse_args()

    rows = load_index(args.tree / "index.jsonl")
    print("#" * W)
    print("# jd3 PILOT — READ BY HAND")
    print("#" * W)
    print(f"# tree: {args.tree}")
    print("# Part 1: Maverick's judgments beside the debate's last round.")
    print("# Part 2: objection + grade + ruling, five overturns and five upholds.")
    print("# The questions each part exists to answer are in the module docstring of")
    print("# records/derivations/jd3-pilot-handread.py.")
    print("#" * W)

    # Part 1: half where the two judges disagree — that is where a reader can see WHICH
    # judge read the debate — and half where they agree, taken in cell order in each.
    ordered = sorted(rows.items())
    disagree = [(c, r) for c, r in ordered if r.get("verdict") != r.get("source_verdict")]
    agree = [(c, r) for c, r in ordered if r.get("verdict") == r.get("source_verdict")]
    half = args.judgments // 2
    chosen = disagree[:half] + agree[:args.judgments - half]
    print(f"\n\n{'#' * W}")
    print(f"# PART 1 — {len(chosen)} JUDGMENTS "
          f"({min(half, len(disagree))} where Maverick and nano DISAGREE, "
          f"the rest where they agree)")
    print("#" * W)
    for n, (cell_id, row) in enumerate(chosen, 1):
        render_judgment(args.tree, cell_id, row, n)

    over = [(c, r) for c, r in ordered
            if r.get("ruling_form") and r.get("changed_the_decision")]
    up = [(c, r) for c, r in ordered
          if r.get("ruling_form") and not r.get("changed_the_decision")]
    half = args.triples // 2
    triples = over[:half] + up[:args.triples - half]
    print(f"\n\n{'#' * W}")
    print(f"# PART 2 — {len(triples)} TRIPLES ({min(half, len(over))} overturns, "
          f"{len(triples) - min(half, len(over))} upholds)")
    print("#" * W)
    for n, (cell_id, row) in enumerate(triples, 1):
        render_triple(args.tree, cell_id, row, n)

    print()
    print("#" * W)
    print(f"# {len(chosen)} judgments and {len(triples)} triples rendered.")
    print("#" * W)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
