"""Pick the cells Fable reads by hand, and write the paths to each one's record.

    cd exp2
    uv run python records/derivations/jd6-handcheck-pick.py > outputs/jd6-handcheck-pick.md

Read-only over `outputs/experiments/jd6-round/` and `outputs/experiments/jd6-plain/`. It
writes nothing under `outputs/experiments/` and it does NOT score anything: the whole point
of a hand check is that a person reads the documents and writes the verdicts, so this file
chooses the cells and prints where they are, and stops.

WHY THESE FOUR GROUPS. The endpoint is P1 and P2 — does the argued round break fewer right
decisions than an un-steered one, and does it fix at least as many wrong ones — so the cells
worth a human's time are the ones where the two arms DISAGREE on a decision that was right,
in each direction, plus the cells where the campaign's own instrument says the judge may
have adopted one advocate, plus a sample of the baseline actually moving.

  (a) R BROKE a right decision that B did not      the failure the round is meant to reduce
  (b) R SAVED a right decision that B broke        the success the round is meant to produce
  (c) the adopt-one-reply instrument fired         the weak-judge-adopts-the-advocate risk
  (d) the plain arm moved a verdict                what an extra round does with no objection

Seeded, so the sample is re-derivable; sorted by cell_id inside each group so the order
carries no information about the outcome.
"""
from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUND = REPO / "outputs" / "experiments" / "jd6-round"
PLAIN = REPO / "outputs" / "experiments" / "jd6-plain"
SEED = 6
N = 5

_JD6 = Path(__file__).resolve().with_name("judgment-debate-6.py")
_spec = importlib.util.spec_from_file_location("judgment_debate_6", _JD6)
jd6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jd6)


def rows(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["cell_id"]] = row
    return out


def contest_dir(cell_id: str) -> str:
    hits = sorted(ROUND.glob(f"cells/{cell_id}/contests/*/runs/*/transcript.md"))
    return str(hits[-1].relative_to(REPO)) if hits else "(not found)"


def decision_dir(cell_id: str) -> str:
    hits = sorted(PLAIN.glob(f"cells/{cell_id}/runs/*/transcript.md"))
    return str(hits[-1].relative_to(REPO)) if hits else "(not found)"


def sample(pool: list[str]) -> list[str]:
    pool = sorted(pool)
    if len(pool) <= N:
        return pool
    return sorted(random.Random(SEED).sample(pool, N))


def block(title: str, why: str, cells: list[str], pool_n: int, plain: bool = False,
          note=lambda c: "") -> None:
    print()
    print(f"## {title}")
    print()
    print(why)
    print()
    print(f"{len(cells)} drawn from a pool of {pool_n}"
          + (f", `random.Random({SEED})`" if pool_n > N else " (the whole pool)") + ".")
    print()
    if not cells:
        print("*The pool is empty.* That is itself a reading, and it is reported as one.")
        return
    for cell in cells:
        print(f"- **`{cell}`**{note(cell)}")
        if plain:
            print(f"  - plain arm: `{decision_dir(cell)}`")
        else:
            print(f"  - contest round: `{contest_dir(cell)}`")
            print(f"  - plain arm:     `{decision_dir(cell)}`")


def main() -> int:
    r, b = rows(ROUND / "index.jsonl"), rows(PLAIN / "index.jsonl")
    print("# judgment-debate-6 — the cells to read by hand")
    print()
    print(__doc__.strip().split("\n\n", 1)[1].split("WHY THESE FOUR GROUPS")[0].strip())
    print()
    print("**Fable reads these and writes the verdicts.** This file chooses the cells and")
    print("prints their paths; it scores nothing. Every path is `transcript.md`, the")
    print("readable record; `transcript_full.md` beside it is the same run verbatim, every")
    print("prompt and every reply, and is where the private `Thinking:` sections are.")
    print()
    print(f"Indexes: arm R {len(r)} rows, arm B {len(b)} rows.")

    both = sorted(set(r) & set(b))
    broke_r, saved_r, moved_b = [], [], []
    for cell in both:
        before = jd6.before_of(r[cell], "R")
        if before is None:
            continue
        ar, ab = jd6.after_of(r[cell], "R"), jd6.after_of(b[cell], "B")
        if ar is None or ab is None:
            continue
        if before and not ar and ab:
            broke_r.append(cell)
        if before and ar and not ab:
            saved_r.append(cell)
    for cell in sorted(b):
        if jd6.overturned_of(b[cell], "B"):
            moved_b.append(cell)

    language = {row["cell_id"]: row for row in jd6.scan_round_tree(ROUND)}
    one_sided = [c for c, row in language.items() if row.get("one_sided")]

    block("(a) R BROKE a right decision that B did not",
          "M0 was right; the contest round's ruling left the cell wrong and the plain\n"
          "round's judgment left it right. **This is the failure P1 says the round should\n"
          "produce LESS of**, so every one of these is a case against the mechanism and the\n"
          "read should say whether the round or the judge is what went wrong.",
          sample(broke_r), len(broke_r))

    block("(b) R SAVED a right decision that B broke",
          "The converse: M0 was right, the plain round's fresh judgment lost it, and the\n"
          "argued round kept it. **This is the success P1 says the round should produce MORE\n"
          "of**; the read should say whether the ANTI reply is what kept it, or whether the\n"
          "judge would have upheld anyway.",
          sample(saved_r), len(saved_r))

    block("(c) the adopt-one-reply instrument fired",
          "The ruling's prose tracks ONE reply materially more closely than the other\n"
          "(distinctive 6-grams, one at least twice the other). **The instrument cannot tell\n"
          "adoption from agreement** — a judge that reached PRO's conclusion independently\n"
          "shares its vocabulary — which is exactly why these go to a person. The question\n"
          "is whether the ruling ANSWERS the other reply anywhere, or only recites one.",
          sample(one_sided), len(one_sided),
          note=lambda c: f" — tracks **{language[c].get('tracks')}**"
                         f" (pro {language[c].get('pro_overlap')},"
                         f" anti {language[c].get('anti_overlap')})")

    block("(d) the plain arm moved a verdict",
          "An ordinary extra round with NO objection anywhere, and the judge changed its\n"
          "mind about the same debate. The read should say whether round 4 added anything\n"
          "the judge could have been moved by, or whether this is the judge disagreeing with\n"
          "itself on a re-draw — which is the caveat PREREG.md attaches to every absolute\n"
          "rate in this arm, and which no arm here prices.",
          sample(moved_b), len(moved_b), plain=True)

    print()
    print("---")
    print()
    print("Groups (a) and (b) are the two halves of P1's discordant pairs, so their POOL")
    print("sizes are the numbers the primary test is computed from; the derivation's")
    print("section (1) prints them as `b` and `c`. The samples here are for reading, never")
    print("for counting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
