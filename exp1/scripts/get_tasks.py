#!/usr/bin/env python
"""Fetch an upstream question source and convert it to task or case JSON.

    uv run python scripts/get_tasks.py --source habermas
    uv run python scripts/get_tasks.py --source neurips25 --limit 5
    uv run python scripts/get_tasks.py --source ftf-theoremqa

Raw files land in the git-ignored ``data/`` cache; converted tasks land in
``data/tasks/<source>/`` and converted cases in ``data/cases/<source>.jsonl``.
Nothing upstream is committed — see ``constitutional_debate.datasets`` for why.

FindTheFlaws is CC0, so vendoring would be permitted. It is still not vendored:
every row carries a benchmark canary string, which exists so the authors can
detect the data leaking into training corpora. Committing it to a public repo
is the leak it is there to detect.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import httpx

from constitutional_debate.datasets import (
    CASE_CONVERTERS,
    SOURCES,
    convert,
    convert_cases,
    provenance,
)


def read_member(archive: bytes, *, member: str, password: str) -> str:
    """Read one member out of an AES-encrypted zip.

    ``zipfile`` handles only ZipCrypto, and FindTheFlaws ships AES, so this
    needs ``pyzipper``. It is an extra rather than a runtime dependency: only
    this script fetches, and the decision path never touches an archive.
    """
    try:
        import pyzipper
    except ImportError:  # pragma: no cover - exercised by humans, not tests
        raise SystemExit(
            "this source ships an AES-encrypted zip, which needs pyzipper.\n"
            "  uv sync --extra datasets   (or: uv run --with pyzipper ...)"
        )
    with pyzipper.AESZipFile(io.BytesIO(archive)) as zf:
        zf.setpassword(password.encode("utf-8"))
        return zf.read(member).decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--limit", type=int, default=None, help="write only the first N items"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="re-download even if cached"
    )
    args = parser.parse_args(argv)

    source = SOURCES[args.source]
    raw_dir = args.data_root / source.key
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Two subsets share one archive, so the cache is keyed on the archive rather
    # than the source: fetching the second subset must not re-download it.
    cache_dir = args.data_root / ("findtheflaws" if source.zip_password else source.key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_path = cache_dir / source.filename

    if raw_path.is_file() and not args.refresh:
        blob = raw_path.read_bytes()
        print(f"using cached {raw_path}")
    else:
        print(f"fetching {source.url}")
        response = httpx.get(source.url, timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        blob = response.content
        raw_path.write_bytes(blob)

    if source.zip_password:
        raw = read_member(
            blob, member=source.member, password=source.zip_password
        )
    else:
        raw = blob.decode("utf-8")

    meta = provenance(source, raw)
    (raw_dir / "provenance.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    if source.key in CASE_CONVERTERS:
        cases = convert_cases(source.key, raw)
        if args.limit is not None:
            cases = cases[: args.limit]
        case_dir = args.data_root / "cases"
        case_dir.mkdir(parents=True, exist_ok=True)
        bundle = case_dir / f"{source.key}.jsonl"
        bundle.write_text(
            "".join(
                json.dumps(c.to_dict(), ensure_ascii=False) + "\n" for c in cases
            ),
            encoding="utf-8",
        )
        # Also one file per case, so a single case can be run by hand.
        per_case = case_dir / source.key
        per_case.mkdir(parents=True, exist_ok=True)
        for case in cases:
            (per_case / f"{case.task.task_id}.json").write_text(
                json.dumps(case.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        graded = sum(1 for c in cases if c.error and c.error.grades_characterisation)
        shaky = sum(
            1 for c in cases if c.error and not c.error.sound_seed_reliable
        )
        print(f"sha256 {meta['sha256']}")
        print(f"wrote {len(cases)} cases to {bundle} and {per_case}/")
        if graded == len(cases):
            print("  all carry an error explanation: the full funnel is measurable")
        else:
            print(
                f"  {graded}/{len(cases)} carry an error explanation; the rest "
                f"annotate location only and cannot support the valid-objection "
                f"metric"
            )
        if shaky:
            print(
                f"  {shaky} have a sound seed upstream annotators disagreed about "
                f"— kept, and stratified in the analysis"
            )
        return 0

    tasks = convert(source.key, raw)
    if args.limit is not None:
        tasks = tasks[: args.limit]

    task_dir = args.data_root / "tasks" / source.key
    task_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        (task_dir / f"{task.task_id}.json").write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(f"sha256 {meta['sha256']}")
    print(f"wrote {len(tasks)} tasks to {task_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
