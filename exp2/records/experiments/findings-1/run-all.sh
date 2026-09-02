#!/usr/bin/env bash
#
# THE TWO ARMS OF findings-1 (`fd1`) — the WEAK findings judge and the STRONG one — over
# all 1,644 stored debate transcripts, sequentially, under one process.
#
#     cd exp2
#     nohup outputs/fd1-run-all.sh > outputs/fd1-run-all.log 2>&1 &
#     echo $! > outputs/fd1-run-all.pid
#
# DO NOT RUN THIS UNTIL `records/experiments/findings-1/PREREG.md` IS COMMITTED. It is the
# first thing the script checks: the file must be on disk AND tracked by git, because
# "committed before the first paid call" is the whole point of a pre-registration and a
# file sitting untracked in a working tree is not committed.
#
# THE ORDER IS A PREFERENCE, NOT A DEPENDENCY. Neither arm reads the other's tree; both
# read `jd3-main` and write their own. W runs first because it is the arm the campaign
# exists for — the registered claim is F-weak's conjunction P1 ∧ P2 — and the one whose
# failure should stop the spend.
#
#     W  fd1-weak     the findings judge and recourse judge at the challenger's own level
#                     (`meta-llama/llama-4-maverick`, pinned `digitalocean`)
#     S  fd1-strong   the same protocol end to end with a strong judge in both seats
#                     (`openai/gpt-5.6-luna-20260709`, pinned `openai`)
#
# WHAT THE ARMS ACTUALLY DO, in one paragraph, because the assertions below only make
# sense against it. Under `judge_form = "findings"` the judge decomposes its judgment into
# one numbered FINDING per purported flaw the FLAWED-side debater raised — passage, claim,
# defence, reason, ruling FLAW / NOT A FLAW — and writes NO verdict line; the verdict is
# DERIVED by code (FLAWED iff any finding is FLAW, SOUND on an empty list) and the list is
# stored as `findings.json`. Under `challenger_variant = "findings"` the challenger
# contests a numbered finding, an OMISSION or a CONTRADICTION, the recourse judge rules
# each contest ABSOLUTELY, the amended list is stored as `findings.after.json` and the
# verdict after recourse is re-derived from it by the same pure function.
#
# AN ARM POINTED AT A TREE THAT IS NOT THERE RE-JUDGES NOTHING AND EXITS 0 — silently
# producing an empty arm that looks finished. So the script does not merely sequence them:
# after each arm it asserts the tree holds what that arm was supposed to make, and halts
# if it does not. THE LOAD-BEARING ONE IS THE FINDINGS COUNT: an arm that wrote decisions
# but no `findings.json` ran the ORDINARY verdict judge under fd1's name, which is jd3's
# M0 wearing this campaign's label, and none of its numbers may be read as this arm's.
# `judge_form` defaults to `"verdict"`, `DebateConfig` refuses the findings challenger
# without it and `experiment_cli` refuses an fd1-named spec that states neither — this is
# the last of those three doors and it is the only one that closes after the money is
# spent, so it halts rather than warns. Every assertion is COUNTED, not sampled.
#
# `--retry-failed` IS ON FOR BOTH ARMS, and that is the user's standing choice of
# 2026-08-26 (LLM_NOTES.md §3r, HANDOFF.md §5). It is read by `rejudge` alone: a cell whose
# latest re-judge run failed is re-attempted once on a resume, and one that still fails is
# counted and left undecided. `contest` does not read it — its resume key is "does some run
# under this cell's contest directory hold a `challenge.json`" — so a failed challenger
# call is re-attempted on every resume with or without the flag, while a cell that wrote a
# challenge and then lost its RULING is skipped as already contested and stays ruling-less.
# PREREG's missing-cell rule drops those from P1 and P2; they are counted here, never
# absorbed.
#
# STOP BEHAVIOUR. The chain halts at the first arm that exits non-zero, writes a `STOP.md`
# of its own, or fails an assertion, and writes `outputs/fd1-STOP.md` naming the arm.
# Nothing after it runs. Stop triggers are catastrophic-only by the user's standing
# instruction (HANDOFF.md §5): failed cells are counted and reported, never stopped for.
#
# FINGERPRINTS. `jd3-main` is READ by both arms and written by neither, and is hashed
# before the first arm, between them and after the last. It must be byte-identical at all
# three points and equal to
# `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`, which is what it has
# hashed to since `judgment-debate-3` finished and what `outputs/jd6-run-all.sh` pinned.
# `find <tree> -type f | sort | xargs sha256sum | sha256sum`, the form every fingerprint in
# this repo's records uses.
#
# RESUME. Every stage resumes on its own artifacts, so re-running this script after a STOP
# spends nothing on what already succeeded and picks up where it stopped. There is no
# half-cell resume anywhere in this campaign — no debater call is made by either arm.
#
# The four FD1_* variables below exist for an offline exercise that drives this script
# against a stub in a tmp directory. A REAL RUN SETS NONE OF THEM.

set -uo pipefail
cd "$(dirname "$0")/.."

PREREG=${FD1_PREREG:-records/experiments/findings-1/PREREG.md}
RUNNER=${FD1_RUNNER:-scripts/run_sweep.sh}
EXPERIMENTS=${FD1_EXPERIMENTS:-outputs/experiments}
LOGS=${FD1_LOGS:-outputs}
STOP="$LOGS/fd1-STOP.md"
DONE="$LOGS/fd1-ALL-DONE.md"
FINGERPRINTS="$LOGS/fd1-fingerprints.md"

# What `jd3-main` has hashed to since judgment-debate-3 finished. Written down rather than
# only compared before-and-after: an arm that corrupted the source tree BEFORE the first
# fingerprint was taken would pass a before/after comparison and fail this.
EXPECTED_MAIN=dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c

# The decided debate cells `jd3-main` holds, and therefore the number of findings lists a
# complete arm writes. The corpus has 2,110 debate cells; the sweep decided 1,644 and the
# other 466 have no stored transcript, so `rejudge` skips them with `no source decision to
# re-judge`. This is REPORTED against, not asserted equal to: a judgment that truncates or
# will not parse fails its cell and is counted and left undecided, which is exactly the
# loss the feasibility gate is about.
EXPECTED_CELLS=1644

# arm-name | spec | stages
ARMS=(
  "W|fd1-weak|rejudge contest agreement ruling_agreement grade analyse"
  "S|fd1-strong|rejudge contest agreement ruling_agreement grade analyse"
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
        echo "# fd1 STOPPED at arm $1 — $(stamp)"
        echo
        echo "$2"
        echo
        echo "Nothing after this arm ran. Every stage resumes on its own artifacts, so"
        echo "re-running \`outputs/fd1-run-all.sh\` after the cause is fixed spends nothing"
        echo "on what already succeeded — but note that \`contest\` resumes on"
        echo "\`challenge.json\`, so a cell that wrote a challenge and lost its ruling is"
        echo "skipped as already contested and will NOT be re-ruled by a plain resume."
        echo "The fingerprints taken before the first arm are in \`$FINGERPRINTS\`; check"
        echo "them before restarting."
    } > "$STOP"
    echo
    echo "!!! STOPPED at arm $1: $2"
    echo "!!! wrote $STOP"
    fingerprint "after the STOP at arm $1" jd3-main
    exit 1
}

count_in() {  # $1 = spec tree, $2 = filename — this arm's OWN files, never the copy's
    # `-not -path '*/parent/*'` is load-bearing here for the same reason it was in jd6:
    # `copy_parent = true`, so every contest directory carries a full copytree of the
    # decision it contests — including that decision's `findings.json` and `verdict.json`.
    # An unfiltered count would report every decision twice on any cell that was contested.
    find "$EXPERIMENTS/$1/cells" -name "$2" -not -path '*/parent/*' 2>/dev/null | wc -l
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

report_attempts() {  # $1 = spec, $2 = manifest glob — attempted / completed / failed
    # Both arms run rejudge AND contest, so there are TWO populations of runs and they are
    # reported separately: decisions live at `cells/<cell>/runs/*` and contests at
    # `cells/<cell>/contests/<model>/runs/*`. jd6's driver needed only one glob because
    # each of its arms ran one of the two stages; pooling them here would add a cell's
    # decision to its own contest and report 3,288 attempts on a complete arm.
    local a c f
    a=$(count_status "$1" "$2" "")
    c=$(count_status "$1" "$2" "completed")
    f=$(count_status "$1" "$2" "failed")
    echo "$a $c $f"
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

echo "=== fd1: two arms, sequentially — started $(stamp) ==="
echo "PREREG: $PREREG"
echo "arms:   W (fd1-weak), S (fd1-strong)"
echo "runner: $RUNNER   outputs: $EXPERIMENTS   logs: $LOGS"
echo

: > "$FINGERPRINTS"
{
    echo "# findings-1 — tree fingerprints"
    echo
    echo "\`find <tree> -type f | sort | xargs sha256sum | sha256sum\`, the form every"
    echo "fingerprint in this repo's records uses. \`jd3-main\` is READ by both arms and"
    echo "written by neither: it holds the stored debate transcripts both arms re-judge"
    echo "into findings, and M0's verdicts, which are the accuracy comparator. It must be"
    echo "identical at every point below, and equal to \`$EXPECTED_MAIN\`."
    echo
} >> "$FINGERPRINTS"
fingerprint "before the first arm" jd3-main
MAIN_BEFORE=$(hash_of jd3-main)
if [[ "$MAIN_BEFORE" != "$EXPECTED_MAIN" ]]; then
    halt "W" "\`jd3-main\` hashes \`$MAIN_BEFORE\` BEFORE anything ran, not the expected \`$EXPECTED_MAIN\`. Both arms read that tree; if it is not the tree judgment-debate-3 left, nothing measured against jd3, jd5 or jd6 is comparable and no arm should be started."
fi

for entry in "${ARMS[@]}"; do
    IFS='|' read -r arm spec stages <<< "$entry"
    log="$LOGS/fd1-${spec}-driver.log"
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

    # --- what the arm was supposed to make, counted -----------------------------------
    fnd=$(count_in "$spec" findings.json)
    dec=$(count_in "$spec" verdict.json)
    chl=$(count_in "$spec" challenge.json)
    rul=$(count_in "$spec" ruling.json)
    aft=$(count_in "$spec" findings.after.json)
    grd=$(count_in "$spec" grade.json)
    read -r datt dcomp dfail <<< "$(report_attempts "$spec" '*/runs/*')"
    read -r catt ccomp cfail <<< "$(report_attempts "$spec" '*/contests/*/runs/*')"
    echo "########## ARM $arm findings lists: $fnd of $EXPECTED_CELLS decided cells ($dec verdicts derived)"
    echo "########## ARM $arm objections: $chl   rulings: $rul   amended lists: $aft   grades: $grd"
    echo "########## ARM $arm decision runs: $datt attempted, $dcomp completed, $dfail failed"
    echo "########## ARM $arm contest runs:  $catt attempted, $ccomp completed, $cfail failed"

    if [[ "$fnd" -eq 0 ]]; then
        halt "$arm" "The arm exited 0 and wrote ZERO \`findings.json\` files into \`$EXPERIMENTS/${spec}\`. Either \`transcripts_from\` pointed at a tree that is not there — in which case every cell was skipped with \`no source decision to re-judge\` and the stage still exited 0 — or, worse, \`judge_form\` did not survive into \`config.json\` and the judge wrote prose verdicts: A REJUDGE THAT WROTE NO FINDINGS IS A VERDICT-FORM REJUDGE UNDER fd1'S NAME, which is jd3's M0 wearing this campaign's label, and none of its numbers may be read as this arm's. Check \`judge_form = \"findings\"\` in \`experiments/${spec}.toml\` and in the tree's \`config.json\`."
    fi
    if [[ "$fnd" -lt "$EXPECTED_CELLS" ]]; then
        # NOT a halt. A findings list that truncates or will not parse fails its cell and
        # is counted and left undecided — that loss IS the feasibility measurement, and
        # stopping for it would stop for the thing being measured.
        echo "########## NOTE: $((EXPECTED_CELLS - fnd)) of the $EXPECTED_CELLS decided cells carry no findings list. PREREG's missing-cell rule drops them at rejudge (no before-state, out of every table, numerator of the feasibility rate); the derivation lists each one with the error that lost it and breaks the loss down by subset."
    fi
    if [[ "$dec" -ne "$fnd" ]]; then
        echo "########## NOTE: $dec verdicts against $fnd findings lists. Under this form the verdict is DERIVED from the list, so the two counts should match exactly; a difference means a run wrote one and not the other and the derivation must say which."
    fi
    if [[ "$rul" -eq 0 ]]; then
        halt "$arm" "The arm wrote $chl objections and ZERO rulings into \`$EXPERIMENTS/${spec}\`. An arm with no ruling has no after-state, so P1 has nothing to test and P2 has an empty denominator. Either every objection declined — which is itself a result and would have to be read before continuing — or the ruling call failed on every cell."
    fi
    if [[ "$aft" -lt "$rul" ]]; then
        echo "########## NOTE: $((rul - aft)) rulings have no \`findings.after.json\` beside them. The amended list is written by the same code path that derives \`verdict_after\`, so a ruling without one is a ruling whose after-state cannot be checked against the list it claims to follow; the derivation counts them."
    fi
    if [[ "$grd" -eq 0 ]]; then
        halt "$arm" "The arm wrote $chl objections and ZERO grades into \`$EXPERIMENTS/${spec}\`. Under the findings arm EVERY contested cell is graded — sound items and correct decisions included, with no annotation gate — so zero grades means the grade stage did not dispatch to \`_grade_findings\` at all and the validity table would be empty."
    fi

    fingerprint "after arm $arm" jd3-main
    if [[ "$(hash_of jd3-main)" != "$MAIN_BEFORE" ]]; then
        halt "$arm" "\`jd3-main\` MOVED during arm $arm. Both arms read it and neither may write to it; nothing measured against it is valid until this is explained."
    fi
done

fingerprint "after the last arm" jd3-main
MAIN_AFTER=$(hash_of jd3-main)

{
    echo "# fd1 — both arms done, $(stamp)"
    echo
    echo "| arm | spec | decisions attempted | completed | failed | contests attempted | completed | failed | findings | verdicts | objections | rulings | after-lists | grades |"
    echo "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    for entry in "${ARMS[@]}"; do
        IFS='|' read -r arm spec stages <<< "$entry"
        read -r datt dcomp dfail <<< "$(report_attempts "$spec" '*/runs/*')"
        read -r catt ccomp cfail <<< "$(report_attempts "$spec" '*/contests/*/runs/*')"
        echo "| $arm | \`$spec\` | $datt | $dcomp | $dfail | $catt | $ccomp | $cfail | $(count_in "$spec" findings.json) | $(count_in "$spec" verdict.json) | $(count_in "$spec" challenge.json) | $(count_in "$spec" ruling.json) | $(count_in "$spec" findings.after.json) | $(count_in "$spec" grade.json) |"
    done
    echo
    echo "The findings column is against **$EXPECTED_CELLS** decided debate cells in"
    echo "\`jd3-main\`. Every list here was written by a judge under \`judge_form ="
    echo "\"findings\"\`, and the verdict beside it was DERIVED from it by code rather than"
    echo "stated by the judge."
    echo
    echo "**Failed cells are COUNTED, never absorbed.** Under \`PREREG.md\`'s missing-cell"
    echo "rule a cell lost at rejudge has no before-state and leaves every table (and is"
    echo "the numerator of the feasibility rate); one lost at contest leaves P1's pairing"
    echo "and P2's denominator; one lost at ruling is contested with no after-state and is"
    echo "never an uphold; one lost at grade or at the instrument stays in P1-P3 and leaves"
    echo "that table alone. The derivation's section (0) lists each with the error that"
    echo "lost it, per stage and per arm, and breaks the rejudge losses down by subset."
    echo "\`--retry-failed\` was on, so a cell failed at rejudge here failed TWICE."
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
    echo "Next: \`uv run python records/derivations/findings-1.py\`."
} > "$DONE"

echo
echo "=== fd1: both arms done $(stamp) ==="
cat "$DONE"
if [[ "$MAIN_BEFORE" != "$MAIN_AFTER" ]]; then
    echo "!!! jd3-main CHANGED"
    exit 1
fi
