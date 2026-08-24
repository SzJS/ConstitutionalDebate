"""The challenger's decision line, and what a decline does to a contest.

The parser's direction of failure is the point: reading a restated template as
"NO" would under-report detection and make the mechanism look *less* contestable
than it is, so an ambiguous response is refused rather than guessed at.
"""

from __future__ import annotations

import json

import pytest

from constitutional_debate.prompts import (
    CHALLENGE_DECISION_INSTRUCTION,
    PROFILES,
    MalformedOutputError,
    build_challenger_messages,
    parse_challenge_output,
)
from constitutional_debate.types import DecisionRecord, Transcript

from helpers import config, make_seating, make_task


def parse(argument: str, thinking: str = "private plan"):
    return parse_challenge_output(f"Thinking: {thinking}\n\nArgument: {argument}")


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #


def test_a_raised_challenge_keeps_its_body_and_drops_the_decision_line():
    thinking, raised, text, mode = parse(
        "Challenge: YES\nThe decision relies on step 4, which divides by zero."
    )
    assert raised is True
    assert text == "The decision relies on step 4, which divides by zero."
    assert "Challenge:" not in text
    assert thinking == "private plan"
    assert mode == "strict"


def test_a_decline_is_recorded_with_the_reasoning_behind_it():
    """The text after a NO is the only evidence a decline was reasoned."""
    _, raised, text, _ = parse(
        "Challenge: NO\nBoth steps check out and the judge's grounds quote them."
    )
    assert raised is False
    assert text == "Both steps check out and the judge's grounds quote them."


@pytest.mark.parametrize(
    "line",
    [
        "Challenge: YES",
        "**Challenge:** YES",
        "Challenge:YES",
        "challenge: yes",
        "Challenge: <YES>",
    ],
)
def test_wrapped_and_lowercased_forms_are_accepted(line):
    assert parse(f"{line}\nThe grounds misread step 2.")[1] is True


def test_a_restated_template_is_refused_rather_than_read_as_no():
    """The load-bearing refusal.

    A challenger that echoes the instruction has not made a judgement. Reading
    "Challenge: <YES|NO>" as NO would count it as "no error detected", which
    biases the detection rate downwards — the one direction that would make the
    mechanism look worse than it is. Refusing costs the one repair attempt.
    """
    with pytest.raises(MalformedOutputError, match="Challenge"):
        parse("Challenge: <YES|NO>\nI would say something here.")


def test_prose_with_no_decision_line_is_refused():
    with pytest.raises(MalformedOutputError, match="Challenge"):
        parse("I think the decision is probably wrong, somewhere in step 4.")


def test_yes_with_nothing_after_it_is_refused():
    with pytest.raises(MalformedOutputError, match="no challenge after it"):
        parse("Challenge: YES")


def test_a_missing_argument_label_still_refuses_before_the_decision_line():
    """Containment first: the debater parser's leak rule still applies."""
    with pytest.raises(MalformedOutputError, match="Argument"):
        parse_challenge_output("Thinking: I plan to say the grounds are wrong.")


def test_the_decision_line_may_be_preceded_by_a_lead_in():
    _, raised, text, _ = parse("My review:\nChallenge: YES\nStep 4 is unsupported.")
    assert raised is True
    assert "My review:" in text and "Step 4 is unsupported." in text


# --------------------------------------------------------------------------- #
# the prompt
# --------------------------------------------------------------------------- #


def challenger_prompt(**kw) -> str:
    task = make_task(gold_index=0)
    seating = make_seating()
    overrides = {k: kw.pop(k) for k in list(kw) if k in {"challenge_word_limit"}}
    messages = build_challenger_messages(
        task, None, seating, config(**overrides),
        DecisionRecord.for_debate(Transcript()),
        arm=kw.pop("arm", "neutral"),
        visibility=kw.pop("visibility", "public"),
        decision_answer_index=0,
        decision_grounds="Alice was more specific.",
        profile=PROFILES["paper"],
        **kw,
    )
    return "\n".join(m["content"] for m in messages)


def test_the_decision_instruction_appears_only_when_declining_is_allowed():
    assert "Challenge: YES" in challenger_prompt(may_decline=True)
    assert "Challenge: YES" not in challenger_prompt(may_decline=False)


def test_the_stakeholder_arm_says_a_challenge_is_not_required():
    text = challenger_prompt(arm="neutral")
    assert "You are not required to find fault" in text
    # The false-positive control: a stated reason not to manufacture an
    # objection, without revealing how often decisions are actually sound.
    assert "wastes this process's time" in text
    assert "how often" not in text


def test_the_stakeholder_arm_invites_an_underspecified_objection():
    """Detection without articulation must be sayable, or it is unmeasurable."""
    text = challenger_prompt(arm="neutral")
    assert "cannot pin down exactly what" in text


# --------------------------------------------------------------------------- #
# what a decline does to a contest, end to end
# --------------------------------------------------------------------------- #

DECLINE = (
    "Thinking: I read the grounds and they track the transcript.\n\n"
    "Argument: Challenge: NO\nThe grounds quote both steps and follow from them."
)


async def test_a_decline_spends_no_ruling_call_and_writes_no_ruling(tmp_path):
    """The decisive property.

    Ruling on a challenge nobody made would put a manufactured objection in
    front of the judge and record an outcome for it. Worse, the funnel could
    then no longer tell a decision that *survived* contestation from one that
    was never contested — they would both be an UPHOLD.
    """
    from helpers import generated_challenge, recorded_recourse, recorded_run

    parent_writer, _ = await recorded_run(
        tmp_path, make_task(gold_index=0), config(), make_seating()
    )
    writer, result, client = await recorded_recourse(
        tmp_path,
        parent_writer,
        challenge=generated_challenge(arm="neutral"),
        scripted={"challenger": DECLINE},
    )

    assert result.ruling is None
    assert result.challenge.raised is False
    assert not (writer.dir / "ruling.json").is_file()
    assert (writer.dir / "challenge.json").is_file()
    assert json.loads((writer.dir / "challenge.json").read_text())["raised"] is False
    assert not any(
        c["meta"].get("role") == "recourse_judge" for c in client.calls
    ), "no ruling call may be spent on a challenge that was never raised"
    assert json.loads((writer.dir / "run.json").read_text())["status"] == "completed"


async def test_a_raised_challenge_still_reaches_a_ruling(tmp_path):
    """The control: the decline path must not have broken the ordinary one."""
    from helpers import generated_challenge, recorded_recourse, recorded_run

    parent_writer, _ = await recorded_run(
        tmp_path, make_task(gold_index=0), config(), make_seating()
    )
    writer, result, client = await recorded_recourse(
        tmp_path, parent_writer, challenge=generated_challenge(arm="neutral")
    )

    assert result.challenge.raised is True
    assert result.ruling is not None
    assert (writer.dir / "ruling.json").is_file()


# --------------------------------------------------------------------------- #
# the two challenger variants
# --------------------------------------------------------------------------- #


def test_the_partisan_arm_represents_the_side_that_lost():
    text = challenger_prompt(arm="partisan")
    assert "represent the side this decision went against" in text
    assert "You are an advocate, not a neutral reviewer" in text


def test_the_partisan_arm_may_still_decline():
    """Declining is retained so both variants share a funnel shape.

    A pure advocate would never decline, which would make detection
    unmeasurable by raise/decline and leave the false-alarm rate undefined for
    that arm — so the two variants could not be compared on the same metrics.
    """
    text = challenger_prompt(arm="partisan")
    assert "not obliged to manufacture a case" in text
    assert "Challenge: YES" in text, "the decision line is still offered"


def test_partisan_and_neutral_differ_only_in_stance():
    """Both invite an underspecified objection; only the standpoint changes."""
    partisan = challenger_prompt(arm="partisan")
    neutral = challenger_prompt(arm="neutral")
    for text in (partisan, neutral):
        assert "cannot pin down exactly what" in text
    assert "represent the side" in partisan and "represent the side" not in neutral
    assert "not required to find fault" in neutral


def test_the_bare_arm_is_kept_as_a_no_instruction_control():
    assert challenger_prompt(arm="bare").count("Write a challenge to this decision.") == 1
