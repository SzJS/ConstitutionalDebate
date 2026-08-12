"""Recourse orchestration: the ruling, the record, and what the audit catches.

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
    file_challenge,
    generated_challenge,
    load_verifier,
    make_recourse_writer,
    make_writer,
    recorded_recourse,
    recorded_run,
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


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("recourse_rounds", [0, 1, 2])
@pytest.mark.parametrize("with_constitution", [False, True])
async def test_a_clean_recourse_passes_the_audit(
    tmp_path, task, seating, make_config, recourse_rounds, with_constitution
):
    """One audit over the recourse directory must verify the whole affair."""
    config = make_config(recourse_rounds=recourse_rounds)
    context = CONSTITUTION if with_constitution else None
    parent, _ = await parent_run(tmp_path, task, config, seating, context)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, config=config, scripted={"recourse_judge": UPHOLD}
    )

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures == [], failures
    # As for a debate: for a record this code wrote, the auditor's re-render must
    # reproduce every artifact exactly. A note means the two have drifted.
    assert notes == [], notes


@pytest.mark.parametrize("arm", ["grounded", "specious", "neutral"])
async def test_a_clean_generated_recourse_passes_the_audit(
    tmp_path, task, seating, config, arm
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(arm=arm),
        scripted={"recourse_judge": UPHOLD},
    )

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert notes == [], notes


async def test_full_visibility_passes_but_is_disclosed_not_hidden(
    tmp_path, task, seating, config
):
    """A recorded configuration, not tampering — and still a departure.

    The generator saw what a reader can now see, so it is no longer a secrecy
    problem. What remains is that the recourse judge can be shown, through the
    challenge, reasoning the deciding judge never had.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(visibility="full"),
        scripted={"recourse_judge": UPHOLD},
    )

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert any("DISCLOSURE" in n for n in notes), notes
    assert any("exempt from the containment scan" in n for n in notes), notes
    # The challenge is published like any other.
    published = (writer.dir / "transcript.md").read_text()
    assert "## The challenge" in published


async def test_the_audit_catches_an_edited_challenge(tmp_path, task, seating, config):
    """The challenge is what the recourse prompts were built from."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    (writer.dir / "challenge.md").write_text("a challenge nobody actually filed\n")
    failures = load_verifier().verify(writer.dir)
    assert any("did not carry the challenge" in f for f in failures), failures


async def test_the_audit_catches_a_ruling_that_does_not_follow(
    tmp_path, task, seating, config
):
    """The decisive new check: the answer must follow from the ruling."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    ruling = read(writer, "ruling.json")
    ruling["answer_index"] = 1 - ruling["answer_index"]
    (writer.dir / "ruling.json").write_text(json.dumps(ruling, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("does not follow from a UPHOLD" in f for f in failures), failures


async def test_the_audit_catches_a_consistently_inverted_ruling(
    tmp_path, task, seating, config
):
    """Flipping the ruling and the index together stays self-consistent — and is
    still caught, because the judge's recorded response is what decided it."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    ruling = read(writer, "ruling.json")
    ruling["ruling"] = "OVERTURN"
    ruling["upheld"] = False
    ruling["answer_index"] = 1 - ruling["answer_index"]
    ruling["choice"] = 3 - ruling["choice"]
    (writer.dir / "ruling.json").write_text(json.dumps(ruling, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("is not what the recourse judge's recorded response" in f for f in failures)


async def test_the_audit_catches_a_tampered_parent(tmp_path, task, seating, config):
    """Editing the copied decision must be caught, and more than once."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    verdict_path = writer.dir / "parent" / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    verdict["choice"] = 3 - verdict["choice"]
    verdict["answer_index"] = 1 - verdict["answer_index"]
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("parent_sha256" in f for f in failures), failures
    assert any(f.startswith("parent:") for f in failures), failures


async def test_the_audit_reports_a_missing_parent_cleanly(
    tmp_path, task, seating, config
):
    import shutil

    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )
    shutil.rmtree(writer.dir / "parent")

    failures = load_verifier().verify(writer.dir)
    assert failures and "parent/ is missing" in failures[0]


async def test_the_audit_catches_a_challenge_claiming_a_provenance_it_lacks(
    tmp_path, task, seating, config
):
    """"Supplied" must mean supplied: a secretly generated one is a false claim."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(),
        scripted={"recourse_judge": UPHOLD},
    )

    challenge = read(writer, "challenge.json")
    challenge["origin"] = "file"
    challenge["source"] = "challenge.md"
    (writer.dir / "challenge.json").write_text(json.dumps(challenge, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("recorded as supplied" in f for f in failures), failures


async def test_a_rewritten_arm_is_not_caught_and_the_audit_says_so(
    tmp_path, task, seating, config
):
    """An accepted limitation, pinned so nobody assumes otherwise.

    Which arm produced a generated challenge is recorded and not checked, so
    editing challenge.json and run.json in step passes. It is the one thing the
    contestability claim would most like pinned, and the audit's docstring says
    plainly that it is not. This keeps that statement true rather than letting
    it quietly become false.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent,
        challenge=generated_challenge(arm="specious", visibility="public"),
        scripted={"recourse_judge": UPHOLD},
    )

    for name in ("challenge.json", "run.json"):
        data = read(writer, name)
        data["arm" if name == "challenge.json" else "challenge_arm"] = "grounded"
        (writer.dir / name).write_text(json.dumps(data, indent=2))

    assert load_verifier().verify(writer.dir) == []


async def test_the_audit_catches_a_protocol_that_does_not_match_its_round_count(
    tmp_path, task, seating, config
):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    manifest = read(writer, "run.json")
    manifest["recourse_protocol"] = "judge_only"
    (writer.dir / "run.json").write_text(json.dumps(manifest, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("names the 'judge_only' protocol" in f for f in failures), failures


async def test_the_audit_catches_a_reseated_recourse(tmp_path, task, seating, config):
    """Reseating would contest a different decision from the one copied in."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    data = read(writer, "seating.json")
    data["choice_order"] = list(reversed(data["choice_order"]))
    (writer.dir / "seating.json").write_text(json.dumps(data, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("seating.json differs from the parent's" in f for f in failures), failures


async def test_the_audit_notices_a_recourse_run_under_different_settings(
    tmp_path, task, seating, config, make_config
):
    """A different judge model is legitimate, and material — so: a note."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, config=make_config(judge_model="another/model"),
        scripted={"recourse_judge": UPHOLD},
    )

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert any("different settings" in n and "judge_model" in n for n in notes), notes


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("challenge_arm", "grounded", "challenge_arm"),
        ("challenge_source", "somewhere/else.md", "challenge_source"),
        ("challenge_origin", "file", "challenge_origin"),
        ("challenge_visibility", "full", "challenge_visibility"),
        ("parent_rounds", 99, "parent_rounds"),
        ("parent_chain", ["someone-else"], "parent_chain"),
    ],
)
async def test_the_audit_catches_an_edited_manifest_claim(
    tmp_path, task, seating, config, field, value, message
):
    """The summary this script prints under OK is written from run.json.

    Unchecked, an edited manifest would have the audit itself report a specious
    challenge as a grounded one — the arm the whole claim turns on.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(arm="specious"),
        scripted={"recourse_judge": UPHOLD},
    )

    manifest = read(writer, "run.json")
    manifest[field] = value
    (writer.dir / "run.json").write_text(json.dumps(manifest, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any(message in f for f in failures), failures


async def test_a_deleted_ruling_is_reported_rather_than_crashing(
    tmp_path, task, seating, config
):
    """The cheapest way to make an outcome unreadable must produce a finding."""
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )
    (writer.dir / "ruling.json").unlink()

    failures = load_verifier().verify(writer.dir)
    assert any("missing" in f and "ruling.json" in f for f in failures), failures


async def test_a_smuggled_field_in_the_ruling_is_caught(tmp_path, task, seating, config):
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, scripted={"recourse_judge": UPHOLD}
    )

    ruling = read(writer, "ruling.json")
    ruling["unanimous"] = True  # a field a reader would believe
    (writer.dir / "ruling.json").write_text(json.dumps(ruling, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("ruling.json's keys" in f for f in failures), failures


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


async def test_the_containment_exemption_cannot_be_repointed_at_another_call(
    tmp_path, task, seating, config
):
    """Only a challenger call may be exempted from the containment scan.

    A challenge.json whose call_id points at the recourse judge would otherwise
    exempt the judge's request — the one prompt that most needs scanning.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(visibility="full"),
        scripted={"recourse_judge": UPHOLD},
    )

    ruling_call_id = read(writer, "ruling.json")["call_id"]
    challenge = read(writer, "challenge.json")
    challenge["call_id"] = ruling_call_id
    (writer.dir / "challenge.json").write_text(json.dumps(challenge, indent=2))

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures, "a repointed call_id must not buy an exemption silently"
    # The exemption is not granted, so the challenger's own request is scanned
    # like any other and its private reasoning is reported.
    assert any("private Thinking" in f for f in failures), failures


async def test_a_challenge_quoting_private_reasoning_is_disclosed(
    tmp_path, task, seating, config
):
    """The disclosure that the two decisions are incomparable must actually fire.

    A full-visibility generator reads the debaters' reasoning through the
    transcript renderer, so a verbatim quote arrives *indented*. Matching the
    raw string would silence this in exactly the case it exists for — and the
    containment scan stays deliberately quiet here, because the challenge text
    is stripped from every request before scanning.
    """
    from constitutional_debate.types import indent_continuations

    parent, parent_result = await parent_run(tmp_path, task, config, seating)
    stolen = parent_result.transcript.all_turns()[0].thinking
    assert "\n" in stolen, "the fixture must be multi-line or this proves nothing"

    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(visibility="full"),
        scripted={
            "recourse_judge": UPHOLD,
            # As the generator would have read it: through the renderer.
            "challenger": (
                "Thinking: the private reasoning gives me the opening.\n\n"
                f"Argument: Alice privately conceded: {indent_continuations(stolen)}"
            ),
        },
    )

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures == [], failures
    assert any(
        "the challenge quotes round 1" in n and "not comparable" in n for n in notes
    ), notes


async def test_a_public_visibility_challenge_quoting_thinking_is_a_failure(
    tmp_path, task, seating, config
):
    """Under the default visibility the same text is not a disclosure but a lie:
    the record claims the generator was never shown it."""
    from constitutional_debate.types import indent_continuations

    parent, parent_result = await parent_run(tmp_path, task, config, seating)
    stolen = parent_result.transcript.all_turns()[0].thinking

    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(visibility="public"),
        scripted={
            "recourse_judge": UPHOLD,
            "challenger": (
                "Thinking: I should not have been able to see this.\n\n"
                f"Argument: Alice privately conceded: {indent_continuations(stolen)}"
            ),
        },
    )

    failures = load_verifier().verify(writer.dir)
    assert any("private Thinking" in f for f in failures), failures


async def test_a_consistently_edited_challenge_is_still_caught(
    tmp_path, task, seating, config
):
    """challenge.md, challenge.json and the manifest sha all restate one text.

    They can be edited together and still agree with each other, so the only
    thing that can contradict them is the requests the judge and debaters
    actually received. Without that scan the record could publish a challenge
    nobody was asked to answer.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=file_challenge("The original objection."),
        scripted={"recourse_judge": UPHOLD},
    )

    import hashlib

    forged = "An objection nobody was asked to answer."
    (writer.dir / "challenge.md").write_text(forged + "\n")
    challenge = read(writer, "challenge.json")
    challenge["text"] = forged
    (writer.dir / "challenge.json").write_text(json.dumps(challenge, indent=2))
    manifest = read(writer, "run.json")
    manifest["challenge_sha256"] = hashlib.sha256(forged.encode()).hexdigest()
    (writer.dir / "run.json").write_text(json.dumps(manifest, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("did not carry the challenge" in f for f in failures), failures


@pytest.mark.parametrize(
    "recorded,actual", [("full", "public"), ("public", "full")]
)
async def test_the_recorded_visibility_must_match_the_request(
    tmp_path, task, seating, config, recorded, actual
):
    """The exemption from the containment scan is earned, not self-granted.

    A record that could declare itself `full` would excuse its own challenger
    call from the scan, silencing a real leak. So the declaration is checked
    against whether the request actually carried the private-reasoning block.
    """
    parent, _ = await parent_run(tmp_path, task, config, seating)
    writer, _, _ = await recorded_recourse(
        tmp_path, parent, challenge=generated_challenge(visibility=actual),
        scripted={"recourse_judge": UPHOLD},
    )

    challenge = read(writer, "challenge.json")
    challenge["visibility"] = recorded
    (writer.dir / "challenge.json").write_text(json.dumps(challenge, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("recorded request carries" in f or "carries no private" in f for f in failures), failures
