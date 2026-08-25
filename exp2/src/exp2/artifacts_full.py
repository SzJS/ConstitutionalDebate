"""``transcript_full.md`` — the same run, made checkable rather than readable.

``artifacts`` publishes the document a person reads. This one publishes the document a
person *audits*: every message that went to a model and every reply that came back,
byte for byte, with no defanging, no trimming and no parsed-out sections.

The obstacle is repetition. A three-round debate re-sends the problem, the text under
review and every earlier argument on every call, so a verbatim dump is mostly the same
kilobytes over and over and nobody reads it. The fix is a reference scheme:

    Every distinct text is printed verbatim exactly once, in a fenced block with a
    label; wherever it recurs, the marker ``[[label]]`` stands in its place.

Substitution is exact string match only. No match means the text prints in full, so the
scheme degrades to "verbatim with repetition" and never to "edited" — and
``BlockRegistry.substitute`` refuses any substitution it cannot expand back to the
original, so that guarantee is checked rather than asserted.

Two things are deliberately *not* here. Rejected and repair-superseded attempts are
omitted — only the attempt whose ``call_id`` the record files kept is printed, because
that is the one that produced the record (a repair's request still carries the rejected
reply as an assistant turn, and is printed as such). And the order of calls comes from
the record files, never from ``calls.jsonl``: simultaneous rounds append in completion
order, which is not the order anything was reasoned in.

A debate document prints each argument twice on purpose: once as the reply, and once
inside the re-indented, tag-defanged transcript the judge was actually shown. Those are
different byte strings, and pretending otherwise would hide the transformation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifacts import ground_truth_section
from .config import DebateConfig
from .types import (
    DecisionRecord,
    Sides,
    Speaker,
    Step,
    Trace,
    Transcript,
    Turn,
    neutralise_tags,
    render_transcript,
)

_MARKER_RE = re.compile(r"\[\[([A-Z]+\d+)\]\]")
_BACKTICKS_RE = re.compile(r"`+")


def fence(text: str) -> str:
    """A fence longer than any backtick run inside, so nothing needs escaping.

    Escaping is the one thing this document may not do: a reader checking a reply
    against the wire log has to be able to compare them character for character.
    """
    longest = max((len(run) for run in _BACKTICKS_RE.findall(text)), default=0)
    return "`" * max(3, longest + 1)


def _fenced(text: str) -> str:
    bar = fence(text)
    return f"{bar}text\n{text}\n{bar}"


@dataclass(frozen=True)
class _Block:
    label: str
    # What the marker stands for: the exact bytes that were sent.
    value: str
    # What is printed under the label, which is ``value`` with earlier blocks
    # substituted — except for replies, printed as they came off the wire.
    printed: str


@dataclass
class BlockRegistry:
    """The label table. Blocks are only ever referenced backwards."""

    by_value: dict[str, _Block] = field(default_factory=dict)
    by_label: dict[str, _Block] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def define(self, prefix: str, value: str,
               printed: str | None = None) -> tuple[str | None, bool]:
        """Register ``value``. Returns ``(label, is_new)``; empty text is never kept.

        ``printed`` overrides what goes in the fenced block — replies print the wire
        text while the marker stands for the stripped text, because stripping is what
        the client did before the reply entered any later conversation.
        """
        if not value:
            return None, False
        existing = self.by_value.get(value)
        if existing is not None:
            return existing.label, False
        body = self.substitute(value) if printed is None else printed
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        block = _Block(f"{prefix}{self.counts[prefix]}", value, body)
        self.by_value[value] = block
        self.by_label[block.label] = block
        return block.label, True

    def substitute(self, text: str) -> str:
        """Replace every registered block occurring in ``text`` with its marker.

        Longest first, so a block nested inside a longer one does not shadow it. The
        result is checked against ``expand`` and discarded if it does not reproduce the
        input — model text that happens to contain a marker of its own must print in
        full rather than round-trip to something else.
        """
        marked = text
        for block in sorted(self.by_value.values(), key=lambda b: -len(b.value)):
            marked = marked.replace(block.value, f"[[{block.label}]]")
        return marked if self.expand(marked) == text else text

    def expand(self, text: str) -> str:
        """Resolve every marker back to the text it stands for."""
        return _MARKER_RE.sub(
            lambda m: (self.by_label[m.group(1)].value
                       if m.group(1) in self.by_label else m.group(0)),
            text,
        )


# --------------------------------------------------------------------------- #
# reading the run directory
# --------------------------------------------------------------------------- #


def _read(directory: Path, name: str) -> Any | None:
    path = directory / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _load_calls(directory: Path) -> dict[str, dict[str, Any]]:
    """The wire log, keyed by ``call_id``.

    ``record_call`` appends from a thread while the run is still going and the renderer
    runs after every recorded step, so the last line can be half written. An unparsable
    line is skipped rather than fatal; the call it belongs to then falls back, and the
    next render picks it up.
    """
    path = directory / "calls.jsonl"
    if not path.is_file():
        return {}
    calls: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("call_id"):
            calls[record["call_id"]] = record
    return calls


def _reply_of(record: dict[str, Any]) -> tuple[str, str]:
    """``(content, native_reasoning)`` exactly as the provider returned them."""
    body = record.get("response_body") or {}
    choices = body.get("choices") or [{}]
    message = (choices[0] or {}).get("message") or {}
    return (message.get("content") or ""), (message.get("reasoning") or "")


def _request_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    return (record.get("request_body") or {}).get("messages") or []


def _transcript_of(data: dict[str, Any]) -> Transcript:
    return Transcript([
        Turn(**{**turn, "speaker": Speaker(turn["speaker"])})
        for turn in data.get("turns", [])
    ])


def _trace_of(data: dict[str, Any]) -> Trace:
    return Trace([Step(**step) for step in data.get("steps", [])])


def _config_of(data: dict[str, Any] | None) -> DebateConfig | None:
    return DebateConfig(**data) if data else None


def _sides_of(data: dict[str, Any] | None) -> Sides | None:
    return (Sides(**{**data, "verdict_order": tuple(data["verdict_order"])})
            if data else None)


# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #

_ROLE_NAMES = {
    "debater": "Debater",
    "judge": "Judge",
    "critic": "Critic",
    "solo": "Reviewer",
    "challenger": "Challenger",
    "comprehension": "Comprehension probe",
    "recourse_judge": "Recourse judge",
    "recourse_solo": "Reviewer, reconsidering",
}


def _expected_params(config: DebateConfig, role: str,
                     model_side: str | None) -> dict[str, Any]:
    """What the header says this role was called with.

    One place, so the header table and the per-call deviation check cannot disagree
    about what "unchanged" means.
    """
    model = {
        "debater": config.debater_model_b if model_side == "b" else config.debater_model,
        "judge": config.judge_model,
        "critic": config.critic_model_for(),
        "solo": config.debater_model,
        "recourse_solo": config.debater_model,
        "challenger": config.challenger_model_for(),
        "comprehension": config.comprehension_model_for(),
        "recourse_judge": config.recourse_judge_model_for(),
    }.get(role, config.debater_model)
    temperature = {
        "judge": config.judge_temperature,
        "recourse_judge": config.judge_temperature,
        # The probe is a measurement, not a generation, so it does not sample.
        "comprehension": 0.0,
    }.get(role, config.debater_temperature)
    reasoning = (config.challenger_reasoning_effort or config.reasoning_effort
                 if role == "challenger" else config.reasoning_effort)
    return {
        "model": model, "temperature": temperature, "max_tokens": config.max_tokens,
        "reasoning": reasoning, "frequency_penalty": config.frequency_penalty,
    }


def _role_label(role: str, model_side: str | None) -> str:
    name = _ROLE_NAMES.get(role, role)
    return f"{name} (second model)" if model_side == "b" else name


def _parameters_section(config: DebateConfig | None,
                        roles: list[tuple[str, str | None]]) -> str:
    if config is None or not roles:
        return ""
    lines = [
        "## Parameters", "",
        "Stated once. A call that was made with anything else says so on its own line.",
        "", "| Role | Model | Temperature | max_tokens | Reasoning | Frequency penalty |",
        "|---|---|---|---|---|---|",
    ]
    for role, model_side in roles:
        p = _expected_params(config, role, model_side)
        lines.append(
            f"| {_role_label(role, model_side)} | `{p['model']}` | {p['temperature']} "
            f"| {p['max_tokens']} | {p['reasoning']} | {p['frequency_penalty']} |"
        )
    return "\n".join(lines) + "\n"


def _reasoning_setting(body: dict[str, Any]) -> str:
    reasoning = body.get("reasoning")
    if not isinstance(reasoning, dict):
        return "unrecorded"
    if reasoning.get("enabled") is False:
        return "off"
    return str(reasoning.get("effort", "unrecorded"))


def _deviations(record: dict[str, Any], expected: dict[str, Any]) -> str:
    """The one line that appears when a call did not use the header's settings."""
    body = record.get("request_body") or {}
    seen = {
        "model": body.get("model"),
        "temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens"),
        "reasoning": _reasoning_setting(body),
        "frequency_penalty": body.get("frequency_penalty", 0.0),
    }
    differences = [f"{key} {seen[key]!r} (header {expected[key]!r})"
                   for key in seen if seen[key] != expected[key]]
    return f"*Deviates from header: {'; '.join(differences)}.*\n" if differences else ""


# --------------------------------------------------------------------------- #
# the calls
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Accepted:
    """One call the record files kept, and everything needed to print it."""

    heading: str
    call_id: str
    role: str
    model_side: str | None = None
    # ``(prefix, description, text)`` for each block this call is the first to use.
    derived: tuple[tuple[str, str, str], ...] = ()
    # What the fallback prints when the wire log cannot supply the call.
    raw: str = ""
    native_reasoning: str = ""


def _meta_line(record: dict[str, Any]) -> str:
    usage = record.get("usage") or {}
    body = record.get("response_body") or {}
    parts = [f"`{record.get('call_id', 'unknown')}`"]
    if record.get("attempt") is not None:
        parts.append(f"attempt {record['attempt']}")
    if record.get("status") is not None:
        parts.append(f"status {record['status']}")
    if record.get("finish_reason"):
        parts.append(f"finish_reason `{record['finish_reason']}`")
    provider = record.get("provider") or body.get("provider")
    if provider:
        parts.append(f"provider {provider}")
    model = record.get("response_model") or body.get("model")
    if model:
        parts.append(f"model `{model}`")
    if usage.get("prompt_tokens") is not None:
        parts.append(f"{usage['prompt_tokens']} prompt + "
                     f"{usage.get('completion_tokens', 0)} completion tokens")
    if usage.get("cost") is not None:
        parts.append(f"${usage['cost']:.6f}")
    if record.get("latency_ms") is not None:
        parts.append(f"{record['latency_ms']} ms")
    if record.get("purpose") == "repair":
        parts.append("accepted after one format repair — the rejected reply is the "
                     "last assistant turn of the request below")
    return " · ".join(parts) + "\n"


def _call_section(registry: BlockRegistry, number: int, accepted: _Accepted,
                  record: dict[str, Any], expected: dict[str, Any] | None) -> str:
    lines = [f"### Call {number} — {accepted.heading}", "", _meta_line(record)]
    if expected is not None:
        deviation = _deviations(record, expected)
        if deviation:
            lines.append(deviation)

    for prefix, description, text in accepted.derived:
        label, is_new = registry.define(prefix, text)
        if label is not None and is_new:
            lines += [f"[[{label}]] = {description}", "",
                      _fenced(registry.by_label[label].printed), ""]

    lines.append("**Request**\n")
    for message in _request_messages(record):
        content = message.get("content") or ""
        role = message.get("role", "?")
        prefix = "S" if role == "system" else "M"
        label, is_new = registry.define(prefix, content)
        if label is None:
            lines += [f"**{role}** *(empty)*", ""]
        elif is_new:
            lines += [f"**{role}** [[{label}]] =", "",
                      _fenced(registry.by_label[label].printed), ""]
        else:
            lines += [f"**{role}** [[{label}]]", ""]

    content, reasoning = _reply_of(record)
    label, is_new = registry.define("G", content.strip(), printed=content)
    if label is None:
        lines += ["**Reply** *(empty)*", ""]
    elif is_new:
        lines += [f"**Reply** [[{label}]] =", "", _fenced(content), ""]
    else:
        lines += [f"**Reply** [[{label}]]", ""]

    lines.append(_native_reasoning(registry, record, reasoning))
    return "\n".join(lines).rstrip() + "\n"


def _native_reasoning(registry: BlockRegistry, record: dict[str, Any],
                      reasoning: str) -> str:
    """The provider's own reasoning channel, and the one case that cannot be shown."""
    if reasoning:
        label, is_new = registry.define("N", reasoning, printed=reasoning)
        if is_new:
            return f"**Native reasoning** [[{label}]] =\n\n{_fenced(reasoning)}\n"
        return f"**Native reasoning** [[{label}]]\n"
    details = (record.get("usage") or {}).get("completion_tokens_details") or {}
    if details.get("reasoning_tokens"):
        return (f"*The provider billed {details['reasoning_tokens']} reasoning tokens "
                "and returned no text for them: a channel that moved this reply and "
                "that no reader can inspect.*\n")
    return ""


_FALLBACK_NOTE = (
    "*Prompts were not recorded for this run; only the accepted generations follow, "
    "from the record files.*\n"
)


def _fallback_sections(accepted: list[_Accepted]) -> list[str]:
    parts = [_FALLBACK_NOTE]
    for number, call in enumerate(accepted, start=1):
        lines = [f"### Call {number} — {call.heading}", "",
                 f"`{call.call_id}`\n", "**Reply**\n", _fenced(call.raw), ""]
        if call.native_reasoning:
            lines += ["**Native reasoning**\n", _fenced(call.native_reasoning), ""]
        parts.append("\n".join(lines).rstrip() + "\n")
    return parts


def _calls_sections(registry: BlockRegistry, accepted: list[_Accepted],
                    calls: dict[str, dict[str, Any]],
                    config: DebateConfig | None) -> list[str]:
    """Every accepted call in record order, or the generations-only fallback."""
    parts = ["## Calls, in order\n"]
    if not accepted:
        return parts
    if not calls or any(call.call_id not in calls for call in accepted):
        return parts + _fallback_sections(accepted)
    for number, call in enumerate(accepted, start=1):
        expected = (_expected_params(config, call.role, call.model_side)
                    if config is not None else None)
        parts.append(
            _call_section(registry, number, call, calls[call.call_id], expected)
        )
    return parts


def _material_section(registry: BlockRegistry, item: dict[str, Any]) -> str:
    """The problem and the text under review, in the form the prompts carry them."""
    lines = ["## Material", "",
             "The two texts every prompt interpolates, tag-defanged exactly as they "
             "were sent.", ""]
    for prefix, description, text in (
        ("P", "the problem statement", neutralise_tags(item["problem"])),
        ("T", "the text under review", neutralise_tags(item["solution"])),
    ):
        label, _ = registry.define(prefix, text)
        if label is not None:
            lines += [f"[[{label}]] = {description}", "",
                      _fenced(registry.by_label[label].printed), ""]
    return "\n".join(lines)


_LEGEND = """## Legend

Each distinct text is printed once, in a fenced block introduced by a line carrying its
label followed by `=`. Wherever the same text was sent again, the marker `[[label]]`
stands in its place; replacing every marker with the block it names reproduces exactly
what went over the wire. A text that is not an exact match of an earlier one is printed
in full, so nothing here is ever an abridgement.

Label prefixes: `P` the problem, `T` the text under review, `S` system prompts,
`M` other messages, `G` replies, `X` texts derived from earlier replies (a rendered
transcript, a decision record, an objection), `N` a provider's native reasoning.

A `G` block prints the reply as it came off the wire. Where a reply was carried into a
later request the marker stands for that same text with leading and trailing whitespace
removed, which is what the client passed on.

Only the attempt the record kept is printed. A rejected reply appears only where it was
actually sent — as an assistant turn inside the repair request that followed it.
"""


# --------------------------------------------------------------------------- #
# decision runs
# --------------------------------------------------------------------------- #


def _run_calls(directory: Path, config: DebateConfig | None,
               sides: Sides | None) -> list[_Accepted]:
    """The accepted calls of a decision run, in the order the record files give.

    Never in ``calls.jsonl`` order: a simultaneous round appends whichever debater
    finished first, which is not the order anything was written in.
    """
    transcript_data = _read(directory, "transcript.json")
    trace_data = _read(directory, "trace.json")
    verdict = _read(directory, "verdict.json")
    accepted: list[_Accepted] = []

    if transcript_data is not None:
        transcript = _transcript_of(transcript_data)
        style = config.turn_style if config is not None else "simultaneous"
        for turn in transcript.all_turns():
            visible = transcript.visible_to(turn.speaker, turn.round, style)
            derived = ((("X", "the debate so far, as it was rendered into this "
                              "request", render_transcript(visible)),)
                       if visible and config is not None else ())
            accepted.append(_Accepted(
                heading=f"{turn.speaker}, round {turn.round}", call_id=turn.call_id,
                role="debater", model_side=_model_side(turn, config, sides),
                derived=derived, raw=turn.raw,
                native_reasoning=turn.native_reasoning,
            ))
        judged = ("X", "the whole debate, as it was rendered into the judge's request",
                  render_transcript(transcript.all_turns()))
        judge = _Accepted(heading="judge", call_id="", role="judge",
                          derived=(judged,) if transcript.all_turns() else ())
    elif trace_data is not None:
        for step in _trace_of(trace_data).all_steps():
            accepted.append(_Accepted(
                heading=step.stage, call_id=step.call_id,
                role="critic" if step.stage == "critique" else "solo",
                raw=step.raw, native_reasoning=step.native_reasoning,
            ))
        judge = _Accepted(heading="verdict", call_id="", role="solo")
    else:
        judge = _Accepted(heading="verdict", call_id="", role="solo")

    if verdict is not None and verdict.get("call_id") not in {
        call.call_id for call in accepted
    }:
        accepted.append(_Accepted(
            heading=judge.heading, call_id=verdict["call_id"], role=judge.role,
            derived=judge.derived, raw=verdict.get("raw", ""),
            native_reasoning=verdict.get("native_reasoning", ""),
        ))
    return accepted


def _model_side(turn: Turn, config: DebateConfig | None,
                sides: Sides | None) -> str:
    """Which of the two debater models spoke, decided the way ``debate.py`` decides it.

    The draw lives in ``sides.json``, so reading it back is the only way to label the
    header row for the right speaker when the two models were swapped.
    """
    if config is None or sides is None:
        return "a"
    model = sides.model_for(turn.speaker, config.debater_model, config.debater_model_b)
    return "b" if model == config.debater_model_b else "a"


def render_full_run_record(directory: Path) -> str:
    """The verbatim document for a decision run."""
    manifest = _read(directory, "run.json") or {}
    item = _read(directory, "item.json")
    if item is None:
        return "# Incomplete run\n\nNo item was recorded.\n"

    config = _config_of(_read(directory, "config.json"))
    accepted = _run_calls(directory, config, _sides_of(_read(directory, "sides.json")))
    registry = BlockRegistry()
    parts = [
        f"# Full record — {item['item_id']}\n\n"
        f"Run `{manifest.get('run_id', directory.name)}` · condition "
        f"**{manifest.get('condition', 'unknown')}**. Every prompt and every reply, "
        "verbatim. The readable version of the same run is `transcript.md` beside this "
        "file.\n",
        _parameters_section(config, _roles_of(accepted)),
        _LEGEND,
        _material_section(registry, item),
        *_calls_sections(registry, accepted, _load_calls(directory), config),
        ground_truth_section(item, _read(directory, "flaw.json")),
    ]
    return "\n".join(part for part in parts if part).rstrip() + "\n"


def _roles_of(accepted: list[_Accepted]) -> list[tuple[str, str | None]]:
    roles: list[tuple[str, str | None]] = []
    for call in accepted:
        key = (call.role, call.model_side)
        if key not in roles:
            roles.append(key)
    return roles


# --------------------------------------------------------------------------- #
# contests
# --------------------------------------------------------------------------- #


def _parent_record(directory: Path) -> tuple[DecisionRecord | None, str]:
    """The decision as the challenger and the recourse judge were shown it.

    Recomputed from the parent's own record files rather than read out of a prompt, so
    the block is the thing the prompt builders produce and a mismatch would show up as
    an unsubstituted repetition rather than as a silent edit.
    """
    transcript_data = _read(directory, "parent/transcript.json")
    trace_data = _read(directory, "parent/trace.json")
    verdict = _read(directory, "parent/verdict.json") or {}
    if transcript_data is not None:
        record = DecisionRecord.for_debate(_transcript_of(transcript_data))
        grounds = verdict.get("raw", "")
    elif trace_data is not None:
        record = DecisionRecord.for_solo(_trace_of(trace_data))
        grounds = verdict.get("reasoning", "")
    else:
        return None, ""
    return record, grounds


def _contest_calls(directory: Path) -> list[_Accepted]:
    """The contest's own calls, in the order they were asked."""
    challenge = _read(directory, "challenge.json")
    comprehension = _read(directory, "comprehension.json")
    ruling = _read(directory, "ruling.json")
    record, grounds = _parent_record(directory)

    shown: tuple[tuple[str, str, str], ...] = ()
    if record is not None:
        shown = (("X", "the decision record the stakeholder was shown",
                  neutralise_tags(record.body)),)

    accepted: list[_Accepted] = []
    if challenge is not None:
        derived = shown
        if grounds:
            derived = (*derived, ("X", "the grounds the decision gave",
                                  neutralise_tags(grounds)))
        accepted.append(_Accepted(
            heading="challenger", call_id=challenge.get("call_id", ""),
            role="challenger", derived=derived, raw=challenge.get("raw", ""),
            native_reasoning=challenge.get("native_reasoning", ""),
        ))
    if comprehension is not None:
        accepted.append(_Accepted(
            heading="comprehension probe",
            call_id=comprehension.get("call_id", ""), role="comprehension",
            raw=comprehension.get("raw", ""),
            native_reasoning=comprehension.get("native_reasoning", ""),
        ))
    if ruling is not None:
        by_judge = ruling.get("form") == "uphold_overturn"
        derived: tuple[tuple[str, str, str], ...] = ()
        if by_judge:
            derived = shown
            if challenge is not None and challenge.get("text"):
                derived = (*derived, ("X", "the objection, as it was put to the judge",
                                      neutralise_tags(challenge["text"])))
        accepted.append(_Accepted(
            heading="ruling (recourse judge)" if by_judge else "ruling (in conversation)",
            call_id=ruling.get("call_id", ""),
            role="recourse_judge" if by_judge else "recourse_solo",
            derived=derived, raw=ruling.get("raw", ""),
            native_reasoning=ruling.get("native_reasoning", ""),
        ))
    return accepted


def render_full_recourse_record(directory: Path) -> str:
    """The verbatim document for a contest: its own calls, not the decision's."""
    manifest = _read(directory, "run.json") or {}
    item = _read(directory, "item.json")
    if item is None:
        return "# Incomplete contest\n\nNo item was recorded.\n"

    config = _config_of(_read(directory, "config.json"))
    accepted = _contest_calls(directory)
    registry = BlockRegistry()
    copied = (directory / "parent").is_dir()
    decision_pointer = (
        "The decision's own calls are in `parent/transcript_full.md`."
        if copied else
        "The decision's directory was not copied here, so its calls are not in this "
        "document; `parent.json` says where they are."
    )
    parts = [
        f"# Full contest record — {item['item_id']}\n\n"
        f"Run `{manifest.get('run_id', directory.name)}` · condition "
        f"**{manifest.get('condition', 'unknown')}** · contest of "
        f"`{manifest.get('parent_run_id', 'unknown')}`. Every prompt and every reply "
        f"of the contest, verbatim. {decision_pointer} The readable version is "
        "`transcript.md` beside this file.\n",
        _parameters_section(config, _roles_of(accepted)),
        _LEGEND,
        _material_section(registry, item),
        *_calls_sections(registry, accepted, _load_calls(directory), config),
        ground_truth_section(item, _read(directory, "parent/flaw.json")),
    ]
    return "\n".join(part for part in parts if part).rstrip() + "\n"
