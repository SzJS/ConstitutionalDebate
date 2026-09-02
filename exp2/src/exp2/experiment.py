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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from .accounting import aggregate_calls, split_calls
from .arms import CONDITIONS, DECIDERS
from .client import OpenRouterClient
from .config import (
    FINDINGS_VARIANT,
    JUDGMENT_VARIANT,
    PLACEHOLDER_VARIANT,
    ClientConfig,
    DebateConfig,
    GradingConfig,
)
from .debate import _judge, _run_round
from .engine import DebateFailure
from .grading import NotGradable, grade_objection
from .persistence import (
    RunWriter,
    load_findings,
    load_flaw,
    load_recourse_transcript,
    load_run_record,
)
from .prompts import (
    contest_lines_from_text,
    count_kind_mismatched_lines,
    objection_defects_fabricated_n,
    objection_fabrication_ok,
    strip_ruling_prose,
)
from .recourse import (
    _SAME_DEBATE_KEYS,
    _assert_same_debate,
    _rule_by_judge,
    hear_exchange,
    judge_admissibility,
    judge_prose_stance,
    judge_ruling_prose,
    mechanical_agreement,
    run_recourse,
)
from .types import Case, Challenge, Item, Ruling, Transcript, make_sides

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
#
# ``gatekeeper`` is the M4 ablation of 2026-08-28, POST HOC, and the driver's default
# list omits it too. It belongs to a spec with ``contests_from``: it copies another tree's
# finished objections AND their rulings, and adds one thing — an ``admission.json`` saying
# whether a same-class model finds the objection admissible at all. It re-rules nothing
# and re-writes nothing; what the answer decides is whether the ruling beside it is
# COUNTED, and that decision is made in ``build_index`` and in the derivation.
#
# ``rejudge`` is the same shape one layer up and the driver's default list omits it for
# the same reason. It belongs to a spec with ``transcripts_from``: it judges another
# tree's stored debate transcripts again, under this spec's judge, and writes a FULL
# decision record — so ``decisions_from`` pointed at the tree it writes works with no
# change anywhere downstream, and ``decide`` refuses on such a spec.
STAGES: tuple[str, ...] = (
    "decide", "rejudge", "contest", "rerule", "gatekeeper", "agreement",
    "ruling_agreement", "grade", "analyse",
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


def source_decisions(cells: Sequence[Cell], *,
                     source_root: Path) -> list[tuple[Cell, Path]]:
    """The cells of ``cells`` that a source tree holds a DECIDED run for.

    The population ``rejudge`` will judge, and therefore the number the run's spend is
    approved from: a cell the source never decided has no transcript to re-judge. Read
    off each run's manifest rather than off the source index, so a spec pointed at a
    tree with no index still quotes a true figure — and cheaply, because it opens
    ``run.json`` alone where ``existing_decision`` parses the whole record including a
    multi-kilobyte transcript, and this runs over the grid at every dry-run.

    The same two conditions ``load_run_record`` applies: the newest readable manifest
    says ``completed`` and a ``verdict.json`` is there beside it.
    """
    found: list[tuple[Cell, Path]] = []
    for cell in cells:
        for directory in sorted((cell_dir(source_root, cell) / "runs").glob("*"),
                                reverse=True):
            try:
                manifest = json.loads(
                    (directory / "run.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (manifest.get("status") == "completed"
                    and (directory / "verdict.json").is_file()):
                found.append((cell, directory))
            break
    return found


def _assert_extendable(source, config: DebateConfig, boundary: int) -> None:
    """Refuse a source this spec cannot honestly continue.

    Loud rather than silent in all three cases, because each one produces a record that
    reads as an ordinary result: a solo source has no debaters, a source that is already
    ``n_rounds`` long would be judged with no round added at all — an ordinary re-judge
    wearing arm B's name — and a source argued under other settings would have a turn by
    a different party spliced into a transcript that says all four turns are one debate.
    ``n_rounds`` is exempted from the settings check for the obvious reason: it is the one
    field that has to differ.
    """
    if source.transcript is None:
        raise DebateFailure(
            "extend_rounds continues a DEBATE and this decision was reached by a single "
            "agent working alone; there are no debaters to play another round."
        )
    if boundary >= config.n_rounds:
        raise DebateFailure(
            f"extend_rounds has nothing to add: the stored debate already has "
            f"{boundary} rounds and this spec's n_rounds is {config.n_rounds}. A "
            "judgment made with no round added is an ordinary re-judge, and counting it "
            "as the plain-round arm would put a cell with no extra round into the "
            "comparison the arm exists to make."
        )
    _assert_same_debate(source.config, config,
                        keys=tuple(k for k in _SAME_DEBATE_KEYS if k != "n_rounds"))


async def run_stage_rejudge(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    client_config: ClientConfig, api_key: str, transcript_root: Path,
    retry_failed: bool = False,
) -> list[dict[str, Any]]:
    """Judge another tree's stored debate transcripts again, into this tree.

    The debates are not re-run — they are the sweep's, they cost $32, and re-drawing
    them would change the population as well as the verdict. So each source decision
    directory is COPIED here minus its verdict, its wire log and its two documents, and
    one new call is made: ``debate._judge``, the *same function the decide stage calls*,
    over the stored transcript, under this spec's ``judge_model``, ``judge_temperature``,
    ``judge_cot``, ``reasoning_effort`` and ``max_tokens``. Building the messages by
    hand here instead would be a second copy of the judge prompt that could drift from
    the one every decided cell was judged under, and the comparison this stage exists to
    make — a different judge, the same debates — would quietly become a comparison of
    two prompts.

    **The sides are the source's and are never re-drawn.** ``make_sides`` is
    deterministic given ``(seed, item_id)``, so a re-draw would usually agree — and
    "usually" is the problem: a spec with a different ``seed`` would silently present
    the verdict template in the other order and swap which speaker argued FLAWED, and
    the judgment would then be of a debate that never happened. The recorded draw is
    read back and reused, which also makes a source tree with a hand-edited
    ``sides.json`` judged as it is written.

    **A truncated or unparseable judgment fails the cell and is counted, not decided** —
    exactly as it was in the sweep. The judge has no ``public_label`` and so no budget
    route: ``_complete_with_repair`` spends its one format repair on a malformed reply,
    and a reply that is still malformed, or one cut off at the token ceiling, raises.
    The run is marked ``failed`` and the cell has no decision, which is the honest
    outcome and the one the sweep's 90.4% is measured on.

    Nothing under ``transcript_root`` is written. It is named in ``experiment.json`` with
    the sha256 of its ``experiment.json``, and each cell's manifest additionally carries
    ``source_run_dir``, ``source_sha256`` — a hash of the whole source directory — and
    the source's own ``source_verdict`` beside the new one.

    Resume follows ``decide``'s rule and for ``decide``'s reasons: a cell already decided
    here is skipped, and so is one whose latest run FAILED, unless ``retry_failed``.

    UNDER ``extend_rounds`` THE DEBATE IS CONTINUED BEFORE IT IS JUDGED — arm B of
    `judgment-debate-6`, the PLAIN extra round the contestability debate round is
    measured against. The same two debaters play ordinary rounds from the source's last
    round + 1 up to this spec's ``n_rounds``, with no objection anywhere and no new prompt
    text: `_round_instructions` already yields `ROUND_3_PLUS` for round 4, and at
    ``round == n_rounds`` it carries no closing clause, so what they read is byte-identical
    to the last round of a genuine four-round debate. Then the SAME `_judge` call is made
    over the longer transcript.

    THIS IS A DECISION DIRECTORY, so the extended transcript goes to ``transcript.json``
    through the ordinary `writer.record_turn` and OVERWRITES the copy `create_rejudge`
    made — which is correct and is the whole difference from the contest round: what this
    tree holds is a four-round debate that was judged here, and a reader who opened its published
    document and found three rounds under a judgment made from four would be reading a
    record that is wrong about itself. The manifest records
    ``extended_from_rounds`` beside ``rounds_n`` so the extension is legible without
    counting turns.

    It refuses a solo source (there are no debaters to continue), a source that already
    has ``n_rounds`` rounds or more (there would be nothing to add and the judgment would
    silently be an ordinary re-judge), and a source argued under settings other than this
    spec's (`recourse._assert_same_debate`, minus ``n_rounds``, which differs BY DESIGN).
    """
    unexpected = sorted({cell.condition for cell in cells} - {"debate"})
    if unexpected:
        raise ValueError(
            f"rejudge is a debate-only stage; got conditions {unexpected}. Only a "
            "debate has a judgment made from a record that outlives it: `single` and "
            "`self_critique` reach their verdict inside the conversation that wrote the "
            "record, and there is no stored artifact a second judge could be handed "
            "without re-running the decision itself."
        )
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def rejudge(cell: Cell) -> dict[str, Any]:
        if existing_decision(root, cell) is not None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already re-judged"}
        if not retry_failed and latest_run_status(root, cell) == "failed":
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already attempted and failed; --retry-failed to "
                              "re-attempt"}
        source = existing_decision(transcript_root, cell)
        if source is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no source decision to re-judge"}
        if source.transcript is None:
            # Unreachable through the CLI, which refuses a non-debate condition on this
            # spec, and recorded by name rather than crashing the stage if a direct
            # caller gets here: a decision with no transcript is a solo record, and
            # there is nothing to hand a judge.
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "source decision has no transcript to re-judge"}
        async with semaphore:
            # Inside the bound, for the reason create_recourse is: this copies a decision
            # directory, and running that unbounded would start every copy at once.
            writer = await asyncio.to_thread(
                RunWriter.create_rejudge,
                root=cell_dir(root, cell) / "runs", source_dir=source.directory,
                config=config, client_config=client_config, condition=cell.condition,
                rejudged_from=transcript_root,
            )
        # `judge_model` on the manifest as well as in `config.json`, because the manifest
        # is what a resume and a spend report read and the whole point of the run is
        # which judge made the verdict beside it.
        # `judge_form` beside `judge_model`, for the manifest's reason: it is what a
        # resume and a spend report read, and the whole point of a `fd1` run is that the
        # verdict beside it was DERIVED from a findings list rather than stated. Written
        # on every rejudge, "verdict" included, so a reader never has to infer it from
        # the presence of a file.
        writer.manifest_update(cell_id=cell.cell_id, judge_model=config.judge_model,
                               judge_form=config.judge_form)
        transcript = source.transcript
        boundary = max(turn.round for turn in transcript.all_turns())
        if config.extend_rounds:
            try:
                _assert_extendable(source, config, boundary)
            except DebateFailure as error:
                writer.finish("failed", error=f"{type(error).__name__}: {error}")
                log.warning("%s rejudge refused: %s", cell.cell_id, error)
                return {"cell_id": cell.cell_id, "status": "failed",
                        "error": f"{type(error).__name__}: {error}"}
            # A transcript of its own, so the source record's is not mutated: nothing
            # under `transcript_root` is written and nothing in memory that came from it
            # is edited either.
            transcript = Transcript(list(transcript.all_turns()))
            writer.manifest_update(extended_from_rounds=boundary,
                                   rounds_n=config.n_rounds)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    if config.extend_rounds:
                        for round_number in range(boundary + 1, config.n_rounds + 1):
                            await _run_round(
                                source.item, config, source.sides, client, transcript,
                                round_number=round_number, writer=writer,
                            )
                    verdict = await _judge(source.item, config, source.sides, client,
                                           transcript, writer=writer)
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s rejudge failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        findings = load_findings(writer.dir) or {}
        if findings:
            # Counted onto the manifest as well as into `findings.json`, so the
            # feasibility gate (the weak judge's parse rate) and the empty-list rate can
            # be read off the run records without opening every list.
            writer.manifest_update(findings_n=findings.get("n_findings"),
                                   findings_flaw_n=findings.get("n_flaw"))
        writer.finish("completed", totals=aggregate_calls(writer.dir / "calls.jsonl"))
        return {"cell_id": cell.cell_id, "status": "completed",
                "verdict": verdict.verdict, "correct": verdict.correct,
                "rounds_n": max(turn.round for turn in transcript.all_turns()),
                "findings_n": findings.get("n_findings"),
                "findings_flaw_n": findings.get("n_flaw"),
                "was": source.verdict.verdict}

    return await _bounded([lambda c=c: rejudge(c) for c in cells],
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

    UNDER ``recourse_rounds = 1`` THIS STAGE ALSO BUYS TWO DEBATER CALLS PER CELL. The
    two ORIGINAL debaters each reply once to the objection before the judge rules, and
    the judge is shown what they said (`recourse.hear_exchange`, DESIGN.md's
    contestability-debate-round ablation). The round's turns are written as
    ``recourse_transcript.json`` — never ``transcript.json``, which would make this
    contest directory load as a decision — and the ruling records the exchange it was
    made on.

    RESUME IS UNCHANGED AND THAT IS A CHOICE. The resume key is still "does this cell
    already hold a ruling", so a cell whose round completed but whose judge call FAILED is
    re-attempted from scratch in a new directory and both turns are bought again. There is
    no half-round resume: ruling on one stored reply and one fresh one would be a
    different protocol wearing this one's name, and the wasted turns are cents.
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
                               recourse_form=config.recourse_form,
                               recourse_rounds=config.recourse_rounds)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    exchange = None
                    if config.recourse_rounds:
                        exchange = await hear_exchange(record, challenge, config,
                                                       client, writer=writer)
                    # The writer goes through so a re-rule of a FINDINGS objection
                    # writes its own `findings.after.json` beside the ruling it just
                    # made. `_RERULE_EXCLUDED` drops the source's copy for exactly that
                    # reason: a derivation is a property of the ruling next to it, and
                    # the old judge's applied rulings under a new judge's verdict would
                    # be a file that is wrong about itself.
                    ruling = await _rule_by_judge(record, challenge, config, client,
                                                  exchange=exchange, writer=writer)
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s rerule failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        if ruling.recourse_pro_speaker is not None:
            writer.manifest_update(recourse_pro_speaker=ruling.recourse_pro_speaker)
        # Writes ruling.json and re-renders both documents, so the copied record and the
        # new ruling are one document rather than a directory a reader has to assemble.
        writer.record_ruling(ruling)
        writer.finish("completed", totals=aggregate_calls(writer.dir / "calls.jsonl"))
        return {"cell_id": cell.cell_id, "status": "completed",
                "was": writer.rerule_of_form, "now": ruling.form,
                "recourse_rounds": ruling.recourse_rounds,
                "changed": ruling.changed_the_decision}

    return await _bounded([lambda c=c: rerule(c) for c in cells],
                          client_config.max_runs_in_flight)


async def run_stage_gatekeeper(
    cells: Sequence[Cell], *, root: Path, config: DebateConfig,
    grading: GradingConfig, client_config: ClientConfig, api_key: str,
    decision_root: Path, contest_root: Path,
) -> list[dict[str, Any]]:
    """Decide, for another tree's finished objections, which of them are heard.

    POST HOC — the M4 ablation added 2026-08-28 after M1's preliminary numbers were seen
    (`records/experiments/judgment-debate-3/PREREG.md`, the M4 amendment, written and
    dated before the first paid call of this stage).

    THIS STAGE MAKES NOTHING AND REPLACES NOTHING. The objection is the stakeholder's, the
    ruling is the recourse judge's, and both are copied here verbatim — with the ruling,
    unlike a re-rule, precisely because the ruling is what the gate decides whether to
    count. One call per contested cell adds one file, ``admission.json``. The after-state
    arithmetic lives in ``build_index``: the ruling's outcome where the objection was
    admitted, the decision's own verdict where it was refused.

    Only cells whose source objection has stance ``contests`` are gated. A decline put
    nothing to a judge and there is nothing to admit, so the cell is skipped with ``no
    objection to gate`` rather than silently.

    Nothing under ``contest_root`` or ``decision_root`` is written. Both are named in
    ``experiment.json`` with the sha256 of their ``experiment.json``, and each cell's
    manifest carries ``source_contest_dir`` and ``source_sha256``, a hash of the whole
    source directory.
    """
    challenger = config.challenger_model_for()
    if not config.gatekeeper_model:
        # Refused once, here, rather than per cell. See `config.WHY["gatekeeper_model"]`:
        # it inherits from nothing, because the only neighbour to inherit from is the
        # judge whose own judgment is under appeal.
        raise ValueError(
            "the gatekeeper stage needs `gatekeeper_model` in the spec's [debate] "
            "table; it has no default and inherits from no other field."
        )
    semaphore = asyncio.Semaphore(client_config.max_concurrency)

    async def gate(cell: Cell) -> dict[str, Any]:
        existing = existing_contest(root, cell, challenger)
        if existing is not None and (existing / "admission.json").is_file():
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "already gated"}
        source = existing_contest(contest_root, cell, challenger)
        if source is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no source contest to gate"}
        challenge = Challenge.from_dict(
            json.loads((source / "challenge.json").read_text()))
        if challenge.stance != "contests":
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no objection to gate"}
        record = existing_decision(decision_root, cell)
        if record is None:
            return {"cell_id": cell.cell_id, "status": "skipped",
                    "reason": "no decision to gate against"}
        async with semaphore:
            # Inside the bound, for the reason create_recourse is: this copies a contest
            # directory that itself contains a copy of a decision, and running that
            # unbounded would start every copy at once.
            writer = await asyncio.to_thread(
                RunWriter.create_gate,
                root=contest_dir(root, cell, challenger) / "runs",
                source_dir=source, item=record.item,
                client_config=client_config, condition=cell.condition,
            )
        writer.manifest_update(cell_id=cell.cell_id, challenger_model=challenger,
                               gatekeeper_model=config.gatekeeper_model)
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=writer.record_call,
                                        semaphore=semaphore) as client:
                async with asyncio.timeout(client_config.run_timeout_s):
                    admission = await judge_admissibility(
                        record, challenge, config=config, grading=grading,
                        client=client)
        except Exception as error:
            writer.finish("failed", error=f"{type(error).__name__}: {error}")
            log.warning("%s gatekeeper failed: %s", cell.cell_id, error)
            return {"cell_id": cell.cell_id, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"}
        totals = aggregate_calls(writer.dir / "calls.jsonl")
        # This run's own wire spend — the gate call plus any repair of it — put on the
        # record it belongs to. `gatekeeper` is an off-path role, so it is the off-path
        # half that carries it; the sum of both halves is taken so that a role
        # reclassified later cannot silently zero the column.
        admission = replace(
            admission,
            cost_usd=(totals["off_path"]["cost_usd"]
                      + totals["decision_path"]["cost_usd"]))
        writer.record_admission(admission)
        writer.finish("completed", totals=totals)
        return {"cell_id": cell.cell_id, "status": "completed",
                "admitted": admission.admitted,
                "findings": len(admission.findings),
                "line_mismatch": admission.line_mismatch}

    return await _bounded([lambda c=c: gate(c) for c in cells],
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
        if challenge.arm == FINDINGS_VARIANT:
            # NO CALL, and no client. Under this arm the objection's argument is a
            # numbered list the harness already parsed, so "did this reply actually
            # contest anything" is `n_well_formed > 0` — a string comparison a reader can
            # redo — rather than a grader's reading of prose. Written as a real
            # `Agreement` with `parse_mode = "mechanical"`, so `agrees`,
            # `phantom_contest` and every consumer work unchanged and nothing claims a
            # model wrote it. It is NEVER pooled with jd3–jd6's Haiku column; the
            # analysis caveat says so, and PREREG §7 names its two blind spots and the
            # hand read that scores them.
            #
            # Placed after the stance check and before the decision is loaded, because
            # it needs neither the decision nor the network.
            agreement = mechanical_agreement(challenge)
            (directory / "agreement.json").write_text(
                json.dumps(agreement.to_dict(), indent=2), encoding="utf-8")
            return {"cell_id": cell.cell_id, "status": "completed",
                    "line": agreement.line_word, "prose": agreement.prose_stance,
                    "agrees": agreement.agrees,
                    "phantom": agreement.phantom_contest}
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
    the line amounted to, the parent verdict — is in ``ruling.json``, and for a findings
    ruling the contests it answered are in the ``challenge.json`` beside it. That is also
    what makes it re-runnable over any finished tree for nothing but the grader's cents.

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
        # THE CONTESTS THE RULING ANSWERED, for the findings reader only. They live on
        # the sibling `challenge.json` and not on the `Ruling` — the record was never
        # asked to carry them — so they are loaded here rather than threaded through the
        # ruling. A ruling whose challenge is missing or unreadable is still read, with
        # the reader told the contests were not recorded: an unmeasured contest block is
        # a worse failure than a reading made without one, and "absent" must stay a
        # visible fact rather than an empty block that reads as "none raised".
        contests = _read_json_or_empty(directory / "challenge.json").get("defects")
        try:
            async with OpenRouterClient(api_key, client_config,
                                        sink=_sink_to(directory / "calls.jsonl"),
                                        semaphore=semaphore) as client:
                reading = await judge_ruling_prose(
                    ruling, contests=contests if isinstance(contests, list) else None,
                    config=config, grading=grading, client=client)
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
        if challenge.arm == FINDINGS_VARIANT:
            # NONE of the flaw grader's three gates applies, and the reason is stronger
            # than the judgment arm's. Two of this arm's three contest kinds are graded
            # against the record alone; the third is graded against the annotation, but
            # on a SOUND item its answer follows from the label with no reading at all
            # (`grading._grade_findings`), so a sound item is not ungradable here — it is
            # the case where grading is FREE. And validity on a CORRECT decision is a
            # real finding: a judge that ruled a genuine flaw NOT A FLAW and still
            # reached FLAWED on another finding was right by accident, and the contest
            # that says so is valid. Every cell whose stance is `contests` is graded.
            #
            # Placed before the gates and not inside them, because the `else` below
            # would KeyError on this mode's grade file.
            try:
                async with OpenRouterClient(api_key, client_config,
                                            sink=_sink_to(directory / "calls.jsonl"),
                                            semaphore=semaphore) as client:
                    grade_result = await grade_objection(
                        cell.case, challenge.text, config=config, grading=grading,
                        client=client, mode="findings",
                        record=record.challenger_view().body,
                        # The judge's own reply — the same findings text the challenger
                        # and the recourse judge were shown.
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
                    "mode": "findings", "valid": grade_result.valid,
                    "contests": len(grade_result.contests),
                    "line_mismatch": grade_result.line_mismatch}
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

    ONE COLUMN IS COMPUTED RATHER THAN READ, and only on a tree the ``gatekeeper`` stage
    ran over. Where an ``admission.json`` sits beside a contest, ``final_correct`` is the
    RULING's outcome if the gate ADMITTED the objection and the DECISION's own verdict if
    it REFUSED — with ``changed_the_decision`` set False on a refusal to match. Nothing in
    the tree is altered to make that true: the ruling is the source arm's, copied
    verbatim, and the gate decides only whether it counts. Both facts stay legible beside
    each other, because ``ruling_form`` and the ruling's own columns are still written,
    and ``analysis._gatekeeper_caveat`` says it in words on every gated index. The M4
    ablation of 2026-08-28 is what needs it, and it is POST HOC — see
    ``records/experiments/judgment-debate-3/PREREG.md``'s M4 amendment.
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
        # Written only on a RE-JUDGED decision, on the rule the graded columns follow:
        # absent where it does not apply, so "this verdict is the tree's own" and "this
        # verdict replaced another one" stay different facts. `source_verdict` is what
        # the source tree's judge said about the SAME transcript, so the M0-vs-nano
        # comparison is a column join and needs no second tree open;
        # `decision_cost_usd` above is this run's one judge call and never the debate,
        # because the debate's wire log was renamed rather than copied.
        # THE FINDINGS JUDGMENT, campaign `fd1`. Written only where the judge actually
        # wrote a list, on the rule every conditional column here follows: absent where it
        # does not apply, so "decided under the verdict form" and "decided under the
        # findings form and found nothing" stay different facts — the second is
        # `findings_n = 0` with a SOUND verdict.
        #
        # `findings_parse_mode` is the JUDGE's parse mode, copied here so the feasibility
        # gate (the weak judge's parse rate) is a column rather than a walk of the tree,
        # and `findings_ruling_normalised_n` counts the rulings written as FLAWED/SOUND
        # and read as FLAW/NOT A FLAW — the one tolerance in this arm's parsers, counted
        # so it is visible rather than invisible.
        stored_findings = load_findings(record.directory)
        if stored_findings is not None:
            row["judge_form"] = "findings"
            row["findings_n"] = stored_findings.get("n_findings")
            row["findings_flaw_n"] = stored_findings.get("n_flaw")
            row["findings_parse_mode"] = stored_findings.get("parse_mode")
            row["findings_ruling_normalised_n"] = stored_findings.get(
                "ruling_normalised_n")
            # HOW WELL THE JUDGE HELD THE FORMAT, reported and never enforced (the smoke
            # of 2026-09-02: one claim listed as four findings, a quarter of the passages
            # not verbatim). `findings_passage_exact_n` counts passages actually found in
            # the text under review, `findings_duplicate_passage_n` findings repeating an
            # earlier finding's passage, and the two char counts how much of the reply the
            # publication trim dropped either side of the list — a judge that writes a
            # page of commentary around every list is visible in a column rather than only
            # in the full published document.
            row["findings_passage_exact_n"] = stored_findings.get("passage_exact_n")
            row["findings_duplicate_passage_n"] = stored_findings.get(
                "duplicate_passage_n")
            row["findings_preamble_chars"] = stored_findings.get("preamble_chars")
            row["findings_trailing_chars"] = stored_findings.get("trailing_chars")
            # THE STRICT PAIR (R11b, after smoke 2). `findings_passage_exact_n` above
            # goes through `quote_in_text`, which case-folds and strips quote marks and
            # backticks, so smoke 2's theoremqa list scored exact on passages that were a
            # debater's prose rendering of the text's LaTeX.
            # `findings_passage_verbatim_n` is the case-sensitive substring test the
            # prompt actually asks for, and `findings_passage_ellipsis_n` counts the
            # ellipsis joins the prompt forbids and the lenient matcher tolerates. Both
            # report-only; the gap between exact and verbatim is the quantity to read.
            row["findings_passage_verbatim_n"] = stored_findings.get(
                "passage_verbatim_n")
            row["findings_passage_ellipsis_n"] = stored_findings.get(
                "passage_ellipsis_n")
        manifest = _decision_manifest(record.directory)
        if manifest.get("kind") == "rejudge":
            row["rejudged_from"] = manifest.get("rejudged_from")
            row["source_verdict"] = manifest.get("source_verdict")
            row["source_correct"] = manifest.get("source_correct")
            row["source_judge_model"] = manifest.get("source_judge_model")
            # ARM B of `judgment-debate-6`, and written only where the round was
            # actually played: `extended_from_rounds` is the source's length and
            # `rounds_n` this tree's, so "the debate this judge read is one round longer
            # than the one the source judge read" is a column and not an inference from
            # a spec file. `round4_*` are the added turns' own parse modes and word
            # counts — the paired arm's are `recourse_turn_*` below and the two are
            # deliberately named apart, because they are answers to different questions.
            if manifest.get("extended_from_rounds") is not None:
                added = manifest["extended_from_rounds"]
                row["extended_from_rounds"] = added
                row["rounds_n"] = manifest.get("rounds_n")
                turns = ([] if record.transcript is None
                         else [t for t in record.transcript.all_turns()
                               if t.round > added])
                row["round4_parse_modes"] = [t.parse_mode for t in turns]
                row["round4_words"] = [t.word_count for t in turns]
                row["round4_repairs"] = sum(t.repair_attempts for t in turns)

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
                row["challenge_fabricated"] = challenge.fabricated
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
                # THE FABRICATED ARM'S GROUND TRUTH, and it is written on every
                # judgment-family row rather than only that arm's, so that the check can
                # be read on the real audit too — where it is the same quantity under the
                # other name: a defect quoting a judgment that does not say it is an
                # instrument failure in M1 and the whole point in this arm.
                #
                # `challenge_defects_fabricated_n` counts defects EVERY one of whose
                # judgment quotations is absent, which is stricter than
                # `challenge_defects_misattributed_n` above: that one counts a defect as
                # soon as ONE of its two quotations fails, which is the right rule for
                # the pre-registered check and the wrong one for "was this invented".
                # `challenge_fabrication_ok` is the per-OBJECTION flag — True only if
                # every defect it alleged is fabricated — and it is the manipulation
                # check `records/experiments/judgment-debate-4/PREREG.md` puts a
                # threshold on. Both are computed by string comparison, not by a model.
                row["challenge_defects_fabricated_n"] = (
                    objection_defects_fabricated_n(challenge.defects))
                row["challenge_fabrication_ok"] = (
                    objection_fabrication_ok(challenge.defects))
            if challenge.arm == FINDINGS_VARIANT:
                # WHAT WAS CONTESTED, by kind, and how much of it was void. Written only
                # under the findings arm, on the rule the graded columns follow: a 0 on a
                # neutral row would read as "it contested nothing" when the truth is that
                # nobody asked it to contest anything.
                #
                # `challenge_contests_void_n` counts contests whose quotation was not in
                # the document it named, whose finding does not exist, whose `Should be:`
                # agrees with the ruling it contests, or which alleges a contradiction
                # between a finding and itself — every one of them a string comparison a
                # reader can redo. They are the second denominator PREREG §2 reports the
                # break rate over: an objection made only of void contests cannot break
                # anything by construction.
                contests = challenge.defects or []
                row["challenge_contests_n"] = len(contests)
                for kind in ("finding", "omission", "contradiction"):
                    row[f"challenge_contests_{kind}_n"] = sum(
                        1 for c in contests if c.get("kind") == kind)
                row["challenge_contests_void_n"] = sum(
                    1 for c in contests if c.get("void"))
                # WHICH WAY EACH CONTEST OF A FINDING POINTS. The two directions are not
                # one instrument: `NOT A FLAW -> FLAW` is graded valid only if the
                # finding IS the annotated flaw (a lower bound on validity, PREREG §5a)
                # and `FLAW -> NOT A FLAW` is valid on every sound item by rule (an upper
                # bound), so a validity rate over the two pooled would move with the mix.
                # Counted over finding contests only: `Should be:` is not a field an
                # omission or a contradiction has.
                row["challenge_contests_to_flaw_n"] = sum(
                    1 for c in contests
                    if c.get("kind") == "finding" and c.get("should_be") == "FLAW")
                row["challenge_contests_to_not_a_flaw_n"] = sum(
                    1 for c in contests
                    if c.get("kind") == "finding"
                    and c.get("should_be") == "NOT A FLAW")
                # A RECORD QUOTATION THAT WAS GIVEN AND NOT FOUND, on a contest of a
                # finding. Since 2026-09-02 (R12a) that does not void the contest —
                # `Record says:` is optional for this kind and the anchor is `Text
                # says:`, and voiding on an optional field discarded a contest the ruling
                # judge had already ruled on (smoke 3, `strong/law`). The fact is still
                # worth having, so it is a column: it is the rate at which this
                # challenger attributes words to a document that does not carry them, and
                # a hand check can read the contests it names.
                row["challenge_contests_record_unverified_n"] = sum(
                    1 for c in contests
                    if c.get("kind") == "finding"
                    and c.get("quote_in_record") is False)
                # AN OBJECTION MADE ENTIRELY OF VOID CONTESTS. It cannot break anything
                # by construction, so PREREG §2 reports the break rate over the
                # denominator that excludes it — and it is NOT a phantom: the challenger
                # contested in earnest and quoted the wrong document, which is a
                # different failure from a REVERSE over an argument that endorses the
                # decision. Kept apart since 2026-09-02, when the phantom column was
                # measuring this instead.
                row["challenge_void_only"] = (
                    bool(contests)
                    and all(c.get("void") for c in contests))
                # A contest can be local and unable to move the verdict — one FLAW
                # finding among five keeps a FLAWED verdict however it is ruled — so
                # "objected" and "asked for a reversal" are two columns and not one.
                # `claimed_verdict` here is DERIVED from the contests, not from the
                # decision line.
                row["challenge_seeks_reversal"] = (
                    challenge.claimed_verdict is not None
                    and challenge.claimed_verdict != record.verdict.verdict)
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
            # THE CONTESTABILITY DEBATE ROUND, `judgment-debate-6`. Written only where a
            # round was heard, on the rule every conditional column here follows: absent
            # where it does not apply, so "judge-only recourse" and "a round that
            # produced nothing" stay different facts. `recourse_cost_usd` is the two
            # debater calls alone, read out of THIS contest's wire log by role, so the
            # arm's extra spend is legible per cell rather than only in a total.
            exchange = load_recourse_transcript(contest)
            if exchange is not None:
                turns = exchange.all_turns()
                row["recourse_turns_n"] = len(turns)
                row["recourse_turn_parse_modes"] = [t.parse_mode for t in turns]
                row["recourse_turn_words"] = [t.word_count for t in turns]
                row["recourse_turn_repairs"] = sum(t.repair_attempts for t in turns)
                row["recourse_cost_usd"] = (
                    aggregate_calls(contest / "calls.jsonl")["by_role"]
                    .get("recourse_debater", {}).get("cost_usd"))
            ruling_path = contest / "ruling.json"
            if ruling_path.is_file():
                ruling = json.loads(ruling_path.read_text())
                row["ruling_form"] = ruling.get("form")
                # HOW MANY ROUNDS the judge heard before ruling, and who argued the
                # objection. Read off the RULING rather than the spec, because the ruling
                # is what records the exchange it was actually made on: a cell whose
                # round failed and was ruled anyway would carry 0 here beside a spec that
                # asked for 1, and that is the fact worth having.
                row["recourse_rounds"] = ruling.get("recourse_rounds", 0)
                row["recourse_pro_speaker"] = ruling.get("recourse_pro_speaker")
                # WHICH PROMPT ruled, not which form the answer took. Both prompts
                # produce `stated_conclusion`, so without this column a materiality
                # ruling and an object-level one are the same row. Defaulted here as
                # well as on the dataclass, because the trees already on disk hold
                # `ruling.json` files written before the field existed.
                row["ruling_prompt_form"] = ruling.get("prompt_form", "object_level")
                if ruling.get("form") == "derived_findings":
                    # THE DERIVATION, as columns, so the re-derived verdict can be
                    # checked against the lines it came from without opening a file.
                    # `ruling_prose_empty` is the residual this arm has to bound: the
                    # judge is asked for lines and may write nothing else, and a ruling
                    # with no prose is one the `ruling_agreement` reader cannot read —
                    # counted rather than silently unmeasured.
                    after = _read_json_or_empty(contest / "findings.after.json")
                    row["ruling_contest_lines"] = ruling.get("conclusion_line")
                    row["findings_after_n"] = after.get("n_findings")
                    row["findings_after_flaw_n"] = after.get("n_flaw")
                    row["findings_added_n"] = after.get("n_added")
                    row["ruling_prose_empty"] = not (ruling.get("reasoning") or "").strip()
                    # A LINE ANSWERED IN THE WRONG VOCABULARY — `NOT AN OMISSION` on an
                    # objection to a numbered finding, and its two mirrors.
                    # `apply_contest_lines` treats such a line as no change, which is the
                    # safe direction, so nothing in the derivation moves with this column;
                    # what it buys is that a contest disposed of by a category error stops
                    # being indistinguishable from one never raised. 1/60 lines in the
                    # weak pilot and 1/26 in the strong one, which is why it is a count
                    # and not an assertion.
                    row["ruling_lines_kind_mismatch_n"] = count_kind_mismatched_lines(
                        challenge.defects if challenge is not None else None,
                        contest_lines_from_text(ruling.get("conclusion_line") or ""))
                    # Whether the PUBLISHED grounds ended on a dangling lead-in that the
                    # document's strip dropped (R11a). Recorded here as well as off the
                    # `ruling_agreement.json` row below, and from the same function on
                    # the same text, so the fact survives on a tree where the reader
                    # stage has not run — the reading overwrites it with the identical
                    # value where it has.
                    row["ruling_leadin_stripped"] = strip_ruling_prose(
                        ruling.get("reasoning") or "")[1]
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
                    # NOT COMPUTED FOR A VOID-ONLY OBJECTION (R12g). `mismatch` compares
                    # the reader's reading of the prose against the ruling's own verdict
                    # — and where every contest was void that verdict is DERIVED with all
                    # of the judge's lines discarded, so the comparison is against a
                    # number the prose never argued for. The reader is not told the
                    # contests were voided either. So the column is None here rather than
                    # False: `_rate` and every derivation already skip a None, and "not
                    # measurable on this row" must not read as "measured and consistent".
                    # `ruling_prose_conclusion` above is kept, since the READING is still
                    # a reading; it is only the comparison that has no meaning.
                    row["ruling_line_mismatch"] = (
                        None if row.get("challenge_void_only")
                        else reading["mismatch"])
                    # Whether the prose handed to the reader ended on a dangling lead-in
                    # ("The final ruling for Contest 1 is:") that the strip dropped. A
                    # fact about the RULING PROMPT, not about the reader: two of three
                    # findings-reader mismatches in the smoke were caused by one, and the
                    # prompt now says to write the lines rather than announce them.
                    row["ruling_leadin_stripped"] = reading.get(
                        "leadin_stripped", False)
            else:
                # No ruling was sought because nothing was objected to. Not-revised is
                # the right reading; "never contested" is preserved by challenge_raised.
                row["changed_the_decision"] = False
                row["final_correct"] = record.verdict.correct
            admission_path = contest / "admission.json"
            if admission_path.is_file():
                # THE M4 GATE — POST HOC, added 2026-08-28 after M1's preliminary
                # numbers were seen. Written only on a tree the `gatekeeper` stage ran
                # over, on the rule every conditional column here follows: absent where
                # it does not apply, so "no gate" and "gate refused" stay different
                # facts.
                #
                # AND IT MOVES `final_correct`. This is the one place in the index where
                # a column is not simply read off an artifact, so it is stated here and
                # in the analysis caveat: on a gated tree the after-state is the
                # RULING's outcome where the objection was ADMITTED and the DECISION's
                # own verdict where it was refused. That is the whole arm — the ruling
                # is unchanged and untouched, and the gate decides only whether it is
                # counted. A gated index whose `final_correct` still counted every
                # ruling would be M1's index under M4's name.
                admission = json.loads(admission_path.read_text())
                row["gate_admitted"] = admission.get("admitted")
                row["gate_model"] = admission.get("model")
                row["gate_findings_n"] = admission.get("findings_n")
                row["gate_findings_real_n"] = admission.get("findings_real_n")
                row["gate_line_mismatch"] = admission.get("line_mismatch")
                row["gate_parse_mode"] = admission.get("parse_mode")
                row["gate_cost_usd"] = admission.get("cost_usd")
                if not admission.get("admitted"):
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
                if row["grade_mode"] == "findings":
                    # The `elif` is not optional: the `else` below reads
                    # `grade["identified_flaw"]`, which a findings grade does not carry,
                    # and would KeyError the whole index on the first graded cell.
                    row["grade_contests_n"] = grade.get("contests_n")
                    row["grade_contests_valid_n"] = grade.get("contests_valid_n")
                    row["grade_contests_mechanical_n"] = grade.get(
                        "contests_mechanical_n")
                    row["grade_line_mismatch"] = grade.get("line_mismatch")
                elif row["grade_mode"] == "judgment":
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


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    """One artifact, or an empty dict where it is not there.

    `_decision_manifest`'s shape, generalised for the conditional artifacts the index
    joins: absent and unreadable both give `{}`, so a `.get` on the result is "not
    written" rather than a crash on a tree a stage has not reached yet.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _decision_manifest(directory: Path) -> dict[str, Any]:
    """A decision run's ``run.json``, or an empty dict.

    ``load_run_record`` deliberately returns no manifest — it is operational rather than
    decision-relevant — but the re-judge provenance lives there, so the index reads it
    directly rather than widening ``RunRecord`` with a field only one stage writes.
    """
    try:
        return json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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
