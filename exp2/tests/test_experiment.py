"""The batch harness: resume, concurrency, isolation, and the index.

Nothing here touches the network — ``OpenRouterClient`` is monkeypatched and the API key
is removed from the environment, so a test cannot spend money even by mistake.
"""

from __future__ import annotations

import json

import pytest
from conftest import FakeClient
from helpers import make_config, make_item, make_sides

from exp2 import experiment as experiment_module
from exp2.config import ClientConfig, GradingConfig
from exp2.experiment import (
    Cell,
    build_grid,
    build_index,
    cell_dir,
    existing_decision,
    latest_run_status,
    run_stage_agreement,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
)
from exp2.types import Case, FlawAnnotation


def client_config(**kw) -> ClientConfig:
    base = dict(base_url="https://x/api", max_concurrency=8, max_attempts=2,
                backoff_base_s=0.01, backoff_cap_s=0.02, connect_timeout_s=1.0,
                read_timeout_s=5.0, run_timeout_s=60.0, max_runs_in_flight=8)
    base.update(kw)
    return ClientConfig(**base)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """One FakeClient shared by every stage, so concurrency is observable across cells."""
    shared = FakeClient()

    class Ctx:
        def __init__(self, *a, **kw):
            self.sink = kw.get("sink")

        async def __aenter__(self):
            shared.sink = self.sink
            return shared

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(experiment_module, "OpenRouterClient", Ctx)
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    return shared


def cases(n=3, *, gold_flawed=True, quality="explanation") -> list[Case]:
    out = []
    for i in range(n):
        item = make_item(item_id=f"theoremqa-p{i}-flawed", row_id=f"theoremqa:p{i}",
                         gold_flawed=gold_flawed)
        flaw = (FlawAnnotation(annotation_id=f"a{i}", flaw_location="2",
                               annotation="Step 2 miscounts.", annotation_quality=quality)
                if gold_flawed else None)
        out.append(Case(item=item, flaw=flaw))
    return out


def make_decisions_wrong(client) -> None:
    """Make every condition answer SOUND on a flawed item, i.e. a false negative.

    The grade stage is confined to the metric's denominator — incorrect decisions on
    flawed, characterisable items — so a test that wants grading to run has to produce
    a decision that is actually wrong.
    """
    client.replies.update({
        "judge": "The sound side answered the objection.\nVerdict: SOUND",
        ("solo", "answer"): "Thinking: t\nReasoning: it holds up.\nVerdict: SOUND",
        ("solo", "draft"): "Thinking: t\nReasoning: it holds up.\nVerdict: SOUND",
        ("solo", "revision"): "Thinking: t\nReasoning: it still holds.\nVerdict: SOUND",
        # The line is relative to whatever the decision was, so the same REVERSE reply
        # contests a SOUND decision here and a FLAWED one in the default fixture — which
        # is the whole point of the third rewrite. A reply with no parsable line is
        # `unclear` and seeks no ruling.
        "challenger": ("Thinking: I read the record.\n"
                       "Argument: Decision: REVERSE\n"
                       "Step 2 divides by zero and the decision missed it."),
    })


async def decide(tmp_path, grid, *, retry_failed=False, **kw):
    return await run_stage_decide(grid, root=tmp_path, config=make_config(),
                                  client_config=client_config(**kw), api_key="k",
                                  retry_failed=retry_failed)


# --- the grid ------------------------------------------------------------------------


def test_the_grid_is_the_cross_product_and_refuses_unknown_conditions():
    grid = build_grid(cases(2), ["debate", "single"])
    assert len(grid) == 4
    assert {c.cell_id for c in grid} == {
        "theoremqa-p0-flawed__debate__r1", "theoremqa-p0-flawed__single__r1",
        "theoremqa-p1-flawed__debate__r1", "theoremqa-p1-flawed__single__r1"}
    with pytest.raises(ValueError, match="unknown conditions"):
        build_grid(cases(1), ["telepathy"])


def test_duplicate_item_ids_are_refused_because_they_would_collide_on_disk():
    duplicated = cases(1) * 2
    with pytest.raises(ValueError, match="duplicate item_id"):
        build_grid(duplicated, ["debate"])


# --- decide --------------------------------------------------------------------------


async def test_decide_writes_a_completed_run_per_cell(tmp_path):
    grid = build_grid(cases(2), ["debate", "single"])
    results = await decide(tmp_path, grid)
    assert [r["status"] for r in results] == ["completed"] * 4
    for cell in grid:
        assert existing_decision(tmp_path, cell) is not None


async def test_decide_resumes_and_spends_nothing_the_second_time(tmp_path, no_network):
    grid = build_grid(cases(2), ["debate"])
    await decide(tmp_path, grid)
    before = len(no_network.calls)
    again = await decide(tmp_path, grid)
    assert [r["status"] for r in again] == ["skipped"] * 2
    assert len(no_network.calls) == before


async def test_a_run_left_running_is_not_a_decision_and_gets_retried(tmp_path,
                                                                    no_network):
    """A cell killed mid-``decide`` — a crash, an ENOSPC, a Ctrl-C — leaves ``run.json``
    at ``"running"`` with whatever files it had managed to write.

    ``load_run_record`` refuses any status but ``completed``, so ``existing_decision``
    reports no decision and the cell is decided again. Both halves matter: skipping it
    would leave a half-written cell in the analysis, and treating it as decided *and*
    writing to it again would double-write a run directory. The retry claims a **new**
    run directory and the abandoned one stays on disk as the record of what happened.
    """
    grid = build_grid(cases(1), ["single"])
    await decide(tmp_path, grid)
    cell = grid[0]
    runs = cell_dir(tmp_path, cell) / "runs"
    killed = sorted(runs.glob("*"))[0]
    manifest = json.loads((killed / "run.json").read_text())
    assert manifest["status"] == "completed"
    manifest["status"] = "running"
    (killed / "run.json").write_text(json.dumps(manifest))
    # the verdict is still there; it is the status alone that says this is not a decision
    assert (killed / "verdict.json").is_file()
    assert existing_decision(tmp_path, cell) is None

    before = len(no_network.calls)
    again = await decide(tmp_path, grid)
    assert [r["status"] for r in again] == ["completed"]
    assert len(no_network.calls) > before
    assert existing_decision(tmp_path, cell) is not None
    assert sorted(runs.glob("*")) != [killed], "the retry did not write over the corpse"
    assert json.loads((killed / "run.json").read_text())["status"] == "running"


async def test_one_failing_cell_does_not_take_the_stage_down(tmp_path, no_network):
    no_network.fail_on = {(1, "Alice"): "fatal"}
    grid = build_grid(cases(3), ["debate"])
    results = await decide(tmp_path, grid)
    assert all(r["status"] == "failed" for r in results)
    # and the stage is still runnable afterwards — see the resume tests below for
    # which of those cells a second invocation attempts.
    no_network.fail_on = {}
    assert all(r["status"] in ("skipped", "completed")
               for r in await decide(tmp_path, grid))


# --- resume: one attempt per cell, unless asked for another ---------------------------


async def _fail_one_cell(tmp_path, no_network):
    """Decide one cell with the client failing, leaving `run.json` at `"failed"`."""
    no_network.fail_on = {(1, "Alice"): "fatal"}
    grid = build_grid(cases(1), ["debate"])
    assert [r["status"] for r in await decide(tmp_path, grid)] == ["failed"]
    no_network.fail_on = {}
    assert latest_run_status(tmp_path, grid[0]) == "failed"
    return grid


async def test_a_failed_cell_is_not_re_attempted_by_default(tmp_path, no_network):
    """A truncation or an unrepairable reply is a MODEL OUTCOME, not an interruption.

    Re-running `decide` after a crash must finish the sweep, not give ~900 truncated
    cells a second draw: that selects for compliant outputs, so the surviving cells stop
    being a sample of the corpus, and at seed 0 the second draw mostly reproduces the
    first failure anyway. `LLM_NOTES.md` 3p.4 declined to wire a per-cell retry for
    exactly these reasons; before this the resume was one, silently.
    """
    grid = await _fail_one_cell(tmp_path, no_network)
    before = len(no_network.calls)
    again = await decide(tmp_path, grid)
    assert [r["status"] for r in again] == ["skipped"]
    assert "--retry-failed" in again[0]["reason"]
    assert len(no_network.calls) == before, "a skipped cell must cost nothing"


async def test_retry_failed_opts_back_into_re_attempting_a_failed_cell(tmp_path,
                                                                      no_network):
    """The escape hatch, for failures that were the harness's fault and not the model's."""
    grid = await _fail_one_cell(tmp_path, no_network)
    before = len(no_network.calls)
    again = await decide(tmp_path, grid, retry_failed=True)
    assert [r["status"] for r in again] == ["completed"]
    assert len(no_network.calls) > before
    assert existing_decision(tmp_path, grid[0]) is not None


async def test_a_cell_left_running_is_still_attempted_without_the_flag(tmp_path,
                                                                      no_network):
    """`"running"` is a killed process, not a model outcome — nothing was learned.

    This is the case the default exists to keep: a driver SIGTERMed mid-`decide`, an
    ENOSPC, a pod reboot. Those cells have to be picked up by a plain resume, or a
    crashed sweep can never be finished.
    """
    grid = build_grid(cases(1), ["single"])
    await decide(tmp_path, grid)
    cell = grid[0]
    killed = sorted((cell_dir(tmp_path, cell) / "runs").glob("*"))[0]
    manifest = json.loads((killed / "run.json").read_text())
    manifest["status"] = "running"
    (killed / "run.json").write_text(json.dumps(manifest))
    assert latest_run_status(tmp_path, cell) == "running"

    before = len(no_network.calls)
    assert [r["status"] for r in await decide(tmp_path, grid)] == ["completed"]
    assert len(no_network.calls) > before


async def test_a_never_attempted_cell_has_no_status_and_a_completed_one_is_skipped(
        tmp_path, no_network):
    grid = build_grid(cases(1), ["single"])
    assert latest_run_status(tmp_path, grid[0]) is None
    assert [r["status"] for r in await decide(tmp_path, grid)] == ["completed"]
    assert latest_run_status(tmp_path, grid[0]) == "completed"
    # completed wins over the flag: --retry-failed re-attempts failures, not decisions
    assert [r["status"] for r in await decide(tmp_path, grid,
                                              retry_failed=True)] == ["skipped"]


async def test_cells_run_concurrently(tmp_path, no_network):
    await decide(tmp_path, build_grid(cases(4), ["debate"]))
    assert no_network.max_in_flight > 1


# --- contest and grade ---------------------------------------------------------------


async def contest(tmp_path, grid):
    return await run_stage_contest(grid, root=tmp_path, config=make_config(),
                                   client_config=client_config(), api_key="k")


async def grade(tmp_path, grid):
    return await run_stage_grade(grid, root=tmp_path, config=make_config(),
                                 grading=GradingConfig(), client_config=client_config(),
                                 api_key="k")


async def agreement(tmp_path, grid):
    return await run_stage_agreement(grid, root=tmp_path, config=make_config(),
                                     grading=GradingConfig(),
                                     client_config=client_config(), api_key="k")


async def test_contest_needs_a_decision_first(tmp_path):
    grid = build_grid(cases(2), ["debate"])
    results = await contest(tmp_path, grid)
    assert all(r["reason"] == "no decision to contest" for r in results)


async def test_the_full_pipeline_runs_and_resumes_at_every_stage(tmp_path, no_network):
    make_decisions_wrong(no_network)
    grid = build_grid(cases(2), ["debate", "single"])
    assert all(r["status"] == "completed" for r in await decide(tmp_path, grid))
    assert all(r["status"] == "completed" for r in await contest(tmp_path, grid))
    assert all(r["status"] == "completed" for r in await agreement(tmp_path, grid))
    assert all(r["status"] == "completed" for r in await grade(tmp_path, grid))
    before = len(no_network.calls)
    for stage in (decide, contest, agreement, grade):
        assert all(r["status"] == "skipped" for r in await stage(tmp_path, grid))
    assert len(no_network.calls) == before


async def test_grade_and_contest_are_concurrent(tmp_path, no_network):
    """exp1's grade stage was a serial await loop whose semaphore was never contended."""
    make_decisions_wrong(no_network)
    grid = build_grid(cases(4), ["debate"])
    await decide(tmp_path, grid)
    no_network.max_in_flight = 0
    await contest(tmp_path, grid)
    assert no_network.max_in_flight > 1
    no_network.max_in_flight = 0
    await agreement(tmp_path, grid)
    assert no_network.max_in_flight > 1
    no_network.max_in_flight = 0
    await grade(tmp_path, grid)
    assert no_network.max_in_flight > 1


async def test_a_sound_item_is_never_graded(tmp_path):
    """Validity is undefined there, so grading it would enter the analysis as a
    measurement of something that does not exist."""
    grid = build_grid(cases(2, gold_flawed=False), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    results = await grade(tmp_path, grid)
    assert all("validity undefined" in r["reason"] for r in results)


async def test_grading_is_confined_to_the_metrics_own_denominator(tmp_path, no_network):
    """P(valid objection | initially incorrect), on flawed items. Grading anything else
    spends a call to learn nothing.

    But a location-only annotation is not "nothing": it records where the flaw is, which
    is what the where-bar asks. gpqa is 382 items and belongs in the detection row."""
    from exp2.types import FlawAnnotation

    ungradable = Case(item=make_item(item_id="gpqa-x-flawed", row_id="gpqa:x",
                                     subset="gpqa"),
                      flaw=FlawAnnotation(annotation_id="g", flaw_location="2",
                                          annotation="", annotation_quality="location_only"))
    grid = build_grid([ungradable], ["debate"])
    make_decisions_wrong(no_network)
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    # a location-only annotation IS graded — it records exactly what the where-bar asks
    assert (await grade(tmp_path, grid))[0]["status"] == "completed"
    directory = next((tmp_path / "cells").rglob("grade.json"))
    grade_result = json.loads(directory.read_text())
    assert grade_result["identified_flaw"] is True        # detection is measurable
    assert grade_result["characterises_the_flaw"] is False  # and clamped, not guessed
    assert grade_result["characterisation_ungradable"] is True
    assert grade_result["valid"] is False


async def test_a_correctly_decided_item_is_not_graded(tmp_path, no_network):
    """The fake judge answers FLAWED, so a flawed item is decided correctly."""
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    assert (await grade(tmp_path, grid))[0]["reason"] == "decision was correct — off-metric"


async def test_a_declined_objection_is_not_graded(tmp_path, no_network):
    no_network.replies = {"challenger":
                          "Thinking: t\nArgument: Decision: STANDS\nLooks sound."}
    grid = build_grid(cases(2), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    assert all(r["reason"] == "stance is declined, not contests"
               for r in await grade(tmp_path, grid))


async def test_a_decline_indexes_its_derived_verdict_and_is_not_graded(tmp_path, no_network):
    """`Decision: STANDS` against a FLAWED verdict derives a claimed FLAWED — the
    challenger no longer names it, so it cannot name it wrongly."""
    no_network.replies = {"challenger": ("Decision: STANDS\n"
                                         "The decision correctly identifies the error.")}
    grid = build_grid(cases(2), ["debate"])
    await decide(tmp_path, grid)
    results = await contest(tmp_path, grid)
    assert all(r["stance"] == "declined" for r in results)
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_raised"] is False and row["challenge_declined"] is True
    assert row["challenge_agreed"] is False and row["challenge_unclear"] is False
    assert row["challenge_claimed_verdict"] == "FLAWED"
    assert row["challenge_contradictory"] is False
    assert "ruling_form" not in row


async def test_an_unreadable_challenger_reply_is_unclear(tmp_path, no_network):
    """Not malformed: making it so would let the experiment's own subject role lose a
    whole contest to a DebateFailure, and the challenger's measured repair rate is 0%."""
    no_network.replies = {"challenger": "Something about this decision is off."}
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    assert (await contest(tmp_path, grid))[0]["stance"] == "unclear"
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_unclear"] is True and row["challenge_raised"] is False
    assert row["challenge_claimed_verdict"] is None
    assert "ruling_form" not in row
    # and the agreement stage has no line to compare against, so it does not spend a call
    assert (await agreement(tmp_path, grid))[0]["reason"].startswith("stance is unclear")


# --- the line-vs-prose instrument ----------------------------------------------------


async def test_the_agreement_stage_catches_a_phantom_contest(tmp_path, no_network):
    """REVERSE at the top of a response that then argues the verdict was right. With one
    relative line nothing mechanical can catch this, which is why the stage exists."""
    no_network.replies = {
        "challenger": ("Decision: REVERSE\n"
                       "The decision correctly identified the flaw in step 2."),
        "agreement": "It endorses the verdict throughout.\nProse: RIGHT",
    }
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    result = (await agreement(tmp_path, grid))[0]
    assert result["status"] == "completed"
    assert result["line"] == "REVERSE" and result["prose"] == "RIGHT"
    assert result["agrees"] is False and result["phantom"] is True
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_raised"] is True     # the label still says it contested
    assert row["phantom_contest"] is True      # and the prose says it did not


async def test_the_agreement_reader_is_never_shown_the_challengers_own_line(tmp_path,
                                                                            no_network):
    """The reading has to be independent of the label it is checking. The line was
    stripped out of ``challenge.text`` when the challenge was recorded, which is what
    makes that structural rather than a promise."""
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    await agreement(tmp_path, grid)
    sent = "".join(m["content"] for m in no_network.sent_to("agreement"))
    assert "Decision: REVERSE" not in sent and "Decision: STANDS" not in sent
    assert "Step 2 does not divide by zero" in sent   # but the prose is there


async def test_a_decline_is_measured_too_not_only_a_contest(tmp_path, no_network):
    """Measuring one direction would make the instrument agree with the column it is
    checking: a decline whose prose argues for reversal is as much a mismatch as a
    contest whose prose endorses the verdict."""
    no_network.replies = {
        "challenger": "Decision: STANDS\nThough step 2 does look wrong to me.",
        "agreement": "It argues the verdict got it wrong.\nProse: WRONG",
    }
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    result = (await agreement(tmp_path, grid))[0]
    assert result["line"] == "STANDS" and result["prose"] == "WRONG"
    assert result["agrees"] is False and result["phantom"] is False


async def test_the_agreement_stage_is_off_the_decision_path(tmp_path, no_network):
    """Costing the instrument against the condition it measures would make it part of
    what it is measuring — and would disturb the token-balance check that guards against
    "debate only won because it generated more text"."""
    from exp2.accounting import aggregate_calls

    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    await agreement(tmp_path, grid)
    contest_calls = next((tmp_path / "cells").rglob("contests/**/calls.jsonl"))
    totals = aggregate_calls(contest_calls)
    assert "agreement" in totals["by_role"]
    assert totals["by_role"]["agreement"]["calls"] == 1
    assert totals["off_path"]["calls"] >= 1


# --- the index -----------------------------------------------------------------------


async def test_the_index_joins_every_stage_and_leaves_nulls_for_missing_ones(tmp_path, no_network):
    make_decisions_wrong(no_network)
    grid = build_grid(cases(2), ["debate"])
    await decide(tmp_path, grid)

    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    assert len(rows) == 2
    # decided but not contested: the contest columns are absent, not False
    assert "challenge_raised" not in rows[0]
    assert rows[0]["initially_correct"] is False
    assert rows[0]["label_basis"] == "injected_pair"
    assert rows[0]["decision_record_words"] > 0

    await contest(tmp_path, grid)
    # "not measured" and "measured and agreed" are different facts, so the agreement
    # columns are absent until the stage has run
    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    assert "prose_stance" not in rows[0]
    await agreement(tmp_path, grid)
    await grade(tmp_path, grid)
    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    assert rows[0]["challenge_raised"] is True
    assert rows[0]["prose_stance"] == "WRONG"
    assert rows[0]["line_prose_agree"] is True
    assert rows[0]["phantom_contest"] is False
    assert rows[0]["grade_valid"] is True
    assert rows[0]["comprehension"] == 4
    assert rows[0]["ruling_form"] == "uphold_overturn"
    assert rows[0]["changed_the_decision"] is True


async def test_a_decline_indexes_as_not_revised_but_keeps_the_distinction(tmp_path, no_network):
    no_network.replies = {"challenger":
                          "Thinking: t\nArgument: Decision: STANDS\nLooks sound."}
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_raised"] is False
    assert row["challenge_declined"] is True
    assert row["changed_the_decision"] is False
    assert "ruling_form" not in row      # no ruling was sought
