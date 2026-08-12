"""End-to-end orchestration: scheduling, verdict resolution, crash safety."""

from __future__ import annotations

import json

import pytest

from conftest import FakeClient
from helpers import (
    CONSTITUTION,
    JUDGE_COT,
    make_writer,
    recorded_run,
)

from constitutional_debate.artifacts import (
    PRIVATE_THINKING_NOTE,
    render_decision_record,
)
from constitutional_debate.debate import (
    DebateFailure,
    TruncatedOutputError,
    run_debate,
)
from constitutional_debate.types import Speaker



# --------------------------------------------------------------------------- #
# scheduling
# --------------------------------------------------------------------------- #


async def test_simultaneous_runs_both_debaters_concurrently(task, seating, make_config):
    client = FakeClient()
    config = make_config(turn_style="simultaneous")
    await run_debate(task, None, config, seating, client)

    assert client.max_in_flight == 2, "both debaters must be in flight together"
    assert len(client.calls) == 2 * config.n_rounds + 1


async def test_sequential_runs_one_at_a_time(task, seating, make_config):
    client = FakeClient()
    config = make_config(turn_style="sequential")
    await run_debate(task, None, config, seating, client)

    assert client.max_in_flight == 1, "a serial for-loop is the point here"
    assert len(client.calls) == 2 * config.n_rounds + 1


async def test_sequential_lets_bob_see_alices_current_round(
    task, seating, make_config
):
    client = FakeClient()
    await run_debate(task, None, make_config(turn_style="sequential"), seating, client)

    bob_round_2 = next(
        c
        for c in client.calls
        if c["meta"].get("speaker") == "Bob" and c["meta"].get("round") == 2
    )
    assert "Alice argument round 2" in bob_round_2["messages"][1]["content"]


async def test_simultaneous_hides_the_current_round_from_both(
    task, seating, make_config
):
    client = FakeClient()
    await run_debate(
        task, None, make_config(turn_style="simultaneous"), seating, client
    )

    for speaker in ("Alice", "Bob"):
        round_2 = next(
            c
            for c in client.calls
            if c["meta"].get("speaker") == speaker and c["meta"].get("round") == 2
        )
        opponent = "Bob" if speaker == "Alice" else "Alice"
        content = round_2["messages"][1]["content"]
        assert f"{opponent} argument round 1" in content
        assert f"{opponent} argument round 2" not in content


# --------------------------------------------------------------------------- #
# verdict resolution
# --------------------------------------------------------------------------- #


async def test_judge_choice_resolves_through_choice_order(task, seating, config):
    """The highest-consequence silent bug: choice 1 is not answer index 0 here."""
    client = FakeClient(scripted={"judge": "Answer: 1"})
    result = await run_debate(task, None, config, seating, client)

    assert seating.choice_order == (1, 0)
    assert result.verdict.choice == 1
    assert result.verdict.answer_index == 1, "choice 1 maps to the *second* answer"
    assert result.verdict.correct is None, "no gold answer, so no correctness"


async def test_correctness_is_scored_when_gold_exists(task, seating, config):
    verifiable = task.__class__(
        task_id=task.task_id,
        question=task.question,
        answers=task.answers,
        gold_index=1,
    )
    client = FakeClient(scripted={"judge": "Answer: 1"})
    result = await run_debate(verifiable, None, config, seating, client)
    assert result.verdict.answer_index == 1
    assert result.verdict.correct is True

    client = FakeClient(scripted={"judge": "Answer: 2"})
    result = await run_debate(verifiable, None, config, seating, client)
    assert result.verdict.correct is False


async def test_judge_never_receives_private_thinking(task, seating, config):
    client = FakeClient()
    await run_debate(task, None, config, seating, client)

    judge_call = next(c for c in client.calls if c["meta"]["role"] == "judge")
    body = json.dumps(judge_call["messages"])
    assert "private plan" not in body
    assert "Thinking:" not in body


# --------------------------------------------------------------------------- #
# failure handling
# --------------------------------------------------------------------------- #


async def test_malformed_debater_output_is_repaired_once(task, seating, config):
    client = FakeClient(fail_on={(1, "Alice"): "malformed"})
    result = await run_debate(task, None, config, seating, client)

    alice_r1 = next(
        t for t in result.transcript.all_turns()
        if t.round == 1 and t.speaker is Speaker.ALICE
    )
    assert alice_r1.repair_attempts == 1
    assert alice_r1.argument == "Alice argument round 1"
    repair_calls = [c for c in client.calls if c["meta"].get("purpose") == "repair"]
    assert len(repair_calls) == 1
    assert repair_calls[0]["messages"][-2]["role"] == "assistant"


async def test_truncated_response_is_fatal_and_names_the_lever(
    task, seating, config
):
    client = FakeClient(fail_on={(1, "Alice"): "truncated"})
    with pytest.raises((TruncatedOutputError, DebateFailure), match="max_tokens"):
        await run_debate(task, None, config, seating, client)


async def test_unrepairable_judge_output_fails_the_run(task, seating, config):
    client = FakeClient(
        scripted={"judge": "I genuinely cannot choose between these."},
    )
    with pytest.raises(DebateFailure, match="judge output still malformed"):
        await run_debate(task, None, config, seating, client)


async def test_a_completed_turn_survives_its_siblings_failure(
    tmp_path, task, seating, make_config
):
    """Alice's paid generation must not be discarded because Bob's call died."""
    config = make_config(turn_style="simultaneous")
    writer = make_writer(tmp_path, task, config, seating)
    client = FakeClient(fail_on={(2, "Bob"): "http_error"})

    with pytest.raises(DebateFailure, match="round 2 failed"):
        await run_debate(task, None, config, seating, client, writer=writer)

    transcript = json.loads((writer.dir / "transcript.json").read_text())
    rounds = [(t["round"], t["speaker"]) for t in transcript["turns"]]
    assert rounds == [(1, "Alice"), (1, "Bob"), (2, "Alice")]


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #


async def test_run_directory_is_complete(
    tmp_path, task, seating, config
):
    writer = make_writer(tmp_path, task, config, seating, context=CONSTITUTION)
    client = FakeClient(sink=writer.record_call, scripted={"judge": JUDGE_COT})

    result = await run_debate(
        task, CONSTITUTION, config, seating, client, writer=writer
    )
    writer.finish(status="completed")

    for name in (
        "run.json", "config.json", "task.json", "seating.json",
        "constitution.md", "calls.jsonl", "transcript.json",
        "transcript.md", "verdict.json",
    ):
        assert (writer.dir / name).is_file(), f"missing artifact: {name}"

    manifest = json.loads((writer.dir / "run.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["profile"] == "constitutional"
    assert manifest["constitution_sha256"] == CONSTITUTION.sha256()

    calls = [
        json.loads(line)
        for line in (writer.dir / "calls.jsonl").read_text().splitlines()
    ]
    assert len(calls) == 7
    assert all({"call_id", "role", "attempt"} <= set(c) for c in calls), (
        "every record needs join keys; gather makes line order nondeterministic"
    )
    assert {c["call_id"] for c in calls} >= {
        t.call_id for t in result.transcript.all_turns()
    }

    published = (writer.dir / "transcript.md").read_text()
    assert "Alice argument round 1" in published
    assert "## Round 1" in published and "### Alice" in published
    assert task.question in published, "the published document states the question"
    assert JUDGE_COT.split("\n")[0] in published, "...and the judge's grounds"

    # The full record is the readable one, and the one that must never be
    # mistaken for the publishable artifact.
    full = (writer.dir / "transcript.md").read_text()
    assert PRIVATE_THINKING_NOTE in full
    assert "private plan" in full
    assert task.question in full
    assert "## Decision" in full
    assert "Alice's case was better grounded" in full, "the judge's own words"

    document = json.loads((writer.dir / "transcript.json").read_text())
    assert document["question"] == task.question
    assert document["answers"] == list(task.answers)
    assert document["positions"]["Alice"] == {
        "answer_index": 0,
        "answer": task.answers[0],
        "judge_choice": 2,  # seating fixture uses choice_order (1, 0)
    }

    verdict = json.loads((writer.dir / "verdict.json").read_text())
    assert verdict["reasoning"] == "Alice's case was better grounded."


async def test_manifest_marks_a_run_before_any_call(tmp_path, task, seating, config):
    writer = make_writer(tmp_path, task, config, seating)
    manifest = json.loads((writer.dir / "run.json").read_text())
    assert manifest["status"] == "running", (
        "a crashed run must be distinguishable from a finished one"
    )
    assert manifest["ended_utc"] is None


async def test_calls_jsonl_survives_concurrent_writers(tmp_path, task, seating, config):
    """Records carry full bodies; unlocked concurrent appends would interleave."""
    import asyncio

    writer = make_writer(tmp_path, task, config, seating)
    payload = "x" * 20_000
    await asyncio.gather(
        *(
            writer.record_call({"call_id": str(i), "role": "debater", "blob": payload})
            for i in range(20)
        )
    )
    lines = (writer.dir / "calls.jsonl").read_text().splitlines()
    assert len(lines) == 20
    assert {json.loads(line)["call_id"] for line in lines} == {
        str(i) for i in range(20)
    }


async def test_the_written_document_is_what_the_renderer_renders(
    tmp_path, task, seating, config
):
    """The writer and the renderer must not drift apart.

    ``RunWriter`` writes ``transcript.md`` during the run; ``artifacts`` is
    where the document is defined. Nothing else would notice if the two came to
    disagree, and the published document is the artifact the project's claim
    rests on.
    """
    writer, result = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    assert (writer.dir / "transcript.md").read_text() == render_decision_record(
        task, seating, result.transcript, result.verdict, judge_cot=config.judge_cot
    )


# --------------------------------------------------------------------------- #


def test_client_config_is_recorded_but_kept_out_of_config_json(
    tmp_path, task, seating, config
):
    writer = make_writer(tmp_path, task, config, seating)
    recorded = json.loads((writer.dir / "config.json").read_text())
    manifest = json.loads((writer.dir / "run.json").read_text())

    assert "max_attempts" not in recorded, "operational settings are not the record"
    assert "turn_style" in recorded
    assert isinstance(manifest["client_config"], dict)
    assert "max_attempts" in manifest["client_config"]


