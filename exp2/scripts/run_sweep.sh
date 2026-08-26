#!/usr/bin/env bash
#
# The sweep driver: the five stages, sequentially, under one background process.
#
#     cd exp2
#     nohup scripts/run_sweep.sh experiments/sweep.toml > outputs/sweep-driver.log 2>&1 &
#
# Why this exists rather than a shell loop in the hand-off. An agent harness caps a
# foreground shell at minutes and blocks `sleep`, so the `PID=$!; until ! ps -p $PID; do
# sleep 60; done` pattern cannot be executed by an agent at all — and `decide` alone is
# ~13 h. One detached driver that an agent *polls* is the shape that works: the driver
# holds the sequencing, and the poller only reads files.
#
# What it guarantees:
#   * stages run in order — decide, contest, agreement, grade, analyse — and each starts
#     only after the previous one exited 0. contest reads decide's artifacts, so an
#     overlap would silently contest cells that were still being written.
#   * every stage's output is teed to outputs/<name>-<stage>.log while still printing,
#     so it lands in the driver log too and neither copy is the only one.
#   * the FIRST non-zero exit halts the chain and writes STOP.md. A stage exits non-zero
#     only when the stage itself crashed; failed *cells* are counted and reported and
#     leave the exit status at 0, which is stop trigger 3 in HANDOFF.md §5 and nothing
#     else.
#   * DONE.md is written only when every stage in the list completed.
#   * a signal to the DRIVER stops the STAGE. Each stage runs in its own process group
#     and the driver waits on it, so SIGINT/SIGTERM to the driver's pid kills the whole
#     stage tree — uv, python, tee — waits for it to die, writes STOP.md naming
#     `signal:TERM` (or INT), and exits 143. `kill <driver pid>` is therefore a real
#     stop button; before this the trap was deferred behind a foreground pipeline and
#     `decide` carried on spending for hours.
#
# Re-running the driver after a STOP is safe and is the intended repair: every stage
# resumes on its own artifacts and spends nothing on cells that already have a completed
# record.
#
# RUN_SWEEP_STAGES names the stages to run, in order; unset means all five. It is the
# one of these variables a real run may set, and the re-contest is why: a spec with
# `decisions_from` contests a tree it does not decide, so `decide` must not run and
# would refuse if it did.
#
#     RUN_SWEEP_STAGES="contest agreement grade analyse" nohup \
#         scripts/run_sweep.sh experiments/recontest.toml > outputs/x.log 2>&1 &
#
# The other three RUN_SWEEP_* variables exist for the offline test
# (tests/test_run_sweep.py), which drives this script against a stub command in a tmp
# directory. A real run sets none of THOSE.

set -uo pipefail

SPEC="${1:-}"
if [[ -z "$SPEC" ]]; then
    echo "usage: nohup scripts/run_sweep.sh <spec.toml> > outputs/sweep-driver.log 2>&1 &" >&2
    exit 64
fi
if [[ ! -f "$SPEC" ]]; then
    echo "run_sweep: no such spec: $SPEC" >&2
    exit 66
fi

CMD=${RUN_SWEEP_CMD:-"uv run exp2-experiment"}
LOGS=${RUN_SWEEP_LOGS:-outputs}
OUTPUTS=${RUN_SWEEP_OUTPUTS:-outputs/experiments}
# shellcheck disable=SC2206
STAGES=(${RUN_SWEEP_STAGES:-decide contest agreement grade analyse})

# The run's name comes from the spec, exactly as experiment_cli.py derives it: the
# top-level `name` key, falling back to the file stem. Reading it here rather than
# passing it in keeps the log names and the outputs directory from drifting apart.
NAME=$(sed -n 's/^name[[:space:]]*=[[:space:]]*"\([^"]*\)".*$/\1/p' "$SPEC" | head -1)
[[ -n "$NAME" ]] || NAME=$(basename "$SPEC" .toml)

ROOT="$OUTPUTS/$NAME"
mkdir -p "$ROOT" "$LOGS"
rm -f "$ROOT/STOP.md" "$ROOT/DONE.md"

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "run_sweep: spec=$SPEC name=$NAME pid=$$ started=$started"
echo "run_sweep: stages: ${STAGES[*]}"
echo "run_sweep: per-stage logs: $LOGS/$NAME-<stage>.log"
echo "run_sweep: outputs: $ROOT"

stop() {  # stage, exit code, note
    local stage=$1 code=$2 note=${3:-}
    {
        echo "# STOPPED"
        echo
        echo "| | |"
        echo "|---|---|"
        echo "| stage | \`$stage\` |"
        echo "| exit code | \`$code\` |"
        echo "| spec | \`$SPEC\` |"
        echo "| stage log | \`$LOGS/$NAME-$stage.log\` |"
        echo "| driver pid | \`$$\` |"
        echo "| started (UTC) | $started |"
        echo "| stopped (UTC) | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
        echo
        [[ -n "$note" ]] && { echo "$note"; echo; }
        echo "The chain halted here: the stages after \`$stage\` were NOT run."
        echo
        echo "A stage exits non-zero only when the stage itself crashed — failed cells are"
        echo "counted and reported and leave the exit status at 0. So this is HANDOFF.md §5"
        echo "stop trigger 3, and it is one of the four things to wake the user for."
        echo
        echo "Read the tail of the stage log for the traceback. Re-running the driver"
        echo "resumes: every stage skips cells that already have a completed record."
    } > "$ROOT/STOP.md"
    echo "run_sweep: STOPPED at $stage (exit $code) -> $ROOT/STOP.md"
}

# Job control, so that every backgrounded stage below becomes the leader of its OWN
# process group. That is the whole mechanism behind on_signal: `kill -TERM -$STAGE_PID`
# then reaches the subshell, the `uv run` it spawned, the python under that, and the
# `tee`. Without it they all share the driver's group and a signal that reaches the
# driver reaches nothing else.
set -m

STAGE_PID=""

# Kill the stage's whole process group and wait for it to actually be gone. Returns
# once nothing in the group answers, or after ~5 s of TERM followed by KILL.
kill_stage() {
    [[ -n "$STAGE_PID" ]] || return 0
    kill -0 "$STAGE_PID" 2>/dev/null || return 0
    echo "run_sweep: killing stage process group $STAGE_PID"
    kill -TERM "-$STAGE_PID" 2>/dev/null
    local i
    for ((i = 0; i < 50; i++)); do
        kill -0 "-$STAGE_PID" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "-$STAGE_PID" 2>/dev/null; then
        echo "run_sweep: stage group $STAGE_PID survived SIGTERM; sending SIGKILL"
        kill -KILL "-$STAGE_PID" 2>/dev/null
    fi
    wait "$STAGE_PID" 2>/dev/null
    STAGE_PID=""
}

on_signal() {
    local signal=$1
    echo
    echo "run_sweep: caught SIG$signal during $CURRENT_STAGE"
    # The stage is what spends money, so it dies FIRST and the bookkeeping happens
    # after. A driver that wrote STOP.md and exited while `decide` kept running would
    # report a stopped sweep that was still billing for thirteen hours.
    kill_stage
    stop "$CURRENT_STAGE" "signal:$signal" \
        "The driver was killed by SIG$signal rather than a stage failing. The stage's process group was signalled and waited for before this file was written, so nothing is still spending."
    exit 143
}
CURRENT_STAGE="(none)"
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

for stage in "${STAGES[@]}"; do
    CURRENT_STAGE=$stage
    log="$LOGS/$NAME-$stage.log"
    echo
    echo "=== run_sweep: $stage  $(date -u +%Y-%m-%dT%H:%M:%SZ)  -> $log ==="
    # The stage runs in a BACKGROUNDED subshell and the driver `wait`s on it, rather
    # than as a foreground pipeline. Two reasons, both signal-shaped:
    #   * bash defers a trap until the current foreground command returns, so a
    #     foreground pipeline meant `kill <driver pid>` did nothing at all until the
    #     stage finished on its own — thirteen hours of `decide` later.
    #   * `wait` IS interruptible: a caught signal returns from it immediately and runs
    #     the trap, which then kills the stage's process group.
    # `set -m` above makes the subshell its own process group leader, so $! is also the
    # group id. The subshell re-exports PIPESTATUS[0] as its own exit status, so the
    # stage's status — not tee's — is still what the chain halts on.
    #
    # Word splitting on $CMD is deliberate: it is a command line ("uv run
    # exp2-experiment"), not a single executable.
    (
        # shellcheck disable=SC2086
        $CMD --spec "$SPEC" --stage "$stage" --outputs "$OUTPUTS" 2>&1 | tee -a "$log"
        exit "${PIPESTATUS[0]}"
    ) &
    STAGE_PID=$!
    wait "$STAGE_PID"
    status=$?
    STAGE_PID=""
    echo "=== run_sweep: $stage exited $status  $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if [[ $status -ne 0 ]]; then
        stop "$stage" "$status"
        exit "$status"
    fi
done

{
    echo "# DONE"
    echo
    echo "All stages completed: ${STAGES[*]}."
    echo
    echo "| | |"
    echo "|---|---|"
    echo "| spec | \`$SPEC\` |"
    echo "| started (UTC) | $started |"
    echo "| finished (UTC) | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
    echo "| stage logs | \`$LOGS/$NAME-{$(IFS=,; echo "${STAGES[*]}")}.log\` |"
    echo
    echo "Completing is not the same as succeeding: read the per-stage cell counts and"
    echo "\`$ROOT/metrics.json\` before quoting anything. HANDOFF.md §5 'After the run'"
    echo "is the checklist."
} > "$ROOT/DONE.md"
echo
echo "run_sweep: ALL STAGES COMPLETED (${STAGES[*]}) -> $ROOT/DONE.md"
