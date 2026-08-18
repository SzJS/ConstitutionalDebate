"""The batch harness: a grid of cells, run to disk, resumable.

A *cell* is one combination of the things the experiment varies —
``(case, arm, condition, challenger, repeat)`` — and it moves through stages:

    decide  ->  contest  ->  grade
     |            |            |
     |            |            +-- off the decision path, re-runnable for free
     |            +-- one contest per challenger, over the SAME decision
     +-- paid once per (case, arm, condition)

Splitting decide from contest is the whole economy of the thing. A decision is
expensive and a challenge is cheap, so the challenger ladder — which is the
experiment's actual variable — multiplies only the cheap half. It also lets the
decisions be inspected before anything is spent contesting them, which is how
the error and correct strata get separated without paying for both.

Resumability derives from **disk**, not from the ledger: a stage is done iff the
record it should have written loads. The ledger is a log of what happened, and a
log that disagrees with the artifacts is a log that is wrong.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable

from .accounting import aggregate_calls, split_calls
from .client import ChatClient, OpenRouterClient
from .config import ClientConfig, DebateConfig
from .arms import DECIDERS
from .engine import DebateFailure, TruncatedOutputError
from .persistence import RunWriter, _write_json, load_run_record
from .prompts import PROFILES, MalformedOutputError, TaskProfile
from .types import Case, ErrorSpec, make_seating

log = logging.getLogger(__name__)

# Failures that belong to one cell and must never take down the experiment.
CELL_FATAL = (DebateFailure, TruncatedOutputError, MalformedOutputError)

# The arms this harness can run, taken from the one place an arm name maps to a
# procedure rather than restated here where the two could drift.
#
# An unknown arm is refused rather than run as a debate. This module previously
# accepted any ``arm`` string, stamped it into the manifest and called
# ``run_debate`` regardless — so a "single" cell produced a full two-debater
# transcript labelled as a single-agent decision. Nothing downstream would have
# caught it: the record is well-formed, the verdict is real, and the analysis
# would have compared debate against debate and reported it as an arm difference.
# Failing loudly on an unimplemented arm is the whole guard.
IMPLEMENTED_ARMS: frozenset[str] = frozenset(DECIDERS)


class UnknownArmError(ValueError):
    """A cell names a decision procedure this harness cannot run."""


@dataclass(frozen=True)
class Cell:
    """One point in the experiment grid.

    ``cell_id`` is deterministic and readable so a directory can be found by
    hand, and so a re-run lands on the same path and can be skipped.
    """

    case: Case
    arm: str
    # "matched" | "unconstrained" -- and currently **inert**. It reaches
    # ``cell_id``, the manifest and ``build_index``'s ``condition`` column, and
    # nothing branches on it: the word-limit ablation it names is already
    # expressed by ``DebateConfig.word_limit`` / ``word_limit_by_profile``, and
    # the error/correct stratum the module docstring describes is deferred (see
    # ``deferred.md``). Two conditions here would multiply the grid and the cost
    # while producing byte-identical decisions.
    condition: str
    repeat: int = 0

    @property
    def cell_id(self) -> str:
        return f"{self.case.task.task_id}__{self.arm}__{self.condition}__r{self.repeat}"

    def dir(self, root: Path) -> Path:
        return Path(root) / "cells" / self.cell_id


@dataclass
class DecisionOutcome:
    """What happened when a cell's decision was attempted."""

    cell_id: str
    status: str  # "completed" | "failed" | "skipped"
    run_dir: Path | None = None
    attempts: int = 0
    failures: list[str] = field(default_factory=list)
    correct: bool | None = None
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "stage": "decide",
            "status": self.status,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "attempts": self.attempts,
            "failures": self.failures,
            "correct": self.correct,
            "cost_usd": round(self.cost_usd, 6),
        }


def build_grid(
    cases: list[Case],
    *,
    arms: list[str],
    conditions: list[str],
    repeats: int = 1,
) -> list[Cell]:
    """The full cross product, in a stable order.

    Refuses duplicate task ids. A cell directory is named from the task id, so
    two cases sharing one would write into the same place: the second decision
    would resume from the first, and the experiment would silently report one
    case twice while never running the other. That is a corrupted result rather
    than a crash, so it is caught here where it is cheap.
    """
    unknown = sorted(set(arms) - IMPLEMENTED_ARMS)
    if unknown:
        # Caught here so ``--dry-run`` reports it, before anything is spent.
        raise UnknownArmError(
            f"spec names arms this harness cannot run: {unknown}; implemented "
            f"arms are {sorted(IMPLEMENTED_ARMS)}"
        )

    seen: dict[str, int] = {}
    for case in cases:
        seen[case.task.task_id] = seen.get(case.task.task_id, 0) + 1
    duplicates = sorted(k for k, n in seen.items() if n > 1)
    if duplicates:
        raise ValueError(
            f"case set has duplicate task_ids, which would collide in one cell "
            f"directory: {duplicates[:5]}"
            + (f" (and {len(duplicates) - 5} more)" if len(duplicates) > 5 else "")
        )
    return [
        Cell(case=case, arm=arm, condition=condition, repeat=repeat)
        for case in cases
        for arm in arms
        for condition in conditions
        for repeat in range(repeats)
    ]


def existing_decision(cell: Cell, root: Path):
    """The completed decision for this cell, if one is already on disk.

    Derived from the artifacts rather than from the ledger, so a run interrupted
    mid-write resumes correctly and a hand-deleted directory is genuinely gone.
    """
    runs = cell.dir(root) / "runs"
    if not runs.is_dir():
        return None
    for candidate in sorted(runs.iterdir(), reverse=True):
        try:
            return load_run_record(candidate)
        except (ValueError, OSError, KeyError):
            continue  # a failed or partial attempt; keep looking
    return None


async def decide_cell(
    cell: Cell,
    *,
    config: DebateConfig,
    client_config: ClientConfig,
    api_key: str,
    root: Path,
    semaphore: asyncio.Semaphore | None = None,
    profile: TaskProfile | None = None,
) -> DecisionOutcome:
    """Produce one decision, retrying the whole run if it fails.

    A retry is a **fresh independent debate**, not a re-attempt of a bad
    response: truncation stays fatal within a run because a truncated argument
    entering the published transcript as though authored would be a false
    statement in the record. Between runs there is no such problem — the failed
    attempt stays on disk, marked failed, and a new one is drawn.

    Every attempt is kept. The discarded ones are evidence about how often the
    protocol fails, which is a reportable rate rather than an embarrassment to
    be tidied away — and since the failures fall on the debater defending the
    weaker case, that rate is not neutral.
    """
    if cell.arm not in IMPLEMENTED_ARMS:
        raise UnknownArmError(
            f"cell {cell.cell_id} names arm {cell.arm!r}, which this harness "
            f"cannot run; implemented arms are {sorted(IMPLEMENTED_ARMS)}. "
            f"Running it as a debate would record a two-debater transcript "
            f"under another arm's label."
        )

    outcome = DecisionOutcome(cell_id=cell.cell_id, status="failed")
    profile = profile or PROFILES["paper"]
    task = cell.case.task
    error = cell.case.error

    for attempt in range(1, config.max_decision_attempts + 1):
        outcome.attempts = attempt
        seating = make_seating(task, config.seed)
        writer = RunWriter.create(
            task=task,
            context=None,
            config=config,
            client_config=client_config,
            seating=seating,
            profile_key=profile.key,
            outputs_root=cell.dir(root),
            error=error,
            arm=cell.arm,
        )
        writer.manifest_update(
            arm=cell.arm, condition=cell.condition, cell_id=cell.cell_id,
            decision_attempt=attempt,
        )
        try:
            async with OpenRouterClient(
                api_key, client_config, sink=writer.record_call, semaphore=semaphore
            ) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    # Dispatch on the cell's arm. Calling run_debate regardless
                    # is what made ``arm`` a decorative manifest field.
                    result = await DECIDERS[cell.arm](
                        task, None, config, seating, client,
                        writer=writer, profile=profile, error=error,
                    )
        except asyncio.CancelledError:
            writer.finish(status="interrupted", error="cancelled")
            raise
        except CELL_FATAL as failure:
            writer.finish(status="failed", error=f"{type(failure).__name__}: {failure}")
            outcome.failures.append(_classify(failure))
            outcome.cost_usd += split_calls(writer.dir / "calls.jsonl")[0].cost_usd
            log.warning(
                "%s attempt %d/%d failed: %s",
                cell.cell_id, attempt, config.max_decision_attempts, _classify(failure),
            )
            continue
        except Exception as failure:  # transport, timeout, anything else
            writer.finish(status="failed", error=f"{type(failure).__name__}: {failure}")
            outcome.failures.append(type(failure).__name__)
            outcome.cost_usd += split_calls(writer.dir / "calls.jsonl")[0].cost_usd
            log.warning("%s attempt %d failed: %r", cell.cell_id, attempt, failure)
            continue

        writer.finish(status="completed")
        outcome.status = "completed"
        outcome.run_dir = writer.dir
        outcome.correct = result.verdict.correct
        outcome.cost_usd += split_calls(writer.dir / "calls.jsonl")[0].cost_usd
        return outcome

    return outcome


def _record_words(document: dict) -> int | None:
    """How much record there is, in words, whichever shape it has.

    ``turns`` for a debate, ``steps`` for a solo arm — the same quantity either
    way: what a challenger has to read. Returns None when neither key is
    present, so a missing document is distinguishable from an empty one.
    """
    for key in ("turns", "steps"):
        if key in document:
            return sum(int(item.get("word_count") or 0) for item in document[key])
    return None


def _classify(failure: BaseException) -> str:
    text = str(failure)
    # Construction failures are matched **first**, and named rather than
    # collapsed into the class name. Rejecting cases whose critique caught the
    # seeded flaw selects against exactly the cases self-critique handles best,
    # so that rate has to be visible in ``decide_summary.json`` rather than
    # inferred.
    #
    # Ordered before the generic checks because they overlap: the drift message
    # reads "55% length change", which the ``"length" in text`` heuristic below
    # would file as a truncation -- burying a construction failure inside an
    # unrelated rate.
    for reason in (
        "critique_caught_the_seeded_flaw",
        "critique_missed_the_injected_error",
        # A steered output that narrated its own steer. Reported rather than
        # collapsed, because it drops the case from that arm and so widens the
        # cross-arm imbalance the analysis has to intersect away.
        "steered_judge_referenced_the_steer",
        "steered_critique_referenced_the_steer",
        "rewrote the solution",
        "no step to inject into",
    ):
        if reason in text:
            return reason.replace(" ", "_")
    if "length" in text or isinstance(failure, TruncatedOutputError):
        return "loop_or_truncation"
    if "malformed" in text:
        return "malformed_after_repair"
    return type(failure).__name__


async def run_stage_decide(
    grid: list[Cell],
    *,
    config: DebateConfig,
    client_config: ClientConfig,
    api_key: str,
    root: Path,
    ledger: Callable[[dict[str, Any]], None] | None = None,
    profile: TaskProfile | None = None,
) -> list[DecisionOutcome]:
    """Decide every cell, bounded and failure-isolated.

    Two separate bounds, because they limit different resources: one semaphore
    shared by every client caps requests in flight across the whole fleet, and a
    second caps how many *cells* are open at once, which is what bounds file
    handles and keeps the logs legible.
    """
    shared = asyncio.Semaphore(client_config.max_concurrency)
    cells_in_flight = asyncio.Semaphore(client_config.max_runs_in_flight)
    outcomes: list[DecisionOutcome] = []

    async def one(cell: Cell) -> DecisionOutcome:
        existing = existing_decision(cell, root)
        if existing is not None:
            log.info("%s already decided; skipping", cell.cell_id)
            return DecisionOutcome(
                cell_id=cell.cell_id, status="skipped", run_dir=existing.dir,
                attempts=0, correct=existing.verdict.correct,
            )
        async with cells_in_flight:
            return await decide_cell(
                cell, config=config, client_config=client_config, api_key=api_key,
                root=root, semaphore=shared, profile=profile,
            )

    results = await asyncio.gather(*(one(c) for c in grid), return_exceptions=True)
    for cell, result in zip(grid, results):
        # Cancellation must stay cancellation, exactly as in _run_round: rewrapping
        # it would stop asyncio.timeout recognising its own.
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            log.error("%s raised %r", cell.cell_id, result)
            result = DecisionOutcome(
                cell_id=cell.cell_id, status="failed",
                failures=[type(result).__name__],
            )
        outcomes.append(result)
        if ledger is not None:
            ledger(result.to_dict())
    return outcomes


def summarise(outcomes: list[DecisionOutcome]) -> dict[str, Any]:
    """The numbers worth printing after a decide stage."""
    decided = [o for o in outcomes if o.status in ("completed", "skipped")]
    retried = [o for o in outcomes if o.attempts > 1]
    incorrect = [o for o in decided if o.correct is False]
    return {
        "cells": len(outcomes),
        "decided": len(decided),
        "failed": sum(1 for o in outcomes if o.status == "failed"),
        "skipped": sum(1 for o in outcomes if o.status == "skipped"),
        "needed_retry": len(retried),
        "initially_incorrect": len(incorrect),
        "initially_correct": sum(1 for o in decided if o.correct is True),
        "cost_usd": round(sum(o.cost_usd for o in outcomes), 6),
        "failure_reasons": _counts(f for o in outcomes for f in o.failures),
    }


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


# --------------------------------------------------------------------------- #
# the stages after decide
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ContestCell:
    """One challenge against one decision.

    The challenger axis multiplies *this* and not the decision: a decision is
    paid once per ``(case, arm, condition)`` and contested by every challenger
    against that same record. That is the whole economy of the decide/challenge
    split — the experiment's actual variable multiplies only the cheap half.
    """

    cell: Cell
    challenger_model: str
    challenge_arm: str

    @property
    def contest_id(self) -> str:
        model = self.challenger_model.replace("/", "-")
        return f"{self.cell.cell_id}__{model}__{self.challenge_arm}"


async def run_stage_challenge(
    grid: list[Cell],
    *,
    challenger_models: list[str],
    challenge_arms: list[str],
    config: DebateConfig,
    client_config: ClientConfig,
    api_key: str,
    root: Path,
    rule: bool = False,
    ledger=None,
) -> list[dict[str, Any]]:
    """Challenge every decided cell, once per challenger and arm.

    ``rule=False`` by default: the headline detection result does not need a
    ruling, so the expensive half is opt-in rather than automatic.
    """
    from .debate import run_recourse
    from .types import Challenge

    shared = asyncio.Semaphore(client_config.max_concurrency)
    in_flight = asyncio.Semaphore(client_config.max_runs_in_flight)
    contests = [
        ContestCell(cell, model, arm)
        for cell in grid
        for model in challenger_models
        for arm in challenge_arms
    ]

    async def one(contest: ContestCell) -> dict[str, Any]:
        parent = existing_decision(contest.cell, root)
        if parent is None:
            return {"contest_id": contest.contest_id, "stage": "challenge",
                    "status": "skipped", "reason": "no decision to contest"}
        contest_root = contest.cell.dir(root) / "contests" / contest.contest_id
        # Resume on the *artifact*, exactly as the decide stage does. The run
        # directory is created before the first call, so testing for it marked a
        # contest that failed on a transport error as permanently done — and it
        # then vanished from the index too, since iter_contest_dirs requires
        # challenge.json. It also made `--stage rule` a no-op after `--stage
        # challenge`, because the challenge had already claimed the directory.
        done = sorted(contest_root.glob("runs/*/challenge.json"))
        if done:
            already_ruled = any(
                (path.parent / "ruling.json").is_file() for path in done
            )
            if not rule or already_ruled:
                return {"contest_id": contest.contest_id, "stage": "challenge",
                        "status": "skipped",
                        "reason": "already ruled" if already_ruled
                                  else "already challenged"}

        cfg = replace(config, challenger_model=contest.challenger_model)
        writer = RunWriter.create_recourse(
            parent=parent, config=cfg, client_config=client_config,
            outputs_root=contest_root,
        )
        writer.manifest_update(
            contest_id=contest.contest_id, cell_id=contest.cell.cell_id,
            challenger_model=contest.challenger_model,
            challenge_arm=contest.challenge_arm,
        )
        async with in_flight:
            try:
                async with OpenRouterClient(
                    api_key, client_config, sink=writer.record_call, semaphore=shared
                ) as client:
                    async with asyncio.timeout(client_config.run_timeout_s):
                        result = await run_recourse(
                            parent,
                            Challenge(text="", origin="generated",
                                      arm=contest.challenge_arm, visibility="public"),
                            cfg, client, writer=writer, rule=rule,
                        )
            except asyncio.CancelledError:
                writer.finish(status="interrupted", error="cancelled")
                raise
            except Exception as error:
                writer.finish(status="failed", error=f"{type(error).__name__}: {error}")
                return {"contest_id": contest.contest_id, "stage": "challenge",
                        "status": "failed", "error": _classify(error)}
        writer.finish(status="completed")
        return {
            "contest_id": contest.contest_id, "stage": "challenge",
            "status": "completed", "run_dir": str(writer.dir),
            "raised": result.challenge.raised,
            "ruled": result.ruling is not None,
        }

    results = await asyncio.gather(*(one(c) for c in contests), return_exceptions=True)
    rows: list[dict[str, Any]] = []
    for contest, result in zip(contests, results):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            log.error("%s raised %r", contest.contest_id, result)
            result = {"contest_id": contest.contest_id, "stage": "challenge",
                      "status": "failed", "error": type(result).__name__}
        rows.append(result)
        if ledger is not None:
            ledger(result)
    return rows


def iter_contest_dirs(root: Path):
    """Every completed contest directory under an experiment, with its cell."""
    cells = Path(root) / "cells"
    if not cells.is_dir():
        return
    for cell_dir in sorted(cells.iterdir()):
        for contest in sorted((cell_dir / "contests").glob("*/runs/*")):
            if (contest / "challenge.json").is_file():
                yield cell_dir, contest


def build_index(root: Path) -> list[dict[str, Any]]:
    """One flat row per contest, joining every stage's artifacts.

    Flat on purpose: the varying columns are repeated on every row so the
    analysis never has to join back, and a row that is missing a stage carries
    nulls rather than being dropped — a challenge that was never graded is a
    fact about coverage, not a row to hide.
    """
    rows: list[dict[str, Any]] = []
    for cell_dir, contest in iter_contest_dirs(Path(root)):
        manifest = _read_json_or(contest / "run.json", {})
        challenge = _read_json_or(contest / "challenge.json", {})
        ruling = _read_json_or(contest / "ruling.json", None)
        grade = _read_json_or(contest / "grade.challenge.json", None)
        validation = _read_json_or(cell_dir / "validation.json", None)
        parent = _read_json_or(contest / "parent" / "verdict.json", {})
        parent_manifest = _read_json_or(contest / "parent" / "run.json", {})
        error = _read_json_or(contest / "parent" / "error.json", {})
        parent_config = _read_json_or(contest / "parent" / "config.json", {})
        usage = aggregate_calls(contest / "parent" / "calls.jsonl")
        document = _read_json_or(contest / "parent" / "transcript.json", {})

        rows.append({
            "cell_id": manifest.get("cell_id"),
            "contest_id": manifest.get("contest_id"),
            "task_id": parent_manifest.get("task_id"),
            "decision_arm": parent_manifest.get("arm"),
            "condition": parent_manifest.get("condition"),
            "challenger_model": manifest.get("challenger_model"),
            "challenge_arm": manifest.get("challenge_arm"),
            # No default. The field went unwritten for so long that
            # ``or "genuine"`` made every row read genuine, so the split that
            # interprets the arms' results was a default rather than a
            # measurement. An unlabelled row is now visibly unlabelled.
            "mechanism": error.get("mechanism") or None,
            "outcome_control": parent_config.get("outcome_control"),
            "gradable": error.get("annotation_quality") == "explanation",
            "initially_correct": parent.get("correct"),
            "challenge_raised": challenge.get("raised"),
            "found_the_flaw": grade.get("found_the_flaw") if grade else None,
            "grade_localisation": grade.get("localisation") if grade else None,
            "grade_valid": grade.get("valid") if grade else None,
            "underspecified": grade.get("underspecified") if grade else None,
            "ruling": ruling.get("ruling") if ruling else None,
            "changed": ruling.get("changed_the_decision") if ruling else None,
            "final_correct": ruling.get("correct") if ruling else parent.get("correct"),
            "validated": validation.get("usable") if validation else None,
            "decision_completion_tokens":
                usage["decision_path"].get("completion_tokens"),
            # What the challenger actually reads. Under outcome control the
            # wire figure above is zero for a constructed arm, so balancing on
            # it alone would report the arms as matched for a reason that has
            # nothing to do with how much record there is to attack.
            "decision_record_words": _record_words(document),
            "decision_cost_usd": usage["decision_path"].get("cost_usd"),
        })
    return rows


def _read_json_or(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


async def run_stage_grade(
    *,
    config: DebateConfig,
    grading,
    client_config: ClientConfig,
    api_key: str,
    root: Path,
    ledger=None,
) -> list[dict[str, Any]]:
    """Grade every raised challenge against its case's annotation.

    Off the decision path: it appends to the contest's own wire log with
    ``role="grader"``, which the accounting excludes from decision totals, and
    it is re-runnable over finished directories without re-spending a decision.

    Skips declines (nothing to grade) and location-only annotations (nothing to
    check a characterisation against). Both are recorded as skipped rather than
    silently absent, because coverage is itself a number the write-up needs.
    """
    from .grading import grade_objection
    from .persistence import load_error_spec
    from .types import Seating, Task

    shared = asyncio.Semaphore(client_config.max_concurrency)
    rows: list[dict[str, Any]] = []

    for _cell_dir, contest in iter_contest_dirs(Path(root)):
        target = contest / "grade.challenge.json"
        if target.is_file():
            rows.append({"contest_id": contest.name, "stage": "grade",
                         "status": "skipped", "reason": "already graded"})
            continue
        challenge = _read_json_or(contest / "challenge.json", {})
        if not challenge.get("raised"):
            rows.append({"contest_id": contest.name, "stage": "grade",
                         "status": "skipped", "reason": "no challenge raised"})
            continue
        error = load_error_spec(contest / "parent")
        if error is None:
            rows.append({"contest_id": contest.name, "stage": "grade",
                         "status": "skipped", "reason": "no annotation"})
            continue

        # Inside the guarded section: a corrupt task.json or seating.json must
        # cost this measurement, not abort the stage. "A grader failure costs a
        # measurement rather than a run" is the module's own rule.
        try:
            task = Task.from_dict(_read_json_or(contest / "parent" / "task.json", {}))
            seat = _read_json_or(contest / "parent" / "seating.json", {})
            seating = Seating(
                alice_answer=seat["alice_answer"], bob_answer=seat["bob_answer"],
                choice_order=tuple(seat["choice_order"]),
                seed_material=seat["seed_material"],
                swap_debater_models=seat.get("swap_debater_models", False),
            )
            verdict = _read_json_or(contest / "parent" / "verdict.json", {})
            if "answer_index" not in verdict:
                raise KeyError("verdict.json has no answer_index")
        except (KeyError, TypeError, ValueError) as failure:
            rows.append({"contest_id": contest.name, "stage": "grade",
                         "status": "failed", "error": f"unreadable parent: {failure}"})
            continue

        writer_sink = _appending_sink(contest / "calls.jsonl")
        try:
            async with OpenRouterClient(
                api_key, client_config, sink=writer_sink, semaphore=shared
            ) as client:
                grade = await grade_objection(
                    task=task, seating=seating, subject_text=challenge.get("text", ""),
                    subject_kind="challenge", error=error,
                    decision_answer_index=verdict["answer_index"],
                    config=config, grading=grading, client=client,
                )
        except Exception as error_:  # a grading failure costs a measurement, not a run
            rows.append({"contest_id": contest.name, "stage": "grade",
                         "status": "failed", "error": type(error_).__name__})
            continue
        _write_json(target, grade.to_dict())
        rows.append({"contest_id": contest.name, "stage": "grade",
                     "status": "completed", "localisation": grade.localisation,
                     "valid": grade.valid})

    if ledger is not None:
        for row in rows:
            ledger(row)
    return rows


def _appending_sink(path: Path):
    """A ``CallSink`` that appends to an existing wire log.

    Grading runs after the writer that owns the directory has finished, so it
    cannot use ``RunWriter.record_call`` — but its calls still belong in the
    same log, tagged with a role the accounting excludes.
    """
    lock = asyncio.Lock()

    async def sink(record: dict[str, Any]) -> None:
        async with lock:
            def append() -> None:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            await asyncio.to_thread(append)

    return sink


async def run_stage_validate(
    *,
    config: DebateConfig,
    grading,
    client_config: ClientConfig,
    api_key: str,
    root: Path,
    ledger=None,
) -> list[dict[str, Any]]:
    """Check each constructed case came out as designed, across all its arms.

    One call per case covering every arm, not one per arm: the cross-arm
    question can only be answered by seeing them together, and it is also
    cheaper by the number of arms.

    Failures are **flagged, not dropped**. A high exclusion rate is itself a
    finding about how hard it is to construct matched error cases, so the count
    and the reasons are reported beside the funnel rather than quietly shrinking
    the denominator.
    """
    from .grading import validate_case
    from .persistence import load_error_spec
    from .types import Task

    shared = asyncio.Semaphore(client_config.max_concurrency)
    cells = Path(root) / "cells"
    if not cells.is_dir():
        return []

    # Group cell directories by the case they decided, so one call sees every arm.
    by_case: dict[str, list[Path]] = {}
    for cell_dir in sorted(cells.iterdir()):
        task_id = cell_dir.name.split("__")[0]
        by_case.setdefault(task_id, []).append(cell_dir)

    rows: list[dict[str, Any]] = []
    for case_id, dirs in by_case.items():
        target = dirs[0] / "validation.json"
        if target.is_file():
            rows.append({"case_id": case_id, "stage": "validate",
                         "status": "skipped", "reason": "already validated"})
            continue

        records: dict[str, str] = {}
        error = None
        task = None
        for cell_dir in dirs:
            for run in sorted((cell_dir / "runs").glob("*")):
                document = run / "transcript.md"
                manifest = _read_json_or(run / "run.json", {})
                if document.is_file() and manifest.get("status") == "completed":
                    records[manifest.get("arm", cell_dir.name)] = document.read_text(
                        encoding="utf-8"
                    )[:12000]
                    error = error or load_error_spec(run)
                    task = task or Task.from_dict(
                        _read_json_or(run / "task.json", {})
                    )
        if not records or error is None or task is None:
            rows.append({"case_id": case_id, "stage": "validate",
                         "status": "skipped", "reason": "nothing decided to validate"})
            continue

        try:
            async with OpenRouterClient(
                api_key, client_config, sink=_appending_sink(dirs[0] / "calls.jsonl"),
                semaphore=shared,
            ) as client:
                validation = await validate_case(
                    case_id=case_id, task=task, records=records, error=error,
                    config=config, grading=grading, client=client,
                )
        except Exception as failure:
            rows.append({"case_id": case_id, "stage": "validate",
                         "status": "failed", "error": type(failure).__name__})
            continue

        # Written beside every cell for this case, so build_index finds it
        # whichever arm's directory it walks.
        for cell_dir in dirs:
            _write_json(cell_dir / "validation.json", validation.to_dict())
        rows.append({"case_id": case_id, "stage": "validate", "status": "completed",
                     "usable": validation.usable, "note": validation.note})

    if ledger is not None:
        for row in rows:
            ledger(row)
    return rows
