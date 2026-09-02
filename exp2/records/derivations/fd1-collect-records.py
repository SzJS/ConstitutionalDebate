"""Copy the summary artifacts of `findings-1` into its records directory.

    cd exp2
    uv run python records/derivations/fd1-collect-records.py 2>&1 | tee outputs/fd1-collect.log

`outputs/` is git-ignored, so this is what carries the evidence into git: the SUMMARY
artifacts only, so that every number in `LLM_NOTES.md` §3ad can be checked against a file
rather than taken on trust. It reads `outputs/experiments/fd1-{weak,strong}/` and the
campaign's logs, and writes only under `records/experiments/findings-1/`. It follows
`judgment-debate-6`'s layout exactly, so a reader who knows that directory knows this one.

It copies rather than summarises, and it NEVER TOUCHES `PREREG.md` or `run-all.sh`, which
were committed before the first paid call and must not move afterwards.

`transcripts/` takes the cells named in `outputs/fd1-handcheck-pick.md`, each as
`<group>__<arm>__<cell_id>__<what>__<file>` so the five groups and the two arms stay
legible in one flat listing. Both documents come across for every cell: `transcript.md`,
the readable record, and `transcript_full.md`, the same run verbatim with every prompt and
reply. The DECISION run comes across as well as the CONTEST run, because this campaign's
decision document is the one that carries the findings list — without it half of what the
hand check is about is missing.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# THE DEFAULTS ARE THE PRODUCTION PATHS and every one of them is a flag, for the reason
# every derivation in this directory takes flags: the script has to be runnable, and
# reviewable, against a smoke tree before the campaign it is written for exists. `--out`,
# `--records`, `--weak-tree` and `--strong-tree` are what a dry run moves.
OUT = REPO / "outputs"
RECORDS = REPO / "records" / "experiments" / "findings-1"
ARMS = {"arm-weak": "fd1-weak", "arm-strong": "fd1-strong"}
# What a reader needs to recompute a number, and nothing that would make this directory an
# input to a stage: no cells the run decided, no wire logs, no copied parents.
SUMMARY = ("index.jsonl", "metrics.json", "cells.jsonl", "experiment.json")
# The contest record's own files, for the hand-checked cells. `findings.after.json` is on
# this list and `findings.json` on the decision list, because the whole claim of this arm
# is that the verdict is DERIVED from a list — a reader who cannot see the list before and
# after recourse is being asked to take the derivation on trust.
CONTEST_FILES = ("transcript.md", "transcript_full.md", "challenge.json", "challenge.md",
                 "agreement.json", "ruling.json", "ruling_agreement.json",
                 "findings.after.json", "grade.json", "comprehension.json", "run.json")
DECISION_FILES = ("transcript.md", "transcript_full.md", "verdict.json", "findings.json",
                  "run.json")
ARM_TREES = {"weak": "fd1-weak", "strong": "fd1-strong"}


def configure(*, out: Path, records: Path, weak: str, strong: str) -> None:
    """Point the module at a tree. Called once by `main`, and by the tests.

    The four names below are module globals rather than an argument threaded through six
    functions because that is what `jd6-collect-records.py` does and a reader who knows
    that file should not have to learn a new shape to read this one. `configure` is the
    one place they move.
    """
    global OUT, RECORDS, ARMS, ARM_TREES
    OUT, RECORDS = Path(out), Path(records)
    ARMS = {"arm-weak": weak, "arm-strong": strong}
    ARM_TREES = {"weak": weak, "strong": strong}


def copy(src: Path, dst: Path) -> bool:
    if not Path(src).is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def collect_arms() -> None:
    for name, tree in ARMS.items():
        root = OUT / "experiments" / tree
        got = [f for f in SUMMARY if copy(root / f, RECORDS / name / f)]
        print(f"{name:<14} <- {tree}: {', '.join(got) or 'NOTHING FOUND'}")


def collect_scans() -> None:
    """The two format scans and the attempts table the derivation writes with --write-scans.

    They are the only tree-derived inputs `findings-1.py` has, and without them its format
    repairs and its validity-by-kind table print NOT IN THE INDEX. Reported as missing
    rather than regenerated here: regenerating them needs the run tree, and this script's
    contract is that it only copies.
    """
    for rel in ("arm-weak/format-scan.jsonl", "arm-strong/format-scan.jsonl",
                "attempts.json"):
        src = RECORDS / rel
        if src.is_file():
            print(f"scan           {rel}: present")
        else:
            print(f"scan           {rel}: MISSING — run findings-1.py with "
                  f"--scan-weak-tree/--scan-strong-tree --write-scans {RECORDS}")


def collect_logs() -> None:
    logs = RECORDS / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    named = {
        "run-all.log": OUT / "fd1-run-all.log",
        "fingerprints.md": OUT / "fd1-fingerprints.md",
        "all-done.md": OUT / "fd1-ALL-DONE.md",
        "provider-check.log": OUT / "fd1-provider-check.log",
        "smoke-1-read.md": OUT / "fd1-smoke-1-read.md",
        "smoke-2-read.md": OUT / "fd1-smoke-2-read.md",
        "smoke-1-cost.txt": OUT / "fd1-smoke-cost.txt",
        "smoke-2-cost.txt": OUT / "fd1-smoke-2-cost.txt",
        "pilot-cost.txt": OUT / "fd1-pilot-cost.txt",
        "injection-report.md": OUT / "fd1-inject" / "report.md",
        "handcheck-pick.md": OUT / "fd1-handcheck-pick.md",
        "DESIGN-paragraph.md": OUT / "fd1-DESIGN-paragraph.md",
    }
    for dst, src in named.items():
        print(f"logs/{dst:<24}{'copied' if copy(src, logs / dst) else 'MISSING'}")
    copy(OUT / "fd1-derivation.log", RECORDS / "derivation.log")
    print(f"derivation.log              "
          f"{'copied' if (RECORDS / 'derivation.log').is_file() else 'MISSING'}")

    # THE DRY-RUN TABLES, which are what the user confirmed before anything was sent
    # (HANDOFF §2.4). They are small and there is one per spec, so they come across whole
    # rather than as a tail: "the run the user approved" and "the run that happened" have
    # to be comparable line for line.
    dryruns = sorted(OUT.glob("fd1-*-dryrun.log"))
    for path in dryruns:
        copy(path, logs / "dryruns" / path.name)
    print(f"logs/dryruns/{'':<16}{len(dryruns)} dry-run tables copied")

    # The last 60 lines of each stage log, which is where the per-stage summary line sits.
    # The full logs live under the git-ignored `outputs/` and are not carried across; what
    # a reader needs from them is the counts, and they are here.
    tails = ["# findings-1 — stage tails",
             "",
             "The last lines of every stage and driver log. The full logs are under the",
             "git-ignored `outputs/` and are not carried across; what a reader needs from",
             "them is each stage's own summary line, and it is here.",
             ""]
    seen: set[str] = set()
    for log in sorted(OUT.glob("fd1-*.log")):
        if log.name in {"fd1-run-all.log", "fd1-provider-check.log"} or log in dryruns:
            continue
        if log.name in seen:
            continue
        seen.add(log.name)
        tails += [f"## `{log.name}`", "", "```",
                  *log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:],
                  "```", ""]
    (logs / "stage-tails.md").write_text("\n".join(tails) + "\n", encoding="utf-8")
    print(f"logs/stage-tails.md         {len(seen)} logs, {len(tails)} lines")


def wanted_cells(pick: Path) -> list[tuple[str, str, str]]:
    """`(group, arm, cell_id)` for every cell named in the hand-check pick file.

    The pick file's format is `## (x) ...` headings and ``- **`cell_id`** [arm]`` lines,
    which is what `fd1-handcheck-pick.py` writes. Group (e) is written as two sub-blocks
    `(e1)` and `(e2)` — the two blind spots of PREREG §7's phantom instrument — and both
    land under `e` here, because the transcripts a reader needs are the same either way.
    """
    group = None
    out: list[tuple[str, str, str]] = []
    for line in Path(pick).read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## \(([a-e])[0-9]?\)", line)
        if heading:
            group = heading.group(1)
            continue
        cell = re.match(r"^- \*\*`([^`]+)`\*\*\s*(?:\[(weak|strong|both)\])?", line)
        if cell and group:
            arm = cell.group(2) or "weak"
            for one in (("weak", "strong") if arm == "both" else (arm,)):
                out.append((group, one, cell.group(1)))
    return out


def collect_transcripts() -> None:
    pick = OUT / "fd1-handcheck-pick.md"
    if not pick.is_file():
        print("transcripts                 SKIPPED — no outputs/fd1-handcheck-pick.md yet")
        return
    seen: set[tuple[str, str, str]] = set()
    for group, arm, cell in wanted_cells(pick):
        if (group, arm, cell) in seen:
            continue
        seen.add((group, arm, cell))
        tree = OUT / "experiments" / ARM_TREES[arm]
        prefix = f"{group}__{arm}__{cell}"
        got = 0
        # THE DECISION RUN, always. This campaign's decision document is the one that
        # carries the findings list, so a hand check that saw only the contest would be
        # reading the objection without the thing it objects to.
        decisions = sorted((tree / "cells" / cell / "runs").glob("*"))
        if decisions:
            for name in DECISION_FILES:
                if copy(decisions[-1] / name,
                        RECORDS / "transcripts" / f"{prefix}__decision__{name}"):
                    got += 1
        contests = sorted((tree / "cells" / cell / "contests").glob("*/runs/*"))
        if contests:
            for name in CONTEST_FILES:
                if copy(contests[-1] / name,
                        RECORDS / "transcripts" / f"{prefix}__contest__{name}"):
                    got += 1
        if not decisions and not contests:
            print(f"transcripts  ({group}) {arm} {cell}: NO RUN DIRECTORY")
            continue
        print(f"transcripts  ({group}) {arm} {cell}: {got} files")
    print(f"transcripts                 {len(seen)} (group, arm, cell) triples")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT,
                        help=f"the outputs directory to read (default: {OUT})")
    parser.add_argument("--records", type=Path, default=RECORDS,
                        help=f"the records directory to write (default: {RECORDS})")
    parser.add_argument("--weak-tree", default=ARMS["arm-weak"],
                        help="the F-weak run tree's name under outputs/experiments "
                             f"(default: {ARMS['arm-weak']})")
    parser.add_argument("--strong-tree", default=ARMS["arm-strong"],
                        help="the F-strong run tree's name under outputs/experiments "
                             f"(default: {ARMS['arm-strong']})")
    parser.add_argument("--create", action="store_true",
                        help="create the records directory if it does not exist "
                             "(off by default: a typo in --records must not silently "
                             "make a new tree beside the real one)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    configure(out=args.out, records=args.records,
              weak=args.weak_tree, strong=args.strong_tree)
    if not RECORDS.is_dir():
        if not args.create:
            print(f"! {RECORDS} does not exist (pass --create to make it)")
            return 1
        RECORDS.mkdir(parents=True)
    print(f"records dir: {RECORDS}")
    print()
    collect_arms()
    collect_scans()
    collect_logs()
    collect_transcripts()
    print()
    total = sum(p.stat().st_size for p in RECORDS.rglob("*") if p.is_file())
    n = sum(1 for p in RECORDS.rglob("*") if p.is_file())
    try:
        where = RECORDS.relative_to(REPO)
    except ValueError:          # --records pointed outside the repo, which is a dry run
        where = RECORDS
    print(f"{n} files, {total / 1e6:.1f} MB under {where}")
    print()
    print("PREREG.md and run-all.sh were committed before the first paid call and are NOT")
    print("touched by this script. README.md, CHECKLIST.md and HANDCHECK.md are written by")
    print("hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
