"""The sweep driver, exercised as a shell script against a stub stage command.

`scripts/run_sweep.sh` is the thing that actually runs the 13-hour sweep, and the one
behaviour that matters is what it does when a stage crashes: halt, leave a record of
where, and NOT run the four stages behind it. Contest reads decide's artifacts, so a
driver that carried on past a crashed decide would produce a contest over half a corpus
and no error anywhere.

The stub stands in for `uv run exp2-experiment` (RUN_SWEEP_CMD), so no model is called
and the test runs in milliseconds. What is under test is the driver's sequencing and its
STOP/DONE bookkeeping, not the stages — those have their own tests, and
`scripts/e2e_offline.py` runs all five against the fake client.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "scripts" / "run_sweep.sh"

# Records each invocation's stage, and fails on the stage named in FAIL_AT if that file
# is present — so one stub covers both the happy path and the crash.
STUB = """#!/usr/bin/env bash
stage=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage) stage=$2; shift 2 ;;
        *) shift ;;
    esac
done
echo "stub running stage $stage"
echo "$stage" >> "$RAN_LOG"
if [[ -f "$FAIL_AT" && "$(cat "$FAIL_AT")" == "$stage" ]]; then
    echo "stub: pretending $stage crashed" >&2
    exit 7
fi
exit 0
"""


def drive(tmp_path: Path, *, fail_at: str | None = None, name: str = "sweep-test"):
    spec = tmp_path / "spec.toml"
    spec.write_text(f'name = "{name}"\ncases = "nowhere.jsonl"\n', encoding="utf-8")
    stub = tmp_path / "stub.sh"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    ran = tmp_path / "ran.txt"
    fail_marker = tmp_path / "fail_at.txt"
    if fail_at:
        fail_marker.write_text(fail_at, encoding="utf-8")

    proc = subprocess.run(
        ["bash", str(DRIVER), str(spec)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "RUN_SWEEP_CMD": str(stub),
            "RUN_SWEEP_LOGS": str(tmp_path / "logs"),
            "RUN_SWEEP_OUTPUTS": str(tmp_path / "experiments"),
            "RAN_LOG": str(ran),
            "FAIL_AT": str(fail_marker),
        },
    )
    stages = ran.read_text(encoding="utf-8").split() if ran.exists() else []
    return proc, stages, tmp_path / "experiments" / name


ALL_FIVE = ["decide", "contest", "agreement", "grade", "analyse"]


def test_all_five_stages_run_in_order_and_leave_done(tmp_path: Path):
    proc, stages, root = drive(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert stages == ALL_FIVE
    assert not (root / "STOP.md").exists()
    done = (root / "DONE.md").read_text(encoding="utf-8")
    assert "All five stages completed" in done
    # Completing is not succeeding, and the file has to say so where it is read.
    assert "metrics.json" in done
    for stage in ALL_FIVE:
        log = tmp_path / "logs" / f"sweep-test-{stage}.log"
        assert f"stub running stage {stage}" in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("fail_at", ["decide", "agreement", "analyse"])
def test_a_failing_stage_halts_the_chain_and_writes_stop(tmp_path: Path, fail_at: str):
    proc, stages, root = drive(tmp_path, fail_at=fail_at)
    expected = ALL_FIVE[: ALL_FIVE.index(fail_at) + 1]
    assert stages == expected, "stages after the failure must not have run"
    assert proc.returncode == 7, "the driver exits with the stage's own code"
    assert not (root / "DONE.md").exists()
    stop = (root / "STOP.md").read_text(encoding="utf-8")
    assert f"`{fail_at}`" in stop
    assert "`7`" in stop
    assert f"the stages after `{fail_at}` were NOT run" in stop.lower() or \
        f"stages after `{fail_at}` were NOT run" in stop


def test_a_rerun_clears_the_previous_stop(tmp_path: Path):
    """A STOP.md left by a crash must not outlive the run that repairs it.

    The driver is polled by reading these two files, so a stale STOP.md beside a fresh
    DONE.md would report a halt that has already been fixed.
    """
    _, _, root = drive(tmp_path, fail_at="contest")
    assert (root / "STOP.md").exists()
    (tmp_path / "ran.txt").unlink()
    (tmp_path / "fail_at.txt").unlink()
    proc, stages, root = drive(tmp_path)
    assert proc.returncode == 0
    assert stages == ALL_FIVE
    assert not (root / "STOP.md").exists()
    assert (root / "DONE.md").exists()


def test_the_name_falls_back_to_the_spec_stem(tmp_path: Path):
    """`experiment_cli.py` derives the name the same way; the two must not drift."""
    spec = tmp_path / "unnamed.toml"
    spec.write_text('cases = "nowhere.jsonl"\n', encoding="utf-8")
    stub = tmp_path / "stub.sh"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    proc = subprocess.run(
        ["bash", str(DRIVER), str(spec)],
        cwd=tmp_path, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "RUN_SWEEP_CMD": str(stub),
             "RUN_SWEEP_LOGS": str(tmp_path / "logs"),
             "RUN_SWEEP_OUTPUTS": str(tmp_path / "experiments"),
             "RAN_LOG": str(tmp_path / "ran.txt"),
             "FAIL_AT": str(tmp_path / "none.txt")},
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "experiments" / "unnamed" / "DONE.md").exists()
    assert (tmp_path / "logs" / "unnamed-decide.log").exists()


def test_a_missing_spec_fails_before_anything_is_spent(tmp_path: Path):
    proc = subprocess.run(
        ["bash", str(DRIVER), str(tmp_path / "nope.toml")],
        cwd=tmp_path, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 66
    assert "no such spec" in proc.stderr


def test_no_spec_prints_the_usage_line(tmp_path: Path):
    proc = subprocess.run(
        ["bash", str(DRIVER)], cwd=tmp_path, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 64
    assert "nohup scripts/run_sweep.sh" in proc.stderr
