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
    run_stage_rerule,
    run_stage_ruling_agreement,
    source_contests,
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
