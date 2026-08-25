"""``transcript.md`` — the document the transparency claim is about.

Everything else in a run directory is machinery. This is the artifact a reader is
supposed to be able to pick up and follow: what was being decided, what was argued,
what was decided, on what grounds, and — if it was contested — what happened then.

Two rules govern every renderer here.

**Never state something that did not happen.** A solo decision has no positions, so its
document says so explicitly rather than printing an empty Positions section, and never
names Alice or Bob. exp1 shipped the opposite and it took a bug report to notice.

**Never quietly edit what a model wrote.** Model text is defanged so it cannot forge
document structure, but it is never trimmed, summarised or corrected. The record is
what was said.

Defanging is a rule about *this* document, which is meant to be read. Its sibling
``transcript_full.md`` (``artifacts_full``) is meant to be checked, and prints every
byte that went over the wire without touching it.

The ground truth is published here, last and nowhere else, so that a reader meets the
record the way the participants did. Nothing on the decision or contest path may read
this document — a test enforces that — because the answer is in it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import verdict_for

_MARKDOWN_STRUCTURE_RE = re.compile(r"(?m)^(#{1,6}[ \t]|-{3,}[ \t]*$|={3,}[ \t]*$)")


def defang_markdown(text: str) -> str:
    """Stop model text forging headings or rules that would restructure the document."""
    return _MARKDOWN_STRUCTURE_RE.sub(lambda m: "​" + m.group(1), text)


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in
                     defang_markdown(text).splitlines()) or ">"


def _read(directory: Path, name: str) -> Any | None:
    path = directory / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


_VERDICT_PHRASE = {
    "FLAWED": "the text under review **contains a flaw**",
    "SOUND": "the text under review **does not contain a flaw**",
}


def _decision_section(verdict: dict[str, Any], heading: str = "## The decision") -> str:
    phrase = _VERDICT_PHRASE.get(verdict["verdict"], verdict["verdict"])
    lines = [heading, "", f"**Verdict:** {phrase}.", ""]
    if verdict.get("repair_attempts"):
        lines += [
            f"*This verdict came from a format-repair reply "
            f"({verdict['repair_attempts']} attempt(s)); the grounds below are from "
            "that reply.*", "",
        ]
    grounds = (verdict.get("reasoning") or "").strip()
    if grounds:
        lines += ["**Grounds given:**", "", _quote(grounds), ""]
    else:
        lines += [
            "*No grounds were stated before the verdict line. The full response is in "
            "`verdict.json`.*", "",
        ]
    return "\n".join(lines)


def _item_section(item: dict[str, Any]) -> str:
    return "\n".join([
        "## What was being decided", "",
        "The question is whether the text under review contains a flaw.", "",
        "### The problem", "", _quote(item["problem"]), "",
        "### The text under review", "", _quote(item["solution"]), "",
    ])


def _positions_section(sides: dict[str, Any]) -> str:
    flawed = "Alice" if sides["alice_side"] == "FLAWED" else "Bob"
    sound = "Bob" if flawed == "Alice" else "Alice"
    return "\n".join([
        "## Positions", "",
        f"- **{flawed}** argued that the text contains a flaw.",
        f"- **{sound}** argued that it does not.", "",
        "Positions were assigned at random. That someone argued a position is no "
        "evidence for it.", "",
    ])


def _rounds_section(turns: list[dict[str, Any]]) -> str:
    lines = ["## The debate", ""]
    for round_number in sorted({t["round"] for t in turns}):
        lines += [f"### Round {round_number}", ""]
        for turn in [t for t in turns if t["round"] == round_number]:
            lines += [f"**{turn['speaker']}:**", "", _quote(turn["argument"]), ""]
    return "\n".join(lines)


def _steps_section(steps: list[dict[str, Any]], condition: str) -> str:
    made = {
        "single": "One reviewer decided alone, in a single pass. **No positions were "
                  "assigned and nobody argued a side.**",
        "self_critique": "One reviewer decided alone, criticising and revising its own "
                         "assessment. **No positions were assigned and nobody argued a "
                         "side.**",
    }.get(condition, "One reviewer decided alone.")
    lines = ["## How the decision was made", "", made, ""]
    for step in steps:
        lines += [f"### {step['index']}. {step['stage'].capitalize()}", "",
                  _quote(step["text"]), ""]
    return "\n".join(lines)


# Private reasoning still has to end up somewhere a reader can reach — the claim is
# that every channel which moved the decision is published. It is no longer printed
# *here* because this document is the one meant to be read straight through, and a
# reviewer's ``Thinking:`` block is not part of what the participants saw.
_PRIVATE_POINTER = (
    "*Private reasoning — each participant's `Thinking:` section, and any native "
    "reasoning the provider returned — is not reproduced in this document. Nobody saw "
    "it while the decision was being made. Every prompt and every reply, verbatim, is "
    "in `transcript_full.md` beside this file.*\n"
)


def ground_truth_section(item: dict[str, Any], flaw: dict[str, Any] | None) -> str:
    """The hidden answer, published at the very bottom and nowhere else.

    Shared with ``artifacts_full`` so the two documents cannot disagree about what the
    answer was. Placement is the whole design: a reader who knows the label before
    reading the arguments can only tell whether they agree with the decision, not
    whether the record was legible enough to check it. So no verdict, ruling or step
    anywhere above is marked correct or incorrect — the reader decides first, then
    scrolls.
    """
    label = verdict_for(item["gold_flawed"])
    lines = [
        "## Ground truth", "",
        "*Shown to nobody who took part — not a debater, a reviewer, the judge or the "
        "challenger — and deliberately placed last, appearing nowhere else above, so "
        "that this record can be read the way they read it. Decide first, then look.*",
        "",
        f"- **Gold label:** {label} — {_VERDICT_PHRASE.get(label, label)}.",
        f"- **`label_basis`:** {item.get('label_basis', 'unrecorded')}",
        f"- **`label_reliable`:** "
        f"{'yes' if item.get('label_reliable', True) else 'no'}",
    ]
    if flaw is None:
        lines += ["", "*No flaw annotation accompanies this record.*", ""]
        return "\n".join(lines)

    lines += [
        f"- **Flaw location:** {flaw.get('flaw_location') or '(none given)'}",
        f"- **Annotation quality:** {flaw.get('annotation_quality', 'none')}",
        f"- **Origin:** {flaw.get('origin', 'unrecorded')}",
        "",
    ]
    annotation = (flaw.get("annotation") or "").strip()
    if annotation:
        lines += ["**What the dataset says is wrong:**", "", _quote(annotation), ""]
    else:
        lines += ["*The dataset described no flaw beyond its location.*", ""]
    return "\n".join(lines)


def render_run_record(directory: Path) -> str:
    """The published document for a decision run."""
    manifest = _read(directory, "run.json") or {}
    item = _read(directory, "item.json")
    verdict = _read(directory, "verdict.json")
    condition = manifest.get("condition", "unknown")
    if item is None:
        return "# Incomplete run\n\nNo item was recorded.\n"

    parts = [f"# Decision record — {item['item_id']}", "",
             f"Condition: **{condition}**. Run `{manifest.get('run_id', directory.name)}`.",
             "", _item_section(item)]

    transcript = _read(directory, "transcript.json")
    trace = _read(directory, "trace.json")
    if transcript is not None:
        sides = _read(directory, "sides.json")
        if sides:
            parts.append(_positions_section(sides))
        parts.append(_rounds_section(transcript.get("turns", [])))
    elif trace is not None:
        parts.append(_steps_section(trace.get("steps", []), condition))

    if verdict is not None:
        parts.append(_decision_section(verdict))
    else:
        parts.append("## The decision\n\n*No verdict was reached.*\n")

    parts.append(_PRIVATE_POINTER)
    parts.append(ground_truth_section(item, _read(directory, "flaw.json")))
    return "\n".join(parts).rstrip() + "\n"


def render_recourse_record(directory: Path) -> str:
    """The published document for a contest: the decision, the objection, the outcome."""
    manifest = _read(directory, "run.json") or {}
    item = _read(directory, "item.json")
    challenge = _read(directory, "challenge.json")
    ruling = _read(directory, "ruling.json")
    comprehension = _read(directory, "comprehension.json")
    if item is None:
        return "# Incomplete contest\n\nNo item was recorded.\n"

    parent_verdict = _read(directory, "parent/verdict.json")
    condition = manifest.get("condition", "unknown")
    parts = [f"# Contest record — {item['item_id']}", "",
             f"Condition: **{condition}**. Contest of run "
             f"`{manifest.get('parent_run_id', 'unknown')}`.", "",
             _item_section(item)]

    if parent_verdict is not None:
        parts.append(_decision_section(parent_verdict, "## The decision being contested"))

    if challenge is None:
        parts.append("## The objection\n\n*No objection was recorded.*\n")
    elif not challenge.get("raised", True):
        parts += ["## The objection", "",
                  "**The stakeholder declined to object.** They were free to, and "
                  "reported finding no grounds. What they wrote:", "",
                  _quote(challenge.get("text", "")), "",
                  "*No ruling was sought, because there was nothing to rule on. A "
                  "decision that was never objected to is not the same as one that "
                  "survived an objection.*", ""]
    else:
        parts += ["## The objection", "",
                  "*Raised by a stakeholder who read only the record above.*", "",
                  _quote(challenge.get("text", "")), ""]

    if ruling is not None:
        outcome = ("**upheld**" if ruling.get("upheld") else "**overturned**")
        lines = ["## The outcome", "",
                 f"The decision was {outcome}.", ""]
        if ruling.get("form") == "uphold_overturn":
            lines.append("*Ruled on by a judge who did not make the original decision. "
                         "The decision stood unless the objection showed it mistaken.*")
        else:
            lines.append("*Reconsidered by the same reviewer that made the decision, in "
                         "the same conversation.*")
        lines += ["", f"**Verdict now:** "
                      f"{_VERDICT_PHRASE.get(ruling['verdict'], ruling['verdict'])}.", ""]
        grounds = (ruling.get("reasoning") or "").strip()
        if grounds:
            lines += ["**Grounds given:**", "", _quote(grounds), ""]
        parts.append("\n".join(lines))

    if comprehension is not None:
        parts += ["## Reported comprehension", "",
                  f"The stakeholder rated how well they could follow the decision's "
                  f"reasoning as **{comprehension['score']} of 5**.", "",
                  _quote(comprehension.get("justification", "")), "",
                  "*Self-reported, and a weak proxy: it measures willingness to claim "
                  "comprehension as much as comprehension itself.*", ""]

    parts.append(_PRIVATE_POINTER)
    # The annotation lives with the decision, not with the contest, so it is read out
    # of the copied parent — and its absence is stated rather than left to look like
    # an item that simply had none.
    parts.append(ground_truth_section(item, _read(directory, "parent/flaw.json")))
    if not (directory / "parent").is_dir():
        parts.append("*The decision's own directory was not copied into this contest, "
                     "so any flaw annotation it carried is not reproduced here.*\n")

    return "\n".join(parts).rstrip() + "\n"
