"""``constitutional-experiment`` — run a grid of cells from a spec file.

    uv run constitutional-experiment --spec experiments/pilot.toml --dry-run
    uv run constitutional-experiment --spec experiments/pilot.toml --stage decide

The spec is TOML carrying the grid plus embedded ``[debate]`` / ``[client]``
tables, which are passed straight through to ``load_config``. Everything a run
needs is therefore in one file that is itself part of the record.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from .accounting import aggregate_tree
from .cli import configure_logging, read_api_key
from .config import ConfigError, load_config
from .config import load_grading_config
from .experiment import (
    build_grid,
    build_index,
    run_stage_challenge,
    run_stage_decide,
    run_stage_grade,
    run_stage_validate,
    summarise,
)
from .persistence import _write_json, git_provenance, utc_now
from .prompts import PROFILES
from .types import load_cases

log = logging.getLogger(__name__)

# challenge and rule are separate stages, not one "contest": the headline
# detection result needs the challenge and not the ruling, so the expensive half
# is opt-in. See Dox/design_decisions.md §1.
STAGES = ("decide", "challenge", "rule", "grade", "validate", "analyse")


def load_spec(path: Path) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="constitutional-experiment",
        description="Run a grid of decision cells and record them.",
    )
    parser.add_argument("--spec", type=Path, required=True, help="experiment TOML")
    parser.add_argument(
        "--config", type=Path, default=None,
        help="TOML supplying the [grading] table; defaults to configs/default.toml",
    )
    parser.add_argument("--stage", choices=STAGES, default="decide")
    parser.add_argument("--outputs", type=Path, default=Path("outputs/experiments"))
    parser.add_argument(
        "--limit", type=int, default=None, help="use only the first N cases"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the grid and what it would cost, and spend nothing",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def calls_per_cell(arm: str, config) -> int:
    """The worst-case call count for one cell of this arm.

    Arm-aware because outcome control changes it drastically: a constructed
    ``single`` cell makes no calls at all, and an arm-blind estimate would quote
    a budget for a grid that spends nothing.
    """
    if config.outcome_control:
        if arm == "single":
            return 0
        if arm == "self_critique":
            # inject, then per critique attempt: the critique, its two
            # gradings, and (when steered) one containment check. Worst case is
            # the unsteered attempt plus two steered ones.
            return 1 + (1 + 2) + 2 * (1 + 2 + 1)
        # Round 1 is inserted, so debaters run for n_rounds - 1 rounds. The
        # judge runs once unsteered, then up to twice steered, each steered
        # judgment paying one containment check.
        return 2 * max(config.n_rounds - 1, 0) + 1 + 2 * 2
    if arm == "single":
        return 1
    if arm == "self_critique":
        return 1 + 2 * max(config.n_critique_rounds, 1)
    # 2 debaters x n_rounds + 1 judge.
    return 2 * config.n_rounds + 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    try:
        spec = load_spec(args.spec)
        name = spec.get("name") or args.spec.stem
        config, client_config = load_config(
            overrides={k: v for k, v in (spec.get("debate") or {}).items()}
        )
        cases = load_cases(Path(spec["cases"]))
        if args.limit is not None:
            cases = cases[: args.limit]
        grid = build_grid(
            cases,
            arms=spec.get("arms", ["debate"]),
            conditions=spec.get("conditions", ["matched"]),
            repeats=int(spec.get("repeats", 1)),
        )
    except (ConfigError, OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2

    root = args.outputs / name
    root.mkdir(parents=True, exist_ok=True)
    configure_logging(root, args.verbose)
    print(root)

    # Every effective hyperparameter, not just the spec's overrides: a reader
    # should never have to open a cell's config.json to know what was run, nor
    # infer a value from a default that may since have changed.
    _write_json(
        root / "experiment.json",
        {
            "name": name,
            "started_utc": utc_now(),
            "spec_path": str(args.spec),
            "spec": spec,
            "cases": spec["cases"],
            "n_cases": len(cases),
            "n_cells": len(grid),
            "arms": spec.get("arms", ["debate"]),
            "conditions": spec.get("conditions", ["matched"]),
            "repeats": int(spec.get("repeats", 1)),
            "debate_config": config.to_dict(),
            "client_config": client_config.to_dict(),
            **git_provenance(),
        },
    )

    log.info(
        "%s: %d cases x %s x %s = %d cells | debater=%s judge=%s word_limit=%d "
        "attempts=%d",
        name, len(cases), spec.get("arms", ["debate"]),
        spec.get("conditions", ["matched"]), len(grid),
        config.debater_model, config.judge_model, config.word_limit,
        config.max_decision_attempts,
    )

    if args.dry_run:
        for cell in grid[:20]:
            print(f"  {cell.cell_id}")
        if len(grid) > 20:
            print(f"  ... and {len(grid) - 20} more")
        total = sum(calls_per_cell(cell.arm, config) for cell in grid)
        by_arm = {}
        for cell in grid:
            by_arm.setdefault(cell.arm, calls_per_cell(cell.arm, config))
        detail = ", ".join(f"{arm}: {n}" for arm, n in sorted(by_arm.items()))
        print(
            f"\n{len(grid)} cells ({detail} calls each) "
            f"= {total} calls; up to "
            f"{total * config.max_decision_attempts} with retries"
        )
        print("dry run: nothing was spent")
        return 0

    try:
        api_key = read_api_key()
    except KeyError as error:
        print(str(error), file=sys.stderr)
        return 2

    ledger_path = root / "cells.jsonl"

    def ledger(row: dict) -> None:
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.stage == "analyse":
        from .analysis import analyse

        index = [*build_index(root)]
        index_path = root / "index.jsonl"
        index_path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in index),
            encoding="utf-8",
        )
        metrics = analyse(index_path)
        _write_json(root / "metrics.json", metrics)
        print(f"wrote {index_path} ({len(index)} rows) and metrics.json")
        # Before the rates, because it is the caveat on their denominator: the
        # funnel is computed over the tasks that came out wrong in *every* arm.
        matching = metrics.get("matching", {})
        if matching.get("checked"):
            print(
                f"  matched {matching['tasks_matched']}/{matching['tasks_total']} "
                f"tasks across {', '.join(matching['arms'])}"
            )
            for arm, causes in sorted(matching["dropped"].items()):
                if causes["never_decided"]:
                    print(f"    {arm:<16}{causes['never_decided']:>4} never decided"
                          f"      (construction refused — regenerate)")
                if causes["decided_correctly"]:
                    print(f"    {arm:<16}{causes['decided_correctly']:>4} decided "
                          f"correctly  (the arm resisted — a finding)")
            if matching.get("unmatchable_rows"):
                print(f"    {matching['unmatchable_rows']} rows had no readable "
                      f"parent manifest and could not be matched")
        elif matching:
            print(f"  arms not intersected: {matching.get('reason')}")
        for label, entry in metrics["funnel"].items():
            rates = entry.get("rates", {})
            detection = rates.get("detection", {})
            if detection.get("n"):
                print(f"  {label:<24} detection {detection['k']}/{detection['n']} "
                      f"= {detection['rate']:.0%} "
                      f"[{detection['ci_low']:.0%}, {detection['ci_high']:.0%}]")
        return 0

    if args.stage in ("challenge", "rule"):
        rows = asyncio.run(
            run_stage_challenge(
                grid,
                challenger_models=spec.get("challenger_models", ["qwen/qwen3-8b"]),
                challenge_arms=spec.get("challenge_arms", ["neutral"]),
                config=config, client_config=client_config, api_key=api_key,
                root=root, rule=args.stage == "rule", ledger=ledger,
            )
        )
        done = sum(1 for r in rows if r["status"] == "completed")
        raised = sum(1 for r in rows if r.get("raised"))
        print(f"\n{args.stage}: {done}/{len(rows)} completed, {raised} raised a challenge")
        return 0 if done else 1

    if args.stage == "validate":
        rows = asyncio.run(
            run_stage_validate(
                config=config, grading=load_grading_config(args.config),
                client_config=client_config, api_key=api_key, root=root,
                ledger=ledger,
            )
        )
        done = [r for r in rows if r["status"] == "completed"]
        unusable = [r for r in done if r.get("usable") is False]
        print(f"\nvalidated {len(done)}/{len(rows)}; {len(unusable)} unusable")
        if unusable:
            print("  excluded from the headline funnel, and reported as excluded:")
            for row in unusable[:10]:
                print(f"    {row['case_id']}: {row.get('note', '')[:70]}")
        return 0

    if args.stage == "grade":
        rows = asyncio.run(
            run_stage_grade(
                config=config, grading=load_grading_config(args.config),
                client_config=client_config, api_key=api_key, root=root,
                ledger=ledger,
            )
        )
        done = [r for r in rows if r["status"] == "completed"]
        print(f"\ngraded {len(done)}/{len(rows)}; "
              f"{sum(1 for r in done if r.get('valid'))} valid objections")
        return 0

    try:
        outcomes = asyncio.run(
            run_stage_decide(
                grid,
                config=config,
                client_config=client_config,
                api_key=api_key,
                root=root,
                ledger=ledger,
                profile=PROFILES[spec.get("profile", "paper")],
            )
        )
    except KeyboardInterrupt:
        print("interrupted; completed cells are on disk and will be skipped on resume",
              file=sys.stderr)
        return 130

    stats = summarise(outcomes)
    stats["spend"] = aggregate_tree(root)
    _write_json(root / "decide_summary.json", stats)

    print()
    print(f"decided {stats['decided']}/{stats['cells']}  "
          f"(failed {stats['failed']}, skipped {stats['skipped']})")
    print(f"  initially incorrect: {stats['initially_incorrect']}   "
          f"initially correct: {stats['initially_correct']}")
    if stats["needed_retry"]:
        print(f"  needed more than one attempt: {stats['needed_retry']}")
    if stats["failure_reasons"]:
        print(f"  failure reasons: {stats['failure_reasons']}")
    print(f"  spent ${stats['spend']['cost_usd']:.4f}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
