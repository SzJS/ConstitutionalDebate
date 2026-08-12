"""Builders shared by more than one test module.

Plain functions rather than fixtures because callers need to vary their
arguments — a fixture cannot be asked for "a seating with the other choice
order" inside a parametrised test.
"""

from __future__ import annotations

from constitutional_debate.config import DebateConfig, load_config
from constitutional_debate.debate import run_debate, run_recourse
from constitutional_debate.persistence import RunWriter, load_run_record
from constitutional_debate.prompts import select_profile
from constitutional_debate.types import (
    ORDER,
    Challenge,
    Context,
    Seating,
    Speaker,
    Task,
    Transcript,
    Turn,
)

CONSTITUTION_TEXT = (
    "§1.1 A decision must be justified by reasons available to those it binds.\n"
    "§2.3 Weigh burdens on those least able to avoid them more heavily."
)

CONSTITUTION = Context(kind="constitution", text="§1.1 Reasons must be public.")

# judge_cot is on by default, so a realistic judge reply states its grounds
# before deciding. The default FakeClient reply is a bare answer line, which
# would leave every reasoning path in the artifacts untested.
JUDGE_COT = "Alice's case was better grounded.\n\nAnswer: 1"


def make_task(gold_index: int | None = None) -> Task:
    return Task(
        task_id="t1",
        question="Is it OK to use tax havens?",
        answers=("It is OK to use tax havens.", "It is NOT OK to use tax havens."),
        gold_index=gold_index,
    )


def make_seating(choice_order: tuple[int, int] = (0, 1)) -> Seating:
    return Seating(
        alice_answer=0, bob_answer=1, choice_order=choice_order, seed_material="fixed"
    )


def config(**kwargs) -> DebateConfig:
    debate, _ = load_config()
    return DebateConfig(**{**debate.to_dict(), **kwargs})


def make_turn(round: int, speaker: Speaker) -> Turn:
    return Turn(
        round=round,
        speaker=speaker,
        answer_index=0 if speaker is Speaker.ALICE else 1,
        thinking=f"SECRET-THINKING-{speaker}-r{round}",
        argument=f"{speaker} public argument r{round}",
        word_count=4,
        parse_mode="strict",
        repair_attempts=0,
        finish_reason="stop",
        has_native_reasoning=False,
        call_id=f"c{round}{speaker}",
        raw="",
    )


def full_transcript(n_rounds: int = 3) -> Transcript:
    transcript = Transcript()
    for round_number in range(1, n_rounds + 1):
        for speaker in ORDER:
            transcript.add(make_turn(round_number, speaker))
    return transcript


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


async def recorded_run(tmp_path, task, config, seating, context=None, **fake_kwargs):
    """Run one debate to a completed record on disk, and hand back the writer."""
    from conftest import FakeClient

    writer = make_writer(tmp_path, task, config, seating, context=context)
    client = FakeClient(sink=writer.record_call, **fake_kwargs)
    result = await run_debate(
        task, context, config, seating, client,
        writer=writer, profile=select_profile(task, context),
    )
    writer.finish(status="completed")
    return writer, result


def file_challenge(text: str = "The decision rests on an unsupported figure.") -> Challenge:
    return Challenge(text=text, origin="file", source="challenge.md")


def generated_challenge(arm: str = "grounded", visibility: str = "public") -> Challenge:
    """The *specification* of a challenge to generate; the run fills in the text."""
    return Challenge(text="", origin="generated", arm=arm, visibility=visibility)


def make_recourse_writer(tmp_path, parent, config=None) -> RunWriter:
    _, client_config = load_config()
    return RunWriter.create_recourse(
        parent=parent,
        config=config or parent.config,
        client_config=client_config,
        outputs_root=tmp_path,
    )


async def recorded_recourse(
    tmp_path, parent_writer, *, challenge=None, config=None, **fake_kwargs
):
    """Contest a completed run, to a completed recourse record on disk.

    Returns ``(writer, result, client)`` — the client too, because several
    properties worth asserting (who was shown what) live in the requests rather
    than in the record.
    """
    from conftest import FakeClient

    parent = load_run_record(parent_writer.dir)
    config = config or parent.config
    writer = make_recourse_writer(tmp_path, parent, config)
    client = FakeClient(sink=writer.record_call, **fake_kwargs)
    result = await run_recourse(
        parent, challenge or file_challenge(), config, client, writer=writer
    )
    writer.finish(status="completed")
    return writer, result, client
