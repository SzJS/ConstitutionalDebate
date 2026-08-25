"""The four hand-read paths for checklist row 10.

  * one genuine contest per condition -- genuine meaning the LINE says REVERSE and the
    PROSE reading agrees it contests, so it is not a phantom;
  * one `declined` on a decision that was wrong.

Prints the contest directory, which holds transcript.md (readable) and
transcript_full.md (verbatim), plus parent/ with the decision it contests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/experiments/pilot-3")
index = [json.loads(l) for l in (ROOT / "index.jsonl").open() if l.strip()]


def contest_dir(cell_id):
    runs = sorted((ROOT / "cells" / cell_id / "contests").glob("*/runs/*"), reverse=True)
    for d in runs:
        if (d / "challenge.json").is_file():
            return d
    return None


def show(label, row):
    d = contest_dir(row["cell_id"])
    print(f"\n{label}")
    print(f"  cell            {row['cell_id']}")
    print(f"  subset          {row['subset']}   gold_flawed={row['gold_flawed']}")
    print(f"  verdict         {row['verdict']}   initially_correct="
          f"{row['initially_correct']}")
    print(f"  stance          {row['challenge_stance']}   "
          f"claimed={row.get('challenge_claimed_verdict')}")
    print(f"  prose           {row.get('prose_stance')}   "
          f"agree={row.get('line_prose_agree')}  phantom={row.get('phantom_contest')}")
    print(f"  changed         {row.get('changed_the_decision')}   "
          f"final_correct={row.get('final_correct')}")
    print(f"  comprehension   {row.get('comprehension')}")
    print(f"  PATH            {d}/transcript.md")
    print(f"  verbatim        {d}/transcript_full.md")


for cond in ("single", "self_critique", "debate"):
    genuine = [r for r in index
               if r["condition"] == cond
               and r.get("challenge_stance") == "contests"
               and r.get("line_prose_agree") is True]
    # Prefer one that contested an actually-wrong decision; else any genuine contest.
    wrong = [r for r in genuine if r.get("initially_correct") is False]
    pick = (wrong or genuine)
    if pick:
        show(f"GENUINE CONTEST — {cond}"
             + ("  (on a decision that was wrong)" if wrong else "  (on a correct decision)"),
             sorted(pick, key=lambda r: r["cell_id"])[0])
    else:
        print(f"\nGENUINE CONTEST — {cond}: NONE (line and prose never both contested)")

declined_wrong = [r for r in index
                  if r.get("challenge_stance") == "declined"
                  and r.get("initially_correct") is False]
if declined_wrong:
    show("DECLINED ON A WRONG DECISION",
         sorted(declined_wrong, key=lambda r: r["cell_id"])[0])
else:
    print("\nDECLINED ON A WRONG DECISION: none")
