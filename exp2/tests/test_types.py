"""The reframing, and the invariants that stop it going wrong quietly.

exp1's equivalent module guarded three orderings; exp2 has two, plus a ground-truth
bool where exp1 had an index. Both changes remove a structural guarantee, so the tests
here carry more of the weight than exp1's did.
"""

from __future__ import annotations

import json

import pytest

from exp2.types import (
    CHALLENGE_STANCES,
    FLAWED,
    LABEL_BASES,
    RULINGS,
    SOUND,
    VERDICTS,
    Case,
    Challenge,
    FlawAnnotation,
    Item,
    Ruling,
    Sides,
    Speaker,
    Verdict,
    challenge_stance,
    complement,
    load_cases,
    make_sides,
    resolve_ruling,
    verdict_for,
)


def item(**kw) -> Item:
    base = dict(
        item_id="theoremqa-p1-flawed",
        row_id="theoremqa:p1",
        subset="theoremqa",
        problem="What is 2+2?",
        solution="Step 1: 2+2 = 5.",
        gold_flawed=True,
    )
    base.update(kw)
    return Item(**base)


def annotation(**kw) -> FlawAnnotation:
    base = dict(
        annotation_id="theoremqa-p1",
        flaw_location="1",
        annotation="Step 1 adds incorrectly.",
        annotation_quality="explanation",
    )
    base.update(kw)
    return FlawAnnotation(**base)


# --- the verdict vocabulary ---------------------------------------------------------


def test_complement_and_verdict_for_agree():
    assert complement(FLAWED) == SOUND
    assert complement(SOUND) == FLAWED
    assert verdict_for(True) == FLAWED
    assert verdict_for(False) == SOUND
    with pytest.raises(ValueError):
        complement("YES")


def test_the_verdict_words_do_not_collide_with_the_objection_words():
    """FLAWED/SOUND rather than YES/NO, so a transcript has one yes/no decision.

    The challenger's line is "Objection: RAISED|NONE"; if the verdict were YES/NO a
    reader scanning the document would meet two unrelated binary decisions, and a
    mis-parse of one would be indistinguishable from the other.
    """
    assert set(VERDICTS).isdisjoint({"YES", "NO", "RAISED", "NONE"})
    assert set(VERDICTS).isdisjoint(set(RULINGS))


# --- Item ---------------------------------------------------------------------------


def test_gold_verdict_follows_the_label():
    assert item(gold_flawed=True).gold_verdict == FLAWED
    assert item(gold_flawed=False, item_id="x-sound").gold_verdict == SOUND


def test_an_empty_solution_is_refused():
    with pytest.raises(ValueError):
        item(solution="   ")


def test_label_basis_is_validated_and_defaults_to_the_paired_construction():
    """The three bases answer different questions and must never be pooled silently."""
    assert item().label_basis == "injected_pair"
    assert set(LABEL_BASES) == {"injected_pair", "sentence_labels", "final_answer"}
    assert item(label_basis="sentence_labels").label_basis == "sentence_labels"
    with pytest.raises(ValueError, match="label_basis"):
        item(label_basis="vibes")


def test_item_round_trips_through_json():
    original = item(label_reliable=False, label_basis="final_answer",
                    source="ftf:theoremqa")
    restored = Item.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original


def test_unknown_keys_in_a_recorded_item_are_dropped_not_fatal():
    """A case file written by a later version must still load."""
    data = {**item().to_dict(), "some_future_field": 1}
    assert Item.from_dict(data).item_id == "theoremqa-p1-flawed"


# --- Case: the invariant that encodes "no valid objection on a sound solution" ------


def test_a_flawed_item_must_carry_an_annotation():
    with pytest.raises(ValueError, match="must carry a FlawAnnotation"):
        Case(item=item(gold_flawed=True), flaw=None)


def test_a_sound_item_must_not_carry_an_annotation():
    """The CELS and medqa subsets carry annotator comments on every row, sound ones
    included. Attaching them would manufacture a gradable flaw that does not exist."""
    with pytest.raises(ValueError, match="No objection can be valid"):
        Case(item=item(gold_flawed=False, item_id="x-sound"), flaw=annotation())


def test_gradable_tracks_the_annotation_tier_not_merely_its_presence():
    assert Case(item(), annotation()).gradable is True
    # gpqa: a step pointer, no characterisation
    assert Case(item(), annotation(annotation_quality="location_only", annotation="")).gradable is False
    assert Case(item(), annotation(annotation_quality="none", annotation="")).gradable is False
    assert Case(item(gold_flawed=False, item_id="x-sound"), None).gradable is False


def test_case_round_trips_including_the_sound_shape(tmp_path):
    flawed = Case(item(), annotation())
    sound = Case(item(gold_flawed=False, item_id="theoremqa-p1-sound"), None)
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c.to_dict()) for c in (flawed, sound)), encoding="utf-8")
    loaded = load_cases(path)
    assert [c.item.item_id for c in loaded] == [flawed.item.item_id, sound.item.item_id]
    assert loaded[0].flaw == flawed.flaw
    assert loaded[1].flaw is None


def test_an_unknown_annotation_quality_is_refused():
    with pytest.raises(ValueError):
        annotation(annotation_quality="vibes")


# --- Sides: the two orderings, drawn independently ----------------------------------


def test_sides_are_stable_per_item_and_independent_of_iteration_order():
    """Seeded on the item id, not on call order, so a sharded or resumed run agrees."""
    first = make_sides(item(), 0)
    assert make_sides(item(), 0) == first
    assert first.seed_material == "0:theoremqa-p1-flawed"
    # a different seed gives a different draw for the same item
    assert make_sides(item(), 1).seed_material == "1:theoremqa-p1-flawed"


def test_the_three_draws_are_independent_and_balanced():
    """A fixed seed, so this is not flaky.

    The failure this guards against is subtle: if side assignment and template order
    came off one draw, "the verdict listed first" would silently become "the side that
    spoke first", and the randomisation that exists to neutralise position bias would
    stop doing anything.
    """
    sides = [make_sides(item(item_id=f"i{n}", row_id=f"r{n}"), 0) for n in range(2000)]
    alice_flawed = [s.alice_side == FLAWED for s in sides]
    flawed_first = [s.verdict_order[0] == FLAWED for s in sides]
    swapped = [s.swap_debater_models for s in sides]

    for marginal, name in ((alice_flawed, "alice_side"), (flawed_first, "verdict_order"),
                           (swapped, "swap_debater_models")):
        share = sum(marginal) / len(marginal)
        assert 0.45 < share < 0.55, f"{name} is unbalanced at {share:.3f}"

    agree = sum(a == b for a, b in zip(alice_flawed, flawed_first)) / len(sides)
    assert 0.45 < agree < 0.55, f"side and template order correlate at {agree:.3f}"


def test_sides_maps_both_ways():
    s = Sides(alice_side=FLAWED, bob_side=SOUND, verdict_order=(SOUND, FLAWED),
              seed_material="t")
    assert s.side_for(Speaker.ALICE) == FLAWED
    assert s.side_for(Speaker.BOB) == SOUND
    assert s.speaker_for_side(FLAWED) is Speaker.ALICE
    assert s.speaker_for_side(SOUND) is Speaker.BOB


def test_inconsistent_sides_are_refused():
    with pytest.raises(ValueError):
        Sides(alice_side=FLAWED, bob_side=FLAWED, verdict_order=(FLAWED, SOUND), seed_material="t")
    with pytest.raises(ValueError):
        Sides(alice_side=FLAWED, bob_side=SOUND, verdict_order=(FLAWED, FLAWED), seed_material="t")


def test_model_assignment_respects_the_swap_and_ignores_it_in_self_play():
    swapped = Sides(FLAWED, SOUND, (FLAWED, SOUND), "t", swap_debater_models=True)
    straight = Sides(FLAWED, SOUND, (FLAWED, SOUND), "t", swap_debater_models=False)
    assert straight.model_for(Speaker.ALICE, "A", "B") == "A"
    assert swapped.model_for(Speaker.ALICE, "A", "B") == "B"
    # self-play: the draw has no effect
    assert swapped.model_for(Speaker.ALICE, "A", None) == "A"
    assert swapped.model_for(Speaker.BOB, "A", None) == "A"


# --- Verdict ------------------------------------------------------------------------


def verdict(**kw) -> Verdict:
    base = dict(verdict=FLAWED, parse_mode="strict", raw="Verdict: FLAWED",
                call_id="c1", finish_reason="stop", correct=True)
    base.update(kw)
    return Verdict(**base)


def test_verdict_refuses_a_word_outside_the_vocabulary():
    with pytest.raises(ValueError):
        verdict(verdict="YES")


def test_says_flawed_survives_serialisation():
    data = verdict().to_dict()
    assert data["says_flawed"] is True
    assert data["verdict"] == FLAWED


def test_there_is_no_confidence_field():
    """Judge confidence is an ablation in DESIGN.md, not part of the main protocol."""
    assert "confidence" not in verdict().to_dict()


# --- Ruling: two forms, one shape ---------------------------------------------------


def test_resolve_ruling_is_the_one_decision_rule():
    assert resolve_ruling("UPHOLD", FLAWED) == FLAWED
    assert resolve_ruling("OVERTURN", FLAWED) == SOUND
    assert resolve_ruling("OVERTURN", SOUND) == FLAWED
    with pytest.raises(ValueError):
        resolve_ruling("UPHELD", FLAWED)


def ruling(**kw) -> Ruling:
    base = dict(form="uphold_overturn", ruling="OVERTURN", protocol="judge_only",
                parent_verdict=FLAWED, verdict=SOUND, parse_mode="strict",
                raw="Ruling: OVERTURN", call_id="c1", finish_reason="stop", correct=True)
    base.update(kw)
    return Ruling(**base)


def test_changed_the_decision_survives_serialisation():
    """exp1's bug: asdict drops properties, and leaving this out pinned every headline
    revision rate to 0/N with a confident interval — a wrong number that never crashes."""
    data = ruling().to_dict()
    assert data["changed_the_decision"] is True
    assert data["upheld"] is False
    round_tripped = json.loads(json.dumps(data))
    assert round_tripped["changed_the_decision"] is True

    upheld = ruling(ruling="UPHOLD", verdict=FLAWED).to_dict()
    assert upheld["changed_the_decision"] is False and upheld["upheld"] is True


def test_a_derived_verdict_inconsistent_with_its_ruling_is_refused():
    """The uphold/overturn form derives the verdict; a mismatch means a caller bug."""
    with pytest.raises(ValueError, match="implies"):
        ruling(ruling="UPHOLD", verdict=SOUND)


def test_the_restated_form_carries_no_ruling_word():
    ok = ruling(form="restated_verdict", ruling=None, protocol="in_conversation",
                parent_verdict=FLAWED, verdict=SOUND)
    assert ok.changed_the_decision is True
    with pytest.raises(ValueError, match="must not carry a ruling word"):
        ruling(form="restated_verdict", ruling="UPHOLD", protocol="in_conversation")


def test_the_two_forms_are_named_because_they_ask_different_questions():
    """A restated verdict asks a model to contradict itself; an uphold/overturn asks a
    third party whether an objection lands. The record must say which was asked."""
    assert ruling().form == "uphold_overturn"
    assert ruling(form="restated_verdict", ruling=None,
                  protocol="in_conversation").form == "restated_verdict"
    with pytest.raises(ValueError):
        ruling(form="whatever")


# --- Challenge: four stances, one of which seeks a ruling -----------------------------


def test_the_stance_is_the_pair_of_lines_not_the_objection_word_alone():
    """The pilot's defect in one function. Its instruction made RAISED true of every
    FLAWED verdict, so roughly 46 of its 51 raised objections agreed with the decision
    they objected to, and the recourse judges upheld them — which read as
    contestability."""
    assert challenge_stance(raised=True, claimed_verdict=SOUND,
                            decision_verdict=FLAWED) == "contests"
    assert challenge_stance(raised=True, claimed_verdict=FLAWED,
                            decision_verdict=FLAWED) == "agrees"
    assert challenge_stance(raised=True, claimed_verdict=None,
                            decision_verdict=FLAWED) == "unclear"
    assert challenge_stance(raised=False, claimed_verdict=None,
                            decision_verdict=FLAWED) == "declined"
    # a decline that names the contrary verdict is still a decline: it was asked
    # whether to object and it answered
    assert challenge_stance(raised=False, claimed_verdict=SOUND,
                            decision_verdict=FLAWED) == "declined"
    assert set(CHALLENGE_STANCES) == {"contests", "agrees", "declined", "unclear"}


def test_a_challenge_written_before_stances_existed_still_loads():
    """Every challenge.json on disk predates the field. Empty means derive from
    ``raised``, which is exactly what the pipeline did before."""
    assert Challenge(text="t", origin="generated", raised=True).stance == "contests"
    assert Challenge(text="t", origin="generated", raised=False).stance == "declined"
    old = {"text": "t", "origin": "generated", "raised": False}
    assert Challenge.from_dict(old).stance == "declined"


def test_a_challenge_round_trips_its_stance_and_claimed_verdict():
    challenge = Challenge(text="t", origin="generated", raised=True,
                          claimed_verdict=SOUND, stance="contests")
    data = challenge.to_dict()
    assert data["stance"] == "contests" and data["claimed_verdict"] == SOUND
    assert Challenge.from_dict(json.loads(json.dumps(data))).stance == "contests"


def test_a_stance_that_disagrees_with_the_objection_word_is_refused():
    with pytest.raises(ValueError, match="disagrees with raised"):
        Challenge(text="t", origin="generated", raised=False, stance="contests")
    with pytest.raises(ValueError, match="must be one of"):
        Challenge(text="t", origin="generated", raised=True, stance="objects")
