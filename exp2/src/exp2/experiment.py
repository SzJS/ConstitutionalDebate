"""The staged batch harness.

Stages: ``decide`` → ``contest`` → ``agreement`` → ``grade`` → ``analyse``.

The plan named ``challenge``, ``rule`` and ``comprehend`` as separate stages; they are
one stage here, and the reason is the comprehension probe. It is asked inside the
challenger's own live conversation, immediately after the objection. Splitting it out
would mean replaying that conversation from disk to ask one question — more moving
parts, and a replay that could silently diverge from what was actually sent. The three
share a coroutine and a resume key.

**Resume is keyed on artifacts, never on a ledger.** A stage is done for a cell if and
only if the record it should have written loads. exp1 keyed one stage on the run
directory, which exists before the first call, making failed contests permanently
un-retryable and invisible to the index.

**A resume gives no cell a second draw.** ``decide`` also skips a cell whose latest run
manifest says ``"failed"`` — attempted, and the model's outcome recorded. Only a cell
with no run, or one left ``"running"`` by a killed process, is attempted again, because
only there was nothing learned. ``--retry-failed`` opts back in; see
``run_stage_decide``.

**Every stage is concurrent against one shared client.** exp1's grade and validate
stages were serial `await` loops that each built a fresh client per item, so their
semaphores could never be contended — a direct violation of the repo's parallelism
rule. ``FakeClient.max_in_flight`` is what stops that recurring.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .accounting import aggregate_calls, split_calls
from .arms import CONDITIONS, DECIDERS
from .client import OpenRouterClient
from .config import (
    JUDGMENT_VARIANT,
    PLACEHOLDER_VARIANT,
    ClientConfig,
    DebateConfig,
    GradingConfig,
)
from .grading import NotGradable, grade_objection
from .persistence import RunWriter, load_flaw, load_run_record
from .recourse import _rule_by_judge, judge_prose_stance, judge_ruling_prose, run_recourse
from .types import Case, Challenge, Item, Ruling, make_sides

log = logging.getLogger(__name__)

# ``agreement`` sits between ``contest`` and ``grade`` because it reads what the contest
# wrote and because the grade stage's own gate — stance == "contests" — is the column it
# exists to audit. It resumes on ``agreement.json`` like every other stage resumes on
# its own artifact.
#
# ``ruling_agreement`` sits directly after it and is the same instrument one layer down:
# it audits the recourse judge's line against the judge's own prose, as ``agreement``
# audits the challenger's. It reads ``ruling.json`` and nothing else, so it runs over
# rulings made under any of the three forms — which is how the sweep's 1,122 and the
# re-contest's 464, all written under the old ``Ruling:`` line, get measured on the same
# scale as the rulings ``rerule`` makes.
#
# ``rerule`` is not part of an ordinary run and the driver's default list omits it. It
# belongs to a spec with ``contests_from``: it re-rules another tree's finished
# objections without re-making them, and ``contest`` refuses on such a spec.
STAGES: tuple[str, ...] = (
    "decide", "contest", "rerule", "agreement", "ruling_agreement", "grade", "analyse",
)


@dataclass(frozen=True)
class Cell:
    case: Case
    condition: str
    repeat: int = 1

    @property
    def cell_id(self) -> str:
        return f"{self.case.item.item_id}__{self.condition}__r{self.repeat}"


def build_grid(cases: Sequence[Case], conditions: Sequence[str],
               repeats: int = 1) -> list[Cell]:
    unknown = sorted(set(conditions) - set(DECIDERS))
    if unknown:
        raise ValueError(f"unknown conditions: {unknown}; expected {list(CONDITIONS)}")
    seen: set[str] = set()
    for case in cases:
        if case.item.item_id in seen:
            raise ValueError(f"duplicate item_id {case.item.item_id!r}; item ids are "
                             "also cell directory names and would collide")
        seen.add(case.item.item_id)
    return [Cell(case, condition, repeat)
            for case in cases for condition in conditions
            for repeat in range(1, repeats + 1)]


def cell_dir(root: Path, cell: Cell) -> Path:
    return root / "cells" / cell.cell_id


def existing_decision(root: Path, cell: Cell):
    """The completed decision for this cell, if one loads. This is the resume key."""
    runs = sorted((cell_dir(root, cell) / "runs").glob("*"), reverse=True)
    for directory in runs:
        try:
            return load_run_record(directory)
        except (ValueError, FileNotFoundError, KeyError):
            continue
    return None


def latest_run_status(root: Path, cell: Cell) -> str | None:
    """The ``status`` in the newest run directory's manifest, or ``None`` if never
    attempted.

    ``persistence.RunWriter`` writes exactly three values: ``"running"`` at creation,
    then ``"completed"`` or ``"failed"`` through ``finish()``. The three mean different
    things to a resume:

    * ``"completed"`` — decided; ``existing_decision`` already skips it.
    * ``"failed"`` — the cell was attempted and the *model* or the *call* produced no
      usable decision (truncation, a malformed reply that survived its repair, a
      timeout). That is an outcome, not an interruption.
    * ``"running"`` — the process was killed mid-flight (a crash, an ENOSPC, a SIGTERM
      to the driver). Nothing about the model was learned, so this is not an outcome and
      the cell is attempted again.
    * ``None`` — no run directory at all: never attempted.

    Run directories are named ``<timestamp>-<item_id>``, so a reverse sort is newest
    first. A directory whose manifest cannot be read is not evidence of anything and the
    search falls through to the one before it.
    """
    runs = sorted((cell_dir(root, cell) / "runs").glob("*"), reverse=True)
    for directory in runs:
        try:
            manifest = json.loads(
                (directory / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        status = manifest.get("status")
        if isinstance(status, str):
            return status
    return None


def contest_dir(root: Path, cell: Cell, challenger_model: str) -> Path:
    slug = challenger_model.replace("/", "-")
    return cell_dir(root, cell) / "contests" / slug


def existing_contest(root: Path, cell: Cell, challenger_model: str) -> Path | None:
    runs = sorted((contest_dir(root, cell, challenger_model) / "runs").glob("*"),
                  reverse=True)
    for directory in runs:
        if (directory / "challenge.json").is_file():
            return directory
    return None


async def _bounded(tasks: Sequence[Callable[[], Any]], limit: int) -> list[Any]:
    """Run every task, at most ``limit`` at once, never failing the whole stage on one.

    A failure becomes that item's result rather than the stage's, because one unreadable
    directory or one refusing model should cost a measurement, not an afternoon.
    """
    semaphore = asyncio.Semaphore(limit)

    async def guarded(task):
        async with semaphore:
            return await task()

    return await asyncio.gather(*(guarded(t) for t in tasks), return_exceptions=True)


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
#
# Each stage builds one client *per run*, so that run's sink owns its own calls.jsonl
# and the logs do not interleave. A single semaphore is shared across those clients, so
# the fleet as a whole stays inside max_concurrency rather than running that many
# requests per run.


async def run_stage_decide(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    client_config: ClientConfig, api_key: str, retry_failed: bool = False,
) -> list[dict[str, Any]]:
    """One attempt per cell per invocation, and by default one attempt per cell *ever*.

    A resume attempts a cell only when nothing was learned about it: no run directory at
    all, or a run left ``"running"`` by a killed process. A cell whose latest run is
    ``"failed"`` was attempted and produced a model outcome — a truncation, a reply that
    was still malformed after its repair — and re-attempting it is the per-cell retry
    that ``LLM_NOTES.md`` §3p.4 declined to wire, for two reasons that both still hold:
    it selects for compliant outputs, so the surviving cells are no longer a sample of
    the corpus; and at ``seed = 0`` the side assignment and template order are identical
    on the second draw, so most of the spend reproduces the first failure.

    ``retry_failed=True`` (``--retry-failed``) opts back in, for the case where the
    failures were the harness's fault rather than the model's — a bad provider slug, a
    full disk — and the run is being repaired rather than resumed.
    """
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def decide(cell: Cell) -> dict[str, Any]:
        if existing_decision(root, cell) is not None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already decided"}
        if not retry_failed and latest_run_status(root, cell) == "failed":
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already attempted and failed; --retry-failed to "
                              "re-attempt"}
        sides = make_sides(cell.case.item, config.seed)
        writer = RunWriter.create(
            root=cell_dir(root, cell) / "runs", item=cell.case.item, sides=sides,
            config=config, client_config=client_config, condition=cell.condition,
            flaw=cell.case.flaw,
        )
        writer.manifest_update(cell_id=cell.cell_id)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    result = await DECIDERS[cell.condition](
                        cell.case.item, config, sides, client, writer=writer,
                    )
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        writer.finish("completed", totals=aggregate_calls(writer.dir / "calls.jsonl"))
        return {"cell_id": cell.cell_id, "status": "completed",
                "verdict": result.verdict.verdict, "correct": result.verdict.correct}

    return await _bounded([lambda c=c: decide(c) for c in cells],
                          client_config.max_runs_in_flight)


async def run_stage_contest(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    client_config: ClientConfig, api_key: str, rule: bool = True,
    decision_root: Path | None = None, contest_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Challenge, comprehension probe, and ruling — one coroutine, one resume key.

    They share a stage because the comprehension probe is asked inside the challenger's
    live conversation. Splitting it out would mean replaying that conversation from disk
    to ask one question, and a replay can diverge from what was actually sent.

    ``decision_root`` is where the DECISIONS live and defaults to ``root``. They differ
    when a spec sets ``decisions_from``: the contest then reads a tree it never writes
    to — the sweep's 5,724 decisions are re-contested under a new protocol without
    regenerating one of them, and without an overwritten ``experiment.json`` or an
    ambiguous append to the source's ``cells.jsonl``.

    ``contest_root`` is the PLACEHOLDER ARM's population, and it is the one case in which
    a spec may carry ``contests_from`` and still run ``contest``. That arm writes no
    objection of its own — it emits one fixed, content-free text with no model call — so
    it cannot overwrite a source objection the way a real contest would, and its whole
    validity as a control depends on landing on **exactly** the cells the source arm
    contested. So it reads the source's stances and emits the placeholder where the
    source objected and nothing at all where the source declined, leaving those cells
    their before-state as the design requires. Any other variant with a ``contest_root``
    is refused here rather than in the CLI, so the invariant holds for a direct caller
    too.
    """
    decisions = decision_root or root
    challenger = config.challenger_model_for()
    placeholder = config.challenger_variant == PLACEHOLDER_VARIANT
    if contest_root is not None and not placeholder:
        raise ValueError(
            "run_stage_contest takes a contest_root only for "
            f"challenger_variant='{PLACEHOLDER_VARIANT}', which generates nothing and "
            f"reads the source only to place itself; got {config.challenger_variant!r}."
        )
    if placeholder and contest_root is None:
        raise ValueError(
            f"challenger_variant='{PLACEHOLDER_VARIANT}' needs `contests_from` naming "
            "the tree whose objections it stands in for: the control is defined by "
            "landing on exactly the cells that arm contested, and without the source "
            "it would place itself on every decided cell instead."
        )
    # Read once, not per cell: the source is a finished tree of thousands of directories
    # and a per-cell re-read would walk it once per cell.
    source_contested: set[str] | None = None
    if contest_root is not None:
        source_contested = {
            cell.cell_id for cell, _ in source_contests(
                cells, source_root=contest_root, challenger_model=challenger)
        }
        log.info("placeholder arm: %d of %d cells carry a contested source objection",
                 len(source_contested), len(cells))
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def contest(cell: Cell) -> dict[str, Any]:
        if existing_contest(root, cell, challenger) is not None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already contested"}
        if source_contested is not None and cell.cell_id not in source_contested:
            # The source declined, was unreadable, or never got a contest at all. The
            # design holds "which cells get a second look" constant across the arms, so
            # this cell keeps its before-state here exactly as it does there.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "source raised no objection; no placeholder emitted"}
        record = existing_decision(decisions, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision to contest"}
        async with semaphore:
            # Inside the bound: create_recourse copies the parent tree and hashes it,
            # and exp1 ran that unbounded, so every parent copy happened at once.
            writer = await asyncio.to_thread(
                RunWriter.create_recourse,
                root=contest_dir(root, cell, challenger) / "runs",
                parent_dir=record.directory, item=record.item, sides=record.sides,
                config=config, client_config=client_config, condition=cell.condition,
                copy_parent=client_config.copy_parent,
            )
        # `recourse_form` and `challenger_variant` are recorded here rather than trusted
        # to config.json: create_recourse copies the DECISION's config.json and ignores
        # the config it is handed, so the contest run's own config.json is the decider's
        # — written before either field existed, and describing a run that made no
        # objection at all. A contest that routed the appeal differently from the
        # decision, or that ran an advocate where the decision's config says nothing,
        # would otherwise leave no trace of it on the run.
        writer.manifest_update(cell_id=cell.cell_id, challenger_model=challenger,
                               recourse_form=config.recourse_form,
                               challenger_variant=config.challenger_variant)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    outcome = await run_recourse(record, config, client, rule=rule,
                                                 writer=writer)
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s contest failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        writer.finish("completed", totals=aggregate_calls(writer.dir / "calls.jsonl"))
        return {"cell_id": cell.cell_id, "status": "completed",
                "raised": outcome.challenge.raised,
                "stance": outcome.challenge.stance,
                "changed": (outcome.ruling.changed_the_decision
                            if outcome.ruling else False)}

    return await _bounded([lambda c=c: contest(c) for c in cells],
                          client_config.max_runs_in_flight)


def source_contests(cells: Sequence[Cell], *, source_root: Path,
                    challenger_model: str) -> list[tuple[Cell, Path]]:
    """The cells of ``cells`` that a source tree holds a CONTESTED objection for.

    The population ``rerule`` will rule on, and therefore the number the run's spend is
    approved from: an objection that declined put nothing to a judge and has no ruling to
    re-make. Computed by reading each source ``challenge.json`` rather than the source
    index, so a spec pointed at a tree with no index still quotes a true figure.
    """
    found: list[tuple[Cell, Path]] = []
    for cell in cells:
        directory = existing_contest(source_root, cell, challenger_model)
        if directory is None:
            continue
        try:
            challenge = Challenge.from_dict(
                json.loads((directory / "challenge.json").read_text()))
        except (OSError, ValueError, KeyError):
            continue
        if challenge.stance == "contests":
            found.append((cell, directory))
    return found


async def run_stage_rerule(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    client_config: ClientConfig, api_key: str, decision_root: Path,
    contest_root: Path,
) -> list[dict[str, Any]]:
    """Rule another tree's finished objections again, into this tree.

    The objections themselves are not re-made — they are the stakeholder's, they cost
    real money, and re-drawing them would change the population as well as the ruling. So
    each source contest directory is COPIED here minus its ruling, its wire log and its
    two documents, the source ruling is kept beside it as ``ruling.source.json``, and one
    new call is made. The result is a self-contained contest record of exactly the same
    shape as one this harness contested itself, which is what makes it readable and what
    lets ``agreement``, ``ruling_agreement`` and ``analyse`` run over it unchanged.

    Nothing under ``contest_root`` or ``decision_root`` is written. Both are named in
    ``experiment.json`` with the sha256 of their ``experiment.json``, and each cell's
    manifest additionally carries ``source_contest_dir``, ``source_sha256`` — a hash of
    the whole source directory — and ``rerule_of_form``, the form of the ruling being
    replaced.

    Only cells whose source objection has stance ``contests`` are re-ruled. A decline put
    nothing to a judge, so there is no ruling to re-make and the cell is skipped with
    ``no objection to re-rule`` rather than silently.
    """
    challenger = config.challenger_model_for()
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def rerule(cell: Cell) -> dict[str, Any]:
        existing = existing_contest(root, cell, challenger)
        if existing is not None and (existing / "ruling.json").is_file():
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already re-ruled"}
        source = existing_contest(contest_root, cell, challenger)
        if source is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no source contest to re-rule"}
        challenge = Challenge.from_dict(
            json.loads((source / "challenge.json").read_text()))
        if challenge.stance != "contests":
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no objection to re-rule"}
        record = existing_decision(decision_root, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision to rule against"}
        async with semaphore:
            # Inside the bound, for the reason create_recourse is: this copies a contest
            # directory that itself contains a copy of a decision, and running that
            # unbounded would start every copy at once.
            writer = await asyncio.to_thread(
                RunWriter.create_rerule,
                root=contest_dir(root, cell, challenger) / "runs",
                source_dir=source, item=record.item, sides=record.sides,
                client_config=client_config, condition=cell.condition,
            )
        writer.manifest_update(cell_id=cell.cell_id, challenger_model=challenger,
                               recourse_form=config.recourse_form)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    ruling = await _rule_by_judge(record, challenge, config, client)
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s rerule failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        # Writes ruling.json and re-renders both documents, so the copied record and the
        # new ruling are one document rather than a directory a reader has to assemble.
        writer.record_ruling(ruling)
        writer.finish("completed", totals=aggregate_calls(writer.dir / "calls.jsonl"))
        return {"cell_id": cell.cell_id, "status": "completed",
                "was": writer.rerule_of_form, "now": ruling.form,
                "changed": ruling.changed_the_decision}

    return await _bounded([lambda c=c: rerule(c) for c in cells],
                          client_config.max_runs_in_flight)


async def run_stage_agreement(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    grading: GradingConfig, client_config: ClientConfig, api_key: str,
    decision_root: Path | None = None,
) -> list[dict[str, Any]]:
    """The line-vs-prose instrument, one grader call per readable contest.

    Every contest whose decision line parsed, contesting **and** declining alike: a
    decline whose prose argues the verdict was wrong is as much a mismatch as a contest
    whose prose agrees with it, and measuring only one direction would make the
    instrument agree with the column it is checking. ``unclear`` contests are skipped
    because there is no line to compare the prose against.

    The calls carry ``role="agreement"``, which ``accounting.OFF_PATH_ROLES`` keeps out
    of every decision-path total.

    ``decision_root`` is where the DECISIONS live and defaults to ``root``. They differ
    when a spec sets ``decisions_from``: the contest then reads a tree it never writes
    to — the sweep's 5,724 decisions are re-contested under a new protocol without
    regenerating one of them, and without an overwritten ``experiment.json`` or an
    ambiguous append to the source's ``cells.jsonl``.
    """
    decisions = decision_root or root
    challenger = config.challenger_model_for()
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def measure(cell: Cell) -> dict[str, Any]:
        directory = existing_contest(root, cell, challenger)
        if directory is None:
            return {"cell_id": cell.cell_id, "status": "skipped", "reason": "no contest"}
        if (directory / "agreement.json").is_file():
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already measured"}
        challenge = Challenge.from_dict(
            json.loads((directory / "challenge.json").read_text()))
        if challenge.placeholder:
            # Nothing to read. The placeholder is one fixed text on every cell, written
            # by no model: its prose cannot disagree with its own decision line, and a
            # grader call per cell would buy 1,148 identical readings of a constant.
            # Recorded rather than silently absent, on the rule this stage exists to
            # serve — "not measured" and "measured and agreed" are different facts.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "not measured: placeholder"}
        if challenge.stance not in ("contests", "declined"):
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": f"stance is {challenge.stance}; no line to compare"}
        record = existing_decision(decisions, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision"}
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=_sink_to(directory / "calls.jsonl"),
                                        semaphore=semaphore) as client:
                agreement = await judge_prose_stance(
                    challenge, decision_verdict=record.verdict.verdict,
                    config=config, grading=grading, client=client,
                )
        except Exception as error:
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        (directory / "agreement.json").write_text(
            json.dumps(agreement.to_dict(), indent=2), encoding="utf-8")
        return {"cell_id": cell.cell_id, "status": "completed",
                "line": agreement.line_word, "prose": agreement.prose_stance,
                "agrees": agreement.agrees,
                "phantom": agreement.phantom_contest}

    return await _bounded([lambda c=c: measure(c) for c in cells],
                          client_config.max_concurrency)


async def run_stage_ruling_agreement(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    grading: GradingConfig, client_config: ClientConfig, api_key: str,
) -> list[dict[str, Any]]:
    """The ruling's line-vs-prose instrument, one grader call per recorded ruling.

    Every contest that has a ``ruling.json``, whatever form it is. The three forms are
    three different instruments and the point of measuring is to compare them: the sweep
    and the re-contest wrote 1,586 rulings under the relative ``Ruling:`` line whose
    reliability the re-contest's hand check put at 4 in 12 on FLAWED parents, and
    ``rerule`` writes new ones under the absolute conclusion that replaced it. Both are
    read by the same reader, at temperature 0, and ``ruling_agreement.json`` records the
    form beside the reading so the comparison is in the record rather than in a script.

    It takes no ``decision_root``: everything it needs — the judge's prose, the verdict
    the line amounted to, the parent verdict — is in ``ruling.json``. That is also what
    makes it re-runnable over any finished tree for nothing but the grader's cents.

    The calls carry ``role="ruling_reader"``, which ``accounting.OFF_PATH_ROLES`` keeps
    out of every decision-path total. Here that rule bites harder than it does for the
    challenger's probe: the thing being measured is the decision path's last step, and a
    reader billed to that step would be measuring itself.
    """
    challenger = config.challenger_model_for()
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def measure(cell: Cell) -> dict[str, Any]:
        directory = existing_contest(root, cell, challenger)
        if directory is None:
            return {"cell_id": cell.cell_id, "status": "skipped", "reason": "no contest"}
        ruling_path = directory / "ruling.json"
        if not ruling_path.is_file():
            # No ruling was sought because nothing was objected to. There is no line to
            # check, which is a different fact from a line that checked out.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no ruling to read"}
        if (directory / "ruling_agreement.json").is_file():
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already measured"}
        ruling = Ruling.from_dict(json.loads(ruling_path.read_text()))
        if not ruling.reasoning.strip():
            # A judge that answered before explaining. Nothing to read, and a reading of
            # an empty string would be a NEITHER that looked like a measurement.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "the ruling recorded no reasoning to read"}
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=_sink_to(directory / "calls.jsonl"),
                                        semaphore=semaphore) as client:
                reading = await judge_ruling_prose(
                    ruling, config=config, grading=grading, client=client)
        except Exception as error:
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        (directory / "ruling_agreement.json").write_text(
            json.dumps(reading.to_dict(), indent=2), encoding="utf-8")
        return {"cell_id": cell.cell_id, "status": "completed",
                "line": reading.line_conclusion, "prose": reading.prose_conclusion,
                "mismatch": reading.mismatch, "form": ruling.form}

    return await _bounded([lambda c=c: measure(c) for c in cells],
                          client_config.max_concurrency)


async def run_stage_grade(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    grading: GradingConfig, client_config: ClientConfig, api_key: str,
    decision_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Concurrent against a bounded fleet. exp1's equivalent was a serial await loop
    whose semaphore could never be contended.

    ``decision_root`` is where the DECISIONS live and defaults to ``root``. They differ
    when a spec sets ``decisions_from``: the contest then reads a tree it never writes
    to — the sweep's 5,724 decisions are re-contested under a new protocol without
    regenerating one of them, and without an overwritten ``experiment.json`` or an
    ambiguous append to the source's ``cells.jsonl``.
    """
    decisions = decision_root or root
    challenger = config.challenger_model_for()
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def grade(cell: Cell) -> dict[str, Any]:
        directory = existing_contest(root, cell, challenger)
        if directory is None:
            return {"cell_id": cell.cell_id, "status": "skipped", "reason": "no contest"}
        if (directory / "grade.json").is_file():
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already graded"}
        challenge = Challenge.from_dict(
            json.loads((directory / "challenge.json").read_text()))
        if challenge.placeholder:
            # There is nothing to grade. Validity under the judgment grader is a property
            # of the alleged defects against the record, and the placeholder alleges the
            # same content-free omission on every cell — a grade of it would be one
            # answer bought 1,148 times, and whichever way it came out it would be a
            # property of this module's constant rather than of any run. The arm's whole
            # cost is its rulings.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "not graded: placeholder"}
        if challenge.stance != "contests":
            # The gate is the stance, not ``raised``. An objection that agrees with the
            # verdict it objects to is not a detection of anything, and grading it
            # against the recorded flaw would score agreement as contestability — which
            # is the pilot's defect, in the one place it would have been priced.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": f"stance is {challenge.stance}, not contests"}
        record = existing_decision(decisions, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision to grade against"}
        # The MODE is read off the challenge, never off the config. A tree can hold
        # objections this invocation's spec did not write — `decisions_from` trees are
        # re-graded, and a mixed tree would otherwise be graded by whatever spec ran
        # last, scoring a judgment audit against a flaw annotation or the reverse.
        judgment_mode = challenge.arm == JUDGMENT_VARIANT
        if judgment_mode:
            # NONE of the three gates below applies. Validity here is a property of the
            # objection against the record — is the alleged contradiction, misstatement
            # or omission really there — so it needs no recorded flaw, is defined on
            # sound items, and is defined on decisions that were CORRECT: a judgment
            # that misquotes the record is defective whichever verdict it reached, and
            # calling that a false alarm would be scoring the wrong thing. Every cell
            # whose stance is `contests` is graded (DESIGN.md, `## Judgment-challenge`).
            try:
                async with OpenRouterClient(api_key, client_config,
                                            sink=_sink_to(directory / "calls.jsonl"),
                                            semaphore=semaphore) as client:
                    grade_result = await grade_objection(
                        cell.case, challenge.text, config=config, grading=grading,
                        client=client, mode="judgment",
                        # The same text the challenger was shown, so its quotes can be
                        # looked for where it took them from.
                        record=record.challenger_view().body,
                        judgment=record.decision_grounds,
                        decision_verdict=record.verdict.verdict,
                        defects=challenge.defects,
                    )
            except NotGradable as error:
                return {"cell_id": cell.cell_id, "status": "skipped",
                        "reason": str(error)}
            except Exception as error:
                return {"cell_id": cell.cell_id, "status": "failed",
                        "error": f"{type(error).__name__}: {error}"}
            (directory / "grade.json").write_text(
                json.dumps(grade_result.to_dict(), indent=2), encoding="utf-8")
            return {"cell_id": cell.cell_id, "status": "completed",
                    "mode": "judgment", "valid": grade_result.valid,
                    "defects": len(grade_result.defects),
                    "line_mismatch": grade_result.line_mismatch}
        if not cell.case.item.gold_flawed or cell.case.flaw is None:
            # A false positive: the challenger objected to a sound solution. Its
            # revision rate is reported; its validity is undefined by design.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "sound item — validity undefined"}
        if cell.case.flaw.annotation_quality == "none":
            # Nothing recorded to grade against at all.
            #
            # Note what is NOT skipped here: a "location_only" annotation (gpqa, 382
            # items) records where the flaw is, which is exactly what the *where* bar
            # asks. Skipping those would drop a fifth of the corpus out of the detection
            # row of the funnel, not just out of the validity row. The grader is told
            # the second bar cannot be scored and grade_objection clamps it to False.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "annotation records nothing to grade against"}
        if record.verdict.correct:
            # The valid-objection rate is conditioned on the decision being wrong
            # (DESIGN.md: "P(valid objection | initially incorrect)"). An objection to a
            # decision that was right is a false alarm, and grading it against the
            # recorded flaw measures nothing the analysis reads.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "decision was correct — off-metric"}
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=_sink_to(directory / "calls.jsonl"),
                                        semaphore=semaphore) as client:
                grade_result = await grade_objection(
                    cell.case, challenge.text, config=config, grading=grading,
                    client=client,
                )
        except NotGradable as error:
            return {"cell_id": cell.cell_id, "status": "skipped", "reason": str(error)}
        except Exception as error:
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        (directory / "grade.json").write_text(
            json.dumps(grade_result.to_dict(), indent=2), encoding="utf-8")
        return {"cell_id": cell.cell_id, "status": "completed",
                "valid": grade_result.valid}

    return await _bounded([lambda c=c: grade(c) for c in cells],
                          client_config.max_concurrency)


def _sink_to(path: Path):
    lock = asyncio.Lock()

    async def sink(record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)

        def append() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        async with lock:
            await asyncio.to_thread(append)

    return sink


# --------------------------------------------------------------------------- #
# the index
# --------------------------------------------------------------------------- #


def build_index(cells: Sequence[Cell], *, root: Path,
                challenger_model: str,
                decision_root: Path | None = None) -> list[dict[str, Any]]:
    """One flat row per cell, joining every stage's artifact.

    A missing stage leaves nulls rather than dropping the row: "not yet graded" and
    "graded as a miss" are different facts and the analysis must be able to tell them
    apart.

    ``decision_root`` is where the DECISIONS live and defaults to ``root``. They differ
    when a spec sets ``decisions_from``: the contest then reads a tree it never writes
    to — the sweep's 5,724 decisions are re-contested under a new protocol without
    regenerating one of them, and without an overwritten ``experiment.json`` or an
    ambiguous append to the source's ``cells.jsonl``.
    """
    decisions = decision_root or root
    rows = []
    for cell in cells:
        record = existing_decision(decisions, cell)
        if record is None:
            continue
        item = cell.case.item
        row: dict[str, Any] = {
            "cell_id": cell.cell_id, "item_id": item.item_id, "row_id": item.row_id,
            "subset": item.subset, "label_basis": item.label_basis,
            "label_reliable": item.label_reliable, "condition": cell.condition,
            "gold_flawed": item.gold_flawed,
            "gradable": cell.case.gradable,
            "verdict": record.verdict.verdict,
            "initially_correct": record.verdict.correct,
            "initially_incorrect": (None if record.verdict.correct is None
                                    else not record.verdict.correct),
            "decision_record_words": _record_words(record),
        }
        usage = aggregate_calls(record.directory / "calls.jsonl")
        row["decision_cost_usd"] = usage["decision_path"]["cost_usd"]
        row["decision_completion_tokens"] = usage["decision_path"]["completion_tokens"]

        contest = existing_contest(root, cell, challenger_model)
        if contest is not None:
            challenge = Challenge.from_dict(
                json.loads((contest / "challenge.json").read_text()))
            # ``challenge_raised`` is the funnel's detection column, and since
            # 2026-08-25 it means the stance, not the word the model wrote. The pilot
            # measured 51 "raised" objections of which roughly 46 agreed with the
            # verdict they objected to; counting those as detections is counting
            # agreement as contestability. The other three stances get their own
            # columns so nothing is silently folded into "did not object".
            # WHICH challenger wrote it. A neutral raise rate and a partisan one are
            # not the same quantity, and without this column an index that pooled two
            # runs would read as one population.
            #
            # `challenge.variant`, NOT `challenge.arm`. The two differ for the two
            # controls of 2026-08-28: both carry `arm = "judgment"` so the materiality
            # ruling prompt applies to them, and this column is what says which of the
            # three actually wrote the objection. A specious arm pooled with the real
            # audit under one "judgment" label would put deliberately-invalid objections
            # into the valid-objection rate, and a placeholder pooled with either would
            # put a constant into a measurement.
            row["challenge_arm"] = challenge.variant
            # The two control flags, as their own columns rather than only encoded in
            # the arm name, so a derivation can filter on a boolean it cannot misspell.
            # Written on every judgment-family row (False included): here "measured and
            # false" is the useful fact, since the whole 2×3 design turns on which arm a
            # row belongs to.
            if challenge.arm == JUDGMENT_VARIANT:
                row["challenge_specious"] = challenge.specious
                row["challenge_placeholder"] = challenge.placeholder
                # How much was alleged, and how much of it was built on a quotation the
                # judgment does not contain. Written only under the judgment arm, on the
                # rule the graded columns follow: a 0 on a neutral row would read as "it
                # alleged nothing" when the truth is that nobody asked it to allege
                # anything. `challenge_defects_misattributed_n` counts DEFECTS whose
                # quote check failed, not quotes — one defect can carry two — and it is
                # the numerator of the `misattributed_quote` rate in the analysis.
                row["challenge_defects_n"] = len(challenge.defects)
                row["challenge_defects_misattributed_n"] = sum(
                    1 for defect in challenge.defects
                    if defect.get("quote_in_judgment") is False)
            row["challenge_stance"] = challenge.stance
            row["challenge_raised"] = challenge.stance == "contests"
            row["challenge_agreed"] = challenge.stance == "agrees"
            row["challenge_declined"] = challenge.stance == "declined"
            row["challenge_unclear"] = challenge.stance == "unclear"
            row["challenge_claimed_verdict"] = challenge.claimed_verdict
            row["challenge_contradictory"] = challenge.contradictory
            agreement_path = contest / "agreement.json"
            if agreement_path.is_file():
                # The instrument that keeps `challenge_raised` falsifiable. Absent
                # rather than False when the stage has not run, so "not measured" and
                # "measured and agreed" stay different facts — the same rule the graded
                # columns follow.
                agreement = json.loads(agreement_path.read_text())
                row["prose_stance"] = agreement["prose_stance"]
                row["line_prose_agree"] = agreement["agrees"]
                row["phantom_contest"] = agreement["phantom_contest"]
            ruling_path = contest / "ruling.json"
            if ruling_path.is_file():
                ruling = json.loads(ruling_path.read_text())
                row["ruling_form"] = ruling.get("form")
                # WHICH PROMPT ruled, not which form the answer took. Both prompts
                # produce `stated_conclusion`, so without this column a materiality
                # ruling and an object-level one are the same row. Defaulted here as
                # well as on the dataclass, because the trees already on disk hold
                # `ruling.json` files written before the field existed.
                row["ruling_prompt_form"] = ruling.get("prompt_form", "object_level")
                row["changed_the_decision"] = ruling.get("changed_the_decision")
                row["final_correct"] = ruling.get("correct")
                reading_path = contest / "ruling_agreement.json"
                if reading_path.is_file():
                    # The instrument that keeps `changed_the_decision` falsifiable, on
                    # the same rule as the agreement columns above: absent rather than
                    # False when the stage has not run, so "not measured" and "measured
                    # and consistent" stay different facts.
                    reading = json.loads(reading_path.read_text())
                    row["ruling_prose_conclusion"] = reading["prose_conclusion"]
                    row["ruling_line_mismatch"] = reading["mismatch"]
            else:
                # No ruling was sought because nothing was objected to. Not-revised is
                # the right reading; "never contested" is preserved by challenge_raised.
                row["changed_the_decision"] = False
                row["final_correct"] = record.verdict.correct
            comprehension_path = contest / "comprehension.json"
            if comprehension_path.is_file():
                row["comprehension"] = json.loads(
                    comprehension_path.read_text())["score"]
            grade_path = contest / "grade.json"
            if grade_path.is_file():
                grade = json.loads(grade_path.read_text())
                # WHICH grader wrote it. `grade_valid` means "found the recorded flaw"
                # under the flaw grader and "alleged a defect that is really in the
                # record" under the judgment one — two different claims over two
                # different denominators, and a column that did not say which would let
                # them be pooled. Absent `mode` means the flaw grader: every grade.json
                # written before 2026-08-27 was one.
                row["grade_mode"] = grade.get("mode", "flaw")
                row["grade_valid"] = grade["valid"]
                if row["grade_mode"] == "judgment":
                    row["grade_defects_n"] = grade.get("defects_n")
                    row["grade_defects_valid_n"] = grade.get("defects_valid_n")
                    # The grader's summary line against its own per-defect rulings —
                    # the same kind of instrument as `ruling_line_mismatch`, one layer
                    # further out, and the bound on every judgment-mode rate.
                    row["grade_line_mismatch"] = grade.get("line_mismatch")
                else:
                    row["identified_flaw"] = grade["identified_flaw"]
                    row["characterises_the_flaw"] = grade["characterises_the_flaw"]
        rows.append(row)
    return rows


def _record_words(record) -> int | None:
    """How much record a challenger actually had to read.

    The quantity the token-balance check needs — not completion tokens, which measure
    the wire rather than the document.
    """
    if record.transcript is not None:
        return sum(t.word_count for t in record.transcript.all_turns())
    if record.trace is not None:
        return sum(s.word_count for s in record.trace.all_steps())
    return None
