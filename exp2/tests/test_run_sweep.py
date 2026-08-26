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

import os
import signal
import subprocess
import time
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
if [[ -n "${STUB_SLEEP:-}" ]]; then
    # The long stage. Its own pid goes on disk so the test can assert the PROCESS is
    # gone, not merely that the driver stopped waiting for it. bash may exec `sleep`
    # in place, which keeps this pid, so one number covers the whole stub.
    echo $$ > "$STUB_PID_FILE"
    sleep "$STUB_SLEEP"
    echo "stub: $stage slept the whole way through" >> "$RAN_LOG"
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


# --- a signal to the driver has to stop the stage ------------------------------------


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _reap(proc: subprocess.Popen, stage_pid: int | None) -> None:
    """Leave nothing behind, whatever the driver did."""
    for target in (proc.pid, stage_pid):
        if target is None:
            continue
        try:
            os.killpg(os.getpgid(target), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if proc.poll() is None:
        try:
            proc.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            pass


def _wait_until(predicate, timeout: float, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_a_signal_to_the_driver_kills_the_running_stage(tmp_path: Path):
    """`kill <driver pid>` must be a real stop button, not a deferred one.

    The driver used to run each stage as a *foreground* pipeline, and bash defers a trap
    until the foreground command returns — so a SIGTERM to the driver did nothing at all
    until the stage finished on its own. On the sweep that stage is `decide`, ~13 hours,
    all of it billed. The stage now runs in its own process group with the driver
    `wait`ing on it, so the trap fires at once, kills the group, waits for it, and only
    then writes STOP.md.

    What is asserted is the operationally load-bearing half: the stage PROCESS is gone.
    """
    spec = tmp_path / "spec.toml"
    spec.write_text('name = "sweep-signal"\ncases = "nowhere.jsonl"\n', encoding="utf-8")
    stub = tmp_path / "stub.sh"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    pid_file = tmp_path / "stage.pid"

    # `start_new_session` puts the driver and everything it spawns in a session of their
    # own, so the cleanup below can SIGKILL the lot. Without it a regression — a driver
    # that ignores the signal — leaves a 300 s sleep holding this test's read pipe open
    # and the suite hangs instead of failing.
    proc = subprocess.Popen(
        ["bash", str(DRIVER), str(spec)],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "RUN_SWEEP_CMD": str(stub),
             "RUN_SWEEP_LOGS": str(tmp_path / "logs"),
             "RUN_SWEEP_OUTPUTS": str(tmp_path / "experiments"),
             "RAN_LOG": str(tmp_path / "ran.txt"),
             "FAIL_AT": str(tmp_path / "none.txt"),
             "STUB_SLEEP": "300", "STUB_PID_FILE": str(pid_file)},
    )
    stage_pid = None
    try:
        assert _wait_until(pid_file.is_file, 15.0), "the stage never started"
        stage_pid = int(pid_file.read_text().strip())
        assert _alive(stage_pid)

        # The signal goes to the DRIVER's pid alone — exactly what an operator types as
        # `kill <driver pid>`. Reaching the stage is the driver's job, not the sender's.
        proc.send_signal(signal.SIGTERM)
        driver_out = proc.communicate(timeout=20.0)[0]
    finally:
        _reap(proc, stage_pid)

    assert proc.returncode == 143, driver_out
    assert _wait_until(lambda: not _alive(stage_pid), 5.0), \
        f"the stage (pid {stage_pid}) outlived the driver — it would still be spending"

    root = tmp_path / "experiments" / "sweep-signal"
    assert not (root / "DONE.md").exists()
    stop = (root / "STOP.md").read_text(encoding="utf-8")
    assert "`signal:TERM`" in stop, stop
    assert "`decide`" in stop, "STOP.md must name the stage that was interrupted"
    # The start line is how wall-clock is read after a resume, so it is printed per
    # attempt and has to survive the change of how the stage is launched.
    assert "=== run_sweep: decide  " in driver_out, driver_out
