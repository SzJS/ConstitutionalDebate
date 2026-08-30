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
    recourse_pro_speaker,
    recourse_stance,
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


def test_the_verdict_words_do_not_collide_with_any_other_decision_words():
    """FLAWED/SOUND rather than YES/NO, so a transcript has one yes/no decision.

    The challenger's line is "Decision: STANDS|REVERSE"; if the verdict were YES/NO a
    reader scanning the document would meet two unrelated binary decisions, and a
    mis-parse of one would be indistinguishable from the other.

    The stronger form of the same rule, and the reason the challenger's line was
    rewritten a third time: the challenger's vocabulary must share no word with the
    verdict's, because pilot 2 measured it using SOUND to mean "the verdict is sound"
    as often as "the text is sound".
    """
    from exp2.types import DECISION_WORDS, PROSE_STANCES

    assert set(VERDICTS).isdisjoint({"YES", "NO", "RAISED", "NONE"})
    assert set(VERDICTS).isdisjoint(set(RULINGS))
    assert set(VERDICTS).isdisjoint(set(DECISION_WORDS))
    assert set(VERDICTS).isdisjoint(set(PROSE_STANCES))
    assert set(DECISION_WORDS).isdisjoint(set(RULINGS))
    assert set(DECISION_WORDS).isdisjoint(set(PROSE_STANCES))


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


def test_the_three_forms_are_named_because_they_ask_different_questions():
    """A restated verdict asks a model to contradict itself; an uphold/overturn asks a
    third party whether an objection lands; a stated conclusion asks it what is true of
    the text and derives the rest. The record must say which was asked."""
    assert ruling().form == "uphold_overturn"
    assert ruling(form="restated_verdict", ruling=None,
                  protocol="in_conversation").form == "restated_verdict"
    assert ruling(form="stated_conclusion").form == "stated_conclusion"
    with pytest.raises(ValueError):
        ruling(form="whatever")


def test_the_stated_conclusion_form_still_derives_its_verdict_from_its_ruling():
    """The judge states the verdict and the ruling word is computed from it, which is the
    opposite direction from uphold_overturn — but the invariant is the same one, so
    nothing downstream has to know which way it ran."""
    ok = ruling(form="stated_conclusion", ruling="OVERTURN",
                parent_verdict=FLAWED, verdict=SOUND,
                conclusion_line="Conclusion: the original text in <solution> does not "
                                "contain a flaw")
    assert resolve_ruling(ok.ruling, ok.parent_verdict) == ok.verdict
    assert ok.changed_the_decision is True
    assert ok.to_dict()["conclusion_line"].startswith("Conclusion:")
    with pytest.raises(ValueError, match="implies"):
        ruling(form="stated_conclusion", ruling="UPHOLD", parent_verdict=FLAWED,
               verdict=SOUND)
    with pytest.raises(ValueError, match="needs a ruling"):
        ruling(form="stated_conclusion", ruling=None, parent_verdict=FLAWED,
               verdict=SOUND)


def test_an_old_ruling_json_still_loads_after_conclusion_line_was_added():
    """The 1,586 rulings on disk predate the field, and the ruling-agreement stage has to
    read every one of them. `from_dict` also has to drop the two serialised properties,
    which are not constructor arguments."""
    old = {"form": "uphold_overturn", "ruling": "OVERTURN", "protocol": "judge_only",
           "parent_verdict": FLAWED, "verdict": SOUND, "parse_mode": "strict",
           "raw": "Ruling: OVERTURN", "call_id": "c1", "finish_reason": "stop",
           "correct": True, "reasoning": "It lands.",
           "upheld": False, "changed_the_decision": True}
    loaded = Ruling.from_dict(old)
    assert loaded.conclusion_line == ""
    assert loaded.changed_the_decision is True
    assert Ruling.from_dict(ruling().to_dict()).to_dict() == ruling().to_dict()


# --- the ruling's line-vs-prose instrument -------------------------------------------


def test_a_ruling_agreement_mismatch_counts_neither_as_a_mismatch():
    """Deliberate, and the conservative direction: this number is used as a BOUND on
    every revised_* rate, and a line whose reasoning does not support it has not been
    shown to follow from anything. `prose_conclusion` is in the index beside it, so the
    strict contradiction rate can be recovered without re-running the stage."""
    from exp2.types import RulingAgreement

    def reading(**kw) -> RulingAgreement:
        base = dict(prose_conclusion="FLAWED", line_conclusion=FLAWED,
                    reasoning="it finds the error", model="grader/model",
                    parse_mode="strict", raw="Reading: FLAWED", call_id="c1",
                    finish_reason="stop", ruling_form="stated_conclusion",
                    parent_verdict=SOUND)
        base.update(kw)
        return RulingAgreement(**base)

    assert reading().mismatch is False
    assert reading(prose_conclusion="SOUND").mismatch is True
    assert reading(prose_conclusion="NEITHER").mismatch is True
    assert reading().to_dict()["mismatch"] is False
    with pytest.raises(ValueError, match="prose_conclusion"):
        reading(prose_conclusion="RIGHT")
    with pytest.raises(ValueError, match="line_conclusion"):
        reading(line_conclusion="UPHOLD")


# --- Challenge: three stances, one of which seeks a ruling ----------------------------


def test_the_stance_is_the_one_relative_line():
    """Two earlier instructions are compressed into this function. Pilot 1's made
    RAISED true of every FLAWED verdict; pilot 2's asked for a claimed verdict beside it
    and the challenger reused the verdict's own words for two different claims. One
    relative token leaves nothing to translate and nothing to answer independently."""
    from exp2.types import claimed_verdict_for

    assert challenge_stance("REVERSE") == "contests"
    assert challenge_stance("STANDS") == "declined"
    assert challenge_stance(None) == "unclear"
    with pytest.raises(ValueError):
        challenge_stance("MAYBE")
    assert set(CHALLENGE_STANCES) == {"contests", "agrees", "declined", "unclear"}


def test_the_claimed_verdict_is_derived_from_the_line_not_named_by_the_model():
    from exp2.types import claimed_verdict_for

    assert claimed_verdict_for("REVERSE", FLAWED) == SOUND
    assert claimed_verdict_for("REVERSE", SOUND) == FLAWED
    assert claimed_verdict_for("STANDS", FLAWED) == FLAWED
    assert claimed_verdict_for("STANDS", SOUND) == SOUND
    # an unreadable line is not asking for either verdict, and defaulting it to one
    # would manufacture a claim
    assert claimed_verdict_for(None, FLAWED) is None


def test_raised_now_means_exactly_contests():
    """It meant "the model wrote RAISED" under the two-line instruction, which was also
    true of `agrees` and of `unclear`. With one line there is no such reply."""
    assert Challenge(text="t", origin="generated", raised=True,
                     stance="contests").raised is True
    assert Challenge(text="t", origin="generated", raised=False,
                     stance="unclear").raised is False
    with pytest.raises(ValueError, match="disagrees with raised"):
        Challenge(text="t", origin="generated", raised=True, stance="unclear")
    with pytest.raises(ValueError, match="disagrees with raised"):
        Challenge(text="t", origin="generated", raised=False, stance="contests")


def test_line_and_prose_are_compared_through_one_table():
    """The instrument that keeps `contests` falsifiable. NEITHER is not folded into
    disagreement: prose that takes no side has not contradicted its label, it has failed
    to support it, and those are different findings."""
    from exp2.types import Agreement, line_prose_agree

    assert line_prose_agree("REVERSE", "WRONG") is True
    assert line_prose_agree("STANDS", "RIGHT") is True
    assert line_prose_agree("REVERSE", "RIGHT") is False
    assert line_prose_agree("STANDS", "WRONG") is False
    assert line_prose_agree("REVERSE", "NEITHER") is None
    assert line_prose_agree(None, "WRONG") is None

    phantom = Agreement(prose_stance="RIGHT", line_word="REVERSE", reasoning="r",
                        model="m", parse_mode="strict", raw="x", call_id="c",
                        finish_reason="stop")
    assert phantom.phantom_contest is True and phantom.agrees is False
    assert phantom.to_dict()["phantom_contest"] is True
    honest = Agreement(prose_stance="WRONG", line_word="REVERSE", reasoning="r",
                       model="m", parse_mode="strict", raw="x", call_id="c",
                       finish_reason="stop")
    assert honest.phantom_contest is False and honest.agrees is True
    with pytest.raises(ValueError):
        Agreement(prose_stance="MAYBE", line_word="REVERSE", reasoning="r", model="m",
                  parse_mode="strict", raw="x", call_id="c", finish_reason="stop")


def test_a_challenges_arm_is_validated_and_old_records_still_load():
    """`arm` was a free string set to "neutral" by the only writer. It is now the column
    that tells a reader whether a raise rate is a stakeholder's or an advocate's, so an
    unknown value has to be an error rather than a label nothing checks. Every
    challenge.json on disk carries "neutral"; a supplied challenge carries nothing."""
    from exp2.config import CHALLENGER_VARIANTS

    for variant in CHALLENGER_VARIANTS:
        assert Challenge(text="t", origin="generated", raised=True,
                         arm=variant).arm == variant
    assert Challenge(text="t", origin="file", raised=True).arm is None
    assert Challenge.from_dict(
        {"text": "t", "origin": "generated", "raised": True, "arm": "neutral"}
    ).arm == "neutral"
    with pytest.raises(ValueError, match="arm must be one of"):
        Challenge(text="t", origin="generated", raised=True, arm="partisan")


def test_the_three_controls_are_mutually_exclusive_and_name_themselves():
    """One objection cannot be two controls, and each must say which it is.

    `arm` is what selects the RULING prompt and all three controls share it — that is
    the design, since a control ruled in a different form measures the form. So the only
    thing keeping a specious objection out of the fabricated arm's numbers is
    `Challenge.variant`, and the only thing keeping a row out of two arms at once is this
    refusal."""
    common = dict(text="t", origin="generated", raised=True, arm="judgment")

    assert Challenge(**common, specious=True).variant == "judgment_specious"
    assert Challenge(**common, fabricated=True).variant == "judgment_fabricated"
    assert Challenge(**common, placeholder=True).variant == "placeholder"
    assert Challenge(**common).variant == "judgment"

    for pair in (("specious", "fabricated"), ("specious", "placeholder"),
                 ("fabricated", "placeholder")):
        with pytest.raises(ValueError, match="at most one of specious"):
            Challenge(**common, **{name: True for name in pair})

    # a control ruled under any other arm would not be a control at all
    for name in ("specious", "fabricated", "placeholder"):
        with pytest.raises(ValueError, match="must carry arm='judgment'"):
            Challenge(text="t", origin="generated", raised=True, arm="neutral",
                      **{name: True})

    # and every challenge.json written before 2026-08-28 loads as a real objection
    old = {"text": "t", "origin": "generated", "raised": True, "arm": "judgment"}
    loaded = Challenge.from_dict(old)
    assert loaded.fabricated is False and loaded.variant == "judgment"


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


# --- who argues what when a decision is contested ------------------------------------


def test_the_loser_argues_pro_and_the_winner_anti():
    """exp1's rule, ported: the debater the decision went AGAINST argues the objection.

    Overturning is the only way the decision comes back to that side, so this is the one
    assignment under which neither debater argues against the case it spent three rounds
    making. It is derived from `sides` and the parent verdict and nothing else, which is
    what stops a stored copy drifting from the seating.
    """
    sides = Sides(alice_side=FLAWED, bob_side=SOUND, verdict_order=(FLAWED, SOUND),
                  seed_material="0:x")
    # the decision went FLAWED — Alice's side — so Alice defends it and Bob attacks it
    assert recourse_stance(sides, Speaker.ALICE, FLAWED) == "anti"
    assert recourse_stance(sides, Speaker.BOB, FLAWED) == "pro"
    assert recourse_pro_speaker(sides, FLAWED) is Speaker.BOB
    # and the other way round on a SOUND decision
    assert recourse_stance(sides, Speaker.ALICE, SOUND) == "pro"
    assert recourse_stance(sides, Speaker.BOB, SOUND) == "anti"
    assert recourse_pro_speaker(sides, SOUND) is Speaker.ALICE
    # exactly one of the two argues pro, whichever way the seating fell
    for alice_side in VERDICTS:
        seating = Sides(alice_side=alice_side, bob_side=complement(alice_side),
                        verdict_order=(FLAWED, SOUND), seed_material="0:x")
        for decision in VERDICTS:
            stances = {recourse_stance(seating, s, decision)
                       for s in (Speaker.ALICE, Speaker.BOB)}
            assert stances == {"pro", "anti"}


def test_a_stance_for_a_verdict_that_is_not_one_is_refused():
    sides = Sides(alice_side=FLAWED, bob_side=SOUND, verdict_order=(FLAWED, SOUND),
                  seed_material="0:x")
    with pytest.raises(ValueError, match="must be one of"):
        recourse_stance(sides, Speaker.ALICE, "MAYBE")
    with pytest.raises(ValueError, match="must be one of"):
        recourse_pro_speaker(sides, "MAYBE")


def test_a_ruling_written_before_the_contest_round_existed_still_loads():
    """1,586 `ruling.json` files predate the three fields. They must read as what they
    are — judge-only rulings with no exchange — rather than failing to load."""
    old = {"form": "stated_conclusion", "ruling": "UPHOLD", "protocol": "judge_only",
           "parent_verdict": FLAWED, "verdict": FLAWED, "parse_mode": "strict",
           "raw": "r", "call_id": "c", "finish_reason": "stop", "correct": True}
    loaded = Ruling.from_dict(old)
    assert loaded.recourse_rounds == 0
    assert loaded.recourse_pro_speaker is None
    assert loaded.recourse_exchange_sha256 is None
    # and a contest-round ruling round-trips all three
    ruled = Ruling(**{**old, "protocol": "debate", "recourse_rounds": 1,
                      "recourse_pro_speaker": "Bob",
                      "recourse_exchange_sha256": "abc"})
    data = json.loads(json.dumps(ruled.to_dict()))
    back = Ruling.from_dict(data)
    assert (back.recourse_rounds, back.recourse_pro_speaker,
            back.recourse_exchange_sha256) == (1, "Bob", "abc")
