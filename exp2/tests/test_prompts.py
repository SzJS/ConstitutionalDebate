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
    _round_instructions,
    FLAW_DEFINITION,
    FLAW_PHRASE,
    SOLO_CRITIQUE_INSTRUCTION,
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
    REPAIR_INSTRUCTIONS,
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
    assert "Objection: RAISED" in messages[1]["content"]
    assert "Objection: NONE" in messages[1]["content"]


def test_the_challenger_is_asked_about_the_verdict_not_about_the_text():
    """The pilot's instruction was literally satisfiable by agreeing with the verdict:
    "RAISED if the decision rests on an error" is true of every FLAWED verdict, and the
    challenger duly raised objections that agreed with the decisions they objected to.
    The question asked is now the verdict, and a claimed verdict comes with it."""
    messages = build_challenger_messages(
        make_item(), make_config(), DecisionRecord.for_solo_body("b"), sides=make_sides(),
        decision_verdict=FLAWED, decision_grounds="g")
    instruction = messages[1]["content"]
    assert "whether the **verdict** above is right" in instruction
    assert "Verdict should be:" in instruction
    assert "rests on an error" not in instruction
    # and it must not presuppose a section the challenger does not write: 118 of the
    # pilot's 120 replies carried no Thinking:/Argument: labels at all.
    assert "Begin the Argument section" not in instruction
    # the system prompt says both verdicts are contestable, and says how each is
    system = messages[0]["content"]
    assert "Either verdict can be wrong." in system
    assert "a SOUND verdict is contested by showing a flaw the decision missed" in system
    # ... and deliberately does NOT invite the challenger to go looking for one itself:
    # a challenger told to search has a ready-made flaw in a debate transcript and none
    # in a solo record, which would raise the false-alarm rate for prompt reasons.
    assert "examine it yourself" not in system


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
    # ... and the lookbehind is [A-Za-z], not [a-z]. The paid pilot walked through the
    # lower-case-only version: `Verdict: FLAWEDThinking: <private>` reached a challenger
    # because a capital `D` sits before the label. This is that exact shape.
    with pytest.raises(MalformedOutputError, match="contains a 'Thinking:' label"):
        parse_debater_output(
            "Argument: The sentence is wrong.\n\nVerdict: FLAWEDThinking: The sentence "
            "under review asserts a specific grammatical parsing of option (B).")
    # the same reply on the solo path, which is where every one of the three measured
    # leaks of this class happened
    with pytest.raises(MalformedOutputError):
        parse_objection_output(
            "Objection: NONE\nThe grounds hold.\nVerdict: SOUNDThinking: privately, no.")


def test_the_objection_parser_layers_on_the_debater_parser():
    thinking, raised, body, _, claimed = parse_objection_output(
        "Thinking: private\nArgument: Objection: RAISED\nStep 2 divides by zero.")
    assert thinking == "private" and raised is True
    assert body == "Step 2 divides by zero."
    assert claimed is None


def test_a_decline_keeps_its_body_as_evidence():
    """The text after a decline is the only evidence for whether the challenger
    declined having understood the record or having skimmed it."""
    _, raised, body, _, _ = parse_objection_output(
        "Thinking: t\nArgument: Objection: NONE\nThe judge checked the algebra.")
    assert raised is False and body == "The judge checked the algebra."


def test_the_claimed_verdict_is_parsed_and_taken_out_of_the_body():
    """Both decision lines leave the body. It becomes ``Challenge.text``, which is handed
    to the recourse judge — a challenge opening "Verdict should be: FLAWED" would be an
    instruction to the judge about what to answer rather than an argument for it."""
    _, raised, body, mode, claimed = parse_objection_output(
        "Objection: RAISED\nVerdict should be: SOUND\n"
        "The claimed flaw in step 2 is not one: the identity holds for all real x.")
    assert raised is True and claimed == "SOUND" and mode == "salvaged_no_labels"
    assert body == (
        "The claimed flaw in step 2 is not one: the identity holds for all real x.")
    assert "Verdict should be" not in body and "Objection" not in body


def test_the_claimed_verdict_line_does_not_collide_with_the_verdict_line():
    """`_VERDICT_RE` wants the colon straight after "verdict"; "should be" sits between
    them here. Two vocabularies, as everywhere else in this module."""
    from exp2.prompts import _CLAIMED_VERDICT_RE, _VERDICT_RE

    assert _VERDICT_RE.search("Verdict should be: FLAWED") is None
    assert _CLAIMED_VERDICT_RE.search("Verdict: FLAWED") is None
    # a restated template is refused by both, in either randomised order
    assert _CLAIMED_VERDICT_RE.search("Verdict should be: <FLAWED|SOUND>") is None
    assert _CLAIMED_VERDICT_RE.search("Verdict should be: <SOUND|FLAWED>") is None
    # markdown wrappers, as the other matchers tolerate them
    assert _CLAIMED_VERDICT_RE.search(
        "**Verdict should be:** SOUND").group(1) == "SOUND"


def test_the_two_line_reply_the_challenger_actually_writes_still_salvages():
    """The measured shape: no Thinking:/Argument: labels anywhere, the two decision
    lines, then prose. 118 of the pilot's 120 replies parsed this way."""
    thinking, raised, body, mode, claimed = parse_objection_output(
        "Objection: NONE\nVerdict should be: FLAWED\n"
        "The decision correctly identifies the error in step 4.")
    assert mode == "salvaged_no_labels" and thinking == ""
    assert raised is False and claimed == "FLAWED"
    assert body == "The decision correctly identifies the error in step 4."


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
    thinking, raised, body, mode, _ = parse_objection_output(
        "Objection: NONE\nThe decision is sound because the derivation is complete.")
    assert raised is False
    assert thinking == ""
    assert body == "The decision is sound because the derivation is complete."
    assert mode == "salvaged_no_labels"

    _, raised, body, mode, _ = parse_objection_output(
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


def test_a_critique_is_repaired_towards_reasoning_and_away_from_a_verdict():
    """A critique repaired with the solo instruction would be asked for the verdict line
    its own instruction forbids, burning the one attempt on a contradiction."""
    instruction = repair_instruction_for("critic", 400)
    assert "Reasoning:" in instruction
    assert "Verdict" not in instruction
    assert "Under Reasoning, give the criticism itself" in SOLO_CRITIQUE_INSTRUCTION


def test_repair_messages_replay_the_bad_output_so_the_model_can_see_it():
    original = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    messages = build_repair_messages(original, "garbage", role="judge", word_limit=400)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[2]["content"] == "garbage"


# --- the shape of a refusal, and the repair aimed at it ------------------------------
#
# The four literals below are pilot-2's measured shapes, trimmed but not reshaped
# (LLM_NOTES §3m). Every one of them is a reply the parser is RIGHT to refuse; what
# changed is that the refusal now says which shape it refused, so the one repair
# attempt can be spent on that shape.

# 6 of the 15 malformed-after-repair cells. Everything filed under Thinking, complete
# answer and all, and no public label anywhere.
THINKING_ONLY = (
    "Thinking:\nThe solution claims the assumption is harmless. I need to check it.\n\n"
    "Therefore, the sentence is flawed.\n\nVerdict: FLAWED"
)
# 5 of the 15. The label IS there — glued to the end of the sentence that announced it,
# with no newline, so the line-anchored `_LABEL_RE` cannot see it.
GLUED_LABEL = (
    "Thinking:\nThe criticism is right about the parol evidence rule.\n\n"
    "I'll write the revised assessment under Reasoning.Reasoning:\n"
    "The sentence says \"statements\" where the rule says \"agreements\".\n\n"
    "Verdict: FLAWED"
)
# 1 of the 15. An XML wrapper in place of the label, after two requests for one.
XML_WRAPPED = (
    "Thinking:\nI must show the starting material is wrong.\n"
    "<argument>\nThe regiochemistry does not match the target.\n</argument>"
)
# 3 of the 15. The model restarts mid-sentence and the private label lands INSIDE the
# public section, glued to the last word — "...the text contains no logicalThinking:".
# `_LABEL_RE` is line-anchored and cannot see it as a boundary, so the argument would
# run to the end of the text and publish the restart. `_ANY_THINKING_RE` is what
# catches it, and refusing is the only safe answer: the boundary is unknown.
THINKING_INSIDE = (
    "Thinking: private working.\nArgument: The step is wrong, and the text "
    "contains no logicalThinking:\nThe solution defines PLR correctly, then"
)


def _kind_of(text: str, *, solo: bool = False) -> str:
    from exp2.arms import _split_solo

    parse = _split_solo if solo else parse_debater_output
    with pytest.raises(MalformedOutputError) as caught:
        parse(text)
    return caught.value.kind


def test_every_refusal_names_the_shape_it_refused():
    """One repair attempt is all there is, so it has to be aimed. These are the shapes
    it is aimed at, and they are the ones pilot-2 actually produced."""
    assert _kind_of(THINKING_ONLY, solo=True) == "no_public_label"
    assert _kind_of(GLUED_LABEL, solo=True) == "label_not_at_line_start"
    assert _kind_of(XML_WRAPPED) == "xml_tag"
    assert _kind_of(THINKING_INSIDE) == "private_label_in_public"
    assert _kind_of("Thinking: a\nArgument:\nThinking: b") == "empty_public"
    assert _kind_of("no labels here at all") == "no_labels_at_all"
    assert MalformedOutputError("m").kind == "other"


def test_ordinary_prose_is_not_mistaken_for_a_misplaced_label():
    """`_INLINE_LABEL_RE` requires the label to be GLUED to the character before it,
    which is the measured shape. A sentence that merely uses the word would otherwise
    be told where to put a label it never wrote."""
    assert _kind_of("Thinking:\nHere is my reasoning: the integral diverges.",
                    solo=True) == "no_public_label"


def test_the_kind_vocabulary_is_closed():
    """A typo'd kind would silently fall through to the per-role instruction and the
    aiming would quietly stop happening."""
    with pytest.raises(ValueError, match="unknown malformed-output kind"):
        MalformedOutputError("m", kind="no_public_lable")


def test_the_two_aimed_repairs_ask_for_the_public_section_and_nothing_else():
    """A model that has just filed everything under Thinking, told to "reply again with
    exactly two labelled sections", writes two sections the same way again — pilot-2's
    15 repair replies are the evidence. So the second attempt asks for the one section
    that can be published, which `salvaged_no_thinking` already accepts."""
    for role, label in (("debater", "Argument"), ("solo", "Reasoning"),
                        ("critic", "Reasoning"), ("challenger", "Argument"),
                        ("recourse_solo", "Reasoning")):
        aimed = repair_instruction_for(role, 400, "no_public_label")
        assert "had only a Thinking section" in aimed
        assert f"begin your reply with the line `{label}:`" in aimed
        assert "do not write a Thinking section" in aimed
        for kind in ("label_not_at_line_start", "private_label_in_public", "xml_tag"):
            placed = repair_instruction_for(role, 400, kind)
            assert f"must begin on its own line with `{label}:`" in placed
            assert f"Reply now with **only** the {label} section." in placed


def test_each_aimed_repair_still_asks_for_the_line_the_role_owes():
    """Repairing the format by dropping the content would trade one refusal for
    another: a solo reply with no `Verdict:` line is refused just as surely."""
    assert "Verdict: FLAWED" in repair_instruction_for("solo", 400, "no_public_label")
    assert "Verdict: FLAWED" in repair_instruction_for("recourse_solo", 400, "xml_tag")
    assert "Objection: <RAISED|NONE>" in repair_instruction_for(
        "challenger", 400, "no_public_label")
    assert "within the stated word limit" in repair_instruction_for(
        "debater", 400, "no_public_label")
    assert "concisely" in repair_instruction_for("debater", 0, "no_public_label")
    # the critic is the one role that must NOT be asked for a verdict
    critic = repair_instruction_for("critic", 400, "no_public_label")
    assert "Do not give a verdict" in critic and "Verdict:" not in critic


def test_a_shape_with_no_aimed_repair_gets_exactly_the_old_instruction():
    """The fallback is the whole safety of this change: an unclassified failure is told
    what it was told before the kinds existed."""
    for role in REPAIR_INSTRUCTIONS:
        base = repair_instruction_for(role, 400)
        for kind in ("other", "empty_public", "no_labels_at_all",
                     "missing_decision_line", None):
            assert repair_instruction_for(role, 400, kind) == base
    # and the roles that emit a decision line and no public section are never aimed
    for role in ("judge", "recourse_judge", "comprehension", "grader"):
        assert repair_instruction_for(role, 400, "no_public_label") == (
            repair_instruction_for(role, 400))


def test_a_public_only_reply_is_what_the_aimed_repair_can_actually_get():
    """The aimed instruction asks for a reply with no Thinking section. If that did not
    parse, the repair would be asking for a response the parser then refuses — exp1's
    mistake, and the reason this is a test rather than a comment."""
    from exp2.arms import _parse_solo

    _, argument, mode = parse_debater_output("Argument: The step is wrong.")
    assert (argument, mode) == ("The step is wrong.", "salvaged_no_thinking")
    _, reasoning, verdict, mode = _parse_solo(
        "Reasoning: The sentence misstates the rule.\n\nVerdict: FLAWED")
    assert verdict == "FLAWED" and mode == "salvaged_no_thinking"
    assert reasoning.startswith("The sentence misstates the rule.")


def test_length_rule_and_clause_handle_the_no_cap_case():
    assert "at most 400 words per argument" in length_rule(400)
    assert "no word limit" in length_rule(0)
    assert length_clause(400) == "within the stated word limit"
    assert length_clause(0) == "concisely"


def test_side_phrase_refuses_a_word_outside_the_vocabulary():
    assert side_phrase(FLAWED) == FLAW_PHRASE and side_phrase(SOUND) == SOUND_PHRASE
    with pytest.raises(ValueError):
        side_phrase("YES")


def test_every_round_bounds_deliberation_and_none_of_them_offers_a_concession():
    """The pilot's commonest runaway was a debater assigned the pro-flaw side of a sound
    item, deliberating for ever because there is no honest flaw to find. The bound is
    symmetric on purpose: a concede option would be reachable only from the pro-flaw
    side, i.e. only on sound items, which leaks the gold label through the protocol."""
    config = make_config()
    texts = [_round_instructions(config, speaker=Speaker.ALICE, round_number=r)
             for r in (1, 2, 3)]
    for text in texts:
        assert "do not search exhaustively, and do not restart" in text
        # the bound sits in the Thinking directive, before the Argument is asked for
        assert text.index("do not restart") < text.index("under Argument")
        for word in ("concede", "concession", "withdraw", "may agree"):
            assert word not in text.lower()
    # identical wording in all three, so neither side is bounded differently by round
    assert len({t.split("Decide what to argue")[1] for t in texts}) == 3  # tails differ
    assert all(t.count("Decide what to argue quickly") == 1 for t in texts)
