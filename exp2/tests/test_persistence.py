"""The run directory, and the document it publishes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from conftest import SOLO_THINKING, FakeClient
from helpers import SECRET_THINKING, make_config, make_item, make_sides
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
