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

from .client import ChatClient
from .config import DebateConfig
from .engine import _complete_with_repair
from .prompts import (
    build_challenger_messages,
    build_comprehension_messages,
    build_recourse_judge_messages,
    build_solo_recourse_message,
    parse_comprehension_output,
    parse_objection_output,
    parse_verdict_output,
    parse_ruling_output,
)
from .types import (
    COMPREHENSION_SCALE_ID,
    Challenge,
    Comprehension,
    Item,
    Ruling,
    Sides,
    count_words,
    resolve_ruling,
)

log = logging.getLogger(__name__)


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
    (thinking, raised, text, parse_mode), completion, repairs, sent = (
        await _complete_with_repair(
            client, model=model, messages=messages,
            temperature=config.debater_temperature, config=config,
            meta={"role": "challenger", "speaker": None, "round": None,
                  "purpose": "challenge"},
            parse=parse_objection_output, role="challenger",
            word_limit=config.challenge_word_limit_for(),
            reasoning_effort=config.challenger_reasoning_effort,
        )
    )
    limit = config.challenge_word_limit_for()
    if limit and count_words(text) > limit:
        log.warning("challenger wrote %d words over a %d-word limit",
                    count_words(text), limit)
    challenge = Challenge(
        text=text, origin="generated", raised=raised, arm="neutral",
        visibility="public", model=model, call_id=completion.call_id,
        finish_reason=completion.finish_reason, parse_mode=parse_mode,
        repair_attempts=repairs, thinking=thinking, raw=completion.content,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
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
    (score, justification, parse_mode), completion, repairs, _ = (
        await _complete_with_repair(
            client, model=model, messages=messages, temperature=0.0, config=config,
            meta={"role": "comprehension", "speaker": None, "round": None,
                  "purpose": "comprehension"},
            parse=parse_comprehension_output, role="comprehension", word_limit=0,
        )
    )
    comprehension = Comprehension(
        score=score, scale=COMPREHENSION_SCALE_ID, justification=justification,
        asked_after_decline=not challenge.raised, model=model, parse_mode=parse_mode,
        raw=completion.content, call_id=completion.call_id,
        finish_reason=completion.finish_reason, repair_attempts=repairs,
        native_reasoning=completion.reasoning,
        reasoning_withheld=completion.reasoning_withheld,
    )
    if writer is not None:
        writer.record_comprehension(comprehension)
    return comprehension


async def _rule_by_judge(
    record: Any, challenge: Challenge, config: DebateConfig, client: ChatClient
) -> Ruling:
    """Debate: a recourse judge rules on the objection. The verdict is derived."""
    messages = build_recourse_judge_messages(
        record.item, record.sides, record.challenger_view(),
        decision_verdict=record.verdict.verdict, objection=challenge.text,
    )
    (word, reasoning, parse_mode), completion, repairs, _ = (
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
    messages = [*record.messages, build_solo_recourse_message(record.sides, challenge.text)]
    (word, reasoning, parse_mode), completion, repairs, _ = (
        await _complete_with_repair(
            client, model=config.debater_model, messages=messages,
            temperature=config.debater_temperature, config=config,
            meta={"role": "recourse_solo", "speaker": None, "round": None,
                  "purpose": "rule"},
            parse=parse_verdict_output, role="recourse_solo",
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

    if not challenge.raised or not rule:
        # No ruling.json is written, and its absence is what lets the analysis tell "the
        # decision was never objected to" from "the decision survived an objection".
        return RecourseOutcome(challenge=challenge, ruling=None,
                               comprehension=comprehension)

    ruling = await RECOURSERS[record.condition](record, challenge, config, client)
    if writer is not None:
        writer.record_ruling(ruling)
    return RecourseOutcome(challenge=challenge, ruling=ruling,
                           comprehension=comprehension)
