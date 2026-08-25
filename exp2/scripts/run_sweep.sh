#!/usr/bin/env bash
#
# The sweep driver: five stages, sequentially, under one background process.
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
#   * DONE.md is written only when all five completed.
#
# Re-running the driver after a STOP is safe and is the intended repair: every stage
# resumes on its own artifacts and spends nothing on cells that already have a completed
# record.
#
# The three RUN_SWEEP_* environment variables exist for the offline test
# (tests/test_run_sweep.py), which drives this script against a stub command in a tmp
# directory. A real run sets none of them.

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
STAGES=(decide contest agreement grade analyse)

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

on_signal() {
    local signal=$1
    stop "$CURRENT_STAGE" "signal:$signal" \
        "The driver was killed by SIG$signal rather than a stage failing."
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
    # Word splitting on $CMD is deliberate: it is a command line ("uv run
    # exp2-experiment"), not a single executable.
    # shellcheck disable=SC2086
    $CMD --spec "$SPEC" --stage "$stage" --outputs "$OUTPUTS" 2>&1 | tee -a "$log"
    status=${PIPESTATUS[0]}
    echo "=== run_sweep: $stage exited $status  $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if [[ $status -ne 0 ]]; then
        stop "$stage" "$status"
        exit "$status"
    fi
done

{
    echo "# DONE"
    echo
    echo "All five stages completed: ${STAGES[*]}."
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
echo "run_sweep: ALL FIVE STAGES COMPLETED -> $ROOT/DONE.md"
