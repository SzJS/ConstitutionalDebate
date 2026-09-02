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

from .prompts import contest_void_reason, strip_ruling_prose
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


def _decision_section(verdict: dict[str, Any], heading: str = "## The decision",
                      extended_from: int | None = None) -> str:
    """Grounds first, then the verdict they led to.

    The order was the other way round until 2026-08-25, and the reason for turning it is
    a rendering artifact rather than a preference. The grounds are the model's own text
    up to its decision line, and a model that ends *"...and so my verdict is:"* or
    writes a dangling ``**Final verdict:**`` header leaves that header as the last line
    of the quote — 12 of pilot 2's records do exactly this. With the verdict printed
    above, the header pointed at nothing and the document read as if the decision had
    gone missing. Printed below, the model's own run-up runs straight into it.

    Nothing is edited or trimmed to achieve that: the quote is the same bytes either
    way. The repair note moves with the verdict line, because it is a statement about
    which reply the verdict came from.
    """
    phrase = _VERDICT_PHRASE.get(verdict["verdict"], verdict["verdict"])
    lines = [heading, ""]
    grounds = (verdict.get("reasoning") or "").strip()
    if grounds:
        lines += ["**Grounds given:**", "", _quote(grounds), ""]
    else:
        lines += [
            "*No grounds were stated before the verdict line. The full response is in "
            "`verdict.json`.*", "",
        ]
    lines += [f"**Verdict:** {phrase}.", ""]
    if extended_from is not None:
        # Arm B of `judgment-debate-6`. Said in the document because the transcript
        # above is longer than the one the source judge read, and a reader comparing
        # this verdict with that one has to know which record each was made from.
        lines += [
            f"*The debate above was argued elsewhere to round {extended_from} and "
            f"continued here; this verdict was made from the longer transcript.*", "",
        ]
    if verdict.get("repair_attempts"):
        lines += [
            f"*This verdict came from a format-repair reply "
            f"({verdict['repair_attempts']} attempt(s)); the grounds above are from "
            "that reply.*", "",
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
        parts.append(_decision_section(
            verdict, extended_from=manifest.get("extended_from_rounds")))
    else:
        parts.append("## The decision\n\n*No verdict was reached.*\n")

    parts.append(_PRIVATE_POINTER)
    parts.append(ground_truth_section(item, _read(directory, "flaw.json")))
    return "\n".join(parts).rstrip() + "\n"


# What the document says about each stance. `agrees` is unreachable since the
# challenger's line became one relative token — a reply cannot both ask for a reversal
# and name the verdict it is reversing to — but the branch stays, because contest
# records written under the two-line instruction still render through here and a
# document that presented such an objection as a contest which failed would be
# describing a contest that never happened. What replaced the detection is the
# `agreement` stage, which reads the prose rather than the label.
def _objection_section(challenge: dict,
                       parent_verdict: dict | None = None) -> list[str]:
    stance = challenge.get("stance") or (
        "contests" if challenge.get("raised", True) else "declined")
    text = _quote(challenge.get("text", ""))
    claimed = challenge.get("claimed_verdict")
    if stance == "declined":
        lines = ["**The stakeholder declined to object.** They were free to, and "
                 "reported finding no grounds. What they wrote:", "", text, "",
                 "*No ruling was sought, because there was nothing to rule on. A "
                 "decision that was never objected to is not the same as one that "
                 "survived an objection.*"]
        if challenge.get("contradictory"):
            lines += ["", "*They declined and yet named the opposite verdict. Recorded "
                          "as a decline — the question asked was whether to object, and "
                          "they answered it.*"]
    elif stance == "agrees":
        lines = [f"**The stakeholder raised an objection that agreed with the verdict; "
                 f"no ruling was sought.** They said the verdict should be "
                 f"**{claimed}**, which is the verdict the decision reached. What they "
                 f"wrote:", "", text, "",
                 "*A recourse judge asked to rule on an objection that agrees with the "
                 "decision is being asked nothing, so none was sought.*"]
    elif stance == "unclear":
        lines = ["**The stakeholder raised an objection without saying which verdict "
                 "it wanted.** No ruling was sought, and the contest is excluded from "
                 "the rates rather than counted either way. What they wrote:", "",
                 text, ""]
    elif challenge.get("arm") == "findings":
        # THE FINDINGS ARM. Here `claimed_verdict` is DERIVED from every contest the
        # objection raised — void ones included, because a stakeholder whose quotation
        # could not be found still asked for something — rather than read off the
        # decision line. Three things it can therefore say, and they are three different
        # facts about the objection:
        contests = challenge.get("defects") or []
        if contests and all(contest.get("void") for contest in contests):
            # EVERY CONTEST VOID. Said outright, because the alternative sentences would
            # both be false: the objection did not merely concern the reasoning, and its
            # contests were not weighed and rejected — they never reached the judge's
            # standard at all. The outcome section names the failed check per contest.
            lines = [f"*Raised by a stakeholder who read only the record above. They "
                     f"say the verdict should be **{claimed}**. Every contest quoted "
                     f"words that could not be found in the documents they were "
                     f"attributed to, so none of them could be applied.*", "", text]
        elif (parent_verdict is not None
              and claimed == parent_verdict.get("verdict")):
            # A LOCAL CONTEST: one finding among several, contested and possibly right,
            # leaving the verdict where it was. Printing "they say the verdict should be
            # FLAWED" over a FLAWED decision would tell a stakeholder their objection
            # asked for nothing, which is the opposite of what it did.
            lines = [f"*Raised by a stakeholder who read only the record above. They "
                     f"contest the findings below; granting every one of them would "
                     f"still leave the verdict **{claimed}**, so the objection is about "
                     f"the reasoning rather than about the answer.*", "", text]
        else:
            lines = [f"*Raised by a stakeholder who read only the record above. They say "
                     f"the verdict should be **{claimed}**.*", "", text]
    else:
        lines = [f"*Raised by a stakeholder who read only the record above. They say "
                 f"the verdict should be **{claimed}**.*", "", text]
    return ["## The objection", "", *lines, ""]


# What each debater was arguing, in words, so a reader does not have to hold the
# derivation in their head. Which of the two is which is derived from the parent verdict
# and is NOT recorded on the turn — see `types.recourse_stance` — so the ruling's
# `recourse_pro_speaker` is what names it here, and a contest whose ruling is missing
# falls back to saying so rather than guessing.
_STANCE_GLOSS = {
    "pro": "argues the objection is well founded",
    "anti": "argues the objection is not well founded",
}


def _exchange_section(exchange: dict[str, Any], ruling: dict[str, Any] | None) -> str:
    """The contestability debate round, as the judge was shown it.

    PUBLIC ARGUMENTS ONLY. `recourse_transcript.json` holds full turns, `Thinking:`
    included, exactly as a decision's `transcript.json` does; this document publishes
    what the judge saw and `_PRIVATE_POINTER` at the foot says where the rest is. A
    renderer that reached for `thinking` here would put two private sections into the
    document a stakeholder is handed.
    """
    turns = sorted(exchange["turns"],
                   key=lambda t: (t.get("round", 0), str(t.get("speaker"))))
    pro = (ruling or {}).get("recourse_pro_speaker")
    lines = ["## The exchange on the objection", ""]
    if pro:
        lines += [f"*Both debaters were shown the judgment and the objection and "
                  f"replied once, simultaneously, without seeing each other's reply. "
                  f"{pro}, whose position the decision went against, argues that the "
                  f"objection is well founded; the other argues that it is not. Each "
                  f"still argues its own assigned side.*", ""]
    else:
        lines += ["*Both debaters replied once to the objection, simultaneously, "
                  "without seeing each other's reply. Which of them argued for the "
                  "objection is derived from the decision and no ruling was recorded "
                  "here to name it.*", ""]
    for turn in turns:
        speaker = str(turn.get("speaker"))
        gloss = _STANCE_GLOSS.get("pro" if speaker == pro else "anti") if pro else None
        heading = f"**{speaker}" + (f" ({gloss})" if gloss else "") + ":**"
        lines += [heading, "", _quote(turn.get("argument", "")), ""]
    return "\n".join(lines)


_CONTEST_NUMBER_RE = re.compile(r"^\s*Contest\s+(\d+)\b")


def _annotated_contest_lines(stated: str,
                             contests: list[dict[str, Any]]) -> tuple[str, bool]:
    """The judge's lines, each void contest's marked ``not applied`` and why.

    Added 2026-09-02, after a smoke record printed `Contest 1: FLAW` directly above "0
    are ruled FLAW" with nothing in between to explain it. The judge really did write
    that line; the contest was void at parse time, so `apply_contest_lines` ignored it
    and the verdict did not move. A stakeholder reading their own record has to be told
    that, and told which check failed — otherwise the document contradicts itself in
    front of the person it is written for.
    """
    by_index = {int(contest["index"]): contest for contest in contests
                if contest.get("index") is not None}
    out: list[str] = []
    any_void = False
    for line in stated.splitlines():
        match = _CONTEST_NUMBER_RE.match(line)
        contest = by_index.get(int(match.group(1))) if match else None
        if contest is not None and contest.get("void"):
            any_void = True
            reason = contest_void_reason(contest) or "a mechanical check failed"
            out.append(f"{line.rstrip()} — not applied: {reason}")
        else:
            out.append(line)
    return "\n".join(out), any_void


def _findings_outcome_lines(ruling: dict[str, Any],
                            after: dict[str, Any] | None,
                            challenge: dict[str, Any] | None = None) -> list[str]:
    """The judge's contest rulings, and what they did to the list.

    Printed from the RULING's own `conclusion_line` and from `findings.after.json`, not
    re-derived here: the document's whole claim is that a reader can check the verdict
    against the sentences it came from, and a renderer that recomputed the derivation
    would be showing them its own arithmetic instead of the judge's. The one thing added
    to the judge's own words is the note on a line that was NOT applied, which is a fact
    about the harness and is marked as one.
    """
    lines: list[str] = []
    stated = (ruling.get("conclusion_line") or "").strip()
    if stated:
        annotated, any_void = _annotated_contest_lines(
            stated, (challenge or {}).get("defects") or [])
        lines += ["", "**The judge ruled on each contest:**"]
        if any_void:
            lines += ["", "Contests whose quotations could not be found were not "
                          "applied."]
        lines += ["", _quote(annotated)]
    if not after:
        return lines
    added = [f for f in (after.get("findings") or []) if f.get("added_at_recourse")]
    if added:
        lines += ["", f"**{len(added)} finding(s) were added at recourse**, built from "
                      "the objection's own quotations because the judge agreed a "
                      "purported flaw had been left out of the list:", ""]
        for finding in added:
            lines.append(f"- *{finding.get('ruling')}* — "
                         f"{finding.get('claim') or finding.get('passage') or ''}")
    lines += ["", f"The list now holds {after.get('n_findings')} finding(s), of which "
                  f"{after.get('n_flaw')} are ruled FLAW."]
    return lines


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
    else:
        parts += _objection_section(challenge, parent_verdict)

    exchange = _read(directory, "recourse_transcript.json")
    if exchange is not None and exchange.get("turns"):
        parts.append(_exchange_section(exchange, ruling))

    if ruling is not None:
        outcome = ("**upheld**" if ruling.get("upheld") else "**overturned**")
        heard = (" after hearing both debaters on the objection"
                 if ruling.get("recourse_rounds") else "")
        lines = ["## The outcome", "",
                 f"The decision was {outcome}{heard}.", ""]
        if ruling.get("form") == "uphold_overturn":
            lines.append("*Ruled on by a judge who did not make the original decision. "
                         "The decision stood unless the objection showed it mistaken.*")
        elif ruling.get("form") == "derived_findings":
            # The account a stakeholder is handed of how their objection was heard, and
            # here it has to say something no other form has to: the judge did not state
            # a verdict at all. It ruled on each contest, those rulings were written into
            # the findings list, and the verdict was worked out by counting. A reader who
            # was told only "upheld" would have no way to check that, so the lines, the
            # appended findings and the count are all printed below.
            lines.append("*Ruled on by a judge who did not make the original decision. "
                         "The judge ruled on each contest separately; the findings were "
                         "updated with those rulings and the verdict was re-derived from "
                         "the whole list — the text counts as flawed if any finding is "
                         "ruled FLAW.*")
        elif ruling.get("form") == "stated_conclusion":
            # The same judge and the same standard; what changed is that it is no longer
            # asked for the relative word. Said plainly here because this sentence is the
            # account a stakeholder is handed of how their objection was heard, and
            # "upheld" now means something the judge did not itself write.
            lines.append("*Ruled on by a judge who did not make the original decision. "
                         "The judge stated its own conclusion about the text under "
                         "review; the decision was upheld/overturned by comparing the "
                         "two.*")
        else:
            lines.append("*Reconsidered by the same reviewer that made the decision, in "
                         "the same conversation.*")
        # Same order as the decision section above, and for the same reason: the
        # grounds end where the model's own decision line began, so the verdict has to
        # follow them or a dangling "**Final verdict:**" points at nothing.
        grounds = (ruling.get("reasoning") or "").strip()
        if ruling.get("form") == "derived_findings":
            # THE SAME STRIP THE READER GETS (R11a, after smoke 2). `Ruling.reasoning`
            # already ends where the judge's contest lines began, and under this form
            # the judge routinely announces them — "The final answer is:" — leaving the
            # published grounds ending on a sentence that promises an answer printed
            # three paragraphs further down, under "The judge ruled on each contest".
            # `strip_ruling_prose` is the function the ruling-agreement reader is handed
            # its copy through, so this makes the document and the instrument that
            # audits it read the same words, and `ruling_leadin_stripped` records that a
            # lead-in was dropped. Nothing is lost: `Verdict`/`Ruling` `raw` is untouched
            # and `transcript_full.md` prints every byte the judge wrote.
            grounds = strip_ruling_prose(grounds)[0].strip()
        if grounds:
            lines += ["", "**Grounds given:**", "", _quote(grounds)]
        if ruling.get("form") == "derived_findings":
            lines += _findings_outcome_lines(
                ruling, _read(directory, "findings.after.json"), challenge)
        lines += ["", f"**Verdict now:** "
                      f"{_VERDICT_PHRASE.get(ruling['verdict'], ruling['verdict'])}.", ""]
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
