"""Templates, builders, and the parsers that read the replies back.

The most important test here is ``test_no_prompt_changes_when_the_label_is_flipped``.
exp1 could enforce "the gold answer never reaches a prompt" structurally, because its
gold was an index that would have had to be matched against answer text to leak. exp2's
is a bool, which cannot be grepped for, so the guarantee has to be a property test.
"""

from __future__ import annotations

import pytest
from helpers import SECRET_THINKING, full_transcript, make_config, make_item, make_sides

from exp2.prompts import (
    FLAW_DEFINITION,
    FLAW_PHRASE,
    SOUND_PHRASE,
    MalformedOutputError,
    build_challenger_messages,
    build_comprehension_messages,
    build_debater_messages,
    build_grader_messages,
    build_judge_messages,
    build_recourse_judge_messages,
    build_repair_messages,
    build_solo_opening,
    build_solo_recourse_message,
    length_clause,
    length_rule,
    parse_comprehension_output,
    parse_debater_output,
    parse_grade_output,
    parse_objection_output,
    parse_ruling_output,
    parse_verdict_output,
    repair_instruction_for,
    side_phrase,
)
from exp2.types import FLAWED, SOUND, DecisionRecord, Speaker, Transcript


def every_message_list(item, sides, config):
    """Every prompt this module can build for one item, as (name, messages) pairs."""
    transcript = full_transcript(sides)
    record = DecisionRecord.for_debate(transcript)
    solo_record = DecisionRecord.for_solo_body("Reasoning: it looks fine.")
    return [
        ("debater-a-r1", build_debater_messages(item, sides, config, Transcript(),
                                                speaker=Speaker.ALICE, round_number=1)),
        ("debater-b-r3", build_debater_messages(item, sides, config, transcript,
                                                speaker=Speaker.BOB, round_number=3)),
        ("judge", build_judge_messages(item, sides, config, transcript)),
        ("solo-answer", build_solo_opening(item, sides, config, stage="answer")),
        ("solo-draft", build_solo_opening(item, sides, config, stage="draft")),
        ("challenger-debate", build_challenger_messages(
            item, config, record, sides=sides, decision_verdict=FLAWED,
            decision_grounds="The judge's grounds.")),
        ("challenger-solo", build_challenger_messages(
            item, config, solo_record, sides=sides, decision_verdict=SOUND,
            decision_grounds="The reviewer's grounds.")),
        ("recourse-judge", build_recourse_judge_messages(
            item, sides, record, decision_verdict=FLAWED, objection="An objection.")),
    ]


# --- the invariant ------------------------------------------------------------------


def test_no_prompt_changes_when_the_label_is_flipped():
    """The ground truth must not reach any prompt, in any role.

    Built twice from the same item with only ``gold_flawed`` differing; every message
    list must be byte-identical. A template that interpolated the label, or a builder
    that branched on it, fails here.
    """
    config, sides = make_config(), make_sides()
    flawed = every_message_list(make_item(gold_flawed=True), sides, config)
    sound = every_message_list(make_item(gold_flawed=False), sides, config)
    for (name, a), (_, b) in zip(flawed, sound):
        assert a == b, f"{name} differs when the ground-truth label is flipped"


def test_all_five_roles_are_told_what_a_flaw_is_and_told_the_same_thing():
    """Until 2026-08-25 no prompt defined the word, and eight of nine probed models
    answered FLAWED on 63-87% of a 46%-flawed fixture. Debater, judge, solo reviewer,
    challenger and grader must be answering the same question, so the definition is one
    constant interpolated five times -- and this test is what stops it drifting out of
    one of them."""
    config, sides, item = make_config(), make_sides(), make_item()
    built = dict(every_message_list(item, sides, config))
    built["grader"] = build_grader_messages(
        item, flaw_location="2", annotation="a", grades_characterisation=True,
        objection="obj")

    for name in ("debater-a-r1", "judge", "solo-answer", "challenger-debate", "grader"):
        system = built[name][0]
        assert system["role"] == "system", name
        assert FLAW_DEFINITION in system["content"], (
            f"{name} does not carry the flaw definition")

    # The wording the corpus was annotated against, and the anti-nitpick clause that
    # is the whole point of adding it.
    assert "untrue, illogical, or " in FLAW_DEFINITION
    assert "\u2014 something a careful expert" in FLAW_DEFINITION
    assert "misleading" in FLAW_DEFINITION
    assert "SOUND does not mean perfect" in FLAW_DEFINITION
    # No base-rate hint: telling a judge how often the answer is FLAWED would let it
    # score without reading (the user's explicit choice, 2026-08-25).
    for hint in ("%", "half", "46", "roughly as many", "base rate"):
        assert hint not in FLAW_DEFINITION, f"base-rate hint {hint!r} leaked in"


def test_a_system_prompt_that_drops_the_placeholder_fails_at_import():
    """Dropping `{flaw_definition}` from a template must be an error, not a silent
    change to the question a role is being asked."""
    from exp2.prompts import _with_flaw_definition

    with pytest.raises(ValueError, match="flaw_definition"):
        _with_flaw_definition("You are a judge. Decide.")
    assert FLAW_DEFINITION in _with_flaw_definition("x {flaw_definition} y")


def test_the_annotation_never_reaches_a_decision_or_contest_prompt():
    """Only the grader sees what the dataset records about the flaw."""
    needle = "THE-RECORDED-FLAW-IS-IN-STEP-TWO"
    config, sides, item = make_config(), make_sides(), make_item()
    for name, messages in every_message_list(item, sides, config):
        blob = "".join(m["content"] for m in messages)
        assert needle not in blob, name
    grader = build_grader_messages(item, flaw_location="2", annotation=needle,
                                   grades_characterisation=True, objection="obj")
    assert needle in "".join(m["content"] for m in grader)


def test_private_thinking_never_reaches_the_judge_or_the_challenger():
    config, sides = make_config(), make_sides()
    transcript = full_transcript(sides)
    judge = build_judge_messages(make_item(), sides, config, transcript)
    assert SECRET_THINKING not in "".join(m["content"] for m in judge)
    record = DecisionRecord.for_debate(transcript)
    assert SECRET_THINKING not in record.body


# --- sides and framing ---------------------------------------------------------------


def test_a_debater_is_told_its_own_side_and_its_opponents():
    config = make_config()
    alice_flawed = make_sides(alice_side=FLAWED, bob_side=SOUND)
    messages = build_debater_messages(make_item(), alice_flawed, config, Transcript(),
                                      speaker=Speaker.ALICE, round_number=1)
    user = messages[1]["content"]
    assert f"You argue that {FLAW_PHRASE}" in user
    assert f"Bob argues that {SOUND_PHRASE}" in user

    swapped = make_sides(alice_side=SOUND, bob_side=FLAWED)
    user2 = build_debater_messages(make_item(), swapped, config, Transcript(),
                                   speaker=Speaker.ALICE, round_number=1)[1]["content"]
    assert f"You argue that {SOUND_PHRASE}" in user2


def test_the_judge_is_told_who_argued_which_side_not_who_spoke_first():
    """Alice always speaks first, so naming sides by speaking order would leak the
    randomisation that exists to neutralise position bias."""
    config = make_config()
    bob_flawed = make_sides(alice_side=SOUND, bob_side=FLAWED)
    user = build_judge_messages(make_item(), bob_flawed, config,
                                full_transcript(bob_flawed))[1]["content"]
    assert "Bob argued that it does." in user
    assert "Alice argued that it does not." in user


def test_the_verdict_template_order_follows_the_draw():
    config = make_config()
    flawed_first = build_judge_messages(
        make_item(), make_sides(verdict_order=(FLAWED, SOUND)), config,
        full_transcript(make_sides()))[1]["content"]
    sound_first = build_judge_messages(
        make_item(), make_sides(verdict_order=(SOUND, FLAWED)), config,
        full_transcript(make_sides()))[1]["content"]
    assert "Verdict: <FLAWED|SOUND>" in flawed_first
    assert "Verdict: <SOUND|FLAWED>" in sound_first


def test_the_last_round_drops_the_further_rounds_clause():
    config = make_config(n_rounds=3)
    item, sides = make_item(), make_sides()
    early = build_debater_messages(item, sides, config, Transcript(),
                                   speaker=Speaker.ALICE, round_number=1)[1]["content"]
    last = build_debater_messages(item, sides, config, full_transcript(sides),
                                  speaker=Speaker.ALICE, round_number=3)[1]["content"]
    assert "Further rounds follow" in early
    assert "Further rounds follow" not in last


def test_a_solo_prompt_never_says_anyone_argued_a_position():
    """Nobody argued in a solo run; exp1 shipped a record that claimed otherwise."""
    messages = build_solo_opening(make_item(), make_sides(), make_config(), stage="answer")
    blob = "".join(m["content"] for m in messages)
    for word in ("Alice", "Bob", "debate", "debater", "opponent"):
        assert word.lower() not in blob.lower(), word


def test_the_solo_and_judge_prompts_share_the_verdict_template_order():
    """So position bias is controlled identically across conditions."""
    sides = make_sides(verdict_order=(SOUND, FLAWED))
    solo = build_solo_opening(make_item(), sides, make_config(), stage="answer")[1]["content"]
    judge = build_judge_messages(make_item(), sides, make_config(),
                                 full_transcript(sides))[1]["content"]
    assert "Verdict: <SOUND|FLAWED>" in solo and "Verdict: <SOUND|FLAWED>" in judge


# --- challenger ----------------------------------------------------------------------


def test_the_challenger_can_read_the_text_it_is_asked_to_judge():
    """DESIGN.md: "The challenger only sees the public transcript; this should contain
    the original problem statement", and the published record is "problem + solution +
    verdict + justification".

    Without this the challenger judges an argument about a text it cannot read, while
    the recourse judge ruling on its objection can — and the shortfall bites unevenly,
    because debaters are told to quote the text and a lone reviewer may not be, which
    would manufacture a debate advantage that is about record contents rather than
    contestability.
    """
    item = make_item()
    for record in (DecisionRecord.for_debate(full_transcript(make_sides())),
                   DecisionRecord.for_solo_body("body")):
        prompt = "".join(m["content"] for m in build_challenger_messages(
            item, make_config(), record, sides=make_sides(),
            decision_verdict=FLAWED, decision_grounds="g"))
        assert item.problem in prompt
        assert item.solution in prompt


def test_the_challenger_and_the_recourse_judge_read_the_same_material():
    """Not merely the same transcript — the same problem and solution too."""
    item, sides, config = make_item(), make_sides(), make_config()
    record = DecisionRecord.for_debate(full_transcript(sides))
    challenger = "".join(m["content"] for m in build_challenger_messages(
        item, config, record, sides=sides, decision_verdict=FLAWED,
        decision_grounds="g"))
    judge = "".join(m["content"] for m in build_recourse_judge_messages(
        item, sides, record, decision_verdict=FLAWED, objection="o"))
    for text in (item.problem, item.solution, record.body):
        assert text in challenger and text in judge


def test_the_challenger_record_matches_the_shape_of_the_decision():
    config, sides = make_config(), make_sides()
    debate = build_challenger_messages(
        make_item(), config, DecisionRecord.for_debate(full_transcript(sides)), sides=sides,
        decision_verdict=FLAWED, decision_grounds="g")[1]["content"]
    solo = build_challenger_messages(
        make_item(), config, DecisionRecord.for_solo_body("body"), sides=sides,
        decision_verdict=FLAWED, decision_grounds="g")[1]["content"]
    assert "Two debaters were assigned opposing positions" in debate
    assert "No debaters were assigned and nobody argued a position" in solo
    assert "Alice" not in solo and "Bob" not in solo


def test_the_challenger_is_refused_a_bare_transcript():
    """exp1's bug: a solo decision described to the challenger as a debate."""
    with pytest.raises(TypeError, match="DecisionRecord"):
        build_challenger_messages(make_item(), make_config(),
                                  full_transcript(make_sides()),
                                  sides=make_sides(), decision_verdict=FLAWED,
                                  decision_grounds="g")


def test_the_challenger_may_always_decline():
    messages = build_challenger_messages(
        make_item(), make_config(), DecisionRecord.for_solo_body("b"), sides=make_sides(),
        decision_verdict=SOUND, decision_grounds="g")
    assert 'reading exactly "Objection: RAISED"' in messages[1]["content"]
    assert '"Objection: NONE"' in messages[1]["content"]


def test_comprehension_is_asked_in_the_challengers_own_conversation():
    prior = build_challenger_messages(
        make_item(), make_config(), DecisionRecord.for_solo_body("b"), sides=make_sides(),
        decision_verdict=SOUND, decision_grounds="g")
    messages = build_comprehension_messages(prior, "Objection: NONE\nLooks fine.")
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert "how well could you follow" in messages[-1]["content"]
    # the scale is shown verbatim, so the record can say what a 4 meant
    assert "4 — I could follow most of it" in messages[-1]["content"]


# --- recourse ------------------------------------------------------------------------


def test_the_recourse_judge_sees_the_same_record_as_the_challenger():
    config, sides = make_config(), make_sides()
    record = DecisionRecord.for_debate(full_transcript(sides))
    challenger = build_challenger_messages(make_item(), config, record, sides=sides,
                                           decision_verdict=FLAWED, decision_grounds="g")
    judge = build_recourse_judge_messages(make_item(), sides, record,
                                          decision_verdict=FLAWED, objection="o")
    assert record.body in challenger[1]["content"]
    assert record.body in judge[1]["content"]


def test_the_solo_recourse_turn_asks_for_reconsideration_not_capitulation():
    turn = build_solo_recourse_message(make_sides(), "You divided by zero.")
    assert turn["role"] == "user"
    assert "Change your answer if it is right and keep your answer if it is not" in turn["content"]
    assert "Verdict: <FLAWED|SOUND>" in turn["content"]


# --- parsers -------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("Reasoning here.\nVerdict: FLAWED", "FLAWED"),
    ("**Verdict:** SOUND", "SOUND"),
    ("#### Verdict: flawed", "FLAWED"),
    ("Verdict: SOUND\nActually, on reflection.\nVerdict: FLAWED", "FLAWED"),
])
def test_the_verdict_matcher_is_tolerant_and_takes_the_last_match(text, expected):
    assert parse_verdict_output(text)[0] == expected


@pytest.mark.parametrize("template", [
    "I will end with Verdict: <FLAWED|SOUND>",
    "I will end with Verdict: <SOUND|FLAWED>",
])
def test_a_restated_verdict_template_is_refused_in_either_order(template):
    """The order is randomised per item, so a lenient parse would smear noise across
    every condition's headline accuracy."""
    with pytest.raises(MalformedOutputError):
        parse_verdict_output(template)


def test_the_verdict_reasoning_is_what_precedes_the_decisive_line():
    verdict, reasoning, mode = parse_verdict_output("Because X.\n\nVerdict: SOUND")
    assert (verdict, reasoning, mode) == ("SOUND", "Because X.", "strict")


def test_a_bare_word_is_not_a_verdict():
    with pytest.raises(MalformedOutputError):
        parse_verdict_output("I think it is flawed.")


def test_the_debater_parser_is_exp1s_verbatim():
    thinking, argument, mode = parse_debater_output(
        "Thinking: private\nArgument: public")
    assert (thinking, argument, mode) == ("private", "public", "strict")
    # a trailing coda after the argument is dropped, not published
    _, argument, mode = parse_debater_output(
        "Thinking: p\nArgument: public\nThinking: I should have conceded")
    assert argument == "public" and mode.endswith("_trailing_dropped")
    # a missing Argument label raises rather than publishing the whole response
    with pytest.raises(MalformedOutputError):
        parse_debater_output("Thinking: everything is private")
    # a one-line "Argument: Thinking:" hides the second label from the line anchor
    with pytest.raises(MalformedOutputError):
        parse_debater_output("Argument: Thinking: private stuff")


def test_an_inline_thinking_label_anywhere_in_the_argument_is_refused():
    """The exact shape measured on 2 of 426 fixture arguments: the debater restates
    the whole structure with no newline before the second label, so `_LABEL_RE`'s line
    anchor misses both and the argument runs to end of text — publishing the private
    block to the judge and the challenger with parse_mode="strict"."""
    leaked = ("Thinking:\nfirst private plan.\n"
              "Argument:\nThe step is sound and the text does not contain a "
              "flawThinking: on reflection I should concede the point about step "
              "2.Argument: The step is sound.")
    with pytest.raises(MalformedOutputError, match="contains a 'Thinking:' label"):
        parse_debater_output(leaked)

    # ... at the head, as before
    with pytest.raises(MalformedOutputError, match="contains a 'Thinking:' label"):
        parse_debater_output("Argument: Thinking: private")
    # ... and at the very end
    with pytest.raises(MalformedOutputError, match="contains a 'Thinking:' label"):
        parse_debater_output("Argument: public claim. Thinking: but privately, no.")
    # an ordinary argument is untouched
    _, argument, mode = parse_debater_output(
        "Thinking: private\nArgument: Step 2 divides by zero.")
    assert argument == "Step 2 divides by zero." and mode == "strict"
    # ... including prose that merely contains the letters. `\bThinking` cannot match
    # "flawThinking:" at all (no word boundary between two word characters), which is
    # why the rule needs a second, case-sensitive alternative — and why that alternative
    # must not fire on "Rethinking:".
    _, argument, _ = parse_debater_output(
        "Argument: Rethinking: the analyst's step 2 is where it fails.")
    assert argument.startswith("Rethinking:")


def test_the_objection_parser_layers_on_the_debater_parser():
    thinking, raised, body, _ = parse_objection_output(
        "Thinking: private\nArgument: Objection: RAISED\nStep 2 divides by zero.")
    assert thinking == "private" and raised is True
    assert body == "Step 2 divides by zero."


def test_a_decline_keeps_its_body_as_evidence():
    """The text after a decline is the only evidence for whether the challenger
    declined having understood the record or having skimmed it."""
    _, raised, body, _ = parse_objection_output(
        "Thinking: t\nArgument: Objection: NONE\nThe judge checked the algebra.")
    assert raised is False and body == "The judge checked the algebra."


def test_a_raised_objection_with_no_body_is_refused():
    with pytest.raises(MalformedOutputError, match="no objection after it"):
        parse_objection_output("Thinking: t\nArgument: Objection: RAISED")


def test_a_missing_objection_line_is_refused_rather_than_guessed():
    with pytest.raises(MalformedOutputError, match="Objection"):
        parse_objection_output("Thinking: t\nArgument: This decision seems wrong.")


def test_a_label_less_challenger_reply_is_salvaged():
    """The shape the first probe measured 70/70 times on ling-3.0-flash: the decision
    line, then the reasoning, and no Thinking/Argument wrapper at all. Nothing was
    marked private, so nothing can leak by publishing all of it."""
    thinking, raised, body, mode = parse_objection_output(
        "Objection: NONE\nThe decision is sound because the derivation is complete.")
    assert raised is False
    assert thinking == ""
    assert body == "The decision is sound because the derivation is complete."
    assert mode == "salvaged_no_labels"

    _, raised, body, mode = parse_objection_output(
        "Objection: RAISED\nSentence 8 assumes the contract was fulfilled.")
    assert raised is True and mode == "salvaged_no_labels"
    assert body == "Sentence 8 assumes the contract was fulfilled."


def test_the_salvage_refuses_anything_that_marked_text_private():
    # a Thinking: label with no Argument: label — the boundary is unknown
    with pytest.raises(MalformedOutputError):
        parse_objection_output("Thinking: private\nObjection: NONE\nlooks fine")
    # ... including one that is not at the head of a line
    with pytest.raises(MalformedOutputError):
        parse_objection_output("Objection: NONE it is fine. Thinking: but actually no")
    # a one-line "Argument: Thinking:" is still refused by the debater parser
    with pytest.raises(MalformedOutputError):
        parse_objection_output("Argument: Thinking: private\nObjection: NONE\nfine")
    # the salvage does not weaken the other rules
    with pytest.raises(MalformedOutputError, match="no objection after it"):
        parse_objection_output("Objection: RAISED")
    with pytest.raises(MalformedOutputError, match="Objection"):
        parse_objection_output("Objection: <RAISED|NONE>\nsomething is wrong")
    with pytest.raises(MalformedOutputError):
        parse_objection_output("This decision seems wrong but I cannot say why.")


def test_the_ruling_parser_refuses_near_misses_rather_than_normalising_them():
    assert parse_ruling_output("Because X.\nRuling: OVERTURN")[0] == "OVERTURN"
    for near_miss in ("Ruling: UPHELD", "Ruling: OVERRULED", "Ruling: <UPHOLD|OVERTURN>"):
        with pytest.raises(MalformedOutputError):
            parse_ruling_output(near_miss)


def test_the_comprehension_parser_takes_one_to_five_only():
    score, justification, _ = parse_comprehension_output(
        "I followed most of it.\nComprehension: 4")
    assert score == 4 and justification == "I followed most of it."
    for bad in ("Comprehension: 6", "Comprehension: 0", "Comprehension: <1|2|3|4|5>"):
        with pytest.raises(MalformedOutputError):
            parse_comprehension_output(bad)


def test_the_grader_parser_returns_two_independent_booleans():
    identified, characterised, reasoning, _ = parse_grade_output(
        "It points at step 2 but only calls it odd.\n"
        "Identified the flaw: YES\nCharacterised the flaw: NO")
    assert identified is True and characterised is False
    assert reasoning.startswith("It points at step 2")
    # American spelling is accepted, since the grader model may normalise it
    assert parse_grade_output(
        "Identified the flaw: NO\nCharacterized the flaw: NO")[:2] == (False, False)


def test_a_grader_response_missing_a_line_names_what_is_missing():
    with pytest.raises(MalformedOutputError, match="Characterised the flaw"):
        parse_grade_output("Identified the flaw: YES")


# --- repair --------------------------------------------------------------------------


def test_each_role_gets_its_own_repair_instruction():
    """A challenger repaired with the debater's instruction would be asked for a
    response the challenger parser then refuses, burning the one attempt."""
    assert "Objection:" in repair_instruction_for("challenger", 400)
    assert "Verdict:" in repair_instruction_for("judge", 400)
    assert "Ruling:" in repair_instruction_for("recourse_judge", 400)
    assert "Comprehension:" in repair_instruction_for("comprehension", 400)
    with pytest.raises(ValueError):
        repair_instruction_for("nobody", 400)


def test_repair_messages_replay_the_bad_output_so_the_model_can_see_it():
    original = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    messages = build_repair_messages(original, "garbage", role="judge", word_limit=400)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[2]["content"] == "garbage"


def test_length_rule_and_clause_handle_the_no_cap_case():
    assert "at most 400 words per argument" in length_rule(400)
    assert "no word limit" in length_rule(0)
    assert length_clause(400) == "within the stated word limit"
    assert length_clause(0) == "concisely"


def test_side_phrase_refuses_a_word_outside_the_vocabulary():
    assert side_phrase(FLAWED) == FLAW_PHRASE and side_phrase(SOUND) == SOUND_PHRASE
    with pytest.raises(ValueError):
        side_phrase("YES")
