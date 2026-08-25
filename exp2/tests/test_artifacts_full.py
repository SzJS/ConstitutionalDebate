"""``transcript_full.md`` — the document that has to be checkable against the wire.

The load-bearing test here is ``test_every_accepted_request_round_trips_byte_for_byte``.
Everything else in this file is about readability; that one is about whether the
reference scheme is honest. It re-derives the label table from the published document
alone — not from ``BlockRegistry`` — so a renderer bug cannot be cancelled out by the
same bug in the checker.
"""

from __future__ import annotations

import json
import re

from conftest import FakeClient
from recording import contest, recorded

from exp2.artifacts_full import fence, render_full_run_record

DEFINITION_RE = re.compile(r"^.*?\[\[([A-Z]+\d+)\]\] =(?:\s|$)")
MARKER_RE = re.compile(r"\[\[([A-Z]+\d+)\]\]")
MESSAGE_RE = re.compile(r"^\*\*(system|user|assistant)\*\* \[\[([A-Z]+\d+)\]\]")
REPLY_RE = re.compile(r"^\*\*Reply\*\* \[\[([A-Z]+\d+)\]\]")


def blocks_of(document: str) -> dict[str, str]:
    """Every label's printed text, read back out of the document and nothing else."""
    found: dict[str, str] = {}
    lines = document.splitlines()
    index = 0
    while index < len(lines):
        match = DEFINITION_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        label = match.group(1)
        index += 1
        while not lines[index].startswith("```"):
            index += 1
        bar = "`" * (len(lines[index]) - len(lines[index].lstrip("`")))
        index += 1
        body: list[str] = []
        while lines[index] != bar:
            body.append(lines[index])
            index += 1
        assert label not in found, f"{label} was defined twice"
        found[label] = "\n".join(body)
        index += 1
    return found


def expand(found: dict[str, str], text: str) -> str:
    """The legend's rule, applied literally: a reply's marker stands for it stripped."""
    def resolve(match: re.Match[str]) -> str:
        label = match.group(1)
        value = expand(found, found[label])
        return value.strip() if label.startswith("G") else value

    return MARKER_RE.sub(resolve, text)


def call_sections(document: str) -> list[list[str]]:
    sections: list[list[str]] = []
    for line in document.splitlines():
        if line.startswith("### Call "):
            sections.append([])
        if sections:
            sections[-1].append(line)
    return sections


def call_id_of(section: list[str]) -> str:
    match = re.match(r"^`([^`]+)`", section[2])
    assert match, section[:3]
    return match.group(1)


def logged_calls(directory) -> dict[str, dict]:
    return {
        record["call_id"]: record
        for record in (json.loads(line) for line
                       in (directory / "calls.jsonl").read_text().splitlines())
    }


# --- both documents, every condition -------------------------------------------------


async def test_both_documents_are_written_for_every_condition(tmp_path):
    for condition in ("debate", "single", "self_critique"):
        writer, _ = await recorded(tmp_path / condition, condition)
        names = {path.name for path in writer.dir.iterdir()}
        assert {"transcript.md", "transcript_full.md"} <= names, condition


async def test_both_documents_are_written_for_a_contest(tmp_path):
    _, _, writer, _ = await contest(tmp_path, "debate")
    assert (writer.dir / "transcript_full.md").is_file()
    assert (writer.dir / "parent" / "transcript_full.md").is_file()


# --- the invariant -------------------------------------------------------------------


async def test_every_accepted_request_round_trips_byte_for_byte(tmp_path):
    """Re-expanding every marker has to reproduce what was sent, exactly.

    The repaired run is in here because a repair's request carries the rejected reply
    as an assistant turn — the one place a generation the document otherwise omits is
    still part of what went over the wire.
    """
    runs = [
        await recorded(tmp_path / "debate", "debate"),
        await recorded(tmp_path / "critique", "self_critique"),
        await recorded(tmp_path / "repaired", "single", client=FakeClient(
            fail_on={("solo", "answer"): "malformed"})),
    ]
    for writer, _ in runs:
        document = (writer.dir / "transcript_full.md").read_text()
        found = blocks_of(document)
        calls = logged_calls(writer.dir)
        sections = call_sections(document)
        assert sections

        for section in sections:
            record = calls[call_id_of(section)]
            sent = [{"role": m.group(1), "content": expand(found, found[m.group(2)])}
                    for m in (MESSAGE_RE.match(line) for line in section) if m]
            assert sent == record["request_body"]["messages"], call_id_of(section)

            reply = next(REPLY_RE.match(line) for line in section
                         if REPLY_RE.match(line))
            wire = record["response_body"]["choices"][0]["message"]["content"]
            assert found[reply.group(1)] == wire
            assert expand(found, f"[[{reply.group(1)}]]") == wire.strip()


async def test_a_repaired_call_is_labelled_and_the_rejected_attempt_is_not_a_reply(
    tmp_path,
):
    """The rejected generation is printed only where it was actually sent."""
    client = FakeClient(fail_on={("solo", "answer"): "malformed"})
    writer, _ = await recorded(tmp_path, "single", client=client)
    document = (writer.dir / "transcript_full.md").read_text()
    assert "accepted after one format repair" in document
    # once, as the assistant turn inside the repair request — never as a Reply block
    assert document.count("no labels here at all") == 1
    assert len(call_sections(document)) == 1


# --- the reference scheme ------------------------------------------------------------


async def test_each_distinct_text_is_printed_once(tmp_path):
    writer, _ = await recorded(tmp_path, "debate")
    document = (writer.dir / "transcript_full.md").read_text()
    assert document.count("What is the third Catalan number?") == 1
    assert document.count("Step 2: C_3 = 6.") == 1
    # the round-1 rendering is defined once and referred to by both round-2 requests
    assert document.count("Round 1:\n  Alice:") == 1
    assert document.count("[[X1]]") >= 3


async def test_a_later_rendering_refers_to_the_earlier_one_it_contains(tmp_path):
    """Definitions are substituted too, so nesting shows rather than repeats."""
    writer, _ = await recorded(tmp_path, "debate")
    found = blocks_of((writer.dir / "transcript_full.md").read_text())
    assert "[[X1]]" in found["X2"]
    assert expand(found, found["X2"]).startswith(expand(found, found["X1"]))


async def test_model_text_is_never_defanged_and_fences_outrun_its_backticks(tmp_path):
    """The readable document defangs; this one may not, or it is not a wire record."""
    argument = "\n# Fake heading\n```\nprint(1)\n```\nnormal text"
    client = FakeClient(replies={(1, "Alice"): f"Thinking: t\nArgument:{argument}"})
    writer, _ = await recorded(tmp_path, "debate", client=client)
    document = (writer.dir / "transcript_full.md").read_text()
    assert "​" not in document  # the zero-width space defang_markdown inserts
    assert "\n# Fake heading" in document
    assert "````text" in document


def test_a_fence_is_always_longer_than_the_longest_backtick_run():
    assert fence("plain") == "```"
    assert fence("a ``` b") == "````"
    assert fence("`````") == "``````"


# --- the header ----------------------------------------------------------------------


async def test_the_parameters_are_stated_once_and_nothing_deviates_from_them(tmp_path):
    writer, _ = await recorded(tmp_path, "debate")
    document = (writer.dir / "transcript_full.md").read_text()
    assert document.count("## Parameters") == 1
    assert "| Debater | `strong/model` | 0.7 | 8192 | off | 0.0 |" in document
    assert "| Judge | `weak/model` | 0.0 | 8192 | off | 0.0 |" in document
    assert "Deviates from header" not in document


async def test_a_call_made_with_other_settings_says_so(tmp_path):
    """The header is a claim about the run; a call that contradicts it must show."""
    writer, _ = await recorded(tmp_path, "debate")
    config = json.loads((writer.dir / "config.json").read_text())
    config["judge_temperature"] = 0.5
    (writer.dir / "config.json").write_text(json.dumps(config))
    document = render_full_run_record(writer.dir)
    assert document.count("Deviates from header") == 1
    assert "temperature 0.0 (header 0.5)" in document


# --- native reasoning ----------------------------------------------------------------


async def test_native_reasoning_is_printed_when_the_provider_returned_it(tmp_path):
    client = FakeClient(native_reasoning="the provider's own working")
    writer, _ = await recorded(tmp_path, "single", client=client)
    document = (writer.dir / "transcript_full.md").read_text()
    assert "**Native reasoning**" in document
    assert "the provider's own working" in document


# --- degradation ---------------------------------------------------------------------


async def test_without_a_wire_log_the_generations_are_still_published(tmp_path):
    writer, _ = await recorded(tmp_path, "self_critique")
    (writer.dir / "calls.jsonl").unlink()
    document = render_full_run_record(writer.dir)
    assert "Prompts were not recorded for this run" in document
    assert "**Request**" not in document
    assert len(call_sections(document)) == 7  # draft + (critique, revision) * 3
    assert "my revision assessment." in document


async def test_a_half_written_wire_log_line_does_not_break_the_render(tmp_path):
    writer, _ = await recorded(tmp_path, "debate")
    with (writer.dir / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"call_id": "truncated hal')
    assert "# Full record" in render_full_run_record(writer.dir)


# --- contests ------------------------------------------------------------------------


async def test_a_solo_contest_prints_the_replayed_conversation_once(tmp_path):
    """The ruling re-sends the whole decision conversation; the contest document is
    self-contained, so it prints it, and prints it once."""
    _, _, writer, _ = await contest(tmp_path, "single")
    document = (writer.dir / "transcript_full.md").read_text()
    assert document.count(
        "You are reviewing a piece of reasoning to decide whether it contains a flaw."
    ) == 1
    headings = [section[0] for section in call_sections(document)]
    assert headings == ["### Call 1 — challenger", "### Call 2 — comprehension probe",
                        "### Call 3 — ruling (in conversation)"]


async def test_a_debate_contest_points_at_the_decisions_own_document(tmp_path):
    _, _, writer, _ = await contest(tmp_path, "debate")
    document = (writer.dir / "transcript_full.md").read_text()
    assert "`parent/transcript_full.md`" in document
    headings = [section[0] for section in call_sections(document)]
    assert headings[-1] == "### Call 3 — ruling (recourse judge)"


async def test_the_record_the_stakeholder_read_is_a_block_shared_with_the_judge(
    tmp_path,
):
    _, _, writer, _ = await contest(tmp_path, "debate")
    document = (writer.dir / "transcript_full.md").read_text()
    assert "= the decision record the stakeholder was shown" in document
    assert document.count("Round 1:\n  Alice:") == 1


# --- the answer, last ----------------------------------------------------------------


async def test_the_full_document_ends_with_the_ground_truth(tmp_path):
    writer, result = await recorded(tmp_path, "debate")
    document = (writer.dir / "transcript_full.md").read_text()
    head, marker, tail = document.rpartition("\n## Ground truth")
    assert marker
    assert "\n## " not in tail
    assert result.item.gold_verdict in tail
    for leak in ("gold", "ground truth", "label_basis"):
        assert leak not in head.lower()
