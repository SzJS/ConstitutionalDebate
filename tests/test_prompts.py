"""Prompt rendering, profile selection, leak invariants, and parsing."""

from __future__ import annotations

import pytest

from constitutional_debate.config import DebateConfig
from constitutional_debate.prompts import (
    CONSTITUTIONAL,
    OPINION,
    PAPER,
    MalformedOutputError,
    build_debater_messages,
    build_judge_messages,
    build_repair_messages,
    parse_debater_output,
    parse_judge_output,
    response_states_grounds,
    select_profile,
)
from constitutional_debate.types import (
    ORDER,
    Context,
    Speaker,
    Task,
    Transcript,
)

from helpers import (  # noqa: E402 - tests/ is on sys.path under pytest
    CONSTITUTION_TEXT,
    config,
    full_transcript,
    make_seating,
    make_task,
    make_turn,
)

__all__ = [
    "CONSTITUTION_TEXT",
    "config",
    "full_transcript",
    "make_seating",
    "make_task",
    "make_turn",
]


def all_rendered_prompts(
    task: Task, context: Context | None, cfg: DebateConfig
) -> list[str]:
    """Every prompt string this run would ever send, across roles and rounds."""
    seating = make_seating()
    transcript = full_transcript(cfg.n_rounds)
    rendered: list[str] = []
    for round_number in range(1, cfg.n_rounds + 1):
        for speaker in ORDER:
            rendered += [
                m["content"]
                for m in build_debater_messages(
                    task,
                    context,
                    seating,
                    cfg,
                    transcript,
                    speaker=speaker,
                    round=round_number,
                )
            ]
    rendered += [
        m["content"]
        for m in build_judge_messages(task, context, seating, cfg, transcript)
    ]
    return rendered


# --------------------------------------------------------------------------- #
# profile selection
# --------------------------------------------------------------------------- #


def test_profile_selection():
    constitution = Context(kind="constitution", text=CONSTITUTION_TEXT)
    assert select_profile(make_task(), None) is OPINION
    assert select_profile(make_task(gold_index=0), None) is PAPER
    # A constitution wins regardless of whether the task has a gold answer.
    assert select_profile(make_task(), constitution) is CONSTITUTIONAL
    assert select_profile(make_task(gold_index=0), constitution) is CONSTITUTIONAL


def test_no_constitution_means_no_constitutional_language_anywhere():
    """The constitution is optional, and absence must be total."""
    for task in (make_task(), make_task(gold_index=0)):
        for prompt in all_rendered_prompts(task, None, config()):
            lowered = prompt.lower()
            assert "constitution" not in lowered
            assert "provision" not in lowered
            assert "§" not in prompt


def test_constitutional_profile_without_a_constitution_is_refused():
    """Otherwise the prompts name a constitution that was never supplied."""
    with pytest.raises(ValueError, match="requires a constitution"):
        build_judge_messages(
            make_task(), None, make_seating(), config(), full_transcript(),
            profile=CONSTITUTIONAL,
        )
    with pytest.raises(ValueError, match="requires a constitution"):
        build_debater_messages(
            make_task(), None, make_seating(), config(), Transcript(),
            speaker=Speaker.ALICE, round=1, profile=CONSTITUTIONAL,
        )


def test_constitution_reaches_both_debaters_and_judge():
    constitution = Context(kind="constitution", text=CONSTITUTION_TEXT)
    prompts = all_rendered_prompts(make_task(), constitution, config())
    assert all(
        CONSTITUTION_TEXT in p
        for p in prompts
        if "<question>" in p or "Question:" in p
    ), "the constitution is public by construction — every user prompt carries it"

    judge = build_judge_messages(
        make_task(), constitution, make_seating(), config(), full_transcript()
    )
    assert CONSTITUTION_TEXT in judge[1]["content"]
    assert "only standard you may apply" in judge[0]["content"]


def test_paper_and_opinion_differ_only_in_framing():
    task_paper, task_opinion = make_task(gold_index=0), make_task()
    paper = build_judge_messages(
        task_paper, None, make_seating(), config(), full_transcript()
    )
    opinion = build_judge_messages(
        task_opinion, None, make_seating(), config(), full_transcript()
    )
    assert "determine which debater is right" in paper[0]["content"]
    assert "stronger case" in opinion[0]["content"]
    assert "no established correct answer" in opinion[0]["content"]


# --------------------------------------------------------------------------- #
# leak invariants
# --------------------------------------------------------------------------- #


def test_which_answer_is_gold_changes_no_prompt():
    """The strongest form of "gold never reaches a prompt".

    Both answer texts must of course appear — the debate is about them. What may
    never appear is any signal of *which* one is correct, so flipping gold_index
    must leave every rendered prompt identical. Nothing on the record side
    checks this, so this test is the whole of the guarantee.
    """
    cfg = config()
    gold_first = all_rendered_prompts(make_task(gold_index=0), None, cfg)
    gold_second = all_rendered_prompts(make_task(gold_index=1), None, cfg)
    assert gold_first == gold_second

    for prompt in gold_first:
        assert "gold" not in prompt.lower()
        assert "correct answer is" not in prompt.lower()


def test_private_thinking_never_reaches_opponent_or_judge():
    task, cfg = make_task(), config()
    for prompt in all_rendered_prompts(task, None, cfg):
        assert "SECRET-THINKING" not in prompt


def test_debater_sees_own_assigned_answer_only_as_assignment():
    seating = make_seating()
    messages = build_debater_messages(
        make_task(),
        None,
        seating,
        config(),
        Transcript(),
        speaker=Speaker.BOB,
        round=1,
    )
    user = messages[1]["content"]
    assert "<your_answer>It is NOT OK to use tax havens.</your_answer>" in user
    assert "<opponent_answer>It is OK to use tax havens.</opponent_answer>" in user
    assert "Alice argues for the answer in <opponent_answer>" in user


# --------------------------------------------------------------------------- #
# round-specific and judge rendering
# --------------------------------------------------------------------------- #


def test_round_instructions_shift_by_round():
    task, cfg, transcript = make_task(), config(n_rounds=3), full_transcript()
    texts = [
        build_debater_messages(
            task, None, make_seating(), cfg, transcript,
            speaker=Speaker.ALICE, round=r,
        )[1]["content"]
        for r in (1, 2, 3)
    ]
    assert "opening argument" in texts[0]
    assert "what context the judge needs" in texts[0]
    assert "next argument" in texts[1]
    assert "biggest flaws in Bob's argument" in texts[1]
    assert "critiques Bob has made of your argument" in texts[2]


def test_final_round_drops_the_further_rounds_follow_clause():
    task, cfg, transcript = make_task(), config(n_rounds=3), full_transcript()
    early = build_debater_messages(
        task, None, make_seating(), cfg, transcript, speaker=Speaker.ALICE, round=1
    )[0]["content"]
    final = build_debater_messages(
        task, None, make_seating(), cfg, transcript, speaker=Speaker.ALICE, round=3
    )[0]["content"]
    assert "further rounds follow" in early
    assert "further rounds follow" not in final, "it is false in the last round"


def test_judge_choice_header_follows_choice_order_not_transcript_order():
    """Alice speaks first; choice 1 may still be Bob's answer."""
    task = make_task()
    judge = build_judge_messages(
        task, None, make_seating(choice_order=(1, 0)), config(), full_transcript()
    )[1]["content"]

    assert "1: It is NOT OK to use tax havens." in judge
    assert "2: It is OK to use tax havens." in judge
    assert "Bob argues for 1. Alice argues for 2." in judge
    # ...and the transcript still opens with Alice.
    assert judge.index("Alice: Alice public argument r1") < judge.index(
        "Bob: Bob public argument r1"
    )


def test_judge_cot_switches_the_closing_instruction():
    task, transcript = make_task(), full_transcript()
    predict = build_judge_messages(
        task, None, make_seating(), config(judge_cot=False), transcript
    )[1]["content"]
    cot = build_judge_messages(
        task, None, make_seating(), config(judge_cot=True), transcript
    )[1]["content"]
    assert "Do not explain your reasoning." in predict
    assert "First explain your reasoning" in cot
    assert "Answer: <1|2>" in predict and "Answer: <1|2>" in cot


def test_word_limit_is_interpolated_and_profile_overridable():
    cfg = config(word_limit_by_profile={"constitutional": 250})
    constitution = Context(kind="constitution", text=CONSTITUTION_TEXT)

    plain = build_debater_messages(
        make_task(), None, make_seating(), cfg, Transcript(),
        speaker=Speaker.ALICE, round=1,
    )
    assert "at most 150 words" in plain[0]["content"]
    assert "at most 150 words" in plain[1]["content"]

    constitutional = build_debater_messages(
        make_task(), constitution, make_seating(), cfg, Transcript(),
        speaker=Speaker.ALICE, round=1,
    )
    assert "at most 250 words" in constitutional[0]["content"]


def test_first_round_transcript_is_the_empty_placeholder():
    user = build_debater_messages(
        make_task(), None, make_seating(), config(), Transcript(),
        speaker=Speaker.ALICE, round=1,
    )[1]["content"]
    assert "no arguments have been made yet" in user


def test_repair_messages_append_the_bad_reply_and_a_correction():
    original = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    repaired = build_repair_messages(
        original, "garbage", role="debater", word_limit=150
    )
    assert repaired[:2] == original
    assert repaired[2] == {"role": "assistant", "content": "garbage"}
    assert "Thinking:" in repaired[3]["content"]

    judge_repair = build_repair_messages(original, "garbage", role="judge")
    assert '"Answer: 1" or "Answer: 2"' in judge_repair[3]["content"]


# --------------------------------------------------------------------------- #
# parsing: debater
# --------------------------------------------------------------------------- #


def test_parses_the_normal_shape():
    thinking, argument, mode = parse_debater_output(
        "Thinking:\nI should open with context.\n\nArgument:\nTax havens are legal."
    )
    assert thinking == "I should open with context."
    assert argument == "Tax havens are legal."
    assert mode == "strict"


@pytest.mark.parametrize(
    "text",
    [
        "**Thinking:** plan\n\n**Argument:** the case",
        "### Thinking:\nplan\n\n### Argument:\nthe case",
        "> Thinking: plan\n> Argument: the case",
        "Thinking：plan\n\nArgument：the case",  # full-width colon
    ],
)
def test_tolerates_markdown_wrappers(text):
    _, argument, _ = parse_debater_output(text)
    assert "the case" in argument


def test_missing_thinking_is_salvaged():
    thinking, argument, mode = parse_debater_output("Argument: straight to the point")
    assert thinking == ""
    assert argument == "straight to the point"
    assert mode == "salvaged_no_thinking"


def test_missing_argument_raises_rather_than_leaking_thinking():
    with pytest.raises(MalformedOutputError, match="no 'Argument:' label"):
        parse_debater_output("Thinking: I will reason at length and then forget.")
    with pytest.raises(MalformedOutputError):
        parse_debater_output("No labels here at all.")


def test_empty_argument_section_raises():
    with pytest.raises(MalformedOutputError, match="empty"):
        parse_debater_output("Thinking: plan\n\nArgument:\n   \n")


def test_the_word_argument_inside_thinking_does_not_split_early():
    """Splitting on str.find would cut here and leak reasoning to the judge."""
    text = (
        "Thinking:\n"
        "My Argument: should lead with the fairness point.\n"
        "Then I will rebut.\n\n"
        "Argument:\nFairness favours my answer."
    )
    thinking, argument, _ = parse_debater_output(text)
    assert argument == "Fairness favours my answer."
    assert "should lead with the fairness point" in thinking


def test_argument_label_before_thinking_still_uses_the_later_argument():
    text = "Argument: premature\n\nThinking: plan\n\nArgument: the real one"
    thinking, argument, _ = parse_debater_output(text)
    assert argument == "the real one"
    assert thinking == "plan"


# The three cases below are verbatim label shapes observed from
# deepseek-v4-flash on live constitutional runs. They are the reason the parser
# tolerates a parenthetical and a doubled label.


# The three cases below are leaks found in code review: each one published a
# debater's private reasoning to the judge and the opponent.


def test_a_coda_after_the_argument_is_not_published():
    """Models append second thoughts; running to end-of-text would ship them."""
    text = (
        "Thinking: plan\n"
        "Argument: my public case\n"
        "Thinking: on reflection I should have conceded the fairness point"
    )
    thinking, argument, mode = parse_debater_output(text)
    assert argument == "my public case"
    assert "on reflection" not in argument
    assert mode.endswith("_trailing_dropped"), "dropping text must be visible"


def test_sections_in_the_wrong_order_do_not_publish_thinking():
    text = "Argument: public case\n\nThinking: my private strategy"
    thinking, argument, _ = parse_debater_output(text)
    assert argument == "public case"
    assert "private strategy" not in argument


def test_a_thinking_label_on_the_argument_line_raises():
    """The label regex is line-anchored, so an inline Thinking label hides.

    Without an explicit check this publishes the private text verbatim; the
    newline form below raises for a different reason (empty argument), so it
    does not cover this case.
    """
    with pytest.raises(MalformedOutputError, match="marked as private"):
        parse_debater_output(
            "Argument: Thinking: I must argue X though I believe Y."
        )


def test_a_thinking_label_immediately_after_argument_raises():
    """The redundant-label strip must never launder a Thinking label away."""
    with pytest.raises(MalformedOutputError):
        parse_debater_output(
            "Argument:\nThinking: I will argue X but the honest read is Y"
        )


def test_judge_restating_the_template_after_deciding():
    """`Answer: <1|2>` echoed after the verdict must not be read as a vote."""
    assert parse_judge_output("Answer: 2\n\n(format: Answer: <1|2>)")[0] == 2


def test_label_with_an_echoed_word_limit_parenthetical():
    text = (
        "Thinking:\nI will cite §2.2 and §4.1.\n\n"
        "Argument (150 words max):\nThe constitution requires weighing burdens."
    )
    thinking, argument, _ = parse_debater_output(text)
    assert argument == "The constitution requires weighing burdens."
    assert "§2.2" in thinking


def test_doubled_label_on_one_line():
    text = (
        "Thinking:\nplanning\n\n"
        "Argument (150 words max):Argument:\nThe constitution requires this."
    )
    _, argument, _ = parse_debater_output(text)
    assert argument == "The constitution requires this."


def test_a_restated_second_block_uses_the_final_argument():
    """A repaired reply sometimes restates the whole structure; the last stands."""
    text = (
        "Thinking:\nfirst pass\n\n"
        "Argument (150 words max):Thinking:\nsecond pass reasoning\n\n"
        "Argument:\nThe final public argument."
    )
    _, argument, mode = parse_debater_output(text)
    assert argument == "The final public argument."
    assert mode == "strict"


# --------------------------------------------------------------------------- #
# parsing: judge
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Answer: 1", 1),
        ("Answer: <2>", 2),
        ("**Answer:** 2", 2),
        ("answer:1", 1),
        ("Answer : 2", 2),
    ],
)
def test_judge_format_tolerance(text, expected):
    choice, reasoning, mode = parse_judge_output(text)
    assert choice == expected
    assert mode == "strict"
    assert reasoning == "", "a bare answer line states no grounds"


def test_judge_last_match_wins():
    """CoT replies echo the instruction before deciding; first-match is wrong."""
    text = (
        "I must reply formatted as Answer: <1|2>. Considering both cases, "
        "Alice's argument on fairness was weaker.\n\nAnswer: 2"
    )
    choice, reasoning, _ = parse_judge_output(text)
    assert choice == 2
    assert reasoning.startswith("I must reply")
    assert reasoning.endswith("was weaker."), (
        "an echoed template lands inside the reasoning; only the decisive "
        "match ends it"
    )


def test_judge_reasoning_is_captured_without_its_wrapper():
    choice, reasoning, _ = parse_judge_output(
        "Bob quoted §2 accurately and Alice did not.\n\n**Answer:** 2"
    )
    assert choice == 2
    assert reasoning == "Bob quoted §2 accurately and Alice did not."


def test_judge_reasoning_drops_a_combined_wrapper():
    """A wrapper's two halves are separated by a space; both must go."""
    assert (
        parse_judge_output("Bob quoted §2.\n\n#### **Answer:** 1")[1]
        == "Bob quoted §2."
    )
    assert parse_judge_output("Bob quoted §2.\n\n> Answer: 1")[1] == "Bob quoted §2."


def test_judge_reasoning_keeps_a_hash_that_is_part_of_the_prose():
    """Only a dangling wrapper is stripped, never a character the judge wrote."""
    assert (
        parse_judge_output("Bob's analogy was to C#.\n\nAnswer: 1")[1]
        == "Bob's analogy was to C#."
    )


def test_judge_reasoning_survives_the_strip_seam():
    """The audit compares a re-parse of the *unstripped* recorded body.

    ``Completion`` stores stripped content while the audit re-parses the raw
    response body, so the two only agree because the parser strips too. Without
    this, a judge reply with trailing whitespace would fail its own audit.
    """
    assert (
        parse_judge_output("  Bob quoted §2.\n\nAnswer: 1  \n")[1]
        == parse_judge_output("Bob quoted §2.\n\nAnswer: 1")[1]
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Answer: 1", False),
        ("**Answer:** 2", False),
        ("### Answer: 1", False),
        ("Answer: 2.", False),
        ("Bob quoted §2.\n\nAnswer: 1", True),
        ("Answer: 1\n\nBecause Bob quoted §2.", True),
    ],
)
def test_response_states_grounds_looks_past_the_answer_line(text, expected):
    """The renderer shows the whole response, so this asks about the whole of it."""
    assert response_states_grounds(text) is expected


def test_judge_reasoning_after_the_decision_is_not_captured():
    """Documented limitation: `raw` stays the complete record, not `reasoning`.

    A judge that decides before explaining leaves nothing before the decisive
    match, which is why the markdown artifact renders ``Verdict.raw``.
    """
    choice, reasoning, _ = parse_judge_output("Answer: 2\n\nBecause Bob cited §2.")
    assert choice == 2
    assert reasoning == ""


def test_naked_digit_is_rejected_not_guessed():
    with pytest.raises(MalformedOutputError, match="bare digit"):
        parse_judge_output("Alice made the stronger case.\n\n1")
    with pytest.raises(MalformedOutputError):
        parse_judge_output("I cannot decide between these two positions.")
