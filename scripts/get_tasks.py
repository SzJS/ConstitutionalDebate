#!/usr/bin/env python
"""Fetch an upstream question source and convert it to task JSON files.

    uv run python scripts/get_tasks.py --source habermas
    uv run python scripts/get_tasks.py --source neurips25 --limit 5

Raw files land in the git-ignored ``data/`` cache; converted tasks land in
``data/tasks/<source>/``. Nothing upstream is committed — see
``constitutional_debate.datasets`` for why.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from constitutional_debate.datasets import SOURCES, convert, provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--limit", type=int, default=None, help="write only the first N tasks"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="re-download even if cached"
    )
    args = parser.parse_args(argv)

    source = SOURCES[args.source]
    raw_dir = args.data_root / source.key
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source.filename

    if raw_path.is_file() and not args.refresh:
        raw = raw_path.read_text(encoding="utf-8")
        print(f"using cached {raw_path}")
    else:
        print(f"fetching {source.url}")
        response = httpx.get(source.url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        raw = response.text
        raw_path.write_text(raw, encoding="utf-8")

    meta = provenance(source, raw)
    (raw_dir / "provenance.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

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
