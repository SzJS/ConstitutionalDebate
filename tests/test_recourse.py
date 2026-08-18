"""Recourse orchestration: the ruling, and the record it leaves.

The decisive property under test is the one the ruling form exists for: the
decision stands unless the challenge moves it, and which answer stands afterwards
is *derived* from the ruling rather than parsed out of it.
"""

from __future__ import annotations

import json

import pytest

from conftest import FakeClient
from helpers import (
    CONSTITUTION,
    JUDGE_COT,
    SOLO_THINKING,
    file_challenge,
    generated_challenge,
    make_recourse_writer,
    make_writer,
    recorded_recourse,
    recorded_run,
    recorded_solo_run,
)

from constitutional_debate.debate import run_recourse
from constitutional_debate.persistence import RunWriter, load_run_record

UPHOLD = "The challenge reargues the question.\n\nRuling: UPHOLD"
OVERTURN = "The figure was indeed unsupported.\n\nRuling: OVERTURN"


async def parent_run(tmp_path, task, config, seating, context=None):
    return await recorded_run(
        tmp_path, task, config, seating, context, scripted={"judge": JUDGE_COT}
    )


def read(writer, name):
    return json.loads((writer.dir / name).read_text())


# --------------------------------------------------------------------------- #
# the ruling
# --------------------------------------------------------------------------- #


async def test_upholding_leaves_the_decision_exactly_as_it_was(
    tmp_path, task, seating, config
):
    parent, parent_result = await parent_run(tmp_path, task, config, seating)
    _, result, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    assert result.ruling.ruling == "UPHOLD"
    assert result.ruling.upheld is True
    assert result.ruling.answer_index == parent_result.verdict.answer_index
    assert result.ruling.choice == parent_result.verdict.choice
    assert result.ruling.changed_the_decision is False


async def test_overturning_flips_the_answer_and_resolves_through_the_seating(
    tmp_path, task, seating, config
):
    parent, parent_result = await parent_run(tmp_path, task, config, seating)
    _, result, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": OVERTURN}
    )

    decided = parent_result.verdict.answer_index
    assert result.ruling.answer_index == 1 - decided
    assert result.ruling.choice == seating.choice_for_answer(1 - decided)
    assert result.ruling.changed_the_decision is True
    # The seating is inherited whole, so the choice numbering does not shift.
    assert result.ruling.parent_choice == parent_result.verdict.choice


async def test_correctness_is_rescored_against_gold_after_a_ruling(
    tmp_path, seating, config
):
    from constitutional_debate.types import Task

    verifiable = Task(
        task_id="fixture-task",
        question="Is it OK to use tax havens?",
        answers=("It is OK to use tax havens.", "It is NOT OK to use tax havens."),
        gold_index=1,
    )
    parent, parent_result = await parent_run(tmp_path, verifiable, config, seating)
    assert parent_result.verdict.correct is True  # judge chose 1 -> answers[1] == gold

    _, result, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": OVERTURN}
    )
    assert result.ruling.correct is False, "overturning moved it off the gold answer"


async def test_an_unrulable_response_is_repaired_once_then_fails(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    with pytest.raises(Exception, match="recourse_judge output still malformed"):
        await recorded_recourse(
            tmp_path, parent, scripted={"recourse_judge": "I am not sure."}
        )


# --------------------------------------------------------------------------- #
# the two protocols
# --------------------------------------------------------------------------- #


async def test_judge_only_rules_without_a_further_exchange(
    tmp_path, task, seating, config, make_config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, result, _ = await recorded_recourse(
        tmp_path, parent, config=make_config(recourse_rounds=0),
        scripted={"recourse_judge": UPHOLD},
    )

    assert result.ruling.protocol == "judge_only"
    assert result.transcript.turns == []
    assert read(writer, "run.json")["recourse_protocol"] == "judge_only"
    assert read(writer, "transcript.json")["turns"] == []
    calls = [json.loads(x) for x in (writer.dir / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 1, "the judge-only protocol is exactly one call"
    assert calls[0]["role"] == "recourse_judge"


@pytest.mark.parametrize("recourse_rounds", [1, 2])
async def test_the_debate_protocol_runs_the_configured_rounds_simultaneously(
    tmp_path, task, seating, config, make_config, recourse_rounds
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer, result, _ = await recorded_recourse(
        tmp_path, parent, config=make_config(recourse_rounds=recourse_rounds),
        scripted={"recourse_judge": UPHOLD},
    )

    assert result.ruling.protocol == "debate"
    assert len(result.transcript.turns) == 2 * recourse_rounds
    rounds = sorted({t.round for t in result.transcript.all_turns()})
    assert rounds == [
        parent_record.config.n_rounds + n for n in range(1, recourse_rounds + 1)
    ], "recourse rounds continue the parent's numbering"


async def test_recourse_rounds_run_both_debaters_concurrently(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(parent_record, file_challenge(), config, client, writer=writer)
    assert client.max_in_flight == 2, "a recourse round is a round like any other"


# --------------------------------------------------------------------------- #
# who argues which side, on the wire
# --------------------------------------------------------------------------- #


async def test_the_debater_whose_answer_lost_argues_for_the_challenge(
    tmp_path, task, seating, config
):
    parent, parent_result = await parent_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(parent_record, file_challenge(), config, client, writer=writer)

    winner = seating.speaker_for_choice(parent_result.verdict.choice)
    loser = winner.opponent
    by_speaker = {
        c["meta"]["speaker"]: c["messages"][1]["content"]
        for c in client.calls
        if c["meta"].get("purpose") == "recourse_turn"
    }
    assert "should be overturned" in by_speaker[str(loser)]
    assert "the decision should stand" in by_speaker[str(winner)]


# --------------------------------------------------------------------------- #
# the challenge
# --------------------------------------------------------------------------- #


async def test_a_supplied_challenge_costs_no_generation(tmp_path, task, seating, config):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, result, _ = await recorded_recourse(
        tmp_path, parent, challenge=file_challenge("A supplied objection."),
        scripted={"recourse_judge": UPHOLD},
    )

    assert result.challenge.origin == "file"
    assert (writer.dir / "challenge.md").read_text().strip() == "A supplied objection."
    calls = [json.loads(x) for x in (writer.dir / "calls.jsonl").read_text().splitlines()]
    assert not any(c["role"] == "challenger" for c in calls)


@pytest.mark.parametrize("arm", ["grounded", "specious", "neutral"])
async def test_a_generated_challenge_is_recorded_with_its_provenance(
    tmp_path, task, seating, config, arm
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, result, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(arm=arm),
        scripted={"recourse_judge": UPHOLD},
    )

    assert result.challenge.origin == "generated"
    assert result.challenge.arm == arm
    assert result.challenge.visibility == "public"
    assert result.challenge.call_id
    recorded = read(writer, "challenge.json")
    assert recorded["arm"] == arm
    assert recorded["text"] == result.challenge.text
    manifest = read(writer, "run.json")
    assert manifest["challenge_arm"] == arm
    assert manifest["challenge_sha256"] == result.challenge.sha256()


async def test_the_generators_scratchpad_is_recorded_and_is_not_the_challenge(
    tmp_path, task, seating, config
):
    """The generator's private reasoning is kept out of the challenge itself.

    It is recorded in challenge.json — the record is complete — but the document
    put to the judge is the argument, not the scratchpad behind it.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, result, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(),
        scripted={"recourse_judge": UPHOLD},
    )

    assert "private plan for the challenge" in result.challenge.thinking
    assert "private plan for the challenge" not in (writer.dir / "challenge.md").read_text()
    calls = [json.loads(x) for x in (writer.dir / "calls.jsonl").read_text().splitlines()]
    for call in calls:
        if call["role"] == "challenger":
            continue
        assert "private plan for the challenge" not in json.dumps(call["request_body"])


async def test_a_public_visibility_generator_is_not_shown_the_debaters_thinking(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(
        parent_record, generated_challenge(visibility="public"), config, client,
        writer=writer,
    )

    challenger_call = next(c for c in client.calls if c["meta"]["role"] == "challenger")
    assert "private plan for Alice" not in json.dumps(challenger_call["messages"])

    # ...and with full visibility it is, deliberately.
    client_full = FakeClient(scripted={"recourse_judge": UPHOLD})
    writer_full = make_recourse_writer(tmp_path, parent_record, config)
    await run_recourse(
        parent_record, generated_challenge(visibility="full"), config, client_full,
        writer=writer_full,
    )
    challenger_call = next(
        c for c in client_full.calls if c["meta"]["role"] == "challenger"
    )
    assert "private plan for Alice" in json.dumps(challenger_call["messages"])


async def test_the_recourse_judge_never_sees_any_private_thinking(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(parent_record, file_challenge(), config, client, writer=writer)

    ruling_call = next(c for c in client.calls if c["meta"]["role"] == "recourse_judge")
    body = json.dumps(ruling_call["messages"])
    assert "private plan" not in body
    assert "Thinking:" not in body


# --------------------------------------------------------------------------- #
# the record
# --------------------------------------------------------------------------- #


async def test_a_recourse_directory_is_complete_and_self_contained(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating, CONSTITUTION)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(),
        scripted={"recourse_judge": UPHOLD},
    )

    for name in (
        "run.json", "config.json", "task.json", "seating.json", "constitution.md",
        "challenge.md", "challenge.json", "calls.jsonl", "transcript.json",
        "transcript.md", "ruling.json",
    ):
        assert (writer.dir / name).is_file(), f"missing artifact: {name}"
    assert (writer.dir / "parent" / "run.json").is_file()
    assert (writer.dir / "parent" / "verdict.json").is_file()
    assert not (writer.dir / "verdict.json").exists(), (
        "a recourse records a ruling, not a verdict"
    )

    manifest = read(writer, "run.json")
    assert manifest["kind"] == "recourse"
    assert manifest["parent_run_id"] == parent.run_id
    assert manifest["parent_chain"] == [parent.run_id]
    assert manifest["profile"] == "constitutional", "the profile is inherited"


async def test_the_recourse_transcript_holds_only_its_own_turns(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    document = read(writer, "transcript.json")
    assert {t["round"] for t in document["turns"]} == {config.n_rounds + 1}
    assert document["parent_run_id"] == parent.run_id
    assert document["parent_rounds"] == config.n_rounds
    # The parent's turns live in exactly one place.
    parent_document = json.loads((writer.dir / "parent" / "transcript.json").read_text())
    assert len(parent_document["turns"]) == 2 * config.n_rounds


async def test_the_parent_copy_is_hashed_when_it_is_made(
    tmp_path, task, seating, config
):
    from constitutional_debate.persistence import tree_sha256

    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    manifest = read(writer, "run.json")
    assert manifest["parent_sha256"] == tree_sha256(writer.dir / "parent")

    (writer.dir / "parent" / "verdict.json").write_text("{}")
    assert manifest["parent_sha256"] != tree_sha256(writer.dir / "parent")


async def test_a_ruling_cannot_itself_be_challenged_yet_and_says_so(
    tmp_path, task, seating, config, make_config
):
    """Chained recourse is out of scope, and must fail loudly rather than oddly.

    A recourse records a ruling, not a verdict, so there is no "decision under
    challenge" for a second round of this mechanism to quote. That is a real
    limitation of the protocol as built; the loader states it in those terms
    instead of raising a KeyError on a missing file.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    first, _, _ = await recorded_recourse(
        tmp_path, parent, config=make_config(recourse_rounds=0),
        scripted={"recourse_judge": UPHOLD},
    )
    with pytest.raises(ValueError, match="records no verdict"):
        load_run_record(first.dir)


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #


async def test_an_unfinished_run_cannot_be_challenged(tmp_path, task, seating, config):
    writer = make_writer(tmp_path, task, config, seating)  # status: running
    with pytest.raises(ValueError, match="only a completed run can be challenged"):
        load_run_record(writer.dir)


async def test_a_recourse_cannot_change_the_parents_round_count(
    tmp_path, task, seating, config, make_config
):
    """The round boundary is what separates the debate from the contest of it."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    from constitutional_debate.config import load_config

    with pytest.raises(ValueError, match="inherits the parent's n_rounds"):
        RunWriter.create_recourse(
            parent=load_run_record(parent.dir),
            config=make_config(n_rounds=config.n_rounds + 1),
            client_config=load_config()[1],
            outputs_root=tmp_path,
        )





async def test_a_recourse_does_not_inherit_the_parents_recourse_settings(
    tmp_path, task, seating, make_config
):
    """A debate run records recourse_rounds but had no opinion about it."""
    from constitutional_debate.config import RECOURSE_ONLY_KEYS, load_config

    parent_config = make_config(recourse_rounds=0, word_limit=250)
    parent, _ = await parent_run(tmp_path, task, parent_config, seating)
    parent_record = load_run_record(parent.dir)

    inherited, _ = load_config(
        inherit={
            k: v for k, v in parent_record.config.to_dict().items()
            if k not in RECOURSE_ONLY_KEYS
        }
    )
    assert inherited.word_limit == 250, "decision-relevant settings are inherited"
    assert inherited.recourse_rounds == 1, "how it is contested is not"


async def test_a_recourse_republishes_the_parents_provider_reasoning(tmp_path):
    """The parent's reasoning channel must survive the round-trip to a contest.

    A recourse re-renders the parent's rounds from the loaded record. If
    load_run_record drops native_reasoning, the published contest document shows
    the parent debate with the provider's channel missing — and the whole point
    of publishing it is that the record contains every channel that moved the
    outcome. The failure is silent: the document still renders, just without it.
    """
    from constitutional_debate.persistence import load_run_record
    from helpers import config, make_seating, make_task, recorded_run

    NEEDLE = "PROVIDER-REASONING-must-survive-the-round-trip"
    writer, _ = await recorded_run(
        tmp_path, make_task(gold_index=0), config(), make_seating()
    )
    # stamp reasoning onto the recorded turns, as a reasoning-bearing model would
    data = json.loads((writer.dir / "transcript.json").read_text())
    for turn in data["turns"]:
        turn["native_reasoning"] = NEEDLE
        turn["has_native_reasoning"] = True
    (writer.dir / "transcript.json").write_text(json.dumps(data), encoding="utf-8")

    parent = load_run_record(writer.dir)
    assert all(t.native_reasoning == NEEDLE for t in parent.transcript.all_turns()), (
        "load_run_record must restore native_reasoning, not drop it"
    )


async def test_withheld_reasoning_survives_the_round_trip_too(tmp_path):
    """The flag matters more than the text: it marks the uninspectable case."""
    from constitutional_debate.persistence import load_run_record
    from helpers import config, make_seating, make_task, recorded_run

    writer, _ = await recorded_run(
        tmp_path, make_task(gold_index=0), config(), make_seating()
    )
    data = json.loads((writer.dir / "transcript.json").read_text())
    for turn in data["turns"]:
        turn["reasoning_withheld"] = True
    (writer.dir / "transcript.json").write_text(json.dumps(data), encoding="utf-8")

    parent = load_run_record(writer.dir)
    assert all(t.reasoning_withheld for t in parent.transcript.all_turns())


# --------------------------------------------------------------------------- #
# contesting a decision that was not a debate
#
# Every test above builds a *debate* parent, which is why the solo shape went
# unexercised: `load_run_record` puts a solo body in `.trace` and leaves
# `.transcript` empty, and the recourse path read only `.transcript`.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("arm", ["single", "self_critique"])
async def test_a_solo_decisions_record_reaches_its_challenger(
    tmp_path, task, seating, config, arm
):
    parent, _ = await recorded_solo_run(tmp_path, task, config, seating, arm=arm)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(
        parent_record, generated_challenge(visibility="public"), config, client,
        writer=writer,
    )

    body = json.dumps(
        next(c for c in client.calls if c["meta"]["role"] == "challenger")["messages"]
    )
    assert "The second choice follows from the constraint" in body, (
        "the agent's published reasoning is the record; without it the challenger "
        "is contesting a decision it has not been shown"
    )
    assert "no arguments have been made yet" not in body
    assert "argues for 1" not in body


async def test_a_public_visibility_challenger_is_not_shown_a_solo_agents_thinking(
    tmp_path, task, seating, config
):
    """The guard that would have caught sub-fault (c).

    A solo `Verdict.raw` is the whole completion, private `Thinking:` included.
    Passed as the decision's grounds it reached the challenger through the
    `<decision>` block even at public visibility, while
    `Challenge.shown_private_reasoning` went on reporting False.
    """
    parent, _ = await recorded_solo_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    result = await run_recourse(
        parent_record, generated_challenge(visibility="public"), config, client,
        writer=writer,
    )

    challenger_call = next(c for c in client.calls if c["meta"]["role"] == "challenger")
    assert SOLO_THINKING not in json.dumps(challenger_call["messages"])
    assert result.challenge.shown_private_reasoning is False


async def test_a_full_visibility_challenger_is_shown_a_solo_agents_thinking(
    tmp_path, task, seating, config
):
    parent, _ = await recorded_solo_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(
        parent_record, generated_challenge(visibility="full"), config, client,
        writer=writer,
    )

    challenger_call = next(c for c in client.calls if c["meta"]["role"] == "challenger")
    assert SOLO_THINKING in json.dumps(challenger_call["messages"])


async def test_the_recourse_judge_never_sees_a_solo_agents_thinking(
    tmp_path, task, seating, config
):
    parent, _ = await recorded_solo_run(tmp_path, task, config, seating)
    parent_record = load_run_record(parent.dir)
    writer = make_recourse_writer(tmp_path, parent_record, config)
    client = FakeClient(sink=writer.record_call, scripted={"recourse_judge": UPHOLD})
    await run_recourse(parent_record, file_challenge(), config, client, writer=writer)

    body = json.dumps(
        next(c for c in client.calls if c["meta"]["role"] == "recourse_judge")["messages"]
    )
    assert SOLO_THINKING not in body
    assert "Thinking:" not in body
