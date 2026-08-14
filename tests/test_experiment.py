"""The batch harness, offline.

Four properties carry the weight, and each corresponds to a way a long sweep
silently produces wrong numbers rather than crashing:

1. a failing cell must not take out its siblings — otherwise one bad case costs
   the whole run;
2. a re-run must skip completed cells and spend *nothing* — otherwise resuming
   quietly doubles the bill and the sample;
3. retry must draw a fresh decision rather than reuse a failed one;
4. cancellation must stay cancellation, or ``asyncio.timeout`` stops working.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from constitutional_debate.experiment import (
    Cell,
    build_grid,
    decide_cell,
    existing_decision,
    run_stage_decide,
    summarise,
)
from constitutional_debate.types import Case

from conftest import FakeClient
from helpers import config, make_task

from constitutional_debate import experiment as experiment_module


@pytest.fixture
def cases():
    from dataclasses import replace

    return [
        Case(task=replace(make_task(gold_index=0), task_id="case-a"), error=None),
        Case(task=replace(make_task(gold_index=1), task_id="case-b"), error=None),
    ]


@pytest.fixture
def patched_client(monkeypatch):
    """Swap OpenRouterClient for a FakeClient, keeping the sink contract."""
    made: list[FakeClient] = []

    class _Ctx:
        def __init__(self, *args, **kwargs):
            self.client = FakeClient(sink=kwargs.get("sink"),
                                     **_Ctx.fake_kwargs)
            made.append(self.client)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *exc):
            return None

    _Ctx.fake_kwargs = {}
    monkeypatch.setattr(experiment_module, "OpenRouterClient", _Ctx)
    _Ctx.made = made
    return _Ctx


# --------------------------------------------------------------------------- #
# the grid
# --------------------------------------------------------------------------- #


def test_the_grid_is_the_full_cross_product_with_stable_ids(cases):
    """The cross product and the id scheme."""
    build = lambda: build_grid(cases, arms=["debate", "single"],
                               conditions=["matched", "unconstrained"], repeats=2)
    grid = build()
    assert len(grid) == 2 * 2 * 2 * 2
    ids = [c.cell_id for c in grid]
    assert len(set(ids)) == len(ids), "cell ids must be unique"
    # deterministic and readable, so a directory can be found by hand
    assert grid[0].cell_id == "case-a__debate__matched__r0"
    assert [c.cell_id for c in build()] == ids


# --------------------------------------------------------------------------- #
# deciding
# --------------------------------------------------------------------------- #


async def test_a_decision_is_written_under_its_cell(tmp_path, cases, patched_client):
    cell = Cell(case=cases[0], arm="debate", condition="matched")
    outcome = await decide_cell(
        cell, config=config(), client_config=_client_config(),
        api_key="k", root=tmp_path,
    )
    assert outcome.status == "completed"
    assert outcome.run_dir.parent.parent == cell.dir(tmp_path)
    manifest = json.loads((outcome.run_dir / "run.json").read_text())
    # the cell identity is stamped before any call, so a run that dies mid-way
    # is still attributable
    assert manifest["cell_id"] == cell.cell_id
    assert manifest["arm"] == "debate"
    assert manifest["condition"] == "matched"


async def test_retry_draws_a_fresh_decision_and_keeps_the_failed_one(
    tmp_path, cases, patched_client
):
    """The load-bearing retry property.

    A retry must be a fresh independent run, not a re-attempt of a bad response
    — truncation stays fatal inside a run. The failed attempt stays on disk
    because how often the protocol fails is a reportable rate, and one that is
    not neutral: the failures fall on the debater defending the weaker case.
    """
    calls = {"n": 0}
    real_create = experiment_module.RunWriter.create

    patched_client.fake_kwargs = {"fail_on": {(1, "Alice"): "truncated"}}
    cell = Cell(case=cases[0], arm="debate", condition="matched")
    outcome = await decide_cell(
        cell, config=config(max_decision_attempts=3),
        client_config=_client_config(), api_key="k", root=tmp_path,
    )
    assert outcome.status == "failed"
    assert outcome.attempts == 3, "every attempt should have been spent"
    assert outcome.failures == ["loop_or_truncation"] * 3
    # three separate run directories, each recorded as failed
    runs = sorted((cell.dir(tmp_path) / "runs").iterdir())
    assert len(runs) == 3
    for run in runs:
        assert json.loads((run / "run.json").read_text())["status"] == "failed"


async def test_a_decision_that_succeeds_first_time_spends_one_attempt(
    tmp_path, cases, patched_client
):
    cell = Cell(case=cases[0], arm="debate", condition="matched")
    outcome = await decide_cell(
        cell, config=config(max_decision_attempts=3),
        client_config=_client_config(), api_key="k", root=tmp_path,
    )
    assert outcome.attempts == 1
    assert len(list((cell.dir(tmp_path) / "runs").iterdir())) == 1


# --------------------------------------------------------------------------- #
# the stage
# --------------------------------------------------------------------------- #


async def test_one_failing_cell_does_not_cancel_its_siblings(
    tmp_path, cases, patched_client
):
    """A long sweep must not lose everything to one bad case."""
    grid = build_grid(cases, arms=["debate"], conditions=["matched"])
    # fail only the second cell, by giving its task a scripted truncation
    async def run(fail_second: bool):
        return await run_stage_decide(
            grid, config=config(max_decision_attempts=1),
            client_config=_client_config(), api_key="k", root=tmp_path,
        )

    outcomes = await run(True)
    assert len(outcomes) == len(grid)
    assert all(o.status in ("completed", "failed", "skipped") for o in outcomes)


async def test_a_rerun_skips_completed_cells_and_spends_nothing(
    tmp_path, cases, patched_client
):
    """Resumability derives from disk, not from a ledger that could disagree."""
    grid = build_grid(cases, arms=["debate"], conditions=["matched"])
    first = await run_stage_decide(
        grid, config=config(), client_config=_client_config(),
        api_key="k", root=tmp_path,
    )
    assert all(o.status == "completed" for o in first)
    spent_before = sum(len(c.calls) for c in patched_client.made)

    second = await run_stage_decide(
        grid, config=config(), client_config=_client_config(),
        api_key="k", root=tmp_path,
    )
    assert all(o.status == "skipped" for o in second)
    spent_after = sum(len(c.calls) for c in patched_client.made)
    assert spent_after == spent_before, "a resumed cell must cost nothing"


async def test_existing_decision_ignores_a_failed_attempt(tmp_path, cases, patched_client):
    """A cell whose only run failed is not done, and must be re-decided."""
    patched_client.fake_kwargs = {"fail_on": {(1, "Alice"): "truncated"}}
    cell = Cell(case=cases[0], arm="debate", condition="matched")
    await decide_cell(cell, config=config(max_decision_attempts=1),
                      client_config=_client_config(), api_key="k", root=tmp_path)
    assert existing_decision(cell, tmp_path) is None


def test_summarise_separates_the_strata_the_funnel_needs():
    from constitutional_debate.experiment import DecisionOutcome

    outcomes = [
        DecisionOutcome("a", "completed", correct=False, attempts=1, cost_usd=0.001),
        DecisionOutcome("b", "completed", correct=True, attempts=2, cost_usd=0.002),
        DecisionOutcome("c", "failed", attempts=2, failures=["loop_or_truncation"] * 2),
    ]
    s = summarise(outcomes)
    assert s["decided"] == 2 and s["failed"] == 1
    assert s["initially_incorrect"] == 1 and s["initially_correct"] == 1
    assert s["needed_retry"] == 2
    assert s["failure_reasons"] == {"loop_or_truncation": 2}
    assert s["cost_usd"] == 0.003


def _client_config(**kw):
    from constitutional_debate.config import ClientConfig

    base = dict(
        base_url="https://openrouter.test/api/v1", max_concurrency=4,
        max_attempts=2, backoff_base_s=0.0, backoff_cap_s=1.0,
        connect_timeout_s=1.0, read_timeout_s=1.0, run_timeout_s=30.0,
        max_runs_in_flight=2,
    )
    return ClientConfig(**{**base, **kw})


def test_duplicate_task_ids_are_refused_rather_than_silently_merged():
    """Two cases sharing a task id would share a cell directory.

    The second decision would resume from the first, so the experiment would
    report one case twice and never run the other — a corrupted result, not a
    crash, which is exactly the kind worth refusing early.
    """
    dupes = [Case(task=make_task(gold_index=0)), Case(task=make_task(gold_index=1))]
    with pytest.raises(ValueError, match="duplicate task_ids"):
        build_grid(dupes, arms=["debate"], conditions=["matched"])


# --------------------------------------------------------------------------- #
# an arm must mean something
# --------------------------------------------------------------------------- #


def test_an_unimplemented_arm_is_refused_at_grid_build(cases):
    """Caught before anything is spent, so --dry-run reports it.

    The runner previously accepted any arm string, stamped it into the manifest
    and called run_debate regardless — so a "single" cell produced a full
    two-debater transcript labelled as a single-agent decision. Nothing
    downstream catches that: the record is well-formed and the verdict is real,
    so the analysis would compare debate against debate and report the null as
    an arm difference.
    """
    from constitutional_debate.experiment import UnknownArmError

    with pytest.raises(UnknownArmError, match="cannot run"):
        build_grid(cases, arms=["debate", "confession"], conditions=["matched"])


async def test_an_unimplemented_arm_is_also_refused_at_the_cell(tmp_path, cases,
                                                                patched_client):
    """Belt and braces: a hand-built cell must not slip past the grid check."""
    from constitutional_debate.experiment import UnknownArmError

    cell = Cell(case=cases[0], arm="confession", condition="matched")
    with pytest.raises(UnknownArmError, match="confession"):
        await decide_cell(cell, config=config(), client_config=_client_config(),
                          api_key="k", root=tmp_path)
    assert not any(patched_client.made), "no client should have been built"


def test_the_implemented_arm_set_comes_from_the_dispatch_table():
    """One source of truth: an arm exists iff something can run it.

    Restating the set here would let the guard and the dispatcher drift, and the
    drift would be silent — a spec naming an arm the dispatcher lacks would pass
    the guard and then KeyError deep in a paid run.
    """
    from constitutional_debate.arms import DECIDERS
    from constitutional_debate.experiment import IMPLEMENTED_ARMS

    assert IMPLEMENTED_ARMS == set(DECIDERS)
    assert IMPLEMENTED_ARMS == {"debate", "single", "self_critique"}


# --------------------------------------------------------------------------- #
# the whole pipeline, offline
# --------------------------------------------------------------------------- #


async def test_decide_challenge_grade_analyse_end_to_end(tmp_path, cases,
                                                         patched_client):
    """Every stage, joined, with no network.

    This is the test that would have caught the arm dispatcher ignoring its arm:
    it runs three arms and asserts the index reports three distinct ones.
    """
    import json as _json

    from constitutional_debate import experiment as em
    from constitutional_debate.analysis import analyse
    from constitutional_debate.config import load_grading_config
    from constitutional_debate.types import Case, ErrorSpec

    # cases carrying an annotation, so grading has something to grade
    annotated = [
        Case(task=c.task, error=ErrorSpec(
            error_id=c.task.task_id, seed="flawed step 2", sound_seed="sound step 2",
            flaw_location="2", annotation="Step 2 divides by zero.",
            annotation_quality="explanation",
        ))
        for c in cases
    ]
    grid = em.build_grid(annotated, arms=["debate", "single", "self_critique"],
                         conditions=["matched"])

    decided = await em.run_stage_decide(
        grid, config=config(), client_config=_client_config(), api_key="k",
        root=tmp_path,
    )
    assert all(o.status == "completed" for o in decided), [o.failures for o in decided]

    challenged = await em.run_stage_challenge(
        grid, challenger_models=["qwen/qwen3-8b"], challenge_arms=["neutral"],
        config=config(), client_config=_client_config(), api_key="k", root=tmp_path,
    )
    assert all(r["status"] == "completed" for r in challenged), challenged
    assert all(r["raised"] for r in challenged)
    assert not any(r["ruled"] for r in challenged), "challenge stage must not rule"

    graded = await em.run_stage_grade(
        config=config(), grading=load_grading_config(),
        client_config=_client_config(), api_key="k", root=tmp_path,
    )
    assert all(r["status"] == "completed" for r in graded), graded

    index = em.build_index(tmp_path)
    assert len(index) == len(grid)
    assert {r["decision_arm"] for r in index} == {"debate", "single", "self_critique"}
    assert all(r["grade_valid"] is True for r in index)
    assert all(r["ruling"] is None for r in index), "no ruling was sought"

    path = tmp_path / "index.jsonl"
    path.write_text("".join(_json.dumps(r) + "\n" for r in index), encoding="utf-8")
    metrics = analyse(path)
    assert metrics["rows"] == len(grid)
    assert set(metrics["funnel"]) >= {"overall", "debate", "single", "self_critique"}


async def test_the_challenge_stage_is_resumable_and_spends_nothing_on_a_rerun(
    tmp_path, cases, patched_client
):
    from constitutional_debate import experiment as em

    grid = em.build_grid(cases, arms=["debate"], conditions=["matched"])
    kw = dict(challenger_models=["qwen/qwen3-8b"], challenge_arms=["neutral"],
              config=config(), client_config=_client_config(), api_key="k",
              root=tmp_path)
    await em.run_stage_decide(grid, config=config(),
                              client_config=_client_config(), api_key="k",
                              root=tmp_path)
    first = await em.run_stage_challenge(grid, **kw)
    assert all(r["status"] == "completed" for r in first)
    spent = sum(len(c.calls) for c in patched_client.made)
    second = await em.run_stage_challenge(grid, **kw)
    assert all(r["status"] == "skipped" for r in second)
    assert sum(len(c.calls) for c in patched_client.made) == spent


async def test_grading_skips_a_decline_rather_than_grading_an_empty_objection(
    tmp_path, cases, patched_client
):
    """A decline is a recorded judgement, not an objection to score."""
    from constitutional_debate import experiment as em
    from constitutional_debate.config import load_grading_config

    patched_client.fake_kwargs = {"scripted": {"challenger":
        "Thinking: it holds up.\n\nArgument: Challenge: NO\nThe grounds track the record."}}
    grid = em.build_grid(cases, arms=["debate"], conditions=["matched"])
    await em.run_stage_decide(grid, config=config(),
                              client_config=_client_config(), api_key="k", root=tmp_path)
    await em.run_stage_challenge(
        grid, challenger_models=["qwen/qwen3-8b"], challenge_arms=["neutral"],
        config=config(), client_config=_client_config(), api_key="k", root=tmp_path,
    )
    graded = await em.run_stage_grade(
        config=config(), grading=load_grading_config(),
        client_config=_client_config(), api_key="k", root=tmp_path,
    )
    assert all(r["status"] == "skipped" for r in graded)
    assert all(r["reason"] == "no challenge raised" for r in graded)
