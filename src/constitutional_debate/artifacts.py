"""Human-readable renderings of a recorded run.

Two invariants a reader of this module needs:

1. Nothing here may reach a prompt.  ``types.render_transcript`` is the
   *model-facing* render — it is interpolated into every debater and judge
   request, so ``scripts/verify_run.py`` re-derives it byte for byte and any
   change to it invalidates every recorded run.  These renderers are derived
   artifacts: no prompt depends on them, which is exactly what lets them be
   formatted for a human.

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

from .prompts import response_states_grounds
from .types import ORDER, Seating, Task, Transcript, Turn, Verdict

NOT_PUBLIC_BANNER = (
    "> **This is not the public record.** It contains each debater's private "
    "`Thinking` section, which the judge and the opposing debater never saw. "
    "`transcript.public.md` is the public artifact."
)

TRANSCRIPT_DOC_KEYS = frozenset({"question", "answers", "positions", "turns"})

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
    """The judge's choice number (1 or 2) that showed this answer."""
    return seating.choice_order.index(answer_index) + 1


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


def _rounds(turns: list[Turn], *, thinking: bool) -> list[str]:
    """Render turns as ``## Round N`` / ``### Speaker`` sections."""
    blocks: list[str] = []
    for round_number in sorted({t.round for t in turns}):
        blocks.append(f"## Round {round_number}")
        for turn in sorted(
            (t for t in turns if t.round == round_number),
            key=lambda t: t.speaker.position,
        ):
            blocks.append(f"### {turn.speaker}")
            if thinking:
                blocks.append(
                    "**Thinking** (private — neither the judge nor the opponent "
                    "ever saw this)"
                )
                blocks.append(
                    defang_markdown(turn.thinking.strip()) or "_(none recorded)_"
                )
                blocks.append("**Argument** (public)")
            blocks.append(defang_markdown(turn.argument))
    return blocks


def render_public_markdown(transcript: Transcript) -> str:
    """The public record: arguments only, no question, no decision.

    A re-render, not a byte-copy of what the judge saw — the byte-exact artifact
    is the judge request body in ``calls.jsonl``.
    """
    blocks = [
        "# Public transcript",
        "Arguments only. Debaters' private `Thinking` sections are excluded by "
        "protocol and are not part of the public record.",
        *_rounds(transcript.all_turns(), thinking=False),
    ]
    return "\n\n".join(blocks) + "\n"


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
    task: Task, seating: Seating, verdict: Verdict | None, judge_cot: bool
) -> list[str]:
    if verdict is None:
        return [
            "## Decision",
            "No verdict recorded — this run did not reach a decision. See "
            "`run.json` for its status.",
        ]
    winner = seating.speaker_for_choice(verdict.choice)
    blocks = [
        "## Decision",
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


def render_full_markdown(
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
        "# Full transcript",
        NOT_PUBLIC_BANNER,
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
        *_rounds(transcript.all_turns(), thinking=True),
        *_decision(task, seating, verdict, judge_cot),
    ]
    return "\n\n".join(blocks) + "\n"
