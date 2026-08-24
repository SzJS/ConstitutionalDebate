"""The recourse CLI: what it refuses, and what it inherits.

No test here touches the network.
"""

from __future__ import annotations

import json

import pytest

from helpers import JUDGE_COT, recorded_run

from constitutional_debate.cli import API_KEY_ENV
from constitutional_debate.recourse_cli import main


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """Stop load_dotenv pulling a real key out of the repo's .env."""
    monkeypatch.setattr(
        "constitutional_debate.recourse_cli.load_dotenv", lambda *a, **k: None
    )
    monkeypatch.delenv(API_KEY_ENV, raising=False)


@pytest.fixture
async def parent(tmp_path, task, seating, config):
    writer, _ = await recorded_run(
        tmp_path / "parent", task, config, seating, scripted={"judge": JUDGE_COT}
    )
    return writer


@pytest.fixture
def challenge_file(tmp_path):
    path = tmp_path / "challenge.md"
    path.write_text("The decision rests on a figure neither debater supported.\n")
    return path


def run(tmp_path, parent, *args) -> int:
    return main(["--outputs", str(tmp_path / "out"), "--run", str(parent.dir), *args])


def only_run_dir(tmp_path):
    return next((tmp_path / "out" / "runs").iterdir())


async def test_a_dry_run_renders_the_real_prompts(tmp_path, parent, challenge_file):
    assert run(tmp_path, parent, "--challenge", str(challenge_file), "--dry-run") == 0

    run_dir = only_run_dir(tmp_path)
    manifest = json.loads((run_dir / "run.json").read_text())
    assert manifest["status"] == "dryrun"
    assert manifest["kind"] == "recourse"
    assert not (run_dir / "parent").exists(), "a dry run leaves no half-formed record"

    prompts = (run_dir / "prompts.dryrun.md").read_text()
    assert "Ruling: <UPHOLD|OVERTURN>" in prompts
    # The parent transcript exists, so these are the prompts that would be sent.
    assert "Alice argument round 1" in prompts
    assert "figure neither debater supported" in prompts
    assert "(pro)" in prompts and "(anti)" in prompts


async def test_a_dry_run_marks_where_a_generated_challenge_would_go(
    tmp_path, parent
):
    assert run(tmp_path, parent, "--generate", "grounded", "--dry-run") == 0

    prompts = (only_run_dir(tmp_path) / "prompts.dryrun.md").read_text()
    assert "challenger [system]" in prompts
    assert "Find a real error." in prompts
    assert "the generated challenge appears here" in prompts


async def test_the_judge_only_protocol_renders_no_debater_prompts(tmp_path, parent, challenge_file):
    assert (
        run(
            tmp_path, parent, "--challenge", str(challenge_file),
            "--recourse-rounds", "0", "--dry-run",
        )
        == 0
    )
    prompts = (only_run_dir(tmp_path) / "prompts.dryrun.md").read_text()
    assert "Ruling: <UPHOLD|OVERTURN>" in prompts
    assert "recourse r4" not in prompts


async def test_an_unfinished_run_cannot_be_contested(tmp_path, task, seating, config):
    from helpers import make_writer

    unfinished = make_writer(tmp_path / "parent", task, config, seating)
    assert run(tmp_path, unfinished, "--generate", "neutral", "--dry-run") == 2


async def test_a_challenge_must_be_supplied_or_generated_but_not_both(
    tmp_path, parent, challenge_file
):
    with pytest.raises(SystemExit):  # argparse rejects both at once
        run(
            tmp_path, parent,
            "--challenge", str(challenge_file), "--generate", "neutral", "--dry-run",
        )
    with pytest.raises(SystemExit):  # ...and neither
        run(tmp_path, parent, "--dry-run")


async def test_visibility_is_meaningless_for_a_supplied_challenge(
    tmp_path, parent, challenge_file
):
    """A supplied challenge was written by whoever wrote it; the flag would lie."""
    assert (
        run(
            tmp_path, parent, "--challenge", str(challenge_file),
            "--challenge-visibility", "full", "--dry-run",
        )
        == 2
    )


async def test_an_empty_challenge_file_is_refused(tmp_path, parent):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n")
    assert run(tmp_path, parent, "--challenge", str(empty), "--dry-run") == 2


async def test_the_recourse_inherits_the_parents_settings_not_the_defaults(
    tmp_path, task, seating, make_config, challenge_file
):
    """A decision made at 250 words is contested at 250 words, not at the default."""
    writer, _ = await recorded_run(
        tmp_path / "parent", task, make_config(word_limit=250), seating,
        scripted={"judge": JUDGE_COT},
    )
    assert run(tmp_path, writer, "--challenge", str(challenge_file), "--dry-run") == 0

    config = json.loads((only_run_dir(tmp_path) / "config.json").read_text())
    assert config["word_limit"] == 250


async def test_the_recourse_inherits_the_parents_profile_and_constitution(
    tmp_path, task, seating, config, challenge_file
):
    from helpers import CONSTITUTION

    writer, _ = await recorded_run(
        tmp_path / "parent", task, config, seating, CONSTITUTION,
        scripted={"judge": JUDGE_COT},
    )
    assert run(tmp_path, writer, "--challenge", str(challenge_file), "--dry-run") == 0

    run_dir = only_run_dir(tmp_path)
    assert json.loads((run_dir / "run.json").read_text())["profile"] == "constitutional"
    assert (run_dir / "constitution.md").read_text() == CONSTITUTION.text
    prompts = (run_dir / "prompts.dryrun.md").read_text()
    assert CONSTITUTION.text in prompts
    assert "the constitution below is the only standard" in prompts.lower()


async def test_the_round_boundary_cannot_be_moved_by_a_config_file(
    tmp_path, parent, challenge_file
):
    config_file = tmp_path / "other.toml"
    config_file.write_text("[debate]\nn_rounds = 5\n")
    assert (
        run(
            tmp_path, parent, "--challenge", str(challenge_file),
            "--config", str(config_file), "--dry-run",
        )
        == 2
    )


async def test_a_missing_api_key_exits_two_rather_than_starting(
    tmp_path, parent, challenge_file
):
    assert run(tmp_path, parent, "--challenge", str(challenge_file)) == 2
    manifest = json.loads((only_run_dir(tmp_path) / "run.json").read_text())
    assert manifest["status"] == "failed"


async def test_the_recourse_round_can_be_run_sequentially(
    tmp_path, parent, challenge_file
):
    """A simultaneous debate may reasonably be contested sequentially, so that
    the debater defending the decision answers the case against it."""
    assert (
        run(
            tmp_path, parent, "--challenge", str(challenge_file),
            "--turn-style", "sequential", "--dry-run",
        )
        == 0
    )
    config = json.loads((only_run_dir(tmp_path) / "config.json").read_text())
    assert config["turn_style"] == "sequential"
