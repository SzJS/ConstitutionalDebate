#!/usr/bin/env python
"""Fetch FindTheFlaws and convert it to cases.

    uv run python scripts/get_tasks.py --subset all 2>&1 | tee outputs/get-tasks.log

Nothing upstream is vendored. The archive is fetched into a git-ignored cache and only
provenance — URL, pinned commit, sha256, byte count, canary — is recorded.

exp2 fetches its own copy; it does not read exp1's cache. That is not fussiness: the
two experiments convert the same archive into different shapes, and a shared cache is
the kind of coupling that makes one experiment's refresh silently alter the other's
corpus.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exp2.datasets import FTF, SUBSETS, convert_subset, provenance  # noqa: E402
from exp2.types import load_cases  # noqa: E402


def read_member(archive: bytes, *, member: str, password: str) -> str:
    """Decrypt one member. FindTheFlaws ships AES, which stdlib zipfile cannot read."""
    try:
        import pyzipper
    except ImportError:  # pragma: no cover - environment guard
        raise SystemExit(
            "pyzipper is required to read the FindTheFlaws archive.\n"
            "  uv sync --extra datasets"
        )
    import io

    with pyzipper.AESZipFile(io.BytesIO(archive)) as zf:
        zf.setpassword(password.encode("utf-8"))
        return zf.read(member).decode("utf-8")


def fetch_archive(data_root: Path, *, refresh: bool) -> bytes:
    """Download once and cache. The cache is keyed on the archive, not the subset, so
    converting all seven members costs one download."""
    cache = data_root / "findtheflaws" / FTF.filename
    if cache.is_file() and not refresh:
        print(f"using cached {cache}")
        return cache.read_bytes()
    print(f"fetching {FTF.url}")
    response = httpx.get(FTF.url, follow_redirects=True, timeout=120.0)
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(response.content)
    print(f"cached to {cache} ({len(response.content)} bytes)")
    return response.content


def write_subset(cases, subset_key: str, data_root: Path) -> Path:
    bundle = data_root / "cases" / f"ftf-{subset_key}.jsonl"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        "\n".join(json.dumps(c.to_dict()) for c in cases) + "\n", encoding="utf-8"
    )
    per_case = data_root / "cases" / f"ftf-{subset_key}"
    per_case.mkdir(parents=True, exist_ok=True)
    for case in cases:
        (per_case / f"{case.item.item_id}.json").write_text(
            json.dumps(case.to_dict(), indent=2), encoding="utf-8"
        )
    return bundle


def summarise(subset_key: str, cases) -> dict:
    sound = sum(1 for c in cases if not c.item.gold_flawed)
    flawed = len(cases) - sound
    gradable = sum(1 for c in cases if c.gradable)
    rows = len({c.item.row_id for c in cases})
    return {
        "subset": subset_key, "items": len(cases), "rows": rows,
        "sound": sound, "flawed": flawed, "gradable_flawed": gradable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", default="all",
                        choices=["all", *sorted(SUBSETS)])
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--sentences-per-argument", type=int, default=1,
                        help="CELS subsets only; 1 keeps items near-independent")
    parser.add_argument("--seed", type=int, default=0,
                        help="seeds the CELS sentence draw and --sample")
    parser.add_argument("--sample", type=int, default=None,
                        help="cap each subset to N rows, sampled on row_id so a row's "
                             "items travel together")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--pilot", type=int, default=None, metavar="N",
                        help="also write a pilot bundle (see --pilot-out) with N "
                             "flawed and "
                             "N sound items per subset, balanced so the pilot "
                             "exercises both error types everywhere, PLUS the two "
                             "longest items in each subset (see --pilot-longest)")
    parser.add_argument("--pilot-subsets", default=None,
                        help="comma-separated subsets to put in the pilot. Default: "
                             "every subset converted. This is how the pilot is "
                             "restricted to the subsets that survived the weak-model "
                             "screen, without re-converting a different corpus")
    parser.add_argument("--pilot-out", type=Path, default=None, metavar="PATH",
                        help="where to write the pilot bundle. Default: "
                             "<data-root>/cases/pilot.jsonl. Give a different path "
                             "when the draw changes: `experiments/pilot.toml` and "
                             "`pilot-2.toml` both point at pilot.jsonl and it has to "
                             "keep meaning the 42 items they were run on, or two "
                             "finished experiments start describing a corpus they "
                             "never saw")
    parser.add_argument("--pilot-longest", type=int, default=2, metavar="N",
                        help="items per subset added on top of the balanced draw, "
                             "chosen as the longest by len(problem)+len(solution). "
                             "These are the max_tokens stress test: truncation is fatal "
                             "by design and unretryable at the same cap, and a random "
                             "draw tests the median while the sweep ships the p95. 0 "
                             "disables")
    args = parser.parse_args(argv)

    keys = sorted(SUBSETS) if args.subset == "all" else [args.subset]
    archive = fetch_archive(args.data_root, refresh=args.refresh)

    summaries = []
    for key in keys:
        subset = SUBSETS[key]
        raw = read_member(archive, member=subset.member, password=FTF.zip_password)
        cases = convert_subset(
            key, raw,
            sentences_per_argument=args.sentences_per_argument, seed=args.seed,
        )
        if args.sample is not None:
            by_row = collections.OrderedDict()
            for case in cases:
                by_row.setdefault(case.item.row_id, []).append(case)
            row_ids = list(by_row)
            random.Random(f"{args.seed}:sample:{key}").shuffle(row_ids)
            keep = set(row_ids[: args.sample])
            cases = [c for c in cases if c.item.row_id in keep]

        bundle = write_subset(cases, key, args.data_root)
        record = provenance(subset, raw)
        prov = args.data_root / "cases" / f"ftf-{key}.provenance.json"
        prov.write_text(json.dumps(record, indent=2), encoding="utf-8")
        summaries.append(summarise(key, cases))
        print(f"wrote {len(cases):5d} cases to {bundle}  sha256={record['sha256'][:12]}")

    if args.pilot:
        pilot_keys = ([k.strip() for k in args.pilot_subsets.split(",") if k.strip()]
                      if args.pilot_subsets else list(keys))
        unknown = sorted(set(pilot_keys) - set(SUBSETS))
        if unknown:
            parser.error(f"unknown --pilot-subsets {unknown}; known: {sorted(SUBSETS)}")
        pilot, composition = [], []
        for key in pilot_keys:
            cases = load_cases(args.data_root / "cases" / f"ftf-{key}.jsonl")
            chosen: dict[str, object] = {}
            for flawed in (True, False):
                pool = [c for c in cases if c.item.gold_flawed is flawed]
                random.Random(f"{args.seed}:pilot:{key}:{flawed}").shuffle(pool)
                for case in pool[: args.pilot]:
                    chosen[case.item.item_id] = case
            seeded = len(chosen)
            # The two longest items are the max_tokens stress test. Ties broken on
            # item_id so the corpus is reproducible.
            longest = sorted(
                cases,
                key=lambda c: (-(len(c.item.problem) + len(c.item.solution)),
                               c.item.item_id),
            )[: args.pilot_longest]
            for case in longest:
                chosen.setdefault(case.item.item_id, case)
            pilot.extend(chosen.values())
            composition.append({
                "subset": key, "items": len(chosen), "seeded": seeded,
                "longest_added": len(chosen) - seeded,
                "longest": [(c.item.item_id,
                             len(c.item.problem) + len(c.item.solution))
                            for c in longest],
                "flawed": sum(1 for c in chosen.values() if c.item.gold_flawed),
            })
        bundle = args.pilot_out or (args.data_root / "cases" / "pilot.jsonl")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(
            "\n".join(json.dumps(c.to_dict()) for c in pilot) + "\n", encoding="utf-8")
        flawed_n = sum(1 for c in pilot if c.item.gold_flawed)
        print(f"\nwrote {len(pilot)} pilot cases to {bundle} "
              f"({flawed_n} flawed / {len(pilot) - flawed_n} sound) over "
              f"{len(pilot_keys)} subsets")
        print(f"\n{'subset':12s}{'items':>7s}{'flawed':>8s}{'seeded':>8s}"
              f"{'+longest':>10s}   longest items (chars: problem+solution)")
        print("-" * 100)
        for row in composition:
            longest = ", ".join(f"{i} ({n})" for i, n in row["longest"])
            print(f"{row['subset']:12s}{row['items']:7d}{row['flawed']:8d}"
                  f"{row['seeded']:8d}{row['longest_added']:10d}   {longest}")
        print("-" * 100)
        print(f"{'TOTAL':12s}{len(pilot):7d}{flawed_n:8d}")
        print("\nA subset shows fewer than the expected 2N+longest items when a longest "
              "item was\nalready in the balanced draw, or when the subset has fewer "
              "than N of one label.")

    print(f"\n{'subset':12s}{'rows':>7s}{'items':>8s}{'sound':>8s}{'flawed':>8s}"
          f"{'gradable':>10s}")
    print("-" * 53)
    for s in summaries:
        print(f"{s['subset']:12s}{s['rows']:7d}{s['items']:8d}{s['sound']:8d}"
              f"{s['flawed']:8d}{s['gradable_flawed']:10d}")
    total = {k: sum(s[k] for s in summaries)
             for k in ("rows", "items", "sound", "flawed", "gradable_flawed")}
    print("-" * 53)
    print(f"{'TOTAL':12s}{total['rows']:7d}{total['items']:8d}{total['sound']:8d}"
          f"{total['flawed']:8d}{total['gradable_flawed']:10d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
