"""Copy the summary artifacts of `judgment-debate-6` into its records directory.

    cd exp2
    uv run python records/derivations/jd6-collect-records.py 2>&1 | tee outputs/jd6-collect.log

`outputs/` is git-ignored, so this is what carries the evidence into git: the SUMMARY
artifacts only, so that every number in `LLM_NOTES.md` §3ab can be checked against a file
rather than taken on trust. It reads `outputs/experiments/jd6-{round,plain}/` and the run's
logs, and writes only under `records/experiments/judgment-debate-6/`. It follows
`judgment-debate-5`'s layout exactly, so a reader who knows that directory knows this one.

It copies rather than summarises, and it never touches `PREREG.md` or `run-all.sh`, which
were committed before the first paid call and must not move afterwards.

`transcripts/` takes the cells named in `outputs/jd6-handcheck-pick.md`, each as
`<group>__<cell_id>__<file>` so the four groups stay legible in one flat listing — jd5's
convention. Both documents come across for every cell: `transcript.md`, the readable
record, and `transcript_full.md`, the same run verbatim with every prompt and reply.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "outputs"
RECORDS = REPO / "records" / "experiments" / "judgment-debate-6"
ARMS = {"arm-round": "jd6-round", "arm-plain": "jd6-plain"}
# What a reader needs to recompute a number, and nothing that would make this directory an
# input to a stage: no cells the run decided, no wire logs, no copied parents.
SUMMARY = ("index.jsonl", "metrics.json", "cells.jsonl", "experiment.json")
# The contest record's own files, for the hand-checked cells.
CONTEST_FILES = ("transcript.md", "transcript_full.md", "ruling.json",
                 "ruling.source.json", "ruling_agreement.json", "challenge.json",
                 "recourse_transcript.json", "grade.json", "run.json")
DECISION_FILES = ("transcript.md", "transcript_full.md", "verdict.json", "run.json")


def copy(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def collect_arms() -> None:
    for name, tree in ARMS.items():
        root = OUT / "experiments" / tree
        got = [f for f in SUMMARY if copy(root / f, RECORDS / name / f)]
        print(f"{name:<12} <- {tree}: {', '.join(got) or 'NOTHING FOUND'}")


def collect_scans() -> None:
    """The two language scans and the two json tables the derivation writes."""
    for rel in ("arm-round/round-language.jsonl", "arm-plain/round-language.jsonl",
                "provider-mix.json", "attempts.json"):
        src = RECORDS / rel
        print(f"scan         {rel}: {'present' if src.is_file() else 'MISSING — run the '
              'derivation with --write-scans ' + str(RECORDS)}")


def collect_logs() -> None:
    logs = RECORDS / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    named = {
        "run-all.log": OUT / "jd6-run-all.log",
        "fingerprints.md": OUT / "jd6-fingerprints.txt",
        "all-done.md": OUT / "jd6-ALL-DONE.md",
        "provider-check.log": OUT / "jd6-provider-check.log",
        "indices.md": OUT / "jd6-indices.md",
        "smoke-1-read.txt": OUT / "jd6-smoke-read.txt",
        "smoke-2-read.txt": OUT / "jd6-smoke-2-read.txt",
        "smoke-1-cost.txt": OUT / "jd6-smoke-cost.txt",
        "smoke-2-cost.txt": OUT / "jd6-smoke-2-cost.txt",
        "handcheck-pick.md": OUT / "jd6-handcheck-pick.md",
        "DESIGN-paragraph.md": OUT / "jd6-DESIGN-paragraph.md",
    }
    for dst, src in named.items():
        print(f"logs/{dst:<22}{'copied' if copy(src, logs / dst) else 'MISSING'}")
    copy(OUT / "jd6-derivation.log", RECORDS / "derivation.log")
    print(f"derivation.log            "
          f"{'copied' if (RECORDS / 'derivation.log').is_file() else 'MISSING'}")

    # The last 60 lines of each stage log, which is where the per-stage summary line is.
    tails = ["# judgment-debate-6 — stage tails",
             "",
             "The last lines of every stage log, which is where each stage's own summary",
             "sits. The full logs are under the git-ignored `outputs/` and are not carried",
             "across; what a reader needs from them is the counts, and they are here.",
             ""]
    for log in sorted(OUT.glob("jd6-jd6-*-*.log")) + sorted(OUT.glob("jd6-*-driver.log")):
        tails += [f"## `{log.name}`", "", "```",
                  *log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:],
                  "```", ""]
    (logs / "stage-tails.md").write_text("\n".join(tails) + "\n", encoding="utf-8")
    print(f"logs/stage-tails.md       {len(tails)} lines")


def collect_transcripts() -> None:
    """The hand-check cells, named `<group>__<cell_id>__<file>` as jd5 names them."""
    pick = OUT / "jd6-handcheck-pick.md"
    if not pick.is_file():
        print("transcripts               SKIPPED — no outputs/jd6-handcheck-pick.md yet")
        return
    group = None
    wanted: list[tuple[str, str, bool]] = []
    for line in pick.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## \(([a-d])\)", line)
        if heading:
            group = heading.group(1)
            continue
        cell = re.match(r"^- \*\*`([^`]+)`\*\*", line)
        if cell and group:
            wanted.append((group, cell.group(1), group == "d"))
    seen = set()
    for group, cell, plain in wanted:
        if (group, cell) in seen:
            continue
        seen.add((group, cell))
        if plain:
            runs = sorted((OUT / "experiments" / "jd6-plain" / "cells" / cell
                           / "runs").glob("*"))
            files = DECISION_FILES
        else:
            runs = sorted((OUT / "experiments" / "jd6-round" / "cells" / cell
                           / "contests").glob("*/runs/*"))
            files = CONTEST_FILES
        if not runs:
            print(f"transcripts  ({group}) {cell}: NO RUN DIRECTORY")
            continue
        directory = runs[-1]
        got = 0
        for name in files:
            if copy(directory / name,
                    RECORDS / "transcripts" / f"{group}__{cell}__{name}"):
                got += 1
        # BOTH ARMS WHERE BOTH EXIST. Groups (a)-(c) are contest cells, but the whole
        # reading of (a) and (b) is a comparison — "R broke it and B did not" — so the
        # plain arm's own document has to be beside it or the reader is taking half the
        # claim on trust. Named `__plain__transcript.md` so the pair is obvious in a flat
        # listing.
        if not plain:
            others = sorted((OUT / "experiments" / "jd6-plain" / "cells" / cell
                             / "runs").glob("*"))
            if others and copy(others[-1] / "transcript.md",
                               RECORDS / "transcripts"
                               / f"{group}__{cell}__plain__transcript.md"):
                got += 1
        print(f"transcripts  ({group}) {cell}: {got} files")
    print(f"transcripts               {len(seen)} cells")


def main() -> int:
    if not RECORDS.is_dir():
        print(f"! {RECORDS} does not exist")
        return 1
    print(f"records dir: {RECORDS}")
    print()
    collect_arms()
    collect_scans()
    collect_logs()
    collect_transcripts()
    print()
    total = sum(p.stat().st_size for p in RECORDS.rglob("*") if p.is_file())
    n = sum(1 for p in RECORDS.rglob("*") if p.is_file())
    print(f"{n} files, {total / 1e6:.1f} MB under {RECORDS.relative_to(REPO)}")
    print()
    print("PREREG.md and run-all.sh were committed before the first paid call and are NOT")
    print("touched by this script. README.md and CHECKLIST.md are written by hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
