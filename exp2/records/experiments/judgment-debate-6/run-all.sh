#!/usr/bin/env bash
#
# THE TWO ARMS OF judgment-debate-6 — the contestability debate round against a plain
# extra round — sequentially, under one process.
#
#     cd exp2
#     nohup outputs/jd6-run-all.sh > outputs/jd6-run-all.log 2>&1 &
#     echo $! > outputs/jd6-run-all.pid
#
# DO NOT RUN THIS UNTIL `records/experiments/judgment-debate-6/PREREG.md` IS COMMITTED.
# It is the first thing the script checks: the file must be on disk AND tracked by git,
# because "committed before the first paid call" is the whole point of a pre-registration
# and a file sitting untracked in a working tree is not committed.
#
# THE ORDER IS A PREFERENCE, NOT A DEPENDENCY — and that is worth saying, because jd3's
# driver's order WAS a dependency and this one's is not. Neither arm reads the other's
# tree; both read `jd3-main` and write their own. R runs first because it is the arm the
# campaign exists for and the one whose failure should stop the spend.
#
#     R  jd6-round   M1's 896 objections, ARGUED by the two original debaters, then ruled
#     B  jd6-plain   the same 896 cells, ONE MORE ORDINARY ROUND, then re-judged
#
# An arm pointed at a tree that does not exist yet rules nothing and EXITS 0 — silently
# producing an empty arm that looks finished. So the script does not merely sequence them:
# after each arm it asserts the tree holds what that arm was supposed to make, and halts
# if it does not. R must have written `recourse_transcript.json` files as well as rulings,
# because an arm that ruled without hearing a round is jd5-B under jd6's name; B must have
# written FOUR-ROUND transcripts, because a rejudge that added no round is jd3's M0 under
# jd6's name. Both assertions are counted, not sampled.
#
# `--retry-failed` IS ON FOR BOTH ARMS, and that is the user's standing choice of
# 2026-08-26 (LLM_NOTES.md §3r, HANDOFF.md §5): a cell whose latest run failed is
# re-attempted once on a resume, and a cell that still fails is counted and left
# undecided. NOTE WHAT IT COSTS IN ARM R: the resume key is "does this cell hold a
# ruling", so a retried cell re-buys both round-4 turns. That is deliberate — there is no
# half-round resume, and ruling on one stored reply and one fresh one would be a different
# protocol wearing this one's name.
#
# STOP BEHAVIOUR. The chain halts at the first arm that exits non-zero, writes a `STOP.md`
# of its own, or produces nothing, and writes `outputs/jd6-STOP.md` naming the arm.
# Nothing after it runs. Stop triggers are catastrophic-only by the user's standing
# instruction (HANDOFF.md §5): failed cells are counted and reported, never stopped for.
#
# FINGERPRINTS. `jd3-main` is READ by both arms and written by neither, and is hashed
# before the first arm, between them and after the last. It must be byte-identical at all
# three points and equal to `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`,
# which is what it has hashed to since `judgment-debate-3` finished.
# `find <tree> -type f | sort | xargs sha256sum | sha256sum`, the form every fingerprint
# in this repo's records uses.
#
# RESUME. Every stage resumes on its own artifacts, so re-running this script after a STOP
# spends nothing on what already succeeded and picks up where it stopped.
#
# The four JD6_* variables below exist for an offline exercise that drives this script
# against a stub in a tmp directory. A REAL RUN SETS NONE OF THEM.

set -uo pipefail
cd "$(dirname "$0")/.."

PREREG=${JD6_PREREG:-records/experiments/judgment-debate-6/PREREG.md}
RUNNER=${JD6_RUNNER:-scripts/run_sweep.sh}
EXPERIMENTS=${JD6_EXPERIMENTS:-outputs/experiments}
LOGS=${JD6_LOGS:-outputs}
STOP="$LOGS/jd6-STOP.md"
DONE="$LOGS/jd6-ALL-DONE.md"
FINGERPRINTS="$LOGS/jd6-fingerprints.md"

# What `jd3-main` has hashed to since judgment-debate-3 finished. Written down rather than
# only compared before-and-after: an arm that corrupted the source tree BEFORE the first
# fingerprint was taken would pass a before/after comparison and fail this.
EXPECTED_MAIN=dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c

# arm-name | spec | stages
ARMS=(
  "R|jd6-round|rerule ruling_agreement analyse"
  "B|jd6-plain|rejudge analyse"
)

stamp() { date -u +%FT%TZ; }

hash_of() {
    local path="$EXPERIMENTS/$1"
    if [[ -d "$path" ]]; then
        find "$path" -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1
    else
        echo "MISSING"
    fi
}

fingerprint() {
    # $1 = label written into the record; $2.. = trees
    local label=$1; shift
    echo "## $label — $(stamp)" >> "$FINGERPRINTS"
    echo "| tree | sha256 |" >> "$FINGERPRINTS"
    echo "|---|---|" >> "$FINGERPRINTS"
    local tree h
    for tree in "$@"; do
        h=$(hash_of "$tree")
        echo "| \`$tree\` | \`$h\` |" >> "$FINGERPRINTS"
        echo "  fingerprint $tree $h"
    done
    echo >> "$FINGERPRINTS"
}

halt() {
    # $1 = arm name, $2 = why
    {
        echo "# jd6 STOPPED at arm $1 — $(stamp)"
        echo
        echo "$2"
        echo
        echo "Nothing after this arm ran. Every stage resumes on its own artifacts, so"
        echo "re-running \`outputs/jd6-run-all.sh\` after the cause is fixed spends nothing"
        echo "on what already succeeded — EXCEPT in arm R, where a cell with no ruling"
        echo "re-buys both of its round-4 turns. The fingerprints taken before the first"
        echo "arm are in \`$FINGERPRINTS\`; check them before restarting."
    } > "$STOP"
    echo
    echo "!!! STOPPED at arm $1: $2"
    echo "!!! wrote $STOP"
    fingerprint "after the STOP at arm $1" jd3-main
    exit 1
}

count_in() {  # $1 = spec tree, $2 = filename — this arm's OWN files, never the copy's
    # `-not -path '*/parent/*'` is load-bearing in the ROUND arm: every contest directory
    # carries a full copy of the decision it contests, so an unfiltered count of
    # `verdict.json` there counts the copied decisions and an unfiltered count of any
    # manifest counts the copied runs. The first draft of this script reported 12
    # attempted cells on a six-cell smoke for exactly that reason.
    find "$EXPERIMENTS/$1/cells" -name "$2" -not -path '*/parent/*' 2>/dev/null | wc -l
}

count_two_turn_rounds() {  # $1 = spec tree — exchanges holding EXACTLY 2 turns
    # Exactly two, not "at least one". `hear_exchange` commits the turn that completed
    # before it raises (`debate._run_round`'s rule), so a cell that lost one debater
    # leaves a ONE-TURN `recourse_transcript.json` behind in a run whose manifest says
    # failed. Counting those as exchanges would report a half-round as a round, and a
    # ruling made on one reply is not the protocol this arm registered.
    local n=0 path turns
    while IFS= read -r path; do
        turns=$(grep -c '"round":' "$path" 2>/dev/null)
        [[ "$turns" -eq 2 ]] && n=$((n + 1))
    done < <(find "$EXPERIMENTS/$1/cells" -name recourse_transcript.json \
                  -not -path '*/parent/*' 2>/dev/null)
    echo "$n"
}

count_status() {  # $1 = spec tree, $2 = manifest glob, $3 = status ("" = every run)
    local n=0 path
    while IFS= read -r path; do
        if [[ -z "$3" ]] || grep -q "\"status\": \"$3\"" "$path" 2>/dev/null; then
            n=$((n + 1))
        fi
    done < <(find "$EXPERIMENTS/$1/cells" -path "$2" -name run.json \
                  -not -path '*/parent/*' 2>/dev/null)
    echo "$n"
}

manifest_glob() {  # $1 = spec — where that arm's own runs live
    if [[ "$1" == *round* ]]; then echo '*/contests/*/runs/*'; else echo '*/runs/*'; fi
}

report_attempts() {  # $1 = spec
    local g a c f
    g=$(manifest_glob "$1")
    a=$(count_status "$1" "$g" "")
    c=$(count_status "$1" "$g" "completed")
    f=$(count_status "$1" "$g" "failed")
    echo "$a $c $f"
}

count_four_round() {  # $1 = spec tree — DECIDED cells whose transcript reaches round 4
    # The verdict.json test is not decoration. A cell whose round-4 turn truncated commits
    # the turn that completed before failing (`debate._run_round`'s rule), so its
    # transcript.json holds a round 4 and its run holds no verdict — counting it here
    # would report a half-round failure as a played round.
    local n=0 path
    while IFS= read -r path; do
        [[ -f "$(dirname "$path")/verdict.json" ]] || continue
        if grep -q '"round": 4' "$path" 2>/dev/null; then n=$((n + 1)); fi
    done < <(find "$EXPERIMENTS/$1/cells" -path '*/runs/*' -name transcript.json \
                  -not -path '*/parent/*' 2>/dev/null)
    echo "$n"
}

if [[ ! -f "$PREREG" ]]; then
    echo "REFUSING: $PREREG is not on disk. The pre-registration is committed BEFORE the"
    echo "first paid call of the first arm; that is the whole point of it."
    exit 64
fi
if command -v git > /dev/null 2>&1; then
    if ! git ls-files --error-unmatch "$PREREG" > /dev/null 2>&1; then
        echo "REFUSING: $PREREG exists but is NOT TRACKED BY GIT, so it is not committed."
        echo "A pre-registration that only exists in a working tree can still be edited"
        echo "after the numbers, which is the one thing it exists to make impossible."
        echo "Commit it, then run this script."
        exit 64
    fi
fi
if [[ -f "$STOP" ]]; then
    echo "note: a previous run left $STOP; removing it and resuming."
    rm -f "$STOP"
fi
rm -f "$DONE"

echo "=== jd6: two arms, sequentially — started $(stamp) ==="
echo "PREREG: $PREREG"
echo "arms:   R (jd6-round), B (jd6-plain)"
echo "runner: $RUNNER   outputs: $EXPERIMENTS   logs: $LOGS"
echo

: > "$FINGERPRINTS"
{
    echo "# judgment-debate-6 — tree fingerprints"
    echo
    echo "\`find <tree> -type f | sort | xargs sha256sum | sha256sum\`, the form every"
    echo "fingerprint in this repo's records uses. \`jd3-main\` is READ by both arms and"
    echo "written by neither: it holds M0's decisions, M1's objections and the judgments"
    echo "both arms argue about. It must be identical at every point below, and equal to"
    echo "\`$EXPECTED_MAIN\`."
    echo
} >> "$FINGERPRINTS"
fingerprint "before the first arm" jd3-main
MAIN_BEFORE=$(hash_of jd3-main)
if [[ "$MAIN_BEFORE" != "$EXPECTED_MAIN" ]]; then
    halt "R" "\`jd3-main\` hashes \`$MAIN_BEFORE\` BEFORE anything ran, not the expected \`$EXPECTED_MAIN\`. Both arms read that tree; if it is not the tree judgment-debate-3 left, nothing measured against jd3, jd4 or jd5 is comparable and no arm should be started."
fi

for entry in "${ARMS[@]}"; do
    IFS='|' read -r arm spec stages <<< "$entry"
    log="$LOGS/jd6-${spec}-driver.log"
    echo
    echo "########## ARM $arm  ($spec)  $(stamp)"
    echo "########## stages: $stages   -> $log"
    RUN_SWEEP_CMD="uv run exp2-experiment --retry-failed" \
    RUN_SWEEP_STAGES="$stages" \
    RUN_SWEEP_LOGS="$LOGS" \
    RUN_SWEEP_OUTPUTS="$EXPERIMENTS" \
        "$RUNNER" "experiments/${spec}.toml" > "$log" 2>&1
    code=$?
    echo "########## ARM $arm exited $code  $(stamp)"
    tail -20 "$log"

    if [[ $code -ne 0 ]]; then
        halt "$arm" "\`$RUNNER experiments/${spec}.toml\` exited $code. Its log is \`$log\`."
    fi
    if [[ -f "$EXPERIMENTS/${spec}/STOP.md" ]]; then
        halt "$arm" "The arm wrote its own STOP.md: \`$EXPERIMENTS/${spec}/STOP.md\`."
    fi

    if [[ "$spec" == "jd6-round" ]]; then
        n=$(count_in "$spec" ruling.json)
        e=$(count_in "$spec" recourse_transcript.json)
        t=$(count_two_turn_rounds "$spec")
        read -r att comp fail <<< "$(report_attempts "$spec")"
        echo "########## ARM $arm wrote $n rulings and $e exchanges ($t of them two-turn)"
        echo "########## ARM $arm cells: $att attempted, $comp completed, $fail failed"
        if [[ "$n" -eq 0 ]]; then
            halt "$arm" "The arm exited 0 and wrote ZERO rulings into \`$EXPERIMENTS/${spec}\`. That almost always means \`decisions_from\` / \`contests_from\` pointed at a tree that is not there, in which case every cell was skipped with \`no decision to rule against\` and the stage still exited 0."
        fi
        if [[ "$e" -eq 0 ]]; then
            halt "$arm" "The arm wrote $n rulings and ZERO \`recourse_transcript.json\` files, so it ruled WITHOUT hearing a round. That is jd5-B under jd6's name and none of its numbers may be read as this arm's. Check that \`recourse_rounds = 1\` survived into \`config.json\`."
        fi
        if [[ "$e" -lt "$n" ]]; then
            echo "########## NOTE: $((n - e)) rulings have no exchange beside them; the derivation reports them, and \`recourse_rounds\` on each ruling says which."
        fi
        if [[ "$t" -lt "$e" ]]; then
            # Not a halt: a half-round dir is what a FAILED cell leaves behind, and the
            # cell is counted and reported rather than stopped for. It is printed because
            # a one-turn exchange beside a ruling would be a ruling on one reply, which is
            # a different protocol from the one PREREG.md registers.
            echo "########## NOTE: $((e - t)) \`recourse_transcript.json\` files do NOT hold exactly two turns. A half-round is what a failed cell leaves behind (the completed turn is committed before the raise); check that none of them sits beside a \`ruling.json\` — the derivation's section (6) counts them and PREREG.md's loss rule drops those cells."
        fi
    else
        d=$(count_in "$spec" verdict.json)
        r4=$(count_four_round "$spec")
        read -r att comp fail <<< "$(report_attempts "$spec")"
        echo "########## ARM $arm wrote $d decisions, $r4 of them from a four-round transcript"
        echo "########## ARM $arm cells: $att attempted, $comp completed, $fail failed"
        if [[ "$d" -eq 0 ]]; then
            halt "$arm" "The arm exited 0 and wrote ZERO decisions into \`$EXPERIMENTS/${spec}\`. That almost always means \`transcripts_from\` pointed at a tree that is not there, in which case every cell was skipped with \`no source decision to re-judge\` and the stage still exited 0."
        fi
        if [[ "$r4" -eq 0 ]]; then
            halt "$arm" "The arm wrote $d decisions and NONE of them from a four-round transcript, so no extra round was played. That is jd3's M0 under jd6's name and none of its numbers may be read as this arm's. Check that \`extend_rounds = true\` and \`n_rounds = 4\` survived into \`config.json\`."
        fi
        if [[ "$r4" -lt "$d" ]]; then
            echo "########## NOTE: $((d - r4)) decisions were judged from a shorter transcript; the derivation reports them, and \`extended_from_rounds\` in the index says which."
        fi
    fi

    fingerprint "after arm $arm" jd3-main
    if [[ "$(hash_of jd3-main)" != "$MAIN_BEFORE" ]]; then
        halt "$arm" "\`jd3-main\` MOVED during arm $arm. Both arms read it and neither may write to it; nothing measured against it is valid until this is explained."
    fi
done

fingerprint "after the last arm" jd3-main
MAIN_AFTER=$(hash_of jd3-main)

{
    echo "# jd6 — both arms done, $(stamp)"
    echo
    echo "| arm | spec | attempted | completed | failed | rulings | two-turn rounds | decisions | four-round |"
    echo "|---|---|---|---|---|---|---|---|---|"
    for entry in "${ARMS[@]}"; do
        IFS='|' read -r arm spec stages <<< "$entry"
        read -r att comp fail <<< "$(report_attempts "$spec")"
        echo "| $arm | \`$spec\` | $att | $comp | $fail | $(count_in "$spec" ruling.json) | $(count_two_turn_rounds "$spec") | $(count_in "$spec" verdict.json) | $(count_four_round "$spec") |"
    done
    echo
    echo "**Failed cells are COUNTED, never absorbed.** Under \`PREREG.md\`'s loss rule a"
    echo "cell missing in either arm leaves every paired table; the derivation's section (0)"
    echo "lists each one with the error that lost it. \`--retry-failed\` was on, so a cell"
    echo "here failed TWICE, and because the debaters run at temperature 0.7 a retried cell"
    echo "was a different draw rather than a repeat."
    echo
    if [[ "$MAIN_BEFORE" != "$MAIN_AFTER" ]]; then
        echo "**\`jd3-main\` CHANGED — the campaign's numbers are NOT valid."
        echo "Nothing here may be read until this is explained.** It is read by both arms"
        echo "and written by neither."
    else
        echo "\`jd3-main\` byte-identical before and after: \`$MAIN_AFTER\`."
    fi
    echo
    echo "Hashes in \`$FINGERPRINTS\`."
    echo
    echo "Next: \`uv run python records/derivations/judgment-debate-6.py\`."
} > "$DONE"

echo
echo "=== jd6: both arms done $(stamp) ==="
cat "$DONE"
if [[ "$MAIN_BEFORE" != "$MAIN_AFTER" ]]; then
    echo "!!! jd3-main CHANGED"
    exit 1
fi
