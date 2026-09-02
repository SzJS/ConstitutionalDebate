"""Re-parse the fd1 smoke objections under R10 and say what it would have changed.

    cd exp2
    uv run python records/derivations/fd1-reparse-smokes.py 2>&1 | tee outputs/fd1-reparse-smokes.log

R10 swapped the `Record says:` matcher in `parse_finding_contests` for
`_record_quote_found`, the rule jd3's `record_quotes_in_record` gate already applied to a
judgment defect's record quotation: strict comparison, then every substantial quoted span,
then a leading attribution of up to sixty characters stripped. The change was forced by
smoke 2, where three of the weak arm's four contests were VOID on `quote_in_record` with
every span they quoted present in the record — `gemini-2.5-flash` writes the field as
`Alice: "…" Alice: "…"`, and the record renders its turns as `Round 1:\n  Alice: …`.

This script does not run a model and does not write into any tree. For every cell of the
four smoke trees that has a `challenge.json`, it re-runs the parser on the STORED objection
text against the STORED documents and prints three passes:

  * `stored`  — the flags as they were written at run time;
  * `pre-R10` — today's parser with `_record_quote_found` monkeypatched back to plain
    `quote_in_text`. Smoke 1 predates R1 (the rule that a finding contest's `Record says:`
    may quote the findings text), so a bare stored-vs-new comparison there would blame R10
    for R1's work; this column separates them. On smoke 2 it should equal `stored`, and
    where it does that is a check that the re-parse is faithful;
  * `new`     — today's parser as it stands, i.e. R10.

Then, for each cell, it replays the stored ruling — `conclusion_line` read by
`parse_findings_ruling_output`, applied by `apply_contest_lines`, verdict by
`derive_verdict` — over the new contest list, and prints the post-recourse verdict that
would have resulted beside the one that was recorded, scored against gold.

IT READS GOLD (`item.gold_flawed`). That is what a derivation is allowed to do and a
decision-path module is not: nothing here feeds a prompt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from exp2 import persistence, prompts
from exp2.prompts import (
    apply_contest_lines,
    derive_verdict,
    parse_finding_contests,
    parse_findings_ruling_output,
    quote_in_text,
    render_findings,
)
from exp2.types import FLAWED, SOUND, verdict_for

REPO = Path(__file__).resolve().parents[2]
TREES = ("fd1-smoke-weak", "fd1-smoke-strong", "fd1-smoke-2-weak", "fd1-smoke-2-strong")


def _flags(contests: list[dict[str, Any]], key: str) -> list[Any]:
    return [c[key] for c in contests]


def _parse(text: str, findings: list[dict[str, Any]], *, solution: str, record: str,
           findings_text: str, lenient: bool) -> list[dict[str, Any]]:
    """One pass of the parser, with the record matcher on (`lenient`) or off.

    The monkeypatch is on the module global the two `_all_record_quotes_in*` helpers look
    up, so switching it swaps exactly R10 and nothing else — the two-document rule, the
    per-kind requirements and every other flag stay as they are today.
    """
    original = prompts._record_quote_found
    if not lenient:
        prompts._record_quote_found = lambda quote, source: quote_in_text(quote, source)
    try:
        return parse_finding_contests(text, findings, solution=solution, record=record,
                                      findings_text=findings_text)
    finally:
        prompts._record_quote_found = original


def _replay(findings: list[dict[str, Any]], contests: list[dict[str, Any]],
            conclusion_line: str) -> tuple[str | None, str]:
    """The verdict this ruling would derive over this contest list, or `(None, why)`."""
    if not conclusion_line.strip():
        return None, "no ruling lines"
    try:
        lines, _, _ = parse_findings_ruling_output(conclusion_line, len(contests))
    except Exception as error:  # a ruling written against a different list length
        return None, f"unreadable ({type(error).__name__})"
    try:
        after = apply_contest_lines(findings, contests, lines)
    except ValueError as error:
        return None, f"inapplicable ({error})"
    return derive_verdict(after), ""


def cells(tree: Path) -> list[tuple[str, Path]]:
    out = []
    for cell in sorted((tree / "cells").glob("*")):
        for challenge in sorted(cell.glob("contests/*/runs/*/challenge.json")):
            out.append((cell.name, challenge.parent))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "outputs")
    parser.add_argument("--trees", nargs="*", default=list(TREES))
    args = parser.parse_args()

    totals: dict[str, dict[str, int]] = {}
    verdict_changes: list[str] = []
    for name in args.trees:
        tree = args.out / "experiments" / name
        if not tree.is_dir():
            print(f"\n### {name}: no such tree, skipped")
            continue
        counted = {"contests": 0, "void_stored": 0, "void_pre": 0, "void_new": 0,
                   "verdict_changed": 0, "fixed": 0, "broken": 0, "cells": 0,
                   "r10_moved": 0}
        print(f"\n### {name}")
        for cell_name, run in cells(tree):
            challenge = json.loads((run / "challenge.json").read_text())
            stored = challenge.get("defects") or []
            record = persistence.load_run_record(run / "parent")
            findings_blob = persistence.load_findings(run / "parent") or {}
            findings = findings_blob.get("findings") or []
            documents = {
                "solution": record.item.solution,
                "record": record.challenger_view().body,
                "findings_text": render_findings(record.decision_grounds),
            }
            pre = _parse(challenge["text"], findings, lenient=False, **documents)
            new = _parse(challenge["text"], findings, lenient=True, **documents)
            counted["cells"] += 1
            counted["contests"] += len(new)
            counted["void_stored"] += sum(1 for c in stored if c["void"])
            counted["void_pre"] += sum(1 for c in pre if c["void"])
            counted["void_new"] += sum(1 for c in new if c["void"])

            print(f"\n  {cell_name}  ({len(new)} contest(s), gold "
                  f"{'FLAWED' if record.item.gold_flawed else 'SOUND'})")
            print(f"    kind         {_flags(new, 'kind')}")
            print(f"    quote_in_record  stored {_flags(stored, 'quote_in_record')}"
                  f"  pre-R10 {_flags(pre, 'quote_in_record')}"
                  f"  new {_flags(new, 'quote_in_record')}")
            print(f"    void             stored {_flags(stored, 'void')}"
                  f"  pre-R10 {_flags(pre, 'void')}"
                  f"  new {_flags(new, 'void')}")

            ruling_path = run / "ruling.json"
            if not ruling_path.is_file():
                print("    ruling: none (the cell did not reach a ruling)")
                continue
            ruling = json.loads(ruling_path.read_text())
            line = ruling.get("conclusion_line") or ""
            recorded = ruling.get("verdict")
            would, why = _replay(findings, new, line)
            before, why_before = _replay(findings, pre, line)
            gold = verdict_for(record.item.gold_flawed)
            print(f"    ruling lines     {line.splitlines()}")
            print(f"    verdict          recorded {recorded}"
                  f"   pre-R10 {before if before is not None else f'n/a — {why_before}'}"
                  f"   under R10 {would if would is not None else f'n/a — {why}'}"
                  f"   gold {gold}")
            # WHICH CHANGE MOVED IT. `recorded` is what the run wrote, `pre-R10` what
            # today's parser without the record matcher derives, `under R10` what it
            # derives with it. A cell where `pre-R10` already differs from `recorded` was
            # moved by R1, not by this change, and smoke 1 predates R1.
            if before is not None and would is not None and before != would:
                counted["r10_moved"] += 1
            if would is not None and would != recorded:
                counted["verdict_changed"] += 1
                if would == gold and recorded != gold:
                    counted["fixed"] += 1
                    label = "FIXED"
                elif would != gold and recorded == gold:
                    counted["broken"] += 1
                    label = "BROKEN"
                else:
                    label = "moved, same correctness"
                print(f"    >>> {label}: {recorded} -> {would} (gold {gold})")
                verdict_changes.append(f"{name}/{cell_name}: {recorded} -> {would} "
                                       f"(gold {gold}) — {label}")
        totals[name] = counted

    print("\n\n### SUMMARY")
    header = (f"{'tree':<20}{'cells':>6}{'contests':>10}{'void stored':>13}"
              f"{'void pre-R10':>14}{'void new':>10}{'v. moved':>10}"
              f"{'by R10':>8}{'fixed':>7}{'broken':>8}")
    print(header)
    print("-" * len(header))
    for name, c in totals.items():
        print(f"{name:<20}{c['cells']:>6}{c['contests']:>10}{c['void_stored']:>13}"
              f"{c['void_pre']:>14}{c['void_new']:>10}{c['verdict_changed']:>10}"
              f"{c['r10_moved']:>8}{c['fixed']:>7}{c['broken']:>8}")
    grand = {k: sum(c[k] for c in totals.values()) for k in
             ("cells", "contests", "void_stored", "void_pre", "void_new",
              "verdict_changed", "r10_moved", "fixed", "broken")}
    print(f"{'ALL':<20}{grand['cells']:>6}{grand['contests']:>10}"
          f"{grand['void_stored']:>13}{grand['void_pre']:>14}{grand['void_new']:>10}"
          f"{grand['verdict_changed']:>10}{grand['r10_moved']:>8}"
          f"{grand['fixed']:>7}{grand['broken']:>8}")
    print("\n`v. moved` is recorded vs R10 and so includes R1's work on smoke 1; "
          "`by R10` is pre-R10 vs R10, this change alone.")
    print("\nverdicts that move under R10:")
    for line in verdict_changes or ["  (none)"]:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
