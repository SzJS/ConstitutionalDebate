#!/usr/bin/env bash
# Mop-up after fd1-ALL-DONE (2026-09-02): one resume pass per arm, sequential, --retry-failed,
# to re-attempt (a) the ~8 run dirs the 17:03Z incident left "running", (b) failed rejudges,
# (c) failed contests (no challenge.json), and re-run the off-path stages + analyse.
set -uo pipefail
cd "$(dirname "$0")/.."
for spec in fd1-weak fd1-strong; do
  echo "=== mop-up $spec  $(date -u +%FT%TZ) ==="
  RUN_SWEEP_CMD="uv run exp2-experiment --retry-failed" \
  RUN_SWEEP_STAGES="rejudge contest agreement ruling_agreement grade analyse" \
    scripts/run_sweep.sh experiments/$spec.toml > outputs/$spec-mopup-driver.log 2>&1
  echo "=== mop-up $spec exit $?  $(date -u +%FT%TZ) ==="
done
echo "=== MOP-UP DONE $(date -u +%FT%TZ) ===" | tee outputs/fd1-mopup-DONE.md
