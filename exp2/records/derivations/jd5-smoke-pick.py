"""Write the two three-cell cases files the `judgment-debate-5` prompt smoke runs on.

    cd exp2
    uv run python records/derivations/jd5-smoke-pick.py 2>&1 | tee outputs/jd5-smoke-pick.log

Read-only over `outputs/experiments/jd4-fabricated/index.jsonl`,
`outputs/experiments/jd3-main/index.jsonl` and `data/cases/ftf-all.jsonl`; writes exactly
two files, `data/cases/jd5-smoke-fabricated.jsonl` and `data/cases/jd5-smoke-real.jsonl`.
It touches nothing under `outputs/experiments/`.

WHY SIX CELLS AND WHY THESE SIX. The house rule (`HANDOFF.md` §2.8) is that a new or
changed prompt is read on about six chosen examples before any slice or paid arm. The
change is an existence check at the head of Step 1 of `RECOURSE_JUDGE_USER_JUDGMENT` —
find the sentence the objection puts under `Judgment says:` IN THE JUDGMENT before ruling
on whether the alleged defect is real — and there are exactly two ways it can be wrong:

  * it does not fire, and the fabricated objections keep their overturns; or
  * it fires too hard, and the REAL audit's genuine defects are refused over wording.

So three cells come from each side, and on both sides they are cells the judge
OVERTURNED, because an upheld cell cannot show a change: the old ruling already refused
the objection and a new refusal would say nothing about the check.

  * **fabricated** — `jd4-fabricated`, `changed_the_decision` and
    `challenge_fabrication_ok` (every judgment quotation invented, by the harness's own
    string comparison; the smoke read recomputes it rather than trusting the flag).
  * **real** — `jd3-main` M1, `changed_the_decision`, `grade_valid` (Haiku confirmed the
    alleged defect), and `challenge_defects_misattributed_n == 0` — the quotations really
    are in the judgment, which is precisely the case where the new check must not fire.

EXCLUDED: the nine cells Fable already read by hand in `outputs/jd4-handcheck.md`. Reading
the fix on the cells that produced the finding would confuse "the check works" with "the
check works here", which is the same rule `records/derivations/jd4-pick.py` applied to
smoke 2's draw.

ONE PER SUBSET on each side and a stated seed, so the six can be re-derived by re-running
this file, and so the reader is not shown three python800 judgments.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FABRICATED = REPO / "outputs" / "experiments" / "jd4-fabricated" / "index.jsonl"
REAL = REPO / "outputs" / "experiments" / "jd3-main" / "index.jsonl"
CORPUS = REPO / "data" / "cases" / "ftf-all.jsonl"
OUT_FABRICATED = REPO / "data" / "cases" / "jd5-smoke-fabricated.jsonl"
OUT_REAL = REPO / "data" / "cases" / "jd5-smoke-real.jsonl"

SEED = 5
SMOKE_N = 3

# The nine cells of `outputs/jd4-handcheck.md` — eight overturns and one upheld ruling
# read in full. The finding was made on these; the fix is not read on them.
HANDCHECKED = {
    "medqa-dev_0043", "python800-p03673", "python800-p03698", "python800-p03011",
    "python800-p02690", "python800-p03338", "python800-p03838", "gpqa-63",
    "python800-p03803",
}


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def item_stem(item_id: str) -> str:
    """`gpqa-63-flawed` -> `gpqa-63`, which is how the hand check names its cells."""
    for suffix in ("-flawed", "-sound"):
        if item_id.endswith(suffix):
            return item_id[: -len(suffix)]
    return item_id


def draw(pool: list[dict], label: str) -> list[dict]:
    """A seeded draw, one per subset, printed with the reason each cell qualifies."""
    shuffled = list(pool)
    random.Random(SEED).shuffle(shuffled)
    chosen: list[dict] = []
    seen: set[str] = set()
    for row in shuffled:
        if len(chosen) >= SMOKE_N:
            break
        if row["subset"] in seen:
            continue
        seen.add(row["subset"])
        chosen.append(row)
    chosen.sort(key=lambda r: (r["subset"] or "", r["cell_id"]))
    print(f"\n{label}: {len(pool)} eligible cells, subsets "
          f"{dict(Counter(r['subset'] for r in pool))}")
    return chosen


def write(path: Path, chosen: list[dict], by_id: dict[str, str], label: str) -> None:
    path.write_text("\n".join(by_id[row["item_id"]] for row in chosen) + "\n",
                    encoding="utf-8")
    print(f"wrote {len(chosen)} items -> {path}")
    print(f"  {label}")
    print(f"{'cell_id':<46}{'subset':>11}{'M0 right':>10}{'defects':>9}"
          f"{'valid':>7}{'misattr':>9}")
    print("-" * 92)
    for row in chosen:
        print(f"{row['cell_id']:<46}{row['subset']:>11}"
              f"{str(row['initially_correct']):>10}"
              f"{row.get('challenge_defects_n', 0):>9}"
              f"{str(row.get('grade_valid')):>7}"
              f"{str(row.get('challenge_defects_misattributed_n')):>9}")
    print("-" * 92)


def main() -> int:
    fabricated = rows(FABRICATED)
    real = rows(REAL)
    print(f"{FABRICATED}: {len(fabricated)} rows")
    print(f"{REAL}: {len(real)} rows")

    fab_pool = [
        r for r in fabricated
        if r.get("changed_the_decision")
        and r.get("challenge_fabrication_ok")
        and item_stem(r["item_id"]) not in HANDCHECKED
    ]
    real_pool = [
        r for r in real
        if r.get("changed_the_decision")
        and r.get("grade_valid")
        and r.get("challenge_defects_misattributed_n") == 0
        and item_stem(r["item_id"]) not in HANDCHECKED
    ]
    if len(fab_pool) < SMOKE_N or len(real_pool) < SMOKE_N:
        print(f"  ! not enough eligible cells: {len(fab_pool)} fabricated, "
              f"{len(real_pool)} real")
        return 1

    by_id: dict[str, str] = {}
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            by_id[json.loads(line)["item"]["item_id"]] = line

    fab_chosen = draw(fab_pool, "FABRICATED (jd4, overturned, every quotation invented)")
    real_chosen = draw(real_pool, "REAL (jd3-main M1, overturned, graded valid, "
                                 "0 misattributed quotations)")
    write(OUT_FABRICATED, fab_chosen, by_id,
          f"the check must FIRE here (random.Random({SEED}), one per subset)")
    write(OUT_REAL, real_chosen, by_id,
          f"the check must NOT fire here (random.Random({SEED}), one per subset)")

    overlap = ({r["item_id"] for r in fab_chosen}
               & {r["item_id"] for r in real_chosen})
    if overlap:
        # Not an error — the two arms stand on the same 896 cells, so an item can be
        # drawn on both sides — but the reader has to be told, because the same judgment
        # would then be read twice under two objections.
        print(f"\nNOTE: {len(overlap)} item(s) drawn on both sides: {sorted(overlap)}")
    print("\nEACH SMOKE MAKES ONE RECOURSE-JUDGE CALL PER CELL (three) and nothing else: "
          "the objections are copied from the source tree, no challenger is called, and "
          "`--stage rerule` refuses `contest`, `agreement` and `grade`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
