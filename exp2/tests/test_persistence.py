"""The run directory, and the document it publishes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import SECRET_THINKING, make_config, make_item, make_sides, make_turn
from recording import client_config, recorded

from exp2.persistence import RunWriter, load_flaw, load_run_record, tree_sha256
from exp2.types import FLAWED, FlawAnnotation


# --- layout --------------------------------------------------------------------------


async def test_a_debate_run_writes_the_expected_files(tmp_path):
    writer, _ = await recorded(tmp_path, "debate")
    names = {p.name for p in writer.dir.iterdir()}
    assert {"item.json", "sides.json", "config.json", "run.json",
            "transcript.json", "verdict.json", "transcript.md"} <= names


async def test_a_solo_run_writes_the_conversation(tmp_path):
    writer, result = await recorded(tmp_path, "self_critique")
    saved = json.loads((writer.dir / "conversation.json").read_text())
    assert saved == result.messages
    assert saved[-1]["role"] == "assistant"


async def test_a_completed_run_round_trips(tmp_path):
    writer, result = await recorded(tmp_path, "debate")
    record = load_run_record(writer.dir)
    assert record.item.item_id == result.item.item_id
    assert record.verdict.verdict == result.verdict.verdict
    assert record.transcript is not None and record.trace is None
    assert record.challenger_view().kind == "debate"


async def test_a_solo_run_round_trips_to_the_solo_shape(tmp_path):
    writer, _ = await recorded(tmp_path, "single")
    record = load_run_record(writer.dir)
    assert record.trace is not None and record.transcript is None
    assert record.challenger_view().kind == "solo"


async def test_an_unfinished_run_is_refused(tmp_path):
    writer = RunWriter.create(
        root=tmp_path, item=make_item(), sides=make_sides(), config=make_config(),
        client_config=client_config(), condition="single")
    with pytest.raises(ValueError, match="status is"):
        load_run_record(writer.dir)


# --- containment ---------------------------------------------------------------------


async def test_the_flaw_annotation_is_written_but_never_loaded_with_the_run(tmp_path):
    """Structural containment: no decision-path code can reach the answer by accident."""
    flaw = FlawAnnotation(annotation_id="a", annotation="Step 2 divides by zero.",
                          annotation_quality="explanation")
    writer, _ = await recorded(tmp_path, "single", flaw=flaw)
    record = load_run_record(writer.dir)
    # the annotation text reaches nothing a decision or contest touches
    assert not hasattr(record, "flaw")
    assert "divides by zero" not in json.dumps(record.item.to_dict())
    head, _, tail = _split_at_ground_truth((writer.dir / "transcript.md").read_text())
    assert "divides by zero" not in head
    assert "divides by zero" in tail
    # only the dedicated door opens it
    assert load_flaw(writer.dir).annotation == "Step 2 divides by zero."
    assert load_flaw(tmp_path / "nonexistent") is None


def _split_at_ground_truth(document: str) -> tuple[str, str, str]:
    head, marker, tail = document.rpartition("\n## Ground truth")
    assert marker, "the document has no ground-truth section"
    return head, marker, tail


async def test_ground_truth_is_the_last_section_and_appears_nowhere_earlier(tmp_path):
    """A reader who knows the answer first can only say whether they agree with the
    decision, not whether the record was legible enough to check it."""
    writer, result = await recorded(tmp_path, "debate")
    head, _, tail = _split_at_ground_truth(
        (writer.dir / "transcript.md").read_text())
    assert "\n## " not in tail  # nothing follows it
    for leak in ("gold", "ground truth", "label_basis"):
        assert leak not in head.lower()
    assert result.item.gold_verdict in tail
    assert "label_basis" in tail


async def test_solo_decision_grounds_exclude_private_thinking(tmp_path):
    """exp1's bug: a public-visibility challenger was shown the agent's Thinking block,
    because a solo verdict's raw contains it and the debate shape's does not."""
    writer, _ = await recorded(tmp_path, "single")
    record = load_run_record(writer.dir)
    assert SOLO_THINKING not in record.decision_grounds
    assert record.decision_grounds  # but it is not empty


# --- the published document ----------------------------------------------------------


async def test_a_debate_document_states_positions_and_a_solo_one_denies_them(tmp_path):
    debate_writer, _ = await recorded(tmp_path / "d", "debate")
    solo_writer, _ = await recorded(tmp_path / "s", "single")
    debate_doc = (debate_writer.dir / "transcript.md").read_text()
    solo_doc = (solo_writer.dir / "transcript.md").read_text()

    assert "## Positions" in debate_doc
    assert "argued that the text contains a flaw" in debate_doc
    assert "## Positions" not in solo_doc
    assert "No positions were assigned and nobody argued a side" in solo_doc
    for name in ("Alice", "Bob"):
        assert name not in solo_doc


async def test_the_document_publishes_the_problem_the_solution_and_the_grounds(tmp_path):
    writer, _ = await recorded(tmp_path, "debate")
    document = (writer.dir / "transcript.md").read_text()
    assert "### The problem" in document
    assert "### The text under review" in document
    assert "Step 2: C_3 = 6." in document       # the solution is published
    assert "**Grounds given:**" in document


def test_the_verdict_is_printed_after_the_grounds_it_followed_from():
    """The exact shape 12 of pilot 2's records carry: the model's reasoning ends on a
    dangling `**Final verdict:**` header, because ``parse_verdict_output`` cuts the
    grounds at the decision line and the header sits just before it. Printed above the
    grounds, the header pointed at nothing. Nothing is edited to fix it — the order is."""
    from exp2.artifacts import _decision_section

    section = _decision_section({
        "verdict": "FLAWED",
        "reasoning": "Step 2 divides by zero.\n\n**Final verdict:**",
        "repair_attempts": 0,
    })
    assert section.index("**Grounds given:**") < section.index("**Verdict:**")
    # the model's own run-up runs straight into the verdict, and its text is untouched
    assert "> **Final verdict:**" in section
    assert section.rstrip().endswith("**Verdict:** the text under review "
                                     "**contains a flaw**.")


def test_the_repair_note_travels_with_the_verdict_line():
    """It is a statement about which reply the verdict came from, so it has to sit with
    the verdict — and it says "above" now that the grounds are printed first."""
    from exp2.artifacts import _decision_section

    section = _decision_section({
        "verdict": "SOUND", "reasoning": "It checks out.", "repair_attempts": 1,
    })
    assert section.index("**Verdict:**") < section.index("format-repair reply")
    assert "the grounds above are from that reply" in section
    assert "grounds below" not in section


async def test_a_ruling_prints_its_grounds_before_the_verdict_too(tmp_path):
    """Same rendering artifact, same fix: a re-decider ends on the same dangling
    header as the decider did."""
    from exp2.artifacts import render_recourse_record

    writer, _ = await recorded(tmp_path, "debate")
    import json
    (writer.dir / "ruling.json").write_text(json.dumps({
        "form": "uphold_overturn", "ruling": "OVERTURN", "upheld": False,
        "verdict": "SOUND", "reasoning": "The objection lands.\n\n**Ruling:**",
    }), encoding="utf-8")
    (writer.dir / "challenge.json").write_text(json.dumps({
        "text": "Step 2 is fine.", "origin": "generated", "raised": True,
        "stance": "contests", "claimed_verdict": "SOUND",
    }), encoding="utf-8")
    document = render_recourse_record(writer.dir)
    assert document.index("**Grounds given:**") < document.index("**Verdict now:**")


async def test_private_reasoning_is_not_in_the_readable_document_but_is_pointed_to(
    tmp_path,
):
    """It still has to be published somewhere — that is the transparency claim — but
    the readable document is read straight through, and nobody saw it there."""
    writer, _ = await recorded(tmp_path, "self_critique")
    document = (writer.dir / "transcript.md").read_text()
    assert "## Private reasoning" not in document
    assert SOLO_THINKING not in document
    assert SECRET_THINKING not in document
    assert "`transcript_full.md`" in document


def test_no_model_facing_module_reads_the_published_documents():
    """The documents end with the ground truth, so anything on the decision or contest
    path that opened one would be reading the answer out of a file it published."""
    import exp2

    package = Path(exp2.__file__).resolve().parent
    mentioning = {
        path.name for path in package.glob("*.py")
        if "transcript.md" in path.read_text(encoding="utf-8")
        or "transcript_full.md" in path.read_text(encoding="utf-8")
    }
    decision_path = {"prompts.py", "arms.py", "debate.py", "recourse.py", "engine.py",
                     "experiment.py", "grading.py", "types.py"}
    assert not mentioning & decision_path
    assert mentioning <= {"artifacts.py", "artifacts_full.py", "persistence.py",
                          "cli.py"}


async def test_model_text_cannot_forge_document_structure(tmp_path):
    client = FakeClient(replies={
        (1, "Alice"): "Thinking: t\nArgument: # Fake heading\n---\nnormal text"})
    writer, _ = await recorded(tmp_path, "debate", client=client)
    document = (writer.dir / "transcript.md").read_text()
    assert "\n# Fake heading" not in document


# --- durability ----------------------------------------------------------------------


async def test_writes_are_atomic(tmp_path):
    """A half-written transcript.md is worse than a missing one: it looks like a record."""
    writer, _ = await recorded(tmp_path, "debate")
    assert not list(writer.dir.glob("*.tmp"))
    assert (writer.dir / "transcript.md").read_text().endswith("\n")


async def test_concurrent_call_records_produce_valid_json_lines(tmp_path):
    writer = RunWriter.create(
        root=tmp_path, item=make_item(), sides=make_sides(), config=make_config(),
        client_config=client_config(), condition="debate")
    await asyncio.gather(*(
        writer.record_call({"call_id": f"c{n}", "role": "debater", "body": "x" * 2000})
        for n in range(50)
    ))
    lines = (writer.dir / "calls.jsonl").read_text().strip().splitlines()
    assert len(lines) == 50
    assert all(json.loads(line)["role"] == "debater" for line in lines)


def test_tree_sha256_changes_when_a_file_does(tmp_path):
    (tmp_path / "a.txt").write_text("one")
    before = tree_sha256(tmp_path)
    (tmp_path / "a.txt").write_text("two")
    assert tree_sha256(tmp_path) != before


# --- a contest copied for re-ruling ---------------------------------------------------


async def test_create_rerule_copies_the_objection_and_leaves_the_ruling_behind(tmp_path):
    """The objection is the stakeholder's, it cost real money, and re-drawing it would
    change the population as well as the ruling. So everything the source recorded comes
    across except the four things about to be replaced — and the source ruling is kept
    beside the new one, so the record carries both."""
    import json

    from recording import contest

    from exp2.persistence import tree_sha256

    _, _, source_writer, _ = await contest(tmp_path, "debate")
    source = source_writer.dir
    (source / "ruling_agreement.json").write_text('{"prose_conclusion": "SOUND"}',
                                                  encoding="utf-8")
    before = tree_sha256(source)

    writer = RunWriter.create_rerule(
        root=tmp_path / "rerule", source_dir=source,
        item=make_item(), sides=make_sides(), client_config=client_config(),
        condition="debate")

    copied = {p.name for p in writer.dir.iterdir()}
    assert {"challenge.json", "challenge.md", "comprehension.json", "item.json",
            "sides.json", "config.json", "parent"} <= copied
    # the four that must not come across
    assert "ruling.json" not in copied
    assert "calls.jsonl" not in copied
    assert "ruling_agreement.json" not in copied
    assert not [name for name in copied if name.startswith("transcript")]
    # ... but the copied DECISION keeps its own log and its own documents, which is what
    # makes the record self-contained
    assert (writer.dir / "parent" / "calls.jsonl").is_file()
    assert (writer.dir / "parent" / "transcript.md").is_file()

    assert json.loads((writer.dir / "ruling.source.json").read_text())["form"] == (
        "stated_conclusion")
    manifest = json.loads((writer.dir / "run.json").read_text())
    assert manifest["kind"] == "rerule"
    assert manifest["source_contest_dir"] == str(source)
    assert manifest["source_sha256"] == before
    assert manifest["rerule_of_form"] == "stated_conclusion"
    assert manifest["parent_run_id"]          # still names the decision it contests
    assert writer.rerule_of_form == "stated_conclusion"
    # and nothing under the source moved
    assert tree_sha256(source) == before


async def test_a_re_ruled_record_renders_as_a_contest_and_not_as_a_decision(tmp_path):
    """`record_ruling` re-renders both documents from the new state. A stale document
    saying "the decision was overturned" beside a ruling that upheld it is worse than a
    missing one, and a re-rule that rendered as a DECISION record would lose the
    objection entirely."""
    from recording import contest

    from exp2.types import Ruling

    outcome, _, source_writer, _ = await contest(tmp_path, "debate")
    source = source_writer.dir
    writer = RunWriter.create_rerule(
        root=tmp_path / "rerule", source_dir=source,
        item=make_item(), sides=make_sides(), client_config=client_config(),
        condition="debate")
    writer.record_ruling(Ruling(
        form="stated_conclusion", ruling="UPHOLD", protocol="judge_only",
        parent_verdict=outcome.ruling.parent_verdict,
        verdict=outcome.ruling.parent_verdict, parse_mode="strict",
        conclusion_line="Conclusion: the original text in <solution> contains a flaw",
        raw="Conclusion: the original text in <solution> contains a flaw",
        call_id="c9", finish_reason="stop", correct=True,
        reasoning="The objection does not land."))
    document = (writer.dir / "transcript.md").read_text()
    assert document.startswith("# Contest record")
    assert "The decision was **upheld**." in document
    assert "The judge stated its own conclusion about the text under review" in document
    assert "The objection does not land." in document


# --- the contestability debate round's own turns --------------------------------------


async def test_record_recourse_turn_writes_beside_the_copy_and_never_a_transcript(
        tmp_path):
    """A contest directory must never hold `transcript.json`.

    `load_run_record` reads that name and would load this contest as a DECISION whose
    debate is two turns long — while the copied `parent/` beside it is the record that
    actually holds the debate. So the round's own turns get their own name, and the
    reader that goes with it returns None where no round was heard.
    """
    import json

    from recording import contest

    from exp2.persistence import load_recourse_transcript
    from exp2.types import Speaker, Transcript

    _, _, writer, record = await contest(tmp_path, "debate")
    own = Transcript()
    for speaker in (Speaker.ALICE, Speaker.BOB):
        own.add(make_turn(4, speaker, record.sides.side_for(speaker)))
    writer.record_recourse_turn(own)

    assert (writer.dir / "recourse_transcript.json").is_file()
    assert not (writer.dir / "transcript.json").is_file()
    stored = json.loads((writer.dir / "recourse_transcript.json").read_text())
    assert [t["round"] for t in stored["turns"]] == [4, 4]
    # full Turns, thinking included: `transcript_full.md` is where the private half is
    # published and `transcript.md` prints the arguments only
    assert all(t["thinking"] for t in stored["turns"])
    back = load_recourse_transcript(writer.dir)
    assert [t.speaker.value for t in back.all_turns()] == ["Alice", "Bob"]
    assert load_recourse_transcript(writer.dir / "parent") is None


async def test_create_rerule_leaves_another_runs_exchange_behind(tmp_path):
    """A re-rule that copied the round forward would put ANOTHER run's exchange in front
    of this run's judge, and `render_recourse_record` would print it as though these
    debaters had argued here."""
    from recording import contest

    from exp2.types import Speaker, Transcript

    _, _, source_writer, record = await contest(tmp_path, "debate")
    own = Transcript()
    for speaker in (Speaker.ALICE, Speaker.BOB):
        own.add(make_turn(4, speaker, record.sides.side_for(speaker)))
    source_writer.record_recourse_turn(own)

    writer = RunWriter.create_rerule(
        root=tmp_path / "rerule", source_dir=source_writer.dir,
        item=make_item(), sides=make_sides(), client_config=client_config(),
        condition="debate")
    assert not (writer.dir / "recourse_transcript.json").exists()
