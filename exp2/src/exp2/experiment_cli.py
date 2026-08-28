"""``exp2-experiment`` — run a stage of the grid.

    uv run exp2-experiment --spec experiments/pilot.toml --stage decide \\
        2>&1 | tee outputs/pilot-decide.log

``--dry-run`` prints the grid, the call estimate, and **every effective hyperparameter
with the reason it is what it is**. The repo's practice rule says that table has to be
shown and confirmed before a run; building it into the tool means it cannot drift from
the values actually used, and nobody has to retype it.

A spec may set ``decisions_from = "<path>"``. The run then reads its decisions out of
that tree and writes its contests, agreements, grades and index into its own — which is
how a finished experiment's decisions get re-contested under a changed protocol without
regenerating them and without touching the tree that holds them. ``--stage decide``
refuses on such a spec: it has nothing to decide, and running it would build a second,
differently-decided grid under the new name.

A spec may additionally set ``contests_from = "<path>"``. The run then reads the
OBJECTIONS out of that tree too and makes only one thing of its own: the ruling. Each
source contest is copied here minus its ruling and re-ruled by the recourse judge, so
1,586 existing objections get a second ruling under the changed prompt without one of
them being rewritten. ``contest``, ``agreement`` and ``grade`` refuse on such a spec —
each would write a new objection, or a new grade of one, over the copy this tree holds —
and ``--stage rerule`` refuses without it.

One arm is exempt from that refusal and only one: ``challenger_variant = "placeholder"``,
the second-look control. It carries ``contests_from`` and runs ``contest``, but it
generates nothing — the stage writes one fixed, content-free objection with no model call
and reads the source only to place itself on exactly the cells the source arm contested,
which is the whole of what makes it a control. Nothing under the source is written.
``agreement`` and ``grade`` stay refused for it, and the stages themselves skip it with
an explicit reason, because there is nothing in a constant to read or to grade.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from .config import (
    CHALLENGER_VARIANTS,
    CLIENT_WHY,
    GRADING_WHY,
    JUDGMENT_VARIANT,
    PLACEHOLDER_VARIANT,
    SPECIOUS_VARIANT,
    WHY,
    ClientConfig,
    DebateConfig,
    GradingConfig,
    load_config,
    load_grading_config,
)
from .experiment import (
    STAGES,
    build_grid,
    build_index,
    run_stage_agreement,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
    run_stage_rerule,
    run_stage_ruling_agreement,
    source_contests,
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


def _print_table(title: str, config: Any, why: dict[str, str]) -> None:
    print(f"\n[{title}]")
    for field in fields(type(config)):
        value = getattr(config, field.name)
        print(f"  {field.name:28s} {str(value):26s} {why.get(field.name, '')}")


def print_hyperparameters(config: DebateConfig, client_config: ClientConfig,
                          grading: GradingConfig) -> None:
    """All three tables, every field, defaults included.

    The repo's practice rule is the *full* set of values with a reason each, and a
    dry-run that printed only the decision-relevant table left the concurrency and
    timeout levers — the ones a sweep dies on — to be read out of a toml by hand.
    """
    print("\nHyperparameters — every value, and why it is what it is")
    print("=" * 100)
    _print_table("debate", config, WHY)
    _print_table("client", client_config, CLIENT_WHY)
    _print_table("grading", grading, GRADING_WHY)
    print("=" * 100)


def print_estimate(grid, config: DebateConfig,
                   decisions_from: Path | None = None,
                   contests_from: Path | None = None,
                   n_source_contests: int | None = None) -> None:
    """The call estimate, which is the line a run is approved from.

    ``decisions_from`` makes the decision term ZERO rather than the cost of deciding the
    grid: a re-contest reads its decisions off another tree and calls no decider at all.
    Printing the ordinary figure there would quote 90 calls for a run that makes 36, and
    quote them at the moment the spend is being agreed to.

    ``contests_from`` does the same to the contest and grading terms, and replaces the
    ruling term with a COUNTED one. A re-rule makes no challenge, no comprehension probe
    and no grade — the objection and its grade are copied from the source — and it rules
    only the cells whose source objection actually contested, which is a number that can
    be read off the source tree rather than bounded by the grid. On the sweep the two
    differ by a factor of five, and quoting the bound would be quoting five times the
    spend at the moment it is being agreed to.

    The PLACEHOLDER arm is the one spec that carries ``contests_from`` and still runs
    ``contest``, and its estimate is the same shape for a different reason: the contest
    term is zero because the objection is a constant this module writes rather than a
    generation, and the ruling term is the source's contested count because that is
    exactly where the placeholder is placed. Its whole spend is rulings plus the reading
    of them.
    """
    by_condition: dict[str, int] = {}
    for cell in grid:
        by_condition[cell.condition] = by_condition.get(cell.condition, 0) + 1
    decision = (0 if decisions_from is not None
                else sum(n * calls_per_cell(c, config) for c, n in by_condition.items()))
    # challenge + comprehension always; ruling only when an objection is raised, and
    # grading only on flawed items whose subset records what the flaw was.
    contest = 0 if contests_from is not None else 2 * len(grid)
    ruling = (n_source_contests if contests_from is not None else len(grid)) or 0
    # One short grader call per contest whose decision line parsed — the line-vs-prose
    # instrument. Bounded by the grid because every cell can produce at most one.
    agreement = 0 if contests_from is not None else len(grid)
    # One per ruling: the judge's line read against the judge's own prose.
    ruling_agreement = ruling
    # Under the judgment variant the grading term is the GRID, not the gradable subset:
    # that grader checks alleged defects against the record and opens no annotation, so
    # every contested cell is graded — sound items and correctly decided cells included.
    # Quoting the flaw grader's 87 for a run that makes up to 207 grader calls would
    # understate the spend at the moment it is being agreed to, which is the one thing
    # this line exists not to do.
    # The specious arm is graded by the SAME judgment grader, on every contested cell —
    # that grade is the manipulation check on the instruction and it is the whole reason
    # the arm is readable — so it takes the judgment grading term too. The placeholder is
    # not graded at all; `contests_from` already zeroes its term.
    judgment = config.challenger_variant in (JUDGMENT_VARIANT, SPECIOUS_VARIANT)
    placeholder = config.challenger_variant == PLACEHOLDER_VARIANT
    gradable = (0 if contests_from is not None
                else len(grid) if judgment
                else sum(1 for cell in grid if cell.case.gradable))
    print(f"\ncells: {len(grid)}  " +
          "  ".join(f"{c}={n}" for c, n in sorted(by_condition.items())))
    decision_term = (f"decision 0 (read from {decisions_from})"
                     if decisions_from is not None else f"decision {decision}")
    contest_term = (
        "contest 0 (the placeholder objection is a fixed text written with NO model "
        f"call, on the cells {contests_from} contested)" if placeholder
        else f"contest 0 (objections read from {contests_from})"
        if contests_from is not None else f"contest {contest}")
    print(f"estimated calls: {decision_term}, {contest_term}, "
          f"ruling <= {ruling}, agreement <= {agreement}, "
          f"ruling_agreement <= {ruling_agreement}, grading <= {gradable}  "
          f"=> up to {decision + contest + ruling + agreement + ruling_agreement + gradable}")
    if judgment:
        print("the grading term is the whole grid: `challenger_variant = \"judgment\"` "
              "grades every cell whose objection contests, against the RECORD rather "
              "than the recorded flaw — so the annotation gates that hold the ordinary "
              "grading term down do not apply.")
    if contests_from is not None:
        print(f"the ruling term is COUNTED, not bounded: {ruling} of the {len(grid)} "
              f"cells have a source objection whose stance is `contests`. The rest "
              "declined or were unreadable and put nothing to a judge.")
    if placeholder:
        print("this is the SECOND-LOOK CONTROL. It makes no challenger call, no "
              "comprehension probe, no agreement reading and no grade: its whole spend "
              f"is {ruling} rulings on a content-free objection plus the reading of "
              "them. Every cell the source declined keeps its before-state, exactly as "
              "it does there, so the two arms rule on the same cells.")
    # `max_decision_attempts` is deliberately NOT quoted here. It is loaded and
    # validated but consulted nowhere in `src/`, and the line that used to print it
    # promised a per-cell retry the harness does not make. What is true is stated
    # instead — including which cells a resume actually re-attempts, because that is
    # the difference between finishing a crashed sweep and giving ~900 truncated cells
    # a second draw at the moment the run is being approved.
    print("one attempt per cell per invocation, and one per cell across a resume: "
          "re-run the stage to resume, and a cell whose latest run is completed or "
          "failed is skipped while only a cell with no run — or one left running by a "
          "crash — is attempted. --retry-failed re-attempts failed cells too. Client "
          "transport retries and at most one format repair per generation are on top.")


def _tree_fingerprint(path: Path) -> str | None:
    """sha256 of the source tree's ``experiment.json``, or None if it has none.

    Provenance, not a checksum of the decisions: it pins WHICH run's decisions were
    contested — its name, its cases, its config — in a file the new tree owns. The
    decisions themselves are already hashed per cell by ``RunWriter.create_recourse``,
    which records a ``parent_sha256`` of the directory it copied.
    """
    source = path / "experiment.json"
    if not source.is_file():
        return None
    return hashlib.sha256(source.read_bytes()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, out of ``main`` so a test can assert on the real flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--stage", default="decide", choices=STAGES)
    parser.add_argument("--outputs", type=Path, default=Path("outputs/experiments"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="re-attempt cells whose latest run failed. Off by default: a failed cell "
             "was attempted and the model's outcome recorded, and re-drawing it "
             "selects for compliant outputs (LLM_NOTES.md 3p.4). Use it when the "
             "failures were the harness's fault — a bad provider slug, a full disk — "
             "not the model's. Only `decide` reads it.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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

    # The decision source. `None` — the ordinary case — means this tree decides for
    # itself and every stage reads and writes the same root.
    decisions_from = spec.get("decisions_from")
    decision_root = Path(decisions_from) if decisions_from else None
    if decision_root is not None and args.stage == "decide":
        raise SystemExit(
            f"this spec contests decisions in {decision_root}; it does not decide. "
            "Run --stage contest / agreement / grade / analyse against it, or drop "
            "decisions_from to make a tree that decides for itself."
        )

    # The OBJECTION source. Set only by a re-rule spec, which makes no objection of its
    # own: it copies each source contest here, minus its ruling, and rules it again. The
    # three stages that would generate an objection or a grade of one refuse, because
    # running any of them would make this tree hold objections the source never wrote
    # while claiming to re-rule the source's.
    contests_from = spec.get("contests_from")
    contest_root = Path(contests_from) if contests_from else None
    # THE ONE EXCEPTION, and it is narrow. The placeholder arm carries `contests_from`
    # and DOES run `contest` — but it generates nothing: the stage writes one fixed,
    # content-free text with no model call, and reads the source only to place itself on
    # exactly the cells the source arm objected to. Nothing under the source is written,
    # for the same reason a re-rule writes nothing under it. The other two stages the
    # refusal covers stay refused for that arm as well, and they are also the two the
    # stage-level skips already decline to spend on.
    placeholder_arm = config.challenger_variant == PLACEHOLDER_VARIANT
    refused = ("agreement", "grade") if placeholder_arm else ("contest", "agreement",
                                                              "grade")
    if contest_root is not None and args.stage in refused:
        raise SystemExit(
            f"this spec re-rules contests in {contest_root}; it does not contest. "
            f"`{args.stage}` would write a new objection (or a new grade of one) over "
            "the copy this tree holds. Run --stage rerule / ruling_agreement / analyse "
            "against it, or drop contests_from to make a tree that contests for itself."
        )
    if placeholder_arm and contest_root is None:
        raise SystemExit(
            f"`challenger_variant = \"{PLACEHOLDER_VARIANT}\"` needs `contests_from = "
            "\"<tree>\"`: the second-look control is defined by standing on exactly the "
            "cells the real arm contested, and without the source tree it would place "
            "itself on every decided cell instead — a different population, and not a "
            "control for anything."
        )
    if contest_root is None and args.stage == "rerule":
        raise SystemExit(
            "--stage rerule needs `contests_from = \"<tree>\"` in the spec: it re-rules "
            "objections another tree already made, and there are none to read."
        )
    if contest_root is not None and decision_root is None:
        raise SystemExit(
            "a spec with `contests_from` also needs `decisions_from`: a ruling is made "
            "against the decision that was contested, and this tree decides nothing."
        )

    # A spec whose NAME claims a challenger variant has to STATE one. `challenger_variant`
    # defaults to "neutral" — the historical value, so that specs written before the field
    # existed still mean what they ran — which makes the failure silent in exactly the
    # place it costs most: a spec called `partisan` with the field commented out would
    # run the neutral challenger, write it into `outputs/experiments/partisan/`, and
    # produce a tree whose every number is a neutral number under a partisan name. The
    # `challenge_arm` column would say "neutral" and nobody would read it before the
    # money was spent. `partisan.toml` ships with the field commented out on purpose —
    # the winning clause is chosen by a pilot — so this is what stops it running as-is.
    #
    # `judgment` is in the same trap for the same reason and is checked with it: a spec
    # called `judgment-pilot` with the field missing would run the stakeholder arm, grade
    # it against `flaw.json`, and produce a tree whose `grade_mode` said "flaw" under a
    # name that promised an audit.
    stated_variant = spec.get("debate", {}).get("challenger_variant")
    if stated_variant is None and ("partisan" in name or "judgment" in name):
        raise SystemExit(
            f"this spec is named {name!r} but sets no `challenger_variant`, so it would "
            f"run the neutral challenger — `challenger_variant` defaults to "
            f"{config.challenger_variant!r}. Set it in the spec's [debate] table to one "
            f"of {CHALLENGER_VARIANTS[1:]}, or rename the spec."
        )

    cases = load_cases(Path(spec["cases"]))
    if args.limit:
        cases = cases[: args.limit]
    grid = build_grid(cases, conditions, repeats)

    root = args.outputs / name
    root.mkdir(parents=True, exist_ok=True)

    print(f"experiment: {name}   stage: {args.stage}   outputs: {root}")
    if decision_root is not None:
        print(f"decisions read from: {decision_root}   (never written to)")
    n_source_contests = None
    if contest_root is not None:
        print(f"objections read from: {contest_root}   (never written to)")
        n_source_contests = len(source_contests(
            grid, source_root=contest_root,
            challenger_model=config.challenger_model_for()))
    print_estimate(grid, config, decisions_from=decision_root,
                   contests_from=contest_root,
                   n_source_contests=n_source_contests)
    print_hyperparameters(config, client_config, grading)

    if args.dry_run:
        print("\ndry run — nothing was sent. Re-run without --dry-run to spend.")
        return 0

    (root / "experiment.json").write_text(json.dumps({
        "name": name, "conditions": conditions, "repeats": repeats,
        "cases": spec["cases"], "cells": len(grid),
        # Null unless this tree contests another's decisions. The hash is of the source
        # tree's experiment.json: without it a re-contest's records would name a path
        # that may since have been re-run under the same name.
        "decisions_from": str(decision_root) if decision_root else None,
        "decisions_from_experiment_sha256": (
            _tree_fingerprint(decision_root) if decision_root else None),
        # Null unless this tree re-rules another's objections. Both sources are named
        # and both are hashed: a re-rule reads two trees and its record has to pin which
        # run of each, since a rerule tree's numbers are only comparable against the
        # exact objections they were made on.
        "contests_from": str(contest_root) if contest_root else None,
        "contests_from_experiment_sha256": (
            _tree_fingerprint(contest_root) if contest_root else None),
        "config": config.to_dict(), "client_config": client_config.to_dict(),
        "grading": grading.to_dict(),
    }, indent=2), encoding="utf-8")

    if args.stage == "analyse":
        rows = build_index(grid, root=root,
                           challenger_model=config.challenger_model_for(),
                           decision_root=decision_root)
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
            api_key=api_key, retry_failed=args.retry_failed),
        "contest": lambda: run_stage_contest(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key, decision_root=decision_root,
            contest_root=contest_root),
        "rerule": lambda: run_stage_rerule(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key, decision_root=decision_root or root,
            contest_root=contest_root),
        "ruling_agreement": lambda: run_stage_ruling_agreement(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key=api_key),
        "agreement": lambda: run_stage_agreement(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key=api_key,
            decision_root=decision_root),
        "grade": lambda: run_stage_grade(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key=api_key,
            decision_root=decision_root),
    }[args.stage]

    results = asyncio.run(runner())
    counts: dict[str, int] = {}
    for result in results:
        key = ("error" if isinstance(result, BaseException)
               else result.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    print(f"\n{args.stage}: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    # THE CONTROL'S ONE INVARIANT, asserted where it can still be acted on. The
    # placeholder arm is a control only if it stands on exactly the cells the source arm
    # objected to: one cell too many and the judge is given a second look the real arm
    # never gave it, one too few and the two after-states are not paired. `completed +
    # already contested` is the count that has to equal the source's, because a resumed
    # run finds some of its own work already done.
    if placeholder_arm and args.stage == "contest":
        emitted = sum(1 for result in results
                      if not isinstance(result, BaseException)
                      and (result.get("status") == "completed"
                           or result.get("reason") == "already contested"))
        expected = n_source_contests or 0
        verdict = "MATCHES" if emitted == expected else "DOES NOT MATCH"
        print(f"\nplaceholder placement: {emitted} objections stand where "
              f"{contest_root} raised {expected} — {verdict}.")
        if emitted != expected:
            print("  ! the second-look control is NOT paired with the arm it controls "
                  "for. Do not read a P2 comparison off this tree until the difference "
                  "is accounted for cell by cell.")
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
