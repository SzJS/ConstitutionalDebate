"""The solo arms, and what makes them fair controls rather than lookalikes.

Three properties carry the weight:

1. **No speaker appears anywhere in a solo record.** Reusing `Transcript` with a
   solo `Speaker.ALICE` would have made every renderer work unchanged, at the
   price of a document stating that Bob argued for `answers[1]` in a run where
   Bob never spoke. The claim under test is that the record is readable *and
   true*.
2. **The critique is published.** If only the revision were recorded, a
   challenger would never see the adversarial work and the arm would be
   unmatched against debate by construction.
3. **Answers are presented through `seating.choice_order`**, as the debate
   judge's are. Otherwise position bias is controlled in one arm and not the
   others — a confound pointing in debate's favour.
"""

from __future__ import annotations

import json

import pytest

from constitutional_debate.arms import DECIDERS, run_self_critique, run_single_agent
from constitutional_debate.prompts import PROFILES, build_solo_messages
from constitutional_debate.types import Seating, Trace, Transcript

from conftest import FakeClient
from helpers import config, make_seating, make_task

SOLO_REPLY = (
    "Thinking:\nprivate working the reader sees only afterwards\n\n"
    "Reasoning:\nThe second choice follows from the constraint.\nAnswer: 2"
)
CRITIQUE_REPLY = "Step 2 asserts the bound without establishing it."


def solo_client(**kw) -> FakeClient:
    scripted = {
        ("solo", "draft"): SOLO_REPLY,
        ("solo", "revision"): SOLO_REPLY,
        ("critic", "critique"): CRITIQUE_REPLY,
    }
    scripted.update(kw.pop("scripted", {}))
    return FakeClient(scripted=scripted, **kw)


# Non-identity on purpose: choice 2 must resolve to answers[0], so a
# `choice - 1` shortcut inverts the decision and every test still passes
# unless the seating is flipped.
FLIPPED = Seating(alice_answer=0, bob_answer=1, choice_order=(1, 0),
                  seed_material="flipped")


async def run_single(**kw):
    client = solo_client()
    result = await run_single_agent(
        make_task(gold_index=0), None, config(), FLIPPED, client,
        profile=PROFILES["paper"], **kw,
    )
    return result, client


# --------------------------------------------------------------------------- #
# the decision resolves like everyone else's
# --------------------------------------------------------------------------- #


async def test_the_choice_resolves_through_the_seating():
    """The non-identity fixture: choice_order=(1,0), so choice 2 means answers[0].

    Written as `choice - 1` this silently inverts every solo decision, and the
    run still completes.
    """
    result, _ = await run_single()
    assert result.verdict.choice == 2
    assert result.verdict.answer_index == 0, "choice 2 -> answers[choice_order[1]] = 0"
    assert result.verdict.correct is True  # gold_index=0


async def test_a_single_agent_spends_exactly_one_call():
    result, client = await run_single()
    assert len(client.calls) == 1
    assert [s.stage for s in result.trace.all_steps()] == ["draft"]


async def test_self_critique_is_draft_critique_revision():
    client = solo_client()
    result = await run_self_critique(
        make_task(gold_index=0), None, config(), make_seating(), client,
        profile=PROFILES["paper"],
    )
    assert [s.stage for s in result.trace.all_steps()] == ["draft", "critique", "revision"]
    assert len(client.calls) == 3


async def test_more_critique_rounds_repeat_the_pair():
    client = solo_client()
    result = await run_self_critique(
        make_task(gold_index=0), None, config(n_critique_rounds=2),
        make_seating(), client, profile=PROFILES["paper"],
    )
    assert [s.stage for s in result.trace.all_steps()] == [
        "draft", "critique", "revision", "critique", "revision",
    ]


async def test_the_critique_spends_no_repair_attempt():
    """It produces no decision, so there is nothing to parse and nothing to fix."""
    client = solo_client(scripted={("critic", "critique"): "free-form prose, no labels"})
    result = await run_self_critique(
        make_task(gold_index=0), None, config(), make_seating(), client,
        profile=PROFILES["paper"],
    )
    critique = [s for s in result.trace.all_steps() if s.stage == "critique"][0]
    assert critique.parse_mode == "none"
    assert critique.repair_attempts == 0
    assert not any(c["meta"].get("purpose") == "repair" for c in client.calls)


# --------------------------------------------------------------------------- #
# the record is true
# --------------------------------------------------------------------------- #


async def test_no_speaker_appears_anywhere_in_a_solo_record(tmp_path):
    """The reason Step exists instead of a solo Turn."""
    from constitutional_debate.persistence import RunWriter

    task = make_task(gold_index=0)
    writer = RunWriter.create(
        task=task, context=None, config=config(), client_config=_client_config(),
        seating=make_seating(), profile_key="paper", outputs_root=tmp_path,
        arm="self_critique",
    )
    await run_self_critique(
        task, None, config(), make_seating(), solo_client(),
        writer=writer, profile=PROFILES["paper"],
    )
    for name in ("transcript.json", "transcript.md"):
        text = (writer.dir / name).read_text()
        assert "Alice" not in text, f"{name} names a debater that never spoke"
        assert "Bob" not in text
    doc = json.loads((writer.dir / "transcript.json").read_text())
    assert "positions" not in doc, "a solo record has no positions to state"
    assert "steps" in doc


async def test_the_critique_is_published_in_the_readable_record(tmp_path):
    """Unpublished, the arm would be unmatched against debate by construction."""
    from constitutional_debate.persistence import RunWriter

    task = make_task(gold_index=0)
    writer = RunWriter.create(
        task=task, context=None, config=config(), client_config=_client_config(),
        seating=make_seating(), profile_key="paper", outputs_root=tmp_path,
        arm="self_critique",
    )
    await run_self_critique(
        task, None, config(), make_seating(), solo_client(),
        writer=writer, profile=PROFILES["paper"],
    )
    document = (writer.dir / "transcript.md").read_text()
    assert CRITIQUE_REPLY in document
    assert "critique is part of the record" in document
    assert "Step 2 — critique" in document


async def test_steps_are_written_as_produced(tmp_path):
    """A run that dies at the revision still has its draft and critique."""
    from constitutional_debate.persistence import RunWriter

    task = make_task(gold_index=0)
    writer = RunWriter.create(
        task=task, context=None, config=config(), client_config=_client_config(),
        seating=make_seating(), profile_key="paper", outputs_root=tmp_path,
        arm="self_critique",
    )
    client = solo_client(fail_on={("solo", "revision"): "http_error"})
    with pytest.raises(Exception):
        await run_self_critique(
            task, None, config(), make_seating(), client,
            writer=writer, profile=PROFILES["paper"],
        )
    doc = json.loads((writer.dir / "transcript.json").read_text())
    assert [s["stage"] for s in doc["steps"]] == ["draft", "critique"]


# --------------------------------------------------------------------------- #
# positional bias is controlled here too
# --------------------------------------------------------------------------- #


def test_answers_are_presented_through_the_choice_order():
    """As build_judge_messages does. Otherwise the baselines are unshuffled."""
    task = make_task(gold_index=0)
    flipped = Seating(alice_answer=0, bob_answer=1, choice_order=(1, 0),
                      seed_material="x")
    user = build_solo_messages(
        task, None, flipped, config(), "", stage="draft", profile=PROFILES["paper"],
    )[1]["content"]
    shown_first = user.split("1: ")[1].split("\n")[0]
    assert shown_first == task.answers[1], "choice 1 must show answers[choice_order[0]]"


def test_the_gold_answer_changes_no_solo_prompt():
    """The same invariant the debate prompts carry."""
    seating = make_seating()
    a = build_solo_messages(make_task(gold_index=0), None, seating, config(), "",
                            stage="draft", profile=PROFILES["paper"])
    b = build_solo_messages(make_task(gold_index=1), None, seating, config(), "",
                            stage="draft", profile=PROFILES["paper"])
    assert a == b


# --------------------------------------------------------------------------- #
# the seam
# --------------------------------------------------------------------------- #


def test_every_arm_is_reachable_through_one_dispatch_table():
    assert set(DECIDERS) == {"debate", "single", "self_critique"}


async def test_each_arm_produces_the_same_verdict_shape():
    """Verdict stays universal, so every downstream metric is arm-independent."""
    single, _ = await run_single()
    critique = await run_self_critique(
        make_task(gold_index=0), None, config(), make_seating(), solo_client(),
        profile=PROFILES["paper"],
    )
    for result in (single, critique):
        assert result.verdict.answer_index in (0, 1)
        assert result.verdict.correct is not None
        assert isinstance(result.trace, Trace)
        assert not isinstance(result.trace, Transcript)


def _client_config(**kw):
    from constitutional_debate.config import ClientConfig

    base = dict(
        base_url="https://openrouter.test/api/v1", max_concurrency=4, max_attempts=2,
        backoff_base_s=0.0, backoff_cap_s=1.0, connect_timeout_s=1.0,
        read_timeout_s=1.0, run_timeout_s=30.0, max_runs_in_flight=2,
    )
    return ClientConfig(**{**base, **kw})


# --------------------------------------------------------------------------- #
# the two debate variants
# --------------------------------------------------------------------------- #


def test_the_model_side_draw_is_independent_of_the_other_two():
    """A fourth independent draw, for the same reason as the other three.

    Alice always speaks first, so if model identity correlated with speaking
    order a capability gap between the two models would read as a first-mover
    effect — and the seating module exists precisely to keep those apart.
    """
    import collections

    from constitutional_debate.types import make_seating as draw

    seatings = [draw(make_task_id(i), 0) for i in range(200)]
    swaps = collections.Counter(s.swap_debater_models for s in seatings)
    assert 60 <= swaps[True] <= 140, swaps
    # independent of who defends what, and of the choice order
    pairs = collections.Counter(
        (s.swap_debater_models, s.alice_answer) for s in seatings
    )
    assert all(30 <= n <= 70 for n in pairs.values()), pairs


def make_task_id(i):
    from constitutional_debate.types import Task

    return Task(task_id=f"t{i}", question="q", answers=("a", "b"), gold_index=0)


def test_one_model_means_both_sides_get_it_whatever_the_draw():
    from constitutional_debate.types import Speaker

    for swap in (False, True):
        seating = Seating(alice_answer=0, bob_answer=1, choice_order=(0, 1),
                          seed_material="x", swap_debater_models=swap)
        for speaker in (Speaker.ALICE, Speaker.BOB):
            assert seating.model_for(speaker, "primary", None) == "primary"


def test_two_models_are_assigned_by_the_draw():
    from constitutional_debate.types import Speaker

    straight = Seating(alice_answer=0, bob_answer=1, choice_order=(0, 1),
                       seed_material="x", swap_debater_models=False)
    swapped = Seating(alice_answer=0, bob_answer=1, choice_order=(0, 1),
                      seed_material="x", swap_debater_models=True)
    assert straight.model_for(Speaker.ALICE, "A", "B") == "A"
    assert straight.model_for(Speaker.BOB, "A", "B") == "B"
    assert swapped.model_for(Speaker.ALICE, "A", "B") == "B"
    assert swapped.model_for(Speaker.BOB, "A", "B") == "A"


async def test_a_two_model_debate_calls_each_model_once_per_round():
    from constitutional_debate.debate import run_debate

    task = make_task(gold_index=0)
    seating = Seating(alice_answer=0, bob_answer=1, choice_order=(0, 1),
                      seed_material="x", swap_debater_models=False)
    client = FakeClient()
    await run_debate(
        task, None, config(n_rounds=1, debater_model_b="model-b"),
        seating, client, profile=PROFILES["paper"],
    )
    debaters = [c for c in client.calls if c["meta"]["role"] == "debater"]
    assert {c["model"] for c in debaters} == {config().debater_model, "model-b"}
    # and the record says which side each model spoke for, so a reader does not
    # have to re-derive it from the seating
    assert {c["meta"]["model_side"] for c in debaters} == {"a", "b"}


async def test_a_one_model_debate_is_unchanged():
    from constitutional_debate.debate import run_debate

    client = FakeClient()
    await run_debate(
        make_task(gold_index=0), None, config(n_rounds=1), make_seating(), client,
        profile=PROFILES["paper"],
    )
    debaters = [c for c in client.calls if c["meta"]["role"] == "debater"]
    assert {c["model"] for c in debaters} == {config().debater_model}
    assert {c["meta"]["model_side"] for c in debaters} == {"a"}
