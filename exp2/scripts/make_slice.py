#!/usr/bin/env python
"""Draw a stratified sweep slice from the seven finished corpus bundles.

    uv run python scripts/make_slice.py 2>&1 | tee outputs/make-slice-1.log

**Why this exists rather than `get_tasks.py --sample`.** That flag caps each subset to N
rows and then *rewrites the full bundle* `data/cases/ftf-<subset>.jsonl` with the sampled
rows — it is a re-conversion switch, not a sampler. Running it to build a slice would
destroy the 2,110-item corpus that every finished run's provenance describes. This script
never writes into `data/cases/ftf-*`; it opens them read-only and writes one new bundle.

The draw is **stratified by subset and clustered on `row_id`**: N rows per subset, and
every item of a drawn row travels with it, because a row's paired flawed/sound siblings
share a problem and `row_id` is the bootstrap's clustering unit (`types.Item`). Drawing
items instead would split pairs across the in-sample/out-of-sample boundary and make the
cluster structure a lie.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exp2.types import load_cases  # noqa: E402

SUBSET_KEYS = ["gpqa", "law", "lojban", "medqa", "python800", "surgery", "theoremqa"]


def group_by_row(cases):
    """Rows in the order the bundle lists them, each holding its items in file order."""
    by_row: collections.OrderedDict[str, list] = collections.OrderedDict()
    for case in cases:
        by_row.setdefault(case.item.row_id, []).append(case)
    return by_row


def draw(cases, *, rows: int, seed: int, subset: str):
    """Keep every item of `rows` rows drawn with `Random(f"{seed}:slice:{subset}")`.

    The returned cases stay in bundle order, not draw order, so the slice reads like a
    subsequence of the corpus and two runs of this function are byte-identical.
    """
    by_row = group_by_row(cases)
    row_ids = list(by_row)
    random.Random(f"{seed}:slice:{subset}").shuffle(row_ids)
    keep = set(row_ids[:rows])
    return [c for c in cases if c.item.row_id in keep]


def compose(subset: str, drawn) -> dict:
    flawed = sum(1 for c in drawn if c.item.gold_flawed)
    return {
        "subset": subset,
        "rows": len({c.item.row_id for c in drawn}),
        "items": len(drawn),
        "flawed": flawed,
        "sound": len(drawn) - flawed,
        "gradable_flawed": sum(1 for c in drawn if c.gradable),
        "label_bases": collections.Counter(c.item.label_basis for c in drawn),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--subsets", default=",".join(SUBSET_KEYS),
                   help="comma-separated; default all seven")
    p.add_argument("--rows", type=int, default=25,
                   help="rows drawn per subset (not items: a paired row brings 2)")
    p.add_argument("--seed", type=int, default=1,
                   help="seeds the per-subset draw as f'{seed}:slice:{subset}'")
    p.add_argument("--out", type=Path, default=None,
                   help="default <data-root>/cases/sweep-1.jsonl")
    p.add_argument("--compare", type=Path, default=None,
                   help="an existing bundle to report item-id overlap against; "
                        "default <data-root>/cases/pilot-3.jsonl when it exists")
    args = p.parse_args(argv)

    keys = [k.strip() for k in args.subsets.split(",") if k.strip()]
    unknown = sorted(set(keys) - set(SUBSET_KEYS))
    if unknown:
        p.error(f"unknown subsets {unknown}; known: {SUBSET_KEYS}")

    out = args.out or (args.data_root / "cases" / "sweep-1.jsonl")
    slice_cases, composition = [], []
    for key in keys:
        bundle = args.data_root / "cases" / f"ftf-{key}.jsonl"
        if not bundle.is_file():
            p.error(f"missing corpus bundle {bundle}; run scripts/get_tasks.py first")
        cases = load_cases(bundle)  # read-only; this script never writes ftf-*.jsonl
        drawn = draw(cases, rows=args.rows, seed=args.seed, subset=key)
        total_rows = len(group_by_row(cases))
        row = compose(key, drawn)
        row["rows_available"] = total_rows
        row["items_available"] = len(cases)
        composition.append(row)
        slice_cases.extend(drawn)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(c.to_dict()) for c in slice_cases) + "\n",
        encoding="utf-8",
    )

    flawed = sum(1 for c in slice_cases if c.item.gold_flawed)
    rows_total = len({c.item.row_id for c in slice_cases})
    print(f"wrote {len(slice_cases)} cases to {out} "
          f"({flawed} flawed / {len(slice_cases) - flawed} sound) over "
          f"{rows_total} rows and {len(keys)} subsets")
    print(f"cells at three conditions x one repeat: {len(slice_cases) * 3}")

    print(f"\n{'subset':12s}{'rows':>6s}{'/avail':>8s}{'items':>7s}{'/avail':>8s}"
          f"{'flawed':>8s}{'sound':>7s}{'gradable':>10s}   label_basis")
    print("-" * 100)
    for r in composition:
        bases = ", ".join(f"{k} {v}" for k, v in sorted(r["label_bases"].items()))
        print(f"{r['subset']:12s}{r['rows']:6d}{r['rows_available']:8d}"
              f"{r['items']:7d}{r['items_available']:8d}{r['flawed']:8d}"
              f"{r['sound']:7d}{r['gradable_flawed']:10d}   {bases}")
    print("-" * 100)
    print(f"{'TOTAL':12s}{rows_total:6d}{'':8s}{len(slice_cases):7d}{'':8s}"
          f"{flawed:8d}{len(slice_cases) - flawed:7d}"
          f"{sum(1 for c in slice_cases if c.gradable):10d}")
    print("\nA subset draws fewer than --rows rows only if it has fewer rows than that.")

    compare = args.compare
    if compare is None:
        default = args.data_root / "cases" / "pilot-3.jsonl"
        compare = default if default.is_file() else None
    if compare is not None:
        other = {c.item.item_id for c in load_cases(compare)}
        mine = {c.item.item_id for c in slice_cases}
        shared = mine & other
        print(f"\noverlap with {compare}: {len(shared)} of {len(mine)} slice items "
              f"({len(other)} there). Every decision is made fresh, so an overlapping "
              f"item is not a re-use of a result; it is reported because the two runs' "
              f"cells are then not independent.")
        for item_id in sorted(shared):
            print(f"  {item_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
