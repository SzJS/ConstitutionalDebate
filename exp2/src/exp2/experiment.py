"""The staged batch harness.

Stages: ``decide`` → ``contest`` → ``grade`` → ``analyse``.

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
from .config import ClientConfig, DebateConfig, GradingConfig
from .grading import NotGradable, grade_objection
from .persistence import RunWriter, load_flaw, load_run_record
from .recourse import run_recourse
from .types import Case, Challenge, Item, make_sides

log = logging.getLogger(__name__)

STAGES: tuple[str, ...] = ("decide", "contest", "grade", "analyse")


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
    client_config: ClientConfig, api_key: str,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def decide(cell: Cell) -> dict[str, Any]:
        if existing_decision(root, cell) is not None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already decided"}
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
) -> list[dict[str, Any]]:
    """Challenge, comprehension probe, and ruling — one coroutine, one resume key.

    They share a stage because the comprehension probe is asked inside the challenger's
    live conversation. Splitting it out would mean replaying that conversation from disk
    to ask one question, and a replay can diverge from what was actually sent.
    """
    challenger = config.challenger_model_for()
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def contest(cell: Cell) -> dict[str, Any]:
        if existing_contest(root, cell, challenger) is not None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already contested"}
        record = existing_decision(root, cell)
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
        writer.manifest_update(cell_id=cell.cell_id, challenger_model=challenger)
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


async def run_stage_grade(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    grading: GradingConfig, client_config: ClientConfig, api_key: str,
) -> list[dict[str, Any]]:
    """Concurrent against a bounded fleet. exp1's equivalent was a serial await loop
    whose semaphore could never be contended."""
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
        if challenge.stance != "contests":
            # The gate is the stance, not ``raised``. An objection that agrees with the
            # verdict it objects to is not a detection of anything, and grading it
            # against the recorded flaw would score agreement as contestability — which
            # is the pilot's defect, in the one place it would have been priced.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": f"stance is {challenge.stance}, not contests"}
        record = existing_decision(root, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision to grade against"}
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
                challenger_model: str) -> list[dict[str, Any]]:
    """One flat row per cell, joining every stage's artifact.

    A missing stage leaves nulls rather than dropping the row: "not yet graded" and
    "graded as a miss" are different facts and the analysis must be able to tell them
    apart.
    """
    rows = []
    for cell in cells:
        record = existing_decision(root, cell)
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
            row["challenge_stance"] = challenge.stance
            row["challenge_raised"] = challenge.stance == "contests"
            row["challenge_agreed"] = challenge.stance == "agrees"
            row["challenge_declined"] = challenge.stance == "declined"
            row["challenge_unclear"] = challenge.stance == "unclear"
            row["challenge_claimed_verdict"] = challenge.claimed_verdict
            row["challenge_contradictory"] = challenge.contradictory
            ruling_path = contest / "ruling.json"
            if ruling_path.is_file():
                ruling = json.loads(ruling_path.read_text())
                row["ruling_form"] = ruling.get("form")
                row["changed_the_decision"] = ruling.get("changed_the_decision")
                row["final_correct"] = ruling.get("correct")
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
                row["identified_flaw"] = grade["identified_flaw"]
                row["characterises_the_flaw"] = grade["characterises_the_flaw"]
                row["grade_valid"] = grade["valid"]
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
