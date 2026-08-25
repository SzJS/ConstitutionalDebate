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


async def test_the_contest_record_carries_a_hash_of_the_decision_it_contests(tmp_path):
    import json
    _, _, writer, _ = await contest(tmp_path, "debate")
    manifest = json.loads((writer.dir / "run.json").read_text())
    assert manifest["parent_sha256"]
    assert (writer.dir / "parent" / "transcript.md").is_file()
