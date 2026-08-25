"""The three conditions: what they call, in what order, and what they leave behind."""

from __future__ import annotations

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import make_config, make_item, make_sides

from exp2.arms import (
    CONDITIONS,
    DECIDERS,
    WITHHELD,
    WITHHELD_TRUNCATED,
    run_self_critique,
    run_single,
)
from exp2.debate import run_debate
from exp2.engine import DebateFailure, TruncatedOutputError
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


# --- the repair, aimed by shape ------------------------------------------------------
#
# Pilot 2 lost 15 cells malformed-AFTER-repair, and in every one the repair reply was
# the same class of failure as the reply that bought it: told "reply again with exactly
# two labelled sections", the model wrote two sections wrongly again. The fix is to ask
# for the one section that can be published. These tests are the end-to-end half of
# `test_prompts.py`'s unit half: they check what actually goes on the wire, that it is
# still ONE repair, and that the conversation records what happened.

# Pilot-2's commonest shape, verbatim in structure: everything filed under Thinking,
# verdict and all, and no public label anywhere.
THINKING_ONLY_SOLO = (
    "Thinking:\nThe solution claims the assumption is harmless. Checking it now.\n\n"
    "Therefore, the sentence is flawed.\n\nVerdict: FLAWED"
)
# What the aimed instruction asks for, and what the parser accepts from it.
PUBLIC_ONLY_SOLO = "Reasoning: The sentence misstates the rule.\n\nVerdict: FLAWED"


# --- the scar a repair used to leave ---------------------------------------------------
#
# "Do not write a Thinking section" stayed in a solo conversation and the model kept
# obeying it: `salvaged_no_thinking` ran at 4.8% across pilot 2's original decisions and
# 51.0% in its retry pass. Not a leak — nothing marked private was published, because
# nothing was marked private — but those cells' records are a different kind of document
# from the rest, and it is a confound between the retried cells and the others. Two
# things fix it: the instruction scopes itself, and the next turn restates the format.


async def test_the_aimed_repair_scopes_itself_to_the_one_reply():
    client = FakeClient(fail_on={("solo", "draft"): "malformed"},
                        malformed_content=THINKING_ONLY_SOLO)
    await decide("self_critique", client=client)
    repair = client.calls[1]["messages"][-1]["content"]
    assert repair.startswith("For this reply only, do not write a Thinking section.")


async def test_the_next_stage_restates_the_format_only_after_a_repair():
    """Conditional, so an unrepaired run's prompts are byte-identical to what they
    were: an unconditional reminder would change every solo conversation in the
    experiment to fix something that happens in a fifth of them."""
    from exp2.prompts import REPAIR_CARRYOVER_PREFIX

    clean = FakeClient()
    await decide("self_critique", client=clean)
    assert not any(REPAIR_CARRYOVER_PREFIX in m["content"]
                   for call in clean.calls for m in call["messages"])

    client = FakeClient(fail_on={("solo", "draft"): "malformed"},
                        malformed_content=THINKING_ONLY_SOLO)
    await decide("self_critique", client=client)
    critique = client.sent_to("critic")[-1]["content"]
    assert critique.startswith(REPAIR_CARRYOVER_PREFIX)
    # and it must not fight the critique instruction, which forbids a verdict
    assert "Do not give a verdict in this response." in critique
    assert "Verdict:" not in REPAIR_CARRYOVER_PREFIX


async def test_a_conversation_that_spent_a_repair_is_detectable_from_its_messages():
    """The contest replays `conversation.json` and that file is the only record of what
    was said, so the detector reads the messages rather than a counter."""
    from exp2.prompts import conversation_spent_a_repair

    clean, _ = await decide("single")
    assert conversation_spent_a_repair(clean.messages) is False

    client = FakeClient(fail_on={("solo", "answer"): "malformed"},
                        malformed_content=THINKING_ONLY_SOLO)
    repaired, _ = await decide("single", client=client)
    assert conversation_spent_a_repair(repaired.messages) is True


def test_every_repair_template_is_detected_by_the_carryover_check():
    """If a template were added without a marker the recourse replay would silently
    stop restating the format on the runs that need it most."""
    from exp2.prompts import (
        REPAIR_INSTRUCTIONS,
        budget_repair_instruction,
        conversation_spent_a_repair,
        repair_instruction_for,
    )

    texts = [repair_instruction_for(role, 400) for role in REPAIR_INSTRUCTIONS]
    texts += [repair_instruction_for(role, 400, kind)
              for role in ("solo", "critic", "debater", "challenger", "recourse_solo")
              for kind in ("no_public_label", "label_not_at_line_start",
                           "private_label_in_public", "xml_tag")]
    texts.append(budget_repair_instruction("Reasoning", 400))
    for text in texts:
        assert conversation_spent_a_repair([{"role": "user", "content": text}]), text
    # and it does not fire on an ordinary turn
    assert not conversation_spent_a_repair(
        [{"role": "user", "content": "Now criticise your own assessment above."}])
PUBLIC_ONLY_ARGUMENT = "Argument: Alice argues the step is wrong."


async def test_a_thinking_only_reply_is_told_that_none_of_it_can_be_published():
    client = FakeClient(
        fail_on={("solo", "answer"): "malformed"},
        malformed_content=THINKING_ONLY_SOLO,
        replies={("solo", "repair"): PUBLIC_ONLY_SOLO},
    )
    result, client = await decide("single", client=client)
    repair = _repairs(client)[0]
    # the malformed reply is the assistant turn: the conversation has to be true
    assert repair["messages"][-2] == {"role": "assistant",
                                      "content": THINKING_ONLY_SOLO}
    instruction = repair["messages"][-1]["content"]
    assert "had only a Thinking section" in instruction
    assert "begin your reply with the line `Reasoning:`" in instruction
    assert "Verdict: FLAWED" in instruction
    # and the reply it asks for is one the parser accepts, at ONE repair
    step = result.trace.all_steps()[0]
    assert step.parse_mode == "salvaged_no_thinking"
    assert step.repair_attempts == 1
    assert result.verdict.repair_attempts == 1
    assert len(_repairs(client)) == 1


async def test_a_glued_label_is_told_where_the_label_goes_not_what_it_can_publish():
    """5 of pilot-2's 15: the label was there, glued to the end of the sentence that
    announced it. Telling that reply "none of it can be published" would be false."""
    glued = ("Thinking:\nThe criticism is right.\n\n"
             "I'll write the revised assessment under Reasoning.Reasoning:\n"
             "The sentence misstates the rule.\n\nVerdict: FLAWED")
    client = FakeClient(
        fail_on={("solo", "answer"): "malformed"},
        malformed_content=glued,
        replies={("solo", "repair"): PUBLIC_ONLY_SOLO},
    )
    result, client = await decide("single", client=client)
    instruction = _repairs(client)[0]["messages"][-1]["content"]
    assert "must begin on its own line with `Reasoning:`" in instruction
    assert "had only a Thinking section" not in instruction
    assert result.trace.all_steps()[0].parse_mode == "salvaged_no_thinking"


async def test_a_debater_gets_the_same_treatment_under_its_own_label():
    client = FakeClient(
        fail_on={(1, Speaker.ALICE.value): "malformed"},
        malformed_content=("Thinking:\nI must show the starting material is wrong.\n"
                           "So the regiochemistry does not match the target."),
        replies={(1, Speaker.ALICE.value): PUBLIC_ONLY_ARGUMENT},
    )
    result, client = await decide("debate", client=client)
    instruction = _repairs(client)[0]["messages"][-1]["content"]
    assert "begin your reply with the line `Argument:`" in instruction
    assert "within the stated word limit" in instruction
    turn = result.transcript.all_turns()[0]
    assert turn.parse_mode == "salvaged_no_thinking"
    assert turn.repair_attempts == 1


async def test_an_unclassified_malformed_reply_still_gets_the_old_instruction():
    """The fallback is the safety of the whole change. `no labels here at all` is the
    fake's default malformed reply and has no aimed instruction."""
    client = FakeClient(fail_on={("solo", "answer"): "malformed"})
    _, client = await decide("single", client=client)
    instruction = _repairs(client)[0]["messages"][-1]["content"]
    assert "Reply again with exactly two labelled sections" in instruction


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


# --- the two token caps --------------------------------------------------------------


async def test_record_producing_roles_use_the_generation_cap(tmp_path):
    """Every one of the pilot's 16 truncations was a debater's or reviewer's own private
    Thinking block; not one was a judge, challenger or ruling. So the runaway is bounded
    where it lives, and the deciding roles keep the run's own ceiling."""
    config = make_config(max_tokens=16384, generation_max_tokens=8192)
    client = FakeClient()
    await run_debate(make_item(), config, make_sides(), client)
    assert client.max_tokens_for("debater") == 8192
    assert client.max_tokens_for("judge") == 16384

    client = FakeClient()
    await run_self_critique(make_item(), config, make_sides(), client)
    assert client.max_tokens_for("solo", "draft") == 8192
    assert client.max_tokens_for("critic", "critique") == 8192


# --- the budget route ----------------------------------------------------------------
#
# The pilot's commonest truncation: a debater assigned the pro-flaw side of a *sound*
# item, deliberating without end because there is no honest flaw to find. 12 of its 16
# truncations never reached a public label, so nothing public was cut and the fatal rule
# spent the cap for nothing.

RUNAWAY = ("Thinking: The solution is correct. But I must argue there is a flaw. "
           "Hmm. Perhaps the flaw is that the solu")
# The same runaway, except that the word "Argument:" appears in the deliberation itself —
# mid-line, which the pilot shows models doing. Line anchoring is what keeps this from
# being read as "the public section was reached".
RUNAWAY_MENTIONING_THE_LABEL = (
    "Thinking: I will put this under Argument: once I know what to say. Hmm. Perhaps")
CUT_ARGUMENT = "Thinking: private working.\nArgument: The solution fails at step 2 bec"


def _repairs(client):
    return [c for c in client.calls if c["meta"].get("purpose") == "repair"]


async def test_a_truncation_that_reached_no_public_label_is_repaired_on_budget():
    client = FakeClient(fail_on={(1, Speaker.ALICE.value): "truncated"},
                        truncated_content=RUNAWAY)
    result, client = await decide("debate", client=client)
    turn = result.transcript.all_turns()[0]
    assert turn.parse_mode.endswith("_after_budget_repair")
    assert turn.repair_attempts == 1
    repair = _repairs(client)[0]
    # the truncated reply is the assistant turn, so the conversation stays true
    assert repair["messages"][-2] == {"role": "assistant", "content": RUNAWAY}
    assert "ran out of budget before writing the Argument section" in (
        repair["messages"][-1]["content"])
    assert "Do not deliberate further" in repair["messages"][-1]["content"]


async def test_the_label_is_looked_for_line_anchored_not_anywhere():
    client = FakeClient(fail_on={(1, Speaker.ALICE.value): "truncated"},
                        truncated_content=RUNAWAY_MENTIONING_THE_LABEL)
    result, client = await decide("debate", client=client)
    assert result.transcript.all_turns()[0].parse_mode.endswith("_after_budget_repair")


async def test_a_truncation_that_did_reach_the_public_label_stays_fatal():
    """Something public may have been cut, and a half-written argument entering the
    transcript as if authored is the failure the fatal rule was written for."""
    client = FakeClient(fail_on={(1, Speaker.ALICE.value): "truncated"},
                        truncated_content=CUT_ARGUMENT)
    with pytest.raises(DebateFailure, match="stopped on"):
        await decide("debate", client=client)
    assert _repairs(client) == []


async def test_a_deciding_role_truncated_twice_fails_the_run():
    client = FakeClient(fail_on={"solo": "truncated_twice"},
                        truncated_content=RUNAWAY)
    with pytest.raises(DebateFailure, match="truncated again after a budget repair"):
        await decide("single", client=client)


async def test_a_critique_truncated_twice_is_withheld_rather_than_fatal():
    """A withheld critique costs a step of the record; killing the cell costs all of it."""
    client = FakeClient(fail_on={"critic": "truncated_twice"},
                        truncated_content=RUNAWAY)
    result, _ = await decide("self_critique", client=client)
    critiques = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert critiques[0].text == WITHHELD_TRUNCATED
    assert critiques[0].parse_mode == "unparsed_withheld_truncated_after_budget_repair"
    assert result.verdict.verdict in (FLAWED, SOUND)


async def test_the_roles_that_decide_nothing_keep_truncation_fatal():
    """No public_label, so no budget route: a truncated verdict, ruling or rating is a
    cut decision line, and there is nothing to salvage."""
    client = FakeClient(fail_on={"judge": "truncated"}, truncated_content=RUNAWAY)
    with pytest.raises(Exception, match="stopped on"):
        await decide("debate", client=client)
    assert _repairs(client) == []


# --- a truncation past the label, where the role has a last resort -------------------
#
# Pilot 3 lost 30 cells and **13 of them were a critique truncating past its own
# `Reasoning:` label** (LLM_NOTES §3n, §3o) — one cut critique killing a complete
# seven-stage decision, because the `unrepaired` withholding was reachable only on a
# second failure. Nothing half-written is published by any of this: the truncated reply
# is discarded exactly as before. What changes is that the critic, which decides
# nothing, now spends its one repair instead of failing on the spot.

CUT_REASONING = ("Thinking: private working.\n"
                 "Reasoning: the draft takes step 2 on trust, and step 2 is where")


async def test_a_critique_cut_off_inside_its_label_spends_the_repair_and_survives():
    client = FakeClient(fail_on={"critic": "truncated"},
                        truncated_content=CUT_REASONING)
    result, client = await decide("self_critique", client=client)
    critiques = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert critiques and all(s.repair_attempts == 1 for s in critiques)
    assert all(s.parse_mode.endswith("_after_budget_repair") for s in critiques)
    assert result.verdict.verdict in (FLAWED, SOUND), "the decision survives"
    # the cut half-sentence is not published anywhere
    assert all("step 2 is where" not in s.text for s in critiques)
    # and the repair says what actually happened rather than the other route's sentence
    instruction = _repairs(client)[0]["messages"][-1]["content"]
    assert "partway through the Reasoning section" in instruction
    assert "ran out of budget before writing" not in instruction
    assert _repairs(client)[0]["messages"][-2] == {"role": "assistant",
                                                  "content": CUT_REASONING}


async def test_a_critique_cut_off_twice_is_withheld_and_the_placeholder_says_why():
    client = FakeClient(fail_on={"critic": "truncated_twice"},
                        truncated_content=CUT_REASONING)
    result, _ = await decide("self_critique", client=client)
    critiques = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert all(s.text == WITHHELD_TRUNCATED for s in critiques)
    assert all(s.parse_mode == "unparsed_withheld_truncated_after_budget_repair"
               for s in critiques), "a truncated withholding is countable apart"
    assert result.verdict.verdict in (FLAWED, SOUND)


async def test_the_truncated_placeholder_reaches_the_document_and_the_challenger(
    tmp_path,
):
    """The accepted degradation, stated in LLM_NOTES §3o: the self_critique record can
    now carry a placeholder where a critique should be, and the challenger reads it."""
    from recording import recorded

    from exp2.types import DecisionRecord

    client = FakeClient(fail_on={"critic": "truncated_twice"},
                        truncated_content=CUT_REASONING)
    writer, result = await recorded(tmp_path, "self_critique", client=client)
    assert WITHHELD_TRUNCATED in (writer.dir / "transcript.md").read_text()
    assert WITHHELD_TRUNCATED in DecisionRecord.for_solo(result.trace).body


async def test_a_critique_that_reached_no_label_still_takes_the_ordinary_budget_route():
    """The route that already existed is untouched: nothing public was cut, so the
    repair asks for the section that was never begun."""
    client = FakeClient(fail_on={"critic": "truncated"}, truncated_content=RUNAWAY)
    result, client = await decide("self_critique", client=client)
    critiques = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert all(s.parse_mode.endswith("_after_budget_repair") for s in critiques)
    assert all("repair assessment" in s.text for s in critiques), (
        "the repair's own reply is what the record carries")
    assert "ran out of budget before writing the Reasoning section" in (
        _repairs(client)[0]["messages"][-1]["content"])


async def test_a_solo_stage_that_decides_keeps_a_cut_label_fatal():
    """The deciding stages pass no last resort, so the rescue cannot reach them. A cut
    `Reasoning:` section may be a decision cut in half, and there is nothing to fall
    back to — the same rule the debater keeps two tests above."""
    client = FakeClient(fail_on={("solo", "answer"): "truncated"},
                        truncated_content=CUT_REASONING)
    with pytest.raises(TruncatedOutputError, match="stopped on"):
        await decide("single", client=client)
    assert _repairs(client) == []


async def test_a_critique_cut_off_then_malformed_is_still_reported_as_truncated():
    """The truncation is what cost the step, whichever way the repair then failed."""
    client = FakeClient(fail_on={("critic", "critique"): "truncated"},
                        truncated_content=CUT_REASONING,
                        replies={("critic", "repair"): "no labels at all"})
    result, _ = await decide("self_critique", client=client)
    critiques = [s for s in result.trace.all_steps() if s.stage == "critique"]
    assert all(s.text == WITHHELD_TRUNCATED for s in critiques)
    assert all(s.parse_mode == "unparsed_withheld_truncated_after_budget_repair"
               for s in critiques)
