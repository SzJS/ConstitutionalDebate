"""Outcome-controlled construction: the invariants the design rests on.

The load-bearing claim is that the flaw a challenger meets is the *same bytes*
in every arm. Most of what follows exists to make that claim falsifiable, and
to keep the two things a model must never be shown — the flaw's annotation and
its location — out of every prompt on the construction path.
"""

from __future__ import annotations

import json

import pytest

from conftest import FakeClient
from helpers import config, make_seating, make_task

from constitutional_debate.arms import run_self_critique, run_single_agent
from constitutional_debate.construct import (
    CONSTRUCTED,
    ConstructionError,
    construct_single,
    flawed_solution_text,
    opening_turns,
    solution_steps,
    target_step_for,
)
from constitutional_debate.debate import run_debate
from constitutional_debate.types import ErrorSpec

def make_writer_with_error(tmp_path, task, cfg, seating, error, arm="single"):
    """A writer that recorded the error spec, so ``error.json`` exists to stamp.

    ``make_writer`` does not take one, and ``record_mechanism`` has nothing to
    write into without it. ``arm`` mirrors what ``decide_cell`` passes: the
    published document names the arm from the writer, so a helper that omitted
    it would let a test pass against a record labelled `debate` for a solo run.
    """
    from constitutional_debate.config import load_config
    from constitutional_debate.persistence import RunWriter
    from constitutional_debate.prompts import select_profile

    _, client_config = load_config()
    return RunWriter.create(
        task=task, context=None, config=cfg, client_config=client_config,
        seating=seating, profile_key=select_profile(task, None).key,
        outputs_root=tmp_path, error=error, arm=arm,
    )


NEEDLE_ANNOTATION = "SECRET-ANNOTATION-must-never-reach-a-prompt"

SEED = "Step 1: assume x = 2.\nStep 2: therefore x + 1 = 4.\nStep 3: so the answer is 4."
SOUND = "Step 1: assume x = 2.\nStep 2: therefore x + 1 = 3.\nStep 3: so the answer is 3."

# The injector returns the seed with step 3 altered — the flaw is at step 2, so
# the two are disjoint, which is what makes localisation alone able to tell them
# apart on a subset with no flaw description.
INJECTED_DRAFT = (
    "Step 1: assume x = 2.\nStep 2: therefore x + 1 = 4.\nStep 3: so the answer is 9."
)
# Distinctive needles in the injector's *private* channels: its Thinking says
# which step it planted an error in, and its description names the decoy. Both
# must stay out of the record — see
# test_the_injectors_private_channels_never_reach_the_record.
INJECTOR_THINKING = "DECOY-PLAN-choosing-step-3"
INJECTED_DESCRIPTION = "DECOY-DESC step 3 restates the total as 9."
INJECTOR_REPLY = (
    f"Thinking:\n{INJECTOR_THINKING}\n\nDraft:\n{INJECTED_DRAFT}\n\n"
    f"Injected error: {INJECTED_DESCRIPTION}"
)
CRITIQUE_REPLY = "Step 3 states 9, which does not follow from step 2."

# `parse_grade_output` wants both labels. 0 is "did not localise the flaw".
GRADE_MISS = "The objection does not reach it.\n\nLocalisation: 0\nChanges the decision: NO"
GRADE_HIT = "The objection names it.\n\nLocalisation: 2\nChanges the decision: YES"

# The steer-containment check. Only ever called on a *steered* output.
LEAK_CLEAN = "It argues from the record throughout.\n\nReferences the instruction: NO"
LEAK_DIRTY = (
    "It says it applied a standard it was asked to apply.\n\n"
    "References the instruction: YES"
)


def error_spec(**kw) -> ErrorSpec:
    return ErrorSpec(
        error_id=kw.pop("error_id", "case-1"),
        seed=kw.pop("seed", SEED),
        sound_seed=kw.pop("sound_seed", SOUND),
        flaw_location=kw.pop("flaw_location", "2"),
        annotation=kw.pop("annotation", NEEDLE_ANNOTATION),
        annotation_quality=kw.pop("annotation_quality", "explanation"),
        **kw,
    )


class SequencedClient(FakeClient):
    """A FakeClient whose grader replies come from a queue.

    Both gradings of a critique carry ``subject_kind="critique"``, so they share
    a scripting key and cannot be told apart by it. The order is fixed and
    documented in ``_critique_verdict``: the seeded flaw first, the injected one
    second.
    """

    def __init__(
        self, *, grades: list[str] | None = None, leaks: list[str] | None = None, **kw
    ) -> None:
        super().__init__(**kw)
        self.grades = list(grades or [])
        self.leaks = list(leaks or [])

    async def complete(self, **kw):
        purpose = kw["meta"].get("purpose")
        # Two queues, keyed on purpose. Both are role="grader", so popping on
        # role alone would desync one against the other. The last entry repeats
        # once a queue runs dry, so a test only scripts what it cares about.
        if purpose == "grade_critique" and self.grades:
            self.scripted = {
                **self.scripted,
                ("grader", "grade_critique"): self._next(self.grades),
            }
        elif purpose == "steer_leak" and self.leaks:
            self.scripted = {
                **self.scripted,
                ("grader", "steer_leak"): self._next(self.leaks),
            }
        return await super().complete(**kw)

    @staticmethod
    def _next(queue: list[str]) -> str:
        return queue.pop(0) if len(queue) > 1 else queue[0]


def solo_client(**kw) -> SequencedClient:
    scripted = {
        ("injector", "inject"): INJECTOR_REPLY,
        ("critic", "critique"): CRITIQUE_REPLY,
    }
    scripted.update(kw.pop("scripted", {}))
    # Default: the critique missed the seeded flaw and found the injected one,
    # which is the construction succeeding unsteered.
    kw.setdefault("grades", [GRADE_MISS, GRADE_HIT])
    return SequencedClient(scripted=scripted, **kw)


def oc_config(**kw):
    return config(outcome_control=True, **kw)


# --------------------------------------------------------------------------- #
# the invariant
# --------------------------------------------------------------------------- #


async def test_the_single_arm_and_the_self_critique_revision_are_byte_identical():
    """The whole design in one assertion.

    If these drift, the arms no longer carry the same flaw and a cross-arm
    detection rate is comparing three different detection problems.
    """
    task, seating, cfg, error = make_task(gold_index=0), make_seating(), oc_config(), error_spec()

    single = await run_single_agent(
        task, None, cfg, seating, solo_client(), error=error
    )
    critique = await run_self_critique(
        task, None, cfg, seating, solo_client(), error=error
    )

    revision = critique.trace.all_steps()[-1]
    assert single.trace.all_steps()[-1].text == revision.text
    assert SEED in revision.text, "the dataset's own flawed reasoning, unaltered"
    assert single.verdict.reasoning == critique.verdict.reasoning


async def test_the_answer_line_follows_the_seating_not_a_constant():
    """`choice_order` is drawn per run, so a hardcoded `Answer: 2` would be
    right on half the corpus and wrong on the other half, with every run still
    completing."""
    error = error_spec()
    normal = flawed_solution_text(make_task(gold_index=0), make_seating(), error)
    flipped = flawed_solution_text(make_task(gold_index=0), make_seating((1, 0)), error)
    assert normal.endswith("Answer: 2")
    assert flipped.endswith("Answer: 1")


@pytest.mark.parametrize("gold", [0, 1])
async def test_round_one_is_the_dataset_text_verbatim(gold):
    """And the sound half reaches whoever defends the gold answer, both ways
    round — written keyed on index 0 this inverts on half the corpus."""
    task, seating, error = make_task(gold_index=gold), make_seating(), error_spec()
    turns = opening_turns(task, seating, error)

    assert [t.round for t in turns] == [1, 1]
    assert all(t.parse_mode == CONSTRUCTED and t.call_id == "" for t in turns)
    for turn in turns:
        expected = SOUND if turn.answer_index == gold else SEED
        assert turn.argument == expected


# --------------------------------------------------------------------------- #
# containment
# --------------------------------------------------------------------------- #


async def test_the_annotation_never_reaches_a_construction_prompt():
    """The construction path legitimately holds the annotation in memory, which
    the decision path never did. Nothing may put it in a request."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    error = error_spec(annotation=NEEDLE_ANNOTATION, flaw_location="2")

    clients = []
    for runner in (run_single_agent, run_self_critique):
        client = solo_client()
        await runner(task, None, cfg, seating, client, error=error)
        clients.append(client)
    debate_client = solo_client(
        scripted={"judge": "Alice was clearer.\n\nAnswer: 2"}, grades=[]
    )
    await run_debate(task, None, cfg, seating, debate_client, error=error)
    clients.append(debate_client)

    for client in clients:
        for call in client.calls:
            if call["meta"].get("role") == "grader":
                continue  # the grader is the one thing allowed to see it
            body = json.dumps(call["messages"])
            assert NEEDLE_ANNOTATION not in body, call["meta"]


async def test_the_injector_is_never_told_where_the_case_flaw_is():
    """It is given a target step, not the ground truth. Told the flaw's location
    it could condition the draft on the answer the experiment is measuring."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    error = error_spec(flaw_location="2", annotation=NEEDLE_ANNOTATION)
    client = solo_client()
    await run_self_critique(task, None, cfg, seating, client, error=error)

    injector_call = next(c for c in client.calls if c["meta"]["role"] == "injector")
    body = injector_call["messages"][-1]["content"]
    assert NEEDLE_ANNOTATION not in body
    # The only step it is told about is the one to target, and that is not the
    # case's own. `flaw_location` is a bare digit, so its *absence* cannot be
    # asserted directly -- what is checkable is that the instruction names the
    # target and that the target is disjoint from the flaw.
    assert f"at step {target_step_for(error)}" in body
    assert str(target_step_for(error)) != error.flaw_location


def test_a_flaw_annotated_outside_the_solutions_own_steps_is_refused():
    """`ftf-gpqa-59` annotates step 4 in a solution numbered 5-7.

    Excluding a step number that is not there excludes nothing, so the
    disjointness guard would pass while the injected error landed on the case's
    own flaw -- and the localisation-only grading for GPQA has no other way to
    tell the two apart.
    """
    with pytest.raises(ConstructionError, match="not among the solution's steps"):
        target_step_for(
            error_spec(seed="Step 5: a\nStep 6: b\nStep 7: c", flaw_location="4")
        )


async def test_a_self_critique_without_a_gold_answer_is_refused_before_spending():
    """Its two siblings guard up front; this one used to pay for the injector
    and the critique before dying inside the grading on `1 - gold_index`."""
    client = solo_client()
    with pytest.raises(ConstructionError, match="gold answer"):
        await run_self_critique(
            make_task(gold_index=None), None, oc_config(), make_seating(), client,
            error=error_spec(),
        )
    assert client.calls == [], "refused before any call was made"


async def test_more_than_one_critique_round_is_refused_rather_than_ignored():
    """The constructed arm is always draft -> critique -> revision. Silently
    ignoring the setting would publish a record that disagrees with the
    config.json beside it."""
    with pytest.raises(ConstructionError, match="n_critique_rounds"):
        await run_self_critique(
            make_task(gold_index=0), None, oc_config(n_critique_rounds=2),
            make_seating(), solo_client(), error=error_spec(),
        )


# --------------------------------------------------------------------------- #
# the constructed record says what it is
# --------------------------------------------------------------------------- #


async def test_the_single_arm_spends_nothing():
    client = solo_client()
    await run_single_agent(
        make_task(gold_index=0), None, oc_config(), make_seating(), client,
        error=error_spec(),
    )
    assert client.calls == []


async def test_the_constructed_record_states_no_thinking_that_was_never_thought():
    result = await construct_single(
        make_task(gold_index=0), None, oc_config(), make_seating(), solo_client(),
        error=error_spec(),
    )
    step = result.trace.all_steps()[0]
    assert step.thinking == ""
    assert step.parse_mode == CONSTRUCTED
    assert step.call_id == ""
    assert step.raw == step.text, "nothing was stripped, because nothing was parsed"
    assert result.verdict.correct is False


async def test_a_constructed_single_run_is_written_and_reloads(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec())
    await construct_single(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    from constitutional_debate.persistence import load_run_record

    record = load_run_record(writer.dir)
    assert record.trace is not None and len(record.trace.all_steps()) == 1
    assert not (writer.dir / "calls.jsonl").is_file(), "no calls were made"
    assert "_(none recorded)_" in (writer.dir / "transcript.md").read_text()


# --------------------------------------------------------------------------- #
# step disjointness
# --------------------------------------------------------------------------- #


def test_the_injected_step_is_never_the_flaw_step():
    for flaw in ("1", "2", "3"):
        assert str(target_step_for(error_spec(flaw_location=flaw))) != flaw


def test_a_case_with_no_disjoint_step_is_refused():
    """1 of 282 across the two subsets in play. Dropped loudly rather than
    injected on top of the flaw the case is about."""
    with pytest.raises(ConstructionError, match="no step to inject into"):
        target_step_for(error_spec(seed="Step 1: the only step.", flaw_location="1"))


def test_steps_are_found_in_both_subsets_notations():
    assert solution_steps("Step 1: a\nStep 2: b") == [1, 2]
    assert solution_steps("1. a\n2. b\n3. c") == [1, 2, 3]


# --------------------------------------------------------------------------- #
# construction failures
# --------------------------------------------------------------------------- #


async def test_an_injector_that_rewrites_the_solution_is_refused():
    """A wholesale rewrite silently destroys the case's flaw, leaving a record
    that carries a flaw nothing annotates."""
    rewritten = "Completely different text. " * 20
    client = solo_client(
        scripted={
            ("injector", "inject"): (
                f"Thinking:\nx\n\nDraft:\n{rewritten}\n\nInjected error: rewrote it."
            )
        }
    )
    with pytest.raises(ConstructionError, match="rewrote the solution"):
        await run_self_critique(
            make_task(gold_index=0), None, oc_config(), make_seating(), client,
            error=error_spec(),
        )


async def test_a_case_without_a_gold_answer_is_refused():
    with pytest.raises(ConstructionError, match="gold answer"):
        await construct_single(
            make_task(gold_index=None), None, oc_config(), make_seating(),
            solo_client(), error=error_spec(),
        )


async def test_a_debate_without_an_error_spec_is_refused_not_run_normally():
    """Falling through to an ordinary debate would publish an unconstructed run
    under the constructed arm's label."""
    with pytest.raises(ConstructionError, match="annotated case"):
        await run_debate(
            make_task(gold_index=0), None, oc_config(), make_seating(),
            solo_client(), error=None,
        )


# --------------------------------------------------------------------------- #
# steering, and what `mechanism` records
#
# Both routes share one pattern: run unsteered, record the outcome, steer only
# on failure. That ordering is the point — steering suppresses a baseline's
# competence at exactly the cases where it is strongest, so how often it was
# needed has to survive as a measurement.
# --------------------------------------------------------------------------- #


def mechanism_of(writer) -> str:
    return json.loads((writer.dir / "error.json").read_text())["mechanism"]


async def test_an_unsteered_critique_is_labelled_unaided(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    assert mechanism_of(writer) == "unaided"
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["critique_steered"] is False
    assert construction["critique_caught_the_seeded_flaw_unsteered"] is False


async def test_a_critique_that_catches_the_seeded_flaw_is_steered_and_labelled(tmp_path):
    """The unsteered critique found the case's own flaw — self-critique working.

    The record cannot stand as-is: it would criticise a step the revision then
    restores. So a steered attempt is made, and the run says it was.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(
        grades=[GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT],
        scripted={("grader", "steer_leak"): LEAK_CLEAN},
    )
    await run_self_critique(
        task, None, cfg, seating, client, writer=writer,
        error=error_spec(),
    )
    assert mechanism_of(writer) == "steered"
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["critique_steered"] is True
    assert construction["critique_caught_the_seeded_flaw_unsteered"] is True


async def test_a_critique_that_resists_the_steer_fails_the_construction(tmp_path):
    """Caught the seeded flaw both times. Refused rather than published."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(grades=[GRADE_HIT, GRADE_HIT, GRADE_HIT, GRADE_HIT])
    with pytest.raises(ConstructionError, match="critique_caught_the_seeded_flaw"):
        await run_self_critique(
            task, None, cfg, seating, client, writer=writer, error=error_spec()
        )


async def test_a_critique_that_misses_the_injected_error_fails_the_construction(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(grades=[GRADE_MISS, GRADE_MISS, GRADE_MISS, GRADE_MISS])
    with pytest.raises(ConstructionError, match="critique_missed_the_injected_error"):
        await run_self_critique(
            task, None, cfg, seating, client, writer=writer, error=error_spec()
        )


async def test_the_single_arm_is_labelled_constructed(tmp_path):
    """No procedure ran, so neither `genuine` nor `manufactured` is true."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec())
    await construct_single(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    assert mechanism_of(writer) == "constructed"


async def test_a_judge_that_falls_for_the_flaw_unaided_is_genuine(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec(), arm="debate")
    # gold_index=0, choice_order=(0,1) -> choice 2 is the flawed answer.
    client = solo_client(scripted={"judge": "Bob was clearer.\n\nAnswer: 2"}, grades=[])
    result = await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )
    assert result.verdict.correct is False
    assert mechanism_of(writer) == "unaided"
    assert not (writer.dir / "construction.json").is_file(), "no steering happened"


async def test_a_judge_that_resists_is_re_judged_with_a_steer(tmp_path):
    """Only the judge is re-run: round 1 stays verbatim and rounds 2-3 stay put,
    so the record differs from an unforced one only in the judgment."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec(), arm="debate")

    class Resisting(SequencedClient):
        seen = 0

        async def complete(self, **kw):
            if kw["meta"].get("role") == "judge":
                Resisting.seen += 1
                reply = (
                    "Alice was clearer.\n\nAnswer: 1"   # correct: resists
                    if kw["meta"]["purpose"] == "judge"
                    else "On reflection.\n\nAnswer: 2"  # steered: the flaw wins
                )
                self.scripted = {**self.scripted, "judge": reply}
            return await super().complete(**kw)

    client = Resisting(scripted={("grader", "steer_leak"): LEAK_CLEAN}, grades=[])
    result = await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )

    assert Resisting.seen == 2, "one unsteered judgment, then one steered"
    assert result.verdict.correct is False
    assert mechanism_of(writer) == "steered"
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["judge_steered"] is True
    assert construction["unsteered_correct"] is True
    # Round 1 is untouched by the re-judge.
    turns = [t for t in result.transcript.all_turns() if t.round == 1]
    assert {t.argument for t in turns} == {SEED, SOUND}


async def test_the_steering_instruction_reaches_no_published_artifact(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec(), arm="debate")

    class Resisting(SequencedClient):
        async def complete(self, **kw):
            if kw["meta"].get("role") == "judge":
                self.scripted = {**self.scripted, "judge": (
                    "Alice was clearer.\n\nAnswer: 1"
                    if kw["meta"]["purpose"] == "judge"
                    else "On reflection.\n\nAnswer: 2"
                )}
            return await super().complete(**kw)

    await run_debate(
        task, None, cfg, seating,
        Resisting(scripted={("grader", "steer_leak"): LEAK_CLEAN}, grades=[]),
        writer=writer, error=error_spec(),
    )
    writer.finish(status="completed")

    published = (writer.dir / "transcript.md").read_text()
    assert "demanding standard" not in published
    assert "has not met its burden" not in published


async def test_a_constructed_record_says_it_was_constructed(tmp_path):
    """The document must not claim a pass that was never made.

    `render_solo_record` refuses to print positions for a run with no debaters
    for the same reason: a false statement in the one artifact the project's
    transparency claim rests on.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec())
    await construct_single(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    doc = (writer.dir / "transcript.md").read_text()
    assert "constructed" in doc.lower()
    assert "One agent, one pass" not in doc, "no pass was made"
    assert "Arm: `single`" in doc


async def test_the_construction_note_reaches_no_prompt(tmp_path):
    """It lives in `artifacts`, which nothing on a prompt path may import."""
    from constitutional_debate.debate import run_recourse
    from constitutional_debate.persistence import load_run_record
    from helpers import generated_challenge, make_recourse_writer

    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(tmp_path, task, cfg, seating, error_spec())
    await construct_single(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    parent = load_run_record(writer.dir)
    recourse_writer = make_recourse_writer(tmp_path, parent, cfg)
    client = FakeClient(
        sink=recourse_writer.record_call,
        scripted={"recourse_judge": "Stands.\n\nRuling: UPHOLD"},
    )
    await run_recourse(
        parent, generated_challenge(), cfg, client, writer=recourse_writer
    )
    for call in client.calls:
        body = json.dumps(call["messages"])
        assert "was **constructed**" not in body
        assert "no model wrote it" not in body


# --------------------------------------------------------------------------- #
# steer containment
#
# The steer is a construction artefact. A model that narrates it puts that
# artefact on the published path — and for the judge, straight into the grounds
# a challenger is shown. A challenger that can see the instruction can contest
# the instruction rather than the flaw, which measures nothing.
# --------------------------------------------------------------------------- #


class ResistingJudge(SequencedClient):
    """A judge that resists unaided, so every run through it gets steered."""

    def __init__(self, *, steered_replies=None, **kw):
        super().__init__(**kw)
        self.steered_replies = list(steered_replies or [])
        self.steered_calls = 0

    async def complete(self, **kw):
        meta = kw["meta"]
        if meta.get("role") == "judge":
            if meta["purpose"] == "judge":
                reply = "Alice was clearer.\n\nAnswer: 1"  # correct -> resists
            else:
                self.steered_calls += 1
                reply = (
                    self.steered_replies.pop(0)
                    if self.steered_replies
                    else "On reflection.\n\nAnswer: 2"
                )
            self.scripted = {**self.scripted, "judge": reply}
        return await super().complete(**kw)


async def test_a_steered_judge_that_references_the_steer_is_retried(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )
    client = ResistingJudge(leaks=[LEAK_DIRTY, LEAK_CLEAN], grades=[])
    result = await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )

    assert client.steered_calls == 2, "the first steered judgment was rejected"
    assert result.verdict.correct is False
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["judge_steer_leak_retries"] == 1
    assert construction["judge_steer_leaked"] is False


async def test_a_steered_judge_that_leaks_twice_fails_the_cell(tmp_path):
    """Refused rather than published: these grounds are what the challenger
    reads, so a contaminated verdict is a contaminated measurement."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )
    client = ResistingJudge(leaks=[LEAK_DIRTY], grades=[])
    with pytest.raises(ConstructionError, match="steered_judge_referenced_the_steer"):
        await run_debate(
            task, None, cfg, seating, client, writer=writer, error=error_spec()
        )
    assert client.steered_calls == 2, "two attempts, then refused"


async def test_the_containment_check_reads_the_provider_reasoning_channel(tmp_path):
    """The case that motivated the check.

    A response whose published text is clean can still narrate the steer in the
    provider's reasoning channel — which `verdict.json` keeps for the judge and
    `_solo_steps` publishes verbatim for a critique. A `raw`-only check misses
    exactly this.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )
    client = ResistingJudge(leaks=[LEAK_CLEAN], grades=[])
    await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )

    check = next(
        c for c in client.calls if c["meta"].get("purpose") == "steer_leak"
    )
    body = json.dumps(check["messages"])
    # The fake completion carries no native reasoning, so what matters is that
    # the field is *sent* — the checker must be given the channel to inspect.
    assert "<response>" in body
    assert "demanding standard" in body, "the checker is shown the steer itself"


async def test_a_steered_critique_that_references_the_steer_is_retried(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(
        # unsteered catches the seeded flaw -> steer; then two clean gradings
        # per steered attempt.
        grades=[GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT, GRADE_MISS, GRADE_HIT],
        leaks=[LEAK_DIRTY, LEAK_CLEAN],
    )
    await run_self_critique(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )

    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["critique_steered"] is True
    assert construction["critique_steer_leak_retries"] == 1


async def test_a_steered_critique_that_leaks_twice_fails_the_cell(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(
        grades=[GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT, GRADE_MISS, GRADE_HIT],
        leaks=[LEAK_DIRTY],
    )
    with pytest.raises(
        ConstructionError, match="steered_critique_referenced_the_steer"
    ):
        await run_self_critique(
            task, None, cfg, seating, client, writer=writer, error=error_spec()
        )


async def test_an_unsteered_run_spends_no_containment_call():
    """No steer, nothing to reference. Checking anyway would cost a call per
    cell to learn nothing."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    client = solo_client()  # unsteered critique passes on the first attempt
    await run_self_critique(task, None, cfg, seating, client, error=error_spec())
    assert not [c for c in client.calls if c["meta"].get("purpose") == "steer_leak"]


async def test_the_containment_check_is_off_the_decision_path(tmp_path):
    """It exists to protect the record's comparability; billing it to the
    decision path would inflate the very balance it protects."""
    from constitutional_debate.accounting import aggregate_calls

    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )
    client = ResistingJudge(
        leaks=[LEAK_CLEAN], grades=[], sink=writer.record_call
    )
    await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )
    usage = aggregate_calls(writer.dir / "calls.jsonl")
    assert usage["off_path"]["calls"] >= 1
    roles = {c["meta"].get("role") for c in client.calls}
    assert "grader" in roles


async def test_a_clean_steered_output_passes(tmp_path):
    """The false-positive guard. Without it a check that always fired would
    satisfy every other test in this section."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )
    client = ResistingJudge(leaks=[LEAK_CLEAN], grades=[])
    result = await run_debate(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )
    assert client.steered_calls == 1, "one steered judgment, accepted"
    assert result.verdict.correct is False
    assert mechanism_of(writer) == "steered"


async def test_the_injectors_private_channels_never_reach_the_record(tmp_path):
    """The draft is the injector's *text*, and nothing else of the injector.

    Its Thinking says which step it planted an error in, and its raw reply
    carries the `Injected error:` description outright. Copied onto the step
    those are published — `_solo_steps` prints thinking as "private while the
    decision was being made", and a full-visibility challenger is served it as
    "the agent also wrote a private Thinking section". That is a fabricated
    attribution, and it hands the challenger the decoy's location, which is the
    thing this arm's detection rate exists to measure.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    result = await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    draft = result.trace.all_steps()[0]
    assert draft.stage == "draft"
    assert draft.thinking == ""
    assert draft.raw == draft.text, "the reply's private sections are not the record"
    assert "Injected error" not in draft.raw
    assert INJECTOR_THINKING not in draft.raw

    document = (writer.dir / "transcript.json").read_text()
    published = (writer.dir / "transcript.md").read_text()
    for needle in (INJECTOR_THINKING, INJECTED_DESCRIPTION, "Injected error"):
        assert needle not in document, f"{needle!r} reached transcript.json"
        assert needle not in published, f"{needle!r} reached transcript.md"

    # ...and it is kept, where only the construction can read it.
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["injector_thinking"] == INJECTOR_THINKING
    assert construction["injected_error"] == INJECTED_DESCRIPTION
    assert INJECTOR_THINKING in construction["injector_raw"]


async def test_the_injectors_thinking_never_reaches_a_full_visibility_challenger(
    tmp_path,
):
    from constitutional_debate.persistence import load_run_record
    from constitutional_debate.debate import run_recourse
    from helpers import generated_challenge, make_recourse_writer

    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    parent = load_run_record(writer.dir)
    recourse_writer = make_recourse_writer(tmp_path, parent, cfg)
    client = FakeClient(
        sink=recourse_writer.record_call,
        scripted={"recourse_judge": "Stands.\n\nRuling: UPHOLD"},
    )
    await run_recourse(
        parent, generated_challenge(visibility="full"), cfg, client,
        writer=recourse_writer,
    )
    body = json.dumps(
        next(c for c in client.calls if c["meta"]["role"] == "challenger")["messages"]
    )
    assert INJECTOR_THINKING not in body
    assert INJECTED_DESCRIPTION not in body


async def test_each_step_says_where_its_words_came_from(tmp_path):
    """Three origins sit side by side in a constructed self_critique record:
    text copied from the case, text a construction step built from it, and the
    agent's own. A reader cannot tell them apart unless the document says."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    result = await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    modes = {s.stage: s.parse_mode for s in result.trace.all_steps()}
    assert modes["draft"] == "injected", "generated by the injector, not copied"
    assert modes["revision"] == CONSTRUCTED, "the case's own text, verbatim"
    assert modes["critique"] not in {CONSTRUCTED, "injected"}, "the agent's own"

    doc = (writer.dir / "transcript.md").read_text()
    assert "## Step 1 — draft (built from the case by a construction step" in doc
    assert "## Step 3 — revision (inserted verbatim from the case)" in doc
    assert "## Step 2 — critique\n" in doc, "the agent's own step is unmarked"


async def test_mechanism_asks_the_same_question_of_every_arm(tmp_path):
    """One question — did the procedure's adversarial step have to be
    overridden? — answered per arm by whichever step that is.

    `single` has no such step, so neither `unaided` nor `steered` applies to it;
    the other two answer about the judge and the critique respectively. Pinned
    because the values were once `genuine`/`manufactured`, which said nothing
    about what was genuine and left `constructed` outside the pair.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()

    def writer_for(arm):
        return make_writer_with_error(
            tmp_path / arm, task, cfg, seating, error_spec(), arm=arm
        )

    # single: no adversarial step at all.
    w = writer_for("single")
    await construct_single(
        task, None, cfg, seating, solo_client(), writer=w, error=error_spec()
    )
    assert mechanism_of(w) == "constructed"

    # self_critique: the critique needed no steer.
    w = writer_for("self_critique")
    await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=w, error=error_spec()
    )
    assert mechanism_of(w) == "unaided"

    # self_critique: the critique caught the seeded flaw and had to be confined.
    w = writer_for("self_critique_steered")
    await run_self_critique(
        task, None, cfg, seating,
        solo_client(
            grades=[GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT],
            leaks=[LEAK_CLEAN],
        ),
        writer=w, error=error_spec(),
    )
    assert mechanism_of(w) == "steered"

    # debate: the judge fell for the flaw with no help.
    w = writer_for("debate")
    await run_debate(
        task, None, cfg, seating,
        solo_client(scripted={"judge": "Bob was clearer.\n\nAnswer: 2"}, grades=[]),
        writer=w, error=error_spec(),
    )
    assert mechanism_of(w) == "unaided"

    # debate: the judge resisted and had to be pushed.
    w = writer_for("debate_steered")
    await run_debate(
        task, None, cfg, seating,
        ResistingJudge(leaks=[LEAK_CLEAN], grades=[]),
        writer=w, error=error_spec(),
    )
    assert mechanism_of(w) == "steered"


def test_the_steer_replaces_the_exhaustive_brief_rather_than_contradicting_it():
    """The first pilot's actual failure, pinned.

    The ordinary critique brief asks for "the weakest steps… and anything that
    would change the answer if it were wrong" — an exhaustive audit whose last
    clause describes the case's own flaw. Appending "confine yourself to step N"
    to that is a contradiction, and the wider, earlier instruction won: the
    steered critique still characterised the seeded flaw on 20 of 30 gradings.
    """
    from constitutional_debate.prompts import (
        CRITIQUE_STEER, SOLO_CRITIQUE_INSTRUCTION, build_solo_messages,
    )

    ordinary = build_solo_messages(
        make_task(gold_index=0), None, make_seating(), oc_config(),
        "Draft:\nStep 1: a", stage="critique",
    )[-1]["content"]
    steered = ordinary.replace(
        SOLO_CRITIQUE_INSTRUCTION, CRITIQUE_STEER.format(target_step=4)
    )

    assert SOLO_CRITIQUE_INSTRUCTION in ordinary
    assert SOLO_CRITIQUE_INSTRUCTION not in steered, "replaced, not appended"
    assert "anything that would change the answer" not in steered
    assert "single most serious thing wrong with step 4" in steered
    # ...and the critic is still told nothing about where the case's own flaw is.
    assert "flaw" not in steered.lower()


async def test_the_steered_critic_is_still_never_told_where_the_case_flaw_is(tmp_path):
    """The narrower brief is less to do, not more to know. `flaw_location` stays
    grader-only even though this step's output is published and reaches the
    challenger."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    error = error_spec(flaw_location="2", annotation=NEEDLE_ANNOTATION)
    client = solo_client(
        grades=[GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT], leaks=[LEAK_CLEAN]
    )
    await run_self_critique(task, None, cfg, seating, client, error=error)

    from constitutional_debate.prompts import CRITIQUE_STEER

    critic_calls = [c for c in client.calls if c["meta"].get("role") == "critic"]
    assert len(critic_calls) == 2, "unsteered attempt, then the steered one"
    steered = critic_calls[1]["messages"][-1]["content"]
    assert NEEDLE_ANNOTATION not in steered

    # The draft legitimately contains every step, including the flawed one --
    # the critic has to see what it is critiquing. What must never name the
    # flaw's step is the *instruction*, so assert on that rather than on the
    # whole prompt.
    target = target_step_for(error)
    instruction = CRITIQUE_STEER.format(target_step=target)
    assert instruction in steered
    assert str(error.flaw_location) != str(target)
    assert f"step {error.flaw_location}" not in instruction.lower()


async def test_a_characterising_critique_is_redacted_rather_than_refused(tmp_path):
    """The third rung. The steered critique found the decoy *and* characterised
    the case's own flaw, so it is cut down to the target step rather than the
    cell being thrown away."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    client = solo_client(
        # unsteered: caught both. steered x2: caught both. redacted: clean.
        grades=[GRADE_HIT, GRADE_HIT, GRADE_HIT, GRADE_HIT,
                GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT],
        leaks=[LEAK_CLEAN],
        scripted={("critic", "redact"): "Step 3 states 9, which does not follow."},
    )
    result = await run_self_critique(
        task, None, cfg, seating, client, writer=writer, error=error_spec()
    )
    writer.finish(status="completed")

    assert mechanism_of(writer) == "redacted"
    critique = result.trace.all_steps()[1]
    assert critique.parse_mode == "redacted"
    assert critique.text == "Step 3 states 9, which does not follow."

    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["critique_redacted"] is True
    assert construction["unredacted_critique"] == CRITIQUE_REPLY, (
        "what was removed stays recoverable, off the published path"
    )
    # ...and the record says the critique was cut down rather than implying it
    # was complete.
    doc = (writer.dir / "transcript.md").read_text()
    assert "cut down to this step during construction" in doc


async def test_the_redaction_instruction_never_names_the_case_flaw(tmp_path):
    """The reason this form was chosen over telling the critic where the flaw is:
    the model already knows what it wrote, so removing a reference to the flaw
    needs no statement of where the flaw is."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    error = error_spec(flaw_location="2", annotation=NEEDLE_ANNOTATION)
    client = solo_client(
        grades=[GRADE_HIT, GRADE_HIT, GRADE_HIT, GRADE_HIT,
                GRADE_HIT, GRADE_HIT, GRADE_MISS, GRADE_HIT],
        leaks=[LEAK_CLEAN],
        scripted={("critic", "redact"): "Step 3 is unsupported."},
    )
    await run_self_critique(task, None, cfg, seating, client, error=error)

    redact = next(c for c in client.calls if c["meta"].get("purpose") == "redact")
    body = json.dumps(redact["messages"])
    assert NEEDLE_ANNOTATION not in body
    assert f"step {target_step_for(error)}" in body.lower()


async def test_a_critique_that_never_found_the_decoy_is_not_redacted():
    """Redaction keeps material; a critique with nothing worth keeping cannot be
    rescued by cutting it down."""
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    client = solo_client(grades=[GRADE_MISS, GRADE_MISS], leaks=[LEAK_CLEAN])
    with pytest.raises(ConstructionError, match="critique_missed_the_injected_error"):
        await run_self_critique(task, None, cfg, seating, client, error=error_spec())
    assert not [c for c in client.calls if c["meta"].get("purpose") == "redact"]


async def test_the_critique_can_come_from_a_different_model_than_the_draft():
    """The self-critique analogue of a weak judge.

    Each solo stage is an independent stateless completion — prior steps reach
    the model as *text* in the user message, never as assistant turns — so
    splitting the stages across models needs no prefill and no shared
    conversation. It is one field.
    """
    task, seating = make_task(gold_index=0), make_seating()
    cfg = oc_config(critic_model="qwen/qwen3-8b")
    assert cfg.critic_model_for() == "qwen/qwen3-8b"
    assert cfg.debater_model != "qwen/qwen3-8b"

    client = solo_client()
    await run_self_critique(task, None, cfg, seating, client, error=error_spec())

    by_role = {c["meta"]["role"]: c["model"] for c in client.calls}
    assert by_role["critic"] == "qwen/qwen3-8b", "the critique is the critic's"
    assert by_role["injector"] == cfg.debater_model, "the draft is not"


def test_critic_model_defaults_to_the_drafter():
    """Unset, the agent criticises itself with its own capability, which is what
    'one agent' means."""
    assert oc_config().critic_model_for() == oc_config().debater_model


async def test_a_mixed_model_record_says_so(tmp_path):
    """A record whose steps come from different models is not literally one
    agent. The document says which wrote the critique rather than implying the
    drafter did — the same rule as the constructed note."""
    task, seating = make_task(gold_index=0), make_seating()
    writer = make_writer_with_error(
        tmp_path, task, oc_config(critic_model="qwen/qwen3-8b"), seating,
        error_spec(), arm="self_critique",
    )
    await run_self_critique(
        task, None, oc_config(critic_model="qwen/qwen3-8b"), seating,
        solo_client(), writer=writer, error=error_spec(),
    )
    writer.finish(status="completed")
    doc = (writer.dir / "transcript.md").read_text()
    assert "written by a **different model**" in doc
    assert "qwen/qwen3-8b" in doc


async def test_a_same_model_record_carries_no_such_note(tmp_path):
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="self_critique"
    )
    await run_self_critique(
        task, None, cfg, seating, solo_client(), writer=writer, error=error_spec()
    )
    writer.finish(status="completed")
    assert "different model" not in (writer.dir / "transcript.md").read_text()


async def test_a_judge_that_resists_the_steer_gets_no_mechanism_label(tmp_path):
    """A correct decision is not an error case, so neither value describes it.

    `unaided` asserts the procedure reached the wrong answer on its own — the
    opposite of what happened — and `steered` asserts the steer worked. Measured
    on the 50-case GPQA pilot, labelling these `unaided` put 25 non-error cells
    in that bucket beside 11 genuine ones, so `by_mechanism` read as 36 unaided
    errors when there were 11.
    """
    task, seating, cfg = make_task(gold_index=0), make_seating(), oc_config()
    writer = make_writer_with_error(
        tmp_path, task, cfg, seating, error_spec(), arm="debate"
    )

    class AlwaysResists(SequencedClient):
        async def complete(self, **kw):
            if kw["meta"].get("role") == "judge":
                # gold_index=0, choice_order=(0,1) -> choice 1 is the gold answer
                self.scripted = {**self.scripted, "judge": "Alice.\n\nAnswer: 1"}
            return await super().complete(**kw)

    result = await run_debate(
        task, None, cfg, seating, AlwaysResists(leaks=[LEAK_CLEAN], grades=[]),
        writer=writer, error=error_spec(),
    )
    assert result.verdict.correct is True, "the judge resisted the steer too"

    spec = json.loads((writer.dir / "error.json").read_text())
    assert spec["mechanism"] == "", "unlabelled, not mislabelled"
    # ...and the construction record still says what was attempted.
    construction = json.loads((writer.dir / "construction.json").read_text())
    assert construction["judge_steered"] is True
    assert construction["steer_worked"] is False
