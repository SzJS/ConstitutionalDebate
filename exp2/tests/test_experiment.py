"""The batch harness: resume, concurrency, isolation, and the index.

Nothing here touches the network — ``OpenRouterClient`` is monkeypatched and the API key
is removed from the environment, so a test cannot spend money even by mistake.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from conftest import FakeClient
from helpers import SECRET_THINKING, make_config, make_item, make_sides

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
    run_stage_gatekeeper,
    run_stage_grade,
    run_stage_rejudge,
    run_stage_rerule,
    run_stage_ruling_agreement,
    source_contests,
    source_decisions,
)
from pathlib import Path

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
                       "Argument: Step 2 divides by zero and the decision missed "
                       "it.\nDecision: REVERSE"),
        # The recourse judge states an absolute conclusion, so a reply that overturns a
        # SOUND decision has to SAY the text is flawed. The default fixture's judge
        # decides FLAWED and its judge concludes SOUND, which overturns there; here the
        # decisions are SOUND, so the conclusion is flipped to keep these tests measuring
        # a revision rather than an upheld decision.
        "recourse_judge": ("The objection identifies a real error.\n"
                           "Conclusion: the original text in <solution> contains a "
                           "flaw"),
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


async def contest(tmp_path, grid, **kw):
    return await run_stage_contest(grid, root=tmp_path, config=make_config(**kw),
                                   client_config=client_config(), api_key="k")


async def grade(tmp_path, grid):
    return await run_stage_grade(grid, root=tmp_path, config=make_config(),
                                 grading=GradingConfig(), client_config=client_config(),
                                 api_key="k")


async def agreement(tmp_path, grid):
    return await run_stage_agreement(grid, root=tmp_path, config=make_config(),
                                     grading=GradingConfig(),
                                     client_config=client_config(), api_key="k")


async def ruling_agreement(tmp_path, grid):
    return await run_stage_ruling_agreement(
        grid, root=tmp_path, config=make_config(), grading=GradingConfig(),
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
                          "Thinking: t\nArgument: Looks sound.\nDecision: STANDS"}
    grid = build_grid(cases(2), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    assert all(r["reason"] == "stance is declined, not contests"
               for r in await grade(tmp_path, grid))


async def test_a_decline_indexes_its_derived_verdict_and_is_not_graded(tmp_path, no_network):
    """`Decision: STANDS` against a FLAWED verdict derives a claimed FLAWED — the
    challenger no longer names it, so it cannot name it wrongly."""
    no_network.replies = {"challenger": ("The decision correctly identifies the "
                                         "error.\nDecision: STANDS")}
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
    """REVERSE on a response whose prose argues the verdict was right. With one relative
    line nothing mechanical can catch this, which is why the stage exists — and moving
    the line to the end of the reply reduces the rate but cannot make it unreachable."""
    no_network.replies = {
        "challenger": ("The decision correctly identified the flaw in step 2.\n"
                       "Decision: REVERSE"),
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
        "challenger": "Though step 2 does look wrong to me.\nDecision: STANDS",
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
    assert rows[0]["ruling_form"] == "stated_conclusion"
    assert rows[0]["changed_the_decision"] is True
    # which challenger wrote it — "neutral" unless a spec asked for advocacy
    assert rows[0]["challenge_arm"] == "neutral"


async def test_a_decline_indexes_as_not_revised_but_keeps_the_distinction(tmp_path, no_network):
    no_network.replies = {"challenger":
                          "Thinking: t\nArgument: Looks sound.\nDecision: STANDS"}
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_raised"] is False
    assert row["challenge_declined"] is True
    assert row["changed_the_decision"] is False
    assert "ruling_form" not in row      # no ruling was sought


async def test_a_partisan_contest_records_its_arm_and_is_written_from_it(tmp_path,
                                                                          no_network):
    """The variant has to reach two places or the ablation is unreadable: the prompt the
    challenger was actually sent, and the column that says so in `index.jsonl`. A run
    that set the field and still sent the neutral paragraph would be a neutral run
    filed under a partisan name."""
    make_decisions_wrong(no_network)
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid, challenger_variant="partisan_advocate")

    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_arm"] == "partisan_advocate"
    challenge_path = next((tmp_path / "cells").rglob("challenge.json"))
    assert json.loads(challenge_path.read_text())["arm"] == "partisan_advocate"
    # and the run says so too: a contest's own config.json is the DECIDER's, copied,
    # so the manifest is where a contest-only setting has to be written down
    run = json.loads((challenge_path.parent / "run.json").read_text())
    assert run["challenger_variant"] == "partisan_advocate"
    sent = [c for c in no_network.calls if c["meta"].get("role") == "challenger"]
    assert sent and all("You represent the side this decision went against"
                        in c["messages"][0]["content"] for c in sent)
    assert not any("You are not required to find fault" in c["messages"][0]["content"]
                   for c in sent)


# --- the judgment variant -------------------------------------------------------------

# The `Judgment says:` quote is a VERBATIM span of the fake judge's reply
# (`conftest.DEFAULT_REPLIES["judge"]`), so this objection passes the quote check and
# reaches the grader whole. A quote that missed would be ruled INVALID without a call —
# which is the subject of its own test below, not of these.
JUDGMENT_OBJECTION = (
    "1. Type: misstatement\n"
    '   Judgment says: "the sound side did not"\n'
    '   Record says: "Bob: I do not answer step 2"\n'
    "   Why it matters: the verdict rests on an answer nobody gave.\n"
    "2. Type: omission\n"
    "   Judgment says: (the judgment does not address this)\n"
    '   Record says: "Alice: step 2 divides by zero"\n'
    "   Why it matters: it is the point the verdict turned on.\n"
    "Decision: REVERSE"
)

JUDGMENT_GRADE = (
    "The first quote is not in the record; the second point is addressed.\n"
    "Defect 1: VALID — the record does not say that.\n"
    "Defect 2: INVALID — the judgment does address it.\n"
    "Valid objection: YES"
)


async def test_a_judgment_contest_is_graded_on_a_cell_the_flaw_grader_would_skip(
    tmp_path, no_network
):
    """The three gates the flaw grader applies — sound item, no annotation, correct
    decision — all fall away here, because validity is a property of the objection
    against the RECORD. This cell is decided CORRECTLY (the fake judge answers FLAWED on
    a flawed item), which the flaw grader skips as off-metric; under the judgment mode a
    defect in the reasoning is a real finding whichever verdict it reached.

    And the mode is read off `challenge.json`: the grade stage below runs with a config
    whose variant is the default `neutral`, exactly as a re-grade of someone else's tree
    would, and must still grade this objection as the audit it is."""
    no_network.replies = {"challenger": JUDGMENT_OBJECTION,
                          "judgment_grader": JUDGMENT_GRADE}
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid, challenger_variant="judgment")

    challenge = json.loads(
        next((tmp_path / "cells").rglob("challenge.json")).read_text())
    assert challenge["arm"] == "judgment"
    assert [d["type"] for d in challenge["defects"]] == ["misstatement", "omission"]
    assert challenge["defects"][0]["record_says"] == ['"Bob: I do not answer step 2"']

    results = await grade(tmp_path, grid)      # neutral config, judgment challenge
    assert results[0]["status"] == "completed"
    assert results[0]["mode"] == "judgment"
    graded = json.loads(next((tmp_path / "cells").rglob("grade.json")).read_text())
    assert graded["mode"] == "judgment"
    assert graded["valid"] is True
    assert graded["defects_n"] == 2 and graded["defects_valid_n"] == 1
    assert [d["type"] for d in graded["defects"]] == ["misstatement", "omission"]
    assert graded["line_mismatch"] is False
    # the grader was shown the record and the judgment, and never the annotation
    sent = "".join(
        m["content"] for c in no_network.calls
        if c["meta"]["role"] == "judgment_grader" for m in c["messages"])
    assert "Alice argues in round 1." in sent
    assert "Step 2 miscounts." not in sent

    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["initially_correct"] is True       # the flaw grader would have skipped it
    assert row["challenge_arm"] == "judgment"
    assert row["grade_mode"] == "judgment"
    assert row["grade_valid"] is True
    assert row["grade_defects_n"] == 2
    assert row["grade_defects_valid_n"] == 1
    assert row["grade_line_mismatch"] is False
    # the flaw grader's two columns are absent rather than nulled: this row was never
    # scored against an annotation and a null would read as "graded and missed"
    assert "identified_flaw" not in row and "characterises_the_flaw" not in row
    # both quotes check out against the judgment, so nothing was skipped
    assert row["challenge_defects_n"] == 2
    assert row["challenge_defects_misattributed_n"] == 0


async def test_a_misattributed_quote_is_counted_in_the_index_and_never_graded(
    tmp_path, no_network
):
    """End to end, on the shape the slice found in a quarter of nano's objections: a
    defect quoting a judgment that does not say it. The check runs when the objection is
    parsed, the index counts it, and the grader is never asked — which is what the two
    new columns exist to make visible on every run rather than only in a hand read."""
    from exp2.grading import QUOTE_NOT_IN_JUDGMENT

    no_network.replies = {
        "challenger": (
            "1. Type: misstatement\n"
            '   Judgment says: "Bob conceded that step 2 divides by zero"\n'
            '   Record says: "Bob: I concede nothing"\n'
            "2. Type: omission\n"
            "   Judgment says: (the judgment does not address this)\n"
            '   Record says: "Alice: step 2 divides by zero"\n'
            "Decision: REVERSE"),
        "judgment_grader": ("Defect 2: VALID — the judgment is silent on it.\n"
                            "Valid objection: YES"),
    }
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid, challenger_variant="judgment")

    challenge = json.loads(
        next((tmp_path / "cells").rglob("challenge.json")).read_text())
    assert [d["quote_in_judgment"] for d in challenge["defects"]] == [False, None]

    await grade(tmp_path, grid)
    graded = json.loads(next((tmp_path / "cells").rglob("grade.json")).read_text())
    assert [(d["index"], d["valid"], d["reason"]) for d in graded["defects"]] == [
        (1, False, QUOTE_NOT_IN_JUDGMENT),
        (2, True, "the judgment is silent on it."),
    ]
    sent = "".join(m["content"] for c in no_network.calls
                   if c["meta"]["role"] == "judgment_grader" for m in c["messages"])
    assert "Defect 1 has already been checked" in sent

    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["challenge_defects_n"] == 2
    assert row["challenge_defects_misattributed_n"] == 1
    # and a neutral objection is not asked for quotes, so it has neither column
    neutral = build_grid(cases(1), ["single"])
    await decide(tmp_path, neutral)
    await contest(tmp_path, neutral)
    other = [r for r in build_index(neutral, root=tmp_path,
                                    challenger_model="strong/model")
             if r["condition"] == "single"][0]
    assert "challenge_defects_n" not in other


async def test_a_sound_item_is_graded_under_the_judgment_mode(tmp_path, no_network):
    """Where `test_a_sound_item_is_never_graded` skips. There is no recorded flaw and
    none is wanted — the quotes are checked against the record."""
    no_network.replies = {"challenger": JUDGMENT_OBJECTION,
                          "judgment_grader": JUDGMENT_GRADE}
    grid = build_grid(cases(1, gold_flawed=False), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid, challenger_variant="judgment")
    results = await grade(tmp_path, grid)
    assert results[0]["status"] == "completed"
    assert json.loads(
        next((tmp_path / "cells").rglob("grade.json")).read_text())["mode"] == "judgment"


async def test_a_judgment_objection_is_read_with_the_judgment_agreement_question(
    tmp_path, no_network
):
    """Off the challenge's own arm, so a re-read of a finished tree cannot ask the
    verdict-shaped question of an audit — which would answer NEITHER for exactly the
    replies this variant produces."""
    no_network.replies = {"challenger": JUDGMENT_OBJECTION}
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid, challenger_variant="judgment")
    await agreement(tmp_path, grid)             # neutral config again

    sent = "".join(m["content"] for c in no_network.calls
                   if c["meta"]["role"] == "agreement" for m in c["messages"])
    assert "audit those reasons — the judgment" in sent
    assert "Does this text argue that the verdict was **right**" not in sent
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["prose_stance"] == "WRONG"       # the fake reader's default


# --- a tree that contests another tree's decisions ------------------------------------


def _tree_fingerprint(root) -> list[tuple[str, str]]:
    """Every file under ``root``, with its sha256. The whole guarantee in one list."""
    import hashlib

    return sorted(
        (str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob("*") if p.is_file()
    )


async def test_a_contest_tree_reads_decisions_elsewhere_and_never_writes_there(tmp_path):
    """The re-contest's whole safety property: the sweep's 5,724 decisions are contested
    under a changed protocol and not one byte of the tree holding them changes.

    `experiment.json` is overwritten on every invocation and `cells.jsonl` is
    append-only with no run discriminator, so a second contest inside the source tree
    would silently rewrite the record of what the first one ran.
    """
    decisions, contests = tmp_path / "A", tmp_path / "B"
    grid = build_grid(cases(2), ["debate", "single"])
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    before = _tree_fingerprint(decisions)
    assert before

    for stage in (
        lambda: run_stage_contest(grid, root=contests, config=make_config(),
                                  client_config=client_config(), api_key="k",
                                  decision_root=decisions),
        lambda: run_stage_agreement(grid, root=contests, config=make_config(),
                                    grading=GradingConfig(),
                                    client_config=client_config(), api_key="k",
                                    decision_root=decisions),
        lambda: run_stage_grade(grid, root=contests, config=make_config(),
                                grading=GradingConfig(),
                                client_config=client_config(), api_key="k",
                                decision_root=decisions),
    ):
        results = await stage()
        assert not any(r.get("reason") in ("no decision to contest", "no decision",
                                           "no decision to grade against")
                       for r in results)

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=decisions)
    assert len(rows) == 4
    assert all(row["challenge_raised"] is True for row in rows)
    assert all(row["prose_stance"] == "WRONG" for row in rows)

    assert _tree_fingerprint(decisions) == before
    # ... and the contests really are in the other tree
    assert (contests / "cells").is_dir()
    assert any((contests / "cells").rglob("challenge.json"))
    assert not any((decisions / "cells").rglob("challenge.json"))


async def test_a_contest_tree_without_the_decision_root_finds_no_decisions(tmp_path):
    """The failure the flag prevents, shown: pointed at its own empty tree, the same
    stage silently contests nothing rather than reading the source."""
    decisions, contests = tmp_path / "A", tmp_path / "B"
    grid = build_grid(cases(1), ["debate"])
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    results = await run_stage_contest(grid, root=contests, config=make_config(),
                                      client_config=client_config(), api_key="k")
    assert all(r["reason"] == "no decision to contest" for r in results)


def test_a_contest_trees_experiment_json_names_the_tree_it_contested(tmp_path,
                                                                    monkeypatch):
    """A record that says "the sweep's decisions" and nothing else would be a path that
    may since have been re-run under the same name. The hash pins which run it was."""
    import hashlib

    from exp2.experiment_cli import main

    source = tmp_path / "outputs" / "experiments" / "sweep"
    source.mkdir(parents=True)
    (source / "experiment.json").write_text('{"name": "sweep"}', encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        "\n".join(json.dumps(c.to_dict()) for c in cases(1)),
        encoding="utf-8")
    spec = tmp_path / "recontest.toml"
    spec.write_text(
        'name = "recontest-x"\n'
        f'cases = "{cases_path}"\n'
        'conditions = ["debate"]\n'
        f'decisions_from = "{source}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["--spec", str(spec), "--stage", "analyse"]) == 0
    written = json.loads(
        (tmp_path / "outputs" / "experiments" / "recontest-x" / "experiment.json")
        .read_text())
    assert written["decisions_from"] == str(source)
    assert written["decisions_from_experiment_sha256"] == hashlib.sha256(
        (source / "experiment.json").read_bytes()).hexdigest()
    # and the source tree still holds exactly the one file it started with
    assert [p.name for p in source.rglob("*")] == ["experiment.json"]


def test_a_spec_that_contests_another_tree_refuses_to_decide(tmp_path, monkeypatch):
    """`decide` would build a second, differently-decided grid under the new name — and
    the point of the re-contest is that the decisions are the sweep's, unchanged."""
    from exp2.experiment_cli import main

    spec = tmp_path / "recontest.toml"
    spec.write_text(
        'name = "recontest-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "decide"])
    assert "it does not decide" in str(excinfo.value)


# --- the ruling's line-vs-prose instrument --------------------------------------------


async def test_the_ruling_agreement_stage_reads_every_ruling_and_skips_declines(
    tmp_path, no_network
):
    """One grader call per recorded ruling, whatever form it is: the sweep's and the
    re-contest's 1,586 were written under the old relative line and are exactly what has
    to be measured on the same scale as the new ones. A cell that was never objected to
    has no line to check, which is a different fact from a line that checked out."""
    no_network.replies = {
        "challenger": "Step 2 is wrong.\nDecision: REVERSE",
        "recourse_judge": ("The objection lands.\n"
                           "Conclusion: the original text in <solution> does not "
                           "contain a flaw"),
        "ruling_reader": "It concludes the text is fine.\nReading: SOUND",
    }
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    result = (await ruling_agreement(tmp_path, grid))[0]
    assert result["status"] == "completed"
    assert result["line"] == "SOUND" and result["prose"] == "SOUND"
    assert result["mismatch"] is False and result["form"] == "stated_conclusion"
    # ... and it resumes on its own artifact
    assert (await ruling_agreement(tmp_path, grid))[0]["reason"] == "already measured"

    declined = tmp_path / "declined"
    no_network.replies["challenger"] = "Looks sound to me.\nDecision: STANDS"
    await decide(declined, grid)
    await contest(declined, grid)
    assert (await ruling_agreement(declined, grid))[0]["reason"] == "no ruling to read"


async def test_the_ruling_agreement_stage_catches_a_line_its_prose_contradicts(
    tmp_path, no_network
):
    """The failure it exists to count, and the one the re-contest's hand check found 8 of
    in 12: the judge's reasoning concludes the text is flawed and the recorded outcome
    says SOUND. Every `revised_*` rate is bounded by this number."""
    no_network.replies = {
        "challenger": "Step 2 is wrong.\nDecision: REVERSE",
        "recourse_judge": ("The objection identifies a real error in step 2.\n"
                           "Conclusion: the original text in <solution> does not "
                           "contain a flaw"),
        "ruling_reader": "It finds a real error in step 2.\nReading: FLAWED",
    }
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    result = (await ruling_agreement(tmp_path, grid))[0]
    assert result["line"] == "SOUND" and result["prose"] == "FLAWED"
    assert result["mismatch"] is True
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["changed_the_decision"] is True        # the record still says revised
    assert row["ruling_prose_conclusion"] == "FLAWED"
    assert row["ruling_line_mismatch"] is True        # and the prose says it did not


async def test_the_ruling_agreement_columns_are_absent_until_the_stage_has_run(
    tmp_path, no_network
):
    """"not measured" and "measured and consistent" are different facts, on the same rule
    the agreement columns follow."""
    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert "ruling_line_mismatch" not in row
    await ruling_agreement(tmp_path, grid)
    row = build_index(grid, root=tmp_path, challenger_model="strong/model")[0]
    assert row["ruling_line_mismatch"] is False


async def test_the_ruling_agreement_stage_is_off_the_decision_path(tmp_path, no_network):
    """The rule bites harder here than for the challenger's probe: the thing being
    measured IS the decision path's last step, and a reader billed to that step would be
    measuring itself."""
    from exp2.accounting import aggregate_calls

    grid = build_grid(cases(1), ["debate"])
    await decide(tmp_path, grid)
    await contest(tmp_path, grid)
    await ruling_agreement(tmp_path, grid)
    contest_calls = next((tmp_path / "cells").rglob("contests/**/calls.jsonl"))
    totals = aggregate_calls(contest_calls)
    assert totals["by_role"]["ruling_reader"]["calls"] == 1
    assert "ruling_reader" not in totals["decision_path"]


# --- re-ruling another tree's contests ------------------------------------------------


async def _three_trees(tmp_path, no_network):
    """A → decisions, B → contests of them, and a grid. C is the caller's to make."""
    make_decisions_wrong(no_network)
    grid = build_grid(cases(2), ["debate", "single"])
    decisions, contests = tmp_path / "A", tmp_path / "B"
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    await run_stage_contest(grid, root=contests, config=make_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    await run_stage_grade(grid, root=contests, config=make_config(),
                          grading=GradingConfig(), client_config=client_config(),
                          api_key="k", decision_root=decisions)
    return grid, decisions, contests


async def test_a_rerule_tree_re_rules_every_contested_cell_and_writes_nowhere_else(
    tmp_path, no_network
):
    """The whole safety property of the re-rule, and the reason it exists at all: 1,586
    objections that cost real money get a second ruling under the changed prompt, and not
    one byte of either tree holding them changes."""
    grid, decisions, contests = await _three_trees(tmp_path, no_network)
    rerules = tmp_path / "C"
    before_a, before_b = _tree_fingerprint(decisions), _tree_fingerprint(contests)

    results = await run_stage_rerule(
        grid, root=rerules, config=make_config(), client_config=client_config(),
        api_key="k", decision_root=decisions, contest_root=contests)
    assert [r["status"] for r in results] == ["completed"] * 4
    # The two conditions were ruled by different mechanisms in B — `debate` by the
    # third-party judge, `single` by the model that decided, in its own conversation —
    # and BOTH are re-ruled here by the judge. That is the paired comparison the whole
    # exercise is for: the same objections, one ruler.
    assert {r["was"] for r in results} == {"stated_conclusion", "restated_verdict"}
    assert all(r["now"] == "stated_conclusion" for r in results)

    rulings = sorted(rerules.rglob("cells/*/contests/*/runs/*/ruling.json"))
    assert len(rulings) == 4
    for path in rulings:
        ruling = json.loads(path.read_text())
        assert ruling["form"] == "stated_conclusion"
        assert ruling["conclusion_line"].startswith("Conclusion:")
        # the objection, its grade and the copied decision came across; the old ruling
        # is beside the new one rather than gone
        directory = path.parent
        assert (directory / "challenge.json").is_file()
        assert (directory / "grade.json").is_file()
        assert (directory / "parent" / "verdict.json").is_file()
        assert (directory / "ruling.source.json").is_file()
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["kind"] == "rerule"
        assert manifest["rerule_of_form"] in ("stated_conclusion", "restated_verdict")
        assert Path(manifest["source_contest_dir"]).is_relative_to(contests)
        assert len(manifest["source_sha256"]) == 64

    # The wire log is THIS run's. The source contest's calls.jsonl held a challenger and
    # a comprehension probe; copying it would make the full document print the old
    # judge's prompt as though it were this ruling's. (The offline fixture shares one
    # fake client across concurrent cells, so the four records may land in one file —
    # what is asserted is that there are four of them and that every one is the ruling.)
    logged = [json.loads(line)
              for path in rerules.glob("cells/*/contests/*/runs/*/calls.jsonl")
              for line in path.read_text().splitlines()]
    assert len(logged) == 4
    assert {record["role"] for record in logged} == {"recourse_judge"}

    assert _tree_fingerprint(decisions) == before_a
    assert _tree_fingerprint(contests) == before_b
    # and it resumes on the ruling it wrote
    again = await run_stage_rerule(
        grid, root=rerules, config=make_config(), client_config=client_config(),
        api_key="k", decision_root=decisions, contest_root=contests)
    assert all(r["reason"] == "already re-ruled" for r in again)


async def test_a_rerule_skips_a_cell_whose_source_objection_declined(tmp_path,
                                                                     no_network):
    """A decline put nothing to a judge, so there is no ruling to re-make. Skipped by
    name rather than silently, because "declined" and "we forgot" have to stay apart."""
    no_network.replies = {"challenger": "Looks sound.\nDecision: STANDS"}
    grid = build_grid(cases(1), ["debate"])
    decisions, contests, rerules = tmp_path / "A", tmp_path / "B", tmp_path / "C"
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    await run_stage_contest(grid, root=contests, config=make_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    assert source_contests(grid, source_root=contests,
                           challenger_model="strong/model") == []
    results = await run_stage_rerule(
        grid, root=rerules, config=make_config(), client_config=client_config(),
        api_key="k", decision_root=decisions, contest_root=contests)
    assert [r["reason"] for r in results] == ["no objection to re-rule"]
    assert not list(rerules.rglob("ruling.json"))


async def test_a_rerule_tree_analyses_without_a_grade_stage(tmp_path, no_network):
    """The grade is of the OBJECTION, and the objection has not changed — so it is copied
    through and `grade` never runs on a re-rule spec. If it did not come across, every
    validity rate in the re-rule's own metrics would read 0/N."""
    grid, decisions, contests = await _three_trees(tmp_path, no_network)
    rerules = tmp_path / "C"
    await run_stage_rerule(
        grid, root=rerules, config=make_config(), client_config=client_config(),
        api_key="k", decision_root=decisions, contest_root=contests)
    await run_stage_ruling_agreement(
        grid, root=rerules, config=make_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k")
    rows = build_index(grid, root=rerules, challenger_model="strong/model",
                       decision_root=decisions)
    assert len(rows) == 4
    assert all(r["grade_valid"] is True for r in rows)
    assert all(r["ruling_form"] == "stated_conclusion" for r in rows)
    assert all(r["ruling_line_mismatch"] is not None for r in rows)


# --- the M4 admissibility gate (POST HOC, 2026-08-28) ---------------------------------
#
# It is the narrowest stage in the harness: it copies a finished contest WITH its ruling
# and adds one file. Nothing is re-made, so every test below is really about two things —
# that the copy is complete, and that the after-state arithmetic happens in the index and
# not in the tree.


REFUSED_GATE = ("Neither quotation is in the document it is attributed to.\n"
                "Defect 1: NOT REAL — the record does not contain that sentence.\n"
                "Admissibility: REFUSED")

# One numbered defect, so the gatekeeper's `Defect 1:` finding has a defect to be joined
# to. The conftest default challenger writes prose and no list, and a finding joined to
# nothing would test the join by not exercising it.
GATED_OBJECTION = (
    "Thinking: I read the judgment against the record.\n"
    "Argument:\n"
    "1. Type: misstatement\n"
    '   Judgment says: "The sound side answered the objection"\n'
    '   Record says: "Alice round 1 argument."\n'
    "   Why it matters: the judgment attributes an answer nobody gave.\n"
    "Decision: REVERSE"
)


def _gate_config(**kw):
    base = dict(challenger_variant="judgment", recourse_form="third_party",
                gatekeeper_model="gate/model")
    base.update(kw)
    return make_config(**base)


async def test_the_gate_adds_an_admission_and_replaces_nothing(tmp_path, no_network):
    """The safety property, and it is stricter than the re-rule's: a re-rule replaces the
    ruling, and this replaces NOTHING. The objection, its ruling, its grade and the copied
    decision all come across intact, one `admission.json` is added beside them, and the
    two trees it read are byte-identical afterwards."""
    grid, decisions, source = await _source_arm(tmp_path, no_network,
                                                challenger_reply=GATED_OBJECTION)
    root = tmp_path / "C"
    before_a, before_b = _tree_fingerprint(decisions), _tree_fingerprint(source)

    results = await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    assert [r["status"] for r in results] == ["completed"] * 3
    assert all(r["admitted"] is True for r in results)

    admissions = sorted(root.rglob("cells/*/contests/*/runs/*/admission.json"))
    assert len(admissions) == 3
    for path in admissions:
        admission = json.loads(path.read_text())
        assert admission["admitted"] is True
        assert admission["line_admitted"] is True
        assert admission["line_mismatch"] is False
        assert admission["model"] == "gate/model"
        assert admission["parse_mode"] == "strict"
        assert admission["findings"][0]["real"] is True
        # joined to the challenger's own defect list by the number both used
        assert admission["findings"][0]["type"] == "misstatement"
        assert admission["findings"][0]["alleged"] is True
        assert admission["cost_usd"] >= 0.0
        directory = path.parent
        # THE RULING CAME ACROSS. This is the one line that separates a gate from a
        # re-rule: the ruling is what the gate decides whether to count, so a gate tree
        # with no ruling in it could not be read at all.
        assert (directory / "ruling.json").is_file()
        assert not (directory / "ruling.source.json").exists()
        assert (directory / "challenge.json").is_file()
        assert (directory / "parent" / "verdict.json").is_file()
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["kind"] == "gate"
        assert manifest["gate_admitted"] is True
        assert manifest["gatekeeper_model"] == "gate/model"
        assert Path(manifest["source_contest_dir"]).is_relative_to(source)
        assert len(manifest["source_sha256"]) == 64

    # the wire log is THIS run's one call, and the source's is kept beside it verbatim
    logged = [json.loads(line)
              for path in root.glob("cells/*/contests/*/runs/*/calls.jsonl")
              for line in path.read_text().splitlines()]
    assert len(logged) == 3
    assert {record["role"] for record in logged} == {"gatekeeper"}
    # (the offline fixture shares one fake client across concurrent cells, so a
    # source contest may have had no calls.jsonl of its own to rename)
    assert any((path.parent / "calls.source.jsonl").is_file()
               for path in admissions)
    # AND THE GATE CALL IS OFF THE DECISION PATH, so it cannot inflate what it gates.
    #
    # Summed over every wire log in the tree rather than read out of one cell's, for the
    # reason the `calls.source.jsonl` line above already gives: the offline fixture shares
    # ONE FakeClient across concurrent cells and hands it whichever writer's sink entered
    # last, so all three records can land in one directory's `calls.jsonl` and another's
    # may not exist at all. Which cell wins that race is asyncio scheduling, so an
    # assertion about `admissions[0]`'s own log is a coin toss. What is true of the STAGE,
    # and is what this check is for, is true of the union: three gatekeeper calls, none of
    # them on the decision path.
    from exp2.accounting import aggregate_calls

    per_run = [aggregate_calls(path) for path in
               sorted(root.glob("cells/*/contests/*/runs/*/calls.jsonl"))]
    assert sum(t["by_role"].get("gatekeeper", {}).get("calls", 0)
               for t in per_run) == 3
    assert all(set(t["by_role"]) == {"gatekeeper"} for t in per_run)
    # every one of them counted OFF the path: the decision-path half of each log is empty
    assert all(t["decision_path"]["calls"] == 0 for t in per_run)
    assert sum(t["off_path"]["calls"] for t in per_run) == 3
    # temperature 0 and reasoning off, pinned at the call site rather than inherited
    gate_calls = [c for c in no_network.calls if c["meta"]["role"] == "gatekeeper"]
    assert {c["temperature"] for c in gate_calls} == {0.0}

    assert _tree_fingerprint(decisions) == before_a
    assert _tree_fingerprint(source) == before_b
    # and it resumes on the admission it wrote
    again = await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    assert all(r["reason"] == "already gated" for r in again)


async def test_a_refused_objection_leaves_the_cell_at_its_before_state(tmp_path,
                                                                       no_network):
    """THE AFTER-STATE RULE, and it is the whole arm. The ruling is untouched — it still
    says what it said and `ruling_form` is still written — and `final_correct` is the
    DECISION's own verdict, because the objection was never heard. A gated index whose
    `final_correct` still counted every ruling would be the source arm's index under a
    different name."""
    grid, decisions, source = await _source_arm(tmp_path, no_network)
    no_network.replies["gatekeeper"] = REFUSED_GATE
    root = tmp_path / "C"
    results = await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    assert all(r["admitted"] is False for r in results)

    rows = build_index(grid, root=root, challenger_model="strong/model",
                       decision_root=decisions)
    assert len(rows) == 3
    for row in rows:
        assert row["gate_admitted"] is False
        assert row["gate_model"] == "gate/model"
        assert row["gate_findings_n"] == 1 and row["gate_findings_real_n"] == 0
        # the decision was wrong and the source's ruling overturned it; refused, the
        # cell keeps the wrong decision it started with
        assert row["initially_correct"] is False
        assert row["ruling_form"] == "stated_conclusion"
        assert row["changed_the_decision"] is False
        assert row["final_correct"] is False

    # and with the SAME rulings admitted, the same cells are fixed — so the difference
    # between the two indexes is the gate and nothing else
    admitted_root = tmp_path / "D"
    del no_network.replies["gatekeeper"]
    await run_stage_gatekeeper(
        grid, root=admitted_root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    admitted_rows = build_index(grid, root=admitted_root,
                                challenger_model="strong/model",
                                decision_root=decisions)
    assert all(r["gate_admitted"] is True for r in admitted_rows)
    assert all(r["final_correct"] is True for r in admitted_rows)
    assert all(r["changed_the_decision"] is True for r in admitted_rows)


async def test_the_gated_index_says_in_words_that_it_moved_the_after_state(tmp_path,
                                                                           no_network):
    """A column computed rather than read has to announce itself. The caveat names the
    gate model, says the after-state is the ruling's outcome only where it admitted, and
    says the two things that make M4 an ablation: it is post hoc, and it is a model."""
    from exp2.analysis import caveats

    grid, decisions, source = await _source_arm(tmp_path, no_network)
    no_network.replies["gatekeeper"] = REFUSED_GATE
    root = tmp_path / "C"
    await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    rows = build_index(grid, root=root, challenger_model="strong/model",
                       decision_root=decisions)
    stated = [c for c in caveats(rows, ["debate"]) if "ADMISSIBILITY GATE" in c]
    assert len(stated) == 1
    assert "gate/model" in stated[0]
    assert "MOVES" in stated[0] and "`final_correct`" in stated[0]
    assert "0 of 3" in stated[0]
    assert "POST HOC" in stated[0]
    assert "No ruling was re-made" in stated[0]
    # an ungated index says nothing about a gate at all
    ungated = build_index(grid, root=source, challenger_model="strong/model",
                          decision_root=decisions)
    assert not any("ADMISSIBILITY GATE" in c for c in caveats(ungated, ["debate"]))


async def test_the_gate_spends_one_repair_on_a_reply_with_no_admissibility_line(
    tmp_path, no_network
):
    """One repair and no more, as every role gets. The repaired reply is parsed and the
    record says a repair was spent, so a run's own gate-repair rate is a column and not
    something a reader has to infer."""
    grid, decisions, source = await _source_arm(tmp_path, no_network)
    no_network.fail_on = {"gatekeeper": "malformed"}
    root = tmp_path / "C"
    results = await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    assert [r["status"] for r in results] == ["completed"] * 3
    for path in root.rglob("admission.json"):
        assert json.loads(path.read_text())["repair_attempts"] == 1
    # and the repair asked for the gate's OWN format, not the grader's
    repairs = [c for c in no_network.calls
               if c["meta"]["role"] == "gatekeeper"
               and c["meta"].get("purpose") == "repair"]
    assert repairs
    sent = repairs[0]["messages"][-1]["content"]
    assert "Admissibility: <ADMITTED|REFUSED>" in sent
    assert "Valid objection" not in sent


async def test_the_gate_skips_a_declined_objection_and_needs_a_model(tmp_path,
                                                                     no_network):
    """A decline put nothing to a judge, so there is no ruling to gate — skipped by name.
    And the stage refuses ONCE, before any cell, when no gatekeeper is named: it inherits
    from no other field, because the only neighbour to inherit from is the judge whose own
    judgment is under appeal."""
    no_network.replies = {"challenger": "Looks sound.\nDecision: STANDS"}
    grid = build_grid(cases(1), ["debate"])
    decisions, source, root = tmp_path / "A", tmp_path / "B", tmp_path / "C"
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    await run_stage_contest(grid, root=source,
                            config=make_config(challenger_variant="judgment",
                                               recourse_form="third_party"),
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    results = await run_stage_gatekeeper(
        grid, root=root, config=_gate_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    assert [r["reason"] for r in results] == ["no objection to gate"]
    assert not list(root.rglob("admission.json"))

    with pytest.raises(ValueError, match="needs `gatekeeper_model`"):
        await run_stage_gatekeeper(
            grid, root=root, config=make_config(challenger_variant="judgment"),
            grading=GradingConfig(), client_config=client_config(), api_key="k",
            decision_root=decisions, contest_root=source)


def test_the_gatekeeper_stage_refuses_a_spec_with_no_source_and_no_model(tmp_path,
                                                                         monkeypatch):
    """Both refusals are one-line SystemExits before anything is spent: a gate with no
    objections to read would report success having measured nothing, and a gate with no
    model would fall back to the judge."""
    from exp2.experiment_cli import main

    spec = tmp_path / "gate.toml"
    spec.write_text(
        'name = "gate-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "gatekeeper"])
    assert "needs `contests_from" in str(excinfo.value)

    spec.write_text(
        'name = "gate-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n'
        f'contests_from = "{tmp_path / "B"}"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "gatekeeper"])
    assert "needs `gatekeeper_model`" in str(excinfo.value)
    assert "would have the judge decide" in str(excinfo.value)

    # and a `contests_from` spec still refuses the three stages that would REWRITE the
    # objection — the gate is not a loophole into them
    for stage in ("contest", "agreement", "grade"):
        with pytest.raises(SystemExit) as excinfo:
            main(["--spec", str(spec), "--stage", stage])
        assert "it does not contest" in str(excinfo.value)


def test_a_spec_that_names_a_gatekeeper_quotes_its_calls_in_the_estimate(tmp_path,
                                                                         monkeypatch,
                                                                         capsys):
    """The estimate is the line a run is approved from, and the gate term is COUNTED off
    the source tree rather than bounded by the grid — on the sweep the two differ by a
    factor of five."""
    from exp2.experiment_cli import main

    outputs = tmp_path / "outputs" / "experiments"
    for name in ("src-decisions", "src-contests"):
        (outputs / name).mkdir(parents=True)
        (outputs / name / "experiment.json").write_text(
            json.dumps({"name": name}), encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n".join(json.dumps(c.to_dict()) for c in cases(2)),
                          encoding="utf-8")
    spec = tmp_path / "gate.toml"
    spec.write_text(
        'name = "gate-x"\n'
        f'cases = "{cases_path}"\n'
        'conditions = ["debate"]\n'
        f'decisions_from = "{outputs / "src-decisions"}"\n'
        f'contests_from = "{outputs / "src-contests"}"\n'
        '[debate]\n'
        'gatekeeper_model = "gate/model"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["--spec", str(spec), "--stage", "gatekeeper", "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "gatekeeper <= 0" in printed          # the source contested nothing yet
    assert "the gatekeeper term is COUNTED, not bounded" in printed
    assert "gate/model" in printed
    assert "POST HOC" in printed


async def test_the_mechanical_gate_admits_only_objections_whose_quotes_all_exist(
    tmp_path, no_network
):
    """`records/derivations/jd3-gates.py`, over real records rather than a fixture.

    POST HOC, and no model reads anything: an objection is admitted iff every `Judgment
    says:` quotation is in the judgment AND every `Record says:` quotation is in the
    record the challenger was shown. It is the LOWER bound of the three gate rows — the
    weakest filter there is, asking only whether the evidence exists.

    Three cells, one per branch: every quotation verbatim, a record quotation that is in
    nothing, and a judgment quotation that is in nothing (which the harness's own
    parse-time check already caught, and which this recomputes rather than reads).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "jd3_gates", Path(__file__).resolve().parent.parent / "records" / "derivations"
        / "jd3-gates.py")
    gates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gates)

    def objection(judgment_quote, record_quote):
        return ("Thinking: reading the two documents.\n"
                "Argument:\n"
                "1. Type: misstatement\n"
                f'   Judgment says: "{judgment_quote}"\n'
                f'   Record says: "{record_quote}"\n'
                "   Why it matters: it bears on the verdict.\n"
                "Decision: REVERSE")

    # what the fake judge and the fake debaters actually wrote, so a "verbatim" quotation
    # here really is verbatim
    real_judgment = "The sound side answered the objection"
    real_record = "Alice argues in round 1"
    invented = "nothing in either document says anything like this"

    make_decisions_wrong(no_network)
    grid = build_grid(cases(3), ["debate"])
    decisions, source = tmp_path / "A", tmp_path / "B"
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    replies = [objection(real_judgment, real_record),      # admitted
               objection(real_judgment, invented),         # refused on the record half
               objection(invented, real_record)]           # refused on the judgment half
    for cell, reply in zip(grid, replies):
        no_network.replies["challenger"] = reply
        await run_stage_contest([cell], root=source,
                                config=make_config(challenger_variant="judgment",
                                                   recourse_form="third_party"),
                                client_config=client_config(), api_key="k",
                                decision_root=decisions)

    out = tmp_path / "gates.jsonl"
    assert gates.main(["--tree", str(source), "--out", str(out)]) == 0
    rows = {r["cell_id"]: r for r in
            (json.loads(line) for line in out.read_text().splitlines())}
    assert len(rows) == 3
    by_cell = [rows[cell.cell_id] for cell in grid]

    assert by_cell[0]["mech_admitted"] is True
    assert by_cell[0]["defects"][0]["judgment_quotes_ok"] is True
    assert by_cell[0]["defects"][0]["record_quotes_ok"] is True

    assert by_cell[1]["mech_admitted"] is False
    assert by_cell[1]["defects_failing_record_quotes"] == 1
    assert by_cell[1]["defects_failing_judgment_quotes"] == 0
    # the RECORD half is the new one, so an objection the pre-registered check passed and
    # this one refuses is exactly what the row adds
    assert by_cell[1]["defects"][0]["judgment_quotes_ok"] is True

    assert by_cell[2]["mech_admitted"] is False
    assert by_cell[2]["defects_failing_judgment_quotes"] == 1

    # the recomputed judgment flag agrees with the one the harness stored at parse time —
    # one comparison made once by one rule, not two rules that happen to agree today
    for row in by_cell:
        for flag in row["defects"]:
            assert flag["judgment_quotes_ok"] == flag["judgment_flag_stored"]

    # a DECLINE is not gated: it put nothing to a judge, so there is no ruling to admit
    no_network.replies["challenger"] = "Looks sound.\nDecision: STANDS"
    declined = build_grid(cases(4)[3:], ["debate"])
    await run_stage_decide(declined, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    await run_stage_contest(declined, root=source,
                            config=make_config(challenger_variant="judgment",
                                               recourse_form="third_party"),
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    assert gates.main(["--tree", str(source), "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 3

    # and the tree it read is opened for reading only
    assert not list(source.rglob("*gates*"))


def test_a_spec_that_re_rules_another_tree_refuses_to_contest(tmp_path, monkeypatch):
    """`contest` would write a NEW objection over the copy this tree holds, and then the
    rulings would be of objections the source never made."""
    from exp2.experiment_cli import main

    spec = tmp_path / "rerule.toml"
    spec.write_text(
        'name = "rerule-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n'
        f'contests_from = "{tmp_path / "B"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for stage in ("contest", "agreement", "grade"):
        with pytest.raises(SystemExit) as excinfo:
            main(["--spec", str(spec), "--stage", stage])
        assert "it does not contest" in str(excinfo.value)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "decide"])
    assert "it does not decide" in str(excinfo.value)


def test_a_spec_named_for_a_variant_must_state_it(tmp_path, monkeypatch):
    """`challenger_variant` defaults to "neutral", so a spec called `partisan` with the
    field commented out would run the neutral challenger into
    `outputs/experiments/partisan/` and every number in that tree would be a neutral
    number under a partisan name. `partisan.toml` ships that way on purpose — the clause
    is chosen by a pilot — and this is what stops it running as-is."""
    from exp2.experiment_cli import main

    spec = tmp_path / "partisan.toml"
    body = ('name = "partisan"\n'
            'cases = "data/cases/does-not-matter.jsonl"\n'
            f'decisions_from = "{tmp_path / "A"}"\n')
    spec.write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "contest", "--dry-run"])
    message = str(excinfo.value)
    assert "sets no `challenger_variant`" in message
    assert "would run the neutral challenger" in message
    assert "partisan_advocate" in message

    # the judgment variant is in the same trap and is caught by the same guard: a
    # `judgment-pilot` that ran the stakeholder arm would grade against `flaw.json` and
    # write `grade_mode: "flaw"` into a tree whose name promised an audit
    judgment = tmp_path / "judgment-pilot.toml"
    judgment.write_text(body.replace('"partisan"', '"judgment-pilot"'),
                        encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(judgment), "--stage", "contest", "--dry-run"])
    assert "sets no `challenger_variant`" in str(excinfo.value)

    # a neutrally-named spec is not second-guessed: the default IS what it means
    neutral = tmp_path / "recontest.toml"
    neutral.write_text(body.replace('"partisan"', '"recontest-x"'), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        # past the guard, and on to the cases file that does not exist here
        main(["--spec", str(neutral), "--stage", "contest", "--dry-run"])


def test_rerule_refuses_a_spec_that_names_no_contest_source(tmp_path, monkeypatch):
    """There would be nothing to read, and a stage that silently re-ruled nothing is how
    a run reports success having spent nothing and measured nothing."""
    from exp2.experiment_cli import main

    spec = tmp_path / "recontest.toml"
    spec.write_text(
        'name = "recontest-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "rerule"])
    assert "needs `contests_from" in str(excinfo.value)


def test_a_rerule_trees_experiment_json_names_both_trees_it_read(tmp_path, monkeypatch):
    """A re-rule reads two trees and its numbers are only comparable against the exact
    objections they were made on, so the record pins which run of each."""
    import hashlib

    from exp2.experiment_cli import main

    outputs = tmp_path / "outputs" / "experiments"
    for name in ("sweep", "recontest"):
        (outputs / name).mkdir(parents=True)
        (outputs / name / "experiment.json").write_text(
            json.dumps({"name": name}), encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n".join(json.dumps(c.to_dict()) for c in cases(1)),
                          encoding="utf-8")
    spec = tmp_path / "rerule.toml"
    spec.write_text(
        'name = "rerule-x"\n'
        f'cases = "{cases_path}"\n'
        'conditions = ["debate"]\n'
        f'decisions_from = "{outputs / "sweep"}"\n'
        f'contests_from = "{outputs / "recontest"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["--spec", str(spec), "--stage", "analyse"]) == 0
    written = json.loads((outputs / "rerule-x" / "experiment.json").read_text())
    assert written["decisions_from"] == str(outputs / "sweep")
    assert written["contests_from"] == str(outputs / "recontest")
    for key, source in (("decisions_from", "sweep"), ("contests_from", "recontest")):
        assert written[f"{key}_experiment_sha256"] == hashlib.sha256(
            (outputs / source / "experiment.json").read_bytes()).hexdigest()
    # and neither source grew a file
    for source in ("sweep", "recontest"):
        assert [p.name for p in (outputs / source).rglob("*")] == ["experiment.json"]


# --- the two controls of 2026-08-28 --------------------------------------------------


SPECIOUS_REPLY = (
    "Thinking: something plausible and wrong.\n"
    "Argument:\n"
    "1. Type: misstatement\n"
    '   Judgment says: "The sound side answered the objection"\n'
    '   Record says: "Alice round 1 argument."\n'
    "   Why it matters: the judgment attributes an answer nobody gave.\n"
    "Decision: REVERSE"
)


async def _source_arm(tmp_path, no_network, *, challenger_reply=None):
    """A → decisions, B → a real judgment contest of them. The placeholder's source."""
    make_decisions_wrong(no_network)
    if challenger_reply is not None:
        no_network.replies["challenger"] = challenger_reply
    grid = build_grid(cases(3), ["debate"])
    decisions, source = tmp_path / "A", tmp_path / "B"
    await run_stage_decide(grid, root=decisions, config=make_config(),
                           client_config=client_config(), api_key="k")
    await run_stage_contest(grid, root=source,
                            config=make_config(challenger_variant="judgment",
                                               recourse_form="third_party"),
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    return grid, decisions, source


async def test_the_placeholder_stands_on_exactly_the_cells_the_source_contested(
    tmp_path, no_network
):
    """The control's defining property, and the one the run asserts before it reads a
    number: the placeholder arm and the arm it controls for must rule on the SAME cells.

    One cell here declines in the source; it gets no placeholder, keeps its before-state,
    and is skipped by name — because the design holds "which cells get a second look"
    constant across every arm of the 2x3, and a placeholder on a cell the real arm never
    contested would give the judge a second look the real arm never gave it.
    """
    from exp2.prompts import PLACEHOLDER_OBJECTION_TEXT

    grid, decisions, source = await _source_arm(tmp_path, no_network)
    # make ONE of the three source cells a decline, by contesting it under a client that
    # declines — done by hand, since the stage resumes on what is already there
    declined = grid[0]
    for path in (source / "cells" / declined.cell_id).rglob("challenge.json"):
        data = json.loads(path.read_text())
        data.update(raised=False, stance="declined", claimed_verdict="SOUND")
        path.write_text(json.dumps(data))
        (path.parent / "ruling.json").unlink(missing_ok=True)

    contested = {c.cell_id for c, _ in source_contests(
        grid, source_root=source, challenger_model="strong/model")}
    assert len(contested) == 2 and declined.cell_id not in contested

    root = tmp_path / "C"
    before = len(no_network.calls)
    results = await run_stage_contest(
        grid, root=root, config=make_config(challenger_variant="placeholder",
                                            recourse_form="third_party"),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)
    by_cell = {r["cell_id"]: r for r in results}
    assert by_cell[declined.cell_id]["status"] == "skipped"
    assert by_cell[declined.cell_id]["reason"] == (
        "source raised no objection; no placeholder emitted")
    assert sorted(c for c, r in by_cell.items() if r["status"] == "completed") == \
        sorted(contested)

    # ONE call per placed cell, and it is the ruling. No challenger, no probe.
    made = [call for call in no_network.calls[before:]]
    assert len(made) == 2
    assert {call["meta"]["role"] for call in made} == {"recourse_judge"}

    # every placed objection is the same content-free text, recorded as a placeholder
    written = sorted(root.rglob("cells/*/contests/*/runs/*/challenge.json"))
    assert len(written) == 2
    for path in written:
        challenge = json.loads(path.read_text())
        assert challenge["text"] == PLACEHOLDER_OBJECTION_TEXT
        assert challenge["placeholder"] is True and challenge["specious"] is False
        assert challenge["arm"] == "judgment"
        assert challenge["model"] is None and challenge["call_id"] is None
        assert (path.parent / "ruling.json").is_file()
        assert json.loads((path.parent / "ruling.json").read_text())["prompt_form"] \
            == "materiality"
        # and no comprehension probe was bought
        assert not (path.parent / "comprehension.json").is_file()

    # the source tree is untouched — this arm reads it and writes nothing to it
    assert not list(source.rglob("*placeholder*"))


async def test_the_placeholder_arm_refuses_to_run_without_a_source(tmp_path):
    """Without the source it would place itself on every decided cell — a different
    population, and not a control for anything."""
    grid = build_grid(cases(1), ["debate"])
    with pytest.raises(ValueError, match="needs `contests_from`"):
        await run_stage_contest(
            grid, root=tmp_path, config=make_config(challenger_variant="placeholder"),
            client_config=client_config(), api_key="k")


async def test_only_the_placeholder_arm_may_read_a_source_while_contesting(tmp_path):
    """Any other variant with a `contest_root` would be generating objections into a
    tree that claims to re-rule another's."""
    grid = build_grid(cases(1), ["debate"])
    with pytest.raises(ValueError, match="takes a contest_root only for"):
        await run_stage_contest(
            grid, root=tmp_path, config=make_config(challenger_variant="judgment"),
            client_config=client_config(), api_key="k",
            contest_root=tmp_path / "nowhere")


async def test_grade_and_agreement_skip_a_placeholder_without_spending(tmp_path,
                                                                      no_network):
    """There is nothing in a constant to grade or to read, and the skip is recorded by
    name so that "not graded" and "graded and failed" stay different facts."""
    grid, decisions, source = await _source_arm(tmp_path, no_network)
    root = tmp_path / "C"
    config = make_config(challenger_variant="placeholder",
                         recourse_form="third_party")
    await run_stage_contest(grid, root=root, config=config,
                            client_config=client_config(), api_key="k",
                            decision_root=decisions, contest_root=source)
    before = len(no_network.calls)

    agreed = await run_stage_agreement(
        grid, root=root, config=config, grading=GradingConfig(),
        client_config=client_config(), api_key="k", decision_root=decisions)
    graded = await run_stage_grade(
        grid, root=root, config=config, grading=GradingConfig(),
        client_config=client_config(), api_key="k", decision_root=decisions)

    placed = [r for r in agreed if r["reason"] != "no contest"]
    assert placed and all(r["reason"] == "not measured: placeholder" for r in placed)
    placed = [r for r in graded if r["reason"] != "no contest"]
    assert placed and all(r["reason"] == "not graded: placeholder" for r in placed)
    assert len(no_network.calls) == before        # not one call between them
    assert not list(root.rglob("grade.json"))
    assert not list(root.rglob("agreement.json"))


async def test_the_index_names_the_control_arm_and_never_the_ruling_arm(tmp_path,
                                                                        no_network):
    """`challenge_arm` is what a derivation splits on, and both controls carry
    `arm = "judgment"` so that the materiality prompt rules them. If the index wrote the
    ruling arm, the placeholder's 1,148 rows and the real audit's 1,148 rows would be one
    population of 2,296 under one label."""
    grid, decisions, source = await _source_arm(tmp_path, no_network)
    root = tmp_path / "C"
    await run_stage_contest(
        grid, root=root, config=make_config(challenger_variant="placeholder",
                                            recourse_form="third_party"),
        client_config=client_config(), api_key="k",
        decision_root=decisions, contest_root=source)

    rows = build_index(grid, root=root, challenger_model="strong/model",
                       decision_root=decisions)
    placed = [r for r in rows if "challenge_arm" in r]
    assert placed
    for row in placed:
        assert row["challenge_arm"] == "placeholder"
        assert row["challenge_placeholder"] is True
        assert row["challenge_specious"] is False
        assert row["challenge_raised"] is True
        assert row["ruling_prompt_form"] == "materiality"
        # nothing grades it, so the grade columns are absent rather than 0
        assert "grade_mode" not in row and "grade_valid" not in row

    # the source arm's own index says `judgment` on the same cells — the two are
    # joinable cell by cell and are never the same label
    source_rows = build_index(grid, root=source, challenger_model="strong/model",
                              decision_root=decisions)
    assert {r["challenge_arm"] for r in source_rows} == {"judgment"}


async def test_a_specious_arm_is_graded_by_the_judgment_grader_unchanged(tmp_path,
                                                                         no_network):
    """The manipulation check. The grader runs on the specious objections exactly as it
    runs on the real ones — that is what makes "were they actually specious?" a
    measurement rather than an assumption — and the index says which arm wrote them."""
    make_decisions_wrong(no_network)
    no_network.replies["challenger"] = SPECIOUS_REPLY
    grid = build_grid(cases(2), ["debate"])
    config = make_config(challenger_variant="judgment_specious",
                         recourse_form="third_party")
    await decide(tmp_path, grid)
    await run_stage_contest(grid, root=tmp_path, config=config,
                            client_config=client_config(), api_key="k")
    results = await run_stage_grade(grid, root=tmp_path, config=config,
                                    grading=GradingConfig(),
                                    client_config=client_config(), api_key="k")
    assert all(r["status"] == "completed" and r["mode"] == "judgment" for r in results)

    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    for row in rows:
        assert row["challenge_arm"] == "judgment_specious"
        assert row["challenge_specious"] is True
        assert row["challenge_placeholder"] is False
        assert row["grade_mode"] == "judgment"       # the same instrument, unchanged
        assert row["ruling_prompt_form"] == "materiality"
        assert row["challenge_defects_n"] == 1


FABRICATED_REPLY = (
    "Thinking: a sentence in this judgment's register that it does not contain.\n"
    "Argument:\n"
    "1. Type: misstatement\n"
    '   Judgment says: "the flawed side withdrew its objection in the third round"\n'
    '   Record says: "Alice round 1 argument."\n'
    "   Why it matters: the verdict rests on a withdrawal the record does not show.\n"
    "Decision: REVERSE"
)


async def test_the_fabricated_arm_is_graded_with_no_grader_call_and_the_index_says_so(
    tmp_path, no_network
):
    """WHAT MAKES THIS ARM CHEAP, and what makes its ground truth code.

    Every defect it alleges quotes a judgment that does not say it, so
    `grading._grade_judgment` returns a `quote_check_only` grade and **never reaches the
    wire**. The grade stage still runs on every contested cell — the row must say
    `grade_mode = "judgment"` and `grade_valid = False`, not "not graded" — and the index
    carries the manipulation check itself: `challenge_fabrication_ok` per objection and
    `challenge_defects_fabricated_n` per defect, both string comparisons.
    """
    from exp2.grading import QUOTE_CHECK_ONLY

    make_decisions_wrong(no_network)
    no_network.replies["challenger"] = FABRICATED_REPLY
    grid = build_grid(cases(2), ["debate"])
    config = make_config(challenger_variant="judgment_fabricated",
                         recourse_form="third_party")
    await decide(tmp_path, grid)
    await run_stage_contest(grid, root=tmp_path, config=config,
                            client_config=client_config(), api_key="k")
    before = len(no_network.calls)
    results = await run_stage_grade(grid, root=tmp_path, config=config,
                                    grading=GradingConfig(),
                                    client_config=client_config(), api_key="k")
    assert all(r["status"] == "completed" and r["mode"] == "judgment" for r in results)
    # THE POINT: the grade stage bought nothing
    assert no_network.calls[before:] == []

    for path in sorted(tmp_path.rglob("cells/*/contests/*/runs/*/grade.json")):
        grade = json.loads(path.read_text())
        assert grade["parse_mode"] == QUOTE_CHECK_ONLY
        assert grade["valid"] is False and grade["model"] == ""

    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    for row in rows:
        assert row["challenge_arm"] == "judgment_fabricated"
        assert row["challenge_fabricated"] is True
        assert row["challenge_specious"] is False
        assert row["challenge_placeholder"] is False
        assert row["ruling_prompt_form"] == "materiality"   # ruled as the real audit is
        assert row["grade_mode"] == "judgment"
        assert row["grade_valid"] is False
        # the check, in the index, computed by string comparison and not by a model
        assert row["challenge_defects_n"] == 1
        assert row["challenge_defects_fabricated_n"] == 1
        assert row["challenge_fabrication_ok"] is True
        # the same defect is a misattributed quotation under the pre-registered check —
        # one fact, two columns, and they mean opposite things in the two arms
        assert row["challenge_defects_misattributed_n"] == 1


async def test_a_fabricated_objection_whose_quote_is_real_is_visible_as_the_arm_failing(
    tmp_path, no_network
):
    """The failure mode, and it must be legible in the index rather than inferred.

    A challenger that quotes the judgment accurately has written a REAL objection under
    the fabricated arm's name — which is exactly how `judgment-debate-3`'s specious arm
    came apart (29.2% graded valid). The row then says `challenge_fabrication_ok = False`
    and the grader IS called, so the arm's cost and its validity fail together and in the
    same place."""
    make_decisions_wrong(no_network)
    # "The sound side answered the objection." is the judgment the fake judge writes
    no_network.replies["challenger"] = (
        "Argument:\n"
        "1. Type: misstatement\n"
        '   Judgment says: "The sound side answered the objection"\n'
        '   Record says: "Alice round 1 argument."\n'
        "   Why it matters: it did not.\n"
        "Decision: REVERSE"
    )
    grid = build_grid(cases(1), ["debate"])
    config = make_config(challenger_variant="judgment_fabricated",
                         recourse_form="third_party")
    await decide(tmp_path, grid)
    await run_stage_contest(grid, root=tmp_path, config=config,
                            client_config=client_config(), api_key="k")
    before = len(no_network.calls)
    await run_stage_grade(grid, root=tmp_path, config=config, grading=GradingConfig(),
                          client_config=client_config(), api_key="k")
    assert [c["meta"]["role"] for c in no_network.calls[before:]] == ["judgment_grader"]

    rows = build_index(grid, root=tmp_path, challenger_model="strong/model")
    for row in rows:
        assert row["challenge_arm"] == "judgment_fabricated"
        assert row["challenge_fabrication_ok"] is False
        assert row["challenge_defects_fabricated_n"] == 0
        assert row["challenge_defects_misattributed_n"] == 0


def test_only_the_placeholder_spec_may_contest_while_reading_another_trees_contests(
    tmp_path, monkeypatch
):
    """The refusal that protects every re-rule stays in place, and the one arm exempt
    from it is named in the spec rather than inferred.

    A `contests_from` spec running `contest` would ordinarily write a NEW objection over
    the copy the tree holds. The placeholder writes no objection — it emits a constant
    with no model call, and reads the source only to place itself — so it is exempt, and
    `agreement` and `grade` stay refused for it because there is still nothing to grade.
    """
    from exp2.experiment_cli import main

    def spec_for(name, variant):
        path = tmp_path / f"{name}.toml"
        body = (f'name = "{name}"\n'
                'cases = "data/cases/does-not-matter.jsonl"\n'
                f'decisions_from = "{tmp_path / "A"}"\n'
                f'contests_from = "{tmp_path / "B"}"\n')
        if variant:
            body += f'[debate]\nchallenger_variant = "{variant}"\n'
        path.write_text(body, encoding="utf-8")
        return path

    monkeypatch.chdir(tmp_path)

    # the ordinary re-rule spec: contest still refused
    rerule = spec_for("rerule-x", None)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(rerule), "--stage", "contest"])
    assert "it does not contest" in str(excinfo.value)

    # the placeholder spec: contest allowed (it dies later, on the missing cases file,
    # which is proof it got past the refusal), agreement and grade still refused
    placeholder = spec_for("jd2-nano-placeholder", "placeholder")
    with pytest.raises(FileNotFoundError):
        main(["--spec", str(placeholder), "--stage", "contest", "--dry-run"])
    for stage in ("agreement", "grade"):
        with pytest.raises(SystemExit) as excinfo:
            main(["--spec", str(placeholder), "--stage", stage])
        assert "it does not contest" in str(excinfo.value)


def test_a_placeholder_spec_without_a_source_is_refused_at_the_cli(tmp_path,
                                                                   monkeypatch):
    """Without `contests_from` the arm would place itself on every decided cell — a
    different population from the one it controls for, and not a control for anything."""
    from exp2.experiment_cli import main

    spec = tmp_path / "jd2-nano-placeholder.toml"
    spec.write_text(
        'name = "jd2-nano-placeholder"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        f'decisions_from = "{tmp_path / "A"}"\n'
        '[debate]\nchallenger_variant = "placeholder"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "contest", "--dry-run"])
    message = str(excinfo.value)
    assert "needs `contests_from" in message
    assert "not a control for anything" in message


# --- re-judging another tree's stored transcripts -------------------------------------
#
# The `rejudge` stage of 2026-08-28. Its whole reason for existing is that the sweep's
# 1,644 debate transcripts cost $32 and a different judge can be measured on them for
# cents — and its whole safety property is that measuring so changes nothing about them.


async def _decided_debates(tmp_path, no_network, n=2):
    """A source tree holding decided DEBATE cells, and the grid over them."""
    grid = build_grid(cases(n), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    return grid, source


async def test_a_rejudge_writes_a_full_decision_record_and_writes_nowhere_else(
    tmp_path, no_network
):
    """The stage's two promises at once: the source tree does not change by one byte,
    and what lands in the new tree is an ORDINARY decision run — which is what lets
    `decisions_from` read it downstream with no change anywhere."""
    grid, source = await _decided_debates(tmp_path, no_network)
    before = _tree_fingerprint(source)
    assert before
    rejudged = tmp_path / "M0"

    # A different judge, stated the way the real spec states it.
    config = make_config(judge_model="meta-llama/llama-4-maverick")
    results = await run_stage_rejudge(
        grid, root=rejudged, config=config, client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["completed"] * 2

    runs = sorted(rejudged.glob("cells/*/runs/*"))
    assert len(runs) == 2
    copied = 0
    for directory in runs:
        # everything load_run_record needs, and nothing it must not find twice
        for name in ("item.json", "sides.json", "config.json", "transcript.json",
                     "verdict.json", "run.json"):
            assert (directory / name).is_file(), name
        # the config names the judge that actually judged, not the source's
        assert json.loads((directory / "config.json").read_text())["judge_model"] == (
            "meta-llama/llama-4-maverick")
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["kind"] == "rejudge"
        assert manifest["status"] == "completed"
        assert manifest["rejudged_from"] == str(source)
        assert manifest["source_verdict"] == "FLAWED"
        assert manifest["source_judge_model"] == "weak/model"
        assert len(manifest["source_sha256"]) == 64
        assert Path(manifest["source_run_dir"]).is_relative_to(source)
        # THIS run's wire log is the one judge call and nothing else. The debate's own
        # calls are beside it under another name, so the money stays this run's while
        # the verbatim document stays complete. (The offline fixture shares one fake
        # client across concurrent cells and so one sink at a time, which is why the
        # copied log is asserted where the source actually wrote one; the e2e builds a
        # client per run and checks every document there.)
        logged = [json.loads(line) for line
                  in (directory / "calls.jsonl").read_text().splitlines()]
        assert [record["role"] for record in logged] == ["judge"]
        source_run = Path(json.loads((directory / "run.json").read_text())
                          ["source_run_dir"])
        if (source_run / "calls.jsonl").is_file():
            copied += 1
            source_log = [json.loads(line) for line
                          in (directory / "calls.source.jsonl").read_text().splitlines()]
            assert {record["role"] for record in source_log} == {"debater", "judge"}
            full = (directory / "transcript_full.md").read_text()
            assert "Prompts were not recorded for this run" not in full
    assert copied, "no source wire log was copied, so the document check never ran"

    # the decision really is readable as a decision
    for cell in grid:
        record = existing_decision(rejudged, cell)
        assert record is not None
        assert record.transcript is not None
        assert record.verdict.verdict == "FLAWED"

    assert _tree_fingerprint(source) == before
    # ... and it resumes on the decision it wrote
    again = await run_stage_rejudge(
        grid, root=rejudged, config=config, client_config=client_config(),
        api_key="k", transcript_root=source)
    assert all(r["reason"] == "already re-judged" for r in again)


async def test_a_truncated_judgment_is_counted_and_left_undecided(tmp_path, no_network):
    """As the sweep did: the judge has no budget route, so a reply cut off at the
    ceiling fails the cell rather than entering the record half-written. The run is on
    disk and marked `failed` — the cell is counted — and no verdict exists."""
    grid, source = await _decided_debates(tmp_path, no_network, n=1)
    rejudged = tmp_path / "M0"
    no_network.fail_on = {"judge": "truncated_twice"}

    results = await run_stage_rejudge(
        grid, root=rejudged, config=make_config(), client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["failed"]
    assert "Truncated" in results[0]["error"]
    directory = next(iter(sorted(rejudged.glob("cells/*/runs/*"))))
    assert json.loads((directory / "run.json").read_text())["status"] == "failed"
    assert not (directory / "verdict.json").exists()
    assert existing_decision(rejudged, grid[0]) is None
    assert latest_run_status(rejudged, grid[0]) == "failed"
    # and a resume does not give it a second draw unless asked
    no_network.fail_on = {}
    again = await run_stage_rejudge(
        grid, root=rejudged, config=make_config(), client_config=client_config(),
        api_key="k", transcript_root=source)
    assert again[0]["reason"].startswith("already attempted and failed")
    retried = await run_stage_rejudge(
        grid, root=rejudged, config=make_config(), client_config=client_config(),
        api_key="k", transcript_root=source, retry_failed=True)
    assert [r["status"] for r in retried] == ["completed"]


async def test_a_rejudge_reuses_the_recorded_sides_and_never_re_draws_them(
    tmp_path, no_network
):
    """The judgment has to be of the debate that happened. `make_sides` is deterministic
    given (seed, item_id), so a re-draw would usually agree — and "usually" is the
    failure: a spec with another seed would present the verdict template in the other
    order and swap which speaker argued FLAWED."""
    from exp2.types import make_sides as draw_sides

    grid, source = await _decided_debates(tmp_path, no_network, n=1)
    decision = existing_decision(source, grid[0])
    assert decision is not None
    # Doctor the recorded draw so it can no longer be confused with a fresh one.
    flipped = {
        "alice_side": decision.sides.bob_side,
        "bob_side": decision.sides.alice_side,
        "verdict_order": [decision.sides.verdict_order[1],
                          decision.sides.verdict_order[0]],
        "seed_material": decision.sides.seed_material,
        "swap_debater_models": decision.sides.swap_debater_models,
    }
    (decision.directory / "sides.json").write_text(json.dumps(flipped),
                                                   encoding="utf-8")
    drawn = draw_sides(grid[0].case.item, make_config().seed)
    assert list(drawn.verdict_order) != flipped["verdict_order"]

    rejudged = tmp_path / "M0"
    await run_stage_rejudge(grid, root=rejudged, config=make_config(),
                            client_config=client_config(), api_key="k",
                            transcript_root=source)
    written = json.loads(
        next(iter(sorted(rejudged.glob("cells/*/runs/*/sides.json")))).read_text())
    assert written == flipped
    # and the prompt the judge was actually sent carries that order, not the draw
    judge_calls = [c for c in no_network.calls if c["meta"].get("role") == "judge"]
    sent = judge_calls[-1]["messages"][-1]["content"]
    first, second = flipped["verdict_order"]
    assert f"Verdict: <{first}|{second}>" in sent


async def test_decisions_from_a_rejudged_tree_round_trips_through_every_later_stage(
    tmp_path, no_network
):
    """The design's whole point: what `rejudge` writes is an ordinary decision tree, so
    the contest, the agreement reading, the grade and the index run over it with no
    argument any of them did not already take."""
    grid, source = await _decided_debates(tmp_path, no_network)
    rejudged = tmp_path / "M0"
    await run_stage_rejudge(grid, root=rejudged, config=make_config(),
                            client_config=client_config(), api_key="k",
                            transcript_root=source)
    contests = tmp_path / "M1"
    for stage in (
        lambda: run_stage_contest(grid, root=contests, config=make_config(),
                                  client_config=client_config(), api_key="k",
                                  decision_root=rejudged),
        lambda: run_stage_agreement(grid, root=contests, config=make_config(),
                                    grading=GradingConfig(),
                                    client_config=client_config(), api_key="k",
                                    decision_root=rejudged),
        lambda: run_stage_ruling_agreement(grid, root=contests, config=make_config(),
                                           grading=GradingConfig(),
                                           client_config=client_config(), api_key="k"),
    ):
        results = await stage()
        assert [r["status"] for r in results] == ["completed"] * 2, results

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert len(rows) == 2
    assert all(row["challenge_raised"] is True for row in rows)
    assert all(row["ruling_line_mismatch"] is not None for row in rows)
    # the contest carried the re-judged decision with it, judge and all
    parents = sorted(contests.glob("cells/*/contests/*/runs/*/parent/verdict.json"))
    assert len(parents) == 2
    configs = sorted(contests.glob("cells/*/contests/*/runs/*/config.json"))
    assert all(json.loads(p.read_text())["judge_model"] == "weak/model"
               for p in configs)


async def test_the_index_says_a_decision_was_rejudged_and_what_the_source_said(
    tmp_path, no_network
):
    """`source_verdict` beside `verdict` is what makes the new judge against the old one
    a column join rather than a second tree to open, and the caveat is what stops the
    two being read as one population of decisions this tree made."""
    from exp2.analysis import caveats

    grid, source = await _decided_debates(tmp_path, no_network)
    rejudged = tmp_path / "M0"
    # The new judge disagrees with the source's FLAWED on the same transcripts.
    no_network.replies = {"judge": "The sound side answered it.\nVerdict: SOUND"}
    await run_stage_rejudge(grid, root=rejudged, config=make_config(),
                            client_config=client_config(), api_key="k",
                            transcript_root=source)
    rows = build_index(grid, root=rejudged, challenger_model="strong/model")
    assert len(rows) == 2
    for row in rows:
        assert row["verdict"] == "SOUND"
        assert row["source_verdict"] == "FLAWED"
        assert row["initially_correct"] is False
        assert row["source_correct"] is True
        assert row["rejudged_from"] == str(source)
        assert row["source_judge_model"] == "weak/model"
        # the cost is this run's ONE judge call, never the debate it read
        assert row["decision_cost_usd"] == 0.0
    stated = caveats(rows, ["debate"])
    assert any("RE-JUDGED FROM STORED TRANSCRIPTS" in c for c in stated)

    # a tree that decided for itself says nothing of the kind
    plain = build_index(grid, root=source, challenger_model="strong/model")
    assert all("rejudged_from" not in row for row in plain)
    assert not any("RE-JUDGED" in c for c in caveats(plain, ["debate"]))


async def test_rejudge_refuses_a_condition_that_publishes_no_transcript(tmp_path):
    """`single` and `self_critique` reach their verdict inside the conversation that
    wrote the record, so there is nothing to hand a second judge without re-deciding.
    Refused in the stage as well as in the CLI, so a direct caller cannot get past it."""
    grid = build_grid(cases(1), ["debate", "single"])
    with pytest.raises(ValueError) as excinfo:
        await run_stage_rejudge(grid, root=tmp_path / "M0", config=make_config(),
                                client_config=client_config(), api_key="k",
                                transcript_root=tmp_path / "sweep")
    assert "debate-only" in str(excinfo.value)


async def test_a_cell_the_source_never_decided_is_skipped_by_name(tmp_path, no_network):
    """The sweep lost 466 debate cells to truncation and they have no transcript. Named
    rather than silent, because "never decided there" and "we forgot" must stay apart."""
    grid = build_grid(cases(1), ["debate"])
    results = await run_stage_rejudge(
        grid, root=tmp_path / "M0", config=make_config(),
        client_config=client_config(), api_key="k", transcript_root=tmp_path / "sweep")
    assert [r["reason"] for r in results] == ["no source decision to re-judge"]


def test_a_spec_that_rejudges_transcripts_refuses_to_decide_and_needs_its_source(
    tmp_path, monkeypatch
):
    """`decide` would run the debates again — new arguments, a new population, and the
    one thing the arm holds fixed. And `rejudge` without a source would judge nothing
    and exit 0, which is how a run reports success having measured nothing."""
    from exp2.experiment_cli import main

    spec = tmp_path / "jd3.toml"
    spec.write_text(
        'name = "jd3-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        'conditions = ["debate"]\n'
        f'transcripts_from = "{tmp_path / "sweep"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec), "--stage", "decide"])
    assert "it does not decide" in str(excinfo.value)

    bare = tmp_path / "plain.toml"
    bare.write_text('name = "plain-x"\n'
                    'cases = "data/cases/does-not-matter.jsonl"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(bare), "--stage", "rejudge"])
    assert "needs `transcripts_from" in str(excinfo.value)


def test_a_rejudge_spec_is_debate_only_and_may_not_also_read_decisions(tmp_path,
                                                                       monkeypatch):
    """Two refusals with one cause: a re-judge tree DECIDES, for one condition only."""
    from exp2.experiment_cli import main

    monkeypatch.chdir(tmp_path)
    both = tmp_path / "both.toml"
    both.write_text(
        'name = "both-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        'conditions = ["debate"]\n'
        f'decisions_from = "{tmp_path / "A"}"\n'
        f'transcripts_from = "{tmp_path / "sweep"}"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(both), "--stage", "rejudge"])
    assert "not both" in str(excinfo.value)

    solo = tmp_path / "solo.toml"
    solo.write_text(
        'name = "solo-x"\n'
        'cases = "data/cases/does-not-matter.jsonl"\n'
        'conditions = ["debate", "single"]\n'
        f'transcripts_from = "{tmp_path / "sweep"}"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(solo), "--stage", "rejudge"])
    assert "debate-only" in str(excinfo.value)


def test_a_rejudge_trees_experiment_json_names_the_tree_it_read(tmp_path, monkeypatch):
    """The verdicts are only interpretable against the exact debates they were made
    over, so the record pins which run of the source tree that was."""
    import hashlib

    from exp2.experiment_cli import main

    outputs = tmp_path / "outputs" / "experiments"
    (outputs / "sweep").mkdir(parents=True)
    (outputs / "sweep" / "experiment.json").write_text(
        json.dumps({"name": "sweep"}), encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n".join(json.dumps(c.to_dict()) for c in cases(1)),
                          encoding="utf-8")
    spec = tmp_path / "jd3.toml"
    spec.write_text(
        'name = "jd3-x"\n'
        f'cases = "{cases_path}"\n'
        'conditions = ["debate"]\n'
        f'transcripts_from = "{outputs / "sweep"}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["--spec", str(spec), "--stage", "analyse"]) == 0
    written = json.loads((outputs / "jd3-x" / "experiment.json").read_text())
    assert written["transcripts_from"] == str(outputs / "sweep")
    assert written["transcripts_from_experiment_sha256"] == hashlib.sha256(
        (outputs / "sweep" / "experiment.json").read_bytes()).hexdigest()
    assert written["decisions_from"] is None
    assert [p.name for p in (outputs / "sweep").rglob("*")] == ["experiment.json"]


async def test_the_estimate_counts_the_source_decisions_rather_than_the_grid(
    tmp_path, no_network, capsys
):
    """The line a run is approved from. A re-judge makes ONE call per stored decision,
    not the seven a debate costs, and not one at all for a cell the source never
    decided — quoting the grid would quote fourteen times the spend."""
    from exp2.experiment_cli import print_estimate

    grid, source = await _decided_debates(tmp_path, no_network, n=3)
    # one of the three was never decided in the source
    shutil_rmtree = __import__("shutil").rmtree
    shutil_rmtree(cell_dir(source, grid[0]))
    found = source_decisions(grid, source_root=source)
    assert len(found) == 2
    print_estimate(grid, make_config(), transcripts_from=source,
                   n_source_decisions=len(found))
    printed = capsys.readouterr().out
    assert "decision 2 (one judge call per stored transcript" in printed
    assert "the decision term is COUNTED, not bounded: 2 of the 3 cells" in printed


# --- the contestability debate round and the plain extra round, 2026-08-30 ------------
#
# `judgment-debate-6`, and its two arms are opposite ends of the same tree of stages. Arm
# R hears a round INSIDE a rerule; arm B plays one INSIDE a rejudge. What every test here
# is really guarding is that the arm is opt-in: at the defaults both stages send byte for
# byte what they sent before, and the arms are readable apart from each other afterwards.


async def _judgment_trees(tmp_path, no_network, n=2):
    """A → decisions, B → JUDGMENT-arm contests of them. The round runs on that arm."""
    make_decisions_wrong(no_network)
    grid = build_grid(cases(n), ["debate"])
    decisions, contests = tmp_path / "A", tmp_path / "B"
    config = make_config(challenger_variant="judgment", recourse_form="third_party")
    await run_stage_decide(grid, root=decisions, config=config,
                           client_config=client_config(), api_key="k")
    await run_stage_contest(grid, root=contests, config=config,
                            client_config=client_config(), api_key="k",
                            decision_root=decisions)
    return grid, decisions, contests, config


def _messages_by_role(root, role):
    """Every message list a tree's wire log holds for one role, oldest first."""
    out = []
    for path in sorted(root.rglob("calls.jsonl")):
        if "parent" in path.parts:
            continue
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get("role") == role:
                out.append(record["request_body"]["messages"])
    return out


async def test_a_rerule_with_rounds_zero_sends_exactly_what_it_sent_before(
    tmp_path, no_network
):
    """The byte-identity half of "opt-in".

    1,586 rulings and four paired campaigns stand on the judge-only messages. A default
    that had drifted by a newline would make every jd6 comparison a comparison of two
    instruments, and nothing else in the repo would notice.
    """
    grid, decisions, contests, config = await _judgment_trees(tmp_path, no_network)
    plain, rounds = tmp_path / "P", tmp_path / "R"
    await run_stage_rerule(grid, root=plain, config=config,
                           client_config=client_config(), api_key="k",
                           decision_root=decisions, contest_root=contests)
    sent = _messages_by_role(plain, "recourse_judge")
    assert sent and "recourse_debater" not in {
        json.loads(line)["role"]
        for path in plain.rglob("calls.jsonl") if "parent" not in path.parts
        for line in path.read_text().splitlines()}
    assert not list(plain.rglob("recourse_transcript.json"))
    for messages in sent:
        blob = "".join(m["content"] for m in messages)
        assert "<exchange>" not in blob
        assert "Rule in two steps." in blob

    # the SAME cells with the round asked for send the same prompt plus one block
    await run_stage_rerule(grid, root=rounds,
                           config=dataclasses.replace(config, recourse_rounds=1),
                           client_config=client_config(), api_key="k",
                           decision_root=decisions, contest_root=contests)
    argued = _messages_by_role(rounds, "recourse_judge")
    assert len(argued) == len(sent)
    for messages in argued:
        blob = "".join(m["content"] for m in messages)
        assert "<exchange>" in blob and "Rule in two steps." in blob


async def test_a_rerule_with_one_round_writes_the_exchange_and_rules_on_it(
    tmp_path, no_network
):
    """Arm R end to end, on the two things a reader afterwards depends on: what the tree
    holds, and what the index says about it. The source trees must not move — the whole
    campaign is a re-ruling of stored objections against stored decisions."""
    grid, decisions, contests, config = await _judgment_trees(tmp_path, no_network)
    rounds = tmp_path / "R"
    before_a, before_b = _tree_fingerprint(decisions), _tree_fingerprint(contests)
    config = dataclasses.replace(config, recourse_rounds=1)

    results = await run_stage_rerule(
        grid, root=rounds, config=config, client_config=client_config(),
        api_key="k", decision_root=decisions, contest_root=contests)
    assert [r["status"] for r in results] == ["completed"] * 2
    assert all(r["recourse_rounds"] == 1 for r in results)

    dirs = sorted(p.parent for p in rounds.rglob("cells/*/contests/*/runs/*/ruling.json"))
    assert len(dirs) == 2
    for directory in dirs:
        stored = json.loads((directory / "recourse_transcript.json").read_text())
        assert [t["round"] for t in stored["turns"]] == [4, 4]
        # a contest directory must never hold a decision's transcript
        assert not (directory / "transcript.json").is_file()
        ruling = json.loads((directory / "ruling.json").read_text())
        assert ruling["recourse_rounds"] == 1
        assert ruling["prompt_form"] == "materiality"
        assert ruling["recourse_pro_speaker"] in ("Alice", "Bob")
        assert ruling["recourse_exchange_sha256"]
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["recourse_rounds"] == 1
        assert manifest["recourse_pro_speaker"] == ruling["recourse_pro_speaker"]
        # the published documents carry the round, and the private half is not in the
        # readable one
        document = (directory / "transcript.md").read_text()
        assert "## The exchange on the objection" in document
        assert "after hearing both debaters on the objection" in document
        assert SECRET_THINKING not in document

    logged = [json.loads(line)
              for path in rounds.glob("cells/*/contests/*/runs/*/calls.jsonl")
              for line in path.read_text().splitlines()]
    assert sorted(r["role"] for r in logged) == (
        ["recourse_debater"] * 4 + ["recourse_judge"] * 2)
    assert {r["purpose"] for r in logged if r["role"] == "recourse_debater"} == {
        "recourse_turn"}

    # the reading stage still runs over these rulings, unchanged
    await run_stage_ruling_agreement(
        grid, root=rounds, config=config, grading=GradingConfig(),
        client_config=client_config(), api_key="k")
    rows = build_index(grid, root=rounds, challenger_model="strong/model",
                       decision_root=decisions)
    assert len(rows) == 2
    for row in rows:
        assert row["recourse_rounds"] == 1
        assert row["recourse_turns_n"] == 2
        assert len(row["recourse_turn_parse_modes"]) == 2
        assert len(row["recourse_turn_words"]) == 2
        assert row["ruling_prompt_form"] == "materiality"
        assert row["ruling_line_mismatch"] is not None
    # The round's own spend, off this contest's wire log by role. Asserted over the tree
    # rather than per row: the offline fixture shares ONE fake client across concurrent
    # cells and so one sink at a time, so a cell's calls can land in a sibling's log.
    assert any(row["recourse_cost_usd"] is not None for row in rows)
    from exp2.analysis import caveats as caveats_for
    caveats = caveats_for(rows, ["debate"])
    assert any("ARGUED BEFORE IT WAS RULED ON" in c for c in caveats)

    assert _tree_fingerprint(decisions) == before_a
    assert _tree_fingerprint(contests) == before_b


async def test_a_rejudge_without_extend_rounds_sends_exactly_what_jd3_sent(
    tmp_path, no_network
):
    """The other byte-identity half. jd3's M0 re-judged 1,644 stored transcripts with no
    debater call at all, and every number in that campaign is under those messages."""
    grid, source = await _decided_debates(tmp_path, no_network)
    plain = tmp_path / "M0"
    results = await run_stage_rejudge(
        grid, root=plain, config=make_config(), client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["completed"] * 2
    assert all(r["rounds_n"] == 3 for r in results)
    logged = [json.loads(line) for path in plain.glob("cells/*/runs/*/calls.jsonl")
              for line in path.read_text().splitlines()]
    assert {r["role"] for r in logged} == {"judge"}
    for messages in _messages_by_role(plain, "judge"):
        blob = "".join(m["content"] for m in messages)
        assert "Round 3:" in blob and "Round 4:" not in blob
    for directory in sorted(plain.glob("cells/*/runs/*")):
        manifest = json.loads((directory / "run.json").read_text())
        assert "extended_from_rounds" not in manifest


async def test_a_rejudge_with_extend_rounds_plays_round_4_then_judges(
    tmp_path, no_network
):
    """Arm B end to end. The extended transcript IS this tree's decision, so it goes to
    `transcript.json` and overwrites the copy — the opposite of the contest round's rule,
    and for the opposite reason: here the four-round debate is what was judged."""
    grid, source = await _decided_debates(tmp_path, no_network)
    before = _tree_fingerprint(source)
    extended = tmp_path / "B"
    config = make_config(n_rounds=4, n_critique_rounds=4, extend_rounds=True)

    results = await run_stage_rejudge(
        grid, root=extended, config=config, client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["completed"] * 2
    assert all(r["rounds_n"] == 4 for r in results)

    for directory in sorted(extended.glob("cells/*/runs/*")):
        stored = json.loads((directory / "transcript.json").read_text())
        assert sorted(t["round"] for t in stored["turns"]) == [1, 1, 2, 2, 3, 3, 4, 4]
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["extended_from_rounds"] == 3
        assert manifest["rounds_n"] == 4
    # Roles over the TREE, not per directory: the offline fixture shares one fake client
    # across concurrent cells and so one sink at a time, so a cell's calls can land in a
    # sibling's log. What is asserted is that the tree holds two debater calls and one
    # judgment per cell and nothing else.
    logged = [json.loads(line) for path in extended.glob("cells/*/runs/*/calls.jsonl")
              for line in path.read_text().splitlines()]
    assert sorted(r["role"] for r in logged) == ["debater"] * 4 + ["judge"] * 2
    for directory in sorted(extended.glob("cells/*/runs/*")):
        # no objection anywhere in the round-4 prompts, and the ordinary instruction
        for record in logged:
            if record["role"] != "debater":
                continue
            blob = "".join(m["content"] for m in record["request_body"]["messages"])
            assert "This is round 4 of 4." in blob
            assert "objection" not in blob.lower()
            assert "do not write a closing summary" not in blob
        # and every judgment was made from the LONGER transcript
        for record in logged:
            if record["role"] != "judge":
                continue
            assert "Round 4:" in "".join(
                m["content"] for m in record["request_body"]["messages"])
        assert "continued here" in (directory / "transcript.md").read_text()

    rows = build_index(grid, root=extended, challenger_model="strong/model")
    for row in rows:
        assert row["extended_from_rounds"] == 3 and row["rounds_n"] == 4
        assert len(row["round4_parse_modes"]) == 2
        assert len(row["round4_words"]) == 2
    from exp2.analysis import caveats as caveats_for
    caveats = caveats_for(rows, ["debate"])
    assert any("CONTINUED BEFORE IT WAS JUDGED" in c for c in caveats)

    assert _tree_fingerprint(source) == before


async def test_extend_rounds_refuses_a_solo_or_already_long_source(
    tmp_path, no_network
):
    """Both refusals fail the CELL rather than the stage, and both are counted.

    A source already `n_rounds` long would be judged with no round added — an ordinary
    re-judge wearing arm B's name — and a source argued under other settings would splice
    a turn by a different party into a transcript that says all four turns are one debate.
    """
    grid, source = await _decided_debates(tmp_path, no_network, n=1)
    same_length = make_config(n_rounds=3, n_critique_rounds=3, extend_rounds=True)
    results = await run_stage_rejudge(
        grid, root=tmp_path / "X", config=same_length, client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["failed"]
    assert "nothing to add" in results[0]["error"]
    assert not list((tmp_path / "X").rglob("verdict.json"))

    other = make_config(n_rounds=4, n_critique_rounds=4, extend_rounds=True,
                        debater_model="other/model")
    results = await run_stage_rejudge(
        grid, root=tmp_path / "Y", config=other, client_config=client_config(),
        api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["failed"]
    assert "debater_model" in results[0]["error"]


# --- the FINDINGS arm, campaign `fd1` (2026-09-02) -----------------------------------
#
# End to end through the stages a `fd1` spec actually runs — rejudge, contest, agreement,
# ruling_agreement, grade, index — over the fake client, because the properties that
# matter here are the joins between stages: a verdict that follows from a list by
# counting at BOTH ends, a contest numbering that survives to the ruling and to the
# grade, and a grade stage with none of the flaw grader's gates.

# The LIST — what the trim publishes, and therefore what the challenger, the recourse
# judge and the grader are all shown inside `<findings>`.
FINDINGS_LIST = (
    "Finding 1\n"
    'Passage: "Step 2: C_3 = 6."\n'
    "Claim: the third Catalan number is 5, not 6\n"
    "Defence: none given\n"
    "Reason: the divisor is not bounded away from zero\n"
    "Ruling: FLAW\n"
    "Finding 2\n"
    'Passage: "Step 1: apply the formula."\n'
    "Claim: the formula named is the wrong one\n"
    "Defence: the sound side said rounding is conventional\n"
    "Reason: the convention is standard and the step is fine\n"
    "Ruling: NOT A FLAW"
)

# The whole reply, with the preamble and the trailing self-commentary the smoke of
# 2026-09-02 found published inside `<findings>`. `Verdict.raw` keeps it; nothing
# downstream is shown it.
FINDINGS_JUDGMENT = (
    "The flawed side raised two points.\n"
    + FINDINGS_LIST
    + "\n\nFindings are done. They are different ways of expressing the same worry."
)

FINDINGS_OBJECTION = (
    "Thinking: I read the list.\n"
    "Argument:\n"
    "1. Contests: Finding 1\n"
    "   Should be: NOT A FLAW\n"
    '   Text says: "Step 2: C_3 = 6."\n'
    '   Record says: "Alice argues in round 1."\n'
    "   Why: six is right and the record shows it."

    "Decision: REVERSE"
)


def findings_config(**kw):
    return make_config(judge_form="findings", challenger_variant="findings", **kw)


async def _findings_tree(tmp_path, no_network, n=2):
    """A source tree of decided debates, re-judged into a findings tree."""
    grid = build_grid(cases(n), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    no_network.replies["judge_findings"] = FINDINGS_JUDGMENT
    rejudged = tmp_path / "F"
    results = await run_stage_rejudge(
        grid, root=rejudged, config=findings_config(), client_config=client_config(),
        api_key="k", transcript_root=source)
    return grid, source, rejudged, results


async def test_a_findings_rejudge_writes_a_list_and_a_verdict_derived_from_it(
    tmp_path, no_network
):
    """The decision half of the arm. The judge writes no verdict line at all, so the
    verdict in `verdict.json` has to be `derive_verdict(findings.json)` — computed, not
    asserted — and `findings.json` has to be beside it for a reader to redo the count."""
    from exp2.persistence import load_findings
    from exp2.prompts import derive_verdict

    grid, source, rejudged, results = await _findings_tree(tmp_path, no_network)
    assert [r["status"] for r in results] == ["completed"] * 2
    assert all(r["findings_n"] == 2 and r["findings_flaw_n"] == 1 for r in results)

    for directory in sorted(rejudged.glob("cells/*/runs/*")):
        stored = load_findings(directory)
        assert stored is not None
        assert stored["form"] == "findings" and stored["n_findings"] == 2
        assert stored["n_flaw"] == 1 and stored["ruling_normalised_n"] == 0
        assert [f["ruling"] for f in stored["findings"]] == ["FLAW", "NOT A FLAW"]
        verdict = json.loads((directory / "verdict.json").read_text())
        # THE INVARIANT: the verdict follows from the list by counting
        assert verdict["verdict"] == derive_verdict(stored["findings"]) == "FLAWED"
        # and the grounds are the LIST — the reply trimmed to the findings blocks, so a
        # preamble and three paragraphs of trailing self-commentary are not published as
        # part of the judgment (R4, after the smoke of 2026-09-02)
        assert verdict["reasoning"] == FINDINGS_LIST
        # nothing is lost: `raw` keeps the whole reply, and what the trim dropped is
        # counted rather than only dropped
        assert verdict["raw"] == FINDINGS_JUDGMENT
        assert stored["preamble_chars"] == len("The flawed side raised two points.\n")
        assert stored["trailing_chars"] == len(
            "\n\nFindings are done. They are different ways of expressing the same "
            "worry.")
        manifest = json.loads((directory / "run.json").read_text())
        assert manifest["judge_form"] == "findings"
        assert (manifest["findings_n"], manifest["findings_flaw_n"]) == (2, 1)
        # the wire role is unchanged, so accounting and the cost tables are untouched
        logged = [json.loads(line) for line
                  in (directory / "calls.jsonl").read_text().splitlines()]
        assert [record["role"] for record in logged] == ["judge"]

    # a rejudge does not carry the SOURCE's list forward — it makes a new judgment
    assert not any(source.glob("cells/*/runs/*/findings.json"))


async def test_an_unparseable_findings_list_fails_the_cell_after_one_repair(
    tmp_path, no_network
):
    """The loss rule, unchanged: a malformed judgment buys one format repair and then the
    cell has no decision. A lost cell is a number that is missing; a guessed verdict is a
    number that is wrong and looks fine."""
    grid = build_grid(cases(1), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    no_network.replies["judge_findings"] = "I think the text is fine overall."
    results = await run_stage_rejudge(
        grid, root=tmp_path / "F", config=findings_config(),
        client_config=client_config(), api_key="k", transcript_root=source)
    assert [r["status"] for r in results] == ["failed"]
    assert "still malformed after one format repair" in results[0]["error"]
    assert existing_decision(tmp_path / "F", grid[0]) is None
    # the repair that was spent asked for the FINDINGS format, not "Verdict: FLAWED"
    repairs = [c for c in no_network.calls
               if c["meta"].get("purpose") == "repair"
               and c["meta"].get("role") == "judge"]
    assert repairs and "Findings: none" in repairs[-1]["messages"][-1]["content"]


async def test_the_findings_contest_rules_per_finding_and_re_derives_the_verdict(
    tmp_path, no_network
):
    """The recourse half. The judge answers one line per contest; the contested finding
    takes that ruling, uncontested findings stand, and the verdict is re-derived from the
    whole list — so `verdict == derive_verdict(findings.after.json)` at this end too."""
    from exp2.prompts import derive_verdict

    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    no_network.replies["recourse_judge_findings"] = (
        "Six is the third Catalan number, so the claim does not hold.\n"
        "Contest 1 (Finding 1): NOT A FLAW")
    contests = tmp_path / "C"
    results = await run_stage_contest(
        grid, root=contests, config=findings_config(), client_config=client_config(),
        api_key="k", decision_root=rejudged)
    assert [r["status"] for r in results] == ["completed"] * 2

    for directory in sorted(contests.glob("cells/*/contests/*/runs/*")):
        challenge = json.loads((directory / "challenge.json").read_text())
        assert challenge["arm"] == "findings"
        assert len(challenge["defects"]) == 1
        contest = challenge["defects"][0]
        assert contest["kind"] == "finding" and contest["finding"] == 1
        assert contest["should_be"] == "NOT A FLAW" and contest["void"] is False
        # the claimed verdict is DERIVED: granting this contest leaves nothing FLAW
        assert challenge["claimed_verdict"] == "SOUND"

        ruling = json.loads((directory / "ruling.json").read_text())
        assert ruling["form"] == "derived_findings"
        assert ruling["prompt_form"] == "findings"
        assert ruling["ruling"] == "OVERTURN" and ruling["verdict"] == "SOUND"
        assert ruling["conclusion_line"] == "Contest 1: NOT A FLAW"
        after = json.loads((directory / "findings.after.json").read_text())
        assert [f["ruling"] for f in after["findings"]] == ["NOT A FLAW", "NOT A FLAW"]
        assert after["n_added"] == 0
        assert ruling["verdict"] == derive_verdict(after["findings"])
        # the judge was sent the findings ruling prompt, not the object-level one
        judge_calls = [c for c in no_network.calls
                       if c["meta"].get("role") == "recourse_judge"]
        sent = "".join(m["content"] for m in judge_calls[0]["messages"])
        assert "Rule only on the contests" in sent
        assert "<findings>" in sent

    # R4: THE THREE READERS ARE SHOWN THE SAME TEXT, and it is the TRIMMED list. The
    # `<findings>` block in the challenger's own request is the published grounds
    # exactly — no preamble, no trailing self-commentary — and the ruling judge is shown
    # the same block, so a contest that says "Finding 1" means the same finding 1 to
    # both of them.
    def findings_block(messages):
        sent = "".join(m["content"] for m in messages)
        return sent.split("<findings>")[1].split("</findings>")[0].strip()

    challenger_call = next(c for c in no_network.calls
                           if c["meta"].get("role") == "challenger")
    assert findings_block(challenger_call["messages"]) == FINDINGS_LIST
    ruling_call = next(c for c in no_network.calls
                       if c["meta"].get("role") == "recourse_judge")
    assert findings_block(ruling_call["messages"]) == FINDINGS_LIST
    assert "Findings are done" not in "".join(
        m["content"] for m in challenger_call["messages"])


async def test_the_published_objection_is_the_contests_not_the_public_section(
    tmp_path, no_network
):
    """R12b, and the case is smoke 3's `weak/lojban`.

    `gemini-2.5-flash` wrote `Argument:` as a HEADING inside its own deliberation, so the
    public section held 9,142 characters of private working — rejected drafts, notes to
    itself — of which the lines that parsed into contests were a fraction. All of it went
    into `<objection>` for the ruling judge and the grader, and all of it was published
    as the stakeholder's objection.

    So the objection is the harness's RENDERING of the contests it parsed. The judge
    rules on what will actually be applied, the grader grades that, the published
    document is that, and the whole reply survives in `raw`. The parser is not loosened
    to buy it: what does not parse is not rendered.
    """
    from exp2.prompts import render_contests

    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = (
        "Thinking: I read the list.\n"
        "Argument:\n"
        "Wait — let me reconsider whether finding 1 is really wrong. Argument: no, it "
        "is. Here is my objection, and I will not include the half-written second one.\n"
        "1. Contests: Finding 1\n"
        "   Should be: NOT A FLAW\n"
        '   Text says: "Step 2: C_3 = 6."\n'
        "   Why: six is the third Catalan number.\n"
        "2. Contests: Fin\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "Six is the third Catalan number.\nContest 1 (Finding 1): NOT A FLAW")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    await run_stage_grade(grid, root=contests, config=findings_config(),
                          grading=GradingConfig(), client_config=client_config(),
                          api_key="k", decision_root=rejudged)

    directory = sorted(contests.glob("cells/*/contests/*/runs/*"))[0]
    challenge = json.loads((directory / "challenge.json").read_text())
    expected = render_contests(challenge["defects"])
    assert challenge["text"] == expected
    assert challenge["text_rendered_from_contests"] is True
    assert expected == ('1. Contests: Finding 1\n'
                        '   Should be: NOT A FLAW\n'
                        '   Text says: "Step 2: C_3 = 6."\n'
                        '   Why: six is the third Catalan number.')
    # the deliberation is out of the objection and still on disk
    assert "let me reconsider" not in challenge["text"].lower()
    assert "let me reconsider" in challenge["raw"].lower()

    # ON THE WIRE: both readers of the objection were sent the rendering, byte for byte
    def objection_block(role):
        call = next(c for c in no_network.calls if c["meta"].get("role") == role)
        sent = "".join(m["content"] for m in call["messages"])
        return sent.split("<objection>")[1].split("</objection>")[0].strip()

    assert objection_block("recourse_judge") == expected
    assert objection_block("findings_grader") == expected
    for role in ("recourse_judge", "findings_grader"):
        assert "let me reconsider" not in objection_block(role).lower()

    # AND THE PUBLISHED DOCUMENT is the same text
    document = (directory / "transcript.md").read_text()
    assert "Text says: \"Step 2: C_3 = 6.\"" in document
    assert "let me reconsider" not in document.lower()


async def test_an_objection_with_no_parsed_contests_keeps_its_public_section(
    tmp_path, no_network
):
    """The fallback, and it is the reason the rendering is safe to make the default.

    A STANDS, or a list the parser could not read, renders to nothing — so the objection
    stays the public section, which is the only text there is. Publishing an empty
    objection, or putting one to a judge, would be worse than publishing prose.
    """
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = (
        "Thinking: I read the list.\n"
        "Argument:\n"
        "I disagree with finding 1 in spirit but I cannot put it in the format.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = "Nothing to rule on."
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    directory = sorted(contests.glob("cells/*/contests/*/runs/*"))[0]
    challenge = json.loads((directory / "challenge.json").read_text())
    assert challenge["defects"] == []
    assert challenge["text_rendered_from_contests"] is False
    assert "I cannot put it in the format" in challenge["text"]


async def test_an_upheld_omission_appends_a_finding_and_can_move_the_verdict(
    tmp_path, no_network
):
    """The one contest an EMPTY list can face, and the only one that adds to the list.
    The appended finding is built from the challenger's own quotations, not from the
    judge's prose, so it stays checkable against the record like every other entry."""
    grid = build_grid(cases(1), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    no_network.replies["judge_findings"] = "Nothing identifiable.\n\nFindings: none"
    rejudged = tmp_path / "F"
    await run_stage_rejudge(grid, root=rejudged, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            transcript_root=source)
    # the empty list is an ANSWER: it derives SOUND
    record = existing_decision(rejudged, grid[0])
    assert record.verdict.verdict == "SOUND"

    no_network.replies["challenger"] = (
        "Argument:\n"
        "1. Contests: omission\n"
        '   Record says: "Alice argues in round 1."\n'
        '   Passage: "Step 2: C_3 = 6."\n'
        "   Why: the list is empty and this was raised.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "It was raised and nothing lists it.\n"
        "Contest 1 (omission): FLAW")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    directory = sorted(contests.glob("cells/*/contests/*/runs/*"))[0]
    after = json.loads((directory / "findings.after.json").read_text())
    assert after["n_findings"] == 1 and after["n_added"] == 1
    added = after["findings"][0]
    assert added["added_at_recourse"] is True and added["ruling"] == "FLAW"
    assert added["passage"] == '"Step 2: C_3 = 6."'
    assert "Alice argues in round 1." in added["claim"]
    ruling = json.loads((directory / "ruling.json").read_text())
    assert ruling["verdict"] == "FLAWED" and ruling["ruling"] == "OVERTURN"
    # and the document says what happened, in words a stakeholder can check
    document = (directory / "transcript.md").read_text()
    assert "The judge ruled on each contest" in document
    assert "Contest 1: FLAW" in document
    assert "were added at recourse" in document


async def test_the_findings_agreement_is_mechanical_and_costs_nothing(
    tmp_path, no_network
):
    """No call, and that is the point: under this arm the objection's argument is a
    numbered list the harness already parsed, so `phantom_contest` is a string comparison
    rather than a grader's reading of prose — and it is never pooled with the other
    arms' Haiku column."""
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    before = sum(1 for c in no_network.calls if c["meta"].get("role") == "agreement")
    results = await run_stage_agreement(
        grid, root=contests, config=findings_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k", decision_root=rejudged)
    assert [r["status"] for r in results] == ["completed"] * 2
    after = sum(1 for c in no_network.calls if c["meta"].get("role") == "agreement")
    assert after == before, "the findings agreement stage made a wire call"

    for path in sorted(contests.glob("cells/*/contests/*/runs/*/agreement.json")):
        agreement = json.loads(path.read_text())
        assert agreement["parse_mode"] == "mechanical" and agreement["model"] == ""
        assert agreement["prose_stance"] == "WRONG"
        assert agreement["line_word"] == "REVERSE"
        assert agreement["agrees"] is True
        assert agreement["phantom_contest"] is False

    # a REVERSE with NO PARSED CONTEST under it IS the mechanical phantom
    from exp2.recourse import mechanical_agreement
    from exp2.types import Challenge

    phantom = mechanical_agreement(Challenge(
        text="t", origin="generated", raised=True, arm="findings", stance="contests",
        claimed_verdict="SOUND", defects=[]))
    assert phantom.prose_stance == "RIGHT" and phantom.phantom_contest is True

    # R2d, and the correction the smoke of 2026-09-02 forced: a VOID contest is still a
    # contest for this count. The challenger contested in earnest and quoted the wrong
    # document; calling that a phantom measured the void rule rather than the phantom
    # rate, and fired on two of the strong arm's four objections. It is counted apart,
    # under `challenge_void_only`.
    void_only = mechanical_agreement(Challenge(
        text="t", origin="generated", raised=True, arm="findings", stance="contests",
        claimed_verdict="SOUND",
        defects=[{"index": 1, "void": True}, {"index": 2, "void": True}]))
    assert void_only.prose_stance == "WRONG"
    assert void_only.phantom_contest is False
    assert "2 contests" in void_only.reasoning and "2 of them void" in (
        void_only.reasoning)


async def test_every_contested_findings_cell_is_graded_including_the_ungradable_ones(
    tmp_path, no_network
):
    """The grade stage's gates are DROPPED for this arm, and more of them than for the
    judgment arm. A sound item is not ungradable here — it is the case where grading is
    free, because both directions of a finding contest follow from the label with no
    reading at all."""
    grid = build_grid(cases(1, gold_flawed=False), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    no_network.replies["judge_findings"] = FINDINGS_JUDGMENT
    rejudged = tmp_path / "F"
    await run_stage_rejudge(grid, root=rejudged, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            transcript_root=source)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    before = sum(1 for c in no_network.calls
                 if c["meta"].get("role") == "findings_grader")
    results = await run_stage_grade(
        grid, root=contests, config=findings_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k", decision_root=rejudged)
    assert [r["status"] for r in results] == ["completed"]
    assert results[0]["mode"] == "findings" and results[0]["valid"] is True
    # NO WIRE CALL: on a sound item a `Should be: NOT A FLAW` contest is VALID by rule,
    # so there was nothing left for a grader to decide
    after = sum(1 for c in no_network.calls
                if c["meta"].get("role") == "findings_grader")
    assert after == before

    grade = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/grade.json")).read_text())
    assert grade["mode"] == "findings" and grade["parse_mode"] == "mechanical_only"
    assert grade["contests_n"] == 1 and grade["contests_valid_n"] == 1
    assert grade["contests_mechanical_n"] == 1
    assert grade["line_mismatch"] is False
    assert grade["contests"][0]["reason"].startswith("the item is sound")


async def test_a_findings_grade_on_a_flawed_item_calls_the_grader_and_joins_by_number(
    tmp_path, no_network
):
    """A finding contest on a FLAWED item is the one thing in this arm graded against the
    annotation — this grader is that door — while a void contest beside it is settled by
    a string comparison and is not the grader's to revisit."""
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network, n=1)
    no_network.replies["challenger"] = (
        "Argument:\n"
        "1. Contests: Finding 1\n"
        "   Should be: NOT A FLAW\n"
        '   Text says: "Step 2: C_3 = 6."\n'
        '   Record says: "Alice argues in round 1."\n'
        "   Why: six is right.\n"
        "2. Contests: Finding 9\n"
        "   Should be: FLAW\n"
        '   Text says: "Step 2: C_3 = 6."\n'
        '   Record says: "Alice argues in round 1."\n'
        "   Why: there is no finding 9.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "One holds, one quotes nothing I can find.\n"
        "Contest 1 (Finding 1): FLAW\n"
        "Contest 2 (Finding 9): NOT A FLAW")
    no_network.replies["findings_grader"] = (
        "The finding is about the annotated step.\n"
        "Contest 1: INVALID — finding 1 IS the recorded flaw.\n"
        "Contest 2: VALID — I disagree with the harness.\n"
        "Valid objection: YES")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    results = await run_stage_grade(
        grid, root=contests, config=findings_config(), grading=GradingConfig(),
        client_config=client_config(), api_key="k", decision_root=rejudged)
    assert [r["status"] for r in results] == ["completed"]

    grade = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/grade.json")).read_text())
    assert grade["parse_mode"] == "strict"
    assert grade["contests_n"] == 2
    # the void contest keeps its NUMBER and its mechanical ruling; the grader's opinion
    # about it is DISCARDED rather than merged — a model does not overturn a string
    # comparison
    by_index = {c["index"]: c for c in grade["contests"]}
    assert by_index[2]["mechanical"] is True and by_index[2]["valid"] is False
    assert by_index[2]["reason"].startswith("void at parse time")
    assert by_index[1]["mechanical"] is False and by_index[1]["valid"] is False
    # `valid` is the conjunction of the per-contest rulings, NOT the summary line, and
    # the disagreement is recorded rather than clamped
    assert grade["valid"] is False and grade["line_valid"] is True
    assert grade["line_mismatch"] is True
    # the annotation reached the grader and the void contest was named to it
    sent = "".join(m["content"] for m in no_network.sent_to("findings_grader"))
    assert "Step 2 miscounts." in sent
    assert "Contest 2 has" in sent and "not yours to revisit" in sent
    # the ruling only applied the well-formed contest; the void one changed nothing
    after = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/findings.after.json")).read_text())
    assert [f["ruling"] for f in after["findings"]] == ["FLAW", "NOT A FLAW"]

    # R2b: AND THE DOCUMENT SAYS SO. The judge really did write `Contest 2 (Finding 9):
    # NOT A FLAW`; the contest was void at parse time, so nothing was applied. A smoke
    # record printed exactly such a line above a count that contradicted it, with nothing
    # in between — so the line is printed annotated, with the check that failed.
    document = next(
        contests.glob("cells/*/contests/*/runs/*/transcript.md")).read_text()
    assert ("A line marked *not applied* is one the harness set aside before the "
            "derivation") in document
    assert ("Contest 2: NOT A FLAW — not applied: the finding it contests is not in "
            "the list") in document
    # the well-formed contest's line is printed exactly as the judge wrote it
    assert "Contest 1: FLAW\n" in document
    # and the objection is not described as void-only: one of its two contests holds
    assert "Every contest quoted words that could not be found" not in document


async def test_a_void_only_objection_is_not_a_phantom_and_the_record_says_why(
    tmp_path, no_network
):
    """The smoke of 2026-09-02 found three of the strong arm's four contests voided by a
    rule that was wrong (R1) — and then found the harness reporting them as PHANTOMS and
    the published record printing the judge's ruling on them with no explanation. Three
    facts, three places, and none of them may borrow another's name: the objection
    contested something (so it is not a phantom), nothing could be applied (so the
    document says so), and the cell is excluded from the break-rate denominator by a
    column of its own."""
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network, n=1)
    # Both contests quote a passage that is nowhere in the solution, so both are void on
    # `Text says:` — the anchor a finding contest cannot do without.
    no_network.replies["challenger"] = (
        "Argument:\n"
        "1. Contests: Finding 1\n"
        "   Should be: NOT A FLAW\n"
        '   Text says: "the Riemann hypothesis is assumed throughout"\n'
        "   Why: it is not a flaw.\n"
        "2. Contests: Finding 2\n"
        "   Should be: FLAW\n"
        '   Text says: "a second sentence that is not in the text either"\n'
        "   Why: it is a flaw.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "Neither quotation is in the text under review.\n"
        "Contest 1 (Finding 1): FLAW\n"
        "Contest 2 (Finding 2): FLAW")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    await run_stage_agreement(grid, root=contests, config=findings_config(),
                              grading=GradingConfig(), client_config=client_config(),
                              api_key="k", decision_root=rejudged)

    challenge = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/challenge.json")).read_text())
    assert [c["void"] for c in challenge["defects"]] == [True, True]
    # R2a: the claimed verdict is what they ASKED FOR — both contests granted — and not
    # the decision's own verdict. Finding 1 to NOT A FLAW and finding 2 to FLAW leaves a
    # FLAW in the list, so the objection asked for FLAWED and got its own decision back;
    # what matters is that the number is derived from every contest, void included.
    assert challenge["claimed_verdict"] == "FLAWED"

    agreement = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/agreement.json")).read_text())
    assert agreement["prose_stance"] == "WRONG"
    assert agreement["phantom_contest"] is False

    document = next(
        contests.glob("cells/*/contests/*/runs/*/transcript.md")).read_text()
    # R12d: the header is worded FROM THE FLAGS, so a stakeholder whose contest failed
    # on its index or its direction is not told their quotation was the problem.
    assert ("Every contest was void: the words quoted under Text says were not found "
            "in the text under review.") in document
    assert ("Contest 1: FLAW — not applied: the words quoted under Text says were not "
            "found in the text under review") in document
    # nothing moved: the verdict is the one the findings list derives, unchanged
    after = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/findings.after.json")).read_text())
    assert [f["ruling"] for f in after["findings"]] == ["FLAW", "NOT A FLAW"]

    await run_stage_ruling_agreement(grid, root=contests, config=findings_config(),
                                     grading=GradingConfig(),
                                     client_config=client_config(), api_key="k")

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert rows[0]["challenge_contests_void_n"] == 2
    assert rows[0]["challenge_void_only"] is True
    assert rows[0]["phantom_contest"] is False
    # R12g: `ruling_line_mismatch` IS NOT COMPUTED HERE. The ruling's verdict was derived
    # with both of the judge's lines discarded, so the reader's reading of the prose is
    # being compared against a conclusion the prose never argued for. The READING is kept
    # — it is still a reading — and only the comparison is dropped, as None rather than
    # False so that "not measurable" cannot read as "measured and consistent".
    assert rows[0]["ruling_prose_conclusion"] is not None
    assert rows[0]["ruling_line_mismatch"] is None
    from exp2.analysis import funnel

    metrics = funnel(rows)
    assert metrics["rates"]["ruling_line_mismatch"]["n"] == 0
    assert metrics["findings_contests"]["void_only_rulings_unmeasured"] == 1


async def test_the_index_carries_every_findings_column_and_the_analysis_reads_them(
    tmp_path, no_network
):
    """Absent-not-False throughout: a column that reads 0 says the shape did not occur,
    a column that is absent says nobody looked. And the grade branch has to be an `elif`
    — the flaw grader's `else` would KeyError on the first graded findings cell."""
    from exp2.analysis import funnel

    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    no_network.replies["recourse_judge_findings"] = (
        "It does not hold.\nContest 1 (Finding 1): NOT A FLAW")
    contests = tmp_path / "C"
    for stage in (
        lambda: run_stage_contest(grid, root=contests, config=findings_config(),
                                  client_config=client_config(), api_key="k",
                                  decision_root=rejudged),
        lambda: run_stage_agreement(grid, root=contests, config=findings_config(),
                                    grading=GradingConfig(),
                                    client_config=client_config(), api_key="k",
                                    decision_root=rejudged),
        lambda: run_stage_ruling_agreement(grid, root=contests, config=findings_config(),
                                           grading=GradingConfig(),
                                           client_config=client_config(), api_key="k"),
        lambda: run_stage_grade(grid, root=contests, config=findings_config(),
                                grading=GradingConfig(),
                                client_config=client_config(), api_key="k",
                                decision_root=rejudged),
    ):
        assert [r["status"] for r in await stage()] == ["completed"] * 2

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert len(rows) == 2
    row = rows[0]
    assert row["judge_form"] == "findings"
    assert (row["findings_n"], row["findings_flaw_n"]) == (2, 1)
    assert row["findings_parse_mode"] == "strict"
    assert row["findings_ruling_normalised_n"] == 0
    # R3/R4, report-only: how many passages are really in the text under review, how many
    # findings repeat an earlier passage, and how much of the reply the publication trim
    # dropped either side of the list. Both of the fixture's passages are copied out of
    # the item's own solution, so both are found.
    assert row["findings_passage_exact_n"] == 2
    assert row["findings_duplicate_passage_n"] == 0
    assert row["findings_preamble_chars"] == len("The flawed side raised two points.\n")
    assert row["findings_trailing_chars"] > 0
    # R11b, beside the lenient pair and deliberately stricter: a CASE-SENSITIVE substring
    # test with no ellipsis splitting and no quote stripping beyond the outer pair, and a
    # count of ellipsis joins. Both fixture passages are copied out of the solution
    # exactly, so verbatim == exact here — the GAP between the two columns is the
    # quantity the pair exists to expose.
    assert row["findings_passage_verbatim_n"] == 2
    assert row["findings_passage_ellipsis_n"] == 0
    assert row["challenge_contests_n"] == 1
    assert row["challenge_contests_finding_n"] == 1
    assert row["challenge_contests_omission_n"] == 0
    assert row["challenge_contests_contradiction_n"] == 0
    assert row["challenge_contests_void_n"] == 0
    # R12e: WHICH WAY the finding contests point. The two directions are graded against
    # different bounds (PREREG §5a) and are never pooled, so they are two columns.
    assert row["challenge_contests_to_flaw_n"] == 0
    assert row["challenge_contests_to_not_a_flaw_n"] == 1
    # R12a: a record quotation given on a finding contest and not found. It no longer
    # voids the contest, so it needs a column of its own or the fact disappears.
    assert row["challenge_contests_record_unverified_n"] == 0
    # R2d: an objection every one of whose contests was void cannot break anything, and
    # is NOT a phantom. False here, because this objection's one contest is well formed.
    assert row["challenge_void_only"] is False
    assert row["challenge_seeks_reversal"] is True
    assert row["ruling_form"] == "derived_findings"
    assert row["ruling_contest_lines"] == "Contest 1: NOT A FLAW"
    assert (row["findings_after_n"], row["findings_added_n"]) == (2, 0)
    assert row["ruling_prose_empty"] is False
    assert row["grade_mode"] == "findings"
    assert row["grade_contests_n"] == 1
    assert row["grade_contests_valid_n"] is not None
    assert row["grade_line_mismatch"] is not None
    # the flaw grader's columns are absent, not False
    assert "identified_flaw" not in row and "grade_defects_n" not in row
    # the ruling reader answered in the findings vocabulary and the reading was
    # translated against the RULING's own verdict
    reading = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/ruling_agreement.json")).read_text())
    # CONSISTENT was translated against the RULING's own derived verdict, not the
    # parent's, so `prose_conclusion` is what the lines amount to and `mismatch` is False
    assert reading["line_conclusion"] == reading["prose_conclusion"] == "SOUND"
    assert reading["mismatch"] is False
    # R5: whether the prose handed to the reader ended on a dangling lead-in that the
    # strip dropped. A fact about the RULING PROMPT; 0 is that instruction working.
    assert row["ruling_leadin_stripped"] is False
    # R8: the reader was shown the ruling's own lines, in a block of their own, and told
    # they are not what it is judging
    asked = "".join(m["content"] for m in no_network.sent_to("ruling_reader"))
    assert "<lines>" in asked and "Contest 1: NOT A FLAW" in asked
    # R12g: and it was shown WHAT EACH CONTEST ASKED FOR beside its line, loaded from the
    # sibling `challenge.json` — without which it cannot tell a line that REFUSES a
    # contest from one that GRANTS it, which is what the pilot's reader got wrong.
    assert ("Contest 1: an objection to Finding 1, asking for it to be ruled "
            "`NOT A FLAW`. The reviewer's line: `NOT A FLAW`") in asked
    assert "(the contests were not recorded)" not in asked
    # D5 of the pilot read: a line answered in the wrong vocabulary for its contest's
    # kind. 0 is the judge answering in the right one, and the column has to be there for
    # that to be a fact rather than an absence.
    assert row["ruling_lines_kind_mismatch_n"] == 0
    assert row["ruling_line_mismatch"] is False

    metrics = funnel(rows)
    assert metrics["n_findings_graded"] == 2
    assert metrics["findings_lists"]["findings_per_judgment"] == 2.0
    assert metrics["findings_lists"]["empty_lists"] == 0
    assert metrics["findings_contests"]["by_kind"] == {
        "finding": 2, "omission": 0, "contradiction": 0}
    assert metrics["findings_contests"]["contests_per_objection"] == 1.0
    assert metrics["findings_contests"]["void_only_objections"] == 0
    assert metrics["findings_contests"]["by_direction"] == {
        "to_flaw": 0, "to_not_a_flaw": 2}
    assert metrics["findings_contests"]["record_unverified"] == 0
    assert metrics["findings_contests"]["ruling_lines_kind_mismatched"] == 0
    assert metrics["findings_contests"]["rulings_with_a_kind_mismatched_line"] == 0
    assert metrics["findings_contests"]["void_only_rulings_unmeasured"] == 0
    assert metrics["findings_lists"]["duplicate_passages"] == 0
    # R11b in the metrics, totalled over both cells: every fixture passage is copied out
    # of the solution exactly, so the strict count equals the lenient one and nothing is
    # ellipsis-joined. On a real arm the GAP between the two is the measurement.
    assert metrics["findings_lists"]["passages_exact"] == 4
    assert metrics["findings_lists"]["passages_verbatim"] == 4
    assert metrics["findings_lists"]["passages_ellipsis_joined"] == 0
    assert metrics["findings_lists"]["trailing_chars_total"] > 0
    assert "valid_objection_findings" in metrics["rates"]
    assert "phantom_contest_mechanical" in metrics["rates"]
    assert metrics["rates"]["seeks_reversal_given_contested"]["k"] == 2
    # the flaw-graded bars are EMPTY: these rows are held out of both, because
    # `grade_valid` here is a third kind of validity
    assert metrics["rates"]["valid_objection"]["n"] == 0
    assert metrics["rates"]["identified_flaw"]["n"] == 0


async def test_a_ruling_line_in_the_wrong_vocabulary_is_counted_not_applied(
    tmp_path, no_network
):
    """D5 of the fd1 pilot read, end to end. A contest of a numbered FINDING answered
    `NOT AN OMISSION`: `apply_contest_lines` changes nothing, which is the safe
    direction, and the count is what stops such a contest being indistinguishable from
    one never raised. It happened once in each pilot arm."""
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    no_network.replies["recourse_judge_findings"] = (
        "The list already covers it.\nContest 1 (Finding 1): NOT AN OMISSION")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)

    after = json.loads(
        next(contests.glob("cells/*/contests/*/runs/*/findings.after.json")).read_text())
    # nothing moved: the word does not apply to the kind, so the list is untouched
    assert [f["ruling"] for f in after["findings"]] == ["FLAW", "NOT A FLAW"]

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert rows[0]["ruling_lines_kind_mismatch_n"] == 1
    from exp2.analysis import funnel

    metrics = funnel(rows)
    assert metrics["findings_contests"]["ruling_lines_kind_mismatched"] == 2
    assert metrics["findings_contests"]["rulings_with_a_kind_mismatched_line"] == 2


async def test_an_unfound_record_quote_is_counted_and_the_contest_still_runs(
    tmp_path, no_network
):
    """R12a end to end, and the case is smoke 3's `strong/law`.

    The challenger gave a `Record says:` the matcher could not find, on a contest of a
    FINDING — the one kind for which that field is optional. Before R12a the contest was
    void: the ruling judge ruled on it, the grader was told not to, and the harness threw
    the judge's line away, leaving a published record whose `Contest 1: FLAW` sat above a
    verdict that had not moved. Now the contest is applied, is graded like any other, and
    the unfound quotation is a REPORT COLUMN.
    """
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = (
        "Thinking: I read the list.\n"
        "Argument:\n"
        "1. Contests: Finding 2\n"
        "   Should be: FLAW\n"
        '   Text says: "Step 1: apply the formula."\n'
        '   Record says: "Bob: this was never said by anybody at all"\n'
        "   Why: the formula named really is the wrong one.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "The passage does name the wrong formula.\nContest 1 (Finding 2): FLAW")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    await run_stage_grade(grid, root=contests, config=findings_config(),
                          grading=GradingConfig(), client_config=client_config(),
                          api_key="k", decision_root=rejudged)

    directory = sorted(contests.glob("cells/*/contests/*/runs/*"))[0]
    challenge = json.loads((directory / "challenge.json").read_text())
    contest = challenge["defects"][0]
    assert contest["quote_in_record"] is False
    assert contest["quote_in_text"] is True
    assert contest["void"] is False
    # THE JUDGE'S LINE WAS APPLIED: finding 2 took the ruling it wrote
    after = json.loads((directory / "findings.after.json").read_text())
    assert [f["ruling"] for f in after["findings"]] == ["FLAW", "FLAW"]
    # and the document does not annotate the line as set aside
    document = (directory / "transcript.md").read_text()
    assert "not applied" not in document
    # THE GRADER SAW IT: it was not settled mechanically as void
    grade = json.loads((directory / "grade.json").read_text())
    assert grade["contests"][0]["mechanical"] is False

    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert rows[0]["challenge_contests_record_unverified_n"] == 1
    assert rows[0]["challenge_contests_void_n"] == 0
    assert rows[0]["challenge_contests_to_flaw_n"] == 1
    assert rows[0]["challenge_contests_to_not_a_flaw_n"] == 0


async def test_the_all_void_header_names_the_check_that_failed(tmp_path, no_network):
    """R12d. The header is written from the FLAGS, as the outcome section's per-line
    annotation already was.

    It used to say every contest "quoted words that could not be found", which was the
    common case and not the rule: a contest is void just as often because the finding it
    names is not in the list, or because the ruling it asks for is the one that finding
    already carries. Telling a stakeholder their QUOTATION failed when their INDEX failed
    sends them to check the wrong thing.
    """
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = (
        "Argument:\n"
        "1. Contests: Finding 9\n"
        "   Should be: FLAW\n"
        '   Text says: "Step 1: apply the formula."\n'
        "   Why: there is no finding 9.\n"
        "2. Contests: Finding 1\n"
        "   Should be: FLAW\n"
        '   Text says: "Step 2: C_3 = 6."\n'
        "   Why: it already says FLAW.\n"
        "Decision: REVERSE"
    )
    no_network.replies["recourse_judge_findings"] = (
        "Neither contest can be granted.\n"
        "Contest 1 (Finding 9): NOT A FLAW\n"
        "Contest 2 (Finding 1): FLAW")
    contests = tmp_path / "C"
    await run_stage_contest(grid, root=contests, config=findings_config(),
                            client_config=client_config(), api_key="k",
                            decision_root=rejudged)
    directory = sorted(contests.glob("cells/*/contests/*/runs/*"))[0]
    document = (directory / "transcript.md").read_text()
    assert ("Every contest was void: the finding it contests is not in the list; and "
            "the ruling it asks for is the one that finding already carries.") in document
    assert "quoted words that could not be found" not in document


async def test_a_findings_ruling_that_announces_its_lines_is_stripped_and_counted(
    tmp_path, no_network
):
    """R11a, from smoke 2's weak/medqa record. The judge is told to write its lines and
    not announce them; when it announces them anyway the announcement is the LAST thing
    in `Ruling.reasoning`, because the lines themselves are past the cut. Published as
    it stood, the document's "Grounds given" ended on "The final answer is:" and the
    answer appeared three paragraphs lower under a different heading.

    The document now goes through `strip_ruling_prose` — the same function the
    ruling-agreement reader is handed its copy through, so the reader and the reader's
    audience see the same words — and `ruling_leadin_stripped` says it happened even on
    a tree where the reader stage never ran. `raw` is never touched: the full document
    still prints the announcement verbatim."""
    grid, _, rejudged, _ = await _findings_tree(tmp_path, no_network)
    no_network.replies["challenger"] = FINDINGS_OBJECTION
    no_network.replies["recourse_judge_findings"] = (
        "Finding 1's passage does bear out the claim; the finding stands.\n"
        "The final answer is:\n"
        "Contest 1 (Finding 1): FLAW")
    contests = tmp_path / "C"
    assert [r["status"] for r in await run_stage_contest(
        grid, root=contests, config=findings_config(), client_config=client_config(),
        api_key="k", decision_root=rejudged)] == ["completed"] * 2

    directory = next(contests.glob("cells/*/contests/*/runs/*/ruling.json")).parent
    ruling = json.loads((directory / "ruling.json").read_text())
    # `raw` and `reasoning` keep every word the judge wrote; only the DOCUMENT trims.
    assert "The final answer is:" in ruling["reasoning"]
    assert "The final answer is:" in ruling["raw"]

    document = (directory / "transcript.md").read_text()
    outcome = document[document.index("## The outcome"):]
    grounds = outcome[outcome.index("**Grounds given:**"):
                      outcome.index("**The judge ruled on each contest:**")]
    assert "the finding stands" in grounds
    assert "The final answer is:" not in grounds
    # and the line it announced is still printed, under the heading that belongs to it
    # (in the parser's canonical form, `Contest n: <ruling>`)
    assert "Contest 1: FLAW" in outcome

    # the whole reply, untouched, in the document meant to be checked rather than read
    assert "The final answer is:" in (directory / "transcript_full.md").read_text()

    # the column, on a tree where `ruling_agreement` has not run at all
    rows = build_index(grid, root=contests, challenger_model="strong/model",
                       decision_root=rejudged)
    assert rows[0]["ruling_leadin_stripped"] is True
    assert "ruling_prose_conclusion" not in rows[0]


def test_the_findings_caveat_says_which_validity_and_which_phantom(tmp_path):
    from exp2.analysis import caveats

    rows = [{"cell_id": "c", "item_id": "i", "condition": "debate",
             "judge_form": "findings", "grade_mode": "findings",
             "grade_valid": True, "initially_correct": False, "gold_flawed": True,
             "challenge_arm": "findings", "ruling_form": "derived_findings"}]
    text = next(c for c in caveats(rows, ["debate"]) if "THIS ARM'S DECISION IS A LIST" in c)
    assert "DERIVED by code" in text
    assert "THIRD kind of validity" in text
    assert "MECHANICAL" in text
    assert "challenge_seeks_reversal" in text
    # and the specious caveat still reads this as a THIRD-PARTY ruling rather than an
    # in-conversation re-decision, which it would if `derived_findings` were unknown
    specious = next(c for c in caveats(rows, ["debate"])
                    if "no specious-objection control" in c)
    assert "no condition adjudicates its own appeal" in specious


def test_a_findings_spec_must_state_both_fields_and_its_estimate_says_what_it_buys(
    tmp_path, monkeypatch, capsys
):
    """Both halves of the same trap. `challenger_variant` and `judge_form` BOTH default
    to their historical values, so a spec called `fd1-weak` with either one commented out
    would run the ordinary arm, write it into `outputs/experiments/fd1-weak/` and produce
    a tree whose every number is a verdict-form number under a findings name — after
    paying for 1,644 judgments. `DebateConfig` refuses one order; this guard catches the
    other."""
    from exp2.experiment_cli import main

    outputs = tmp_path / "outputs" / "experiments"
    (outputs / "jd3-main").mkdir(parents=True)
    (outputs / "jd3-main" / "experiment.json").write_text(
        json.dumps({"name": "jd3-main"}), encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n".join(json.dumps(c.to_dict()) for c in cases(2)),
                          encoding="utf-8")

    def spec_for(name, body):
        path = tmp_path / f"{name}.toml"
        path.write_text(
            f'name = "{name}"\n'
            f'cases = "{cases_path}"\n'
            'conditions = ["debate"]\n'
            f'transcripts_from = "{outputs / "jd3-main"}"\n'
            '[debate]\n' + body, encoding="utf-8")
        return path

    monkeypatch.chdir(tmp_path)
    # neither field stated
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec_for("fd1-weak", "")), "--stage", "rejudge",
              "--dry-run"])
    assert "sets no `challenger_variant`" in str(excinfo.value)
    # the variant stated as `findings` and the judge form not: `DebateConfig` refuses it
    # before the spec guard is reached, because a findings challenger has no list to
    # contest without a findings judgment
    from exp2.config import ConfigError

    with pytest.raises(ConfigError) as config_error:
        main(["--spec", str(spec_for("fd1-weak2",
                                     'challenger_variant = "findings"\n')),
              "--stage", "rejudge", "--dry-run"])
    assert "needs judge_form='findings'" in str(config_error.value)
    # and the other order — a findings-named spec whose challenger is stated but whose
    # JUDGE would quietly write a prose verdict — is what the spec guard is for
    with pytest.raises(SystemExit) as excinfo:
        main(["--spec", str(spec_for("fd1-weak4",
                                     'challenger_variant = "neutral"\n')),
              "--stage", "rejudge", "--dry-run"])
    assert "sets no `judge_form`" in str(excinfo.value)

    both = spec_for("fd1-weak3", 'challenger_variant = "findings"\n'
                                 'judge_form = "findings"\n')
    assert main(["--spec", str(both), "--stage", "rejudge", "--dry-run"]) == 0
    printed = capsys.readouterr().out
    # the dry-run prints the field with its reason, which is what the run is approved
    # from (HANDOFF §2.4)
    assert "judge_form" in printed and "findings" in printed
    assert "The verdict is DERIVED by code" in printed
    # the grading term is the whole grid — every contested cell is graded — and the
    # agreement term is ZERO, because that stage makes no call under this arm
    assert "agreement <= 0" in printed
    assert "grading <= 2" in printed
    assert "the AGREEMENT term is 0 and that is not an omission" in printed
    assert "the grading term is the whole grid" in printed


async def test_the_findings_challenger_is_loud_when_there_is_no_list_to_contest(
    tmp_path, no_network
):
    """`DebateFailure`, not an empty objection. `DebateConfig` already refuses the
    combination that would produce this, so a cell reaching it is a wiring bug — and a
    silent empty list would produce a whole tree of objections against nothing, every one
    of them void, with no stage saying why."""
    from exp2.engine import DebateFailure
    from exp2.recourse import generate_challenge

    grid = build_grid(cases(1), ["debate"])
    source = tmp_path / "sweep"
    await run_stage_decide(grid, root=source, config=make_config(),
                           client_config=client_config(), api_key="k")
    # an ORDINARY decision: prose verdict, no findings.json beside it
    record = existing_decision(source, grid[0])
    assert not (record.directory / "findings.json").is_file()
    with pytest.raises(DebateFailure, match="needs `findings.json`"):
        await generate_challenge(record, findings_config(), no_network)


def test_judge_form_is_a_decision_key_and_a_contest_inherits_it():
    """It changes what the judge was ASKED and therefore what the decision IS, so a
    contest of that decision must carry it: the challenger has to be shown the list the
    judge actually wrote. `RECOURSE_ONLY_KEYS` is the exemption list for settings a
    decision had no opinion about, and this is not one of them."""
    from exp2.config import RECOURSE_ONLY_KEYS, WHY

    assert "judge_form" not in RECOURSE_ONLY_KEYS
    assert "judge_form" in WHY
    assert "verdict_order` is UNUSED" in WHY["judge_form"]
