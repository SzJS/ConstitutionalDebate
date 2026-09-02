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

A spec with ``contests_from`` may also run ``--stage gatekeeper``, and that stage is the
narrowest of all: it copies each source contest here WITH its ruling and adds one file,
``admission.json``, saying whether a same-class model finds the objection admissible at
all. It re-rules nothing, so the rulings in this tree are byte-identical to the source's;
what the answer changes is `final_correct` in THIS tree's index — the ruling's outcome
where the objection was admitted, the decision's own verdict where it was refused. It
needs ``gatekeeper_model`` in the ``[debate]`` table, which has no default and inherits
from nothing. POST HOC: the M4 ablation of 2026-08-28, added after the primary arm's
preliminary numbers were seen.

A spec may instead set ``transcripts_from = "<path>"``. The run then reads the stored
debate TRANSCRIPTS out of that tree and judges them again under its own ``judge_model``,
writing a full decision record of its own — the transcript copied, the new judgment and
verdict, a ``config.json`` naming the judge that made it. Everything downstream then
works with no change at all: the tree it writes is an ordinary decision tree, and a later
spec points ``decisions_from`` at it. ``--stage decide`` refuses on such a spec (it would
re-run the debates), ``--stage rejudge`` refuses without it, the two source keys are
mutually exclusive — a run either decides for itself, reads decisions, or re-judges
transcripts, and never two of the three — and the conditions must be ``["debate"]``,
because only a debate leaves a record a second judge can be handed without re-deciding.

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
from typing import Any, Sequence

from dotenv import load_dotenv

from .accounting import aggregate_tree
from .analysis import analyse
from .arms import CONDITIONS
from .config import (
    CHALLENGER_VARIANTS,
    CLIENT_WHY,
    GRADING_WHY,
    FABRICATED_VARIANT,
    FINDINGS_VARIANT,
    JUDGMENT_VARIANT,
    PLACEHOLDER_VARIANT,
    SPECIOUS_VARIANT,
    WHY,
    ClientConfig,
    DebateConfig,
    GradingConfig,
    load_config,
    load_grading_config,
    why_for,
)
from .experiment import (
    STAGES,
    build_grid,
    build_index,
    run_stage_agreement,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
    run_stage_rejudge,
    run_stage_gatekeeper,
    run_stage_rerule,
    run_stage_ruling_agreement,
    source_contests,
    source_decisions,
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
    # `why_for`, not the bare table: two of its lines are only true at the default
    # and this is the document the run is approved from.
    _print_table("debate", config, why_for(config))
    _print_table("client", client_config, CLIENT_WHY)
    _print_table("grading", grading, GRADING_WHY)
    print("=" * 100)


def print_estimate(grid, config: DebateConfig,
                   decisions_from: Path | None = None,
                   contests_from: Path | None = None,
                   n_source_contests: int | None = None,
                   transcripts_from: Path | None = None,
                   n_source_decisions: int | None = None,
                   planned_stages: Sequence[str] | None = None) -> None:
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

    ``planned_stages`` is the spec's own statement of which stages its driver runs, and
    it is echoed VERBATIM rather than used to compute anything. The terms above are
    per-stage bounds and every one of them is printed whether or not that stage is in the
    run — which is right, because a spec is a description of a tree and a stage can be run
    against it later — but it means the total over-counts a driver that runs two stages of
    seven. Rather than teach the estimator which stages a shell script will invoke, the
    spec says so and the line below repeats it, so the reader agreeing to the spend can
    see the difference. Absent means the spec does not say, and the line says that too.

    ``transcripts_from`` replaces the decision term with a COUNTED one: a re-judge makes
    exactly ONE call per stored decision — the judge's, over a transcript it does not
    re-run — so the figure is the source tree's decided cells and not the 7 calls a
    debate costs. On the sweep's debate cells those differ by a factor of seven and by
    hundreds of cells the sweep never decided, and quoting the grid here would quote
    fourteen times the spend at the moment it is being agreed to.
    """
    by_condition: dict[str, int] = {}
    for cell in grid:
        by_condition[cell.condition] = by_condition.get(cell.condition, 0) + 1
    decision = (0 if decisions_from is not None
                else (n_source_decisions or 0) if transcripts_from is not None
                else sum(n * calls_per_cell(c, config) for c, n in by_condition.items()))
    # challenge + comprehension always; ruling only when an objection is raised, and
    # grading only on flawed items whose subset records what the flaw was.
    contest = 0 if contests_from is not None else 2 * len(grid)
    ruling = (n_source_contests if contests_from is not None else len(grid)) or 0
    # THE CONTESTABILITY DEBATE ROUND. Two debater calls per cell that actually puts
    # something to a judge — the round is heard only where there is an objection to argue
    # about — so it is counted off the same number the ruling term is, and it is the
    # single largest term in that arm's bill: the round-4 turns are strong-model
    # generations with a four-round context, where the ruling is one short weak-model
    # call.
    contest_round = config.recourse_rounds * 2 * ruling
    # And the plain-round baseline: two debater calls per SOURCE DECISION, on every cell
    # that has one, because nothing gates an ordinary round on an objection.
    extra_rounds = (2 * (config.n_rounds - 3) * decision
                    if config.extend_rounds and transcripts_from is not None else 0)
    # One short grader call per contest whose decision line parsed — the line-vs-prose
    # instrument. Bounded by the grid because every cell can produce at most one.
    # ZERO for the findings arm: that stage makes NO call there. The objection's argument
    # is a numbered list the harness already parsed, so line-vs-prose is a string
    # comparison (`recourse.mechanical_agreement`) rather than a grader reading. Quoting
    # a per-cell grader call for a stage that spends nothing would overstate the bill at
    # the moment it is being agreed to.
    agreement = (0 if contests_from is not None
                 or config.challenger_variant == FINDINGS_VARIANT
                 else len(grid))
    # One per ruling: the judge's line read against the judge's own prose.
    ruling_agreement = ruling
    # One per CONTESTED source cell, and only where a gate model is named: the M4
    # admissibility gate. Counted off the source tree for the same reason the ruling term
    # is — it lands on exactly the cells that objected, and bounding it by the grid would
    # quote five times the spend at the moment it is being agreed to.
    gatekeeper = ruling if config.gatekeeper_model else 0
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
    # The FABRICATED arm takes the judgment grading term too, and the estimate it
    # produces is deliberately an UPPER bound rather than the spend: when the arm works,
    # every defect fails the parse-time quote check and `grading._grade_judgment` returns
    # a `quote_check_only` grade with NO wire call, so the grader is called only on the
    # objections the manipulation failed on. Quoting the smaller number here would be
    # quoting a number that is only right if the arm succeeds.
    # The FINDINGS arm takes the judgment grading term for the same reason: every
    # contested cell is graded there too — sound items and correct decisions included —
    # because two of its three contest kinds are graded against the record and the third
    # is settled by the label on a sound item. It is an UPPER bound, like the fabricated
    # arm's: an objection whose every contest is void or settled by the label is graded
    # with no wire call at all (`grading._grade_findings`).
    judgment = config.challenger_variant in (JUDGMENT_VARIANT, SPECIOUS_VARIANT,
                                             FABRICATED_VARIANT, FINDINGS_VARIANT)
    placeholder = config.challenger_variant == PLACEHOLDER_VARIANT
    gradable = (0 if contests_from is not None
                else len(grid) if judgment
                else sum(1 for cell in grid if cell.case.gradable))
    print(f"\ncells: {len(grid)}  " +
          "  ".join(f"{c}={n}" for c, n in sorted(by_condition.items())))
    decision_term = (
        f"decision 0 (read from {decisions_from})" if decisions_from is not None
        else f"decision {decision} (one judge call per stored transcript in "
             f"{transcripts_from}; the debates are NOT re-run)"
        if transcripts_from is not None else f"decision {decision}")
    contest_term = (
        "contest 0 (the placeholder objection is a fixed text written with NO model "
        f"call, on the cells {contests_from} contested)" if placeholder
        else f"contest 0 (objections read from {contests_from})"
        if contests_from is not None else f"contest {contest}")
    # Printed whenever a gate is NAMED, zero included: a spec that names a gatekeeper
    # and quotes no gate term reads as a spec with no gate, and 0 is itself the
    # thing to see — the source tree holds no contested objection to gate.
    gate_term = (f", gatekeeper <= {gatekeeper}" if config.gatekeeper_model
                 else "")
    round_term = (f", contest round {contest_round}" if contest_round else "")
    extend_term = (f", extra debate rounds {extra_rounds}" if extra_rounds else "")
    print(f"estimated calls: {decision_term}{extend_term}, {contest_term}{round_term}, "
          f"ruling <= {ruling}, agreement <= {agreement}, "
          f"ruling_agreement <= {ruling_agreement}, grading <= {gradable}{gate_term}  "
          f"=> up to {decision + extra_rounds + contest + contest_round + ruling + agreement + ruling_agreement + gradable + gatekeeper}")
    if contest_round:
        print(f"the contest round adds 2 DEBATER calls per contested cell "
              f"({contest_round} in all), at `{config.debater_model}` and "
              f"{config.debater_temperature}: the two ORIGINAL debaters each reply once "
              "to the objection, simultaneously, and the recourse judge rules on the "
              "exchange instead of on the objection alone. They are the expensive calls "
              "in this arm — a strong model writing 400 words over a four-round context "
              "— and a cell whose round completes but whose ruling fails is re-attempted "
              "from scratch, buying both turns again.")
    if extra_rounds:
        print(f"extend_rounds adds 2 DEBATER calls per stored decision "
              f"({extra_rounds} in all), at `{config.debater_model}` and "
              f"{config.debater_temperature}: the same two debaters continue the stored "
              f"debate to {config.n_rounds} rounds under the ORDINARY round instruction "
              "— no objection anywhere — and then the judge decides the longer "
              "transcript. This is the plain-round baseline; nothing gates it on an "
              "objection, so it lands on every cell with a source decision.")
    if planned_stages:
        print(f"stages this spec's driver runs: {' '.join(planned_stages)}  "
              "(`planned_stages` in the spec, echoed verbatim). Every term above is a "
              "per-stage bound and is printed whether or not that stage is in the run, "
              "so the total is a bound over ALL stages and not this driver's bill.")
    else:
        print("stages this spec's driver runs: unknown — the spec sets no "
              "`planned_stages`, so the total above is a bound over every stage that "
              "could be run against this tree, not over the ones that will be.")
    if judgment:
        print("the grading term is the whole grid: `challenger_variant = "
              f"\"{config.challenger_variant}\"` grades every cell whose objection "
              "contests, against the RECORD rather than the recorded flaw — so the "
              "annotation gates that hold the ordinary grading term down do not apply.")
    if config.challenger_variant == FINDINGS_VARIANT:
        print("the AGREEMENT term is 0 and that is not an omission: under the findings "
              "arm the line-vs-prose instrument is MECHANICAL — the objection's "
              "argument is a numbered list this harness parses, so `phantom_contest` is "
              "`(stance == contests) != (well-formed contests > 0)`, a string "
              "comparison rather than a grader reading. It is never pooled with the "
              "Haiku column of the judgment campaigns. The DECISION term buys a "
              "findings judgment per stored transcript: the judge writes a numbered "
              "list and NO verdict line, and the verdict is derived by code (FLAWED iff "
              "any finding is ruled FLAW). A list that will not parse buys one format "
              "repair and then fails its cell, exactly as a malformed verdict does, and "
              "both count against the arm's parse rate.")
    if config.challenger_variant == FABRICATED_VARIANT:
        # The one arm whose grading term is an upper bound rather than a forecast, and
        # the reader agreeing to the spend has to know which: a working fabricated arm
        # pays almost nothing here, and a bill that lands near the bound is the
        # manipulation failing rather than the estimate being wrong.
        print("BUT THE FABRICATED ARM SHOULD PAY ALMOST NONE OF IT: an objection whose "
              "every defect fails the parse-time quote check is graded invalid with NO "
              "grader call, which is what this arm is built to produce on every cell. "
              "The grading term above is the bound if the manipulation fails outright; "
              "the grader is called only on the objections whose quotations turned out "
              "to be real, and that count IS the failure-mode measurement.")
    if transcripts_from is not None:
        print(f"the decision term is COUNTED, not bounded: {decision} of the "
              f"{len(grid)} cells have a decided run in {transcripts_from}, and each "
              "costs ONE judge call over the transcript that run already paid for. The "
              "rest were never decided there and are skipped with `no source decision "
              "to re-judge`. A judgment that truncates or will not parse fails its cell "
              "and is counted, not decided, exactly as it was in the source run.")
    if contests_from is not None:
        print(f"the ruling term is COUNTED, not bounded: {ruling} of the {len(grid)} "
              f"cells have a source objection whose stance is `contests`. The rest "
              "declined or were unreadable and put nothing to a judge.")
    if config.gatekeeper_model:
        print(f"the gatekeeper term is COUNTED, not bounded: ONE admissibility call per "
              f"contested source objection, at `{config.gatekeeper_model}`. It re-rules "
              "nothing and re-writes nothing — the objections and the rulings are copied "
              "verbatim and one `admission.json` is added beside each. POST HOC (M4, "
              "2026-08-28): read it as an ablation beside the pre-registered endpoint, "
              "never as it.")
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
             "not the model's. `decide` and `rejudge` read it; no other stage does.")
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

    # The TRANSCRIPT source. Set only by a re-judge spec, which makes no debate of its
    # own: it copies each source decision here minus its verdict and judges the stored
    # transcript again. What it writes is an ORDINARY decision tree — that is the whole
    # design — so no other stage learns a new path and a later spec reads it through
    # `decisions_from` unchanged.
    transcripts_from = spec.get("transcripts_from")
    transcript_root = Path(transcripts_from) if transcripts_from else None
    if transcript_root is not None and args.stage == "decide":
        raise SystemExit(
            f"this spec re-judges the stored transcripts in {transcript_root}; it does "
            "not decide. `decide` would run the debates again — new arguments, a new "
            "population, and the one thing this stage exists to hold fixed. Run "
            "--stage rejudge / contest / agreement / ruling_agreement / grade / analyse "
            "against it, or drop transcripts_from to make a tree that decides for "
            "itself."
        )
    if transcript_root is not None and decision_root is not None:
        raise SystemExit(
            "a spec may set `decisions_from` OR `transcripts_from`, not both: the first "
            "reads finished decisions and never writes one, the second WRITES a "
            "decision per stored transcript. With both, every stage after `rejudge` "
            "would read its decisions out of the other tree and the re-judged verdicts "
            "this run paid for would be indexed nowhere."
        )
    if transcript_root is not None and set(conditions) != {"debate"}:
        raise SystemExit(
            f"this spec re-judges transcripts but runs conditions {conditions}. "
            "`rejudge` is debate-only: only a debate leaves a record a second judge can "
            "be handed. `single` and `self_critique` reach their verdict inside the "
            "conversation that wrote the record, so there is nothing to re-judge "
            "without re-running the decision. Set `conditions = [\"debate\"]`."
        )
    if transcript_root is None and args.stage == "rejudge":
        raise SystemExit(
            "--stage rejudge needs `transcripts_from = \"<tree>\"` in the spec: it "
            "judges debates another tree already ran, and there are none to read."
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
    #
    # `gatekeeper` is NOT in the refusal for the same reason `rerule` is not: it writes no
    # objection and no grade of one. It writes a file the source does not have, beside a
    # copy of the source's own objection and ruling, and it is the only stage that adds to
    # a contest record without replacing anything in it.
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
    if contest_root is None and args.stage == "gatekeeper":
        raise SystemExit(
            "--stage gatekeeper needs `contests_from = \"<tree>\"` in the spec: it "
            "decides which of another tree's finished objections are heard, and there "
            "are none to read."
        )
    if args.stage == "gatekeeper" and not config.gatekeeper_model:
        raise SystemExit(
            "--stage gatekeeper needs `gatekeeper_model` in the spec's [debate] table. "
            "It has no default and inherits from no other field: a gate that fell back "
            "to `judge_model` would have the judge decide whether the appeal against "
            "its own judgment is heard, and a gate stronger than the decider would "
            "import a better reader into the decision path — the confound that stopped "
            "the judgment-debate-2 chain."
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
    if stated_variant is None and any(word in name for word in
                                      ("partisan", "judgment", "fabricated",
                                       "findings", "fd1")):
        raise SystemExit(
            f"this spec is named {name!r} but sets no `challenger_variant`, so it would "
            f"run the neutral challenger — `challenger_variant` defaults to "
            f"{config.challenger_variant!r}. Set it in the spec's [debate] table to one "
            f"of {CHALLENGER_VARIANTS[1:]}, or rename the spec."
        )
    # AND THE SECOND HALF OF THE SAME TRAP, for the findings campaign only. `judge_form`
    # defaults to "verdict" — the historical value, so specs written before the field
    # existed still mean what they ran — which makes the failure silent exactly where it
    # costs most: a spec called `fd1-weak` with `judge_form` commented out would run the
    # ORDINARY judge, write prose verdicts into `outputs/experiments/fd1-weak/`, and then
    # fail every contest for want of a `findings.json` — after paying for 1,644
    # judgments. `DebateConfig` refuses `challenger_variant = "findings"` without it, so
    # this catches the other order: a findings-named spec that states neither.
    stated_form = spec.get("debate", {}).get("judge_form")
    if stated_form is None and any(word in name for word in ("findings", "fd1")):
        raise SystemExit(
            f"this spec is named {name!r} but sets no `judge_form`, so its judge would "
            f"write a prose verdict — `judge_form` defaults to "
            f"{config.judge_form!r}. Set `judge_form = \"findings\"` in the spec's "
            "[debate] table, or rename the spec."
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
    n_source_decisions = None
    if transcript_root is not None:
        print(f"transcripts read from: {transcript_root}   (never written to)")
        n_source_decisions = len(source_decisions(grid, source_root=transcript_root))
    n_source_contests = None
    if contest_root is not None:
        print(f"objections read from: {contest_root}   (never written to)")
        n_source_contests = len(source_contests(
            grid, source_root=contest_root,
            challenger_model=config.challenger_model_for()))
    print_estimate(grid, config, decisions_from=decision_root,
                   contests_from=contest_root,
                   n_source_contests=n_source_contests,
                   transcripts_from=transcript_root,
                   n_source_decisions=n_source_decisions,
                   planned_stages=spec.get("planned_stages"))
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
        # Null unless this tree re-judges another's transcripts. Named and hashed for
        # the same reason both of the above are: this tree's verdicts are only
        # interpretable against the exact debates they were made over, and the source
        # tree's own cell directories are hashed one by one in each run's manifest.
        "transcripts_from": str(transcript_root) if transcript_root else None,
        "transcripts_from_experiment_sha256": (
            _tree_fingerprint(transcript_root) if transcript_root else None),
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
        "rejudge": lambda: run_stage_rejudge(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key, transcript_root=transcript_root,
            retry_failed=args.retry_failed),
        "contest": lambda: run_stage_contest(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key, decision_root=decision_root,
            contest_root=contest_root),
        "rerule": lambda: run_stage_rerule(
            grid, root=root, config=config, client_config=client_config,
            api_key=api_key, decision_root=decision_root or root,
            contest_root=contest_root),
        "gatekeeper": lambda: run_stage_gatekeeper(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key=api_key,
            decision_root=decision_root or root, contest_root=contest_root),
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
