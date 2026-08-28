"""The admissibility gate's six readings, defect by defect, in full.

    cd exp2
    uv run python records/derivations/jd3-gate-smoke-read.py \
        > outputs/jd3-gate-smoke-read.txt

Read-only over `outputs/experiments/jd3-gate-smoke/`. It writes nothing and computes
nothing that is not a count of what is on disk.

**THE GATE IS A READING, NOT A NUMBER.** The house rule (`HANDOFF.md` §2.8) is that a new
prompt is tried on about six chosen examples and READ before a slice or a sweep. Six cells
cannot measure an admission rate and nothing here is scored. What is printed, per cell, is
what a person needs to check the gate against the two documents it was given:

  * the OBJECTION's defect list — type, the judgment quote, the record quote, and the
    harness's own parse-time `quote_in_judgment` flag beside each;
  * the MECHANICAL gate's answer on the same defect (`prompts.record_quotes_in_record`
    added on top of that flag) — no model, just whether the evidence exists;
  * the GATEKEEPER's per-defect finding, its reason, and its `Admissibility:` line;
  * the GRADER's per-defect verdict, if `jd3-main`'s grade stage has reached this cell —
    it is the nearest thing on the tree to an independent answer to the gate's own
    question, and where the two disagree is exactly what is worth reading;
  * the RECOURSE JUDGE's ruling, which is what the six were DRAWN on and is not an answer
    key: the judge ruled on MATERIALITY and the gate answers whether the defect is REAL.
    An objection can be real and immaterial, and a specious one can move a judge.

The three things that would stop M4 are all visible here and none of them is a rate:
replies that do not parse or need the repair every time; findings that answer a DIFFERENT
question (weighing materiality, or re-deciding whether the solution is flawed — the
failure the prompt is written against); and six admissions or six refusals with reasons
that do not turn on the documents.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TREE_NAME = sys.argv[1] if len(sys.argv) > 1 else "jd3-gate-smoke"
TREE = REPO / "outputs" / "experiments" / TREE_NAME
W = 100

sys.path.insert(0, str(REPO / "src"))
from exp2.persistence import load_run_record          # noqa: E402
from exp2.prompts import (                            # noqa: E402
    defect_quote_in_judgment,
    defect_quotes_in_record,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def latest(cell: Path) -> Path | None:
    for directory in sorted((cell / "contests").glob("*/runs/*"), reverse=True):
        if (directory / "admission.json").is_file():
            return directory
    return None


def wrap(text: str, width: int = 96, indent: str = "        ") -> str:
    """Hard-wrapped, because the file is read by a person in a terminal."""
    words, lines, line = str(text).split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(indent + l for l in lines if l)


def main() -> int:
    print("=" * W)
    print("THE ADMISSIBILITY PROMPT — SIX CELLS, READ IN FULL   [M4, POST HOC 2026-08-28]")
    print("=" * W)
    print(f"tree: {TREE}")
    print("model: the `gatekeeper_model` named in each cell's admission.json")
    print()
    print("Nothing here is scored. The six were drawn three OVERTURNED / three UPHELD by")
    print("the recourse judge, which is a contrast to read against and NOT an answer key:")
    print("the judge ruled on materiality and the gate answers whether the alleged defect")
    print("is real. Read each finding against the judgment and the record.")

    cells = sorted((TREE / "cells").glob("*"))
    if not cells:
        print(f"\n  NOT RUN — no cells under {TREE}.")
        return 1

    admitted = repairs = mismatches = 0
    agree_overturn = 0
    graded_seen = graded_agree = 0
    n = 0
    for cell in cells:
        directory = latest(cell)
        if directory is None:
            continue
        n += 1
        challenge = load(directory / "challenge.json") or {}
        admission = load(directory / "admission.json") or {}
        ruling = load(directory / "ruling.json") or {}
        grade = load(directory / "grade.json")
        if grade is None:
            # The gate copied this contest BEFORE `jd3-main`'s grade stage reached it, so
            # the copy has no grade of its own. The grade is of the OBJECTION and the
            # objection has not changed, so the source's is the right one to read — found
            # through the manifest, not by string surgery on the path, since the two run
            # directories carry different suffixes and different timestamps.
            manifest = load(directory / "run.json") or {}
            source = manifest.get("source_contest_dir")
            if source:
                grade = load(Path(source) / "grade.json")
        parent = load(directory / "parent" / "verdict.json") or {}
        record = load_run_record(directory / "parent")
        judgment, body = record.decision_grounds, record.challenger_view().body

        admitted += bool(admission.get("admitted"))
        repairs += int(admission.get("repair_attempts") or 0)
        mismatches += bool(admission.get("line_mismatch"))
        if bool(admission.get("admitted")) == bool(ruling.get("changed_the_decision")):
            agree_overturn += 1

        print()
        print("=" * W)
        print(f"CELL  {cell.name}")
        print("=" * W)
        print(f"  M0 verdict {parent.get('verdict')}   correct {parent.get('correct')}"
              f"   |   ruling: {'OVERTURNED' if ruling.get('changed_the_decision') else 'UPHELD'}"
              f" ({ruling.get('ruling')})")
        print(f"  gatekeeper: {admission.get('model')}   "
              f"parse_mode {admission.get('parse_mode')}   "
              f"repairs {admission.get('repair_attempts')}")
        print(f"  ADMISSIBILITY LINE: "
              f"{'ADMITTED' if admission.get('line_admitted') else 'REFUSED'}"
              f"   |   from its own findings: "
              f"{'ADMITTED' if admission.get('admitted') else 'REFUSED'}"
              f"{'   *** LINE/FINDINGS MISMATCH ***' if admission.get('line_mismatch') else ''}")

        findings = {f["index"]: f for f in (admission.get("findings") or [])}
        graded = {g["index"]: g for g in ((grade or {}).get("defects") or [])}
        defects = challenge.get("defects") or []
        print(f"\n  the objection alleges {len(defects)} defect(s):")
        for index, defect in enumerate(defects, 1):
            print()
            print(f"  --- Defect {index}: {defect.get('type')} "
                  + "-" * max(0, W - 22 - len(str(defect.get('type')))))
            for label, key in (("Judgment says", "judgment_says"),
                               ("Record says", "record_says")):
                for quote in defect.get(key) or []:
                    print(f"      {label}:")
                    print(wrap(quote))
            print(f"      Why it matters:")
            print(wrap(defect.get("why") or "(none given)"))
            print(f"      quote check  judgment: "
                  f"{defect_quote_in_judgment(defect, judgment)}"
                  f"   record: {defect_quotes_in_record(defect, body)}"
                  f"   (stored: {defect.get('quote_in_judgment')})")
            finding = findings.get(index)
            if finding is None:
                print("      GATEKEEPER: no finding for this defect")
            else:
                print(f"      GATEKEEPER: {'REAL' if finding['real'] else 'NOT REAL'}")
                print(wrap(finding.get("reason") or "(no reason given)"))
            if index in graded:
                graded_seen += 1
                verdict = graded[index]
                print(f"      GRADER:     "
                      f"{'VALID' if verdict.get('valid') else 'INVALID'}")
                print(wrap(verdict.get("reason") or "(no reason given)"))
                if bool(verdict.get("valid")) == bool((finding or {}).get("real")):
                    graded_agree += 1
            else:
                print("      GRADER:     not graded yet (jd3-main's grade stage)")

        reasoning = (admission.get("reasoning") or "").strip()
        if reasoning:
            print("\n  the gatekeeper's working, in full:")
            print(wrap(reasoning, indent="      "))

    print()
    print("=" * W)
    print("SUMMARY — counts of what is above, and not a result")
    print("=" * W)
    print(f"  cells read                         {n}")
    print(f"  ADMITTED                           {admitted}/{n}")
    print(f"  REFUSED                            {n - admitted}/{n}")
    print(f"  replies needing the one repair     {repairs}/{n}")
    print(f"  line contradicting its own findings {mismatches}/{n}")
    print(f"  admission agreeing with the judge's overturn   {agree_overturn}/{n}")
    print("     (a contrast to read, NOT a score: materiality and reality are different")
    print("      questions and they are expected to come apart)")
    if graded_seen:
        print(f"  defects with a grader verdict too  {graded_seen}")
        print(f"    gate and grader agreeing         {graded_agree}/{graded_seen}")
    else:
        print("  grader verdicts available          none — jd3-main's grade stage has")
        print("                                     not reached these cells")
    print()
    print("Read the findings, not this table. Six cells cannot measure an admission rate,")
    print("and the failure that would stop M4 — a gate that answers materiality or")
    print("re-decides the case — is invisible in every count above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
