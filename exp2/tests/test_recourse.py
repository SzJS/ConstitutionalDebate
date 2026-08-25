"""Contesting a decision — the part exp1 never implemented properly."""

from __future__ import annotations

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import make_config
from recording import contest, decided

from exp2.arms import DECIDERS
from exp2.recourse import RECOURSERS, run_recourse
from exp2.types import FLAWED, SOUND


# --- the two mechanisms --------------------------------------------------------------


async def test_every_condition_has_exactly_one_recourse_mechanism():
    assert set(RECOURSERS) == set(DECIDERS)
    assert RECOURSERS["debate"].__name__ == "_rule_by_judge"
    assert RECOURSERS["single"] is RECOURSERS["self_critique"]


async def test_debate_is_ruled_by_a_judge_who_did_not_decide(tmp_path):
    outcome, client, _, _ = await contest(tmp_path, "debate")
    assert outcome.ruling.form == "uphold_overturn"
    assert outcome.ruling.protocol == "judge_only"
    assert outcome.ruling.ruling in ("UPHOLD", "OVERTURN")
    assert "recourse_judge" in client.roles()
    # judge-only: no debater speaks in the contest
    assert "debater" not in client.roles()


async def test_the_derived_verdict_follows_from_the_ruling(tmp_path):
    outcome, _, _, record = await contest(tmp_path, "debate")
    # the fake recourse judge overturns
    assert outcome.ruling.ruling == "OVERTURN"
    assert outcome.ruling.verdict != record.verdict.verdict
    assert outcome.ruling.changed_the_decision is True


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


DECLINE = "Thinking: I read it.\nArgument: Objection: NONE\nThe grounds check out."


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


# --- the four stances ----------------------------------------------------------------
#
# The pilot's replies, in their measured shapes. Its instruction — "RAISED if the
# decision rests on an error" — was satisfied by agreeing with a FLAWED verdict, and the
# challenger duly raised 51 objections of which roughly 46 agreed with the decision they
# objected to. `raised` alone therefore says nothing; `stance` is what gates.

# The measured shape: no Thinking:/Argument: labels anywhere (118 of 120 pilot replies).
AGREES = ("Objection: RAISED\nVerdict should be: FLAWED\n"
          "The decision correctly identifies the error in step 2.")
CONTESTS = ("Objection: RAISED\nVerdict should be: SOUND\n"
            "The claimed flaw in step 2 is not one; the identity holds.")
UNCLEAR = "Objection: RAISED\nSomething about this decision is off."
CONTRADICTORY = "Objection: NONE\nVerdict should be: SOUND\nThe grounds check out."


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
    assert "Verdict should be" not in outcome.challenge.text
    assert "Verdict should be" not in "".join(
        m["content"] for m in client.sent_to("recourse_judge"))


async def test_an_agreeing_objection_seeks_no_ruling(tmp_path):
    """RAISED, and the verdict it names is the one already given. The pilot ran 51 such
    rulings and read the judges' upholding of them as contestability."""
    client = FakeClient(replies={"challenger": AGREES})
    outcome, client, writer, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.raised is True          # the literal word it wrote
    assert outcome.challenge.stance == "agrees"      # what the pipeline gates on
    assert outcome.challenge.claimed_verdict == FLAWED
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


async def test_a_decline_that_names_the_contrary_verdict_is_still_a_decline(tmp_path):
    """It was asked whether to object and it answered. Reading a contest into a reply
    that says there is none would manufacture objections nobody made."""
    client = FakeClient(replies={"challenger": CONTRADICTORY})
    outcome, client, _, _ = await contest(tmp_path, "debate", client=client)
    assert outcome.challenge.stance == "declined"
    assert outcome.challenge.contradictory is True
    assert outcome.ruling is None
    assert "recourse_judge" not in client.roles()


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


async def test_the_contest_document_says_when_an_objection_agreed(tmp_path):
    client = FakeClient(replies={"challenger": AGREES})
    _, _, writer, _ = await contest(tmp_path, "debate", client=client)
    document = (writer.dir / "transcript.md").read_text()
    assert "agreed with the verdict" in document
    assert "no ruling was sought" in document


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
