"""The readable record of a decision.

``transcript.md`` is what this module exists to produce, and it is the artifact
the project's claim rests on: the question, the arguments, the debaters'
reasoning, the decision, and the grounds the judge gave for it, in one document
a person can read. Everything else in the run directory is machinery.

Two invariants a reader of this module needs:

1. Nothing here may reach a prompt.  ``types.render_transcript`` is the
   *model-facing* render, interpolated into every debater and judge request.
   Keeping the two apart is what stops a change to a published document altering
   what a participant was shown — a presentation edit must never be able to
   reach into the debate it describes.

2. ``types.indent_continuations`` is deliberately *not* reused here.  Its two
   effects are both wrong for markdown: four-space indentation means "code
   block", and escaping ``</transcript>`` guards a tagged plaintext document
   that markdown does not have.  ``defang_markdown`` is this module's analogue —
   same threat (a participant authors text inside a structured document), same
   mitigation-not-prevention caveat, different structure to defend.
"""

from __future__ import annotations

import re
from typing import Any

from .prompts import RULING_RE, response_states_grounds
from .types import (
    ORDER,
    Challenge,
    Ruling,
    Seating,
    Task,
    Transcript,
    Turn,
    Verdict,
)

PRIVATE_THINKING_NOTE = (
    "> **The `Thinking` sections below were private during the debate.** Neither "
    "the judge nor the opposing debater ever saw them, and that is what makes "
    "the arguments the debate. They are published here afterwards because a "
    "record of a public decision should let a reader see everything that went "
    "into it, including what a debater worked out and chose not to say."
)

TRANSCRIPT_DOC_KEYS = frozenset({"question", "answers", "positions", "turns"})
# A separate constant, not an extension of the one above: widening the debate
# document's key set would let a recourse-only key appear unnoticed in an
# ordinary run's transcript.json.
RECOURSE_TRANSCRIPT_DOC_KEYS = TRANSCRIPT_DOC_KEYS | {"parent_run_id", "parent_rounds"}

# Block structure is line-leading, so one line-anchored rule covers all of it.
# Worst first: an unclosed ``` fence swallows the remainder of the document —
# every later round and the decision itself — in any rendered view. Then ATX
# headings (`## Round 4`) forging structure, setext underlines promoting the
# *preceding* line to a heading, and thematic breaks faking a section boundary.
#
# The thresholds are the easy mistake. A setext underline is *one or more* `=`
# or `-`, so "Round 4\n=" forges an h1 that outranks this document's own
# headings; a thematic break may be spaced ("- - -"). Both are matched here.
_MARKDOWN_STRUCTURE_RE = re.compile(
    r"""^[ ]{0,3}(
        \#{1,6}([ \t]|$)                 # ATX heading
      | `{3,} | ~{3,}                    # fenced code
      | [-=]+[ \t]*$                     # setext underline (one is enough)
      | [-*_]([ \t]*[-*_]){2,}[ \t]*$    # thematic break, spaced or not
    )""",
    re.VERBOSE,
)

# Raw HTML is not line-leading: CommonMark passes inline HTML through verbatim,
# so a mid-sentence "<div style=display:none>" hides everything after it just as
# an unclosed fence does. Escaped everywhere rather than only at line start.
_INLINE_HTML_RE = re.compile(r"<(?=[a-zA-Z!/?])")


def defang_markdown(text: str) -> str:
    """Neutralise line-leading markdown structure in authored text.

    Arguments, ``Thinking`` sections and the judge's response are all written by
    a model, and the question and answers come off disk from an unvendored
    dataset.  All of them are interpolated into a document whose headings carry
    meaning, so any of them could forge a round, a speaker, or a decision.

    A leading backslash is enough for block structure: ``\\#`` renders as a
    literal ``#``, and a line that no longer *begins* with backticks cannot open
    a fence.  Inline HTML is escaped wherever it appears, because it can hide
    the rest of the document from mid-sentence; an ``<https://...>`` autolink is
    collateral, and renders as literal text.  Emphasis and inline links are left
    alone — escaping them would mangle legitimate prose for very little gain.

    Mitigation, not prevention: a reader is still reading a document that one
    participant partly wrote.
    """
    escaped = _INLINE_HTML_RE.sub("\\\\<", text)
    return "\n".join(
        "\\" + line if _MARKDOWN_STRUCTURE_RE.match(line) else line
        for line in escaped.split("\n")
    )


def judge_choice_for_answer(seating: Seating, answer_index: int) -> int:
    """The judge's choice number (1 or 2) that showed this answer.

    Kept as a module-level name because it reads better at the call sites below
    than the method it now delegates to; ``Seating`` owns the mapping because
    ``prompts`` needs it too and may not import this module.
    """
    return seating.choice_for_answer(answer_index)


def positions(task: Task, seating: Seating) -> dict[str, dict[str, Any]]:
    """Who defends what, in all three numberings at once.

    ``answer_index`` indexes ``Task.answers``; ``judge_choice`` is the 1/2 label
    the judge saw.  They are drawn independently (see the ``types`` module
    docstring), so stating one without the other invites a reader to assume they
    coincide — which for half of all seatings they do not.
    """
    return {
        str(speaker): {
            "answer_index": seating.answer_for(speaker),
            "answer": task.answers[seating.answer_for(speaker)],
            "judge_choice": judge_choice_for_answer(
                seating, seating.answer_for(speaker)
            ),
        }
        for speaker in ORDER
    }


def transcript_document(
    task: Task, seating: Seating, transcript: Transcript
) -> dict[str, Any]:
    """The ``transcript.json`` payload: the turns plus what they are about.

    ``gold_index`` is deliberately absent.  It lives in ``task.json`` and
    nowhere else, which is what makes "the gold answer never reaches a prompt" a
    checkable invariant rather than a habit.
    """
    return {
        "question": task.question,
        "answers": list(task.answers),
        "positions": positions(task, seating),
        "turns": transcript.to_dict()["turns"],
    }


def _rounds(turns: list[Turn]) -> list[str]:
    """Render turns as ``## Round N`` / ``### Speaker`` sections.

    Both halves of every turn. The ``Thinking`` was private *during* the debate
    and the ``Argument`` is what the judge decided on; the document says which
    is which, because a reader who could not tell them apart would credit the
    judge with reasoning it never saw.
    """
    blocks: list[str] = []
    for round_number in sorted({t.round for t in turns}):
        blocks.append(f"## Round {round_number}")
        for turn in sorted(
            (t for t in turns if t.round == round_number),
            key=lambda t: t.speaker.position,
        ):
            blocks += [
                f"### {turn.speaker}",
                "**Thinking** (private during the debate — neither the judge nor "
                "the opponent ever saw this)",
                defang_markdown(turn.thinking.strip()) or "_(none recorded)_",
            ]
            blocks += _native_reasoning_block(turn)
            blocks += [
                "**Argument** (what the judge read)",
                defang_markdown(turn.argument),
            ]
    return blocks


def _native_reasoning_block(turn: Turn) -> list[str]:
    """The provider's own reasoning channel, published rather than suppressed.

    ``reasoning_effort = "off"`` used to make this section impossible, and the
    claim was that the channel was simply not in play. That is no longer a
    choice available for every model: the newest ones refuse to disable
    reasoning at all (``"Reasoning is mandatory for this endpoint"``). They do
    return the text, so the honest form of the claim is not "the channel is off"
    but "every channel that moved the outcome is in this document".

    Two things a reader needs and would otherwise have to infer:

    - this text is the *provider's*, generated outside the protocol, and is not
      the ``Thinking`` section the prompts asked for;
    - some providers return a **summary** of their reasoning rather than the
      trace itself, so its presence here is not a guarantee of completeness.

    And the case the claim cannot cover — reasoning billed but withheld — is
    stated outright rather than left as a silent absence.
    """
    if turn.reasoning_withheld:
        return [
            "**Provider reasoning** — _the provider billed reasoning tokens for "
            "this turn but returned no text for them. This is a channel that "
            "shaped the argument below and that no reader can inspect; it is "
            "recorded here because the record should say so rather than look "
            "complete._",
        ]
    if not turn.native_reasoning.strip():
        return []
    return [
        "**Provider reasoning** (the model's own reasoning channel, outside the "
        "protocol — published, not suppressed; some providers return a summary "
        "rather than the full trace)",
        defang_markdown(turn.native_reasoning.strip()),
    ]


def _grounds_caveat(verdict: Verdict, judge_cot: bool) -> str:
    """Why this decision states no grounds — never leave a reader guessing.

    A bare "Answer: 2" under a heading reads like something went missing. Each
    of the three ways it can happen means something different about the run, and
    only one of them is a configuration the reader can change.
    """
    if verdict.repair_attempts:
        return (
            "**No grounds are recorded**: the format-repair reply above asks "
            "for the answer line alone."
        )
    if not judge_cot:
        return (
            "**No grounds are recorded, by configuration.** This run set "
            "`judge_cot = false`, so the judge was instructed to give its answer "
            "and nothing else — there is no explanation to publish, and none was "
            "withheld. `judge_cot` is enabled by default; re-run without "
            "`--no-judge-cot` for a judge that states its reasons."
        )
    return (
        "**No grounds are recorded.** The judge was asked to explain itself "
        "first and answered without doing so."
    )


def _decision(
    task: Task,
    seating: Seating,
    verdict: Verdict | None,
    judge_cot: bool,
    *,
    heading: str = "## Decision",
) -> list[str]:
    """Render a verdict as a section.

    ``heading`` exists for the recourse document, where this block sits above a
    second decision — the ruling on the challenge to it. Two sections headed
    "Decision" in one document, meaning different things, would be worse than
    no heading at all.
    """
    if verdict is None:
        return [
            heading,
            "No verdict recorded — this run did not reach a decision. See "
            "`run.json` for its status.",
        ]
    winner = seating.speaker_for_choice(verdict.choice)
    blocks = [
        heading,
        f"The judge chose **{verdict.choice}**: "
        f"{defang_markdown(task.answers[verdict.answer_index])}",
        f"That is `answers[{verdict.answer_index}]`, the answer {winner} defended.",
    ]
    if verdict.correct is not None:
        graded = "correct" if verdict.correct else "incorrect"
        blocks.append(f"Against the task's gold answer, this is **{graded}**.")
    if verdict.repair_attempts:
        # Unconditional: how the decision was obtained is provenance, true
        # whether or not the repaired reply happened to carry an explanation.
        blocks.append(
            "The judge's first response was not in the required format, so this "
            "decision came from a format-repair reply. The first response is in "
            "`calls.jsonl`, under this verdict's `call_id`."
        )

    blocks.append("### The judge's response")
    # The judge's own words verbatim, not the parsed `reasoning`: a judge that
    # writes "Answer: 2. Here is why: ..." puts its justification *after* the
    # decisive match, where the parser cannot see it. Nothing is dropped here —
    # which is exactly why the caveat below asks about the *response*, not about
    # `reasoning`, or it would contradict the text it sits under.
    if verdict.raw.strip():
        blocks.append(defang_markdown(verdict.raw.strip()))
    if not response_states_grounds(verdict.raw):
        blocks.append(_grounds_caveat(verdict, judge_cot))
    return blocks


def _challenge_provenance(challenge: Challenge) -> str:
    """State where a challenge came from, before quoting a word of it.

    A generated ``specious`` challenge is written to read as a serious
    objection — that is its job — and it is stored verbatim, so the only place a
    reader can learn what it is, is here. Saying so is not editorialising; a
    document that presents a deliberately ungrounded argument as an ordinary
    challenge would be misleading its reader.
    """
    if challenge.origin == "file":
        source = f" from `{challenge.source}`" if challenge.source else ""
        return f"Supplied{source}."

    lines = [
        f"Generated by the `{challenge.arm}` arm of the challenge generator "
        f"(`{challenge.model}`)."
    ]
    if challenge.visibility == "full":
        lines.append(
            "It was shown the **full** record, including the debaters' private "
            "`Thinking` sections, which the judge who decided this question "
            "never saw."
        )
    else:
        lines.append("It was shown the public record and the decision, nothing more.")
    if challenge.arm == "specious":
        lines.append(
            "**The generator was instructed to write a challenge that is not "
            "grounded in the record** — persuasive in form, identifying no "
            "actual error. It is an input to a test of whether the process can "
            "tell a grounded objection from a merely rhetorical one, and it "
            "should not be read as a genuine objection to this decision."
        )
    return " ".join(lines)


def _challenge_section(challenge: Challenge) -> list[str]:
    return [
        "## The challenge",
        _challenge_provenance(challenge),
        defang_markdown(challenge.text.strip()),
    ]


def _ruling(task: Task, ruling: Ruling | None, judge_cot: bool) -> list[str]:
    if ruling is None:
        return [
            "## Ruling",
            "No ruling recorded — this recourse did not reach one. See "
            "`run.json` for its status.",
        ]
    outcome = "UPHELD" if ruling.upheld else "OVERTURNED"
    blocks = [
        "## Ruling",
        f"The challenge was rejected and the decision **{outcome}**."
        if ruling.upheld
        else f"The challenge succeeded and the decision was **{outcome}**.",
        f"The answer that now stands is `answers[{ruling.answer_index}]` (the "
        f"judge's choice {ruling.choice}): "
        f"{defang_markdown(task.answers[ruling.answer_index])}",
    ]
    if ruling.changed_the_decision:
        blocks.append(
            f"This **changed** the decision, which had gone to "
            f"`answers[{ruling.parent_answer_index}]`."
        )
    else:
        blocks.append("This left the original decision standing.")
    if ruling.correct is not None:
        graded = "correct" if ruling.correct else "incorrect"
        blocks.append(f"Against the task's gold answer, this is **{graded}**.")
    if ruling.repair_attempts:
        blocks.append(
            "The recourse judge's first response was not in the required "
            "format, so this ruling came from a format-repair reply. The first "
            "response is in `calls.jsonl`, under this ruling's `call_id`."
        )

    blocks.append("### The recourse judge's response")
    if ruling.raw.strip():
        blocks.append(defang_markdown(ruling.raw.strip()))
    if not response_states_grounds(ruling.raw, decision_re=RULING_RE):
        blocks.append(_ruling_grounds_caveat(ruling, judge_cot))
    return blocks


def _ruling_grounds_caveat(ruling: Ruling, judge_cot: bool) -> str:
    """Why this ruling states no grounds. Mirrors ``_grounds_caveat``."""
    if ruling.repair_attempts:
        return (
            "**No grounds are recorded**: the format-repair reply above asks "
            "for the ruling line alone."
        )
    if not judge_cot:
        return (
            "**No grounds are recorded, by configuration.** This run set "
            "`judge_cot = false`, so the recourse judge was instructed to give "
            "its ruling and nothing else. A ruling that states no grounds "
            "cannot itself be contested; re-run without `--no-judge-cot`."
        )
    return (
        "**No grounds are recorded.** The recourse judge was asked to explain "
        "itself first and ruled without doing so."
    )


def recourse_transcript_document(
    task: Task,
    seating: Seating,
    transcript: Transcript,
    *,
    parent_run_id: str,
    parent_rounds: int,
) -> dict[str, Any]:
    """The recourse ``transcript.json``: this run's turns, and what came before.

    Only the recourse's own turns. The parent's live in ``parent/transcript.json``
    and are verified there — duplicating them here would put the same turn in two
    places that can disagree, and would break the join from a turn to the wire
    log that produced it, which for an inherited turn is the parent's.
    """
    return {
        **transcript_document(task, seating, transcript),
        "parent_run_id": parent_run_id,
        "parent_rounds": parent_rounds,
    }


def render_recourse_record(
    task: Task,
    seating: Seating,
    composed: Transcript,
    *,
    parent_rounds: int,
    parent_verdict: Verdict,
    challenge: Challenge,
    ruling: Ruling | None = None,
    judge_cot: bool,
    parent_judge_cot: bool,
    parent_trace=None,
) -> str:
    """The whole affair in one document: debate, decision, challenge, ruling.

    ``parent_judge_cot`` is separate from ``judge_cot`` for the same reason
    ``judge_cot`` is required at all: a silent original decision and a silent
    ruling have different causes, and a document that cannot tell a reader which
    it is looking at should not exist. The two are usually equal and must not be
    assumed to be.

    ``parent_trace`` is set when the challenged decision was reached by a solo
    arm. It replaces the positions block and the parent rounds with the steps
    that actually happened — because there were no debaters, and printing a
    seating here would state that Alice argued for an answer in a run where
    nobody argued at all. That is the same false statement ``render_solo_record``
    refuses to make, and this document feeds the case validator as well as a
    human reader.
    """
    before, after = composed.split_at(parent_rounds)
    parent_turns, recourse_turns = before.all_turns(), after.all_turns()
    solo_parent = parent_trace is not None
    blocks = [
        "# The decision, and the challenge to it",
        PRIVATE_THINKING_NOTE,
        "## Question",
        defang_markdown(task.question),
        "## Answers",
        "\n".join(
            f"- `answers[{index}]` (the judge saw this as choice "
            f"{judge_choice_for_answer(seating, index)}): "
            f"{defang_markdown(answer)}"
            for index, answer in enumerate(task.answers)
        ),
        "The order above is the task's own; the judge's choice order was "
        "randomised independently.",
    ]
    if solo_parent:
        blocks += [
            "## How the challenged decision was made",
            "One agent working alone. No advocates were assigned to the two "
            "answers, so this document states no positions.",
            *_solo_steps(parent_trace.all_steps()),
        ]
    else:
        position_map = positions(task, seating)
        blocks += [
            "## Positions",
            "\n".join(
                f"- **{speaker}** argues for `answers[{position['answer_index']}]` "
                f"(the judge's choice {position['judge_choice']}): "
                f"{defang_markdown(position['answer'])}"
                for speaker, position in position_map.items()
            ),
            *_rounds(parent_turns),
        ]
    blocks += [
        # The original decision, rendered by the same helper that renders it in
        # the parent's own document, so the two cannot come to differ.
        *_decision(
            task, seating, parent_verdict, parent_judge_cot,
            heading="## The original decision",
        ),
        *_challenge_section(challenge),
    ]
    if recourse_turns:
        blocks += _rounds(recourse_turns)
    else:
        blocks.append(
            "_No further rounds: this recourse ran the judge-only protocol "
            "(`recourse_rounds = 0`), in which the judge rules on the challenge "
            "without a further exchange._"
        )
    blocks += _ruling(task, ruling, judge_cot)
    return "\n\n".join(blocks) + "\n"


def render_decision_record(
    task: Task,
    seating: Seating,
    transcript: Transcript,
    verdict: Verdict | None = None,
    *,
    judge_cot: bool,
) -> str:
    """The whole record in one document: question, debate, thinking, decision.

    ``judge_cot`` is the run's setting, not a rendering option: it is the
    difference between a judge that had nothing to say and one that was told not
    to say anything, and a decision document that cannot tell a reader which
    should not exist.  Required rather than defaulted for that reason — a wrong
    guess here would not degrade the document, it would make it state something
    untrue.
    """
    position_map = positions(task, seating)
    blocks = [
        "# The decision",
        PRIVATE_THINKING_NOTE,
        "## Question",
        defang_markdown(task.question),
        "## Answers",
        "\n".join(
            f"- `answers[{index}]` (the judge saw this as choice "
            f"{judge_choice_for_answer(seating, index)}): "
            f"{defang_markdown(answer)}"
            for index, answer in enumerate(task.answers)
        ),
        "The order above is the task's own; the judge's choice order was "
        "randomised independently.",
        "## Positions",
        "\n".join(
            f"- **{speaker}** argues for `answers[{position['answer_index']}]` "
            f"(the judge's choice {position['judge_choice']}): "
            f"{defang_markdown(position['answer'])}"
            for speaker, position in position_map.items()
        ),
        *_rounds(transcript.all_turns()),
        *_decision(task, seating, verdict, judge_cot),
    ]
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- #
# solo arms
# --------------------------------------------------------------------------- #

TRACE_DOC_KEYS = frozenset({"question", "answers", "steps"})

SOLO_PRIVATE_NOTE = (
    "> **The `Thinking` sections below were private while the decision was being "
    "made.** They are published afterwards for the same reason a debater's are: "
    "a record of a public decision should let a reader see everything that went "
    "into it, including what the agent worked out and chose not to say."
)

CONSTRUCTED_NOTE = (
    "_This record was **constructed**, not generated. The published reasoning "
    "below is the flawed solution supplied with this case, reproduced "
    "unaltered; no model wrote it. Steps marked `constructed` were inserted "
    "verbatim, and the decision follows from them by construction._"
)

SOLO_CRITIQUE_NOTE = (
    "> **The critique is part of the record, not a hidden step.** The agent "
    "criticised its own draft and then revised it; all three are published. "
    "Publishing only the revision would leave a reader unable to see what the "
    "agent decided to change, or to disagree with it."
)


def trace_document(task: Task, trace) -> dict[str, Any]:
    """``transcript.json`` for a solo arm.

    A different key set from the debate document on purpose: widening
    ``TRANSCRIPT_DOC_KEYS`` to admit ``steps`` would let a solo key appear
    unnoticed in a debate record, and vice versa.
    """
    return {
        "question": task.question,
        "answers": list(task.answers),
        "steps": [s.to_dict() for s in trace.all_steps()],
    }


def _solo_steps(steps) -> list[str]:
    """The per-step blocks of a solo decision, as published.

    Shared by ``render_solo_record`` and ``render_recourse_record``: a contest of
    a solo decision publishes the same steps the decision's own document does,
    and two copies of this loop would be one edit away from disagreeing about
    what a reader was shown.
    """
    blocks: list[str] = []
    for step in steps:
        blocks.append(f"## Step {step.index} — {step.stage}")
        blocks += [
            "**Thinking** (private while the decision was being made)",
            defang_markdown(step.thinking.strip()) or "_(none recorded)_",
        ]
        blocks += _native_reasoning_block(step)
        blocks += [
            "**Published**" if step.stage != "critique" else "**Critique**",
            defang_markdown(step.text),
        ]
    return blocks


def _how_made(arm: str, outcome_control: bool) -> str:
    """One sentence on how the decision was reached — true in every case.

    Under outcome control the ``single`` arm made no pass at all, so the
    ordinary sentence would be false rather than merely incomplete.
    """
    if arm == "single":
        if outcome_control:
            return (
                "No pass was made: the reasoning and the decision are the "
                "case's own flawed solution, reproduced unaltered."
            )
        return "One agent, one pass."
    if outcome_control:
        return (
            "One agent: draft, then a critique of that draft. The revision was "
            "not generated — it is the case's own flawed solution, restored."
        )
    return "One agent: draft, then a critique of that draft, then a revision."


def render_solo_record(
    task: Task,
    seating: Seating,
    trace,
    *,
    verdict: Verdict | None = None,
    arm: str = "single",
    outcome_control: bool = False,
) -> str:
    """The published record of a decision reached without a debate.

    States **no positions**. There are no debaters, so there is nobody to say
    argued for what — and printing a seating here, as the debate renderer does,
    would put a false statement in the document.

    ``outcome_control`` says so when the record was constructed rather than
    generated. Without it this document asserts "One agent, one pass" for a run
    in which no agent made a pass — the same class of false statement the
    positions rule exists to prevent, in the one artifact the project's
    transparency claim rests on.
    """
    steps = trace.all_steps()
    blocks: list[str] = [
        "# The decision",
        SOLO_PRIVATE_NOTE,
    ]
    if outcome_control:
        blocks.append(CONSTRUCTED_NOTE)
    if any(s.stage == "critique" for s in steps):
        blocks.append(SOLO_CRITIQUE_NOTE)
    blocks += [
        "## Question",
        defang_markdown(task.question),
        "## Answers",
        "\n".join(
            f"- `answers[{i}]` — {defang_markdown(answer)} "
            f"(shown to the agent as choice {seating.choice_for_answer(i)})"
            for i, answer in enumerate(task.answers)
        ),
        f"## How this decision was made\n\nArm: `{arm}`. "
        + _how_made(arm, outcome_control),
    ]

    blocks += _solo_steps(steps)

    if verdict is not None:
        blocks += [
            "## Decision",
            "\n".join(
                [
                    f"- Choice: **{verdict.choice}**",
                    f"- Resolved answer: `answers[{verdict.answer_index}]` — "
                    f"{defang_markdown(task.answers[verdict.answer_index])}",
                ]
                + (
                    []
                    if verdict.correct is None
                    else [f"- Graded against the gold answer: **"
                          f"{'correct' if verdict.correct else 'incorrect'}**"]
                )
            ),
        ]
    return "\n\n".join(blocks) + "\n"
