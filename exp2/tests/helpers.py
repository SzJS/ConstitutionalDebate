"""Builders for tests. Plain functions rather than fixtures, so a test can vary one
thing without inheriting a fixture chain."""

from __future__ import annotations

from exp2.config import DebateConfig
from exp2.types import FLAWED, SOUND, Item, Sides, Speaker, Transcript, Turn


def make_config(**kw) -> DebateConfig:
    base = dict(
        debater_model="strong/model", judge_model="weak/model", n_rounds=3,
        turn_style="simultaneous", word_limit=400, debater_temperature=0.7,
        judge_temperature=0.0, max_tokens=8192, reasoning_effort="off",
        judge_cot=True, seed=0, n_critique_rounds=3,
    )
    base.update(kw)
    return DebateConfig(**base)


def make_item(**kw) -> Item:
    base = dict(
        item_id="theoremqa-p1-flawed", row_id="theoremqa:p1", subset="theoremqa",
        problem="What is the third Catalan number?",
        solution="Step 1: apply the formula.\nStep 2: C_3 = 6.",
        gold_flawed=True,
    )
    base.update(kw)
    return Item(**base)


def make_sides(**kw) -> Sides:
    base = dict(alice_side=FLAWED, bob_side=SOUND, verdict_order=(FLAWED, SOUND),
                seed_material="0:theoremqa-p1-flawed")
    base.update(kw)
    return Sides(**base)


# A distinctive needle, so a leak assertion cannot pass by accident.
SECRET_THINKING = "SECRET-THINKING-must-never-be-published"


def make_turn(round_number: int, speaker: Speaker, side: str, **kw) -> Turn:
    base = dict(
        round=round_number, speaker=speaker, side=side,
        thinking=f"{SECRET_THINKING}-{speaker.value}-{round_number}",
        argument=f"{speaker.value} round {round_number} argument.",
        word_count=5, parse_mode="strict", repair_attempts=0, finish_reason="stop",
        has_native_reasoning=False, call_id=f"c-{speaker.value}-{round_number}",
        raw="raw",
    )
    base.update(kw)
    return Turn(**base)


def full_transcript(sides: Sides, n_rounds: int = 3) -> Transcript:
    transcript = Transcript()
    for round_number in range(1, n_rounds + 1):
        for speaker in (Speaker.ALICE, Speaker.BOB):
            transcript.add(make_turn(round_number, speaker, sides.side_for(speaker)))
    return transcript
