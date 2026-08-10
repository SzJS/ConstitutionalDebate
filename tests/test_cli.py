"""CLI exit codes and run-state handling. No test here touches the network."""

from __future__ import annotations

import json

import pytest

from constitutional_debate.cli import API_KEY_ENV, main


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """Stop load_dotenv pulling a real key out of the repo's .env."""
    monkeypatch.setattr("constitutional_debate.cli.load_dotenv", lambda *a, **k: None)


def run(tmp_path, *args) -> int:
    return main(["--outputs", str(tmp_path), *args])


def only_run_dir(tmp_path):
    return next((tmp_path / "runs").iterdir())


def test_dry_run_writes_a_run_dir_and_exits_zero(tmp_path, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert run(tmp_path, "--task", "examples/tax_havens.json", "--dry-run") == 0

    run_dir = only_run_dir(tmp_path)
    manifest = json.loads((run_dir / "run.json").read_text())
    assert manifest["status"] == "dryrun"
    assert manifest["profile"] == "opinion"

    prompts = (run_dir / "prompts.dryrun.md").read_text()
    assert "constitution" not in prompts.lower(), "no constitution was supplied"
    assert "Answer: <1|2>" in prompts


def test_dry_run_with_a_constitution_selects_that_profile(tmp_path, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert (
        run(
            tmp_path,
            "--task", "examples/tax_havens.json",
            "--constitution", "constitutions/minimal.md",
            "--dry-run",
        )
        == 0
    )
    run_dir = only_run_dir(tmp_path)
    assert json.loads((run_dir / "run.json").read_text())["profile"] == "constitutional"
    assert (run_dir / "constitution.md").is_file()


def test_missing_api_key_exits_two_and_marks_the_run_failed(tmp_path, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert run(tmp_path, "--task", "examples/tax_havens.json") == 2

    manifest = json.loads((only_run_dir(tmp_path) / "run.json").read_text())
    assert manifest["status"] == "failed"
    assert API_KEY_ENV in manifest["error"]


def test_missing_api_key_message_names_the_right_variable(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    run(tmp_path, "--task", "examples/tax_havens.json")
    stderr = capsys.readouterr().err
    assert "OPENROUTER_KEY" in stderr
    assert "not OPENROUTER_API_KEY" in stderr, "the name is the easy mistake"


def test_bad_config_exits_two_without_creating_a_run(tmp_path):
    assert run(tmp_path, "--task", "examples/tax_havens.json", "--rounds", "0") == 2
    assert not (tmp_path / "runs").exists(), "no run dir for a config that never ran"


def test_missing_task_file_exits_two(tmp_path):
    assert run(tmp_path, "--task", str(tmp_path / "nope.json")) == 2


def test_constitutional_profile_without_a_constitution_exits_two(tmp_path):
    assert (
        run(
            tmp_path,
            "--task", "examples/tax_havens.json",
            "--profile", "constitutional",
            "--dry-run",
        )
        == 2
    )


def test_cli_overrides_beat_the_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    run(
        tmp_path,
        "--task", "examples/tax_havens.json",
        "--turn-style", "sequential",
        "--rounds", "1",
        "--dry-run",
    )
    config = json.loads((only_run_dir(tmp_path) / "config.json").read_text())
    assert config["turn_style"] == "sequential"
    assert config["n_rounds"] == 1


def test_a_verifiable_task_selects_the_paper_profile(tmp_path, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    run(tmp_path, "--task", "examples/factual_capital.json", "--dry-run")
    manifest = json.loads((only_run_dir(tmp_path) / "run.json").read_text())
    assert manifest["profile"] == "paper"
