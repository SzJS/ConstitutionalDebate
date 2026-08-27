"""Contesting a decision — the part exp1 never implemented properly."""

from __future__ import annotations

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import make_config
from recording import contest, decided

from exp2.arms import DECIDERS
from exp2.recourse import RECOURSERS, recoursers_for, run_recourse
from exp2.types import FLAWED, SOUND


# --- the two mechanisms --------------------------------------------------------------


async def test_every_condition_has_exactly_one_recourse_mechanism():
    assert set(RECOURSERS) == set(DECIDERS)
    assert RECOURSERS["debate"].__name__ == "_rule_by_judge"
    assert RECOURSERS["single"] is RECOURSERS["self_critique"]


async def test_each_recourse_form_covers_every_condition():
    """A form that omitted a condition would fail at the cell rather than at the config,
    hours into a sweep."""
    for form in ("per_condition", "third_party", "in_conversation"):
        assert set(recoursers_for(form)) == set(DECIDERS)
    assert recoursers_for("per_condition") is RECOURSERS
    with pytest.raises(ValueError, match="unknown recourse_form"):
        recoursers_for("whatever")


async def test_third_party_sends_a_solo_objection_to_the_recourse_judge(tmp_path):
    """The settled protocol: the appeal is heard by a weak party that did not decide.
    Under the historical routing this same cell is re-decided by the model that decided
    it, and the sweep measured the two forms disagreeing about 20 points of the phantom
    objections they were handed."""
    config = make_config(recourse_form="third_party")
    outcome, client, _, _ = await contest(tmp_path, "single", config=config)
    assert outcome.ruling.form == "stated_conclusion"
    assert outcome.ruling.protocol == "judge_only"
    assert "recourse_judge" in client.roles()
    assert "recourse_solo" not in client.roles()
    # and the judge is shown the SOLO record, not a debate it never had
    sent = "".join(m["content"] for m in client.sent_to("recourse_judge"))
    assert "No debaters were assigned and nobody argued a position" in sent


async def test_third_party_leaves_the_debate_condition_where_it_already_was(tmp_path):
    config = make_config(recourse_form="third_party")
    outcome, client, _, _ = await contest(tmp_path, "debate", config=config)
    assert outcome.ruling.form == "stated_conclusion"
    assert "recourse_judge" in client.roles()


async def test_in_conversation_refuses_the_debate_condition(tmp_path):
    """There is no single decider whose conversation could be replayed. Falling back to
    the judge would make the ablation mean "third_party for debate", which is the
    conflation the form exists to separate."""
    config = make_config(recourse_form="in_conversation")
    with pytest.raises(ValueError, match="no single decider"):
        await contest(tmp_path, "debate", config=config)


async def test_in_conversation_keeps_the_solo_conditions_in_their_conversation(tmp_path):
    config = make_config(recourse_form="in_conversation")
    outcome, client, _, _ = await contest(tmp_path, "self_critique", config=config)
    assert outcome.ruling.form == "restated_verdict"
    assert "recourse_solo" in client.roles()


async def test_debate_is_ruled_by_a_judge_who_did_not_decide(tmp_path):
    outcome, client, _, _ = await contest(tmp_path, "debate")
    assert outcome.ruling.form == "stated_conclusion"
    assert outcome.ruling.protocol == "judge_only"
    assert outcome.ruling.ruling in ("UPHOLD", "OVERTURN")
    assert "recourse_judge" in client.roles()
    # judge-only: no debater speaks in the contest
    assert "debater" not in client.roles()


async def test_the_derived_verdict_follows_from_the_ruling(tmp_path):
    outcome, _, _, record = await contest(tmp_path, "debate")
    # the fake recourse judge concludes the text is SOUND against a FLAWED decision
    assert outcome.ruling.ruling == "OVERTURN"
    assert outcome.ruling.verdict != record.verdict.verdict
    assert outcome.ruling.changed_the_decision is True


async def test_the_judge_states_a_conclusion_and_the_ruling_word_is_derived(tmp_path):
    """The judge is never asked whether to uphold or overturn. The re-contest measured
    what asking cost: 8 of 12 hand-checked rulings on FLAWED parents ended on a line that
    contradicted the judge's own reasoning, because "the objection is valid" and "the
    text is flawed" both land on OVERTURN."""
    from exp2.types import resolve_ruling

    outcome, client, _, record = await contest(tmp_path, "debate")
    ruling = outcome.ruling
    assert ruling.form == "stated_conclusion"
    assert ruling.conclusion_line == (
        "Conclusion: the original text in <solution> does not contain a flaw")
    assert ruling.verdict == "SOUND"          # what the judge actually said
    assert ruling.ruling == "OVERTURN"        # what follows, given a FLAWED decision
    assert resolve_ruling(ruling.ruling, ruling.parent_verdict) == ruling.verdict
    # and the relative word never appears in what the judge was asked
    sent = "".join(m["content"] for m in client.sent_to("recourse_judge"))
    assert "UPHOLD" not in sent and "OVERTURN" not in sent
    assert "You are judging the TEXT, not the thing it assesses" in sent


async def test_a_judge_that_agrees_with_the_decision_upholds_it(tmp_path):
    """The other half of the derivation, and the half the old line got wrong: the same
    conclusion means UPHOLD or OVERTURN depending on the decision, and the comparison is
    now made in code rather than by a weak model."""
    client = FakeClient(replies={
        "recourse_judge": ("The objection does not land.\n"
                           "Conclusion: the original text in <solution> contains a flaw"),
    })
    outcome, _, _, record = await contest(tmp_path, "debate", client=client)
    assert record.verdict.verdict == "FLAWED"
    assert outcome.ruling.verdict == "FLAWED"
    assert outcome.ruling.ruling == "UPHOLD"
    assert outcome.ruling.changed_the_decision is False


async def test_a_ruling_document_says_the_judge_stated_its_own_conclusion(tmp_path):
    """This sentence is the account a stakeholder is handed of how their objection was
    heard, and "upheld" now means something the judge did not itself write."""
    _, _, writer, _ = await contest(tmp_path, "debate")
    document = (writer.dir / "transcript.md").read_text()
    assert ("*Ruled on by a judge who did not make the original decision. The judge "
            "stated its own conclusion about the text under review; the decision was "
            "upheld/overturned by comparing the two.*") in document
    full = (writer.dir / "transcript_full.md").read_text()
    assert "ruling (recourse judge, stated conclusion)" in full


async def test_the_ruling_agreement_reader_measures_the_line_against_the_prose(tmp_path):
    """The residual instrument. The smoke put the new line's contradiction rate at 1 in
    20 rather than 8 — but a residual nobody measures is a residual nobody can bound, and
    every revised_* rate in the experiment is bounded by this one."""
    from exp2.config import GradingConfig
    from exp2.recourse import judge_ruling_prose

    outcome, _, _, _ = await contest(tmp_path, "debate")
    client = FakeClient()
    reading = await judge_ruling_prose(
        outcome.ruling, config=make_config(), grading=GradingConfig(), client=client)
    assert reading.prose_conclusion == "SOUND"
    assert reading.line_conclusion == outcome.ruling.verdict == "SOUND"
    assert reading.mismatch is False
    assert reading.ruling_form == "stated_conclusion"
    assert client.roles() == ["ruling_reader"]
    assert client.temperature_for("ruling_reader") == 0.0
    # the reader sees the judge's prose and no decision line of any vocabulary
    sent = "".join(m["content"] for m in client.sent_to("ruling_reader"))
    assert "The objection identifies a real error." in sent
    assert "Conclusion:" not in sent and "Ruling:" not in sent


async def test_the_ruling_agreement_reader_catches_a_line_its_prose_contradicts(tmp_path):
    """The failure it exists to count, and the one the hand check found 8 of in 12: the
    reasoning concludes the text is flawed and the record says the verdict is SOUND."""
    from exp2.config import GradingConfig
    from exp2.recourse import judge_ruling_prose

    outcome, _, _, _ = await contest(tmp_path, "debate")
    client = FakeClient(replies={
        "ruling_reader": "It finds a real error in step 2.\nReading: FLAWED"})
    reading = await judge_ruling_prose(
        outcome.ruling, config=make_config(), grading=GradingConfig(), client=client)
    assert reading.prose_conclusion == "FLAWED"
    assert reading.line_conclusion == "SOUND"
    assert reading.mismatch is True


async def test_a_solo_contest_replays_the_recorded_conversation(tmp_path):
    """Rebuilding the prompt instead would make this a fresh judgement by a model that
    merely shares a name with the decider — a different mechanism."""
    outcome, client, _, record = await contest(tmp_path, "self_critique")
    assert outcome.ruling.form == "restated_verdict"
    assert outcome.ruling.protocol == "in_conversation"
    sent = client.sent_to("recourse_solo")
    assert sent[: len(record.messages)] == record.messages
    assert len(sent) == len(record.messages) + 1
    assert sent[-1]["role"] == "user"


async def test_the_recourse_replay_restates_the_format_after_a_repaired_decision(tmp_path):
    """The path where the scar mattered most. `_rule_in_conversation` replays the
    conversation verbatim, so a repair's "do not write a Thinking section" is still in
    context — and this call is the one that produces `changed_the_decision`. `single`
    has one stage, so no next-stage reminder can ever reach it."""
    from exp2.prompts import REPAIR_CARRYOVER_PREFIX

    decider = FakeClient(
        fail_on={("solo", "answer"): "malformed"},
        malformed_content=("Thinking:\nEverything filed here, verdict and all.\n\n"
                           "Verdict: FLAWED"),
    )
    _, client, _, _ = await contest(tmp_path, "single", decider=decider)
    appended = client.sent_to("recourse_solo")[-1]["content"]
    assert appended.startswith(REPAIR_CARRYOVER_PREFIX)
    assert "A stakeholder has read your published reasoning" in appended


async def test_the_recourse_replay_is_byte_identical_when_no_repair_happened(tmp_path):
    """Conditional, or every solo contest in the experiment changes to fix a thing that
    happens in a fifth of them."""
    from exp2.prompts import REPAIR_CARRYOVER_PREFIX

    _, client, _, _ = await contest(tmp_path, "single")
    appended = client.sent_to("recourse_solo")[-1]["content"]
    assert REPAIR_CARRYOVER_PREFIX not in appended
    assert appended.startswith("A stakeholder has read your published reasoning")


async def test_a_solo_rulings_grounds_exclude_the_deciders_private_thinking(tmp_path):
    """The ruling is a solo-format reply, so everything before the verdict line is the
    Thinking block as well as the reasoning. Publishing that as "Grounds given" would
    leak exactly what the two-section protocol exists to contain."""
    outcome, _, writer, _ = await contest(tmp_path, "single")
    assert outcome.ruling.reasoning == "I was wrong."
    assert "reconsidering" not in (writer.dir / "transcript.md").read_text()


async def test_a_solo_contest_without_a_conversation_is_refused(tmp_path):
    record = await decided(tmp_path, "single")
    stripped = type(record)(**{**record.__dict__, "messages": None})
    with pytest.raises(ValueError, match="no conversation.json"):
        await run_recourse(stripped, make_config(), FakeClient())


# --- declining -----------------------------------------------------------------------


DECLINE = "Thinking: I read it.\nArgument: The grounds check out.\nDecision: STANDS"


async def test_a_decline_seeks_no_ruling_and_writes_no_ruling_file(tmp_path):
    """The absence of ruling.json is what distinguishes "never objected to" from
    "survived an objection"."""
    client = FakeClient(replies={"challenger": DECLINE})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.raised is False
    assert outcome.ruling is None
    assert not (writer.dir / "ruling.json").is_file()
    assert "recourse_judge" not in client.roles()


async def test_comprehension_is_still_asked_after_a_decline(tmp_path):
    """It asks whether the record could be followed, not whether fault was found."""
    client = FakeClient(replies={"challenger": DECLINE})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.comprehension is not None
    assert outcome.comprehension.asked_after_decline is True
    assert (writer.dir / "comprehension.json").is_file()


# --- the three stances ---------------------------------------------------------------
#
# The challenger's replies, in their measured shapes. Pilot 1's instruction — "RAISED if
# the decision rests on an error" — was satisfied by agreeing with a FLAWED verdict.
# Pilot 2 added a claimed verdict beside it and that word collided with the challenger's
# own vocabulary. The line is now one token stated relative to the decision, so
# `raised`, `stance` and the verdict being asked for are all one answer — and the
# `agrees` stance it used to detect is unreachable, which is why the `agreement` stage
# exists.

# The measured shape: no Thinking:/Argument: labels anywhere (118 of 120 pilot replies).
CONTESTS = ("The claimed flaw in step 2 is not one; the identity holds.\n"
            "Decision: REVERSE")
DECLINES = ("The decision correctly identifies the error in step 2.\n"
            "Decision: STANDS")
UNCLEAR = "I have several concerns about how this decision was reached."


async def test_a_contesting_objection_is_the_only_stance_that_seeks_a_ruling(tmp_path):
    """The fake judge decides FLAWED, so a claimed SOUND is a genuine contest."""
    client = FakeClient(replies={"challenger": CONTESTS})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.stance == "contests"
    assert outcome.challenge.claimed_verdict == SOUND
    assert outcome.ruling is not None
    assert (writer.dir / "ruling.json").is_file()
    assert "recourse_judge" in client.roles()
    # the claimed-verdict line is not in the text handed to the recourse judge
    assert "Decision: REVERSE" not in outcome.challenge.text
    assert "Decision: REVERSE" not in "".join(
        m["content"] for m in client.sent_to("recourse_judge"))


async def test_a_stands_reply_declines_and_seeks_no_ruling(tmp_path):
    """The verdict it is asking for is DERIVED from the line, not named by the model.
    Naming it is what pilot 2 did, and the challenger reused the word SOUND for two
    different propositions."""
    client = FakeClient(replies={"challenger": DECLINES})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.raised is False
    assert outcome.challenge.stance == "declined"
    assert outcome.challenge.claimed_verdict == FLAWED  # the fake judge decided FLAWED
    assert outcome.ruling is None
    assert not (writer.dir / "ruling.json").is_file()
    assert "recourse_judge" not in client.roles()
    assert outcome.comprehension.asked_after_decline is True


async def test_an_unclear_objection_seeks_no_ruling_and_is_not_fatal(tmp_path):
    client = FakeClient(replies={"challenger": UNCLEAR})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.stance == "unclear"
    assert outcome.challenge.claimed_verdict is None
    assert outcome.ruling is None
    assert "recourse_judge" not in client.roles()


async def test_the_agreeing_stance_is_unreachable_and_says_so(tmp_path):
    """One relative line cannot both ask for a reversal and name the verdict it is
    reversing to, so `agrees` and `contradictory` can no longer occur. They are recorded
    as False rather than dropped: a column that reads 0 says the shape did not happen,
    a column that is absent says nobody looked."""
    for reply in (CONTESTS, DECLINES):
        client = FakeClient(replies={"challenger": reply})
        outcome, _, _, _ = await contest(tmp_path / reply[:16], "debate", client=client)
        assert outcome.challenge.stance in ("contests", "declined")
        assert outcome.challenge.contradictory is False


async def test_a_challenger_reply_unparsable_after_repair_is_unclear_not_fatal(tmp_path):
    """The challenger is the experiment's subject. Making an unreadable reply fatal
    would let the role under measurement lose an entire contest to a DebateFailure."""
    client = FakeClient(replies={"challenger": "Thinking: private, and no Argument label."})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.stance == "unclear"
    assert outcome.challenge.repair_attempts == 1
    # it marked text private and the boundary is unknown, so the public text is withheld
    assert outcome.challenge.parse_mode == "unparsed_unclear_withheld"
    assert "private, and no Argument label" not in outcome.challenge.text
    assert "private, and no Argument label" in outcome.challenge.raw
    assert outcome.ruling is None


async def test_the_contest_document_says_when_the_line_could_not_be_read(tmp_path):
    client = FakeClient(replies={"challenger": UNCLEAR})
    _, _, writer, _ = await contest(tmp_path, "debate", client=client)
    document = (writer.dir / "transcript.md").read_text()
    assert "without saying which verdict" in document
    assert "excluded from the rates" in document


async def test_the_challenger_runs_at_its_own_temperature(tmp_path):
    """It ran at debater_temperature by inheritance until 2026-08-25 — same value, no
    field. The comprehension probe beside it is a measurement and stays at 0."""
    config = make_config(challenger_temperature=0.55, debater_temperature=0.11)
    _, client, _, _ = await contest(tmp_path, "debate", config=config)
    assert client.temperature_for("challenger") == 0.55
    assert client.temperature_for("comprehension") == 0.0


async def test_comprehension_is_asked_in_the_challengers_conversation(tmp_path):
    outcome, client, _, _ = await contest(tmp_path, "debate")
    challenger_messages = client.sent_to("challenger")
    comprehension_messages = client.sent_to("comprehension")
    assert comprehension_messages[: len(challenger_messages)] == challenger_messages
    assert comprehension_messages[-2]["role"] == "assistant"  # the objection itself
    assert outcome.comprehension.asked_after_decline is False
    assert outcome.comprehension.score == 4


# --- what the contest is shown -------------------------------------------------------


async def test_the_challenger_and_the_recourse_judge_see_the_same_record(tmp_path):
    _, client, _, record = await contest(tmp_path, "debate")
    body = record.challenger_view().body
    assert body in "".join(m["content"] for m in client.sent_to("challenger"))
    assert body in "".join(m["content"] for m in client.sent_to("recourse_judge"))


async def test_a_solo_parent_is_never_described_to_the_challenger_as_a_debate(tmp_path):
    """exp1's bug: a solo decision was announced with "Alice argues for 1" in a run
    where nobody argued."""
    _, client, _, _ = await contest(tmp_path, "single")
    prompt = "".join(m["content"] for m in client.sent_to("challenger"))
    assert "No debaters were assigned and nobody argued a position" in prompt
    assert "Alice" not in prompt and "Bob" not in prompt


async def test_the_challenger_is_not_shown_the_deciders_private_thinking(tmp_path):
    _, client, _, _ = await contest(tmp_path, "single")
    prompt = "".join(m["content"] for m in client.sent_to("challenger"))
    assert SOLO_THINKING not in prompt


# --- the published contest document --------------------------------------------------


async def test_the_contest_document_reports_a_decline_as_a_decline(tmp_path):
    client = FakeClient(replies={"challenger": DECLINE})
    _, _, writer, _ = await contest(tmp_path, "debate", client=client)
    document = (writer.dir / "transcript.md").read_text()
    assert "The stakeholder declined to object" in document
    assert "is not the same as one that survived an objection" in document


async def test_the_contest_document_names_which_mechanism_ruled(tmp_path):
    _, _, debate_writer, _ = await contest(tmp_path / "a", "debate")
    _, _, solo_writer, _ = await contest(tmp_path / "b", "single")
    debate_doc = (debate_writer.dir / "transcript.md").read_text()
    solo_doc = (solo_writer.dir / "transcript.md").read_text()
    assert "judge who did not make the original decision" in debate_doc
    assert "same reviewer that made the decision, in the same conversation" in solo_doc


async def test_the_contest_document_ends_with_the_ground_truth(tmp_path):
    """Same rule as a decision record: the answer is last, and nowhere above it."""
    _, _, writer, record = await contest(tmp_path, "debate")
    document = (writer.dir / "transcript.md").read_text()
    head, marker, tail = document.rpartition("\n## Ground truth")
    assert marker
    assert "\n## " not in tail
    for leak in ("gold", "ground truth", "label_basis"):
        assert leak not in head.lower()
    assert record.item.gold_verdict in tail


async def test_the_contest_record_carries_a_hash_of_the_decision_it_contests(tmp_path):
    import json
    _, _, writer, _ = await contest(tmp_path, "debate")
    manifest = json.loads((writer.dir / "run.json").read_text())
    assert manifest["parent_sha256"]
    assert (writer.dir / "parent" / "transcript.md").is_file()
