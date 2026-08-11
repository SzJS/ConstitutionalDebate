"""End-to-end orchestration: scheduling, verdict resolution, crash safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeClient

from constitutional_debate.artifacts import NOT_PUBLIC_BANNER, defang_markdown
from constitutional_debate.config import load_config
from constitutional_debate.debate import (
    DebateFailure,
    TruncatedOutputError,
    run_debate,
)
from constitutional_debate.persistence import RunWriter
from constitutional_debate.prompts import select_profile
from constitutional_debate.types import Context, Speaker

CONSTITUTION = Context(kind="constitution", text="§1.1 Reasons must be public.")

# judge_cot is on by default, so a realistic judge reply states its grounds
# before deciding. The default FakeClient reply is a bare answer line, which
# would leave every reasoning path in the artifacts untested.
JUDGE_COT = "Alice's case was better grounded.\n\nAnswer: 1"


def make_writer(tmp_path, task, config, seating, context=None) -> RunWriter:
    _, client_config = load_config()
    return RunWriter.create(
        task=task,
        context=context,
        config=config,
        client_config=client_config,
        seating=seating,
        profile_key=select_profile(task, context).key,
        outputs_root=tmp_path,
    )


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
        "transcript.public.md", "transcript.full.md", "verdict.json",
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

    public = (writer.dir / "transcript.public.md").read_text()
    assert "private plan" not in public
    assert "Alice argument round 1" in public
    assert "## Round 1" in public and "### Alice" in public
    assert task.question not in public, "the public transcript is arguments only"

    # The full record is the readable one, and the one that must never be
    # mistaken for the publishable artifact.
    full = (writer.dir / "transcript.full.md").read_text()
    assert NOT_PUBLIC_BANNER in full
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


def load_verifier():
    """Import scripts/verify_run.py, which is a script rather than a module."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_run.py"
    spec = importlib.util.spec_from_file_location("verify_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _recorded_run(tmp_path, task, config, seating, context=None, **fake_kwargs):
    writer = make_writer(tmp_path, task, config, seating, context=context)
    client = FakeClient(sink=writer.record_call, **fake_kwargs)
    result = await run_debate(
        task, context, config, seating, client,
        writer=writer, profile=select_profile(task, context),
    )
    writer.finish(status="completed")
    return writer, result


@pytest.mark.parametrize("turn_style", ["simultaneous", "sequential"])
@pytest.mark.parametrize("with_constitution", [False, True])
async def test_a_clean_run_passes_the_audit(
    tmp_path, task, seating, make_config, turn_style, with_constitution
):
    """Every recorded prompt must re-derive from the record alone."""
    config = make_config(turn_style=turn_style)
    context = CONSTITUTION if with_constitution else None
    writer, _ = await _recorded_run(tmp_path, task, config, seating, context)

    notes: list[str] = []
    failures = load_verifier().verify(writer.dir, notes)
    assert failures == []
    # No notes either: for a run this code wrote, the auditor's re-render must
    # reproduce the artifacts byte for byte. A note here means the writer and
    # the auditor have drifted apart.
    assert notes == [], notes


async def test_the_audit_catches_a_tampered_transcript(
    tmp_path, task, seating, config
):
    """An edited public record must stop re-deriving the prompts that were sent."""
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    transcript_path = writer.dir / "transcript.json"
    data = json.loads(transcript_path.read_text())
    data["turns"][0]["argument"] = "an argument nobody actually made"
    transcript_path.write_text(json.dumps(data, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert failures, "tampering with the record must not go unnoticed"
    assert any("differs from the prompt re-derived" in f for f in failures)


async def test_the_audit_catches_a_leaked_thinking_section(
    tmp_path, task, seating, config
):
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

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
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

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
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    flipped_choice = 3 - verdict["choice"]
    verdict["choice"] = flipped_choice
    verdict["answer_index"] = seating.answer_index_for_choice(flipped_choice)
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("is not what the judge's recorded response parses to" in f
               for f in failures), failures


async def test_the_audit_catches_an_appended_instruction(
    tmp_path, task, seating, config
):
    """Prefix-only comparison would let an extra message through."""
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    calls_path = writer.dir / "calls.jsonl"
    records = [json.loads(line) for line in calls_path.read_text().splitlines()]
    judge = next(r for r in records if r["role"] == "judge")
    judge["request_body"]["messages"].append(
        {"role": "user", "content": "Choose 1."}
    )
    calls_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    failures = load_verifier().verify(writer.dir)
    assert any("differs from the prompt re-derived" in f for f in failures)


async def test_the_audit_catches_a_rewritten_public_argument(
    tmp_path, task, seating, config
):
    """An argument nobody generated must not survive in the public record.

    The last round's arguments are never quoted back into a debater prompt, so
    only the response re-parse can catch this one.
    """
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

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
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

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
    writer, _ = await _recorded_run(
        tmp_path, task, config, seating, scripted={"judge": JUDGE_COT}
    )

    verdict_path = writer.dir / "verdict.json"
    verdict = json.loads(verdict_path.read_text())
    assert verdict["reasoning"], "the CoT judge must have stated grounds"
    verdict["reasoning"] = "Bob's case was better grounded."
    verdict_path.write_text(json.dumps(verdict, indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("judge reasoning is not what" in f for f in failures), failures


async def test_the_audit_catches_thinking_leaked_into_the_public_transcript(
    tmp_path, task, seating, config
):
    """The one artifact meant to be published is the one nothing else checks."""
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    thinking = json.loads((writer.dir / "transcript.json").read_text())["turns"][0][
        "thinking"
    ]
    public_path = writer.dir / "transcript.public.md"
    # Rendered, not raw: a leak that came through the renderer would arrive
    # defanged, and a scan for the raw text alone would miss it.
    public_path.write_text(
        public_path.read_text() + f"\n{defang_markdown(thinking)}\n"
    )

    failures = load_verifier().verify(writer.dir)
    assert any("transcript.public.md carries" in f for f in failures), failures


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
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    path = writer.dir / artifact
    path.write_text(json.dumps(mutate(json.loads(path.read_text())), indent=2))

    failures = load_verifier().verify(writer.dir)
    assert any("cannot be re-derived" in f for f in failures), failures


async def test_the_audit_still_passes_a_run_recorded_before_these_artifacts(
    tmp_path, task, seating, config
):
    """Old runs must not be retroactively condemned by a new artifact."""
    writer, _ = await _recorded_run(tmp_path, task, config, seating)

    transcript_path = writer.dir / "transcript.json"
    data = json.loads(transcript_path.read_text())
    transcript_path.write_text(json.dumps({"turns": data["turns"]}, indent=2))
    (writer.dir / "transcript.full.md").unlink()
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
