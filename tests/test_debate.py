"""End-to-end orchestration: scheduling, verdict resolution, crash safety."""

from __future__ import annotations

import json

import pytest

from conftest import FakeClient
from helpers import (
    CONSTITUTION,
    JUDGE_COT,
    load_verifier,
    make_writer,
    recorded_run,
)

from constitutional_debate.artifacts import PRIVATE_THINKING_NOTE
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


async def test_run_directory_is_complete_and_audit_ready(
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


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #




@pytest.mark.parametrize("turn_style", ["simultaneous", "sequential"])
@pytest.mark.parametrize("with_constitution", [False, True])
async def test_a_clean_run_passes_the_audit(
    tmp_path, task, seating, make_config, turn_style, with_constitution
):
    """A clean record must pass, with nothing to note.

    `notes == []` is the load-bearing half: for a record this code wrote, the
    auditor's re-render must reproduce every artifact exactly. A note means the
    writer and the auditor have drifted apart.
    """
    config = make_config(turn_style=turn_style)
    context = CONSTITUTION if with_constitution else None
    writer, _ = await recorded_run(tmp_path, task, config, seating, context)

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures == []
    assert notes == [], notes


async def test_the_audit_catches_a_leaked_thinking_section(
    tmp_path, task, seating, config
):
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    calls_path = writer.dir / "calls.jsonl"
    records = [json.loads(line) for line in calls_path.read_text().splitlines()]
    leaked = json.loads((writer.dir / "transcript.json").read_text())["turns"][0][
        "thinking"
    ]
    judge = next(r for r in records if r["role"] == "judge")
    judge["request_body"]["messages"][1]["content"] += f"\n\n{leaked}"
    calls_path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n"
    )

    failures = load_verifier().verify(writer.dir)
    assert any("private Thinking" in f for f in failures)


async def test_the_audit_catches_an_inconsistent_verdict(
    tmp_path, task, seating, config
):
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    verdict["answer_index"] = 1 - verdict["answer_index"]
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("does not resolve to answer" in f for f in failures)


async def test_the_audit_catches_a_self_consistent_inverted_verdict(
    tmp_path, task, seating, config
):
    """The hard case: flip choice AND answer_index so seating still agrees.

    Checking the verdict only against the seating is circular — it would pass.
    The judge's recorded response is what actually decided the question.
    """
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    flipped_choice = 3 - verdict["choice"]
    verdict["choice"] = flipped_choice
    verdict["answer_index"] = seating.answer_index_for_choice(flipped_choice)
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("is not what the judge's recorded response parses to" in f
               for f in failures), failures


async def test_the_audit_catches_a_rewritten_public_argument(
    tmp_path, task, seating, config
):
    """An argument nobody generated must not survive in the published record.

    A tampered `transcript.json` is internally consistent, so the recorded
    response is the only thing that can contradict it.
    """
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    transcript_path = writer.dir / "transcript.json"
    data = json.loads(transcript_path.read_text())
    data["turns"][-1]["argument"] = "a far more persuasive closing nobody made"
    transcript_path.write_text(json.dumps(data, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("not what the recorded response parses to" in f for f in failures)


async def test_the_audit_catches_a_tampered_transcript_header(
    tmp_path, task, seating, config
):
    """The question a decision answers is part of what the record must fix."""
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    transcript_path = writer.dir / "transcript.json"
    data = json.loads(transcript_path.read_text())
    data["question"] = "a question nobody was asked"
    transcript_path.write_text(json.dumps(data, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("question disagrees with task.json" in f for f in failures), failures


async def test_the_audit_catches_tampered_judge_reasoning(
    tmp_path, task, seating, config
):
    """Published grounds must be the judge's, not the last editor's."""
    writer, _ = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    assert verdict["reasoning"], "the CoT judge must have stated grounds"
    verdict["reasoning"] = "Bob's case was better grounded."
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("judge reasoning is not what" in f for f in failures), failures


@pytest.mark.parametrize(
    "artifact,mutate",
    [
        ("verdict.json", lambda d: {**d, "answer_index": 7}),
        ("seating.json", lambda d: {**d, "choice_order": [1, 1]}),
    ],
)
async def test_the_audit_reports_an_unrederivable_artifact_rather_than_crashing(
    tmp_path, task, seating, config, artifact, mutate
):
    """On-disk integers become list indices. A doctored one is a finding.

    A traceback here would be the worst outcome: the audit falls over at the
    one moment it has something to say about the record.
    """
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    path = writer.dir / artifact
    path.write_text(json.dumps(mutate(json.loads(path.read_text())), indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("cannot be re-derived" in f for f in failures), failures


async def test_the_audit_still_passes_a_run_recorded_before_these_artifacts(
    tmp_path, task, seating, config
):
    """Old runs must not be retroactively condemned by a new artifact."""
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    transcript_path = writer.dir / "transcript.json"
    data = json.loads(transcript_path.read_text())
    transcript_path.write_text(json.dumps({"turns": data["turns"]}, indent=2))
    (writer.dir / "transcript.md").unlink()
    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    del verdict["reasoning"]
    verdict_path.write_text(json.dumps(verdict, indent=2))

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures == [], failures
    assert any("predates" in note for note in notes), notes


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


async def test_the_audit_catches_thinking_that_leaked_through_the_renderer(
    tmp_path, task, seating, config
):
    """A leak does not arrive as the raw string.

    Everything that interpolates a turn into a prompt indents its continuation
    lines, and real Thinking is multi-line, so a containment scan that searched
    only for `turn.thinking` would be near-vacuous against the failure it exists
    to catch: a renderer emitting Thinking alongside Argument.
    """
    from constitutional_debate.types import indent_continuations

    writer, result = await recorded_run(tmp_path, task, config, seating)

    leaked = next(t for t in result.transcript.all_turns() if t.round == 1)
    assert "\n" in leaked.thinking, "the fixture must be multi-line or this proves nothing"

    calls_path = writer.dir / "calls.jsonl"
    records = [json.loads(line) for line in calls_path.read_text().splitlines()]
    judge = next(r for r in records if r.get("role") == "judge")
    # As a renderer would have produced it, not as it is stored.
    judge["request_body"]["messages"][1]["content"] += (
        f"\n  {leaked.speaker}: {indent_continuations(leaked.thinking)}"
    )
    calls_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    failures = load_verifier().verify(writer.dir)
    assert any("private Thinking" in f for f in failures), failures


async def test_a_record_in_the_old_two_document_shape_still_verifies(
    tmp_path, task, seating, config
):
    """Records written before `transcript.md` must not be condemned by it.

    They cannot be migrated either: a recourse hashes every byte of the run it
    copied, so renaming a file inside `parent/` would break that seal. The old
    documents are therefore inert — tolerated, unchecked, and reported as such.
    """
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    document = writer.dir / "transcript.md"
    (writer.dir / "transcript.full.md").write_text(document.read_text())
    (writer.dir / "transcript.public.md").write_text("# Public transcript\n")
    document.unlink()

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert any("predates transcript.md" in note for note in notes), notes


async def test_the_audit_catches_a_published_document_naming_the_wrong_winner(
    tmp_path, task, seating, config
):
    """Presentation may drift; the decisive statements may not.

    A re-render mismatch is only a note, so without this floor a published
    document could name the losing answer and the audit would shrug. The edit
    below touches only the Decision section — a document-wide search-and-replace
    would also rewrite the Answers list and pass for the wrong reason.
    """
    writer, result = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    document = writer.dir / "transcript.md"
    won, lost = result.verdict.answer_index, 1 - result.verdict.answer_index
    text = document.read_text()
    head, decision = text.split("## Decision", 1)
    document.write_text(
        head + "## Decision" + decision.replace(f"answers[{won}]", f"answers[{lost}]")
    )

    failures = load_verifier().verify(writer.dir)
    assert any("which answer the judge chose" in f for f in failures), failures


async def test_the_audit_catches_a_rewritten_argument_in_the_published_document(
    tmp_path, task, seating, config
):
    """The arguments are what determined the decision, so they are pinned too."""
    writer, result = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    document = writer.dir / "transcript.md"
    argument = result.transcript.all_turns()[0].argument
    document.write_text(
        document.read_text().replace(argument, "something Alice never said")
    )

    failures = load_verifier().verify(writer.dir)
    assert any("argument" in f and "does not state" in f for f in failures), failures


async def test_a_reformatted_document_is_a_note_not_a_failure(
    tmp_path, task, seating, config
):
    """The other half of the same rule: headings are presentation."""
    writer, _ = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    document = writer.dir / "transcript.md"
    document.write_text(document.read_text().replace("## Round 1", "## Opening round"))

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert any("presentation has drifted" in note for note in notes), notes


async def test_a_smuggled_turn_field_cannot_hide_behind_the_old_record_branch(
    tmp_path, task, seating, config
):
    """Deleting the header used to disable the field-set pin along with it."""
    writer, _ = await recorded_run(tmp_path, task, config, seating)

    path = writer.dir / "transcript.json"
    document = json.loads(path.read_text())
    del document["positions"]
    for turn in document["turns"]:
        turn["gold_index"] = 1
    path.write_text(json.dumps(document, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert failures, "an edited document is not an old one"


async def test_a_discarded_generation_is_reported(tmp_path, task, seating, config):
    """Publishing the judge call you liked best must not be invisible."""
    writer, _ = await recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    calls_path = writer.dir / "calls.jsonl"
    records = [json.loads(line) for line in calls_path.read_text().splitlines()]
    discarded = dict(next(r for r in records if r.get("role") == "judge"))
    discarded["call_id"] = "a-call-nobody-published"
    calls_path.write_text(
        "\n".join(json.dumps(r) for r in [*records, discarded]) + "\n"
    )

    notes: list[str] = []
    assert load_verifier().verify(writer.dir, notes) == []
    assert any("does not account for" in note for note in notes), notes
