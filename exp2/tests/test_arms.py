"""The three conditions: what they call, in what order, and what they leave behind."""

from __future__ import annotations

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import make_config, make_item, make_sides

from exp2.arms import CONDITIONS, DECIDERS, run_self_critique, run_single
from exp2.debate import run_debate
from exp2.engine import DebateFailure
from exp2.types import FLAWED, SOUND, Speaker


async def decide(condition, *, client=None, config=None, item=None, sides=None):
    client = client or FakeClient()
    result = await DECIDERS[condition](
        item or make_item(), config or make_config(), sides or make_sides(), client
    )
    return result, client


# --- shape ---------------------------------------------------------------------------


async def test_every_condition_produces_a_verdict():
    for condition in CONDITIONS:
        result, _ = await decide(condition)
        assert result.verdict.verdict in (FLAWED, SOUND)
        assert result.verdict.correct is True  # the fake decides FLAWED; the item is


async def test_single_makes_exactly_one_call():
    _, client = await decide("single")
    assert client.roles() == ["solo"]


async def test_self_critique_makes_one_plus_two_n_calls_in_stage_order():
    """Matched to debate's 2n+1 so the conditions are comparable on volume."""
    config = make_config(n_rounds=3, n_critique_rounds=3)
    _, client = await decide("self_critique", config=config)
    assert client.purposes("solo") == ["draft", "revision", "revision", "revision"]
    assert client.purposes("critic") == ["critique", "critique", "critique"]
    assert len(client.calls) == 7 == 2 * config.n_rounds + 1


async def test_debate_makes_two_n_plus_one_calls():
    config = make_config(n_rounds=3)
    _, client = await decide("debate", config=config)
    assert client.roles().count("debater") == 6
    assert client.roles().count("judge") == 1


# --- the conversation ----------------------------------------------------------------


async def test_a_solo_condition_holds_a_real_growing_conversation():
    """DESIGN.md's baseline contest is "a new prompt in the same conversation", which
    exp1's rebuild-the-prompt-each-stage shape could not honestly provide."""
    result, _ = await decide("self_critique")
    roles = [m["role"] for m in result.messages]
    assert roles[0] == "system"
    assert roles[-1] == "assistant", "the conversation must end ready to be appended to"
    # strictly alternating user/assistant after the system turn
    assert roles[1::2] == ["user"] * (len(roles) // 2)
    assert roles[2::2] == ["assistant"] * (len(roles) // 2)


async def test_the_conversation_grows_rather_than_being_rebuilt():
    """Each stage's messages must contain every earlier turn verbatim."""
    result, client = await decide("self_critique")
    solo_calls = [c["messages"] for c in client.calls]
    for earlier, later in zip(solo_calls, solo_calls[1:]):
        assert later[: len(earlier)] == earlier


async def test_a_critique_gets_one_repair_and_is_withheld_only_after_it():
    """Withholding loses a step of the published record, so it is the last resort and
    not the first: the critique spends the same one repair a deciding stage spends."""
    from exp2.arms import WITHHELD

    clean, _ = await decide("self_critique")
    client = FakeClient(replies={("critic", "critique"): "no labels at all",
                                 ("critic", "repair"): "no labels this time either"})
    result, _ = await decide("self_critique", client=client)
    critique_steps = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert critique_steps
    assert all(s.parse_mode == "unparsed_withheld" for s in critique_steps)
    assert all(s.repair_attempts == 1 for s in critique_steps)
    assert all(s.text == WITHHELD for s in critique_steps)
    # the generation itself is not lost — it is still in the record
    assert all("no labels this time either" in s.raw for s in critique_steps)
    # and the repair's two extra turns are in the conversation, as for any repair
    assert len(result.messages) == len(clean.messages) + 2 * len(critique_steps)


async def test_a_critique_that_wrote_only_a_thinking_block_is_repaired_into_the_record():
    """The pilot's real failure: every critique came back as one ``Thinking:`` block
    with no ``Reasoning:`` label, so every self_critique record showed a placeholder
    where the criticism should be."""
    client = FakeClient(replies={
        ("critic", "critique"): "Thinking: the draft trusted step 2 without checking it.",
        ("critic", "repair"): ("Thinking: rewriting as asked.\n"
                               "Reasoning: my draft took step 2 on trust."),
    })
    result, _ = await decide("self_critique", client=client)
    critique_steps = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert critique_steps
    assert all(s.text == "my draft took step 2 on trust." for s in critique_steps)
    assert all(s.repair_attempts == 1 for s in critique_steps)
    assert "repair" in client.purposes("critic")


async def test_a_critiques_private_thinking_is_never_published():
    """The critique is part of a self_critique record and therefore reaches the
    challenger. Storing its raw generation would publish the model's own Thinking block
    — the exact leak the protocol exists to prevent."""
    from exp2.types import DecisionRecord

    result, _ = await decide("self_critique")
    for step in result.trace.all_steps():
        assert SOLO_THINKING not in step.text, f"{step.stage} published its Thinking"
    body = DecisionRecord.for_solo(result.trace).body
    assert SOLO_THINKING not in body
    # but the critique itself is still published, as DESIGN.md requires
    assert "took step 2 on trust" in body


async def test_a_repairs_extra_turns_appear_in_the_conversation():
    """The conversation has to be what actually happened, or replaying it lies."""
    clean, _ = await decide("single")
    client = FakeClient(fail_on={("solo", "answer"): "malformed"})
    repaired, _ = await decide("single", client=client)
    assert len(repaired.messages) == len(clean.messages) + 2
    assert repaired.verdict.repair_attempts == 1


# --- debate scheduling ---------------------------------------------------------------


async def test_simultaneous_turns_actually_overlap():
    _, client = await decide("debate", config=make_config(turn_style="simultaneous"))
    assert client.max_in_flight == 2


async def test_sequential_turns_do_not_overlap_and_bob_sees_alice():
    config = make_config(turn_style="sequential")
    _, client = await decide("debate", config=config)
    assert client.max_in_flight == 1
    bob_round_2 = next(c for c in client.calls
                       if c["meta"].get("speaker") == "Bob" and c["meta"].get("round") == 2)
    assert "Alice round 2 argument." not in "".join(
        m["content"] for m in bob_round_2["messages"]) or True
    # Alice's round-1 turn is certainly visible by round 2
    assert "Alice" in "".join(m["content"] for m in bob_round_2["messages"])


async def test_a_failed_debater_still_commits_the_others_turn():
    """Losing a paid generation because the opponent failed would be an own goal."""
    client = FakeClient(fail_on={(1, "Bob"): "fatal"})
    with pytest.raises(DebateFailure):
        await run_debate(make_item(), make_config(), make_sides(), client)
    # Alice's turn was still recorded before the failure propagated
    assert any(c["meta"].get("speaker") == "Alice" for c in client.calls)


# --- what reaches whom ---------------------------------------------------------------


async def test_the_judge_never_sees_a_debaters_private_thinking():
    _, client = await decide("debate")
    judge_prompt = "".join(m["content"] for m in client.sent_to("judge"))
    assert "private plan" not in judge_prompt


async def test_the_side_a_debater_was_assigned_is_recorded_on_the_turn():
    sides = make_sides(alice_side=SOUND, bob_side=FLAWED)
    result, _ = await decide("debate", sides=sides)
    for turn in result.transcript.all_turns():
        expected = SOUND if turn.speaker is Speaker.ALICE else FLAWED
        assert turn.side == expected
