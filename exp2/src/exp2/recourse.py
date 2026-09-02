"""Contesting a finished decision.

exp1 has no module like this: its baseline recourse was never implemented properly, and
DESIGN.md says so. The difficulty is that the three conditions are contested by
genuinely different mechanisms, and the record has to say which was used rather than
leaving a reader to infer it from a model name.

    debate                  a recourse judge — the same weak model — is asked what is
                            true of the original text under review. The burden is on the
                            challenger, and UPHOLD/OVERTURN is *derived* by comparing the
                            judge's conclusion with the decision rather than asked for.

    single, self_critique   the model that decided is handed the objection **in its own
                            conversation** and asked for its verdict again. This is what
                            DESIGN.md means by "a contest here is the user raising an
                            objection during chat". The verdict is parsed, not derived.

Those are not the same question, and the second sits exactly where models are most
sycophantic — being asked to contradict themselves. ``Ruling.form`` records which was
asked so the analysis can keep them apart, and `LLM_NOTES.md` records that without a
specious-objection control a high revision rate under the second form cannot be
distinguished from a re-decider that simply folds.

One challenge round per decision. A decline ends the contest: no ruling is sought,
because there is nothing to rule on. The comprehension probe still runs — it asks about
the record's readability, not about the objection.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from .arms import _split_solo
from .client import ChatClient
from .debate import _turn_from_completion
from .config import (
    FABRICATED_VARIANT,
    FINDINGS_VARIANT,
    JUDGMENT_FAMILY,
    JUDGMENT_VARIANT,
    PLACEHOLDER_VARIANT,
    SPECIOUS_VARIANT,
    DebateConfig,
    GradingConfig,
    arm_for_variant,
)
from .engine import DebateFailure, _complete_with_repair
from .persistence import load_findings
from .prompts import (
    build_agreement_messages,
    build_challenger_messages,
    build_comprehension_messages,
    build_gatekeeper_messages,
    build_recourse_debater_messages,
    build_recourse_judge_messages,
    PLACEHOLDER_DECISION_WORD,
    PLACEHOLDER_OBJECTION_RAW,
    PLACEHOLDER_OBJECTION_TEXT,
    PLACEHOLDER_PARSE_MODE,
    RULING_READER_ROLES,
    build_ruling_agreement_messages,
    build_solo_recourse_message,
    conversation_spent_a_repair,
    parse_debater_output,
    marks_private_text,
    parse_admissibility_output,
    parse_agreement_output,
    parse_comprehension_output,
    parse_defects,
    parse_finding_contests,
    parse_findings_reading_output,
    parse_findings_ruling_output,
    parse_objection_output,
    parse_ruling_agreement_materiality_output,
    parse_ruling_agreement_output,
    parse_ruling_output,
    apply_contest_lines,
    claimed_verdict_for_contests,
    derive_verdict,
    prose_conclusion_for_findings_reading,
    prose_conclusion_for_reading,
    ruling_prompt_form,
    parse_verdict_output,
    ruling_conclusion_line,
    strip_decision_lines,
)
from .types import (
    COMPREHENSION_SCALE_ID,
    ORDER,
    REVERSE,
    STANDS,
    Admission,
    Agreement,
    Challenge,
    Comprehension,
    Item,
    Ruling,
    RulingAgreement,
    Sides,
    Speaker,
    Transcript,
    Turn,
    challenge_stance,
    claimed_verdict_for,
    compose_transcript,
    count_words,
    recourse_pro_speaker,
    recourse_stance,
    render_transcript,
    resolve_ruling,
)

log = logging.getLogger(__name__)

# The comprehension probe is a measurement, not a generation: the same reader shown the
# same record should report the same rating, and sampling variation in a 1-5 Likert
# answer is noise in a number the analysis reports as a distribution. Named rather than
# written inline as 0.0 so that it is visibly a decision and not an omission — the
# challenger beside it deliberately runs hot (config.challenger_temperature).
COMPREHENSION_TEMPERATURE = 0.0

# Same rule for the line-vs-prose probe, and for the same reason: a classification that
# moved between two readings of one text would be noise in the number that decides
# whether the `contests` column means anything.
AGREEMENT_TEMPERATURE = 0.0

# THE GATE IS A MEASUREMENT, NOT A GENERATOR, so it runs at 0 for the reason the two
# probes above do: the same objection read twice must be read the same way, and an
# admissibility rate that moved with the sampler would be a property of the sampler.
# Nothing here is being asked to write anything; it is being asked whether a quotation is
# in a document.
GATEKEEPER_TEMPERATURE = 0.0
# And with native reasoning OFF, explicitly rather than by inheriting the run's setting.
# Every spec in this phase already sets `reasoning_effort = "off"`, and the reason is the
# transparency rule (`configs/default.toml`): a channel that moves an outcome and that no
# reader can see is exactly what this experiment refuses. Naming it at the call site means
# a spec that forgot it cannot quietly buy the gate a private channel the parties it
# gates never had.
GATEKEEPER_REASONING_EFFORT = "off"

# Published in place of an objection whose public section could not be located, on the
# same rule as arms.WITHHELD: the reply marked a boundary, the repair did not fix it,
# and guessing where the private half ends is worse than losing the text. The raw
# generation survives in ``Challenge.raw`` and in the run's wire log.
WITHHELD_OBJECTION = (
    "[this objection's public section could not be identified and is withheld]"
)


def _unparsed_objection(text: str) -> tuple[str, str | None, str, str]:
    """Last resort for a challenger reply still unparsable after its one repair.

    Routed to the ``unclear`` stance rather than raising. The challenger is the
    experiment's *subject*: making an unreadable reply fatal would let the role whose
    behaviour is being measured lose a whole contest to a DebateFailure, and its
    measured repair rate is 0%. An unclear stance seeks no ruling, is excluded from the
    rates and is counted in coverage, which is the honest reading of "it answered and I
    could not tell what it said".

    The decision word is ``None``, which is what ``unclear`` *is*: a reply whose
    direction could not be read. It used to be recorded as ``raised=True`` on the
    grounds that the challenger had written the word RAISED; under one relative line
    there is no word to have written, so ``raised`` follows the stance and is False.
    Every gate downstream reads ``stance`` either way, and what the model actually wrote
    is in ``raw``.
    """
    if marks_private_text(text):
        return "", None, WITHHELD_OBJECTION, "unparsed_unclear_withheld"
    return "", None, text.strip(), "unparsed_unclear"


@dataclass
class RecourseOutcome:
    challenge: Challenge
    ruling: Ruling | None
    comprehension: Comprehension | None
    # The contestability debate round's own turns. Empty under judge-only recourse, which
    # is what every run before 2026-08-30 did — an empty transcript rather than None
    # because `RecourseResult.transcript` has always been "the recourse turns only; empty
    # under judge-only recourse" and the two must go on meaning the same thing.
    transcript: Transcript = field(default_factory=Transcript)


async def generate_challenge(
    record: Any,
    config: DebateConfig,
    client: ChatClient,
    *,
    writer: Any | None = None,
) -> tuple[Challenge, list[dict[str, str]]]:
    """The stakeholder reads the published record and either objects or declines.

    Returns the challenge and the conversation it was written in, because the
    comprehension probe is asked in that same conversation.
    """
    messages = build_challenger_messages(
        record.item,
        config,
        record.challenger_view(),
        sides=record.sides,
        decision_verdict=record.verdict.verdict,
        decision_grounds=record.decision_grounds,
    )
    model = config.challenger_model_for()
    (thinking, word, text, parse_mode), completion, repairs, sent, _ = (
        await _complete_with_repair(
            client, model=model, messages=messages,
            temperature=config.challenger_temperature, config=config,
            meta={"role": "challenger", "speaker": None, "round": None,
                  "purpose": "challenge"},
            parse=parse_objection_output, role="challenger",
            word_limit=config.challenge_word_limit_for(),
            reasoning_effort=config.challenger_reasoning_effort,
            unrepaired=_unparsed_objection,
        )
    )
    limit = config.challenge_word_limit_for()
    if limit and count_words(text) > limit:
        log.warning("challenger wrote %d words over a %d-word limit",
                    count_words(text), limit)
    decision = record.verdict.verdict
    stance = challenge_stance(word)
    claimed = claimed_verdict_for(word, decision)
    # THE FINDINGS ARM'S CONTEST LIST, and its claimed verdict, which is DERIVED.
    #
    # `findings.json` is loaded from the decision directory rather than re-parsed out of
    # the judge's raw reply: the harness's parse is what every number in this arm is
    # built on, and a second parse here could disagree with it — the challenger would
    # then be contesting a finding 3 that is not the finding 3 the ruling applies to.
    # Its ABSENCE is loud (`DebateFailure`), not a silent empty list: a decision made
    # under the verdict form has no findings to contest, `DebateConfig` already refuses
    # that combination, and a cell that reached here without one is a wiring bug that
    # would otherwise produce a whole tree of objections against nothing.
    contests: list[dict[str, Any]] = []
    if config.challenger_variant == FINDINGS_VARIANT:
        stored = load_findings(record.directory)
        if stored is None:
            raise DebateFailure(
                f"{record.directory.name}: the findings challenger needs "
                "`findings.json` beside the decision it contests, and there is none. A "
                "decision made under `judge_form = \"verdict\"` has no numbered "
                "findings to contest."
            )
        contests = parse_finding_contests(
            text, stored.get("findings") or [],
            solution=record.item.solution,
            record=record.challenger_view().body,
        )
        # The claimed verdict is what the objection would produce if every well-formed
        # contest were granted, re-derived from the whole list — not the complement of
        # the decision. Under this arm `Decision: REVERSE` says only that something was
        # contested, and a contest can be entirely local and unable to move the verdict
        # (PREREG §5d). `claimed_verdict_for` would report a reversal the objection never
        # asked for.
        claimed = (claimed_verdict_for_contests(stored.get("findings") or [], contests)
                   if stance == "contests" else claimed)
    challenge = Challenge(
        text=text, origin="generated", raised=(stance == "contests"),
        # The arm the objection is RULED as. Read off the config rather than
        # hard-coded, so that a reader of the row can tell which challenger wrote it and
        # the analysis can refuse to pool two of them — but NOT the identity, because
        # `arm` selects the ruling prompt and the ruling reader: `arm_for_variant` maps
        # the specious auditor onto `judgment` so the materiality prompt applies to it
        # exactly as it applies to the real audit, and a control ruled in another form
        # would measure the form. What the objection actually IS survives beside it in
        # `specious`, and `Challenge.variant` is the column `index.jsonl` writes.
        arm=arm_for_variant(config.challenger_variant),
        # DESIGN.md's sycophancy control, recorded on the objection rather than inferred
        # from the spec that produced the tree: a specious objection pooled with a real
        # one would put a deliberately-invalid audit into the valid-objection rate.
        specious=config.challenger_variant == SPECIOUS_VARIANT,
        # The 2026-08-28 control whose falsity is a string comparison rather than an
        # instruction: every `Judgment says:` quotation invented, the `Record says:` one
        # real. Recorded here for the same reason `specious` is — an arm inferred from
        # the spec that produced the tree is an arm a re-run of one stage can lose.
        fabricated=config.challenger_variant == FABRICATED_VARIANT,
        # Only the judgment family is asked for a defect list, so only it is read for
        # one: running the parser over every arm would put an empty column on 5,724
        # neutral rows and, worse, could pick a stray "Type:" out of a stakeholder's
        # prose and report it as an audited defect.
        #
        # The grounds are handed over with the text so that each defect's
        # `quote_in_judgment` is settled here, at the moment the objection is read,
        # against the very text the challenger was shown. Deciding it later would mean
        # re-deriving that text from the tree and hoping the derivation matched.
        # Two different lists in one field, told apart by the arm and never read
        # together: judgment defects under `JUDGMENT_FAMILY`, findings contests under
        # `findings`. Every consumer of `defects` is gated on `JUDGMENT_VARIANT` and the
        # new ones on `FINDINGS_VARIANT`, so neither can be handed the other's shape.
        # Running either parser over every arm would put an empty column on thousands of
        # neutral rows and, worse, could pick a stray `Type:` or `Contests:` out of a
        # stakeholder's prose and report it as an audited defect.
        defects=(contests if config.challenger_variant == FINDINGS_VARIANT
                 else parse_defects(text, record.decision_grounds)
                 if config.challenger_variant in JUDGMENT_FAMILY else []),
        claimed_verdict=claimed, stance=stance,
        # Unreachable with one line, and recorded as False rather than dropped: a
        # column that reads 0 says the shape did not occur, a column that is absent
        # says nobody looked.
        contradictory=False,
        visibility="public", model=model, call_id=completion.call_id,
        finish_reason=completion.finish_reason, parse_mode=parse_mode,
        repair_attempts=repairs, thinking=thinking, raw=completion.content,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if stance != "contests":
        log.info("challenger stance %s (line %s against a %s decision)",
                 stance, word, decision)
    if writer is not None:
        writer.record_challenge(challenge)
    return challenge, sent


def placeholder_challenge(record: Any, config: DebateConfig, *,
                          writer: Any | None = None) -> Challenge:
    """The second-look control's objection. **No model call is made.**

    `prompts.PLACEHOLDER_OBJECTION_TEXT` is a fixed, content-free, well-formed judgment
    objection — one omission whose two quotations are the parenthetical placeholders the
    judgment prompt itself asks for — and it is the same text on every cell. The
    recourse judge therefore gets exactly what it got in the real arm (a second reading
    of the record, under the materiality prompt, prompted by an objection) and nothing
    else: no sentence is named, no claim is made, nothing is alleged that could be true
    of this judgment rather than any judgment. A judge that overturns on this overturns
    on nothing, and the difference between the two arms' after-states is the audit net of
    the second look — which is the confound `records/experiments/judgment-debate/PREREG.md`
    named and could not resolve.

    Everything a generated challenge derives, this derives the same way: the stance comes
    from `challenge_stance` and the claimed verdict from `claimed_verdict_for`, both
    given the same `REVERSE` word a challenger would have written. What differs is
    recorded rather than faked — `model` and `call_id` are None because there was no
    call, `thinking` is empty because no model deliberated, and `parse_mode` says
    `placeholder_no_call` rather than borrowing one of the parser's names.
    """
    if config.challenger_variant != PLACEHOLDER_VARIANT:
        raise ValueError(
            "placeholder_challenge is the placeholder arm's objection and must not be "
            f"written under challenger_variant={config.challenger_variant!r}: the cell "
            "would carry a control objection under an arm that claims a challenger "
            "wrote it."
        )
    decision = record.verdict.verdict
    challenge = Challenge(
        text=PLACEHOLDER_OBJECTION_TEXT, origin="generated", raised=True,
        # `judgment`, so the materiality ruling prompt and the materiality ruling reader
        # apply. `placeholder=True` beside it is what says no challenger wrote it.
        arm=arm_for_variant(config.challenger_variant),
        placeholder=True,
        defects=parse_defects(PLACEHOLDER_OBJECTION_TEXT, record.decision_grounds),
        claimed_verdict=claimed_verdict_for(PLACEHOLDER_DECISION_WORD, decision),
        stance=challenge_stance(PLACEHOLDER_DECISION_WORD),
        contradictory=False, visibility="public",
        # None, and deliberately not the configured challenger: no model produced this,
        # and a row naming one would make the arm look like a cheap challenger rather
        # than no challenger.
        model=None, call_id=None, finish_reason=None,
        parse_mode=PLACEHOLDER_PARSE_MODE, repair_attempts=0, thinking="",
        raw=PLACEHOLDER_OBJECTION_RAW,
    )
    if writer is not None:
        writer.record_challenge(challenge)
    return challenge


async def ask_comprehension(
    prior: list[dict[str, str]],
    challenge: Challenge,
    config: DebateConfig,
    client: ChatClient,
    *,
    writer: Any | None = None,
) -> Comprehension:
    """Asked after the objection, in the challenger's own conversation, always.

    Always, including after a decline: it is a question about whether the record could
    be followed, not about whether the reader found fault. Skipping it on declines would
    condition the measurement on the outcome it is meant to explain.
    """
    messages = build_comprehension_messages(prior, challenge.raw)
    model = config.comprehension_model_for()
    (score, justification, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=model, messages=messages,
            temperature=COMPREHENSION_TEMPERATURE, config=config,
            meta={"role": "comprehension", "speaker": None, "round": None,
                  "purpose": "comprehension"},
            parse=parse_comprehension_output, role="comprehension", word_limit=0,
        )
    )
    comprehension = Comprehension(
        score=score, scale=COMPREHENSION_SCALE_ID, justification=justification,
        asked_after_decline=challenge.stance != "contests", model=model,
        parse_mode=parse_mode,
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if writer is not None:
        writer.record_comprehension(comprehension)
    return comprehension


async def judge_prose_stance(
    challenge: Challenge,
    *,
    decision_verdict: str,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> Agreement:
    """Read one objection's prose and say which way it argues. Off the decision path.

    Run as its own stage after every contest, never inside one: it must not be able to
    change what the challenger wrote or what a recourse judge was handed, and keeping it
    in a separate pass makes that structural rather than a promise. It is also
    re-runnable over finished contest directories for nothing but the grader's cents.

    Temperature 0, for the same reason the comprehension probe is at 0 — this is a
    measurement, and the same text read twice should be read the same way. The cap is
    ``grading.max_tokens`` rather than the run's: the answer is one line and a sentence,
    and a 16k ceiling on a probe that costs cents only buys a runaway.

    ``line_word`` is taken from the recorded stance rather than re-parsed, because the
    line was stripped out of ``challenge.text`` before it was written — which is also
    why the reader cannot see it and the reading is independent of it.
    """
    # Chosen off the CHALLENGE's own arm, never off the config: this stage is
    # re-runnable over finished trees, including a tree some other spec wrote, and a
    # judgment objection read with the verdict-shaped question would answer NEITHER for
    # exactly the replies the variant exists to produce.
    messages = build_agreement_messages(
        challenge.text, decision_verdict=decision_verdict,
        mode=("judgment" if challenge.arm == JUDGMENT_VARIANT else "verdict"),
    )
    (prose, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=grading.grader_model, messages=messages,
            temperature=AGREEMENT_TEMPERATURE, config=config,
            meta={"role": "agreement", "speaker": None, "round": None,
                  "purpose": "agreement"},
            parse=parse_agreement_output, role="agreement", word_limit=0,
            max_tokens=grading.max_tokens,
        )
    )
    word = {"contests": REVERSE, "declined": STANDS}.get(challenge.stance)
    return Agreement(
        prose_stance=prose, line_word=word, reasoning=reasoning,
        model=grading.grader_model,
        parse_mode=parse_mode, raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


# --------------------------------------------------------------------------- #
# the contestability debate round
# --------------------------------------------------------------------------- #
#
# DESIGN.md's contestability-debate-round ablation, implemented 2026-08-30 for
# `judgment-debate-6`. Every recourse ruling before it was weak-against-weak with nobody
# answering the objection; here the two ORIGINAL debaters each reply once, simultaneously,
# and the weak recourse judge rules on the argued exchange.

# The parent's settings this round has to match, and the reason the list is a constant:
# the round continues a debate that another run paid for, so a spec whose debaters,
# temperature, word limit or token budget differ from that run's would splice a turn by a
# different party into a record that says all four turns are the same debate. `n_rounds`
# is here because the round number is derived from it, and `turn_style` because the whole
# no-speaking-order claim rests on it.
_SAME_DEBATE_KEYS: tuple[str, ...] = (
    "debater_model", "debater_model_b", "debater_temperature", "word_limit",
    "n_rounds", "turn_style", "reasoning_effort", "generation_max_tokens",
)


def _assert_same_debate(parent: DebateConfig, config: DebateConfig,
                        *, keys: tuple[str, ...] = _SAME_DEBATE_KEYS) -> None:
    """Refuse to continue a debate under settings that are not the ones it was argued
    under. Loudly, and naming every field that differs, because the failure this prevents
    produces a record that looks entirely ordinary."""
    differ = [(key, getattr(parent, key), getattr(config, key)) for key in keys
              if getattr(parent, key) != getattr(config, key)]
    if differ:
        detail = "; ".join(f"{k}: the debate was argued at {a!r}, this spec says {b!r}"
                           for k, a, b in differ)
        raise DebateFailure(
            "a contest round continues a debate another run argued, so it must be "
            f"argued under that run's settings — {detail}"
        )


async def _recourse_turn(
    record: Any,
    challenge: Challenge,
    config: DebateConfig,
    client: ChatClient,
    transcript: Transcript,
    *,
    speaker: Speaker,
    round_number: int,
) -> Turn:
    """One debater's reply to the objection. `debate._debater_turn`, one prompt over.

    ``role="debater"`` because `engine.REPAIR_INSTRUCTIONS` is keyed on the role and has
    no `recourse_debater` entry — a repair asked for under a role the table does not know
    raises, and the one format repair would be spent on a call that could not succeed.
    The WIRE meta says `recourse_debater`, so accounting, `artifacts_full` and the index
    can still tell the round-4 turns from the debate's own; the two are deliberately
    different names for deliberately different questions.
    """
    sides = record.sides
    messages = build_recourse_debater_messages(
        record.item, sides, config, transcript,
        speaker=speaker, round_number=round_number,
        decision_verdict=record.verdict.verdict,
        judgment=record.decision_grounds,
        objection=challenge.text,
    )
    model = sides.model_for(speaker, config.debater_model, config.debater_model_b)
    (thinking, argument, parse_mode), completion, repairs, _, repair_kind = (
        await _complete_with_repair(
            client,
            model=model,
            messages=messages,
            temperature=config.debater_temperature,
            config=config,
            meta={
                "role": "recourse_debater", "speaker": speaker.value,
                "round": round_number, "purpose": "recourse_turn",
                "stance": recourse_stance(sides, speaker, record.verdict.verdict),
                "model_side": "b" if model == config.debater_model_b else "a",
            },
            parse=parse_debater_output,
            role="debater",
            word_limit=config.word_limit,
            # The record-text cap, not the judge's. Without it a round-4 turn would run
            # at `max_tokens` — 16,384 in every spec of this phase — and a truncation
            # would cost the cell rather than being caught by the budget repair.
            max_tokens=config.generation_max_tokens,
            public_label="Argument",
        )
    )
    return _turn_from_completion(
        thinking, argument, parse_mode, completion,
        repairs=repairs, repair_kind=repair_kind,
        round_number=round_number, speaker=speaker, side=sides.side_for(speaker),
        word_limit=config.word_limit,
    )


async def hear_exchange(
    record: Any,
    challenge: Challenge,
    config: DebateConfig,
    client: ChatClient,
    *,
    writer: Any | None = None,
) -> Transcript:
    """Both original debaters reply to the objection, once, simultaneously.

    Returns the round's OWN turns — the recourse side of `Transcript.split_at` — not the
    composed four-round transcript. The caller passes it to `_rule_by_judge`, which puts
    it in front of the judge as an `<exchange>`, and to the writer, which stores it as
    `recourse_transcript.json`.

    FOUR REFUSALS, all loud:

    * a SOLO record. There were no advocates to argue the objection, and inventing two
      would put a debate in front of a judge told it is ruling on a solo decision.
    * an objection that is not a JUDGMENT-arm one. The exchange argues about the
      judgment, and the object-level ruling prompt does not show one.
    * `turn_style = "sequential"`. The round is one simultaneous turn each, which is
      what makes "neither reply conditions on the other" true; a sequential spec would
      quietly reintroduce a speaking-order effect into a paired comparison.
    * a parent whose debate settings differ from this spec's (`_assert_same_debate`).

    THE ROUND NUMBER CONTINUES THE PARENT'S, so `compose_transcript`, `all_turns` and
    `visible_to` all do the right thing with no round-aware special case: the parent
    debated rounds 1..n, this is round n+1, and `visible_to` therefore hands each debater
    the parent debate and nothing from its own round.

    A FAILED ROUND COMMITS WHAT COMPLETED BEFORE RAISING, exactly as `debate._run_round`
    does and for the same reason: losing a paid generation because the other debater
    failed is an own goal, and the partial exchange is still a true record of what was
    said. The cell then fails and is re-attempted from scratch in a NEW directory — there
    is no half-round resume, and the spec comment says so, because a resume that ruled on
    one reply would be a different protocol wearing this one's name.
    """
    if record.transcript is None:
        raise DebateFailure(
            "a contest round needs the two debaters who argued the decision, and this "
            "decision was reached by a single agent working alone; there is nobody to "
            "argue the objection. Use recourse_rounds = 0 for the solo conditions."
        )
    if challenge.arm != JUDGMENT_VARIANT:
        raise DebateFailure(
            f"a contest round is implemented for the judgment arm only, got "
            f"{challenge.arm!r}. The round argues about the JUDGMENT and the ruling "
            "prompt for every other arm tells the judge to disregard it."
        )
    if config.turn_style != "simultaneous":
        raise DebateFailure(
            f"a contest round is one simultaneous turn each, got turn_style="
            f"{config.turn_style!r}. Under sequential the second debater would answer "
            "the first, which is a different protocol and not the one being measured."
        )
    _assert_same_debate(record.config, config)

    boundary = record.config.n_rounds
    last = max(turn.round for turn in record.transcript.all_turns())
    if last != boundary:
        raise DebateFailure(
            f"the stored debate ends at round {last} but its config says "
            f"{boundary} rounds; the contest round's number would be wrong"
        )
    round_number = boundary + 1
    # Composed rather than mutated in place: the parent transcript belongs to a record
    # this run must not write to, and `compose_transcript` is also the one place that
    # checks the new turns really do follow the parent's rounds.
    composed = compose_transcript(record.transcript, Transcript())

    async def turn_for(speaker: Speaker) -> Turn:
        return await _recourse_turn(
            record, challenge, config, client, composed,
            speaker=speaker, round_number=round_number,
        )

    results = await asyncio.gather(
        *(turn_for(speaker) for speaker in ORDER), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Turn):
            composed.add(result)
            if result.parse_mode != "strict":
                log.warning("recourse round %d %s parsed as %s",
                            result.round, result.speaker.value, result.parse_mode)
            if writer is not None:
                # NOT `writer.record_turn`, which writes `transcript.json` — a contest
                # directory holding one would load as a DECISION whose debate is two
                # turns long.
                _, own = composed.split_at(boundary)
                writer.record_recourse_turn(own)
    for result in results:
        if isinstance(result, BaseException):
            # Unwrapped, so an enclosing asyncio.timeout still recognises its own
            # cancellation rather than seeing a DebateFailure it cannot attribute.
            if isinstance(result, asyncio.CancelledError):
                raise result
            raise DebateFailure(
                f"contest round {round_number} failed: {result}") from result

    _, own = composed.split_at(boundary)
    return own


async def _rule_findings_by_judge(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient,
    *, writer: Any | None = None,
) -> Ruling:
    """The findings arm's ruling: per contest, absolute, and the verdict re-derived.

    **The judge is never asked for a verdict, and never for UPHOLD/OVERTURN.** It answers
    one line per contest in the findings' own vocabulary — `Contest 1 (Finding 3): FLAW`
    — `apply_contest_lines` writes those rulings into the list, and `derive_verdict`
    re-derives the verdict from the whole list, contested findings and uncontested ones
    together. UPHOLD/OVERTURN is then the comparison of that with the parent, computed
    here, and `Ruling.__post_init__` re-derives it and refuses the record if the two ever
    disagree — the same invariant every other form satisfies.

    That is the `stated_conclusion` change of 2026-08-27 taken one step further. There
    the judge still had to state a fact about the whole text; here it states a fact about
    one claim about one passage, which is the smallest question this experiment has put
    to a recourse judge and the one furthest from the vocabulary collision that made the
    relative word unreliable (8 contradictions in 12 hand-checked rulings).

    ``n_contests`` is bound into the parser so a MISSING line is a parse failure: the
    lines are the ruling, and a gap would silently leave a contested finding standing on
    a ruling nobody wrote. It buys the one format repair — repair role
    `recourse_judge_findings`, wire role `recourse_judge`, so accounting is untouched —
    and then fails the cell.

    `findings.after.json` is written beside `ruling.json` so a reader can check the
    derivation by counting rather than take it on trust.
    """
    stored = load_findings(record.directory) or {}
    findings = stored.get("findings") or []
    contests = list(challenge.defects or [])
    messages = build_recourse_judge_messages(
        record.item, record.sides, record.challenger_view(),
        decision_verdict=record.verdict.verdict, objection=challenge.text,
        judgment=record.decision_grounds, arm=challenge.arm,
    )
    n_contests = len(contests)

    def parse(text: str):
        return parse_findings_ruling_output(text, n_contests)

    (lines, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=config.recourse_judge_model_for(), messages=messages,
            temperature=config.judge_temperature, config=config,
            meta={"role": "recourse_judge", "speaker": None, "round": None,
                  "purpose": "rule"},
            parse=parse, role="recourse_judge_findings",
            word_limit=config.word_limit,
        )
    )
    after = apply_contest_lines(findings, contests, lines)
    parent = record.verdict.verdict
    verdict = derive_verdict(after)
    word = "UPHOLD" if verdict == parent else "OVERTURN"
    if writer is not None:
        writer.record_findings_after(after, verdict=verdict, parent_verdict=parent,
                                     contest_lines=lines)
    return Ruling(
        form="derived_findings", ruling=word, protocol=config.recourse_protocol,
        prompt_form=ruling_prompt_form(challenge.arm),
        parent_verdict=parent, verdict=verdict, parse_mode=parse_mode,
        # The judge's own lines, joined, so a reader of one `ruling.json` can check the
        # derived verdict against the sentences it was derived from — the same reason
        # `stated_conclusion` records its `Conclusion:` line.
        conclusion_line="\n".join(
            f"Contest {index}: {lines[index]}" for index in sorted(lines)),
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(verdict == record.item.gold_verdict), repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


async def _rule_by_judge(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient,
    *, exchange: Transcript | None = None, writer: Any | None = None,
) -> Ruling:
    """A third party states its conclusion; UPHOLD/OVERTURN is derived from it.

    Reached by `debate` under the historical `per_condition` routing and by every
    condition under `third_party`. The judge is shown the record the challenger was
    shown, whichever shape it has, so a solo cell ruled here is ruled on the decision
    that was actually made.

    **The relative word is never asked for.** Until 2026-08-27 the judge ended on
    `Ruling: UPHOLD|OVERTURN` and the verdict was derived from that. The re-contest
    measured what it cost: a hand check of 12 rulings on FLAWED parents found 8 whose
    line contradicted the judge's own reasoning, and 52 of the 62 phantom objections —
    objections whose prose agreed with the verdict — were overturned. It is the pilot-2
    vocabulary collision one layer down: "the objection is valid" and "the text is
    flawed" both map onto OVERTURN, whichever way the decision went. So the judge is
    asked the object-level question instead, in the ONE vocabulary it cannot mistranslate
    — does the original text contain a flaw — and this function does the comparison the
    judge was getting wrong. `outputs/rerule-smoke/review.md` is the three-variant smoke
    that chose the wording; DESIGN.md records the decision.

    **Which user prompt is sent depends on the OBJECTION'S arm.** A judgment-variant
    objection alleges defects in the judgment, and the object-level prompt tells the
    judge to disregard the decision's reasoning — the only thing that objection is
    about. So that arm gets `RECOURSE_JUDGE_USER_JUDGMENT`, which shows the judgment and
    asks the two-step materiality question, and every other arm gets the prompt it
    always got. `Ruling.prompt_form` records which, because both produce a
    `stated_conclusion` ruling and nothing else on the record distinguishes them.

    The arithmetic goes through `resolve_ruling` in the same direction as before, so the
    `Ruling` invariant is checked rather than asserted: `ruling` is chosen so that
    `resolve_ruling(ruling, parent) == verdict`, and `Ruling.__post_init__` re-derives it
    and refuses the record if the two ever disagree.

    ``exchange`` is the contestability debate round's two replies. ``None`` — the
    default, and what every ruling before 2026-08-30 was made under — sends byte-identical
    messages to what this function has always sent, and records `recourse_rounds = 0`
    with no pro speaker and no exchange hash. Given one, the judge is shown the two
    arguments in the one block `RECOURSE_JUDGE_USER_JUDGMENT_EXCHANGE` adds and the
    ruling records which exchange it ruled on: the sha256 is of the rendered arguments,
    so a `recourse_transcript.json` that were ever edited afterwards would no longer
    match the ruling that was made from it.
    """
    if challenge.arm == FINDINGS_VARIANT:
        return await _rule_findings_by_judge(record, challenge, config, client,
                                             writer=writer)
    # `arm` is the OBJECTION's arm and not the config's variant. A re-rule pass reads
    # finished objections out of another tree, so the config in front of it need not be
    # the one that wrote them; keying on the challenge is what makes each objection ruled
    # in the form it was written in — see `build_recourse_judge_messages`.
    messages = build_recourse_judge_messages(
        record.item, record.sides, record.challenger_view(),
        decision_verdict=record.verdict.verdict, objection=challenge.text,
        judgment=record.decision_grounds, arm=challenge.arm, exchange=exchange,
    )
    turns = exchange.all_turns() if exchange is not None else []
    pro = (recourse_pro_speaker(record.sides, record.verdict.verdict).value
           if turns else None)
    (conclusion, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=config.recourse_judge_model_for(), messages=messages,
            temperature=config.judge_temperature, config=config,
            meta={"role": "recourse_judge", "speaker": None, "round": None,
                  "purpose": "rule"},
            parse=parse_ruling_output, role="recourse_judge",
            word_limit=config.word_limit,
        )
    )
    parent = record.verdict.verdict
    word = "UPHOLD" if conclusion == parent else "OVERTURN"
    verdict = resolve_ruling(word, parent)
    return Ruling(
        form="stated_conclusion", ruling=word, protocol=config.recourse_protocol,
        prompt_form=ruling_prompt_form(challenge.arm),
        # DERIVED from the exchange in hand, never from the config: a cell whose round
        # failed and was ruled anyway would otherwise record a round it never heard.
        recourse_rounds=1 if turns else 0,
        recourse_pro_speaker=pro,
        recourse_exchange_sha256=(
            hashlib.sha256(render_transcript(turns).encode("utf-8")).hexdigest()
            if turns else None),
        parent_verdict=parent, verdict=verdict, parse_mode=parse_mode,
        conclusion_line=ruling_conclusion_line(completion.content),
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(verdict == record.item.gold_verdict), repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


def mechanical_agreement(challenge: Challenge) -> Agreement:
    """The findings arm's line-vs-prose reading, computed rather than bought.

    The `agreement` stage exists because the challenger's `Decision:` line is one relative
    token and nothing mechanical could check it against the prose that followed. Under
    this arm something mechanical CAN: the objection's argument is a numbered list, the
    parser reads it, and "did this reply actually contest anything" is
    `n_well_formed > 0` — a string comparison a reader can redo, not a grader's opinion.
    So no call is made, and `phantom_contest` becomes exactly the disagreement between
    the line and the list: REVERSE with nothing well formed under it, or STANDS with a
    contest under it.

    It is a real `Agreement`, so `agrees`, `phantom_contest` and every consumer are
    unchanged, and `parse_mode` says `mechanical` rather than borrowing one of the
    parser's names — nothing was parsed here, because nothing was generated. It is NEVER
    pooled with the Haiku column of jd3–jd6: the two measure different things and the
    analysis caveat says so.

    Its two blind spots are stated in PREREG §7 and scored by hand rather than papered
    over: a well-formed contest whose `Why` argues the finding is RIGHT, and a STANDS
    whose prose attacks a finding without writing an entry.
    """
    well_formed = sum(1 for contest in (challenge.defects or [])
                      if not contest.get("void"))
    stance = "WRONG" if well_formed else "RIGHT"
    return Agreement(
        prose_stance=stance,
        line_word={"contests": REVERSE, "declined": STANDS}.get(challenge.stance),
        reasoning=(f"mechanical: {well_formed} well-formed contest"
                   f"{'' if well_formed == 1 else 's'} in the objection's own list"),
        model="", parse_mode="mechanical", raw="", call_id="", finish_reason=None,
    )


async def judge_ruling_prose(
    ruling: Ruling,
    *,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> RulingAgreement:
    """Read one ruling's reasoning and say what it concludes. Off the decision path.

    The exact shape of `judge_prose_stance`, one layer down, and for the same reason: a
    column that nothing can falsify is not a measurement. There the column is the
    challenger's `contests` label; here it is the judge's own line, and the re-contest
    showed that line to be the weaker of the two — 8 contradictions in 12 hand-checked
    rulings against roughly 1 in 2 phantom objections.

    Run as its own stage over finished contest directories, never inside a contest: it
    must not be able to change what a judge was handed or what it wrote, and a separate
    pass makes that structural rather than a promise. It also runs over trees this code
    did not write — the sweep's 1,122 rulings and the re-contest's 464, every one under
    the old `Ruling:` line — which is how the two instruments get compared on the same
    scale.

    Temperature 0 and `grading.max_tokens`, as the agreement probe: this is a
    measurement, the same text read twice should read the same way, and a 16k ceiling on
    a probe that costs cents only buys a runaway.

    `line_conclusion` is the ruling's recorded verdict rather than a re-parse of its raw
    text — under `stated_conclusion` that verdict is exactly what the line said, and
    under the older forms it is what the record says the ruling amounted to. The reader
    never sees it, or any decision line: `strip_decision_lines` takes both vocabularies
    off the prose first, so the reading cannot be steered by the answer.
    """
    # Which question to ask is a property of the RULING, not of the config: a materiality
    # ruling's prose argues about the defect and reaches the text only by implication, so
    # the object-level reader mis-reads its upholds. Read off `prompt_form` so that a
    # finished tree — or a mixed one — is always asked the question its rulings answer.
    mode = ruling.prompt_form
    materiality = mode == "materiality"
    findings_mode = mode == "findings"
    messages = build_ruling_agreement_messages(
        strip_decision_lines(ruling.reasoning), mode=mode)
    (answer, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=grading.grader_model, messages=messages,
            temperature=AGREEMENT_TEMPERATURE, config=config,
            # The WIRE role is `ruling_reader` for all three — accounting reads `meta`,
            # and the readings are one probe. Only the repair is per-question.
            meta={"role": "ruling_reader", "speaker": None, "round": None,
                  "purpose": "ruling_agreement"},
            parse=(parse_findings_reading_output if findings_mode
                   else parse_ruling_agreement_materiality_output if materiality
                   else parse_ruling_agreement_output),
            role=RULING_READER_ROLES[mode], word_limit=0,
            max_tokens=grading.max_tokens,
        )
    )
    # STANDS -> the parent's own verdict, CHANGED -> the other, NEITHER unchanged. Done
    # here so `prose_conclusion` keeps its three values and `mismatch` keeps its meaning.
    #
    # The findings reader answers a third question — do the reasons support the lines —
    # and is translated against the RULING's own derived verdict rather than the
    # parent's: under that form the lines ARE the ruling and the verdict is derived from
    # them, so CONSISTENT means the reasoning amounts to the verdict the ruling reached.
    if findings_mode:
        prose = prose_conclusion_for_findings_reading(answer, ruling.verdict)
    elif materiality:
        prose = prose_conclusion_for_reading(answer, ruling.parent_verdict)
    else:
        prose = answer
    return RulingAgreement(
        prose_conclusion=prose, line_conclusion=ruling.verdict, reasoning=reasoning,
        ruling_form=ruling.form, parent_verdict=ruling.parent_verdict,
        model=grading.grader_model,
        parse_mode=parse_mode, raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


def _parse_solo_ruling(text: str) -> tuple[str, str, str]:
    """``(verdict, grounds, parse_mode)`` for a re-decision made in the conversation.

    The reply is in the solo two-section format, so it is split like any other solo
    step: ``parse_verdict_output`` alone would take everything before the verdict line
    as the grounds, ``Thinking:`` block included, and the readable record publishes the
    grounds. The verdict line is then taken off the grounds the way the recourse
    judge's ruling line is, so both forms' grounds are the same kind of text.
    """
    _, reasoning, parse_mode = _split_solo(text)
    word, grounds, _ = parse_verdict_output(reasoning)
    return word, grounds, parse_mode


async def _rule_in_conversation(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient
) -> Ruling:
    """Solo: the deciding model reconsiders, in the conversation that decided.

    The conversation is replayed exactly as recorded — including any turns a format
    repair added — and one user turn is appended. Rebuilding it from scratch instead
    would make this a fresh judgement by a model that happens to share a name with the
    decider, which is a different mechanism from the one DESIGN.md describes.
    """
    if not record.messages:
        raise ValueError(
            f"{record.directory.name}: no conversation.json to contest; the solo "
            "contest replays the conversation that produced the decision"
        )
    # The conversation is replayed verbatim, so a repair's correction is still in
    # context. `conversation_spent_a_repair` reads that off the messages themselves,
    # which is the only record of what was said, and the appended turn then restates the
    # two-section format. This call is the one that produces `changed_the_decision`, and
    # `single` has one stage, so nothing else can reach it.
    messages = [
        *record.messages,
        build_solo_recourse_message(
            record.sides, challenge.text,
            after_repair=conversation_spent_a_repair(record.messages),
        ),
    ]
    (word, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=config.debater_model, messages=messages,
            temperature=config.debater_temperature, config=config,
            meta={"role": "recourse_solo", "speaker": None, "round": None,
                  "purpose": "rule"},
            parse=_parse_solo_ruling, role="recourse_solo",
            word_limit=config.word_limit,
        )
    )
    return Ruling(
        form="restated_verdict", ruling=None, protocol="in_conversation",
        parent_verdict=record.verdict.verdict, verdict=word, parse_mode=parse_mode,
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(word == record.item.gold_verdict), repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )


# Mirrors arms.DECIDERS: one table, so a condition cannot be decided one way and
# contested another by accident. This is the **historical** routing — what every paid
# run up to and including the first full sweep did — and `config.recourse_form`
# selects it by name, `"per_condition"`.
RECOURSERS = {
    "debate": _rule_by_judge,
    "single": _rule_in_conversation,
    "self_critique": _rule_in_conversation,
}

# The settled protocol (DESIGN.md): the appeal is heard by a weak third party in every
# condition, so no decider ever adjudicates its own appeal. The sweep is why — the
# recourse judge overturned 24% of *phantom* objections and the strong re-decider 0-4%,
# so the two forms are not the same instrument and running one per condition made the
# routing part of the result.
_THIRD_PARTY_RECOURSERS = {
    "debate": _rule_by_judge,
    "single": _rule_by_judge,
    "self_critique": _rule_by_judge,
}


def _no_conversation_to_replay(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient
) -> Ruling:
    raise ValueError(
        "recourse_form='in_conversation' cannot rule on a debate decision: there is no "
        "single decider whose conversation could be replayed. Use 'third_party', or "
        "run the ablation on the solo conditions only."
    )


# The opposite-corner ablation DESIGN.md keeps as a separately-reported form: the
# decider re-decides wherever there is a conversation to replay. Wired and tested, not
# run. `debate` raises rather than falling back to the judge, because a silent fallback
# would make this form mean "third_party for debate" and the whole point of naming it is
# that the two forms are different instruments.
_IN_CONVERSATION_RECOURSERS = {
    "debate": _no_conversation_to_replay,
    "single": _rule_in_conversation,
    "self_critique": _rule_in_conversation,
}

_RECOURSER_TABLES = {
    "per_condition": RECOURSERS,
    "third_party": _THIRD_PARTY_RECOURSERS,
    "in_conversation": _IN_CONVERSATION_RECOURSERS,
}


async def judge_admissibility(
    record: Any,
    challenge: Challenge,
    *,
    config: DebateConfig,
    grading: GradingConfig,
    client: ChatClient,
) -> Admission:
    """Is this objection admissible — does it allege at least one REAL defect?

    POST HOC (2026-08-28). ONE call per contested cell, and it changes nothing: M1's
    ruling is already on the record and is copied beside this file untouched. What the
    answer decides is whether that ruling is COUNTED, and that decision is made in the
    index and in the derivation, never in the tree's own `ruling.json`.

    Off the decision path in the accounting sense too — `role="gatekeeper"` is in
    `accounting.OFF_PATH_ROLES` — because a gate that could inflate the condition it
    gates would be measuring itself.

    The gatekeeper is shown the record the challenger was shown, the judgment it audited,
    and the objection whole. It is NOT shown the recourse judge's ruling, the grader's
    verdict, or the harness's own quote-check findings: an admissibility rate that had
    seen any of those would be partly a restatement of them, and the mechanical gate is
    reported as its own row precisely so the two can be compared.

    ``temperature`` and ``reasoning_effort`` are pinned here rather than taken from the
    spec — see the two constants above.
    """
    model = config.gatekeeper_model
    if not model:
        # Refused rather than defaulted. Every other model field in DebateConfig falls
        # back to a neighbour when unset; this one must not, because the neighbour is the
        # judge whose own judgment is under appeal.
        raise ValueError(
            "judge_admissibility needs `gatekeeper_model` in the spec's [debate] table. "
            "It has no default and inherits from nothing: a gate that fell back to "
            "`judge_model` would have the judge decide whether the appeal against its "
            "own judgment is heard."
        )
    messages = build_gatekeeper_messages(
        record.item, record=record.challenger_view().body,
        judgment=record.decision_grounds,
        decision_verdict=record.verdict.verdict, objection=challenge.text,
        n_defects=len(challenge.defects),
    )
    (findings, line_admitted, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=model, messages=messages,
            temperature=GATEKEEPER_TEMPERATURE, config=config,
            meta={"role": "gatekeeper", "speaker": None, "round": None,
                  "purpose": "admissibility"},
            parse=parse_admissibility_output, role="gatekeeper", word_limit=0,
            reasoning_effort=GATEKEEPER_REASONING_EFFORT,
            max_tokens=grading.max_tokens,
        )
    )
    # The gatekeeper's per-defect lines joined to the challenger's own defect list, by the
    # number both of them used — the same join `grading._grade_judgment` makes, and kept
    # rather than dropped when the number is out of range: a finding about a defect nobody
    # alleged is evidence about the gatekeeper, and hiding it would make `findings_n`
    # disagree with the objection it came from for no visible reason.
    joined: list[dict[str, Any]] = []
    for finding in findings:
        alleged = (challenge.defects[finding["index"] - 1]
                   if 1 <= finding["index"] <= len(challenge.defects) else {})
        joined.append({
            "index": finding["index"],
            "type": alleged.get("type"),
            "real": finding["real"],
            "reason": finding["reason"],
            "alleged": bool(alleged),
        })
    result = Admission(
        findings=joined, line_admitted=line_admitted, model=model,
        parse_mode=parse_mode, raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, reasoning=reasoning,
        repair_attempts=repairs, native_reasoning=completion.reasoning or "",
        reasoning_withheld=completion.reasoning_withheld,
    )
    if result.line_mismatch:
        # Neither repaired nor clamped, exactly as `JudgmentGrade`'s equivalent is not:
        # `admitted` is the conjunction of the findings, which are the judgements a reader
        # can check, and the flag is what bounds how often the gate's own summary line
        # disagreed with them.
        log.warning(
            "%s: gatekeeper's line says %s and its per-defect findings say %s",
            record.item.item_id, "ADMITTED" if line_admitted else "REFUSED",
            "ADMITTED" if result.admitted else "REFUSED",
        )
    return result


def recoursers_for(recourse_form: str) -> dict[str, Any]:
    """The condition → ruler table named by ``config.recourse_form``.

    A lookup rather than a branch at the call site, so the three forms are visible
    together and the historical one keeps its own name in the record.
    """
    try:
        return _RECOURSER_TABLES[recourse_form]
    except KeyError:
        raise ValueError(
            f"unknown recourse_form {recourse_form!r}; expected one of "
            f"{tuple(_RECOURSER_TABLES)}"
        ) from None


async def _hear_if_asked(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient,
    *, writer: Any | None = None,
) -> Transcript:
    """The contest round, when the spec asks for one; an empty transcript otherwise.

    Kept out of `run_recourse`'s two branches so that "does this run hear a round" is one
    decision in one place. It refuses a solo condition here rather than in
    `hear_exchange`'s own check, because at this level the CONDITION is what is wrong —
    `recourse_rounds = 1` on a spec that runs `single` is a spec that asked for advocates
    for a decision that never had any, and the error should say that rather than "this
    record has no transcript".
    """
    if not config.recourse_rounds:
        return Transcript()
    if record.condition != "debate":
        raise DebateFailure(
            f"recourse_rounds = {config.recourse_rounds} on condition "
            f"{record.condition!r}: only a debate has two advocates who can argue the "
            "objection. The contest step has to be identical across conditions, so a "
            "spec that hears a round must run the debate condition alone."
        )
    return await hear_exchange(record, challenge, config, client, writer=writer)


async def _ruled_by(recoursers, record: Any, challenge: Challenge,
                    config: DebateConfig, client: ChatClient,
                    exchange: Transcript, *,
                    writer: Any | None = None) -> Ruling:
    """Route to the condition's ruler, handing the exchange to the one that takes one.

    Only `_rule_by_judge` hears an exchange. The solo re-decider is the model that made
    the decision reconsidering in its own conversation, and there is no exchange to hand
    it — `_hear_if_asked` has already refused that combination, so this is the belt to
    its braces rather than a second policy.
    """
    ruler = recoursers[record.condition]
    if ruler is _rule_by_judge:
        # The writer goes only to the third-party judge, because it is the only ruler
        # with a derivation to record: the findings branch writes `findings.after.json`
        # beside its `ruling.json`. The solo re-decider states a verdict and has nothing
        # to derive, and handing it a writer would give it a file it never fills.
        return await ruler(record, challenge, config, client,
                           exchange=exchange if exchange.all_turns() else None,
                           writer=writer)
    return await ruler(record, challenge, config, client)


async def run_recourse(
    record: Any,
    config: DebateConfig,
    client: ChatClient,
    *,
    rule: bool = True,
    writer: Any | None = None,
) -> RecourseOutcome:
    """Generate an objection, ask about comprehension, and rule if there is anything to."""
    recoursers = recoursers_for(config.recourse_form)
    if record.condition not in recoursers:
        raise ValueError(f"no recourse mechanism for condition {record.condition!r}")

    if config.challenger_variant == PLACEHOLDER_VARIANT:
        # The arm's whole cost is the ruling. No challenger call, and no comprehension
        # probe either: that probe asks the reader how readable the record was, and
        # there is no reader here — asking the question would buy a rating of a document
        # nobody read, on every cell, for the price of a second full pass.
        challenge = placeholder_challenge(record, config, writer=writer)
        if not rule:
            return RecourseOutcome(challenge=challenge, ruling=None, comprehension=None)
        exchange = await _hear_if_asked(record, challenge, config, client,
                                        writer=writer)
        ruling = await _ruled_by(recoursers, record, challenge, config, client,
                                 exchange, writer=writer)
        if writer is not None:
            writer.record_ruling(ruling)
        return RecourseOutcome(challenge=challenge, ruling=ruling, comprehension=None,
                               transcript=exchange)

    challenge, conversation = await generate_challenge(
        record, config, client, writer=writer
    )
    comprehension = await ask_comprehension(
        conversation, challenge, config, client, writer=writer
    )

    if challenge.stance != "contests" or not rule:
        # No ruling.json is written, and its absence is what lets the analysis tell "the
        # decision was never objected to" from "the decision survived an objection".
        #
        # The gate is the STANCE, not ``raised``. An objection that agrees with the
        # verdict it is objecting to puts nothing to a recourse judge — the pilot ran
        # 51 such rulings and the judges correctly upheld almost all of them, which
        # looked like a contestability result and was an artifact of the instruction.
        return RecourseOutcome(challenge=challenge, ruling=None,
                               comprehension=comprehension)

    exchange = await _hear_if_asked(record, challenge, config, client, writer=writer)
    ruling = await _ruled_by(recoursers, record, challenge, config, client, exchange,
                             writer=writer)
    if writer is not None:
        writer.record_ruling(ruling)
    return RecourseOutcome(challenge=challenge, ruling=ruling,
                           comprehension=comprehension, transcript=exchange)
