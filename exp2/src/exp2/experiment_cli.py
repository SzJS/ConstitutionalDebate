"""``exp2-experiment`` — run a stage of the grid.

    uv run exp2-experiment --spec experiments/pilot.toml --stage decide \\
        2>&1 | tee outputs/pilot-decide.log

``--dry-run`` prints the grid, the call estimate, and **every effective hyperparameter
with the reason it is what it is**. The repo's practice rule says that table has to be
shown and confirmed before a run; building it into the tool means it cannot drift from
the values actually used, and nobody has to retype it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .accounting import aggregate_tree
from .analysis import analyse
from .arms import CONDITIONS
from .config import WHY, DebateConfig, load_config, load_grading_config
from .experiment import (
    STAGES,
    build_grid,
    build_index,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
)
from .types import load_cases

# The name is OPENROUTER_KEY, not OPENROUTER_API_KEY. exp1 carries an error message
# warning about exactly this, and the port made the mistake anyway.
API_KEY_ENV = "OPENROUTER_KEY"
log = logging.getLogger(__name__)


def read_api_key() -> str:
    load_dotenv()
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise SystemExit(
            f"{API_KEY_ENV} is not set. It lives in the repo root's .env, which "
            "load_dotenv() finds by walking up from here. Note the name is "
            f"{API_KEY_ENV}, not OPENROUTER_API_KEY."
        )
    return key


def calls_per_cell(condition: str, config: DebateConfig) -> int:
    """Decision calls only; the contest adds a fixed 2 or 3 on top."""
    if condition == "single":
        return 1
    if condition == "self_critique":
        return 1 + 2 * config.n_critique_rounds
    return 2 * config.n_rounds + 1


def print_hyperparameters(config: DebateConfig) -> None:
    print("\nHyperparameters — every value, and why it is what it is")
    print("=" * 100)
    for field in fields(DebateConfig):
        value = getattr(config, field.name)
        print(f"  {field.name:28s} {str(value):26s} {WHY.get(field.name, '')}")
    print("=" * 100)


def print_estimate(grid, config: DebateConfig) -> None:
    by_condition: dict[str, int] = {}
    for cell in grid:
        by_condition[cell.condition] = by_condition.get(cell.condition, 0) + 1
    decision = sum(n * calls_per_cell(c, config) for c, n in by_condition.items())
    # challenge + comprehension always; ruling only when an objection is raised, and
    # grading only on flawed items whose subset records what the flaw was.
    contest = 2 * len(grid)
    ruling = len(grid)
    gradable = sum(1 for cell in grid if cell.case.gradable)
    print(f"\ncells: {len(grid)}  " +
          "  ".join(f"{c}={n}" for c, n in sorted(by_condition.items())))
    print(f"estimated calls: decision {decision}, contest {contest}, "
          f"ruling <= {ruling}, grading <= {gradable}  "
          f"=> up to {decision + contest + ruling + gradable}")
    print(f"retries are on top: max_decision_attempts={config.max_decision_attempts}, "
          "plus at most one format repair per generation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--stage", default="decide", choices=STAGES)
    parser.add_argument("--outputs", type=Path, default=Path("outputs/experiments"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    spec = tomllib.loads(args.spec.read_text(encoding="utf-8"))
    name = spec.get("name") or args.spec.stem
    conditions = spec.get("conditions", list(CONDITIONS))
    repeats = int(spec.get("repeats", 1))
    config, client_config = load_config(args.spec)
    grading = load_grading_config(args.spec)

    cases = load_cases(Path(spec["cases"]))
    if args.limit:
        cases = cases[: args.limit]
    grid = build_grid(cases, conditions, repeats)

    root = args.outputs / name
    root.mkdir(parents=True, exist_ok=True)

    print(f"experiment: {name}   stage: {args.stage}   outputs: {root}")
    print_estimate(grid, config)
    print_hyperparameters(config)
    print(f"\n  {'grader_model':28s} {grading.grader_model:26s} "
          "off-path; batch latency costs nothing on a finished directory")
    print(f"  {'max_concurrency':28s} {str(client_config.max_concurrency):26s} "
          "requests in flight across the whole fleet")

    if args.dry_run:
        print("\ndry run — nothing was sent. Re-run without --dry-run to spend.")
        return 0

    (root / "experiment.json").write_text(json.dumps({
        "name": name, "conditions": conditions, "repeats": repeats,
        "cases": spec["cases"], "cells": len(grid),
        "config": config.to_dict(), "client_config": client_config.to_dict(),
        "grading": grading.to_dict(),
    }, indent=2), encoding="utf-8")

    if args.stage == "analyse":
        rows = build_index(grid, root=root, challenger_model=config.challenger_model_for())
        index = root / "index.jsonl"
        index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        metrics = analyse(index, conditions)
        (root / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"\nindexed {len(rows)} rows -> {index}")
        for caveat in metrics["caveats"]:
            print(f"\n  ! {caveat}")
        if metrics["small_cells"]:
            print(f"\n  ! small cells: {', '.join(metrics['small_cells'])}")
        print(f"\nwrote {root / 'metrics.json'}")
        return 0

    api_key = read_api_key()
    runner = {
        "decide": lambda: run_stage_decide(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key),
        "contest": lambda: run_stage_contest(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key),
        "grade": lambda: run_stage_grade(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key=api_key),
    }[args.stage]

    results = asyncio.run(runner())
    counts: dict[str, int] = {}
    for result in results:
        key = ("error" if isinstance(result, BaseException)
               else result.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    print(f"\n{args.stage}: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for result in results:
        if isinstance(result, BaseException):
            print(f"  ! {type(result).__name__}: {result}")
        elif result.get("status") == "failed":
            print(f"  ! {result['cell_id']}: {result.get('error')}")

    spend = aggregate_tree(root)
    print(f"spend so far: ${spend['cost_usd']:.4f} over {spend['runs']} run directories")
    with (root / "cells.jsonl").open("a", encoding="utf-8") as fh:
        for result in results:
            if not isinstance(result, BaseException):
                fh.write(json.dumps({"stage": args.stage, **result}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
