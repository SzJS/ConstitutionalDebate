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
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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


def _private_section(bodies: list[tuple[str, str]]) -> str:
    """Private reasoning, published *after* the decision it did not reach.

    It was invisible to the judge, the opponent and the challenger while the decision
    was being made. It is printed here because the claim is that every channel which
    moved the decision ends up somewhere a reader can see — not that a reader sees it
    at the same time the participants did.
    """
    if not any(body.strip() for _, body in bodies):
        return ""
    lines = ["## Private reasoning", "",
             "*Not shown to anyone during the decision — neither the judge, the other "
             "participant, nor the challenger. Published afterwards.*", ""]
    for label, body in bodies:
        if body.strip():
            lines += [f"**{label}:**", "", _quote(body), ""]
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

    private: list[tuple[str, str]] = []
    if transcript is not None:
        private = [(f"{t['speaker']}, round {t['round']}", t.get("thinking", ""))
                   for t in transcript.get("turns", [])]
    elif trace is not None:
        private = [(f"Step {s['index']} ({s['stage']})", s.get("thinking", ""))
                   for s in trace.get("steps", [])]
    section = _private_section(private)
    if section:
        parts.append(section)
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

    return "\n".join(parts).rstrip() + "\n"
