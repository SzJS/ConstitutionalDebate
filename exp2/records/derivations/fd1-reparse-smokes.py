"""Re-parse the fd1 smoke objections under today's rules and say what would change.

    cd exp2
    uv run python records/derivations/fd1-reparse-smokes.py 2>&1 | tee outputs/fd1-reparse-smokes.log
    uv run python records/derivations/fd1-reparse-smokes.py --tree fd1-pilot-weak fd1-pilot-strong

`--tree` takes tree names under `outputs/experiments/`, or paths; the default is the four
smoke trees. It runs on any tree with `challenge.json` files in it, the pilots and the
full runs included.

WHAT R12a ADDED TO THIS SCRIPT (2026-09-02). The void rule was narrowed again: a contest
of a FINDING is no longer void because an OPTIONAL `Record says:` could not be found —
`Text says:` is that kind's anchor and the only quotation it is required to give. Smoke 3
forced it: on `strong/law` the challenger gave two real record quotations joined by "and",
each prefixed `"Bob: `, the ruling judge found both and ruled the contest, and the harness
discarded its line. The second summary table below counts what the rule now records
rather than enforces — `record unverified` — and how many stored-void contests it gives
back (`un-voided by R12a`).

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


def tree_path(name: str, out: Path) -> Path:
    """A `--tree` argument, as a directory. A bare name is looked up under `<out>/
    experiments/`; anything with a separator in it, or that already exists, is taken as
    the path it is — so the pilots and the full runs can be given by path without moving
    them or symlinking them under another name."""
    candidate = Path(name)
    if candidate.is_dir() or candidate.is_absolute() or len(candidate.parts) > 1:
        return candidate
    return out / "experiments" / name


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
    # `--tree` is the name; `--trees` is kept as an alias because the log of the first
    # run of this script names it, and a command in a record has to stay runnable.
    # ACCUMULATES rather than overwrites, so `--tree a --tree b` and `--tree a b` both
    # run both trees. With the plain `nargs="*"` the repeated form silently kept only
    # the LAST tree, which is a summary table that looks complete and is not.
    parser.add_argument("--tree", "--trees", dest="trees", nargs="*", action="extend",
                        default=None,
                        help="tree names under <out>/experiments, or paths. Repeatable. "
                             "Default: the four smoke trees.")
    args = parser.parse_args()
    if not args.trees:
        args.trees = list(TREES)

    totals: dict[str, dict[str, int]] = {}
    verdict_changes: list[str] = []
    for name in args.trees:
        tree = tree_path(name, args.out)
        if not tree.is_dir():
            print(f"\n### {name}: no such tree, skipped")
            continue
        counted = {"contests": 0, "void_stored": 0, "void_pre": 0, "void_new": 0,
                   "verdict_changed": 0, "fixed": 0, "broken": 0, "cells": 0,
                   "r10_moved": 0, "finding_contests": 0, "record_unverified": 0,
                   "unvoided_by_r12a": 0}
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
            # R12a. `record_unverified` is a contest of a FINDING that gave a `Record
            # says:` the matcher could not find. It no longer voids — the field is
            # optional for this kind and the anchor is `Text says:` — so it is counted
            # separately from `void_new` and never inside it. `unvoided_by_r12a` is the
            # subset of those that WERE void as stored: the contests this change gives
            # back, which on smoke 3 is the whole of what it does, since both smoke-3
            # arms already ran under R10 and R11.
            counted["finding_contests"] += sum(
                1 for c in new if c["kind"] == "finding")
            unverified = [c for c in new
                          if c["kind"] == "finding" and c["quote_in_record"] is False]
            counted["record_unverified"] += len(unverified)
            by_index = {c["index"]: c for c in stored}
            counted["unvoided_by_r12a"] += sum(
                1 for c in unverified
                if by_index.get(c["index"], {}).get("void") and not c["void"])

            print(f"\n  {cell_name}  ({len(new)} contest(s), gold "
                  f"{'FLAWED' if record.item.gold_flawed else 'SOUND'})")
            print(f"    kind         {_flags(new, 'kind')}")
            print(f"    quote_in_record  stored {_flags(stored, 'quote_in_record')}"
                  f"  pre-R10 {_flags(pre, 'quote_in_record')}"
                  f"  new {_flags(new, 'quote_in_record')}")
            print(f"    void             stored {_flags(stored, 'void')}"
                  f"  pre-R10 {_flags(pre, 'void')}"
                  f"  new {_flags(new, 'void')}")
            if unverified:
                print(f"    record UNVERIFIED (finding contests, recorded and not "
                      f"voiding): {[c['index'] for c in unverified]}")

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
    keys = ("cells", "contests", "void_stored", "void_pre", "void_new",
            "verdict_changed", "r10_moved", "fixed", "broken")
    header = (f"{'tree':<22}{'cells':>6}{'contests':>10}{'void stored':>13}"
              f"{'void pre-R10':>14}{'void new':>10}{'v. moved':>10}"
              f"{'by R10':>8}{'fixed':>7}{'broken':>8}")
    print(header)
    print("-" * len(header))
    for name, c in totals.items():
        print(f"{name:<22}{c['cells']:>6}{c['contests']:>10}{c['void_stored']:>13}"
              f"{c['void_pre']:>14}{c['void_new']:>10}{c['verdict_changed']:>10}"
              f"{c['r10_moved']:>8}{c['fixed']:>7}{c['broken']:>8}")
    grand = {k: sum(c[k] for c in totals.values()) for k in keys}
    print(f"{'ALL':<22}{grand['cells']:>6}{grand['contests']:>10}"
          f"{grand['void_stored']:>13}{grand['void_pre']:>14}{grand['void_new']:>10}"
          f"{grand['verdict_changed']:>10}{grand['r10_moved']:>8}"
          f"{grand['fixed']:>7}{grand['broken']:>8}")

    # R12a's own table, kept apart from the one above because it counts a different
    # thing: `void new` is what the rules as they stand set aside, and these three
    # columns are the check that was demoted to a report.
    print()
    header = (f"{'tree':<22}{'finding contests':>18}{'void new':>10}"
              f"{'record unverified':>19}{'un-voided by R12a':>19}")
    print(header)
    print("-" * len(header))
    for name, c in totals.items():
        print(f"{name:<22}{c['finding_contests']:>18}{c['void_new']:>10}"
              f"{c['record_unverified']:>19}{c['unvoided_by_r12a']:>19}")
    r12 = {k: sum(c[k] for c in totals.values()) for k in
           ("finding_contests", "void_new", "record_unverified", "unvoided_by_r12a")}
    print(f"{'ALL':<22}{r12['finding_contests']:>18}{r12['void_new']:>10}"
          f"{r12['record_unverified']:>19}{r12['unvoided_by_r12a']:>19}")
    print("\n`record unverified` is a contest of a FINDING whose optional `Record says:` "
          "was\ngiven and not found. Since R12a it is RECORDED and does not void; "
          "`un-voided by R12a`\nis how many of them were void as stored, i.e. what this "
          "change gives back.")
    print("\n`v. moved` is recorded vs R10 and so includes R1's work on smoke 1; "
          "`by R10` is pre-R10 vs R10, this change alone.")
    print("\nverdicts that move under R10:")
    for line in verdict_changes or ["  (none)"]:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
