"""Contesting a finished decision.

exp1 has no module like this: its baseline recourse was never implemented properly, and
DESIGN.md says so. The difficulty is that the three conditions are contested by
genuinely different mechanisms, and the record has to say which was used rather than
leaving a reader to infer it from a model name.

    debate                  a recourse judge — the same weak model — is asked whether
                            the objection shows the decision to be mistaken. The burden
                            is on the challenger and the verdict is *derived* from
                            UPHOLD/OVERTURN.

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

import logging
from dataclasses import dataclass
from typing import Any

from .arms import _split_solo
from .client import ChatClient
from .config import DebateConfig, GradingConfig
from .engine import _complete_with_repair
from .prompts import (
    build_agreement_messages,
    build_challenger_messages,
    build_comprehension_messages,
    build_recourse_judge_messages,
    build_solo_recourse_message,
    conversation_spent_a_repair,
    marks_private_text,
    parse_agreement_output,
    parse_comprehension_output,
    parse_objection_output,
    parse_verdict_output,
    parse_ruling_output,
)
from .types import (
    COMPREHENSION_SCALE_ID,
    REVERSE,
    STANDS,
    Agreement,
    Challenge,
    Comprehension,
    Item,
    Ruling,
    Sides,
    challenge_stance,
    claimed_verdict_for,
    count_words,
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
    challenge = Challenge(
        text=text, origin="generated", raised=(stance == "contests"), arm="neutral",
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
    messages = build_agreement_messages(
        challenge.text, decision_verdict=decision_verdict
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


async def _rule_by_judge(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient
) -> Ruling:
    """Debate: a recourse judge rules on the objection. The verdict is derived."""
    messages = build_recourse_judge_messages(
        record.item, record.sides, record.challenger_view(),
        decision_verdict=record.verdict.verdict, objection=challenge.text,
    )
    (word, reasoning, parse_mode), completion, repairs, _, _ = (
        await _complete_with_repair(
            client, model=config.recourse_judge_model_for(), messages=messages,
            temperature=config.judge_temperature, config=config,
            meta={"role": "recourse_judge", "speaker": None, "round": None,
                  "purpose": "rule"},
            parse=parse_ruling_output, role="recourse_judge",
            word_limit=config.word_limit,
        )
    )
    verdict = resolve_ruling(word, record.verdict.verdict)
    return Ruling(
        form="uphold_overturn", ruling=word, protocol=config.recourse_protocol,
        parent_verdict=record.verdict.verdict, verdict=verdict, parse_mode=parse_mode,
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason,
        correct=(verdict == record.item.gold_verdict), repair_attempts=repairs,
        reasoning=reasoning, native_reasoning=completion.reasoning,
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
# contested another by accident.
RECOURSERS = {
    "debate": _rule_by_judge,
    "single": _rule_in_conversation,
    "self_critique": _rule_in_conversation,
}


async def run_recourse(
    record: Any,
    config: DebateConfig,
    client: ChatClient,
    *,
    rule: bool = True,
    writer: Any | None = None,
) -> RecourseOutcome:
    """Generate an objection, ask about comprehension, and rule if there is anything to."""
    if record.condition not in RECOURSERS:
        raise ValueError(f"no recourse mechanism for condition {record.condition!r}")

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

    ruling = await RECOURSERS[record.condition](record, challenge, config, client)
    if writer is not None:
        writer.record_ruling(ruling)
    return RecourseOutcome(challenge=challenge, ruling=ruling,
                           comprehension=comprehension)
